"""Horizon view shared by the periscope and the bridge lookout page.

Sky and sea in the light of the hour, haze from the visibility, the
horizon in motion from the wave slope, a true-bearing scale, an optional
crosshair and procedural outlines of what the eye made out.  Callers pass
detached ``(bearing, span_deg, cls, stale)`` rows; nothing here reads an
entity.
"""

from collections import OrderedDict
import math

import numpy as np
import pygame

from src.core import config
from src.core.i18n import raw_text
from src.physics import ship_dynamics
from src.ui import layout, silhouettes

SKY_DAY = ((25, 70, 92), (111, 151, 157))
SKY_NIGHT = ((5, 14, 27), (38, 53, 62))
SEA_DAY, SEA_NIGHT = (9, 54, 67), (7, 35, 48)
HAZE = (150, 160, 165)
SCALE_COLOR = (220, 225, 225)
CROSSHAIR_COLOR = (235, 235, 210)
# Horizon motion: px per rad of wave slope, bounded.
MOTION_PX_PER_RAD = 260.0
# Charted coast on the horizon: rays per full circle, the observer's move that
# re-casts them, the bounded cache, and the assumed coastal heights (m; the
# chart has no elevation, so hills vary smoothly along the coast).
LAND_RAYS = 720
LAND_RECAST_NM = 0.1
LAND_CACHE_MAX = 4
LAND_HEIGHT_M = (25.0, 70.0)
LAND_DAY, LAND_NIGHT = (52, 66, 52), (14, 22, 24)
_LAND_CACHE = OrderedDict()


def _coast_segments(world, x, y, reach_nm):
    """Coastline edges within ``reach_nm`` of the observer, as (N, 4) arrays."""
    coast = getattr(world, "coast", None)
    rows = []
    for mass in getattr(coast, "landmasses", ()):
        left, top, right, bottom = mass.bounds
        if right < x - reach_nm or left > x + reach_nm or bottom < y - reach_nm \
                or top > y + reach_nm:
            continue
        points = np.asarray(mass.points, dtype=float)
        rows.append(np.hstack((points, np.roll(points, -1, axis=0))))
    if not rows:
        return np.zeros((0, 4))
    edges = np.vstack(rows)
    ax, ay, bx, by = edges.T
    # Drop edges wholly outside the reach (a cheap box test).
    near = ((np.minimum(ax, bx) <= x + reach_nm) & (np.maximum(ax, bx) >= x - reach_nm)
            & (np.minimum(ay, by) <= y + reach_nm) & (np.maximum(ay, by) >= y - reach_nm))
    return edges[near]


def land_profile(world, x: float, y: float, reach_nm: float):
    """Distance (NM) to the charted coast along each of ``LAND_RAYS`` true
    bearings from (x, y), ``inf`` where no coast lies within ``reach_nm``,
    and the assumed coast height (m) there.  Known geography only; the
    result is cached per rounded position (bounded, display only)."""
    key = (id(getattr(world, "coast", None)), round(x / LAND_RECAST_NM),
           round(y / LAND_RECAST_NM), round(reach_nm, 1))
    cached = _LAND_CACHE.get(key)
    if cached is not None:
        _LAND_CACHE.move_to_end(key)
        return cached
    edges = _coast_segments(world, x, y, reach_nm)
    angles = np.radians(np.arange(LAND_RAYS) * (360.0 / LAND_RAYS))
    distance = np.full(LAND_RAYS, np.inf)
    if len(edges):
        rx, ry = np.sin(angles)[:, None], -np.cos(angles)[:, None]
        ax, ay, bx, by = (edges[:, index][None, :] for index in range(4))
        sx, sy = bx - ax, by - ay
        qx, qy = ax - x, ay - y
        denom = rx * sy - ry * sx
        with np.errstate(divide="ignore", invalid="ignore"):
            t = (qx * sy - qy * sx) / denom
            u = (qx * ry - qy * rx) / denom
        hit = (np.abs(denom) > 1e-12) & (t > 1e-6) & (u >= 0.0) & (u <= 1.0)
        t = np.where(hit, t, np.inf)
        distance = t.min(axis=1)
        distance[distance > reach_nm] = np.inf
    hx = x + np.sin(angles) * np.where(np.isfinite(distance), distance, 0.0)
    hy = y - np.cos(angles) * np.where(np.isfinite(distance), distance, 0.0)
    low, high = LAND_HEIGHT_M
    wave = 0.5 + 0.25 * np.sin(hx * 2.3 + hy * 1.1) + 0.25 * np.sin(hx * 0.7 - hy * 3.1)
    height = low + (high - low) * np.clip(wave, 0.0, 1.0)
    result = (distance, height)
    _LAND_CACHE[key] = result
    while len(_LAND_CACHE) > LAND_CACHE_MAX:
        _LAND_CACHE.popitem(last=False)
    return result


