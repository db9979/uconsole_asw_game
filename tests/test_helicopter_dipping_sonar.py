import copy
import json
import math
import random
from types import SimpleNamespace as NS

import pytest
import pygame

from src.air.helicopter import Helicopter
from src.core import config
from src.core.game import Game
from src.core.station import Station
from src.sonar.sonar import Contact, SonarSystem
from src.ui import stations_view


class Ocean:
    size_nm = 500.0
    sea_state = 0

    @staticmethod
    def on_land(x, y):
        return False

    @staticmethod
    def depth_m(x, y):
        return 120.0

    @staticmethod
    def thermocline_depth_m(x, y):
        return 60.0

    @staticmethod
    def sonar_path_blocked(*args):
        return False

    @staticmethod
    def echo_delay_s(distance):
        return distance * 1852.0 * 2.0 / config.SOUND_SPEED_M_S


class Target:
    def __init__(self, target_id=90001, x=5.0, y=0.0, depth=45.0):
        self.id = target_id
        self.sensor_seed = target_id + 17
        self.x, self.y, self.depth = x, y, depth
        self.stype = "test"
        self.sunk = False
        self.heard = 0

    def quiet_factor(self):
        return 0.0

    def acoustic_signature(self):
        return "test signature"

    def distance_nm(self, observer):
        return math.hypot(self.x - observer.x, self.y - observer.y)

    def bearing_from_frigate(self, observer):
        return math.degrees(math.atan2(
            self.x - observer.x, -(self.y - observer.y))) % 360.0

    def hear_ping(self):
        self.heard += 1


def test_dip_deploy_holds_hover_and_respects_water_depth():
    helo = Helicopter(random.Random(1))
    ship = NS(x=0.0, y=0.0, course=0.0)
    world = Ocean()
    helo.launch(ship)
    helo.set_waypoint(20.0, 0.0)

    assert helo.set_dipping(True, world)
    position = helo.x, helo.y
    helo.update(100.0, ship, world)

    assert (helo.x, helo.y) == position
    assert helo.dip_state == "DEPLOYED"
    assert helo.hovering and helo.dip_available
    assert helo.dip_depth_m == pytest.approx(helo.dip_depth_target_m)
    assert helo.dip_depth_m <= world.depth_m(0, 0) - config.HELO_DIP_BOTTOM_CLEARANCE_M

    helo.order_return()
    helo.update(100.0, ship, world)
    assert helo.dip_state == "STOWED"


def test_dipping_passive_bearing_uses_helicopter_origin_deterministically():
    helo = Helicopter(random.Random(2))
    helo.state = "AUF"
    helo.x, helo.y = 10.0, 20.0
    helo.dip_state = "DEPLOYED"
    helo.dip_depth_m = 75.0
    target = Target(x=14.0, y=20.0)
    first, second = SonarSystem(77), SonarSystem(77)

    for sonar in (first, second):
        sonar.update_dipping_passive(.25, 12.0, helo, [target], Ocean())

    contact = first.contacts[target.id]
    assert (contact.dip_observer_x, contact.dip_observer_y) == (helo.x, helo.y)
    assert contact.range_est is None
    assert contact.dip_bearing == second.contacts[target.id].dip_bearing
    assert abs(config.angle_diff_deg(contact.dip_bearing, 90.0)) \
        <= config.HELO_DIP_BEARING_ERR_DEG
    # W2: the ship's own passive track is a fully separate state and must
    # stay untouched by a helicopter dip (this was the reported bug: a dip
    # was overwriting the frigate's own bearing every tick).
    assert contact.passive_bearing is None
    assert contact.passive_source == "SONAR-BRG"


def test_helicopter_dip_never_overwrites_ships_own_passive_bearing():
    """Reported bug: as long as the helicopter was also dipping, the ship's
    own passive bearing on the same contact kept disappearing every tick,
    because both wrote into the same Kalman-filter state despite being
    measured from two different platforms."""
    sonar = SonarSystem(55)
    ship = NS(x=0.0, y=0.0, speed=0.0, course=0.0)
    target = Target(target_id=90050, x=10.0, y=0.0)

    # The ship hears the contact on its own bow array first.
    contact = sonar._get_contact(target)
    contact._fx, contact._fy = ship.x, ship.y
    contact.observer_x, contact.observer_y = ship.x, ship.y
    contact.passive_source = "SONAR-BRG"
    ship_bearing_before = 90.0
    contact.update_passive(ship_bearing_before, .6, .6, "test signature", 10.0)
    assert contact.passive_bearing == pytest.approx(ship_bearing_before)

    helo = Helicopter(random.Random(9))
    helo.state = "AUF"
    helo.x, helo.y = 5.0, 5.0
    helo.dip_state = "DEPLOYED"
    helo.dip_depth_m = 75.0

    for tick in range(20):
        sonar.update_dipping_passive(.25, 10.25 + tick * .25, helo, [target],
                                     Ocean())

    # The frigate's own tracked bearing must still be there and unchanged by
    # the helicopter's independent dip measurements.
    assert contact.passive_bearing == pytest.approx(ship_bearing_before)
    assert contact.passive_source == "SONAR-BRG"
    assert (contact.observer_x, contact.observer_y) == (0.0, 0.0)
    # The helicopter gets its own, separately tracked bearing.
    assert contact.dip_bearing is not None
    assert (contact.dip_observer_x, contact.dip_observer_y) == (helo.x, helo.y)


