"""Charted wrecks: chart symbols, seabed obstacle, submarine hiding, echo merging."""

import copy
import json
import math

import pygame
import pytest

from src.core import config
from src.core.game import Game
from src.enemies import sub as sub_module
from src.sonar import equation
from src.ui import chart_symbols
from src.ui.map_view import map_hit_target


@pytest.fixture
def game():
    current = Game(seed=4242, start_menu=False, audio_enabled=False, language="en")
    yield current
    current.audio.shutdown()


def _wreck(game, deep=False):
    for hazard in game.world.charted_hazards():
        if hazard.kind != "wreck":
            continue
        if not deep or game.world.charted_depth_m(hazard.x_nm, hazard.y_nm) > 80.0:
            return hazard
    pytest.skip("no suitable wreck in this world")


def test_wrecks_raise_the_seabed_only_within_their_footprint(game):
    wreck = _wreck(game)
    world = game.world
    on = world.depth_m(wreck.x_nm, wreck.y_nm)
    assert on <= wreck.top_depth_m + 1e-9
    # The chart datum is the plain bathymetry; the wreck is a charted symbol.
    assert world.charted_depth_m(wreck.x_nm, wreck.y_nm) > wreck.top_depth_m
    beside = world.depth_m(wreck.x_nm + wreck.radius_nm + 0.05, wreck.y_nm)
    assert beside > on


def test_chart_tooltip_describes_a_charted_wreck(game):
    wreck = _wreck(game)
    game.station = config_station = game.station
    view = game.map_view
    view.cx, view.cy = wreck.x_nm, wreck.y_nm
    view.scale = 40.0
    from src.ui import layout
    layout.configure_for(game)
    shown = copy.copy(view)
    shown.set_rect(config.MAP_RECT)
    pos = shown.world_to_screen(wreck.x_nm, wreck.y_nm)
    payload = map_hit_target(game, (int(pos[0]), int(pos[1])))
    assert payload is not None
    assert "wreck" in json.dumps(payload).lower() or payload.get("target_id", "").startswith("chart:wreck")
    assert chart_symbols.hazard_at([wreck], shown.world_to_screen, pos) is wreck
    del config_station


def test_hazard_symbols_are_drawn_on_the_bridge_chart(game):
    wreck = _wreck(game)
    game.map_view.cx, game.map_view.cy = wreck.x_nm, wreck.y_nm
    game.map_view.scale = 20.0
    game.draw()
    shown = copy.copy(game.map_view)
    shown.set_rect(config.MAP_RECT)
    px, py = shown.world_to_screen(wreck.x_nm, wreck.y_nm)
    colours = {tuple(game.screen.get_at((int(px) + dx, int(py)))[:3]) for dx in range(-5, 6)}
    assert chart_symbols.WRECK_COLOR in colours


def _hiding_sub(game):
    """Put the first boat 1 NM from the first wreck it can lie beside."""
    sub = game.subs[0]
    for wreck in game.world.charted_hazards():
        if wreck.kind != "wreck":
            continue
        for dx, dy in ((1.0, 0.0), (-1.0, 0.0), (0.0, 1.0), (0.0, -1.0)):
            x, y = wreck.x_nm + dx, wreck.y_nm + dy
            if game.world.depth_m(x, y) < 60.0 or game.world.on_land(x, y):
                continue
            sub.x, sub.y = x, y
            sub.depth = sub.target_depth = 30.0
            spot = sub.wreck_hiding_spot(game.world)
            if spot is not None and spot[0] is wreck:
                sub.state = "WRACK"
                sub.evac_left = 3000.0
                return sub, spot
    pytest.skip("no reachable wreck berth in this world")


