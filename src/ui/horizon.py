"""Horizon view shared by the periscope and the bridge lookout page.

Sky and sea in the light of the hour, haze from the visibility, the
horizon in motion from the wave slope, a true-bearing scale, an optional
crosshair and procedural outlines of what the eye made out.  Callers pass
detached ``(bearing, span_deg, cls, stale)`` rows; nothing here reads an
entity.
"""

import base64
from collections import OrderedDict
import math
from typing import NamedTuple

import numpy as np
import pygame

from src.core import config
from src.core.i18n import message, raw_text
from src.physics import ship_dynamics
from src.sensors import nav_lights
from src.ui import layout, quality, ship_way, sight_events_view, sight_scene, silhouettes, unit_models
from src.world import real_relief

SCALE_COLOR = (170, 232, 208)
CROSSHAIR_COLOR = (120, 214, 180)
SCALE_LABEL_MIN_PX = 36
# Horizon motion: px per rad of wave slope, bounded.
MOTION_PX_PER_RAD = 260.0
# A stabilized binocular or periscope keeps this share of the hull motion.
STABILIZED_RESIDUAL = 0.12
# An aircraft lower than this above the sea horizon (a helicopter hovering
# over its dipping sonar, the own helicopter close aboard) is drawn against
# the moving sea horizon in front of the sea, not hidden behind it.
LOW_AIR_DEG = 1.0
# The bridge lookout's eye over the sea (``visual.LOOKOUT_EYE_HEIGHT_M``),
# the default eye of a picture whose own way names none.
DEFAULT_EYE_M = 18.0
# Charted coast on the horizon: rays per full circle, the observer's move that
# re-casts them, the bounded cache.  A real sector reads the real land heights
# (src/world/real_relief.py) out to ``LAND_VIEW_MAX_NM`` and draws them in
# ``LAND_BANDS_NM`` staggered ranges (far ranges paler in the haze); any other
# coast keeps the assumed heights ``LAND_HEIGHT_M`` varying smoothly along it.
LAND_RAYS = 720
LAND_RECAST_NM = 0.1
LAND_CACHE_MAX = 4
LAND_HEIGHT_M = (25.0, 70.0)
LAND_VIEW_MAX_NM = real_relief.MARGIN_NM
LAND_BANDS_NM = (0.0, 4.0, 12.0, math.inf)
LAND_SAMPLES = 56
# The lowest coast (m) where the chart has land but the relief grid is water.
COAST_MIN_M = 10.0
# Rays to each side over which a crest's colour is averaged.
LAND_COLOR_SMOOTH = 4
# The haze over land: this share close aboard, rising with the square of
# the range over the visibility.
LAND_HAZE_MIN, LAND_HAZE = 0.06, 0.8
LAND_NIGHT = (8, 20, 26)
# Land colours of the Tiefenkontakt terrain (sand, grass, rock, snow).
LAND_SAND, LAND_GRASS = (138, 132, 112), (77, 90, 68)
LAND_ROCK, LAND_SNOW = (95, 95, 90), (217, 220, 220)
LAND_DAY = LAND_GRASS
_LAND_CACHE = OrderedDict()


class LandView(NamedTuple):
    """What the eye sees of the land, per band (near to far) and true
    bearing ray: the crest's rise above the sea horizon (deg, NaN where the
    band shows no land), its range (NM) and its day colour (RGB)."""
    rise: np.ndarray
    distance: np.ndarray
    color: np.ndarray


def snow_line_m(latitude: float) -> float:
    """Height (m) above which the land shows snow at ``latitude``."""
    return config.clamp(4600.0 - 66.0 * abs(latitude), 600.0, 4600.0)


