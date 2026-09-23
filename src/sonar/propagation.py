"""Bounded synthetic one-way acoustic propagation for passive sensors.

This is a deterministic game model, not a representation of measured ocean
conditions.  It owns no simulation state and deliberately accepts only the
fixed bands used by the game.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from src.core import config


MAX_RANGE_NM = 500.0
MAX_PATHS = 4
MAX_SEGMENTS_PER_PATH = 3
PROFILE_SAMPLES = 21
PROFILE_MAX_DEPTH_M = 400.0
REPRESENTATIVE_PASSIVE_BAND_HZ = 100.0
# Historical per-band absorption folded into path loss; the sonar equation
# replaces it with Francois-Garrison (src/sonar/equation.py).
ABSORPTION_DB_PER_NM = {100.0: .012, 400.0: .025, 1600.0: .055, 6400.0: .12}
CANONICAL_FREQUENCY_BANDS_HZ = (100.0, 400.0, 1600.0, 6400.0)


class PathKind(str, Enum):
    DIRECT = "DIRECT"
    REFRACTED = "REFRACTED"
    SURFACE = "SURFACE"
    BOTTOM = "BOTTOM"


@dataclass(frozen=True, slots=True)
class SoundSpeedProfile:
    thermocline_m: float
    water_depth_m: float
    depths_m: tuple[float, ...]
    speeds_m_s: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class AcousticPoint:
    x_nm: float
    y_nm: float
    depth_m: float


@dataclass(frozen=True, slots=True)
class PathSegment:
    start: AcousticPoint
    end: AcousticPoint
    distance_nm: float
    travel_time_s: float
    terrain_clear: bool


@dataclass(frozen=True, slots=True)
class PropagationPath:
    kind: PathKind
    segments: tuple[PathSegment, ...]
    distance_nm: float
    loss_db: float
    travel_time_s: float


@dataclass(frozen=True, slots=True)
class PropagationResult:
    frequency_hz: float
    profile: SoundSpeedProfile
    paths: tuple[PropagationPath, ...]
    reverberation_db: float
    spectral_gains: tuple[tuple[float, float], ...]

    @property
    def best_path(self) -> PropagationPath | None:
        return self.paths[0] if self.paths else None


TerrainBlocked = Callable[[float, float, float, float, float, float], bool]


def _geometry_key(points: tuple[AcousticPoint, ...]) -> tuple[AcousticPoint, ...]:
    compact = tuple(point for index, point in enumerate(points)
                    if index == 0 or point != points[index - 1])
    if len(compact) == 3:
        first, middle, last = compact
        if all(abs(value) <= 1e-12 for value in (
                middle.x_nm - (first.x_nm + last.x_nm) * .5,
                middle.y_nm - (first.y_nm + last.y_nm) * .5,
                middle.depth_m - (first.depth_m + last.depth_m) * .5)):
            return first, last
    return compact


def _number(name: str, value: object, low: float, high: float) -> float:
    if (not isinstance(value, (int, float)) or isinstance(value, bool)
            or not math.isfinite(value)):
        raise ValueError(f"{name} must be a finite number")
    result = float(value)
    if not low <= result <= high:
        raise ValueError(f"{name} is outside the supported range")
    return result


def synthetic_sound_speed_m_s(depth_m: float, thermocline_m: float) -> float:
    """Return the existing synthetic BT truth curve at one depth."""
    depth = _number("depth_m", depth_m, 0.0, 10_000.0)
    thermo = _number("thermocline_m", thermocline_m, 0.0, 10_000.0)
    return (1504.0 - .018 * min(depth, thermo)
            + .012 * max(0.0, depth - thermo))


def synthetic_sound_speed_profile(thermocline_m: float,
                                  water_depth_m: float) -> SoundSpeedProfile:
    """Sample the canonical 21-point, at-most-400 m synthetic profile."""
    water_depth = _number("water_depth_m", water_depth_m, 1.0, 10_000.0)
    thermo = _number("thermocline_m", thermocline_m, 0.0, water_depth)
    maximum = min(water_depth, PROFILE_MAX_DEPTH_M)
    step = maximum / (PROFILE_SAMPLES - 1)
    depths = tuple(step * index for index in range(PROFILE_SAMPLES))
    speeds = tuple(synthetic_sound_speed_m_s(depth, thermo) for depth in depths)
    return SoundSpeedProfile(thermo, water_depth, depths, speeds)


def _segment(start: AcousticPoint, end: AcousticPoint,
             profile: SoundSpeedProfile,
             terrain_blocked: TerrainBlocked | None) -> PathSegment:
    horizontal_nm = math.hypot(end.x_nm - start.x_nm, end.y_nm - start.y_nm)
    vertical_nm = abs(end.depth_m - start.depth_m) / 1852.0
    distance_nm = math.hypot(horizontal_nm, vertical_nm)
    middle_depth = (start.depth_m + end.depth_m) * .5
    # Simpson integration retains profile dependence without an iterative ray solver.
    reciprocal_speed = (
        1.0 / synthetic_sound_speed_m_s(start.depth_m, profile.thermocline_m)
        + 4.0 / synthetic_sound_speed_m_s(middle_depth, profile.thermocline_m)
        + 1.0 / synthetic_sound_speed_m_s(end.depth_m, profile.thermocline_m)
    ) / 6.0
    blocked = False if terrain_blocked is None else bool(terrain_blocked(
        start.x_nm, start.y_nm, start.depth_m,
        end.x_nm, end.y_nm, end.depth_m))
    return PathSegment(start, end, distance_nm,
                       distance_nm * 1852.0 * reciprocal_speed, not blocked)


def propagate(source_x_nm: float, source_y_nm: float, source_depth_m: float,
              target_x_nm: float, target_y_nm: float, target_depth_m: float,
              frequency_hz: float, thermocline_m: float, water_depth_m: float,
              *, sea_state: float = 0,
              terrain_blocked: TerrainBlocked | None = None) -> PropagationResult:
    """Compute at most four stable, terrain-clear synthetic one-way paths."""
    sx = _number("source_x_nm", source_x_nm, -1_000_000.0, 1_000_000.0)
    sy = _number("source_y_nm", source_y_nm, -1_000_000.0, 1_000_000.0)
    tx = _number("target_x_nm", target_x_nm, -1_000_000.0, 1_000_000.0)
    ty = _number("target_y_nm", target_y_nm, -1_000_000.0, 1_000_000.0)
    source_depth = _number("source_depth_m", source_depth_m, 0.0, 10_000.0)
    target_depth = _number("target_depth_m", target_depth_m, 0.0, 10_000.0)
    frequency = _number("frequency_hz", frequency_hz,
                        CANONICAL_FREQUENCY_BANDS_HZ[0],
                        CANONICAL_FREQUENCY_BANDS_HZ[-1])
    if frequency not in CANONICAL_FREQUENCY_BANDS_HZ:
        raise ValueError("frequency_hz must be a canonical game band")
    if (type(sea_state) not in (int, float) or not math.isfinite(sea_state)
            or not 0 <= sea_state <= 6):
        raise ValueError("sea_state must be a finite number from 0 to 6")
    if terrain_blocked is not None and not callable(terrain_blocked):
        raise ValueError("terrain_blocked must be callable")
    profile = synthetic_sound_speed_profile(thermocline_m, water_depth_m)
    if source_depth > profile.water_depth_m or target_depth > profile.water_depth_m:
        raise ValueError("endpoint depth exceeds water depth")
    direct_range = math.hypot(tx - sx, ty - sy)
    if direct_range > MAX_RANGE_NM:
        raise ValueError("propagation range exceeds bounded game sector")

    source = AcousticPoint(sx, sy, source_depth)
    target = AcousticPoint(tx, ty, target_depth)
    mx, my = (sx + tx) * .5, (sy + ty) * .5
    thermo = profile.thermocline_m
    same_layer = (source_depth < thermo) == (target_depth < thermo)
    refracted_depth = min(profile.water_depth_m - 1.0, max(1.0, thermo))
    bottom_depth = max(0.0, profile.water_depth_m - 10.0)
    candidates = []
    point_sets = set()
    for kind, points in (
            (PathKind.DIRECT, (source, target)),
            (PathKind.REFRACTED,
             (source, AcousticPoint(mx, my, refracted_depth), target)),
            (PathKind.SURFACE,
             (source, AcousticPoint(mx, my, 0.0), target)),
            (PathKind.BOTTOM,
             (source, AcousticPoint(mx, my, bottom_depth), target))):
        geometry = _geometry_key(points)
        if geometry not in point_sets:
            candidates.append((kind, points))
            point_sets.add(geometry)
    convergence_focus_db = (8.0 if any(
        low <= direct_range <= high for low, high in config.CZ_BANDS) else 0.0)
    kind_penalty = {
        PathKind.DIRECT: 0.0,
        PathKind.REFRACTED: 2.5 - convergence_focus_db,
        PathKind.SURFACE: 5.0 + .6 * sea_state,
        PathKind.BOTTOM: 7.0,
    }
    absorption_db_nm = ABSORPTION_DB_PER_NM[frequency]
    paths = []
    for order, (kind, points) in enumerate(candidates):
        segments = tuple(_segment(first, second, profile, terrain_blocked)
                         for first, second in zip(points, points[1:]))
        if len(segments) > MAX_SEGMENTS_PER_PATH or not all(
                segment.terrain_clear for segment in segments):
            continue
        distance = sum(segment.distance_nm for segment in segments)
        layer_penalty = (6.5 if not same_layer
                         and kind in (PathKind.DIRECT, PathKind.REFRACTED) else 0.0)
        loss = (20.0 * math.log10(1.0 + distance)
                + distance * absorption_db_nm + kind_penalty[kind] + layer_penalty)
        paths.append((loss, order, PropagationPath(
            kind, segments, distance, loss,
            sum(segment.travel_time_s for segment in segments))))
    paths.sort(key=lambda item: (item[0], item[1]))
    ordered = tuple(item[2] for item in paths[:MAX_PATHS])
    reverberation = min(24.0, max(0.0, 1.5 + 1.1 * sea_state
                                 + .004 * direct_range * math.sqrt(frequency)))
    # Relative coloration only: source quality already includes propagation at
    # 100 Hz, so spreading/path penalties must not be applied a second time.
    path_distance = ordered[0].distance_nm if ordered else 0.0
    absorption = {100.0: .012, 400.0: .025, 1600.0: .055}
    reference_absorption = path_distance * absorption[100.0]
    spectral_gains = tuple(
        (band, 10.0 ** (-(path_distance * coefficient
                          - reference_absorption) / 20.0))
        for band, coefficient in absorption.items())
    return PropagationResult(frequency, profile, ordered, reverberation,
                             spectral_gains)


def representative_frequency_hz(signature) -> float:
    """Canonical propagation band closest to a target's own dominant tonal
    frequency (its ``tonal_band_hz`` midpoint), e.g. a fast cavitating
    warship attenuates faster than a slow diesel tanker. Falls back to the
    historical fixed representative band when no usable signature is given
    (unmodeled contacts, e.g. biological), so those keep today's behavior.
    """
    band = getattr(signature, "tonal_band_hz", None) if signature is not None else None
    if not band or band[0] <= 0.0 or band[1] <= 0.0:
        return REPRESENTATIVE_PASSIVE_BAND_HZ
    midpoint = (band[0] + band[1]) / 2.0
    return min(CANONICAL_FREQUENCY_BANDS_HZ,
               key=lambda candidate: abs(candidate - midpoint))


def passive_range_factor(result: PropagationResult, direct_range_nm: float) -> float:
    """Convert modeled excess loss into a range multiplier without re-spreading."""
    distance = _number("direct_range_nm", direct_range_nm, 0.0, MAX_RANGE_NM)
    if result.best_path is None:
        return 0.0
    baseline_loss = 20.0 * math.log10(1.0 + distance)
    excess_loss = max(0.0, result.best_path.loss_db - baseline_loss)
    return 10.0 ** (-excess_loss / 20.0)


# --- ray-traced transmission loss (physics upgrade, phase 4) -----------------

RAY_REFERENCE_KEY = (5.0, 60.0, 13.0, 1000.0, "sand", 10.0)
RAY_REFERENCE_RECEIVER_M = 50.0
RAY_REFERENCE_RANGE_NM = 20.0
_ray_anchor_db: float | None = None


def _profile_from_key(key: tuple):
    from src.world.ocean import (
        SALINITY_PSU, mackenzie_sound_speed, temperature_profile_c)

    _sensor, mld, sst, depth, _sediment, _wind = key
    maximum = min(depth, PROFILE_MAX_DEPTH_M)
    depths = [maximum * index / (PROFILE_SAMPLES - 1)
              for index in range(PROFILE_SAMPLES)]
    speeds = [mackenzie_sound_speed(temperature_profile_c(z, mld, sst),
                                    SALINITY_PSU, z) for z in depths]
    return depths, speeds


def _spherical_db(distance_nm: float) -> float:
    return 20.0 * math.log10(max(1.0, distance_nm * 1852.0))


def ray_anchor_db() -> float:
    """Excess of the reference environment at the reference range; the
    passive figure of merit is anchored there so 1.0.0 ranges hold."""
    global _ray_anchor_db
    if _ray_anchor_db is None:
        from src.sonar import raytrace

        table = raytrace.cached_table(RAY_REFERENCE_KEY, _profile_from_key)
        _ray_anchor_db = raytrace.lookup_tl_db(
            table, REPRESENTATIVE_PASSIVE_BAND_HZ, RAY_REFERENCE_RANGE_NM,
            RAY_REFERENCE_RECEIVER_M, RAY_REFERENCE_KEY[3]) - _spherical_db(
                RAY_REFERENCE_RANGE_NM)
    return _ray_anchor_db


def ray_environment_key(world, sensor_depth_m: float, mid_x: float,
                        mid_y: float) -> tuple | None:
    """Quantized environment at the path midpoint (None without an ocean)."""
    from src.sonar.raytrace import quantize

    ocean = getattr(world, "ocean", None)
    if ocean is None:
        return None
    depth = max(10.0, float(world.depth_m(mid_x, mid_y)))
    return (quantize(sensor_depth_m, 10.0 if sensor_depth_m > 30.0 else 5.0) or 5.0,
            max(10.0, quantize(world.thermocline_depth_m(mid_x, mid_y), 10.0)),
            quantize(ocean.sea_surface_temperature_c(getattr(world, "hour", 12.0)), 1.0),
            quantize(depth, 25.0 if depth < 1000.0 else 100.0) or 25.0,
            world.seabed_at(mid_x, mid_y),
            quantize(float(getattr(world, "wind_speed_kn", 10.0)), 5.0))


def ray_excess_db(world, sensor_x: float, sensor_y: float, sensor_depth_m: float,
                  target_x: float, target_y: float, target_depth_m: float,
                  frequency_hz: float) -> float | None:
    """Ray-traced loss beyond spherical spreading, relative to the anchor.

    Reciprocity: the own sensor is the ray source, the target the receiver,
    so one cached table serves every target seen by that sensor."""
    from src.sonar import raytrace

    mid_x, mid_y = (sensor_x + target_x) * .5, (sensor_y + target_y) * .5
    key = ray_environment_key(world, sensor_depth_m, mid_x, mid_y)
    if key is None:
        return None
    table = raytrace.cached_table(key, _profile_from_key)
    distance = math.hypot(target_x - sensor_x, target_y - sensor_y)
    tl = raytrace.lookup_tl_db(table, frequency_hz, distance,
                               min(target_depth_m, key[3]), key[3])
    return tl - _spherical_db(distance) - ray_anchor_db()
