"""Measured-bearing CPU benchmarks, not physical uConsole acceptance.

Run timings explicitly with: pytest -q -s tests/test_review_performance.py
No wall-clock thresholds are used as correctness assertions.
"""

import cProfile
import math
import pstats
import statistics
import timeit
from types import SimpleNamespace

import pygame
import pytest

from src.core import config
from src.core.i18n import Translator
from src.sonar import tma
from src.ui import map_view
from src.ui.viewport import Viewport
from src.world.coastline import Coastline
from src.world.world import World


def measured_track(count=80, outlier=False):
    track = tma.BearingTrack()
    for index in range(count):
        seconds = index * 320.0 / (count - 1)
        fx = 250.0 + seconds / 240.0
        fy = 250.0 - min(seconds, 160.0) / 180.0
        tx = 260.0 + seconds / 600.0
        ty = 230.0 + seconds / 900.0
        bearing = math.degrees(math.atan2(tx - fx, -(ty - fy)))
        bearing += .15 * math.sin(index * 1.7)
        if outlier and index == count // 2:
            bearing += 18.0
        track.add(seconds, bearing, fx, fy,
                  37.0 if seconds < 160 else 90.0, .8 + (index % 3) * .2)
    return track


def chart_game():
    pygame.font.init()
    world = World(seed=42, coast=Coastline.generate(42))
    view = Viewport(500, .5, 14)
    view.scale = 1.0
    return SimpleNamespace(
        screen=pygame.Surface((1280, 720)), world=world, map_view=view,
        tr=Translator("en").t,
        font=pygame.font.Font(None, 16), radar_tracks=lambda: [],
        torpedoes=[], buoys=[], essms=[], selected_contact=None, target=None,
        hfdf_log=[], hfdf_fixes={}, sim_t=0.0,
        ship=SimpleNamespace(x=250, y=250, course=0, target_course=0, speed=0),
        helo=SimpleNamespace(airborne=False))


def reference_line_position(geometry, vx, vy, robust_weights=None):
    """Pre-optimization line fit, recalculating raw-bearing geometry each time."""
    m00 = m01 = m11 = b0 = b1 = 0.0
    t0 = geometry[0][0].t
    for index, row in enumerate(geometry):
        p = row[0]
        ux, uy = tma._bearing_dir(p.bearing)
        a00 = 1.0 - ux * ux
        a01 = -ux * uy
        a11 = 1.0 - uy * uy
        weight = 1.0 / (p.uncertainty_deg * p.uncertainty_deg)
        if robust_weights is not None:
            weight *= robust_weights[index]
        tau = p.t - t0
        fx = p.fx - vx * tau
        fy = p.fy - vy * tau
        m00 += weight * a00
        m01 += weight * a01
        m11 += weight * a11
        b0 += weight * (a00 * fx + a01 * fy)
        b1 += weight * (a01 * fx + a11 * fy)
    det = m00 * m11 - m01 * m01
    if det < 1e-9:
        return None
    return ((b0 * m11 - b1 * m01) / det,
            (b1 * m00 - b0 * m01) / det)


@pytest.mark.parametrize("case", ["short", "clean", "outlier", "parallel", "range"])
def test_tma_every_candidate_matches_original_geometry_exactly(case, monkeypatch):
    track = measured_track(4 if case == "short" else 80, case == "outlier")
    if case == "parallel":
        for p in track.pts:
            p.bearing = 90.0
    before = [tuple(getattr(p, name) for name in p.__slots__) for p in track.pts]
    candidates = []
    original = tma._try_candidate

    def record(*args):
        result = original(*args)
        candidates.append(result)
        return result

    monkeypatch.setattr(tma, "_try_candidate", record)
    limit = .01 if case == "range" else None
    actual = tma.solve_tma(track, limit)
    expected_candidates = candidates[:]
    candidates.clear()
    monkeypatch.setattr(tma, "_line_position", reference_line_position)
    expected = tma.solve_tma(track, limit)
    assert candidates == expected_candidates
    assert len(candidates) >= 240
    if expected is None:
        assert actual is None
    else:
        assert tuple(getattr(actual, name) for name in actual.__slots__) == tuple(
            getattr(expected, name) for name in expected.__slots__)
    assert before == [tuple(getattr(p, name) for name in p.__slots__) for p in track.pts]


def test_tma_precomputes_once_per_solve_and_preserves_tie_order(monkeypatch):
    track = measured_track()
    directions = []
    original = tma._bearing_dir

    def direction(bearing):
        directions.append(bearing)
        return original(bearing)

    monkeypatch.setattr(tma, "_bearing_dir", direction)
    tma.solve_tma(track)
    assert directions == [p.bearing for p in track.pts]
    calls = []

    def tied(geometry, t0, course, speed, max_range):
        calls.append((course, speed))
        return 1.0, course, speed, (260.0, 230.0), .5

    monkeypatch.setattr(tma, "_try_candidate", tied)
    result = tma.solve_tma(track)
    assert (result.course, result.speed) == (0, 0.0)
    assert calls[:240] == [(course, speed) for course in range(0, 360, 15)
                           for speed in (0., 2., 4., 6., 8., 10., 12., 14., 16., 18.)]
    dc, ds = config.TMA_FINE_COURSE_STEP_DEG, config.TMA_FINE_SPEED_STEP_KN
    assert calls[240:] == [(course % 360, speed) for course in (-dc, 0, dc)
                          for speed in (0.0, ds)]


@pytest.mark.parametrize("count", [20, 80])
def test_profile_measured_bearing_solve(count):
    track = measured_track(count, outlier=True)
    assert tma.solve_tma(track) is not None
    samples = timeit.repeat(lambda: tma.solve_tma(track), number=3, repeat=5)
    print(f"TMA {count} measured bearings: "
          f"{statistics.median(samples) / 3 * 1000:.3f} ms/solve (median 5 x 3)")
    profile = cProfile.Profile()
    profile.runcall(tma.solve_tma, track)
    pstats.Stats(profile).strip_dirs().sort_stats("cumtime").print_stats(8)


@pytest.mark.parametrize("scale", [1.0, 4.0])
def test_profile_chart_draw(scale):
    game = chart_game()
    game.map_view.scale = scale
    map_view.draw_map_view(game)
    samples = timeit.repeat(lambda: map_view.draw_map_view(game), number=30, repeat=5)
    print(f"Chart scale {scale}: {statistics.median(samples) / 30 * 1000:.3f} "
          "ms/draw (warm median 5 x 30, generated sector seed 42, empty tracks)")
    profile = cProfile.Profile()
    profile.runcall(map_view.draw_map_view, game)
    pstats.Stats(profile).strip_dirs().sort_stats("cumtime").print_stats(8)
