"""Maritime patrol aircraft (MPA) under the frigate's tactical control.

A long-range patrol aircraft on call from the nearest friendly airbase.
The operations room (OPZ) requests it, gives it a waypoint to search
about, orders sonobuoy patterns, switches its surface-search radar and
releases a lightweight torpedo on a designated contact.  Its reports reach
the ship only by datalink: radar contacts become ``RADAR-MPA`` tracks and
its buoys are heard only while the aircraft is close enough to relay them.

States: ``BASE`` (on the ground; ready again after a turnaround),
``TRANSIT`` (flying to its waypoint), ``STATION`` (orbiting the waypoint),
``RTB`` (returning to base).  Movement uses the same simulation time as
every other platform: ``x += sin(course)``, ``y -= cos(course)``.
Every step is deterministic (no random draws here).
"""

from __future__ import annotations

import math

from src.air.sonobuoy import Sonobuoy
from src.core import config
from src.physics.geo import bearing_deg as _bearing
from src.core.limits import finite_number as _number

STATES = ("BASE", "TRANSIT", "STATION", "RTB")
AIRBORNE = ("TRANSIT", "STATION", "RTB")
VERSION = 1
STATE_FIELDS = frozenset({
    "version", "state", "x", "y", "course", "base_x", "base_y",
    "waypoint_x", "waypoint_y", "fuel_s", "ready_t", "sorties", "buoys_left",
    "torps", "radar_on", "buoy_mode", "pattern", "pattern_queue", "mad_mode",
})
MAX_PATTERN_POINTS = 4


def _steer(course: float, wanted: float, dt: float) -> float:
    delta = (wanted - course + 540.0) % 360.0 - 180.0
    limit = config.MPA_TURN_DEG_S * dt
    return (course + max(-limit, min(limit, delta))) % 360.0


