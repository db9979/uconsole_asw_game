"""Radar detection physics (pure functions).

* Radar equation: the signal-to-noise ratio of a point target falls with
  R^-4 and rises with its cross-section.  It is anchored so that the
  nominal instrumented range of each radar is the range at which a
  reference (broadside) target is detected with Pd = 0.5 in a calm sea.
* Swerling-1 target fluctuation with a cell-averaging CFAR detector:
  Pd = (1 + T / (1 + SINR))^-N with T = Pfa^(-1/N) - 1 (exact closed form
  for N reference cells).  The CFAR adapts its threshold to the local
  interference, so clutter and jamming act as extra noise.
* Sea clutter (GIT-type): the clutter-to-noise ratio of a resolution cell
  grows about 3 dB per sea state and falls with R^-3 (illuminated area ~ R,
  two-way spreading ~ R^-4).  Air search uses MTI and suffers less.
* Rain: two-way specific attenuation proportional to the rain intensity.
* Self-screening noise jammer: jammer-to-noise ratio ~ R^-2 (one-way), so
  the skin return burns through inside a finite range; the jammer power is
  solved from the profiled burn-through range.

The legacy range multipliers (weather 25 %/10 %, rain 10 %/20 %, aspect
0.55..1) are reproduced at their anchor points, which the calibration
harness checks.
"""

from __future__ import annotations

import math
from functools import lru_cache

from src.core import config

PFA = 1.0e-6
CFAR_CELLS = 16
CFAR_T = PFA ** (-1.0 / CFAR_CELLS) - 1.0
# SINR (linear) for Pd = 0.5 with this CFAR.
SNR_50 = CFAR_T / (2.0 ** (1.0 / CFAR_CELLS) - 1.0) - 1.0
NM_KM = 1.852

# Legacy anchor points (range fraction lost at full severity: sea state 6,
# rain intensity 1.0).
SURFACE_CLUTTER_ANCHOR = config.RADAR_SURFACE_WEATHER_LOSS
AIR_CLUTTER_ANCHOR = config.RADAR_AIR_WEATHER_LOSS
SURFACE_RAIN_ANCHOR = config.RADAR_RAIN_SURFACE_LOSS
AIR_RAIN_ANCHOR = config.RADAR_RAIN_AIR_LOSS
CLUTTER_DB_PER_SEA_STATE = 3.0
CLUTTER_REFERENCE_SEA_STATE = 6.0


def pd_from_sinr(sinr: float) -> float:
    """Swerling-1 detection probability behind a CA-CFAR detector."""
    if not math.isfinite(sinr) or sinr <= 0.0:
        return 0.0
    return (1.0 + CFAR_T / (1.0 + sinr)) ** (-CFAR_CELLS)


def snr(range_nm: float, reference_range_nm: float, rcs_factor: float = 1.0) -> float:
    """Signal-to-noise ratio (linear) from the anchored radar equation."""
    range_nm = max(range_nm, 1e-3)
    return (SNR_50 * max(rcs_factor, 0.0)
            * (reference_range_nm / range_nm) ** 4)


def _clutter_coefficient(anchor_loss: float) -> float:
    # At the anchor range fraction x the SINR equals SNR_50:
    # x^-4 / (1 + c x^-3) = 1  =>  c = (x^-4 - 1) x^3.
    x = 1.0 - anchor_loss
    return (x ** -4 - 1.0) * x ** 3


SURFACE_CNR_REF = _clutter_coefficient(SURFACE_CLUTTER_ANCHOR)
AIR_CNR_REF = _clutter_coefficient(AIR_CLUTTER_ANCHOR)


def clutter_to_noise(domain: str, sea_state: float, range_nm: float,
                     reference_range_nm: float) -> float:
    """Sea-clutter CNR (linear) in the target's resolution cell."""
    ref = SURFACE_CNR_REF if domain == "surface" else AIR_CNR_REF
    level = ref * 10.0 ** (CLUTTER_DB_PER_SEA_STATE
                           * (max(0.0, sea_state) - CLUTTER_REFERENCE_SEA_STATE) / 10.0)
    return level * (reference_range_nm / max(range_nm, 1e-3)) ** 3


