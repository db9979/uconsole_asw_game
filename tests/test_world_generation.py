"""Deterministic real-sector coastlines and bathymetry."""

from collections import deque
import json

import pytest

from src.world.coastline import Coastline
from src.world.world import World


def _snapshot(coast):
    return (
        [[tuple(point) for point in land.points] for land in coast.landmasses],
        coast.airbases,
        [[round(coast.depth_m(x, y), 8) for x in (175, 250, 325)]
         for y in (175, 250, 325)],
    )


def _signed_area(points):
    return sum(points[index][0] * points[(index + 1) % len(points)][1]
               - points[(index + 1) % len(points)][0] * points[index][1]
               for index in range(len(points))) / 2.0


def test_generation_is_exactly_deterministic_and_seed_varied():
    first = Coastline.generate(731)
    again = Coastline.generate(731)
    different = Coastline.generate(732)

    assert _snapshot(first) == _snapshot(again)
    assert _snapshot(first) != _snapshot(different)
    assert first.metadata["sector_id"] != different.metadata["sector_id"]


def test_generated_geometry_airbases_and_radar_are_usable():
    coast = Coastline.generate(19)

    assert all(len(land.points) >= 3 and abs(_signed_area(land.points)) > 0.1
               for land in coast.landmasses)
    assert coast.contour_segments_in_circle(250.0, 250.0, 250.0)
    assert len(coast.friendly_bases()) >= 2
    assert coast.hostile_base()["gameplay_role"] == "hostile"
    assert coast.neutral_base()["gameplay_role"] == "neutral"
    for base in coast.airbases:
        assert coast.landmass_at(base["x"], base["y"]) is not None
        assert base["wikidata"].startswith("Q")


def test_land_ratio_and_central_ocean_connectivity_across_seeds():
    grid_size = 31
    for seed in range(12):
        coast = Coastline.generate(seed)
        water = set()
        land_count = 0
        for row in range(grid_size):
            for column in range(grid_size):
                x = (column + 0.5) * 500.0 / grid_size
                y = (row + 0.5) * 500.0 / grid_size
                if coast.on_land(x, y):
                    land_count += 1
                else:
                    water.add((column, row))
        ratio = land_count / (grid_size * grid_size)
        assert 0.07 <= ratio <= 0.47

        center = (grid_size // 2, grid_size // 2)
        reached = {center}
        pending = deque([center])
        while pending:
            column, row = pending.popleft()
            for neighbor in ((column - 1, row), (column + 1, row),
                             (column, row - 1), (column, row + 1)):
                if neighbor in water and neighbor not in reached:
                    reached.add(neighbor)
                    pending.append(neighbor)
        # Narrow real straits and enclosed seas vary with sampling resolution;
        # the central ocean must still dominate the playable water area.
        assert len(reached) >= len(water) * 0.85


def test_bathymetry_is_seeded_and_deepens_away_from_coast():
    coast = Coastline.generate(44)
    assert coast.depth_m(250.0, 250.0) > 350.0
    assert coast.depth_m(250.0, 250.0) != Coastline.generate(45).depth_m(250.0, 250.0)
    land_point = next((x, y) for y in range(0, 501, 10)
                      for x in range(0, 501, 10) if coast.on_land(x, y))
    assert coast.depth_m(*land_point) == 0.0

    world = World(seed=44)
    assert world.depth_m(250.0, 250.0) == coast.depth_m(250.0, 250.0)


def test_legacy_load_remains_fixed(tmp_path):
    path = tmp_path / "coast.json"
    path.write_text(json.dumps({
        "world_nm": 90,
        "landmasses": [{"name": "legacy", "nation": "ZIVIL",
                        "points": [[0, 0], [20, 0], [0, 20]]}],
        "airbases": [],
    }))
    coast = Coastline.load(str(path))

    assert coast.world_size_nm == 90
    assert coast.on_land(2, 2)
    with pytest.raises(ValueError, match="no bathymetry"):
        coast.depth_m(50, 50)


def test_generated_snapshot_round_trip_is_generator_independent():
    original = Coastline.generate(83)
    restored = Coastline.from_dict(original.to_dict())

    assert restored.to_dict() == original.to_dict()
    assert restored.metadata["sector_id"] == "real-083"


@pytest.mark.parametrize("size", [0, -10, float("inf")])
def test_invalid_world_size_is_rejected(size):
    with pytest.raises(ValueError):
        Coastline.generate(1, size_nm=size)
