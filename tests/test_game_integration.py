import random
import json
from unittest.mock import Mock

import numpy as np
import pygame
import pytest

import src.core.game as game_module
from src.core import config
from src.core.game import Game
from src.core.station import Station
from src.core.i18n import RawText, Translator, localize, message
from src.core.mission_definition import default_mission
from src.core.preferences import Preferences
from src.enemies.surface import SurfaceShip
from src.sonar.sonar import Contact


def test_mixer_preinit_precedes_pygame_init(monkeypatch):
    calls = []
    pre_init = pygame.mixer.pre_init
    init = pygame.init
    monkeypatch.setattr(pygame.mixer, "pre_init",
                        lambda *args, **kwargs: (calls.append(("pre", kwargs)),
                                                pre_init(*args, **kwargs))[1])
    monkeypatch.setattr(pygame, "init",
                        lambda: (calls.append(("init", {})), init())[1])
    game = Game(seed=80, audio_enabled=False)
    assert [name for name, _ in calls[:2]] == ["pre", "init"]
    assert calls[0][1] == {
        "frequency": game_module.config.AUDIO_SAMPLE_RATE,
        "size": -16,
        "channels": game_module.config.AUDIO_CHANNELS,
        "buffer": game_module.config.AUDIO_MIXER_BUFFER_MS,
    }
    game.audio.shutdown()


def test_update_passes_unclamped_wall_dt_to_audio(monkeypatch):
    """Der Main-Loop klemmt Sim-dt auf 0.1 s; die Audio-Cadence darf nicht."""
    game = Game(seed=84, audio_enabled=False)
    seen = []
    monkeypatch.setattr(game, "_update_audio", seen.append)
    game.update(0.1, audio_dt=0.35)
    assert seen == [0.35]
    game.update(0.1)
    assert seen == [0.35, 0.1]
    game.audio.shutdown()


def test_audio_hold_flag_follows_time_scale(monkeypatch):
    """Sonar-Block-Hold nur bei 1x; Zeitraffer bleibt sampled preview."""
    game = Game(seed=85, audio_enabled=False)
    game.station = Station.SONAR
    game.sonar_audio_enabled = True
    blocks = [(1, np.ones(4096, dtype=np.float32))]
    monkeypatch.setattr(game.sonar.receiver, "blocks_since", lambda seq: blocks)
    monkeypatch.setattr(game.sonar, "listening_samples", lambda samples: samples)
    spy = Mock(return_value=True)
    monkeypatch.setattr(game.audio, "play_sonar", spy)
    game._update_audio(0.25)
    assert spy.call_args.kwargs["hold"] is True
    game.time_scale_idx = config.TIME_SCALE_STEPS.index(5)
    game._update_audio(0.25)
    assert spy.call_args.kwargs["hold"] is False
    game.audio.shutdown()


def test_audio_replacement_and_run_shutdown_old_engines(monkeypatch):
    game = Game(seed=81, audio_enabled=False)
    initial = game.audio
    monkeypatch.setattr(initial, "shutdown", Mock(wraps=initial.shutdown))
    replacement = Mock(available=False)
    monkeypatch.setattr(game_module, "AudioEngine", Mock(return_value=replacement))
    monkeypatch.setattr(game_module, "save_preferences", Mock())
    game._set_preference("audio", True)
    old = game_module.AudioEngine.return_value
    assert game.audio is old
    initial.shutdown.assert_called_once()

    # The engine present before replacement was shut down by the transition.
    # Use a second transition to make that ownership directly observable.
    newer = Mock(available=False)
    game_module.AudioEngine.return_value = newer
    game._set_preference("audio", False)
    old.shutdown.assert_called_once()
    assert game._sonar_audio_sequence == -1

    game.running = False
    monkeypatch.setattr(pygame, "quit", Mock())
    game.run()
    newer.shutdown.assert_called_once()


