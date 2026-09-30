"""Weather and time of day chosen for a scenario or campaign start (1.3.118)."""

import pygame

from src.core import config
from src.core.game import Game
from src.core.lobby import ROWS, LobbyRoom


def _game():
    return Game(seed=77, start_menu=False, audio_enabled=False, language="en")


def test_random_keeps_the_seeded_environment():
    first, second = _game(), _game()
    second.start_weather = second.start_time = "random"
    second.reset(77, "s1_patrouille")
    first.reset(77, "s1_patrouille")
    assert first.world.hour == second.world.hour
    assert first.world.sea_state == second.world.sea_state
    assert second.world.weather_override is None
    for game in (first, second):
        game.audio.shutdown()


def test_chosen_weather_and_time_hold_the_mission():
    game = _game()
    game.start_weather, game.start_time = "storm", "night"
    game.reset(77, "s2_doppeljagd")
    assert game.world.hour == config.START_TIME_HOURS["night"]
    assert game.world.is_night()
    assert game.world.weather_override == "storm"
    assert game.world.sea_state == config.START_WEATHER_SEA_STATE["storm"]
    # The sea drifts only inside the storm's band.
    for _ in range(40):
        game.world.update(config.WEATHER_SHIFT_PERIOD_S)
        assert 5 <= game.world.sea_state <= 6
    game.audio.shutdown()


def test_fair_weather_is_clear_and_calm():
    game = _game()
    game.start_weather = "fair"
    game.reset(77, "s3_abfang")
    values = game.world.weather_values()
    assert values["rain_intensity"] == 0.0
    assert values["visibility_nm"] == config.WEATHER_VISIBILITY_MAX_NM
    assert game.world.sea_state == 1
    game.audio.shutdown()


def test_briefing_rows_cycle_the_choices():
    game = Game(seed=77, audio_enabled=False, language="en")
    game.in_menu, game.main_menu = True, False
    game.menu_screen, game.scenario_key, game.menu_sel = "briefing", "s1_patrouille", 0
    key = lambda code: game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=code, mod=0))
    key(pygame.K_RIGHT)
    assert game.start_weather == "fair"
    key(pygame.K_DOWN)
    key(pygame.K_LEFT)
    assert game.start_time == "night"
    key(pygame.K_RETURN)
    assert not game.in_menu
    assert game.world.weather_override == "fair" and game.world.is_night()
    game.audio.shutdown()


def test_saved_mission_keeps_its_fair_weather(tmp_path):
    game = _game()
    game.start_weather = "fair"
    game.reset(77, "s1_patrouille")
    game.save_game(str(tmp_path / "slot.json"))
    loaded = _game()
    assert loaded.load_game(str(tmp_path / "slot.json"))
    assert loaded.world.weather_override == "fair"
    for item in (game, loaded):
        item.audio.shutdown()


def test_lobby_rows_carry_weather_and_time():
    room = LobbyRoom()
    room.row = ROWS.index("weather")
    room.change(1)
    room.row = ROWS.index("time")
    room.change(-1)
    assert (room.weather, room.time) == ("fair", "night")
