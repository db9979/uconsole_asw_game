"""Evidence lifetime, source separation and read-only historical instruments."""

import copy
import math
import random
from types import SimpleNamespace as NS

import numpy as np
import pygame
import pytest

from src.core import config
from src.core.i18n import Translator, translation_scope
from src.enemies.sub import Sub
from src.ship.ship import Ship
from src.sonar.sonar import Contact, SonarSystem
from src.sonar.tma import BearingTrack, solve_tma
from src.ui import layout, sonar_view as view


def solution(pos=(3.0, -4.0), quality=.8):
    return NS(pos=pos, course=40.0, speed=8.0, quality=quality)


@pytest.mark.parametrize("source", ["tma", "buoy"])
def test_passive_reports_do_not_refresh_position_or_motion(source):
    contact = Contact(1, 1, "passiv", "sub")
    contact.update_tma(solution(), 0)
    if source == "buoy":
        contact.update_buoy(4, -3, .8, 0)
    for t in (1, 60, config.SONAR_CONTACT_LOST_S):
        contact.update_passive(95, 1, .8, "", t)
        assert contact.positioned and contact.range_seen == 0
        assert contact.bearing != contact.passive_bearing
    raw = list(contact.raw_bearings)
    contact.update_passive(95, 1, .8, "", config.SONAR_CONTACT_LOST_S + 1)
    assert not contact.positioned
    assert contact.range_source is None
    assert contact.observed_x is contact.observed_y is None
    assert contact.tma_pos is contact.tma_course is contact.tma_speed is None
    assert contact.tma_quality == 0
    assert contact.depth_est is contact.depth_sigma_m is None
    assert contact.bearing == contact.passive_bearing
    assert contact.raw_bearings[:len(raw)] == raw


def test_hidden_tma_motion_expires_while_ping_remains_fresh():
    contact = Contact(1, 1, "passiv", "sub")
    contact.update_tma(solution(), 0)
    contact.update_ping(80, 6, 50, 1, 100)
    contact.expire_ping_fix(121)
    assert contact.tma_course is contact.tma_speed is None
    assert contact.range_source == "ping" and contact.depth_est == 50
    contact.update_buoy(4, -3, .8, 221)
    assert contact.range_source == "buoy"
    assert contact.depth_est is contact.depth_sigma_m is None


def test_legacy_tma_fix_uses_range_seen_but_undated_motion_is_not_rejuvenated():
    contact = Contact(1, 1, "passiv", "sub")
    contact.tma_pos, contact.tma_course, contact.tma_speed = (1, 2), 45, 6
    contact.range_source, contact.range_est, contact.range_seen = "tma", 3, 0
    contact.expire_ping_fix(120)
    assert contact.tma_pos == (1, 2)
    contact.expire_ping_fix(121)
    assert contact.tma_pos is None and contact.range_est is None


def test_buoy_filter_keeps_raw_fixes_separate_and_arbitrates_sources():
    contact = Contact(1, 1, "passiv", "sub")
    contact.update_passive(170, 1, .8, "", 0)
    raw = list(contact.raw_bearings)
    contact.update_tma(solution(), 0)
    contact.update_buoy(4, -3, .8, 1)
    contact.update_buoy(8, -6, .8, 3)
    assert contact.buoy_fixes == [(1, 4, -3, .8), (3, 8, -6, .8)]
    assert 4 < contact.observed_x < 8
    assert -6 < contact.observed_y < -3
    assert contact.bearing == pytest.approx(math.degrees(math.atan2(
        contact.observed_x, -contact.observed_y)))
    assert contact.range_est == pytest.approx(math.hypot(
        contact.observed_x, contact.observed_y))
    assert contact.raw_bearings == raw and contact.raw_bearing == 170
    position = contact.observed_x, contact.observed_y
    contact.update_tma(solution((20, 10)), 4)
    assert contact.range_source == "buoy"
    assert (contact.observed_x, contact.observed_y) == position
    contact.update_ping(90, 8, 50, 1, 5)
    contact.update_buoy(7, -5, .8, 6)
    assert contact.range_source == "ping"
    assert contact.buoy_fixes[-1] == (6, 7, -5, .8)
    for t in range(8, 400, 2):
        contact.update_buoy(7, -5, .8, t)
    assert len(contact.buoy_fixes) == config.BEARING_TRACK_MAX_PTS


