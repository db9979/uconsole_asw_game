"""Scenarios 11 to 20: ten more missions, six for the frigate and four for the boat."""

import copy
import json
import math
import sys
from dataclasses import replace
from pathlib import Path

from src.core import boat_debrief, boat_missions, config, mission_modes
from src.core.game import Game
from src.core.i18n import localize
from src.ui import layout, map_view, uboot_view

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_boat_missions import _boat_game, _reason  # noqa: E402

FRIGATE = {"s11_geleitschutz": ("convoy_attack", 10800), "s12_datum": ("datum", 7200),
           "s13_fuehlung": ("trail", 7200), "s14_hafenschutz": ("swimmers", 21600),
           "s15_versorgung": ("ras", 7200), "s16_seenot": ("rescue", 7200)}
BOAT = {"s17_duell": ("duel", 10800), "s18_heimkehr": ("homecoming", 18000),
        "s19_abholung": ("pickup", 21600), "s20_lauschposten": ("elint", 14400)}


def _game(scenario, seed=61, short=False):
    game = Game(seed=seed, start_menu=False, audio_enabled=False, language="en")
    if short:
        game.start_length = "short"
    assert game.start_new_game(scenario, "fixed", seed=seed)
    return game


def _tick(game, steps=6):
    """Past one mission stage (it runs every half second)."""
    for _ in range(steps):
        game._update_sim(0.1)


def _end(game):
    game._check_mission_end()
    return game.mission_result, _reason(game)


def test_both_sides_now_have_ten_scenarios():
    assert len(config.scenarios_for_side("frigate")) == 10
    assert len(config.scenarios_for_side("uboot")) == 10
    for key, (kind, limit) in {**FRIGATE, **BOAT}.items():
        assert config.SCENARIOS[key].get("boat", False) is (key in BOAT)
        assert boat_missions.scenario_mode(key) == kind
        game = _game(key)
        assert boat_missions.mode(game) == kind and game.mission.time_limit_s == limit
        short = _game(key, short=True)
        assert short.short_mission and short.mission.time_limit_s <= 3600


def test_the_start_is_the_same_for_the_same_seed():
    for key in ("s12_datum", "s15_versorgung", "s16_seenot", "s18_heimkehr"):
        first, second = _game(key, seed=7), _game(key, seed=7)
        assert (first.ship.x, first.ship.y, first.ship.course) == (
            second.ship.x, second.ship.y, second.ship.course)
        one, two = boat_missions.target_sub(first), boat_missions.target_sub(second)
        assert (one.x, one.y, one.course) == (two.x, two.y, two.course)
        assert not first.world.on_land(first.ship.x, first.ship.y)
        assert not first.world.on_land(one.x, one.y)


def test_the_burning_datum_is_reported_and_the_boat_wins_by_slipping_out():
    game = _game("s12_datum")
    wreck = game.mission_entity("datum-1")
    sub = boat_missions.target_sub(game)
    cx, cy = mission_modes.centre(game.world, game.scenario_key)
    assert wreck is not None and wreck.damage > 0.0
    assert math.hypot(sub.x - cx, sub.y - cy) <= config.DATUM_BOAT_NM + 0.5
    assert math.hypot(game.ship.x - cx, game.ship.y - cy) > config.DATUM_ESCAPE_NM
    assert boat_missions.guard_area(game)["label"] == "map.guard.datum"
    assert "datum" in localize(game.mission_objective_display())
    sub.x = cx + mission_modes.datum_radius(game) + 0.5
    sub.y = cy
    assert _end(game) == ("VERLOREN", "end.reason.datum_escaped")
    game = _game("s12_datum")
    game.mission_time = game.mission.time_limit_s
    assert _end(game) == ("VERLOREN", "end.reason.datum_time")
    game = _game("s12_datum")
    boat_missions.target_sub(game).sunk = True
    assert _end(game)[0] == "SIEG"


