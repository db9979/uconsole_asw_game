"""The AI boat's mission: an uncrewed boat pursues a boat mission's objective.

In scenarios 5 to 7 played from the frigate, the boat the mission belongs to
(``boat_missions.target_sub``) is run by the AI.  Its patrol leg is replaced by
a mission leg (``Submarine.mission_orders``: course, speed, depth), recomputed
every substep from the current state, so it needs no saved state; evasion,
lying in wait and the counter-attack on the frigate keep their priority.

- ``breakthrough``: transit to the goal area below the layer, passing wide
  of a frigate it holds near the leg.
- ``recon``: close the frigate's last known position (its own contact, else
  HQ's contact report as the radio room receives it, else its patrol area), come to periscope depth within sighting range and send
  the report once a periscope look (``scope_look``) has made the frigate
  out; the raised periscope is a mast the frigate's radar can see.
- ``convoy_attack``: lie in wait ahead of the convoy, abeam of its track,
  and fire one torpedo at a time at the nearest merchant within attack
  range; a convoy that has passed is chased on an intercept course.
- ``strait``: transit to the goal beyond the gate like the breakthrough;
  unhunted, it tucks in under a merchant passing the same way within
  ``BOAT_AI_SHADOW_NM`` and keeps its speed, hiding in its noise.
- ``swimmers``: transit to the zone off the coast below the layer, come up to
  swimmer depth ``BOAT_AI_SWIMMER_APPROACH_NM`` out and stop in the zone.
- ``escort``: as the convoy attack, against the zigzagging supply ship,
  waiting on its base course.

Every leg creeps (``BOAT_AI_CREEP_KN``) while the boat is hunted: a ping or
torpedo heard lately, or its own contact on the frigate close by.

Like the other AI, the boat may read the entities it attacks or sights
internally; nothing here reaches the frigate's picture.
"""

from __future__ import annotations

import math

from src.core import boat_missions, boat_radio, config, detrand
from src.physics import bioluminescence
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


def frigate_known(sub):
    """``(x, y)`` of the frigate from the boat's own fire-control contact, or None."""
    contact = sub.memory.get("contact")
    if contact is None or sub.memory.get("contact_age", float("inf")) > config.BOAT_AI_HUNTED_S:
        return None
    return contact["x"], contact["y"]


def hunted(sub) -> bool:
    """The boat heard a ping or a torpedo lately, or knows the frigate close."""
    if min(sub.memory.get("last_ping_age", float("inf")),
           sub.memory.get("last_torpedo_age", float("inf"))) <= config.BOAT_AI_HUNTED_S:
        return True
    known = frigate_known(sub)
    return known is not None and math.hypot(known[0] - sub.x,
                                            known[1] - sub.y) <= config.BOAT_AI_THREAT_NM


def pace(sub, speed: float) -> float:
    """Creep when hunted: a slow boat is a quiet boat."""
    return min(speed, config.BOAT_AI_CREEP_KN) if hunted(sub) else speed


def detour(sub, course: float, distance_nm: float, post=None) -> float:
    """Steer ``BOAT_AI_DETOUR_DEG`` off a leg that runs close past the known
    frigate, else past the guard ``post`` its orders name, turning away from
    its side."""
    known = frigate_known(sub) or post
    if known is None:
        return course
    bearing = _bearing(sub.x, sub.y, *known)
    off = config.angle_diff_deg(bearing, course)
    rng = math.hypot(known[0] - sub.x, known[1] - sub.y)
    if abs(off) >= 90.0 or rng > distance_nm + config.BOAT_AI_DETOUR_NM:
        return course
    if rng * abs(math.sin(math.radians(off))) > config.BOAT_AI_DETOUR_NM:
        return course
    return (course - math.copysign(config.BOAT_AI_DETOUR_DEG, off or 1.0)) % 360.0


def ambush_point(sub, ships, course=None, hold=None):
    """Where the boat waits for the convoy: ahead of it, abeam of its track on
    the boat's side; None once the convoy has passed the boat. ``course`` is
    the track (the lead ship's course by default). With ``hold`` (a point on
    the base track) the boat only closes that track sideways and lets the
    ships come to it, whatever their zigzag."""
    cx = sum(ship.x for ship in ships) / len(ships)
    cy = sum(ship.y for ship in ships) / len(ships)
    rad = math.radians(ships[0].course if course is None else course)
    ux, uy = math.sin(rad), -math.cos(rad)
    rx, ry = sub.x - cx, sub.y - cy
    if rx * ux + ry * uy < 0.0:
        return None
    ahead, abeam = config.BOAT_AI_AMBUSH_AHEAD_NM, config.BOAT_AI_AMBUSH_ABEAM_NM
    if hold is not None:
        hx, hy = sub.x - hold[0], sub.y - hold[1]
        side = 1.0 if hx * -uy + hy * ux >= 0.0 else -1.0
        along = hx * ux + hy * uy
        abeam = config.BOAT_AI_ESCORT_ABEAM_NM
        return (hold[0] + along * ux - side * abeam * uy,
                hold[1] + along * uy + side * abeam * ux)
    side = 1.0 if rx * -uy + ry * ux >= 0.0 else -1.0
    return cx + ahead * ux - side * abeam * uy, cy + ahead * uy + side * abeam * ux


