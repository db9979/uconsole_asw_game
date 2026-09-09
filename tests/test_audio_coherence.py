"""Joined-waveform and captured-PCM evidence, independent of audio hardware."""

from copy import deepcopy
from unittest.mock import Mock

import numpy as np
import pygame
import pytest

from src.audio.engine import AudioEngine
from src.audio.receiver import AcousticReceiver, directional_gain, smooth_limit
from src.audio.synthesis import propeller_block


def update(receiver, sources=(), bearing=0, **kwargs):
    receiver.update(sources, bearing, 24, kwargs.get("own_noise", 0),
                    kwargs.get("sea_state", 0), kwargs.get("own_speed", 0),
                    own_cavitation=kwargs.get("own_cavitation", 0))


def source(lines=(), seed=0, level=1, bearing=0, **kwargs):
    return dict(lines=lines, seed=seed, level=level, bearing=bearing, **kwargs)


@pytest.fixture
def playback(monkeypatch):
    channels = [Mock() for _ in range(4)]
    for channel in channels:
        channel.get_busy.return_value = False
        channel.get_queue.return_value = None
    backend = Mock()
    backend.get_init.return_value = (22050, -16, 2)
    backend.get_num_channels.return_value = 8
    backend.Channel.side_effect = channels.__getitem__
    monkeypatch.setattr(pygame, "mixer", backend)
    capture = Mock(side_effect=lambda pcm: pcm.copy())
    monkeypatch.setattr(pygame.sndarray, "make_sound", capture)
    return AudioEngine(), channels, capture


@pytest.mark.parametrize("frequencies", [(123.25, 147.3, 91.7, 173.11),
                                          (12.3, 17.9, 23.7, 8.1)])
def test_changing_frequency_matches_integrated_joined_reference(frequencies):
    receiver, background = AcousticReceiver(81), AcousticReceiver(81)
    blocks = []
    for frequency in frequencies:
        update(receiver, [source([(frequency, .8, 0)])])
        update(background)
        blocks.append(receiver.samples - background.samples)
    frequency = np.repeat(frequencies, 1024)
    phase = 2 * np.pi * np.concatenate(([0], np.cumsum(frequency[:-1]))) / 4096
    expected = .2 * np.sin(phase)
    if frequencies[0] < 80:
        t = np.arange(frequency.size) / 4096
        expected += .08 * (1 + .7 * np.sin(phase)) * np.sin(2 * np.pi * 700 * t)
    edge = round(.005 * 4096)
    expected[:edge] *= np.linspace(0, 1, edge)
    np.testing.assert_allclose(np.concatenate(blocks), expected, atol=4e-8)


def test_component_amplitude_and_disappearance_lifecycle():
    receiver = AcousticReceiver()
    phase = .7
    previous_amp = 0
    state = {}
    for freq, amp in [(121.3, .2), (131.7, .4), (93.1, 0), (161.9, .1)]:
        block, state = receiver._components({"line": (freq, amp, .7)}, state)
        envelope = np.full(1024, amp)
        envelope[:20] = np.linspace(previous_amp, amp, 20)
        expected = envelope * np.sin(phase + 2 * np.pi * freq * np.arange(1024) / 4096)
        np.testing.assert_allclose(block, expected, atol=2e-13)
        phase += 2 * np.pi * freq * .25
        previous_amp = amp
        assert 0 <= state["line"][2] < 2 * np.pi
    release, state = receiver._components({}, state)
    assert state == {}
    assert np.any(release[:19]) and not np.any(release[19:])
    attack, _ = receiver._components({"line": (161.9, .1, .7)}, state)
    assert attack[0] == 0


def test_changing_spread_keeps_each_side_tone_phase():
    receiver, background = AcousticReceiver(11), AcousticReceiver(11)
    phases = np.zeros(3)
    old_amps = np.zeros(3)
    for freq, spread in [(123.3, 0), (127.7, 5), (119.1, 9), (121.9, 0)]:
        update(receiver, [source([(freq, .8, spread)])])
        update(background)
        freqs = np.array([freq - spread / 2, freq, freq + spread / 2])
        amps = np.array([.05, .1, .05]) if spread else np.array([0, .2, 0])
        envelope = np.repeat(amps[:, None], 1024, axis=1)
        envelope[:, :20] = np.linspace(old_amps, amps, 20).T
        expected = np.sum(envelope * np.sin(
            phases[:, None] + 2 * np.pi * freqs[:, None] * np.arange(1024) / 4096), axis=0)
        np.testing.assert_allclose(receiver.samples - background.samples, expected, atol=3e-8)
        phases += 2 * np.pi * freqs * .25
        old_amps = amps


