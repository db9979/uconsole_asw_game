"""Torpedo model: launch, commanded-datum wire guidance, and terminal search."""

import math

from src.core import config
from src.physics import torpedo_dyn
from src.data.catalog import CATALOG


def _required_torpedo_profile(key: str):
    profile = CATALOG.get_torpedo(key)
    if profile is None:
        raise RuntimeError(
            f"Kontaktkatalog unvollstaendig: Torpedo-Profil '{key}' fehlt")
    return profile


_FRIGATE_TORP_PROFILE = _required_torpedo_profile("frigate_torp")


def underwater_path_blocked(world, x0, y0, depth0, x1, y1, depth1):
    """Bounded collision/receiver query; lightweight callers may omit world."""
    if world is None:
        return False
    size = getattr(world, "size_nm", float("inf"))
    if not (0 <= x0 <= size and 0 <= y0 <= size
            and 0 <= x1 <= size and 0 <= y1 <= size):
        return True
    path = getattr(world, "sonar_path_blocked", None)
    if callable(path):
        return path(x0, y0, max(0.0, depth0), x1, y1, max(0.0, depth1))
    land = getattr(world, "on_land", lambda x, y: False)
    bottom = getattr(world, "depth_m", lambda x, y: float("inf"))
    count = min(64, max(1, math.ceil(math.hypot(x1 - x0, y1 - y0) / 0.05)))
    for i in range(count + 1):
        t = i / count
        x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
        if land(x, y) or bottom(x, y) <= depth0 + (depth1 - depth0) * t:
            return True
    return False


ASROC_HELIX_DEG_PER_S = 6.0
# Seeker discrimination: a new candidate must be this much louder than the
# held one to steal the lock; echoes without Doppler (stationary objects)
# are suppressed; overrun decoys are remembered and ignored.
SEEKER_LOCK_HYSTERESIS_DB = 6.0
SEEKER_NO_DOPPLER_DB = 10.0
SEEKER_DOPPLER_MIN_KN = 1.0
SEEKER_REJECT_MAX = 4


def seeker_level_db(weapon, candidate) -> float:
    """Received level of a candidate at a homing seeker (relative dB).

    Source level from the candidate's quietness/radiated level (a decoy's
    designed emission), spherical spreading, a depth-mismatch penalty and the
    Doppler gate against echoes from stationary objects."""
    distance = max(0.01, math.hypot(candidate.x - weapon.x, candidate.y - weapon.y))
    level = getattr(candidate, "acoustic_level_db", None)
    if level is None:
        quiet = getattr(candidate, "quiet_factor", None)
        level = (20.0 * math.log10(1.0 + 0.8 * (1.0 - quiet()))
                 if callable(quiet) else 0.0)
        offset = getattr(candidate, "source_level_offset_db", None)
        if callable(offset):
            level += offset()
    level -= 20.0 * math.log10(distance)
    depth = getattr(candidate, "depth", None)
    if depth is not None:
        level -= abs(depth - weapon.depth) / 10.0
    speed = getattr(candidate, "speed_kn", None)
    if speed is None and hasattr(candidate, "stype"):
        speed = getattr(candidate, "speed", None)
    if speed is not None and speed < SEEKER_DOPPLER_MIN_KN:
        level -= SEEKER_NO_DOPPLER_DB
    return level


def choose_seeker_target(weapon, viable, current):
    """Loudest viable candidate, holding the current lock unless a new one
    is louder by the hysteresis margin."""
    if not viable:
        return None
    scored = [(seeker_level_db(weapon, candidate), index, candidate)
              for index, candidate in enumerate(viable)]
    best_level, _index, best = max(scored, key=lambda item: (item[0], -item[1]))
    if current is not None:
        held = next((item for item in scored if item[2] is current), None)
        if held is not None and best_level < held[0] + SEEKER_LOCK_HYSTERESIS_DB:
            return current
    return best
WAKE_HOMING_THRESHOLD = 0.15


def _apply_warhead(body, slant_m: float) -> None:
    """Deliver shock-factor damage; fall back to the legacy hit call."""
    if getattr(body, "signature_key", None) is not None:
        amount = torpedo_dyn.surface_damage(slant_m)
    else:
        amount = torpedo_dyn.submarine_damage(slant_m)
    try:
        body.hit(amount)
    except TypeError:
        body.hit()


