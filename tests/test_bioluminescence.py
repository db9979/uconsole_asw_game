"""Bioluminescence: stirred water glows at night in warm seas (both sides)."""

from src.physics import bioluminescence
from src.sensors.visual import LookoutModel
from src.world.world import World


def _model():
    return LookoutModel({"SURFACE": 12.0, "SUB": 3.0, "FLG": 15.0, "TORP": 1.5,
                         "LAND": 20.0}, 20.0)


def test_bloom_follows_warm_water_and_the_seed():
    assert bioluminescence.bloom(1, 8.0) == 0.0
    warm = bioluminescence.bloom(1, 20.0)
    assert 0.3 <= warm <= 1.0
    assert bioluminescence.bloom(1, 20.0) == warm            # deterministic
    assert bioluminescence.bloom(1, 13.5) < warm


def test_wake_glow_needs_way_except_for_a_torpedo():
    assert bioluminescence.wake_glow(1.0, "SURFACE", 1.0) == 0.0
    assert bioluminescence.wake_glow(1.0, "SURFACE", 25.0) == 1.0
    assert bioluminescence.wake_glow(0.5, "TORP", 0.0) == 0.5
    assert bioluminescence.wake_glow(1.0, "FLG", 300.0) == 0.0


def test_glow_takes_back_part_of_the_night_only():
    model = _model()
    common = dict(visibility_nm=20.0, illumination=0.1, sea_state=2.0)
    dark = model.margin("SUB", 1.5, night=True, **common)
    glowing = model.margin("SUB", 1.5, night=True, glow=1.0, **common)
    assert glowing > dark
    day = model.margin("SUB", 1.5, night=False, **common)
    assert model.margin("SUB", 1.5, night=False, glow=1.0, **common) == day
    assert glowing < day


def test_world_glow_only_at_night():
    world = World(seed=7)
    world.hour = 12.0
    assert world.glow() == 0.0
    world.hour = 1.0
    assert world.glow() == world.bioluminescence() >= 0.0
