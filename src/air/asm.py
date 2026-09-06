"""M16: Fliegerabwehr – See-Skimming-ASMs (feindlich) + ESSM (eigene).

Zeitbasis: Simulationssekunden; bei 1x identisch zu Echtzeit.
"""

import math

from src.core import config


class ASM:
    """Feindliche Schiffs-Rakete: skimmt auf ~20 m, optionaler ESM-Jammer.

    Zustand: LAUF | CHAFF | ABGEFANGEN | TREFFER | VERLOREN
    """

    def __init__(self, x_nm: float, y_nm: float, course_deg: float, seq: int,
                 rng):
        self.x = x_nm
        self.y = y_nm
        self.course = course_deg % 360.0
        self.seq = seq
        self.rng = rng
        self.state = "LAUF"
        self.jammer = rng.random() < config.ASM_JAM_PROB
        self.chaff_left = 0.0
        self.broken = False

    # --- Abfragen ---

    def distance_nm(self, frigate) -> float:
        return math.hypot(self.x - frigate.x, self.y - frigate.y)

    def bearing_to_frigate(self, frigate) -> float:
        """Nautische Peilung der Rakete (0° = Nord)."""
        dx = self.x - frigate.x
        dy = self.y - frigate.y
        return math.degrees(math.atan2(dx, -dy)) % 360.0

    def jamming(self, frigate) -> bool:
        """Jenseits ASM_JAM_BREAK_NM: nur HOJ-Peilung (Bearing-Only)."""
        return bool(self.jammer
                    and self.distance_nm(frigate) > config.ASM_JAM_BREAK_NM)

    # --- Wirkung ---

    def launch_chaff(self, rng) -> bool:
        """Chaff-Wolke: mit CHAFF_BREAK_P bricht die Rakete ab, sonst
        kurz Störblindheit und dann weiterfliegen."""
        if self.state != "LAUF":
            return False
        self.state = "CHAFF"
        self.chaff_left = rng.uniform(2.0, 4.0)
        self.broken = rng.random() < config.CHAFF_BREAK_P
        return self.broken

    # --- Physik ---

    def update(self, dt: float, frigate) -> None:
        if self.state in ("ABGEFANGEN", "TREFFER", "VERLOREN"):
            return
        if self.state == "CHAFF":
            # Störblindheit: gerader Kurs weiter, ohne Korrekturen
            self.chaff_left -= dt
            step = config.kn_to_nm_per_s(config.ASM_SPEED_KN) * dt
            self.x += step * math.sin(math.radians(self.course))
            self.y -= step * math.cos(math.radians(self.course))
            if self.chaff_left <= 0.0:
                self.state = "VERLOREN" if self.broken else "LAUF"
            return

        dist = self.distance_nm(frigate)
        if not self.jamming(frigate):
            # homt auf die Fregatte
            desired = math.degrees(math.atan2(frigate.x - self.x,
                                              -(frigate.y - self.y))) % 360.0
            diff = config.angle_diff_deg(desired, self.course)
            self.course = (self.course + config.clamp(
                diff, -8.0 * dt, 8.0 * dt)) % 360.0
        step = config.kn_to_nm_per_s(config.ASM_SPEED_KN) * dt
        self.x += step * math.sin(math.radians(self.course))
        self.y -= step * math.cos(math.radians(self.course))
        if dist <= 0.15:
            self.state = "TREFFER"


class ESSM:
    """Eigene Abfangrakete (VLS): homing auf ASM-Track (auch HOJ-Track)."""

    TURN_DEG_PER_S = 30.0

    def __init__(self, x_nm: float, y_nm: float, course_deg: float,
                 target_asm, seq: int):
        self.x = x_nm
        self.y = y_nm
        self.course = course_deg % 360.0
        self.target = target_asm
        self.seq = seq
        self.state = "LAUF"
        self.travel = 0.0

    def update(self, dt: float) -> None:
        if self.state != "LAUF":
            return
        tgt = self.target
        if tgt.state in ("ABGEFANGEN", "VERLOREN", "TREFFER"):
            self.state = "SASE"
            return
        dist = math.hypot(tgt.x - self.x, tgt.y - self.y)
        desired = math.degrees(math.atan2(tgt.x - self.x,
                                          -(tgt.y - self.y))) % 360.0
        diff = config.angle_diff_deg(desired, self.course)
        self.course = (self.course + config.clamp(
            diff, -self.TURN_DEG_PER_S * dt, self.TURN_DEG_PER_S * dt)) % 360.0
        step = config.kn_to_nm_per_s(config.ESSM_SPEED_KN) * dt
        self.x += step * math.sin(math.radians(self.course))
        self.y -= step * math.cos(math.radians(self.course))
        self.travel += step
        if dist <= config.ESSM_KILL_DIST_NM:
            tgt.state = "ABGEFANGEN"
            self.state = "HIT"
        elif self.travel >= config.ESSM_RANGE_NM:
            self.state = "SASE"
