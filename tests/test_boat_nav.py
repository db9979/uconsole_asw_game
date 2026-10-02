"""The crewed boat's navigation: dead reckoning, GPS fix and the route."""

import copy
import json
import math
import sys
from pathlib import Path

import pygame

from src.commander.server import V2_ACTION_REGISTRY
from src.core import boat_nav, config, opfor, uboot_local
from src.core.game import Game
from src.ship import route as route_model

sys.path.insert(0, str(Path(__file__).parent))
from test_opfor_sub import _boat_apply, _crewed, _run  # noqa: E402


def _dived(game, depth=120.0, speed=6.0, course=90.0):
    sub = game.opfor.sub
    sub.set_orders(course=course, speed=speed, depth=depth)
    sub.depth = min(depth, sub.safe_depth_m(game.world))
    return sub


def test_dived_position_drifts_and_a_gps_fix_clears_it():
    game, _server, _bridge = _crewed(seed=83)
    boat = game.opfor
    _dived(game)
    assert boat.orders.nav == boat_nav.new_state()
    _run(game, 1800.0, dt=0.5)
    error = math.hypot(*boat_nav.error(boat))
    assert error > 0.01
    # The navigator's estimate covers the real error with a margin.
    assert boat_nav.uncertainty_nm(boat) >= error * 0.5
    assert boat.orders.nav[2] >= 1799.0
    # Mast up at periscope depth for the fix time: back on the true position.
    sub = boat.sub
    sub.set_orders(depth=opfor.depth_presets(game, boat)["periscope"], speed=3.0)
    sub.depth = opfor.depth_presets(game, boat)["periscope"]
    assert sub.command_mast(True) is True
    _run(game, config.UBOOT_GPS_FIX_S + 2.0, dt=0.25)
    assert boat_nav.error(boat) == (0.0, 0.0)
    assert boat.orders.nav[4] == 1
    assert boat.orders.nav[2] < config.UBOOT_GPS_FIX_S


def test_the_ai_boats_keep_their_exact_position():
    game = Game(seed=83, start_menu=False, audio_enabled=False, language="en")
    for _ in range(200):
        game._update_sim(0.5)
    assert game.opfor is None    # nothing to drift: only a crew navigates


def test_dead_reckoning_is_deterministic_and_saved():
    def run():
        game, _server, _bridge = _crewed(seed=91)
        _dived(game)
        _run(game, 900.0, dt=0.5)
        return game
    first, second = run(), run()
    assert first.opfor.orders.nav == second.opfor.orders.nav
    state = first.save_state()
    assert state["crew"]["orders"]["nav"] == first.opfor.orders.nav
    json.dumps(state, allow_nan=False)


def test_nav_state_validation_rejects_bad_values():
    assert boat_nav.valid_state(boat_nav.new_state())
    assert not boat_nav.valid_state([0.0, 0.0, 0.0, 0.0])
    assert not boat_nav.valid_state([float("nan"), 0.0, 0.0, 0.0, 0])
    assert not boat_nav.valid_state([99.0, 0.0, 0.0, 0.0, 0])
    assert not boat_nav.valid_state([0.0, 0.0, 0.0, config.UBOOT_GPS_FIX_S + 1, 0])
    assert not boat_nav.valid_state([0.0, 0.0, 0.0, 0.0, 1.5])


def test_route_waypoints_steer_the_boat_from_its_navigated_position():
    game, _server, bridge = _crewed(seed=83)
    apply = _boat_apply(game, bridge)
    boat = game.opfor
    sub = _dived(game, course=0.0)
    assert V2_ACTION_REGISTRY["uboot_route_waypoint"].stations == {"uboot_nav"}
    x, y = sub.x + 3.0, sub.y
    assert apply("uboot_route_waypoint", {"x": x, "y": y}) is True
    assert boat.orders.route.points == [(x, y)]
    _run(game, 1.0)
    assert abs(sub.order_course - 90.0) < 1.0
    # The navigated position, not the true one, decides the course.
    boat.orders.nav[1] = 1.0          # the crew believes it is 1 NM south
    _run(game, 0.5)
    expected = route_model.bearing_to(sub.x, sub.y + 1.0, x, y)
    assert abs(((sub.order_course - expected + 180.0) % 360.0) - 180.0) < 1.0
    # A helm order takes the boat off its route.
    assert apply("uboot_set_course", {"course": 180.0}) is True
    assert not boat.orders.route.active


def test_route_patterns_and_clear_are_navigation_orders():
    game, _server, bridge = _crewed(seed=83)
    apply = _boat_apply(game, bridge)
    boat = game.opfor
    _dived(game)
    assert apply("uboot_route_pattern", {"pattern": "zigzag"}) is True
    assert boat.orders.route.kind == "zigzag" and boat.orders.route.active
    assert len(boat.orders.route.points) == route_model.MAX_WAYPOINTS
    assert apply("uboot_route_clear", {}) is True
    assert not boat.orders.route.active
    # Full route: the ninth manual waypoint is refused.
    for index in range(route_model.MAX_WAYPOINTS):
        assert boat_nav.add_waypoint(boat, 100.0 + index, 100.0, 500.0) is True
    assert boat_nav.add_waypoint(boat, 120.0, 100.0, 500.0) == "uboot_route_full"


def test_navigation_keys_follow_the_frigate_bridge(monkeypatch):
    game, _server, _bridge = _crewed(seed=83)
    game.local_side = "uboot"
    uboot_local.set_local_station(game, "uboot_nav")
    monkeypatch.setattr(uboot_local, "station_remote", lambda _game: False)
    boat = game.opfor
    _dived(game)

    def key(code, mod=0):
        uboot_local.handle_key(game, pygame.event.Event(pygame.KEYDOWN, key=code, mod=mod))
    key(pygame.K_w)
    assert boat.orders.route.kind == "zigzag"
    key(pygame.K_w)
    assert boat.orders.route.kind == "square"
    key(pygame.K_BACKSPACE)
    assert not boat.orders.route.active


def test_route_and_nav_survive_a_save_round_trip():
    game, _server, _bridge = _crewed(seed=83)
    boat = game.opfor
    _dived(game)
    boat_nav.add_waypoint(boat, boat.sub.x + 2.0, boat.sub.y + 2.0, 500.0)
    _run(game, 120.0, dt=0.5)
    state = game.save_state()
    orders = state["crew"]["orders"]
    assert orders["route"]["points"] and orders["nav"][2] > 100.0
    restored = opfor.CrewOrders()
    restored.restore(copy.deepcopy(orders))
    assert restored.route.points == boat.orders.route.points
    assert restored.nav == boat.orders.nav
