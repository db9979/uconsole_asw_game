"""Sonar class library: catalog classes sorted by how well they fit the
operator's own line marks.

The operator marks lines by hand: the LOFAR fundamental (a tonal line) and
on the DEMON page the shaft line and the blade line.  Each catalog class is
graded against the marks it can be compared with: the shaft RPM against the
class's RPM range (best in its middle), the blade count (blade line / shaft
line) against its blade counts, and the tonal line against its main tonal
band and its secondary tonals (gears, pumps).  The result is a sorted list with a fit of
0..1 and the number of marks it rests on; the classification itself stays
the operator's annotation.

Pure and bounded: the grade depends only on the marks and the catalog, never
on a hidden contact.  Both sonar rooms (frigate and crewed submarine) use it.
"""

from __future__ import annotations

import math

# How far outside a class's range a mark may lie before it no longer fits
# (relative to the range's edge): falling from the edge value to 0.
RPM_TOLERANCE = 0.25
TONAL_TOLERANCE = 0.25
# A secondary tonal (gear, pump) matches within this many hertz.
SECONDARY_MATCH_HZ = 1.5
# Fit at the edge of a class's range (1.0 in its middle).
EDGE_PENALTY = 0.3
# A blade ratio further than this from a whole number is not a blade count.
BLADE_DEVIATION_MAX = 0.3
WEIGHTS = {"rpm": 0.35, "blades": 0.35, "tonal": 0.30}
# Below this many marks the list is only a hint.
SURE_MARKS = 2
MAX_ROWS = 12


def _band_fit(value: float, low: float, high: float, tolerance: float) -> float:
    if low <= value <= high:
        # Inside the range the middle fits best: a class whose range the
        # mark only grazes is a weaker candidate than one it sits in.
        half = (high - low) / 2.0
        if half <= 0.0:
            return 1.0
        return 1.0 - EDGE_PENALTY * abs(value - (low + high) / 2.0) / half
    edge = low if value < low else high
    distance = abs(value - edge) / max(abs(edge), 1e-6)
    return max(0.0, (1.0 - EDGE_PENALTY) * (1.0 - distance / tolerance))


def _valid(value) -> bool:
    return (type(value) in (int, float) and not isinstance(value, bool)
            and math.isfinite(value) and value > 0.0)


def marks_count(shaft_hz=None, blade_hz=None, tonal_hz=None) -> int:
    return sum(1 for value in (shaft_hz, blade_hz, tonal_hz) if _valid(value))


def grade(signature, shaft_hz=None, blade_hz=None, tonal_hz=None):
    """Fit of one class (0..1) and the parts it rests on, or None when no
    mark can be compared with it."""
    parts = {}
    if _valid(shaft_hz) and signature.rpm_range:
        parts["rpm"] = _band_fit(float(shaft_hz) * 60.0, float(signature.rpm_range[0]),
                                 float(signature.rpm_range[1]), RPM_TOLERANCE)
    if _valid(shaft_hz) and _valid(blade_hz) and signature.blade_counts:
        ratio = float(blade_hz) / float(shaft_hz)
        blades = max(1, int(round(ratio)))
        deviation = abs(ratio - blades)
        parts["blades"] = (max(0.0, 1.0 - deviation / BLADE_DEVIATION_MAX)
                           if blades in signature.blade_counts else 0.0)
    if _valid(tonal_hz):
        band = signature.tonal_band_hz
        main = (_band_fit(float(tonal_hz), float(band[0]), float(band[1]), TONAL_TOLERANCE)
                if band else 0.0)
        secondary = max((1.0 - abs(float(tonal_hz) - float(line[0])) / SECONDARY_MATCH_HZ
                         for line in signature.secondary_tonals
                         if abs(float(tonal_hz) - float(line[0])) < SECONDARY_MATCH_HZ),
                        default=0.0)
        parts["tonal"] = max(main, secondary)
    if not parts:
        return None
    weight = sum(WEIGHTS[name] for name in parts)
    return round(sum(WEIGHTS[name] * value for name, value in parts.items()) / weight, 3), parts


def rank(signatures, shaft_hz=None, blade_hz=None, tonal_hz=None, limit: int = MAX_ROWS):
    """Classes sorted by fit (best first, then by key): ``[(signature, fit)]``.

    Empty without a usable mark.  Ties keep a stable key order."""
    if marks_count(shaft_hz, blade_hz, tonal_hz) == 0:
        return []
    rows = []
    for signature in signatures:
        result = grade(signature, shaft_hz, blade_hz, tonal_hz)
        if result is not None:
            rows.append((signature, result[0]))
    rows.sort(key=lambda row: (-row[1], str(row[0].key)))
    return rows[:max(0, int(limit))]
