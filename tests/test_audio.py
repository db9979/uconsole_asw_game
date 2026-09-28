"""Audio- und Signalanalyse ohne echtes Audiogeraet."""

import gc
import weakref
from unittest.mock import Mock

import numpy as np
import pygame
import pytest

import src.audio.engine as audio_module
from src.audio.database import TARGET_DATABASE, rank_signatures
from src.audio.demon import DemonAnalyzer
from src.audio.engine import AudioEngine
from src.audio.synthesis import (active_sonar_ping, combat_effect, sonar_echo,
                                  filtered_noise_event, fm_chirp,
                                  stereo_bearing, tone)
from src.core import config


def test_event_primitives_are_finite():
    rate = 8000
    for event in (fm_chirp(300, 1100, .2, rate, modulation_hz=17,
                           modulation_depth_hz=12),
                  filtered_noise_event(.2, rate, 180, 900, seed=8)):
        assert event.dtype == np.float32
        assert np.isfinite(event).all()
        assert np.max(np.abs(event)) <= 1
        assert event[0] == event[-1] == 0


def test_sonar_and_combat_synthesis_is_finite_and_distinct():
    rate = 8000
    ping = active_sonar_ping(900, rate)
    effects = [combat_effect(kind, rate) for kind in
               ("torpedo_launch", "missile_launch", "gunfire", "explosion",
                "water_entry")]
    for signal in (ping, *effects):
        assert signal.dtype == np.float32
        assert signal.size > 100
        assert np.isfinite(signal).all()
        assert 0 < np.max(np.abs(signal)) <= 1
    assert len({signal.size for signal in effects}) >= 4


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
    monkeypatch.setattr(pygame.mixer, "get_init", synthesize)
    engine = AudioEngine(enabled=False)
    assert engine.available is False
    assert engine.play_ping() is False
    assert engine.play_alert("damage") is False
    assert engine.play_effect("explosion") is False
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
    count = int(0.62 * 44100)
    assert pcm.shape == ((count,) if channels == 1 else (count, 2))
    assert pcm.dtype == np.int16
    assert pcm.flags.c_contiguous
    mono = pcm if channels == 1 else pcm[:, 0]
    peak = np.argmax(np.abs(np.fft.rfft(mono))) * 44100 / count
    assert 700.0 <= peak <= 980.0


def test_initializes_signed16_and_reserves_independent_channels(mixer):
    backend, channels, _ = mixer
    backend.get_init.side_effect = [None, (22050, -16, config.AUDIO_CHANNELS)]
    backend.get_num_channels.return_value = 1
    engine = AudioEngine()
    backend.init.assert_called_once_with(
        frequency=22050, size=-16, channels=config.AUDIO_CHANNELS,
        buffer=config.AUDIO_MIXER_BUFFER_SAMPLES, allowedchanges=0)
    backend.set_num_channels.assert_called_once_with(4)
    backend.set_reserved.assert_called_once_with(4)
    assert engine._sonar_channel is channels[1]
    assert engine._ping_channel is channels[2]
    assert engine._alert_channel is channels[3]
    for name, channel in zip(
            ("sonar", "ping", "alert"), channels[1:]):
        channel.set_volume.assert_called_once_with(engine.CHANNEL_GAINS[name])


def test_audio_debug_log_is_opt_in_and_throttled(monkeypatch, tmp_path):
    monkeypatch.delenv("U_JAGD_AUDIO_DEBUG", raising=False)
    disabled_root = tmp_path / "disabled"
    monkeypatch.setattr(config, "SAVE_DIR", str(disabled_root))
    engine = AudioEngine(enabled=False)
    engine.debug_log(2.0)
    assert not disabled_root.exists()
    monkeypatch.setenv("U_JAGD_AUDIO_DEBUG", "1")
    debug_root = tmp_path / "debug"
    monkeypatch.setattr(config, "SAVE_DIR", str(debug_root))
    debug = AudioEngine(enabled=False)
    debug.sonar_dropped_blocks = 3
    debug.sonar_holds = 4
    debug.debug_log(0.6)
    assert not debug_root.exists()
    debug.debug_log(0.5)
    lines = (debug_root / "audio_debug.log").read_text().splitlines()
    assert len(lines) == 1
    assert "sonar_drops=3" in lines[0]
    assert "sonar_holds=4" in lines[0]
    assert "evictions=0" in lines[0]
    assert "channel_idle=0" in lines[0] and "pump_late=0" in lines[0]
    assert "pump_late_max_ms=0" in lines[0] and "input_gaps=0" in lines[0]
    debug.debug_log(0.8)
    assert len((debug_root / "audio_debug.log").read_text().splitlines()) == 1
    debug.debug_log(0.1)
    assert len((debug_root / "audio_debug.log").read_text().splitlines()) == 2


