"""The simulation step of the game: real-time frame update, ordered entity
updates, sensor generation, weapons, damage and mission end (``Game`` mixin).

Verbatim moves from ``game.py`` (plan 1.3, phase 2, step 2). The update order
inside ``_update_sim`` is the ``SIM_ORDER`` contract frozen by
``tests/test_sim_order.py``."""

import hashlib
import math
import time
from types import SimpleNamespace

import pygame

from src.audio.preview import unit_sonar_preview
from src.audio.synthesis import bearing_pan
from src.core import config
from src.core import detrand
from src.core.i18n import message, raw_text
from src.core.station import Station
from src.core.save_schema import PING_INTERCEPTS_MAX
from src.core import boat_ai, boat_autocrew, boat_debrief, boat_missions, hunter, opfor, phone_lookout
from src.core.limits import (
    MAX_DECOYS,
    MAX_ENEMY_TORPEDOES,
    MAX_SAVED_ASMS,
    MAX_SAVED_ESSMS,
    MAX_SAVED_PLAYER_TORPEDOES)
from src.sensors import visual as visual_physics
from src.sensors import lookout_id
from src.sensors import nav_lights
from src.sensors import threat_cue
from src.ui import unit_variants
from src.sonar import equation as sonar_equation
from src.sonar import propagation as sonar_propagation
from src.physics import torpedo_dyn
from src.physics import ship_dynamics
from src.weapons import ciws as ciws_physics
from src.sensors.platform import MAST_DEPTH_M
from src.enemies.decoy import Decoy
from src.enemies.sub import Sub
from src.enemies.surface import SurfaceShip
from src.enemies import traffic
from src.sensors.platform import exchange_friendly_datalink, snapshot_observation
from src.sonar.sonar import TowState, hull_length_m
from src.ui import layout
from src.ui.splash_view import SPLASH_PING_PERIOD_S
from src.air import helicopter as helicopter_physics
from src.sensors import mad as mad_physics
from src.air.flights import Flight
from src.weapons.torpedo import EnemyTorpedo, Torpedo
from src.weapons.asw import ASROC, MAX_ASROCS
# Names tests and tools import from ``src.core.game`` (kept as re-exports).


SONAR_CLASS_KINDS = {
    "U_BOOT": "SUB",
    "KAMPFSCHIFF": "SURFACE",
    "FAHRZEUG": "SURFACE",
    "TORPEDO": "TORP",
}

TORPEDO_WAKE_VISIBLE_NM = config.TORPEDO_WAKE_VISIBLE_NM


TORPEDO_WAKE_VISIBLE_DEPTH_M = 15.0


# Directional hearing: a foreign ping's tone, and how close a sound is to be
# heard from everywhere (centred) rather than from a bearing.
ENEMY_PING_HZ = 1300.0
ENEMY_PING_VOLUME = 0.3
HEARD_CENTRE_NM = 0.05


# Koschmieder lookout model anchored to the 1.0.0 day/calm/clear ranges.
LOOKOUT_MODEL = visual_physics.LookoutModel(
    {"SURFACE": config.LOOKOUT_SURFACE_RANGE_NM, "SUB": config.LOOKOUT_SUB_RANGE_NM,
     "FLG": config.LOOKOUT_AIR_RANGE_NM, "TORP": TORPEDO_WAKE_VISIBLE_NM,
     "LAND": config.LOOKOUT_LAND_RANGE_NM, "MAST": config.LOOKOUT_FEATHER_RANGE_NM},
    config.WEATHER_VISIBILITY_MAX_NM)


# The stage order of one ``_update_sim`` substep (``tests/test_sim_order.py``
# freezes it).  Stages behind an accumulator (sensors, ESM, radio, slow) run
# on their own cadence but never out of this order within a substep.
SIM_ORDER = (
    "_mission_time_warning", "_update_navigation", "_update_asw_stores",
    "_update_platform_sensors", "_update_underwater_entities",
    "_update_aviation", "_update_raiders", "_update_air_defense",
    "_update_enemy_torpedoes", "_update_player_torpedoes", "_update_asrocs",
    "_update_depth_charges", "_update_sensors", "_update_esm_picture", "_update_radio_picture",
    "_update_opz_picture", "_update_damage_and_mission", "_record_simlog_state",
)


