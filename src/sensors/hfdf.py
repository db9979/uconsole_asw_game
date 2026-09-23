"""HF propagation for the HFDF receiver (pure functions).

* A submarine calls a distant shore station and picks the optimum working
  frequency for that path: OWF = 0.85 x MUF, MUF = foF2 sqrt(1 + (d/2h)^2)
  (flat-Earth single hop off the F2 layer, virtual height h).  foF2 follows
  the day/night ionosphere.
* Ground wave over sea water: the usable range falls with frequency.  It is
  anchored so that a typical 15 MHz call is heard to the 1.0.0 HFDF range.
* Sky wave returns to the sea surface only beyond the skip distance
  d_skip = 2h sqrt((f/foF2)^2 - 1); sky-wave bearings suffer ionospheric
  tilt errors and are about twice as uncertain as ground-wave bearings.

The measured carrier frequency and the propagation mode are observable; the
receiver never learns the true range from them.
"""

from __future__ import annotations

import math

from src.core import detrand

F2_HEIGHT_KM = 300.0
FOF2_DAY_MHZ = 8.0
FOF2_NIGHT_MHZ = 4.5
OWF_FRACTION = 0.85
SHORE_PATH_KM = (800.0, 2500.0)
GROUND_WAVE_REF_MHZ = 15.0
GROUND_WAVE_EXPONENT = 0.7
SKY_WAVE_BEARING_FACTOR = 2.0
MIN_FREQUENCY_MHZ = 2.0
MAX_FREQUENCY_MHZ = 30.0
NM_KM = 1.852


def fof2_mhz(night: bool) -> float:
    return FOF2_NIGHT_MHZ if night else FOF2_DAY_MHZ


def muf_mhz(path_km: float, night: bool) -> float:
    return fof2_mhz(night) * math.sqrt(1.0 + (path_km / (2.0 * F2_HEIGHT_KM)) ** 2)


def transmit_frequency_mhz(sensor_seed: int, window: int, night: bool) -> float:
    """Frequency a boat picks for one call (deterministic per call window)."""
    path = detrand.uniform(*SHORE_PATH_KM, sensor_seed, "hf-path", window)
    return max(MIN_FREQUENCY_MHZ,
               min(MAX_FREQUENCY_MHZ, OWF_FRACTION * muf_mhz(path, night)))


def ground_wave_range_nm(frequency_mhz: float, reference_range_nm: float) -> float:
    return reference_range_nm * (GROUND_WAVE_REF_MHZ
                                 / max(frequency_mhz, 0.1)) ** GROUND_WAVE_EXPONENT


def skip_distance_nm(frequency_mhz: float, night: bool) -> float:
    ratio = frequency_mhz / fof2_mhz(night)
    if ratio <= 1.0:
        return 0.0
    return 2.0 * F2_HEIGHT_KM * math.sqrt(ratio * ratio - 1.0) / NM_KM


def propagation_mode(distance_nm: float, frequency_mhz: float, night: bool,
                     reference_range_nm: float) -> str | None:
    """'GROUND', 'SKY' or None when the call is not heard at this distance."""
    if distance_nm <= ground_wave_range_nm(frequency_mhz, reference_range_nm):
        return "GROUND"
    if distance_nm >= skip_distance_nm(frequency_mhz, night):
        return "SKY"
    return None