def land_colors(height, slope, snow_m: float) -> np.ndarray:
    """Day colours (N, 3) of land ``height`` (m) on a ``slope`` (m per m):
    sand at the waterline, grass turning to rock with height and steepness,
    snow above ``snow_m`` (rock where too steep to hold it)."""
    height, slope = np.asarray(height, dtype=float), np.asarray(slope, dtype=float)
    sand, grass = np.array(LAND_SAND, float), np.array(LAND_GRASS, float)
    rock, snow = np.array(LAND_ROCK, float), np.array(LAND_SNOW, float)
    to_rock = np.clip(slope * 2.0 + height / (snow_m * 1.4), 0.0, 1.0)[..., None]
    green = grass + (rock - grass) * to_rock
    bare = np.clip(slope * 1.5, 0.0, 1.0)[..., None]
    white = snow + (rock - snow) * bare
    color = np.where((height > snow_m)[..., None], white, green)
    color = np.where((height < 6.0)[..., None], sand, color)
    return np.round(color).astype(np.uint8)


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


def coast_distance(world, x: float, y: float, reach_nm: float) -> np.ndarray:
    """Distance (NM) to the charted coast along each of ``LAND_RAYS`` true
    bearings from (x, y), ``inf`` where no coast lies within ``reach_nm``."""
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
    return distance


def _sea_hidden_m(distance_nm, eye_m: float):
    """Height (m) of land at ``distance_nm`` hidden behind the sea horizon of
    an eye ``eye_m`` up (the geometric range 1.17 * (sqrt(eye) + sqrt(h)))."""
    beyond = np.maximum(0.0, np.asarray(distance_nm) - 1.17 * math.sqrt(max(0.0, eye_m)))
    return (beyond / 1.17) ** 2


def _rise_deg(height_m, distance_nm, eye_m: float):
    visible = np.asarray(height_m) - _sea_hidden_m(distance_nm, eye_m)
    return np.degrees(np.arctan2(visible, np.maximum(distance_nm, 0.02) * 1852.0))


def _assumed_land(world, x, y, eye_m, reach_nm) -> LandView:
    """The coast at the assumed heights (a coast without real relief)."""
    distance = coast_distance(world, x, y, reach_nm)
    angles = np.radians(np.arange(LAND_RAYS) * (360.0 / LAND_RAYS))
    hx = x + np.sin(angles) * np.where(np.isfinite(distance), distance, 0.0)
    hy = y - np.cos(angles) * np.where(np.isfinite(distance), distance, 0.0)
    low, high = LAND_HEIGHT_M
    wave = 0.5 + 0.25 * np.sin(hx * 2.3 + hy * 1.1) + 0.25 * np.sin(hx * 0.7 - hy * 3.1)
    height = low + (high - low) * np.clip(wave, 0.0, 1.0)
    with np.errstate(invalid="ignore"):
        rise = np.where(np.isfinite(distance), _rise_deg(height, distance, eye_m), np.nan)
    color = np.broadcast_to(np.array(LAND_DAY, np.uint8), (1, LAND_RAYS, 3)).copy()
    return LandView(rise[None, :], distance[None, :], color)