def test_dipping_ping_delivers_frozen_helicopter_snapshot_after_delay():
    helo = Helicopter(random.Random(3))
    helo.state = "AUF"
    helo.x, helo.y = 10.0, 20.0
    helo.dip_state = "DEPLOYED"
    helo.dip_depth_m = 75.0
    target = Target(x=15.0, y=20.0)
    sonar = SonarSystem(88)

    assert helo.fire_dipping_ping()
    sonar.queue_ping(helo, [target], Ocean(), 4.0, mode="DIPPING")
    pending = sonar._pending_pings[0]
    snapshot = dict(pending["snapshot"])
    helo.x, helo.y = 100.0, 200.0
    target.x, target.y, target.depth = 300.0, 400.0, 250.0

    sonar._process_pending_pings(pending["ready_at"] - .001)
    assert not sonar.contacts
    sonar._process_pending_pings(pending["ready_at"])
    contact = sonar.contacts[target.id]
    expected = (
        snapshot["observer_x"] + snapshot["range_nm"]
        * math.sin(math.radians(snapshot["bearing"])),
        snapshot["observer_y"] - snapshot["range_nm"]
        * math.cos(math.radians(snapshot["bearing"])),
    )
    assert contact.ping_pos == pytest.approx(expected)
    assert contact.fixes["DIPPING"]["measured_at"] == 4.0
    assert sonar.echo_history[-1]["mode"] == "DIPPING"


def test_classification_and_continuous_opz_release_are_independent():
    game = Game(seed=901, start_menu=False, audio_enabled=False)
    game.sonar.contacts.clear()
    contact = Contact(1, 90001, "passiv", "sub")
    contact.update_passive(45.0, .8, .8, "hidden", game.sim_t)
    game.sonar.contacts[contact.target_id] = contact

    assert game.classify_sonar_contact(contact, "U_BOOT") is True
    assert not game.opz_tracks()
    assert game.release_sonar_contact(contact, True) is True
    assert game.opz_tracks()[0].classification == "U_BOOT"

    contact.update_passive(50.0, .9, .9, "hidden", game.sim_t + 1.0)
    game.sim_t += 1.0
    assert game.classify_sonar_contact(contact, None) is True
    report = game.opz_tracks()[0]
    assert report.classification is None and report.released_to_opz
    assert report.bearing == contact.passive_bearing
    assert game.release_sonar_contact(contact, False) is True
    assert not game.opz_tracks()


def test_native_opz_bearing_ray_starts_at_released_helicopter_origin():
    game = Game(seed=907, start_menu=False, audio_enabled=False)
    game.sonar.contacts.clear()
    contact = Contact(1, 99002, "dipping-passiv", "sub")
    contact.update_dip_passive(0.0, game.sim_t, game.ship.x + 5.0,
                               game.ship.y, 1.5)
    contact.dip_released_to_opz = True
    game.sonar.contacts[contact.target_id] = contact
    report = game.opz_tracks()[0]
    ppi = pygame.Rect(0, 0, 400, 400)

    start, end = stations_view._opz_bearing_ray(game, report, ppi, 20.0)

    assert start[0] > ppi.centerx
    assert start[1] == pytest.approx(ppi.centery)
    assert end[1] < start[1]


