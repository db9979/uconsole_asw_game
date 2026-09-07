"""W1: Sonar-System – SNR-Modell, Peilfehler, TMA, LOFAR-Wasserfall.

Passiv: nur Peilung (± Peilfehler je Array/Eigenfahrt/Qualität).
TMA: Peilungsreihe + Fregattenmanöver -> Position + Geschwindigkeit.
Aktiv: Ping -> exakte Distanz + Tiefe (verrät Position).
"""

import math
import random
from enum import Enum

import numpy as np

from src.core import config
from src.sonar.tma import BearingTrack, solve_tma
from src.audio.database import rank_signatures
from src.audio.receiver import AcousticReceiver, directional_gain


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


def _correlated_uniform(seed: int, t: float, epoch_s: float,
                        salt: int = 0) -> float:
    """Deterministic smooth noise in [-1, 1], reconstructable from epoch/time."""
    scaled = max(0.0, t) / epoch_s
    epoch = math.floor(scaled)
    fraction = scaled - epoch
    blend = fraction * fraction * (3.0 - 2.0 * fraction)
    first = random.Random(seed * 7919 + epoch * 104729 + salt).uniform(-1, 1)
    second = random.Random(seed * 7919 + (epoch + 1) * 104729 + salt).uniform(-1, 1)
    return first + (second - first) * blend


