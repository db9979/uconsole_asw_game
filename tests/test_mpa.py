"""The on-call maritime patrol aircraft (OPZ page 3; save v21)."""

import copy
import json
import math

import pygame
import pytest

from src.air.mpa import PatrolAircraft
from src.core import config
from src.core.game import Game
from src.core.station import Station


def _game(seed=5):
    game = Game(seed=seed, start_menu=False, audio_enabled=False)
    game.tasking.next_offer_t = 1e9
    return game


def _fly(game, seconds, dt=0.5):
    for _ in range(int(seconds / dt)):
        game.update(dt)


def _overhead(game, dx=0.0, dy=0.0):
    """Launch and put the aircraft on station over a point near the ship."""
    assert game.request_mpa() is True
    mpa = game.mpa
    mpa.x, mpa.y = game.ship.x + dx, game.ship.y + dy
    mpa.set_waypoint(mpa.x, mpa.y)
    return mpa


def _key(game, key, mod=0):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod, unicode=""))


def test_request_flies_to_the_ship_and_orbits():
    game = _game()
    mpa = game.mpa
    assert mpa.state == "BASE" and mpa.available(game.sim_t)
    assert game.request_mpa() is True and mpa.state == "TRANSIT"
    assert game.request_mpa() == "not_ready"
    mpa.x, mpa.y = game.ship.x + 10.0, game.ship.y
    _fly(game, 240.0)
    assert mpa.state == "STATION"
    _fly(game, 600.0)
    distance = math.hypot(mpa.x - mpa.waypoint_x, mpa.y - mpa.waypoint_y)
    assert distance < config.MPA_ORBIT_NM + 1.5


def test_bingo_landing_turnaround_and_sortie_limit():
    aircraft = PatrolAircraft(0.0, 0.0)
    assert aircraft.launch(50.0, 0.0, 0.0)
    aircraft.x = 40.0
    aircraft.fuel_s = aircraft.bingo_s() + 1.0
    events = [aircraft.update(1.0, 10.0) for _ in range(5)]
    assert "bingo" in events and aircraft.state == "RTB"
    t = 10.0
    while aircraft.state != "BASE":
        t += 1.0
        aircraft.update(1.0, t)
    assert aircraft.sorties == 1 and aircraft.buoys_left == config.MPA_BUOYS
    assert not aircraft.available(t)
    assert aircraft.available(t + config.MPA_TURNAROUND_S)
    aircraft.sorties = config.MPA_SORTIES
    assert aircraft.ready_in_s(t + config.MPA_TURNAROUND_S) is None


def test_buoys_are_heard_only_while_relayed():
    game = _game()
    mpa = _overhead(game, 20.0, 0.0)
    assert game.mpa_drop_buoy() is True
    buoy = game.buoys[-1]
    assert buoy.owner == "MPA" and buoy in game.heard_buoys()
    mpa.x += config.MPA_RELAY_NM + 5.0
    assert buoy not in game.heard_buoys()
    mpa.state = "BASE"
    assert buoy not in game.heard_buoys() and game.mpa_view()["x"] is None


def test_pattern_drops_along_the_planned_points():
    game = _game()
    mpa = _overhead(game, 15.0, 0.0)
    assert game.set_mpa_pattern("barrier") is True
    planned = len(mpa.pattern_queue)
    assert planned >= 2
    before = mpa.buoys_left
    _fly(game, 900.0)
    assert mpa.pattern == "single" and not mpa.pattern_queue
    assert before - mpa.buoys_left == planned
    assert game.set_mpa_pattern("spiral") == "invalid_value"


def test_radar_reports_as_datalink_tracks():
    game = _game()
    ship = next(ship for ship in game.civilians if not ship.sunk)
    mpa = _overhead(game)
    mpa.x, mpa.y = ship.x + 5.0, ship.y
    game.mpa.set_waypoint(mpa.x, mpa.y)
    _fly(game, 20.0)
    tracks = [track for track in game.air_picture.tracks(game.sim_t) if track.source == "RADAR-MPA"]
    assert tracks
    game.set_mpa_radar(False)
    assert game.mpa.radar_on is False


def test_attack_needs_a_designated_submarine_and_the_datum():
    game = _game()
    _overhead(game, 5.0, 0.0)
    assert game.mpa_attack() == "invalid_target"
    assert game.set_mpa_radar("yes") == "invalid_value"
    assert game.set_mpa_waypoint(float("nan"), 1.0) == "invalid_value"


def test_opz_page_three_keys():
    game = _game()
    game.station, game.station_page = Station.OPZ, 2
    # The helicopter's keys: H, X / Shift+X, Shift+B, Ctrl+R.
    _key(game, pygame.K_h)
    assert game.mpa.state == "TRANSIT"
    _key(game, pygame.K_x)
    assert game.mpa.pattern == "field"
    _key(game, pygame.K_x, pygame.KMOD_SHIFT)
    assert game.mpa.pattern == "single"
    _key(game, pygame.K_b, pygame.KMOD_SHIFT)
    assert game.mpa.buoy_mode == "ACTIVE"
    _key(game, pygame.K_r, pygame.KMOD_CTRL)
    assert game.mpa.radar_on is False
    radars = (game.surface_radar_on, game.air_radar_on)
    game.draw()
    _key(game, pygame.K_h)
    assert game.mpa.state == "RTB"
    assert (game.surface_radar_on, game.air_radar_on) == radars
    game.station_page = 0
    _key(game, pygame.K_b, pygame.KMOD_SHIFT)
    assert game.mpa.buoy_mode == "ACTIVE"          # page 1 keeps its own keys


def test_save_load_continues_the_sortie_identically():
    game = _game()
    _overhead(game, 12.0, 4.0)
    game.set_mpa_pattern("circle")
    _fly(game, 120.0)
    document = json.loads(json.dumps(game.save_state()))
    other = _game()
    assert other._load_save_data(document)
    for runner in (game, other):
        _fly(runner, 300.0)
    assert game.mpa.serialize() == other.mpa.serialize()
    assert ([b.seq for b in game.buoys], [b.owner for b in game.buoys]) == (
        [b.seq for b in other.buoys], [b.owner for b in other.buoys])
    for mutate in (lambda doc: doc.pop("mpa"),
                   lambda doc: doc["mpa"].update(state="HOVER"),
                   lambda doc: doc["mpa"].update(buoys_left=99),
                   lambda doc: doc["buoys"][0].update(owner="SHIP"),
                   lambda doc: doc["buoys"][0].pop("owner")):
        broken = copy.deepcopy(document)
        mutate(broken)
        assert not other._load_save_data(broken)


def test_remote_crew_projection_and_actions():
    from src.commander.projections import _mpa
    game = _game()
    payload = _mpa(game)
    assert payload["state"] == "BASE" and payload["x"] is None
    assert json.loads(json.dumps(payload)) == payload
    from src.commander.v2.commands import V2_ACTION_REGISTRY
    assert V2_ACTION_REGISTRY["mpa_attack"].direct_fire is True
    for action in ("mpa_request", "mpa_return", "mpa_set_waypoint", "mpa_set_pattern",
                   "mpa_drop_buoy", "mpa_set_buoy_mode", "mpa_set_radar", "mpa_attack"):
        assert V2_ACTION_REGISTRY[action].stations == frozenset({"opz"})