def radiated_source_db(speed_fraction: float) -> float:
    """Torpedo self noise: ~60 log v (cavitating propulsor at depth)."""
    return 60.0 * math.log10(max(speed_fraction, 0.05))


class Torpedo:
    # Exact speeds, envelopes, rates and timing below are gameplay tuning
    # values. They do not describe real weapon performance or doctrine.
    SPEED_KN = _FRIGATE_TORP_PROFILE.speed_kn
    RANGE_NM = _FRIGATE_TORP_PROFILE.range_nm
    KILL_DIST_NM = _FRIGATE_TORP_PROFILE.hit_dist_nm
    KILL_DEPTH_M = 15.0    # Tiefentoleranz
    TURN_DEG_PER_S = 8.0
    HOMING_TURN_DEG_PER_S = 15.0
    DEPTH_RATE_M_PER_S = 10.0
    WIRE_UPDATE_CADENCE_S = config.TORP_MIDCOURSE_UPDATE_S
    WIRE_STALE_S = 3.0
    WIRE_BREAK_S = 12.0

    def __init__(self, x_nm: float, y_nm: float, course_deg: float,
                 target_depth_m: float, target_sub, idx: int,
                   kill_dist_nm: float = None, kill_depth_m: float = None,
                   speed_kn: float = None, guidance_x: float = None,
                    guidance_y: float = None, range_nm: float = None,
                    profile=None, launch_origin: str | None = None,
                    launch_platform_id: int | None = None,
                    launch_weapon_key: str | None = None,
                    time_since_launch: float | None = None,
                    pattern: str = "snake", enable_nm: float | None = None):
        self.x = x_nm
        self.y = y_nm
        self.course = course_deg % 360.0
        self.depth = 5.0
        self.target_depth = target_depth_m
        self.target = target_sub
        self.idx = idx
        self.travel = 0.0
        self.state = "RUN"  # RUN, HIT, SASE
        self.profile_key = profile.key if profile is not None else "frigate_torp"
        self.launch_origin = launch_origin or (
            profile.used_by if profile is not None else "frigate")
        self.launch_platform_id = launch_platform_id
        self.launch_weapon_key = launch_weapon_key
        default_hit = profile.hit_dist_nm if profile is not None else self.KILL_DIST_NM
        default_speed = profile.speed_kn if profile is not None else self.SPEED_KN
        default_range = profile.range_nm if profile is not None else self.RANGE_NM
        self.kill_dist_nm = default_hit if kill_dist_nm is None else kill_dist_nm
        self.kill_depth_m = self.KILL_DEPTH_M if kill_depth_m is None else kill_depth_m
        self.speed_kn = default_speed if speed_kn is None else speed_kn
        self.range_nm = default_range if range_nm is None else range_nm
        # Keep RANGE_NM as the established public API for callers and saves.
        self.RANGE_NM = self.range_nm
        # Default is "already spooled up": direct construction (tests, legacy
        # saves) gets today's instant-cruise-speed behavior. Only real launch
        # sites pass time_since_launch=0.0 for the ramp-up.
        self.time_since_launch = (config.TORP_SPOOLUP_S if time_since_launch is None
                                  else time_since_launch)
        # Phase 8 physics state (saved): energy store in cruise seconds, motor
        # speed fraction (1 while powered, falling while coasting), vertical
        # rate, and the wire's ship-side payout/tension.
        self.energy_s = torpedo_dyn.energy_budget_s(self.range_nm, self.speed_kn)
        self.motor_fraction = 1.0
        self.depth_rate = 0.0
        self.wire_ship_out_nm = 0.0
        self.wire_stress_s = 0.0
        # Terminal search pattern and seeker enable point (operator settings
        # at launch; the 1.0.0 behaviour is snake at TORP_HOME_RANGE_NM).
        self.pattern = pattern if pattern in torpedo_dyn.SEARCH_PATTERNS else "snake"
        self.enable_nm = (config.TORP_HOME_RANGE_NM if enable_nm is None
                          else float(enable_nm))
        self._turns_done = 0.0       # helix progress, in full circles
        self.last_miss_m = None
        self.rejected_ids: list[int] = []
        self._search_phase = 0.0     # M15: Serpentin-Phase
        self._midcourse = course_deg % 360.0  # M15: Draht-Mittelkurs
        # The persisted timer also carries wire age.
        self._midcourse_timer = self.WIRE_UPDATE_CADENCE_S
        self.guidance_x = guidance_x
        self.guidance_y = guidance_y
        self.seeker_acquired = False
        self.terminal_active = False
        self._seeker_target = None
        if guidance_x is not None and guidance_y is not None:
            self._midcourse = self._bearing_to(guidance_x, guidance_y)

    @property
    def speed_nm_per_s(self) -> float:
        """Physikalische Geschwindigkeit in NM pro Simulationssekunde."""
        return config.kn_to_nm_per_s(self.speed_kn)

    def _spoolup_factor(self) -> float:
        """Motor-Hochlauf: 0..TORP_SPOOLUP_S linear von MIN_FRAC auf 1.0."""
        if self.time_since_launch >= config.TORP_SPOOLUP_S:
            return 1.0
        frac = self.time_since_launch / config.TORP_SPOOLUP_S
        return config.TORP_SPOOLUP_MIN_FRAC + (1.0 - config.TORP_SPOOLUP_MIN_FRAC) * frac

    def distance_to_target_nm(self) -> float:
        if self.target is None or getattr(self.target, "sunk", False):
            return float("inf")
        return math.hypot(self.target.x - self.x, self.target.y - self.y)

    def guidance_distance_nm(self) -> float:
        """Operator-visible distance to the observed fire-control solution."""
        if self.guidance_x is None or self.guidance_y is None:
            return float("inf")
        return math.hypot(self.guidance_x - self.x, self.guidance_y - self.y)

    @property
    def wire_state(self) -> str:
        """Current explicit wire state: ACTIVE, STALE, or BROKEN."""
        if self._midcourse_timer >= self.WIRE_BREAK_S:
            return "BROKEN"
        if (self.guidance_x is None or self.guidance_y is None
                or self._midcourse_timer >= self.WIRE_STALE_S):
            return "STALE"
        return "ACTIVE"

    def speed_fraction(self) -> float:
        """Current speed as a fraction of the catalog cruise speed."""
        return self._spoolup_factor() * self.motor_fraction

    def wire_tension_update(self, dt: float, ship_speed_kn: float,
                            ship_yaw_deg_s: float) -> None:
        """Pay out the ship-side spool and break the wire on overload."""
        if self.state != "RUN" or self.wire_state == "BROKEN":
            return
        self.wire_ship_out_nm += config.kn_to_nm_per_s(max(0.0, ship_speed_kn)) * dt
        overload = (ship_speed_kn > torpedo_dyn.WIRE_MAX_SHIP_KN
                    or abs(ship_yaw_deg_s) > torpedo_dyn.WIRE_MAX_SHIP_YAW_DEG_S)
        self.wire_stress_s = (self.wire_stress_s + dt) if overload else 0.0
        if (self.wire_stress_s >= torpedo_dyn.WIRE_TENSION_BREAK_S
                or self.wire_ship_out_nm >= torpedo_dyn.WIRE_SHIP_SPOOL_NM
                or self.travel >= self.range_nm * torpedo_dyn.WIRE_TORPEDO_SPOOL_FACTOR):
            self.break_wire()

    def break_wire(self) -> None:
        """Permanently reject further command updates for this run."""
        self._midcourse_timer = self.WIRE_BREAK_S

    def wire_update(self, x_nm: float, y_nm: float) -> bool:
        """Feed an observed contact position into the wire guidance loop."""
        if (self.state != "RUN" or self.seeker_acquired
                or self.wire_state == "BROKEN"
                or self._midcourse_timer < self.WIRE_UPDATE_CADENCE_S):
            return False
        self.guidance_x, self.guidance_y = x_nm, y_nm
        self._midcourse = self._bearing_to(x_nm, y_nm)
        self._midcourse_timer = 0.0
        return True

    def evaluate_seeker_candidates(self, candidates, world=None) -> object | None:
        """Return the best viable terminal contact, including decoys.

        Candidates only need position/depth attributes. The API deliberately
        accepts duck-typed objects so sensor tracks or decoys can be supplied
        later without coupling this weapon model to Game.
        """
        viable = []
        for candidate in candidates:
            if (candidate is None or getattr(candidate, "sunk", False)
                    or getattr(candidate, "dead", False)
                    or getattr(candidate, "state", None) == "SINKING"):
                continue
            distance = math.hypot(candidate.x - self.x, candidate.y - self.y)
            if distance > config.TORP_HOME_RANGE_NM:
                continue
            if underwater_path_blocked(world, self.x, self.y, self.depth,
                    candidate.x, candidate.y, getattr(candidate, "depth", self.target_depth)):
                continue
            if getattr(candidate, "id", None) in self.rejected_ids:
                continue
            viable.append(candidate)
        return choose_seeker_target(self, viable, self._seeker_target)

    def _bearing_to(self, x_nm: float, y_nm: float) -> float:
        return math.degrees(math.atan2(x_nm - self.x,
                                       -(y_nm - self.y))) % 360.0

    def update(self, dt: float, seeker_candidates=None, world=None,
               collision_candidates=()) -> None:
        if self.state != "RUN":
            return

        self.time_since_launch = min(
            config.TORP_SPOOLUP_S, self.time_since_launch + dt)
        self._midcourse_timer = min(
            self.WIRE_BREAK_S, self._midcourse_timer + dt)

        # Before terminal search the weapon follows only the commanded datum,
        # with a serpentine offset around that course. Once near the datum its
        # seeker may select one of the supplied contacts.
        # The existing save loader restores seeker_acquired and target but did
        # not previously need a separate terminal contact reference.
        if self.seeker_acquired and self._seeker_target is None:
            self._seeker_target = self.target
        self.terminal_active = self.terminal_active or self.seeker_acquired
        sub = self._seeker_target
        if self.seeker_acquired and self.evaluate_seeker_candidates([sub], world) is None:
            self.seeker_acquired = False
            self._seeker_target = sub = None
        desired = None
        wobble = 0.0
        turn = self.TURN_DEG_PER_S
        if self.launch_origin == "asroc" and not self.seeker_acquired:
            # Air-dropped payload: helical search around the splash point
            # while descending to the search depth.
            self.terminal_active = True
        # Normal activation is based on the commanded datum, never hidden truth.
        seeker_active = self.guidance_distance_nm() <= self.enable_nm
        if self.guidance_x is None or self.guidance_y is None:
            seeker_active = self.distance_to_target_nm() <= self.enable_nm
        self.terminal_active = self.terminal_active or self.seeker_acquired or seeker_active
        if self.terminal_active and seeker_candidates is not None:
            candidate = self.evaluate_seeker_candidates(seeker_candidates, world)
            if candidate is not None:
                self._seeker_target = self.target = candidate
                self.seeker_acquired = True
                sub = candidate
        if not self.seeker_acquired and self.terminal_active:
            candidates = ([self.target] if seeker_candidates is None
                          else seeker_candidates)
            self._seeker_target = self.evaluate_seeker_candidates(candidates, world)
            self.seeker_acquired = self._seeker_target is not None
            sub = self._seeker_target
            if self.seeker_acquired:
                self.target = self._seeker_target
        target_alive = (sub is not None and not getattr(sub, "sunk", False)
                        and not getattr(sub, "dead", False)
                        and getattr(sub, "state", None) != "SINKING")
        if self.seeker_acquired and target_alive:
            desired = self._bearing_to(sub.x, sub.y)
            self.target_depth = max(0.0, sub.depth)
            turn = self.HOMING_TURN_DEG_PER_S
        elif self.launch_origin == "asroc" and self.guidance_distance_nm() < 0.5:
            desired = (self.course + ASROC_HELIX_DEG_PER_S) % 360.0
        elif self.terminal_active and self.pattern in ("circle", "helix"):
            # Enabled without acquisition: a constant turn about the enable
            # point (circle) or an opening spiral (helix) instead of the snake.
            fraction_now = self.speed_fraction()
            rate = torpedo_dyn.pattern_turn_deg_s(
                self.pattern, self.speed_nm_per_s * max(0.0, fraction_now),
                self._turns_done)
            rate = min(rate, torpedo_dyn.turn_rate_deg_s(turn, fraction_now))
            desired = (self.course + rate * dt) % 360.0
            self._turns_done += rate * dt / 360.0
        else:
            # Vor der Eigenortung folgt der Torpedo nur Drahtdaten und sucht
            # um deren Kurs. Die wahre Zielposition korrigiert ihn hier nicht.
            self._search_phase += dt * 0.03
            if self.guidance_x is not None and self.guidance_y is not None:
                self._midcourse = self._bearing_to(
                    self.guidance_x, self.guidance_y)
            desired = (self._midcourse
                       + 15.0 * math.sin(self._search_phase)) % 360.0
            wobble = 8.0 * math.sin(self._search_phase * 0.7)

        # Tiefe ansteuern (im Suchlauf mit Wobble, sonst Zieltiefe).
        # Proportionaler Regelkreis: reicht auch bei kurzen Anflügen,
        # um in Zieltiefe zu treffen (lineares Tauchen kam zu spat an).
        old_depth = self.depth
        d_target = max(0.0, self.target_depth + wobble)
        fraction = self.speed_fraction()
        self.depth, self.depth_rate = torpedo_dyn.depth_step(
            self.depth, self.depth_rate, d_target, fraction, dt,
            self.DEPTH_RATE_M_PER_S)

        throttle = 1.0
        if desired is not None:
            diff = config.angle_diff_deg(desired, self.course)
            # Constant turning radius: the rate scales with speed.
            rate = torpedo_dyn.turn_rate_deg_s(turn, fraction)
            self.course = (self.course + config.clamp(
                diff, -rate * dt, rate * dt)) % 360.0
            # M15: bei starkem Ruderbedarf krabbeln, damit der Torpedo
            # nicht um das Ziel kreist: Kurs erst richten, dann anrennen.
            if abs(diff) > 60.0:
                throttle = 0.6
            else:
                throttle = 1.0 - 0.5 * max(
                    0.0, min(1.0, (abs(diff) - 30.0) / 30.0))
        # Energy: power ~ v^3; an empty store stops the motor and the weapon
        # coasts against drag until it is lost.
        effective = self._spoolup_factor() * throttle * self.motor_fraction
        if self.motor_fraction >= 1.0:
            self.energy_s -= torpedo_dyn.energy_rate(
                self._spoolup_factor() * throttle) * dt
            if self.energy_s <= 0.0:
                self.energy_s = 0.0
                self.motor_fraction = 1.0 - 1e-9
        else:
            self.motor_fraction = torpedo_dyn.coast_step(self.motor_fraction, dt)
            effective = self._spoolup_factor() * self.motor_fraction
        # Bewegung (Anti-Tunneling: Swept-Check über den ganzen Schritt)
        ox, oy = self.x, self.y
        step = self.speed_nm_per_s * dt * effective
        self.x += step * math.sin(math.radians(self.course))
        self.y -= step * math.cos(math.radians(self.course))
        self.travel += step
        # W2: Meeresstroemung - reiner Driftzusatz, kein Antrieb/keine Steuerung.
        current = getattr(world, "current_vec", None)
        if current is not None:
            cu, cv = current(self.x, self.y)
            self.x += config.kn_to_nm_per_s(cu) * dt
            self.y -= config.kn_to_nm_per_s(cv) * dt

        bodies = [(body, config.CIVILIAN_HIT_RADIUS_NM)
                  for body in collision_candidates if not body.sunk]
        if target_alive and not any(body is sub for body, _ in bodies):
            bodies.append((sub, self.kill_dist_nm))
        hits = []
        for body, radius in bodies:
            fraction = self._swept_hit_fraction(body, ox, oy, old_depth, radius)
            if fraction is not None:
                hits.append((fraction, body))
        for fraction, body in sorted(hits, key=lambda item: item[0]):
            hx, hy = ox + (self.x - ox) * fraction, oy + (self.y - oy) * fraction
            hd = old_depth + (self.depth - old_depth) * fraction
            if (not underwater_path_blocked(world, ox, oy, old_depth, hx, hy, hd)
                    and not underwater_path_blocked(world, hx, hy, hd,
                                                     body.x, body.y, body.depth)):
                if callable(getattr(body, "hit", None)):
                    self.x, self.y, self.depth = hx, hy, hd
                    self.travel -= step * (1.0 - fraction)
                    self.target = body
                    # Proximity fuze at closest approach: shock-factor damage.
                    horizontal = self._swept_dist(body, ox, oy) * 1852.0
                    slant = math.hypot(horizontal, getattr(body, "depth", hd) - hd)
                    self.last_miss_m = slant
                    self.state = "HIT"
                    _apply_warhead(body, slant)
                else:
                    # Overran a decoy: no hull, no detonation. Remember it and
                    # re-attack with the energy that is left.
                    identity = getattr(body, "id", None)
                    if identity is not None:
                        self.rejected_ids = (self.rejected_ids + [identity])[
                            -SEEKER_REJECT_MAX:]
                    self._seeker_target = None
                    self.seeker_acquired = False
                    self.target = None
                    continue
                return
        if (underwater_path_blocked(world, ox, oy, old_depth,
                                    self.x, self.y, self.depth)
                or self.motor_fraction < torpedo_dyn.COAST_SINK_FRACTION):
            self.state = "SASE"

    # --- radiated noise (heard by the target's sonar) ---------------------

    def source_level_offset_db(self) -> float:
        return radiated_source_db(self.speed_fraction())

    def quiet_factor(self) -> float:
        return config.ENEMY_TORP_QUIET

    def lofar_lines(self, t_sim: float = 0.0) -> list:
        """Propulsor tonals scale with motor speed."""
        if self.state != "RUN":
            return []
        f = 180.0 * max(0.1, self.speed_fraction())
        amplitude = min(1.0, 0.9 * self.speed_fraction())
        return [(f * 0.5, 0.4 * amplitude, 5.0), (f, amplitude, 8.0)]

    def _swept_hit_fraction(self, target, ox, oy, old_depth, radius):
        """First overlap of the horizontal hit circle and vertical tolerance."""
        dx, dy = self.x - ox, self.y - oy
        rx, ry = ox - target.x, oy - target.y
        a = dx * dx + dy * dy
        c = rx * rx + ry * ry - radius * radius
        low, high = 0.0, 1.0
        if a <= 1e-20:
            if c > 0:
                return None
        else:
            b = 2.0 * (rx * dx + ry * dy)
            discriminant = b * b - 4.0 * a * c
            if discriminant < 0:
                return None
            root = math.sqrt(discriminant)
            low, high = max(low, (-b - root) / (2 * a)), min(high, (-b + root) / (2 * a))
        dz = self.depth - old_depth
        if abs(dz) <= 1e-12:
            if abs(target.depth - old_depth) > self.kill_depth_m:
                return None
        else:
            first = (target.depth - self.kill_depth_m - old_depth) / dz
            last = (target.depth + self.kill_depth_m - old_depth) / dz
            low, high = max(low, min(first, last)), min(high, max(first, last))
        return low if low <= high else None

    def _swept_dist(self, sub, ox: float, oy: float) -> float:
        """Min. Distanz Ziel-Position -> Torpedo-Strecke (ox,oy)->(x,y)."""
        fx, fy = self.x - ox, self.y - oy
        l2 = fx * fx + fy * fy
        if l2 < 1e-12:
            return math.hypot(sub.x - self.x, sub.y - self.y)
        t = ((sub.x - ox) * fx + (sub.y - oy) * fy) / l2
        t = config.clamp(t, 0.0, 1.0)
        return math.hypot(ox + t * fx - sub.x, oy + t * fy - sub.y)