def test_trailing_is_weapons_tight_and_counted_from_the_sonar_picture():
    game = _game("s13_fuehlung")
    sub = boat_missions.target_sub(game)
    _tick(game)
    assert game.weapons_tight() and sub.mission_peace
    assert sub.fire_readiness() == "not_ready"
    contact = next(iter(game.sonar.contacts.values()), None)
    if contact is not None:
        assert game.launch_torpedo_at(contact, 100.0) == "roe_blocked"
    progress = game.mission_progress
    progress["count_s"] = mission_modes.trail_goal_s(game)
    assert _end(game) == ("SIEG", "end.reason.trail_held")
    game = _game("s13_fuehlung")
    game.mission_progress["gap_s"] = mission_modes.trail_lost_s(game)
    assert _end(game) == ("VERLOREN", "end.reason.trail_lost")
    game = _game("s13_fuehlung")
    game.mission_time = game.mission.time_limit_s
    assert _end(game) == ("VERLOREN", "end.reason.trail_short")
    assert not _game("s1_patrouille").weapons_tight()


def test_the_trail_counter_runs_only_while_the_contact_is_fresh():
    game = _game("s13_fuehlung")
    sub = boat_missions.target_sub(game)
    game.sonar.contacts.pop(sub.id, None)
    mission_modes.update(game, "trail", 5.0)
    assert game.mission_progress["gap_s"] == 5.0 and game.mission_progress["count_s"] == 0.0


def test_replenishment_runs_on_the_task_board_and_ends_with_the_tanker():
    game = _game("s15_versorgung")
    tanker = mission_modes.supply(game)
    assert tanker is not None and tanker.side == "friendly"
    assert game.ship.fuel_kg <= config.RAS_FUEL_START * game.ship.fuel_capacity_kg + 1.0
    _tick(game)
    tasks = mission_modes.mission_tasks(game, "ras")
    assert len(tasks) == 1 and tasks[0]["state"] == "active"
    assert tasks[0]["target_id"] == tanker.id and game.tasking.next_offer_t is None
    assert "0 %" in localize(game.mission_objective_display())
    tasks[0]["state"] = "done"
    assert _end(game) == ("SIEG", "end.reason.ras_done")
    game = _game("s15_versorgung")
    _tick(game)
    mission_modes.supply(game).sunk = True
    assert _end(game) == ("VERLOREN", "end.reason.ras_tanker_sunk")
    game = _game("s15_versorgung")
    game.mission_time = game.mission.time_limit_s
    assert _end(game) == ("VERLOREN", "end.reason.ras_time")


def test_the_rescue_needs_both_rafts_even_after_the_boat_is_sunk():
    game = _game("s16_seenot")
    _tick(game)
    tasks = mission_modes.mission_tasks(game, "sar")
    assert [task["name"] for task in tasks] == list(mission_modes.RESCUE_NAMES)
    assert all(task["state"] == "active" for task in tasks)
    boat_missions.target_sub(game).sunk = True
    game._check_mission_end()
    assert game.mission_result is None
    for task in tasks:
        task["state"] = "done"
    assert _end(game) == ("SIEG", "end.reason.rescue_done")
    game = _game("s16_seenot")
    _tick(game)
    game.mission_time = game.mission.time_limit_s
    assert _end(game) == ("VERLOREN", "end.reason.rescue_lost")


def test_the_duel_is_won_by_the_frigate_holding_out():
    game, boat = _boat_game("s17_duell")
    assert "frigate" in localize(boat_missions.objective(game, boat)).lower()
    game.mission_time = game.mission.time_limit_s
    assert _end(game) == ("SIEG", "end.reason.duel_survived")


