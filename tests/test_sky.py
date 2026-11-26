"""The shaded sky of the sight pictures (src/ui/skyshade.py, a port of
Tiefenkontakt's sky) and its browser twin (data/commander/js/views/sky.js)."""

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pygame
import pytest

from src.ui import horizon, quality, sight_scene, skyshade

ROOT = Path(__file__).resolve().parents[1]


def _params(hour=12.0, cloud=0.5, precipitation="none", intensity=0.0, visibility_nm=20.0,
            **kw):
    sky = sight_scene.sky_values(hour, 10.0, 0.8, cloud, precipitation, intensity, 230.0)
    args = dict(sun_el=25.0, moon_el=15.0, visibility_nm=visibility_nm, own_e=500.0,
                own_n=-300.0, t=20.0)
    args.update(kw)
    return sky, skyshade.sky_params(sky, sight_scene.palette(sky, 0.0), **args)


def _cover(cloud):
    _, p = _params(cloud=cloud)
    bearings = np.repeat(np.linspace(0.0, 360.0, 90, endpoint=False), 6)
    elevations = np.tile(np.linspace(15.0, 60.0, 6), 90)
    return skyshade.shade(p, bearings, elevations)[2].mean()


def test_the_cloud_deck_follows_the_cloud_cover():
    clear, broken, overcast = _cover(0.05), _cover(0.5), _cover(0.95)
    assert clear < 0.1 < broken < overcast and overcast > 0.9


def test_the_haze_band_sits_on_the_horizon_and_thickens_in_rain():
    sky, p = _params(cloud=0.0)
    haze = np.array(sight_scene.palette(sky, 0.0)["haze"]) / 255.0
    back = skyshade.shade(p, np.array([200.0, 200.0]), np.array([0.5, 40.0]))[0]
    assert np.abs(back[0] - haze).max() < np.abs(back[1] - haze).max()
    # At 6 degrees (away from the sun) rain hazes the sky more than clear air.
    _, wet = _params(cloud=0.0, precipitation="rain", intensity=0.8)
    rainy = skyshade.shade(wet, np.array([20.0]), np.array([6.0]))[0][0]
    clear = skyshade.shade(p, np.array([20.0]), np.array([6.0]))[0][0]
    assert np.abs(rainy - haze).max() < np.abs(clear - haze).max()


def test_the_sun_has_a_halo_and_clouds_are_dark_at_night():
    _, p = _params(cloud=0.0)
    toward, away = skyshade.shade(p, np.array([0.0, 180.0]) + _sun_bearing(),
                                  np.array([25.0, 25.0]))[0]
    assert toward.sum() > away.sum() + 0.3
    _, day = _params(cloud=0.9)
    _, night = _params(hour=1.0, cloud=0.9)
    elev = np.full(20, 30.0)
    bearings = np.linspace(0.0, 360.0, 20)
    assert skyshade.shade(night, bearings, elev)[1].mean() < 0.2 * \
        skyshade.shade(day, bearings, elev)[1].mean()


def _sun_bearing():
    return sight_scene.sky_values(12.0, 10.0, 0.8, 0.0, "none", 0.0, 230.0)["sun_bearing"]


def test_the_deck_drifts_with_the_wind_and_the_own_way():
    bearings, elevations = np.linspace(150.0, 250.0, 50), np.full(50, 30.0)
    _, now = _params()
    _, later = _params(t=300.0)
    _, moved = _params(own_e=5500.0)
    base = skyshade.shade(now, bearings, elevations)[2]
    assert not np.allclose(base, skyshade.shade(later, bearings, elevations)[2])
    assert not np.allclose(base, skyshade.shade(moved, bearings, elevations)[2])


def _picture(level, sky, **kw):
    surface = pygame.Surface((400, 200))
    args = dict(line_of_sight=200.0, fov_deg=32.0, night=False, visibility_nm=20.0,
                motion=(0.0, 0.0), outlines=[], crosshair_deg=None, anim_t=2.0, sky=sky,
                sea_state=3.0)
    args.update(kw)
    previous = quality.LEVEL
    quality.LEVEL = level
    try:
        horizon.draw_horizon(surface, (0, 0, 400, 200), **args)
    finally:
        quality.LEVEL = previous
    return surface


