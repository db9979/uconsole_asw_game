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
    # Session-wide guard as well: nothing in a test run (collection, threads
    # outliving a test, helpers) may write the real ~/.u-jagd/settings.json.
    from pathlib import Path
    from src.core import preferences as preferences_module
    real_path = preferences_module.default_preferences_path

    def isolated_path():
        return Path(saves.name) / "settings.json"

    isolated_path.__wrapped__ = real_path
    patch.setattr(preferences_module, "default_preferences_path", isolated_path)


_BROWSER_MARKS = {}


def drives_browser(path) -> bool:
    """True for a test module that launches headless Chromium (directly or
    through the ``commander_web`` helpers)."""
    path = str(path)
    if path not in _BROWSER_MARKS:
        try:
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
        except OSError:
            text = ""
        _BROWSER_MARKS[path] = ("chromium" in text or "commander_web" in text)
    return _BROWSER_MARKS[path]


def pytest_collection_modifyitems(config, items):
    """Mark every test of a module that drives headless Chromium as ``browser``
    so a local iteration can leave them out (``-m "not browser"``)."""
    for item in items:
        if drives_browser(item.fspath):
            item.add_marker(pytest.mark.browser)
            # Under pytest-xdist (``--dist loadgroup``) at most two headless
            # Chromium instances run at once; more of them starve each other
            # of CPU on a four-core host and time out their virtual-time
            # budgets, which makes DOM-probe tests flaky.
            group = sum(map(ord, str(item.fspath))) % 2
            item.add_marker(pytest.mark.xdist_group(f"browser-{group}"))


@pytest.fixture(autouse=True)
def isolated_saves(tmp_path, monkeypatch):
    from src.core import config
    from src.core import preferences as preferences_module

    saves = tmp_path / "saves"
    saves.mkdir()
    monkeypatch.setattr(config, "SAVE_DIR", str(saves))
    monkeypatch.setattr(config, "SAVE_PATH", str(saves / "save.json"))
    monkeypatch.setattr(
        preferences_module, "default_preferences_path",
        lambda: saves / "settings.json")
    return saves
