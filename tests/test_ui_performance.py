"""Structural render-performance regressions for the 1280x720 audit paths."""

import inspect
import math
import copy
from types import SimpleNamespace

import numpy as np
import pygame
import pytest

from src.core import config
from src.core.i18n import Translator
from src.ui import map_view, sonar_view, stations_view
from src.ui.viewport import Viewport
from src.world.coastline import Coastline
from src.world.world import World


def test_map_culls_landmass_bounds_before_point_transforms():
    coast = Coastline({"landmasses": [
        {"name": "visible", "points": [(45, 45), (55, 45), (50, 55)]},
        {"name": "offscreen", "points": [(450.25, 450.25),
                                            (460.25, 450.25),
                                            (455.25, 460.25)]},
    ]}, 500)
    view = Viewport(500, 1, 14)
    view.set_rect((0, 0, 640, 510))
    view.scale = 14
    view.cx = view.cy = 50
    transformed = []
    original = view.world_to_screen

    def record(x, y):
        transformed.append((x, y))
        return original(x, y)

    view.world_to_screen = record
    visible = map_view._visible_landmasses(coast, view, view.rect)
    polygons = [[view.world_to_screen(x, y) for x, y in land.points]
                for land in visible]

    assert [land.name for land in visible] == ["visible"]
    assert len(polygons) == 1
    assert not any(x == 450.25 for x, _ in transformed)


def test_opz_bounds_cull_preserves_exact_edge_clipping():
    data = {"landmasses": [
        {"name": "near", "points": [(-10, 0), (10, 0), (10, 12)]},
        {"name": "far", "points": [(300 + math.cos(i) * 5,
                                      300 + math.sin(i) * 5)
                                     for i in range(40)]},
    ]}
    coast = Coastline(data, 500)

    expected = coast.contour_segments_in_circle(0, 0, 5)
    actual = stations_view._contour_segments_in_circle(coast, 0, 0, 5)

    assert actual == expected
    assert not stations_view._bounds_intersect_circle(
        coast.landmasses[1].bounds, 0, 0, 5)


def test_lofar_new_sequence_avoids_serialization_and_preserves_pixels():
    rows = np.linspace(0.0, 1.2, 6 * 110).reshape(6, 110)
    controls = (6.0, 25.0, 240.0, True, 8.0)
    frequencies = [config.lofar_bin_freq(index) for index in range(rows.shape[1])]
    gain = 10.0 ** (controls[0] / 20.0)
    shaft = 10.0 + 1.9 * controls[4]
    # Notch attenuation and gain both precede display clipping. The old
    # reference incorrectly bypassed gain for notched bins.
    reference = np.asarray([
        [0.0 if not controls[1] <= frequency <= controls[2]
         else min(1.0, value * gain * 0.15) if abs(frequency - shaft) < 5.0
         else min(1.0, value * gain)
         for value, frequency in zip(row, frequencies)]
        for row in rows
    ])
    processed = sonar_view._process_lofar_rows(rows, controls)
    reference_linear = np.asarray([sonar_view._linear_lofar(row, 601)
                                   for row in reference])
    processed_linear = np.asarray([sonar_view._linear_lofar(row, 601)
                                   for row in processed])
    expected = pygame.surfarray.array3d(
        sonar_view.waterfall_surface(reference_linear, 601, 120))
    actual = pygame.surfarray.array3d(
        sonar_view.waterfall_surface(processed_linear, 601, 120))

    np.testing.assert_array_equal(processed, reference)
    np.testing.assert_array_equal(actual, expected)
    assert "tobytes" not in inspect.getsource(sonar_view._waterfall)


def _chart():
    pygame.font.init()
    coast = Coastline({
        "landmasses": [{"name": "land", "points": [(0, 0), (200, 0), (0, 200)]}],
        "bathymetry": {"size": 2, "values": [[50., 300.], [700., 1000.]]},
    }, 500)
    return SimpleNamespace(
        screen=pygame.Surface((1280, 720)), tr=Translator("en").t,
        world=World(coast=coast), map_view=Viewport(500, .5, 14),
        font=pygame.font.Font(None, 16), radar_tracks=lambda: [],
        torpedoes=[], buoys=[], essms=[], selected_contact=None, target=None,
        hfdf_log=[], hfdf_fixes={}, sim_t=0.0,
        ship=SimpleNamespace(x=250, y=250, course=0, target_course=0, speed=0),
        helo=SimpleNamespace(airborne=False))


