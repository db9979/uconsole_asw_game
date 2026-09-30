"""First launch: the one-time "What do you want to play?" welcome page."""

import json
from dataclasses import replace

import pygame
import pytest

from src.core import config, training
from src.core.game import Game
from src.core.game_bugreport import MAIN_MENU_ENTRIES
from src.core.game_welcome import WELCOME_CHOICES, WELCOME_SCREEN
from src.core.i18n import Translator, pseudolocale
from src.core import preferences as preferences_module
from src.core.preferences import load_preferences, save_preferences, Preferences
from src.ui import layout


def settings_path():
    # The autouse fixture patches the module attribute per test.
    return preferences_module.default_preferences_path()


def key(game, code):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=code))


def first_launch(show_splash=False):
    assert not settings_path().exists()
    return Game(seed=19, start_menu=True, show_splash=show_splash,
                preferences=load_preferences(), audio_enabled=False,
                fullscreen=False, window_size=(1280, 720))


def test_first_launch_without_settings_shows_welcome_after_splash():
    game = first_launch(show_splash=True)
    assert game.splash_active
    game._t = game.splash_started_at + 1.0
    key(game, pygame.K_SPACE)
    assert not game.splash_active
    assert game.welcome_active and not game.main_menu
    assert game.menu_screen == WELCOME_SCREEN
    # Onboarding is only stored once the player leaves the page.
    assert not settings_path().exists()


def test_existing_settings_without_the_field_skip_welcome():
    path = settings_path()
    path.write_text(json.dumps({"language": "en", "audio": False}), encoding="utf-8")
    game = Game(seed=19, start_menu=True, preferences=load_preferences(),
                audio_enabled=False)
    assert game.main_menu and not game.welcome_active


def test_games_without_loaded_preferences_and_web_host_skip_welcome():
    assert not Game(seed=19, start_menu=True).welcome_active
    game = Game(seed=19, start_menu=True, web_mode=True,
                preferences=Preferences(onboarded=False))
    assert not game.welcome_active and game.main_menu


@pytest.mark.parametrize("choice_key, lesson", [
    (pygame.K_1, training.FRIGATE_LESSONS[0]),
    (pygame.K_2, training.BOAT_LESSONS[0]),
])
def test_frigate_and_submarine_open_training_with_the_lesson_selected(choice_key, lesson):
    game = first_launch()
    key(game, choice_key)
    assert not game.main_menu and game.menu_screen == "training"
    assert training.LESSONS[game.menu_sel] == lesson
    assert game.local_side == training.side_of(lesson)
    assert load_preferences().onboarded is True
    assert game.preferences.onboarded is True
    # Esc from the training list lands on the Training entry of the main menu.
    key(game, pygame.K_ESCAPE)
    assert game.main_menu
    assert MAIN_MENU_ENTRIES[game.main_menu_sel] == "training"


def test_submarine_choice_is_lesson_five():
    assert training.LESSONS.index(training.BOAT_LESSONS[0]) == 4


def test_arrow_keys_and_enter_choose_remote_crew(monkeypatch):
    game = first_launch()
    started = []
    monkeypatch.setattr(game.commander, "autostart", lambda solo=False: started.append(solo))
    key(game, pygame.K_DOWN)
    key(game, pygame.K_DOWN)
    assert WELCOME_CHOICES[game.welcome_sel] == "remote_crew"
    key(game, pygame.K_RETURN)
    # The multiplayer lobby opens and starts Remote Crew in crew mode.
    assert game.lobby_active and started == [False]
    assert not game.main_menu and not game.welcome_active
    assert load_preferences().onboarded is True
    # Leaving the lobby shows the main menu on its entry.
    key(game, pygame.K_ESCAPE)
    assert game.main_menu and MAIN_MENU_ENTRIES[game.main_menu_sel] == "multiplayer"


@pytest.mark.parametrize("skip_key", [pygame.K_ESCAPE, pygame.K_4])
def test_escape_or_main_menu_choice_skips_and_persists(skip_key):
    game = first_launch()
    key(game, skip_key)
    assert game.main_menu and not game.welcome_active
    assert MAIN_MENU_ENTRIES[game.main_menu_sel] == "new"
    assert load_preferences().onboarded is True
    # The next launch goes straight to the main menu.
    assert Game(seed=19, start_menu=True, preferences=load_preferences(),
                audio_enabled=False).main_menu


def test_closing_the_window_on_welcome_marks_onboarding_done():
    game = first_launch()
    game.handle_event(pygame.event.Event(pygame.QUIT))
    assert game.quit_confirm
    assert load_preferences().onboarded is True


def test_welcome_does_not_advance_the_simulation():
    game = first_launch()
    before = game.sim_t
    game.update(1.0)
    assert game.sim_t == before


def test_welcome_draws_at_1280x720_in_en_de_pseudo_and_large_text():
    game = first_launch()
    save_preferences(game.preferences)
    for translator in (Translator("en"), Translator("de"),
                       Translator("en", catalog=pseudolocale())):
        game.translator = translator
        game.tr = translator.t
        for large in (False, True):
            game.preferences = replace(game.preferences, large_text=large)
            game._apply_text_size()
            for index in range(len(WELCOME_CHOICES)):
                game.welcome_sel = index
                with layout.capture_text() as text:
                    game.draw()
                assert game.screen.get_size() == (config.SCREEN_W, config.SCREEN_H)
                welcome = [item for item in text
                           if 130 <= item["bounds"].y < 600]
                # Title, four labels and notes, hint: all inside their bounds.
                assert len(welcome) >= 10
                for item in welcome:
                    assert item["bounds"].contains(item["rect"]), item
    assert game.welcome_active


def test_world_and_seed_keys_still_work_on_welcome():
    game = first_launch()
    mode = game.world_mode
    key(game, pygame.K_w)
    assert game.world_mode != mode and game.welcome_active
    assert not settings_path().exists()
