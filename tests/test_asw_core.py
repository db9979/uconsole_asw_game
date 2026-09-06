"""Fokustests fuer mathematische ASW-Grundmechaniken."""

import random

from src.core import config
from src.enemies.sub import Sub
from src.ship.damage import DamageModel
from src.ship.ship import Ship
from src.sonar.sonar import bearing_error_deg, snr_db
from src.sonar.sonar import SonarSystem
from src.sonar.tma import BearingTrack, solve_tma
from src.sonar import tma as tma_module
from src.world.world import World
from src.weapons.torpedo import Torpedo


class Target:
    def __init__(self, x, y, depth=60.0):
        self.id = 9001
        self.x = x
        self.y = y
        self.depth = depth
        self.sunk = False
        self.state = "RUN"

    def distance_nm(self, frigate):
        return ((self.x - frigate.x) ** 2 + (self.y - frigate.y) ** 2) ** 0.5

    def hit(self):
        self.sunk = True
        self.state = "SINKING"


def test_snr_is_zero_at_detection_edge():
    assert abs(snr_db(20.0, 20.0)) < 1e-9
    assert snr_db(20.0, 10.0) > snr_db(20.0, 20.0)


def test_towed_array_has_lower_bearing_error():
    bow = bearing_error_deg("BOW", 6.0, 0.8)
    towed = bearing_error_deg("TOWED", 6.0, 0.8)
    assert towed < bow


def test_ping_reaction_enters_evasive_state():
    sub = Sub(10.0, 10.0, 60.0, 0.0, "diesel_alt", random.Random(4))
    sub.hear_ping()
    assert sub.state == "EVADE"
    assert sub.heard_ping is True
    assert sub.evac_left == config.SUB_EVADE_DURATION_S


def test_torpedo_swept_collision_hits_between_frames():
    target = Target(0.7, 0.0, depth=5.0)
    torpedo = Torpedo(0.0, 0.0, 90.0, 5.0, target, 1,
                      kill_dist_nm=0.2, kill_depth_m=15.0)
    # 45 kn legt in einer Minute 0,75 NM zurueck.
    torpedo.update(60.0)
    assert torpedo.state == "HIT"
    assert target.sunk is True


def test_tma_requires_observable_maneuver():
    track = BearingTrack()
    for i in range(5):
        track.add(float(i * 3), 90.0, 0.0, float(i), 0.0)
    assert solve_tma(track) is None


def test_tma_refinement_keeps_best_rmse(monkeypatch):
    track = BearingTrack()
    for i in range(config.TMA_MIN_PTS):
        track.add(i * config.TMA_MIN_SPAN_S / (config.TMA_MIN_PTS - 1),
                  30 + i, i, 0, i * config.TMA_MIN_COURSE_CHG_DEG)
    calls = 0
    refinement_rmse = iter((9.0, 8.0, 10.0, 7.0, 6.0, 9.0))

    def candidate(pts, t0, course, speed, max_range):
        nonlocal calls
        calls += 1
        if calls <= 240:
            rmse = 10.0 if course == 0 and speed == 0 else 20.0
        else:
            rmse = next(refinement_rmse)
        return rmse, course, speed, (1.0, 1.0), .5

    monkeypatch.setattr(tma_module, "_try_candidate", candidate)
    assert solve_tma(track).rmse_deg == 6.0


def test_sub_utility_prefers_hiding_below_thermocline():
    sub = Sub(10.0, 10.0, 100.0, 0.0, "aip_modern", random.Random(8))
    scores = sub.utility_scores(20.0, 80.0, 0.2)
    assert scores["hide"] > scores["lurk"]
    assert sub.tactical_decision(20.0, 80.0, 0.2) == "hide"
    assert "hide" in sub.decision_reason


def test_damage_zone_biases_expected_compartment():
    damage = DamageModel(random.Random(11))
    hits = [damage.torpedo_hit("stern") for _ in range(30)]
    assert sum("engine" in hit for hit in hits) > 0


def test_active_ping_echo_is_delayed_by_sound_travel_time():
    world = World(seed=3)
    frigate = Ship(250.0, 250.0, speed_kn=4.0)
    sub = Sub(265.0, 250.0, 60.0, 180.0, "diesel_alt", random.Random(3))
    sonar = SonarSystem(seed=3)
    sonar.queue_ping(frigate, [sub], world, 0.0)
    assert sub.state == "EVADE"
    sonar.update(1.0, 1.0, frigate, [], world)
    assert sub.id not in sonar.contacts
    sonar.update(1.0, 40.0, frigate, [], world)
    assert sub.id in sonar.contacts


def test_ship_turning_has_rudder_and_yaw_inertia():
    ship = Ship(0.0, 0.0, course_deg=0.0, speed_kn=12.0)
    ship.target_course = 90.0
    ship.update(1.0)
    assert 0.0 < ship.rudder_angle < config.SHIP_MAX_RUDDER_DEG
    assert 0.0 < ship.course < 90.0
    assert ship.yaw_rate > 0.0
    assert ship.turn_radius_nm > 0.0


def test_ship_turning_slows_with_damaged_bridge_scale():
    ship = Ship(0.0, 0.0, course_deg=0.0, speed_kn=12.0)
    ship.target_course = 90.0
    ship.turn_rate_scale = 0.5
    ship.update(1.0)
    assert ship.rudder_angle <= config.SHIP_RUDDER_RATE_DEG_PER_S * 0.5


def test_ship_helm_state_survives_save_load():
    from src.core.game import Game

    game = Game(seed=22, start_menu=False)
    game.ship.target_course = 180.0
    game.ship.update(2.0, game.world)
    state = game.save_state()
    other = Game(seed=23, start_menu=False)
    other.load_state(state)
    assert other.ship.rudder_angle == game.ship.rudder_angle
    assert other.ship.yaw_rate == game.ship.yaw_rate


def test_focused_sonar_track_exposes_signature_analysis():
    world = World(seed=6)
    frigate = Ship(250.0, 250.0, speed_kn=4.0)
    sub = Sub(255.0, 250.0, 60.0, 180.0, "diesel_alt", random.Random(6))
    sonar = SonarSystem(seed=6)
    sonar.set_listen_bearing(90.0)
    sonar.update(1.0, 1.0, frigate, [sub], world, focus_tgt=sub)
    assert sonar.demon_analysis is not None
    assert sonar.demon_analysis["blade_rate_hz"] > 0.0
    assert sonar.signature_candidates
