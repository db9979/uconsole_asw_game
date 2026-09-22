"""Independent buoy evidence and helicopter publication contract."""

import json
import math
import random
from types import SimpleNamespace as NS

import pygame
import pytest

from src.air.sonobuoy import Sonobuoy
from src.commander.bridge import CommanderBridge
from src.core import config
from src.core.game import Game
from src.core.station import Station
from src.enemies.sub import Sub
from src.ship.ship import Ship
from src.sonar.sonar import Contact, SonarSystem
from src.ui.stations_view import helicopter_acoustic_geometry, helicopter_acoustic_hit


def test_single_passive_buoy_keeps_only_its_measured_bearing():
    ship = Ship(250, 250, speed_kn=0)
    world = NS(sea_state=0, thermocline_depth_m=lambda x, y: 100)
    sub = Sub(20, 20, 40, 0, "diesel_alt", random.Random(5))
    buoy = Sonobuoy(20, 18, 1)
    sonar = SonarSystem(5)
    sonar.update(.25, .25, ship, [sub], world, buoys=[buoy])
    contact = sonar.contacts[sub.id]
    report = contact.buoy_reports[1]
    assert report["mode"] == "PASSIVE"
    assert report["observer_x"] == buoy.x and report["observer_y"] == buoy.y
    assert report["range_nm"] is None and report["x"] is None
    assert contact.passive_bearing is None
    assert contact.range_source is None


def test_active_buoy_pings_every_thirty_seconds_with_no_exact_truth():
    ship = Ship(250, 250, speed_kn=0)
    world = NS(sea_state=0, thermocline_depth_m=lambda x, y: 100)
    sub = Sub(20, 20, 40, 0, "diesel_alt", random.Random(5))
    buoy = Sonobuoy(20, 18, 1, "ACTIVE")
    sonar = SonarSystem(5)
    sonar.update(.25, .25, ship, [sub], world, buoys=[buoy])
    first = dict(sonar.contacts[sub.id].buoy_reports[1])
    assert first["mode"] == "ACTIVE" and first["range_nm"] is not None
    assert 0 < math.hypot(first["x"] - sub.x, first["y"] - sub.y) < 1
    sonar.update(.25, 1.0, ship, [sub], world, buoys=[buoy])
    assert sonar.contacts[sub.id].buoy_reports[1] == first
    sonar.update(.25, config.BUOY_PING_COOLDOWN_S, ship, [sub], world,
                 buoys=[buoy])
    assert sonar.contacts[sub.id].buoy_reports[1]["measured_at"] == 30.0


def test_buoy_release_requires_confirmation_and_preserves_origin_after_save():
    game = Game(seed=901, start_menu=False, audio_enabled=False)
    contact = Contact(1, game.subs[0].id, "passiv", "sub")
    contact.update_passive(90.0, .8, .8, "", game.sim_t)
    contact.ship_observer_x = game.ship.x
    contact.ship_observer_y = game.ship.y
    buoy = Sonobuoy(game.ship.x + 2, game.ship.y + 1, 1)
    game.buoys = [buoy]
    game.buoy_seq = 1
    game.helo.buoys_left -= 1
    contact.buoy_reports[1] = dict(
        mode="PASSIVE", bearing=180.0, bearing_uncertainty_deg=2.0,
        quality=.7, measured_at=game.sim_t, observer_x=buoy.x,
        observer_y=buoy.y, range_nm=None, x=None, y=None)
    game.sonar.contacts[contact.target_id] = contact
    game.sonar._next_contact_id = 2
    assert game.release_sonar_contact(contact, True, source="buoy") == "not_qualified"
    assert game.qualify_helicopter_contact(contact, True) is True
    assert game.release_sonar_contact(contact, True, source="buoy") is True
    assert game.release_sonar_contact(contact, True, source="sonar") is True
    tracks = game.opz_tracks()
    assert len(tracks) == 2
    buoy_track = next(row for row in tracks if row.source.startswith("SONAR-BUOY"))
    assert (buoy_track.observer_x, buoy_track.observer_y) == (buoy.x, buoy.y)
    assert buoy_track.x is None and buoy_track.range_nm is None
    restored = Game(seed=902, start_menu=False, audio_enabled=False)
    restored.load_state(json.loads(json.dumps(game.save_state(), allow_nan=False)))
    restored_contact = restored.sonar.contacts[contact.target_id]
    assert restored_contact.helo_qualified and restored_contact.buoy_released_to_opz
    assert restored.buoys[0].mode == "PASSIVE"
    assert [row.source for row in restored.opz_tracks()] == [row.source for row in tracks]
    assert restored.qualify_helicopter_contact(restored_contact, False) is True
    assert not any(row.source.startswith("SONAR-BUOY") for row in restored.opz_tracks())


