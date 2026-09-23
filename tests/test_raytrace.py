"""Phase 4: ray-traced transmission loss."""

import math

import numpy as np
import pytest

from src.sonar import propagation, raytrace
from src.world.ocean import rayleigh_bottom_loss_db
from src.world.world import World


def spherical(nm):
    return 20.0 * math.log10(nm * 1852.0)


def test_homogeneous_deep_water_is_spherical_plus_surface_image():
    table = raytrace.trace_table(50.0, [0.0, 4000.0], [1500.0, 1500.0],
                                 4000.0, "mud", 0.0)
    for nm in (1.0, 5.0, 10.0):
        excess = raytrace.lookup_tl_db(table, 100.0, nm, 50.0, 4000.0) - spherical(nm)
        # Incoherent sum with the surface-reflected image: up to ~3 dB gain.
        assert -5.0 < excess < 1.0


def _mixed_layer_profile(mld=60.0):
    from src.world.ocean import mackenzie_sound_speed, temperature_profile_c
    depths = np.linspace(0.0, 400.0, 21)
    return depths, [mackenzie_sound_speed(temperature_profile_c(z, mld, 14.0), 35.0, z)
                    for z in depths]


def test_surface_duct_and_shadow_zone_emerge_in_deep_water():
    depths, speeds = _mixed_layer_profile(60.0)
    table = raytrace.trace_table(5.0, depths, speeds, 3000.0, "mud", 5.0)
    in_duct = raytrace.lookup_tl_db(table, 100.0, 3.0, 30.0, 3000.0)
    shadow = raytrace.lookup_tl_db(table, 100.0, 3.0, 250.0, 3000.0)
    assert shadow - in_duct > 8.0


def test_bottom_reflection_depends_on_sediment():
    assert rayleigh_bottom_loss_db("rock", 10.0) < rayleigh_bottom_loss_db("sand", 10.0)
    assert rayleigh_bottom_loss_db("sand", 10.0) < rayleigh_bottom_loss_db("silt", 10.0)
    depths, speeds = _mixed_layer_profile(60.0)
    hard = raytrace.trace_table(5.0, depths, speeds, 300.0, "gravel", 5.0)
    soft = raytrace.trace_table(5.0, depths, speeds, 300.0, "silt", 5.0)
    assert raytrace.lookup_tl_db(hard, 100.0, 20.0, 100.0, 300.0) < \
        raytrace.lookup_tl_db(soft, 100.0, 20.0, 100.0, 300.0) - 1.0


def test_rough_surface_costs_high_frequencies_more():
    depths, speeds = _mixed_layer_profile(80.0)
    calm = raytrace.trace_table(5.0, depths, speeds, 3000.0, "mud", 0.0)
    windy = raytrace.trace_table(5.0, depths, speeds, 3000.0, "mud", 30.0)
    loss = lambda table, band: raytrace.lookup_tl_db(table, band, 15.0, 30.0, 3000.0)
    assert loss(windy, 6400.0) - loss(calm, 6400.0) > loss(windy, 100.0) - loss(calm, 100.0)


def test_ray_excess_is_pure_and_cache_bounded():
    world = World(seed=41)
    raytrace.clear_cache()
    first = propagation.ray_excess_db(world, 200.0, 200.0, 5.0, 212.0, 203.0, 80.0, 100.0)
    raytrace.clear_cache()
    second = propagation.ray_excess_db(world, 200.0, 200.0, 5.0, 212.0, 203.0, 80.0, 100.0)
    assert first == second
    assert raytrace.build_count >= 1
    for index in range(raytrace.CACHE_SIZE + 5):
        raytrace.cached_table((5.0, 10.0 * index, 12.0, 500.0, "sand", 5.0),
                              propagation._profile_from_key)
    assert len(raytrace._cache) <= raytrace.CACHE_SIZE


def test_anchor_makes_reference_environment_zero_at_reference_range():
    table = raytrace.cached_table(propagation.RAY_REFERENCE_KEY,
                                  propagation._profile_from_key)
    excess = raytrace.lookup_tl_db(
        table, 100.0, propagation.RAY_REFERENCE_RANGE_NM,
        propagation.RAY_REFERENCE_RECEIVER_M, propagation.RAY_REFERENCE_KEY[3]) \
        - spherical(propagation.RAY_REFERENCE_RANGE_NM) - propagation.ray_anchor_db()
    assert excess == pytest.approx(0.0, abs=1e-9)


def test_lookup_extends_cylindrically_beyond_the_table():
    depths, speeds = _mixed_layer_profile(60.0)
    table = raytrace.trace_table(5.0, depths, speeds, 500.0, "sand", 5.0)
    edge = raytrace.MAX_RANGE_NM
    near = raytrace.lookup_tl_db(table, 100.0, edge * 1.001, 50.0, 500.0)
    far = raytrace.lookup_tl_db(table, 100.0, edge * 2.0, 50.0, 500.0)
    assert far - near == pytest.approx(10.0 * math.log10(2.0 / 1.001), abs=0.2)
