"""Wounded crew (save v38): hits and exposure wound people at the stations of
the compartments hit, empty posts slow the station, and both sides decide on
the medical team and on re-manning from the resting watches."""

import copy
import json
import sys
from pathlib import Path

import pygame

from src.commander.server import V2_ACTION_REGISTRY
from src.core import casualties as model
from src.core.casualties import Casualties
from src.core.game import Game
from src.core.station import Station

sys.path.insert(0, str(Path(__file__).parent))
from test_opfor_sub import _crewed  # noqa: E402


def _game(seed=3801):
    return Game(seed=seed, start_menu=False, audio_enabled=False)


def test_roster_wounds_treats_and_reassigns_deterministically():
    roster = Casualties()
    levels = {station: 0.0 for station in model.STATIONS}
    assert roster.update(0.5, 40.0, levels, "sonar") == 3     # a hit: ceil(40/15)
    assert roster.gaps("sonar") == 3 and roster.serious["sonar"] == 1
    assert roster.factor("sonar") == 1.0 - model.GAP_WEIGHT * 3 / 4
    assert roster.update(0.5, 42.0, levels, "sonar") == 0     # slow growth: no hit
    # A full fire in damage control wounds one a minute.
    levels["damage"] = 1.0
    hurt = sum(roster.update(1.0, 42.0, levels, "damage") for _ in range(120))
    assert hurt == 2 and roster.returned == 1    # the medic worked meanwhile
    # The medical team treats the lightly wounded, most first.
    assert roster.medic in model.STATIONS
    light, returned = sum(roster.light.values()), roster.returned
    levels["damage"] = 0.0
    for _ in range(int(model.MEDIC_TREAT_S) + 1):
        roster.update(1.0, 42.0, levels, None)
    assert sum(roster.light.values()) == light - 1 and roster.returned == returned + 1
    # Re-manning fills up to two posts of the worst station, then waits.
    worst = roster.worst()
    before = roster.gaps(worst)
    station, men = roster.reassign(100.0)
    assert station == worst and men == min(2, before)
    assert roster.reassign(101.0) == "reassign_wait"
    assert roster.spare() == model.REASSIGN_POOL - men
    state = roster.serialize()
    assert Casualties.valid_state(json.loads(json.dumps(state)))
    assert Casualties.restore(state).serialize() == state
    for bad in (dict(state, version=2), dict(state, wounded=-1),
                dict(state, light=dict(state["light"], sonar=9)),
                dict(state, medic="bridge"), dict(state, reassigned=model.REASSIGN_POOL + 1)):
        assert not Casualties.valid_state(bad)


def test_a_torpedo_hit_wounds_the_frigate_and_slows_its_stations():
    game = _game()
    game.casualties_hit(game.damage.torpedo_hit(impact=(0.55, 0.0)))
    game._update_crew(0.5)
    roster = game.casualties
    assert roster.wounded > 0
    assert any(roster.gaps(station) for station in model.STATIONS)
    game._apply_crew_effects()
    worst = roster.worst()
    assert game.casualty_factor(worst) < 1.0
    state = json.loads(json.dumps(game.save_state()))
    twin = Game(seed=1, start_menu=False, audio_enabled=False)
    assert twin._load_save_data(copy.deepcopy(state))
    assert twin.casualties.serialize() == roster.serialize()
    broken = copy.deepcopy(state)
    broken["casualties"]["subs"] = [dict(id=999_999, roster=Casualties().serialize())]
    assert not twin._load_save_data(broken)


def test_frigate_keys_order_the_medic_and_re_man():
    game = _game()
    game.casualties.wound("weapons")
    game.casualties.wound("weapons")
    game.station, game.station_page = Station.DAMAGE, 2
    rested = [game.crew_watch.fatigue[i] for i in range(3) if i != game.crew_watch.on_watch]
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_u, mod=0, unicode="u"))
    assert game.casualties.gaps("weapons") == 0
    after = [game.crew_watch.fatigue[i] for i in range(3) if i != game.crew_watch.on_watch]
    assert all(b > a for a, b in zip(rested, after))
    game.casualties.wound("sonar")                   # the third wound is serious
    game.casualties.wound("sonar")
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_m, mod=0, unicode="m"))
    assert game.casualties.medic_order == "sonar"
    assert V2_ACTION_REGISTRY["crew_casualty_reassign"].stations == frozenset({"damage"})
    assert "uboot_engine" in V2_ACTION_REGISTRY["uboot_casualty_medic"].stations


def test_submarines_have_rosters_too_and_ai_boats_re_man():
    game = _game(3802)
    sub = game.subs[0]
    game._update_crew(0.5)
    sub.damage += 40.0
    game._update_crew(0.5)
    roster = game.sub_casualties[sub.id]
    assert roster.wounded == 3
    # An AI boat re-mans a station with two empty posts on its own.
    assert roster.reassigned > 0 or all(roster.gaps(s) < 2 for s in model.STATIONS)
    roster.light["weapons"] = 2
    game._apply_crew_effects()
    assert sub.weapons_crew_factor < 1.0
    assert sub.crew_efficiency() <= sub.weapons_crew_factor + 1e-9


def test_the_crewed_boat_is_told_and_decides():
    game, _server, _bridge = _crewed(seed=78)
    boat = game.opfor
    game._update_crew(0.5)
    boat.sub.damage += 20.0
    game._update_crew(0.5)
    events = [values for key, values in boat.orders.drain_events() if key == "wounded"]
    assert events and events[-1]["count"] == "2"
    roster = game.sub_roster(boat.sub)
    assert roster.wounded == 2 and roster.reassigned == 0     # the crew decides
    assert game.boat_casualty_reassign() is True
    assert roster.reassigned > 0
    assert game.boat_casualty_medic() is True
