"""Surface-ship hydrodynamics: surge, propeller, cavitation, steering,
seakeeping, sinkage and wake.

The model is force based and calibrated at load time against the 1.0.0
gameplay references (``src/core/config.py``): top speed, the time to reach
90 % of FULL, the stop distance, the steady turn at FULL and the cavitation
onset.  Physical inputs (hull, propeller, stability) come from
``data/loadouts/ownship_hull.json``.

Surge integrates exactly: with the propeller speed held over a step the
equation of motion ``M dv/dt = a0 - a1 v - a2 v^2`` is a constant-coefficient
Riccati equation with a closed-form solution, so one long step equals many
short ones.
"""

from __future__ import annotations

import functools
import json
import math
from dataclasses import dataclass
from importlib import resources

from src.core import config, detrand

RHO_SEA = 1025.0
G = 9.80665
P_ATM = 101_325.0
P_VAPOUR = 2_340.0
KN = 1852.0 / 3600.0            # m/s per knot
# Significant wave height (m) by sea state 0..6.
SEA_STATE_HS_M = (0.0, 0.1, 0.5, 1.25, 2.5, 4.0, 6.0)
WAVE_COMPONENTS = 8
# Added resistance in waves: R_aw = c * rho * g * Hs^2 * B^2 / L.
ADDED_RESISTANCE_COEFF = 0.6

_HULL_FIELDS = {
    "version", "note", "displacement_t", "length_m", "beam_m", "draft_m",
    "block_coefficient", "waterplane_coefficient", "max_brake_power_kw",
    "propulsive_efficiency", "propeller_diameter_m",
    "propeller_zero_thrust_advance_ratio", "flank_advance_ratio",
    "shaft_immersion_m", "idle_rpm", "metacentric_height_m",
    "turn_heel_lever_m", "roll_period_s", "roll_damping_ratio",
    "stabilizer_damping_ratio", "stabilizer_full_speed_kn", "pitch_period_s",
    "pitch_damping_ratio", "flood_mass_t_per_percent",
    "brake_thrust_limit_fraction", "surge_added_mass_ratio",
    "wake_sample_s", "wake_max_points",
    "wake_decay_s",
}


def load_hull_data() -> dict:
    path = resources.files("data.loadouts") / "ownship_hull.json"
    data = json.loads(path.read_text(encoding="utf-8"),
                      parse_constant=lambda value: (_ for _ in ()).throw(
                          ValueError(value)))
    if not isinstance(data, dict) or set(data) != _HULL_FIELDS:
        raise ValueError("ownship_hull.json: unexpected fields")
    if data["version"] != 1 or not isinstance(data["note"], str):
        raise ValueError("ownship_hull.json: unsupported version")
    for key, value in data.items():
        if key in ("version", "note"):
            continue
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value <= 0.0):
            raise ValueError(f"ownship_hull.json: {key} must be positive")
    if data["flank_advance_ratio"] >= data["propeller_zero_thrust_advance_ratio"]:
        raise ValueError("ownship_hull.json: flank advance ratio too high")
    return data


def riccati_step(v0: float, a0: float, a1: float, a2: float,
                 dt: float) -> float:
    """Exact solution of dv/dt = a0 - a1 v - a2 v^2 after ``dt`` (a2 > 0)."""
    if dt <= 0.0:
        return v0
    disc = a1 * a1 + 4.0 * a2 * a0
    if disc > 1e-18:
        root = math.sqrt(disc)
        r1 = (-a1 + root) / (2.0 * a2)
        r2 = (-a1 - root) / (2.0 * a2)
        if abs(v0 - r2) < 1e-15:
            return r2
        q = (v0 - r1) / (v0 - r2) * math.exp(-a2 * (r1 - r2) * dt)
        return (r1 - r2 * q) / (1.0 - q)
    shift = a1 / (2.0 * a2)
    if disc > -1e-18:
        w0 = v0 + shift
        return 1.0 / (1.0 / w0 + a2 * dt) - shift if w0 > 0.0 else w0 - shift
    omega = math.sqrt(-disc) / (2.0 * a2)
    w0 = v0 + shift
    angle = math.atan(w0 / omega) - a2 * omega * dt
    return omega * math.tan(angle) - shift


