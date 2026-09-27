"""Bounded, vectorized acoustic ray tracing and transmission-loss tables.

A fan of rays leaves the source with launch angles within +/-FAN_DEG.  Each
ray obeys Snell's law in the range-independent sound-speed profile
(``cos(theta)/c = const``), turns where the invariant demands it, reflects
at the surface (Beckmann-Spizzichino roughness loss) and at the seabed
(Rayleigh fluid-fluid loss of the local sediment).  Ray energy is summed
incoherently on a (range x depth) grid with the geometric flux through each
cell, giving transmission loss ``TL(r, z)`` per canonical band.  Surface
ducts, shadow zones, bottom bounce and convergence zones emerge from the
profile instead of being prescribed.

Tables are pure functions of a quantized environment key and are cached in
a bounded LRU; a table costs one vectorized trace (48 rays x 370 range
steps) and is rebuilt only when the quantized environment changes.
"""

from __future__ import annotations

import math
from collections import OrderedDict

import numpy as np

from src.world.ocean import rayleigh_bottom_loss_db

BANDS_HZ = (100.0, 400.0, 1600.0, 6400.0)
NM_M = 1852.0
FAN_DEG = 20.0
RAYS = 48
MAX_BOUNCES = 12
MAX_RANGE_NM = 80.0
RANGE_STEP_M = 400.0
FINE_BINS = 16            # upper water column (to 400 m)
COARSE_BINS = 4           # below 400 m
FINE_DEPTH_M = 400.0
CACHE_SIZE = 64
# Loss beyond which a cell counts as insonified by nothing (shadow).
SHADOW_TL_DB = 200.0

_cache: "OrderedDict[tuple, np.ndarray]" = OrderedDict()
build_count = 0


def _surface_loss_db(grazing_rad: np.ndarray, wind_kn: float,
                     frequency_hz: float) -> np.ndarray:
    """Coherent surface reflection loss for a rough (wind-driven) sea."""
    # RMS wave height of a fully developed sea, Hs ~ 0.0214 U^2 (U m/s).
    wind = wind_kn * 0.5144
    hs = 0.0214 * wind * wind
    k = 2.0 * math.pi * frequency_hz / 1500.0
    rayleigh = 2.0 * k * (hs / 4.0) * np.sin(grazing_rad)
    coefficient = np.exp(-0.5 * rayleigh ** 2)
    return np.minimum(20.0, -20.0 * np.log10(np.maximum(coefficient, 1e-3)))


def quantize(value: float, step: float) -> float:
    return round(value / step) * step


def depth_edges(water_depth_m: float) -> np.ndarray:
    bottom = max(float(water_depth_m), 5.0)
    fine = np.linspace(0.0, min(bottom, FINE_DEPTH_M), FINE_BINS + 1)
    if bottom <= FINE_DEPTH_M:
        return fine
    return np.concatenate([fine, np.linspace(FINE_DEPTH_M, bottom,
                                             COARSE_BINS + 1)[1:]])


def _profile_speed(depths: np.ndarray, speeds: np.ndarray,
                   z: np.ndarray) -> np.ndarray:
    return np.interp(z, depths, speeds)


