"""Phase 3: passive/active sonar equations, noise, reverberation, pulses,
wreck clutter and NPC receiver sensitivity."""

import copy
import json
import math
from types import SimpleNamespace

import pygame
import pytest

from src.core.game import Game
from src.sonar import equation
from src.world.ocean import SEDIMENTS


def test_francois_garrison_matches_reference_magnitudes():
    assert 0.04 < equation.francois_garrison_db_per_km(1000.0, 10.0) < 0.09
    assert equation.francois_garrison_db_per_km(100.0) < \
        equation.francois_garrison_db_per_km(6400.0)


def test_ambient_noise_follows_wind_rain_and_shipping():
    calm = equation.ambient_noise_db(1600.0, 1)
    rough = equation.ambient_noise_db(1600.0, 5)
    assert rough - calm > 8.0
    assert equation.ambient_noise_db(1600.0, 1, rain=1.0) > calm + 3.0
    assert equation.ambient_noise_db(100.0, 1, shipping_contacts=40) > \
        equation.ambient_noise_db(100.0, 1, shipping_contacts=0) + 5.0


def test_passive_reference_and_self_noise_reproduce_calibration():
    terms = equation.passive_terms(
        frequency_hz=100.0, distance_nm=equation.PASSIVE_REFERENCE_RANGE_NM,
        target_bonus=1.0, excess_path_loss_db=0.0, absorption_db_per_km=0.0,
        legacy_absorption_db=0.0, own_range_factor=1.0, array_range_factor=1.0,
        sea_state=1.0, rain=0.0,
        shipping_contacts=equation.REFERENCE_SHIPPING_CONTACTS)
    assert terms.signal_excess_db == pytest.approx(0.0, abs=1e-9)
    noisy = equation.passive_terms(
        frequency_hz=100.0, distance_nm=10.0, target_bonus=1.0,
        excess_path_loss_db=0.0, absorption_db_per_km=0.0,
        legacy_absorption_db=0.0, own_range_factor=0.5, array_range_factor=1.0,
        sea_state=1.0, rain=0.0,
        shipping_contacts=equation.REFERENCE_SHIPPING_CONTACTS)
    # Half the 1.0.0 range means 6 dB less excess at the same distance.
    quiet = equation.passive_terms(
        frequency_hz=100.0, distance_nm=10.0, target_bonus=1.0,
        excess_path_loss_db=0.0, absorption_db_per_km=0.0,
        legacy_absorption_db=0.0, own_range_factor=1.0, array_range_factor=1.0,
        sea_state=1.0, rain=0.0,
        shipping_contacts=equation.REFERENCE_SHIPPING_CONTACTS)
    assert quiet.signal_excess_db - noisy.signal_excess_db == pytest.approx(
        20 * math.log10(2), abs=1e-6)


def _active(distance, **overrides):
    values = dict(distance_nm=distance,
                  target_ts_db=equation.reference_target_strength_db(),
                  legacy_range_factor=1.0, sea_state=0.0, rain=0.0,
                  pulse="CW", water_depth_m=4000.0,
                  lambert_mu_db=SEDIMENTS["mud"][3], wind_kn=0.0,
                  absorption_db_per_km=equation.francois_garrison_db_per_km(
                      equation.ACTIVE_FREQUENCY_HZ,
                      equation.REFERENCE_WATER_TEMPERATURE_C))
    values.update(overrides)
    return equation.active_terms(**values)


def test_active_reference_range_and_target_aspect():
    assert _active(equation.ACTIVE_REFERENCE_RANGE_NM).signal_excess_db == \
        pytest.approx(0.0, abs=0.5)
    assert equation.target_strength_db(70, 90) - equation.target_strength_db(70, 0) \
        == pytest.approx(15.0)


def test_reverberation_depends_on_seabed_and_cw_doppler_rejects_it():
    rock = _active(3.0, water_depth_m=60.0, lambert_mu_db=SEDIMENTS["rock"][3])
    mud = _active(3.0, water_depth_m=60.0, lambert_mu_db=SEDIMENTS["mud"][3])
    assert rock.reverberation_db > mud.reverberation_db + 5.0
    still = _active(3.0, water_depth_m=60.0, lambert_mu_db=SEDIMENTS["rock"][3])
    moving = _active(3.0, water_depth_m=60.0, lambert_mu_db=SEDIMENTS["rock"][3],
                     radial_speed_kn=12.0)
    assert moving.signal_excess_db > still.signal_excess_db
    assert equation.cw_doppler_rejection_db(1.0) == 0.0
    assert equation.cw_doppler_rejection_db(20.0) > equation.cw_doppler_rejection_db(4.0)


