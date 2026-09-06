"""Directional sonar integration: input, observations, audio and persistence."""

import random
from types import SimpleNamespace

import numpy as np
import pygame
import pytest

from src.core import config
from src.core.game import Game
from src.core.station import Station
from src.enemies.civilian import CivilianShip
from src.enemies.decoy import Decoy
from src.enemies.sub import Sub
from src.ship.ship import Ship
from src.sonar.sonar import SonarSystem


def press(game, key, **kwargs):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, **kwargs))


@pytest.fixture
def game():
    game = Game(seed=6, start_menu=False)
    game.station = Station.SONAR
    return game


def test_bearing_controls_and_pages_do_not_change_ship_orders(game):
    course = game.ship.target_course
    press(game, pygame.K_r)
    for key in (pygame.K_3, pygame.K_5, pygame.K_9, pygame.K_PERIOD,
                pygame.K_9, pygame.K_RETURN):
        press(game, key)
    assert game.sonar.listen_bearing == 359.9
    press(game, pygame.K_RIGHT, mod=pygame.KMOD_CTRL)
    assert game.sonar.listen_bearing == pytest.approx(0.0)
    press(game, pygame.K_LEFT, mod=pygame.KMOD_SHIFT)
    assert game.sonar.listen_bearing == pytest.approx(355.0)
    for _ in range(config.SONAR_PAGE_COUNT):
        press(game, pygame.K_PAGEDOWN)
        game.draw()
    assert game.sonar_page == 0
    press(game, pygame.K_DOWN)
    press(game, pygame.K_UP)
    assert not game.held and game.ship.target_course == course


def test_manual_beam_hears_without_selected_contact_and_resets_on_retune():
    ship = Ship(250, 250, speed_kn=0)
    world = SimpleNamespace(sea_state=0, thermocline_depth_m=lambda x, y: 100)
    sub = Sub(253, 250, 40, 0, "diesel_alt", random.Random(1))
    sonar = SonarSystem(1)
    sonar.set_listen_bearing(90)
    for i in range(8):
        sonar.update(.25, (i + 1) * .25, ship, [sub], world)
    assert sonar.demon_analysis is not None
    on_axis = np.sqrt(np.mean(sonar.listening_samples()**2))
    assert sonar.broadband_history and sonar.lofar_times[-1] == 2.0
    sonar.set_listen_bearing(270)
    assert not sonar.lofar_history and sonar.demon_analysis is None
    assert np.max(np.abs(sonar.receiver.samples)) == 0
    assert sonar.broadband_history  # Rundumsicht remains valid when retuning.
    for i in range(8):
        sonar.update(.25, 2.0 + (i + 1) * .25, ship, [sub], world)
    off_axis = np.sqrt(np.mean(sonar.listening_samples()**2))
    assert on_axis > off_axis * 5
    assert sonar.demon_analysis is None


def test_contact_selection_does_not_silently_repoint_manual_beam(game):
    target = game.subs[0]
    contact = game.sonar._get_contact(target)
    contact.bearing = 72.0
    contact.last_seen = game.sim_t
    game.sonar.set_listen_bearing(120)
    press(game, pygame.K_DOWN)
    assert game.selected_contact is contact and game.sonar.listen_bearing == 120
    press(game, pygame.K_RETURN)
    assert game.sonar.focus_locked and game.sonar.listen_bearing == 72
    press(game, pygame.K_LEFT)
    assert not game.sonar.focus_locked


def test_lost_track_holds_last_observation_not_target_position():
    ship = Ship(250, 250, speed_kn=0)
    world = SimpleNamespace(sea_state=0, thermocline_depth_m=lambda x, y: 100)
    sub = Sub(253, 250, 40, 0, "diesel_alt", random.Random(1))
    sonar = SonarSystem(1)
    sonar.focus_locked = True
    sonar.update(.25, .25, ship, [sub], world, focus_tgt=sub)
    bearing = sonar.listen_bearing
    sub.x, sub.y = 0, 0
    sonar.update(.25, 3, ship, [sub], world, focus_tgt=sub)
    assert not sonar.focus_locked
    assert sonar.listen_bearing == bearing