def trace_table(source_depth_m: float, profile_depths_m, profile_m_s,
                water_depth_m: float, sediment: str, wind_kn: float) -> np.ndarray:
    """Return TL[band, range_bin, depth_bin] in dB (without absorption)."""
    global build_count
    build_count += 1
    depths = np.asarray(profile_depths_m, dtype=float)
    speeds = np.asarray(profile_m_s, dtype=float)
    bottom = max(float(water_depth_m), 5.0)
    if depths[-1] < bottom:
        # Below the sampled profile the pressure term dominates (+0.017 1/s).
        depths = np.append(depths, bottom)
        speeds = np.append(speeds, speeds[-1] + 0.017 * (bottom - depths[-2]))
    source = min(max(float(source_depth_m), 0.5), bottom - 0.5)
    angles = np.radians(np.linspace(-FAN_DEG, FAN_DEG, RAYS))
    d_theta = abs(angles[1] - angles[0])
    c0 = float(_profile_speed(depths, speeds, np.array([source]))[0])
    xi = np.cos(angles) / c0                     # Snell invariant
    z = np.full(RAYS, source)
    direction = np.sign(np.sin(angles))          # +1 downward
    direction[direction == 0] = 1.0
    energy = np.cos(angles) * d_theta            # 2D fan energy weights
    losses = np.zeros((len(BANDS_HZ), RAYS))
    bounces = np.zeros(RAYS, dtype=int)
    alive = np.ones(RAYS, dtype=bool)
    n_range = int(MAX_RANGE_NM * NM_M / RANGE_STEP_M)
    bin_edges = depth_edges(bottom)
    widths = np.diff(bin_edges)
    centres = 0.5 * (bin_edges[:-1] + bin_edges[1:])
    intensity = np.zeros((len(BANDS_HZ), n_range, len(centres)))
    sediment_loss_cache = {}
    for step in range(n_range):
        r = (step + 1) * RANGE_STEP_M
        c = _profile_speed(depths, speeds, z)
        cos_t = np.clip(xi * c, 0.0, 1.0)
        sin_t = np.sqrt(np.maximum(0.0, 1.0 - cos_t * cos_t))
        # Turning point: the ray becomes horizontal and reverses.
        turning = cos_t >= 0.999999
        direction = np.where(turning, -direction, direction)
        sin_t = np.where(turning, 1e-3, sin_t)
        dz = direction * RANGE_STEP_M * sin_t / np.maximum(cos_t, 1e-3)
        z = z + dz
        hit_surface = z < 0.0
        hit_bottom = z > bottom
        if hit_surface.any():
            z = np.where(hit_surface, -z, z)
            direction = np.where(hit_surface, 1.0, direction)
            grazing = np.arcsin(np.clip(sin_t, 0.0, 1.0))
            for band_index, frequency in enumerate(BANDS_HZ):
                losses[band_index] += np.where(
                    hit_surface, _surface_loss_db(grazing, wind_kn, frequency), 0.0)
            bounces += hit_surface
        if hit_bottom.any():
            z = np.where(hit_bottom, 2.0 * bottom - z, z)
            direction = np.where(hit_bottom, -1.0, direction)
            grazing_deg = np.degrees(np.arcsin(np.clip(sin_t, 0.0, 1.0)))
            key = np.round(grazing_deg, 1)
            loss = np.array([sediment_loss_cache.setdefault(
                (sediment, float(value)), rayleigh_bottom_loss_db(sediment, float(value)))
                for value in key])
            for band_index in range(len(BANDS_HZ)):
                losses[band_index] += np.where(hit_bottom, loss, 0.0)
            bounces += hit_bottom
        z = np.clip(z, 0.0, bottom)
        alive &= bounces <= MAX_BOUNCES
        # Incoherent flux into depth bins with a Gaussian beam footprint;
        # each ray's energy is shared over the bins and divided by bin height.
        width = max(widths[0], 0.5 * r * d_theta)
        weights = np.exp(-0.5 * ((centres[None, :] - z[:, None]) / width) ** 2)
        norm = weights.sum(axis=1, keepdims=True)
        weights = np.where(norm > 0, weights / np.maximum(norm, 1e-12), 0.0)
        weights = weights / widths[None, :]
        flux = energy / (r * np.maximum(cos_t, 1e-3))
        for band_index in range(len(BANDS_HZ)):
            ray_power = np.where(alive, flux * 10.0 ** (-losses[band_index] / 10.0),
                                 0.0)
            intensity[band_index, step] = ray_power @ weights
    with np.errstate(divide="ignore"):
        table = -10.0 * np.log10(np.maximum(intensity, 10.0 ** (-SHADOW_TL_DB / 10.0)))
    return table


def cached_table(key: tuple, profile_builder) -> np.ndarray:
    """TL table for a quantized environment ``key``.

    The result is a pure function of the key, so the cache only saves time:
    save/load, evaluation order or an empty cache never change results.
    ``key`` = (sensor depth, mixed-layer depth, SST, water depth, sediment,
    wind); ``profile_builder(key)`` returns (depths, speeds)."""
    table = _cache.get(key)
    if table is not None:
        _cache.move_to_end(key)
        return table
    depths, speeds = profile_builder(key)
    table = trace_table(key[0], depths, speeds, key[3], key[4], key[5])
    _cache[key] = table
    while len(_cache) > CACHE_SIZE:
        _cache.popitem(last=False)
    return table


