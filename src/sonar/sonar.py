"""W1: Sonar-System – SNR-Modell, Peilfehler, TMA, LOFAR-Wasserfall.

Passiv: nur Peilung (± Peilfehler je Array/Eigenfahrt/Qualität).
TMA: Peilungsreihe + Fregattenmanöver -> Position + Geschwindigkeit.
Aktiv: Ping -> exakte Distanz + Tiefe (verrät Position).
"""

import math
import random

import numpy as np

from src.core import config
from src.sonar.tma import BearingTrack, solve_tma
from src.audio.database import rank_signatures
from src.audio.receiver import AcousticReceiver


def tgt_gone(tgt) -> bool:
    """True, wenn das Ziel versenkt/tot ist (Sub.sunk / Animal.dead)."""
    if hasattr(tgt, "sunk"):
        return bool(tgt.sunk)
    if hasattr(tgt, "dead"):
        return bool(tgt.dead)
    return bool(getattr(tgt, "hit", False))


def snr_db(passive_range_nm: float, dist_nm: float) -> float:
    """SNR: 20*log10(R_eff/d). 0 dB = am Rande der Detektion."""
    return 20.0 * math.log10(max(passive_range_nm, 1e-6)
                             / max(dist_nm, 1e-6))


def bearing_error_deg(mode: str, frigate_speed_kn: float, quality: float) -> float:
    """± Peilfehler: Array-Basis * Eigenfahrt-Aufschlag * Qualitätsfaktor."""
    base = (config.BEARING_ERR_TOWED_DEG if mode == "TOWED"
            else config.BEARING_ERR_BOW_DEG)
    return (base * (1.0 + config.BEARING_ERR_SPEED_FACTOR * frigate_speed_kn)
            * (1.4 - config.BEARING_ERR_QUALITY_SPAN * quality))


