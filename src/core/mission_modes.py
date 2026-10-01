"""Scenarios 11 to 20: eight more missions on the boat-mission frame.

``boat_missions`` owns the frame (one mission boat, ``mode``, setup, update,
end check, the crewed boat's objective line) and hands these modes over:

Frigate side (the frigate's objective):

- ``datum``: a merchant was just torpedoed at the nominal start. The boat
  starts beside the wreck and must slip out of the datum circle
  (``DATUM_ESCAPE_NM``); the frigate starts far off with the exact datum and
  must sink it first. The time limit is the boat's.
- ``trail``: peacetime, weapons tight on both sides. HQ hands over a foreign
  nuclear submarine ahead of the frigate. The frigate wins once its sonar
  picture has held the boat for ``TRAIL_GOAL_FRACTION`` of the time limit;
  the boat wins when it was out of contact for ``TRAIL_LOST_S`` at a stretch
  or at the time limit (save ``mission_progress``: ``count_s``, ``gap_s``).
- ``ras``: replenishment at sea. A tanker steams a straight course; the
  frigate starts low on fuel on its quarter and wins when the transfer
  alongside (the HQ task board's ``ras`` task, saved there) is done. The
  boat wins by sinking the tanker or at the time limit.
- ``rescue``: two life rafts of a ditched patrol aircraft drift near the
  nominal start (two ``sar`` tasks); the boat lies in wait near them. The
  frigate wins when both crews are aboard, the boat when one is lost or at
  the time limit. Sinking the boat alone does not end it.

Submarine side (the boat's objective):

- ``duel``: the boat seeks out the frigate and must sink it; the frigate
  must sink the boat, which wins the duel when still afloat at the time limit.
- ``homecoming``: the boat starts damaged (hull ``HOMECOMING_DAMAGE``, half
  a battery) and must reach its home area ``HOMECOMING_NM`` away; the
  frigate comes in on its flank.
- ``pickup``: in the combat swimmers' zone the boat takes an agent team
  aboard (like the swimmers leave: shallow, slow, ``PICKUP_HOLD_S``; save
  ``hold_s`` and ``phase``), then runs out to deep water.
- ``elint``: at periscope depth with the mast up, the boat records the
  hunters' radars within ``ELINT_RANGE_NM`` (``count_s`` emitter-seconds,
  ``flags`` the kinds heard) and wins by reporting them by radio.

Every placement is a pure function of the scenario's nominal start, the seed
and the world; draws use ``detrand`` or a local stream keyed by the seed.
Adjudication may read the boat's true position like every end check; the
frigate's own displays read only its task board, its sonar picture and
authored mission data (the datum, the coast section).
"""

from __future__ import annotations

import math
import random

from src.core import boat_missions, config, detrand, mission_geo
from src.core.i18n import message, raw_text
from src.sensors.platform import MAST_DEPTH_M

MODES = ("datum", "trail", "ras", "rescue", "duel", "homecoming", "pickup", "elint")
# Missions whose objective is the frigate's: the time limit is the boat's.
FRIGATE_MODES = ("datum", "trail", "ras", "rescue", "duel")
# Missions where the AI hunters get HQ's start report as their lead.
LEAD_MODES = ("datum", "trail", "ras", "rescue", "homecoming")
# Missions without HQ tasking beyond their own tasks.
OWN_TASK_MODES = ("ras", "rescue")
RESCUE_NAMES = ("BRAVO 1", "BRAVO 2")      # call signs of the two rafts
ELINT_BITS = (("surface", 1), ("air", 2), ("helo", 4), ("mpa", 8))

PROGRESS_FIELDS = frozenset({"hold_s", "count_s", "gap_s", "phase", "flags"})
PROGRESS_MAX_S = 1e6


def new_progress() -> dict:
    """Save ``mission_progress``: the running counters of scenarios 13, 19, 20."""
    return dict(hold_s=0.0, count_s=0.0, gap_s=0.0, phase=0, flags=0)


def valid_progress(value) -> bool:
    if not isinstance(value, dict) or set(value) != PROGRESS_FIELDS:
        return False
    for key in ("hold_s", "count_s", "gap_s"):
        item = value[key]
        if type(item) is not float or not math.isfinite(item) or not 0.0 <= item <= PROGRESS_MAX_S:
            return False
    return (type(value["phase"]) is int and value["phase"] in (0, 1)
            and type(value["flags"]) is int and 0 <= value["flags"] <= 15)


def _progress(game) -> dict:
    value = getattr(game, "mission_progress", None)
    if value is None:
        value = game.mission_progress = new_progress()
    return value


# --- geometry --------------------------------------------------------------------------

def _bearing(x0, y0, x1, y1) -> float:
    return math.degrees(math.atan2(x1 - x0, -(y1 - y0))) % 360.0