class EnemyTorpedo:
    """Feindlicher Torpedo (M5): Vorhaltkurs mit terminaler Eigenortung.

    Ab der Kontakt-DB auch passiv auffindbar: lautes Hochton-Kreischen,
    das im LOFAR mit fallender Frequenz sichtbar wird (Sonarkontakt
    mit kind='torpedo').
    """

    _next_id = 2000000

    def __init__(self, x_nm: float, y_nm: float, course_deg: float,
                   depth_m: float, idx: int, profile=None,
                   guidance_x: float = None, guidance_y: float = None, *,
                   launch_platform_id: int | None = None,
                   launch_weapon_key: str | None = None,
                   time_since_launch: float | None = None):
        self.id = EnemyTorpedo._next_id
        EnemyTorpedo._next_id += 1
        self.x = x_nm
        self.y = y_nm
        self.course = course_deg % 360.0
        self.depth = depth_m
        self.idx = idx
        self.travel = 0.0
        self.state = "RUN"  # RUN, HIT, SASE
        self.torpedo_class = "enemy"
        prof = profile or _required_torpedo_profile("enemy_torp")
        self.profile = prof
        self.profile_key = prof.key
        self.speed_kn = prof.speed_kn
        self.range_nm = prof.range_nm
        self.kill_dist_nm = prof.hit_dist_nm
        self.guidance_x = guidance_x
        self.guidance_y = guidance_y
        self.launch_platform_id = launch_platform_id
        self.launch_weapon_key = launch_weapon_key
        self.terminal_active = False
        self.seeker_acquired = False
        self._seeker_target = None
        # Default is "already spooled up" (see Torpedo); only real launch
        # sites pass time_since_launch=0.0 for the ramp-up.
        self.time_since_launch = (config.TORP_SPOOLUP_S if time_since_launch is None
                                  else time_since_launch)
        # Phase 8 physics state (saved).
        self.energy_s = torpedo_dyn.energy_budget_s(self.range_nm, self.speed_kn)
        self.motor_fraction = 1.0
        self.depth_rate = 0.0
        self.target_depth = depth_m

    def _spoolup_factor(self) -> float:
        return Torpedo._spoolup_factor(self)

    def speed_fraction(self) -> float:
        return self._spoolup_factor() * self.motor_fraction

    def source_level_offset_db(self) -> float:
        return radiated_source_db(self.speed_fraction())

    @property
    def dead(self) -> bool:
        return self.state != "RUN"

    @property
    def speed_nm_per_s(self) -> float:
        return config.kn_to_nm_per_s(self.speed_kn)

    def _candidate(self, candidates, world=None):
        viable = []
        for index, candidate in enumerate(candidates):
            if (candidate is None or getattr(candidate, "dead", False)
                    or getattr(candidate, "sunk", False)):
                continue
            distance = math.hypot(candidate.x - self.x, candidate.y - self.y)
            if distance > 3.0 or underwater_path_blocked(
                    world, self.x, self.y, self.depth, candidate.x, candidate.y,
                    getattr(candidate, "depth", 5.0)):
                continue
            viable.append(candidate)
        return choose_seeker_target(self, viable, self._seeker_target)

    def update(self, dt: float, ship, world=None, seeker_candidates=()) -> None:
        if self.state != "RUN":
            return
        self.time_since_launch = min(
            config.TORP_SPOOLUP_S, self.time_since_launch + dt)
        if self.seeker_acquired and (self._seeker_target is None
                or getattr(self._seeker_target, "dead", False)
                or getattr(self._seeker_target, "sunk", False)):
            self.seeker_acquired = False
            self._seeker_target = None
        if self.guidance_x is None or self.guidance_y is None:
            seeker_active = math.hypot(ship.x - self.x, ship.y - self.y) <= 3.0
        else:
            seeker_active = math.hypot(
                self.guidance_x - self.x, self.guidance_y - self.y) <= 3.0
        self.terminal_active = self.terminal_active or seeker_active
        if self.terminal_active:
            candidate = self._candidate([ship, *seeker_candidates], world)
            if candidate is not None:
                self._seeker_target = candidate
                self.seeker_acquired = True
        target = self._seeker_target
        fraction = self.speed_fraction()
        desired = None
        if target is not None:
            desired = math.degrees(math.atan2(
                target.x - self.x, -(target.y - self.y))) % 360.0
            # Homing on a surface ship: run up to keel depth.
            self.target_depth = min(self.target_depth,
                                    max(3.0, getattr(target, "depth", 5.0) + 1.0))
        else:
            wake = getattr(ship, "wake_strength_at", None)
            if wake is not None and wake(self.x, self.y) >= WAKE_HOMING_THRESHOLD:
                # Wake homing: follow the bubble trail toward its young end.
                desired = self._wake_course(ship)
        if desired is not None:
            diff = config.angle_diff_deg(desired, self.course)
            rate = torpedo_dyn.turn_rate_deg_s(self.TURN_DEG_PER_S, fraction)
            self.course = (self.course + config.clamp(
                diff, -rate * dt, rate * dt)) % 360.0
        self.depth, self.depth_rate = torpedo_dyn.depth_step(
            self.depth, self.depth_rate, self.target_depth, fraction, dt)
        if self.motor_fraction >= 1.0:
            self.energy_s -= torpedo_dyn.energy_rate(self._spoolup_factor()) * dt
            if self.energy_s <= 0.0:
                self.energy_s = 0.0
                self.motor_fraction = 1.0 - 1e-9
        else:
            self.motor_fraction = torpedo_dyn.coast_step(self.motor_fraction, dt)
        ox, oy = self.x, self.y
        step = self.speed_nm_per_s * dt * self.speed_fraction()
        self.x += step * math.sin(math.radians(self.course))
        self.y -= step * math.cos(math.radians(self.course))
        self.travel += step
        # W2: Meeresstroemung - reiner Driftzusatz, kein Antrieb/keine Steuerung.
        current = getattr(world, "current_vec", None)
        if current is not None:
            cu, cv = current(self.x, self.y)
            self.x += config.kn_to_nm_per_s(cu) * dt
            self.y -= config.kn_to_nm_per_s(cv) * dt

        if underwater_path_blocked(world, ox, oy, self.depth,
                                   self.x, self.y, self.depth):
            self.state = "SASE"
        elif (target is not None
              and Torpedo._swept_dist(self, target, ox, oy) <= self.kill_dist_nm
              and not underwater_path_blocked(world, self.x, self.y, self.depth,
                                               target.x, target.y,
                                               getattr(target, "depth", 5.0))):
            if target is ship:
                self.state = "HIT"
            else:
                self.state = "SASE"
                if hasattr(target, "dead"):
                    target.dead = True
                    target.state = "SASE"
        elif self.motor_fraction < torpedo_dyn.COAST_SINK_FRACTION:
            self.state = "SASE"

    TURN_DEG_PER_S = 6.0

    def _wake_course(self, ship) -> float:
        """Course along the wake toward its youngest sampled point."""
        points = getattr(ship, "wake", ())
        if not points:
            return self.course
        youngest = points[-1]
        return math.degrees(math.atan2(youngest[0] - self.x,
                                       -(youngest[1] - self.y))) % 360.0

    # --- Duck-Type-Interface wie Sub/Animal (passives Sonar) ---

    def distance_nm(self, ship) -> float:
        return math.hypot(self.x - ship.x, self.y - ship.y)

    def bearing_from_frigate(self, ship) -> float:
        dx = self.x - ship.x
        dy = self.y - ship.y
        return math.degrees(math.atan2(dx, -dy)) % 360.0

    def quiet_factor(self) -> float:
        return config.ENEMY_TORP_QUIET

    def lofar_lines(self, t_sim: float = 0.0) -> list:
        """Propulsor whine: frequency and level follow the motor speed as the
        battery sags over the run (150 -> 90 Hz), plus the subharmonic."""
        if self.state != "RUN":
            return []
        used = 1.0 - self.energy_s / max(
            torpedo_dyn.energy_budget_s(self.range_nm, self.speed_kn), 1e-9)
        f = (150.0 - 60.0 * min(1.0, max(0.0, used))) * max(0.1, self.speed_fraction())
        amplitude = min(1.0, 0.9 * self.speed_fraction())
        return [(f * 0.5, 0.39 * amplitude, 5.0), (f, amplitude, 8.0)]

    def broadband(self) -> dict:
        prof = self.profile
        if prof is not None and prof.acoustic is not None \
                and prof.acoustic.broadband is not None \
                and self.state == "RUN":
            lv, lo, hi = prof.acoustic.broadband
            return {"level": lv, "low_hz": lo, "high_hz": hi}
        return {}

    def acoustic_signature(self) -> str:
        if self.state != "RUN":
            return ""
        prof = self.profile
        text = prof.acoustic.signature_text if (prof and prof.acoustic) \
            else "hochfrequentes Kreischen"
        return f"mechanisch · {text} (Torpedo?)"