def test_buoy_filter_substep_and_restored_continuation_are_stable():
    coarse, fine = Contact(1, 1, "passiv", "sub"), Contact(1, 1, "passiv", "sub")
    for contact in (coarse, fine):
        contact.update_buoy(1, 2, .8, 0)
    coarse.update_buoy(5, 6, .8, 2)
    for t in np.arange(.25, 2.01, .25):
        fine.update_buoy(5, 6, .8, t)
    assert coarse.observed_x == pytest.approx(fine.observed_x)
    restored = copy.deepcopy(fine)
    for contact in (fine, restored):
        contact.update_buoy(7, 8, .8, 4)
    assert vars(fine) == vars(restored)


def test_buoy_crossing_uses_valid_shorter_pair_without_ownship_passive_truth():
    ship = Ship(250, 250, speed_kn=0)
    world = NS(sea_state=0, thermocline_depth_m=lambda x, y: 100)
    sub = Sub(20, 20, 40, 0, "diesel_alt", random.Random(5))
    buoys = [NS(active=True, x=x, y=y, seq=i)
             for i, (x, y) in enumerate(((20, 18), (20, 22), (21, 20)), 1)]
    sonar = SonarSystem(5)
    sonar.update(.25, .25, ship, [sub], world, buoys=buoys)
    contact = sonar.contacts[sub.id]
    assert contact.range_source == "buoy"
    assert math.hypot(contact.observed_x - 20, contact.observed_y - 20) < .5
    assert contact.passive_bearing is None and contact.raw_bearings == []
    assert contact.bearing == pytest.approx(math.degrees(math.atan2(
        contact.observed_x - ship.x, -(contact.observed_y - ship.y))) % 360)


@pytest.mark.parametrize("mode", ["BOW", "TOWED"])
def test_receiver_uses_selected_array_not_fusion_or_ping(mode, monkeypatch):
    ship = Ship(250, 250, speed_kn=0)
    world = NS(sea_state=0, thermocline_depth_m=lambda x, y: 100)
    sub = Sub(252, 250, 40, 0, "diesel_alt", random.Random(5))
    sonar = SonarSystem(5)
    sonar.tow_state, sonar.tow_payout = sonar.STREAMED, 1.0
    sonar._tow_settle_s = config.SONAR_TOWED_SETTLE_S
    sonar._observed_bearing = lambda target, true, frigate, quality, array, t: (
        10.0 if array == "BOW" else 14.0)
    contact = sonar._get_contact(sub)
    contact._fx, contact._fy = ship.x, ship.y
    contact.update_ping(180, 3, 40, 1, 0)
    sonar.focus_locked = True
    captured = []
    monkeypatch.setattr(sonar.receiver, "update", lambda sources, *args, **kwargs:
                        captured.extend(sources))
    sonar.update(.25, .25, ship, [sub], world, mode=mode, focus_tgt=sub)
    report = contact.array_observations[mode]
    assert captured[0]["bearing"] == report["bearing"]
    assert captured[0]["level"] == report["quality"]
    assert sonar.listen_bearing == report["bearing"]
    assert contact.bearing == 180 and contact.passive_bearing != 180
    sonar.advance_mechanics(.25, 5, ship)
    assert contact.array_observations == {}
    assert contact.fusion_status == "KEINE DATEN"
    assert contact.fusion_delta_deg is None and contact.fused_quality == 0