def _offset(x, y, angle_deg, distance):
    rad = math.radians(angle_deg)
    return x + distance * math.sin(rad), y - distance * math.cos(rad)


def _nominal(scenario_key):
    return boat_missions._nominal(scenario_key)


def scale_for(scenario_key, short: bool) -> float:
    """Start distances of the scenario: shorter in the short variant; a
    mission type may scale its full length too (``scale``)."""
    spec = config.MISSION_TYPES.get(config.SCENARIOS[scenario_key]["mission_type"], {})
    if not short:
        return float(spec.get("scale", 1.0))
    return float(spec.get("short_scale", config.SHORT_DISTANCE_SCALE))


def _scale(game) -> float:
    return boat_missions.distance_scale(game)


def _reach(world, x, y, angle, distance):
    """A point on open, reachable water about ``distance`` out on ``angle``
    (or the nearest turn of it); the nearest water as a last resort."""
    for delta in (0.0, 30.0, -30.0, 60.0, -60.0, 90.0, -90.0, 120.0, -120.0, 150.0,
                  -150.0, 180.0):
        point = mission_geo.walk(world, x, y, angle + delta,
                                 (distance, distance * 0.8, distance * 1.2, distance * 0.6))
        if point is not None:
            return point
    px, py = _offset(x, y, angle, distance)
    size = float(world.size_nm)
    return world.nearest_water(config.clamp(px, 5.0, size - 5.0),
                               config.clamp(py, 5.0, size - 5.0))


def centre(world, scenario_key):
    """The datum, the rafts' area or the tanker's start: the nominal start on water."""
    x, y = world.nearest_water(*_nominal(scenario_key))
    return float(x), float(y)


def base_course(world, scenario_key) -> float:
    """The scenario's course with clear water ahead (trail, tanker, homecoming)."""
    spec = config.SCENARIOS[scenario_key]
    return mission_geo.escort_course(world, centre(world, scenario_key),
                                     float(spec["ship_course"]))


def datum_radius(game) -> float:
    return config.DATUM_ESCAPE_NM * _scale(game)


def home(world, scenario_key, short: bool):
    """The homecoming boat's home area ``{x, y, radius_nm}``."""
    cx, cy = centre(world, scenario_key)
    distance = config.HOMECOMING_NM * scale_for(scenario_key, short)
    x, y = _reach(world, cx, cy, base_course(world, scenario_key), distance)
    return dict(x=float(x), y=float(y), radius_nm=config.BOAT_GOAL_RADIUS_NM)


def escape_point(game):
    """Deep water seaward of the pick-up zone ``{x, y, radius_nm}``."""
    zone = boat_missions._zone_of(game.world, game.scenario_key)
    key = ("pickup", game.seed, game.scenario_key, _scale(game))
    cached = getattr(game, "_pickup_goal_cache", None)
    if cached is not None and cached[0] == key:
        return cached[1]
    x, y = _reach(game.world, zone["x"], zone["y"], zone["seaward"],
                  config.PICKUP_ESCAPE_NM * _scale(game))
    result = dict(x=float(x), y=float(y), radius_nm=config.BOAT_GOAL_RADIUS_NM)
    game._pickup_goal_cache = (key, result)
    return result


def frigate_start(world, scenario_key, seed, short: bool = False):
    """``(x, y, course)`` of the frigate in these scenarios, else None."""
    kind = boat_missions.scenario_mode(scenario_key)
    if kind not in ("datum", "trail", "ras", "rescue", "homecoming"):
        return None
    scale = scale_for(scenario_key, short)
    cx, cy = centre(world, scenario_key)
    if kind == "datum":
        angle = 360.0 * detrand.u01(seed, "datum-frigate", 0)
        x, y = _reach(world, cx, cy, angle, config.DATUM_FRIGATE_NM * scale)
        return float(x), float(y), _bearing(x, y, cx, cy)
    if kind == "trail":
        return cx, cy, base_course(world, scenario_key)
    if kind == "ras":
        course = base_course(world, scenario_key)
        quarter = 180.0 + (detrand.u01(seed, "ras-quarter", 0) * 80.0 - 40.0)
        x, y = _reach(world, cx, cy, course + quarter, config.RAS_FRIGATE_NM)
        return float(x), float(y), course
    if kind == "rescue":
        angle = 360.0 * detrand.u01(seed, "rescue-frigate", 0)
        x, y = _reach(world, cx, cy, angle, config.RESCUE_FRIGATE_NM * scale)
        return float(x), float(y), _bearing(x, y, cx, cy)
    if kind == "homecoming":
        course = base_course(world, scenario_key)
        side = 90.0 if detrand.u01(seed, "home-flank", 0) < 0.5 else -90.0
        x, y = _reach(world, cx, cy, course + side, config.HOMECOMING_FRIGATE_NM)
        return float(x), float(y), _bearing(x, y, cx, cy)
    return None


