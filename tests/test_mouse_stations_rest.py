"""Package 4 of the mouse plan: the rest of the stations by click."""

import pygame
import pytest

from src.core import config
from src.core.game import Game
from src.core.station import Station
from src.ui import layout, pointer
from src.ui.sonar_hit import _demon_plot, _waterfall_plot, sonar_geometry


@pytest.fixture
def game(monkeypatch):
    monkeypatch.setattr(pygame.display, "get_window_size", lambda: (1280, 720))
    instance = Game(seed=31, start_menu=False, audio_enabled=False, language="de")
    instance.station = Station.SONAR
    yield instance
    instance.commander.stop()
    instance.audio.shutdown()
    layout.configure_for(large_text=False)


def geometry(game):
    """The sonar's geometry as the click sees it (full station rect)."""
    game.draw()
    previous = config.STATION_RECT
    config.STATION_RECT = config.FULL_STATION_RECT
    try:
        return sonar_geometry(game)
    finally:
        config.STATION_RECT = previous


def click(game, pos):
    game.draw()
    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        game.handle_event(pygame.event.Event(kind, button=1, pos=pos))


def test_a_click_in_lofar_and_demon_sets_the_cursor(game):
    game.sonar_page = 1
    plot = _waterfall_plot(geometry(game)["main"], 1)
    click(game, (plot.x + plot.w // 2, plot.centery))
    assert abs(game.sonar_tools.lofar_cursor_hz - config.LOFAR_FMAX_HZ / 2) < 5
    game.sonar_page = 2
    plot = _demon_plot(geometry(game)["main"])
    click(game, (plot.x + plot.w // 4, plot.centery))
    assert game.sonar_tools.demon_cursor_hz != 10.0


def test_gain_chip_halves_lower_and_raise(game):
    game.sonar_page = 0
    game.draw()
    lower = next(t.rect for t in pointer.targets("station") if t.key == pygame.K_i)
    raise_ = next(t.rect for t in pointer.targets("station") if t.key == pygame.K_o)
    assert lower.right <= raise_.x                 # left half lowers, right half raises
    click(game, raise_.center)
    assert game.sonar.gain_db == 3.0
    click(game, lower.center)
    click(game, lower.center)
    assert game.sonar.gain_db == -3.0


def test_a_click_on_a_dip_line_selects_its_contact(game):
    from src.sonar.contact import Contact
    contacts = []
    for number, bearing in ((7, 40.0), (8, 200.0)):
        current = Contact(number, 7654300 + number, "passiv", "sub")
        current.update_passive(bearing, .8, .8, "label", game.sim_t)
        current.update_dip_passive(bearing, game.sim_t, 20.0, 30.0, 1.5)
        game.sonar.contacts[current.target_id] = current
        contacts.append(current)
    game.station = Station.HELICOPTER
    game.station_page = 2
    game.selected_contact = contacts[0]
    game.draw()
    rows = [t.rect for t in pointer.targets("station")
            if t.action is not None and t.key is None and t.rect.x > 700
            and t.rect.y > 250 and t.rect.h <= 30]
    assert len(rows) >= 2
    click(game, rows[1].center)
    assert game.selected_contact is contacts[1]
    click(game, rows[0].center)
    assert game.selected_contact is contacts[0]
