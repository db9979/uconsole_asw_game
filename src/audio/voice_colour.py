"""How a spoken report sounds on its way to the listener.

The executive officer stands beside the commander and is heard as he is.
Every other station reports over the ship's (or boat's) internal net: a
telephone band, slightly driven, so the stations sound like a speaker on a
bulkhead and stand apart from the officer.  The radio room's reports come
over the radio net: a narrower band, more drive, a little hiss and a short
squelch tail when the speaker lets go of the key.

Runs on the speech service's worker thread on each piece of audio as it
arrives (``src/llm/voice.py``): a short windowed-sinc band pass applied by
``numpy.convolve`` with the last samples of the previous piece carried over,
so pieces join without a click and nothing loops per sample in Python.
Wall-side only; nothing here touches the simulation.
"""

from __future__ import annotations

import numpy as np

COLOURS = ("", "intercom", "radio")
# (low Hz, high Hz, drive, hiss level) per colour.
_SHAPE = {
    "intercom": (300.0, 3400.0, 1.8, 0.0),
    "radio": (450.0, 2600.0, 3.2, 0.012),
}
TAPS = 127
SQUELCH_S = 0.14
SQUELCH_LEVEL = 0.10


def _band_pass(rate: int, low: float, high: float) -> np.ndarray:
    """A linear-phase FIR band pass (difference of two windowed sincs)."""
    n = np.arange(TAPS, dtype=np.float64) - (TAPS - 1) / 2.0
    nyquist = rate / 2.0
    high = min(high, nyquist * 0.95)

    def low_pass(cut):
        frac = cut / rate
        return 2.0 * frac * np.sinc(2.0 * frac * n)

    window = np.hamming(TAPS)
    taps = (low_pass(high) - low_pass(low)) * window
    # Unity gain in the middle of the pass band.
    centre = np.sqrt(low * high)
    response = abs(np.sum(taps * np.exp(-2j * np.pi * centre / rate * np.arange(TAPS))))
    return (taps / max(response, 1e-9)).astype(np.float32)


class VoiceColour:
    """One report's filter; ``feed`` float32 pieces, then ``tail`` once."""

    def __init__(self, colour: str, rate: int, seed: int = 0):
        self.colour = colour if colour in _SHAPE else ""
        self.rate = int(rate)
        self._history = np.zeros(TAPS - 1, dtype=np.float32)
        self._rng = np.random.default_rng(seed)
        if self.colour:
            low, high, self._drive, self._hiss = _SHAPE[self.colour]
            self._taps = _band_pass(self.rate, low, high)
            # tanh(drive * x) / tanh(drive): full scale stays full scale.
            self._norm = float(np.tanh(self._drive))

    @property
    def active(self) -> bool:
        return bool(self.colour)

    def feed(self, samples: np.ndarray) -> np.ndarray:
        """Float32 samples in -1..1 -> the coloured piece (same length)."""
        if not self.colour or not len(samples):
            return samples
        samples = np.asarray(samples, dtype=np.float32)
        joined = np.concatenate((self._history, samples))
        out = np.convolve(joined, self._taps, mode="valid").astype(np.float32)
        self._history = joined[-(TAPS - 1):].copy()
        out = np.tanh(self._drive * out) / self._norm
        if self._hiss:
            out += self._hiss * self._rng.standard_normal(len(out)).astype(np.float32)
        return np.clip(out, -1.0, 1.0).astype(np.float32)

    def tail(self) -> np.ndarray:
        """The filter's last samples, and the radio's squelch tail after the
        last word (empty without a colour)."""
        if not self.colour:
            return np.zeros(0, dtype=np.float32)
        flush = self.feed(np.zeros(TAPS - 1, dtype=np.float32))
        if self.colour != "radio":
            return flush
        count = max(1, int(self.rate * SQUELCH_S))
        noise = self._rng.standard_normal(count).astype(np.float32)
        noise = np.convolve(noise, self._taps, mode="same").astype(np.float32)
        envelope = np.linspace(1.0, 0.0, count, dtype=np.float32) ** 2
        squelch = np.clip(SQUELCH_LEVEL * noise * envelope / max(1e-6, float(
            np.max(np.abs(noise)))), -1.0, 1.0).astype(np.float32)
        return np.concatenate((flush, squelch))