def lookup_tl_db(table: np.ndarray, band_hz: float, range_nm: float,
                 receiver_depth_m: float, water_depth_m: float) -> float:
    """Interpolated TL (dB) for one receiver; beyond the table, cylindrical."""
    band_index = BANDS_HZ.index(band_hz)
    n_range = table.shape[1]
    r_m = max(range_nm * NM_M, RANGE_STEP_M)
    edges = depth_edges(water_depth_m)
    depth_index = int(min(len(edges) - 2, max(0, np.searchsorted(
        edges, receiver_depth_m, side="right") - 1)))
    position = r_m / RANGE_STEP_M - 1.0
    if position >= n_range - 1:
        last = table[band_index, n_range - 1, depth_index]
        edge = n_range * RANGE_STEP_M
        return float(last + 10.0 * math.log10(r_m / edge))
    low = int(position)
    fraction = position - low
    return float(table[band_index, low, depth_index] * (1.0 - fraction)
                 + table[band_index, low + 1, depth_index] * fraction)


def clear_cache() -> None:
    global build_count
    _cache.clear()
    _cz_cache.clear()
    build_count = 0


# Convergence zones (plan 1.3, phase 7): ranges beyond CZ_SCAN_MIN_NM where
# the traced transmission loss at the receiver depth falls CZ_PROMINENCE_DB
# below the loss of the surrounding water (excess over spherical spreading),
# i.e. where refracted energy refocuses.  A pure, bounded-cache function.
CZ_BAND_HZ = 400.0
CZ_SCAN_MIN_NM = 15.0
CZ_PROMINENCE_DB = 6.0
CZ_MIN_WIDTH_NM = 1.5
CZ_MAX_BANDS = 4
_cz_cache: "OrderedDict[tuple, tuple]" = OrderedDict()


def convergence_zones_nm(profile_depths_m, profile_m_s, water_depth_m: float,
                         source_depth_m: float, sediment: str, wind_kn: float,
                         receiver_depth_m: float) -> list:
    """[[low_nm, high_nm], ...] of the convergence zones of one profile."""
    key = (tuple(round(float(d), 1) for d in profile_depths_m),
           tuple(round(float(s), 2) for s in profile_m_s),
           round(float(water_depth_m), 1), round(float(source_depth_m), 1),
           str(sediment), round(float(wind_kn), 1), round(float(receiver_depth_m), 1))
    cached = _cz_cache.get(key)
    if cached is not None:
        _cz_cache.move_to_end(key)
        return [list(band) for band in cached]
    bands: list = []
    bottom = max(float(water_depth_m), 5.0)
    if bottom >= 20.0:
        table = trace_table(source_depth_m, profile_depths_m, profile_m_s, bottom,
                            sediment, wind_kn)
        band_index = BANDS_HZ.index(CZ_BAND_HZ)
        edges = depth_edges(bottom)
        depth_index = int(min(len(edges) - 2, max(0, np.searchsorted(
            edges, receiver_depth_m, side="right") - 1)))
        n_range = table.shape[1]
        ranges_m = (np.arange(n_range) + 1.0) * RANGE_STEP_M
        excess = table[band_index, :, depth_index] - 20.0 * np.log10(ranges_m)
        start = int(CZ_SCAN_MIN_NM * NM_M / RANGE_STEP_M)
        scan = excess[start:]
        finite = np.isfinite(scan)
        if finite.sum() > 4:
            level = float(np.median(scan[finite]))
            focused = finite & (scan <= level - CZ_PROMINENCE_DB)
            index = 0
            while index < len(focused) and len(bands) < CZ_MAX_BANDS:
                if not focused[index]:
                    index += 1
                    continue
                end = index
                while end + 1 < len(focused) and focused[end + 1]:
                    end += 1
                low = ranges_m[start + index] / NM_M
                high = ranges_m[start + end] / NM_M
                if high - low >= CZ_MIN_WIDTH_NM:
                    bands.append([round(float(low), 1), round(float(high), 1)])
                index = end + 1
    _cz_cache[key] = tuple(tuple(band) for band in bands)
    while len(_cz_cache) > CACHE_SIZE:
        _cz_cache.popitem(last=False)
    return bands


# --- ray picture for the weather/sonar analysis panel ------------------------

PICTURE_RAYS_DEG = (-12.0, -8.0, -4.0, -1.5, 0.0, 1.5, 4.0, 8.0, 12.0)
PICTURE_POINTS = 64
PICTURE_RANGE_NM = 20.0
PICTURE_STEP_M = 100.0
SHADOW_RANGE_BINS = 25
SHADOW_EXCESS_DB = 10.0
SHADOW_BAND_HZ = 1600.0
_picture_cache: "OrderedDict[tuple, dict]" = OrderedDict()
PICTURE_CACHE_SIZE = 8


