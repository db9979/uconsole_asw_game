"""The frigate's own helicopter in the bridge's eyepieces (display only)."""

import math

import numpy as np
import pygame

from src.commander import lookout_projection, projections
from src.core.game import Game
from src.core.station import Station
from src.ui import horizon, own_helo
from src.ui.stations import bridge as bridge_view


def _game(seed=83):
    game = Game(seed=seed, start_menu=False, audio_enabled=False, language="en")
    game.world.hour = 12.0
    return game


def _fly(game, distance_nm, off_bow_deg, *, dipping=False):
    """Launch the helicopter and hold it ``distance_nm`` off the bow."""
    helo = game.helo
    helo.launch(game.ship)
    bearing = math.radians(game.ship.course + off_bow_deg)
    helo.x = game.ship.x + distance_nm * math.sin(bearing)
    helo.y = game.ship.y - distance_nm * math.cos(bearing)
    helo.course = (game.ship.course + 90.0) % 360.0
    if dipping:
        helo.dip_state = "DEPLOYED"
    return math.degrees(bearing) % 360.0


def test_hangar_shows_nothing_and_flight_shows_the_model():
    game = _game()
    assert game.helo.state == "HANGAR"
    assert own_helo.outline(game) is None
    bearing = _fly(game, 1.0, 20.0)
    row, distance = own_helo.seen(game)
    assert row[2] == "aircraft" and row[3] is False
    assert abs(((row[0] - bearing + 180.0) % 360.0) - 180.0) < 1.0
    assert abs(distance - 1.0) < 0.05
    # Above the sea horizon, turned by its own heading, its own length.
    assert row[5] > 0.0 and row[6] is not None
    assert abs(row[1] - math.degrees(own_helo.LENGTH_M / (distance * 1852.0))) < 1e-6


def test_dipping_hover_flies_lower_than_transit():
    game = _game()
    _fly(game, 1.0, 20.0)
    transit = own_helo.outline(game)[5]
    game.helo.dip_state = "DEPLOYED"
    assert own_helo.outline(game)[5] < transit


def test_on_launch_it_sits_on_the_flight_deck_astern():
    game = _game()
    game.helo.launch(game.ship)
    row = own_helo.outline(game)
    astern = (game.ship.course + 180.0) % 360.0
    assert abs(((row[0] - astern + 180.0) % 360.0) - 180.0) < 1.0
    assert row[5] < 0.0          # below the bridge's eye, on the deck


def test_out_of_sight_beyond_the_eye_or_lost():
    game = _game()
    _fly(game, 3.0, 20.0)
    assert own_helo.outline(game) is not None
    game.world.weather_override = "fog"
    assert own_helo.outline(game) is None
    game.world.weather_override = None
    assert own_helo.outline(game) is not None
    game.helo.state = "VERLOREN"
    assert own_helo.outline(game) is None


def test_eye_outlines_put_the_helicopter_first_and_report_nothing():
    game = _game()
    _fly(game, 1.0, 20.0)
    tracks = len(game.air_picture.tracks(game.sim_t))
    rows = bridge_view.eye_outlines(game, game.lookout_sightings())
    assert rows[0] == own_helo.outline(game)
    # Own asset: never a lookout track, report or call.
    assert not game.lookout_sightings()
    assert len(game.air_picture.tracks(game.sim_t)) == tracks
    assert not game.lookout_reports


def test_remote_glasses_phone_and_hit_view_carry_it():
    game = _game()
    _fly(game, 1.0, 20.0)
    glasses = projections._lookout_glasses(game)
    assert glasses["outlines"][0]["cls"] == "aircraft"
    assert glasses["outlines"][0]["elevation_deg"] > 0.0
    phone = lookout_projection._frigate(game)
    assert phone["outlines"][0]["cls"] == "aircraft"
    assert phone["outlines"][0]["called"] is False


def test_glasses_and_lookout_page_draw_it():
    game = _game()
    _fly(game, 0.6, 10.0)
    game.station = Station.BRIDGE
    game.station_page = 2
    game.lookout_glasses = True
    row = own_helo.outline(game)
    game.lookout_glasses_rel = (row[0] - game.ship.course) % 360.0
    game.lookout_optics.elevation_deg = row[5]
    game.draw()
    with_helo = pygame.surfarray.array3d(game.screen).copy()
    game.helo.state = "HANGAR"
    game.draw()
    without = pygame.surfarray.array3d(game.screen)
    assert (with_helo != without).any(axis=2).sum() > 200


def test_a_low_aircraft_stands_in_front_of_the_sea():
    """Below ``LOW_AIR_DEG`` an aircraft is drawn on the moving horizon after
    the sea, so a hovering helicopter is not hidden behind the waves."""
    def picture(rows):
        surface = pygame.Surface((400, 200))
        horizon.draw_horizon(surface, (0, 0, 400, 200), line_of_sight=0.0, fov_deg=4.0,
                             night=False, visibility_nm=30.0, motion=(0.0, 0.0),
                             outlines=rows, anim_t=1.0)
        return pygame.surfarray.array3d(surface)

    empty = picture([])
    low = picture([(0.0, 0.3, "aircraft", False, None, 0.05, 90.0, None, None)])
    changed = np.argwhere((empty != low).any(axis=2))
    assert len(changed) > 50
    # Around the horizon in the middle of the field.
    assert abs(changed[:, 0].mean() - 200) < 30
    assert abs(changed[:, 1].mean() - 100) < 30
