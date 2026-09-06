"""W0: Layout-Helfer – 3-Teil-Grid, Text-Einpassung (Wrap/Autofit/Clip).

Text darf niemals über Box-Grenzen hinausragen: alle Views rendern über
die Helfer hier (Word-Wrap, dynamische Schriftgröße, Surface-Clipping).
"""

from contextlib import contextmanager

import pygame

from src.core import config
from src.core.i18n import localize

# Font-Cache: pygame-Fonts sind teuer -> pro Größe einmal erzeugen.
_FONT_CACHE: dict = {}
_FONT_CACHE_DISPLAY = None
MIN_OPERATIONAL_FONT = 12


def clear_font_cache() -> None:
    """Drop SDL-bound fonts before pygame teardown or display replacement."""
    global _FONT_CACHE_DISPLAY
    _FONT_CACHE.clear()
    _FONT_CACHE_DISPLAY = None


def font(size: int, bold: bool = False) -> pygame.font.Font:
    global _FONT_CACHE_DISPLAY
    if not pygame.font.get_init():
        clear_font_cache()
        pygame.font.init()
    display = pygame.display.get_surface()
    # Tests and standalone tools can quit/reinitialize SDL between surfaces.
    # Cache only while a live display provides a stable SDL lifetime token.
    if display is None:
        return pygame.font.SysFont("monospace", size, bold=bold)
    if display is not _FONT_CACHE_DISPLAY:
        clear_font_cache()
        _FONT_CACHE_DISPLAY = display
    key = (size, bold)
    f = _FONT_CACHE.get(key)
    if f is None:
        f = pygame.font.SysFont("monospace", size, bold=bold)
        _FONT_CACHE[key] = f
    return f


def _line_height(f: pygame.font.Font) -> int:
    return int(f.get_linesize() * 1.15)


def wrap_text(text: str, f: pygame.font.Font, width_px: int) -> list:
    """Word-Wrap über f.size(); explizite Newlines werden respektiert."""
    if width_px <= 0:
        return []
    out = []
    for para in text.split("\n"):
        words = para.split(" ")
        line = ""
        for w in words:
            trial = w if not line else line + " " + w
            if f.size(trial)[0] <= width_px:
                line = trial
            else:
                if line:
                    out.append(line)
                # Zu langes Einzelwort: harte Zerteilung (kein Overflow)
                line = ""
                for char in w:
                    if f.size(line + char)[0] > width_px:
                        if line:
                            out.append(line)
                        line = ""
                    # A glyph wider than the box cannot be wrapped to fit.
                    if f.size(char)[0] <= width_px:
                        line += char
        out.append(line)
    return out


