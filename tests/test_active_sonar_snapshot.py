"""Frozen active evidence, legacy queue migration and transactional validation."""

import copy
import json
import math
import random
from types import SimpleNamespace as NS

import pytest

from src.core import config
from src.core.game import Game
from src.enemies.animal import Animal
from src.enemies.decoy import Decoy
from src.enemies.sub import Sub
from src.enemies.surface import SurfaceShip
from src.ship.ship import Ship
from src.sonar.sonar import SonarSystem
from src.weapons.torpedo import EnemyTorpedo
from src.world.world import World


def counters():
    return tuple(cls._next_id for cls in (Sub, Animal, SurfaceShip, Decoy, EnemyTorpedo))


def scene():
    ship = Ship(250, 250, speed_kn=4)
    target = Sub(255, 250, 40, 0, "diesel_alt", random.Random(7))
    world = NS(sea_state=0, thermocline_depth_m=lambda x, y: 100,
               sonar_path_blocked=lambda *args: False,
               echo_delay_s=lambda distance: distance * 1852 * 2 / config.SOUND_SPEED_M_S)
    return ship, target, world


@pytest.mark.parametrize("version", range(1, 9))
def test_legacy_pending_return_from_retired_entity_is_discarded(version):
    game = Game(seed=7, audio_enabled=False)
    state = game.save_state()
    state["version"] = version
    state["sonar"]["pending_pings"] = [dict(
        target_id=987654321, sent_at=0., ready_at=2., range_factor=1., mode="BOW")]
    restored = Game(seed=8, audio_enabled=False)
    restored.load_state(state)
    assert restored.seed == 7
    assert restored.sonar._pending_pings == []


def test_moving_geometry_and_later_terrain_cannot_remeasure_echo(monkeypatch):
    ship, target, world = scene()
    sonar, immediate = SonarSystem(7), SonarSystem(7)
    heard = []
    target.hear_ping = lambda: heard.append(True)
    expected = immediate.apply_ping(ship, [target], world, 10, notify_ping=False)[0]
    rng_state = sonar.rng.getstate(), random.getstate()
    sonar.queue_ping(ship, [target], world, 10)
    assert heard == [True]  # Intentional immediate simplified intercept.
    assert not sonar.contacts and not sonar.echo_history
    pending = sonar._pending_pings[0]
    snapshot = dict(pending["snapshot"])
    assert SonarSystem.valid_ping_snapshot(snapshot)
    json.dumps(snapshot, allow_nan=False)
    ship.x, ship.y, ship.course = 300, 290, 180
    target.x, target.y, target.depth = 450, 410, 300
    world.sea_state = 9

    def no_remeasurement(*args):
        pytest.fail("Echo reception read live geometry or environment")

    monkeypatch.setattr(target, "distance_nm", no_remeasurement)
    monkeypatch.setattr(target, "bearing_from_frigate", no_remeasurement)
    world.thermocline_depth_m = world.sonar_path_blocked = no_remeasurement
    sonar._process_pending_pings(pending["ready_at"] - .001)
    assert not sonar.contacts and not sonar.echo_events
    sonar._process_pending_pings(pending["ready_at"] + .1)
    contact = sonar.contacts[target.id]
    assert contact.ping_pos == expected.ping_pos
    assert (contact.bearing, contact.range_est, contact.depth_est) == (
        snapshot["bearing"], snapshot["range_nm"], snapshot["depth_m"])
    assert contact.range_seen == contact.last_seen == 10
    assert sonar.echo_history == immediate.echo_history == sonar.echo_events
    assert pending["snapshot"] == snapshot and not sonar._pending_pings
    assert (sonar.rng.getstate(), random.getstate()) == rng_state
    assert heard == [True]
    assert not any("target" in key or "world" in key for key in sonar.echo_history[0])


def test_tow_retrieval_does_not_cancel_a_scattered_return():
    ship, target, world = scene()
    sonar = SonarSystem()
    sonar.tow_state, sonar.tow_payout = sonar.STREAMED, 1
    sonar.queue_ping(ship, [target], world, 0, mode="TOWED")
    deadline = sonar._pending_pings[0]["ready_at"]
    sonar.tow_state, sonar.tow_payout = sonar.STOWED, 0
    sonar.advance_mechanics(.1, deadline, ship)
    assert sonar.echo_history[0]["mode"] == "TOWED"


