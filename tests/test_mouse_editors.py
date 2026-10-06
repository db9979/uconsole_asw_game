"""Package 5 of the mouse plan: the Mission and Unit Editors by click."""

import pygame
import pytest

from src.core import config
from src.core.game import Game
from src.data.catalog import CATALOG
from src.data.user_content import UserContentStore
from src.ui import layout, pointer
from src.ui.mission_editor import MissionEditor
from src.ui.unit_editor import UnitEditor, catalog_builtins


@pytest.fixture
def game(monkeypatch):
    monkeypatch.setattr(pygame.display, "get_window_size", lambda: (1280, 720))
    instance = Game(seed=31, start_menu=True, audio_enabled=False, language="de")
    instance.splash_active = False
    yield instance
    instance.commander.stop()
    instance.audio.shutdown()
    layout.configure_for(large_text=False)


def chip(game, key, mod=0):
    game.draw()
    return next(t.rect for t in pointer.targets("editor")
                if t.key == key and t.mod == mod)


def click(game, rect):
    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        game.handle_event(pygame.event.Event(kind, button=1, pos=rect.center))


def mission_editor(game, tmp_path):
    game.editor = MissionEditor(store=UserContentStore(tmp_path), tr=game.tr,
                                profile_keys=set(catalog_builtins(CATALOG)))
    return game.editor


def test_mission_editor_chips_and_close_cross(game, tmp_path):
    editor = mission_editor(game, tmp_path)
    click(game, chip(game, pygame.K_n))                 # N: new mission
    assert editor.mode == "editor" and editor.current is not None
    click(game, chip(game, pygame.K_RIGHT))             # ←/→ right half: next section
    assert editor.tab_index == 1
    click(game, editor.close_rect)                       # the cross: back to the list
    assert editor.mode == "browser" and game.editor is editor
    click(game, chip(game, pygame.K_ESCAPE))             # Esc chip: out of the editor
    assert game.editor is None


def test_every_drawn_editor_chip_has_a_key(game, tmp_path):
    editor = mission_editor(game, tmp_path)
    for setup in (lambda: None, editor.new, lambda: editor._begin_path("export")):
        setup()
        game.draw()
        targets = pointer.targets("editor")
        assert targets and all(t.key is not None for t in targets)


def test_path_dialog_ok_and_cancel_buttons(game, tmp_path):
    editor = mission_editor(game, tmp_path)
    editor._begin_path("export")
    game.draw()
    escapes = [t.rect for t in pointer.targets("editor") if t.key == pygame.K_ESCAPE]
    assert len(escapes) == 2                             # dialog button and key bar
    click(game, escapes[0])
    assert editor.path_action is None and game.editor is editor


def test_unit_editor_new_kind_and_delete_question_by_click(game, tmp_path):
    store = UserContentStore(tmp_path)
    game.editor = editor = UnitEditor(catalog_builtins(CATALOG), store=store, tr=game.tr)
    click(game, chip(game, pygame.K_n, pygame.KMOD_CTRL))
    assert editor.mode == "kind"
    click(game, chip(game, pygame.K_RETURN))             # create the chosen kind
    assert editor.mode == "editor"
    click(game, chip(game, pygame.K_s, pygame.KMOD_CTRL))
    click(game, chip(game, pygame.K_ESCAPE))
    assert editor.mode == "browser"
    editor.refresh()
    editor.listbox.selected = next(position for position, index in enumerate(editor.filtered)
                                   if not editor.records[index].builtin)
    click(game, chip(game, pygame.K_DELETE))
    assert editor._delete_pending
    click(game, chip(game, pygame.K_ESCAPE))             # "no": nothing deleted
    assert not editor._delete_pending and store.list("unit")
    click(game, chip(game, pygame.K_DELETE))
    click(game, chip(game, pygame.K_RETURN))             # "yes, delete"
    assert not store.list("unit")
