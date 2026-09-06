"""Integrity, provenance, diversity, and playability of bundled sectors."""

from collections import deque
import json

from src.world.coastline import Coastline
from src.world.projection import lonlat_to_nm
from src.world.real_coast import SECTOR_COUNT, load_catalog


def test_catalog_has_exactly_128_distinct_real_sectors():
    catalog = load_catalog()
    sectors = catalog["sectors"]
    assert len(sectors) == SECTOR_COUNT == 128
    assert len({sector["id"] for sector in sectors}) == 128
    geometries = {json.dumps(sector["landmasses"], sort_keys=True)
                  for sector in sectors}
    assert len(geometries) == 128
    assert len({country for sector in sectors for country in sector["countries"]}) >= 50


def test_seed_mapping_is_stable_and_has_exactly_128_outcomes():
    ids = [Coastline.generate(seed).metadata["sector_id"] for seed in range(256)]
    assert len(set(ids)) == 128
    assert ids[:128] == ids[128:]


def test_provenance_and_airbase_coordinates_are_truthful():
    catalog = load_catalog()
    provenance = catalog["provenance"]
    assert provenance["natural_earth"]["license"] == "Public Domain"
    assert provenance["natural_earth"]["commit"] == "9380cca83db5f9aef52d5e762765100745f84b27"
    assert provenance["airbases"]["license"] == "CC0 1.0"
    assert provenance["airbases"]["retrieved"] == "2026-09-06"
    for sector in catalog["sectors"]:
        center = sector["center"]
        assert len(sector["airbases"]) >= 4
        assert len({base["wikidata"] for base in sector["airbases"]}) == len(
            sector["airbases"])
        for base in sector["airbases"]:
            x, y = lonlat_to_nm(base["longitude"], base["latitude"],
                                center["longitude"], center["latitude"])
            assert abs(x - base["x"]) < 0.002
            assert abs(y - base["y"]) < 0.002
            assert base["name"] and base["nation"]
            assert base["wikidata"].startswith("Q")


def test_every_sector_keeps_a_connected_central_operating_area():
    n = 21
    for seed in range(SECTOR_COUNT):
        coast = Coastline.generate(seed)
        water = {(column, row) for row in range(n) for column in range(n)
                 if not coast.on_land((column + .5) * 500 / n,
                                      (row + .5) * 500 / n)}
        center = (n // 2, n // 2)
        assert center in water
        reached, pending = {center}, deque([center])
        while pending:
            column, row = pending.popleft()
            for point in ((column - 1, row), (column + 1, row),
                          (column, row - 1), (column, row + 1)):
                if point in water and point not in reached:
                    reached.add(point)
                    pending.append(point)
        assert len(reached) >= len(water) * .94
