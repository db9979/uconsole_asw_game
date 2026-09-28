"""The crewed submarine's torpedo tubes: loaded one by one, flooded to fire."""

import copy
import json
import sys
from pathlib import Path

import pygame

from src.commander.server import UBOOT_REASONS, V2_ACTION_REGISTRY
from src.core import config, opfor, uboot_local
from src.core.i18n import localize
from src.ui import uboot_view

sys.path.insert(0, str(Path(__file__).parent))
from test_opfor_sub import _crewed, _feed_texts, _run  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _states(sub):
    return [state for state, _left in opfor.tube_states(sub)]


def _fire(sub, game):
    return sub.command_fire(90.0, 3.0, now=game.sim_t)


def _aim(sub):
    sub.course = 90.0


def _reloads(sub, count=4, reload_s=60.0):
    """Give the battery reloads in its racks (the catalog decides the real stock)."""
    battery = sub.weapon_battery
    magazine = next(iter(battery.magazines.values()))
    magazine.capacity += count
    magazine.stowed += count
    battery.reload_s = reload_s
    sub.torpedoes_left = battery.remaining_total


def test_the_crew_takes_over_flooded_tubes_and_reloads_by_hand():
    game, _server, _bridge = _crewed(seed=71)
    sub = game.opfor.sub
    _aim(sub)
    _reloads(sub)
    battery = sub.weapon_battery
    loaded = battery.ready_count
    assert loaded >= 1 and _states(sub)[:loaded] == ["flooded"] * loaded
    assert _fire(sub, game) is True
    fired = battery.last_fired_tube
    # The fired tube stays empty: the crew loads each tube itself.
    _run(game, battery.reload_s + 5.0)
    assert _states(sub)[fired] == "empty"
    for _ in range(loaded - 1):
        game.opfor.sub.pending_torpedoes.clear()
        assert _fire(sub, game) is True
    sub.pending_torpedoes.clear()
    assert sub.fire_readiness() in ("reloading", "uboot_tube_dry")
    assert sub.command_flood_tube() == "uboot_no_dry_tube"
    assert sub.command_load_tube(fired) is True
    assert _states(sub)[fired] == "loading"
    assert sub.command_load_tube(fired) == "uboot_tubes_full"
    _run(game, battery.reload_s + 1.0)
    assert _states(sub)[fired] == "dry"
    assert any(f"Tube {fired + 1} loaded" in text for text in _feed_texts(game))
    # A loaded but dry tube does not fire.
    assert sub.fire_readiness() == "uboot_tube_dry"
    assert _fire(sub, game) == "uboot_tube_dry"
    before = sub.transient_left
    assert sub.command_flood_tube() is True
    assert _states(sub)[fired] == "flooding"
    assert sub.transient_left >= max(before, config.UBOOT_TUBE_FLOOD_NOISE_S - 1e-9)
    _run(game, config.UBOOT_TUBE_FLOOD_S + 1.0)
    assert _states(sub)[fired] == "flooded"
    assert any(f"Tube {fired + 1} flooded" in text for text in _feed_texts(game))
    assert sub.fire_readiness() is None and _fire(sub, game) is True


def test_a_flooded_torpedo_room_cannot_work_the_tubes():
    game, _server, _bridge = _crewed(seed=72)
    sub = game.opfor.sub
    sub.damage_control.down = lambda name: name == "bow"
    assert sub.command_load_tube() == "uboot_compartment_down"
    assert sub.command_flood_tube() == "uboot_compartment_down"


def test_the_ai_boat_keeps_reloading_by_itself():
    game, _server, _bridge = _crewed(seed=73)
    sub = game.opfor.sub
    sub.manual = False
    _reloads(sub)
    assert sub.crew_tubes is None
    battery = sub.weapon_battery
    assert battery.fire() is not None
    battery.update(1.0)
    assert battery.tubes[battery.last_fired_tube].loading_weapon_key is not None


