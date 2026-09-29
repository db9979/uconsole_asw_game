"""Realism levels: Beginner, Standard, Realistic tune the computer opponent,
the operator assistance and the mission score, and stay with the mission."""

import copy
import json
from dataclasses import replace

import pygame
import pytest

from src.core import config, hunter
from src.core.game import Game
from src.core.preferences import load_preferences


def _game(level="standard", seed=6101, scenario="s1_patrouille"):
    game = Game(seed=seed, start_menu=False, audio_enabled=False)
    game.preferences = replace(game.preferences, level=level)
    game.reset(seed, scenario if scenario in config.SCENARIOS else None)
    return game


def test_apply_level_scales_only_the_opponent_and_clamps():
    base = dict(config.DEFAULT_DIFFICULTY)
    assert config.apply_level(base, "standard") == base
    easy = config.apply_level(base, "beginner")
    hard = config.apply_level(base, "realistic")
    assert easy["enemy_attack_mult"] < base["enemy_attack_mult"] < hard["enemy_attack_mult"]
    assert (easy["enemy_solution_threshold"] < base["enemy_solution_threshold"]
            < hard["enemy_solution_threshold"])
    # Everything the player owns (torpedoes, repairs, noise) is untouched.
    for name in ("quiet_mult", "torpedo_count", "repair_mult", "time_limit_s"):
        assert easy[name] == hard[name] == base[name]
    high = dict(base, enemy_attack_mult=2.0, enemy_solution_threshold=0.4)
    capped = config.apply_level(high, "realistic")
    assert capped["enemy_attack_mult"] == 2.0
    assert capped["enemy_solution_threshold"] == 0.4


@pytest.mark.parametrize("level", config.LEVELS)
def test_mission_takes_the_preferred_level_and_scales_its_subs(level):
    game = _game(level)
    assert game.level == level
    expected = config.apply_level(
        {**config.DEFAULT_DIFFICULTY,
         **(config.SCENARIOS[game.scenario_key]["difficulty"] or game.menu_difficulty)},
        level)
    assert game.difficulty == expected
    assert game.operator_assist() == (level == "beginner")
    # Changing the preference mid-mission keeps the mission's level.
    game.preferences = replace(game.preferences, level="realistic" if level != "realistic"
                               else "beginner")
    assert game.level == level


def test_standard_follows_the_assist_preference():
    game = _game("standard")
    assert not game.operator_assist()
    game.preferences = replace(game.preferences, operator_assist="training")
    assert game.operator_assist()
    game.level = "realistic"
    assert not game.operator_assist()


def test_score_factor_on_the_mission_end():
    scores = {}
    for level in config.LEVELS:
        game = _game(level)
        game.score = 1000
        game._end_mission(False, "test")
        scores[level] = game.score
    assert scores == {"beginner": 750, "standard": 1000, "realistic": 1250}


def test_level_survives_save_and_load_and_is_validated():
    game = _game("realistic")
    state = json.loads(json.dumps(game.save_state()))
    assert state["level"] == "realistic"
    twin = _game("beginner", seed=1)
    assert twin._load_save_data(copy.deepcopy(state))
    assert twin.level == "realistic"
    assert twin.difficulty == game.difficulty
    assert not twin.operator_assist()
    for bad in ("custom", "", 3, None):
        broken = copy.deepcopy(state)
        broken["level"] = bad
        assert not twin._load_save_data(broken)
    assert twin.level == "realistic"


def test_hunter_reaction_times_follow_the_level():
    game = _game("beginner")
    assert hunter._level_delay(game) == config.LEVEL_HUNTER_DELAY["beginner"] > 1.0
    game.level = "realistic"
    assert hunter._level_delay(game) < 1.0
    game.level = "standard"
    assert hunter._level_delay(game) == 1.0


def test_preferences_file_levels(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"level": "realistic"}), encoding="utf-8")
    assert load_preferences(path).level == "realistic"
    # Settings from before the levels: training assistance meant a beginner.
    path.write_text(json.dumps({"operator_assist": "training"}), encoding="utf-8")
    assert load_preferences(path).level == "beginner"
    path.write_text(json.dumps({"level": "godmode"}), encoding="utf-8")
    assert load_preferences(path).level == "standard"


def test_options_row_cycles_the_level_and_sets_the_assistance(monkeypatch):
    game = _game("standard")
    monkeypatch.setattr("src.core.game_draw.save_preferences", lambda prefs: None)
    game.options_open = True
    game.options_page = 0
    game.options_sel = game._OPTION_ROWS.index("level")
    game._handle_administration_key(pygame.K_RIGHT)
    assert game.preferences.level == "realistic"
    assert game.preferences.operator_assist == "off"
    game._handle_administration_key(pygame.K_RIGHT)
    assert game.preferences.level == "beginner"
    assert game.preferences.operator_assist == "training"
    # The running mission keeps its level; the row says so.
    assert game.level == "standard"
    game.in_menu = False
    simple = game.tr("option.level", level=game.tr("level.beginner"), factor=75)
    text = game._level_option_text()
    assert text == game.tr("option.level_next", level=game.tr("level.beginner"))
    game.level = "beginner"
    assert game._level_option_text() == simple
