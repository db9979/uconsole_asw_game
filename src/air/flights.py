"""W3: Luftfahrt – zivile Flüge zwischen Airbases + militärische Patrouillen.

Flüge sind oberflächennahe, nie im Sonar sichtbar; Radar/ESM zeigen sie
(militärische Patrouillen nur als ESM-Peilung jenseits der Radarreichweite,
innerhalb als Track "FLG").
"""

import math
import random

from src.core import config
from src.data.catalog import CATALOG
from src.sensors.platform import (
    PlatformObservation,
    PlatformSensorSuite,
    snapshot_observation,
)


class Flight:
    """Ein Flug: civil = Basis A -> Basis B (einfach), military = Loiter um
    die eigene Basis. Flugzeugprofil (Speed, ESM, Loiter) kommt aus dem
    Kontakt-Katalog."""

    def __init__(self, kind: str, base: dict, dest: dict = None,
                  loiter_nm: float = None, rng: random.Random = None,
                  seq: int = 1, akey: str = None, catalog=None, *,
                  side: str = None, doctrine: str = None):
        self.kind = kind
        self.seq = seq
        self.rng = rng or random.Random()
        self.base_id = base["id"]
        self.nation = base.get("nation", "ZIVIL")
        self.base = base
        self.dest = dest
        catalog = catalog or CATALOG
        if akey is None:
            binding = "civil_flight" if kind == "civil" else "military_flight"
            akey = catalog.runtime_bindings[binding]
        self.akey = akey
        profile = catalog.aircraft.get(akey)
        if profile is None:
            profile = catalog.pick_aircraft(self.rng, kind)
            akey = profile.key
            self.akey = akey
        self.profile = profile
        self.side = side or ("neutral" if kind == "civil" else "hostile")
        self.doctrine = doctrine or (
            "civil_flight" if kind == "civil" else "military_patrol")
        self.sensor_seed = int(seq)
        self.sensor_suite = PlatformSensorSuite(
            catalog, self.akey, self.sensor_seed, side=self.side,
            doctrine=self.doctrine,
            datalink_group="blue" if self.side == "friendly" else None)
        self.speed = profile.speed_kn
        self.esm = profile.esm
        self.esm_range_nm = profile.esm_range_nm
        # Gameplay doctrine, not aircraft equipment specifications: military
        # patrols transmit radar. ESM is separately a passive receiver capability.
        self.radar_emitting = kind == "military" and dest is None
        self.sensor_bearing = None
        self.sensor_age = config.RADAR_TRACK_STALE_S
        loiter_nm = loiter_nm or self.rng.uniform(*profile.loiter_nm)
        self.loiter_nm = loiter_nm

        if dest is not None:
            self.x, self.y = base["x"], base["y"]
            dx = dest["x"] - self.x
            dy = dest["y"] - self.y
            self.total_dist = math.hypot(dx, dy)
            self.traveled = 0.0
            # Nautischer Kurs: 0° = Nord/-y
            self.course = math.degrees(math.atan2(dx, -dy)) % 360.0
        else:
            cx, cy = base["x"], base["y"]
            ang = self.rng.uniform(0.0, 360.0)
            r = self.rng.uniform(0.0, loiter_nm)
            self.x = cx + r * math.cos(math.radians(ang))
            self.y = cy + r * math.sin(math.radians(ang))
            self.course = self.rng.uniform(0.0, 360.0)
            self.total_dist = None
            self.traveled = 0.0
            axis = math.radians(self.rng.uniform(0.0, 360.0))
            along = (math.sin(axis), -math.cos(axis))
            across = (math.cos(axis), math.sin(axis))
            half_width = loiter_nm * .35
            self.waypoints = [
                (cx + along[0] * loiter_nm + across[0] * half_width,
                 cy + along[1] * loiter_nm + across[1] * half_width),
                (cx - along[0] * loiter_nm + across[0] * half_width,
                 cy - along[1] * loiter_nm + across[1] * half_width),
                (cx - along[0] * loiter_nm - across[0] * half_width,
                 cy - along[1] * loiter_nm - across[1] * half_width),
                (cx + along[0] * loiter_nm - across[0] * half_width,
                 cy + along[1] * loiter_nm - across[1] * half_width),
            ]
            self.waypoint_idx = 0
        self.active = True

    def update(self, dt: float, observation=None, *, ship_emitting=False,
               world=None) -> None:
        if not self.active:
            return
        step = config.kn_to_nm_per_s(self.speed) * dt
        if self.dest is None:
            wx, wy = self.waypoints[self.waypoint_idx]
            if math.hypot(wx - self.x, wy - self.y) < 1.0:
                self.waypoint_idx = (self.waypoint_idx + 1) % len(self.waypoints)
                wx, wy = self.waypoints[self.waypoint_idx]
            target = math.degrees(math.atan2(wx - self.x,
                                             -(wy - self.y))) % 360.0
            self.sensor_age = min(config.RADAR_TRACK_STALE_S, self.sensor_age + dt)
            if (observation is not None and not isinstance(
                    observation, PlatformObservation)):
                observation = (snapshot_observation(
                    self, observation, domain="esm", positioned=False)
                    if ship_emitting and self.esm
                    and self.distance_nm(observation) <= self.esm_range_nm
                    and not getattr(world, "land_blocks_line", lambda *args: False)(
                        self.x, self.y, observation.x, observation.y) else None)
            fresh_observation = (observation is not None and (
                observation.track_id == "LEGACY"
                or observation.last_seen > self.sensor_suite.last_consumed_s))
            if fresh_observation and self.esm:
                self.sensor_bearing = observation.bearing
                self.sensor_age = 0.0
                self.sensor_suite.last_consumed_s = max(
                    self.sensor_suite.last_consumed_s, observation.last_seen)
            if self.sensor_age >= config.RADAR_TRACK_STALE_S:
                self.sensor_bearing = None
            if self.sensor_bearing is not None:
                target = self.sensor_bearing
            diff = config.angle_diff_deg(target, self.course)
            self.course = (self.course + config.clamp(
                diff, -2.0 * dt, 2.0 * dt)) % 360.0
        self.x += step * math.sin(math.radians(self.course))
        self.y -= step * math.cos(math.radians(self.course))
        if self.dest is not None:
            self.traveled += step
            if self.traveled >= self.total_dist:
                self.active = False

    def distance_nm(self, ship) -> float:
        return math.hypot(self.x - ship.x, self.y - ship.y)

    def bearing_to_frigate(self, ship) -> float:
        dx = self.x - ship.x
        dy = self.y - ship.y
        return math.degrees(math.atan2(dx, -dy)) % 360.0

    @property
    def ais_transmitting(self) -> bool:
        return False

    @property
    def sensor_domain(self) -> str:
        return "air"