def test_audio_debug_log_truncates_at_bounded_size(monkeypatch, tmp_path):
    monkeypatch.setenv("U_JAGD_AUDIO_DEBUG", "1")
    monkeypatch.setattr(config, "SAVE_DIR", str(tmp_path))
    path = tmp_path / "audio_debug.log"
    # A file already at the bound is truncated before the new line (about
    # 270 bytes) is appended, so only that line remains.
    path.write_text("x" * 600, encoding="utf-8")
    debug = AudioEngine(enabled=False)
    monkeypatch.setattr(debug, "DEBUG_LOG_MAX_BYTES", 512)

    debug.debug_log(1.0)

    content = path.read_text(encoding="utf-8")
    assert len(content) < 512
    assert content.startswith("t=") and "sonar_drops=" in content


def test_audio_debug_rejects_symlinked_root_and_file(monkeypatch, tmp_path):
    monkeypatch.setenv("U_JAGD_AUDIO_DEBUG", "1")
    target = tmp_path / "target"
    target.mkdir()
    root_link = tmp_path / "root-link"
    root_link.symlink_to(target, target_is_directory=True)
    monkeypatch.setattr(config, "SAVE_DIR", str(root_link))
    AudioEngine(enabled=False).debug_log(1.0)
    assert not (target / "audio_debug.log").exists()

    safe_root = tmp_path / "safe"
    safe_root.mkdir()
    protected = tmp_path / "protected"
    protected.write_text("unchanged", encoding="utf-8")
    (safe_root / "audio_debug.log").symlink_to(protected)
    monkeypatch.setattr(config, "SAVE_DIR", str(safe_root))
    AudioEngine(enabled=False).debug_log(1.0)
    assert protected.read_text(encoding="utf-8") == "unchanged"


def test_dedicated_channels_allow_overlap_and_ping_rejects_self_overlap(mixer):
    _, channels, make_sound = mixer
    engine = AudioEngine()
    assert engine.play_sonar(np.ones(4096, dtype=np.float32), 4096)
    assert engine.play_ping()
    assert engine.play_alert("damage")
    for channel in channels[1:]:
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


def test_effect_queue_is_bounded(mixer):
    _, channels, _ = mixer
    engine = AudioEngine()
    assert engine.play_effect("torpedo_launch")
    channels[3].get_busy.return_value = True
    assert engine.play_effect("gunfire")
    channels[3].get_queue.return_value = object()
    assert not engine.play_effect("explosion")
    assert engine.alert_dropped_events == 1
    assert not engine.play_effect("unknown")


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
    assert not engine.play_ping()
    assert not engine.play_alert()
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


def test_buffered_sonar_waits_for_its_lead_and_discards_audio_on_stop(mixer):
    _, channels, _ = mixer
    engine = AudioEngine()
    # Drive the worker's mixer step synchronously; it must not consume a block
    # before the startup cushion (SONAR_BUFFER_S, 1.5 s = six blocks) exists.
    engine._sonar_worker = Mock()
    block = np.ones(1024, dtype=np.float32)
    lead_blocks = round(AudioEngine.SONAR_BUFFER_S / .25)
    assert lead_blocks == 6
    for _ in range(lead_blocks - 1):
        assert engine.play_sonar(block, 4096, buffered=True)
        engine._pump_sonar_once()
    channels[1].play.assert_not_called()
    assert engine.play_sonar(block, 4096, buffered=True)
    engine._pump_sonar_once()
    channels[1].play.assert_called_once()
    assert len(engine._sonar_buffer) == lead_blocks - 1
    channels[1].get_busy.return_value = True
    engine._pump_sonar_once()
    channels[1].queue.assert_called_once()
    engine.stop_sonar(immediate=True)
    assert not engine._sonar_buffer and engine._sonar_buffer_duration == 0
    engine._pump_sonar_once()
    channels[1].queue.assert_called_once()
    engine.shutdown()


