"""Crew watches, fatigue and morale (frigate and crewed boat; save v21)."""

import copy
import json
import sys
from pathlib import Path

import pygame
import pytest

from src.core import config, uboot_local
from src.core.crew import CrewState, sonar_penalty_db
from src.core.game import Game
from src.core.station import Station
from src.sonar import equation

sys.path.insert(0, str(Path(__file__).parent))
from test_opfor_sub import _crewed  # noqa: E402
from test_uboot_scope import _key, _local_boat  # noqa: E402


def _game(seed=5201):
    game = Game(seed=seed, start_menu=False, audio_enabled=False)
    game.tasking.next_offer_t = 1e9
    return game


def _run(game, seconds, dt=5.0):
    for _ in range(int(seconds / dt)):
        game.sim_t += dt
        game._update_crew(dt)


def test_a_fresh_crew_is_the_calibrated_crew():
    game = _game()
    assert game.crew_effect() == 1.0
    assert game.sonar.operator_dt_db == 0.0 and game.damage.crew_factor == 1.0
    # Normal rotation keeps the duty watch below the free fatigue for hours.
    _run(game, 4 * config.CREW_WATCH_S + 120.0)
    assert game.crew_watch.duty_fatigue() <= config.CREW_FATIGUE_FREE
    assert game.crew_effect() == pytest.approx(1.0)


def test_watch_is_relieved_every_hour_with_a_short_turnover():
    game = _game()
    _run(game, config.CREW_WATCH_S)
    watch = game.crew_watch
    assert watch.on_watch == 1 and watch.in_turnover(game.sim_t)
    assert game.crew_effect() == pytest.approx(config.CREW_TURNOVER_FACTOR)
    _run(game, config.CREW_TURNOVER_S + 5.0)
    assert not watch.in_turnover(game.sim_t) and game.crew_effect() == pytest.approx(1.0)


def test_action_stations_alert_first_then_tired():
    game = _game()
    assert game.set_action_stations(True) is True
    assert game.set_action_stations(True) == "not_ready"
    assert game.crew_effect() == pytest.approx(config.CREW_ACTION_BONUS)
    assert game.change_watch() == "not_ready"          # nobody to relieve
    _run(game, 90 * 60.0)
    assert all(value > 0.9 for value in game.crew_watch.fatigue)
    assert game.crew_effect() < 0.8
    assert game.sonar.operator_dt_db > 1.0
    assert game.damage.crew_factor == pytest.approx(game.crew_effect())
    assert game.set_action_stations(False) is True
    assert game.crew_watch.watch_left_s(game.sim_t) == config.CREW_WATCH_S
    _run(game, 3 * config.CREW_WATCH_S + 120.0)
    assert game.crew_effect() == pytest.approx(1.0)    # rested again


def test_morale_follows_kills_damage_and_tasks():
    game = _game()
    start = game.crew_watch.morale
    task = game._offer_task("emcon")
    game.decline_task(task["id"])
    assert game.crew_watch.morale < start
    hostile = next(sub for sub in game.subs if sub.side == "hostile")
    hostile.sunk = True
    _run(game, 5.0)
    assert game.crew_watch.morale > start
    morale = game.crew_watch.morale
    game.damage.compartments["engine"].state = "BESCHAEDIGT"
    _run(game, 5.0)
    assert game.crew_watch.morale < morale
    _run(game, 5.0)
    assert game.crew_watch.damaged == 1                # credited once


def test_tired_sonar_needs_a_stronger_signal():
    terms = dict(frequency_hz=300.0, distance_nm=5.0, target_bonus=1.0,
                 excess_path_loss_db=0.0, absorption_db_per_km=0.0,
                 legacy_absorption_db=0.0, own_range_factor=1.0,
                 array_range_factor=1.0, sea_state=3, rain=0.0, shipping_contacts=0)
    fresh = equation.passive_terms(**terms)
    tired = equation.passive_terms(**terms, threshold_db=sonar_penalty_db(0.8))
    assert fresh.signal_excess_db - tired.signal_excess_db == pytest.approx(2.0)


def test_tired_damage_control_is_slower():
    game = _game()
    room = game.damage.compartments["engine"]
    fresh = game.damage.repair_rates("engine")
    game.damage.teams[1] = "engine"
    game.damage.team_eta[1] = 0.0
    fresh = game.damage.repair_rates("engine")
    game.damage.crew_factor = 0.8
    tired = game.damage.repair_rates("engine")
    assert tired[0] == pytest.approx(0.8 * fresh[0]) and tired[1] == pytest.approx(0.8 * fresh[1])
    assert room is game.damage.compartments["engine"]


