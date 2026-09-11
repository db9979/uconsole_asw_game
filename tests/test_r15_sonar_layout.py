"""R15 sonar layout, contrast, mouse, and station acceptance contracts."""

import builtins
import copy
import pickle
from dataclasses import replace
from types import SimpleNamespace as NS

import numpy as np
import pygame
import pytest

from src.core import config
from src.core.game import Game, letterbox_layout
from src.core.i18n import Translator, load_catalog, pseudolocale
from src.core.station import Station
from src.sonar.sonar import Contact
from src.ui import layout, sonar_view


def press(game, key, **values):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, **values))


def test_1280x800_letterbox_transform_and_bar_rejection(monkeypatch):
    game = Game(seed=1510, start_menu=False, audio_enabled=False)
    monkeypatch.setattr(pygame.display, "get_window_size", lambda: (1280, 800))
    assert letterbox_layout(1280, 800) == (1.0, 0, 40, 1280, 720)
    assert game._window_to_canvas((0, 40)) == (0, 0)
    assert game._window_to_canvas((1279, 759)) == (1279, 719)
    assert game._window_to_canvas((640, 39)) is None
    assert game._window_to_canvas((640, 760)) is None


def test_station_keys_one_through_nine_and_no_context_leak():
    game = Game(seed=1511, start_menu=False, audio_enabled=False)
    original_gain = game.sonar.gain_db
    for index, station in enumerate(Station):
        press(game, pygame.K_1 + index)
        assert game.station is station
    game.station = Station.SONAR
    press(game, pygame.K_3)
    press(game, pygame.K_o)
    assert game.station is Station.WEAPONS
    assert game.sonar.gain_db == original_gain


@pytest.mark.parametrize("page", range(6))
def test_every_sonar_page_keeps_main_panel_and_three_contact_rows(page):
    game = Game(seed=1512, start_menu=False, audio_enabled=False)
    game.station = Station.SONAR
    game.sonar_page = page
    previous = config.STATION_RECT
    config.STATION_RECT = config.FULL_STATION_RECT
    try:
        regions = sonar_view.sonar_geometry(game)
    finally:
        config.STATION_RECT = previous
    assert regions["main"].w >= 850 and regions["main"].h >= 380
    assert (regions["contacts"].h - 33) // 43 >= 3


def test_tabs_contacts_and_safe_actions_share_draw_hit_geometry(monkeypatch):
    game = Game(seed=1513, start_menu=False, audio_enabled=False)
    game.station = Station.SONAR
    contact = Contact(73, 9001, "passiv", "sub")
    contact.bearing = 42
    contact.last_seen = game.sim_t
    game.sonar.active_contacts = lambda: [contact]
    previous = config.STATION_RECT
    config.STATION_RECT = config.FULL_STATION_RECT
    try:
        with layout.capture_geometry() as drawn:
            sonar_view.draw_sonar_view(game)
        regions = sonar_view.sonar_geometry(game)
        for index, rect in enumerate(regions["tabs"]):
            assert sonar_view.sonar_click_target(game, rect.center) == {
                "action": "page_set", "value": index, "safe": True}
        contact_rect = next(item["rect"] for item in drawn
                            if item["kind"] == "sonar-contact")
        assert sonar_view.sonar_click_target(game, contact_rect.center)["value"] == 73
        contacts = regions["contacts"]
        assert sonar_view.sonar_click_target(game, (contacts.x + 2, contact_rect.centery)) is None
        assert sonar_view.sonar_click_target(game, (contact_rect.centerx, contact_rect.bottom)) is None
        assert sonar_view.sonar_hit_target(game, (contacts.x + 2, contact_rect.centery)) is None
        assert sonar_view.sonar_hit_target(game, (contact_rect.centerx, contact_rect.bottom)) is None
        game.sonar_page = 5
        game.sonar.echo_history = [dict(t=game.sim_t, contact_id=73, bearing=42,
                                        range_nm=3, range_sigma_nm=.2,
                                        depth_m=None, depth_sigma_m=None,
                                        snr_db=8, mode="BOW")]
        with layout.capture_geometry() as echo_drawn:
            sonar_view.draw_sonar_view(game)
        echo_rect = next(item["rect"] for item in echo_drawn
                         if item["kind"] == "sonar-echo")
        echo_contacts = sonar_view.sonar_geometry(game)["contacts"]
        assert sonar_view.sonar_click_target(game, echo_rect.center)["value"] == 73
        assert sonar_view.sonar_click_target(game, (echo_contacts.x + 2, echo_rect.centery)) is None
        assert sonar_view.sonar_click_target(game, (echo_rect.centerx, echo_rect.bottom)) is None
        action_rects = {item["title"]: item["rect"] for item in drawn
                        if item["kind"] == "sonar-action"}
        assert set(action_rects) == {
            "sonar:action:page", "sonar:action:array", "sonar:action:gain",
            "sonar:action:band_filter", "sonar:action:notch",
            "sonar:action:harmonic", "sonar:action:peak", "sonar:action:audio"}
        for name, rect in action_rects.items():
            target = sonar_view.sonar_click_target(game, rect.center)
            assert target == {"action": name.rsplit(":", 1)[-1], "safe": True}
    finally:
        config.STATION_RECT = previous


