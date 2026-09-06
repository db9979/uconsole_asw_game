"""pytest-Setup: Projektroot auf sys.path + headlose SDL-Treiber."""

import os
import sys
from tempfile import TemporaryDirectory

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


def pytest_configure(config):
    from src.core import config as game_config

    # Protect collection and session fixtures as well as individual tests.
    saves = TemporaryDirectory(prefix="u-jagd-pytest-")
    config.add_cleanup(saves.cleanup)
    patch = pytest.MonkeyPatch()
    config.add_cleanup(patch.undo)
    patch.setattr(game_config, "SAVE_DIR", saves.name)
    patch.setattr(game_config, "SAVE_PATH", os.path.join(saves.name, "save.json"))


@pytest.fixture(autouse=True)
def isolated_saves(tmp_path, monkeypatch):
    from src.core import config

    saves = tmp_path / "saves"
    saves.mkdir()
    monkeypatch.setattr(config, "SAVE_DIR", str(saves))
    monkeypatch.setattr(config, "SAVE_PATH", str(saves / "save.json"))
    return saves
