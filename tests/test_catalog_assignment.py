"""Operator catalog assignment of sonar contacts (save v13)."""

import copy
import json

import pygame

from src.core.game import Game
from src.core.station import Station
from src.sonar.sonar import Contact


def _game_with_contact():
    game = Game(seed=5151, start_menu=False, audio_enabled=False)
    contact = Contact(3, 4242, "passiv", "sub")
    contact.update_passive(100.0, .8, .8, "", game.sim_t)
    game.sonar.contacts[4242] = contact
    game.selected_contact = contact
    return game, contact


def test_assignment_is_an_operator_annotation_and_survives_save_load():
    game, contact = _game_with_contact()
    key = next(iter(game.runtime_catalog.profile_systems))
    assert game.assign_contact_profile(contact, "no_such_profile") == "invalid_value"
    assert game.assign_contact_profile(contact, key) is True
    assert contact.player_profile == key
    state = json.loads(json.dumps(game.save_state()))
    assert state["sonar"]["contacts"]["4242"]["player_profile"] == key
    restored = Game(seed=1, start_menu=False, audio_enabled=False)
    assert restored._load_save_data(copy.deepcopy(state))
    assert restored.sonar.contacts[4242].player_profile == key
    broken = copy.deepcopy(state)
    broken["sonar"]["contacts"]["4242"]["player_profile"] = "no_such_profile"
    assert not restored._load_save_data(broken)
    missing = copy.deepcopy(state)
    del missing["sonar"]["contacts"]["4242"]["player_profile"]
    assert not restored._load_save_data(missing)


def test_f8_analyser_assigns_the_browsed_profile_to_the_selected_contact():
    game, contact = _game_with_contact()
    game.station = Station.SONAR
    game._open_analyzer_in_game()
    analyzer = game.editor
    assert analyzer.assign_label
    expected = analyzer.selected_profile["key"]
    analyzer.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0))
    assert contact.player_profile == expected
    analyzer.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN,
                                             mod=pygame.KMOD_SHIFT))
    assert contact.player_profile is None
    analyzer.draw(game.screen)
