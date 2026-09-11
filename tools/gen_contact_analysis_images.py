"""Generate deterministic, font-free contact-analysis PNG resources."""

import argparse
import binascii
import hashlib
import json
import math
import os
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.contact_analysis import project_contact_catalog  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "contact_analysis"
PLOT_SIZE = (320, 180)
GENERATED_SUFFIXES = (".png", ".json")
SPECTRUM_MIN_HZ = 5.0
SPECTRUM_MAX_HZ = 10_000.0
PLOT_LEFT = 24
PLOT_RIGHT = PLOT_SIZE[0] - 12


def _chunk(kind, payload):
    return (struct.pack(">I", len(payload)) + kind + payload
            + struct.pack(">I", binascii.crc32(kind + payload) & 0xffffffff))


def _png(width, height, pixels):
    raw = b"".join(b"\x00" + bytes(pixels[y * width * 3:(y + 1) * width * 3])
                   for y in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header)
            + _chunk(b"IDAT", zlib.compress(raw, level=9)) + _chunk(b"IEND", b""))


def _canvas(width, height, color=(8, 17, 24)):
    return bytearray(color * (width * height))


def _pixel(pixels, width, height, x, y, color):
    if 0 <= x < width and 0 <= y < height:
        index = (y * width + x) * 3
        pixels[index:index + 3] = bytes(color)


def _line(pixels, width, height, x0, y0, x1, y1, color):
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    error = dx + dy
    while True:
        _pixel(pixels, width, height, x0, y0, color)
        if x0 == x1 and y0 == y1:
            return
        twice = 2 * error
        if twice >= dy:
            error += dy
            x0 += sx
        if twice <= dx:
            error += dx
            y0 += sy


def spectral_x(frequency):
    """Map a frequency to the fixed comparable logarithmic plot column."""
    frequency = max(SPECTRUM_MIN_HZ, min(SPECTRUM_MAX_HZ, frequency))
    span = math.log10(SPECTRUM_MAX_HZ / SPECTRUM_MIN_HZ)
    return PLOT_LEFT + round((PLOT_RIGHT - PLOT_LEFT)
                             * math.log10(frequency / SPECTRUM_MIN_HZ) / span)


def _plot(machine, speed, *, include_hypotheses=False):
    width, height = PLOT_SIZE
    pixels = _canvas(width, height)
    left, right, top, spectral_bottom = PLOT_LEFT, PLOT_RIGHT, 10, 112
    demon_top, demon_bottom = 134, 169
    lines = machine[f"{speed}_lines"]
    broadband = machine[f"{speed}_broadband"]

    for step in range(5):
        y = top + (spectral_bottom - top) * step // 4
        _line(pixels, width, height, left, y, right, y, (22, 48, 58))
    for frequency in (5, 10, 100, 1000, 10000):
        x = spectral_x(frequency)
        _line(pixels, width, height, x, top, x, spectral_bottom, (18, 41, 50))
    if broadband is not None:
        x0, x1 = spectral_x(broadband[1]), spectral_x(broadband[2])
        y0 = spectral_bottom - round((spectral_bottom - top) * broadband[0])
        for y in range(y0, spectral_bottom):
            for x in range(x0, x1 + 1):
                if (x + y) % 3 == 0:
                    _pixel(pixels, width, height, x, y, (25, 83, 91))
        _line(pixels, width, height, x0, y0, x1, y0, (42, 137, 145))
        _line(pixels, width, height, x0, y0, x0, spectral_bottom, (42, 137, 145))
        _line(pixels, width, height, x1, y0, x1, spectral_bottom, (42, 137, 145))
        _line(pixels, width, height, x0, spectral_bottom - 1, x1,
              spectral_bottom - 1, (42, 137, 145))
    # Tonal records remain discrete. Their finite catalog widths define the
    # support, and overlapping supports are max-composed rather than overdrawn.
    tonal_level = [0.0] * width
    for frequency, level, line_width in sorted(lines):
        center = spectral_x(frequency)
        half_width = max(.05, line_width / 2.0)
        x0 = min(center - 1, spectral_x(max(SPECTRUM_MIN_HZ,
                                             frequency - half_width)))
        x1 = max(center + 1, spectral_x(min(SPECTRUM_MAX_HZ,
                                             frequency + half_width)))
        x0, x1 = max(left, x0), min(right, x1)
        for x in range(x0, x1 + 1):
            if x <= center:
                shape = (x - x0) / max(1, center - x0)
            else:
                shape = (x1 - x) / max(1, x1 - center)
            tonal_level[x] = max(tonal_level[x], level * max(0.0, shape))
    for x in range(left, right + 1):
        if tonal_level[x] <= 0:
            continue
        peak_y = spectral_bottom - round((spectral_bottom - top) * tonal_level[x])
        for y in range(peak_y + 1, spectral_bottom):
            if (x + y) % 2 == 0:
                _pixel(pixels, width, height, x, y, (42, 115, 104))
        _pixel(pixels, width, height, x, peak_y, (115, 220, 194))
    _line(pixels, width, height, left, top, left, spectral_bottom, (96, 135, 141))
    _line(pixels, width, height, left, spectral_bottom, right, spectral_bottom,
          (96, 135, 141))

    # This is a derived hypothesis region, not spectral evidence. Profile-wide
    # shaft/BPF assumptions are rendered once, on the cruise reference image.
    for y in range(demon_top, demon_bottom + 1):
        if y in (demon_top, demon_bottom):
            _line(pixels, width, height, left, y, right, y, (62, 91, 99))
    shaft = machine["shaft_rpm"] if include_hypotheses else None
    if shaft is not None:
        def demon_x(frequency):
            return left + round((right - left) * max(0.0, min(80.0, frequency)) / 80.0)

        shaft_x0, shaft_x1 = demon_x(shaft[0] / 60.0), demon_x(shaft[-1] / 60.0)
        _line(pixels, width, height, shaft_x0, demon_top + 9, shaft_x1,
              demon_top + 9, (77, 190, 219))
        _line(pixels, width, height, shaft_x0, demon_top + 4, shaft_x0,
              demon_top + 14, (77, 190, 219))
        _line(pixels, width, height, shaft_x1, demon_top + 4, shaft_x1,
              demon_top + 14, (77, 190, 219))
        blades = machine["blade_count"]
        if blades is not None:
            blade_x0 = demon_x(shaft[0] * blades / 60.0)
            blade_x1 = demon_x(shaft[-1] * blades / 60.0)
            _line(pixels, width, height, blade_x0, demon_top + 25, blade_x1,
                  demon_top + 25, (229, 174, 71))
            _line(pixels, width, height, blade_x0, demon_top + 19, blade_x0,
                  demon_bottom - 4, (229, 174, 71))
            _line(pixels, width, height, blade_x1, demon_top + 19, blade_x1,
                  demon_bottom - 4, (229, 174, 71))
    return _png(width, height, pixels)


