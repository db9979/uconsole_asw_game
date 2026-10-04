"""U-Boot-Modell: Typen-Daten aus dem Kontakt-Katalog + Patrouillen/Ausweich-KI (M2).

Pro Instanz: sensor_seed + Fingerprint (Blattzahl, Raten-Skala, Tonal-Offsets,
Kavitation/Breitband-Level) – Details in docs/contacts-db.md.
"""

import math
import random

from src.core.baffles import in_baffles
from src.core import config
from src.physics import submarine as sub_physics
from src.core import commander_traits, detrand
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
from src.enemies.ballast import BoatBallast
from src.enemies.damage_control import BoatDamageControl
from src.enemies.endurance import SubmarineEndurance
from src.physics.geo import FrigateRelativeMixin

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


class Sub(FrigateRelativeMixin):
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
        # Tanks, trim and air bottles; only a crewed boat feels them (the
        # AI keeps itself trimmed and keeps its one legacy blow).
        self.ballast = BoatBallast()
        # Compartments, leaks, fire, gas and the two damage-control teams;
        # likewise only a crewed boat's (the AI keeps one damage value).
        self.damage_control = BoatDamageControl()
        # Empty posts in the torpedo room (``game_casualties``; derived).
        self.weapons_crew_factor = 1.0
        # Own passive TMA on one bearing-only contact and crew reaction.
        self.tma_track = BearingTrack()
        self.tma_track_id = None
        self.tma_next_t = 0.0
        self.torpedo_alarm_left = -1.0
        self.emergency_ascent = False
        self.transient_left = 0.0
        # Tube flooding / outer door: a short transient the frigate's sonar
        # may hear (``flood_seq`` numbers each one, quiet = slow flooding).
        self.flood_noise_left = 0.0
        self.flood_quiet = False
        # Noise of the crew's mishaps and voices (game_noise, recomputed each substep).
        self.crew_noise = 0.0
        self.flood_seq = 0
        # The AI's tubes: -1 dry, > 0 seconds of flooding left, 0 flooded;
        # a shot ordered on dry tubes waits for the flooding (fire pending).
        self.ai_tube_left = -1.0
        self.ai_fire_pending = False
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
        # A boat mission's leg (course, speed, depth) set every substep by
        # src/core/boat_ai.py for the AI's mission boat; never saved.
        self.mission_orders = None
        # The patrol leg (course, speed, depth) of the boat's plan, set every
        # substep by src/core/boat_ai.py from its own picture
        # (src/core/opfor_plans.py) or the experimental opponent's saved
        # plan (src/llm/opponent.py); never saved.
        self.plan_orders = None
        # Scenarios 8 to 10 (src/core/boat_missions.GUARDED_MODES): the boat
        # slips past a guard and answers a close ping; never saved either.
        self.mission_guarded = False
        # Scenarios 8 and 9 (boat_missions.SNAP_MODES): a snap shot down the
        # bearing of a loud frigate; never saved either.
        self.mission_snap = False
        # Scenario 13 (trail) is peacetime: the boat never fires; never saved.
        self.mission_peace = False
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
        # Seconds the AI stays deep after its ESM heard an own aircraft's
        # search radar with the mast or snorkel up (save v32 ``radar_hold_s``).
        self.radar_hold_s = 0.0
        self.pinged_this_tick = False
        self.countermeasure_store = ConsumableStore.from_catalog(
            runtime_catalog, source.key, "acoustic_decoy")
        # Taktisches Gedaechtnis: nur Ereignisse, die das Boot wahrnimmt.
        self.memory = self.fresh_memory()
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

    @staticmethod
    def fresh_memory() -> dict:
        """The tactical memory of a boat that has heard nothing yet."""
        return {
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

    def forget(self) -> None:
        """A boat brought back as a new encounter starts with a clean slate:
        no contact, solution, alarm or shots of its former patrol. It also
        takes a new identity, so nothing the other side still holds on the
        old one (contact, track, TMA, OPZ label) attaches to it."""
        self.id = Sub._next_id
        Sub._next_id += 1
        self.memory = self.fresh_memory()
        self.tma_track = BearingTrack()
        self.tma_track_id = None
        self.pending_torpedoes.clear()
        self.pending_decoys.clear()
        self.torpedo_alerted = False
        self.heard_ping = False
        self.state = "PATROLLE"
        self.decision_reason = "Patrouille"

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
        return bearing

    def ping_level_db(self, source, kind: str) -> float:
        """Received level of an intercepted ping (spreading and absorption)."""
        range_m = max(50.0, math.hypot(source[0] - self.x, source[1] - self.y) * 1852.0)
        return (config.UBOOT_PING_SOURCE_DB[kind] - 20.0 * math.log10(range_m)
                - 0.0002 * range_m)

    def hear_ping(self, source=None, kind: str = "hull") -> None:
        """U-Boot hört einen aktiven Ping -> Ausweichen.

        ``kind`` is the pinging sensor (hull or towed array, dipping sonar,
        active buoy); only a crewed boat's intercept picture uses it."""
        if self.manual:
            # A crewed boat only notes the intercept; the crew decides.
            if not self.sunk and self.state != "SINKING":
                self.heard_ping = True
                previous = self.memory["last_ping_age"]
                self.memory["last_ping_age"] = 0.0
                bearing = self._crew_alarm(source, "ping", config.PING_INTERCEPT_SIGMA_DEG,
                                           previous if kind == "hull" else 0.0)
                if bearing is not None:
                    self.crew.intercept(kind, bearing, self.ping_level_db(source, kind))
                    if kind != "hull" and previous >= 20.0:
                        self.crew.event(f"ping_{kind}_heard", bearing=f"{bearing:03.0f}")
            return
        if (self.mission_guarded and source is not None
                and math.hypot(source[0] - self.x, source[1] - self.y)
                > config.BOAT_AI_PING_IGNORE_NM):
            # A mission boat keeps to its orders under a faint, distant ping:
            # that sonar cannot hold it at this range.
            return
        if not self.sunk and self.state != "SINKING":
            self.state = "EVADE"
            # A daring commander gives way briefly, a cautious one long.
            self.evac_left = config.SUB_EVADE_DURATION_S * commander_traits.sub_factor(
                self, "evade")
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
            bearing = self._crew_alarm(source, "torpedo", 5.0, previous)
            if bearing is not None:
                self.crew.intercept("torpedo", bearing, None)
            return
        if self.state == "EVADE" or self.torpedo_alarm_left == 0.0:
            # Already evading, or the recognition time has elapsed.
            self._react_to_torpedo()
            return
        if self.torpedo_alarm_left < 0.0:
            self.torpedo_alarm_left = self.reaction_delay_s()

    def _baffle_trail(self, observation):
        """The hunter's course when this boat sits in its baffles close
        astern (and no torpedo is after it), else None: a boat there is
        deaf to the hull sonar, so it trails instead of running."""
        if (observation is None or observation.course is None
                or observation.range_nm is None or observation.x is None
                or observation.range_nm > config.SUB_BAFFLE_TRAIL_NM
                or self.memory["last_torpedo_age"] <= config.SUB_EVADE_DURATION_S):
            return None
        from_hunter = math.degrees(math.atan2(self.x - observation.x,
                                              -(self.y - observation.y))) % 360.0
        if not in_baffles(observation.course, from_hunter):
            return None
        return float(observation.course) % 360.0

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
        if self.manual and self.crew is not None:
            self.crew.event("hull_hit")
        self._compartment_hit(amount)
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
        if (self.side != "hostile" or self.sunk or self.state == "SINKING"
                or self.mission_peace):
            return
        self.attack_left -= dt
        if (observation is not None and self.ai_tube_left < 0.0
                and self.torpedoes_left > 0
                and observation.range_nm is not None
                and observation.range_nm <= config.SUB_AI_PREFLOOD_NM
                and (self.weapon_battery is None
                     or self.weapon_battery.ready_count > 0)):
            # A stalking boat floods its tubes early and slowly (quiet).
            self.ai_flood_tubes(quiet=True)
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
        # A mission boat, pinged from close by, answers down the bearing for
        # longer: it only hears pings inside BOAT_AI_PING_IGNORE_NM.
        window = config.BOAT_AI_COUNTERFIRE_S if self.mission_guarded else 2.0
        bearing_counterfire = (dist is None and self.heard_ping
                               and self.memory["last_ping_age"] <= window)
        if (self.state == "EVADE" and self.heard_ping
                and (close_fix or bearing_counterfire)):
            rate = 0.006 * (0.5 + noise) * self.stype.aggression
        elif noise >= 0.75 and dist is not None and dist < 18.0:
            rate = 0.002 * self.stype.aggression
        elif noise >= 0.75 and dist is None and self.mission_snap:
            # Scenarios 8 and 9: a loud frigate closing on its bearing gets a
            # snap shot down that bearing; the seeker finds it.
            rate = 0.002 * self.stype.aggression
        elif dist is not None and dist < config.SUB_SOLUTION_ATTACK_NM:
            # A located frigate in torpedo range is attacked even when quiet.
            rate = config.SUB_SOLUTION_ATTACK_RATE * self.stype.aggression
        rate *= self.attack_mult * commander_traits.sub_factor(self, "attack")
        if self.mission_orders is not None:
            # A mission boat fights its way through: the frigate is its threat.
            rate *= (config.BOAT_AI_GUARDED_ATTACK_MULT if self.mission_guarded
                     else config.BOAT_AI_ATTACK_MULT)
        if rate <= 0:
            self.ai_fire_pending = False
            return
        if self.ai_fire_pending:
            if self.ai_tube_left != 0.0:
                return
            # The tubes flooded for the shot ordered earlier: fire now.
            self.ai_fire_pending = False
        elif self.asw_rng.random() < rate * dt:
            if self.ai_tube_left != 0.0:
                # Dry tubes: a hurried, loud flooding before the shot.
                if self.ai_tube_left < 0.0:
                    self.ai_flood_tubes(quiet=False)
                self.ai_fire_pending = True
                return
        else:
            return
        n = min(2 if dist is not None and dist < 12.0
                and self.stype.aggression > .8 else 1,
                self.torpedoes_left,
                SUB_MAX_PENDING_TORPEDOES - len(self.pending_torpedoes))
        if self._fire_salvo(observation, n):
            self.attack_left = self.attack_cooldown

    def flood_transient(self, quiet: bool) -> None:
        """Tube flooding and the outer door: a brief transient. Loud flooding
        also raises the radiated level; quiet (slow) flooding is heard only close."""
        self.flood_seq = (self.flood_seq + 1) % config.SUB_FLOOD_SEQ_MAX
        self.flood_quiet = bool(quiet)
        self.flood_noise_left = config.UBOOT_TUBE_FLOOD_NOISE_S
        if not quiet:
            self.transient_left = max(self.transient_left,
                                      config.UBOOT_TUBE_FLOOD_NOISE_S)

    def ai_flood_tubes(self, quiet: bool) -> None:
        """Start flooding the AI's dry tubes (slow and quiet, or fast and loud)."""
        if self.manual or self.ai_tube_left >= 0.0:
            return
        self.ai_tube_left = (config.UBOOT_TUBE_FLOOD_QUIET_S if quiet
                             else config.UBOOT_TUBE_FLOOD_S)
        self.flood_transient(quiet)

    def _fire_salvo(self, observation: PlatformObservation, count: int) -> int:
        """Load up to ``count`` torpedoes on ``observation``; returns fired."""
        launched = 0
        for _ in range(count):
            profile = self.enemy_torpedo_profile
            fired_key = None
            if self.weapon_battery is not None:
                tubes = self.crew_tubes
                # A crew fires only flooded tubes and loads each one itself.
                fired_key = self.weapon_battery.fire(
                    tubes=None if tubes is None else {
                        index for index, row in enumerate(tubes) if row[0] == "flooded"},
                    auto_reload=tubes is None)
                if fired_key is None:
                    break
                if tubes is not None:
                    tubes[self.weapon_battery.last_fired_tube] = ["dry", 0.0]
                runtime_key = self.runtime_catalog.weapons[
                    fired_key].runtime_profile_key
                if runtime_key is None:
                    break
                profile = self.runtime_catalog.torpedoes[runtime_key]
            self.pending_torpedoes.append(
                (*self._launch_data(observation, profile), profile.key,
                 self.id, fired_key))
            launched += 1
            if self.manual and self.crew is not None:
                # The torpedo room reports each shot (with its tube).
                if self.weapon_battery is not None:
                    self.crew.event("torpedo_fired",
                                    tube=f"{self.weapon_battery.last_fired_tube + 1}")
                else:
                    self.crew.event("torpedo_fired_tubeless")
        if launched:
            if not self.manual:
                self.ai_tube_left = -1.0      # fired: the tubes are dry again
                self.ai_fire_pending = False
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
        """Only the explicit radio phase (or a crew's situation report on
        the air) is detectable by HFDF."""
        crew_radio = getattr(self.crew, "radio", None) if self.crew is not None else None
        if crew_radio is not None and crew_radio.transmitting:
            return True
        return self.endurance is not None and self.endurance.transmitting

    def contact_report_on_air(self, seed: int, now: float) -> bool:
        """An AI boat at periscope depth holding the frigate reports it to
        headquarters: one 20 s HF call at a stateless time in each window."""
        if (self.manual or self.sunk or self.state == "SINKING"
                or self.depth > MAST_DEPTH_M
                or self.memory["contact"] is None):
            return False
        window = math.floor(now / config.SUB_REPORT_PERIOD_S)
        start = window * config.SUB_REPORT_PERIOD_S + detrand.u01(
            seed, "sub-contact-report", int(self.sensor_seed), window) * (
                config.SUB_REPORT_PERIOD_S - config.SUB_REPORT_TX_S)
        return start <= now < start + config.SUB_REPORT_TX_S

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
        """Pressure-hull fatigue below test depth; collapse beyond crush depth.

        A crewed boat may go below test depth: there hull failures come much
        faster (``overdepth_rate_per_s``) and grow worse with the depth."""
        test = self.stype.max_depth_m
        if self.depth >= sub_physics.crush_depth_m(test):
            self.damage = 100.0
            if self.crew is not None and self.state != "SINKING":
                self.crew.event("hull_collapse")
        rate = sub_physics.fatigue_rate_per_s(self.depth, test)
        crewed = self.manual and self.crew is not None
        if crewed:
            rate += sub_physics.overdepth_rate_per_s(self.depth, test)
        self.hull_fatigue += rate * dt
        if self.hull_fatigue >= 1.0:
            self.hull_fatigue -= 1.0
            if crewed:
                self._hull_failure(self.depth / max(test, 1.0))
            else:
                self.damage = min(100.0, self.damage + 20.0)
                self._compartment_hit(config.UBOOT_DC_FATIGUE_LEAK
                                      / config.UBOOT_DC_LEAK_PER_PCT)
        if self.damage >= 100.0 and self.state != "SINKING":
            self.state = "SINKING"
            self.sink_left = 20.0

    def _mission_pressing_on(self) -> bool:
        """A mission boat that heard no torpedo lately holds to its mission."""
        return (self.mission_orders is not None
                and self.memory["last_torpedo_age"] > config.SUB_EVADE_DURATION_S)

    def evade_depth(self, thermo: float, safe_depth: float) -> float:
        """Below the layer, away from a ping; the reconnaissance boat within
        sighting range still comes up for its periscope look, since a ping
        alone does not keep it down (a torpedo in the water does)."""
        if self._mission_pressing_on() and self.mission_orders[2] <= MAST_DEPTH_M:
            return self.mission_orders[2]
        return min(thermo + 40.0, safe_depth)

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
            # Diesels (or only the fans) running at snorkel depth.
            level += config.UBOOT_CHARGE_NOISE_DB[self.snorkel_rate]
        if self.pumping:
            level += config.UBOOT_PUMP_NOISE_DB
        return level

    @property
    def pumping(self) -> bool:
        """A crewed boat's trim or bilge pumps are running."""
        return bool(self.manual and (self.ballast.pumping or self.damage_control.pumping))

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
        old_depth = self.depth
        try:
            self._update_inner(dt, observation, world)
        finally:
            if self.manual and self.crew is not None:
                self._report_test_depth(old_depth)
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
        self.flood_noise_left = max(0.0, self.flood_noise_left - dt)
        if not self.manual and self.ai_tube_left > 0.0:
            left = self.ai_tube_left - dt * self.crew_efficiency()
            self.ai_tube_left = 0.0 if left <= 1e-9 else left
        depth_at = getattr(world, "depth_m", lambda x, y: 1000.0)
        bottom = depth_at(self.x, self.y)
        self.last_bottom_m = bottom
        safe_depth = min(self.stype.max_depth_m, max(0.0, bottom - self._bottom_clearance_m()))
        self.radar_hold_s = max(0.0, self.radar_hold_s - dt)
        if self.endurance is not None:
            self.endurance.manual = bool(self.manual)
            self.endurance.hold_ascent = self.radar_hold_s > 0.0 and not self.manual
        self.target_depth = config.clamp(self.target_depth, 0.0, safe_depth)
        old_depth = self.depth
        for key in ("last_ping_age", "last_torpedo_age"):
            if self.memory[key] != float("inf"):
                self.memory[key] += dt
        thermo = world.thermocline_depth_m(self.x, self.y)
        world_size = world.size_nm
        self._decoy_cd = max(0.0, self._decoy_cd - dt)
        if self.endurance is not None:
            self._update_air(dt)
        if self.weapon_battery is not None:
            # Foul air slows the torpedo gang's reloading and flooding.
            tubes = self.crew_tubes
            loading = [tube.loading_weapon_key is not None
                       for tube in self.weapon_battery.tubes]
            self.weapon_battery.update(dt * self.crew_efficiency(),
                                       auto_reload=tubes is None)
            self.torpedoes_left = self.weapon_battery.remaining_total
            if tubes is not None:
                self._update_tubes(dt * self.crew_efficiency(), tubes, loading)
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
        if 30.0 < self.damage < 100.0 and not self.emergency_ascent and not self.manual:
            # Holed pressure hull: progressive flooding until blown or lost
            # (a crewed boat floods compartment by compartment instead).
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
            # A crew may take the boat below test depth, down to crush depth.
            self._steer_to_orders(dt, safe_depth, min(
                self.crush_depth_m, max(0.0, bottom - self._bottom_clearance_m())))
        elif self.state == "EVADE":
            self.evac_left -= dt
            if self.evac_left <= 0:
                # W2: In der Nähe der Fregatte -> still halten und lauschen
                if (tactical_observation is not None
                        and not self._mission_pressing_on()
                        and tactical_observation.range_nm is not None
                        and tactical_observation.range_nm < config.SUB_LUER_DIST_NM
                        * commander_traits.sub_factor(self, "lurk")):
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
            self.target_depth = self.evade_depth(thermo, safe_depth)
            self._advance_depth(self.target_depth,
                                self.motion.depth_rate_m_s * 3.0, dt)
            bearing = self.memory["contact_bearing"]
            target_course = (self.course if bearing is None else
                             (bearing + 180.0 + self.evade_offset) % 360.0)
            if self._mission_pressing_on():
                # A ping alone does not turn a mission boat back: it keeps
                # its leg, deep and slow, and gives way only to a torpedo.
                target_course = self.mission_orders[0]
            trail = self._baffle_trail(tactical_observation)
            if trail is not None:
                target_course = trail
            diff = config.angle_diff_deg(target_course, self.course)
            self.course = (self.course + config.clamp(
                diff, -self.motion.turn_rate_deg_s * 2.5 * dt,
                self.motion.turn_rate_deg_s * 2.5 * dt)) % 360.0
            if trail is not None:
                # Tucked into the hunter's baffles: follow it quietly.
                self.speed = min(self.speed_for_state(), max(
                    3.0, float(tactical_observation.speed_kn or 0.0) - 1.0))
            elif (self.mission_orders is not None
                    and self.memory["last_torpedo_age"] > config.SUB_EVADE_DURATION_S):
                # A mission boat slips away from a ping quietly below the
                # layer; only a torpedo in the water makes it run.
                self.speed = min(self.speed_for_state(), config.BOAT_AI_EVADE_KN)
            else:
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
                self.target_course = math.degrees(math.atan2(-cu, -cv)) % 360.0
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
            if self.mission_orders is not None:
                # The mission leg replaces the random patrol leg; the draws
                # above still run, so the boat's stream stays in step.
                self.target_course, self.speed, self.target_depth = self.mission_orders
            elif self.plan_orders is not None:
                self.target_course, self.speed, self.target_depth = self.plan_orders
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
                # veering: the crew must choose a new course.  Only a boat
                # under way reports it; a stopped one merely set by the
                # current against the obstacle stays where it is quietly.
                under_way = self.speed > 0.0 or self.order_speed > 0.0
                self.speed = self.order_speed = 0.0
                if self.crew is not None and under_way:
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
        """Stillheit with the crew's own noise (``noise_discipline``) off it."""
        return config.clamp(self.machinery_quiet_factor() - self.crew_noise, 0.0, 1.0)

    def machinery_quiet_factor(self) -> float:
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
            q -= config.UBOOT_CHARGE_QUIET_LOSS[self.snorkel_rate]
        if self.pumping:
            q -= config.UBOOT_PUMP_QUIET_LOSS
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

    @property
    def crush_depth_m(self) -> float:
        return sub_physics.crush_depth_m(self.stype.max_depth_m)

    def beyond_test_depth(self) -> bool:
        return self.depth > self.stype.max_depth_m

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
        if depth is not None and not 0.0 <= depth <= self.crush_depth_m:
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

    def _steer_to_orders(self, dt: float, safe_depth: float,
                         order_limit: float | None = None) -> None:
        """Follow the crew's orders within the boat's handling limits
        (``order_limit``: the deepest order, below test depth at the crew's risk)."""
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
                ceiling = min(ceiling, config.UBOOT_SURFACE_MAX_KN if self.surfaced
                              else config.UBOOT_SNORKEL_MAX_KN)
        control = self.damage_control
        if not control.power():
            ceiling = 0.0                       # no power: the motor stops
        elif control.down("stern"):
            ceiling *= config.UBOOT_DC_STERN_SPEED_FACTOR
        if self.snorkeling and control.down("engine"):
            # Diesel room flooded, burning or gassed: the diesels stop.
            self.endurance.stop_snorkel()
            if crew is not None:
                crew.event("snorkel_stopped")
        limit = safe_depth if order_limit is None or (crew is not None and crew.bottomed) \
            else order_limit
        self.target_depth = config.clamp(order_depth, 0.0, limit)
        if not self.ballast.dived():
            # Main ballast blown: the boat stays up until the vents flood it.
            self.target_depth = min(self.target_depth, config.UBOOT_MBT_SURFACE_DEPTH_M)
        self._advance_depth(self.target_depth, self.motion.depth_rate_m_s, dt)
        self.speed = config.clamp(self.order_speed, 0.0, ceiling)
        self._update_ballast(dt)
        if crew is not None and crew.mast and (self.depth > MAST_DEPTH_M + 1.0
                                               or control.down("control")):
            crew.mast = False                   # masts come down when diving
            crew.event("mast_lowered")
        if self.snorkeling and self.depth > self.endurance.profile.snorkel_depth_m + 1.0:
            # Dived below snorkel depth: the head valve shuts, diesels stop.
            self.endurance.stop_snorkel()
            if crew is not None:
                crew.event("snorkel_stopped")

    def flooding_kg(self) -> float:
        """Floodwater in the compartments (a crewed boat's only)."""
        return self.damage_control.total_water_kg()

    def flood_moment_kg(self) -> float:
        return self.damage_control.water_moment_kg()

    def _report_test_depth(self, old_depth: float) -> None:
        """The crew calls passing close to and below test depth going down
        (own depth gauge; one call per crossing, no saved state)."""
        if self.sunk or self.state in ("SINKING", "SUNK"):
            return
        test = self.stype.max_depth_m
        near = test * config.UBOOT_TEST_DEPTH_WARN_FRACTION
        depth = f"{self.depth:.0f}"
        if old_depth <= test < self.depth:
            self.crew.event("test_depth_over", depth=depth, test=f"{test:.0f}")
        elif old_depth < near <= self.depth:
            self.crew.event("test_depth_near", depth=depth, test=f"{test:.0f}")

    def _hull_failure(self, ratio: float) -> None:
        """One pressure-hull failure of a crewed boat deep below its limits:
        a bolted fitting, a shaft or valve seal, or a crack in the hull.
        The deeper the boat, the likelier the crack."""
        if self.sunk or self.state == "SINKING":
            return
        control = self.damage_control
        draw = detrand.u01(self.sensor_seed, "hull-failure", control.hits)
        fracture = config.clamp((ratio - 1.0) * config.UBOOT_HULL_FRACTURE_PER_EXCESS,
                                0.0, config.UBOOT_HULL_FRACTURE_MAX)
        if draw < fracture:
            kind, damage = "hull_fracture", config.UBOOT_HULL_FRACTURE_DAMAGE
            notices = control.hull_leak(1.0, self.sensor_seed, spread=0.6)
        elif draw < fracture + config.UBOOT_HULL_SEAL_CHANCE:
            kind, damage = "hull_seal", config.UBOOT_HULL_SEAL_DAMAGE
            where = "stern" if detrand.u01(self.sensor_seed, "hull-seal",
                                           control.hits) < 0.5 else "engine"
            notices = control.hull_leak(0.5, self.sensor_seed, where=where)
        else:
            kind, damage = "hull_bolts", config.UBOOT_HULL_BOLTS_DAMAGE
            notices = control.hull_leak(0.25, self.sensor_seed)
        self.damage = min(100.0, self.damage + damage)
        if self.crew is not None:
            self.crew.event(kind, compartment=notices[0][1]["compartment"])
            for key, values in notices:
                self.crew.event(key, **values)

    def _compartment_hit(self, amount: float) -> None:
        """A crewed boat feels a hit compartment by compartment."""
        if not self.manual or self.sunk or self.state == "SINKING":
            return
        notices = self.damage_control.apply_hit(amount, self.sensor_seed)
        if self.crew is not None:
            for key, values in notices:
                self.crew.event(key, **values)

    def _update_ballast(self, dt: float) -> None:
        """Compartments, pumps, vents and compressor; the residual weight
        and trim move the boat off its ordered depth where the planes cannot
        hold it."""
        ballast = self.ballast
        dc_notices = self.damage_control.update(dt, depth_m=self.depth)
        flooding, moment = self.flooding_kg(), self.flood_moment_kg()
        power = self.damage_control.power()
        compressor = self.snorkeling and self.snorkel_rate != "vent"
        vent = self.order_depth > config.UBOOT_MBT_SURFACE_DEPTH_M + 2.0
        notices = ballast.update(dt, flooding_kg=flooding, flood_moment_kg=moment,
                                 compressor=compressor, vent_ordered=vent, power=power)
        if (power and self.surfaced and self.order_depth <= config.UBOOT_SURFACED_DEPTH_M
                and not ballast.blowing and ballast.lp_blow(dt)):
            notices.append("tanks_lp_blown")
        if ballast.dived() and not self.emergency_ascent:
            drift = ballast.vertical_drift_mps(flooding, self.speed, moment)
            bottom = self.last_bottom_m if self.last_bottom_m is not None else float("inf")
            self.depth = config.clamp(self.depth + drift * dt, 0.0, max(0.0, bottom))
        self.blow_available = ballast.can_blow() and not self.emergency_ascent
        crew = self.crew
        if crew is None:
            return
        for key in notices:
            crew.event(key)
        for key, values in dc_notices:
            crew.event(key, **values)
        # Out-of-trim warnings on the edge (display state, not saved: a loaded
        # boat starts from its current trim and so announces nothing).
        residual = ballast.residual_kg(flooding)
        heavy = ("heavy" if residual > config.UBOOT_HEAVY_WARN_KG
                 else "light" if residual < -config.UBOOT_HEAVY_WARN_KG else None)
        if heavy is not None and heavy != getattr(self, "_trim_seen", heavy):
            crew.event(f"boat_{heavy}", weight=f"{abs(residual) / 1000.0:.1f}")
        self._trim_seen = heavy
        trim = ballast.trim_deg(moment)
        angle = abs(trim) > config.UBOOT_TRIM_WARN_DEG
        if angle and not getattr(self, "_trim_angle_seen", True):
            crew.event("trim_angle", angle=f"{trim:+.1f}")
        self._trim_angle_seen = angle

    def command_trim_auto(self, enabled):
        """Crew: the engineer keeps the boat trimmed, or the crew does."""
        if not self._crew_ready():
            return "not_ready"
        return self.ballast.set_auto(enabled)

    def command_ballast(self, tank, direction):
        """Crew: flood (+1) or pump out (-1) the regulating tank, or move
        trim water forward (+1) or aft (-1); switches the automatic trim off."""
        if not self._crew_ready():
            return "not_ready"
        return self.ballast.step(tank, direction)

    def command_dc_team(self, team, compartment, task):
        """Crew: send a damage-control team to a compartment with a task."""
        if not self._crew_ready():
            return "not_ready"
        return self.damage_control.order_team(team, compartment, task)

    def command_bulkhead(self, compartment, closed):
        """Crew: shut (or open) a compartment's bulkheads."""
        if not self._crew_ready():
            return "not_ready"
        return self.damage_control.set_bulkhead(compartment, closed)

    @property
    def crew_tubes(self):
        """The crew's flood state per tube (``[state, seconds left]``), or None
        when nobody crews the boat (the AI's tubes fire and reload by themselves)."""
        crew = self.crew
        tubes = getattr(crew, "tubes", None) if self.manual else None
        if (not tubes or self.weapon_battery is None
                or len(tubes) != len(self.weapon_battery.tubes)):
            return None
        return tubes

    def _update_tubes(self, dt: float, tubes, was_loading) -> None:
        for index, row in enumerate(tubes):
            tube = self.weapon_battery.tubes[index]
            if was_loading[index] and tube.loaded_weapon_key is not None:
                self.crew.event("tube_loaded", tube=f"{index + 1}")
            if tube.loaded_weapon_key is None and row[0] != "dry":
                tubes[index] = ["dry", 0.0]
            elif row[0] == "flooding":
                left = max(0.0, row[1] - dt)
                tubes[index] = ["flooded", 0.0] if left <= 1e-9 else ["flooding", left]
                if left <= 1e-9:
                    self.crew.event("tube_flooded", tube=f"{index + 1}")

    def _tube_order_ready(self):
        if not self.manual or self.sunk or self.state in ("SINKING", "SUNK"):
            return "not_ready"
        if self.crew_tubes is None:
            return "not_ready"
        if self.damage_control.down("bow"):
            return "uboot_compartment_down"     # torpedo room flooded or burning
        return None

    def command_load_tube(self, tube=None):
        """Load one empty tube from the racks (the first empty one by default)."""
        reason = self._tube_order_ready()
        if reason is not None:
            return reason
        battery = self.weapon_battery
        if tube is None:
            tube = next((item.index for item in battery.tubes
                         if item.loaded_weapon_key is None
                         and item.loading_weapon_key is None), None)
            if tube is None:
                return "uboot_tubes_full"
        if type(tube) is not int or not 0 <= tube < len(battery.tubes):
            return "invalid_value"
        row = battery.tubes[tube]
        if row.loaded_weapon_key is not None or row.loading_weapon_key is not None:
            return "uboot_tubes_full"
        if not battery.load_tube(tube):
            return "no_torpedoes"
        self.crew_tubes[tube] = ["dry", 0.0]
        return True

    def command_flood_tube(self, tube=None, quiet: bool = False):
        """Flood a loaded tube and open its outer door: only a flooded tube fires.
        Flooding takes ``UBOOT_TUBE_FLOOD_S`` and is a short, audible transient;
        quiet flooding takes ``UBOOT_TUBE_FLOOD_QUIET_S`` and is heard only close."""
        reason = self._tube_order_ready()
        if reason is not None:
            return reason
        battery, tubes = self.weapon_battery, self.crew_tubes
        if tube is None:
            tube = next((item.index for item in battery.tubes
                         if item.loaded_weapon_key is not None
                         and tubes[item.index][0] == "dry"), None)
            if tube is None:
                return "uboot_no_dry_tube"
        if type(tube) is not int or not 0 <= tube < len(battery.tubes):
            return "invalid_value"
        if battery.tubes[tube].loaded_weapon_key is None or tubes[tube][0] != "dry":
            return "uboot_no_dry_tube"
        tubes[tube] = ["flooding", float(config.UBOOT_TUBE_FLOOD_QUIET_S if quiet
                                         else config.UBOOT_TUBE_FLOOD_S)]
        self.flood_transient(bool(quiet))
        return True

    def fire_readiness(self, bearing=None, salvo: int = 1):
        """Why a crew torpedo shot is impossible now, or None when ready."""
        if (not self.manual or self.sunk or self.state in ("SINKING", "SUNK")
                or self.mission_peace):
            # Scenario 13 is peacetime: the tubes stay closed.
            return "not_ready"
        if self.damage_control.down("bow"):
            return "uboot_compartment_down"     # torpedo room flooded or burning
        if self.torpedoes_left <= 0:
            return "no_torpedoes"
        if self.torpedoes_left < salvo:
            return "no_torpedoes"
        if self.weapon_battery is not None and self.weapon_battery.ready_count < salvo:
            return "reloading"
        if len(self.pending_torpedoes) + salvo > SUB_MAX_PENDING_TORPEDOES:
            return "reloading"
        tubes = self.crew_tubes
        if tubes is not None and sum(
                row[0] == "flooded" and self.weapon_battery.tubes[index].loaded_weapon_key
                is not None for index, row in enumerate(tubes)) < salvo:
            return "uboot_tube_dry"
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
        for _ in range(launched):
            self.ballast.torpedo_away()
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
        if self.emergency_ascent or self.depth <= 30.0:
            return "not_ready"
        result = self.ballast.blow()
        if result is not True:
            return result
        self.blow_available = False
        self.emergency_ascent = True
        self.transient_left = max(self.transient_left, 20.0)
        # Up and stay up: the crew orders a depth again to flood and dive.
        self.order_depth = config.UBOOT_MBT_SURFACE_DEPTH_M
        if self.crew is not None and self.ballast.blows_left() == 0:
            self.crew.event("hp_air_low")
        return True

    @property
    def surfaced(self) -> bool:
        """Fully up: hull and conning tower above the water."""
        return not self.sunk and self.depth <= config.UBOOT_SURFACED_DEPTH_M

    def command_surface(self, on):
        """Crew: surface (once up, the low-pressure blower empties the main
        ballast) or, near the surface, a crash dive."""
        if type(on) is not bool:
            return "invalid_value"
        if not self._crew_ready():
            return "not_ready"
        if not on:
            return self.command_crash_dive()
        if self.damage_control.down("control"):
            return "uboot_compartment_down"
        self.crew.bottomed = False
        self.order_depth = 0.0
        return True

    def command_crash_dive(self):
        """Crew: alarm dive from the surface or snorkel depth: masts and snorkel
        down, vents open, full ahead and down to ``UBOOT_CRASH_DIVE_DEPTH_M``.
        Blown tanks hold the boat up until the vents have flooded them."""
        if not self._crew_ready():
            return "not_ready"
        if self.depth > config.UBOOT_MBT_SURFACE_DEPTH_M + 2.0:
            return "uboot_not_surfaced"
        self.crew.mast = False
        self.crew.bottomed = False
        if self.snorkeling:
            self.endurance.stop_snorkel()
        self.order_depth = config.UBOOT_CRASH_DIVE_DEPTH_M
        self.order_speed = float(self.motion.maximum_speed_kn)
        self.transient_left = max(self.transient_left, config.UBOOT_CRASH_DIVE_NOISE_S)
        self.crew.event("crash_dive")
        return True

    @property
    def snorkeling(self) -> bool:
        return self.endurance is not None and self.endurance.phase == "SNORKEL"

    @property
    def snorkel_rate(self) -> str:
        """How hard the snorkel run works: the AI always charges in full; a
        crew charges at its ordered rate, and dry bunkers leave only the fans."""
        endurance = self.endurance
        if endurance is None or not self.manual:
            return "full"
        if endurance.generator_kw() <= 0.0:
            return "vent"
        return endurance.charge_rate

    def _snorkel_lines(self) -> list:
        scale = config.UBOOT_CHARGE_LINE_SCALE[self.snorkel_rate]
        return [(hz, amp * scale, width) for hz, amp, width in config.UBOOT_SNORKEL_LINES
                if scale > 0.0]

    def crew_efficiency(self) -> float:
        """The torpedo gang's performance: the boat's air (1.0 without an air
        model) and its empty posts (``weapons_crew_factor``, set by the game
        from the wounded, not saved)."""
        air = 1.0 if self.endurance is None else self.endurance.air.efficiency()
        return air * self.weapons_crew_factor

    def _update_air(self, dt: float) -> None:
        """Breathe, scrub and air the boat; the AI's crew also answers foul air."""
        endurance = self.endurance
        airing = (endurance.phase in ("SNORKEL", "RADIO")
                  and self.depth <= endurance.profile.snorkel_depth_m
                  + endurance.DEPTH_TOLERANCE_M) or (self.manual and self.surfaced)
        notices = endurance.air.update(dt, ventilating=airing, automatic=not self.manual)
        if not self.manual:
            if (endurance.air.level() == "danger"
                    and endurance.phase in ("SUBMERGED", "AIP")):
                # Foul air: the boat must come up and air, whatever the battery.
                endurance.return_depth_m = max(self.depth, endurance.profile.snorkel_depth_m)
                endurance.phase = "ASCENDING"
            return
        if self.crew is None:
            return
        for key in notices:
            self.crew.event(key)
        # Bunker level at the previous step (display state only: a loaded boat
        # starts from its current level and so announces nothing).
        fuel = endurance.fuel_kwh / max(endurance.fuel_capacity_kwh, 1e-9)
        fuel_before = getattr(self, "_fuel_seen", fuel)
        self._fuel_seen = fuel
        if fuel <= 0.0 < fuel_before:
            self.crew.event("fuel_empty")
        elif fuel <= config.UBOOT_FUEL_LOW_FRACTION < fuel_before:
            self.crew.event("fuel_low")

    def command_charge_rate(self, rate):
        """Crew: snorkel charge rate (full, half, or only airing the boat)."""
        if rate not in config.UBOOT_CHARGE_RATES:
            return "invalid_value"
        if not self._crew_ready():
            return "not_ready"
        if self.endurance is None:
            return "uboot_no_snorkel"
        return self.endurance.set_charge_rate(rate)

    def command_absorber(self):
        """Crew: fit a fresh CO2 absorber set."""
        if not self._crew_ready():
            return "not_ready"
        if self.endurance is None:
            return "uboot_no_air_stores"
        return self.endurance.air.change_absorber()

    def command_o2_candle(self):
        """Crew: light an oxygen candle."""
        if not self._crew_ready():
            return "not_ready"
        if self.endurance is None:
            return "uboot_no_air_stores"
        return self.endurance.air.burn_candle()

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
        if self.damage_control.down("engine"):
            return "uboot_compartment_down"
        if self.depth > self.endurance.profile.snorkel_depth_m + 1.0:
            return "uboot_too_deep"
        self.crew.bottomed = False
        if self.order_depth > config.UBOOT_SURFACED_DEPTH_M:
            # Surfaced (or surfacing) the diesels run in the open air.
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
        if on and self.damage_control.down("control"):
            return "uboot_compartment_down"     # control room out: no masts
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
                result.extend(self._snorkel_lines())        # diesel firing lines
            if self.pumping:
                result.append(config.UBOOT_PUMP_LINE)
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
            lines.extend(self._snorkel_lines())          # diesel firing lines
        if self.pumping:
            lines.append(config.UBOOT_PUMP_LINE)
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
                level += config.UBOOT_CHARGE_QUIET_LOSS[self.snorkel_rate]
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
