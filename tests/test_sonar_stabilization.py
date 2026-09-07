import math
import random
from types import SimpleNamespace

import pytest

from src.core import config
from src.enemies.sub import Sub
from src.ship.ship import Ship
from src.sonar.sonar import Contact, SonarSystem
from src.sonar.tma import BearingTrack, solve_tma


def _contact_outputs(measurements, dt=.25):
    contact = Contact(1, 1, "passiv", "sub")
    outputs = []
    for index, bearing in enumerate(measurements):
        contact.update_passive(
            bearing, 1.0, .8, "", index * dt,
            bearing_uncertainty_deg=2.0)
        outputs.append(contact.passive_bearing)
    return contact, outputs


def test_contact_filter_suppresses_jitter_without_mutating_raw_measurements():
    measurements = [100.0 + (6.0 if (index // 8) % 2 else -6.0)
                    for index in range(80)]
    contact, outputs = _contact_outputs(measurements)

    raw_steps = [abs(config.angle_diff_deg(after, before))
                 for before, after in zip(measurements, measurements[1:])]
    filtered_steps = [abs(config.angle_diff_deg(after, before))
                      for before, after in zip(outputs, outputs[1:])]
    assert sum(filtered_steps) / len(filtered_steps) < \
        sum(raw_steps) / len(raw_steps) * .25
    assert max(filtered_steps) < max(raw_steps) * .1
    expected_raw = [measurements[index]
                    for index in range(0, len(measurements), 8)]
    assert [row[1] for row in contact.raw_bearings] == expected_raw
    assert len(set(outputs[9:16])) > 1
    assert contact.bearing_uncertainty_deg > 0.0
    assert abs(contact._bearing_filter_rate_deg_s) <= \
        config.SONAR_BEARING_RATE_MAX_DEG_S


def test_contact_filter_crosses_north_on_short_arc_and_remains_responsive():
    _, north = _contact_outputs([357.0, 359.0, 1.0, 3.0, 5.0], dt=2.0)
    assert all(abs(config.angle_diff_deg(after, before)) < 10.0
               for before, after in zip(north, north[1:]))
    assert 0.0 < north[-1] < 5.0

    _, turn = _contact_outputs([0.0] * 16 + [30.0] * 64)
    assert abs(config.angle_diff_deg(turn[-1], 30.0)) < 2.0


def test_contact_filter_is_deterministic():
    measurements = [359.0, 1.0, 4.0, 2.0, 8.0, 12.0]
    first, first_outputs = _contact_outputs(measurements)
    second, second_outputs = _contact_outputs(measurements)
    assert first_outputs == second_outputs
    assert first.raw_bearings == second.raw_bearings
    assert first.bearing_uncertainty_deg == second.bearing_uncertainty_deg


def test_confirmed_array_fusion_uses_inverse_variance():
    ship = Ship(250, 250, speed_kn=0)
    world = SimpleNamespace(sea_state=0,
                            thermocline_depth_m=lambda x, y: 100)
    sub = Sub(252, 250, 40, 0, "diesel_alt", random.Random(5))
    sonar = SonarSystem(5)
    sonar.tow_state = sonar.STREAMED
    sonar.tow_payout = 1.0
    sonar._tow_settle_s = config.SONAR_TOWED_SETTLE_S
    sonar._observed_bearing = lambda target, true, frigate, quality, mode, t: \
        10.0 if mode == "BOW" else 14.0

    sonar.update(.25, .25, ship, [sub], world)

    contact = sonar.contacts[sub.id]
    bow = contact.array_observations["BOW"]
    towed = contact.array_observations["TOWED"]
    assert contact.fusion_status == "BESTAETIGT"
    assert abs(config.angle_diff_deg(contact.raw_bearing, towed["bearing"])) < \
        abs(config.angle_diff_deg(contact.raw_bearing, bow["bearing"]))
    assert contact.raw_bearing == pytest.approx(13.6, abs=.2)
    assert contact.raw_bearings[0][1] == contact.raw_bearing
    assert contact.raw_bearings[0][2] < min(
        bow["uncertainty_deg"], towed["uncertainty_deg"])


def test_four_second_runtime_track_reaches_normal_tma_span_with_uncertainty():
    track = BearingTrack()
    for t in range(0, 321):
        fx = t / 180.0 * 3.0
        fy = 0.0
        bearing = math.degrees(math.atan2(10.0 - fx, 20.0)) % 360.0
        track.add(float(t), bearing, fx, fy, t / 9.0,
                  uncertainty_deg=1.0)

    assert len(track.pts) == config.BEARING_TRACK_MAX_PTS
    assert 75 <= len(track.pts) <= 90
    assert track.span_s() >= config.TMA_MIN_SPAN_S
    assert all(b.t - a.t >= 4.0 for a, b in zip(track.pts, track.pts[1:]))
    assert all(point.uncertainty_deg == 1.0 for point in track.pts)
    assert solve_tma(track) is not None


def test_tma_inverse_variance_and_robust_weighting_limit_an_uncertain_outlier():
    solutions = []
    for outlier_sigma in (1.0, 20.0):
        track = BearingTrack()
        for t in range(0, int(config.TMA_MIN_SPAN_S) + 1, 10):
            fx = t / 60.0
            bearing = math.degrees(math.atan2(10.0 - fx, 20.0)) % 360.0
            if t == 90:
                bearing = (bearing + 15.0) % 360.0
            track.add(float(t), bearing, fx, 0.0, t / 9.0,
                      uncertainty_deg=outlier_sigma if t == 90 else 1.0)
        solutions.append(solve_tma(track))

    certain_error = math.hypot(solutions[0].pos[0] - 10.0,
                               solutions[0].pos[1] + 20.0)
    uncertain_error = math.hypot(solutions[1].pos[0] - 10.0,
                                 solutions[1].pos[1] + 20.0)
    assert uncertain_error < .25
    assert uncertain_error < certain_error


def test_low_quality_tma_does_not_move_an_acquired_fix():
    contact = Contact(1, 1, "passiv", "sub")
    contact._fx = contact._fy = 0.0
    good = SimpleNamespace(pos=(3.0, -4.0), course=40.0, speed=8.0,
                           quality=.8)
    poor = SimpleNamespace(pos=(20.0, 10.0), course=200.0, speed=18.0,
                           quality=config.TMA_RANGE_MIN_QUALITY - .01)
    contact.update_tma(good, 180.0)
    state = (contact.tma_pos, contact.tma_course, contact.tma_speed,
             contact.tma_quality, contact.observed_x, contact.observed_y,
             contact.bearing, contact.range_est, contact.range_seen)

    contact.update_tma(poor, 182.0)
    contact.update_passive(90.0, 1.0, .8, "", 184.0)

    assert (contact.tma_pos, contact.tma_course, contact.tma_speed,
            contact.tma_quality, contact.observed_x, contact.observed_y,
            contact.bearing, contact.range_est, contact.range_seen) == state
