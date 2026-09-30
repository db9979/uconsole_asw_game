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
            part for part in (p.strip() for p in label.replace(" / ", "/").split("/")) if part]
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
