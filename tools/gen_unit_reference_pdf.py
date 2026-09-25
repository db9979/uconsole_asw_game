"""Generate a deterministic, dependency-free printable PDF reference of every
catalog unit, including a print-optimised sonar (acoustic) and radar/ESM
fingerprint diagram for each.

This mirrors tools/gen_contact_analysis_images.py's philosophy: no
third-party library, no embedded fonts (PDF's standard Helvetica/
Helvetica-Bold), no timestamps, so two runs on the same catalog produce
byte-identical output. The diagrams are deliberately NOT the dark on-screen
analyzer images (data/contact_analysis/*.png) scaled up - those are tuned for
a backlit uConsole panel, not paper. They are light, ink-sparing prints of the
same station screens from the same data: the receiver's LOFAR/DEMON history
and measured peaks of each catalog signature, and the ELOKA signal fingerprint
of each catalog emitter, on white paper with a bigger reference font so the
measured values stay legible when printed.
"""

import argparse
import os
import sys
import zlib
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.i18n import Translator  # noqa: E402
from src.core.version import APP_VERSION  # noqa: E402
from src.data.contact_analysis import project_contact_catalog  # noqa: E402
from src.core import config  # noqa: E402
from src.sensors.esm import signal_fingerprint  # noqa: E402
from src.ui.sonar_view import (DEMON_DISPLAY_MAX_HZ, _linear_lofar,  # noqa: E402
                               waterfall_pixels)
from tools.gen_contact_analysis_images import (  # noqa: E402
    DISPLAY_BLACK, DISPLAY_CONTRAST, _DIGITS, _format_hz, _line, _pixel,
    _receiver_history, _reference_track, _scaled, _signature_key)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "dist" / "u-jagd-unit-reference.pdf"
DEFAULT_LANG = "de"
CATEGORY_ORDER = ("subs.json", "warships.json", "civilians.json",
                  "aircraft.json", "animals.json", "torpedoes.json",
                  "decoys.json")
IMAGE_KINDS = ("acoustic_cruise", "acoustic_high", "radar")

# --- Print-optimised fingerprint diagrams -----------------------------------
# White canvas, thin/sparse ink, and a font drawn far larger (relative to the
# plot) than the on-screen dark diagrams - see the module docstring.
PRINT_SIZE = (900, 510)
FONT_SCALE = 7  # each _DIGITS bitmap pixel becomes an FONT_SCALE x FONT_SCALE block
AXIS_SCALE = 5
VALUE_SCALE = 5
P_LEFT, P_RIGHT = 14, 885
# (x, y, w, h) regions of the printed sonar screen.
P_LOFAR_TRACE = (P_LEFT, 6, P_RIGHT - P_LEFT + 1, 64)
P_LOFAR = (P_LEFT, 74, P_RIGHT - P_LEFT + 1, 172)
P_DEMON_TRACE = (P_LEFT, 292, P_RIGHT - P_LEFT + 1, 50)
P_DEMON = (P_LEFT, 346, P_RIGHT - P_LEFT + 1, 116)

_BG = (255, 255, 255)
_GRID = (205, 205, 205)
_AXIS = (70, 70, 70)
_LABEL = (25, 25, 25)
_INK = (10, 70, 105)       # waterfall energy: dark teal ink on white paper
_TRACE = (20, 20, 20)
_PEAK = (175, 95, 0)       # measured DEMON modulation peak (amber on screen)
_ESM_BORDER = (120, 150, 130)
_ESM_GRID = (220, 228, 224)
_ESM_SPECTRUM = (175, 105, 0)
_ESM_WAVEFORM = (15, 120, 70)
ESM_LABEL_W = 214


def _canvas():
    width, height = PRINT_SIZE
    # bytes(...) * n is a fast C-level repeat; a tuple repeat (color * n)
    # would build width*height individual Python int objects first.
    return bytearray(bytes(_BG) * (width * height))


