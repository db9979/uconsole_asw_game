"""DEMON: Huellenspektrum zur Blattfrequenz- und RPM-Schaetzung."""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class DemonResult:
    blade_rate_hz: float | None
    rpm_candidates: tuple[float, ...]
    confidence: float
    cavitation: float


class DemonAnalyzer:
    """Kleine, deterministische DEMON-Auswertung fuer ein fokussiertes Signal."""

    def __init__(self, sample_rate: int = 8000, min_hz: float = 2.0,
                 max_hz: float = 80.0, fft_size: int = 4096):
        self.sample_rate = sample_rate
        self.min_hz = min_hz
        self.max_hz = max_hz
        self.fft_size = fft_size

    def analyze(self, samples: np.ndarray, blade_counts=(3, 4, 5, 6)) -> DemonResult:
        data = np.asarray(samples, dtype=np.float32).reshape(-1)
        if data.size < 32 or not np.isfinite(data).all():
            return DemonResult(None, (), 0.0, 0.0)
        data = data[-self.fft_size:]
        data = data - np.mean(data)
        envelope = np.abs(data)
        # Gleichanteil entfernen, damit Fensterrauschen keine Tieffrequenz-
        # Spitze als Blattfrequenz vortaeuscht.
        envelope = envelope - np.mean(envelope)
        window = np.hanning(envelope.size)
        spectrum = np.abs(np.fft.rfft(envelope * window))
        frequencies = np.fft.rfftfreq(envelope.size, 1.0 / self.sample_rate)
        mask = (frequencies >= self.min_hz) & (frequencies <= self.max_hz)
        if not np.any(mask):
            return DemonResult(None, (), 0.0, 0.0)
        band = spectrum[mask]
        idx = int(np.argmax(band))
        peak = float(band[idx])
        total = float(np.sum(band)) + 1e-9
        blade_rate = float(frequencies[mask][idx])
        confidence = max(0.0, min(1.0, peak / total * 8.0))
        high_band = spectrum[frequencies >= self.max_hz * 0.65]
        cavitation = max(0.0, min(1.0, float(np.mean(high_band)) /
                                   (float(np.mean(band)) + 1e-9) * 0.25))
        candidates = tuple(round(blade_rate * 60.0 / count, 1)
                          for count in blade_counts)
        return DemonResult(round(blade_rate, 2), candidates,
                           round(confidence, 3), round(cavitation, 3))
