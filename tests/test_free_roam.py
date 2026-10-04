"""Free patrol ("Freie Fahrt") for both sides: no time limit, endless HQ
orders, encounters and incidents (src/core/free_roam.py)."""

import copy
import json
import math
import sys
from pathlib import Path

import pytest

from src.core import boat_missions, boat_radio, config, free_roam, tasking
from src.core.game import Game
from src.core.i18n import localize

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_boat_missions import _reason  # noqa: E402


def _frigate(seed=61):
    game = Game(seed=seed, start_menu=False, audio_enabled=False, language="en")
    assert game.start_new_game("frei_fregatte", "fixed", seed=seed)
    return game


def _boat(seed=61):
    game = Game(seed=seed, start_menu=False, audio_enabled=False, language="en")
    game.reset(seed, "frei_uboot")
    game.local_side = "uboot"
    game._update(0.05)
    assert game.opfor is not None
    return game, game.opfor


def _broadcast(game, boat, number):
    """Copy broadcast ``number`` with the mast up at periscope depth."""
    boat.sub.depth = boat.sub.target_depth = 14.0
    boat.orders.mast = True
    game.sim_t = number * config.UBOOT_RADIO_BROADCAST_S + 1.0
    boat.radio.copy_since = game.sim_t - config.UBOOT_RADIO_COPY_S - 0.5
    boat.radio.copy_since = max(boat.radio.copy_since,
                                number * config.UBOOT_RADIO_BROADCAST_S)
    game.sim_t = boat.radio.copy_since + config.UBOOT_RADIO_COPY_S + 0.1
    boat.radio.update(game, boat)


def _order(game, boat, kind):
    """Force an open order of ``kind`` on the free patrol's radio."""
    radio = boat.radio
    for order in radio.orders:
        if order["state"] == "active":
            order["state"], order["ended_t"] = "failed", game.sim_t
    fields = free_roam._order_fields(game, boat, kind, 7)
    assert fields is not None
    radio.order_seq += 1
    order = boat_radio.new_order(radio.order_seq, kind, 7, game.sim_t,
                                 game.sim_t + config.FREE_ORDER_S.get(kind, 1800.0), **fields)
    radio.orders.append(order)
    return order


def test_both_sides_list_a_free_patrol_without_a_time_limit():
    assert config.scenarios_for_side("frigate")[-1] == "frei_fregatte"
    assert config.scenarios_for_side("uboot")[-1] == "frei_uboot"
    assert free_roam.scenario_free("frei_fregatte") and free_roam.scenario_free("frei_uboot")
    assert not free_roam.scenario_free("s1_patrouille")
    game = _frigate()
    assert free_roam.frigate_side(game) and game.mission.open_ended
    assert game.mission.format_remaining(game.mission_time) == "--:--"
    assert game.start_choice_rows() == ("weather", "time")
    assert "Free patrol" in localize(game.mission_objective_display())
    assert not game.subs and game.free_roam["count"] == 0
    # Hours on patrol do not end it.
    game.mission_time = game.sim_t = 30 * 3600.0
    game._check_mission_end()
    assert game.mission_result is None
    boat_game, _boat_ = _boat()
    assert free_roam.boat_side(boat_game) and boat_missions.mode(boat_game) == "free_boat"


def test_frigate_encounters_bring_submarines_raids_and_merchants():
    game = _frigate()
    assert free_roam.encounter(game, 0, "sub") == "sub"
    hostile = [sub for sub in game.subs if sub.side == "hostile"]
    assert len(hostile) == 1
    distance = math.hypot(hostile[0].x - game.ship.x, hostile[0].y - game.ship.y)
    assert config.FREE_SUB_SPAWN_NM[0] - 0.1 <= distance <= config.FREE_SUB_SPAWN_NM[1] + 0.1
    assert free_roam.encounter(game, 1, "sub") == "sub"
    # Two hostile boats about: no third until one is gone.
    assert free_roam.encounter(game, 2, "sub") is None
    assert free_roam.encounter(game, 3, "neutral_sub") == "neutral_sub"
    assert [sub.side for sub in game.subs].count("neutral") == 1
    before = len(game.civilians)
    assert free_roam.encounter(game, 4, "merchants") == "merchants"
    assert len(game.civilians) > before
    game.mission_time = config.FREE_RAID_AFTER_S + 1.0
    assert free_roam.encounter(game, 5, "raid") == "raid" and game.raiders