def test_game_passive_population_includes_civilian_and_decoy(game):
    game.ship.speed = 0.0
    game.civilians = [CivilianShip(game.ship.x + 2, game.ship.y, random.Random(2))]
    game.decoys = [Decoy(game.ship.x + 3, game.ship.y, 10, random.Random(3))]
    assert game.civilians[0].id != game.decoys[0].id
    game._update_sensors(.25)
    for target in game.civilians + game.decoys:
        assert target.id in game.sonar.contacts
        assert game._find_target(target.id) is target


def test_audition_band_removes_carrier_without_changing_receiver():
    sonar = SonarSystem()
    t = np.arange(1024) / sonar.receiver.sample_rate
    sonar.receiver.samples = (.1 * np.sin(2 * np.pi * 700 * t)).astype(np.float32)
    original = sonar.receiver.samples.copy()
    sonar.listen_filtered = True
    assert np.max(np.abs(sonar.listening_samples())) < .001
    np.testing.assert_array_equal(sonar.receiver.samples, original)


@pytest.mark.parametrize("action", [pygame.K_p, pygame.K_F1, pygame.K_j, pygame.K_1])
def test_audio_stops_on_pause_administration_mute_and_station_change(game, monkeypatch, action):
    calls = []
    monkeypatch.setattr(game.audio, "stop_sonar", lambda: calls.append("stop"))
    press(game, action)
    assert calls


def test_sonar_audio_uses_receiver_samples_and_only_new_blocks(game, monkeypatch):
    calls = []
    game.sonar.receiver.samples[:] = .05
    monkeypatch.setattr(game.audio, "play_sonar", lambda samples, rate, volume, **kwargs:
                        calls.append((samples.copy(), rate, volume)) or True)
    monkeypatch.setattr(game.audio, "update_engine", lambda *args, **kwargs: None)
    game._update_audio(.25)
    game._update_audio(.25)
    assert len(calls) == 1
    np.testing.assert_allclose(calls[0][0], .05)
    assert calls[0][1] == game.sonar.receiver.sample_rate
    assert calls[0][2] == game.sonar_volume


def test_sonar_controls_and_surface_focus_survive_slot_save(game):
    civilian = game.civilians[0]
    contact = game.sonar._get_contact(civilian)
    assert contact.id != contact.target_id
    game.selected_contact = contact
    game.sonar_page = 2
    game.sonar.set_listen_bearing(123.4)
    game.sonar.listen_filtered = True
    game.sonar_audio_enabled = False
    game.sonar_volume = .3
    game.save_to_slot(1)
    game.reset(game.seed)
    assert game.load_from_slot(1)
    assert game.sonar.listen_bearing == 123.4
    assert game.sonar.listen_filtered and game.sonar_page == 2
    assert not game.sonar_audio_enabled and game.sonar_volume == .3
    assert game.selected_contact.id == contact.id
    assert game.selected_contact.target_id == civilian.id
    assert game.selected_contact is game.sonar.contacts[civilian.id]
    assert game.sonar.demon_analysis is None  # DSP warms up instead of inventing state.


def test_history_and_peak_hold_are_bounded():
    ship = Ship(250, 250, speed_kn=0)
    world = SimpleNamespace(sea_state=0, thermocline_depth_m=lambda x, y: 100)
    sonar = SonarSystem()
    sonar.peak_hold = True
    for i in range(config.LOFAR_HISTORY_COLS + 5):
        sonar.update(.25, (i + 1) * .25, ship, [], world)
    assert len(sonar.lofar_history) == len(sonar.broadband_history) == config.LOFAR_HISTORY_COLS
    assert len(sonar.lofar_times) == len(sonar.lofar_bearings) == config.LOFAR_HISTORY_COLS
    assert len(sonar.peak_spectrum) == config.LOFAR_BINS
    assert sonar.history_times == sorted(sonar.history_times)