def _rain_coefficient(anchor_loss: float, reference_range_nm: float) -> float:
    # Two-way attenuation 2 * gamma * R_km equals the SNR margin at the
    # anchor range fraction x: 40 log10(1/x) dB.
    x = 1.0 - anchor_loss
    return 40.0 * math.log10(1.0 / x) / (2.0 * x * reference_range_nm * NM_KM)


def rain_loss_db(domain: str, rain_intensity: float, range_nm: float,
                 reference_range_nm: float) -> float:
    anchor = SURFACE_RAIN_ANCHOR if domain == "surface" else AIR_RAIN_ANCHOR
    gamma = _rain_coefficient(anchor, reference_range_nm) * max(0.0, rain_intensity)
    return 2.0 * gamma * max(range_nm, 0.0) * NM_KM


def jammer_to_noise(range_nm: float, burn_through_nm: float,
                    skin_snr_at_burn_through: float) -> float:
    """Self-screening jammer JNR (linear), R^-2, solved from burn-through."""
    jnr_bt = max(0.0, skin_snr_at_burn_through / SNR_50 - 1.0)
    return jnr_bt * (burn_through_nm / max(range_nm, 1e-3)) ** 2


def sinr(range_nm: float, reference_range_nm: float, *, rcs_factor: float = 1.0,
         domain: str = "surface", sea_state: float = 0.0,
         rain_intensity: float = 0.0, capability: float = 1.0,
         jnr: float = 0.0) -> float:
    """Signal to interference-plus-noise ratio for one look."""
    signal = snr(range_nm, reference_range_nm * max(capability, 1e-3), rcs_factor)
    signal *= 10.0 ** (-rain_loss_db(domain, rain_intensity, range_nm,
                                     reference_range_nm) / 10.0)
    cnr = clutter_to_noise(domain, sea_state, range_nm, reference_range_nm)
    return signal / (1.0 + cnr + max(0.0, jnr))


def detection_range_nm(reference_range_nm: float, **kwargs) -> float:
    """Range at which Pd falls to 0.5 (bisection; for displays and tests)."""
    low, high = 1e-3, reference_range_nm * 4.0
    for _ in range(60):
        mid = 0.5 * (low + high)
        if sinr(mid, reference_range_nm, **kwargs) >= SNR_50:
            low = mid
        else:
            high = mid
    return low


@lru_cache(maxsize=128)
def _detection_fraction(domain: str, sea_state: float, rain: float,
                        capability: float, reference_range_nm: float,
                        rcs_factor: float = 1.0) -> float:
    return detection_range_nm(reference_range_nm, domain=domain,
                              sea_state=sea_state, rain_intensity=rain,
                              capability=capability,
                              rcs_factor=rcs_factor) / reference_range_nm


def detection_fraction(domain: str, sea_state: float, rain_intensity: float,
                       reference_range_nm: float, capability: float = 1.0,
                       rcs_factor: float = 1.0) -> float:
    """Pd = 0.5 range as a fraction of the calm-sea reference.  Conditions
    are quantized before the (pure, bounded) cache so the result depends
    only on the arguments, never on call order.  ``rcs_factor`` scales the
    target's cross-section (a raised submarine mast is 0.01)."""
    return _detection_fraction(domain, round(float(sea_state), 2),
                               round(float(rain_intensity), 3),
                               round(float(capability), 3),
                               float(reference_range_nm),
                               round(float(rcs_factor), 4))


def swept(bearing_deg: float, scan_end_deg: float, swept_deg: float) -> bool:
    """True when the beam passed ``bearing_deg`` during the last
    ``swept_deg`` degrees of rotation that ended at ``scan_end_deg``."""
    if swept_deg >= 360.0:
        return True
    if swept_deg <= 0.0:
        return False
    return (scan_end_deg - bearing_deg) % 360.0 < swept_deg
