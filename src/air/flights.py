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
    """Ein Flug: civil = Basis A -> Basis B (optional via Weichpunkt),
    military = Loiter um die eigene Basis. Flugzeugprofil (Speed, ESM,
    Loiter) kommt aus dem Kontakt-Katalog."""

    def __init__(self, kind: str, base: dict, dest: dict = None,
                  loiter_nm: float = None, rng: random.Random = None,
                  seq: int = 1, akey: str = None, catalog=None, *,
                  side: str = None, doctrine: str = None,
                  via: tuple = None):
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
        # Component scans are recorded, while the established flight doctrine
        # continues to steer only from its legacy detached ESM observation.
        self.legacy_observation_model = True
        self.speed = profile.speed_kn
        self.esm = profile.esm
        self.esm_range_nm = profile.esm_range_nm
        # Gameplay doctrine, not aircraft equipment specifications: military
        # flights transmit radar. ESM is separately a passive receiver capability.
        self.radar_emitting = kind == "military"
        self.sensor_bearing = None
        self.sensor_age = config.RADAR_TRACK_STALE_S
        loiter_nm = loiter_nm or self.rng.uniform(*profile.loiter_nm)
        self.loiter_nm = loiter_nm

        if dest is not None:
            # Via-Punkt (optional): Route wird geometrisch so gelegt, dass sie
            # nahe am Spieler vorbeifluegt; reine Geometrie, keine RNG-Ziehung.
            self.waypoints = [tuple(via)] if via is not None else []
            self.waypoint_idx = 0
            self.x, self.y = base["x"], base["y"]
            first = self.waypoints[0] if self.waypoints else (dest["x"], dest["y"])
            dx = first[0] - self.x
            dy = first[1] - self.y
            if self.waypoints:
                self.total_dist = math.hypot(dx, dy) + math.hypot(
                    dest["x"] - first[0], dest["y"] - first[1])
            else:
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
        else:
            # Zivil: Basis -> optionaler Via-Punkt -> Ziel, gleiche
            # Wendegrenze wie die Patrouille.
            if self.waypoints and self.waypoint_idx < len(self.waypoints):
                wx, wy = self.waypoints[self.waypoint_idx]
                if math.hypot(wx - self.x, wy - self.y) < 1.0:
                    self.waypoint_idx += 1
                if self.waypoint_idx < len(self.waypoints):
                    wx, wy = self.waypoints[self.waypoint_idx]
                else:
                    wx, wy = self.dest["x"], self.dest["y"]
            else:
                wx, wy = self.dest["x"], self.dest["y"]
            target = math.degrees(math.atan2(wx - self.x,
                                             -(wy - self.y))) % 360.0
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

    def __init__(self, coast, rng: random.Random, catalog=None, *, near=None):
        self.coast = coast
        self.rng = rng
        self.catalog = catalog or CATALOG
        self.flights: list[Flight] = []
        self._seq = 0
        self._spawn_cd = 600.0
        # Position, an die zivile Routen geometrisch angebunden werden
        # (reine Geometrie, keine RNG-Ziehung).
        self._near = near
        self._spawn_initial()

    @staticmethod
    def _is_hostile_base(base: dict) -> bool:
        """Real-Sektoren nutzen gameplay_role; die Legacy-Welt nur Nationen."""
        role = base.get("gameplay_role")
        if role is not None:
            return role == "hostile"
        return base.get("nation") == "BOREN"

    def _civil_via(self, base: dict, dest: dict, near=None):
        """Via-Punkt, der die Zivilroute nahe an `near` (Fregatte) führt.

        Rein geometrisch (keine RNG-Ziehung): liegt die Gerade A->B bereits
        innerhalb von FLIGHT_CIVIL_PASS_NM an `near`, bleibt sie direkt;
        sonst wird ein Weichpunkt so gewählt, dass die Route
        FLIGHT_CIVIL_VIA_NM am Spieler vorbeifliegt."""
        if near is None:
            near = self._near
        if near is None:
            return None
        px, py = float(near[0]), float(near[1])
        ax, ay = float(base["x"]), float(base["y"])
        bx, by = float(dest["x"]), float(dest["y"])
        dx, dy = bx - ax, by - ay
        seg = dx * dx + dy * dy
        if seg <= 0.0:
            return None
        t = ((px - ax) * dx + (py - ay) * dy) / seg
        t = min(1.0, max(0.0, t))
        cx, cy = ax + t * dx, ay + t * dy
        dist = math.hypot(px - cx, py - cy)
        if dist <= config.FLIGHT_CIVIL_PASS_NM:
            return None
        scale = min(1.0, config.FLIGHT_CIVIL_VIA_NM / dist)
        vx = px + (cx - px) * scale
        vy = py + (cy - py) * scale
        size = getattr(self.coast, "world_size_nm", config.WORLD_SIZE_NM)
        return (config.clamp(vx, 0.0, size), config.clamp(vy, 0.0, size))

    def _spawn_flight(self, kind: str, base: dict, dest: dict = None,
                      via: tuple = None) -> None:
        self._seq += 1
        self.flights.append(Flight(kind, base, dest=dest, via=via, rng=self.rng,
                                    seq=self._seq, catalog=self.catalog))

    def _spawn_initial(self) -> None:
        friendly = self.coast.friendly_bases()
        host = self.coast.hostile_base()
        neutral = self.coast.neutral_base()
        if len(friendly) >= 2:
            b1, b2 = friendly[0], friendly[1]
        else:
            b1, b2 = neutral, (friendly[0] if friendly else host)
        self._spawn_flight("civil", b1, dest=b2, via=self._civil_via(b1, b2))
        self._spawn_flight("military", host)

    def update(self, dt: float, ship=None, *, near=None, ship_emitting=False,
               world=None) -> None:
        for f in self.flights:
            observation = (ship if ship is not None else
                           getattr(f, "_tactical_observation", None))
            f.update(dt, observation, ship_emitting=ship_emitting, world=world)
        self.flights = [f for f in self.flights if f.active]
        self._spawn_cd -= dt
        if self._spawn_cd <= 0.0 and len(self.flights) < self.MAX_FLIGHTS:
            window = self.rng.uniform(1200.0, 2700.0)
            bases = list(self.coast.airbases)
            b1, b2 = self.rng.choice(bases), self.rng.choice(bases)
            spawned = False
            if b1["id"] != b2["id"]:
                if self.rng.random() < 0.65:
                    # Zivil: zwischen zwei nicht-feindlichen Basen, Route
                    # nahe am Spieler, damit sie radar-einsehbar bleibt.
                    if not (self._is_hostile_base(b1) or self._is_hostile_base(b2)):
                        self._spawn_flight("civil", b1, dest=b2,
                                           via=self._civil_via(b1, b2, near))
                        spawned = True
                else:
                    # Militär: nur feindliche Basen patrouillieren.
                    base = b1 if self._is_hostile_base(b1) else (
                        b2 if self._is_hostile_base(b2) else None)
                    if base is not None:
                        self._spawn_flight("military", base)
                        spawned = True
            # Fehlgeschlagene Versuche frassen nicht das ganze Fenster.
            self._spawn_cd = window if spawned else min(window, 300.0)

    def military(self) -> list:
        return [f for f in self.flights if f.kind == "military"]

    def civil(self) -> list:
        return [f for f in self.flights if f.kind == "civil"]
