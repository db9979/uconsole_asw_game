"""The night sky of the eyepieces, the stars of Tiefenkontakt (its
``sea3d/astro.ts`` and ``sea3d/stars.ts``) drawn in 2D.

The 986 stars of the Yale Bright Star Catalogue brighter than V 4.6
(``data/sky/bright_stars.json``, ``tools/build_star_catalog.py``) stand in
their real places over the sea area: the sector's latitude, the day of the
year and the ship's clock as local solar time, so the sky turns through the
night and with the seasons.  Size and brightness follow the magnitude, the
colour the B-V index; extinction dims and reddens them toward the horizon,
where they twinkle hardest and sink into the haze.  They come out as the
sun sinks, thin out in moonlight and hide behind the cloud deck, fog and
rain.  The glasses and the periscope gather more light: past V 4.6 a seeded
scatter of faint stars (real counts per magnitude, crowding toward the
Milky Way) fills their field, and on a clear dark night the Milky Way
itself shows as a faint band (``milky_way``, added to the shaded sky by
``src/ui/skyshade.py``).

Unlike the stylised sky gradient and cloud deck, the stars keep their true
angles (like the aircraft): tilting the optics up shows the constellations
as they stand.  Positions are J2000 without precession.  Display only;
``data/commander/js/views/stars.js`` is the browser's twin.
"""

from __future__ import annotations

import base64
import json
import math
from functools import lru_cache
from importlib.resources import files as resource_files

import numpy as np

from src.ui.ocean import fbm, noise, _smoothstep

RESOURCE = ("data.sky", "bright_stars.json")
# Obliquity of the ecliptic.
EPS = math.radians(23.44)
DEFAULT_DAY_OF_YEAR = 80
# The faint scatter past the catalogue (Tiefenkontakt's ``faintStars``).
FAINT_COUNT = 24_000
FAINT_SEED = 7
STAR_WHITE = (0.92, 0.94, 1.0)
REDDENED = (1.0, 0.78, 0.55)
MILKY_COLOR = (0.72, 0.78, 0.92)
# Point spread scale (px): Tiefenkontakt's device pixel, a little wider for
# the small eyepieces of the uConsole.
POINT_PX = 1.2
# Stars twinkle by this phase spread (golden ratio per catalogue index).
_GOLDEN = 0.6180339887498949


def _wrap360(deg):
    return deg % 360.0


def equ_vec(ra_deg, dec_deg):
    """Equatorial unit vector(s) of right ascension and declination."""
    a, d = np.radians(ra_deg), np.radians(dec_deg)
    return np.stack([np.cos(d) * np.cos(a), np.cos(d) * np.sin(a), np.sin(d)], axis=-1)


GAL_POLE = equ_vec(192.8595, 27.1283)
GAL_CENTRE = equ_vec(266.405, -28.936)


def sun_ra(day_of_year: float) -> float:
    """The sun's right ascension (deg) on day ``day_of_year``, on the orbit
    ``atmosphere.sun_elevation_deg`` assumes (declination -23.44 cos(2 pi
    (doy + 10) / 365))."""
    lam = math.radians(360.0 / 365.0 * (day_of_year + 10.0) - 90.0)
    return _wrap360(math.degrees(math.atan2(math.cos(EPS) * math.sin(lam), math.cos(lam))))


def sidereal_deg(day_of_year: float, hour: float) -> float:
    """Local sidereal time (deg): the right ascension on the meridian at the
    local solar ``hour``."""
    return _wrap360(sun_ra(day_of_year) + 15.0 * (hour - 12.0))


def rotation(lat_deg: float, lst_deg: float) -> np.ndarray:
    """3x3 from the equatorial unit vector to east, north, up."""
    lst, lat = math.radians(lst_deg), math.radians(lat_deg)
    cl, sl, cp, sp = math.cos(lst), math.sin(lst), math.cos(lat), math.sin(lat)
    u0, u1, u2 = np.array((cl, sl, 0.0)), np.array((-sl, cl, 0.0)), np.array((0.0, 0.0, 1.0))
    return np.array([u1, -sp * u0 + cp * u2, cp * u0 + sp * u2])


@lru_cache(maxsize=1)
def catalog() -> tuple:
    """The bright stars: equatorial unit vectors (N, 3), V, B-V."""
    package, name = RESOURCE
    data = json.loads(resource_files(package).joinpath(name).read_text(encoding="utf-8"))
    raw = np.frombuffer(base64.b64decode(data["stars_b64"]), dtype=np.uint8)
    raw = raw[:data["count"] * 6].reshape(-1, 6).astype(np.float64)
    ra = (raw[:, 0] + raw[:, 1] * 256.0) / 65535.0 * 360.0
    dec = (raw[:, 2] + raw[:, 3] * 256.0) / 65535.0 * 180.0 - 90.0
    return equ_vec(ra, dec), raw[:, 4] / 40.0 - 1.5, raw[:, 5] / 80.0 - 0.4


