"""Guided training lessons and the campaign (its own file, never in a save)."""

import copy
import json
import os

import pygame
import pytest

from src.core import campaign as campaign_model, config, training
from src.core.campaign import CampaignState
from src.core.game import Game
from src.core.mission_definition import validate_mission
from src.core.station import Station
from src.sonar.sonar import Contact


def _menu_game(seed=11):
    return Game(seed=seed, start_menu=True, audio_enabled=False)


def _key(game, key, mod=0):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod, unicode=""))


@pytest.mark.parametrize("lesson", training.LESSONS)
def test_every_lesson_is_a_valid_mission_and_starts(lesson):
    definition = training.lesson_definition(lesson, 11)
    assert validate_mission(definition) == []
    game = _menu_game()
    assert game.start_training(lesson)
    assert game.training.lesson == lesson and game.training.step == 0
    boat = game.subs[0]
    hostile = lesson == "attack" or lesson in training.BOAT_LESSONS
    assert boat.side == ("hostile" if hostile else "neutral")
    assert game.local_side == training.side_of(lesson)
    assert (game.opfor is not None) is (lesson in training.BOAT_LESSONS)
    game.draw()


def test_sonar_lesson_steps_through_and_ends_as_won(monkeypatch):
    game = _menu_game()
    game.start_training("sonar")
    coach = game.training
    game._update_training()
    assert coach.step == 0
    game.station = Station.SONAR
    contact = Contact(1, game.subs[0].id, "passiv", "sub")
    monkeypatch.setattr(game.sonar, "active_contacts", lambda: [contact])
    game._update_training()
    assert coach.step == 2                           # station and contact passed
    game.sonar.focus_locked = True
    contact.player_class = "U_BOOT"
    game._update_training()
    assert coach.done and game.game_over and game.mission_result == "SIEG"


def test_a_loaded_lesson_gets_its_coach_back_and_r_restarts_it():
    game = _menu_game()
    game.start_training("tma")
    for _ in range(10):
        game.update(0.5)
    document = json.loads(json.dumps(game.save_state()))
    other = _menu_game()
    assert other._load_save_data(document)
    assert other.training is not None and other.training.lesson == "tma"
    other._end_mission(False, "test")
    _key(other, pygame.K_r)
    assert other.training.lesson == "tma" and not other.game_over


def test_training_menu_starts_the_chosen_lesson():
    game = _menu_game()
    _key(game, pygame.K_DOWN)
    _key(game, pygame.K_DOWN)
    _key(game, pygame.K_RETURN)
    assert game.menu_screen == "training"
    _key(game, pygame.K_3)
    game.draw()
    _key(game, pygame.K_RETURN)
    assert game.training.lesson == "attack" and not game.in_menu


def test_campaign_results_standing_and_port():
    state = CampaignState(1234)
    assert state.mission_seed() % 128 == 1234 % 128
    state.record(won=True, ship_sunk=False, score=900, torpedoes_left=3,
                 damaged=["engine", "nowhere"], helo_lost=True, incident=False,
                 tasks_done=1, tasks_failed=0)
    assert state.port and state.reputation == 50 + 15 + 3
    assert state.damaged == ["engine"] and state.torpedoes == 3
    assert not state.can_sail()
    quick = copy.deepcopy(state)
    assert quick.call_at_port("quick") and quick.leg == 1
    assert quick.damaged == ["engine"] and quick.helo_lost
    assert state.call_at_port("refit") and state.torpedoes == campaign_model.resupply(63)
    assert state.damaged == [] and not state.helo_lost
    assert CampaignState.restore(state.serialize()).serialize() == state.serialize()
    for key, value in (("leg", 9), ("reputation", 101), ("damaged", ["hull"]),
                       ("status", "draw"), ("history", [])):
        broken = dict(state.serialize(), **{key: value})
        assert not CampaignState.valid_state(broken)
    sunk = CampaignState(5)
    sunk.record(won=False, ship_sunk=True, score=0, torpedoes_left=0, damaged=[],
                helo_lost=False, incident=False, tasks_done=0, tasks_failed=0)
    assert sunk.status == "lost" and not sunk.port


def test_campaign_file_is_atomic_and_rejects_symlinks(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SAVE_DIR", str(tmp_path))
    assert campaign_model.load_campaign() is None
    state = CampaignState(77)
    assert campaign_model.save_campaign(state)
    assert campaign_model.load_campaign().serialize() == state.serialize()
    path = tmp_path / campaign_model.FILE_NAME
    path.write_text('{"version": NaN}')
    assert campaign_model.load_campaign() is None
    path.unlink()
    target = tmp_path / "elsewhere.json"
    target.write_text(json.dumps(state.serialize()))
    os.symlink(target, path)
    assert campaign_model.load_campaign() is None


def test_a_campaign_leg_carries_stock_damage_and_helicopter(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SAVE_DIR", str(tmp_path))
    game = _menu_game(seed=300)
    assert game.new_campaign()
    state = game.campaign
    state.torpedoes, state.damaged, state.helo_lost = 3, ["sonar"], True
    assert game.start_campaign_leg()
    assert game.torpedo_count == 3 and game.difficulty["torpedo_count"] == 3
    assert game.damage.compartments["sonar"].state == "BESCHAEDIGT"
    assert game.helo.state == "VERLOREN" and game.campaign_mission
    document = json.loads(json.dumps(game.save_state()))
    other = _menu_game()
    assert other._load_save_data(document)          # a plain v21 mission save
    assert not other.campaign_mission
    game._end_mission(True, "test")
    saved = campaign_model.load_campaign()
    assert saved.port and saved.history[0]["result"] == "won"
    game.draw()


def test_campaign_menu_new_port_and_sail(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SAVE_DIR", str(tmp_path))
    game = _menu_game(seed=400)
    game.main_menu_sel = game.main_menu_index("campaign")
    _key(game, pygame.K_RETURN)
    assert game.menu_screen == "campaign"
    game.draw()
    _key(game, pygame.K_n)
    assert game.campaign is not None
    _key(game, pygame.K_n)                           # asks before replacing
    assert game._campaign_confirm_new
    game.draw()
    _key(game, pygame.K_ESCAPE)
    game.main_menu_sel = game.main_menu_index("campaign")
    _key(game, pygame.K_RETURN)
    _key(game, pygame.K_RETURN)
    assert game.campaign_mission and game.scenario_key == campaign_model.LEGS[0]
    game._end_mission(False, "test")
    _key(game, pygame.K_m)
    game.main_menu_sel = game.main_menu_index("campaign")
    _key(game, pygame.K_RETURN)
    game.draw()
    _key(game, pygame.K_2)
    assert game.campaign.leg == 1 and not game.campaign.port
