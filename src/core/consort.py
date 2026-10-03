"""The consort: a second friendly warship hunting together with the frigate.

Group-hunt scenarios put a destroyer beside the frigate. The frigate's OPZ
commands it (OPZ page 4, Remote Crew OPZ): keep station in formation, search
around a point, prosecute a point, hold, or decide by itself (``auto``),
with its active sonar and its weapons released or held. The destroyer is a
commanded own asset, so its position, course, speed, orders and stores are
datalink truth for the frigate; what its sonar hears reaches the frigate
only as measurements: a cross-fix of its passive bearing with the frigate's
own (fix source ``CONSORT``), or the echo of its active ping.

Pure model: the orders, their validation, the steering they ask for and the
deterministic ping. The game side lives in ``src/core/game_consort.py``.
"""

from __future__ import annotations

import math

from src.core import config, detrand
from src.physics.geo import bearing_deg as bearing

MODES = ("auto", "formation", "search", "prosecute", "hold")
# Formation stations relative to the frigate's course: (bearing, key).
STATIONS = (("starboard", 90.0), ("ahead", 0.0), ("port", 270.0), ("astern", 180.0))
STATION_KEYS = tuple(key for key, _bearing in STATIONS)
FIELDS = frozenset({"warship_id", "callsign", "mode", "point", "station", "active",
                    "weapons_free", "next_ping_s", "last_shot_s", "lost"})


class ConsortOrders:
    """What the frigate ordered its consort (save root ``consort``)."""

    def __init__(self, warship_id: int, callsign: str):
        self.warship_id = int(warship_id)
        self.callsign = str(callsign)
        self.mode = "auto"
        self.point: tuple[float, float] | None = None
        self.station = STATION_KEYS[0]
        self.active = False
        self.weapons_free = False
        self.next_ping_s = 0.0
        self.last_shot_s = -1.0
        # The destroyer was sunk (reported once).
        self.lost = False

    def serialize(self) -> dict:
        return dict(warship_id=self.warship_id, callsign=self.callsign, mode=self.mode,
                    point=None if self.point is None else [float(v) for v in self.point],
                    station=self.station, active=bool(self.active),
                    weapons_free=bool(self.weapons_free),
                    next_ping_s=float(self.next_ping_s),
                    last_shot_s=float(self.last_shot_s), lost=bool(self.lost))

    @staticmethod
    def valid_state(state, world_size_nm: float, save_sim_t: float) -> bool:
        if state is None:
            return True
        if not isinstance(state, dict) or set(state) != FIELDS:
            return False

        def number(value, low, high):
            return (type(value) in (int, float) and math.isfinite(value)
                    and low <= value <= high)

        point = state["point"]
        return (type(state["warship_id"]) is int and 0 <= state["warship_id"] < 2**31
                and isinstance(state["callsign"], str) and 0 < len(state["callsign"]) <= 40
                and state["mode"] in MODES and state["station"] in STATION_KEYS
                and (point is None or (isinstance(point, list) and len(point) == 2
                                       and all(number(v, 0.0, world_size_nm)
                                               for v in point)))
                and all(type(state[key]) is bool
                        for key in ("active", "weapons_free", "lost"))
                and number(state["next_ping_s"], 0.0, save_sim_t + 3600.0)
                and number(state["last_shot_s"], -1.0, save_sim_t))

    @classmethod
    def restore(cls, state) -> "ConsortOrders | None":
        if state is None:
            return None
        orders = cls(state["warship_id"], state["callsign"])
        orders.mode = state["mode"]
        orders.point = None if state["point"] is None else tuple(
            float(v) for v in state["point"])
        orders.station = state["station"]
        orders.active = state["active"]
        orders.weapons_free = state["weapons_free"]
        orders.next_ping_s = float(state["next_ping_s"])
        orders.last_shot_s = float(state["last_shot_s"])
        orders.lost = state["lost"]
        return orders


def station_point(orders: ConsortOrders, frigate) -> tuple[float, float]:
    """The consort's formation station off the frigate."""
    relative = dict(STATIONS)[orders.station]
    angle = math.radians((frigate.course + relative) % 360.0)
    distance = config.CONSORT_STATION_NM
    return (frigate.x + distance * math.sin(angle), frigate.y - distance * math.cos(angle))