def fit_text(text: str, size: int, width_px: int, height_px: int,
             min_size: int = MIN_OPERATIONAL_FONT) -> tuple:
    """Text so groß wie möglich (ab min_size), dass er in w×h passt.

    Liefert (Font, [Zeilen]). Zeilen werden bei Bedarf auf die verfügbare
    Anzahl gekürzt und die letzte Zeile ellipsiert – nie Überlauf.
    """
    for sz in range(size, min_size - 1, -1):
        f = font(sz)
        lines = wrap_text(text, f, width_px)
        if not lines:
            return f, [""]
        lh = _line_height(f)
        if len(lines) * lh <= height_px:
            return f, lines
    f = font(min_size)
    lines = wrap_text(text, f, width_px)
    lh = _line_height(f)
    max_lines = max(1, height_px // lh)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and f.size(last + "…")[0] > width_px:
            last = last[:-1]
        lines[-1] = last + "…" if f.size("…")[0] <= width_px else last
    return f, lines


def blit_block(screen, text: str, x: int, y: int, w: int, h: int,
               color, size: int = 16, min_size: int = MIN_OPERATIONAL_FONT,
               align: str = "left", valign: str = "top") -> None:
    """Blendet einen Textblock, der garantiert in (x,y,w,h) bleibt."""
    text = localize(text)
    if not text or w <= 0 or h <= 0:
        return
    rect = pygame.Rect(x, y, w, h)
    f, lines = fit_text(text, size, w, h, min_size)
    lh = _line_height(f)
    total_h = len(lines) * lh
    if valign == "center":
        y += max(0, (h - total_h) // 2)
    elif valign == "bottom":
        y += max(0, h - total_h)
    with clip_to(screen, rect):
        for i, line in enumerate(lines):
            px = x
            if align == "center":
                px = x + max(0, (w - f.size(line)[0]) // 2)
            elif align == "right":
                px = x + w - f.size(line)[0]
            screen.blit(f.render(line, True, color), (px, y + i * lh))


def box(screen, rect, title: str = "", border=None, fill=(14, 24, 18),
        title_size: int = 16) -> tuple:
    """Zeichnet eine Box und liefert ihr garantiert inneres Rechteck."""
    x, y, w, h = rect
    border = border or config.COLOR_SONAR_RING
    pygame.draw.rect(screen, fill, rect)
    pygame.draw.rect(screen, border, rect, 1)
    top = y + 8
    if title:
        f = font(title_size, bold=True)
        blit_block(screen, title, x + 10, top, w - 20, f.get_linesize() + 2,
                   config.COLOR_TEXT, title_size, min_size=MIN_OPERATIONAL_FONT)
        top += f.get_linesize() + 8
    return x + 10, top, max(1, w - 20), max(1, y + h - top - 8)


def blit_line(screen, text: str, rect, color, size: int = 14,
              align: str = "left") -> None:
    """Einzeilige, horizontal und vertikal begrenzte Textausgabe."""
    x, y, w, h = rect
    blit_block(screen, text, x, y, w, h, color=color, size=size,
               min_size=min(size, max(MIN_OPERATIONAL_FONT, size - 4)), align=align)


def blit_lines(screen, lines, rect, color, size: int = 14,
               line_gap: int = 2) -> int:
    """Render a bounded list and return the number of visible lines."""
    x, y, w, h = rect
    f = font(size)
    line_h = max(f.get_linesize(), int(f.get_linesize() * 1.05)) + line_gap
    visible = max(0, h // line_h)
    lines = list(lines)
    with clip_to(screen, (x, y, w, h)):
        for i, text in enumerate(lines[:visible]):
            blit_line(screen, text, (x, y + i * line_h, w, line_h),
                      color, size=size)
    return min(len(lines), visible)


@contextmanager
def clip_to(screen, rect):
    """`with layout.clip_to(s, rect):` – Clip auf rect (keine Übermalung)."""
    old = screen.get_clip()
    screen.set_clip(old.clip(rect))
    try:
        yield
    finally:
        screen.set_clip(old)


def panel(screen, rect, title: str = "", title_size: int = 20) -> int:
    """Panel-Rahmen + optionaler Titel; liefert y unterhalb des Titels."""
    x, y, w, h = rect
    pygame.draw.rect(screen, (14, 24, 18), (x, y, w, h))
    pygame.draw.rect(screen, config.COLOR_SONAR_RING, (x, y, w, h), 1)
    title = localize(title)
    if title:
        f, lines = fit_text(title, title_size, w - 28, 40, min_size=12)
        screen.blit(f.render(lines[0], True, config.COLOR_TEXT), (x + 14, y + 8))
        return y + 8 + _line_height(f) + 8
    return y + 12


def status_line(screen, x: int, y: int, w: int, label: str, value: str,
                color=None, dim_color=None, size: int = 15,
                label_w: int = 130) -> None:
    """'Label  Wert' – beide Hälften einzeln gekürzt, nie Überlauf."""
    f = font(size)
    col = color or config.COLOR_TEXT
    dcol = dim_color or config.COLOR_TEXT_DIM
    lab = localize(label)
    while lab and f.size(lab)[0] > label_w - 4:
        lab = lab[:-1]
    value = localize(value)
    val = value
    rest = w - label_w - 4
    ellipsis = "…"
    while val and f.size(val + ellipsis)[0] > rest:
        val = val[:-1]
    if val != value:
        val += ellipsis
    with clip_to(screen, (x, y, w, f.get_linesize())):
        screen.blit(f.render(lab, True, dcol), (x, y))
        screen.blit(f.render(val, True, col), (x + label_w + 4, y))


def tooltip_payload(title: str, *lines: str, target_id: str = "") -> dict:
    """Return an object-free tooltip value safe to retain or serialize."""
    return {
        "id": str(target_id),
        "title": localize(title),
        "lines": [localize(line) for line in lines
                  if line is not None and str(line)],
    }


def valid_tooltip(value) -> dict | None:
    """Validate untrusted/save-loaded tooltip data without retaining objects."""
    if not isinstance(value, dict) or not isinstance(value.get("title"), str):
        return None
    lines = value.get("lines", [])
    if not isinstance(lines, list) or not all(isinstance(line, str) for line in lines):
        return None
    return tooltip_payload(value["title"], *lines[:12],
                           target_id=value.get("id", ""))


def tooltip_rect(payload: dict, pointer, bounds=(0, 0, 1280, 720),
                 max_width: int = 420) -> tuple[pygame.Rect, list[str]]:
    """Lay out a readable tooltip, flipping and clamping it at canvas edges."""
    bounds = pygame.Rect(bounds)
    f = font(MIN_OPERATIONAL_FONT)
    available = max(80, min(max_width, bounds.w - 16))
    source = [payload.get("title", "")] + list(payload.get("lines", []))
    natural = max((f.size(line)[0] for line in source), default=0) + 24
    width = max(180, min(available, natural))
    lines = []
    for line in source:
        lines.extend(wrap_text(str(line), f, width - 24) or [""])
    line_h = _line_height(f)
    height = 16 + line_h * len(lines)
    height = min(max(44, height), bounds.h - 16)
    x, y = int(pointer[0]) + 14, int(pointer[1]) + 18
    if x + width > bounds.right - 8:
        x = int(pointer[0]) - width - 14
    if y + height > bounds.bottom - 8:
        y = int(pointer[1]) - height - 14
    rect = pygame.Rect(x, y, width, height)
    rect.clamp_ip(bounds.inflate(-16, -16))
    return rect, lines


def draw_tooltip(screen, payload: dict, pointer,
                 bounds=(0, 0, 1280, 720)) -> pygame.Rect | None:
    """Draw a high-contrast tooltip and return its bounded rectangle."""
    payload = valid_tooltip(payload)
    if payload is None:
        return None
    rect, lines = tooltip_rect(payload, pointer, bounds)
    pygame.draw.rect(screen, (5, 13, 10), rect)
    pygame.draw.rect(screen, config.COLOR_WARN, rect, 2)
    f = font(MIN_OPERATIONAL_FONT)
    line_h = _line_height(f)
    with clip_to(screen, rect.inflate(-10, -8)):
        for index, line in enumerate(lines):
            face = font(MIN_OPERATIONAL_FONT, bold=True) if index == 0 else f
            color = config.COLOR_TEXT if index == 0 else config.COLOR_TEXT_DIM
            screen.blit(face.render(line, True, color),
                        (rect.x + 12, rect.y + 8 + index * line_h))
    return rect