class Contact:
    """Sonarkontakt: passiv nur Peilung, Position via Ping oder TMA.

    Klassifizierung erfolgt manuell (player_class) auf Basis der
    hörbaren Geräusch-Signatur (signature).
    """

    def __init__(self, contact_id: int, target_id: int, origin: str, kind: str):
        self.id = contact_id
        self.target_id = target_id
        self.origin = origin   # "passiv" | "ping"
        self.kind = kind       # "sub"|"animal"|"surface"|"decoy"|"torpedo"
        self.bearing = 0.0
        self.range_est = None  # None = nicht geortet (nur Peilung)
        self.range_sigma_nm = None  # 1-sigma Unsicherheit der Entfernung
        self.range_source = None  # None | "ping" | "tma"
        self.range_seen = None
        self.confidence = 0.0
        self.quality = 0.0
        self.last_seen = 0.0
        self.depth_est = None
        self.depth_sigma_m = None  # 1-sigma Unsicherheit der Tiefe
        self.player_class = None  # None|U_BOOT|KAMPFSCHIFF|BIOLOGISCH|FAHRZEUG
        self.signature = ""       # zuletzt gehörte Geräusch-Signatur
        # W1: SNR + TMA
        self.snr = -99.0          # dB, -99 = gerade nicht detektiert
        self.tma_pos = None       # (x, y) NM
        self.tma_course = None
        self.tma_speed = None
        self.tma_quality = 0.0
        self.array_observations = {}
        self.fusion_status = "KEINE DATEN"
        self.fusion_delta_deg = None
        self.fused_quality = 0.0

    def update_passive(self, bearing: float, confidence: float,
                       quality: float, signature: str, t: float,
                       snr: float = 0.0):
        """Passives Hören: nur (fehlerbehaftete) Peilung."""
        self.bearing = bearing
        self.confidence = min(1.0, confidence)
        self.quality = min(1.0, quality)
        self.last_seen = t
        self.snr = snr
        if (self.range_source == "ping" and self.range_seen is not None
                and t - self.range_seen > config.SONAR_PING_FIX_MAX_AGE_S):
            self.range_est = None
            self.range_sigma_nm = None
            self.range_source = None
            self.depth_est = None
            self.depth_sigma_m = None
        if signature:
            self.signature = signature

    def update_ping(self, bearing: float, range_est: float, depth_est: float,
                    confidence: float, t: float, snr: float = 0.0):
        """Aktiver Ping: liefert Position + Tiefe (maßstabsgenau)."""
        self.bearing = bearing
        self.range_est = range_est
        self.range_sigma_nm = 0.0
        self.range_source = "ping"
        self.range_seen = t
        self.depth_est = depth_est
        self.depth_sigma_m = 0.0
        self.origin = "ping"
        self.confidence = min(1.0, confidence)
        self.quality = 1.0
        self.last_seen = t
        self.snr = snr

    def update_tma(self, sol, t: float):
        """TMA-Estimate übernehmen (nur, solange kein frischerer Ping)."""
        self.tma_pos = sol.pos
        self.tma_course = sol.course
        self.tma_speed = sol.speed
        self.tma_quality = max(self.tma_quality, sol.quality)
        ping_fresh = (self.range_source == "ping" and self.range_seen is not None
                      and t - self.range_seen <= config.SONAR_PING_FIX_MAX_AGE_S)
        if not ping_fresh and \
                sol.quality >= config.TMA_RANGE_MIN_QUALITY:
            self.range_est = math.hypot(sol.pos[0] - self._fx,
                                        sol.pos[1] - self._fy)
            self.range_sigma_nm = max(0.1, (1.0 - sol.quality) * 12.0)
            self.range_source = "tma"
            self.range_seen = t
            self.last_seen = t

    def decay(self, dt: float, t: float) -> bool:
        """Konfidenz sinkt ohne neue Detektion; nach Zeit + niedriger
        Konfidenz gilt der Kontakt als verloren (False = entfernen)."""
        self.confidence = max(
            0.0, self.confidence - config.SONAR_CONF_DECAY_PER_S * dt)
        if (t - self.last_seen >= config.SONAR_CONTACT_LOST_S
                and self.confidence <= 0.15):
            return False
        return True

    @property
    def positioned(self) -> bool:
        return self.range_est is not None

    @property
    def display_label(self) -> str:
        return config.PLAYER_CLASS_LABELS.get(self.player_class, "Unbekannt")


