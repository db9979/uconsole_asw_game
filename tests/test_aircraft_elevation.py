"""Aircraft in the eyepieces stand at their true elevation above the sea
horizon, in the still sky behind the clouds, not riding the swell."""

import math
import sys
from pathlib import Path

import pygame
import pytest

from src.commander import projections
from src.core import opfor
from src.sensors import visual
from src.ui import horizon, sight_scene, uboot_scope
from src.ui.stations import bridge as bridge_view

sys.path.insert(0, str(Path(__file__).parent))
from test_uboot_scope import _clear, _crewed, _environment, _scope_up  # noqa: E402


def test_elevation_follows_height_range_and_the_curved_earth():
    # 1500 m at 4 NM from the bridge wing: about 11 degrees up.
    assert visual.elevation_deg(1500.0, 4.0, 18.0) == pytest.approx(11.4, abs=0.1)
    assert visual.elevation_deg(10_000.0, 1.0, 18.0) > 75.0
    # Higher is higher, further is lower.
    assert visual.elevation_deg(300.0, 3.0, 18.0) < visual.elevation_deg(600.0, 3.0, 18.0)
    assert visual.elevation_deg(300.0, 6.0, 18.0) < visual.elevation_deg(300.0, 3.0, 18.0)
    # An object at eye height sits on the horizon at the horizon distance.
    reach = visual.optical_horizon_nm(18.0, 0.0) * 2.0
    assert visual.elevation_deg(18.0, reach, 18.0) == pytest.approx(0.0, abs=0.02)
    # Low and far it drops below the horizon.
    assert visual.elevation_deg(20.0, 30.0, 18.0) < 0.0


def _bases(monkeypatch, motion, rows):
    pygame.init()
    drawn = []
    monkeypatch.setattr(horizon, "draw_outline",
                        lambda s, cls, cx, base, *args, aloft=False, **kw:
                        drawn.append((cls, base, aloft)))
    surface = pygame.Surface((480, 300))
    horizon.draw_horizon(surface, (0, 0, 480, 300), line_of_sight=0.0, fov_deg=16.0,
                         night=False, visibility_nm=15.0, motion=motion, outlines=rows,
                         sky=sight_scene.plain_sky(False))
    return drawn


def test_aircraft_hang_in_the_still_sky_while_ships_ride_the_swell(monkeypatch):
    rows = [(0.0, 0.5, "aircraft", False, None, 3.0), (2.0, 1.0, "merchant", False, None, None)]
    calm = _bases(monkeypatch, (0.0, 0.0), rows)
    rolling = _bases(monkeypatch, (25.0, 0.1), rows)
    px_per_deg = 480 / 16.0
    assert calm[0] == ("aircraft", int(150 - 3.0 * px_per_deg), True)
    assert rolling[0] == calm[0]                          # decoupled from the waves
    assert calm[1][2] is False and rolling[1][1] != calm[1][1]


def test_aircraft_fly_behind_the_clouds(monkeypatch):
    order = []
    monkeypatch.setattr(sight_scene, "_draw_clouds", lambda *args: order.append("clouds"))
    monkeypatch.setattr(horizon, "draw_outline",
                        lambda *args, aloft=False, **kw: order.append("aloft" if aloft else "ship"))
    pygame.init()
    horizon.draw_horizon(pygame.Surface((480, 300)), (0, 0, 480, 300), line_of_sight=0.0,
                         fov_deg=16.0, night=False, visibility_nm=15.0, motion=(0.0, 0.0),
                         outlines=[(0.0, 0.5, "aircraft", False, None, 2.0),
                                   (1.0, 1.0, "merchant", False, None, None)],
                         sky=sight_scene.plain_sky(False))
    assert order == ["aloft", "clouds", "ship"]


def test_the_lookout_reports_the_elevation_of_an_aircraft():
    game, _server, _bridge = _crewed(seed=61)
    game.world.hour = 12.0
    game._lookout_environment = lambda: dict(_environment(False), illumination=1.0)
    game.crew_effect = lambda: 1.0
    for other in game.civilians + game.warships:
        other.x, other.y = game.ship.x + 60.0, game.ship.y + 60.0
    game.world.land_blocks_line = lambda *args: False
    flights = [flight for flight in game.flights.flights if flight.active]
    if not flights:
        pytest.skip("no flight in the air for this seed")
    for flight in game.flights.flights:
        flight.x, flight.y = game.ship.x - 80.0, game.ship.y - 80.0
    flight = flights[0]
    flight.x, flight.y = game.ship.x + 2.0, game.ship.y
    game._update_lookout_picture()
    rows = [row for row in bridge_view.lookout_outlines(game, game.lookout_sightings())
            if row[2] == "aircraft"]
    expected = visual.elevation_deg(flight.altitude_m, 2.0, visual.LOOKOUT_EYE_HEIGHT_M)
    assert len(rows) == 1 and rows[0][5] == pytest.approx(expected)
    glasses = projections._lookout_glasses(game)
    air = [row for row in glasses["outlines"] if row["cls"] == "aircraft"]
    assert air[0]["elevation_deg"] == pytest.approx(expected)
    assert all(row["elevation_deg"] is None for row in glasses["outlines"]
               if row["cls"] != "aircraft")


def test_the_periscope_sees_the_helicopter_at_its_elevation():
    game, _server, _bridge = _crewed(seed=61)
    boat = game.opfor
    _scope_up(boat)
    _clear(game)
    game.world.land_blocks_line = lambda *args: False
    sub = boat.sub
    for other in game.civilians + game.warships:
        other.x, other.y = sub.x + 60.0, sub.y + 60.0
    game.ship.x, game.ship.y = sub.x + 40.0, sub.y + 40.0
    game.helo.state = "AUF"
    game.helo.x, game.helo.y = sub.x, sub.y - 1.0
    opfor.update_sightings(game, boat)
    rows = [row for row in uboot_scope.scope_outlines(game, boat) if row[5] is not None]
    assert len(rows) == 1 and rows[0][2] == "aircraft"
    assert rows[0][5] == pytest.approx(visual.elevation_deg(
        opfor._SCOPE_AIR_ALTITUDE_M, 1.0, opfor.config.UBOOT_SCOPE_EYE_HEIGHT_M))
    scope = projections._uboot_scope(game, boat)
    assert [row["elevation_deg"] for row in scope["sightings"]
            if row["elevation_deg"] is not None] == [pytest.approx(rows[0][5])]
    assert math.isfinite(rows[0][5])
