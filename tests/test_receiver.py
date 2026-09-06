"""Deterministic, device-free tests of the raw acoustic receiver."""

import numpy as np
import pytest

from src.audio.receiver import AcousticReceiver, smooth_limit
from src.core import config
from src.data.catalog import CATALOG


def source(bearing=0, level=1, lines=None, seed=1234):
    return {"bearing": bearing, "level": level,
            "lines": [(24, .8, 0)] if lines is None else lines, "seed": seed}


def run(sources, bearing=0, width=24, blocks=8, **noise):
    receiver = AcousticReceiver()
    for _ in range(blocks):
        receiver.update(sources, bearing, width, noise.get("own_noise", 0),
                        noise.get("sea_state", 0), noise.get("own_speed", 0))
    return receiver


def test_directional_strength_and_no_agc():
    strong = run([source()])
    opposite = run([source()], bearing=180)
    faint = run([source(level=.05)])
    assert np.std(strong.samples) > 20 * np.std(opposite.samples)
    assert max(strong.spectrum) > 10 * max(faint.spectrum)
    assert max(strong.spectrum) > 20 * max(opposite.spectrum)
    assert strong.demon_analysis is not None
    assert faint.demon_analysis is None
    assert opposite.demon_analysis is None
    assert opposite.peaks == []
    assert strong.broadband[0] > 100 * strong.broadband[90]
    assert strong.broadband == opposite.broadband


def test_wraparound_and_beam_width():
    left = run([source(bearing=359)], bearing=1)
    right = run([source(bearing=1)], bearing=359)
    np.testing.assert_array_equal(left.samples, right.samples)
    wrapped = run([source(bearing=719)], bearing=-359)
    np.testing.assert_array_equal(left.samples, wrapped.samples)
    narrow = run([source(bearing=20)], width=8)
    wide = run([source(bearing=20)], width=80)
    assert np.std(wide.samples) > 20 * np.std(narrow.samples)
    assert left.broadband[0] > left.broadband[90]


def test_all_source_mix_is_additive_and_ignores_identity_metadata():
    a = source(bearing=-3, level=.6, lines=[(32, .7, 0)], seed=19)
    b = source(bearing=4, level=.5, lines=[(73, .8, 0)], seed=59)
    mixed, first, second, noise = run([a, b]), run([a]), run([b]), run([])
    np.testing.assert_allclose(mixed.samples, first.samples + second.samples - noise.samples,
                               atol=3e-8)
    assert any(abs(freq - 32) < .6 for freq, _ in mixed.peaks)
    assert any(abs(freq - 73) < .6 for freq, _ in mixed.peaks)
    a.update(target_id="secret", true_class="sub", selected=True)
    b.update(target_id="other", signature_key="irrelevant")
    np.testing.assert_array_equal(mixed.samples, run([b, a]).samples)


def test_receiver_retains_normal_mix_headroom_before_analysis():
    sources = [source(lines=[(24, 1, 0)], seed=0) for _ in range(8)]
    receiver = run(sources, blocks=1)
    assert np.max(np.abs(receiver.samples)) > 1.0
    assert np.isfinite(receiver.samples).all()


def test_smooth_limiter_is_monotonic_transparent_and_off_the_rails():
    values = np.linspace(-32, 32, 20001)
    limited = smooth_limit(values)
    assert np.all(np.diff(limited) >= 0)
    np.testing.assert_allclose(limited[np.abs(values) <= .75],
                               values[np.abs(values) <= .75], atol=3e-8)
    assert np.max(np.abs(limited)) < 1.0
    assert not np.any(np.abs(limited) == 1.0)
    dirty = smooth_limit([np.nan, np.inf, -np.inf])
    assert np.isfinite(dirty).all()


def test_representative_catalog_mix_keeps_analysis_headroom():
    profiles = [CATALOG.subs["diesel_alt"].acoustic,
                CATALOG.subs["aip_modern"].acoustic,
                CATALOG.surfaces["warship_01"].acoustic,
                CATALOG.surfaces["warship_02"].acoustic]
    sources = []
    for index, profile in enumerate(profiles):
        low, high = profile.tonal_band_hz
        item = source(bearing=index * 3, level=.85,
                      lines=[((low + high) / 2, .8, 0),
                             *profile.secondary_tonals], seed=100 + index)
        if profile.broadband:
            level, low_hz, high_hz = profile.broadband
            item["broadband"] = {"level": level, "low_hz": low_hz,
                                  "high_hz": high_hz}
        sources.append(item)
    receiver = run(sources, width=30, blocks=1, own_noise=.5,
                   sea_state=6, own_speed=18)
    assert np.isfinite(receiver.samples).all()
    assert .1 < np.max(np.abs(receiver.samples)) < 4.0
    assert np.isfinite(receiver.spectrum).all()
    for gain_db in (12, 24):
        playback = smooth_limit(receiver.samples * 10 ** (gain_db / 20) * .55)
        assert np.isfinite(playback).all()
        assert np.max(np.abs(playback)) < 1.0
        assert not np.any(np.abs(playback) == 1.0)


