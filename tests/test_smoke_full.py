"""Smoke-Test (W0-W4/M10-M16) im pytest-Format."""

from pathlib import Path

import pytest

from src.core import config
from src.core.game import Game
from tools import smoke_full
from tools.smoke_full import main


def test_smoke_full():
    previous_paths = config.SAVE_DIR, config.SAVE_PATH
    main()
    assert (config.SAVE_DIR, config.SAVE_PATH) == previous_paths


@pytest.mark.parametrize("fail", [False, True])
def test_smoke_isolates_saves_and_restores_paths(tmp_path, monkeypatch, fail):
    existing = tmp_path / "existing-saves"
    existing.mkdir()
    legacy = tmp_path / "legacy.json"
    sentinels = {existing / "slot2.json": b"existing slot 2",
                 existing / "slot5.json": b"existing slot 5",
                 legacy: b"existing legacy save"}
    for path, contents in sentinels.items():
        path.write_bytes(contents)
    monkeypatch.setattr(config, "SAVE_DIR", str(existing))
    monkeypatch.setattr(config, "SAVE_PATH", str(legacy))
    temporary_paths = []

    def save_probe():
        saves = Path(config.SAVE_DIR)
        temporary_paths.append(saves)
        assert saves != existing
        assert Path(config.SAVE_PATH) == saves / "save.json"
        assert list(saves.iterdir()) == []
        game = Game(seed=1234, start_menu=False)
        assert not game.load_from_slot(5)
        assert not game.load_game()
        game.save_to_slot(2)
        game.save_game()
        assert (saves / "slot2.json").is_file()
        assert (saves / "save.json").is_file()
        if fail:
            raise RuntimeError("smoke failure")

    monkeypatch.setattr(smoke_full, "_run_smoke", save_probe)
    # Each call must get a fresh directory, including after a failed run.
    for _ in range(2):
        if fail:
            with pytest.raises(RuntimeError, match="smoke failure"):
                main()
        else:
            main()
        assert (config.SAVE_DIR, config.SAVE_PATH) == (str(existing), str(legacy))
        assert not temporary_paths[-1].exists()
        assert {path: path.read_bytes() for path in sentinels} == sentinels
        assert set(existing.iterdir()) == {existing / "slot2.json",
                                          existing / "slot5.json"}
