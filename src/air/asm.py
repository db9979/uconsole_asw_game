"""M16: Fliegerabwehr – See-Skimming-ASMs (feindlich) + ESSM (eigene).

Zeitbasis: Simulationssekunden; bei 1x identisch zu Echtzeit.
"""

import math

from src.core import config
from src.weapons.air_defense import air_defense_loadout
from src.weapons.torpedo import Torpedo


class ASM:
    """Feindliche Schiffs-Rakete: skimmt auf ~20 m, optionaler ESM-Jammer.

    Zustand: LAUF | CHAFF | ABGEFANGEN | TREFFER | VERLOREN
    """

    # Bounded gameplay endurance, not a real missile specification.
    _DEFAULT_PROFILE = air_defense_loadout()["asm"]
    RANGE_NM = _DEFAULT_PROFILE["range_nm"]
    LIFE_S = RANGE_NM / config.kn_to_nm_per_s(_DEFAULT_PROFILE["speed_kn"])
    side = "hostile"
    sensor_domain = "air"

    def __init__(self, x_nm: float, y_nm: float, course_deg: float, seq: int,
                 rng, profile=None):
        self.profile = profile or self._DEFAULT_PROFILE
        self.profile_key = self.profile["key"]
        self.speed_kn = self.profile["speed_kn"]
        self.range_nm = self.profile["range_nm"]
        self.life_s = self.range_nm / config.kn_to_nm_per_s(self.speed_kn)
        self.x = x_nm
        self.y = y_nm
        self.course = course_deg % 360.0
        self.seq = seq
        self.rng = rng
        self.state = "LAUF"
        self.jammer = rng.random() < self.profile["jam_probability"]
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
        """Outside the profiled burn-through range, expose bearing-only HOJ."""
        return bool(self.jammer
                    and self.distance_nm(frigate) > self.profile["jam_break_nm"])

    # --- Wirkung ---

    def launch_chaff(self, rng, softkill_profile=None) -> bool:
        """Apply the profiled softkill result and temporary seeker blindness."""
        if self.state != "LAUF":
            return False
        softkill_profile = softkill_profile or air_defense_loadout()["softkill"]
        self.state = "CHAFF"
        self.chaff_left = rng.uniform(*softkill_profile["effect_duration_s"])
        self.broken = rng.random() < softkill_profile["defeat_probability"]
        return self.broken

    # --- Physik ---

    def update(self, dt: float, frigate, world=None) -> None:
        if self.state in ("ABGEFANGEN", "TREFFER", "VERLOREN"):
            return
        run_dt = min(dt, max(0.0, self.life_s - self.age_s))
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
                diff, -self.profile["turn_rate_deg_s"] * dt,
                self.profile["turn_rate_deg_s"] * dt)) % 360.0
        ox, oy = self.x, self.y
        self.age_s = min(self.life_s, self.age_s + dt)
        step = min(config.kn_to_nm_per_s(self.speed_kn) * run_dt,
                   max(0.0, self.range_nm - self.travel))
        self.x += step * math.sin(math.radians(self.course))
        self.y -= step * math.cos(math.radians(self.course))
        self.travel += step
        if Torpedo._swept_dist(self, frigate, ox, oy) <= self.profile["hit_distance_nm"]:
            self.state = "TREFFER"
        elif (self.travel >= self.range_nm or self.age_s >= self.life_s
              or (world is not None and not (0 <= self.x <= world.size_nm
                                              and 0 <= self.y <= world.size_nm))):
            self.state = "VERLOREN"
        elif self.state == "CHAFF" and self.chaff_left <= 0.0:
            self.state = "VERLOREN" if self.broken else "LAUF"


class ESSM:
    """Eigene Abfangrakete (VLS): homing auf ASM-Track (auch HOJ-Track)."""

    _DEFAULT_PROFILE = air_defense_loadout()["sam"]
    TURN_DEG_PER_S = _DEFAULT_PROFILE["turn_rate_deg_s"]
    SEEKER_RANGE_NM = _DEFAULT_PROFILE["seeker_range_nm"]

    def __init__(self, x_nm: float, y_nm: float, course_deg: float,
                 target_asm, seq: int, guidance_x=None, guidance_y=None,
                 target_id=None, profile=None):
        self.profile = profile or self._DEFAULT_PROFILE
        self.profile_key = self.profile["key"]
        self.x = x_nm
        self.y = y_nm
        self.course = course_deg % 360.0
        self.target = target_asm
        self.target_id = getattr(target_asm, "seq", None) if target_id is None else target_id
        self.seq = seq
        self.state = "LAUF"
        self.travel = 0.0
        # Legacy direct callers supply a launch snapshot. Game supplies a track.
        self.guidance_x = (getattr(target_asm, "x", x_nm + self.profile["range_nm"]
                                  * math.sin(math.radians(self.course)))
                           if guidance_x is None else guidance_x)
        self.guidance_y = (getattr(target_asm, "y", y_nm - self.profile["range_nm"]
                                  * math.cos(math.radians(self.course)))
                           if guidance_y is None else guidance_y)
        self.seeker_acquired = False

    def update(self, dt: float, candidates=None, world=None) -> None:
        if self.state != "LAUF":
            return
        tgt = self.target
        def viable(item):
            return (item is not None and item.state in ("LAUF", "CHAFF")
                    and not (item.state == "CHAFF" and item.broken)
                    and math.hypot(item.x - self.x, item.y - self.y)
                    <= self.profile["seeker_range_nm"]
                    and not (world is not None and getattr(
                        world, "land_blocks_line", lambda *args: False)(
                            self.x, self.y, item.x, item.y)))

        if self.seeker_acquired and not viable(tgt):
            self.seeker_acquired = False
        if (not self.seeker_acquired and math.hypot(
                self.guidance_x - self.x, self.guidance_y - self.y)
                <= self.profile["seeker_range_nm"]):
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
            diff, -self.profile["turn_rate_deg_s"] * dt,
            self.profile["turn_rate_deg_s"] * dt)) % 360.0
        ox, oy = self.x, self.y
        step = min(config.kn_to_nm_per_s(self.profile["speed_kn"]) * dt,
                   max(0.0, self.profile["range_nm"] - self.travel))
        self.x += step * math.sin(math.radians(self.course))
        self.y -= step * math.cos(math.radians(self.course))
        self.travel += step
        if (self.seeker_acquired
                and Torpedo._swept_dist(self, tgt, ox, oy)
                <= self.profile["kill_distance_nm"]):
            tgt.state = "ABGEFANGEN"
            self.state = "HIT"
        elif self.travel >= self.profile["range_nm"]:
            self.state = "SASE"
