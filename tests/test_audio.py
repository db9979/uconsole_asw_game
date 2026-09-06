"""Audio- und Signalanalyse ohne echtes Audiogeraet."""

from unittest.mock import Mock

import numpy as np
import pygame
import pytest

import src.audio.engine as audio_module
from src.audio.database import TARGET_DATABASE, rank_signatures
from src.audio.demon import DemonAnalyzer
from src.audio.engine import AudioEngine
from src.audio.synthesis import (filtered_noise_event, fm_chirp,
                                 propeller_block, stereo_bearing, tone)


def test_synthesis_is_bounded_and_vectorized():
    signal = propeller_block(180.0, 5, 8000, cavitation=0.8)
    assert signal.dtype == np.float32
    assert signal.size == 2000
    assert float(np.max(np.abs(signal))) <= 1.0


def test_propeller_phase_continuity_and_event_primitives_are_finite():
    rate = 8000
    first = propeller_block(183, 5, rate, cavitation=0, phase=.4)
    blade_hz = 183 / 60 * 5
    phase = .4 + 2 * np.pi * blade_hz * first.size / rate
    second = propeller_block(183, 5, rate, cavitation=0, phase=phase)
    whole = propeller_block(183, 5, rate, duration_s=.5,
                            cavitation=0, phase=.4)
    np.testing.assert_allclose(np.concatenate((first, second)), whole, atol=2e-7)
    for event in (fm_chirp(300, 1100, .2, rate, modulation_hz=17,
                           modulation_depth_hz=12),
                  filtered_noise_event(.2, rate, 180, 900, seed=8)):
        assert event.dtype == np.float32
        assert np.isfinite(event).all()
        assert np.max(np.abs(event)) <= 1
        assert event[0] == event[-1] == 0


def test_stereo_bearing_has_expected_channel_bias():
    mono = np.ones(32, dtype=np.float32)
    center = stereo_bearing(mono, 0)
    right = stereo_bearing(mono, 90)
    np.testing.assert_allclose(center[:, 0], center[:, 1])
    assert right.shape == (32, 2)
    assert np.max(np.abs(right[:, 0])) < 1e-6
    assert np.all(right[:, 1] == 1)


def test_demon_recovers_modulation_frequency():
    sample_rate = 8000
    t = np.arange(4096, dtype=np.float32) / sample_rate
    signal = (1.0 + 0.7 * np.sin(2.0 * np.pi * 10.0 * t)) \
        * np.sin(2.0 * np.pi * 200.0 * t)
    result = DemonAnalyzer(sample_rate=sample_rate).analyze(signal)
    assert result.blade_rate_hz is not None
    assert abs(result.blade_rate_hz - 10.0) < 1.0
    assert result.confidence > 0.0


def test_target_database_returns_ranked_candidates():
    ranked = rank_signatures(10.0, 120.0, 25.0, 0.2)
    assert ranked
    assert ranked[0][1] >= ranked[-1][1]


def test_target_database_contains_100_platform_profiles():
    platform_keys = {entry.key for entry in TARGET_DATABASE
                     if entry.category != "BIOLOGISCH"}
    assert len(platform_keys) >= 100
    assert any(entry.category == "TANKER" for entry in TARGET_DATABASE)
    assert any(entry.category == "PASSAGIER" for entry in TARGET_DATABASE)
    assert any(entry.category == "U_BOOT" for entry in TARGET_DATABASE)


def test_audio_engine_is_safe_when_disabled(monkeypatch):
    synthesize = Mock(side_effect=AssertionError("disabled audio synthesized"))
    monkeypatch.setattr(audio_module, "tone", synthesize)
    monkeypatch.setattr(audio_module, "propeller_block", synthesize)
    monkeypatch.setattr(pygame.mixer, "get_init", synthesize)
    engine = AudioEngine(enabled=False)
    assert engine.available is False
    assert engine.play_ping() is False
    assert engine.play_alert("damage") is False
    assert engine.update_engine(180.0) is False
    assert engine.play_sonar(np.ones(100, dtype=np.float32), 4096) is False
    engine.stop_sonar()
    engine.shutdown()
    synthesize.assert_not_called()


