"""The coast edge index answers exactly what the full edge scan answered."""

import math
import random

import pytest

from src.world import coastline as coast_mod
from src.world.coastline import Coastline


def _brute_contains(land, x, y):
    left, top, right, bottom = land.bounds
    if x < left or x > right or y < top or y > bottom:
        return False
    return coast_mod._point_in_poly(x, y, land.points)


def _brute_distance(coast, x, y):
    nearest = coast.world_size_nm
    for land in coast.landmasses:
        for index, first in enumerate(land.points):
            second = land.points[(index + 1) % len(land.points)]
            nearest = min(nearest, coast_mod._distance_to_segment(x, y, first, second))
    return nearest


def _brute_cuts(land, first, second):
    cuts = []
    for index, edge_first in enumerate(land.points):
        edge_second = land.points[(index + 1) % len(land.points)]
        cuts.extend(coast_mod._segment_intersection_parameters(
            first, second, edge_first, edge_second))
    return sorted(cuts)


@pytest.mark.parametrize("seed", [0, 8, 40, 64, 88, 112])
def test_index_queries_match_the_full_scan(seed):
    coast = Coastline.generate(seed)
    rng = random.Random(seed)
    for _ in range(400):
        x, y = rng.uniform(0, 500), rng.uniform(0, 500)
        for land in coast.landmasses:
            assert land.contains(x, y) == _brute_contains(land, x, y)
    # Points right on coast vertices and edge midpoints.
    for land in coast.landmasses[:8]:
        for index in range(0, len(land.points), max(1, len(land.points) // 40)):
            a, b = land.edge(index)
            for x, y in (a, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)):
                assert land.contains(x, y) == _brute_contains(land, x, y)
    for _ in range(60):
        x, y = rng.uniform(0, 500), rng.uniform(0, 500)
        assert coast._distance_to_coast(x, y) == _brute_distance(coast, x, y)
    for _ in range(150):
        first = (rng.uniform(0, 500), rng.uniform(0, 500))
        length = rng.choice((0.5, 5.0, 60.0, 400.0))
        angle = rng.uniform(0, math.tau)
        second = (first[0] + length * math.cos(angle), first[1] + length * math.sin(angle))
        for land in coast.landmasses:
            found = []
            for index in land.index.segment_edges(first, second):
                found.extend(coast_mod._segment_intersection_parameters(
                    first, second, *land.edge(index)))
            assert sorted(found) == _brute_cuts(land, first, second)
