"""OPZ display settings: the Display page, layer chips, bearing scale,
track trails and the selected track's CPA (display only)."""

import math

import pygame
import pytest

from src.core import config, opz_display
from src.core.game import Game
from src.core.preferences import Preferences, load_preferences, save_preferences
from src.core.station import Station
from src.ui import layout, pointer
from src.ui.stations import opz, opz_display_view


def press(game, key, mod=0):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod))


def _game(language="en"):
    game = Game(seed=1234, start_menu=False, show_splash=False, audio_enabled=False,
                preferences=Preferences(language=language, fullscreen=False, audio=False,
                                        tooltips=False))
    game.msg_until = 0.0
    game.station = Station.OPZ
    return game


def _convoy(language="en"):
    game = _game(language)
    game.reset(1234, "s11_geleitschutz")
    game.station = Station.OPZ
    for _ in range(1200):
        game.update(.1)
    game.msg_until = 0.0
    return game


def _texts(game):
    with layout.capture_text() as traced:
        game.draw()
    return traced


def test_settings_normalize_step_and_store_only_changes():
    assert opz_display.normalize(()) == opz_display.DEFAULTS
    hostile = [("trails", "99"), ("labels", "brief"), ["bogus", "on"], "x", ("cpa",)]
    values = opz_display.normalize(hostile)
    assert values["trails"] == opz_display.DEFAULTS["trails"]
    assert values["labels"] == "brief"
    assert opz_display.to_pairs(values) == (("labels", "brief"),)
    stepped = opz_display.step(values, "vectors", 1)
    assert stepped["vectors"] == "6"
    assert opz_display.step(stepped, "vectors", -2)["vectors"] == "30"
    assert opz_display.step(values, "compass", 1)["compass"] == "off"
    assert opz_display.trail_minutes(opz_display.step(opz_display.DEFAULTS, "trails", -1)) == 3.0


def test_cpa_from_reported_motion():
    # A track 10 NM north running south at 10 kn past a stopped ship, 1 NM east.
    distance, minutes, own, track = opz_display.cpa(0.0, 0.0, 0.0, 0.0,
                                                    1.0, -10.0, 180.0, 10.0)
    assert distance == pytest.approx(1.0)
    assert minutes == pytest.approx(60.0)
    assert own == pytest.approx((0.0, 0.0))
    assert track == pytest.approx((1.0, 0.0), abs=1e-9)
    # Opening, too slow, no motion or too far ahead: no CPA.
    assert opz_display.cpa(0, 0, 0, 0, 0, -10, 0, 10) is None
    assert opz_display.cpa(0, 0, 0, 0, 0, -10, 180, .1) is None
    assert opz_display.cpa(0, 0, 0, 0, 0, -10, None, 10) is None
    assert opz_display.cpa(0, 0, 0, 0, 0, -100, 180, 10) is None
    assert opz_display.cpa(0, 0, 0, 0, 0, -10, 180, math.nan) is None


def test_preferences_keep_the_display_and_drop_hostile_values(tmp_path):
    path = tmp_path / "settings.json"
    save_preferences(Preferences(opz_display=(("trails", "12"), ("rings", "off"))), path)
    assert load_preferences(path).opz_display == (("trails", "12"), ("rings", "off"))
    path.write_text('{"opz_display": [["trails", "7"], ["labels", "off"], "x", 5]}',
                    encoding="utf-8")
    assert load_preferences(path).opz_display == (("labels", "off"),)
    path.write_text('{"opz_display": "nonsense"}', encoding="utf-8")
    assert load_preferences(path).opz_display == ()


def test_display_page_keys_pick_change_and_reset():
    game = _game()
    game.station_page = 4
    press(game, pygame.K_DOWN)
    assert game.opz_display_sel == 1
    press(game, pygame.K_RIGHT)
    assert game.opz_display_settings()["vectors"] == "6"
    press(game, pygame.K_LEFT)
    press(game, pygame.K_LEFT)
    assert game.opz_display_settings()["vectors"] == "30"
    assert game.preferences.opz_display == (("vectors", "30"),)
    press(game, pygame.K_UP)
    press(game, pygame.K_UP)
    assert game.opz_display_sel == len(opz_display.KEYS) - 1
    press(game, pygame.K_BACKSPACE)
    assert game.preferences.opz_display == ()
    # The page keys belong to this page only: on the picture ↑/↓ pick tracks.
    game.station_page = 0
    press(game, pygame.K_RIGHT)
    assert game.preferences.opz_display == ()


def test_display_page_rows_and_chips_are_clickable():
    game = _game("de")
    game.station_page = 4
    pointer.reset()
    game.draw()
    actions = [t for t in pointer.targets("station") if t.action is not None]
    with layout.bottom_panel_regions(game.bottom_panel_mode()):
        regions = opz.opz_regions(config.OPZ_STATION_RECT)
    sidebar = regions["sidebar"]
    rows = [t for t in actions if sidebar.contains(t.rect)]
    assert len(rows) == len(opz_display.KEYS)
    rows[2].action(rows[2].rect.center)
    assert game.opz_display_sel == 2
    assert game.opz_display_settings()["labels"] == "brief"
    chart = regions["chart"]
    chips = [t for t in actions if t.rect.top > chart.bottom]
    assert len(chips) == len(opz_display.CHIP_KEYS)
    chips[3].action(chips[3].rect.center)
    assert game.opz_display_settings()["compass"] == "off"