@pytest.mark.parametrize("scale", [.9, 3.99, 4., 14.])
@pytest.mark.parametrize("center", [0., 250., 500.])
def test_bathymetry_cache_matches_uncached_rectangles_and_pixels(scale, center, monkeypatch):
    game = _chart()
    view = game.map_view
    view.scale = scale
    view.cx = view.cy = center
    view.set_rect(config.MAP_RECT)
    r = config.MAP_RECT
    wl, wt = view.screen_to_world(r[0], r[1])
    wr, wb = view.screen_to_world(r[0] + r[2], r[1] + r[3])
    cell_nm = 10.0 if scale >= 4.0 else 25.0
    expected = []
    y_nm = max(0.0, math.floor(min(wt, wb) / cell_nm) * cell_nm)
    while y_nm < min(game.world.size_nm, max(wt, wb) + cell_nm):
        x_nm = max(0.0, math.floor(min(wl, wr) / cell_nm) * cell_nm)
        while x_nm < min(game.world.size_nm, max(wl, wr) + cell_nm):
            depth = game.world.depth_m(x_nm + cell_nm * .5, y_nm + cell_nm * .5)
            if depth > 0.0:
                deep = max(0.0, min(1.0, depth / 900.0))
                color = tuple(int(a + (b - a) * deep)
                              for a, b in zip(config.COLOR_SHALLOW, config.COLOR_DEEP))
                px, py = view.world_to_screen(x_nm, y_nm)
                px2, py2 = view.world_to_screen(x_nm + cell_nm, y_nm + cell_nm)
                expected.append((color, (int(px), int(py), max(1, int(px2 - px) + 1),
                                         max(1, int(py2 - py) + 1))))
            x_nm += cell_nm
        y_nm += cell_nm
    rectangles = []
    original = pygame.draw.rect

    def record(surface, color, rect, *args, **kwargs):
        rectangles.append((color, rect))
        return original(surface, color, rect, *args, **kwargs)

    monkeypatch.setattr(pygame.draw, "rect", record)
    snapshot = copy.deepcopy(game.world.coast.to_dict())
    rng = game.world.rng.getstate()
    world_fields = vars(game.world).copy()
    map_view.draw_map_view(game)
    assert rectangles[1:1 + len(expected)] == expected
    pixels = pygame.surfarray.array3d(game.screen)

    def unexpected_lookup(*args):
        pytest.fail("warm chart repeated a static depth lookup")

    monkeypatch.setattr(game.world, "depth_m", unexpected_lookup)
    rectangles.clear()
    map_view.draw_map_view(game)
    assert rectangles[1:1 + len(expected)] == expected
    np.testing.assert_array_equal(pygame.surfarray.array3d(game.screen), pixels)
    assert game.world.coast.to_dict() == snapshot
    assert game.world.rng.getstate() == rng
    assert {key: value for key, value in vars(game.world).items() if key != "depth_m"} == world_fields


def test_bathymetry_cache_invalidation_scales_and_bound(monkeypatch):
    game = _chart()
    world = game.world
    calls = []
    original = World.depth_m

    def depth(self, x, y):
        calls.append((self, x, y))
        return original(self, x, y)

    monkeypatch.setattr(World, "depth_m", depth)
    map_view.draw_map_view(game)
    coarse_count = len(calls)
    game.map_view.scale = 4.
    map_view.draw_map_view(game)
    assert len(calls) > coarse_count
    calls.clear()
    game.map_view.scale = 1.
    map_view.draw_map_view(game)
    assert not calls
    for change in ("grid", "snapshot", "world", "palette"):
        previous = map_view.draw_map_view._bathymetry_cache
        if change == "grid":
            world.coast._bathymetry["values"][0][0] += 100.
        elif change == "snapshot":
            world.coast = Coastline.from_dict(copy.deepcopy(world.coast.to_dict()))
        elif change == "world":
            game.world = world = World(coast=world.coast)
        else:
            monkeypatch.setattr(config, "COLOR_DEEP", (1, 2, 3))
        map_view.draw_map_view(game)
        assert calls
        assert map_view.draw_map_view._bathymetry_cache is not previous
        calls.clear()
    world.size_nm = world.coast.world_size_nm = 10000.
    for index in range(20):
        game.map_view.cx = 250. + index * 500.
        map_view.draw_map_view(game)
        assert len(map_view.draw_map_view._bathymetry_cache[3]) <= 4096
    assert len(calls) > 4096
    assert {cell[0] for cell in map_view.draw_map_view._bathymetry_cache[3]} == {25.0}