def test_tma_out_and_back_counts_intermediate_turn_but_not_heading_only_confidence():
    moving, straight = BearingTrack(), BearingTrack()
    for t in range(0, 241, 10):
        course = 90 if t < 80 or t >= 160 else 0
        x = min(t, 80) / 60 + max(0, t - 160) / 60
        y = -max(0, min(t - 80, 80)) / 60
        for track, fx, fy in ((moving, x, y), (straight, t / 60, 0)):
            # Stationary target at (5, -6), observed from each recorded pose.
            bearing = math.degrees(math.atan2(5 - fx, -(-6 - fy))) % 360
            track.add(t, bearing, fx, fy, course, .3)
    assert moving.course_span_deg() == 90
    assert view.tma_observation_summary(moving, 240)["geometry"] == "BRAUCHBAR"
    good, weak = solve_tma(moving), solve_tma(straight)
    assert good is not None and good.quality >= config.TMA_RANGE_MIN_QUALITY
    assert math.hypot(good.pos[0] - 5, good.pos[1] + 6) < .1
    assert weak is None or weak.quality < config.TMA_RANGE_MIN_QUALITY


def test_delayed_tma_solve_does_not_redate_measurement(monkeypatch):
    sonar = SonarSystem()
    target = NS(id=1)
    contact = Contact(1, 1, "passiv", "sub")
    sonar.contacts[1] = contact
    track = BearingTrack()
    track.add(10, 30, 0, 0, 0)
    sonar._tracks[1] = track
    monkeypatch.setattr("src.sonar.sonar.solve_tma", lambda tr: solution())
    sonar._update_tma(target, 20)
    assert contact.range_seen == contact.tma_seen == 10
    sonar.advance_mechanics(1, 131, Ship(0, 0))
    sonar._tma_versions.clear()
    sonar._update_tma(target, 131)
    assert not contact.positioned and contact.tma_pos is None


@pytest.fixture
def display_game(monkeypatch):
    pygame.font.init()
    monkeypatch.setattr(config, "STATION_RECT", config.FULL_STATION_RECT)
    sonar = SonarSystem()
    contact = Contact(1, 1, "passiv", "sub")
    contact.update_tma(solution(), 100)
    contact.range_est = 50
    contact.fusion_delta_deg = 3
    sonar.contacts[1] = contact
    sonar.receiver.peaks = [(float(i * 10), .8) for i in range(1, 7)]
    sonar.receiver.demon_spectrum[19] = .8
    sonar.demon_analysis = dict(blade_rate_hz=20, confidence=.8)
    sonar.signature_candidates = [(NS(label=f"Reference {i}"), .8) for i in range(3)]
    sonar.bt_profile = dict(t=90, thermocline_m=80, water_depth_m=300,
                            sea_state=3, depths_m=[0, 80, 300],
                            speeds_m_s=[1504, 1502.5, 1505], cz_bands_nm=[[40, 70]])
    sonar.echo_history = [dict(t=99, contact_id=1, bearing=45, range_nm=8,
                               range_sigma_nm=.4, depth_m=120,
                               depth_sigma_m=9, snr_db=10, mode="BOW")]
    return NS(screen=pygame.Surface((1280, 720)), sonar=sonar, sonar_page=0,
              ship=NS(x=0, y=0, course=20, speed=0), selected_contact=contact,
              preferences=NS(large_text=False), sim_t=100, tr=Translator("en"))


@pytest.mark.parametrize("language", ["en", "de"])
@pytest.mark.parametrize("large", [False, True])
@pytest.mark.parametrize("page", range(6))
def test_all_detail_rows_fit_actual_panel_and_font(display_game, language, large, page):
    game = display_game
    game.tr, game.preferences.large_text, game.sonar_page = Translator(language), large, page
    with layout.capture_geometry() as geometry, layout.capture_text() as texts:
        view.draw_sonar_view(game)
    details = next(item["rect"] for item in geometry if item["title"] == "sonar-details")
    with translation_scope(game.tr):
        expected = view._detail_rows(game, page)
    rendered = [item for item in texts if item["bounds"].x == details.x + 13]
    assert len(rendered) == len(expected)
    assert all(details.contains(item["rect"]) for item in rendered)
    assert all(item["bounds"].contains(item["rect"]) for item in rendered)
    assert all(a["rect"].bottom <= b["rect"].top for a, b in zip(rendered, rendered[1:]))


