"""Stage C: the crewed boat's main ballast, trim tanks and high-pressure air."""

import copy
import json
import sys
from pathlib import Path

import pygame
import pytest

from src.core import config, uboot_local
from src.enemies.ballast import BoatBallast
from src.ui import layout

sys.path.insert(0, str(Path(__file__).parent))
from test_opfor_sub import _crewed, _feed_texts, _run  # noqa: E402
from test_uboot_scope import _key, _local_boat  # noqa: E402


def _pump(ballast, seconds, flooding=0.0, dt=0.5):
    for _ in range(int(seconds / dt)):
        ballast.update(dt, flooding_kg=flooding, compressor=False, vent_ordered=False)


def test_automatic_trim_takes_up_a_torpedo_and_stops_the_pumps():
    ballast = BoatBallast()
    ballast.torpedo_away()
    assert ballast.residual_kg(0.0) == -config.UBOOT_TORPEDO_KG and ballast.trim_deg() < 0.0
    ballast.update(0.5, compressor=False, vent_ordered=False)
    assert ballast.pumping
    _pump(ballast, 200.0)
    assert not ballast.pumping
    assert abs(ballast.residual_kg(0.0)) <= config.UBOOT_PUMP_DEADBAND_KG
    assert abs(ballast.trim_deg()) < 0.05


def test_flooding_beyond_the_regulating_tank_leaves_the_boat_heavy():
    flooding = 20000.0
    ballast = BoatBallast()
    _pump(ballast, 1000.0, flooding=flooding)
    assert ballast.regulating_kg == pytest.approx(-config.UBOOT_REGULATING_KG)
    assert ballast.residual_kg(flooding) == pytest.approx(
        flooding - config.UBOOT_REGULATING_KG)
    assert ballast.vertical_drift_mps(flooding, 0.0) > 0.0
    # Without power the pumps stand still.
    idle = BoatBallast()
    idle.update(10.0, flooding_kg=flooding, compressor=True, vent_ordered=False, power=False)
    assert idle.regulating_kg == 0.0 and not idle.pumping
    assert idle.hp_air_bar == config.UBOOT_HP_AIR_START_BAR


def test_manual_orders_switch_the_automatic_off_and_stay_in_capacity():
    ballast = BoatBallast()
    assert ballast.step("regulating", 1) is True and not ballast.auto
    assert ballast.regulating_order_kg == config.UBOOT_REGULATING_STEP_KG
    for _ in range(100):
        ballast.step("trim", -1)
    assert ballast.trim_order_kg == -config.UBOOT_TRIM_TANK_KG
    assert ballast.step("sideways", 1) == "invalid_value"
    assert ballast.step("trim", 2) == "invalid_value"
    _pump(ballast, 400.0)
    assert ballast.trim_kg == -config.UBOOT_TRIM_TANK_KG and ballast.trim_deg() < 0.0


