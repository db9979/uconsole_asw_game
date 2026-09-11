"""Synthetic beam audio and sample-derived spectra; no target classification.

The first line, if narrow and in 2..80 Hz, illustratively modulates a 700 Hz
carrier. This is NOT a measurement of true propeller blades. The same rule
applies to every source, and DEMON measures only the resulting mixed audio.

Broadband: sources may carry a "broadband" dict {level, low_hz, high_hz}
(target-internal band energy). Every source receives an independent,
seed-derived, replayable and block-continuous noise stream (the band limit is
applied with 50% overlap-add, so consecutive 250 ms blocks stay sample-
continuous at their boundary). Frequencies and levels are illustrative
synthesis parameters, not recordings or claims about real platform spectra.
"""

import math
from collections import OrderedDict, deque
from itertools import islice
from typing import NamedTuple

import numpy as np

from src.audio.hydroacoustics import analytic_envelope
from src.core import config

_BROADBAND_GAIN = 0.04      # rms-Skalierung der Bandrauschaudio
_OWN_CAV_GAIN = 0.10        # rms-Skalierung der Eigen-Kavitation
_OWN_CAV_LOW_HZ = 80.0
_OWN_CAV_HIGH_HZ = 380.0
OWN_NOISE_LOBE_WIDTH_DEG = 70.0


class RPMHypothesis(NamedTuple):
    blade_count: int
    harmonic_order: int
    rpm: float


def smooth_limit(samples, knee: float = 0.75,
                 ceiling: float = 0.98) -> np.ndarray:
    """Bound a signal with a transparent, monotonic rational soft knee.

    Values through ``knee`` are unchanged. Above it, the output approaches
    ``ceiling`` without reaching the +/-1 PCM rails. Non-finite input is
    converted deterministically before limiting.
    """
    if not (math.isfinite(knee) and math.isfinite(ceiling)
            and 0.0 <= knee < ceiling):
        raise ValueError("limiter requires 0 <= knee < ceiling")
    signal = np.nan_to_num(np.asarray(samples, dtype=np.float64), copy=True)
    magnitude = np.abs(signal)
    excess = np.maximum(0.0, magnitude - knee)
    span = ceiling - knee
    limited = np.where(magnitude <= knee, magnitude,
                       knee + span * (excess / (span + excess)))
    return np.copysign(limited, signal).astype(np.float32)


def _finite(value, default=0.0):
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return value if math.isfinite(value) else default


def directional_gain(bearing_deg: float, center_deg: float,
                     width_deg: float = OWN_NOISE_LOBE_WIDTH_DEG) -> float:
    """Gaussian amplitude gain used for displayed and simulated lobes."""
    delta = (center_deg - bearing_deg + 180.0) % 360.0 - 180.0
    gain = np.exp(-4.0 * math.log(2.0) * (delta / width_deg) ** 2)
    return float(gain) if np.ndim(gain) == 0 else gain


