"""Deterministic host-local Autocrew controls and persistence."""

from types import SimpleNamespace

import pygame

from src.core.autocrew import AutocrewController
from src.core.game import Game
from src.core.station import Station


class _Commander:
    def __init__(self):
        self.leased = set()

    def station_leased(self, station):
        return station.name.lower() in self.leased


class _Damage:
    def station_down(self, _key):
        return False


def _event(key):
    return pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, repeat=False)


def test_cadence_stays_anchored_when_update_crosses_deadline_late():
    crew = AutocrewController()
    crew.set_enabled("bridge", True, 0.0)
    game = SimpleNamespace(sim_t=.3, commander=_Commander(), damage=_Damage())
    crew.update(game)
    assert crew.next_due_s["bridge"] == 1.0
    game.sim_t = 2.4
    crew.update(game)
    assert crew.next_due_s["bridge"] == 3.0


def test_remote_lease_suspends_without_disabling_station():
    crew = AutocrewController()
    commander = _Commander()
    game = SimpleNamespace(sim_t=0.0, commander=commander, damage=_Damage())
    crew.set_enabled("sonar", True, 0.0)
    commander.leased.add("sonar")
    assert crew.status(game, "sonar") == "suspended_remote"
    assert crew.enabled["sonar"] is True


def test_state_validation_rejects_hostile_types():
    state = AutocrewController().serialize()
    state["version"] = True
    assert not AutocrewController.valid_state(state, 0.0)
    state = AutocrewController().serialize()
    state["stations"]["bridge"]["last_action"] = []
    assert not AutocrewController.valid_state(state, 0.0)


def test_f2_toggle_locks_station_controls_and_f3_owns_input():
    game = Game(seed=910, start_menu=False, audio_enabled=False)
    try:
        game.handle_event(_event(pygame.K_F2))
        assert game.autocrew.enabled["bridge"] is True
        assert game._local_station_input_locked()
        course = game.ship.target_course
        game.handle_event(_event(pygame.K_LEFT))
        assert not game.held and game.ship.target_course == course
        game.handle_event(_event(pygame.K_F3))
        assert game.autocrew_overview_open
        game.handle_event(_event(pygame.K_ESCAPE))
        assert not game.autocrew_overview_open
        game.handle_event(_event(pygame.K_F2))
        assert game.autocrew.enabled["bridge"] is False
    finally:
        game.audio.shutdown()


def test_save_roundtrip_preserves_autocrew_state():
    game = Game(seed=911, start_menu=False, audio_enabled=False)
    restored = Game(seed=912, start_menu=False, audio_enabled=False)
    try:
        game.autocrew.set_enabled(Station.ENGINE, True, game.sim_t)
        state = game.save_state()
        restored.load_state(state)
        assert restored.autocrew.serialize() == game.autocrew.serialize()
    finally:
        game.audio.shutdown()
        restored.audio.shutdown()
