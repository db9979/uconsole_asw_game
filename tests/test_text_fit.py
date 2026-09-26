"""No operational text is lost to an ellipsis on the 1280x720 canvas.

Layout helpers first try the full catalog wording, then the operator
abbreviation ``<key>.short``; the event feed wraps, the ticker scrolls.
"""

import re
from dataclasses import replace

import pygame
import pytest

from src.core import config
from src.core.commands import STATION_PAGES
from src.core.game import Game
from src.core.i18n import (Translator, load_catalog, localize, message,
                           short_candidates, translation_scope)
from src.core.preferences import load_preferences, save_preferences
from src.core.station import Station
from src.ui import layout

_PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


@pytest.mark.parametrize("language", ["en", "de"])
def test_every_abbreviation_shortens_an_existing_entry(language):
    catalog = load_catalog(language)
    for key, value in catalog.items():
        if not key.endswith(".short"):
            continue
        base = key[:-len(".short")]
        assert base in catalog, key
        assert set(_PLACEHOLDER.findall(value)) <= set(
            _PLACEHOLDER.findall(catalog[base])), key
        assert "..." not in value and "…" not in value, key


def test_fit_line_prefers_the_catalog_abbreviation_over_an_ellipsis():
    pygame.font.init()
    translator = Translator("en")
    face = layout.font(16)
    long = message("sonar.status.array", array=message("enum.array.bow"),
                   state=message("state.stowed"), payout="0", ready="", pause="")
    with translation_scope(translator.t):
        full = localize(long)
        width = face.size(full)[0] - 20
        with layout.capture_truncations() as cut:
            shown = layout.fit_line(long, face, width)
        assert not cut and "..." not in shown
        # Parameters shorten first; the template keeps its full wording.
        assert shown.startswith("ARRAY HMS |") and "Hull" not in shown
        assert short_candidates("ui.not_ready") == ["ui.not_ready.short"]


def _warm_game(language, large, mode):
    game = Game(seed=1515, start_menu=False, audio_enabled=False,
                language=language)
    game.preferences = replace(game.preferences, large_text=large,
                               bottom_panel=mode)
    for _ in range(240):
        game.update(1.0)
    contacts = game.sonar.active_contacts()
    if contacts:
        game.selected_contact = game.target = contacts[0]
    return game


@pytest.mark.parametrize("language,large,mode", [
    ("en", False, "ticker"), ("de", False, "ticker"),
    ("en", True, "ticker"), ("de", True, "ticker"), ("de", False, "docked")])
def test_no_station_page_ellipsizes_operational_text(language, large, mode):
    game = _warm_game(language, large, mode)
    lost = []
    for station in (item for item in Station if item is not Station.RADAR):
        for page in range(len(STATION_PAGES[station])):
            game.station, game.station_page = station, page
            if station is Station.SONAR:
                game.sonar_page = page
            with layout.capture_truncations() as cut:
                game.draw()
            lost += [(station.name, page, item["text"]) for item in cut]
    assert not lost


def test_ticker_frees_station_space_and_keeps_hit_tests_aligned():
    game = Game(seed=77, start_menu=False, audio_enabled=False)
    assert game.bottom_panel_mode() == "ticker"
    with layout.bottom_panel_regions("ticker"):
        ticker_full = pygame.Rect(config.FULL_STATION_RECT)
        ticker_map = pygame.Rect(config.MAP_RECT)
    assert ticker_full.bottom == config.SCREEN_H - layout.TICKER_H
    assert ticker_map.h == ticker_full.h
    # The docked module defaults are untouched outside a game call.
    assert pygame.Rect(config.FULL_STATION_RECT).bottom == config.MAIN_BOTTOM == 540
    with layout.capture_geometry() as geometry:
        game.draw()
    assert all(item["rect"].bottom <= ticker_full.bottom for item in geometry
               if item["kind"] in ("box", "panel", "region"))


def test_f11_overlay_is_display_only_and_scrolls(monkeypatch):
    game = Game(seed=78, start_menu=False, audio_enabled=False)
    for index in range(40):
        game.feed.add("12:00", "sonar", message("runtime.echo.unassociated",
                                               bearing=f"{index:05.1f}", range="1.0"))
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F11))
    assert game.feed_overlay_open
    game.draw()
    # Station controls stay live underneath: selecting another station works.
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_2))
    assert game.station is Station.SONAR and game.feed_overlay_open
    monkeypatch.setattr(game, "_window_to_canvas", lambda pos: (100, 600))
    game.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=2, pos=(100, 600)))
    assert game.feed_overlay_scroll == 6
    with layout.capture_truncations() as cut:
        game.draw()
    assert not cut
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F11))
    assert not game.feed_overlay_open


def test_bottom_panel_preference_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    preferences = load_preferences(path)
    assert preferences.bottom_panel == "ticker"
    save_preferences(replace(preferences, bottom_panel="docked"), path)
    assert load_preferences(path).bottom_panel == "docked"
    path.write_text('{"bottom_panel": "sidebar"}', encoding="utf-8")
    assert load_preferences(path).bottom_panel == "ticker"
