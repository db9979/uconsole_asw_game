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

TWO_PAGE_STATIONS = {
    Station.BRIDGE: ("BRIDGE_NAV", "BRIDGE_MISSION"),
    Station.WEAPONS: ("WEAPONS_TARGET", "WEAPONS_AMMO"),
    Station.DAMAGE: ("DAMAGE_PLAN", "DAMAGE_DETAIL"),
    Station.OPZ: ("OPZ_PICTURE", "OPZ_TARGET"),
    Station.RADIO: ("RADIO_HFDF", "RADIO_MESSAGES"),
    Station.ENGINE: ("ENGINE_TELEGRAPH", "ENGINE_SYSTEMS"),
    Station.HELICOPTER: ("HELO_STATUS", "HELO_MISSION"),
    Station.ELOKA: ("ELOKA_INTERCEPTS", "ELOKA_EVIDENCE"),
}


def test_page_metadata_covers_every_canonical_station():
    assert set(STATION_PAGES) == set(Station)
    assert STATION_PAGES[Station.SONAR] == SONAR_PAGES
    for station, pages in TWO_PAGE_STATIONS.items():
        assert STATION_PAGES[station] == pages

    for station in Station:
        pages = STATION_PAGES[station]
        assert isinstance(pages, tuple)
        assert pages
        assert all(isinstance(page, str) and page for page in pages)
        assert len(pages) == (6 if station is Station.SONAR else 2)


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


@pytest.mark.parametrize("station", list(TWO_PAGE_STATIONS))
def test_two_page_stations_wrap_within_two_pages(station):
    assert station_page_step(station, 0, 1) == 1
    assert station_page_step(station, 1, 1) == 0
    assert station_page_step(station, 5, 1) == 0
    assert station_page_step(station, 2, -1) == 1
    assert station_page_step(station, 0, -1) == 1


def test_station_alias_uses_canonical_opz_metadata():
    assert Station.RADAR is Station.OPZ
    assert STATION_PAGES[Station.RADAR] == STATION_PAGES[Station.OPZ]
    assert station_page_step(Station.RADAR, 1, 1) == 0


def test_station_page_step_rejects_unknown_stations():
    with pytest.raises(KeyError):
        station_page_step("SONAR", 0, 1)