def test_detail_evidence_age_uses_each_page_source(display_game):
    game = display_game
    game.sonar.history_times = [99]
    game.sonar.lofar_times = [98]
    track = BearingTrack()
    track.add(70, 45, 0, 0, 0)
    game.sonar._tracks[game.selected_contact.target_id] = track
    game.selected_contact.tma_seen = 75

    with translation_scope(game.tr):
        assert view._detail_evidence(game, 0)[:2] == ("RECEIVER", 1)
        assert view._detail_evidence(game, 1)[:2] == ("RECEIVER", 2)
        assert view._detail_evidence(game, 2)[:2] == ("RECEIVER", 2)
        assert view._detail_evidence(game, 3)[:2] == ("SELECTED TMA TRACK", 25)
        assert view._detail_evidence(game, 4)[:2] == ("BT PROFILE", 10)
        assert view._detail_evidence(game, 5)[:2] == ("ACTIVE ECHO", 1)
        game.sonar.lofar_times = [60]
        assert view._detail_evidence(game, 1)[2] == "STALE"

        game.selected_contact = None
        game.sonar.bt_profile = None
        game.sonar.echo_history = []
        game.sonar._pending_pings = []
        for page in (3, 4, 5):
            source, age, state = view._detail_evidence(game, page)
            assert source != "RECEIVER" and age is None and state == "ABSENT"


def test_lofar_harmonics_require_current_operator_selection(display_game):
    game = display_game
    game.sonar_page = 1
    assert view._selected_harmonic(game) is None
    assert not any("2f" in str(row[0]) for row in view._detail_rows(game, 1))
    game.sonar_harmonic_hz = 20.0
    assert view._selected_harmonic(game) == 20.0
    assert any("2f" in str(row[0]) for row in view._detail_rows(game, 1))
    game.sonar.receiver.peaks = [(30.0, .8)]
    assert view._selected_harmonic(game) is None
    game.sonar.receiver.peaks = [(20.0, .8)]
    assert view._selected_harmonic(game) is None


@pytest.mark.parametrize("page", [0, 1])
def test_waterfall_tooltips_use_drawn_history_not_live_or_padding(display_game, page):
    game = display_game
    game.sonar_page = page
    game.sonar.broadband_history = [[.2] * 180, [.7] * 180]
    game.sonar.lofar_history = [[.2] * config.LOFAR_BINS, [.7] * config.LOFAR_BINS]
    game.sonar.history_times = game.sonar.lofar_times = [10, 20]
    game.sonar.lofar_bearings = [40, 80]
    game.sonar.listen_bearing = 200
    game.sonar.receiver.spectrum = [.99] * config.LOFAR_BINS
    main, _, _ = view._panels(game, page)
    plot = view._waterfall_plot(main, page)
    top = view.sonar_hit_target(game, (plot.centerx, plot.y))
    old_y = plot.y + math.ceil(plot.h / config.LOFAR_HISTORY_COLS)
    old = view.sonar_hit_target(game, (plot.centerx, old_y))
    assert any("0.700" in line for line in top["lines"])
    assert any("0.200" in line for line in old["lines"])
    assert any("20.0" in line for line in top["lines"])
    assert any("10.0" in line for line in old["lines"])
    assert view.sonar_hit_target(game, plot.center)["id"] == f"sonar:empty-history:{page}"
    if page == 1:
        assert any("080" in line for line in top["lines"])
        assert any("040" in line for line in old["lines"])
    game.tr = Translator("de")
    translated = view.sonar_hit_target(game, (plot.centerx, plot.y))
    assert translated["title"] != top["title"]