def test_a_far_unheard_boat_comes_back_as_the_next_encounter():
    game = _frigate()
    free_roam.encounter(game, 0, "sub")
    free_roam.encounter(game, 1, "sub")
    far = game.subs[0]
    far.x, far.y = game.ship.x + config.FREE_RECYCLE_NM + 5.0, game.ship.y
    game.sonar.contacts.pop(far.id, None)
    # What it knew and planned on its last patrol goes with it.
    far.memory["contact_bearing"] = 90.0
    far.memory["contact_age"] = 0.0
    far.pending_torpedoes.append((far.x, far.y, 90.0))
    far.state = "EVADE"
    old_id = far.id
    # The frigate's own picture of it: a TMA hypothesis and an OPZ label.
    game.tma_hypotheses[old_id] = object()
    count = len(game.subs)
    assert free_roam.encounter(game, 2, "sub") == "sub"
    assert len(game.subs) == count
    assert far.memory == far.fresh_memory()
    assert not far.pending_torpedoes and far.state == "PATROLLE"
    # It comes back as a new contact: nothing kept on its old identity fits it.
    assert far.id != old_id and far.id not in game.tma_hypotheses
    assert old_id not in game.tma_hypotheses
    assert far.id == max(sub.id for sub in game.subs)
    assert math.hypot(far.x - game.ship.x, far.y - game.ship.y) <= config.FREE_SUB_SPAWN_NM[1] + 0.1


def test_sinking_a_neutral_submarine_costs_points_once():
    from src.weapons.depth_charge import DepthCharge
    game = _frigate()
    free_roam.encounter(game, 0, "neutral_sub")
    neutral = next(sub for sub in game.subs if sub.side == "neutral")
    score = game.score
    neutral.damage = 99.0
    charge = DepthCharge(1, neutral.x, neutral.y, neutral.depth, depth=neutral.depth)
    game._detonate_depth_charge(charge)
    game._detonate_depth_charge(charge)
    free_roam.update(game, 0.1)
    assert neutral.state == "SINKING"
    assert game.score == score - config.FREE_NEUTRAL_SUNK
    assert game.free_roam["charged"] == [neutral.id]


def test_a_neutral_submarine_lost_without_the_frigate_costs_nothing():
    game = _frigate()
    free_roam.encounter(game, 0, "neutral_sub")
    neutral = next(sub for sub in game.subs if sub.side == "neutral")
    score = game.score
    # Run aground, rammed or hit by the hostile boat: not the frigate's doing.
    neutral.hit(100.0)
    neutral.state, neutral.sunk = "SUNK", True
    for _ in range(3):
        free_roam.update(game, 0.1)
    assert game.score == score and game.free_roam["charged"] == []


def test_encounters_follow_the_schedule_and_the_seed():
    first, second = _frigate(seed=5), _frigate(seed=5)
    for game in (first, second):
        game.sim_t = game.mission_time = 4 * 3600.0
        for _ in range(4):
            game.free_roam["next_t"] = 0.0
            free_roam.update(game, 0.1)
    assert first.free_roam == second.free_roam
    assert first.free_roam["count"] == 4 and first.free_roam["log"]
    assert [(sub.x, sub.y) for sub in first.subs] == [(sub.x, sub.y) for sub in second.subs]


def test_frigate_tasks_never_run_out_and_include_the_sector_patrol():
    game = _frigate()
    board = game.tasking
    assert board.next_offer_t <= config.FREE_TASK_FIRST_S[1]
    board.offers = config.TASK_MAX_OFFERS + 3
    board.next_offer_t = 0.0
    game._update_tasking(0.1)
    assert board.offers == config.TASK_MAX_OFFERS + 4
    task = game._offer_task("patrol")
    assert task is not None and task["kind"] == "patrol"
    assert tasking.valid_task(task)
    assert game.accept_task(task["id"]) is True
    game.ship.x, game.ship.y = task["x"], task["y"]
    score = game.score
    for _ in range(int(config.FREE_PATROL_HOLD_S / 10.0) + 2):
        if task["state"] == "active":
            game._progress_task_patrol(task, 10.0)
    assert task["state"] == "done" and game.score == score + config.SCORE_TASK["patrol"][0]


def test_scenarios_never_offer_the_sector_patrol():
    game = Game(seed=61, start_menu=False, audio_enabled=False, language="en")
    assert game.start_new_game("s1_patrouille", "fixed", seed=61)
    assert not game._task_candidate_patrol()
    assert free_roam.task_interval(game) == (config.TASK_INTERVAL_S, config.TASK_MAX_OFFERS)


def test_boat_orders_come_with_almost_every_broadcast_and_never_run_out():
    game, boat = _boat()
    issued = []
    for number in range(1, 40):
        order = boat.radio.active_order()
        if order is not None:
            boat.radio._close_order(boat, order, "failed", game.sim_t, game)
        _broadcast(game, boat, number)
        order = boat.radio.active_order()
        if order is not None:
            issued.append(order["kind"])
    assert len(issued) > config.UBOOT_ORDER_MAX
    assert set(issued) - set(boat_radio.ORDER_KINDS)
    assert boat_radio.BoatRadio.valid_state(boat.radio.to_save())
    # Each failed order cost its points.
    assert game.free_roam["points"] < 0


