import random

import numpy as np
import pytest

from src.audio.hydroacoustics import (
    AcousticSignature, HydroacousticChannel, analyze_demon, analyze_lofar,
)
from src.audio.receiver import AcousticReceiver


def test_signature_one_shot_matches_blocks_and_preserves_rng_and_phases():
    legacy, py_state = np.random.get_state(), random.getstate()
    whole = AcousticSignature(frame_size=4096, seed=19).render_frame()
    blocked_source = AcousticSignature(frame_size=2048, seed=19)
    blocked = np.concatenate((blocked_source.render_frame(), blocked_source.render_frame()))
    np.testing.assert_allclose(blocked, whole, atol=2e-7)
    assert whole.dtype == np.float32 and whole.shape == (4096,)
    assert all(0 <= phase < 2 * np.pi for phase in (
        blocked_source.shaft_phase, blocked_source.blade_phase,
        blocked_source.carrier_phase))
    assert np.random.get_state()[0] == legacy[0]
    np.testing.assert_array_equal(np.random.get_state()[1], legacy[1])
    assert random.getstate() == py_state


def test_noninteger_harmonic_is_exactly_partition_continuous():
    whole = AcousticSignature(frame_size=4096, rpm=137.3, blades=7,
                              harmonics=((1.5, .4),), cavitation=0, seed=19)
    split = AcousticSignature(frame_size=2048, rpm=137.3, blades=7,
                              harmonics=((1.5, .4),), cavitation=0, seed=19)
    joined = np.concatenate((split.render_frame(), split.render_frame()))
    np.testing.assert_allclose(joined, whole.render_frame(), atol=2e-7)
    assert 0 <= split.harmonic_phases[0] < 2 * np.pi


def test_custom_harmonic_uses_shaft_rate_without_aliasing():
    source = AcousticSignature(frame_size=32768, rpm=3600, blades=16,
                               harmonics=((128.0, 1.0),), cavitation=0, seed=3)
    samples = source.render_frame()
    frequencies = np.fft.rfftfreq(samples.size, 1 / source.sample_rate)
    assert frequencies[np.argmax(abs(np.fft.rfft(samples)))] == pytest.approx(
        7680, abs=1)
    assert 7680 < source.sample_rate / 2


def test_channel_uses_meter_spreading_absorption_and_layer_loss():
    channel = HydroacousticChannel(distance_m=1000, source_depth_m=20,
                                   receiver_depth_m=20,
                                   thermocline_depth_m=50)
    expected = 20 * np.log10(1000) + .0004 * 1000
    assert channel.transmission_loss_db() == pytest.approx(expected)
    channel.set_geometry(receiver_depth_m=80)
    assert channel.transmission_loss_db() == pytest.approx(expected + 25)


def test_signature_changes_are_smoothed_without_boundary_pop():
    source = AcousticSignature(frame_size=2048, rpm=80, gain=.1, cavitation=0, seed=3)
    before = source.render_frame()
    changed = source.render_frame(rpm=240, gain=.8)
    assert abs(float(changed[0] - before[-1])) < .25
    assert source.rpm < 240 and source.gain < .8
    for _ in range(20):
        source.render_frame()
    assert source.rpm == pytest.approx(240, rel=1e-3)


def test_channel_streaming_filter_approach_depth_and_smoothing():
    tone = np.sin(2 * np.pi * 6000 * np.arange(4096) / 32768).astype(np.float32)
    whole_channel = HydroacousticChannel(distance_m=1000)
    whole = whole_channel.process_frame(tone)
    block_channel = HydroacousticChannel(distance_m=1000)
    blocked = np.concatenate((block_channel.process_frame(tone[:2048]),
                              block_channel.process_frame(tone[2048:])))
    np.testing.assert_allclose(blocked, whole, atol=1e-7)
    far = HydroacousticChannel(distance_m=4000).process_frame(tone)
    near_channel = HydroacousticChannel(distance_m=4000)
    near_channel.process_frame(tone)
    near = near_channel.process_frame(tone, distance_m=500)
    cross = HydroacousticChannel(distance_m=500, source_depth_m=80,
                                 receiver_depth_m=20,
                                 thermocline_depth_m=50).process_frame(tone)
    assert np.sqrt(np.mean(near[-1000:] ** 2)) > np.sqrt(np.mean(far[-1000:] ** 2))
    assert np.sqrt(np.mean(cross[-1000:] ** 2)) < .08 * np.sqrt(
        np.mean(near[-1000:] ** 2))
    assert abs(float(near[0] - far[-1])) < .2


