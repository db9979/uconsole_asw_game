"""The shaded sea of the sight pictures (src/ui/ocean.py, a port of
Tiefenkontakt's ocean) and its browser twin (data/commander/js/views/ocean.js)."""

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pygame
import pytest

from src.ui import horizon, ocean, quality, sight_scene

ROOT = Path(__file__).resolve().parents[1]


def _sky(hour=12.0, **extra):
    sky = sight_scene.sky_values(hour, 10.0, 0.2, 0.3, "none", 0.0, 230.0)
    sky.update(extra)
    return sky


def _params(sky, **kw):
    args = dict(sea_state=4.0, visibility_nm=12.0, eye_m=18.0, own_e=0.0, own_n=0.0, t=10.0)
    args.update(kw)
    return ocean.sea_params(sky, sight_scene.palette(sky, 0.0), **args)


def test_the_waves_grow_with_the_sea_state_and_run_downwind():
    heights = [ocean.sig_height(s) for s in range(10)]
    assert heights == sorted(heights) and heights[0] < 0.1 and heights[9] > 10.0
    calm, gale = ocean.waves(1.0, 0.0, 0, 0, 0), ocean.waves(8.0, 0.0, 0, 0, 0)
    assert gale["amp"] > 20.0 * calm["amp"]
    assert calm["share"].sum() == pytest.approx(1.0)
    # The wind blows from the north: the waves run south.
    assert gale["wind"] == pytest.approx((0.0, -1.0), abs=1e-12)
    # A gale's energy sits in the long waves, a calm sea's in the short ones.
    assert np.argmax(gale["share"]) < np.argmax(calm["share"])
    # Moving on the sea moves the phases: the field hangs on the water.
    moved = ocean.waves(4.0, 0.0, 100.0, 50.0, 0.0)["phase"]
    assert not np.allclose(moved, ocean.waves(4.0, 0.0, 0.0, 0.0, 0.0)["phase"])


def test_the_noise_tiles_and_stays_in_range():
    xs = np.linspace(-200.0, 200.0, 997)
    values = ocean.noise(xs, xs * 0.7)
    assert values.min() >= 0.0 and values.max() <= 1.0 and values.std() > 0.1
    size = ocean.NOISE_SIZE
    assert np.allclose(ocean.noise(xs + size, xs * 0.7), values)


def test_sun_glitter_fog_and_foam():
    day = _sky(12.0)
    p = _params(day, sea_state=3.0)
    sun = float(day["sun_bearing"])
    below = np.full(40, 3.0)
    toward = ocean.shade(p, np.full(40, sun) + np.linspace(-1, 1, 40), below, 0.3)
    away = ocean.shade(p, np.full(40, sun + 180.0) + np.linspace(-1, 1, 40), below, 0.3)
    assert toward.sum(axis=1).mean() > away.sum(axis=1).mean()
    # Far off the sea fades into the haze; in thick fog sooner.
    near = ocean.shade(_params(day, visibility_nm=0.5), np.array([90.0]), np.array([20.0]), 0.3)
    far = ocean.shade(_params(day, visibility_nm=0.5), np.array([90.0]), np.array([0.05]), 0.3)
    haze = np.array(sight_scene.palette(day, 0.0)["haze"]) / 255.0
    assert np.abs(far[0] - haze).max() < np.abs(near[0] - haze).max()
    # A gale throws more white water than a calm sea.
    bearings = np.linspace(0.0, 360.0, 720)
    below = np.full(720, 4.0)
    calm = ocean.shade(_params(day, sea_state=1.0), bearings, below, 0.5)
    gale = ocean.shade(_params(day, sea_state=8.0), bearings, below, 0.5)
    assert (gale.min(axis=1) > 0.6).mean() > (calm.min(axis=1) > 0.6).mean()
    # By night the sea is dark.
    night = ocean.shade(_params(_sky(1.0)), bearings, below, 0.5)
    assert night.mean() < 0.5 * calm.mean()


def test_the_sea_is_drawn_in_cells_by_graphics_level():
    assert ocean.grid_size(640, 300, "normal")[0] * ocean.grid_size(640, 300, "normal")[1] \
        < ocean.grid_size(640, 300, "full")[0] * ocean.grid_size(640, 300, "full")[1]
    columns, rows = ocean.grid_size(80, 30, "full")
    assert columns * rows <= 80 * 30 / ocean.MIN_CELL_PX * 1.3


def test_the_low_level_keeps_the_wave_rows(monkeypatch):
    sky = dict(sight_scene.plain_sky(False), wind_from_deg=0.0)

    def picture():
        surface = pygame.Surface((400, 200))
        horizon.draw_horizon(surface, (0, 0, 400, 200), line_of_sight=0.0, fov_deg=32.0,
                             night=False, visibility_nm=30.0, motion=(0.0, 0.0),
                             outlines=[], crosshair_deg=None, anim_t=2.0, sky=sky,
                             sea_state=4.0)

    calls = []
    monkeypatch.setattr(sight_scene, "_draw_sea",
                        lambda *a, **k: calls.append(1))
    monkeypatch.setattr(quality, "LEVEL", "low")
    picture()
    assert calls
    calls.clear()
    monkeypatch.setattr(quality, "LEVEL", "normal")
    picture()
    assert not calls


def test_the_browser_shades_the_same_sea():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not installed")
    sky = sight_scene.sky_values(17.5, 10.0, 0.8, 0.3, "rain", 0.4, 230.0)
    colors = sight_scene.palette(sky, 0.2)
    p = ocean.sea_params(sky, colors, sea_state=6.0, visibility_nm=12.0, eye_m=18.0,
                         own_e=1234.5, own_n=-987.0, t=42.3)
    rng = np.random.default_rng(1)
    bearings, below = rng.uniform(0, 360, 300), rng.uniform(0.01, 12, 300)
    expected = ocean.shade(p, bearings, below, 0.4)
    wire = {k: ([list(c) for c in v] if isinstance(v, tuple) and isinstance(v[0], tuple) else v)
            for k, v in colors.items()}
    script = (
        "const m = await import('./data/commander/js/views/ocean.js');"
        f"const p = m.seaParams({json.dumps(sky)}, {json.dumps(wire)},"
        " {seaState: 6, visibility: 12, eye: 18, ownE: 1234.5, ownN: -987, t: 42.3});"
        f"const b = {json.dumps(bearings.tolist())}, d = {json.dumps(below.tolist())};"
        "const out = []; let lattice = 0;"
        "for (let i = 0; i < b.length; i++) {"
        " const c = new Float64Array(3); m.shade(p, b[i], d[i], .4, c); out.push(Array.from(c)); }"
        "for (let i = 0; i < m.LATTICE.length; i++) lattice += m.LATTICE[i] * ((i % 97) + 1);"
        "console.log(JSON.stringify({out, lattice}));")
    result = subprocess.run([node, "--input-type=module", "-e", script], cwd=ROOT,
                            capture_output=True, text=True, timeout=60, check=True)
    got = json.loads(result.stdout)
    assert np.abs(np.array(got["out"]) - expected).max() < 1e-9
    flat = ocean.LATTICE.ravel()
    assert got["lattice"] == pytest.approx(float((flat * (np.arange(flat.size) % 97 + 1)).sum()))
