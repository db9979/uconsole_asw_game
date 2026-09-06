"""Geographic map palette and own-helicopter presentation."""

from types import SimpleNamespace

import pygame

from src.core import config
from src.ui import map_view, nato_symbols
from src.ui.viewport import Viewport


class EmptyCoast:
    has_bathymetry = False

    def land_points_px(self, view):
        return []

    def airbase_px(self, view):
        return []


class BathymetricCoast(EmptyCoast):
    has_bathymetry = True


def map_game(*, helo_airborne=False, coast=None):
    pygame.font.init()
    view = Viewport(500.0, 1.0, 14.0)
    view.scale = 1.0
    return SimpleNamespace(
        screen=pygame.Surface((config.SCREEN_W, config.SCREEN_H)),
        map_view=view,
        map_follow=False,
        world=SimpleNamespace(
            coast=coast or EmptyCoast(), size_nm=500.0,
            depth_m=lambda x, y: 900.0),
        ship=SimpleNamespace(
            x=250.0, y=250.0, course=0.0, target_course=0.0, speed=0.0),
        helo=SimpleNamespace(
            airborne=helo_airborne, x=250.0, y=250.0, course=90.0),
        font=pygame.font.Font(None, 18),
        torpedoes=[],
        buoys=[],
        essms=[],
        selected_contact=None,
        target=None,
        hfdf_log=[],
        hfdf_fixes={},
        world_mode="fixed",
        radar_tracks=lambda: [],
    )


def test_fixed_map_water_and_out_of_world_strips_use_geographic_navy():
    game = map_game()

    map_view.draw_map_view(game)

    assert game.screen.get_at((301, 261))[:3] == config.COLOR_GEO_BG
    assert game.screen.get_at((20, 100))[:3] == config.COLOR_GEO_BG
    assert config.COLOR_GEO_BG[2] > config.COLOR_GEO_BG[1] > config.COLOR_GEO_BG[0]


def test_procedural_bathymetry_uses_blue_depth_palette():
    game = map_game(coast=BathymetricCoast())

    map_view.draw_map_view(game)

    assert game.screen.get_at((301, 261))[:3] == config.COLOR_DEEP
    assert all(color[2] > color[1] > color[0]
               for color in (config.COLOR_SHALLOW, config.COLOR_DEEP))


def test_airborne_helo_uses_readable_friend_air_symbol_above_ship(monkeypatch):
    game = map_game(helo_airborne=True)
    calls = []
    original = nato_symbols.draw_symbol

    def record(surface, center, affiliation, domain, size=16, selected=False):
        calls.append((center, affiliation, domain, size))
        return original(surface, center, affiliation, domain, size, selected)

    monkeypatch.setattr(nato_symbols, "draw_symbol", record)
    map_view.draw_map_view(game)

    center = tuple(map(int, game.map_view.world_to_screen(250.0, 250.0)))
    assert calls == [((320.0, 285.0), "FRIEND", "AIR", 22)]
    assert game.screen.get_at(center)[:3] == nato_symbols.AFFILIATION_COLORS["FRIEND"]