@pytest.mark.parametrize("flag", ["sunk", "dead", "hit"])
def test_destroyed_scatterer_cancels_pending_return(flag):
    ship, sub, world = scene()
    target = NS(id=sub.id, depth=sub.depth, x=sub.x, y=sub.y,
                distance_nm=sub.distance_nm, bearing_from_frigate=sub.bearing_from_frigate)
    setattr(target, flag, False)
    sonar = SonarSystem()
    sonar.queue_ping(ship, [target], world, 0)
    deadline = sonar._pending_pings[0]["ready_at"]
    setattr(target, flag, True)
    sonar._process_pending_pings(deadline)
    assert not sonar._pending_pings and not sonar.contacts
    assert not sonar.echo_history and not sonar.echo_events


def test_intercept_only_does_not_create_future_echo_opportunity():
    ship, target, world = scene()
    target.x = ship.x + (config.SONAR_ACTIVE_BASE_NM + config.SONAR_PING_HEAR_RANGE_NM) / 2
    heard = []
    target.hear_ping = lambda: heard.append(True)
    sonar = SonarSystem()
    sonar.queue_ping(ship, [target], world, 0)
    assert heard == [True] and not sonar._pending_pings
    target.x = ship.x + 1
    sonar._process_pending_pings(100)
    assert not sonar.contacts


def test_overdue_echo_keeps_measurement_age_and_cannot_revive_stale_fix():
    ship, target, world = scene()
    sonar = SonarSystem()
    sonar.queue_ping(ship, [target], world, 0)
    sonar._process_pending_pings(config.SONAR_PING_FIX_MAX_AGE_S + 1)
    contact = sonar.contacts[target.id]
    assert contact.range_est is contact.depth_est is contact.observed_x is None
    assert sonar.echo_history[0]["t"] == 0


def test_late_echo_records_its_own_measurement_without_replacing_newer_ping():
    ship, target, world = scene()
    sonar = SonarSystem()
    sonar.queue_ping(ship, [target], world, 0)
    old = dict(sonar._pending_pings[0]["snapshot"])
    target.x = ship.x + 1
    newer = sonar.apply_ping(ship, [target], world, 5)[0]
    position = newer.ping_pos
    sonar._process_pending_pings(20)
    assert newer.range_seen == 5 and newer.ping_pos == position
    assert sonar.echo_history[-1]["t"] == 0
    assert sonar.echo_history[-1]["range_nm"] == old["range_nm"]


@pytest.fixture
def flight_game(monkeypatch):
    game = Game(seed=811, start_menu=False, audio_enabled=False)
    game.ship.x = game.ship.y = 250
    target = game.subs[0]
    target.x, target.y, target.depth = 255, 250, 40
    game.sonar = SonarSystem(811)
    monkeypatch.setattr(game.world, "sonar_path_blocked", lambda *args: False)
    monkeypatch.setattr(game.world, "thermocline_depth_m", lambda *args: 100)
    game.sonar.queue_ping(game.ship, [target], game.world, 0)
    assert len(game.sonar._pending_pings) == 1
    game.sim_t = 2
    game.ship.x += .1
    target.y -= .1
    return game


def test_save_midflight_matches_uninterrupted_frozen_delivery(flight_game):
    game = flight_game
    state = json.loads(json.dumps(game.save_state(), allow_nan=False))
    restored = Game(seed=812, start_menu=False, audio_enabled=False)
    restored.load_state(state)
    pending = state["sonar"]["pending_pings"][0]
    snapshot = pending["snapshot"]
    assert restored.sonar._pending_pings[0]["snapshot"] == snapshot
    assert restored.save_state()["sonar"]["pending_pings"] == state["sonar"]["pending_pings"]
    for current in (game, restored):
        current.ship.x += 20
        current.subs[0].x += 100
        current.subs[0].depth = 250
        current.sonar.advance_mechanics(.1, pending["ready_at"] - .001, current.ship)
        assert not current.sonar.echo_history
        current.sonar.advance_mechanics(.1, pending["ready_at"] + .1, current.ship)
    assert restored.save_state()["sonar"] == game.save_state()["sonar"]
    assert restored.sonar.echo_events == game.sonar.echo_events
    contact = restored.sonar.contacts[game.subs[0].id]
    expected = (snapshot["observer_x"] + snapshot["range_nm"] * math.sin(math.radians(snapshot["bearing"])),
                snapshot["observer_y"] - snapshot["range_nm"] * math.cos(math.radians(snapshot["bearing"])))
    assert contact.ping_pos == expected
    assert contact.range_seen == restored.sonar.echo_history[0]["t"] == snapshot["t"]


