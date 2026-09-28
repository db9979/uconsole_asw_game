"""Boat missions: breakthrough and reconnaissance, decided from the boat's side."""

import json
from dataclasses import replace
import math
import sys
from pathlib import Path

from src.core import boat_debrief, boat_missions, config, opfor
from src.core.game import Game
from src.core.i18n import localize
from src.commander import projections
from src.sensors.platform import MAST_DEPTH_M
from src.sonar.platforms import OWNSHIP_TARGET_ID
from src.ui import layout, uboot_view

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))


def _boat_game(scenario, seed=61):
    game = Game(seed=seed, start_menu=False, audio_enabled=False, language="en")
    game.reset(seed, scenario)
    game.local_side = "uboot"
    game._update(0.05)
    assert game.opfor is not None
    return game, game.opfor


def _reason(game):
    return game.result_reason["__u_jagd_i18n__"]


def test_boat_scenarios_are_listed_with_their_modes():
    assert config.SCENARIO_ORDER[-3:] == ("s5_durchbruch", "s6_aufklaerung", "s7_geleitzug")
    game, _boat = _boat_game("s5_durchbruch")
    assert boat_missions.mode(game) == "breakthrough"
    assert game.mission.time_limit_s == 14400
    game, _boat = _boat_game("s6_aufklaerung")
    assert boat_missions.mode(game) == "recon"
    game, _boat = _boat_game("s1_patrouille")
    assert boat_missions.mode(game) is None and boat_missions.goal(game) is None


def test_the_breakthrough_goal_lies_beyond_the_frigate_on_water():
    game, boat = _boat_game("s5_durchbruch")
    point = boat_missions.goal(game)
    fx, fy = config.SCENARIOS["s5_durchbruch"]["ship_start"]
    sx, sy = boat.sub.start_pos
    assert not game.world.on_land(point["x"], point["y"])
    assert game.world.depth_m(point["x"], point["y"]) >= config.BOAT_GOAL_MIN_DEPTH_M
    # Farther from the boat's start than the frigate is.
    assert math.hypot(point["x"] - sx, point["y"] - sy) > math.hypot(fx - sx, fy - sy)
    assert boat_missions.goal(game) == point                  # stable
    # The same seed gives the same goal after a save and load.
    data = game.save_state()
    game._boat_goal_cache = None
    assert game._load_save_data(json.loads(json.dumps(data)))
    assert boat_missions.goal(game) == point


def test_reaching_the_goal_wins_the_breakthrough_for_the_boat():
    game, boat = _boat_game("s5_durchbruch")
    point = boat_missions.goal(game)
    game._check_mission_end()
    assert game.mission_result is None
    boat.sub.x, boat.sub.y = point["x"] + 1.0, point["y"]
    game._check_mission_end()
    assert game.mission_result == "VERLOREN"
    assert _reason(game) == "end.reason.boat_broke_through"
    assert boat_debrief.outcome(game, boat) == "broke_through"
    assert uboot_view.end_text(game, boat) == "uboot.end.broke_through"


def test_holding_the_boat_off_wins_for_the_frigate():
    game, boat = _boat_game("s5_durchbruch")
    game.mission_time = game.mission.time_limit_s
    game._check_mission_end()
    assert game.mission_result == "SIEG" and _reason(game) == "end.reason.boat_stopped"
    assert boat_debrief.outcome(game, boat) == "over"
    # A sunk boat ends it at once as well.
    game, boat = _boat_game("s6_aufklaerung")
    boat.sub.sunk = True
    game._check_mission_end()
    assert game.mission_result == "SIEG"


def _raise_mast(boat):
    sub = boat.sub
    sub.depth = sub.target_depth = sub.order_depth = MAST_DEPTH_M - 3.0
    assert sub.command_mast(True) is True


def _send_report(game, boat):
    assert boat.radio.send_sitrep(game, boat) is True
    end = game.sim_t + config.UBOOT_RADIO_TX_S + 1.0
    while game.sim_t < end and not game.game_over:
        game.sim_t += 0.5
        boat.radio.update(game, boat)


def _sighting(game):
    return dict(ref="V-00000001", target_id=OWNSHIP_TARGET_ID, kind="SURFACE",
                cls="warship", bearing=90.0, span_deg=1.0, aspect=1.0, quality=.8,
                first_t=game.sim_t, t=game.sim_t, range_nm=None, range_sigma_nm=None,
                range_t=None)


def test_a_report_without_the_frigate_in_sight_does_not_count():
    game, boat = _boat_game("s6_aufklaerung")
    _raise_mast(boat)
    game.sim_t = 100.0
    _send_report(game, boat)
    assert boat.radio.sitreps == 1 and game.mission_result is None


def test_a_report_with_the_frigate_in_sight_wins_recon():
    game, boat = _boat_game("s6_aufklaerung")
    _raise_mast(boat)
    game.sim_t = 100.0
    boat.orders.sightings = [_sighting(game)]
    assert localize(boat_missions.objective(game, boat)).startswith("Frigate in sight")
    _send_report(game, boat)
    assert game.mission_result == "VERLOREN" and _reason(game) == "end.reason.boat_reported"
    assert boat_debrief.outcome(game, boat) == "reported"


