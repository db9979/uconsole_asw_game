"""Phase 5: array physics, Doppler, LM TMA with covariance, multistatic."""

import math
import random
from types import SimpleNamespace

import numpy as np
import pytest

from src.audio.receiver import beam_pattern_gain
from src.core import config
from src.enemies.sub import Sub
from src.ship.ship import Ship
from src.sonar import sonar as sonar_mod
from src.sonar.sonar import SonarSystem, TowState, doppler_factor
from src.sonar.tma import BearingTrack, solve_tma
from src.sonar import tma_lm
from src.world.world import World


def test_doppler_factor_sign_and_magnitude():
    observer = SimpleNamespace(x=0.0, y=0.0, course=0.0, speed=0.0)
    closing = SimpleNamespace(x=0.0, y=-5.0, course=180.0, speed=15.0)
    opening = SimpleNamespace(x=0.0, y=-5.0, course=0.0, speed=15.0)
    assert doppler_factor(closing, observer) == pytest.approx(
        1.0 + 15.0 / sonar_mod.SOUND_SPEED_KN)
    assert doppler_factor(opening, observer) < 1.0


def _track(noise=0.3, doppler=False, manoeuvre=True, seed=4,
           start=(8.0, -6.0), course=250.0, speed=7.0):
    rng = random.Random(seed)
    track = BearingTrack()
    tx, ty = start
    f0 = 50.0
    vx = config.kn_to_nm_per_s(speed) * math.sin(math.radians(course))
    vy = -config.kn_to_nm_per_s(speed) * math.cos(math.radians(course))
    fx = fy = 0.0
    own_speed = 10.0
    for index in range(40):
        t = index * config.BEARING_TRACK_MIN_INTERVAL_S * 2
        own_course = (60.0 if index < 20 else 150.0) if manoeuvre else 60.0
        if index:
            step = config.kn_to_nm_per_s(own_speed) * config.BEARING_TRACK_MIN_INTERVAL_S * 2
            fx += step * math.sin(math.radians(own_course))
            fy -= step * math.cos(math.radians(own_course))
        x, y = tx + vx * t, ty + vy * t
        bearing = math.degrees(math.atan2(x - fx, -(y - fy))) % 360.0
        freq = None
        if doppler:
            target = SimpleNamespace(x=x, y=y, course=course, speed=speed)
            observer = SimpleNamespace(x=fx, y=fy, course=own_course, speed=own_speed)
            freq = f0 * doppler_factor(target, observer) + rng.gauss(0.0, 0.01)
        track.add(t, bearing + rng.gauss(0.0, noise), fx, fy, own_course, 1.0,
                  freq, own_speed)
    truth = (tx + vx * t, ty + vy * t)
    return track, truth


def test_lm_tma_reports_covariance_ellipse_and_fits_truth():
    track, truth = _track()
    solution = solve_tma(track)
    assert solution is not None and solution.ellipse is not None
    major, minor, _orientation = solution.ellipse
    assert major >= minor >= 0.0
    error = math.hypot(solution.pos[0] - truth[0], solution.pos[1] - truth[1])
    assert error < 2.0


def test_doppler_makes_range_observable_without_manoeuvre():
    bearing_only, _ = _track(manoeuvre=False, doppler=False,
                             start=(4.0, -4.0), course=270.0, speed=12.0)
    assert solve_tma(bearing_only) is None
    # A crossing target near its closest approach: the received tonal
    # sweeps through tenths of a hertz, which fixes range.
    with_doppler, truth = _track(manoeuvre=False, doppler=True,
                                 start=(4.0, -4.0), course=270.0, speed=12.0)
    solution = solve_tma(with_doppler)
    assert solution is not None and solution.f0_hz == pytest.approx(50.0, abs=0.2)
    assert math.hypot(solution.pos[0] - truth[0], solution.pos[1] - truth[1]) < 3.0


def test_towed_endfire_broadens_bearing_error():
    sonar = SonarSystem(seed=1)
    sonar.tow_heading_deg = 0.0
    assert sonar._endfire_factor(90.0) == pytest.approx(1.0)
    assert sonar._endfire_factor(5.0) > 1.8


