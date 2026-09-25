"""Generate deterministic, font-free contact-analysis PNG resources.

Acoustic images are reference sonar screens: the catalog signature is played
through the station's own AcousticReceiver and rendered with the station's
LOFAR (0-300 Hz linear) and DEMON (0-50 Hz) waterfall mapping. Radar images
show the ELOKA signal fingerprint of every catalog emitter/modulation.
"""

import argparse
import binascii
from functools import lru_cache
import hashlib
import json
import os
import struct
import sys
import zlib
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.audio.receiver import AcousticReceiver  # noqa: E402
from src.core import config  # noqa: E402
from src.data.contact_analysis import project_contact_catalog  # noqa: E402
from src.sensors.esm import ESMTrack, signal_fingerprint  # noqa: E402
from src.ui.sonar_view import (AMBER as SCREEN_AMBER, CYAN as SCREEN_CYAN,  # noqa: E402
                               DEMON_DISPLAY_MAX_HZ, GRID as SCREEN_GRID,
                               NAVY as SCREEN_NAVY, PANEL as SCREEN_PANEL,
                               _linear_lofar, waterfall_pixels)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "contact_analysis"
PLOT_SIZE = (320, 180)
GENERATED_SUFFIXES = (".png", ".json")
# Axis bounds of the printed unit reference (tools/gen_unit_reference_pdf.py).
SPECTRUM_MIN_HZ = 5.0
SPECTRUM_MAX_HZ = 10_000.0
RADAR_MIN_HZ = 0.5e9
RADAR_MAX_HZ = 18e9
RADAR_PRF_MIN_HZ = 100.0
RADAR_PRF_MAX_HZ = 10_000.0
LABEL_COLOR = (119, 151, 169)  # sonar_view.DIM
PLOT_LEFT = 6
PLOT_RIGHT = PLOT_SIZE[0] - 7
# (x, y, w, h) regions of the reference sonar screen.
LOFAR_TRACE_RECT = (PLOT_LEFT, 3, PLOT_RIGHT - PLOT_LEFT + 1, 22)
LOFAR_RECT = (PLOT_LEFT, 27, PLOT_RIGHT - PLOT_LEFT + 1, 76)
DEMON_TRACE_RECT = (PLOT_LEFT, 114, PLOT_RIGHT - PLOT_LEFT + 1, 16)
DEMON_RECT = (PLOT_LEFT, 132, PLOT_RIGHT - PLOT_LEFT + 1, 37)
# Reference listening geometry: a clear contact in the beam, own ship stopped.
REFERENCE_LEVEL = 0.8
REFERENCE_SEA_STATE = 3.0
REFERENCE_BEAM_DEG = 12.0
REFERENCE_RECEIVER_SEED = 42
WARMUP_BLOCKS = 8               # fills the receiver's two-second FFT window
LOFAR_ROWS = config.LOFAR_HISTORY_COLS
DEMON_ROWS = config.SONAR_DEMON_HISTORY_ROWS
# Station display defaults (Game.sonar_display_*).
DISPLAY_BLACK = 0.0
DISPLAY_CONTRAST = 1.6
DISPLAY_PALETTE = "green"
# ELOKA evidence-page colours (stations_view._draw_eloka_signal).
ESM_PANEL = (6, 12, 10)
ESM_BACKGROUND = (8, 18, 16)
ESM_BORDER = config.COLOR_SONAR_RING
ESM_GRID = (24, 50, 44)
ESM_SPLIT = (36, 72, 62)
ESM_SPECTRUM = config.COLOR_WARN
ESM_WAVEFORM = config.COLOR_OK
RADAR_LABEL_W = 62
_DIGITS = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "010", "010", "010"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
    ".": ("000", "000", "000", "000", "010"),
    "-": ("000", "000", "111", "000", "000"),
    "k": ("100", "101", "110", "101", "101"),
    "G": ("111", "100", "101", "101", "111"),
    "H": ("101", "101", "111", "101", "101"),
    "z": ("000", "111", "001", "010", "111"),
}
VALUE_COLOR = (226, 240, 236)


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


def _label(pixels, width, height, value, x, y, *, align="center",
           color=LABEL_COLOR):
    """Draw fixed numeric ticks into the shared PNG for both UIs."""
    label_width = len(value) * 4 - 1
    if align == "center":
        x -= label_width // 2
    elif align == "right":
        x -= label_width
    for character in value:
        for row, bits in enumerate(_DIGITS[character]):
            for column, bit in enumerate(bits):
                if bit == "1":
                    _pixel(pixels, width, height, x + column, y + row,
                           color)
        x += 4