def test_buffered_sonar_rejects_overflow_without_advancing_stream(mixer):
    engine = AudioEngine()
    engine._sonar_worker = Mock()
    block = np.ones(1024, dtype=np.float32)
    # The queue holds SONAR_BUFFER_MAX_S (5 s = 20 blocks): enough for the
    # standing lead plus a full SIM_CATCHUP_MAX_S burst plus one block.
    assert (AudioEngine.SONAR_BUFFER_MAX_S >= AudioEngine.SONAR_TARGET_S
            + config.SIM_CATCHUP_MAX_S + .25)
    for _ in range(round(AudioEngine.SONAR_BUFFER_MAX_S / .25)):
        assert engine.play_sonar(block, 4096, buffered=True)
    before = (engine._sonar_input_count, engine._sonar_output_count,
              engine._sonar_previous)
    assert not engine.play_sonar(block, 4096, buffered=True)
    assert before == (engine._sonar_input_count, engine._sonar_output_count,
                      engine._sonar_previous)
    engine.shutdown()


def test_lost_receiver_block_keeps_buffered_sonar_playback(mixer):
    _, channels, _ = mixer
    engine = AudioEngine()
    engine._sonar_worker = Mock()
    block = np.ones(1024, dtype=np.float32)
    for _ in range(8):
        assert engine.play_sonar(block, 4096, buffered=True)
    engine._pump_sonar_once()
    queued_before = len(engine._sonar_buffer)
    engine.discontinue_sonar_input()
    assert engine._sonar_previous is None
    assert len(engine._sonar_buffer) == queued_before
    assert engine._sonar_primed
    channels[1].get_busy.return_value = True
    engine._pump_sonar_once()
    channels[1].queue.assert_called_once()
    assert engine.play_sonar(block * .5, 4096, buffered=True)
    engine.shutdown()


def test_buffered_sonar_conceals_then_uses_neutral_sound_and_refills(mixer, monkeypatch):
    _, channels, make_sound = mixer
    engine = AudioEngine()
    engine._sonar_worker = Mock()
    clock = [100.0]
    monkeypatch.setattr(audio_module.time, "monotonic", lambda: clock[0])
    block = np.linspace(-.2, .2, 1024, dtype=np.float32)
    lead_blocks = round(AudioEngine.SONAR_BUFFER_S / .25)
    for _ in range(lead_blocks):
        assert engine.play_sonar(block, 4096, buffered=True)
    for _ in range(lead_blocks):
        engine._pump_sonar_once()
    assert not engine._sonar_buffer
    channels[1].get_busy.return_value = True
    engine._pump_sonar_once()
    engine._pump_sonar_once()
    # One underrun event, two concealed blocks, neither a copy of fresh audio.
    assert engine.sonar_local_underruns == 1
    assert engine.sonar_concealed_blocks == 2
    assert not engine.sonar_stale
    fresh = make_sound.call_args_list[lead_blocks - 1].args[0]
    for call in make_sound.call_args_list[-2:]:
        concealed = call.args[0]
        assert concealed.shape == fresh.shape
        assert not np.array_equal(concealed, fresh)
    assert not np.array_equal(make_sound.call_args_list[-1].args[0],
                              make_sound.call_args_list[-2].args[0])
    clock[0] += AudioEngine.SONAR_STALE_S + .1
    engine._pump_sonar_once()
    assert engine.sonar_stale and engine.sonar_neutral_blocks == 1
    # Recovery waits for a short refill (SONAR_REFILL_S, four blocks) instead
    # of stuttering block by block.
    refill_blocks = round(AudioEngine.SONAR_REFILL_S / .25)
    assert refill_blocks == 4
    for played in range(1, refill_blocks):
        assert engine.play_sonar(block * .5, 4096, buffered=True)
        engine._pump_sonar_once()
        assert engine.sonar_stale and engine.sonar_neutral_blocks == 1 + played
    assert engine.play_sonar(block * .5, 4096, buffered=True)
    engine._pump_sonar_once()
    assert not engine.sonar_stale
    assert engine.sonar_neutral_blocks == refill_blocks
    engine.stop_sonar(immediate=True)
    assert not engine.sonar_stale and not engine._sonar_buffer
    engine.shutdown()


