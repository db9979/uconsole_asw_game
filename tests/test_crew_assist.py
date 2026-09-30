"""Crew assist (Shift+F2, on in every lobby round): the AI mans every station
nobody holds, on the frigate and on a crewed boat; the station the uConsole
shows stays with its operator."""

import copy
import json
import sys
from pathlib import Path

import pygame

from src.core import boat_autocrew, hunter, uboot_local
from src.core.autocrew import AUTOCREW_STATIONS
from src.core.game import Game
from src.core.station import Station

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from test_uboot_scope import _local_boat  # noqa: E402


def _game(seed=3901):
    return Game(seed=seed, start_menu=False, audio_enabled=False)


def _key(game, key, mod=0):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod, unicode=""))


def _run(game, seconds, dt=0.25):
    end = game.sim_t + seconds
    while game.sim_t < end - 1e-9 and not game.game_over:
        game._update_sim(dt)


def test_shift_f2_mans_every_station_but_the_one_on_screen():
    game = _game()
    game.station = Station.SONAR
    _key(game, pygame.K_F2, pygame.KMOD_SHIFT)
    assert game.crew_assist and all(game.autocrew.enabled.values())
    assert game.autocrew.status(game, "sonar") == "suspended_local"
    assert game.autocrew.status(game, "radio") == "active"
    # The operator keeps working the station on screen.
    assert not game._local_station_input_locked()
    assert hunter.active(game)
    assert hunter.manned(game, Station.SONAR) and not hunter.manned(game, Station.BRIDGE)
    game.station = Station.BRIDGE
    assert game.autocrew.status(game, "sonar") == "active"
    _key(game, pygame.K_F2, pygame.KMOD_SHIFT)
    assert not game.crew_assist and not any(game.autocrew.enabled.values())


def test_the_assist_is_saved_and_restored():
    game = _game()
    game.toggle_crew_assist()
    state = json.loads(json.dumps(game.save_state()))
    assert state["autocrew"]["assist"] is True
    other = _game()
    assert other._load_save_data(copy.deepcopy(state))
    assert other.crew_assist and set(k for k, v in other.autocrew.enabled.items() if v) \
        == set(AUTOCREW_STATIONS)
    broken = copy.deepcopy(state)
    broken["autocrew"]["assist"] = 1
    assert not other._load_save_data(broken)


def test_the_boat_autocrew_works_only_the_free_boat_stations():
    game, boat = _local_boat(seed=3902)
    uboot_local.set_local_station(game, "uboot_engine")
    sub = boat.sub
    sub.command_trim_auto(False)
    before = (sub.order_course, sub.order_speed, sub.order_depth)
    _run(game, 4.0)
    assert not sub.ballast.auto                    # nobody touches it without the assist
    assert (sub.order_course, sub.order_speed, sub.order_depth) == before
    game.autocrew.set_assist(True, game.sim_t)
    assert boat_autocrew.active(game)
    assert boat_autocrew.held(game, "uboot_engine")
    assert not boat_autocrew.held(game, "uboot")
    _run(game, 4.0)
    assert not sub.ballast.auto                    # the engine room is the uConsole's
    assert (sub.order_course, sub.order_speed, sub.order_depth) != before
    uboot_local.set_local_station(game, "uboot_sonar")
    _run(game, 4.0)
    assert sub.ballast.auto


def test_the_boat_autocrew_is_deterministic():
    def run():
        game, _boat = _local_boat(seed=3903)
        uboot_local.set_local_station(game, "uboot_sonar")
        game.autocrew.set_assist(True, game.sim_t)
        _run(game, 120.0, dt=0.5)
        sub = game.opfor.sub
        return (round(sub.x, 9), round(sub.y, 9), round(sub.depth, 6),
                sub.order_course, sub.order_speed, sub.order_depth, sub.snorkeling)
    assert run() == run()
