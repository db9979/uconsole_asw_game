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
from src.core import config


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


def test_propeller_cavitation_rng_and_filter_are_continuous():
    rate = 8000
    rng = np.random.default_rng(41)
    state = np.zeros(5)
    first = propeller_block(183, 5, rate, cavitation=.7, phase=.4,
                            rng=rng, filter_state=state)
    phase = .4 + 2 * np.pi * (183 / 60 * 5) * first.size / rate
    second = propeller_block(183, 5, rate, cavitation=.7, phase=phase,
                             rng=rng, filter_state=state)
    whole = propeller_block(183, 5, rate, duration_s=.5, cavitation=.7,
                            phase=.4, rng=np.random.default_rng(41),
                            filter_state=np.zeros(5))
    np.testing.assert_allclose(np.concatenate((first, second)), whole, atol=2e-7)


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
    channels = [Mock(), Mock(), Mock(), Mock()]
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
    backend.get_init.side_effect = [None, (22050, -16, config.AUDIO_CHANNELS)]
    backend.get_num_channels.return_value = 1
    engine = AudioEngine()
    backend.init.assert_called_once_with(
        frequency=22050, size=-16, channels=config.AUDIO_CHANNELS,
        buffer=config.AUDIO_MIXER_BUFFER_MS, allowedchanges=0)
    backend.set_num_channels.assert_called_once_with(4)
    backend.set_reserved.assert_called_once_with(4)
    assert engine._engine_channel is channels[0]
    assert engine._sonar_channel is channels[1]
    assert engine._ping_channel is channels[2]
    assert engine._alert_channel is channels[3]
    for name, channel in zip(("engine", "sonar", "ping", "alert"), channels):
        channel.set_volume.assert_called_once_with(engine.CHANNEL_GAINS[name])


def test_audio_debug_log_is_opt_in_and_throttled(monkeypatch, tmp_path):
    monkeypatch.delenv("U_JAGD_AUDIO_DEBUG", raising=False)
    engine = AudioEngine(enabled=False)
    engine.debug_log(2.0)
    assert not (tmp_path / "audio_debug.log").exists()
    monkeypatch.setenv("U_JAGD_AUDIO_DEBUG", "1")
    monkeypatch.setattr(config, "SAVE_DIR", str(tmp_path))
    debug = AudioEngine(enabled=False)
    debug.engine_dropped_blocks = 3
    debug.sonar_holds = 4
    debug.debug_log(0.6)
    assert not (tmp_path / "audio_debug.log").exists()
    debug.debug_log(0.5)
    lines = (tmp_path / "audio_debug.log").read_text().splitlines()
    assert len(lines) == 1
    assert "engine_drops=3" in lines[0] and "underruns=0" in lines[0]
    assert "sonar_holds=4" in lines[0]
    assert "evictions=0" in lines[0]


def test_dedicated_channels_allow_overlap_and_ping_rejects_self_overlap(mixer):
    _, channels, make_sound = mixer
    engine = AudioEngine()
    assert engine.update_engine(180)
    assert engine.play_sonar(np.ones(4096, dtype=np.float32), 4096)
    assert engine.play_ping()
    assert engine.play_alert("damage")
    for channel in channels:
        channel.play.assert_called_once()
    calls = make_sound.call_count
    channels[2].get_busy.return_value = True
    assert not engine.play_ping()
    assert make_sound.call_count == calls
    channels[2].play.side_effect = pygame.error("device lost")
    channels[2].get_busy.return_value = False
    assert not engine.play_ping(901)
    channels[3].get_busy.return_value = True
    assert engine.play_alert("launch")
    channels[3].queue.assert_called_once()
    channels[3].get_queue.return_value = channels[3].queue.call_args.args[0]
    assert not engine.play_alert("defense")
    assert engine.alert_dropped_events == 1


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
    assert mono[0] == 0
    assert 10000 < np.max(np.abs(mono)) < 15000
    assert abs(int(mono[1])) < 100
    assert np.argmax(np.abs(np.fft.rfft(mono))) == 256
    if channels == 2:
        np.testing.assert_array_equal(pcm[:, 0], pcm[:, 1])
    np.testing.assert_array_equal(samples, original)
    playback[1].play.assert_called_once()
    assert len(playback[1].play.call_args.args) == 1
    assert playback[1].play.call_args.kwargs == {"fade_ms": engine.FADE_MS}
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
    assert np.max(np.abs(pcm.astype(np.int32))) < 32767
    assert not np.any(np.abs(pcm.astype(np.int32)) == 32767)
    assert np.all(pcm[0] == 0)


