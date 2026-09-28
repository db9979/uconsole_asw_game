"""The crewed boat's periscope attack computer.

Every stadimeter reading is a *mark*: the time and the target position it
implies (the boat's own position plus the measured bearing and range).  A
straight-line fit through a sighting's marks gives the target's course and
speed; with the torpedo's speed that becomes the intercept course, the lead
angle and the running time.  Everything here is the crew's estimate from
its own marks and own-ship truth, never the target's true state.

Marks live in ``crew.orders.tdc`` (``{ref: {"target_id", "marks"}}``,
saved) so a loaded game fires on the same solution.
"""

from __future__ import annotations

import math

from src.core import config


def _bearing(dx: float, dy: float) -> float:
    return math.degrees(math.atan2(dx, -dy)) % 360.0


def record_mark(boat, row, now: float) -> None:
    """A stadimeter reading on sighting ``row`` becomes a mark."""
    sub = boat.sub
    rad = math.radians(row["bearing"])
    x = sub.x + row["range_nm"] * math.sin(rad)
    y = sub.y - row["range_nm"] * math.cos(rad)
    tdc = boat.orders.tdc
    entry = tdc.get(row["ref"])
    if entry is None or entry["target_id"] != row["target_id"]:
        entry = tdc[row["ref"]] = dict(target_id=int(row["target_id"]), marks=[])
    marks = [mark for mark in entry["marks"] if mark[0] < now]
    marks.append([float(now), float(x), float(y)])
    entry["marks"] = marks[-config.UBOOT_TDC_MARKS_MAX:]
    prune(boat, now)


def prune(boat, now: float) -> None:
    """Drop marks out of the window and the oldest sightings over the bound."""
    tdc = boat.orders.tdc
    for ref in list(tdc):
        marks = [mark for mark in tdc[ref]["marks"]
                 if 0.0 <= now - mark[0] <= config.UBOOT_TDC_WINDOW_S]
        if marks:
            tdc[ref]["marks"] = marks
        else:
            del tdc[ref]
    if len(tdc) > config.UBOOT_TDC_TARGETS_MAX:
        newest = sorted(tdc, key=lambda ref: (tdc[ref]["marks"][-1][0], ref))
        for ref in newest[:len(tdc) - config.UBOOT_TDC_TARGETS_MAX]:
            del tdc[ref]


def solve(marks, now: float):
    """Least-squares course and speed through the marks, or None.

    Returns ``dict(x, y, course, speed_kn, marks, base_s, quality)`` with the
    target's estimated position at ``now``."""
    marks = [mark for mark in marks if 0.0 <= now - mark[0] <= config.UBOOT_TDC_WINDOW_S]
    if len(marks) < 2:
        return None
    base = marks[-1][0] - marks[0][0]
    if base < config.UBOOT_TDC_MIN_BASE_S:
        return None
    n = len(marks)
    mt = sum(mark[0] for mark in marks) / n
    mx = sum(mark[1] for mark in marks) / n
    my = sum(mark[2] for mark in marks) / n
    stt = sum((mark[0] - mt) ** 2 for mark in marks)
    vx = sum((mark[0] - mt) * (mark[1] - mx) for mark in marks) / stt
    vy = sum((mark[0] - mt) * (mark[2] - my) for mark in marks) / stt
    speed_kn = math.hypot(vx, vy) * 3600.0
    if speed_kn > config.UBOOT_TDC_MAX_SPEED_KN:
        return None
    x, y = mx + vx * (now - mt), my + vy * (now - mt)
    course = _bearing(vx, vy) if speed_kn >= 0.5 else 0.0
    quality = (min(1.0, base / config.UBOOT_TDC_GOOD_BASE_S)
               * min(1.0, 0.5 + 0.25 * (n - 2)))
    return dict(x=x, y=y, course=course, speed_kn=speed_kn if speed_kn >= 0.5 else 0.0,
                marks=n, base_s=base, quality=quality)


