"""Stage D: the crewed boat's compartments, leaks, fire, gas and teams."""

import copy
import json
import sys
from pathlib import Path

import pygame
import pytest

from src.core import config, uboot_local
from src.enemies.damage_control import COMPARTMENTS, BoatDamageControl, capacity_kg
from src.ui import layout

sys.path.insert(0, str(Path(__file__).parent))
from test_opfor_sub import _crewed, _feed_texts, _run  # noqa: E402
from test_uboot_scope import _key, _local_boat  # noqa: E402


def _step(control, seconds, depth=100.0, dt=0.5):
    notices = []
    for _ in range(int(seconds / dt)):
        notices += control.update(dt, depth_m=depth)
    return notices


def _index(name):
    return COMPARTMENTS.index(name)


def test_a_leak_floods_with_depth_and_spills_into_open_neighbours():
    shallow, deep = BoatDamageControl(), BoatDamageControl()
    for control in (shallow, deep):
        control.compartments[_index("quarters")].leak = 1.0
    _step(shallow, 10.0, depth=25.0)
    _step(deep, 10.0, depth=100.0)
    assert deep.total_water_kg() == pytest.approx(2.0 * shallow.total_water_kg())
    assert deep.total_water_kg() == pytest.approx(config.UBOOT_DC_LEAK_KG_S * 10.0)
    # Past half full the water runs on through open bulkheads, not shut ones.
    open_boat, shut_boat = BoatDamageControl(), BoatDamageControl()
    for control in (open_boat, shut_boat):
        control.compartments[_index("quarters")].water_kg = capacity_kg(_index("quarters"))
    shut_boat.set_bulkhead("quarters", True)
    _step(open_boat, 20.0, depth=50.0)
    _step(shut_boat, 20.0, depth=50.0)
    assert open_boat.compartments[_index("control")].water_kg > 0.0
    assert open_boat.compartments[_index("battery")].water_kg > 0.0
    assert shut_boat.compartments[_index("control")].water_kg == 0.0
    assert shut_boat.compartments[_index("battery")].water_kg == 0.0
    # Floodwater forward trims the boat bow down.
    bow = BoatDamageControl()
    bow.compartments[_index("bow")].water_kg = 4000.0
    assert bow.water_moment_kg() > 0.0


def test_teams_walk_seal_pump_and_fight_fire():
    control = BoatDamageControl()
    engine = control.compartments[_index("engine")]
    engine.leak, engine.fire = 1.0, 0.5
    assert control.order_team(0, "engine", "seal") is True
    assert control.order_team(1, "engine", "fire") is True
    # Two compartments from the quarters.
    assert control.teams[0]["transit_s"] == 2 * config.UBOOT_DC_TRANSIT_S
    notices = _step(control, 2 * config.UBOOT_DC_TRANSIT_S + config.UBOOT_DC_SEAL_S + 1.0)
    keys = [key for key, _values in notices]
    assert engine.leak == 0.0 and engine.fire == 0.0
    assert "dc_leak_sealed" in keys and "dc_fire_out" in keys
    assert control.order_team(0, "engine", "pump") is True
    water = engine.water_kg
    _step(control, 10.0)
    assert engine.water_kg == pytest.approx(max(0.0, water - config.UBOOT_DC_PUMP_KG_S * 10.0))
    assert control.pumping
    for bad in ((2, "engine", "seal"), (0, "galley", "seal"), (0, "engine", "dance"),
                (True, "engine", "seal")):
        assert control.order_team(*bad) == "invalid_value"
    assert control.set_bulkhead("engine", 1) == "invalid_value"


