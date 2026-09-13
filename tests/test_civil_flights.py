"""Zivile Luftfahrt: role-basierte Spawns, Spieler-nahe Routen, Cooldown."""

import math
import random

import pytest

from src.air.flights import Flight, FlightManager
from src.core import config
from src.data.catalog import CATALOG


def _coast():
    from src.world.coastline import Coastline
    bases = [
        {"id": "f1", "name": "F1", "nation": "UK", "gameplay_role": "friendly",
         "x": 10.0, "y": 10.0},
        {"id": "f2", "name": "F2", "nation": "UK", "gameplay_role": "friendly",
         "x": 200.0, "y": 10.0},
        {"id": "h1", "name": "H1", "nation": "UK", "gameplay_role": "hostile",
         "x": 400.0, "y": 10.0},
        {"id": "n1", "name": "N1", "nation": "UK", "gameplay_role": "neutral",
         "x": 100.0, "y": 300.0},
    ]
    return Coastline({"airbases": [dict(b) for b in bases],
                      "landmasses": [], "bathymetry": None,
                      "metadata": {}, "world_nm": 500.0}, 500.0)


def _scripted_manager(f1, f2, civil_roll):
    manager = FlightManager(_coast(), random.Random(0), CATALOG,
                            near=(300.0, 250.0))
    manager.flights = []
    manager._spawn_cd = 0.0
    choices = iter((f1, f2))
    fake = type("Rng", (), {})()
    fake.uniform = lambda lo, hi: 1200.0
    fake.choice = lambda bases: next(choices)
    fake.random = lambda: civil_roll
    manager.rng = fake
    return manager


def test_hostile_base_detection_uses_role_then_legacy_nation():
    check = FlightManager._is_hostile_base
    assert check({"gameplay_role": "hostile", "nation": "UK"})
    assert not check({"gameplay_role": "civil", "nation": "BOREN"})
    assert check({"nation": "BOREN"})
    assert not check({"nation": "HANSE"})
    assert not check({})


def test_civil_via_bends_far_routes_toward_the_frigate():
    coast = _coast()
    manager = FlightManager(coast, random.Random(1), CATALOG,
                            near=(300.0, 250.0))
    a, b = coast.airbases[0], coast.airbases[1]
    via = manager._civil_via(a, b, (300.0, 250.0))
    assert via is not None
    assert math.hypot(via[0] - 300.0, via[1] - 250.0) == \
        pytest.approx(config.FLIGHT_CIVIL_VIA_NM)
    assert 0.0 <= via[0] <= 500.0 and 0.0 <= via[1] <= 500.0
    # A route that already passes close stays direct.
    assert manager._civil_via(a, b, (100.0, 20.0)) is None
    # Without any frigate position no routing is invented.
    plain = FlightManager(coast, random.Random(1), CATALOG)
    assert plain._civil_via(a, b) is None


def test_civil_flight_steers_through_the_via_point():
    base = {"id": "a", "x": 0.0, "y": 0.0}
    dest = {"id": "b", "x": 400.0, "y": 0.0}
    via = (200.0, 270.0)
    flight = Flight("civil", base, dest=dest, via=via, rng=random.Random(3),
                    seq=9, catalog=CATALOG)
    assert flight.waypoints == [via]
    assert flight.total_dist == pytest.approx(
        math.hypot(200.0, 270.0) * 2.0)
    closest = float("inf")
    for _ in range(120):
        flight.update(30.0)
        closest = min(closest, math.hypot(flight.x - via[0],
                                          flight.y - via[1]))
    assert flight.active
    assert closest < 10.0
    for _ in range(300):
        flight.update(30.0)
    assert not flight.active


def test_civil_flight_without_via_keeps_the_legacy_straight_route():
    base = {"id": "a", "x": 10.0, "y": 10.0}
    dest = {"id": "b", "x": 20.0, "y": 10.0}
    flight = Flight("civil", base, dest=dest, rng=random.Random(4),
                    catalog=CATALOG)
    flight.update(60.0)
    assert flight.speed == 450.0
    assert flight.x == pytest.approx(10.0 + 450.0 / 60.0)
    assert flight.y == pytest.approx(10.0)
    assert flight.waypoints == []


def test_continuous_civil_spawn_routes_near_the_frigate():
    coast = _coast()
    f1, f2 = coast.airbases[0], coast.airbases[1]
    manager = _scripted_manager(f1, f2, 0.1)
    manager.update(1.0, near=(300.0, 250.0))
    assert [f.kind for f in manager.flights] == ["civil"]
    flight = manager.flights[0]
    assert flight.waypoints
    assert math.hypot(flight.waypoints[0][0] - 300.0,
                      flight.waypoints[0][1] - 250.0) == \
        pytest.approx(config.FLIGHT_CIVIL_VIA_NM)
    assert manager._spawn_cd == 1200.0


def test_continuous_civil_spawn_rejects_hostile_bases_with_short_retry():
    coast = _coast()
    f1, h1 = coast.airbases[0], coast.airbases[2]
    manager = _scripted_manager(f1, h1, 0.1)
    manager.update(1.0, near=(300.0, 250.0))
    assert manager.flights == []
    assert manager._spawn_cd == 300.0


def test_continuous_military_spawn_uses_hostile_role_base():
    coast = _coast()
    f1, h1 = coast.airbases[0], coast.airbases[2]
    manager = _scripted_manager(f1, h1, 0.9)
    manager.update(1.0, near=(300.0, 250.0))
    assert [f.kind for f in manager.flights] == ["military"]
    assert manager.flights[0].base_id == "h1"
    assert manager._spawn_cd == 1200.0


def test_repeated_same_base_attempt_retries_quickly():
    coast = _coast()
    f1 = coast.airbases[0]
    manager = _scripted_manager(f1, f1, 0.1)
    manager.update(1.0, near=(300.0, 250.0))
    assert manager.flights == []
    assert manager._spawn_cd == 300.0


def test_spawn_sequence_is_deterministic():
    def run():
        manager = FlightManager(_coast(), random.Random(99), CATALOG,
                                near=(300.0, 250.0))
        for _ in range(6000):
            manager.update(1.0, near=(300.0, 250.0))
        return [(f.seq, f.kind, f.base_id, f.waypoint_idx,
                 round(f.x, 6), round(f.y, 6)) for f in manager.flights]

    assert run() == run()


def test_civil_via_waypoint_survives_save_load():
    from src.core.game import Game

    game = Game(seed=6, start_menu=False, audio_enabled=False)
    bases = game.world.coast.airbases
    via = game.flights._civil_via(bases[0], bases[1],
                                  (game.ship.x, game.ship.y))
    if via is None:
        via = game.flights._civil_via(bases[0], bases[2],
                                      (game.ship.x, game.ship.y))
        assert via is not None
    flight = Flight("civil", bases[0], dest=bases[1], via=via,
                    rng=game.flights.rng, seq=game.flights._seq + 1,
                    catalog=game.runtime_catalog)
    game.flights.flights = [flight]
    state = game.save_state()
    assert state["flights"]["items"][0]["waypoints"] == [via]
    restored = Game(seed=6, start_menu=False, audio_enabled=False)
    restored.load_state(state)
    loaded = restored.flights.flights[0]
    assert loaded.waypoints == [tuple(via)]
    assert loaded.waypoint_idx == 0
    assert loaded.total_dist == pytest.approx(flight.total_dist)