def land_view(world, x: float, y: float, eye_height_m: float):
    """The coast an eye at ``eye_height_m`` above (x, y) can see: the land
    profile limited by the geometric horizon of the hills and the lookout's
    land range."""
    reach = min(config.LOOKOUT_LAND_RANGE_NM,
                1.17 * (math.sqrt(max(0.0, eye_height_m)) + math.sqrt(LAND_HEIGHT_M[1])))
    return land_profile(world, x, y, reach)


def _draw_land(s, rect, land, *, line_of_sight, fov_deg, horizon, tilt, night,
               visibility_nm, haze_color) -> None:
    distance, height = land
    px_per_deg = rect.w / fov_deg
    step = 360.0 / len(distance)
    base_color = LAND_NIGHT if night else LAND_DAY
    first = int(math.floor((line_of_sight - fov_deg / 2) / step)) - 1
    last = int(math.ceil((line_of_sight + fov_deg / 2) / step)) + 1
    column = None
    for index in range(first, last + 1):
        d = float(distance[index % len(distance)])
        bearing = index * step
        px = rect.centerx + relative_offset(bearing, line_of_sight) * px_per_deg
        if not math.isfinite(d) or d > visibility_nm:
            column = None
            continue
        rise = math.degrees(math.atan2(float(height[index % len(distance)]),
                                       max(d, 0.02) * 1852.0)) * px_per_deg
        base = horizon + math.tan(tilt) * (px - rect.centerx)
        top = base - max(2.0, rise)
        fade = min(1.0, d / max(visibility_nm, 0.1))
        color = blend(base_color, haze_color, 0.25 + 0.6 * fade)
        if column is not None:
            x0, top0, base0 = column
            if px - x0 < rect.w:
                pygame.draw.polygon(s, color, [(x0, top0), (px, top), (px, base + 1),
                                               (x0, base0 + 1)])
        column = (px, top, base)


def relative_offset(bearing: float, line_of_sight: float) -> float:
    """Signed angle from the line of sight to ``bearing`` (-180..180)."""
    return (bearing - line_of_sight + 180.0) % 360.0 - 180.0


def blend(a, b, t: float) -> tuple:
    t = config.clamp(t, 0.0, 1.0)
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def horizon_motion(seed: int, sim_t: float, sea_state: float) -> tuple:
    """(vertical offset px, tilt rad) of the horizon from the wave slope at
    ``seed`` (display only, deterministic in sim time)."""
    slope = ship_dynamics.wave_slope_rad(int(seed), sim_t, sea_state)
    offset = config.clamp(slope * MOTION_PX_PER_RAD, -40.0, 40.0)
    tilt = config.clamp(slope * 0.6, -0.25, 0.25)
    return offset, tilt


