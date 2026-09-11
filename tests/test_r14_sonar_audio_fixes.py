"""R14 audition and independent sonar-fix publication contracts."""

import copy
from types import SimpleNamespace as NS

import numpy as np
import pytest

from src.core import config
from src.core.game import Game
from src.core.station import Station
from src.sonar.sonar import Contact, SonarSystem
from src.ui import map_view


def tone(frequency, amplitude=.1):
    time = np.arange(1024) / 4096
    return (amplitude * np.sin(2 * np.pi * frequency * time)).astype(np.float32)


@pytest.mark.parametrize("mode", ["BROADBAND", "FILTERED", "HETERODYNE"])
def test_audition_gain_applies_to_complete_beam_in_every_mode(mode):
    low, high = SonarSystem(), SonarSystem()
    for sonar in (low, high):
        sonar.set_audition_mode(mode)
        sonar.band_low_hz, sonar.band_high_hz = 20, 80
    high.gain_db = 6
    source = tone(40) + tone(150, .04)
    a = low.listening_samples(source, block_id=1)
    b = high.listening_samples(source, block_id=1)
    np.testing.assert_allclose(b, a * 10 ** (6 / 20), atol=2e-7)
    if mode != "BROADBAND":
        frequencies = np.fft.rfftfreq(len(a), 1 / 4096)
        spectrum = abs(np.fft.rfft(a))
        if mode == "FILTERED":
            assert spectrum[np.argmin(abs(frequencies - 40))] > 100 * spectrum[
                np.argmin(abs(frequencies - 150))]
        else:
            assert spectrum[np.argmin(abs(frequencies - 740))] > spectrum[
                np.argmin(abs(frequencies - 40))]


def test_mode_transition_is_short_and_sequence_retry_is_idempotent():
    sonar = SonarSystem()
    source = tone(32)
    sonar.set_audition_mode("BROADBAND")
    sonar.listening_samples(source, block_id=1)
    sonar.set_audition_mode("FILTERED")
    changed = sonar.listening_samples(source, block_id=2)
    state = tuple(part.copy() for part in sonar._audition_ola_state)
    retry = sonar.listening_samples(np.zeros_like(source), block_id=2)
    np.testing.assert_array_equal(changed, retry)
    for before, after in zip(state, sonar._audition_ola_state):
        np.testing.assert_array_equal(before, after)
    # Blend starts on the old path instead of introducing a mode boundary step.
    assert changed[0] == pytest.approx(source[0])
    assert len(sonar._audition_states) <= 1


def test_filter_and_gain_transition_has_no_half_block_dropout():
    sonar = SonarSystem()
    sonar.set_audition_mode("FILTERED")
    sonar.band_low_hz, sonar.band_high_hz = 20, 80
    source = tone(40)
    sonar.listening_samples(source, block_id=1)
    steady = sonar.listening_samples(source, block_id=2)
    sonar.gain_db = 6
    changed = sonar.listening_samples(source, block_id=3)
    edge = round(.02 * sonar.receiver.sample_rate)
    assert np.sqrt(np.mean(changed[edge:512] ** 2)) > .75 * np.sqrt(
        np.mean(steady[edge:512] ** 2))


def test_audition_accepts_only_a_complete_mixed_receiver_block():
    sonar = SonarSystem()
    with pytest.raises(ValueError):
        sonar.listening_samples(NS(target_id=3), block_id=1)
    with pytest.raises(ValueError):
        sonar.listening_samples(np.zeros(100, dtype=np.float32), block_id=1)


def test_audio_status_separates_device_local_and_acceleration():
    game = Game(seed=1401, start_menu=False, audio_enabled=False)
    game.station = Station.SONAR
    game.sonar_audio_enabled = True
    game.sonar.set_audition_mode("HETERODYNE")
    status = game.sonar_audio_status()
    assert status["global_enabled"] is False
    assert status["device_available"] is False
    assert status["local_enabled"] is True
    assert status["mode"] == "HETERODYNE" and not status["audible"]
    game.time_scale_idx = 1
    assert game.sonar_audio_status()["muted_above_1x"] is True


