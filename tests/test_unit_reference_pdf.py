import re
import zlib

import numpy as np

from tools.gen_unit_reference_pdf import (DEFAULT_LANG, P_DEMON,
                                          P_DEMON_TRACE, P_LEFT, P_LOFAR,
                                          P_LOFAR_TRACE, P_RIGHT, PRINT_SIZE,
                                          _ESM_BORDER, _ESM_SPECTRUM,
                                          _ESM_WAVEFORM, _PEAK, build_pdf,
                                          check, generate, print_acoustic_plot,
                                          print_radar_plot)

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
        {"cruise_lines": [], "cruise_broadband": None}, "cruise"))
    light = np.all(pixels >= 235, axis=2)
    # A print diagram must be overwhelmingly light - the opposite of the dark
    # on-screen theme - to keep printer ink use low, per the request that
    # motivated this: no black background, numbers must stay legible.
    assert light.mean() > 0.85
    assert not np.any(np.all(pixels == (0, 0, 0), axis=2))
    radar = _decode(print_radar_plot([{"frequency_band_hz": [9e9, 9.5e9],
                                       "prf_band_hz": [500, 2000],
                                       "modulation_codes": ["pulse"]}]))
    assert np.all(radar >= 235, axis=2).mean() > 0.85


def lofar_x(frequency):
    return P_LEFT + round(frequency / 300.0 * (P_RIGHT - P_LEFT))


def test_print_acoustic_plot_is_the_station_screen_with_measured_values():
    pixels = _decode(print_acoustic_plot(
        {"cruise_lines": [[20.0, 1.0, .2], [150.0, .8, .5]],
         "cruise_broadband": None}, "cruise")).astype(int)
    newest = pixels[P_LOFAR[1] + 2, P_LEFT + 2:P_RIGHT - 2].sum(axis=1)
    for frequency in (20.0, 150.0):
        x = lofar_x(frequency) - P_LEFT - 2
        # Dark ink where the receiver measured a tonal, paper elsewhere.
        assert newest[x - 3:x + 4].min() < np.median(newest) - 150, frequency
        strip = pixels[P_LOFAR_TRACE[1]:P_LOFAR_TRACE[1] + P_LOFAR_TRACE[3],
                       lofar_x(frequency) - 40:lofar_x(frequency) + 40]
        assert np.any(np.all(strip == _PEAK, axis=2)), frequency
    demon = pixels[P_DEMON_TRACE[1]:P_DEMON[1] + P_DEMON[3]]
    assert np.any(np.all(demon == _PEAK, axis=2))
    silent = _decode(print_acoustic_plot(
        {"cruise_lines": [], "cruise_broadband": None}, "cruise"))
    assert not np.any(np.all(silent == _PEAK, axis=2))


def test_print_radar_plot_draws_fingerprints_per_emitter_and_modulation():
    emitters = [
        {"frequency_band_hz": [1e9, 2e9], "prf_band_hz": [200, 400],
         "modulation_codes": ["pulse"]},
        {"frequency_band_hz": [8e9, 12e9], "prf_band_hz": None,
         "modulation_codes": ["frequency_agile", "continuous_wave"]},
    ]
    pixels = _decode(print_radar_plot(emitters))
    row_h = (PRINT_SIZE[1] - 8) // len(emitters)
    for index, emitter in enumerate(emitters):
        top = 4 + index * row_h
        row = pixels[top + row_h // 2]
        border = np.all(row == _ESM_BORDER, axis=1)
        runs = int(np.sum(border[1:] & ~border[:-1]) + border[0])
        assert runs == 2 * len(emitter["modulation_codes"]), index
        region = pixels[top:top + row_h]
        assert np.any(np.all(region == _ESM_SPECTRUM, axis=2))
        assert np.any(np.all(region[:, :200] == _ESM_WAVEFORM, axis=2)) == (
            emitter["prf_band_hz"] is not None)
