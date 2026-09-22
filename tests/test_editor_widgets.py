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
