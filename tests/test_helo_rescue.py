"""The helicopter's rescue hoist and life rafts on radar (1.3.196, save v52)."""

import copy
import math

from src.core import config, mission_modes, save_migrate
from src.core.game import Game
from src.core.game_rescue import persons_left
from src.core.tasking import TaskBoard


def _game(seed=4101):
    game = Game(seed=seed, start_menu=False, audio_enabled=False)
    game.tasking.next_offer_t = 1e9     # no scheduled offers in these tests
    _weather(game, True)
    return game


def _weather(game, winch_ok):
    real = type(game).helicopter_weather.__get__(game)
    game.helicopter_weather = lambda: dict(real(), dipping_safe=winch_ok)


def _sea(game, state):
    weather = game.world.weather_values
    game.world.weather_values = lambda: dict(weather(), sea_state=state)


def _raft(game, persons=None):
    task = game._offer_task("sar")
    assert game.accept_task(task["id"]) is True
    if persons is not None:
        task["persons"] = persons
    # Keep the frigate away so only the helicopter recovers.
    game.ship.x, game.ship.y = task["true_x"] + 5.0, task["true_y"]
    return task


def _fly(game, seconds, dt=0.5):
    for _ in range(int(seconds / dt)):
        game.sim_t += dt
        game.helo.update(dt, game.ship, game.world)
        game._update_tasking(dt)


def _airborne_near(game, task, offset_nm=0.05):
    game.helo.launch(game.ship)
    game.helo.x, game.helo.y = task["true_x"] + offset_nm, task["true_y"]
    game.helo.set_waypoint(game.helo.x, game.helo.y)


def test_hoist_needs_an_airborne_helicopter_near_a_raft():
    game = _game()
    task = _raft(game)
    assert game.order_helicopter_hoist(True) == "not_airborne"
    game.helo.launch(game.ship)
    game.helo.x, game.helo.y = task["true_x"] + 1.0, task["true_y"]
    assert game.order_helicopter_hoist(True) == "no_raft"
    game.helo.x = task["true_x"] + 0.5 * config.TASK_SAR_HOIST_ORDER_NM
    game.helo.dip_state = "DEPLOYED"
    assert game.order_helicopter_hoist(True) == "dipping"
    game.helo.dip_state = "STOWED"
    assert game.order_helicopter_hoist(True) is True and game.helo.hoist
    # The winch is busy: no dipping while it runs.
    assert game.helo.set_dipping(True, game.world) is False


def test_hoist_moves_over_the_raft_lifts_one_by_one_and_stops_when_empty():
    game = _game()
    task = _raft(game, persons=3)
    _airborne_near(game, task)
    assert game.order_helicopter_hoist(True) is True
    status = game.helo_rescue_status()
    assert status["phase"] == "approach" and status["aboard"] == 0
    _fly(game, 30.0)
    gap = math.hypot(game.helo.x - task["true_x"], game.helo.y - task["true_y"])
    assert gap <= config.TASK_SAR_HOIST_OVERHEAD_NM
    assert game.helo_rescue_status()["phase"] == "lifting"
    _fly(game, 3 * config.TASK_SAR_HELO_S_PER_PERSON + 5.0)
    assert task["aboard"] == 3 and persons_left(task) == 0
    assert not game.helo.hoist
    # Out of the water, but not rescued until the cabin is on deck.
    assert task["state"] == "active"
    assert game.helo_rescue_status()["phase"] == "return"


def test_survivors_count_once_the_helicopter_is_back_on_deck():
    game = _game()
    task = _raft(game, persons=2)
    _airborne_near(game, task, 0.0)
    game.order_helicopter_hoist(True)
    _fly(game, 2 * config.TASK_SAR_HELO_S_PER_PERSON + 5.0)
    assert task["aboard"] == 2
    score = game.score
    game.helo.state = "HANGAR"
    game.sim_t += 0.5
    game._update_tasking(0.5)
    assert task["aboard"] == 0 and task["state"] == "done"
    assert game.score == score + config.SCORE_TASK["sar"][0]
    assert game.helo_survivors() == 0


def test_cabin_capacity_stops_the_hoist():
    game = _game()
    task = _raft(game, persons=config.TASK_SAR_HELO_CAPACITY + 2)
    _airborne_near(game, task, 0.0)
    game.order_helicopter_hoist(True)
    _fly(game, (config.TASK_SAR_HELO_CAPACITY + 2) * config.TASK_SAR_HELO_S_PER_PERSON)
    assert game.helo_survivors() == config.TASK_SAR_HELO_CAPACITY
    assert persons_left(task) == 2 and not game.helo.hoist
    assert game.order_helicopter_hoist(True) == "full"


def test_no_lift_when_the_weather_forbids_the_winch():
    game = _game()
    task = _raft(game, persons=2)
    _weather(game, False)
    _airborne_near(game, task, 0.0)
    assert game.order_helicopter_hoist(True) is True
    _fly(game, 3 * config.TASK_SAR_HELO_S_PER_PERSON)
    assert task["aboard"] == 0 and game.helo_rescue_status()["phase"] == "weather"


