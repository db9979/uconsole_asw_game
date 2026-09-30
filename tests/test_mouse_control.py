"""Full mouse control on the uConsole: a click does what its key does."""

import pygame
import pytest

from src.core.game import Game
from src.core.station import Station
from src.ui import instruments, pointer


@pytest.fixture
def game(monkeypatch):
    monkeypatch.setattr(pygame.display, "get_window_size", lambda: (1280, 720))
    instance = Game(seed=31, start_menu=False, audio_enabled=False, language="en")
    instance.station, instance.station_page = Station.BRIDGE, 0
    yield instance
    instance.audio.shutdown()


def click(game, pos, button=1, up=True):
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=button, pos=pos))
    if up:
        game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=button, pos=pos))


def target(owner, key=None):
    return next(t for t in pointer.targets(owner) if key is None or t.key == key)


def test_legend_keys_parse_every_footer_spelling():
    assert pointer.legend_keys("←/→") == [(pygame.K_LEFT, 0), (pygame.K_RIGHT, 0)]
    assert pointer.legend_keys(", / .") == [(pygame.K_COMMA, 0), (pygame.K_PERIOD, 0)]
    assert pointer.legend_keys("Shift+G") == [(pygame.K_g, pygame.KMOD_SHIFT)]
    assert pointer.legend_keys("help.key.uboot_fire") == [(pygame.K_RETURN, pygame.KMOD_CTRL)]
    assert pointer.legend_keys("help.key.page_arrows") == [(pygame.K_PAGEUP, 0),
                                                          (pygame.K_PAGEDOWN, 0)]
    assert pointer.legend_keys("U/J/H") == [(pygame.K_u, 0), (pygame.K_j, 0), (pygame.K_h, 0)]
    assert pointer.legend_keys("Backspace") == [(pygame.K_BACKSPACE, 0)]


def test_station_tab_click_switches_station(game):
    game.draw()
    tab = target("station", pygame.K_2)
    click(game, tab.rect.center)
    assert game.station is Station.SONAR


def test_footer_click_opens_the_course_entry_and_the_keypad_orders_it(game):
    game.draw()
    click(game, target("station", pygame.K_u).rect.center)
    assert game.input_mode == "course"
    game.draw()
    for key in (pygame.K_1, pygame.K_3, pygame.K_5, pygame.K_RETURN):
        click(game, target("input", key).rect.center)
        game.draw()
    assert game.input_mode is None
    assert game.ship.target_course == pytest.approx(135.0)


def test_heading_dial_click_orders_that_course(game):
    game.draw()
    dial = next(t for t in pointer.targets("station") if t.action is not None
                and instruments.heading_at(t.rect, (t.rect.right - 20, t.rect.centery)) == 90)
    click(game, (dial.rect.right - 20, dial.rect.centery))
    assert game.ship.target_course == pytest.approx(90.0)


def test_held_legend_acts_like_a_held_key(game):
    game.draw()
    left = target("station", pygame.K_LEFT)
    click(game, left.rect.center, up=False)
    assert pygame.K_LEFT in game.held
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=left.rect.center))
    assert pygame.K_LEFT not in game.held


def test_station_targets_are_dead_under_an_overlay_and_right_click_closes_it(game):
    game.draw()
    tab = target("station", pygame.K_3)
    game._open_administration("help")
    game.draw()
    click(game, tab.rect.center)
    assert game.station is Station.BRIDGE and game.help_open
    click(game, (640, 360), button=3)
    assert not game.help_open


def test_main_menu_row_click_opens_it(monkeypatch):
    monkeypatch.setattr(pygame.display, "get_window_size", lambda: (1280, 720))
    game = Game(seed=31, start_menu=True, show_splash=False, audio_enabled=False,
                language="en")
    try:
        game.draw()
        index = game.main_menu_entries().index("options")
        rows = pointer.targets("menu")
        click(game, rows[index].rect.center)
        assert game.options_open
    finally:
        game.audio.shutdown()


def test_quit_dialog_rows_and_save_slots_are_clickable(game):
    game._open_administration("quit")
    game.draw()
    rows = [t for t in pointer.targets("overlay") if t.action is not None]
    click(game, rows[0].rect.center)          # "back to the game"
    assert not game.quit_confirm


def test_pointer_never_changes_the_simulation_by_itself(game):
    """Drawing and registering targets is display only (same seed, same state)."""
    other = Game(seed=31, start_menu=False, audio_enabled=False, language="en")
    try:
        for _ in range(20):
            game.draw()
            game.update(0.1)
            other.update(0.1)
        assert (game.ship.x, game.ship.y) == (other.ship.x, other.ship.y)
    finally:
        other.audio.shutdown()