@pytest.mark.parametrize("gain_db", [12, 24])
def test_sonar_gain_is_soft_limited_after_headphone_volume(mixer, gain_db):
    engine = AudioEngine(channels=1)
    rate = 4096
    t = np.arange(1024) / rate
    gained = (.4 * 10 ** (gain_db / 20)
              * np.sin(2 * np.pi * 173 * t)).astype(np.float32)

    def rendered(volume):
        mixer[2].reset_mock()
        engine._reset_sonar_stream()
        assert engine.play_sonar(gained, rate, volume=volume)
        pcm = mixer[2].call_args.args[0]
        mono = pcm if pcm.ndim == 1 else pcm[:, 0]
        return mono.astype(np.float64) / 32767

    loud = rendered(1.0)
    assert np.isfinite(loud).all()
    assert np.max(np.abs(loud)) < 1.0
    assert not np.any(np.abs(loud) == 1.0)
    assert np.max(np.abs(loud)) <= AudioEngine.SOURCE_LIMITS["sonar"]
    quiet = rendered(.1)
    baseline = rendered(.01)
    loud_error = np.sqrt(np.mean((loud - baseline / .01) ** 2))
    quiet_error = np.sqrt(np.mean((quiet / .1 - baseline / .01) ** 2))
    assert quiet_error < loud_error


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


def test_sonar_hold_repeats_previous_block_on_idle_channel(mixer, monkeypatch):
    _, channels, _ = mixer
    made = []
    monkeypatch.setattr(pygame.sndarray, "make_sound",
                        lambda pcm: made.append(pcm) or pcm)
    engine = AudioEngine()
    blocks = [np.full(4096, 1.0 / 2 ** i, dtype=np.float32) for i in range(4)]
    for samples in blocks:
        assert engine.play_sonar(samples, 4096, hold=True)
    played = [call.args[0] for call in channels[1].play.call_args_list]
    queued = [call.args[0] for call in channels[1].queue.call_args_list]
    # First block starts fresh; blocks 2 and 3 repeat the previous block and
    # queue the new one; block 4 hits the hold bound and starts normally.
    assert len(played) == 4 and len(queued) == 2
    assert played[0] is made[0] and played[1] is made[0]
    assert played[2] is made[1] and played[3] is made[3]
    assert queued[0] is made[1] and queued[1] is made[2]
    assert engine.sonar_holds == 2


def test_sonar_hold_is_opt_in_and_reset_by_busy_channel(mixer):
    _, channels, _ = mixer
    engine = AudioEngine()
    samples = np.ones(4096, dtype=np.float32)
    assert engine.play_sonar(samples, 4096)
    assert engine.play_sonar(samples * 0.5, 4096)
    assert channels[1].play.call_count == 2
    assert channels[1].queue.call_count == 0
    assert engine.sonar_holds == 0
    assert engine._sonar_hold_streak == 0
    channels[1].get_busy.return_value = True
    assert engine.play_sonar(samples * 0.25, 4096, hold=True)
    assert engine._sonar_hold_streak == 0
    assert channels[1].queue.call_count == 1


def test_sonar_hold_state_clears_on_stop(mixer):
    _, channels, _ = mixer
    engine = AudioEngine()
    samples = np.ones(4096, dtype=np.float32)
    assert engine.play_sonar(samples, 4096)
    assert engine.play_sonar(samples * 0.5, 4096, hold=True)
    assert channels[1].queue.call_count == 1
    engine.stop_sonar()
    assert engine._sonar_last_sound is None
    assert engine._sonar_hold_streak == 0
    assert engine.play_sonar(samples, 4096, hold=True)
    assert channels[1].queue.call_count == 1
    engine.shutdown()


def test_sonar_hold_does_not_change_resampler_state(mixer):
    engine = AudioEngine()
    source_rate = 4093
    t = np.arange(3000, dtype=np.float64) / source_rate
    source = np.sin(2 * np.pi * 173 * t).astype(np.float32)
    for block in np.array_split(source, 3):
        assert engine.play_sonar(block, source_rate, hold=True)
    assert engine._sonar_input_count == source.size
    assert engine._sonar_output_count == int(
        np.ceil(source.size * 44100 / source_rate))
    assert engine._sonar_previous == float(source[-1])