def _fill(pixels, width, height, rect, color):
    x0, y0, w, h = rect
    for y in range(max(0, y0), min(height, y0 + h)):
        row = (y * width) * 3
        for x in range(max(0, x0), min(width, x0 + w)):
            pixels[row + x * 3:row + x * 3 + 3] = bytes(color)


def _blit(pixels, width, image, x0, y0):
    """Copy an RGB uint8 array (rows x columns x 3) into the canvas."""
    image = np.ascontiguousarray(image, dtype=np.uint8)
    rows, columns = image.shape[:2]
    for row in range(rows):
        start = ((y0 + row) * width + x0) * 3
        pixels[start:start + columns * 3] = image[row].tobytes()


def _scaled(image, rows, columns):
    """Nearest-neighbour scale like the one pygame.transform.scale per frame."""
    y = (np.arange(rows) * image.shape[0]) // rows
    x = (np.arange(columns) * image.shape[1]) // columns
    return image[y][:, x]


def _polyline(pixels, width, height, rect, values, color, *, thickness=1):
    """Station-style trace: 0..1 values spread across the strip's width."""
    x0, y0, w, h = rect
    values = [min(1.0, max(0.0, float(value))) for value in values]
    if len(values) < 2:
        return
    points = [(x0 + round(i * (w - 1) / (len(values) - 1)),
               y0 + h - 1 - round(value * (h - 1)))
              for i, value in enumerate(values)]
    for offset in range(thickness):
        for (ax, ay), (bx, by) in zip(points, points[1:]):
            _line(pixels, width, height, ax, ay + offset, bx, by + offset, color)


def _label_width(text):
    return len(text) * 4 - 1


def _value_label(pixels, width, height, text, x, y, color, background):
    """A measured value on a dark plate so it stays legible over traces."""
    _fill(pixels, width, height, (x - 1, y - 1, _label_width(text) + 2, 7),
          background)
    _label(pixels, width, height, text, x, y, align="left", color=color)


