"""Mouse targets of the last drawn frame (full mouse control on the uConsole).

Drawing code registers what a click on a rectangle does: press a key (the
footer legends, station tabs, instrument buttons) or run a small UI action
(pick a menu row).  ``Game.handle_event`` looks the click up in the targets
of the frame the player saw and hands a key target to the normal keyboard
path, so a click does exactly what its key does, with the same input
ownership, confirmations and checks.  A target held down behaves like a held
key (release ends it).

Every target belongs to a layer ("station", "menu", "overlay" or "end"), and
only the layer that owns input takes clicks, so a station legend under an
open overlay can never be pressed.  Registration is display state: bounded,
rebuilt every frame, never saved and never read by the simulation.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable

import pygame

MAX_TARGETS = 256
LAYERS = ("station", "menu", "overlay", "end")


@dataclass(frozen=True)
class Target:
    rect: pygame.Rect
    layer: str
    key: int | None = None
    mod: int = 0
    action: Callable | None = None
    # Hover only: the station's own hit test takes the click (page tabs,
    # sonar segments, OPZ buttons); the target just shows it is clickable.
    hover_only: bool = False


_targets: list[Target] = []
_layer = ["station"]


def reset() -> None:
    """Start a new frame (called before drawing)."""
    _targets.clear()
    del _layer[1:]
    _layer[0] = "station"


@contextmanager
def layer(name: str):
    """Targets registered inside belong to ``name``."""
    _layer.append(name)
    try:
        yield
    finally:
        _layer.pop()


def add_key(rect, key: int, mod: int = 0) -> None:
    """A click on ``rect`` presses ``key`` (with ``mod``)."""
    if len(_targets) < MAX_TARGETS:
        _targets.append(Target(pygame.Rect(rect), _layer[-1], key=key, mod=mod))


def add_action(rect, action: Callable) -> None:
    """A click on ``rect`` calls ``action()`` (UI state only)."""
    if len(_targets) < MAX_TARGETS:
        _targets.append(Target(pygame.Rect(rect), _layer[-1], action=action))


def add_hotspot(rect) -> None:
    """``rect`` is clickable through the station's own hit test: hover only."""
    if len(_targets) < MAX_TARGETS:
        _targets.append(Target(pygame.Rect(rect), _layer[-1], hover_only=True))


def add_spec(rect, spec) -> None:
    """A click on ``rect`` presses ``spec``: a key code, ``(key, mod)``, a
    legend label (``"Shift+A"``, ``"U/V"``: split left/right), or a callable
    UI action; None leaves the rectangle display only."""
    if spec is None:
        return
    if callable(spec):
        add_action(rect, spec)
    elif isinstance(spec, str):
        add_legend(rect, spec)
    elif isinstance(spec, tuple):
        add_key(rect, *spec)
    else:
        add_key(rect, spec)


def hit(pos, owner: str) -> Target | None:
    """The topmost target of layer ``owner`` under ``pos`` (canvas pixels)."""
    if pos is None:
        return None
    for target in reversed(_targets):
        if target.layer == owner and target.rect.collidepoint(pos):
            return target
    return None


def targets(owner: str | None = None) -> list[Target]:
    return [t for t in _targets if owner is None or t.layer == owner]


def hover_rect(pos, owner: str) -> pygame.Rect | None:
    """The clickable rectangle under ``pos`` for the hover frame, or None."""
    target = hit(pos, owner)
    return None if target is None else target.rect


# --- footer legends ---------------------------------------------------------------

