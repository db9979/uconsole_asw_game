import hashlib
import json
import struct
import zlib

import numpy as np
import pytest

from tools.gen_contact_analysis_images import (DEMON_RECT, DEMON_TRACE_RECT,
                                               ESM_BORDER, ESM_SPECTRUM,
                                               ESM_WAVEFORM, LABEL_COLOR,
                                               LOFAR_RECT, PLOT_LEFT, PLOT_RIGHT,
                                               LOFAR_TRACE_RECT, SCREEN_AMBER,
                                               VALUE_COLOR, _format_hz, _plot,
                                               _radar_plot, check, generate)
from src.data.contact_analysis import project_contact_catalog


def decode(payload):
    width, height = struct.unpack(">II", payload[16:24])
    offset, raw = 8, b""
    while offset < len(payload):
        size = struct.unpack(">I", payload[offset:offset + 4])[0]
        kind = payload[offset + 4:offset + 8]
        if kind == b"IDAT":
            raw += payload[offset + 8:offset + 8 + size]
        offset += size + 12
    rows = zlib.decompress(raw)
    assert all(rows[y * (width * 3 + 1)] == 0 for y in range(height))
    pixels = np.frombuffer(rows, dtype=np.uint8).reshape(height, width * 3 + 1)[:, 1:]
    return pixels.reshape(height, width, 3)