class SonarSystem:
    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed + 1000)
        self.contacts: dict[int, Contact] = {}
        self._tracks: dict[int, BearingTrack] = {}
        self._next_contact_id = 1
        self.ping_cooldown = 0.0
        self.ping_active = False
        self._ping_anim_timer = 0.0
        self.lofar_history: list = []   # Spalten à LOFAR_BINS (0..1)
        self._lofar_timer = 0.0
        self._tma_versions: dict[int, int] = {}  # TMA-Re-Solve nur bei neuen Peilungen
        self._tma_next: dict[int, float] = {}    # + Throttle: max. alle TMA_RESOLVE_EVERY_S
        self._pending_pings: list[dict] = []
        self.demon_analysis = None
        self.signature_candidates = []
        self.gain_db = 0.0
        self.band_low_hz = 0.0
        self.band_high_hz = config.LOFAR_FMAX_HZ
        self.notch_enabled = False
        self.peak_hold = False
        self.focus_locked = False
        self.tma_enabled = True
        self.listen_bearing = 0.0
        self.beam_width_deg = 12.0
        self.listen_filtered = False
        self.receiver = AcousticReceiver(seed)
        self.broadband_history = []
        self.history_times = []
        self.lofar_times = []
        self.lofar_bearings = []
        self.peak_spectrum = []
        self._listen_target_id = None
        self._receiver_mode = "BOW"
        self._own_line_hz = 10.0
        self.towed_depth_m = config.SONAR_TOWED_DEPTH_M
        self.towed_depth_target_m = config.SONAR_TOWED_DEPTH_M
        self.bt_profile = None
        self.bt_cooldown = 0.0
        self.echo_events = []

    def adjust_towed_depth(self, delta_m: float, ship_speed: float) -> float:
        limit = max(config.SONAR_TOWED_DEPTH_MIN_M,
                    config.SONAR_TOWED_DEPTH_MAX_M
                    - ship_speed * config.SONAR_TOWED_SPEED_SHALLOW_M_PER_KN)
        self.towed_depth_target_m = config.clamp(
            self.towed_depth_target_m + delta_m,
            config.SONAR_TOWED_DEPTH_MIN_M, limit)
        return self.towed_depth_target_m

    def measure_environment(self, world, frigate, t: float) -> bool:
        """Take a noisy expendable-bathythermograph style sound profile."""
        if self.bt_cooldown > 0.0:
            return False
        water_depth = world.depth_m(frigate.x, frigate.y)
        true_thermo = world.thermocline_depth_m(frigate.x, frigate.y)
        measured_thermo = config.clamp(true_thermo + self.rng.uniform(-3.0, 3.0),
                                       20.0, water_depth)
        max_depth = min(water_depth, 400.0)
        depths = np.linspace(0.0, max_depth, 21)
        speeds = []
        for depth in depths:
            # Synthetic game profile: cooling dominates above the layer,
            # pressure dominates below it. Values are model evidence, not charts.
            speed = (1504.0 - .018 * min(depth, measured_thermo)
                     + .012 * max(0.0, depth - measured_thermo))
            speeds.append(speed + self.rng.uniform(-.15, .15))
        self.bt_profile = dict(t=t, x=frigate.x, y=frigate.y,
                               thermocline_m=measured_thermo,
                               water_depth_m=water_depth,
                               sea_state=world.sea_state,
                               depths_m=depths.tolist(), speeds_m_s=speeds,
                               cz_bands_nm=[list(band) for band in config.CZ_BANDS])
        self.bt_cooldown = config.SONAR_BT_COOLDOWN_S
        return True

    def set_listen_bearing(self, bearing: float) -> None:
        """Manual steering never follows a hidden target or changes ship course."""
        self.listen_bearing = bearing % 360.0
        self.focus_locked = False
        self._listen_target_id = None
        self.reset_listening_history()

    def reset_listening_history(self) -> None:
        """Do not show a previous beam's spectra under a new bearing label."""
        self.receiver.reset()
        self.lofar_history.clear()
        self.lofar_times.clear()
        self.lofar_bearings.clear()
        self.peak_spectrum = []
        self.demon_analysis = None
        self.signature_candidates = []

    def listening_samples(self):
        """Same beam as the instruments; optional operator-band audition."""
        samples = self.receiver.samples.copy()
        if self.listen_filtered:
            frequencies = np.fft.rfftfreq(len(samples), 1.0 / self.receiver.sample_rate)
            spectrum = np.fft.rfft(samples)
            spectrum[(frequencies < self.band_low_hz) | (frequencies > self.band_high_hz)] = 0
            if self.notch_enabled:
                spectrum[abs(frequencies - self._own_line_hz) < 5] *= .15
            samples = np.fft.irfft(spectrum, n=len(samples))
        return np.clip(samples * 10 ** (self.gain_db / 20), -1, 1).astype(np.float32)

    @property
    def ping_ready(self) -> bool:
        return self.ping_cooldown <= 0.0

    @property
    def ping_cooldown_remaining(self) -> float:
        return max(0.0, self.ping_cooldown)

    def fire_ping(self) -> bool:
        if not self.ping_ready:
            return False
        self.ping_cooldown = config.SONAR_PING_COOLDOWN_S
        self.ping_active = True
        self._ping_anim_timer = 1.5
        return True

    def queue_ping(self, frigate, targets, world, t_real: float,
                   range_factor: float = 1.0, mode: str = "BOW") -> None:
        """Plant Echoantworten; Warnung entsteht beim Aussenden, nicht beim Echo."""
        for target in targets:
            if tgt_gone(target):
                continue
            distance = target.distance_nm(frigate)
            if distance <= config.SONAR_PING_HEAR_RANGE_NM \
                    and hasattr(target, "hear_ping"):
                target.hear_ping()
            self._pending_pings.append({
                "target": target,
                "frigate": frigate,
                "world": world,
                "sent_at": t_real,
                "ready_at": t_real + world.echo_delay_s(distance),
                "range_factor": range_factor,
                "mode": mode,
            })

    def passive_range_nm(self, tgt, dist_nm: float, frigate, world,
                         range_factor: float, mode: str) -> float:
        """Effektive passive Reichweite R_eff (SNR-Grundlage)."""
        passive_range = frigate.passive_sonar_range_nm(
            tgt.quiet_factor(), world.sea_state)
        thermo = world.thermocline_depth_m(tgt.x, tgt.y)
        sensor_depth = self.towed_depth_m if mode == "TOWED" else 5.0
        same_layer = (sensor_depth < thermo) == (tgt.depth < thermo)
        passive_range *= (config.SONAR_THERMO_PASSIVE_ABOVE if same_layer
                          else config.SONAR_THERMO_PASSIVE_BELOW)
        if mode == "TOWED":
            arr = max(0.5, config.SONAR_ARRAY_TOWED_PASSIVE
                      - config.SONAR_TOWED_SPEED_PENALTY * frigate.speed)
            passive_range *= arr
            # A deep array gains most when it occupies the target's layer.
            if same_layer and self.towed_depth_m >= 30.0:
                passive_range *= config.SONAR_TOWED_DEEP_BONUS
        passive_range *= range_factor
        for lo, hi in config.CZ_BANDS:
            if lo <= dist_nm <= hi:
                passive_range += config.CZ_BONUS_NM
                break
        return passive_range

    def update(self, dt: float, t: float, frigate, targets, world,
               range_factor: float = 1.0, mode: str = "BOW",
               buoys=(), focus_tgt=None, own_cavitation: float = 0.0):
        """Passives Hören (dt/t in sim-Sekunden).

        targets: Sub/Animal/Decoy/SurfaceShip/EnemyTorpedo (Duck-Types).
        """
        self.ping_cooldown = max(0.0, self.ping_cooldown - dt)
        self.bt_cooldown = max(0.0, self.bt_cooldown - dt)
        depth_limit = max(config.SONAR_TOWED_DEPTH_MIN_M,
                          config.SONAR_TOWED_DEPTH_MAX_M
                          - frigate.speed * config.SONAR_TOWED_SPEED_SHALLOW_M_PER_KN)
        self.towed_depth_target_m = min(self.towed_depth_target_m, depth_limit)
        depth_step = config.SONAR_TOWED_DEPTH_RATE_M_S * dt
        self.towed_depth_m += config.clamp(
            self.towed_depth_target_m - self.towed_depth_m,
            -depth_step, depth_step)
        self._process_pending_pings(t)
        if self._ping_anim_timer > 0:
            self._ping_anim_timer -= dt
            if self._ping_anim_timer <= 0:
                self.ping_active = False

        detected_ids: set = set()
        self._lofar_timer += dt
        sample_due = self._lofar_timer + 1e-9 >= self.receiver.block_s
        sources = []
        self._own_line_hz = 10.0 + 1.9 * frigate.speed
        if mode != self._receiver_mode:
            self._receiver_mode = mode
            self.beam_width_deg = 6.0 if mode == "TOWED" else 12.0
            self.reset_listening_history()
        for tgt in targets:
            if tgt_gone(tgt):
                continue
            dist = tgt.distance_nm(frigate)
            true_bearing = tgt.bearing_from_frigate(frigate)
            observations = {}
            for array_mode in ("BOW", "TOWED"):
                r_eff = self.passive_range_nm(tgt, dist, frigate, world,
                                              range_factor, array_mode)
                if dist >= r_eff:
                    continue
                s_db = snr_db(r_eff, dist)
                quality = config.clamp(
                    s_db / config.SONAR_SNR_QUALITY_SPAN_DB, 0.0, 1.0)
                bearing = self._observed_bearing(
                    tgt, true_bearing, frigate, quality, array_mode, t)
                observations[array_mode] = dict(
                    bearing=bearing, quality=quality, snr=s_db, last_seen=t)
            if not observations:
                continue
            c = self._get_contact(tgt)
            c._fx, c._fy = frigate.x, frigate.y
            c.array_observations.update(observations)
            c.array_observations = {
                key: value for key, value in c.array_observations.items()
                if t - value["last_seen"] <= 4.0}
            primary = observations.get(mode) or max(
                observations.values(), key=lambda item: item["quality"])
            bearing = primary["bearing"]
            quality = primary["quality"]
            s_db = primary["snr"]
            bow = c.array_observations.get("BOW")
            towed = c.array_observations.get("TOWED")
            if bow is not None and towed is not None:
                delta = abs(config.angle_diff_deg(bow["bearing"], towed["bearing"]))
                c.fusion_delta_deg = delta
                if delta <= config.SONAR_FUSION_CONFIRM_DEG:
                    c.fusion_status = "BESTAETIGT"
                    x = (math.sin(math.radians(bow["bearing"])) * bow["quality"]
                         + math.sin(math.radians(towed["bearing"])) * towed["quality"])
                    y = (math.cos(math.radians(bow["bearing"])) * bow["quality"]
                         + math.cos(math.radians(towed["bearing"])) * towed["quality"])
                    bearing = math.degrees(math.atan2(x, y)) % 360.0
                    quality = min(1.0, max(bow["quality"], towed["quality"]) + .1)
                elif delta >= config.SONAR_FUSION_DIVERGENT_DEG:
                    c.fusion_status = "DIVERGENT / GEISTERKONTAKT?"
                    quality *= .65
                else:
                    c.fusion_status = "UNSICHER"
                c.fused_quality = quality
            else:
                c.fusion_status = "NUR " + next(iter(observations))
                c.fusion_delta_deg = None
                c.fused_quality = quality
            sig = ""
            if c.confidence + config.SONAR_CONF_PASSIVE_PER_S * dt \
                    >= config.CONTACT_SIG_CONF:
                sig = tgt.acoustic_signature()
            c.update_passive(
                bearing=bearing,
                confidence=c.confidence + config.SONAR_CONF_PASSIVE_PER_S * dt,
                quality=quality,
                signature=sig,
                t=t,
                snr=s_db)
            # W1: Peilungs-Track (TMA-Datenbasis)
            tr = self._tracks.setdefault(tgt.id, BearingTrack())
            tr.add(t, bearing, frigate.x, frigate.y, frigate.course)
            detected_ids.add(tgt.id)
            listen_observation = observations.get(mode)
            if sample_due and listen_observation is not None:
                broadband = getattr(tgt, "broadband", lambda: {})()
                source = {"bearing": bearing, "level": quality,
                          "lines": tgt.lofar_lines(t),
                          "seed": getattr(tgt, "sensor_seed", tgt.id)}
                if isinstance(broadband, dict) and broadband.get("level", 0) > 0:
                    source["broadband"] = broadband
                sources.append(source)

        # Bojen messen von ihrer eigenen Position. Erst zwei Peilstrahlen
        # liefern eine an die Fregatte übertragbare Positionslösung.
        active_buoys = [b for b in buoys if getattr(b, "active", False)]
        for tgt in targets:
            if tgt_gone(tgt):
                continue
            reports = []
            for b in active_buoys:
                dist = math.hypot(tgt.x - b.x, tgt.y - b.y)
                if dist >= config.BUOY_RANGE_NM:
                    continue
                quality = config.clamp(1.0 - dist / config.BUOY_RANGE_NM,
                                       .2, .9)
                if tgt.depth > world.thermocline_depth_m(b.x, b.y):
                    quality *= .55
                true_bearing = math.degrees(
                    math.atan2(tgt.x - b.x, -(tgt.y - b.y))) % 360.0
                rng = random.Random(getattr(tgt, "sensor_seed", tgt.id) * 1543
                                    + b.seq * 7919 + int(t // 2.0))
                error = 2.0 + 5.0 * (1.0 - quality)
                reports.append((b, (true_bearing + rng.uniform(-error, error))
                                % 360.0, quality))
            if len(reports) < 2:
                continue
            pair = max(((a, b) for i, a in enumerate(reports)
                        for b in reports[i + 1:]),
                       key=lambda pair: math.hypot(pair[0][0].x - pair[1][0].x,
                                                   pair[0][0].y - pair[1][0].y))
            fix = self._bearing_fix(pair[0], pair[1])
            if fix is None:
                continue
            fx, fy, geometry = fix
            c = self._get_contact(tgt)
            c._fx, c._fy = frigate.x, frigate.y
            ping_fresh = (c.range_source == "ping" and c.range_seen is not None
                          and t - c.range_seen <= config.SONAR_PING_FIX_MAX_AGE_S)
            if ping_fresh:
                c.confidence = min(1.0, c.confidence
                                   + config.SONAR_CONF_PASSIVE_PER_S * dt)
                c.last_seen = t
                detected_ids.add(tgt.id)
                continue
            bearing = math.degrees(math.atan2(fx - frigate.x,
                                               -(fy - frigate.y))) % 360.0
            quality = min(pair[0][2], pair[1][2]) * geometry
            sig = tgt.acoustic_signature() \
                if c.confidence >= config.CONTACT_SIG_CONF else ""
            c.update_passive(
                bearing=bearing,
                confidence=c.confidence + config.SONAR_CONF_PASSIVE_PER_S * dt,
                quality=quality, signature=sig, t=t, snr=0.0)
            c.range_est = math.hypot(fx - frigate.x, fy - frigate.y)
            c.range_sigma_nm = max(.5, (1.0 - quality) * 8.0)
            c.range_source = "buoy"
            c.range_seen = t
            c.origin = "bojenkreuzpeilung"
            detected_ids.add(tgt.id)

        # M9: Kontakte ohne neue Detektion verfallen
        for cid in list(self.contacts):
            if cid not in detected_ids:
                self._decay_contact(cid, dt, t)

        # W1: TMA für den fokussierten Kontakt
        if (self.tma_enabled and focus_tgt is not None and not tgt_gone(focus_tgt)
                and focus_tgt.id in self.contacts):
            self._update_tma(focus_tgt, t)

        if self.focus_locked:
            contact = self.contacts.get(getattr(focus_tgt, "id", None))
            if contact is not None and t - contact.last_seen <= 2.0:
                if contact.target_id != self._listen_target_id:
                    self.reset_listening_history()
                    self._listen_target_id = contact.target_id
                self.listen_bearing = contact.bearing
            else:
                # Lost tracks hold the last observed direction, not world truth.
                self.focus_locked = False
                self._listen_target_id = None

        while self._lofar_timer + 1e-9 >= self.receiver.block_s:
            self._lofar_timer = max(0.0, self._lofar_timer - self.receiver.block_s)
            self.receiver.update(sources, self.listen_bearing, self.beam_width_deg,
                                 frigate.noise_level(), world.sea_state, frigate.speed,
                                 own_cavitation=own_cavitation)
            stamp = t - self._lofar_timer
            self.broadband_history.append(list(self.receiver.broadband))
            self.history_times.append(stamp)
            self.lofar_history.append(list(self.receiver.spectrum))
            self.lofar_times.append(stamp)
            self.lofar_bearings.append(self.listen_bearing)
            for history in (self.broadband_history, self.history_times, self.lofar_history,
                            self.lofar_times, self.lofar_bearings):
                del history[:-config.LOFAR_HISTORY_COLS]
            if self.peak_hold:
                self.peak_spectrum = (np.maximum(self.peak_spectrum, self.receiver.spectrum).tolist()
                                      if self.peak_spectrum else list(self.receiver.spectrum))
            else:
                self.peak_spectrum = []
            self._update_signature_analysis()

    @staticmethod
    def _bearing_fix(first, second):
        b1, bearing1, _ = first
        b2, bearing2, _ = second
        a1, a2 = math.radians(bearing1), math.radians(bearing2)
        r = (math.sin(a1), -math.cos(a1))
        s = (math.sin(a2), -math.cos(a2))
        denom = r[0] * s[1] - r[1] * s[0]
        geometry = abs(denom)
        if geometry < math.sin(math.radians(10.0)):
            return None
        qx, qy = b2.x - b1.x, b2.y - b1.y
        along_first = (qx * s[1] - qy * s[0]) / denom
        along_second = (qx * r[1] - qy * r[0]) / denom
        if along_first < 0.0 or along_second < 0.0:
            return None
        return b1.x + along_first * r[0], b1.y + along_first * r[1], geometry

    def _update_signature_analysis(self) -> None:
        """Classify measured beam features, never the hidden platform key."""
        self.demon_analysis = self.receiver.demon_analysis
        self.signature_candidates = []
        if self.demon_analysis is None:
            return
        data = self.demon_analysis
        self.signature_candidates = rank_signatures(
            data["blade_rate_hz"], None, data["tonal_hz"], data["cavitation"])

    def process_lofar_column(self, column, frigate) -> list:
        """Apply operator gain and frequency controls to one LOFAR column."""
        gain = 10.0 ** (self.gain_db / 20.0)
        shaft = 10.0 + 1.9 * frigate.speed
        result = []
        for index, value in enumerate(column):
            freq = config.lofar_bin_freq(index)
            if not self.band_low_hz <= freq <= self.band_high_hz:
                result.append(0.0)
                continue
            if self.notch_enabled and abs(freq - shaft) < 5.0:
                result.append(value * 0.15)
            else:
                result.append(min(1.0, value * gain))
        return result

    def _process_pending_pings(self, t: float) -> None:
        """Liefert faellige Echos einzeln aus, damit Mehrfachziele Laufzeit haben."""
        pending = []
        for ping in self._pending_pings:
            target = ping["target"]
            if tgt_gone(target):
                continue
            if t >= ping["ready_at"]:
                contacts = self.apply_ping(
                    ping["frigate"], [target], ping["world"], t,
                    ping["range_factor"], ping["mode"])
                for contact in contacts:
                    self.echo_events.append(dict(
                        t=t, contact_id=contact.id, bearing=contact.bearing,
                        range_nm=contact.range_est, depth_m=contact.depth_est))
            else:
                pending.append(ping)
        self._pending_pings = pending

    def _observed_bearing(self, tgt, true_bearing: float, frigate,
                          quality: float, mode: str, t: float) -> float:
        """Peilung mit deterministischem Fehler (stabil je 2 sim-s)."""
        err = bearing_error_deg(mode, frigate.speed, quality)
        rng = random.Random(getattr(tgt, "sensor_seed", tgt.id) * 7919
                             + int(t // 2.0))
        return (true_bearing + rng.uniform(-err, err)) % 360.0

    def _update_tma(self, tgt, t: float) -> None:
        """TMA nur neu lösen, wenn der Peilungs-Track neue Punkte hat
        (version-Gate) – sonst läuft die Gittersuche jeden Substep und
        verzögert das ganze Spiel (LOFAR 'hängt')."""
        tr = self._tracks.get(tgt.id)
        if tr is None:
            return
        if self._tma_versions.get(tgt.id) == tr.version:
            return
        if t < self._tma_next.get(tgt.id, 0.0):
            return  # Throttle: waehlt naechstes Re-Solve-Fenster ab
        c = self.contacts.get(tgt.id)
        if c is None:
            return
        sol = solve_tma(tr)
        if sol is not None:
            c.update_tma(sol, t)
        self._tma_versions[tgt.id] = tr.version
        self._tma_next[tgt.id] = t + config.TMA_RESOLVE_EVERY_S

    def apply_ping(self, frigate, targets, world, t_real: float,
                   range_factor: float = 1.0, mode: str = "BOW"):
        """Ping-Echo berechnen (wird nach fire_ping aufgerufen)."""
        ping_mult = (config.SONAR_ARRAY_TOWED_PING if mode == "TOWED"
                     else config.SONAR_ARRAY_BOW_PING)
        contacts = []
        for tgt in targets:
            if tgt_gone(tgt):
                continue
            dist = tgt.distance_nm(frigate)
            bearing = tgt.bearing_from_frigate(frigate)
            thermo = world.thermocline_depth_m(tgt.x, tgt.y)
            above_thermo = tgt.depth < thermo

            # Hört das U-Boot den Ping?
            if dist <= config.SONAR_PING_HEAR_RANGE_NM and hasattr(tgt, "hear_ping"):
                tgt.hear_ping()

            # Echo erhalten?
            active_range = config.SONAR_ACTIVE_BASE_NM * ping_mult
            if not above_thermo:
                active_range *= config.SONAR_THERMO_ACTIVE_BELOW
            sea_penalty = 1.0 - 0.03 * world.sea_state
            active_range *= sea_penalty * range_factor

            if dist < active_range:
                c = self._get_contact(tgt)
                c._fx, c._fy = frigate.x, frigate.y
                signal = snr_db(active_range, dist)
                error_scale = 1.0 / max(1.0, 1.0 + signal / 8.0)
                measured_bearing = (bearing + self.rng.uniform(
                    -1.5, 1.5) * error_scale) % 360.0
                measured_range = max(0.0, dist + self.rng.uniform(
                    -0.18, 0.18) * error_scale)
                measured_depth = max(0.0, tgt.depth + self.rng.uniform(
                    -12.0, 12.0) * error_scale)
                c.update_ping(
                    bearing=measured_bearing,
                    range_est=measured_range,
                    depth_est=measured_depth,
                    confidence=c.confidence + config.SONAR_CONF_PING_BONUS,
                    t=t_real,
                    snr=signal)
                contacts.append(c)
        return contacts

    def _get_contact(self, tgt) -> Contact:
        cid = tgt.id
        if cid not in self.contacts:
            if hasattr(tgt, "torpedo_class"):
                kind = "torpedo"
            elif hasattr(tgt, "stype"):
                kind = "sub"
            elif getattr(tgt, "kind", None) == "decoy":
                kind = "decoy"
            elif hasattr(tgt, "signature_key"):
                kind = "surface"
            else:
                kind = "animal"
            c = Contact(contact_id=self._next_contact_id,
                        target_id=cid, origin="passiv", kind=kind)
            c._fx = 0.0
            c._fy = 0.0
            self.contacts[cid] = c
            self._next_contact_id += 1
        return self.contacts[cid]

    def _decay_contact(self, cid: int, dt: float, t: float):
        c = self.contacts.get(cid)
        if c is None:
            return
        if not c.decay(dt, t):
            del self.contacts[cid]
            self._tracks.pop(cid, None)
            self._tma_versions.pop(cid, None)
            self._tma_next.pop(cid, None)

    def active_contacts(self) -> list:
        return list(self.contacts.values())
