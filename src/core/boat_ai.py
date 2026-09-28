"""The AI boat's mission: an uncrewed boat pursues a boat mission's objective.

In scenarios 5 to 7 played from the frigate, the boat the mission belongs to
(``boat_missions.target_sub``) is run by the AI.  Its patrol leg is replaced by
a mission leg (``Submarine.mission_orders``: course, speed, depth), recomputed
every substep from the current state, so it needs no saved state; evasion,
lying in wait and the counter-attack on the frigate keep their priority.

- ``breakthrough``: transit to the goal area below the layer.
- ``recon``: close the frigate's last known position (its own contact, else
  HQ's contact report as the radio room receives it, else its patrol area), come to periscope depth within sighting range and send
  the report once the frigate is in sight there.
- ``convoy_attack``: run ahead of the convoy on an intercept course below the
  layer (faster than the convoy) and fire one torpedo at a time at the
  nearest merchant within attack range.

Like the other AI, the boat may read the entities it attacks or sights
internally; nothing here reaches the frigate's picture.
"""

from __future__ import annotations

import math

from src.core import boat_missions, boat_radio, config
from src.core.i18n import message
from src.sensors.platform import MAST_DEPTH_M, PlatformObservation

CADENCE_S = 2.0
PROBE_NM = 2.0                    # the leg looks this far ahead for land and shoals
HQ_REPORTS_BACK = 4              # the boat acts on HQ's report from this many broadcasts
DETOURS_DEG = (0.0, 30.0, -30.0, 60.0, -60.0, 90.0, -90.0, 135.0, -135.0)


def boat(game):
    """The AI-run mission boat, or None (no boat mission, crewed or sunk)."""
    if boat_missions.mode(game) is None:
        return None
    sub = boat_missions.target_sub(game)
    if sub is None or sub.sunk or sub.manual or sub.state in ("SINKING", "SUNK"):
        return None
    return sub


def _bearing(x0, y0, x1, y1) -> float:
    return math.degrees(math.atan2(x1 - x0, -(y1 - y0))) % 360.0


def _open(game, sub, course: float) -> bool:
    rad = math.radians(course)
    for step in (0.5, 1.0, PROBE_NM):
        x = sub.x + step * math.sin(rad)
        y = sub.y - step * math.cos(rad)
        if game.world.on_land(x, y) or game.world.depth_m(x, y) < config.BOAT_AI_MIN_WATER_M:
            return False
    return True


def _course(game, sub, course: float) -> float:
    """``course``, or the smallest detour around land and shoal water ahead."""
    for delta in DETOURS_DEG:
        heading = (course + delta) % 360.0
        if _open(game, sub, heading):
            return heading
    return course


def _deep(game, sub) -> float:
    return config.clamp(game.world.thermocline_depth_m(sub.x, sub.y)
                        + config.BOAT_AI_BELOW_LAYER_M, 40.0, sub.stype.max_depth_m * .8)


def recon_target(game, sub):
    """``(x, y, course, speed_kn)`` of the frigate as the boat knows it: its own
    contact, else HQ's latest contact report on it (the radio room's
    broadcasts), else its patrol area; None without either."""
    contact = sub.memory.get("contact")
    if contact is not None:
        return (contact["x"], contact["y"], contact["course"] or 0.0,
                contact["speed"] or 0.0)
    number = boat_radio.broadcast_number(game.sim_t)
    for back in range(HQ_REPORTS_BACK):
        report = boat_radio.hq_report(game, number - back)
        if report is not None:
            return report["x"], report["y"], report["course"], report["speed_kn"]
    start = config.SCENARIOS.get(game.scenario_key, {}).get("ship_start")
    return (float(start[0]), float(start[1]), 0.0, 0.0) if start is not None else None


def convoy_ships(game) -> list:
    return [ship for ship in boat_missions.convoy(game) if not ship.sunk]


def lead(sub, x, y, course, target_kn, speed_kn: float):
    """Where the boat at ``speed_kn`` meets a target at ``x, y`` making ``target_kn``."""
    vx = target_kn * math.sin(math.radians(course))
    vy = -target_kn * math.cos(math.radians(course))
    px, py = x, y
    for _ in range(3):
        hours = math.hypot(px - sub.x, py - sub.y) / max(speed_kn, 0.1)
        px, py = x + vx * hours, y + vy * hours
    return px, py


def closing_kn(sub, target_kn: float) -> float:
    """Transit speed, or faster than the target when it would run away."""
    return min(sub.motion.maximum_speed_kn,
               max(config.BOAT_AI_TRANSIT_KN, target_kn + config.BOAT_AI_CLOSING_KN))


