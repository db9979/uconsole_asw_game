"""Real land heights on the horizon: the ETOPO1 relief file, the land bands
the eye sees and their browser twin."""

import json
import math
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pygame
import pytest

from src.ui import horizon
from src.world import real_relief
from src.world.coastline import Coastline
from src.world.projection import lonlat_to_nm
from tools import build_real_relief

ROOT = Path(__file__).resolve().parents[1]
# Sector real-041 (off Shikoku and the Kii peninsula) and two known summits.
SHIKOKU = 41
ISHIZUCHI = (133.1153, 33.7678, 1982.0)


def _world(index):
    return SimpleNamespace(coast=Coastline.generate(0, 500.0, sector_index=index))


def _relief(index):
    world = _world(index)
    return world, real_relief.for_coast(world.coast)


def test_the_relief_file_holds_land_tiles_for_the_sectors():
    data = real_relief._load()
    assert data["schema"] == 1 and data["tile"] == 60 // data["step_arcmin"]
    assert 1000 < len(data["tiles"]) < 3000
    assert "ETOPO1" in data["provenance"]["relief"]


def test_a_known_summit_stands_at_its_height_and_the_sea_is_flat():
    world, relief = _relief(SHIKOKU)
    center = world.coast.metadata["center"]
    lon, lat, top = ISHIZUCHI
    x, y = lonlat_to_nm(lon, lat, center["longitude"], center["latitude"], 500.0)
    # 2-NM grid: the summit is smoothed, but a mountain it is.
    assert 0.6 * top < float(relief.heights(np.array([x]), np.array([y]))[0]) <= top
    # Open Pacific south of the sector's middle.
    assert float(relief.heights(np.array([250.0]), np.array([480.0]))[0]) == 0.0
    assert relief.peak_m > 1500.0


def test_a_scaled_world_reads_the_same_place():
    world = SimpleNamespace(coast=Coastline.generate(0, 250.0, sector_index=SHIKOKU))
    small = real_relief.for_coast(world.coast)
    _, full = _relief(SHIKOKU)
    xs, ys = np.array([180.0, 300.0]), np.array([120.0, 200.0])
    assert np.allclose(small.heights(xs / 2.0, ys / 2.0), full.heights(xs, ys))


def test_a_coast_without_a_sector_keeps_the_assumed_heights():
    coast = Coastline({"landmasses": [{"name": "Insel", "points": [[100, 100], [110, 100],
                                                                   [110, 110], [100, 110]]}]},
                      500.0)
    assert real_relief.for_coast(coast) is None
    land = horizon.land_view(SimpleNamespace(coast=coast), 105.0, 114.0, 18.0)
    assert land.rise.shape == (1, horizon.LAND_RAYS)
    ahead = land.distance[0, 0]
    assert 3.9 < ahead < 4.1 and land.rise[0, 0] > 0.0


def test_mountains_stand_behind_the_coast_in_paler_bands():
    world, relief = _relief(SHIKOKU)
    rng = np.random.default_rng(3)
    best = None
    for x, y in rng.uniform(40.0, 460.0, size=(120, 2)):
        if world.coast.on_land(x, y):
            continue
        land = horizon.land_view(world, x, y, 18.0)
        far = land.rise[2]
        if np.isfinite(far).any() and (best is None or np.nanmax(far) > best[0]):
            best = (np.nanmax(far), land)
    peak, land = best
    assert peak > 0.5
    # The far band's crests lie beyond the near band's limit and below the
    # height hidden behind the sea horizon nothing shows.
    seen = np.isfinite(land.rise[2])
    assert (land.distance[2][seen] >= horizon.LAND_BANDS_NM[2]).all()
    assert (land.rise[np.isfinite(land.rise)] > 0.0).all()
    assert land.color.dtype == np.uint8 and land.color.shape == land.rise.shape + (3,)


def test_land_hidden_behind_the_sea_horizon_is_not_seen():
    assert horizon._sea_hidden_m(1.17 * math.sqrt(18.0), 18.0) == 0.0
    # 40 m of coast 20 NM off the bridge (horizon ~5 NM) is below it.
    assert horizon._rise_deg(40.0, 20.0, 18.0) < 0.0
    assert horizon._rise_deg(1500.0, 20.0, 18.0) > 1.0


def test_land_colours_follow_height_slope_and_the_snow_line():
    colors = horizon.land_colors([2.0, 80.0, 900.0, 2500.0, 2500.0],
                                 [0.0, 0.0, 0.3, 0.05, 2.0], 2000.0)
    sand, low, steep, snow, cliff = (tuple(int(v) for v in row) for row in colors)
    assert sand == horizon.LAND_SAND and snow[0] > 200
    assert low[1] > low[0] and low[1] > low[2]   # green
    assert abs(steep[0] - steep[1]) < 12        # rock grey
    assert cliff == horizon.LAND_ROCK
    assert horizon.snow_line_m(60.0) < horizon.snow_line_m(35.0) < horizon.snow_line_m(10.0)