class AcousticReceiver:
    """4096 Hz mono receiver, advanced by exactly .25 s per update.

    Bearings are measured degrees; beam width is amplitude FWHM (1..360 deg).
    Levels, line amplitudes and own_noise are clamped to 0..1, sea_state to
    0..9, own_speed to 0..60 knots. Line width is a spread in Hz (0..30).
    Only 0 < frequency <= 300 Hz lines are synthesized. Invalid lines/sources
    are ignored. No operator gain, notch, band filter or per-frame AGC is used.

    spectrum/peaks use fixed full-scale amplitude .25; demon_spectrum uses
    .10 envelope amplitude. Peaks cover 1..300 Hz, at most five above the
    noise threshold. The two-second FFT has .5 Hz spacing; spectra during
    startup have poorer true resolution. Peaks and DEMON need one second.
    broadband is a 180-bin absolute-bearing scan of
    relative received power with the same beam width. It sums unsteered source
    block mean-square energies times beam amplitude gain squared, with analytic
    ambient/own-noise powers, all divided by .25**2 and clipped to 0..1. It is
    not a coherent sum across sources or a calibrated physical power spectrum.
    DEMON publishes the measured modulation peak plus typed blade-count,
    harmonic-order, and RPM hypotheses. Compatibility fields retain the old
    first-order view. Detection confidence and cavitation are bounded signal
    heuristics, not identity or physical estimates; tonal_hz is the strongest
    measured low-frequency peak, or None.

    Receiver state remains transient under the intentional save/load warm-up.
    Exact continuation would additionally need seed, elapsed, sequence, RNG
    state, _source_states, _shaft_state, _history, _write and _filled. Published
    samples/analysis and _blocks are snapshots; FFT grids and _band_cache are
    rebuildable, never playback- or simulation-dependent persistence inputs.
    """

    sample_rate = 4096
    block_s = 0.25
    MAX_SOURCES = 128
    MAX_LINES = 32
    BAND_CACHE_SIZE = 64
    AVAILABLE_BLOCKS = 2

    def __init__(self, seed=42):
        self.seed = int(_finite(seed, 42)) % (2**64)
        self.sequence = -1
        self._history = np.zeros(2 * self.sample_rate, dtype=np.float32)
        self._time = np.arange(1024) / self.sample_rate
        self._angles = np.arange(180) * 2.0
        self._frequencies = np.fft.rfftfreq(self._history.size, 1 / self.sample_rate)
        self._block_freqs = np.fft.rfftfreq(self._time.size, 1 / self.sample_rate)
        self._ola_window = 0.5 * (1.0
                                  - np.cos(2.0 * np.pi * np.arange(self._time.size)
                                           / self._time.size))
        centers = np.array([config.lofar_bin_freq(i)
                            for i in range(config.LOFAR_BINS)])
        widths = np.where(centers < 40, 1, np.where(centers < 100, 2, 5))
        self._bin_starts = np.searchsorted(self._frequencies, centers - widths / 2)
        self._band_cache = OrderedDict()
        self.evicted_blocks = 0
        self.reset()

    def reset(self):
        """Clear audio, spectra and time on retune; retain seed, advance sequence.

        Reset also rewinds the noise RNG, so replay with the same inputs is
        deterministic. Construction starts sequence at zero; updates and
        explicit resets each increment it once.
        """
        self._rng = np.random.default_rng(self.seed)
        self._source_states = {}
        self._spectral_states = {}
        self._shaft_state = {}
        self._cav_ola = None
        self._cav_rms = 0.0
        self._blocks = deque(maxlen=self.AVAILABLE_BLOCKS)
        self._band_cache.clear()
        self._history.fill(0)
        self._write = self._filled = 0
        self.elapsed = 0.0
        self.samples = np.zeros(1024, dtype=np.float32)
        self.spectrum = [0.0] * config.LOFAR_BINS
        self.broadband = [0.0] * 180
        self.demon_spectrum = [0.0] * 80
        self.demon_analysis = None
        self.peaks = []
        self.ownship_tonals = []
        self.own_noise_lobe = None
        self.sequence += 1

    def blocks_since(self, sequence: int) -> tuple:
        """Read-only (sequence, samples) pairs, oldest first, without consuming.

        Retains current + one handoff block independently of devices/consumers.
        A nonconsecutive first sequence signals overrun or reset, never silently
        concatenate it. At 1x retry unaccepted blocks every frame; at time
        scales above one listening is silent, so callers discard availability.
        Reset clears availability and advances sequence; no zero warm-up block
        is published. Callers must not mutate the returned sample arrays.
        """
        return tuple(block for block in self._blocks if block[0] > sequence)

    def _components(self, desired, previous):
        """Integrate blockwise frequency; ramp amplitude changes over 5 ms.

        Identity is source seed + duplicate occurrence, then fixed line index
        and component name. Callers must keep line slots stable, including zero
        amplitudes. Removed components release once, then forget their phase;
        reappearing components start at the seeded phase with an attack.
        """
        audio = np.zeros(self._time.size)
        state = {}
        edge = round(.005 * self.sample_rate)
        for key in dict.fromkeys((*desired, *previous)):
            old = previous.get(key)
            freq, amp, phase = desired.get(key, (old if old else (0, 0, 0)))
            if key not in desired:
                amp = 0.0
            initial_amp = old[1] if old else 0.0
            if old:
                phase = old[2]
            if initial_amp or amp:
                envelope = amp
                if initial_amp != amp:
                    envelope = np.full(self._time.size, amp)
                    envelope[:edge] = np.linspace(initial_amp, amp, edge)
                audio += envelope * np.sin(2 * np.pi * freq * self._time + phase)
            if key in desired:
                state[key] = (freq, amp, (phase + 2 * np.pi * freq * self.block_s)
                              % (2 * np.pi))
        return audio, state

    def _band_mask(self, low_hz: float, high_hz: float) -> np.ndarray:
        """Bounded LRU of soft masks on the block's 4 Hz FFT grid."""
        key = (float(low_hz), float(high_hz))
        mask = self._band_cache.get(key)
        if mask is not None:
            self._band_cache.move_to_end(key)
            return mask
        width = max(1.0, high_hz - low_hz)
        ramp = 0.25 * width
        freqs = self._block_freqs
        mask = np.zeros_like(freqs)
        sel = (freqs >= low_hz - ramp) & (freqs <= high_hz + ramp)
        mask[sel] = (np.clip((freqs[sel] - (low_hz - ramp)) / ramp, 0, 1)
                     * np.clip(((high_hz + ramp) - freqs[sel]) / ramp, 0, 1))
        mask[0] = 0.0
        self._band_cache[key] = mask
        while len(self._band_cache) > self.BAND_CACHE_SIZE:
            self._band_cache.popitem(last=False)
        return mask

    def _spectral_curve(self, value) -> tuple[tuple[float, float], ...]:
        """Detach a bounded relative gain curve from a source descriptor."""
        if not isinstance(value, (list, tuple)) or not 1 <= len(value) <= 8:
            return ((100.0, 1.0),)
        points = []
        for point in value:
            if (not isinstance(point, (list, tuple)) or len(point) != 2
                    or isinstance(point[0], bool) or isinstance(point[1], bool)):
                return ((100.0, 1.0),)
            frequency, gain = _finite(point[0], float("nan")), _finite(
                point[1], float("nan"))
            if not (0.0 <= frequency <= 3000.0 and 0.0 <= gain <= 4.0):
                return ((100.0, 1.0),)
            points.append((frequency, gain))
        if any(points[index][0] <= points[index - 1][0]
               for index in range(1, len(points))):
            return ((100.0, 1.0),)
        return tuple(points)

    @staticmethod
    def _curve_gain(curve: tuple[tuple[float, float], ...], frequencies):
        x = np.asarray([point[0] for point in curve])
        y = np.asarray([point[1] for point in curve])
        return np.interp(frequencies, x, y, left=y[0], right=y[-1])

    def _frame_audio(self, frame: np.ndarray, mask: np.ndarray,
                     window: np.ndarray) -> np.ndarray:
        return np.fft.irfft(np.fft.rfft(window * frame) * mask, n=frame.size)

    def _band_audio(self, noise: np.ndarray, mask: np.ndarray, rms: float,
                    state: tuple | None,
                    normalization_mask: np.ndarray | None = None):
        """Streaming 50% overlap-add band limit; returns (block, next state).

        Two half-overlapped analysis frames per block keep the FFT band limit
        continuous at the 250 ms boundary. The emitted block is the complete
        overlap-add sum and therefore lags its input by half a block. ``state``
        is ``(previous input half, filtered overlap)``; a missing or mismatched
        state starts from zero padding. A fixed transfer gain targets ``rms``
        without independently normalizing blocks and introducing gain steps.
        """
        n = noise.size
        half = n // 2
        if n < 2 or n % 2:
            return np.zeros(n), None
        window = (self._ola_window if n == self._ola_window.size
                  else 0.5 * (1.0 - np.cos(2.0 * np.pi * np.arange(n) / n)))
        reference = mask if normalization_mask is None else normalization_mask
        weighted_power = (reference[0] ** 2 + reference[-1] ** 2
                          + 2.0 * np.sum(reference[1:-1] ** 2)) / n
        scaled_mask = mask * (rms / math.sqrt(weighted_power)) \
            if weighted_power > 1e-24 else mask
        previous, overlap = state if state is not None else (None, None)
        if (previous is None or overlap is None
                or previous.shape != (half,) or overlap.shape != (half,)):
            previous = np.zeros(half)
            overlap = np.zeros(half)
        output = []
        for current in (noise[:half], noise[half:]):
            filtered = self._frame_audio(
                np.concatenate((previous, current)), scaled_mask, window)
            output.append(overlap + filtered[:half])
            previous = current.copy()
            overlap = filtered[half:]
        return np.concatenate(output), (previous, overlap)

    def update(self, sources, bearing_deg, beam_width_deg, own_noise,
               sea_state, own_speed, own_cavitation=0.0,
               own_noise_bearing=None,
               own_noise_width_deg=OWN_NOISE_LOBE_WIDTH_DEG):
        """Mix all received sources and publish one block; returns None.

        Source dictionaries contain bearing, level, lines [(Hz, amp, width)],
        and a stable integer seed for synthesis identity, never classification.
        At most MAX_SOURCES sources and MAX_LINES fixed line slots are used.
        An optional "broadband" dict {level, low_hz, high_hz} adds a band-
        limited noise layer for that source. own_cavitation (0..1) adds the
        ship's own cavitation noise isotropically. Call reset() when retuning
        to discard the old beam's two-second tail.
        """
        bearing = _finite(bearing_deg) % 360
        width = np.clip(_finite(beam_width_deg, 20), 1, 360)
        own = np.clip(_finite(own_noise), 0, 1)
        sea = np.clip(_finite(sea_state), 0, 9)
        speed = np.clip(_finite(own_speed), 0, 60)
        own_cav = np.clip(_finite(own_cavitation), 0, 1)
        lobe_bearing = _finite(own_noise_bearing, float("nan"))
        if math.isfinite(lobe_bearing):
            lobe_bearing %= 360.0
            lobe_width = float(np.clip(_finite(own_noise_width_deg, 70), 1, 360))
            own_gain = directional_gain(bearing, lobe_bearing, lobe_width)
            self.own_noise_lobe = {
                "bearing": lobe_bearing, "width_deg": lobe_width,
                "level": float(own),
            }
        else:
            lobe_width = 360.0
            own_gain = 1.0
            self.own_noise_lobe = None
        ambient_rms = 0.002 + 0.035 * sea / 9
        own_rms = 0.04 * own + 0.025 * speed / 60
        noise_rms = math.hypot(ambient_rms, own_rms * own_gain)
        audio = self._rng.normal(0, noise_rms, self._time.size)
        engine_amp = 0.08 * min(speed / 20, 1) * (0.25 + own)
        shaft_hz = 10 + 1.9 * speed
        shaft, self._shaft_state = self._components(
            {0: (shaft_hz, engine_amp, 0.0)}, self._shaft_state)
        audio += shaft
        self.ownship_tonals = [{
            "label": "OWN SHAFT", "frequency_hz": shaft_hz,
            "rpm": speed * config.SHIP_RPM_PER_KN + config.SHIP_RPM_MIN,
        }] if speed > 0 else []
        # Shaft frequency is machinery/RPM evidence, not a bearing return.
        scan = np.full(180, (ambient_rms**2 + np.mean(shaft**2)) / .25**2)
        if math.isfinite(lobe_bearing):
            lobe = directional_gain(self._angles, lobe_bearing, lobe_width)
            scan += (((0.04 * own + 0.025 * speed / 60) * lobe) / .25)**2
        else:
            scan += ((0.04 * own + 0.025 * speed / 60) / .25)**2

        entries = {}
        occurrences = {}
        for source in islice(iter(sources), self.MAX_SOURCES):
            if not isinstance(source, dict):
                continue
            direction = _finite(source.get("bearing"), float("nan"))
            level = np.clip(_finite(source.get("level")), 0, 1)
            if not math.isfinite(direction) or level <= 0:
                continue
            direction %= 360
            phase = (int(_finite(source.get("seed"))) % 65536) * (2 * np.pi / 65536)
            lines = source.get("lines", ())
            if not isinstance(lines, (list, tuple)):
                lines = ()
            bb = source.get("broadband")
            bb_level, bb_low, bb_high = 0.0, 0.0, 0.0
            if isinstance(bb, dict):
                bb_level = np.clip(_finite(bb.get("level")), 0, 1)
                bb_low = np.clip(_finite(bb.get("low_hz")), 0, 3000)
                bb_high = np.clip(_finite(bb.get("high_hz")), 0, 3000)
                if not (bb_level > 0 and bb_high > bb_low):
                    bb_level = 0.0
            source_seed = int(_finite(source.get("seed"))) % (2**64)
            occurrence = occurrences.get(source_seed, 0)
            occurrences[source_seed] = occurrence + 1
            curve = self._spectral_curve(source.get("spectral_gains"))
            entries[(source_seed, occurrence)] = (level, direction, phase, lines,
                                                   bb_level, bb_low, bb_high, curve)

        block_index = round(self.elapsed / self.block_s)
        next_states = {}
        next_spectral_states = {}
        for key in dict.fromkeys((*entries, *self._source_states)):
            old_direction, previous, bb_ola, old_bb = self._source_states.get(
                key, (0, {}, None, None))
            old_curve = self._spectral_states.get(key, ((100.0, 1.0),))
            level, direction, phase, lines, bb_level, bb_low, bb_high, curve = entries.get(
                key, (0, old_direction, 0, (), 0, 0, 0, old_curve))
            desired = {}
            for index, line in enumerate(lines[:self.MAX_LINES]):
                if not isinstance(line, (list, tuple)) or len(line) != 3:
                    continue
                freq, amp, spread = (_finite(value) for value in line)
                amp = np.clip(amp, 0, 1)
                spread = np.clip(spread, 0, 30)
                if not 0 < freq <= 300:
                    continue
                partials = (("low", -spread / 2, .25 if spread else 0),
                            ("center", 0, .5 if spread else 1),
                            ("high", spread / 2, .25 if spread else 0))
                for name, offset, weight in partials:
                    if 0 < freq + offset <= 300:
                        spectral_gain = float(self._curve_gain(curve, freq + offset))
                        desired[index, name] = (freq + offset,
                                                .25 * level * amp * weight
                                                * spectral_gain, phase)
                if index == 0 and 2 <= freq <= 80 and spread <= max(1, .15 * freq):
                    # AM as carrier + sidebands, each with integrated phase.
                    carrier_gain = float(self._curve_gain(curve, 700.0))
                    desired[index, "carrier"] = (700, .10 * level * amp * carrier_gain, 3 * phase)
                    desired[index, "am_low"] = (700 - freq, .035 * level * amp * carrier_gain,
                                                  2 * phase + np.pi / 2)
                    desired[index, "am_high"] = (700 + freq, .035 * level * amp * carrier_gain,
                                                   4 * phase - np.pi / 2)
            source_audio, state = self._components(desired, previous)
            if bb_level > 0:
                source_seed = key[0]
                seed_words = (self.seed & 0xffffffff, self.seed >> 32,
                               source_seed & 0xffffffff, source_seed >> 32,
                               key[1], block_index)
                band_noise = np.random.default_rng(
                    np.random.SeedSequence(seed_words)).normal(0, 1,
                                                               self._time.size)
                # OLA preserves the boundary while this bounded per-frame blend
                # prevents abrupt spectral coloration as path geometry changes.
                frequencies = self._block_freqs
                target_mask = self._curve_gain(curve, frequencies)
                previous_mask = self._curve_gain(old_curve, frequencies)
                base_mask = self._band_mask(bb_low, bb_high)
                mask = base_mask * (
                    .5 * previous_mask + .5 * target_mask)
                broadband, bb_ola = self._band_audio(
                    band_noise, mask,
                    _BROADBAND_GAIN * level * bb_level, bb_ola, base_mask)
                source_audio = source_audio + broadband
                bb_params = (bb_low, bb_high,
                             _BROADBAND_GAIN * level * bb_level)
            elif bb_ola is not None and old_bb is not None:
                old_low, old_high, old_rms = old_bb
                broadband, _ = self._band_audio(
                    np.zeros(self._time.size),
                    self._band_mask(old_low, old_high), old_rms, bb_ola)
                source_audio = source_audio + broadband
                bb_ola = None
                bb_params = None
            else:
                bb_ola = None
                bb_params = None
            if key in entries:
                next_states[key] = (direction, state, bb_ola, bb_params)
                next_spectral_states[key] = curve
            audio += source_audio * directional_gain(bearing, direction, width)
            # Actual unsteered block energy, not source presence or current beam
            # amplitude. Incoherent source powers add; normalize all terms alike.
            scan += (np.mean(source_audio**2) / .25**2
                     * directional_gain(self._angles, direction, width)**2)
        self._source_states = next_states
        self._spectral_states = next_spectral_states
        if own_cav > 0:
            band_noise = self._rng.normal(0, 1, self._time.size)
            mask = self._band_mask(_OWN_CAV_LOW_HZ, _OWN_CAV_HIGH_HZ)
            cavitation, self._cav_ola = self._band_audio(
                band_noise, mask, _OWN_CAV_GAIN * own_cav, self._cav_ola)
            audio += cavitation
            scan += (_OWN_CAV_GAIN * own_cav / .25)**2
            self._cav_rms = _OWN_CAV_GAIN * own_cav
        elif self._cav_ola is not None:
            cavitation, _ = self._band_audio(
                np.zeros(self._time.size),
                self._band_mask(_OWN_CAV_LOW_HZ, _OWN_CAV_HIGH_HZ),
                self._cav_rms, self._cav_ola)
            audio += cavitation
            scan += np.mean(cavitation**2) / .25**2
            self._cav_ola = None
            self._cav_rms = 0.0
        else:
            self._cav_ola = None
            self._cav_rms = 0.0

        # Preserve normal mixture headroom for FFT/DEMON analysis. The high
        # soft ceiling only bounds hostile/pathological source collections;
        # audition gain and the final playback limiter are applied later.
        self.samples = smooth_limit(audio, knee=4.0, ceiling=8.0)
        self.broadband = np.clip(scan, 0, 1).tolist()
        count = self.samples.size
        self._history[self._write:self._write + count] = self.samples
        self._write = (self._write + count) % self._history.size
        self._filled = min(self._filled + count, self._history.size)
        if self._filled < self._history.size:
            data = self._history[:self._filled]
        else:
            data = np.concatenate((self._history[self._write:], self._history[:self._write]))
        self.elapsed += self.block_s
        self.sequence += 1
        self.samples.setflags(write=False)
        if len(self._blocks) >= self.AVAILABLE_BLOCKS:
            self.evicted_blocks += 1
        self._blocks.append((self.sequence, self.samples))
        self._analyze(data)

    def _analyze(self, data):
        """Analyze raw beam samples, with no access to source descriptors."""
        self.demon_analysis = None
        self.demon_spectrum = [0.0] * 80
        self.peaks = []
        data = np.asarray(data, dtype=np.float64)[-self._history.size:]
        if data.ndim != 1 or data.size < 32 or not np.isfinite(data).all():
            self.spectrum = [0.0] * config.LOFAR_BINS
            return
        data = data - data.mean()
        window = np.hanning(data.size)
        scale = 2 / window.sum()
        amplitudes = np.abs(np.fft.rfft(data * window, n=self._history.size)) * scale
        low = amplitudes[self._frequencies <= 300]
        self.spectrum = np.clip(np.maximum.reduceat(low, self._bin_starts) / .25, 0, 1).tolist()
        if data.size < self.sample_rate:
            return
        floor = float(np.median(low))
        threshold = max(.006, 6 * floor, .04 * float(low.max()))
        maxima = np.flatnonzero((amplitudes[1:-1] > amplitudes[:-2]) &
                               (amplitudes[1:-1] >= amplitudes[2:]) &
                               (amplitudes[1:-1] > threshold)) + 1
        maxima = maxima[self._frequencies[maxima] <= 300]
        for index in maxima[np.argsort(low[maxima])[::-1]]:
            freq = float(self._frequencies[index])
            if freq >= 1 and all(abs(freq - other) >= 2 for other, _ in self.peaks):
                self.peaks.append((freq, float(min(1, low[index] / .25))))
                if len(self.peaks) == 5:
                    break

        # A low-frequency tone alone must not be mistaken for modulation.
        envelope = analytic_envelope(data, self.sample_rate, 400.0, 1400.0)
        carrier_rms = float(np.sqrt(np.mean(envelope**2) / 2))
        envelope_mean = float(envelope.mean())
        modulation = np.abs(np.fft.rfft((envelope - envelope_mean) * window,
                                      n=self._history.size)) * scale
        band_indices = np.flatnonzero((self._frequencies >= 1) & (self._frequencies <= 80))
        band = modulation[band_indices]
        self.demon_spectrum = np.clip(np.interp(np.arange(1, 81),
                                                self._frequencies, modulation) / .10, 0, 1).tolist()
        index = int(np.argmax(band))
        peak = float(band[index])
        noise_floor = float(np.median(band))
        nearby = np.abs(self._frequencies[band_indices] - self._frequencies[band_indices[index]]) <= 1
        concentration = float(np.sum(band[nearby]**2) / (np.sum(band**2) + 1e-12))
        if (carrier_rms < .012 or peak < .008 or peak < 6 * noise_floor
                or peak < .12 * envelope_mean or concentration < .35):
            return
        modulation_peak = float(self._frequencies[band_indices[index]])
        hypotheses = tuple(
            RPMHypothesis(blades, order,
                          round(modulation_peak * 60 / (blades * order), 1))
            for blades in (3, 4, 5, 6, 7) for order in range(1, 5))
        detection_confidence = float(np.clip(
            concentration * (1 - 6 * noise_floor / peak), 0, 1))
        self.demon_analysis = {
            "modulation_peak_hz": modulation_peak,
            "harmonic_rpm_hypotheses": hypotheses,
            "detection_confidence": detection_confidence,
            # Compatibility keys for existing displays and classification code.
            "blade_rate_hz": modulation_peak,
            "rpm_candidates": tuple(round(modulation_peak * 60 / blades, 1)
                                    for blades in (3, 4, 5, 6, 7)),
            "confidence": detection_confidence,
            "cavitation": float(np.clip(carrier_rms / .15, 0, 1)),
            "tonal_hz": self.peaks[0][0] if self.peaks else None,
        }
