"""A raised periscope or snorkel head is seen by its feather (1.3.117)."""

from src.core import config
from src.core.game import Game
from src.sensors import visual as visual_physics


def _game(seed=83):
    game = Game(seed=seed, start_menu=False, audio_enabled=False, language="en")
    game.world.land_blocks_line = lambda *args: False
    game._lookout_environment = lambda: dict(
        visibility_nm=config.WEATHER_VISIBILITY_MAX_NM, night=False,
        illumination=1.0, sea_state=1.0)
    game.crew_effect = lambda: 1.0
    return game


def _crewed_sub(game, distance_nm, speed_kn, mast=True):
    sub = game.subs[0]
    sub.x, sub.y = game.ship.x + distance_nm, game.ship.y
    sub.depth = sub.target_depth = 12.0
    game.claim_opfor_sub()
    boat = game.opfor
    boat.orders.mast = mast
    sub.speed = speed_kn
    return sub


def _lookout_tracks(game):
    return [track for track in game.air_picture.tracks(game.sim_t)
            if track.source == "LOOKOUT"]


def test_feather_grows_with_speed():
    slow = visual_physics.feather_strength(0.0)
    assert slow == visual_physics.FEATHER_BARE_FRACTION
    assert visual_physics.feather_strength(3.0) < visual_physics.feather_strength(6.0)
    assert visual_physics.feather_strength(20.0) == 1.0


def test_lookout_sees_a_fast_periscope_but_not_a_slow_one():
    game = _game()
    _crewed_sub(game, 2.5, 8.0)
    game._update_lookout_picture()
    seen = _lookout_tracks(game)
    assert seen and all(track.kind in ("SURFACE", "SUB") for track in seen)
    game.audio.shutdown()

    game = _game()
    _crewed_sub(game, 2.5, 1.0)
    game._update_lookout_picture()
    assert not _lookout_tracks(game)
    game.audio.shutdown()


def test_no_feather_with_the_mast_down():
    game = _game()
    _crewed_sub(game, 1.0, 8.0, mast=False)
    game._update_lookout_picture()
    assert not _lookout_tracks(game)
    game.audio.shutdown()


def test_close_periscope_is_recognized_as_a_submarine():
    game = _game()
    _crewed_sub(game, 0.8, 8.0)
    game._update_lookout_picture()
    track = _lookout_tracks(game)[0]
    assert track.kind == "SUB" and "PERISCOPE" in track.label
    assert any(report["code"] == "PERISCOPE" for report in game.lookout_reports)
    game.audio.shutdown()


def test_helicopter_crew_sees_the_feather():
    game = _game()
    sub = _crewed_sub(game, 12.0, 8.0)
    helo = game.helo
    helo.state = "AUF"
    helo.x, helo.y = sub.x - 2.0, sub.y
    helo.dip_state = "STOWED"
    game.sim_t = 10.0
    game._update_aircrew_eyes(1.0)
    tracks = [track for track in game.air_picture.tracks(game.sim_t)
              if track.source == "HELO-EYE"]
    assert tracks and tracks[0].target_id == 0
    game.audio.shutdown()


def test_crewed_boat_warns_of_a_visible_feather():
    game = _game()
    sub = _crewed_sub(game, 20.0, 2.0)
    for _ in range(3):
        game._update_sim(0.1)
    sub.speed = sub.order_speed = 9.0
    for _ in range(3):
        game._update_sim(0.1)
    texts = [str(row["text"]) for row in game.opfor.feed]
    assert any("feather" in text for text in texts)
    game.audio.shutdown()
