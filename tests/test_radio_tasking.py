"""HQ tasks in the radio room: offers, answers, progress, saves (save v21)."""

import copy
import json
import math

import pytest

from src.commander import projections
from src.core import config
from src.core.game import Game
from src.core.tasking import TaskBoard, valid_task


def _game(seed=4101):
    game = Game(seed=seed, start_menu=False, audio_enabled=False)
    game.tasking.next_offer_t = 1e9     # no scheduled offers in these tests
    return game


def _slow(game, seconds, dt=0.5):
    for _ in range(int(seconds / dt)):
        game.sim_t += dt
        game._update_tasking(dt)


def _only_ship(game):
    """Keep one neutral merchant near the frigate; the others steam far away."""
    ships = sorted(game.civilians, key=lambda item: item.id)
    for other in ships[1:]:
        other.x, other.y = game.ship.x + 200.0, game.ship.y + 200.0
    return ships[0]


def _park(game, x, y, speed=0.0):
    game.ship.x, game.ship.y = x, y
    game.ship.speed = game.ship.target_speed = speed


def test_first_offer_is_scheduled_and_custom_missions_have_none():
    game = Game(seed=4102, start_menu=False, audio_enabled=False)
    low, high = config.TASK_FIRST_OFFER_S
    assert low <= game.tasking.next_offer_t <= high
    again = Game(seed=4102, start_menu=False, audio_enabled=False)
    assert again.tasking.next_offer_t == game.tasking.next_offer_t
    assert TaskBoard(None).enabled is False


def test_schedule_offers_a_task_and_no_answer_counts_as_declined():
    game = _game()
    game.tasking.next_offer_t = 0.0
    score = game.score
    game._update_tasking(0.5)
    (task,) = game.tasking.tasks
    assert task["state"] == "offered"
    assert game.tasking.next_offer_t >= config.TASK_INTERVAL_S[0]
    assert any("task.offer." in json.dumps(text) for _, text in game.messages)
    _slow(game, config.TASK_RESPONSE_S + 1.0)
    assert task["state"] == "declined"
    assert game.score == score + config.SCORE_TASK[task["kind"]][2]


def test_accept_plots_the_report_and_decline_costs_points():
    game = _game()
    task = game._offer_task("datum")
    assert game.accept_task(task["id"]) is True
    assert task["state"] == "active" and task["deadline_t"] is not None
    plotted = [item for item in game.plot.objects if item["id"] == task["plot_id"]]
    assert plotted and plotted[0]["kind"] == "circle"
    assert game.accept_task(task["id"]) == "not_ready"
    assert game.decline_task(999) == "stale_ref"
    other = game._offer_task("emcon")
    score = game.score
    assert game.decline_task(other["id"]) is True
    assert other["state"] == "declined"
    assert game.score == score + config.SCORE_TASK["emcon"][2]


def test_radio_room_down_cannot_answer():
    game = _game()
    task = game._offer_task("datum")
    game.damage.compartments["radio"].state = "ZERSTOERT"
    assert game.damage.station_down("radio")
    assert game.accept_task(task["id"]) == "radio_down"


def test_sar_recovered_by_the_ship_alongside_at_slow_speed():
    game = _game()
    task = game._offer_task("sar")
    assert task["persons"] >= 2 and task["deadline_t"] > game.sim_t
    # The report carries the EPIRB error; the raft itself is elsewhere.
    assert (task["x"], task["y"]) != (task["true_x"], task["true_y"])
    assert game.accept_task(task["id"]) is True
    score = game.score
    _park(game, task["true_x"], task["true_y"] + 0.1, speed=2.0)
    _slow(game, 1.0)
    assert task["sighted"] and task["radius_nm"] == 0.3
    _slow(game, config.TASK_SAR_SHIP_S + 5.0)
    assert task["state"] == "done"
    assert game.score == score + config.SCORE_TASK["sar"][0]
    assert task["plot_id"] is None


def test_sar_too_fast_does_not_count_and_the_survival_time_runs_out():
    game = _game()
    task = game._offer_task("sar")
    game.accept_task(task["id"])
    _park(game, task["true_x"], task["true_y"], speed=10.0)
    remaining = task["deadline_t"] - game.sim_t
    for _ in range(int(remaining / 5.0) + 2):
        game.ship.x, game.ship.y = task["true_x"], task["true_y"]
        game.sim_t += 5.0
        game._update_tasking(5.0)
        if task["state"] != "active":
            break
    assert task["state"] == "failed"
    assert task["points"] == config.SCORE_TASK["sar"][1]


def test_sar_helicopter_hoists_the_survivors():
    game = _game()
    task = game._offer_task("sar")
    game.accept_task(task["id"])
    game.helo.launch(game.ship)
    needed = config.TASK_SAR_HELO_S_PER_PERSON * task["persons"]
    for _ in range(int(needed / 0.5) + 4):
        game.helo.x, game.helo.y = task["true_x"], task["true_y"]
        game.sim_t += 0.5
        game._update_tasking(0.5)
    assert task["state"] == "done"


def test_raft_drifts_with_current_and_wind():
    game = _game()
    task = game._offer_task("sar")
    start = (task["true_x"], task["true_y"])
    _slow(game, 600.0, dt=5.0)
    assert (task["true_x"], task["true_y"]) != start


def test_datum_searched_inside_the_circle():
    game = _game()
    task = game._offer_task("datum")
    game.accept_task(task["id"])
    _park(game, task["x"], task["y"], speed=12.0)
    _slow(game, config.TASK_DATUM_SEARCH_S + 1.0)
    assert task["state"] == "done"