def test_tone_has_fade_in_and_out():
    signal = tone(500.0, 0.2, 8000)
    assert abs(float(signal[0])) < 1e-6
    assert abs(float(signal[-1])) < 0.01


@pytest.fixture
def mixer(monkeypatch):
    channels = [Mock(), Mock()]
    for channel in channels:
        channel.get_busy.return_value = False
        channel.get_queue.return_value = None
    backend = Mock()
    backend.get_init.return_value = (44100, -16, 2)
    backend.get_num_channels.return_value = 8
    backend.Channel.side_effect = channels.__getitem__
    monkeypatch.setattr(pygame, "mixer", backend)
    make_sound = Mock(side_effect=lambda pcm: Mock())
    monkeypatch.setattr(pygame.sndarray, "make_sound", make_sound)
    return backend, channels, make_sound


@pytest.mark.parametrize("channels", [1, 2])
def test_uses_actual_mixer_rate_and_shape(mixer, channels):
    backend, _, make_sound = mixer
    backend.get_init.return_value = (44100, -16, channels)
    engine = AudioEngine(sample_rate=22050, channels=2)
    assert engine.sample_rate == 44100
    assert engine.channels == channels
    backend.init.assert_not_called()
    assert engine.play_ping()
    pcm = make_sound.call_args.args[0]
    count = int(0.45 * 44100)
    assert pcm.shape == ((count,) if channels == 1 else (count, 2))
    assert pcm.dtype == np.int16
    assert pcm.flags.c_contiguous
    mono = pcm if channels == 1 else pcm[:, 0]
    peak = np.argmax(np.abs(np.fft.rfft(mono))) * 44100 / count
    assert 700.0 <= peak <= 980.0
    assert engine.update_engine(180.0)
    assert make_sound.call_args.args[0].shape[0] == int(0.25 * 44100)


def test_initializes_signed16_and_reserves_independent_channels(mixer):
    backend, channels, _ = mixer
    backend.get_init.side_effect = [None, (22050, -16, 2)]
    backend.get_num_channels.return_value = 1
    engine = AudioEngine()
    backend.init.assert_called_once_with(frequency=22050, size=-16,
                                         channels=2, buffer=512, allowedchanges=0)
    backend.set_num_channels.assert_called_once_with(3)
    backend.set_reserved.assert_called_once_with(2)
    assert engine._engine_channel is channels[0]
    assert engine._sonar_channel is channels[1]


@pytest.mark.parametrize("mixer_format", [
    (44100, 8, 2), (44100, -32, 2), (44100, -16, 4),
])
def test_incompatible_shared_mixer_is_safe(mixer, mixer_format):
    backend, _, make_sound = mixer
    backend.get_init.return_value = mixer_format
    engine = AudioEngine()
    assert not engine.available
    assert not engine.play_ping()
    assert not engine.play_sonar(np.ones(100, dtype=np.float32), 4096)
    backend.quit.assert_not_called()
    backend.init.assert_not_called()
    make_sound.assert_not_called()


@pytest.mark.parametrize("enabled,available", [(False, True), (True, False)])
def test_inactive_engine_does_not_synthesize(mixer, monkeypatch, enabled, available):
    engine = AudioEngine()
    engine.enabled = enabled
    engine.available = available
    synthesize = Mock(side_effect=AssertionError("inactive audio synthesized"))
    monkeypatch.setattr(audio_module, "tone", synthesize)
    monkeypatch.setattr(audio_module, "propeller_block", synthesize)
    assert not engine.play_ping()
    assert not engine.play_alert()
    assert not engine.update_engine(180.0)
    assert not engine.play_sonar(np.ones(100, dtype=np.float32), 4096)
    synthesize.assert_not_called()
    mixer[2].assert_not_called()


