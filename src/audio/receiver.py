"""Synthetic beam audio and sample-derived spectra; no target classification.

The first line, if narrow and in 2..80 Hz, illustratively modulates a 700 Hz
carrier. This is NOT a measurement of true propeller blades. The same rule
applies to every source, and DEMON measures only the resulting mixed audio.

Broadband: sources may carry a "broadband" dict {level, low_hz, high_hz}
(target-internal band energy). Every source receives an independent,
seed-derived and replayable noise stream. Existing call sites without
broadband data keep producing bit-identical audio.
"""

import math

import numpy as np

from src.core import config

_BROADBAND_GAIN = 0.04      # rms-Skalierung der Bandrauschaudio
_OWN_CAV_GAIN = 0.10        # rms-Skalierung der Eigen-Kavitation
_OWN_CAV_LOW_HZ = 80.0
_OWN_CAV_HIGH_HZ = 380.0
_SCAN_BROADBAND_GAIN = 0.35  # BTR-Scan-Aufschlag fuer Breitband-Quellen


def _finite(value, default=0.0):
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return value if math.isfinite(value) else default


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
    relative received power with the same beam width and isotropic noise.
    DEMON RPM candidates are a tuple in blade-count order (3, 4, 5, 6, 7);
    tonal_hz is the strongest measured low-frequency peak, or None. Confidence
    and cavitation are bounded signal heuristics, not physical estimates.
    """

    sample_rate = 4096
    block_s = 0.25

    def __init__(self, seed=42):
        self.seed = int(_finite(seed, 42)) % (2**64)
        self.sequence = -1
        self._history = np.zeros(2 * self.sample_rate, dtype=np.float32)
        self._time = np.arange(1024) / self.sample_rate
        self._angles = np.arange(180) * 2.0
        self._frequencies = np.fft.rfftfreq(self._history.size, 1 / self.sample_rate)
        self._block_freqs = np.fft.rfftfreq(self._time.size, 1 / self.sample_rate)
        centers = np.array([config.lofar_bin_freq(i)
                            for i in range(config.LOFAR_BINS)])
        widths = np.where(centers < 40, 1, np.where(centers < 100, 2, 5))
        self._bin_starts = np.searchsorted(self._frequencies, centers - widths / 2)
        self._band_cache = {}
        self.reset()

    def reset(self):
        """Clear audio, spectra and time on retune; retain seed, advance sequence.

        Reset also rewinds the noise RNG, so replay with the same inputs is
        deterministic. Construction starts sequence at zero; updates and
        explicit resets each increment it once.
        """
        self._rng = np.random.default_rng(self.seed)
        self._history.fill(0)
        self._write = self._filled = 0
        self.elapsed = 0.0
        self.samples = np.zeros(1024, dtype=np.float32)
        self.spectrum = [0.0] * config.LOFAR_BINS
        self.broadband = [0.0] * 180
        self.demon_spectrum = [0.0] * 80
        self.demon_analysis = None
        self.peaks = []
        self.sequence += 1

    def _band_mask(self, low_hz: float, high_hz: float) -> np.ndarray:
        """Weiche 0..1-Maske ueber dem 2-Hz-FFT-Raster eines Audioterms."""
        key = (round(low_hz), round(high_hz))
        mask = self._band_cache.get(key)
        if mask is not None:
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
        return mask

    @staticmethod
    def _band_audio(noise: np.ndarray, mask: np.ndarray, rms: float) -> np.ndarray:
        spectrum = np.fft.rfft(noise) * mask
        signal = np.fft.irfft(spectrum, n=noise.size)
        actual = float(np.sqrt(np.mean(signal**2)))
        if actual > 1e-12:
            signal *= rms / actual
        return signal

    def update(self, sources, bearing_deg, beam_width_deg, own_noise,
               sea_state, own_speed, own_cavitation=0.0):
        """Mix all received sources and publish one block; returns None.

        Source dictionaries contain bearing, level, lines [(Hz, amp, width)],
        and a stable integer seed used only for phase, never identity/ranking.
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
        noise_rms = 0.002 + 0.035 * sea / 9 + 0.04 * own + 0.025 * speed / 60
        t = self._time + self.elapsed
        audio = self._rng.normal(0, noise_rms, self._time.size)
        engine_amp = 0.08 * min(speed / 20, 1) * (0.25 + own)
        audio += engine_amp * np.sin(2 * np.pi * (10 + 1.9 * speed) * t)
        scan = np.full(180, (noise_rms / 0.25)**2 + (engine_amp / 0.25)**2 / 2)

        entries = []
        for source in sources:
            if not isinstance(source, dict):
                continue
            direction = _finite(source.get("bearing"), float("nan"))
            level = np.clip(_finite(source.get("level")), 0, 1)
            if not math.isfinite(direction) or level <= 0:
                continue
            direction %= 360
            delta = (direction - bearing + 180) % 360 - 180
            gain = level * math.exp(-4 * math.log(2) * (delta / width)**2)
            offsets = (self._angles - direction + 180) % 360 - 180
            scan += (level * np.exp(-4 * math.log(2) * (offsets / width)**2))**2
            phase = (int(_finite(source.get("seed"))) % 65536) * (2 * np.pi / 65536)
            lines = source.get("lines", ())
            if not isinstance(lines, (list, tuple)):
                continue
            bb = source.get("broadband")
            bb_level, bb_low, bb_high = 0.0, 0.0, 0.0
            if isinstance(bb, dict):
                bb_level = np.clip(_finite(bb.get("level")), 0, 1)
                bb_low = np.clip(_finite(bb.get("low_hz")), 0, 3000)
                bb_high = np.clip(_finite(bb.get("high_hz")), 0, 3000)
                if not (bb_level > 0 and bb_high > bb_low):
                    bb_level = 0.0
            source_seed = int(_finite(source.get("seed"))) % (2**64)
            entries.append((gain, direction, phase, lines,
                            bb_level, bb_low, bb_high, source_seed))

        block_index = round(self.elapsed / self.block_s)
        for gain, direction, phase, lines, bb_level, bb_low, bb_high, source_seed in entries:
            for index, line in enumerate(lines):
                if not isinstance(line, (list, tuple)) or len(line) != 3:
                    continue
                freq, amp, spread = (_finite(value) for value in line)
                amp = np.clip(amp, 0, 1)
                spread = np.clip(spread, 0, 30)
                if not 0 < freq <= 300 or amp <= 0:
                    continue
                # Symmetric side tones give finite-width lines without keeping
                # per-source phase state. Absolute audio time preserves phase.
                partials = ((0, 1),) if spread == 0 else ((-spread / 2, .25),
                                                          (0, .5), (spread / 2, .25))
                for offset, weight in partials:
                    if 0 < freq + offset <= 300:
                        audio += .25 * gain * amp * weight * np.sin(
                            2 * np.pi * (freq + offset) * t + phase)
                if index == 0 and 2 <= freq <= 80 and spread <= max(1, .15 * freq):
                    envelope = 1 + .7 * np.sin(2 * np.pi * freq * t + phase)
                    audio += .10 * gain * amp * envelope * np.sin(
                        2 * np.pi * 700 * t + 3 * phase)
            if bb_level > 0:
                seed_words = (self.seed & 0xffffffff, self.seed >> 32,
                              source_seed & 0xffffffff, source_seed >> 32,
                              block_index)
                band_noise = np.random.default_rng(
                    np.random.SeedSequence(seed_words)).normal(0, 1, self._time.size)
                mask = self._band_mask(bb_low, bb_high)
                audio += self._band_audio(band_noise, mask,
                                          _BROADBAND_GAIN * gain * bb_level)
                d2 = (self._angles - direction + 180) % 360 - 180
                scan += (_SCAN_BROADBAND_GAIN * gain * bb_level
                         * np.exp(-4 * math.log(2) * (d2 / width)**2))**2
        if own_cav > 0:
            band_noise = self._rng.normal(0, 1, self._time.size)
            mask = self._band_mask(_OWN_CAV_LOW_HZ, _OWN_CAV_HIGH_HZ)
            audio += self._band_audio(band_noise, mask,
                                      _OWN_CAV_GAIN * own_cav)
            scan += (_SCAN_BROADBAND_GAIN * _OWN_CAV_GAIN * own_cav)**2

        self.samples = np.clip(audio, -1, 1).astype(np.float32)
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

        # Analytic high-passed signal (FFT Hilbert transform, no SciPy).
        # A low-frequency tone alone must not be mistaken for modulation.
        frequencies = np.fft.fftfreq(data.size, 1 / self.sample_rate)
        carrier_fft = np.fft.fft(data)
        carrier_fft *= 2 * ((frequencies >= 400) & (frequencies <= 1400))
        envelope = np.abs(np.fft.ifft(carrier_fft))
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
        blade_rate = float(self._frequencies[band_indices[index]])
        self.demon_analysis = {
            "blade_rate_hz": blade_rate,
            "rpm_candidates": tuple(round(blade_rate * 60 / blades, 1)
                                    for blades in (3, 4, 5, 6, 7)),
            "confidence": float(np.clip(concentration * (1 - 6 * noise_floor / peak), 0, 1)),
            "cavitation": float(np.clip(carrier_rms / .15, 0, 1)),
            "tonal_hz": self.peaks[0][0] if self.peaks else None,
        }
