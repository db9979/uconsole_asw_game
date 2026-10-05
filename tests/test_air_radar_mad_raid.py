"""1.3.76: the helicopter radar switch and the AI boats' answer to aircraft
radars, the patrol aircraft's MAD passes and patrol boats that torpedo
merchants in the frigate missions (save v32)."""

import json
import math
from types import SimpleNamespace

import pygame
import pytest

from src.commander.actions import _V2_ACTION_HANDLERS as STATION_ACTION_HANDLERS
from src.commander.v2.commands import V2_ACTION_REGISTRY as V2_ACTIONS
from src.core import boat_ai, boat_esm, boat_missions, config
from src.core.game import Game
from src.core.station import Station
from src.world.world import World


@pytest.fixture(autouse=True)
def calm_sea(monkeypatch):
    monkeypatch.setattr(World, "effective_sea_state", property(lambda self: 1.0))
    monkeypatch.setattr(Game, "radar_rain_severity", lambda self: 0.0)


def _game(seed=7601):
    game = Game(seed=seed, start_menu=False, audio_enabled=False, language="en")
    game.tasking.next_offer_t = 1e9
    return game


def _airborne(game, x, y):
    helo = game.helo
    helo.state = "AUF"
    helo.x, helo.y = x, y
    helo.dip_state = "STOWED"
    return helo


def _key(game, key, mod=0):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod, unicode=""))


def _alert(game, seconds=60.0, dt=0.5):
    for _ in range(int(seconds / dt)):
        game.sim_t += dt
        game._update_sub_radar_alert(dt)


def _snorkeling_boat(game):
    sub = next(boat for boat in game.subs if boat.endurance is not None)
    for other in game.subs:
        if other is not sub:
            other.sunk = True
    sub.depth = sub.endurance.profile.snorkel_depth_m
    sub.endurance.phase = "SNORKEL"
    return sub


# --- helicopter radar switch -------------------------------------------------

def test_the_helicopter_radar_switch_silences_radar_and_esm():
    game = _game()
    helo = _airborne(game, game.ship.x + 5.0, game.ship.y)
    assert game.helo_radar_active()
    game.station = Station.HELICOPTER
    _key(game, pygame.K_r, pygame.KMOD_CTRL)       # Ctrl+R: the aircraft radar
    assert helo.radar_on is False and not game.helo_radar_active()
    assert not [signal for signal, _height in boat_esm.own_asset_emissions(game)
                if abs(_height - config.HELO_RADAR_ALTITUDE_M) < 1e-9]
    assert game.set_helicopter_radar("on") == "invalid_value"
    assert game.set_helicopter_radar(True) is True and game.helo_radar_active()
    # Saved (v32) and restored.
    game.set_helicopter_radar(False)
    other = _game()
    assert other._load_save_data(json.loads(json.dumps(game.save_state())))
    assert other.helo.radar_on is False


def test_remote_crew_can_switch_helicopter_radar_and_mad_passes():
    for name, role in (("helicopter_set_radar", "helicopter"), ("mpa_set_mad", "opz")):
        assert name in STATION_ACTION_HANDLERS and role in V2_ACTIONS[name].stations
        assert V2_ACTIONS[name].validate_params({"enabled": True})
        assert not V2_ACTIONS[name].validate_params({"enabled": 1})
    game = _game()
    _airborne(game, game.ship.x + 5.0, game.ship.y)
    assert STATION_ACTION_HANDLERS["helicopter_set_radar"](game, {"enabled": False}, {}) is True
    assert game.helo.radar_on is False


# --- AI boats answer aircraft radars -----------------------------------------

