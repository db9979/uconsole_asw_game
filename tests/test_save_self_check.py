"""A save is checked the way the loader reads it before it is written: a
state the strict validator rejects never replaces the last good slot or the
autosave, and the fault reaches the crash log."""

import pickle

import pygame
import pytest
from pathlib import Path

from src.core import config, crashlog
from src.core.game import Game
from src.core.game_autosave import autosave_path
from src.core.game_save import SaveSelfCheckError
from src.core.i18n import message


@pytest.fixture
def game():
    return Game(seed=4711, start_menu=False, audio_enabled=False)


def _break_next_documents(game, monkeypatch):
    built = game.save_state

    def unloadable():
        document = built()
        document["not_a_save_field"] = 1   # exact schema: the loader rejects it
        return document

    monkeypatch.setattr(game, "save_state", unloadable)


def _record_faults(monkeypatch):
    faults = []
    monkeypatch.setattr(crashlog, "record_fault",
                        lambda exc_type, exc, tb, where="": faults.append((exc_type, where)))
    return faults


def test_rejected_document_keeps_the_previous_slot(game, monkeypatch):
    game.save_to_slot(2)
    path = Path(config.SAVE_DIR) / "slot2.json"
    original = path.read_bytes()
    game._update_sim(5.0)
    faults = _record_faults(monkeypatch)
    _break_next_documents(game, monkeypatch)
    with pytest.raises(SaveSelfCheckError):
        game.save_to_slot(2)
    assert path.read_bytes() == original
    assert faults == [(SaveSelfCheckError, "save")]
    assert sorted(p.name for p in Path(config.SAVE_DIR).iterdir()) == ["slot2.json"]
    fresh = Game(seed=1, start_menu=False, audio_enabled=False)
    assert fresh.load_from_slot(2)


def test_rejected_document_in_the_save_menu_flashes_and_stays_open(game, monkeypatch):
    game.save_to_slot(1)
    path = Path(config.SAVE_DIR) / "slot1.json"
    original = path.read_bytes()
    _record_faults(monkeypatch)
    _break_next_documents(game, monkeypatch)
    flashes = []
    monkeypatch.setattr(game, "flash", lambda text, *args, **kwargs: flashes.append(text))
    game.save_ui, game.save_slot, game.save_confirm = "save", 1, True
    game.quit_after_save = True
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0,
                                         unicode="\r"))
    assert path.read_bytes() == original
    assert game.running and game.save_ui == "save"
    assert flashes[-1] == message("runtime.save.error",
                                  error=message("save.self_check_failed"))


def test_rejected_document_keeps_the_previous_autosave(game, monkeypatch):
    assert game.autosave()
    path = Path(autosave_path())
    original = path.read_bytes()
    snapshot = game._recovery_snapshot
    game._update_sim(5.0)
    faults = _record_faults(monkeypatch)
    _break_next_documents(game, monkeypatch)
    assert not game.autosave()
    assert path.read_bytes() == original
    assert game._autosave_failed and game.autosave_available
    assert game._recovery_snapshot == snapshot
    assert faults == [(SaveSelfCheckError, "save")]


def test_valid_document_is_written_unchanged(game):
    document, text = game.checked_save_document(indent=1)
    path = Path(game.save_game(str(Path(config.SAVE_DIR) / "check.json")))
    assert path.read_text() == text and document["version"] == 50


def test_rejected_recovery_snapshot_keeps_the_previous_autosave(game):
    assert game.autosave()
    path = Path(autosave_path())
    original = path.read_bytes()
    document = game.save_state()
    document["not_a_save_field"] = 1
    game._recovery_snapshot = pickle.dumps(document, protocol=4)
    assert not game.write_recovery_autosave()
    assert path.read_bytes() == original
