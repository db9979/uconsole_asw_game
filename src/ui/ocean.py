"""The sea surface in the eyepieces in the look of Tiefenkontakt (its
``sea3d/waves.ts`` and ocean shader), drawn in 2D: every cell of the sea
below the horizon is a point on the water whose wave normal mirrors the sky,
shows the deep water's colour, the sun's or moon's glitter, whitecaps and
the haze.

Twelve wave trains with deep-water dispersion run with the wind (a spread
sea), their energy peaks at a wavelength that grows with the sea state, and
their height follows the WMO significant wave height of the sea state.  The
phases hang on the sea, not on the eye: the water streams past a ship under
way.  Trains shorter than the cell's footprint on the water drop out, so far
water stays calm instead of shimmering.

The picture is computed in cells of a few pixels (``CELLS`` per picture at
the graphics level) and smoothed up; ``data/commander/js/views/ocean.js`` is
the browser's twin.  Display only.
"""

from __future__ import annotations

import math
from collections import OrderedDict

import numpy as np
import pygame

# Wave numbers (rad/m): twelve trains from 251 m down to 5.7 m wavelength.
WK = np.array([0.025 * 44.0 ** (i / 11.0) for i in range(12)])
# Direction of each train relative to the wind (deg) and its fixed phase.
SPREAD = np.array([24, -6, 17, -21, 8, -33, 29, -12, 41, -47, 3, 58], dtype=float)
PH0 = np.array([0, 2.1, 4.4, 1.3, 5.6, 3.2, 0.7, 4.9, 2.8, 6.0, 1.8, 3.9])
# First train counted as short wind sea (k >= 0.15 rad/m): where it breaks, whitecaps.
CHOP0 = int(np.argmax(WK >= 0.15))
# Significant wave height (m) by sea state (WMO code 3700) and the spectral peak (rad/m).
HS = (0.05, 0.25, 0.8, 1.6, 2.8, 4.2, 6.0, 8.5, 11.0, 14.0)
PEAK_K = (0.9, 0.6, 0.38, 0.24, 0.15, 0.1, 0.075, 0.055, 0.045, 0.04)
G = 9.81
# The deep water's own colour (0..1), the subsurface green on lit flanks,
# the foam, the sun's and the moon's glitter.
DEEP = (16 / 255, 48 / 255, 58 / 255)
SUBSURFACE = (0.02, 0.07, 0.06)
FOAM = (0.86, 0.9, 0.92)
SUN_GLITTER = (1.0, 0.92, 0.8)
MOON_GLITTER = (0.75, 0.8, 0.9)
# Cells per picture by graphics level (the picture is computed at this many
# points and smoothed up); cells are at most twice as wide as high.
CELLS = {"normal": 2400, "full": 8000}
# A cell covers at least this many pixels (small pictures need fewer cells).
MIN_CELL_PX = 24.0
# Fog: the haze's extinction per metre at a given visibility (Koschmieder).
EXTINCTION = 3.0
# The footprint that decides which trains a cell can carry, in cells (the
# smoothing up draws a wave over two cells and more).
FOOT = 1.0
_CACHE = OrderedDict()


def _table(values, x):
    x = min(len(values) - 1.0, max(0.0, float(x)))
    i = min(len(values) - 2, int(math.floor(x)))
    return values[i] + (values[i + 1] - values[i]) * (x - i)


def sig_height(sea_state: float) -> float:
    """Significant wave height (m) of ``sea_state`` (0..9)."""
    return _table(HS, sea_state)


def waves(sea_state: float, wind_from_deg: float, own_e: float, own_n: float, t: float) -> dict:
    """The wave field: amplitude, chop, per train its share, direction of
    travel (east, north) and phase at the eye (rad), at sea time ``t`` with
    the eye at ``own_e``/``own_n`` metres on the sea."""
    toward = math.radians(wind_from_deg + 180.0)
    kp = _table(PEAK_K, sea_state)
    x = np.log(WK / kp) / 0.55
    raw = (np.exp(-0.5 * x * x) * np.where(WK < kp, 1.0, (kp / WK) ** 0.6)
           + np.where(WK < 0.05, 0.06, 0.012) * np.where(np.arange(12) % 2 == 1, 0.8, 1.2))
    share = raw / raw.sum()
    sigma = math.sqrt(float((share * share).sum()) / 2.0)
    amp = sig_height(sea_state) / (4.0 * sigma)
    fold = float((np.minimum(5.0 * amp * share, 0.75 / WK) * WK).sum())
    chop = min(1.0, 0.8 / max(fold, 1e-6))
    angle = toward + np.radians(SPREAD)
    direction = np.stack((np.sin(angle), np.cos(angle)), axis=1)
    phase = (WK * (direction[:, 0] * own_e + direction[:, 1] * own_n)
             - np.sqrt(G * WK) * t + PH0) % math.tau
    return dict(amp=amp, chop=chop, share=share, direction=direction, phase=phase,
                wind=(math.sin(toward), math.cos(toward)))


