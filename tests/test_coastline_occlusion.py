"""Deterministic terrain occlusion without sensor-system integration."""

from time import perf_counter

import pytest

from src.world.coastline import Coastline
from src.world.world import World


def test_land_blocks_crossing_but_not_open_water_or_tangent():
    coast = Coastline({"landmasses": [{
        "name": "island", "nation": "X",
        "points": [(40, 40), (60, 40), (60, 60), (40, 60)],
    }]}, world_size_nm=100)

    assert coast.land_blocks_line(10, 50, 90, 50)
    assert not coast.land_blocks_line(10, 20, 90, 20)
    assert not coast.land_blocks_line(10, 40, 90, 40)


def test_land_query_handles_polygon_and_playable_sector_boundaries():
    coast = Coastline({"landmasses": [{
        "name": "boundary island", "nation": "X",
        "points": [(49, 20), (51, 20), (51, 80), (49, 80)],
    }]}, world_size_nm=100)

    assert coast.land_blocks_line(10, 50, 90, 50)
    assert not coast.land_blocks_line(0, 10, 100, 10)
    assert coast.land_blocks_line(-0.001, 10, 90, 10)


def test_sonar_uses_bathymetry_and_depth_without_inventing_surface_blockage():
    coast = Coastline({
        "landmasses": [],
        "bathymetry": {"size": 3, "values": [
            [500, 500, 500],
            [500, 60, 500],
            [500, 500, 500],
        ]},
    }, world_size_nm=100)

    assert not coast.sonar_path_blocked(10, 50, 20, 90, 50, 20)
    assert coast.sonar_path_blocked(10, 50, 100, 90, 50, 100)
    assert coast.sonar_path_blocked(10, 50, 55, 90, 50, 55, clearance_m=5)


def test_sonar_without_bathymetry_still_obeys_exact_land_geometry():
    coast = Coastline({"landmasses": [{
        "name": "island", "nation": "X",
        "points": [(40, 40), (60, 40), (60, 60), (40, 60)],
    }]}, world_size_nm=100)

    assert coast.sonar_path_blocked(10, 50, 20, 90, 50, 20)
    assert not coast.sonar_path_blocked(10, 20, 200, 90, 20, 200)


def test_queries_are_symmetric_deterministic_and_cache_is_bounded():
    coast = Coastline({"landmasses": []}, world_size_nm=100)
    assert coast.land_blocks_line(1, 2, 98, 97) == \
        coast.land_blocks_line(98, 97, 1, 2)
    assert coast.occlusion_cache_entries == 1

    for index in range(1100):
        coast.land_blocks_line(index / 20_000, 1, 99, 99)
    assert coast.occlusion_cache_entries == 1024
    coast.clear_occlusion_cache()
    assert coast.occlusion_cache_entries == 0


def test_world_exposes_occlusion_without_sensor_integration():
    coast = Coastline({"landmasses": []}, world_size_nm=100)
    world = World(seed=1, size_nm=100, coast=coast)

    assert not world.land_blocks_line(10, 10, 90, 90)
    assert not world.sonar_path_blocked(10, 10, 20, 90, 90, 20)


@pytest.mark.parametrize("method,args", [
    ("land_blocks_line", (0, 0, float("nan"), 1)),
    ("sonar_path_blocked", (0, 0, -1, 1, 1, 10)),
])
def test_invalid_queries_are_rejected(method, args):
    with pytest.raises(ValueError):
        getattr(Coastline({}), method)(*args)


def test_generated_sector_query_budget_is_practical():
    coast = Coastline.generate(53)  # Catalog sector with dense geometry.
    queries = [(1.25, (index * 37) % 499 + .25,
                498.75, (index * 83) % 499 + .25)
               for index in range(500)]

    started = perf_counter()
    first = [coast.land_blocks_line(*query) for query in queries]
    elapsed = perf_counter() - started
    assert first == [coast.land_blocks_line(*query) for query in queries]
    # A deliberately loose guard catches accidental unbounded algorithms while
    # remaining portable to the lower-power uConsole target.
    assert elapsed < 2.0
