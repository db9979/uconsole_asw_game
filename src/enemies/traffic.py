"""Merchant traffic: shipping lanes, collision avoidance and alarm.

Cargo ships, tankers and passenger ships of the ambient traffic steam from
one destination to the next: the charted ports (the water off each charted
base) and the exits at the world's edge.  Every lane decision happens on a
fixed simulation tick (``STEP_S``) and is kept in fields the save already
holds, so nothing new is saved:

* ``turn_delta`` is the leg number (0 = not on a lane: work boats, fishing
  boats, convoys, tasked ships and mission units keep their own behaviour);
* ``turn_left`` is the time left for the leg before the ship gives up on an
  unreachable destination and heads for the next one;
* ``target_course`` is the course ordered at the last tick.

The destination of a leg is a stateless draw keyed by the seed, the ship's
saved sensor seed (entity ids differ between games in one process) and
the leg (``src/core/detrand.py``).  A lane ship gives way like a merchant
under the collision regulations: when another surface ship will pass closer
than ``CPA_NM`` and is head-on, crossing from starboard or being overtaken,
it alters course to starboard; any ship alters when the pass would be very
close.  A detonation within ``ALARM_NM`` makes lane ships turn away at full
speed for ``ALARM_S`` (``SurfaceShip._torpedo_evade_left``, saved).

The rules read only the positions, courses and speeds of surface ships
(what a bridge sees by eye, radar and AIS), never submarines.
"""

from __future__ import annotations

import math

from src.core import config, detrand

LANE_CATEGORIES = frozenset({"FRACHT", "TANKER", "PASSAGIER"})
STEP_S = 10.0             # a lane ship decides every 10 s of simulation time
ARRIVAL_NM = 5.0          # destination reached
LOOK_NM = 6.0             # other ships considered for a close pass
CPA_NM = 0.5              # closest point of approach that calls for action
CLOSE_CPA_NM = 0.25       # so close that even the stand-on ship alters
TCPA_MAX_S = 1200.0       # only passes within the next 20 minutes count
AVOID_DEG = 35.0          # alteration to starboard
ALARM_NM = 8.0            # a detonation this close alarms a lane ship
ALARM_S = 600.0           # it runs from the detonation this long
EDGE_MARGIN_NM = 8.0
EDGE_GATES = 8
MIN_LEG_S = 3600.0
MAX_LEG_S = 12 * 3600.0


def is_lane_ship(ship) -> bool:
    return (not ship.sunk and ship.doctrine == "surface_transit"
            and getattr(ship, "live_mmsi", None) is None and ship.turn_delta >= 1.0)


def destinations(world) -> list[tuple[float, float]]:
    """Charted ports and edge exits in water, in a stable order (cached)."""
    cached = getattr(world, "_traffic_destinations", None)
    if cached is not None:
        return cached
    size = float(world.size_nm)
    points = []
    coast = getattr(world, "coast", None)
    for base in sorted(getattr(coast, "airbases", ()) or (),
                       key=lambda item: str(item.get("id", ""))):
        x, y = world.nearest_water(float(base["x"]), float(base["y"]))
        if not world.on_land(x, y):
            points.append((float(x), float(y)))
    margin = min(EDGE_MARGIN_NM, size * 0.1)
    for index in range(EDGE_GATES):
        angle = math.tau * index / EDGE_GATES
        # The gate on the square's edge in this direction from the centre.
        dx, dy = math.sin(angle), -math.cos(angle)
        scale = (size * 0.5 - margin) / max(abs(dx), abs(dy))
        x, y = size * 0.5 + dx * scale, size * 0.5 + dy * scale
        if not world.on_land(x, y):
            points.append((x, y))
    try:
        world._traffic_destinations = points
    except AttributeError:
        pass
    return points


def destination(ship, seed: int, world):
    """Where ``ship`` is bound on its current leg (None without a choice)."""
    points = destinations(world)
    if len(points) < 2:
        return None
    leg = int(ship.turn_delta)
    cache = getattr(ship, "_lane_cache", None)
    if cache is not None and cache[0] == leg and cache[1] is world:
        return cache[2]

    def pick(number: int) -> int:
        return int(detrand.u01(seed, "lane-port", ship.sensor_seed, number) * len(points)) % len(points)

    index = pick(leg)
    if leg > 1 and index == pick(leg - 1):
        index = (index + 1) % len(points)
    point = points[index]
    ship._lane_cache = (leg, world, point)
    return point


