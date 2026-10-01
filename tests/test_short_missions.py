"""Short missions: the 45-minute variant of every fixed scenario (1.3.130)."""

import json
import math

import pygame
import pytest

from src.commander.v2.commands import _new_game_params
from src.core import boat_missions, config
from src.core.game import Game
from src.core.i18n import localize
from src.core.lobby import ROWS, LobbyRoom

# The random scenario and the open-ended free patrols have no short variant.
SHORT = [key for key in config.SCENARIO_ORDER
         if key not in ("s4_zufall", "frei_fregatte", "frei_uboot")]


def _game():
    return Game(seed=11, start_menu=False, audio_enabled=False, language="en")


def _start(key, length, seed=11):
    game = _game()
    game.start_length = length
    assert game.start_new_game(key, "fixed", seed=seed)
    return game


@pytest.mark.parametrize("key", SHORT)
def test_every_fixed_scenario_has_a_short_variant(key):
    game = _start(key, "short")
    spec = config.MISSION_TYPES[config.SCENARIOS[key]["mission_type"]]
    assert game.short_mission
    assert game.mission.time_limit_s == spec["short_time_limit_s"]
    assert 1800 <= spec["short_time_limit_s"] <= 3600
    assert "(short)" in localize(game.mission_name_display(), game.tr)
    normal = _start(key, "normal")
    assert not normal.short_mission
    assert normal.mission.time_limit_s == spec["time_limit_s"]
    for item in (game, normal):
        item.audio.shutdown()


def test_hostile_submarines_start_closer():
    short, normal = _start("s2_doppeljagd", "short"), _start("s2_doppeljagd", "normal")
    distances = [math.hypot(sub.x - short.ship.x, sub.y - short.ship.y) for sub in short.subs]
    (low, _), (_, high) = config.SHORT_SUB_SPAWN_NM
    assert all(low - 0.5 <= d <= high + 0.5 for d in distances)
    far = [math.hypot(sub.x - normal.ship.x, sub.y - normal.ship.y) for sub in normal.subs]
    assert max(distances) < min(far)
    for item in (short, normal):
        item.audio.shutdown()


def test_boat_mission_distances_shrink():
    short, normal = _start("s8_meerenge", "short"), _start("s8_meerenge", "normal")

    def to_goal(game):
        goal, sub = boat_missions.goal(game), boat_missions.target_sub(game)
        return math.hypot(goal["x"] - sub.x, goal["y"] - sub.y)

    assert boat_missions.distance_scale(short) == config.SHORT_DISTANCE_SCALE
    assert boat_missions.distance_scale(normal) == 1.0
    assert to_goal(short) < to_goal(normal) * 0.75
    for item in (short, normal):
        item.audio.shutdown()


def test_free_hunt_has_no_short_variant():
    game = _start("s4_zufall", "short")
    assert not game.short_mission
    assert game.mission.time_limit_s == float(game.menu_difficulty["time_limit_s"])
    game.scenario_key = "s4_zufall"
    assert game.start_choice_rows() == ("weather", "time")
    game.scenario_key = "s1_patrouille"
    assert game.start_choice_rows() == ("weather", "time", "length")
    game.audio.shutdown()


def test_a_saved_short_mission_stays_short(tmp_path):
    game = _start("s5_durchbruch", "short")
    for _ in range(20):
        game.update(0.1)
    goal = boat_missions.goal(game)
    document = json.loads(json.dumps(game.save_state()))
    loaded = _game()
    assert loaded.start_length == "normal"
    assert loaded._load_save_data(document)
    assert loaded.short_mission
    assert boat_missions.goal(loaded) == goal
    for item in (game, loaded):
        item.audio.shutdown()


def test_briefing_length_row():
    game = Game(seed=77, audio_enabled=False, language="en")
    game.in_menu, game.main_menu = True, False
    game.menu_screen, game.scenario_key, game.menu_sel = "briefing", "s1_patrouille", 0
    key = lambda code: game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=code, mod=0))
    key(pygame.K_UP)                      # wraps to the length row
    assert game.menu_sel == 2
    key(pygame.K_RIGHT)
    assert game.start_length == "short"
    key(pygame.K_RETURN)
    assert not game.in_menu and game.short_mission
    game.audio.shutdown()


def test_lobby_and_web_carry_the_length():
    room = LobbyRoom()
    room.row = ROWS.index("length")
    room.change(1)
    assert room.length == "short"
    base = {"scenario": "s1_patrouille", "world_mode": "fixed"}
    assert _new_game_params({**base, "length": "short"})
    assert not _new_game_params({**base, "length": "long"})
