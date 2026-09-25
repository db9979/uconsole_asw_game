"""Operator target motion analysis: hypothesis, residuals, acceptance (pure).

The operator proposes a target course, speed and range on the newest
measured bearing. This module only replays the recorded own-ship bearing
track against that hypothesis: it predicts each bearing and reports the
residuals. Nothing here searches for a solution; the automatic solver in
``tma.py`` is a separate training aid.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from src.core import config

COURSE_STEP_DEG = 5.0
COURSE_FINE_DEG = 1.0
SPEED_STEP_KN = 1.0
RANGE_STEP_NM = 1.0
RANGE_FINE_NM = 0.2
SPEED_MAX_KN = 45.0
RANGE_MIN_NM = 0.2
RANGE_MAX_NM = 60.0
MIN_POINTS = 4
SEGMENTS = 4
NOISE_REFERENCE_DEG = 2.0   # bearing scatter that still pins a solution


@dataclass(frozen=True)
class Hypothesis:
    course: float
    speed_kn: float
    range_nm: float

    def clamped(self) -> "Hypothesis":
        return Hypothesis(self.course % 360.0,
                          min(SPEED_MAX_KN, max(0.0, self.speed_kn)),
                          min(RANGE_MAX_NM, max(RANGE_MIN_NM, self.range_nm)))


def default_hypothesis(points) -> Hypothesis:
    """Neutral start: target crossing the newest bearing at 8 kn, 10 NM."""
    bearing = points[-1].bearing if points else 0.0
    return Hypothesis((bearing + 90.0) % 360.0, 8.0, 10.0)


def _reference(points, hypothesis: Hypothesis):
    ref = points[-1]
    angle = math.radians(ref.bearing)
    x = ref.fx + hypothesis.range_nm * math.sin(angle)
    y = ref.fy - hypothesis.range_nm * math.cos(angle)
    speed = config.kn_to_nm_per_s(hypothesis.speed_kn)
    course = math.radians(hypothesis.course)
    return ref.t, x, y, speed * math.sin(course), -speed * math.cos(course)


def position_at(points, hypothesis: Hypothesis, t: float):
    """Target position the hypothesis implies at time ``t``."""
    t_ref, x, y, vx, vy = _reference(points, hypothesis)
    return x + vx * (t - t_ref), y + vy * (t - t_ref)


def residuals(points, hypothesis: Hypothesis) -> list:
    """Measured minus predicted bearing (deg, -180..180) for every point."""
    if not points:
        return []
    t_ref, x, y, vx, vy = _reference(points, hypothesis)
    result = []
    for point in points:
        tx = x + vx * (point.t - t_ref)
        ty = y + vy * (point.t - t_ref)
        predicted = math.degrees(math.atan2(tx - point.fx, -(ty - point.fy))) % 360.0
        result.append(((point.bearing - predicted + 180.0) % 360.0) - 180.0)
    return result


def _effective_count(values) -> float:
    """Sample count corrected for correlated noise (lag-1 autocorrelation)."""
    count = len(values)
    if count < 3:
        return float(count)
    mean = sum(values) / count
    centred = [value - mean for value in values]
    variance = sum(value * value for value in centred)
    if variance <= 1e-12:
        return float(count)
    rho = sum(a * b for a, b in zip(centred, centred[1:])) / variance
    rho = min(0.95, max(0.0, rho))
    return max(1.0, count * (1.0 - rho) / (1.0 + rho))


def observability(points) -> float:
    """0..1: how far own ship's course changed over the track (range needs it)."""
    if len(points) < 2:
        return 0.0
    courses = [point.fcourse for point in points]
    span = max(abs(((a - b + 180.0) % 360.0) - 180.0)
               for a in courses for b in (courses[0], courses[-1]))
    return min(1.0, span / (2.0 * config.TMA_MIN_COURSE_CHG_DEG))


def evaluate(points, hypothesis: Hypothesis):
    """How well the hypothesis explains the bearings.

    Single bearings are noisy (and their errors correlated), so a plain RMS
    cannot tell a good hypothesis from a bad one. As an analyst reads the
    residual plot, the fit looks for *systematic* residuals: the track is
    split into four time segments and each segment's mean residual is
    compared with the noise left after averaging, estimated from the
    residual scatter itself. ``quality`` also carries observability: without
    an own-ship manoeuvre the range cannot be tested at all.
    """
    values = residuals(points, hypothesis)
    if len(values) < MIN_POINTS:
        return None
    # Short tracks are split in two halves, longer ones in four segments.
    segments = SEGMENTS if len(values) >= 4 * SEGMENTS else 2
    rms = math.sqrt(sum(value * value for value in values) / len(values))
    size = len(values) / segments
    means, scatter = [], []
    for index in range(segments):
        part = values[int(round(index * size)):int(round((index + 1) * size))]
        mean = sum(part) / len(part)
        means.append(mean)
        scatter.extend(value - mean for value in part)
    sigma = max(0.25, math.sqrt(sum(value * value for value in scatter) / len(scatter)))
    noise = sigma / math.sqrt(max(1.0, _effective_count(scatter) / segments))
    systematic = math.sqrt(sum(mean * mean for mean in means) / segments)
    fit = math.exp(-0.5 * (systematic / (2.0 * noise)) ** 2)
    seen = observability(points)
    # Noisy bearings cannot pin a solution down even when it fits: the
    # accepted quality (and so the range uncertainty) reflects that.
    precision = min(1.0, NOISE_REFERENCE_DEG / sigma)
    return {"rms_deg": rms, "systematic_deg": systematic, "fit": fit,
            "observability": seen, "sigma_deg": sigma,
            "quality": fit * seen * precision,
            "residuals": values, "segment_means": means}