def _mulberry32(seed: int):
    state = seed & 0xFFFFFFFF
    mask = 0xFFFFFFFF

    def rnd() -> float:
        nonlocal state
        state = (state + 0x6D2B79F5) & mask
        t = ((state ^ (state >> 15)) * (1 | state)) & mask
        t = ((t + (((t ^ (t >> 7)) * (61 | t)) & mask)) & mask) ^ t
        return ((t ^ (t >> 14)) & mask) / 4294967296.0
    return rnd


@lru_cache(maxsize=1)
def faint() -> tuple:
    """The faint stars past the catalogue (V 4.6 to 8): not real ones, a
    seeded scatter with the real count per magnitude and crowding toward
    the Milky Way (Tiefenkontakt's ``faintStars``)."""
    rnd = _mulberry32(FAINT_SEED)
    pole = GAL_POLE
    lo, hi = 10.0 ** (0.47 * 4.6), 10.0 ** (0.47 * 8.0)
    pos, mag, bv = [], [], []
    while len(mag) < FAINT_COUNT:
        z = rnd() * 2.0 - 1.0
        a = rnd() * math.tau
        r = math.sqrt(1.0 - z * z)
        v = (r * math.cos(a), r * math.sin(a), z)
        b = v[0] * pole[0] + v[1] * pole[1] + v[2] * pole[2]
        if rnd() > 0.3 + 0.7 * math.exp(-(b * b) / 0.06):
            continue
        pos.append(v)
        mag.append(math.log10(lo + rnd() * (hi - lo)) / 0.47)
        product = rnd() * rnd()
        bv.append(-0.1 + 1.5 * product + 0.3 * rnd())
    return np.array(pos), np.array(mag), np.array(bv)


def limiting_mag(sun_el: float, light: float) -> float:
    """Faintest magnitude the naked eye sees with the sun ``sun_el`` deg up
    and this much daylight (0..1)."""
    by_sun = -1.0 + max(0.0, -sun_el - 3.0) * 0.45
    by_light = 5.0 - max(0.0, light - 0.13) * 30.0
    return max(-2.0, min(5.0, by_sun, by_light))


def _unit(bearing_deg: float, alt_deg: float) -> tuple:
    b, a = math.radians(bearing_deg), math.radians(alt_deg)
    return (math.sin(b) * math.cos(a), math.cos(b) * math.cos(a), math.sin(a))


def _clamp(x, low=0.0, high=1.0):
    return min(high, max(low, x))


def conditions(sky: dict, *, fov_deg: float, visibility_nm: float, haze_k: float) -> dict:
    """How the night sky shows in one picture: where it stands, how faint
    the stars go through this optic (``fov_deg``), how clear the air is and
    how bright the Milky Way is.  ``haze_k`` is the shaded sky's haze
    steepness (``skyshade.haze_k``)."""
    light = float(sky["light"])
    over = _clamp(float(sky["cloud"]))
    precip = float(sky["intensity"]) if sky["precipitation"] in ("rain", "snow") else 0.0
    fog = _clamp(1.0 - visibility_nm / 3.0)
    lat = float(sky.get("latitude", 55.0))
    doy = float(sky.get("day_of_year", DEFAULT_DAY_OF_YEAR))
    hour = float(sky.get("hour", 0.0))
    rot = rotation(lat, sidereal_deg(doy, hour))
    moon_alt = float(sky["moon_alt_deg"])
    moon = (_clamp(math.sin(math.radians(moon_alt)) * 4.0) * (1.0 - over)
            * _clamp(float(sky["moon_illumination"])))
    # Glasses and periscope gather more light: fainter stars, a little
    # bigger, still points.
    gain_mag = max(1.0, 55.0 / max(1.0, fov_deg))
    lim = limiting_mag(float(sky["sun_alt_deg"]), light) + 2.5 * math.log10(gain_mag)
    clear = ((1.0 - precip) * (1.0 - min(1.0, fog * 1.5))
             * (1.0 - float(_smoothstep(0.8, 0.97, over))))
    show = clear > 0.01 and lim > -1.6
    pole, centre = rot @ GAL_POLE, rot @ GAL_CENTRE
    return dict(
        lat=lat, doy=doy, hour=hour, rot=rot, lim=lim,
        gain=clear * min(1.6, gain_mag ** 0.25),
        px=POINT_PX * (1.0 + 0.12 * math.log2(gain_mag)),
        ext=0.25 + 0.3 * min(1.0, precip + fog + over * 0.3),
        haze_k=haze_k * 1.4,
        moon=_unit(float(sky["moon_bearing"]), moon_alt), moon_k=moon,
        show=show, faint=show and lim - 0.4 * moon > 4.5,
        # Only well after twilight, on a clear night; the moon washes most
        # of it out.
        milky=(clear * float(_smoothstep(3.8, 4.8, lim)) * (1.0 - 0.6 * moon)) if show else 0.0,
        gal_pole=tuple(float(v) for v in pole), gal_centre=tuple(float(v) for v in centre))