class TowState(str, Enum):
    STOWED = "STOWED"
    DEPLOYING = "DEPLOYING"
    STREAMED = "STREAMED"
    RETRIEVING = "RETRIEVING"
    FAULT = "FAULT"


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
        self.passive_bearing = None
        self.raw_bearing = None
        self.raw_bearings = []
        self.bearing_uncertainty_deg = None
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
        self.tma_seen = None
        self.buoy_fixes = []  # raw (t, x, y, quality), not ownship passive bearings
        self.ping_pos = None
        self.observed_x = None
        self.observed_y = None
        self._passive_epoch = None
        self._bearing_filter_t = None
        self._bearing_filter_rate_deg_s = 0.0
        self._bearing_filter_uncertainty_deg = None
        self._fx = 0.0
        self._fy = 0.0
        self.array_observations = {}
        self.fusion_status = "KEINE DATEN"
        self.fusion_delta_deg = None
        self.fused_quality = 0.0

    def update_passive(self, bearing: float, confidence: float,
                       quality: float, signature: str, t: float,
                       snr: float = 0.0,
                       bearing_uncertainty_deg: float = None):
        """Passives Hören: nur (fehlerbehaftete) Peilung."""
        raw = bearing % 360.0
        self.raw_bearing = raw
        epoch = math.floor((t + 1e-9) / config.SONAR_BEARING_NOISE_EPOCH_S)
        uncertainty = (max(0.25, (1.0 - quality) * config.BEARING_ERR_BOW_DEG)
                       if bearing_uncertainty_deg is None
                       else max(0.05, bearing_uncertainty_deg))
        if epoch != self._passive_epoch:
            self.raw_bearings.append((t, raw, uncertainty))
            del self.raw_bearings[:-config.BEARING_TRACK_MAX_PTS]
            self._passive_epoch = epoch
        if self.passive_bearing is None:
            self.passive_bearing = raw
            self._bearing_filter_uncertainty_deg = uncertainty
            self._bearing_filter_t = t
            self._bearing_filter_rate_deg_s = 0.0
        elif self._bearing_filter_t is None:
            # Legacy saves have a presentation bearing but no causal rate state.
            self._bearing_filter_t = t
            self._bearing_filter_rate_deg_s = 0.0
            if self._bearing_filter_uncertainty_deg is None:
                self._bearing_filter_uncertainty_deg = (
                    self.bearing_uncertainty_deg or uncertainty)
        elif t > self._bearing_filter_t:
            dt = t - self._bearing_filter_t
            alpha = 1.0 - math.exp(-dt / config.SONAR_BEARING_DISPLAY_TAU_S)
            beta = alpha * alpha / max(1e-6, 2.0 - alpha)
            self._bearing_filter_rate_deg_s *= math.exp(
                -dt / config.SONAR_BEARING_DISPLAY_TAU_S)
            predicted = (self.passive_bearing
                         + self._bearing_filter_rate_deg_s * dt) % 360.0
            innovation = config.angle_diff_deg(raw, predicted)
            self.passive_bearing = (predicted + alpha * innovation) % 360.0
            self._bearing_filter_rate_deg_s = config.clamp(
                self._bearing_filter_rate_deg_s + beta * innovation / dt,
                -config.SONAR_BEARING_RATE_MAX_DEG_S,
                config.SONAR_BEARING_RATE_MAX_DEG_S)
            prior_uncertainty = max(
                0.05, self._bearing_filter_uncertainty_deg or uncertainty)
            self._bearing_filter_uncertainty_deg = math.sqrt(
                (1.0 - alpha) * prior_uncertainty * prior_uncertainty
                + alpha * (uncertainty * uncertainty
                           + (1.0 - alpha) * innovation * innovation))
            self._bearing_filter_t = t
        self.confidence = min(1.0, confidence)
        self.quality = min(1.0, quality)
        self.last_seen = t
        self.snr = snr
        self.expire_ping_fix(t)
        if self.range_source == "ping" and self.ping_pos is None \
                and self.range_est is not None:
            # Legacy saves did not retain the Cartesian active fix.
            self.ping_pos = (
                self._fx + self.range_est * math.sin(math.radians(self.bearing)),
                self._fy - self.range_est * math.cos(math.radians(self.bearing)))
        if self.range_source == "ping" and self.ping_pos is not None:
            self.observed_x, self.observed_y = self.ping_pos
        elif self.range_source == "tma" and self.tma_pos is not None:
            self.observed_x, self.observed_y = self.tma_pos
        if self.observed_x is not None and self.observed_y is not None:
            self.bearing = math.degrees(math.atan2(
                self.observed_x - self._fx, -(self.observed_y - self._fy))) % 360.0
            self.range_est = math.hypot(self.observed_x - self._fx,
                                        self.observed_y - self._fy)
        elif self.range_source not in ("ping", "tma", "buoy"):
            self.bearing = self.passive_bearing
            self.bearing_uncertainty_deg = self._bearing_filter_uncertainty_deg
        if signature:
            self.signature = signature

    def update_ping(self, bearing: float, range_est: float, depth_est: float,
                    confidence: float, t: float, snr: float = 0.0,
                    range_sigma_nm: float = None, depth_sigma_m: float = None):
        """Aktiver Ping: liefert Position + Tiefe (maßstabsgenau)."""
        self.bearing = bearing % 360.0
        self.raw_bearing = self.bearing
        self.bearing_uncertainty_deg = 1.5 / math.sqrt(3)
        self.range_est = range_est
        self.range_sigma_nm = (config.SONAR_PING_RANGE_ERROR_NM / math.sqrt(3)
                               if range_sigma_nm is None else max(1e-6, range_sigma_nm))
        self.range_source = "ping"
        self.range_seen = t
        self.depth_est = depth_est
        self.depth_sigma_m = (config.SONAR_PING_DEPTH_ERROR_M / math.sqrt(3)
                              if depth_sigma_m is None else max(1e-6, depth_sigma_m))
        self.origin = "ping"
        self.confidence = min(1.0, confidence)
        self.quality = 1.0
        self.last_seen = t
        self.snr = snr
        self.ping_pos = (
            self._fx + range_est * math.sin(math.radians(self.bearing)),
            self._fy - range_est * math.cos(math.radians(self.bearing)))
        self.observed_x, self.observed_y = self.ping_pos

    def expire_ping_fix(self, t: float) -> None:
        """Expire evidence even without detections (name retained for callers).

        TMA/buoy positions and TMA motion are usable for at most
        SONAR_CONTACT_LOST_S since their measurement, not last passive hearing.
        The uncertainty fields for these estimates are heuristic, not covariance.
        """
        tma_seen = self.tma_seen
        if tma_seen is None and self.range_source == "tma":
            tma_seen = self.range_seen  # pre-evidence saves
        if (self.tma_pos is not None or self.tma_course is not None
                or self.tma_speed is not None) and (tma_seen is None or
                t - tma_seen > config.SONAR_CONTACT_LOST_S):
            self.tma_pos = self.tma_course = self.tma_speed = None
            self.tma_quality = 0.0
            self.tma_seen = None
        max_age = (config.SONAR_PING_FIX_MAX_AGE_S
                   if self.range_source == "ping" else config.SONAR_CONTACT_LOST_S)
        if self.range_source is not None and (self.range_seen is None
                or t - self.range_seen > max_age):
            self.range_est = None
            self.range_sigma_nm = None
            self.range_source = None
            self.depth_est = None
            self.depth_sigma_m = None
            self.observed_x = self.observed_y = None
            self.ping_pos = None
            if self.passive_bearing is not None:
                self.bearing = self.passive_bearing
                self.bearing_uncertainty_deg = \
                    self._bearing_filter_uncertainty_deg
        self.array_observations = {
            key: value for key, value in self.array_observations.items()
            if t - value["last_seen"] <= 4.0}
        if len(self.array_observations) < 2:
            self.fusion_status = ("NUR " + next(iter(self.array_observations))
                                  if self.array_observations else "KEINE DATEN")
            self.fusion_delta_deg = None
            self.fused_quality = max((report["quality"] for report in
                                      self.array_observations.values()), default=0.0)

    def update_buoy(self, x: float, y: float, quality: float, t: float):
        """Keep raw cross-fixes separate; smooth only the public position.

        Fresh ping > fresh buoy > TMA avoids source flapping. The filter is a
        bounded convex blend, with no velocity extrapolation or covariance claim.
        """
        self.expire_ping_fix(t)
        if not self.buoy_fixes or int(t // 2) != int(self.buoy_fixes[-1][0] // 2):
            self.buoy_fixes.append((t, x, y, quality))
            del self.buoy_fixes[:-config.BEARING_TRACK_MAX_PTS]
        if self.range_source == "ping":
            return
        if (self.range_source == "buoy" and self.observed_x is not None
                and self.observed_y is not None and self.range_seen is not None):
            alpha = 1.0 - math.exp(-max(0.0, t - self.range_seen)
                                   / config.SONAR_BEARING_DISPLAY_TAU_S)
            x = self.observed_x + alpha * (x - self.observed_x)
            y = self.observed_y + alpha * (y - self.observed_y)
        self.observed_x, self.observed_y = x, y
        self.bearing = math.degrees(math.atan2(x - self._fx, -(y - self._fy))) % 360
        self.range_est = math.hypot(x - self._fx, y - self._fy)
        self.range_sigma_nm = max(.5, (1.0 - quality) * 8.0)
        self.bearing_uncertainty_deg = None
        self.depth_est = self.depth_sigma_m = None
        self.range_source = "buoy"
        self.range_seen = t
        self.origin = "bojenkreuzpeilung"

    def update_tma(self, sol, t: float):
        """TMA-Estimate übernehmen (nur, solange kein frischerer Ping)."""
        self.expire_ping_fix(t)
        if (self.tma_pos is not None
                and self.tma_quality >= config.TMA_RANGE_MIN_QUALITY
                and sol.quality < config.TMA_RANGE_MIN_QUALITY):
            return
        alpha = config.TMA_PRESENTATION_ALPHA
        if self.tma_pos is None:
            self.tma_pos = tuple(sol.pos)
            self.tma_course = sol.course
            self.tma_speed = sol.speed
            self.tma_quality = sol.quality
        else:
            self.tma_pos = (self.tma_pos[0] + (sol.pos[0] - self.tma_pos[0]) * alpha,
                            self.tma_pos[1] + (sol.pos[1] - self.tma_pos[1]) * alpha)
            if self.tma_course is None:
                self.tma_course = sol.course
            else:
                self.tma_course = (self.tma_course + config.angle_diff_deg(
                    sol.course, self.tma_course) * alpha) % 360.0
            if self.tma_speed is None:
                self.tma_speed = sol.speed
            else:
                self.tma_speed += (sol.speed - self.tma_speed) * alpha
            self.tma_quality += (sol.quality - self.tma_quality) * alpha
        self.tma_seen = t
        if self.range_source not in ("ping", "buoy") and \
                sol.quality >= config.TMA_RANGE_MIN_QUALITY:
            self.observed_x, self.observed_y = self.tma_pos
            self.bearing = math.degrees(math.atan2(
                self.observed_x - self._fx, -(self.observed_y - self._fy))) % 360.0
            self.range_est = math.hypot(self.observed_x - self._fx,
                                        self.observed_y - self._fy)
            self.range_sigma_nm = max(0.1, (1.0 - sol.quality) * 12.0)
            self.range_source = "tma"
            self.range_seen = t
            self.bearing_uncertainty_deg = None
            self.depth_est = self.depth_sigma_m = None

    def decay(self, dt: float, t: float) -> bool:
        """Konfidenz sinkt ohne neue Detektion; nach Zeit + niedriger
        Konfidenz gilt der Kontakt als verloren (False = entfernen)."""
        self.expire_ping_fix(t)
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
    MAX_PENDING_PINGS = 10000
    STOWED = TowState.STOWED
    DEPLOYING = TowState.DEPLOYING
    STREAMED = TowState.STREAMED
    RETRIEVING = TowState.RETRIEVING
    FAULT = TowState.FAULT

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
        self.tow_state = TowState.STOWED
        self.tow_payout = 0.0
        self.tow_heading_deg = 0.0
        self._tow_settle_s = 0.0
        self._tow_handling_ok = True
        self.bt_profile = None
        self.bt_cooldown = 0.0
        self.echo_events = []
        self.echo_history = []

    def toggle_tow(self, ship_speed: float = 0.0) -> bool:
        """Start/reverse array handling; progress pauses outside its envelope."""
        if self.tow_state == TowState.FAULT:
            return False
        if self.tow_state in (TowState.STOWED, TowState.RETRIEVING):
            self.tow_state = TowState.DEPLOYING
        else:
            self.tow_state = TowState.RETRIEVING
        self._tow_handling_ok = self._tow_speed_ok(ship_speed)
        self._tow_settle_s = 0.0
        return True

    @staticmethod
    def _tow_speed_ok(ship_speed: float) -> bool:
        return (config.SONAR_TOWED_HANDLING_MIN_KN <= ship_speed
                <= config.SONAR_TOWED_HANDLING_MAX_KN)

    def _tow_available(self) -> bool:
        return (self.tow_state == TowState.STREAMED
                and self.tow_payout >= config.SONAR_TOWED_AVAILABLE_PAYOUT)

    @property
    def tow_performance(self) -> float:
        """0..1 TAS benefit; full benefit requires streamed and settled cable."""
        if self.tow_state != TowState.STREAMED:
            return 0.0
        stability = config.clamp(
            self._tow_settle_s / config.SONAR_TOWED_SETTLE_S, 0.0, 1.0)
        return stability * config.clamp(self.tow_payout, 0.0, 1.0)

    def tow_status(self, ship_speed: float = None) -> dict:
        handling_ok = self._tow_handling_ok if ship_speed is None else \
            self._tow_speed_ok(ship_speed)
        return {
            "state": getattr(self.tow_state, "value", self.tow_state),
            "payout": self.tow_payout,
            "payout_percent": round(self.tow_payout * 100.0, 1),
            "available": self._tow_available(),
            "handling_ok": handling_ok,
            "performance": self.tow_performance,
            "depth_m": self.towed_depth_m,
            "depth_target_m": self.towed_depth_target_m,
            "heading_deg": self.tow_heading_deg,
        }

    def adjust_towed_depth(self, delta_m: float, ship_speed: float) -> float:
        if self.tow_state != TowState.STREAMED:
            return self.towed_depth_target_m
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

    def listening_samples(self, samples=None):
        """Return pre-playback beam audio with operator filtering and gain.

        An explicit receiver block uses the current controls instead of reading
        the latest samples. Always copy; playback must not mutate or consume
        receiver blocks, analysis, or simulation state.

        The playback path applies headphone volume before its smooth limiter;
        keeping floating headroom here lets lower volume reduce compression.
        Instrument analysis continues to use the receiver's ungained samples.
        """
        samples = np.array(self.receiver.samples if samples is None else samples,
                           dtype=np.float32, copy=True)
        if self.listen_filtered:
            frequencies = np.fft.rfftfreq(len(samples), 1.0 / self.receiver.sample_rate)
            spectrum = np.fft.rfft(samples)
            spectrum[(frequencies < self.band_low_hz) | (frequencies > self.band_high_hz)] = 0
            if self.notch_enabled:
                spectrum[abs(frequencies - self._own_line_hz) < 5] *= .15
            samples = np.fft.irfft(spectrum, n=len(samples))
        samples *= 10 ** (self.gain_db / 20)
        return np.nan_to_num(samples, copy=False).astype(np.float32)

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
        """Freeze an instantaneous transmit/scatter measurement until its echo.

        Immediate hear_ping is a simplified intercept warning, not a modeled
        one-way propagation event. Only destruction can cancel a queued return;
        subsequent motion, terrain or array handling cannot change its evidence.
        """
        if mode == "TOWED" and not self.tow_status(frigate.speed)["available"]:
            return
        for target in targets:
            if tgt_gone(target):
                continue
            distance = target.distance_nm(frigate)
            active_range = self._active_range_nm(
                target, world, range_factor, mode)
            if (distance >= active_range
                    and distance > config.SONAR_PING_HEAR_RANGE_NM):
                continue
            source_depth = self.towed_depth_m if mode == "TOWED" else 5.0
            if (hasattr(world, "sonar_path_blocked")
                    and world.sonar_path_blocked(frigate.x, frigate.y, source_depth,
                                                 target.x, target.y,
                                                 getattr(target, "depth", 0.0))):
                continue
            snapshot = (self._measure_ping(frigate, target, t_real, distance, active_range)
                        if distance < active_range else None)
            if distance <= config.SONAR_PING_HEAR_RANGE_NM \
                    and hasattr(target, "hear_ping"):
                target.hear_ping()
            if snapshot is None or len(self._pending_pings) >= self.MAX_PENDING_PINGS:
                continue
            self._pending_pings.append({
                "target": target,
                "frigate": frigate,
                "world": world,
                "sent_at": t_real,
                "ready_at": t_real + world.echo_delay_s(distance),
                "range_factor": range_factor,
                "mode": mode,
                "snapshot": snapshot,
            })

    def passive_range_nm(self, tgt, dist_nm: float, frigate, world,
                          range_factor: float, mode: str) -> float:
        """Effektive passive Reichweite R_eff (SNR-Grundlage)."""
        tow_available = (mode != "TOWED"
                         or self.tow_status(frigate.speed)["available"])
        return self._passive_range_nm(
            tgt, dist_nm, frigate, world, range_factor, mode,
            tgt.bearing_from_frigate(frigate), tow_available)

    def _passive_range_nm(self, tgt, dist_nm: float, frigate, world,
                          range_factor: float, mode: str, true_bearing: float,
                          tow_available: bool) -> float:
        passive_range = frigate.passive_sonar_range_nm(
            tgt.quiet_factor(), world.sea_state)
        thermo = world.thermocline_depth_m(tgt.x, tgt.y)
        sensor_depth = self.towed_depth_m if mode == "TOWED" else 5.0
        same_layer = (sensor_depth < thermo) == (tgt.depth < thermo)
        passive_range *= (config.SONAR_THERMO_PASSIVE_ABOVE if same_layer
                          else config.SONAR_THERMO_PASSIVE_BELOW)
        if mode == "TOWED":
            if not tow_available:
                return 0.0
            full_arr = max(0.5, config.SONAR_ARRAY_TOWED_PASSIVE
                           - config.SONAR_TOWED_SPEED_PENALTY * frigate.speed)
            arr = 1.0 + (full_arr - 1.0) * self.tow_performance
            passive_range *= arr
            # A deep array gains most when it occupies the target's layer.
            if same_layer and self.towed_depth_m >= 30.0:
                passive_range *= 1.0 + (config.SONAR_TOWED_DEEP_BONUS - 1.0) \
                    * self.tow_performance
        own_noise = frigate.noise_level()
        isotropic_penalty = max(0.2, 1.0 - 0.8 * own_noise)
        directional_penalty = 1.0 - 0.8 * own_noise \
            * self._receiver_noise_factor(mode) \
            * directional_gain(true_bearing,
                               self._own_noise_bearing(mode, frigate.course))
        passive_range *= directional_penalty / isotropic_penalty
        passive_range *= range_factor
        for lo, hi in config.CZ_BANDS:
            if lo <= dist_nm <= hi:
                passive_range += config.CZ_BONUS_NM
                break
        return passive_range

    def advance_mechanics(self, dt: float, t: float, frigate) -> None:
        """Advance cooldown, tow handling and queued-echo clocks each sim tick."""
        self.ping_cooldown = max(0.0, self.ping_cooldown - dt)
        self.bt_cooldown = max(0.0, self.bt_cooldown - dt)
        self._update_tow(dt, frigate.speed, frigate.course)
        for contact in self.contacts.values():
            if not self._tow_available():
                contact.array_observations.pop("TOWED", None)
            contact.expire_ping_fix(t)
        if self.tow_state == TowState.STREAMED:
            depth_limit = max(config.SONAR_TOWED_DEPTH_MIN_M,
                              config.SONAR_TOWED_DEPTH_MAX_M
                              - frigate.speed * config.SONAR_TOWED_SPEED_SHALLOW_M_PER_KN)
            self.towed_depth_target_m = min(self.towed_depth_target_m, depth_limit)
            depth_step = config.SONAR_TOWED_DEPTH_RATE_M_S * dt
            self.towed_depth_m += config.clamp(
                self.towed_depth_target_m - self.towed_depth_m, -depth_step, depth_step)
        self._process_pending_pings(t)
        if self._ping_anim_timer > 0:
            self._ping_anim_timer -= dt
            if self._ping_anim_timer <= 0:
                self.ping_active = False

    def update(self, dt: float, t: float, frigate, targets, world,
               range_factor: float = 1.0, mode: str = "BOW",
               buoys=(), focus_tgt=None, own_cavitation: float = 0.0,
               advance_mechanics: bool = True):
        """Passives Hören (dt/t in sim-Sekunden).

        targets: Sub/Animal/Decoy/SurfaceShip/EnemyTorpedo (Duck-Types).
        """
        if advance_mechanics:
            self.advance_mechanics(dt, t, frigate)
        else:
            for contact in self.contacts.values():
                contact.expire_ping_fix(t)

        detected_ids: set = set()
        self._lofar_timer += dt
        sample_due = self._lofar_timer + 1e-9 >= self.receiver.block_s
        sources = []
        self._own_line_hz = 10.0 + 1.9 * frigate.speed
        if mode != self._receiver_mode:
            self._receiver_mode = mode
            self.beam_width_deg = 6.0 if mode == "TOWED" else 12.0
            self.reset_listening_history()
        tow_available = self.tow_status(frigate.speed)["available"]
        array_modes = ("BOW", "TOWED") if tow_available else ("BOW",)
        for tgt in targets:
            if tgt_gone(tgt):
                continue
            dist = tgt.distance_nm(frigate)
            true_bearing = tgt.bearing_from_frigate(frigate)
            observations = {}
            for array_mode in array_modes:
                r_eff = self._passive_range_nm(
                    tgt, dist, frigate, world, range_factor, array_mode,
                    true_bearing, tow_available)
                if dist >= r_eff:
                    continue
                source_depth = self.towed_depth_m if array_mode == "TOWED" else 5.0
                if (hasattr(world, "sonar_path_blocked")
                        and world.sonar_path_blocked(
                             frigate.x, frigate.y, source_depth, tgt.x, tgt.y,
                             getattr(tgt, "depth", 0.0))):
                    continue
                s_db = snr_db(r_eff, dist)
                quality = config.clamp(
                    s_db / config.SONAR_SNR_QUALITY_SPAN_DB, 0.0, 1.0)
                bearing = self._observed_bearing(
                    tgt, true_bearing, frigate, quality, array_mode, t)
                uncertainty = bearing_error_deg(
                    array_mode, frigate.speed, quality) / math.sqrt(3.0)
                observations[array_mode] = dict(
                    bearing=bearing, quality=quality, snr=s_db, last_seen=t,
                    uncertainty_deg=uncertainty)
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
            uncertainty = primary["uncertainty_deg"]
            bow = c.array_observations.get("BOW")
            towed = c.array_observations.get("TOWED")
            if bow is not None and towed is not None:
                delta = abs(config.angle_diff_deg(bow["bearing"], towed["bearing"]))
                c.fusion_delta_deg = delta
                if delta <= config.SONAR_FUSION_CONFIRM_DEG:
                    c.fusion_status = "BESTAETIGT"
                    bow_sigma = bow.get("uncertainty_deg",
                                        config.TMA_DEFAULT_BEARING_SIGMA_DEG)
                    towed_sigma = towed.get("uncertainty_deg",
                                            config.TMA_DEFAULT_BEARING_SIGMA_DEG)
                    bow_weight = 1.0 / bow_sigma ** 2
                    towed_weight = 1.0 / towed_sigma ** 2
                    x = (math.sin(math.radians(bow["bearing"])) * bow_weight
                         + math.sin(math.radians(towed["bearing"])) * towed_weight)
                    y = (math.cos(math.radians(bow["bearing"])) * bow_weight
                         + math.cos(math.radians(towed["bearing"])) * towed_weight)
                    bearing = math.degrees(math.atan2(x, y)) % 360.0
                    quality = min(1.0, max(bow["quality"], towed["quality"]) + .1)
                    uncertainty = math.sqrt(1.0 / (bow_weight + towed_weight))
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
                snr=s_db,
                bearing_uncertainty_deg=uncertainty)
            # W1: Peilungs-Track (TMA-Datenbasis)
            tr = self._tracks.setdefault(tgt.id, BearingTrack())
            tr.add(t, bearing, frigate.x, frigate.y, frigate.course,
                   uncertainty)
            detected_ids.add(tgt.id)
            listen_observation = observations.get(mode)
            if sample_due and listen_observation is not None:
                broadband = getattr(tgt, "broadband", lambda: {})()
                source = {"bearing": listen_observation["bearing"],
                          "level": listen_observation["quality"],
                          "lines": tgt.lofar_lines(t),
                          "seed": getattr(tgt, "sensor_seed", tgt.id)}
                if isinstance(broadband, dict) and broadband.get("level", 0) > 0:
                    source["broadband"] = broadband
                sources.append(source)

        # Bojen messen von ihrer eigenen Position. Erst zwei Peilstrahlen
        # liefern eine an die Fregatte übertragbare Positionslösung.
        active_buoys = [b for b in buoys if getattr(b, "active", False)]
        for tgt in targets if active_buoys else ():
            if tgt_gone(tgt):
                continue
            reports = []
            for b in active_buoys:
                dist = math.hypot(tgt.x - b.x, tgt.y - b.y)
                if dist >= config.BUOY_RANGE_NM:
                    continue
                if (hasattr(world, "sonar_path_blocked")
                        and world.sonar_path_blocked(
                            b.x, b.y, 5.0, tgt.x, tgt.y,
                            getattr(tgt, "depth", 0.0))):
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
            best = None
            for i, first in enumerate(reports):
                for second in reports[i + 1:]:
                    fix = self._bearing_fix(first, second)
                    if fix is None:
                        continue
                    quality = min(first[2], second[2]) * fix[2]
                    if best is None or quality > best[0]:
                        best = (quality, fix)
            if best is None:
                continue
            quality, fix = best
            fx, fy, geometry = fix
            c = self._get_contact(tgt)
            c._fx, c._fy = frigate.x, frigate.y
            if tgt.id not in detected_ids:
                c.confidence = min(1.0, c.confidence
                                   + config.SONAR_CONF_PASSIVE_PER_S * dt)
                c.quality = quality
                c.last_seen = t
            c.update_buoy(fx, fy, quality, t)
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
            report = contact.array_observations.get(mode) if contact is not None else None
            if report is not None and t - report["last_seen"] <= 2.0:
                if contact.target_id != self._listen_target_id:
                    self.reset_listening_history()
                    self._listen_target_id = contact.target_id
                self.listen_bearing = report["bearing"]
            else:
                # Lost tracks hold the last observed direction, not world truth.
                self.focus_locked = False
                self._listen_target_id = None

        while self._lofar_timer + 1e-9 >= self.receiver.block_s:
            self._lofar_timer = max(0.0, self._lofar_timer - self.receiver.block_s)
            self.receiver.update(sources, self.listen_bearing, self.beam_width_deg,
                                  frigate.noise_level() * self._receiver_noise_factor(mode),
                                  world.sea_state, frigate.speed,
                                  own_cavitation=own_cavitation,
                                  own_noise_bearing=self._own_noise_bearing(mode, frigate.course))
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
        if not (0.0 <= along_first <= config.BUOY_RANGE_NM
                and 0.0 <= along_second <= config.BUOY_RANGE_NM):
            return None
        return b1.x + along_first * r[0], b1.y + along_first * r[1], geometry

    def _update_tow(self, dt: float, speed: float, course: float) -> None:
        lag_fraction = config.clamp(dt / (config.SONAR_TOWED_HEADING_LAG_S + dt), 0, 1)
        self.tow_heading_deg = (self.tow_heading_deg
                                + config.angle_diff_deg(course, self.tow_heading_deg)
                                * lag_fraction) % 360.0
        if self.tow_payout > 0 and speed > config.SONAR_TOWED_MAX_SAFE_KN:
            self.tow_state = TowState.FAULT
            self._tow_settle_s = 0.0
            return
        self._tow_handling_ok = self._tow_speed_ok(speed)
        if self.tow_state == TowState.DEPLOYING and self._tow_handling_ok:
            self.tow_payout = min(1.0, self.tow_payout + dt / config.SONAR_TOWED_DEPLOY_S)
            if self.tow_payout >= 1.0:
                self.tow_state = TowState.STREAMED
                self._tow_settle_s = 0.0
        elif self.tow_state == TowState.RETRIEVING and self._tow_handling_ok:
            self.tow_payout = max(0.0, self.tow_payout - dt / config.SONAR_TOWED_RETRIEVE_S)
            if self.tow_payout <= 0.0:
                self.tow_state = TowState.STOWED
        elif self.tow_state == TowState.STREAMED:
            self._tow_settle_s = min(config.SONAR_TOWED_SETTLE_S,
                                     self._tow_settle_s + dt)

    def _own_noise_bearing(self, mode: str, ship_course: float) -> float:
        # HMS sees machinery aft; from the streamed array the ship is forward
        # along the lagging cable axis.
        return self.tow_heading_deg if mode == "TOWED" else (ship_course + 180.0) % 360.0

    def _receiver_noise_factor(self, mode: str) -> float:
        if mode != "TOWED":
            return 1.0
        return 1.0 - (1.0 - config.SONAR_TOWED_SELF_NOISE_FACTOR) * self.tow_performance

    def _update_signature_analysis(self) -> None:
        """Classify measured beam features, never the hidden platform key."""
        self.demon_analysis = self.receiver.demon_analysis
        self.signature_candidates = []
        if self.demon_analysis is None:
            return
        data = self.demon_analysis
        self.signature_candidates = rank_signatures(
            data["blade_rate_hz"], None, data["tonal_hz"], data["cavitation"])

    @staticmethod
    def _active_range_nm(tgt, world, range_factor: float, mode: str) -> float:
        ping_mult = (config.SONAR_ARRAY_TOWED_PING if mode == "TOWED"
                     else config.SONAR_ARRAY_BOW_PING)
        active_range = config.SONAR_ACTIVE_BASE_NM * ping_mult
        if getattr(tgt, "depth", 0.0) >= world.thermocline_depth_m(tgt.x, tgt.y):
            active_range *= config.SONAR_THERMO_ACTIVE_BELOW
        return active_range * (1.0 - 0.03 * world.sea_state) * range_factor

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
                result.append(min(1.0, value * gain * 0.15))
            else:
                result.append(min(1.0, value * gain))
        return result

    def _process_pending_pings(self, t: float) -> None:
        """Deliver frozen evidence at the first tick meeting its deadline.

        Preserve the historical sunk/dead/hit cancellation rule. Target identity
        is internal association only; neither geometry nor propagation is read
        again. Measurement timestamps never become reception timestamps.
        """
        pending = []
        for ping in self._pending_pings:
            target = ping["target"]
            if tgt_gone(target):
                continue
            if t >= ping["ready_at"]:
                contact = self._apply_ping_snapshot(target, ping["snapshot"], ping["mode"])
                self.echo_events.append(dict(self.echo_history[-1]))
                del self.echo_events[:-config.SONAR_ECHO_HISTORY_MAX]
                contact.expire_ping_fix(t)
            else:
                pending.append(ping)
        self._pending_pings = pending

    @staticmethod
    def valid_ping_snapshot(snapshot) -> bool:
        """Strict measurement-only schema shared with transactional save loading."""
        limits = {"t": (0, 1e12), "observer_x": (-1e6, 1e6),
                  "observer_y": (-1e6, 1e6), "bearing": (0, 360),
                  "range_nm": (0, 10000), "depth_m": (0, 10000),
                  "range_sigma_nm": (1e-9, config.SONAR_PING_RANGE_ERROR_NM),
                  "depth_sigma_m": (1e-9, config.SONAR_PING_DEPTH_ERROR_M),
                  "snr_db": (-200, 200)}
        if not isinstance(snapshot, dict) or set(snapshot) != set(limits):
            return False
        try:
            return snapshot["bearing"] < 360 and all(
                isinstance(snapshot[key], (int, float))
                and not isinstance(snapshot[key], bool)
                and math.isfinite(snapshot[key]) and low <= snapshot[key] <= high
                for key, (low, high) in limits.items())
        except (TypeError, OverflowError):
            return False

    @staticmethod
    def _measure_ping(frigate, target, t: float, distance: float, active_range: float):
        """Deterministic noisy snapshot; no shared RNG or contact allocation."""
        signal = snr_db(active_range, distance)
        error_scale = 1.0 / max(1.0, 1.0 + signal / 8.0)
        seed = getattr(target, "sensor_seed", target.id)
        snapshot = dict(
            t=t, observer_x=frigate.x, observer_y=frigate.y,
            bearing=(target.bearing_from_frigate(frigate) + 1.5 * error_scale
                     * _correlated_uniform(seed, t, 1.0, 101)) % 360.0,
            range_nm=max(0.0, distance + config.SONAR_PING_RANGE_ERROR_NM
                         * error_scale * _correlated_uniform(seed, t, 1.0, 211)),
            depth_m=max(0.0, target.depth + config.SONAR_PING_DEPTH_ERROR_M
                        * error_scale * _correlated_uniform(seed, t, 1.0, 307)),
            range_sigma_nm=config.SONAR_PING_RANGE_ERROR_NM * error_scale / math.sqrt(3),
            depth_sigma_m=config.SONAR_PING_DEPTH_ERROR_M * error_scale / math.sqrt(3),
            snr_db=signal)
        if not SonarSystem.valid_ping_snapshot(snapshot):
            raise ValueError("invalid active sonar measurement")
        return snapshot

    def _apply_ping_snapshot(self, target, snapshot, mode):
        c = self._get_contact(target)
        # A late return must not replace an already newer active measurement.
        if c.range_source != "ping" or c.range_seen is None or snapshot["t"] >= c.range_seen:
            last_seen = c.last_seen
            c._fx, c._fy = snapshot["observer_x"], snapshot["observer_y"]
            c.update_ping(
                bearing=snapshot["bearing"], range_est=snapshot["range_nm"],
                depth_est=snapshot["depth_m"],
                confidence=c.confidence + config.SONAR_CONF_PING_BONUS,
                t=snapshot["t"], snr=snapshot["snr_db"],
                range_sigma_nm=snapshot["range_sigma_nm"],
                depth_sigma_m=snapshot["depth_sigma_m"])
            c.last_seen = max(last_seen, c.last_seen)
        self.echo_history.append({
            key: value for key, value in dict(snapshot, contact_id=c.id, mode=mode).items()
            if key not in ("observer_x", "observer_y")})
        del self.echo_history[:-config.SONAR_ECHO_HISTORY_MAX]
        return c

    def _observed_bearing(self, tgt, true_bearing: float, frigate,
                          quality: float, mode: str, t: float) -> float:
        """Peilung mit deterministisch korreliertem, glatt interpoliertem Fehler."""
        err = bearing_error_deg(mode, frigate.speed, quality)
        seed = getattr(tgt, "sensor_seed", tgt.id)
        salt = 17 if mode == "TOWED" else 0
        return (true_bearing + err * _correlated_uniform(
            seed, t, config.SONAR_BEARING_NOISE_EPOCH_S, salt)) % 360.0

    def _update_tma(self, tgt, t: float) -> None:
        """TMA nur neu lösen, wenn der Peilungs-Track neue Punkte hat
        (version-Gate) – sonst läuft die Gittersuche jeden Substep und
        verzögert das ganze Spiel (LOFAR 'hängt')."""
        tr = self._tracks.get(tgt.id)
        if tr is None:
            return
        if not tr.pts or t - tr.pts[-1].t > config.SONAR_CONTACT_LOST_S:
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
            c.update_tma(sol, tr.pts[-1].t)
        self._tma_versions[tgt.id] = tr.version
        self._tma_next[tgt.id] = t + config.TMA_RESOLVE_EVERY_S

    def apply_ping(self, frigate, targets, world, t_real: float,
                   range_factor: float = 1.0, mode: str = "BOW",
                   notify_ping: bool = True):
        """Ping-Echo berechnen (wird nach fire_ping aufgerufen)."""
        if mode == "TOWED" and not self.tow_status(frigate.speed)["available"]:
            return []
        contacts = []
        for tgt in targets:
            if tgt_gone(tgt):
                continue
            dist = tgt.distance_nm(frigate)
            active_range = self._active_range_nm(tgt, world, range_factor, mode)
            can_hear = (notify_ping and dist <= config.SONAR_PING_HEAR_RANGE_NM
                        and hasattr(tgt, "hear_ping"))
            if dist >= active_range and not can_hear:
                continue
            source_depth = self.towed_depth_m if mode == "TOWED" else 5.0
            if (hasattr(world, "sonar_path_blocked")
                    and world.sonar_path_blocked(frigate.x, frigate.y, source_depth,
                                                 tgt.x, tgt.y,
                                                 getattr(tgt, "depth", 0.0))):
                continue

            # Hört das U-Boot den Ping?
            if can_hear:
                tgt.hear_ping()

            # Echo erhalten?
            if dist < active_range:
                snapshot = self._measure_ping(frigate, tgt, t_real, dist, active_range)
                contacts.append(self._apply_ping_snapshot(tgt, snapshot, mode))
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
