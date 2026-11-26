"""The real night sky of the eyepieces (src/ui/stars.py, a port of
Tiefenkontakt's stars) and its browser twin (data/commander/js/views/stars.js)."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pygame
import pytest

from src.ui import horizon, quality, sight_scene, skyshade, stars

ROOT = Path(__file__).resolve().parents[1]


def _sky(hour=23.5, cloud=0.1, precipitation="none", intensity=0.0, illumination=0.0,
         latitude=55.0, day_of_year=220):
    age = 0.5 if illumination < 0.1 else 14.0
    return sight_scene.sky_values(hour, age, illumination, cloud, precipitation, intensity, 230.0,
                                  latitude=latitude, day_of_year=day_of_year)


def _night(sky, fov=40.0, visibility=25.0):
    return stars.conditions(sky, fov_deg=fov, visibility_nm=visibility,
                            haze_k=skyshade.haze_k(sky, visibility))


def _place(c, ra, dec):
    d = c["rot"] @ stars.equ_vec(ra, dec)
    return (np.degrees(np.arctan2(d[0], d[1])) % 360.0, np.degrees(np.arcsin(d[2])))


def _count(c, fov=40.0, top=45.0):
    return sum(len(stars.points(c, b, fov, top, 5.0)["alpha"]) for b in range(0, 360, int(fov)))


def _light(c, fov=40.0, top=45.0):
    return sum(stars.points(c, b, fov, top, 5.0)["alpha"].sum() for b in range(0, 360, int(fov)))


def test_the_catalogue_is_tiefenkontakts_and_the_browser_has_the_same():
    data = json.loads((ROOT / "data" / "sky" / "bright_stars.json").read_text())
    js = (ROOT / "data" / "commander" / "js" / "views" / "star-catalog.js").read_text()
    assert data["count"] == 986 == int(re.search(r"STAR_COUNT = (\d+)", js).group(1))
    assert "".join(re.findall(r"'([A-Za-z0-9+/=]+)'", js)) == data["stars_b64"]
    pos, mag, bv = stars.catalog()
    assert len(mag) == 986 and mag.min() < -1.0 and mag.max() < 4.7
    assert np.allclose(np.linalg.norm(pos, axis=1), 1.0)


def test_polaris_stands_at_the_latitude_and_the_sky_turns_with_the_seasons():
    for latitude in (40.0, 55.0, 70.0):
        for hour in (0.0, 6.0, 21.0):
            bearing, elev = _place(_night(_sky(hour=hour, latitude=latitude)), 37.95, 89.26)
            assert abs(elev - latitude) < 1.0 and min(bearing, 360.0 - bearing) < 3.0
    # Orion (Betelgeuse) at midnight: up in January, down in July.
    assert _place(_night(_sky(hour=0.0, day_of_year=15)), 88.79, 7.41)[1] > 20.0
    assert _place(_night(_sky(hour=0.0, day_of_year=196)), 88.79, 7.41)[1] < 0.0
    # At midnight the sun's right ascension stands under the north horizon.
    c = _night(_sky(hour=0.0, day_of_year=80))
    assert _place(c, stars.sun_ra(80), 0.0)[1] < -30.0


def test_the_stars_come_out_in_the_dark_and_hide_by_day_and_in_weather():
    night = _count(_night(_sky()))
    assert night > 40
    assert _count(_night(_sky(hour=12.0))) == 0
    assert _count(_night(_sky(cloud=0.99))) == 0
    assert _light(_night(_sky(precipitation="rain", intensity=0.6))) < 0.5 * _light(_night(_sky()))
    assert _count(_night(_sky(), visibility=0.5)) == 0
    # A bright moon high up washes out the faint ones.
    assert _count(_night(_sky(illumination=1.0))) < 0.7 * night
    # Low down the air dims and reddens them.
    c = _night(_sky())
    p = stars.points(c, 0.0, 360.0, 90.0, 5.0)
    low, high = p["elev"] < 8.0, p["elev"] > 40.0
    assert p["rgb"][low][:, 2].mean() < p["rgb"][high][:, 2].mean()


def test_the_optics_reach_fainter_stars_and_the_twinkle_moves():
    naked, glasses = _night(_sky(), fov=60.0), _night(_sky(), fov=8.0)
    assert glasses["lim"] > naked["lim"] + 2.0 and glasses["faint"]
    area = lambda c: len(stars.points(c, 180.0, 8.0, 45.0, 5.0)["alpha"])
    assert area(glasses) > 2 * max(1, area(naked))
    a = stars.points(naked, 180.0, 60.0, 45.0, 5.0)["alpha"]
    b = stars.points(naked, 180.0, 60.0, 45.0, 5.3)["alpha"]
    assert len(a) and not np.allclose(a[:len(b)], b[:len(a)])


def test_the_milky_way_lies_along_the_galactic_plane_on_dark_nights():
    c = _night(_sky())
    pole = np.array(c["gal_pole"])
    # Directions on the galactic plane above the horizon and near its pole.
    on_plane, near_pole = [], []
    for bearing in range(0, 360, 3):
        for elev in range(10, 89, 3):
            b, e = np.radians(bearing), np.radians(elev)
            d = np.array((np.sin(b) * np.cos(e), np.cos(b) * np.cos(e), np.sin(e)))
            g = abs(d @ pole)
            (on_plane if g < 0.03 else near_pole if g > 0.8 else []).append((bearing, elev))
    plane = stars.milky_way(c, *np.array(on_plane).T)
    assert plane.mean() > 0.005 and stars.milky_way(c, *np.array(near_pole).T).max() == 0.0
    assert stars.milky_way(_night(_sky(hour=12.0)), *np.array(on_plane).T).max() == 0.0
    assert stars.milky_way(_night(_sky(illumination=1.0)), *np.array(on_plane).T).mean() \
        < 0.6 * plane.mean()


def _picture(level, sky, **kw):
    surface = pygame.Surface((400, 200))
    args = dict(line_of_sight=40.0, fov_deg=32.0, night=True, visibility_nm=25.0,
                motion=(0.0, 0.0), outlines=[], crosshair_deg=None, anim_t=2.0, sky=sky,
                sea_state=2.0, elevation_deg=35.0)
    args.update(kw)
    previous = quality.LEVEL
    quality.LEVEL = level
    try:
        horizon.draw_horizon(surface, (0, 0, 400, 200), **args)
    finally:
        quality.LEVEL = previous
    return pygame.surfarray.array3d(surface).astype(int)


def test_the_picture_adds_the_stars_as_light_and_the_low_level_keeps_the_old_field(monkeypatch):
    sky = _sky()
    with_stars = _picture("normal", sky)
    monkeypatch.setattr(sight_scene, "draw_night_stars", lambda *a: None)
    without = _picture("normal", sky)
    assert (with_stars >= without).all() and (with_stars - without).max() > 60
    old = []
    monkeypatch.setattr(sight_scene, "_draw_stars", lambda *a: old.append(1))
    _picture("low", sky)
    _picture("normal", sky)
    assert old == [1]


def test_the_browser_shows_the_same_night_sky():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not installed")
    cases = [(_sky(), 40.0, 25.0, 180.0), (_sky(hour=2.0, day_of_year=20, illumination=0.9), 8.0,
                                           25.0, 120.0),
             (_sky(hour=21.3, latitude=12.0, cloud=0.5), 16.0, 6.0, 300.0)]
    rng = np.random.default_rng(3)
    bearings, elevations = rng.uniform(0, 360, 300), rng.uniform(-3, 89, 300)
    expected = []
    for sky, fov, visibility, los in cases:
        c = _night(sky, fov, visibility)
        p = stars.points(c, los, fov, 50.0, 12.3)
        milky = stars.milky_way(c, bearings, elevations)
        expected.append(dict(lim=c["lim"], milky=c["milky"], points=np.hstack([
            p["bearing"][:, None], p["elev"][:, None], p["alpha"][:, None], p["rgb"],
            p["sigma"][:, None]]), mw=milky))
    script = (
        "const m = await import('./data/commander/js/views/stars.js');"
        "const sky = await import('./data/commander/js/views/sky.js');"
        f"const cases = {json.dumps([[s, f, v, l] for s, f, v, l in cases])};"
        f"const b = {json.dumps(bearings.tolist())}, e = {json.dumps(elevations.tolist())};"
        "const out = cases.map(([s, fov, visibility, los]) => {"
        " const c = m.conditions(s, {fov, visibility, hazeK: sky.hazeK(s, visibility)});"
        " const p = m.points(c, los, fov, 50, 12.3);"
        " return {lim: c.lim, milky: c.milky, points: p.alpha.map((a, i) => [p.bearing[i],"
        " p.elev[i], a, ...p.rgb.slice(i * 3, i * 3 + 3), p.sigma[i]]),"
        " mw: b.map((x, i) => m.milkyWay(c, x, e[i]))}; });"
        "console.log(JSON.stringify(out));")
    result = subprocess.run([node, "--input-type=module", "-e", script], cwd=ROOT,
                            capture_output=True, text=True, timeout=120, check=True)
    for want, got in zip(expected, json.loads(result.stdout)):
        assert abs(want["lim"] - got["lim"]) < 1e-12 and abs(want["milky"] - got["milky"]) < 1e-12
        assert len(want["points"]) == len(got["points"]) > 0
        assert np.abs(np.array(got["points"]) - want["points"]).max() < 1e-9
        assert np.abs(np.array(got["mw"]) - want["mw"]).max() < 1e-12
