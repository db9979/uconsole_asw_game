"""Bridge lookout binoculars over the chart, the periscope box on the uConsole
and Command raising the boat's mast."""

import math
import sys
from pathlib import Path

import pygame

from src.core import config, uboot_local
from src.core.station import Station
from src.ui import layout, uboot_scope
from src.ui.stations import bridge as bridge_view

sys.path.insert(0, str(Path(__file__).parent))
from test_opfor_sub import _crewed, _game  # noqa: E402
from test_uboot_scope import _local_boat, _scope_up  # noqa: E402


def _key(game, key, mod=0):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod, unicode=""))


def _lookout_page(game):
    game.station = Station.BRIDGE
    game.station_page = 2


def _warship_ahead(game, distance_nm=3.0, off_bow_deg=20.0):
    warship = game.warships[0]
    bearing = math.radians(game.ship.course + off_bow_deg)
    warship.x = game.ship.x + distance_nm * math.sin(bearing)
    warship.y = game.ship.y - distance_nm * math.cos(bearing)
    game.world.hour = 12.0
    for _ in range(80):
        game._update(0.25)
    assert game.lookout_sightings()


def test_b_raises_the_binoculars_only_on_the_lookout_page():
    game = _game(5)
    game.station = Station.BRIDGE
    game.station_page = 0
    _key(game, pygame.K_b)
    assert not game.lookout_glasses_shown()
    _lookout_page(game)
    _key(game, pygame.K_b)
    assert game.lookout_glasses and game.lookout_glasses_shown()
    # Another page or station hides them; they are display state only.
    game.station_page = 1
    assert not game.lookout_glasses_shown()
    _lookout_page(game)
    _key(game, pygame.K_b)
    assert not game.lookout_glasses_shown()


def test_glasses_train_with_comma_and_period_instead_of_the_radius():
    game = _game(5)
    _lookout_page(game)
    radius = game.lookout_range_nm
    _key(game, pygame.K_b)
    _key(game, pygame.K_PERIOD)
    assert game.lookout_glasses_rel == config.LOOKOUT_GLASSES_STEP_DEG
    _key(game, pygame.K_COMMA, pygame.KMOD_SHIFT)
    assert game.lookout_glasses_rel == (config.LOOKOUT_GLASSES_STEP_DEG
                                        - config.LOOKOUT_GLASSES_STEP_FAST_DEG) % 360.0
    assert game.lookout_range_nm == radius
    _key(game, pygame.K_b)
    _key(game, pygame.K_PERIOD)
    assert game.lookout_range_nm != radius           # the radius again once closed


def test_glasses_cover_the_chart_pointer_and_a_panorama_click_trains_them():
    game = _game(5)
    _lookout_page(game)
    _key(game, pygame.K_b)
    with layout.bottom_panel_regions(game.bottom_panel_mode()):
        _frame, eyepiece, panorama = bridge_view._glasses_layout()
    assert game._map_pointer(eyepiece.center) is None
    # The middle of the panorama is the bow, a quarter further is 90° to starboard.
    point = (panorama.x + panorama.w * 3 // 4, panorama.centery)
    with layout.bottom_panel_regions(game.bottom_panel_mode()):
        bearing = bridge_view.lookout_glasses_bearing_at(game, point)
    assert abs(((bearing - game.ship.course - 90.0 + 180.0) % 360.0) - 180.0) < 1.0
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=point))
    assert abs(((game.lookout_glasses_rel - 90.0 + 180.0) % 360.0) - 180.0) < 1.0
    _key(game, pygame.K_b)
    assert game._map_pointer(eyepiece.center) is not None


def test_glasses_draw_the_lookouts_sightings_over_the_chart(monkeypatch):
    game = _game(5)
    _warship_ahead(game)
    _lookout_page(game)
    _key(game, pygame.K_b)
    track = game.lookout_sightings()[0]
    game._train_lookout_glasses_to(track.bearing)
    seen = []
    original = bridge_view.horizon.draw_horizon

    def spy(s, rect, **kwargs):
        seen.append((pygame.Rect(rect), kwargs))
        return original(s, rect, **kwargs)

    monkeypatch.setattr(bridge_view.horizon, "draw_horizon", spy)
    game.draw()
    glasses = [(rect, kwargs) for rect, kwargs in seen
               if kwargs["fov_deg"] == config.LOOKOUT_GLASSES_FOV_DEG]
    assert len(glasses) == 1
    rect, kwargs = glasses[0]
    assert pygame.Rect(config.MAP_RECT).contains(rect)
    assert abs(((kwargs["line_of_sight"] - track.bearing + 180.0) % 360.0) - 180.0) < 1e-6
    assert any(abs(((row[0] - track.bearing + 180.0) % 360.0) - 180.0) < 1e-6
               for row in kwargs["outlines"])


def test_the_eyepiece_stays_inside_its_box(monkeypatch):
    game, boat = _local_boat()
    _scope_up(boat)
    uboot_local.set_local_station(game, "uboot")
    boat.command_page = 2
    views = []
    monkeypatch.setattr(uboot_scope, "draw_eyepiece",
                        lambda s, game, boat, rect: views.append(pygame.Rect(rect)))
    with layout.capture_geometry() as boxes:
        game.draw()
    box = next(row["rect"] for row in boxes if row["title"] == "uboot.panel.scope")
    assert views and box.contains(views[0])


def test_command_raises_the_mast_for_the_periscope():
    game, _server, bridge = _crewed()
    sub = game.opfor.sub
    sub.depth = sub.target_depth = sub.order_depth = 12.0
    assert bridge._apply_opfor_action(game, "uboot_mast", {"enabled": True}, "uboot") is True
    assert sub.crew.mast


def test_p_raises_the_mast_at_the_commands_periscope_page():
    game, boat = _local_boat()
    sub = boat.sub
    sub.depth = sub.target_depth = sub.order_depth = 12.0
    uboot_local.set_local_station(game, "uboot")
    boat.command_page = 2
    _key(game, pygame.K_p)
    assert boat.orders.mast
