import hashlib
import json
import struct
import zlib

import numpy as np
import pytest

from tools.gen_contact_analysis_images import (_plot, check, generate,
                                               spectral_x)
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
    assert len(manifest["assets"]) == 226
    assert sum(item["kind"] == "acoustic_cruise"
               for item in manifest["assets"]) == 113
    assert sum(item["kind"] == "acoustic_high"
               for item in manifest["assets"]) == 113
    assert "silhouette" not in json.dumps(manifest)
    for asset in manifest["assets"]:
        payload = first_files[asset["filename"]]
        assert payload.startswith(b"\x89PNG\r\n\x1a\n")
        assert asset["route"] == "/contact-analysis/" + asset["filename"]
        assert asset["bytes"] == len(payload)
        assert asset["sha256"] == hashlib.sha256(payload).hexdigest()


def test_composite_diagrams_have_fixed_log_spectrum_and_separate_demon_hypotheses(tmp_path):
    output = tmp_path / "assets"
    generate(output)
    manifest = json.loads((output / "manifest.json").read_text())
    images = [decode((output / item["filename"]).read_bytes())
              for item in manifest["assets"]]
    # Every diagram has the fixed 5 Hz-10 kHz grid and separated hypothesis boundary.
    for pixels in images[::37]:
        for x in (24, 50, 136, 222, 308):
            assert np.any(pixels[10:113, x] != (8, 17, 24))
        assert np.any(pixels[134] != (8, 17, 24))
        assert not np.any(np.all(pixels[113:134] == (229, 174, 71), axis=2))
    assert any(np.any(np.all(pixels[134:170] == (229, 174, 71), axis=2))
               for pixels in images)
    assert any(np.any(np.all(pixels[:113] == (42, 137, 145), axis=2))
               for pixels in images)

    profiles = {profile["key"]: profile for profile in project_contact_catalog()["profiles"]}
    manifest_by_name = {item["filename"]: item for item in manifest["assets"]}
    profile = next(item for item in profiles.values()
                   if item["machine"]["cruise_lines"]
                   and item["machine"]["cruise_broadband"] is not None)
    pixels = decode((output / manifest_by_name[
        profile["assets"]["acoustic_cruise"].rsplit("/", 1)[-1]]["filename"]).read_bytes())
    frequency = profile["machine"]["cruise_lines"][0][0]
    expected_x = spectral_x(frequency)
    assert np.any(np.all(pixels[:113, max(0, expected_x - 3):expected_x + 4]
                         == (115, 220, 194), axis=2))
    broadband = profile["machine"]["cruise_broadband"]
    x0 = spectral_x(broadband[1])
    x1 = spectral_x(broadband[2])
    assert np.any(np.all(pixels[:113, x0:x1 + 1] == (42, 137, 145), axis=2))

    no_demon = next(item for item in profiles.values()
                    if item["machine"]["shaft_rpm"] is None
                    and "acoustic_cruise" in item["assets"])
    no_demon_pixels = decode((output / no_demon["assets"]["acoustic_cruise"].rsplit(
        "/", 1)[-1]).read_bytes())
    assert not np.any(np.all(no_demon_pixels[134:170] == (77, 190, 219), axis=2))
    assert not np.any(np.all(no_demon_pixels[134:170] == (229, 174, 71), axis=2))


def test_every_profiles_tonal_columns_are_exact_and_distinct(tmp_path):
    output = tmp_path / "assets"
    generate(output)
    profiles = project_contact_catalog()["profiles"]
    assert {frequency: spectral_x(frequency)
            for frequency in (6, 8, 8.5, 9.75)} == {
                6: 31, 8: 42, 8.5: 44, 9.75: 49,
            }
    for profile in profiles:
        for kind, field in (("acoustic_cruise", "cruise_lines"),
                            ("acoustic_high", "high_speed_lines")):
            lines = profile["machine"][field]
            columns = [spectral_x(line[0]) for line in lines]
            assert len(columns) == len(set(columns)), (profile["key"], field)
            if not lines:
                continue
            pixels = decode((output / profile["assets"][kind].rsplit("/", 1)[-1]).read_bytes())
            for frequency, column in zip((line[0] for line in lines), columns):
                assert np.any(np.all(pixels[10:113, column] == (115, 220, 194), axis=1)), \
                    (profile["key"], field, frequency, column)


def test_tonal_records_are_discrete_max_composed_peaks_and_hypotheses_appear_once():
    machine = {
        "cruise_lines": [[10, .4, 1], [10.2, .8, 1], [100, .7, 2]],
        "high_speed_lines": [[10, .4, 1], [100, .7, 2]],
        "cruise_broadband": [.3, 20, 40],
        "high_speed_broadband": None,
        "shaft_rpm": [60, 120],
        "blade_count": 4,
    }
    cruise = decode(_plot(machine, "cruise", include_hypotheses=True))
    high = decode(_plot(machine, "high_speed", include_hypotheses=False))
    midpoint = (spectral_x(10) + spectral_x(100)) // 2
    tonal_colors = ((115, 220, 194), (42, 115, 104), (89, 181, 166))
    assert not any(np.any(np.all(cruise[10:112, midpoint] == color, axis=1))
                   for color in tonal_colors)
    assert not np.any(np.all(cruise[:113] == (89, 181, 166), axis=2))
    overlap = spectral_x(10.2)
    composed_y = 112 - round((112 - 10) * .8)
    assert np.array_equal(cruise[composed_y, overlap], (115, 220, 194))
    assert np.any(np.all(cruise[134:170] == (77, 190, 219), axis=2))
    assert np.any(np.all(cruise[134:170] == (229, 174, 71), axis=2))
    assert not np.any(np.all(high[134:170] == (77, 190, 219), axis=2))
    assert not np.any(np.all(high[134:170] == (229, 174, 71), axis=2))


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