def test_an_attack_order_names_a_merchant_and_is_done_when_it_sinks():
    game, boat = _boat()
    order = _order(game, boat, "attack")
    ship = free_roam._civilian(game, order["target_id"])
    assert ship is not None and order["name"]
    x, y = free_roam.target_position(order, game.sim_t)
    assert math.hypot(x - ship.x, y - ship.y) <= 6.0 * config.FREE_ATTACK_SIGMA_NM
    assert "sink the merchant" in localize(boat_missions.objective(game, boat))
    assert free_roam.ai_targets(game, boat.sub) == [ship]
    points = game.free_roam["points"]
    boat_missions.merchant_struck(game, ship)
    assert ship.sunk
    boat.radio._update_orders(game, boat, game.sim_t)
    assert order["state"] == "done"
    assert game.free_roam["points"] == points + config.FREE_ORDER_POINTS["attack"][0]
    # Another merchant sunk without an order still counts a little.
    other = free_roam.merchant(game, ship.x + 3.0, ship.y, 90.0, 5, 0, set())
    boat_missions.merchant_struck(game, other)
    assert game.free_roam["points"] == (points + config.FREE_ORDER_POINTS["attack"][0]
                                        + config.FREE_MERCHANT_SUNK)


def test_the_supply_boat_fills_torpedoes_and_battery():
    game, boat = _boat()
    sub = boat.sub
    battery = sub.weapon_battery
    while battery.remaining_total > 0 and battery.magazines:
        magazine = next(item for item in battery.magazines.values() if item.stowed)
        magazine.stowed -= 1
        if not any(item.stowed for item in battery.magazines.values()):
            break
    sub.endurance.battery_kwh = 0.1 * sub.endurance.profile.battery_capacity_kwh
    assert free_roam._supply_needed(sub)
    order = _order(game, boat, "supply")
    sub.x, sub.y = order["x"], order["y"]
    sub.depth, sub.speed = 14.0, 1.0
    boat.radio._update_orders(game, boat, game.sim_t)
    assert order["since"] == game.sim_t and order["state"] == "active"
    game.sim_t += config.FREE_SUPPLY_HOLD_S + 1.0
    boat.radio._update_orders(game, boat, game.sim_t)
    assert order["state"] == "done"
    assert battery.remaining_total == battery.capacity_total
    assert sub.endurance.battery_kwh == sub.endurance.profile.battery_capacity_kwh


def test_the_hunt_gives_the_frigate_a_lead_and_warns_the_boat(monkeypatch):
    game, boat = _boat()
    assert game.hunter_lead is None
    # No reported hunt in the first half hour.
    assert free_roam.encounter(game, 0, "hunt") is None
    monkeypatch.setattr(config, "FREE_HUNT_AFTER_S", 0.0)
    assert free_roam.encounter(game, 0, "hunt") == "hunt"
    assert game.hunter_lead is not None and game.hunter_lead["hq"] is not None
    game.free_roam["log"].append({"t": game.sim_t, "kind": "hunt"})
    # At most one an hour.
    assert free_roam.encounter(game, 1, "hunt") is None


def test_the_boat_patrol_ends_with_the_boat_or_the_frigate():
    game, boat = _boat()
    boat.sub.sunk = True
    game._check_mission_end()
    assert game.mission_result == "SIEG" and _reason(game) == "end.reason.free_boat_lost"
    game, boat = _boat()
    points = game.free_roam["points"]
    game.damage.ship_sunk = True
    game._check_mission_end()
    assert game.mission_result == "VERLOREN"
    assert _reason(game) == "end.reason.free_boat_frigate"
    assert game.free_roam["points"] == points + config.FREE_FRIGATE_SUNK
    frigate = _frigate()
    frigate.damage.ship_sunk = True
    frigate._check_mission_end()
    assert frigate.mission_result == "VERLOREN"
    assert _reason(frigate) == "end.reason.free_frigate_lost"


@pytest.mark.parametrize("side", ["frigate", "uboot"])
def test_a_free_patrol_saves_and_loads(side, tmp_path):
    if side == "frigate":
        game = _frigate()
        free_roam.encounter(game, 0, "sub")
        free_roam.encounter(game, 1, "merchants")
    else:
        game, boat = _boat()
        _order(game, boat, "attack")
    for _ in range(20):
        game._update_sim(0.1)
    state = json.loads(json.dumps(game.save_state()))
    assert state["free_roam"] == game.free_roam
    loaded = Game(seed=1, start_menu=False, audio_enabled=False, language="en")
    loaded.local_side = game.local_side
    for broken in (dict(copy.deepcopy(state), free_roam=dict(state["free_roam"], points=1.5)),
                   dict(copy.deepcopy(state), scenario_key="s1_patrouille")):
        assert not loaded._load_save_data(broken)
    assert loaded._load_save_data(copy.deepcopy(state))
    assert loaded.free_roam == game.free_roam
    assert free_roam.active(loaded)