def orders(game, sub):
    """The mission leg ``(course, speed, depth)`` or None."""
    kind = boat_missions.mode(game)
    if kind == "breakthrough":
        point = boat_missions.goal(game)
        if point is None:
            return None
        course = _bearing(sub.x, sub.y, point["x"], point["y"])
        return _course(game, sub, course), config.BOAT_AI_TRANSIT_KN, _deep(game, sub)
    if kind == "recon":
        known = recon_target(game, sub)
        if known is None:
            return None
        x, y, course, target_kn = known
        if math.hypot(x - sub.x, y - sub.y) <= config.BOAT_AI_SIGHT_NM:
            return (_course(game, sub, _bearing(sub.x, sub.y, x, y)),
                    config.BOAT_AI_PERISCOPE_KN, MAST_DEPTH_M - 3.0)
        speed = closing_kn(sub, target_kn)
        px, py = lead(sub, x, y, course, target_kn, speed)
        return _course(game, sub, _bearing(sub.x, sub.y, px, py)), speed, _deep(game, sub)
    if kind == "convoy_attack":
        ships = convoy_ships(game)
        if not ships:
            return None
        target = min(ships, key=lambda ship: (math.hypot(ship.x - sub.x, ship.y - sub.y),
                                              ship.id))
        distance = math.hypot(target.x - sub.x, target.y - sub.y)
        if distance <= config.BOAT_AI_ATTACK_NM:
            # Turn the tubes on the target and creep in.
            return (_bearing(sub.x, sub.y, target.x, target.y),
                    config.BOAT_AI_PERISCOPE_KN, _deep(game, sub))
        speed = closing_kn(sub, target.speed)
        cx = sum(ship.x for ship in ships) / len(ships)
        cy = sum(ship.y for ship in ships) / len(ships)
        cx, cy = lead(sub, cx, cy, target.course, target.speed, speed)
        course = _bearing(sub.x, sub.y, cx, cy)
        return _course(game, sub, course), speed, _deep(game, sub)
    return None


def steer(game) -> None:
    """Set every boat's mission leg for this substep (None when it has none)."""
    mission_boat = boat(game)
    for sub in game.subs:
        sub.mission_orders = orders(game, sub) if sub is mission_boat else None


def _window(game, period: float) -> bool:
    return math.floor(game.sim_t / period) != math.floor((game.sim_t - CADENCE_S) / period)


def _torpedo_running(game, sub) -> bool:
    return bool(sub.pending_torpedoes) or any(
        torpedo.launch_platform_id == sub.id and torpedo.state == "RUN"
        for torpedo in game.enemy_torpedoes)


def attack(game, sub) -> bool:
    """Fire one torpedo at the nearest merchant within attack range."""
    ships = [ship for ship in convoy_ships(game)
             if math.hypot(ship.x - sub.x, ship.y - sub.y) <= config.BOAT_AI_ATTACK_NM]
    if (not ships or sub.state != "PATROLLE" or sub.torpedoes_left <= 0
            or _torpedo_running(game, sub) or not _window(game, config.BOAT_AI_FIRE_EVERY_S)):
        return False
    if sub.weapon_battery is not None and sub.weapon_battery.ready_count <= 0:
        return False
    target = min(ships, key=lambda ship: (math.hypot(ship.x - sub.x, ship.y - sub.y), ship.id))
    bearing = _bearing(sub.x, sub.y, target.x, target.y)
    if sub.weapon_battery is not None:
        launcher = sub.runtime_catalog.launchers[sub.weapon_battery.launcher_key]
        centre = (sub.course + launcher.arc_center_deg) % 360.0
        if abs(config.angle_diff_deg(bearing, centre)) > launcher.arc_width_deg / 2.0:
            return False
    observation = PlatformObservation(
        track_id="MISSION", domain="sonar", source="SONAR",
        observer_x=sub.x, observer_y=sub.y, bearing=bearing,
        range_nm=math.hypot(target.x - sub.x, target.y - sub.y),
        x=float(target.x), y=float(target.y), course=float(target.course),
        speed_kn=float(target.speed), depth_m=None, quality=1.0, signal=0.0,
        last_seen=float(game.sim_t), bearing_uncertainty_deg=None,
        range_uncertainty_nm=None, depth_uncertainty_m=None, label=None)
    return sub._fire_salvo(observation, 1) > 0


def frigate_sighted(game, sub) -> bool:
    """At periscope depth with the frigate within sighting range."""
    return (sub.depth <= MAST_DEPTH_M and not game.damage.ship_sunk
            and math.hypot(game.ship.x - sub.x, game.ship.y - sub.y)
            <= min(config.BOAT_AI_SIGHT_NM, game.world.visibility_nm))


def report(game, sub) -> bool:
    """With the frigate in sight, the AI's situation report wins recon."""
    if (game.game_over or game.mission_result is not None or not frigate_sighted(game, sub)
            or not _window(game, config.BOAT_AI_REPORT_EVERY_S)):
        return False
    game._end_mission(False, message("end.reason.boat_reported"))
    return True


def update(game, dt: float) -> None:
    """The boat's weapons and radio on their cadence (after the hunters)."""
    if math.floor(game.sim_t / CADENCE_S) == math.floor((game.sim_t - dt) / CADENCE_S):
        return
    sub = boat(game)
    if sub is None:
        return
    kind = boat_missions.mode(game)
    if kind == "convoy_attack":
        attack(game, sub)
    elif kind == "recon":
        report(game, sub)