def test_tone_peaks_and_nonuniform_lofar_mapping():
    frequencies = [17.5, 51, 112.5, 187.5, 272.5, 289]
    receiver = run([source(lines=[(freq, .7 if i < 5 else .2, 0)
                                 for i, freq in enumerate(frequencies)])])
    assert len(receiver.peaks) == 5
    for freq in frequencies[:5]:
        assert any(abs(found - freq) <= .5 for found, _ in receiver.peaks)
        index = min(range(config.LOFAR_BINS), key=lambda i: abs(config.lofar_bin_freq(i) - freq))
        assert receiver.spectrum[index] > .5
    assert all(earlier[1] >= later[1] for earlier, later in zip(receiver.peaks, receiver.peaks[1:]))


def test_peak_at_upper_lofar_boundary():
    receiver = run([source(lines=[(300, .8, 0)])])
    assert receiver.peaks[0][0] == 300
    assert receiver.spectrum[-1] > .75
    assert receiver.demon_analysis is None


@pytest.mark.parametrize("rate", [2, 10, 23.5, 60, 80])
def test_demon_measures_known_am_audio_without_source_descriptors(rate):
    receiver = AcousticReceiver()
    t = np.arange(receiver.sample_rate * 2) / receiver.sample_rate
    samples = .12 * (1 + .65 * np.sin(2 * np.pi * rate * t)) * np.sin(2 * np.pi * 700 * t)
    receiver._analyze(samples)
    result = receiver.demon_analysis
    assert result is not None
    assert abs(result["blade_rate_hz"] - rate) <= .5
    assert result["rpm_candidates"] == tuple(round(rate * 60 / n, 1) for n in (3, 4, 5, 6, 7))
    assert .35 < result["confidence"] <= 1
    assert 0 <= result["cavitation"] <= 1
    assert result["tonal_hz"] is None
    assert abs(np.argmax(receiver.demon_spectrum) + 1 - rate) <= 1


def test_synthesized_modulation_is_illustrative_first_line_not_strongest():
    receiver = run([source(lines=[(12, .5, 0), (47, .9, 0)])])
    assert receiver.demon_analysis["blade_rate_hz"] == 12
    assert receiver.demon_analysis["tonal_hz"] == 47
    fft = abs(np.fft.rfft(receiver.samples))
    assert fft[175] > 10  # 700 Hz carrier is present in playable samples.
    assert run([source(lines=[(120, .8, 0)])]).demon_analysis is None
    assert run([source(lines=[(12, .8, 20)])]).demon_analysis is None


@pytest.mark.parametrize("kind", ["silence", "noise", "low_tone", "carrier", "faint_am"])
def test_demon_rejects_unmodulated_or_insufficient_audio(kind):
    receiver = AcousticReceiver()
    t = np.arange(receiver.sample_rate * 2) / receiver.sample_rate
    samples = {
        "silence": np.zeros(t.size),
        "noise": np.random.default_rng(23).normal(0, .15, t.size),
        "low_tone": .3 * np.sin(2 * np.pi * 23.7 * t),
        "carrier": .2 * np.sin(2 * np.pi * 700.3 * t),
        "faint_am": .002 * (1 + .7 * np.sin(2 * np.pi * 12 * t)) * np.sin(2 * np.pi * 700 * t),
    }[kind]
    receiver._analyze(samples)
    assert receiver.demon_analysis is None
    if kind in ("silence", "carrier", "faint_am"):
        assert receiver.peaks == []


def test_noise_only_not_identified_even_at_high_noise_and_speed():
    receiver = AcousticReceiver()
    for i in range(80):
        receiver.update([], 0, 30, 1, 9, 30)
        assert receiver.demon_analysis is None
    assert any(abs(freq - 67) <= .5 for freq, _ in receiver.peaks)
    assert run([]).peaks == []


