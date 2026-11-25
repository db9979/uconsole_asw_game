"""Real water depths (ETOPO1) and the monthly surface layer (World Ocean
Atlas 2023) of the real coastline sectors (``src/world/real_ocean.py``)."""

from __future__ import annotations

import pytest

from src.world import real_ocean
from src.world.coastline import SHOAL_MAX_DEPTH_M, Coastline
from src.world.real_coast import load_catalog
from src.world.world import World

pytestmark = pytest.mark.real_sea


def test_every_sector_has_real_depths_and_a_surface_layer():
    data = real_ocean.load()
    assert data is not None
    ids = [sector["id"] for sector in load_catalog()["sectors"]]
    assert set(data["sectors"]) == set(ids)
    for entry in data["sectors"].values():
        assert len(entry["sst_c"]) == 12 and len(entry["mld_m"]) == 12


def test_the_chart_uses_real_depths_with_land_dry_and_water_wet():
    coast = Coastline.generate(0)
    grid = coast.to_dict()["bathymetry"]
    assert grid["size"] == real_ocean.load()["grid"]
    spacing = coast.world_size_nm / (grid["size"] - 1)
    deepest = 0.0
    for row, line in enumerate(grid["values"]):
        for column, depth in enumerate(line):
            if coast.on_land(column * spacing, row * spacing):
                assert depth == 0.0
            else:
                assert depth >= min(real_ocean.MIN_WATER_DEPTH_M, 5.0)
            deepest = max(deepest, depth)
    # Sector 0 reaches the Bay of Biscay abyssal plain.
    assert deepest > 3000.0


def test_synthetic_shoals_sit_on_the_shelf_only():
    for seed in range(0, 128, 9):
        fresh = Coastline.generate(seed).to_dict()["bathymetry"]["values"]
        real = real_ocean.bathymetry(
            Coastline.generate(seed).metadata["sector_id"],
            Coastline.generate(seed).on_land, 500.0)["values"]
        for fresh_row, real_row in zip(fresh, real):
            for shoal, chart in zip(fresh_row, real_row):
                if shoal < 10.0 < chart:  # a shoal's core
                    assert chart <= SHOAL_MAX_DEPTH_M


def test_monthly_values_interpolate_cyclically():
    months = [float(index) for index in range(12)]
    assert real_ocean.monthly(months, 16) == pytest.approx(0.0)
    assert real_ocean.monthly(months, 45) == pytest.approx(1.0)
    assert real_ocean.monthly(months, 350) == pytest.approx(11.0)
    # Between mid-December and mid-January it runs back to January.
    assert 0.0 < real_ocean.monthly(months, 1) < 11.0
    assert real_ocean.monthly(months, 365) == pytest.approx(
        real_ocean.monthly(months, 365.0))


def test_the_sea_follows_the_sectors_season():
    world = World(seed=0, coast=Coastline.generate(0))
    climate = world.ocean.climate
    assert climate is not None
    world.ocean.day_of_year = 16
    winter = world.ocean.sea_surface_temperature_c(15.0) \
        - 0.5  # the afternoon peak of the diurnal swing
    assert winter == pytest.approx(climate["sst_c"][0])
    world.ocean.day_of_year = 228
    assert world.ocean.sea_surface_temperature_c(15.0) - 0.5 \
        == pytest.approx(climate["sst_c"][7])
    # Summer stratifies: the mixed layer is shallower than in winter.
    summer_layer = world.thermocline_depth_m(250.0, 250.0)
    world.ocean.day_of_year = 46
    assert world.thermocline_depth_m(250.0, 250.0) > summer_layer


def test_a_map_without_a_real_sector_keeps_the_synthetic_sea(monkeypatch):
    monkeypatch.setattr(real_ocean, "sector", lambda _sector_id: None)
    coast = Coastline.generate(3)
    assert coast.to_dict()["bathymetry"]["size"] == 17
    world = World(seed=3, coast=coast)
    assert world.ocean.climate is None
    assert world.ocean.seasonal_mixed_layer_m() is None


def test_a_damaged_file_falls_back(tmp_path):
    path = tmp_path / "broken.json.gz"
    path.write_bytes(b"not gzip")
    assert real_ocean.load(str(path)) is None


def test_a_measuring_process_can_hold_the_synthetic_sea(monkeypatch):
    monkeypatch.setattr(real_ocean, "_reference_depth", 0)
    assert real_ocean.sector("real-000") is not None
    real_ocean.hold_reference_sea()
    assert real_ocean.sector("real-000") is None


def test_a_submarine_never_spawns_under_a_shallow_real_seabed():
    from src.core.game import Game

    for seed in (1235, 1242):   # real shelf seas, 40-55 m deep at the spawn
        game = Game(seed=seed, start_menu=False, audio_enabled=False)
        for sub in game.subs:
            assert sub.depth <= game.world.depth_m(sub.x, sub.y)
            assert sub.depth == sub.target_depth == sub.order_depth
