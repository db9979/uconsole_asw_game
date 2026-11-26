"""The sky of the eyepieces in the look of Tiefenkontakt (its ``sea3d/sky.ts``
sky shader), drawn in 2D: every cell above the horizon is a direction whose
colour comes from the sky gradient, the dusk glow on the sun's side, the
halo round the sun, high cirrus streaks along the wind, the cloud deck and
the haze band at the horizon.

The cloud deck lies about 1.8 km up and hangs on the sea: it drifts
downwind and the own way carries the eye under it.  Its cover follows the
observed cloud cover (fair-weather cumulus, a broken deck, overcast), lit
from the sun's side with bright tops, grey bases and a silver lining where
thin cloud covers the sun, red undersides at dusk and dark at night.

The eyepieces' sky is stylised (``sight_scene.View.alt_y``): the top of the
picture is about 57 degrees up, the sun and the moon stand where
``sight_scene`` draws them.  The sky is computed in cells and smoothed up
like the sea (``src/ui/ocean.py``, the same noise); the background and the
cloud deck are two layers, so stars, the moon and aircraft show between
them.  ``data/commander/js/views/sky.js`` is the browser's twin.  Display
only.
"""

from __future__ import annotations

import math
from collections import OrderedDict

import numpy as np
import pygame

from src.ui import stars
from src.ui.ocean import fbm, _smoothstep

# Height of the deck over its noise scale (Tiefenkontakt: 1800 m, 2500 m).
CLOUD_UV = 1800.0 / 2500.0
CLOUD_SCALE_M = 2500.0
CLOUD_WRAP = 2048.0
CLOUD_START = (17.31, 41.77)
# Wind aloft (m/s) the deck drifts with.
WIND_ALOFT = 9.0
# Cells per picture by graphics level and the least pixels per cell.
CELLS = {"normal": 1800, "full": 6000}
MIN_CELL_PX = 24.0
SUN_COLOR = (1.0, 0.957, 0.878)
SUN_DUSK = (1.0, 0.627, 0.376)
CIRRUS = (0.92, 0.94, 0.96)
CLOUD_BASE = ((0.5, 0.54, 0.57), (0.3, 0.33, 0.36))
CLOUD_TOP = ((0.97, 0.97, 0.96), (0.62, 0.66, 0.69))
MOON_GLOW = (0.85, 0.88, 0.95)
# Stylised elevation: the sight scene's fraction of the sky height to
# degrees (its sun at ``alt`` stands at fraction 0.12 + 0.7 * alt / 45, so
# about 8 degrees higher here: it never touches the horizon's haze).
FRACTION_PER_DEG = 0.7 / 45.0
# The shaded sky changes slowly: a picture is reused while its view stays
# and for this long (s); the eye's way moves it on every this many metres.
REUSE_S = 0.5
REUSE_M = 10.0
_CACHE = OrderedDict()
_CACHE_MAX = 6


def elevation(fraction):
    """Degrees above the horizon of a height ``fraction`` of the sky; an
    optic tilted far up looks at the zenith, not past it."""
    return np.clip(np.asarray(fraction, dtype=float) / FRACTION_PER_DEG, -90.0, 90.0)


def _mix(a, b, t):
    a, b = np.asarray(a, float), np.asarray(b, float)
    return a + (b - a) * np.asarray(t, float)[..., None] if np.ndim(t) else a + (b - a) * t


def _unit(bearing_deg, alt_deg):
    b, a = math.radians(bearing_deg), math.radians(alt_deg)
    return (math.sin(b) * math.cos(a), math.cos(b) * math.cos(a), math.sin(a))


def haze_k(sky: dict, visibility_nm: float) -> float:
    """How steeply the haze band thins upward: a thin band in clear air, a
    wall in rain and fog."""
    over = min(1.0, max(0.0, float(sky["cloud"])))
    rain = float(sky["intensity"]) if sky["precipitation"] in ("rain", "snow") else 0.0
    fog = min(1.0, max(0.0, 1.0 - visibility_nm / 3.0))
    k = 45.0 + (14.0 - 45.0) * max(rain, over * 0.5)
    return k + (2.0 - k) * fog