def test_own_shaft_changing_speed_uses_integrated_phase():
    receiver = AcousticReceiver(4)
    rng = np.random.default_rng(4)
    phase, old_amp = 0, 0
    for speed in (11.3, 19.8, 4.7, 0):
        update(receiver, own_speed=speed)
        freq = 10 + 1.9 * speed
        amp = .08 * min(speed / 20, 1) * .25
        envelope = np.full(1024, amp)
        envelope[:20] = np.linspace(old_amp, amp, 20)
        expected = envelope * np.sin(phase + 2 * np.pi * freq * np.arange(1024) / 4096)
        expected += rng.normal(0, np.hypot(.002, .025 * speed / 60), 1024)
        np.testing.assert_allclose(receiver.samples, expected, atol=1e-8)
        phase += 2 * np.pi * freq * .25
        old_amp = amp


@pytest.mark.parametrize("lines,broadband", [([], None), ([(160, 0, 0)], None),
    ([(160, .3, 0)], None), ([(24, .4, 0)], None),
    ([], dict(level=.8, low_hz=100, high_hz=700)),
    ([], dict(level=1, low_hz=2900, high_hz=3000)),
    ([(160, .3, 4)], dict(level=.7, low_hz=100, high_hz=700))])
def test_scan_is_actual_unsteered_power_not_presence_or_listening_bearing(lines, broadband):
    on, off, background = AcousticReceiver(5), AcousticReceiver(5), AcousticReceiver(5)
    item = source(lines, seed=91, level=.6, broadband=broadband)
    for _ in range(4):
        update(on, [item])
        update(off, [item], bearing=113)
        update(background)
        np.testing.assert_array_equal(on.broadband, off.broadband)
        signal = on.samples.astype(float) - background.samples
        expected = (np.mean(signal**2) / .25**2
                    * directional_gain(np.arange(180) * 2, 0, 24)**2)
        np.testing.assert_allclose(np.array(on.broadband) - background.broadband,
                                   expected, atol=2e-9)
    if not lines or all(line[1] == 0 for line in lines):
        if broadband is None or broadband["low_hz"] > 2048:
            np.testing.assert_array_equal(on.broadband, background.broadband)
    on.reset()
    off.reset()
    update(on, [item], bearing=35)
    update(off, [item], bearing=261)
    np.testing.assert_array_equal(on.broadband, off.broadband)


def test_scan_level_is_power_and_noise_terms_use_same_normalization():
    full, half, background = AcousticReceiver(), AcousticReceiver(), AcousticReceiver()
    for _ in range(2):
        update(full, [source([(140, .2, 0)], level=1)])
        update(half, [source([(140, .2, 0)], level=.5)])
        update(background)
    np.testing.assert_allclose(np.array(full.broadband) - background.broadband,
                               4 * (np.array(half.broadband) - background.broadband),
                               atol=1e-18)
    update(full, own_noise=.5, sea_state=3, own_cavitation=.4)
    # No phantom source after its one-block release.
    update(full, own_noise=.5, sea_state=3, own_cavitation=.4)
    expected = ((.002 + .035 / 3)**2 + .02**2 + .04**2) / .25**2
    np.testing.assert_allclose(full.broadband, expected)


def test_band_cache_is_bounded_and_eviction_does_not_change_masks():
    receiver = AcousticReceiver()
    expected = receiver._band_mask(100.1, 500.1).copy()
    other = receiver._band_mask(100.4, 500.4)
    assert not np.array_equal(expected, other)
    for i in range(400):
        receiver._band_mask(i + .25, i + 300.75)
        assert len(receiver._band_cache) <= receiver.BAND_CACHE_SIZE
    np.testing.assert_array_equal(expected, receiver._band_mask(100.1, 500.1))


def test_source_state_is_bounded_released_and_zero_slots_keep_identity():
    receiver = AcousticReceiver()
    for generation in range(3):
        items = [source([(123.7, .01, 0)] * 40, seed=generation * 200 + i)
                 for i in range(140)]
        update(receiver, items)
        assert len(receiver._source_states) == receiver.MAX_SOURCES
        assert all(len(state) <= receiver.MAX_LINES * 3 + 3
                   for _, state, _, _ in receiver._source_states.values())
    update(receiver)
    assert receiver._source_states == {}


