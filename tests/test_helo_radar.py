"""The helicopter's surface-search radar (RADAR-HELO tracks for the OPZ)."""

import pytest

from src.core import config
from src.core.game import Game
from src.world.world import World


@pytest.fixture(autouse=True)
def calm_sea(monkeypatch):
    monkeypatch.setattr(World, "effective_sea_state", property(lambda self: 1.0))
    monkeypatch.setattr(Game, "radar_rain_severity", lambda self: 0.0)


def _game(seed=3001):
    return Game(seed=seed, start_menu=False, audio_enabled=False)


def _airborne(game, x, y):
    helo = game.helo
    helo.state = "AUF"
    helo.x, helo.y = x, y
    helo.dip_state = "STOWED"
    return helo


def _helo_tracks(game):
    return [track for track in game.air_picture.tracks(game.sim_t)
            if track.source == "RADAR-HELO"]


def _sweep(game, seconds=20.0):
    for _ in range(int(seconds / 0.5)):
        game.sim_t += 0.5
        game._update_helo_radar(0.5)


def test_airborne_radar_reports_a_surfaced_boat_and_a_ship():
    game = _game()
    sub = game.subs[0]
    sub.depth = 0.0
    _airborne(game, sub.x + 3.0, sub.y)
    _sweep(game)
    tracks = _helo_tracks(game)
    assert tracks
    assert any(track.target_id == sub.id for track in tracks)
    assert all(track.kind == "SURFACE" and track.track_id.startswith("H-")
               for track in tracks)
    assert game.helo_radar_active()


def test_a_raised_mast_shows_but_a_deep_boat_does_not():
    game = _game(3002)
    game.civilians, game.warships = [], []
    sub = game.subs[0]
    for other in game.subs[1:]:
        other.sunk = True
    _airborne(game, sub.x + 3.0, sub.y)
    sub.depth = 150.0
    _sweep(game)
    assert not _helo_tracks(game)
    sub.depth = 12.0
    game._mast_up = lambda boat: boat is sub
    _sweep(game, 60.0)
    assert _helo_tracks(game)


def test_no_radar_on_deck_or_while_dipping():
    game = _game(3003)
    sub = game.subs[0]
    sub.depth = 0.0
    game.helo.x, game.helo.y = sub.x + 3.0, sub.y
    assert game.helo.state == "HANGAR" and not game.helo_radar_active()
    _sweep(game)
    assert not _helo_tracks(game)
    _airborne(game, sub.x + 3.0, sub.y)
    game.helo.dip_state = "DEPLOYED"
    assert not game.helo_radar_active()
    _sweep(game)
    assert not _helo_tracks(game)


def test_radar_range_and_horizon_bound_the_search():
    game = _game(3004)
    sub = game.subs[0]
    sub.depth = 0.0
    far = config.radar_horizon_nm(config.HELO_RADAR_ALTITUDE_M, 3.0) + 1.0
    _airborne(game, sub.x + far, sub.y)
    game.civilians, game.warships = [], []
    _sweep(game)
    assert not [track for track in _helo_tracks(game) if track.target_id == sub.id]


def test_projection_reports_the_radar_state():
    from src.commander import projections
    game = _game(3005)
    _airborne(game, game.ship.x + 2.0, game.ship.y)
    asset = projections._helicopter(game, [], {}, {}, asset_only=True)["asset"]
    assert "radar" not in asset
    game.helo.dip_state = "DEPLOYED"
    assert game.helo_radar_active() is False
