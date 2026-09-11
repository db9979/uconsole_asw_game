import dataclasses
import math
import random
from types import SimpleNamespace

import pytest

from src.core.game import Game
from src.data.catalog import CATALOG
from src.sensors.platform import PlatformSensorSuite
from src.ship.ship import Ship
from src.sonar import propagation
from src.sonar.sonar import SonarSystem
from src.ui import sonar_view


def calculate(**changes):
    values = dict(
        source_x_nm=0.0, source_y_nm=0.0, source_depth_m=20.0,
        target_x_nm=20.0, target_y_nm=0.0, target_depth_m=40.0,
        frequency_hz=100.0, thermocline_m=80.0, water_depth_m=500.0,
        sea_state=2, terrain_blocked=lambda *_args: False,
    )
    values.update(changes)
    return propagation.propagate(**values)


def test_profile_retains_exact_bt_truth_curve_and_bt_noise_contract():
    profile = propagation.synthetic_sound_speed_profile(80.0, 300.0)
    assert len(profile.depths_m) == len(profile.speeds_m_s) == 21
    assert profile.depths_m[0] == 0.0 and profile.depths_m[-1] == 300.0
    assert profile.speeds_m_s == tuple(
        1504.0 - .018 * min(depth, 80.0) + .012 * max(0.0, depth - 80.0)
        for depth in profile.depths_m)

    draws = iter((2.0, *([.1] * 21)))
    sonar = SonarSystem(7)
    sonar.rng = SimpleNamespace(uniform=lambda low, high: next(draws))
    world = SimpleNamespace(depth_m=lambda _x, _y: 300.0,
                            thermocline_depth_m=lambda _x, _y: 80.0,
                            sea_state=2)
    assert sonar.measure_environment(world, SimpleNamespace(x=1.0, y=2.0), 3.0)
    measured = sonar.bt_profile
    truth = propagation.synthetic_sound_speed_profile(82.0, 300.0)
    assert measured["thermocline_m"] == 82.0
    assert measured["depths_m"] == list(truth.depths_m)
    assert measured["speeds_m_s"] == pytest.approx(
        [speed + .1 for speed in truth.speeds_m_s])
    with pytest.raises(StopIteration):
        next(draws)


@pytest.mark.parametrize(("field", "value"), [
    ("source_x_nm", True), ("source_y_nm", float("nan")),
    ("target_x_nm", float("inf")), ("source_depth_m", -1.0),
    ("target_depth_m", 501.0), ("frequency_hz", 101.0),
    ("thermocline_m", False), ("water_depth_m", 0.0),
    ("sea_state", 2.5), ("sea_state", True),
    ("terrain_blocked", 4),
])
def test_invalid_values_are_rejected(field, value):
    with pytest.raises(ValueError):
        calculate(**{field: value})


def test_range_and_frequency_loss_are_monotone():
    range_losses = [calculate(target_x_nm=distance).best_path.loss_db
                    for distance in (1.0, 10.0, 50.0, 100.0)]
    frequency_losses = [calculate(frequency_hz=frequency).best_path.loss_db
                        for frequency in propagation.CANONICAL_FREQUENCY_BANDS_HZ]
    assert range_losses == sorted(range_losses)
    assert frequency_losses == sorted(frequency_losses)
    assert len(set(frequency_losses)) == len(frequency_losses)


def test_best_path_publishes_relative_audio_curve_without_more_terrain_queries():
    calls = 0

    def terrain(*_args):
        nonlocal calls
        calls += 1
        return False

    result = calculate(target_x_nm=40.0, terrain_blocked=terrain)
    assert calls == 7
    assert tuple(frequency for frequency, _gain in result.spectral_gains) == (
        100.0, 400.0, 1600.0)
    assert result.spectral_gains[0] == (100.0, 1.0)
    assert 0 < result.spectral_gains[2][1] < result.spectral_gains[1][1] < 1


def test_direct_and_bounded_multipath_have_stable_order_and_clear_segments():
    result = calculate()
    assert result.best_path.kind is propagation.PathKind.DIRECT
    assert 1 <= len(result.paths) <= propagation.MAX_PATHS == 4
    assert {path.kind for path in result.paths} == set(propagation.PathKind)
    assert all(1 <= len(path.segments) <= propagation.MAX_SEGMENTS_PER_PATH
               for path in result.paths)
    assert all(segment.terrain_clear for path in result.paths
               for segment in path.segments)
    assert 0.0 <= result.reverberation_db <= 24.0
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.reverberation_db = 0.0