def test_sequence_handoff_is_bounded_nonconsuming_and_device_independent(playback):
    engine, _, _ = playback
    receiver, reference = AcousticReceiver(7), AcousticReceiver(7)
    cursor = receiver.sequence
    for i in range(9):
        update(receiver, [source([(123 + i, .2, 0)])])
        update(reference, [source([(123 + i, .2, 0)])])
        # A disabled/stalled consumer cannot modify receiver continuation.
        engine.enabled = False
        for sequence, samples in receiver.blocks_since(cursor):
            assert not engine.play_sonar(samples, receiver.sample_rate)
            assert not samples.flags.writeable
        assert len(receiver.blocks_since(-1)) <= 2
        np.testing.assert_array_equal(receiver.samples, reference.samples)
        assert receiver.spectrum == reference.spectrum
    blocks = receiver.blocks_since(cursor)
    assert [seq for seq, _ in blocks] == [8, 9]
    assert blocks[0][0] > cursor + 1  # explicit gap visible to the integrator
    assert receiver.blocks_since(8)[0][0] == 9
    receiver.reset()
    assert receiver.blocks_since(-1) == ()
    update(receiver)
    assert receiver.blocks_since(-1)[0][0] == 11


def test_band_filter_ola_is_a_bounded_half_block_delayed_stream():
    receiver = AcousticReceiver()
    rng = np.random.default_rng(12)
    inputs = [rng.normal(size=1024) for _ in range(3)]
    mask = np.ones(513)
    state = None
    outputs = []
    for block in inputs:
        output, state = receiver._band_audio(block, mask, 1.0, state)
        outputs.append(output)
        assert len(state) == 2
        assert all(part.shape == (512,) for part in state)
    source = np.concatenate(inputs)
    expected = np.concatenate((np.zeros(512), source[:-512]))
    np.testing.assert_allclose(np.concatenate(outputs), expected, atol=1e-12)


def test_two_due_blocks_can_be_retried_then_played_without_losing_1x_audio(playback):
    engine, channels, capture = playback
    receiver = AcousticReceiver(21)
    cursor = receiver.sequence
    all_samples, accepted = [], []
    for _ in range(6):
        for _ in range(2):
            update(receiver, [source([(137.1, .2, 0)])])
            all_samples.append(receiver.samples)
        channels[1].get_queue.return_value = object()
        first_sequence, first_samples = receiver.blocks_since(cursor)[0]
        assert first_sequence == cursor + 1
        assert not engine.play_sonar(first_samples, 4096)
        # A subsequent wall frame has capacity; retry rather than mark as heard.
        channels[1].get_queue.return_value = None
        channels[1].get_busy.return_value = False
        for sequence, samples in receiver.blocks_since(cursor):
            assert sequence == cursor + 1
            assert engine.play_sonar(samples, 4096)
            accepted.append(sequence)
            cursor = sequence
            channels[1].get_busy.return_value = True
    assert accepted == list(range(1, 13))
    streamed = np.concatenate([call.args[0] for call in capture.call_args_list])
    engine._reset_sonar_stream()
    assert engine.play_sonar(np.concatenate(all_samples), 4096)
    np.testing.assert_array_equal(streamed, capture.call_args.args[0])


@pytest.mark.parametrize("source_rate", [4096, 4093, 22050, 48000])
@pytest.mark.parametrize("bearing", [None, 90, 270])
def test_streaming_resample_equals_joined_reference_without_boundary_crossfade(
        playback, source_rate, bearing):
    engine, channels, capture = playback
    rng = np.random.default_rng(41)
    # Include nonstationary/high-frequency content that a constant blend destroys.
    signal = (.1 * rng.normal(size=6000)).astype(np.float32)
    blocks = np.split(signal, [1001, 2804, 4000])
    for block in blocks:
        assert engine.play_sonar(block, source_rate, volume=.8, bearing_deg=bearing)
        channels[1].get_busy.return_value = True
    streamed = np.concatenate([call.args[0] for call in capture.call_args_list])
    engine._reset_sonar_stream()
    assert engine.play_sonar(signal, source_rate, volume=.8, bearing_deg=bearing)
    np.testing.assert_array_equal(streamed, capture.call_args.args[0])
    assert len(streamed) == int(np.ceil(len(signal) * engine.sample_rate / source_rate))


def test_rejected_block_leaves_stream_state_retryable(playback):
    engine, channels, capture = playback
    block = np.linspace(-.2, .2, 1024, dtype=np.float32)
    assert engine.play_sonar(block, 4096)
    before = (engine._sonar_input_count, engine._sonar_output_count, engine._sonar_previous)
    channels[1].get_queue.return_value = object()
    assert not engine.play_sonar(block, 4096)
    assert before == (engine._sonar_input_count, engine._sonar_output_count,
                      engine._sonar_previous)
    channels[1].get_queue.return_value = None
    capture.side_effect = pygame.error("lost device")
    assert not engine.play_sonar(block, 4096)
    assert before == (engine._sonar_input_count, engine._sonar_output_count,
                      engine._sonar_previous)


