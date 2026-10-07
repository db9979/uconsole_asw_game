"""Fire by click outside the weapons station needs a confirming second click."""

import pygame
import pytest

from src.core.game import Game
from src.core.station import Station
from src.ui import layout, pointer
from src.ui.stations import common


@pytest.fixture
def game(monkeypatch):
    monkeypatch.setattr(pygame.display, "get_window_size", lambda: (1280, 720))
    instance = Game(seed=31, start_menu=False, audio_enabled=False, language="de")
    yield instance
    instance.commander.stop()
    instance.audio.shutdown()
    layout.configure_for(large_text=False)


def fire_target(game):
    game.draw()
    return next(t for t in pointer.targets("station") if t.action is not None
                and getattr(t.action, "__qualname__", "").startswith("fire_button"))


def click(game, target):
    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        game.handle_event(pygame.event.Event(kind, button=1, pos=target.rect.center))


@pytest.mark.parametrize("station, page, launcher", (
    (Station.OPZ, 1, "launch_essm"),
    (Station.HELICOPTER, 1, "launch_helo_torpedo"),
))
def test_first_click_arms_second_fires(game, monkeypatch, station, page, launcher):
    fired = []
    monkeypatch.setattr(game, launcher, lambda *a, **k: fired.append(launcher))
    game.station, game.station_page = station, page
    target = fire_target(game)
    click(game, target)
    assert fired == [] and common.fire_armed(game, game._fire_armed[0])
    click(game, fire_target(game))
    assert fired == [launcher]
    assert not getattr(game, "_fire_armed", None)


def test_the_arming_runs_out(game, monkeypatch):
    fired = []
    monkeypatch.setattr(game, "launch_essm", lambda *a, **k: fired.append(1))
    game.station, game.station_page = Station.OPZ, 1
    click(game, fire_target(game))
    game._t += common.FIRE_CONFIRM_S + 0.1
    click(game, fire_target(game))           # too late: arms again, fires nothing
    assert fired == []


def test_mpa_torpedo_button_only_once_chosen(game, monkeypatch):
    fired = []
    monkeypatch.setattr(game, "mpa_attack", lambda *a, **k: fired.append(1) or "ok")
    monkeypatch.setattr(game, "_mpa_order_feedback", lambda result: None)
    game.station, game.station_page = Station.OPZ, 2
    game.draw()
    assert not any(getattr(t.action, "__qualname__", "").startswith("fire_button")
                   for t in pointer.targets("station") if t.action is not None)
    game.opz_weapon = "mpa_torpedo"
    click(game, fire_target(game))
    click(game, fire_target(game))
    assert fired == [1]
