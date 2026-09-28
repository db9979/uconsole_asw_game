"""ListBox/FieldList mouse-click row selection.

Regression coverage for a real crash: Game._window_to_canvas() scales pointer
coordinates by SCREEN_W/win_w (or the letterbox scale), which yields float
pixel positions whenever the window size isn't an exact multiple of the
1280x720 virtual canvas - as it normally isn't on real (uConsole) hardware.
The row-index math must floor-divide down to a plain int, or the resulting
float selected-index later crashes any list indexing (`self.rows[selected]`).
"""

import pygame
import pytest

from src.ui.editor_widgets import FieldList, FieldRow, FilterField, ListBox


@pytest.fixture(autouse=True, scope="module")
def _pygame_init():
    pygame.init()
    yield
    pygame.quit()


def _click(pos):
    return pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1)


def test_listbox_click_with_float_pointer_selects_integer_row():
    box = ListBox(["a", "b", "c", "d"])
    rect = pygame.Rect(0, 0, 200, 120)
    changed = box.handle_event(_click((50.0, 61.3)), rect, row_height=28)
    assert changed
    assert box.selected == 2
    assert isinstance(box.selected, int)


def test_listbox_click_with_float_pointer_outside_rows_is_ignored():
    box = ListBox(["a"])
    rect = pygame.Rect(0, 0, 200, 28)
    before = box.selected
    changed = box.handle_event(_click((10.0, 500.7)), rect, row_height=28)
    assert not changed
    assert box.selected == before


def test_fieldlist_click_with_float_pointer_selects_integer_row():
    fields = FieldList()
    fields.set_rows([FieldRow(f"field.{i}", str(i), str(i), lambda value: None)
                    for i in range(5)])
    rect = pygame.Rect(0, 0, 200, 200)
    changed = fields.handle_event(_click((20.0, 84.9)), rect, row_height=28)
    assert changed
    assert fields.selected == 3
    assert isinstance(fields.selected, int)
    assert fields.selected_row is not None  # would raise on a float index


def _key(char):
    return pygame.event.Event(pygame.KEYDOWN, key=ord(char), unicode=char, mod=0)


def test_filter_field_types_directly_case_insensitive():
    field = FilterField(maximum=8)
    for char in "AbC":
        assert field.handle_event(_key(char))
    assert field.text == "AbC"
    assert field.matches("XyzABCqrs")
    assert not field.matches("nothing here")
    field.set("")
    assert field.matches("anything")  # empty query matches everything
    field.set("AbC")
    field.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_BACKSPACE,
                                          unicode="", mod=0))
    assert field.text == "Ab"


def test_filter_field_is_bounded_and_ignores_navigation_keys():
    field = FilterField(maximum=4)
    for char in "abcdef":
        field.handle_event(_key(char))
    assert field.text == "abcd"
    for key in (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT,
                pygame.K_TAB, pygame.K_RETURN, pygame.K_ESCAPE):
        consumed = field.handle_event(
            pygame.event.Event(pygame.KEYDOWN, key=key, unicode="", mod=0))
        assert not consumed
    assert field.text == "abcd"


def test_filter_field_textinput_dedup_matches_key_text():
    field = FilterField()
    assert field.handle_event(_key("q"))
    assert field.text == "q"
    # The TEXTINPUT event that follows the same keystroke must be swallowed,
    # not appended a second time.
    consumed = field.handle_event(
        pygame.event.Event(pygame.TEXTINPUT, text="q"))
    assert consumed
    assert field.text == "q"


def _keydown(key):
    return pygame.event.Event(pygame.KEYDOWN, key=key, unicode="", mod=0)


def _choice_fields(taken):
    fields = FieldList()
    fields.set_rows([FieldRow("world.kind", "kind", "fixed", taken.append,
                              choices=lambda: [("fixed", "fixed"), ("reference", "reference")])])
    return fields


def test_choice_row_opens_pick_list_and_applies_the_chosen_value():
    taken = []
    fields = _choice_fields(taken)
    rect = pygame.Rect(0, 0, 400, 300)
    assert fields.handle_event(_keydown(pygame.K_RETURN), rect)
    assert fields.choosing and fields.choice_index == 0
    assert fields.handle_event(_keydown(pygame.K_DOWN), rect)
    assert fields.handle_event(_keydown(pygame.K_DOWN), rect)  # clamps at the end
    assert fields.choice_index == 1
    # Text typed into an open pick list is swallowed, not parsed.
    assert fields.handle_event(pygame.event.Event(pygame.TEXTINPUT, text="x"), rect)
    assert fields.handle_event(_keydown(pygame.K_RETURN), rect)
    assert taken == ["reference"]
    assert not fields.editing and not fields.choosing


def test_choice_row_escape_keeps_the_value():
    taken = []
    fields = _choice_fields(taken)
    rect = pygame.Rect(0, 0, 400, 300)
    fields.handle_event(_keydown(pygame.K_RETURN), rect)
    fields.handle_event(_keydown(pygame.K_END), rect)
    assert fields.handle_event(_keydown(pygame.K_ESCAPE), rect)
    assert taken == [] and not fields.editing


def test_choice_row_click_uses_the_drawn_list_geometry():
    taken = []
    fields = _choice_fields(taken)
    rect = pygame.Rect(0, 0, 400, 300)
    surface = pygame.Surface((400, 300))
    fields.begin_edit()
    fields.draw(surface, rect)
    box = fields._choice_rect
    assert box is not None and rect.contains(box)
    row = fields._choice_row_height
    assert fields.handle_event(_click((box.x + 10.0, box.y + 2 + row * 1.5)), rect)
    assert taken == ["reference"]
    # A click outside an open list closes it without a change.
    fields.begin_edit()
    fields.draw(surface, rect)
    assert fields.handle_event(_click((5.0, 5.0)), rect)
    assert taken == ["reference"] and not fields.editing