def test_options_apply_global_tooltip_preference_and_language_state(monkeypatch):
    game = Game(seed=82, audio_enabled=False,
                preferences=Preferences(language="en", tooltips=True))
    save = Mock()
    monkeypatch.setattr(game_module, "save_preferences", save)
    game.pinned_tooltip = {"title": "old", "lines": []}
    game._set_preference("tooltips", False)
    assert not game.tooltips_enabled and not game.preferences.tooltips
    assert game.pinned_tooltip is None
    save.assert_called_with(game.preferences)

    game.pinned_tooltip = {"title": "old", "lines": []}
    game._set_preference("language", "de")
    assert game.pinned_tooltip is None
    assert "Deutsch" in localize(game.msg, game.tr)
    assert pygame.display.get_caption()[0] == game.tr("app.title")


def test_runtime_notices_are_structured_for_bt_listening_and_launches(monkeypatch):
    game = Game(seed=86, audio_enabled=False)
    game.station = game_module.Station.SONAR
    game.sonar.bt_profile = {"thermocline_m": 75.0}
    monkeypatch.setattr(game.sonar, "measure_environment", lambda *_: True)
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e, mod=0))
    assert game.msg["__u_jagd_i18n__"] == "runtime.bt.measured"
    assert game.feed.entries[-1].text["__u_jagd_i18n__"] == "runtime.bt.feed"

    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_d, mod=0))
    assert game.msg["__u_jagd_i18n__"] == "runtime.listen.filtered"

    game.helo.state = "HANGAR"
    game.toggle_helo()
    assert game.msg["__u_jagd_i18n__"] == "runtime.helo.launch"

    target = game.subs[0]
    contact = Contact(1, target.id, "ping", "sub")
    contact.player_class = "U_BOOT"
    contact.range_est = 4.0
    contact.range_source = "ping"
    contact.range_seen = contact.last_seen = game.sim_t
    contact.bearing = 0.0
    game.target = contact
    game.sonar.contacts[target.id] = contact
    game.launch_torpedo()
    assert game.msg["__u_jagd_i18n__"] == "runtime.torpedo.launched"
    assert game.feed.entries[-1].text["__u_jagd_i18n__"] == "runtime.torpedo.feed"


def test_runtime_language_switch_retranslates_feeds_and_keeps_legacy_strings(monkeypatch):
    game = Game(seed=87, audio_enabled=False,
                preferences=Preferences(language="en"))
    monkeypatch.setattr(game_module, "save_preferences", Mock())
    structured = message("runtime.helo.return")
    game.feed.add("12:00", "mission", structured)
    game.feed.add("12:01", "mission", "Saved")
    game.messages.extend((("12:00", structured), ("12:01", "Saved")))

    game._set_preference("language", "de")

    assert len(game.feed.entries) >= 2
    assert localize(game.feed.entries[-2].text, game.tr) == "HSP-5: Rückkehr befohlen"
    assert localize(game.feed.entries[-1].text, game.tr) == "Gespeichert"
    assert game.messages[-1] == ("12:01", "Saved")


def test_custom_runtime_mission_text_is_opaque():
    game = Game(seed=88, audio_enabled=False,
                preferences=Preferences(language="de"))
    game.custom_mission_definition = {"description": "Saved {verbatim}"}
    game.mission.name = "Save"

    assert isinstance(game.mission_name_display(), RawText)
    assert localize(game.mission_name_display(), Translator("de").t) == "Save"
    assert localize(game.mission_description_display(), Translator("de").t) == \
        "Saved {verbatim}"


@pytest.mark.parametrize(
    "objective_type,retained_type,english,german",
    (("sink", "konvoi", "Sink all submarines", "Alle U-Boote versenken"),
     ("survive", "nuklearer_abfang", "Convoy: survive the time limit",
      "Konvoi: Zeitlimit durchhalten")),
)
def test_custom_objective_and_start_feed_ignore_random_mission_type(
        objective_type, retained_type, english, german):
    game = Game(seed=89, audio_enabled=False,
                preferences=Preferences(language="en"))
    definition = default_mission("user.objective")
    definition["name"] = "Saved"
    definition["objective"]["type"] = objective_type
    game.level = "normal"

    assert game.start_custom_mission(definition)
    game.mission.type_key = retained_type
    objective = game.mission_objective_display()
    started = game.feed.entries[-1].text
    json.dumps(started)

    assert localize(objective, Translator("en").t) == english
    assert localize(objective, Translator("de").t) == german
    assert localize(started, Translator("en").t) == \
        f"Mission: Saved (Normal) - {english}"
    assert localize(started, Translator("de").t) == \
        f"Mission: Saved (Normal) - {german}"


