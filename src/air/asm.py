"""M16: Fliegerabwehr – See-Skimming-ASMs (feindlich) + ESSM (eigene).

Zeitbasis: Simulationssekunden; bei 1x identisch zu Echtzeit.
"""

import math

from src.core import config
from src.air import chaff
from src.physics import missile
from src.weapons.air_defense import air_defense_loadout
from src.weapons.torpedo import Torpedo
from src.physics.geo import bearing_deg


class ASM:
    """Feindliche Schiffs-Rakete: 3-DOF-Punktmasse (Boost, Seeziel-Flughoehe,
    INS-Mittelkurs zum Startdatum, aktiver Suchkopf mit Sichtfeld und
    Aufschaltzeit, Proportionalnavigation mit g-Limit), optionaler ESM-Jammer.

    Zustand: LAUF | CHAFF | ABGEFANGEN | TREFFER | VERLOREN
    """

    # Bounded gameplay endurance, not a real missile specification.
    _DEFAULT_PROFILE = air_defense_loadout()["asm"]
    RANGE_NM = _DEFAULT_PROFILE["range_nm"]
    LIFE_S = missile.flight_time_bound_s(RANGE_NM, _DEFAULT_PROFILE["speed_kn"])
    side = "hostile"
    sensor_domain = "air"

    def __init__(self, x_nm: float, y_nm: float, course_deg: float, seq: int,
                 rng, profile=None, *, launch_speed_kn: float | None = None,
                 altitude_m: float | None = None, datum=None):
        self.profile = profile or self._DEFAULT_PROFILE
        self.profile_key = self.profile["key"]
        self.cruise_kn = self.profile["speed_kn"]
        # A round created in flight (legacy callers, tests) is already at
        # cruise; a launched round boosts from its launcher's speed.
        self.speed_kn = (self.cruise_kn if launch_speed_kn is None
                         else max(0.0, float(launch_speed_kn)))
        self.boosting = self.speed_kn < self.cruise_kn
        self.range_nm = self.profile["range_nm"]
        self.life_s = missile.flight_time_bound_s(self.range_nm, self.cruise_kn)
        self.x = x_nm
        self.y = y_nm
        self.course = course_deg % 360.0
        self.altitude_m = (missile.CRUISE_ALTITUDE_M if altitude_m is None
                           else max(0.0, float(altitude_m)))
        if datum is None:
            datum = (x_nm + self.range_nm * math.sin(math.radians(self.course)),
                     y_nm - self.range_nm * math.cos(math.radians(self.course)))
        self.datum_x, self.datum_y = float(datum[0]), float(datum[1])
        self.seq = seq
        self.sensor_seed = int(seq)
        self.rng = rng
        self.state = "LAUF"
        self.jammer = rng.random() < self.profile["jam_probability"]
        self.chaff_left = 0.0
        self.broken = False
        self.chaff_cloud = None       # seq of the cloud that seduced the seeker
        self.travel = 0.0
        self.age_s = 0.0
        self.lock_s = 0.0
        self.locked = False
        self.los_prev = None

    # --- Abfragen ---

    def distance_nm(self, frigate) -> float:
        return math.hypot(self.x - frigate.x, self.y - frigate.y)

    def bearing_to_frigate(self, frigate) -> float:
        """Nautische Peilung der Rakete (0° = Nord)."""
        return bearing_deg(frigate.x, frigate.y, self.x, self.y)

    def jamming(self, frigate) -> bool:
        """Outside the profiled burn-through range, expose bearing-only HOJ."""
        return bool(self.jammer
                    and self.distance_nm(frigate) > self.profile["jam_break_nm"])

    def seeker_active(self, frigate) -> bool:
        """Terminal active-radar seeker: silent mid-course, radiates close in."""
        return (self.state in ("LAUF", "CHAFF")
                and self.distance_nm(frigate) <= self.profile["seeker_active_range_nm"])

    # --- Wirkung ---

    def launch_chaff(self, rng, softkill_profile=None, cloud_seq=None,
                     arrival_s=None) -> bool:
        """A chaff cloud blooms in the seeker's resolution cell.  The seeker
        transfers to it when its echo exceeds the fluctuating (Swerling-1)
        ship echo: P = 1 - exp(-sigma_chaff / sigma_ship), which the profiled
        defeat probability expresses.  Otherwise the cloud only confuses the
        range gate for the effect duration."""
        if self.state != "LAUF":
            return False
        softkill_profile = softkill_profile or air_defense_loadout()["softkill"]
        self.state = "CHAFF"
        self.chaff_left = rng.uniform(*softkill_profile["effect_duration_s"])
        probability = softkill_profile["defeat_probability"]
        if arrival_s is not None:
            probability = chaff.seduction_probability(probability, arrival_s)
        self.broken = rng.random() < probability
        self.chaff_cloud = cloud_seq if self.broken else None
        return self.broken

    # --- Physik ---

    def _ecm_decision(self, ecm_effect):
        effectiveness = (max(0.0, min(.7, float(ecm_effect)))
                         if isinstance(ecm_effect, (int, float))
                         else max(0.0, min(.7, float(getattr(
                             ecm_effect, "effectiveness", 0.0)))))
        technique = getattr(ecm_effect, "technique", None)
        home_on_jam = bool(getattr(ecm_effect, "hoj_exposure", False))
        deceived = (effectiveness > 0.0 and not home_on_jam
                    and self.rng.random() < effectiveness)
        return deceived, technique

    def _turn_towards(self, bearing: float, rate_deg_s: float, dt: float) -> None:
        diff = config.angle_diff_deg(bearing, self.course)
        self.course = (self.course + config.clamp(
            diff, -rate_deg_s * dt, rate_deg_s * dt)) % 360.0

    def _guide(self, h: float, frigate, world, deceived: bool, technique) -> None:
        distance = self.distance_nm(frigate)
        bearing = math.degrees(math.atan2(frigate.x - self.x,
                                          -(frigate.y - self.y))) % 360.0
        visible = (distance <= self.profile["seeker_active_range_nm"]
                   and missile.in_field_of_view(self.course, bearing)
                   and not (world is not None and getattr(
                       world, "land_blocks_line", lambda *args: False)(
                           self.x, self.y, frigate.x, frigate.y)))
        if not visible:
            self.lock_s, self.locked, self.los_prev = 0.0, False, None
        elif not self.locked:
            self.lock_s += h
            if self.lock_s >= missile.SEEKER_LOCK_S:
                self.locked, self.los_prev = True, bearing
        if not self.locked:
            # Inertial mid-course towards the launch datum.
            if math.hypot(self.datum_x - self.x, self.datum_y - self.y) > .05:
                self._turn_towards(math.degrees(math.atan2(
                    self.datum_x - self.x, -(self.datum_y - self.y))) % 360.0,
                    self.profile["turn_rate_deg_s"], h)
            return
        if deceived and technique != "false_targets":
            # RGPO/VGPO break the seeker's gate for this update.
            return
        if deceived:
            # A coherent phantom is a bounded angular gate displacement.
            self._turn_towards((bearing + (25.0 if self.seq % 2 else -25.0)) % 360.0,
                               missile.max_turn_rate_deg_s(self.speed_kn), h)
            self.los_prev = None
            return
        if self.los_prev is None:
            self.los_prev = bearing
        rate = missile.pn_turn_rate_deg_s(bearing, self.los_prev, h, self.speed_kn)
        # Close the initial heading error inside the seeker cone as well.
        pursuit = config.angle_diff_deg(bearing, self.course)
        limit = missile.max_turn_rate_deg_s(self.speed_kn)
        rate = config.clamp(rate + 0.5 * pursuit, -limit, limit)
        self.course = (self.course + rate * h) % 360.0
        self.los_prev = bearing

    def update(self, dt: float, frigate, world=None, ecm_effect=None,
               chaff_target=None) -> None:
        if self.state in ("ABGEFANGEN", "TREFFER", "VERLOREN"):
            return
        deceived, technique = (self._ecm_decision(ecm_effect)
                               if self.state == "LAUF" and self.locked
                               and ecm_effect is not None else (False, None))
        steps = min(1000, max(1, math.ceil(dt / missile.GUIDANCE_SUBSTEP_S - 1e-9)))
        h = dt / steps
        for _ in range(steps):
            run = min(h, max(0.0, self.life_s - self.age_s))
            if self.state == "CHAFF":
                if self.broken:
                    run = min(run, max(0.0, self.chaff_left))
                    if chaff_target is not None and run > 0.0:
                        # Seduced: the seeker homes on the chaff centroid.
                        self._turn_towards(math.degrees(math.atan2(
                            chaff_target.x - self.x, -(chaff_target.y - self.y)))
                            % 360.0, missile.max_turn_rate_deg_s(self.speed_kn), run)
                self.chaff_left -= h
            elif run > 0.0:
                self._guide(run, frigate, world, deceived, technique)
            if self.boosting:
                self.speed_kn = missile.speed_step(self.speed_kn, self.cruise_kn, h)
                self.boosting = self.speed_kn < self.cruise_kn
            self.altitude_m = missile.altitude_step(
                self.altitude_m, missile.commanded_altitude_m(
                    self.distance_nm(frigate)), h)
            ox, oy = self.x, self.y
            self.age_s = min(self.life_s, self.age_s + h)
            step = min(config.kn_to_nm_per_s(self.speed_kn) * run,
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
                self.chaff_cloud = None
            if self.state != "LAUF" and self.state != "CHAFF":
                return


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
        self.los_prev = None

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
        limit = self.profile["turn_rate_deg_s"]   # airframe lateral-g limit
        if self.seeker_acquired and self.los_prev is not None and dt > 0.0:
            # Terminal proportional navigation on the seeker's LOS rate, plus
            # a pursuit term that closes the initial heading error.
            los_rate = config.angle_diff_deg(desired, self.los_prev) / dt
            rate = config.clamp(missile.PN_GAIN * los_rate + 0.5 * config.angle_diff_deg(
                desired, self.course), -limit, limit)
            self.course = (self.course + rate * dt) % 360.0
        else:
            diff = config.angle_diff_deg(desired, self.course)
            self.course = (self.course + config.clamp(
                diff, -limit * dt, limit * dt)) % 360.0
        self.los_prev = desired if self.seeker_acquired else None
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
