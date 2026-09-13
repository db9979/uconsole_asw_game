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
    assert contact.passive_source == "SONAR-DIP-BRG"
    assert (contact.observer_x, contact.observer_y) == (helo.x, helo.y)
    assert contact.range_est is None
    assert contact.raw_bearing == second.contacts[target.id].raw_bearing
    assert abs(config.angle_diff_deg(contact.raw_bearing, 90.0)) \
        <= config.HELO_DIP_BEARING_ERR_DEG


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
    contact.update_passive(0.0, .8, .8, "hidden", game.sim_t)
    contact.passive_source = "SONAR-DIP-BRG"
    contact.observer_x, contact.observer_y = game.ship.x + 5.0, game.ship.y
    contact.released_to_opz = True
    game.sonar.contacts[contact.target_id] = contact
    report = game.opz_tracks()[0]
    ppi = pygame.Rect(0, 0, 400, 400)

    start, end = stations_view._opz_bearing_ray(game, report, ppi, 20.0)

    assert start[0] > ppi.centerx
    assert start[1] == pytest.approx(ppi.centery)
    assert end[1] < start[1]


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
        for key in ("released_to_opz", "passive_source", "observer_x", "observer_y"):
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

    state = json.loads(json.dumps(game.save_state(), allow_nan=False))
    restored = Game(seed=905, start_menu=False, audio_enabled=False)
    restored.load_state(state)

    assert restored.helo.dip_state == "DEPLOYED"
    assert restored.helo.dip_depth_m == 50.0
    assert restored.helo.dip_ping_cooldown == 12.0
    assert restored.sonar.contacts[target.id].released_to_opz
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