def test_stereo_sonar_bearing_play_and_queue_preserve_continuity(mixer):
    _, channels, make_sound = mixer
    engine = AudioEngine()
    source_rate = 4093
    t = np.arange(2000, dtype=np.float64) / source_rate
    source = np.sin(2 * np.pi * 173 * t).astype(np.float32)
    first, second = np.array_split(source, 2)

    assert engine.play_sonar(first, source_rate, bearing_deg=90,
                             listener_bearing_deg=0)
    first_pcm = make_sound.call_args.args[0]
    assert first_pcm.shape[1] == 2
    assert np.max(np.abs(first_pcm[:, 1])) > np.max(np.abs(first_pcm[:, 0]))
    assert engine._sonar_input_count == first.size
    assert engine._sonar_previous == float(first[-1])

    channels[1].get_busy.return_value = True
    assert engine.play_sonar(second, source_rate, bearing_deg=90,
                             listener_bearing_deg=0)
    second_pcm = make_sound.call_args.args[0]
    channels[1].play.assert_called_once()
    channels[1].queue.assert_called_once()
    assert make_sound.call_count == 2
    assert engine._sonar_input_count == source.size
    assert engine._sonar_output_count == int(np.ceil(source.size * 44100 / source_rate))

    joined = np.concatenate((first_pcm, second_pcm)).astype(np.int32)
    normal_step = np.quantile(np.abs(np.diff(joined, axis=0))[300:], .999,
                              axis=0)
    boundary_step = np.abs(second_pcm[0].astype(np.int32)
                           - first_pcm[-1].astype(np.int32))
    assert np.all(boundary_step <= normal_step * 1.2)


def test_engine_queues_ahead_and_advances_only_accepted_blocks(mixer):
    _, channels, make_sound = mixer
    engine = AudioEngine()
    assert engine.update_engine(183, cavitation=.7)
    phase = engine._engine_phase
    rng_state = repr(engine._engine_rng.bit_generator.state)
    channels[0].get_busy.return_value = True
    assert engine.update_engine(183, cavitation=.7)
    channels[0].queue.assert_called_once()
    assert engine._engine_phase != phase
    accepted_phase = engine._engine_phase
    accepted_rng_state = repr(engine._engine_rng.bit_generator.state)
    channels[0].get_queue.return_value = channels[0].queue.call_args.args[0]
    assert not engine.update_engine(183, cavitation=.7)
    assert engine.engine_dropped_blocks == 1
    assert engine._engine_phase == accepted_phase
    assert repr(engine._engine_rng.bit_generator.state) == accepted_rng_state
    assert repr(engine._engine_rng.bit_generator.state) != rng_state
    assert make_sound.call_count == 2


def test_sonar_resampling_uses_cumulative_lengths_and_clean_boundaries(mixer):
    _, _, make_sound = mixer
    engine = AudioEngine()
    source_rate = 4093
    t = np.arange(3000, dtype=np.float64) / source_rate
    source = np.sin(2 * np.pi * 173 * t).astype(np.float32)
    for block in np.array_split(source, 3):
        assert engine.play_sonar(block, source_rate, volume=1.0)
    blocks = [call.args[0][:, 0].astype(np.float64) / 32767
              for call in make_sound.call_args_list]
    assert sum(map(len, blocks)) == int(np.ceil(source.size * 44100 / source_rate))
    joined = np.concatenate(blocks)
    normal_step = np.quantile(np.abs(np.diff(joined))[300:], .999)
    for boundary in np.cumsum([len(block) for block in blocks[:-1]]):
        assert abs(joined[boundary] - joined[boundary - 1]) <= normal_step * 1.2


def test_normal_stop_fades_streams_and_clears_event_buses(mixer):
    engine = AudioEngine()
    channels = mixer[1]
    channels[0].get_busy.return_value = True
    channels[1].get_busy.return_value = True
    engine.stop()
    engine.stop()
    channels[0].fadeout.assert_called_once_with(engine.FADE_MS)
    channels[1].fadeout.assert_called_once_with(engine.FADE_MS)
    for channel in channels[:2]:
        channel.stop.assert_not_called()
    for channel in channels[2:]:
        assert channel.stop.call_count == 2
        channel.stop.reset_mock()
    engine.shutdown()
    for channel in channels:
        channel.stop.assert_called_once()
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
        assert pygame.mixer.Channel(0).get_sound() is not None
        engine.stop_sonar()
        engine.shutdown()
        for index in range(4):
            assert not pygame.mixer.Channel(index).get_busy()
    finally:
        pygame.mixer.quit()
