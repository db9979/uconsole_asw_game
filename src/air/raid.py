"""R20: Luftangriff – feindliche Angriffsflugzeuge gegen die Fregatte.

Raider sind Simulationsentitaeten (KI/Physik duerfen die Wahrwerte nutzen).
Beobachtung laeuft ausschliesslich ueber das Air Picture als anonymer
FLG-Track; die Flak feuert nur gegen frische Radar-Beobachtungen.

Phasenmaschine:
    APPROACH -> (Waffenbereich) -> ATTACK -> (Fenster abgelaufen /
    Bereich verlassen) -> RETREAT -> (Rausradius / Weltende) -> Despawn

Flight physics: coordinated turns (rate = g tan(bank) / v at the bank
limit) and, for every salvo, a pop-up: the raider climbs from its
sea-skimming approach height to acquire the ship with its fire-control
radar (an ESM-visible emission and a radar-horizon spike), releases after
the lock time and descends again.
"""

import math
import random
from enum import Enum

from src.core import config
from src.physics.geo import FrigateRelativeMixin


class RaidPhase(str, Enum):
    APPROACH = "APPROACH"
    ATTACK = "ATTACK"
    RETREAT = "RETREAT"

    @classmethod
    def parse(cls, value: str) -> "RaidPhase":
        for phase in cls:
            if phase.value == value:
                return phase
        raise ValueError(f"unknown raid phase: {value!r}")


G = 9.80665
MAX_BANK_DEG = 56.0
POPUP_ALTITUDE_M = 300.0
CLIMB_RATE_MPS = 40.0
FC_LOCK_S = 4.0


def coordinated_turn_rate_deg_s(speed_kn: float, bank_deg: float = MAX_BANK_DEG) -> float:
    speed = max(speed_kn * 1852.0 / 3600.0, 1.0)
    return math.degrees(G * math.tan(math.radians(bank_deg)) / speed)


class Raider(FrigateRelativeMixin):
    """Feindliches Angriffsflugzeug mit ASM-Salvenlast."""

    # Attacke: tangentialer Stand-off-Flug am Waffenbereich entlang.
    STANDOFF_FRAC = 0.9

    def __init__(self, x_nm: float, y_nm: float, course_deg: float, seq: int,
                 rng: random.Random, profile: dict):
        self.profile = profile
        self.seq = seq
        self.sensor_seed = int(seq)
        self.rng = rng
        self.x = float(x_nm)
        self.y = float(y_nm)
        self.course = float(course_deg) % 360.0
        self.speed_kn = self.profile["speed_kn"]
        self.altitude_m = self.profile["altitude_m"]
        self.hp = self.profile["hp"]
        self.max_hp = self.profile["hp"]
        self.evasion = self.profile["evasion"]
        self.turn_deg_s = coordinated_turn_rate_deg_s(self.speed_kn)
        self.phase = RaidPhase.APPROACH
        # Seconds at pop-up height with the fire-control radar on (-1 = low).
        self.popup_t = -1.0
        self.attack_t = 0.0
        self.salto_cd = 0.0
        self.pending_asm = 0
        self.despawned = False

    # --- Simulation-interne Geometrie ---

    def course_to_frigate(self, frigate) -> float:
        """Steuerkurs vom Raider zur Fregatte (Umkehr der Peilung)."""
        return (self.bearing_from_frigate(frigate) + 180.0) % 360.0

    @property
    def fc_radar_on(self) -> bool:
        return self.popup_t >= 0.0 and self.altitude_m >= 0.9 * POPUP_ALTITUDE_M

    def _climb(self, target_m: float, dt: float) -> None:
        step = CLIMB_RATE_MPS * dt
        self.altitude_m += config.clamp(target_m - self.altitude_m, -step, step)

    # --- Phasenmaschine ---

    def update(self, dt: float, frigate, world=None) -> None:
        """Ein Schritt voranbringen; `pending_asm` laedt das Spiel als
        ASM-Objekte ab. Setzt `despawned`, wenn der Raider weg ist."""
        if self.despawned or self.hp <= 0:
            return
        profile = self.profile
        dist = math.hypot(self.x - frigate.x, self.y - frigate.y)
        to_frigate = self.course_to_frigate(frigate)

        if self.phase is RaidPhase.APPROACH:
            if dist <= profile["weapon_range_nm"]:
                self.phase = RaidPhase.ATTACK
                self.attack_t = 0.0
                self.salto_cd = 0.0
        if self.phase is RaidPhase.ATTACK:
            self.attack_t += dt
            self.salto_cd -= dt
            if self.salto_cd <= 0.0 and self.popup_t < 0.0:
                self.popup_t = 0.0
            if self.popup_t >= 0.0:
                self._climb(POPUP_ALTITUDE_M, dt)
                if self.fc_radar_on:
                    self.popup_t += dt
                if self.popup_t >= FC_LOCK_S:
                    self.salto_cd = profile["weapon_cooldown_s"]
                    lo, hi = profile["salvo"]
                    self.pending_asm += lo + self.rng.randint(0, hi - lo)
                    self.popup_t = -1.0
            if (self.attack_t >= config.RAIDER_ATTACK_WINDOW_S
                    or dist > profile["weapon_range_nm"] * 1.25):
                self.phase = RaidPhase.RETREAT
                self.popup_t = -1.0
        if self.popup_t < 0.0:
            self._climb(profile["altitude_m"], dt)
        if self.phase is RaidPhase.APPROACH:
            target = to_frigate
        elif self.phase is RaidPhase.ATTACK:
            side = 90.0 if self.seq % 2 else 270.0
            target = (to_frigate + side) % 360.0
        else:
            target = self.bearing_from_frigate(frigate)
            if dist >= profile["retreat_radius_nm"]:
                self.despawned = True

        diff = config.angle_diff_deg(target, self.course)
        self.course = (self.course + config.clamp(
            diff, -self.turn_deg_s * dt, self.turn_deg_s * dt)) % 360.0
        step = config.kn_to_nm_per_s(self.speed_kn) * dt
        self.x += step * math.sin(math.radians(self.course))
        self.y -= step * math.cos(math.radians(self.course))
        if world is not None and not (0 <= self.x <= world.size_nm
                                      and 0 <= self.y <= world.size_nm):
            self.despawned = True
