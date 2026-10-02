"""The crewed submarine's navigation: dead reckoning and its route.

Dived, the boat knows its position only by dead reckoning (save v48
``crew.orders.nav``).  The navigated position drifts slowly away from the
true one: a steady set the log and gyro cannot see (``UBOOT_DR_DRIFT_KN``,
less on a nuclear boat with its inertial navigation) plus a small random
walk once a minute.  A GPS fix with the mast raised at periscope depth for
``UBOOT_GPS_FIX_S`` puts the navigated position back on the true one.

The error is own-ship data, never a fact about anyone else: it shifts the
crew's picture of the chart (coast, soundings, hazards, goals and HQ's
reports) against the boat and everything it measures itself.  The chart
check ahead and the route steer from the navigated position, so a stale
fix can lead the boat into water the chart says is clear.  Only a crewed
boat navigates this way; the AI boats are unchanged.

State: ``[error x, error y, s since fix, s of fix held, fixes]``; the draws
are counter based (``detrand``) and need nothing else saved.

The route (save v48 ``crew.orders.route``) is the frigate's autopilot model
(``src/ship/route.py``): waypoints on the chart the boat steers through from
its navigated position, or a zigzag or expanding-square search.
"""

from __future__ import annotations

import math

from src.core import config, detrand
from src.ship import route as route_model


def new_state() -> list:
    return [0.0, 0.0, 0.0, 0.0, 0]


def valid_state(value) -> bool:
    return (isinstance(value, list) and len(value) == 5
            and all(type(item) is float and math.isfinite(item) for item in value[:4])
            and all(abs(item) <= config.UBOOT_DR_ERROR_MAX_NM for item in value[:2])
            and 0.0 <= value[2] <= 1e9 and 0.0 <= value[3] <= config.UBOOT_GPS_FIX_S
            and type(value[4]) is int and 0 <= value[4] <= 10**6)


def _rate_kn(sub) -> float:
    """Drift of the navigated position: smaller with inertial navigation."""
    nuclear = sub.endurance is None
    return config.UBOOT_DR_DRIFT_KN * (config.UBOOT_DR_NUCLEAR_FACTOR if nuclear else 1.0)


def _drift(sub, fixes: int) -> tuple[float, float]:
    """The set since the last fix (direction and size drawn per fix)."""
    angle = detrand.phase(sub.sensor_seed, "boat_dr_set", fixes)
    size = _rate_kn(sub) * (0.5 + 0.5 * detrand.u01(sub.sensor_seed, "boat_dr_rate", fixes))
    return (config.kn_to_nm_per_s(size) * math.sin(angle),
            -config.kn_to_nm_per_s(size) * math.cos(angle))


def step(state: list, sub, dt: float, sim_t: float, gps_ok: bool) -> str | None:
    """Advance the dead reckoning; returns ``"gps_fix"`` on a new fix."""
    if dt <= 0.0 or sub.sunk:
        return None
    if gps_ok:
        before = state[3]
        state[3] = min(config.UBOOT_GPS_FIX_S, state[3] + dt)
        if state[3] >= config.UBOOT_GPS_FIX_S:
            # Fixed, and held on the true position while the mast stays up.
            fixes = state[4] + (1 if before < config.UBOOT_GPS_FIX_S else 0)
            state[:] = [0.0, 0.0, 0.0, config.UBOOT_GPS_FIX_S, min(10**6, fixes)]
            return "gps_fix" if before < config.UBOOT_GPS_FIX_S else None
    else:
        state[3] = 0.0
    state[2] = min(1e9, state[2] + dt)
    if sub.depth <= config.UBOOT_DR_SURFACE_M or getattr(sub.crew, "bottomed", False):
        # Awash the boat sees landmarks; on the bottom it does not move.
        return None
    vx, vy = _drift(sub, state[4])
    state[0] += vx * dt
    state[1] += vy * dt
    minute_before = math.floor((sim_t - dt) / 60.0)
    minute = math.floor(sim_t / 60.0)
    if minute != minute_before:
        walk = config.UBOOT_DR_WALK_NM * (config.UBOOT_DR_NUCLEAR_FACTOR
                                          if sub.endurance is None else 1.0)
        state[0] += walk * detrand.normal(sub.sensor_seed, "boat_dr_walk_x", minute)
        state[1] += walk * detrand.normal(sub.sensor_seed, "boat_dr_walk_y", minute)
    limit = config.UBOOT_DR_ERROR_MAX_NM
    state[0] = max(-limit, min(limit, state[0]))
    state[1] = max(-limit, min(limit, state[1]))
    return None


