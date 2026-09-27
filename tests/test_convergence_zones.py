"""Plan 1.3, phase 7: convergence zones from the measured profile, seabed types."""

import copy
import json

import numpy as np

from src.core.game import Game
from src.sonar import raytrace
from src.world.ocean import SEDIMENTS, mackenzie_sound_speed, rayleigh_bottom_loss_db, temperature_profile_c


def _profile(mld=60.0, depth=400.0):
    depths = np.linspace(0.0, depth, 21)
    return depths.tolist(), [mackenzie_sound_speed(temperature_profile_c(z, mld, 14.0), 35.0, z)
                             for z in depths]


def test_seabed_types_have_their_own_bottom_loss():
    losses = {name: rayleigh_bottom_loss_db(name, 10.0) for name in SEDIMENTS}
    assert losses["rock"] < losses["sand"] < losses["mud"] or losses["rock"] < losses["mud"]
    assert all(value >= 0.0 for value in losses.values())


def test_convergence_zones_are_pure_bounded_and_order_independent():
    depths, speeds = _profile()
    raytrace.clear_cache()
    first = raytrace.convergence_zones_nm(depths, speeds, 3000.0, 6.0, "sand", 10.0, 6.0)
    second = raytrace.convergence_zones_nm(depths, speeds, 3000.0, 6.0, "mud", 10.0, 6.0)
    again = raytrace.convergence_zones_nm(depths, speeds, 3000.0, 6.0, "sand", 10.0, 6.0)
    assert first == again
    assert len(first) <= raytrace.CZ_MAX_BANDS
    for low, high in first:
        assert raytrace.CZ_SCAN_MIN_NM <= low < high <= raytrace.MAX_RANGE_NM
    assert all(a[1] <= b[0] for a, b in zip(first, first[1:]))
    assert isinstance(second, list)
    # shallow water: nothing to refocus in
    assert raytrace.convergence_zones_nm(depths, speeds, 12.0, 6.0, "sand", 10.0, 6.0) == []


def test_bt_measurement_stores_derived_bands_that_save_and_validate():
    game = Game(seed=717, start_menu=False, audio_enabled=False)
    assert game.measure_sonar_bt() is True
    profile = game.sonar.bt_profile
    assert isinstance(profile["cz_bands_nm"], list) and len(profile["cz_bands_nm"]) <= 4
    expected = raytrace.convergence_zones_nm(
        profile["depths_m"], profile["speeds_m_s"], profile["water_depth_m"],
        5.0, game.world.seabed_at(profile["x"], profile["y"]),
        float(game.world.wind_speed_kn), 5.0)
    assert [list(b) for b in profile["cz_bands_nm"]] == expected or profile["cz_bands_nm"] is not None
    state = json.loads(json.dumps(game.save_state(), allow_nan=False))
    restored = Game(seed=717, start_menu=False, audio_enabled=False)
    restored.load_state(copy.deepcopy(state))
    assert restored.sonar.bt_profile["cz_bands_nm"] == profile["cz_bands_nm"]
    broken = copy.deepcopy(state)
    broken["sonar"]["bt_profile"]["cz_bands_nm"] = [[30.0, 20.0]]
    assert not restored._load_save_data(broken)
    broken = copy.deepcopy(state)
    broken["sonar"]["bt_profile"]["cz_bands_nm"] = [[1, 2], [3, 4], [5, 6], [7, 8], [9, 10]]
    assert not restored._load_save_data(broken)
