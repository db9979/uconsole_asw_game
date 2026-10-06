"""The frigate's own ASROC and depth charges (Weapons station, save v29)."""

import copy
import json

import pygame

from src.core.game import Game
from src.core.station import Station
from src.sonar.sonar import Contact
from src.weapons import depth_charge
from src.weapons.depth_charge import DepthCharge


def _game(seed=2901):
    game = Game(seed=seed, start_menu=False, audio_enabled=False)
    game.world.physical_depth_m = lambda x, y: 1000.0
    return game


def _target(game, range_nm=5.0, player_class="U_BOOT"):
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


def test_own_asroc_spends_its_store_and_drops_the_lightweight_torpedo_at_the_datum():
    game = _game()
    contact = _target(game, 5.0)
    assert game.fire_own_asroc() == "ok"
    assert game.own_asrocs_left == depth_charge.OWN_ASROC_STOCK - 1
    weapon = game.asrocs[-1]
    assert weapon.launch_platform_id is None
    assert weapon.weapon_key == depth_charge.OWN_ASROC_KEY
    assert (weapon.datum_x, weapon.datum_y) == (contact.observed_x, contact.observed_y)
    state, other = _roundtrip(game)
    assert other.own_asrocs_left == game.own_asrocs_left
    assert len(other.asrocs) == 1
    for _ in range(600):
        game._update_asrocs(0.1)
        if not game.asrocs:
            break
    payload = game.torpedoes[-1]
    assert payload.launch_origin == "asroc"
    assert payload.launch_platform_id is None
    assert abs(payload.x - contact.observed_x) < 0.05
    _roundtrip(game)


def test_own_asroc_refuses_close_unclassified_unlocated_and_empty():
    game = _game()
    _target(game, 0.5)
    assert game.fire_own_asroc() == "out_of_range"
    _target(game, 5.0, player_class=None)
    assert game.fire_own_asroc() == "not_classified"
    contact = _target(game, 5.0)
    contact.range_est = None
    assert game.fire_own_asroc() == "not_located"
    _target(game, 5.0)
    game.own_asrocs_left = 0
    assert game.fire_own_asroc() == "empty_asroc"
    assert not game.asrocs


def test_depth_charge_pattern_needs_speed_sinks_and_reloads():
    game = _game()
    _target(game)
    game.torpedo_depth = 60
    game.ship.speed = 5.0
    assert game.drop_depth_charges() == "too_slow"
    game.ship.speed = 18.0
    assert game.drop_depth_charges() == "ok"
    assert len(game.depth_charges) == depth_charge.PATTERN_SIZE
    assert game.depth_charges_left == depth_charge.DEPTH_CHARGE_STOCK - depth_charge.PATTERN_SIZE
    assert {charge.set_depth for charge in game.depth_charges} == {60.0}
    assert game.drop_depth_charges() == "reloading"
    game._update_depth_charges(10.0)
    assert all(charge.depth == 35.0 for charge in game.depth_charges)
    game._update_depth_charges(10.0)
    assert not game.depth_charges
    game._update_depth_charges(depth_charge.PATTERN_RELOAD_S)
    assert game.depth_charge_reload_s == 0.0
    assert game.drop_depth_charges() == "ok"


def test_depth_charge_detonation_damages_a_boat_under_the_pattern():
    game = _game(2902)
    sub = game.subs[0]
    game.world.sonar_path_blocked = lambda *args: False
    sub.x, sub.y, sub.depth = game.ship.x, game.ship.y + 0.03, 60.0
    before = sub.hp if hasattr(sub, "hp") else None
    game.depth_charges = [DepthCharge(1, sub.x, sub.y, 60.0, depth=59.0)]
    game.depth_charge_seq = 1
    game.depth_charges_left -= 1
    game._update_depth_charges(1.0)
    assert not game.depth_charges
    assert sub.sunk or sub.state == "SINKING" or (before is not None and sub.hp < before)
    assert depth_charge.depth_charge_damage(5.0) == 100.0
    assert depth_charge.depth_charge_damage(500.0) < 1.0


