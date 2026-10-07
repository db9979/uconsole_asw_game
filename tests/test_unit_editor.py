import pygame
import pytest

from src.core.i18n import Translator, translation_scope
from src.data.catalog import CATALOG
from src.data.user_content import UserContentStore
from src.ui import editor_widgets as widgets
from src.ui import unit_editor
from src.ui.unit_editor import (PROFILE_KINDS, UnitDefinition, UnitEditor,
                               _UNIT_FIELD_GROUPS, _UNIT_KIND_FIELDS,
                               default_unit)


def _key(char, mod=0):
    return pygame.event.Event(pygame.KEYDOWN, key=ord(char), unicode=char, mod=mod)


def test_browser_list_shows_the_units_name_not_only_its_key(tmp_path):
    editor = UnitEditor({"diesel_alt": ("sub", CATALOG.subs["diesel_alt"])},
                        UserContentStore(tmp_path))
    label = editor.listbox.items[0]
    assert CATALOG.subs["diesel_alt"].name in label
    assert "diesel_alt" in label


def test_typing_filters_the_browser_list_case_insensitively(tmp_path):
    editor = UnitEditor({"diesel_alt": ("sub", CATALOG.subs["diesel_alt"]),
                         "sub_01": ("sub", CATALOG.subs["sub_01"])},
                        UserContentStore(tmp_path))
    assert len(editor.filtered) == 2

    query = CATALOG.subs["diesel_alt"].name[:4].upper()
    for char in query:
        assert editor.handle_event(_key(char))
    assert len(editor.filtered) == 1
    assert editor.selected.key == "diesel_alt"

    for _ in range(len(query)):
        editor.handle_event(pygame.event.Event(
            pygame.KEYDOWN, key=pygame.K_BACKSPACE, unicode="", mod=0))
    assert len(editor.filtered) == 2

    editor._set_filter("no such unit at all")
    assert editor.filtered == []
    assert editor.selected is None


def test_bare_n_types_into_filter_ctrl_n_opens_kind_chooser(tmp_path):
    editor = UnitEditor(store=UserContentStore(tmp_path))
    assert editor.handle_event(_key("n"))
    assert editor.mode == "browser"
    assert editor.filter.text == "n"

    editor._set_filter("")
    assert editor.handle_event(_key("n", pygame.KMOD_CTRL))
    assert editor.mode == "kind"


def test_selection_stays_correct_across_filtering_and_survives_delete(tmp_path):
    store = UserContentStore(tmp_path)
    editor = UnitEditor({"diesel_alt": ("sub", CATALOG.subs["diesel_alt"])}, store)
    editor.new("sub", "user.alpha")
    editor.set_value("name", "Alpha Boat")
    editor.save()
    editor.new("sub", "user.beta")
    editor.set_value("name", "Beta Boat")
    editor.save()
    assert len(editor.records) == 3

    editor._set_filter("Boat")
    assert len(editor.filtered) == 2
    assert {editor.records[i].key for i in editor.filtered} == \
        {"user.alpha", "user.beta"}

    editor.listbox.selected = 0
    target_key = editor.selected.key
    editor.mode = "browser"
    editor.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_DELETE, mod=pygame.KMOD_SHIFT, unicode=""))
    assert target_key not in {r.key for r in editor.records}
    # Filter is preserved after the list-mutating refresh() delete triggers.
    assert editor.filter.text == "Boat"
    assert len(editor.filtered) == 1


@pytest.mark.parametrize("kind", PROFILE_KINDS)
def test_field_groups_cover_exactly_the_kinds_full_field_set(kind):
    """A field silently missing from every group would just vanish from the
    editor instead of raising - this is the guard against that."""
    full = {"version", "key", "profile_kind", "name"} | set(_UNIT_KIND_FIELDS[kind])
    grouped = set()
    for _, keys in _UNIT_FIELD_GROUPS[kind]:
        assert not (grouped & set(keys)), "field claimed by two groups"
        grouped |= set(keys)
    assert grouped == full