@pytest.mark.parametrize("channels", [1, 2])
def test_sonar_resampling_preserves_pitch_duration_and_fades(mixer, channels):
    backend, playback, make_sound = mixer
    backend.get_init.return_value = (44100, -16, channels)
    engine = AudioEngine()
    t = np.arange(4096, dtype=np.float32) / 4096
    samples = np.cos(2 * np.pi * 256 * t).astype(np.float32)
    original = samples.copy()
    assert engine.play_sonar(samples, 4096)
    pcm = make_sound.call_args.args[0]
    assert pcm.shape == ((44100,) if channels == 1 else (44100, 2))
    mono = pcm if channels == 1 else pcm[:, 0]
    assert mono[0] == mono[-1] == 0
    assert 10000 < np.max(np.abs(mono)) <= 13107
    assert abs(int(mono[1])) < 100
    assert abs(int(mono[-2])) < 100
    assert np.argmax(np.abs(np.fft.rfft(mono))) == 256
    if channels == 2:
        np.testing.assert_array_equal(pcm[:, 0], pcm[:, 1])
    np.testing.assert_array_equal(samples, original)
    playback[1].play.assert_called_once()
    assert len(playback[1].play.call_args.args) == 1
    assert playback[1].play.call_args.kwargs == {}
    playback[0].play.assert_not_called()
    assert not engine._cache


@pytest.mark.parametrize("samples,rate,volume", [
    (np.array([], dtype=np.float32), 4096, 0.4),
    (np.ones(1, dtype=np.float32), 4096, 0.4),
    (np.ones((10, 2), dtype=np.float32), 4096, 0.4),
    (np.array([0, np.nan], dtype=np.float32), 4096, 0.4),
    (np.array([0, np.inf], dtype=np.float32), 4096, 0.4),
    (np.array([0, -np.inf], dtype=np.float32), 4096, 0.4),
    (np.ones(10, dtype=np.complex64), 4096, 0.4),
    ([0.0, 1.0], 4096, 0.4),
    (None, 4096, 0.4),
    (np.ones(10, dtype=np.float32), 0, 0.4),
    (np.ones(10, dtype=np.float32), -4096, 0.4),
    (np.ones(10, dtype=np.float32), 4096.5, 0.4),
    (np.ones(10, dtype=np.float32), True, 0.4),
    (np.ones(10, dtype=np.float32), 4096, np.nan),
    (np.ones(10, dtype=np.float32), 4096, np.inf),
    (np.ones(10, dtype=np.float32), 4096, None),
    (np.ones(2, dtype=np.float32), 1000000, 0.4),
])
def test_sonar_invalid_input_is_safe(mixer, samples, rate, volume):
    engine = AudioEngine()
    assert engine.play_sonar(samples, rate, volume) is False
    mixer[2].assert_not_called()
    mixer[1][1].play.assert_not_called()


@pytest.mark.parametrize("count", [2, 3, 4, 1000])
@pytest.mark.parametrize("volume", [-1.0, 0.4, 2.0])
def test_sonar_short_and_clipped_blocks(mixer, count, volume):
    engine = AudioEngine()
    samples = np.full(count, np.finfo(np.float32).max, dtype=np.float32)
    samples[::2] *= -1
    assert engine.play_sonar(samples, 44100, volume)
    pcm = mixer[2].call_args.args[0]
    assert pcm.dtype == np.int16
    assert np.max(np.abs(pcm.astype(np.int32))) <= 32767 * np.clip(volume, 0, 1)
    assert np.all(pcm[[0, -1]] == 0)


def test_sonar_queue_is_bounded_and_not_cached(mixer):
    _, channels, make_sound = mixer
    engine = AudioEngine(cache_size=2)
    samples = np.ones(4096, dtype=np.float32)
    assert engine.play_sonar(samples, 4096)
    channels[1].get_busy.return_value = True
    assert engine.play_sonar(samples * 0.5, 4096)
    channels[1].queue.assert_called_once()
    channels[1].get_queue.return_value = channels[1].queue.call_args.args[0]
    for _ in range(20):
        assert not engine.play_sonar(samples, 4096)
    assert make_sound.call_count == 2
    channels[1].play.assert_called_once()
    assert not engine._cache