_NAMED_KEYS = {
    "enter": pygame.K_RETURN, "return": pygame.K_RETURN, "eingabe": pygame.K_RETURN,
    "backspace": pygame.K_BACKSPACE, "space": pygame.K_SPACE, "leertaste": pygame.K_SPACE,
    "tab": pygame.K_TAB, "esc": pygame.K_ESCAPE, "del": pygame.K_DELETE,
    "entf": pygame.K_DELETE, "pgup": pygame.K_PAGEUP, "pgdn": pygame.K_PAGEDOWN,
    "bild↑": pygame.K_PAGEUP, "bild↓": pygame.K_PAGEDOWN,
    "←": pygame.K_LEFT, "→": pygame.K_RIGHT, "↑": pygame.K_UP, "↓": pygame.K_DOWN,
    ",": pygame.K_COMMA, ".": pygame.K_PERIOD, "+": pygame.K_PLUS, "-": pygame.K_MINUS,
    "[": pygame.K_LEFTBRACKET, "]": pygame.K_RIGHTBRACKET, "0": pygame.K_0,
}
_MODS = {"shift": pygame.KMOD_SHIFT, "umschalt": pygame.KMOD_SHIFT,
         "ctrl": pygame.KMOD_CTRL, "strg": pygame.KMOD_CTRL, "alt": pygame.KMOD_ALT}
# Legend spellings that stand for two keys at once.
_PAIRS = {"help.key.page_arrows": ("PgUp", "PgDn"), "help.key.page": ("PgUp", "PgDn"),
          "help.key.page_spaced": ("PgUp", "PgDn"), "help.key.enter": ("Enter",),
          "help.key.uboot_blow": ("Shift+B",), "help.key.uboot_fire": ("Ctrl+Enter",),
          "help.key.left_right": ("←", "→"), "help.key.up_down": ("↑", "↓"),
          "help.key.up_down_hold": ("↑", "↓")}


def _one_key(text: str):
    text = text.strip()
    mod = 0
    while "+" in text[1:]:
        head, _, rest = text.partition("+")
        flag = _MODS.get(head.strip().lower())
        if flag is None:
            break
        mod |= flag
        text = rest.strip()
    lowered = text.lower()
    if lowered in _NAMED_KEYS:
        return _NAMED_KEYS[lowered], mod
    if len(text) == 1 and text.isalnum():
        return getattr(pygame, f"K_{text.lower()}", None), mod
    if len(text) >= 2 and text[0] == "F" and text[1:].isdigit():
        return getattr(pygame, f"K_F{int(text[1:])}", None), mod
    return None


def legend_keys(label) -> list[tuple[int, int]]:
    """Keys of a footer legend label (``"←/→"``, ``"Shift+B"``, ``"Enter"``).

    Unknown spellings give no keys (the segment then stays display only).
    """
    if not isinstance(label, str):
        return []
    parts = _PAIRS.get(label)
    if parts is None:
        parts = [label] if label.strip() == "/" else [
            word for part in label.replace(" / ", "/").split("/")
            for word in part.split() if word]
    keys = []
    for part in parts:
        found = _one_key(part)
        if found is None or found[0] is None:
            return []
        keys.append(found)
    return keys