def orders(game, sub):
    """The mission leg ``(course, speed, depth)`` or None."""
    from src.core import mission_modes
    kind = boat_missions.mode(game)
    if kind in mission_modes.MODES and kind not in boat_missions.SHIP_MODES:
        return mission_modes.ai_orders(game, sub, kind)
    if kind == "breakthrough":
        point = boat_missions.goal(game)
        if point is None:
            return None
        distance = math.hypot(point["x"] - sub.x, point["y"] - sub.y)
        # The orders name the passage the frigate guards (its patrol area).
        start = config.SCENARIOS.get(game.scenario_key, {}).get("ship_start")
        post = None if start is None else (float(start[0]), float(start[1]))
        course = detour(sub, _bearing(sub.x, sub.y, point["x"], point["y"]), distance, post)
        return (_course(game, sub, course), pace(sub, config.BOAT_AI_TRANSIT_KN),
                _deep(game, sub))
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
        return (_course(game, sub, _bearing(sub.x, sub.y, px, py)),
                max(config.BOAT_AI_CREEP_KN, pace(sub, speed)), _deep(game, sub))
    if kind == "strait":
        return _strait_leg(game, sub)
    if kind == "swimmers":
        return _swimmer_leg(game, sub)
    if kind in boat_missions.SHIP_MODES:
        ships = convoy_ships(game)
        if not ships:
            return None
        track = (boat_missions.escort_base_course(game.world, game.scenario_key)
                 if kind == "escort" else None)
        target = min(ships, key=lambda ship: (math.hypot(ship.x - sub.x, ship.y - sub.y),
                                              ship.id))
        distance = math.hypot(target.x - sub.x, target.y - sub.y)
        if distance <= attack_nm(game):
            # Turn the tubes on the target and creep in.
            return (_bearing(sub.x, sub.y, target.x, target.y),
                    config.BOAT_AI_PERISCOPE_KN, _deep(game, sub))
        wait = ambush_point(sub, ships, track, hold=(boat_missions.escort_origin(game)
                                                     if kind == "escort" else None))
        if wait is not None:
            # Ahead of the convoy: lie in wait abeam of its track, quietly.
            gap = math.hypot(wait[0] - sub.x, wait[1] - sub.y)
            if gap <= config.BOAT_AI_AMBUSH_ARRIVE_NM:
                return (_course(game, sub, _bearing(sub.x, sub.y, target.x, target.y)),
                        config.BOAT_AI_WAIT_KN, _deep(game, sub))
            return (_course(game, sub, _bearing(sub.x, sub.y, *wait)),
                    pace(sub, config.BOAT_AI_TRANSIT_KN), _deep(game, sub))
        speed = closing_kn(sub, target.speed)
        cx = sum(ship.x for ship in ships) / len(ships)
        cy = sum(ship.y for ship in ships) / len(ships)
        cx, cy = lead(sub, cx, cy, target.course, target.speed, speed)
        course = _bearing(sub.x, sub.y, cx, cy)
        return _course(game, sub, course), speed, _deep(game, sub)
    return None


def shadow_ship(game, sub, heading: float):
    """A merchant passing the strait the boat's way within
    ``BOAT_AI_SHADOW_NM`` it can hide under, or None."""
    best = None
    for ship in game.civilians:
        if ship.sunk or abs(config.angle_diff_deg(ship.course, heading)) > 60.0:
            continue
        distance = math.hypot(ship.x - sub.x, ship.y - sub.y)
        if distance > config.BOAT_AI_SHADOW_NM:
            continue
        if ship.speed > sub.motion.maximum_speed_kn - 1.0:
            continue
        key = (distance, ship.id)
        if best is None or key < best[0]:
            best = (key, ship)
    return None if best is None else best[1]