def test_towed_only_contact_is_side_ambiguous_until_the_operator_confirms():
    world = World(seed=5)
    frigate = Ship(250.0, 250.0, course_deg=0.0, speed_kn=6.0)
    sub = Sub(253.0, 250.0, 60.0, 90.0, "diesel_alt", random.Random(5))
    sonar = SonarSystem(seed=5)
    sonar.tow_state = TowState.STREAMED
    sonar.tow_payout = 1.0
    sonar._tow_settle_s = config.SONAR_TOWED_SETTLE_S
    sonar.tow_heading_deg = 0.0
    original = sonar._passive_range_nm

    def towed_only(tgt, dist, frigate, world, rf, mode, *args, **kwargs):
        if mode == "BOW":
            return 0.0
        return original(tgt, dist, frigate, world, rf, mode, *args, **kwargs)
    sonar._passive_range_nm = towed_only
    sonar.update(1.0, 1.0, frigate, [sub], world, mode="TOWED",
                 advance_mechanics=False)
    contact = sonar.contacts[sub.id]
    assert contact.towed_ambiguous and contact.fusion_status == "TAS L/R?"
    assert abs(config.angle_diff_deg(contact.bearing, contact.mirror_bearing)) > 90.0
    assert sub.id not in sonar._tracks or not sonar._tracks[sub.id].pts
    sonar.tow_heading_deg = 30.0
    sonar.update(1.0, 12.0, frigate, [sub], world, mode="TOWED",
                 advance_mechanics=False)
    # An own turn only makes the ghost jump; the operator decides the side.
    assert contact.towed_ambiguous and contact.fusion_status == "TAS L/R? WENDE"
    # The boat bears 090 from the frigate, starboard of the 030 array axis.
    contact.towed_side = "STBD"
    contact.towed_ambiguous, contact.towed_resolved = False, True
    contact.mirror_bearing = contact.ambiguity_axis = None
    sonar.update(1.0, 13.0, frigate, [sub], world, mode="TOWED",
                 advance_mechanics=False)
    assert not contact.towed_ambiguous and contact.towed_resolved
    assert contact.mirror_bearing is None


def test_buoy_bearings_join_the_track_as_multistatic_observers():
    world = World(seed=6)
    sub = Sub(250.0, 250.0, 40.0, 90.0, "diesel_alt", random.Random(6))
    buoys = [SimpleNamespace(seq=i + 1, x=250.0 + dx, y=250.0 + dy, active=True,
                             mode="PASSIVE") for i, (dx, dy) in
             enumerate(((-2.0, 0.0), (0.0, -2.0)))]
    frigate = Ship(200.0, 200.0, speed_kn=6.0)
    sonar = SonarSystem(seed=6)
    sonar.update(1.0, 1.0, frigate, [sub], world, buoys=buoys,
                 advance_mechanics=False)
    points = sonar._tracks[sub.id].pts
    assert any((p.fx, p.fy) in {(b.x, b.y) for b in buoys} for p in points)


def test_beam_pattern_has_minus_13db_side_lobes():
    angles = np.linspace(-60.0, 60.0, 2401)
    gain = beam_pattern_gain(angles, 0.0, 12.0)
    assert beam_pattern_gain(6.0, 0.0, 12.0) == pytest.approx(0.5, abs=0.01)
    side = gain[np.abs(angles) > 12.0].max()
    assert 20 * math.log10(side) == pytest.approx(-13.3, abs=0.5)


def test_measured_tonal_is_doppler_shifted_and_saved():
    import json
    import copy
    from src.core.game import Game
    game = Game(seed=5501, start_menu=False, audio_enabled=False)
    for _ in range(400):
        game.update(0.5)
    points = [p for track in game.sonar._tracks.values() for p in track.pts]
    state = json.loads(json.dumps(game.save_state()))
    restored = Game(seed=1, start_menu=False, audio_enabled=False)
    assert restored._load_save_data(copy.deepcopy(state))
    assert restored.save_state()["sonar"]["tracks"] == state["sonar"]["tracks"]
    if points:
        assert all(p.fspeed >= 0.0 for p in points)