@pytest.mark.parametrize("version", range(1, 9))
def test_legacy_queue_freezes_once_at_restore_without_rng_or_warning(flight_game, monkeypatch, version):
    game = flight_game
    state = copy.deepcopy(game.save_state())
    state["version"] = version
    pending = state["sonar"]["pending_pings"][0]
    del pending["snapshot"]
    monkeypatch.setattr(World, "sonar_path_blocked", lambda *args: False)
    monkeypatch.setattr(World, "thermocline_depth_m", lambda *args: 100)

    def no_warning(*args):
        pytest.fail("Restoring a pending echo repeated the intercept warning")

    monkeypatch.setattr(Sub, "hear_ping", no_warning)
    random_state = random.getstate()
    game.load_state(state)
    migrated = game.sonar._pending_pings[0]
    assert migrated["ready_at"] == pending["ready_at"]
    assert migrated["snapshot"]["t"] == state["sim_t"]
    assert migrated["snapshot"]["observer_x"] == state["ship"]["x"]
    assert game.save_state()["rngs"] == state["rngs"]
    assert random.getstate() == random_state
    snapshot = dict(migrated["snapshot"])
    game.ship.x += 10
    game.subs[0].x += 30
    resaved = game.save_state()
    monkeypatch.setattr(SonarSystem, "_measure_ping", no_warning)
    game.load_state(resaved)
    assert game.sonar._pending_pings[0]["snapshot"] == snapshot
    game.sonar._process_pending_pings(pending["ready_at"])
    assert game.sonar.echo_history[-1]["t"] == state["sim_t"]


@pytest.mark.parametrize("reason", ["range", "terrain", "stowed", "destroyed"])
def test_legacy_undetectable_return_is_conservatively_discarded(flight_game, monkeypatch, reason):
    state = copy.deepcopy(flight_game.save_state())
    pending = state["sonar"]["pending_pings"][0]
    del pending["snapshot"]
    monkeypatch.setattr(World, "sonar_path_blocked", lambda *args: reason == "terrain")
    if reason == "range":
        state["subs"][0]["x"] = 499
    elif reason == "stowed":
        pending["mode"] = "TOWED"
    elif reason == "destroyed":
        state["subs"][0]["state"] = "SUNK"
    flight_game.load_state(state)
    assert not flight_game.sonar._pending_pings


@pytest.mark.parametrize("key,value", [
    ("t", -1), ("t", 3), ("t", True), ("t", float("nan")),
    ("observer_x", float("inf")), ("observer_y", 1e7), ("observer_x", "250"),
    ("bearing", 360), ("bearing", -1), ("bearing", None),
    ("range_nm", -1), ("range_nm", 10001), ("range_sigma_nm", 0),
    ("range_sigma_nm", 1e-300), ("range_sigma_nm", True),
    ("depth_m", -1), ("depth_m", 10001), ("depth_sigma_m", -1),
    ("depth_sigma_m", 100), ("snr_db", 201), ("target", {"x": 10}),
])
def test_malformed_snapshot_is_transactional(flight_game, key, value):
    before, ids = flight_game.save_state(), counters()
    state = copy.deepcopy(before)
    state["sonar"]["pending_pings"][0]["snapshot"][key] = value
    assert not flight_game._load_save_data(state)
    assert flight_game.save_state() == before and counters() == ids


