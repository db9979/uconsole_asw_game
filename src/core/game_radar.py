"""The frigate's radar, air and electronic picture: radar sweeps and air
tracks, mast echoes, ECM, ESM and radio pictures, anti-ship missiles and
raiders (``Game`` mixin).

Verbatim move from ``game_sim.py`` (1.3.59); the stages still run in the
``SIM_ORDER`` of ``_update_sim``."""

import math


from src.core import buoy_antenna, config
from src.core import detrand
from src.core.i18n import message
from src.sensors import radar as radar_physics
from src.sensors import threat_cue
from src.sensors import hfdf as hf_physics
from src.world import thunder
from src.data import catalog as contact_catalog
from src.data.catalog import EmitterProfile
from src.sensors.esm import (
    ECM_SIGNAL_FRESH_S,
    ESMMeasurement,
    RadarSuiteController,
    scan_for_signals,
    analyze_signal,
    filter_and_sort_tracks)
from src.air.asm import ASM
from src.air.raid import Raider


# Close-in weapon system: own Ku-band search/track radar that keeps an
# inbound missile under continuous track inside this range.
CIWS_TRACK_RANGE_NM = 3.0


class RadarPictureMixin:
    """Radar, air, ECM, ESM and radio pictures; missiles and raiders."""

    def _update_air_picture(self, full_scan: bool = False) -> None:
        """Create noisy observations; consumers never receive world objects.

        Radar contacts are looked at only where the rotating antenna swept
        since the previous publication (``full_scan`` treats the call as one
        complete revolution) and only when the detector declares the echo.
        """
        import random
        station_live = not self.damage.station_down("opz")
        surface_live = self.surface_radar_on and station_live
        air_live = self.air_radar_on and station_live
        swept_deg = 360.0 if full_scan else self.radar_scan_pending_deg
        self.radar_scan_pending_deg = 0.0
        self.ais.update(self.sim_t, self.civilians, self.ship, self.world)
        error_scale = 1.0 + (config.RADAR_WEATHER_ERROR_GAIN
                             * self.radar_weather_severity()
                             + config.RADAR_RAIN_ERROR_GAIN
                             * self.radar_rain_severity())
        for c in self.civilians:
            if c.sunk:
                continue
            dist = c.distance_nm(self.ship)
            bearing = c.bearing_from_frigate(self.ship)
            aspect = config.aspect_rcs_factor(c.course, bearing)
            horizon = config.radar_horizon_nm(
                config.RADAR_ANTENNA_HEIGHT_M, config.RADAR_SURFACE_TARGET_HEIGHT_M)
            radar_eligible = (surface_live and dist <= horizon
                              and self._radar_look("surface", c.sensor_seed, dist,
                                                   bearing, swept_deg=swept_deg,
                                                   rcs_factor=aspect ** 4))
            radar_clear = radar_eligible and not self.world.land_blocks_line(
                self.ship.x, self.ship.y, c.x, c.y)
            if radar_eligible and radar_clear:
                rng = random.Random(c.sensor_seed * 3571 + int(self.sim_t * 2.0))
                bearing_error = config.RADAR_BEARING_ERR_DEG * error_scale
                brg = (bearing + rng.uniform(-bearing_error, bearing_error)) % 360.0
                range_error = config.RADAR_RANGE_ERR_FRAC * error_scale
                measured = max(0.0, dist * (1.0 + rng.uniform(
                    -range_error, range_error)))
                # Radar measures position only. Name and course of a civilian
                # are known only from AIS reports the receiver has decoded.
                self.air_picture.observe(track_id=f"S-{c.id}", kind="SURFACE",
                    target_id=c.id, source="RADAR-S", bearing=brg,
                    range_nm=measured, observer_x=self.ship.x, observer_y=self.ship.y,
                    course=self.ais.course_for(c.id, self.sim_t), quality=.95,
                    now=self.sim_t, label=self.ais.label_for(c.id) or f"S-{c.id}",
                    bearing_uncertainty_deg=bearing_error / math.sqrt(3.0))
        for w in self.warships:
            if w.sunk:
                continue
            dist = w.distance_nm(self.ship)
            bearing = w.bearing_from_frigate(self.ship)
            aspect = config.aspect_rcs_factor(w.course, bearing)
            horizon = config.radar_horizon_nm(
                config.RADAR_ANTENNA_HEIGHT_M, config.RADAR_SURFACE_TARGET_HEIGHT_M)
            radar_eligible = (surface_live and dist <= horizon
                              and self._radar_look("surface", w.sensor_seed, dist,
                                                   bearing, swept_deg=swept_deg,
                                                   rcs_factor=aspect ** 4))
            radar_clear = radar_eligible and not self.world.land_blocks_line(
                self.ship.x, self.ship.y, w.x, w.y)
            if radar_eligible and radar_clear:
                rng = random.Random(w.sensor_seed * 3571 + int(self.sim_t * 2.0))
                bearing_error = config.RADAR_BEARING_ERR_DEG * error_scale
                brg = (bearing + rng.uniform(-bearing_error, bearing_error)) % 360.0
                range_error = config.RADAR_RANGE_ERR_FRAC * error_scale
                measured = max(0.0, dist * (1.0 + rng.uniform(
                    -range_error, range_error)))
                # Same S-<id> form as civilians (shared SurfaceShip ID counter):
                # the track ID must not reveal that a contact is a warship.
                self.air_picture.observe(track_id=f"S-{w.id}", kind="SURFACE",
                    target_id=w.id, source="RADAR-S", bearing=brg,
                    range_nm=measured, observer_x=self.ship.x, observer_y=self.ship.y,
                    course=None, quality=.9, now=self.sim_t,
                    label=f"S-{w.id}",
                    bearing_uncertainty_deg=bearing_error / math.sqrt(3.0))
        self._update_mast_echoes(surface_live, swept_deg, error_scale)
        for f in self.flights.flights:
            dist = f.distance_nm(self.ship)
            bearing = f.bearing_to_frigate(self.ship)
            horizon = config.radar_horizon_nm(
                config.RADAR_ANTENNA_HEIGHT_M, f.altitude_m)
            radar_eligible = (air_live and dist <= horizon
                              and self._radar_look("air", f.seq + 10000, dist,
                                                   bearing, swept_deg=swept_deg))
            radar_clear = radar_eligible and not self.world.land_blocks_line(
                self.ship.x, self.ship.y, f.x, f.y)
            if radar_eligible and radar_clear:
                rng = random.Random((f.seq + 10000) * 3571 + int(self.sim_t * 2.0))
                bearing_error = config.RADAR_BEARING_ERR_DEG * error_scale
                brg = (bearing + rng.uniform(-bearing_error, bearing_error)) % 360.0
                range_error = config.RADAR_RANGE_ERR_FRAC * error_scale
                measured = max(0.0, dist * (1.0 + rng.uniform(
                    -range_error, range_error)))
                altitude = config.measure_altitude_m(rng, f.altitude_m, error_scale)
                self.air_picture.observe(track_id=f"A-{f.seq}",
                    kind=self._radar_air_kind(f"A-{f.seq}", altitude),
                    target_id=f.seq, source="RADAR-L", bearing=brg, range_nm=measured,
                    observer_x=self.ship.x, observer_y=self.ship.y, course=None,
                    quality=.85, now=self.sim_t, label=f"A-{f.seq}",
                    bearing_uncertainty_deg=bearing_error / math.sqrt(3.0),
                    altitude_m=altitude)
        for r in self.raiders:
            dist = r.distance_nm(self.ship)
            bearing = r.bearing_from_frigate(self.ship)
            horizon = config.radar_horizon_nm(
                config.RADAR_ANTENNA_HEIGHT_M, getattr(r, "altitude_m", 0.0))
            radar_eligible = (air_live and dist <= horizon
                              and self._radar_look("air", r.seq + 60000, dist,
                                                   bearing, swept_deg=swept_deg))
            radar_clear = radar_eligible and not self.world.land_blocks_line(
                self.ship.x, self.ship.y, r.x, r.y)
            if radar_eligible and radar_clear:
                rng = random.Random((r.seq + 60000) * 3571 + int(self.sim_t * 2.0))
                bearing_error = config.RADAR_BEARING_ERR_DEG * error_scale
                brg = (bearing + rng.uniform(-bearing_error, bearing_error)) % 360.0
                range_error = config.RADAR_RANGE_ERR_FRAC * error_scale
                measured = max(0.0, dist * (1.0 + rng.uniform(
                    -range_error, range_error)))
                altitude = config.measure_altitude_m(
                    rng, getattr(r, "altitude_m", 0.0), error_scale)
                self.air_picture.observe(track_id=f"R-{r.seq}",
                    kind=self._radar_air_kind(f"R-{r.seq}", altitude),
                    target_id=r.seq, source="RADAR-L", bearing=brg,
                    range_nm=measured,
                    observer_x=self.ship.x, observer_y=self.ship.y, course=None,
                    quality=.85, now=self.sim_t, label=f"A-{r.seq}",
                    bearing_uncertainty_deg=bearing_error / math.sqrt(3.0),
                    altitude_m=altitude)
        for live in self.live_traffic.aircraft.values():
            if live.despawned:
                continue
            dist = live.distance_nm(self.ship)
            bearing = live.bearing_from_frigate(self.ship)
            horizon = config.radar_horizon_nm(
                config.RADAR_ANTENNA_HEIGHT_M, getattr(live, "altitude_m", 0.0))
            radar_eligible = (air_live and dist <= horizon
                              and self._radar_look("air", live.seq + 90000, dist,
                                                   bearing, swept_deg=swept_deg))
            radar_clear = radar_eligible and not self.world.land_blocks_line(
                self.ship.x, self.ship.y, live.x, live.y)
            if radar_eligible and radar_clear:
                rng = random.Random((live.seq + 90000) * 3571 + int(self.sim_t * 2.0))
                bearing_error = config.RADAR_BEARING_ERR_DEG * error_scale
                brg = (bearing + rng.uniform(-bearing_error, bearing_error)) % 360.0
                range_error = config.RADAR_RANGE_ERR_FRAC * error_scale
                measured = max(0.0, dist * (1.0 + rng.uniform(
                    -range_error, range_error)))
                # Selbe Track-ID-Form wie simulierte Fluege (A-<seq>, geteilter
                # Zaehler via FlightManager.next_seq): reale und simulierte
                # Luftkontakte sind fuer den Spieler ununterscheidbar.
                altitude = config.measure_altitude_m(
                    rng, live.altitude_m, error_scale)
                self.air_picture.observe(track_id=f"A-{live.seq}",
                    kind=self._radar_air_kind(f"A-{live.seq}", altitude),
                    target_id=live.seq, source="RADAR-L", bearing=brg,
                    range_nm=measured,
                    observer_x=self.ship.x, observer_y=self.ship.y, course=None,
                    quality=.85, now=self.sim_t, label=f"A-{live.seq}",
                    bearing_uncertainty_deg=bearing_error / math.sqrt(3.0),
                    altitude_m=altitude)
        ciws_track = station_live and self.ciws_authorized
        for a in self.asms:
            if a.state not in ("LAUF", "CHAFF"):
                continue
            dist = a.distance_nm(self.ship)
            # A sea-skimmer is below the radar (and radio) horizon until close.
            if dist > self._asm_radar_horizon_nm(a):
                continue
            if (a.jamming(self.ship) and dist <= config.ESM_RANGE_NM
                    and not self.world.land_blocks_line(
                        self.ship.x, self.ship.y, a.x, a.y)):
                noise = self._smooth_sensor_noise(
                    a.seq * 7919, self.sim_t, 5.0)
                brg = (a.bearing_to_frigate(self.ship)
                       + noise * 5.0) % 360.0
                self.air_picture.observe(track_id=f"M-{a.seq}",
                    kind=self._radar_air_kind(f"M-{a.seq}", None, jamming=True),
                    target_id=a.seq, source="HOJ", bearing=brg, range_nm=None,
                    observer_x=self.ship.x, observer_y=self.ship.y, course=None,
                    quality=.55, now=self.sim_t, label=f"A-{a.seq}",
                    jamming=True, bearing_uncertainty_deg=5.0 / math.sqrt(3.0))
            elif ((air_live or ciws_track)
                  and self._radar_look(
                      "air", a.seq + 120000, dist, a.bearing_to_frigate(self.ship),
                      # The CIWS search/track radar holds close-in missiles
                      # continuously; beyond it only the rotating antenna looks.
                      swept_deg=(360.0 if ciws_track and dist <= CIWS_TRACK_RANGE_NM
                                 else swept_deg if air_live else 0.0),
                      jnr=self._asm_jammer_to_noise(a, dist))
                  and not self.world.land_blocks_line(
                      self.ship.x, self.ship.y, a.x, a.y)):
                rng = random.Random(a.seq * 7919 + int(self.sim_t * 2.0))
                bearing_error = config.RADAR_BEARING_ERR_DEG * error_scale
                brg = (a.bearing_to_frigate(self.ship)
                       + rng.uniform(-bearing_error, bearing_error)) % 360.0
                range_error = config.RADAR_RANGE_ERR_FRAC * error_scale
                measured = max(0.0, dist * (1.0 + rng.uniform(
                    -range_error, range_error)))
                altitude = config.measure_altitude_m(rng, a.altitude_m, error_scale)
                self.air_picture.observe(track_id=f"M-{a.seq}",
                    kind=self._radar_air_kind(f"M-{a.seq}", altitude),
                    target_id=a.seq, source="RADAR-L", bearing=brg, range_nm=measured,
                    observer_x=self.ship.x, observer_y=self.ship.y, course=None,
                    quality=.9, now=self.sim_t, label=f"A-{a.seq}",
                    bearing_uncertainty_deg=bearing_error / math.sqrt(3.0),
                    altitude_m=altitude)
        self._update_lookout_picture()
        self.air_picture.expire(self.sim_t)

    def _radar_air_kind(self, track_id: str, altitude_m, jamming: bool = False) -> str:
        """Threat evaluation from this track's own measurements only."""
        previous = self.air_picture.current(track_id, self.sim_t)
        return threat_cue.air_track_kind(
            None if previous is None else previous.kind,
            None if previous is None else previous.derived_motion()[1],
            altitude_m, jamming)

    def _update_ecm(self) -> None:
        tracks = self.eloka_tracks()
        self.ecm_jammer.update(
            tracks, self.sim_t, operational=not self.damage.station_down("opz"))
        if not self.ecm_jammer.auto_enabled:
            return
        occupied = {channel.track_key for channel in self.ecm_jammer.channels}
        threat_order = {"critical": 0, "high": 1, "medium": 2, "low": 3,
                        "unknown": 4}
        choices = []
        for track in tracks:
            if (track.track_key in occupied
                    or track.age(self.sim_t) > ECM_SIGNAL_FRESH_S):
                continue
            analysis = analyze_signal(track, self.runtime_catalog.emitters)
            if (analysis.threat_level not in ("critical", "high")
                    or not analysis.candidates
                    or analysis.candidates[0].score < .65):
                continue
            choices.append((threat_order[analysis.threat_level],
                            track.age(self.sim_t), -track.quality,
                            track.track_key, track))
        for *_, track in sorted(choices):
            if len(self.ecm_jammer.channels) >= self.ecm_jammer.MAX_CHANNELS:
                break
            self.ecm_jammer.deploy_jamming(track, self.sim_t, automatic=True)

    def _emitter_profile(self, profile_key: str):
        systems = self.runtime_catalog.profile_systems.get(profile_key)
        if systems is None:
            return None
        return next((self.runtime_catalog.emitters[key]
                     for key in sorted(systems.emitter_keys)
                     if key in self.runtime_catalog.emitters
                     and self.runtime_catalog.emitters[key].domain == "radar"), None)

    @staticmethod
    def _asm_radar_horizon_nm(asm) -> float:
        """Two-way horizon between the own mast and an inbound missile."""
        return config.radar_horizon_nm(config.RADAR_ANTENNA_HEIGHT_M,
                                       asm.altitude_m)

    def _asm_seeker_emitter(self, profile: dict) -> EmitterProfile:
        """Terminal active-radar seeker signature of an inbound ASM.

        The signature is the catalog's library emitter the loadout names; a
        save written before the seeker was catalogued carries a snapshot
        without it and keeps emitting the packaged signature.
        """
        key = profile["seeker_emitter_key"]
        emitter = self.runtime_catalog.emitters.get(key)
        if emitter is None:
            emitter = contact_catalog.CATALOG.emitters[key]
        return emitter

    def _radar_signals(self, actor, profile_key: str, *, enabled=True,
                       synthetic=False, fire_control=False, terminal=False):
        systems = self.runtime_catalog.profile_systems.get(profile_key)
        if systems is None:
            return ()
        emitters = [self.runtime_catalog.emitters[key]
                    for key in systems.emitter_keys
                    if key in self.runtime_catalog.emitters]
        return RadarSuiteController(
            emitters, int(getattr(actor, "sensor_seed", 0)),
            synthetic_assumption=synthetic).active_signals(
                self.sim_t, actor.x, actor.y, enabled=enabled,
                fire_control=fire_control, terminal=terminal)

    def own_radar_signals(self):
        """Internal own-force emissions available to hostile ESM simulation."""
        profile_key = "warship_25"
        systems = self.runtime_catalog.profile_systems.get(profile_key)
        if systems is None or self.damage.station_down("opz"):
            return ()
        emitters = []
        for key in systems.emitter_keys:
            emitter = self.runtime_catalog.emitters[key]
            role = emitter.radar_role
            if ((role in ("navigation", "surface_search") and self.surface_radar_on)
                    or role == "air_search" and self.air_radar_on
                    or role == "multi_function"
                    and (self.surface_radar_on or self.air_radar_on)
                    or role == "fire_control" and self.selected_opz_track() is not None):
                emitters.append(emitter)
        return RadarSuiteController(emitters, self.seed + 0x52414441).active_signals(
            self.sim_t, self.ship.x, self.ship.y,
            fire_control=self.selected_opz_track() is not None)

    def _signal_measurements(self, actor, signals):
        seed = int(getattr(actor, "sensor_seed", 0))
        return scan_for_signals(
            signals, observer_x=self.ship.x, observer_y=self.ship.y,
            now=self.sim_t, maximum_range_nm=config.ESM_RANGE_NM,
            bearing_error_deg=config.ESM_BEARING_ERR_DEG,
            noise_for=lambda signal: self._smooth_sensor_noise(
                seed * 1009 + int(signal.signal_id[1:9], 16),
                self.sim_t, 5.0),
            line_of_sight=lambda signal: not self.world.land_blocks_line(
                self.ship.x, self.ship.y, signal.x, signal.y),
            level_noise_for=lambda signal: detrand.normal(
                self.seed, "esm-level", int(signal.signal_id[1:9], 16),
                math.floor(self.sim_t * 2.0 + 1e-6)))

    def _ecm_effect_against_asm(self, asm):
        if not asm.seeker_active(self.ship) or not self.ecm_jammer.channels:
            return None
        emitter = self._asm_seeker_emitter(asm.profile)
        signals = RadarSuiteController((emitter,), asm.sensor_seed).active_signals(
            self.sim_t, asm.x, asm.y, terminal=True)
        if not signals:
            return None
        blocked = (asm.distance_nm(self.ship) > self._asm_radar_horizon_nm(asm)
                   or self.world.land_blocks_line(
                       self.ship.x, self.ship.y, asm.x, asm.y))
        return self.ecm_jammer.effect_details_on(
            signals[0], asm.distance_nm(self.ship), line_of_sight=not blocked,
            operational=not self.damage.station_down("opz"),
            burn_through_nm=asm.profile["jam_break_nm"])

    def _esm_measurement(self, actor, bearing: float, distance: float,
                         emitter, namespace: int) -> ESMMeasurement:
        import random

        seed = int(getattr(actor, "sensor_seed", 0)) + namespace
        rng = random.Random(seed * 65537 + 0x45534D)
        if emitter is None:
            frequency = rng.uniform(2e9, 12e9)
            prf = rng.uniform(200.0, 1500.0)
            modulation = "unknown"
        else:
            frequency = rng.uniform(*emitter.frequency_band_hz)
            prf = (rng.uniform(*emitter.prf_band_hz)
                   if emitter.prf_band_hz is not None else None)
            modulation = rng.choice(emitter.modulation_codes)
        uncertainty = config.ESM_BEARING_ERR_DEG / math.sqrt(3.0)
        noise = self._smooth_sensor_noise(seed * 1009, self.sim_t, 5.0)
        return ESMMeasurement(
            observer_x=self.ship.x,
            observer_y=self.ship.y,
            bearing=(bearing + noise * config.ESM_BEARING_ERR_DEG) % 360.0,
            bearing_uncertainty_deg=uncertainty,
            frequency_hz=frequency,
            prf_hz=prf,
            modulation_code=modulation,
            quality=config.clamp(.9 - .45 * distance / config.ESM_RANGE_NM,
                                 .35, .9),
            observed_at=self.sim_t,
        )

    def _update_esm_picture(self) -> None:
        """Publish passive intercepts independently from own-radar evidence."""
        if self.damage.station_down("opz"):
            self.esm_picture.expire(self.sim_t)
            self._update_ecm()
        else:
            def measurements():
                for sub in self.subs:
                    # Mast radar is possible only near periscope/snorkel depth
                    # and outside evasion/attack phases.
                    enabled = (not sub.sunk and sub.depth <= 20.0
                               and sub.state == "PATROLLE")
                    signals = self._radar_signals(
                        sub, sub.stype.key, enabled=enabled)
                    yield from self._signal_measurements(sub, signals)
                for actor in self.civilians + self.warships:
                    if actor.sunk or not actor.emitter:
                        continue
                    signals = self._radar_signals(
                        actor, actor.signature_key, enabled=actor.radar_emitting,
                        synthetic=actor.live_mmsi is not None,
                        fire_control=actor in self.warships
                        and bool(actor.pending_asm))
                    yield from self._signal_measurements(actor, signals)
                for flight in self.flights.flights:
                    signals = self._radar_signals(
                        flight, flight.akey,
                        enabled=flight.radar_emitting or flight.kind == "civil",
                        synthetic=flight.kind == "civil",
                        fire_control=flight.akey == "su_25")
                    yield from self._signal_measurements(flight, signals)
                for live in sorted(self.live_traffic.aircraft.values(),
                                   key=lambda item: item.seq):
                    profile_key = self.runtime_catalog.runtime_bindings[
                        "civil_flight"]
                    signals = self._radar_signals(
                        live, profile_key, enabled=True, synthetic=True)
                    yield from self._signal_measurements(live, signals)
                for raider in sorted(self.raiders, key=lambda item: item.seq):
                    signals = self._radar_signals(
                        raider, "su_25", enabled=not raider.despawned,
                        fire_control=raider.fc_radar_on)
                    yield from self._signal_measurements(raider, signals)
                for asm in self.asms:
                    # A sea-skimmer's seeker is heard only once the missile
                    # has risen above the mast's radar horizon.
                    if asm.distance_nm(self.ship) > self._asm_radar_horizon_nm(asm):
                        continue
                    emitter = self._asm_seeker_emitter(asm.profile)
                    signals = RadarSuiteController(
                        (emitter,), asm.sensor_seed).active_signals(
                            self.sim_t, asm.x, asm.y,
                            terminal=asm.seeker_active(self.ship))
                    yield from self._signal_measurements(asm, signals)

            protected = set(self.eloka_annotations)
            protected.update(channel.track_key for channel in self.ecm_jammer.channels)
            previous_operational = {
                track.track_key for track in self.eloka_tracks()
                if filter_and_sort_tracks(
                    (track,), self.sim_t, self.eloka_analysis,
                    annotated_keys=self.eloka_annotations,
                    jamming_keys=protected)}
            self.esm_picture.observe_batch(
                measurements(), self.sim_t, protected_keys=protected)
            self._update_ecm()
            operational = {track.track_key for track in filter_and_sort_tracks(
                self.eloka_tracks(), self.sim_t, self.eloka_analysis,
                annotated_keys=self.eloka_annotations,
                jamming_keys=(channel.track_key
                              for channel in self.ecm_jammer.channels))}
            if operational - previous_operational:
                self._emit_sound("esm_contact")
            self._publish_released_esm()
        self._reconcile_eloka_selection()

    def _update_radio_picture(self) -> None:
        """Measure transmitting emitters without publishing their positions."""
        if self.damage.station_down("radio"):
            self.radio_picture.expire(self.sim_t)
            return
        night = self.world.is_night()
        for sub in self.subs:
            if not (sub.transmitting or sub.contact_report_on_air(self.seed, self.sim_t)):
                continue
            dist = sub.distance_nm(self.ship)
            seed = getattr(sub, "sensor_seed", sub.id)
            # One call keeps its frequency; a new 5-minute schedule window
            # may pick another one for the path to the shore station.
            frequency = hf_physics.transmit_frequency_mhz(
                seed, math.floor(self.sim_t / 300.0), night)
            mode = hf_physics.propagation_mode(
                dist, frequency, night, config.HFDF_RANGE_NM)
            if mode is None:
                continue
            if (mode == "GROUND" and self.world.land_blocks_line(
                    self.ship.x, self.ship.y, sub.x, sub.y)):
                continue
            error = config.HFDF_BEARING_ERR_DEG * (
                hf_physics.SKY_WAVE_BEARING_FACTOR if mode == "SKY" else 1.0) \
                * thunder.sferics_factor(self.world.thunderstorm())
            noise = self._smooth_sensor_noise(seed * 777, self.sim_t, 10.0)
            brg = (sub.bearing_from_frigate(self.ship) + noise * error) % 360.0
            self.radio_picture.observe(track_id=f"H-{sub.id}", kind="HF",
                target_id=sub.id, source="HFDF", bearing=brg, range_nm=None,
                observer_x=self.ship.x, observer_y=self.ship.y, course=None,
                quality=.55 if mode == "GROUND" else .4, now=self.sim_t,
                label=f"SIG-{sub.id:02d}",
                bearing_uncertainty_deg=error / math.sqrt(3.0),
                frequency_hz=round(frequency * 1e6, -2), propagation=mode)
        self.radio_picture.expire(self.sim_t)

    def _drain_warship_asm(self) -> None:
        """Kampfschiff-Salven aus pending_asm werden zu ASM-Objekten."""
        for w in self.warships:
            if w.sunk:
                continue
            pending, w.pending_asm = w.pending_asm, []
            for x, y, n in pending:
                for i in range(n):
                    course = (math.degrees(math.atan2(w.sensor_contact[0] - x,
                                                      -(w.sensor_contact[1] - y))) % 360.0
                              if w.sensor_contact is not None else w.course)
                    self.warship_asm_seq += 1
                    # Ship-launched: booster from the launcher's speed; the
                    # launcher's sensor contact is the inertial datum.
                    self.asms.append(ASM(
                        x, y, course, self._next_asm_sequence(), self.rng_asm,
                        self._air_defense_loadout["asm"],
                        launch_speed_kn=w.speed, altitude_m=10.0,
                        datum=w.sensor_contact))

    def _next_asm_sequence(self) -> int:
        self.asm_seq += 1
        return self.asm_seq

    def _maybe_spawn_asm(self) -> None:
        """M16: ASM-Wellen laut Missionsplan (zeitgesteuert, deterministisch)."""
        m = self.mission
        if self.asm_spawned >= m.asm_count:
            return
        need = (config.ASM_SPAWN_FIRST_S
                + self.asm_spawned * self.mission.asm_interval_s)
        if self.mission_time < need:
            return
        self.asm_spawned += 1
        d = self.rng_asm.uniform(*config.ASM_SPAWN_DIST_NM)
        ang = self.rng_asm.uniform(0.0, 360.0)
        x = config.clamp(self.ship.x + d * math.cos(math.radians(ang)),
                         0.0, self.world.size_nm)
        y = config.clamp(self.ship.y + d * math.sin(math.radians(ang)),
                         0.0, self.world.size_nm)
        course = math.degrees(math.atan2(self.ship.x - x, -(self.ship.y - y))) % 360.0
        # A wave appears already in cruise flight, aimed by its (unseen)
        # launcher at the ship's position at that moment.
        self.asms.append(ASM(x, y, course, self._next_asm_sequence(), self.rng_asm,
                              self._air_defense_loadout["asm"],
                              datum=(self.ship.x, self.ship.y)))

    # --- R20: Luftangriff (feindliche Angriffsflugzeug-Wellen) ---

    def _spawn_raid_wave(self, profile: dict) -> None:
        """Eine Welle Angriffsflugzeuge außerhalb der Radarreichweite spawnen."""
        size = self.rng_raid.randint(*config.RAID_WAVE_SIZE)
        for _ in range(size):
            d = self.rng_raid.uniform(*config.RAID_SPAWN_DIST_NM)
            ang = self.rng_raid.uniform(0.0, 360.0)
            x = config.clamp(self.ship.x + d * math.cos(math.radians(ang)),
                             0.0, self.world.size_nm)
            y = config.clamp(self.ship.y + d * math.sin(math.radians(ang)),
                             0.0, self.world.size_nm)
            course = (math.degrees(math.atan2(self.ship.x - x,
                                              -(self.ship.y - y))) % 360.0)
            self.raid_seq += 1
            self.raiders.append(Raider(x, y, course, self.raid_seq,
                                       self.rng_raid, profile))
        self.raid_waves_spawned += 1

    def _update_raiders(self, dt: float, publish_picture: bool = True) -> None:
        """R20: Raid-Wellen, Bewegung/Phasen, Salven-Ablöse und Flak-Einsatz."""
        profiles = self._air_defense_loadout
        if (self.mission.asm_count > 0
                and len(self.raiders) < config.RAID_MAX_CONCURRENT
                and self.mission_time >= config.RAID_FIRST_WAVE_S
                + self.raid_waves_spawned * self.mission.raid_interval_s):
            self._spawn_raid_wave(profiles["raider"])
        for raider in self.raiders:
            raider.update(dt, self.ship, world=self.world)
        self.aa_cooldown_s = max(0.0, self.aa_cooldown_s - dt)
        aa = profiles["aa_gun"]
        observed = {}
        # Live-Flugzeuge tragen absichtlich dasselbe "A-<seq>"-Format wie
        # simulierte Fluege (siehe FlightManager.next_seq) - der exakte,
        # eindeutige Seq-Wert je LiveAircraft macht die Zuordnung trotzdem
        # kollisionsfrei, ohne dass ein eigenes, erkennbares Praefix noetig
        # waere.
        observed_a_tracks = {}
        for track in self.air_picture.tracks(self.sim_t, ("FLG", "ASM")):
            if track.track_id.startswith("R-"):
                observed[track.track_id] = track
            elif track.track_id.startswith("A-"):
                observed_a_tracks[track.track_id] = track
        for raider in self.raiders:
            if raider.hp <= 0:
                continue
            track = observed.get(f"R-{raider.seq}")
            if (self.flak_authorized
                    and track is not None and track.x is not None and track.y is not None
                    and track.position_seen is not None
                    and self.sim_t - track.position_seen
                    <= aa["observation_max_age_s"]
                    and track.range_nm is not None
                    and track.range_nm <= aa["range_nm"]
                    and self.aa_ammo >= aa["rounds_per_attempt"]
                    and self.aa_cooldown_s <= 0.0
                    and not self.damage.station_down("weapons")
                    and not self.world.land_blocks_line(
                        self.ship.x, self.ship.y, track.x, track.y)):
                self.aa_ammo -= aa["rounds_per_attempt"]
                self.aa_cooldown_s = aa["cycle_s"]
                self._emit_sound("gunfire")
                # Pk composes base accuracy with evasion and a range falloff:
                # closer raiders are easier hard-kill targets for the AA gun.
                distance_factor = 1.0 - 0.5 * config.clamp(
                    track.range_nm / max(0.01, aa["range_nm"]), 0.0, 1.0)
                if (self.rng_raid.random()
                        < aa["hit_probability"] * (1.0 - raider.evasion) * distance_factor):
                    raider.hp -= 1
                    if raider.hp <= 0:
                        raider.despawned = True
                        self.audio.play_alert("defense")
                        self.flash(message("runtime.raid.downed"), 3.0)
                        self.feed.add(self.world.format_time(), "waffen",
                                      message("runtime.raid.downed"))
        self.raiders = [r for r in self.raiders if not r.despawned]
        # Echter ADS-B-Verkehr ist nie automatisch feindlich: die Flak darf
        # ihn nur treffen, wenn der Spieler den konkreten OPZ-Track manuell
        # als HOSTILE eingestuft hat (dieselbe IFF-Klassifizierung wie fuer
        # jeden anderen Radar-/Sonar-Kontakt). Ohne diese bewusste
        # Fehleinschaetzung bleibt Realverkehr fuer die Waffen unantastbar,
        # daher gilt hier - anders als vorher - die reale Geschuetzreichweite.
        for live in list(self.live_traffic.aircraft.values()):
            if live.despawned:
                continue
            track_id = f"A-{live.seq}"
            if self.opz_affiliation(track_id) != "HOSTILE":
                continue
            if live.icao24 not in self.live_engage_authorized:
                continue
            track = observed_a_tracks.get(track_id)
            if (self.flak_authorized
                    and track is not None and track.x is not None and track.y is not None
                    and track.position_seen is not None
                    and self.sim_t - track.position_seen
                    <= aa["observation_max_age_s"]
                    and track.range_nm is not None
                    and track.range_nm <= aa["range_nm"]
                    and self.aa_ammo >= aa["rounds_per_attempt"]
                    and self.aa_cooldown_s <= 0.0
                    and not self.damage.station_down("weapons")
                    and not self.world.land_blocks_line(
                        self.ship.x, self.ship.y, track.x, track.y)):
                self.aa_ammo -= aa["rounds_per_attempt"]
                self.aa_cooldown_s = aa["cycle_s"]
                self._emit_sound("gunfire")
                distance_factor = 1.0 - 0.5 * config.clamp(
                    track.range_nm / max(0.01, aa["range_nm"]), 0.0, 1.0)
                if self.rng_raid.random() < aa["hit_probability"] * distance_factor:
                    live.hit()
                    if live.despawned:
                        self.live_traffic.mark_aircraft_destroyed(live.icao24)
                        self.incident = True
                        self.audio.play_alert("danger")
                        self.flash(message("runtime.live_air.downed"), 4.0)
                        self.feed.add(self.world.format_time(), "waffen",
                                      message("runtime.live_air.downed"))
        if publish_picture:
            # No "raid incoming" call: radar cannot tell an attack aircraft
            # from other air traffic. Threat alerts come from the measured
            # ASM cue (speed/altitude/jamming) and operator annotations.
            self._raider_visible_last = bool(observed)

    def _drain_raider_asm(self) -> None:
        """R20: Raid-Salven werden zu ASM-Objekten gegen die Fregatte."""
        for raider in self.raiders:
            pending, raider.pending_asm = raider.pending_asm, 0
            for _ in range(pending):
                course = raider.course_to_frigate(self.ship)
                # Air-launched at the raider's speed and pop-up height; its
                # fire-control radar supplied the datum.
                self.asms.append(ASM(
                    raider.x, raider.y, course, self._next_asm_sequence(),
                    self.rng_asm, self._air_defense_loadout["asm"],
                    launch_speed_kn=raider.speed_kn, altitude_m=raider.altitude_m,
                    datum=(self.ship.x, self.ship.y)))

    # --- Waffenzentrale ---

    def _mast_up(self, sub) -> bool:
        """A mast or snorkel head above the water: the crew's raised mast or
        snorkel, an AI boat snorkelling or at radio depth, or the AI recon
        boat's periscope during a look."""
        from src.sensors.platform import MAST_DEPTH_M
        if sub.sunk or sub.depth > MAST_DEPTH_M:
            return False
        crew = getattr(sub, "crew", None)
        if sub.manual and crew is not None and crew.mast:
            return True
        endurance = sub.endurance
        if endurance is not None and endurance.phase in ("SNORKEL", "RADIO"):
            return True
        from src.core import boat_ai
        return boat_ai.scope_look(self, sub) is not None

    def _update_mast_echoes(self, surface_live, swept_deg, error_scale) -> None:
        """Surface-radar looks at raised masts: a bare blip, or an update of
        the track the OPZ marked for that boat."""
        for sub_id, (_track_id, last) in tuple(self._radar_marked.items()):
            if self.sim_t - last > config.RADAR_TRACK_STALE_S:
                del self._radar_marked[sub_id]
        if not surface_live:
            return
        horizon = config.radar_horizon_nm(config.RADAR_ANTENNA_HEIGHT_M,
                                          config.SUB_MAST_HEIGHT_M)
        tick = math.floor(self.sim_t * 4.0 + 1e-6)
        for sub, sx, sy, key, rcs, reach in self._surface_heads(horizon):
            dist = math.hypot(sx - self.ship.x, sy - self.ship.y)
            bearing = math.degrees(math.atan2(sx - self.ship.x,
                                              -(sy - self.ship.y))) % 360.0
            if (dist > reach or not self._radar_look(
                    "surface", key, dist, bearing, swept_deg=swept_deg,
                    rcs_factor=rcs)
                    or self.world.land_blocks_line(self.ship.x, self.ship.y, sx, sy)):
                continue
            bearing_error = config.RADAR_BEARING_ERR_DEG * error_scale
            range_error = config.RADAR_RANGE_ERR_FRAC * error_scale
            brg = (bearing + detrand.uniform(-bearing_error, bearing_error, self.seed,
                                             "radar-mast-brg", sub.sensor_seed, tick)) % 360.0
            measured = max(0.0, dist * (1.0 + detrand.uniform(
                -range_error, range_error, self.seed, "radar-mast-rng", sub.sensor_seed, tick)))
            marked = self._radar_marked.get(sub.id)
            if marked is not None:
                self._observe_mast(marked[0], sub.id, brg, measured,
                                   self.ship.x, self.ship.y, bearing_error)
                continue
            self.radar_blip_seq += 1
            rad = math.radians(brg)
            self.radar_blips.append(dict(
                seq=self.radar_blip_seq, t=float(self.sim_t), target=sub.id,
                bearing=brg, range_nm=measured, error=bearing_error,
                observer_x=self.ship.x, observer_y=self.ship.y,
                x=self.ship.x + measured * math.sin(rad),
                y=self.ship.y - measured * math.cos(rad)))

    def _surface_heads(self, mast_horizon):
        """What of each submarine rides on the water for the surface radar:
        a surfaced boat's hull and conning tower, a raised mast, or the
        crewed boat's streamed buoy antenna (smaller and lower, astern of the
        boat).  Rows ``(sub, x, y, key, rcs, horizon)``."""
        rows = []
        for sub in self.subs:
            if (not sub.sunk and sub.state != "SINKING"
                    and sub.depth <= config.UBOOT_SURFACED_DEPTH_M):
                rows.append((sub, sub.x, sub.y, sub.sensor_seed,
                             config.SUB_SURFACED_RCS_FACTOR, config.radar_horizon_nm(
                                 config.RADAR_ANTENNA_HEIGHT_M, config.SUB_SURFACED_HEIGHT_M)))
            elif self._mast_up(sub):
                rows.append((sub, sub.x, sub.y, sub.sensor_seed,
                             config.SUB_MAST_RCS_FACTOR, mast_horizon))
            elif self._buoy_afloat(sub):
                bx, by = buoy_antenna.position(sub)
                rows.append((sub, bx, by, sub.sensor_seed + 300_000,
                             config.UBOOT_BUOY_RCS_FACTOR, config.radar_horizon_nm(
                                 config.RADAR_ANTENNA_HEIGHT_M, config.UBOOT_BUOY_HEIGHT_M)))
        return rows

    def _buoy_afloat(self, sub) -> bool:
        """The crewed boat's buoy antenna rides on the surface."""
        crew = getattr(sub, "crew", None)
        return (sub.manual and crew is not None and not sub.sunk
                and buoy_antenna.afloat(getattr(crew, "buoy", None), sub.speed))

    def _observe_mast(self, track_id, sub_id, bearing, range_nm, observer_x, observer_y,
                      bearing_error) -> None:
        self._radar_marked[sub_id] = (track_id, float(self.sim_t))
        self.air_picture.observe(track_id=track_id, kind="SURFACE", target_id=sub_id,
            source="RADAR-S", bearing=bearing, range_nm=range_nm,
            observer_x=observer_x, observer_y=observer_y, course=None, quality=.5,
            now=self.sim_t, label=track_id,
            bearing_uncertainty_deg=bearing_error / math.sqrt(3.0))

    def _radar_look(self, domain: str, key: int, distance: float, bearing: float,
                    *, swept_deg: float, rcs_factor: float = 1.0,
                    jnr: float = 0.0) -> bool:
        """One antenna look: the beam must have passed the bearing and the
        Swerling-1/CFAR detector must declare the echo (deterministic draw)."""
        if not radar_physics.swept(bearing, self.radar_scan_phase, swept_deg):
            return False
        nominal = (config.RADAR_AIR_RANGE_NM if domain == "air"
                   else config.RADAR_SURFACE_RANGE_NM)
        sinr = radar_physics.sinr(distance, nominal, rcs_factor=rcs_factor,
                                  domain=domain, jnr=jnr,
                                  **self._radar_conditions())
        tick = math.floor(self.sim_t * 4.0 + 1e-6)
        return (detrand.u01(self.seed, "radar-look-" + domain, key, tick)
                < radar_physics.pd_from_sinr(sinr))

    def _radar_conditions(self) -> dict:
        # Damage to the operations room (radar consoles, power) degrades the
        # radar continuously rather than only at destruction.
        capability = (1.0 if not self.damage.station_degraded("opz")
                      else 0.5 + 0.5 * self.damage.capability("opz"))
        return dict(
            sea_state=getattr(self.world, "effective_sea_state", self.world.sea_state),
            rain_intensity=self.radar_rain_severity(), capability=capability)

    def _asm_jammer_to_noise(self, asm, distance: float) -> float:
        """Self-screening noise jammer of a missile, solved from its profiled
        burn-through range (J/S ~ R^2): inside it the skin echo wins."""
        if not asm.jammer:
            return 0.0
        burn_through = asm.profile["jam_break_nm"]
        skin = radar_physics.snr(burn_through, config.RADAR_AIR_RANGE_NM)
        return radar_physics.jammer_to_noise(distance, burn_through, skin)

    def radar_weather_severity(self) -> float:
        """0 bis Seegang 4; 0.5/1.0 erst bei schwerem Wetter 5/6."""
        return config.clamp(
            (getattr(self.world, "effective_sea_state", self.world.sea_state)
             - (config.RADAR_WEATHER_THRESHOLD - 1)) / 2.0,
            0.0, 1.0)

    def radar_rain_severity(self) -> float:
        return config.clamp(getattr(self.world, "rain_intensity", 0.0), 0.0, 1.0)

    def radar_effective_range(self, domain: str) -> float:
        """Range of Pd = 0.5 per look for a reference target (radar equation
        with sea clutter, rain attenuation and console damage)."""
        nominal = (config.RADAR_AIR_RANGE_NM if domain == "air"
                   else config.RADAR_SURFACE_RANGE_NM)
        conditions = self._radar_conditions()
        return nominal * radar_physics.detection_fraction(
            domain, conditions["sea_state"], conditions["rain_intensity"],
            nominal, conditions["capability"])