def test_a_snorkeling_ai_boat_goes_deep_on_an_aircraft_radar_and_stays_down():
    game = _game()
    sub = _snorkeling_boat(game)
    _airborne(game, sub.x + 6.0, sub.y)
    _alert(game)
    assert sub.radar_hold_s == pytest.approx(config.SUB_RADAR_HOLD_S, abs=60.0)
    assert sub.endurance.phase == "DESCENDING"
    assert sub.endurance.return_depth_m == pytest.approx(
        sub.endurance.profile.snorkel_depth_m + config.SUB_RADAR_DIVE_M)
    # Held: a low battery does not start a new ascent while the hold runs.
    endurance = sub.endurance
    endurance.phase = "SUBMERGED"
    endurance.battery_kwh = (endurance.profile.battery_capacity_kwh
                             * endurance.profile.reserve_start_fraction * 0.9)
    endurance.hold_ascent = True
    endurance._start_reserve_cycle(60.0)
    assert endurance.phase in ("SUBMERGED", "AIP")
    endurance.hold_ascent = False
    endurance._start_reserve_cycle(60.0)
    assert endurance.phase in ("ASCENDING", "AIP")
    # Saved (v32) and restored.
    other = _game()
    assert other._load_save_data(json.loads(json.dumps(game.save_state())))
    assert next(boat for boat in other.subs if boat.id == sub.id).radar_hold_s == sub.radar_hold_s


def test_a_silent_helicopter_or_a_deep_boat_raises_no_alarm():
    game = _game(7602)
    sub = _snorkeling_boat(game)
    _airborne(game, sub.x + 6.0, sub.y)
    game.set_helicopter_radar(False)
    _alert(game)
    assert sub.radar_hold_s == 0.0 and sub.endurance.phase == "SNORKEL"
    game.set_helicopter_radar(True)
    sub.endurance.phase = "SUBMERGED"
    sub.depth = 120.0
    _alert(game)
    assert sub.radar_hold_s == 0.0


# --- patrol aircraft MAD passes -----------------------------------------------

def _on_station(game, x, y):
    assert game.request_mpa() is True
    mpa = game.mpa
    mpa.x, mpa.y = x + 2.5, y
    mpa.set_waypoint(x, y)
    mpa.state = "STATION"
    return mpa


def test_mad_passes_fly_over_the_waypoint_and_find_a_boat_under_it():
    game = _game(7603)
    sub = game.subs[0]
    for other in game.subs[1:]:
        other.sunk = True
    sub.depth = 60.0
    sub.speed = sub.target_speed = 0.0 if hasattr(sub, "target_speed") else 0.0
    mpa = _on_station(game, sub.x, sub.y)
    assert game.set_mpa_mad(True) is True and mpa.mad_run
    assert mpa.altitude_m == config.MPA_MAD_ALTITUDE_M and mpa.speed_kn == config.MPA_MAD_KN
    closest = math.inf
    found = False
    for _ in range(int(900 / 0.5)):
        game.sim_t += 0.5
        mpa.set_waypoint(sub.x, sub.y)
        mpa.update(0.5, game.sim_t)
        closest = min(closest, math.hypot(mpa.x - sub.x, mpa.y - sub.y))
        game._update_mpa_mad(0.5)
        contact = next((c for c in game.sonar.contacts.values()
                        if getattr(c, "target_id", None) == sub.id
                        or getattr(c, "entity_id", None) == sub.id), None)
        if contact is not None and contact.fixes.get("MAD") is not None:
            found = True
            break
    assert closest < 0.2
    assert found


def test_mad_passes_need_an_airborne_aircraft_and_are_saved():
    game = _game(7604)
    assert game.set_mpa_mad(True) == "not_airborne"
    mpa = _on_station(game, game.ship.x + 10.0, game.ship.y)
    game.station = Station.OPZ
    game.station_page = 2
    _key(game, pygame.K_m, pygame.KMOD_SHIFT)      # Shift+M, as the helicopter's MAD
    assert mpa.mad_mode is True
    assert game.mpa_view()["mad"] is True
    other = _game(7604)
    assert other._load_save_data(json.loads(json.dumps(game.save_state())))
    assert other.mpa.mad_mode is True
    mpa.order_return()
    assert mpa.mad_mode is False


