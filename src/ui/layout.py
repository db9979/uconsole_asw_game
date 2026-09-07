"""W0: Layout-Helfer – 3-Teil-Grid, Text-Einpassung (Wrap/Autofit/Clip).

Text darf niemals über Box-Grenzen hinausragen: alle Views rendern über
die Helfer hier (Word-Wrap, dynamische Schriftgröße, Surface-Clipping).
"""

from contextlib import contextmanager

import pygame

from src.core import config
from src.core.i18n import localize, message

# Font-Cache: pygame-Fonts sind teuer -> pro Größe einmal erzeugen.
_FONT_CACHE: dict = {}
_FONT_CACHE_DISPLAY = None
MIN_OPERATIONAL_FONT = 14
TOOLTIP_BODY_SIZE = 14
TOOLTIP_TITLE_SIZE = 16
LARGE_TEXT_SCALE = 1.2
_TEXT_SCALE = 1.0
_GEOMETRY_TRACE = None
_TEXT_TRACE = None


def clear_font_cache() -> None:
    """Drop SDL-bound fonts before pygame teardown or display replacement."""
    global _FONT_CACHE_DISPLAY
    _FONT_CACHE.clear()
    _FONT_CACHE_DISPLAY = None


def set_text_scale(scale: float = 1.0) -> float:
    """Set the authoritative logical-to-rendered text scale for UI helpers."""
    global _TEXT_SCALE
    try:
        value = float(scale)
    except (TypeError, ValueError):
        value = 1.0
    _TEXT_SCALE = max(1.0, min(2.0, value))
    return _TEXT_SCALE


def configure_for(game=None, *, large_text: bool | None = None) -> float:
    """Apply a game's text preference without retaining the game object."""
    if large_text is None:
        preferences = getattr(game, "preferences", None)
        large_text = bool(getattr(preferences, "large_text", False))
    return set_text_scale(LARGE_TEXT_SCALE if large_text else 1.0)


def text_scale() -> float:
    return _TEXT_SCALE


def scaled_size(size: int | float) -> int:
    return max(1, round(float(size) * _TEXT_SCALE))


@contextmanager
def capture_geometry():
    """Collect card/panel rectangles for headless layout instrumentation."""
    global _GEOMETRY_TRACE
    previous = _GEOMETRY_TRACE
    captured = []
    _GEOMETRY_TRACE = captured
    try:
        yield captured
    finally:
        _GEOMETRY_TRACE = previous


@contextmanager
def capture_text():
    """Collect localized text and its actual rendered rectangles."""
    global _TEXT_TRACE
    previous = _TEXT_TRACE
    captured = []
    _TEXT_TRACE = captured
    try:
        yield captured
    finally:
        _TEXT_TRACE = previous


def record_text(text: str, rendered_rect, bounds) -> None:
    if _TEXT_TRACE is not None and text:
        _TEXT_TRACE.append({
            "text": str(text),
            "rect": pygame.Rect(rendered_rect).copy(),
            "bounds": pygame.Rect(bounds).copy(),
        })


def record_geometry(kind: str, rect, title: str = "") -> None:
    """Record a bounded UI region when ``capture_geometry`` is active."""
    if _GEOMETRY_TRACE is not None:
        _GEOMETRY_TRACE.append({
            "kind": kind, "title": str(title), "rect": pygame.Rect(rect).copy(),
            "text_scale": _TEXT_SCALE,
        })


def font(size: int, bold: bool = False) -> pygame.font.Font:
    global _FONT_CACHE_DISPLAY
    if not pygame.font.get_init():
        clear_font_cache()
        pygame.font.init()
    display = pygame.display.get_surface()
    # Tests and standalone tools can quit/reinitialize SDL between surfaces.
    # Cache only while a live display provides a stable SDL lifetime token.
    if display is None:
        return pygame.font.SysFont("monospace", scaled_size(size), bold=bold)
    if display is not _FONT_CACHE_DISPLAY:
        clear_font_cache()
        _FONT_CACHE_DISPLAY = display
    rendered_size = scaled_size(size)
    key = (rendered_size, bold)
    f = _FONT_CACHE.get(key)
    if f is None:
        f = pygame.font.SysFont("monospace", rendered_size, bold=bold)
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


def ellipsize(text: object, f: pygame.font.Font, width_px: int,
              suffix: str = "...") -> str:
    """Return one explicit, width-bounded line."""
    value = str(text)
    if width_px <= 0:
        return ""
    if f.size(value)[0] <= width_px:
        return value
    if f.size(suffix)[0] > width_px:
        return ""
    low, high = 0, len(value)
    while low < high:
        middle = (low + high + 1) // 2
        if f.size(value[:middle] + suffix)[0] <= width_px:
            low = middle
        else:
            high = middle - 1
    return value[:low] + suffix


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
        lines[-1] = ellipsize(last + "...", f, width_px)
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
            image = f.render(line, True, color)
            rendered = image.get_rect(topleft=(px, y + i * lh))
            record_text(line, rendered, rect)
            screen.blit(image, rendered)


def box(screen, rect, title: str = "", border=None, fill=(14, 24, 18),
        title_size: int = 16) -> tuple:
    """Zeichnet eine Box und liefert ihr garantiert inneres Rechteck."""
    x, y, w, h = rect
    record_geometry("box", rect, title)
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
    record_geometry("panel", rect, title)
    pygame.draw.rect(screen, (14, 24, 18), (x, y, w, h))
    pygame.draw.rect(screen, config.COLOR_SONAR_RING, (x, y, w, h), 1)
    title = localize(title)
    if title:
        f, lines = fit_text(title, title_size, w - 28, 40, min_size=12)
        image = f.render(lines[0], True, config.COLOR_TEXT)
        rendered = image.get_rect(topleft=(x + 14, y + 8))
        record_text(lines[0], rendered, (x + 14, y + 8, w - 28, 40))
        screen.blit(image, rendered)
        return y + 8 + _line_height(f) + 8
    return y + 12