def test_ship_and_helicopter_release_create_two_independent_opz_bearings():
    game = Game(seed=911, start_menu=False, audio_enabled=False)
    game.sonar.contacts.clear()
    contact = Contact(1, 99003, "passiv", "sub")
    contact.update_passive(90.0, .8, .8, "hidden", game.sim_t)
    contact.observer_x, contact.observer_y = game.ship.x, game.ship.y
    contact.ship_observer_x, contact.ship_observer_y = game.ship.x, game.ship.y
    contact.update_dip_passive(180.0, game.sim_t, game.ship.x + 5.0,
                               game.ship.y - 5.0, 1.5)
    game.sonar.contacts[contact.target_id] = contact

    assert game.release_sonar_contact(contact, True) is True
    assert len(game.opz_tracks()) == 1
    assert game.release_sonar_contact(contact, True, source="helicopter") == "not_qualified"
    assert game.qualify_helicopter_contact(contact, True) is True
    assert game.release_sonar_contact(contact, True, source="helicopter") is True
    tracks = game.opz_tracks()
    assert len(tracks) == 2
    ship = next(track for track in tracks if track.source == "SONAR-BRG")
    dip = next(track for track in tracks if track.source == "SONAR-DIP-BRG")
    assert ship.observation_id != dip.observation_id
    assert (ship.observer_x, ship.observer_y) == (game.ship.x, game.ship.y)
    assert (dip.observer_x, dip.observer_y) == (game.ship.x + 5.0, game.ship.y - 5.0)
    assert (ship.bearing, dip.bearing) == (90.0, 180.0)
    chart = pygame.Rect(0, 0, 400, 400)
    ship_ray = stations_view._opz_bearing_ray(game, ship, chart, 20.0)
    dip_ray = stations_view._opz_bearing_ray(game, dip, chart, 20.0)
    assert ship_ray[0] == pytest.approx((200.0, 200.0))
    assert dip_ray[0] == pytest.approx((250.0, 150.0))
    game.ship.x += 1.0
    # Both rays keep their measured origins when the frigate moves.
    assert stations_view._opz_bearing_ray(game, ship, chart, 20.0)[0] == \
        pytest.approx((190.0, 200.0))
    assert stations_view._opz_bearing_ray(game, dip, chart, 20.0)[0] == \
        pytest.approx((240.0, 150.0))
    game.ship.x -= 1.0

    contact._fx, contact._fy = game.ship.x + 5.0, game.ship.y - 5.0
    contact.observer_x, contact.observer_y = contact._fx, contact._fy
    contact.update_ping(180.0, 5.0, 60.0, .9, game.sim_t,
                        fix_source="DIPPING")
    tracks_after_ping = game.opz_tracks()
    assert {track.source for track in tracks_after_ping} == {
        "SONAR-BRG", "SONAR-DIP-BRG"}
    ship_after_ping = next(track for track in tracks_after_ping
                           if track.source == "SONAR-BRG")
    assert (ship_after_ping.observer_x, ship_after_ping.observer_y) == (
        game.ship.x, game.ship.y)

    assert game.release_sonar_contact(contact, False, source="helicopter") is True
    assert [track.observation_id for track in game.opz_tracks()] == [ship.observation_id]
    assert game.release_sonar_contact(contact, True, source="helicopter") is True
    assert game.release_sonar_contact(contact, False) is True
    assert [track.observation_id for track in game.opz_tracks()] == [dip.observation_id]


def test_same_v10_upgrader_recognizes_only_prior_exact_release_shape():
    game = Game(seed=902, start_menu=False, audio_enabled=False)
    contact = Contact(1, game.subs[0].id, "passiv", "sub")
    contact.update_passive(45.0, .8, .8, "hidden", game.sim_t)
    contact.player_class = "U_BOOT"
    game.sonar.contacts[contact.target_id] = contact
    game.sonar._next_contact_id = 2
    old = copy.deepcopy(game.save_state())
    for key in ("dip_state", "dip_depth_m", "dip_depth_target_m",
                "dip_water_depth_m", "dip_ping_cooldown"):
        del old["helo"][key]
    for row in old["sonar"]["contacts"].values():
        for key in ("released_to_opz", "dip_released_to_opz", "ship_observer_x", "ship_observer_y",
                    "passive_source", "observer_x", "observer_y",
                    "dip_bearing", "dip_bearing_uncertainty_deg", "dip_last_seen",
                    "dip_observer_x", "dip_observer_y", "buoy_reports",
                    "helo_qualified", "buoy_released_to_opz"):
            del row[key]

    restored = Game(seed=903, start_menu=False, audio_enabled=False)
    assert restored._load_save_data(old, allow_pre_r9=True)
    upgraded = restored.sonar.contacts[contact.target_id]
    assert upgraded.released_to_opz and upgraded.player_class == "U_BOOT"
    assert restored.helo.dip_state == "STOWED"

    malformed = copy.deepcopy(old)
    malformed["helo"]["dip_state"] = "STOWED"
    assert not restored._load_save_data(malformed, allow_pre_r9=True)