def _fill_row(pixels, x0, x1, y, color):
    """Fill one horizontal span with a single slice assignment - the hot path
    for every shape in these diagrams is axis-aligned, so this (not per-pixel
    calls) is what keeps ~330 print diagrams per PDF build fast."""
    width, height = PRINT_SIZE
    if not 0 <= y < height:
        return
    x0, x1 = max(0, min(x0, x1)), min(width - 1, max(x0, x1))
    if x0 > x1:
        return
    row = y * width * 3
    pixels[row + x0 * 3:row + (x1 + 1) * 3] = bytes(color) * (x1 - x0 + 1)


def _fill_col(pixels, x, y0, y1, color):
    width, height = PRINT_SIZE
    if not 0 <= x < width:
        return
    y0, y1 = max(0, min(y0, y1)), min(height - 1, max(y0, y1))
    packed = bytes(color)
    for y in range(y0, y1 + 1):
        offset = (y * width + x) * 3
        pixels[offset:offset + 3] = packed


def _hline(pixels, x0, x1, y, color, thickness=1):
    for offset in range(thickness):
        _fill_row(pixels, x0, x1, y + offset, color)


def _vline(pixels, x, y0, y1, color, thickness=1):
    for offset in range(thickness):
        _fill_col(pixels, x + offset, y0, y1, color)


def _hatch(pixels, x0, x1, y0, y1, color, step=9):
    """Sparse dot fill (roughly 1/step of the area) for shaded regions -
    walked directly at `step` stride rather than visiting and rejecting every
    pixel in the box."""
    width, height = PRINT_SIZE
    for y in range(max(0, y0), min(height - 1, y1) + 1):
        start = x0 + ((-(x0 + y)) % step)
        for x in range(start, x1 + 1, step):
            _pixel(pixels, width, height, x, y, color)


def _label(pixels, value, x, y, *, align="center", color=_LABEL, scale=FONT_SCALE):
    advance = 4 * scale
    label_width = len(value) * advance - scale
    if align == "center":
        x -= label_width // 2
    elif align == "right":
        x -= label_width
    for character in value:
        for row, bits in enumerate(_DIGITS[character]):
            column = 0
            while column < len(bits):
                if bits[column] != "1":
                    column += 1
                    continue
                start = column
                while column < len(bits) and bits[column] == "1":
                    column += 1
                span_x0 = x + start * scale
                span_x1 = x + column * scale - 1
                for dy in range(scale):
                    _fill_row(pixels, span_x0, span_x1, y + row * scale + dy, color)
        x += advance


def _label_width(value, scale):
    return len(value) * 4 * scale - scale


def _rect(pixels, rect, color, thickness=1):
    x0, y0, w, h = rect
    _hline(pixels, x0, x0 + w - 1, y0, color, thickness)
    _hline(pixels, x0, x0 + w - 1, y0 + h - thickness, color, thickness)
    _vline(pixels, x0, y0, y0 + h - 1, color, thickness)
    _vline(pixels, x0 + w - thickness, y0, y0 + h - 1, color, thickness)


def _polyline(pixels, rect, values, color, thickness=2):
    x0, y0, w, h = rect
    values = [min(1.0, max(0.0, float(value))) for value in values]
    points = [(x0 + round(i * (w - 1) / max(1, len(values) - 1)),
               y0 + h - 1 - round(value * (h - 1)))
              for i, value in enumerate(values)]
    for offset in range(thickness):
        for (ax, ay), (bx, by) in zip(points, points[1:]):
            _line(pixels, *PRINT_SIZE, ax, ay + offset, bx, by + offset, color)


def _blit(pixels, image, x0, y0):
    width = PRINT_SIZE[0]
    image = np.ascontiguousarray(image, dtype=np.uint8)
    for row in range(image.shape[0]):
        start = ((y0 + row) * width + x0) * 3
        pixels[start:start + image.shape[1] * 3] = image[row].tobytes()


def _plated_label(pixels, value, x, y, color, scale=VALUE_SCALE):
    """A measured value on a white plate so it stays legible over traces."""
    for row in range(y - scale, y + 6 * scale):
        _fill_row(pixels, x - scale, x + _label_width(value, scale) + scale, row, _BG)
    _label(pixels, value, x, y, align="left", color=color, scale=scale)


