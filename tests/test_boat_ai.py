"""The AI boat pursues a boat mission's objective when nobody crews it."""

import json
import math
import sys
from pathlib import Path

import pytest

from src.core import boat_ai, boat_missions, config
from src.core.game import Game
from src.sensors.platform import MAST_DEPTH_M

sys.path.insert(0, str(Path(__file__).parent))
from test_boat_missions import _boat_game, _quiet_convoy, _reason, _shot_at  # noqa: E402


def _frigate_game(scenario, seed=61):
    game = Game(seed=seed, start_menu=False, audio_enabled=False, language="en")
    game.reset(seed, scenario)
    game._update(0.05)
    assert game.opfor is None
    sub = boat_missions.target_sub(game)
    assert boat_ai.boat(game) is sub
    return game, sub


def _run(game, seconds, step=0.5):
    for _ in range(int(seconds / step)):
        game._update_sim(step)
        if game.mission_result is not None:
            break


def _goal_range(game, sub):
    point = boat_missions.goal(game)
    return math.hypot(point["x"] - sub.x, point["y"] - sub.y)


def test_the_ai_boat_runs_for_the_breakthrough_goal():
    game, sub = _frigate_game("s5_durchbruch")
    game.ship.x, game.ship.y = game.ship.x + 60.0, game.ship.y + 60.0   # out of the way
    before = _goal_range(game, sub)
    _run(game, 600)
    assert sub.mission_orders is not None
    course, speed, depth = sub.mission_orders
    assert speed == config.BOAT_AI_TRANSIT_KN and depth >= 40.0
    assert before - _goal_range(game, sub) > 0.5
    # A crewed boat keeps its crew's orders.
    game, boat = _boat_game("s5_durchbruch")
    _run(game, 5)
    assert boat_ai.boat(game) is None and boat.sub.mission_orders is None
    # Frigate missions have no mission leg.
    game = Game(seed=61, start_menu=False, audio_enabled=False, language="en")
    game.reset(61, "s1_patrouille")
    _run(game, 5)
    assert all(s.mission_orders is None for s in game.subs)


def test_the_mission_leg_continues_identically_after_a_load():
    game, sub = _frigate_game("s5_durchbruch", seed=62)
    _run(game, 120)
    data = json.loads(json.dumps(game.save_state()))
    _run(game, 240)
    expected = (round(sub.x, 9), round(sub.y, 9), round(sub.depth, 6))
    other = Game(seed=62, start_menu=False, audio_enabled=False, language="en")
    assert other._load_save_data(data)
    _run(other, 240)
    copy = boat_missions.target_sub(other)
    assert (round(copy.x, 9), round(copy.y, 9), round(copy.depth, 6)) == expected


def test_the_ai_boat_reports_the_frigate_only_from_periscope_depth():
    game, sub = _frigate_game("s6_aufklaerung")
    sub.x, sub.y = game.ship.x + 3.0, game.ship.y
    sub.depth = sub.target_depth = 120.0
    for _ in range(80):                                    # 160 s deep: no report
        game.sim_t += 2.0
        assert not boat_ai.report(game, sub)
    assert game.mission_result is None
    sub.depth = MAST_DEPTH_M - 3.0
    reported = False
    for _ in range(80):
        game.sim_t += 2.0
        if boat_ai.report(game, sub):
            reported = True
            break
    assert reported
    assert game.mission_result == "VERLOREN" and _reason(game) == "end.reason.boat_reported"


def _clear_day(game, **change):
    light = dict(visibility_nm=config.WEATHER_VISIBILITY_MAX_NM, night=False,
                 illumination=0.5, sea_state=1.0)
    light.update(change)
    game._lookout_environment = lambda: dict(light)


def test_the_recon_periscope_looks_round_part_of_the_time_and_shows_on_radar():
    game, sub = _frigate_game("s6_aufklaerung")
    _clear_day(game)
    sub.x, sub.y = game.ship.x + 3.0, game.ship.y
    sub.depth = MAST_DEPTH_M - 3.0
    up, sighted = 0, 0
    cycle = int(config.BOAT_AI_SCOPE_CYCLE_S)
    for step in range(cycle):
        game.sim_t = 1000.0 + step
        look = boat_ai.scope_look(game, sub)
        assert (look is not None) == game._mast_up(sub)
        up += look is not None
        sighted += boat_ai.frigate_sighted(game, sub)
    assert up == pytest.approx(config.BOAT_AI_SCOPE_LOOK_S, abs=1)
    # The head reaches the frigate's bearing part of the way round the sweep.
    assert 0 < sighted < up
    sub.depth = MAST_DEPTH_M + 5.0
    assert all(boat_ai.scope_look(game, sub) is None and not game._mast_up(sub)
               for game.sim_t in (1000.0 + t for t in range(cycle)))