def test_bathythermograph_and_towed_depth_are_operator_controls(game):
    assert game.sonar.bt_profile is None
    press(game, pygame.K_e)
    profile = game.sonar.bt_profile
    assert profile is not None
    assert len(profile["depths_m"]) == len(profile["speeds_m_s"]) == 21
    assert profile["cz_bands_nm"]
    assert game.sonar.bt_cooldown == config.SONAR_BT_COOLDOWN_S

    game.sonar.tow_state = game.sonar.STREAMED
    game.sonar.tow_payout = 1.0
    before = game.sonar.towed_depth_target_m
    press(game, pygame.K_v)
    assert game.sonar.towed_depth_target_m == before + 10.0
    game.sonar.update(1.0, 1.0, game.ship, [], game.world)
    assert before < game.sonar.towed_depth_m < game.sonar.towed_depth_target_m


def test_towed_array_below_layer_improves_deep_target_range():
    ship = Ship(250, 250, speed_kn=0)
    world = SimpleNamespace(sea_state=0, thermocline_depth_m=lambda x, y: 100)
    sub = Sub(255, 250, 160, 0, "diesel_alt", random.Random(4))
    sonar = SonarSystem(4)
    sonar.tow_state = sonar.STREAMED
    sonar.tow_payout = 1.0
    sonar._tow_settle_s = config.SONAR_TOWED_SETTLE_S
    sonar.towed_depth_m = 50.0
    shadowed = sonar.passive_range_nm(sub, 5.0, ship, world, 1.0, "TOWED")
    sonar.towed_depth_m = 150.0
    same_layer = sonar.passive_range_nm(sub, 5.0, ship, world, 1.0, "TOWED")
    assert same_layer > shadowed * 2.0


@pytest.mark.parametrize("offset,status", [
    (1.0, "BESTAETIGT"),
    (12.0, "DIVERGENT / GEISTERKONTAKT?"),
])
def test_hms_tas_fusion_uses_separate_observed_bearings(offset, status):
    ship = Ship(250, 250, speed_kn=0)
    world = SimpleNamespace(sea_state=0, thermocline_depth_m=lambda x, y: 100)
    sub = Sub(252, 250, 40, 0, "diesel_alt", random.Random(5))
    sonar = SonarSystem(5)
    sonar.tow_state = sonar.STREAMED
    sonar.tow_payout = 1.0
    sonar._tow_settle_s = config.SONAR_TOWED_SETTLE_S
    sonar._observed_bearing = lambda target, true, frigate, quality, mode, t: \
        true + (offset if mode == "TOWED" else 0.0)
    sonar.update(.25, .25, ship, [sub], world)
    contact = sonar.contacts[sub.id]
    assert set(contact.array_observations) == {"BOW", "TOWED"}
    assert contact.fusion_status == status
    assert contact.fusion_delta_deg == pytest.approx(offset)


def test_environment_and_fusion_state_survive_save_load(game):
    press(game, pygame.K_e)
    game.sonar.towed_depth_m = 87.0
    game.sonar.towed_depth_target_m = 110.0
    contact = game.sonar._get_contact(game.subs[0])
    contact.array_observations = {
        "BOW": {"bearing": 20.0, "quality": .5, "snr": 4.0,
                "last_seen": game.sim_t}}
    contact.fusion_status = "NUR BOW"
    data = game.save_state()
    restored = Game(seed=99, start_menu=False)
    restored.load_state(data)
    assert restored.sonar.bt_profile == game.sonar.bt_profile
    assert restored.sonar.towed_depth_m == 87.0
    assert restored.sonar.towed_depth_target_m == 110.0
    loaded = restored.sonar.contacts[contact.target_id]
    assert loaded.array_observations == contact.array_observations
    assert loaded.fusion_status == "NUR BOW"