def test_identify_by_helicopter_close_aboard():
    game = _game()
    ship = _only_ship(game)
    ship.x, ship.y = game.ship.x + 10.0, game.ship.y
    task = game._offer_task("identify")
    assert task["target_id"] == ship.id and task["name"] == ship.name
    game.accept_task(task["id"])
    game.helo.launch(game.ship)
    game.helo.x, game.helo.y = ship.x, ship.y + 0.5
    _slow(game, 0.5)
    assert task["state"] == "done" and task["verdict"] in ("clear", "suspect")


def test_identify_by_the_lookout_needs_its_published_identification():
    game = _game()
    ship = _only_ship(game)
    ship.x, ship.y = game.ship.x + 5.0, game.ship.y
    task = game._offer_task("identify")
    game.accept_task(task["id"])
    _slow(game, 0.5)
    assert task["state"] == "active"
    game.world.hour = 12.0
    ship.x, ship.y = game.ship.x + 1.0, game.ship.y
    game._update_lookout_picture()
    _slow(game, 0.5)
    assert task["state"] == "done"


def test_replenishment_alongside_fills_fuel_and_torpedoes():
    game = _game()
    game.ship.fuel_kg = 0.5 * game.ship.fuel_capacity_kg
    game.player_torpedo_battery.fire()
    game.torpedo_count = game.player_torpedo_battery.remaining_total
    assert game.torpedo_count < game.torpedo_total
    count = len(game.civilians)
    task = game._offer_task("ras")
    tanker = game.civilians[-1]
    assert len(game.civilians) == count + 1 and tanker.side == "friendly"
    assert tanker.id == task["target_id"] and tanker.speed == config.TASK_RAS_SPEED_KN
    game.accept_task(task["id"])
    assert any(item["kind"] == "dr" and item["t"] == task["report_t"]
               for item in game.plot.objects)
    for _ in range(int(config.TASK_RAS_S / 0.5) + 4):
        game.ship.x, game.ship.y = tanker.x + 0.1, tanker.y
        game.ship.speed = tanker.speed
        game.sim_t += 0.5
        game._update_tasking(0.5)
    assert task["state"] == "done"
    assert game.ship.fuel_kg == game.ship.fuel_capacity_kg
    assert game.torpedo_count == game.torpedo_total
    assert not game._task_candidate_ras()


def test_emcon_radar_left_on_fails_and_silence_is_rewarded():
    game = _game()
    game.surface_radar_on = game.air_radar_on = True
    task = game._offer_task("emcon")
    game.accept_task(task["id"])
    _slow(game, config.TASK_EMCON_GRACE_S + 1.0)
    assert task["state"] == "failed"
    game = _game(4103)
    game.surface_radar_on = game.air_radar_on = True
    task = game._offer_task("emcon")
    game.accept_task(task["id"])
    game.surface_radar_on = game.air_radar_on = False
    _slow(game, task["deadline_t"] - game.sim_t + 10.0, dt=5.0)
    assert task["state"] == "done"


def test_board_schema_is_exact_and_bounded():
    game = _game()
    for kind in ("sar", "datum", "emcon"):
        game._offer_task(kind)
    state = game.tasking.serialize()
    assert TaskBoard.valid_state(state)
    assert TaskBoard.restore(state).serialize() == state
    broken = copy.deepcopy(state)
    broken["tasks"][0]["extra"] = 1
    assert not TaskBoard.valid_state(broken)
    broken = copy.deepcopy(state)
    broken["tasks"][0]["true_x"] = None
    broken["tasks"][0]["true_y"] = None
    assert not valid_task(broken["tasks"][0])        # a raft needs its position
    broken = copy.deepcopy(state)
    broken["tasks"][1]["state"] = "done"
    assert not TaskBoard.valid_state(broken)          # closed tasks have ended
    broken = copy.deepcopy(state)
    broken["tasks"][0]["x"] = float("nan")
    assert not TaskBoard.valid_state(broken)
    with pytest.raises(ValueError):
        TaskBoard.restore({"version": 2})


def test_save_load_continues_a_running_task_identically():
    game = _game()
    task = game._offer_task("sar")
    game.accept_task(task["id"])
    _slow(game, 30.0)
    document = json.loads(json.dumps(game.save_state()))
    other = _game()
    assert other._load_save_data(document)
    for runner in (game, other):
        _slow(runner, 120.0)
    assert game.tasking.serialize() == other.tasking.serialize()
    broken = copy.deepcopy(document)
    del broken["tasking"]
    assert not other._load_save_data(broken)


def test_save_rejects_a_task_whose_ship_is_missing():
    game = _game()
    game.ship.fuel_kg = 0.5 * game.ship.fuel_capacity_kg
    task = game._offer_task("ras")
    document = json.loads(json.dumps(game.save_state()))
    document["civilians"] = [row for row in document["civilians"]
                             if row["id"] != task["target_id"]]
    assert not game._load_save_data(document)


def test_remote_radio_projection_carries_reports_not_truth():
    game = _game()
    task = game._offer_task("sar")
    payload = projections._radio(game, [], {})
    (row,) = payload["tasks"]
    assert row["id"] == task["id"] and row["can_answer"] is True
    assert (row["x"], row["y"]) == (task["x"], task["y"])
    text = json.dumps(payload)
    assert str(task["true_x"]) not in text and "true_x" not in text
    assert math.isfinite(row["bearing"]) and row["respond_s"] > 0.0
