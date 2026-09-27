"""Visual detection physics for lookouts (pure functions).

* Koschmieder's law: the apparent contrast of a target against the horizon
  sky decays as C(R) = C0 exp(-3.912 R / V), V = meteorological visibility.
* The eye's contrast threshold rises for small targets (Blackwell-type):
  eps(alpha) = EPS0 (1 + (ALPHA0 / alpha)^2), alpha = target height / range.
* Whitecaps raise the background clutter of sea-level targets by a factor
  per sea state (small, low targets such as a sail suffer most); aircraft
  are seen against the sky.
* Night: the threshold rises by the ratio of adaptation luminances, and the
  moon's illuminated fraction (from its phase) interpolates between a dark
  new-moon night and a full-moon night.
* A target is visible only above the geometric horizon of lookout eye height
  plus target height.

The inherent contrast C0 of each target kind is solved so that the 1.0.0
day, calm, clear-air ranges are reproduced exactly; the night multipliers
are solved so that a half moon reproduces the 1.0.0 night factor for a
surface ship.
"""

from __future__ import annotations

import math

KOSCHMIEDER = 3.912
EPS0 = 0.02
ALPHA0_RAD = math.radians(1.0 / 60.0) * 3.0     # ~3 arcmin knee
LOOKOUT_EYE_HEIGHT_M = 18.0
SYNODIC_MONTH_D = 29.530588
NIGHT_RANGE_NEW_MOON = 0.25     # fraction of day range, surface ship
NIGHT_RANGE_FULL_MOON = 0.45
SEA_CLUTTER_PER_STATE = 0.45    # threshold growth per sea state (sea-level targets)

TARGET_HEIGHT_M = {
    "SURFACE": 12.0,
    "SUB": 3.0,        # sail/periscope and wake of a surfaced boat
    "FLG": 6.0,        # apparent size of an aircraft
    "TORP": 1.0,       # bubble track
    "LAND": 50.0,      # coastal hills and cliffs
}


def optical_horizon_nm(eye_m: float, target_m: float) -> float:
    """Geometric horizon with standard optical refraction (2.08 NM/sqrt(m))."""
    return 2.08 * (math.sqrt(max(eye_m, 0.0)) + math.sqrt(max(target_m, 0.0)))


def threshold(height_m: float, range_nm: float) -> float:
    alpha = height_m / max(range_nm * 1852.0, 1.0)
    return EPS0 * (1.0 + (ALPHA0_RAD / max(alpha, 1e-12)) ** 2)


def apparent_contrast(c0: float, range_nm: float, visibility_nm: float) -> float:
    return c0 * math.exp(-KOSCHMIEDER * range_nm / max(visibility_nm, 1e-3))


def inherent_contrast(kind: str, reference_range_nm: float,
                      reference_visibility_nm: float) -> float:
    """C0 such that the day/clear/calm threshold crossing is at the reference."""
    height = TARGET_HEIGHT_M[kind]
    return (threshold(height, reference_range_nm)
            * math.exp(KOSCHMIEDER * reference_range_nm / reference_visibility_nm))


def night_multiplier(fraction: float, reference_range_nm: float,
                     reference_visibility_nm: float) -> float:
    """Threshold multiplier giving a surface night range = fraction x day."""
    height = TARGET_HEIGHT_M["SURFACE"]
    c0 = inherent_contrast("SURFACE", reference_range_nm, reference_visibility_nm)
    night_range = fraction * reference_range_nm
    return (apparent_contrast(c0, night_range, reference_visibility_nm)
            / threshold(height, night_range))


def moon_illumination(lunar_age_days: float) -> float:
    """Illuminated fraction of the lunar disc (0 new, 1 full)."""
    return 0.5 * (1.0 - math.cos(2.0 * math.pi * lunar_age_days / SYNODIC_MONTH_D))


class LookoutModel:
    """Anchored visual model; construct once per world visibility maximum."""

    def __init__(self, reference_ranges: dict, reference_visibility_nm: float):
        self.reference_visibility_nm = float(reference_visibility_nm)
        self.c0 = {kind: inherent_contrast(kind, rng, reference_visibility_nm)
                   for kind, rng in reference_ranges.items()}
        surface = reference_ranges["SURFACE"]
        self.night_new = night_multiplier(
            NIGHT_RANGE_NEW_MOON, surface, reference_visibility_nm)
        self.night_full = night_multiplier(
            NIGHT_RANGE_FULL_MOON, surface, reference_visibility_nm)

    def night_factor(self, illumination: float) -> float:
        """Log-interpolated threshold multiplier between new and full moon."""
        f = max(0.0, min(1.0, illumination))
        return self.night_new ** (1.0 - f) * self.night_full ** f

    def margin(self, kind: str, range_nm: float, *, visibility_nm: float,
               night: bool, illumination: float, sea_state: float,
               altitude_m: float | None = None, detail: float = 1.0,
               eye_m: float = LOOKOUT_EYE_HEIGHT_M) -> float:
        """Apparent contrast over threshold (>= 1 means seen).

        ``detail`` > 1 asks for a finer resolved feature (Johnson cycles
        over relative target size): the resolved height shrinks by that
        factor, the horizon still belongs to the whole target.  ``eye_m``
        is the observer's eye height (the frigate's lookout by default, a
        periscope sits just above the water)."""
        height = TARGET_HEIGHT_M[kind]
        top = height if altitude_m is None else max(height, altitude_m)
        if range_nm > optical_horizon_nm(eye_m, top):
            return 0.0
        eps = threshold(height / max(detail, 1e-6), range_nm)
        if kind not in ("FLG", "LAND"):
            # Aircraft are seen against the sky, land above the horizon,
            # not against the whitecaps.
            eps *= 1.0 + SEA_CLUTTER_PER_STATE * max(0.0, sea_state)
        if night:
            eps *= self.night_factor(illumination)
        return apparent_contrast(self.c0[kind], range_nm, visibility_nm) / eps

    def sighting_range_nm(self, kind: str, *, visibility_nm: float, night: bool,
                          illumination: float, sea_state: float,
                          eye_m: float = LOOKOUT_EYE_HEIGHT_M) -> float:
        """Largest range at which ``margin`` still reaches 1 (bisection; for
        displays).  The margin falls monotonically with range and is cut at
        the geometric horizon, so the result is at most that horizon."""
        conditions = dict(visibility_nm=visibility_nm, night=night,
                          illumination=illumination, sea_state=sea_state, eye_m=eye_m)
        high = optical_horizon_nm(eye_m, TARGET_HEIGHT_M[kind])
        if self.margin(kind, high, **conditions) >= 1.0:
            return high
        low = 0.0
        for _ in range(40):
            mid = 0.5 * (low + high)
            if self.margin(kind, mid, **conditions) >= 1.0:
                low = mid
            else:
                high = mid
        return low
