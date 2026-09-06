import pygame

from src.core.game import Game
from src.core.version import APP_VERSION, SPLASH_TEXT


def test_release_version_and_exact_splash_text():
    assert APP_VERSION == "0.1.0"
    assert SPLASH_TEXT == (
        "Anti Sub Marine Warfare on uConsole by Dominik Bornhäußer Version 0.1.0"
    )


def test_splash_draws_without_advancing_simulation_and_can_be_skipped():
    game = Game(seed=19, start_menu=True, show_splash=True)
    before = game.sim_t
    game.update(1.0)
    game.draw()
    assert game.sim_t == before
    assert game.splash_active is True

    game._t = game.splash_started_at + .5
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
    assert game.splash_active is False
    assert game.in_menu is True


def test_menu_can_select_fixed_or_procedural_world_and_reroll_seed():
    game = Game(seed=22, start_menu=True)
    assert game.world_mode == "procedural"
    game._handle_menu_key(pygame.K_w)
    assert game.world_mode == "fixed"
    old_seed = game.seed
    game._handle_menu_key(pygame.K_r)
    assert game.seed != old_seed
