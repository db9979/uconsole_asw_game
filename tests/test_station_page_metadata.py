import pytest

from src.core.commands import STATION_PAGES, station_page_step
from src.core.station import Station


SONAR_PAGES = (
    "BROADBAND",
    "LOFAR",
    "DEMON",
    "TMA",
    "UMWELT/FUSION",
    "ACTIVE",
)


def test_page_metadata_covers_every_canonical_station():
    assert set(STATION_PAGES) == set(Station)
    assert STATION_PAGES[Station.SONAR] == SONAR_PAGES

    for station in Station:
        pages = STATION_PAGES[station]
        assert isinstance(pages, tuple)
        assert pages
        assert all(isinstance(page, str) and page for page in pages)
        assert len(pages) == (6 if station is Station.SONAR else 1)
        if station is not Station.SONAR:
            assert pages == (station.name,)


@pytest.mark.parametrize(
    ("current", "delta", "expected"),
    [
        (0, 1, 1),
        (5, 1, 0),
        (0, -1, 5),
        (1, 13, 2),
        (1, -14, 5),
        ("4", "1", 5),
    ],
)
def test_station_page_step_wraps_in_both_directions(current, delta, expected):
    assert station_page_step(Station.SONAR, current, delta) == expected


@pytest.mark.parametrize("station", [station for station in Station
                                     if station is not Station.SONAR])
def test_single_page_stations_always_remain_on_their_only_page(station):
    assert station_page_step(station, 100, -37) == 0


def test_station_alias_uses_canonical_opz_metadata():
    assert Station.RADAR is Station.OPZ
    assert station_page_step(Station.RADAR, 2, 1) == 0


def test_station_page_step_rejects_unknown_stations():
    with pytest.raises(KeyError):
        station_page_step("SONAR", 0, 1)