def test_warmup_bounded_history_and_reset_replay():
    receiver = AcousticReceiver(seed=11)
    first = None
    for i in range(100):
        receiver.update([source()], 0, 30, .1, 2, 0)
        if i == 0:
            first = receiver.samples.copy()
        if i < 3:
            assert receiver.demon_analysis is None
        assert receiver.sequence == i + 1
        assert receiver.elapsed == (i + 1) * .25
        assert receiver.samples.shape == (1024,)
        assert receiver.samples.dtype == np.float32
        assert np.isfinite(receiver.samples).all()
        assert max(abs(receiver.samples)) <= 8
        assert receiver._history.shape == (8192,)
        assert receiver._filled <= 8192
        for values, count in ((receiver.spectrum, 110), (receiver.broadband, 180),
                              (receiver.demon_spectrum, 80)):
            assert isinstance(values, list) and len(values) == count
            assert all(np.isfinite(v) and 0 <= v <= 1 for v in values)
    assert receiver.demon_analysis is not None
    receiver.reset()
    assert receiver.sequence == 101
    assert receiver.elapsed == 0
    assert receiver.seed == 11
    assert not np.any(receiver.samples) and not np.any(receiver._history)
    assert not any(receiver.spectrum + receiver.broadband + receiver.demon_spectrum)
    assert receiver.peaks == [] and receiver.demon_analysis is None
    receiver.update([source()], 0, 30, .1, 2, 0)
    np.testing.assert_array_equal(receiver.samples, first)


def test_history_expires_when_sources_disappear():
    receiver = run([source()])
    for _ in range(8):
        receiver.update([], 0, 24, 0, 0, 0)
    assert receiver.peaks == []
    assert receiver.demon_analysis is None


def test_identical_seeds_and_continuous_tone_phase():
    a, b = AcousticReceiver(9), AcousticReceiver(9)
    noise = AcousticReceiver(9)
    blocks = []
    for _ in range(12):
        for receiver in (a, b):
            receiver.update([source(lines=[(123.25, .8, 0)], seed=0)], 0, 20, 0, 0, 0)
        noise.update([], 0, 20, 0, 0, 0)
        np.testing.assert_array_equal(a.samples, b.samples)
        assert a.spectrum == b.spectrum and a.demon_analysis == b.demon_analysis
        blocks.append(a.samples - noise.samples)
    t = np.arange(12 * 1024) / 4096
    np.testing.assert_allclose(np.concatenate(blocks), .2 * np.sin(2 * np.pi * 123.25 * t), atol=2e-8)
    other = AcousticReceiver(10)
    other.update([], 0, 20, 0, 0, 0)
    assert not np.array_equal(noise.samples, other.samples)


def test_nonfinite_inputs_and_overload_are_bounded():
    receiver = run([None, {}, source(bearing=float("nan")),
                    source(lines=[None, (float("inf"), 1, 0), (10, float("nan"), 2),
                                  (-4, 1, 0), (600, 1, 0), (12, 1, float("nan"))]),
                    source(level=float("inf")), source(lines=None)],
                   bearing=float("inf"), width=float("nan"), own_noise=float("nan"),
                   sea_state=float("inf"), own_speed=-99)
    assert np.isfinite(receiver.samples).all()
    overloaded = run([source(seed=i) for i in range(100)], width=-1, own_noise=999, sea_state=999)
    assert np.isfinite(overloaded.samples).all()
    assert np.max(np.abs(overloaded.samples)) <= 8
    assert all(0 <= value <= 1 for value in overloaded.spectrum + overloaded.broadband)
    receiver._analyze(np.full(8192, np.nan))
    assert receiver.demon_analysis is None and receiver.peaks == []
    assert not any(receiver.spectrum + receiver.demon_spectrum)


def test_broadband_sources_have_independent_deterministic_noise():
    a = source(seed=11, lines=[])
    b = source(seed=29, lines=[])
    for item in (a, b):
        item["broadband"] = {"level": .8, "low_hz": 100, "high_hz": 700}
    mixed = run([a, b], blocks=1)
    first = run([a], blocks=1)
    second = run([b], blocks=1)
    background = run([], blocks=1)
    np.testing.assert_allclose(mixed.samples,
                               first.samples + second.samples - background.samples,
                               atol=3e-8)
    assert not np.array_equal(first.samples, second.samples)
    np.testing.assert_array_equal(mixed.samples, run([b, a], blocks=1).samples)