def test_discontinuity_discards_current_and_promoted_queue(playback):
    engine, channels, _ = playback
    assert engine.play_sonar(np.ones(1024, dtype=np.float32), 4096)
    channels[1].get_queue.return_value = object()
    engine.stop_sonar(immediate=True)
    assert channels[1].stop.call_count == 2
    assert engine._sonar_rate is None
    assert engine._sonar_previous is None
    assert engine._sonar_input_count == engine._sonar_output_count == 0


def test_volume_has_no_60_to_100_percent_dead_range_and_analysis_is_unchanged(playback):
    engine, _, capture = playback
    receiver = AcousticReceiver()
    for _ in range(8):
        update(receiver, [source([(137.3, .3, 0)])])
    before = deepcopy((receiver.samples, receiver.spectrum, receiver.peaks,
                       receiver.demon_spectrum, receiver.broadband, receiver._source_states))
    rms = []
    for volume in (.6, .7, .8, .9, 1):
        engine._reset_sonar_stream()
        assert engine.play_sonar(receiver.samples, 4096, volume=volume)
        rms.append(np.sqrt(np.mean(capture.call_args.args[0].astype(float)**2)))
    np.testing.assert_allclose(np.array(rms) / rms[-1], [.6, .7, .8, .9, 1], atol=.001)
    np.testing.assert_array_equal(before[0], receiver.samples)
    assert before[1:] == (receiver.spectrum, receiver.peaks, receiver.demon_spectrum,
                          receiver.broadband, receiver._source_states)


@pytest.mark.parametrize("bearing", [None, 0, 90, 270])
@pytest.mark.parametrize("hostile", [False, True])
def test_real_postlimiter_pcm_bus_and_composite_ceiling(playback, monkeypatch, bearing, hostile):
    engine, _, capture = playback
    if hostile:
        # Force coincident over-range peaks through actual public playback paths.
        import src.audio.engine as module
        for name in ("propeller_block", "fm_chirp", "tone"):
            monkeypatch.setattr(module, name, lambda *a, **k: np.full(5512, 1e6))
    assert engine.update_engine(247.3, cavitation=.7, volume=1)
    assert engine.play_sonar(np.full(1024, 1e6, dtype=np.float32), 4096,
                             volume=1, bearing_deg=bearing)
    assert engine.play_ping(volume=1)
    assert engine.play_alert("damage")
    buses = dict(zip(("engine", "sonar", "ping", "alert"),
                     (call.args[0].astype(float) / 32767 for call in capture.call_args_list)))
    length = min(map(len, buses.values()))
    composite = np.zeros((length, 2))
    for name, pcm in buses.items():
        assert np.max(np.abs(pcm)) <= engine.SOURCE_LIMITS[name]
        composite += pcm[:length] * engine.CHANNEL_GAINS[name]
    assert np.max(np.abs(composite)) <= .9155
    if hostile and bearing in (None, 90, 270):
        assert np.max(composite) > .915  # exercise the ceiling, not a quiet mix


def test_engine_wrapped_blade_and_shaft_phases_match_unwrapped_reference(playback):
    engine, channels, capture = playback
    phase = 0
    shaft_phase = 0
    for rpm, blades in [(183, 5)] * 8 + [(217.3, 5), (91.7, 7), (103.1, 3)]:
        assert engine.update_engine(rpm, blades, cavitation=0, volume=.12)
        count = int(.25 * engine.sample_rate)
        reference = propeller_block(rpm, blades, engine.sample_rate, amplitude=.12,
                                     phase=phase, shaft_phase=shaft_phase)
        expected = smooth_limit(reference, knee=.135, ceiling=.18)
        expected = (expected * 32767).astype(np.int16)
        np.testing.assert_array_equal(capture.call_args.args[0][:, 0], expected)
        blade_hz = rpm / 60 * blades
        phase += 2 * np.pi * blade_hz * count / engine.sample_rate
        shaft_phase += 2 * np.pi * blade_hz / blades * count / engine.sample_rate
        assert 0 <= engine._engine_phase < 2 * np.pi
        assert 0 <= engine._engine_shaft_phase < 2 * np.pi
        channels[0].get_busy.return_value = True