def steer(orders: ConsortOrders, consort, frigate, mode: str, point, sim_t: float):
    """``(course, speed)`` the consort's bridge orders for ``mode``.

    ``mode`` is the effective mode (``auto`` already resolved by the game);
    ``point`` the search/prosecute point. Course and speed only, the ship's
    own safety steering (land, other ships) still has the last word."""
    cap = consort.speed_cap_kn
    if mode == "hold":
        return consort.course, min(config.CONSORT_HOLD_KN, cap)
    if mode in ("search", "prosecute") and point is not None:
        distance = math.hypot(point[0] - consort.x, point[1] - consort.y)
        orbit = (config.CONSORT_PROSECUTE_ORBIT_NM if mode == "prosecute"
                 else config.CONSORT_SEARCH_ORBIT_NM)
        if distance > orbit * 1.5:
            speed = (config.CONSORT_SPRINT_KN if mode == "prosecute"
                     else config.CONSORT_TRANSIT_KN)
            return bearing(consort.x, consort.y, *point), min(speed, cap)
        # Circle the point: tangent course, closing in when outside the orbit,
        # slow enough for the hull sonar to hear.
        radial = bearing(point[0], point[1], consort.x, consort.y)
        correction = config.clamp((distance - orbit) * 30.0, -45.0, 45.0)
        return ((radial + 90.0 + correction) % 360.0,
                min(config.CONSORT_SEARCH_KN, cap))
    # Formation: run for the station, match the frigate's speed once there.
    sx, sy = station_point(orders, frigate)
    distance = math.hypot(sx - consort.x, sy - consort.y)
    if distance < 0.3:
        return frigate.course, min(max(frigate.speed, config.CONSORT_HOLD_KN), cap)
    catch_up = frigate.speed + config.clamp(distance * 6.0, 2.0, 14.0)
    return bearing(consort.x, consort.y, sx, sy), min(catch_up, cap)


def ping_echo(seed: int, consort, target, tick: int, blocked: bool):
    """The consort's active ping on one submerged target, or None.

    Returns ``(x, y, depth_m, quality)`` measured with the hull sonar's
    errors; detection falls off with range (stateless draws keyed by the
    ping's tick, so a loaded game pings identically)."""
    if blocked or getattr(target, "sunk", False):
        return None
    distance = math.hypot(target.x - consort.x, target.y - consort.y)
    reach = config.CONSORT_ACTIVE_RANGE_NM
    if distance > reach:
        return None
    probability = config.clamp(1.0 - (distance / reach) ** 2, 0.1, 0.95)
    # Keyed on the boat's sensor seed: entity ids are process-global, so two
    # games with the same seed would otherwise ping differently.
    key = 1 + int(getattr(target, "sensor_seed", 0)) % 1_000_000
    if detrand.u01(seed, "consort_ping", key, tick) >= probability:
        return None
    error = config.CONSORT_ACTIVE_ERR_NM * (0.5 + distance / reach)
    x = target.x + error * detrand.normal(seed, "consort_ping_x", key, tick)
    y = target.y + error * detrand.normal(seed, "consort_ping_y", key, tick)
    depth = max(0.0, float(getattr(target, "depth", 0.0)) + config.CONSORT_ACTIVE_DEPTH_ERR_M
                * detrand.normal(seed, "consort_ping_d", key, tick))
    return x, y, depth, config.clamp(1.0 - distance / reach, 0.3, 1.0)


def cross_fix(first, second, max_nm: float):
    """Intersection of two bearing lines ``(x, y, bearing)``: ``(x, y, sin angle)``
    or None for a poor cut or a point behind either observer."""
    a1, a2 = math.radians(first[2]), math.radians(second[2])
    r = (math.sin(a1), -math.cos(a1))
    s = (math.sin(a2), -math.cos(a2))
    denom = r[0] * s[1] - r[1] * s[0]
    if abs(denom) < math.sin(math.radians(config.CONSORT_XFIX_MIN_DEG)):
        return None
    qx, qy = second[0] - first[0], second[1] - first[1]
    along_first = (qx * s[1] - qy * s[0]) / denom
    along_second = (qx * r[1] - qy * r[0]) / denom
    if not (0.0 <= along_first <= max_nm and 0.0 <= along_second <= max_nm):
        return None
    return first[0] + along_first * r[0], first[1] + along_first * r[1], abs(denom)