def test_surface_top_level_and_nested_category_no_longer_collide(tmp_path):
    """Regression: surface's top-level "category" (KAMPFSCHIFF/...) and
    acoustic.category (acoustic classification) used to render as the same
    "field.category" row label."""
    editor = UnitEditor(store=UserContentStore(tmp_path))
    editor.new("surface", "user.warship")
    labels = [row.label for row in editor.fields.rows if not row.header]
    assert labels.count("field.category") == 1
    assert "field.acoustic.category" in labels


def test_field_list_groups_have_non_selectable_headers_that_are_skipped(tmp_path):
    editor = UnitEditor(store=UserContentStore(tmp_path))
    editor.new("sub", "user.probe")
    assert editor.fields.rows[0].header
    assert not editor.fields.selected_row.header  # set_rows() skipped the header

    seen_headers = 0
    for _ in range(len(editor.fields.rows)):
        if editor.fields.selected_row.header:
            seen_headers += 1
        editor.fields.move(1)
    assert seen_headers == 0

    # Forcing selection onto a header must never let editing start on it.
    editor.fields.selected = 0
    assert editor.fields.rows[0].header
    assert editor.fields.begin_edit() is False
    assert not editor.fields.editing


def test_wiki_import_hotkey_is_discoverable_in_browser_and_editor_footers(
        tmp_path, monkeypatch):
    """W2: Ctrl+G (wiki import) had no footer hint anywhere - a user could
    only find it by reading the source. Both the initial unit list and the
    field editor must now advertise it."""
    seen = []
    monkeypatch.setattr(widgets, "draw_footer",
                        lambda surface, rect, hints, tr=None: seen.append(tuple(hints)))
    pygame.init()
    editor = UnitEditor(store=UserContentStore(tmp_path))
    surface = pygame.Surface((1280, 720))
    editor.mode = "browser"
    editor.draw(surface)
    assert ("Ctrl+G", "editor.bar.wiki_import") in seen[-1]
    editor.new("sub", "user.wiki_hint_probe")
    editor.mode = "editor"
    editor.draw(surface)
    assert ("Ctrl+G", "editor.bar.wiki_import") in seen[-1]
    pygame.quit()


def test_clone_builtin_is_user_owned_valid_and_saved(tmp_path):
    cloned = UnitDefinition.clone_builtin(CATALOG.subs["diesel_alt"], "sub", "user.diesel_clone")
    assert not cloned.validate()
    editor = UnitEditor(store=UserContentStore(tmp_path))
    editor.current = cloned
    editor.mode = "editor"
    assert editor.save().name == "user.diesel_clone.json"


def test_builtin_browser_clones_instead_of_editing(tmp_path):
    editor = UnitEditor({"diesel_alt": ("sub", CATALOG.subs["diesel_alt"])},
                        UserContentStore(tmp_path))
    assert editor.selected.read_only
    opened = editor.open_selected()
    assert opened.data["key"].startswith("user.")
    assert editor.builtins["diesel_alt"][1].key == "diesel_alt"


def test_unit_editor_draw_and_trackball_hat(tmp_path):
    pygame.init()
    editor = UnitEditor(store=UserContentStore(tmp_path))
    editor.new("decoy", "user.decoy")
    surface = pygame.Surface((1280, 720))
    editor.draw(surface)
    assert editor.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0))
    pygame.quit()


@pytest.mark.parametrize("kind", PROFILE_KINDS)
def test_unit_editor_draws_every_kinds_grouped_fields_without_crashing(tmp_path, kind):
    pygame.init()
    editor = UnitEditor(store=UserContentStore(tmp_path))
    editor.new(kind, f"user.{kind}_probe")
    surface = pygame.Surface((1280, 720))
    editor.draw(surface)
    for _ in range(len(editor.fields.rows) + 2):
        editor.fields.move(1)
        editor.draw(surface)
    pygame.quit()


