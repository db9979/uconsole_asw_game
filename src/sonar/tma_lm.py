"""Levenberg-Marquardt refinement and covariance for bearing(-Doppler) TMA.

The coarse grid search in ``tma.py`` finds the basin; this module refines the
constant-velocity target state (position at the newest measurement, velocity
and, when frequency measurements exist, the unshifted tonal frequency f0)
by damped Gauss-Newton on the weighted bearing and Doppler residuals, and
returns the state covariance ``(J^T W J)^-1``.

Doppler makes range observable without an own-ship manoeuvre: the received
tonal is f = f0 (1 + v_c / c) with the closing speed v_c of the geometry.
Everything is deterministic, bounded (at most MAX_ITERATIONS) and uses no
target truth.
"""

from __future__ import annotations

import math

import numpy as np

from src.core import config

MAX_ITERATIONS = 8
SOUND_SPEED_KN = config.SOUND_SPEED_M_S * 3600.0 / 1852.0
DOPPLER_SIGMA_HZ = 0.02
MIN_DOPPLER_POINTS = 4


def _bearing(tx, ty, fx, fy):
    return math.degrees(math.atan2(tx - fx, -(ty - fy))) % 360.0


def _residuals(state, points, t_ref, use_doppler):
    x, y, vx, vy = state[:4]      # NM, NM/s
    f0 = state[4] if use_doppler else None
    residuals = []
    for p in points:
        tau = p.t - t_ref
        tx, ty = x + vx * tau, y + vy * tau
        dx, dy = tx - p.fx, ty - p.fy
        if math.hypot(dx, dy) < 1e-3:
            return None
        predicted = _bearing(tx, ty, p.fx, p.fy)
        residuals.append(config.angle_diff_deg(p.bearing, predicted)
                         / p.uncertainty_deg)
        freq = getattr(p, "freq_hz", None)
        if use_doppler and freq is not None:
            # Closing speed: relative velocity along the line of sight.
            distance = math.hypot(dx, dy)
            ux, uy = -dx / distance, -dy / distance
            speed = getattr(p, "fspeed", 0.0) or 0.0
            ovx = config.kn_to_nm_per_s(speed) * math.sin(math.radians(p.fcourse))
            ovy = -config.kn_to_nm_per_s(speed) * math.cos(math.radians(p.fcourse))
            closing = ((vx - ovx) * ux + (vy - ovy) * uy) * 3600.0   # kn
            residuals.append((freq - f0 * (1.0 + closing / SOUND_SPEED_KN))
                             / DOPPLER_SIGMA_HZ)
    return np.asarray(residuals, dtype=float)


def _state(pos, course_deg, speed_kn):
    vmag = config.kn_to_nm_per_s(speed_kn)
    return [pos[0], pos[1], vmag * math.sin(math.radians(course_deg)),
            -vmag * math.cos(math.radians(course_deg))]


def _jacobian(state, points, t_ref, use_doppler, scales):
    columns = []
    for index in range(len(state)):
        step = np.zeros_like(state)
        step[index] = scales[index] * 1e-2
        plus = _residuals(state + step, points, t_ref, use_doppler)
        minus = _residuals(state - step, points, t_ref, use_doppler)
        if plus is None or minus is None:
            return None
        columns.append((plus - minus) / (2.0 * step[index]))
    return np.stack(columns, axis=1)


def refine(points, course_deg: float, speed_kn: float, pos: tuple):
    """Refine a grid solution.

    Returns (pos, course, speed, cov2x2, f0, rmse_deg, cost_ratio, doppler)
    or None when the problem is singular.  ``cost_ratio`` compares the
    refined bearing cost with the starting grid solution."""
    if len(points) < 3:
        return None
    t_ref = points[-1].t
    freqs = [p.freq_hz for p in points if getattr(p, "freq_hz", None) is not None]
    use_doppler = len(freqs) >= MIN_DOPPLER_POINTS
    state = _state(pos, course_deg, speed_kn)
    if use_doppler:
        state.append(float(np.median(freqs)))
    state = np.asarray(state, dtype=float)
    scales = np.array([0.05, 0.05, 2e-5, 2e-5, 0.01][:len(state)])
    residual = _residuals(state, points, t_ref, use_doppler)
    if residual is None:
        return None
    start_cost = cost = float(residual @ residual)
    lam = 1e-2
    for _ in range(MAX_ITERATIONS):
        jacobian = _jacobian(state, points, t_ref, use_doppler, scales)
        if jacobian is None:
            return None
        normal = jacobian.T @ jacobian
        gradient = jacobian.T @ residual
        damped = normal + lam * np.diag(np.diag(normal) + 1e-12)
        try:
            delta = -np.linalg.solve(damped, gradient)
        except np.linalg.LinAlgError:
            return None
        trial = state + delta
        trial_residual = _residuals(trial, points, t_ref, use_doppler)
        if trial_residual is not None and trial_residual @ trial_residual < cost:
            state, residual = trial, trial_residual
            cost = float(residual @ residual)
            lam = max(lam * 0.3, 1e-6)
        else:
            lam = min(lam * 10.0, 1e6)
    jacobian = _jacobian(state, points, t_ref, use_doppler, scales)
    if jacobian is None:
        return None
    try:
        covariance = np.linalg.inv(jacobian.T @ jacobian)
    except np.linalg.LinAlgError:
        return None
    if not np.all(np.isfinite(covariance)):
        return None
    vx, vy = state[2], state[3]
    speed = math.hypot(vx, vy) * 3600.0
    course = math.degrees(math.atan2(vx, -vy)) % 360.0
    bearing_residuals = [
        config.angle_diff_deg(p.bearing, _bearing(
            state[0] + vx * (p.t - t_ref), state[1] + vy * (p.t - t_ref),
            p.fx, p.fy)) for p in points]
    rmse = math.sqrt(sum(r * r for r in bearing_residuals) / len(bearing_residuals))
    return ((float(state[0]), float(state[1])), course, speed,
            covariance[:2, :2].copy(), (float(state[4]) if use_doppler else None),
            rmse, cost / max(start_cost, 1e-12), use_doppler)


def covariance_at(points, course_deg: float, speed_kn: float, pos: tuple):
    """Position covariance of a given solution (no iteration)."""
    if len(points) < 3:
        return None
    state = np.asarray(_state(pos, course_deg, speed_kn), dtype=float)
    jacobian = _jacobian(state, points, points[-1].t, False,
                         np.array([0.05, 0.05, 2e-5, 2e-5]))
    if jacobian is None:
        return None
    try:
        covariance = np.linalg.inv(jacobian.T @ jacobian)
    except np.linalg.LinAlgError:
        return None
    return covariance[:2, :2].copy() if np.all(np.isfinite(covariance)) else None


def ellipse(cov2x2) -> tuple[float, float, float]:
    """(semi-major NM, semi-minor NM, orientation deg nautical) at 1 sigma."""
    values, vectors = np.linalg.eigh(np.asarray(cov2x2, dtype=float))
    values = np.maximum(values, 0.0)
    major = vectors[:, 1]
    orientation = math.degrees(math.atan2(major[0], -major[1])) % 180.0
    return math.sqrt(values[1]), math.sqrt(values[0]), orientation
