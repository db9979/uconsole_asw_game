"""Bounded passive ESM observations without entity identity."""

from __future__ import annotations

import heapq
import math
import re
from dataclasses import asdict, dataclass
from typing import Mapping


ESM_STATE_VERSION = 1
ESM_MAX_TRACKS = 64
ESM_MAX_ANNOTATIONS = 256
ESM_STALE_S = 30.0
ESM_TRACK_KEY_RE = re.compile(r"E[0-9a-f]{16}")
ESM_MODULATIONS = frozenset((
    "continuous_wave", "frequency_agile", "pulse", "pulse_doppler", "unknown",
))


@dataclass(frozen=True, slots=True)
class ESMMeasurement:
    observer_x: float
    observer_y: float
    bearing: float
    bearing_uncertainty_deg: float
    frequency_hz: float
    prf_hz: float | None
    modulation_code: str
    quality: float
    observed_at: float


@dataclass(slots=True)
class ESMTrack:
    track_key: str
    observer_x: float
    observer_y: float
    bearing: float
    bearing_uncertainty_deg: float
    frequency_hz: float
    prf_hz: float | None
    modulation_code: str
    quality: float
    first_seen: float
    last_seen: float

    def age(self, now: float) -> float:
        return max(0.0, now - self.last_seen)

    def display_quality(self, now: float, stale_s: float = ESM_STALE_S) -> float:
        return max(0.0, self.quality * (1.0 - self.age(now) / stale_s))


@dataclass(frozen=True, slots=True)
class ESMCandidate:
    emitter_key: str
    score: float


@dataclass(frozen=True, slots=True)
class ESMCorrelationEvidence:
    track_id: str
    source: str
    bearing: float
    bearing_uncertainty_deg: float | None
    x: float | None
    y: float | None
    observed_at: float


@dataclass(frozen=True, slots=True)
class ESMCorrelation:
    track_id: str
    source: str
    score: float
    ambiguous: bool


def _angle_difference(first: float, second: float) -> float:
    return abs((first - second + 180.0) % 360.0 - 180.0)


def _measurement_sort_key(measurement: ESMMeasurement) -> tuple:
    return (
        measurement.observed_at, measurement.bearing,
        measurement.bearing_uncertainty_deg, measurement.frequency_hz,
        -1.0 if measurement.prf_hz is None else measurement.prf_hz,
        measurement.modulation_code, measurement.observer_x,
        measurement.observer_y, measurement.quality,
    )


def _association_cost(track: ESMTrack, measurement: ESMMeasurement) -> float | None:
    elapsed = measurement.observed_at - track.last_seen
    if not 0.0 <= elapsed <= 5.0:
        return None
    uncertainty = math.hypot(track.bearing_uncertainty_deg,
                             measurement.bearing_uncertainty_deg)
    bearing_delta = _angle_difference(track.bearing, measurement.bearing)
    bearing_gate = max(4.0, uncertainty * 3.0)
    if bearing_delta > bearing_gate:
        return None
    frequency_scale = max(50_000_000.0, track.frequency_hz * 0.08)
    frequency_delta = abs(track.frequency_hz - measurement.frequency_hz)
    if frequency_delta > frequency_scale:
        return None
    if track.prf_hz is not None and measurement.prf_hz is not None:
        prf_scale = max(50.0, track.prf_hz * 0.25)
        prf_delta = abs(track.prf_hz - measurement.prf_hz)
        if prf_delta > prf_scale:
            return None
    else:
        prf_scale, prf_delta = 1.0, 0.0
    if (track.modulation_code != "unknown"
            and measurement.modulation_code != "unknown"
            and track.modulation_code != measurement.modulation_code):
        return None
    return (bearing_delta / bearing_gate
            + frequency_delta / frequency_scale
            + prf_delta / prf_scale + elapsed / 5.0)