def _waterfall(pixels, rows, rect):
    image = waterfall_pixels(rows, black_level=DISPLAY_BLACK,
                             contrast=DISPLAY_CONTRAST, colors=(_BG, _INK))
    _blit(pixels, _scaled(image, rect[3], rect[2]), rect[0], rect[1])


def _axis(pixels, trace, rect, divisions, step, unit):
    x0, _, w, _ = rect
    bottom = rect[1] + rect[3] - 1
    for index in range(divisions + 1):
        x = x0 + round(index * (w - 1) / divisions)
        _vline(pixels, x, trace[1], bottom, _GRID)
        text = str(index * step) + (unit if index == divisions else "")
        _label(pixels, text, x, bottom + 8, scale=AXIS_SCALE,
               align="left" if index == 0 else "right" if index == divisions else "center")
    _rect(pixels, trace, _GRID)
    _rect(pixels, rect, _AXIS)


def print_acoustic_plot(machine, speed):
    """Light print of the reference sonar screen: LOFAR 0-300 Hz and DEMON
    0-50 Hz waterfalls from the station receiver, with measured values."""
    pixels = _canvas()
    lofar_rows, demon_rows, demon_peak, lofar_peaks = _receiver_history(
        _signature_key(machine[f"{speed}_lines"], machine[f"{speed}_broadband"]))
    plot_w = P_RIGHT - P_LEFT + 1

    lofar = np.asarray([_linear_lofar(row, plot_w)
                        for row in np.clip(lofar_rows, 0.0, 1.0)])
    _waterfall(pixels, lofar, P_LOFAR)
    _axis(pixels, P_LOFAR_TRACE, P_LOFAR, 6, 50, "Hz")
    _polyline(pixels, P_LOFAR_TRACE, lofar[-1], _TRACE)

    def lofar_x(frequency):
        return P_LEFT + round(frequency / config.LOFAR_FMAX_HZ * (plot_w - 1))

    levels = [-100, -100]
    for frequency in lofar_peaks:
        text = _format_hz(round(frequency, 1))
        x = lofar_x(frequency)
        _vline(pixels, x, P_LOFAR_TRACE[1] + P_LOFAR_TRACE[3] - 14,
               P_LOFAR_TRACE[1] + P_LOFAR_TRACE[3] - 1, _PEAK, thickness=2)
        left = min(P_RIGHT - _label_width(text, VALUE_SCALE) - 6,
                   max(P_LEFT + 6, x - _label_width(text, VALUE_SCALE) // 2))
        for level, right in enumerate(levels):
            if left > right + 2 * VALUE_SCALE:
                levels[level] = left + _label_width(text, VALUE_SCALE)
                _plated_label(pixels, text, left,
                              P_LOFAR_TRACE[1] + 4 + level * 7 * VALUE_SCALE, _PEAK)
                break

    demon = np.asarray(demon_rows)[:, :int(DEMON_DISPLAY_MAX_HZ)]
    _waterfall(pixels, demon, P_DEMON)
    _axis(pixels, P_DEMON_TRACE, P_DEMON, 5, 10, "Hz")
    _polyline(pixels, P_DEMON_TRACE, np.concatenate(([0.0], demon[-1])), _TRACE)
    if demon_peak is not None and 0.0 <= demon_peak <= DEMON_DISPLAY_MAX_HZ:
        x = P_LEFT + round(demon_peak / DEMON_DISPLAY_MAX_HZ * (plot_w - 1))
        _vline(pixels, x - 1, P_DEMON_TRACE[1], P_DEMON[1] + P_DEMON[3] - 1,
               _PEAK, thickness=3)
        text = _format_hz(round(demon_peak, 1)) + "Hz"
        width = _label_width(text, VALUE_SCALE)
        label_x = x + 10 if x + 10 + width < P_RIGHT else x - 10 - width
        _plated_label(pixels, text, label_x, P_DEMON_TRACE[1] + 8, _PEAK)
    return bytes(pixels)


def _print_fingerprint(pixels, rect, track):
    x0, y0, w, h = rect
    _rect(pixels, rect, _ESM_BORDER, thickness=2)
    _label(pixels, f"{track.frequency_hz / 1e9:.3f}GHz", x0 + 8, y0 + 7,
           align="left", color=_ESM_SPECTRUM, scale=4)
    if track.prf_hz is not None:
        _label(pixels, f"{track.prf_hz:.0f}Hz", x0 + w - 9, y0 + 7,
               align="right", color=_ESM_WAVEFORM, scale=4)
    gx, gy, gw, gh = x0 + 8, y0 + 34, w - 16, h - 42
    split = gy + gh // 2
    for fraction in (.25, .5, .75):
        _vline(pixels, gx + round(gw * fraction), gy, gy + gh - 1, _ESM_GRID, 2)
    _hline(pixels, gx, gx + gw - 1, split, _ESM_GRID, 2)
    fingerprint = signal_fingerprint(track, samples=48, bins=40)
    _polyline(pixels, (gx, gy + 2, gw, split - gy - 6), fingerprint.spectrum,
              _ESM_SPECTRUM, thickness=4)
    _polyline(pixels, (gx, split + 4, gw, gy + gh - split - 6),
              [(value + 1.0) / 2.0 for value in fingerprint.waveform],
              _ESM_WAVEFORM, thickness=4)


def print_radar_plot(emitters):
    """Light print of the ELOKA signal fingerprints: one row per catalog
    emitter (RF/PRF band), one fingerprint per catalog modulation."""
    pixels = _canvas()
    width, height = PRINT_SIZE
    rows = max(1, len(emitters))
    row_h = (height - 8) // rows
    for index, emitter in enumerate(emitters):
        y0 = 4 + index * row_h
        low, high = emitter["frequency_band_hz"]
        _label(pixels, f"{_format_hz(low / 1e9)}-{_format_hz(high / 1e9)}GHz",
               6, y0 + row_h // 2 - 28, align="left", color=_ESM_SPECTRUM, scale=4)
        if emitter["prf_band_hz"] is not None:
            plow, phigh = emitter["prf_band_hz"]
            _label(pixels, f"{_format_hz(plow)}-{_format_hz(phigh)}Hz",
                   6, y0 + row_h // 2 + 6, align="left", color=_ESM_WAVEFORM, scale=4)
        codes = emitter.get("modulation_codes") or ["unknown"]
        box_w = (width - 4 - ESM_LABEL_W - 10 * (len(codes) - 1)) // len(codes)
        for slot, modulation in enumerate(codes):
            _print_fingerprint(
                pixels, (ESM_LABEL_W + slot * (box_w + 10), y0 + 3, box_w, row_h - 6),
                _reference_track(emitter, modulation))
    return bytes(pixels)


def _print_image(kind, machine, emitters):
    if kind == "acoustic_cruise":
        return print_acoustic_plot(machine, "cruise")
    if kind == "acoustic_high":
        return print_acoustic_plot(machine, "high_speed")
    return print_radar_plot(emitters)


# --- PDF layout --------------------------------------------------------------
PAGE_W, PAGE_H = 595.0, 842.0  # A4, points
MARGIN = 36.0
CONTENT_W = PAGE_W - 2 * MARGIN
HEADER_H = 30.0
FOOTER_H = 18.0
CONTENT_TOP = PAGE_H - MARGIN - HEADER_H
CONTENT_BOTTOM = MARGIN + FOOTER_H
CATEGORY_HEADER_H = 16.0
ENTRY_H = 206.0
ENTRY_GAP = 14.0

THUMB_GAP = 10.0
THUMB_W = (CONTENT_W - 2 * THUMB_GAP) / 3
THUMB_H = THUMB_W * PRINT_SIZE[1] / PRINT_SIZE[0]
STATS_COL_GAP = 16.0
STATS_COL_W = (CONTENT_W - STATS_COL_GAP) / 2
STATS_ROW_H = 10.5

# Approximate, deliberately conservative (slightly wide) average glyph widths
# as a fraction of font size, used only to bound/truncate text so a layout
# line never overflows its column - not a real glyph metrics table.
_AVG_WIDTH_EM = {"regular": 0.54, "bold": 0.60}


def _text_width(text, size, bold=False):
    return len(text) * size * _AVG_WIDTH_EM["bold" if bold else "regular"]


def _truncate(text, max_width, size, bold=False):
    if _text_width(text, size, bold) <= max_width or len(text) <= 1:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        candidate = text[:mid].rstrip() + "..."
        if _text_width(candidate, size, bold) <= max_width:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + "..." if lo < len(text) else text


class _PDF:
    """Minimal, deterministic PDF object graph: reserve an object number up
    front, fill its body once known, then serialize in one linear pass so
    byte offsets in the xref table are exact."""

    def __init__(self):
        self._objects: list[bytes | None] = []

    def reserve(self) -> int:
        self._objects.append(None)
        return len(self._objects)

    def set(self, obj_id: int, body: bytes) -> None:
        self._objects[obj_id - 1] = body

    def add(self, body: bytes) -> int:
        obj_id = self.reserve()
        self.set(obj_id, body)
        return obj_id

    def add_stream(self, dict_entries: bytes, data: bytes) -> int:
        """`dict_entries` is the stream dictionary's inner entries, without
        the surrounding `<< >>` - `/Length` is added automatically."""
        body = (b"<< " + dict_entries + b" /Length %d >>\nstream\n" % len(data)
               + data + b"\nendstream")
        return self.add(body)

    def serialize(self, root_id: int, info_id: int | None) -> bytes:
        if any(body is None for body in self._objects):
            raise ValueError("unresolved PDF object")
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0] * (len(self._objects) + 1)
        for index, body in enumerate(self._objects, start=1):
            offsets[index] = len(out)
            out += b"%d 0 obj\n" % index + body + b"\nendobj\n"
        xref_offset = len(out)
        count = len(self._objects) + 1
        out += b"xref\n0 %d\n0000000000 65535 f \n" % count
        for index in range(1, count):
            out += b"%010d 00000 n \n" % offsets[index]
        out += b"trailer\n<< /Size %d /Root %d 0 R" % (count, root_id)
        if info_id is not None:
            out += b" /Info %d 0 R" % info_id
        out += b" >>\nstartxref\n%d\n%%%%EOF" % xref_offset
        return bytes(out)


def _pdf_string(text: str) -> bytes:
    encoded = text.encode("cp1252", errors="replace")
    escaped = (encoded.replace(b"\\", b"\\\\")
              .replace(b"(", b"\\(").replace(b")", b"\\)"))
    return b"(" + escaped + b")"


def _op_text(x, y, size, font, text, *, bold=False):
    name = b"F2" if bold else b"F1"
    return b"BT /%s %g Tf %g %g Td %s Tj ET\n" % (name, size, x, y, _pdf_string(text))


def _op_image(name: str, x, y, w, h) -> bytes:
    return b"q %g 0 0 %g %g %g cm /%s Do Q\n" % (w, h, x, y, name.encode("ascii"))


def _category_key(profile):
    resource = profile["resource"]
    try:
        return CATEGORY_ORDER.index(resource)
    except ValueError:
        return len(CATEGORY_ORDER)


def _entries(language):
    projection = project_contact_catalog()
    translator = Translator(language)

    stat_fields = (
        ("analyzer.hull", lambda p: p["reference"]["hull_type"]),
        ("analyzer.length", lambda p: p["reference"]["length_m"]),
        ("analyzer.cruise_speed", lambda p: p["machine"]["cruise_speed_kn"]),
        ("analyzer.maximum_speed", lambda p: p["machine"]["maximum_speed_kn"]),
        ("analyzer.quiet_speed", lambda p: p["machine"]["quiet_speed_kn"]),
        ("analyzer.propulsion", lambda p: ", ".join(p["machine"]["propulsion_codes"]) or "-"),
        ("analyzer.propulsor", lambda p: p["machine"]["propulsor_type"]),
        ("analyzer.sensors", lambda p: len(p["components"]["sensors"])),
        ("analyzer.emitters", lambda p: len(p["components"]["emitters"])),
        ("analyzer.weapons", lambda p: len(p["components"]["weapons"])),
    )

    profiles = sorted(projection["profiles"],
                      key=lambda p: (_category_key(p), p["name"], p["key"]))
    entries = []
    for profile in profiles:
        stats = []
        for label_key, getter in stat_fields:
            value = getter(profile)
            if value is None:
                value = "-"
            stats.append(f"{translator.t(label_key)}: {value}")
        thumbnails = []
        for kind in IMAGE_KINDS:
            if kind not in profile["assets"]:
                continue
            rgb = _print_image(kind, profile["machine"], profile["components"]["emitters"])
            thumbnails.append((translator.t(f"analyzer.{kind}"), *PRINT_SIZE, rgb))
        entries.append({
            "category": profile["resource"], "name": profile["name"],
            "key": profile["key"], "stats": stats, "thumbnails": thumbnails,
        })
    return translator, entries


class _Layout:
    """Flows entries onto A4 pages, opening a new page whenever the current
    one runs out of room, and emits one finished content stream per page."""

    def __init__(self, pdf: _PDF, translator: Translator):
        self.pdf = pdf
        self.translator = translator
        self.pages: list[tuple[bytes, list[tuple[str, int]]]] = []
        self._ops = bytearray()
        self._images: list[tuple[str, int]] = []
        self._y = CONTENT_BOTTOM  # forces a first page on the first entry

    def _flush_page(self):
        if self._ops:
            page_number = len(self.pages) + 1
            footer = self.translator.t("tools.unit_reference_pdf.footer", page=page_number)
            self._ops += _op_text(MARGIN, MARGIN, 8, "F1", footer)
            self.pages.append((bytes(self._ops), self._images))
        self._ops = bytearray()
        self._images = []

    def _new_page(self):
        self._flush_page()
        title = self.translator.t("tools.unit_reference_pdf.title")
        self._ops += _op_text(MARGIN, PAGE_H - MARGIN - 12, 12, "F1", title, bold=True)
        version_line = f"v{APP_VERSION}"
        self._ops += _op_text(PAGE_W - MARGIN - _text_width(version_line, 9), PAGE_H - MARGIN - 12,
                              9, "F1", version_line)
        self._y = CONTENT_TOP

    def ensure(self, height):
        if self._y - height < CONTENT_BOTTOM:
            self._new_page()

    def category_header(self, text):
        self.ensure(CATEGORY_HEADER_H + ENTRY_H)
        self._y -= CATEGORY_HEADER_H
        self._ops += _op_text(MARGIN, self._y, 11, "F1", text, bold=True)

    def entry(self, name, key, stats, thumbnails):
        self.ensure(ENTRY_H)
        top = self._y
        name_line = _truncate(f"{name}  [{key}]", CONTENT_W, 11, bold=True)
        self._ops += _op_text(MARGIN, top - 13, 11, "F1", name_line, bold=True)

        rows_per_col = (len(stats) + 1) // 2
        stats_top = top - 30
        for index, line in enumerate(stats):
            column, row = divmod(index, rows_per_col)
            x = MARGIN + column * (STATS_COL_W + STATS_COL_GAP)
            line = _truncate(line, STATS_COL_W, 8)
            self._ops += _op_text(x, stats_top - row * STATS_ROW_H, 8, "F1", line)

        images_top = stats_top - rows_per_col * STATS_ROW_H - 10
        for index, (label, width, height, rgb) in enumerate(thumbnails):
            box_x = MARGIN + index * (THUMB_W + THUMB_GAP)
            box_y = images_top - THUMB_H
            name_id = f"Im{len(self._images) + 1}"
            dict_entries = (
                b"/Type /XObject /Subtype /Image /Width %d /Height %d "
                b"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode"
                % (width, height))
            # level 6 keeps these ~370 flat, mostly-white images small enough
            # while staying fast; level 9 cost 3x the time for little gain here.
            obj_id = self.pdf.add_stream(dict_entries, zlib.compress(rgb, level=6))
            self._images.append((name_id, obj_id))
            self._ops += _op_image(name_id, box_x, box_y, THUMB_W, THUMB_H)
            caption = _truncate(label, THUMB_W, 7.5, bold=True)
            caption_x = box_x + (THUMB_W - _text_width(caption, 7.5, bold=True)) / 2
            self._ops += _op_text(max(box_x, caption_x), box_y - 10, 7.5, "F1", caption, bold=True)

        self._y = top - ENTRY_H - ENTRY_GAP

    def finish(self):
        self._flush_page()
        return self.pages


def build_pdf(language=DEFAULT_LANG) -> bytes:
    pdf = _PDF()
    translator, entries = _entries(language)
    layout = _Layout(pdf, translator)

    root_id = pdf.reserve()
    pages_id = pdf.reserve()
    font_id = pdf.add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
                      b"/Encoding /WinAnsiEncoding >>")
    bold_font_id = pdf.add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
                           b"/Encoding /WinAnsiEncoding >>")
    info_id = pdf.add(b"<< /Producer (U-Jagd tools/gen_unit_reference_pdf.py) "
                      b"/Title (U-Jagd Unit Reference) >>")

    last_category = None
    for entry in entries:
        if entry["category"] != last_category:
            layout.category_header(translator.t(f"commander.web.analyzer_{entry['category'][:-5]}"))
            last_category = entry["category"]
        layout.entry(entry["name"], entry["key"], entry["stats"], entry["thumbnails"])

    pages = layout.finish()
    page_ids = []
    for content, images in pages:
        content_id = pdf.add_stream(b"", content)
        page_id = pdf.reserve()
        page_ids.append(page_id)
        xobjects = b"".join(b"/%s %d 0 R " % (name.encode("ascii"), obj_id)
                            for name, obj_id in images)
        pdf.set(page_id,
               b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %g %g] "
               b"/Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> /XObject << %s>> >> "
               b"/Contents %d 0 R >>"
               % (pages_id, PAGE_W, PAGE_H, font_id, bold_font_id, xobjects, content_id))

    kids = b" ".join(b"%d 0 R" % page_id for page_id in page_ids)
    pdf.set(pages_id, b"<< /Type /Pages /Kids [ %s ] /Count %d >>" % (kids, len(page_ids)))
    pdf.set(root_id, b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)
    return pdf.serialize(root_id, info_id)


