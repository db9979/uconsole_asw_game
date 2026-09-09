import copy
import random
from types import SimpleNamespace

import pygame
import pytest

from src.core.game import Game
from src.core.station import Station
from src.data.catalog import CATALOG
from src.enemies.surface import SurfaceShip
from src.sensors.esm import (
    ESM_MAX_TRACKS,
    ESMCorrelationEvidence,
    ESMMeasurement,
    ESMPicture,
    correlate_observations,
    rank_emitters,
    valid_esm_state,
)


def measurement(*, bearing=90.0, frequency=9.2e9, prf=800.0,
                modulation="pulse", quality=.8, now=1.0):
    return ESMMeasurement(
        observer_x=10.0, observer_y=20.0, bearing=bearing,
        bearing_uncertainty_deg=2.0, frequency_hz=frequency,
        prf_hz=prf, modulation_code=modulation, quality=quality,
        observed_at=now)


def emitting_game(monkeypatch, *, radar=False):
    game = Game(seed=709, audio_enabled=False)
    profile = game.runtime_catalog.surfaces["warship_01"]
    actor = SurfaceShip(game.ship.x + 4.0, game.ship.y,
                        random.Random(17), hostile=True, profile=profile,
                        runtime_catalog=game.runtime_catalog)
    actor.emitter = True
    game.civilians = []
    game.warships = [actor]
    game.flights.flights = []
    game.asms = []
    game.surface_radar_on = radar
    game.air_radar_on = False
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)
    return game, actor


def test_picture_uses_opaque_monotonic_keys_and_deterministic_bounds():
    picture = ESMPicture(maximum=3)
    picture.observe_batch([
        measurement(bearing=float(index), frequency=1e9 + index * 2e8)
        for index in range(5)
    ], 1.0)

    assert len(picture.tracks(1.0)) == 3
    assert picture.track_seq == 3
    assert [track.track_key for track in picture.tracks(1.0)] == [
        "E0000000000000001", "E0000000000000002", "E0000000000000003"]
    assert all("target" not in row and "entity" not in row
               and "emitter_key" not in row for row in picture.serialize())


def test_large_measurement_batch_never_allocates_above_picture_bound():
    picture = ESMPicture()
    picture.observe_batch((
        measurement(bearing=float(index % 360),
                    frequency=1e9 + index * 1e6)
        for index in range(10_000)
    ), 1.0)
    assert len(picture.tracks(1.0)) == ESM_MAX_TRACKS
    assert picture.track_seq == ESM_MAX_TRACKS


def test_association_depends_on_measurements_not_input_order():
    rows = [measurement(bearing=20.0, frequency=3e9),
            measurement(bearing=200.0, frequency=10e9)]
    first, second = ESMPicture(), ESMPicture()
    first.observe_batch(rows, 1.0)
    second.observe_batch(reversed(rows), 1.0)
    assert first.serialize() == second.serialize()

    updates = [measurement(bearing=21.0, frequency=3e9, now=1.5),
               measurement(bearing=201.0, frequency=10e9, now=1.5)]
    first.observe_batch(updates, 1.5)
    second.observe_batch(reversed(updates), 1.5)
    assert first.serialize() == second.serialize()


def test_candidate_ranking_uses_only_observed_fingerprint():
    picture = ESMPicture()
    picture.observe_batch([measurement()], 1.0)
    track = picture.tracks(1.0)[0]

    ranked = rank_emitters(track, CATALOG.emitters)
    assert ranked
    assert ranked == rank_emitters(copy.copy(track), CATALOG.emitters)
    assert [item.emitter_key for item in ranked] == sorted(
        (item.emitter_key for item in ranked),
        key=lambda key: (-next(item.score for item in ranked
                               if item.emitter_key == key), key))


def test_correlation_never_reads_hidden_target_identity():
    picture = ESMPicture()
    picture.observe_batch([measurement(bearing=90.0)], 1.0)
    track = picture.tracks(1.0)[0]

    class Evidence:
        track_id = "R-7"
        source = "RADAR-S"
        bearing = 90.0
        bearing_uncertainty_deg = 1.0
        x = 14.0
        y = 20.0
        observed_at = 1.0

        @property
        def target_id(self):
            raise AssertionError("hidden identity accessed")

    matches = correlate_observations(track, [Evidence()], 1.0)
    assert [(item.track_id, item.source) for item in matches] == [("R-7", "RADAR-S")]