def raft_points(game):
    """Where the two rafts went into the water (centre, and a spread off it)."""
    cx, cy = centre(game.world, game.scenario_key)
    angle = 360.0 * detrand.u01(game.seed, "rescue-spread", 0)
    second = game.world.nearest_water(*_offset(cx, cy, angle, config.RESCUE_SPREAD_NM))
    return (cx, cy), (float(second[0]), float(second[1]))


# --- setup ----------------------------------------------------------------------------

def setup(game, kind) -> None:
    """Place the mission's own units once the world is populated."""
    if kind == "datum":
        _setup_datum(game)
    elif kind == "trail":
        _setup_trail(game)
    elif kind == "ras":
        _setup_ras(game)
    elif kind == "rescue":
        _setup_rescue(game)
    elif kind == "homecoming":
        _setup_homecoming(game)
    elif kind == "pickup":
        boat_missions._setup_swimmers(game)
    elif kind == "elint":
        _setup_elint(game)
    if kind in OWN_TASK_MODES:
        # The mission is the task: HQ offers nothing else.
        game.tasking.next_offer_t = None


def _setup_datum(game) -> None:
    from src.enemies.civilian import CivilianShip
    cx, cy = centre(game.world, game.scenario_key)
    rng = random.Random(game.seed * 7907 + 401)
    ship = CivilianShip(cx, cy, rng=rng,
                        profile=game.runtime_catalog.pick_surface(rng, hostile=False),
                        side="neutral", doctrine="surface_transit",
                        runtime_catalog=game.runtime_catalog)
    ship.speed = ship.target_speed = 0.0
    game.civilians.append(ship)
    game.mission_units["datum-1"] = int(ship.id)
    ship.hit(config.BOAT_CONVOY_WARHEAD)
    angle = 360.0 * detrand.u01(game.seed, "datum-boat", 0)
    x, y = game.world.nearest_water(*_offset(cx, cy, angle, config.DATUM_BOAT_NM))
    boat_missions._place_boat(game, x, y, angle)


def _setup_trail(game) -> None:
    course = base_course(game.world, game.scenario_key)
    side = detrand.u01(game.seed, "trail-side", 0) * 2.0 - 1.0
    ahead = config.TRAIL_START_NM
    x, y = _offset(game.ship.x, game.ship.y, course, ahead)
    x, y = _offset(x, y, course + 90.0, side)
    x, y = game.world.nearest_water(x, y)
    boat_missions._place_boat(game, x, y, course)


def _setup_ras(game) -> None:
    from src.enemies.civilian import CivilianShip
    course = base_course(game.world, game.scenario_key)
    x, y = centre(game.world, game.scenario_key)
    rng = random.Random(game.seed * 7907 + 503)
    ship = CivilianShip(x, y, rng=rng, side="friendly", doctrine="surface_transit",
                        profile=game.runtime_catalog.surfaces[config.TASK_RAS_PROFILE],
                        runtime_catalog=game.runtime_catalog)
    ship.course = ship.target_course = course
    ship.speed = ship.target_speed = min(config.TASK_RAS_SPEED_KN, ship.speed_cap_kn)
    ship.turn_left = game.mission.time_limit_s + 3600.0
    game.civilians.append(ship)
    game.mission_units["supply-1"] = int(ship.id)
    game.ship.fuel_kg = config.RAS_FUEL_START * game.ship.fuel_capacity_kg
    boat_missions._station_boat_ahead(game, course, (ship.x, ship.y), config.RAS_BOAT_AHEAD_NM)


def _setup_rescue(game) -> None:
    cx, cy = centre(game.world, game.scenario_key)
    toward = _bearing(cx, cy, game.ship.x, game.ship.y)
    angle = toward + (detrand.u01(game.seed, "rescue-boat", 0) * 160.0 - 80.0)
    x, y = game.world.nearest_water(*_offset(cx, cy, angle,
                                             config.RESCUE_BOAT_NM * _scale(game)))
    boat_missions._place_boat(game, x, y, angle + 180.0)


def _setup_homecoming(game) -> None:
    cx, cy = centre(game.world, game.scenario_key)
    boat_missions._place_boat(game, cx, cy, base_course(game.world, game.scenario_key))
    sub = boat_missions.target_sub(game)
    if sub is None:
        return
    sub.damage = max(sub.damage, config.HOMECOMING_DAMAGE)
    if sub.endurance is not None:
        sub.endurance.battery_kwh = (config.HOMECOMING_BATTERY
                                     * sub.endurance.profile.battery_capacity_kwh)


def _setup_elint(game) -> None:
    angle = 360.0 * detrand.u01(game.seed, "elint-boat", 0)
    x, y = _reach(game.world, game.ship.x, game.ship.y, angle,
                  config.ELINT_START_NM * _scale(game))
    boat_missions._place_boat(game, x, y, _bearing(x, y, game.ship.x, game.ship.y))


