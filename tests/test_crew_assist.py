"""Crew assist (Shift+F2, on in every lobby round): the AI mans every station
nobody holds, on the frigate and on a crewed boat; the station the uConsole
shows stays with its operator."""

import copy
import json
import sys
from pathlib import Path

import pygame

from src.core import boat_autocrew, hunter, uboot_local
from src.core.autocrew import AUTOCREW_STATIONS
from src.core.game import Game
from src.core.station import Station

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from test_uboot_scope import _local_boat  # noqa: E402


def _game(seed=3901):
    return Game(seed=seed, start_menu=False, audio_enabled=False)


def _key(game, key, mod=0):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod, unicode=""))


def _run(game, seconds, dt=0.25):
    end = game.sim_t + seconds
    while game.sim_t < end - 1e-9 and not game.game_over:
        game._update_sim(dt)


def test_shift_f2_mans_every_station_but_the_one_on_screen():
    game = _game()
    game.station = Station.SONAR
    _key(game, pygame.K_F2, pygame.KMOD_SHIFT)
    assert game.crew_assist and all(game.autocrew.enabled.values())
    assert game.autocrew.status(game, "sonar") == "suspended_local"
    assert game.autocrew.status(game, "radio") == "active"
    # The operator keeps working the station on screen.
    assert not game._local_station_input_locked()
    assert hunter.active(game)
    assert hunter.manned(game, Station.SONAR) and not hunter.manned(game, Station.BRIDGE)
    game.station = Station.BRIDGE
    assert game.autocrew.status(game, "sonar") == "active"
    _key(game, pygame.K_F2, pygame.KMOD_SHIFT)
    assert not game.crew_assist and not any(game.autocrew.enabled.values())


def test_the_assist_is_saved_and_restored():
    game = _game()
    game.toggle_crew_assist()
    state = json.loads(json.dumps(game.save_state()))
    assert state["autocrew"]["assist"] is True
    other = _game()
    assert other._load_save_data(copy.deepcopy(state))
    assert other.crew_assist and set(k for k, v in other.autocrew.enabled.items() if v) \
        == set(AUTOCREW_STATIONS)
    broken = copy.deepcopy(state)
    broken["autocrew"]["assist"] = 1
    assert not other._load_save_data(broken)


def test_the_boat_autocrew_works_only_the_free_boat_stations():
    game, boat = _local_boat(seed=3902)
    uboot_local.set_local_station(game, "uboot_engine")
    sub = boat.sub
    sub.command_trim_auto(False)
    before = (sub.order_course, sub.order_speed, sub.order_depth)
    _run(game, 4.0)
    assert not sub.ballast.auto                    # nobody touches it without the assist
    assert (sub.order_course, sub.order_speed, sub.order_depth) == before
    game.autocrew.set_assist(True, game.sim_t)
    assert boat_autocrew.active(game)
    assert boat_autocrew.held(game, "uboot_engine")
    assert not boat_autocrew.held(game, "uboot")
    _run(game, 4.0)
    assert not sub.ballast.auto                    # the engine room is the uConsole's
    assert (sub.order_course, sub.order_speed, sub.order_depth) != before
    uboot_local.set_local_station(game, "uboot_sonar")
    _run(game, 4.0)
    assert sub.ballast.auto


def test_the_boat_autocrew_is_deterministic():
    def run():
        game, _boat = _local_boat(seed=3903)
        uboot_local.set_local_station(game, "uboot_sonar")
        game.autocrew.set_assist(True, game.sim_t)
        _run(game, 120.0, dt=0.5)
        sub = game.opfor.sub
        return (round(sub.x, 9), round(sub.y, 9), round(sub.depth, 6),
                sub.order_course, sub.order_speed, sub.order_depth, sub.snorkeling)
    assert run() == run()


# --- a person's order wins over the AI of a free station --------------------

def _assisted_boat(station, seed=3902):
    game, boat = _local_boat(seed=seed)
    uboot_local.set_local_station(game, station)
    game.autocrew.set_assist(True, game.sim_t)
    return game, boat


def _at_periscope_depth(game, boat):
    from src.core import opfor
    depth = opfor.depth_presets(game, boat)["periscope"]
    boat.sub.set_orders(depth=depth)
    boat.sub.depth = boat.sub.target_depth = depth
    return depth


def _ping_alarm(game, boat):
    boat.orders.ping_bearing = 90.0
    boat.sub.memory["last_ping_age"] = 0.0


def test_a_mast_a_person_raised_keeps_the_ai_command_at_periscope_depth():
    # The report: the mast raised at another station came straight down again,
    # because the free command dived the boat below periscope depth.
    for station in ("uboot_esm", "uboot_radio"):
        game, boat = _assisted_boat(station)
        depth = _at_periscope_depth(game, boat)
        assert boat.sub.command_mast(True) is True
        _run(game, 30.0)
        assert boat.orders.mast, station
        assert boat.sub.order_depth <= depth + 1e-9
    # Nobody at a mast station: the free command dives as before.
    game, boat = _assisted_boat("uboot_sonar")
    _at_periscope_depth(game, boat)
    boat.sub.command_mast(True)
    _run(game, 30.0)
    assert not boat.orders.mast