def test_sonar_mouse_works_without_tooltips_and_never_launches_weapon(monkeypatch):
    game = Game(seed=1514, start_menu=False, audio_enabled=False)
    game.station = Station.SONAR
    game.tooltips_enabled = False
    monkeypatch.setattr(pygame.display, "get_window_size", lambda: (1280, 800))
    launched = []
    monkeypatch.setattr(game, "launch_torpedo", lambda: launched.append(True))
    previous = config.STATION_RECT
    config.STATION_RECT = config.FULL_STATION_RECT
    try:
        tab = sonar_view.sonar_geometry(game)["tabs"][2]
    finally:
        config.STATION_RECT = previous
    game.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=(tab.centerx, tab.centery + 40)))
    assert game.sonar_page == 2
    assert launched == []


def test_harmonic_aid_requires_explicit_transient_operator_selection():
    game = Game(seed=1517, start_menu=False, audio_enabled=False)
    game.station = Station.SONAR
    game.sonar_page = 1
    game.sonar.receiver.peaks = [(12.0, .8), (24.0, .7)]
    assert game.sonar_harmonic_hz is None
    assert "sonar_harmonic_hz" not in game.save_state()["sonar_controls"]
    press(game, pygame.K_k)
    assert game.sonar_harmonic_hz == 12.0
    press(game, pygame.K_k)
    assert game.sonar_harmonic_hz == 24.0
    press(game, pygame.K_k)
    assert game.sonar_harmonic_hz is None


def _set_sonar_state(game, state):
    game.sonar.lofar_history = []
    game.sonar.lofar_times = []
    game.sonar.receiver.spectrum = np.zeros(110)
    game.sonar.receiver.peaks = []
    game.sonar.receiver.demon_spectrum = np.zeros(80)
    game.sonar.demon_analysis = None
    game.sonar.signature_candidates = []
    game.sonar.active_contacts = lambda: []
    game.selected_contact = None
    if state in ("populated", "selected", "stale"):
        game.sonar.lofar_history = [np.linspace(0, .8, 110)]
        game.sonar.lofar_times = [game.sim_t - (90 if state == "stale" else 1)]
        game.sonar.receiver.spectrum = np.linspace(0, .8, 110)
        game.sonar.receiver.peaks = [(12., .7), (24., .6), (36., .5)]
        game.sonar.receiver.demon_spectrum[11] = .8
        game.sonar.demon_analysis = dict(blade_rate_hz=12., confidence=.8)
        game.sonar.signature_candidates = [(NS(label=f"Reference {i}"), .8 - i * .1)
                                           for i in range(4)]
    if state == "selected":
        contact = Contact(4, 44, "passiv", "sub")
        contact.last_seen = game.sim_t
        game.sonar.active_contacts = lambda: [contact]
        game.selected_contact = contact
    if state == "low_evidence":
        game.sonar.receiver.demon_spectrum[:] = .01
        game.sonar.demon_analysis = dict(blade_rate_hz=12., confidence=.1)


