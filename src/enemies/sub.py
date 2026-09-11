"""U-Boot-Modell: Typen-Daten aus dem Kontakt-Katalog + Patrouillen/Ausweich-KI (M2).

Pro Instanz: sensor_seed + Fingerprint (Blattzahl, Raten-Skala, Tonal-Offsets,
Kavitation/Breitband-Level) – Details in docs/contacts-db.md.
"""

import math
import random

from src.core import config
from src.data import catalog
from src.data import fingerprint as fingerprint_mod
from src.sensors.platform import (
    PlatformObservation,
    PlatformSensorSuite,
    machine_acoustics,
    motion_limits,
    snapshot_observation,
)
from src.weapons.torpedo import underwater_path_blocked
from src.weapons.asw import ConsumableStore, WeaponBattery
from src.enemies.endurance import SubmarineEndurance

CATALOG = catalog.CATALOG
DECOY_PROFILE = CATALOG.get_decoy("decoy")
if DECOY_PROFILE is None:
    raise RuntimeError(
        "Kontaktkatalog unvollstaendig: Dekoy-Profil 'decoy' fehlt")


class SubType:
    """Statik eines U-Boot-Typs (Captain's Log §2)."""

    def __init__(self, key, name, max_depth_m, torpedoes, quiet, speed_kn,
                 aggression, profile, acoustic):
        self.key = key
        self.name = name
        self.max_depth_m = max_depth_m
        self.torpedoes = torpedoes
        self.quiet = quiet          # 0 = laut ... 1 = stumm
        self.speed_min_kn, self.speed_kn = speed_kn
        self.aggression = aggression  # Angriffswahrscheinlichkeit (M5)
        self.profile = profile      # SubProfile (Kontakt-Katalog)
        self.acoustic = acoustic    # TargetSignature


SUB_TYPES = {
    p.key: SubType(p.key, p.name, p.max_depth_m, p.torpedoes, p.quiet,
                    p.speed_kn, p.aggression, p, p.acoustic)
    for p in CATALOG.subs.values()
}