def draw_outline(s, cls: str, cx: int, base_y: int, width: int, color,
                 t: float = 0.0) -> None:
    """Procedural side view of a coarse class, ``width`` px long, sitting on
    the horizon (aircraft: hovering above it).  ``t`` (display clock)
    animates pitch, radar, rotor and wake."""
    width = max(3, int(width))
    if cls == "torpedo":
        left = cx - width // 2
        pygame.draw.line(s, silhouettes.FOAM, (left, base_y + 1), (left + width, base_y + 1),
                         max(1, min(3, width // 12)))
        return
    silhouettes.draw_profile(s, cls if cls in silhouettes.PROFILES else "unknown",
                             cx, base_y, width, color, t=t)


def draw_horizon(s, rect, *, line_of_sight: float, fov_deg: float, night: bool,
                 visibility_nm: float, motion: tuple, outlines, crosshair_deg=None,
                 land=None, anim_t: float = 0.0) -> None:
    """The picture in the eyepiece or binoculars: sky, sea, the horizon in
    motion, the true-bearing scale, the outlines within the field and an
    optional crosshair with its measuring window (half width in degrees)."""
    rect = pygame.Rect(rect)
    haze = 1.0 - config.clamp(visibility_nm / config.WEATHER_VISIBILITY_MAX_NM, 0.0, 1.0)
    sky_top, sky_bottom = SKY_NIGHT if night else SKY_DAY
    sea = SEA_NIGHT if night else SEA_DAY
    haze_color = blend(HAZE, (40, 48, 54), 0.8 if night else 0.0)
    offset, tilt = motion
    horizon = rect.y + int(rect.h * 0.5 + offset)
    with layout.clip_to(s, rect):
        for py in range(rect.y, rect.bottom):
            t = (py - rect.y) / max(1, rect.h - 1)
            pygame.draw.line(s, blend(blend(sky_top, sky_bottom, t), haze_color, haze * 0.6),
                             (rect.x, py), (rect.right, py))
        dy = int(math.tan(tilt) * rect.w / 2)
        sea_color = blend(sea, haze_color, haze * 0.4)
        pygame.draw.polygon(s, sea_color, [(rect.x, horizon - dy), (rect.right, horizon + dy),
                                           (rect.right, rect.bottom), (rect.x, rect.bottom)])
        pygame.draw.line(s, blend(sea_color, (200, 210, 210), 0.35),
                         (rect.x, horizon - dy), (rect.right, horizon + dy), 1)
        if land is not None:
            _draw_land(s, rect, land, line_of_sight=line_of_sight, fov_deg=fov_deg,
                       horizon=horizon, tilt=tilt, night=night,
                       visibility_nm=visibility_nm, haze_color=haze_color)
        px_per_deg = rect.w / fov_deg
        dark = (60, 66, 72) if night else (28, 34, 40)
        for bearing, span_deg, cls, stale in outlines:
            off = relative_offset(bearing, line_of_sight)
            if abs(off) > fov_deg / 2 + span_deg / 2:
                continue
            cx = rect.centerx + int(off * px_per_deg)
            base = horizon + int(math.tan(tilt) * (cx - rect.centerx))
            width = min(rect.w, max(3, int(span_deg * px_per_deg)))
            draw_outline(s, cls, cx, base, width,
                         blend(dark, haze_color, 0.5 if stale else haze * 0.5), anim_t)
        first = int(math.floor((line_of_sight - fov_deg / 2) / 5.0)) * 5
        for tick in range(first, first + int(fov_deg) + 10, 5):
            off = relative_offset(tick, line_of_sight)
            if abs(off) > fov_deg / 2:
                continue
            tx = rect.x + int((off + fov_deg / 2) * px_per_deg)
            major = tick % 10 == 0
            pygame.draw.line(s, SCALE_COLOR, (tx, rect.y), (tx, rect.y + (10 if major else 5)), 1)
            if major and rect.h >= 40:
                layout.blit_line(s, raw_text(f"{tick % 360:03d}"), (tx - 16, rect.y + 11, 32, 13),
                                 SCALE_COLOR, size=11, align="center")
        if crosshair_deg is not None:
            pygame.draw.line(s, CROSSHAIR_COLOR, (rect.centerx, rect.y + 26),
                             (rect.centerx, rect.bottom), 1)
            window = int(crosshair_deg * px_per_deg)
            pygame.draw.line(s, CROSSHAIR_COLOR, (rect.centerx - window, rect.centery),
                             (rect.centerx + window, rect.centery), 1)
        pygame.draw.rect(s, CROSSHAIR_COLOR, rect, 1)