def test_concealment_keeps_level_and_joins_last_sample(mixer):
    engine = AudioEngine()
    rng = np.random.default_rng(3)
    history = rng.normal(0, .1, 11025)
    engine._sonar_history.extend((history[:5512], history[5512:]))
    engine._sonar_last_value = np.array(.3)
    signal = engine._conceal_signal()
    assert signal.shape == (11025,)
    assert signal[0] == pytest.approx(.3)
    body = signal[round(44100 * .02):]
    assert np.sqrt(np.mean(body ** 2)) == pytest.approx(.1, rel=.15)
    assert not np.array_equal(signal, engine._conceal_signal())
    engine.shutdown()


@pytest.mark.parametrize("producer_ratio", [.99, 1.0, 1.01])
def test_elastic_rate_holds_queue_near_target_under_clock_drift(mixer, producer_ratio):
    _, channels, _ = mixer
    channels[1].get_busy.return_value = True
    engine = AudioEngine()
    engine._sonar_worker = Mock()
    block = (np.sin(np.arange(1024) * .3) * .1).astype(np.float32)
    jitter = np.random.default_rng(1)
    produced, mixer_end, adjust, levels = 0.0, None, [], []
    for step in range(18000):   # 180 s in 10 ms ticks
        now = step * .01
        if now * producer_ratio >= produced + jitter.uniform(0, .1):
            assert engine.play_sonar(block, 4096, buffered=True)
            produced += .25
        # Fake mixer: one playing and one queued block, drained in wall time.
        if mixer_end is None or now >= mixer_end - .25:
            before = engine._sonar_buffer_duration
            engine._pump_sonar_once()
            if engine._sonar_primed:
                taken = before - engine._sonar_buffer_duration
                mixer_end = (now if mixer_end is None else mixer_end) + (taken or .25)
        if step > 9000:
            adjust.append(engine.sonar_rate_adjust)
            levels.append(engine._sonar_buffer_duration)
    assert engine.sonar_local_underruns == 0
    assert engine.sonar_dropped_blocks == 0
    assert engine.sonar_channel_idle == 0
    assert (AudioEngine.SONAR_TARGET_S - .5 <= np.mean(levels)
            <= AudioEngine.SONAR_TARGET_S + 1.0)
    # The correction cancels the drift and stays steady (no audible wobble).
    assert np.mean(adjust) == pytest.approx(1 - producer_ratio, abs=.002)
    assert np.std(adjust) < .002
    engine.shutdown()


def test_elastic_rate_change_keeps_boundaries_continuous(mixer):
    _, _, make_sound = mixer
    engine = AudioEngine()
    engine._sonar_worker = Mock()
    t = np.arange(8 * 1024) / 4096
    source = (.2 * np.sin(2 * np.pi * 173 * t)).astype(np.float32)
    rates = [44100, 44100, 45000, 45000, 43500, 44100, 44982, 44100]
    for block, rate in zip(np.split(source, 8), rates):
        engine._elastic_output_rate = lambda rate=rate: rate
        assert engine.play_sonar(block, 4096, volume=1.0, buffered=True)
        engine._sonar_buffer.clear()
        engine._sonar_buffer_duration = 0.0
    blocks = [call.args[0][:, 0].astype(np.float64) / 32767
              for call in make_sound.call_args_list]
    joined = np.concatenate(blocks)
    normal_step = np.quantile(np.abs(np.diff(joined))[300:], .999)
    for boundary in np.cumsum([len(block) for block in blocks[:-1]]):
        assert abs(joined[boundary] - joined[boundary - 1]) <= normal_step * 1.3
    assert len(blocks[2]) > len(blocks[0]) > len(blocks[4])
    engine.shutdown()


