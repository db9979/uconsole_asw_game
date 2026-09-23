"""Phase 2: force-based own-ship hydrodynamics."""

import copy
import json
import math
from types import SimpleNamespace

import pytest

from src.core import config
from src.core.game import Game
from src.physics import ship_dynamics as dyn
from src.ship.ship import Ship

KN = dyn.KN


def _rk4(f, v, dt, steps):
    h = dt / steps
    for _ in range(steps):
        k1 = f(v)
        k2 = f(v + .5 * h * k1)
        k3 = f(v + .5 * h * k2)
        k4 = f(v + h * k3)
        v += h * (k1 + 2 * k2 + 2 * k3 + k4) / 6.0
    return v


@pytest.mark.parametrize("a0,a1,a2,v0", [
    (0.5, 0.02, 0.01, 0.0), (0.5, 0.02, 0.01, 9.0), (-0.3, 0.0, 0.01, 8.0),
    (0.0, 0.0, 0.02, 5.0)])
def test_riccati_step_matches_numerical_integration(a0, a1, a2, v0):
    exact = dyn.riccati_step(v0, a0, a1, a2, 12.0)
    numeric = _rk4(lambda v: a0 - a1 * v - a2 * v * v, v0, 12.0, 4000)
    assert exact == pytest.approx(numeric, rel=1e-7, abs=1e-9)


def test_surge_is_step_size_invariant_across_regimes():
    hull = dyn.HULL
    mass = hull.mass_design_kg
    for start, target in ((0.0, 25.0), (25.0, 0.0), (16.0, 6.0), (6.0, 16.0)):
        big = dyn.surge_step(hull, start * KN, target * KN, mass, 150.0)[0]
        small = start * KN
        for _ in range(1500):
            small = dyn.surge_step(hull, small, target * KN, mass, 0.1)[0]
        assert big == pytest.approx(small, abs=1e-9)


@pytest.mark.parametrize("order,speed", config.TELEGRAPH_ORDERS)
def test_every_telegraph_order_reaches_its_calibrated_speed(order, speed):
    ship = Ship(0.0, 0.0, speed_kn=0.0)
    ship.target_speed = speed
    ship.update(1200.0)
    assert ship.speed == pytest.approx(speed, abs=0.02)


def test_heavier_ship_accelerates_slower_and_sits_deeper():
    light = Ship(0.0, 0.0, speed_kn=0.0)
    heavy = Ship(0.0, 0.0, speed_kn=0.0)
    heavy.flood_percent = 200.0
    light.fuel_kg = 100_000.0
    for ship in (light, heavy):
        ship.target_speed = 16.0
        ship.update(60.0)
    assert light.speed > heavy.speed
    assert heavy.dynamic_draft_m() > dyn.HULL.draft_m > light.dynamic_draft_m()


def test_added_resistance_in_heavy_sea_costs_speed():
    calm = Ship(0.0, 0.0, speed_kn=16.0)
    rough = Ship(0.0, 0.0, speed_kn=16.0)
    world = SimpleNamespace(effective_sea_state=6.0, sea_state=6,
                            wind_from_deg=0.0, ocean=SimpleNamespace(seed=1),
                            current_vec=lambda x, y: (0.0, 0.0),
                            depth_m=lambda x, y: 4000.0,
                            swept_grounding=lambda start, end, hull: SimpleNamespace(
                                safe_x_nm=end[0], safe_y_nm=end[1],
                                safe_course_deg=end[2], contacted=False,
                                contact=None))
    calm.target_speed = rough.target_speed = 16.0
    calm.update(1200.0)
    rough.update(1200.0, world)
    assert calm.speed == pytest.approx(16.0, abs=0.01)
    assert 13.0 < rough.speed < 15.8


def test_cavitation_onset_is_calibrated_and_earlier_when_stern_lifts():
    below = Ship(0.0, 0.0, speed_kn=14.9)
    below.target_speed = 14.9
    at = Ship(0.0, 0.0, speed_kn=15.0)
    at.target_speed = 15.0
    assert not below.cavitating and at.cavitating
    pitched = Ship(0.0, 0.0, speed_kn=13.5)
    pitched.target_speed = 13.5
    assert not pitched.cavitating
    pitched.pitch = -3.0          # bow down: screws rise toward the surface
    assert pitched.cavitating


