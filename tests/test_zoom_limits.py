"""Strong zoom never breaks a chart (1.3.191: 'Anzeige gestört').

At 1400 px/NM a waypoint a few miles away lies tens of thousands of
pixels off the chart; the anti-aliased line path (gfxdraw, signed 16-bit
coordinates) raised ``OverflowError`` and the guarded view showed the
fault box.  Lines and polygons are clipped before they reach gfxdraw."""

from dataclasses import replace

import pygame
import pytest

from src.core import config, uboot_local
from src.core.game import Game
from src.commander.v2.wire import OPFOR_ROLES
from src.core.station import Station
from src.ship.route import Route
from src.ui import layout, lines, uboot_view

FAR = 40000.0


@pytest.fixture
def aa_lines():
    lines.ENABLED = True
    yield
    lines.ENABLED = False
    layout.configure_for(large_text=False)


def test_anti_aliased_primitives_accept_coordinates_far_off_the_surface(aa_lines):
    surface = pygame.Surface((64, 64))
    surface.fill((0, 0, 0))
    lines.line(surface, (255, 255, 255), (10, 10), (FAR, 50))
    lines.line(surface, (255, 255, 255), (-FAR, -FAR), (FAR * 3, FAR * 3))
    lines.line(surface, (255, 255, 255), (FAR, FAR), (FAR + 5, FAR))     # fully outside
    lines.lines(surface, (200, 200, 200), True, [(5, 50), (FAR, 58), (55, -FAR)])
    lines.polygon(surface, (120, 200, 120), [(-FAR, -FAR), (FAR, -FAR), (32, FAR)])
    lines.polygon(surface, (120, 200, 120), [(-FAR, 5), (FAR, 8), (50, FAR)], 1)
    lines.polygon(surface, (120, 200, 120), [(FAR, FAR), (FAR + 9, FAR), (FAR, FAR + 9)])
    # The clipped segment still reaches the surface edge towards the far end.
    assert surface.get_at((63, 59))[:3] != (0, 0, 0) or surface.get_at((63, 60))[:3] != (0, 0, 0)
    seg = lines.clip_segment((10, 10), (FAR, 50), (0, 0, 64, 64))
    assert seg[0] == (10, 10) and seg[1][0] == 64
    assert lines.clip_segment((100, 100), (200, 100), (0, 0, 64, 64)) is None


def _full_graphics_game(seed=31):
    game = Game(seed=seed, start_menu=False)
    game.preferences = replace(game.preferences, graphics="full")
    layout.configure_for(game)
    assert lines.ENABLED is True
    return game


def _frigate_views(game):
    for station in (Station.BRIDGE, Station.SONAR, Station.WEAPONS, Station.DAMAGE,
                    Station.OPZ, Station.RADIO, Station.ENGINE, Station.HELICOPTER,
                    Station.ELOKA):
        game.station = station
        game.draw()


@pytest.mark.parametrize("corner", [(0.5, 0.5), (250.0, 250.0), (499.5, 499.5)])
def test_every_frigate_station_draws_at_both_zoom_limits(aa_lines, corner):
    game = _full_graphics_game()
    game.ship.x, game.ship.y = corner
    # A route with a far waypoint: its leg crosses the whole zoomed chart.
    game.route = Route([(250.0, 10.0), (10.0, 490.0), (490.0, 250.0)])
    for scale in (config.MAP_ZOOM_MAX_PX_PER_NM, config.MAP_ZOOM_MIN_PX_PER_NM):
        game.map_view.set_rect(config.MAP_RECT)
        game.map_view.scale = scale
        game.map_view.cx, game.map_view.cy = corner
        game.map_view.clamp_center()
        game.opz_map_view.scale = game.opz_map_view.max_scale if scale > 1 \
            else game.opz_map_view.min_scale
        _frigate_views(game)
    assert game.view_faults == 0


def test_every_boat_station_draws_at_both_zoom_limits(aa_lines):
    game = _full_graphics_game(seed=5)
    game.local_side = "uboot"
    game._update(0.05)
    boat = game.opfor
    assert boat is not None
    for scale in (config.MAP_ZOOM_MAX_PX_PER_NM, config.MAP_ZOOM_MIN_PX_PER_NM):
        for follow in (True, False):
            boat.chart_follow = follow
            view = uboot_view.chart_view(game, boat)
            view.scale = scale
            if not follow:
                view.cx, view.cy = 0.0, 0.0
                view.clamp_center()
            for station in OPFOR_ROLES:
                uboot_local.set_local_station(game, station)
                game.draw()
    assert game.view_faults == 0
