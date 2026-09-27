"""Magnetic anomaly detection from the helicopter (plan 1.3, phase 6).

Pure functions: a MAD pass at 30 m over a submerged hull gives a detection
whose probability falls with the slant distance.  Gameplay tuning values,
not a real sensor model; the draw is stateless (``detrand``) so a save
needs no stream and the result never depends on call order.
"""

import math

from src.core import detrand

MAD_ALTITUDE_M = 30.0        # the MAD run's height above the sea
MAD_SURE_SLANT_M = 250.0     # up to here: MAD_SURE_PROBABILITY
MAD_MAX_SLANT_M = 400.0      # beyond: nothing
MAD_SURE_PROBABILITY = 0.9
MAD_FIX_UNCERTAINTY_NM = 0.3
MAD_FIX_QUALITY = 0.7
MAD_SPEED_KN = 90.0          # the run is flown slow and low


def slant_m(horizontal_nm: float, depth_m: float,
            altitude_m: float = MAD_ALTITUDE_M) -> float:
    """Straight-line distance sensor to hull (m) for a horizontal offset in NM."""
    return math.hypot(max(0.0, horizontal_nm) * 1852.0,
                      max(0.0, depth_m) + max(0.0, altitude_m))


def detection_probability(slant: float) -> float:
    """0.9 inside the sure range, linear to zero at the maximum slant."""
    if slant <= MAD_SURE_SLANT_M:
        return MAD_SURE_PROBABILITY
    if slant >= MAD_MAX_SLANT_M:
        return 0.0
    return MAD_SURE_PROBABILITY * (MAD_MAX_SLANT_M - slant) / (
        MAD_MAX_SLANT_M - MAD_SURE_SLANT_M)


def detects(seed: int, target_id: int, tick: int, slant: float) -> bool:
    """One stateless Bernoulli draw per target and sensor tick."""
    probability = detection_probability(slant)
    return probability > 0.0 and detrand.u01(seed, "mad", target_id, tick) < probability
