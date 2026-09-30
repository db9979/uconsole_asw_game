"""Engagement sketch, the boat's navigation dials and the radio room boxes."""

from dataclasses import replace
import math
from types import SimpleNamespace as NS

import pygame
import pytest

from src.core import config, uboot_local
from src.core.game import Game
from src.ui import engagement, layout, uboot_view, weapons_view


def _boat(station, large=False):
    game = Game(seed=61, start_menu=False, audio_enabled=False, language="de")
    game.reset(61, "s1_patrouille")
    game.local_side = "uboot"
    game._update(0.05)
    if large:
        game.preferences = replace(game.preferences, large_text=True)
    uboot_local.set_local_station(game, station)
    pygame.display.set_mode((1280, 720))
    return game


def _draw(game):
    # The whole frame, so the station regions follow the bottom-panel mode.
    with layout.capture_geometry() as shapes, layout.capture_text() as texts:
        game.draw()
    layout.configure_for(large_text=False)
    return shapes, texts


@pytest.mark.parametrize("large", (False, True))
def test_radio_room_text_stays_inside_its_boxes(large):
    game = _boat("uboot_radio", large)
    shapes, texts = _draw(game)
    boxes = [shape["rect"] for shape in shapes
             if shape["kind"] == "box" and shape["title"].startswith("uboot.panel.")]
    assert len(boxes) == 4
    for box in boxes:
        inside = [item for item in texts
                  if box.left <= item["ink"].centerx < box.right
                  and box.top <= item["ink"].top < box.bottom]
        assert inside
        for item in inside:
            # 1.3.109: the HQ order line ran through the box's lower frame.
            assert item["ink"].bottom < box.bottom, (item["text"], box)


def test_boat_navigation_page_has_heading_depth_and_speed_dials():
    game = _boat("uboot")
    shapes, _texts = _draw(game)
    dials = {shape["title"] for shape in shapes if shape["kind"] == "instrument"}
    assert {"heading", "depth", "speed"} <= dials
    ladder = [shape["rect"] for shape in shapes if shape["kind"] == "box"
              and shape["title"] == "uboot.panel.depth_ladder"]
    assert ladder and ladder[0].h >= uboot_view.NAV_LADDER_MIN_H


def test_docked_feed_keeps_the_full_water_column_without_dials():
    game = _boat("uboot")
    game.preferences = replace(game.preferences, bottom_panel="docked")
    shapes, _texts = _draw(game)
    assert not any(shape["kind"] == "instrument" for shape in shapes)
    assert any(shape["title"] == "uboot.panel.depth_ladder" for shape in shapes)


def test_boat_weapons_page_draws_the_engagement_sketch_from_the_contact():
    game = _boat("uboot_weapons")
    boat = game.opfor
    seen = {}
    original = engagement.draw_engagement_sketch

    def spy(screen, rect, **values):
        seen.update(values)
        original(screen, rect, **values)

    engagement.draw_engagement_sketch = spy
    try:
        shapes, _texts = _draw(game)
    finally:
        engagement.draw_engagement_sketch = original
    assert any(shape["kind"] == "instrument" and shape["title"] == "engagement"
               for shape in shapes)
    assert seen["own_course"] == pytest.approx(boat.sub.course)
    assert seen["torpedo_kn"] > 0 and seen["torpedo_range_nm"] > 0
    selected = boat.station.selected_contact
    if selected is None:
        assert seen["bearing"] is None and seen["target"] is None


def test_intercept_leads_a_moving_target_and_gives_up_on_a_faster_one():
    # A stationary target: the torpedo runs straight to it.
    t, point = engagement.intercept(0.0, -5.0, 0.0, 0.0, 40.0)
    assert point == pytest.approx((0.0, -5.0))
    assert t == pytest.approx(5.0 / (40.0 / 3600.0))
    # Crossing east at 15 kn: the point lies ahead of it, and the torpedo
    # and the target arrive there together.
    t, (px, py) = engagement.intercept(0.0, -5.0, 90.0, 15.0, 40.0)
    assert px > 0.0 and py == pytest.approx(-5.0)
    assert math.hypot(px, py) == pytest.approx(40.0 / 3600.0 * t)
    assert px == pytest.approx(15.0 / 3600.0 * t)
    # Running away faster than the torpedo: no solution.
    assert engagement.intercept(0.0, -5.0, 0.0, 50.0, 40.0) is None


def test_frigate_sketch_uses_the_contact_observation_not_the_submarine(monkeypatch):
    pygame.font.init()
    monkeypatch.setattr(config, "STATION_RECT", (640, 30, 640, 660))
    seen = {}
    monkeypatch.setattr(engagement, "draw_engagement_sketch",
                        lambda screen, rect, **values: seen.update(values, rect=rect))
    contact = NS(passive_bearing=None, bearing=90.0, observed_x=4.0, observed_y=0.0,
                 range_est=4.0, range_source="tma", range_seen=0.0, tma_course=180.0,
                 tma_speed=10.0, tma_quality=.6, range_sigma_nm=.3, confidence=.9,
                 depth_est=None, display_label="K01", id=1, player_class=None,
                 classification="UNBEKANNT", position_seen=0.0, seen=0.0)
    game = NS(
        screen=pygame.Surface((1280, 720)), target=contact, sim_t=0.0,
        ship=NS(x=0.0, y=0.0, course=30.0, speed=12.0),
        torpedo_readiness=lambda: ("FEUER FREI", config.COLOR_OK),
        _contact_range_fresh=lambda c: True, weapon_classification=lambda c: "U_BOOT",
        torpedo_count=4, torpedo_total=4, torpedo_depth=50.0, torpedoes=[],
        roe="FREE", station_page=0, flak_authorized=False,
        helo=NS(torps=2, buoys_left=6, airborne=False, state="HANGAR"),
    )
    monkeypatch.setattr(weapons_view.observations, "contact_display_id", lambda g, c: "K01")
    monkeypatch.setattr(weapons_view.observations, "format_bearing_pair",
                        lambda c, ship, compact=False: "090")
    monkeypatch.setattr(weapons_view.observations, "observation_age", lambda c, t: 0.0)
    monkeypatch.setattr(weapons_view.observations, "position_age", lambda c, t: 0.0)
    weapons_view.draw_weapons_panel(game)
    assert seen["bearing"] == pytest.approx(90.0)
    assert seen["target"] == pytest.approx((4.0, 0.0))
    assert (seen["target_course"], seen["target_speed_kn"]) == (180.0, 10.0)
    assert seen["own_course"] == 30.0
    assert seen["rect"][3] >= weapons_view.SKETCH_MIN_H