class ESMPicture:
    """Associate detached measurements and retain a bounded intercept picture."""

    def __init__(self, stale_s: float = ESM_STALE_S,
                 maximum: int = ESM_MAX_TRACKS):
        self.stale_s = float(stale_s)
        self.maximum = int(maximum)
        self.track_seq = 0
        self._tracks: dict[str, ESMTrack] = {}

    def tracks(self, now: float) -> tuple[ESMTrack, ...]:
        return tuple(sorted(
            (track for track in self._tracks.values()
             if track.age(now) <= self.stale_s),
            key=lambda track: track.track_key))

    def expire(self, now: float) -> None:
        self._tracks = {
            key: track for key, track in self._tracks.items()
            if track.age(now) <= self.stale_s
        }

    def observe_batch(self, measurements, now: float) -> None:
        def checked():
            for measurement in measurements:
                _validate_measurement(measurement, now)
                yield measurement

        detached = heapq.nsmallest(self.maximum, checked(),
                                   key=_measurement_sort_key)
        for measurement in detached:
            _validate_measurement(measurement, now)
        self.expire(now)

        pairs = []
        for measurement_index, measurement in enumerate(detached):
            for track in self._tracks.values():
                cost = _association_cost(track, measurement)
                if cost is not None:
                    pairs.append((cost, track.track_key, measurement_index))
        matched_tracks, matched_measurements = set(), set()
        for _, track_key, measurement_index in sorted(pairs):
            if (track_key in matched_tracks
                    or measurement_index in matched_measurements):
                continue
            self._update_track(self._tracks[track_key], detached[measurement_index])
            matched_tracks.add(track_key)
            matched_measurements.add(measurement_index)

        for index, measurement in enumerate(detached):
            if index in matched_measurements:
                continue
            track_key = self._allocate_key()
            if track_key is None:
                break
            self._tracks[track_key] = ESMTrack(
                track_key=track_key,
                observer_x=measurement.observer_x,
                observer_y=measurement.observer_y,
                bearing=measurement.bearing,
                bearing_uncertainty_deg=measurement.bearing_uncertainty_deg,
                frequency_hz=measurement.frequency_hz,
                prf_hz=measurement.prf_hz,
                modulation_code=measurement.modulation_code,
                quality=measurement.quality,
                first_seen=measurement.observed_at,
                last_seen=measurement.observed_at,
            )
        while len(self._tracks) > self.maximum:
            evicted = min(self._tracks.values(), key=lambda track: (
                track.last_seen, track.quality, track.track_key))
            del self._tracks[evicted.track_key]

    def _allocate_key(self) -> str | None:
        if self.track_seq >= 2**63 - 1:
            return None
        self.track_seq += 1
        return f"E{self.track_seq:016x}"

    @staticmethod
    def _update_track(track: ESMTrack, measurement: ESMMeasurement) -> None:
        alpha = 0.35
        track.bearing = (track.bearing + _signed_angle_difference(
            measurement.bearing, track.bearing) * alpha) % 360.0
        track.observer_x = measurement.observer_x
        track.observer_y = measurement.observer_y
        track.bearing_uncertainty_deg = measurement.bearing_uncertainty_deg
        track.frequency_hz = measurement.frequency_hz
        track.prf_hz = measurement.prf_hz
        track.modulation_code = measurement.modulation_code
        track.quality = measurement.quality
        track.last_seen = measurement.observed_at

    def serialize(self) -> list[dict]:
        return [asdict(track) for track in sorted(
            self._tracks.values(), key=lambda track: track.track_key)]

    def restore(self, rows: list[dict], track_seq: int, now: float) -> None:
        if (type(track_seq) is not int or not 0 <= track_seq <= 2**63 - 1
                or not isinstance(rows, list) or len(rows) > self.maximum):
            raise ValueError("invalid ESM picture")
        fields = set(ESMTrack.__dataclass_fields__)
        restored = {}
        previous = None
        for row in rows:
            if not isinstance(row, dict) or set(row) != fields:
                raise ValueError("invalid ESM track fields")
            track = ESMTrack(**row)
            _validate_track(track, now, track_seq)
            if track.track_key in restored or (previous is not None
                                                and track.track_key <= previous):
                raise ValueError("duplicate or unsorted ESM track")
            restored[track.track_key] = track
            previous = track.track_key
        self.track_seq = track_seq
        self._tracks = restored


def _signed_angle_difference(first: float, second: float) -> float:
    return (first - second + 180.0) % 360.0 - 180.0


def rank_emitters(track: ESMTrack, emitters: Mapping[str, object],
                  maximum: int = 5) -> tuple[ESMCandidate, ...]:
    """Rank catalog hypotheses using measured fingerprint fields only."""
    ranked = []
    for emitter_key in sorted(emitters):
        emitter = emitters[emitter_key]
        if getattr(emitter, "domain", None) != "radar":
            continue
        frequency = _band_score(track.frequency_hz, emitter.frequency_band_hz)
        prf = (_band_score(track.prf_hz, emitter.prf_band_hz)
               if track.prf_hz is not None and emitter.prf_band_hz is not None
               else 0.5)
        modulation = (1.0 if track.modulation_code in emitter.modulation_codes
                      else (0.5 if track.modulation_code == "unknown" else 0.0))
        score = max(0.0, min(1.0, frequency * .45 + prf * .35
                             + modulation * .20))
        ranked.append(ESMCandidate(emitter_key, score))
    return tuple(sorted(ranked, key=lambda item: (-item.score, item.emitter_key))[
                 :max(0, int(maximum))])


def _band_score(value: float, band) -> float:
    low, high = band
    if low <= value <= high:
        return 1.0
    width = max(1.0, high - low)
    distance = low - value if value < low else value - high
    return max(0.0, 1.0 - distance / width)