def riccati_time_to(v0: float, v1: float, a0: float, a1: float,
                    a2: float) -> float:
    """Time for dv/dt = a0 - a1 v - a2 v^2 (no real roots) to fall v0->v1."""
    disc = a1 * a1 + 4.0 * a2 * a0
    omega = math.sqrt(max(-disc, 1e-18)) / (2.0 * a2)
    shift = a1 / (2.0 * a2)
    return (math.atan((v0 + shift) / omega)
            - math.atan((v1 + shift) / omega)) / (a2 * omega)


@dataclass(frozen=True)
class HullModel:
    """Calibrated constants of the own frigate (SI units)."""
    mass_design_kg: float
    added_mass_ratio: float
    drag_k: float                 # R = k v^2   [N s^2/m^2]
    thrust_k: float               # T = K n^2 - B n v   (n in rev/s)
    thrust_b: float
    brake_thrust_n: float
    load_up_rps: float            # control-programme margin over steady rps
    rpm_per_mps: float            # steady rev/min per m/s
    diameter_m: float
    shaft_immersion_m: float
    cavitation_sigma: float
    sfc_kg_per_j: float
    propulsive_efficiency: float
    pitch_screw_m: float          # zero-thrust advance per revolution
    nomoto_k: float               # r = K (V/L) delta
    nomoto_t_s: float
    length_m: float
    beam_m: float
    draft_m: float
    block_coefficient: float
    waterplane_area_m2: float
    gm_m: float
    turn_heel_lever_m: float
    roll_omega: float
    roll_zeta: float
    stabilizer_zeta: float
    stabilizer_full_mps: float
    pitch_omega: float
    pitch_zeta: float
    flood_kg_per_percent: float
    idle_rpm: float
    wake_sample_s: float
    wake_max_points: int
    wake_decay_s: float

    # --- steady relations ------------------------------------------------

    def steady_rps(self, speed_mps: float) -> float:
        return self.rpm_per_mps * max(0.0, speed_mps) / 60.0

    def thrust_n(self, rps: float, speed_mps: float) -> float:
        return self.thrust_k * rps * rps - self.thrust_b * rps * speed_mps

    def added_resistance_n(self, sea_state: float) -> float:
        index = max(0.0, min(6.0, sea_state))
        low = int(index)
        high = min(6, low + 1)
        hs = (SEA_STATE_HS_M[low]
              + (SEA_STATE_HS_M[high] - SEA_STATE_HS_M[low]) * (index - low))
        return (ADDED_RESISTANCE_COEFF * RHO_SEA * G * hs * hs
                * self.beam_m ** 2 / self.length_m)

    def effective_mass_kg(self, mass_kg: float) -> float:
        return mass_kg * (1.0 + self.added_mass_ratio)

    def cavitation_number(self, rps: float, speed_mps: float,
                          immersion_m: float) -> float:
        tip = math.hypot(math.pi * rps * self.diameter_m, speed_mps)
        if tip <= 1e-6:
            return float("inf")
        pressure = P_ATM + RHO_SEA * G * max(0.0, immersion_m) - P_VAPOUR
        return pressure / (0.5 * RHO_SEA * tip * tip)

    def shaft_power_w(self, thrust: float, rps: float) -> float:
        """Delivered power from thrust times screw advance (bollard-safe)."""
        return abs(thrust) * max(rps, 0.0) * self.pitch_screw_m \
            / max(0.05, self.propulsive_efficiency)


def _exp_linear_step(v0: float, alpha: float, beta: float, dt: float) -> float:
    """Exact solution of dv/dt = alpha + beta v."""
    if abs(beta) < 1e-15:
        return v0 + alpha * dt
    return (v0 + alpha / beta) * math.exp(beta * dt) - alpha / beta


