"""Generate a deterministic, dependency-free printable PDF reference of every
catalog unit, including a print-optimised sonar (acoustic) and radar/ESM
fingerprint diagram for each.

This mirrors tools/gen_contact_analysis_images.py's philosophy: no
third-party library, no embedded fonts (PDF's standard Helvetica/
Helvetica-Bold), no timestamps, so two runs on the same catalog produce
byte-identical output. The fingerprint diagrams are deliberately NOT the dark,
on-screen analyzer images (data/contact_analysis/*.png) scaled up - those are
tuned for a backlit uConsole panel, not paper. Instead this tool renders its
own light, ink-sparing diagrams straight from the same catalog data (machine
acoustic lines/broadband, radar emitters), with a bigger reference font so the
axis numbers stay legible when printed.
"""

import argparse
import math
import os
import sys
import zlib
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.i18n import Translator  # noqa: E402
from src.core.version import APP_VERSION  # noqa: E402
from src.data.contact_analysis import project_contact_catalog  # noqa: E402
from tools.gen_contact_analysis_images import (  # noqa: E402
    RADAR_MAX_HZ, RADAR_MIN_HZ, RADAR_PRF_MAX_HZ, RADAR_PRF_MIN_HZ,
    SPECTRUM_MAX_HZ, SPECTRUM_MIN_HZ, _DIGITS, _line, _pixel)

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
P_LEFT, P_RIGHT = 76, 880
P_TOP, P_SPECTRAL_BOTTOM = 34, 326
P_DEMON_TOP, P_DEMON_BOTTOM = 376, 456

_BG = (255, 255, 255)
_GRID = (226, 226, 226)
_AXIS = (70, 70, 70)
_LABEL = (25, 25, 25)
_TONAL = (10, 95, 135)
_BAND_LINE = (30, 110, 150)
_BAND_FILL = (221, 236, 245)
_SHAFT_COLOR = (15, 105, 150)
_BLADE_COLOR = (190, 120, 15)
# One fixed colour per emitter row, in catalog (listed) order - kept distinct
# in both hue and lightness so it still reads on a grayscale/B&W printer.
ROW_COLORS = ((25, 60, 140), (195, 95, 10), (15, 120, 70), (150, 15, 95))


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


def _label(pixels, value, x, y, *, align="center", color=_LABEL):
    advance = 4 * FONT_SCALE
    label_width = len(value) * advance - FONT_SCALE
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
                span_x0 = x + start * FONT_SCALE
                span_x1 = x + column * FONT_SCALE - 1
                for dy in range(FONT_SCALE):
                    _fill_row(pixels, span_x0, span_x1, y + row * FONT_SCALE + dy, color)
        x += advance


def _log_x(value, vmin, vmax):
    value = max(vmin, min(vmax, value))
    span = math.log10(vmax / vmin)
    return P_LEFT + round((P_RIGHT - P_LEFT) * math.log10(value / vmin) / span)


def spectral_x(frequency):
    return _log_x(frequency, SPECTRUM_MIN_HZ, SPECTRUM_MAX_HZ)


def radar_spectral_x(frequency):
    return _log_x(frequency, RADAR_MIN_HZ, RADAR_MAX_HZ)


def radar_prf_x(frequency):
    return _log_x(frequency, RADAR_PRF_MIN_HZ, RADAR_PRF_MAX_HZ)


