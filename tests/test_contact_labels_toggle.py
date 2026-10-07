"""Alt+N shows and hides the contact names on every chart.

Dominik asked (2026-10-06) for the contact labels to be switchable: one key
at every station of both sides (and in the browser), plus a blue key chip on
each chart. Symbols and vectors stay; the choice lives in settings.json.
"""

from __future__ import annotations

import pygame
import pytest

from src.core import config, uboot_local
from src.core.game import Game
from src.core.preferences import Preferences, load_preferences, save_preferences
from src.core.station import Station
from src.ui import layout, map_view, pointer


def _game(language="en", side="frigate") -> Game:
    prefs = Preferences(language=language, fullscreen=False, audio=False, tooltips=False)
    game = Game(seed=1234, start_menu=False, show_splash=False, audio_enabled=False,
                preferences=prefs)
    game.local_side = side
    game.msg_until = 0.0
    return game


def _alt_n(game) -> None:
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_n,
                                         mod=pygame.KMOD_ALT, unicode="n"))


def _chart(game) -> pygame.Rect:
    with layout.bottom_panel_regions(game.bottom_panel_mode()):
        return pygame.Rect(config.MAP_RECT)


def _texts(game, area=None) -> list:
    with layout.capture_text() as traced:
        game.draw()
    return [item["text"] for item in traced
            if area is None or pygame.Rect(area).collidepoint(item["ink"].center)]


def test_the_choice_is_kept_in_the_settings(tmp_path):
    path = tmp_path / "settings.json"
    save_preferences(Preferences(contact_labels=False), path)
    assert load_preferences(path).contact_labels is False
    assert Preferences().contact_labels is True


@pytest.mark.parametrize("station", [Station.BRIDGE, Station.SONAR, Station.WEAPONS,
                                     Station.OPZ, Station.RADIO, Station.HELICOPTER,
                                     Station.ENGINE, Station.ELOKA, Station.DAMAGE])
def test_alt_n_switches_the_names_at_every_frigate_station(station):
    game = _game()
    game.station = station
    _alt_n(game)
    assert game.contact_labels_shown() is False
    assert not game.nations_open
    _alt_n(game)
    assert game.contact_labels_shown() is True


@pytest.mark.parametrize("role", ["uboot", "uboot_sonar", "uboot_weapons", "uboot_nav"])
def test_alt_n_switches_the_names_on_the_submarine(role):
    game = _game(side="uboot")
    assert game.start_new_game("s8_meerenge", "fixed", seed=61)
    uboot_local.set_local_station(game, role)
    _alt_n(game)
    assert game.contact_labels_shown() is False


def test_plain_n_still_opens_the_nations():
    game = _game()
    game.station = Station.BRIDGE
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_n, mod=0, unicode="n"))
    assert game.nations_open
    assert game.contact_labels_shown() is True


@pytest.fixture(scope="module")
def convoy():
    """The convoy of the bug report: ships on radar with AIS names."""
    game = _game()
    assert game.start_new_game("s7_geleitzug", "real_fixed", seed=2)
    game.surface_radar_on = True
    for _ in range(600):
        game.update(.1)
    return game


@pytest.mark.parametrize("language", ["en", "de"])
@pytest.mark.parametrize("station", [Station.BRIDGE, Station.WEAPONS, Station.OPZ])
def test_hidden_names_leave_symbols_but_no_name(convoy, language, station):
    game = convoy
    game._set_preference("language", language)
    game._set_preference("contact_labels", True)
    game.station, game.station_page, game.msg_until = station, 0, 0.0
    game.map_view.scale = 117.0
    names = {str(track["label"]) for track in game.chart_tracks()
             if str(track["label"]).startswith("AIS-")}
    assert names
    game.draw()
    area = (game.opz_map_view.rect if station is Station.OPZ
            else _chart(game))
    shown = _texts(game, area)
    assert any(name in text for text in shown for name in names)
    game.toggle_contact_labels()
    hidden = _texts(game, area)
    assert not [text for text in hidden if any(name in text for name in names)]
    assert ("Namen aus" if language == "de" else "Names off") in hidden
    game._set_preference("contact_labels", True)


def test_the_chip_is_a_click_on_alt_n():
    game = _game()
    game.station = Station.BRIDGE
    game.draw()
    chip = map_view.contact_label_chip_rect(_chart(game))
    found = [target for target in pointer.targets("station")
             if target.key == pygame.K_n and target.mod & pygame.KMOD_ALT]
    assert found and found[-1].rect == chip
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=chip.center))
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=chip.center))
    assert game.contact_labels_shown() is False


def test_hidden_names_on_the_submarine_chart():
    game = _game("de", side="uboot")
    assert game.start_new_game("s8_meerenge", "fixed", seed=61)
    for _ in range(600):
        game.update(.1)
    game.msg_until = 0.0
    uboot_local.set_local_station(game, "uboot")
    names = [text for text in _texts(game) if text.startswith("K0")]
    assert names
    game.toggle_contact_labels()
    hidden = _texts(game)
    assert not [text for text in hidden if text.startswith("K0")]
    assert "Namen aus" in hidden