def test_shallow_profiles_do_not_publish_duplicate_path_geometry():
    result = calculate(source_depth_m=.5, target_depth_m=.5,
                       thermocline_m=.5, water_depth_m=1.0)
    point_sets = [tuple((segment.start, segment.end) for segment in path.segments)
                  for path in result.paths]
    assert len(point_sets) == len(set(point_sets))

    coincident = calculate(source_depth_m=0.0, target_x_nm=0.0,
                           target_depth_m=0.0, thermocline_m=0.0,
                           water_depth_m=1.0)
    assert [path.kind for path in coincident.paths] == [
        propagation.PathKind.DIRECT]

    straight = calculate(source_depth_m=0.0, target_x_nm=40.0,
                         target_depth_m=0.0, thermocline_m=0.0,
                         water_depth_m=1.0)
    assert [path.kind for path in straight.paths] == [
        propagation.PathKind.DIRECT]


def test_reported_convergence_zones_focus_only_the_refracted_path():
    outside = calculate(target_x_nm=39.0)
    inside = calculate(target_x_nm=40.0)
    outside_refracted = next(
        path for path in outside.paths if path.kind is propagation.PathKind.REFRACTED)
    inside_refracted = next(
        path for path in inside.paths if path.kind is propagation.PathKind.REFRACTED)
    outside_direct = next(
        path for path in outside.paths if path.kind is propagation.PathKind.DIRECT)
    inside_direct = next(
        path for path in inside.paths if path.kind is propagation.PathKind.DIRECT)
    assert inside_refracted.loss_db < outside_refracted.loss_db
    assert inside_direct.loss_db > outside_direct.loss_db


def test_ridge_can_block_direct_ray_while_a_bounded_multipath_survives():
    calls = []

    def ridge(x1, _y1, d1, x2, _y2, d2):
        calls.append((x1, d1, x2, d2))
        return {x1, x2} == {0.0, 20.0} and min(d1, d2) > 10.0

    result = calculate(terrain_blocked=ridge)
    assert propagation.PathKind.DIRECT not in {path.kind for path in result.paths}
    assert propagation.PathKind.SURFACE in {path.kind for path in result.paths}
    assert len(calls) == 7  # one direct and two segments for each other candidate
    assert calculate(terrain_blocked=lambda *_args: True).paths == ()


def test_endpoint_reversal_preserves_path_ranking_loss_and_travel_time():
    forward = calculate()
    reverse = calculate(source_x_nm=20.0, source_depth_m=40.0,
                        target_x_nm=0.0, target_depth_m=20.0)
    assert [path.kind for path in forward.paths] == [path.kind for path in reverse.paths]
    assert [path.loss_db for path in forward.paths] == pytest.approx(
        [path.loss_db for path in reverse.paths])
    assert [path.travel_time_s for path in forward.paths] == pytest.approx(
        [path.travel_time_s for path in reverse.paths])


def test_travel_time_uses_profile_and_reverberation_is_deterministic_and_bounded():
    shallow = calculate(thermocline_m=40.0)
    deep = calculate(thermocline_m=150.0)
    assert shallow.best_path.travel_time_s != deep.best_path.travel_time_s
    assert calculate() == calculate()
    assert calculate(sea_state=6).reverberation_db > calculate(sea_state=0).reverberation_db


def test_propagation_never_reads_or_advances_global_random_state():
    before = random.getstate()
    for frequency in propagation.CANONICAL_FREQUENCY_BANDS_HZ:
        calculate(frequency_hz=frequency)
    assert random.getstate() == before


def test_representative_workload_has_a_fixed_query_budget():
    calls = 0

    def terrain(*_args):
        nonlocal calls
        calls += 1
        return False

    results = [calculate(target_x_nm=1.0 + index, terrain_blocked=terrain)
               for index in range(100)]
    assert len(results) == 100
    assert calls == 100 * 7
    assert all(len(result.paths) <= 4 for result in results)


