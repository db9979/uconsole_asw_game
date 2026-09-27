"""Save v15: the crewed boat's crew state survives a save and a load."""

import copy
import json
import sys
from pathlib import Path

import pytest

from src.core import config
from src.core.game import Game, _same_save_value
from src.core.save_schema import (CREW_FIELDS, CREW_ORDERS_FIELDS,
                                  SAVE_ROOT_FIELDS, SUB_CREW_FIELDS)

sys.path.insert(0, str(Path(__file__).parent))
from test_opfor_sub import _crewed, _first_difference, _game  # noqa: E402


def _fire_two(game):
    """Two wire-guided crew torpedoes in the water, plus a few orders."""
    sub = game.opfor.sub
    launcher = game.runtime_catalog.launchers[sub.weapon_battery.launcher_key]
    bearing = (sub.course + launcher.arc_center_deg) % 360.0
    assert sub.command_fire(bearing, 5.0, now=game.sim_t) is True
    for _ in range(4):
        game._update_sim(0.05)
    assert sub.command_fire((bearing + 3.0) % 360.0, 4.0, now=game.sim_t) is True
    for _ in range(4):
        game._update_sim(0.05)
    assert sub.set_orders(course=(sub.course + 40.0) % 360.0, speed=4.0,
                          depth=min(sub.depth + 20.0, 80.0)) is True
    assert sub.command_silent(True) is True
    game.opfor.plot.add_mark(sub.x + 1.0, sub.y - 1.0) if hasattr(
        game.opfor.plot, "add_mark") else None
    for _ in range(20):
        game._update_sim(0.25)
    wires = game.opfor.orders.wires
    assert len(wires) == 2 and all(wire.active for wire in wires.values())
    return sub


# Audio-derived sonar display histories: the acoustic receiver's overlap-add
# filter state is transient (as for the frigate), so these rows differ
# slightly after a load without any simulation state differing.
_DISPLAY_HISTORY = ("broadband", "lofar", "lofar_times", "lofar_bearings",
                    "history_times", "echo_history")


def _same_state(left, right, *, display=True):
    """Equal saves apart from the process-global ID high-water marks, which a
    second Game in the same test process advances."""
    left, right = (json.loads(json.dumps(state, allow_nan=False))
                   for state in (left, right))
    for state in (left, right):
        # A load (re)starts the crew hold; it is not simulation state.
        if state.get("crew") is not None:
            state["crew"].pop("hold_s", None)
        if not display:
            for block in (state["sonar"], state["crew"]["station"]["sonar"]):
                for key in _DISPLAY_HISTORY:
                    block.pop(key, None)
    left = {key: value for key, value in left.items() if key != "next_entity_ids"}
    right = {key: value for key, value in right.items() if key != "next_entity_ids"}
    # The game's own comparison (numeric types are interchangeable in JSON).
    assert _same_save_value(left, right), _first_difference(left, right)


def _saved(game, tmp_path):
    data = game.save_state()
    path = tmp_path / "slot.json"
    path.write_text(json.dumps(data, allow_nan=False), encoding="utf-8")
    return data, path


def test_round_trip_crewed_boat_with_two_wires(tmp_path):
    game, _server, _bridge = _crewed(seed=91)
    sub = _fire_two(game)
    data, path = _saved(game, tmp_path)
    assert set(data) == SAVE_ROOT_FIELDS
    crew = data["crew"]
    assert set(crew) == CREW_FIELDS and set(crew["orders"]) == CREW_ORDERS_FIELDS
    assert crew["sub_id"] == sub.id and crew["orders"]["silent"] is True
    assert len(crew["orders"]["wires"]) == 2
    row = next(row for row in data["subs"] if row["id"] == sub.id)
    assert SUB_CREW_FIELDS <= set(row) and row["manual"] is True
    assert data["ui"]["local_side"] == "frigate"

    restored = _game(seed=91)
    assert restored.load_game(str(path))
    boat = restored.opfor
    assert boat is not None and boat.sub_id == sub.id
    assert boat.sub.manual and boat.sub.crew is boat.orders
    assert boat.orders.silent is True
    assert set(boat.orders.wires) == {int(key) for key in crew["orders"]["wires"]}
    assert all(wire.active for wire in boat.orders.wires.values())
    assert boat.sub.order_speed == pytest.approx(4.0)
    _same_state(restored.save_state(), data)


