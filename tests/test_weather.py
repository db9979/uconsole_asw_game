"""Deterministic atmospheric weather and balanced gameplay effects."""

import math
import random

from src.core import config
from src.core.game import Game
from src.sonar.propagation import propagate
from src.world.world import World


def _set_weather(world, *, wind=10.0, direction=0.0, rain=0.0,
                  visibility=30.0, sea=None):
    if sea is not None:
        world.sea_state = sea
    values = dict(wind_from_deg=direction, wind_speed_kn=wind,
                  rain_intensity=rain, visibility_nm=visibility)
    world._weather_start = dict(values)
    world._weather_target = dict(values)
    world._weather_target_sea = world.sea_state if sea is None else sea
    world._weather_source_sea = world.sea_state
    world.weather_shift_timer = 0.0


def test_weather_is_seeded_finite_and_bounded():
    first, second = World(71), World(71)
    assert first.weather_values() == second.weather_values()
    values = first.weather_values()
    assert 0.0 <= values["wind_from_deg"] < 360.0
    assert 0.0 <= values["wind_speed_kn"] <= config.WEATHER_WIND_MAX_KN
    assert 0.0 <= values["rain_intensity"] <= 1.0
    assert config.WEATHER_VISIBILITY_MIN_NM <= values["visibility_nm"] \
        <= config.WEATHER_VISIBILITY_MAX_NM
    assert 0.0 <= values["sea_state"] <= 6.0
    assert all(math.isfinite(value) for value in values.values())


def test_weather_boundary_is_chunk_invariant_and_uses_one_existing_draw():
    whole, split = World(72), World(72)
    expected_rng = random.Random()
    expected_rng.setstate(whole.rng.getstate())
    expected_delta = expected_rng.choice([-1, 0, 0, 1])
    before_sea = whole.sea_state
    whole.update(config.WEATHER_SHIFT_PERIOD_S)
    for _ in range(60):
        split.update(config.WEATHER_SHIFT_PERIOD_S / 60.0)
    assert whole.rng.getstate() == split.rng.getstate() == expected_rng.getstate()
    assert whole.sea_state == max(0, min(6, before_sea + expected_delta))
    assert whole.weather_values() == split.weather_values()
    assert whole.weather_shift_timer == split.weather_shift_timer == 0.0


def test_wind_interpolation_uses_shortest_path_across_north():
    world = World(73)
    world._weather_start = dict(wind_from_deg=350.0, wind_speed_kn=10.0,
                                rain_intensity=0.0, visibility_nm=30.0)
    world._weather_target = dict(wind_from_deg=10.0, wind_speed_kn=10.0,
                                 rain_intensity=0.0, visibility_nm=30.0)
    world._weather_target_sea = world.sea_state
    world.weather_shift_timer = (config.WEATHER_SHIFT_PERIOD_S
                                 - config.WEATHER_TRANSITION_S / 2.0)
    assert world.wind_from_deg == 0.0


def test_sonar_propagation_accepts_transitioning_fractional_sea_state():
    result = propagate(0.0, 0.0, 10.0, 2.0, 0.0, 40.0, 100.0,
                       80.0, 300.0, sea_state=2.5)
    assert math.isfinite(result.reverberation_db)
    assert result.best_path is not None and math.isfinite(result.best_path.loss_db)


def test_rain_reduces_radar_and_visibility_caps_lookout(monkeypatch):
    game = Game(seed=74, start_menu=False, audio_enabled=False)
    try:
        _set_weather(game.world, rain=0.0, visibility=30.0)
        clear = game.radar_effective_range("air")
        _set_weather(game.world, rain=1.0, visibility=1.0)
        assert game.radar_effective_range("air") < clear

        observed = []
        monkeypatch.setattr(game.air_picture, "observe",
                            lambda *args, **kwargs: observed.append(kwargs))
        actor = type("Actor", (), dict(
            x=game.ship.x + 2.0, y=game.ship.y, id=1))()
        monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)
        game._lookout_observe(actor, "test", "SURFACE", 12.0, 1)
        assert observed == []
    finally:
        game.audio.shutdown()


def test_unsafe_weather_blocks_launch_but_never_return_order():
    game = Game(seed=75, start_menu=False, audio_enabled=False)
    try:
        _set_weather(game.world, wind=45.0, direction=90.0,
                     rain=0.8, visibility=0.5, sea=6)
        assert game.launch_helicopter() == "weather_unsafe"
        game.helo.launch(game.ship)
        assert game.return_helicopter() is True
    finally:
        game.audio.shutdown()
