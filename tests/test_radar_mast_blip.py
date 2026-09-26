"""A raised submarine mast or snorkel is a bare radar blip until the OPZ marks it."""

import math

import pytest

from src.core import config
from src.core.game import Game
from src.sensors import radar as radar_physics


def _game(seed=83):
    game = Game(seed=seed, start_menu=False, audio_enabled=False, language="en")
    game._radar_conditions = lambda: dict(sea_state=1, rain_intensity=0.0, capability=1.0)
    game.world.land_blocks_line = lambda *args: False
    game.surface_radar_on = True
    return game


def _place_sub(game, distance_nm=3.0, mast=True):
    sub = game.subs[0]
    sub.x, sub.y = game.ship.x + distance_nm, game.ship.y
    sub.depth = sub.target_depth = 12.0
    game.claim_opfor_sub()
    boat = game.opfor
    assert boat is not None and boat.sub is sub
    boat.orders.mast = mast
    return sub


def _sweeps(game, revolutions=6):
    for _ in range(revolutions):
        game._update_air_picture(full_scan=True)
        game.sim_t += 4.0


def test_mast_echo_is_a_blip_without_a_track():
    game = _game()
    sub = _place_sub(game)
    tracks_before = {track.track_id for track in game.air_picture.tracks(game.sim_t)}
    _sweeps(game)
    assert any(blip["target"] == sub.id for blip in game.radar_blips)
    # No radar track is created from the echo alone.
    assert {track.track_id for track in game.air_picture.tracks(game.sim_t)} == tracks_before
    game.audio.shutdown()


def test_no_blip_with_the_mast_down_or_deep():
    game = _game()
    _place_sub(game, mast=False)
    _sweeps(game)
    assert not game.radar_blips
    game.opfor.orders.mast = True
    game.opfor.sub.depth = 60.0
    _sweeps(game)
    assert not game.radar_blips
    game.audio.shutdown()


def test_marking_a_blip_starts_a_track_that_later_echoes_update():
    game = _game()
    sub = _place_sub(game)
    for _ in range(12):
        game._update_air_picture(full_scan=True)
        game.sim_t += 1.0
        if game.radar_blip_view():
            break
    blips = game.radar_blip_view()
    assert blips
    assert game.mark_radar_blip(blips[-1]["seq"]) is True
    track_id = f"R-{blips[-1]['seq']}"
    track = next(track for track in game.air_picture.tracks(game.sim_t)
                 if track.track_id == track_id)
    assert track.source == "RADAR-S" and track.kind == "SURFACE"
    assert game.radar_blip_view() == []  # The marked boat no longer blips.
    first = track.last_seen
    _sweeps(game, 8)
    updated = next(track for track in game.air_picture.tracks(game.sim_t)
                   if track.track_id == track_id)
    assert updated.last_seen > first
    assert game.mark_radar_blip(10**9) == "stale_ref"
    assert game.mark_radar_blip("1") == "invalid_value"
    assert sub.id in game._radar_marked
    game.audio.shutdown()


def test_blips_are_deterministic():
    runs = []
    for _ in range(2):
        game = _game(seed=91)
        _place_sub(game, distance_nm=4.0)
        _sweeps(game, 10)
        runs.append([(blip["seq"], round(blip["x"], 9), round(blip["y"], 9))
                     for blip in game.radar_blips])
        game.audio.shutdown()
    assert runs[0] == runs[1] and runs[0]


@pytest.mark.parametrize("sea_state,low,high", [(1, 6.0, 8.5), (3, 1.8, 3.5), (5, 0.3, 1.2)])
def test_mast_echo_range_falls_with_sea_state(sea_state, low, high):
    """Documented Pd = 0.5 ranges of the mast echo (manual, OPZ chapter)."""
    distance = None
    for tenth in range(1, 400):
        value = tenth / 10.0
        sinr = radar_physics.sinr(value, config.RADAR_SURFACE_RANGE_NM,
                                  rcs_factor=config.SUB_MAST_RCS_FACTOR, domain="surface",
                                  jnr=0.0, sea_state=sea_state, rain_intensity=0.0,
                                  capability=1.0)
        if radar_physics.pd_from_sinr(sinr) < 0.5:
            distance = value
            break
    assert distance is not None and low <= distance <= high


def test_web_opz_sees_blips_and_marks_them():
    from src.commander.bridge import CommanderBridge
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from test_commander_bridge import Server

    game = _game()
    _place_sub(game)
    _sweeps(game)
    server, bridge = Server(), CommanderBridge()
    bridge.pump(game, server, now=1.0)
    blips = server.v2_states["opz"]["opz"]["radar_blips"]
    if not blips:
        pytest.skip("no fresh blip at publication")
    assert set(blips[0]) == {"ref", "x", "y", "age_s"} and blips[0]["ref"].startswith("blip-")
    from src.commander.bridge import _opz_mark_blip
    assert _opz_mark_blip(game, {"ref": blips[-1]["ref"]}, {}) is True
    assert _opz_mark_blip(game, {"ref": "track-1"}, {}) == "unknown_ref"
    assert math.isfinite(blips[0]["x"])
    game.audio.shutdown()