def test_continuation_after_load_matches_unsaved_run(tmp_path):
    left, _s1, _b1 = _crewed(seed=92)
    _fire_two(left)
    data, path = _saved(left, tmp_path)
    right = _game(seed=92)
    assert right.load_game(str(path))
    _same_state(right.save_state(), data)
    for _ in range(1200):
        left._update_sim(0.25)
        right._update_sim(0.25)
    _same_state(left.save_state(), right.save_state(), display=False)


def test_v14_document_rejected():
    game, _server, _bridge = _crewed(seed=93)
    state = json.loads(json.dumps(game.save_state()))
    before = game.save_state()
    legacy = copy.deepcopy(state)
    legacy["version"] = 14
    legacy["save_schema"] = "u-jagd-save-v14"
    assert not game._load_save_data(legacy)
    assert game.save_state() == before and game.opfor is not None


@pytest.mark.parametrize("mutate", [
    lambda crew: crew.pop("hold_s"),
    lambda crew: crew["orders"].pop("wires"),
    lambda crew: crew["orders"].__setitem__("salvo", 3),
    lambda crew: crew["orders"].__setitem__("battery_state", "full"),
    lambda crew: crew["station"].pop("rng"),
    lambda crew: crew.__setitem__("hold_s", config.UBOOT_RESTORE_HOLD_S + 1.0),
    lambda crew: crew["feed"].append(dict(seq=10**8, t=-1.0, stamp="", category="sonar",
                                          text="x")),
])
def test_crew_block_mutations_rejected(mutate):
    game, _server, _bridge = _crewed(seed=94)
    _fire_two(game)
    state = json.loads(json.dumps(game.save_state()))
    before = game.save_state()
    mutate(state["crew"])
    assert not game._load_save_data(state)
    assert game.save_state() == before


def test_wire_for_unknown_torpedo_rejected():
    game, _server, _bridge = _crewed(seed=95)
    _fire_two(game)
    state = json.loads(json.dumps(game.save_state()))
    before = game.save_state()
    wires = state["crew"]["orders"]["wires"]
    key = next(iter(wires))
    wires["999999"] = wires.pop(key)
    assert not game._load_save_data(state)
    assert game.save_state() == before


def test_manual_flag_without_crew_block_rejected():
    game, _server, _bridge = _crewed(seed=96)
    state = json.loads(json.dumps(game.save_state()))
    before = game.save_state()
    state["crew"] = None
    assert not game._load_save_data(state)
    assert game.save_state() == before


def test_load_keeps_local_boat_side_and_hold(tmp_path):
    game = _game(seed=97)
    game.local_side = "uboot"
    game.update(0.1) if hasattr(game, "update") else None
    game.claim_opfor_sub()
    assert game.opfor is not None
    for _ in range(8):
        game._update_sim(0.25)
    data, path = _saved(game, tmp_path)
    assert data["ui"]["local_side"] == "uboot"
    restored = _game(seed=97)
    assert restored.local_side == "frigate"
    assert restored.load_game(str(path))
    assert restored.local_side == "uboot" and restored.opfor is not None
    # An uncrewed loaded boat keeps its binding for the hold, then the AI
    # takes it back through the ordinary crew-departure path.
    assert restored._opfor_hold_s == pytest.approx(config.UBOOT_RESTORE_HOLD_S)
    for _ in range(4):
        restored._update_sim(0.25)
    assert restored._opfor_hold_s == pytest.approx(config.UBOOT_RESTORE_HOLD_S - 1.0)


def test_loaded_crew_binding_is_released_only_after_the_hold(tmp_path):
    game, server, bridge = _crewed(seed=98)
    data, path = _saved(game, tmp_path)
    restored = _game(seed=98)
    assert restored.load_game(str(path))
    server.crewed = False
    bridge.pump(restored, server, now=3.0)
    assert restored.opfor is not None, "hold keeps the loaded crew binding"
    restored._opfor_hold_s = 0.0
    bridge.pump(restored, server, now=4.0)
    assert restored.opfor is None and not any(sub.manual for sub in restored.subs)


def test_uncrewed_save_has_no_crew_block(tmp_path):
    game = _game(seed=99)
    for _ in range(4):
        game._update_sim(0.25)
    data, path = _saved(game, tmp_path)
    assert data["crew"] is None
    assert not any(row["manual"] for row in data["subs"])
    restored = _game(seed=99)
    assert restored.load_game(str(path)) and restored.opfor is None
