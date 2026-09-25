"""HQ start report: coarse position only, or the deployed hostile unit types."""

import re

import pygame

from src.core import config
from src.core.game import Game
from src.core.i18n import localize


def press(game, key):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key))


def intel_reports(game):
    return [text for _, text in game.messages
            if isinstance(text, dict) and str(text.get("__u_jagd_i18n__", "")
                                              ).startswith("runtime.hq.intel")]


def test_patrol_names_the_deployed_submarine_and_other_scenarios_stay_coarse():
    game = Game(seed=4711, start_menu=False, audio_enabled=False, language="en")
    assert game.scenario_key == "s1_patrouille" and game.hq_intel_mode() == "exact"
    [report] = intel_reports(game)
    text = localize(report, game.tr)
    sub = game.subs[0]
    assert text.startswith("HQ: Intelligence confirms")
    assert f"1x {sub.stype.profile.name}" in text
    for scenario in ("s2_doppeljagd", "s3_abfang"):
        game.scenario_key = scenario
        game.reset(4711)
        assert game.hq_intel_mode() == "coarse" and not intel_reports(game)


def test_free_hunt_menu_row_selects_exact_intel_with_counts_and_air_waves():
    game = Game(seed=99, start_menu=True, audio_enabled=False, language="de")
    game.main_menu = False
    press(game, pygame.K_4)
    press(game, pygame.K_RETURN)
    assert game.menu_screen == "difficulty"
    game.menu_difficulty.update(sub_count=2, warship_count=0, air_raid_count=3)
    press(game, pygame.K_UP)                  # wraps to the HQ intel row
    assert game.menu_sel == len(config.DIFFICULTY_FIELD_ORDER)
    press(game, pygame.K_RIGHT)
    assert game.menu_hq_intel == "exact"
    game.draw()
    press(game, pygame.K_RETURN)
    assert not game.in_menu and game.scenario_key == "s4_zufall"
    [report] = intel_reports(game)
    text = localize(report, game.tr)
    assert "3x Luftangriffswelle" in text
    units = re.findall(r"(\d+)x ([^,.]+)", text)
    assert sum(int(count) for count, name in units
               if "Luftangriff" not in name) == len(game.subs) + len(game.warships)


def test_exact_report_survives_save_and_load():
    game = Game(seed=4711, start_menu=False, audio_enabled=False, language="en")
    before = localize(intel_reports(game)[0], game.tr)
    game.save_to_slot(2)
    game.scenario_key = "s2_doppeljagd"
    game.reset(5)
    assert game.load_from_slot(2)
    assert localize(intel_reports(game)[0], game.tr) == before
