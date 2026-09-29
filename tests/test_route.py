"""The Bridge's autopilot route: waypoints, search patterns, save v28."""

import copy
import json
import math

import pygame

from src.core import config
from src.core.game import Game
from src.core.station import Station
from src.ship import route as route_model
from src.ship.route import Route


def _game(seed=31):
    game = Game(seed=seed, start_menu=False, audio_enabled=False, language="en")
    game.station = Station.BRIDGE
    return game


def _run(game, seconds, dt=0.5):
    end = game.sim_t + seconds
    while game.sim_t < end - 1e-9 and not game.game_over:
        game._update_sim(dt)


def test_route_steers_through_waypoints_and_ends():
    route = Route()
    assert route.add(0.0, -1.0) and route.add(1.0, -1.0)
    course, reached = route.steer(0.0, 0.0)
    assert reached == 0 and abs(course - 0.0) < 1e-9
    course, reached = route.steer(0.0, -0.9)
    assert reached == 1 and abs(course - math.degrees(math.atan2(1.0, 0.1))) < 1e-6
    course, reached = route.steer(0.95, -1.0)
    assert course is None and reached == 1 and not route.active


def test_route_is_bounded_and_a_pattern_replaces_it():
    route = Route()
    for index in range(route_model.MAX_WAYPOINTS):
        assert route.add(float(index), 0.0)
    assert not route.add(99.0, 0.0)
    route.start_pattern("square", 10.0, 10.0, 0.0)
    assert route.kind == "square" and len(route.points) == route_model.MAX_WAYPOINTS
    # A manual waypoint after a pattern starts a new manual route.
    assert route.add(1.0, 1.0) and route.points == [(1.0, 1.0)] and route.kind == "manual"


def test_patterns_are_deterministic_geometry():
    zigzag = route_model.pattern_points("zigzag", 100.0, 100.0, 0.0)
    assert len(zigzag) == route_model.MAX_WAYPOINTS
    first = zigzag[0]
    assert math.isclose(math.hypot(first[0] - 100.0, first[1] - 100.0), route_model.ZIGZAG_LEG_NM)
    assert first[0] > 100.0 and first[1] < 100.0          # 045 off a north course
    square = route_model.pattern_points("square", 0.0, 0.0, 90.0)
    assert [round(p[0], 6) for p in square[:3]] == [1.0, 1.0, -1.0]
    assert [round(p[1], 6) for p in square[:3]] == [0.0, 1.0, 1.0]


def test_the_ship_follows_the_route_and_a_helm_order_cancels_it():
    game = _game()
    ship = game.ship
    game.order_speed(15.0)
    # North-west is open water at this start (east is land, see below).
    target = (ship.x - 2.1, ship.y - 2.1)
    assert game.add_route_waypoint(*target) == "ok"
    _run(game, 30.0)
    assert abs(ship.target_course - 315.0) < 3.0
    assert game.order_course(180.0) == "ok"
    assert not game.route.active and ship.target_course == 180.0


def test_the_route_is_reached_and_logged():
    game = _game()
    ship = game.ship
    game.order_speed(25.0)
    assert game.add_route_waypoint(ship.x, ship.y - 0.8) == "ok"
    _run(game, 240.0)
    assert not game.route.active and game.route.points == []


def test_rudder_takes_over_from_the_autopilot():
    game = _game()
    assert game.start_route_pattern("zigzag") == "ok"
    game.held.add(pygame.K_LEFT)
    game.update(0.1)
    assert not game.route.active


def test_bridge_keys_cycle_patterns_and_clear():
    game = _game()

    def key(code):
        game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=code, mod=0, unicode=""))

    key(pygame.K_w)
    assert game.route.kind == "zigzag" and game.route.active
    key(pygame.K_w)
    assert game.route.kind == "square"
    key(pygame.K_w)
    assert not game.route.active
    key(pygame.K_w)
    key(pygame.K_BACKSPACE)
    assert not game.route.active


def test_right_click_on_the_chart_adds_a_waypoint():
    game = _game()
    rect = pygame.Rect(config.MAP_RECT)
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=3,
                                         pos=(rect.centerx + 40, rect.centery)))
    assert game.route.active and len(game.route.points) == 1
    game.draw()


def test_route_saves_and_restores_and_bad_blocks_are_rejected():
    game = _game()
    game.order_speed(12.0)
    game.start_route_pattern("square")
    _run(game, 60.0)
    state = json.loads(json.dumps(game.save_state()))
    assert state["route"]["kind"] == "square"
    other = _game(seed=32)
    assert other._load_save_data(copy.deepcopy(state))
    assert other.route.serialize() == game.route.serialize()
    _run(game, 120.0)
    _run(other, 120.0)
    assert (other.ship.x, other.ship.y, other.ship.target_course) == \
        (game.ship.x, game.ship.y, game.ship.target_course)
    for bad in ({"points": [[0, 0]], "index": 3, "kind": "square"},
                {"points": [[float("nan"), 0]], "index": 0, "kind": "manual"},
                {"points": [[0, 0]] * (route_model.MAX_ROUTE_POINTS + 1), "index": 0,
                 "kind": "manual"},
                {"points": [], "index": 0, "kind": "spiral"},
                {"points": [], "index": 0}):
        broken = copy.deepcopy(state)
        broken["route"] = bad
        assert not other._load_save_data(broken)