class SimMixin:
    """Simulation half of ``Game``: ``update`` and everything ``_update_sim`` runs."""

    def _sonar_range_factor(self) -> float:
        """Continuous sonar-room capability: an undamaged room keeps full
        range, a degraded one falls to DMG_SONAR_DEGRADED_FACTOR and below."""
        if self.damage.station_degraded("sonar"):
            return config.DMG_SONAR_DEGRADED_FACTOR * (
                0.5 + 0.5 * self.damage.capability("sonar"))
        return 1.0

    def _sonar_targets(self) -> list:
        """Akustisch auffassbare Ziele: Boote, Tiere, Dekoys, Zivilverkehr,
        feindliche Schiffe und laufende Feindtorpedos."""
        return ([s for s in self.subs if not s.sunk]
                + [a for a in self.animals if not a.dead]
                + [d for d in self.decoys if not d.dead]
                + [c for c in self.civilians if not c.sunk]
                + [w for w in self.warships if not w.sunk]
                + [t for t in self.enemy_torpedoes if t.state == "RUN"])

    def _drain_enemy_torpedoes(self) -> None:
        for sub in self.subs:
            while (sub.pending_torpedoes
                   and len(self.enemy_torpedoes) < MAX_ENEMY_TORPEDOES):
                row = sub.pending_torpedoes.pop(0)
                x, y, course, depth = row[:4]
                guidance = row[4:6] if len(row) >= 6 else (None, None)
                profile_key, launch_platform_id, launch_weapon_key = row[6:9]
                self.enemy_torpedoes.append(
                    EnemyTorpedo(x, y, course, depth,
                                 len(self.enemy_torpedoes) + 1,
                                 profile=self.runtime_catalog.torpedoes[profile_key],
                                 guidance_x=guidance[0], guidance_y=guidance[1],
                                 launch_platform_id=launch_platform_id,
                                 launch_weapon_key=launch_weapon_key,
                                 time_since_launch=0.0))

    def update(self, dt: float, audio_dt: float | None = None) -> None:
        with layout.bottom_panel_regions(self.bottom_panel_mode()):
            self._update(dt, audio_dt)

    def _update(self, dt: float, audio_dt: float | None = None) -> None:
        """Advance simulation in real time with bounded physics substeps."""
        wall_dt = audio_dt if audio_dt is not None else dt
        self.audio.debug_log(wall_dt, receiver=getattr(self.sonar, "receiver", None))
        if self.splash_active:
            splash_elapsed = self._t - self.splash_started_at
            ping_cycle = int(max(0.0, splash_elapsed) / SPLASH_PING_PERIOD_S)
            if ping_cycle != self._splash_ping_cycle:
                self._splash_ping_cycle = ping_cycle
                self.audio.play_ping()
            self._frame_clock_reset = True
            return
        # The game always runs in real time: overlays, menus opened over a
        # mission and focus loss never stop it. Only no mission (menu) or a
        # finished one has nothing to simulate.
        if not self.running or self.in_menu or self.main_menu or self.game_over:
            # Nothing is caught up after the menu or game over.
            self._frame_clock_reset = True
            self.audio.stop()
            self._sonar_audio_sequence = -1
            return
        playing_boat = self.local_side == "uboot"
        self.audio.local_effects = not playing_boat
        if playing_boat and self._opfor is None:
            self.claim_opfor_sub()
        # Operator adjustments follow wall time; hull and weapon motion do not.
        turn, _ = (0.0, 0.0) if playing_boat else self.steering_input()
        if turn:
            # The rudder takes over from the autopilot.
            self.cancel_route()
        if not playing_boat and not self.damage.station_down("bridge"):
            self.ship.steer_input(dt, turn, 0)
        if self.station is Station.WEAPONS and not playing_boat:
            depth_dir = int(pygame.K_UP in self.held) - int(pygame.K_DOWN in self.held)
            self.torpedo_depth = config.clamp(
                self.torpedo_depth + depth_dir * 20.0 * dt, 10.0, 300.0)
        sim_dt = dt
        n = max(1, int(math.ceil(sim_dt / config.PHYS_SUBSTEP_S)))
        n = min(n, config.PHYS_SUBSTEP_MAX)
        step = sim_dt / n
        sim_started = time.perf_counter() if self._perf_debug_enabled else None
        for _ in range(n):
            self._update_sim(step)
            if self.game_over:
                break
        if sim_started is not None:
            self._perf_sim_s += time.perf_counter() - sim_started
            self._perf_substeps += n
        # Display-only chart history (own track, earlier fixes and bearings).
        self.chart_history.record(self)
        self.map_view.set_rect(config.MAP_RECT)
        if self.map_follow:
            self.map_view.cx, self.map_view.cy = self.ship.x, self.ship.y
            self.map_view.clamp_center()
        self._configure_opz_map_view()
        if self.opz_map_follow:
            self.opz_map_view.cx, self.opz_map_view.cy = self.ship.x, self.ship.y
            self.opz_map_view.clamp_center()
        if not self.game_over:
            audio_started = time.perf_counter() if self._perf_debug_enabled else None
            if playing_boat:
                # The local mixer plays the boat's own sonar room only.
                if self._opfor is not None and self.station is Station.SONAR:
                    with self.sonar_perspective(self._opfor.station):
                        self._update_audio(wall_dt)
                else:
                    self._stop_sonar_audio()
            else:
                self._update_audio(wall_dt)
            if audio_started is not None:
                self._perf_audio_s += time.perf_counter() - audio_started
        else:
            self.audio.stop()
            self._sonar_audio_sequence = -1

    def _update_audio(self, dt: float) -> None:
        """Stream opt-in sonar; there is no continuous own-ship ambience."""
        helicopter = self.station is Station.HELICOPTER
        receiver = self.helo_receiver if helicopter else self.sonar.receiver
        listening = (self.helo_audio_enabled and self.helicopter_audio_ready()
                     if helicopter else self.station is Station.SONAR
                     and self.sonar_audio_enabled
                     and not self._sonar_down())
        if not listening:
            self._stop_sonar_audio()
        else:
            blocks = receiver.blocks_since(self._sonar_audio_sequence)
            if not blocks:
                self.audio.hold_sonar()
            for sequence, samples in blocks:
                if (self._sonar_audio_sequence < 0
                        or sequence != self._sonar_audio_sequence + 1):
                    if self._sonar_audio_sequence < 0:
                        self.audio.stop_sonar(immediate=True)
                    else:
                        self.audio.discontinue_sonar_input()
                    (self.helo_audition if helicopter else self.sonar).reset_audition_audio()
                if not self.audio.play_sonar(
                        (self.helo_audition if helicopter else self.sonar).listening_samples(
                            samples, block_id=sequence),
                        receiver.sample_rate, self.sonar_volume,
                        bearing_deg=0 if helicopter else self.sonar.listen_bearing,
                        listener_bearing_deg=0 if helicopter else self.ship.course,
                        buffered=True):
                    break
                self._sonar_audio_sequence = sequence

    def _emit_sound(self, kind: str, at=None, pan: float | None = None) -> None:
        """Play locally and publish a bounded, detached browser sound cue.

        ``at``: where a detonation happened, so a crewed boat hears it too and
        the frigate hears it from its (measured) bearing. ``pan``: left/right
        of the ship's head (-1 port .. +1 starboard); None plays it centred."""
        if at is not None and self._opfor is not None:
            opfor.hear_detonation(self, self._opfor, float(at[0]), float(at[1]))
        if at is not None and kind == "explosion":
            traffic.alarm(self.civilians, float(at[0]), float(at[1]))
        if at is not None and pan is None:
            pan = self._heard_pan(float(at[0]), float(at[1]), kind)
        if kind == "sonar_ping":
            self.audio.play_ping()
        elif kind == "enemy_ping":
            self.audio.play_ping(ENEMY_PING_HZ, ENEMY_PING_VOLUME, pan=pan)
        elif kind == "esm_contact":
            if (self.station is Station.ELOKA
                    and self.eloka_audio_enabled
                    and not self.damage.station_down("opz")):
                self.audio.play_alert("esm")
        else:
            self.audio.play_effect(kind, pan=pan)
        self._sound_event_seq += 1
        self._sound_events.append(dict(seq=self._sound_event_seq, kind=kind, pan=pan))

    def _hull_slam(self, previous_pitch: float) -> None:
        """A bow coming down hard into a head sea slams: a sound only (the
        seakeeping model already carries the motion)."""
        pitch = self.ship.pitch
        if (previous_pitch > -config.HULL_SLAM_PITCH_DEG >= pitch
                and self.ship.speed >= config.HULL_SLAM_MIN_KN
                and getattr(self.world, "effective_sea_state", self.world.sea_state)
                >= config.HULL_SLAM_SEA_STATE):
            self._emit_sound("hull_slam")

    def _heard_pan(self, x: float, y: float, kind: str) -> float:
        """Where the crew hears a sound from ``x, y``: its bearing by ear
        (a few degrees off, deterministic) relative to the ship's head."""
        if math.hypot(x - self.ship.x, y - self.ship.y) < HEARD_CENTRE_NM:
            return 0.0
        bearing = (math.degrees(math.atan2(x - self.ship.x, -(y - self.ship.y)))
                   + config.UBOOT_DETONATION_BEARING_SD_DEG * detrand.normal(
                       self.seed, f"heard_{kind}", int(round(self.sim_t * 1000.0))))
        return bearing_pan(bearing, self.ship.course)

    ECHO_LOUD_SNR_DB = 12.0

    def _remember_ping_pulse(self) -> None:
        self._ping_pulses[self.sim_t] = self.sonar.ping_pulse
        while len(self._ping_pulses) > 32:
            del self._ping_pulses[next(iter(self._ping_pulses))]

    def _emit_echo(self, echo: dict) -> None:
        """Make one arrived echo audible: local synthesis and a browser cue.

        The simulation already delays the echo by its two-way travel time;
        this only turns the measured return (pulse, echo SNR) into sound.
        """
        pulse = self._ping_pulses.get(echo.get("t"), self.sonar.ping_pulse)
        pulse = pulse if pulse in ("CW", "LFM") else "CW"
        snr_db = float(echo.get("snr_db", 0.0))
        level = config.clamp((snr_db + 5.0) / 35.0, 0.0, 1.0)
        # The echo comes back from its measured bearing.
        pan = (bearing_pan(float(echo["bearing"]), self.ship.course)
               if isinstance(echo.get("bearing"), (int, float)) else None)
        self.audio.play_echo(pulse, level, pan=pan)
        cue = f"sonar_echo_{pulse.lower()}"
        if snr_db < self.ECHO_LOUD_SNR_DB:
            cue += "_faint"
        self._sound_event_seq += 1
        self._sound_events.append(dict(seq=self._sound_event_seq, kind=cue, pan=pan))

    def _play_unit_audio(self, profile_key: str, mode: str, machine) -> None:
        """Kontakt-Katalog-Hörprobe: deterministisches Einheiten-Sample abspielen."""
        rate = self.audio.sample_rate
        key = ("sonar", "unit_preview", profile_key, mode, rate)
        self.audio.play_unit_preview(
            lambda: unit_sonar_preview(profile_key, machine, mode, rate), key)

    def _update_navigation(self, dt: float) -> None:
        """Wendet Steuerung, Brückenschaden und Telegraph auf die Fregatte an."""
        if self.damage.station_down("bridge"):
            self.ship.target_course = self.ship.course
        self.ship.turn_rate_scale = (
            0.5 if self.damage.station_degraded("bridge") else 1.0)
        self.ship.speed_cap = self.damage.engine_speed_cap()
        self.ship.trim_noise = self.damage.trim_noise_boost()
        # Steering gear sits aft under the flight deck; a destroyed room
        # jams the rudder where it is. Stabilizer fins are lost with either
        # hull side destroyed. Floodwater adds displacement.
        jammed, emergency = self.rudder_casualty()
        if emergency:
            # Emergency steering from the steering gear room: half rate.
            self.ship.turn_rate_scale *= 0.5
        self.ship.steering_jammed = self.damage.station_down("flightdeck") or jammed
        self.ship.stabilizers_ok = not (self.damage.station_down("hull_left")
                                        or self.damage.station_down("hull_right"))
        self.ship.flood_percent = (self.damage.flood_mass_kg()
                                   / ship_dynamics.HULL.flood_kg_per_percent)
        self.ship.update_fuel(dt)
        self.world.update(dt)
        self._steer_route(dt)
        self._steer_baffle_clear()
        previous_pitch = self.ship.pitch
        contact = self.ship.update(dt, self.world, self.damage.list_deg())
        self._hull_slam(previous_pitch)
        if contact is not None:
            speed_m_s = self.ship.last_impact_speed_kn * 1852.0 / 3600.0
            heading = math.radians(self.ship.course)
            normal_factor = abs(math.sin(heading) * contact.normal_x
                                - math.cos(heading) * contact.normal_y)
            if normal_factor <= 1e-9:
                normal_factor = 1.0
            normal_speed = speed_m_s * normal_factor
            energy_j = (0.5 * self.ship.hull_spec.mass_t * 1000.0
                        * normal_speed ** 2)
            self.damage.grounding_impact(
                energy_j, contact.hull_longitudinal, contact.hull_lateral)
            notice = message(f"event.grounding.{contact.kind}")
            self.flash(notice, 4.0)
            self.feed.add(self.world.format_time(), "navigation",
                          message("runtime.grounding.feed", kind=notice))

    def _shipping_noise_contacts(self) -> int:
        """Merchant traffic within 50 NM that feeds distant-shipping noise."""
        return sum(1 for ship in self.civilians
                   if not ship.sunk and ship.distance_nm(self.ship) <= 50.0)

    def _update_platform_sensors(self, dt: float) -> None:
        """Run independent NPC sensors before any actor makes a decision."""
        ship_target = SimpleNamespace(
            id=0, x=self.ship.x, y=self.ship.y, depth=5.0,
            course=self.ship.course, speed=self.ship.speed, active=True,
            sunk=False, side="friendly", name=None, sensor_domain="surface",
            radar_emitting=(not self.damage.station_down("opz")
                            and (self.surface_radar_on or self.air_radar_on)),
            ais_transmitting=False, noise_level=self.ship.noise_level)
        actors = sorted(
            self.subs + self.civilians + self.warships + self.flights.flights,
            key=lambda actor: (type(actor).__name__,
                               getattr(actor, "id", getattr(actor, "seq", 0))))
        suites = []
        all_candidates = [ship_target, *actors, *self.animals, *self.decoys,
                          *self.asms]
        for actor in actors:
            suite = actor.sensor_suite
            suites.append(suite)
            actor._tactical_observation = None
            actor._asw_observation = None
            domains = set()
            degraded = set()
            if getattr(actor, "sunk", False) or getattr(actor, "damage", 0.0) >= 75.0:
                domains = {"radar", "esm", "sonar", "ais"}
            elif getattr(actor, "damage", 0.0) >= 34.0:
                degraded = {"radar", "esm", "sonar", "ais"}
            candidates = [candidate for candidate in all_candidates
                          if getattr(candidate, "side", None) != actor.side]
            suite.datalink_reachable = not (
                isinstance(actor, Sub) and actor.depth > MAST_DEPTH_M
                and getattr(getattr(actor, "endurance", None), "phase", "")
                not in ("SNORKEL", "RADIO"))
            suite.update(
                self.sim_t, actor, candidates, self.world, self.runtime_catalog,
                emcon={"radar": getattr(actor, "radar_emitting", False),
                       "ais": getattr(actor, "ais_transmitting", False)},
                unavailable=domains, degraded=degraded)
            # Metadata-only R10 submarine components retain the established
            # tactical gate; the actor still receives only a detached observation.
            legacy_observation = (not suite.controllers or getattr(
                actor, "legacy_observation_model", False))
            if legacy_observation and actor.side == "hostile":
                distance = math.hypot(actor.x - self.ship.x, actor.y - self.ship.y)
                blocked = self.world.land_blocks_line(
                    actor.x, actor.y, self.ship.x, self.ship.y)
                if (isinstance(actor, Sub) and distance < 20.0
                        and (actor.memory["last_ping_age"] <= dt
                             or (self.ship.noise_level() >= 0.75 and distance < 18.0))
                        and not self.world.sonar_path_blocked(
                            actor.x, actor.y, actor.depth,
                            self.ship.x, self.ship.y, 5.0)):
                    actor._tactical_observation = snapshot_observation(
                        actor, self.ship, domain="sonar", now=self.sim_t)
                elif (isinstance(actor, SurfaceShip) and actor.emitter
                      and distance <= config.WARSHIP_ASM_RANGE_NM and not blocked):
                    actor._tactical_observation = snapshot_observation(
                        actor, self.ship, domain="radar", now=self.sim_t)
                elif (isinstance(actor, Flight) and actor.esm
                      and ship_target.radar_emitting
                      and distance <= actor.esm_range_nm and not blocked):
                    actor._tactical_observation = snapshot_observation(
                        actor, self.ship, domain="esm", now=self.sim_t,
                        positioned=False)
        exchange_friendly_datalink(suites, self.sim_t)
        # Friendly platforms publish detached radar fixes into the own-ship air
        # picture. Candidate identity is used only at this sensor-generation
        # boundary; downstream weapons consume the resulting saved observation.
        for actor in actors:
            suite = actor.sensor_suite
            if actor.side != "friendly" or suite.datalink_group != "blue":
                continue
            for asm in self.asms:
                for report in suite.tracks_for_candidate(asm, self.sim_t):
                    if (report.domain != "radar" or report.x is None
                            or report.y is None or report.range_nm is None):
                        continue
                    dx, dy = report.x - self.ship.x, report.y - self.ship.y
                    self.air_picture.observe(
                        track_id=f"M-{asm.seq}", kind="ASM", target_id=asm.seq,
                        source="DATALINK",
                        bearing=math.degrees(math.atan2(dx, -dy)) % 360.0,
                        range_nm=math.hypot(dx, dy), observer_x=self.ship.x,
                        observer_y=self.ship.y, course=report.course,
                        quality=report.quality, now=report.last_seen,
                        position_time=report.last_seen, label=f"A-{asm.seq}",
                        bearing_uncertainty_deg=report.bearing_uncertainty_deg)
        for actor in actors:
            suite = actor.sensor_suite
            if (not suite.controllers
                    or getattr(actor, "legacy_observation_model", False)):
                continue
            tracks = suite.tactical_tracks(self.sim_t)
            preferred = ("sonar" if isinstance(actor, Sub) else
                         "esm" if isinstance(actor, Flight) else "radar")
            actor._tactical_observation = next(
                (track for track in tracks if track.domain == preferred),
                tracks[0] if tracks else None)
            if isinstance(actor, SurfaceShip):
                actor._asw_observation = next(
                    (track for track in tracks
                     if track.domain == "sonar"
                     and track.fix_source in ("ACTIVE", "TMA", "BUOY", "FUSED")
                     and track.x is not None and track.y is not None), None)

    def _deliver_ping_intercepts(self) -> None:
        """Warn of foreign active pings whose sound has reached the frigate.

        Pings still travelling are saved (v16 ``ping_intercepts``)."""
        arrived = [row for row in self._ping_intercepts if row[0] <= self.sim_t]
        if not arrived:
            return
        self._ping_intercepts = [row for row in self._ping_intercepts
                                 if row[0] > self.sim_t]
        for arrival, x, y in sorted(arrived):
            # Measured by ear: the same deterministic error as the crewed
            # boat's alarm bearing, keyed by the (saved) arrival time.
            bearing = (math.degrees(math.atan2(x - self.ship.x, -(y - self.ship.y)))
                       + config.PING_INTERCEPT_SIGMA_DEG * detrand.normal(
                           self.seed, "ping_intercept", int(round(arrival * 1000.0)))
                       ) % 360.0
            self.flash(message("runtime.enemy_ping.detected",
                               bearing=f"{bearing:03.0f}"), 3.0)
            self.audio.play_alert("danger")
            self._emit_sound("enemy_ping", pan=bearing_pan(bearing, self.ship.course))
            self.feed.add(self.world.format_time(), "sonar",
                          message("runtime.enemy_ping.feed",
                                  bearing=f"{bearing:03.0f}"))

    def _update_underwater_entities(self, dt: float) -> None:
        """Aktualisiert U-Boote, Tiere, Zivile und Dekoys."""
        self._deliver_ping_intercepts()
        self._apply_incident_effects()
        # The AI mission boat's leg for this substep (before it moves).
        boat_ai.steer(self)
        for sub in self.subs:
            was_sunk = sub.sunk
            sub.update(dt, getattr(sub, "_tactical_observation", None), self.world)
            distance = math.hypot(sub.x - self.ship.x, sub.y - self.ship.y)
            if (sub.pinged_this_tick
                    and distance <= config.SONAR_PING_HEAR_RANGE_NM
                    and not self.world.sonar_path_blocked(
                        sub.x, sub.y, sub.depth, self.ship.x, self.ship.y, 5.0)
                    and len(self._ping_intercepts) < PING_INTERCEPTS_MAX):
                # The transmission reaches the frigate after its one-way travel
                # time, not in the frame the boat sends.
                self._ping_intercepts.append((
                    float(self.sim_t + self.world.echo_delay_s(
                        distance, (sub.x + self.ship.x) * .5,
                        (sub.y + self.ship.y) * .5) * .5),
                    float(sub.x), float(sub.y)))
            if sub.sunk and not was_sunk:
                if sub.side == "hostile":
                    self.score += config.SCORE_SUNK
                else:
                    self.incident = True
                self._report_breakup_noise(sub.x, sub.y, sub.depth, sub.id)
            if sub.sunk and sub.side == "hostile" and self.roe != "FREE":
                self.roe = "FREE"
                self.hq_msg(message("runtime.roe_free_confirmed"))
        for animal in self.animals:
            animal.update(dt, self.world)
        if traffic.due(self.sim_t, dt):
            traffic.plan(self.civilians, [self.ship, *self.warships, *self.civilians],
                         self.seed, self.world)
        for civilian in self.civilians:
            civilian.update(dt, getattr(civilian, "_tactical_observation", None),
                            self.world)
        for w in self.warships:
            w.update(dt, getattr(w, "_tactical_observation", None), self.world,
                     asw_observation=getattr(w, "_asw_observation", None))
        for sub in self.subs:
            while sub.pending_decoys and len(self.decoys) < MAX_DECOYS:
                dx, dy = sub.pending_decoys.pop(0)
                decoy_profile = self.runtime_catalog.decoys[
                    self.runtime_catalog.runtime_bindings["submarine_decoy"]]
                self.decoys.append(Decoy(
                    dx, dy, sub.depth, self.rng_asw, decoy_profile,
                    self.runtime_catalog.acoustic_for(decoy_profile.key),
                    source_id=sub.id))
        for decoy in self.decoys:
            decoy.update(dt, self.world)
        self.decoys = [decoy for decoy in self.decoys if not decoy.dead]

    def _update_aviation(self, dt: float) -> None:
        """Aktualisiert HSP-5, Sonarbojen und Chaff-Kühlzeit."""
        if (self.helo.dip_state in ("DEPLOYING", "DEPLOYED")
                and not self.helicopter_weather()["dipping_safe"]):
            self.helo.set_dipping(False, self.world)
        icing = (self.atmosphere()["icing"] if self.helo.airborne else "none")
        self.helo.update(dt, self.ship, self.world,
                         recovery_available=not self.damage.station_down("flightdeck")
                         and helicopter_physics.deck_within_limits(
                             self.ship.roll, self.ship.pitch),
                         fuel_factor=(config.HELO_ICING_FUEL_FACTOR
                                      if icing != "none" else 1.0))
        self._fly_buoy_pattern()
        self._update_helo_radar(dt)
        self._update_mpa(dt)
        self._update_aircrew_eyes(dt)
        self._update_sub_radar_alert(dt)
        for buoy in self.buoys:
            buoy.update(dt, self.world)
        self.buoys = [buoy for buoy in self.buoys if buoy.active]
        self.softkill_store.update(dt)
        self.chaff_cd = min(self.softkill_store.loading, default=0.0)

    def _fly_buoy_pattern(self) -> None:
        """Fly the queued pattern points; each one is an ordinary single drop
        at the helicopter's measured position when it gets there."""
        helo = self.helo
        if not helo.pattern_queue:
            return
        if helo.state != "AUF" or helo.hovering:
            return
        target_x, target_y = helo.pattern_queue[0]
        if (helo.waypoint_x, helo.waypoint_y) != (target_x, target_y):
            helo.set_waypoint(target_x, target_y)
        if math.hypot(helo.x - target_x, helo.y - target_y) > helicopter_physics.PATTERN_DROP_RADIUS_NM:
            return
        result = self.deploy_helicopter_buoy()
        helo.pattern_queue.pop(0)
        if result is True:
            buoy = self.buoys[-1]
            self.flash(message("runtime.buoy.deployed", buoy=buoy.seq))
            self.feed.add(self.world.format_time(), "sonar",
                          message("runtime.buoy.active", buoy=buoy.seq))
        elif result == "no_buoys":
            helo.pattern_queue = []
        if not helo.pattern_queue:
            helo.pattern = "single"
            self.flash(message("runtime.helo.pattern_done"), 2.0)

    def _update_mad(self, targets, dt: float) -> None:
        """MAD run: a stateless draw per submerged hull under the helicopter."""
        helo = self.helo
        if not helo.mad_mode or not helo.airborne or helo.hovering:
            return
        tick = int(self.sim_t / max(dt, 1e-6))
        for target in targets:
            if (getattr(target, "sensor_domain", None) != "subsurface"
                    or getattr(target, "sunk", False)):
                continue
            slant = mad_physics.slant_m(math.hypot(helo.x - target.x, helo.y - target.y),
                                        getattr(target, "depth", 0.0))
            if slant > mad_physics.MAD_MAX_SLANT_M:
                continue
            if not mad_physics.detects(self.seed, target.id, tick, slant):
                continue
            contact = self.sonar._get_contact(target)
            contact._fx, contact._fy = self.ship.x, self.ship.y
            previous = contact.fixes.get("MAD")
            contact.update_mad(helo.x, helo.y, self.sim_t,
                               mad_physics.MAD_FIX_UNCERTAINTY_NM,
                               mad_physics.MAD_FIX_QUALITY)
            if previous is None or self.sim_t - previous["measured_at"] >= 10.0:
                notice = message("runtime.helo.mad_contact", contact=contact.id)
                self.flash(notice, 3.0)
                self.feed.add(self.world.format_time(), "sonar", notice)

    def _update_asw_stores(self, dt: float) -> None:
        scale = (0.0 if self.damage.station_down("weapons") else
                 .5 if self.damage.station_degraded("weapons") else 1.0)
        scale *= self.casualty_factor("weapons")
        self.player_torpedo_battery.update(dt, scale)
        self.torpedo_count = self.player_torpedo_battery.remaining_total
        self.nixie_store.update(dt)
        for decoy in self.nixies:
            decoy.update(dt, self.ship, self.world)
        self.nixies = [decoy for decoy in self.nixies if not decoy.dead]

    def _update_air_defense(self, dt: float, publish_picture: bool = True) -> None:
        """Aktualisiert ASM-Wellen, CIWS und ESSM-Abfangflugkorper."""
        profiles = self._air_defense_loadout
        self._drain_warship_asm()
        self._drain_raider_asm()
        self._maybe_spawn_asm()
        self._auto_ecm_softkill()
        # Softkill state is resolved by ASM.update before layered hardkill.
        self.ciws_cooldown_s = max(0.0, getattr(self, "ciws_cooldown_s", 0.0) - dt)
        for cloud in self.chaff_clouds:
            cloud.update(dt, self.world.wind_from_deg, self.world.wind_speed_kn)
        self.chaff_clouds = [cloud for cloud in self.chaff_clouds if cloud.active]
        clouds = {cloud.seq: cloud for cloud in self.chaff_clouds}
        for asm in self.asms:
            asm.update(dt, self.ship, self.world,
                       ecm_effect=self._ecm_effect_against_asm(asm),
                       chaff_target=clouds.get(asm.chaff_cloud))
            if asm.state == "TREFFER":
                hit = self.damage.missile_hit(*self._hull_impact(asm.x, asm.y))
                self._emit_sound("explosion", at=(asm.x, asm.y))
                self.announce(message("runtime.hit.asm", compartments=", ".join(
                    self.damage.compartments[k].name for k in hit)),
                    "schaden", 5.0)
        observed_asms = {self._missile_seq(track): track
                         for track in self.asm_tracks()
                         if self._missile_seq(track) is not None}
        for essm in self.essms:
            track = observed_asms.get(essm.target_id)
            if (not essm.seeker_acquired and track is not None
                    and track.x is not None and track.y is not None
                    and track.position_seen is not None
                    and self.sim_t - track.position_seen
                    <= profiles["sam"]["observation_max_age_s"]):
                essm.guidance_x, essm.guidance_y = track.x, track.y
            essm.update(dt, candidates=self.asms, world=self.world)
        ciws = profiles["ciws"]
        # CIWS fire control works on its latest own measurement, not on the
        # smoothed OPZ track range.
        def fc_range(track):
            return (track.raw_range_nm if track.raw_range_nm is not None
                    else track.range_nm)

        # The mount slews towards the nearest fresh close-in missile track.
        close_tracks = sorted(
            (fc_range(track), track.track_id, track) for track in observed_asms.values()
            if fc_range(track) is not None and fc_range(track) <= ciws["range_nm"]
            and track.position_seen is not None
            and self.sim_t - track.position_seen <= ciws["observation_max_age_s"])
        if self.ciws_authorized and close_tracks:
            self.ciws_mount_deg = ciws_physics.slew(
                self.ciws_mount_deg, close_tracks[0][2].bearing, dt)
        for asm in self.asms:
            track = observed_asms.get(asm.seq)
            if (self.ciws_authorized
                    and asm.state in ("LAUF", "CHAFF")
                    and not (asm.state == "CHAFF" and asm.broken)
                    and track is not None
                    and track.x is not None and track.y is not None
                    and track.position_seen is not None
                    and self.sim_t - track.position_seen
                    <= ciws["observation_max_age_s"]
                    and self.ciws_ammo >= ciws["rounds_per_attempt"]
                    and fc_range(track) is not None
                    and fc_range(track) <= ciws["range_nm"]
                    and self.ciws_cooldown_s <= 0.0
                    and ciws_physics.on_target(self.ciws_mount_deg, track.bearing)
                    and not self.damage.station_down("opz")
                    and not self.world.land_blocks_line(
                        self.ship.x, self.ship.y, track.x, track.y)):
                self.ciws_ammo -= ciws["rounds_per_attempt"]
                self.ciws_cooldown_s = ciws["cycle_s"]
                self._emit_sound("gunfire")
                # Burst physics at the true geometry: dispersion and
                # prediction error over the rounds' time of flight; a missile
                # that arrives first cannot be stopped by this burst.
                distance = asm.distance_nm(self.ship)
                time_to_go = distance / max(config.kn_to_nm_per_s(asm.speed_kn), 1e-9)
                kill = (0.0 if time_to_go <= ciws_physics.time_of_flight_s(distance)
                        else ciws_physics.burst_kill_probability(
                            distance, ciws["rounds_per_attempt"],
                            asm.jamming(self.ship), ciws["kill_probability"]))
                if self.rng_asm.random() < kill:
                    asm.state = "ABGEFANGEN"
                    self.audio.play_alert("defense")
                    self.announce(message("runtime.ciws.intercepted"),
                                  "waffen", 3.0)
        self.asms = [a for a in self.asms if a.state in ("LAUF", "CHAFF")]
        self.essms = [e for e in self.essms if e.state == "LAUF"]
        if publish_picture:
            self._update_air_picture()
            observed_threat = bool(self.asm_tracks())
            if observed_threat and not self.air_threat_reported:
                self.flash(message("runtime.threat.air"), 4.0)
                self.feed.add(self.world.format_time(), "waffen", message("runtime.threat.air"))
            self.air_threat_reported = observed_threat

    def _auto_ecm_softkill(self) -> None:
        """Couple critical terminal ECM tracks to the finite RF decoy store."""
        if (not self.ecm_jammer.auto_enabled or self.softkill_store.ready <= 0
                or self.damage.station_down("opz")):
            return
        by_target = {self._missile_seq(track): track
                     for track in self.asm_tracks()
                     if self._missile_seq(track) is not None}
        softkill_range = self._air_defense_loadout["softkill"]["range_nm"]
        candidates = []
        for asm in self.asms:
            track = by_target.get(asm.seq)
            effect = self._ecm_effect_against_asm(asm)
            if (asm.state != "LAUF" or track is None or track.range_nm is None
                    or track.range_nm > softkill_range or effect is None
                    or effect.effectiveness <= 0.0):
                continue
            candidates.append((track.range_nm, track.track_id, track))
        if candidates:
            self.launch_chaff_at(min(candidates, key=lambda item: item[:2])[2])

    def _update_enemy_torpedoes(self, dt: float) -> None:
        """Erzeugt und bewegt Feindtorpedos; Treffer werden als Schaden gebucht."""
        self._drain_enemy_torpedoes()
        boat = self._opfor
        attackers = {boat.sub.id} if boat is not None else set()
        mission_boat = boat_ai.boat(self)
        if mission_boat is not None and boat_missions.mode(self) == "convoy_attack":
            attackers.add(mission_boat.id)
        # The patrol boats of a frigate mission hunt merchants too (1.3.76).
        attackers.update(sub.id for sub in boat_ai.patrol_raiders(self))
        # Only the crewed boat's weapons, the AI boat's in the convoy attack
        # or a frigate mission's patrol boats may take another ship.
        merchants = ([ship for ship in self.civilians if not ship.sunk]
                     if attackers else [])
        for torpedo in self.enemy_torpedoes:
            torpedo.update(dt, self.ship, world=self.world,
                           seeker_candidates=self.nixies,
                           surface_targets=(merchants if torpedo.launch_platform_id in attackers
                                            else ()))
        for torpedo in self.enemy_torpedoes:
            if torpedo.state == "STRUCK":
                boat_missions.merchant_struck(self, torpedo.struck)
        for torpedo in self.enemy_torpedoes:
            if torpedo.state == "HIT":
                distance_m = max(1.0, math.hypot(torpedo.x - self.ship.x,
                                                 torpedo.y - self.ship.y) * 1852.0)
                # Shock factor sets the hole size relative to a 20 m burst.
                hit = self.damage.torpedo_hit(
                    impact=self._hull_impact(torpedo.x, torpedo.y),
                    hole_scale=config.clamp(20.0 / distance_m, 0.5, 3.0))
                self.casualties_hit(hit)
                self._emit_sound("explosion", at=(torpedo.x, torpedo.y))
                text = ", ".join(self.damage.compartments[k].name for k in hit)
                self.flash(message("runtime.hit.torpedo", compartments=text), 5.0)
                self.feed.add(self.world.format_time(), "schaden",
                              message("runtime.hit.damage", compartments=text))
        self.enemy_torpedoes = [t for t in self.enemy_torpedoes
                                if t.state == "RUN"]

    def _drain_asrocs(self) -> None:
        for ship in self.warships:
            pending, ship.pending_asroc = ship.pending_asroc, []
            room = max(0, MAX_ASROCS - len(self.asrocs))
            ship.pending_asroc = pending[room:]
            for row in pending[:room]:
                weapon = self.runtime_catalog.weapons[row["weapon_key"]]
                self.asroc_seq += 1
                self.asrocs.append(ASROC(
                    row["x"], row["y"], row["datum_x"], row["datum_y"],
                    self.asroc_seq, weapon.key,
                    self.runtime_catalog.runtime_bindings["helicopter_torpedo"],
                    weapon.maximum_speed_kn, weapon.engagement_range_nm[1],
                    ship.side, row["target_depth_m"], ship.id))

    def _update_asrocs(self, dt: float) -> None:
        survivors = []
        for weapon in self.asrocs:
            if weapon.update(dt, self.world):
                profile = self.runtime_catalog.torpedoes[
                    weapon.payload_profile_key]
                self.torpedo_seq += 1
                payload = Torpedo(
                    weapon.x, weapon.y, weapon.course, weapon.target_depth_m,
                    None, self.torpedo_seq, guidance_x=weapon.datum_x,
                    guidance_y=weapon.datum_y, profile=profile,
                    launch_origin="asroc",
                    launch_platform_id=weapon.launch_platform_id,
                    launch_weapon_key=weapon.weapon_key, time_since_launch=0.0)
                payload.break_wire()
                self.torpedoes.append(payload)
            elif weapon.state == "FLIGHT":
                survivors.append(weapon)
        self.asrocs = survivors
        # A launch decision consumes this substep before flight begins.
        self._drain_asrocs()

    def _hull_impact(self, x_nm: float, y_nm: float) -> tuple[float, float]:
        """Impact point in hull coordinates (bow/starboard positive, -1..1)."""
        dx, dy = (x_nm - self.ship.x) * 1852.0, (y_nm - self.ship.y) * 1852.0
        heading = math.radians(self.ship.course)
        forward = dx * math.sin(heading) - dy * math.cos(heading)
        starboard = dx * math.cos(heading) + dy * math.sin(heading)
        half_length = self.ship.hull_spec.length_m / 2.0
        half_beam = self.ship.hull_spec.beam_m / 2.0
        if math.hypot(forward, starboard) < 1e-6:
            return 0.0, 0.0
        # Project onto the hull outline along the approach direction.
        scale = max(abs(forward) / half_length, abs(starboard) / half_beam, 1.0)
        return (config.clamp(forward / scale / half_length, -1.0, 1.0),
                config.clamp(starboard / scale / half_beam, -1.0, 1.0))

    def _incoming_hit_zone(self, torpedo) -> str:
        """Naehert die getroffene Schiffszone aus der Angriffsrichtung an."""
        source_bearing = (torpedo.course + 180.0) % 360.0
        relative = config.angle_diff_deg(source_bearing, self.ship.course)
        if abs(relative) <= 45.0:
            return "bow"
        if abs(relative) >= 135.0:
            return "stern"
        return "starboard" if relative > 0.0 else "port"

    def _sub_hears_torpedo(self, sub, torpedo, distance_nm: float) -> bool:
        """Passive sonar equation for a running torpedo heard by a boat.

        The figure of merit reproduces TORP_RUNNING_NOISE_RANGE_NM for a
        quiet boat and a torpedo at cruise speed; propagation, ambient noise,
        the boat's own noise and the torpedo's speed-dependent level decide."""
        if distance_nm > 3.0 * config.TORP_RUNNING_NOISE_RANGE_NM:
            return False
        frequency = torpedo_dyn.RUNNING_NOISE_BAND_HZ
        excess = sonar_propagation.ray_excess_db(
            self.world, sub.x, sub.y, max(sub.depth, 1.0), torpedo.x, torpedo.y,
            max(torpedo.depth, 1.0), frequency)
        absorption = sonar_equation.francois_garrison_db_per_km(frequency)
        terms = sonar_equation.passive_terms(
            frequency_hz=frequency, distance_nm=max(distance_nm, 0.01),
            target_bonus=10.0 ** (torpedo.source_level_offset_db() / 20.0),
            excess_path_loss_db=(0.0 if excess is None else excess
                                 - sonar_propagation.ray_reference_excess_db(
                                     config.TORP_RUNNING_NOISE_RANGE_NM, frequency))
            # Absorption is part of the reference-range figure of merit too.
            - absorption * config.TORP_RUNNING_NOISE_RANGE_NM * 1.852,
            absorption_db_per_km=absorption,
            legacy_absorption_db=0.0,
            own_range_factor=max(0.2, 1.0 - 0.8 * sub.noise_level()),
            array_range_factor=(config.TORP_RUNNING_NOISE_RANGE_NM
                                / config.SONAR_PASSIVE_BASE_NM),
            sea_state=float(getattr(self.world, "effective_sea_state",
                                    self.world.sea_state)),
            rain=float(getattr(self.world, "rain_intensity", 0.0)),
            shipping_contacts=self.sonar.shipping_contacts)
        return terms.signal_excess_db > 0.0

    def _update_player_torpedoes(self, dt: float) -> None:
        """Bewegt eigene Torpedos und verarbeitet Treffer/Fehlkontakte."""
        for sub in self.subs:
            if (sub.sunk or sub.state == "SINKING"
                    or sub.memory["last_torpedo_age"] < config.SUB_EVADE_DURATION_S):
                continue
            for torpedo in self.torpedoes:
                if torpedo.state != "RUN":
                    continue
                dist = math.hypot(torpedo.x - sub.x, torpedo.y - sub.y)
                if (dist <= config.TORP_HOME_RANGE_NM
                        and not self.world.sonar_path_blocked(
                            torpedo.x, torpedo.y, torpedo.depth,
                            sub.x, sub.y, sub.depth)):
                    sub.alert_torpedo(source=(torpedo.x, torpedo.y))
                    break
                # W2: graduated passive notice of a running torpedo's own
                # noise, between pure terminal homing and the loud one-time
                # launch transient - additive, does not replace either.
                if (self._sub_hears_torpedo(sub, torpedo, dist)
                        and not self.world.sonar_path_blocked(
                            torpedo.x, torpedo.y, torpedo.depth,
                            sub.x, sub.y, sub.depth)):
                    sub.alert_torpedo(source=(torpedo.x, torpedo.y))
                    break
        for torpedo in self.torpedoes:
            target_id = getattr(torpedo.target, "id", None)
            contact = self.sonar.contacts.get(target_id)
            solution_fresh = self._contact_range_fresh(contact)
            if (solution_fresh and contact.observed_x is not None
                    and contact.observed_y is not None):
                torpedo.wire_update(contact.observed_x, contact.observed_y)
            if torpedo.launch_origin == "frigate":
                torpedo.wire_tension_update(dt, self.ship.speed,
                                            self.ship.yaw_rate)
            torpedo.update(dt, seeker_candidates=(
                [s for s in self.subs if not s.sunk]
                + [d for d in self.decoys if not d.dead]
                + [w for w in self.warships if not w.sunk]
                + [a for a in self.animals if not a.dead]
                + [c for c in self.civilians if not c.sunk]), world=self.world,
                collision_candidates=self.civilians)
        alive = []
        for torpedo in self.torpedoes:
            if torpedo.state == "RUN":
                alive.append(torpedo)
                continue
            if torpedo.state != "HIT":
                continue
            self._emit_sound("explosion", at=(torpedo.x, torpedo.y))
            if (isinstance(torpedo.target, SurfaceShip)
                    and torpedo.target.side != "hostile"):
                torpedo.target.sunk = True
                self.incident = True
                self.live_traffic.mark_ship_destroyed(
                    getattr(torpedo.target, "live_mmsi", None))
                self.audio.play_alert("danger")
                self.flash(message("runtime.incident"), 6.0)
                self.feed.add(self.world.format_time(), "waffen",
                              message("runtime.incident"))
                continue
            contact = self.sonar.contacts.get(getattr(torpedo.target, "id", None))
            if contact is not None and self.sim_t - contact.last_seen < config.SONAR_CONTACT_LOST_S:
                self.flash(message("runtime.hit.contact",
                                   contact=contact.id), 3.0)
                self.feed.add(self.world.format_time(), "waffen",
                              message("runtime.hit.contact", contact=contact.id))
            if getattr(torpedo.target, "hostile", False):
                if (torpedo.target.sunk
                        and not torpedo.target.sunk_score_awarded):
                    torpedo.target.sunk_score_awarded = True
                    self.score += config.SCORE_SUNK
                    self._report_breakup_noise(
                        torpedo.target.x, torpedo.target.y,
                        getattr(torpedo.target, "depth", 0.0),
                        torpedo.target.id)
        self.torpedoes = alive

    def _report_breakup_noise(self, x: float, y: float, depth: float,
                              key: int) -> None:
        """A sinking hull is heard, not identified: bearing only, no class.

        Kill assessment stays with the operator; the score is shown only in
        the mission debrief.
        """
        if self._opfor is not None:
            opfor.hear_breakup(self, self._opfor, x, y, depth, key)
        if (self.damage.station_down("sonar")
                or math.hypot(x - self.ship.x, y - self.ship.y)
                > config.TORP_TRANSIENT_HEAR_NM
                or self.world.sonar_path_blocked(x, y, depth,
                                                 self.ship.x, self.ship.y, 5.0)):
            return
        bearing = threat_cue.measured_cue_bearing(
            math.degrees(math.atan2(x - self.ship.x, -(y - self.ship.y))) % 360.0,
            self.seed, 500_000 + int(key), self.sim_t)
        notice = message("runtime.breakup_noise", bearing=f"{bearing:05.1f}")
        self.flash(notice, 4.0)
        self.feed.add(self.world.format_time(), "sonar", notice)

    def _update_helicopter_audio(self, dt: float, targets) -> None:
        """Synthesize only presently measured helicopter channels, at 4 Hz."""
        if (self.station is not Station.HELICOPTER
                and not self.commander.station_leased(Station.HELICOPTER)):
            return
        if not self.helicopter_audio_ready():
            return
        self._helo_receiver_timer += dt
        if self._helo_receiver_timer + 1e-9 < self.helo_receiver.block_s:
            return
        seq = (int(self.helo_listen_source[2:])
               if self.helo_listen_source.startswith("SB") else None)
        reports = []
        for target in targets:
            contact = self.sonar.contacts.get(target.id)
            if contact is None:
                continue
            if seq is None:
                if (not self.helo.dip_available or contact.dip_last_seen is None
                        or not 0 <= self.sim_t - contact.dip_last_seen < 2.0):
                    continue
                bearing = contact.dip_bearing
                quality = contact.quality
            else:
                row = contact.buoy_reports.get(seq)
                if row is None or not 0 <= self.sim_t - row["measured_at"] < 2.0:
                    continue
                bearing = row["bearing"]
                quality = row["quality"]
            if bearing is None:
                continue
            source = dict(bearing=bearing, level=quality,
                          lines=target.lofar_lines(self.sim_t),
                          seed=getattr(target, "sensor_seed", target.id))
            broadband = getattr(target, "broadband", lambda: {})()
            if isinstance(broadband, dict) and broadband.get("level", 0) > 0:
                source["broadband"] = broadband
            reports.append((contact, source))
        selected = next((row for contact, row in reports
                         if contact is self.selected_contact), None)
        listen_bearing = (self.helo_listen_bearing if self.helo_listen_bearing is not None
                          else (selected or reports[0][1])["bearing"] if reports else 0.0)
        while self._helo_receiver_timer + 1e-9 >= self.helo_receiver.block_s:
            self._helo_receiver_timer = max(0.0, self._helo_receiver_timer
                                            - self.helo_receiver.block_s)
            self.helo_receiver.update(
                [row for _, row in reports], listen_bearing, 18.0,
                .2 if seq is None else .05,
                getattr(self.world, "effective_sea_state", self.world.sea_state),
                0.0)
            self.helo_spectra.append(tuple(self.helo_receiver.spectrum))
            del self.helo_spectra[:-128]
            self.helo_broadband_history.append(tuple(self.helo_receiver.broadband))
            del self.helo_broadband_history[:-128]
            self.helo_demon_history.append(tuple(self.helo_receiver.demon_spectrum))
            del self.helo_demon_history[:-128]

    def _update_sensors(self, dt: float) -> None:
        """Aktualisiert Sonar-Kontakte, TMA und Kontaktfeed."""
        if self.target is not None and self.target.target_id not in self.sonar.contacts:
            self.target = None
        if (self.selected_contact is not None
                and self.selected_contact.target_id not in self.sonar.contacts):
            self.selected_contact = None
        prev_cts = {c.id for c in self.sonar.contacts.values()}
        targets = self._sonar_targets()
        self._update_mad(targets, dt)
        if self.damage.station_down("sonar"):
            if self.sonar.lofar_history:
                self.sonar.reset_listening_history()
                self.sonar.broadband_history.clear()
                self.sonar.history_times.clear()
                self.sonar.broadband_long_history.clear()
                self.sonar.broadband_long_times.clear()
                self.sonar._broadband_long_accumulator.clear()
            self.sonar.update_dipping_passive(
                dt, self.sim_t, self.helo, targets, self.world,
                range_factor=self._sonar_range_factor())
            self._update_helicopter_audio(dt, targets)
            return
        focus = (self._find_target(self.selected_contact.target_id)
                 if self.selected_contact else None)
        self.sonar.shipping_contacts = self._shipping_noise_contacts()
        self.sonar.update(dt, self.sim_t, self.ship, targets, self.world,
                          range_factor=self._sonar_range_factor(),
                          mode=self.sonar_mode, buoys=self.heard_buoys(),
                           focus_tgt=focus,
                           own_cavitation=1.0 if self.ship.cavitating else 0.0,
                           advance_mechanics=False)
        self.sonar.update_dipping_passive(
            dt, self.sim_t, self.helo, targets, self.world,
            range_factor=self._sonar_range_factor())
        self._update_helicopter_audio(dt, targets)
        for contact in self.sonar.active_contacts():
            bearing = (contact.passive_bearing
                       if contact.passive_bearing is not None else contact.bearing)
            range_nm = None
            active_fixes = contact.active_fixes(self.sim_t)
            if contact.observed_x is not None and contact.observed_y is not None:
                dx = contact.observed_x - self.ship.x
                dy = contact.observed_y - self.ship.y
                bearing = math.degrees(math.atan2(dx, -dy)) % 360.0
                range_nm = math.hypot(dx, dy)
            # The domain symbol follows the operator's classification; the
            # contact's underlying entity type is never published.
            observed_kind = SONAR_CLASS_KINDS.get(contact.player_class, "UNKNOWN")
            self.air_picture.observe(
                track_id=f"U-{contact.target_id}",
                kind=observed_kind,
                target_id=contact.target_id,
                source=(f"SONAR-{max(active_fixes, key=lambda fix: (fix['fixed_at'], fix['source']))['source']}"
                        if active_fixes
                        else contact.passive_source),
                bearing=bearing, range_nm=range_nm,
                observer_x=self.ship.x, observer_y=self.ship.y,
                course=contact.tma_course,
                quality=max(contact.quality, contact.confidence),
                now=contact.last_seen, label=f"K{contact.id}",
                position_time=contact.range_seen,
                bearing_uncertainty_deg=contact.bearing_uncertainty_deg)
        while self.sonar.echo_events:
            echo = self.sonar.echo_events.pop(0)
            self._emit_echo(echo)
            if echo["contact_id"] == 0:
                self.feed.add(self.world.format_time(), "sonar",
                              message("runtime.echo.unassociated",
                                      bearing=f"{echo['bearing']:05.1f}",
                                      range=f"{echo['range_nm']:.1f}"))
                continue
            self.feed.add(self.world.format_time(), "sonar",
                          message("runtime.echo.feed", contact=echo["contact_id"],
                                  bearing=f"{echo['bearing']:05.1f}",
                                  range=f"{echo['range_nm']:.1f}",
                                  depth=f"{echo['depth_m']:.0f}"))
            self.flash(message("runtime.echo.flash", contact=echo["contact_id"],
                               range=f"{echo['range_nm']:.1f}"), 2.0)
        for contact in self.sonar.active_contacts():
            if contact.id not in prev_cts:
                key = ("runtime.contact.new_range" if contact.range_est
                       else "runtime.contact.new_bearing")
                self.feed.add(self.world.format_time(), "sonar",
                              message(key,
                                      contact=contact.id,
                                      bearing=f"{contact.bearing:4.0f}",
                                      range=(f"{contact.range_est:.1f}"
                                             if contact.range_est else ""),
                                      origin=contact.origin))
        self._update_torpedo_cues()

    def current_torpedo_cues(self) -> list:
        """Torpedo intercepts audible right now, as detached measurements.

        A pure function of the saved torpedo state and simulation time: a
        launch transient or HF seeker pulses on a noisy bearing. The weapon's
        type or identity is never published; only the intercept is.
        """
        if self.damage.station_down("sonar"):
            return []
        cues = []
        for torpedo in self.enemy_torpedoes:
            if torpedo.state != "RUN":
                continue
            distance = math.hypot(torpedo.x - self.ship.x, torpedo.y - self.ship.y)
            kind = threat_cue.torpedo_cue_kind(
                torpedo.time_since_launch, torpedo.terminal_active, distance)
            if kind is None or self.world.sonar_path_blocked(
                    torpedo.x, torpedo.y, torpedo.depth,
                    self.ship.x, self.ship.y, 5.0):
                continue
            true_bearing = math.degrees(math.atan2(
                torpedo.x - self.ship.x, -(torpedo.y - self.ship.y))) % 360.0
            key = (int(torpedo.launch_platform_id or 0) * 1000
                   + int(getattr(torpedo, "idx", 0)))
            cues.append({"kind": kind, "t": self.sim_t, "owner": torpedo,
                         "report": kind, "serial": id(torpedo),
                         "bearing": threat_cue.measured_cue_bearing(
                             true_bearing, self.seed, key, self.sim_t)})
        cues += self._tube_flood_cues()
        return cues

    def _tube_flood_cues(self) -> list:
        """Tube flooding / outer-door transients audible right now.

        Heard only within ``TORP_FLOOD_HEAR_NM`` (slow, quiet flooding
        ``TORP_FLOOD_QUIET_HEAR_NM``), shrunk by the frigate's own noise, sea
        state and sonar damage, and never through land. Measurement only: a
        bearing and the fact of a transient, no identity."""
        own = (self.ship.passive_sonar_range_nm(
            1.0, int(getattr(self.world, "effective_sea_state", self.world.sea_state)))
            / config.SONAR_PASSIVE_BASE_NM) * self._sonar_range_factor()
        cues = []
        for sub in self.subs:
            if sub.sunk or sub.flood_noise_left <= 0.0:
                continue
            reach = own * (config.TORP_FLOOD_QUIET_HEAR_NM if sub.flood_quiet
                           else config.TORP_FLOOD_HEAR_NM)
            if (math.hypot(sub.x - self.ship.x, sub.y - self.ship.y) > reach
                    or self.world.sonar_path_blocked(
                        sub.x, sub.y, sub.depth, self.ship.x, self.ship.y, 5.0)):
                continue
            true_bearing = math.degrees(math.atan2(
                sub.x - self.ship.x, -(sub.y - self.ship.y))) % 360.0
            key = (config.SUB_FLOOD_SEQ_MAX * (int(sub.id) + 1) + sub.flood_seq) * 1000 + 999
            cues.append({"kind": "flood", "t": self.sim_t, "owner": sub,
                         "report": f"flood:{sub.flood_seq}",
                         "serial": ("flood", id(sub)),
                         "bearing": threat_cue.measured_cue_bearing(
                             true_bearing, self.seed, key, self.sim_t)})
        return cues

    def _update_torpedo_cues(self) -> None:
        """Announce each intercept once and hold it briefly on the alarm board."""
        self.torpedo_cues = [cue for cue in self.torpedo_cues
                             if self.sim_t - cue["t"] <= config.TORP_CUE_HOLD_S]
        for cue in self.current_torpedo_cues():
            owner, report = cue.pop("owner"), cue.pop("report")
            reported = self._torpedo_cues_reported.setdefault(owner, set())
            self.torpedo_cues = [held for held in self.torpedo_cues
                                 if held["serial"] != cue["serial"]]
            self.torpedo_cues.append(cue)
            if report in reported:
                continue
            reported.add(report)
            notice = message(f"runtime.torpedo_cue.{cue['kind']}",
                             bearing=f"{cue['bearing']:05.1f}")
            self.flash(notice, 4.0)
            self.audio.play_alert("danger")
            self.feed.add(self.world.format_time(), "sonar", notice)

    def torpedo_warnings(self, held: bool = True) -> list:
        """Detached torpedo alarms: held intercepts plus operator-classified
        TORPEDO contacts. `held=False` uses only intercepts audible now."""
        cues = (self.torpedo_cues if held else self.current_torpedo_cues())
        rows = [{"source": cue["kind"], "bearing": cue["bearing"],
                 "age_s": self.sim_t - cue["t"], "contact": None}
                for cue in cues]
        rows += [{"source": "classified", "bearing": contact.bearing,
                  "age_s": self.sim_t - contact.last_seen, "contact": contact.id}
                 for contact in self.sonar.active_contacts()
                 if contact.player_class == "TORPEDO"]
        return sorted(rows, key=lambda row: (row["age_s"], row["bearing"]))

    def _update_damage_and_mission(self, dt: float) -> None:
        """Fortschritt von Schaden, Flugverkehr und Missionszielen."""
        self._update_crew(dt)
        self.damage.update(dt, draft_m=self.ship.dynamic_draft_m())
        self.flights.update(dt, world=self.world,
                            near=(self.ship.x, self.ship.y))
        self._run_mission_events()
        self._update_tasking(dt)
        self._update_incidents(dt)
        self._update_hq_reports()
        self._check_mission_end()
        self._update_training()

    def _update_sim(self, dt: float) -> None:
        self.sim_t += dt
        self.mission_time += dt
        self._mission_time_warning()
        self._update_navigation(dt)
        self._update_asw_stores(dt)
        self.sonar.advance_mechanics(dt, self.sim_t, self.ship)
        if self.sonar.tow_state != self._last_tow_state:
            keys = {TowState.STREAMED: "status.tas.streamed",
                    TowState.STOWED: "status.tas.stowed",
                    TowState.FAULT: "status.tas.fault"}
            key = keys.get(self.sonar.tow_state)
            if key is not None:
                notice = message(key)
                self.flash(notice, 3.0)
                self.feed.add(self.world.format_time(), "sonar", notice)
            self._last_tow_state = self.sonar.tow_state
        if self._opfor is not None:
            if self._opfor.sub not in self.subs:
                self._opfor = None
                self._opfor_hold_s = 0.0
            else:
                opfor.advance_mechanics(self, self._opfor, dt)
                self._opfor_hold_s = max(0.0, self._opfor_hold_s - dt)
        sweep = config.RADAR_SWEEP_DEG_PER_S * dt
        self.radar_scan_phase = (self.radar_scan_phase + sweep) % 360.0
        self.radar_scan_pending_deg = min(360.0, self.radar_scan_pending_deg + sweep)
        self._sensor_acc += dt
        publish_picture = self._sensor_acc >= .25
        if publish_picture:
            self._update_platform_sensors(self._sensor_acc)
        self._update_underwater_entities(dt)
        self._update_aviation(dt)
        self._esm_acc += dt
        self._radio_acc += dt
        self._slow_acc += dt
        self._update_raiders(dt, publish_picture=publish_picture)
        self._update_air_defense(dt, publish_picture=publish_picture)
        # M13: Wetter-Hinweise per Teletype
        self.hq_timer -= dt
        if self.hq_timer <= 0.0:
            self.hq_timer = config.WEATHER_BULLETIN_PERIOD_S
            weather = self.world.weather_values()
            self.hq_msg(message(
                "runtime.hq.profile", sea_state=f"{weather['sea_state']:.1f}",
                depth=f"{self.world.thermocline_depth_m(self.ship.x, self.ship.y):.0f}",
                tide=f"{self.world.tide_m(self.ship.x, self.ship.y):+.1f}",
                sst=f"{self.world.ocean.sea_surface_temperature_c(self.world.hour):.1f}",
                wind_from=f"{weather['wind_from_deg']:.0f}",
                wind_speed=f"{weather['wind_speed_kn']:.0f}",
                rain=f"{weather['rain_intensity']:.0%}",
                visibility=f"{weather['visibility_nm']:.1f}"))
        self._update_enemy_torpedoes(dt)
        self._update_player_torpedoes(dt)
        # A payload entering the water starts moving on the next substep; the
        # current substep was already consumed by ASROC flight.
        self._update_asrocs(dt)
        self._update_depth_charges(dt)
        if self._sensor_acc >= .25:
            sensor_dt = self._sensor_acc
            self._sensor_acc = 0.0
            self._update_sensors(sensor_dt)
            if self._opfor is not None:
                opfor.update_sonar(self, self._opfor, sensor_dt)
                opfor.update_wires(self, self._opfor, sensor_dt)
                opfor.update_crew(self, self._opfor)
        if self._esm_acc >= .5:
            self._esm_acc = 0.0
            self._update_esm_picture()
        if self._radio_acc >= .5:
            self._radio_acc = 0.0
            self._update_radio_picture()
        self._update_opz_picture()
        if self._slow_acc >= .5:
            slow_dt = self._slow_acc
            self._slow_acc = 0.0
            self._update_damage_and_mission(slow_dt)
        # Automation consumes observations published in this substep; actuator
        # changes take effect on the following physics substep.
        self.autocrew.update(self)
        # With nobody on the frigate, the hunters crew its unleased stations;
        # with the crew assist the boat's autocrew mans its free stations.
        hunter.update(self, dt)
        boat_autocrew.update(self, dt)
        # An uncrewed mission boat fires and reports on its own cadence.
        boat_ai.update(self, dt)
        self._record_simlog_state(dt)

    def _mission_time_warning(self) -> None:
        """Warn before a deadline so the player can react instead of guessing."""
        remaining = self.mission.remaining_s(self.mission_time)
        for threshold in (300.0, 120.0, 60.0):
            if remaining <= threshold and threshold not in self._mission_warnings:
                self._mission_warnings.add(threshold)
                minutes = int(threshold // 60)
                amount = minutes if minutes else 60
                suffix = "minutes" if minutes else "seconds"
                # Running out the clock wins a survive mission: announce the
                # remaining time as progress, not as a deadline.
                prefix = ("runtime.survive." if self.mission.win_mode in ("survive", "protect")
                          else "runtime.deadline.")
                self.flash(message(prefix + "warning_" + suffix,
                                   amount=amount), 4.0)
                self.feed.add(self.world.format_time(), "mission",
                              message(prefix + "feed_" + suffix,
                                      amount=amount))

    # --- M6: Missions-Endbedingungen & Score ---

    def _torus_dist(self, x1, y1, x2, y2) -> float:
        """Legacy name; the generated world has hard, non-toroidal edges."""
        return math.hypot(x1 - x2, y1 - y2)

    def _check_mission_end(self) -> None:
        if self.mission_result is not None:
            return
        m = self.mission
        if self.damage.ship_sunk:
            self._end_mission(False, message("end.reason.frigate_sunk"))
            return
        if self.incident:
            self._end_mission(False, message("end.reason.incident"))
            return
        if boat_missions.check(self):
            return
        definition = self.custom_mission_definition
        if definition is not None and m.win_mode in ("protect", "reach"):
            objective = definition["objective"]
            if m.win_mode == "protect":
                for unit_id in objective["target_ids"]:
                    entity = self.mission_entity(unit_id)
                    if entity is None or getattr(entity, "sunk", False) \
                            or getattr(entity, "dead", False):
                        self._end_mission(False, message("end.reason.protected_lost",
                                                         unit=raw_text(str(unit_id))))
                        return
                if self.mission_time >= m.time_limit_s:
                    self._end_mission(True, message("end.reason.protected_survived"))
                return
            point = objective["reach"]
            if math.hypot(self.ship.x - float(point["x"]),
                          self.ship.y - float(point["y"])) <= float(point["radius_nm"]):
                self._end_mission(True, message("end.reason.point_reached"))
            elif self.mission_time >= m.time_limit_s:
                self._end_mission(False, message("end.reason.time_limit"))
            return
        if m.win_mode == "sink":
            targets = [sub for sub in self.subs if sub.side == "hostile"]
            for sub in targets:
                if not sub.sunk and \
                        self._torus_dist(sub.x, sub.y, *sub.start_pos) > config.MISSION_ESCAPE_RADIUS_NM:
                    self._end_mission(False, message("end.reason.sub_escaped",
                                                     contact=sub.id))
                    return
            if all(sub.sunk for sub in targets):
                self._end_mission(True, message("end.reason.targets_sunk"))
                return
            if self.mission_time >= m.time_limit_s:
                self._end_mission(False, message("end.reason.time_limit"))
                return
        else:
            if self.mission_time >= m.time_limit_s:
                self._end_mission(True, message("end.reason.convoy_survived"))

    def _end_mission(self, win: bool, reason: object) -> None:
        self.mission_result = "SIEG" if win else "VERLOREN"
        self.result_reason = reason
        self.game_over = True
        self._finish_debrief()
        self.input_mode = None
        self.input_buffer = ""
        self._clear_controls()
        if win:
            bonus = int(self.mission.remaining_s(self.mission_time)
                        / self.mission.time_limit_s * config.SCORE_TIME_BONUS_MAX)
            self.score += bonus + config.SCORE_AMMO_BONUS * self.torpedo_count
            if not self.incident:
                self.score += config.SCORE_CIVIL_BONUS
        # Contact reports that were right count now (never during the mission).
        self.score += self._score_hq_reports()
        # The realism level scales the mission's score (Beginner less,
        # Realistic more).
        self.score = int(round(self.score * self.level_score_factor()))
        self.announce(message("runtime.mission.won" if win
                              else "runtime.mission.lost"), "mission", 10.0)
        boat = self._opfor
        if boat is not None:
            # The crewed boat's own log: the mission from the boat's side.
            result = boat_debrief.outcome(self, boat)
            if result != "over":
                boat.notice(self.sim_t, "mission", message(
                    "uboot.event.mission_lost" if result == "lost"
                    else "uboot.event.mission_won"), stamp=self.world.format_time())
        self._campaign_mission_ended()
        self._logbook_mission_ended()

    # --- M6: Speichern / Laden ---

    MAX_SAVED_ASMS = MAX_SAVED_ASMS
    MAX_SAVED_PLAYER_TORPEDOES = MAX_SAVED_PLAYER_TORPEDOES
    MAX_SAVED_ESSMS = MAX_SAVED_ESSMS

    @staticmethod
    def _smooth_sensor_noise(seed: int, now: float,
                             period_s: float) -> float:
        """Deterministic, smoothly correlated unit noise on simulation time."""
        import random
        scaled = now / period_s
        epoch = math.floor(scaled)
        fraction = scaled - epoch
        blend = fraction * fraction * (3.0 - 2.0 * fraction)
        first = random.Random(seed + epoch * 104729).uniform(-1.0, 1.0)
        second = random.Random(seed + (epoch + 1) * 104729).uniform(-1.0, 1.0)
        return first + (second - first) * blend

    def _observation_key(self, namespace: str, identity: object) -> str:
        value = f"{self.seed}:{namespace}:{identity}".encode("utf-8")
        return hashlib.blake2b(value, digest_size=8).hexdigest().upper()

    def lunar_age_days(self) -> float:
        """Lunar age: seeded per world, advancing with simulation time."""
        return (detrand.u01(self.seed, "lunar-age") * visual_physics.SYNODIC_MONTH_D
                + self.sim_t / 86400.0) % visual_physics.SYNODIC_MONTH_D

    def moon_illumination(self) -> float:
        """Illuminated lunar fraction."""
        return visual_physics.moon_illumination(self.lunar_age_days())

    def _reset_lookout_reports(self) -> None:
        """Transient bridge-lookout report log (like the feed, never saved)."""
        self.lookout_reports: list[dict] = []
        self._lookout_land_seen: set[int] = set()
        self._lookout_land_epoch: int | None = None
        # Navigation lights the lookout made out, per track (never saved; the
        # next observation restores them).
        self._lookout_lights: dict[str, tuple] = {}
        # What the lookout last called out about each contact's lights:
        # (aspect, work, time); transient like the report log.
        self._lookout_lights_called: dict[str, tuple] = {}
        # Elevation (deg above the sea horizon) of each aircraft he sees.
        self._lookout_elevation: dict[str, tuple] = {}
        # Angle on the bow he judges of each silhouette he made out.
        self._lookout_aspect: dict[str, tuple] = {}
        phone_lookout.reset(self)

    def _lookout_environment(self) -> dict:
        return dict(
            visibility_nm=getattr(self.world, "visibility_nm",
                                  config.WEATHER_VISIBILITY_MAX_NM),
            night=self.world.is_night(), illumination=self.moon_illumination(),
            sea_state=getattr(self.world, "effective_sea_state", self.world.sea_state))

    def _lookout_observe(self, actor, namespace: str, kind: str,
                         seed: int, altitude_m: float | None = None,
                         classes: tuple | None = None, lit: bool = False,
                         strength: float = 1.0) -> None:
        import random

        dx, dy = actor.x - self.ship.x, actor.y - self.ship.y
        distance = math.hypot(dx, dy)
        environment = self._lookout_environment()
        # A tired lookout needs more contrast (crew watch, 1.0 when fresh);
        # ``strength`` scales the target's own contrast (a mast's feather).
        alert = self.crew_effect() * strength
        margin = alert * LOOKOUT_MODEL.margin(kind, distance, altitude_m=altitude_m,
                                              **environment)
        bearing = math.degrees(math.atan2(dx, -dy)) % 360.0
        lights = None
        if lit and kind == "FLG":
            lights = nav_lights.aircraft_code(actor.course, bearing, distance,
                                              environment["visibility_nm"])
        elif lit:
            lights = nav_lights.code(actor.course, bearing, distance, hull_length_m(actor),
                                     environment["visibility_nm"],
                                     nav_lights.duty(getattr(actor, "profile", None)))
        # Navigation lights in range are seen even where the dark hull is not
        # (a bare sighting; the class still needs the silhouette).
        if lights is not None:
            margin = max(margin, 1.0)
        if (margin < 1.0 or self.world.land_blocks_line(
                self.ship.x, self.ship.y, actor.x, actor.y)):
            return
        epoch = math.floor((self.sim_t + 1e-9) / config.LOOKOUT_EPOCH_S)
        rng = random.Random(seed * 65537 + epoch * 104729 + 0x4C4F4F4B)
        measured_bearing = (bearing + rng.uniform(
            -config.LOOKOUT_BEARING_ERR_DEG,
            config.LOOKOUT_BEARING_ERR_DEG)) % 360.0
        measured_range = max(0.0, distance * (1.0 + rng.uniform(
            -config.LOOKOUT_RANGE_ERR_FRAC, config.LOOKOUT_RANGE_ERR_FRAC)))
        # Contrast margin: just above threshold is a doubtful sighting.
        quality = config.clamp(.5 + .45 * (1.0 - 1.0 / margin), .5, .95)
        identity = getattr(actor, "id", getattr(actor, "seq", 0))
        track_id = "L-" + self._observation_key(namespace, identity)
        # Johnson criteria: the class needs a finer resolved silhouette than
        # the sighting, the type finer still.  A class once made out is held
        # while the lookout keeps the contact.
        level = lookout_id.DETECTED
        recognized = identified = type_key = None
        if classes is not None:
            recognized, identified, type_key = classes
            if LOOKOUT_MODEL.margin(
                    kind, distance, altitude_m=altitude_m,
                    detail=lookout_id.RECOGNIZE_CYCLES / lookout_id.CLASS_SIZE[recognized],
                    **environment) * alert >= 1.0:
                level = lookout_id.RECOGNIZED
                if LOOKOUT_MODEL.margin(
                        kind, distance, altitude_m=altitude_m,
                        detail=lookout_id.IDENTIFY_CYCLES / lookout_id.CLASS_SIZE[identified],
                        **environment) * alert >= 1.0:
                    level = lookout_id.IDENTIFIED
        previous = self.air_picture.current(track_id, self.sim_t)
        called = previous is not None and previous.source == "LOOKOUT"
        previous_level = lookout_id.decode(previous.label)[0] if called else -1
        eye = self.lookout_eye.get(track_id) if self.lookout_phone else None
        if eye is not None:
            previous_level = max(previous_level, eye.level)
        level = max(level, previous_level)
        label = lookout_id.encode(level, recognized, identified, type_key)
        # A bare detection only says what the eye sees: something on the
        # surface or a wake. Submarine/torpedo domains need recognition.
        # A mast or feather made out as a periscope is a submarine.
        if kind == "MAST":
            published_kind = "SUB" if level >= lookout_id.RECOGNIZED else "SURFACE"
        else:
            published_kind = (kind if level >= lookout_id.RECOGNIZED
                              or kind in ("SURFACE", "FLG")
                              else "SURFACE" if kind == "SUB" else "UNKNOWN")
        if lights is None:
            self._lookout_lights.pop(track_id, None)
        else:
            self._lookout_lights[track_id] = (lights, self.sim_t)
        aspect = getattr(self, "_lookout_aspect", None)
        if aspect is not None:
            course = getattr(actor, "course", None)
            if level >= lookout_id.RECOGNIZED and course is not None and kind != "MAST":
                # The eye sees the real ship; the type is the watch's call.
                aspect[track_id] = (lookout_id.angle_on_bow(course, bearing), self.sim_t,
                                    unit_variants.entity_model(actor))
            else:
                aspect.pop(track_id, None)
        if kind == "FLG":
            self._lookout_elevation[track_id] = (max(-5.0, visual_physics.elevation_deg(
                altitude_m or 0.0, distance, visual_physics.LOOKOUT_EYE_HEIGHT_M)), self.sim_t)
        if self.lookout_phone and not called:
            # A phone holds the lookout: the bridge hears only what it calls.
            phone_lookout.see(self, track_id, published_kind, label, level,
                              measured_bearing, measured_range, quality)
            return
        track = self.air_picture.observe(
            track_id=track_id,
            kind=published_kind, target_id=0, source="LOOKOUT",
            bearing=measured_bearing, range_nm=measured_range,
            observer_x=self.ship.x, observer_y=self.ship.y, course=None,
            quality=quality, now=self.sim_t, label=label,
            bearing_uncertainty_deg=(config.LOOKOUT_BEARING_ERR_DEG
                                     / math.sqrt(3.0)))
        # One report per new sighting and per step up in recognition; a call
        # inside the same measurement epoch leaves the track unchanged.
        if level > previous_level and track.label == label:
            self._lookout_report(kind, label, measured_bearing, measured_range)
        if lights is not None:
            self._lookout_call_lights(track_id, lights, measured_bearing, measured_range)

    def _lookout_call_lights(self, track_id: str, lights: str, bearing: float,
                             range_nm: float) -> None:
        """Call a contact's lights when they first show, or when what they
        tell (aspect, work) changes; a vessel showing both side lights is
        heading for the ship and is called aloud."""
        _seen, aspect, work = nav_lights.describe(lights)
        called = getattr(self, "_lookout_lights_called", None)
        if called is None:
            called = self._lookout_lights_called = {}
        previous = called.get(track_id)
        if previous is not None and (previous[:2] == (aspect, work)
                                     or self.sim_t - previous[2] < config.LOOKOUT_LIGHTS_REPORT_S):
            return
        called[track_id] = (aspect, work, self.sim_t)
        report = dict(t=self.sim_t, stamp=self.world.format_time(), kind="LIGHTS",
                      level=lookout_id.DETECTED, code=None, type_name=None,
                      lights=lights, bearing=bearing % 360.0, range_nm=range_nm)
        self.lookout_reports.append(report)
        del self.lookout_reports[:-config.LOOKOUT_REPORTS_MAX]
        text = self.lookout_report_text(report)
        if aspect == "head_on":
            self.announce(text, "ausguck", 4.0)
        else:
            self.feed.add(self.world.format_time(), "ausguck", text)

    def _lookout_report(self, kind: str, label: str, bearing: float,
                        range_nm: float, called: str | None = None) -> None:
        level, code, type_key = lookout_id.decode(label)
        report = dict(t=self.sim_t, stamp=self.world.format_time(), kind=kind,
                      level=level, code=code,
                      type_name=self.lookout_type_name(type_key),
                      bearing=bearing % 360.0, range_nm=range_nm)
        self.lookout_reports.append(report)
        del self.lookout_reports[:-config.LOOKOUT_REPORTS_MAX]
        if called is not None:
            # The phone lookout's own call: always announced and said aloud.
            self.announce(phone_lookout.called_text(called, bearing, range_nm),
                          "ausguck", 4.0)
            return
        text = self.lookout_report_text(report)
        if kind in ("TORP", "SUB", "MAST") and level > lookout_id.DETECTED:
            self.announce(text, "ausguck", 4.0)
        else:
            self.feed.add(self.world.format_time(), "ausguck", text)

    def _update_lookout_land(self) -> None:
        """'Land in sight': nearest coast of each landmass on a slow cadence."""
        epoch = math.floor((self.sim_t + 1e-9) / config.LOOKOUT_LAND_CHECK_S)
        if epoch == self._lookout_land_epoch:
            return
        self._lookout_land_epoch = epoch
        environment = self._lookout_environment()
        horizon = visual_physics.optical_horizon_nm(
            visual_physics.LOOKOUT_EYE_HEIGHT_M, visual_physics.TARGET_HEIGHT_M["LAND"])
        ox, oy = self.ship.x, self.ship.y
        seen = set()
        for index, landmass in enumerate(self.world.coast.landmasses):
            left, top, right, bottom = landmass.bounds
            if (max(left - ox, 0.0, ox - right) > horizon
                    or max(top - oy, 0.0, oy - bottom) > horizon):
                continue
            best = None
            points = landmass.points
            for position, first in enumerate(points):
                second = points[(position + 1) % len(points)]
                sx, sy = second[0] - first[0], second[1] - first[1]
                length = sx * sx + sy * sy
                along = (0.0 if length <= 1e-12 else max(0.0, min(1.0, (
                    (ox - first[0]) * sx + (oy - first[1]) * sy) / length)))
                px, py = first[0] + sx * along, first[1] + sy * along
                distance = math.hypot(px - ox, py - oy)
                if best is None or distance < best[0]:
                    best = (distance, px, py)
            if best is None or LOOKOUT_MODEL.margin(
                    "LAND", best[0], **environment) < 1.0:
                continue
            seen.add(index)
            if index not in self._lookout_land_seen:
                bearing = math.degrees(math.atan2(best[1] - ox, -(best[2] - oy))) % 360.0
                self._lookout_report("LAND", lookout_id.encode(
                    lookout_id.RECOGNIZED, "LAND", "LAND", None), bearing, best[0])
        self._lookout_land_seen = seen

    def _update_lookout_picture(self) -> None:
        """Publish bounded visual fixes without correlating sensor identities."""
        phone_lookout.refresh(self)
        # A shallow-running torpedo leaves a visible bubble track by day in a
        # moderate sea.
        if (not self.world.is_night()
                and getattr(self.world, "effective_sea_state", self.world.sea_state) <= 3.0):
            for torpedo in sorted(self.enemy_torpedoes, key=lambda item: item.id):
                if (torpedo.state == "RUN" and torpedo.depth <= TORPEDO_WAKE_VISIBLE_DEPTH_M
                        and math.hypot(torpedo.x - self.ship.x, torpedo.y - self.ship.y)
                        <= TORPEDO_WAKE_VISIBLE_NM):
                    self._lookout_observe(torpedo, "torpedo-wake", "TORP",
                                          torpedo.id, classes=("TORPEDO_WAKE",
                                                               "TORPEDO_WAKE", None))
        # Neutral traffic runs its navigation lights; warships run darkened.
        lit = nav_lights.lit(self.world.daylight_stage(),
                             getattr(self.world, "visibility_nm",
                                     config.WEATHER_VISIBILITY_MAX_NM))
        civilians = {id(actor) for actor in self.civilians}
        for actor in sorted(self.civilians + self.warships,
                            key=lambda item: item.id):
            if not actor.sunk:
                self._lookout_observe(
                    actor, "surface", "SURFACE", actor.sensor_seed,
                    classes=lookout_id.surface_classes(getattr(actor, "profile", None)),
                    lit=lit and id(actor) in civilians)
        self._lookout_lights = {key: value for key, value in self._lookout_lights.items()
                                if self.sim_t - value[1] <= config.LOOKOUT_EPOCH_S * 2}
        self._lookout_lights_called = {
            key: value for key, value in getattr(self, "_lookout_lights_called", {}).items()
            if self.sim_t - value[2] <= config.LOOKOUT_LIGHTS_REPORT_S * 5}
        self._lookout_elevation = {
            key: value for key, value in getattr(self, "_lookout_elevation", {}).items()
            if self.sim_t - value[1] <= config.LOOKOUT_EPOCH_S * 2}
        self._lookout_aspect = {
            key: value for key, value in getattr(self, "_lookout_aspect", {}).items()
            if self.sim_t - value[1] <= config.LOOKOUT_EPOCH_S * 2}
        for actor in sorted(self.subs, key=lambda item: item.id):
            if (not actor.sunk and actor.state != "SINKING"
                    and actor.depth <= config.LOOKOUT_SUB_SURFACED_MAX_DEPTH_M):
                self._lookout_observe(actor, "sub", "SUB", actor.sensor_seed,
                                      classes=("SUBMARINE", "SUBMARINE", None))
            elif not actor.sunk and actor.state != "SINKING" and self._mast_up(actor):
                # A raised periscope or snorkel head: the eye sees its
                # feather, which grows with the boat's speed.
                self._lookout_observe(actor, "sub", "MAST", actor.sensor_seed,
                                      classes=("PERISCOPE", "PERISCOPE", None),
                                      strength=visual_physics.feather_strength(actor.speed))
        # Civil aircraft show their position and anti-collision lights;
        # military aircraft fly dark.
        for actor in sorted(self.flights.flights, key=lambda item: item.seq):
            if actor.active:
                self._lookout_observe(
                    actor, "flight", "FLG", actor.sensor_seed + 200_000,
                    altitude_m=actor.altitude_m,
                    classes=lookout_id.aircraft_classes(
                        getattr(actor, "kind", "military"), getattr(actor, "akey", None)),
                    lit=lit and getattr(actor, "kind", "military") == "civil")
        for actor in sorted(self.raiders, key=lambda item: item.seq):
            if not actor.despawned and actor.hp > 0:
                self._lookout_observe(
                    actor, "raider", "FLG", actor.seq + 400_000,
                    altitude_m=getattr(actor, "altitude_m", 0.0),
                    classes=lookout_id.aircraft_classes("military", None))
        for actor in sorted(self.live_traffic.aircraft.values(),
                            key=lambda item: item.seq):
            if not actor.despawned:
                self._lookout_observe(
                    actor, "live_air", "FLG", actor.seq + 800_000,
                    altitude_m=getattr(actor, "altitude_m", 0.0),
                    # Indistinguishable from simulated civil traffic.
                    classes=lookout_id.aircraft_classes("civil", None), lit=lit)
        self._update_lookout_land()