def test_a_frigate_mission_ignores_boat_reports():
    game, boat = _boat_game("s1_patrouille")
    _raise_mast(boat)
    game.sim_t = 100.0
    boat.orders.sightings = [_sighting(game)]
    _send_report(game, boat)
    assert game.mission_result is None


def test_the_boat_sees_its_orders_on_the_chart_and_in_the_browser(monkeypatch):
    game, boat = _boat_game("s5_durchbruch")
    text = localize(boat_missions.objective(game, boat))
    assert text.startswith("Break through to the goal area: bearing ")
    monkeypatch.setattr(projections, "_common",
                        lambda game, status, role: {"mission": {}})
    common = projections._opfor_common(game, {}, "uboot", boat)
    assert common["mission"]["objective"] == text
    for language in ("en", "de"):
        game.preferences = replace(game.preferences, language=language)
        layout.configure_for(game)
        uboot_view.draw_chart(game, boat)
    # The frigate's own view names its side of the mission.
    assert localize(game.mission_objective_display()).startswith(
        "Stop the submarine breaking through")


def test_boat_missions_run_with_the_crew_cadence():
    game, boat = _boat_game("s6_aufklaerung")
    for _ in range(40):
        game._update_sim(0.25)
    opfor.update_crew(game, boat)
    assert game.mission_result is None


# --- convoy attack -------------------------------------------------------------

from src.core import hunter  # noqa: E402
from src.weapons.torpedo import EnemyTorpedo  # noqa: E402


def _shot_at(game, ship, platform_id):
    """A running torpedo 0.5 NM off a ship, guided onto it."""
    torpedo = EnemyTorpedo(ship.x - 0.5, ship.y, 90.0, 5.0, 1,
                           profile=game.runtime_catalog.torpedoes[
                               game.runtime_catalog.runtime_bindings["enemy_torpedo"]],
                           guidance_x=ship.x, guidance_y=ship.y,
                           launch_platform_id=platform_id)
    game.enemy_torpedoes.append(torpedo)
    for _ in range(1200):
        if torpedo.state != "RUN":
            break
        game._update_enemy_torpedoes(0.1)
    return torpedo


def _quiet_convoy(game):
    """Stop the convoy so a test shot is geometry only."""
    for ship in boat_missions.convoy(game):
        ship.speed = ship.target_speed = 0.0
    game.ship.x, game.ship.y = game.ship.x + 30.0, game.ship.y + 30.0


def test_the_convoy_sails_with_the_frigate_and_is_saved():
    game, _boat = _boat_game("s7_geleitzug")
    ships = boat_missions.convoy(game)
    assert len(ships) == config.BOAT_CONVOY_SIZE
    assert [f"convoy-{n}" for n in range(1, 5)] == sorted(game.mission_units)
    course = config.SCENARIOS["s7_geleitzug"]["ship_course"]
    for ship in ships:
        assert ship.course == course and ship.turn_left > game.mission.time_limit_s
        assert math.hypot(ship.x - game.ship.x, ship.y - game.ship.y) < 3.0
    data = game.save_state()
    assert game._load_save_data(json.loads(json.dumps(data)))
    assert [ship.id for ship in boat_missions.convoy(game)] == [ship.id for ship in ships]


def test_only_the_crewed_boats_torpedo_takes_a_merchant():
    game, boat = _boat_game("s7_geleitzug")
    _quiet_convoy(game)
    first, second = boat_missions.convoy(game)[:2]
    stray = _shot_at(game, first, platform_id=-1)          # not the crewed boat
    assert stray.state != "STRUCK" and not first.sunk
    torpedo = _shot_at(game, second, platform_id=boat.sub.id)
    assert torpedo.state == "STRUCK" and second.sunk
    assert boat_missions.convoy_sunk(game) == 1
    assert game.mission_result is None and not game.incident
    assert "1 sunk" in localize(boat_missions.objective(game, boat))


def test_two_merchants_sunk_win_the_convoy_attack():
    game, boat = _boat_game("s7_geleitzug")
    ships = boat_missions.convoy(game)
    ships[0].sunk = ships[3].sunk = True
    game._check_mission_end()
    assert game.mission_result == "VERLOREN" and _reason(game) == "end.reason.convoy_lost"
    assert boat_debrief.outcome(game, boat) == "convoy_sunk"
    game, boat = _boat_game("s7_geleitzug")
    game.mission_time = game.mission.time_limit_s
    game._check_mission_end()
    assert game.mission_result == "SIEG" and _reason(game) == "end.reason.convoy_survived"


def test_the_ai_frigate_escorts_the_convoy_without_a_datum():
    game, _boat = _boat_game("s7_geleitzug")
    ships = boat_missions.convoy(game)
    game.ship.x -= 10.0                                   # fell behind
    course, speed = hunter.escort_course(game)
    assert speed == hunter.TRANSIT_KN and abs(((course - 90.0 + 180.0) % 360.0) - 180.0) < 30.0
    game.ship.x = sum(s.x for s in ships) / 4 + 3.0       # on station ahead
    game.ship.y = sum(s.y for s in ships) / 4
    course, speed = hunter.escort_course(game)
    assert speed == ships[0].speed + 2.0
    for ship in ships:
        ship.sunk = True
    assert hunter.escort_course(game) is None
