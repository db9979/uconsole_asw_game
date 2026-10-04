"""Malformed saves are refused, never raised out of a load (code review 1.3.205).

A hand-edited or damaged slot or autosave used to reach a migration step or
the validator with a value of the wrong type; the TypeError then escaped the
main menu's load and ended the process. A failed load also left the live
game's raid stream changed, so the game no longer continued as before.
"""

import copy
import json

import pytest

from src.core import game_save
from src.core.game import Game


def _game(seed=7):
    game = Game(seed=seed, start_menu=False, show_splash=False, audio_enabled=False,
                language="en")
    assert game.start_new_game("s1_patrouille", "fixed", seed=seed)
    for _ in range(50):
        game.update(0.1)
    return game


@pytest.fixture(scope="module")
def document():
    return json.loads(json.dumps(_game().save_state(), allow_nan=False))


def _ship_x(doc):
    doc["ship"]["x"] = {}


def _vds_state(doc):
    doc["sonar"]["vds_state"] = {"a": 1}


def _civilian_id(doc):
    doc["civilians"][0]["id"] = [1]


def _old_torpedoes(doc):
    # An older format whose migration step walks a list that is a number.
    doc["version"] = 47
    doc["enemy_torpedoes"] = 1


def _deep(doc):
    node = doc["ui"]
    for _ in range(5000):
        node["x"] = {}
        node = node["x"]


@pytest.mark.parametrize("mutate", [_ship_x, _vds_state, _civilian_id,
                                    _old_torpedoes, _deep])
def test_a_malformed_save_is_refused_from_the_main_menu(document, mutate):
    doc = copy.deepcopy(document)
    if mutate is _civilian_id and not doc.get("civilians"):
        pytest.skip("no civilians in this sample")
    mutate(doc)
    menu = Game(seed=3, start_menu=True, show_splash=False, audio_enabled=False,
                language="en")
    assert menu._load_save_data(doc) is False


def test_a_failed_load_leaves_the_live_raid_stream_alone(document, monkeypatch):
    live = _game(seed=5)
    before = live.rng_raid.getstate()
    # A document the validator accepts but whose restore does not reproduce
    # itself fails at the very end, after every stream was restored.
    monkeypatch.setattr(game_save, "_same_save_value", lambda a, b: False)
    assert live._load_save_data(copy.deepcopy(document)) is False
    assert live.rng_raid.getstate() == before
