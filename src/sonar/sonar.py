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
from src.sonar import equation, propagation
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


_HULL_LENGTH_FALLBACK_M = (("torpedo_class", 6.0), ("atype", 15.0),
                           ("kind", 3.0), ("stype", 70.0))


def hull_length_m(tgt) -> float:
    """Catalogued hull length of an echo target (bounded fallbacks)."""
    catalog = getattr(tgt, "runtime_catalog", None)
    key = getattr(getattr(tgt, "stype", None), "key", None) or getattr(
        tgt, "signature_key", None)
    if catalog is not None and key is not None:
        systems = catalog.profile_systems.get(key)
        reference = (catalog.references.get(systems.reference_key)
                     if systems is not None and systems.reference_key else None)
        if reference is not None and reference.length_m:
            return float(reference.length_m)
    if hasattr(tgt, "length_m"):
        return float(tgt.length_m)
    if hasattr(tgt, "signature_key"):
        return 120.0
    for attribute, length in _HULL_LENGTH_FALLBACK_M:
        if hasattr(tgt, attribute):
            return length
    return equation.REFERENCE_TARGET_LENGTH_M


class _WreckEcho:
    """Stationary echo source for a charted wreck (hard, flat-lying hull)."""

    speed = 0.0
    extra_ts_db = 3.0

    def __init__(self, index: int, hazard, seed: int):
        from src.core import detrand

        self.id = 0
        self.x, self.y = hazard.x_nm, hazard.y_nm
        self.depth = hazard.top_depth_m + 6.0
        self.length_m = hazard.length_m
        self.course = detrand.uniform(0.0, 360.0, seed, "wreck-heading", index)
        self.sensor_seed = int(detrand.bits(seed, "wreck-echo", index) & 0x7FFFFFFF)

    def bearing_from_frigate(self, frigate) -> float:
        return math.degrees(math.atan2(self.x - frigate.x,
                                       -(self.y - frigate.y))) % 360.0


def _lambert_mu_db(world, x_nm: float, y_nm: float) -> float:
    from src.world.ocean import SEDIMENTS

    seabed = getattr(world, "seabed_at", None)
    if seabed is None:
        return SEDIMENTS["sand"][3]
    return SEDIMENTS[seabed(x_nm, y_nm)][3]


SOUND_SPEED_KN = config.SOUND_SPEED_M_S * 3600.0 / 1852.0
DOPPLER_SIGMA_HZ = 0.02
DOPPLER_MIN_QUALITY = 0.3


def source_level_factor(tgt) -> float:
    """Amplitude factor of a target's speed/cavitation/transient source level."""
    offset = getattr(tgt, "source_level_offset_db", None)
    return 10.0 ** (offset() / 20.0) if offset is not None else 1.0


def doppler_factor(tgt, observer) -> float:
    """Received/emitted frequency ratio from the closing speed (knots)."""
    dx, dy = observer.x - tgt.x, observer.y - tgt.y
    distance = math.hypot(dx, dy)
    if distance < 1e-6:
        return 1.0
    ux, uy = dx / distance, dy / distance
    speed_t = getattr(tgt, "speed", None)
    if speed_t is None:
        speed_t = getattr(tgt, "speed_kn", 0.0)
    course_t = math.radians(getattr(tgt, "course", 0.0))
    course_o = math.radians(getattr(observer, "course", 0.0))
    speed_o = getattr(observer, "speed", 0.0) or 0.0
    vx = speed_t * math.sin(course_t) - speed_o * math.sin(course_o)
    vy = -speed_t * math.cos(course_t) + speed_o * math.cos(course_o)
    closing = vx * ux + vy * uy
    return 1.0 + closing / SOUND_SPEED_KN


def _surface_temperature(world) -> float:
    ocean = getattr(world, "ocean", None)
    if ocean is None:
        return 10.0
    return ocean.sea_surface_temperature_c(getattr(world, "hour", 12.0))


def _echo_delay(world, distance_nm: float, frigate, target) -> float:
    """Two-way echo latency with the modelled sound speed on the path."""
    if hasattr(world, "mean_sound_speed_m_s"):
        return world.echo_delay_s(distance_nm, (frigate.x + target.x) * .5,
                                  (frigate.y + target.y) * .5)
    return world.echo_delay_s(distance_nm)


def _target_acoustic_signature(tgt):
    """Best-effort TargetSignature lookup across the different contact types."""
    for attr in ("acoustic", "stype", "profile"):
        candidate = getattr(tgt, attr, None)
        if candidate is None:
            continue
        if hasattr(candidate, "tonal_band_hz"):
            return candidate
        nested = getattr(candidate, "acoustic", None)
        if nested is not None and hasattr(nested, "tonal_band_hz"):
            return nested
    return None


