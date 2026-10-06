"""Torpedo physics helpers (pure functions).

* Energy: the battery/fuel store is expressed in "cruise seconds" - the
  catalog range at catalog speed.  Propulsive power grows with the cube of
  speed, so running slower (a throttled turn) stretches the store.  When it
  is empty the motor stops and the weapon coasts down against drag
  (dv/dt = -k v^2) until it sinks/self-destructs.
* Turning: a constant minimum turning radius, so the turn rate is
  proportional to speed.
* Depth: fins give a pitch/depth acceleration proportional to dynamic
  pressure; the depth rate follows a proportional command at that
  acceleration limit (small overshoot emerges).
* Warhead: a proximity fuze fires at closest approach inside its radius;
  damage follows the underwater-explosion shock factor SF = sqrt(W) / R.
* Wire: finite payout on both spools, and tension breaks the wire when the
  launching ship runs too fast or turns too hard for long enough.
"""

from __future__ import annotations

import math

COAST_DRAG_K = 0.45            # 1/s in dv/dt = -k v^2 (v as cruise fraction)
COAST_SINK_FRACTION = 0.3      # below this speed fraction the weapon is lost
DEPTH_ACCEL_MPS2 = 12.0        # at cruise speed (calibrated: 1.0.0 dive profile)
DEPTH_GAIN_PER_S = 0.8
DEPTH_RATE_MAX_MPS = 10.0
DEPTH_SUBSTEP_S = 0.1
WARHEAD_KG = 250.0
SF_LETHAL_SUBMARINE = 0.35
SF_LETHAL_SURFACE = 1.0
SURFACE_DAMAGE_CAP = 60.0
WIRE_TORPEDO_SPOOL_FACTOR = 1.25   # torpedo spool vs. catalog range
WIRE_SHIP_SPOOL_NM = 5.0
WIRE_MAX_SHIP_KN = 20.0
WIRE_MAX_SHIP_YAW_DEG_S = 1.5
WIRE_TENSION_BREAK_S = 5.0
RUNNING_NOISE_BAND_HZ = 1600.0


def energy_budget_s(range_nm: float, speed_kn: float) -> float:
    """Store in cruise seconds: catalog range at catalog speed."""
    return range_nm / max(speed_kn / 3600.0, 1e-9)


def energy_rate(speed_fraction: float) -> float:
    """Cruise-seconds consumed per second at a fraction of cruise speed."""
    return max(0.0, speed_fraction) ** 3


def coast_step(fraction: float, dt: float) -> float:
    """Exact coast-down of the speed fraction under quadratic drag."""
    return fraction / (1.0 + COAST_DRAG_K * fraction * dt)


def turn_rate_deg_s(base_rate: float, speed_fraction: float) -> float:
    """Constant turning radius: rate scales with speed."""
    return base_rate * max(0.0, min(1.0, speed_fraction))


def depth_step(depth: float, rate: float, target: float, speed_fraction: float,
               dt: float, max_rate: float = DEPTH_RATE_MAX_MPS) -> tuple[float, float]:
    """Advance depth with a fin-limited vertical acceleration (substepped
    to at most DEPTH_SUBSTEP_S so long frames integrate faithfully)."""
    accel = DEPTH_ACCEL_MPS2 * max(0.05, speed_fraction) ** 2
    steps = min(1000, max(1, math.ceil(dt / DEPTH_SUBSTEP_S - 1e-9)))
    h = dt / steps
    for _ in range(steps):
        desired = max(-max_rate, min(max_rate, DEPTH_GAIN_PER_S * (target - depth)))
        change = max(-accel * h, min(accel * h, desired - rate))
        new_rate = rate + change
        depth = max(0.0, depth + 0.5 * (rate + new_rate) * h)
        rate = new_rate
    return depth, rate


def shock_factor(charge_kg: float, slant_m: float) -> float:
    return math.sqrt(charge_kg) / max(slant_m, 1.0)


def submarine_damage(slant_m: float) -> float:
    return min(100.0, 100.0 * shock_factor(WARHEAD_KG, slant_m)
               / SF_LETHAL_SUBMARINE)


def surface_damage(slant_m: float) -> float:
    return min(SURFACE_DAMAGE_CAP, 100.0 * shock_factor(WARHEAD_KG, slant_m)
               / SF_LETHAL_SURFACE)

# --- appended to src/physics/torpedo_dyn.py (plan 1.3, phase 4) ---------

# Terminal search patterns a lightweight torpedo runs once its seeker is
# enabled and has not acquired: the classic serpentine about the datum
# course, a circle about the enable point, or an expanding helix.  Gameplay
# tuning values, not real weapon doctrine.
SEARCH_PATTERNS = ("snake", "circle", "helix")
SNAKE_AMPLITUDE_DEG = 15.0
SNAKE_DEPTH_WOBBLE_M = 8.0
CIRCLE_RADIUS_NM = 0.4
HELIX_START_RADIUS_NM = 0.15
HELIX_STEP_NM = 0.15            # radius growth per full turn
HELIX_MAX_RADIUS_NM = 1.0
ENABLE_RANGE_MIN_NM = 0.6
ENABLE_RANGE_MAX_NM = 3.0
ENABLE_RANGE_STEP_NM = 0.2
SALVO_SPREAD_DEG = 8.0
SALVO_SIZES = (1, 2)
# A crewed submarine's torpedo: the seeker switches on 3 NM before its datum
# unless the weapons officer sets a later point, and runs straight on an
# enabled search unless the crew orders a pattern (the 1.3.140 behaviour is
# straight at 3 NM, which also every AI shot keeps).
BOAT_SEARCH_PATTERNS = ("straight",) + SEARCH_PATTERNS
BOAT_ENABLE_DEFAULT_NM = 3.0