class FlightManager:
    """Verwaltet die Fluginformationen (W3)."""

    MAX_FLIGHTS = 4

    def __init__(self, coast, rng: random.Random, catalog=None):
        self.coast = coast
        self.rng = rng
        self.catalog = catalog or CATALOG
        self.flights: list[Flight] = []
        self._seq = 0
        self._spawn_cd = 600.0
        self._spawn_initial()

    def _spawn_flight(self, kind: str, base: dict, dest: dict = None) -> None:
        self._seq += 1
        self.flights.append(Flight(kind, base, dest=dest, rng=self.rng,
                                   seq=self._seq, catalog=self.catalog))

    def _spawn_initial(self) -> None:
        friendly = self.coast.friendly_bases()
        host = self.coast.hostile_base()
        neutral = self.coast.neutral_base()
        if len(friendly) >= 2:
            self._spawn_flight("civil", friendly[0], dest=friendly[1])
        else:
            self._spawn_flight("civil", neutral,
                               dest=friendly[0] if friendly else host)
        self._spawn_flight("military", host)

    def update(self, dt: float, ship=None, *, ship_emitting=False, world=None) -> None:
        for f in self.flights:
            observation = (ship if ship is not None else
                           getattr(f, "_tactical_observation", None))
            f.update(dt, observation, ship_emitting=ship_emitting, world=world)
        self.flights = [f for f in self.flights if f.active]
        self._spawn_cd -= dt
        if self._spawn_cd <= 0.0 and len(self.flights) < self.MAX_FLIGHTS:
            self._spawn_cd = self.rng.uniform(1200.0, 2700.0)
            bases = list(self.coast.airbases)
            b1, b2 = self.rng.choice(bases), self.rng.choice(bases)
            if b1["id"] == b2["id"]:
                return
            if self.rng.random() < 0.65:
                # Zivil: zwischen zwei Basen (meist friedliche)
                if b1.get("nation") == "BOREN" or b2.get("nation") == "BOREN":
                    return
                self._spawn_flight("civil", b1, dest=b2)
            else:
                # Militär: nur BOREN patrouilliert
                base = b1 if b1.get("nation") == "BOREN" else b2
                if base.get("nation") != "BOREN":
                    return
                self._spawn_flight("military", base)

    def military(self) -> list:
        return [f for f in self.flights if f.kind == "military"]

    def civil(self) -> list:
        return [f for f in self.flights if f.kind == "civil"]
