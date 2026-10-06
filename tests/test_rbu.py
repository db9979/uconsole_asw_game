"""The frigate's ASW rocket launcher (Weapons station, save v37): attack
salvoes need a fresh range fix, defence salvoes a fresh torpedo warning; the
splashes warn every submarine near enough, the crewed boat with a bearing."""

import copy
import json
import sys
from pathlib import Path

import pygame

from src.commander.server import V2_ACTION_REGISTRY
from src.core.game import Game
from src.core.station import Station
from src.sonar.sonar import Contact
from src.weapons import rbu
from src.weapons.rbu import RbuRound
from src.weapons.torpedo import EnemyTorpedo

sys.path.insert(0, str(Path(__file__).parent))
from test_opfor_sub import _crewed  # noqa: E402


def _game(seed=3701):
    game = Game(seed=seed, start_menu=False, audio_enabled=False)
    game.world.physical_depth_m = lambda x, y: 1000.0
    game.world.sonar_path_blocked = lambda *args: False
    return game


def _target(game, range_nm=1.5, player_class="U_BOOT"):
    sub = game.subs[0]
    contact = Contact(71, sub.id, "ping", "sub")
    contact.update_ping(90, range_nm, sub.depth, 1, game.sim_t)
    contact.observed_x, contact.observed_y = game.ship.x + range_nm, game.ship.y
    contact.player_class = player_class
    game.sonar.contacts[sub.id] = contact
    game.target = contact
    return contact


def _roundtrip(game):
    state = json.loads(json.dumps(game.save_state()))
    other = Game(seed=1, start_menu=False, audio_enabled=False)
    assert other._load_save_data(copy.deepcopy(state))
    return state, other


def test_patterns_and_damage():
    points = rbu.attack_points(10.0, 10.0)
    assert len(points) == rbu.SALVO and points[0] == (10.0, 10.0)
    ring = [((x - 10.0) ** 2 + (y - 10.0) ** 2) ** .5 * 1852.0 for x, y in points[1:]]
    assert all(abs(value - rbu.ATTACK_RING_M) < 1e-6 for value in ring)
    line = rbu.defence_points(0.0, 0.0, 90.0)
    assert [round(x, 2) for x, _y in line] == list(rbu.DEFENCE_RANGES_NM)
    assert rbu.damage(10.0) == 100.0
    assert 0.0 < rbu.damage(50.0) < 40.0 and rbu.damage(61.0) == 0.0
    assert abs(rbu.flight_s(1.0) - 9.0) < 1e-9


def test_attack_salvo_needs_a_fixed_classified_target_in_range():
    game = _game()
    _target(game, 5.0)
    assert game.fire_rbu() == "out_of_range"
    _target(game, 1.5, player_class=None)
    assert game.fire_rbu() == "not_classified"
    contact = _target(game, 1.5)
    contact.range_est = None
    assert game.fire_rbu() == "not_located"
    _target(game, 1.5)
    game.torpedo_depth = 80
    assert game.fire_rbu() == "ok"
    assert game.rbu_rockets == rbu.STOCK - rbu.SALVO
    assert len(game.rbu_rounds) == rbu.SALVO
    assert {item.set_depth for item in game.rbu_rounds} == {80.0}
    assert game.fire_rbu() == "rbu_reloading"
    game.rbu_reload_s = 0.0
    game.rbu_rockets = 0
    assert game.fire_rbu() == "rbu_empty"


def test_rounds_fly_sink_detonate_and_survive_save_load():
    game = _game(3702)
    _target(game, 1.5)
    game.torpedo_depth = 60
    assert game.fire_rbu() == "ok"
    game._update_rbu(5.0)
    state, other = _roundtrip(game)
    assert [item.serialize() for item in other.rbu_rounds] == state["rbu"]["rounds"]
    assert other.rbu_rockets == game.rbu_rockets
    game._update_rbu(10.0)                     # 13.5 s of flight: in the water
    assert all(not item.flying for item in game.rbu_rounds)
    game._update_rbu(10.0)                     # 110 m of sinking: gone off
    assert not game.rbu_rounds
    for bad in (lambda s: s["rbu"].__setitem__("rockets", rbu.STOCK + 1),
                lambda s: s["rbu"].__setitem__("version", 2),
                lambda s: s["rbu"].__setitem__("reload_s", -1.0)):
        broken = copy.deepcopy(state)
        bad(broken)
        assert not other._load_save_data(broken)
    broken = copy.deepcopy(state)
    broken["rbu"]["rounds"][0]["mode"] = "nuke"
    assert not other._load_save_data(broken)


def test_a_round_close_to_the_boat_damages_it_and_splashes_warn_ai_boats():
    game = _game(3703)
    sub = game.subs[0]
    sub.x, sub.y, sub.depth = game.ship.x + 1.0, game.ship.y, 60.0
    hp = getattr(sub, "damage", 0.0)
    game.rbu_seq = 1
    game.rbu_rockets -= 1
    game.rbu_rounds = [RbuRound(1, sub.x, sub.y + 0.005, 60.0, 0.05, True, "attack")]
    game._update_rbu(0.1)                      # splash: the AI boat hears it
    assert sub.torpedo_alarm_left >= 0.0 or sub.state == "EVADE"
    game._update_rbu(10.0)
    assert not game.rbu_rounds
    assert sub.sunk or sub.state == "SINKING" or getattr(sub, "damage", 0.0) > hp


def test_defence_salvo_follows_the_torpedo_warning_and_kills_a_torpedo():
    game = _game(3704)
    assert game.fire_rbu_defence() == "rbu_no_warning"
    game.torpedo_cues = [dict(serial=1, kind="hull", bearing=90.0, t=game.sim_t)]
    assert game.rbu_defence_bearing() == 90.0
    assert game.fire_rbu_defence() == "ok"
    assert {item.mode for item in game.rbu_rounds} == {"defence"}
    assert all(item.set_depth == rbu.DEFENCE_DEPTH_M for item in game.rbu_rounds)
    first = game.rbu_rounds[0]
    torpedo = EnemyTorpedo(first.x, first.y, 270.0, rbu.DEFENCE_DEPTH_M, 1)
    game.enemy_torpedoes.append(torpedo)
    for _ in range(40):
        game._update_rbu(0.25)
        torpedo.x, torpedo.y = first.x, first.y
    assert torpedo.state == "SASE"


def test_the_crewed_boat_hears_the_splashes_with_a_bearing():
    game, _server, _bridge = _crewed(seed=78)
    boat = game.opfor
    sub = boat.sub
    game.rbu_seq = 1
    game.rbu_rounds = [RbuRound(1, sub.x + 0.5, sub.y, 50.0, 0.05, True, "attack")]
    game.rbu_rockets -= 1
    game._update_rbu(0.1)
    events = [values for key, values in boat.orders.drain_events() if key == "rbu_splash"]
    assert events
    bearing = int(events[-1]["bearing"])
    assert abs(((bearing - 90) + 180) % 360 - 180) <= 10


def test_keys_and_remote_actions():
    game = _game()
    _target(game, 1.5)
    game.station = Station.WEAPONS
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r, mod=0, unicode="r"))
    assert len(game.rbu_rounds) == 0          # R only chooses the rocket launcher
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN,
                                         mod=pygame.KMOD_CTRL, unicode="\r"))
    assert len(game.rbu_rounds) == rbu.SALVO
    assert V2_ACTION_REGISTRY["weapons_fire_rbu"].direct_fire
    assert V2_ACTION_REGISTRY["weapons_rbu_defence"].stations == frozenset({"weapons"})
    assert V2_ACTION_REGISTRY["weapons_rbu_defence"].validate_params({})
