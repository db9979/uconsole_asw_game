"""Bounded passive ESM observations without entity identity."""

from __future__ import annotations

import heapq
import hashlib
import math
import re
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Mapping


ESM_STATE_VERSION = 3
ESM_MAX_TRACKS = 64
ESM_MAX_ANNOTATIONS = 256
# Operator memory deliberately outlives intermittent radar duty cycles (mast
# radars can remain silent for 54 s). Quality still decays continuously.
ESM_STALE_S = 300.0
ESM_ASSOCIATION_MAX_GAP_S = 90.0
ESM_CONFIRMATION_S = 1.0
ECM_SIGNAL_FRESH_S = 2.0
ECM_AUTO_RELEASE_S = 10.0
ESM_TRACK_KEY_RE = re.compile(r"E[0-9a-f]{16}")
ESM_MODULATIONS = frozenset((
    "continuous_wave", "frequency_agile", "pulse", "pulse_doppler", "unknown",
))
ESM_FREQUENCY_MIN_HZ = 500e6
ESM_FREQUENCY_MAX_HZ = 40e9
ESM_DF_SENSOR_COUNT = 4
ESM_BROADBAND_SENSOR_COUNT = 1


class SpectrumBand(str, Enum):
    A_C = "a_c"
    D = "d"
    E_F = "e_f"
    G_H = "g_h"
    I_J = "i_j"
    K = "k"


def spectrum_band(frequency_hz: float) -> SpectrumBand:
    """Return the operator-facing EW band for one measured frequency."""
    if not _finite_number(frequency_hz) or not 0.0 <= frequency_hz <= 40e9:
        raise ValueError("frequency outside supported spectrum")
    if frequency_hz < 1e9:
        return SpectrumBand.A_C
    if frequency_hz < 2e9:
        return SpectrumBand.D
    if frequency_hz < 4e9:
        return SpectrumBand.E_F
    if frequency_hz < 8e9:
        return SpectrumBand.G_H
    if frequency_hz < 20e9:
        return SpectrumBand.I_J
    return SpectrumBand.K


class SignalType(str, Enum):
    NAVIGATION = "navigation"
    SURFACE_SEARCH = "surface_search"
    AIR_SEARCH = "air_search"
    MULTI_FUNCTION = "multi_function"
    FIRE_CONTROL = "fire_control"
    MISSILE_SEEKER = "missile_seeker"


THREAT_LEVELS = {
    SignalType.NAVIGATION: "low",
    SignalType.SURFACE_SEARCH: "low",
    SignalType.AIR_SEARCH: "medium",
    SignalType.MULTI_FUNCTION: "medium",
    SignalType.FIRE_CONTROL: "high",
    SignalType.MISSILE_SEEKER: "critical",
}
POWER_CLASS_RANGE_NM = {"low": 60.0, "medium": 100.0, "high": 150.0}
# Rotating search antennas illuminate the ESM mast only when their main beam
# passes (one-way level 20 log10(R_class / R)); between passes only the
# side lobes reach it.  Tracking/fire-control and seeker radars point at
# their target.  Periods are generic rotation rates per radar role.
ANTENNA_SCAN_PERIOD_S = {"navigation": 2.5, "surface_search": 2.5,
                         "air_search": 5.0, "multi_function": 2.0}
MAIN_BEAM_WIDTH_DEG = 2.0
SIDELOBE_DB = -25.0
ESM_DWELL_S = 0.5
ESM_LEVEL_NOISE_DB = 2.0
ESM_SIGNAL_DB_RANGE = (-60.0, 200.0)
ESM_LIVE_SCAN_CAP_S = 7.5
THREAT_ORDER = {"unknown": 0, "low": 1, "medium": 2, "high": 3,
                "critical": 4}
ESM_STATUS_FILTERS = ("OPERATIONAL", "LIVE", "MEMORY", "ALL")
ESM_THREAT_FILTERS = ("ALL", "LOW", "MEDIUM", "HIGH", "CRITICAL")
ESM_BAND_FILTERS = ("ALL", "A_C", "D", "E_F", "G_H", "I_J", "K")


@dataclass(frozen=True, slots=True)
class RadarSignal:
    """Internal emission.  Instances must never enter a public projection."""

    signal_id: str
    emitter_key: str
    frequency_hz: float
    prf_hz: float | None
    modulation_code: str
    operating_mode: str
    signal_type: SignalType
    x: float
    y: float
    power_class: str
    emitted_at: float
    synthetic_assumption: bool = False

    @property
    def pri_s(self) -> float | None:
        return None if self.prf_hz is None else 1.0 / self.prf_hz