def test_lfm_improves_range_accuracy_and_noise_limited_gain():
    assert equation.range_resolution_m("LFM") < equation.range_resolution_m("CW") / 50
    assert equation.range_sigma_m("CW", 20.0) < equation.range_sigma_m("CW", 5.0)
    far_cw = _active(20.0)
    far_lfm = _active(20.0, pulse="LFM")
    assert far_lfm.signal_excess_db > far_cw.signal_excess_db


def _game(seed=3301):
    return Game(seed=seed, start_menu=False, audio_enabled=False)


def test_pulse_key_cycles_and_persists():
    game = _game()
    game.station = type(game.station).SONAR
    assert game.sonar.ping_pulse == "CW"
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_w, mod=0,
                                         unicode="w"))
    assert game.sonar.ping_pulse == "LFM"
    state = json.loads(json.dumps(game.save_state()))
    restored = _game(1)
    assert restored._load_save_data(copy.deepcopy(state))
    assert restored.sonar.ping_pulse == "LFM"
    state["sonar"]["ping_pulse"] = "FM"
    assert not restored._load_save_data(state)


def test_wreck_returns_unassociated_echo_that_survives_save():
    game = _game(3302)
    wreck = next(h for h in game.world.ocean.hazards if h.kind == "wreck")
    game.ship.x, game.ship.y = wreck.x_nm - 1.0, wreck.y_nm
    game.world.sonar_path_blocked = lambda *args: False
    game.sonar.queue_ping(game.ship, [], game.world, game.sim_t)
    assert game.sonar._pending_clutter
    state = json.loads(json.dumps(game.save_state()))
    restored = _game(1)
    assert restored._load_save_data(copy.deepcopy(state))
    assert restored.sonar._pending_clutter == game.sonar._pending_clutter
    restored.sonar._process_pending_pings(restored.sim_t + 60.0)
    echo = restored.sonar.echo_history[-1]
    assert echo["contact_id"] == 0
    assert echo["range_nm"] == pytest.approx(1.0, abs=0.3)
    broken = copy.deepcopy(state)
    broken["sonar"]["pending_clutter"][0]["snapshot"]["bearing"] = 400.0
    assert not restored._load_save_data(broken)


def test_npc_receiver_sensitivity_extends_passive_range():
    from src.data.catalog import CATALOG
    from src.sensors.platform import PlatformSensorSuite

    class World:
        size_nm = 500.0
        depth_m = staticmethod(lambda *a: 1000.0)
        thermocline_depth_m = staticmethod(lambda *a: 80.0)
        on_land = staticmethod(lambda *a: False)
        land_blocks_line = staticmethod(lambda *a: False)
        sonar_path_blocked = staticmethod(lambda *a: False)
        sea_state = 1
        effective_sea_state = 1.0

    import dataclasses

    base = next(CATALOG.sensors[key] for key in
                CATALOG.profile_systems["warship_01"].sensor_keys
                if CATALOG.sensors[key].domain == "sonar")

    def heard(distance, sensitivity_shift):
        suite = PlatformSensorSuite(CATALOG, "warship_01", 5, side="hostile",
                                    doctrine="surface_combatant")
        profile = dataclasses.replace(
            base, sensitivity_db=base.sensitivity_db + sensitivity_shift)
        owner = SimpleNamespace(id=1, x=0.0, y=0.0, depth=5.0, course=0.0,
                                speed=10.0, noise_level=lambda: 0.3)
        target = SimpleNamespace(id=77, x=distance, y=0.0, depth=50.0,
                                 course=0.0, speed=5.0, active=True, sunk=False,
                                 noise_level=lambda: 0.3)
        suite._observe_candidate(1.0, owner, target, World(), profile, 0, 1.0)
        return bool(suite.local_picture.tracks(1.0)) if hasattr(
            suite.local_picture, "tracks") else bool(suite.tactical_tracks(1.0))

    far = 68.0     # beyond the 40 NM x source-level reach, inside the 1.8x cap
    assert not heard(far, 0.0)
    assert heard(far, -6.0)
