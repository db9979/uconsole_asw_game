import copy
import random
from types import SimpleNamespace

import pytest

from src.air.live_aircraft import LiveAircraft
from src.core.game import Game
from src.enemies.surface import SurfaceShip
from src.sensors.esm import (
    ECMJammer,
    ECMEffect,
    ECMTechnique,
    ESMMeasurement,
    ESMPicture,
    RadarSuiteController,
    SignalType,
    analyze_signal,
    animated_signal_fingerprint,
    scan_for_signals,
    signal_fingerprint,
    spectrum_band,
)


def test_radar_suite_is_seeded_bounded_and_uses_simulation_time():
    game = Game(seed=801, audio_enabled=False)
    systems = game.runtime_catalog.profile_systems["warship_22"]
    emitters = [game.runtime_catalog.emitters[key]
                for key in systems.emitter_keys]
    suite = RadarSuiteController(emitters, 17)
    first = suite.active_signals(0.0, 10.0, 20.0, fire_control=True)
    again = RadarSuiteController(reversed(emitters), 17).active_signals(
        0.0, 10.0, 20.0, fire_control=True)
    assert first == again
    assert 1 <= len(first) <= 4
    assert {signal.signal_type for signal in first} == {
        SignalType.NAVIGATION, SignalType.AIR_SEARCH,
        SignalType.MULTI_FUNCTION, SignalType.FIRE_CONTROL}
    assert all(500e6 <= signal.frequency_hz <= 18e9 for signal in first)
    assert all(signal.pri_s == pytest.approx(1.0 / signal.prf_hz)
               for signal in first if signal.prf_hz is not None)


def test_non_agile_radar_fingerprint_is_stable_across_duty_cycle_silence():
    game = Game(seed=8011, audio_enabled=False)
    emitter = game.runtime_catalog.emitters["emitter.sub_01.mast_radar"]
    suite = RadarSuiteController((emitter,), 17)
    start = next(tick / 2 for tick in range(1, 120)
                 if suite.active_signals(tick / 2, 10.0, 20.0))
    first = suite.active_signals(start, 10.0, 20.0)[0]
    again = suite.active_signals(start + emitter.operating_period_s,
                                 10.0, 20.0)[0]
    assert first.frequency_hz == again.frequency_hz
    assert first.prf_hz == again.prf_hz


def test_scan_detaches_internal_identity_and_prefers_strong_signals():
    game = Game(seed=802, audio_enabled=False)
    emitter = game.runtime_catalog.emitters["emitter.warship_22.radar"]
    signal = RadarSuiteController((emitter,), 3).active_signals(0.0, 5.0, 0.0)[0]
    measured = scan_for_signals(
        (signal,), observer_x=0.0, observer_y=0.0, now=0.0,
        maximum_range_nm=150.0, bearing_error_deg=3.0,
        noise_for=lambda _signal: 0.0)
    assert len(measured) == 1
    assert not hasattr(measured[0], "signal_id")
    assert not hasattr(measured[0], "x")
    assert measured[0].bearing == pytest.approx(90.0)


@pytest.mark.parametrize("modulation", [
    "continuous_wave", "frequency_agile", "pulse", "pulse_doppler", "unknown",
])
def test_signal_fingerprint_is_bounded_deterministic_operator_aid(modulation):
    picture = ESMPicture()
    picture.observe_batch([ESMMeasurement(
        0, 0, 90, 1, 9e9, 900, modulation, .8, 1.0)], 1.0)
    track = picture.tracks(1.0)[0]
    first = signal_fingerprint(track)
    assert first == signal_fingerprint(track)
    assert len(first.waveform) == 48 and len(first.spectrum) == 40
    assert all(-1 <= value <= 1 for value in first.waveform)
    assert all(0 <= value <= 1 for value in first.spectrum)


@pytest.mark.parametrize("technique", [None, "noise", "rgpo", "vgpo",
                                        "false_targets"])
def test_animated_signal_uses_only_simulation_time_and_stays_bounded(technique):
    picture = ESMPicture()
    picture.observe_batch([ESMMeasurement(
        0, 0, 90, 1, 9e9, 1800, "pulse_doppler", .8, 1.0)], 1.0)
    track = picture.tracks(1.0)[0]
    first = animated_signal_fingerprint(
        track, 1.25, technique=technique, effectiveness=.6)
    assert first == animated_signal_fingerprint(
        track, 1.25, technique=technique, effectiveness=.6)
    assert first != animated_signal_fingerprint(
        track, 1.75, technique=technique, effectiveness=.6)
    assert all(-1 <= value <= 1 for value in first.waveform)
    assert all(0 <= value <= 1 for value in first.spectrum)


