"""The local sonar stream recovers by itself when its channel falls silent.

Dominik heard the uConsole's sonar go quiet a few times while every other
sound played on. Whatever stalls the reserved sonar channel (a queue slot
that never frees, a stuck channel volume, a pump error, a dead worker behind
a full queue, a stream cursor ahead of its receiver), the next blocks must be
audible again without switching audio off and on.
"""

import threading
from unittest.mock import Mock

import numpy as np
import pygame
import pytest

import src.audio.engine as audio_module
from src.audio.engine import AudioEngine
from src.core.game import Game
from src.core.station import Station

BLOCK = np.ones(1024, dtype=np.float32)
LEAD = round(AudioEngine.SONAR_BUFFER_S / .25)


@pytest.fixture
def mixer(monkeypatch):
    channels = [Mock(), Mock(), Mock(), Mock()]
    for channel in channels:
        channel.get_busy.return_value = False
        channel.get_queue.return_value = None
    backend = Mock()
    backend.get_init.return_value = (44100, -16, 2)
    backend.get_num_channels.return_value = 8
    backend.Channel.side_effect = channels.__getitem__
    monkeypatch.setattr(pygame, "mixer", backend)
    monkeypatch.setattr(pygame.sndarray, "make_sound", Mock(side_effect=lambda pcm: Mock()))
    return channels