def _strait_leg(game, sub):
    point = boat_missions.goal(game)
    if point is None:
        return None
    distance = math.hypot(point["x"] - sub.x, point["y"] - sub.y)
    heading = _bearing(sub.x, sub.y, point["x"], point["y"])
    ship = None if hunted(sub) else shadow_ship(game, sub, heading)
    if ship is not None:
        # Tuck in close astern of it and keep its speed, below the layer.
        rad = math.radians(ship.course)
        ax = ship.x - config.BOAT_AI_SHADOW_ASTERN_NM * math.sin(rad)
        ay = ship.y + config.BOAT_AI_SHADOW_ASTERN_NM * math.cos(rad)
        gap = math.hypot(ax - sub.x, ay - sub.y)
        speed = ship.speed + (2.0 if gap > 0.3 else 0.0)
        return (_course(game, sub, _bearing(sub.x, sub.y, ax, ay)),
                min(speed, sub.motion.maximum_speed_kn), _deep(game, sub))
    course = detour(sub, heading, distance)
    return (_course(game, sub, course), pace(sub, config.BOAT_AI_STEALTH_KN),
            _deep(game, sub))


def _swimmer_leg(game, sub):
    point = boat_missions.goal(game)
    if point is None:
        return None
    distance = math.hypot(point["x"] - sub.x, point["y"] - sub.y)
    heading = _bearing(sub.x, sub.y, point["x"], point["y"])
    shallow = config.SWIMMER_DEPTH_M - 3.0
    if distance <= point["radius_nm"] * 0.5:
        # In the zone: stop at swimmer depth for the lock-out.
        return heading, 0.0, shallow
    if distance <= config.BOAT_AI_SWIMMER_APPROACH_NM:
        # The last miles straight in, slow and shallow.
        return heading, config.BOAT_AI_PERISCOPE_KN, shallow
    course = detour(sub, heading, distance)
    return (_course(game, sub, course), pace(sub, config.BOAT_AI_STEALTH_KN),
            _deep(game, sub))


def steer(game) -> None:
    """Set every boat's mission leg for this substep (None when it has none)."""
    mission_boat = boat(game)
    kind = boat_missions.mode(game)
    guarded = kind in boat_missions.GUARDED_MODES
    snap = kind in boat_missions.SNAP_MODES
    for sub in game.subs:
        sub.mission_orders = orders(game, sub) if sub is mission_boat else None
        sub.mission_guarded = guarded and sub is mission_boat
        sub.mission_snap = snap and sub is mission_boat
        # Scenario 13 is peacetime: no AI boat fires.
        sub.mission_peace = kind == "trail"


def _window(game, period: float) -> bool:
    return math.floor(game.sim_t / period) != math.floor((game.sim_t - CADENCE_S) / period)


def _torpedo_running(game, sub) -> bool:
    return bool(sub.pending_torpedoes) or any(
        torpedo.launch_platform_id == sub.id and torpedo.state == "RUN"
        for torpedo in game.enemy_torpedoes)


def attack_nm(game) -> float:
    """How close the mission boat closes a convoy ship before it fires."""
    if boat_missions.mode(game) in ("escort", "ras"):
        return config.BOAT_AI_ESCORT_ATTACK_NM
    return config.BOAT_AI_CONVOY_ATTACK_NM


def attack(game, sub, ships=None) -> bool:
    """Fire one torpedo at the nearest merchant within attack range (the
    convoy's from farther out than a patrol raid's passing merchant)."""
    reach = attack_nm(game) if ships is None else config.BOAT_AI_ATTACK_NM
    near = [ship for ship in (convoy_ships(game) if ships is None else ships)
            if math.hypot(ship.x - sub.x, ship.y - sub.y)
            <= reach + config.BOAT_AI_PREFLOOD_MARGIN_NM]
    # Against the lone supply ship the boat fires even while it slips away
    # from a ping: one hit decides the mission.
    ready = sub.state == "PATROLLE" or (sub.state == "EVADE"
                                        and boat_missions.mode(game) in ("escort", "ras"))
    if (near and ready and sub.torpedoes_left > 0
            and (sub.weapon_battery is None or sub.weapon_battery.ready_count > 0)):
        # Flood the tubes quietly while closing; the shot waits for them.
        sub.ai_flood_tubes(quiet=True)
    ships = [ship for ship in near
             if math.hypot(ship.x - sub.x, ship.y - sub.y) <= reach]
    if (not ships or not ready or sub.torpedoes_left <= 0
            or _torpedo_running(game, sub) or not _window(game, config.BOAT_AI_FIRE_EVERY_S)):
        return False
    if sub.weapon_battery is not None and sub.weapon_battery.ready_count <= 0:
        return False
    if sub.ai_tube_left != 0.0:
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


def patrol_raiders(game) -> list:
    """AI submarines that may torpedo merchants in a frigate mission: every
    hostile, uncrewed patrol boat of a built-in frigate scenario (not a boat
    mission, a custom mission or a training lesson)."""
    if (boat_missions.mode(game) is not None
            or getattr(game, "custom_mission_definition", None) is not None
            or getattr(game, "training", None) is not None):
        return []
    return [sub for sub in game.subs
            if sub.side == "hostile" and not sub.sunk and not sub.manual
            and sub.state not in ("SINKING", "SUNK")]


