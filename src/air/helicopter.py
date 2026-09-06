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

    def __init__(self, rng):
        self.rng = rng
        self.state = "HANGAR"
        self.x = 0.0
        self.y = 0.0
        self.course = 0.0
        self.torps = config.HELO_TORPS
        self.buoys_left = config.BUOY_COUNT
        self.fuel_s = 0.0
        self.waypoint_x = None
        self.waypoint_y = None

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
        if self.waypoint_x is None or self.waypoint_y is None:
            self.set_waypoint(frigate.x + 2.0 * math.sin(math.radians(frigate.course)),
                              frigate.y - 2.0 * math.cos(math.radians(frigate.course)))

    def set_waypoint(self, x_nm: float, y_nm: float) -> None:
        self.waypoint_x = x_nm
        self.waypoint_y = y_nm

    def order_return(self) -> None:
        if self.airborne:
            self.state = "ZURUECK"

    def update(self, dt: float, frigate, world) -> None:
        """dt in Simulationssekunden. Haelt Patrouillen-Offset vor der
        Fregatte (AUF) bzw. fliegt zurück (ZURUECK)."""
        if not self.airborne:
            return
        self.fuel_s = max(0.0, self.fuel_s - dt)
        home_dist = math.hypot(frigate.x - self.x, frigate.y - self.y)
        return_time = home_dist / config.kn_to_nm_per_s(self.SPEED_KN)
        if (self.state == "AUF"
                and self.fuel_s <= return_time + config.HELO_FUEL_RESERVE_S):
            self.state = "ZURUECK"
        if self.fuel_s <= 0.0:
            self.state = "VERLOREN"
            return
        if self.state == "ZURUECK":
            dist = math.hypot(frigate.x - self.x, frigate.y - self.y)
            if dist <= config.HELO_RETURN_DIST_NM:
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

    def deploy_buoy(self, seq: int) -> Sonobuoy | None:
        """Drop one buoy at the helicopter's measured current position."""
        if not self.airborne or self.buoys_left <= 0:
            return None
        self.buoys_left -= 1
        return Sonobuoy(self.x, self.y, seq)

    def release_datum_from_ship_observation(
            self, ship, observed_bearing_deg: float, observed_range_nm: float,
            bearing_uncertainty_deg: float = 0.0,
            range_uncertainty_nm: float = 0.0) -> ReleaseDatum:
        """Convert a ship-relative observation for a helicopter release.

        The observed bearing is world-referenced, as elsewhere in the sensor
        model. Uncertainty remains attached rather than being mistaken for an
        exact helicopter-relative measurement.
        """
        bearing_rad = math.radians(observed_bearing_deg)
        x_nm = ship.x + observed_range_nm * math.sin(bearing_rad)
        y_nm = ship.y - observed_range_nm * math.cos(bearing_rad)
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
                      guidance_y: float = None) -> "Torpedo | None":
        """Drop a catalog torpedo with an optional absolute hit-envelope result.

        The catalog remains the default; callers may supply the intentionally
        difficulty-adjusted result used by the game level configuration.
        """
        if not self.airborne or self.torps <= 0:
            return None
        self.torps -= 1
        aim_x = target.x if guidance_x is None else guidance_x
        aim_y = target.y if guidance_y is None else guidance_y
        course = math.degrees(math.atan2(aim_x - self.x,
                                         -(aim_y - self.y))) % 360.0
        return Torpedo(self.x, self.y, course, target_depth_m, target, seq,
                       kill_dist_nm=(HELO_TORPEDO_PROFILE.hit_dist_nm
                                     if kill_dist_nm is None else kill_dist_nm),
                       kill_depth_m=kill_depth_m,
                       speed_kn=HELO_TORPEDO_PROFILE.speed_kn,
                       guidance_x=aim_x, guidance_y=aim_y,
                       range_nm=HELO_TORPEDO_PROFILE.range_nm)