def ray_picture(profile_depths_m, profile_m_s, water_depth_m: float,
                source_depth_m: float, sediment: str, wind_kn: float,
                layer_m: float) -> dict:
    """Display rays and an acoustic shadow grid from one (measured) profile.

    ``rays``: a few named launch angles traced with the same Snell stepping
    and surface/seabed reflection as ``trace_table``.  ``shadow``: cells of
    the ``trace_table`` grid within the display range where transmission
    loss exceeds spherical spreading by more than ``SHADOW_EXCESS_DB`` - the
    region no significant ray energy reaches.  Only cells below the measured
    layer and beyond the first range cell count: steep paths the display fan
    does not trace reach the water right under the ship.  A pure function of its
    arguments, cached in a small bounded LRU."""
    depths = tuple(round(float(value), 1) for value in profile_depths_m)
    speeds = tuple(round(float(value), 2) for value in profile_m_s)
    bottom = max(float(water_depth_m), 5.0)
    source = min(max(float(source_depth_m), 0.5), bottom - 0.5)
    key = (depths, speeds, round(bottom, 1), round(source, 1), sediment,
           round(float(wind_kn)), round(float(layer_m), 1))
    cached = _picture_cache.get(key)
    if cached is not None:
        _picture_cache.move_to_end(key)
        return cached
    z_profile = np.asarray(depths, dtype=float)
    c_profile = np.asarray(speeds, dtype=float)
    if z_profile[-1] < bottom:
        z_profile = np.append(z_profile, bottom)
        c_profile = np.append(c_profile, c_profile[-1] + 0.017 * (bottom - z_profile[-2]))
    angles = np.radians(np.array(PICTURE_RAYS_DEG))
    c0 = float(np.interp(source, z_profile, c_profile))
    xi = np.cos(angles) / c0
    z = np.full(len(angles), source)
    direction = np.sign(np.sin(angles))
    direction[direction == 0] = 1.0
    steps = int(PICTURE_RANGE_NM * NM_M / PICTURE_STEP_M)
    stride = max(1, -(-steps // (PICTURE_POINTS - 1)))    # ceil: reach the full range
    paths = [[(0.0, round(source, 1))] for _ in angles]
    for step in range(steps):
        r = (step + 1) * PICTURE_STEP_M
        c = np.interp(z, z_profile, c_profile)
        cos_t = np.clip(xi * c, 0.0, 1.0)
        sin_t = np.sqrt(np.maximum(0.0, 1.0 - cos_t * cos_t))
        turning = cos_t >= 0.999999
        direction = np.where(turning, -direction, direction)
        sin_t = np.where(turning, 1e-3, sin_t)
        z = z + direction * PICTURE_STEP_M * sin_t / np.maximum(cos_t, 1e-3)
        surface, seabed = z < 0.0, z > bottom
        z = np.where(surface, -z, z)
        direction = np.where(surface, 1.0, direction)
        z = np.where(seabed, 2.0 * bottom - z, z)
        direction = np.where(seabed, -1.0, direction)
        z = np.clip(z, 0.0, bottom)
        if (step + 1) % stride == 0 or step == steps - 1:
            for index, depth in enumerate(z):
                if len(paths[index]) < PICTURE_POINTS:
                    paths[index].append((round(r / NM_M, 3), round(float(depth), 1)))
    table = trace_table(source, z_profile, c_profile, bottom, sediment, wind_kn)
    band = BANDS_HZ.index(SHADOW_BAND_HZ)
    edges = depth_edges(bottom)
    per_bin = max(1, int(PICTURE_RANGE_NM * NM_M / RANGE_STEP_M) // SHADOW_RANGE_BINS)
    shadow = []
    for range_bin in range(SHADOW_RANGE_BINS):
        rows = table[band, range_bin * per_bin:(range_bin + 1) * per_bin]
        r_m = ((range_bin + 0.5) * per_bin) * RANGE_STEP_M
        spherical = 20.0 * math.log10(max(r_m, 1.0))
        shadow.append([bool(range_bin > 0 and edges[index] >= layer_m
                            and value - spherical > SHADOW_EXCESS_DB)
                       for index, value in enumerate(rows.mean(axis=0))])
    result = {
        "range_nm": PICTURE_RANGE_NM,
        "rays": [[[r, d] for r, d in path] for path in paths],
        "depth_edges_m": [round(float(edge), 1) for edge in edges],
        "shadow": shadow,
    }
    _picture_cache[key] = result
    while len(_picture_cache) > PICTURE_CACHE_SIZE:
        _picture_cache.popitem(last=False)
    return result