@pytest.fixture
def clock(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(audio_module.time, "monotonic", lambda: now[0])
    return now


def primed_engine():
    engine = AudioEngine()
    engine._sonar_worker = Mock()
    for _ in range(LEAD + 2):
        assert engine.play_sonar(BLOCK, 4096, buffered=True)
    engine._pump_sonar_once()
    return engine


def test_a_queue_slot_that_never_frees_restarts_the_channel(mixer, clock):
    sonar = mixer[1]
    engine = primed_engine()
    sonar.play.assert_called_once()
    stuck = object()
    sonar.get_busy.return_value = True
    sonar.get_queue.return_value = stuck
    # A normal block holds the slot for about a quarter second: no action.
    for _ in range(int(.9 / .02)):
        clock[0] += .02
        engine._pump_sonar_once()
    assert engine.sonar_wedged == 0
    sonar.stop.assert_not_called()

    def halted():
        sonar.get_busy.return_value = False
        sonar.get_queue.return_value = None
    sonar.stop.side_effect = halted
    for _ in range(int(.2 / .02)):
        clock[0] += .02
        engine._pump_sonar_once()
        if engine.sonar_wedged:
            break
    assert engine.sonar_wedged == 1
    sonar.stop.assert_called()
    # The buffered stream carries on into the freed channel.
    assert sonar.play.call_count == 2
    assert sonar.play.call_args.args[0] is not stuck
    engine.shutdown()


def test_a_late_pump_is_not_mistaken_for_a_wedged_channel(mixer, clock):
    sonar = mixer[1]
    engine = primed_engine()
    sonar.get_busy.return_value = True
    sonar.get_queue.return_value = object()
    clock[0] += .02
    engine._pump_sonar_once()
    # The worker was starved for two seconds: the slot age is unknown.
    clock[0] += 2.0
    engine._pump_sonar_once()
    assert engine.sonar_wedged == 0
    sonar.stop.assert_not_called()
    engine.shutdown()


def test_a_stuck_channel_volume_is_restored_outside_a_fade(mixer, clock):
    sonar = mixer[1]
    gain = AudioEngine.CHANNEL_GAINS["sonar"]
    engine = primed_engine()
    sonar.set_volume.reset_mock()
    # Inside the fade-in the volume ramps: never touched.
    sonar.get_volume.return_value = 0.0
    clock[0] += .02
    engine._pump_sonar_once()
    sonar.set_volume.assert_not_called()
    # After the fade a channel left at zero plays inaudibly: restore it.
    clock[0] += AudioEngine.SONAR_VOLUME_SETTLE_S
    engine._pump_sonar_once()
    sonar.set_volume.assert_called_once_with(gain)
    assert engine.sonar_volume_restored == 1
    # The mixer's 1/128 steps round the gain: that is not a stuck volume.
    sonar.get_volume.return_value = round(gain * 128) / 128
    clock[0] += .02
    engine._pump_sonar_once()
    assert engine.sonar_volume_restored == 1
    engine.shutdown()


def test_the_pump_survives_an_error_and_restarts_the_stream(mixer):
    sonar = mixer[1]
    engine = primed_engine()
    exit_event, wake = threading.Event(), threading.Event()
    calls = []

    def broken():
        calls.append(1)
        exit_event.set()
        raise IndexError("broken block")
    engine._pump_sonar_once = broken
    wake.set()
    import weakref
    AudioEngine._pump_sonar(weakref.ref(engine), wake, exit_event)
    assert calls == [1]
    assert engine.sonar_pump_errors == 1
    sonar.stop.assert_called()
    assert not engine._sonar_buffered and not engine._sonar_buffer
    # The next blocks build a fresh stream.
    assert engine.play_sonar(BLOCK, 4096, buffered=True)
    engine.shutdown()


def test_a_dead_worker_is_restarted_even_when_the_queue_is_full(mixer):
    engine = AudioEngine()
    engine._sonar_worker = Mock()
    for _ in range(round(AudioEngine.SONAR_BUFFER_MAX_S / .25)):
        assert engine.play_sonar(BLOCK, 4096, buffered=True)
    dead = Mock()
    dead.is_alive.return_value = False
    engine._sonar_worker = dead
    assert not engine.play_sonar(BLOCK, 4096, buffered=True)
    assert engine._sonar_worker is not dead
    assert engine._sonar_worker.is_alive()
    assert engine.sonar_worker_restarts == 1
    engine.shutdown()


def test_a_queue_nobody_drains_restarts_the_stream(mixer, clock):
    engine = AudioEngine()
    engine._sonar_worker = Mock()
    for _ in range(round(AudioEngine.SONAR_BUFFER_MAX_S / .25)):
        assert engine.play_sonar(BLOCK, 4096, buffered=True)
    # Short overflows (a catch-up burst) only reject the block for a retry.
    assert not engine.play_sonar(BLOCK, 4096, buffered=True)
    clock[0] += AudioEngine.SONAR_FULL_WEDGE_S - .1
    assert not engine.play_sonar(BLOCK, 4096, buffered=True)
    assert engine.sonar_full_resets == 0
    clock[0] += .2
    assert not engine.play_sonar(BLOCK, 4096, buffered=True)
    assert engine.sonar_full_resets == 1
    assert engine._sonar_buffer_duration == 0
    # The retried block starts the new stream.
    assert engine.play_sonar(BLOCK, 4096, buffered=True)
    engine.shutdown()


def test_watchdog_counters_reach_the_audio_debug_log(mixer, monkeypatch, tmp_path):
    monkeypatch.setenv("U_JAGD_AUDIO_DEBUG", "1")
    monkeypatch.setattr(audio_module.config, "SAVE_DIR", str(tmp_path))
    engine = AudioEngine()
    engine.sonar_wedged, engine.sonar_volume_restored = 2, 3
    engine.sonar_pump_errors, engine.sonar_full_resets = 4, 5
    engine.debug_log(1.0)
    line = (tmp_path / "audio_debug.log").read_text()
    assert "wedged=2 volume_restored=3 pump_errors=4 full_resets=5" in line
    engine.shutdown()


def _listening_game():
    game = Game(seed=91, audio_enabled=False)
    game.station = Station.SONAR
    game.sonar_audio_enabled = True
    game.audio.play_sonar = Mock(return_value=True)
    return game


def test_a_stream_cursor_ahead_of_its_receiver_restarts_listening():
    game = _listening_game()
    receiver = game.sonar.receiver
    receiver.update([], 0, 12, .2, 2, 6)
    # A cursor from another receiver's numbering would wait for blocks that
    # never come: the sonar would stay silent for good.
    game._sonar_audio_sequence = receiver.sequence + 500
    game._update_audio(.25)
    game.audio.play_sonar.assert_called_once()
    assert game._sonar_audio_sequence == receiver.sequence
    game.audio.shutdown()


def test_boat_sonar_pans_against_the_boats_own_course():
    game = Game(seed=92, audio_enabled=False)
    game.local_side = "uboot"
    game._update(.05)
    boat = game._opfor
    assert boat is not None
    game.station = Station.SONAR
    boat.sub.course = (game.ship.course + 90.0) % 360.0
    game.audio.play_sonar = Mock(return_value=True)
    boat.station.sonar.receiver.update([], 0, 12, .2, 2, 6)
    with game.sonar_perspective(boat.station):
        game._update_audio(.25)
    kwargs = game.audio.play_sonar.call_args.kwargs
    assert kwargs["listener_bearing_deg"] == pytest.approx(boat.sub.course)
    game.audio.shutdown()
