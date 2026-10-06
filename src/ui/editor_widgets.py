"""Small bounded pygame widgets shared by standalone editors."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
import math
from typing import Any, Callable, Iterable

import pygame

from src.core.i18n import localize, raw_text
from src.data.validation import ContentValidationError, issue, localized_error
from src.ui import layout


Tr = Callable[..., str]
IDENTITY_TR: Tr = lambda value, **_: value


@dataclass(frozen=True)
class EditorPalette:
    background: tuple[int, int, int] = (11, 15, 25)
    panel: tuple[int, int, int] = (17, 24, 39)
    raised: tuple[int, int, int] = (26, 35, 51)
    border: tuple[int, int, int] = (52, 80, 122)
    text: tuple[int, int, int] = (229, 231, 235)
    dim: tuple[int, int, int] = (139, 149, 167)
    focus: tuple[int, int, int] = (245, 158, 11)
    danger: tuple[int, int, int] = (239, 68, 68)
    friendly: tuple[int, int, int] = (96, 165, 250)
    hostile: tuple[int, int, int] = (248, 113, 113)
    neutral: tuple[int, int, int] = (251, 191, 36)


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
            # Window-to-canvas scaling (Game._window_to_canvas) can hand us
            # float pointer coordinates; row indices must stay integers.
            index = self.scroll + int((position[1] - rect.y) // row_height)
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
    def __init__(self, value: str = "", maximum: int = 256, *, secret: bool = False):
        self.value = value
        self.maximum = maximum
        self.secret = secret        # drawn as asterisks (an API key)
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
        shown = ("*" * len(self.value) if self.secret else self.value) + ("_" if focused else "")
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


class FilterField:
    """Bounded, IME-safe, case-insensitive substring filter box.

    Shared by every browser-style list (unit editor, tactical/contact
    analyzer): types directly into the filter with no separate focus step,
    using the same KEYDOWN/TEXTINPUT dedup trick as TextField.handle_text().
    Navigation keys (arrows, page, enter, escape, tab) are left unhandled so
    callers can still use them for list navigation.
    """

    def __init__(self, maximum: int = 48):
        self.text = ""
        self.maximum = maximum
        self._key_text = ""

    def set(self, value: str) -> None:
        self.text = value[:self.maximum]

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                self.set(self.text[:-1])
                self._key_text = ""
                return True
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_ESCAPE,
                             pygame.K_TAB, pygame.K_UP, pygame.K_DOWN,
                             pygame.K_LEFT, pygame.K_RIGHT, pygame.K_PAGEUP,
                             pygame.K_PAGEDOWN, pygame.K_HOME, pygame.K_END):
                return False
            char = getattr(event, "unicode", "")
            if char and char.isprintable() and len(self.text) < self.maximum:
                self.set(self.text + char)
                self._key_text = char
                return True
            return False
        if event.type == pygame.TEXTINPUT:
            text = "".join(char for char in getattr(event, "text", "")
                           if char.isprintable())
            if text == self._key_text:
                self._key_text = ""
                return True
            self._key_text = ""
            if text:
                self.set(self.text + text)
                return True
        return False

    def matches(self, *fields: object) -> bool:
        query = self.text.casefold()
        return not query or query in " ".join(str(f) for f in fields).casefold()

    def draw(self, surface: pygame.Surface, rect: pygame.Rect | tuple[int, int, int, int],
             *, placeholder: str = "", tr: Tr = IDENTITY_TR) -> None:
        rect = pygame.Rect(rect)
        pygame.draw.rect(surface, PALETTE.background, rect)
        pygame.draw.rect(surface, PALETTE.focus, rect, 1)
        shown = self.text or tr(placeholder)
        draw_text(surface, raw_text(shown), rect.inflate(-8, 0),
                  color=(PALETTE.text if self.text else PALETTE.dim), size=14)


@dataclass
class FieldRow:
    """One editable value. The setter is called only after successful parsing."""

    path: str
    label: str
    value: Any
    setter: Callable[[Any], None]
    header: bool = False
    # A closed value set: Enter opens a pick list of (value, display text)
    # instead of free text editing. Display text is drawn raw.
    choices: Callable[[], list[tuple[Any, str]]] | None = None


def section_header(group: str) -> FieldRow:
    """A non-selectable section heading row, grouping the fields under it."""
    return FieldRow(f"__section__{group}", group, None, lambda value: None,
                    header=True)


def value_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None or isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def parse_value(text: str, existing: Any, path: str = "") -> Any:
    """Parse an edit according to the existing type, never executing input."""
    if isinstance(existing, bool):
        normalized = text.strip().lower()
        if normalized not in ("true", "false"):
            raise ContentValidationError([issue(path, "boolean", "must be true or false")])
        return normalized == "true"
    if isinstance(existing, int):
        try:
            return int(text.strip())
        except ValueError as exc:
            raise ContentValidationError([issue(path, "integer", "must be an integer")]) from exc
    if isinstance(existing, float):
        try:
            value = float(text.strip())
        except ValueError as exc:
            raise ContentValidationError([issue(path, "number", "must be a number")]) from exc
        if not math.isfinite(value):
            raise ContentValidationError([issue(path, "finite", "must be a finite number")])
        return value
    if isinstance(existing, str):
        return text

    def reject_constant(value: str):
        raise ContentValidationError(
            [issue(path, "json_constant", f"invalid JSON constant {value}", value=value)])

    try:
        value = json.loads(text, parse_constant=reject_constant)
    except ContentValidationError:
        raise
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise ContentValidationError([issue(path, "json", "must be valid JSON")]) from exc
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, float) and not math.isfinite(item):
            raise ContentValidationError(
                [issue(path, "json_finite", "JSON numbers must be finite")])
        if isinstance(item, dict):
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    if existing is not None and not isinstance(value, type(existing)):
        raise ContentValidationError([issue(
            path, "json_type", f"must be a JSON {type(existing).__name__}",
            type=type(existing).__name__)])
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
        self.choice_items: list[tuple[Any, str]] = []
        self.choice_index = 0
        self.choice_scroll = 0
        self._choice_rect: pygame.Rect | None = None
        self._choice_row_height = 26

    @property
    def choosing(self) -> bool:
        return self.editing and bool(self.choice_items)

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
        self._land_on_selectable(1)

    def _land_on_selectable(self, step: int) -> None:
        """Nudge self.selected off a non-selectable section-header row."""
        if not self.rows or not self.rows[self.selected].header:
            return
        index = self.selected
        for _ in range(len(self.rows)):
            index += step
            if not 0 <= index < len(self.rows):
                step = -step
                index = self.selected
                continue
            if not self.rows[index].header:
                self.selected = index
                return

    def begin_edit(self) -> bool:
        row = self.selected_row
        if row is None or row.header:
            return False
        self.original = row.value
        self.choice_items = list(row.choices()) if row.choices is not None else []
        if row.choices is not None and not self.choice_items:
            return False
        self.choice_index = next((index for index, (value, _) in enumerate(self.choice_items)
                                  if value == row.value), 0)
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
        self.choice_items = []
        self.error = ""
        return True

    def move_choice(self, amount: int) -> bool:
        if not self.choosing:
            return False
        before = self.choice_index
        self.choice_index = max(0, min(len(self.choice_items) - 1, self.choice_index + amount))
        return before != self.choice_index

    def apply_edit(self, tr: Tr = IDENTITY_TR) -> bool:
        row = self.selected_row
        if not self.editing or row is None:
            return False
        try:
            if self.choice_items:
                value = self.choice_items[self.choice_index][0]
            else:
                value = parse_value(self.input.value, self.original, row.path)
            row.setter(value)
        except ContentValidationError as exc:
            self.error = localized_error(exc, tr)
            return True
        except (TypeError, ValueError, KeyError) as exc:
            self.error = f"{row.path}: {exc}"
            return True
        self.editing = False
        self.choice_items = []
        self.error = ""
        return True

    def move(self, amount: int) -> bool:
        if self.editing or not self.rows:
            return False
        before = self.selected
        step = 1 if amount > 0 else -1
        index = self.selected
        remaining = abs(amount)
        while remaining > 0:
            candidate = index + step
            if not 0 <= candidate < len(self.rows):
                break
            index = candidate
            if not self.rows[index].header:
                remaining -= 1
        self.selected = index
        self._land_on_selectable(step)
        return before != self.selected

    def handle_event(self, event: pygame.event.Event, rect: pygame.Rect,
                     row_height: int = 32, tr: Tr = IDENTITY_TR) -> bool:
        if self.choosing:
            return self._handle_choice_event(event, rect)
        if self.editing:
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    return self.apply_edit(tr)
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
            # Window-to-canvas scaling (Game._window_to_canvas) can hand us
            # float pointer coordinates; row indices must stay integers.
            index = self.scroll + int((position[1] - rect.y) // row_height)
            if 0 <= index < len(self.rows) and not self.rows[index].header:
                changed = index != self.selected
                self.selected = index
                # A click picks a row, a second click on it opens it (Enter):
                # Pygame's button events carry no double-click count.
                if not changed or getattr(event, "clicks", 1) >= 2:
                    self.begin_edit()
                return True
        return False

    def _handle_choice_event(self, event: pygame.event.Event, rect: pygame.Rect) -> bool:
        """The open pick list owns all input until Enter or Esc."""
        page = max(1, (self._choice_rect.height if self._choice_rect else rect.height)
                   // self._choice_row_height - 1)
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                return self.apply_edit()
            if event.key == pygame.K_ESCAPE:
                return self.cancel_edit()
            steps = {pygame.K_UP: -1, pygame.K_k: -1, pygame.K_DOWN: 1, pygame.K_j: 1,
                     pygame.K_PAGEUP: -page, pygame.K_PAGEDOWN: page,
                     pygame.K_HOME: -len(self.choice_items), pygame.K_END: len(self.choice_items)}
            if event.key in steps:
                self.move_choice(steps[event.key])
            return True
        position = event_position(event)
        if event.type == pygame.MOUSEWHEEL:
            self.move_choice(-event.y)
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and getattr(event, "button", 0) == 1 and position:
            box = self._choice_rect
            if box is None or not box.collidepoint(position):
                return self.cancel_edit()
            index = self.choice_scroll + int((position[1] - box.y) // self._choice_row_height)
            if 0 <= index < len(self.choice_items):
                self.choice_index = index
                return self.apply_edit()
            return True
        return event.type == pygame.TEXTINPUT

    def _draw_choices(self, surface: pygame.Surface, rect: pygame.Rect,
                      anchor: pygame.Rect, value_x: int) -> None:
        """Draw the pick list under (or above) the edited row, inside rect."""
        height = self._choice_row_height
        below = rect.bottom - anchor.bottom
        above = anchor.top - rect.top
        room = below if below >= above else above
        visible = max(1, min(len(self.choice_items), (room - 4) // height))
        box_h = visible * height + 4
        top = anchor.bottom if below >= above else anchor.top - box_h
        box = pygame.Rect(value_x, top, max(1, rect.right - value_x - 4), box_h)
        self._choice_rect = box
        self.choice_scroll = max(0, min(self.choice_scroll, len(self.choice_items) - visible))
        if self.choice_index < self.choice_scroll:
            self.choice_scroll = self.choice_index
        elif self.choice_index >= self.choice_scroll + visible:
            self.choice_scroll = self.choice_index - visible + 1
        pygame.draw.rect(surface, PALETTE.panel, box)
        pygame.draw.rect(surface, PALETTE.focus, box, 1)
        for offset, (_, label) in enumerate(
                self.choice_items[self.choice_scroll:self.choice_scroll + visible]):
            index = self.choice_scroll + offset
            item = pygame.Rect(box.x + 2, box.y + 2 + offset * height, box.width - 4, height)
            if index == self.choice_index:
                pygame.draw.rect(surface, PALETTE.raised, item)
            draw_text(surface, raw_text(label), item.inflate(-8, 0), size=13,
                      color=PALETTE.focus if index == self.choice_index else PALETTE.text)

    def draw(self, surface: pygame.Surface, rect: pygame.Rect, *, tr: Tr = IDENTITY_TR,
             label_width: int = 245, row_height: int = 32) -> None:
        pygame.draw.rect(surface, PALETTE.background, rect)
        choice_anchor: tuple[pygame.Rect, int] | None = None
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
                if row.header:
                    header_rect = pygame.Rect(row_rect.x + 4, row_rect.y,
                                              row_rect.width - 8, row_height)
                    pygame.draw.line(surface, PALETTE.border,
                                     (header_rect.x, header_rect.bottom - 4),
                                     (header_rect.right, header_rect.bottom - 4))
                    draw_text(surface, tr(row.label), header_rect,
                             color=PALETTE.focus, size=13, bold=True)
                    continue
                selected = index == self.selected
                if selected:
                    pygame.draw.rect(surface, PALETTE.raised, row_rect)
                    pygame.draw.rect(surface, PALETTE.focus, row_rect, 1)
                label_rect = pygame.Rect(row_rect.x + 7, row_rect.y, min(label_width, row_rect.width // 2), row_height)
                value_rect = pygame.Rect(label_rect.right + 6, row_rect.y + 3,
                                         max(1, row_rect.right - label_rect.right - 12), row_height - 6)
                draw_text(surface, tr(row.label), label_rect, color=PALETTE.text if selected else PALETTE.dim,
                          size=13)
                if selected and self.choosing:
                    pygame.draw.rect(surface, PALETTE.focus, value_rect, 1)
                    draw_text(surface, raw_text(self.choice_items[self.choice_index][1]),
                              value_rect.inflate(-8, 0), size=14)
                    choice_anchor = (row_rect, value_rect.x)
                elif selected and self.editing:
                    self.input.draw(surface, value_rect, focused=True)
                else:
                    draw_text(surface, raw_text(value_text(row.value)), value_rect, size=14)
            if choice_anchor is not None:
                self._draw_choices(surface, rect, *choice_anchor)


def _leaf_rows(current: dict[str, Any], current_prefix: str,
               label_prefix: str) -> list[FieldRow]:
    """Recursively flatten one dict; nested fields get a parent-qualified
    label (e.g. "field.acoustic.category") so they can never collide with a
    same-named top-level field ("field.category")."""
    rows: list[FieldRow] = []
    for key, item in current.items():
        path = f"{current_prefix}.{key}" if current_prefix else key
        label = f"{label_prefix}{key}"
        if isinstance(item, dict):
            rows.extend(_leaf_rows(item, path, f"{label}."))
            continue

        def assign(new_value: Any, target=current, field=key) -> None:
            target[field] = new_value

        rows.append(FieldRow(path, "field." + label, item, assign))
    return rows


def mapping_rows(value: dict[str, Any], prefix: str = "",
                 groups: Iterable[tuple[str, tuple[str, ...]]] | None = None
                 ) -> list[FieldRow]:
    """Flatten dictionaries into editable leaves; arrays remain safe JSON fields.

    With `groups` - an ordered [(header_label, (top_level_key, ...)), ...] -
    top-level keys are arranged under non-selectable section-header rows in
    that order instead of raw dict-iteration order; a group with none of its
    keys present in `value` is omitted.
    """
    if groups is None:
        return _leaf_rows(value, prefix, "")
    rows: list[FieldRow] = []
    for header_label, keys in groups:
        present = [key for key in keys if key in value]
        if not present:
            continue
        rows.append(section_header(header_label))
        for key in present:
            item = value[key]
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(item, dict):
                rows.extend(_leaf_rows(item, path, f"{key}."))
                continue

            def assign(new_value: Any, target=value, field=key) -> None:
                target[field] = new_value

            rows.append(FieldRow(path, "field." + key, item, assign))
    return rows


def draw_footer(surface: pygame.Surface, rect: pygame.Rect, hints: Iterable[str],
                *, tr: Tr = IDENTITY_TR) -> None:
    pygame.draw.rect(surface, PALETTE.raised, rect)
    draw_text(surface, " | ".join(tr(hint) for hint in hints), rect.inflate(-10, 0),
              color=PALETTE.dim, size=13)
