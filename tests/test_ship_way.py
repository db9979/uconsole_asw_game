"""Bow waves and wakes of made-out ships and the optics' rim (display only)."""

from pathlib import Path

import pygame

from src.commander.v2 import schema
from src.sensors import lookout_id
from src.ui import horizon, quality, ship_way, sight_scene

ROOT = Path(__file__).resolve().parents[1]


def test_the_way_level_follows_the_speed_in_tenths():
    assert lookout_id.way_level(0.0) == 0.0
    assert lookout_id.way_level(12.5) == 0.5
    assert lookout_id.way_level(40.0) == 1.0
    assert lookout_id.way_level(-3.0) == 0.0


def test_the_bow_points_where_the_eye_sees_her_side():
    bow, stern, face = ship_way.ends(100.0, 80.0, 90.0)
    assert face == 1.0 and bow > 100.0 > stern
    bow, stern, face = ship_way.ends(100.0, 80.0, -90.0)
    assert face == -1.0 and bow < 100.0 < stern


def _picture(way, eyepiece=None):
    s = pygame.Surface((400, 200))
    rows = [(0.0, 8.0, "warship", False, None, None, 90.0, None, way)]
    horizon.draw_horizon(s, (0, 0, 400, 200), line_of_sight=0.0, fov_deg=20.0, night=False,
                         visibility_nm=30.0, motion=(0.0, 0.0), outlines=rows, anim_t=3.0,
                         sea_state=1.0, eyepiece=eyepiece)
    return s


def test_a_fast_ship_throws_up_white_water_a_slow_one_none():
    still, fast = _picture(0.0), _picture(1.0)
    differs = sum(1 for x in range(0, 400, 2) for y in range(80, 130)
                  if still.get_at((x, y)) != fast.get_at((x, y)))
    assert differs > 20


def test_the_eyepiece_rim_darkens_the_corners_but_not_the_centre():
    previous = quality.LEVEL
    try:
        quality.configure("normal")
        plain, rimmed = _picture(0.0), _picture(0.0, "binoculars")
        assert rimmed.get_at((2, 198))[:3] == sight_scene.EYEPIECE_RIM
        assert rimmed.get_at((100, 100)) == plain.get_at((100, 100))
        quality.configure("low")
        assert _picture(0.0, "scope").get_at((2, 198)) == plain.get_at((2, 198))
    finally:
        quality.configure(previous)


def test_the_browser_gets_the_way_of_every_outline():
    assert "way" in schema.LOOKOUT_OUTLINE_FIELDS
    scene = (ROOT / "data/commander/js/views/sight-scene.js").read_text(encoding="utf-8")
    assert "drawShipWay(" in scene and "drawEyepiece(" in scene
