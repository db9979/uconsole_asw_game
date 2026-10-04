"""Incidents at sea: drift nets, weather fronts, merchants without AIS and
whales, on a deterministic schedule, saved, and passed on to the boat."""

import copy
import json
import math

import pytest

from src.core import config
from src.core.game import Game
from src.core.incidents import IncidentBoard, segment_distance_nm, valid_item
from src.sonar.sonar import TowState


def _game(seed=5101):
    game = Game(seed=seed, start_menu=False, audio_enabled=False)
    return game


def _texts(game):
    return [str(game.tr(row.text) if hasattr(game, "tr") else row.text)
            for row in game.feed.entries]


def test_schedule_is_deterministic_and_bounded():
    first, second = _game(5102), _game(5102)
    assert first.incidents.enabled
    assert first.incidents.next_t == second.incidents.next_t
    lo, hi = config.INCIDENT_FIRST_S
    assert lo <= first.incidents.next_t <= hi
    for game in (first, second):
        game.incidents.next_t = game.sim_t
        game._update_incidents(0.5)
    # Entity IDs are process-global counters; everything else must agree.
    strip = [dict(row, target_id=None) for row in first.incidents.serialize()["items"]]
    assert strip == [dict(row, target_id=None)
                     for row in second.incidents.serialize()["items"]]
    assert first.incidents.count == 1
    # Never more than INCIDENT_MAX in a mission.
    for _ in range(10):
        first.incidents.next_t = first.sim_t
        first._update_incidents(0.5)
    assert first.incidents.count == config.INCIDENT_MAX


def test_drift_net_across_the_track_fouls_the_towed_array_and_costs_score():
    game = _game()
    item = game._start_incident("net")
    assert item is not None and item["kind"] == "net"
    # Across the track ahead, plotted on the chart.
    cx, cy = (item["x"] + item["x2"]) / 2.0, (item["y"] + item["y2"]) / 2.0
    ahead = math.hypot(cx - game.ship.x, cy - game.ship.y)
    assert config.INCIDENT_NET_RANGE_NM[0] - 0.1 <= ahead <= config.INCIDENT_NET_RANGE_NM[1] + 0.1
    assert abs(math.hypot(item["x2"] - item["x"], item["y2"] - item["y"])
               - config.INCIDENT_NET_LENGTH_NM) < 1e-9
    assert any(row["id"] == item["plot_id"] and row["kind"] == "ruler"
               for row in game.plot.objects)
    game.sonar.tow_state, game.sonar.tow_payout = TowState.STREAMED, 1.0
    score = game.score
    game.ship.x, game.ship.y = cx, cy
    game._update_incidents(0.5)
    assert item["fouled"] == [0]
    assert game.score == score - config.SCORE_NET_TORN
    assert game.sonar.tow_state == TowState.RETRIEVING
    # Once only.
    game._update_incidents(0.5)
    assert game.score == score - config.SCORE_NET_TORN
    # The fishing boat hauls it in: off the chart.
    plot_id = item["plot_id"]
    game.sim_t = item["end_t"]
    game._update_incidents(0.5)
    assert not item["active"] and item["plot_id"] is None
    assert not any(row["id"] == plot_id for row in game.plot.objects)


def test_a_shallow_submarine_fouls_the_net_and_a_deep_one_passes_under():
    game = _game(5103)
    item = game._start_incident("net")
    cx, cy = (item["x"] + item["x2"]) / 2.0, (item["y"] + item["y2"]) / 2.0
    deep, shallow = game.subs[0], game.subs[-1] if len(game.subs) > 1 else None
    deep.x, deep.y, deep.depth = cx, cy, config.INCIDENT_NET_DEPTH_M + 30.0
    game._update_incidents(0.5)
    assert deep.id not in item["fouled"]
    deep.depth = 12.0
    deep.transient_left = 0.0
    game._update_incidents(0.5)
    assert deep.id in item["fouled"]
    assert deep.transient_left == config.INCIDENT_NET_TRANSIENT_S
    del shallow


def test_weather_front_is_warned_holds_and_passes():
    game = _game(5104)
    game.world.set_weather_override(None)
    item = game._start_incident("front")
    assert item["weather"] in ("rain", "storm", "fog")
    assert item["start_t"] == game.sim_t + config.INCIDENT_FRONT_LEAD_S
    game._update_incidents(0.5)
    assert game.world.weather_override is None
    game.sim_t = item["start_t"]
    game._update_incidents(0.5)
    assert game.world.weather_override == item["weather"]
    game.sim_t = item["end_t"]
    game._update_incidents(0.5)
    assert game.world.weather_override is None and not item["active"]
    # No second front while one is on, nor over an authored weather.
    game.world.set_weather_override("fog")
    assert not game._incident_candidate_front()


