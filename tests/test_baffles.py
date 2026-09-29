"""Baffles: hull sonars are deaf astern on both sides, clearing them is a
short turn for the frigate and the crewed submarine, and an AI boat that
finds itself in the hunter's baffles trails it there."""

import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pygame

from src.commander.server import V2_ACTION_REGISTRY
from src.core import baffles, config, opfor
from src.core.game import Game
from src.data.catalog import CATALOG
from src.sensors.platform import PlatformSensorSuite, PlatformObservation
from src.sonar.sonar import TowState

sys.path.insert(0, str(Path(__file__).parent))
from test_opfor_sub import _crewed  # noqa: E402


def _game(seed=8101):
    return Game(seed=seed, start_menu=False, audio_enabled=False)


def test_baffle_geometry():
    assert baffles.in_baffles(0.0, 180.0)
    assert baffles.in_baffles(0.0, 155.0) and baffles.in_baffles(0.0, 205.0)
    assert not baffles.in_baffles(0.0, 145.0) and not baffles.in_baffles(0.0, 90.0)
    assert baffles.in_baffles(350.0, 175.0)
    state = baffles.start(350.0, 100.0)
    assert state == [350.0, 50.0, 100.0 + config.BAFFLE_CLEAR_HOLD_S]
    assert baffles.step(state, 50.0, 150.0) == (state, None)
    assert baffles.step(state, 50.0, state[2]) == (None, 350.0)
    assert baffles.step(state, 120.0, 150.0) == (None, None)     # another order
    assert baffles.valid_state(None) and baffles.valid_state(state)
    for bad in ([1, 2], [360.0, 0.0, 1.0], [0.0, 0.0, float("nan")], "x", [True, 0, 0]):
        assert not baffles.valid_state(bad)


def _hull_contacts(game, bearing_from_ship):
    """Contacts of the frigate's hull array alone on a loud boat 3 NM off."""
    ship, sub = game.ship, game.subs[0]
    ship.x, ship.y = next((x, y) for x in range(50, 450, 10) for y in range(50, 450, 10)
                          if min(game.world.depth_m(x + dx, y + dy) for dx, dy in
                                 ((0, 0), (4, 0), (0, 4), (-4, 0), (0, -4))) > 800.0)
    ship.course = ship.target_course = 0.0
    ship.speed = ship.target_speed = 5.0
    import math
    rad = math.radians(bearing_from_ship)
    sub.x, sub.y = ship.x + 3.0 * math.sin(rad), ship.y - 3.0 * math.cos(rad)
    sub.depth = 20.0
    sub.speed = 12.0
    sonar = game.sonar
    sonar.tow_state = TowState.STOWED
    sonar.tow_payout = 0.0
    sonar.contacts.clear()
    for step in range(12):
        sonar.update(0.5, 1.0 + step * 0.5, ship, [sub], game.world, mode="BOW")
    return [contact for contact in sonar.contacts.values() if contact.target_id == sub.id]


def test_the_frigate_hull_sonar_is_deaf_in_its_baffles():
    game = _game()
    assert _hull_contacts(game, 90.0), "abeam the boat is heard"
    game = _game()
    assert not _hull_contacts(game, 180.0), "astern the hull array hears nothing"


def test_ai_passive_sonars_are_deaf_astern_too():
    def heard(owner_course):
        suite = PlatformSensorSuite(CATALOG, "sub_03", 3, side="hostile",
                                    doctrine="submarine")
        sonar = next(controller for controller in suite.controllers.values()
                     if controller.domain == "sonar")
        for controller in suite.controllers.values():
            controller.enabled = controller is sonar
            controller.next_scan_s = 0.0
        owner = SimpleNamespace(id=1, x=0.0, y=0.0, depth=40.0, active=True, sunk=False,
                                sensor_domain="subsurface", course=owner_course)
        candidate = SimpleNamespace(id=2, x=4.0, y=0.0, depth=5.0, active=True,
                                    sunk=False, sensor_domain="surface",
                                    noise_level=lambda: .9)
        world = SimpleNamespace(
            sea_state=1, depth_m=lambda *_args: 500.0,
            thermocline_depth_m=lambda *_args: 80.0,
            land_blocks_line=lambda *_args: False,
            sonar_path_blocked=lambda *_args: False)
        for t in (0.0, 1.0, 2.0):
            suite.update(t, owner, [candidate], world, CATALOG)
        return bool(suite.tactical_tracks(2.0))
    assert heard(90.0)            # the ship is dead ahead
    assert not heard(270.0)       # the ship is dead astern