# Value noise from a fixed table of NOISE_SIZE x NOISE_SIZE random lattice
# values (an integer hash, the same in the browser): tiles every NOISE_SIZE
# units, cheap to sample.
NOISE_SIZE = 64


def _lattice() -> np.ndarray:
    x = np.arange(NOISE_SIZE * NOISE_SIZE, dtype=np.uint64)
    mask = np.uint64(0xFFFFFFFF)
    x = (x * np.uint64(0x9E3779B1)) & mask
    x ^= x >> np.uint64(15)
    x = (x * np.uint64(0x85EBCA77)) & mask
    x ^= x >> np.uint64(13)
    x = (x * np.uint64(0xC2B2AE3D)) & mask
    x ^= x >> np.uint64(16)
    return (x.astype(np.float64) / 4294967296.0).reshape(NOISE_SIZE, NOISE_SIZE)


LATTICE = _lattice()


def noise(px, py):
    """Value noise 0..1 (the shader's ``noise``), smooth between the
    lattice values."""
    ix, iy = np.floor(px), np.floor(py)
    fx, fy = px - ix, py - iy
    ux, uy = fx * fx * (3.0 - 2.0 * fx), fy * fy * (3.0 - 2.0 * fy)
    i0 = ix.astype(np.int64) % NOISE_SIZE
    j0 = iy.astype(np.int64) % NOISE_SIZE
    i1, j1 = (i0 + 1) % NOISE_SIZE, (j0 + 1) % NOISE_SIZE
    a, b = LATTICE[j0, i0], LATTICE[j0, i1]
    c, d = LATTICE[j1, i0], LATTICE[j1, i1]
    top = a + (b - a) * ux
    return top + ((c + (d - c) * ux) - top) * uy


def fbm(px, py):
    value, weight = 0.0, 0.5
    for _ in range(4):
        value = value + weight * noise(px, py)
        px, py, weight = px * 2.0, py * 2.0, weight * 0.5
    return value