def intercept(solution, own_x: float, own_y: float, torpedo_kn: float):
    """``dict(course, lead_deg, run_s, range_nm, bearing)`` of a straight
    torpedo shot onto the solution, or None when it cannot catch the target."""
    dx, dy = solution["x"] - own_x, solution["y"] - own_y
    bearing = _bearing(dx, dy)
    rad = math.radians(solution["course"])
    speed = config.kn_to_nm_per_s(solution["speed_kn"])
    vx, vy = speed * math.sin(rad), -speed * math.cos(rad)
    torpedo = config.kn_to_nm_per_s(torpedo_kn)
    a = vx * vx + vy * vy - torpedo * torpedo
    b = 2.0 * (dx * vx + dy * vy)
    c = dx * dx + dy * dy
    if abs(a) < 1e-15:
        run = -c / b if b < 0.0 else None
    else:
        disc = b * b - 4.0 * a * c
        if disc < 0.0:
            return None
        roots = [(-b - math.sqrt(disc)) / (2.0 * a), (-b + math.sqrt(disc)) / (2.0 * a)]
        positive = [root for root in roots if root > 0.0]
        run = min(positive) if positive else None
    if run is None:
        return None
    px, py = dx + vx * run, dy + vy * run
    course = _bearing(px, py)
    lead = (course - bearing + 180.0) % 360.0 - 180.0
    return dict(course=course, lead_deg=lead, run_s=run, range_nm=math.hypot(px, py),
                bearing=bearing)


def torpedo_speed_kn(sub) -> float:
    return float(sub.enemy_torpedo_profile.speed_kn)


def solution_for_ref(boat, ref: str, now: float):
    entry = boat.orders.tdc.get(ref)
    return None if entry is None else solve(entry["marks"], now)


def solution_for_target(boat, target_id: int, now: float):
    """The freshest solution on a target the crew has marked (the sonar
    contact and the sighting of one target share its internal id)."""
    best = None
    for ref, entry in sorted(boat.orders.tdc.items()):
        if entry["target_id"] != target_id:
            continue
        solution = solve(entry["marks"], now)
        if solution is not None and (best is None or entry["marks"][-1][0] > best[0]):
            best = (entry["marks"][-1][0], solution)
    return None if best is None else best[1]


def shot(boat, solution):
    """``(bearing, range_nm)`` for ``command_fire``: the intercept course and
    the intercept point as the torpedo's datum, or None."""
    sub = boat.sub
    lead = intercept(solution, sub.x, sub.y, torpedo_speed_kn(sub))
    if lead is None or not 0.05 <= lead["range_nm"] <= 40.0:
        return None
    return lead["course"] % 360.0, lead["range_nm"]


def fire_on_solution(game, boat, solution):
    """Fire the boat's torpedo (or salvo) on an attack-computer solution."""
    if solution is None:
        return "uboot_no_solution"
    aim = shot(boat, solution)
    if aim is None:
        return "uboot_no_solution"
    return boat.sub.command_fire(aim[0], aim[1], now=game.sim_t,
                                 depth_m=boat.orders.torpedo_depth, salvo=boat.orders.salvo)


def fire_on_crosshair(game, boat):
    """Fire on the solution of the sighting under the periscope crosshair."""
    from src.core import opfor
    if not opfor.scope_available(boat):
        return "uboot_mast_down"
    row = opfor.sighting_in_crosshair(boat, game.sim_t)
    if row is None:
        return "uboot_no_sighting"
    return fire_on_solution(game, boat, solution_for_ref(boat, row["ref"], game.sim_t))


def summary(boat, ref: str, now: float):
    """Detached display values of a sighting's solution, or None."""
    solution = solution_for_ref(boat, ref, now)
    if solution is None:
        entry = boat.orders.tdc.get(ref)
        return None if entry is None else dict(marks=len(entry["marks"]), course=None,
                                               speed_kn=None, lead_deg=None, run_s=None,
                                               quality=0.0)
    sub = boat.sub
    lead = intercept(solution, sub.x, sub.y, torpedo_speed_kn(sub))
    return dict(marks=solution["marks"], course=solution["course"],
                speed_kn=solution["speed_kn"],
                lead_deg=None if lead is None else lead["lead_deg"],
                run_s=None if lead is None else lead["run_s"],
                quality=solution["quality"])