# --- the mission's own tasks (replenishment, rescue) ----------------------------------

def _add_task(game, kind: str, **fields):
    """File and accept one of the mission's own HQ tasks (deadline: the time limit)."""
    base = dict(kind=kind, state="offered", offered_t=game.sim_t,
                respond_by_t=game.sim_t + config.TASK_RESPONSE_S,
                deadline_t=None, ended_t=None, course=None, speed_kn=None,
                report_t=game.sim_t, name=None, persons=0, target_id=None,
                true_x=None, true_y=None, progress=0.0, sighted=False,
                plot_id=None, verdict=None, points=0)
    task = game.tasking.add({**base, **fields})
    if game.accept_task(task["id"]) is not True:
        task["state"] = "active"
    task["deadline_t"] = float(game.mission.time_limit_s)
    return task


def mission_tasks(game, kind: str) -> list:
    return [task for task in game.tasking.tasks if task["kind"] == kind]


def _ensure_tasks(game, kind) -> None:
    if kind == "ras" and not mission_tasks(game, "ras"):
        tanker = supply(game)
        if tanker is None or tanker.sunk:
            return
        _add_task(game, "ras", x=float(tanker.x), y=float(tanker.y), radius_nm=1.0,
                  course=float(tanker.course) % 360.0, speed_kn=float(tanker.speed),
                  name=str(tanker.name)[:24] or "-", target_id=int(tanker.id))
    elif kind == "rescue" and not mission_tasks(game, "sar"):
        sigma = config.TASK_SAR_REPORT_SIGMA_NM
        for index, (tx, ty) in enumerate(raft_points(game)):
            _add_task(game, "sar",
                      x=tx + sigma * detrand.normal(game.seed, "rescue-ex", index),
                      y=ty + sigma * detrand.normal(game.seed, "rescue-ey", index),
                      radius_nm=config.TASK_SAR_RADIUS_NM, name=RESCUE_NAMES[index],
                      persons=config.RESCUE_PERSONS[index], true_x=tx, true_y=ty)


def supply(game):
    """The tanker of the replenishment (sunk or not), or None."""
    return game.mission_entity("supply-1") if boat_missions.mode(game) == "ras" else None


# --- every substep -----------------------------------------------------------------------

def update(game, kind, dt: float) -> None:
    if game.game_over:
        return
    if kind in OWN_TASK_MODES:
        _ensure_tasks(game, kind)
    elif kind == "trail":
        _trail_contact(game, dt)
    elif kind == "pickup":
        _pickup_hold(game, dt)
    elif kind == "elint":
        _elint_listen(game, dt)


def trail_heard(game) -> bool:
    """The frigate's sonar picture heard the trailed boat lately."""
    sub = boat_missions.target_sub(game)
    if sub is None:
        return False
    contact = game.sonar.contacts.get(sub.id)
    return contact is not None and 0.0 <= game.sim_t - contact.last_seen <= config.TRAIL_FRESH_S


def trail_held(game) -> bool:
    """Contact is held: heard lately and located (a ping or TMA range) not long ago."""
    if not trail_heard(game):
        return False
    contact = game.sonar.contacts.get(boat_missions.target_sub(game).id)
    return (contact.range_seen is not None
            and 0.0 <= game.sim_t - contact.range_seen <= config.TRAIL_FIX_S)


def trail_goal_s(game) -> float:
    """Contact time the frigate must hold: a share of the time limit (the
    full length may ask a larger share, ``goal_fraction``)."""
    fraction = (config.TRAIL_GOAL_FRACTION if getattr(game, "short_mission", False)
                else (game.mission.spec or {}).get("goal_fraction", config.TRAIL_GOAL_FRACTION))
    return float(game.mission.time_limit_s) * float(fraction)


def trail_lost_s(game) -> float:
    return config.TRAIL_LOST_S * _scale(game)


def _trail_contact(game, dt: float) -> None:
    progress = _progress(game)
    if trail_held(game):
        progress["count_s"] = min(PROGRESS_MAX_S, progress["count_s"] + dt)
    # Lost means not even heard; a bare bearing keeps the trail alive.
    if trail_heard(game):
        progress["gap_s"] = 0.0
    else:
        progress["gap_s"] = min(PROGRESS_MAX_S, progress["gap_s"] + dt)


def _pickup_hold(game, dt: float) -> None:
    progress = _progress(game)
    if progress["phase"] != 0:
        return
    if boat_missions.in_lockout(game, boat_missions.target_sub(game)):
        progress["hold_s"] = min(config.PICKUP_HOLD_S, progress["hold_s"] + dt)
    else:
        progress["hold_s"] = 0.0
    if progress["hold_s"] >= config.PICKUP_HOLD_S:
        progress["phase"] = 1


