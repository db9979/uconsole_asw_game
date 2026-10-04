"""M15: Hubschrauber HSP-5 (Sea Lynx) – Sonarbojen + Leichttorpedos.

Zustände: HANGAR | AUF (Einsatz) | ZURUECK (Rückkehr).  A launch order
first prepares the aircraft in the hangar for ``config.HELO_PREP_S``.
Bewegung, Treibstoff und Zeitfenster verwenden dieselbe Simulationszeit.

Flight physics: hovering (dipping) needs more power than cruise, so fuel
burns faster; in the hover the wind pushes the aircraft off its hover point
and the pilot holds it back (a small steady downwind offset).  Launch and
recovery wait for a deck-motion window (roll/pitch limits).
"""

import math
from dataclasses import dataclass

from src.core import config
from src.sensors.mad import MAD_SPEED_KN
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


HOVER_FUEL_FACTOR = 1.3          # hover power / best-range cruise power
HOVER_DRIFT_FRACTION = 0.1       # un-corrected share of the wind in the hover
HOVER_HOLD_GAIN_PER_S = 0.2      # pilot position-hold gain
DECK_ROLL_LIMIT_DEG = 8.0
DECK_PITCH_LIMIT_DEG = 3.5


# A launch or recovery needs a quiet period: the deck inside its limits for
# this long (the flight deck officer waits for the lull between wave groups).
DECK_WINDOW_S = 6.0
DECK_QUIET_MAX_S = 3600.0


def deck_within_limits(roll_deg: float, pitch_deg: float) -> bool:
    return abs(roll_deg) <= DECK_ROLL_LIMIT_DEG and abs(pitch_deg) <= DECK_PITCH_LIMIT_DEG


def deck_quiet_step(quiet_s: float, roll_deg: float, pitch_deg: float, dt: float) -> float:
    """Seconds the deck has stayed inside its limits after one step."""
    if not deck_within_limits(roll_deg, pitch_deg):
        return 0.0
    return min(DECK_QUIET_MAX_S, quiet_s + dt)


def deck_window_open(quiet_s: float, roll_deg: float = 0.0, pitch_deg: float = 0.0) -> bool:
    """A launch/recovery window: inside the limits now and quiet long enough."""
    return deck_within_limits(roll_deg, pitch_deg) and quiet_s >= DECK_WINDOW_S - 1e-6


# Plan 1.3 phase 6: sonobuoy patterns (a queue of drop points the helicopter
# flies one after the other with the ordinary single drop) and the MAD run.
BUOY_PATTERNS = ("single", "field", "barrier", "circle")
PATTERN_FIELD_SPACING_NM = 1.5     # 2x2 field
PATTERN_BARRIER_SPACING_NM = config.BUOY_SPACING_NM
PATTERN_CIRCLE_RADIUS_NM = 1.5
PATTERN_MAX_BUOYS = 4
PATTERN_DROP_RADIUS_NM = 0.3