def expected_output():
    projection = project_contact_catalog()
    files = {}
    assets = []
    for profile in projection["profiles"]:
        for kind, route in profile["assets"].items():
            filename = route.rsplit("/", 1)[-1]
            speed = "cruise" if kind == "acoustic_cruise" else "high_speed"
            payload = _plot(profile["machine"], speed,
                            include_hypotheses=(kind == "acoustic_cruise"))
            width, height = PLOT_SIZE
            files[filename] = payload
            assets.append({
                "profile_key": profile["key"], "kind": kind, "route": route,
                "filename": filename, "width": width, "height": height,
                "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
            })
    manifest = {"version": 1, "assets": assets}
    files["manifest.json"] = (json.dumps(
        manifest, ensure_ascii=True, indent=2, separators=(",", ": ")) + "\n").encode("utf-8")
    return files


def generate(output_dir=DEFAULT_OUTPUT):
    output_dir = Path(output_dir)
    if output_dir.is_symlink():
        raise ValueError("contact-analysis output directory cannot be a symlink")
    output_dir.mkdir(parents=True, exist_ok=True)
    expected = expected_output()
    for path in output_dir.iterdir():
        if path.name == "__pycache__" and path.is_dir() and not path.is_symlink():
            continue
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"unsafe output entry: {path.name}")
        if path.is_file() and path.suffix in GENERATED_SUFFIXES \
                and path.name not in expected and path.name != "__init__.py":
            path.unlink()
    for filename, payload in expected.items():
        (output_dir / filename).write_bytes(payload)
    return expected


def check(output_dir=DEFAULT_OUTPUT):
    output_dir = Path(output_dir)
    expected = expected_output()
    try:
        if output_dir.is_symlink() or not output_dir.is_dir():
            raise ValueError("unsafe output directory")
        entries = [path for path in output_dir.iterdir()
                   if not (path.name == "__pycache__" and path.is_dir()
                           and not path.is_symlink())]
        if any(path.is_symlink() or not path.is_file() for path in entries):
            raise ValueError("unsafe output entry")
        actual_names = {path.name for path in entries}
        allowed_names = set(expected) | {"__init__.py"}
        if actual_names != allowed_names:
            missing = sorted(allowed_names - actual_names)
            extra = sorted(actual_names - allowed_names)
            raise ValueError(f"asset set mismatch (missing={missing}, extra={extra})")
        for filename, payload in expected.items():
            if (output_dir / filename).read_bytes() != payload:
                raise ValueError(f"modified asset: {filename}")
    except (OSError, ValueError) as exc:
        print(f"contact analysis images invalid: {exc}", file=sys.stderr)
        return 1
    print(f"contact analysis images valid: {len(expected) - 1} PNG assets")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="verify packaged bytes without writing")
    parser.add_argument("directory", nargs="?", default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    if args.check:
        return check(args.directory)
    generated = generate(args.directory)
    print(f"generated {len(generated) - 1} PNG assets in {args.directory}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