def test_helicopter_live_audio_requires_selected_wet_passive_receiver():
    game = Game(seed=903, start_menu=False, audio_enabled=False)
    assert not game.helicopter_audio_ready()
    game.helo.state = "AUF"
    game.helo.dip_state = "DEPLOYING"
    game.helo.dip_depth_m = 10.0
    assert not game.helicopter_audio_ready()
    game.helo.dip_state = "DEPLOYED"
    assert game.helicopter_audio_ready()
    game.helo.dip_state = "STOWED"
    passive = Sonobuoy(game.ship.x, game.ship.y, 1, "PASSIVE")
    active = Sonobuoy(game.ship.x, game.ship.y, 2, "ACTIVE")
    game.buoys = [passive, active]
    assert game.set_helicopter_listen_source("SB1") is True
    assert game.helicopter_audio_ready()
    passive.battery_s = 0.0
    assert not game.helicopter_audio_ready()
    assert game.set_helicopter_listen_source("SB2") is True
    assert not game.helicopter_audio_ready()


def test_helicopter_audio_publication_clears_dry_stream():
    class AudioServer:
        def __init__(self):
            self.clears = 0
            self.prepares = 0

        def clear_helicopter_audio(self):
            self.clears += 1

        def prepare_helicopter_audio(self, **_context):
            self.prepares += 1
            return 1

        def publish_helicopter_audio(self, *_args, **_context):
            raise AssertionError("dry helicopter audio must not publish")

    game = Game(seed=904, start_menu=False, audio_enabled=False)
    bridge, server = CommanderBridge(), AudioServer()
    bridge._publish_helicopter_audio(game, server, "live")
    assert server.clears == 1 and server.prepares == 0
    game.helo.state = "AUF"
    game.helo.dip_state = "DEPLOYED"
    game.helo.dip_depth_m = 10.0
    bridge._publish_helicopter_audio(game, server, "live")
    assert server.prepares > 0
    game.helo.dip_state = "STOWED"
    bridge._publish_helicopter_audio(game, server, "live")
    assert server.clears >= 2


def test_native_helicopter_acoustics_uses_full_station_area():
    game = Game(seed=905, start_menu=False, audio_enabled=False)
    game.station = Station.HELICOPTER
    game.station_page = 3
    assert not game._map_station_visible()
    game.draw()
    # The former right-hand station panel starts at x=640. The selected
    # acoustic page now paints its instrument across the left half too.
    assert game.screen.get_at((100, 140))[:3] != (0, 0, 0)
    game.station_page = 2
    assert game._map_station_visible()


def test_helicopter_listening_controls_are_independent_of_ship_sonar():
    game = Game(seed=906, start_menu=False, audio_enabled=False)
    ship_mode = game.sonar.audition_mode
    ship_gain = game.sonar.gain_db
    assert game.set_helicopter_listen_bearing(217.5) is True
    assert game.set_helicopter_audio_mode("HETERODYNE") is True
    assert game.set_helicopter_audio_band("LOW") is True
    assert game.set_helicopter_audio_gain(12) is True
    assert game.set_helicopter_audio_notch(True) is True
    assert game.helo_listen_bearing == 217.5
    assert game.helo_audition.audition_mode == "HETERODYNE"
    assert game.helo_audio_band == "LOW"
    assert game.helo_audition.gain_db == 12
    assert game.helo_audition.notch_enabled
    assert (game.sonar.audition_mode, game.sonar.gain_db) == (ship_mode, ship_gain)
    assert game.set_helicopter_listen_bearing(360) == "invalid_value"
    assert game.set_helicopter_audio_mode("OTHER") == "invalid_value"
    assert game.set_helicopter_audio_band("OTHER") == "invalid_value"
    assert game.set_helicopter_audio_gain(float("nan")) == "invalid_value"
    assert game.set_helicopter_audio_notch(1) == "invalid_value"
    assert game.set_helicopter_listen_bearing(None) is True


