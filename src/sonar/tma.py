"""W1: TMA – Position + Geschwindigkeit aus einer Peilungsreihe
(bearing-only Tracking).

Deterministisch: Gittersuche über (Kurs, Geschwindigkeit) des Ziels;
pro Kandidat wird die Startposition P0 per Least Squares so gelöst,
dass alle (bewegte) Fregatten-Positionen + Zielbahn die Peilstriche
möglichst gut treffen. Der Peil-RMSE liefert die Qualität.

Zeiten in sim-Sekunden, Distanzen in NM.
"""

import math

from src.core import config
from src.sonar import tma_lm

# A refinement replaces the grid solution only when it fits clearly better
# (or uses Doppler); flat bearing-only minima otherwise make it wander.
LM_ACCEPT_COST_RATIO = 0.8
LM_MIN_MANOEUVRE = 0.5
DOPPLER_OBSERVABLE_SPREAD_HZ = 0.05


class BearingPoint:
    __slots__ = ("t", "bearing", "fx", "fy", "fcourse", "uncertainty_deg",
                 "freq_hz", "fspeed")

    def __init__(self, t: float, bearing: float, fx: float, fy: float,
                 fcourse: float, uncertainty_deg: float = None,
                 freq_hz: float | None = None, fspeed: float = 0.0):
        self.t = t
        # Measured (Doppler-shifted) tonal frequency and observer speed.
        self.freq_hz = freq_hz
        self.fspeed = fspeed
        self.bearing = bearing % 360.0
        self.fx = fx
        self.fy = fy
        self.fcourse = fcourse
        self.uncertainty_deg = (config.TMA_DEFAULT_BEARING_SIGMA_DEG
                                if uncertainty_deg is None
                                else max(0.05, uncertainty_deg))


class BearingTrack:
    def __init__(self):
        self.pts: list[BearingPoint] = []
        self.version = 0  # laeuft hoch bei jeder Aenderung -> TMA-Re-Solve-Gate

    def add(self, t: float, bearing: float, fx: float, fy: float,
            fcourse: float, uncertainty_deg: float = None,
            freq_hz: float | None = None, fspeed: float = 0.0) -> None:
        if self.pts and \
                t - self.pts[-1].t < config.BEARING_TRACK_MIN_INTERVAL_S:
            return
        self.pts.append(BearingPoint(
            t, bearing, fx, fy, fcourse, uncertainty_deg, freq_hz, fspeed))
        if len(self.pts) > config.BEARING_TRACK_MAX_PTS:
            self.pts.pop(0)
        self.version += 1

    def span_s(self) -> float:
        return (self.pts[-1].t - self.pts[0].t) if len(self.pts) >= 2 else 0.0

    def course_span_deg(self) -> float:
        """Beobachtbarkeit: Fregatten-Kursänderung über das Zeitfenster."""
        if len(self.pts) < 2:
            return 0.0
        return max(abs(config.angle_diff_deg(a.fcourse, b.fcourse))
                   for i, a in enumerate(self.pts) for b in self.pts[i + 1:])

    def doppler_observable(self) -> bool:
        """Enough frequency measurements with a real spread to fix range."""
        freqs = [p.freq_hz for p in self.pts if p.freq_hz is not None]
        return (len(freqs) >= tma_lm.MIN_DOPPLER_POINTS
                and max(freqs) - min(freqs) >= DOPPLER_OBSERVABLE_SPREAD_HZ)


class TMASolution:
    __slots__ = ("pos", "course", "speed", "quality", "rmse_deg", "n_pts",
                 "ellipse", "f0_hz")

    def __init__(self, pos: tuple, course: float, speed: float,
                 quality: float, rmse_deg: float, n_pts: int,
                 ellipse: tuple | None = None, f0_hz: float | None = None):
        # (semi-major NM, semi-minor NM, orientation deg) at 1 sigma.
        self.ellipse = ellipse
        self.f0_hz = f0_hz
        self.pos = pos            # (x, y) NM – Zielposition (letzte Peilung)
        self.course = course      # Zielkurs (°)
        self.speed = speed        # Zielfahrt (kn)
        self.quality = quality    # 0..1
        self.rmse_deg = rmse_deg
        self.n_pts = n_pts


def _bearing_dir(brg_deg: float) -> tuple:
    """Einheitsvektor einer nautischen Peilung (0° = Nord/-y, 90° = Ost/+x)."""
    r = math.radians(brg_deg)
    return math.sin(r), -math.cos(r)


