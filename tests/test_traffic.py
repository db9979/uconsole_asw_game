"""Merchant traffic: lanes to destinations, collision avoidance, alarm."""

import math
from types import SimpleNamespace

import pytest

from src.core import config
from src.enemies import traffic
from src.enemies.surface import SurfaceShip


class OpenSea:
    size_nm = 200.0
    sea_state = 0.0

    def __init__(self):
        self.coast = SimpleNamespace(airbases=[
            {"id": "a", "x": 20.0, "y": 100.0}, {"id": "b", "x": 180.0, "y": 100.0}])

    def on_land(self, x, y):
        return False

    def nearest_water(self, x, y):
        return x, y

    def land_blocks_line(self, *args):
        return False


def merchant(x, y, course, speed=12.0, category="FRACHT", seed=7):
    import random
    ship = SurfaceShip(x, y, random.Random(seed), side="neutral", doctrine="surface_transit")
    ship.profile = SimpleNamespace(**{**ship.profile.__dict__, "category": category})
    ship.course = ship.target_course = course
    ship.speed = ship.target_speed = speed
    return ship


def test_destinations_are_ports_and_edge_exits_in_a_stable_order():
    world = OpenSea()
    points = traffic.destinations(world)
    assert points[:2] == [(20.0, 100.0), (180.0, 100.0)]
    assert len(points) == 2 + traffic.EDGE_GATES
    assert traffic.destinations(world) is points


def test_a_merchant_takes_a_lane_and_steers_for_its_destination():
    world = OpenSea()
    ship = merchant(100.0, 100.0, 0.0)
    traffic.assign_lane(ship, 5, world)
    assert traffic.is_lane_ship(ship)
    point = traffic.destination(ship, 5, world)
    bearing = math.degrees(math.atan2(point[0] - 100.0, -(point[1] - 100.0))) % 360.0
    assert ship.course == pytest.approx(bearing)
    assert traffic.MIN_LEG_S <= ship.turn_left <= traffic.MAX_LEG_S


def test_work_boats_keep_wandering():
    world = OpenSea()
    ship = merchant(100.0, 100.0, 0.0, category="SONSTIGES")
    traffic.assign_lane(ship, 5, world)
    assert not traffic.is_lane_ship(ship)


def test_the_destination_is_a_pure_function_of_seed_ship_and_leg():
    world = OpenSea()
    ship = merchant(100.0, 100.0, 0.0)
    ship.turn_delta = 3.0
    first = traffic.destination(ship, 11, world)
    ship._lane_cache = None
    assert traffic.destination(ship, 11, world) == first
    ship.turn_delta = 4.0
    assert traffic.destination(ship, 11, world) != first


def test_arrival_starts_the_next_leg():
    world = OpenSea()
    ship = merchant(100.0, 100.0, 0.0)
    traffic.assign_lane(ship, 5, world)
    ship.x, ship.y = traffic.destination(ship, 5, world)
    traffic.plan([ship], [ship], 5, world)
    assert int(ship.turn_delta) == 2


def test_head_on_merchants_both_alter_to_starboard():
    world = OpenSea()
    a = merchant(100.0, 110.0, 0.0)
    b = merchant(100.0, 104.0, 180.0)
    for ship in (a, b):
        ship.turn_delta = 1.0
        ship._lane_cache = (1, world, (ship.x, ship.y - 80.0 if ship is a else ship.y + 80.0))
        ship.turn_left = 9999.0
    traffic.plan([a, b], [a, b], 5, world)
    assert a.target_course == pytest.approx(traffic.AVOID_DEG)
    assert b.target_course == pytest.approx(180.0 + traffic.AVOID_DEG)


def test_the_stand_on_ship_holds_when_crossing_from_port():
    world = OpenSea()
    own = merchant(100.0, 100.0, 0.0)
    own.turn_delta, own.turn_left = 1.0, 9999.0
    own._lane_cache = (1, world, (100.0, 20.0))
    # From port, heading east to cross ahead: own ship stands on.
    other = merchant(97.0, 97.5, 90.0)
    cpa, _tcpa, relative = traffic._close_pass(own, other, 0.0)
    assert traffic.CLOSE_CPA_NM < cpa < traffic.CPA_NM and relative < 0.0
    traffic.plan([own], [own, other], 5, world)
    assert own.target_course == pytest.approx(0.0)


def test_a_detonation_close_by_makes_lane_ships_run():
    world = OpenSea()
    ship = merchant(100.0, 100.0, 0.0)
    traffic.assign_lane(ship, 5, world)
    far = merchant(150.0, 100.0, 0.0)
    traffic.assign_lane(far, 5, world)
    traffic.alarm([ship, far], 100.0, 97.0)
    assert ship._torpedo_evade_left == traffic.ALARM_S
    assert far._torpedo_evade_left == 0.0
    ship._update_civil(1.0, world)
    assert ship.target_course == pytest.approx(180.0)
    assert ship.target_speed == pytest.approx(ship.speed_cap_kn)


def test_due_fires_once_per_step():
    ticks = [t for t in range(1, 101) if traffic.due(float(t), 1.0)]
    assert ticks == [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    assert config.clamp(1, 0, 2) == 1


def test_lane_state_survives_save_and_load(monkeypatch, tmp_path):
    import pygame
    from src.core.game import Game
    monkeypatch.setattr(pygame.display, "get_window_size", lambda: (1280, 720))
    game = Game(seed=4, start_menu=False, audio_enabled=False, language="en")
    try:
        for _ in range(30):
            game.update(1.0)
        before = [(c.id, c.turn_delta, c.turn_left, c.target_course) for c in game.civilians]
        document = game.save_state()
        game.load_state(document)
        after = [(c.id, c.turn_delta, c.turn_left, c.target_course) for c in game.civilians]
        assert after == before
    finally:
        game.audio.shutdown()
