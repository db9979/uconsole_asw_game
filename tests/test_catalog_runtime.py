"""Runtime behavior values are sourced from the packaged contact catalog."""

import json
import random
from importlib import resources
from types import SimpleNamespace

from src.air.helicopter import Helicopter
from src.core import config
from src.enemies.sub import Sub
from src.weapons.torpedo import Torpedo


def _packaged_entry(filename: str, key: str) -> dict:
    path = resources.files("data.contacts") / filename
    with path.open("r", encoding="utf-8") as stream:
        entries = json.load(stream)["entries"]
    return next(entry for entry in entries if entry["key"] == key)


def test_torpedo_runtime_values_match_packaged_json():
    frigate_profile = _packaged_entry("torpedoes.json", "frigate_torp")
    torpedo = Torpedo(0.0, 0.0, 0.0, 50.0, None, 1)
    assert torpedo.speed_kn == frigate_profile["speed_kn"]
    assert torpedo.range_nm == frigate_profile["range_nm"]
    assert torpedo.kill_dist_nm == frigate_profile["hit_dist_nm"]


def test_helicopter_torpedo_runtime_values_match_packaged_json():
    profile = _packaged_entry("torpedoes.json", "helo_torp")
    helicopter = Helicopter(random.Random(1))
    helicopter.state = "AUF"
    target = SimpleNamespace(x=1.0, y=0.0)
    torpedo = helicopter.drop_torpedo(
        target, 50.0, 1, kill_depth_m=15.0)
    assert torpedo.speed_kn == profile["speed_kn"]
    assert torpedo.range_nm == profile["range_nm"]
    assert torpedo.kill_dist_nm == profile["hit_dist_nm"]
    assert config.HELO_TORP_SPEED_KN == profile["speed_kn"]


def test_helicopter_torpedo_applies_supplied_difficulty_hit_envelope():
    helicopter = Helicopter(random.Random(1))
    helicopter.state = "AUF"
    target = SimpleNamespace(x=1.0, y=0.0)
    torpedo = helicopter.drop_torpedo(
        target, 50.0, 1, kill_dist_nm=0.2, kill_depth_m=20.0)
    assert torpedo.kill_dist_nm == 0.2


def test_submarine_decoy_behavior_matches_packaged_json():
    profile = _packaged_entry("decoys.json", "decoy")
    submarine = Sub(10.0, 10.0, 50.0, 0.0, "diesel_alt",
                    random.Random(2))
    submarine.state = "SINKING"
    submarine.sink_left = 10.0
    submarine.torpedo_alerted = True
    submarine.rng.random = lambda: 0.0
    world = SimpleNamespace(
        depth_m=lambda _x, _y: 1000.0,
        thermocline_depth_m=lambda _x, _y: 100.0,
        size_nm=500.0,
    )
    submarine.update(0.1, SimpleNamespace(), world)
    assert submarine.pending_decoys == [(10.0, 10.0)]
    assert submarine._decoy_cd == profile["cooldown_s"]
    assert config.SUB_DECOY_CHANCE == profile["chance"]
    assert config.SUB_DECOY_COOLDOWN_S == profile["cooldown_s"]