def _line_position(geometry, vx, vy, robust_weights=None):
    """Weighted line intersection, optionally with robust residual weights."""
    m00 = m01 = m11 = 0.0
    b0 = b1 = 0.0
    for index, (p, tau, a00, a01, a11, weight) in enumerate(geometry):
        if robust_weights is not None:
            weight *= robust_weights[index]
        fx = p.fx - vx * tau
        fy = p.fy - vy * tau
        m00 += weight * a00
        m01 += weight * a01
        m11 += weight * a11
        b0 += weight * (a00 * fx + a01 * fy)
        b1 += weight * (a01 * fx + a11 * fy)
    det = m00 * m11 - m01 * m01
    if det < 1e-9:
        return None
    return ((b0 * m11 - b1 * m01) / det,
            (b1 * m00 - b0 * m01) / det)


def _candidate_errors(geometry, p0x, p0y, vx, vy):
    errors = []
    for p, tau, _, _, _, _ in geometry:
        tx = p0x + vx * tau
        ty = p0y + vy * tau
        ddx, ddy = tx - p.fx, ty - p.fy
        if math.hypot(ddx, ddy) < 1e-3:
            return None
        predicted = math.degrees(math.atan2(ddx, -ddy)) % 360.0
        errors.append(config.angle_diff_deg(p.bearing, predicted))
    return errors


def _try_candidate(geometry, t0, course_deg, speed_kn, max_range_nm):
    """RMSE + Position für einen (Kurs, Geschw.)-Kandidaten."""
    vr = math.radians(course_deg)
    vmag = config.kn_to_nm_per_s(speed_kn)
    # Nautisches Koordinatensystem: 0° = Nord/-y, 90° = Ost/+x
    vx, vy = vmag * math.sin(vr), -vmag * math.cos(vr)

    position = _line_position(geometry, vx, vy)
    if position is None:
        return None
    p0x, p0y = position
    # Two fixed IRLS passes suppress isolated bad bearings without consulting
    # target truth or introducing convergence/order nondeterminism.
    for _ in range(2):
        errors = _candidate_errors(geometry, p0x, p0y, vx, vy)
        if errors is None:
            return None
        robust = [min(1.0, config.TMA_ROBUST_SIGMA * row[0].uncertainty_deg
                      / max(abs(error), 1e-9))
                  for row, error in zip(geometry, errors)]
        position = _line_position(geometry, vx, vy, robust)
        if position is None:
            return None
        p0x, p0y = position
    errors = _candidate_errors(geometry, p0x, p0y, vx, vy)
    if errors is None:
        return None
    weights = [row[5] for row in geometry]
    rmse = math.sqrt(sum(weight * error * error
                         for weight, error in zip(weights, errors)) / sum(weights))
    if rmse > 25.0:
        return None

    last = geometry[-1][0]
    tau = last.t - t0
    last_x = p0x + vx * tau
    last_y = p0y + vy * tau
    range_nm = math.hypot(last_x - last.fx, last_y - last.fy)
    if range_nm > max_range_nm:
        return None
    quality = max(0.0, 1.0 - rmse / config.TMA_QUALITY_DB)
    quality *= min(1.0, len(geometry) / (config.TMA_MIN_PTS + 4.0))
    return (rmse, course_deg, speed_kn, (last_x, last_y), quality)