def _real_land(world, relief, x, y, eye_m, reach_nm, latitude) -> LandView:
    """The real land out to ``reach_nm``: per band the highest crest above
    the sea horizon.  The chart's coast (cast out to the assumed coast's
    reach) decides where the near land begins; farther out the relief
    alone tells land from water."""
    near_reach = min(reach_nm, 1.17 * (math.sqrt(max(0.0, eye_m)) + math.sqrt(LAND_HEIGHT_M[1])))
    coast = coast_distance(world, x, y, near_reach)
    angles = np.radians(np.arange(LAND_RAYS) * (360.0 / LAND_RAYS))
    ray_x, ray_y = np.sin(angles)[:, None], -np.cos(angles)[:, None]
    steps = (np.linspace(0.0, 1.0, LAND_SAMPLES) ** 1.6 * reach_nm)[None, :]
    first = np.where(np.isfinite(coast), coast + 0.02, near_reach)[:, None]
    ranges = np.hstack((first, np.broadcast_to(steps, (LAND_RAYS, LAND_SAMPLES))))
    height = relief.heights(x + ray_x * ranges, y + ray_y * ranges)
    # On the chart's coast the land stands at least COAST_MIN_M high.
    height[:, 0] = np.where(np.isfinite(coast), np.maximum(height[:, 0], COAST_MIN_M), 0.0)
    # Water before the chart's coast stays water.
    sea = (ranges < near_reach) & (ranges < coast[:, None])
    height = np.where(sea, 0.0, height)
    with np.errstate(invalid="ignore"):
        rise = np.where(height > 0.0, _rise_deg(height, ranges, eye_m), -np.inf)
    bands = len(LAND_BANDS_NM) - 1
    rows = np.arange(LAND_RAYS)
    out_rise = np.full((bands, LAND_RAYS), np.nan)
    out_distance = np.full((bands, LAND_RAYS), np.inf)
    crest_x = np.zeros((bands, LAND_RAYS))
    crest_y = np.zeros((bands, LAND_RAYS))
    crest_h = np.zeros((bands, LAND_RAYS))
    for band in range(bands):
        low, high = LAND_BANDS_NM[band], LAND_BANDS_NM[band + 1]
        inside = np.where((ranges >= low) & (ranges < high), rise, -np.inf)
        best = inside.argmax(axis=1)
        value = inside[rows, best]
        seen = np.isfinite(value) & (value > 0.0)
        out_rise[band] = np.where(seen, value, np.nan)
        out_distance[band] = np.where(seen, ranges[rows, best], np.inf)
        crest_x[band] = x + ray_x[:, 0] * ranges[rows, best]
        crest_y[band] = y + ray_y[:, 0] * ranges[rows, best]
        crest_h[band] = height[rows, best]
    # The slope at each crest from the relief around it (m per m).
    probe = 0.5
    gx = (relief.heights(crest_x + probe, crest_y) - relief.heights(crest_x - probe, crest_y))
    gy = (relief.heights(crest_x, crest_y + probe) - relief.heights(crest_x, crest_y - probe))
    slope = np.hypot(gx, gy) / (2.0 * probe * 1852.0 * relief.scale)
    color = land_colors(crest_h, slope, snow_line_m(latitude)).astype(float)
    # Smooth the colours along each band (over the rays that show land), so
    # neighbouring crests blend rather than stand in stripes.
    seen = np.isfinite(out_rise)[..., None].astype(float)
    total, weight = np.zeros_like(color), np.zeros_like(seen)
    for shift in range(-LAND_COLOR_SMOOTH, LAND_COLOR_SMOOTH + 1):
        total += np.roll(color * seen, shift, axis=1)
        weight += np.roll(seen, shift, axis=1)
    color = np.where(weight > 0, total / np.maximum(weight, 1e-9), color)
    return LandView(out_rise, out_distance, np.round(color).astype(np.uint8))


def land_profile(world, x: float, y: float, reach_nm: float, eye_m: float = DEFAULT_EYE_M):
    """The land an eye ``eye_m`` above (x, y) sees out to ``reach_nm`` as a
    ``LandView`` over ``LAND_RAYS`` true bearings.  Known geography only;
    the result is cached per rounded position (bounded, display only)."""
    coast = getattr(world, "coast", None)
    key = (id(coast), round(x / LAND_RECAST_NM), round(y / LAND_RECAST_NM),
           round(reach_nm, 1), round(eye_m, 1))
    cached = _LAND_CACHE.get(key)
    if cached is not None:
        _LAND_CACHE.move_to_end(key)
        return cached
    relief = real_relief.for_coast(coast)
    if relief is None:
        result = _assumed_land(world, x, y, eye_m, reach_nm)
    else:
        latitude = float(coast.metadata["center"]["latitude"])
        result = _real_land(world, relief, x, y, eye_m, reach_nm, latitude)
    _LAND_CACHE[key] = result
    while len(_LAND_CACHE) > LAND_CACHE_MAX:
        _LAND_CACHE.popitem(last=False)
    return result


