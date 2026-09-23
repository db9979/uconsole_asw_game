"""Anti-ship missile flight physics (pure helpers).

Point-mass 3-DOF model: horizontal position/heading, altitude, speed.

* Boost: a ship- or air-launched round accelerates from its launch speed to
  the profiled cruise speed at the booster acceleration; the sustainer then
  holds cruise speed (thrust = drag).  Fuel is the profiled range.
* Altitude: climb/descent to the sea-skimming cruise height at a limited
  vertical speed, dropping to the terminal height inside the terminal range.
  The missile's own height sets its radar horizon.
* Mid-course: inertial flight towards the launch datum with the profiled
  (gentle, waypoint) turn rate.
* Terminal: the active seeker must see the target inside its field of view
  for the lock delay; locked, the missile flies proportional navigation
  (commanded turn rate = N x line-of-sight rate) limited by its lateral g.
"""

from __future__ import annotations

import math

G = 9.80665
MPS_PER_KN = 1852.0 / 3600.0
BOOST_ACCEL_MPS2 = 60.0
CRUISE_ALTITUDE_M = 20.0
TERMINAL_ALTITUDE_M = 5.0
TERMINAL_RANGE_NM = 5.0
VERTICAL_SPEED_MPS = 30.0
PN_GAIN = 4.0
LATERAL_G_LIMIT = 15.0
SEEKER_FOV_HALF_DEG = 30.0
SEEKER_LOCK_S = 1.5
GUIDANCE_SUBSTEP_S = 0.1


def boost_time_s(launch_kn: float, cruise_kn: float) -> float:
    return max(0.0, cruise_kn - launch_kn) * MPS_PER_KN / BOOST_ACCEL_MPS2


def speed_step(speed_kn: float, cruise_kn: float, dt: float) -> float:
    if speed_kn >= cruise_kn:
        return speed_kn
    return min(cruise_kn, speed_kn + BOOST_ACCEL_MPS2 * dt / MPS_PER_KN)


def altitude_step(altitude_m: float, target_m: float, dt: float) -> float:
    step = VERTICAL_SPEED_MPS * dt
    return altitude_m + max(-step, min(step, target_m - altitude_m))


def commanded_altitude_m(distance_to_target_nm: float) -> float:
    return (TERMINAL_ALTITUDE_M if distance_to_target_nm <= TERMINAL_RANGE_NM
            else CRUISE_ALTITUDE_M)


def max_turn_rate_deg_s(speed_kn: float) -> float:
    """Lateral-g limit: omega = a / v."""
    speed = max(speed_kn * MPS_PER_KN, 1.0)
    return math.degrees(LATERAL_G_LIMIT * G / speed)


def in_field_of_view(heading_deg: float, bearing_deg: float) -> bool:
    diff = (bearing_deg - heading_deg + 180.0) % 360.0 - 180.0
    return abs(diff) <= SEEKER_FOV_HALF_DEG


def pn_turn_rate_deg_s(los_deg: float, los_prev_deg: float | None, dt: float,
                       speed_kn: float) -> float:
    """Proportional navigation with the airframe's lateral-g limit."""
    if los_prev_deg is None or dt <= 0.0:
        return 0.0
    los_rate = ((los_deg - los_prev_deg + 180.0) % 360.0 - 180.0) / dt
    limit = max_turn_rate_deg_s(speed_kn)
    return max(-limit, min(limit, PN_GAIN * los_rate))


def flight_time_bound_s(range_nm: float, cruise_kn: float) -> float:
    """Upper bound of the powered flight: range at cruise plus the time lost
    accelerating from rest."""
    cruise = max(cruise_kn * MPS_PER_KN, 1e-6)
    return range_nm * 1852.0 / cruise + cruise / (2.0 * BOOST_ACCEL_MPS2)