class PatrolAircraft:
    """The on-call patrol aircraft and its stores."""

    def __init__(self, base_x: float, base_y: float):
        self.state = "BASE"
        self.base_x, self.base_y = float(base_x), float(base_y)
        self.x, self.y = self.base_x, self.base_y
        self.course = 0.0
        self.waypoint_x, self.waypoint_y = self.base_x, self.base_y
        self.fuel_s = config.MPA_ENDURANCE_S
        self.ready_t = 0.0
        self.sorties = 0
        self.buoys_left = config.MPA_BUOYS
        self.torps = config.MPA_TORPS
        self.radar_on = True
        self.buoy_mode = "PASSIVE"
        self.pattern = "single"
        self.pattern_queue: list[tuple[float, float]] = []
        # MAD run: low and slower, straight passes over the waypoint instead
        # of the orbit (only on station without a buoy pattern).
        self.mad_mode = False

    # --- state ---------------------------------------------------------------

    @property
    def airborne(self) -> bool:
        return self.state in AIRBORNE

    @property
    def mad_run(self) -> bool:
        """Flying the MAD passes right now (on station, no pattern queued)."""
        return self.mad_mode and self.state == "STATION" and not self.pattern_queue

    @property
    def altitude_m(self) -> float:
        return config.MPA_MAD_ALTITUDE_M if self.mad_run else config.MPA_ALTITUDE_M

    @property
    def speed_kn(self) -> float:
        if self.mad_run:
            return config.MPA_MAD_KN
        if self.state == "STATION":
            return config.MPA_STATION_KN
        return config.MPA_TRANSIT_KN if self.airborne else 0.0

    def available(self, sim_t: float) -> bool:
        return (self.state == "BASE" and sim_t >= self.ready_t
                and self.sorties < config.MPA_SORTIES)

    def ready_in_s(self, sim_t: float) -> float | None:
        if self.state != "BASE" or self.sorties >= config.MPA_SORTIES:
            return None
        return max(0.0, self.ready_t - sim_t)

    def bingo_s(self) -> float:
        """Fuel needed to fly home from here, with the reserve."""
        distance = math.hypot(self.base_x - self.x, self.base_y - self.y)
        return distance / config.kn_to_nm_per_s(config.MPA_TRANSIT_KN) + config.MPA_RESERVE_S

    # --- orders ----------------------------------------------------------------

    def launch(self, waypoint_x: float, waypoint_y: float, sim_t: float) -> bool:
        if not self.available(sim_t):
            return False
        self.state = "TRANSIT"
        self.x, self.y = self.base_x, self.base_y
        self.fuel_s = config.MPA_ENDURANCE_S
        self.set_waypoint(waypoint_x, waypoint_y)
        self.course = _bearing(self.x, self.y, waypoint_x, waypoint_y)
        return True

    def set_waypoint(self, x: float, y: float) -> None:
        self.waypoint_x, self.waypoint_y = float(x), float(y)
        if self.state == "STATION" and math.hypot(
                self.x - x, self.y - y) > config.MPA_ORBIT_NM + config.MPA_ARRIVE_NM:
            self.state = "TRANSIT"

    def order_return(self) -> bool:
        if self.state not in ("TRANSIT", "STATION"):
            return False
        self.state = "RTB"
        self.pattern_queue = []
        self.pattern = "single"
        self.mad_mode = False
        return True

    def deploy_buoy(self, seq: int, world=None) -> Sonobuoy | None:
        """Drop one buoy at the aircraft's own position (water only)."""
        if not self.airborne or self.state == "RTB" or self.buoys_left <= 0:
            return None
        if world is not None and (
                not (0.0 <= self.x <= world.size_nm and 0.0 <= self.y <= world.size_nm)
                or world.on_land(self.x, self.y) or world.depth_m(self.x, self.y) <= 5.0):
            return None
        self.buoys_left -= 1
        return Sonobuoy(self.x, self.y, seq, self.buoy_mode, owner="MPA")

    # --- time ----------------------------------------------------------------------

    def update(self, dt: float, sim_t: float) -> str | None:
        """Fly one step; returns an event name (``on_station``, ``bingo``,
        ``landed``) when the state changed."""
        if not self.airborne:
            return None
        self.fuel_s = max(0.0, self.fuel_s - dt)
        event = None
        if self.state in ("TRANSIT", "STATION") and self.fuel_s <= self.bingo_s():
            self.order_return()
            event = "bingo"
        if self.state == "RTB":
            target = (self.base_x, self.base_y)
        elif self.pattern_queue:
            target = self.pattern_queue[0]
        else:
            target = (self.waypoint_x, self.waypoint_y)
        distance = math.hypot(target[0] - self.x, target[1] - self.y)
        if self.state == "RTB" and distance <= config.MPA_ARRIVE_NM:
            self._land(sim_t)
            return "landed"
        if self.state == "TRANSIT" and not self.pattern_queue and distance <= config.MPA_ARRIVE_NM:
            self.state = "STATION"
            event = event or "on_station"
        wanted = _bearing(self.x, self.y, *target)
        if self.mad_run:
            # Straight passes over the waypoint: steer at it, hold the course
            # once it is behind and turn back after the leg length (a cloverleaf).
            behind = abs((wanted - self.course + 540.0) % 360.0 - 180.0) > 90.0
            if behind and distance <= config.MPA_MAD_LEG_NM:
                wanted = self.course
        elif self.state == "STATION" and not self.pattern_queue:
            # Orbit the waypoint: fly the tangent, corrected towards the circle.
            # Clockwise tangent is the bearing from the centre + 90 degrees;
            # outside the circle the correction turns in, inside it out.
            error = (distance - config.MPA_ORBIT_NM) / config.MPA_ORBIT_NM
            correction = max(-60.0, min(60.0, 60.0 * error))
            wanted = (_bearing(target[0], target[1], self.x, self.y) + 90.0
                      + correction) % 360.0
        self.course = _steer(self.course, wanted, dt)
        step = config.kn_to_nm_per_s(self.speed_kn) * dt
        self.x += step * math.sin(math.radians(self.course))
        self.y -= step * math.cos(math.radians(self.course))
        return event

    def _land(self, sim_t: float) -> None:
        self.state = "BASE"
        self.x, self.y = self.base_x, self.base_y
        self.sorties += 1
        self.ready_t = float(sim_t) + config.MPA_TURNAROUND_S
        # Turned round with full stores and fuel.
        self.buoys_left = config.MPA_BUOYS
        self.torps = config.MPA_TORPS
        self.fuel_s = config.MPA_ENDURANCE_S

    # --- save ------------------------------------------------------------------------

    def serialize(self) -> dict:
        return dict(version=VERSION, state=self.state, x=self.x, y=self.y,
                    course=self.course, base_x=self.base_x, base_y=self.base_y,
                    waypoint_x=self.waypoint_x, waypoint_y=self.waypoint_y,
                    fuel_s=self.fuel_s, ready_t=self.ready_t, sorties=self.sorties,
                    buoys_left=self.buoys_left, torps=self.torps,
                    radar_on=self.radar_on, buoy_mode=self.buoy_mode,
                    pattern=self.pattern,
                    pattern_queue=[[x, y] for x, y in self.pattern_queue],
                    mad_mode=self.mad_mode)

    @staticmethod
    def valid_state(state, world_size_nm: float) -> bool:
        if not isinstance(state, dict) or set(state) != STATE_FIELDS:
            return False
        if type(state["version"]) is not int or state["version"] != VERSION:
            return False
        if state["state"] not in STATES:
            return False
        # Loose bound: the base may lie off a small test world's chart.
        limit = max(float(world_size_nm), config.WORLD_SIZE_NM) + 200.0

        def coord(value) -> bool:
            return _number(value) and -200.0 <= value <= limit

        if not all(coord(state[key]) for key in (
                "x", "y", "base_x", "base_y", "waypoint_x", "waypoint_y")):
            return False
        if not (_number(state["course"]) and 0.0 <= state["course"] < 360.0):
            return False
        if not (_number(state["fuel_s"]) and 0.0 <= state["fuel_s"] <= config.MPA_ENDURANCE_S):
            return False
        if not (_number(state["ready_t"]) and 0.0 <= state["ready_t"] <= 1e9):
            return False
        if (type(state["sorties"]) is not int
                or not 0 <= state["sorties"] <= config.MPA_SORTIES):
            return False
        if (type(state["buoys_left"]) is not int
                or not 0 <= state["buoys_left"] <= config.MPA_BUOYS):
            return False
        if type(state["torps"]) is not int or not 0 <= state["torps"] <= config.MPA_TORPS:
            return False
        if type(state["radar_on"]) is not bool or type(state["mad_mode"]) is not bool:
            return False
        if state["mad_mode"] and state["state"] not in ("TRANSIT", "STATION"):
            return False
        if state["buoy_mode"] not in ("PASSIVE", "ACTIVE"):
            return False
        from src.air.helicopter import BUOY_PATTERNS
        if state["pattern"] not in BUOY_PATTERNS:
            return False
        queue = state["pattern_queue"]
        if (not isinstance(queue, list) or len(queue) > MAX_PATTERN_POINTS
                or not all(isinstance(point, list) and len(point) == 2
                           and all(coord(value) for value in point) for point in queue)):
            return False
        if (state["pattern"] == "single") != (not queue):
            return False
        if state["state"] == "BASE" and (queue or (state["x"], state["y"])
                                          != (state["base_x"], state["base_y"])):
            return False
        return True

    @classmethod
    def restore(cls, state, world_size_nm: float) -> "PatrolAircraft":
        if not cls.valid_state(state, world_size_nm):
            raise ValueError("invalid patrol aircraft state")
        aircraft = cls(state["base_x"], state["base_y"])
        for key in ("state", "x", "y", "course", "waypoint_x", "waypoint_y",
                    "fuel_s", "ready_t", "sorties", "buoys_left", "torps",
                    "radar_on", "buoy_mode", "pattern", "mad_mode"):
            setattr(aircraft, key, state[key])
        aircraft.pattern_queue = [(float(x), float(y)) for x, y in state["pattern_queue"]]
        return aircraft