def test_two_generations_are_byte_identical_and_manifest_hashes_match(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    generate(first)
    generate(second)
    first_files = {path.name: path.read_bytes() for path in first.iterdir()}
    second_files = {path.name: path.read_bytes() for path in second.iterdir()}
    assert first_files == second_files
    manifest = json.loads(first_files["manifest.json"])
    assert manifest["version"] == 1
    assert len(manifest["assets"]) == 337  # +109: new radar/ESM fingerprint kind
    assert sum(item["kind"] == "acoustic_cruise"
               for item in manifest["assets"]) == 114
    assert sum(item["kind"] == "acoustic_high"
               for item in manifest["assets"]) == 114
    assert sum(item["kind"] == "radar"
               for item in manifest["assets"]) == 109
    assert "silhouette" not in json.dumps(manifest)
    for asset in manifest["assets"]:
        payload = first_files[asset["filename"]]
        assert payload.startswith(b"\x89PNG\r\n\x1a\n")
        assert asset["route"] == "/contact-analysis/" + asset["filename"]
        assert asset["bytes"] == len(payload)
        assert asset["sha256"] == hashlib.sha256(payload).hexdigest()


def lofar_x(frequency):
    return PLOT_LEFT + round(frequency / 300.0 * (PLOT_RIGHT - PLOT_LEFT))


def demon_x(frequency):
    return PLOT_LEFT + round(frequency / 50.0 * (PLOT_RIGHT - PLOT_LEFT))


def machine(lines, broadband=None):
    return {"cruise_lines": lines, "cruise_broadband": broadband}


def test_acoustic_images_are_station_lofar_and_demon_screens(tmp_path):
    output = tmp_path / "assets"
    generate(output)
    profiles = project_contact_catalog()["profiles"]
    checked = 0
    for profile in profiles:
        for kind, field in (("acoustic_cruise", "cruise_lines"),
                            ("acoustic_high", "high_speed_lines")):
            lines = [line for line in profile["machine"][field] if line[0] <= 295]
            if kind not in profile["assets"] or not lines:
                continue
            pixels = decode((output / profile["assets"][kind].rsplit("/", 1)[-1])
                            .read_bytes()).astype(int)
            newest = pixels[LOFAR_RECT[1] + 1, PLOT_LEFT:PLOT_RIGHT + 1, 1]
            strongest = max(lines, key=lambda line: line[1])
            column = lofar_x(strongest[0]) - PLOT_LEFT
            # The receiver's strongest catalog tonal is a bright vertical
            # trace in the newest waterfall row, well above the noise floor.
            assert newest[max(0, column - 2):column + 3].max() > 2 * np.median(newest) + 10, \
                (profile["key"], kind, strongest)
            checked += 1
    assert checked > 150


def test_lofar_trace_position_and_demon_peak_follow_the_receiver():
    pixels = decode(_plot(machine([[20.0, 1.0, 0.2], [150.0, .8, .5]]), "cruise")).astype(int)
    newest = pixels[LOFAR_RECT[1] + 1, :, 1]
    for frequency in (20.0, 150.0):
        x = lofar_x(frequency)
        assert newest[x - 2:x + 3].max() > 3 * np.median(newest[PLOT_LEFT:PLOT_RIGHT]), frequency
    # A narrow first tonal in 2-80 Hz modulates the carrier, so the station's
    # DEMON analysis measures a peak there and marks it in amber.
    amber = np.all(pixels[DEMON_TRACE_RECT[1]:DEMON_RECT[1] + DEMON_RECT[3]]
                   == SCREEN_AMBER, axis=2)
    assert np.any(amber[:, demon_x(20.0) - 1:demon_x(20.0) + 2])

    broadband_only = decode(_plot(machine([], [.5, 20.0, 400.0]), "cruise"))
    assert not np.any(np.all(broadband_only == SCREEN_AMBER, axis=2))
    silent = decode(_plot(machine([]), "cruise")).astype(int)
    band = broadband_only.astype(int)[LOFAR_RECT[1] + 1, PLOT_LEFT:PLOT_RIGHT, 1]
    quiet = silent[LOFAR_RECT[1] + 1, PLOT_LEFT:PLOT_RIGHT, 1]
    assert band.mean() > quiet.mean() + 3


def test_measured_peak_frequencies_are_written_into_the_image():
    pixels = decode(_plot(machine([[20.0, 1.0, 0.2], [150.0, .8, .5]]), "cruise"))
    strip = pixels[LOFAR_TRACE_RECT[1]:LOFAR_TRACE_RECT[1] + LOFAR_TRACE_RECT[3]]
    value = np.all(strip == VALUE_COLOR, axis=2)
    for frequency in (20.0, 150.0):
        x = lofar_x(frequency)
        assert np.any(value[:, x - 6:x + 7]), frequency
    # The DEMON value label sits beside the amber measured-peak line.
    demon = pixels[DEMON_TRACE_RECT[1]:DEMON_TRACE_RECT[1] + DEMON_TRACE_RECT[3]]
    amber = np.all(demon == SCREEN_AMBER, axis=2)
    x = demon_x(20.0)
    assert np.any(amber[:, x + 3:x + 20])
    silent = decode(_plot(machine([]), "cruise"))
    assert not np.any(np.all(silent == VALUE_COLOR, axis=2))


def test_acoustic_images_label_both_linear_axes():
    pixels = decode(_plot(machine([]), "cruise"))
    label = np.array(LABEL_COLOR)
    for rect, count in ((LOFAR_RECT, 7), (DEMON_RECT, 6)):
        y = rect[1] + rect[3] + 3
        for index in range(count):
            x = PLOT_LEFT + round(index * (PLOT_RIGHT - PLOT_LEFT) / (count - 1))
            nearby = pixels[y:y + 5, max(0, x - 12):min(320, x + 12)]
            assert np.any(np.all(nearby == label, axis=2)), (rect, index)


def test_check_accepts_exact_set_and_rejects_missing_extra_modified(tmp_path):
    output = tmp_path / "assets"
    generate(output)
    (output / "__init__.py").write_text("", encoding="ascii")
    assert check(output) == 0

    png = next(output.glob("*.png"))
    original = png.read_bytes()
    png.unlink()
    assert check(output) == 1
    png.write_bytes(original)

    (output / "extra.png").write_bytes(original)
    assert check(output) == 1
    (output / "extra.png").unlink()

    png.write_bytes(original + b"changed")
    assert check(output) == 1


def test_packaged_assets_are_exact_and_check_is_read_only(tmp_path):
    packaged = tmp_path / "packaged"
    generate(packaged)
    (packaged / "__init__.py").write_text("", encoding="ascii")
    before = {path.name: (path.read_bytes(), path.stat().st_mtime_ns)
              for path in packaged.iterdir()}
    assert check(packaged) == 0
    after = {path.name: (path.read_bytes(), path.stat().st_mtime_ns)
             for path in packaged.iterdir()}
    assert after == before


def test_generate_and_check_reject_symlinked_assets(tmp_path):
    output = tmp_path / "assets"
    generate(output)
    png = next(output.glob("*.png"))
    target = tmp_path / "outside.png"
    target.write_bytes(b"outside")
    png.unlink()
    png.symlink_to(target)

    assert check(output) == 1
    with pytest.raises(ValueError, match="unsafe output entry"):
        generate(output)
    assert target.read_bytes() == b"outside"


def fingerprint_boxes(pixels, row):
    """Count ESM border runs (box edges) crossing one pixel row."""
    border = np.all(pixels[row] == ESM_BORDER, axis=1)
    return int(np.sum(border[1:] & ~border[:-1]) + border[0]) // 2


def test_radar_plot_draws_eloka_fingerprints_per_emitter_and_modulation():
    emitters = [
        {"frequency_band_hz": [1e9, 2e9], "prf_band_hz": [200, 400],
         "modulation_codes": ["pulse"]},
        {"frequency_band_hz": [8e9, 12e9], "prf_band_hz": None,
         "modulation_codes": ["frequency_agile", "continuous_wave"]},
        {"frequency_band_hz": [12e9, 18e9], "prf_band_hz": [1000, 5000],
         "modulation_codes": ["pulse_doppler"]},
    ]
    pixels = decode(_radar_plot(emitters))
    row_h = (180 - 4) // len(emitters)
    for index, emitter in enumerate(emitters):
        top, bottom = 2 + index * row_h, 2 + (index + 1) * row_h
        middle = top + row_h // 2
        assert fingerprint_boxes(pixels, middle) == len(emitter["modulation_codes"])
        region = pixels[top + 9:bottom, 62:]
        assert np.any(np.all(region == ESM_SPECTRUM, axis=2)), index
        assert np.any(np.all(region == ESM_WAVEFORM, axis=2)), index
        labels = pixels[top:bottom, :60]
        assert np.any(np.all(labels == ESM_SPECTRUM, axis=2)), index
        # The PRF label is drawn only when the catalog supplies a PRF band.
        assert np.any(np.all(labels == ESM_WAVEFORM, axis=2)) == (
            emitter["prf_band_hz"] is not None), index


def test_radar_fingerprints_are_headed_by_the_reference_rf_and_prf():
    with_prf = decode(_radar_plot([{"frequency_band_hz": [9e9, 9.5e9],
                                    "prf_band_hz": [500, 2000],
                                    "modulation_codes": ["pulse"]}]))
    without = decode(_radar_plot([{"frequency_band_hz": [9e9, 9.5e9],
                                   "prf_band_hz": None,
                                   "modulation_codes": ["pulse"]}]))
    for pixels in (with_prf, without):
        assert np.any(np.all(pixels[3:10, 62:200] == ESM_SPECTRUM, axis=2))
    assert np.any(np.all(with_prf[3:10, 200:] == ESM_WAVEFORM, axis=2))
    assert not np.any(np.all(without[3:10, 200:] == ESM_WAVEFORM, axis=2))


def test_radar_plot_single_emitter_uses_the_whole_image_and_compact_labels():
    pixels = decode(_radar_plot([{"frequency_band_hz": [9e9, 9.5e9],
                                  "prf_band_hz": [500, 2000],
                                  "modulation_codes": ["pulse"]}]))
    assert fingerprint_boxes(pixels, 90) == 1
    assert np.any(np.all(pixels[150:175, 62:] == ESM_WAVEFORM, axis=2))
    assert (_format_hz(9.0), _format_hz(9.5), _format_hz(300.0),
            _format_hz(1200.0), _format_hz(5000.0)) == ("9", "9.5", "300", "1.2k", "5k")