def generate(output=DEFAULT_OUTPUT, language=DEFAULT_LANG):
    output = Path(output)
    if output.is_symlink():
        raise ValueError("unit-reference output path cannot be a symlink")
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = build_pdf(language)
    staged = output.with_suffix(output.suffix + ".tmp")
    staged.write_bytes(payload)
    os.replace(staged, output)
    return payload


def check(output=DEFAULT_OUTPUT, language=DEFAULT_LANG):
    """Verify deterministic generation without writing. If `output` already
    exists, also verify it holds exactly the current expected bytes (same
    read-only convention as tools/gen_contact_analysis_images.py --check)."""
    output = Path(output)
    expected = build_pdf(language)
    again = build_pdf(language)
    if expected != again:
        print("unit reference pdf invalid: generation is not deterministic",
             file=sys.stderr)
        return 1
    if output.exists():
        if output.is_symlink():
            print("unit reference pdf invalid: output is a symlink", file=sys.stderr)
            return 1
        if output.read_bytes() != expected:
            print(f"unit reference pdf invalid: {output} does not match "
                 "the current deterministic output", file=sys.stderr)
            return 1
    print(f"unit reference pdf deterministic: {len(expected)} bytes")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="verify deterministic generation without writing")
    parser.add_argument("--lang", choices=("en", "de"), default=DEFAULT_LANG,
                        help="language for labels and captions (default: de)")
    parser.add_argument("output", nargs="?", default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    if args.check:
        return check(args.output, args.lang)
    payload = generate(args.output, args.lang)
    print(f"generated {args.output} ({len(payload)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