def test_tma_and_echo_tooltips_pick_actual_historical_points(display_game):
    game = display_game
    track = BearingTrack()
    track.add(0, 358, 0, 0, 0)
    track.add(10, 1, 0, 0, 20)
    track.add(20, 3, 0, 0, 0)
    game.sonar._tracks[1] = track
    game.sonar_page = 3
    main, _, _ = view._panels(game, 3)
    plot, _, _, points = view._tma_plot(main, track.pts)
    for point, measurement in zip(points, track.pts):
        payload = view.sonar_hit_target(game, point)
        assert payload["id"] == f"sonar:tma:{measurement.t:.1f}"
    assert view.sonar_hit_target(game, (plot.centerx, plot.bottom - 2)) is None
    game.sonar.echo_history.append(dict(game.sonar.echo_history[0], t=100,
                                        contact_id=2, bearing=230, range_nm=4))
    game.sonar_page = 5
    main, _, _ = view._panels(game, 5)
    echoes = view.active_echoes(game.sonar, 100)
    ascope, polar, maximum = view._active_geometry(main, echoes)
    for echo in echoes:
        for point in (view._echo_point(polar, maximum, echo),
                      view._ascope_point(ascope, maximum, echo)):
            payload = view.sonar_hit_target(game, point)
            assert payload["id"] == f"sonar:active-plot:{echo['contact_id']}:{echo['t']}"


@pytest.mark.parametrize("page,notch,rebuild", [(0, False, False), (0, True, False),
                                              (1, False, False), (1, True, True)])
def test_waterfall_cache_ignores_speed_unless_notch_uses_it(display_game, page, notch, rebuild):
    game = display_game
    game.sonar.broadband_history = [[.2] * 180]
    game.sonar.lofar_history = [[.2] * config.LOFAR_BINS]
    game.sonar.notch_enabled = notch
    view._WATERFALL_CACHE.clear()
    rect = pygame.Rect(0, 0, 400, 200)
    view._waterfall(game, page, rect)
    first = next(iter(view._WATERFALL_CACHE.values()))[0]
    game.ship.speed = 4
    view._waterfall(game, page, rect)
    assert len(view._WATERFALL_CACHE) == (2 if rebuild else 1)
    if not rebuild:
        assert next(iter(view._WATERFALL_CACHE.values()))[0] is first


def test_notch_gain_matches_scalar_vector_and_audition_controls():
    sonar = SonarSystem()
    sonar.gain_db, sonar.notch_enabled, sonar.listen_filtered = 12, True, True
    column = [.2] * config.LOFAR_BINS
    scalar = sonar.process_lofar_column(column, NS(speed=0))
    vector = view._process_lofar_rows(np.asarray([column]), (12, 0, 300, True, 0))[0]
    np.testing.assert_allclose(scalar, vector)
    index = min(range(len(column)), key=lambda i: abs(config.lofar_bin_freq(i) - 10))
    assert scalar[index] == pytest.approx(.2 * 10 ** (12 / 20) * .15)
    t = np.arange(sonar.receiver.sample_rate) / sonar.receiver.sample_rate
    sonar.receiver.samples = (.2 * np.sin(2 * np.pi * 10 * t)).astype(np.float32)
    sonar.listening_samples(sonar.receiver.samples, block_id=1)
    samples = sonar.listening_samples(sonar.receiver.samples.copy(), block_id=2)
    assert np.max(samples) == pytest.approx(scalar[index], rel=.01)


@pytest.mark.parametrize("gain_db", [-6, 0, 12, 24])
@pytest.mark.parametrize("notch", [False, True])
def test_lofar_scalar_vector_parity_includes_band_edges_and_clipping(gain_db, notch):
    sonar = SonarSystem()
    sonar.gain_db, sonar.notch_enabled = gain_db, notch
    sonar.band_low_hz, sonar.band_high_hz = 25, 240
    rows = np.linspace(0, 2, 3 * config.LOFAR_BINS).reshape(3, -1)
    original = rows.copy()
    scalar = np.asarray([sonar.process_lofar_column(row, NS(speed=8)) for row in rows])
    vector = view._process_lofar_rows(rows, (gain_db, 25, 240, notch, 8))
    frequencies = np.asarray([config.lofar_bin_freq(i) for i in range(config.LOFAR_BINS)])
    gain = 10 ** (gain_db / 20)
    in_band = (frequencies >= 25) & (frequencies <= 240)
    notched = in_band & (abs(frequencies - (10 + 1.9 * 8)) < 5)
    expected_notch = np.clip(rows[:, notched] * gain * (.15 if notch else 1), 0, 1)
    np.testing.assert_array_equal(scalar, vector)
    np.testing.assert_array_equal(vector[:, notched], expected_notch)
    np.testing.assert_array_equal(vector[:, ~in_band], 0)
    np.testing.assert_array_equal(rows, original)


