"""Scenarios 8 to 10: strait blockade, combat swimmers and supply ship escort."""

import copy
import json
import math
import sys
from dataclasses import replace
from pathlib import Path

import pygame

from src.core import boat_ai, boat_debrief, boat_missions, config, hunter, mission_geo
from src.core.game import Game
from src.core.i18n import localize
from src.ui import layout, map_view, uboot_view
from src.world.coastline import Coastline
from src.world.world import World

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_boat_missions import _boat_game, _quiet_convoy, _reason, _shot_at  # noqa: E402


def _frigate_game(scenario, seed=61, world="fixed"):
    game = Game(seed=seed, start_menu=False, audio_enabled=False, language="en")
    assert game.start_new_game(scenario, world, seed=seed)
    return game


def test_three_new_boat_scenarios_are_listed_and_keyed():
    assert config.scenarios_for_side("uboot")[3:6] == ("s8_meerenge", "s9_kampfschwimmer", "s10_versorger")
    for key, kind, limit in (("s8_meerenge", "strait", 14400),
                             ("s9_kampfschwimmer", "swimmers", 21600),
                             ("s10_versorger", "escort", 10800)):
        assert config.SCENARIOS[key]["boat"] is True
        assert boat_missions.scenario_mode(key) == kind
        game = _frigate_game(key)
        assert boat_missions.mode(game) == kind and game.mission.time_limit_s == limit
    # Key 6 picks the sixth and last scenario of the submarine's menu list.
    game = Game(seed=5, start_menu=False, audio_enabled=False)
    game.local_side = "uboot"
    game.in_menu, game.main_menu, game.menu_screen = True, False, "scenario"
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_6, mod=0, unicode="6"))
    assert config.SCENARIO_ORDER[game.menu_sel] == "s10_versorger"


def test_the_strait_is_found_on_real_geography_and_the_same_after_a_load():
    world = World(seed=1, coast=Coastline.load())
    gate = mission_geo.strait(world, (250.0, 180.0))
    assert gate["natural"] and config.STRAIT_MIN_NM / 2.0 <= gate["half_nm"] <= config.STRAIT_MAX_NM
    # Both sides of the gate end at a wall; the channel runs open along it.
    for side in (90.0, -90.0):
        assert mission_geo._ray_nm(world, gate["x"], gate["y"], gate["axis"] + side,
                                   gate["half_nm"] + 1.0) is not None
    for sign in (0.0, 180.0):
        assert mission_geo.walk(world, gate["x"], gate["y"], gate["axis"] + sign, (10.0,))
    game = _frigate_game("s8_meerenge")
    assert math.hypot(game.ship.x - gate["x"], game.ship.y - gate["y"]) < 1.0
    sub = boat_missions.target_sub(game)
    point = boat_missions.goal(game)
    before, _ = mission_geo.along((sub.x, sub.y), gate)
    after, _ = mission_geo.along((point["x"], point["y"]), gate)
    assert before * after < 0.0 and abs(before) >= config.STRAIT_ENTRY_NM * 0.5
    assert len([key for key in game.mission_units if key.startswith("traffic-")]) == \
        config.STRAIT_TRAFFIC
    data = json.loads(json.dumps(game.save_state()))
    game._boat_goal_cache = None
    game.world._mission_geo_cache = {}
    assert game._load_save_data(data)
    assert boat_missions.goal(game) == point
    # A world without any narrow passage gets a declared barrier line.
    assert mission_geo._open_gate(world, (250.0, 250.0))["natural"] is False


def test_passing_the_strait_wins_for_the_boat_and_holding_it_for_the_frigate():
    game, boat = _boat_game("s8_meerenge")
    point = boat_missions.goal(game)
    text = localize(boat_missions.objective(game, boat))
    assert text.startswith("Pass the strait to the goal area: bearing ")
    boat.sub.x, boat.sub.y = point["x"], point["y"]
    game._check_mission_end()
    assert game.mission_result == "VERLOREN" and _reason(game) == "end.reason.boat_passed_strait"
    assert boat_debrief.outcome(game, boat) == "passed"
    assert uboot_view.end_text(game, boat) == "uboot.end.passed"
    game, boat = _boat_game("s8_meerenge")
    game.mission_time = game.mission.time_limit_s
    game._check_mission_end()
    assert game.mission_result == "SIEG" and _reason(game) == "end.reason.strait_held"


def test_the_ai_boat_hides_under_a_merchant_in_the_strait():
    game = _frigate_game("s8_meerenge")
    sub = boat_missions.target_sub(game)
    point = boat_missions.goal(game)
    heading = boat_ai._bearing(sub.x, sub.y, point["x"], point["y"])
    ship = game.civilians[0]
    ship.x, ship.y = sub.x + 1.0, sub.y
    ship.course, ship.speed = heading, 8.0
    assert boat_ai.shadow_ship(game, sub, heading) is ship
    course, speed, _depth = boat_ai.orders(game, sub)
    assert speed >= ship.speed
    # Hunted, it transits on its own again.
    sub.memory["last_ping_age"] = 0.0
    assert boat_ai.orders(game, sub)[1] == config.BOAT_AI_CREEP_KN