# --- patrol boats torpedo merchants -----------------------------------------

def test_a_patrol_boat_torpedoes_a_merchant_far_from_the_frigate(monkeypatch):
    monkeypatch.setattr(config, "SUB_RAID_P", 1.0)
    game = _game(7605)
    assert boat_missions.mode(game) is None
    sub = next(boat for boat in game.subs if boat.side == "hostile")
    for other in game.subs:
        if other is not sub:
            other.sunk = True
    merchant = game.civilians[0]
    merchant.x, merchant.y = sub.x + 2.0 * math.sin(math.radians(sub.course)), \
        sub.y - 2.0 * math.cos(math.radians(sub.course))
    game.ship.x, game.ship.y = sub.x + 30.0, sub.y + 30.0
    sub.memory["last_ping_age"] = sub.memory["last_torpedo_age"] = float("inf")
    assert sub in boat_ai.patrol_raiders(game)
    before = sub.torpedoes_left
    fired = flooded = False
    for _ in range(int(260 / 2.0)):
        game.sim_t += 2.0
        # The tubes flood with the boat's own clock (quietly, before the shot).
        if sub.ai_tube_left > 0.0:
            flooded = True
            sub.ai_tube_left = max(0.0, sub.ai_tube_left - 2.0)
        if boat_ai.patrol_attack(game, sub):
            fired = True
            break
    assert flooded and sub.flood_quiet
    assert fired and (sub.torpedoes_left < before or sub.pending_torpedoes)
    assert sub.ai_tube_left == -1.0 and not sub.ai_fire_pending


def test_raids_stay_out_of_boat_missions_and_hunted_boats(monkeypatch):
    monkeypatch.setattr(config, "SUB_RAID_P", 1.0)
    game = _game(7606)
    sub = next(boat for boat in game.subs if boat.side == "hostile")
    sub.memory["last_ping_age"] = 30.0
    game.ship.x, game.ship.y = sub.x + 30.0, sub.y + 30.0
    game.civilians[0].x, game.civilians[0].y = sub.x + 1.0, sub.y
    for _ in range(40):
        game.sim_t += 2.0
        assert not boat_ai.patrol_attack(game, sub)
    game.training = object()
    assert boat_ai.patrol_raiders(game) == []


def test_a_merchant_lost_in_a_frigate_mission_costs_score():
    game = _game(7607)
    sub = next(boat for boat in game.subs if boat.side == "hostile")
    merchant = game.civilians[0]
    score = game.score
    # The frigate's sonar heard the attacker lately: it could have stopped it.
    game.sonar.contacts[sub.id] = SimpleNamespace(last_seen=game.sim_t - 60.0)
    boat_missions.merchant_struck(game, merchant, sub.id)
    assert merchant.sunk
    assert game.score == score - config.SCORE_MERCHANT_LOST


def test_a_merchant_lost_to_an_unheard_boat_is_a_distress_call_without_penalty():
    game = _game(7607)
    sub = next(boat for boat in game.subs if boat.side == "hostile")
    game.sonar.contacts.pop(sub.id, None)
    merchant = game.civilians[0]
    merchant.x, merchant.y = game.ship.x + 10.4, game.ship.y + 0.3
    score = game.score
    boat_missions.merchant_struck(game, merchant, sub.id)
    assert merchant.sunk and game.score == score
    calls = [entry.text for entry in game.feed.entries if isinstance(entry.text, dict)
             and entry.text.get("__u_jagd_i18n__", "").startswith("runtime.merchant")]
    assert calls == [{"__u_jagd_i18n__": "runtime.merchant_distress",
                      "params": {"bearing": "090", "range": "10"}}]
    # Heard too long ago counts as not held either.
    other = game.civilians[1]
    game.sonar.contacts[sub.id] = SimpleNamespace(
        last_seen=game.sim_t - config.MERCHANT_BLAME_S - 1.0)
    boat_missions.merchant_struck(game, other, sub.id)
    assert other.sunk and game.score == score
