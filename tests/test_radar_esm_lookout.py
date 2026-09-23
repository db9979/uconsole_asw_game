"""Phase 11: radar equation, antenna scan, ESM amplitude, HFDF, lookout."""

import copy
import json
import math
from types import SimpleNamespace

import pytest

from src.core import config
from src.core.game import LOOKOUT_MODEL, Game
from src.sensors import esm, hfdf, radar, visual


def test_swerling_cfar_detection_probability_is_anchored_at_snr_50():
    assert radar.pd_from_sinr(radar.SNR_50) == pytest.approx(0.5)
    values = [radar.pd_from_sinr(s) for s in (1.0, 10.0, 30.0, 100.0, 1000.0)]
    assert values == sorted(values)
    assert radar.pd_from_sinr(0.0) == 0.0


def test_radar_range_anchors_reproduce_the_legacy_ranges():
    surface = radar.detection_range_nm(30.0, domain="surface")
    assert surface == pytest.approx(30.0, rel=.01)
    assert radar.detection_range_nm(30.0, domain="surface", sea_state=6) \
        == pytest.approx(30.0 * .75, rel=.01)
    assert radar.detection_range_nm(100.0, domain="air", rain_intensity=1.0) \
        == pytest.approx(80.0, rel=.01)
    # R^4: a -6 dB smaller target is seen at ~0.71 of the range.
    assert radar.detection_range_nm(30.0, rcs_factor=.25) \
        == pytest.approx(30.0 * .25 ** .25, rel=.02)


def test_self_screening_jammer_burns_through_at_the_profiled_range():
    skin = radar.snr(8.0, 100.0)
    for distance, expected in ((8.0, .5), (4.0, None), (20.0, None)):
        jnr = radar.jammer_to_noise(distance, 8.0, skin)
        pd = radar.pd_from_sinr(radar.sinr(distance, 100.0, domain="air", jnr=jnr))
        if expected is not None:
            assert pd == pytest.approx(expected, abs=.01)
    inside = radar.pd_from_sinr(radar.sinr(
        4.0, 100.0, domain="air", jnr=radar.jammer_to_noise(4.0, 8.0, skin)))
    outside = radar.pd_from_sinr(radar.sinr(
        20.0, 100.0, domain="air", jnr=radar.jammer_to_noise(20.0, 8.0, skin)))
    assert inside > .5 > outside


def _surface_target_game(monkeypatch):
    game = Game(seed=1101, start_menu=False, audio_enabled=False)
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)
    civilian = game.civilians[0]
    civilian.x, civilian.y = game.ship.x + 6.0, game.ship.y   # bearing 090
    civilian.emitter = False
    game.civilians, game.warships, game.asms = [civilian], [], []
    game.flights.flights = []
    game.air_picture._tracks.clear()
    return game, civilian


def test_contacts_are_looked_at_only_where_the_beam_swept(monkeypatch):
    game, civilian = _surface_target_game(monkeypatch)
    game.radar_scan_phase, game.radar_scan_pending_deg = 45.0, 40.0
    game._update_air_picture()
    assert not any(t.source == "RADAR-S" for t in game.air_picture.tracks(game.sim_t))
    assert game.radar_scan_pending_deg == 0.0
    game.radar_scan_phase, game.radar_scan_pending_deg = 100.0, 30.0
    game._update_air_picture()
    assert any(t.source == "RADAR-S" for t in game.air_picture.tracks(game.sim_t))


def test_antenna_turns_only_with_simulation_time():
    game = Game(seed=1102, start_menu=False, audio_enabled=False)
    game.radar_scan_phase = 0.0
    game._t += 30.0
    assert game.radar_sweep_bearing() == 0.0
    for _ in range(20):
        game._update_sim(0.1)
    assert game.radar_sweep_bearing() == pytest.approx(
        2.0 * config.RADAR_SWEEP_DEG_PER_S % 360.0)