def test_the_frigate_patrols_its_gate_and_its_coast_section():
    game = _frigate_game("s8_meerenge")
    area = boat_missions.guard_area(game)
    assert area["kind"] == "gate"
    course, speed = hunter.guard_course(game)
    assert speed == hunter.SEARCH_KN
    game = _frigate_game("s9_kampfschwimmer")
    area = boat_missions.guard_area(game)
    zone = boat_missions.zone(game)
    assert area["kind"] == "circle"
    assert math.hypot(area["x"] - zone["x"], area["y"] - zone["y"]) < area["radius_nm"]
    game.ship.x += 40.0
    assert hunter.guard_course(game)[1] == hunter.TRANSIT_KN
    for language in ("en", "de"):
        game.preferences = replace(game.preferences, language=language)
        layout.configure_for(game)
        map_view.draw_map_view(game)


def test_swimmers_land_only_after_ten_quiet_minutes_in_the_zone():
    game, boat = _boat_game("s9_kampfschwimmer")
    zone = boat_missions.zone(game)
    sub = boat.sub
    assert math.hypot(sub.x - zone["x"], sub.y - zone["y"]) >= config.SWIMMER_APPROACH_NM * 0.4
    assert not game.world.on_land(zone["x"], zone["y"])
    sub.x, sub.y = zone["x"], zone["y"]
    sub.depth, sub.speed = 15.0, 0.5
    for _ in range(int(config.SWIMMER_HOLD_S / 2) - 1):
        boat_missions.update(game, 1.0)
    assert 0.0 < game.swimmer_hold_s < config.SWIMMER_HOLD_S
    assert "Swimmers leaving the lock" in localize(boat_missions.objective(game, boat))
    # Too fast: the lock-out starts over.
    sub.speed = config.SWIMMER_SPEED_KN + 1.0
    boat_missions.update(game, 1.0)
    assert game.swimmer_hold_s == 0.0
    sub.speed = 0.5
    for _ in range(int(config.SWIMMER_HOLD_S)):
        boat_missions.update(game, 1.0)
    game._check_mission_end()
    assert game.mission_result == "VERLOREN" and _reason(game) == "end.reason.swimmers_landed"
    assert boat_debrief.outcome(game, boat) == "landed"


def test_the_swimmers_lock_out_is_saved_and_checked():
    game, boat = _boat_game("s9_kampfschwimmer")
    game.swimmer_hold_s = 123.5
    data = json.loads(json.dumps(game.save_state()))
    assert data["swimmer_hold_s"] == 123.5
    assert game._load_save_data(copy.deepcopy(data)) and game.swimmer_hold_s == 123.5
    before = game.save_state()
    for bad in (-1.0, config.SWIMMER_HOLD_S + 1.0, 5, "x", None):
        broken = copy.deepcopy(data)
        broken["swimmer_hold_s"] = bad
        assert not game._load_save_data(broken)
    assert game.save_state() == before


def test_the_ai_boat_comes_up_and_stops_in_the_zone():
    game = _frigate_game("s9_kampfschwimmer")
    sub = boat_missions.target_sub(game)
    zone = boat_missions.zone(game)
    _course, speed, depth = boat_ai.orders(game, sub)
    assert depth > config.SWIMMER_DEPTH_M and speed > 0.0
    sub.x, sub.y = zone["x"], zone["y"]
    _course, speed, depth = boat_ai.orders(game, sub)
    assert speed == 0.0 and depth <= config.SWIMMER_DEPTH_M


def test_the_supply_ship_zigzags_and_one_hit_decides_the_escort():
    game, boat = _boat_game("s10_versorger")
    ship = boat_missions.supply(game)
    assert ship.side == "friendly" and ship.profile.key == config.TASK_RAS_PROFILE
    assert boat_missions.convoy(game) == [ship]
    base = boat_missions.escort_base_course(game.world, game.scenario_key)
    courses = set()
    for leg in range(4):
        game.sim_t = leg * config.ESCORT_ZIGZAG_LEG_S + 1.0
        course = boat_missions.zigzag_course(game)
        off = abs(config.angle_diff_deg(course, base))
        assert config.ESCORT_ZIGZAG_DEG[0] - 1e-6 <= off <= config.ESCORT_ZIGZAG_DEG[1] + 1e-6
        courses.add(round(config.angle_diff_deg(course, base) > 0))
    assert courses == {0, 1}                     # both sides of the base course
    assert "supply ship" in localize(boat_missions.objective(game, boat))
    _quiet_convoy(game)
    torpedo = _shot_at(game, ship, platform_id=boat.sub.id)
    assert torpedo.state == "STRUCK" and ship.sunk
    game._check_mission_end()
    assert game.mission_result == "VERLOREN" and _reason(game) == "end.reason.supply_sunk"
    assert boat_debrief.outcome(game, boat) == "supply_sunk"
    game, _boat = _boat_game("s10_versorger")
    game.mission_time = game.mission.time_limit_s
    game._check_mission_end()
    assert game.mission_result == "SIEG" and _reason(game) == "end.reason.supply_protected"


def test_new_missions_draw_on_both_sides_in_both_languages():
    for key in ("s8_meerenge", "s9_kampfschwimmer", "s10_versorger"):
        game, boat = _boat_game(key)
        for language in ("en", "de"):
            game.preferences = replace(game.preferences, language=language)
            layout.configure_for(game)
            uboot_view.draw_chart(game, boat)
            assert localize(game.mission_objective_display())
            assert localize(game.mission_name_display())
        for _ in range(20):
            game._update_sim(0.25)
        assert game.mission_result is None