def test_crew_page_keys_and_draw():
    game = _game()
    game.station, game.station_page = Station.DAMAGE, 2
    _key(game, pygame.K_g)
    assert game.crew_watch.action_stations
    _key(game, pygame.K_w)                              # blocked at action stations
    assert game.crew_watch.on_watch == 0
    game.draw()
    game.station, game.station_page = Station.BRIDGE, 0
    _key(game, pygame.K_g)
    assert not game.crew_watch.action_stations
    game.station, game.station_page = Station.DAMAGE, 2
    game.crew_watch.turnover_t = None
    _key(game, pygame.K_w)
    assert game.crew_watch.on_watch != 0
    game.station, game.station_page = Station.DAMAGE, 0
    before = game.crew_watch.on_watch
    _key(game, pygame.K_w)                              # plan page: no watch order
    assert game.crew_watch.on_watch == before


def test_crew_state_schema_is_exact():
    state = CrewState(12.0).serialize()
    assert CrewState.valid_state(state)
    assert CrewState.restore(state).serialize() == state
    for key, value in (("morale", 1.5), ("on_watch", 3), ("fatigue", [0.0, 0.0]),
                       ("turnover_t", float("nan")), ("kills", -1), ("version", 2)):
        broken = copy.deepcopy(state)
        broken[key] = value
        assert not CrewState.valid_state(broken)
    broken = dict(state, action_stations=True, turnover_t=20.0)
    assert not CrewState.valid_state(broken)
    broken = dict(state, extra=1)
    assert not CrewState.valid_state(broken)
    with pytest.raises(ValueError):
        CrewState.restore(broken)


def test_save_load_continues_the_watch_bill_identically():
    game = _game()
    game.set_action_stations(True)
    _run(game, 1200.0)
    game.damage.compartments["engine"].state = "BESCHAEDIGT"
    _run(game, 5.0)
    document = json.loads(json.dumps(game.save_state()))
    other = _game()
    assert other._load_save_data(document)
    assert other.damage.crew_factor == game.damage.crew_factor
    assert other.sonar.operator_dt_db == game.sonar.operator_dt_db
    for runner in (game, other):
        runner.set_action_stations(False)
        _run(runner, 1800.0)
    assert game.crew_watch.serialize() == other.crew_watch.serialize()
    for mutate in (lambda doc: doc.pop("watch"),
                   lambda doc: doc["watch"].update(watch_t=doc["sim_t"] + 10.0),
                   lambda doc: doc["watch"].update(morale="high")):
        broken = copy.deepcopy(document)
        mutate(broken)
        assert not other._load_save_data(broken)


def test_crewed_boat_has_its_own_watch_bill():
    game, _server, bridge = _crewed()
    boat = game.opfor
    assert boat.watch.watch_t == game.sim_t
    apply = bridge._apply_opfor_action
    assert apply(game, "uboot_action_stations", {"enabled": True}, "uboot_engine") is True
    assert boat.watch.action_stations and not game.crew_watch.action_stations
    assert apply(game, "uboot_watch_change", {}, "uboot") == "not_ready"
    assert apply(game, "uboot_action_stations", {"enabled": False}, "uboot_sonar") is False
    _run(game, 5400.0)
    effect = boat.watch.effectiveness(game.sim_t)
    assert effect < 0.8
    assert boat.sub.damage_control.crew_factor == pytest.approx(effect)
    assert boat.station.sonar.operator_dt_db == pytest.approx(sonar_penalty_db(effect))
    assert game.sonar.operator_dt_db == 0.0              # the frigate is not tired
    document = json.loads(json.dumps(game.save_state()))
    assert document["crew"]["watch"] == boat.watch.serialize()
    broken = copy.deepcopy(document)
    del broken["crew"]["watch"]
    assert not game._load_save_data(broken)
    game.release_opfor_sub()
    assert boat.sub.damage_control.crew_factor == 1.0


def test_boat_keys_order_the_watch_bill():
    game, boat = _local_boat()
    uboot_local.set_local_station(game, "uboot_engine")
    boat.command_page = 3
    # The frigate's keys: G action stations, W relieves the watch.
    _key(game, pygame.K_g)
    assert boat.watch.action_stations
    _key(game, pygame.K_g)
    assert not boat.watch.action_stations
    boat.watch.turnover_t = None
    _key(game, pygame.K_w)
    assert boat.watch.on_watch != 0
    game.draw()


def test_remote_crew_projection():
    from src.commander.projections import _crew
    game = _game()
    payload = _crew(game)
    assert payload["effectiveness"] == 1.0 and payload["on_watch"] == 1
    assert [row["index"] for row in payload["watches"]] == [1, 2, 3]
    assert json.loads(json.dumps(payload)) == payload