def _smoothstep(low, high, x):
    t = np.clip((x - low) / (high - low), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _unit(bearing_deg, alt_deg):
    b, a = math.radians(bearing_deg), math.radians(alt_deg)
    return np.array((math.sin(b) * math.cos(a), math.cos(b) * math.cos(a), math.sin(a)))


def sea_params(sky: dict, colors: dict, *, sea_state: float, visibility_nm: float,
               eye_m: float, own_e: float, own_n: float, t: float) -> dict:
    """Everything the shading needs for one picture, plain numbers (the
    browser builds the same from its state)."""
    light = float(sky["light"])
    sun_up = min(1.0, max(0.0, (float(sky["sun_alt_deg"]) + 1.0) / 6.0))
    clear = 1.0 - min(1.0, max(0.0, (float(sky["cloud"]) - 0.5) * 2.0))
    top, horizon = (np.array(c, float) / 255.0 for c in colors["sky"])
    haze = np.array(colors["haze"], float) / 255.0
    reflect = (horizon + (top - horizon) * 0.25)
    reflect = reflect + (haze - reflect) * 0.3
    reflect_top = top + (horizon - top) * 0.25
    return dict(
        waves=waves(sea_state, float(sky["wind_from_deg"]), own_e, own_n, t),
        t=float(t), eye_m=max(1.0, float(eye_m)), light=light,
        deep=np.array(DEEP) * (0.12 + 0.88 * light * light),
        reflect=reflect, reflect_top=reflect_top, haze=haze,
        sun=_unit(sky["sun_bearing"], sky["sun_alt_deg"]),
        moon=_unit(sky["moon_bearing"], sky["moon_alt_deg"]),
        sun_up=sun_up * clear, moon_light=float(sky["moon_illumination"]) * clear
        * (1.0 if sky["moon_alt_deg"] > 0 else 0.0),
        foam=min(1.0, max(0.0, (sea_state - 2.0) / 4.0)),
        spin=min(1.0, max(0.0, (sea_state - 4.0) / 2.0)),
        rain=float(sky["intensity"]) if sky["precipitation"] == "rain" else 0.0,
        fog=EXTINCTION / max(50.0, visibility_nm * 1852.0),
        own=(float(own_e) % 32768.0, float(own_n) % 32768.0))


def shade(p: dict, bearing_deg, below_deg, cell_deg: float):
    """Colours (N, 3, 0..1) of the sea seen at true ``bearing_deg`` and
    ``below_deg`` under the sea horizon (arrays of N), each cell
    ``cell_deg`` wide."""
    eye = p["eye_m"]
    dip = math.sqrt(2.0 * eye / 7.3e6)
    down = np.radians(np.maximum(below_deg, 1e-4)) + dip
    distance = eye / np.tan(down)
    b = np.radians(bearing_deg)
    se, sn = np.sin(b), np.cos(b)
    e, n = se * distance, sn * distance
    cos_d, sin_d = np.cos(down), np.sin(down)
    view = np.stack((-se * cos_d, -sn * cos_d, sin_d), axis=1)
    # The cell's footprint on the water (m): across and along the line of sight.
    cell = math.radians(cell_deg)
    foot = np.maximum(np.sqrt(distance * cell * distance * cell / np.maximum(sin_d, 1e-4)) * FOOT,
                      0.05)
    w = p["waves"]
    lam = math.tau / WK
    keep = 1.0 - _smoothstep(lam * 0.15, lam * 0.35, foot[:, None])          # (N, 12)
    psi = WK * (e[:, None] * w["direction"][:, 0] + n[:, None] * w["direction"][:, 1]) \
        + w["phase"]
    weight = w["share"] * keep
    cos_psi, sin_psi = np.cos(psi), np.sin(psi)
    slope = (weight * WK * cos_psi) @ w["direction"] * w["amp"]               # (N, 2)
    height = (weight * sin_psi).sum(axis=1)
    normal = np.stack((-slope[:, 0] * 1.2, -slope[:, 1] * 1.2, np.ones(len(e))), axis=1)
    sea_e, sea_n = e + p["own"][0], n + p["own"][1]
    # Capillary ripples close by, drifting downwind.
    # (Left out where a cell spans many ripples: they would only flicker.)
    near = (1.0 - _smoothstep(60.0, 900.0, distance)) * (1.0 - _smoothstep(0.4, 1.6, foot))
    if near.max() > 0.0:
        qx = sea_e + w["wind"][0] * p["t"] * 0.7
        qy = sea_n + w["wind"][1] * p["t"] * 0.7
        normal[:, 0] += (noise(qx, qy) - 0.5) * 0.12 * near
        normal[:, 1] += (noise(qx * 2.0 + 4.0, qy * 2.0 + 4.0) - 0.5) * 0.12 * near
    # Rain pocks the water close by: fine, fast roughness that dulls the mirror.
    if p["rain"] > 0.0:
        pock = p["rain"] * (1.0 - _smoothstep(0.1, 0.75, foot)) \
            * (1.0 - _smoothstep(80.0, 450.0, distance))
        rx, ry = sea_e * 3.0, sea_n * 3.0
        normal[:, 0] += (noise(rx + p["t"] * 11.0, ry + p["t"] * 11.0) - 0.5) * 0.8 * pock
        normal[:, 1] += (noise(rx * 1.7 - p["t"] * 9.0, ry * 1.7 - p["t"] * 9.0) - 0.5) * 0.8 * pock
    normal /= np.linalg.norm(normal, axis=1)[:, None]
    facing = (normal * view).sum(axis=1)
    fresnel = (1.0 - np.maximum(facing, 0.0)) ** 4
    mirror = 2.0 * facing[:, None] * normal - view
    up = _smoothstep(0.0, 0.7, mirror[:, 2])[:, None]
    sky = p["reflect"] + (p["reflect_top"] - p["reflect"]) * up
    mix = np.clip(0.08 + fresnel * 0.85, 0.0, 1.0)[:, None]
    color = p["deep"] + (sky - p["deep"]) * mix
    color = color + np.array(SUBSURFACE) * np.maximum(0.0, height)[:, None] * p["light"]
    if p["sun_up"] > 0.0:
        sd = np.maximum(mirror @ p["sun"], 0.0)
        # A sharp core, a broad sheen and (for the cells too coarse to catch
        # a single facet) the glitter path of the many facets within a cell.
        color = color + np.array(SUN_GLITTER) * ((sd ** 400 * 1.4 + sd ** 60 * 0.45
                                                  + sd ** 30 * 0.12) * p["sun_up"])[:, None]
    if p["moon_light"] > 0.0 and p["sun_up"] < 1.0:
        md = np.maximum(mirror @ p["moon"], 0.0)
        color = color + np.array(MOON_GLITTER) * ((md ** 160 * 0.9 + md ** 40 * 0.3)
                                                  * (1.0 - p["sun_up"])
                                                  * p["moon_light"])[:, None]
    if p["foam"] > 0.0:
        wind = w["wind"]
        wx = e * wind[0] + n * wind[1] + (p["own"][0] * wind[0] + p["own"][1] * wind[1])
        wy = -e * wind[1] + n * wind[0] + (-p["own"][0] * wind[1] + p["own"][1] * wind[0])
        short = w["share"][CHOP0:]
        chop = (weight[:, CHOP0:] * sin_psi[:, CHOP0:]).sum(axis=1) / max(short.sum(), 1e-3)
        pf = fbm(wx * 0.0625 + p["t"] * 0.03, wy * 0.125)
        fine = noise(sea_e * 0.5 + wind[0] * p["t"] * 0.4, sea_n * 0.5 + wind[1] * p["t"] * 0.4)
        # Where a cell spans several patches, their mean.
        fine = fine + (0.5 - fine) * _smoothstep(1.0, 4.0, foot)
        m = 0.42 * chop + 0.12 * height + 0.9 * pf - 1.0 + 0.3 * p["foam"]
        foam = _smoothstep(0.0, 0.12, m) * _smoothstep(0.25, 0.7, fine)
        far = 1.0 - _smoothstep(400.0, 2500.0, distance)
        foam = (0.05 * p["foam"] + (foam - 0.05 * p["foam"]) * far) * p["foam"]
        if p["spin"] > 0.0:
            # A gale: long foam streaks blown out along the wind.
            sy = wy + (noise(wx * 0.05, wy * 0.05) - 0.5) * 14.0
            lane = noise(wx * 0.03 + p["t"] * 0.05, sy * 0.45)
            patchy = _smoothstep(0.4, 0.75, noise(wx * 0.012 + 9.0, wy * 0.05 + 9.0))
            sharp = 1.0 - _smoothstep(0.6, 2.5, foot)
            streak = 0.08 + (_smoothstep(0.6, 0.82, lane) * patchy * 0.45 - 0.08) * sharp
            foam = foam + p["spin"] * streak * far
        foam_color = np.array(FOAM) * (0.1 + 0.9 * p["light"])
        k = (np.clip(foam, 0.0, 1.0) * 0.85)[:, None]
        color = color + (foam_color - color) * k
    fog = (1.0 - np.exp(-distance * p["fog"]))[:, None]
    return np.clip(color + (p["haze"] - color) * fog, 0.0, 1.0)


def grid_size(width: int, height: int, level: str) -> tuple:
    """Cells across and down a sea of ``width`` x ``height`` px."""
    total = min(CELLS.get(level, CELLS["normal"]), width * height / MIN_CELL_PX)
    cell = max(1.0, math.sqrt(width * height / (total * 2.0)))
    return max(2, int(round(width / (cell * 2.0)))), max(2, int(round(height / cell)))


def draw(s, view, sky: dict, colors: dict, *, sea_state: float, visibility_nm: float,
         eye_m: float, own_e: float, own_n: float, t: float, level: str = "normal") -> None:
    """The shaded sea below the moving horizon of ``view``
    (``sight_scene.View``)."""
    rect = view.rect
    dy = math.tan(view.tilt) * rect.w / 2.0
    top = int(max(rect.y, math.floor(min(view.horizon - dy, view.horizon + dy)) - 1))
    if top >= rect.bottom:
        return
    width, height = rect.w, rect.bottom - top
    columns, rows = grid_size(width, height, level)
    p = sea_params(sky, colors, sea_state=sea_state, visibility_nm=visibility_nm, eye_m=eye_m,
                   own_e=own_e, own_n=own_n, t=t)
    xs = rect.x + (np.arange(columns) + 0.5) * width / columns
    ys = top + (np.arange(rows) + 0.5) * height / rows
    gx, gy = np.meshgrid(xs, ys)
    base = view.horizon + math.tan(view.tilt) * (gx - rect.centerx)
    below = (gy - base) / view.px_per_deg
    bearing = view.los + (gx - rect.centerx) / view.px_per_deg
    cell_deg = width / columns / view.px_per_deg
    rgb = shade(p, bearing.ravel(), np.maximum(below.ravel(), 0.5 * height / rows
                                                / view.px_per_deg), cell_deg)
    pixels = np.round(rgb * 255.0).astype(np.uint8).reshape(rows, columns, 3)
    small = pygame.surfarray.make_surface(pixels.transpose(1, 0, 2))
    picture = pygame.transform.smoothscale(small, (width, height))
    # Above the moving horizon the sky stays: a colour key cut along it.
    key = (255, 0, 255)
    sky_part = [(0, -1), (width, -1), (width, view.base(rect.right) - top),
                (0, view.base(rect.x) - top)]
    pygame.draw.polygon(picture, key, sky_part)
    picture.set_colorkey(key)
    s.blit(picture, (rect.x, top))
