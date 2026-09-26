"""Submarine and hostile-hull physics helpers (pure functions).

* Hydroplanes produce lift proportional to dynamic pressure, so the
  achievable depth-change rate falls with speed squared; below a few knots the
  boat relies on slow trim/ballast changes.
* Propeller cavitation onset rises with the static pressure at the screw:
  v_c(z) = v_c0 * sqrt(1 + z / 10.3 m).
* Radiated source level grows with speed (machinery/flow noise ~40 log v
  below cavitation) and jumps when the screw cavitates.
* Operating below test depth accumulates pressure-hull fatigue; the crush
  depth has a safety factor of 1.5.
* A bounded high-pressure-air store allows one emergency blow.
* Surface ships lose speed in waves (added resistance ~ Hs^2 B^2 / L,
  relative to their own resistance at top speed).
"""

from __future__ import annotations

import math

PLANE_REFERENCE_KN = 4.0
PLANE_MIN_AUTHORITY = 0.25
CAVITATION_PRESSURE_HEAD_M = 10.3
SPEED_SOURCE_LAW_DB = 40.0
# Lower bound: auxiliary machinery (pumps, generators) keeps radiating when
# the boat hovers; the speed law only governs above that floor.
SOURCE_SPEED_DB_LIMITS = (-6.0, 18.0)
CAVITATION_JUMP_DB = 8.0
SUBMARINE_REFERENCE_SPEED_KN = 6.0
TEST_DEPTH_FATIGUE_START = 0.9
FATIGUE_PER_S_AT_TEST = 1.0 / 1800.0     # 30 min at 10 % beyond test depth
CRUSH_SAFETY_FACTOR = 1.5
EMERGENCY_BLOW_RATE_MPS = 4.0
EMERGENCY_BLOW_DAMAGE = 60.0             # damage level that triggers a blow
LAUNCH_TRANSIENT_S = 8.0
LAUNCH_TRANSIENT_DB = 12.0


def plane_authority(speed_kn: float) -> float:
    """Fraction of the design depth rate the hydroplanes can produce."""
    return min(1.0, max(PLANE_MIN_AUTHORITY,
                        (max(speed_kn, 0.0) / PLANE_REFERENCE_KN) ** 2))


def cavitation_speed_kn(surface_onset_kn: float, depth_m: float) -> float:
    return surface_onset_kn * math.sqrt(1.0 + max(depth_m, 0.0)
                                        / CAVITATION_PRESSURE_HEAD_M)


def source_speed_db(speed_kn: float, reference_kn: float,
                    cavitating: bool = False) -> float:
    """Source-level change relative to the reference operating speed."""
    low, high = SOURCE_SPEED_DB_LIMITS
    level = SPEED_SOURCE_LAW_DB * math.log10(
        max(speed_kn, 1.0) / max(reference_kn, 1.0))
    level = min(high, max(low, level))
    return level + (CAVITATION_JUMP_DB if cavitating else 0.0)


def crush_depth_m(test_depth_m: float) -> float:
    return test_depth_m * CRUSH_SAFETY_FACTOR


def fatigue_rate_per_s(depth_m: float, test_depth_m: float) -> float:
    ratio = depth_m / max(test_depth_m, 1.0)
    if ratio <= TEST_DEPTH_FATIGUE_START:
        return 0.0
    return FATIGUE_PER_S_AT_TEST * (ratio - TEST_DEPTH_FATIGUE_START) / 0.2


def wave_speed_fraction(sea_state: float, length_m: float, beam_m: float) -> float:
    """Top-speed fraction retained in waves (sustained-power equilibrium).

    Added resistance scales with Hs^2 B^2 / L; relative to a hull's own
    resistance at top speed (~ L^2 for similar forms) smaller ships lose
    proportionally more."""
    from src.physics.ship_dynamics import SEA_STATE_HS_M

    index = max(0.0, min(6.0, sea_state))
    low = int(index)
    high = min(6, low + 1)
    hs = SEA_STATE_HS_M[low] + (SEA_STATE_HS_M[high] - SEA_STATE_HS_M[low]) * (index - low)
    length = max(length_m, 20.0)
    beam = max(beam_m, length / 9.0)
    relative = 0.015 * hs * hs * (beam / 14.0) ** 2 * (118.0 / length) ** 3
    return 1.0 / math.sqrt(1.0 + relative)