def test_the_damaged_boat_wins_by_reaching_home():
    game, boat = _boat_game("s18_heimkehr")
    sub = boat.sub
    assert sub.damage >= config.HOMECOMING_DAMAGE
    home = boat_missions.goal(game)
    assert home is not None and not game.world.on_land(home["x"], home["y"])
    assert localize(boat_missions.objective(game, boat))
    sub.x, sub.y = home["x"], home["y"]
    assert _end(game) == ("VERLOREN", "end.reason.boat_home")
    assert boat_debrief.outcome(game, boat) == "home"


def test_agents_board_after_the_hold_and_the_boat_then_runs_for_deep_water():
    game, boat = _boat_game("s19_abholung")
    sub = boat.sub
    zone = boat_missions.zone(game)
    sub.x, sub.y = zone["x"], zone["y"]
    sub.depth, sub.speed = 15.0, 0.5
    for _ in range(int(config.PICKUP_HOLD_S) + 1):
        mission_modes.update(game, "pickup", 1.0)
    assert game.mission_progress["phase"] == 1
    goal = boat_missions.goal(game)
    assert goal != zone and math.hypot(goal["x"] - zone["x"], goal["y"] - zone["y"]) > 5.0
    sub.x, sub.y = goal["x"], goal["y"]
    assert _end(game) == ("VERLOREN", "end.reason.agents_escaped")
    assert boat_debrief.outcome(game, boat) == "picked_up"
    game, boat = _boat_game("s19_abholung")
    game.mission_time = game.mission.time_limit_s
    assert _end(game) == ("SIEG", "end.reason.agents_denied")


def test_the_listening_post_records_radars_and_wins_with_its_report():
    game, boat = _boat_game("s20_lauschposten")
    sub = boat.sub
    sub.x, sub.y = game.ship.x + 5.0, game.ship.y
    sub.depth = 12.0
    boat.orders.mast = True
    game.surface_radar_on = game.air_radar_on = True
    mission_modes.elint_report(game)
    assert game.mission_result is None            # nothing recorded yet
    for _ in range(int(mission_modes.elint_goal_s(game)) + 1):
        mission_modes.update(game, "elint", 1.0)
    assert mission_modes.elint_complete(game) and mission_modes.elint_kinds(game) == 2
    boat_missions.report_sent(game, boat)
    assert game.mission_result == "VERLOREN" and _reason(game) == "end.reason.elint_reported"
    assert boat_debrief.outcome(game, boat) == "elint"


def test_the_mission_progress_is_saved_and_checked():
    game = _game("s20_lauschposten")
    game.mission_progress.update(count_s=12.5, flags=3, phase=1)
    data = json.loads(json.dumps(game.save_state()))
    assert data["mission_progress"]["count_s"] == 12.5
    assert game._load_save_data(copy.deepcopy(data))
    assert game.mission_progress["flags"] == 3 and game.mission_progress["phase"] == 1
    before = game.save_state()
    for field, bad in (("count_s", -1.0), ("count_s", 3), ("flags", 16), ("phase", 2),
                       ("gap_s", float("inf")), ("extra", 0.0)):
        broken = copy.deepcopy(data)
        broken["mission_progress"][field] = bad
        assert not game._load_save_data(broken), field
    assert game.save_state() == before


def test_every_new_scenario_draws_and_runs_on_both_sides_in_both_languages():
    for key in (*FRIGATE, *BOAT):
        game, boat = _boat_game(key)
        for language in ("en", "de"):
            game.preferences = replace(game.preferences, language=language)
            layout.configure_for(game)
            uboot_view.draw_chart(game, boat)
            assert localize(game.mission_objective_display())
            assert localize(game.mission_name_display())
        frigate = _game(key)
        for language in ("en", "de"):
            frigate.preferences = replace(frigate.preferences, language=language)
            layout.configure_for(frigate)
            map_view.draw_map_view(frigate)
            assert localize(frigate.mission_objective_display())
        for _ in range(20):
            game._update_sim(0.25)
            frigate._update_sim(0.25)
        assert game.mission_result is None and frigate.mission_result is None, key