def correlate_observations(track: ESMTrack, evidence,
                           now: float) -> tuple[ESMCorrelation, ...]:
    """Return plausible public-track correlations without reading target IDs."""
    matches = []
    for item in evidence:
        if not 0.0 <= item.observed_at <= now:
            continue
        elapsed = abs(track.last_seen - item.observed_at)
        if elapsed > 15.0 or now - item.observed_at > 30.0:
            continue
        bearing = item.bearing
        if item.x is not None and item.y is not None:
            bearing = math.degrees(math.atan2(
                item.x - track.observer_x, -(item.y - track.observer_y))) % 360.0
        uncertainty = item.bearing_uncertainty_deg
        combined = math.hypot(track.bearing_uncertainty_deg,
                              2.0 if uncertainty is None else uncertainty)
        gate = max(4.0, combined * 3.0)
        delta = _angle_difference(track.bearing, bearing)
        if delta > gate:
            continue
        score = max(0.0, 1.0 - .7 * delta / gate - .3 * elapsed / 15.0)
        matches.append((item, score))
    matches.sort(key=lambda pair: (-pair[1], pair[0].source, pair[0].track_id))
    ambiguous = len(matches) > 1 and matches[0][1] - matches[1][1] < .1
    return tuple(ESMCorrelation(item.track_id, item.source, score,
                                ambiguous and index < 2)
                 for index, (item, score) in enumerate(matches))


def valid_esm_state(state, now: float, emitters: Mapping[str, object]) -> bool:
    """Validate the exact ESM envelope in the canonical save schema."""
    if not isinstance(state, dict) or set(state) != {
            "version", "track_seq", "picture", "selected_track_key", "annotations"}:
        return False
    if type(state["version"]) is not int or state["version"] != ESM_STATE_VERSION:
        return False
    track_seq = state["track_seq"]
    if type(track_seq) is not int or not 0 <= track_seq <= 2**63 - 1:
        return False
    picture = ESMPicture()
    try:
        picture.restore(state["picture"], track_seq, now)
    except (TypeError, ValueError, OverflowError):
        return False
    selected = state["selected_track_key"]
    if selected is not None and selected not in picture._tracks:
        return False
    annotations = state["annotations"]
    if not isinstance(annotations, list) or len(annotations) > ESM_MAX_ANNOTATIONS:
        return False
    previous = None
    for row in annotations:
        if not isinstance(row, dict) or set(row) != {"track_key", "emitter_key"}:
            return False
        track_key, emitter_key = row["track_key"], row["emitter_key"]
        sequence = _track_sequence(track_key)
        emitter = emitters.get(emitter_key) if isinstance(emitter_key, str) else None
        if (sequence is None or sequence > track_seq
                or (previous is not None and track_key <= previous)
                or emitter is None or getattr(emitter, "domain", None) != "radar"):
            return False
        previous = track_key
    return True


def _validate_measurement(measurement: ESMMeasurement, now: float) -> None:
    if not isinstance(measurement, ESMMeasurement):
        raise ValueError("invalid ESM measurement")
    values = (measurement.observer_x, measurement.observer_y,
              measurement.bearing, measurement.bearing_uncertainty_deg,
              measurement.frequency_hz, measurement.quality,
              measurement.observed_at)
    if any(not _finite_number(value) for value in values):
        raise ValueError("non-finite ESM measurement")
    if (not -1_000_000.0 <= measurement.observer_x <= 1_000_000.0
            or not -1_000_000.0 <= measurement.observer_y <= 1_000_000.0
            or not 0.0 <= measurement.bearing < 360.0
            or not .05 <= measurement.bearing_uncertainty_deg <= 180.0
            or not 1.0 <= measurement.frequency_hz <= 1e12
            or not 0.0 <= measurement.quality <= 1.0
            or not 0.0 <= measurement.observed_at <= now
            or measurement.modulation_code not in ESM_MODULATIONS
            or (measurement.prf_hz is not None and (
                not _finite_number(measurement.prf_hz)
                or not 1.0 <= measurement.prf_hz <= 1e7))):
        raise ValueError("out-of-range ESM measurement")


def _validate_track(track: ESMTrack, now: float, track_seq: int) -> None:
    sequence = _track_sequence(track.track_key)
    measurement = ESMMeasurement(
        observer_x=track.observer_x, observer_y=track.observer_y,
        bearing=track.bearing,
        bearing_uncertainty_deg=track.bearing_uncertainty_deg,
        frequency_hz=track.frequency_hz, prf_hz=track.prf_hz,
        modulation_code=track.modulation_code, quality=track.quality,
        observed_at=track.last_seen)
    _validate_measurement(measurement, now)
    if (sequence is None or sequence > track_seq
            or not _finite_number(track.first_seen)
            or not 0.0 <= track.first_seen <= track.last_seen):
        raise ValueError("invalid ESM track")


def _track_sequence(track_key) -> int | None:
    if not isinstance(track_key, str) or ESM_TRACK_KEY_RE.fullmatch(track_key) is None:
        return None
    sequence = int(track_key[1:], 16)
    return sequence if sequence > 0 else None


def _finite_number(value) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))