def test_radar_scan_state_round_trips_and_is_validated():
    game = Game(seed=1103, start_menu=False, audio_enabled=False)
    game.radar_scan_phase, game.radar_scan_pending_deg = 123.5, 17.25
    state = json.loads(json.dumps(game.save_state()))
    restored = Game(seed=1, start_menu=False, audio_enabled=False)
    assert restored._load_save_data(copy.deepcopy(state))
    assert (restored.radar_scan_phase, restored.radar_scan_pending_deg) == (123.5, 17.25)
    for key, value in (("scan_phase", 360.0), ("scan_pending_deg", -1.0),
                       ("scan_phase", 5)):
        broken = copy.deepcopy(state)
        broken["radars"][key] = value
        assert not restored._load_save_data(broken)


def _signal(role="surface_search", power="high", x=0.0, y=40.0, now=0.0):
    return esm.RadarSignal("R0123456789abcdef", "emitter.test", 9.4e9, 1000.0,
                           "pulse", "search", esm.SignalType(role), x, y,
                           power, now)


def test_esm_hears_main_beam_far_and_side_lobes_only_close():
    far = _signal(y=100.0)     # 100 NM, inside the 150 NM high-power class
    near = _signal(y=5.0)
    hits = {"far": 0, "near": 0}
    for step in range(40):
        now = step * 0.5
        for name, signal in (("far", far), ("near", near)):
            if esm.scan_for_signals((signal,), observer_x=0.0, observer_y=0.0,
                                    now=now, maximum_range_nm=150.0,
                                    bearing_error_deg=3.0, noise_for=lambda s: 0.0):
                hits[name] += 1
    # 2.5 s rotation, 0.5 s dwell: the far emitter is heard once per turn.
    assert 6 <= hits["far"] <= 12
    assert hits["near"] == 40


def test_esm_track_measures_scan_period_level_and_range_estimate():
    picture = esm.ESMPicture()
    for step in range(60):
        now = step * 0.5
        picture.observe_batch(esm.scan_for_signals(
            (_signal(y=60.0, now=now),), observer_x=0.0, observer_y=0.0, now=now,
            maximum_range_nm=150.0, bearing_error_deg=3.0,
            noise_for=lambda s: 0.0), now)
    (track,) = picture.tracks(30.0)
    assert track.revisit_s == pytest.approx(2.5, abs=.6)
    assert esm.estimated_range_nm(track, "high") == pytest.approx(60.0, rel=.05)
    assert esm.live_window_s(track) > esm.ECM_SIGNAL_FRESH_S


def test_hf_frequency_and_propagation_modes():
    day = hfdf.transmit_frequency_mhz(7, 0, night=False)
    night = hfdf.transmit_frequency_mhz(7, 0, night=True)
    assert 2.0 <= night < day <= 30.0
    ground = hfdf.ground_wave_range_nm(day, config.HFDF_RANGE_NM)
    assert hfdf.propagation_mode(ground * .9, day, False, config.HFDF_RANGE_NM) == "GROUND"
    skip = hfdf.skip_distance_nm(day, False)
    assert skip > ground
    assert hfdf.propagation_mode((ground + skip) / 2, day, False,
                                 config.HFDF_RANGE_NM) is None
    assert hfdf.propagation_mode(skip + 1.0, day, False, config.HFDF_RANGE_NM) == "SKY"


def test_hfdf_observation_carries_frequency_and_mode(monkeypatch):
    game = Game(seed=1104, start_menu=False, audio_enabled=False)
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)
    sub = game.subs[0]
    sub.x, sub.y = game.ship.x + 20.0, game.ship.y
    monkeypatch.setattr(type(sub), "transmitting", property(lambda self: True))
    game.subs = [sub]
    game._update_radio_picture()
    (report,) = game.hfdf_bearings()
    assert report.propagation == "GROUND"
    assert 2e6 <= report.frequency_hz <= 30e6
    assert report.range_nm is None


