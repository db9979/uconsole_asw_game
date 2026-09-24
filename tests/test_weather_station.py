"""Weather & sonar analysis panel (key 0): input, drawing, physics, boundary."""

import copy
import json
import math

import pygame
import pytest

from src.core import config
from src.core.game import Game
from src.core.station import Station
from src.sonar import raytrace
from src.world import atmosphere
from src.world.ocean import (
    SALINITY_PSU, mackenzie_sound_speed, salinity_psu, sofar_axis_m,
    temperature_profile_c)


def key(game, code):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=code, mod=0, repeat=False))


@pytest.fixture
def game():
    current = Game(seed=4242, start_menu=False, audio_enabled=False, language="en")
    yield current
    current.audio.shutdown()


def test_zero_toggles_the_panel_and_owns_input(game):
    game.station = Station.BRIDGE
    key(game, pygame.K_0)
    assert game.weather_station_open is True
    # Station keys do not leak through the panel.
    key(game, pygame.K_2)
    assert game.station is Station.BRIDGE and game.weather_station_open
    key(game, pygame.K_0)
    assert game.weather_station_open is False
    key(game, pygame.K_KP0)
    assert game.weather_station_open
    key(game, pygame.K_ESCAPE)
    assert not game.weather_station_open


def test_panel_opens_while_paused_and_numeric_entry_keeps_the_zero(game):
    game.paused = True
    key(game, pygame.K_0)
    assert game.weather_station_open
    key(game, pygame.K_ESCAPE)
    game.paused = False
    game.input_mode = "course"
    game.input_buffer = ""
    key(game, pygame.K_0)
    assert not game.weather_station_open
    assert game.input_buffer.endswith("0")


def test_stations_are_drawn_when_no_overlay_is_open(game):
    """Regression: the overlay flag must be a real bool property; a stray
    decorator once turned it into a (truthy) method and blanked every
    station."""
    assert game._station_overlay_open is False
    game.station = Station.SONAR
    game.draw()
    area = game.screen.subsurface(pygame.Rect(config.FULL_STATION_RECT))
    lit = sum(1 for x in range(0, area.get_width(), 8)
              for y in range(0, area.get_height(), 8)
              if sum(area.get_at((x, y))[:3]) > 120)
    assert lit > 40


@pytest.mark.parametrize("language", ["en", "de"])
def test_panel_draws_before_and_after_a_bt_measurement(language):
    current = Game(seed=4242, start_menu=False, audio_enabled=False, language=language)
    try:
        key(current, pygame.K_0)
        current.draw()
        assert current.weather_station_data()["profile"] is None
        assert current.measure_sonar_bt() is True
        current.draw()
        assert current.weather_station_data()["profile"] is not None
    finally:
        current.audio.shutdown()


def test_ocean_profile_only_after_the_sonar_measured(game):
    data = game.weather_station_data()
    assert data["profile"] is None
    assert game.measure_sonar_bt() is True
    profile = game.weather_station_data()["profile"]
    bt = game.sonar.bt_profile
    # The panel shows the measurement (with its noise), not the truth.
    assert profile["thermocline_m"] == bt["thermocline_m"]
    assert profile["speeds_m_s"] == bt["speeds_m_s"]
    assert len(profile["rays"]) <= 9 and all(len(ray) <= 64 for ray in profile["rays"])
    assert profile["stale"] is False and profile["age_s"] == 0.0
    game.sim_t += game.WEATHER_PROFILE_STALE_S + 1.0
    assert game.weather_station_data()["profile"]["stale"] is True
    game.sim_t -= game.WEATHER_PROFILE_STALE_S + 1.0
    game.ship.x += game.WEATHER_PROFILE_STALE_NM + 1.0
    assert game.weather_station_data()["profile"]["stale"] is True


def test_dto_is_json_safe_and_save_load_keeps_it(game):
    game.measure_sonar_bt()
    before = game.weather_station_data()
    json.dumps(before, allow_nan=False)
    restored = Game(seed=1, start_menu=False, audio_enabled=False, language="en")
    try:
        assert restored._load_save_data(copy.deepcopy(
            json.loads(json.dumps(game.save_state()))))
        after = restored.weather_station_data()
        assert after["atmosphere"] == before["atmosphere"]
        assert after["profile"]["depths_m"] == before["profile"]["depths_m"]
        assert after["profile"]["shadow"] == before["profile"]["shadow"]
    finally:
        restored.audio.shutdown()


def test_barometer_leads_the_weather_and_warns_before_storms():
    seed = 7
    start, _ = atmosphere.barometer(seed, 3, 5, 0.0)
    middle, tendency = atmosphere.barometer(seed, 3, 5, config.WEATHER_SHIFT_PERIOD_S / 2)
    end, _ = atmosphere.barometer(seed, 3, 5, config.WEATHER_SHIFT_PERIOD_S)
    assert start > middle > end
    assert atmosphere.pressure_trend(tendency) == "falling_rapidly"
    assert atmosphere.storm_warning(end, "falling_rapidly")
    steady, flat = atmosphere.barometer(seed, 2, 2, 1800.0)
    assert atmosphere.pressure_trend(flat) == "steady"
    assert not atmosphere.storm_warning(steady, "steady")
    rising, up = atmosphere.barometer(seed, 5, 4, 1800.0)
    assert atmosphere.pressure_trend(up) == "rising"