def test_game_correlation_does_not_read_or_publish_producer_track_id(monkeypatch):
    game, _ = emitting_game(monkeypatch, radar=False)
    game.sim_t = 1.0
    game._update_esm_picture()

    class Evidence:
        source = "RADAR-S"
        bearing = 90.0
        bearing_uncertainty_deg = 1.0
        x = game.ship.x + 4.0
        y = game.ship.y
        position_seen = last_seen = 1.0

        @property
        def track_id(self):
            raise AssertionError("producer track identity accessed")

    game.air_picture._tracks = {"hidden": Evidence()}
    correlations = game.eloka_correlations(game.eloka_tracks()[0])
    assert correlations[0].track_id.startswith("OBS-")
    assert correlations[0].track_id != "hidden"


def test_correlation_reference_is_stable_when_unrelated_evidence_changes(monkeypatch):
    game, _ = emitting_game(monkeypatch, radar=False)
    game.sim_t = 1.0
    game._update_esm_picture()
    track = game.eloka_tracks()[0]

    def evidence(bearing):
        return SimpleNamespace(
            track_id="hidden", source="RADAR-S", bearing=bearing,
            bearing_uncertainty_deg=1.0, x=None, y=None,
            position_seen=None, last_seen=1.0)

    game.air_picture._tracks = {"matching": evidence(track.bearing)}
    first = game.eloka_correlations(track)[0].track_id
    game.air_picture._tracks["unrelated"] = evidence((track.bearing + 180) % 360)
    assert game.eloka_correlations(track)[0].track_id == first


def test_future_correlation_evidence_is_rejected():
    picture = ESMPicture()
    picture.observe_batch([measurement()], 1.0)
    evidence = ESMCorrelationEvidence(
        track_id="OBS-X", source="RADAR-S", bearing=90.0,
        bearing_uncertainty_deg=1.0, x=None, y=None, observed_at=2.0)
    assert not correlate_observations(picture.tracks(1.0)[0], [evidence], 1.0)


def test_radar_off_esm_on_and_parallel_evidence(monkeypatch):
    game, actor = emitting_game(monkeypatch, radar=False)
    game.sim_t = .5
    game._update_air_picture()
    game._update_esm_picture()

    assert game.eloka_tracks()
    assert all(track.source != "ESM" for track in game.air_picture.tracks(game.sim_t))

    game.surface_radar_on = True
    game.sim_t = 1.0
    game._update_air_picture()
    game._update_esm_picture()
    assert f"W-{actor.id}" in game.air_picture._tracks
    assert game.eloka_tracks()


def test_shared_correlation_picture_is_bounded():
    game = Game(seed=710, audio_enabled=False)
    for index in range(600):
        game.air_picture.observe(
            track_id=f"R-{index}", kind="SURFACE", target_id=index,
            source="RADAR-S", bearing=float(index % 360), range_nm=5.0,
            observer_x=game.ship.x, observer_y=game.ship.y, course=None,
            quality=.8, now=game.sim_t, label=f"R-{index}")
    assert len(game.air_picture._tracks) == game.air_picture.maximum


def test_opz_destruction_disables_new_measurements_and_picture_expires(monkeypatch):
    game, _ = emitting_game(monkeypatch)
    game.sim_t = .5
    game._update_esm_picture()
    assert game.eloka_tracks()
    assert len(game.damage.compartments) == 9

    game.damage.compartments["opz"].state = "ZERSTOERT"
    selected = game.eloka_tracks()[0].track_key
    game.eloka_selected_track_key = selected
    game._cycle_eloka_track(1)
    game._cycle_eloka_annotation()
    assert game.eloka_selected_track_key == selected
    assert not game.eloka_annotations
    assert not game.eloka_candidates()
    assert not game.eloka_correlations()
    game.sim_t += game.esm_picture.stale_s + .1
    game._update_esm_picture()
    assert not game.eloka_tracks()