def test_the_bridge_clears_its_baffles_and_comes_back():
    game = _game()
    game.ship.target_course = 10.0
    assert game.clear_baffles() == "ok"
    assert game.ship.target_course == 70.0
    assert game.baffle_clear == [10.0, 70.0, game.sim_t + config.BAFFLE_CLEAR_HOLD_S]
    state = json.loads(json.dumps(game.save_state()))
    twin = _game(1)
    assert twin._load_save_data(copy.deepcopy(state))
    assert twin.baffle_clear == game.baffle_clear
    broken = copy.deepcopy(state)
    broken["baffle_clear"] = [10.0, 70.0]
    assert not twin._load_save_data(broken)
    game.sim_t = game.baffle_clear[2]
    game._steer_baffle_clear()
    assert game.baffle_clear is None and game.ship.target_course == 10.0
    # A helm order in between ends the clearing where it is.
    assert game.clear_baffles() == "ok"
    assert game.order_course(200.0) == "ok"
    game._steer_baffle_clear()
    assert game.baffle_clear is None and game.ship.target_course == 200.0


def test_bridge_key_and_remote_action_clear_baffles():
    game = _game()
    game.station = game.station.__class__.BRIDGE
    game.ship.target_course = 0.0
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_b,
                                         mod=pygame.KMOD_CTRL, unicode="b"))
    assert game.baffle_clear is not None
    assert V2_ACTION_REGISTRY["bridge_clear_baffles"].stations == frozenset({"bridge"})
    assert V2_ACTION_REGISTRY["bridge_clear_baffles"].validate_params({})
    assert "uboot_nav" in V2_ACTION_REGISTRY["uboot_clear_baffles"].stations


def test_the_crewed_boat_clears_its_baffles():
    game, _server, _bridge = _crewed(seed=78)
    boat = game.opfor
    boat.sub.order_course = 100.0
    assert opfor.clear_baffles(game, boat) is True
    assert boat.sub.order_course == 160.0
    saved = boat.orders.to_save()
    assert saved["baffle_clear"] == [100.0, 160.0, game.sim_t + config.BAFFLE_CLEAR_HOLD_S]
    state = json.loads(json.dumps(game.save_state()))
    assert game._load_save_data(copy.deepcopy(state))
    boat = game.opfor
    assert boat.orders.baffle_clear is not None
    game.sim_t = boat.orders.baffle_clear[2]
    opfor.update_crew(game, boat)
    assert boat.orders.baffle_clear is None and boat.sub.order_course == 100.0


def test_an_ai_boat_in_the_hunters_baffles_trails_it():
    game = _game()
    sub = game.subs[0]
    ship = game.ship

    def observation(x, y, course=0.0, speed=12.0):
        return PlatformObservation(
            track_id="T", domain="sonar", source="SONAR", observer_x=sub.x,
            observer_y=sub.y, bearing=0.0, range_nm=((x - sub.x) ** 2 + (y - sub.y) ** 2) ** .5,
            x=x, y=y, course=course, speed_kn=speed, depth_m=5.0, quality=1.0,
            signal=1.0, last_seen=0.0, bearing_uncertainty_deg=None,
            range_uncertainty_nm=None, depth_uncertainty_m=None, label=None,
            fix_source="TMA")
    sub.x, sub.y = ship.x, ship.y + 2.0          # 2 NM south, the hunter heads north
    assert sub._baffle_trail(observation(ship.x, ship.y)) == 0.0
    assert sub._baffle_trail(observation(ship.x, ship.y, course=90.0)) is None
    sub.memory["last_torpedo_age"] = 0.0          # a torpedo after it: run instead
    assert sub._baffle_trail(observation(ship.x, ship.y)) is None
