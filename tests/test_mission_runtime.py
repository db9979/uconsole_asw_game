"""Mission runtime = editor scope (plan 1.3, phase 13): reference worlds,
protect/reach objectives, random groups and events, placed aircraft,
animals and decoys.  User unit profiles and other world sizes stay rejected."""

import copy
import json

import pytest

from src.core import config
from src.core.game import Game
from src.core.mission_definition import (default_mission, reference_sector_index,
                                         validate_mission)


def _game(seed=901):
    return Game(seed=seed, start_menu=False, audio_enabled=False, language="en")


def _sub(unit_id="target", x=300.0, y=250.0, side="hostile", profile="sub_03"):
    return {"id": unit_id, "profile": profile, "side": side,
            "placement": {"kind": "fixed", "x": x, "y": y},
            "course_deg": 90.0, "speed_kn": 4.0, "depth_m": 60.0}


def _definition(key="user.runtime", objective="sink", **world):
    definition = default_mission(key)
    definition["seed"] = 4242
    definition["units"]["exact"] = [_sub()]
    definition["objective"] = {"type": objective, "target_ids": ["target"] if objective == "sink" else [],
                               "time_limit_s": 1800.0}
    definition["world"].update(world)
    return definition


def _run(game, seconds, dt=0.25):
    for _ in range(int(seconds / dt)):
        game._update_sim(dt)


def _poses(game):
    return [(round(game.ship.x, 6), round(game.ship.y, 6), round(game.ship.course, 6))] + [
        (round(sub.x, 6), round(sub.y, 6), round(sub.depth, 6)) for sub in game.subs]


# --- step 1: reference worlds ------------------------------------------------

def test_reference_sector_names_are_strict():
    assert reference_sector_index("sector:0") == 0
    assert reference_sector_index("sector:127") == 127
    for bad in ("sector:128", "sector:-1", "sector:01", "sector:", "north_sea", "sector:12a", 7):
        assert reference_sector_index(bad) is None
    definition = _definition(kind="reference", reference="north_sea")
    assert "reference" in {problem.code for problem in validate_mission(definition)}
    assert not validate_mission(_definition(kind="reference", reference="sector:5"))


def test_reference_world_starts_on_its_packaged_sector_and_survives_a_save(tmp_path):
    game = _game()
    definition = _definition(kind="reference", reference="sector:17")
    assert game.start_custom_mission(definition)
    assert game.world_mode == "real_fixed"
    assert game.world.coast.metadata["sector_id"] == "real-017"
    assert game.world.size_nm == config.WORLD_SIZE_NM
    _run(game, 5.0)
    state = json.loads(json.dumps(game.save_state(), allow_nan=False))
    assert state["world"]["mode"] == "real_fixed"
    other = _game(seed=1)
    assert other._load_save_data(copy.deepcopy(state))
    assert other.world.coast.metadata["sector_id"] == "real-017"
    assert other.custom_mission_definition["world"]["reference"] == "sector:17"
    assert _poses(other) == _poses(game)


def test_reference_world_rejections_stay():
    game = _game()
    for world in ({"kind": "reference", "reference": "sector:999"},
                  {"kind": "reference", "reference": "sector:3", "size_nm": 300.0},
                  {"kind": "fixed", "size_nm": 250.0}):
        assert not game.start_custom_mission(_definition(**world))
    profile = _definition()
    profile["units"]["exact"][0]["profile"] = "user.my_boat"
    assert not game.start_custom_mission(profile)


def test_two_reference_world_runs_are_identical():
    runs = []
    for _ in range(2):
        game = _game()
        assert game.start_custom_mission(_definition(kind="reference", reference="sector:40"))
        _run(game, 30.0)
        runs.append((_poses(game), game.world.coast.metadata["sector_id"],
                     round(game.world.weather_values()["wind_speed_kn"], 6)))
    assert runs[0] == runs[1]
