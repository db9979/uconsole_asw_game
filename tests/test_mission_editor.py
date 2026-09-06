import pygame
import pytest

from src.core.i18n import Translator, translation_scope
from src.core.mission_definition import default_mission
from src.data.user_content import UserContentStore
from src.ui.mission_editor import MissionEditor


def test_mission_editor_clone_save_preview_and_bundle(tmp_path):
    store = UserContentStore(tmp_path)
    editor = MissionEditor({"builtin.demo": default_mission("user.source")}, store=store,
                           profile_keys={"sub"})
    mission = editor.clone_selected("user.demo")
    editor.add_sector("east", 100, 100, 50, 50)
    editor.add_exact_unit("target", "sub", "hostile", sector="east")
    mission.data["objective"]["target_ids"] = ["target"]
    assert not editor.validate()
    assert editor.save().exists()
    assert editor.preview()["markers"][1]["source"] == "exact"
    bundle = editor.export_bundle(tmp_path / "bundle.json")
    other = MissionEditor(store=UserContentStore(tmp_path / "other"))
    assert other.import_bundle(bundle)[0].key == "user.demo"


def test_mission_editor_draw_and_keyboard_are_standalone(tmp_path):
    pygame.init()
    translated = []
    editor = MissionEditor(store=UserContentStore(tmp_path), tr=lambda value: translated.append(value) or value)
    editor.new()
    surface = pygame.Surface((1280, 720))
    editor.draw(surface)
    before = editor.tab_index
    editor.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT, mod=0))
    assert editor.tab_index == before + 1
    assert translated
    pygame.quit()


def test_imported_mission_text_is_rendered_without_translation(tmp_path):
    pygame.init()
    store = UserContentStore(tmp_path)
    mission = default_mission("user.braces")
    mission["name"] = "menu.seed"
    mission["description"] = "unmatched { and {arbitrary}"
    store.import_bundle({"format": "u-jagd.editor-bundle", "version": 1,
                         "missions": [mission], "units": []})
    translated = []

    def controlled_only(value):
        translated.append(value)
        assert value not in (mission["key"], mission["name"], mission["description"])
        return value

    editor = MissionEditor(store=store, tr=controlled_only)
    with translation_scope(Translator("en").translate):
        editor.draw(pygame.Surface((1280, 720)))
    pygame.quit()


@pytest.mark.parametrize("language", ["en", "de"])
def test_mission_authoring_events_add_edit_delete_and_save(tmp_path, language):
    pygame.init()
    editor = MissionEditor(store=UserContentStore(tmp_path / language),
                           tr=Translator(language).translate)
    surface = pygame.Surface((1280, 720))
    editor.new("user.interactive")
    editor.draw(surface)

    objective_tab = editor._rects["tabs"][editor.tabs.index("objective")]
    assert editor.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=objective_tab.center))
    assert editor.tab == "objective"
    overview_tab = editor._rects["tabs"][editor.tabs.index("overview")]
    assert editor.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=overview_tab.center))

    # Enter edits the selected key row transactionally.
    assert editor.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_RETURN, mod=0, unicode=""))
    editor.fields.input.value = "user.edited"
    assert editor.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_RETURN, mod=0, unicode=""))
    assert editor.current.data["key"] == "user.edited"

    editor.tab_index = editor.tabs.index("units")
    editor._sync_fields()
    assert editor.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_e, mod=0, unicode="e"))
    assert len(editor.current.data["units"]["exact"]) == 1
    assert editor.fields.rows[0].path == "units.exact[0].id"

    editor.tab_index = editor.tabs.index("events")
    editor._sync_fields()
    assert editor.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_a, mod=0, unicode="a"))
    assert len(editor.current.data["events"]) == 1
    assert editor.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_DELETE, mod=0, unicode=""))
    assert len(editor.current.data["events"]) == 1
    assert editor.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_RETURN, mod=0, unicode=""))
    assert not editor.current.data["events"]

    assert editor.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_s, mod=pygame.KMOD_CTRL, unicode="s"))
    assert (tmp_path / language / "missions" / "user.edited.json").exists()
    editor.draw(surface)
    pygame.quit()
