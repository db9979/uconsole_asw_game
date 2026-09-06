import math
import random
from types import SimpleNamespace

import pytest

from src.air.flights import Flight
from src.core import config
from src.ship.ship import Ship
from src.weapons.torpedo import EnemyTorpedo


def test_one_minute_at_one_x_uses_physical_ship_speed():
    ship = Ship(100.0, 100.0, course_deg=90.0, speed_kn=20.0)
    ship.update(60.0)

    assert config.TACTICAL_TIME_SCALE == 1.0
    assert ship.x == pytest.approx(100.0 + 20.0 / 60.0)
    assert ship.y == pytest.approx(100.0)


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
