"""Close-in weapon system fire control (pure helpers).

* The mount slews at a finite rate; a burst is fired only once the barrel is
  on the predicted bearing.
* Rounds need their time of flight to reach the aim point; a missile that
  impacts before the burst arrives cannot be stopped by it.
* Hit probability per round follows the circular-normal miss distance at
  the target: gun dispersion (angular, grows with range), the prediction
  error of the fire-control track (velocity error x time of flight) and
  extra angle noise while the target jams.  A round that hits kills with
  the profiled kill probability; a burst kills with 1 - (1 - p_hit pk)^n.

``LETHAL_AREA_M2`` is the effective area around the aim point inside which a
round defeats the missile (airframe, seeker and warhead initiation); it is
calibrated so that a single sea-skimmer leaks through CIWS at the 1.0.0 rate
(calibration section ``air``).  Most kills therefore happen in the last few
hundred metres, where dispersion and prediction error are small.
"""

from __future__ import annotations

import math

SLEW_DEG_S = 115.0
ON_TARGET_DEG = 2.0
ROUND_MEAN_SPEED_MPS = 950.0
DISPERSION_MRAD = 2.0
TRACK_VELOCITY_ERROR_MPS = 8.0
JAMMING_ANGLE_NOISE_MRAD = 3.0
LETHAL_AREA_M2 = 55.0


def slew(mount_deg: float, bearing_deg: float, dt: float) -> float:
    diff = (bearing_deg - mount_deg + 180.0) % 360.0 - 180.0
    step = SLEW_DEG_S * dt
    return (mount_deg + max(-step, min(step, diff))) % 360.0


def on_target(mount_deg: float, bearing_deg: float) -> bool:
    return abs((bearing_deg - mount_deg + 180.0) % 360.0 - 180.0) <= ON_TARGET_DEG


def time_of_flight_s(range_nm: float) -> float:
    return max(0.0, range_nm) * 1852.0 / ROUND_MEAN_SPEED_MPS


def burst_kill_probability(range_nm: float, rounds: int, jamming: bool,
                           kill_given_hit: float = 1.0) -> float:
    r = max(range_nm, 0.0) * 1852.0
    angular = DISPERSION_MRAD ** 2 + (JAMMING_ANGLE_NOISE_MRAD ** 2 if jamming else 0.0)
    sigma2 = (angular * 1e-6 * r * r
              + (TRACK_VELOCITY_ERROR_MPS * time_of_flight_s(range_nm)) ** 2)
    p_hit = min(1.0, LETHAL_AREA_M2 / (2.0 * math.pi * max(sigma2, 1e-6)))
    p_round = p_hit * max(0.0, min(1.0, kill_given_hit))
    return 1.0 - (1.0 - p_round) ** max(0, int(rounds))