def test_catalog_passive_propagation_runs_only_on_sensor_scan_cadence(monkeypatch):
    suite = PlatformSensorSuite(CATALOG, "sub_03", 3, side="hostile",
                                doctrine="submarine")
    sonar_controller = next(controller for controller in suite.controllers.values()
                            if controller.domain == "sonar")
    for controller in suite.controllers.values():
        controller.enabled = controller is sonar_controller
        controller.next_scan_s = 1.0
    owner = SimpleNamespace(id=1, x=0.0, y=0.0, depth=40.0, active=True,
                            sunk=False, sensor_domain="subsurface")
    candidate = SimpleNamespace(id=2, x=5.0, y=0.0, depth=5.0, active=True,
                                sunk=False, sensor_domain="surface",
                                noise_level=lambda: .8)
    world = SimpleNamespace(
        sea_state=1, depth_m=lambda *_args: 500.0,
        thermocline_depth_m=lambda *_args: 80.0,
        land_blocks_line=lambda *_args: False,
        sonar_path_blocked=lambda *_args: False)
    calls = []
    original = propagation.propagate
    monkeypatch.setattr(propagation, "propagate",
                        lambda *args, **kwargs: calls.append((args, kwargs))
                        or original(*args, **kwargs))
    suite.update(.99, owner, [candidate], world, CATALOG)
    assert calls == []
    suite.update(1.0, owner, [candidate], world, CATALOG)
    assert len(calls) == 1
    suite.update(1.1, owner, [candidate], world, CATALOG)
    assert len(calls) == 1


def test_catalog_passive_rejects_coincident_fully_blocked_target():
    suite = PlatformSensorSuite(CATALOG, "sub_03", 3, side="hostile",
                                doctrine="submarine")
    sonar_controller = next(controller for controller in suite.controllers.values()
                            if controller.domain == "sonar")
    for controller in suite.controllers.values():
        controller.enabled = controller is sonar_controller
        controller.next_scan_s = 0.0
    owner = SimpleNamespace(id=1, x=0.0, y=0.0, depth=40.0, active=True,
                            sunk=False, sensor_domain="subsurface")
    candidate = SimpleNamespace(id=2, x=0.0, y=0.0, depth=40.0, active=True,
                                sunk=False, sensor_domain="subsurface",
                                noise_level=lambda: .8)
    world = SimpleNamespace(
        sea_state=1, depth_m=lambda *_args: 500.0,
        thermocline_depth_m=lambda *_args: 80.0,
        land_blocks_line=lambda *_args: False,
        sonar_path_blocked=lambda *_args: True)

    suite.update(1.0, owner, [candidate], world, CATALOG)

    assert suite.local_picture.tracks(1.0) == ()


def test_ownship_passive_propagation_runs_only_on_quarter_second_scan(monkeypatch):
    game = Game(seed=18, start_menu=False)
    for actor in game.subs + game.civilians + game.warships + game.flights.flights:
        for controller in actor.sensor_suite.controllers.values():
            controller.enabled = False
    targets = game._sonar_targets()
    for target in targets:
        target.x = target.y = 0.0
    target = game.subs[0]
    target.x, target.y = game.ship.x + 2.0, game.ship.y
    calls = []
    original = propagation.propagate
    monkeypatch.setattr(propagation, "propagate",
                        lambda *args, **kwargs: calls.append((args, kwargs))
                        or original(*args, **kwargs))

    game._update_sim(.1)
    game._update_sim(.1)
    assert calls == []
    game._update_sim(.1)
    assert len(calls) == 1


def test_renderer_and_cold_save_state_do_not_depend_on_propagation(monkeypatch):
    game = Game(seed=17, start_menu=False)
    state = game.save_state()
    assert "propagation" not in state["sonar"]
    monkeypatch.setattr(propagation, "propagate",
                        lambda *_args, **_kwargs: pytest.fail(
                            "renderer called propagation"))
    sonar_view.draw_sonar_view(game)
    assert game.save_state() == state


def test_passive_range_uses_representative_low_frequency_band(monkeypatch):
    sonar = SonarSystem(2)
    ship = Ship(0.0, 0.0, speed_kn=4.0)
    target = SimpleNamespace(
        x=5.0, y=0.0, depth=40.0, quiet_factor=lambda: .4,
        bearing_from_frigate=lambda _ship: 90.0)
    world = SimpleNamespace(
        sea_state=0, depth_m=lambda *_args: 500.0,
        thermocline_depth_m=lambda *_args: 80.0,
        sonar_path_blocked=lambda *_args: False)
    bands = []
    original = propagation.propagate

    def record(*args, **kwargs):
        bands.append(args[6])
        return original(*args, **kwargs)

    monkeypatch.setattr(propagation, "propagate", record)
    value = sonar.passive_range_nm(target, 5.0, ship, world, 1.0, "BOW")
    assert math.isfinite(value) and value > 0.0
    assert bands == [propagation.REPRESENTATIVE_PASSIVE_BAND_HZ]