def test_merchant_without_ais_is_spawned_and_offered_for_identification():
    game = _game(5105)
    before = len(game.civilians)
    item = game._start_incident("dark")
    assert len(game.civilians) == before + 1
    ship = game.civilians[-1]
    assert ship.id == item["target_id"] and not ship.ais_transmitting
    assert ship.doctrine == "dark_transit"
    offered = [task for task in game.tasking.tasks
               if task["kind"] == "identify" and task["target_id"] == ship.id]
    assert len(offered) == 1


def test_whales_come_as_a_pod():
    game = _game(5106)
    before = len(game.animals)
    item = game._start_incident("whales")
    added = game.animals[before:]
    low, high = config.INCIDENT_WHALES_COUNT
    assert low <= len(added) <= high
    assert all(animal.kind == "whale" or getattr(animal, "profile_key", "whale") == "whale"
               for animal in added)
    assert all(math.hypot(a.x - item["x"], a.y - item["y"]) < 1.0 for a in added)


def test_incidents_stop_adding_ships_and_whales_to_a_full_sea():
    game = _game(5107)
    while len(game.civilians) < config.INCIDENT_CIVILIANS_MAX:
        game.civilians.append(game.civilians[0])
    while len(game.animals) < config.INCIDENT_ANIMALS_MAX:
        game.animals.append(game.animals[0] if game.animals else game.civilians[0])
    ships, animals = len(game.civilians), len(game.animals)
    assert game._start_incident("dark") is None
    assert game._start_incident("whales") is None
    assert (len(game.civilians), len(game.animals)) == (ships, animals)


def test_incidents_round_trip_and_bad_rows_are_rejected():
    game = _game(5107)
    game.world.set_weather_override(None)
    game._start_incident("net")
    game._start_incident("front")
    game._start_incident("dark")
    state = json.loads(json.dumps(game.save_state()))
    assert IncidentBoard.valid_state(state["incidents"])
    twin = _game(1)
    assert twin._load_save_data(copy.deepcopy(state))
    assert twin.incidents.serialize() == game.incidents.serialize()
    assert twin.save_state()["incidents"] == state["incidents"]
    for field, value in (("kind", "mine"), ("x2", None), ("weather", "hail"),
                         ("fouled", [3, 1]), ("active", 1), ("announced_t", 1e12)):
        bad = copy.deepcopy(state)
        bad["incidents"]["items"][0][field] = value
        assert not twin._load_save_data(bad), field
    late = copy.deepcopy(state)
    late["incidents"]["items"][0]["announced_t"] = state["sim_t"] + 10.0
    late["incidents"]["items"][0]["start_t"] = late["incidents"]["items"][0]["end_t"] = \
        state["sim_t"] + 10.0
    assert not twin._load_save_data(late)


def test_no_incidents_in_custom_missions_or_lessons():
    assert not IncidentBoard(None).enabled
    game = _game(5108)
    game.training = object()
    game.incidents.next_t = 0.0
    game._update_incidents(0.5)
    assert game.incidents.count == 0


def test_the_crewed_boat_hears_of_the_net_in_its_broadcast():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from test_opfor_sub import _crewed  # noqa: E402
    game, _server, _bridge = _crewed(seed=77)
    boat = game.opfor
    item = game._start_incident("net")
    assert item is not None
    game.incidents_to_boat(boat, item["announced_t"] - 1.0)
    assert not item["boat_told"]
    game.incidents_to_boat(boat, item["announced_t"])
    assert item["boat_told"]
    assert any(row["kind"] == "ruler" for row in boat.plot.objects)
    count = len(boat.plot.objects)
    game.incidents_to_boat(boat, item["announced_t"] + 1.0)
    assert len(boat.plot.objects) == count


def test_geometry_and_row_validation():
    assert segment_distance_nm(0.0, 1.0, -1.0, 0.0, 1.0, 0.0) == pytest.approx(1.0)
    assert segment_distance_nm(3.0, 0.0, -1.0, 0.0, 1.0, 0.0) == pytest.approx(2.0)
    row = dict(id=1, kind="whales", announced_t=0.0, start_t=0.0, end_t=10.0, active=True,
               x=1.0, y=2.0, x2=None, y2=None, weather=None, target_id=None,
               plot_id=None, boat_told=False, fouled=[])
    assert valid_item(row)
    assert not valid_item(dict(row, fouled=[5]))
    assert not valid_item(dict(row, end_t=-1.0))


def test_the_ai_hunter_steers_round_a_reported_net():
    from src.core import hunter
    game = _game(5109)
    game.ship.course = game.ship.target_course = 0.0
    game.ship.speed = 10.0
    x, y = game.ship.x, game.ship.y
    item = game._start_incident("net")
    item.update(x=x - 1.0, y=y - 0.6, x2=x + 1.0, y2=y - 0.6)
    assert game.net_ahead(x, y, x, y - 2.0)
    assert not game.net_ahead(x, y, x - 2.0, y)
    hunter._steer(game, 0.0, 10.0)
    assert abs(((game.ship.target_course + 180.0) % 360.0) - 180.0) >= 30.0
