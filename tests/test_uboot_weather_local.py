"""Key 0 opens the weather panel aboard the crewed boat on the uConsole."""

import sys
from pathlib import Path

import pygame

from src.core import uboot_local
from src.core.station import Station
from src.ui import layout, weather_station

sys.path.insert(0, str(Path(__file__).parent))
from test_uboot_scope import _key, _local_boat  # noqa: E402


def test_zero_opens_the_boats_weather_panel_and_closes_again(monkeypatch):
    game, boat = _local_boat()
    seen = []
    original = weather_station._boat
    monkeypatch.setattr(weather_station, "_boat",
                        lambda s, rect, data: (seen.append(data["boat"]),
                                               original(s, rect, data)))
    for station in ("uboot", "uboot_engine", "uboot_sonar"):
        uboot_local.set_local_station(game, station)
        _key(game, pygame.K_0)
        assert game.weather_station_open
        seen.clear()
        with layout.capture_geometry() as boxes:
            game.draw()
        # The boat's own block, never the frigate's flight weather.
        assert seen and seen[0]["snorkel_available"] is (boat.sub.endurance is not None)
        titles = {row["title"] for row in boxes}
        assert "weather.box.boat" in titles and "weather.box.flight" not in titles
        _key(game, pygame.K_0)
        assert not game.weather_station_open
    _key(game, pygame.K_0)
    _key(game, pygame.K_ESCAPE)
    assert not game.weather_station_open and not game.quit_confirm


def test_the_boat_panel_omits_the_flight_rows():
    game, boat = _local_boat()
    with game.sonar_perspective(boat.station):
        data = game.weather_station_data()
    assert "boat" in data and "flight" not in data
    assert "icing" not in data["atmosphere"]
    game.station = Station.BRIDGE
    assert "flight" in game.weather_station_data()
