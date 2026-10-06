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
    # A panel drawn over the station (the F11 log): the click ends here and
    # never reaches a station control underneath; no hover frame.
    blocker: bool = False


_targets: list[Target] = []
_layer = ["station"]
# Hover notes of status lamps: (rect, layer, payload or a function making
# it), rebuilt every frame like the targets.
MAX_TIPS = 128
_tips: list[tuple] = []
# Wheel regions: (rect, layer, up key token, down key token), rebuilt per frame.
_scrolls: list[tuple] = []


def reset() -> None:
    """Start a new frame (called before drawing)."""
    _targets.clear()
    _tips.clear()
    _scrolls.clear()
    del _layer[1:]
    _layer[0] = "station"


def add_scroll(rect, up=None, down=None) -> None:
    """The mouse wheel over ``rect`` presses ``up``/``down`` (key tokens, as
    in a footer legend): a long list scrolls where it is shown."""
    if len(_scrolls) < MAX_TARGETS:
        _scrolls.append((pygame.Rect(rect), _layer[-1], up or "↑", down or "↓"))


def scroll_at(pos, layer_name: str = "station"):
    """``(up_key, down_key)`` of the topmost scroll region under ``pos``."""
    if pos is None:
        return None
    for rect, name, up, down in reversed(_scrolls):
        if name == layer_name and rect.collidepoint(pos):
            return up, down
    return None


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
    """A click on ``rect`` calls ``action(pos)`` with the canvas position
    (UI state only)."""
    if len(_targets) < MAX_TARGETS:
        _targets.append(Target(pygame.Rect(rect), _layer[-1], action=action))


def add_hotspot(rect) -> None:
    """``rect`` is clickable through the station's own hit test: hover only."""
    if len(_targets) < MAX_TARGETS:
        _targets.append(Target(pygame.Rect(rect), _layer[-1], hover_only=True))


def add_blocker(rect) -> None:
    """``rect`` is a panel over the station: clicks inside it do nothing
    (targets registered after it, such as its close box, still work), and
    no station target or lamp note under it reacts to the mouse."""
    if len(_targets) < MAX_TARGETS:
        _targets.append(Target(pygame.Rect(rect), _layer[-1],
                               action=lambda _pos: None, blocker=True))
    if len(_tips) < MAX_TIPS:
        _tips.append((pygame.Rect(rect), _layer[-1], lambda: None))


def blocked(pos, owner: str) -> bool:
    """True when ``pos`` lies on a panel registered with :func:`add_blocker`."""
    return pos is not None and any(
        target.blocker and target.layer == owner and target.rect.collidepoint(pos)
        for target in _targets)


def add_tip(rect, tip) -> None:
    """Hovering ``rect`` shows ``tip``: a tooltip payload
    (``layout.tooltip_payload``) or a function returning one, called only
    while the pointer is over it."""
    if tip is not None and len(_tips) < MAX_TIPS:
        _tips.append((pygame.Rect(rect), _layer[-1], tip))


def tip_at(pos, layer_name: str = "station"):
    """The payload of the topmost lamp note under ``pos``, or None."""
    if pos is None:
        return None
    for rect, name, tip in reversed(_tips):
        if name == layer_name and rect.collidepoint(pos):
            return tip() if callable(tip) else tip
    return None


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
    return None if target is None or target.blocker else target.rect


# --- footer legends ---------------------------------------------------------------