def sky_params(sky: dict, colors: dict, *, sun_el: float, moon_el: float,
               visibility_nm: float, own_e: float, own_n: float, t: float) -> dict:
    """Everything the shading needs for one picture, plain numbers.
    ``sun_el``/``moon_el`` are the stylised elevations the bodies are drawn
    at (degrees)."""
    light = float(sky["light"])
    over = min(1.0, max(0.0, float(sky["cloud"])))
    rain = float(sky["intensity"]) if sky["precipitation"] in ("rain", "snow") else 0.0
    fog = min(1.0, max(0.0, 1.0 - visibility_nm / 3.0))
    toward = math.radians(float(sky["wind_from_deg"]) + 180.0)
    wind = (math.sin(toward), math.cos(toward))
    drift = WIND_ALOFT * 1.5 * t
    # (Started off the noise lattice's origin, where every octave of the
    # integer hash meets at its zero.)
    off = (((own_e + wind[0] * drift) / CLOUD_SCALE_M + CLOUD_START[0]) % CLOUD_WRAP,
           ((own_n + wind[1] * drift) / CLOUD_SCALE_M + CLOUD_START[1]) % CLOUD_WRAP)
    dusk = float(sky["dusk"])
    sun_alt = float(sky["sun_alt_deg"])
    sun_up = (min(1.0, max(0.0, math.sin(math.radians(sun_alt)) * 6.0 + 0.2))
              * (1.0 - 0.95 * over) * (1.0 - 0.9 * rain) * (1.0 - 0.8 * fog))
    moon_up = (float(sky["moon_illumination"]) * (1.0 - over)
               * (1.0 if sky["moon_alt_deg"] > 0 else 0.0) * max(0.0, 1.0 - light * 2.0))
    top, horizon = (tuple(c / 255.0 for c in color) for color in colors["sky"])
    return dict(
        top=top, horizon=horizon, haze=tuple(c / 255.0 for c in colors["haze"]),
        lit=0.05 + 0.95 * light * light, light=light, dusk=dusk, over=over,
        cover=min(1.0, over * 1.05),
        sun=_unit(float(sky["sun_bearing"]), sun_el), sun_up=sun_up,
        sun_color=tuple(a + (b - a) * dusk for a, b in zip(SUN_COLOR, SUN_DUSK)),
        moon=_unit(float(sky["moon_bearing"]), moon_el), moon_up=moon_up,
        haze_k=haze_k(sky, visibility_nm), wind=wind, off=off)


def _cloud_dens(p, px, py):
    wx = fbm(px * 0.5 + 3.1, py * 0.5 + 1.7)
    wy = fbm(px * 0.5 + 7.7, py * 0.5 + 4.2)
    n = fbm(px + wx * 1.4, py + wy * 1.4)
    thr = 0.8 + (0.12 - 0.8) * p["cover"]
    return _smoothstep(thr - 0.05, thr + 0.16, n)


def shade(p: dict, bearing_deg, elev_deg):
    """Colours of the sky at ``bearing_deg``/``elev_deg`` (arrays of N):
    the background (N, 3) and the cloud deck's colour (N, 3) with its
    cover (N,), all 0..1."""
    b = np.radians(np.asarray(bearing_deg, float))
    e = np.radians(np.asarray(elev_deg, float))
    ce = np.cos(e)
    dx, dy, dz = np.sin(b) * ce, np.cos(b) * ce, np.sin(e)
    h = np.maximum(dz, 0.0)
    lit = p["lit"]
    sx, sy, sz = p["sun"]
    s = np.maximum(dx * sx + dy * sy + dz * sz, 0.0)
    col = _mix(p["horizon"], p["top"], np.clip(h * 2.4, 0.0, 1.0) ** 0.55)
    # Dusk: a warm band low on the sun's side, fading round to the far side.
    flat = np.hypot(dx, dy) + 1e-9
    sflat = math.hypot(sx, sy) + 1e-9
    az = (dx * sx + dy * sy) / (flat * sflat) * 0.5 + 0.5
    warm = _mix((1.0, 0.38, 0.12), (1.0, 0.7, 0.35), az ** 12 * (1.0 - h))
    glow = ((warm * ((1.0 - h) ** 7 * az ** 3 * 1.5)[:, None]
             + np.array((0.9, 0.45, 0.3)) * ((1.0 - h) ** 3 * az ** 1.5 * 0.15)[:, None])
            * p["dusk"] * (1.0 - 0.75 * p["over"]) * (lit + 0.3))
    col = col + glow
    # The halo round the sun (forward scattering); the disc is drawn apart.
    clear = 1.0 - 0.85 * p["over"]
    col = col + np.array(p["sun_color"]) * ((s ** 6 * 0.18 + s ** 60 * 0.35)
                                            * p["sun_up"] * clear)[:, None]
    mx, my, mz = p["moon"]
    m = np.maximum(dx * mx + dy * my + dz * mz, 0.0)
    col = col + np.array(MOON_GLOW) * (m ** 200 * 0.08 * p["moon_up"])[:, None]
    up = np.maximum(dz, 0.05)
    # High cirrus: thin streaks along the wind in fair weather.
    wx, wy = p["wind"]
    cx = dx / up * 0.25 + p["off"][0] * 0.37
    cy = dy / up * 0.25 + p["off"][1] * 0.37
    q1, q2 = cx * wx + cy * wy, -cx * wy + cy * wx
    ci = (_smoothstep(0.55, 0.85, fbm(q1 * 0.5, q2 * 5.0)) * _smoothstep(0.05, 0.4, dz)
          * (1.0 - p["cover"]) * (dz > 0.0))
    col = _mix(col, np.array(CIRRUS) * lit, ci * 0.35)
    # The cumulus / stratus deck, lit from the sun's side; low down only its
    # mean cover (the pattern would crowd into the horizon).
    ux = dx / np.maximum(dz, 0.02) * CLOUD_UV + p["off"][0]
    uy = dy / np.maximum(dz, 0.02) * CLOUD_UV + p["off"][1]
    dens = _cloud_dens(p, ux, uy)
    far = _smoothstep(0.03, 0.22, dz)
    c = (np.clip(p["cover"] * 1.25, 0.0, 1.0) * (1.0 - far) + dens * far) * (dz > 0.0)
    toward = _cloud_dens(p, ux + sx / sflat * 0.12, uy + sy / sflat * 0.12)
    toward = np.where(dz > 0.03, toward, c)
    over = p["over"]
    tone = np.clip(0.62 + (c - toward) * 1.6 * (1.0 - 0.75 * over) - over * 0.35, 0.0, 1.0)
    base = _mix(CLOUD_BASE[0], CLOUD_BASE[1], over)
    top = _mix(CLOUD_TOP[0], CLOUD_TOP[1], over)
    cc = base + (top - base) * tone[:, None]
    cc = cc + (cc * np.array((1.35, 0.85, 0.6)) - cc) * (
        p["dusk"] * az ** 2 * 0.8 * (1.0 - over))[:, None]
    cc = cc + np.array(p["sun_color"]) * (s ** 14 * (1.0 - c) * 1.2 * p["sun_up"])[:, None]
    cc = cc * lit
    # The haze toward the horizon: a thin band in clear air, a wall in rain
    # and fog; the clouds sink into it too.
    hz = np.where(dz < 0.0, 1.0, np.exp(-h * p["haze_k"]))
    haze = np.array(p["haze"])
    back = _mix(col, haze, hz) + glow * (hz * 0.8)[:, None]
    cloud = _mix(cc, haze, hz) + glow * (hz * 0.8)[:, None]
    return np.clip(back, 0.0, 1.0), np.clip(cloud, 0.0, 1.0), np.clip(c, 0.0, 1.0)