def _exp_linear_time_to(v0: float, v1: float, alpha: float, beta: float) -> float:
    """Time until dv/dt = alpha + beta v reaches ``v1``; inf if it never does."""
    if abs(beta) < 1e-15:
        t = (v1 - v0) / alpha if alpha != 0.0 else float("inf")
    else:
        ratio = (v1 + alpha / beta) / (v0 + alpha / beta)
        t = math.log(ratio) / beta if ratio > 0.0 else float("inf")
    # A negative time means v1 lies behind the motion (or beyond an unstable
    # equilibrium): it is not reached, never jumped to.
    return t if t >= 0.0 else float("inf")


def surge_step(model: HullModel, v0: float, target: float, mass_kg: float,
               dt: float, extra_resistance: float = 0.0,
               brake_margin: float = 0.15) -> tuple[float, float, bool]:
    """Advance speed (m/s) toward the ordered speed for ``dt`` seconds.

    Three exactly integrable regimes, split at their boundaries:

    * braking - more than ``brake_margin`` above the order the controllable
      pitch reverses for a bounded braking thrust (``a0 - a2 v^2``);
    * load-up - the propulsion control programme lets the shaft run at most
      ``load_up_rps`` above the steady revolutions of the present speed, so
      the quadratic thrust and drag terms cancel and ``dv/dt`` is linear;
    * governed - the shaft holds the steady revolutions of the order
      (Riccati ``a0 - a1 v - a2 v^2``).

    Returns ``(speed, shaft_rps, braking)``.
    """
    mass_eff = model.effective_mass_kg(mass_kg)
    n_target = model.steady_rps(target)
    c = model.rpm_per_mps / 60.0
    # The control programme's load-up margin also covers the added resistance
    # in a seaway, so the calm-water acceleration margin K*delta0^2 is kept
    # (without it the ship could not get under way from rest in heavy seas).
    delta = math.sqrt(model.load_up_rps ** 2
                      + max(0.0, extra_resistance) / model.thrust_k)
    remaining = dt
    v = max(0.0, v0)
    governed = False
    for _ in range(4):
        if remaining <= 0.0:
            break
        if not governed and v > target + brake_margin:
            a0 = -(model.brake_thrust_n + extra_resistance) / mass_eff
            a2 = model.drag_k / mass_eff
            t_hit = riccati_time_to(v, target + brake_margin, a0, 0.0, a2)
            if t_hit >= remaining:
                return max(0.0, riccati_step(v, a0, 0.0, a2, remaining)), 0.0, True
            v = target + brake_margin
            remaining -= t_hit
            governed = True
            continue
        n_free = c * v + delta
        if not governed and n_target > n_free:
            alpha = (model.thrust_k * delta * delta - extra_resistance) / mass_eff
            beta = (2.0 * model.thrust_k * c - model.thrust_b) * delta / mass_eff
            v_switch = (n_target - delta) / c
            t_hit = _exp_linear_time_to(v, v_switch, alpha, beta)
            if t_hit >= remaining:
                v = _exp_linear_step(v, alpha, beta, remaining)
                return max(0.0, v), c * v + delta, False
            v = v_switch
            remaining -= t_hit
            governed = True
            continue
        a0 = (model.thrust_k * n_target * n_target - extra_resistance) / mass_eff
        a1 = model.thrust_b * n_target / mass_eff
        a2 = model.drag_k / mass_eff
        v = riccati_step(v, a0, a1, a2, remaining)
        remaining = 0.0
    return max(0.0, v), n_target, False


def _time_to_fraction(model: HullModel, mass_kg: float, start: float,
                      target: float, fraction_of: float, rising: bool,
                      limit_s: float = 3600.0) -> float:
    """Exact-ish time until speed crosses ``fraction_of`` (bisection)."""
    def speed_at(t):
        return surge_step(model, start, target, mass_kg, t)[0]
    low, high = 0.0, limit_s
    for _ in range(80):
        mid = 0.5 * (low + high)
        reached = speed_at(mid) >= fraction_of if rising else \
            speed_at(mid) <= fraction_of
        if reached:
            high = mid
        else:
            low = mid
    return high


