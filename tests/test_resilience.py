"""Fault resilience: display errors are contained, simulation errors restore
the recovery snapshot, repeated or fatal errors keep the mission as autosave."""

import json
import os

import pygame
import pytest

from src.core import config, crashlog
from src.core import game_draw
from src.core.crashlog import last_launch_crashed
from src.core.game import Game
from src.core.game_autosave import CONTINUE_ENTRY, autosave_path
from src.core.game_save import _same_save_value
from src.core.station import Station


def _mission(seed=11):
    return Game(seed=seed, start_menu=False, show_splash=False, audio_enabled=False)


def _without_ids(document):
    document = dict(document)
    document.pop("next_entity_ids")
    return document


@pytest.fixture
def crash_root(tmp_path, monkeypatch):
    monkeypatch.setattr(crashlog, "_active_root", str(tmp_path))
    return tmp_path


def _log(root):
    path = os.path.join(root, crashlog.CRASH_LOG)
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as stream:
        return stream.read()


def test_snapshot_taken_at_start_refreshed_and_dropped_in_menu():
    game = _mission()
    assert game._recovery_snapshot is None
    game.recovery_tick(0.1)
    first = game._recovery_snapshot
    assert first is not None
    game.update(0.1)
    game.recovery_tick(config.RECOVERY_SNAPSHOT_INTERVAL_S - 1.0)
    assert game._recovery_snapshot is first
    game.recovery_tick(1.0)
    assert game._recovery_snapshot is not first
    game._return_to_main_menu()
    game.recovery_tick(0.1)
    assert game._recovery_snapshot is None


def test_new_world_is_snapshotted_at_once():
    game = _mission()
    game.recovery_tick(0.1)
    game.reset(game.seed + 1)
    game.recovery_tick(0.1)
    assert game._recovery_world is game.world
    assert game.recovery_document()["seed"] == game.seed


def test_autosave_refreshes_the_recovery_point():
    game = _mission()
    game.update(0.1)
    assert game.autosave()
    game.wait_for_autosave()
    with open(autosave_path(), encoding="utf-8") as stream:
        written = json.load(stream)
    assert _same_save_value(game.recovery_document(), written)


def test_simulation_fault_restores_the_snapshot(crash_root):
    game = _mission()
    for _ in range(20):
        game.update(0.1)
    game.recovery_tick(0.1)
    # save_state() shares lists with live state; the snapshot is detached.
    expected = game.recovery_document()
    for _ in range(30):
        game.update(0.1)
    try:
        raise RuntimeError("boom in update")
    except RuntimeError as exc:
        assert game.recover_from_fault(exc, "simulation")
    assert _same_save_value(_without_ids(game.save_state()), _without_ids(expected))
    assert "resilience.restored" in game.msg.values()
    assert "caught fault (simulation)" in _log(crash_root)
    assert "boom in update" in _log(crash_root)
    # A caught fault is not a crash of the launch.
    assert not last_launch_crashed(str(crash_root))
    # The restored mission runs on.
    game.update(0.1)


def test_run_survives_an_update_fault(crash_root, monkeypatch):
    game = _mission()
    monkeypatch.setattr(game, "compose_frame", lambda: None)
    original = game.update
    calls = {"n": 0}

    def update(dt, audio_dt=None):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("frame failure")
        original(dt, audio_dt=audio_dt)

    monkeypatch.setattr(game, "update", update)
    game.auto_quit = 6
    game.run()
    assert calls["n"] >= 5
    assert game._recovery_restores
    assert "frame failure" in _log(crash_root)


def test_repeated_faults_keep_the_mission_as_autosave(crash_root):
    game = _mission()
    game.update(0.1)
    game.recovery_tick(0.1)
    snapshot = game.recovery_document()
    for _ in range(config.RECOVERY_MAX_RESTORES):
        assert game.recover_from_fault(RuntimeError("again"), "simulation")
    assert not game.main_menu
    assert game.recover_from_fault(RuntimeError("again"), "simulation")
    assert game.main_menu and game.in_menu
    assert game.main_menu_entries()[game.main_menu_sel] == CONTINUE_ENTRY
    with open(autosave_path(), encoding="utf-8") as stream:
        written = json.load(stream)
    assert _same_save_value(written, snapshot)
    # The menu frame clears the block; the next mission autosaves again.
    game.recovery_tick(0.1)
    assert not game._autosave_blocked
    # Logged once per place, not per repeat.
    assert _log(crash_root).count("caught fault (simulation)") == 1


def test_menu_fault_still_raises():
    game = Game(seed=11, start_menu=True, show_splash=False, audio_enabled=False)
    assert not game.recover_from_fault(RuntimeError("menu"), "simulation")


def test_fatal_error_writes_the_recovery_point(monkeypatch):
    game = _mission()
    monkeypatch.setattr(game, "compose_frame", lambda: None)
    monkeypatch.setattr(game, "recover_from_fault", lambda exc, where: False)
    original = game.update
    calls = {"n": 0}

    def update(dt, audio_dt=None):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("fatal")
        original(dt, audio_dt=audio_dt)

    monkeypatch.setattr(game, "update", update)
    with pytest.raises(RuntimeError, match="fatal"):
        game.run()
    assert os.path.exists(autosave_path())
    resumed = Game(seed=5, start_menu=True, show_splash=False, audio_enabled=False)
    assert resumed.main_menu_entries()[resumed.main_menu_sel] == CONTINUE_ENTRY
    assert resumed.continue_from_autosave()


def test_broken_station_view_shows_a_notice(crash_root, monkeypatch):
    game = _mission()
    game.station = Station.SONAR

    def broken(current):
        raise ZeroDivisionError("sonar view")

    monkeypatch.setattr(game_draw, "draw_sonar_view", broken)
    game.draw()
    game.draw()
    assert game.view_faults == 2
    assert _log(crash_root).count("caught fault (draw sonar)") == 1
    # The top bar still draws and other stations are untouched.
    game.station = Station.BRIDGE
    game.draw()
    assert game.view_faults == 2


def test_broken_frame_never_ends_the_loop(crash_root, monkeypatch):
    game = _mission()
    monkeypatch.setattr(game, "compose_frame", lambda: None)

    def broken():
        raise KeyError("frame")

    monkeypatch.setattr(game, "draw", broken)
    game.auto_quit = 4
    game.run()
    assert game.view_faults >= 2
    assert "caught fault (draw frame)" in _log(crash_root)


def test_restore_survives_a_fault_inside_a_sonar_perspective():
    game = _mission()
    game.recovery_tick(0.1)
    other = game._frigate_sonar
    with pytest.raises(RuntimeError):
        with game.sonar_perspective(other):
            raise RuntimeError("inside")
    assert game.recover_from_fault(RuntimeError("inside"), "simulation")


def test_held_controls_clear_on_restore():
    game = _mission()
    game.recovery_tick(0.1)
    game.held.add(pygame.K_LEFT)
    assert game.recover_from_fault(RuntimeError("x"), "simulation")
    assert not game.held