@pytest.mark.parametrize("filtered", [False, True])
def test_listening_samples_processes_each_receiver_block_without_mutation(filtered):
    sonar = SonarSystem()
    sonar.gain_db, sonar.listen_filtered, sonar.notch_enabled = 12, filtered, True
    receiver = sonar.receiver
    for level in (.2, .8):
        receiver.update([dict(bearing=0, level=level, lines=[(28, 1, 0)], seed=1)],
                        0, 12, .1, 0, 0)
    blocks = receiver.blocks_since(0)
    assert len(blocks) == 2
    snapshots = [samples.copy() for _, samples in blocks]
    history = receiver._history.copy()
    state = (receiver.sequence, receiver.elapsed, receiver._rng.bit_generator.state,
             sonar.rng.getstate())
    outputs = [sonar.listening_samples(samples, block_id=sequence)
               for sequence, samples in blocks]
    assert not np.array_equal(outputs[0], outputs[1])
    retry_state = tuple(part.copy() for part in sonar._audition_ola_state) \
        if sonar._audition_ola_state is not None else None
    np.testing.assert_array_equal(
        outputs[-1], sonar.listening_samples(blocks[-1][1],
                                             block_id=blocks[-1][0]))
    if retry_state is not None:
        for before, after in zip(retry_state, sonar._audition_ola_state):
            np.testing.assert_array_equal(before, after)
    previous = overlap = None
    for output, (sequence, samples), original in zip(outputs, blocks, snapshots):
        expected = original.copy()
        if filtered:
            n = len(expected)
            half = n // 2
            window = 0.5 * (1.0 - np.cos(2.0 * np.pi * np.arange(n) / n))
            frequencies = np.fft.rfftfreq(n, 1 / receiver.sample_rate)
            mask = ((frequencies >= sonar.band_low_hz)
                    & (frequencies <= sonar.band_high_hz)).astype(float)
            mask[abs(frequencies - sonar._own_line_hz) < 5] *= .15
            if previous is None:
                previous = np.zeros(half)
                overlap = np.zeros(half)
            parts = []
            for current in (expected[:half], expected[half:]):
                block = np.fft.irfft(
                    np.fft.rfft(window * np.concatenate((previous, current)))
                    * mask, n=n)
                parts.append(overlap + block[:half])
                previous, overlap = current.copy(), block[half:]
            expected = np.concatenate(parts)
        expected *= 10 ** (sonar.gain_db / 20)
        np.testing.assert_array_equal(output, expected.astype(np.float32))
        assert output.dtype == np.float32 and not np.shares_memory(output, samples)
        output[:] = 0
        np.testing.assert_array_equal(samples, original)
        assert not samples.flags.writeable
        assert any(seq == sequence and block is samples for seq, block in receiver.blocks_since(0))
    np.testing.assert_array_equal(receiver._history, history)
    assert state == (receiver.sequence, receiver.elapsed, receiver._rng.bit_generator.state,
                     sonar.rng.getstate())


def test_filtered_receiver_sequence_retry_ignores_intervening_own_line_change():
    sonar = SonarSystem()
    sonar.listen_filtered = True
    samples = np.linspace(-1.0, 1.0, sonar.receiver.samples.size, dtype=np.float32)
    first = sonar.listening_samples(samples, block_id=7)
    state = tuple(part.copy() for part in sonar._audition_ola_state)

    sonar._own_line_hz += 17.0
    retry = sonar.listening_samples(samples, block_id=7)

    np.testing.assert_array_equal(retry, first)
    for before, after in zip(state, sonar._audition_ola_state):
        np.testing.assert_array_equal(after, before)