def test_air_temperature_snow_and_icing_physics():
    winter_storm = atmosphere.air_temperature_c(8.0, 15, 4.0, 0.0, 40.0, 1.0)
    summer_day = atmosphere.air_temperature_c(18.0, 200, 14.0, 180.0, 5.0, 0.2)
    assert winter_storm < 0.0 < summer_day
    assert atmosphere.precipitation(0.5, winter_storm) == "snow"
    assert atmosphere.precipitation(0.5, summer_day) == "rain"
    assert atmosphere.precipitation(0.05, winter_storm) == "none"
    assert atmosphere.icing(summer_day, "rain", 40.0) == "none"
    assert atmosphere.icing(-1.0, "none", 10.0) == "none"
    assert atmosphere.icing(-1.0, "snow", 10.0) == "light"
    assert atmosphere.icing(-5.0, "snow", 30.0) == "severe"
    assert atmosphere.beaufort(0.5) == 0 and atmosphere.beaufort(15.0) == 4
    assert atmosphere.beaufort(70.0) == 12
    assert atmosphere.gust_kn(20.0, 6) > atmosphere.gust_kn(20.0, 0) > 20.0


def test_twilight_from_sun_elevation_and_moon_phases():
    noon = atmosphere.sun_elevation_deg(55.0, 172, 12.0)
    midnight = atmosphere.sun_elevation_deg(55.0, 355, 0.0)
    assert atmosphere.daylight(noon) == "day" and noon > 50.0
    assert atmosphere.daylight(midnight) == "night"
    assert atmosphere.daylight(-3.0) == "civil_twilight"
    assert atmosphere.daylight(-9.0) == "nautical_twilight"
    assert atmosphere.moon_phase(0.0) == "new"
    assert atmosphere.moon_phase(atmosphere.SYNODIC_MONTH_D / 2) == "full"
    assert atmosphere.moon_phase(atmosphere.SYNODIC_MONTH_D * .25) == "first_quarter"


def test_rain_lens_lowers_surface_sound_speed_and_wind_mixes_it():
    assert salinity_psu(0.0) == SALINITY_PSU
    fresh = salinity_psu(0.0, rain_intensity=1.0, wind_kn=0.0)
    mixed = salinity_psu(0.0, rain_intensity=1.0, wind_kn=30.0)
    assert fresh < mixed < SALINITY_PSU
    assert salinity_psu(50.0, 1.0, 0.0) == pytest.approx(SALINITY_PSU, abs=1e-3)
    assert (mackenzie_sound_speed(12.0, fresh, 0.0)
            < mackenzie_sound_speed(12.0, SALINITY_PSU, 0.0))


def test_sofar_channel_only_in_deep_water():
    def profile(water_depth):
        depths = [i * min(water_depth, 1500.0) / 20 for i in range(21)]
        return depths, [mackenzie_sound_speed(temperature_profile_c(z, 60.0, 13.0),
                                              35.0, z) for z in depths]
    deep = sofar_axis_m(*profile(1600.0), 1600.0)
    assert deep is not None and 300.0 < deep < 800.0
    assert sofar_axis_m(*profile(250.0), 250.0) is None


def test_ray_picture_is_bounded_pure_and_shadows_only_below_the_layer():
    depths = [i * 1500.0 / 20 for i in range(21)]
    speeds = [mackenzie_sound_speed(temperature_profile_c(z, 60.0, 13.0), 35.0, z)
              for z in depths]
    first = raytrace.ray_picture(depths, speeds, 1600.0, 5.0, "sand", 10.0, 60.0)
    second = raytrace.ray_picture(depths, speeds, 1600.0, 5.0, "sand", 10.0, 60.0)
    assert first is second or first == second
    assert len(first["rays"]) == len(raytrace.PICTURE_RAYS_DEG)
    assert all(len(ray) <= raytrace.PICTURE_POINTS for ray in first["rays"])
    edges = first["depth_edges_m"]
    shaded = [(column, row) for column, cells in enumerate(first["shadow"])
              for row, cell in enumerate(cells) if cell]
    assert shaded, "deep water with a surface layer has a shadow zone"
    assert all(column > 0 and edges[row] >= 60.0 for column, row in shaded)
    assert len(raytrace._picture_cache) <= raytrace.PICTURE_CACHE_SIZE


def test_flight_weather_status_and_icing_limits(game, monkeypatch):
    weather = game.helicopter_weather()
    assert weather["status"] in ("clear", "limited", "no_go")
    base = game.atmosphere()
    monkeypatch.setattr(game, "atmosphere", lambda: dict(base, icing="severe"))
    blocked = game.helicopter_weather()
    assert blocked["status"] == "no_go" and not blocked["launch_safe"]
    assert not blocked["dipping_safe"]
    monkeypatch.setattr(game, "atmosphere", lambda: dict(base, icing="light"))
    light = game.helicopter_weather()
    assert light["status"] in ("limited", "no_go") and not light["dipping_safe"]