def _bearing(x0: float, y0: float, x1: float, y1: float) -> float:
    return math.degrees(math.atan2(x1 - x0, -(y1 - y0))) % 360.0


def _leg_time(ship, point) -> float:
    distance = math.hypot(point[0] - ship.x, point[1] - ship.y)
    hours = distance / max(6.0, ship.target_speed)
    return config.clamp(hours * 3600.0 * 1.5 + 1800.0, MIN_LEG_S, MAX_LEG_S)


def assign_lane(ship, seed: int, world) -> None:
    """Put a freshly spawned merchant on its first leg (no RNG draws)."""
    if ship.profile.category not in LANE_CATEGORIES:
        return
    ship.turn_delta = 1.0
    point = destination(ship, seed, world)
    if point is None:
        ship.turn_delta = 0.0
        return
    ship.course = ship.target_course = _bearing(ship.x, ship.y, *point)
    ship.turn_left = _leg_time(ship, point)


def _velocity(course: float, speed: float) -> tuple[float, float]:
    rad = math.radians(course)
    return speed * math.sin(rad), -speed * math.cos(rad)


def _close_pass(ship, other, course: float):
    """(cpa_nm, tcpa_s, relative bearing of ``other``) if ``ship`` held
    ``course``, or None when the two are not closing."""
    dx, dy = other.x - ship.x, other.y - ship.y
    if dx * dx + dy * dy > LOOK_NM * LOOK_NM:
        return None
    ou, ov = _velocity(other.course, other.speed)
    su, sv = _velocity(course, ship.speed)
    ru, rv = (ou - su) / 3600.0, (ov - sv) / 3600.0   # NM per second
    closing = ru * ru + rv * rv
    if closing < 1e-12:
        return None
    tcpa = -(dx * ru + dy * rv) / closing
    if not 0.0 < tcpa <= TCPA_MAX_S:
        return None
    cpa = math.hypot(dx + ru * tcpa, dy + rv * tcpa)
    relative = config.angle_diff_deg(_bearing(ship.x, ship.y, other.x, other.y), course)
    return cpa, tcpa, relative


def _gives_way(ship, other, course: float, relative: float, cpa: float) -> bool:
    if cpa < CLOSE_CPA_NM:
        return True
    head_on = (abs(relative) <= 10.0
               and abs(config.angle_diff_deg(other.course, course + 180.0)) <= 15.0)
    crossing_from_starboard = 0.0 < relative <= 112.5
    overtaking = abs(relative) <= 30.0 and ship.speed > other.speed + 0.5
    return head_on or crossing_from_starboard or overtaking


def due(sim_t: float, dt: float) -> bool:
    """True on the update step that crosses a ``STEP_S`` boundary."""
    return math.floor(sim_t / STEP_S) != math.floor((sim_t - dt) / STEP_S)


def plan(ships, obstacles, seed: int, world) -> None:
    """Order course (and leg) for every lane ship; call when ``due``.

    ``obstacles`` are the other surface ships in a stable order (the
    frigate, warships and all civilians); a ship never avoids itself.
    """
    for ship in ships:
        if not is_lane_ship(ship) or ship._torpedo_evade_left > 0.0:
            continue
        point = destination(ship, seed, world)
        if point is None:
            continue
        if (ship.turn_left <= 0.0
                or math.hypot(point[0] - ship.x, point[1] - ship.y) <= ARRIVAL_NM):
            ship.turn_delta = float(int(ship.turn_delta) + 1)
            point = destination(ship, seed, world)
            ship.turn_left = _leg_time(ship, point)
        course = _bearing(ship.x, ship.y, *point)
        # Judged on the course to the destination, so the alteration is held
        # until the other ship is past and clear, then the lane is resumed.
        for other in obstacles:
            if other is ship or getattr(other, "sunk", False):
                continue
            found = _close_pass(ship, other, course)
            if found is None:
                continue
            cpa, _tcpa, relative = found
            if cpa < CPA_NM and _gives_way(ship, other, course, relative, cpa):
                course = (course + AVOID_DEG) % 360.0
                break
        ship.target_course = course


def alarm(ships, x: float, y: float) -> None:
    """A detonation at ``x, y``: lane ships close by run from it."""
    for ship in ships:
        if not is_lane_ship(ship):
            continue
        if math.hypot(ship.x - x, ship.y - y) > ALARM_NM:
            continue
        ship._torpedo_evade_left = ALARM_S
        ship._torpedo_threat_bearing = _bearing(ship.x, ship.y, x, y)
