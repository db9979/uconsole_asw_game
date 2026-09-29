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
from src.core.i18n import message, raw_text
from src.physics import ship_dynamics
from src.sensors import nav_lights
from src.ui import layout, sight_scene, silhouettes, unit_models

SCALE_COLOR = (170, 232, 208)
CROSSHAIR_COLOR = (120, 214, 180)
SCALE_LABEL_MIN_PX = 36
# Horizon motion: px per rad of wave slope, bounded.
MOTION_PX_PER_RAD = 260.0
# A stabilized binocular or periscope keeps this share of the hull motion.
STABILIZED_RESIDUAL = 0.12
# Charted coast on the horizon: rays per full circle, the observer's move that
# re-casts them, the bounded cache, and the assumed coastal heights (m; the
# chart has no elevation, so hills vary smoothly along the coast).
LAND_RAYS = 720
LAND_RECAST_NM = 0.1
LAND_CACHE_MAX = 4
LAND_HEIGHT_M = (25.0, 70.0)
LAND_DAY, LAND_NIGHT = (52, 66, 58), (8, 20, 26)
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
               visibility_nm, haze_color, colors=None) -> None:
    distance, height = land
    px_per_deg = rect.w / fov_deg
    step = 360.0 / len(distance)
    base_color = LAND_NIGHT if night else LAND_DAY
    rim = None if colors is None else colors["rim"]
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
                if rim is not None:
                    pygame.draw.line(s, blend(rim, haze_color, 0.3 + 0.6 * fade),
                                     (x0, top0), (px, top), 1)
        column = (px, top, base)


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
                 aloft: bool = False, aob_deg: float | None = None) -> None:
    """Procedural side view of a coarse class, ``width`` px long, sitting on
    the horizon (aircraft: hovering above it, or with ``aloft`` centred on
    ``base_y`` at its elevation).  ``t`` (display clock) animates pitch,
    radar, rotor and wake.  With the judged angle on the bow ``aob_deg`` a
    large enough outline is its 3D model (``unit_models``), turned so."""
    width = max(3, int(width))
    if unit_models.draw_in_scene(s, cls, cx, base_y, width, color, aob_deg=aob_deg,
                                 aloft=aloft, nav=nav, t=t):
        return
    if cls == "torpedo":
        left = cx - width // 2
        pygame.draw.line(s, silhouettes.FOAM, (left, base_y + 1), (left + width, base_y + 1),
                         max(1, min(3, width // 12)))
        return
    silhouettes.draw_profile(s, cls if cls in silhouettes.PROFILES else "unknown",
                             cx, base_y, width, color, t=t, rim=rim, lights=lights,
                             facing=nav_lights.facing(nav), nav=nav, aloft=aloft)


def draw_horizon(s, rect, *, line_of_sight: float, fov_deg: float, night: bool,
                 visibility_nm: float, motion: tuple, outlines, crosshair_deg=None,
                 land=None, anim_t: float = 0.0, sky=None, sea_state: float = 2.0,
                 elevation_deg: float = 0.0, stabilized: bool = False,
                 optics_label=None) -> None:
    """The picture in the eyepiece or binoculars in the start screen's look:
    sky with stars, moon or sun and clouds, the sea in motion, the charted
    coast, the outlines within the field in steel with a lit rim, rain, snow
    or fog, the true-bearing scale, an optional crosshair with its measuring
    window (half width in degrees) and the corner brackets.  ``sky`` is a
    ``sight_scene.sky_values`` dict; without one a clear noon or midnight.
    ``elevation_deg`` tilts the optics up (positive) or down; ``stabilized``
    takes out all but ``STABILIZED_RESIDUAL`` of the hull's motion."""
    rect = pygame.Rect(rect)
    sky = sky if sky is not None else sight_scene.plain_sky(night)
    offset, tilt = motion
    if stabilized:
        offset, tilt = offset * STABILIZED_RESIDUAL, tilt * STABILIZED_RESIDUAL
    lift = elevation_deg * rect.w / fov_deg
    horizon = rect.y + int(rect.h * 0.5 + offset + lift)
    view = sight_scene.View(rect, line_of_sight, fov_deg, horizon, tilt, lift)
    px_per_deg = rect.w / fov_deg
    lit = sky["light"] < 0.45

    def draw_rows(rows, colors, aloft):
        haze, haze_color = colors["haze_level"], colors["haze"]
        for row in rows:
            bearing, span_deg, cls, stale = row[:4]
            nav = row[4] if len(row) > 4 else None
            off = relative_offset(bearing, line_of_sight)
            if abs(off) > fov_deg / 2 + span_deg / 2:
                continue
            cx = rect.centerx + int(off * px_per_deg)
            if aloft:
                # In the still sky at its elevation, behind the clouds.
                base = int(view.alt_y(0.0, cx) - row[5] * px_per_deg)
            else:
                base = horizon + int(math.tan(tilt) * (cx - rect.centerx))
            width = min(rect.w, max(3, int(span_deg * px_per_deg)))
            fade = 0.55 if stale else haze * 0.6
            draw_outline(s, cls, cx, base, width, blend(colors["steel"], haze_color, fade),
                         anim_t, rim=blend(colors["rim"], haze_color, fade),
                         lights=(sight_scene.WINDOW_LIGHT if lit and not stale else None),
                         nav=nav, aloft=aloft, aob_deg=row[6] if len(row) > 6 else None)

    airborne = [row for row in outlines if len(row) > 5 and row[5] is not None]
    afloat = [row for row in outlines if not (len(row) > 5 and row[5] is not None)]
    with layout.clip_to(s, rect):
        colors = sight_scene.draw_scene(
            s, view, sky, visibility_nm=visibility_nm, sea_state=sea_state, t=anim_t,
            aloft=(lambda colors: draw_rows(airborne, colors, True)) if airborne else None)
        haze_color = colors["haze"]
        if land is not None:
            _draw_land(s, rect, land, line_of_sight=line_of_sight, fov_deg=fov_deg,
                       horizon=horizon, tilt=tilt, night=sky["light"] < 0.5,
                       visibility_nm=visibility_nm, haze_color=haze_color, colors=colors)
        draw_rows(afloat, colors, False)
        sight_scene.draw_weather(s, view, sky, colors, visibility_nm=visibility_nm, t=anim_t)
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