def test_the_recon_periscope_needs_the_frigate_above_the_optics_threshold():
    game, sub = _frigate_game("s6_aufklaerung")
    _clear_day(game)
    sub.x, sub.y = game.ship.x + 7.0, game.ship.y
    sub.depth = MAST_DEPTH_M - 3.0
    times = [1000.0 + t for t in range(int(config.BOAT_AI_SCOPE_CYCLE_S))]

    def seen():
        return any(boat_ai.frigate_sighted(game, sub) for game.sim_t in times)

    assert seen()
    _clear_day(game, visibility_nm=2.0)                   # fog: 7 NM is out of sight
    assert not seen()
    _clear_day(game, night=True)                          # night: likewise
    assert not seen()
    _clear_day(game)
    sub.x = game.ship.x + config.BOAT_AI_SIGHT_NM + 1.0   # beyond the report range
    assert not seen()


def test_the_recon_boat_follows_hq_reports_then_comes_up():
    game, sub = _frigate_game("s6_aufklaerung")
    sub.memory["contact"] = None
    game.sim_t = 3 * config.UBOOT_RADIO_BROADCAST_S
    x, y, _course, _speed = boat_ai.recon_target(game, sub)
    # HQ's report lies within its stated circle of the frigate, or the
    # boat falls back to the frigate's patrol area.
    start = config.SCENARIOS["s6_aufklaerung"]["ship_start"]
    assert (math.hypot(x - game.ship.x, y - game.ship.y)
            <= 2.0 * config.UBOOT_RADIO_REPORT_RADIUS_NM + 1.0
            or (x, y) == (float(start[0]), float(start[1])))
    sub.x, sub.y = x + 30.0, y
    _, speed, depth = boat_ai.orders(game, sub)
    assert speed >= config.BOAT_AI_TRANSIT_KN and depth > MAST_DEPTH_M
    sub.x = x + 5.0
    _, speed, depth = boat_ai.orders(game, sub)
    assert speed == config.BOAT_AI_PERISCOPE_KN and depth < MAST_DEPTH_M
    # Its own contact comes first.
    sub.memory["contact"] = dict(x=1.0, y=2.0, speed=5.0, course=90.0, noise=.5)
    assert boat_ai.recon_target(game, sub) == (1.0, 2.0, 90.0, 5.0)


def test_the_ai_boat_attacks_the_convoy():
    game, sub = _frigate_game("s7_geleitzug")
    _quiet_convoy(game)
    target = boat_missions.convoy(game)[0]
    sub.x, sub.y = target.x - 3.0, target.y
    sub.course = sub.target_course = 90.0
    sub.state = "PATROLLE"
    # Dry tubes: the boat floods them quietly first and holds its fire.
    game.sim_t += 60.0
    assert not boat_ai.attack(game, sub)
    assert sub.ai_tube_left == config.UBOOT_TUBE_FLOOD_QUIET_S and sub.flood_quiet
    sub.ai_tube_left = 0.0
    fired = False
    for _ in range(40):
        game.sim_t += 2.0
        if boat_ai.attack(game, sub):
            fired = True
            break
    assert fired and len(sub.pending_torpedoes) == 1
    # One at a time: no second shot while the first is under way.
    game.sim_t += 60.0
    assert not boat_ai.attack(game, sub)
    # The AI mission boat's torpedo takes a merchant here, a stray one does not.
    sub.pending_torpedoes.clear()
    torpedo = _shot_at(game, boat_missions.convoy(game)[1], platform_id=sub.id)
    assert torpedo.state == "STRUCK" and boat_missions.convoy_sunk(game) == 1
    stray = _shot_at(game, boat_missions.convoy(game)[2], platform_id=-1)
    assert stray.state != "STRUCK"