def _stable_u64(*parts: object) -> int:
    encoded = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.blake2b(
        encoded, digest_size=8, person=b"ujagd-esm").digest(), "big")


class RadarSuiteController:
    """Deterministic, simulation-time radar duty-cycle controller."""

    MAX_ACTIVE = 4

    def __init__(self, emitters, seed: int, *, synthetic_assumption=False):
        self.emitters = tuple(sorted(emitters, key=lambda item: item.key))[:4]
        self.seed = int(seed)
        self.synthetic_assumption = bool(synthetic_assumption)

    def active_signals(self, now: float, x: float, y: float, *,
                       enabled: bool = True, emcon: bool = False,
                       fire_control: bool = False,
                       terminal: bool = False) -> tuple[RadarSignal, ...]:
        if not enabled or emcon or not math.isfinite(now) or now < 0.0:
            return ()
        signals = []
        for emitter in self.emitters:
            if self.synthetic_assumption and now == 0.0:
                continue
            role = SignalType(getattr(emitter, "radar_role", "surface_search"))
            if role is SignalType.FIRE_CONTROL and not fire_control:
                continue
            if role is SignalType.MISSILE_SEEKER and not terminal:
                continue
            period = float(getattr(emitter, "operating_period_s", 10.0))
            on_time = float(getattr(emitter, "on_duration_s", period))
            phase = (_stable_u64(self.seed, emitter.key, "phase") % 10_000_000
                     / 10_000_000.0 * period)
            window = math.floor((now + phase) / period)
            elapsed = (now + phase) % period
            # Initial publication gives every enabled suite one acquisition
            # sample; subsequent windows follow the seeded duty cycle.
            if (now > 0.0 or self.synthetic_assumption) and elapsed >= on_time:
                continue
            modulation = emitter.modulation_codes[
                _stable_u64(self.seed, emitter.key, window, "mod")
                % len(emitter.modulation_codes)]
            # A conventional radar keeps its carrier/PRF fingerprint across
            # duty-cycle silence. Only an explicitly frequency-agile waveform
            # hops between emission windows.
            fingerprint_window = (window if modulation == "frequency_agile"
                                  else "fixed")
            low, high = emitter.frequency_band_hz
            fraction = (_stable_u64(
                self.seed, emitter.key, fingerprint_window, "freq")
                        / float(2**64 - 1))
            frequency = low + (high - low) * fraction
            prf = None
            if emitter.prf_band_hz is not None:
                plow, phigh = emitter.prf_band_hz
                pf = (_stable_u64(
                    self.seed, emitter.key, fingerprint_window, "prf")
                      / float(2**64 - 1))
                prf = plow + (phigh - plow) * pf
            signal_id = "R" + hashlib.blake2b(
                f"{self.seed}:{emitter.key}".encode(), digest_size=8,
                person=b"ujagd-rd").hexdigest()
            signals.append(RadarSignal(
                signal_id, emitter.key, frequency, prf, modulation,
                getattr(emitter, "operating_mode", role.value), role,
                float(x), float(y), getattr(emitter, "power_class", "medium"),
                float(now), self.synthetic_assumption))
        return tuple(signals[:self.MAX_ACTIVE])


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
    synthetic_assumption: bool = False
    signal_db: float = 0.0


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
    synthetic_assumption: bool = False
    # Peak received level over the ESM sensitivity (dB) and the measured
    # interval between intercepts (antenna scan period, 0 until measured).
    signal_db: float = 0.0
    revisit_s: float = 0.0

    def age(self, now: float) -> float:
        return max(0.0, now - self.last_seen)

    def display_quality(self, now: float, stale_s: float = ESM_STALE_S) -> float:
        return max(0.0, self.quality * (1.0 - self.age(now) / stale_s))


def live_window_s(track: ESMTrack) -> float:
    """A scanning emitter is still live until one missed revolution."""
    return max(ECM_SIGNAL_FRESH_S,
               1.5 * min(track.revisit_s, ESM_LIVE_SCAN_CAP_S))


def estimated_range_nm(track: ESMTrack, power_class: str) -> float:
    """Range implied by the peak level for an assumed emitter power class."""
    reference = POWER_CLASS_RANGE_NM.get(power_class, POWER_CLASS_RANGE_NM["medium"])
    return reference * 10.0 ** (-track.signal_db / 20.0)


def signal_state(track: ESMTrack, now: float, threat_level: str) -> str:
    """Derive the operator state solely from retained observation data."""
    confirmed = (track.last_seen - track.first_seen >= ESM_CONFIRMATION_S
                 or threat_level in ("high", "critical"))
    if not confirmed:
        return "UNCONFIRMED"
    age = track.age(now)
    if age <= live_window_s(track):
        return "LIVE"
    if age <= ESM_ASSOCIATION_MAX_GAP_S:
        return "RECENT"
    return "MEMORY"


