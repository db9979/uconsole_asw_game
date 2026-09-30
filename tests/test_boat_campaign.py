"""The boat campaign: boat missions linked with carried torpedoes, hull and standing."""

import copy
from dataclasses import replace
import json
import os

import pygame

from src.core import boat_campaign, config
from src.core.boat_campaign import BoatCampaignState
from src.core.game import Game
from src.ui import layout


def _menu_game(seed=11, language="en"):
    return Game(seed=seed, start_menu=True, audio_enabled=False, language=language)


def _key(game, key):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode=""))


def test_legs_are_boat_missions_in_one_sea_area():
    assert all(config.SCENARIOS[key].get("boat") for key in boat_campaign.LEGS)
    state = BoatCampaignState(1234)
    seeds = []
    for leg in range(len(boat_campaign.LEGS)):
        state.leg = leg
        seeds.append(state.mission_seed())
    assert {seed % 128 for seed in seeds} == {1234 % 128} and len(set(seeds)) == len(seeds)


def test_results_standing_and_the_base():
    state = BoatCampaignState(1234)
    assert state.torpedoes is None and state.damage == 0
    state.record(won=True, boat_sunk=False, torpedoes_left=3, damage=82.4)
    assert state.port and state.reputation == 65
    assert state.torpedoes == 3 and state.damage == boat_campaign.DAMAGE_CARRY_MAX
    quick = copy.deepcopy(state)
    assert quick.call_at_port("quick") and quick.leg == 1
    assert quick.torpedoes == 3 + boat_campaign.resupply(65) // 2
    assert quick.damage == boat_campaign.DAMAGE_CARRY_MAX and quick.reputation == 68
    assert state.call_at_port("refit")
    assert state.torpedoes is None and state.damage == 0 and state.reputation == 60
    assert BoatCampaignState.restore(state.serialize()).serialize() == state.serialize()
    for key, value in (("leg", 9), ("reputation", 101), ("damage", 61), ("torpedoes", -1),
                       ("torpedoes", 2.0), ("status", "draw"), ("history", [])):
        assert not BoatCampaignState.valid_state(dict(state.serialize(), **{key: value}))
    sunk = BoatCampaignState(5)
    sunk.record(won=False, boat_sunk=True, torpedoes_left=0, damage=100.0)
    assert sunk.status == "lost" and not sunk.port and sunk.history[0]["result"] == "sunk"
    last = BoatCampaignState(5)
    last.leg = len(boat_campaign.LEGS) - 1
    last.history = [dict(leg=n, result="won") for n in range(last.leg)]
    last.record(won=True, boat_sunk=False, torpedoes_left=1, damage=0.0)
    assert last.status == "won"


def test_the_file_is_atomic_and_rejects_symlinks(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SAVE_DIR", str(tmp_path))
    assert boat_campaign.load_campaign() is None
    state = BoatCampaignState(77)
    assert boat_campaign.save_campaign(state)
    assert boat_campaign.load_campaign().serialize() == state.serialize()
    path = tmp_path / boat_campaign.FILE_NAME
    target = tmp_path / "elsewhere.json"
    os.replace(path, target)
    os.symlink(target, path)
    assert boat_campaign.load_campaign() is None


def test_a_leg_puts_the_carried_state_aboard_and_records_the_result(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SAVE_DIR", str(tmp_path))
    game = _menu_game(seed=300)
    assert game.new_boat_campaign()
    state = game.boat_campaign
    state.torpedoes, state.damage = 3, 25
    assert game.start_boat_campaign_leg()
    assert game.local_side == "uboot" and game.scenario_key == boat_campaign.LEGS[0]
    sub = game.opfor.sub
    assert sub.torpedoes_left == 3 and sub.weapon_battery.remaining_total == 3
    assert sub.damage == 25.0 and game.campaign_mission
    game._update(0.05)
    assert game.opfor.sub is sub
    # A slot saved on a leg loads as a plain mission.
    other = _menu_game()
    assert other._load_save_data(json.loads(json.dumps(game.save_state())))
    assert not other.campaign_mission
    game._end_mission(False, {"__u_jagd_i18n__": "end.reason.boat_reported"})
    saved = boat_campaign.load_campaign()
    assert saved.port and saved.history[0]["result"] == "won"
    assert saved.torpedoes == 3 and saved.damage == 25
    # The frigate's campaign is untouched.
    assert game._campaign() is None
    for language in ("en", "de"):
        game.preferences = replace(game.preferences, language=language)
        layout.configure_for(game)
        game.draw()


def test_a_sunk_boat_ends_the_boat_campaign(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SAVE_DIR", str(tmp_path))
    game = _menu_game(seed=301)
    assert game.new_boat_campaign() and game.start_boat_campaign_leg()
    game.opfor.sub.sunk = True
    game._check_mission_end()
    assert game.mission_result == "SIEG"
    assert boat_campaign.load_campaign().status == "lost"


def test_the_campaign_screen_switches_to_the_boat(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SAVE_DIR", str(tmp_path))
    game = _menu_game(seed=400)
    game.main_menu_sel = game.main_menu_index("campaign")
    _key(game, pygame.K_RETURN)
    assert game.menu_screen == "campaign" and game.campaign_side == "frigate"
    _key(game, pygame.K_TAB)
    assert game.campaign_side == "boat"
    game.draw()
    _key(game, pygame.K_n)
    assert game.boat_campaign is not None and game._campaign() is None
    game.draw()
    _key(game, pygame.K_RETURN)
    assert game.campaign_mission and game.local_side == "uboot"
    assert game.scenario_key == boat_campaign.LEGS[0]
    game._end_mission(True, "test")                  # the frigate held out
    assert game.boat_campaign.port and game.boat_campaign.history[0]["result"] == "lost"
    game.draw()
    _key(game, pygame.K_m)
    game.main_menu_sel = game.main_menu_index("campaign")
    _key(game, pygame.K_RETURN)
    assert game.campaign_side == "boat"
    game.draw()
    _key(game, pygame.K_1)
    assert game.boat_campaign.leg == 1 and game.boat_campaign.torpedoes is None
    assert boat_campaign.load_campaign().leg == 1