def test_v10_roundtrip_preserves_dip_release_and_pending_echo(monkeypatch):
    game = Game(seed=904, start_menu=False, audio_enabled=False)
    target = game.subs[0]
    target.x, target.y, target.depth = game.ship.x + 1.0, game.ship.y, 10.0
    game.helo.launch(game.ship)
    game.helo.x, game.helo.y = game.ship.x, game.ship.y
    game.helo.dip_state = "DEPLOYED"
    game.helo.dip_depth_m = game.helo.dip_depth_target_m = 50.0
    game.helo.dip_water_depth_m = max(60.0, game.world.depth_m(
        game.helo.x, game.helo.y))
    game.helo.dip_ping_cooldown = 12.0
    monkeypatch.setattr(game.world, "sonar_path_blocked", lambda *args: False)
    game.sonar.queue_ping(game.helo, [target], game.world, game.sim_t,
                          mode="DIPPING")
    assert game.sonar._pending_pings
    contact = game.sonar._get_contact(target)
    contact.released_to_opz = True
    contact.dip_released_to_opz = True
    contact.ship_observer_x, contact.ship_observer_y = game.ship.x, game.ship.y

    state = json.loads(json.dumps(game.save_state(), allow_nan=False))
    restored = Game(seed=905, start_menu=False, audio_enabled=False)
    restored.load_state(state)

    assert restored.helo.dip_state == "DEPLOYED"
    assert restored.helo.dip_depth_m == 50.0
    assert restored.helo.dip_ping_cooldown == 12.0
    assert restored.sonar.contacts[target.id].released_to_opz
    assert restored.sonar.contacts[target.id].dip_released_to_opz
    assert (restored.sonar.contacts[target.id].ship_observer_x,
            restored.sonar.contacts[target.id].ship_observer_y) == (
                game.ship.x, game.ship.y)
    assert restored.sonar._pending_pings[0]["mode"] == "DIPPING"
    assert restored.sonar._pending_pings[0]["snapshot"] == \
        state["sonar"]["pending_pings"][0]["snapshot"]


def test_native_keys_control_release_and_dipping(monkeypatch):
    game = Game(seed=906, start_menu=False, audio_enabled=False)
    game.sonar.contacts.clear()
    contact = Contact(1, 99001, "passiv", "sub")
    contact.update_passive(20.0, .8, .8, "hidden", game.sim_t)
    game.sonar.contacts[contact.target_id] = contact
    game.selected_contact = contact
    game.station = Station.SONAR

    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_g, mod=0))
    assert contact.released_to_opz

    monkeypatch.setattr(game.world, "on_land", lambda *args: False)
    monkeypatch.setattr(game.world, "depth_m", lambda *args: 120.0)
    monkeypatch.setattr(game.world, "sonar_path_blocked", lambda *args: False)
    game.helo.launch(game.ship)
    game.station = Station.HELICOPTER
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_y, mod=0))
    assert game.helo.dip_state == "DEPLOYING"
    game.helo.update(40.0, game.ship, game.world)
    assert game.helo.dip_state == "DEPLOYED"
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_a, mod=0))
    assert game.helo.dip_ping_cooldown == config.HELO_DIP_PING_COOLDOWN_S
    prior_depth = game.helo.dip_depth_target_m
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_v, mod=0))
    assert game.helo.dip_depth_target_m > prior_depth
    assert game.helo.dip_state == "DEPLOYING"


def test_helicopter_station_can_cycle_and_release_its_own_dip_plot():
    """Feature request: the helicopter needs its own active-ping plotter and
    a way to release what it found to CIC directly from its own station."""
    game = Game(seed=908, start_menu=False, audio_enabled=False)
    game.sonar.contacts.clear()
    game.station = Station.HELICOPTER

    # A contact the ship's own array holds - no dip - must never appear here.
    ship_only = Contact(1, 90101, "passiv", "sub")
    ship_only.update_passive(10.0, .8, .8, "hidden", game.sim_t)
    game.sonar.contacts[ship_only.target_id] = ship_only

    # A contact the helicopter's own dip has plotted.
    dip_found = Contact(2, 90102, "dipping-passiv", "sub")
    dip_found.update_dip_passive(200.0, game.sim_t, 12.0, 34.0, 1.5)
    game.sonar.contacts[dip_found.target_id] = dip_found

    assert game.selected_contact is None
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_g, mod=0))
    assert game.selected_contact is dip_found
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_f, mod=0))
    assert dip_found.helo_qualified

    game.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_g, mod=pygame.KMOD_SHIFT))
    assert dip_found.dip_released_to_opz is True
    assert dip_found.released_to_opz is False
    assert ship_only.released_to_opz is False

    game.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_g, mod=pygame.KMOD_SHIFT))
    assert dip_found.dip_released_to_opz is False