def test_animated_signal_enters_memory_hold_and_fades_with_track_age():
    picture = ESMPicture()
    picture.observe_batch([ESMMeasurement(
        0, 0, 90, 1, 9e9, 1800, "pulse", .8, 1.0)], 1.0)
    track = picture.tracks(1.0)[0]
    live = animated_signal_fingerprint(track, 1.5)
    held = animated_signal_fingerprint(track, 100.0)
    assert not live.memory_hold and held.memory_hold
    assert held.intensity < live.intensity


def test_four_channel_ecm_manual_priority_reaction_and_burnthrough():
    picture = ESMPicture()
    picture.observe_batch([
        ESMMeasurement(0, 0, 10 + index * 30, 1, 9e9 + index * 1e8,
                       1000, "pulse", .9, 1.0)
        for index in range(5)
    ], 1.0)
    jammer = ECMJammer()
    tracks = picture.tracks(1.0)
    assert jammer.deploy_jamming(tracks[0], 1.0) is True
    assert jammer.deploy_jamming(tracks[1], 1.0) is True
    assert jammer.deploy_jamming(tracks[2], 1.0) is True
    assert jammer.deploy_jamming(tracks[3], 1.0) is True
    assert jammer.deploy_jamming(tracks[4], 1.0) == "channels_full"
    jammer.update(tracks, 2.1)
    assert len(jammer.channels) == 4
    assert all(0 < item.effectiveness <= .7 for item in jammer.channels)

    game = Game(seed=803, audio_enabled=False)
    emitter = game.runtime_catalog.emitters["emitter.warship_22.navigation"]
    signal = RadarSuiteController((emitter,), 1).active_signals(0.0, 10, 0)[0]
    jammer.channels[0].tuned_frequency_hz = signal.frequency_hz
    jammer.channels[0].effectiveness = .7
    assert jammer.effect_on(signal, 1.0, burn_through_nm=10.0) < .1
    assert jammer.effect_on(signal, 20.0, burn_through_nm=10.0) <= .7


@pytest.mark.parametrize(("frequency", "band"), [
    (500e6, "a_c"), (1e9, "d"), (2e9, "e_f"), (4e9, "g_h"),
    (8e9, "i_j"), (20e9, "k"), (40e9, "k"),
])
def test_esm_frequency_band_boundaries(frequency, band):
    assert spectrum_band(frequency).value == band


@pytest.mark.parametrize("technique", [item.value for item in ECMTechnique])
def test_ecm_techniques_produce_bounded_distinct_effects(technique):
    game = Game(seed=8031, audio_enabled=False)
    emitter = game._asm_seeker_emitter(game._air_defense_loadout["asm"])
    signal = RadarSuiteController((emitter,), 1).active_signals(
        1.0, 10.0, 0.0, terminal=True)[0]
    picture = ESMPicture()
    picture.observe_batch([ESMMeasurement(
        0, 0, 90, 1, signal.frequency_hz, signal.prf_hz,
        signal.modulation_code, .9, 1.0)], 1.0)
    jammer = ECMJammer()
    track = picture.tracks(1.0)[0]
    assert jammer.deploy_jamming(track, 1.0, technique=technique) is True
    jammer.update((track,), 1.01)
    effect = jammer.effect_details_on(signal, 20.0, burn_through_nm=8.0)
    assert 0 < effect.effectiveness <= jammer.MAX_EFFECTIVENESS
    assert effect.technique == technique
    assert effect.hoj_exposure is (technique == "noise")
    assert (effect.range_error_nm > 0) is (technique == "rgpo")
    assert (effect.velocity_error_kn > 0) is (technique == "vgpo")
    assert (effect.false_targets > 0) is (technique == "false_targets")


def test_ecm_shared_power_budget_reduces_four_noise_channels():
    picture = ESMPicture()
    picture.observe_batch([ESMMeasurement(
        0, 0, 10 + index * 20, 1, 9e9 + index * 1e8, 1000,
        "frequency_agile", .9, 1.0) for index in range(4)], 1.0)
    jammer = ECMJammer()
    tracks = picture.tracks(1.0)
    for track in tracks:
        assert jammer.deploy_jamming(track, 1.0, technique="noise") is True
    jammer.update(tracks, 1.01)
    assert sum(channel.power_draw for channel in jammer.channels) > 1.0
    assert all(channel.effectiveness < jammer.MAX_EFFECTIVENESS
               for channel in jammer.channels)


