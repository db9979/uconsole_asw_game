"""Plan 1.3, phase 8: counter-flooding, longitudinal trim, plant selection."""

import copy
import json
import random

import pytest

from src.core import config
from src.core.game import Game
from src.ship import damage as damage_module
from src.ship.damage import DamageModel
from src.ship.ship import PLANT_DIESEL_MAX_KN, Ship


def _model():
    return DamageModel(random.Random(3))


def _list_model(side="hull_right", flood=40.0):
    model = _model()
    model.compartments[side].flood = flood
    model._recompute_totals()
    return model


def test_counterflood_needs_a_list_and_floods_the_high_side():
    model = _model()
    assert model.order_counterflood() == "not_needed"
    model = _list_model("hull_right", 40.0)
    assert model.list_deg() > damage_module.COUNTERFLOOD_MIN_LIST_DEG
    assert model.order_counterflood() is True
    assert model.counterflood_room == "hull_left"
    before = model.compartments["hull_left"].flood
    model.update(10.0, draft_m=7.5)
    after = model.compartments["hull_left"].flood
    assert after == pytest.approx(before + damage_module.COUNTERFLOOD_RATE_PCT_S * 10.0)
    assert after <= damage_module.COUNTERFLOOD_MAX_PCT


def test_counterflood_stops_by_itself_below_one_degree_and_never_exceeds_the_cap():
    model = _list_model("hull_right", 40.0)
    assert model.order_counterflood() is True
    for _ in range(400):
        model.update(1.0, draft_m=7.5)
        if model.counterflood_room is None:
            break
    assert model.counterflood_room is None
    assert abs(model.list_deg()) < damage_module.COUNTERFLOOD_STOP_LIST_DEG + 0.5
    assert model.compartments["hull_left"].flood <= damage_module.COUNTERFLOOD_MAX_PCT
    model.stop_counterflood()
    assert all(value == 0.0 for value in model.counterflood.values())


def test_counterflood_refuses_a_destroyed_side():
    model = _list_model("hull_right", 40.0)
    model.compartments["hull_left"].state = "ZERSTOERT"
    assert model.order_counterflood() == "destroyed"


def test_trim_follows_fore_aft_water_and_costs_speed_and_noise():
    model = _model()
    assert model.trim_deg() == 0.0
    assert model.engine_speed_cap() == config.SHIP_SPEED_MAX_KN
    model.compartments["sonar"].flood = 60.0          # far forward
    model._recompute_totals()
    trim = model.trim_deg()
    assert trim > 0.0
    assert model.engine_speed_cap() == pytest.approx(
        config.SHIP_SPEED_MAX_KN - trim * damage_module.TRIM_SPEED_LOSS_KN_PER_DEG)
    assert model.trim_noise_boost() == pytest.approx(trim * damage_module.TRIM_NOISE_PER_DEG)
    aft = _model()
    aft.compartments["flightdeck"].flood = 60.0
    aft._recompute_totals()
    assert aft.trim_deg() < 0.0 and aft.trim_noise_boost() == 0.0


def test_plant_modes_change_cap_noise_and_fuel_but_auto_is_the_baseline():
    ship = Ship(0.0, 0.0, speed_kn=20.0)
    ship.target_speed = 25.0
    baseline = (ship.effective_target_kn(), ship.noise_level(), ship.fuel_burn_kg_h())
    assert ship.plant_mode == "AUTO"
    ship.plant_mode = "DIESEL"
    assert ship.effective_target_kn() == PLANT_DIESEL_MAX_KN
    assert ship.noise_level() < baseline[1]
    assert ship.fuel_burn_kg_h() < baseline[2]
    ship.plant_mode = "TURBINE"
    assert ship.effective_target_kn() == baseline[0]
    assert ship.noise_level() >= baseline[1]
    assert ship.fuel_burn_kg_h() > baseline[2]
    ship.plant_mode = "AUTO"
    assert (ship.effective_target_kn(), ship.noise_level(), ship.fuel_burn_kg_h()) == baseline


def test_game_commands_and_save_round_trip(tmp_path):
    game = Game(seed=808, start_menu=False, audio_enabled=False)
    assert game.set_plant_mode("STEAM") == "invalid_value"
    assert game.set_plant_mode("DIESEL") is True and game.ship.plant_mode == "DIESEL"
    game._cycle_plant_mode()
    assert game.ship.plant_mode == "TURBINE"
    assert game.set_counterflood(True) == "not_needed"
    game.damage.compartments["hull_right"].flood = 40.0
    game.damage._recompute_totals()
    assert game.set_counterflood(True) is True
    assert game.damage.counterflood_room == "hull_left"
    for _ in range(4):
        game._update_sim(0.25)
    state = json.loads(json.dumps(game.save_state(), allow_nan=False))
    assert state["ship"]["plant_mode"] == "TURBINE"
    assert state["damage"]["compartments"]["hull_left"]["counterflood"] > 0.0
    restored = Game(seed=808, start_menu=False, audio_enabled=False)
    restored.load_state(copy.deepcopy(state))
    assert restored.ship.plant_mode == "TURBINE"
    assert restored.damage.counterflood_room == "hull_left"
    for mutate in (lambda s: s["ship"].__setitem__("plant_mode", "STEAM"),
                   lambda s: s["damage"]["compartments"]["engine"].__setitem__("counterflood", 5.0),
                   lambda s: s["damage"]["compartments"]["hull_left"].__setitem__("counterflood", -1.0)):
        broken = copy.deepcopy(state)
        mutate(broken)
        assert not restored._load_save_data(broken)
    assert game.set_counterflood(False) is True and game.damage.counterflood_room is None