def test_the_picture_reuses_its_sky_and_the_low_level_keeps_the_old_one(monkeypatch):
    sky = sight_scene.sky_values(12.0, 10.0, 0.8, 0.6, "none", 0.0, 230.0)
    skyshade._CACHE.clear()
    calls = []
    real = skyshade.shade
    monkeypatch.setattr(skyshade, "shade", lambda *a: calls.append(1) or real(*a))
    _picture("normal", sky)
    _picture("normal", sky, anim_t=2.1)
    assert len(calls) == 1                     # the same sky a moment later
    _picture("normal", sky, line_of_sight=210.0)
    assert len(calls) == 2                     # turned: shaded again
    _picture("low", sky)
    assert len(calls) == 2
    clouds = []
    monkeypatch.setattr(sight_scene, "_draw_clouds", lambda *a: clouds.append(1))
    _picture("low", sky)
    _picture("normal", sky, anim_t=2.2)
    assert clouds == [1]


def test_rain_streaks_are_translucent_near_long_far_short():
    streaks = sight_scene.rain_streaks(400, 200, 0.8, 0.3, 5.0)
    assert len(streaks) == int(sight_scene.RAIN_MAX * 2 * 0.8)
    longest = max(streaks, key=lambda s: s[3] - s[1])
    shortest = min(streaks, key=lambda s: s[3] - s[1])
    assert longest[4] > shortest[4] and all(0.0 < s[4] < 0.6 for s in streaks)


def test_the_browser_shades_the_same_sky_and_rain():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not installed")
    rng = np.random.default_rng(4)
    bearings, elevations = rng.uniform(0, 360, 200), rng.uniform(-5, 64, 200)
    cases = []
    for hour, cloud, kind, rain in ((17.9, 0.5, "none", 0.0), (11.0, 0.9, "rain", 0.6),
                                    (23.0, 0.3, "none", 0.0)):
        sky = sight_scene.sky_values(hour, 10.0, 0.8, cloud, kind, rain, 230.0)
        colors = sight_scene.palette(sky, 0.2)
        p = skyshade.sky_params(sky, colors, sun_el=20.0, moon_el=12.0, visibility_nm=5.0,
                                own_e=-1234.5, own_n=987.0, t=42.3)
        back, cloud_rgb, cover = skyshade.shade(p, bearings, elevations)
        wire = {k: ([list(c) for c in v] if isinstance(v, tuple) and isinstance(v[0], tuple)
                    else v) for k, v in colors.items()}
        cases.append((sky, wire, np.hstack([back, cloud_rgb, cover[:, None]])))
    script = (
        "const m = await import('./data/commander/js/views/sky.js');"
        "const scene = await import('./data/commander/js/views/sight-scene.js');"
        f"const cases = {json.dumps([[sky, wire] for sky, wire, _ in cases])};"
        f"const b = {json.dumps(bearings.tolist())}, e = {json.dumps(elevations.tolist())};"
        "const out = cases.map(([sky, colors]) => {"
        " const p = m.skyParams(sky, colors, {sunEl: 20, moonEl: 12, visibility: 5,"
        " ownE: -1234.5, ownN: 987, t: 42.3});"
        " return b.map((_, i) => { const x = new Float64Array(3), y = new Float64Array(3);"
        " const c = m.shade(p, b[i], e[i], x, y); return [...x, ...y, c]; }); });"
        "console.log(JSON.stringify({out, rain: scene.rainStreaks(400, 200, .7, .3, 12.3)}));")
    result = subprocess.run([node, "--input-type=module", "-e", script], cwd=ROOT,
                            capture_output=True, text=True, timeout=120, check=True)
    got = json.loads(result.stdout)
    for (_, _, expected), values in zip(cases, got["out"]):
        assert np.abs(np.array(values) - expected).max() < 1e-9
    assert np.allclose(got["rain"], sight_scene.rain_streaks(400, 200, 0.7, 0.3, 12.3))
