import pygame
import pytest

from src.core.i18n import Translator, translation_scope
from src.data.catalog import CATALOG
from src.data.user_content import UserContentStore
from src.ui.unit_editor import UnitDefinition, UnitEditor, default_unit


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
        pygame.KEYDOWN, key=pygame.K_n, mod=0, unicode="n"))
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
