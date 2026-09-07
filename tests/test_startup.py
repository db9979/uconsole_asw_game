import random

import pygame
import pytest

from src.core.game import Game
from src.core.version import APP_VERSION, SPLASH_TEXT
from src.world.real_coast import sector_for_seed


def test_release_version_and_exact_splash_text():
    assert APP_VERSION == "0.1.6"
    assert SPLASH_TEXT == (
        "Anti Sub Marine Warfare on uConsole by Dominik Bornhäußer Version 0.1.6"
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


def test_menu_can_select_fixed_or_procedural_world_and_reroll_seed(monkeypatch):
    game = Game(seed=22, start_menu=True)
    assert game.world_mode == "procedural"
    game._handle_menu_key(pygame.K_w)
    assert game.world_mode == "fixed"
    monkeypatch.setattr(random, "SystemRandom", lambda: type(
        "FixedRandom", (), {"randrange": lambda self, start, stop: 22})())
    old_seed = game.seed
    game._handle_menu_key(pygame.K_r)
    assert game.seed == old_seed + 1


@pytest.mark.parametrize("main_menu,screen", [
    (True, "scenario"),
    (False, "scenario"),
    (False, "level"),
    (False, "briefing"),
])
def test_world_and_seed_controls_work_on_every_advertised_menu_screen(
        monkeypatch, main_menu, screen):
    game = Game(seed=22, start_menu=True)
    game.main_menu = main_menu
    game.menu_screen = screen
    monkeypatch.setattr(random, "SystemRandom", lambda: type(
        "FixedRandom", (), {"randrange": lambda self, start, stop: 7})())

    game._handle_menu_key(pygame.K_w)
    game._handle_menu_key(pygame.K_r)

    assert game.world_mode == "fixed"
    assert game.seed == 7
    assert game.in_menu


def test_briefing_uses_the_latest_menu_seed_and_world_mode(monkeypatch):
    game = Game(seed=22, start_menu=True)
    game.main_menu = False
    game.menu_screen = "scenario"
    game.menu_sel = 0
    monkeypatch.setattr(random, "SystemRandom", lambda: type(
        "FixedRandom", (), {"randrange": lambda self, start, stop: 83})())

    game._handle_menu_key(pygame.K_RETURN)
    assert game.menu_screen == "briefing"
    game._handle_menu_key(pygame.K_r)
    expected_seed = 84
    expected_sector = sector_for_seed(expected_seed)[0]["id"]
    game._handle_menu_key(pygame.K_RETURN)

    assert not game.in_menu
    assert game.seed == expected_seed
    assert game.world_mode == "procedural"
    assert game.world.coast.metadata["sector_id"] == expected_sector
