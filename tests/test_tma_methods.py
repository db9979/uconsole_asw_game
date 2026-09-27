"""Plan 1.3, phase 7: Ekelund range and dot stack beside the hypothesis TMA."""

import copy
import json
import math
import random

import pytest

from src.core import config
from src.core.game import Game
from src.sonar import tma_operator
from src.sonar.tma import BearingPoint


def _two_leg_track(range_nm=8.0, target_speed=6.0, noise=0.0, seed=5):
    """Own ship runs two 150 s legs with a 60 deg turn; the target crosses."""
    rng = random.Random(seed)
    own_x, own_y, own_course, own_speed = 100.0, 100.0, 0.0, 10.0
    target = [100.0 + range_nm, 100.0]
    vx = config.kn_to_nm_per_s(target_speed)
    points = []
    for step in range(300):
        t = float(step)
        if step == 150:
            own_course = 60.0
        own_x += config.kn_to_nm_per_s(own_speed) * math.sin(math.radians(own_course))
        own_y -= config.kn_to_nm_per_s(own_speed) * math.cos(math.radians(own_course))
        target[1] += vx
        bearing = math.degrees(math.atan2(target[0] - own_x, -(target[1] - own_y))) % 360.0
        bearing = (bearing + rng.gauss(0.0, noise)) % 360.0
        if step % 5 == 0:
            points.append(BearingPoint(t, bearing, own_x, own_y, own_course, 0.5,
                                       None, own_speed))
    truth = math.hypot(target[0] - own_x, target[1] - own_y)
    return points, truth


def test_ekelund_needs_two_legs_and_lands_near_the_truth():
    points, truth = _two_leg_track()
    estimate = tma_operator.ekelund_range_nm(points)
    assert estimate is not None
    range_nm, uncertainty = estimate
    assert uncertainty == pytest.approx(range_nm * tma_operator.EKELUND_UNCERTAINTY)
    assert abs(range_nm - truth) / truth < 0.35
    straight = [BearingPoint(p.t, p.bearing, p.fx, p.fy, 0.0, 0.5, None, 10.0)
                for p in points]
    assert tma_operator.ekelund_range_nm(straight) is None
    assert tma_operator.ekelund_range_nm(points[:6]) is None


def test_dot_stack_rows_bracket_the_hypothesis_range():
    points, truth = _two_leg_track()
    hypothesis = tma_operator.Hypothesis(180.0, 6.0, truth)   # the target runs south
    rows = tma_operator.dot_stack(points, hypothesis)
    assert [round(r / truth, 1) for r, _ in rows] == [0.6, 1.0, 1.6]
    flat = [math.sqrt(sum(v * v for v in residuals) / len(residuals)) for _, residuals in rows]
    assert flat[1] < flat[0] and flat[1] < flat[2], "true range gives the flattest row"


def test_method_is_a_station_setting_that_saves_and_gates_shift_k(tmp_path):
    game = Game(seed=707, start_menu=False, audio_enabled=False)
    assert game.tma_method == "hypothesis"
    assert game.set_tma_method("magic") == "invalid_value"
    game._cycle_tma_method()
    assert game.tma_method == "ekelund"
    game._cycle_tma_method()
    assert game.tma_method == "dotstack"
    game.set_tma_method("ekelund")
    state = json.loads(json.dumps(game.save_state(), allow_nan=False))
    assert state["sonar_controls"]["tma_method"] == "ekelund"
    restored = Game(seed=707, start_menu=False, audio_enabled=False)
    restored.load_state(copy.deepcopy(state))
    assert restored.tma_method == "ekelund"
    broken = copy.deepcopy(state)
    broken["sonar_controls"]["tma_method"] = "magic"
    assert not restored._load_save_data(broken)
    with game.sonar_perspective(game._frigate_sonar):
        assert game.copy_tma_ekelund(None) == "stale_ref"
