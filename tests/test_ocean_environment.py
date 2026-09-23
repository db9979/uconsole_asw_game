"""Phase 1: time-varying ocean environment (tides, mixed layer, sound speed,
wind drift, seabed, hazards) and its persistence."""

import copy
import json
import math

import pytest

from src.core.game import Game
from src.world import ocean as ocean_mod
from src.world.grounding import DEFAULT_HULL_SPEC
from src.world.world import World


def test_mackenzie_reference_values():
    assert ocean_mod.mackenzie_sound_speed(10.0, 35.0, 0.0) == pytest.approx(
        1489.8, abs=0.2)
    assert ocean_mod.mackenzie_sound_speed(4.0, 35.0, 1000.0) == pytest.approx(
        1483.0, abs=0.3)


def test_tide_is_semidiurnal_bounded_and_shoals_in_shallow_water():
    world = World(seed=11)
    ocean = world.ocean
    heights = []
    for step in range(0, 25 * 60):
        ocean.clock_s = step * 60.0
        heights.append(ocean.tide_m(100.0, 100.0, 400.0))
    amplitude = ocean.m2_amplitude_m * (1 + ocean_mod.S2_TO_M2_RATIO)
    assert max(heights) <= amplitude + 1e-9 and min(heights) >= -amplitude - 1e-9
    assert max(heights) - min(heights) > 0.5 * ocean.m2_amplitude_m
    # Two high waters per lunar day.
    peaks = sum(1 for i in range(1, len(heights) - 1)
                if heights[i - 1] < heights[i] >= heights[i + 1])
    assert peaks in (2, 3)
    ocean.clock_s = 3 * 3600.0
    deep = abs(ocean.tide_m(100.0, 100.0, 2000.0))
    shallow = abs(ocean.tide_m(100.0, 100.0, 20.0))
    assert shallow > deep


def test_actual_depth_follows_tide_and_can_ground_a_ship():
    world = World(seed=12)
    ocean = world.ocean
    ocean.m2_amplitude_m = 1.4
    # Find a charted spot where the hull fits at high water only.
    hull = DEFAULT_HULL_SPEC
    spot = None
    for x in range(2, 500, 1):
        for y in range(2, 500, 1):
            charted = world.coast.physical_depth_m(x, y)
            if hull.minimum_depth_m - 0.4 < charted < hull.minimum_depth_m + 0.4:
                spot = (float(x), float(y))
                break
        if spot:
            break
    assert spot is not None
    safe_states = set()
    for step in range(0, 13 * 60, 10):
        ocean.clock_s = step * 60.0
        depth = world.physical_depth_m(*spot)
        assert depth == pytest.approx(
            world.coast.physical_depth_m(*spot) + ocean.tide_m(
                *spot, world.coast.physical_depth_m(*spot)), abs=1e-6)
        safe_states.add(depth >= hull.minimum_depth_m)
    assert safe_states == {True, False}


def test_mixed_layer_diurnal_mean_matches_base_and_wind_deepens():
    world = World(seed=13)
    ocean = world.ocean
    base = world._cell(200.0, 200.0, world._thermo)
    samples = []
    for step in range(24 * 12):
        ocean.clock_s = step * 300.0
        samples.append(ocean.mixed_layer_depth_m(base, step / 12.0, 200.0, 200.0))
    assert sum(samples) / len(samples) == pytest.approx(base, abs=2.0)
    assert max(samples) - min(samples) >= ocean_mod.MLD_DIURNAL_AMPLITUDE_M
    one = ocean_mod.OceanEnvironment(13, 500.0, lambda x, y: 500.0)
    many = ocean_mod.OceanEnvironment(13, 500.0, lambda x, y: 500.0)
    one.update(3600.0, 40.0)
    for _ in range(3600):
        many.update(1.0, 40.0)
    assert one.wind_mix_m == pytest.approx(many.wind_mix_m, rel=1e-9)
    assert one.wind_mix_m > 10.0
    one.update(24 * 3600.0, 5.0)
    assert one.wind_mix_m < 5.0


def test_sound_speed_profile_has_isothermal_layer_and_deep_minimum():
    world = World(seed=14)
    mld = world.thermocline_depth_m(250.0, 250.0)
    near = world.sound_speed_m_s(mld * 0.5, 250.0, 250.0)
    top = world.sound_speed_m_s(1.0, 250.0, 250.0)
    below = world.sound_speed_m_s(mld + 150.0, 250.0, 250.0)
    assert near >= top - 0.2          # pressure term: slight increase in layer
    assert below < near               # thermocline: speed drops below the layer
    assert 1450.0 < world.mean_sound_speed_m_s(250.0, 250.0) < 1530.0


def test_wind_drift_is_three_percent_and_deflected_right():
    u, v = ocean_mod.OceanEnvironment.wind_drift_kn(0.0, 20.0)   # from north
    assert math.hypot(u, v) == pytest.approx(0.6)
    # Blowing towards south (180) deflected 20 degrees right -> 200 degrees.
    assert math.degrees(math.atan2(u, v)) % 360.0 == pytest.approx(200.0)


def test_seabed_and_hazards_are_seeded_bounded_and_rocks_shoal():
    first, second = World(seed=15), World(seed=15)
    assert first.ocean._sediment == second.ocean._sediment
    assert first.ocean.hazards == second.ocean.hazards
    kinds = {cell for row in first.ocean._sediment for cell in row}
    assert kinds <= set(ocean_mod.SEDIMENTS)
    assert len(first.ocean.hazards) <= ocean_mod.MAX_HAZARDS
    rocks = [h for h in first.ocean.hazards if h.kind == "rock"]
    assert all(h.top_depth_m >= ocean_mod.ROCK_MIN_TOP_M for h in rocks)
    for rock in rocks:
        assert first.depth_m(rock.x_nm, rock.y_nm) <= rock.top_depth_m + 1e-9
    assert World(seed=16).ocean.hazards != first.ocean.hazards


@pytest.mark.parametrize("sediment", sorted(ocean_mod.SEDIMENTS))
def test_rayleigh_bottom_loss_is_finite_and_rock_reflects_best(sediment):
    loss = ocean_mod.rayleigh_bottom_loss_db(sediment, 20.0)
    assert 0.0 <= loss < 40.0
    assert ocean_mod.rayleigh_bottom_loss_db("rock", 20.0) <= loss + 1e-9


def test_ocean_state_round_trips_and_rejects_malformed():
    game = Game(seed=1501, start_menu=False, audio_enabled=False)
    for _ in range(200):
        game.update(0.5)
    state = json.loads(json.dumps(game.save_state()))
    assert state["world"]["ocean"]["clock_s"] > 0.0
    restored = Game(seed=1, start_menu=False, audio_enabled=False)
    assert restored._load_save_data(copy.deepcopy(state))
    assert restored.world.thermocline_depth_m(123.0, 321.0) == \
        game.world.thermocline_depth_m(123.0, 321.0)
    assert restored.world.depth_m(123.0, 321.0) == game.world.depth_m(123.0, 321.0)
    for mutation in (lambda o: o.update(clock_s=-1.0),
                     lambda o: o.update(wind_mix_m=1e6),
                     lambda o: o.pop("clock_s"),
                     lambda o: o.update(extra=0)):
        broken = copy.deepcopy(state)
        mutation(broken["world"]["ocean"])
        assert not restored._load_save_data(broken)