def test_native_helicopter_audio_waits_for_water_then_plays_without_rearming(monkeypatch):
    game = Game(seed=907, start_menu=False, audio_enabled=False)
    game.station = Station.HELICOPTER
    played = []
    monkeypatch.setattr(game.audio, "play_sonar", lambda samples, *_args, **_kwargs:
                        played.append(samples.copy()) or True)
    game._update_audio(.25)
    assert game.helo_audio_enabled and not played
    game.helo.state = "AUF"
    game.helo.dip_state = "DEPLOYED"
    game.helo.dip_depth_m = 30.0
    game.helo_receiver.update([], 0.0, 18.0, .2, 0.0, 0.0)
    game._update_audio(.25)
    assert played and played[0].size == game.helo_receiver.samples.size
    assert game.helo_audio_enabled
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_j, mod=0))
    assert not game.helo_audio_enabled and game.sonar_audio_enabled
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_j, mod=0))
    assert game.helo_audio_enabled
    game.station_page = 3
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_n, mod=0))
    assert game.helo_audition.notch_enabled and not game.administration_open


def test_helicopter_receiver_updates_when_ship_sonar_station_is_down(monkeypatch):
    game = Game(seed=909, start_menu=False, audio_enabled=False)
    game.station = Station.HELICOPTER
    game.helo.state = "AUF"
    game.helo.x, game.helo.y = game.ship.x, game.ship.y
    game.helo.dip_state = "DEPLOYED"
    game.helo.dip_depth_m = 30.0
    monkeypatch.setattr(game.damage, "station_down", lambda station:
                        station == "sonar")
    before = game.helo_receiver.sequence
    game._update_sensors(.25)
    assert game.helo_receiver.sequence > before


def test_first_passive_buoy_becomes_listening_source_when_dip_is_dry():
    game = Game(seed=910, start_menu=False, audio_enabled=False)
    game.helo.state = "AUF"
    game.helo.x, game.helo.y = game.ship.x, game.ship.y
    assert game.deploy_helicopter_buoy() is True
    assert game.helo_listen_source == "SB1"
    assert game.helicopter_audio_ready()
    restored = Game(seed=912, start_menu=False, audio_enabled=False)
    restored.load_state(json.loads(json.dumps(game.save_state(), allow_nan=False)))
    assert restored.helo_listen_source == "SB1"
    assert restored.helicopter_audio_ready()


def test_wet_buoy_reaches_local_audio_mixer():
    game = Game(seed=911, start_menu=False, audio_enabled=True)
    if not game.audio.available:
        pytest.skip("No SDL audio mixer available")
    try:
        game.station = Station.HELICOPTER
        game.buoys = [Sonobuoy(game.ship.x, game.ship.y, 1)]
        assert game.set_helicopter_listen_source("SB1") is True
        game.update(.5)
        assert game.helo_receiver.sequence > 0
        assert game._sonar_audio_sequence == game.helo_receiver.sequence
        assert game.audio.sonar_dropped_blocks == 0
    finally:
        game.audio.shutdown()


def test_native_helicopter_acoustic_tabs_and_bearing_click():
    game = Game(seed=908, start_menu=False, audio_enabled=False)
    game.station = Station.HELICOPTER
    game.station_page = 3
    rect = pygame.Rect(config.FULL_STATION_RECT)
    geo = helicopter_acoustic_geometry(rect)
    assert geo["plot"].w > 700 and geo["plot"].h > 300
    assert helicopter_acoustic_hit(game, geo["back"].center) == ("deck", 2)
    for index, tab in enumerate(geo["tabs"]):
        assert helicopter_acoustic_hit(game, tab.center) == ("page", index)
    game.helo_acoustic_page = 0
    action, bearing = helicopter_acoustic_hit(game, geo["plot"].center)
    assert action == "bearing" and 175 <= bearing <= 185
    contact = Contact(77, game.subs[0].id, "passiv", "sub")
    contact.update_dip_passive(126, game.sim_t, game.ship.x, game.ship.y, 2)
    game.sonar.contacts[contact.target_id] = contact
    row = pygame.Rect(geo["rail"].x + 8, geo["rail"].y + 132,
                      geo["rail"].w - 16, 43)
    assert helicopter_acoustic_hit(game, row.center) == ("contact", 77)
    game.helo_acoustic_page = 2
    game.draw()
    game.handle_event(pygame.event.Event(pygame.KEYDOWN,
                                        key=pygame.K_PAGEUP, mod=0))
    assert game.helo_acoustic_page == 1
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                        button=1, pos=geo["tabs"][2].center))
    assert game.helo_acoustic_page == 2
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                        button=1, pos=geo["back"].center))
    assert game.station_page == 2
