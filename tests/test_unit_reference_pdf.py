import re
import zlib

import numpy as np

from tools.gen_unit_reference_pdf import (DEFAULT_LANG, PRINT_SIZE,
                                          ROW_COLORS, build_pdf, check,
                                          generate, print_acoustic_plot,
                                          print_radar_plot, radar_prf_x,
                                          radar_spectral_x, spectral_x)

MAX_PDF_BYTES = 32 * 1024 * 1024  # print reference, not a runtime asset - still bounded


def _decode(rgb):
    width, height = PRINT_SIZE
    return np.frombuffer(rgb, dtype=np.uint8).reshape(height, width, 3)


def test_pdf_is_well_formed_and_bounded():
    payload = build_pdf(DEFAULT_LANG)
    assert payload.startswith(b"%PDF-1.4\n")
    assert payload.endswith(b"%%EOF")
    assert 0 < len(payload) <= MAX_PDF_BYTES
    trailer = payload.rsplit(b"trailer", 1)[-1]
    assert b"/Root 1 0 R" in trailer
    startxref = int(payload.rsplit(b"startxref\n", 1)[-1].split(b"\n", 1)[0])
    assert 0 < startxref < len(payload)
    page_count = payload.count(b"/Type /Page /Parent")
    assert page_count > 1
    assert payload.count(b"/Type /Pages /Kids [ ") == 1
    assert f"/Count {page_count} ".encode("ascii") in payload


def test_two_generations_are_byte_identical():
    first = build_pdf(DEFAULT_LANG)
    second = build_pdf(DEFAULT_LANG)
    assert first == second


def test_english_and_german_both_generate_distinct_valid_documents():
    en = build_pdf("en")
    de = build_pdf("de")
    assert en.startswith(b"%PDF-1.4\n") and en.endswith(b"%%EOF")
    assert de.startswith(b"%PDF-1.4\n") and de.endswith(b"%%EOF")
    assert en != de
    # Both cover the same catalog, so page counts must match exactly.
    assert en.count(b"/Type /Page /Parent") == de.count(b"/Type /Page /Parent")


def test_embedded_images_are_valid_flate_rgb_xobjects_at_the_print_resolution():
    payload = build_pdf(DEFAULT_LANG)
    width, height = PRINT_SIZE
    found = False
    for match in re.finditer(
            rb"/Type /XObject /Subtype /Image /Width (\d+) /Height (\d+) "
            rb"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode "
            rb"/Length (\d+) >>\nstream\n", payload):
        found = True
        found_width, found_height, length = (int(group) for group in match.groups())
        assert (found_width, found_height) == (width, height)
        start = match.end()
        data = payload[start:start + length]
        assert payload[start + length:start + length + len(b"\nendstream")] == b"\nendstream"
        assert len(zlib.decompress(data)) == width * height * 3
    assert found


def test_generate_writes_atomically_and_check_is_deterministic_and_read_only(tmp_path):
    output = tmp_path / "nested" / "reference.pdf"
    payload = generate(output, DEFAULT_LANG)
    assert output.read_bytes() == payload
    assert not output.with_suffix(output.suffix + ".tmp").exists()
    assert check(output, DEFAULT_LANG) == 0
    before = output.read_bytes()
    assert check(output, DEFAULT_LANG) == 0
    assert output.read_bytes() == before


def test_print_diagrams_are_white_background_and_ink_sparing():
    pixels = _decode(print_acoustic_plot(
        {"cruise_lines": [], "cruise_broadband": None,
         "shaft_rpm": None, "blade_count": None}, "cruise"))
    white = np.all(pixels == (255, 255, 255), axis=2)
    # A print diagram must be overwhelmingly white - the opposite of the dark
    # on-screen theme - to keep printer ink use low, per the request that
    # motivated this: no black background, numbers must stay legible.
    assert white.mean() > 0.9
    assert not np.any(np.all(pixels == (0, 0, 0), axis=2))


def test_print_axis_helpers_map_the_fixed_bounds_to_the_shared_plot_edges():
    from tools.gen_unit_reference_pdf import P_LEFT, P_RIGHT
    assert spectral_x(5) == P_LEFT
    assert spectral_x(10_000) == P_RIGHT
    assert radar_spectral_x(0.5e9) == P_LEFT
    assert radar_spectral_x(18e9) == P_RIGHT
    assert radar_prf_x(100.0) == P_LEFT
    assert radar_prf_x(10_000.0) == P_RIGHT


def test_print_acoustic_plot_traces_tonals_without_a_filled_peak():
    machine = {
        "cruise_lines": [[100, .8, 2]], "cruise_broadband": [.3, 20, 40],
        "shaft_rpm": [60, 120], "blade_count": 4,
    }
    pixels = _decode(print_acoustic_plot(machine, "cruise", include_hypotheses=True))
    from tools.gen_unit_reference_pdf import (P_DEMON_BOTTOM, P_DEMON_TOP,
                                              P_SPECTRAL_BOTTOM, P_TOP,
                                              _SHAFT_COLOR, _TONAL)
    peak_x = spectral_x(100)
    peak_y = P_SPECTRAL_BOTTOM - round((P_SPECTRAL_BOTTOM - P_TOP) * .8)
    assert np.any(np.all(pixels[max(0, peak_y - 1):peak_y + 2,
                                max(0, peak_x - 2):peak_x + 3] == _TONAL, axis=2))
    assert np.any(np.all(pixels[P_DEMON_TOP:P_DEMON_BOTTOM] == _SHAFT_COLOR, axis=2))


def test_print_radar_plot_draws_one_row_per_listed_emitter_and_skips_missing_prf():
    from tools.gen_unit_reference_pdf import P_DEMON_BOTTOM, P_DEMON_TOP
    emitters = [
        {"frequency_band_hz": [1e9, 2e9], "prf_band_hz": [200, 400]},
        {"frequency_band_hz": [8e9, 12e9], "prf_band_hz": None},
        {"frequency_band_hz": [12e9, 18e9], "prf_band_hz": [1000, 5000]},
    ]
    pixels = _decode(print_radar_plot(emitters))
    for index, emitter in enumerate(emitters):
        color = ROW_COLORS[index % len(ROW_COLORS)]
        x0 = radar_spectral_x(emitter["frequency_band_hz"][0])
        x1 = radar_spectral_x(emitter["frequency_band_hz"][1])
        assert np.any(np.all(pixels[:, x0:x1 + 1] == color, axis=2)), index
    assert np.any(np.all(pixels[P_DEMON_TOP:P_DEMON_BOTTOM] == ROW_COLORS[0], axis=2))
    assert np.any(np.all(pixels[P_DEMON_TOP:P_DEMON_BOTTOM] == ROW_COLORS[2], axis=2))
    assert not np.any(np.all(pixels[P_DEMON_TOP:P_DEMON_BOTTOM] == ROW_COLORS[1], axis=2))