def test_sensor_picture_uses_generic_evidence_not_platform_truth(monkeypatch):
    game = Game(seed=83, audio_enabled=False)
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)
    warship = SurfaceShip(game.ship.x + 4.0, game.ship.y,
                          random.Random(830), hostile=True)
    warship.emitter = True
    game.warships = [warship]
    game.civilians = []
    game.flights.flights = []
    game.asms = []
    game._update_air_picture()
    track = game.air_picture._tracks[f"W-{warship.id}"]
    assert track.label == f"W-{warship.id}"
    assert track.course is None and track.hostile is False
    assert warship.name not in track.label

    contact = Contact(7, warship.id, "ping", "surface")
    contact.last_seen = game.sim_t
    contact.confidence = contact.quality = 1.0
    contact.player_class = None
    contact.passive_bearing = 270.0
    contact.range_est = 99.0
    contact.range_source = "ping"
    contact.range_seen = game.sim_t
    contact.observed_x = game.ship.x + 3.0
    contact.observed_y = game.ship.y - 4.0
    monkeypatch.setattr(game.sonar, "update", Mock())
    monkeypatch.setattr(game.sonar, "active_contacts", lambda: [contact])
    game._update_sensors(.25)
    sonar_track = game.air_picture._tracks[f"U-{warship.id}"]
    assert (sonar_track.raw_x, sonar_track.raw_y) == pytest.approx(
        (contact.observed_x, contact.observed_y))
    assert sonar_track.label == "K7" and sonar_track.hostile is False
    assert sonar_track.course is None


def test_weapon_datum_uses_canonical_observed_position(monkeypatch):
    game = Game(seed=84, audio_enabled=False)
    target = game.subs[0]
    contact = Contact(1, target.id, "ping", "sub")
    contact.player_class = "U_BOOT"
    contact.range_est = 12.0
    contact.range_source = "ping"
    contact.range_seen = contact.last_seen = game.sim_t
    contact.bearing = 180.0
    contact.ping_pos = (game.ship.x + 8.0, game.ship.y)
    contact.tma_pos = (game.ship.x - 8.0, game.ship.y)
    contact.observed_x, contact.observed_y = game.ship.x, game.ship.y - 6.0
    game.target = contact
    game.sonar.contacts[target.id] = contact
    game.launch_torpedo()
    assert (game.torpedoes[-1].guidance_x, game.torpedoes[-1].guidance_y) == (
        contact.observed_x, contact.observed_y)

    update = Mock(return_value=True)
    monkeypatch.setattr(game.torpedoes[-1], "wire_update", update)
    game._update_player_torpedoes(0.1)
    update.assert_called_with(contact.observed_x, contact.observed_y)


def test_hfdf_noise_uses_sim_clock_and_is_smooth(monkeypatch):
    game = Game(seed=85, audio_enabled=False)
    sub = game.subs[0]
    sub.state = "SNOCKEL"
    sub.x, sub.y = game.ship.x + 4.0, game.ship.y
    game.subs = [sub]
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)

    game.sim_t, game._t = 9.99, 1.0
    game._update_radio_picture()
    first = game.radio_picture._tracks[f"H-{sub.id}"].raw_bearing
    game.radio_picture._tracks.clear()
    game._t = 10000.0
    game._update_radio_picture()
    assert game.radio_picture._tracks[f"H-{sub.id}"].raw_bearing == first

    game.radio_picture._tracks.clear()
    game.sim_t = 10.01
    game._update_radio_picture()
    second = game.radio_picture._tracks[f"H-{sub.id}"].raw_bearing
    assert abs(game_module.config.angle_diff_deg(second, first)) < .1