def test_charges_in_the_water_survive_save_load_and_bad_stores_are_rejected():
    game = _game(2903)
    _target(game)
    game.ship.speed = 18.0
    game.drop_depth_charges()
    game._update_depth_charges(3.0)
    state, other = _roundtrip(game)
    assert [c.serialize() for c in other.depth_charges] == [
        c.serialize() for c in game.depth_charges]
    assert (other.depth_charges_left, other.depth_charge_reload_s) == (
        game.depth_charges_left, game.depth_charge_reload_s)
    for mutate in (
            lambda s: s["asw"]["own_stores"].__setitem__("depth_charges", 20),
            lambda s: s["asw"]["own_stores"].__setitem__("asroc", 5),
            lambda s: s["asw"]["own_stores"].__setitem__("depth_charge_reload_s", -1),
            lambda s: s["asw"]["depth_charges"][0].__setitem__("depth", 400.0),
            lambda s: s["asw"]["depth_charges"][0].__setitem__("seq", 99),
            lambda s: s["asw"]["depth_charges"][0].__setitem__("extra", 1),
            lambda s: s["asw"].pop("own_stores")):
        bad = copy.deepcopy(state)
        mutate(bad)
        assert not other._load_save_data(bad)


def test_own_asroc_in_flight_must_come_out_of_the_store():
    game = _game(2904)
    _target(game)
    game.fire_own_asroc()
    state = json.loads(json.dumps(game.save_state()))
    bad = copy.deepcopy(state)
    bad["asw"]["own_stores"]["asroc"] = depth_charge.OWN_ASROC_STOCK
    assert not game._load_save_data(bad)
    bad = copy.deepcopy(state)
    bad["asw"]["asrocs"][0]["launch_platform_id"] = 5
    assert not game._load_save_data(bad)


def test_keys_are_weapons_station_only_and_deterministic():
    def run():
        game = _game(2905)
        _target(game)
        game.ship.speed = 18.0
        game.station = Station.SONAR
        for key in (pygame.K_a, pygame.K_z):
            game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key))
        assert game.own_asrocs_left == depth_charge.OWN_ASROC_STOCK
        assert game.depth_charges_left == depth_charge.DEPTH_CHARGE_STOCK
        game.station = Station.WEAPONS
        # A and Z only choose; Ctrl+Enter fires the choice.
        for key in (pygame.K_a, pygame.K_z):
            game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key))
            game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN,
                                                 mod=pygame.KMOD_CTRL))
        for _ in range(100):
            game.update(0.1)
        return game
    first, second = run(), run()
    assert first.own_asrocs_left == depth_charge.OWN_ASROC_STOCK - 1
    assert first.depth_charges_left < depth_charge.DEPTH_CHARGE_STOCK
    # Entity ids advance per process, so compare the weapons state itself.
    def weapons(game):
        asw = json.loads(json.dumps(game.save_state()))["asw"]
        return {key: asw[key] for key in ("depth_charges", "depth_charge_seq",
                                           "own_stores", "asrocs")}
    assert weapons(first) == weapons(second)


def test_remote_crew_handlers_fire_through_the_same_checks():
    from src.commander.actions import (_weapons_drop_depth_charges,
                                       _weapons_fire_asroc)
    from src.commander.v2.commands import V2_ACTION_REGISTRY
    game = _game(2906)
    contact = _target(game)
    game.ship.speed = 18.0
    bindings = {"r1": (None, "DIRECT_SONAR", contact, None, None, "weapons")}
    assert V2_ACTION_REGISTRY["weapons_fire_asroc"].direct_fire is True
    assert _weapons_fire_asroc(game, {"ref": "r1", "depth_m": 80}, bindings) == "ok"
    assert game.asrocs[-1].target_depth_m == 80.0
    assert _weapons_drop_depth_charges(game, {"ref": "r1", "depth_m": 120}, bindings) == "ok"
    assert {charge.set_depth for charge in game.depth_charges} == {120.0}
    assert _weapons_drop_depth_charges(game, {"ref": "r1", "depth_m": 120}, bindings) == "not_ready"
    assert _weapons_fire_asroc(game, {"ref": "nope", "depth_m": 80}, bindings) == "unknown_ref"
    game.own_asrocs_left = 0
    assert _weapons_fire_asroc(game, {"ref": "r1", "depth_m": 80}, bindings) == "empty"
