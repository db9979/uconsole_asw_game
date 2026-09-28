import pygame
import pytest

from src.core.i18n import RawText, Translator, translation_scope
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


def test_catalog_literal_mission_name_is_explicit_raw_text(tmp_path, monkeypatch):
    pygame.init()
    mission = default_mission("user.saved")
    mission["name"] = "Saved"
    editor = MissionEditor({"user.saved": mission}, store=UserContentStore(tmp_path),
                           tr=Translator("de").translate)
    captured = []
    original = __import__("src.ui.editor_widgets", fromlist=["draw_text"]).draw_text

    def record(surface, value, rect, **kwargs):
        captured.append(value)
        return original(surface, value, rect, **kwargs)

    monkeypatch.setattr("src.ui.editor_widgets.draw_text", record)
    editor.draw(pygame.Surface((1280, 720)))
    assert any(isinstance(value, RawText) and value.value == "Saved" for value in captured)
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


def _world_row(editor, path):
    editor.tab_index = editor.tabs.index("world")
    editor._sync_fields()
    index = next(i for i, row in enumerate(editor.fields.rows) if row.path == path)
    editor.fields.selected = index
    return editor.fields.rows[index]


def test_world_reference_is_picked_from_the_packaged_sectors(tmp_path):
    pygame.init()
    editor = MissionEditor(store=UserContentStore(tmp_path), profile_keys={"sub"},
                           tr=Translator("en").translate)
    editor.new("user.sector_pick")
    row = _world_row(editor, "world.reference")
    choices = row.choices()
    assert len(choices) == 128
    assert choices[17][0] == "sector:17" and "Greece" in choices[17][1]
    key = lambda k: pygame.event.Event(pygame.KEYDOWN, key=k, unicode="", mod=0)
    assert editor.handle_event(key(pygame.K_RETURN))
    assert editor.fields.choosing and editor.status
    for _ in range(17):
        editor.handle_event(key(pygame.K_DOWN))
    editor.draw(pygame.Surface((1280, 720)))
    assert editor.handle_event(key(pygame.K_RETURN))
    world = editor.current.data["world"]
    assert world["reference"] == "sector:17" and not editor.status
    assert world["kind"] == "reference" and world["size_nm"] == 500.0
    assert not [p for p in editor.validate() if p.path.startswith("world")]
    pygame.quit()


def test_world_kind_is_a_closed_choice_and_preview_draws_the_sector_coast(tmp_path):
    pygame.init()
    editor = MissionEditor(store=UserContentStore(tmp_path), profile_keys={"sub"},
                           tr=Translator("de").translate)
    editor.new("user.sector_preview")
    assert [value for value, _ in _world_row(editor, "world.kind").choices()] == ["fixed", "reference"]
    surface = pygame.Surface((1280, 720))
    editor.tab_index = editor.tabs.index("preview")
    editor.draw(surface)
    fixed = pygame.image.tobytes(surface, "RGB")
    editor.current.data["world"].update(kind="reference", reference="sector:17")
    editor.draw(surface)
    assert pygame.image.tobytes(surface, "RGB") != fixed
    pygame.quit()