def test_imported_unit_text_is_rendered_without_translation(tmp_path):
    pygame.init()
    store = UserContentStore(tmp_path)
    unit = default_unit("decoy", "user.braces")
    unit["name"] = "menu.seed {unmatched"
    unit["signature_text"] = "raw {arbitrary} value"
    store.import_bundle({"format": "u-jagd.editor-bundle", "version": 1,
                         "missions": [], "units": [unit]})

    def controlled_only(value):
        assert value not in (unit["key"], unit["name"], unit["signature_text"])
        return value

    editor = UnitEditor(store=store, tr=controlled_only)
    surface = pygame.Surface((1280, 720))
    with translation_scope(Translator("en").translate):
        editor.draw(surface)
        editor.open_selected()
        editor.draw(surface)
    pygame.quit()


@pytest.mark.parametrize("language", ["en", "de"])
def test_unit_authoring_kind_edit_save_and_delete_events(tmp_path, language):
    pygame.init()
    store = UserContentStore(tmp_path / language)
    editor = UnitEditor(store=store, tr=Translator(language).translate)
    surface = pygame.Surface((1280, 720))
    editor.draw(surface)

    assert editor.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_n, mod=pygame.KMOD_CTRL, unicode=""))
    assert editor.mode == "kind"
    assert tuple(editor.kind_box.items) == ("sub", "surface", "aircraft", "animal", "torpedo", "decoy")
    editor.draw(surface)
    kind_rect = editor._rects["kinds"]
    assert editor.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1,
        pos=(kind_rect.centerx, kind_rect.y + 5 * 38 + 10)))
    assert editor.kind_box.selected == 5
    assert editor.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_RETURN, mod=0, unicode=""))
    assert editor.current.data["profile_kind"] == "decoy"
    editor.draw(surface)

    editor.fields.selected = next(index for index, row in enumerate(editor.fields.rows)
                                  if row.path == "key")
    assert editor.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_RETURN, mod=0, unicode=""))
    editor.fields.input.value = "user.interactive_decoy"
    assert editor.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_RETURN, mod=0, unicode=""))
    assert editor.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_s, mod=pygame.KMOD_CTRL, unicode="s"))
    assert store.path_for("unit", "user.interactive_decoy").exists()

    assert editor.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode=""))
    assert editor.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_DELETE, mod=0, unicode=""))
    assert store.path_for("unit", "user.interactive_decoy").exists()
    assert editor.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_RETURN, mod=0, unicode=""))
    assert not store.path_for("unit", "user.interactive_decoy").exists()
    pygame.quit()


def test_open_wiki_button_opens_the_profile_wiki_url(tmp_path, monkeypatch):
    pygame.init()
    opened = []
    monkeypatch.setattr(unit_editor.webbrowser, "open", opened.append)
    editor = UnitEditor(store=UserContentStore(tmp_path))
    editor.new("sub", "user.test_sub")
    editor.current.data["wiki_url"] = "https://en.wikipedia.org/wiki/Test"
    surface = pygame.Surface((1280, 720))
    editor.draw(surface)
    rect = editor._rects.get("open_wiki")
    assert rect is not None
    assert surface.get_rect().contains(rect)
    assert editor.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center)) is True
    assert opened == ["https://en.wikipedia.org/wiki/Test"]
    # Ctrl+W still works alongside the clickable button.
    assert editor.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_w, mod=pygame.KMOD_CTRL, unicode="w"))
    assert opened == ["https://en.wikipedia.org/wiki/Test"] * 2
    pygame.quit()


def test_open_wiki_button_hidden_and_inert_without_wiki_url(tmp_path, monkeypatch):
    pygame.init()
    opened = []
    monkeypatch.setattr(unit_editor.webbrowser, "open", opened.append)
    editor = UnitEditor(store=UserContentStore(tmp_path))
    editor.new("sub", "user.test_sub")
    surface = pygame.Surface((1280, 720))
    editor.draw(surface)
    assert editor._rects.get("open_wiki") is None
    assert editor.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=(0, 0))) is False
    assert opened == []
    pygame.quit()