def test_the_ai_command_leaves_a_held_helm_and_engine_room_alone():
    game, boat = _assisted_boat("uboot_nav")
    sub = boat.sub
    sub.set_orders(course=123.0, speed=2.0, depth=40.0)
    _ping_alarm(game, boat)                          # no evasion over the helm either
    _run(game, 6.0)
    assert (sub.order_course, sub.order_speed, sub.order_depth) == (123.0, 2.0, 40.0)
    game, boat = _assisted_boat("uboot_engine")
    sub = boat.sub
    sub.set_orders(speed=2.0)
    assert sub.command_silent(True) is True
    _run(game, 6.0)
    assert sub.order_speed == 2.0 and boat.orders.silent


def test_the_ai_mast_station_leaves_a_mast_raised_at_command_up():
    game, boat = _assisted_boat("uboot")
    _at_periscope_depth(game, boat)
    boat.sub.command_mast(True)
    _ping_alarm(game, boat)
    assert boat_autocrew.esm(game, boat) == "monitoring"
    assert boat.orders.mast
    uboot_local.set_local_station(game, "uboot_sonar")
    assert boat_autocrew.esm(game, boat) == "mast_down"


def test_the_ai_engine_room_leaves_trim_and_damage_control_to_a_held_command():
    game, boat = _assisted_boat("uboot")
    sub = boat.sub
    sub.command_trim_auto(False)
    _run(game, 4.0)
    assert not sub.ballast.auto


def test_the_ai_sonar_keeps_the_contact_the_uconsole_picked():
    from types import SimpleNamespace
    game, boat = _assisted_boat("uboot_weapons")
    contacts = boat.station.sonar.contacts
    contacts.clear()
    quiet, loud = (SimpleNamespace(id=n, target_id=-900 - n, snr=snr, last_seen=game.sim_t)
                   for n, snr in ((1, 3.0), (2, 12.0)))
    contacts.update({quiet.target_id: quiet, loud.target_id: loud})
    boat.station.selected_contact = quiet            # Up/Down on the uConsole
    assert boat_autocrew.sonar(game, boat) == "monitoring"
    assert boat.station.selected_contact is quiet
    boat.station.selected_contact = None
    assert boat_autocrew.sonar(game, boat) == "focused"
    assert boat.station.selected_contact is loud


def test_the_ai_bridge_leaves_the_helm_to_a_person_in_the_engine_room():
    game = _game(seed=3905)
    game.station = Station.ENGINE
    game.toggle_crew_assist()
    assert hunter.manned(game, Station.ENGINE) and not hunter.manned(game, Station.BRIDGE)
    assert game.order_course(77.0) == "ok"
    _run(game, 10.0)
    assert game.ship.target_course == 77.0


def test_the_ai_designates_only_when_no_person_picked_another_target():
    from types import SimpleNamespace
    game = _game(seed=3906)
    first = SimpleNamespace(target_id=-901, last_seen=game.sim_t)
    second = SimpleNamespace(target_id=-902, last_seen=game.sim_t)
    game.sonar.contacts[first.target_id] = first
    game.target = first
    game.station = Station.BRIDGE
    game.toggle_crew_assist()
    # Nobody at the designating stations: the AI may designate.
    assert hunter._may_designate(game, second, Station.SONAR, Station.OPZ)
    # A person at the sonar with a live target of their own: hands off.
    game.station = Station.SONAR
    assert not hunter._may_designate(game, second, Station.SONAR, Station.OPZ)
    assert hunter._may_designate(game, first, Station.SONAR, Station.OPZ)
    # Their target lost: the AI may designate again.
    first.last_seen = game.sim_t - 10_000.0
    assert hunter._may_designate(game, second, Station.SONAR, Station.OPZ)


def test_the_ai_sonar_listens_to_the_contact_the_uconsole_selected():
    from src.core.autocrew import AutocrewController
    from src.sonar.sonar import Contact
    game = _game(seed=3907)
    game.sonar.tma_enabled = True
    game.sonar.bt_cooldown = 1e9
    game.sonar.contacts.clear()
    rows = []
    for number, quality in ((1, 0.2), (2, 0.9)):
        contact = Contact(number, 9200 + number, "passiv", "sub")
        contact.bearing, contact.quality, contact.last_seen = 40.0 * number, quality, game.sim_t
        contact.released_to_opz = True
        game.sonar.contacts[contact.target_id] = contact
        rows.append(contact)
    game.station = Station.WEAPONS
    game.toggle_crew_assist()
    game.selected_contact = rows[0]                  # Up/Down at the weapons station
    game.sonar.focus_locked = False
    assert AutocrewController._sonar(game) == "focused"
    assert game.selected_contact is rows[0]
    # Nobody on the uConsole's frigate stations: the loudest wins, as before.
    game.local_side = "uboot"
    game.sonar.focus_locked = False
    assert AutocrewController._sonar(game) == "focused"
    assert game.selected_contact is rows[1]
