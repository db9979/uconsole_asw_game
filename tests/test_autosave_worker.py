"""The periodic and the recovery autosave are checked and written by one
background worker: the main thread only builds and serializes the document.
At most one job waits (a newer one replaces it), a quit waits for the worker,
and a mission end, a new mission or a load is never overtaken by a late
write. Outcomes (faults, flashes) come back to the main thread."""

import json
import os
import threading

import pytest

from src.core import game_autosave
from src.core.game import Game
from src.core.game_autosave import autosave_path
from src.ui import layout


@pytest.fixture
def game():
    return Game(seed=11, start_menu=False, show_splash=False, audio_enabled=False)


class Gate:
    """Holds the worker inside its write until released; records payloads."""

    def __init__(self, monkeypatch):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.written = []
        real = game_autosave._write_atomically

        def gated(path, payload):
            self.entered.set()
            assert self.release.wait(10.0)
            real(path, payload)
            self.written.append(json.loads(payload)["sim_t"])

        monkeypatch.setattr(game_autosave, "_write_atomically", gated)

    def release_later(self, delay=0.2):
        timer = threading.Timer(delay, self.release.set)
        timer.start()
        return timer


def _queue(game, seconds=1.0):
    game._update_sim(seconds)
    assert game.autosave(background=True)
    return game.sim_t


def _saved_sim_t():
    with open(autosave_path(), encoding="utf-8") as stream:
        return json.load(stream)["sim_t"]


def test_a_newer_autosave_replaces_the_queued_one(game, monkeypatch):
    gate = Gate(monkeypatch)
    first = _queue(game)
    assert gate.entered.wait(10.0)          # the first job is being written
    _queue(game)                            # queued ...
    third = _queue(game)                    # ... and replaced by this one
    gate.release.set()
    game.wait_for_autosave()
    assert gate.written == [first, third]
    assert _saved_sim_t() == third and game.autosave_available


def test_quit_waits_for_the_worker(game, monkeypatch):
    gate = Gate(monkeypatch)
    _queue(game)
    assert gate.entered.wait(10.0)
    gate.release_later()
    game._update_sim(1.0)
    game.autosave_on_exit()
    assert game._autosave_worker.idle()
    assert _saved_sim_t() == game.sim_t and gate.written[-1] == game.sim_t


def test_mission_end_delete_is_not_resurrected_by_a_late_write(game, monkeypatch):
    assert game.autosave()                  # a good autosave exists
    gate = Gate(monkeypatch)
    _queue(game)
    assert gate.entered.wait(10.0)          # one write running, one queued
    _queue(game)
    game.game_over = True
    timer = gate.release_later()
    game.autosave_tick(0.1)                 # the mission end deletes it
    timer.join()
    game.wait_for_autosave()
    assert len(gate.written) == 1           # the queued job was dropped
    assert not os.path.exists(autosave_path()) and not game.autosave_available


def test_a_load_is_not_overtaken_by_a_late_write(game, monkeypatch):
    game.save_to_slot(3)
    gate = Gate(monkeypatch)
    running = _queue(game)
    assert gate.entered.wait(10.0)
    _queue(game)
    gate.release_later()
    assert game.load_from_slot(3)
    # Nothing of the replaced state is running, queued or written afterwards.
    assert game._autosave_worker.idle() and gate.written[0] == running
    written, saved = list(gate.written), _saved_sim_t()
    gate.entered.clear()
    game.wait_for_autosave()
    assert not gate.entered.wait(0.3)
    assert gate.written == written and _saved_sim_t() == saved


def test_a_failed_background_autosave_flashes_on_the_main_thread(game, monkeypatch):
    main = threading.get_ident()
    flashes = []
    monkeypatch.setattr(game, "flash",
                        lambda text, *a, **k: flashes.append((text, threading.get_ident())))
    built = game.save_state
    monkeypatch.setattr(game, "save_state",
                        lambda: {**built(), "not_a_save_field": 1})
    assert game.autosave(background=True)
    game._autosave_worker.wait()
    assert flashes == []                    # nothing from the worker itself
    game.autosave_tick(0.0)
    assert [thread for _text, thread in flashes] == [main]
    assert game._autosave_failed and not os.path.exists(autosave_path())


def test_the_worker_check_needs_no_pygame(game, monkeypatch):
    main = threading.get_ident()
    calls = []
    real = layout.font
    monkeypatch.setattr(layout, "font",
                        lambda *a, **k: calls.append(threading.get_ident()) or real(*a, **k))
    assert game.autosave(background=True)
    game.wait_for_autosave()
    assert os.path.exists(autosave_path())
    assert set(calls) <= {main}
