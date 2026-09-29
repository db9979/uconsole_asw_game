"""Plan 1.3, phase 5: the AI boat fires on its own TMA only once it converged."""

import copy
import dataclasses
import json
import math
import random

from src.core import config
from src.core.game import Game
from src.enemies import sub as sub_module
from src.enemies.sub import Sub, solution_converged, solution_sigma_nm
from src.sensors.platform import PlatformObservation


class Ocean:
    """The same flat, quiet ocean stub the hostile-sensor tests use."""
    size_nm = 500.0
    sea_state = 1
    effective_sea_state = 1.0
    depth_m = staticmethod(lambda *a: 3000.0)
    thermocline_depth_m = staticmethod(lambda *a: 60.0)
    on_land = staticmethod(lambda *a: False)
    land_blocks_line = staticmethod(lambda *a: False)
    sonar_path_blocked = staticmethod(lambda *a: False)
    current_vec = staticmethod(lambda *a: (0.0, 0.0))


def _bearing_observation(sub, target, t):
    bearing = math.degrees(math.atan2(target[0] - sub.x, -(target[1] - sub.y))) % 360.0
    return PlatformObservation(
        track_id="Lcontact", domain="sonar", source="SONAR", observer_x=sub.x,
        observer_y=sub.y, bearing=bearing, range_nm=None, x=None, y=None,
        course=None, speed_kn=None, depth_m=None, quality=0.8, signal=0.6,
        last_seen=t, bearing_uncertainty_deg=0.5, range_uncertainty_nm=None,
        depth_uncertainty_m=None, label=None)


def _tracking_boat(seed=2, threshold=0.20):
    sub = Sub(100.0, 100.0, 80.0, 0.0, "aip_modern", random.Random(seed),
              solution_threshold=threshold)
    sub.endurance = None
    sub.speed = 6.0
    return sub


def _run(sub, target, seconds, course_kn=(90.0, 12.0), start_t=0.0):
    """Drive a moving target past the boat; returns the sigma history."""
    world = Ocean()
    course, speed = course_kn
    vx = config.kn_to_nm_per_s(speed) * math.sin(math.radians(course))
    vy = -config.kn_to_nm_per_s(speed) * math.cos(math.radians(course))
    t = start_t
    history = []
    for _ in range(int(seconds)):
        t += 1.0
        target[0] += vx
        target[1] += vy
        sub.update(1.0, _bearing_observation(sub, target, t), world)
        history.append(sub.memory["contact_sigma_nm"])
    return history, t


def test_converged_gate_is_pure_and_bounded():
    assert solution_converged(0.5, 5.0, 0.20, 10.0)
    assert not solution_converged(1.5, 5.0, 0.20, 10.0)
    assert not solution_converged(0.5, 5.0, 0.20, sub_module.SUB_SOLUTION_MAX_AGE_S + 1)
    assert not solution_converged(None, 5.0, 0.20, 0.0)
    assert not solution_converged(0.5, 0.0, 0.20, 0.0)

    class Solution:
        ellipse = (1.25, 0.4, 30.0)
        quality = 0.9
    assert solution_sigma_nm(Solution(), 8.0) == 1.25
    Solution.ellipse = None
    assert math.isclose(solution_sigma_nm(Solution(), 8.0), 0.8)


def test_solution_converges_with_own_legs_and_reopens_after_a_target_manoeuvre():
    sub = _tracking_boat(threshold=0.30)
    target = [106.0, 96.0]
    world = Ocean()
    vx = config.kn_to_nm_per_s(12.0)
    t = 0.0
    converged_at = None
    for step in range(1, 601):
        t += 1.0
        target[0] += vx
        if step in (100, 300):                      # the boat's own TMA legs
            sub.course = (sub.course + (90.0 if step == 100 else -90.0)) % 360.0
            sub.target_course = sub.course
        sub.update(1.0, _bearing_observation(sub, target, t), world)
        distance = math.hypot(target[0] - sub.x, target[1] - sub.y)
        if converged_at is None and solution_converged(
                sub.memory["contact_sigma_nm"], distance, sub.solution_threshold,
                sub.memory["contact_age"]):
            converged_at = t
    assert converged_at is not None, "own legs never converged the solution"
    assert sub.memory["contact_t"] is not None and sub.memory["contact_t"] <= t
    # A bearing the solution cannot explain (a target manoeuvre) reopens the
    # plot: the gate closes, the track restarts and three new bearings are
    # needed before the boat solves again.
    predicted = sub_module.solution_predicts_bearing(
        sub.memory["contact"], sub.memory["contact_t"], sub.x, sub.y, t + 1.0)
    jump = _bearing_observation(sub, target, t + 1.0)
    jump = dataclasses.replace(jump, bearing=(predicted + 12.0) % 360.0)
    sub.update(1.0, jump, world)
    assert sub.memory["contact_reopen_left"] == sub_module.SUB_SOLUTION_REOPEN_BEARINGS
    assert sub.memory["contact_sigma_nm"] is None and len(sub.tma_track.pts) == 1
    distance = math.hypot(target[0] - sub.x, target[1] - sub.y)
    assert not solution_converged(sub.memory["contact_sigma_nm"], distance,
                                  sub.solution_threshold, sub.memory["contact_age"])
    for offset in (2.0, 3.0, 4.0):
        sub.update(1.0, _bearing_observation(sub, target, t + offset), world)
    assert sub.memory["contact_reopen_left"] == 0