@pytest.mark.parametrize("language", ["en", "de", "pseudo"])
@pytest.mark.parametrize("large", [False, True])
@pytest.mark.parametrize("page", [1, 2])
@pytest.mark.parametrize("state", ["empty", "populated", "selected", "stale",
                                   "low_evidence"])
def test_lofar_demon_language_size_state_matrix(language, large, page, state):
    game = Game(seed=1515, start_menu=False, audio_enabled=False)
    translator = Translator("en" if language == "pseudo" else language)
    if language == "pseudo":
        translator.catalog = pseudolocale(load_catalog("en"))
    game.translator = translator
    game.tr = translator.t
    game.preferences = replace(game.preferences, large_text=large)
    game.station = Station.SONAR
    game.sonar_page = page
    _set_sonar_state(game, state)
    with layout.capture_geometry() as geometry, layout.capture_text() as text:
        game.draw()
    assert text
    assert all(entry["bounds"].contains(entry["rect"]) for entry in text)
    details = next(entry["rect"] for entry in geometry
                   if entry["title"] == "sonar-details")
    detail_text = [entry for entry in text if entry["bounds"].x == details.x + 13]
    assert detail_text and all(details.contains(entry["rect"]) for entry in detail_text)
    rendered = " ".join(entry["text"] for entry in text)
    assert "sonar." not in rendered
    if page == 1 and state == "populated":
        assert "2f" not in rendered and "3f" not in rendered
        game.sonar_harmonic_hz = 12.0
        with layout.capture_text() as selected:
            game.draw()
        selected_text = " ".join(entry["text"] for entry in selected)
        assert "2f" in selected_text and "3f" in selected_text
    if page == 2 and state == "populated":
        assert rendered.count("Reference") <= 3


def test_sonar_render_has_no_fft_io_or_serialized_state_mutation(monkeypatch):
    game = Game(seed=1516, start_menu=False, audio_enabled=False)
    game.station = Station.SONAR
    game.sonar_page = 1
    _set_sonar_state(game, "populated")
    game.draw()  # Warm fonts and surfaces before I/O is prohibited.
    before = pickle.dumps(copy.deepcopy(game.save_state()))
    monkeypatch.setattr(builtins, "open", lambda *args, **kwargs:
                        pytest.fail("render attempted disk I/O"))
    monkeypatch.setattr(np.fft, "rfft", lambda *args, **kwargs:
                        pytest.fail("render attempted FFT"))
    monkeypatch.setattr(np.fft, "fft", lambda *args, **kwargs:
                        pytest.fail("render attempted FFT"))
    game.draw()
    assert pickle.dumps(game.save_state()) == before


def test_command_segment_uses_semantic_contrast(monkeypatch):
    pygame.font.init()
    colors = []
    face = layout.font(12)
    original = face.render
    monkeypatch.setattr(layout, "font", lambda *args, **kwargs: NS(
        size=face.size, get_linesize=face.get_linesize,
        render=lambda text, antialias, color: colors.append(color) or
        original(text, antialias, color)))
    layout.command_segment(pygame.Surface((500, 40)), (0, 0, 500, 30),
                           "F", "FILTER", "BAND", "20-120 Hz")
    assert colors == [layout.COMMAND_KEY_COLOR, layout.COMMAND_DESCRIPTION_COLOR,
                      config.COLOR_TEXT_DIM, config.COLOR_TEXT]