@pytest.mark.parametrize("patch", [
    {"snapshot": None}, {"snapshot": {}}, {"snapshot": []},
    {"sent_at": 3}, {"sent_at": True}, {"ready_at": -1}, {"ready_at": 25001},
    {"range_factor": True}, {"mode": "OTHER"}, {"target": 1},
])
def test_malformed_pending_envelope_is_transactional(flight_game, patch):
    before, ids = flight_game.save_state(), counters()
    state = copy.deepcopy(before)
    state["sonar"]["pending_pings"][0].update(patch)
    assert not flight_game._load_save_data(state)
    assert flight_game.save_state() == before and counters() == ids


@pytest.mark.parametrize("patch", [
    {"uncertainty_deg": 0}, {"uncertainty_deg": -1}, {"uncertainty_deg": 1e-300},
    {"uncertainty_deg": True}, {"uncertainty_deg": None}, {"uncertainty_deg": 181},
    {"uncertainty_deg": float("nan")}, {"bearing": 360}, {"bearing": "north"},
    {"quality": 1.1}, {"snr": float("inf")}, {"last_seen": -1}, {"entity": {}},
])
def test_nested_array_report_validation_is_transactional(flight_game, patch):
    contact = flight_game.sonar._get_contact(flight_game.subs[0])
    contact.array_observations = {"BOW": dict(bearing=90, quality=.5, snr=4,
                                             last_seen=1, uncertainty_deg=1)}
    before, ids = flight_game.save_state(), counters()
    state = copy.deepcopy(before)
    state["sonar"]["contacts"][str(contact.target_id)]["array_observations"]["BOW"].update(patch)
    assert not flight_game._load_save_data(state)
    assert flight_game.save_state() == before and counters() == ids


def test_legacy_array_report_without_uncertainty_remains_supported(flight_game):
    contact = flight_game.sonar._get_contact(flight_game.subs[0])
    contact.array_observations = {"BOW": dict(bearing=90, quality=.5, snr=4, last_seen=1)}
    flight_game.load_state(flight_game.save_state())
    assert flight_game.sonar.contacts[contact.target_id].array_observations == contact.array_observations


@pytest.mark.parametrize("reports", [[], {"OTHER": {}}, {"BOW": None}, {"BOW": {"quality": .5}}])
def test_malformed_array_report_structure_is_transactional(flight_game, reports):
    contact = flight_game.sonar._get_contact(flight_game.subs[0])
    before, ids = flight_game.save_state(), counters()
    state = copy.deepcopy(before)
    state["sonar"]["contacts"][str(contact.target_id)]["array_observations"] = reports
    assert not flight_game._load_save_data(state)
    assert flight_game.save_state() == before and counters() == ids


def test_failed_legacy_snapshot_derivation_rolls_back_candidate_and_ids(flight_game, monkeypatch):
    before, ids = flight_game.save_state(), counters()
    state = copy.deepcopy(before)
    del state["sonar"]["pending_pings"][0]["snapshot"]
    monkeypatch.setattr(World, "sonar_path_blocked", lambda *args: False)

    def invalid_measurement(*args):
        raise ValueError("invalid reconstructed measurement")

    monkeypatch.setattr(SonarSystem, "_measure_ping", invalid_measurement)
    assert not flight_game._load_save_data(state)
    assert flight_game.save_state() == before and counters() == ids


def test_pending_queue_bound_preserves_immediate_intercepts(monkeypatch):
    ship, first, world = scene()
    second = Sub(256, 250, 40, 0, "diesel_alt", random.Random(8))
    sonar = SonarSystem()
    monkeypatch.setattr(SonarSystem, "MAX_PENDING_PINGS", 1)
    sonar.queue_ping(ship, [first, second], world, 0)
    assert first.heard_ping and second.heard_ping
    assert len(sonar._pending_pings) == 1
    assert sonar._pending_pings[0]["target"] is first


def test_oversized_pending_save_is_transactional(flight_game, monkeypatch):
    before, ids = flight_game.save_state(), counters()
    state = copy.deepcopy(before)
    state["sonar"]["pending_pings"] *= 2
    monkeypatch.setattr(SonarSystem, "MAX_PENDING_PINGS", 1)
    assert not flight_game._load_save_data(state)
    assert flight_game.save_state() == before and counters() == ids