def test_the_bands_are_drawn_far_to_near_over_the_sea():
    world, _relief_ = _relief(SHIKOKU)
    land = horizon.land_view(world, 120.0, 150.0, 18.0)
    rays = land.rise.shape[1]
    toward = int(np.nanargmax(np.nanmax(np.where(np.isfinite(land.rise), land.rise, -1.0),
                                        axis=0)))
    bearing = toward * 360.0 / rays
    surface = pygame.Surface((320, 200))
    kwargs = dict(fov_deg=40.0, night=False, visibility_nm=40.0, motion=(0.0, 0.0),
                  outlines=[], line_of_sight=bearing)
    horizon.draw_horizon(surface, (0, 0, 320, 200), land=land, **kwargs)
    with_land = surface.get_at((160, 98))
    horizon.draw_horizon(surface, (0, 0, 320, 200), **kwargs)
    assert surface.get_at((160, 98)) != with_land


def test_the_browser_reads_the_packed_land():
    world, _relief_ = _relief(SHIKOKU)
    land = horizon.land_view(world, 120.0, 150.0, 18.0)
    wire = horizon.land_wire(land)
    assert wire is horizon.land_wire(land)   # cached per land view
    assert set(wire) == {"rays", "bands", "data"}
    assert wire["rays"] == horizon.LAND_RAYS // horizon.LAND_WIRE_STRIDE
    # Only the rays with land travel: a few kB per state.
    assert len(json.dumps(wire)) < 6_000
    assert horizon.land_wire(None) is None
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not installed")
    script = (
        "const m = await import('./data/commander/js/views/sight-scene.js');"
        f"const land = m.decodeLand({json.dumps(wire)});"
        "console.log(JSON.stringify({palette: m.LAND_PALETTE, bands: land.bands.map((b) => ({"
        "rise: Array.from(b.rise, (v) => Number.isNaN(v) ? null : v),"
        "range: Array.from(b.range, (v) => Number.isFinite(v) ? v : null),"
        "color: b.color}))}));")
    result = subprocess.run([node, "--input-type=module", "-e", script], cwd=ROOT,
                            capture_output=True, text=True, timeout=60, check=True)
    decoded = json.loads(result.stdout)
    palette = horizon.land_palette()
    assert decoded["palette"] == palette.tolist()
    stride = horizon.LAND_WIRE_STRIDE
    for band, row in enumerate(decoded["bands"]):
        rise = land.rise[band, ::stride]
        seen = np.isfinite(rise)
        assert [value is not None for value in row["rise"]] == seen.tolist()
        got = np.array([value for value in row["rise"] if value is not None])
        assert np.allclose(got, rise[seen], atol=0.006)
        far = np.array([value for value in row["range"] if value is not None])
        assert np.allclose(far, land.distance[band, ::stride][seen],
                           atol=horizon.LAND_WIRE_NM / 2 + 1e-6)
        # Each colour travels as the nearest palette colour.
        sent = land.color[band, ::stride][seen].astype(int)
        nearest = palette[((sent[:, None, :] - palette.astype(int)) ** 2).sum(-1).argmin(-1)]
        assert (np.array(row["color"])[seen] == nearest).all()
        assert not seen.any() or np.abs(nearest.astype(int) - sent).max() < 30


def test_the_build_tool_covers_every_sector_tile():
    tiles = build_real_relief.sector_tiles(33.0, 134.0)
    boxes = build_real_relief.fetch_boxes(tiles)
    covered = {(lat, lon) for lat0, lat1, lon0, lon1 in boxes
               for lat in range(lat0, lat1) for lon in range(lon0, lon1)}
    assert tiles <= covered
    # Across the date line the tiles wrap to -180.
    wrapped = build_real_relief.sector_tiles(-43.6, 175.2)
    assert any(lon < -170 for _, lon in wrapped) and all(-180 <= lon < 180
                                                         for _, lon in wrapped)
    heights = [0.0, 5.0, 1000.0, 4500.0] * (build_real_relief.TILE ** 2 // 4)
    data = {"tile": build_real_relief.TILE, "height_scale_m": build_real_relief.HEIGHT_SCALE_M,
            "tiles": {"33,134": build_real_relief.encode_tile(heights)}}
    relief = real_relief.Relief(data, 33.5, 134.5)
    decoded = relief.grid[(33 - relief.lat0) * 30, (134 - relief.lon0) * 30:][:4]
    assert decoded[0] == 0.0 and abs(decoded[1] - 5.0) < 1.0
    assert abs(decoded[2] - 1000.0) < 20.0 and abs(decoded[3] - 4500.0) < 1.0
