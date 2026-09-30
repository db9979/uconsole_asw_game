"""The crewed boat's towed buoy antenna (save v42 ``crew.orders.buoy``)."""

import copy
import json
import sys
from pathlib import Path

import pygame

from src.commander import projections
from src.core import boat_radio, buoy_antenna, config, opfor, uboot_local
from src.ui import layout, uboot_view

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_opfor_sub import _crewed, _feed_texts  # noqa: E402
from test_uboot_scope import _key, _local_boat  # noqa: E402

BROADCAST = config.UBOOT_RADIO_BROADCAST_S


def _step(game, boat, seconds, dt=0.25):
    end = game.sim_t + seconds
    while game.sim_t < end - 1e-9:
        game.sim_t += dt
        opfor.update_crew(game, boat, dt)


def _deep(boat, depth=50.0, speed=4.0):
    sub = boat.sub
    sub.depth = sub.target_depth = sub.order_depth = depth
    sub.speed = speed


def test_the_winch_streams_and_recovers_and_a_fast_boat_tears_the_buoy_off():
    state = buoy_antenna.new_state()
    assert buoy_antenna.valid_state(state) and buoy_antenna.status(state) == "stowed"
    assert buoy_antenna.order(state, True) is True
    assert buoy_antenna.step(state, 30.0, 4.0) is None
    assert buoy_antenna.status(state) == "streaming" and abs(state[0] - 0.5) < 1e-9
    assert buoy_antenna.step(state, 30.0, 4.0) == "buoy_streamed"
    assert buoy_antenna.streamed(state)
    assert buoy_antenna.receiving(state, 55.0, 5.0)
    assert not buoy_antenna.receiving(state, 70.0, 5.0)      # too deep
    assert not buoy_antenna.receiving(state, 55.0, 8.0)      # pulled under
    assert buoy_antenna.order(state, False) is True
    assert buoy_antenna.step(state, 60.0, 4.0) == "buoy_recovered"
    assert buoy_antenna.status(state) == "stowed"
    buoy_antenna.order(state, True)
    buoy_antenna.step(state, 10.0, 4.0)
    assert buoy_antenna.step(state, 0.25, config.UBOOT_BUOY_TEAR_KN + 1.0) == "buoy_torn"
    assert state == [0.0, False, True] and buoy_antenna.valid_state(state)
    assert buoy_antenna.order(state, True) == "uboot_buoy_lost"
    for broken in ([0.5, True], [1.5, True, False], [0.5, True, True], ["x", False, False],
                   [float("nan"), False, False], (0.0, False, False)):
        assert not buoy_antenna.valid_state(broken)


def test_the_buoy_copies_the_broadcast_deep_and_slow_but_cannot_send():
    game, _server, bridge = _crewed(seed=61)
    boat = game.opfor
    _deep(boat)
    assert boat_radio.reception(boat) is None
    assert bridge._apply_opfor_action(game, "uboot_buoy", {"enabled": True},
                                      "uboot_radio") is True
    game.sim_t = BROADCAST + 1.0
    _step(game, boat, config.UBOOT_BUOY_STREAM_S + 1.0)
    assert any("buoy antenna streamed" in text for text in _feed_texts(game))
    assert boat_radio.reception(boat) == "buoy"
    _step(game, boat, config.UBOOT_BUOY_COPY_S + 2.0)
    assert boat.radio.copied == 1
    # Receiving only: a situation report still needs the mast.
    assert boat.radio.send_sitrep(game, boat) == "uboot_no_antenna"
    view = projections._uboot_radio(game, boat)
    assert view["buoy"] == "out" and view["buoy_rx"] and view["buoy_payout"] == 1.0
    assert json.loads(json.dumps(view)) == view
    # Too fast and it is pulled under; faster still and it is lost.
    boat.sub.speed = config.UBOOT_BUOY_SPEED_KN + 1.0
    assert boat_radio.reception(boat) != "buoy"
    boat.sub.speed = config.UBOOT_BUOY_TEAR_KN + 2.0
    _step(game, boat, 0.5)
    assert boat.orders.buoy[2] and projections._uboot_radio(game, boat)["buoy"] == "lost"
    assert any("torn off" in text for text in _feed_texts(game))
    assert bridge._apply_opfor_action(game, "uboot_buoy", {"enabled": True},
                                      "uboot_radio") == "uboot_buoy_lost"


def test_the_frigate_can_find_the_buoy_close_in_but_not_far_out():
    game, _server, _bridge = _crewed(seed=61)
    boat = game.opfor
    _deep(boat)
    boat.orders.buoy[:] = [1.0, True, False]
    sub = boat.sub
    sub.course = 0.0
    game.world.land_blocks_line = lambda *args: False
    game._lookout_environment = lambda: dict(
        visibility_nm=config.WEATHER_VISIBILITY_MAX_NM, night=False,
        illumination=1.0, sea_state=1.0)
    game.crew_effect = lambda: 1.0

    def seen(distance):
        sub.x, sub.y = game.ship.x + distance, game.ship.y
        game.air_picture._tracks.clear() if hasattr(game.air_picture, "_tracks") else None
        game._update_lookout_picture()
        return [track for track in game.air_picture.tracks(game.sim_t)
                if track.source == "LOOKOUT"]

    near = seen(0.6)
    assert near and all(track.kind in ("SURFACE", "UNKNOWN") for track in near)
    assert not seen(6.0)
    heads = game._surface_heads(20.0)
    assert len(heads) == 1 and heads[0][4] == config.UBOOT_BUOY_RCS_FACTOR
    bx, by = buoy_antenna.position(sub)
    assert abs(by - (sub.y + config.UBOOT_BUOY_TRAIL_NM)) < 1e-9 and abs(bx - sub.x) < 1e-9
    boat.orders.buoy[:] = [0.0, False, False]
    assert not game._surface_heads(20.0)


def test_the_buoy_state_saves_and_malformed_blocks_are_rejected(tmp_path):
    game, _server, _bridge = _crewed(seed=61)
    boat = game.opfor
    boat.orders.buoy[:] = [0.4, True, False]
    data = json.loads(json.dumps(game.save_state()))
    assert data["crew"]["orders"]["buoy"] == [0.4, True, False]
    path = tmp_path / "slot.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert game.load_game(str(path))
    assert game.opfor.orders.buoy == [0.4, True, False]
    before = game.save_state()
    for bad in ([0.4, True], [2.0, True, False], [0.4, True, True], None):
        broken = copy.deepcopy(data)
        broken["crew"]["orders"]["buoy"] = bad
        assert not game._load_save_data(broken)
    broken = copy.deepcopy(data)
    del broken["crew"]["orders"]["buoy"]
    assert not game._load_save_data(broken)
    assert game.save_state() == before


def test_b_on_the_radio_page_streams_the_buoy():
    game, boat = _local_boat(seed=61)
    _key(game, pygame.K_7)
    assert uboot_view.page_name(game, boat) == "UBOOT_RADIO"
    _key(game, pygame.K_b)
    assert boat.orders.buoy[1] is True
    _key(game, pygame.K_b)
    assert boat.orders.buoy[1] is False
    for language in ("en", "de"):
        game.set_language(language) if hasattr(game, "set_language") else None
        layout.configure_for(game)
        uboot_view.draw_command_panel(game, boat)
    assert "uboot_buoy_lost" in uboot_local.UBOOT_LOCAL_REASONS