def calibrate(data: dict | None = None) -> HullModel:
    """Solve model constants so the 1.0.0 gameplay references hold."""
    data = data or load_hull_data()
    orders = dict(config.TELEGRAPH_ORDERS)
    v_max = config.SHIP_SPEED_MAX_KN * KN
    power_w = data["max_brake_power_kw"] * 1000.0
    eta = data["propulsive_efficiency"]
    drag_k = power_w * eta / v_max ** 3
    diameter = data["propeller_diameter_m"]
    j0 = data["propeller_zero_thrust_advance_ratio"]
    j_flank = data["flank_advance_ratio"]
    rps_flank = v_max / (j_flank * diameter)
    # Linear K_T(J): T = K n^2 (1 - J/J0) = K n^2 - (K/(D J0)) n v; steady at
    # flank solves K.
    thrust_k = drag_k * v_max ** 2 / (rps_flank ** 2 * (1.0 - j_flank / j0))
    thrust_b = thrust_k / (diameter * j0)
    rpm_per_mps = rps_flank * 60.0 / v_max
    mass_design = data["displacement_t"] * 1000.0
    waterplane = (data["waterplane_coefficient"] * data["length_m"]
                  * data["beam_m"])
    screw = diameter * j0
    base = dict(
        mass_design_kg=mass_design,
        added_mass_ratio=data["surge_added_mass_ratio"], drag_k=drag_k,
        thrust_k=thrust_k, thrust_b=thrust_b, brake_thrust_n=1.0,
        load_up_rps=0.1,
        rpm_per_mps=rpm_per_mps, diameter_m=diameter,
        shaft_immersion_m=data["shaft_immersion_m"], cavitation_sigma=0.0,
        sfc_kg_per_j=0.0, propulsive_efficiency=eta, pitch_screw_m=screw, nomoto_k=1.0,
        nomoto_t_s=config.SHIP_YAW_RESPONSE_S, length_m=data["length_m"],
        beam_m=data["beam_m"], draft_m=data["draft_m"],
        block_coefficient=data["block_coefficient"],
        waterplane_area_m2=waterplane, gm_m=data["metacentric_height_m"],
        turn_heel_lever_m=data["turn_heel_lever_m"],
        roll_omega=2.0 * math.pi / data["roll_period_s"],
        roll_zeta=data["roll_damping_ratio"],
        stabilizer_zeta=data["stabilizer_damping_ratio"],
        stabilizer_full_mps=data["stabilizer_full_speed_kn"] * KN,
        pitch_omega=2.0 * math.pi / data["pitch_period_s"],
        pitch_zeta=data["pitch_damping_ratio"],
        flood_kg_per_percent=data["flood_mass_t_per_percent"] * 1000.0,
        idle_rpm=data["idle_rpm"], wake_sample_s=data["wake_sample_s"],
        wake_max_points=int(data["wake_max_points"]),
        wake_decay_s=data["wake_decay_s"])

    def with_(**changes):
        values = dict(base)
        values.update(changes)
        return HullModel(**values)

    # Load-up programme: time to 90 % of FULL from rest equals the 1.0.0
    # reference SHIP_SPEED_TAU_S * ln 10.
    v_full = orders["FULL"] * KN
    t90_target = config.SHIP_SPEED_TAU_S * math.log(10.0)
    low, high = 1e-4, rps_flank
    for _ in range(80):
        mid = 0.5 * (low + high)
        model = with_(load_up_rps=mid)
        t90 = _time_to_fraction(model, mass_design, 0.0, v_full, 0.9 * v_full,
                                True)
        if t90 > t90_target:
            low = mid
        else:
            high = mid
    base["load_up_rps"] = 0.5 * (low + high)
    # Braking thrust: STOP from FULL to 10 % in the same reference time.
    low, high = 1.0, 20.0 * drag_k * v_max ** 2
    for _ in range(80):
        mid = 0.5 * (low + high)
        model = with_(brake_thrust_n=mid)
        t10 = _time_to_fraction(model, mass_design, v_full, 0.0, 0.1 * v_full,
                                False)
        if t10 > t90_target:
            low = mid
        else:
            high = mid
    brake = 0.5 * (low + high)
    base["brake_thrust_n"] = min(
        brake, data["brake_thrust_limit_fraction"] * drag_k * v_max ** 2)
    # Cavitation onset at CAVITATION_KN in calm water.
    v_cav = config.CAVITATION_KN * KN
    model = with_()
    base["cavitation_sigma"] = model.cavitation_number(
        model.steady_rps(v_cav), v_cav, data["shaft_immersion_m"])
    # Fuel: steady FLANK burns the 1.0.0 propulsion allowance.
    model = with_()
    flank_power = model.shaft_power_w(drag_k * v_max ** 2, rps_flank)
    base["sfc_kg_per_j"] = (config.SHIP_FUEL_MAX_PROPULSION_KG_H / 3600.0
                            / flank_power)
    # Nomoto gain: steady turn at FULL with full rudder equals the 1.0.0
    # reference (max yaw rate x the capped speed factor).
    reference_yaw = math.radians(config.SHIP_MAX_YAW_RATE_DEG_PER_S * 1.5)
    base["nomoto_k"] = reference_yaw * data["length_m"] / (
        v_full * math.radians(config.SHIP_MAX_RUDDER_DEG))
    return HullModel(**base)