def test_a_fire_spreads_through_open_bulkheads_and_dies_behind_shut_ones():
    control = BoatDamageControl()
    control.compartments[_index("engine")].fire = 1.0
    _step(control, 30.0)
    assert control.compartments[_index("battery")].fire > 0.0
    assert control.compartments[_index("stern")].fire > 0.0
    starved = BoatDamageControl()
    starved.compartments[_index("engine")].fire = 1.0
    starved.set_bulkhead("engine", True)
    _step(starved, config.UBOOT_DC_FIRE_STARVE_S + 1.0)
    assert starved.compartments[_index("engine")].fire == 0.0
    assert starved.compartments[_index("battery")].fire == 0.0
    # A compartment half full of water puts its fire out.
    wet = BoatDamageControl()
    wet.compartments[_index("bow")].fire = 1.0
    wet.compartments[_index("bow")].water_kg = capacity_kg(_index("bow")) * 0.6
    _step(wet, 1.0)
    assert wet.compartments[_index("bow")].fire == 0.0


def test_seawater_on_the_battery_makes_gas_and_cuts_the_power():
    control = BoatDamageControl()
    battery = control.compartments[_index("battery")]
    battery.water_kg = config.UBOOT_DC_POWER_WATER_KG + 100.0
    notices = _step(control, 60.0)
    keys = [key for key, _values in notices]
    assert not control.power()
    assert battery.chlorine > 0.0 and "dc_chlorine" in keys
    # Gas halves the teams' work, and without power they pump by hand.
    control.order_team(0, "battery", "pump")
    control.teams[0]["transit_s"] = 0.0
    before = battery.water_kg
    _step(control, 10.0)
    rate = config.UBOOT_DC_PUMP_KG_S * config.UBOOT_DC_HAND_PUMP * (
        config.UBOOT_DC_GAS_FACTOR if battery.chlorine >= 0.5 else 1.0)
    assert before - battery.water_kg == pytest.approx(rate * 10.0, rel=0.3)
    battery.water_kg = config.UBOOT_DC_POWER_WATER_KG + 1.0
    notices = _step(control, 2.0)
    assert control.power() and ("dc_power_restored", {}) in notices


def test_hits_on_the_crewed_boat_hole_compartments_deterministically():
    first, second = BoatDamageControl(), BoatDamageControl()
    for control in (first, second):
        control.apply_hit(60.0, 1234)
    assert first.serialize() == second.serialize()
    holed = [c for c in first.compartments if c.leak > 0.0]
    assert len(holed) == 2 and max(c.leak for c in holed) == pytest.approx(0.9)
    game, _server, _bridge = _crewed()
    sub = game.opfor.sub
    sub.hit(40.0)
    assert sub.damage_control.any_damage()
    ai = next((s for s in game.subs if not s.manual), None)
    if ai is not None:
        ai.hit(40.0)
        assert not ai.damage_control.any_damage()


def test_a_flooding_boat_gets_heavy_and_its_stations_go_down():
    game, _server, _bridge = _crewed()
    sub = game.opfor.sub
    game.world.depth_m = lambda x, y: 2000.0
    sub.depth = sub.target_depth = 80.0
    sub.set_orders(depth=80.0, speed=0.0)
    _run(game, 1.0)
    control = sub.damage_control
    control.compartments[_index("bow")].water_kg = capacity_kg(_index("bow")) - 50.0
    control.compartments[_index("bow")].leak = 1.0
    _run(game, 20.0)
    assert sub.ballast.residual_kg(sub.flooding_kg()) > config.UBOOT_HEAVY_WARN_KG
    assert sub.ballast.trim_deg(sub.flood_moment_kg()) > 0.0
    assert sub.depth > 80.0
    assert sub.fire_readiness() == "uboot_compartment_down"
    control.compartments[_index("control")].fire = 0.9
    sub.depth = 5.0
    assert sub.command_mast(True) == "uboot_compartment_down"
    sub.depth = 80.0
    # No power: the motor stops.
    control.compartments[_index("battery")].water_kg = config.UBOOT_DC_POWER_WATER_KG - 5.0
    control.compartments[_index("battery")].leak = 0.5
    sub.set_orders(speed=8.0)
    _run(game, 5.0)
    assert sub.speed_order == 0.0            # the boat only coasts down
    texts = " ".join(_feed_texts(game))
    assert "Power lost" in texts and "Bow room" in texts


