"""Boat missions: scenarios whose objective belongs to the submarine.

``breakthrough``: reach a goal area beyond the frigate's start, seen from the
boat's start. ``recon``: sight the frigate through the periscope and get a
situation report off by radio while it is in sight. The frigate wins by
sinking the boat or by holding out to the time limit.

The goal is a pure function of the scenario's frigate start, the boat's saved
start position and the world, so it needs no saved state; mission
adjudication may read the boat's true position like every other end check.
"""

from __future__ import annotations

import math

from src.core import config
from src.core.i18n import message
from src.sonar.platforms import OWNSHIP_TARGET_ID

MODES = ("breakthrough", "recon")


def mode(game):
    """``breakthrough``, ``recon`` or None for a frigate mission."""
    if getattr(game, "custom_mission_definition", None) is not None:
        return None
    value = getattr(game.mission, "win_mode", None)
    return value if value in MODES else None


def target_sub(game):
    """The boat the mission belongs to: the crewed one, else the first hostile."""
    boat = getattr(game, "_opfor", None)
    if boat is not None and boat.sub in game.subs:
        return boat.sub
    hostile = sorted((sub for sub in game.subs if sub.side == "hostile"),
                     key=lambda sub: sub.id)
    return hostile[0] if hostile else None


def _water(game, x, y) -> bool:
    size = float(game.world.size_nm)
    return (5.0 <= x <= size - 5.0 and 5.0 <= y <= size - 5.0
            and not game.world.on_land(x, y)
            and game.world.depth_m(x, y) >= config.BOAT_GOAL_MIN_DEPTH_M)


def goal(game):
    """The breakthrough goal ``{x, y, radius_nm}`` or None."""
    if mode(game) != "breakthrough":
        return None
    sub = target_sub(game)
    start = config.SCENARIOS.get(game.scenario_key, {}).get("ship_start")
    if sub is None or start is None:
        return None
    key = (game.seed, game.scenario_key, sub.id, tuple(sub.start_pos))
    cached = getattr(game, "_boat_goal_cache", None)
    if cached is not None and cached[0] == key:
        return cached[1]
    sx, sy = sub.start_pos
    fx, fy = start
    bearing = math.degrees(math.atan2(fx - sx, -(fy - sy))) % 360.0
    point = None
    for distance in (config.BOAT_GOAL_BEYOND_NM, config.BOAT_GOAL_BEYOND_NM * 1.5,
                     config.BOAT_GOAL_BEYOND_NM * 0.5):
        for delta in (0.0, 20.0, -20.0, 40.0, -40.0, 60.0, -60.0, 90.0, -90.0):
            rad = math.radians(bearing + delta)
            x = fx + distance * math.sin(rad)
            y = fy - distance * math.cos(rad)
            if _water(game, x, y):
                point = (x, y)
                break
        if point is not None:
            break
    if point is None:
        point = (fx, fy)
    result = dict(x=float(point[0]), y=float(point[1]),
                  radius_nm=config.BOAT_GOAL_RADIUS_NM)
    game._boat_goal_cache = (key, result)
    return result


def check(game) -> bool:
    """End a boat mission when it is decided; True when this module owns it."""
    kind = mode(game)
    if kind is None:
        return False
    sub = target_sub(game)
    if sub is None or sub.sunk or sub.state == "SINKING":
        game._end_mission(True, message("end.reason.targets_sunk"))
        return True
    if kind == "breakthrough":
        point = goal(game)
        if point is not None and math.hypot(sub.x - point["x"], sub.y - point["y"]) \
                <= point["radius_nm"]:
            game._end_mission(False, message("end.reason.boat_broke_through"))
            return True
    if game.mission_time >= game.mission.time_limit_s:
        game._end_mission(True, message("end.reason.boat_stopped" if kind == "breakthrough"
                                        else "end.reason.boat_report_denied"))
    return True


def frigate_in_sight(boat) -> bool:
    return any(row["target_id"] == OWNSHIP_TARGET_ID for row in boat.orders.sightings)


def report_sent(game, boat) -> None:
    """A situation report went out: with the frigate in sight it wins recon."""
    if (mode(game) == "recon" and not game.game_over and game.mission_result is None
            and boat.sub is target_sub(game) and frigate_in_sight(boat)):
        game._end_mission(False, message("end.reason.boat_reported"))


def objective(game, boat):
    """The boat's own mission line (its orders from HQ, own truth only)."""
    kind = mode(game)
    if boat.sub.sunk:
        return message("uboot.objective_lost")
    if kind == "breakthrough":
        point = goal(game)
        dx, dy = point["x"] - boat.sub.x, point["y"] - boat.sub.y
        return message("uboot.objective.breakthrough",
                       bearing=f"{math.degrees(math.atan2(dx, -dy)) % 360.0:03.0f}",
                       range=f"{math.hypot(dx, dy):.1f}")
    if kind == "recon":
        return message("uboot.objective.recon_sighted" if frigate_in_sight(boat)
                       else "uboot.objective.recon")
    return message("uboot.objective")