def snake_offset(phase: float) -> tuple[float, float]:
    """(course offset deg, depth wobble m) of the serpentine at ``phase``."""
    return (SNAKE_AMPLITUDE_DEG * math.sin(phase),
            SNAKE_DEPTH_WOBBLE_M * math.sin(phase * 0.7))


def turn_rate_for_radius(speed_nm_per_s: float, radius_nm: float) -> float:
    """Yaw rate (deg/s) that holds a circle of ``radius_nm`` at that speed."""
    return math.degrees(max(0.0, speed_nm_per_s) / max(0.01, radius_nm))


def helix_radius_nm(turns: float) -> float:
    """Radius after ``turns`` full circles: grows by a fixed step per turn."""
    return min(HELIX_MAX_RADIUS_NM, HELIX_START_RADIUS_NM + HELIX_STEP_NM * max(0.0, turns))


def pattern_turn_deg_s(pattern: str, speed_nm_per_s: float, turns_done: float) -> float:
    """Constant-turn command for the circle and helix patterns (deg/s)."""
    if pattern == "circle":
        return turn_rate_for_radius(speed_nm_per_s, CIRCLE_RADIUS_NM)
    if pattern == "helix":
        return turn_rate_for_radius(speed_nm_per_s, helix_radius_nm(turns_done))
    return 0.0


def spread_courses(course_deg: float, count: int,
                   spread_deg: float = SALVO_SPREAD_DEG) -> tuple[float, ...]:
    """Launch courses of a salvo: one on the line, two at +/- the spread."""
    if count <= 1:
        return (course_deg % 360.0,)
    return ((course_deg - spread_deg) % 360.0, (course_deg + spread_deg) % 360.0)


def rotate_datum(origin_x: float, origin_y: float, datum_x: float, datum_y: float,
                 angle_deg: float) -> tuple[float, float]:
    """Turn a datum about the launching ship by ``angle_deg`` (nautical sense)."""
    angle = math.radians(angle_deg)
    dx, dy = datum_x - origin_x, datum_y - origin_y
    return (origin_x + dx * math.cos(angle) - dy * math.sin(angle),
            origin_y + dx * math.sin(angle) + dy * math.cos(angle))


def quantized_enable_nm(value: float) -> float:
    """Snap an enable point to the 0.2 NM grid inside its bounds."""
    steps = round((float(value) - ENABLE_RANGE_MIN_NM) / ENABLE_RANGE_STEP_NM)
    snapped = ENABLE_RANGE_MIN_NM + steps * ENABLE_RANGE_STEP_NM
    return round(min(ENABLE_RANGE_MAX_NM, max(ENABLE_RANGE_MIN_NM, snapped)), 3)


# --- Homing seeker (1.3.215) --------------------------------------------------
# The seeker looks ahead in a cone about the weapon's heading and inside a
# depth gate about its own depth; a contact is acquired when the better of its
# passive level and its active echo beats the seeker's self noise, which grows
# as 60 log v with the weapon's speed.  So the weapon searches at a quiet
# search speed and sprints once it holds a target.  A held target is kept in a
# wider cone and with a margin below the acquisition threshold.
SEEKER_CONE_HALF_DEG = 45.0
SEEKER_HOLD_CONE_HALF_DEG = 60.0
SEEKER_DEPTH_GATE_M = 150.0
SEEKER_SEARCH_FRACTION = 0.7
SEEKER_PASSIVE_DT_DB = 15.0
SEEKER_HOLD_MARGIN_DB = 10.0
# Active acquisition range against a hull echo at full speed, and the
# seeker's maximum range (own weapons; the hostile boats' heavier weapon).
SEEKER_ACTIVE_NM = {"own": 1.2, "enemy": 2.0}
SEEKER_MAX_NM = {"own": 2.0, "enemy": 3.0}


def self_noise_db(speed_fraction: float) -> float:
    """Seeker self noise relative to full speed (flow and propulsor)."""
    return 60.0 * math.log10(max(speed_fraction, 0.05))


def seeker_excess_db(passive_level_db: float, distance_nm: float,
                     depth_gap_m: float, stationary: bool, speed_fraction: float,
                     active_nm: float, no_doppler_db: float) -> float:
    """Signal excess of a contact at the seeker: the better of the passive
    level (relative dB, see ``torpedo.seeker_level_db``) and the active echo
    (two-way spreading, calibrated to ``active_nm`` at full speed)."""
    noise = self_noise_db(speed_fraction)
    passive = passive_level_db - noise - SEEKER_PASSIVE_DT_DB
    active = (40.0 * math.log10(active_nm / max(distance_nm, 0.01))
              - depth_gap_m / 10.0 - (no_doppler_db if stationary else 0.0) - noise)
    return max(passive, active)


def in_seeker_cone(heading_deg: float, bearing_deg: float, half_deg: float) -> bool:
    return abs((bearing_deg - heading_deg + 180.0) % 360.0 - 180.0) <= half_deg
