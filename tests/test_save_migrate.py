"""Save migration: frozen saves of older releases load and play on.

Every sample in ``tests/data/saves`` was written by the release that last
used its format (``tools/make_save_sample.py``); each must lift to the current
format, pass the strict validation, restore, and keep running.
"""

import copy
import json
import os
import sys
from pathlib import Path

import pytest

from src.core import save_migrate
from src.core.game import Game
from src.core.game_save import _same_save_value
from src.core.version import SAVE_SCHEMA, SAVE_VERSION

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "tests" / "data" / "saves"
sys.path.insert(0, str(ROOT / "tools"))
from make_save_sample import unpack  # noqa: E402

SAMPLE_PATHS = sorted(SAMPLES.glob("v*-*.json.xz"))


def _menu_game():
    return Game(seed=3, start_menu=True, show_splash=False, audio_enabled=False)


def test_every_older_format_has_a_step_and_a_sample():
    versions = {int(path.name[1:].split("-")[0]) for path in SAMPLE_PATHS}
    for version in range(save_migrate.MIGRATE_FROM, SAVE_VERSION):
        assert version in save_migrate.STEPS, version
        assert version in versions, f"no frozen v{version} sample"
    assert max(save_migrate.STEPS) == SAVE_VERSION - 1


@pytest.mark.parametrize("path", SAMPLE_PATHS, ids=lambda path: path.name)
def test_older_sample_loads_and_plays_on(path):
    original = unpack(path)
    untouched = copy.deepcopy(original)
    lifted = save_migrate.migrate(original)
    assert original == untouched                    # never edited in place
    assert lifted["version"] == SAVE_VERSION and lifted["save_schema"] == SAVE_SCHEMA
    game = _menu_game()
    assert game._load_save_data(original)
    assert not game.main_menu and game.seed == original["seed"]
    # Everything the old release saved is still there.
    restored = game.save_state()
    for key, value in untouched.items():
        if key in ("version", "save_schema", "next_entity_ids", "autocrew"):
            continue
        assert key in restored, key
    assert restored["sim_t"] == pytest.approx(untouched["sim_t"])
    for _ in range(30):
        game.update(0.1)
    assert game.sim_t > untouched["sim_t"]


def test_lifted_save_continues_like_a_reloaded_one():
    """A lifted save is an ordinary current save: saving it again and loading
    that copy continues identically."""
    game = _menu_game()
    assert game._load_save_data(unpack(SAMPLE_PATHS[0]))
    again = _menu_game()
    assert again._load_save_data(json.loads(json.dumps(game.save_state())))
    for _ in range(20):
        game.update(0.1)
        again.update(0.1)
    left, right = game.save_state(), again.save_state()
    left.pop("next_entity_ids"), right.pop("next_entity_ids")
    assert _same_save_value(left, right)


def test_unsupported_documents_are_left_to_the_validator():
    assert save_migrate.migrate({"version": 12}) == {"version": 12}
    tagless = {"version": 40, "save_schema": "u-jagd-save-v41"}
    assert save_migrate.migrate(tagless) is tagless
    old = {"version": save_migrate.MIGRATE_FROM - 1,
           "save_schema": f"u-jagd-save-v{save_migrate.MIGRATE_FROM - 1}"}
    assert save_migrate.migrate(old) is old
    newer = {"version": SAVE_VERSION + 1, "save_schema": f"u-jagd-save-v{SAVE_VERSION + 1}"}
    assert save_migrate.migrate(newer) is newer
    assert not _menu_game()._load_save_data(old)
    assert not _menu_game()._load_save_data(newer)


def test_broken_old_save_is_still_rejected():
    document = unpack(SAMPLE_PATHS[0])
    document["sim_t"] = "soon"
    game = _menu_game()
    assert not game._load_save_data(document)
    assert game.main_menu


def test_continue_lifts_an_old_autosave():
    from src.core.game_autosave import autosave_path
    os.makedirs(os.path.dirname(autosave_path()), exist_ok=True)
    with open(autosave_path(), "w", encoding="utf-8") as stream:
        json.dump(unpack(SAMPLE_PATHS[0]), stream)
    game = Game(seed=5, start_menu=True, show_splash=False, audio_enabled=False)
    assert game.continue_from_autosave()
    assert not game.main_menu