def _mast_up(game, sub) -> bool:
    boat = getattr(game, "_opfor", None)
    if boat is not None and boat.sub is sub:
        return bool(boat.orders.mast and not sub.sunk and sub.depth <= MAST_DEPTH_M)
    return not sub.sunk and sub.depth <= MAST_DEPTH_M


def emitters(game) -> list:
    """``(bit, x, y)`` of every hunter radar transmitting now."""
    rows = []
    if not game.damage.ship_sunk:
        if game.surface_radar_on:
            rows.append((1, game.ship.x, game.ship.y))
        if game.air_radar_on:
            rows.append((2, game.ship.x, game.ship.y))
    helo = game.helo
    if helo.state == "AUF" and helo.radar_on:
        rows.append((4, helo.x, helo.y))
    mpa = game.mpa
    if mpa.airborne and mpa.radar_on:
        rows.append((8, mpa.x, mpa.y))
    return rows


def elint_goal_s(game) -> float:
    return config.ELINT_GOAL_S * _scale(game)


def elint_kinds(game) -> int:
    return bin(_progress(game)["flags"]).count("1")


def elint_complete(game) -> bool:
    progress = _progress(game)
    return (progress["count_s"] >= elint_goal_s(game)
            and elint_kinds(game) >= config.ELINT_EMITTERS)


def _elint_listen(game, dt: float) -> None:
    sub = boat_missions.target_sub(game)
    if sub is None or sub.state in ("SINKING", "SUNK") or not _mast_up(game, sub):
        return
    progress = _progress(game)
    for bit, x, y in emitters(game):
        if (math.hypot(x - sub.x, y - sub.y) <= config.ELINT_RANGE_NM
                and not game.world.land_blocks_line(sub.x, sub.y, x, y)):
            progress["count_s"] = min(PROGRESS_MAX_S, progress["count_s"] + dt)
            progress["flags"] |= bit


def elint_report(game) -> None:
    """A situation report with the recording complete wins the listening post."""
    if not game.game_over and game.mission_result is None and elint_complete(game):
        game._end_mission(False, message("end.reason.elint_reported"))


# --- end check ---------------------------------------------------------------------------

