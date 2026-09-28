"""The crewed boat's own ESM: intercepts, emitter memory, bearing history
and cross-fix (save ``crew.esm``).

With the mast raised at periscope depth the boat's ESM antenna hears radar
emissions through the same signal path as the frigate (``scan_for_signals``
with the boat as observer): bearing, band, PRF, modulation and received
level.  Nothing here publishes an emitter's identity or position.  The
crew keeps an emitter list across mast periods, may classify an emitter
from the library (an annotation, never truth), and builds a cross-fix from
its own positions along the bearing history.  The model is deterministic:
stateless noise keyed by seed, boat, signal and tick, stable iteration and
a bounded, saved picture.
"""

from __future__ import annotations

from dataclasses import asdict
import math

from src.core import config, detrand
from src.core import plot as plot_geometry
from src.sensors import radar as radar_physics
from src.sensors.esm import (ESM_ASSOCIATION_MAX_GAP_S, ESMMeasurement, ESMTrack,
                             POWER_CLASS_RANGE_NM, RadarSuiteController, SignalType,
                             _validate_track, estimated_range_nm, library_emitters,
                             scan_for_signals, spectrum_band)
from src.sensors.platform import MAST_DEPTH_M

VERSION = 1
# Radar roles that look for surface targets: an intercept of one close
# enough to see the mast raises the mast warning.
MAST_THREAT_ROLES = frozenset(("navigation", "surface_search", "multi_function",
                               "fire_control"))
HISTORY_FIELDS = 6          # t, x, y, bearing, sigma, level
LIBRARY_MAX = 16
_EMITTER_FIELDS = {"track", "history", "label", "peak_db"}
_STATE_FIELDS = {"version", "track_seq", "last_tick", "mast_since", "threat_warned",
                 "overtime_warned", "emitters"}