def track_is_operational(track: ESMTrack, now: float, threat_level: str, *,
                         annotated: bool = False, jamming: bool = False) -> bool:
    state = signal_state(track, now, threat_level)
    return (jamming or state in ("LIVE", "RECENT")
            or annotated or threat_level in ("high", "critical"))


def filter_and_sort_tracks(tracks, now: float, analyze, *,
                           status: str = "OPERATIONAL", minimum_threat: str = "ALL",
                           band: str = "ALL", annotated_keys=(), jamming_keys=()) -> tuple:
    """Shared ELOKA presentation policy; it never consults emitter truth."""
    if status not in ESM_STATUS_FILTERS:
        status = "OPERATIONAL"
    if minimum_threat not in ESM_THREAT_FILTERS:
        minimum_threat = "ALL"
    if band not in ESM_BAND_FILTERS:
        band = "ALL"
    annotated_keys, jamming_keys = set(annotated_keys), set(jamming_keys)
    minimum = -1 if minimum_threat == "ALL" else THREAT_ORDER[minimum_threat.lower()]
    rows = []
    state_order = {"LIVE": 0, "RECENT": 1, "MEMORY": 2, "UNCONFIRMED": 3}
    for track in tracks:
        analysis = analyze(track)
        threat = "unknown" if analysis is None else analysis.threat_level
        state = signal_state(track, now, threat)
        jammed = track.track_key in jamming_keys
        annotated = track.track_key in annotated_keys
        operational = track_is_operational(
            track, now, threat, annotated=annotated, jamming=jammed)
        if jammed:
            rows.append((track, threat, state, True))
            continue
        if status == "OPERATIONAL" and not operational:
            continue
        if status in ("LIVE", "MEMORY") and state != status:
            continue
        if THREAT_ORDER.get(threat, 0) < minimum:
            continue
        if band != "ALL" and spectrum_band(track.frequency_hz).name != band:
            continue
        rows.append((track, threat, state, jammed))
    rows.sort(key=lambda row: (
        not row[3], -THREAT_ORDER.get(row[1], 0), state_order[row[2]],
        -row[0].display_quality(now), row[0].age(now), row[0].track_key))
    return tuple(row[0] for row in rows)


@dataclass(frozen=True, slots=True)
class ESMCandidate:
    emitter_key: str
    score: float


@dataclass(frozen=True, slots=True)
class ESMAnalysis:
    radar_type: SignalType | None
    threat_level: str
    candidates: tuple[ESMCandidate, ...]
    ambiguous: bool


@dataclass(frozen=True, slots=True)
class ESMSignalFingerprint:
    """Normalized display samples derived exclusively from an ESM track."""

    waveform: tuple[float, ...]
    spectrum: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class ESMAnimatedSignal:
    """Simulation-time display samples derived only from an ESM track."""

    waveform: tuple[float, ...]
    spectrum: tuple[float, ...]
    intensity: float
    memory_hold: bool


def signal_fingerprint(track: ESMTrack, samples: int = 48,
                       bins: int = 40) -> ESMSignalFingerprint:
    """Build a bounded operator aid, not a reconstruction of hidden truth."""
    samples = max(16, min(96, int(samples)))
    bins = max(16, min(96, int(bins)))
    modulation = track.modulation_code
    prf = 500.0 if track.prf_hz is None else track.prf_hz
    pulse_count = max(3, min(12, round(2.0 + math.log10(max(1.0, prf)) * 2.0)))
    phase_seed = _stable_u64(
        round(track.frequency_hz / 1e6), round(prf), modulation)
    phase = (phase_seed % 10_000) / 10_000.0 * math.tau
    waveform = []
    for index in range(samples):
        t = index / max(1, samples - 1)
        if modulation == "continuous_wave":
            value = math.sin(math.tau * 5.0 * t + phase)
        elif modulation == "frequency_agile":
            step = min(7, int(t * 8.0))
            value = (-.75, .15, .7, -.25, .45, -.55, .85, 0.0)[
                (step + phase_seed) % 8]
        elif modulation in ("pulse", "pulse_doppler"):
            pulse_phase = (t * pulse_count) % 1.0
            envelope = max(0.0, 1.0 - pulse_phase / .16)
            if modulation == "pulse_doppler":
                envelope *= .65 + .35 * math.sin(
                    math.tau * pulse_count * 1.5 * t + phase)
            value = envelope * 2.0 - .85
        else:
            value = (.55 * math.sin(math.tau * 3.0 * t + phase)
                     + .25 * math.sin(math.tau * 11.0 * t + phase * .37))
        waveform.append(max(-1.0, min(1.0, value)))

    spectrum = []
    centers = ([.28, .5, .72] if modulation == "frequency_agile" else [.5])
    width = (.035 if modulation == "continuous_wave" else
             .09 if modulation in ("pulse_doppler", "frequency_agile") else .14)
    for index in range(bins):
        x = index / max(1, bins - 1)
        value = max(math.exp(-((x - center) / width) ** 2)
                    for center in centers)
        if modulation in ("pulse", "pulse_doppler"):
            value = max(value, .32 * math.exp(-((x - .5) / .32) ** 2)
                        * abs(math.cos((x - .5) * math.pi * pulse_count)))
        spectrum.append(max(0.0, min(1.0, value)))
    return ESMSignalFingerprint(tuple(waveform), tuple(spectrum))


