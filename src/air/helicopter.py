"""M15: Hubschrauber HSP-5 (Sea Lynx) – Sonarbojen + Leichttorpedos.

Zustände: HANGAR | AUF (Einsatz) | ZURUECK (Rückkehr).
Bewegung, Treibstoff und Zeitfenster verwenden dieselbe Simulationszeit.
"""

import math
from dataclasses import dataclass

from src.core import config
from src.air.sonobuoy import Sonobuoy
from src.data.catalog import CATALOG
from src.weapons.torpedo import Torpedo


HELO_TORPEDO_PROFILE = CATALOG.get_torpedo("helo_torp")
if HELO_TORPEDO_PROFILE is None:
    raise RuntimeError(
        "Kontaktkatalog unvollstaendig: Torpedo-Profil 'helo_torp' fehlt")


@dataclass(frozen=True)
class ReleaseDatum:
    """Observed world datum and the helicopter-relative delivery geometry."""

    x_nm: float
    y_nm: float
    course_deg: float
    range_nm: float
    bearing_uncertainty_deg: float
    range_uncertainty_nm: float


class Helicopter:
    SPEED_KN = config.HELO_SPEED_KN

    def __init__(self, rng, torpedo_profile=None):
        self.rng = rng
        self.torpedo_profile = torpedo_profile or HELO_TORPEDO_PROFILE
        self.state = "HANGAR"
        self.x = 0.0
        self.y = 0.0
        self.course = 0.0
        self.torps = config.HELO_TORPS
        self.buoys_left = config.BUOY_COUNT
        self.fuel_s = 0.0
        self.waypoint_x = None
        self.waypoint_y = None
        self.dip_state = "STOWED"
        self.dip_depth_m = 0.0
        self.dip_depth_target_m = config.HELO_DIP_DEPTH_DEFAULT_M
        self.dip_water_depth_m = 0.0
        self.dip_ping_cooldown = 0.0

    @property
    def airborne(self) -> bool:
        return self.state in ("AUF", "ZURUECK")

    def launch(self, frigate) -> None:
        """Start with the remaining finite mission loadout."""
        self.state = "AUF"
        self.x = frigate.x
        self.y = frigate.y
        self.course = frigate.course
        self.fuel_s = config.HELO_FUEL_S
        self.dip_state = "STOWED"
        self.dip_depth_m = 0.0
        self.dip_water_depth_m = 0.0
        if self.waypoint_x is None or self.waypoint_y is None:
            self.set_waypoint(frigate.x + 2.0 * math.sin(math.radians(frigate.course)),
                              frigate.y - 2.0 * math.cos(math.radians(frigate.course)))

    def set_waypoint(self, x_nm: float, y_nm: float) -> None:
        self.waypoint_x = x_nm
        self.waypoint_y = y_nm

    def order_return(self) -> None:
        if self.airborne:
            self.state = "ZURUECK"
            if self.dip_state != "STOWED":
                self.dip_state = "RETRIEVING"

    @property
    def hovering(self) -> bool:
        return self.airborne and self.dip_state != "STOWED"

    @property
    def dip_available(self) -> bool:
        return self.state == "AUF" and self.dip_state == "DEPLOYED"

    @property
    def dip_ping_ready(self) -> bool:
        return self.dip_available and self.dip_ping_cooldown <= 0.0

    def dip_depth_limit(self, world) -> float:
        if not self.water_entry_clear(world):
            return 0.0
        water_depth = float(world.depth_m(self.x, self.y))
        return min(config.HELO_DIP_DEPTH_MAX_M,
                   max(0.0, water_depth - config.HELO_DIP_BOTTOM_CLEARANCE_M))

    def set_dip_depth(self, depth_m: float, world) -> bool:
        limit = self.dip_depth_limit(world)
        if limit < config.HELO_DIP_DEPTH_MIN_M:
            return False
        self.dip_depth_target_m = config.clamp(
            depth_m, config.HELO_DIP_DEPTH_MIN_M, limit)
        if (self.dip_state == "DEPLOYED"
                and abs(self.dip_depth_m - self.dip_depth_target_m) > 1e-9):
            self.dip_state = "DEPLOYING"
        return True

    def set_dipping(self, deployed: bool, world) -> bool:
        if not self.airborne or self.state != "AUF":
            return False
        if deployed:
            if self.dip_state in ("DEPLOYING", "DEPLOYED"):
                return True
            if not self.set_dip_depth(self.dip_depth_target_m, world):
                return False
            self.dip_water_depth_m = float(world.depth_m(self.x, self.y))
            self.dip_state = "DEPLOYING"
        else:
            if self.dip_state == "STOWED":
                return True
            self.dip_state = "RETRIEVING"
        return True

    def fire_dipping_ping(self) -> bool:
        if not self.dip_ping_ready:
            return False
        self.dip_ping_cooldown = config.HELO_DIP_PING_COOLDOWN_S
        return True

    def _update_dipping(self, dt: float, world) -> None:
        if self.dip_state == "STOWED":
            self.dip_depth_m = 0.0
            return
        if self.dip_state == "RETRIEVING":
            self.dip_depth_m = max(
                0.0, self.dip_depth_m - config.HELO_DIP_DEPTH_RATE_M_S * dt)
            if self.dip_depth_m <= 0.0:
                self.dip_state = "STOWED"
                self.dip_water_depth_m = 0.0
            return
        limit = self.dip_depth_limit(world)
        if limit < config.HELO_DIP_DEPTH_MIN_M:
            self.dip_state = "RETRIEVING"
            return
        self.dip_water_depth_m = float(world.depth_m(self.x, self.y))
        self.dip_depth_target_m = min(self.dip_depth_target_m, limit)
        step = config.HELO_DIP_DEPTH_RATE_M_S * dt
        self.dip_depth_m += config.clamp(
            self.dip_depth_target_m - self.dip_depth_m, -step, step)
        if abs(self.dip_depth_m - self.dip_depth_target_m) <= 1e-9:
            self.dip_state = "DEPLOYED"

    def update(self, dt: float, frigate, world, recovery_available: bool = True) -> None:
        """dt in Simulationssekunden. Haelt Patrouillen-Offset vor der
        Fregatte (AUF) bzw. fliegt zurück (ZURUECK)."""
        self.dip_ping_cooldown = max(0.0, self.dip_ping_cooldown - dt)
        if not self.airborne:
            return
        self.fuel_s = max(0.0, self.fuel_s - dt)
        self._update_dipping(dt, world)
        home_dist = math.hypot(frigate.x - self.x, frigate.y - self.y)
        return_time = home_dist / config.kn_to_nm_per_s(self.SPEED_KN)
        if (self.state == "AUF"
                and self.fuel_s <= return_time + config.HELO_FUEL_RESERVE_S):
            self.state = "ZURUECK"
            if self.dip_state != "STOWED":
                self.dip_state = "RETRIEVING"
        if self.fuel_s <= 0.0:
            self.state = "VERLOREN"
            self.dip_state = "STOWED"
            self.dip_depth_m = 0.0
            self.dip_water_depth_m = 0.0
            return
        if self.hovering:
            return
        if self.state == "ZURUECK":
            dist = math.hypot(frigate.x - self.x, frigate.y - self.y)
            if dist <= config.HELO_RETURN_DIST_NM and recovery_available:
                self.state = "HANGAR"
                self.x, self.y = frigate.x, frigate.y
                return
            target_x, target_y = frigate.x, frigate.y
        else:
            target_x = self.waypoint_x if self.waypoint_x is not None else frigate.x
            target_y = self.waypoint_y if self.waypoint_y is not None else frigate.y

        dx = target_x - self.x
        dy = target_y - self.y
        if math.hypot(dx, dy) > 0.3:
            desired = math.degrees(math.atan2(dx, -dy)) % 360.0
            diff = config.angle_diff_deg(desired, self.course)
            self.course = (self.course + config.clamp(
                diff, -6.0 * dt, 6.0 * dt)) % 360.0
            step = config.kn_to_nm_per_s(self.SPEED_KN) * dt
            self.x += step * math.sin(math.radians(self.course))
            self.y -= step * math.cos(math.radians(self.course))

    def water_entry_clear(self, world=None) -> bool:
        """Require in-world water deep enough for the modeled 5 m entry."""
        return (world is None or (
            0 <= self.x <= world.size_nm and 0 <= self.y <= world.size_nm
            and not world.on_land(self.x, self.y)
            and getattr(world, "depth_m", lambda x, y: 1000.0)(self.x, self.y) > 5.0))

    def deploy_buoy(self, seq: int, world=None) -> Sonobuoy | None:
        """Drop one buoy at the helicopter's measured current position."""
        if not self.airborne or self.buoys_left <= 0:
            return None
        if not self.water_entry_clear(world):
            return None
        self.buoys_left -= 1
        return Sonobuoy(self.x, self.y, seq)

    def release_datum_from_ship_observation(
            self, ship, observed_bearing_deg: float, observed_range_nm: float,
            bearing_uncertainty_deg: float = 0.0,
            range_uncertainty_nm: float = 0.0,
            datum_x: float = None, datum_y: float = None) -> ReleaseDatum:
        """Convert a ship-relative observation for a helicopter release.

        The observed bearing is world-referenced, as elsewhere in the sensor
        model. Uncertainty remains attached rather than being mistaken for an
        exact helicopter-relative measurement.
        """
        bearing_rad = math.radians(observed_bearing_deg)
        x_nm = (ship.x + observed_range_nm * math.sin(bearing_rad)
                if datum_x is None else datum_x)
        y_nm = (ship.y - observed_range_nm * math.cos(bearing_rad)
                if datum_y is None else datum_y)
        dx, dy = x_nm - self.x, y_nm - self.y
        return ReleaseDatum(
            x_nm=x_nm,
            y_nm=y_nm,
            course_deg=math.degrees(math.atan2(dx, -dy)) % 360.0,
            range_nm=math.hypot(dx, dy),
            bearing_uncertainty_deg=bearing_uncertainty_deg,
            range_uncertainty_nm=range_uncertainty_nm,
        )

    def drop_torpedo(self, target, target_depth_m: float, seq: int,
                     kill_dist_nm: float = None, kill_depth_m: float = None,
                     guidance_x: float = None,
                     guidance_y: float = None, world=None) -> "Torpedo | None":
        """Drop a catalog torpedo with an optional absolute hit-envelope result.

        The catalog remains the default; callers may supply the intentionally
        difficulty-adjusted result used by the game level configuration.
        """
        if not self.airborne or self.torps <= 0:
            return None
        if not self.water_entry_clear(world):
            return None
        self.torps -= 1
        aim_x = target.x if guidance_x is None else guidance_x
        aim_y = target.y if guidance_y is None else guidance_y
        course = math.degrees(math.atan2(aim_x - self.x,
                                         -(aim_y - self.y))) % 360.0
        torpedo = Torpedo(self.x, self.y, course, target_depth_m, target, seq,
                          kill_dist_nm=(self.torpedo_profile.hit_dist_nm
                                        if kill_dist_nm is None else kill_dist_nm),
                          kill_depth_m=kill_depth_m,
                          speed_kn=self.torpedo_profile.speed_kn,
                          guidance_x=aim_x, guidance_y=aim_y,
                          range_nm=self.torpedo_profile.range_nm,
                          profile=self.torpedo_profile)
        torpedo.break_wire()
        return torpedo
