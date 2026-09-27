"""U-Boot-Modell: Typen-Daten aus dem Kontakt-Katalog + Patrouillen/Ausweich-KI (M2).

Pro Instanz: sensor_seed + Fingerprint (Blattzahl, Raten-Skala, Tonal-Offsets,
Kavitation/Breitband-Level) – Details in docs/contacts-db.md.
"""

import math
import random

from src.core import config
from src.physics import submarine as sub_physics
from src.core import detrand
from src.sonar.tma import BearingTrack, solve_tma
from src.data import catalog
from src.data import fingerprint as fingerprint_mod
from src.sensors.platform import (
    MAST_DEPTH_M,
    PlatformObservation,
    PlatformSensorSuite,
    machine_acoustics,
    motion_limits,
    side_datalink_group,
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


SUB_REACTION_MEDIAN_S = 5.0
SUB_TMA_RESOLVE_S = 30.0
# A TMA solution older than this (no bearing since) is not fired on.
SUB_SOLUTION_MAX_AGE_S = 90.0
# A measured bearing this far (deg, plus three sigma) off the dead-reckoned
# solution means the target manoeuvred: the solution reopens and needs this
# many new bearings before the next accepted solve.
SUB_SOLUTION_REOPEN_DEG = 3.0
SUB_SOLUTION_REOPEN_BEARINGS = 3


def solution_predicts_bearing(remembered: dict, contact_t, observer_x: float,
                              observer_y: float, now: float) -> float | None:
    """Bearing the remembered solution predicts at ``now`` (dead reckoning)."""
    if remembered is None or contact_t is None:
        return None
    elapsed = max(0.0, float(now) - float(contact_t))
    run_nm = config.kn_to_nm_per_s(float(remembered["speed"])) * elapsed
    x = remembered["x"] + run_nm * math.sin(math.radians(remembered["course"]))
    y = remembered["y"] - run_nm * math.cos(math.radians(remembered["course"]))
    return math.degrees(math.atan2(x - observer_x, -(y - observer_y))) % 360.0


def solution_sigma_nm(solution, range_nm: float) -> float:
    """1-sigma range error of a TMA solution: the error ellipse's semi-major
    axis when the solver provides one, else the quality-scaled range."""
    ellipse = getattr(solution, "ellipse", None)
    if ellipse is not None and len(ellipse) >= 1 and ellipse[0] is not None:
        return max(0.0, float(ellipse[0]))
    return max(0.0, (1.0 - float(solution.quality)) * float(range_nm))


def solution_converged(sigma_nm, range_nm: float, threshold: float,
                       age_s: float) -> bool:
    """Fire-control gate on an own TMA solution: sigma/range at or below the
    difficulty threshold and a bearing newer than SUB_SOLUTION_MAX_AGE_S."""
    if sigma_nm is None or range_nm is None or range_nm <= 0.0:
        return False
    return (float(sigma_nm) / max(0.1, float(range_nm)) <= float(threshold)
            and float(age_s) <= SUB_SOLUTION_MAX_AGE_S)
SUB_TMA_LEG_TURN_DEG = 35.0
# Hiding beside a charted wreck: the boat lies still on the bottom next to
# the wreck, so an active echo without Doppler merges with the wreck echo.
SUB_WRECK_HIDE_RANGE_NM = 8.0
SUB_WRECK_HIDE_S = (900.0, 1800.0)
SUB_WRECK_STANDOFF_NM = 0.02        # beyond the wreck's footprint
SUB_WRECK_ARRIVED_NM = 0.015
SUB_WRECK_MIN_BOTTOM_M = 40.0
SUB_BOTTOM_CLEARANCE_M = 3.0
SUB_WRECK_TRANSIT_KN = 4.0
SUB_WRECK_MAX_DEPTH_FRACTION = 0.85
# States in which the boat runs silent (lurking, or lying by a wreck).
QUIET_STATES = ("LAUER", "WRACK")
# A crewed boat keeps at most this many fired torpedoes waiting for launch.
SUB_MAX_PENDING_TORPEDOES = 2


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
                  solution_threshold: float = 0.20,
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
            datalink_group=side_datalink_group(side))
        self.runtime_catalog = runtime_catalog
        endurance_profile = runtime_catalog.endurances.get(f"endurance.{source.key}")
        self.endurance = (SubmarineEndurance(endurance_profile)
                          if endurance_profile is not None else None)
        systems = runtime_catalog.profile_systems.get(source.key)
        # Every submarine now senses through its own sensor suite (passive
        # bearings, own TMA, ESM at periscope depth, hostile datalink).
        self.legacy_observation_model = False
        self.quiet_mult = quiet_mult        # M7: Level-Faktor (leicht = lauter)
        self.attack_mult = attack_mult      # M7: Level-Faktor Gegenangriff
        # Fire-control convergence: range sigma / range of the own TMA
        # solution must be at or below this before a shot on it.
        self.solution_threshold = float(solution_threshold)
        self.attack_cooldown = (config.SUB_ATTACK_COOLDOWN_S
                                if attack_cooldown_s is None else attack_cooldown_s)
        self.x = x_nm
        self.y = y_nm
        self.start_pos = (x_nm, y_nm)   # M6: Flucht-Erkennung
        self.depth = depth_m
        self.course = course_deg % 360.0
        self.target_course = self.course
        self.target_depth = depth_m
        # W2: signed vertical rate (+ = descending), acceleration-limited so
        # depth changes have inertia instead of snapping to the full rate.
        self.depth_rate_mps = 0.0
        # Physics state (saved): one emergency blow, blow in progress, loud
        # transient timer (launch/blow) and pressure-hull fatigue (0..1).
        self.blow_available = True
        # Own passive TMA on one bearing-only contact and crew reaction.
        self.tma_track = BearingTrack()
        self.tma_track_id = None
        self.tma_next_t = 0.0
        self.torpedo_alarm_left = -1.0
        self.emergency_ascent = False
        self.transient_left = 0.0
        self.hull_fatigue = 0.0
        self.speed = rng.uniform(self.stype.speed_min_kn,
                                 min(self.stype.speed_kn, 8.0))
        self.speed_order = self.speed
        self._last_actual_speed = self.speed
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
        # W2: aktiver Ping als riskante, seltene Aufklärungsaktion
        self._active_ping_cd = 0.0
        self.pinged_this_tick = False
        self.countermeasure_store = ConsumableStore.from_catalog(
            runtime_catalog, source.key, "acoustic_decoy")
        # Taktisches Gedaechtnis: nur Ereignisse, die das Boot wahrnimmt.
        self.memory = {
            "last_ping_age": float("inf"),
            "last_torpedo_age": float("inf"),
            "contact_bearing": None,
            "contact_age": config.SUB_EVADE_DURATION_S,
            "contact": None,
            # Own fire-control solution: 1-sigma range error (NM) and the
            # time of the last bearing it rests on (None without a solution).
            "contact_sigma_nm": None,
            "contact_t": None,
            # Bearings still needed before a solution is trusted again after
            # the target's manoeuvre broke the previous one (0 = none).
            "contact_reopen_left": 0,
        }
        self.decision_reason = "Patrouille"
        # Crew control (transient, never saved): while ``manual`` the AI state
        # machine is bypassed and the boat follows only the crew's orders.
        self.manual = False
        # Transient crew settings of a crewed boat (``opfor.CrewOrders``);
        # None for the AI. Never saved, like the crew binding itself.
        self.crew = None
        self.last_bottom_m = None
        self.order_course = self.course
        self.order_speed = self.speed
        self.order_depth = self.target_depth
        self._manual_ping_pending = False

    # --- Ereignisse ---

    def _crew_alarm(self, source, tag: str, sigma_deg: float, previous_age: float):
        """A crewed boat's measured bearing to an alarm source (with a
        deterministic error); logged once per alarm episode."""
        crew = self.crew
        if not self.manual or crew is None or source is None:
            return
        crew.alarm_seq += 1
        true = math.degrees(math.atan2(source[0] - self.x, -(source[1] - self.y)))
        bearing = (true + sigma_deg * detrand.normal(
            self.sensor_seed, tag, crew.alarm_seq)) % 360.0
        setattr(crew, f"{tag}_bearing", bearing)
        if previous_age >= 20.0:
            crew.event(f"{tag}_heard", bearing=f"{bearing:03.0f}")

    def hear_ping(self, source=None) -> None:
        """U-Boot hört einen aktiven Ping -> Ausweichen."""
        if self.manual:
            # A crewed boat only notes the intercept; the crew decides.
            if not self.sunk and self.state != "SINKING":
                self.heard_ping = True
                previous = self.memory["last_ping_age"]
                self.memory["last_ping_age"] = 0.0
                self._crew_alarm(source, "ping", config.PING_INTERCEPT_SIGMA_DEG, previous)
            return
        if not self.sunk and self.state != "SINKING":
            self.state = "EVADE"
            self.evac_left = config.SUB_EVADE_DURATION_S
            self.heard_ping = True
            self.memory["last_ping_age"] = 0.0
            self.evade_offset = self.rng.uniform(-30.0, 30.0)
            self.decision_reason = "Aktives Sonar gehoert: Ausweichen"

    def reaction_delay_s(self) -> float:
        """Crew recognition time for a torpedo alarm (per boat, lognormal)."""
        spread = detrand.normal(self.sensor_seed, "crew-reaction")
        return config.clamp(math.exp(math.log(SUB_REACTION_MEDIAN_S) + 0.5 * spread),
                            2.0, 15.0)

    def alert_torpedo(self, source=None) -> None:
        """Torpedo heard: after the crew's recognition time, evade hard."""
        if self.sunk or self.state == "SINKING":
            return
        if self.manual:
            previous = self.memory["last_torpedo_age"]
            self.memory["last_torpedo_age"] = 0.0
            self._crew_alarm(source, "torpedo", 5.0, previous)
            return
        if self.state == "EVADE" or self.torpedo_alarm_left == 0.0:
            # Already evading, or the recognition time has elapsed.
            self._react_to_torpedo()
            return
        if self.torpedo_alarm_left < 0.0:
            self.torpedo_alarm_left = self.reaction_delay_s()

    def _react_to_torpedo(self) -> None:
        """W2: Feindtorpedo gehört -> harte Ausweichreaktion + ggf. Dekoy."""
        self.torpedo_alarm_left = -1.0
        if self.manual:
            return
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

    def hit(self, amount: float | None = None) -> None:
        """Torpedotreffer: Schaden; bei 100 % Sinkbeginn (Captain's Log §3).

        ``amount`` is the warhead's shock-factor damage from the proximity
        fuze; without it the historical 60-100 draw applies."""
        if self.sunk or self.state == "SINKING":
            return
        if amount is None:
            amount = self.rng.uniform(60.0, 100.0)
        self.damage = min(100.0, self.damage + amount)
        if self.damage >= 100.0:
            self.state = "SINKING"
            self.sink_left = 20.0
        elif not self.manual:
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
        if (observation.fix_source == "TMA" and dist is not None
                and not solution_converged(observation.range_uncertainty_nm, dist,
                                           self.solution_threshold,
                                           self.memory["contact_age"])):
            # Own TMA only: the solution has not converged (or a target
            # manoeuvre re-opened it), so the boat keeps tracking instead.
            return
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
                    self.torpedoes_left,
                    SUB_MAX_PENDING_TORPEDOES - len(self.pending_torpedoes))
            if self._fire_salvo(observation, n):
                self.attack_left = self.attack_cooldown

    def _fire_salvo(self, observation: PlatformObservation, count: int) -> int:
        """Load up to ``count`` torpedoes on ``observation``; returns fired."""
        launched = 0
        for _ in range(count):
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
            # Tube discharge: a loud, short launch transient.
            self.transient_left = max(self.transient_left,
                                      sub_physics.LAUNCH_TRANSIENT_S)
        return launched

    def _maybe_active_ping(self, dt: float) -> bool:
        """W2: ein aggressives Boot mit frischem Kontakt riskiert selten einen
        aktiven Ping zur Zielaufklärung - laut und sofort vom Ziel gehört,
        keine Feuerlösungsverbesserung (kein Balance-Eingriff, nur Spannung/
        Wahrnehmbarkeit)."""
        self._active_ping_cd = max(0.0, self._active_ping_cd - dt)
        if (self.side != "hostile" or self.sunk or self.state == "SINKING"
                or self._active_ping_cd > 0.0
                or self.stype.aggression < config.SUB_ACTIVE_PING_MIN_AGGRESSION
                or self.memory["contact"] is None
                or self.memory["contact_age"] > 5.0):
            return False
        contact = self.memory["contact"]
        distance = math.hypot(contact["x"] - self.x, contact["y"] - self.y)
        if distance > config.SUB_ACTIVE_PING_MAX_RANGE_NM:
            return False
        if self.asw_rng.random() >= config.SUB_ACTIVE_PING_CHANCE_PER_S * dt:
            return False
        self._active_ping_cd = config.SUB_ACTIVE_PING_COOLDOWN_S
        return True

    # --- M13: Schnorcheln / Funk ---

    @property
    def transmitting(self) -> bool:
        """Only the explicit radio phase is detectable by HFDF."""
        return self.endurance is not None and self.endurance.transmitting

    # --- Physik/KI ---

    # --- physics: planes, hull stress, cavitation, source level ---------------

    def _ingest_bearing(self, observation) -> None:
        """Own passive TMA from bearings of one tracked contact."""
        if observation.track_id != self.tma_track_id:
            self.tma_track = BearingTrack()
            self.tma_track_id = observation.track_id
        sigma_deg = max(0.5, observation.bearing_uncertainty_deg or 0.5)
        self.tma_track.add(observation.last_seen, observation.bearing, self.x,
                           self.y, self.course, sigma_deg, None, self.speed)
        predicted = solution_predicts_bearing(
            self.memory["contact"], self.memory["contact_t"], self.x, self.y,
            observation.last_seen)
        if (predicted is not None and self.memory["contact_reopen_left"] == 0
                and abs(config.angle_diff_deg(observation.bearing, predicted))
                > SUB_SOLUTION_REOPEN_DEG + 3.0 * sigma_deg):
            # Target manoeuvre: the solution no longer explains the bearing.
            # The plot restarts from here, as an operator would, so the next
            # solution rests on post-manoeuvre bearings only.
            self.memory["contact_reopen_left"] = SUB_SOLUTION_REOPEN_BEARINGS
            self.memory["contact_sigma_nm"] = None
            self.tma_track = BearingTrack()
            self.tma_track.add(observation.last_seen, observation.bearing, self.x,
                               self.y, self.course, sigma_deg, None, self.speed)
        elif self.memory["contact_reopen_left"] > 0:
            self.memory["contact_reopen_left"] -= 1
            if self.memory["contact_reopen_left"] == 0:
                self.tma_next_t = observation.last_seen   # solve on this bearing
        if self.memory["contact_reopen_left"] > 0 or observation.last_seen < self.tma_next_t:
            return
        self.tma_next_t = observation.last_seen + SUB_TMA_RESOLVE_S
        solution = solve_tma(self.tma_track)
        if solution is None or solution.quality < config.TMA_RANGE_MIN_QUALITY:
            return
        self.memory["contact"] = dict(
            x=solution.pos[0], y=solution.pos[1], speed=solution.speed,
            course=solution.course, noise=observation.signal)
        self.memory["contact_age"] = 0.0
        self.memory["contact_bearing"] = observation.bearing
        self.memory["contact_sigma_nm"] = solution_sigma_nm(
            solution, math.hypot(solution.pos[0] - self.x, solution.pos[1] - self.y))
        self.memory["contact_t"] = float(observation.last_seen)

    def _update_hull_stress(self, dt: float) -> None:
        """Pressure-hull fatigue below test depth; collapse beyond crush depth."""
        test = self.stype.max_depth_m
        if self.depth >= sub_physics.crush_depth_m(test):
            self.damage = 100.0
        self.hull_fatigue += sub_physics.fatigue_rate_per_s(self.depth, test) * dt
        if self.hull_fatigue >= 1.0:
            self.hull_fatigue -= 1.0
            self.damage = min(100.0, self.damage + 20.0)
        if self.damage >= 100.0 and self.state != "SINKING":
            self.state = "SINKING"
            self.sink_left = 20.0

    def cavitation_onset_kn(self) -> float:
        acoustic = self.stype.acoustic
        onset = getattr(acoustic, "cavitation_speed_knots", None)
        if onset is None:
            tendency = getattr(acoustic, "cavitation_tendency", 0.5)
            onset = self.stype.speed_kn * (1.0 - 0.5 * tendency)
        return sub_physics.cavitation_speed_kn(onset, 0.0) if onset else 99.0

    @property
    def cavitating(self) -> bool:
        return self.speed > sub_physics.cavitation_speed_kn(
            self.cavitation_onset_kn(), self.depth)

    def source_level_offset_db(self) -> float:
        """Radiated-level change from speed, cavitation and transients."""
        level = sub_physics.source_speed_db(
            self.speed, sub_physics.SUBMARINE_REFERENCE_SPEED_KN, self.cavitating)
        if self.transient_left > 0.0:
            level += sub_physics.LAUNCH_TRANSIENT_DB
        if self.snorkeling:
            level += config.UBOOT_SNORKEL_NOISE_DB   # diesels running at snorkel depth
        return level

    def _advance_depth(self, target_depth: float, max_rate: float, dt: float) -> None:
        """Acceleration-limited depth approach (closed-form, no overshoot).

        Replaces an instant-full-rate clamp with inertia: depth_rate_mps
        ramps toward +/-max_rate at SUB_DEPTH_ACCEL_MPS2, and the step is the
        exact trapezoidal integral of that constant-acceleration segment -
        deterministic and exact as long as the rate does not saturate mid-
        segment. Callers only ever pass dt bounded by PHYS_SUBSTEP_S/
        PHYS_SUBSTEP_MAX (see Game._update_sim), far below the several
        seconds a rate would need to saturate at SUB_DEPTH_ACCEL_MPS2, so
        this holds in practice; it is not a general arbitrary-dt integrator.
        Snaps to target_depth (zeroing the rate) once the closing gap would
        be crossed, so there is no asymptotic tail. Not used by
        _update_surface_cycle, which has its own independent, deliberately-
        still-linear depth stepping (see there).
        """
        # Hydroplane lift scales with dynamic pressure (v^2).
        max_rate *= sub_physics.plane_authority(self.speed)
        desired_rate = (max_rate if target_depth > self.depth
                        else -max_rate if target_depth < self.depth else 0.0)
        accel = config.SUB_DEPTH_ACCEL_MPS2 * dt
        new_rate = self.depth_rate_mps + config.clamp(
            desired_rate - self.depth_rate_mps, -accel, accel)
        step = (self.depth_rate_mps + new_rate) / 2.0 * dt
        if (step >= 0.0 and self.depth + step >= target_depth) or \
           (step <= 0.0 and self.depth + step <= target_depth):
            self.depth = target_depth
            self.depth_rate_mps = 0.0
        else:
            self.depth += step
            self.depth_rate_mps = new_rate

    def update(self, dt: float, observation, world) -> None:
        """dt in Simulationssekunden; bei 1x identisch zu Echtzeit.

        The AI below reads and writes ``self.speed`` as the *ordered* speed;
        the hull follows it at its acceleration limit (surge) and everyone
        outside the update sees the actual speed."""
        self.pinged_this_tick = False
        if self.sunk:
            return
        if self.torpedo_alarm_left > 0.0:
            self.torpedo_alarm_left = max(0.0, self.torpedo_alarm_left - dt)
            if self.torpedo_alarm_left == 0.0:
                self._react_to_torpedo()
        if self.speed != self._last_actual_speed:
            # Set from outside (spawn, scenario, test): order and actual.
            self.speed_order = self.speed
        self._actual_speed = self.speed
        self._surged = False
        self.speed = self.speed_order
        try:
            self._update_inner(dt, observation, world)
        finally:
            if not self._surged:
                self.speed_order = config.clamp(
                    self.speed, 0.0, self.motion.maximum_speed_kn)
                self.speed = self._actual_speed
            if self.state in ("SINKING", "SUNK"):
                self.speed = self.speed_order = 0.0
            self._last_actual_speed = self.speed

    def _update_inner(self, dt: float, observation, world) -> None:
        start_speed = self._actual_speed
        self.transient_left = max(0.0, self.transient_left - dt)
        depth_at = getattr(world, "depth_m", lambda x, y: 1000.0)
        bottom = depth_at(self.x, self.y)
        self.last_bottom_m = bottom
        safe_depth = min(self.stype.max_depth_m, max(0.0, bottom - self._bottom_clearance_m()))
        if self.endurance is not None:
            self.endurance.manual = bool(self.manual)
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
        if 30.0 < self.damage < 100.0 and not self.emergency_ascent:
            # Holed pressure hull: progressive flooding until blown or lost.
            self.damage = min(100.0, self.damage + 0.01 * dt
                              * (self.damage - 30.0) / 70.0)
        self._update_hull_stress(dt)
        if self.state == "SINKING":
            return
        if (self.blow_available and not self.emergency_ascent and not self.manual
                and self.damage >= sub_physics.EMERGENCY_BLOW_DAMAGE
                and self.depth > 30.0):
            # Flooding: blow main ballast with the high-pressure air store.
            self.blow_available = False
            self.emergency_ascent = True
            self.transient_left = max(self.transient_left, 20.0)

        # Retain only a bounded local acoustic observation, never a live ship
        # reference. Ping memory does not continuously refresh hidden motion.
        self.memory["contact_age"] = min(config.SUB_EVADE_DURATION_S,
                                         self.memory["contact_age"] + dt)
        fresh_observation = (observation is not None and (
            observation.track_id in ("LEGACY", "MEMORY")
            or observation.last_seen > self.sensor_suite.last_consumed_s))
        if fresh_observation and observation.x is None and observation.domain == "sonar":
            self._ingest_bearing(observation)
        if fresh_observation and not (observation.x is None
                                      and self.memory["contact"] is not None
                                      and observation.domain == "sonar"):
            self.memory["contact"] = (
                dict(x=observation.x, y=observation.y,
                     speed=observation.speed_kn or 0.0,
                     course=(observation.course if observation.course is not None
                             else observation.bearing),
                     noise=observation.signal)
                if observation.x is not None and observation.y is not None else None)
            self.memory["contact_age"] = 0.0
            self.memory["contact_bearing"] = observation.bearing
            self.memory["contact_sigma_nm"] = (
                float(observation.range_uncertainty_nm or 0.0)
                if self.memory["contact"] is not None else None)
            self.memory["contact_t"] = (float(observation.last_seen)
                                        if self.memory["contact"] is not None else None)
            self.sensor_suite.last_consumed_s = max(
                self.sensor_suite.last_consumed_s, observation.last_seen)
        if self.memory["contact_age"] >= config.SUB_EVADE_DURATION_S:
            self.memory["contact"] = None
            self.memory["contact_bearing"] = None
            self.memory["contact_sigma_nm"] = None
            self.memory["contact_t"] = None
            self.memory["contact_reopen_left"] = 0
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
                bearing_uncertainty_deg=None,
                range_uncertainty_nm=self.memory["contact_sigma_nm"],
                depth_uncertainty_m=None, label=None, fix_source="TMA")
        if self.manual:
            self._active_ping_cd = max(0.0, self._active_ping_cd - dt)
            self.pinged_this_tick = self._manual_ping_pending
            self._manual_ping_pending = False
        else:
            self._maybe_attack(dt, tactical_observation)
            self.pinged_this_tick = self._maybe_active_ping(dt)

        surface_steps = 0
        if (self.endurance is not None and self.endurance.surface_operation
                and not self.manual):
            dt, surface_steps = self._update_surface_cycle(
                dt, safe_depth, SubmarineEndurance.MAX_SUBSTEPS)
            if dt <= 0.0:
                return
            old_depth = self.depth

        if self.manual:
            self._steer_to_orders(dt, safe_depth)
        elif self.state == "EVADE":
            self.evac_left -= dt
            if self.evac_left <= 0:
                # W2: In der Nähe der Fregatte -> still halten und lauschen
                if (tactical_observation is not None
                        and tactical_observation.range_nm is not None
                        and tactical_observation.range_nm < config.SUB_LUER_DIST_NM):
                    # A charted wreck within reach is the better hiding place:
                    # lie on the bottom beside it instead of hovering.
                    hide = self.wreck_hiding_spot(world)
                    self.state = "LAUER" if hide is None else "WRACK"
                    self.evac_left = self.rng.uniform(
                        *(config.SUB_LUER_DURATION_S if hide is None
                          else SUB_WRECK_HIDE_S))
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
            self._advance_depth(self.target_depth,
                                self.motion.depth_rate_m_s * 3.0, dt)
            bearing = self.memory["contact_bearing"]
            target_course = (self.course if bearing is None else
                             (bearing + 180.0 + self.evade_offset) % 360.0)
            diff = config.angle_diff_deg(target_course, self.course)
            self.course = (self.course + config.clamp(
                diff, -self.motion.turn_rate_deg_s * 2.5 * dt,
                self.motion.turn_rate_deg_s * 2.5 * dt)) % 360.0
            self.speed = max(self.speed, min(self.speed_for_state(),
                                             max(10.0, self.stype.speed_kn * .9)))
        elif self.state == "WRACK":
            self._hide_by_wreck(dt, world, safe_depth)
        elif self.state == "LAUER":
            # W2: Stillhalten unter der Thermokline (sehr leise, lauschen)
            self.evac_left -= dt
            self.target_depth = min(thermo + 15.0, safe_depth)
            self._advance_depth(self.target_depth, self.motion.depth_rate_m_s, dt)
            # Station keeping: stem the current at bare steerage way instead
            # of a fixed crawl, so the boat hovers over its ambush point.
            current = getattr(world, "current_vec", None)
            cu, cv = current(self.x, self.y) if current is not None else (0.0, 0.0)
            drift = math.hypot(cu, cv)
            if drift > 0.05:
                self.target_course = math.degrees(math.atan2(-cu, cv)) % 360.0
                diff = config.angle_diff_deg(self.target_course, self.course)
                self.course = (self.course + config.clamp(
                    diff, -self.motion.turn_rate_deg_s * dt,
                    self.motion.turn_rate_deg_s * dt)) % 360.0
            self.speed = min(2.0, drift)
            if self.evac_left <= 0:
                self.state = "PATROLLE"
                self.speed = min(6.0, self.speed_for_state())
                self.turn_left = self.rng.uniform(300.0, 900.0)
                self.turn_delta = 0.0
        else:
            # Patrouille: lange, ruhige Legs statt dauernder Kreisfahrt.
            if (self.memory["contact"] is None and len(self.tma_track.pts) >= 4
                    and self.tma_track.course_span_deg()
                    < config.TMA_MIN_COURSE_CHG_DEG):
                # Bearing-only contact without range: open a TMA leg.
                self.target_course = (self.course + SUB_TMA_LEG_TURN_DEG) % 360.0
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
            self._advance_depth(self.target_depth, self.motion.depth_rate_m_s, dt)
            # R15 consumed this patrol snorkel-trigger draw. Preserve the shared
            # world stream while endurance now decides when air is required.
            if self.stype.profile.requires_air and self.depth > 55.0:
                self.rng.random()

        if self.emergency_ascent:
            self.depth = max(10.0, old_depth - sub_physics.EMERGENCY_BLOW_RATE_MPS * dt)
            self.target_depth = self.depth
            self.depth_rate_mps = -sub_physics.EMERGENCY_BLOW_RATE_MPS
            if self.depth <= 10.0 + 1e-9:
                self.emergency_ascent = False
                self.depth_rate_mps = 0.0
        # Surge: the ordered speed is reached at the hull's acceleration
        # limit (propeller thrust against drag and mass), faster when slowing.
        ordered = config.clamp(self.speed, 0.0, self.motion.maximum_speed_kn)
        accel = self.motion.acceleration_kn_s * dt
        self.speed = start_speed + config.clamp(ordered - start_speed,
                                                -2.0 * accel, accel)
        self.speed_order = ordered
        self._surged = True
        motion_dt = dt
        if self.endurance is not None:
            motion_dt = self.endurance.time_until_surface_operation(
                dt, self.speed, self.motion.maximum_speed_kn, self.depth)
            self.speed = self.endurance.supported_speed(
                motion_dt, self.speed, self.motion.maximum_speed_kn, self.depth)
        v = config.kn_to_nm_per_s(self.speed) * motion_dt
        nx = self.x + v * math.sin(math.radians(self.course))
        ny = self.y - v * math.cos(math.radians(self.course))
        # W2: Meeresstroemung - reiner Driftzusatz, kein Antrieb/keine Steuerung.
        current = getattr(world, "current_vec", None)
        if current is not None and not self.bottomed:
            cu, cv = current(self.x, self.y)
            nx += config.kn_to_nm_per_s(cu) * motion_dt
            ny -= config.kn_to_nm_per_s(cv) * motion_dt
        if (world.on_land(nx, ny) or underwater_path_blocked(
                world, self.x, self.y, old_depth + self._bottom_clearance_m() - 1e-6,
                nx, ny, self.depth + self._bottom_clearance_m() - 1e-6)):
            if self.manual:
                # A crewed boat stops short of the obstacle instead of
                # veering: the crew must choose a new course.
                self.speed = self.order_speed = 0.0
                if self.crew is not None:
                    self.crew.event("obstacle")
            else:
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
        elif self.state in QUIET_STATES:
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
        if self.state in QUIET_STATES:
            q = max(0.97, q + 0.08)
        if self.manual and self.crew is not None and self.crew.quiet_active(self):
            # Crew silent running or lying on the bottom: the lurker's quiet.
            q = max(0.97, q + 0.08)
        if self.transmitting:
            q += config.SNOCKEL_TRANSMIT_NOISE  # M13: Senden macht lauter
        if self.snorkeling:
            q -= config.UBOOT_SNORKEL_QUIET_LOSS    # diesels running at snorkel depth
        return config.clamp(q, 0.0, 1.0)

    def noise_level(self) -> float:
        return 1.0 - self.quiet_factor()

    def torpedo_notice_range_nm(self) -> float:
        """Graduated passive notice of a running torpedo's own machinery
        noise: short of the launch-transient alert (SUB_TORPEDO_ALERT_NM) and
        beyond pure terminal homing range (TORP_HOME_RANGE_NM), scaled by the
        sub's own noise the same way Ship.passive_sonar_range_nm penalises
        self-noise - a sub running loud hears less of its surroundings."""
        own_penalty = 1.0 - 0.8 * self.noise_level()
        return config.TORP_RUNNING_NOISE_RANGE_NM * own_penalty

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

    @property
    def bottomed(self) -> bool:
        """Lying still on the seabed (wreck hide): no way ordered, no drift.
        Derived from saved state, so it survives save/load (a crew's
        bottoming is transient like the crew binding)."""
        return ((self.state == "WRACK" and self.speed_order <= 0.0)
                or (self.manual and self.crew is not None and self.crew.bottomed
                    and self.speed <= 0.05))

    def wreck_hiding_spot(self, world):
        """Nearest charted wreck within reach whose bottom this boat can lie
        on, and the berth beside it (charts are public to every navy)."""
        hazards = getattr(world, "charted_hazards", None)
        depth_at = getattr(world, "depth_m", None)
        if hazards is None or depth_at is None:
            return None
        best = None
        for index, hazard in enumerate(hazards()):
            if hazard.kind != "wreck":
                continue
            distance = math.hypot(hazard.x_nm - self.x, hazard.y_nm - self.y)
            if distance > SUB_WRECK_HIDE_RANGE_NM:
                continue
            side = detrand.phase(self.sensor_seed, "wreck-berth", index)
            offset = hazard.radius_nm + SUB_WRECK_STANDOFF_NM
            bx = hazard.x_nm + offset * math.sin(side)
            by = hazard.y_nm - offset * math.cos(side)
            bottom = depth_at(bx, by)
            # Lie well above test depth so the hull does not fatigue.
            if not (SUB_WRECK_MIN_BOTTOM_M <= bottom - SUB_BOTTOM_CLEARANCE_M
                    <= SUB_WRECK_MAX_DEPTH_FRACTION * self.stype.max_depth_m):
                continue
            if best is None or (distance, index) < best[0]:
                best = ((distance, index), hazard, bx, by, bottom)
        return None if best is None else best[1:]

    def _hide_by_wreck(self, dt: float, world, safe_depth: float) -> None:
        """Transit quietly to the berth beside the wreck, then settle on the
        bottom and lie still until the hide time is up."""
        self.evac_left -= dt
        spot = self.wreck_hiding_spot(world)
        if spot is None or self.evac_left <= 0.0:
            self.state = "PATROLLE"
            self.speed = min(6.0, self.speed_for_state())
            self.turn_left = self.rng.uniform(300.0, 900.0)
            self.turn_delta = 0.0
            return
        _hazard, bx, by, bottom = spot
        distance = math.hypot(bx - self.x, by - self.y)
        if distance > SUB_WRECK_ARRIVED_NM and not self.bottomed:
            self.target_course = math.degrees(math.atan2(
                bx - self.x, -(by - self.y))) % 360.0
            diff = config.angle_diff_deg(self.target_course, self.course)
            self.course = (self.course + config.clamp(
                diff, -self.motion.turn_rate_deg_s * dt,
                self.motion.turn_rate_deg_s * dt)) % 360.0
            # Slow down on the final approach so the boat stops on its berth.
            self.speed = min(SUB_WRECK_TRANSIT_KN, self.speed_for_state(),
                             max(0.5, distance * 3600.0 / 60.0))
            # Transit with the usual bottom clearance over the berth, too,
            # so the approach is not blocked by the rising seabed.
            self.target_depth = max(0.0, min(safe_depth, bottom - 30.0))
        else:
            self.speed = 0.0
            self.target_depth = max(0.0, bottom - SUB_BOTTOM_CLEARANCE_M)
        self._advance_depth(self.target_depth, self.motion.depth_rate_m_s, dt)

    # --- crew control (a player crew commands this boat) -------------------

    def claim_manual(self) -> None:
        """Hand the boat to a crew: the AI stops deciding from now on."""
        self.manual = True
        if self.state in ("EVADE", "LAUER", "WRACK"):
            self.state = "PATROLLE"
        self.evac_left = 0.0
        self.torpedo_alarm_left = -1.0
        self.torpedo_alerted = False
        self.order_course = self.course
        self.order_speed = self.speed_order
        self.order_depth = self.target_depth
        self._manual_ping_pending = False
        if self.endurance is not None:
            # The crew runs the plant: an automatic ascent/radio call ends.
            self.endurance.manual = True
            if self.endurance.phase in ("ASCENDING", "RADIO", "DESCENDING"):
                self.endurance.phase = "SUBMERGED"

    def release_manual(self) -> None:
        """Return the boat to the AI, which resumes from its current state."""
        self.manual = False
        self.crew = None
        if self.endurance is not None:
            self.endurance.manual = False
        self._manual_ping_pending = False
        self.target_course = self.course
        self.turn_left = min(self.turn_left, 60.0)

    def _bottom_clearance_m(self) -> float:
        """25 m above the bottom; a crew that lies the boat down goes closer."""
        if self.manual and self.crew is not None and self.crew.bottomed:
            return config.UBOOT_BOTTOM_CLEARANCE_M
        return 25.0

    def safe_depth_m(self, world) -> float:
        """Deepest ordered depth: test depth, and 25 m clear of the bottom."""
        bottom = getattr(world, "depth_m", lambda x, y: 1000.0)(self.x, self.y)
        return min(self.stype.max_depth_m, max(0.0, bottom - self._bottom_clearance_m()))

    def set_orders(self, *, course=None, speed=None, depth=None):
        """Crew orders; each value is checked before any is applied."""
        values = [value for value in (course, speed, depth) if value is not None]
        if any(type(value) not in (int, float) or isinstance(value, bool)
               or not math.isfinite(value) for value in values):
            return "invalid_value"
        if course is not None and not 0.0 <= course < 360.0:
            return "invalid_value"
        if speed is not None and not 0.0 <= speed <= self.motion.maximum_speed_kn:
            return "invalid_value"
        if depth is not None and not 0.0 <= depth <= self.stype.max_depth_m:
            return "invalid_value"
        if not self.manual or self.sunk or self.state == "SINKING":
            return "not_ready"
        if self.crew is not None and self.crew.bottomed and (
                (speed is not None and speed > 0.0) or depth is not None):
            self.crew.bottomed = False          # any way or depth order lifts off
        if course is not None:
            self.order_course = float(course)
        if speed is not None:
            self.order_speed = float(speed)
        if depth is not None:
            self.order_depth = float(depth)
        return True

    def _steer_to_orders(self, dt: float, safe_depth: float) -> None:
        """Follow the crew's orders within the boat's handling limits."""
        self.target_course = self.order_course % 360.0
        diff = config.angle_diff_deg(self.target_course, self.course)
        self.course = (self.course + config.clamp(
            diff, -self.motion.turn_rate_deg_s * dt,
            self.motion.turn_rate_deg_s * dt)) % 360.0
        crew = self.crew
        ceiling = self.speed_for_state()
        order_depth = self.order_depth
        if crew is not None:
            if crew.bottomed:
                order_depth, ceiling = safe_depth, 0.0
            if crew.silent:
                ceiling = min(ceiling, config.UBOOT_SILENT_MAX_KN)
            if self.snorkeling:
                ceiling = min(ceiling, config.UBOOT_SNORKEL_MAX_KN)
        self.target_depth = config.clamp(order_depth, 0.0, safe_depth)
        self._advance_depth(self.target_depth, self.motion.depth_rate_m_s, dt)
        self.speed = config.clamp(self.order_speed, 0.0, ceiling)
        if crew is not None and crew.mast and self.depth > MAST_DEPTH_M + 1.0:
            crew.mast = False                   # masts come down when diving
            crew.event("mast_lowered")
        if self.snorkeling and self.depth > self.endurance.profile.snorkel_depth_m + 1.0:
            # Dived below snorkel depth: the head valve shuts, diesels stop.
            self.endurance.stop_snorkel()
            if crew is not None:
                crew.event("snorkel_stopped")

    def fire_readiness(self, bearing=None, salvo: int = 1):
        """Why a crew torpedo shot is impossible now, or None when ready."""
        if not self.manual or self.sunk or self.state in ("SINKING", "SUNK"):
            return "not_ready"
        if self.torpedoes_left <= 0:
            return "no_torpedoes"
        if self.torpedoes_left < salvo:
            return "no_torpedoes"
        if self.weapon_battery is not None and self.weapon_battery.ready_count < salvo:
            return "reloading"
        if len(self.pending_torpedoes) + salvo > SUB_MAX_PENDING_TORPEDOES:
            return "reloading"
        if bearing is not None and self.weapon_battery is not None:
            launcher = self.runtime_catalog.launchers[self.weapon_battery.launcher_key]
            arc_center = (self.course + launcher.arc_center_deg) % 360.0
            if abs(config.angle_diff_deg(bearing, arc_center)) \
                    > launcher.arc_width_deg / 2.0:
                return "out_of_arc"
        return None

    def command_fire(self, bearing, range_nm=None, target_course=None,
                     target_speed_kn=None, now: float = 0.0, *, depth_m=None,
                     salvo: int = 1):
        """Fire one torpedo down a crew-chosen bearing.

        ``range_nm`` places the guidance datum; with a crew solution
        (``target_course``/``target_speed_kn``) the shot is led as the AI's
        interception course.  All values are crew estimates, never truth.
        """
        numbers = [value for value in (bearing, range_nm, target_course,
                                       target_speed_kn, depth_m) if value is not None]
        if type(salvo) is not int or salvo not in (1, 2):
            return "invalid_value"
        if bearing is None or any(
                type(value) not in (int, float) or isinstance(value, bool)
                or not math.isfinite(value) for value in numbers):
            return "invalid_value"
        if (not 0.0 <= bearing < 360.0
                or (range_nm is not None and not 0.05 <= range_nm <= 40.0)
                or (target_course is not None and not 0.0 <= target_course < 360.0)
                or (target_speed_kn is not None and not 0.0 <= target_speed_kn <= 60.0)
                or ((target_course is None) != (target_speed_kn is None))
                or (target_course is not None and range_nm is None)
                or (depth_m is not None and not config.UBOOT_TORPEDO_MIN_DEPTH_M
                    <= depth_m <= config.UBOOT_TORPEDO_MAX_DEPTH_M)):
            return "invalid_value"
        reason = self.fire_readiness(bearing, salvo)
        if reason is not None:
            return reason
        x = y = None
        if range_nm is not None:
            x = self.x + range_nm * math.sin(math.radians(bearing))
            y = self.y - range_nm * math.cos(math.radians(bearing))
        observation = PlatformObservation(
            track_id="CREW", domain="sonar", source="SONAR",
            observer_x=self.x, observer_y=self.y, bearing=float(bearing),
            range_nm=range_nm, x=x, y=y, course=target_course,
            speed_kn=target_speed_kn, depth_m=None, quality=1.0, signal=0.0,
            last_seen=now, bearing_uncertainty_deg=None,
            range_uncertainty_nm=None, depth_uncertainty_m=None, label=None)
        launched = self._fire_salvo(observation, salvo)
        if not launched:
            return "not_ready"
        # Crew presets on the rows just loaded: run depth, and a two-torpedo
        # spread either side of the fire-control course.
        first = len(self.pending_torpedoes) - launched
        for index in range(first, len(self.pending_torpedoes)):
            row = list(self.pending_torpedoes[index])
            if depth_m is not None:
                row[3] = float(depth_m)
            if launched == 2:
                # Each torpedo gets its own datum, turned about the boat by
                # the same angle, so the wire keeps the spread open.
                offset = config.UBOOT_SALVO_SPREAD_DEG * (-1 if index == first else 1)
                row[2] = (row[2] + offset) % 360.0
                if row[4] is not None and row[5] is not None:
                    angle = math.radians(offset)
                    dx, dy = row[4] - self.x, row[5] - self.y
                    row[4] = self.x + dx * math.cos(angle) - dy * math.sin(angle)
                    row[5] = self.y + dx * math.sin(angle) + dy * math.cos(angle)
            self.pending_torpedoes[index] = tuple(row)
        return True

    def command_decoy(self):
        if not self.manual or self.sunk or self.state in ("SINKING", "SUNK"):
            return "not_ready"
        if (self.countermeasure_store is None or self._decoy_cd > 0.0
                or self.pending_decoys):
            return "not_ready"
        if not self.countermeasure_store.fire():
            return "no_decoys"
        self.pending_decoys.append((self.x, self.y))
        self._decoy_cd = self.decoy_profile.cooldown_s
        return True

    def command_ping(self):
        """Transmit once: every ship in reach hears it on the next update."""
        if not self.manual or self.sunk or self.state in ("SINKING", "SUNK"):
            return "not_ready"
        self._manual_ping_pending = True
        return True

    def command_blow(self):
        """Blow main ballast with the one high-pressure air charge."""
        if not self.manual or self.sunk or self.state in ("SINKING", "SUNK"):
            return "not_ready"
        if not self.blow_available or self.emergency_ascent or self.depth <= 30.0:
            return "not_ready"
        self.blow_available = False
        self.emergency_ascent = True
        self.transient_left = max(self.transient_left, 20.0)
        return True

    @property
    def snorkeling(self) -> bool:
        return self.endurance is not None and self.endurance.phase == "SNORKEL"

    def _crew_ready(self) -> bool:
        return (self.manual and self.crew is not None and not self.sunk
                and self.state not in ("SINKING", "SUNK"))

    def command_snorkel(self, on):
        """Crew: raise the snorkel and run the diesels (or stop them)."""
        if type(on) is not bool:
            return "invalid_value"
        if not self._crew_ready():
            return "not_ready"
        if self.endurance is None:
            return "uboot_no_snorkel"           # nuclear boat: no diesels
        if not on:
            self.endurance.stop_snorkel()
            return True
        if self.depth > self.endurance.profile.snorkel_depth_m + 1.0:
            return "uboot_too_deep"
        self.crew.bottomed = False
        self.order_depth = self.endurance.profile.snorkel_depth_m
        self.endurance.start_snorkel(self.depth)
        return True

    def command_mast(self, on):
        """Crew: raise the ESM/radar-warning mast (periscope depth only)."""
        if type(on) is not bool:
            return "invalid_value"
        if not self._crew_ready():
            return "not_ready"
        if on and self.depth > MAST_DEPTH_M:
            return "uboot_mast_depth"
        self.crew.mast = on
        return True

    def command_silent(self, on):
        """Crew: silent running (speed ceiling, the lurker's quiet)."""
        if type(on) is not bool:
            return "invalid_value"
        if not self._crew_ready():
            return "not_ready"
        self.crew.silent = on
        return True

    def command_bottom(self, on):
        """Crew: lie the boat on the bottom (all stop, 3 m keel clearance)."""
        if type(on) is not bool:
            return "invalid_value"
        if not self._crew_ready():
            return "not_ready"
        if not on:
            self.crew.bottomed = False
            self.order_depth = self.depth
            return True
        if self.last_bottom_m is None or self.last_bottom_m > self.stype.max_depth_m:
            return "uboot_too_deep"
        if self.snorkeling:
            self.endurance.stop_snorkel()
        self.crew.bottomed = True
        self.order_speed = 0.0
        return True

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
            if self.snorkeling:
                result.extend(config.UBOOT_SNORKEL_LINES)   # diesel firing lines
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
            if self.state in QUIET_STATES:
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
        if self.snorkeling:
            lines.extend(config.UBOOT_SNORKEL_LINES)     # diesel firing lines
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
            if self.state in QUIET_STATES:
                level *= 0.5
            if self.snorkeling:
                level += config.UBOOT_SNORKEL_QUIET_LOSS
            return {"level": min(1.0, level + 0.10 * self.damage / 100.0),
                    "low_hz": broadband[1], "high_hz": broadband[2]}
        if self.sunk or sig.broadband is None:
            return {}
        v = max(0.0, self.speed)
        vmax = max(1.0, self.stype.speed_kn)
        level = self.fingerprint.bb_level * (0.15 + 0.85 * min(1.0, v / vmax))
        if self.state == "EVADE":
            level *= 1.6
        if self.state in QUIET_STATES:
            level *= 0.5
        level = min(1.0, level + 0.10 * (self.damage / 100.0))
        return {"level": min(1.0, level),
                "low_hz": sig.broadband[1],
                "high_hz": sig.broadband[2]}
