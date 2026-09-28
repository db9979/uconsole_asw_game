"""Autosave: periodic and on-quit writes, Continue in the main menu, discard."""

import json
import os

import pygame

from src.core import config
from src.core.game import Game
from src.core.game_autosave import CONTINUE_ENTRY, autosave_path
from src.core.game_bugreport import MAIN_MENU_ENTRIES
from src.core.game_save import _same_save_value


def _key(game, key):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode=""))


def _mission(seed=11):
    return Game(seed=seed, start_menu=False, show_splash=False, audio_enabled=False)


def test_tick_writes_after_the_interval_only():
    game = _mission()
    game.autosave_tick(config.AUTOSAVE_INTERVAL_S - 1.0)
    game.wait_for_autosave()
    assert not os.path.exists(autosave_path())
    game.autosave_tick(1.0)
    game.wait_for_autosave()
    with open(autosave_path(), encoding="utf-8") as stream:
        data = json.load(stream)
    assert data["save_schema"] == "u-jagd-save-v28"
    assert game.autosave_available
    # Nothing is left behind from the staged write.
    assert os.listdir(os.path.dirname(autosave_path())) == ["autosave.json"]


def test_menu_states_never_autosave():
    game = Game(seed=11, start_menu=True, show_splash=False, audio_enabled=False)
    game.autosave_tick(config.AUTOSAVE_INTERVAL_S * 2)
    game.wait_for_autosave()
    assert not os.path.exists(autosave_path())
    assert game.main_menu_entries() == MAIN_MENU_ENTRIES


def test_continue_resumes_the_autosaved_mission():
    source = _mission(seed=21)
    for _ in range(50):
        source.update(0.1)
    assert source.autosave()
    source.wait_for_autosave()
    expected = source.save_state()

    game = Game(seed=5, start_menu=True, show_splash=False, audio_enabled=False)
    entries = game.main_menu_entries()
    assert entries[0] == CONTINUE_ENTRY and entries[1:] == MAIN_MENU_ENTRIES
    assert game.main_menu_sel == 0
    game.draw_menu()
    _key(game, pygame.K_RETURN)
    assert not game.main_menu and not game.in_menu
    assert game.seed == 21
    resumed = game.save_state()
    # Entity ID high-water marks are global; the menu's own world raised them.
    resumed.pop("next_entity_ids"), expected.pop("next_entity_ids")
    assert _same_save_value(resumed, expected)


def test_invalid_autosave_keeps_the_menu():
    os.makedirs(os.path.dirname(autosave_path()), exist_ok=True)
    with open(autosave_path(), "w", encoding="utf-8") as stream:
        stream.write('{"save_schema": "u-jagd-save-v26"}')
    game = Game(seed=5, start_menu=True, show_splash=False, audio_enabled=False)
    _key(game, pygame.K_RETURN)
    assert game.main_menu
    assert os.path.exists(autosave_path())


def test_finished_mission_and_new_mission_discard_the_autosave():
    game = _mission()
    assert game.autosave()
    game.wait_for_autosave()
    game.game_over = True
    game.autosave_tick(0.1)
    assert not os.path.exists(autosave_path()) and not game.autosave_available

    game = _mission()
    assert game.autosave()
    game.wait_for_autosave()
    game.reset(game.seed)
    assert not os.path.exists(autosave_path())


def test_leaving_to_the_main_menu_keeps_the_mission():
    game = _mission()
    game._return_to_main_menu()
    assert os.path.exists(autosave_path())
    assert game.main_menu_entries()[game.main_menu_sel] == CONTINUE_ENTRY


def test_normal_quit_writes_the_autosave():
    game = _mission()
    game.auto_quit = 3
    game.run()
    assert os.path.exists(autosave_path())


def test_submenu_escape_returns_to_its_entry_with_continue():
    game = _mission()
    game._return_to_main_menu()
    game.main_menu_sel = game.main_menu_index("training")
    _key(game, pygame.K_RETURN)
    assert game.menu_screen == "training"
    _key(game, pygame.K_ESCAPE)
    assert game.main_menu_entries()[game.main_menu_sel] == "training"