@pytest.mark.parametrize("method", ["stop_sonar", "stop", "shutdown"])
def test_stop_includes_sonar(mixer, method):
    engine = AudioEngine()
    assert engine.play_ping()
    getattr(engine, method)()
    mixer[1][1].stop.assert_called_once()
    assert mixer[1][0].stop.call_count == (method != "stop_sonar")
    if method == "shutdown":
        assert not engine._cache
        assert not engine.play_sonar(np.ones(100, dtype=np.float32), 4096)


def test_cache_size_and_lru_avoid_resynthesis(mixer, monkeypatch):
    synthesize = Mock(wraps=tone)
    chirps = Mock(wraps=audio_module.fm_chirp)
    monkeypatch.setattr(audio_module, "tone", synthesize)
    monkeypatch.setattr(audio_module, "fm_chirp", chirps)
    engine = AudioEngine(cache_size=2)
    assert engine.play_ping(800)
    assert engine.play_alert()
    assert engine.play_ping(800)
    assert synthesize.call_count + chirps.call_count == 2
    assert engine.play_ping(1000)
    assert len(engine._cache) == 2
    assert ("alert", "danger") not in engine._cache
    assert engine.play_alert()
    assert synthesize.call_count + chirps.call_count == 4
    engine = AudioEngine(cache_size=0)
    assert engine.play_ping()
    assert engine.play_ping()
    assert not engine._cache
    assert synthesize.call_count + chirps.call_count == 6


def test_sonar_mixer_error_is_safe(mixer):
    engine = AudioEngine()
    mixer[2].side_effect = pygame.error("audio device lost")
    assert not engine.play_sonar(np.ones(100, dtype=np.float32), 4096)


def test_mixer_initialization_failure_is_safe(mixer):
    backend, _, make_sound = mixer
    backend.get_init.return_value = None
    backend.init.side_effect = pygame.error("no audio device")
    engine = AudioEngine()
    assert not engine.available
    assert not engine.play_ping()
    assert not engine.play_alert()
    assert not engine.update_engine(180)
    assert not engine.play_sonar(np.ones(100, dtype=np.float32), 4096)
    engine.stop_sonar()
    engine.shutdown()
    make_sound.assert_not_called()


@pytest.mark.parametrize("channels", [1, 2])
def test_dummy_mixer_reservations_and_sonar_stop(monkeypatch, channels):
    pygame.mixer.quit()
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    try:
        pygame.mixer.init(frequency=44100, size=-16, channels=channels,
                          allowedchanges=0)
        engine = AudioEngine(sample_rate=22050)
        assert engine.available
        assert engine.play_ping()
        assert engine.play_alert()
        assert pygame.mixer.Channel(0).get_sound() is None
        assert pygame.mixer.Channel(1).get_sound() is None
        samples = np.ones(4096, dtype=np.float32)
        assert engine.update_engine(180)
        assert engine.play_sonar(samples, 4096)
        current = pygame.mixer.Channel(1).get_sound()
        assert engine.play_sonar(samples * 0.5, 4096)
        assert pygame.mixer.Channel(1).get_queue() is not None
        assert not engine.play_sonar(samples, 4096)
        for _ in range(20):
            engine.play_ping()
            engine.play_alert()
        assert pygame.mixer.Channel(1).get_sound() == current
        assert pygame.mixer.Channel(0).get_sound() in engine._cache.values()
        engine.stop_sonar()
        assert not pygame.mixer.Channel(1).get_busy()
        assert pygame.mixer.Channel(1).get_queue() is None
        engine.shutdown()
    finally:
        pygame.mixer.quit()