def add_legend(rect, label) -> None:
    """Register a footer segment: one key, or two keys split left/right."""
    keys = legend_keys(label)
    if not keys:
        return
    rect = pygame.Rect(rect)
    width = max(1, rect.w // len(keys))
    for index, (key, mod) in enumerate(keys):
        part = pygame.Rect(rect.x + index * width, rect.y,
                           rect.right - rect.x - index * width if index == len(keys) - 1
                           else width, rect.h)
        add_key(part, key, mod)


def add_text_keys(text: str, face, center_x: int, center_y: int, keys,
                  separator: str | None = None) -> None:
    """Register each part of a centred one-line hint (``a | b | c``).

    ``keys`` holds one entry per part: a key code, ``(key, mod)``, a legend
    label such as ``"Enter"``, or None for a part that is text only.
    """
    if separator is None:
        separator = " | " if " | " in text else " · "
    parts = text.split(separator)
    total = face.size(text)[0]
    height = face.get_linesize()
    x = center_x - total // 2
    sep_w = face.size(separator)[0]
    for part, key in zip(parts, keys):
        width = face.size(part)[0]
        rect = pygame.Rect(x - 4, center_y - height // 2 - 2, width + 8, height + 4)
        if isinstance(key, str):
            found = legend_keys(key)
            if found:
                add_key(rect, *found[0])
        elif isinstance(key, tuple):
            add_key(rect, *key)
        elif key is not None:
            add_key(rect, key)
        x += width + sep_w


def add_line_keys(rect, text: str, size: int, keys, separator: str | None = None,
                  align: str = "left") -> None:
    """Register the parts of a one-line hint drawn by ``layout.blit_line``.

    ``text`` is the localized line, split at ``separator`` (`` | `` or `` · ``
    by default); ``keys`` holds one :func:`add_spec` entry per part (None:
    text only).  A line that had to shrink keeps its parts in proportion; a
    part that fell off the clipped line is not registered.
    """
    from src.ui import layout
    rect = pygame.Rect(rect)
    if not text or rect.w <= 0:
        return
    if separator is None:
        separator = " | " if " | " in text else " · "
    face = layout.font(size)
    parts = text.split(separator)
    total = max(1, face.size(text)[0])
    scale = min(1.0, rect.w / total)
    shown = total * scale
    x = (rect.x if align == "left" else rect.right - shown if align == "right"
         else rect.centerx - shown / 2)
    sep_w = face.size(separator)[0] * scale
    height = min(rect.h, face.get_linesize() + 4)
    top = rect.y + max(0, (rect.h - height) // 2)
    for part, spec in zip(parts, keys):
        width = face.size(part)[0] * scale
        area = pygame.Rect(round(x) - 3, top, round(width) + 6, height).clip(
            rect.inflate(6, 0))
        if area.w > 4:
            add_spec(area, spec)
        x += width + sep_w


_SEPARATORS = (" | ", " · ", "  ", " / ")


def token_spans(text: str, tokens) -> list:
    """``(start, end, spec)`` of each key token found in ``text``, in order.

    A token (``"H:"``, ``"Shift+A"``, ``"U/V"``) counts only as a whole word;
    its part runs to the next token or the next separator (`` | ``, `` · ``,
    two spaces), whichever comes first.  Tokens not found are skipped, so
    one token list serves English and German.
    """
    import re
    found = []
    cursor = 0
    for token, spec in tokens:
        pattern = re.compile((r"(?<![\w+/])" if token[:1].isalnum() else "")
                             + re.escape(token)
                             + (r"(?![\w+])" if token[-1:].isalnum() else ""))
        match = pattern.search(text, cursor)
        if match is None:
            continue
        found.append((match.start(), spec))
        cursor = match.end()
    spans = []
    for index, (start, spec) in enumerate(found):
        end = found[index + 1][0] if index + 1 < len(found) else len(text)
        for separator in _SEPARATORS[:3]:
            cut = text.find(separator, start + 1)
            if 0 <= cut < end:
                end = cut
        spans.append((start, len(text[:end].rstrip()), spec))
    return spans


def add_token_keys(rect, text, size: int, tokens, align: str = "left",
                   min_size: int | None = None) -> None:
    """Register the key tokens of a hint drawn by ``layout.blit_line`` (or
    ``blit_block`` with its ``min_size``) in ``rect``: the same fitting, so
    a shrunk, wrapped or shortened line keeps its parts where they are drawn.

    ``text`` is what was drawn (catalog key, message or text); ``tokens``
    holds ``(token, spec)`` pairs, see :func:`token_spans`.
    """
    from src.ui import layout
    x, y, w, h = pygame.Rect(rect)
    if w <= 0 or h <= 0:
        return
    if min_size is None:
        min_size = min(size, max(layout.MIN_OPERATIONAL_FONT, size - 4))
    min_size = min(min_size, size)
    fitted = layout.fit_block_text(text, w, h, min_size)
    if not fitted:
        return
    face, lines = layout.fit_text(fitted, size, w, h, min_size)
    pitch = layout._line_height(face)
    bounds = pygame.Rect(x - 3, y, w + 6, h)
    tokens = tuple(tokens)
    for index, line in enumerate(lines):
        width = layout.text_width(face, line)
        left = (x if align == "left" else x + w - width if align == "right"
                else x + max(0, (w - width) // 2))
        for start, end, spec in token_spans(line, tokens):
            x0 = left + layout.text_width(face, line[:start])
            x1 = left + layout.text_width(face, line[:end])
            area = pygame.Rect(x0 - 3, y + index * pitch, x1 - x0 + 6, pitch).clip(bounds)
            if area.w > 4 and area.h > 4:
                add_spec(area, spec)
