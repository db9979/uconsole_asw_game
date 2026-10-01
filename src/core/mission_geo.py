"""Mission geography of the boat missions: a strait, a coast to land combat
swimmers on and sea room for a zigzagging supply ship.

Every place is a pure function of the world's coastline and chart depth
(``charted_depth_m``: no tide, so the answer never changes with the clock)
and the scenario's nominal frigate start, cached on the world object.
Nothing here is saved: a loaded game rebuilds the same world from its
snapshot and finds the same places.

- ``strait``: the narrowest passage near the nominal start between two walls
  (land, or water too shallow for a dived boat), ``STRAIT_MIN_NM`` to
  ``STRAIT_MAX_NM`` wide, with open water ``STRAIT_CHANNEL_NM`` along its
  axis on both sides. Without one the gate lies across open water at the
  nominal start (a declared barrier line).
- ``swimmer_zone``: a point off a coast near the nominal start with enough
  water for a dived boat, open sea behind it.
- ``escort_course``: a base course with clear water far enough ahead.
"""

from __future__ import annotations

import math

import numpy as np

from src.core import config

RASTER_NM = 2.0
# A second, coarser look over the whole world when nothing lies near.
WIDE_RASTER_NM = 4.0


def _cache(world) -> dict:
    cache = getattr(world, "_mission_geo_cache", None)
    if cache is None:
        cache = {}
        world._mission_geo_cache = cache
    return cache


def _wall(world, x: float, y: float) -> bool:
    size = float(world.size_nm)
    return (not (1.0 <= x <= size - 1.0 and 1.0 <= y <= size - 1.0)
            or world.on_land(x, y)
            or world.charted_depth_m(x, y) < config.MISSION_GEO_WALL_DEPTH_M)


def _raster(world, cx: float, cy: float, radius: float, step: float = RASTER_NM):
    """Wall cells (land or shallow) and off-world cells on a square window."""
    n = int(radius / step)
    xs = cx + (np.arange(-n, n + 1) * step)
    ys = cy + (np.arange(-n, n + 1) * step)
    size = float(world.size_nm)
    wall = np.zeros((len(ys), len(xs)), dtype=bool)
    outside = np.zeros_like(wall)
    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            if not (1.0 <= x <= size - 1.0 and 1.0 <= y <= size - 1.0):
                outside[j, i] = True
                wall[j, i] = True
            elif world.on_land(float(x), float(y)) or world.charted_depth_m(
                    float(x), float(y)) < config.MISSION_GEO_WALL_DEPTH_M:
                wall[j, i] = True
    return xs, ys, wall, outside


def _shift(grid, di: int, dj: int, fill: bool):
    """``grid`` moved so cell (j, i) reads (j + dj, i + di); outside is ``fill``."""
    out = np.full_like(grid, fill)
    h, w = grid.shape
    src_j = slice(max(0, dj), min(h, h + dj))
    dst_j = slice(max(0, -dj), min(h, h - dj))
    src_i = slice(max(0, di), min(w, w + di))
    dst_i = slice(max(0, -di), min(w, w - di))
    out[dst_j, dst_i] = grid[src_j, src_i]
    return out


def _unit(angle_deg: float) -> tuple[float, float]:
    rad = math.radians(angle_deg)
    return math.sin(rad), -math.cos(rad)


def _ray_nm(world, x, y, angle_deg, limit_nm, step=0.25):
    """Distance to the first wall along ``angle_deg`` (None when open)."""
    ux, uy = _unit(angle_deg)
    d = step
    while d <= limit_nm + 1e-9:
        if _wall(world, x + d * ux, y + d * uy):
            return d
        d += step
    return None


def strait(world, nominal: tuple[float, float]) -> dict:
    """``{x, y, axis, half_nm, natural}``: the gate across the nearest narrow
    passage. ``axis`` is the passage's direction (either way along it)."""
    key = ("strait", round(nominal[0], 3), round(nominal[1], 3))
    cache = _cache(world)
    if key in cache:
        return cache[key]
    result = (_find_strait(world, nominal, config.STRAIT_SEARCH_NM, RASTER_NM)
              or _find_strait(world, nominal, float(world.size_nm), WIDE_RASTER_NM)
              or _open_gate(world, nominal))
    cache[key] = result
    return result


def _find_strait(world, nominal, radius: float, step: float):
    nx, ny = nominal
    xs, ys, wall, outside = _raster(world, nx, ny, radius, step)
    half_cells = int(config.STRAIT_MAX_NM / step)
    channel_cells = int(config.STRAIT_CHANNEL_NM / step)
    gx, gy = np.meshgrid(xs, ys)
    distance = np.hypot(gx - nx, gy - ny)
    best = None
    for index, axis in enumerate(range(0, 180, 15)):
        ux, uy = _unit(axis)
        px, py = _unit(axis + 90.0)
        widths = []
        for sign in (1.0, -1.0):
            hit = np.full(wall.shape, np.inf)
            edge = np.zeros(wall.shape, dtype=bool)
            for k in range(half_cells, 0, -1):
                di, dj = int(round(sign * k * px)), int(round(sign * k * py))
                cell = _shift(wall, di, dj, True)
                off = _shift(outside, di, dj, True)
                hit = np.where(cell, k * step, hit)
                edge = np.where(cell, off, edge)
            widths.append((hit, edge))
        (left, left_edge), (right, right_edge) = widths
        width = left + right
        ok = (~wall & np.isfinite(width) & ~left_edge & ~right_edge
              & (width >= config.STRAIT_MIN_NM) & (width <= config.STRAIT_MAX_NM))
        for sign in (1.0, -1.0):
            for k in range(1, channel_cells + 1):
                di, dj = int(round(sign * k * ux)), int(round(sign * k * uy))
                ok &= ~_shift(wall, di, dj, True)
        if not ok.any():
            continue
        score = np.where(ok, width + config.STRAIT_DISTANCE_WEIGHT * distance, np.inf)
        j, i = np.unravel_index(int(np.argmin(score)), score.shape)
        candidate = (float(score[j, i]), int(j), int(i), index, axis)
        if best is None or candidate[:4] < best[:4]:
            best = candidate
    if best is None:
        return None
    _score, j, i, _index, axis = best
    x, y = float(xs[i]), float(ys[j])
    # Recentre across the passage on the exact coastline.
    left = _ray_nm(world, x, y, axis + 90.0, config.STRAIT_MAX_NM)
    right = _ray_nm(world, x, y, axis - 90.0, config.STRAIT_MAX_NM)
    if left is None or right is None or left + right < config.STRAIT_MIN_NM / 2.0:
        return None
    px, py = _unit(axis + 90.0)
    offset = (left - right) / 2.0
    x, y = x + offset * px, y + offset * py
    return dict(x=x, y=y, axis=float(axis), half_nm=(left + right) / 2.0, natural=True)


