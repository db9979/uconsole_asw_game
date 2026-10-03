"""The crewed boat's objective line reads bearing and range from the
dead-reckoned position (``boat_nav``), like the free patrol's HQ orders:
the line must not reveal the navigation error the GPS fix would clear."""

import math
import sys
from pathlib import Path

from src.core import boat_missions, boat_nav, custom_boat, mission_modes
from src.core.game import Game
from src.core.i18n import Translator, localize

sys.path.insert(0, str(Path(__file__).parent))
from test_custom_boat_missions import _boat_mission  # noqa: E402

ERROR = (2.5, -1.75)


def _boat_game(scenario, seed=61):
    game = Game(seed=seed, start_menu=False, audio_enabled=False, language="en")
    game.reset(seed, scenario)
    game.local_side = "uboot"
    game._update(0.05)
    assert game.opfor is not None
    return game, game.opfor


def _off_course(boat):
    boat.orders.nav[0], boat.orders.nav[1] = ERROR
    bx, by = boat_nav.position(boat)
    assert (bx, by) == (boat.sub.x + ERROR[0], boat.sub.y + ERROR[1])
    return bx, by


def _bearing_range(fx, fy, x, y):
    return (f"{math.degrees(math.atan2(x - fx, -(y - fy))) % 360.0:03.0f}",
            f"{math.hypot(x - fx, y - fy):.1f}")


def _text(value):
    return localize(value, Translator("en").t)


def test_breakthrough_line_uses_the_navigated_position():
    game, boat = _boat_game("s5_durchbruch")
    bx, by = _off_course(boat)
    point = boat_missions.goal(game)
    bearing, distance = _bearing_range(bx, by, point["x"], point["y"])
    true_bearing, true_distance = _bearing_range(boat.sub.x, boat.sub.y,
                                                 point["x"], point["y"])
    assert (bearing, distance) != (true_bearing, true_distance)
    assert _text(boat_missions.objective(game, boat)) == (
        f"Break through to the goal area: bearing {bearing}, {distance} NM")


def test_homecoming_line_uses_the_navigated_position():
    game, boat = _boat_game("s18_heimkehr")
    assert boat_missions.mode(game) == "homecoming"
    bx, by = _off_course(boat)
    point = mission_modes.goal(game, "homecoming")
    bearing, distance = _bearing_range(bx, by, point["x"], point["y"])
    assert _text(boat_missions.objective(game, boat)) == (
        f"Reach the home area: bearing {bearing}, {distance} NM")


def test_custom_reach_line_uses_the_navigated_position():
    game = Game(seed=903, start_menu=False, audio_enabled=False, language="en")
    game.local_side = "uboot"
    mission = _boat_mission("reach", limit=3600.0)
    mission["objective"]["reach"] = {"x": 300.0, "y": 240.0, "radius_nm": 2.0}
    assert game.start_custom_mission(mission)
    boat = game.claim_opfor_sub()
    bx, by = _off_course(boat)
    bearing, distance = _bearing_range(bx, by, 300.0, 240.0)
    text = _text(custom_boat.objective(game, boat))
    assert text.startswith(f"Reach the objective point: bearing {bearing}, {distance} nm")