class Sub:
    """U-Boot mit einfacher KI: PATROLLE <-> EVADE (M2)."""

    _next_id = 1

    def __init__(self, x_nm: float, y_nm: float, depth_m: float,
                 course_deg: float, stype_key: str, rng: random.Random,
                 quiet_mult: float = 1.0, attack_mult: float = 1.0,
                  attack_cooldown_s: float = None, profile=None,
                  decoy_profile=None, enemy_torpedo_profile=None, *,
                  side: str = "hostile", doctrine: str = "submarine",
                   runtime_catalog=None, asw_rng=None):
        self.id = Sub._next_id
        Sub._next_id += 1
        self.rng = rng
        self.asw_rng = asw_rng or rng
        runtime_catalog = runtime_catalog or CATALOG
        source = runtime_catalog.subs[stype_key] if profile is None else profile
        self.side = side
        self.doctrine = doctrine
        self.stype = SubType(
            source.key, source.name, source.max_depth_m, source.torpedoes,
            source.quiet, source.speed_kn, source.aggression, source,
            source.acoustic)
        self.decoy_profile = decoy_profile or DECOY_PROFILE
        self.enemy_torpedo_profile = (enemy_torpedo_profile
                                      or CATALOG.get_torpedo("enemy_torp"))
        self.sensor_seed = int(rng.randint(0, 2**31 - 1))
        self.fingerprint = fingerprint_mod.roll_from_seed(
            self.sensor_seed, self.stype.acoustic)
        self.motion = motion_limits(
            runtime_catalog, source.key,
            cruise_speed=min(source.speed_kn[1], 8.0),
            maximum_speed=source.speed_kn[1], turn_rate=0.6,
            acceleration=0.08, depth_rate=0.5)
        self.sensor_suite = PlatformSensorSuite(
            runtime_catalog, source.key, self.sensor_seed,
            side=side, doctrine=doctrine,
            datalink_group="blue" if side == "friendly" else None)
        self.runtime_catalog = runtime_catalog
        endurance_profile = runtime_catalog.endurances.get(f"endurance.{source.key}")
        self.endurance = (SubmarineEndurance(endurance_profile)
                          if endurance_profile is not None else None)
        systems = runtime_catalog.profile_systems.get(source.key)
        self.legacy_observation_model = bool(
            systems is not None and systems.machine_key is not None
            and runtime_catalog.machines[
                systems.machine_key].propulsor_type == "unknown")
        self.quiet_mult = quiet_mult        # M7: Level-Faktor (leicht = lauter)
        self.attack_mult = attack_mult      # M7: Level-Faktor Gegenangriff
        self.attack_cooldown = (config.SUB_ATTACK_COOLDOWN_S
                                if attack_cooldown_s is None else attack_cooldown_s)
        self.x = x_nm
        self.y = y_nm
        self.start_pos = (x_nm, y_nm)   # M6: Flucht-Erkennung
        self.depth = depth_m
        self.course = course_deg % 360.0
        self.target_course = self.course
        self.target_depth = depth_m
        self.speed = rng.uniform(self.stype.speed_min_kn,
                                 min(self.stype.speed_kn, 8.0))
        self.state = "PATROLLE"
        self.evac_left = 0.0
        self.turn_left = rng.uniform(300.0, 900.0)
        self.turn_delta = 0.0
        self.evade_offset = rng.uniform(-30.0, 30.0)
        self._lofar_phase = 0.0  # M11: LOFAR-Pulsphase
        self.sunk = False
        self.heard_ping = False
        self.damage = 0.0     # 0..100
        self.sink_left = 0.0  # Sekunden bis versenkt (Zustand SINKING)
        # M5: Gegenschlag
        self.weapon_battery = WeaponBattery.from_catalog(
            runtime_catalog, source.key, "torpedo")
        self.torpedoes_left = (self.weapon_battery.remaining_total
                               if self.weapon_battery is not None
                               else self.stype.torpedoes)
        self.attack_left = self.attack_cooldown
        self.pending_torpedoes: list[tuple] = []
        # Position, course, depth, observed datum, and runtime profile key.
        # W2: Torpedo-Alarm + Dekoy
        self.torpedo_alerted = False   # eigener Torpedo gehört -> harte Reaktion
        self.pending_decoys: list[tuple[float, float]] = []
        self._decoy_cd = 0.0
        self.countermeasure_store = ConsumableStore.from_catalog(
            runtime_catalog, source.key, "acoustic_decoy")
        # Taktisches Gedaechtnis: nur Ereignisse, die das Boot wahrnimmt.
        self.memory = {
            "last_ping_age": float("inf"),
            "last_torpedo_age": float("inf"),
            "contact_bearing": None,
            "contact_age": config.SUB_EVADE_DURATION_S,
            "contact": None,
        }
        self.decision_reason = "Patrouille"

    # --- Ereignisse ---

    def hear_ping(self) -> None:
        """U-Boot hört einen aktiven Ping -> Ausweichen."""
        if not self.sunk and self.state != "SINKING":
            self.state = "EVADE"
            self.evac_left = config.SUB_EVADE_DURATION_S
            self.heard_ping = True
            self.memory["last_ping_age"] = 0.0
            self.evade_offset = self.rng.uniform(-30.0, 30.0)
            self.decision_reason = "Aktives Sonar gehoert: Ausweichen"

    def alert_torpedo(self) -> None:
        """W2: Feindtorpedo gehört -> harte Ausweichreaktion + ggf. Dekoy."""
        if not self.sunk and self.state != "SINKING":
            self.torpedo_alerted = True
            self.heard_ping = True
            self.state = "EVADE"
            self.evac_left = max(self.evac_left, config.SUB_EVADE_DURATION_S)
            self.memory["last_torpedo_age"] = 0.0
            self.evade_offset = self.rng.uniform(-35.0, 35.0)
            self.decision_reason = "Torpedoalarm: Ausweichen und Dekoy pruefen"

    def utility_scores(self, distance_nm: float, thermo_depth_m: float,
                       frigate_noise: float) -> dict[str, float]:
        """Bewertet taktische Optionen aus lokaler Information.

        Die KI bekommt keine Zielposition aus dem Spielzustand. Werte dienen
        zugleich als Debug-/Balancing-Schnittstelle.
        """
        under_thermo = self.depth >= thermo_depth_m
        threat = max(0.0, 1.0 - distance_nm / 40.0)
        return {
            "hide": (0.55 if under_thermo else 0.25) + threat * 0.30,
            "lurk": (0.45 if distance_nm < config.SUB_LUER_DIST_NM else 0.10)
                    + (0.20 if under_thermo else 0.0),
            "attack": (0.25 + frigate_noise * 0.45
                       + self.stype.aggression * 0.20
                       - distance_nm / 120.0),
            "escape": (self.damage / 100.0) * 0.75
                      + (0.25 if self.torpedoes_left == 0 else 0.0),
        }

    def tactical_decision(self, distance_nm: float, thermo_depth_m: float,
                          frigate_noise: float) -> str:
        """Liefert die beste lokale Utility-Aktion und merkt den Grund."""
        scores = self.utility_scores(distance_nm, thermo_depth_m, frigate_noise)
        action = max(scores, key=scores.get)
        self.decision_reason = f"{action}: {scores[action]:.2f}"
        return action

    def hit(self) -> None:
        """Torpedotreffer: Schaden; bei 100 % Sinkbeginn (Captain's Log §3)."""
        if self.sunk or self.state == "SINKING":
            return
        self.damage = min(100.0, self.damage + self.rng.uniform(60.0, 100.0))
        if self.damage >= 100.0:
            self.state = "SINKING"
            self.sink_left = 20.0
        else:
            self.state = "EVADE"
            self.evac_left = max(self.evac_left, config.SUB_EVADE_DURATION_S)

    # --- M5: Gegenschlag ---

    def _launch_data(self, observation: PlatformObservation, torpedo_profile=None
                     ) -> tuple[float, float, float, float, float, float]:
        """Abzugsdaten: Interzeptions-Kurs mit Vorlauf + Kursfehler."""
        if not isinstance(observation, PlatformObservation):
            observation = snapshot_observation(
                self, observation, domain="sonar", positioned=True)
        course = observation.bearing
        if (observation.x is not None and observation.y is not None
                and observation.range_nm is not None):
            profile = torpedo_profile or self.enemy_torpedo_profile
            enemy_speed = config.kn_to_nm_per_s(profile.speed_kn)
            lead_s = observation.range_nm / max(enemy_speed, 0.001)
            target_speed = config.kn_to_nm_per_s(observation.speed_kn or 0.0)
            target_course = (observation.course if observation.course is not None
                             else observation.bearing)
            px = observation.x + target_speed * lead_s * math.sin(
                math.radians(target_course))
            py = observation.y - target_speed * lead_s * math.cos(
                math.radians(target_course))
            course = math.degrees(math.atan2(px - self.x, -(py - self.y))) % 360.0
            datum_x, datum_y = px, py
        observed_range = observation.range_nm
        if (observation.x is not None and observation.y is not None
                and observation.course is None):
            datum_x, datum_y = observation.x, observation.y
        elif observation.x is None or observation.y is None:
            observed_range = 10.0 if observed_range is None else observed_range
            datum_x = self.x + observed_range * math.sin(math.radians(observation.bearing))
            datum_y = self.y - observed_range * math.cos(math.radians(observation.bearing))
        course = (course + self.asw_rng.uniform(-3.0, 3.0)) % 360.0
        return (self.x, self.y, course, self.asw_rng.uniform(5.0, 12.0),
                datum_x, datum_y)

    def _maybe_attack(self, dt: float, observation: PlatformObservation | None) -> None:
        """Gegenschlag, wenn die Fregatte laut/pinged wurde (Captain's Log §2.2)."""
        if self.side != "hostile" or self.sunk or self.state == "SINKING":
            return
        self.attack_left -= dt
        if (self.attack_left > 0 or self.torpedoes_left <= 0
                or (self.weapon_battery is not None
                    and self.weapon_battery.ready_count <= 0)):
            return
        if observation is None:
            return
        if self.weapon_battery is not None:
            launcher = self.runtime_catalog.launchers[
                self.weapon_battery.launcher_key]
            arc_center = (self.course + launcher.arc_center_deg) % 360.0
            if abs(config.angle_diff_deg(observation.bearing, arc_center)) \
                    > launcher.arc_width_deg / 2.0:
                return
        dist = observation.range_nm
        noise = observation.signal
        close_fix = dist is not None and dist < 20.0
        rate = 0.0
        bearing_counterfire = (dist is None and self.heard_ping
                               and self.memory["last_ping_age"] <= 2.0)
        if (self.state == "EVADE" and self.heard_ping
                and (close_fix or bearing_counterfire)):
            rate = 0.006 * (0.5 + noise) * self.stype.aggression
        elif noise >= 0.75 and dist is not None and dist < 18.0:
            rate = 0.002 * self.stype.aggression
        rate *= self.attack_mult
        if rate > 0 and self.asw_rng.random() < rate * dt:
            n = min(2 if dist is not None and dist < 12.0
                    and self.stype.aggression > .8 else 1,
                    self.torpedoes_left, 2 - len(self.pending_torpedoes))
            launched = 0
            for _ in range(n):
                profile = self.enemy_torpedo_profile
                fired_key = None
                if self.weapon_battery is not None:
                    fired_key = self.weapon_battery.fire()
                    if fired_key is None:
                        break
                    runtime_key = self.runtime_catalog.weapons[
                        fired_key].runtime_profile_key
                    if runtime_key is None:
                        break
                    profile = self.runtime_catalog.torpedoes[runtime_key]
                self.pending_torpedoes.append(
                    (*self._launch_data(observation, profile), profile.key,
                     self.id, fired_key))
                launched += 1
            if launched:
                self.torpedoes_left = (self.weapon_battery.remaining_total
                                       if self.weapon_battery is not None
                                       else self.torpedoes_left - launched)
                self.attack_left = self.attack_cooldown

    # --- M13: Schnorcheln / Funk ---

    @property
    def transmitting(self) -> bool:
        """Only the explicit radio phase is detectable by HFDF."""
        return self.endurance is not None and self.endurance.transmitting

    # --- Physik/KI ---

    def update(self, dt: float, observation, world) -> None:
        """dt in Simulationssekunden; bei 1x identisch zu Echtzeit."""
        if self.sunk:
            return
        depth_at = getattr(world, "depth_m", lambda x, y: 1000.0)
        bottom = depth_at(self.x, self.y)
        safe_depth = min(self.stype.max_depth_m, max(0.0, bottom - 25.0))
        self.target_depth = config.clamp(self.target_depth, 0.0, safe_depth)
        old_depth = self.depth
        for key in ("last_ping_age", "last_torpedo_age"):
            if self.memory[key] != float("inf"):
                self.memory[key] += dt
        thermo = world.thermocline_depth_m(self.x, self.y)
        world_size = world.size_nm
        self._decoy_cd = max(0.0, self._decoy_cd - dt)
        if self.weapon_battery is not None:
            self.weapon_battery.update(dt)
            self.torpedoes_left = self.weapon_battery.remaining_total
        if self.countermeasure_store is not None:
            self.countermeasure_store.update(dt)
        if observation is not None and not isinstance(observation, PlatformObservation):
            target = observation
            observation = None
            distance = (self.distance_nm(target)
                        if hasattr(target, "x") and hasattr(target, "y") else None)
            received_ping = self.memory["last_ping_age"] <= dt
            if (distance is not None and distance < 20.0
                    and (received_ping
                         or (target.noise_level() >= 0.75 and distance < 18.0))
                    and not getattr(world, "sonar_path_blocked", lambda *args: False)(
                        self.x, self.y, self.depth, target.x, target.y, 5.0)):
                observation = snapshot_observation(
                    self, target, domain="sonar", positioned=True)

        # W2: Torpedo-Alarm -> einmalig Dekoy-Abwurf (Chance je Level-Faktor)
        if self.torpedo_alerted and self._decoy_cd <= 0.0:
            if (not self.pending_decoys and self.countermeasure_store is not None
                    and self.asw_rng.random() < self.decoy_profile.chance
                    and self.countermeasure_store.fire()):
                self.pending_decoys.append((self.x, self.y))
                self._decoy_cd = self.decoy_profile.cooldown_s
            self.torpedo_alerted = False

        if self.state == "SINKING":
            self.sink_left = max(0.0, self.sink_left - dt)
            self.depth += 3.0 * dt
            self.speed = 0.0
            if self.sink_left <= 0:
                self.state = "SUNK"
                self.sunk = True
            return

        self.speed = config.clamp(self.speed, 0.0, self.motion.maximum_speed_kn)

        # Retain only a bounded local acoustic observation, never a live ship
        # reference. Ping memory does not continuously refresh hidden motion.
        self.memory["contact_age"] = min(config.SUB_EVADE_DURATION_S,
                                         self.memory["contact_age"] + dt)
        fresh_observation = (observation is not None and (
            observation.track_id in ("LEGACY", "MEMORY")
            or observation.last_seen > self.sensor_suite.last_consumed_s))
        if fresh_observation:
            self.memory["contact"] = (
                dict(x=observation.x, y=observation.y,
                     speed=observation.speed_kn or 0.0,
                     course=(observation.course if observation.course is not None
                             else observation.bearing),
                     noise=observation.signal)
                if observation.x is not None and observation.y is not None else None)
            self.memory["contact_age"] = 0.0
            self.memory["contact_bearing"] = observation.bearing
            self.sensor_suite.last_consumed_s = max(
                self.sensor_suite.last_consumed_s, observation.last_seen)
        if self.memory["contact_age"] >= config.SUB_EVADE_DURATION_S:
            self.memory["contact"] = None
            self.memory["contact_bearing"] = None
        tactical_observation = observation
        if tactical_observation is None and self.memory["contact"] is not None:
            remembered = self.memory["contact"]
            distance = math.hypot(remembered["x"] - self.x,
                                  remembered["y"] - self.y)
            tactical_observation = PlatformObservation(
                track_id="MEMORY", domain="sonar", source="SONAR",
                observer_x=self.x, observer_y=self.y,
                bearing=self.memory["contact_bearing"], range_nm=distance,
                x=remembered["x"], y=remembered["y"],
                course=remembered["course"], speed_kn=remembered["speed"],
                depth_m=5.0, quality=max(
                    0.0, 1.0 - self.memory["contact_age"]
                    / config.SUB_EVADE_DURATION_S),
                signal=remembered["noise"], last_seen=0.0,
                bearing_uncertainty_deg=None, range_uncertainty_nm=None,
                depth_uncertainty_m=None, label=None)
        self._maybe_attack(dt, tactical_observation)

        surface_steps = 0
        if self.endurance is not None and self.endurance.surface_operation:
            dt, surface_steps = self._update_surface_cycle(
                dt, safe_depth, SubmarineEndurance.MAX_SUBSTEPS)
            if dt <= 0.0:
                return
            old_depth = self.depth

        if self.state == "EVADE":
            self.evac_left -= dt
            if self.evac_left <= 0:
                # W2: In der Nähe der Fregatte -> still halten und lauschen
                if (tactical_observation is not None
                        and tactical_observation.range_nm is not None
                        and tactical_observation.range_nm < config.SUB_LUER_DIST_NM):
                    self.state = "LAUER"
                    self.evac_left = self.rng.uniform(*config.SUB_LUER_DURATION_S)
                    self.heard_ping = False
                    self.speed = 0.5
                else:
                    self.state = "PATROLLE"
                    self.heard_ping = False
                    self.speed = min(6.0, self.speed_for_state())
                    self.target_depth = min(safe_depth, self.rng.uniform(40.0, 80.0))
                    self.turn_left = self.rng.uniform(300.0, 900.0)
                    self.turn_delta = 0.0
                if self.endurance is not None:
                    self.endurance.update(
                        dt, self.speed, self.motion.maximum_speed_kn, self.depth)
                return
            # Tiefer unter die Thermokline + Kurs ab der Fregatte
            self.target_depth = min(thermo + 40.0, safe_depth)
            rate = self.motion.depth_rate_m_s * 3.0
            self.depth += config.clamp(self.target_depth - self.depth,
                                       -rate * dt, rate * dt)
            bearing = self.memory["contact_bearing"]
            target_course = (self.course if bearing is None else
                             (bearing + 180.0 + self.evade_offset) % 360.0)
            diff = config.angle_diff_deg(target_course, self.course)
            self.course = (self.course + config.clamp(
                diff, -self.motion.turn_rate_deg_s * 2.5 * dt,
                self.motion.turn_rate_deg_s * 2.5 * dt)) % 360.0
            self.speed = max(self.speed, min(self.speed_for_state(),
                                             max(10.0, self.stype.speed_kn * .9)))
        elif self.state == "LAUER":
            # W2: Stillhalten unter der Thermokline (sehr leise, lauschen)
            self.evac_left -= dt
            self.target_depth = min(thermo + 15.0, safe_depth)
            self.depth += config.clamp(self.target_depth - self.depth,
                                       -self.motion.depth_rate_m_s * dt,
                                       self.motion.depth_rate_m_s * dt)
            self.speed = max(1.0, self.speed - .08 * dt)
            if self.evac_left <= 0:
                self.state = "PATROLLE"
                self.speed = min(6.0, self.speed_for_state())
                self.turn_left = self.rng.uniform(300.0, 900.0)
                self.turn_delta = 0.0
        else:
            # Patrouille: lange, ruhige Legs statt dauernder Kreisfahrt.
            self.turn_left -= dt
            if self.turn_left <= 0:
                self.turn_left = self.rng.uniform(300.0, 900.0)
                self.target_course = (self.course
                                      + self.rng.uniform(-45.0, 45.0)) % 360.0
                self.target_depth = self.rng.uniform(
                    40.0, min(self.stype.max_depth_m, max(80.0, thermo + 30.0)))
                patrol_max = min(8.0, self.speed_for_state())
                self.speed = self.rng.uniform(
                    min(3.0, patrol_max), max(min(3.0, patrol_max), patrol_max))
            diff = config.angle_diff_deg(self.target_course, self.course)
            self.course = (self.course + config.clamp(
                diff, -self.motion.turn_rate_deg_s * dt,
                self.motion.turn_rate_deg_s * dt)) % 360.0
            self.target_depth = config.clamp(self.target_depth, 0.0, safe_depth)
            self.depth += config.clamp(
                self.target_depth - self.depth,
                -self.motion.depth_rate_m_s * dt,
                self.motion.depth_rate_m_s * dt)
            # R15 consumed this patrol snorkel-trigger draw. Preserve the shared
            # world stream while endurance now decides when air is required.
            if self.stype.profile.requires_air and self.depth > 55.0:
                self.rng.random()

        motion_dt = dt
        if self.endurance is not None:
            motion_dt = self.endurance.time_until_surface_operation(
                dt, self.speed, self.motion.maximum_speed_kn, self.depth)
            self.speed = self.endurance.supported_speed(
                motion_dt, self.speed, self.motion.maximum_speed_kn, self.depth)
        v = config.kn_to_nm_per_s(self.speed) * motion_dt
        nx = self.x + v * math.sin(math.radians(self.course))
        ny = self.y - v * math.cos(math.radians(self.course))
        if (world.on_land(nx, ny) or underwater_path_blocked(
                world, self.x, self.y, old_depth + 25.0 - 1e-6,
                nx, ny, self.depth + 25.0 - 1e-6)):
            self.target_course = (self.course + 90.0) % 360.0
            self.course = self.target_course
        else:
            self.x, self.y = nx, ny

        # Welt-Rand: Kurs spiegeln (nautisch: x-Rand -> 360-C, y-Rand -> 180-C)
        if self.x < 0 or self.x > world_size:
            self.course = (360.0 - self.course) % 360.0
            self.x = config.clamp(self.x, 0.0, world_size)
        if self.y < 0 or self.y > world_size:
            self.course = (180.0 - self.course) % 360.0
            self.y = config.clamp(self.y, 0.0, world_size)

        if self.endurance is not None:
            self.endurance.update(motion_dt, self.speed, self.motion.maximum_speed_kn,
                                  self.depth)
            remaining_steps = (SubmarineEndurance.MAX_SUBSTEPS
                               - surface_steps - 1)
            if motion_dt < dt and remaining_steps > 0:
                self._update_surface_cycle(
                    dt - motion_dt, safe_depth, remaining_steps)

    def _update_surface_cycle(self, dt: float, safe_depth: float,
                              max_steps: int) -> tuple[float, int]:
        self.speed = 0.0
        remaining = dt
        max_step = max(SubmarineEndurance.MAX_STEP_S,
                       dt / max_steps)
        steps = 0
        for index in range(max_steps):
            if remaining <= 0.0:
                break
            step = (remaining if index == max_steps - 1
                    else min(max_step, remaining))
            if self.endurance.phase == "DESCENDING":
                self.target_depth = min(safe_depth,
                                        self.endurance.return_depth_m)
            else:
                self.target_depth = min(
                    safe_depth, self.endurance.profile.snorkel_depth_m)
            depth_rate = self.motion.depth_rate_m_s
            event_depth = self.target_depth
            if self.endurance.phase == "ASCENDING":
                event_depth = (self.endurance.profile.snorkel_depth_m
                               + self.endurance.DEPTH_TOLERANCE_M)
            elif self.endurance.phase == "DESCENDING":
                event_depth = (self.endurance.return_depth_m
                               - self.endurance.DEPTH_TOLERANCE_M)
            depth_event = (abs(event_depth - self.depth) / depth_rate
                           if depth_rate > 0.0 else 0.0)
            if index < max_steps - 1 and depth_event > 0.0:
                step = min(step, depth_event)
            start_depth = self.depth
            next_depth = self.depth + config.clamp(
                self.target_depth - self.depth,
                -depth_rate * step,
                depth_rate * step)
            self.endurance.update(
                step, self.speed, self.motion.maximum_speed_kn, start_depth)
            steps += 1
            self.depth = next_depth
            self.endurance._advance_instantaneous(self.depth)
            remaining = max(0.0, remaining - step)
            if not self.endurance.surface_operation:
                break
        if self.endurance.surface_operation:
            return 0.0, steps
        if self.state == "EVADE":
            self.speed = min(self.speed_for_state(),
                             max(10.0, self.stype.speed_kn * .9))
        elif self.state == "LAUER":
            self.speed = 1.0
        else:
            self.speed = min(6.0, self.speed_for_state())
        return remaining, steps

    # --- Akustik ---

    def quiet_factor(self) -> float:
        """Stillheit: Sprint/Ausweichen laut, LAUER besonders leise."""
        q = self.stype.quiet * self.quiet_mult - 0.30 * (self.damage / 100.0)
        if self.state == "EVADE":
            q -= 0.30
        if self.state == "LAUER":
            q = max(0.97, q + 0.08)
        if self.transmitting:
            q += config.SNOCKEL_TRANSMIT_NOISE  # M13: Senden macht lauter
        return config.clamp(q, 0.0, 1.0)

    def noise_level(self) -> float:
        return 1.0 - self.quiet_factor()

    def acoustic_signature(self) -> str:
        """M9: Hörbare Geräusch-Signatur für manuelle Klassifizierung.

        Kein exakter Typ, sondern das, was ein Hörposten wahrnehmen würde:
        Antriebsart + aktuelle Frequenz (Fahrt/Zustand).
        """
        if self.sunk:
            return ""
        if self.transmitting:
            return "mechanisch · Funkverkehr (HF), Sender aktiv"
        base = self.stype.acoustic.signature_text or "unbekanter Antrieb"
        if self.state == "EVADE":
            freq = "Frequenz hoch (Ausweichmanöver)"
        elif self.speed >= 10.0:
            freq = "Frequenz hoch (schnelle Fahrt)"
        else:
            freq = "Frequenz niedrig (Langfahrt)"
        detail = (f" · DEMON {self.stype.acoustic.tonal_band_hz[0]:.0f}-"
                  f"{self.stype.acoustic.tonal_band_hz[1]:.0f} Hz")
        return f"mechanisch · {base} · {freq}{detail}"

    def speed_for_state(self) -> float:
        """Fahrt bei Schaden: langsamer je nach Schadensgrad."""
        return self.motion.maximum_speed_kn * (1.0 - 0.25 * self.damage / 100.0)

    def distance_nm(self, frigate) -> float:
        return math.hypot(self.x - frigate.x, self.y - frigate.y)

    def bearing_from_frigate(self, frigate) -> float:
        """Nautische Peilung: 0° = Nord (nach oben), 90° = Ost, im Uhrzeigersinn."""
        dx = self.x - frigate.x
        dy = self.y - frigate.y
        return math.degrees(math.atan2(dx, -dy)) % 360.0

    @property
    def sensor_domain(self) -> str:
        return "subsurface" if self.depth > 5.0 else "surface"

    # --- M11/W1: LOFAR-Signatur + Breitband ---

    def lofar_lines(self, t_sim: float = 0.0) -> list:
        """Diskrete Frequenzlinien (freq_hz, amp 0..1, Breite in Bins).

        Hauptschraube-Linie (Frequenz folgt der Fahrt über das Profil-Band,
        pro Instanz per Fingerprint versetzt), Harmonische bei schneller
        Fahrt, Getriebe-Tonals aus dem Profil, HF-Sender beim Schnorcheln
        und Schadens-Grundrauschen bei hoher Schädigung."""
        if self.sunk:
            return []
        profiled = machine_acoustics(
            self.runtime_catalog, self.stype.key, self.speed)
        if profiled is not None:
            lines, _ = profiled
            result = list(lines)
            if self.transmitting:
                result.extend(((20.0, 0.95, 2.0), (35.0, 0.70, 1.5)))
            if self.damage > 30.0:
                result.append((55.0, 0.25 + 0.45 * self.damage / 100.0, 4.0))
            return result
        lines = []
        v = max(0.0, self.speed)
        sig = self.stype.acoustic
        fp = self.fingerprint
        vmax = max(1.0, self.stype.speed_kn)
        if v > 0.5:
            f = (fp.rate_scale
                 * (sig.tonal_band_hz[0]
                    + (sig.tonal_band_hz[1] - sig.tonal_band_hz[0])
                    * min(1.0, v / vmax))
                 + fp.offsets[0])
            f = max(2.0, f)
            amp = 0.25 + 0.55 * min(1.0, v / 18.0)
            if self.state == "EVADE":
                f *= 1.2
                amp = min(1.0, amp + 0.30)
            if self.state == "LAUER":
                amp *= 0.5
            lines.append((f, amp, 1.5))
            if v > 4.0:
                lines.append((f * 2.0 + fp.offsets[1], amp * 0.5, 1.2))
                lines.append((f * 3.0 + fp.offsets[2], amp * 0.3, 1.0))
            for hz, a, width in sig.secondary_tonals:
                lines.append((hz, a * min(1.0, v / 6.0), width))
        if self.transmitting:
            lines.append((20.0, 0.95, 2.0))
            lines.append((35.0, 0.70, 1.5))
        if self.damage > 30.0:
            lines.append((55.0, 0.25 + 0.45 * self.damage / 100.0, 4.0))
        return lines

    def broadband(self) -> dict:
        """Breitbandige Rausch-Quelle (level 0..1 + Band) für Audio/BTR."""
        sig = self.stype.acoustic
        profiled = machine_acoustics(
            self.runtime_catalog, self.stype.key, self.speed)
        if profiled is not None:
            _, broadband = profiled
            if self.sunk or broadband is None:
                return {}
            level = broadband[0]
            if self.state == "EVADE":
                level *= 1.6
            if self.state == "LAUER":
                level *= 0.5
            return {"level": min(1.0, level + 0.10 * self.damage / 100.0),
                    "low_hz": broadband[1], "high_hz": broadband[2]}
        if self.sunk or sig.broadband is None:
            return {}
        v = max(0.0, self.speed)
        vmax = max(1.0, self.stype.speed_kn)
        level = self.fingerprint.bb_level * (0.15 + 0.85 * min(1.0, v / vmax))
        if self.state == "EVADE":
            level *= 1.6
        if self.state == "LAUER":
            level *= 0.5
        level = min(1.0, level + 0.10 * (self.damage / 100.0))
        return {"level": min(1.0, level),
                "low_hz": sig.broadband[1],
                "high_hz": sig.broadband[2]}