def _open_gate(world, nominal):
    x, y = world.nearest_water(*nominal)
    return dict(x=float(x), y=float(y), axis=0.0,
                half_nm=config.STRAIT_OPEN_HALF_NM, natural=False)


def along(point, gate) -> tuple[float, float]:
    """``(along, across)`` of a point in the gate's frame, in NM."""
    ux, uy = _unit(gate["axis"])
    dx, dy = point[0] - gate["x"], point[1] - gate["y"]
    return dx * ux + dy * uy, dx * -uy + dy * ux


def walk(world, x, y, angle_deg, distances):
    """The first of ``distances`` along ``angle_deg`` on open, reachable water."""
    ux, uy = _unit(angle_deg)
    for distance in distances:
        px, py = x + distance * ux, y + distance * uy
        if (not _wall(world, px, py) and world.charted_depth_m(px, py)
                >= config.BOAT_GOAL_MIN_DEPTH_M
                and not world.land_blocks_line(x, y, px, py)):
            return float(px), float(py)
    return None


def swimmer_zone(world, nominal: tuple[float, float]) -> dict | None:
    """``{x, y, seaward}``: where the boat lands its swimmers, off the coast
    nearest the nominal start; ``seaward`` points away from the coast."""
    key = ("swimmers", round(nominal[0], 3), round(nominal[1], 3))
    cache = _cache(world)
    if key in cache:
        return cache[key]
    result = (_find_swimmer_zone(world, nominal, config.SWIMMER_SEARCH_NM, RASTER_NM)
              or _find_swimmer_zone(world, nominal, float(world.size_nm), WIDE_RASTER_NM))
    cache[key] = result
    return result


def _find_swimmer_zone(world, nominal, radius: float, step: float):
    nx, ny = nominal
    xs, ys, wall, outside = _raster(world, nx, ny, radius, step)
    land = wall & ~outside
    near = np.zeros(wall.shape, dtype=bool)
    for dj in (-1, 0, 1):
        for di in (-1, 0, 1):
            if di or dj:
                near |= _shift(land, di, dj, False)
    candidates = ~wall & near
    order = []
    for j, i in zip(*np.nonzero(candidates)):
        order.append((math.hypot(xs[i] - nx, ys[j] - ny), int(j), int(i)))
    for _distance, j, i in sorted(order):
        # Seaward: away from the land cells around it.
        sx = sy = 0.0
        for dj in range(-2, 3):
            for di in range(-2, 3):
                jj, ii = j + dj, i + di
                if 0 <= jj < wall.shape[0] and 0 <= ii < wall.shape[1] and land[jj, ii]:
                    sx -= di
                    sy -= dj
        if sx == 0.0 and sy == 0.0:
            continue
        seaward = math.degrees(math.atan2(sx, -sy)) % 360.0
        x0, y0 = float(xs[i]), float(ys[j])
        # Open sea behind the zone, for the boat's approach.
        if walk(world, x0, y0, seaward, (config.SWIMMER_APPROACH_NM,)) is None:
            continue
        # Step off the coast until the water carries a dived boat.
        ux, uy = _unit(seaward)
        for step in range(0, 25):
            d = step * 0.25
            px, py = x0 + d * ux, y0 + d * uy
            if _wall(world, px, py):
                continue
            if (world.charted_depth_m(px, py) >= config.SWIMMER_MIN_WATER_M
                    and _ray_nm(world, px, py, (seaward + 180.0) % 360.0,
                                config.SWIMMER_COAST_NM) is not None):
                return dict(x=float(px), y=float(py), seaward=float(seaward))
    return None


def escort_course(world, start: tuple[float, float], course: float) -> float:
    """``course`` or the nearest turn of it with clear water far ahead."""
    key = ("escort", round(start[0], 3), round(start[1], 3), round(course, 3))
    cache = _cache(world)
    if key in cache:
        return cache[key]
    result = float(course) % 360.0
    for delta in (0, 30, -30, 60, -60, 90, -90, 120, -120, 150, -150, 180):
        heading = (course + delta) % 360.0
        ux, uy = _unit(heading)
        reach = config.ESCORT_CLEAR_NM
        if all(not _wall(world, start[0] + d * ux, start[1] + d * uy)
               for d in np.arange(2.0, reach + 0.1, 2.0)) and not world.land_blocks_line(
                start[0], start[1], start[0] + reach * ux, start[1] + reach * uy):
            result = float(heading)
            break
    cache[key] = result
    return result