def _finite(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _angle(first: float, second: float) -> float:
    """Signed difference first - second in (-180, 180]."""
    return (first - second + 180.0) % 360.0 - 180.0


def emitter_number(track_key: str) -> int:
    return int(track_key[1:], 16)


def emitter_label(track_key: str) -> str:
    """The crew's short name of an emitter: ``E`` and its running number."""
    return f"E{emitter_number(track_key)}"


# --- environment ----------------------------------------------------------------

def mast_radar_nm(sea_state: float, rain: float) -> float:
    """Range at which a reference surface-search radar (the frigate class's
    nominal set) sees a raised mast with Pd = 0.5 per look, capped by the
    radar horizon (the model of the simulation's mast echoes)."""
    horizon = config.radar_horizon_nm(config.RADAR_ANTENNA_HEIGHT_M,
                                      config.SUB_MAST_HEIGHT_M)
    nominal = config.RADAR_SURFACE_RANGE_NM
    return min(horizon, nominal * radar_physics.detection_fraction(
        "surface", sea_state, rain, nominal, rcs_factor=config.SUB_MAST_RCS_FACTOR))


def _weather(world) -> tuple[float, float]:
    sea = float(getattr(world, "effective_sea_state", world.sea_state))
    rain = config.clamp(float(getattr(world, "rain_intensity", 0.0)), 0.0, 1.0)
    return sea, rain


def wash_fraction(sea_state: float) -> float:
    """Fraction of scans lost to waves washing over the mast antenna."""
    return config.clamp((sea_state - config.UBOOT_ESM_WASH_SEA_STATE)
                        * config.UBOOT_ESM_WASH_PER_SEA, 0.0, config.UBOOT_ESM_WASH_MAX)


def recommended_mast_time_s(sea_state: float, rain: float, threat: bool) -> float:
    """Mast time the crew recommends: short in a calm sea, longer when sea
    clutter hides the mast; short while a search radar can see it."""
    if threat:
        return config.UBOOT_MAST_TIME_THREAT_S
    calm = mast_radar_nm(0.0, 0.0)
    hidden = 0.0 if calm <= 0.0 else config.clamp(
        1.0 - mast_radar_nm(sea_state, rain) / calm, 0.0, 1.0)
    return config.UBOOT_MAST_TIME_BASE_S + config.UBOOT_MAST_TIME_CLUTTER_S * hidden


# --- pure evaluation of the crew's own data ---------------------------------------

def cross_fix(samples, now: float) -> dict | None:
    """Maximum-likelihood crossing of bearing lines taken from own positions.

    ``samples`` are ``(t, x, y, bearing, sigma_deg)``.  A linear
    least-squares intersection starts a Gauss-Newton fit on the bearing
    residuals; each line's angular error adds the emitter's possible drift
    since it was taken (``UBOOT_ESM_FIX_EMITTER_KN``), so the fix is the
    emitter's position now.  Returns the fix, its 95 % error ellipse
    (semi-axes in NM, major-axis bearing) and whether the lines agree with
    one slow emitter; None without a usable crossing (too few lines, a
    baseline too short, or a point behind a bearing)."""
    drift = config.kn_to_nm_per_s(config.UBOOT_ESM_FIX_EMITTER_KN)
    rows = [(float(x), float(y), math.radians(b), math.radians(max(0.1, float(s))),
             drift * max(0.0, now - t)) for t, x, y, b, s in samples]
    if len(rows) < config.UBOOT_ESM_FIX_MIN_SAMPLES:
        return None
    # Linear start: perpendicular distances of the lines, equal weights.
    a11 = a12 = a22 = b1 = b2 = 0.0
    for x, y, rad, _sigma, _moved in rows:
        nx, ny = math.cos(rad), math.sin(rad)
        c = nx * x + ny * y
        a11, a12, a22 = a11 + nx * nx, a12 + nx * ny, a22 + ny * ny
        b1, b2 = b1 + nx * c, b2 + ny * c
    det = a11 * a22 - a12 * a12
    if not math.isfinite(det) or det <= 1e-9 * max(1.0, (a11 + a22) ** 2):
        return None
    px, py = (a22 * b1 - a12 * b2) / det, (a11 * b2 - a12 * b1) / det
    limit = 4.0 * config.ESM_RANGE_NM
    h11 = h12 = h22 = 0.0
    for _ in range(8):
        h11 = h12 = h22 = g1 = g2 = 0.0
        for x, y, rad, sigma, moved in rows:
            dx, dy = px - x, py - y
            r2 = max(1e-6, dx * dx + dy * dy)
            predicted = math.atan2(dx, -dy)
            residual = (rad - predicted + math.pi) % (2.0 * math.pi) - math.pi
            spread2 = sigma * sigma + moved * moved / r2
            jx, jy = -dy / r2, dx / r2
            h11 += jx * jx / spread2
            h12 += jx * jy / spread2
            h22 += jy * jy / spread2
            g1 += jx * residual / spread2
            g2 += jy * residual / spread2
        det = h11 * h22 - h12 * h12
        if not math.isfinite(det) or det <= 0.0:
            return None
        step_x, step_y = (h22 * g1 - h12 * g2) / det, (h11 * g2 - h12 * g1) / det
        px, py = px + step_x, py + step_y
        if not (math.isfinite(px) and math.isfinite(py)) or max(
                math.hypot(px - x, py - y) for x, y, *_rest in rows) > limit:
            return None
        if math.hypot(step_x, step_y) < 1e-4:
            break
    for x, y, rad, _sigma, _moved in rows:
        if math.sin(rad) * (px - x) - math.cos(rad) * (py - y) <= 0.0:
            return None
    # Own motion must have swung the bearing enough (seen from the fix).
    seen = [math.atan2(x - px, -(y - py)) for x, y, *_rest in rows]
    swing = max(abs(math.degrees((a - b + math.pi) % (2.0 * math.pi) - math.pi))
                for a in seen for b in seen)
    if swing < config.UBOOT_ESM_FIX_MIN_SWING_DEG:
        return None
    c11, c12, c22 = h22 / det, -h12 / det, h11 / det
    half, root = (c11 + c22) / 2.0, math.hypot((c11 - c22) / 2.0, c12)
    major = math.sqrt(max(0.0, half + root)) * config.UBOOT_ESM_FIX_CONFIDENCE
    minor = math.sqrt(max(0.0, half - root)) * config.UBOOT_ESM_FIX_CONFIDENCE
    last_x, last_y = rows[-1][0], rows[-1][1]
    if (not math.isfinite(major) or major > config.UBOOT_ESM_FIX_MAX_AXIS_NM
            or major > config.UBOOT_ESM_FIX_MAX_AXIS_RATIO * math.hypot(px - last_x,
                                                                      py - last_y)):
        return None
    vx, vy = (c12, half + root - c11) if abs(c12) > 1e-15 else (
        (1.0, 0.0) if c11 >= c22 else (0.0, 1.0))
    axis = math.degrees(math.atan2(vx, -vy)) % 180.0
    chi2 = 0.0
    for x, y, rad, sigma, moved in rows:
        dx, dy = px - x, py - y
        r2 = max(1e-6, dx * dx + dy * dy)
        residual = (rad - math.atan2(dx, -dy) + math.pi) % (2.0 * math.pi) - math.pi
        chi2 += residual * residual / (sigma * sigma + moved * moved / r2)
    chi2 /= max(1, len(rows) - 2)
    return dict(x=px, y=py, major_nm=major, minor_nm=minor, axis_deg=axis,
                lines=len(rows), consistent=chi2 <= config.UBOOT_ESM_FIX_CHI2_MAX)


def level_trend(history, now: float):
    """Slope (dB/min) of the received level over the trend window, and its
    reading ``rising``/``steady``/``falling``; (None, None) without data."""
    rows = [(row[0], row[5]) for row in history
            if now - row[0] <= config.UBOOT_ESM_TREND_WINDOW_S]
    if len(rows) < 3 or rows[-1][0] - rows[0][0] < 30.0:
        return None, None
    mean_t = sum(t for t, _ in rows) / len(rows)
    mean_l = sum(level for _, level in rows) / len(rows)
    spread = sum((t - mean_t) ** 2 for t, _ in rows)
    if spread <= 0.0:
        return None, None
    slope = sum((t - mean_t) * (level - mean_l) for t, level in rows) / spread * 60.0
    limit = config.UBOOT_ESM_TREND_DB_PER_MIN
    return slope, ("rising" if slope > limit else "falling" if slope < -limit else "steady")


class BoatEmitter:
    """One emitter in the crew's list: the associated track, its bearing
    history from own positions and the crew's library classification."""

    def __init__(self, track: ESMTrack):
        self.track = track
        self.history: list[list[float]] = []
        self.label: str | None = None
        self.peak_db: float | None = None

    def fix(self, now: float) -> dict | None:
        return cross_fix([row[:5] for row in self.history
                          if now - row[0] <= config.UBOOT_ESM_FIX_WINDOW_S], now)

    def to_save(self) -> dict:
        return dict(track=asdict(self.track), history=[list(row) for row in self.history],
                    label=self.label, peak_db=self.peak_db)


class BoatESM:
    """The crew's ESM picture of one crewed boat."""

    def __init__(self):
        self.track_seq = 0
        self.last_tick = None
        self.mast_since = None
        self.threat_warned = False
        self.overtime_warned = False
        self.emitters: dict[str, BoatEmitter] = {}

    # -- queries ---------------------------------------------------------------

    def ordered(self) -> list[BoatEmitter]:
        """Emitters newest intercept first, then by number (stable)."""
        return sorted(self.emitters.values(),
                      key=lambda item: (-item.track.last_seen, item.track.track_key))

    def by_number(self, number) -> BoatEmitter | None:
        if type(number) is not int or number < 1:
            return None
        return self.emitters.get(f"E{number:016x}")

    @staticmethod
    def live(emitter: BoatEmitter, now: float) -> bool:
        return 0.0 <= now - emitter.track.last_seen <= config.UBOOT_ESM_LIVE_S

    def mast_time_s(self, now: float) -> float | None:
        return None if self.mast_since is None else max(0.0, now - self.mast_since)

    # -- the crew's evaluation (catalog library, annotations) -------------------

    @staticmethod
    def library(game, emitter: BoatEmitter) -> tuple:
        """Library emitters whose published ranges hold the measurement
        (unranked, by key), as the frigate's ELOKA without assistance."""
        return tuple(item.emitter_key for item in library_emitters(
            emitter.track, game.runtime_catalog.emitters, LIBRARY_MAX))

    @staticmethod
    def classified(game, emitter: BoatEmitter):
        profile = game.runtime_catalog.emitters.get(emitter.label)
        return profile if getattr(profile, "domain", None) == "radar" else None

    def assumed_profiles(self, game, emitter: BoatEmitter) -> list:
        profile = self.classified(game, emitter)
        if profile is not None:
            return [profile]
        emitters = game.runtime_catalog.emitters
        return [emitters[key] for key in self.library(game, emitter)]

    def range_estimate_nm(self, game, emitter: BoatEmitter) -> float | None:
        """Range from the peak level for the classified power class; without
        a classification the shortest range the library allows."""
        profiles = self.assumed_profiles(game, emitter)
        classes = sorted({getattr(item, "power_class", "medium") for item in profiles},
                         key=lambda item: POWER_CLASS_RANGE_NM.get(item, 100.0))
        power = classes[0] if classes else "medium"
        return estimated_range_nm(emitter.track, power)

    def mast_threat(self, game, emitter: BoatEmitter, now: float,
                    mast_range_nm: float) -> bool:
        """A live search radar whose estimated range is inside the range at
        which such a radar sees the mast in this sea (crew evaluation)."""
        if not self.live(emitter, now):
            return False
        profiles = self.assumed_profiles(game, emitter)
        roles = {getattr(item, "radar_role", None) for item in profiles}
        if profiles and not roles & MAST_THREAT_ROLES:
            return False
        if SignalType.FIRE_CONTROL.value in roles and self.classified(game, emitter):
            return True
        estimate = self.range_estimate_nm(game, emitter)
        return estimate is not None and estimate <= mast_range_nm

    def classify(self, game, number, candidate) -> bool | str:
        emitter = self.by_number(number)
        if emitter is None:
            return "stale_ref"
        if candidate == -1:
            emitter.label = None
            return True
        library = self.library(game, emitter)
        if type(candidate) is not int or not 0 <= candidate < len(library):
            return "stale_ref"
        emitter.label = library[candidate]
        return True

    def cycle_classification(self, game, number, step: int = 1) -> bool | str:
        """Step through the library suggestions for the emitter, with
        "unclassified" between the last and the first."""
        emitter = self.by_number(number)
        if emitter is None:
            return "stale_ref"
        library = self.library(game, emitter)
        position = library.index(emitter.label) + 1 if emitter.label in library else 0
        position = (position + (1 if step >= 0 else -1)) % (len(library) + 1)
        return self.classify(game, number, position - 1)

    # -- the scan ---------------------------------------------------------------

    def update(self, game, boat) -> None:
        """One intercept scan per ``UBOOT_ESM_SCAN_S`` (called at 0.25 s)."""
        sub, orders = boat.sub, boat.orders
        now = float(game.sim_t)
        tick = math.floor(now / config.UBOOT_ESM_SCAN_S + 1e-6)
        if tick == self.last_tick:
            return
        self.last_tick = tick
        self._expire(now)
        up = bool(orders.mast and not sub.sunk and sub.depth <= MAST_DEPTH_M)
        if not up:
            self.mast_since = None
            self.threat_warned = self.overtime_warned = False
            return
        if self.mast_since is None:
            self.mast_since = now
        sea, rain = _weather(game.world)
        washed = detrand.u01(game.seed, "boat-esm-wash", sub.id, tick) < wash_fraction(sea)
        if not washed:
            self._observe(self._scan(game, sub, now), now, orders)
        mast_range = mast_radar_nm(sea, rain)
        threats = [item for item in self.ordered()
                   if self.mast_threat(game, item, now, mast_range)]
        if threats and not self.threat_warned:
            orders.event("esm_mast_threat", emitter=emitter_label(threats[0].track.track_key),
                         bearing=f"{threats[0].track.bearing:03.0f}")
        self.threat_warned = bool(threats)
        limit = recommended_mast_time_s(sea, rain, bool(threats))
        over = now - self.mast_since > limit
        if over and not self.overtime_warned:
            orders.event("mast_overtime", seconds=f"{limit:.0f}")
        self.overtime_warned = over

    def _scan(self, game, sub, now: float):
        heights = {}
        signals = []
        for signal, height in emissions(game):
            heights[id(signal)] = height
            signals.append(signal)
        mast = config.UBOOT_ESM_ANTENNA_M
        world = game.world

        def line_of_sight(signal) -> bool:
            distance = math.hypot(signal.x - sub.x, signal.y - sub.y)
            return (distance <= config.radar_horizon_nm(mast, heights[id(signal)])
                    and not world.land_blocks_line(sub.x, sub.y, signal.x, signal.y))

        seed = int(getattr(sub, "sensor_seed", sub.id))
        return scan_for_signals(
            signals, observer_x=sub.x, observer_y=sub.y, now=now,
            maximum_range_nm=config.ESM_RANGE_NM,
            bearing_error_deg=config.UBOOT_ESM_BEARING_ERR_DEG,
            noise_for=lambda signal: game._smooth_sensor_noise(
                (seed * 7919 + int(signal.signal_id[1:9], 16)) & 0x7FFFFFFF, now, 5.0),
            line_of_sight=line_of_sight, dwell_s=config.UBOOT_ESM_SCAN_S,
            level_noise_for=lambda signal: detrand.normal(
                game.seed, "boat-esm-level", sub.id, int(signal.signal_id[1:9], 16),
                math.floor(now + 1e-6)))

    def _expire(self, now: float) -> None:
        self.emitters = {key: item for key, item in self.emitters.items()
                         if now - item.track.last_seen <= config.UBOOT_ESM_MEMORY_S}

    @staticmethod
    def _cost(track: ESMTrack, measurement: ESMMeasurement) -> float | None:
        elapsed = measurement.observed_at - track.last_seen
        if not 0.0 <= elapsed <= config.UBOOT_ESM_MEMORY_S:
            return None
        drift = min(config.UBOOT_ESM_DRIFT_MAX_DEG,
                    config.UBOOT_ESM_DRIFT_DEG_PER_MIN * elapsed / 60.0)
        gate = max(4.0, 3.0 * math.hypot(track.bearing_uncertainty_deg,
                                         measurement.bearing_uncertainty_deg)) + drift
        delta = abs(_angle(track.bearing, measurement.bearing))
        if delta > gate:
            return None
        # A frequency-agile radar hops carrier and PRF between emission
        # windows and may alternate with a fixed waveform: an agile intercept
        # associates by bearing and band only, a fixed one by its whole
        # fingerprint (an agile-only emitter adopts the first fixed one).
        m_agile = measurement.modulation_code == "frequency_agile"
        t_agile = track.modulation_code == "frequency_agile"
        agile = m_agile or t_agile
        f_scale = max(500e6 if agile else 50e6, track.frequency_hz * (0.75 if agile else 0.08))
        f_delta = abs(track.frequency_hz - measurement.frequency_hz)
        if f_delta > f_scale:
            return None
        p_scale = p_delta = 0.0
        if not agile:
            if (track.prf_hz is None) != (measurement.prf_hz is None):
                return None
            if track.prf_hz is not None:
                p_scale = max(50.0, track.prf_hz * 0.25)
                p_delta = abs(track.prf_hz - measurement.prf_hz)
                if p_delta > p_scale:
                    return None
            if (track.modulation_code != measurement.modulation_code and "unknown" not in (
                    track.modulation_code, measurement.modulation_code)):
                return None
        return (delta / gate + f_delta / f_scale + (p_delta / p_scale if p_scale else 0.0)
                + elapsed / config.UBOOT_ESM_MEMORY_S)

    def _observe(self, measurements, now: float, orders) -> None:
        # Fixed-waveform intercepts associate first (their fingerprint is
        # decisive), then the agile ones by bearing and band.
        used_keys, used = set(), set()
        for agile_pass in (False, True):
            pairs = []
            for index, measurement in enumerate(measurements):
                if (measurement.modulation_code == "frequency_agile") != agile_pass:
                    continue
                for key, emitter in self.emitters.items():
                    if key in used_keys:
                        continue
                    cost = self._cost(emitter.track, measurement)
                    if cost is not None:
                        pairs.append((cost, key, index))
            for _cost, key, index in sorted(pairs):
                if key in used_keys or index in used:
                    continue
                used_keys.add(key)
                used.add(index)
                self._update(self.emitters[key], measurements[index], now)
        for index, measurement in enumerate(measurements):
            if index in used:
                continue
            # An agile hop on the bearing of an emitter heard in this scan is
            # taken as that platform's, not as a new emitter.
            if measurement.modulation_code == "frequency_agile" and any(
                    self._cost(self.emitters[key].track, measurement) is not None
                    for key in sorted(used_keys)):
                continue
            if len(self.emitters) >= config.UBOOT_ESM_EMITTERS_MAX:
                oldest = min(self.emitters.values(), key=lambda item: (
                    item.track.last_seen, item.track.track_key))
                if now - oldest.track.last_seen <= config.UBOOT_ESM_LIVE_S:
                    continue
                del self.emitters[oldest.track.track_key]
            if self.track_seq >= 2**63 - 1:
                break
            self.track_seq += 1
            key = f"E{self.track_seq:016x}"
            emitter = BoatEmitter(ESMTrack(
                track_key=key, observer_x=measurement.observer_x,
                observer_y=measurement.observer_y, bearing=measurement.bearing,
                bearing_uncertainty_deg=measurement.bearing_uncertainty_deg,
                frequency_hz=measurement.frequency_hz, prf_hz=measurement.prf_hz,
                modulation_code=measurement.modulation_code, quality=measurement.quality,
                first_seen=measurement.observed_at, last_seen=measurement.observed_at,
                synthetic_assumption=measurement.synthetic_assumption,
                signal_db=measurement.signal_db))
            self.emitters[key] = emitter
            self._sample(emitter, measurement)
            orders.event("esm_intercept", emitter=emitter_label(key),
                         bearing=f"{measurement.bearing % 360.0:03.0f}")

    def _update(self, emitter: BoatEmitter, measurement: ESMMeasurement, now: float) -> None:
        track = emitter.track
        gap = measurement.observed_at - track.last_seen
        # After a silence (a dive, a washed antenna) the fresh bearing wins.
        alpha = 0.35 if gap <= ESM_ASSOCIATION_MAX_GAP_S else 1.0
        track.bearing = (track.bearing + _angle(measurement.bearing, track.bearing)
                         * alpha) % 360.0
        track.observer_x, track.observer_y = measurement.observer_x, measurement.observer_y
        track.bearing_uncertainty_deg = measurement.bearing_uncertainty_deg
        if (measurement.modulation_code != "frequency_agile"
                or track.modulation_code == "frequency_agile"):
            track.frequency_hz = measurement.frequency_hz
            track.prf_hz = measurement.prf_hz
            track.modulation_code = measurement.modulation_code
        track.quality = measurement.quality
        if measurement.signal_db >= track.signal_db or gap > ESM_ASSOCIATION_MAX_GAP_S:
            track.signal_db = measurement.signal_db
        else:
            track.signal_db += (measurement.signal_db - track.signal_db) * 0.05
        track.last_seen = measurement.observed_at
        track.synthetic_assumption = measurement.synthetic_assumption
        emitter.peak_db = (measurement.signal_db if emitter.peak_db is None
                           else max(emitter.peak_db, measurement.signal_db))
        last = emitter.history[-1][0] if emitter.history else None
        if last is None or measurement.observed_at - last >= config.UBOOT_ESM_HISTORY_STEP_S:
            self._sample(emitter, measurement)

    @staticmethod
    def _sample(emitter: BoatEmitter, measurement: ESMMeasurement) -> None:
        level = measurement.signal_db if emitter.peak_db is None else emitter.peak_db
        emitter.history.append([float(measurement.observed_at), float(measurement.observer_x),
                                float(measurement.observer_y), float(measurement.bearing),
                                float(measurement.bearing_uncertainty_deg), float(level)])
        del emitter.history[:-config.UBOOT_ESM_HISTORY_MAX]
        emitter.peak_db = None

    # -- the crew's feeds ------------------------------------------------------

    def bearings(self, now: float) -> list:
        """Live intercepts as (bearing, quality, age) for the rose and alarms."""
        return sorted((item.track.bearing % 360.0, item.track.quality,
                       max(0.0, now - item.track.last_seen))
                      for item in self.emitters.values() if self.live(item, now))[:16]

    def to_plot(self, game, boat, number) -> bool | str:
        """Transfer the emitter to the boat's plot: its cross-fix as a mark
        with the error circle, or else the latest bearing line."""
        emitter = self.by_number(number)
        if emitter is None:
            return "stale_ref"
        label = emitter_label(emitter.track.track_key)
        fix = emitter.fix(game.sim_t)
        layer = boat.plot
        if fix is None:
            track = emitter.track
            result = game.plot_add("bearing", track.observer_x, track.observer_y, label,
                                   layer=layer, bearing=track.bearing % 360.0)
        else:
            if len(layer.objects) > plot_geometry.MAX_OBJECTS - 2:
                return "active_limit"
            result = game.plot_add("mark", fix["x"], fix["y"], label, layer=layer)
            if type(result) is int:
                result = game.plot_add("circle", fix["x"], fix["y"], label, layer=layer,
                                       radius_nm=max(0.05, min(200.0, fix["major_nm"])))
        if result == "full":
            return "active_limit"
        return True if type(result) is int else result

    # -- save -----------------------------------------------------------------

    def to_save(self) -> dict:
        return dict(version=VERSION, track_seq=self.track_seq, last_tick=self.last_tick,
                    mast_since=self.mast_since, threat_warned=self.threat_warned,
                    overtime_warned=self.overtime_warned,
                    emitters=[self.emitters[key].to_save() for key in sorted(self.emitters)])

    @staticmethod
    def valid_save(data, sim_t, emitter_keys) -> bool:
        """Exact ``crew.esm`` block of save v18 (bounded, finite, sorted)."""
        if not isinstance(data, dict) or set(data) != _STATE_FIELDS:
            return False
        if data["version"] != VERSION or type(data["version"]) is not int:
            return False
        seq, tick, since = data["track_seq"], data["last_tick"], data["mast_since"]
        if type(seq) is not int or not 0 <= seq <= 2**63 - 1:
            return False
        if not (tick is None or (type(tick) is int and 0 <= tick <= 10**12)):
            return False
        if not (since is None or (_finite(since) and 0.0 <= since <= sim_t)):
            return False
        if type(data["threat_warned"]) is not bool or type(data["overtime_warned"]) is not bool:
            return False
        rows = data["emitters"]
        if not isinstance(rows, list) or len(rows) > config.UBOOT_ESM_EMITTERS_MAX:
            return False
        previous = None
        fields = set(ESMTrack.__dataclass_fields__)
        for row in rows:
            if not isinstance(row, dict) or set(row) != _EMITTER_FIELDS:
                return False
            track = row["track"]
            if not isinstance(track, dict) or set(track) != fields:
                return False
            try:
                restored = ESMTrack(**track)
                _validate_track(restored, sim_t, seq)
            except (TypeError, ValueError):
                return False
            if previous is not None and restored.track_key <= previous:
                return False
            previous = restored.track_key
            label = row["label"]
            if not (label is None or (isinstance(label, str) and label in emitter_keys)):
                return False
            if not (row["peak_db"] is None or (_finite(row["peak_db"])
                                               and -60.0 <= row["peak_db"] <= 200.0)):
                return False
            history = row["history"]
            if not isinstance(history, list) or len(history) > config.UBOOT_ESM_HISTORY_MAX:
                return False
            last_t = -1.0
            for sample in history:
                if (not isinstance(sample, list) or len(sample) != HISTORY_FIELDS
                        or not all(_finite(value) for value in sample)):
                    return False
                t, x, y, bearing, sigma, level = sample
                if (not last_t <= t <= sim_t or abs(x) > 1e6 or abs(y) > 1e6
                        or not 0.0 <= bearing < 360.0 or not 0.05 <= sigma <= 180.0
                        or not -60.0 <= level <= 200.0):
                    return False
                last_t = t
        return True

    @classmethod
    def from_save(cls, data) -> "BoatESM":
        state = cls()
        state.track_seq = data["track_seq"]
        state.last_tick = data["last_tick"]
        state.mast_since = data["mast_since"]
        state.threat_warned = data["threat_warned"]
        state.overtime_warned = data["overtime_warned"]
        for row in data["emitters"]:
            emitter = BoatEmitter(ESMTrack(**row["track"]))
            emitter.history = [[float(value) for value in sample] for sample in row["history"]]
            emitter.label = row["label"]
            emitter.peak_db = None if row["peak_db"] is None else float(row["peak_db"])
            state.emitters[emitter.track.track_key] = emitter
        return state


# --- what the mast can hear -------------------------------------------------------

def emissions(game):
    """Internal radar emissions reaching the boat's mast, with the emitting
    antenna height (m) for the radar horizon.  Never leaves the simulation."""
    if not game.damage.ship_sunk:
        for signal in game.own_radar_signals():
            yield signal, config.RADAR_ANTENNA_HEIGHT_M
    for actor in game.civilians + game.warships:
        if actor.sunk or not actor.emitter:
            continue
        for signal in game._radar_signals(
                actor, actor.signature_key, enabled=actor.radar_emitting,
                synthetic=actor.live_mmsi is not None,
                fire_control=actor in game.warships and bool(actor.pending_asm)):
            yield signal, config.UBOOT_ESM_SHIP_ANTENNA_M
    for flight in game.flights.flights:
        for signal in game._radar_signals(
                flight, flight.akey, enabled=flight.radar_emitting or flight.kind == "civil",
                synthetic=flight.kind == "civil", fire_control=flight.akey == "su_25"):
            yield signal, float(flight.altitude_m)
    for raider in sorted(game.raiders, key=lambda item: item.seq):
        for signal in game._radar_signals(raider, "su_25", enabled=not raider.despawned,
                                          fire_control=raider.fc_radar_on):
            yield signal, float(raider.altitude_m)
    yield from own_asset_emissions(game)


def own_asset_emissions(game):
    """The frigate's aircraft radars: the helicopter's search radar while it
    flies (not in the dip) and the patrol aircraft's while it is switched on."""
    emitters = game.runtime_catalog.emitters
    helo = game.helo
    key = config.HELO_RADAR_EMITTER
    if key in emitters and helo.airborne and helo.dip_state == "STOWED":
        controller = RadarSuiteController((emitters[key],), game.seed * 31 + 1)
        for signal in controller.active_signals(game.sim_t, helo.x, helo.y):
            yield signal, config.HELO_RADAR_ALTITUDE_M
    mpa = getattr(game, "mpa", None)
    key = config.MPA_RADAR_EMITTER
    if key in emitters and mpa is not None and mpa.airborne and mpa.radar_on:
        controller = RadarSuiteController((emitters[key],), game.seed * 31 + 2)
        for signal in controller.active_signals(game.sim_t, mpa.x, mpa.y):
            yield signal, config.MPA_ALTITUDE_M


def band(frequency_hz: float) -> str:
    return spectrum_band(frequency_hz).value