def grid_size(width: int, height: int, level: str) -> tuple:
    """Cells across and down a sky of ``width`` x ``height`` px."""
    total = min(CELLS.get(level, CELLS["normal"]), width * height / MIN_CELL_PX)
    cell = max(1.0, math.sqrt(width * height / total))
    return max(2, int(round(width / cell))), max(2, int(round(height / cell)))


def layers(view, sky: dict, colors: dict, *, sun_el: float, moon_el: float,
           visibility_nm: float, own_e: float, own_n: float, t: float,
           level: str = "normal", night=None):
    """The sky of ``view`` (``sight_scene.View``): (top y, background
    surface, cloud surface with alpha), reused while nothing visible
    changes.  ``night`` (``stars.conditions``) adds the Milky Way at its
    true angles."""
    rect = view.rect
    key = (tuple(rect), round(view.los, 2), round(view.lift, 1), view.sky_h,
           round(view.px_per_deg, 3), level, round(visibility_nm, 1), int(t / REUSE_S),
           round(own_e / REUSE_M), round(own_n / REUSE_M), round(sun_el, 1), round(moon_el, 1),
           tuple(sorted((k, v) for k, v in sky.items() if isinstance(v, (int, float, str)))),
           colors["sky"], colors["haze"])
    cached = _CACHE.get(key)
    if cached is not None:
        _CACHE.move_to_end(key)
        return cached
    # Down to the picture's foot: the sea, rolling, covers what lies below
    # its horizon.
    top = rect.y
    width, height = rect.w, rect.h
    columns, rows = grid_size(width, height, level)
    p = sky_params(sky, colors, sun_el=sun_el, moon_el=moon_el, visibility_nm=visibility_nm,
                   own_e=own_e, own_n=own_n, t=t)
    xs = rect.x + (np.arange(columns) + 0.5) * width / columns
    ys = top + (np.arange(rows) + 0.5) * height / rows
    gx, gy = np.meshgrid(xs, ys)
    nominal = rect.y + rect.h / 2.0 + view.lift
    fraction = (nominal - gy) / view.sky_h
    bearing = view.los + (gx - rect.centerx) / view.px_per_deg
    back, cloud, cover = shade(p, bearing.ravel(), elevation(fraction.ravel()))
    if night is not None and night["milky"] > 0.002:
        true_el = ((nominal - gy) / view.px_per_deg).ravel()
        back = stars.add_milky_way(back, stars.milky_way(night, bearing.ravel(), true_el))
    back_px = np.round(back * 255.0).astype(np.uint8).reshape(rows, columns, 3)
    cloud_px = np.empty((rows, columns, 4), dtype=np.uint8)
    cloud_px[..., :3] = np.round(cloud * 255.0).astype(np.uint8).reshape(rows, columns, 3)
    cloud_px[..., 3] = np.round(cover * 255.0).astype(np.uint8).reshape(rows, columns)
    small = pygame.surfarray.make_surface(back_px.transpose(1, 0, 2))
    back_s = pygame.transform.smoothscale(small, (width, height))
    deck = pygame.image.frombuffer(cloud_px.tobytes(), (columns, rows), "RGBA")
    cloud_s = pygame.transform.smoothscale(deck, (width, height))
    _CACHE[key] = (top, back_s, cloud_s)
    while len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)
    return top, back_s, cloud_s
