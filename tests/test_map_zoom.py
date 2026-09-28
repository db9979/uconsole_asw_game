"""Chart zoom reaches 0.5 NM with a readable grid, clipped coast and rings."""

import pygame

from src.core import config
from src.core.station import Station
from src.core.game import Game
from src.ui import map_view
from src.ui.stations import opz
from src.ui.viewport import Viewport


def _chart_view():
    view = Viewport(500.0, config.MAP_ZOOM_MIN_PX_PER_NM,
                    config.MAP_ZOOM_MAX_PX_PER_NM)
    view.set_rect((0, 30, 640, 668))
    view.scale = config.MAP_ZOOM_DEFAULT_PX_PER_NM
    view.cx = view.cy = 250.0
    return view


def _height(view):
    return round(view.rect[3] / view.scale, 3)


def test_keys_step_through_fixed_heights_down_to_half_a_mile():
    view = _chart_view()
    heights = []
    for _ in range(12):
        view.step_zoom(1, config.MAP_ZOOM_STEPS_NM)
        heights.append(_height(view))
    assert heights[:7] == [50.0, 25.0, 10.0, 5.0, 2.0, 1.0, 0.5]
    # Past the last step the view stops at the maximum zoom.
    assert view.scale == config.MAP_ZOOM_MAX_PX_PER_NM
    for _ in range(12):
        view.step_zoom(-1, config.MAP_ZOOM_STEPS_NM)
    # Fully out shows the whole world again (min scale).
    assert view.scale == config.MAP_ZOOM_MIN_PX_PER_NM


def test_wheel_reaches_the_same_detail_and_keeps_the_pivot():
    view = _chart_view()
    pivot = (100, 200)
    anchor = view.screen_to_world(*pivot)
    for _ in range(40):
        view.zoom(config.MAP_ZOOM_WHEEL_FACTOR, pivot=pivot)
    assert view.scale == config.MAP_ZOOM_MAX_PX_PER_NM
    assert _height(view) < 0.5
    x, y = view.screen_to_world(*pivot)
    assert abs(x - anchor[0]) < 1e-6 and abs(y - anchor[1]) < 1e-6


def test_grid_step_keeps_legacy_steps_and_gets_finer_when_zoomed():
    assert map_view.grid_step_nm(1.0) == 50.0
    assert map_view.grid_step_nm(5.0) == 25.0
    assert map_view.grid_step_nm(10.0) == 10.0
    assert map_view.grid_step_nm(100.0) == 1.0
    assert map_view.grid_step_nm(config.MAP_ZOOM_MAX_PX_PER_NM) == 0.1
    for scale in (8.0, 20.0, 60.0, 300.0, 1400.0):
        assert map_view.grid_step_nm(scale) * scale >= 80.0
    assert map_view.grid_label(247.1) == "247.1"
    assert map_view.grid_label(250.0) == "250"


def test_scale_line_shows_fractions_below_ten_miles():
    assert map_view.scale_label(0.477) == "0.5"
    assert map_view.scale_label(2.0) == "2"
    assert map_view.scale_label(66.8) == "67"


def test_polygon_clip_keeps_small_outlines_and_cuts_huge_ones():
    rect = (0, 30, 640, 668)
    small = [(10.0, 40.0), (100.0, 40.0), (50.0, 90.0)]
    assert map_view.clip_polygon_to_rect(small, rect) == small
    huge = [(-200000.0, -200000.0), (300.0, -200000.0), (300.0, 200000.0),
            (-200000.0, 200000.0)]
    clipped = map_view.clip_polygon_to_rect(huge, rect)
    assert len(clipped) >= 3
    assert all(-64.0 <= x <= 704.0 and -34.0 <= y <= 762.0 for x, y in clipped)
    assert max(x for x, _ in clipped) == 300.0


def test_ring_visibility_skips_circles_that_cannot_be_seen():
    chart = pygame.Rect(0, 0, 400, 300)
    assert opz._ring_visible((200, 150), 100, chart)
    assert not opz._ring_visible((200, 150), 100000, chart)
    assert not opz._ring_visible((5000, 150), 100, chart)


def test_every_chart_draws_at_maximum_zoom():
    game = Game(seed=31, start_menu=False)
    game.station = Station.BRIDGE
    game.map_view.set_rect(config.MAP_RECT)
    game.map_view.scale = config.MAP_ZOOM_MAX_PX_PER_NM
    game.map_view.cx, game.map_view.cy = game.ship.x, game.ship.y
    game.draw()
    game.station = Station.OPZ
    chart = opz.opz_regions()["chart"]
    game._configure_opz_map_view(chart)
    game.opz_map_view.scale = game.opz_map_view.max_scale
    assert game.opz_map_view.max_scale == min(chart.w, chart.h) / (
        2.0 * config.OPZ_MAP_MAX_ZOOM_RADIUS_NM)
    game.draw()