def test_lofar_line_and_demon_seven_blades_at_120_rpm():
    rate = 32768
    time = np.arange(rate * 4) / rate
    lofar = analyze_lofar(np.sin(2 * np.pi * 137 * time), rate)
    peak = lofar.frequencies_hz[np.argmax(lofar.magnitude.mean(axis=0))]
    assert peak == pytest.approx(137, abs=4)
    source = AcousticSignature(rpm=120, blades=7, frame_size=2048,
                               cavitation=.7, seed=77)
    pcm = np.concatenate([source.render_frame() for _ in range(64)])
    demon = analyze_demon(pcm, rate)
    assert demon.blade_rate_hz == pytest.approx(14, abs=.3)
    assert dict(demon.rpm_hypotheses)[7] == pytest.approx(120, abs=3)


def test_demon_reports_measured_peak_and_harmonic_ambiguity():
    rate = 32768
    time = np.arange(rate * 4) / rate
    envelope = 1 + .15 * np.sin(2 * np.pi * 14 * time) \
        + .65 * np.sin(2 * np.pi * 28 * time)
    result = analyze_demon(envelope * np.sin(2 * np.pi * 4000 * time), rate)
    assert result.modulation_peak_hz == pytest.approx(28, abs=.3)
    assert result.blade_rate_hz == result.modulation_peak_hz
    assert any(item.blade_count == 7 and item.harmonic_order == 2
               and item.rpm == pytest.approx(120, abs=3)
               for item in result.hypotheses)


def test_demon_noise_has_no_confident_hypothesis_and_bounds_reject_hostile_values():
    noise = np.random.default_rng(4).normal(0, .1, 32768 * 2)
    assert analyze_demon(noise, 32768).blade_rate_hz is None
    with pytest.raises(ValueError):
        AcousticSignature(sample_rate=24000)
    with pytest.raises(ValueError):
        AcousticSignature(rpm=True)
    with pytest.raises(ValueError):
        HydroacousticChannel(distance_m=float("nan"))
    with pytest.raises(ValueError):
        analyze_lofar(np.zeros(4096), 32768, fft_size=1000)
    with pytest.raises(ValueError):
        analyze_demon(np.zeros(4096), 32768, carrier_band_hz=(2000, 20000))


def test_live_receiver_applies_only_detached_relative_spectral_points():
    flat, colored = AcousticReceiver(8), AcousticReceiver(8)
    base = {"bearing": 0, "level": 1, "lines": [(100, 1, 0), (200, 1, 0)],
            "seed": 9}
    for _ in range(8):
        flat.update([base], 0, 20, 0, 0, 0)
        colored.update([{**base, "spectral_gains": ((100.0, 1.0),
                                                     (400.0, .1),
                                                     (1600.0, .01))}],
                       0, 20, 0, 0, 0)
    frequencies = np.fft.rfftfreq(flat._history.size, 1 / flat.sample_rate)
    flat_fft = abs(np.fft.rfft(flat._history))
    colored_fft = abs(np.fft.rfft(colored._history))
    at = lambda spectrum, hz: spectrum[np.argmin(abs(frequencies - hz))]
    assert at(colored_fft, 100) / at(flat_fft, 100) == pytest.approx(1, rel=.02)
    assert at(colored_fft, 200) < .7 * at(flat_fft, 200)
    assert all(isinstance(value, (int, float, tuple))
               for point in colored._spectral_states[(9, 0)] for value in point)