def land_view(world, x: float, y: float, eye_height_m: float) -> LandView:
    """The land an eye at ``eye_height_m`` above (x, y) can see: the charted
    coast within the geometric horizon of the hills and the lookout's land
    range; with a real relief the mountains out to their own horizon
    (at most ``LAND_VIEW_MAX_NM``)."""
    eye = math.sqrt(max(0.0, eye_height_m))
    relief = real_relief.for_coast(getattr(world, "coast", None))
    if relief is None:
        reach = min(config.LOOKOUT_LAND_RANGE_NM, 1.17 * (eye + math.sqrt(LAND_HEIGHT_M[1])))
    else:
        reach = min(LAND_VIEW_MAX_NM,
                    1.17 * (eye + math.sqrt(max(LAND_HEIGHT_M[1], relief.peak_m))))
    return land_profile(world, x, y, reach, eye_height_m)


def land_nearest(land: LandView) -> np.ndarray:
    """Range (NM) of the nearest land in sight along each ray, ``inf``
    where the eye sees none."""
    seen = np.isfinite(land.rise)
    return np.where(seen, land.distance, np.inf).min(axis=0)


# The land for the browser: every ``LAND_WIRE_STRIDE``-th ray, per band and
# ray the rise (0.01 deg, 0xFFFF none), the range (``LAND_WIRE_NM`` steps)
# and the day colour, six bytes, base64.
LAND_WIRE_STRIDE = 2
LAND_WIRE_NM = 0.25
_LAND_WIRE = OrderedDict()


def land_wire(land: LandView | None) -> dict | None:
    """``land`` packed for the browser's horizon (``sight-scene.js``), None
    without land in sight."""
    if land is None or not np.isfinite(land.rise).any():
        return None
    cached = _LAND_WIRE.get(id(land))
    if cached is not None and cached[0] is land:
        return cached[1]
    rise = land.rise[:, ::LAND_WIRE_STRIDE]
    distance = land.distance[:, ::LAND_WIRE_STRIDE]
    color = land.color[:, ::LAND_WIRE_STRIDE]
    bands, rays = rise.shape
    packed = np.zeros((bands, rays, 6), dtype=np.uint8)
    seen = np.isfinite(rise) & np.isfinite(distance)
    centi = np.where(seen, np.clip(np.round(np.nan_to_num(rise) * 100.0), 0, 0xFFFE),
                     0xFFFF).astype(np.uint16)
    packed[..., 0] = centi & 0xFF
    packed[..., 1] = centi >> 8
    packed[..., 2] = np.where(seen, np.clip(np.round(np.nan_to_num(distance, posinf=0.0)
                                                     / LAND_WIRE_NM), 1, 255), 0)
    packed[..., 3:] = color
    wire = dict(rays=int(rays), bands=int(bands),
                data=base64.b64encode(packed.tobytes()).decode("ascii"))
    _LAND_WIRE[id(land)] = (land, wire)
    while len(_LAND_WIRE) > LAND_CACHE_MAX:
        _LAND_WIRE.popitem(last=False)
    return wire


def land_shade(color, light: float):
    """A day land colour in the light of the hour (0 night .. 1 day)."""
    return blend(LAND_NIGHT, [int(channel) for channel in color],
                 config.clamp(light * 1.25, 0.0, 1.0))


# A drawn land column is at most this wide (px): in the narrow binocular or
# periscope field the rays are spread, so heights and colours are blended
# between them.
LAND_COLUMN_PX = 6.0