def test_squat_deepens_draft_in_shallow_water_and_feeds_grounding():
    ship = Ship(0.0, 0.0, speed_kn=25.0)
    assert ship.dynamic_draft_m(11.0) - ship.dynamic_draft_m() > 2.0
    assert ship.dynamic_draft_m(2000.0) == pytest.approx(ship.dynamic_draft_m())
    slow = Ship(0.0, 0.0, speed_kn=4.0)
    assert slow.dynamic_draft_m(11.0) - slow.dynamic_draft_m() < 0.2
    seen = {}

    def swept(start, end, hull):
        seen["draft"] = hull.draft_m
        return SimpleNamespace(safe_x_nm=end[0], safe_y_nm=end[1],
                               safe_course_deg=end[2], contacted=False,
                               contact=None)
    world = SimpleNamespace(depth_m=lambda x, y: 11.0, swept_grounding=swept,
                            effective_sea_state=0.0, sea_state=0,
                            wind_from_deg=0.0, current_vec=lambda x, y: (0, 0))
    ship.target_speed = 25.0
    ship.update(1.0, world)
    assert seen["draft"] > dyn.HULL.draft_m + 2.0
    assert ship.hull_spec.draft_m == dyn.HULL.draft_m   # saved spec unchanged


def test_jammed_steering_gear_holds_the_rudder_and_keeps_turning():
    ship = Ship(0.0, 0.0, speed_kn=16.0)
    ship.target_speed = 16.0
    ship.rudder_angle = 15.0
    ship.steering_jammed = True
    ship.target_course = 0.0
    for _ in range(120):
        ship.update(1.0)
    assert ship.rudder_angle == 15.0
    assert ship.yaw_rate > 0.3


def test_stabilizers_damp_roll_and_turn_heels_outward():
    world = SimpleNamespace(wind_from_deg=90.0, ocean=SimpleNamespace(seed=5))

    def peak(stabilized):
        ship = Ship(0.0, 0.0, speed_kn=18.0)
        ship.stabilizers_ok = stabilized
        ship.sea_state = 6.0
        values = []
        for _ in range(4000):
            ship._update_roll_pitch(0.05, world)
            values.append(abs(ship.roll))
        return max(values[800:])
    assert peak(True) < 0.8 * peak(False)
    turning = Ship(0.0, 0.0, speed_kn=25.0)
    turning.yaw_rate = 1.5
    assert turning.heel_deg > 1.0


def test_wake_is_bounded_decays_and_round_trips():
    ship = Ship(100.0, 100.0, speed_kn=20.0)
    ship.target_speed = 20.0
    for _ in range(700):
        ship.update(1.0)
    assert 0 < len(ship.wake) <= dyn.HULL.wake_max_points
    newest = ship.wake[-1]
    assert ship.wake_strength_at(newest[0], newest[1]) > 0.3
    assert ship.wake_strength_at(ship.x + 30, ship.y) == 0.0
    oldest = ship.wake[0]
    assert ship.wake_strength_at(oldest[0], oldest[1], 0.01) < \
        ship.wake_strength_at(newest[0], newest[1], 0.01)

    game = Game(seed=2201, start_menu=False, audio_enabled=False)
    game.ship.speed = game.ship.target_speed = 20.0
    for _ in range(30):
        game.update(1.0)
    game.ship.roll_rate = 0.7
    state = json.loads(json.dumps(game.save_state()))
    assert state["ship"]["wake"]
    restored = Game(seed=1, start_menu=False, audio_enabled=False)
    assert restored._load_save_data(copy.deepcopy(state))
    assert restored.ship.wake == game.ship.wake
    assert restored.ship.roll_rate == 0.7
    for _ in range(20):
        game.update(0.5)
        restored.update(0.5)
    assert restored.save_state()["ship"] == game.save_state()["ship"]
    for mutation in (lambda s: s.update(roll_rate=1e6),
                     lambda s: s["wake"].append([0.0, 0.0, 1e13, 5.0]),
                     lambda s: s.update(wake=[[0, 0, 0]])):
        broken = copy.deepcopy(state)
        mutation(broken["ship"])
        assert not restored._load_save_data(broken)


def test_steady_fuel_matches_cubic_reference_and_braking_uses_power():
    for speed in (6.0, 16.0, 25.0):
        ship = Ship(0.0, 0.0, speed_kn=speed)
        ship.target_speed = speed
        expected = (config.SHIP_FUEL_HOTEL_KG_H
                    + config.SHIP_FUEL_MAX_PROPULSION_KG_H
                    * (speed / config.SHIP_SPEED_MAX_KN) ** 3)
        assert ship.fuel_burn_kg_h() == pytest.approx(expected, rel=1e-6)
    braking = Ship(0.0, 0.0, speed_kn=16.0)
    braking.target_speed = 0.0
    assert braking.fuel_burn_kg_h() > config.SHIP_FUEL_HOTEL_KG_H
    assert math.isclose(braking.rpm(), dyn.HULL.idle_rpm)