def test_submarine_settles_on_the_bottom_beside_a_wreck_and_stays_put(game):
    sub, (_wreck_hazard, bx, by, bottom) = _hiding_sub(game)
    for _ in range(4000):
        sub.update(1.0, None, game.world)
        if sub.bottomed and sub.depth >= bottom - sub_module.SUB_BOTTOM_CLEARANCE_M - 1.0:
            break
    assert sub.bottomed
    assert math.hypot(sub.x - bx, sub.y - by) < 0.05
    assert sub.depth == pytest.approx(bottom - sub_module.SUB_BOTTOM_CLEARANCE_M, abs=1.5)
    x, y = sub.x, sub.y
    for _ in range(120):
        sub.update(1.0, None, game.world)
    # Lying on the seabed: no way, no drift with the current.
    assert (sub.x, sub.y) == (x, y) and sub.speed == 0.0
    assert sub.quiet_factor() >= 0.97


def test_hide_ends_and_the_boat_patrols_again(game):
    sub, _spot = _hiding_sub(game)
    sub.evac_left = 5.0
    for _ in range(10):
        sub.update(1.0, None, game.world)
    assert sub.state == "PATROLLE" and not sub.bottomed


def test_evading_boat_near_the_frigate_prefers_a_wreck(game):
    sub, _spot = _hiding_sub(game)
    sub.state = "EVADE"
    sub.evac_left = 0.5
    sub.memory["contact"] = dict(x=sub.x + 2.0, y=sub.y, course=0.0, speed=10.0, noise=0.5)
    sub.memory["contact_bearing"] = 90.0
    sub.memory["contact_age"] = 0.0
    sub.update(1.0, None, game.world)
    assert sub.state == "WRACK"


def test_bottomed_state_survives_save_and_load(game):
    sub, (_hazard, bx, by, bottom) = _hiding_sub(game)
    for _ in range(4000):
        sub.update(1.0, None, game.world)
        if sub.bottomed and sub.depth >= bottom - sub_module.SUB_BOTTOM_CLEARANCE_M - 1.0:
            break
    state = json.loads(json.dumps(game.save_state()))
    restored = Game(seed=1, start_menu=False, audio_enabled=False, language="en")
    try:
        assert restored._load_save_data(copy.deepcopy(state))
        twin = next(item for item in restored.subs if item.id == sub.id)
        assert twin.state == "WRACK" and twin.bottomed
        x, y = twin.x, twin.y
        twin.update(1.0, None, restored.world)
        assert (twin.x, twin.y) == (x, y)
    finally:
        restored.audio.shutdown()


def test_resolution_decides_whether_an_echo_merges_with_a_wreck():
    assert equation.range_resolution_m("CW") == pytest.approx(750.0)
    assert equation.range_resolution_m("LFM") == pytest.approx(7.5)
    # 60 m apart in range, same beam, no Doppler: CW merges, LFM separates.
    assert equation.echo_merges_with_clutter(9260.0, 90.0, 0.0, 9200.0, 90.2, "CW")
    assert not equation.echo_merges_with_clutter(9260.0, 90.0, 0.0, 9200.0, 90.2, "LFM")
    # A moving boat has Doppler; a different beam separates too.
    assert not equation.echo_merges_with_clutter(9260.0, 90.0, 3.0, 9200.0, 90.2, "CW")
    assert not equation.echo_merges_with_clutter(9260.0, 90.0, 0.0, 9200.0, 110.0, "CW")


def test_sonar_masks_a_bottomed_boat_beside_a_wreck_for_cw_only(game):
    sub, (hazard, bx, by, _bottom) = _hiding_sub(game)
    sub.x, sub.y, sub.speed, sub.speed_order = bx, by, 0.0, 0.0
    # Frigate on the line wreck -> berth, so the boat is offset in range.
    dx, dy = bx - hazard.x_nm, by - hazard.y_nm
    norm = math.hypot(dx, dy)
    game.ship.x = hazard.x_nm - dx / norm * 4.0
    game.ship.y = hazard.y_nm - dy / norm * 4.0
    sonar = game.sonar
    sonar.ping_pulse = "CW"
    assert sonar._masked_by_wreck(sub, game.ship, game.world, "BOW")
    sonar.ping_pulse = "LFM"
    assert not sonar._masked_by_wreck(sub, game.ship, game.world, "BOW")
    sonar.ping_pulse = "CW"
    sub.speed = 5.0
    assert not sonar._masked_by_wreck(sub, game.ship, game.world, "BOW")
