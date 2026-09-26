"""Operator signal-analysis tools for LOFAR and DEMON (pure, bounded).

Nothing here detects, names or ranks a signal. The operator places a
frequency cursor, marks lines and chooses the integration time; these helpers
only do the arithmetic an analyst would do by hand (reading a level, drawing a
harmonic comb, dividing a blade rate by a shaft rate) and average spectra.
They never touch simulation state, so display choices cannot change results.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Receiver columns arrive every 0.25 s; each is already a 2 s FFT.
COLUMN_S = 0.25
# 2 s is the receiver's own FFT window (no extra averaging); longer settings
# average successive spectra incoherently to lift steady tonals out of noise.
NATIVE_INTEGRATION_S = 2
INTEGRATION_CHOICES_S = (NATIVE_INTEGRATION_S, 8, 16, 64)
MAX_INTEGRATION_COLUMNS = int(max(INTEGRATION_CHOICES_S) / COLUMN_S)
LOFAR_CURSOR_RANGE_HZ = (0.5, 300.0)
DEMON_CURSOR_RANGE_HZ = (0.5, 50.0)
VERNIER_SPAN_HZ = 20.0
# Operator-selectable DEMON carrier bands (cavitation noise band to search)
# and heterodyne shift frequencies for audition.
DEMON_BANDS_HZ = ((200.0, 800.0), (400.0, 1400.0), (1000.0, 2000.0))
HETERODYNE_OFFSETS_HZ = (400.0, 700.0, 1000.0, 1200.0)
HARMONIC_COUNT = 12


def clamp_cursor(hz: float, page: str) -> float:
    low, high = LOFAR_CURSOR_RANGE_HZ if page == "lofar" else DEMON_CURSOR_RANGE_HZ
    return round(min(high, max(low, float(hz))) * 2.0) / 2.0


def window_columns(seconds: int) -> int:
    """Columns averaged for an integration time (1 = the native FFT)."""
    if seconds <= NATIVE_INTEGRATION_S:
        return 1
    return min(MAX_INTEGRATION_COLUMNS, int(round(seconds / COLUMN_S)))


def integrate(columns, seconds: int) -> np.ndarray:
    """Incoherent average of the newest columns covering ``seconds``."""
    rows = np.asarray(list(columns), dtype=float)
    if rows.ndim != 2 or not len(rows):
        return np.zeros(0)
    count = min(len(rows), window_columns(seconds))
    return rows[-count:].mean(axis=0)


def integrate_rows(rows, seconds: int) -> np.ndarray:
    """Running mean along time for a waterfall (row i averages its window)."""
    data = np.asarray(list(rows), dtype=float)
    if data.ndim != 2 or not len(data):
        return data
    window = min(len(data), window_columns(seconds))
    if window == 1:
        return data
    padded = np.concatenate((np.repeat(data[:1], window - 1, axis=0), data))
    cumulative = np.cumsum(padded, axis=0)
    cumulative = np.concatenate((np.zeros((1, data.shape[1])), cumulative))
    return (cumulative[window:] - cumulative[:-window]) / window


def level_at(values, frequencies, hz: float):
    """Level of the bin nearest to ``hz`` (None without data)."""
    values = np.asarray(values, dtype=float)
    frequencies = np.asarray(frequencies, dtype=float)
    if not values.size or values.size != frequencies.size:
        return None
    return float(values[int(np.argmin(np.abs(frequencies - float(hz))))])


def harmonic_comb(fundamental_hz: float, maximum_hz: float,
                  count: int = HARMONIC_COUNT) -> list:
    """Multiples of an operator-chosen fundamental that fall on the display."""
    if fundamental_hz is None or fundamental_hz <= 0:
        return []
    return [(n, fundamental_hz * n) for n in range(1, count + 1)
            if fundamental_hz * n <= maximum_hz]


def blade_count(shaft_hz, blade_hz):
    """Blades from the operator's shaft and blade-rate marks.

    Returns ``(blades, deviation, rpm)``: the nearest whole ratio, how far the
    measured ratio is from it (0 = exact), and the shaft RPM.
    """
    if shaft_hz is None or blade_hz is None or shaft_hz <= 0 or blade_hz <= 0:
        return None
    ratio = float(blade_hz) / float(shaft_hz)
    blades = max(1, int(round(ratio)))
    return blades, ratio - blades, float(shaft_hz) * 60.0


def vernier_window(cursor_hz: float, maximum_hz: float = LOFAR_CURSOR_RANGE_HZ[1]):
    low = max(0.0, float(cursor_hz) - VERNIER_SPAN_HZ / 2.0)
    high = min(maximum_hz, low + VERNIER_SPAN_HZ)
    return max(0.0, high - VERNIER_SPAN_HZ), high


@dataclass
class AcousticToolState:
    """Transient operator tool settings (UI state, never saved or simulated)."""

    lofar_cursor_hz: float = 50.0
    demon_cursor_hz: float = 10.0
    integration_s: int = NATIVE_INTEGRATION_S
    vernier: bool = False
    shaft_hz: float | None = None
    blade_hz: float | None = None

    def cycle_integration(self) -> int:
        choices = INTEGRATION_CHOICES_S
        index = choices.index(self.integration_s) if self.integration_s in choices else 0
        self.integration_s = choices[(index + 1) % len(choices)]
        return self.integration_s

    def mark_demon(self, hz: float) -> str:
        """First mark = shaft line, second = blade line, third clears both."""
        if self.shaft_hz is None:
            self.shaft_hz = hz
            return "shaft"
        if self.blade_hz is None:
            self.blade_hz = hz
            return "blade"
        self.shaft_hz = self.blade_hz = None
        return "cleared"