def test_the_convoy_boat_closes_the_convoy_from_afar():
    game, sub = _frigate_game("s7_geleitzug")
    ships = boat_missions.convoy(game)
    cx = sum(s.x for s in ships) / len(ships)
    cy = sum(s.y for s in ships) / len(ships)
    sub.x, sub.y = cx, cy + 20.0                         # due south
    course, speed, _ = boat_ai.orders(game, sub)
    # Faster than the convoy, and led ahead of it (the convoy sails east).
    assert speed == min(sub.motion.maximum_speed_kn,
                        ships[0].speed + config.BOAT_AI_CLOSING_KN)
    assert 0.0 < course < 60.0


def test_a_hunted_ai_boat_creeps():
    """1.3.70: a ping heard lately, or the frigate known close, slows the leg."""
    game, sub = _frigate_game("s5_durchbruch")
    sub.memory["last_ping_age"] = float("inf")
    sub.memory["last_torpedo_age"] = float("inf")
    sub.memory["contact"] = None
    assert boat_ai.orders(game, sub)[1] == config.BOAT_AI_TRANSIT_KN
    sub.memory["last_ping_age"] = 30.0
    assert boat_ai.orders(game, sub)[1] == config.BOAT_AI_CREEP_KN
    sub.memory["last_ping_age"] = config.BOAT_AI_HUNTED_S + 1.0
    sub.memory["contact"] = dict(x=sub.x + 5.0, y=sub.y, course=0.0, speed=10.0, noise=0.5)
    sub.memory["contact_age"] = 10.0
    assert boat_ai.hunted(sub)
    sub.memory["contact"]["x"] = sub.x + config.BOAT_AI_THREAT_NM + 5.0
    assert not boat_ai.hunted(sub)


def test_the_breakthrough_boat_passes_wide_of_a_known_frigate():
    game, sub = _frigate_game("s5_durchbruch")
    course = 90.0
    sub.memory["contact_age"] = 10.0
    sub.memory["contact"] = dict(x=sub.x + 8.0, y=sub.y + 1.0, course=0.0, speed=10.0,
                                 noise=0.5)
    # The frigate lies 1 NM south of the leg east: turn away north.
    assert boat_ai.detour(sub, course, 20.0) == (course - config.BOAT_AI_DETOUR_DEG) % 360.0
    sub.memory["contact"]["y"] = sub.y - 1.0
    assert boat_ai.detour(sub, course, 20.0) == course + config.BOAT_AI_DETOUR_DEG
    # Well clear of the leg or behind the boat: no detour.
    sub.memory["contact"]["y"] = sub.y + config.BOAT_AI_DETOUR_NM + 2.0
    assert boat_ai.detour(sub, course, 20.0) == course
    sub.memory["contact"].update(x=sub.x - 5.0, y=sub.y)
    assert boat_ai.detour(sub, course, 20.0) == course


def test_the_convoy_boat_lies_in_wait_ahead_of_the_convoy():
    game, sub = _frigate_game("s7_geleitzug")
    ships = boat_ai.convoy_ships(game)
    point = boat_ai.ambush_point(sub, ships)
    assert point is not None
    cx = sum(ship.x for ship in ships) / len(ships)
    cy = sum(ship.y for ship in ships) / len(ships)
    rad = math.radians(ships[0].course)
    ahead = (point[0] - cx) * math.sin(rad) - (point[1] - cy) * math.cos(rad)
    assert ahead == pytest.approx(config.BOAT_AI_AMBUSH_AHEAD_NM)
    assert math.hypot(point[0] - cx, point[1] - cy) == pytest.approx(
        math.hypot(config.BOAT_AI_AMBUSH_AHEAD_NM, config.BOAT_AI_AMBUSH_ABEAM_NM))
    # Waiting there, it hovers slowly; a convoy that has passed is chased.
    sub.x, sub.y = point
    sub.memory["last_ping_age"] = sub.memory["last_torpedo_age"] = float("inf")
    if min(math.hypot(s.x - sub.x, s.y - sub.y) for s in ships) > config.BOAT_AI_ATTACK_NM:
        assert boat_ai.orders(game, sub)[1] == config.BOAT_AI_WAIT_KN
    sub.x = cx - 10.0 * math.sin(rad)
    sub.y = cy + 10.0 * math.cos(rad)
    assert boat_ai.ambush_point(sub, ships) is None
