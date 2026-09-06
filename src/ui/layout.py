"""W0: Layout-Helfer – 3-Teil-Grid, Text-Einpassung (Wrap/Autofit/Clip).

Text darf niemals über Box-Grenzen hinausragen: alle Views rendern über
die Helfer hier (Word-Wrap, dynamische Schriftgröße, Surface-Clipping).
"""

from contextlib import contextmanager

import pygame

from src.core import config

# Font-Cache: pygame-Fonts sind teuer -> pro Größe einmal erzeugen.
_FONT_CACHE: dict = {}


def font(size: int, bold: bool = False) -> pygame.font.Font:
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
             min_size: int = 9) -> tuple:
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
               color, size: int = 16, min_size: int = 9,
               align: str = "left", valign: str = "top") -> None:
    """Blendet einen Textblock, der garantiert in (x,y,w,h) bleibt."""
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
                   config.COLOR_TEXT, title_size, min_size=10)
        top += f.get_linesize() + 8
    return x + 10, top, max(1, w - 20), max(1, y + h - top - 8)


def blit_line(screen, text: str, rect, color, size: int = 14,
              align: str = "left") -> None:
    """Einzeilige, horizontal und vertikal begrenzte Textausgabe."""
    x, y, w, h = rect
    blit_block(screen, text, x, y, w, h, color=color, size=size,
               min_size=max(9, size - 4), align=align)


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
    lab = label
    while lab and f.size(lab)[0] > label_w - 4:
        lab = lab[:-1]
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
