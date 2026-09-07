"""Cross-system contracts exposed by the workstation/model review."""

import json
import math

import numpy as np
import pygame
import pytest

from src.core import config
from src.core.game import Game
from src.core.station import Station
from src.sensors.tracks import TrackPicture
from src.ui import map_view, sonar_view


def observe(picture, now, bearing=90.0):
    return picture.observe(track_id="S-1", kind="SURFACE", target_id=1,
                           source="RADAR-S", bearing=bearing, range_nm=10.0,
                           observer_x=0., observer_y=0., course=None,
                           quality=.8, now=now, label="S-1")


def test_picture_reads_are_pure_and_reacquisition_does_not_depend_on_reads():
    first, second = TrackPicture(2.), TrackPicture(2.)
    observe(first, 0.)
    observe(second, 0.)
    before = first.serialize()
    assert first.tracks(3.) == []
    assert first.serialize() == before
    observe(first, 3.5, 120.)
    observe(second, 3.5, 120.)
    assert first.serialize() == second.serialize()
    assert len(first.tracks(3.5)[0].measurement_history) == 1


def test_air_picture_skips_terrain_queries_for_ineligible_sources(monkeypatch):
    game = Game(seed=10, audio_enabled=False)
    game.surface_radar_on = game.air_radar_on = False
    game.asms = []
    game.flights.flights = []
    for ship in game.civilians + game.warships:
        ship.emitter = False
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *a:
                        pytest.fail("ineligible sensors must reject before terrain work"))
    game._update_air_picture()


def test_lost_sonar_fix_is_not_retained_by_common_picture():
    picture = TrackPicture(30.)
    args = dict(track_id="U-1", kind="SUB", target_id=1, observer_x=0.,
                observer_y=0., course=None, quality=.8, label="K1")
    track = picture.observe(**args, now=1., source="SONAR-PING",
                            bearing=90., range_nm=10.)
    picture.observe(**args, now=2., source="SONAR-BRG", bearing=120., range_nm=None)
    assert track.x is track.y is track.range_nm is None
    assert track.bearing == 120.


@pytest.mark.parametrize("station,key,field", [
    (Station.BRIDGE, pygame.K_RIGHT, "target_course"),
    (Station.WEAPONS, pygame.K_UP, "torpedo_depth"),
])
def test_held_operator_adjustment_uses_wall_not_accelerated_time(station, key, field):
    game = Game(seed=10, audio_enabled=False)
    game.station = station
    game._update_sim = lambda dt: None
    game._update_audio = lambda dt: None
    results = []
    for scale in (1, 120):
        game.time_scale_idx = config.TIME_SCALE_STEPS.index(scale)
        game.ship.target_course = 0.
        game.torpedo_depth = 60.
        game.held = {key}
        game.update(.1)
        results.append(getattr(game.ship if field == "target_course" else game, field))
    assert results[0] == results[1]


def test_map_render_does_not_change_saved_camera():
    game = Game(seed=10, audio_enabled=False)
    before = dict(vars(game.map_view))
    game.ship.x += 1.
    map_view.draw_map_view(game)
    assert vars(game.map_view) == before


@pytest.mark.parametrize("language,word", [("en", "Snapshot"), ("de", "Momentaufnahme")])
def test_pinned_tooltip_is_explicitly_a_localized_snapshot(language, word):
    game = Game(seed=10, audio_enabled=False, language=language)
    game.sim_t = 23.5
    assert game._pin_tooltip_at((700, 150))
    assert word in game.pinned_tooltip["lines"][0]
    assert "23.5" in game.pinned_tooltip["lines"][0]