def status_line(screen, x: int, y: int, w: int, label: str, value: str,
                color=None, dim_color=None, size: int = 15,
                label_w: int = 130) -> None:
    """'Label  Wert' – beide Hälften einzeln gekürzt, nie Überlauf."""
    f = font(size)
    col = color or config.COLOR_TEXT
    dcol = dim_color or config.COLOR_TEXT_DIM
    lab = ellipsize(localize(label), f, label_w - 4)
    value = localize(value)
    val = value
    rest = w - label_w - 4
    val = ellipsize(value, f, rest)
    with clip_to(screen, (x, y, w, f.get_linesize())):
        label_image = f.render(lab, True, dcol)
        value_image = f.render(val, True, col)
        bounds = pygame.Rect(x, y, w, f.get_linesize())
        label_rect = label_image.get_rect(topleft=(x, y))
        value_rect = value_image.get_rect(topleft=(x + label_w + 4, y))
        record_text(lab, label_rect, bounds)
        record_text(val, value_rect, bounds)
        screen.blit(label_image, label_rect)
        screen.blit(value_image, value_rect)


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
    retained = lines[:12]
    if len(lines) > 12:
        retained[-1] = "... (more omitted)"
    return tooltip_payload(value["title"], *retained,
                           target_id=value.get("id", ""))


def tooltip_rect(payload: dict, pointer, bounds=(0, 0, 1280, 720),
                  max_width: int = 420) -> tuple[pygame.Rect, list[str]]:
    """Lay out a readable tooltip, flipping and clamping it at canvas edges."""
    bounds = pygame.Rect(bounds)
    inset_x = min(8, max(0, bounds.w // 4))
    inset_y = min(8, max(0, bounds.h // 4))
    safe = bounds.inflate(-inset_x * 2, -inset_y * 2)
    title_font = font(TOOLTIP_TITLE_SIZE, bold=True)
    body_font = font(TOOLTIP_BODY_SIZE)
    available = max(1, min(max_width, safe.w))
    title = str(payload.get("title", ""))
    body = [str(line) for line in payload.get("lines", [])]
    natural = max([title_font.size(title)[0]] +
                  [body_font.size(line)[0] for line in body] + [0]) + 24
    width = max(min(180, available), min(available, natural))
    title_lines = wrap_text(title, title_font, width - 24) or [""]
    body_lines = []
    for line in body:
        body_lines.extend(wrap_text(line, body_font, width - 24) or [""])
    title_h = _line_height(title_font)
    body_h = _line_height(body_font)
    max_height = max(1, safe.h)
    max_title_lines = max(1, (max_height - 16) // title_h)
    if len(title_lines) > max_title_lines:
        title_lines = title_lines[:max_title_lines]
        title_lines[-1] = ellipsize(title_lines[-1] + "...", title_font,
                                    width - 24)
        body_lines = []
    available_body_h = max(0, max_height - 16 - len(title_lines) * title_h)
    visible_body = available_body_h // body_h
    truncated = len(body_lines) > visible_body
    body_lines = body_lines[:visible_body]
    if truncated and body_lines:
        body_lines[-1] = ellipsize(body_lines[-1] + "...", body_font,
                                   width - 24)
    elif truncated and title_lines:
        title_lines[-1] = ellipsize(title_lines[-1] + "...", title_font,
                                    width - 24)
    lines = title_lines + body_lines
    height = min(max_height, max(44, 16 + len(title_lines) * title_h
                                 + len(body_lines) * body_h))
    x, y = int(pointer[0]) + 14, int(pointer[1]) + 18
    if x + width > bounds.right - 8:
        x = int(pointer[0]) - width - 14
    if y + height > bounds.bottom - 8:
        y = int(pointer[1]) - height - 14
    rect = pygame.Rect(x, y, width, height)
    rect.clamp_ip(safe)
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
    title_font = font(TOOLTIP_TITLE_SIZE, bold=True)
    body_font = font(TOOLTIP_BODY_SIZE)
    title_lines = wrap_text(payload["title"], title_font, rect.w - 24) or [""]
    title_count = min(len(title_lines), len(lines))
    title_h = _line_height(title_font)
    body_h = _line_height(body_font)
    with clip_to(screen, rect.inflate(-10, -8)):
        for index, line in enumerate(lines):
            is_title = index < title_count
            face = title_font if is_title else body_font
            color = config.COLOR_TEXT if is_title else config.COLOR_TEXT_DIM
            y = (rect.y + 8 + index * title_h if is_title else
                 rect.y + 8 + title_count * title_h
                 + (index - title_count) * body_h)
            screen.blit(face.render(line, True, color),
                        (rect.x + 12, y))
    return rect


def bearing_pair(observed_bearing: float, own_course: float) -> tuple[float, float]:
    """Return north-referenced true and clockwise ship-relative bearings."""
    true_bearing = float(observed_bearing) % 360.0
    relative = (true_bearing - float(own_course)) % 360.0
    return true_bearing, relative


def format_bearing_pair(observed_bearing: float, own_course: float) -> str:
    """Describe an observed bearing without implying target ground truth."""
    true_bearing, relative = bearing_pair(observed_bearing, own_course)
    return localize(message("bearing.observed_pair",
                            true=f"{true_bearing:05.1f}",
                            relative=f"{relative:05.1f}"))