HULL = calibrate()

# The frigate's propeller: its blade-rate line (shaft rate x blades) is the
# own-ship line on LOFAR and the one the notch filter removes.
OWN_PROPELLER_BLADES = 5


def own_blade_line_hz(speed_kn: float) -> float:
    """Own blade-rate line (Hz) at steady speed: the shaft RPM of the
    fixed-pitch propeller (about 5.8 rpm per knot) times the blades."""
    return HULL.steady_rps(max(0.0, speed_kn) * KN) * OWN_PROPELLER_BLADES


# --- seakeeping --------------------------------------------------------------


@functools.lru_cache(maxsize=64)
def _wave_components(seed: int, hs_key: float) -> tuple[tuple[float, float, float], ...]:
    """(omega, slope amplitude, phase) of the discretized PM spectrum."""
    hs = hs_key
    omega_p = 2.0 * math.pi / (4.2 * math.sqrt(hs) + 1.0)
    lo, hi = 0.6 * omega_p, 2.2 * omega_p
    step = (hi - lo) / WAVE_COMPONENTS
    parts = []
    for index in range(WAVE_COMPONENTS):
        omega = lo + (index + 0.5) * step
        spectrum = (5.0 / 16.0) * hs * hs * omega_p ** 4 * omega ** -5 \
            * math.exp(-1.25 * (omega_p / omega) ** 4)
        amplitude = math.sqrt(2.0 * spectrum * step)
        # Wave slope amplitude k a with deep-water dispersion k = w^2/g.
        parts.append((omega, (omega * omega / G) * amplitude,
                      detrand.phase(seed, "wave", index)))
    return tuple(parts)


def wave_slope_rad(seed: int, clock_s: float, sea_state: float) -> float:
    """Effective wave slope from a Pierson-Moskowitz sea (8 components)."""
    index = max(0.0, min(6.0, sea_state))
    low = int(index)
    high = min(6, low + 1)
    hs = SEA_STATE_HS_M[low] + (SEA_STATE_HS_M[high] - SEA_STATE_HS_M[low]) \
        * (index - low)
    if hs <= 0.0:
        return 0.0
    # Quantize the height so the component cache stays small and exact.
    parts = _wave_components(int(seed), round(hs, 2))
    return sum(amplitude * math.sin(omega * clock_s + phase)
               for omega, amplitude, phase in parts)