def test_tube_states_survive_a_save_and_bad_ones_are_rejected():
    game, _server, _bridge = _crewed(seed=74)
    sub = game.opfor.sub
    _aim(sub)
    assert _fire(sub, game) is True
    empty = sub.weapon_battery.last_fired_tube
    sub.pending_torpedoes.clear()
    tube = next(index for index, state in enumerate(_states(sub)) if state == "flooded")
    sub.crew.tubes[tube] = ["dry", 0.0]                 # a loaded tube, drained
    assert sub.command_flood_tube(tube) is True
    _run(game, 5.0)
    state = json.loads(json.dumps(game.save_state()))
    tubes = state["crew"]["orders"]["tubes"]
    assert tubes[tube][0] == "flooding" and 0 < tubes[tube][1] < config.UBOOT_TUBE_FLOOD_S
    assert tubes[empty] == ["dry", 0.0]
    assert game._load_save_data(copy.deepcopy(state))
    assert opfor.tube_states(game.opfor.sub)[tube][0] == "flooding"
    for row in (["dry", 0.0], None):
        broken = copy.deepcopy(state)
        if row is None:
            broken["crew"]["orders"]["tubes"].pop()
        else:
            broken["crew"]["orders"]["tubes"].append(row)
        assert not game._load_save_data(broken)
    broken = copy.deepcopy(state)
    broken["crew"]["orders"]["tubes"][empty] = ["flooded", 0.0]      # an empty tube
    assert not game._load_save_data(broken)
    broken = copy.deepcopy(state)
    broken["crew"]["orders"]["tubes"][tube] = ["flooding", 0.0]
    assert not game._load_save_data(broken)
    broken = copy.deepcopy(state)
    broken["crew"]["orders"]["tubes"][tube] = ["open", 0.0]
    assert not game._load_save_data(broken)


def test_the_tube_orders_reach_the_weapons_station_and_the_browser():
    for action in ("uboot_tube_load", "uboot_tube_flood"):
        spec = V2_ACTION_REGISTRY[action]
        assert spec.stations == frozenset({"uboot_weapons"})
        assert spec.validate_params({"tube": None}) and spec.validate_params({"tube": 2})
        assert not spec.validate_params({"tube": -1}) and not spec.validate_params({"tube": "1"})
        assert not spec.validate_params({})
    assert {"uboot_tube_dry", "uboot_tubes_full", "uboot_no_dry_tube"} <= UBOOT_REASONS
    game, server, bridge = _crewed(seed=75)
    sub = game.opfor.sub
    assert bridge._apply_opfor_action(game, "uboot_tube_load", {"tube": None},
                                      "uboot_weapons") in (True, "uboot_tubes_full")
    assert bridge._apply_opfor_action(game, "uboot_tube_flood", {"tube": 0},
                                      "uboot_weapons") == "uboot_no_dry_tube"
    bridge.pump(game, server, now=5.0)
    weapons = server.v2_states["uboot_weapons"]["uboot_weapons"]["weapons"]
    assert [row["state"] for row in weapons["tubes"]] == _states(sub)
    assert weapons["tubes_ready"] == opfor.tubes_flooded(sub)
    base = (ROOT / "data/commander/js/core/base.js").read_text(encoding="utf-8")
    assert "uboot_tube_dry" in base and "uboot_no_dry_tube" in base


def test_the_uconsole_weapons_page_loads_and_floods_with_m():
    game, _server, _bridge = _crewed(seed=76)
    game.local_side = "uboot"
    uboot_local.set_local_station(game, "uboot_weapons")
    sub = game.opfor.sub
    _aim(sub)
    _reloads(sub)
    assert _fire(sub, game) is True
    tube = sub.weapon_battery.last_fired_tube
    sub.pending_torpedoes.clear()
    uboot_local.handle_key(game, pygame.event.Event(pygame.KEYDOWN, key=pygame.K_m, mod=0))
    assert _states(sub)[tube] == "loading"
    _run(game, sub.weapon_battery.reload_s + 1.0)
    uboot_local.handle_key(game, pygame.event.Event(pygame.KEYDOWN, key=pygame.K_m,
                                                    mod=pygame.KMOD_SHIFT))
    assert _states(sub)[tube] == "flooding"
    text = str(localize(uboot_view.tube_line(sub)))
    assert f"{tube + 1} flooding" in text
    uboot_view.draw(game)
