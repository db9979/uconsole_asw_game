"""Emergencies aboard: man overboard and steering failure on the frigate,
a jammed snorkel valve and battery gas on a submarine (1.3.120)."""

import copy
import math

from src.core import config
from src.core.autocrew import AutocrewController
from src.core.game import Game
from src.core.incidents import IncidentBoard, valid_item


def _game(seed=5301):
    game = Game(seed=seed, start_menu=False, audio_enabled=False)
    assert game.start_new_game("s1_patrouille", "fixed")
    return game


def _diesel_game():
    """A mission with a diesel boat (the scenario's class draw varies)."""
    for seed in range(5301, 5341):
        game = _game(seed)
        sub = game._incident_boat()
        if sub is not None and not sub.manual:     # an AI-commanded boat
            return game
    raise AssertionError("no diesel boat in 40 seeds")


def test_man_overboard_is_plotted_drifts_and_is_recovered_by_the_ship():
    game = _game()
    item = game._start_incident("overboard")
    assert item is not None and item["kind"] == "overboard"
    assert math.hypot(item["x"] - game.ship.x, item["y"] - game.ship.y) < 0.05
    assert any(row["id"] == item["plot_id"] for row in game.plot.objects)
    assert game.overboard_target() == (item["x"], item["y"])
    # Too fast: no pickup even right on top of him.
    game.ship.x, game.ship.y, game.ship.speed = item["x"], item["y"], 15.0
    game._update_incidents(1.0)
    assert item["active"]
    score = game.score
    game.ship.speed = config.INCIDENT_OVERBOARD_PICKUP_KN - 1.0
    game._update_incidents(1.0)
    assert not item["active"]
    assert game.score == score + config.SCORE_OVERBOARD_SAVED
    assert item["plot_id"] is None and game.overboard_target() is None
    assert game.overboard_just_recovered()


def test_man_overboard_is_lost_after_his_time_in_the_water():
    game = _game()
    item = game._start_incident("overboard")
    game.ship.x += 5.0
    score = game.score
    game.sim_t = item["end_t"]
    game._update_incidents(1.0)
    assert not item["active"]
    assert game.score == score - config.SCORE_OVERBOARD_LOST


def test_helicopter_hovering_over_the_man_winches_him_up():
    game = _game()
    item = game._start_incident("overboard")
    game.ship.x += 5.0
    helo = game.helo
    helo.launch(game.ship)
    helo.x, helo.y = item["x"], item["y"]
    helo.set_waypoint(item["x"], item["y"])
    game._update_incidents(1.0)
    assert not item["active"]


def test_bridge_autocrew_steers_onto_the_man_and_slows_down():
    game = _game()
    item = game._start_incident("overboard")
    game.ship.x, game.ship.y = item["x"], item["y"] + 0.5   # he is due north
    game.ship.target_course = 180.0
    game.ship.target_speed = 20.0
    assert AutocrewController._bridge(game) == "recovering"
    assert abs(((game.ship.target_course + 180.0) % 360.0) - 180.0) < 1.0
    assert game.ship.target_speed < config.INCIDENT_OVERBOARD_PICKUP_KN


def test_steering_failure_jams_then_halves_the_rudder_rate():
    game = _game()
    item = game._start_incident("rudder")
    assert item is not None
    assert game.rudder_casualty() == (True, True)
    game._update_sim(0.1)
    assert game.ship.steering_jammed
    game.sim_t = item["start_t"] + config.INCIDENT_RUDDER_JAM_S + 1.0
    assert game.rudder_casualty() == (False, True)
    healthy = _game()
    game._update_sim(0.1)
    healthy._update_sim(0.1)
    assert not game.ship.steering_jammed
    assert game.ship.turn_rate_scale < healthy.ship.turn_rate_scale
    game.sim_t = item["end_t"]
    game._update_incidents(0.1)
    assert not item["active"] and game.rudder_casualty() == (False, False)


def test_snorkel_valve_stops_charging_and_battery_gas_halves_it():
    game = _diesel_game()
    sub = game._incident_boat()
    assert sub is not None
    normal = sub.endurance.generator_kw()
    assert normal > 0.0, (sub.endurance.fuel_kwh, sub.endurance.profile)
    valve = game._start_incident("valve")
    assert valve is not None and valve["target_id"] == sub.id, valve
    assert valve_item_ok(valve), valve
    game._apply_incident_effects()
    assert sub.endurance.generator_kw() == 0.0
    assert sub.radar_hold_s > 0.0, (sub.manual, sub.radar_hold_s)   # the AI boat stays down
    game.sim_t = valve["end_t"]
    game._update_incidents(0.1)
    gas = game._start_incident("gas")
    assert gas is not None and gas["target_id"] == sub.id, gas
    game._apply_incident_effects()
    assert abs(sub.endurance.generator_kw() - 0.5 * normal) < 1e-9, (
        sub.endurance.generator_kw(), normal)
    game.sim_t = gas["end_t"]
    game._update_incidents(0.1)
    game._apply_incident_effects()
    assert sub.endurance.generator_kw() == normal


def valve_item_ok(item):
    return valid_item(copy.deepcopy(item))


def test_emergencies_survive_a_board_round_trip():
    game = _diesel_game()
    for kind in ("overboard", "rudder", "valve"):
        assert game._start_incident(kind) is not None
    saved = game.incidents.serialize()
    restored = IncidentBoard.restore(copy.deepcopy(saved))
    assert restored.serialize() == saved