@pytest.mark.parametrize("language", ["en", "de"])
def test_chips_fit_beside_the_range_legend(language):
    game = _game(language)
    game.preferences = Preferences(language=language, fullscreen=False, audio=False,
                                   opz_display=(("trails", "12"), ("vectors", "30"),
                                                ("labels", "brief")))
    game._open_administration("")
    traced = _texts(game)
    with layout.bottom_panel_regions(game.bottom_panel_mode()):
        chart = opz.opz_regions(config.OPZ_STATION_RECT)["chart"]
    footer = [item for item in traced if item["ink"].top > chart.bottom
              and item["ink"].bottom < config.SCREEN_H]
    chip_texts = [item for item in footer if any(
        word in item["text"] for word in ("12", "30", "CPA"))]
    assert chip_texts
    for a in footer:
        assert "…" not in a["text"] and "..." not in a["text"], a["text"]
        for b in footer:
            if a is not b:
                assert not a["ink"].colliderect(b["ink"]), (a["text"], b["text"])


def test_layers_switch_the_bearing_scale_labels_and_cpa():
    game = _convoy()
    game._configure_opz_map_view()
    game.opz_map_view.scale = 26.0
    game.opz_map_view.cx, game.opz_map_view.cy = game.ship.x, game.ship.y
    game._cycle_radar_range(-1)
    game._cycle_radar_range(-1)
    tracks = [t for t in game.opz_tracks() if opz_display_view.selected_cpa(game, t)]
    assert tracks, "the convoy should close on the frigate"
    game.opz_selected_track_id = tracks[0].track_id
    traced = _texts(game)
    texts = [item["text"] for item in traced]
    assert "030" in texts
    assert any(text.startswith("CPA ") for text in texts)
    labels = [t.label for t in game.opz_tracks()]
    chart = opz.opz_regions(config.OPZ_STATION_RECT)["chart"]
    assert any(item["text"] in labels for item in traced if chart.contains(item["ink"]))
    game.preferences = Preferences(language="en", fullscreen=False, audio=False,
                                   opz_display=(("compass", "off"), ("cpa", "off"),
                                                ("labels", "off"), ("rings", "off")))
    traced = _texts(game)
    texts = [item["text"] for item in traced]
    assert "030" not in texts
    assert not any(text.startswith("CPA ") for text in texts)
    # The track cards keep their labels; the chart itself drops them.
    chart_texts = [item["text"] for item in traced if chart.contains(item["ink"])]
    assert not any(label in chart_texts for label in labels)
    assert not any(text.endswith(" NM") and text[0].isdigit() for text in texts)


def test_trails_follow_the_opz_picture_and_stay_bounded():
    game = _convoy()
    side = game.chart_history.sides["frigate"]
    keys = {t.track_id for t in game.opz_tracks()}
    assert keys and keys <= set(side.opz)
    for rows in side.opz.values():
        assert len(rows) <= 24
        assert all(later[0] - earlier[0] >= 30.0 - 1e-6
                   for earlier, later in zip(rows, list(rows)[1:]))
    some = next(iter(keys))
    assert len(side.opz_positions(some, game.sim_t, 1.0)) <= 3


def test_display_settings_never_touch_the_simulation():
    plain, styled = _game(), _game()
    styled.preferences = Preferences(language="en", fullscreen=False, audio=False,
                                     opz_display=(("trails", "off"), ("chart", "off"),
                                                  ("afterglow", "off")))
    for game in (plain, styled):
        for step in range(300):
            game.update(.1)
            if step % 50 == 0:
                game.draw()
    assert (plain.ship.x, plain.ship.y, plain.sim_t) == (styled.ship.x, styled.ship.y, styled.sim_t)
    assert ([t.track_id for t in plain.opz_tracks()]
            == [t.track_id for t in styled.opz_tracks()])


def test_radar_switches_on_the_chart_press_r_and_shift_r():
    game = _game("de")
    pointer.reset()
    game.draw()
    with layout.bottom_panel_regions(game.bottom_panel_mode()):
        chart = opz.opz_regions(config.OPZ_STATION_RECT)["chart"]
    switches = [t for t in pointer.targets("station")
                if t.key == pygame.K_r and chart.contains(t.rect)]
    assert [t.mod for t in switches] == [0, pygame.KMOD_SHIFT]
    surface, air = game.surface_radar_on, game.air_radar_on
    for target in switches:
        press(game, target.key, target.mod)
    assert (game.surface_radar_on, game.air_radar_on) == (not surface, not air)
    texts = [item["text"] for item in _texts(game)]
    assert any("SEERADAR" in text for text in texts)