def test_damage_control_round_trips_in_saves_and_malformed_blocks_are_rejected(tmp_path):
    game, _server, _bridge = _crewed()
    sub = game.opfor.sub
    sub.hit(30.0)
    sub.command_dc_team(1, "stern", "pump")
    sub.command_bulkhead("battery", True)
    _run(game, 3.0)
    data = game.save_state()
    row = next(item for item in data["subs"] if item["id"] == sub.id)
    assert row["damage_control"] == json.loads(json.dumps(row["damage_control"]))
    path = tmp_path / "slot.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert game.load_game(str(path))
    again = next(item for item in game.subs if item.id == sub.id)
    assert again.damage_control.serialize() == row["damage_control"]
    before = game.save_state()
    for mutate in (lambda b: b.update(version=2), lambda b: b.update(extra=1),
                   lambda b: b.pop("hits"), lambda b: b["teams"].pop(),
                   lambda b: b["teams"][0].update(task="nap"),
                   lambda b: b["teams"][0].update(transit_s=-1.0),
                   lambda b: b["compartments"].pop("bow"),
                   lambda b: b["compartments"]["bow"].update(leak=1.5),
                   lambda b: b["compartments"]["bow"].update(water_kg=float("nan")),
                   lambda b: b["compartments"]["bow"].update(closed=0)):
        broken = copy.deepcopy(data)
        target = next(item for item in broken["subs"] if item["id"] == sub.id)
        mutate(target["damage_control"])
        assert not game._load_save_data(broken)
    assert game.save_state() == before


def test_damage_control_over_remote_crew_and_projection():
    from src.commander.projections import _uboot_damage
    game, _server, bridge = _crewed()
    sub = game.opfor.sub
    apply = bridge._apply_opfor_action
    assert apply(game, "uboot_dc_team", {"team": 1, "compartment": "bow", "task": "seal"},
                 "uboot_engine") is True
    assert sub.damage_control.teams[1]["compartment"] == "bow"
    assert apply(game, "uboot_bulkhead", {"compartment": "engine", "closed": True},
                 "uboot") is True
    assert sub.damage_control.compartments[_index("engine")].closed
    assert apply(game, "uboot_bulkhead", {"compartment": "engine", "closed": False},
                 "uboot_nav") is False
    payload = _uboot_damage(sub)
    assert [row["name"] for row in payload["compartments"]] == list(COMPARTMENTS)
    assert payload["teams"][1]["task"] == "seal" and payload["power"] is True
    blob = json.dumps(payload)
    for forbidden in ("target_id", "track_id", "kind", "signature", "seed", "rng"):
        assert forbidden not in blob


def test_uconsole_damage_page_keys_and_draw():
    game, boat = _local_boat()
    uboot_local.set_local_station(game, "uboot_engine")
    boat.command_page = 3
    control = boat.sub.damage_control
    control.compartments[_index("bow")].leak = 0.5
    control.compartments[_index("engine")].fire = 0.4
    control.compartments[_index("battery")].chlorine = 0.3
    control.set_bulkhead("stern", True)
    with layout.capture_geometry() as boxes:
        game.draw()
    titles = {row["title"] for row in boxes}
    assert {"uboot.panel.compartments", "uboot.panel.dc_status",
            "uboot.panel.dc_teams"} <= titles
    _key(game, pygame.K_DOWN)
    assert boat.dc_selected == 1
    _key(game, pygame.K_RIGHT)
    _key(game, pygame.K_RIGHT)
    assert boat.dc_task == "fire"
    _key(game, pygame.K_RETURN)
    assert control.teams[0]["compartment"] == "control" and control.teams[0]["task"] == "fire"
    _key(game, pygame.K_RETURN, pygame.KMOD_SHIFT)
    assert control.teams[1]["compartment"] == "control"
    _key(game, pygame.K_i)
    assert control.compartments[_index("control")].closed
    _key(game, pygame.K_i)
    assert not control.compartments[_index("control")].closed
    game.draw()