def representative_frequency_hz(tgt) -> float:
    """Propagation band closest to the target's own dominant tonal frequency.

    Different platforms radiate at different frequencies (a slow diesel
    tanker's blade-rate tonal vs. a fast cavitating warship's broadband), and
    higher frequencies attenuate faster underwater.
    """
    return propagation.representative_frequency_hz(_target_acoustic_signature(tgt))


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
        self.player_class = None  # None|U_BOOT|KAMPFSCHIFF|BIOLOGISCH|FAHRZEUG|FLUGZEUG
        self.released_to_opz = False
        self.passive_source = "SONAR-BRG"
        self.observer_x = 0.0
        self.observer_y = 0.0
        self.signature = ""       # zuletzt gehörte Geräusch-Signatur
        # W1: SNR + TMA
        self.snr = -99.0          # dB, -99 = gerade nicht detektiert
        self.tma_pos = None       # (x, y) NM
        self.tma_course = None
        self.tma_speed = None
        self.tma_quality = 0.0
        self.tma_ellipse = None   # (major NM, minor NM, orientation deg)
        # Towed-array left/right ambiguity: the line array cannot tell a
        # bearing from its mirror about the array axis until resolved.
        self.towed_ambiguous = False
        self.ambiguity_axis = None     # tow heading when the ambiguity began
        self.mirror_bearing = None
        self.tonal_hz = None           # measured (Doppler-shifted) tonal
        self.towed_resolved = False
        self.tma_seen = None
        self.buoy_fixes = []  # raw (t, x, y, quality), not ownship passive bearings
        self.buoy_reports = {}  # buoy sequence -> detached measured report
        self.helo_qualified = False
        self.buoy_released_to_opz = False
        self.fixes = {}
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
        # W2: independent helicopter dip-passive bearing track. Kept fully
        # separate from the ship's own passive_bearing/_fx/_fy/observer_x/y -
        # they are measured from different platforms and must never corrupt
        # each other's filter state (the reported bug: the frigate's own
        # bearing was being overwritten every tick the helo was also dipping).
        self.dip_bearing = None
        self.dip_bearing_uncertainty_deg = None
        self.dip_last_seen = None
        self.dip_observer_x = None
        self.dip_observer_y = None
        self.dip_released_to_opz = False
        self.ship_observer_x = None
        self.ship_observer_y = None

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

    def update_dip_passive(self, bearing: float, t: float, observer_x: float,
                           observer_y: float,
                           bearing_uncertainty_deg: float) -> None:
        """W2: the helicopter's own dipping-sonar bearing track.

        A lighter smoothing filter than update_passive() - dips are
        occasional, hover-based fixes, not a continuous towed/bow array -
        but it is fully independent state so it never overwrites the ship's
        own passive_bearing/observer position."""
        raw = bearing % 360.0
        if self.dip_bearing is None or self.dip_last_seen is None:
            self.dip_bearing = raw
        else:
            dt = max(0.0, t - self.dip_last_seen)
            alpha = 1.0 - math.exp(-dt / config.SONAR_BEARING_DISPLAY_TAU_S)
            self.dip_bearing = (self.dip_bearing + alpha * config.angle_diff_deg(
                raw, self.dip_bearing)) % 360.0
        self.dip_bearing_uncertainty_deg = max(0.05, bearing_uncertainty_deg)
        self.dip_observer_x, self.dip_observer_y = observer_x, observer_y
        self.dip_last_seen = t

    def _publish_fix(self, source: str, measured_at: float, fixed_at: float,
                     x: float, y: float, uncertainty_nm: float,
                     quality: float, depth_m=None, depth_uncertainty_m=None):
        """Retain one detached, measurement-dated fix per independent source."""
        self.fixes[source] = dict(
            source=source, measured_at=float(measured_at), fixed_at=float(fixed_at),
            x=float(x), y=float(y), uncertainty_nm=float(uncertainty_nm),
            depth_m=None if depth_m is None else float(depth_m),
            depth_uncertainty_m=(None if depth_uncertainty_m is None
                                 else float(depth_uncertainty_m)),
            quality=float(config.clamp(quality, 0.0, 1.0)))

    def active_fixes(self, now: float) -> tuple:
        """Return stable detached fix copies whose measurements remain current."""
        result = []
        for source in ("PING", "DIPPING", "TMA", "SONOBUOY"):
            fix = self.fixes.get(source)
            lifetime = (config.SONAR_PING_FIX_MAX_AGE_S
                        if source in ("PING", "DIPPING")
                        else config.SONAR_CONTACT_LOST_S)
            if (fix is not None and 0.0 <= now - fix["measured_at"] <= lifetime):
                result.append(dict(fix))
        return tuple(result)

    def update_ping(self, bearing: float, range_est: float, depth_est: float,
                     confidence: float, t: float, snr: float = 0.0,
                     range_sigma_nm: float = None, depth_sigma_m: float = None,
                     fixed_at: float = None, fix_source: str = "PING"):
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
        self._publish_fix(
            fix_source, t, t if fixed_at is None else fixed_at, *self.ping_pos,
            self.range_sigma_nm, self.quality, self.depth_est, self.depth_sigma_m)

    def expire_ping_fix(self, t: float) -> None:
        """Expire evidence even without detections (name retained for callers).

        TMA/buoy positions and TMA motion are usable for at most
        SONAR_CONTACT_LOST_S since their measurement, not last passive hearing.
        The uncertainty fields for these estimates are heuristic, not covariance.
        """
        for source in tuple(self.fixes):
            lifetime = (config.SONAR_PING_FIX_MAX_AGE_S
                        if source in ("PING", "DIPPING")
                        else config.SONAR_CONTACT_LOST_S)
            measured_at = self.fixes[source].get("measured_at")
            if measured_at is None or t - measured_at > lifetime:
                del self.fixes[source]
        tma_seen = self.tma_seen
        if tma_seen is None and self.range_source == "tma":
            tma_seen = self.range_seen  # pre-evidence saves
        if (self.tma_pos is not None or self.tma_course is not None
                or self.tma_speed is not None) and (tma_seen is None or
                t - tma_seen > config.SONAR_CONTACT_LOST_S):
            self.tma_pos = self.tma_course = self.tma_speed = None
            self.tma_ellipse = None
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
            self.fusion_status = ("TAS L/R?" if self.towed_ambiguous
                                  and set(self.array_observations) == {"TOWED"}
                                  else "NUR " + next(iter(self.array_observations))
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
        buoy_uncertainty = max(.5, (1.0 - quality) * 8.0)
        self._publish_fix("SONOBUOY", t, t, x, y, buoy_uncertainty, quality)
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
        self.range_sigma_nm = buoy_uncertainty
        self.bearing_uncertainty_deg = None
        self.depth_est = self.depth_sigma_m = None
        self.range_source = "buoy"
        self.range_seen = t
        self.origin = "bojenkreuzpeilung"

    def tma_range_sigma_nm(self, quality: float) -> float:
        """1-sigma position uncertainty: the covariance semi-major axis, never
        more optimistic than the observability-based quality heuristic (the
        linearized covariance is overconfident in poor geometry)."""
        heuristic = max(0.1, (1.0 - quality) * 12.0)
        if self.tma_ellipse is not None:
            return config.clamp(max(self.tma_ellipse[0], heuristic), 0.1, 12.0)
        return heuristic

    def update_tma(self, sol, t: float, fixed_at: float = None):
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
        self.tma_ellipse = (tuple(float(v) for v in sol.ellipse)
                            if getattr(sol, "ellipse", None) is not None else None)
        sigma = self.tma_range_sigma_nm(sol.quality)
        if sol.quality >= config.TMA_RANGE_MIN_QUALITY:
            self._publish_fix("TMA", t, t if fixed_at is None else fixed_at,
                              self.tma_pos[0], self.tma_pos[1], sigma,
                              self.tma_quality)
        if self.range_source not in ("ping", "buoy") and \
                sol.quality >= config.TMA_RANGE_MIN_QUALITY:
            self.observed_x, self.observed_y = self.tma_pos
            self.bearing = math.degrees(math.atan2(
                self.observed_x - self._fx, -(self.observed_y - self._fy))) % 360.0
            self.range_est = math.hypot(self.observed_x - self._fx,
                                        self.observed_y - self._fy)
            self.range_sigma_nm = sigma
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
    MAX_PENDING_CLUTTER = 8
    CLUTTER_SEARCH_NM = 30.0
    MAX_PENDING_PINGS = 10000
    STOWED = TowState.STOWED
    DEPLOYING = TowState.DEPLOYING
    STREAMED = TowState.STREAMED
    RETRIEVING = TowState.RETRIEVING
    FAULT = TowState.FAULT

    def __init__(self, seed: int = 42, acoustic_profiles=None):
        self.rng = random.Random(seed + 1000)
        self.acoustic_profiles = acoustic_profiles
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
        self.demon_history = []
        self.demon_times = []
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
        self.audition_mode = "BROADBAND"
        self._audition_states = {}
        self._audition_previous_controls = None
        self._audition_ola_state = None
        self._audition_cache_key = None
        self._audition_ola_out = None
        self._audition_previous_source = None
        self.receiver = AcousticReceiver(seed)
        self.broadband_history = []
        self.history_times = []
        self.broadband_long_history = []
        self.broadband_long_times = []
        self._broadband_long_accumulator = []
        self.lofar_times = []
        self.lofar_bearings = []
        self.peak_spectrum = []
        self._listen_target_id = None
        self._receiver_mode = "BOW"
        self._own_line_hz = 10.0
        self.towed_depth_m = config.SONAR_TOWED_DEPTH_M
        self.towed_depth_target_m = config.SONAR_TOWED_DEPTH_M
        # Distant-shipping noise input (civilian contacts nearby, set by the
        # game each tick) and the selected active pulse.
        self.shipping_contacts = equation.REFERENCE_SHIPPING_CONTACTS
        self.ping_pulse = equation.DEFAULT_PULSE
        self.last_passive_terms = None
        # Frozen false echoes from charted wrecks awaiting their return time.
        self._pending_clutter: list[dict] = []
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
        max_depth = min(water_depth, config.SONAR_BT_MAX_DEPTH_M)
        depths = np.linspace(0.0, max_depth, 21)
        speeds = []
        true_speed = getattr(world, "sound_speed_m_s", None)
        for depth in depths:
            # The probe measures the real modelled temperature profile
            # (Mackenzie sound speed) with a small sensor noise.
            speed = (true_speed(float(depth), frigate.x, frigate.y)
                     if true_speed is not None else
                     propagation.synthetic_sound_speed_m_s(depth, measured_thermo))
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
        self.demon_history.clear()
        self.demon_times.clear()
        self.signature_candidates = []
        self.reset_audition_audio()

    def reset_audition_audio(self) -> None:
        """Discard transient operator-filter and retry state."""
        self._audition_states = {}
        self._audition_previous_controls = None
        self._audition_ola_state = None
        self._audition_cache_key = None
        self._audition_ola_out = None
        self._audition_previous_source = None

    @property
    def listen_filtered(self) -> bool:
        """Compatibility view for callers predating the explicit audition modes."""
        return self.audition_mode == "FILTERED"

    @listen_filtered.setter
    def listen_filtered(self, value: bool) -> None:
        self.audition_mode = "FILTERED" if value else "BROADBAND"

    def set_audition_mode(self, mode: str) -> bool:
        if mode not in ("BROADBAND", "FILTERED", "HETERODYNE"):
            return False
        self.audition_mode = mode
        return True

    def _audition_process(self, samples, controls):
        mode, low_hz, high_hz, notch, own_line_hz, gain_db = controls
        out = np.array(samples, copy=True)
        if mode != "BROADBAND":
            n = out.size
            frequencies = np.fft.rfftfreq(n, 1.0 / self.receiver.sample_rate)
            mask = ((frequencies >= low_hz) & (frequencies <= high_hz)).astype(float)
            if notch:
                mask[abs(frequencies - own_line_hz) < 5] *= .15
            if n >= 2 and n % 2 == 0:
                half = n // 2
                previous, overlap = self._audition_states.get(
                    controls, (np.zeros(half), np.zeros(half)))
                window = .5 * (1.0 - np.cos(2.0 * np.pi * np.arange(n) / n))
                output = []
                for current in (out[:half], out[half:]):
                    filtered = np.fft.irfft(
                        np.fft.rfft(window * np.concatenate((previous, current)))
                        * mask, n=n)
                    output.append(overlap + filtered[:half])
                    previous, overlap = current.copy(), filtered[half:]
                out = np.concatenate(output)
                self._audition_states[controls] = (previous, overlap)
                self._audition_ola_state = self._audition_states[controls]
            else:
                out = np.fft.irfft(np.fft.rfft(out) * mask, n=n)
                self._audition_ola_state = None
            if mode == "HETERODYNE":
                # Translate the selected low-frequency beam band around 700 Hz.
                phase = np.arange(out.size) * (2.0 * np.pi * 700.0
                                                / self.receiver.sample_rate)
                out = 2.0 * out * np.cos(phase)
        return out * (10 ** (gain_db / 20))

    def listening_samples(self, samples=None, block_id=None):
        """Return pre-playback beam audio with operator filtering and gain.

        An explicit receiver block uses the current controls instead of reading
        the latest samples. Always copy; playback must not mutate or consume
        receiver blocks, analysis, or simulation state.

        The playback path applies headphone volume before its smooth limiter;
        keeping floating headroom here lets lower volume reduce compression.
        Instrument analysis continues to use the receiver's ungained samples.

        Band filtering uses a periodic-Hann 50% overlap-add stream. The result
        lags by half a block, avoiding independent FFT-block edges. ``block_id``
        makes processing idempotent when playback backpressure retries a block.
        """
        source = self.receiver.samples if samples is None else samples
        if (not isinstance(source, np.ndarray) or source.ndim != 1
                or source.size != self.receiver.samples.size
                or not np.all(np.isfinite(source))):
            raise ValueError("audition requires one complete mixed receiver block")
        controls = (self.audition_mode, self.band_low_hz, self.band_high_hz,
                     self.notch_enabled, self._own_line_hz, self.gain_db)
        # A rejected playback block must retry byte-for-byte even if ship speed
        # changes the own-line notch before the next frame. New controls take
        # effect on the next receiver sequence.
        cache_key = (("sequence", block_id) if block_id is not None
                     else (("object", id(source)), controls))
        if cache_key == self._audition_cache_key:
            return self._audition_ola_out.copy()
        samples = np.array(source, dtype=np.float32, copy=True)
        previous_controls = self._audition_previous_controls
        if (controls[0] != "BROADBAND" and controls not in self._audition_states
                and self._audition_previous_source is not None):
            # Prime a changed Hann OLA path from the preceding complete beam.
            self._audition_process(self._audition_previous_source, controls)
        out = self._audition_process(samples, controls)
        if previous_controls is not None and previous_controls != controls:
            old = self._audition_process(samples, previous_controls)
            edge = min(samples.size, max(2, round(.02 * self.receiver.sample_rate)))
            blend = np.linspace(0.0, 1.0, edge)
            out[:edge] = old[:edge] * (1.0 - blend) + out[:edge] * blend
        self._audition_states = ({controls: self._audition_states[controls]}
                                 if controls in self._audition_states else {})
        self._audition_ola_state = self._audition_states.get(controls)
        self._audition_previous_controls = controls
        self._audition_previous_source = samples.copy()
        result = np.nan_to_num(out, copy=False).astype(np.float32)
        self._audition_cache_key = cache_key
        self._audition_ola_out = result.copy()
        return result

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
                target, world, range_factor, mode, frigate)
            if (distance >= active_range
                    and distance > config.SONAR_PING_HEAR_RANGE_NM):
                continue
            source_depth = (self.towed_depth_m if mode == "TOWED" else
                            getattr(frigate, "dip_depth_m", 5.0)
                            if mode == "DIPPING" else 5.0)
            if (hasattr(world, "sonar_path_blocked")
                    and world.sonar_path_blocked(frigate.x, frigate.y, source_depth,
                                                 target.x, target.y,
                                                 getattr(target, "depth", 0.0))):
                continue
            snapshot = (self._measure_ping(
                frigate, target, t_real, distance,
                self.active_terms(target, frigate, world, range_factor,
                                  mode).signal_excess_db, self.ping_pulse)
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
                "ready_at": t_real + _echo_delay(world, distance,
                                                 frigate, target),
                "range_factor": range_factor,
                "mode": mode,
                "snapshot": snapshot,
            })
        self._queue_clutter(frigate, world, t_real, range_factor, mode)

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
                           tow_available: bool,
                           apply_propagation: bool = True,
                           spectral_out: list | None = None) -> float:
        """Equivalent detection range from the passive sonar equation.

        Returns ``R`` with ``snr_db(R, d) == SE`` so existing consumers keep
        their range-based interface; SE itself is SL - TL - NL + DI - DT per
        ``src/sonar/equation.py``.
        """
        terms = self.passive_terms(tgt, dist_nm, frigate, world, range_factor,
                                   mode, true_bearing, tow_available,
                                   apply_propagation, spectral_out)
        if terms is None:
            return 0.0
        self.last_passive_terms = terms
        return equation.equivalent_range_nm(dist_nm, terms.signal_excess_db)

    def passive_terms(self, tgt, dist_nm: float, frigate, world,
                      range_factor: float, mode: str, true_bearing: float,
                      tow_available: bool, apply_propagation: bool = True,
                      spectral_out: list | None = None):
        # Own-ship self noise: the calibrated own-noise/cavitation penalty
        # (target bonus 1, reference sea state) becomes a self-noise level.
        own_factor = frigate.passive_sonar_range_nm(
            1.0, int(equation.REFERENCE_SEA_STATE)) / config.SONAR_PASSIVE_BASE_NM
        target_bonus = (1.0 + 0.8 * (1.0 - tgt.quiet_factor())) * source_level_factor(tgt)
        thermo = world.thermocline_depth_m(tgt.x, tgt.y)
        sensor_depth = self.towed_depth_m if mode == "TOWED" else 5.0
        same_layer = (sensor_depth < thermo) == (tgt.depth < thermo)
        array_factor = 1.0
        if mode == "TOWED":
            if not tow_available:
                return None
            full_arr = max(0.5, config.SONAR_ARRAY_TOWED_PASSIVE
                           - config.SONAR_TOWED_SPEED_PENALTY * frigate.speed)
            array_factor = 1.0 + (full_arr - 1.0) * self.tow_performance
            # A deep array gains most when it occupies the target's layer.
            if same_layer and self.towed_depth_m >= 30.0:
                array_factor *= 1.0 + (config.SONAR_TOWED_DEEP_BONUS - 1.0) \
                    * self.tow_performance
        own_noise = frigate.noise_level()
        isotropic_penalty = max(0.2, 1.0 - 0.8 * own_noise)
        directional_penalty = 1.0 - 0.8 * own_noise \
            * self._receiver_noise_factor(mode) \
            * directional_gain(true_bearing,
                               self._own_noise_bearing(mode, frigate.course))
        own_factor *= directional_penalty / isotropic_penalty
        # The own wake astern adds bubble noise to the hull array.
        wake = getattr(frigate, "wake_strength_at", None)
        if mode == "BOW" and wake is not None and frigate.speed > 0.0:
            astern = (frigate.course + 180.0) % 360.0
            if abs(config.angle_diff_deg(true_bearing, astern)) < 30.0:
                own_factor *= 1.0 - 0.3 * wake(
                    frigate.x - 0.2 * math.sin(math.radians(frigate.course)),
                    frigate.y + 0.2 * math.cos(math.radians(frigate.course)))
        array_factor *= range_factor
        frequency = representative_frequency_hz(tgt)
        excess = legacy_absorption = 0.0
        absorption = 0.0
        sea_state = float(getattr(world, "effective_sea_state", world.sea_state))
        if apply_propagation:
            midpoint_x = (frigate.x + tgt.x) * .5
            midpoint_y = (frigate.y + tgt.y) * .5
            midpoint_thermo = world.thermocline_depth_m(midpoint_x, midpoint_y)
            depth_query = getattr(world, "depth_m", None)
            water_depth = (depth_query(midpoint_x, midpoint_y)
                           if depth_query is not None else 1000.0)
            water_depth = max(float(water_depth), sensor_depth,
                              float(getattr(tgt, "depth", 0.0)), midpoint_thermo)
            result = propagation.propagate(
                frigate.x, frigate.y, sensor_depth, tgt.x, tgt.y,
                getattr(tgt, "depth", 0.0), frequency,
                midpoint_thermo, water_depth, sea_state=sea_state,
                terrain_blocked=getattr(world, "sonar_path_blocked", None))
            if result.best_path is None:
                return None
            excess = result.best_path.loss_db - 20.0 * math.log10(1.0 + dist_nm)
            legacy_absorption = result.best_path.distance_nm \
                * propagation.ABSORPTION_DB_PER_NM[frequency]
            ray = propagation.ray_excess_db(
                world, frigate.x, frigate.y, sensor_depth, tgt.x, tgt.y,
                float(getattr(tgt, "depth", 0.0)), frequency)
            if ray is not None:
                excess, legacy_absorption = ray, 0.0
            absorption = equation.francois_garrison_db_per_km(
                frequency, _surface_temperature(world),
                min(water_depth, 200.0))
            if spectral_out is not None:
                spectral_out.append(result.spectral_gains)
        return equation.passive_terms(
            frequency_hz=frequency, distance_nm=dist_nm,
            target_bonus=target_bonus, excess_path_loss_db=excess,
            absorption_db_per_km=absorption,
            legacy_absorption_db=legacy_absorption,
            own_range_factor=own_factor, array_range_factor=array_factor,
            sea_state=sea_state,
            rain=float(getattr(world, "rain_intensity", 0.0)),
            shipping_contacts=self.shipping_contacts)

    def update_dipping_passive(self, dt: float, t: float, helicopter,
                               targets, world, range_factor: float = 1.0) -> None:
        """Publish deterministic bearing-only measurements from a dipped sensor."""
        if not getattr(helicopter, "dip_available", False):
            return
        sensor_depth = helicopter.dip_depth_m
        for tgt in targets:
            if tgt_gone(tgt):
                continue
            dx, dy = tgt.x - helicopter.x, tgt.y - helicopter.y
            distance = math.hypot(dx, dy)
            target_bonus = ((1.0 + 0.8 * (1.0 - tgt.quiet_factor()))
                            * source_level_factor(tgt))
            sea_state = float(getattr(world, "effective_sea_state", world.sea_state))
            midpoint_x = (helicopter.x + tgt.x) * .5
            midpoint_y = (helicopter.y + tgt.y) * .5
            thermocline = world.thermocline_depth_m(midpoint_x, midpoint_y)
            water_depth = max(float(world.depth_m(midpoint_x, midpoint_y)),
                              sensor_depth, float(getattr(tgt, "depth", 0.0)),
                              thermocline)
            frequency = representative_frequency_hz(tgt)
            result = propagation.propagate(
                helicopter.x, helicopter.y, sensor_depth, tgt.x, tgt.y,
                getattr(tgt, "depth", 0.0), frequency,
                thermocline, water_depth, sea_state=sea_state,
                terrain_blocked=getattr(world, "sonar_path_blocked", None))
            if result.best_path is None:
                continue
            ray = propagation.ray_excess_db(
                world, helicopter.x, helicopter.y, sensor_depth, tgt.x, tgt.y,
                float(getattr(tgt, "depth", 0.0)), frequency)
            terms = equation.passive_terms(
                frequency_hz=frequency, distance_nm=distance,
                target_bonus=target_bonus,
                excess_path_loss_db=(ray if ray is not None else
                                     result.best_path.loss_db
                                     - 20.0 * math.log10(1.0 + distance)),
                absorption_db_per_km=equation.francois_garrison_db_per_km(
                    frequency, _surface_temperature(world),
                    min(water_depth, 200.0)),
                legacy_absorption_db=(0.0 if ray is not None else
                                      result.best_path.distance_nm
                                      * propagation.ABSORPTION_DB_PER_NM[frequency]),
                own_range_factor=1.0,
                array_range_factor=(config.HELO_DIP_PASSIVE_RANGE_NM
                                    / config.SONAR_PASSIVE_BASE_NM) * range_factor,
                sea_state=sea_state,
                rain=float(getattr(world, "rain_intensity", 0.0)),
                shipping_contacts=self.shipping_contacts,
                hull_self_noise=False)
            effective_range = equation.equivalent_range_nm(
                distance, terms.signal_excess_db)
            if distance >= effective_range:
                continue
            signal = snr_db(effective_range, distance)
            quality = config.clamp(
                signal / config.SONAR_SNR_QUALITY_SPAN_DB, 0.0, 1.0)
            true_bearing = math.degrees(math.atan2(dx, -dy)) % 360.0
            seed = getattr(tgt, "sensor_seed", tgt.id)
            error = config.HELO_DIP_BEARING_ERR_DEG * (1.4 - .8 * quality)
            bearing = (true_bearing + error * _correlated_uniform(
                seed, t, config.SONAR_BEARING_NOISE_EPOCH_S, 43)) % 360.0
            uncertainty = error / math.sqrt(3.0)
            contact = self._get_contact(tgt)
            contact.origin = "dipping-passiv"
            # W2: contact-level fields (confidence/quality/last_seen/signature)
            # are shared across sensors by design - the *bearing* and the
            # observer position are not, so they go through the helicopter's
            # own independent track instead of contact.update_passive().
            contact.confidence = min(
                1.0, contact.confidence + config.SONAR_CONF_PASSIVE_PER_S * dt)
            signature = (tgt.acoustic_signature()
                         if contact.confidence >= config.CONTACT_SIG_CONF else "")
            contact.quality = min(1.0, quality)
            contact.last_seen = max(contact.last_seen, t)
            contact.snr = signal
            if signature:
                contact.signature = signature
            contact.update_dip_passive(
                bearing, t, helicopter.x, helicopter.y, uncertainty)
            contact.expire_ping_fix(t)
            track = self._tracks.setdefault(tgt.id, BearingTrack())
            track.add(t, bearing, helicopter.x, helicopter.y,
                      helicopter.course, uncertainty)

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
            self._ping_anim_timer = max(0.0, self._ping_anim_timer - dt)
            if self._ping_anim_timer == 0:
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
            spectral_by_mode = {}
            for array_mode in array_modes:
                preliminary_range = self._passive_range_nm(
                    tgt, dist, frigate, world, range_factor, array_mode,
                    true_bearing, tow_available, apply_propagation=False)
                if dist >= preliminary_range:
                    continue
                spectral = []
                r_eff = self._passive_range_nm(
                    tgt, dist, frigate, world, range_factor, array_mode,
                    true_bearing, tow_available, spectral_out=spectral)
                if dist >= r_eff:
                    continue
                s_db = snr_db(r_eff, dist)
                quality = config.clamp(
                    s_db / config.SONAR_SNR_QUALITY_SPAN_DB, 0.0, 1.0)
                bearing = self._observed_bearing(
                    tgt, true_bearing, frigate, quality, array_mode, t)
                uncertainty = bearing_error_deg(
                    array_mode, frigate.speed, quality) / math.sqrt(3.0)
                if array_mode == "TOWED":
                    uncertainty *= self._endfire_factor(true_bearing)
                observations[array_mode] = dict(
                    bearing=bearing, quality=quality, snr=s_db, last_seen=t,
                    uncertainty_deg=uncertainty)
                if spectral:
                    spectral_by_mode[array_mode] = spectral[0]
            if not observations:
                continue
            c = self._get_contact(tgt)
            c._fx, c._fy = frigate.x, frigate.y
            c.observer_x, c.observer_y = frigate.x, frigate.y
            c.ship_observer_x, c.ship_observer_y = frigate.x, frigate.y
            c.passive_source = "SONAR-BRG"
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
            ambiguous = False
            if bow is not None and "BOW" in observations:
                # The hull array is unambiguous: it resolves the towed side.
                if c.towed_ambiguous:
                    c.towed_ambiguous, c.towed_resolved = False, True
                    c.mirror_bearing = c.ambiguity_axis = None
            elif set(observations) == {"TOWED"}:
                axis = self.tow_heading_deg
                if not c.towed_ambiguous and not c.towed_resolved:
                    c.towed_ambiguous, c.ambiguity_axis = True, axis
                if c.towed_ambiguous and abs(config.angle_diff_deg(
                        axis, c.ambiguity_axis)) >= config.TAS_AMBIGUITY_RESOLVE_DEG:
                    # After an own turn only one side stays consistent.
                    c.towed_ambiguous, c.towed_resolved = False, True
                    c.mirror_bearing = c.ambiguity_axis = None
                if c.towed_ambiguous:
                    mirror = (2.0 * axis - bearing) % 360.0
                    # Without other evidence the display takes the starboard
                    # candidate; it is the true one only half of the time.
                    if config.angle_diff_deg(bearing, axis) < 0.0:
                        bearing, mirror = mirror, bearing
                    c.mirror_bearing = mirror
                    c.fusion_status = "TAS L/R?"
                    ambiguous = True
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
            # W1: Peilungs-Track (TMA-Datenbasis). Side-ambiguous towed
            # bearings stay out of TMA until the ambiguity is resolved.
            tr = self._tracks.setdefault(tgt.id, BearingTrack())
            if not ambiguous and (not tr.pts or t - tr.pts[-1].t
                                  >= config.BEARING_TRACK_MIN_INTERVAL_S):
                c.tonal_hz = self._measure_tonal(tgt, frigate, quality, t)
                tr.add(t, bearing, frigate.x, frigate.y, frigate.course,
                       uncertainty, c.tonal_hz, frigate.speed)
            detected_ids.add(tgt.id)
            listen_observation = observations.get(mode)
            if sample_due and listen_observation is not None:
                broadband = getattr(tgt, "broadband", lambda: {})()
                source = {"bearing": listen_observation["bearing"],
                          "level": listen_observation["quality"],
                          "lines": [(line[0] * doppler_factor(tgt, frigate),)
                                    + tuple(line[1:])
                                    for line in tgt.lofar_lines(t)],
                          "seed": getattr(tgt, "sensor_seed", tgt.id),
                          "spectral_gains": spectral_by_mode.get(
                              mode, ((100.0, 1.0),))}
                if isinstance(broadband, dict) and broadband.get("level", 0) > 0:
                    source["broadband"] = broadband
                sources.append(source)

        # Measurements belong to the helicopter. Keep each buoy's own ray;
        # only two independent passive rays or an active echo provide a fix.
        active_buoys = [b for b in buoys if getattr(b, "active", False)]
        for contact in self.contacts.values():
            contact.buoy_reports = {
                seq: report for seq, report in contact.buoy_reports.items()
                if t - report["measured_at"] < config.SONAR_CONTACT_LOST_S
                and any(b.seq == seq for b in active_buoys)}
        ping_epoch = int(t // config.BUOY_PING_COOLDOWN_S)
        ping_buoys = {b.seq for b in active_buoys
                      if getattr(b, "mode", "PASSIVE") == "ACTIVE"
                      and getattr(b, "last_ping_epoch", -1) < ping_epoch}
        for tgt in targets if active_buoys else ():
            if tgt_gone(tgt):
                continue
            reports = []
            for b in active_buoys:
                if getattr(b, "mode", "PASSIVE") == "ACTIVE" and b.seq not in ping_buoys:
                    continue
                dist = math.hypot(tgt.x - b.x, tgt.y - b.y)
                if dist >= config.BUOY_RANGE_NM * 1.8:
                    continue
                if (hasattr(world, "sonar_path_blocked")
                        and world.sonar_path_blocked(
                            b.x, b.y, 5.0, tgt.x, tgt.y,
                            getattr(tgt, "depth", 0.0))):
                    continue
                # Passive sonar equation for the buoy hydrophone: ambient
                # limited, small aperture, ray-traced path from its depth.
                buoy_depth = float(getattr(b, "hydrophone_depth_m", 30.0))
                frequency = representative_frequency_hz(tgt)
                ray = propagation.ray_excess_db(
                    world, b.x, b.y, buoy_depth, tgt.x, tgt.y,
                    float(getattr(tgt, "depth", 0.0)), frequency)
                if ray is None:
                    ray = (6.5 if (tgt.depth > world.thermocline_depth_m(b.x, b.y))
                           != (buoy_depth > world.thermocline_depth_m(b.x, b.y))
                           else 0.0)
                terms = equation.passive_terms(
                    frequency_hz=frequency, distance_nm=dist,
                    target_bonus=(1.0 + 0.8 * (1.0 - tgt.quiet_factor()))
                    * source_level_factor(tgt),
                    excess_path_loss_db=ray,
                    absorption_db_per_km=equation.francois_garrison_db_per_km(
                        frequency, _surface_temperature(world)),
                    legacy_absorption_db=0.0, own_range_factor=1.0,
                    array_range_factor=config.BUOY_RANGE_NM
                    / config.SONAR_PASSIVE_BASE_NM,
                    sea_state=float(getattr(world, "effective_sea_state",
                                            world.sea_state)),
                    rain=float(getattr(world, "rain_intensity", 0.0)),
                    shipping_contacts=self.shipping_contacts,
                    hull_self_noise=False)
                excess = terms.signal_excess_db
                if excess <= 0.0:
                    continue
                quality = config.clamp(excess / config.SONAR_SNR_QUALITY_SPAN_DB,
                                       .2, .9)
                true_bearing = math.degrees(
                    math.atan2(tgt.x - b.x, -(tgt.y - b.y))) % 360.0
                rng = random.Random(getattr(tgt, "sensor_seed", tgt.id) * 1543
                                    + b.seq * 7919 + int(t // 2.0))
                error = 2.0 + 5.0 * (1.0 - quality)
                bearing = (true_bearing + rng.uniform(-error, error)) % 360.0
                contact = self._get_contact(tgt)
                measured_range = None
                observed_x = observed_y = None
                if getattr(b, "mode", "PASSIVE") == "ACTIVE":
                    measured_range = max(0.0, dist + rng.uniform(-.25, .25))
                    angle = math.radians(bearing)
                    observed_x = b.x + measured_range * math.sin(angle)
                    observed_y = b.y - measured_range * math.cos(angle)
                    contact._fx, contact._fy = frigate.x, frigate.y
                    contact.update_buoy(observed_x, observed_y, quality, t)
                else:
                    reports.append((b, bearing, quality))
                    # Multi-static TMA: the buoy bearing joins the contact's
                    # bearing track with the buoy as the observer.
                    track = self._tracks.setdefault(tgt.id, BearingTrack())
                    track.add(t, bearing, b.x, b.y, 0.0, error / math.sqrt(3))
                contact.buoy_reports[b.seq] = dict(
                    mode=getattr(b, "mode", "PASSIVE"), bearing=bearing,
                    bearing_uncertainty_deg=error / math.sqrt(3),
                    quality=quality, measured_at=t, observer_x=b.x,
                    observer_y=b.y, range_nm=measured_range,
                    x=observed_x, y=observed_y)
                contact.confidence = min(1.0, contact.confidence
                                         + config.SONAR_CONF_PASSIVE_PER_S * dt)
                contact.quality = max(contact.quality, quality)
                contact.last_seen = t
                detected_ids.add(tgt.id)
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
            c.observer_x, c.observer_y = frigate.x, frigate.y
            if tgt.id not in detected_ids:
                c.confidence = min(1.0, c.confidence
                                   + config.SONAR_CONF_PASSIVE_PER_S * dt)
                c.quality = quality
                c.last_seen = t
            c.update_buoy(fx, fy, quality, t)
            detected_ids.add(tgt.id)
        for b in active_buoys:
            if b.seq in ping_buoys:
                b.last_ping_epoch = ping_epoch

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
                                   getattr(world, "effective_sea_state",
                                           world.sea_state), frigate.speed,
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
            self._broadband_long_accumulator.append(
                np.asarray(self.receiver.broadband, dtype=float))
            long_count = max(1, round(config.SONAR_BROADBAND_LONG_SAMPLE_S
                                      / self.receiver.block_s))
            if len(self._broadband_long_accumulator) >= long_count:
                self.broadband_long_history.append(np.mean(
                    self._broadband_long_accumulator[:long_count], axis=0).tolist())
                self.broadband_long_times.append(stamp)
                del self._broadband_long_accumulator[:long_count]
                del self.broadband_long_history[:-config.SONAR_BROADBAND_LONG_ROWS]
                del self.broadband_long_times[:-config.SONAR_BROADBAND_LONG_ROWS]
            self.demon_history.append(list(self.receiver.demon_spectrum))
            self.demon_times.append(stamp)
            del self.demon_history[:-config.SONAR_DEMON_HISTORY_ROWS]
            del self.demon_times[:-config.SONAR_DEMON_HISTORY_ROWS]
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
            data["blade_rate_hz"], None, data["tonal_hz"], data["cavitation"],
            self.acoustic_profiles)

    def cycle_pulse(self) -> str:
        order = tuple(equation.PULSES)
        self.ping_pulse = order[(order.index(self.ping_pulse) + 1) % len(order)]
        return self.ping_pulse

    def _masked_by_wreck(self, tgt, frigate, world, mode: str) -> bool:
        """Target echo hidden in a wreck echo (same range cell and beam, no
        Doppler).  The finer LFM range resolution can separate them."""
        ocean = getattr(world, "ocean", None)
        if ocean is None or not hasattr(tgt, "stype"):
            return False
        bearing = math.degrees(math.atan2(tgt.x - frigate.x, -(tgt.y - frigate.y))) % 360.0
        radial = getattr(tgt, "speed", 0.0) * math.cos(math.radians(
            config.angle_diff_deg((bearing + 180.0) % 360.0, getattr(tgt, "course", 0.0))))
        target_range = math.hypot(tgt.x - frigate.x, tgt.y - frigate.y) * 1852.0
        beam = 6.0 if mode == "TOWED" else equation.ACTIVE_BEAMWIDTH_DEG
        for hazard in ocean.hazards:
            if hazard.kind != "wreck":
                continue
            if math.hypot(hazard.x_nm - tgt.x, hazard.y_nm - tgt.y) > 0.5:
                continue
            if equation.echo_merges_with_clutter(
                    target_range, bearing, radial,
                    math.hypot(hazard.x_nm - frigate.x, hazard.y_nm - frigate.y) * 1852.0,
                    math.degrees(math.atan2(hazard.x_nm - frigate.x,
                                            -(hazard.y_nm - frigate.y))) % 360.0,
                    self.ping_pulse, beam):
                return True
        return False

    def _queue_clutter(self, frigate, world, t_real: float,
                       range_factor: float, mode: str) -> None:
        """Wrecks on the seabed return real echoes that no contact owns."""
        ocean = getattr(world, "ocean", None)
        if ocean is None:
            return
        source_depth = self.towed_depth_m if mode == "TOWED" else 5.0
        for index, hazard in enumerate(ocean.hazards):
            if (hazard.kind != "wreck"
                    or len(self._pending_clutter) >= self.MAX_PENDING_CLUTTER):
                continue
            distance = math.hypot(hazard.x_nm - frigate.x, hazard.y_nm - frigate.y)
            if distance > self.CLUTTER_SEARCH_NM or distance < 0.05:
                continue
            echo = _WreckEcho(index, hazard, ocean.seed)
            terms = self.active_terms(echo, frigate, world, range_factor, mode)
            if terms.signal_excess_db <= 0.0:
                continue
            if (hasattr(world, "sonar_path_blocked")
                    and world.sonar_path_blocked(frigate.x, frigate.y, source_depth,
                                                 echo.x, echo.y, echo.depth)):
                continue
            snapshot = self._measure_ping(frigate, echo, t_real, distance,
                                          terms.signal_excess_db, self.ping_pulse)
            self._pending_clutter.append({
                "ready_at": t_real + _echo_delay(world, distance, frigate, echo),
                "mode": mode, "snapshot": snapshot})

    def active_terms(self, tgt, frigate, world, range_factor: float,
                     mode: str, pulse: str | None = None):
        """Active sonar equation for one echo from ``tgt``."""
        ping_mult = (config.SONAR_ARRAY_TOWED_PING if mode == "TOWED"
                     else config.SONAR_ARRAY_BOW_PING)
        gain = (config.HELO_DIP_ACTIVE_RANGE_NM / config.SONAR_ACTIVE_BASE_NM
                if mode == "DIPPING" else ping_mult) * range_factor
        layer = 1.0
        if getattr(tgt, "depth", 0.0) >= world.thermocline_depth_m(tgt.x, tgt.y):
            layer = config.SONAR_THERMO_ACTIVE_BELOW
        distance = max(1e-6, math.hypot(tgt.x - frigate.x, tgt.y - frigate.y))
        to_observer = math.degrees(math.atan2(frigate.x - tgt.x,
                                              -(frigate.y - tgt.y))) % 360.0
        aspect = config.angle_diff_deg(to_observer, getattr(tgt, "course", 0.0))
        speed = getattr(tgt, "speed", None)
        if speed is None:
            speed = getattr(tgt, "speed_kn", 0.0)
        radial = speed * math.cos(math.radians(aspect))
        mx, my = (frigate.x + tgt.x) * .5, (frigate.y + tgt.y) * .5
        return equation.active_terms(
            distance_nm=distance,
            target_ts_db=(equation.target_strength_db(hull_length_m(tgt), aspect)
                          + getattr(tgt, "extra_ts_db", 0.0)),
            legacy_range_factor=layer, gain_factor=gain,
            sea_state=float(getattr(world, "effective_sea_state", world.sea_state)),
            rain=float(getattr(world, "rain_intensity", 0.0)),
            pulse=pulse or self.ping_pulse,
            water_depth_m=float(getattr(world, "depth_m", lambda x, y: 1000.0)(mx, my)),
            lambert_mu_db=_lambert_mu_db(world, mx, my),
            wind_kn=float(getattr(world, "wind_speed_kn", 10.0)),
            absorption_db_per_km=equation.francois_garrison_db_per_km(
                equation.ACTIVE_FREQUENCY_HZ, _surface_temperature(world)),
            radial_speed_kn=radial)

    def _active_range_nm(self, tgt, world, range_factor: float, mode: str,
                         frigate=None) -> float:
        """Equivalent range: the echo is detectable while distance < R."""
        if frigate is None:
            return 0.0
        terms = self.active_terms(tgt, frigate, world, range_factor, mode)
        distance = math.hypot(tgt.x - frigate.x, tgt.y - frigate.y)
        return max(distance, 1e-6) * 10.0 ** (terms.signal_excess_db / 40.0)

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
        clutter = []
        for echo in self._pending_clutter:
            if t >= echo["ready_at"]:
                entry = {key: value for key, value in echo["snapshot"].items()
                         if key not in ("observer_x", "observer_y")}
                entry.update(contact_id=0, mode=echo["mode"])
                self.echo_history.append(entry)
                del self.echo_history[:-config.SONAR_ECHO_HISTORY_MAX]
                self.echo_events.append(dict(entry))
                del self.echo_events[:-config.SONAR_ECHO_HISTORY_MAX]
            else:
                clutter.append(echo)
        self._pending_clutter = clutter
        pending = []
        for ping in self._pending_pings:
            target = ping["target"]
            if tgt_gone(target):
                continue
            if t >= ping["ready_at"]:
                contact = self._apply_ping_snapshot(
                    target, ping["snapshot"], ping["mode"], fixed_at=t)
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
                  "range_sigma_nm": (1e-9, equation.range_resolution_m(
                      "CW") / 1852.0 / math.sqrt(2.0)),
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
    def _measure_ping(frigate, target, t: float, distance: float,
                      signal: float, pulse: str = equation.DEFAULT_PULSE):
        """Deterministic noisy snapshot; no shared RNG or contact allocation.

        Range accuracy follows the pulse (CW resolution c*tau/2, LFM c/2B)
        and the echo SNR (Cramer-Rao); bearing and depth errors shrink with
        SNR as before."""
        error_scale = 1.0 / max(1.0, 1.0 + signal / 8.0)
        seed = getattr(target, "sensor_seed", target.id)
        range_sigma = equation.range_sigma_m(pulse, signal) / 1852.0
        snapshot = dict(
            t=t, observer_x=frigate.x, observer_y=frigate.y,
            bearing=(target.bearing_from_frigate(frigate) + 1.5 * error_scale
                     * _correlated_uniform(seed, t, 1.0, 101)) % 360.0,
            range_nm=max(0.0, distance + math.sqrt(3.0) * range_sigma
                         * _correlated_uniform(seed, t, 1.0, 211)),
            depth_m=max(0.0, target.depth + config.SONAR_PING_DEPTH_ERROR_M
                        * error_scale * _correlated_uniform(seed, t, 1.0, 307)),
            range_sigma_nm=range_sigma,
            depth_sigma_m=config.SONAR_PING_DEPTH_ERROR_M * error_scale / math.sqrt(3),
            snr_db=signal)
        if not SonarSystem.valid_ping_snapshot(snapshot):
            raise ValueError("invalid active sonar measurement")
        return snapshot

    def _apply_ping_snapshot(self, target, snapshot, mode, fixed_at=None):
        c = self._get_contact(target)
        # A late return must not replace an already newer active measurement.
        if c.range_source != "ping" or c.range_seen is None or snapshot["t"] >= c.range_seen:
            last_seen = c.last_seen
            c._fx, c._fy = snapshot["observer_x"], snapshot["observer_y"]
            c.observer_x, c.observer_y = c._fx, c._fy
            c.update_ping(
                bearing=snapshot["bearing"], range_est=snapshot["range_nm"],
                depth_est=snapshot["depth_m"],
                confidence=c.confidence + config.SONAR_CONF_PING_BONUS,
                t=snapshot["t"], snr=snapshot["snr_db"],
                range_sigma_nm=snapshot["range_sigma_nm"],
                depth_sigma_m=snapshot["depth_sigma_m"], fixed_at=fixed_at,
                fix_source="DIPPING" if mode == "DIPPING" else "PING")
            c.last_seen = max(last_seen, c.last_seen)
        self.echo_history.append({
            key: value for key, value in dict(snapshot, contact_id=c.id, mode=mode).items()
            if key not in ("observer_x", "observer_y")})
        del self.echo_history[:-config.SONAR_ECHO_HISTORY_MAX]
        return c

    def _measure_tonal(self, tgt, frigate, quality: float, t: float):
        """Doppler-shifted frequency of the strongest tonal (None if weak)."""
        if quality < DOPPLER_MIN_QUALITY:
            return None
        lines = [line for line in (tgt.lofar_lines(t) or ()) if line[0] > 1.0]
        if not lines:
            return None
        frequency = max(lines, key=lambda line: (line[1], -line[0]))[0]
        seed = getattr(tgt, "sensor_seed", tgt.id)
        noise = (DOPPLER_SIGMA_HZ * (1.4 - 0.8 * quality)
                 * _correlated_uniform(seed, t, 10.0, 613))
        return frequency * doppler_factor(tgt, frigate) + noise

    def _endfire_factor(self, true_bearing: float) -> float:
        """Line-array bearing accuracy degrades as 1/sqrt(sin) toward endfire
        (beam broadening; Cramer-Rao ~ 1/sin of the angle off the axis)."""
        off_axis = abs(math.sin(math.radians(true_bearing - self.tow_heading_deg)))
        return 1.0 / math.sqrt(max(off_axis, 0.25))

    def _observed_bearing(self, tgt, true_bearing: float, frigate,
                          quality: float, mode: str, t: float) -> float:
        """Peilung mit deterministisch korreliertem, glatt interpoliertem Fehler."""
        err = bearing_error_deg(mode, frigate.speed, quality)
        if mode == "TOWED":
            err *= self._endfire_factor(true_bearing)
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
        sol = solve_tma(tr, previous_course=c.tma_course,
                        previous_speed=c.tma_speed)
        if sol is not None:
            c.update_tma(sol, tr.pts[-1].t, fixed_at=t)
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
            active_range = self._active_range_nm(tgt, world, range_factor, mode,
                                                 frigate)
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

            # Echo erhalten?  A stopped boat lying beside a wreck returns an
            # echo that merges with the wreck's own clutter echo.
            if dist < active_range and not self._masked_by_wreck(
                    tgt, frigate, world, mode):
                snapshot = self._measure_ping(
                    frigate, tgt, t_real, dist,
                    self.active_terms(tgt, frigate, world, range_factor,
                                      mode).signal_excess_db, self.ping_pulse)
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
