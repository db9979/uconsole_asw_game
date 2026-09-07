"""M16: Fliegerabwehr – See-Skimming-ASMs (feindlich) + ESSM (eigene).

Zeitbasis: Simulationssekunden; bei 1x identisch zu Echtzeit.
"""

import math

from src.core import config
from src.weapons.torpedo import Torpedo


class ASM:
    """Feindliche Schiffs-Rakete: skimmt auf ~20 m, optionaler ESM-Jammer.

    Zustand: LAUF | CHAFF | ABGEFANGEN | TREFFER | VERLOREN
    """

    # Bounded gameplay endurance, not a real missile specification.
    RANGE_NM = 2.0 * max(config.ASM_SPAWN_DIST_NM)
    LIFE_S = RANGE_NM / config.kn_to_nm_per_s(config.ASM_SPEED_KN)

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
        self.travel = 0.0
        self.age_s = 0.0

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

    def update(self, dt: float, frigate, world=None) -> None:
        if self.state in ("ABGEFANGEN", "TREFFER", "VERLOREN"):
            return
        run_dt = min(dt, max(0.0, self.LIFE_S - self.age_s))
        if self.state == "CHAFF":
            # Störblindheit: gerader Kurs weiter, ohne Korrekturen
            if self.broken:
                run_dt = min(run_dt, max(0.0, self.chaff_left))
            self.chaff_left -= dt
        elif not self.jamming(frigate):
            # homt auf die Fregatte
            desired = math.degrees(math.atan2(frigate.x - self.x,
                                              -(frigate.y - self.y))) % 360.0
            diff = config.angle_diff_deg(desired, self.course)
            self.course = (self.course + config.clamp(
                diff, -8.0 * dt, 8.0 * dt)) % 360.0
        ox, oy = self.x, self.y
        self.age_s = min(self.LIFE_S, self.age_s + dt)
        step = min(config.kn_to_nm_per_s(config.ASM_SPEED_KN) * run_dt,
                   max(0.0, self.RANGE_NM - self.travel))
        self.x += step * math.sin(math.radians(self.course))
        self.y -= step * math.cos(math.radians(self.course))
        self.travel += step
        if Torpedo._swept_dist(self, frigate, ox, oy) <= 0.15:
            self.state = "TREFFER"
        elif (self.travel >= self.RANGE_NM or self.age_s >= self.LIFE_S
              or (world is not None and not (0 <= self.x <= world.size_nm
                                              and 0 <= self.y <= world.size_nm))):
            self.state = "VERLOREN"
        elif self.state == "CHAFF" and self.chaff_left <= 0.0:
            self.state = "VERLOREN" if self.broken else "LAUF"


class ESSM:
    """Eigene Abfangrakete (VLS): homing auf ASM-Track (auch HOJ-Track)."""

    TURN_DEG_PER_S = 30.0
    SEEKER_RANGE_NM = 3.0  # Gameplay acquisition envelope, not platform data.

    def __init__(self, x_nm: float, y_nm: float, course_deg: float,
                 target_asm, seq: int, guidance_x=None, guidance_y=None,
                 target_id=None):
        self.x = x_nm
        self.y = y_nm
        self.course = course_deg % 360.0
        self.target = target_asm
        self.target_id = getattr(target_asm, "seq", None) if target_id is None else target_id
        self.seq = seq
        self.state = "LAUF"
        self.travel = 0.0
        # Legacy direct callers supply a launch snapshot. Game supplies a track.
        self.guidance_x = (getattr(target_asm, "x", x_nm + config.ESSM_RANGE_NM
                                  * math.sin(math.radians(self.course)))
                           if guidance_x is None else guidance_x)
        self.guidance_y = (getattr(target_asm, "y", y_nm - config.ESSM_RANGE_NM
                                  * math.cos(math.radians(self.course)))
                           if guidance_y is None else guidance_y)
        self.seeker_acquired = False

    def update(self, dt: float, candidates=None, world=None) -> None:
        if self.state != "LAUF":
            return
        tgt = self.target
        def viable(item):
            return (item is not None and item.state in ("LAUF", "CHAFF")
                    and math.hypot(item.x - self.x, item.y - self.y) <= self.SEEKER_RANGE_NM
                    and not (world is not None and getattr(
                        world, "land_blocks_line", lambda *args: False)(
                            self.x, self.y, item.x, item.y)))

        if self.seeker_acquired and not viable(tgt):
            self.seeker_acquired = False
        if (not self.seeker_acquired and math.hypot(
                self.guidance_x - self.x, self.guidance_y - self.y) <= self.SEEKER_RANGE_NM):
            viable_targets = [item for item in ([tgt] if candidates is None else candidates)
                              if viable(item)]
            if viable_targets:
                tgt = self.target = min(viable_targets, key=lambda item:
                                       math.hypot(item.x - self.x, item.y - self.y))
                self.seeker_acquired = True
        aim_x, aim_y = ((tgt.x, tgt.y) if self.seeker_acquired
                        else (self.guidance_x, self.guidance_y))
        desired = math.degrees(math.atan2(aim_x - self.x,
                                          -(aim_y - self.y))) % 360.0
        diff = config.angle_diff_deg(desired, self.course)
        self.course = (self.course + config.clamp(
            diff, -self.TURN_DEG_PER_S * dt, self.TURN_DEG_PER_S * dt)) % 360.0
        ox, oy = self.x, self.y
        step = min(config.kn_to_nm_per_s(config.ESSM_SPEED_KN) * dt,
                   max(0.0, config.ESSM_RANGE_NM - self.travel))
        self.x += step * math.sin(math.radians(self.course))
        self.y -= step * math.cos(math.radians(self.course))
        self.travel += step
        if (self.seeker_acquired
                and Torpedo._swept_dist(self, tgt, ox, oy) <= config.ESSM_KILL_DIST_NM):
            tgt.state = "ABGEFANGEN"
            self.state = "HIT"
        elif self.travel >= config.ESSM_RANGE_NM:
            self.state = "SASE"
