"""Deterministic host-local Autocrew controls and persistence."""

from types import SimpleNamespace

import pygame
import pytest

from src.core import config
from src.core.autocrew import AutocrewController
from src.core.game import Game
from src.core.station import Station
from src.sonar.sonar import Contact


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
    # Helicopter stays a deliberate no-op, so this needs no station stubs
    # beyond what every AutocrewController.update() call already requires.
    crew = AutocrewController()
    crew.set_enabled("helicopter", True, 0.0)
    game = SimpleNamespace(sim_t=.3, commander=_Commander(), damage=_Damage())
    crew.update(game)
    assert crew.next_due_s["helicopter"] == 1.0
    game.sim_t = 2.4
    crew.update(game)
    assert crew.next_due_s["helicopter"] == 3.0


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


def test_new_action_vocabulary_round_trips_through_valid_state():
    for action in ("evading", "correcting", "engaged"):
        state = AutocrewController().serialize()
        state["stations"]["bridge"]["last_action"] = action
        assert AutocrewController.valid_state(state, 0.0)
        restored = AutocrewController.restore(state)
        assert restored.last_action["bridge"] == action


def test_bridge_evades_inbound_asm_threat(monkeypatch):
    game = Game(seed=930, start_menu=False, audio_enabled=False)
    try:
        monkeypatch.setattr(game, "asm_tracks", lambda: [
            SimpleNamespace(range_nm=5.0, track_id="M-1", bearing=90.0)])
        game.ship.target_course = 0.0
        game.ship.target_speed = 10.0

        action = AutocrewController._bridge(game)

        assert action == "evading"
        assert game.ship.target_course == pytest.approx(270.0)
        assert game.ship.target_speed == pytest.approx(config.SHIP_SPEED_MAX_KN)
    finally:
        game.audio.shutdown()


def test_bridge_evades_when_asm_and_torpedo_both_have_unknown_range(monkeypatch):
    # Both threats resolve to the same "unknown range" tie-break key; the
    # nearest-threat scan must not crash comparing a str ASM track id
    # against an int torpedo contact id when breaking that tie.
    game = Game(seed=934, start_menu=False, audio_enabled=False)
    try:
        monkeypatch.setattr(game, "asm_tracks", lambda: [
            SimpleNamespace(range_nm=None, track_id="M-1", bearing=90.0)])
        contact = Contact(1, 9103, "passiv", "torpedo")
        contact.bearing = 180.0
        contact.last_seen = game.sim_t
        game.sonar.contacts[9103] = contact
        game.ship.target_course = 0.0
        game.ship.target_speed = 10.0

        action = AutocrewController._bridge(game)

        assert action == "evading"
    finally:
        game.audio.shutdown()


def test_bridge_does_not_evade_a_threat_straight_into_a_grounding(monkeypatch):
    game = Game(seed=935, start_menu=False, audio_enabled=False)
    try:
        monkeypatch.setattr(game, "asm_tracks", lambda: [
            SimpleNamespace(range_nm=5.0, track_id="M-1", bearing=90.0)])
        game.ship.target_course = 0.0
        game.ship.target_speed = 10.0
        # Ideal evade course (270) and the first deflection (300) both run
        # the ship aground; 240 is the nearest clear water.
        monkeypatch.setattr(game.world, "hull_is_safe",
                            lambda x, y, course, hull: course not in (270.0, 300.0))

        action = AutocrewController._bridge(game)

        assert action == "evading"
        assert game.ship.target_course == pytest.approx(240.0)
        assert game.ship.target_speed == pytest.approx(config.SHIP_SPEED_MAX_KN)
    finally:
        game.audio.shutdown()


def test_bridge_steers_around_a_projected_grounding_when_no_threat(monkeypatch):
    game = Game(seed=931, start_menu=False, audio_enabled=False)
    try:
        monkeypatch.setattr(game, "asm_tracks", lambda: [])
        game.ship.target_course = 0.0
        game.ship.speed = 10.0
        # Only dead-ahead (0 deg) is unsafe; every deflection is clear water.
        monkeypatch.setattr(game.world, "hull_is_safe",
                            lambda x, y, course, hull: course != 0.0)

        action = AutocrewController._bridge(game)

        assert action == "correcting"
        assert game.ship.target_course == pytest.approx(30.0)
    finally:
        game.audio.shutdown()


def test_weapons_engages_hostile_classified_contact(monkeypatch):
    game = Game(seed=932, start_menu=False, audio_enabled=False)
    try:
        monkeypatch.setattr(game.world, "sonar_path_blocked", lambda *a: False)
        game.roe = "FREE"
        contact = Contact(1, 9101, "passiv", "sub")
        contact.player_class = "U_BOOT"
        contact.bearing = 45.0
        contact.last_seen = game.sim_t
        game.sonar.contacts[9101] = contact
        game.opz_affiliations["S-9101"] = "HOSTILE"

        action = AutocrewController._weapons(game)

        assert action == "engaged"
        assert len(game.torpedoes) == 1
    finally:
        game.audio.shutdown()


def test_weapons_does_not_engage_an_unclassified_affiliation(monkeypatch):
    game = Game(seed=933, start_menu=False, audio_enabled=False)
    try:
        monkeypatch.setattr(game.world, "sonar_path_blocked", lambda *a: False)
        game.roe = "FREE"
        contact = Contact(1, 9102, "passiv", "sub")
        contact.player_class = "U_BOOT"
        contact.bearing = 45.0
        contact.last_seen = game.sim_t
        game.sonar.contacts[9102] = contact
        # No affiliation annotated -> resolves to UNKNOWN, must not be engaged.

        action = AutocrewController._weapons(game)

        assert action == "monitoring"
        assert game.torpedoes == []
    finally:
        game.audio.shutdown()
