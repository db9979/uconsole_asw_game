"""Acoustics regressions from the code review of 1.3.204 (package C)."""

import math

import numpy as np
import pytest

from src.audio.receiver import AcousticReceiver
from src.physics import ship_dynamics
from src.sonar import equation, propagation, raytrace


def _excess(table, range_nm, receiver_m, water_m, band=400.0):
    return (raytrace.lookup_tl_db(table, band, range_nm, receiver_m, water_m)
            - 20.0 * math.log10(range_nm * raytrace.NM_M))


def test_refracted_rays_leave_their_turning_depth():
    # Rays used to flip at their turning depth on every step and freeze there.
    depths, speeds = propagation._profile_from_key((5.0, 60.0, 20.0, 4000.0, "sand", 10.0))
    picture = raytrace.ray_picture(depths, speeds, 4000.0, 50.0, "sand", 10.0, 60.0)
    for angle, path in zip(raytrace.PICTURE_RAYS_DEG, picture["rays"]):
        if angle == 0.0:
            continue
        tail = [depth for _, depth in path[-10:]]
        assert max(tail) - min(tail) > 50.0, angle


def test_deep_water_has_a_shadow_zone_and_a_convergence_zone():
    depths, speeds = propagation._profile_from_key((150.0, 60.0, 20.0, 4000.0, "mud", 10.0))
    table = raytrace.trace_table(150.0, depths, speeds, 4000.0, "mud", 10.0)
    assert _excess(table, 7.0, 200.0, 4000.0) > 40.0
    assert _excess(table, 30.0, 200.0, 4000.0) < 0.0


def test_shallow_water_rays_are_not_cut_by_a_bounce_count():
    # Twelve boundary hits used to end every ray: a hard shadow beyond about 25 NM.
    depths, speeds = propagation._profile_from_key((30.0, 40.0, 15.0, 100.0, "sand", 10.0))
    table = raytrace.trace_table(30.0, depths, speeds, 100.0, "sand", 10.0)
    for range_nm in (30.0, 50.0, 70.0):
        assert _excess(table, range_nm, 50.0, 100.0) < 10.0


def _reverb(lambert_mu_db, distance_nm, water_m=3000.0, sensor_m=7.0):
    return equation.reverberation_level_db(
        source_level_db=220.0, distance_nm=distance_nm, pulse="CW", beamwidth_deg=10.0,
        water_depth_m=water_m, lambert_mu_db=lambert_mu_db, wind_kn=10.0,
        sensor_depth_m=sensor_m)


def test_the_seabed_does_not_reverberate_before_the_echo_reaches_it():
    # 1 NM in 3000 m of water: the range gate has not reached the bottom yet.
    assert _reverb(-27.0, 1.0) == pytest.approx(_reverb(-10.0, 1.0))
    # Beyond the water depth the bottom adds to the level.
    assert _reverb(-10.0, 5.0) > _reverb(-27.0, 5.0)


def test_own_line_follows_the_shaft_rpm():
    for speed in (8.0, 20.0, 31.0):
        rps = ship_dynamics.HULL.steady_rps(speed * ship_dynamics.KN)
        assert ship_dynamics.own_blade_line_hz(speed) == pytest.approx(
            rps * ship_dynamics.OWN_PROPELLER_BLADES)
    assert 9.0 < ship_dynamics.own_blade_line_hz(20.0) < 10.5


def _demon(blades):
    receiver = AcousticReceiver(seed=1)
    source = dict(bearing=10.0, level=0.8, seed=5,
                  lines=[(15.0, 1.0, 1.5), (30.0, .5, 1.2)],
                  broadband=dict(level=.5, low_hz=30, high_hz=250))
    if blades:
        source["blades"] = blades
    for _ in range(80):
        receiver.update([source], 10.0, 12.0, 0.1, 2, 5.0)
    return np.asarray(receiver.demon_spectrum)


def test_demon_shows_the_shaft_line_of_a_propeller():
    with_blades = _demon(5)
    without = _demon(None)
    shaft_bin = 3 - 1          # 15 Hz blade line / 5 blades, 1 Hz bins from 1 Hz
    assert with_blades[shaft_bin] > 5.0 * without[shaft_bin]
    assert with_blades[shaft_bin] > 0.1
