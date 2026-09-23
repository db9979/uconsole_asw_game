from types import SimpleNamespace

import pygame
import pytest

from src.core.game import Game
from src.core.station import Station
from src.sensors.esm import (
    ESMMeasurement,
    ESMPicture,
    ESMTrack,
    RadarSignal,
    SignalType,
    filter_and_sort_tracks,
    scan_for_signals,
    signal_state,
)


def _signal(power, distance):
    return RadarSignal(
        "R0123456789abcdef", "internal", 9e9, 800.0, "pulse",
        "search", SignalType.SURFACE_SEARCH, distance, 0.0, power, 1.0)


@pytest.mark.parametrize("power,limit", [("low", 60.0), ("medium", 100.0),
                                           ("high", 150.0)])
def test_power_class_range_boundaries_and_quality(power, limit):
    kwargs = dict(observer_x=0.0, observer_y=0.0, now=1.0,
                  maximum_range_nm=150.0, bearing_error_deg=3.0,
                  noise_for=lambda _signal: 0.25)
    edge = scan_for_signals([_signal(power, limit)], **kwargs)
    beyond = scan_for_signals([_signal(power, limit + .001)], **kwargs)

    assert len(edge) == 1
    assert edge[0].quality == pytest.approx(.35)
    assert beyond == ()
    assert edge == scan_for_signals([_signal(power, limit)], **kwargs)


def test_land_occlusion_still_precedes_public_measurement():
    assert scan_for_signals(
        [_signal("high", 10.0)], observer_x=0.0, observer_y=0.0, now=1.0,
        maximum_range_nm=150.0, bearing_error_deg=3.0,
        noise_for=lambda _signal: 0.0,
        line_of_sight=lambda _signal: False) == ()


def _track(key, *, first=0.0, last=1.0, quality=.8, frequency=9e9):
    return ESMTrack(key, 0.0, 0.0, 90.0, 2.0, frequency, 800.0,
                    "pulse", quality, first, last)


def test_confirmation_and_memory_state_boundaries():
    low = _track("E0000000000000001", first=1.0, last=1.0)
    assert signal_state(low, 1.0, "low") == "UNCONFIRMED"
    low.last_seen = 2.0
    assert signal_state(low, 2.0, "low") == "LIVE"
    assert signal_state(low, 4.001, "low") == "RECENT"
    assert signal_state(low, 92.0, "low") == "RECENT"
    assert signal_state(low, 92.001, "low") == "MEMORY"

    urgent = _track("E0000000000000002", first=5.0, last=5.0)
    assert signal_state(urgent, 5.0, "high") == "LIVE"
    assert signal_state(urgent, 5.0, "critical") == "LIVE"


def test_shared_filters_sort_and_keep_active_ecm_visible():
    tracks = (
        _track("E0000000000000001", first=0.0, last=10.0,
               quality=.6, frequency=1.5e9),
        _track("E0000000000000002", first=0.0, last=1.0,
               quality=.9, frequency=9e9),
        _track("E0000000000000003", first=10.0, last=10.0,
               quality=.95, frequency=25e9),
    )
    threats = {tracks[0].track_key: "medium", tracks[1].track_key: "low",
               tracks[2].track_key: "critical"}
    analyze = lambda track: SimpleNamespace(threat_level=threats[track.track_key])

    shown = filter_and_sort_tracks(tracks, 10.0, analyze)
    assert [item.track_key for item in shown] == [tracks[2].track_key,
                                                  tracks[0].track_key,
                                                  tracks[1].track_key]
    assert filter_and_sort_tracks(
        tracks, 10.0, analyze, status="MEMORY", minimum_threat="HIGH",
        band="I_J", jamming_keys={tracks[1].track_key}) == (tracks[1],)


def test_capacity_eviction_protects_annotation_and_ecm_keys():
    picture = ESMPicture(maximum=2)
    picture.observe_batch([
        ESMMeasurement(0, 0, 10, 2, 1e9, 100, "pulse", .8, 0),
        ESMMeasurement(0, 0, 200, 2, 10e9, 900, "pulse", .7, 0),
    ], 0)
    protected = picture.tracks(0)[0].track_key
    picture.observe_batch([
        ESMMeasurement(0, 0, 100, 2, 20e9, 1500, "continuous_wave", .9, 1),
    ], 1, protected_keys={protected})
    keys = {track.track_key for track in picture.tracks(1)}
    assert protected in keys
    assert len(keys) == 2


def test_uconsole_filters_reconcile_selection_without_persistence():
    game = Game(seed=9021, audio_enabled=False)
    game.station = Station.ELOKA
    game.esm_picture._tracks = {
        "E0000000000000001": _track("E0000000000000001", frequency=1.5e9),
        "E0000000000000002": _track("E0000000000000002", frequency=9e9),
    }
    game.esm_picture.track_seq = 2
    game.sim_t = 1.0
    game.eloka_status_filter = "ALL"
    game.eloka_selected_track_key = "E0000000000000001"

    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_b, mod=0))
    assert game.eloka_band_filter == "A_C"
    assert game.eloka_selected_track_key is None
    assert "eloka_status_filter" not in game.save_state()["esm"]