def test_boat_holds_fire_until_its_solution_converges(monkeypatch):
    sub = _tracking_boat(threshold=0.05)
    sub.stype.aggression = 1.5
    sub.heard_ping = True
    sub.memory["last_ping_age"] = 0.0
    sub.state = "EVADE"
    remembered = dict(x=sub.x + 4.0, y=sub.y, speed=0.0, course=0.0, noise=1.0)
    sub.memory.update(contact=remembered, contact_age=0.0, contact_bearing=90.0,
                      contact_sigma_nm=2.0, contact_t=0.0)
    sub.attack_left = 0.0
    monkeypatch.setattr(sub.asw_rng, "random", lambda: 0.0)   # every roll fires
    before = len(sub.pending_torpedoes)
    sub.update(0.1, None, Ocean())          # memory-derived TMA observation
    assert len(sub.pending_torpedoes) == before, "unconverged solution was fired on"
    sub.memory["contact_sigma_nm"] = 0.1     # 0.1 / 4 NM = 2.5 % < 5 %
    sub.attack_left = 0.0
    sub.ai_tube_left = 0.0                   # the tubes are flooded by now
    sub.update(0.1, None, Ocean())
    assert len(sub.pending_torpedoes) > before
    # a positioned (active/datalink) observation is not gated by the threshold
    sub2 = _tracking_boat(threshold=0.05)
    sub2.stype.aggression = 1.5
    sub2.heard_ping = True
    sub2.memory["last_ping_age"] = 0.0
    sub2.state = "EVADE"
    sub2.attack_left = 0.0
    sub2.ai_tube_left = 0.0
    monkeypatch.setattr(sub2.asw_rng, "random", lambda: 0.0)
    fix = PlatformObservation(
        track_id="Lfix", domain="sonar", source="SONAR", observer_x=sub2.x,
        observer_y=sub2.y, bearing=90.0, range_nm=4.0, x=sub2.x + 4.0, y=sub2.y,
        course=0.0, speed_kn=5.0, depth_m=5.0, quality=0.9, signal=1.0,
        last_seen=1.0, bearing_uncertainty_deg=1.0, range_uncertainty_nm=0.3,
        depth_uncertainty_m=None, label=None, fix_source="ACTIVE")
    sub2.update(0.1, fix, Ocean())
    assert sub2.pending_torpedoes


def test_difficulty_threshold_reaches_every_boat_and_the_save():
    assert config.DIFFICULTY_FIELDS["enemy_solution_threshold"][4] == 0.20
    assert config.SCENARIOS["s3_abfang"]["difficulty"]["enemy_solution_threshold"] == 0.15
    game = Game(seed=515, start_menu=False, audio_enabled=False)
    assert all(sub.solution_threshold == game.difficulty["enemy_solution_threshold"]
               for sub in game.subs)
    for _ in range(4):
        game._update_sim(0.25)
    state = json.loads(json.dumps(game.save_state(), allow_nan=False))
    row = state["subs"][0]
    assert row["solution_threshold"] == game.difficulty["enemy_solution_threshold"]
    assert {"contact_sigma_nm", "contact_t"} <= set(row["memory"])
    restored = Game(seed=515, start_menu=False, audio_enabled=False)
    restored.load_state(copy.deepcopy(state))
    assert restored.subs[0].solution_threshold == row["solution_threshold"]
    broken = copy.deepcopy(state)
    broken["subs"][0]["solution_threshold"] = 0.9
    assert not restored._load_save_data(broken)
    broken = copy.deepcopy(state)
    del broken["subs"][0]["memory"]["contact_sigma_nm"]
    assert not restored._load_save_data(broken)


def test_same_seed_gives_the_same_solutions():
    runs = []
    for _ in range(2):
        sub = _tracking_boat(seed=7)
        history, _ = _run(sub, [106.0, 96.0], 300)
        runs.append((history, sub.memory["contact"]))
    assert runs[0] == runs[1]
