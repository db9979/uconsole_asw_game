import math
import random

import pygame
import pytest

from src.core.game import Game
from src.core.version import APP_VERSION, SPLASH_TEXT
from src.core.i18n import Translator
from src.ui import layout
from src.ui.splash_view import (SPLASH_PING_PERIOD_S, SPLASH_PING_SPEED_PX_S,
                                draw_splash, ping_origin, submarine_center)
from src.world.real_coast import sector_for_seed


def test_release_version_and_exact_splash_text():
    assert APP_VERSION == "1.3.263"
    assert SPLASH_TEXT == (
        "Anti Sub Marine Warfare on uConsole by Dominik Bornhäußer Version 1.3.263"
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


def test_splash_sonar_pulse_travels_from_frigate_to_submarine(monkeypatch):
    arcs = []

    def record_arc(surface, color, rect, start_angle, stop_angle, width):
        arcs.append((tuple(rect), start_angle, stop_angle))

    # The moment the pulse front reaches the submarine in the first cycle.
    elapsed = 1.0
    for _ in range(20):
        distance = math.dist(ping_origin(elapsed), submarine_center(elapsed))
        elapsed = distance / SPLASH_PING_SPEED_PX_S
    assert elapsed < SPLASH_PING_PERIOD_S
    origin = ping_origin(elapsed)
    monkeypatch.setattr(pygame.draw, "arc", record_arc)
    draw_splash(pygame.Surface((1280, 720)), elapsed)

    fronts = [(rect, start, stop) for rect, start, stop in arcs
              if abs(rect[0] + rect[2] // 2 - int(origin[0])) <= 1
              and abs(rect[1] + rect[3] // 2 - int(origin[1])) <= 1]
    assert fronts, "no pulse front centred on the frigate's sonar dome"
    target = math.dist(origin, submarine_center(elapsed))
    assert any(abs(rect[2] / 2 - target) <= 2 for rect, _s, _e in fronts)
    # The pulse spreads through the water below the frigate.
    assert all(start >= math.pi - 1e-9 for _rect, start, _stop in fronts)


def test_splash_and_menu_show_author_and_version():
    game = Game(seed=19, start_menu=True, show_splash=True)
    for language in ("en", "de"):
        game.tr = Translator(language)
        game._t = game.splash_started_at + 1.0
        with layout.capture_text() as texts:
            game.draw()
        shown = " ".join(item["text"] for item in texts)
        assert "by Dominik Bornhäußer" in shown and APP_VERSION in shown
    game.splash_active = False
    with layout.capture_text() as texts:
        game.draw()
    shown = " ".join(item["text"] for item in texts)
    assert "by Dominik Bornhäußer" in shown and APP_VERSION in shown


def test_splash_plays_one_ping_per_wave_cycle(monkeypatch):
    game = Game(seed=19, start_menu=True, show_splash=True)
    calls = []
    monkeypatch.setattr(game.audio, "play_ping", lambda: calls.append(game._t))

    game.update(.01)
    game.update(.01)
    assert len(calls) == 1

    game._t = game.splash_started_at + SPLASH_PING_PERIOD_S
    game.update(.01)
    assert len(calls) == 2

    game._t = game.splash_started_at + 2 * SPLASH_PING_PERIOD_S
    game.update(.01)
    assert len(calls) == 3

    game._t = game.splash_started_at + 20 * SPLASH_PING_PERIOD_S
    game.update(.01)
    assert game.splash_active is True
    assert len(calls) == 4


def test_splash_waits_for_keypress_and_ignores_mouse_click():
    game = Game(seed=19, start_menu=True, show_splash=True)
    game._t = game.splash_started_at + 30.0

    game.update(.01)
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1))
    assert game.splash_active is True

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


def test_fixed_real_sector_selection_and_seed_reroll(monkeypatch):
    game = Game(seed=22, start_menu=True)
    game._handle_menu_key(pygame.K_w)
    game._handle_menu_key(pygame.K_w)
    assert game.world_mode == "real_fixed"
    game._handle_menu_key(pygame.K_PAGEDOWN)      # Page keys scroll the list only
    assert game.seed == 22
    game._handle_menu_key(pygame.K_RIGHTBRACKET)
    assert game.seed % 128 == 23
    monkeypatch.setattr(random, "SystemRandom", lambda: type(
        "FixedRandom", (), {"randrange": lambda self, start, stop: start})())
    game._handle_menu_key(pygame.K_r)
    assert game.seed != 23
    assert game.seed % 128 == 23
    game.main_menu = False
    game.menu_screen = "briefing"
    game._handle_menu_key(pygame.K_RETURN)
    assert game.world.coast.metadata["sector_id"] == "real-023"
    assert len(game.world.coast.airbases) >= 4
    center = game.world.coast.metadata["center"]
    assert game.live_traffic._center == (center["longitude"], center["latitude"])
    assert game.flights.coast is game.world.coast


@pytest.mark.parametrize("main_menu,screen", [
    (True, "scenario"),
    (False, "scenario"),
    (False, "difficulty"),
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
