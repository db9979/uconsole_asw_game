"""ELOKA list order: emitter groups, the OPEN status and the list switches
(display policy only; the ESM picture itself is unchanged)."""

import pygame

from src.core.game import Game
from src.core.station import Station
from src.sensors.esm import (ESMTrack, collapse_groups, filter_and_sort_tracks,
                             group_tracks, same_signal_kind)
from src.ui import pointer
from src.ui.stations.eloka import draw_eloka_view, filter_chip_rects, eloka_regions, short_key


def _track(number, bearing, *, frequency=9.41e9, modulation="pulse", prf=1000.0,
           last=1.0):
    key = f"E{number:016x}"
    return ESMTrack(key, 0.0, 0.0, bearing, 1.7, frequency, prf, modulation,
                    .8, 0.0, last)


def _game(tracks):
    game = Game(seed=9022, audio_enabled=False)
    game.station = Station.ELOKA
    game.esm_picture._tracks = {track.track_key: track for track in tracks}
    game.esm_picture.track_seq = max(int(track.track_key[1:], 16) for track in tracks)
    game.sim_t = 1.0
    return game


def test_alike_intercepts_in_one_direction_form_one_group():
    a, b, c = _track(1, 205.0), _track(2, 209.0), _track(3, 212.0)
    other_band = _track(4, 206.0, frequency=3.05e9)
    other_mod = _track(5, 207.0, modulation="pulse_doppler")
    far = _track(6, 54.0)
    groups = group_tracks((far, other_mod, c, b, a, other_band))
    # Key order decides the anchor; members join the first matching anchor
    # only (no chaining from b to c beyond the anchor's gate).
    assert groups[a.track_key] == a.track_key
    assert groups[b.track_key] == a.track_key
    assert groups[c.track_key] == c.track_key
    assert {groups[t.track_key] for t in (other_band, other_mod, far)} == {
        other_band.track_key, other_mod.track_key, far.track_key}
    assert same_signal_kind(a, _track(9, 208.0, modulation="unknown"))


def test_classified_and_jammed_intercepts_stand_alone():
    a, b = _track(1, 100.0), _track(2, 101.0)
    assert group_tracks((a, b), solo_keys={a.track_key}) == {
        a.track_key: a.track_key, b.track_key: b.track_key}


def test_collapse_keeps_list_order_and_members():
    a, b, c = _track(1, 100.0), _track(2, 102.0), _track(3, 30.0)
    groups = group_tracks((a, b, c))
    collapsed = collapse_groups((b, c, a), groups)
    assert [(lead.track_key, [m.track_key for m in members])
            for lead, members in collapsed] == [
        (b.track_key, [b.track_key, a.track_key]), (c.track_key, [c.track_key])]


def test_open_status_hides_classified_intercepts():
    a, b = _track(1, 100.0), _track(2, 40.0)
    shown = filter_and_sort_tracks((a, b), 1.0, lambda _track: None, status="OPEN",
                                   annotated_keys={a.track_key})
    assert [track.track_key for track in shown] == [b.track_key]


def test_keys_step_groups_members_and_switches():
    tracks = (_track(1, 205.0), _track(2, 208.0), _track(3, 210.0), _track(4, 54.0))
    game = _game(tracks)
    game.eloka_status_filter = "ALL"
    assert len(game.eloka_visible_groups()) == 2
    game.eloka_selected_track_key = tracks[0].track_key
    press = lambda key, mod=0: game.handle_event(
        pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod))
    press(pygame.K_RIGHT)
    assert game.eloka_selected_track_key in {tracks[1].track_key, tracks[2].track_key}
    assert len(game.eloka_selected_group()) == 3
    # The selected member stands for its group in the list.
    assert game.eloka_selected_track_key in {
        track.track_key for track in game.eloka_listed_tracks()}
    press(pygame.K_DOWN)
    assert game.eloka_selected_track_key == tracks[3].track_key
    press(pygame.K_z)
    assert game.eloka_group_emitters is False
    assert len(game.eloka_visible_groups()) == 4
    press(pygame.K_f)
    assert game.eloka_status_filter == "OPERATIONAL"
    press(pygame.K_f)
    assert game.eloka_status_filter == "OPEN"
    assert "eloka_group_emitters" not in game.save_state()["esm"]


def test_switch_chips_are_clickable_keys():
    game = _game((_track(1, 205.0), _track(2, 208.0)))
    pointer.reset()
    draw_eloka_view(game)
    regions = eloka_regions(page=0)
    if regions["cards"].w <= 0:
        return
    keys = {(target.key, target.mod) for target in pointer.targets("station")
            if target.key is not None}
    assert (pygame.K_f, 0) in keys
    assert (pygame.K_f, pygame.KMOD_SHIFT) in keys
    assert (pygame.K_f, pygame.KMOD_CTRL) in keys
    assert (pygame.K_z, 0) in keys
    assert len(filter_chip_rects(regions["picture"])) == 4


def test_short_key_reads_the_hexadecimal_running_number():
    assert short_key("E000000000000001b") == "E27"
    assert short_key("E0000000000000012") == "E18"