def test_save_v10_round_trip_preserves_picture_selection_annotation_and_station(
        monkeypatch):
    game, _ = emitting_game(monkeypatch)
    game.sim_t = .5
    game._update_esm_picture()
    track = game.eloka_tracks()[0]
    game.eloka_selected_track_key = track.track_key
    game.eloka_annotations[track.track_key] = "emitter.warship_01.radar"
    game.station = Station.ELOKA
    game._esm_acc = .25

    state = game.save_state()
    assert state["ui"]["station"] == "ELOKA"
    assert valid_esm_state(state["esm"], game.sim_t,
                           game.runtime_catalog.emitters)
    restored = Game(seed=1, audio_enabled=False)
    restored.load_state(state)

    assert restored.station is Station.ELOKA
    assert restored.esm_picture.serialize() == game.esm_picture.serialize()
    assert restored.eloka_selected_track_key == track.track_key
    assert restored.eloka_annotations == game.eloka_annotations
    assert restored._esm_acc == .25


def test_normal_update_continuation_preserves_esm_scheduler_and_tracks(monkeypatch):
    game, _ = emitting_game(monkeypatch)
    for _ in range(3):
        game.update(.1)
    restored = Game(seed=3, audio_enabled=False)
    restored.load_state(game.save_state())
    monkeypatch.setattr(restored.world, "land_blocks_line", lambda *args: False)

    for _ in range(12):
        game.update(.1)
        restored.update(.1)
        assert restored._esm_acc == pytest.approx(game._esm_acc)
        assert restored.esm_picture.serialize() == game.esm_picture.serialize()
        assert restored.esm_picture.track_seq == game.esm_picture.track_seq


def test_v10_requires_esm_and_malformed_esm_is_transactional(monkeypatch):
    game, _ = emitting_game(monkeypatch)
    state = game.save_state()
    legacy = copy.deepcopy(state)
    del legacy["esm"]
    restored = Game(seed=2, audio_enabled=False)
    restored_before = restored.save_state()
    assert not restored._load_save_data(legacy)
    assert restored.save_state() == restored_before

    before = game.save_state()
    malformed = copy.deepcopy(before)
    malformed["esm"]["picture"] = [{"bearing": 1.0}]
    assert not game._load_save_data(malformed)
    assert game.save_state() == before


@pytest.mark.parametrize(("field", "value"), [
    ("emitter", "false"),
    ("sensor_seed", -1),
    ("sensor_seed", 1.5),
    ("sensor_seed", 2**31),
])
def test_malformed_esm_source_state_is_rejected_transactionally(
        monkeypatch, field, value):
    game, _ = emitting_game(monkeypatch)
    before = game.save_state()
    malformed = copy.deepcopy(before)
    malformed["warships"][0][field] = value
    assert not game._load_save_data(malformed)
    assert game.save_state() == before


def test_malformed_or_oversized_correlation_sources_are_rejected(monkeypatch):
    game, _ = emitting_game(monkeypatch, radar=True)
    game._update_air_picture()
    before = game.save_state()

    malformed = copy.deepcopy(before)
    malformed["air_picture"][0]["bearing"] = "east"
    assert not game._load_save_data(malformed)
    assert game.save_state() == before

    oversized = copy.deepcopy(before)
    oversized["flights"]["items"] = [{}] * 5
    assert not game._load_save_data(oversized)
    assert game.save_state() == before


def test_key_nine_and_eloka_controls_are_station_owned(monkeypatch):
    game, _ = emitting_game(monkeypatch)
    game.sim_t = .5
    game._update_esm_picture()
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_9))
    assert game.station is Station.ELOKA
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    selected = game.eloka_selected_track_key
    assert selected is not None
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_c))
    assert game.eloka_annotation(selected) is not None


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.0, 360.0])
def test_invalid_bearings_are_rejected(bad):
    picture = ESMPicture(maximum=ESM_MAX_TRACKS)
    with pytest.raises(ValueError):
        picture.observe_batch([measurement(bearing=bad)], 1.0)