def _land_columns(land, band, line_of_sight, fov_deg, px_per_deg):
    """Bearings across the field (deg, relative to the line of sight) and the
    band's rise, range and day colour there, blended between the rays."""
    rays = land.rise.shape[1]
    step = 360.0 / rays
    sub = max(1, int(math.ceil(step * px_per_deg / LAND_COLUMN_PX)))
    first = int(math.floor((line_of_sight - fov_deg / 2) / step)) - 1
    last = int(math.ceil((line_of_sight + fov_deg / 2) / step)) + 1
    position = np.arange(first * sub, last * sub + 1) / sub
    index = np.floor(position).astype(int)
    t = (position - index)[:, None]
    a, b = index % rays, (index + 1) % rays
    rise, distance = land.rise[band], land.distance[band]
    color = land.color[band].astype(float)
    both = np.isfinite(rise[a]) & np.isfinite(rise[b])
    near = np.where(t[:, 0] < 0.5, a, b)
    with np.errstate(invalid="ignore"):
        blended_rise = np.where(both, rise[a] * (1 - t[:, 0]) + rise[b] * t[:, 0], rise[near])
        blended_distance = np.where(both, distance[a] * (1 - t[:, 0]) + distance[b] * t[:, 0],
                                    distance[near])
    blended_color = np.where(both[:, None], color[a] * (1 - t) + color[b] * t, color[near])
    offset = (position * step - line_of_sight + 180.0) % 360.0 - 180.0
    return (offset.tolist(), blended_rise.tolist(), blended_distance.tolist(),
            blended_color.tolist())


def _draw_land(s, rect, land, *, line_of_sight, fov_deg, horizon, tilt, light,
               visibility_nm, haze_color, colors=None) -> None:
    """The land bands far to near, each a run of polygons from the moving
    sea horizon up to its crests; neighbouring columns of one colour share
    one polygon."""
    px_per_deg = rect.w / fov_deg
    rim = None if colors is None else colors["rim"]
    visibility = max(visibility_nm, 0.1)
    for band in reversed(range(land.rise.shape[0])):
        run, run_color, run_fade = [], None, 0.0
        for off, a, d, day in zip(*_land_columns(land, band, line_of_sight, fov_deg,
                                                 px_per_deg)):
            px = rect.centerx + off * px_per_deg
            if not math.isfinite(d) or d > visibility or not a == a:
                _flush_land(s, run, run_color, rim, haze_color, run_fade)
                run, run_color = [], None
                continue
            if run and px - run[-1][0] >= rect.w:
                _flush_land(s, run, run_color, rim, haze_color, run_fade)
                run = []
            base = horizon + math.tan(tilt) * (px - rect.centerx)
            point = (px, base - max(2.0, a * px_per_deg), base)
            fade = min(1.0, d / visibility)
            color = blend(land_shade(day, light), haze_color, LAND_HAZE_MIN + LAND_HAZE * fade * fade)
            color = tuple(channel - channel % 3 for channel in color)
            if run and color != run_color:
                run.append(point)
                _flush_land(s, run, run_color, rim, haze_color, run_fade)
                run = [point]
            else:
                run.append(point)
            run_color, run_fade = color, fade
        _flush_land(s, run, run_color, rim, haze_color, run_fade)


def _flush_land(s, run, color, rim, haze_color, fade) -> None:
    if len(run) < 2 or color is None:
        return
    top = [(px, y) for px, y, _ in run]
    pygame.draw.polygon(s, color, top + [(px, base + 1) for px, _, base in reversed(run)])
    if rim is not None:
        pygame.draw.lines(s, blend(rim, haze_color, 0.3 + 0.6 * fade), False, top, 1)


def row_range(row) -> float:
    """An eyepiece row's range, NM (10th column); infinite when unknown, so
    the row stands on the horizon and behind every ranged one."""
    value = row[9] if len(row) > 9 else None
    return math.inf if value is None or not math.isfinite(value) or value <= 0.0 else float(value)


def relative_offset(bearing: float, line_of_sight: float) -> float:
    """Signed angle from the line of sight to ``bearing`` (-180..180)."""
    return (bearing - line_of_sight + 180.0) % 360.0 - 180.0


