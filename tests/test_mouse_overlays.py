"""Save/load, quit, F1, F4 and the plot toolbar by mouse alone."""

import dataclasses

import pygame
import pytest

from src.core.game import Game
from src.core.game_shared import HELP_MANUAL_PAGE
from src.ui import layout, plot_view, pointer


@pytest.fixture
def game(monkeypatch):
    monkeypatch.setattr(pygame.display, "get_window_size", lambda: (1280, 720))
    instance = Game(seed=31, start_menu=False, audio_enabled=False, language="de")
    yield instance
    instance.commander.stop()
    instance.audio.shutdown()
    layout.configure_for(large_text=False)


def press(game, key, mod=0, below=0):
    """Click the drawn chip of ``key`` (the lowest one below ``below``)."""
    game.draw()
    targets = [t for t in pointer.targets() if t.key == key and t.mod == mod
               and t.rect.y >= below]
    assert targets, f"no chip for {pygame.key.name(key)}"
    target = max(targets, key=lambda t: t.rect.y)
    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        game.handle_event(pygame.event.Event(kind, button=1, pos=target.rect.center))


def test_save_question_answers_yes_and_no_by_chip(game, monkeypatch):
    game._open_administration("save")
    game.save_slot = 2
    game.save_confirm = True
    press(game, pygame.K_ESCAPE, below=400)
    assert not game.save_confirm or game.save_ui is None
    game._open_administration("save")
    game.save_slot = 2
    game.save_confirm = True
    saved = []
    monkeypatch.setattr(game, "begin_save_to_slot", lambda slot, *a, **kw: saved.append(slot))
    press(game, pygame.K_RETURN, below=400)
    assert saved == [2]


def test_quit_hint_chips_move_and_confirm(game):
    game._open_administration("quit")
    press(game, pygame.K_DOWN, below=400)
    assert game.quit_selection == 1
    press(game, pygame.K_ESCAPE, below=400)
    assert not game.quit_confirm


def test_manual_chapter_buttons_and_hint_chips(game):
    game._open_administration("help")
    game.help_page = HELP_MANUAL_PAGE
    chapter = game.help_manual_chapter
    press(game, pygame.K_RIGHTBRACKET)
    assert game.help_manual_chapter == chapter + 1
    press(game, pygame.K_LEFTBRACKET)
    assert game.help_manual_chapter == chapter
    press(game, pygame.K_DOWN, below=600)
    assert game.help_scroll == 1
    press(game, pygame.K_ESCAPE, below=600)
    assert not game.help_open


def test_simlog_footer_chips(game):
    game.preferences = dataclasses.replace(game.preferences, simlog=True)
    game._open_simlog_view()
    press(game, pygame.K_m, below=660)
    assert game.simlog_view_map
    press(game, pygame.K_f, below=660)
    press(game, pygame.K_ESCAPE, below=660)
    assert not game.simlog_view_open


def test_plot_toolbar_picks_tools_and_ends(game):
    game.toggle_plot_mode()
    assert game.plot_mode
    press(game, pygame.K_r)
    assert game.plot_tool == "ruler"
    count = len(game.plot.objects)
    press(game, pygame.K_RETURN, below=500)        # Enter plots the first point
    press(game, pygame.K_ESCAPE, below=500)        # Esc drops the half-made ruler
    assert len(game.plot.objects) == count
    game.draw()
    bar = next(t.rect for t in pointer.targets() if t.blocker and t.rect.h > 40)
    gap = (bar.right - 2, bar.centery)
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=gap))
    assert len(game.plot.objects) == count         # a click on the bar plots nothing
    press(game, pygame.K_ESCAPE, below=500)
    assert not game.plot_mode


def test_plot_toolbar_sits_at_the_chart_foot():
    chart = pygame.Rect(0, 36, 640, 662)
    bar = plot_view.toolbar_rect(chart)
    assert bar.bottom == chart.bottom - plot_view.TOOLBAR_BOTTOM_GAP
    assert chart.contains(bar)