def _tint(color, strength=6):
    return tuple(255 - (255 - channel) // strength for channel in color)


def print_acoustic_plot(machine, speed, *, include_hypotheses=False):
    """A light, print-friendly acoustic fingerprint: a single connected
    spectrum trace (ink proportional to the shape, not its filled area)
    instead of the dark diagram's hatched/shaded peaks."""
    pixels = _canvas()
    lines = machine[f"{speed}_lines"]
    broadband = machine[f"{speed}_broadband"]

    for step in range(5):
        y = P_TOP + (P_SPECTRAL_BOTTOM - P_TOP) * step // 4
        _hline(pixels, P_LEFT, P_RIGHT, y, _GRID)
    for frequency in (5, 10, 100, 1000, 10000):
        _vline(pixels, spectral_x(frequency), P_TOP, P_SPECTRAL_BOTTOM, _GRID)

    if broadband is not None:
        x0, x1 = spectral_x(broadband[1]), spectral_x(broadband[2])
        y0 = P_SPECTRAL_BOTTOM - round((P_SPECTRAL_BOTTOM - P_TOP) * broadband[0])
        _hatch(pixels, x0, x1, y0, P_SPECTRAL_BOTTOM - 1, _BAND_FILL)
        _hline(pixels, x0, x1, y0, _BAND_LINE, thickness=2)
        _vline(pixels, x0, y0, P_SPECTRAL_BOTTOM, _BAND_LINE, thickness=2)
        _vline(pixels, x1, y0, P_SPECTRAL_BOTTOM, _BAND_LINE, thickness=2)

    width = PRINT_SIZE[0]
    tonal_level = [0.0] * width
    for frequency, level, line_width in sorted(lines):
        center = spectral_x(frequency)
        half_width = max(.05, line_width / 2.0)
        x0 = min(center - 1, spectral_x(max(SPECTRUM_MIN_HZ, frequency - half_width)))
        x1 = max(center + 1, spectral_x(min(SPECTRUM_MAX_HZ, frequency + half_width)))
        x0, x1 = max(P_LEFT, x0), min(P_RIGHT, x1)
        for x in range(x0, x1 + 1):
            shape = (x - x0) / max(1, center - x0) if x <= center else (x1 - x) / max(1, x1 - center)
            tonal_level[x] = max(tonal_level[x], level * max(0.0, shape))
    previous = None
    for x in range(P_LEFT, P_RIGHT + 1):
        y = P_SPECTRAL_BOTTOM - round((P_SPECTRAL_BOTTOM - P_TOP) * tonal_level[x])
        if previous is not None:
            _line(pixels, *PRINT_SIZE, previous[0], previous[1], x, y, _TONAL)
        previous = (x, y)

    _hline(pixels, P_LEFT, P_RIGHT, P_SPECTRAL_BOTTOM, _AXIS, thickness=2)
    _vline(pixels, P_LEFT, P_TOP, P_SPECTRAL_BOTTOM, _AXIS, thickness=2)
    for value, y in (("1", P_TOP), (".5", (P_TOP + P_SPECTRAL_BOTTOM) // 2),
                     ("0", P_SPECTRAL_BOTTOM)):
        _label(pixels, value, P_LEFT - 10, y - 3 * FONT_SCALE // 2, align="right")
    for frequency, value in ((5, "5"), (10, "10"), (100, "100"), (1000, "1k"), (10000, "10k")):
        x = spectral_x(frequency)
        _label(pixels, value, min(P_RIGHT, max(P_LEFT, x)), P_SPECTRAL_BOTTOM + 10,
              align="right" if frequency == 10000 else "center")

    for y in (P_DEMON_TOP, P_DEMON_BOTTOM):
        _hline(pixels, P_LEFT, P_RIGHT, y, _AXIS, thickness=2)
    for frequency in (0, 20, 40, 60, 80):
        x = P_LEFT + round((P_RIGHT - P_LEFT) * frequency / 80)
        _vline(pixels, x, P_DEMON_BOTTOM - 6, P_DEMON_BOTTOM, _AXIS, thickness=2)
        _label(pixels, str(frequency), x, P_DEMON_BOTTOM + 10,
              align="right" if frequency == 80 else "center")
    shaft = machine["shaft_rpm"] if include_hypotheses else None
    if shaft is not None:
        def demon_x(frequency):
            return P_LEFT + round((P_RIGHT - P_LEFT) * max(0.0, min(80.0, frequency)) / 80.0)

        shaft_x0, shaft_x1 = demon_x(shaft[0] / 60.0), demon_x(shaft[-1] / 60.0)
        shaft_y = P_DEMON_TOP + 18
        _hline(pixels, shaft_x0, shaft_x1, shaft_y, _SHAFT_COLOR, thickness=3)
        _vline(pixels, shaft_x0, shaft_y - 9, shaft_y + 9, _SHAFT_COLOR, thickness=3)
        _vline(pixels, shaft_x1, shaft_y - 9, shaft_y + 9, _SHAFT_COLOR, thickness=3)
        blades = machine["blade_count"]
        if blades is not None:
            blade_x0 = demon_x(shaft[0] * blades / 60.0)
            blade_x1 = demon_x(shaft[-1] * blades / 60.0)
            blade_y = P_DEMON_BOTTOM - 18
            _hline(pixels, blade_x0, blade_x1, blade_y, _BLADE_COLOR, thickness=3)
            _vline(pixels, blade_x0, blade_y - 9, blade_y + 9, _BLADE_COLOR, thickness=3)
            _vline(pixels, blade_x1, blade_y - 9, blade_y + 9, _BLADE_COLOR, thickness=3)
    return bytes(pixels)


def print_radar_plot(emitters):
    """A light, print-friendly radar/ESM fingerprint: one outlined row per
    catalog emitter, in listed order (never a hidden identity)."""
    pixels = _canvas()

    for step in range(5):
        y = P_TOP + (P_SPECTRAL_BOTTOM - P_TOP) * step // 4
        _hline(pixels, P_LEFT, P_RIGHT, y, _GRID)
    for frequency in (1e9, 2e9, 4e9, 8e9, 18e9):
        _vline(pixels, radar_spectral_x(frequency), P_TOP, P_SPECTRAL_BOTTOM, _GRID)
    _hline(pixels, P_LEFT, P_RIGHT, P_SPECTRAL_BOTTOM, _AXIS, thickness=2)
    _vline(pixels, P_LEFT, P_TOP, P_SPECTRAL_BOTTOM, _AXIS, thickness=2)
    for frequency, value in ((1e9, "1"), (2e9, "2"), (4e9, "4"), (8e9, "8"), (18e9, "18")):
        x = radar_spectral_x(frequency)
        _label(pixels, value, min(P_RIGHT, max(P_LEFT, x)), P_SPECTRAL_BOTTOM + 10,
              align="right" if frequency == 18e9 else "center")

    for y in (P_DEMON_TOP, P_DEMON_BOTTOM):
        _hline(pixels, P_LEFT, P_RIGHT, y, _AXIS, thickness=2)
    for frequency, value in ((100.0, "100"), (1000.0, "1k"), (10_000.0, "10k")):
        x = radar_prf_x(frequency)
        _vline(pixels, x, P_DEMON_BOTTOM - 6, P_DEMON_BOTTOM, _AXIS, thickness=2)
        _label(pixels, value, x, P_DEMON_BOTTOM + 10,
              align="right" if frequency == 10_000.0 else "center")

    rows = len(emitters)
    row_span = (P_SPECTRAL_BOTTOM - P_TOP) / rows
    for index, emitter in enumerate(emitters):
        color = ROW_COLORS[index % len(ROW_COLORS)]
        fill = _tint(color)
        y0 = P_TOP + round(row_span * index) + 6
        y1 = P_TOP + round(row_span * (index + 1)) - 6
        if y1 <= y0:
            y1 = y0 + 1
        lo, hi = emitter["frequency_band_hz"]
        x0, x1 = radar_spectral_x(lo), radar_spectral_x(hi)
        if x1 <= x0:
            x1 = x0 + 1
        _hatch(pixels, x0, x1, y0, y1, fill)
        _hline(pixels, x0, x1, y0, color, thickness=2)
        _hline(pixels, x0, x1, y1, color, thickness=2)
        _vline(pixels, x0, y0, y1, color, thickness=2)
        _vline(pixels, x1, y0, y1, color, thickness=2)

        if emitter["prf_band_hz"] is None:
            continue
        row_y = (P_DEMON_TOP + 18 if rows == 1 else
                 P_DEMON_TOP + 12 + round((P_DEMON_BOTTOM - P_DEMON_TOP - 24) * index / (rows - 1)))
        plo, phi = emitter["prf_band_hz"]
        px0, px1 = radar_prf_x(plo), radar_prf_x(phi)
        if px1 <= px0:
            px1 = px0 + 1
        _hline(pixels, px0, px1, row_y, color, thickness=3)
        _vline(pixels, px0, row_y - 9, row_y + 9, color, thickness=3)
        _vline(pixels, px1, row_y - 9, row_y + 9, color, thickness=3)
    return bytes(pixels)


def _print_image(kind, machine, emitters):
    if kind == "acoustic_cruise":
        return print_acoustic_plot(machine, "cruise", include_hypotheses=True)
    if kind == "acoustic_high":
        return print_acoustic_plot(machine, "high_speed", include_hypotheses=False)
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