def test_retuned_stream_joins_queued_tail_instead_of_dipping(mixer):
    _, _, make_sound = mixer
    engine = AudioEngine()
    engine._sonar_worker = Mock()
    block = np.full(1024, .2, dtype=np.float32)
    assert engine.play_sonar(block, 4096, volume=1.0, buffered=True)
    engine.discontinue_sonar_input()
    assert engine.play_sonar(block, 4096, volume=1.0, buffered=True)
    joined = make_sound.call_args.args[0][:, 0].astype(np.float64) / 32767
    first = make_sound.call_args_list[0].args[0][:, 0].astype(np.float64) / 32767
    assert joined[0] == pytest.approx(first[-1], abs=1e-3)
    assert np.min(joined) >= .9 * first[-1]
    engine.shutdown()


def test_orphaned_sonar_worker_releases_engine_before_mixer_teardown(mixer):
    engine = AudioEngine()
    assert engine.play_sonar(np.ones(1024, dtype=np.float32), 4096,
                             buffered=True)
    worker = engine._sonar_worker
    reference = weakref.ref(engine)
    del engine
    gc.collect()
    worker.join(timeout=1.0)
    assert reference() is None and not worker.is_alive()


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


def test_sonar_hold_fills_no_new_block_gap_without_stream_advance(mixer):
    _, channels, _ = mixer
    engine = AudioEngine()
    samples = np.linspace(-.2, .2, 1024, dtype=np.float32)
    assert engine.play_sonar(samples, 4096)
    before = (engine._sonar_input_count, engine._sonar_output_count,
              engine._sonar_previous)
    assert engine.hold_sonar()
    assert engine.hold_sonar()
    assert not engine.hold_sonar()
    assert before == (engine._sonar_input_count, engine._sonar_output_count,
                      engine._sonar_previous)
    assert channels[1].play.call_args_list[1].args[0] is engine._sonar_last_sound


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
    channels[1].get_busy.return_value = True
    engine.stop()
    engine.stop()
    channels[1].fadeout.assert_called_once_with(engine.FADE_MS)
    channels[1].stop.assert_not_called()
    for channel in channels[2:4]:
        assert channel.stop.call_count == 2
        channel.stop.reset_mock()
    engine.shutdown()
    for channel in channels[1:]:
        channel.stop.assert_called_once()
    assert not engine._cache
    assert not engine.play_sonar(np.ones(100, dtype=np.float32), 4096)


def test_cache_size_and_lru_avoid_resynthesis(mixer, monkeypatch):
    synthesize = Mock(wraps=tone)
    chirps = Mock(wraps=audio_module.active_sonar_ping)
    monkeypatch.setattr(audio_module, "tone", synthesize)
    monkeypatch.setattr(audio_module, "active_sonar_ping", chirps)
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
        assert pygame.mixer.Channel(1).get_sound() is None
        samples = np.ones(4096, dtype=np.float32)
        assert engine.play_sonar(samples, 4096)
        current = pygame.mixer.Channel(1).get_sound()
        assert engine.play_sonar(samples * 0.5, 4096)
        assert pygame.mixer.Channel(1).get_queue() is not None
        assert not engine.play_sonar(samples, 4096)
        for _ in range(20):
            engine.play_ping()
            engine.play_alert()
        assert pygame.mixer.Channel(1).get_sound() == current
        engine.stop_sonar()
        engine.shutdown()
        for index in range(4):
            assert not pygame.mixer.Channel(index).get_busy()
    finally:
        pygame.mixer.quit()


def test_unit_preview_plays_on_real_mixer_channel(monkeypatch):
    """Regression: the real SDL Sound.play() signature takes no volume
    keyword; previews must still obtain a free non-reserved channel."""
    pygame.mixer.quit()
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    try:
        pygame.mixer.init(frequency=44100, size=-16, channels=2,
                          allowedchanges=0)
        engine = AudioEngine(sample_rate=22050)
        assert engine.available
        assert engine.play_unit_preview(
            lambda: np.ones(4410, dtype=np.float32) * 0.1,
            ("sonar", "unit_preview", "diesel_alt", "acoustic_cruise", 44100))
        assert engine._preview_channel is not None
        # The editor's per-frame stop() must not cut the reference sample.
        engine.stop()
        assert engine._preview_channel is not None
        engine.stop_preview()
        assert engine._preview_channel is None
        engine.shutdown()
    finally:
        pygame.mixer.quit()