def _unhunted(sub) -> bool:
    memory = sub.memory
    return (memory["last_ping_age"] > config.SUB_RAID_QUIET_S
            and memory["last_torpedo_age"] > config.SUB_RAID_QUIET_S)


def patrol_attack(game, sub) -> bool:
    """A patrol boat far from the frigate and not hunted torpedoes a merchant
    that passes close, on a random fraction of its fire windows and keeping
    torpedoes back for the frigate."""
    if (sub.torpedoes_left <= config.SUB_RAID_KEEP_TORPEDOES or not _unhunted(sub)
            or (not game.damage.ship_sunk and math.hypot(
                game.ship.x - sub.x, game.ship.y - sub.y) < config.SUB_RAID_FRIGATE_NM)
            or not _window(game, config.BOAT_AI_FIRE_EVERY_S)):
        return False
    window = int(math.floor(game.sim_t / config.BOAT_AI_FIRE_EVERY_S))
    # A raid already decided waits for its tubes instead of rolling again.
    if (not sub.ai_fire_pending and detrand.u01(
            game.seed, "sub-raid", int(sub.id), window) >= config.SUB_RAID_P):
        return False
    ships = [ship for ship in game.civilians if not ship.sunk]
    fired = attack(game, sub, ships)
    # Dry tubes with a merchant in reach: the flooding started, the shot waits.
    sub.ai_fire_pending = (not fired and sub.ai_tube_left != 0.0 and any(
        math.hypot(ship.x - sub.x, ship.y - sub.y) <= config.BOAT_AI_ATTACK_NM
        for ship in ships))
    return fired


def scope_look(game, sub) -> float | None:
    """Seconds into the recon boat's current periscope look, or None while
    the periscope is down (deep, another mission, or between looks)."""
    if (sub.manual or sub.sunk or sub.depth > MAST_DEPTH_M
            or boat_missions.mode(game) != "recon" or boat(game) is not sub):
        return None
    cycle = config.BOAT_AI_SCOPE_CYCLE_S
    phase = detrand.u01(game.seed, "sub-scope-phase", int(sub.id)) * cycle
    into = (game.sim_t + phase) % cycle
    return into if into < config.BOAT_AI_SCOPE_LOOK_S else None


def frigate_sighted(game, sub) -> bool:
    """The raised periscope has swept past the frigate and made it out:
    within ``BOAT_AI_SIGHT_NM``, clear of land and above the optics'
    contrast threshold at the periscope's eye height (the lookout's model:
    light, moon, visibility and sea)."""
    into = scope_look(game, sub)
    if into is None or game.damage.ship_sunk:
        return False
    ship = game.ship
    distance = math.hypot(ship.x - sub.x, ship.y - sub.y)
    if distance > config.BOAT_AI_SIGHT_NM:
        return False
    relative = (_bearing(sub.x, sub.y, ship.x, ship.y) - sub.course) % 360.0
    if into < relative / 360.0 * config.BOAT_AI_SCOPE_SWEEP_S:
        return False
    from src.core.game_sim import LOOKOUT_MODEL
    glow = bioluminescence.wake_glow(game.world.glow(), "SURFACE", ship.speed)
    if LOOKOUT_MODEL.margin("SURFACE", distance, eye_m=config.UBOOT_SCOPE_EYE_HEIGHT_M,
                           glow=glow, **game._lookout_environment()) < 1.0:
        return False
    return not game.world.land_blocks_line(sub.x, sub.y, ship.x, ship.y)


def report(game, sub) -> bool:
    """With the frigate in sight, the AI's situation report wins recon."""
    if (game.game_over or game.mission_result is not None
            or not frigate_sighted(game, sub)):
        return False
    game._end_mission(False, message("end.reason.boat_reported"))
    return True


def update(game, dt: float) -> None:
    """The boat's weapons and radio on their cadence (after the hunters)."""
    if math.floor(game.sim_t / CADENCE_S) == math.floor((game.sim_t - dt) / CADENCE_S):
        return
    for raider in patrol_raiders(game):
        patrol_attack(game, raider)
    sub = boat(game)
    if sub is None:
        return
    kind = boat_missions.mode(game)
    if kind in boat_missions.SHIP_MODES:
        attack(game, sub)
    elif kind == "recon":
        report(game, sub)
    elif kind == "elint" and sub.depth <= MAST_DEPTH_M:
        # The recording complete, the AI's report goes out at once.
        from src.core import mission_modes
        mission_modes.elint_report(game)