def blend(a, b, t: float) -> tuple:
    t = config.clamp(t, 0.0, 1.0)
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def hull_motion(seed: int, sim_t: float, sea_state: float,
                sea_rel_deg: float | None = None) -> tuple:
    """(pitch, roll) wave slopes in rad of a hull ``sea_rel_deg`` off the sea
    (the direction the waves come from, relative to the bow): head or
    following seas make her pitch, beam seas roll (display only,
    deterministic in sim time)."""
    pitch = ship_dynamics.wave_slope_rad(int(seed), sim_t, sea_state)
    if sea_rel_deg is None:
        return pitch, pitch
    # The roll answers the same sea more slowly (longer natural period).
    roll = ship_dynamics.wave_slope_rad(int(seed) + 1, sim_t * 0.7, sea_state)
    angle = math.radians(sea_rel_deg)
    return (pitch * (0.35 + 0.65 * abs(math.cos(angle))),
            roll * (0.3 + 1.2 * abs(math.sin(angle))))


def view_motion(pitch: float, roll: float, look_rel_deg: float = 0.0) -> tuple:
    """(vertical offset px, tilt rad) of the horizon seen ``look_rel_deg``
    off the bow: ahead the pitch lifts it and the roll tilts it, abeam the
    other way round."""
    look = math.radians(look_rel_deg)
    lift = pitch * math.cos(look) + roll * math.sin(look)
    lean = roll * math.cos(look) - pitch * math.sin(look)
    return (config.clamp(lift * MOTION_PX_PER_RAD, -40.0, 40.0),
            config.clamp(lean * 0.6, -0.25, 0.25))


def horizon_motion(seed: int, sim_t: float, sea_state: float,
                   sea_rel_deg: float | None = None, look_rel_deg: float = 0.0) -> tuple:
    """(vertical offset px, tilt rad) of the horizon from the wave slope at
    ``seed`` (display only, deterministic in sim time); with ``sea_rel_deg``
    the hull pitches and rolls by her heading to the sea."""
    if sea_rel_deg is None:
        slope = ship_dynamics.wave_slope_rad(int(seed), sim_t, sea_state)
        return (config.clamp(slope * MOTION_PX_PER_RAD, -40.0, 40.0),
                config.clamp(slope * 0.6, -0.25, 0.25))
    return view_motion(*hull_motion(seed, sim_t, sea_state, sea_rel_deg), look_rel_deg)


def draw_outline(s, cls: str, cx: int, base_y: int, width: int, color,
                 t: float = 0.0, *, rim=None, lights=None, nav=None,
                 aloft: bool = False, aob_deg: float | None = None,
                 model: str | None = None) -> None:
    """Procedural side view of a coarse class, ``width`` px long, sitting on
    the horizon (aircraft: hovering above it, or with ``aloft`` centred on
    ``base_y`` at its elevation).  ``t`` (display clock) animates pitch,
    radar, rotor and wake.  With the judged angle on the bow ``aob_deg`` a
    large enough outline is its 3D model (``unit_models``), turned so; an
    identified type ``model`` is its own variant."""
    width = max(3, int(width))
    if unit_models.draw_in_scene(s, cls, cx, base_y, width, color, aob_deg=aob_deg,
                                 aloft=aloft, nav=nav, t=t, model=model):
        return
    if cls == "torpedo":
        silhouettes.draw_bubble_track(s, cx, base_y, width, t)
        return
    silhouettes.draw_profile(s, cls if cls in silhouettes.PROFILES else "unknown",
                             cx, base_y, width, color, t=t, rim=rim, lights=lights,
                             facing=nav_lights.facing(nav), nav=nav, aloft=aloft)