def check(game, kind, sub, gone: bool) -> bool:
    """End the mission when it is decided; always True (these modes own it)."""
    over = game.mission_time >= game.mission.time_limit_s
    if kind == "rescue":
        tasks = mission_tasks(game, "sar")
        if tasks and all(task["state"] == "done" for task in tasks):
            game._end_mission(True, message("end.reason.rescue_done"))
        elif any(task["state"] in ("failed", "declined") for task in tasks) or over:
            game._end_mission(False, message("end.reason.rescue_lost"))
        return True
    if gone:
        game._end_mission(True, message("end.reason.targets_sunk"))
        return True
    progress = _progress(game)
    if kind == "datum":
        cx, cy = centre(game.world, game.scenario_key)
        if math.hypot(sub.x - cx, sub.y - cy) > datum_radius(game):
            game._end_mission(False, message("end.reason.datum_escaped"))
            return True
    elif kind == "trail":
        if progress["count_s"] >= trail_goal_s(game):
            game._end_mission(True, message("end.reason.trail_held",
                                            minutes=int(progress["count_s"] // 60)))
            return True
        if progress["gap_s"] >= trail_lost_s(game):
            game._end_mission(False, message("end.reason.trail_lost",
                                             minutes=int(progress["gap_s"] // 60)))
            return True
    elif kind == "ras":
        tasks = mission_tasks(game, "ras")
        tanker = supply(game)
        if tasks and tasks[0]["state"] == "done":
            game._end_mission(True, message("end.reason.ras_done"))
            return True
        if tanker is not None and tanker.sunk:
            game._end_mission(False, message("end.reason.ras_tanker_sunk"))
            return True
    elif kind in ("homecoming", "pickup"):
        point = goal(game, kind)
        if (point is not None and (kind == "homecoming" or progress["phase"] == 1)
                and math.hypot(sub.x - point["x"], sub.y - point["y"]) <= point["radius_nm"]):
            game._end_mission(False, message("end.reason.boat_home" if kind == "homecoming"
                                             else "end.reason.agents_escaped"))
            return True
    if over:
        if kind == "trail":
            game._end_mission(False, message("end.reason.trail_short",
                                             minutes=int(progress["count_s"] // 60),
                                             goal=int(trail_goal_s(game) // 60)))
        else:
            game._end_mission(kind not in FRIGATE_MODES, message({
                "datum": "end.reason.datum_time", "ras": "end.reason.ras_time",
                "duel": "end.reason.duel_survived", "homecoming": "end.reason.boat_stopped",
                "pickup": "end.reason.agents_denied", "elint": "end.reason.elint_denied",
            }[kind]))
    return True


def goal(game, kind):
    """The boat's goal area for its chart, or None."""
    if kind == "homecoming":
        return home(game.world, game.scenario_key, getattr(game, "short_mission", False))
    if kind == "pickup":
        if _progress(game)["phase"] == 0:
            return boat_missions.zone(game)
        return escape_point(game)
    return None


def guard_area(game, kind):
    """What the frigate's orders give it: the datum circle."""
    if kind != "datum":
        return None
    cx, cy = centre(game.world, game.scenario_key)
    return dict(kind="circle", x=cx, y=cy, radius_nm=datum_radius(game),
                course=360.0 * detrand.u01(game.seed, "datum-sweep", 0),
                start=1.0, label="map.guard.datum")


# --- what the stations show ---------------------------------------------------------------

def _clock(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def boat_objective(game, boat, kind):
    """The crewed boat's own orders line (its own truth and orders only)."""
    sub = boat.sub
    if kind in ("homecoming", "pickup"):
        point = goal(game, kind)
        dx, dy = point["x"] - sub.x, point["y"] - sub.y
        params = dict(bearing=f"{math.degrees(math.atan2(dx, -dy)) % 360.0:03.0f}",
                      range=f"{math.hypot(dx, dy):.1f}")
        if kind == "homecoming":
            return message("uboot.objective.homecoming", **params)
        if _progress(game)["phase"] == 1:
            return message("uboot.objective.pickup_escape", **params)
        if math.hypot(dx, dy) <= point["radius_nm"]:
            left = max(0.0, config.PICKUP_HOLD_S - _progress(game)["hold_s"])
            return message("uboot.objective.pickup_hold" if boat_missions.in_lockout(game, sub)
                           else "uboot.objective.pickup_zone", left=_clock(left),
                           depth=int(config.SWIMMER_DEPTH_M),
                           speed=f"{config.SWIMMER_SPEED_KN:.1f}")
        return message("uboot.objective.pickup", **params)
    if kind == "elint":
        if elint_complete(game):
            return message("uboot.objective.elint_done")
        return message("uboot.objective.elint",
                       done=int(_progress(game)["count_s"] // 60),
                       goal=int(elint_goal_s(game) // 60),
                       kinds=elint_kinds(game), need=config.ELINT_EMITTERS)
    if kind == "datum":
        cx, cy = centre(game.world, game.scenario_key)
        left = max(0.0, datum_radius(game) - math.hypot(sub.x - cx, sub.y - cy))
        return message("uboot.objective.datum", range=f"{left:.1f}")
    if kind == "trail":
        return message("uboot.objective.trail")
    if kind == "ras":
        tanker = supply(game)
        return message("uboot.objective.ras",
                       name=raw_text(str(getattr(tanker, "name", "") or "-")))
    return message("uboot.objective." + kind)


def frigate_objective(game, kind):
    """The frigate's objective line (its task board and sonar picture only)."""
    if kind == "trail":
        return message("mission.objective.trail",
                       held=int(_progress(game)["count_s"] // 60),
                       goal=int(trail_goal_s(game) // 60))
    if kind == "ras":
        tasks = mission_tasks(game, "ras")
        percent = int(round(100.0 * tasks[0]["progress"])) if tasks else 0
        return message("mission.objective.ras", percent=percent)
    if kind == "rescue":
        tasks = mission_tasks(game, "sar")
        return message("mission.objective.rescue",
                       done=sum(1 for task in tasks if task["state"] == "done"),
                       total=len(RESCUE_NAMES))
    if kind == "datum":
        return message("mission.objective.datum", radius=f"{datum_radius(game):.0f}")
    return message("mission.objective." + kind)


def start_notice(game, kind):
    """HQ's start message for the datum and the trail (exact), else None."""
    from src.core import hunter
    sub = boat_missions.target_sub(game)
    if kind == "datum":
        x, y = centre(game.world, game.scenario_key)
        name = raw_text(str(getattr(game.mission_entity("datum-1"), "name", "") or "-"))
    elif kind == "trail" and sub is not None:
        x, y = sub.x, sub.y
        name = None
    else:
        return None
    bearing = _bearing(game.ship.x, game.ship.y, x, y)
    distance = math.hypot(x - game.ship.x, y - game.ship.y)
    hunter.set_hq_lead(game, bearing, distance)
    if kind == "datum":
        return message("runtime.hq.datum", name=name, bearing=f"{bearing:03.0f}",
                       range=f"{distance:.1f}", radius=f"{datum_radius(game):.0f}")
    return message("runtime.hq.trail", bearing=f"{bearing:03.0f}", range=f"{distance:.1f}",
                   course=f"{sub.course:03.0f}", speed=f"{sub.speed:.0f}")


def outcome(game, key):
    """The crewed boat's end title for these modes' reasons, or None."""
    return {"end.reason.boat_home": "home", "end.reason.agents_escaped": "picked_up",
            "end.reason.elint_reported": "elint", "end.reason.datum_escaped": "escaped",
            "end.reason.trail_lost": "shaken", "end.reason.trail_short": "shaken",
            "end.reason.datum_time": "survived", "end.reason.ras_time": "survived",
            "end.reason.ras_tanker_sunk": "supply_sunk",
            "end.reason.rescue_lost": "survived", "end.reason.duel_survived": "survived"}.get(key)


# --- the AI boat's legs (src/core/boat_ai.py) ---------------------------------------------

def ai_orders(game, sub, kind):
    """The mission leg ``(course, speed, depth)`` of the AI boat, or None."""
    from src.core import boat_ai
    deep = boat_ai._deep(game, sub)
    if kind == "datum":
        cx, cy = centre(game.world, game.scenario_key)
        away = (_bearing(cx, cy, sub.x, sub.y) if math.hypot(sub.x - cx, sub.y - cy) > 0.05
                else sub.course)
        left = datum_radius(game) - math.hypot(sub.x - cx, sub.y - cy)
        course = boat_ai.detour(sub, away, max(0.0, left))
        early = game.mission_time < config.DATUM_SPRINT_S
        speed = (config.DATUM_SPRINT_KN if early and not boat_ai.hunted(sub)
                 else boat_ai.pace(sub, config.BOAT_AI_STEALTH_KN))
        return boat_ai._course(game, sub, course), speed, deep
    if kind == "trail":
        # Trailed in peacetime, it works to shake the frigate off from the
        # start: a sprint on a new heading, then a quiet drift below the layer.
        window = int(math.floor(game.sim_t / config.TRAIL_LEG_S))
        weave = detrand.u01(game.seed, "trail-weave", window) * 2.0 - 1.0
        course = base_course(game.world, game.scenario_key) + weave * config.TRAIL_WEAVE_DEG
        into = game.sim_t - window * config.TRAIL_LEG_S
        speed = config.TRAIL_SPRINT_KN if into < config.TRAIL_SPRINT_S else config.TRAIL_DRIFT_KN
        return (boat_ai._course(game, sub, course % 360.0),
                min(speed, sub.motion.maximum_speed_kn), deep)
    if kind == "rescue":
        known = boat_ai.recon_target(game, sub)
        if known is not None and math.hypot(known[0] - sub.x,
                                            known[1] - sub.y) <= config.DUEL_CLOSE_NM:
            return _attack_leg(game, sub, known, deep)
        cx, cy = centre(game.world, game.scenario_key)
        toward = sub.start_pos if known is None else known[:2]
        wx, wy = _offset(cx, cy, _bearing(cx, cy, *toward), config.RESCUE_BOAT_NM * 0.7)
        if math.hypot(wx - sub.x, wy - sub.y) <= config.BOAT_AI_AMBUSH_ARRIVE_NM:
            return sub.course, config.BOAT_AI_WAIT_KN, deep
        return (boat_ai._course(game, sub, _bearing(sub.x, sub.y, wx, wy)),
                boat_ai.pace(sub, config.BOAT_AI_STEALTH_KN), deep)
    if kind == "duel":
        known = boat_ai.recon_target(game, sub)
        if known is None:
            return None
        x, y, course, target_kn = known
        if math.hypot(x - sub.x, y - sub.y) <= config.DUEL_CLOSE_NM:
            return _attack_leg(game, sub, known, deep)
        # It stalks quietly: a dived boat that runs is heard first.
        speed = config.BOAT_AI_STEALTH_KN
        px, py = boat_ai.lead(sub, x, y, course, target_kn, speed)
        return (boat_ai._course(game, sub, _bearing(sub.x, sub.y, px, py)),
                boat_ai.pace(sub, speed), deep)
    if kind == "homecoming" or (kind == "pickup" and _progress(game)["phase"] == 1):
        point = goal(game, kind)
        distance = math.hypot(point["x"] - sub.x, point["y"] - sub.y)
        course = boat_ai.detour(sub, _bearing(sub.x, sub.y, point["x"], point["y"]), distance)
        return (boat_ai._course(game, sub, course),
                boat_ai.pace(sub, config.BOAT_AI_TRANSIT_KN), deep)
    if kind == "pickup":
        return boat_ai._swimmer_leg(game, sub)
    if kind == "elint":
        return _elint_leg(game, sub, deep)
    return None


def _attack_leg(game, sub, known, deep):
    """Close a known frigate on a slant for bearing motion; the boat's own
    fire control (``Submarine._maybe_attack``) takes the shot."""
    from src.core import boat_ai
    side = 1.0 if math.floor(game.sim_t / 300.0) % 2 else -1.0
    bearing = _bearing(sub.x, sub.y, known[0], known[1])
    return (boat_ai._course(game, sub, (bearing + side * 30.0) % 360.0),
            config.BOAT_AI_PERISCOPE_KN, deep)


def _elint_leg(game, sub, deep):
    from src.core import boat_ai
    known = boat_ai.recon_target(game, sub)
    if known is None:
        return None
    x, y = known[0], known[1]
    distance = math.hypot(x - sub.x, y - sub.y)
    bearing = _bearing(sub.x, sub.y, x, y)
    if boat_ai.hunted(sub):
        return (boat_ai._course(game, sub, (bearing + 180.0) % 360.0),
                config.BOAT_AI_CREEP_KN, deep)
    if distance > config.ELINT_STANDOFF_NM + 3.0:
        return (boat_ai._course(game, sub, bearing),
                boat_ai.pace(sub, config.BOAT_AI_TRANSIT_KN), deep)
    if distance < config.ELINT_STANDOFF_NM - 3.0:
        return boat_ai._course(game, sub, (bearing + 180.0) % 360.0), 4.0, deep
    side = 1.0 if math.floor(game.sim_t / 900.0) % 2 else -1.0
    return (boat_ai._course(game, sub, (bearing + side * 90.0) % 360.0),
            config.BOAT_AI_PERISCOPE_KN, MAST_DEPTH_M - 3.0)


# --- the AI frigate's legs (src/core/hunter.py) -------------------------------------------

def frigate_leg(game, found):
    """``(course, speed)`` for the AI frigate in the replenishment, the rescue
    and the trail, or None to hunt as usual. Reads the task board's reported
    positions and the frigate's own contacts only."""
    from src.core import hunter
    kind = boat_missions.mode(game)
    ship = game.ship
    point = hunter.datum_point(game, found) if found is not None else None
    if kind == "trail":
        if found is None:
            return None
        bearing = _bearing(ship.x, ship.y, *point)
        side = 1.0 if math.floor(game.sim_t / hunter.CROSS_LEG_S) % 2 else -1.0
        if "x" not in found:
            # Close on a slant: bearing motion for the TMA, range for a ping.
            return found["bearing"] + side * 30.0, 16.0
        if math.hypot(point[0] - ship.x, point[1] - ship.y) > 2.5:
            return bearing, 16.0
        return bearing + side * 40.0, 10.0
    if kind == "ras":
        task = next((task for task in mission_tasks(game, "ras")
                     if task["state"] == "active"), None)
        if task is None:
            return None
        tx, ty = game.task_position(task)
        if point is not None and math.hypot(point[0] - tx, point[1] - ty) <= config.RAS_LEASH_NM:
            return None
        return _ras_station(game, tx, ty, task["course"], task["speed_kn"])
    if kind == "rescue":
        # The crews come first; the sonar and the tubes still fight the boat.
        raft = rescue_point(game)
        if raft is None:
            return None
        distance = math.hypot(raft[0] - ship.x, raft[1] - ship.y)
        bearing = _bearing(ship.x, ship.y, *raft)
        if distance > 1.0:
            return bearing, hunter.TRANSIT_KN
        if distance > 0.4:
            return bearing, 10.0
        return bearing, (3.0 if distance > 0.12 else 0.5)
    return None


def _ras_station(game, tx, ty, course, speed_kn):
    """Close the station on the tanker's port beam and keep it."""
    ship = game.ship
    sx, sy = _offset(tx, ty, course - 90.0, config.RAS_STATION_NM)
    distance = math.hypot(sx - ship.x, sy - ship.y)
    if distance > 1.5:
        px, py = sx, sy
        for _ in range(3):
            hours = math.hypot(px - ship.x, py - ship.y) / 20.0
            px, py = _offset(sx, sy, course, speed_kn * hours)
        return _bearing(ship.x, ship.y, px, py), 20.0
    ux, uy = math.sin(math.radians(course)), -math.cos(math.radians(course))
    along = (sx - ship.x) * ux + (sy - ship.y) * uy
    ax, ay = _offset(sx, sy, course, 0.5)
    return (_bearing(ship.x, ship.y, ax, ay),
            speed_kn + config.clamp(along * 15.0, -2.5, 6.0))


def rescue_point(game, flyer: bool = False):
    """The reported position of the raft the ship (nearest to it) or the
    helicopter (the other one, only while two are left) makes for, or None."""
    rows = [task for task in mission_tasks(game, "sar") if task["state"] == "active"]
    if not rows or (flyer and len(rows) < 2):
        return None
    ship = game.ship
    rows.sort(key=lambda row: (math.hypot(row["x"] - ship.x, row["y"] - ship.y), row["id"]))
    task = rows[-1] if flyer else rows[0]
    return task["x"], task["y"]