def test_lookout_follows_koschmieder_moon_and_sea_state():
    kwargs = dict(visibility_nm=config.WEATHER_VISIBILITY_MAX_NM, night=False,
                  illumination=.5, sea_state=0.0)

    def reach(kind, **changes):
        low, high = .01, 60.0
        for _ in range(50):
            mid = (low + high) / 2
            if LOOKOUT_MODEL.margin(kind, mid, **{**kwargs, **changes}) >= 1.0:
                low = mid
            else:
                high = mid
        return low

    assert reach("SURFACE") == pytest.approx(config.LOOKOUT_SURFACE_RANGE_NM, rel=.01)
    assert reach("SUB") == pytest.approx(config.LOOKOUT_SUB_RANGE_NM, rel=.01)
    new_moon = reach("SURFACE", night=True, illumination=0.0)
    full_moon = reach("SURFACE", night=True, illumination=1.0)
    assert new_moon < reach("SURFACE", night=True) < full_moon < reach("SURFACE")
    assert reach("SURFACE", night=True) == pytest.approx(
        config.LOOKOUT_NIGHT_FACTOR * config.LOOKOUT_SURFACE_RANGE_NM, rel=.05)
    assert reach("SURFACE", visibility_nm=2.0) < 2.0
    assert reach("SUB", sea_state=4.0) < reach("SUB")
    # Aircraft are seen against the sky: whitecaps do not hide them.
    assert reach("FLG", sea_state=5.0, altitude_m=3000.0) == pytest.approx(
        reach("FLG", altitude_m=3000.0))
    assert visual.moon_illumination(0.0) == 0.0
    assert visual.moon_illumination(visual.SYNODIC_MONTH_D / 2) == pytest.approx(1.0)


def test_radar_and_lookout_picture_is_deterministic():
    def run():
        game = Game(seed=1105, start_menu=False, audio_enabled=False)
        game.world.land_blocks_line = lambda *args: False
        game.civilians[0].x, game.civilians[0].y = game.ship.x + 8.0, game.ship.y
        game.flights.flights[0].x = game.ship.x - 30.0
        game.flights.flights[0].y = game.ship.y
        for _ in range(200):
            game._update_sim(0.1)
        # Entity IDs come from process-wide counters; compare measurements.
        return sorted((t["source"], round(t["bearing"], 9), t["range_nm"],
                       t["last_seen"]) for t in game.air_picture.serialize()
                      if t["source"] in ("RADAR-S", "RADAR-L", "LOOKOUT"))

    first = run()
    assert first and first == run()


def test_ciws_track_radar_holds_close_in_missiles_between_sweeps(monkeypatch):
    from src.air.asm import ASM
    from src.core.game import CIWS_TRACK_RANGE_NM

    game = Game(seed=1106, start_menu=False, audio_enabled=False)
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)
    asm = ASM(game.ship.x + CIWS_TRACK_RANGE_NM - 0.5, game.ship.y, 270.0, 3,
              game.rng_asm, game._air_defense_loadout["asm"])
    asm.jammer = False
    game.asms = [asm]
    game.radar_scan_phase, game.radar_scan_pending_deg = 0.0, 10.0  # beam north
    game._update_air_picture()
    assert game.asm_tracks()
    game.air_picture._tracks.clear()
    game.ciws_authorized = False
    game.radar_scan_pending_deg = 10.0
    game._update_air_picture()
    assert not game.asm_tracks()


def test_eloka_analysis_cache_matches_direct_ranking_and_is_bounded():
    game = Game(seed=1107, start_menu=False, audio_enabled=False)
    tracks = [esm.ESMTrack(f"E{index + 1:016x}", 0.0, 0.0, 90.0, 1.0,
                           2e9 + index * 1e6, 800.0, "pulse", .8, 0.0, 0.0)
              for index in range(game.ELOKA_ANALYSIS_CACHE_MAX + 20)]
    for track in tracks:
        assert game.eloka_analysis(track) == esm.analyze_signal(
            track, game.runtime_catalog.emitters)
    assert len(game._eloka_analysis_cache) <= game.ELOKA_ANALYSIS_CACHE_MAX
