"""Fregatte-Modell: Position, Kurs, Geschwindigkeit, Lärmpegel."""

import math

from src.core import config


class Ship:
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
        self.speed_cap = config.SHIP_SPEED_MAX_KN
        self.quiet_mode = False
        self.grounded = False
        self.roll = 0.0
        self.pitch = 0.0
        self._clock = 0.0

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
        return config.TELEGRAPH_ORDERS[self.order_idx][0]

    def cycle_telegraph(self, delta: int) -> None:
        """Motorenbefehl umschalten, ohne von STOP auf FLANK zu springen."""
        self.order_idx = config.clamp(self.order_idx + delta, 0,
                                      len(config.TELEGRAPH_ORDERS) - 1)
        self.target_speed = config.TELEGRAPH_ORDERS[self.order_idx][1]

    @property
    def cavitating(self) -> bool:
        """M10: Schraubenkavitation (ab CAVITATION_KN deutlich lauter)."""
        return self.speed >= config.CAVITATION_KN

    def rpm(self) -> float:
        """M10: Wellendrehzahl für die Maschinenraum-Anzeige."""
        return config.SHIP_RPM_MIN + self.speed * config.SHIP_RPM_PER_KN

    # --- Physik ---

    def update(self, dt: float, world=None) -> None:
        """dt in Simulationssekunden; bei 1x identisch zu Echtzeit."""

        # Kurs: Ruder, Giergeschwindigkeit und Kurs bauen sich nacheinander auf.
        diff = config.angle_diff_deg(self.target_course, self.course)
        desired_rudder = config.clamp(
            diff * 0.75 - self.yaw_rate * config.SHIP_YAW_DAMPING,
            -config.SHIP_MAX_RUDDER_DEG, config.SHIP_MAX_RUDDER_DEG)
        rudder_step = config.SHIP_RUDDER_RATE_DEG_PER_S * self.turn_rate_scale * dt
        self.rudder_angle += config.clamp(
            desired_rudder - self.rudder_angle, -rudder_step, rudder_step)
        speed_factor = config.clamp(self.speed / 10.0, 0.0, 1.5)
        max_yaw = config.SHIP_MAX_YAW_RATE_DEG_PER_S * speed_factor \
            * self.turn_rate_scale
        desired_yaw = (self.rudder_angle / config.SHIP_MAX_RUDDER_DEG) * max_yaw
        yaw_step = max_yaw * dt / config.SHIP_YAW_RESPONSE_S if max_yaw else dt
        self.yaw_rate += config.clamp(desired_yaw - self.yaw_rate,
                                      -yaw_step, yaw_step)
        self.course = (self.course + self.yaw_rate * dt) % 360.0

        # Geschwindigkeit: Trägheit
        effective_target = min(self.target_speed, self.speed_cap,
                               12.0 if self.quiet_mode else self.speed_cap)
        target_delta = effective_target - self.speed
        if abs(target_delta) <= 0.2:
            self.speed = effective_target
        else:
            step = config.clamp(target_delta,
                                -config.SHIP_SPEED_RESP_KN_PER_S * dt,
                                config.SHIP_SPEED_RESP_KN_PER_S * dt)
            self.speed += step

        # Physikalische Bewegung (W3: Land-Rueckstoss)
        # Nautisch: 0° = Nord/-y, 90° = Ost/+x (konsistent zu Peilungen)
        step = config.kn_to_nm_per_s(self.speed) * dt
        nx = self.x + step * math.sin(math.radians(self.course))
        ny = self.y - step * math.cos(math.radians(self.course))
        self._advance(nx, ny, world)
        self._update_roll_pitch(dt, world)

    def _advance(self, nx: float, ny: float, world) -> None:
        """Position aktualisieren; bei Welt-Rand/Land Kurs spiegeln."""
        if world is None:
            self.x, self.y = nx, ny
            return
        s = world.size_nm
        blocked = (nx < 0.0 or ny < 0.0 or nx > s or ny > s) \
            or world.on_land(nx, ny)
        if not blocked:
            self.grounded = False
            self.x, self.y = nx, ny
            return
        if abs(nx - self.x) >= abs(ny - self.y):
            self.course = (360.0 - self.course) % 360.0
        else:
            self.course = (180.0 - self.course) % 360.0
        self.target_course = self.course
        self.speed *= 0.4
        self.target_speed = min(self.target_speed, 6.0)
        self.grounded = True

    # --- M10: Roll/Pitch aus Seegang + Fahrt (Anzeige) ---

    def _update_roll_pitch(self, dt: float, world) -> None:
        sea = world.sea_state if world is not None else 0
        amp = 0.4 + 0.30 * sea + 0.02 * self.speed
        self._clock += dt
        self.roll = amp * math.sin(self._clock * 0.23)
        self.pitch = amp * 0.7 * math.sin(self._clock * 0.31 + 1.3)

    # --- Akustik (vereinfacht, Captain's Log §1.1) ---

    def noise_level(self) -> float:
        """Relativer Rauschpegel der Fregatte (0 = leise, 1 = laut)."""
        n = config.clamp((self.speed - 4.0) / (config.SHIP_SPEED_MAX_KN - 4.0), 0.0, 1.0)
        if self.cavitating:
            n = max(n, 0.85 + 0.02 * (self.speed - config.CAVITATION_KN))
        if self.quiet_mode:
            n *= 0.65
        return n

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

    def pos_nm(self) -> tuple:
        return self.x, self.y

    @property
    def course_error_deg(self) -> float:
        return config.angle_diff_deg(self.target_course, self.course)

    @property
    def time_to_course_s(self) -> float:
        return abs(self.course_error_deg) / max(abs(self.yaw_rate), 0.05)

    @property
    def turn_radius_nm(self) -> float:
        omega = abs(math.radians(self.yaw_rate))
        if omega < 1e-6 or self.speed < 0.1:
            return float("inf")
        return (self.speed / 3600.0) / omega
