"""Structural render-performance regressions for the 1280x720 audit paths."""

import inspect
import math

import numpy as np
import pygame

from src.core import config
from src.ui import map_view, sonar_view, stations_view
from src.ui.viewport import Viewport
from src.world.coastline import Coastline


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
    legacy = np.asarray([
        [0.0 if not controls[1] <= frequency <= controls[2]
         else value * 0.15 if abs(frequency - shaft) < 5.0
         else min(1.0, value * gain)
         for value, frequency in zip(row, frequencies)]
        for row in rows
    ])
    processed = sonar_view._process_lofar_rows(rows, controls)
    legacy_linear = np.asarray([sonar_view._linear_lofar(row, 601)
                                for row in legacy])
    processed_linear = np.asarray([sonar_view._linear_lofar(row, 601)
                                   for row in processed])
    expected = pygame.surfarray.array3d(
        sonar_view.waterfall_surface(legacy_linear, 601, 120))
    actual = pygame.surfarray.array3d(
        sonar_view.waterfall_surface(processed_linear, 601, 120))

    np.testing.assert_array_equal(processed, legacy)
    np.testing.assert_array_equal(actual, expected)
    assert "tobytes" not in inspect.getsource(sonar_view._waterfall)