def test_a_lost_helicopter_loses_its_survivors():
    game = _game()
    task = _raft(game, persons=1)
    _airborne_near(game, task, 0.0)
    game.order_helicopter_hoist(True)
    _fly(game, config.TASK_SAR_HELO_S_PER_PERSON + 2.0)
    assert task["aboard"] == 1
    game.helo.state = "VERLOREN"
    game.sim_t += 0.5
    game._update_tasking(0.5)
    assert task["state"] == "failed" and task["aboard"] == 0


def test_raft_is_a_small_radar_echo_that_places_the_search_circle():
    game = _game()
    task = _raft(game)
    _sea(game, 1)
    game.helo.launch(game.ship)
    game.helo.x, game.helo.y = task["true_x"] + 1.0, task["true_y"]
    assert task["radius_nm"] == config.TASK_SAR_RADIUS_NM
    for step in range(40):
        game.sim_t += config.MPA_RADAR_LOOK_S
        game._update_helo_radar(config.MPA_RADAR_LOOK_S)
        if task["radius_nm"] < config.TASK_SAR_RADIUS_NM:
            break
    assert task["radius_nm"] == 0.3 and not task["sighted"]
    assert math.hypot(task["x"] - task["true_x"], task["y"] - task["true_y"]) < 0.3


def test_raft_echo_drowns_in_a_high_sea():
    game = _game()
    task = _raft(game)
    _sea(game, 6)
    game.helo.launch(game.ship)
    game.helo.x, game.helo.y = task["true_x"] + 3.0, task["true_y"]
    for _ in range(40):
        game.sim_t += config.MPA_RADAR_LOOK_S
        game._update_helo_radar(config.MPA_RADAR_LOOK_S)
    assert task["radius_nm"] == config.TASK_SAR_RADIUS_NM


def test_hoist_state_round_trips_through_a_save():
    game = _game()
    task = _raft(game, persons=3)
    _airborne_near(game, task, 0.0)
    game.order_helicopter_hoist(True)
    _fly(game, config.TASK_SAR_HELO_S_PER_PERSON + 10.0)
    data, _text = game.checked_save_document()
    assert data["helo"]["hoist"] is True and 0 < data["helo"]["hoist_s"]
    assert data["tasking"]["version"] == 2
    assert data["tasking"]["tasks"][0]["aboard"] == 1
    other = _game()
    other.load_state(copy.deepcopy(data))
    assert other.helo.hoist and other.helo.hoist_s == game.helo.hoist_s
    assert other.helo_survivors() == 1
    assert TaskBoard.valid_state(data["tasking"])


def test_v51_documents_gain_an_idle_hoist_and_empty_cabins():
    doc = {"version": 51, "save_schema": "u-jagd-save-v51",
           "helo": {"prep_s": None},
           "tasking": {"version": 1, "tasks": [{"id": 1}]}}
    lifted = save_migrate.migrate(doc)
    assert lifted["version"] == save_migrate.SAVE_VERSION
    assert lifted["helo"]["hoist"] is False and lifted["helo"]["hoist_s"] == 0.0
    assert lifted["tasking"]["version"] == 2
    assert lifted["tasking"]["tasks"][0]["aboard"] == 0


def test_rescue_point_skips_rafts_already_emptied():
    game = Game(seed=7, start_menu=False, audio_enabled=False)
    game.start_new_game("s16_seenot", "fixed", seed=7)
    for _ in range(6):
        game._update_sim(0.1)
    rafts = mission_modes.mission_tasks(game, "sar")
    assert len(rafts) == 2
    assert mission_modes.rescue_point(game, flyer=True) is not None
    rafts[0]["progress"] = 1.0
    rafts[0]["aboard"] = rafts[0]["persons"]
    assert mission_modes.rescue_point(game, flyer=True) is None
    x, y = mission_modes.rescue_point(game)
    assert (x, y) == (rafts[1]["x"], rafts[1]["y"])


def test_remote_crew_orders_the_hoist_and_sees_the_rescue_panel():
    from src.commander import projections
    from src.commander.actions import _V2_ACTION_HANDLERS as HANDLERS
    from src.commander.v2.commands import V2_ACTION_REGISTRY as ACTIONS
    action = ACTIONS["helicopter_set_hoist"]
    assert "helicopter" in action.stations and action.validate_params({"enabled": True})
    assert not action.validate_params({"enabled": "yes"})
    game = _game()
    assert projections._helicopter(game, [], {}, {})["rescue"] is None
    task = _raft(game, persons=2)
    _airborne_near(game, task)
    view = projections._helicopter(game, [], {}, {})["rescue"]
    assert view["aboard"] == 0 and view["capacity"] == config.TASK_SAR_HELO_CAPACITY
    # Positions are the reported ones: no raft truth in the panel.
    assert view["raft"] == game._task_label(task)
    assert HANDLERS["helicopter_set_hoist"](game, {"enabled": True}, {}) is True
    assert projections._helicopter(game, [], {}, {})["rescue"]["hoist"] is True


def test_z_at_the_helicopter_station_toggles_the_hoist():
    import pygame
    from src.core.station import Station
    game = _game()
    task = _raft(game, persons=2)
    _airborne_near(game, task)
    game.station = Station.HELICOPTER
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_z, mod=0))
    assert game.helo.hoist
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_z, mod=0))
    assert not game.helo.hoist