def animated_signal_fingerprint(
        track: ESMTrack, now: float, *, technique: str | None = None,
        effectiveness: float = 0.0, samples: int = 48,
        bins: int = 40) -> ESMAnimatedSignal:
    """Animate an operator aid without wall time, FPS, or hidden truth."""
    base = signal_fingerprint(track, samples=samples, bins=bins)
    age = track.age(now)
    motion_time = min(now, track.last_seen + ECM_SIGNAL_FRESH_S)
    intensity = max(0.08, track.display_quality(now) / max(.001, track.quality))
    effectiveness = max(0.0, min(1.0, float(effectiveness)))
    prf = 500.0 if track.prf_hz is None else track.prf_hz
    rate = .35 + min(2.4, math.log10(max(1.0, prf)) * .38)
    if technique == ECMTechnique.VGPO.value:
        rate *= 1.0 + effectiveness * 1.8
    shift = int(math.floor(motion_time * rate * len(base.waveform)))
    if technique == ECMTechnique.RGPO.value:
        shift += int(math.floor(
            motion_time * effectiveness * len(base.waveform) * .22))
    shift %= len(base.waveform)
    waveform = list(base.waveform[shift:] + base.waveform[:shift])

    seed_phase = (_stable_u64(track.track_key, "display") % 10_000
                  / 10_000.0 * math.tau)
    if technique == ECMTechnique.NOISE.value:
        for index, value in enumerate(waveform):
            ripple = math.sin(index * 2.17 + motion_time * 11.0 + seed_phase)
            waveform[index] = max(-1.0, min(
                1.0, value * (1.0 - .45 * effectiveness)
                + ripple * .55 * effectiveness))
    elif technique == ECMTechnique.FALSE_TARGETS.value:
        delay = max(2, len(waveform) // 7)
        source = tuple(waveform)
        for index, value in enumerate(waveform):
            echo = source[(index - delay) % len(source)]
            waveform[index] = max(-1.0, min(
                1.0, value * (1.0 - .35 * effectiveness)
                + echo * .55 * effectiveness))

    spectrum = list(base.spectrum)
    if track.modulation_code == "frequency_agile":
        hop = int(_stable_u64(
            track.track_key, math.floor(motion_time * 2.0), "hop")
                  % max(1, len(spectrum) // 3)) - len(spectrum) // 6
        spectrum = spectrum[hop:] + spectrum[:hop] if hop else spectrum
    if technique == ECMTechnique.NOISE.value:
        for index, value in enumerate(spectrum):
            floor = (.28 + .08 * math.sin(index * .71 + motion_time * 5.0
                                           + seed_phase)) * effectiveness
            spectrum[index] = max(0.0, min(1.0, max(value, floor)))
    elif technique in (ECMTechnique.RGPO.value,
                        ECMTechnique.FALSE_TARGETS.value):
        offsets = ((-5, 6) if technique == ECMTechnique.FALSE_TARGETS.value
                   else (5,))
        source = tuple(spectrum)
        for offset in offsets:
            for index in range(len(spectrum)):
                spectrum[index] = max(
                    spectrum[index],
                    source[(index - offset) % len(source)]
                    * effectiveness * .65)

    waveform = tuple(value * intensity for value in waveform)
    spectrum = tuple(value * intensity for value in spectrum)
    return ESMAnimatedSignal(
        waveform, spectrum, intensity, age > ECM_SIGNAL_FRESH_S)


@dataclass(slots=True)
class ECMChannel:
    track_key: str
    tuned_frequency_hz: float
    requested_at: float
    last_frequency_hz: float
    effectiveness: float = 0.0
    automatic: bool = False
    technique: str = "noise"
    tuned_bearing_deg: float = 0.0
    power_draw: float = 0.0
    is_locked_on: bool = False


class ECMTechnique(str, Enum):
    NOISE = "noise"
    RGPO = "rgpo"
    VGPO = "vgpo"
    FALSE_TARGETS = "false_targets"


ECM_TECHNIQUES = tuple(item.value for item in ECMTechnique)


@dataclass(frozen=True, slots=True)
class ECMEffect:
    """Bounded seeker-facing result of active jamming."""

    effectiveness: float = 0.0
    technique: str | None = None
    range_error_nm: float = 0.0
    velocity_error_kn: float = 0.0
    false_targets: int = 0
    hoj_exposure: bool = False


class ECMJammer:
    """Four bounded directional jammers with a shared power budget."""

    MAX_CHANNELS = 4
    MAX_EFFECTIVENESS = .70
    REACTION_DELAY_S = 1.5e-6
    POWER_BUDGET = 1.0
    TECHNIQUE_POWER = {
        ECMTechnique.NOISE.value: .42,
        ECMTechnique.RGPO.value: .22,
        ECMTechnique.VGPO.value: .22,
        ECMTechnique.FALSE_TARGETS.value: .28,
    }

    def __init__(self):
        self.auto_enabled = False
        self.channels: list[ECMChannel] = []

    @staticmethod
    def recommended_technique(track: ESMTrack) -> str:
        if track.modulation_code == "frequency_agile":
            return ECMTechnique.NOISE.value
        if track.modulation_code == "pulse_doppler":
            return ECMTechnique.VGPO.value
        if track.modulation_code == "pulse":
            return ECMTechnique.RGPO.value
        return ECMTechnique.FALSE_TARGETS.value

    def deploy_jamming(self, track: ESMTrack, now: float, *, automatic=False,
                       technique: str | None = None):
        technique = technique or self.recommended_technique(track)
        if technique not in ECM_TECHNIQUES:
            return "invalid_technique"
        existing = next((item for item in self.channels
                         if item.track_key == track.track_key), None)
        if existing is not None:
            if not automatic:
                self.channels.remove(existing)
                return False
            return True
        if len(self.channels) >= self.MAX_CHANNELS:
            automatic_channel = next((item for item in reversed(self.channels)
                                      if item.automatic), None)
            if automatic_channel is None:
                return "channels_full"
            self.channels.remove(automatic_channel)
        self.channels.append(ECMChannel(
            track.track_key, track.frequency_hz, float(now), track.frequency_hz,
            automatic=bool(automatic), technique=technique,
            tuned_bearing_deg=track.bearing,
            power_draw=self.TECHNIQUE_POWER[technique]))
        return True

    def set_technique(self, track: ESMTrack, technique: str, now: float):
        if technique not in ECM_TECHNIQUES:
            return "invalid_technique"
        channel = next((item for item in self.channels
                        if item.track_key == track.track_key), None)
        if channel is None:
            return self.deploy_jamming(track, now, technique=technique)
        channel.technique = technique
        channel.power_draw = self.TECHNIQUE_POWER[technique]
        channel.requested_at = float(now)
        channel.effectiveness = 0.0
        channel.is_locked_on = False
        return True

    def update(self, tracks, now: float, *, operational=True) -> None:
        by_key = {track.track_key: track for track in tracks}
        retained = []
        demanded_power = sum(self.TECHNIQUE_POWER.get(
            channel.technique, self.POWER_BUDGET) for channel in self.channels)
        power_scale = min(1.0, self.POWER_BUDGET / max(.001, demanded_power))
        for channel in self.channels:
            track = by_key.get(channel.track_key)
            if track is None or not operational:
                continue
            age = track.age(now)
            if channel.automatic and age > ECM_AUTO_RELEASE_S:
                continue
            if age > ECM_SIGNAL_FRESH_S:
                channel.effectiveness = 0.0
                channel.is_locked_on = False
                retained.append(channel)
                continue
            delta = abs(track.frequency_hz - channel.tuned_frequency_hz)
            match = max(0.0, 1.0 - delta / max(50_000_000.0,
                                               track.frequency_hz * .05))
            reacted = now - channel.requested_at >= self.REACTION_DELAY_S
            agile_factor = (.82 if track.modulation_code == "frequency_agile"
                            and channel.technique == ECMTechnique.NOISE.value
                            else .62 if track.modulation_code == "frequency_agile"
                            else 1.0)
            channel.power_draw = self.TECHNIQUE_POWER[channel.technique]
            channel.effectiveness = (self.MAX_EFFECTIVENESS * match * agile_factor
                                     * power_scale * (1.0 if reacted else .35))
            channel.is_locked_on = reacted and match >= .5
            if reacted:
                channel.tuned_frequency_hz = track.frequency_hz
                channel.tuned_bearing_deg = track.bearing
            channel.last_frequency_hz = track.frequency_hz
            retained.append(channel)
        self.channels = retained[:self.MAX_CHANNELS]

    def effect_on(self, signal: RadarSignal, distance_nm: float, *,
                  line_of_sight=True, operational=True,
                  burn_through_nm=8.0) -> float:
        return self.effect_details_on(
            signal, distance_nm, line_of_sight=line_of_sight,
            operational=operational,
            burn_through_nm=burn_through_nm).effectiveness

    def effect_details_on(self, signal: RadarSignal, distance_nm: float, *,
                          line_of_sight=True, operational=True,
                          burn_through_nm=8.0) -> ECMEffect:
        if not operational or not line_of_sight or distance_nm < 0.0:
            return ECMEffect()
        best = ECMEffect()
        for channel in self.channels:
            delta = abs(signal.frequency_hz - channel.tuned_frequency_hz)
            match = max(0.0, 1.0 - delta / max(50_000_000.0,
                                               signal.frequency_hz * .05))
            distance_gain = min(1.0, distance_nm / max(.1, burn_through_nm))
            effectiveness = min(
                self.MAX_EFFECTIVENESS,
                channel.effectiveness * match * distance_gain)
            if effectiveness <= best.effectiveness:
                continue
            technique = channel.technique
            best = ECMEffect(
                effectiveness=effectiveness,
                technique=technique,
                range_error_nm=(distance_nm * .35 * effectiveness
                                if technique == ECMTechnique.RGPO.value else 0.0),
                velocity_error_kn=(900.0 * effectiveness
                                   if technique == ECMTechnique.VGPO.value else 0.0),
                false_targets=(max(1, round(5 * effectiveness))
                               if technique == ECMTechnique.FALSE_TARGETS.value else 0),
                hoj_exposure=technique == ECMTechnique.NOISE.value
                and effectiveness > 0.0)
        return best

    def serialize(self) -> dict:
        return {"auto_enabled": self.auto_enabled,
                "channels": [asdict(channel) for channel in self.channels]}

    def restore(self, state: dict, valid_track_keys: set[str],
                now: float) -> None:
        if not isinstance(state, dict) or set(state) != {"auto_enabled", "channels"}:
            raise ValueError("invalid ECM state")
        if type(state["auto_enabled"]) is not bool or not isinstance(state["channels"], list):
            raise ValueError("invalid ECM state")
        if len(state["channels"]) > self.MAX_CHANNELS:
            raise ValueError("too many ECM channels")
        fields = set(ECMChannel.__dataclass_fields__)
        channels = []
        keys = set()
        for row in state["channels"]:
            if not isinstance(row, dict) or set(row) != fields:
                raise ValueError("invalid ECM channel")
            channel = ECMChannel(**row)
            numbers = (channel.tuned_frequency_hz, channel.requested_at,
                       channel.last_frequency_hz, channel.effectiveness)
            if (channel.track_key not in valid_track_keys or channel.track_key in keys
                    or any(not _finite_number(value) for value in numbers)
                    or not ESM_FREQUENCY_MIN_HZ <= channel.tuned_frequency_hz <= ESM_FREQUENCY_MAX_HZ
                    or not ESM_FREQUENCY_MIN_HZ <= channel.last_frequency_hz <= ESM_FREQUENCY_MAX_HZ
                    or not 0.0 <= channel.requested_at <= now
                    or not 0.0 <= channel.effectiveness <= self.MAX_EFFECTIVENESS
                    or type(channel.automatic) is not bool
                    or channel.technique not in ECM_TECHNIQUES
                    or not 0.0 <= channel.tuned_bearing_deg < 360.0
                    or not _finite_number(channel.power_draw)
                    or channel.power_draw != self.TECHNIQUE_POWER[channel.technique]
                    or type(channel.is_locked_on) is not bool):
                raise ValueError("invalid ECM channel")
            channels.append(channel)
            keys.add(channel.track_key)
        self.auto_enabled = state["auto_enabled"]
        self.channels = channels


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
        -measurement.quality, -measurement.observed_at, measurement.bearing,
        measurement.bearing_uncertainty_deg, measurement.frequency_hz,
        -1.0 if measurement.prf_hz is None else measurement.prf_hz,
        measurement.modulation_code, measurement.observer_x,
        measurement.observer_y, measurement.quality,
    )


def _association_cost(track: ESMTrack, measurement: ESMMeasurement) -> float | None:
    elapsed = measurement.observed_at - track.last_seen
    if not 0.0 <= elapsed <= ESM_ASSOCIATION_MAX_GAP_S:
        return None
    uncertainty = math.hypot(track.bearing_uncertainty_deg,
                             measurement.bearing_uncertainty_deg)
    bearing_delta = _angle_difference(track.bearing, measurement.bearing)
    bearing_gate = max(4.0, uncertainty * 3.0)
    if bearing_delta > bearing_gate:
        return None
    agile = (track.modulation_code == "frequency_agile"
             or measurement.modulation_code == "frequency_agile")
    frequency_scale = max(500_000_000.0 if agile else 50_000_000.0,
                          track.frequency_hz * (0.75 if agile else 0.08))
    frequency_delta = abs(track.frequency_hz - measurement.frequency_hz)
    if frequency_delta > frequency_scale:
        return None
    if track.prf_hz is not None and measurement.prf_hz is not None:
        prf_scale = max(50.0, track.prf_hz * (0.75 if agile else 0.25))
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
            + prf_delta / prf_scale
            + elapsed / ESM_ASSOCIATION_MAX_GAP_S)


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

    def observe_batch(self, measurements, now: float, *, protected_keys=()) -> None:
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
            if len(self._tracks) >= self.maximum:
                protected = set(protected_keys)
                candidates = [track for track in self._tracks.values()
                              if track.track_key not in protected]
                if not candidates:
                    break
                evicted = min(candidates, key=lambda track: (
                    track.last_seen, track.quality, track.track_key))
                del self._tracks[evicted.track_key]
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
                synthetic_assumption=measurement.synthetic_assumption,
                signal_db=measurement.signal_db,
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
        gap = measurement.observed_at - track.last_seen
        if gap > 0.0:
            gap = min(gap, ESM_ASSOCIATION_MAX_GAP_S)
            track.revisit_s = (gap if track.revisit_s <= 0.0
                               else track.revisit_s + (gap - track.revisit_s) * alpha)
        # Peak-hold amplitude that relaxes slowly (side lobes read low).
        if measurement.signal_db >= track.signal_db:
            track.signal_db = measurement.signal_db
        else:
            track.signal_db += (measurement.signal_db - track.signal_db) * 0.05
        track.last_seen = measurement.observed_at
        track.synthetic_assumption = measurement.synthetic_assumption

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


def library_emitters(track: ESMTrack, emitters: Mapping[str, object],
                     maximum: int = 32) -> tuple[ESMCandidate, ...]:
    """Library lookup without ranking: radar emitters whose published
    frequency (and PRF, when measured) range contains the measurement.

    This is the range check an operator does in the emitter reference; the
    result carries no score and is ordered by key, never by likelihood.
    """
    found = []
    for emitter_key in sorted(emitters):
        emitter = emitters[emitter_key]
        if getattr(emitter, "domain", None) != "radar":
            continue
        low, high = emitter.frequency_band_hz
        if not low <= track.frequency_hz <= high:
            continue
        band = emitter.prf_band_hz
        if (track.prf_hz is not None and band is not None
                and not band[0] <= track.prf_hz <= band[1]):
            continue
        found.append(ESMCandidate(emitter_key, None))
        if len(found) >= maximum:
            break
    return tuple(found)


def _band_centre_fit(value: float, band) -> float:
    """1 at the band's centre, 0 at its edges (the value lies inside)."""
    low, high = band
    half = (high - low) / 2.0
    if half <= 0.0:
        return 1.0
    return max(0.0, 1.0 - abs(value - (low + half)) / half)


def library_fit(track: ESMTrack, emitter) -> float:
    """How well a library entry fits the measurement (0..1): frequency and
    PRF near the middle of the published ranges and the same modulation.
    The operator's own reading of the reference, not a likelihood."""
    frequency = _band_centre_fit(track.frequency_hz, emitter.frequency_band_hz)
    band = emitter.prf_band_hz
    prf = (_band_centre_fit(track.prf_hz, band)
           if track.prf_hz is not None and band is not None else 0.5)
    modulation = (0.5 if track.modulation_code == "unknown"
                  else 1.0 if track.modulation_code in emitter.modulation_codes else 0.0)
    return max(0.0, min(1.0, .4 * frequency + .3 * prf + .3 * modulation))


FIT_GRADES = ((0.75, "good"), (0.5, "fair"), (0.0, "poor"))


def fit_grade(fit: float) -> str:
    return next(grade for floor, grade in FIT_GRADES if fit >= floor)


def analyze_signal(track: ESMTrack, emitters: Mapping[str, object],
                   maximum: int = 5) -> ESMAnalysis:
    candidates = rank_emitters(track, emitters, maximum)
    best = emitters.get(candidates[0].emitter_key) if candidates else None
    role_value = getattr(best, "radar_role", None)
    try:
        radar_type = SignalType(role_value) if role_value is not None else None
    except ValueError:
        radar_type = None
    ambiguous = (len(candidates) > 1
                 and candidates[0].score - candidates[1].score < .10)
    return ESMAnalysis(radar_type, THREAT_LEVELS.get(radar_type, "unknown"),
                       candidates, ambiguous)


def antenna_main_beam_on(signal: RadarSignal, bearing_to_observer: float,
                         now: float, dwell_s: float) -> bool:
    """Did the emitter's main beam sweep the observer during the dwell?"""
    period = ANTENNA_SCAN_PERIOD_S.get(getattr(signal.signal_type, "value",
                                               signal.signal_type))
    if period is None:
        return True
    offset = _stable_u64(signal.signal_id, "azimuth") % 3600 / 10.0
    azimuth = (offset + now * 360.0 / period) % 360.0
    swept = 360.0 * dwell_s / period + MAIN_BEAM_WIDTH_DEG
    if swept >= 360.0:
        return True
    return (azimuth - bearing_to_observer + MAIN_BEAM_WIDTH_DEG / 2.0) % 360.0 < swept


def scan_for_signals(signals, *, observer_x: float, observer_y: float,
                     now: float, maximum_range_nm: float,
                     bearing_error_deg: float, noise_for,
                     line_of_sight=lambda _signal: True,
                     dwell_s: float = ESM_DWELL_S,
                     level_noise_for=None) -> tuple[ESMMeasurement, ...]:
    """Convert internal emissions to detached bearing-only ESM measurements.

    The one-way received level decides the intercept: main beam out to the
    power-class range, side lobes (-25 dB) only close in."""
    received = []
    for signal in signals:
        if not isinstance(signal, RadarSignal) or signal.emitted_at > now:
            continue
        distance = math.hypot(signal.x - observer_x, signal.y - observer_y)
        if distance > maximum_range_nm or not line_of_sight(signal):
            continue
        true_bearing = math.degrees(math.atan2(
            signal.x - observer_x, -(signal.y - observer_y))) % 360.0
        noise = max(-1.0, min(1.0, float(noise_for(signal))))
        effective_range = min(maximum_range_nm, POWER_CLASS_RANGE_NM.get(
            signal.power_class, POWER_CLASS_RANGE_NM["medium"]))
        level = 20.0 * math.log10(effective_range / max(distance, 1e-3))
        if not antenna_main_beam_on(signal, (true_bearing + 180.0) % 360.0,
                                    now, dwell_s):
            level += SIDELOBE_DB
        if level < 0.0:
            continue
        # Quality follows the received level (legacy 1 - .65 R/R_eff for the
        # main beam).
        quality = max(.05, min(1.0, 1.0 - .65 * 10.0 ** (-level / 20.0)))
        level_noise = (0.0 if level_noise_for is None
                       else max(-3.0, min(3.0, float(level_noise_for(signal)))))
        measured_level = max(ESM_SIGNAL_DB_RANGE[0], min(
            ESM_SIGNAL_DB_RANGE[1], level + level_noise * ESM_LEVEL_NOISE_DB))
        received.append(ESMMeasurement(
            observer_x, observer_y,
            (true_bearing + noise * bearing_error_deg) % 360.0,
            bearing_error_deg / math.sqrt(3.0), signal.frequency_hz,
            signal.prf_hz, signal.modulation_code, quality, signal.emitted_at,
            signal.synthetic_assumption, measured_level))
    return tuple(sorted(received, key=_measurement_sort_key)[:ESM_MAX_TRACKS])


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
            "version", "track_seq", "picture", "selected_track_key", "annotations",
            "ecm"}:
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
    try:
        ECMJammer().restore(state["ecm"], set(picture._tracks), now)
    except (TypeError, ValueError, OverflowError):
        return False
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
            or not ESM_FREQUENCY_MIN_HZ <= measurement.frequency_hz <= ESM_FREQUENCY_MAX_HZ
            or not 0.0 <= measurement.quality <= 1.0
            or not 0.0 <= measurement.observed_at <= now
            or measurement.modulation_code not in ESM_MODULATIONS
            or type(measurement.synthetic_assumption) is not bool
            or not _finite_number(measurement.signal_db)
            or not ESM_SIGNAL_DB_RANGE[0] <= measurement.signal_db <= ESM_SIGNAL_DB_RANGE[1]
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
        observed_at=track.last_seen,
        synthetic_assumption=track.synthetic_assumption,
        signal_db=track.signal_db)
    _validate_measurement(measurement, now)
    if (sequence is None or sequence > track_seq
            or not _finite_number(track.revisit_s)
            or not 0.0 <= track.revisit_s <= ESM_ASSOCIATION_MAX_GAP_S
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
