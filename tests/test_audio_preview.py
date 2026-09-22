"""Deterministic per-unit sonar preview clips (contact-analyzer audio)."""

import numpy as np
import pytest

from src.audio.preview import (PREVIEW_DURATION_S, preview_available,
                               unit_sonar_preview)
from src.data.catalog import CATALOG


def _machine(profile_key: str):
    systems = CATALOG.profile_systems[profile_key]
    return CATALOG.machines[systems.machine_key]


def test_preview_is_deterministic_and_bounded():
    machine = _machine("diesel_alt")
    first = unit_sonar_preview("diesel_alt", machine, "acoustic_cruise", 4096)
    second = unit_sonar_preview("diesel_alt", machine, "acoustic_cruise", 4096)
    np.testing.assert_array_equal(first, second)
    assert first.dtype == np.float32
    assert first.size == int(round(PREVIEW_DURATION_S * 4096))
    assert np.isfinite(first).all()
    assert float(np.max(np.abs(first))) <= 1.0
    # Faded start/end keep the clip free of edge clicks.
    assert float(abs(first[0])) < 1e-3
    assert float(abs(first[-1])) < 1e-3


def test_preview_contains_the_catalog_tonal_lines():
    machine = _machine("diesel_alt")
    clip = unit_sonar_preview("diesel_alt", machine, "acoustic_cruise", 4096)
    assert clip is not None
    spectrum = np.abs(np.fft.rfft(clip * np.hanning(clip.size)))
    hz = 4096.0 / clip.size
    peak_bin = int(np.argmax(spectrum[1:64])) + 1
    peak_hz = peak_bin * hz
    lines = sorted(line.frequency_hz for line in machine.cruise_lines
                   if 0 < line.frequency_hz <= 300)
    assert lines
    assert min(abs(peak_hz - line) for line in lines) < 1.5 * hz
    # The stronger line (level 1.0) must dominate the weaker one (0.5).
    assert spectrum[int(round(8.0 / hz))] > spectrum[int(round(16.0 / hz))]


def test_preview_modes_differ_between_speeds():
    machine = _machine("diesel_alt")
    cruise = unit_sonar_preview("diesel_alt", machine, "acoustic_cruise", 4096)
    high = unit_sonar_preview("diesel_alt", machine, "acoustic_high", 4096)
    assert cruise is not None and high is not None
    assert cruise.shape == high.shape
    assert not np.allclose(cruise, high)
    spectrum = np.abs(np.fft.rfft(high * np.hanning(high.size)))
    hz = 4096.0 / high.size
    peak_bin = int(np.argmax(spectrum[1:64])) + 1
    assert abs(peak_bin * hz - 22.0) < 2.0


def test_preview_resampling_follows_the_output_rate():
    machine = _machine("diesel_alt")
    at_22050 = unit_sonar_preview("diesel_alt", machine, "acoustic_cruise",
                                  22050)
    at_4096 = unit_sonar_preview("diesel_alt", machine, "acoustic_cruise",
                                 4096)
    assert at_22050.size == int(round(PREVIEW_DURATION_S * 22050))
    assert at_4096.size == int(round(PREVIEW_DURATION_S * 4096))
    assert at_22050.size != at_4096.size


def test_preview_unavailable_for_acoustically_empty_profiles():
    machine = _machine("frigate_torp")
    for mode in ("acoustic_cruise", "acoustic_high"):
        assert preview_available(machine, mode) is False
        assert unit_sonar_preview("frigate_torp", machine, mode, 22050) is None


def test_preview_rejects_invalid_output_rate():
    machine = _machine("diesel_alt")
    assert unit_sonar_preview("diesel_alt", machine, "acoustic_cruise", 0) is None
    assert unit_sonar_preview("diesel_alt", machine, "acoustic_cruise", -1) is None
    assert (unit_sonar_preview("diesel_alt", machine, "acoustic_cruise",
                               22050.0) is None)