def test_remote_crew_route_actions_reach_the_autopilot():
    from src.commander import bridge as commander_bridge
    from src.commander.v2.commands import V2_ACTION_REGISTRY
    registry = V2_ACTION_REGISTRY
    assert registry["bridge_route_add"].validate_params({"x": 250.0, "y": 240.0})
    assert not registry["bridge_route_add"].validate_params({"x": 250.0, "y": float("nan")})
    assert registry["bridge_route_pattern"].validate_params({"pattern": "zigzag"})
    assert not registry["bridge_route_pattern"].validate_params({"pattern": "spiral"})
    assert registry["bridge_route_clear"].validate_params({})
    for name in ("bridge_route_add", "bridge_route_pattern", "bridge_route_clear"):
        assert registry[name].stations == frozenset({"bridge"})
    game = _game()
    handlers = commander_bridge._V2_ACTION_HANDLERS
    assert handlers["bridge_route_add"](game, {"x": game.ship.x, "y": game.ship.y - 2.0}) == "ok"
    assert game.route.active and len(game.route.points) == 1
    assert handlers["bridge_route_pattern"](game, {"pattern": "zigzag"}) == "ok"
    assert game.route.kind == "zigzag"
    assert handlers["bridge_route_clear"](game, {}) == "ok"
    assert not game.route.active


# --- chart safety: shoal-water warnings and detours (1.3.62) ----------------

def _island(x, y):
    """A synthetic chart: 50 m everywhere but a 2 x 2 NM island at 10,10."""
    return 0.0 if 9.0 <= x <= 11.0 and 9.0 <= y <= 11.0 else 50.0


def test_leg_hazard_and_detour_on_a_synthetic_chart():
    assert route_model.leg_hazard(_island, 0.0, 0.0, 5.0, 0.0, 11.0) is None
    t = route_model.leg_hazard(_island, 5.0, 10.0, 15.0, 10.0, 11.0)
    assert t is not None and 0.35 <= t <= 0.4           # enters the island at x = 9
    detour = route_model.plan_detour(_island, 5.0, 10.0, 15.0, 10.0, 11.0, 100.0)
    assert detour
    legs = [(5.0, 10.0)] + detour + [(15.0, 10.0)]
    assert all(route_model.leg_hazard(_island, *a, *b, 11.0) is None
               for a, b in zip(legs, legs[1:]))
    # Same answer every time; an unsafe end point has no detour.
    assert route_model.plan_detour(_island, 5.0, 10.0, 15.0, 10.0, 11.0, 100.0) == detour
    assert route_model.plan_detour(_island, 5.0, 10.0, 10.0, 10.0, 11.0, 100.0) is None


def _legs_clear(game):
    points = [(game.ship.x, game.ship.y)] + game.route.remaining()
    return all(route_model.leg_hazard(game._route_depth, *a, *b, game._route_min_depth()) is None
               for a, b in zip(points, points[1:]))


def _open_water_game():
    """The ship in open water west of this start's coast, with a synthetic
    chart island 2.5 NM east of it (radius 0.6 NM) for the planner."""
    game = _game()
    ship = game.ship
    ship.x, ship.y = ship.x - 6.0, ship.y - 3.0
    ship.course = ship.target_course = 90.0
    assert game.world.hull_is_safe(ship.x, ship.y, ship.course, ship.hull_spec)
    cx, cy = ship.x + 2.5, ship.y

    def chart(x, y):
        return 0.0 if math.hypot(x - cx, y - cy) <= 0.6 else game.world.charted_depth_m(x, y)

    game._route_depth = chart
    return game, (cx, cy)


def _keys(game, count=4):
    return [entry.text.get("__u_jagd_i18n__") for entry in game.feed.entries[-count:]
            if isinstance(entry.text, dict)]


def test_a_waypoint_behind_an_island_gets_a_detour_and_a_warning():
    game, (cx, cy) = _open_water_game()
    target = (cx + 1.5, cy)
    assert game.add_route_waypoint(*target) == "ok"
    assert len(game.route.points) > 1 and game.route.points[-1] == target
    assert _legs_clear(game)
    assert "runtime.route.detour" in _keys(game)


def test_a_waypoint_on_the_island_is_warned_and_the_watch_stops_short():
    game, (cx, cy) = _open_water_game()
    game.order_speed(15.0)
    assert game.add_route_waypoint(cx, cy) == "ok"
    assert "runtime.route.hazard" in _keys(game)
    _run(game, 600.0)
    assert not game.route.active
    assert "runtime.route.hazard_stop" in _keys(game, 12)
    assert math.hypot(game.ship.x - cx, game.ship.y - cy) > 0.6
    assert abs(((game.ship.target_course - 270.0 + 180.0) % 360.0) - 180.0) < 5.0


def test_the_watch_adds_a_detour_to_a_route_loaded_across_the_island():
    game, (cx, cy) = _open_water_game()
    game.order_speed(15.0)
    # A leg straight across (as a save from before could hold it) is
    # replanned on the way.
    game.route.points = [(cx + 1.5, cy)]
    game.route.index = 0
    _run(game, 600.0)
    assert "runtime.route.replanned" in _keys(game, 12)
    assert game.route.active and _legs_clear(game)
    assert math.hypot(game.ship.x - cx, game.ship.y - cy) > 0.6