_NAMED_KEYS = {
    "enter": pygame.K_RETURN, "return": pygame.K_RETURN, "eingabe": pygame.K_RETURN,
    "backspace": pygame.K_BACKSPACE, "space": pygame.K_SPACE, "leertaste": pygame.K_SPACE,
    "tab": pygame.K_TAB, "esc": pygame.K_ESCAPE, "del": pygame.K_DELETE,
    "entf": pygame.K_DELETE, "pgup": pygame.K_PAGEUP, "pgdn": pygame.K_PAGEDOWN,
    "bild↑": pygame.K_PAGEUP, "bild↓": pygame.K_PAGEDOWN,
    "rücktaste": pygame.K_BACKSPACE, "rück": pygame.K_BACKSPACE, "pos1": pygame.K_HOME,
    "home": pygame.K_HOME, "end": pygame.K_END, "ende": pygame.K_END,
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
          "help.key.ctrl_m": ("Ctrl+M",),
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
    from src.ui import layout
    if separator is None:
        separator = " | " if " | " in text else " · "
    parts = text.split(separator)
    total = layout.text_width(face, text)
    height = face.get_linesize()
    x = center_x - total // 2
    sep_w = layout.text_width(face, separator)
    for part, key in zip(parts, keys):
        width = layout.text_width(face, part)
        rect = pygame.Rect(x - 4, center_y - height // 2 - 2, width + 8, height + 4)
        if isinstance(key, str):
            # "[ / ]" splits the part: left half the first key, right the second.
            add_legend(rect, key)
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
    total = max(1, layout.text_width(face, text))
    scale = min(1.0, rect.w / total)
    shown = total * scale
    x = (rect.x if align == "left" else rect.right - shown if align == "right"
         else rect.centerx - shown / 2)
    sep_w = layout.text_width(face, separator) * scale
    height = min(rect.h, face.get_linesize() + 4)
    top = rect.y + max(0, (rect.h - height) // 2)
    for part, spec in zip(parts, keys):
        width = layout.text_width(face, part) * scale
        area = pygame.Rect(round(x) - 3, top, round(width) + 6, height).clip(
            rect.inflate(6, 0))
        if area.w > 4:
            add_spec(area, spec)
        x += width + sep_w


_SEPARATORS = (" | ", " · ", "  ", " / ")


def token_matches(text: str, tokens) -> list:
    """``(start, token_end, end, spec)`` of each key token found in ``text``:
    where the token itself ends and where its part ends (see
    :func:`token_spans`)."""
    import re
    from src.core.i18n import german_key_label
    found = []
    cursor = 0
    for token, spec in tokens:
        # One token list serves both languages: the German texts write
        # Umschalt, Strg, Eingabe ... (i18n.german_key_label).
        match = None
        for spelling in dict.fromkeys((token, german_key_label(token))):
            pattern = re.compile((r"(?<![\w+/])" if spelling[:1].isalnum() else "")
                                 + re.escape(spelling)
                                 + (r"(?![\w+])" if spelling[-1:].isalnum() else ""))
            match = pattern.search(text, cursor)
            if match is not None:
                break
        if match is None:
            continue
        found.append((match.start(), match.end(), spec))
        cursor = match.end()
    spans = []
    for index, (start, token_end, spec) in enumerate(found):
        end = found[index + 1][0] if index + 1 < len(found) else len(text)
        for separator in _SEPARATORS[:3]:
            cut = text.find(separator, start + 1)
            if 0 <= cut < end:
                end = cut
        spans.append((start, token_end, len(text[:end].rstrip()), spec))
    return spans


def token_spans(text: str, tokens) -> list:
    """``(start, end, spec)`` of each key token found in ``text``, in order.

    A token (``"H:"``, ``"Shift+A"``, ``"U/V"``) counts only as a whole word;
    its part runs to the next token or the next separator (`` | ``, `` · ``,
    two spaces), whichever comes first.  Tokens not found are skipped, so
    one token list serves English and German.
    """
    return [(start, end, spec) for start, _token_end, end, spec
            in token_matches(text, tokens)]


# Words that name a key (drawn as a key cap); any other token word, such as
# "Mast", stays plain text that is only clickable.
_KEY_WORDS = {"enter", "eingabe", "esc", "tab", "space", "leertaste", "backspace",
              "pos1", "home", "end", "ende", "arrows", "pfeile", "pfeiltasten",
              "bild", "pgup", "pgdn", "auf", "up", "down", "umsch", "rücktaste",
              "rück", "entf", "bild↑", "bild↓"}


def key_cap_text(token: str) -> tuple[int, int] | None:
    """The part of ``token`` drawn as a key cap, as ``(start, end)``
    offsets (``"(Shift+F)"`` -> ``Shift+F``, ``"H:"`` -> ``H``), or None
    for a word that is not a key name."""
    start, end = 0, len(token)
    while start < end and token[start] in "([":
        start += 1
    while end > start and token[end - 1] in ":)].,/":
        end -= 1
    core = token[start:end]
    if not core:
        return None
    words = core.replace("+", " ").replace("/", " ").split()
    if all(len(word) <= 2 or word.lower() in _KEY_WORDS
           or word.lower() in ("shift", "umschalt", "ctrl", "strg", "alt", "fn")
           or (word[:1] in "Ff" and word[1:].isdigit())
           for word in words):
        return start, end
    return None


def add_token_keys(rect, text, size: int, tokens, align: str = "left",
                   min_size: int | None = None, screen=None) -> None:
    """Register the key tokens of a hint drawn by ``layout.blit_line`` (or
    ``blit_block`` with its ``min_size``) in ``rect``: the same fitting, so
    a shrunk, wrapped or shortened line keeps its parts where they are drawn.

    ``text`` is what was drawn (catalog key, message or text); ``tokens``
    holds ``(token, spec)`` pairs, see :func:`token_spans`.  With ``screen``
    each token that names a key is also drawn as the stations' blue key cap
    over the text just drawn, so a key in prose looks like the footer chips.
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
        line_keys(screen, face, line, left, y + index * pitch, tokens, bounds)


def line_keys(screen, face, line: str, left: int, top: int, tokens, bounds=None) -> None:
    """Register (and with ``screen`` draw as key caps) the key tokens of one
    line already drawn with ``face`` at ``(left, top)``."""
    from src.ui import layout
    pitch = layout._line_height(face)
    if bounds is None:
        bounds = pygame.Rect(left - 3, top, layout.text_width(face, line) + 6, pitch)
    bounds = pygame.Rect(bounds)
    for start, token_end, end, spec in token_matches(line, tuple(tokens)):
        x0 = left + layout.text_width(face, line[:start])
        x1 = left + layout.text_width(face, line[:end])
        area = pygame.Rect(x0 - 3, top, x1 - x0 + 6, pitch).clip(bounds)
        if area.w > 4 and area.h > 4:
            add_spec(area, spec)
        if screen is not None:
            cap = key_cap_text(line[start:token_end])
            if cap is not None:
                layout.key_cap(screen, face, line[start + cap[0]:start + cap[1]],
                               (left + layout.text_width(face, line[:start + cap[0]]), top),
                               pitch, bounds)