def error(boat) -> tuple[float, float]:
    """Navigated minus true position (NM): how far the crew's chart is off."""
    state = boat.orders.nav
    return state[0], state[1]


def position(boat) -> tuple[float, float]:
    """Where the crew believes the boat is (chart coordinates)."""
    ex, ey = error(boat)
    return boat.sub.x + ex, boat.sub.y + ey


def uncertainty_nm(boat) -> float:
    """The navigator's own estimate of the error (what the displays show):
    the worst set over the time since the fix plus twice the walk."""
    sub, state = boat.sub, boat.orders.nav
    hours = state[2] / 3600.0
    minutes = state[2] / 60.0
    walk = config.UBOOT_DR_WALK_NM * (config.UBOOT_DR_NUCLEAR_FACTOR
                                      if sub.endurance is None else 1.0)
    return min(config.UBOOT_DR_ERROR_MAX_NM,
               _rate_kn(sub) * hours + 2.0 * walk * math.sqrt(minutes))


def fix_progress(boat) -> float:
    """0..1 of the GPS fix being taken (0 without one)."""
    return boat.orders.nav[3] / config.UBOOT_GPS_FIX_S


# --- route --------------------------------------------------------------------

def add_waypoint(boat, x: float, y: float, size_nm: float):
    """Append a chart waypoint; True or a refusal code."""
    if (type(x) not in (int, float) or type(y) not in (int, float)
            or not math.isfinite(x) or not math.isfinite(y)):
        return "invalid_value"
    route = boat.orders.route
    x, y = config.clamp(float(x), 0.0, size_nm), config.clamp(float(y), 0.0, size_nm)
    if not route.add(x, y):
        return "uboot_route_full"
    bx, by = position(boat)
    boat.orders.event("route_waypoint", number=f"{len(route.points)}",
                      bearing=f"{route_model.bearing_to(bx, by, x, y):03.0f}")
    return True


def cycle_pattern(boat, size_nm: float):
    """No route -> zigzag -> expanding square -> off, from the navigated
    position and the ordered course."""
    route = boat.orders.route
    if route.active and route.kind == route_model.PATTERNS[-1]:
        return clear(boat)
    index = (route_model.PATTERNS.index(route.kind) + 1
             if route.active and route.kind in route_model.PATTERNS else 0)
    return start_pattern(boat, route_model.PATTERNS[index], size_nm)


def start_pattern(boat, kind: str, size_nm: float):
    """A search pattern from the navigated position on the ordered course."""
    if kind not in route_model.PATTERNS:
        return "invalid_value"
    route = boat.orders.route
    bx, by = position(boat)
    route.start_pattern(kind, bx, by, boat.sub.order_course)
    route.points = [(config.clamp(x, 0.0, size_nm), config.clamp(y, 0.0, size_nm))
                    for x, y in route.points]
    boat.orders.event(f"route_pattern_{kind}")
    return True


def clear(boat):
    if boat.orders.route.active:
        boat.orders.route.clear()
        boat.orders.event("route_cancelled")
    return True


def cancel_on_helm(boat) -> None:
    """A course order from the helm takes the boat off its route."""
    clear(boat)


def steer(boat) -> None:
    """Steer the ordered course to the next waypoint from the navigated
    position (0.25 s cadence; a baffle clearing has the helm meanwhile)."""
    route, sub, orders = boat.orders.route, boat.sub, boat.orders
    if not route.active or orders.baffle_clear is not None or sub.sunk:
        return
    bx, by = position(boat)
    course, reached = route.steer(bx, by)
    if reached:
        if course is None:
            route.clear()
            orders.event("route_complete")
            return
        orders.event("route_reached", number=f"{route.index}")
    if course is not None and abs(((course - sub.order_course + 180.0) % 360.0) - 180.0) > 0.05:
        sub.set_orders(course=round(course, 1) % 360.0)
