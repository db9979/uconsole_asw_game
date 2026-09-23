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