_LOCAL: dict = {}


def _local(c: dict, with_faint: bool) -> dict:
    """Every star's place for the picture's clock (cached per sky)."""
    key = (c["lat"], c["doy"], c["hour"], with_faint)
    if _LOCAL.get("key") == key:
        return _LOCAL["value"]
    pos, mag, bv = catalog()
    index = np.arange(len(mag), dtype=float)
    if with_faint:
        fpos, fmag, fbv = faint()
        pos, mag, bv = np.vstack([pos, fpos]), np.concatenate([mag, fmag]), np.concatenate([bv, fbv])
        index = np.arange(len(mag), dtype=float)
    d = pos @ c["rot"].T
    up = np.clip(d[:, 2], -1.0, 1.0)
    value = dict(d=d, mag=mag, bv=bv,
                 bearing=np.degrees(np.arctan2(d[:, 0], d[:, 1])) % 360.0,
                 elev=np.degrees(np.arcsin(up)),
                 phase=(index * _GOLDEN % 1.0) * math.tau)
    _LOCAL.update(key=key, value=value)
    return value


def _bv_colour(bv):
    def mix(a, b, t):
        return np.asarray(a) + (np.asarray(b) - np.asarray(a)) * t[:, None]
    c = mix((0.66, 0.76, 1.0), (0.9, 0.93, 1.0), _smoothstep(-0.3, 0.1, bv))
    c = c + (np.array((1.0, 0.95, 0.86)) - c) * _smoothstep(0.1, 0.65, bv)[:, None]
    return c + (np.array((1.0, 0.8, 0.6)) - c) * _smoothstep(0.65, 1.6, bv)[:, None]


def points(c: dict, los: float, fov_deg: float, top_deg: float, t: float) -> dict:
    """The stars in a picture looking along ``los`` (true bearing) with
    ``fov_deg`` across, up to ``top_deg`` elevation, at display time ``t``:
    arrays of bearing, elevation (deg), alpha (0..1), colour (N, 3) and the
    point spread (px)."""
    empty = dict(bearing=np.zeros(0), elev=np.zeros(0), alpha=np.zeros(0),
                 rgb=np.zeros((0, 3)), sigma=np.zeros(0))
    if not c["show"]:
        return empty
    star = _local(c, c["faint"])
    off = (star["bearing"] - los + 180.0) % 360.0 - 180.0
    pick = np.flatnonzero((np.abs(off) <= fov_deg / 2.0 + 0.5) & (star["elev"] > 0.0)
                          & (star["elev"] <= top_deg))
    if pick.size == 0:
        return empty
    d = star["d"][pick]
    s = np.maximum(d[:, 2], 0.0)
    # Air mass (Kasten-Young-like): 1 overhead, about 38 at the horizon.
    airmass = 1.0 / (s + 0.025 * np.exp(-11.0 * s))
    m = star["mag"][pick] + c["ext"] * (airmass - 1.0)
    # The moon lifts the sky's glow: fewer faint stars, none right beside it.
    mx, my, mz = c["moon"]
    toward = np.maximum(d[:, 0] * mx + d[:, 1] * my + d[:, 2] * mz, 0.0)
    lim = c["lim"] - c["moon_k"] * (0.4 + 3.0 * toward ** 12)
    keep = m <= lim + 0.3
    pick, d, s, airmass, m, lim = pick[keep], d[keep], s[keep], airmass[keep], m[keep], lim[keep]
    phase = star["phase"][pick]
    amp = 0.08 + 0.55 * (1.0 - s) ** 5
    tt = t % 1000.0
    twinkle = 1.0 + amp * (0.6 * np.sin(tt * 7.3 + phase) + 0.4 * np.sin(tt * 17.9 + phase * 3.7))
    # Seen brightness grows much slower than the flux; magnitude 1 = 1.
    p = 10.0 ** (-0.12 * (m - 1.0)) * twinkle
    hz = np.exp(-s * c["haze_k"])
    vis = (_smoothstep(lim + 0.3, lim - 0.5, m) * (1.0 - hz) * _smoothstep(0.0, 0.035, d[:, 2])
           * c["gain"])
    alpha = np.clip(p * 1.25, 0.0, 1.0) * vis
    # Colour shows in the bright ones only; low down the air reddens them.
    k = np.clip(0.35 + 0.35 * p, 0.0, 0.85)
    white = np.array(STAR_WHITE)
    rgb = white + (_bv_colour(star["bv"][pick]) - white) * k[:, None]
    rgb = rgb * (1.0 + (np.array(REDDENED) - 1.0) * np.clip((airmass - 1.0) / 12.0, 0.0, 1.0)[:, None])
    sigma = c["px"] * (0.62 + 0.3 * np.clip(p, 0.0, 2.6))
    shown = alpha >= 0.004
    return dict(bearing=star["bearing"][pick][shown], elev=star["elev"][pick][shown],
                alpha=alpha[shown], rgb=rgb[shown], sigma=sigma[shown])


