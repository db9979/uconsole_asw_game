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
    _to_open_water(game)
    return game


def _to_open_water(game, clear_nm=9.0):
    """Put the ship where the chart is deep for ``clear_nm`` all round, so
    the route tests do not depend on the start's coast (deterministic)."""
    ship, world = game.ship, game.world

    def open_around(x, y):
        return all(world.charted_depth_m(x + r * math.sin(math.radians(b)),
                                         y - r * math.cos(math.radians(b))) > 40.0
                   for r in (0.0, clear_nm / 3, 2 * clear_nm / 3, clear_nm)
                   for b in range(0, 360, 15))

    for radius in range(0, 120, 3):
        for bearing in range(0, 360, 20):
            x = ship.x + radius * math.sin(math.radians(bearing))
            y = ship.y - radius * math.cos(math.radians(bearing))
            if open_around(x, y):
                ship.x, ship.y = x, y
                return
    raise AssertionError("no open water near the start")


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
    # North-west is open water (the ship is moved clear of the coast).
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
    # A short click east of the ship stays inside the open water around it.
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=3,
                                         pos=(rect.centerx + 8, rect.centery)))
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
    """The ship in open water, with a synthetic chart island 2.5 NM east of
    it (radius 0.6 NM) for the planner."""
    game = _game()
    ship = game.ship
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


# --- chart path search through channels and around long coasts (1.3.74) -----

def _bay(x, y):
    """A synthetic chart: a C-shaped coast (walls 1 NM thick) around a bay
    open to the south; its mouth is a 1.5 NM channel far from the leg."""
    inside_box = 10.0 <= x <= 30.0 and 10.0 <= y <= 30.0
    in_bay = 11.0 < x < 29.0 and 11.0 < y < 29.0
    in_mouth = 19.25 <= x <= 20.75 and y >= 29.0
    if inside_box and not (in_bay or in_mouth):
        return 0.0
    return 50.0


def test_the_path_search_finds_the_channel_the_stand_off_detour_misses():
    start, end = (20.0, 5.0), (20.0, 20.0)          # outside north -> inside the bay
    assert route_model.plan_detour(_bay, *start, *end, 11.0, 100.0) is None
    path = route_model.find_path(_bay, *start, *end, 11.0, 100.0)
    assert path, "the path search should find the way round through the mouth"
    legs = [start] + path + [end]
    assert all(route_model.leg_hazard(_bay, *a, *b, 11.0) is None
               for a, b in zip(legs, legs[1:]))
    assert any(y > 29.0 for _, y in path)            # it goes out round the south side
    assert len(path) <= route_model.MAX_ROUTE_POINTS
    # Deterministic, and plan_leg falls back to it.
    assert route_model.find_path(_bay, *start, *end, 11.0, 100.0) == path
    assert route_model.plan_leg(_bay, *start, *end, 11.0, 100.0) == path
    # A closed bay has no way in.
    closed = lambda x, y: 0.0 if 19.0 <= x <= 21.0 and y >= 29.0 and y <= 30.0 else _bay(x, y)
    assert route_model.find_path(closed, *start, *end, 11.0, 100.0) is None
    assert route_model.plan_leg(closed, *start, *end, 11.0, 100.0) is None


def test_the_path_search_takes_a_long_coast_in_a_few_turning_points():
    def coast(x, y):                                   # a 60 NM wall with one end
        return 0.0 if 49.0 <= x <= 51.0 and y <= 60.0 else 50.0
    start, end = (40.0, 30.0), (60.0, 30.0)
    assert route_model.plan_detour(coast, *start, *end, 11.0, 100.0) is None
    path = route_model.plan_leg(coast, *start, *end, 11.0, 100.0)
    assert path and len(path) <= 4
    legs = [start] + path + [end]
    assert all(route_model.leg_hazard(coast, *a, *b, 11.0) is None
               for a, b in zip(legs, legs[1:]))


def test_a_waypoint_across_a_real_coast_is_routed_by_the_game():
    game = _game()
    size = float(game.world.size_nm)
    minimum = game._route_min_depth()
    ship = game.ship
    # Find a chart point on the far side of land, due some bearing from the ship.
    target = None
    for course in range(0, 360, 15):
        for distance in (15.0, 25.0, 40.0):
            x = ship.x + distance * math.sin(math.radians(course))
            y = ship.y - distance * math.cos(math.radians(course))
            if not (1.0 <= x <= size - 1.0 and 1.0 <= y <= size - 1.0):
                continue
            if game._route_depth(x, y) < minimum + 20.0:
                continue
            if route_model.leg_hazard(game._route_depth, ship.x, ship.y, x, y, minimum) is None:
                continue
            target = (x, y)
            break
        if target:
            break
    assert target is not None
    assert game.add_route_waypoint(*target) == "ok"
    if len(game.route.points) > 1:
        assert _legs_clear(game)
        assert "runtime.route.detour" in _keys(game)
    else:
        assert "runtime.route.hazard" in _keys(game)
