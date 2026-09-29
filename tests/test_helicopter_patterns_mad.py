"""Plan 1.3, phase 6: sonobuoy patterns and the MAD run."""

import copy
import json
import math

import pytest

from src.air import helicopter as helicopter_physics
from src.core import config
from src.core.game import Game
from src.sensors import mad


def _airborne_game(seed=606):
    game = Game(seed=seed, start_menu=False, audio_enabled=False)
    game.helo.launch(game.ship)
    game.helo.x, game.helo.y = game.ship.x + 3.0, game.ship.y
    game.helo.fuel_s = config.HELO_FUEL_S
    return game


def test_pattern_geometry_is_bounded_by_stock_and_kind():
    field = helicopter_physics.plan_buoy_pattern("field", 100.0, 100.0, 0.0, 5)
    assert len(field) == 4 and len({tuple(p) for p in field}) == 4
    assert all(abs(x - 100.0) == pytest.approx(0.75) and abs(y - 100.0) == pytest.approx(0.75)
               for x, y in field)
    barrier = helicopter_physics.plan_buoy_pattern("barrier", 100.0, 100.0, 0.0, 3)
    assert len(barrier) == 3
    assert all(y == pytest.approx(100.0) for _, y in barrier)          # across north
    assert barrier[-1][0] - barrier[0][0] == pytest.approx(2 * config.BUOY_SPACING_NM)
    circle = helicopter_physics.plan_buoy_pattern("circle", 100.0, 100.0, 45.0, 2)
    assert len(circle) == 2
    assert all(math.hypot(x - 100.0, y - 100.0) == pytest.approx(1.5) for x, y in circle)
    assert helicopter_physics.plan_buoy_pattern("single", 0.0, 0.0, 0.0, 4) == []
    assert helicopter_physics.plan_buoy_pattern("field", 0.0, 0.0, 0.0, 0) == []


def test_pattern_is_flown_and_dropped_one_buoy_at_a_time():
    game = _airborne_game()
    assert game.set_helicopter_pattern("zigzag") == "invalid_value"
    assert game.set_helicopter_pattern("field") is True
    helo = game.helo
    assert helo.pattern == "field" and len(helo.pattern_queue) == 4
    assert (helo.waypoint_x, helo.waypoint_y) == helo.pattern_queue[0]
    before = helo.buoys_left
    for _ in range(4000):
        game._update_sim(0.25)
        if not helo.pattern_queue:
            break
    assert not helo.pattern_queue and helo.pattern == "single"
    assert helo.buoys_left == before - 4 and len(game.buoys) == 4
    assert game.set_helicopter_pattern("single") is True


def test_single_clears_and_a_return_drops_the_queue():
    game = _airborne_game(607)
    assert game.set_helicopter_pattern("barrier") is True
    assert game.set_helicopter_pattern("single") is True and not game.helo.pattern_queue
    assert game.set_helicopter_pattern("circle") is True
    game.helo.order_return()
    game.helo.update(0.25, game.ship, game.world)
    assert not game.helo.pattern_queue and game.helo.pattern == "single"
    game.helo.state = "HANGAR"
    assert game.set_helicopter_pattern("field") == "not_ready"


def test_mad_probability_and_draw_are_pure():
    assert mad.detection_probability(100.0) == mad.MAD_SURE_PROBABILITY
    assert mad.detection_probability(mad.MAD_MAX_SLANT_M) == 0.0
    assert 0.0 < mad.detection_probability(325.0) < mad.MAD_SURE_PROBABILITY
    assert mad.slant_m(0.0, 70.0) == pytest.approx(100.0)
    assert mad.detects(1, 2, 3, 100.0) == mad.detects(1, 2, 3, 100.0)
    assert not mad.detects(1, 2, 3, 1000.0)


def test_mad_run_needs_the_dome_stowed_and_reports_a_fix_without_hidden_truth():
    game = _airborne_game(608)
    helo = game.helo
    assert game.set_helicopter_mad(True) is True and helo.mad_mode
    assert helo.speed_kn == mad.MAD_SPEED_KN
    sub = game.subs[0]
    helo.x, helo.y = sub.x, sub.y
    sub.depth = 60.0
    found = False
    for _ in range(80):
        # Each sensor tick is a fresh draw only if simulation time moves on.
        game.sim_t += 0.25
        game._update_sensors(0.25)
        contact = game.sonar.contacts.get(sub.id)
        if contact is not None and contact.fixes.get("MAD") is not None:
            found = True
            break
    assert found, "no MAD detection directly over a 60 m submarine"
    fix = contact.fixes["MAD"]
    assert fix["depth_m"] is None and fix["quality"] == mad.MAD_FIX_QUALITY
    assert contact.range_source == "mad" and contact.depth_est is None
    assert any(f["source"] == "MAD" for f in contact.active_fixes(game.sim_t))
    assert game._contact_range_fresh(contact)
    game.helo.set_dipping(True, game.world)
    game.helo.mad_mode = False
    assert game.set_helicopter_mad(True) == "dip_deployed"
    game.helo.set_dipping(False, game.world)
    game.helo.dip_state = "STOWED"
    assert game.set_helicopter_mad(False) is True and not helo.mad_mode


def test_pattern_and_mad_survive_the_save(tmp_path):
    game = _airborne_game(609)
    assert game.set_helicopter_pattern("barrier") is True
    game.helo.mad_mode = True
    for _ in range(4):
        game._update_sim(0.25)
    state = json.loads(json.dumps(game.save_state(), allow_nan=False))
    assert state["helo"]["pattern"] == "barrier" and len(state["helo"]["pattern_queue"]) == 4
    assert state["helo"]["mad_mode"] is True
    restored = Game(seed=609, start_menu=False, audio_enabled=False)
    restored.load_state(copy.deepcopy(state))
    assert restored.helo.pattern == "barrier"
    assert restored.helo.pattern_queue == [tuple(p) for p in state["helo"]["pattern_queue"]]
    assert restored.helo.mad_mode is True
    for mutate in (lambda s: s["helo"].__setitem__("pattern", "zigzag"),
                   lambda s: s["helo"].__setitem__("mad_mode", 1),
                   lambda s: s["helo"].__setitem__("pattern_queue", []),
                   lambda s: s["helo"].__setitem__("pattern_queue", [[1.0]])):
        broken = copy.deepcopy(state)
        mutate(broken)
        assert not restored._load_save_data(broken)