def to_linear(c):
    """sRGB (0..1) to linear light."""
    c = np.asarray(c, float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def to_srgb(c):
    """Linear light to sRGB (0..1)."""
    c = np.clip(np.asarray(c, float), 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1.0 / 2.4) - 0.055)


def add_milky_way(back, value):
    """The sky colours ``back`` (N, 3, sRGB 0..1) with the Milky Way's
    ``value`` (N,) added as light, as Tiefenkontakt's sky adds it before
    its output conversion."""
    return to_srgb(to_linear(back) + np.outer(value, MILKY_COLOR))


def _mw_clouds(lon, b):
    gx, gy = lon * 16.0, b * 16.0
    clump = _smoothstep(0.25, 0.75, fbm(gx + 17.0, gy + 3.0))
    lane = _smoothstep(0.45, 0.7, fbm(gx * 1.7 + 5.0, gy * 1.7 + 11.0))
    return (0.35 + 1.1 * clump) * (1.0 - 0.5 * lane) * (0.85 + 0.3 * noise(gx * 8.75, gy * 8.75))


def milky_way(c: dict, bearing_deg, elev_deg):
    """Brightness (0..about 0.05) of the Milky Way at the true directions
    ``bearing_deg``/``elev_deg`` (arrays): a faint, mottled band along the
    galactic plane, wider and brighter toward Sagittarius, split by the dark
    rift, fading into the haze low down."""
    bearing_deg = np.asarray(bearing_deg, float)
    out = np.zeros(bearing_deg.shape)
    if c["milky"] <= 0.002:
        return out
    b_, e = np.radians(bearing_deg), np.radians(np.asarray(elev_deg, float))
    ce = np.cos(e)
    d = np.stack([np.sin(b_) * ce, np.cos(b_) * ce, np.sin(e)], axis=-1)
    pole, centre = np.array(c["gal_pole"]), np.array(c["gal_centre"])
    b = d @ pole
    pl = d - b[..., None] * pole
    shifted = pl + 1e-5
    l = (shifted @ centre) / np.linalg.norm(shifted, axis=-1)
    to_c = 0.5 + 0.5 * l
    w = 0.09 + 0.09 * to_c * to_c
    on = (np.abs(b) < 2.0 * w) & (d[..., 2] > 0.0)
    if not on.any():
        return out
    pl, b, l, to_c, w, dz = pl[on], b[on], l[on], to_c[on], w[on], d[..., 2][on]
    band = np.exp(-b * b / (w * w))
    lon = np.arctan2(pl @ np.cross(pole, centre), pl @ centre)
    cl = _mw_clouds(lon, b)
    wrapped = np.abs(lon) > 2.7
    if wrapped.any():
        other = _mw_clouds(lon - np.sign(lon) * 6.2832, b)
        cl = np.where(wrapped, cl + (other - cl) * 0.5 * _smoothstep(2.7, 3.1416, np.abs(lon)), cl)
    rift = 1.0 - 0.6 * np.exp(-((b - 0.015) / 0.025) ** 2) * _smoothstep(-0.3, 0.7, l)
    mw = (0.35 + 0.65 * to_c * to_c) * band * cl * rift
    haze = 1.0 - np.exp(-dz * c["haze_k"] / 1.4)
    out[on] = mw * c["milky"] * 0.022 * _smoothstep(0.0, 0.25, dz) * haze
    return out