def test_unit_preview_plays_on_free_channel_and_stops_explicitly(mixer):
    backend, channels, make_sound = mixer
    engine = AudioEngine(sample_rate=22050)
    synth = lambda: np.ones(2205, dtype=np.float32) * 0.1
    key = ("sonar", "unit_preview", "diesel_alt", "acoustic_cruise", 44100)
    assert engine.play_unit_preview(synth, key)
    assert engine._preview_sound is not None
    first_channel = engine._preview_channel
    assert first_channel is not None
    # The editor's per-frame stop() must not cut a reference sample.
    engine.stop()
    assert engine._preview_channel is first_channel
    # A new preview replaces the previous one.
    assert engine.play_unit_preview(synth, key)
    # An explicit stop_preview halts the channel and clears the state.
    engine.stop_preview()
    assert engine._preview_channel is None
    assert engine._preview_sound is None
    first_channel.stop.assert_called()
    engine.shutdown()


def test_unit_preview_is_lru_cached_per_key(mixer):
    _, _, make_sound = mixer
    engine = AudioEngine(sample_rate=22050)
    calls = []
    synth = lambda: (calls.append(1), np.ones(2205, dtype=np.float32))[1]
    key = ("sonar", "unit_preview", "diesel_alt", "acoustic_cruise", 44100)
    assert engine.play_unit_preview(synth, key)
    assert engine.play_unit_preview(synth, key)
    assert calls == [1]
    engine.stop_preview()
    engine.shutdown()


def test_unit_preview_is_safe_without_audio(mixer):
    engine = AudioEngine(sample_rate=22050, enabled=False)
    synth_calls = []
    assert engine.play_unit_preview(
        lambda: (synth_calls.append(1), np.ones(10, dtype=np.float32))[1],
        ("sonar", "unit_preview", "x", "acoustic_cruise", 44100)) is False
    assert synth_calls == []
    engine.stop_preview()



def test_sonar_echo_is_bounded_and_follows_pulse_and_strength():
    rate = 8000
    cw_loud, cw_faint = (sonar_echo(900, "CW", level, rate) for level in (1.0, 0.0))
    lfm = sonar_echo(900, "LFM", 1.0, rate)
    for signal in (cw_loud, cw_faint, lfm):
        assert signal.dtype == np.float32 and np.isfinite(signal).all()
        assert 0 < np.max(np.abs(signal)) <= 1
        assert signal[0] == signal[-1] == 0
    # LFM is the short pulse; CW is the long tone.
    assert lfm.size < cw_loud.size
    # A strong CW return concentrates energy on the carrier, a faint one
    # is mostly reverberation noise around it.
    def carrier_share(signal):
        spectrum = np.abs(np.fft.rfft(signal)) ** 2
        frequencies = np.fft.rfftfreq(signal.size, 1 / rate)
        band = (frequencies > 880) & (frequencies < 920)
        return spectrum[band].sum() / spectrum.sum()
    assert carrier_share(cw_loud) > 2 * carrier_share(cw_faint)
    assert np.array_equal(sonar_echo(900, "CW", .5, rate), sonar_echo(900, "CW", .5, rate))


def test_echo_plays_on_ping_bus_and_queues_behind_a_busy_one(mixer):
    _, channels, _ = mixer
    engine = AudioEngine()
    ping = channels[2]
    assert engine.play_echo("CW", .8)
    ping.play.assert_called_once()
    ping.get_busy.return_value = True
    assert engine.play_echo("LFM", .3)
    ping.queue.assert_called_once()
    ping.get_queue.return_value = ping.queue.call_args.args[0]
    assert not engine.play_echo("CW", .5)
    assert not AudioEngine(enabled=False).play_echo("CW", 1.0)