def draw_horizon(s, rect, *, line_of_sight: float, fov_deg: float, night: bool,
                 visibility_nm: float, motion: tuple, outlines, crosshair_deg=None,
                 land=None, anim_t: float = 0.0, sky=None, sea_state: float = 2.0,
                 elevation_deg: float = 0.0, stabilized: bool = False,
                 optics_label=None, way=None, events=(), lens=None,
                 eyepiece: str | None = None, eye_m: float | None = None) -> None:
    """The picture in the eyepiece or binoculars in the start screen's look:
    sky with stars, moon or sun and clouds, the sea in motion, the charted
    coast, the outlines within the field in steel with a lit rim, rain, snow
    or fog, the true-bearing scale, an optional crosshair with its measuring
    window (half width in degrees) and the corner brackets.  ``sky`` is a
    ``sight_scene.sky_values`` dict; without one a clear noon or midnight.
    ``elevation_deg`` tilts the optics up (positive) or down; ``stabilized``
    takes out all but ``STABILIZED_RESIDUAL`` of the hull's motion; ``way``
    is the own way through the water (``sight_scene.draw_scene``);
    ``events`` are the ``sight_events`` rows the eye can see (columns, fire,
    sinkings), drawn at the display time ``anim_t``; ``lens`` is the water
    on a periscope's glass (``sight_scene.lens_water``: cover, drops);
    ``eyepiece`` (``"binoculars"`` or ``"scope"``) rounds the field with
    the optics' rim (not at the low graphics level).  A ship whose row
    carries a range (10th column, the observer's own estimate) floats that
    far below the horizon as the eye ``eye_m`` metres up sees its
    waterline (default the own way's ``eye_m``, else the bridge lookout's),
    and nearer ships are drawn in front of farther ones."""
    rect = pygame.Rect(rect)
    if eye_m is None:
        eye_m = float((way or {}).get("eye_m", DEFAULT_EYE_M))
    sky = sky if sky is not None else sight_scene.plain_sky(night)
    offset, tilt = motion
    if stabilized:
        offset, tilt = offset * STABILIZED_RESIDUAL, tilt * STABILIZED_RESIDUAL
    lift = elevation_deg * rect.w / fov_deg
    horizon = rect.y + int(rect.h * 0.5 + offset + lift)
    view = sight_scene.View(rect, line_of_sight, fov_deg, horizon, tilt, lift)
    px_per_deg = rect.w / fov_deg
    lit = sky["light"] < 0.45

    def draw_rows(rows, colors):
        haze, haze_color = colors["haze_level"], colors["haze"]
        for row in rows:
            bearing, span_deg, cls, stale = row[:4]
            aloft = len(row) > 5 and row[5] is not None
            nav = row[4] if len(row) > 4 else None
            off = relative_offset(bearing, line_of_sight)
            if abs(off) > fov_deg / 2 + span_deg / 2:
                continue
            cx = rect.centerx + int(off * px_per_deg)
            if aloft and row[5] < LOW_AIR_DEG:
                # Low over the water: at its elevation above the moving horizon.
                base = horizon + int(math.tan(tilt) * (cx - rect.centerx) - row[5] * px_per_deg)
            elif aloft:
                # In the still sky at its elevation, behind the clouds.
                base = int(view.alt_y(0.0, cx) - row[5] * px_per_deg)
            else:
                # The waterline: close aboard well below the horizon line.
                drop = sight_scene.waterline_drop_deg(row_range(row) * 1852.0, eye_m)
                base = horizon + int(math.tan(tilt) * (cx - rect.centerx) + drop * px_per_deg)
            width = min(rect.w, max(3, int(span_deg * px_per_deg)))
            fade = 0.55 if stale else haze * 0.6
            aob = row[6] if len(row) > 6 else None
            way = row[8] if len(row) > 8 else None
            if not aloft and not stale and aob is not None and way:
                # White water first, the hull stands in it.
                ship_way.draw(s, cx, base, width, aob, way, anim_t,
                              blend(ship_way.FOAM, haze_color, haze * 0.6), colors["sea"][0])
            draw_outline(s, cls, cx, base, width, blend(colors["steel"], haze_color, fade),
                         anim_t, rim=blend(colors["rim"], haze_color, fade),
                         lights=(sight_scene.WINDOW_LIGHT if lit and not stale else None),
                         nav=nav, aloft=aloft, aob_deg=aob,
                         model=row[7] if len(row) > 7 else None)

    # Aircraft high over the sea horizon hang in the sky behind the clouds;
    # a low one (``LOW_AIR_DEG``: hovering, the own helicopter close aboard
    # or over its deck) stands in front of the sea with the ships.
    airborne = [row for row in outlines
                if len(row) > 5 and row[5] is not None and row[5] >= LOW_AIR_DEG]
    # Back to front: the farthest first, so a nearer ship hides a farther one.
    afloat = sorted((row for row in outlines
                     if not (len(row) > 5 and row[5] is not None and row[5] >= LOW_AIR_DEG)),
                    key=lambda row: -row_range(row))
    with layout.clip_to(s, rect):
        colors = sight_scene.draw_scene(
            s, view, sky, visibility_nm=visibility_nm, sea_state=sea_state, t=anim_t, way=way,
            aloft=(lambda colors: draw_rows(airborne, colors)) if airborne else None)
        haze_color = colors["haze"]
        if land is not None:
            _draw_land(s, rect, land, line_of_sight=line_of_sight, fov_deg=fov_deg,
                       horizon=horizon, tilt=tilt, light=sky["light"],
                       visibility_nm=visibility_nm, haze_color=haze_color, colors=colors)
        silhouettes.set_glow(colors.get("glow", 0.0))
        draw_rows(afloat, colors)
        silhouettes.set_glow(0.0)
        sight_events_view.draw_events(s, view, colors, sky, events, anim_t)
        sight_scene.draw_weather(s, view, sky, colors, visibility_nm=visibility_nm, t=anim_t)
        if lens is not None:
            sight_scene.draw_lens_water(s, rect, lens[0], lens[1], anim_t)
        if eyepiece in sight_scene.EYEPIECE_KINDS and quality.LEVEL != "low":
            s.blit(sight_scene.eyepiece_mask(rect.size, eyepiece), rect.topleft)
        # Labels at least ``SCALE_LABEL_MIN_PX`` apart (the narrow lookout
        # strip labels every 30 degrees, the eyepieces every 10).
        label_step = next((step for step in (10, 30, 45, 90)
                           if step * px_per_deg >= SCALE_LABEL_MIN_PX), 90)
        first = int(math.floor((line_of_sight - fov_deg / 2) / 5.0)) * 5
        for tick in range(first, first + int(fov_deg) + 10, 5):
            off = relative_offset(tick, line_of_sight)
            if abs(off) > fov_deg / 2:
                continue
            tx = rect.x + int((off + fov_deg / 2) * px_per_deg)
            major = tick % label_step == 0
            if not major and tick % 10 and 5 * px_per_deg < 6:
                continue
            pygame.draw.line(s, SCALE_COLOR, (tx, rect.y), (tx, rect.y + (10 if major else 5)), 1)
            if major and rect.h >= 40:
                layout.blit_line(s, raw_text(f"{tick % 360:03d}"),
                                 (tx - 16, rect.y + 10, 32, layout.line_pitch(11, 0)),
                                 SCALE_COLOR, size=11, align="center")
        if crosshair_deg is not None:
            pygame.draw.line(s, CROSSHAIR_COLOR, (rect.centerx, rect.y + 26),
                             (rect.centerx, rect.bottom), 1)
            window = int(crosshair_deg * px_per_deg)
            pygame.draw.line(s, CROSSHAIR_COLOR, (rect.centerx - window, rect.centery),
                             (rect.centerx + window, rect.centery), 1)
            for mark in (-1, 1):
                x = rect.centerx + mark * window
                pygame.draw.line(s, CROSSHAIR_COLOR, (x, rect.centery - 4), (x, rect.centery + 4), 1)
        if stabilized and rect.h >= 60:
            layout.blit_line(s, message("sight.stabilized"),
                             (rect.x + 10, rect.bottom - 22, 80, 16), CROSSHAIR_COLOR, size=13)
        if optics_label is not None and rect.h >= 60:
            layout.blit_line(s, optics_label, (rect.right - 250, rect.bottom - 22, 240, 16),
                             CROSSHAIR_COLOR, size=13, align="right")
        sight_scene.draw_frame(s, rect)