def test_blows_use_air_the_boat_floods_again_and_the_compressor_refills():
    game, _server, _bridge = _crewed()
    sub = game.opfor.sub
    ballast = sub.ballast
    blows = ballast.blows_left()
    assert blows == int(config.UBOOT_HP_AIR_START_BAR // config.UBOOT_HP_BLOW_BAR) >= 2
    sub.depth = sub.target_depth = 120.0
    sub.set_orders(depth=120.0)
    assert sub.command_blow() is True
    assert ballast.blows_left() == blows - 1 and sub.emergency_ascent
    _run(game, 60.0)
    assert not ballast.dived() and sub.depth <= config.UBOOT_MBT_SURFACE_DEPTH_M + 1e-6
    # Blown: the boat stays up until an order below the surface floods it.
    _run(game, 30.0)
    assert sub.depth <= config.UBOOT_MBT_SURFACE_DEPTH_M + 1e-6 and not ballast.venting
    sub.set_orders(depth=40.0)
    _run(game, config.UBOOT_MBT_VENT_S + 5.0)
    assert ballast.dived() and any("flooded" in text for text in _feed_texts(game))
    _run(game, 60.0)
    assert sub.depth > config.UBOOT_MBT_SURFACE_DEPTH_M + 5.0
    # Out of air: no more blows; the compressor refills while snorkelling.
    ballast.hp_air_bar = config.UBOOT_HP_BLOW_BAR - 1.0
    sub.depth = sub.target_depth = 120.0
    assert sub.command_blow() == "uboot_no_hp_air" and not sub.emergency_ascent
    before = ballast.hp_air_bar
    ballast.update(10.0, compressor=True, vent_ordered=False)
    assert ballast.hp_air_bar == pytest.approx(before + 10.0 * config.UBOOT_HP_COMPRESSOR_BAR_S)


def test_a_heavy_boat_sinks_when_slow_and_is_held_by_the_planes_at_speed():
    game, _server, _bridge = _crewed()
    sub = game.opfor.sub
    game.world.depth_m = lambda x, y: 2000.0
    sub.depth = sub.target_depth = 80.0
    sub.set_orders(depth=80.0, speed=0.0)
    _run(game, 1.0)
    sub.ballast.auto = False
    sub.ballast.regulating_kg = sub.ballast.regulating_order_kg = 6000.0
    _run(game, 60.0)
    sunk = sub.depth - 80.0
    assert sunk > 3.0
    assert any("heavy" in text for text in _feed_texts(game))
    sub.depth = sub.target_depth = 80.0
    sub.speed = 8.0
    sub.set_orders(speed=8.0)
    _run(game, 60.0)
    assert abs(sub.depth - 80.0) < 1.0


def test_trim_pumps_are_audible_only_on_the_crewed_boat():
    game, _server, _bridge = _crewed()
    sub = game.opfor.sub
    quiet_level, quiet_noise = sub.source_level_offset_db(), sub.noise_level()
    sub.ballast.torpedo_away()
    _run(game, 1.0)
    assert sub.pumping
    assert sub.source_level_offset_db() > quiet_level
    assert sub.noise_level() > quiet_noise
    assert config.UBOOT_PUMP_LINE in sub.lofar_lines(game.sim_t)
    sub.manual = False
    assert not sub.pumping


def test_ballast_round_trips_in_saves_and_malformed_blocks_are_rejected(tmp_path):
    game, _server, _bridge = _crewed()
    sub = game.opfor.sub
    sub.ballast.torpedo_away()
    sub.ballast.step("trim", 1)
    _run(game, 5.0)
    data = game.save_state()
    row = next(item for item in data["subs"] if item["id"] == sub.id)
    assert row["ballast"] == json.loads(json.dumps(row["ballast"]))
    path = tmp_path / "slot.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert game.load_game(str(path))
    again = next(item for item in game.subs if item.id == sub.id)
    assert again.ballast.serialize() == row["ballast"]
    before = game.save_state()
    for mutate in (lambda b: b.update(version=2), lambda b: b.update(extra=1),
                   lambda b: b.pop("auto"), lambda b: b.update(mbt=1.5),
                   lambda b: b.update(hp_air_bar=float("nan")),
                   lambda b: b.update(load_kg=10.0), lambda b: b.update(auto=1),
                   lambda b: b.update(blowing=True, venting=True, mbt=0.5),
                   lambda b: b.update(regulating_kg=config.UBOOT_REGULATING_KG + 1.0)):
        broken = copy.deepcopy(data)
        target = next(item for item in broken["subs"] if item["id"] == sub.id)
        mutate(target["ballast"])
        assert not game._load_save_data(broken)
    assert game.save_state() == before


def test_trim_orders_over_remote_crew_and_projection():
    from src.commander.projections import _uboot_ballast
    game, _server, bridge = _crewed()
    sub = game.opfor.sub
    apply = bridge._apply_opfor_action
    assert apply(game, "uboot_trim_auto", {"enabled": False}, "uboot_engine") is True
    assert not sub.ballast.auto
    assert apply(game, "uboot_ballast", {"tank": "regulating", "direction": 1},
                 "uboot_engine") is True
    assert sub.ballast.regulating_order_kg == config.UBOOT_REGULATING_STEP_KG
    assert apply(game, "uboot_ballast", {"tank": "trim", "direction": -1}, "uboot") is True
    assert apply(game, "uboot_ballast", {"tank": "trim", "direction": 1},
                 "uboot_nav") is False
    payload = _uboot_ballast(sub)
    assert payload["regulating_order_kg"] == config.UBOOT_REGULATING_STEP_KG
    assert payload["blows_left"] >= 2 and payload["auto"] is False
    blob = json.dumps(payload)
    for forbidden in ("target_id", "track_id", "kind", "signature", "seed", "rng"):
        assert forbidden not in blob


def test_uconsole_tanks_page_keys_and_draw():
    game, boat = _local_boat()
    uboot_local.set_local_station(game, "uboot_engine")
    boat.command_page = 2
    with layout.capture_geometry() as boxes:
        game.draw()
    titles = {row["title"] for row in boxes}
    assert {"uboot.panel.tanks", "uboot.panel.hp_air", "uboot.panel.trim"} <= titles
    ballast = boat.sub.ballast
    _key(game, pygame.K_z)
    assert not ballast.auto
    _key(game, pygame.K_DOWN)
    assert ballast.regulating_order_kg == config.UBOOT_REGULATING_STEP_KG
    _key(game, pygame.K_UP)
    assert ballast.regulating_order_kg == 0.0
    _key(game, pygame.K_RIGHT)
    assert ballast.trim_order_kg == config.UBOOT_TRIM_STEP_KG
    _key(game, pygame.K_z)
    assert ballast.auto
    game.draw()


def test_a_stopped_boat_against_an_obstacle_reports_it_once():
    game, _server, _bridge = _crewed()
    sub = game.opfor.sub
    game.world.on_land = lambda x, y: True
    sub.set_orders(speed=5.0)
    sub.speed = 5.0
    _run(game, 30.0)
    texts = [text for text in _feed_texts(game) if "Obstacle ahead" in text
             or "obstacle ahead" in text.lower()]
    assert len(texts) == 1 and sub.speed == 0.0