def plan_buoy_pattern(kind: str, x_nm: float, y_nm: float, bearing_deg: float,
                      count: int) -> list[tuple[float, float]]:
    """Drop points of a pattern about (x, y): a 2x2 field, a barrier across
    ``bearing_deg`` or a circle. ``count`` buoys at most (the pattern's own
    size caps it); ``single`` plans nothing."""
    count = max(0, min(int(count), PATTERN_MAX_BUOYS))
    if kind == "field":
        half = PATTERN_FIELD_SPACING_NM / 2.0
        points = [(x_nm - half, y_nm - half), (x_nm + half, y_nm - half),
                  (x_nm + half, y_nm + half), (x_nm - half, y_nm + half)]
    elif kind == "barrier":
        across = math.radians((bearing_deg + 90.0) % 360.0)
        offsets = [(index - (count - 1) / 2.0) * PATTERN_BARRIER_SPACING_NM
                   for index in range(count)]
        points = [(x_nm + offset * math.sin(across), y_nm - offset * math.cos(across))
                  for offset in offsets]
    elif kind == "circle":
        points = [(x_nm + PATTERN_CIRCLE_RADIUS_NM * math.sin(math.radians(angle)),
                   y_nm - PATTERN_CIRCLE_RADIUS_NM * math.cos(math.radians(angle)))
                  for angle in (0.0, 90.0, 180.0, 270.0)]
    else:
        points = []
    return [(round(px, 4), round(py, 4)) for px, py in points[:count]]


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
        self.hover_x = None
        self.hover_y = None
        # Buoy pattern in progress (kind and the drop points still to fly).
        self.pattern = "single"
        self.pattern_queue = []
        # MAD run: low and slow, dipping sonar stowed.
        self.mad_mode = False
        # Surface-search radar switch: radiates while airborne with the
        # dipping sonar stowed (a submarine's ESM hears it); off runs silent.
        self.radar_on = True
        # Start preparation: None when no launch is ordered, else the
        # seconds left in the hangar (0: ready, waiting for the deck window).
        self.prep_s = None
        # Speed over the last step (display only, not saved): 0 in the
        # hover, on the deck or holding over its waypoint.
        self.ground_speed_kn = 0.0

    @property
    def preparing(self) -> bool:
        return self.state == "HANGAR" and self.prep_s is not None

    @property
    def prep_ready(self) -> bool:
        return self.preparing and self.prep_s <= 0.0

    def order_prep(self) -> None:
        """Start the preparation (an order already running keeps its time)."""
        if self.state == "HANGAR" and self.prep_s is None:
            self.prep_s = config.HELO_PREP_S

    def cancel_prep(self) -> bool:
        if not self.preparing:
            return False
        self.prep_s = None
        return True

    @property
    def speed_kn(self) -> float:
        return MAD_SPEED_KN if self.mad_mode else self.SPEED_KN

    @property
    def airborne(self) -> bool:
        return self.state in ("AUF", "ZURUECK")

    def launch(self, frigate) -> None:
        """Start with the remaining finite mission loadout."""
        self.state = "AUF"
        self.prep_s = None
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

    def update(self, dt: float, frigate, world, recovery_available: bool = True,
               fuel_factor: float = 1.0) -> None:
        """dt in Simulationssekunden. Haelt Patrouillen-Offset vor der
        Fregatte (AUF) bzw. fliegt zurück (ZURUECK)."""
        self.dip_ping_cooldown = max(0.0, self.dip_ping_cooldown - dt)
        self.ground_speed_kn = 0.0
        if self.preparing:
            self.prep_s = max(0.0, self.prep_s - dt)
        if not self.airborne:
            return
        # fuel_factor: extra power for anti-/de-icing in icing conditions.
        self.fuel_s = max(0.0, self.fuel_s - dt * max(1.0, fuel_factor) * (
            HOVER_FUEL_FACTOR if self.hovering else 1.0))
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
            self.mad_mode = False
            self.pattern_queue = []
            self.pattern = "single"
            self.dip_depth_m = 0.0
            self.dip_water_depth_m = 0.0
            return
        if self.hovering:
            self._hold_hover(dt, world)
            return
        self.hover_x = self.hover_y = None
        if self.state == "ZURUECK":
            self.mad_mode = False
            self.pattern_queue = []
            self.pattern = "single"
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
            step = config.kn_to_nm_per_s(self.speed_kn) * dt
            self.ground_speed_kn = self.speed_kn
            self.x += step * math.sin(math.radians(self.course))
            self.y -= step * math.cos(math.radians(self.course))

    def _hold_hover(self, dt: float, world) -> None:
        if self.hover_x is None or self.hover_y is None:
            self.hover_x, self.hover_y = self.x, self.y
        wind = getattr(world, "wind_speed_kn", 0.0) if world is not None else 0.0
        towards = math.radians((getattr(world, "wind_from_deg", 0.0) + 180.0) % 360.0
                               if world is not None else 0.0)
        drift = config.kn_to_nm_per_s(wind) * HOVER_DRIFT_FRACTION * dt
        self.x += drift * math.sin(towards)
        self.y -= drift * math.cos(towards)
        hold = min(1.0, HOVER_HOLD_GAIN_PER_S * dt)
        self.x += (self.hover_x - self.x) * hold
        self.y += (self.hover_y - self.y) * hold

    def water_entry_clear(self, world=None) -> bool:
        """Require in-world water deep enough for the modeled 5 m entry."""
        return (world is None or (
            0 <= self.x <= world.size_nm and 0 <= self.y <= world.size_nm
            and not world.on_land(self.x, self.y)
            and getattr(world, "depth_m", lambda x, y: 1000.0)(self.x, self.y) > 5.0))

    def deploy_buoy(self, seq: int, world=None,
                    mode: str = "PASSIVE") -> Sonobuoy | None:
        """Drop one buoy at the helicopter's measured current position."""
        if not self.airborne or self.buoys_left <= 0:
            return None
        if not self.water_entry_clear(world):
            return None
        self.buoys_left -= 1
        return Sonobuoy(self.x, self.y, seq, mode)

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
        if guidance_x is None or guidance_y is None:
            # Every caller passes the release datum. Without one the weapon
            # runs unguided on the helicopter's heading; it never aims at
            # the hidden target.
            aim_x = aim_y = None
            course = self.course
        else:
            aim_x, aim_y = guidance_x, guidance_y
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
