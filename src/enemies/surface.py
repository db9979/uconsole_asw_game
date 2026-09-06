"""Oberflächenschiffe: Zivil (AIS/ESM) + feindliche Kriegsschiffe (KAMPFSCHIFF).

Einheitliche Klasse; feindliche Variante lochert um Ankerpunkt und feuert
ASM-Salven. Akustik und Profil aus dem Kontakt-Katalog (src/data/catalog.py).
"""

import math
import random

from src.core import config
from src.data import catalog
from src.data import fingerprint as fingerprint_mod

CATALOG = catalog.CATALOG


class SurfaceShip:
    """Ziviles Oberflächenschiff oder feindliches Kriegsschiff."""

    _next_id = 5000

    def __init__(self, x_nm: float, y_nm: float, rng: random.Random,
                 hostile: bool = False, profile=None):
        self.id = SurfaceShip._next_id
        SurfaceShip._next_id += 1
        self.rng = rng
        self.hostile = bool(hostile)
        self.profile = (profile if profile is not None
                        else CATALOG.pick_surface(rng, hostile=self.hostile))
        self.signature_key = self.profile.key
        if self.hostile:
            self.name = self.profile.name
            self.callsign = self.profile.name
        else:
            pool = self.profile.callsigns or ("MV UNBEKANNT",)
            self.callsign = rng.choice(pool)
            self.name = self.callsign
        self.sensor_seed = int(rng.randint(0, 2**31 - 1))
        self.fingerprint = fingerprint_mod.roll_from_seed(
            self.sensor_seed, self.profile.acoustic)
        self.x = x_nm
        self.y = y_nm
        self.depth = 5.0
        self.course = rng.uniform(0.0, 360.0)
        self.speed = rng.uniform(*self.profile.speed_kn)
        self.target_course = self.course
        self.target_speed = self.speed
        self.emitter = rng.random() < self.profile.esm_prob
        self.turn_left = rng.uniform(600.0, 1800.0)
        self.turn_delta = 0.0
        self.sunk = False
        self.damage = 0.0
        # Kriegsschiff: Loiter + ASM
        self.anchor = None  # (x, y) – vom Game gesetzt
        self.waypoint = None
        self.orbit_direction = rng.choice((-1, 1))
        self.attack_left = self.profile.asm_cooldown_s
        self.pending_asm: list[tuple[float, float, int]] = []

    # --- Torpedo-Treffer ---

    def hit(self) -> None:
        self.damage = min(100.0, self.damage + 34.0)
        if self.damage >= 100.0:
            self.sunk = True

    # --- Bewegung ---

    def update(self, dt: float, frigate, world) -> None:
        if self.sunk:
            return
        if self.hostile:
            self._update_hostile(dt, frigate, world)
        else:
            self._update_civil(dt, world)

    def _update_civil(self, dt: float, world) -> None:
        self.turn_left -= dt
        if self.turn_left <= 0:
            self.turn_left = self.rng.uniform(600.0, 1800.0)
            self.target_course = (self.course
                                  + self.rng.uniform(-30.0, 30.0)) % 360.0
            self.target_speed = self.rng.uniform(*self.profile.speed_kn)
        self._steer(dt, .5)
        self._move(dt, world)

    def _update_hostile(self, dt: float, frigate, world) -> None:
        dist = self.distance_nm(frigate)
        bearing = math.degrees(math.atan2(
            frigate.x - self.x, -(frigate.y - self.y))) % 360.0
        if dist < 18.0:
            self.target_course = (bearing + 180.0) % 360.0
            self.target_speed = self.profile.speed_kn[1]
        elif dist <= config.WARSHIP_ASM_RANGE_NM:
            self.target_course = (bearing + self.orbit_direction * 90.0) % 360.0
            self.target_speed = min(18.0, self.profile.speed_kn[1])
        elif self.anchor is not None:
            ax, ay = self.anchor
            radius = min(20.0, max(8.0, self.profile.loiter_nm * .75))
            if self.waypoint is None or math.hypot(
                    self.x - self.waypoint[0], self.y - self.waypoint[1]) < 1.0:
                angle = math.atan2(self.y - ay, self.x - ax) \
                    + self.orbit_direction * math.radians(60.0)
                self.waypoint = (ax + radius * math.cos(angle),
                                 ay + radius * math.sin(angle))
            wx, wy = self.waypoint
            self.target_course = math.degrees(
                math.atan2(wx - self.x, -(wy - self.y))) % 360.0
            self.target_speed = min(16.0, self.profile.speed_kn[1])
        self._steer(dt, 1.0)
        self._move(dt, world)
        self._maybe_asm(dt, frigate)

    def _steer(self, dt: float, max_rate: float) -> None:
        diff = config.angle_diff_deg(self.target_course, self.course)
        self.course = (self.course + config.clamp(
            diff, -max_rate * dt, max_rate * dt)) % 360.0
        delta = self.target_speed - self.speed
        self.speed += config.clamp(delta, -.03 * dt, .03 * dt)

    def _move(self, dt: float, world) -> None:
        # Kuestenvorausschau verhindert, dass lange Legs ins Land fuehren.
        on_land = getattr(world, "on_land", lambda x, y: False)
        lookahead = max(1.0, self.speed / 6.0)
        lx = self.x + lookahead * math.sin(math.radians(self.course))
        ly = self.y - lookahead * math.cos(math.radians(self.course))
        if on_land(lx, ly):
            self.target_course = (self.course + self.orbit_direction * 60.0) % 360.0
        v = config.kn_to_nm_per_s(self.speed) * dt
        nx = self.x + v * math.sin(math.radians(self.course))
        ny = self.y - v * math.cos(math.radians(self.course))
        world_size = world.size_nm
        if on_land(nx, ny):
            self.target_course = (self.course + 90.0) % 360.0
            return
        self.x, self.y = nx, ny
        if self.x < 0 or self.x > world_size:
            self.course = (360.0 - self.course) % 360.0
            self.x = config.clamp(self.x, 0.0, world_size)
        if self.y < 0 or self.y > world_size:
            self.course = (180.0 - self.course) % 360.0
            self.y = config.clamp(self.y, 0.0, world_size)

    def _maybe_asm(self, dt: float, frigate) -> None:
        if self.profile.asm_salvo[0] <= 0:
            return
        self.attack_left -= dt
        if self.attack_left > 0.0:
            return
        dist = self.distance_nm(frigate)
        if dist <= config.WARSHIP_ASM_RANGE_NM:
            n = self.rng.randint(self.profile.asm_salvo[0],
                                 self.profile.asm_salvo[1])
            self.pending_asm.append((self.x, self.y, n))
            self.attack_left = self.profile.asm_cooldown_s

    # --- Akustik ---

    def quiet_factor(self) -> float:
        if self.sunk:
            return 0.0
        return max(0.05, 0.45 - self.speed / 60.0)

    def acoustic_signature(self) -> str:
        if self.sunk:
            return ""
        sig = self.profile.acoustic
        base = sig.signature_text or "unbekannter Antrieb"
        if self.speed >= 18.0:
            freq = "Frequenz hoch (volle Fahrt)"
        elif self.speed >= 10.0:
            freq = "Frequenz mittel"
        else:
            freq = "Frequenz niedrig (Langfahrt)"
        detail = (f" · DEMON {sig.tonal_band_hz[0]:.0f}-"
                  f"{sig.tonal_band_hz[1]:.0f} Hz")
        return f"mechanisch · {base} · {freq}{detail}"

    def lofar_lines(self, t_sim: float = 0.0) -> list:
        if self.sunk:
            return []
        lines = []
        v = max(0.0, self.speed)
        sig = self.profile.acoustic
        fp = self.fingerprint
        vmax = max(1.0, self.profile.speed_kn[1])
        if v > 0.3:
            f = (fp.rate_scale
                 * (sig.tonal_band_hz[0]
                    + (sig.tonal_band_hz[1] - sig.tonal_band_hz[0])
                    * min(1.0, v / vmax))
                 + fp.offsets[0])
            f = max(2.0, f)
            amp = 0.20 + 0.60 * min(1.0, v / 24.0)
            lines.append((f, amp, 1.5))
            if v > 8.0:
                lines.append((f * 2.0 + fp.offsets[1], amp * 0.45, 1.2))
                lines.append((f * 3.0 + fp.offsets[2], amp * 0.25, 1.0))
            for hz, a, width in sig.secondary_tonals:
                lines.append((hz, a * min(1.0, v / 6.0), width))
        if self.damage > 30.0:
            lines.append((55.0, 0.25 + 0.45 * self.damage / 100.0, 4.0))
        return lines

    def broadband(self) -> dict:
        sig = self.profile.acoustic
        if self.sunk or sig.broadband is None:
            return {}
        v = max(0.0, self.speed)
        vmax = max(1.0, self.profile.speed_kn[1])
        level = self.fingerprint.bb_level * (0.2 + 0.8 * min(1.0, v / vmax))
        level = min(1.0, level + 0.10 * (self.damage / 100.0))
        return {"level": min(1.0, level),
                "low_hz": sig.broadband[1],
                "high_hz": sig.broadband[2]}

    # --- Geometrie ---

    def distance_nm(self, frigate) -> float:
        return math.hypot(self.x - frigate.x, self.y - frigate.y)

    def bearing_from_frigate(self, frigate) -> float:
        dx = self.x - frigate.x
        dy = self.y - frigate.y
        return math.degrees(math.atan2(dx, -dy)) % 360.0