def test_independent_fixes_coexist_have_separate_ages_and_expire_without_draw():
    contact = Contact(7, 17, "passiv", "sub")
    contact._fx = contact._fy = 0
    contact.update_ping(90, 10, 80, .8, 10, range_sigma_nm=.2,
                        depth_sigma_m=2, fixed_at=12)
    contact.update_buoy(8, 3, .7, 20)
    contact.update_tma(NS(pos=(7, 4), course=30, speed=8, quality=.8), 30)
    fixes = contact.active_fixes(40)
    assert [fix["source"] for fix in fixes] == ["PING", "TMA", "SONOBUOY"]
    assert [(40 - fix["measured_at"], 40 - fix["fixed_at"]) for fix in fixes] == [
        (30, 28), (10, 10), (20, 20)]
    contact.expire_ping_fix(10 + config.SONAR_PING_FIX_MAX_AGE_S + .1)
    assert "PING" not in contact.fixes


def test_bridge_fix_draw_and_hit_share_geometry_and_expiration():
    game = Game(seed=1402, start_menu=False, audio_enabled=False)
    game.map_follow = False
    game.map_view.set_rect(config.MAP_RECT)
    game.map_view.cx = game.map_view.cy = 250
    game.map_view.scale = 4
    game.radar_tracks = lambda: []
    contact = Contact(9, game.subs[0].id, "passiv", "sub")
    contact._publish_fix("TMA", game.sim_t, game.sim_t, 260, 240, 1, .8)
    game.sonar.contacts = {contact.target_id: contact}
    marker = map_view.active_fix_markers(game, game.map_view)[0][2]
    assert map_view.map_hit_target(game, marker)["id"] == "map:sonar:9:fix:tma"
    contact.fixes["TMA"]["uncertainty_nm"] = 10
    ring = (marker[0] + 40, marker[1])
    assert map_view.map_hit_target(game, ring)["id"] == "map:sonar:9:fix:tma"
    game.sim_t += config.SONAR_CONTACT_LOST_S + .1
    assert map_view.active_fix_markers(game, game.map_view) == []
    assert map_view.map_hit_target(game, marker)["id"].startswith("chart:")


def test_delayed_tma_fix_keeps_measurement_and_publication_times_separate():
    contact = Contact(8, 18, "passiv", "sub")
    contact._fx = contact._fy = 0
    solution = NS(pos=(4, 5), course=20, speed=7, quality=.8)
    contact.update_tma(solution, 10, fixed_at=25)
    fix = contact.fixes["TMA"]
    assert fix["measured_at"] == 10
    assert fix["fixed_at"] == 25


def test_fix_and_audition_mode_save_roundtrip_and_malformed_rejection():
    game = Game(seed=1403, start_menu=False, audio_enabled=False)
    game.sim_t = 50
    contact = Contact(3, game.subs[0].id, "passiv", "sub")
    contact._publish_fix("PING", 40, 42, 200, 210, .3, .9, 70, 2)
    game.sonar.contacts = {contact.target_id: contact}
    game.sonar.set_audition_mode("HETERODYNE")
    state = game.save_state()
    restored = Game(seed=1, start_menu=False, audio_enabled=False)
    restored.load_state(copy.deepcopy(state))
    canonical = restored.save_state()
    canonical["next_entity_ids"] = state["next_entity_ids"]
    assert canonical == state
    assert restored.sonar.audition_mode == "HETERODYNE"
    malformed = copy.deepcopy(state)
    malformed["sonar"]["contacts"][str(contact.target_id)]["fixes"][0]["x"] = float("nan")
    before = restored.save_state()
    with pytest.raises(ValueError):
        restored.load_state(malformed)
    assert restored.save_state() == before


def test_exact_r13_sonar_shape_has_narrow_v10_upgrade():
    game = Game(seed=1404, start_menu=False, audio_enabled=False)
    prior = game.save_state()
    del prior["sonar_controls"]["audition_mode"]
    for contact in prior["sonar"]["contacts"].values():
        del contact["fixes"]
    candidate = Game(seed=1, start_menu=False, audio_enabled=False)
    assert candidate._load_save_data(prior, allow_pre_r9=True)
    malformed = copy.deepcopy(prior)
    malformed["sonar_controls"]["unknown_r13_field"] = True
    assert not candidate._load_save_data(malformed, allow_pre_r9=True)
