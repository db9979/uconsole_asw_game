"""Fregatte-Modell: Position, Kurs, Geschwindigkeit, Lärmpegel."""

import dataclasses
import math

from src.core import config
from src.physics import ship_dynamics as dyn
from src.world.grounding import DEFAULT_HULL_SPEC

KN = dyn.KN


# Plan 1.3 phase 8: propulsion plant selection (fictional CODOG frigate).
PLANT_MODES = ("AUTO", "DIESEL", "TURBINE")
PLANT_DIESEL_MAX_KN = 18.0
PLANT_DIESEL_NOISE = 0.63      # about -4 dB
PLANT_DIESEL_FUEL = 0.90
PLANT_TURBINE_NOISE = 1.41     # about +3 dB
PLANT_TURBINE_FUEL = 1.25
# The loudest the frigate gets (cavitating at flank on the AUTO plant); the
# turbine plant and a bow-down trim never push the level past it.
NOISE_LEVEL_MAX = 0.85 + 0.02 * (config.SHIP_SPEED_MAX_KN - config.CAVITATION_KN)


class Ship:
    PLANT_MODES = PLANT_MODES

    def __init__(self, x_nm: float, y_nm: float, course_deg: float = 0.0,
                 speed_kn: float = config.SHIP_SPEED_START_KN):
        self.x = x_nm
        self.y = y_nm
        self.course = course_deg % 360.0
        self.speed = speed_kn
        self.target_speed = speed_kn
        self.target_course = course_deg % 360.0
        self.turn_rate_scale = 1.0  # M5: gestörte Brücke = trägeres Ruder
        self.rudder_angle = 0.0
        self.yaw_rate = 0.0
        self.order_idx = config.TELEGRAPH_DEFAULT  # M10: Motorenbefehl
        self.hull_spec = DEFAULT_HULL_SPEC
        self.astern = False
        self.speed_cap = config.SHIP_SPEED_MAX_KN
        self.quiet_mode = False
        # Noise of the crew's mishaps and voices (game_noise, recomputed each substep).
        self.crew_noise = 0.0
        self.plant_mode = "AUTO"
        self.trim_noise = 0.0        # from DamageModel.trim_noise_boost(), per tick
        self.fuel_capacity_kg = config.SHIP_FUEL_CAPACITY_KG
        self.fuel_kg = self.fuel_capacity_kg
        self.grounding_latched = False
        self.grounding_contact = None
        self.last_safe_pose = (self.x, self.y, self.course)
        self.last_impact_speed_kn = 0.0
        self.roll = 0.0
        self.pitch = 0.0
        self.roll_rate = 0.0
        self.pitch_rate = 0.0
        # Seconds the flight deck has been inside its motion limits (saved);
        # a ship starts at rest, so the deck starts quiet.
        self.deck_quiet_s = 60.0
        self._clock = 0.0
        # Derived each tick from damage control (not saved state).
        self.flood_percent = 0.0
        self.steering_jammed = False
        self.stabilizers_ok = True
        self.sea_state = 0.0
        # Wake ring: [x_nm, y_nm, clock_s, speed_kn], newest last.
        self.wake: list[list[float]] = []

    # --- Steuerung (dt = reelle Sekunden, turn_dir/speed_dir in -1/0/+1) ---

    def steer_input(self, dt: float, turn_dir: int, speed_dir: int) -> None:
        if turn_dir:
            self.target_course = (
                self.target_course
                + turn_dir * config.SHIP_TURN_INPUT_DEG_PER_S * dt) % 360.0
        if speed_dir:
            self.target_speed = config.clamp(
                self.target_speed + speed_dir * config.SHIP_SPEED_INPUT_KN_PER_S * dt,
                config.SHIP_SPEED_MIN_KN, config.SHIP_SPEED_MAX_KN)

    # --- M10: Telegraph & Maschinenraum ---

    @property
    def telegraph(self) -> str:
        """Name des aktuellen Motorenbefehls (STOP/SLOW/HALF/FULL/FLANK)."""
        if self.astern:
            return "ASTERN"
        return config.TELEGRAPH_ORDERS[self.order_idx][0]

    def cycle_telegraph(self, delta: int) -> None:
        """Motorenbefehl umschalten, ohne von STOP auf FLANK zu springen."""
        if self.astern:
            if delta > 0:
                self.astern = False
                self.order_idx = 0
                self.target_speed = 0.0
            return
        if self.order_idx == 0 and delta < 0:
            self.astern = True
            self.target_speed = config.ASTERN_SPEED_KN
            return
        self.order_idx = config.clamp(self.order_idx + delta, 0,
                                       len(config.TELEGRAPH_ORDERS) - 1)
        self.target_speed = config.TELEGRAPH_ORDERS[self.order_idx][1]

    @property
    def grounded(self) -> bool:
        return self.grounding_latched

    # --- propulsion state (pure functions of the saved state) -------------

    def effective_target_kn(self) -> float:
        target = min(self.target_speed, self.speed_cap,
                     12.0 if self.quiet_mode else self.speed_cap,
                     PLANT_DIESEL_MAX_KN if self.plant_mode == "DIESEL" else self.speed_cap)
        if self.fuel_kg <= 0.0 or (self.grounding_latched and not self.astern):
            return 0.0
        return max(0.0, target)

    def mass_kg(self) -> float:
        """Displacement: design load less burnt fuel plus floodwater."""
        hull = dyn.HULL
        return (hull.mass_design_kg - (self.fuel_capacity_kg - self.fuel_kg)
                + hull.flood_kg_per_percent * max(0.0, self.flood_percent))

    def _propulsion(self) -> tuple[float, float, bool]:
        """(shaft rev/s, thrust N, braking) for the current state."""
        hull = dyn.HULL
        target = self.effective_target_kn() * KN
        v = self.speed * KN
        if v > target + 0.15:
            return 0.0, hull.brake_thrust_n, True
        c = hull.rpm_per_mps / 60.0
        rps = min(hull.steady_rps(target), c * v + hull.load_up_rps)
        return rps, hull.thrust_n(rps, v), False

    @property
    def shaft_immersion_m(self) -> float:
        """Propeller depth; a bow-down pitch lifts the stern screws."""
        hull = dyn.HULL
        return hull.shaft_immersion_m + 0.5 * hull.length_m * math.sin(
            math.radians(self.pitch))

    @property
    def cavitating(self) -> bool:
        """Blade-tip cavitation from the cavitation number (sigma).

        Calibrated to start at CAVITATION_KN in calm water; heavy pitching
        that lifts the propellers makes it start earlier."""
        if self.fuel_kg <= 0.0:
            return False
        rps, _thrust, braking = self._propulsion()
        if braking:
            rps = dyn.HULL.steady_rps(self.speed * KN)
        sigma = dyn.HULL.cavitation_number(rps, self.speed * KN,
                                           self.shaft_immersion_m)
        return sigma <= dyn.HULL.cavitation_sigma + 1e-12

    def rpm(self) -> float:
        """Shaft revolutions for the engine-room display."""
        if self.fuel_kg <= 0.0:
            return 0.0
        rps, _thrust, braking = self._propulsion()
        return max(dyn.HULL.idle_rpm, 0.0 if braking else rps * 60.0)

    @staticmethod
    def max_rpm() -> float:
        return dyn.HULL.steady_rps(config.SHIP_SPEED_MAX_KN * KN) * 60.0

    def fuel_burn_kg_h(self) -> float:
        """Hotel load plus fuel for the power the propellers deliver now."""
        if self.fuel_kg <= 0.0:
            return 0.0
        hull = dyn.HULL
        rps, thrust, braking = self._propulsion()
        if braking:
            power = thrust * max(self.speed * KN, 1.0) / hull.propulsive_efficiency
        else:
            power = hull.shaft_power_w(max(0.0, thrust), rps)
        propulsion = hull.sfc_kg_per_j * power * 3600.0
        if self.astern:
            propulsion *= config.SHIP_FUEL_ASTERN_FACTOR
        if self.plant_mode == "TURBINE":
            propulsion *= PLANT_TURBINE_FUEL
        elif self.plant_mode == "DIESEL":
            propulsion *= PLANT_DIESEL_FUEL
        return config.SHIP_FUEL_HOTEL_KG_H + propulsion

    def fuel_endurance_h(self) -> float | None:
        burn = self.fuel_burn_kg_h()
        return self.fuel_kg / burn if burn > 0.0 else None

    def fuel_range_nm(self) -> float | None:
        endurance = self.fuel_endurance_h()
        if endurance is None or self.speed <= 0.0:
            return None
        return endurance * self.speed

    def update_fuel(self, dt: float) -> None:
        self.fuel_kg = max(0.0, self.fuel_kg - self.fuel_burn_kg_h() * dt / 3600.0)
        if self.fuel_kg <= 0.0:
            self.astern = False
            self.order_idx = 0
            self.target_speed = 0.0

    # --- Physik ---

    def update(self, dt: float, world=None, list_bias_deg: float = 0.0):
        """dt in Simulationssekunden; bei 1x identisch zu Echtzeit.

        list_bias_deg: current hull list from DamageModel.list_deg(), passed
        in fresh each tick (not stored) so a listing ship persistently pulls
        toward its heavier side and needs rudder correction to hold course.
        """

        start_pose = (self.x, self.y, self.course)
        hull = dyn.HULL
        if world is not None:
            self.sea_state = float(getattr(world, "effective_sea_state",
                                           getattr(world, "sea_state", 0.0)))
        # Steering: the rudder slews toward the autopilot order unless the
        # steering gear is disabled; yaw follows the first-order Nomoto model
        # r_ss = K (V/L) delta, so the turning circle is nearly speed
        # independent and a stopped ship does not turn.
        diff = config.angle_diff_deg(self.target_course, self.course)
        desired_rudder = config.clamp(
            diff * 0.75 - self.yaw_rate * config.SHIP_YAW_DAMPING,
            -config.SHIP_MAX_RUDDER_DEG, config.SHIP_MAX_RUDDER_DEG)
        if not self.steering_jammed:
            rudder_step = config.SHIP_RUDDER_RATE_DEG_PER_S * self.turn_rate_scale * dt
            self.rudder_angle += config.clamp(
                desired_rudder - self.rudder_angle, -rudder_step, rudder_step)
        v_mps = self.speed * KN
        steady_yaw = math.degrees(
            hull.nomoto_k * (v_mps / hull.length_m)
            * math.radians(self.rudder_angle)) * self.turn_rate_scale
        # Damage list pulls the bow toward the low side, again scaled by
        # the flow past the hull (no spin in place).
        steady_yaw += list_bias_deg * config.SHIP_LIST_YAW_GAIN * min(
            1.5, self.speed / 10.0)
        tau = config.clamp(hull.nomoto_t_s * (config.TELEGRAPH_ORDERS[3][1] * KN)
                           / max(v_mps, 0.5), config.SHIP_YAW_RESPONSE_S * 0.5,
                           config.SHIP_YAW_RESPONSE_S * 6.0)
        self.yaw_rate = steady_yaw + (self.yaw_rate - steady_yaw) * math.exp(-dt / tau)
        self.course = (self.course + self.yaw_rate * dt) % 360.0

        # Surge: thrust against resistance (exact Riccati integration).
        effective_target = self.effective_target_kn()
        extra = (hull.added_resistance_n(self.sea_state)
                 + hull.turn_resistance_n(self.yaw_rate))
        speed_mps, _rps, _braking = dyn.surge_step(
            hull, self.speed * KN, effective_target * KN, self.mass_kg(), dt,
            extra_resistance=extra)
        self.speed = min(config.SHIP_SPEED_MAX_KN, speed_mps / KN)

        # Physikalische Bewegung (W3: Land-Rueckstoss)
        # Nautisch: 0° = Nord/-y, 90° = Ost/+x (konsistent zu Peilungen)
        step = config.kn_to_nm_per_s(self.speed) * dt * (-1.0 if self.astern else 1.0)
        nx = self.x + step * math.sin(math.radians(self.course))
        ny = self.y - step * math.cos(math.radians(self.course))
        # W2: Meeresstroemung - reiner Driftzusatz, kein Antrieb/keine Steuerung.
        current = getattr(world, "current_vec", None)
        if current is not None:
            cu, cv = current(self.x, self.y)
            nx += config.kn_to_nm_per_s(cu) * dt
            ny -= config.kn_to_nm_per_s(cv) * dt
        contact = self._advance(start_pose, nx, ny, world)
        self._update_roll_pitch(dt, world, list_bias_deg)
        self._update_wake(dt)
        return contact

    # --- sinkage ---------------------------------------------------------------

    def dynamic_draft_m(self, water_depth_m: float | None = None) -> float:
        """Hydrostatic draft from displacement plus squat in shallow water."""
        hull = dyn.HULL
        draft = dyn.hydrostatic_draft_m(hull, self.mass_kg())
        if water_depth_m is not None:
            draft += dyn.squat_m(hull, self.speed, water_depth_m, draft)
        return draft

    @property
    def trim_deg(self) -> float:
        """Dynamic trim by the stern, growing with Froude number squared."""
        froude = self.speed * KN / math.sqrt(dyn.G * dyn.HULL.length_m)
        return 1.2 * froude * froude

    # --- wake ----------------------------------------------------------------

    def _update_wake(self, dt: float) -> None:
        hull = dyn.HULL
        last = self.wake[-1][2] if self.wake else -1e9
        if self.speed >= 3.0 and self._clock - last >= hull.wake_sample_s:
            self.wake.append([self.x, self.y, self._clock, self.speed])
            del self.wake[:-hull.wake_max_points]
        cutoff = self._clock - 4.0 * hull.wake_decay_s
        while self.wake and self.wake[0][2] < cutoff:
            self.wake.pop(0)

    def wake_strength_at(self, x_nm: float, y_nm: float,
                         radius_nm: float = 0.15) -> float:
        """0..1 bubble density of the own wake near a point."""
        hull = dyn.HULL
        decay = hull.wake_decay_s / (1.0 + 0.25 * self.sea_state)
        best = 0.0
        for px, py, t, speed in self.wake:
            if math.hypot(px - x_nm, py - y_nm) <= radius_nm:
                best = max(best, (speed / config.SHIP_SPEED_REFERENCE_KN)
                           * math.exp(-(self._clock - t) / decay))
        return min(1.0, best)

    def _advance(self, start_pose, nx: float, ny: float, world):
        """Advance to the first safe swept pose and latch physical contact."""
        if world is None:
            self.x, self.y = nx, ny
            self.last_safe_pose = (self.x, self.y, self.course)
            return None
        if self.grounding_latched and not self.astern:
            self.x, self.y, self.course = self.last_safe_pose
            self.speed = 0.0
            return None
        depth_query = getattr(world, "depth_m", None)
        hull = self.hull_spec
        if depth_query is not None:
            draft = self.dynamic_draft_m(depth_query(start_pose[0], start_pose[1]))
            hull = dataclasses.replace(self.hull_spec, draft_m=max(0.5, draft))
        result = world.swept_grounding(
            start_pose, (nx, ny, self.course), hull)
        self.x, self.y, self.course = (result.safe_x_nm, result.safe_y_nm,
                                       result.safe_course_deg)
        self.last_safe_pose = (self.x, self.y, self.course)
        if not result.contacted:
            if self.grounding_latched and self.astern:
                self.grounding_latched = False
                self.grounding_contact = None
            return None
        if self.grounding_latched:
            self.speed = 0.0
            return None
        self.grounding_latched = True
        self.grounding_contact = result.contact
        self.last_impact_speed_kn = self.speed
        self.speed = 0.0
        return result.contact

    # --- M10: Roll/Pitch aus Seegang + Fahrt (Anzeige) ---

    def _update_roll_pitch(self, dt: float, world, list_deg: float = 0.0) -> None:
        wind_from = float(getattr(world, "wind_from_deg", 0.0)) if world else 0.0
        seed = int(getattr(getattr(world, "ocean", None), "seed", 0)) if world else 0
        start = self._clock
        self._clock += dt
        (self.roll, self.roll_rate, self.pitch,
         self.pitch_rate) = dyn.seakeeping_step(
            dyn.HULL, self.roll, self.roll_rate, self.pitch, self.pitch_rate,
            dt=dt, clock_s=start, seed=seed, sea_state=self.sea_state,
            wave_relative_deg=wind_from - self.course,
            speed_mps=self.speed * KN,
            yaw_rate_rad=math.radians(self.yaw_rate), list_deg=list_deg,
            stabilizers=self.stabilizers_ok)

    # --- Akustik (vereinfacht, Captain's Log §1.1) ---

    def noise_level(self) -> float:
        """Relativer Rauschpegel der Fregatte (0 = leise, 1 = laut), with the
        crew's own noise (``noise_discipline``) on top."""
        return config.clamp(self.machinery_noise_level() + self.crew_noise, 0.0,
                            NOISE_LEVEL_MAX)

    def machinery_noise_level(self) -> float:
        """The frigate's noise without the crew's mishaps and voices."""
        n = max(0.0, (self.speed - 4.0) / (config.SHIP_SPEED_REFERENCE_KN - 4.0))
        if self.cavitating:
            n = max(n, 0.85 + 0.02 * (self.speed - config.CAVITATION_KN))
        if self.quiet_mode:
            n *= 0.65
        if self.plant_mode == "DIESEL":
            n *= PLANT_DIESEL_NOISE
        elif self.plant_mode == "TURBINE":
            n *= PLANT_TURBINE_NOISE
        return config.clamp(n + self.trim_noise, 0.0, NOISE_LEVEL_MAX)

    def passive_sonar_range_nm(self, target_quiet: float = 0.5,
                               sea_state: int = 0) -> float:
        """Passive Detektionsreichweite in NM.

        target_quiet: 0 = sehr lautes Ziel, 1 = sehr leises Ziel.
        M10: Seegrad verringert die Reichweite; bei Kavitation "bricht"
        der passive Sensor (Sensor-Faktor).
        """
        base = config.SONAR_PASSIVE_BASE_NM
        own_penalty = 1.0 - 0.8 * self.noise_level()
        if self.cavitating:
            own_penalty *= config.CAVITATION_PASSIVE_FACTOR
        target_bonus = 1.0 + 0.8 * (1.0 - target_quiet)
        sea = 1.0 - config.SEA_STATE_SONAR_FACTOR * max(0, sea_state - 1)
        return base * own_penalty * target_bonus * sea

    # --- Status ---


    @property
    def course_error_deg(self) -> float:
        return config.angle_diff_deg(self.target_course, self.course)

    @property
    def time_to_course_s(self) -> float:
        return abs(self.course_error_deg) / max(abs(self.yaw_rate), 0.05)

    @property
    def heel_deg(self) -> float:
        return math.degrees(dyn.turn_heel_rad(
            dyn.HULL, self.speed * KN, math.radians(self.yaw_rate)))

    @property
    def turn_radius_nm(self) -> float:
        omega = abs(math.radians(self.yaw_rate))
        if omega < 1e-6 or self.speed < 0.1:
            return float("inf")
        return (self.speed / 3600.0) / omega