def solve_tma(track: BearingTrack,
              max_range_nm: float = None,
              previous_course: float = None,
              previous_speed: float = None) -> "TMASolution | None":
    """TMA-Lösung oder None (zu wenig Daten / keine Observierbarkeit).

    `previous_course`/`previous_speed` add re-solve hysteresis: bearing-only
    geometry routinely has several near-tied (course, speed) candidates, and
    the window sliding by one point between re-solves can tip the coarse grid
    search from one to another even though neither fits meaningfully better.
    Re-scoring the previous solution and keeping it unless a fresh candidate
    clears it by more than the RMSE margin stops that hopping without ever
    preferring a candidate that fits distinctly worse.
    """
    pts = track.pts
    if len(pts) < config.TMA_MIN_PTS:
        return None
    if track.span_s() < config.TMA_MIN_SPAN_S:
        return None
    doppler = track.doppler_observable()
    if track.course_span_deg() < config.TMA_MIN_COURSE_CHG_DEG and not doppler:
        return None
    max_range_nm = max_range_nm or config.TMA_MAX_RANGE_NM

    t0 = pts[0].t
    # These terms are invariant across candidates and both IRLS passes. Keep
    # the original operation/reduction order in the fits to preserve ties.
    geometry = []
    for p in pts:
        ux, uy = _bearing_dir(p.bearing)
        geometry.append((p, p.t - t0, 1.0 - ux * ux, -ux * uy,
                         1.0 - uy * uy,
                         1.0 / (p.uncertainty_deg * p.uncertainty_deg)))
    best = None
    for course_deg in range(0, 360, 15):
        for speed_kn in (0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0, 18.0):
            cand = _try_candidate(geometry, t0, course_deg, speed_kn, max_range_nm)
            if cand is not None and (best is None or cand[0] < best[0]):
                best = cand
    if best is None:
        return None
    # Fine local search remains based solely on the immutable raw bearings.
    _, b_course, b_speed, _, _ = best
    course_step = config.TMA_FINE_COURSE_STEP_DEG
    speed_step = config.TMA_FINE_SPEED_STEP_KN
    for dc in (-course_step, 0, course_step):
        for ds in (-speed_step, 0.0, speed_step):
            c2 = (b_course + dc) % 360
            s2 = b_speed + ds
            if s2 < 0.0:
                continue
            cand = _try_candidate(geometry, t0, c2, s2, max_range_nm)
            if cand is not None and cand[0] < best[0]:
                best = cand
    if previous_course is not None and previous_speed is not None:
        prev = _try_candidate(geometry, t0, previous_course % 360.0,
                              previous_speed, max_range_nm)
        if prev is not None:
            for dc in (-course_step, 0, course_step):
                for ds in (-speed_step, 0.0, speed_step):
                    c2 = (previous_course + dc) % 360
                    s2 = previous_speed + ds
                    if s2 < 0.0:
                        continue
                    cand = _try_candidate(geometry, t0, c2, s2, max_range_nm)
                    if cand is not None and cand[0] < prev[0]:
                        prev = cand
            if prev[0] <= best[0] + config.TMA_HYSTERESIS_RMSE_MARGIN_DEG:
                best = prev
    rmse, course, speed, pos, quality = best
    # Heading changes alone (including turns in place) do not resolve range.
    # Scale confidence by the actual departure from constant ownship velocity,
    # relative to angular measurement error at the solved range.
    first, last = pts[0], pts[-1]
    deviation = max(math.hypot(
        p.fx - (first.fx + (last.fx - first.fx) * (p.t - t0) / track.span_s()),
        p.fy - (first.fy + (last.fy - first.fy) * (p.t - t0) / track.span_s()))
        for p in pts)
    angular_noise = math.radians(sum(p.uncertainty_deg for p in pts) / len(pts))

    def manoeuvre_of(position):
        distance = math.hypot(position[0] - last.fx, position[1] - last.fy)
        return min(1.0, deviation / max(1e-6, distance * angular_noise))

    # Levenberg-Marquardt refinement with Doppler and the state covariance;
    # accepted only where the geometry (own manoeuvre or Doppler) makes range
    # observable, otherwise flat minima would let it wander.
    covariance = None
    f0 = None
    refined = tma_lm.refine(pts, course, speed, pos)
    if refined is not None and (
            refined[7] or (manoeuvre_of(refined[0]) >= LM_MIN_MANOEUVRE
                           and refined[6] < LM_ACCEPT_COST_RATIO)):
        pos, course, speed, covariance, f0, rmse = refined[:6]
        quality = max(0.0, 1.0 - rmse / config.TMA_QUALITY_DB) * min(
            1.0, len(pts) / (config.TMA_MIN_PTS + 4.0))
    if covariance is None:
        covariance = tma_lm.covariance_at(pts, course, speed, pos)
    ellipse = (tma_lm.ellipse(covariance) if covariance is not None else None)
    distance = math.hypot(pos[0] - last.fx, pos[1] - last.fy)
    manoeuvre = manoeuvre_of(pos)
    if doppler and ellipse is not None:
        # Doppler observability: judge by the solved range uncertainty.
        manoeuvre = max(manoeuvre, min(1.0, 1.0 - ellipse[0] / max(distance, 1e-3)))
    quality *= manoeuvre
    return TMASolution(pos=pos, course=course, speed=speed, quality=quality,
                       rmse_deg=rmse, n_pts=len(pts), ellipse=ellipse, f0_hz=f0)