def _peak_labels(pixels, width, height, rect, frequencies, x_of, color):
    """Label measured peaks in a trace strip, staggering crowded ones."""
    x0, y0, w, h = rect
    levels = max(1, (h - 2) // 7)
    last_right = [-10] * levels
    for frequency in frequencies:
        text = _format_hz(round(frequency, 1))
        x = x_of(frequency)
        left = min(x0 + w - _label_width(text) - 1,
                   max(x0 + 1, x - _label_width(text) // 2))
        for level in range(levels):
            if left > last_right[level] + 1:
                break
        else:
            continue
        last_right[level] = left + _label_width(text)
        _value_label(pixels, width, height, text, left, y0 + 1 + 7 * level,
                     color, SCREEN_NAVY)


def _signature_key(lines, broadband):
    return json.dumps([lines, broadband], separators=(",", ":"))


@lru_cache(maxsize=None)
def _receiver_history(signature):
    """Run the station receiver on one catalog signature; return display rows.

    The contact is a steady source dead ahead in the listening beam of a
    stopped own ship: no Doppler, own shaft line or self-noise lobe. Every
    trace therefore comes from the same synthesis and FFT/DEMON analysis the
    sonar station uses, never from a hand-drawn catalog diagram.
    """
    lines, broadband = json.loads(signature)
    source = {"bearing": 0.0, "level": REFERENCE_LEVEL,
              "lines": [tuple(line) for line in lines],
              "seed": zlib.crc32(signature.encode("ascii"))}
    if broadband is not None and broadband[0] > 0:
        source["broadband"] = {"level": broadband[0], "low_hz": broadband[1],
                               "high_hz": broadband[2]}
    receiver = AcousticReceiver(seed=REFERENCE_RECEIVER_SEED)
    lofar, demon = [], []
    for _ in range(WARMUP_BLOCKS + DEMON_ROWS):
        receiver.update([source], 0.0, REFERENCE_BEAM_DEG, 0.0,
                        REFERENCE_SEA_STATE, 0.0)
        lofar.append(list(receiver.spectrum))
        demon.append(list(receiver.demon_spectrum))
    analysis = receiver.demon_analysis or {}
    peak = analysis.get("modulation_peak_hz")
    peaks = tuple(sorted(float(hz) for hz, _ in receiver.peaks
                         if 0.0 < hz <= config.LOFAR_FMAX_HZ))
    return (np.asarray(lofar[-LOFAR_ROWS:], dtype=float),
            np.asarray(demon[-DEMON_ROWS:], dtype=float),
            None if peak is None else float(peak), peaks)


def _waterfall_image(rows, rect):
    pixels = waterfall_pixels(rows, black_level=DISPLAY_BLACK,
                              contrast=DISPLAY_CONTRAST, palette=DISPLAY_PALETTE)
    return _scaled(pixels, rect[3], rect[2])


def _plot(machine, speed):
    """Reference LOFAR (0-300 Hz, linear) and DEMON (0-50 Hz) sonar screens."""
    width, height = PLOT_SIZE
    pixels = _canvas(width, height, SCREEN_PANEL)
    lofar_rows, demon_rows, demon_peak, lofar_peaks = _receiver_history(_signature_key(
        machine[f"{speed}_lines"], machine[f"{speed}_broadband"]))
    left, plot_w = PLOT_LEFT, PLOT_RIGHT - PLOT_LEFT + 1

    # LOFAR: live spectrum strip above the waterfall, newest row on top.
    lofar_rows = np.clip(lofar_rows, 0.0, 1.0)
    lofar = np.asarray([_linear_lofar(row, plot_w) for row in lofar_rows])
    _fill(pixels, width, height, LOFAR_TRACE_RECT, SCREEN_NAVY)
    _blit(pixels, width, _waterfall_image(lofar, LOFAR_RECT), left, LOFAR_RECT[1])
    for index in range(7):
        x = left + round(index * (plot_w - 1) / 6)
        _line(pixels, width, height, x, LOFAR_TRACE_RECT[1], x,
              LOFAR_RECT[1] + LOFAR_RECT[3] - 1, SCREEN_GRID)
        _label(pixels, width, height, str(index * 50) + ("Hz" if index == 6 else ""),
               x, LOFAR_RECT[1] + LOFAR_RECT[3] + 3,
               align="left" if index == 0 else "right" if index == 6 else "center")
    _polyline(pixels, width, height, LOFAR_TRACE_RECT, lofar[-1], SCREEN_CYAN)

    def lofar_x(frequency):
        return left + round(frequency / config.LOFAR_FMAX_HZ * (plot_w - 1))

    for frequency in lofar_peaks:
        x = lofar_x(frequency)
        _line(pixels, width, height, x, LOFAR_TRACE_RECT[1] + LOFAR_TRACE_RECT[3] - 4,
              x, LOFAR_TRACE_RECT[1] + LOFAR_TRACE_RECT[3] - 1, VALUE_COLOR)
    _peak_labels(pixels, width, height, LOFAR_TRACE_RECT, lofar_peaks, lofar_x,
                 VALUE_COLOR)

    # DEMON: envelope spectrum strip and waterfall, amber measured peak.
    demon = np.concatenate((np.zeros((len(demon_rows), 1)),
                            demon_rows[:, :int(DEMON_DISPLAY_MAX_HZ)]), axis=1)
    _fill(pixels, width, height, DEMON_TRACE_RECT, SCREEN_NAVY)
    _blit(pixels, width, _waterfall_image(demon[:, 1:], DEMON_RECT), left,
          DEMON_RECT[1])
    for index in range(6):
        x = left + round(index * (plot_w - 1) / 5)
        _line(pixels, width, height, x, DEMON_TRACE_RECT[1], x,
              DEMON_RECT[1] + DEMON_RECT[3] - 1, SCREEN_GRID)
        _label(pixels, width, height, str(index * 10) + ("Hz" if index == 5 else ""),
               x, DEMON_RECT[1] + DEMON_RECT[3] + 3,
               align="left" if index == 0 else "right" if index == 5 else "center")
    _polyline(pixels, width, height, DEMON_TRACE_RECT, demon[-1], SCREEN_CYAN)
    if demon_peak is not None and 0.0 <= demon_peak <= DEMON_DISPLAY_MAX_HZ:
        x = left + round(demon_peak / DEMON_DISPLAY_MAX_HZ * (plot_w - 1))
        _line(pixels, width, height, x, DEMON_TRACE_RECT[1], x,
              DEMON_RECT[1] + DEMON_RECT[3] - 1, SCREEN_AMBER)
        text = _format_hz(round(demon_peak, 1)) + "Hz"
        label_x = (x + 3 if x + 3 + _label_width(text) < PLOT_RIGHT
                   else x - 3 - _label_width(text))
        _value_label(pixels, width, height, text, label_x,
                     DEMON_TRACE_RECT[1] + 2, SCREEN_AMBER, SCREEN_NAVY)
    return _png(width, height, pixels)


def _format_hz(value):
    """Compact 3x5-font number: 9.4, 12, 300, 1.2k."""
    if value >= 1000.0:
        text = f"{value / 1000.0:.1f}".rstrip("0").rstrip(".")
        return text + "k"
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _reference_track(emitter, modulation):
    """Detached ESM track at the emitter's band centres (never a live track)."""
    low, high = emitter["frequency_band_hz"]
    prf = (None if emitter["prf_band_hz"] is None
           else sum(emitter["prf_band_hz"]) / 2.0)
    return ESMTrack(track_key="REFERENCE", observer_x=0.0, observer_y=0.0,
                    bearing=0.0, bearing_uncertainty_deg=0.0,
                    frequency_hz=(low + high) / 2.0, prf_hz=prf,
                    modulation_code=modulation, quality=1.0,
                    first_seen=0.0, last_seen=0.0)


def _fingerprint_box(pixels, width, height, rect, track):
    """The ESM evidence page's signal fingerprint, drawn at its own colours."""
    x0, y0, w, h = rect
    _fill(pixels, width, height, rect, ESM_BACKGROUND)
    _line(pixels, width, height, x0, y0, x0 + w - 1, y0, ESM_BORDER)
    _line(pixels, width, height, x0, y0 + h - 1, x0 + w - 1, y0 + h - 1, ESM_BORDER)
    _line(pixels, width, height, x0, y0, x0, y0 + h - 1, ESM_BORDER)
    _line(pixels, width, height, x0 + w - 1, y0, x0 + w - 1, y0 + h - 1, ESM_BORDER)
    # Header: the intercept's measured RF (GHz, three decimals as on the
    # ELOKA list) and PRF, like the evidence page's frequency/PRF fields.
    _label(pixels, width, height, f"{track.frequency_hz / 1e9:.3f}GHz",
           x0 + 3, y0 + 2, align="left", color=ESM_SPECTRUM)
    if track.prf_hz is not None:
        _label(pixels, width, height, f"{track.prf_hz:.0f}Hz", x0 + w - 4,
               y0 + 2, align="right", color=ESM_WAVEFORM)
    y0, h = y0 + 7, h - 7
    gx, gy, gw, gh = x0 + 3, y0 + 3, w - 6, h - 6
    split = gy + gh // 2
    for fraction in (.25, .5, .75):
        x = gx + round(gw * fraction)
        _line(pixels, width, height, x, gy, x, gy + gh - 1, ESM_GRID)
    _line(pixels, width, height, gx, split, gx + gw - 1, split, ESM_SPLIT)
    fingerprint = signal_fingerprint(track, samples=48, bins=40)
    spectrum_h = max(4, split - gy - 3)
    _polyline(pixels, width, height, (gx, gy + 1, gw, spectrum_h),
              fingerprint.spectrum, ESM_SPECTRUM, thickness=2)
    wave_h = gy + gh - split - 3
    _polyline(pixels, width, height, (gx, split + 2, gw, wave_h),
              [(value + 1.0) / 2.0 for value in fingerprint.waveform],
              ESM_WAVEFORM, thickness=2)


def _radar_plot(emitters):
    """One row per listed catalog emitter: RF band (GHz) and PRF band (Hz)
    labels, then one ESM signal fingerprint per catalog modulation code,
    exactly as the ELOKA evidence page draws an intercept of that emitter."""
    width, height = PLOT_SIZE
    pixels = _canvas(width, height, ESM_PANEL)
    rows = max(1, len(emitters))
    row_h = (height - 4) // rows
    for index, emitter in enumerate(emitters):
        y0 = 2 + index * row_h
        low, high = emitter["frequency_band_hz"]
        rf = f"{_format_hz(low / 1e9)}-{_format_hz(high / 1e9)}GHz"
        _label(pixels, width, height, rf, 4, y0 + row_h // 2 - 8, align="left",
               color=ESM_SPECTRUM)
        if emitter["prf_band_hz"] is not None:
            plow, phigh = emitter["prf_band_hz"]
            _label(pixels, width, height,
                   f"{_format_hz(plow)}-{_format_hz(phigh)}Hz", 4,
                   y0 + row_h // 2 + 2, align="left", color=ESM_WAVEFORM)
        codes = emitter.get("modulation_codes") or ["unknown"]
        box_left = RADAR_LABEL_W
        box_w = (width - 2 - box_left - 4 * (len(codes) - 1)) // len(codes)
        for slot, modulation in enumerate(codes):
            _fingerprint_box(
                pixels, width, height,
                (box_left + slot * (box_w + 4), y0 + 1, box_w, row_h - 2),
                _reference_track(emitter, modulation))
    return _png(width, height, pixels)


def expected_output():
    projection = project_contact_catalog()
    files = {}
    assets = []
    for profile in projection["profiles"]:
        for kind, route in profile["assets"].items():
            filename = route.rsplit("/", 1)[-1]
            if kind == "radar":
                payload = _radar_plot(profile["components"]["emitters"])
            else:
                speed = "cruise" if kind == "acoustic_cruise" else "high_speed"
                payload = _plot(profile["machine"], speed)
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