def test_helicopter_view_shows_only_the_helicopters_own_dip_plot():
    game = Game(seed=909, start_menu=False, audio_enabled=False)
    game.sonar.contacts.clear()

    assert stations_view.helo_dip_contacts(game) == []

    dip_found = Contact(1, 90201, "dipping-passiv", "sub")
    dip_found.update_dip_passive(123.0, game.sim_t, 5.0, 6.0, 1.5)
    game.sonar.contacts[dip_found.target_id] = dip_found
    game.selected_contact = dip_found

    assert stations_view.helo_dip_contacts(game) == [dip_found]
    line = stations_view._helo_dip_contact_line(game)
    assert "K01" in line and "123" in line

    pygame.init()
    surface = pygame.Surface((1280, 720))
    game.screen = surface
    game.station = Station.HELICOPTER
    stations_view.draw_helicopter_view(game)  # must not crash
    game.station_page = 2
    stations_view.draw_helicopter_view(game)


def test_entering_helicopter_station_opens_sonar_console():
    game = Game(seed=909, start_menu=False, audio_enabled=False)
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_8, mod=0))
    assert game.station is Station.HELICOPTER
    assert game.station_page == 2

    game.station = Station.ENGINE
    game.station_page = 1
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB, mod=0))
    assert game.station is Station.HELICOPTER
    assert game.station_page == 2
    pygame.quit()


def test_helicopter_can_select_active_only_dip_echo():
    game = Game(seed=910, start_menu=False, audio_enabled=False)
    game.sonar.contacts.clear()
    contact = Contact(1, 90202, "ping", "sub")
    contact._fx, contact._fy = 5.0, 6.0
    contact.observer_x, contact.observer_y = 5.0, 6.0
    contact.update_ping(90.0, 3.0, 40.0, .8, game.sim_t,
                        fix_source="DIPPING")
    game.sonar.contacts[contact.target_id] = contact
    assert stations_view.helo_dip_contacts(game) == [contact]
    game._cycle_helo_contact(1)
    assert game.selected_contact is contact
    assert "090.0" in stations_view._helo_dip_contact_line(game)
    assert game.qualify_helicopter_contact(contact, True) is True
    assert game.release_sonar_contact(contact, True, source="helicopter") is True
    reports = game.opz_tracks()
    assert len(reports) == 1 and reports[0].source == "SONAR-DIPPING"
    assert reports[0].range_nm == pytest.approx(3.0)
    assert (reports[0].observer_x, reports[0].observer_y) == (5.0, 6.0)


def test_helicopter_station_can_classify_its_own_selected_contact():
    """Feature request: the helicopter must be able to classify a contact
    itself - otherwise it can never launch a torpedo on its own dip find."""
    game = Game(seed=910, start_menu=False, audio_enabled=False)
    game.sonar.contacts.clear()
    game.station = Station.HELICOPTER

    dip_found = Contact(1, 90301, "dipping-passiv", "sub")
    dip_found.update_dip_passive(200.0, game.sim_t, 12.0, 34.0, 1.5)
    game.sonar.contacts[dip_found.target_id] = dip_found

    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_g, mod=0))
    assert game.selected_contact is dip_found

    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_c))
    assert dip_found.player_class == "U_BOOT"

    game.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_g, mod=pygame.KMOD_SHIFT))
    game.roe = "FREE"  # only classification gates a release under FREE ROE
    result = game.launch_helicopter_torpedo_at(dip_found, 90.0)
    assert result != "not_classified"


def test_helicopter_only_contact_reports_its_own_origin_to_opz():
    """A sub only the helicopter's dip has heard must plot from the
    helicopter's own position in OPZ, not a bogus ship-relative bearing."""
    game = Game(seed=911, start_menu=False, audio_enabled=False)
    game.sonar.contacts.clear()
    contact = Contact(1, 90401, "dipping-passiv", "sub")
    origin_x, origin_y = game.ship.x + 5.0, game.ship.y + 2.0
    contact.update_dip_passive(15.0, game.sim_t, origin_x, origin_y, 1.5)
    contact.last_seen = game.sim_t
    contact.dip_released_to_opz = True
    game.sonar.contacts[contact.target_id] = contact

    report = game.opz_tracks()[0]
    assert report.source == "SONAR-DIP-BRG"
    assert report.bearing == pytest.approx(15.0)
    assert report.observer_x == pytest.approx(origin_x)
    assert report.observer_y == pytest.approx(origin_y)

    ppi = pygame.Rect(0, 0, 400, 400)
    start, end = stations_view._opz_bearing_ray(game, report, ppi, 20.0)
    assert (start[0], start[1]) != (ppi.centerx, ppi.centery)
