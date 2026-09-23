"""Reusable synthetic hydroacoustic synthesis, channel, and PCM analysis.

These routines are deterministic game/audio models.  They are not measured
signatures, calibrated propagation, or physically accurate ocean acoustics.
They deliberately own no target identity and the analyzers inspect PCM only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import NamedTuple, Sequence

import numpy as np
from numpy.typing import NDArray


FloatArray = NDArray[np.float32]
Float64Array = NDArray[np.float64]
TAU = 2.0 * math.pi
DEFAULT_SAMPLE_RATE = 32_768
MAX_SAMPLE_RATE = 192_000
MAX_FRAME_SAMPLES = 262_144
MAX_ANALYSIS_SAMPLES = 4_194_304

_ENGINE_HARMONICS: dict[str, tuple[tuple[float, float], ...]] = {
    "diesel": ((1.0, .48), (2.0, .24), (3.0, .12), (6.0, .06)),
    "electric": ((1.0, .22), (2.0, .08), (12.0, .05)),
    "turbine": ((4.0, .18), (8.0, .10), (16.0, .06)),
}


def _number(name: str, value: object, low: float, high: float) -> float:
    if (not isinstance(value, (int, float)) or isinstance(value, bool)
            or not math.isfinite(value)):
        raise ValueError(f"{name} must be a finite number")
    result = float(value)
    if not low <= result <= high:
        raise ValueError(f"{name} is outside the supported range")
    return result


def _integer(name: str, value: object, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer from {low} to {high}")
    return value


def _pcm(samples: object) -> Float64Array:
    data = np.asarray(samples)
    if data.ndim != 1 or data.size < 32 or data.size > MAX_ANALYSIS_SAMPLES:
        raise ValueError("samples must be bounded mono PCM")
    if data.dtype.kind not in "fiu" or not np.isfinite(data).all():
        raise ValueError("samples must contain finite numeric PCM")
    return np.asarray(data, dtype=np.float64)


def _sample_rate(value: object, *, minimum: int = 64) -> int:
    return _integer("sample_rate", value, minimum, MAX_SAMPLE_RATE)


def analytic_envelope(samples: object, sample_rate: int, low_hz: float,
                      high_hz: float) -> FloatArray:
    """Return the FFT analytic envelope of finite mono PCM in one carrier band."""
    data = _pcm(samples)
    rate = _sample_rate(sample_rate)
    low = _number("low_hz", low_hz, 0.0, rate / 2.0)
    high = _number("high_hz", high_hz, 0.0, rate / 2.0)
    if not low < high:
        raise ValueError("carrier band must have positive width")
    frequencies = np.fft.fftfreq(data.size, 1.0 / rate)
    spectrum = np.fft.fft(data - data.mean())
    spectrum *= 2.0 * ((frequencies >= low) & (frequencies <= high))
    return np.abs(np.fft.ifft(spectrum)).astype(np.float32)


class AcousticSignature:
    """Stateful, click-free procedural vessel source with a private RNG.

    RPM and gain changes converge with 50 ms exponential smoothing.  Shaft,
    blade-rate, and broadband carrier phases are explicit and wrapped modulo
    ``2*pi``.  Cavitation uses a persistent two-stage one-pole bandpass.
    """

    def __init__(self, *, sample_rate: int = DEFAULT_SAMPLE_RATE,
                 frame_size: int = 2048, rpm: float = 120.0, blades: int = 7,
                 engine_type: str = "diesel",
                 harmonics: Sequence[tuple[float, float]] | None = None,
                 cavitation_band_hz: tuple[float, float] = (2_000.0, 10_000.0),
                 cavitation: float = .25, gain: float = .2,
                 seed: int = 0) -> None:
        self.sample_rate = _sample_rate(sample_rate, minimum=32_768)
        self.frame_size = _integer("frame_size", frame_size, 32, MAX_FRAME_SAMPLES)
        self.blades = _integer("blades", blades, 1, 16)
        if harmonics is None:
            if engine_type not in _ENGINE_HARMONICS:
                raise ValueError("unsupported engine_type")
            selected = _ENGINE_HARMONICS[engine_type]
        else:
            if isinstance(harmonics, (str, bytes)) or not 1 <= len(harmonics) <= 32:
                raise ValueError("harmonics must contain 1..32 pairs")
            selected = tuple((_number("harmonic multiplier", pair[0], .1, 128.0),
                              _number("harmonic gain", pair[1], 0.0, 1.0))
                             for pair in harmonics
                             if isinstance(pair, (tuple, list)) and len(pair) == 2)
            if len(selected) != len(harmonics):
                raise ValueError("harmonics must contain numeric pairs")
        low, high = cavitation_band_hz
        self.cavitation_band_hz = (
            _number("cavitation low", low, 1.0, self.sample_rate / 2.0 - 1.0),
            _number("cavitation high", high, 1.0, self.sample_rate / 2.0 - 1.0),
        )
        if self.cavitation_band_hz[0] >= self.cavitation_band_hz[1]:
            raise ValueError("cavitation band must have positive width")
        self.harmonics = tuple(selected)
        self.engine_type = engine_type
        self.target_rpm = self.rpm = _number("rpm", rpm, 0.0, 3_600.0)
        self.target_gain = self.gain = _number("gain", gain, 0.0, 1.0)
        self.cavitation = _number("cavitation", cavitation, 0.0, 1.0)
        self.shaft_phase = 0.0
        self.blade_phase = 0.0
        self.harmonic_phases = [multiplier * .17 % TAU
                                for multiplier, _ in self.harmonics]
        self.carrier_phase = 0.0
        self._low_state = 0.0
        self._high_state = 0.0
        self._rng = np.random.default_rng(_integer("seed", seed, 0, 2**63 - 1))
        self._smooth = 1.0 - math.exp(-1.0 / (.05 * self.sample_rate))

    def set_operating_point(self, *, rpm: float | None = None,
                            gain: float | None = None) -> None:
        """Set bounded targets; transitions occur during subsequent rendering."""
        if rpm is not None:
            self.target_rpm = _number("rpm", rpm, 0.0, 3_600.0)
        if gain is not None:
            self.target_gain = _number("gain", gain, 0.0, 1.0)

    @staticmethod
    def _one_pole(data: Float64Array, coefficient: float,
                  state: float) -> tuple[Float64Array, float]:
        output = np.empty_like(data)
        for index, value in enumerate(data):
            state += coefficient * (float(value) - state)
            output[index] = state
        return output, state

    def render_frame(self, frame_size: int | None = None, *,
                     rpm: float | None = None,
                     gain: float | None = None) -> FloatArray:
        """Render one fixed mono float32 frame and advance streaming state."""
        count = self.frame_size if frame_size is None else _integer(
            "frame_size", frame_size, 32, MAX_FRAME_SAMPLES)
        self.set_operating_point(rpm=rpm, gain=gain)
        indices = np.arange(1, count + 1, dtype=np.float64)
        decay = np.power(1.0 - self._smooth, indices)
        rpms = self.target_rpm + (self.rpm - self.target_rpm) * decay
        gains = self.target_gain + (self.gain - self.target_gain) * decay
        shaft_steps = TAU * rpms / (60.0 * self.sample_rate)
        shaft = self.shaft_phase + np.cumsum(shaft_steps) - shaft_steps
        blade_steps = shaft_steps * self.blades
        blade = self.blade_phase + np.cumsum(blade_steps) - blade_steps
        carrier_hz = min(self.sample_rate * .22, 4_000.0)
        carrier_step = TAU * carrier_hz / self.sample_rate
        carrier = self.carrier_phase + carrier_step * np.arange(count)

        signal = .34 * np.sin(blade) + .10 * np.sin(shaft + .31)
        next_harmonic_phases = []
        for harmonic_index, (multiplier, amplitude) in enumerate(self.harmonics):
            harmonic_steps = multiplier * shaft_steps
            harmonic = (self.harmonic_phases[harmonic_index]
                        + np.cumsum(harmonic_steps) - harmonic_steps)
            # Fade before Nyquist rather than switching a moving partial abruptly.
            nyquist_fade = np.clip(
                (math.pi - harmonic_steps) / (math.pi * .05), 0.0, 1.0)
            signal += amplitude * np.sin(harmonic) * nyquist_fade
            next_harmonic_phases.append(float(
                (self.harmonic_phases[harmonic_index] + harmonic_steps.sum()) % TAU))
        raw = self._rng.normal(0.0, 1.0, count)
        high_alpha = 1.0 - math.exp(-TAU * self.cavitation_band_hz[1]
                                    / self.sample_rate)
        low_alpha = 1.0 - math.exp(-TAU * self.cavitation_band_hz[0]
                                   / self.sample_rate)
        upper, self._high_state = self._one_pole(raw, high_alpha, self._high_state)
        lower, self._low_state = self._one_pole(raw, low_alpha, self._low_state)
        bursts = .35 + .65 * np.maximum(0.0, np.sin(blade - .8)) ** 2
        signal += self.cavitation * (upper - lower) * bursts * (
            .8 + .2 * np.sin(carrier))
        self.rpm, self.gain = float(rpms[-1]), float(gains[-1])
        self.shaft_phase = float((self.shaft_phase + shaft_steps.sum()) % TAU)
        self.blade_phase = float((self.blade_phase + blade_steps.sum()) % TAU)
        self.harmonic_phases = next_harmonic_phases
        self.carrier_phase = float((self.carrier_phase + carrier_step * count) % TAU)
        return np.clip(signal * gains * .42, -1.0, 1.0).astype(np.float32)

    def update(self, frame_size: int | None = None, *, rpm: float | None = None,
               gain: float | None = None) -> FloatArray:
        """Alias for :meth:`render_frame` for frame-driven callers."""
        return self.render_frame(frame_size, rpm=rpm, gain=gain)


class HydroacousticChannel:
    """Stateful synthetic range/depth channel with smooth gain and low-pass.

    Spherical game spreading and frequency-dependent distance absorption are
    represented by amplitude and a four-pole low-pass.  Crossing opposite
    sides of the thermocline adds exactly 25 dB attenuation.  Filter and gain
    state persist, and changing geometry interpolates coefficients per sample.
    """

    def __init__(self, *, sample_rate: int = DEFAULT_SAMPLE_RATE,
                 distance_m: float = 1_000.0, source_depth_m: float = 20.0,
                 receiver_depth_m: float = 20.0,
                 thermocline_depth_m: float = 50.0) -> None:
        self.sample_rate = _sample_rate(sample_rate, minimum=32_768)
        self.distance_m = _number("distance_m", distance_m, 0.0, 1_000_000.0)
        self.source_depth_m = _number("source_depth_m", source_depth_m, 0.0, 12_000.0)
        self.receiver_depth_m = _number("receiver_depth_m", receiver_depth_m, 0.0, 12_000.0)
        self.thermocline_depth_m = _number(
            "thermocline_depth_m", thermocline_depth_m, 0.0, 12_000.0)
        self._gain = self._target_gain()
        self._cutoff = self._target_cutoff()
        self._filter_state = np.zeros(4, dtype=np.float64)

    def set_geometry(self, *, distance_m: float | None = None,
                     source_depth_m: float | None = None,
                     receiver_depth_m: float | None = None,
                     thermocline_depth_m: float | None = None) -> None:
        if distance_m is not None:
            self.distance_m = _number("distance_m", distance_m, 0.0, 1_000_000.0)
        if source_depth_m is not None:
            self.source_depth_m = _number("source_depth_m", source_depth_m, 0.0, 12_000.0)
        if receiver_depth_m is not None:
            self.receiver_depth_m = _number("receiver_depth_m", receiver_depth_m, 0.0, 12_000.0)
        if thermocline_depth_m is not None:
            self.thermocline_depth_m = _number(
                "thermocline_depth_m", thermocline_depth_m, 0.0, 12_000.0)

    def _target_gain(self) -> float:
        return 10.0 ** (-self.transmission_loss_db() / 20.0)

    def transmission_loss_db(self) -> float:
        """Return synthetic meter-based TL for the current geometry."""
        spreading_db = 20.0 * math.log10(max(1.0, self.distance_m))
        absorption_db = .0004 * self.distance_m
        cross_layer = ((self.source_depth_m < self.thermocline_depth_m)
                       != (self.receiver_depth_m < self.thermocline_depth_m))
        return spreading_db + absorption_db + (25.0 if cross_layer else 0.0)

    def _target_cutoff(self) -> float:
        return max(180.0, min(self.sample_rate * .45,
                              12_000.0 / (1.0 + self.distance_m / 2_500.0)))

    def process_frame(self, samples: object, *, distance_m: float | None = None,
                      source_depth_m: float | None = None,
                      receiver_depth_m: float | None = None,
                      thermocline_depth_m: float | None = None) -> FloatArray:
        data = _pcm(samples)
        if data.size > MAX_FRAME_SAMPLES:
            raise ValueError("frame exceeds channel bound")
        self.set_geometry(distance_m=distance_m, source_depth_m=source_depth_m,
                          receiver_depth_m=receiver_depth_m,
                          thermocline_depth_m=thermocline_depth_m)
        count = data.size
        target_gain, target_cutoff = self._target_gain(), self._target_cutoff()
        indices = np.arange(1, count + 1, dtype=np.float64)
        smoothing = 1.0 - math.exp(-1.0 / (.05 * self.sample_rate))
        decay = np.power(1.0 - smoothing, indices)
        gains = target_gain + (self._gain - target_gain) * decay
        cutoffs = target_cutoff + (self._cutoff - target_cutoff) * decay
        output = np.empty(count, dtype=np.float64)
        states = self._filter_state
        for index, value in enumerate(data):
            coefficient = 1.0 - math.exp(-TAU * float(cutoffs[index]) / self.sample_rate)
            filtered = float(value)
            for pole in range(states.size):
                states[pole] += coefficient * (filtered - states[pole])
                filtered = states[pole]
            output[index] = filtered * gains[index]
        self._gain, self._cutoff = float(gains[-1]), float(cutoffs[-1])
        return np.clip(output, -1.0, 1.0).astype(np.float32)

    def update(self, samples: object, *, distance_m: float | None = None,
               source_depth_m: float | None = None,
               receiver_depth_m: float | None = None,
               thermocline_depth_m: float | None = None) -> FloatArray:
        """Alias for :meth:`process_frame` for frame-driven callers."""
        return self.process_frame(
            samples, distance_m=distance_m, source_depth_m=source_depth_m,
            receiver_depth_m=receiver_depth_m,
            thermocline_depth_m=thermocline_depth_m)


@dataclass(frozen=True, slots=True)
class LOFARResult:
    frequencies_hz: FloatArray
    times_s: FloatArray
    magnitude: FloatArray


class DEMONHypothesis(NamedTuple):
    blade_count: int
    harmonic_order: int
    rpm: float


@dataclass(frozen=True, slots=True)
class DEMONResult:
    frequencies_hz: FloatArray
    magnitude: FloatArray
    modulation_peak_hz: float | None
    hypotheses: tuple[DEMONHypothesis, ...]
    detection_confidence: float

    @property
    def blade_rate_hz(self) -> float | None:
        """Compatibility alias; the measured peak is not an identified blade rate."""
        return self.modulation_peak_hz

    @property
    def rpm_hypotheses(self) -> tuple[tuple[int, float], ...]:
        """Compatibility view of first-order blade-count assumptions."""
        return tuple((item.blade_count, item.rpm) for item in self.hypotheses
                     if item.harmonic_order == 1)

    @property
    def confidence(self) -> float:
        """Compatibility alias for peak detection, not identity confidence."""
        return self.detection_confidence


def analyze_lofar(samples: object, sample_rate: int, *,
                  fft_size: int = 4096) -> LOFARResult:
    """Bounded Hann STFT from 0..1000 Hz with fixed 75 percent overlap."""
    data = _pcm(samples)
    rate = _sample_rate(sample_rate)
    size = _integer("fft_size", fft_size, 128, 65_536)
    if size > data.size or size & (size - 1):
        raise ValueError("fft_size must be a power of two no larger than PCM")
    hop = size // 4
    starts = np.arange(0, data.size - size + 1, hop)
    window = np.hanning(size)
    bins = np.fft.rfftfreq(size, 1.0 / rate)
    keep = bins <= min(1_000.0, rate / 2.0)
    spectra = np.empty((starts.size, int(keep.sum())), dtype=np.float32)
    scale = 2.0 / window.sum()
    for row, start in enumerate(starts):
        frame = data[start:start + size]
        spectra[row] = (np.abs(np.fft.rfft((frame - frame.mean()) * window))[keep]
                        * scale).astype(np.float32)
    return LOFARResult(bins[keep].astype(np.float32),
                       ((starts + size / 2) / rate).astype(np.float32), spectra)


def analyze_demon(samples: object, sample_rate: int, *,
                  carrier_band_hz: tuple[float, float] = (2_000.0, 10_000.0),
                  max_modulation_hz: float = 80.0,
                  blade_counts: Sequence[int] = (3, 4, 5, 6, 7)) -> DEMONResult:
    """Analyze PCM envelope modulation and publish blade-count RPM hypotheses."""
    data = _pcm(samples)
    rate = _sample_rate(sample_rate)
    maximum = _number("max_modulation_hz", max_modulation_hz, 1.0, 80.0)
    counts = tuple(_integer("blade count", count, 1, 16) for count in blade_counts)
    if not counts or len(counts) > 16 or len(set(counts)) != len(counts):
        raise ValueError("blade_counts must be 1..16 distinct assumptions")
    envelope = np.asarray(analytic_envelope(data, rate, *carrier_band_hz),
                          dtype=np.float64)
    envelope -= envelope.mean()
    window = np.hanning(envelope.size)
    frequencies = np.fft.rfftfreq(envelope.size, 1.0 / rate)
    magnitude = np.abs(np.fft.rfft(envelope * window)) * (2.0 / window.sum())
    keep = frequencies <= maximum
    shown_freq = frequencies[keep]
    shown = magnitude[keep]
    search = (shown_freq >= 1.0) & (shown_freq <= maximum)
    modulation_peak: float | None = None
    confidence = 0.0
    if np.any(search):
        band = shown[search]
        index = int(np.argmax(band))
        peak = float(band[index])
        floor = float(np.median(band))
        concentration = peak * peak / (float(np.sum(band * band)) + 1e-24)
        carrier_rms = float(np.sqrt(np.mean(envelope * envelope)))
        prominence = peak / (floor + 1e-12)
        if carrier_rms >= 1e-5 and prominence >= 6.0 and concentration >= .08:
            modulation_peak = float(shown_freq[search][index])
            confidence = float(np.clip((prominence - 6.0) / 12.0, 0.0, 1.0)
                               * np.clip(concentration / .4, 0.0, 1.0))
    hypotheses = (() if modulation_peak is None else tuple(
        DEMONHypothesis(count, order,
                        round(modulation_peak * 60.0 / (count * order), 2))
        for count in counts for order in range(1, 5)))
    return DEMONResult(shown_freq.astype(np.float32), shown.astype(np.float32),
                       modulation_peak, hypotheses, confidence)


# Conventional mixed-case aliases keep the result names ergonomic in Python.
LofarResult = LOFARResult
DemonResult = DEMONResult

__all__ = [
    "AcousticSignature", "HydroacousticChannel", "LOFARResult", "DEMONResult",
    "DEMONHypothesis",
    "LofarResult", "DemonResult", "analytic_envelope", "analyze_lofar",
    "analyze_demon",
]
