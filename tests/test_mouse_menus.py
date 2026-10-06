"""Options, live traffic, splash, lobby and Remote Crew rows by mouse alone."""

import pygame
import pytest

from src.core.game import Game
from src.ui import layout, pointer


@pytest.fixture
def game(monkeypatch):
    monkeypatch.setattr(pygame.display, "get_window_size", lambda: (1280, 720))
    instance = Game(seed=31, start_menu=False, audio_enabled=False, language="de")
    yield instance
    instance.commander.stop()
    instance.audio.shutdown()
    layout.configure_for(large_text=False)


def click(game, pos):
    game.draw()
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos))


def option_row(game, name):
    rows = game._option_rows()
    return game._option_row_hit_rects(rows)[rows.index(name)]


def test_a_click_on_an_options_row_changes_it(game):
    game._open_administration("options")
    before = game.tooltips_enabled
    click(game, option_row(game, "tooltips").midleft)
    assert game.tooltips_enabled is not before
    assert game.options_open


def test_options_arrows_step_a_value_both_ways(game):
    game._open_administration("options")
    row = option_row(game, "level")
    left, right = game._option_arrow_rects(row)
    start = game._preferred_level()
    click(game, right.center)
    assert game._preferred_level() != start
    click(game, left.center)
    assert game._preferred_level() == start


def test_options_page_and_hint_chips_work_by_click(game):
    game._open_administration("options")
    game.draw()
    page_down = next(t for t in pointer.targets("overlay") if t.key == pygame.K_PAGEDOWN)
    click(game, page_down.rect.center)
    assert game.options_page == 1
    escape = [t for t in pointer.targets("overlay") if t.key == pygame.K_ESCAPE]
    assert len(escape) >= 2          # the close cross and the hint's Esc chip
    click(game, escape[-1].rect.center)
    assert not game.options_open


def test_live_traffic_rows_toggle_and_open_fields_by_click(game, monkeypatch):
    game._open_administration("live_traffic")
    monkeypatch.setattr(game, "_live_traffic_can_enable", lambda name: True)
    rows = game._live_traffic_row_rects()
    before = game.preferences.live_ais_enabled
    click(game, rows[0].center)
    assert game.preferences.live_ais_enabled is not before
    click(game, rows[2].center)
    assert game.live_traffic_field_name == "aisstream_api_key"
    game.draw()
    escape = next(t for t in pointer.targets("overlay") if t.key == pygame.K_ESCAPE
                  and t.rect.y > 600)
    click(game, escape.rect.center)
    assert game.live_traffic_field is None and game.live_traffic_open


def test_a_click_closes_the_splash(monkeypatch):
    monkeypatch.setattr(pygame.display, "get_window_size", lambda: (1280, 720))
    game = Game(seed=31, start_menu=True, show_splash=True, audio_enabled=False)
    try:
        game._t = game.splash_started_at + 1.0
        game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                             pos=(640, 360)))
        assert not game.splash_active
    finally:
        game.commander.stop()
        game.audio.shutdown()


def test_remote_crew_port_steps_down_from_the_rows_left_third(game):
    console = game.commander
    game._open_administration("commander")
    console.advanced = True
    index = console.rows().index("port")
    rect = console.row_rects()[index]
    console.selection = index
    start = console.port
    console.handle_click(game, (rect.x + 5, rect.centery))
    assert console.port == start - 1
    console.handle_click(game, (rect.right - 5, rect.centery))
    assert console.port == start