def test_audio_drains_two_blocks_in_order_and_retries_queue_backpressure(monkeypatch):
    game = Game(seed=10, audio_enabled=False)
    game.station = Station.SONAR
    receiver = game.sonar.receiver
    game._sonar_audio_sequence = receiver.sequence
    for _ in range(2):
        receiver.update([], 0, 12, .2, 2, 6)
    blocks = receiver.blocks_since(game._sonar_audio_sequence)
    calls = []
    accept = iter((True, False, True))
    monkeypatch.setattr(game.audio, "play_sonar", lambda samples, *args, **kwargs:
                        calls.append(samples.copy()) or next(accept))
    monkeypatch.setattr(game.audio, "update_engine", lambda *args, **kwargs: None)
    game._update_audio(.016)
    assert game._sonar_audio_sequence == blocks[0][0]
    game._update_audio(.016)
    assert game._sonar_audio_sequence == blocks[1][0]
    np.testing.assert_allclose(calls[0], game.sonar.listening_samples(blocks[0][1]))
    np.testing.assert_array_equal(calls[1], calls[2])


def test_accelerated_audio_is_bounded_preview_and_pans_the_listening_beam(monkeypatch):
    game = Game(seed=10, audio_enabled=False)
    game.station = Station.SONAR
    game.time_scale_idx = config.TIME_SCALE_STEPS.index(5)
    game.sonar.listen_bearing = 75.
    game._sonar_audio_sequence = 0
    for _ in range(5):
        game.sonar.receiver.update([], 75, 12, .2, 2, 6)
    stops, calls, text = [], [], []
    monkeypatch.setattr(game.audio, "stop_sonar", lambda **kw: stops.append(kw))
    monkeypatch.setattr(game.audio, "play_sonar", lambda samples, *args, **kwargs:
                        calls.append(kwargs) or True)
    monkeypatch.setattr(game.audio, "update_engine", lambda *args, **kwargs: None)
    game._update_audio(.1)
    assert not calls
    game._update_audio(.15)
    assert len(calls) == 1 and calls[0]["bearing_deg"] == 75.
    assert stops == [{"immediate": True}]
    monkeypatch.setattr(sonar_view, "_text", lambda screen, value, *a, **kw: text.append(value))
    sonar_view.draw_sonar_view(game)
    assert any("5x" in str(value) for value in text)


def test_hfdf_fix_uses_raw_measurement_and_range_scaled_covariance():
    sigmas = []
    for scale in (1., 2.):
        game = Game(seed=10, audio_enabled=False)
        game.hfdf_log = [dict(track_id="H-1", label="HF", bearing=45.,
                              observer_x=0., observer_y=0., t=0.)]
        game.sim_t = 60.
        report = game.radio_picture.observe(
            track_id="H-1", kind="HF", target_id=1, source="HFDF", bearing=315.,
            range_nm=None, observer_x=10. * scale, observer_y=0., course=None,
            quality=.8, now=60., label="HF")
        report.bearing = 300.  # Display filtering must not move the captured ray.
        game.capture_hfdf()
        fix = game.hfdf_fixes["H-1"]
        assert (fix["x"], fix["y"]) == pytest.approx((5. * scale, -5. * scale))
        xx, xy, yy = fix["covariance_nm2"]
        assert all(math.isfinite(value) for value in (xx, xy, yy))
        assert xx * yy - xy * xy >= 0
        sigmas.append(fix["sigma_nm"])
    assert sigmas[1] == pytest.approx(2 * sigmas[0])


@pytest.mark.parametrize("covariance", [[1], [1, 2, 1], [-1, 0, 1],
                                       [True, 0, 1], [1, "bad", 1]])
def test_invalid_hfdf_covariance_rejects_before_replacing_live_state(tmp_path, covariance):
    game = Game(seed=10, audio_enabled=False)
    before = game.save_state()
    state = game.save_state()
    state["hfdf_fixes"] = {"H-1": dict(label="HF", x=20, y=20, t=0,
                                     sigma_nm=1., covariance_nm2=covariance)}
    path = tmp_path / "bad-covariance.json"
    path.write_text(json.dumps(state), encoding="utf-8")
    assert not game.load_game(str(path))
    assert game.save_state() == before
