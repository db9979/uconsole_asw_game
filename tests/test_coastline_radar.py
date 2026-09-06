"""Radar-Kuestenreflexe: anonyme, kreisbeschnittene Segmente."""

import math

import pytest

from src.world.coastline import Coastline


def coast(points):
    return Coastline({"landmasses": [{"name": "GEHEIM", "nation": "X",
                                      "points": points}],
                      "airbases": [{"name": "BASIS", "x": 1, "y": 1}]})


def test_contour_segment_fully_inside_circle_is_unchanged():
    result = coast([(-2, 0), (2, 0)]).contour_segments_in_circle(0, 0, 5)
    assert result == [((-2.0, 0.0), (2.0, 0.0)),
                      ((2.0, 0.0), (-2.0, 0.0))]


def test_contour_crossing_circle_is_clipped_even_with_both_ends_outside():
    result = coast([(-10, 0), (10, 0)]).contour_segments_in_circle(0, 0, 5)
    assert result
    for first, second in result:
        assert math.hypot(*first) <= 5 + 1e-9
        assert math.hypot(*second) <= 5 + 1e-9
    assert any(first[0] == pytest.approx(-5) and second[0] == pytest.approx(5)
               for first, second in result)


def test_contour_outside_circle_is_omitted_and_metadata_not_returned():
    result = coast([(20, 20), (30, 20), (25, 30)]) \
        .contour_segments_in_circle(0, 0, 5)
    assert result == []


def test_duplicate_closing_point_does_not_create_zero_length_segment():
    result = coast([(-2, 0), (2, 0), (-2, 0)]) \
        .contour_segments_in_circle(0, 0, 5)
    assert result
    assert all(first != second for first, second in result)