def test_pump_counts_idle_channel_and_late_iterations(mixer, monkeypatch):
    """A dry mixer channel and a starved worker are counted, never guessed."""
    _, channels, _ = mixer
    engine = AudioEngine()
    engine._sonar_worker = Mock()
    clock = [50.0]
    monkeypatch.setattr(audio_module.time, "monotonic", lambda: clock[0])
    block = np.ones(1024, dtype=np.float32)
    for _ in range(round(AudioEngine.SONAR_BUFFER_S / .25) + 2):
        assert engine.play_sonar(block, 4096, buffered=True)
    channels[1].get_busy.return_value = True
    engine._pump_sonar_once()               # primes and plays the first block
    assert engine._sonar_primed and engine.sonar_channel_idle == 0
    # Regular 20 ms iterations are on time.
    for _ in range(5):
        clock[0] += .02
        engine._pump_sonar_once()
    assert engine.sonar_pump_late == 0
    # The worker was starved for 0.4 s and finds the channel idle: one late
    # iteration, one audible gap, both reported once in the debug line.
    clock[0] += .4
    channels[1].get_busy.return_value = False
    engine._pump_sonar_once()
    assert engine.sonar_pump_late == 1
    assert engine.sonar_pump_late_max_s == pytest.approx(.4)
    assert engine.sonar_channel_idle == 1
    channels[1].get_busy.return_value = True
    clock[0] += .02
    engine._pump_sonar_once()
    assert engine.sonar_channel_idle == 1 and engine.sonar_pump_late == 1
    engine.shutdown()


def test_pump_replays_a_queued_sound_stranded_on_an_idle_channel(mixer, monkeypatch):
    """pygame's end-of-sound callback reads the queue without the GIL, so a
    queue() in that window leaves the channel idle with a sound queued for
    good. The pump must replay it instead of waiting for the slot forever."""
    _, channels, _ = mixer
    sonar = channels[1]
    engine = AudioEngine()
    engine._sonar_worker = Mock()
    clock = [80.0]
    monkeypatch.setattr(audio_module.time, "monotonic", lambda: clock[0])
    block = np.ones(1024, dtype=np.float32)
    for _ in range(round(AudioEngine.SONAR_BUFFER_S / .25) + 2):
        assert engine.play_sonar(block, 4096, buffered=True)
    engine._pump_sonar_once()               # primes and plays the first block
    sonar.play.assert_called_once()
    stranded = object()
    sonar.get_queue.return_value = stranded
    # Busy with a queued sound is the normal state: nothing to do.
    sonar.get_busy.return_value = True
    for _ in range(3):
        clock[0] += .02
        engine._pump_sonar_once()
    sonar.play.assert_called_once()
    assert engine.sonar_queue_stranded == 0
    # Idle with the queue still held: one iteration may be the instant
    # before the callback promotes it, the second one is stranded.
    sonar.get_busy.return_value = False
    clock[0] += .02
    engine._pump_sonar_once()
    sonar.play.assert_called_once()
    clock[0] += .02
    engine._pump_sonar_once()
    assert sonar.play.call_args.args[0] is stranded
    assert engine.sonar_queue_stranded == 1
    assert engine.sonar_channel_idle == 1
    # play() cleared the queue: the next iteration refills as usual.
    sonar.get_queue.return_value = None
    sonar.get_busy.return_value = True
    clock[0] += .02
    engine._pump_sonar_once()
    sonar.queue.assert_called_once()
    engine.shutdown()


def test_stranded_queue_after_a_stream_reset_is_discarded_not_replayed(mixer):
    _, channels, _ = mixer
    sonar = channels[1]
    engine = AudioEngine()
    engine._sonar_worker = Mock()
    block = np.ones(1024, dtype=np.float32)
    stranded = object()
    sonar.get_queue.return_value = stranded
    sonar.get_busy.return_value = False
    engine.stop_sonar(immediate=True)
    for _ in range(round(AudioEngine.SONAR_BUFFER_S / .25)):
        assert engine.play_sonar(block, 4096, buffered=True)
    engine._pump_sonar_once()
    # The old beam's sound is not replayed; the new stream's play() drops it.
    sonar.play.assert_called_once()
    assert sonar.play.call_args.args[0] is not stranded
    assert engine.sonar_queue_stranded == 0
    engine.shutdown()


def test_play_sonar_restarts_a_dead_sonar_worker(mixer):
    engine = AudioEngine()
    dead = Mock()
    dead.is_alive.return_value = False
    engine._sonar_worker = dead
    assert engine.play_sonar(np.ones(1024, dtype=np.float32), 4096,
                             buffered=True)
    assert engine._sonar_worker is not dead
    assert engine._sonar_worker.is_alive()
    assert engine.sonar_worker_restarts == 1
    engine.shutdown()
