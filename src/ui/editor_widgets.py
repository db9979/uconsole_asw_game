"""Small bounded pygame widgets shared by standalone editors."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
import math
from typing import Any, Callable, Iterable

import pygame

from src.core.i18n import localize, raw_text
from src.ui import layout


Tr = Callable[[str], str]
IDENTITY_TR: Tr = lambda value: value


@dataclass(frozen=True)
class EditorPalette:
    background: tuple[int, int, int] = (8, 14, 17)
    panel: tuple[int, int, int] = (14, 25, 29)
    raised: tuple[int, int, int] = (23, 39, 43)
    border: tuple[int, int, int] = (62, 125, 128)
    text: tuple[int, int, int] = (200, 232, 214)
    dim: tuple[int, int, int] = (116, 150, 142)
    focus: tuple[int, int, int] = (232, 183, 74)
    danger: tuple[int, int, int] = (224, 91, 79)
    friendly: tuple[int, int, int] = (92, 174, 225)
    hostile: tuple[int, int, int] = (224, 91, 79)
    neutral: tuple[int, int, int] = (202, 198, 132)


PALETTE = EditorPalette()


def font(size: int = 16, bold: bool = False) -> pygame.font.Font:
    return layout.font(size, bold)


def clear_font_cache() -> None:
    """Shared editor/runtime font-cache teardown hook."""
    layout.clear_font_cache()


@contextmanager
def clipped(surface: pygame.Surface, rect: pygame.Rect | tuple[int, int, int, int]):
    old = surface.get_clip()
    surface.set_clip(old.clip(pygame.Rect(rect)))
    try:
        yield
    finally:
        surface.set_clip(old)


def ellipsize(value: object, width: int, text_font: pygame.font.Font) -> str:
    return layout.ellipsize(value, text_font, width)


def draw_text(surface: pygame.Surface, value: object,
              rect: pygame.Rect | tuple[int, int, int, int], *, color=None,
              size: int = 16, bold: bool = False, align: str = "left") -> None:
    rect = pygame.Rect(rect)
    if rect.width <= 0 or rect.height <= 0:
        return
    text_font = font(size, bold)
    value = ellipsize(localize(value), rect.width, text_font)
    image = text_font.render(value, True, color or PALETTE.text)
    x = rect.x
    if align == "center":
        x += max(0, (rect.width - image.get_width()) // 2)
    elif align == "right":
        x += max(0, rect.width - image.get_width())
    y = rect.y + max(0, (rect.height - image.get_height()) // 2)
    with clipped(surface, rect):
        surface.blit(image, (x, y))


def panel(surface: pygame.Surface, rect: pygame.Rect | tuple[int, int, int, int],
          title: str = "", *, tr: Tr = IDENTITY_TR) -> pygame.Rect:
    rect = pygame.Rect(rect)
    pygame.draw.rect(surface, PALETTE.panel, rect)
    pygame.draw.rect(surface, PALETTE.border, rect, 1)
    inner = rect.inflate(-16, -16)
    if title:
        draw_text(surface, tr(title), (inner.x, inner.y, inner.width, 26), bold=True)
        inner.y += 30
        inner.height = max(0, inner.height - 30)
    return inner


def event_position(event: pygame.event.Event) -> tuple[int, int] | None:
    position = getattr(event, "pos", None)
    return tuple(position) if position is not None else None


class ListBox:
    """Keyboard, wheel, click, and trackball-motion friendly list selection."""

    def __init__(self, items: Iterable[str] = (), selected: int = 0):
        self.items = list(items)
        self.selected = selected
        self.scroll = 0

    def set_items(self, items: Iterable[str]) -> None:
        self.items = list(items)
        self.selected = max(0, min(self.selected, len(self.items) - 1))

    def move(self, amount: int) -> bool:
        if not self.items:
            return False
        before = self.selected
        self.selected = max(0, min(len(self.items) - 1, self.selected + amount))
        return before != self.selected

    def handle_event(self, event: pygame.event.Event, rect: pygame.Rect,
                     row_height: int = 28) -> bool:
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_UP, pygame.K_k):
                return self.move(-1)
            if event.key in (pygame.K_DOWN, pygame.K_j):
                return self.move(1)
            if event.key == pygame.K_PAGEUP:
                return self.move(-max(1, rect.height // row_height))
            if event.key == pygame.K_PAGEDOWN:
                return self.move(max(1, rect.height // row_height))
            if event.key == pygame.K_HOME:
                return self.move(-len(self.items))
            if event.key == pygame.K_END:
                return self.move(len(self.items))
        position = event_position(event)
        if event.type == pygame.MOUSEWHEEL and (position is None or rect.collidepoint(position)):
            return self.move(-event.y)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and position and rect.collidepoint(position):
            index = self.scroll + (position[1] - rect.y) // row_height
            if 0 <= index < len(self.items):
                changed = index != self.selected
                self.selected = index
                return changed
        return False

    def draw(self, surface: pygame.Surface, rect: pygame.Rect, *, tr: Tr = IDENTITY_TR,
             row_height: int = 28) -> None:
        pygame.draw.rect(surface, PALETTE.background, rect)
        visible = max(1, rect.height // row_height)
        self.scroll = max(0, min(self.scroll, max(0, len(self.items) - visible)))
        if self.selected < self.scroll:
            self.scroll = self.selected
        if self.selected >= self.scroll + visible:
            self.scroll = self.selected - visible + 1
        with clipped(surface, rect):
            for row, item in enumerate(self.items[self.scroll:self.scroll + visible]):
                index = self.scroll + row
                row_rect = pygame.Rect(rect.x, rect.y + row * row_height, rect.width, row_height)
                if index == self.selected:
                    pygame.draw.rect(surface, PALETTE.raised, row_rect)
                    pygame.draw.rect(surface, PALETTE.focus, row_rect, 1)
                draw_text(surface, raw_text(tr(item)), row_rect.inflate(-8, 0),
                          color=PALETTE.text if index == self.selected else PALETTE.dim,
                          size=14)


class TextField:
    def __init__(self, value: str = "", maximum: int = 256):
        self.value = value
        self.maximum = maximum
        self.selected_all = False
        self._key_text = ""

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type != pygame.KEYDOWN:
            return False
        if event.key == pygame.K_BACKSPACE:
            self.value = "" if self.selected_all else self.value[:-1]
            self.selected_all = False
            self._key_text = ""
            return True
        if event.key == pygame.K_a and getattr(event, "mod", 0) & pygame.KMOD_CTRL:
            self.selected_all = True
            return True
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_ESCAPE, pygame.K_TAB):
            return False
        char = getattr(event, "unicode", "")
        if char and char.isprintable() and len(self.value) < self.maximum:
            if self.selected_all:
                self.value = ""
                self.selected_all = False
            self.value += char
            self._key_text = char
            return True
        return False

    def handle_text(self, text: str) -> bool:
        """Accept TEXTINPUT while suppressing its duplicate KEYDOWN unicode."""
        if not text:
            return False
        if text == self._key_text:
            self._key_text = ""
            return True
        self._key_text = ""
        if self.selected_all:
            self.value = ""
            self.selected_all = False
        available = self.maximum - len(self.value)
        self.value += text[:available]
        return available > 0

    def draw(self, surface: pygame.Surface, rect: pygame.Rect, *, focused: bool = False) -> None:
        pygame.draw.rect(surface, PALETTE.background, rect)
        pygame.draw.rect(surface, PALETTE.focus if focused else PALETTE.border, rect, 2 if focused else 1)
        shown = self.value + ("_" if focused else "")
        text_font = font(15)
        available = max(1, rect.width - 16)
        if text_font.size(shown)[0] > available:
            low, high = 0, len(shown)
            while low < high:
                middle = (low + high) // 2
                if text_font.size(shown[middle:])[0] <= available:
                    high = middle
                else:
                    low = middle + 1
            shown = shown[low:]
        draw_text(surface, raw_text(shown), rect.inflate(-8, -2), size=15)


@dataclass
class FieldRow:
    """One editable value. The setter is called only after successful parsing."""

    path: str
    label: str
    value: Any
    setter: Callable[[Any], None]


def value_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None or isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def parse_value(text: str, existing: Any) -> Any:
    """Parse an edit according to the existing type, never executing input."""
    if isinstance(existing, bool):
        normalized = text.strip().lower()
        if normalized not in ("true", "false"):
            raise ValueError("use true or false")
        return normalized == "true"
    if isinstance(existing, int):
        try:
            return int(text.strip())
        except ValueError as exc:
            raise ValueError("must be an integer") from exc
    if isinstance(existing, float):
        try:
            value = float(text.strip())
        except ValueError as exc:
            raise ValueError("must be a number") from exc
        if not math.isfinite(value):
            raise ValueError("must be a finite number")
        return value
    if isinstance(existing, str):
        return text

    def reject_constant(value: str):
        raise ValueError(f"invalid JSON constant {value}")

    try:
        value = json.loads(text, parse_constant=reject_constant)
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise ValueError("must be valid JSON") from exc
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("JSON numbers must be finite")
        if isinstance(item, dict):
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    if existing is not None and not isinstance(value, type(existing)):
        raise ValueError(f"must be a JSON {type(existing).__name__}")
    return value


class FieldList:
    """Scrollable focusable rows with transactional keyboard text editing."""

    def __init__(self):
        self.rows: list[FieldRow] = []
        self.selected = 0
        self.scroll = 0
        self.editing = False
        self.input = TextField(maximum=4096)
        self.original: Any = None
        self.error = ""

    @property
    def selected_row(self) -> FieldRow | None:
        return self.rows[self.selected] if self.rows else None

    def set_rows(self, rows: Iterable[FieldRow]) -> None:
        old_path = self.selected_row.path if self.selected_row else None
        self.rows = list(rows)
        if old_path is not None:
            self.selected = next((index for index, row in enumerate(self.rows)
                                  if row.path == old_path), self.selected)
        self.selected = max(0, min(self.selected, len(self.rows) - 1))

    def begin_edit(self) -> bool:
        row = self.selected_row
        if row is None:
            return False
        self.original = row.value
        self.input.value = value_text(row.value)
        self.input.selected_all = True
        self.input._key_text = ""
        self.editing = True
        self.error = ""
        return True

    def cancel_edit(self) -> bool:
        if not self.editing:
            return False
        self.editing = False
        self.error = ""
        return True

    def apply_edit(self) -> bool:
        row = self.selected_row
        if not self.editing or row is None:
            return False
        try:
            value = parse_value(self.input.value, self.original)
            row.setter(value)
        except (TypeError, ValueError, KeyError) as exc:
            self.error = f"{row.path}: {exc}"
            return True
        self.editing = False
        self.error = ""
        return True

    def move(self, amount: int) -> bool:
        if self.editing or not self.rows:
            return False
        before = self.selected
        self.selected = max(0, min(len(self.rows) - 1, self.selected + amount))
        return before != self.selected

    def handle_event(self, event: pygame.event.Event, rect: pygame.Rect,
                     row_height: int = 32) -> bool:
        if self.editing:
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    return self.apply_edit()
                if event.key == pygame.K_ESCAPE:
                    return self.cancel_edit()
                return self.input.handle_event(event)
            if event.type == pygame.TEXTINPUT:
                return self.input.handle_text(getattr(event, "text", ""))
            return False
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_UP, pygame.K_k):
                return self.move(-1)
            if event.key in (pygame.K_DOWN, pygame.K_j):
                return self.move(1)
            if event.key == pygame.K_PAGEUP:
                return self.move(-max(1, rect.height // row_height))
            if event.key == pygame.K_PAGEDOWN:
                return self.move(max(1, rect.height // row_height))
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                return self.begin_edit()
        position = event_position(event)
        if event.type == pygame.MOUSEWHEEL and (position is None or rect.collidepoint(position)):
            return self.move(-event.y)
        if (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and position
                and rect.collidepoint(position)):
            index = self.scroll + (position[1] - rect.y) // row_height
            if 0 <= index < len(self.rows):
                changed = index != self.selected
                self.selected = index
                if getattr(event, "clicks", 1) >= 2:
                    self.begin_edit()
                return True if changed or self.editing else True
        return False

    def draw(self, surface: pygame.Surface, rect: pygame.Rect, *, tr: Tr = IDENTITY_TR,
             label_width: int = 245, row_height: int = 32) -> None:
        pygame.draw.rect(surface, PALETTE.background, rect)
        visible = max(1, rect.height // row_height)
        self.scroll = max(0, min(self.scroll, max(0, len(self.rows) - visible)))
        if self.selected < self.scroll:
            self.scroll = self.selected
        elif self.selected >= self.scroll + visible:
            self.scroll = self.selected - visible + 1
        with clipped(surface, rect):
            for screen_row, row in enumerate(self.rows[self.scroll:self.scroll + visible]):
                index = self.scroll + screen_row
                row_rect = pygame.Rect(rect.x, rect.y + screen_row * row_height,
                                       rect.width, row_height)
                selected = index == self.selected
                if selected:
                    pygame.draw.rect(surface, PALETTE.raised, row_rect)
                    pygame.draw.rect(surface, PALETTE.focus, row_rect, 1)
                label_rect = pygame.Rect(row_rect.x + 7, row_rect.y, min(label_width, row_rect.width // 2), row_height)
                value_rect = pygame.Rect(label_rect.right + 6, row_rect.y + 3,
                                         max(1, row_rect.right - label_rect.right - 12), row_height - 6)
                draw_text(surface, tr(row.label), label_rect, color=PALETTE.text if selected else PALETTE.dim,
                          size=13)
                if selected and self.editing:
                    self.input.draw(surface, value_rect, focused=True)
                else:
                    draw_text(surface, raw_text(value_text(row.value)), value_rect, size=14)


def mapping_rows(value: dict[str, Any], prefix: str = "") -> list[FieldRow]:
    """Flatten dictionaries into editable leaves; arrays remain safe JSON fields."""
    rows: list[FieldRow] = []

    def visit(current: dict[str, Any], current_prefix: str) -> None:
        for key, item in current.items():
            path = f"{current_prefix}.{key}" if current_prefix else key
            if isinstance(item, dict):
                visit(item, path)
                continue

            def assign(new_value: Any, target=current, field=key) -> None:
                target[field] = new_value

            rows.append(FieldRow(path, "field." + key, item, assign))

    visit(value, prefix)
    return rows


def draw_footer(surface: pygame.Surface, rect: pygame.Rect, hints: Iterable[str],
                *, tr: Tr = IDENTITY_TR) -> None:
    pygame.draw.rect(surface, PALETTE.raised, rect)
    draw_text(surface, " | ".join(tr(hint) for hint in hints), rect.inflate(-10, 0),
              color=PALETTE.dim, size=13)