def test_noise_exposes_home_on_jam_while_rgpo_breaks_guidance():
    game = Game(seed=8032, audio_enabled=False)
    profile = game._air_defense_loadout["asm"]
    from src.air.asm import ASM
    # ECM acts on a seeker in terminal lock: both missiles close on the ship
    # (due west) 20 deg off the line of sight with the seeker locked.
    noise = ASM(game.ship.x + 5, game.ship.y, 250, 1, random.Random(10), profile)
    rgpo = ASM(game.ship.x + 5, game.ship.y, 250, 2, random.Random(10), profile)
    for missile in (noise, rgpo):
        missile.jammer = False
        missile.locked, missile.los_prev = True, 270.0
    noise.update(.1, game.ship, ecm_effect=ECMEffect(
        .7, "noise", hoj_exposure=True))
    rgpo.update(.1, game.ship, ecm_effect=ECMEffect(
        .7, "rgpo", range_error_nm=1.0))
    assert noise.course != 250.0
    assert rgpo.course == 250.0


def test_ecm_auto_couples_terminal_threat_to_finite_softkill(monkeypatch):
    game = Game(seed=8033, audio_enabled=False)
    from src.air.asm import ASM
    asm = ASM(game.ship.x + 1, game.ship.y, 270, 77, game.rng_asm,
              game._air_defense_loadout["asm"])
    asm.jammer = False
    game.asms = [asm]
    track = SimpleNamespace(target_id=asm.seq, range_nm=1.0,
                            position_seen=game.sim_t, track_id="M-77")
    monkeypatch.setattr(game, "asm_tracks", lambda: [track])
    monkeypatch.setattr(game, "_ecm_effect_against_asm", lambda _asm:
                        ECMEffect(.5, "vgpo", velocity_error_kn=100.0))
    game.ecm_jammer.auto_enabled = True
    inventory = game.softkill_store.remaining_total
    game._auto_ecm_softkill()
    assert asm.state == "CHAFF"
    assert game.softkill_store.remaining_total == inventory - 1


def test_live_aircraft_seed_and_synthetic_projection_are_stable(monkeypatch):
    first = LiveAircraft("abc123", None, 1, 0, 0, 1000, 0, 100, 0)
    second = LiveAircraft("ABC123", None, 2, 0, 0, 1000, 0, 100, 0)
    assert first.sensor_seed == second.sensor_seed

    game = Game(seed=804, audio_enabled=False)
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)
    first.x, first.y = game.ship.x + 5, game.ship.y
    game.live_traffic.aircraft = {first.icao24: first}
    game.civilians = game.warships = []
    game.flights.flights = []
    for tick in range(1, 121):
        game.sim_t = float(tick)
        game._update_esm_picture()
        if game.eloka_tracks():
            break
    assert game.eloka_tracks()[0].synthetic_assumption is True


def test_submarine_mast_radar_requires_shallow_tactical_state(monkeypatch):
    game = Game(seed=805, audio_enabled=False)
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)
    sub = game.subs[0]
    sub.x, sub.y = game.ship.x + 5, game.ship.y
    game.civilians = game.warships = []
    game.flights.flights = []
    game.sim_t = 0.0
    sub.depth = 100.0
    game._update_esm_picture()
    assert not game.eloka_tracks()
    sub.depth = 15.0
    sub.state = "PATROLLE"
    game._update_esm_picture()
    assert game.eloka_tracks()
    analysis = analyze_signal(game.eloka_tracks()[0], game.runtime_catalog.emitters)
    assert analysis.radar_type is SignalType.NAVIGATION


def test_pre_ecm_esm_shape_is_rejected():
    game = Game(seed=806, audio_enabled=False)
    state = game.save_state()
    state["esm"]["version"] = 1
    del state["esm"]["ecm"]
    restored = Game(seed=1, audio_enabled=False)
    before = restored.save_state()
    assert not restored._load_save_data(copy.deepcopy(state))
    assert restored.save_state() == before


def test_two_channel_ecm_v2_shape_is_rejected():
    game = Game(seed=807, audio_enabled=False)
    game.esm_picture.observe_batch([ESMMeasurement(
        0, 0, 90, 1, 9e9, 1000, "pulse", .9, game.sim_t)], game.sim_t)
    track = game.eloka_tracks()[0]
    assert game.ecm_jammer.deploy_jamming(track, game.sim_t) is True
    state = game.save_state()
    state["esm"]["version"] = 2
    for channel in state["esm"]["ecm"]["channels"]:
        for key in ("technique", "tuned_bearing_deg", "power_draw",
                    "is_locked_on"):
            del channel[key]
    restored = Game(seed=1, audio_enabled=False)
    assert not restored._load_save_data(copy.deepcopy(state))
