import math
import random
from types import SimpleNamespace

import pytest

from src.air.flights import Flight
from src.core import config
from src.enemies.decoy import Decoy
from src.ship.ship import Ship
from src.weapons.torpedo import EnemyTorpedo, Torpedo
from src.world.coastline import Coastline
from src.world.world import World


def test_one_minute_at_one_x_uses_physical_ship_speed():
    ship = Ship(100.0, 100.0, course_deg=90.0, speed_kn=20.0)
    ship.update(60.0)

    assert not hasattr(config, "TACTICAL_TIME_SCALE")
    assert ship.x == pytest.approx(100.0 + 20.0 / 60.0)
    assert ship.y == pytest.approx(100.0)


def test_ship_speed_response_is_dt_agnostic_and_asymptotic():
    """W2: hydrodynamic exponential-lag speed response - closed form, so one
    big-dt call must match many small-dt calls, and it approaches but never
    overshoots the commanded speed."""
    big = Ship(100.0, 100.0, speed_kn=0.0)
    big.target_speed = 25.0
    big.update(120.0)

    small = Ship(100.0, 100.0, speed_kn=0.0)
    small.target_speed = 25.0
    for _ in range(1200):
        small.update(0.1)

    assert big.speed == pytest.approx(small.speed, abs=1e-6)
    assert 0.0 < big.speed < 25.0


def test_ship_turn_rate_scales_linearly_with_speed_nomoto():
    """Phase 2: Nomoto steering r = K (V/L) delta - rudder force grows with
    dynamic pressure but so does the hull's yaw damping, so the steady turn
    rate doubles with speed and the turning circle stays nearly constant."""
    slow = Ship(100.0, 100.0, course_deg=0.0, speed_kn=4.0)
    slow.target_speed = 4.0
    slow.target_course = 90.0
    fast = Ship(100.0, 100.0, course_deg=0.0, speed_kn=8.0)
    fast.target_speed = 8.0
    fast.target_course = 90.0
    for _ in range(300):
        for ship in (slow, fast):
            ship.target_course = (ship.course + 90.0) % 360.0   # hold hard rudder
            ship.update(1.0)

    assert fast.yaw_rate == pytest.approx(2.0 * slow.yaw_rate, rel=0.02)


def test_ship_drifts_with_ocean_current_when_stopped():
    """W2: current is a pure additive drift, independent of propulsion - a
    stopped ship with zero speed still moves if the world reports a current."""
    open_water = Coastline({"world_nm": 500.0, "landmasses": [], "airbases": []}, 500.0)
    world = World(seed=1, coast=open_water)
    world.current_vec = lambda x, y: (0.5, 0.0)
    ship = Ship(100.0, 100.0, speed_kn=0.0)
    ship.target_speed = 0.0
    ship.update(60.0, world)

    assert ship.x == pytest.approx(100.0 + config.kn_to_nm_per_s(0.5) * 60.0)
    assert ship.y == pytest.approx(100.0)


def test_hull_list_pulls_course_off_target_without_rudder_input():
    """A listing ship needs constant rudder correction to hold course:
    the same steady target course drifts away over time only when listing."""
    level = Ship(100.0, 100.0, course_deg=90.0, speed_kn=15.0)
    level.target_course = 90.0
    listing = Ship(100.0, 100.0, course_deg=90.0, speed_kn=15.0)
    listing.target_course = 90.0

    for _ in range(200):
        level.update(1.0, list_bias_deg=0.0)
        listing.update(1.0, list_bias_deg=config.SHIP_MAX_LIST_DEG)

    assert level.course == pytest.approx(90.0, abs=0.05)
    assert listing.course != pytest.approx(90.0, abs=0.05)
    assert listing.yaw_rate != 0.0


def test_torpedo_drifts_with_ocean_current_when_stopped():
    """W2: current is a pure additive drift, independent of propulsion - a
    zero-speed torpedo still moves if the world reports a current."""
    world = SimpleNamespace(current_vec=lambda x, y: (0.5, 0.0))
    torpedo = Torpedo(100.0, 100.0, 90.0, 50.0, None, 1, speed_kn=0.0)
    torpedo.update(60.0, world=world)

    assert torpedo.x == pytest.approx(100.0 + config.kn_to_nm_per_s(0.5) * 60.0)
    assert torpedo.y == pytest.approx(100.0)


def test_enemy_torpedo_drifts_with_ocean_current_when_stopped():
    world = SimpleNamespace(current_vec=lambda x, y: (0.5, 0.0))
    target = SimpleNamespace(x=100.0, y=0.0)
    torpedo = EnemyTorpedo(100.0, 100.0, 90.0, 10.0, 1)
    torpedo.speed_kn = 0.0
    torpedo.update(60.0, target, world=world)

    assert torpedo.x == pytest.approx(100.0 + config.kn_to_nm_per_s(0.5) * 60.0)
    assert torpedo.y == pytest.approx(100.0)


def test_decoy_drifts_with_ocean_current():
    world = SimpleNamespace(current_vec=lambda x, y: (0.5, 0.0), size_nm=500.0)
    decoy = Decoy(100.0, 100.0, 50.0, random.Random(1))
    decoy.speed = 0.0
    decoy.update(10.0, world)

    assert decoy.x == pytest.approx(100.0 + config.kn_to_nm_per_s(0.5) * 10.0)
    assert decoy.y == pytest.approx(100.0)


def test_enemy_torpedo_uses_knots_without_hidden_compression():
    target = SimpleNamespace(x=100.0, y=0.0)
    torpedo = EnemyTorpedo(0.0, 0.0, 90.0, 10.0, 1)
    torpedo.update(60.0, target)

    assert torpedo.travel == pytest.approx(torpedo.speed_kn / 60.0)


def test_civil_flight_uses_knots_and_direct_route():
    base = {"id": "A", "x": 10.0, "y": 10.0, "nation": "HANSE"}
    dest = {"id": "B", "x": 20.0, "y": 10.0, "nation": "HANSE"}
    flight = Flight("civil", base, dest=dest, rng=random.Random(4))
    flight.update(60.0)

    assert flight.speed == 450.0
    assert flight.x == pytest.approx(10.0 + 450.0 / 60.0)
    assert flight.y == pytest.approx(10.0)


def test_military_flight_uses_racetrack_waypoints():
    base = {"id": "A", "x": 100.0, "y": 100.0, "nation": "BOREN"}
    flight = Flight("military", base, loiter_nm=20.0,
                    rng=random.Random(7))

    assert len(flight.waypoints) == 4
    assert all(math.hypot(x - base["x"], y - base["y"]) > 15.0
               for x, y in flight.waypoints)