def turn_heel_rad(model: HullModel, speed_mps: float, yaw_rate_rad: float) -> float:
    """Steady outward heel from the centripetal moment in a turn."""
    return (speed_mps * yaw_rate_rad * model.turn_heel_lever_m
            / (G * model.gm_m))


def squat_m(model: HullModel, speed_kn: float, depth_m: float,
            draft_m: float) -> float:
    """Barrass squat, fading out as water depth exceeds ~5 draughts."""
    if depth_m <= 0.0:
        return 0.0
    ratio = depth_m / max(draft_m, 0.1)
    factor = max(0.0, min(1.0, (5.0 - ratio) / 3.8))
    return model.block_coefficient * speed_kn * speed_kn / 100.0 * factor


def hydrostatic_draft_m(model: HullModel, mass_kg: float) -> float:
    return model.draft_m + (mass_kg - model.mass_design_kg) / (
        RHO_SEA * model.waterplane_area_m2)


# Effective fraction of the local wave slope that excites the hull (a long
# ship averages the slope over its beam/length).
ROLL_WAVE_GAIN = 0.55
PITCH_WAVE_GAIN = 0.35
# Running into the sea meets the waves faster and pitches harder; running
# with it softer: pitch forcing x (1 + gain x speed(kn) x cos(wave angle)),
# never below ENCOUNTER_MIN.  At rest the sea is met as before.
ENCOUNTER_PITCH_GAIN = 0.03
ENCOUNTER_MIN = 0.6
SEAKEEPING_SUBSTEP_S = 0.05


def seakeeping_step(model: HullModel, roll_deg: float, roll_rate: float,
                    pitch_deg: float, pitch_rate: float, *, dt: float,
                    clock_s: float, seed: int, sea_state: float,
                    wave_relative_deg: float, speed_mps: float,
                    yaw_rate_rad: float, list_deg: float,
                    stabilizers: bool) -> tuple[float, float, float, float]:
    """Integrate 1-DOF roll and pitch oscillators (semi-implicit Euler).

    Roll is driven toward the instantaneous equilibrium of wave slope (beam
    component), steady turn heel and damage list; active fin stabilizers add
    speed-dependent damping.  Pitch follows the head/following-sea slope.
    """
    steps = max(1, math.ceil(dt / SEAKEEPING_SUBSTEP_S - 1e-9))
    h = dt / steps
    rel = math.radians(wave_relative_deg)
    beam = abs(math.sin(rel))
    head = abs(math.cos(rel))
    heel = math.degrees(turn_heel_rad(model, speed_mps, yaw_rate_rad))
    zeta_roll = model.roll_zeta
    if stabilizers:
        zeta_roll += model.stabilizer_zeta * min(
            1.0, (speed_mps / model.stabilizer_full_mps) ** 2)
    w_r, w_p = model.roll_omega, model.pitch_omega
    encounter = max(ENCOUNTER_MIN, 1.0 + ENCOUNTER_PITCH_GAIN * (speed_mps / 0.514444)
                    * math.cos(rel))
    for index in range(steps):
        t = clock_s + (index + 1) * h
        slope = math.degrees(wave_slope_rad(seed, t, sea_state))
        slope_p = math.degrees(wave_slope_rad(seed + 7919, t, sea_state))
        roll_eq = ROLL_WAVE_GAIN * beam * slope + heel + list_deg
        pitch_eq = PITCH_WAVE_GAIN * head * slope_p * encounter
        roll_rate += h * (-2.0 * zeta_roll * w_r * roll_rate
                          - w_r * w_r * (roll_deg - roll_eq))
        roll_deg += h * roll_rate
        pitch_rate += h * (-2.0 * model.pitch_zeta * w_p * pitch_rate
                           - w_p * w_p * (pitch_deg - pitch_eq))
        pitch_deg += h * pitch_rate
    return roll_deg, roll_rate, pitch_deg, pitch_rate
