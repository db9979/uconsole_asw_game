"""Strict, transactional v8 continuation for runtime weapons and observations."""

import copy
import json
import math
import random

import pytest

from src.air.asm import ASM, ESSM
from src.core import config
from src.core.game import Game
from src.enemies.animal import Animal
from src.enemies.decoy import Decoy
from src.enemies.sub import Sub
from src.enemies.surface import SurfaceShip
from src.sonar.sonar import Contact
from src.weapons.torpedo import EnemyTorpedo, Torpedo


ID_CLASSES = {"sub": Sub, "animal": Animal, "surface": SurfaceShip,
              "decoy": Decoy, "enemy_torpedo": EnemyTorpedo}


@pytest.fixture(autouse=True)
def preserve_process_counters(monkeypatch):
    for cls in ID_CLASSES.values():
        monkeypatch.setattr(cls, "_next_id", cls._next_id)


@pytest.fixture
def game():
    game = Game(seed=721, start_menu=False, audio_enabled=False)
    game.sim_t = 20.0
    sub = game.subs[0]
    sub.memory.update(contact_age=3.0, contact_bearing=90.0,
                      contact=dict(x=game.ship.x, y=game.ship.y,
                                   speed=5.0, course=90.0, noise=.4))
    game.torpedoes = [Torpedo(game.ship.x, game.ship.y, 90, 80, sub, 1,
                              range_nm=5.5, guidance_x=game.ship.x + 8,
                              guidance_y=game.ship.y)]
    game.torpedoes[0].break_wire()
    game.torpedoes[0].terminal_active = True
    game.torpedoes[0].travel = .3
    missile = ASM(game.ship.x + 12, game.ship.y, 270, 21, game.rng_asm)
    missile.age_s, missile.travel = 5, .5
    game.asms = [missile]
    game.asm_seq, game.warship_asm_seq = 39, 2
    game.ciws_cooldown_s = .63
    game.essms = [ESSM(game.ship.x, game.ship.y, 90, missile, 1,
                       guidance_x=game.ship.x + 10, guidance_y=game.ship.y + 1,
                       target_id=21)]
    game.essms[0].travel = .2
    game.decoys = [Decoy(game.ship.x + 2, game.ship.y, 50, game.rng_world)]
    game.enemy_torpedoes = [EnemyTorpedo(game.ship.x + 8, game.ship.y, 270, 8, 1)]
    if not game.civilians:
        game.civilians = [SurfaceShip(game.ship.x + 30, game.ship.y, game.rng_world)]
    game.civilians[0].orbit_direction = -1
    game.warships = [SurfaceShip(game.ship.x + 40, game.ship.y,
                                 game.rng_world, hostile=True)]
    game.warships[0].sunk = True
    game.warships[0].sunk_score_awarded = True
    game.dmg_team = 3
    game.damage.teams[3] = "engine"
    contact = Contact(11, sub.id, "buoy", "sub")
    contact.last_seen = 20
    contact.tma_seen = 17
    contact.buoy_fixes = [(16, game.ship.x + 5, game.ship.y, .6),
                          (18, game.ship.x + 6, game.ship.y, .7)]
    game.sonar.contacts[sub.id] = contact
    game.sonar._pending_pings = [dict(
        target=game.enemy_torpedoes[0], frigate=game.ship, world=game.world,
        sent_at=20, ready_at=25, range_factor=1.0, mode="BOW")]
    return game


def counter_state():
    return {name: cls._next_id for name, cls in ID_CLASSES.items()}


def reject_constant(value):
    raise AssertionError(f"non-JSON numeric constant: {value}")


def test_normal_save_is_strict_json_and_restores_all_new_fields(game, tmp_path):
    path = tmp_path / "strict.json"
    game.save_game(str(path))
    state = json.loads(path.read_text(), parse_constant=reject_constant)
    assert state["version"] == 8
    assert state["subs"][0]["memory"]["last_ping_age"] is None
    assert state["subs"][0]["memory"]["last_torpedo_age"] is None
    before_counters = counter_state()
    game.load_state(state)
    assert counter_state() == before_counters
    assert math.isinf(game.subs[0].memory["last_ping_age"])
    assert game.subs[0].memory["contact"]["noise"] == .4
    assert game.torpedoes[0].range_nm == game.torpedoes[0].RANGE_NM == 5.5
    assert game.torpedoes[0].terminal_active
    assert game.torpedoes[0].wire_state == "BROKEN"
    assert (game.asms[0].age_s, game.asms[0].travel) == (5, .5)
    assert game.asm_seq == 39 and game.warship_asm_seq == 2
    assert game.ciws_cooldown_s == .63
    assert game.dmg_team == 3 and game.damage.teams[3] == "engine"
    assert game.civilians[0].orbit_direction == -1
    assert game.warships[0].sunk_score_awarded
    assert game.essms[0].target is game.asms[0]
    assert game.essms[0].target_id == 21
    assert game.essms[0].guidance_x == state["essms"][0]["guidance_x"]
    assert game.essms[0].guidance_y == state["essms"][0]["guidance_y"]
    contact = game.sonar.contacts[game.subs[0].id]
    assert contact.tma_seen == 17
    assert contact.buoy_fixes == [tuple(row) for row in state["sonar"]["contacts"][str(contact.target_id)]["buoy_fixes"]]
    assert json.loads(json.dumps(game.save_state(), allow_nan=False)) == state


def test_enemy_torpedo_pending_ping_reference_restored_after_all_entities(game):
    target_id = game.enemy_torpedoes[0].id
    game.load_state(game.save_state())
    pending = game.sonar._pending_pings[0]
    assert pending["target"] is game.enemy_torpedoes[0]
    assert pending["target"].id == target_id
    assert pending["frigate"] is game.ship and pending["world"] is game.world
    assert pending["ready_at"] == 25


def test_pending_launch_queues_survive_save(game):
    sub = game.subs[0]
    sub.pending_torpedoes = [(sub.x, sub.y, 123, 8)]
    sub.pending_decoys = [(sub.x, sub.y)]
    game.warships[0].pending_asm = [(300, 300, 2)]
    state = game.save_state()
    game.load_state(state)
    assert game.subs[0].pending_torpedoes == [(sub.x, sub.y, 123, 8)]
    assert game.subs[0].pending_decoys == [(sub.x, sub.y)]
    assert game.warships[0].pending_asm == [(300, 300, 2)]
    game._drain_enemy_torpedoes()
    assert game.enemy_torpedoes[-1].course == 123


def test_weapon_midcourse_split_run_matches_uninterrupted(game):
    restored = Game(seed=722, start_menu=False, audio_enabled=False)
    snapshot = json.loads(json.dumps(game.save_state(), allow_nan=False))
    restored.load_state(snapshot)
    for current in (game, restored):
        current.mission.asm_count = 0
        for _ in range(10):
            current._update_player_torpedoes(.05)
            current._update_air_defense(.05, publish_picture=False)
    first, second = game.save_state(), restored.save_state()
    for key in ("torpedoes_in_flight", "asms", "essms", "ciws_cooldown_s", "asm_seq", "rngs"):
        assert second[key] == first[key], key


def test_terminal_seekers_restore_actual_target_and_command_identity(game):
    game.torpedoes[0].seeker_acquired = True
    game.torpedoes[0]._seeker_target = game.subs[0]
    game.essms[0].seeker_acquired = True
    game.essms[0].target_id = 39  # Command identity may differ from acquired ASM.
    game.load_state(game.save_state())
    assert game.torpedoes[0]._seeker_target is game.subs[0]
    assert game.torpedoes[0].seeker_acquired
    assert game.essms[0].target is game.asms[0]
    assert game.essms[0].target_id == 39 and game.essms[0].seeker_acquired


def test_essm_lost_track_retains_observed_datum_without_live_object(game):
    weapon = game.essms[0]
    weapon.target = None
    state = game.save_state()
    game.load_state(state)
    restored = game.essms[0]
    assert restored.target is None and restored.target_id == 21
    assert (restored.guidance_x, restored.guidance_y) == (weapon.guidance_x, weapon.guidance_y)
    restored.update(.1)
    assert restored.state == "LAUF"


def test_legacy_essm_datum_uses_saved_course_not_hidden_target(game):
    state = game.save_state()
    weapon = state["essms"][0]
    for key in ("guidance_x", "guidance_y", "track_target_id", "seeker_acquired"):
        weapon.pop(key)
    weapon["course"] = 0
    game.load_state(state)
    restored = game.essms[0]
    assert restored.guidance_x == weapon["x"]
    assert restored.guidance_y == weapon["y"] - (config.ESSM_RANGE_NM - weapon["travel"])
    assert not restored.seeker_acquired


def test_cleared_wave_counter_survives_reload_and_reset(game):
    game.asms.clear()
    game.essms.clear()
    game.load_state(game.save_state())
    assert game.asm_seq == 39
    game.mission.asm_count = 10
    game.mission_time = 100000
    game._maybe_spawn_asm()
    assert game.asms[0].seq == 40
    game.reset(721)
    assert game.asm_seq == 0 and game.ciws_cooldown_s == 0


def test_legacy_asm_counter_accounts_for_retained_observations(game):
    game.air_picture.observe(track_id="M-120", kind="ASM", target_id=120,
                             source="RADAR-L", bearing=90, range_nm=10,
                             observer_x=game.ship.x, observer_y=game.ship.y,
                             course=None, quality=1, now=20, label="M120")
    state = game.save_state()
    state.pop("asm_seq")
    game.load_state(state)
    assert game.asm_seq == 120
    assert game._next_asm_sequence() == 121


def spawn_entities(game):
    rng = game.rng_world
    return [Sub(100, 100, 50, 0, "diesel_alt", rng),
            Animal(100, 100, "whale", rng), SurfaceShip(100, 100, rng),
            Decoy(100, 100, 50, rng), EnemyTorpedo(100, 100, 90, 5, 1)]


def test_retired_entity_high_water_preserves_future_spawn_ids(game, monkeypatch):
    spawn_entities(game)  # Allocated, then removed before the snapshot.
    state = game.save_state()
    expected = [(e.id, getattr(e, "sensor_seed", None)) for e in spawn_entities(game)]
    # Fork the allocator timeline to model a fresh process, not a concurrent game.
    for name, cls in ID_CLASSES.items():
        monkeypatch.setattr(cls, "_next_id", state["next_entity_ids"][name])
    game.load_state(state)
    actual = [(e.id, getattr(e, "sensor_seed", None)) for e in spawn_entities(game)]
    assert actual == expected


def test_repeated_load_does_not_consume_ids_or_rewind_other_instances(game):
    state = game.save_state()
    other_entities = spawn_entities(game)
    high_water = counter_state()
    for _ in range(3):
        game.load_state(state)
        assert counter_state() == high_water
    for cls, entity in zip(ID_CLASSES.values(), other_entities):
        assert cls._next_id > entity.id


def test_late_restore_failure_rolls_back_live_state_and_all_counters(game):
    before, counters = game.save_state(), counter_state()
    ship, sonar = game.ship, game.sonar
    bad = copy.deepcopy(before)
    bad["rngs"]["world"] = [3, [0], None]
    with pytest.raises(ValueError, match="invalid save"):
        game.load_state(bad)
    assert game.ship is ship and game.sonar is sonar
    assert game.save_state() == before
    assert counter_state() == counters


def test_load_does_not_rewind_an_allocation_made_during_restoration(game, monkeypatch):
    original = Game._restore_rng
    external = []

    def allocate_then_fail(rng, data):
        external.append(Decoy(100, 100, 50, random.Random(1)))
        raise ValueError("late failure after another instance allocated")

    state = game.save_state()
    before = Decoy._next_id
    monkeypatch.setattr(Game, "_restore_rng", staticmethod(allocate_then_fail))
    assert not game._load_save_data(state)
    assert Decoy._next_id > external[0].id >= before
    monkeypatch.setattr(Game, "_restore_rng", staticmethod(original))


@pytest.mark.parametrize("version", range(1, 9))
def test_only_known_legacy_infinite_ages_migrate_to_strict_json(game, tmp_path, version):
    data = game.save_state()
    data["version"] = version
    memory = data["subs"][0]["memory"]
    memory["last_ping_age"] = memory["last_torpedo_age"] = float("inf")
    memory["unknown_optional"] = None
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(data))
    assert game.load_game(str(path))
    assert math.isinf(game.subs[0].memory["last_ping_age"])
    assert game.subs[0].memory["unknown_optional"] is None
    json.loads(json.dumps(game.save_state(), allow_nan=False), parse_constant=reject_constant)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("location", ["unknown", "ship", "memory"])
def test_recursive_nonfinite_rejection_preserves_state(game, value, location):
    before = game.save_state()
    data = copy.deepcopy(before)
    if location == "unknown":
        data["future_extension"] = {"nested": [value]}
    elif location == "ship":
        data["ship"]["clock"] = value
    else:
        data["subs"][0]["memory"]["contact_age"] = value
    assert not game._load_save_data(data)
    assert game.save_state() == before


def test_strict_write_failure_keeps_previous_file_and_removes_stage(game, tmp_path):
    path = tmp_path / "slot.json"
    game.save_game(str(path))
    previous = path.read_bytes()
    game.sonar.gain_db = float("nan")
    with pytest.raises(ValueError):
        game.save_game(str(path))
    assert path.read_bytes() == previous
    assert set(tmp_path.iterdir()) == {path, tmp_path / "saves"}


@pytest.mark.parametrize("path,value", [
    (("torpedoes_in_flight", 0, "target_id"), 999999999),
    (("torpedoes_in_flight", 0, "range_nm"), 0),
    (("torpedoes_in_flight", 0, "range_nm"), True),
    (("torpedoes_in_flight", 0, "travel"), 1000),
    (("torpedoes_in_flight", 0, "terminal_active"), 1),
    (("torpedoes_in_flight", 0, "midcourse_timer"), 13),
    (("essms", 0, "target_id"), 999999999),
    (("essms", 0, "track_target_id"), -1),
    (("essms", 0, "guidance_x"), None),
    (("essms", 0, "guidance_y"), "east"),
    (("essms", 0, "seeker_acquired"), "yes"),
    (("asms", 0, "age_s"), ASM.LIFE_S + 1),
    (("asms", 0, "travel"), ASM.RANGE_NM + 1),
    (("asm_seq",), 0),
    (("ciws_cooldown_s",), 1.1),
    (("ciws_cooldown_s",), True),
    (("next_entity_ids", "sub"), 0),
    (("next_entity_ids", "surface"), "5000"),
    (("next_entity_ids", "unknown"), 5000),
    (("sonar", "pending_pings", 0, "target_id"), 999999999),
    (("damage", "teams", "4"), "engine"),
    (("damage", "teams", "1"), "missing_compartment"),
    (("damage", "teams"), []),
    (("ship", "order_idx"), len(config.TELEGRAPH_ORDERS)),
    (("ship", "order_idx"), True),
    (("ship", "order_idx"), "2"),
    (("dmg_team",), 0),
    (("dmg_team",), True),
    (("civilians", 0, "orbit_direction"), 0),
    (("civilians", 0, "sunk_score_awarded"), True),
    (("subs", 0, "memory", "contact_age"), None),
    (("subs", 0, "memory", "contact", "noise"), 1.1),
    (("subs", 0, "memory", "last_ping_age"), -float("inf")),
])
def test_malformed_runtime_states_and_refs_are_transactional(game, path, value):
    before, counters = game.save_state(), counter_state()
    data = copy.deepcopy(before)
    item = data
    for key in path[:-1]:
        item = item[key]
    item[path[-1]] = value
    assert not game._load_save_data(data)
    assert game.save_state() == before
    assert counter_state() == counters


@pytest.mark.parametrize("patch", [
    {"tma_seen": -1}, {"tma_seen": float("nan")}, {"tma_seen": "later"},
    {"buoy_fixes": [[1, 2, 3]]}, {"buoy_fixes": [[1, 2, 3, 1.1]]},
    {"buoy_fixes": [[1, 2, 3, -.1]]}, {"buoy_fixes": [[1, 2, 3, True]]},
    {"buoy_fixes": [[1, float("inf"), 3, .5]]},
    {"buoy_fixes": [[1, 2, 3, .5]] * 81},
])
def test_malformed_buoy_evidence_is_transactional(game, patch):
    before = game.save_state()
    data = copy.deepcopy(before)
    data["sonar"]["contacts"][str(game.subs[0].id)].update(patch)
    with pytest.raises(ValueError):
        game.load_state(data)
    assert game.save_state() == before


def test_buoy_evidence_save_is_bounded_without_mutating_live_history(game):
    contact = game.sonar.contacts[game.subs[0].id]
    contact.buoy_fixes = [(i, 100, 100, .5) for i in range(90)]
    state = game.save_state()
    assert len(contact.buoy_fixes) == 90
    game.load_state(state)
    assert game.sonar.contacts[game.subs[0].id].buoy_fixes == [(i, 100, 100, .5) for i in range(10, 90)]


def test_actual_flank_noise_observation_roundtrips(game, monkeypatch, tmp_path):
    game.ship.cycle_telegraph(len(config.TELEGRAPH_ORDERS))
    game.ship.update(300.0)
    assert game.ship.telegraph == "FLANK"
    assert game.ship.speed == config.SHIP_SPEED_MAX_KN
    assert game.ship.noise_level() == pytest.approx(1.05)
    sub = game.subs[0]
    sub.x, sub.y = game.ship.x + 1, game.ship.y
    monkeypatch.setattr(game.world, "on_land", lambda *args: False)
    monkeypatch.setattr(game.world, "depth_m", lambda *args: 1000)
    monkeypatch.setattr(game.world, "sonar_path_blocked", lambda *args: False)
    sub.update(.1, game.ship, game.world)
    assert sub.memory["contact"]["noise"] == game.ship.noise_level()
    path = tmp_path / "flank.json"
    game.save_game(str(path))
    assert game.load_game(str(path))
    assert game.ship.telegraph == "FLANK"
    assert game.subs[0].memory["contact"]["noise"] == game.ship.noise_level()


@pytest.mark.parametrize("count", [0, 1, 5, 1_000_000, True, 2.5, float("inf")])
def test_pending_salvo_counts_obey_catalog_envelope_before_restore(game, monkeypatch, count):
    before, counters = game.save_state(), counter_state()
    bad = copy.deepcopy(before)
    bad["warships"][0]["pending_asm"] = [(100, 100, count)]

    def forbidden_restore(*args):
        pytest.fail("invalid salvo reached state construction")

    monkeypatch.setattr(Game, "_restore_state", forbidden_restore)
    assert not game._load_save_data(bad)
    assert game.save_state() == before and counter_state() == counters


def test_pending_salvo_expansion_budget_includes_all_queues_and_live_missiles(game, monkeypatch):
    state = game.save_state()
    salvo_max = game.warships[0].profile.asm_salvo[1]
    live_count = salvo_max
    first_seq = state["asms"][0]["seq"]
    state["asms"] = [dict(state["asms"][0], seq=first_seq + index) for index in range(live_count)]
    rows = (Game.MAX_SAVED_ASMS - live_count) // salvo_max
    state["warships"][0]["pending_asm"] = [(100, 100, salvo_max)] * rows
    assert Game._valid_save_document(state)

    # A second queue stays individually legal but exceeds the aggregate budget.
    extra = copy.deepcopy(state["warships"][0])
    extra["id"] = state["next_entity_ids"]["surface"]
    state["next_entity_ids"]["surface"] += 1
    extra["pending_asm"] = [(100, 100, salvo_max)]
    state["warships"].append(extra)
    before, counters = game.save_state(), counter_state()
    monkeypatch.setattr(Game, "_restore_state",
                        lambda *args: pytest.fail("expanded missile budget was not checked before restore"))
    assert not game._load_save_data(state)
    assert game.save_state() == before and counter_state() == counters
    state["warships"].pop()
    state["asms"].append(dict(state["asms"][0], seq=first_seq + live_count))
    assert not Game._valid_save_document(state)


def test_salvo_drain_allocates_monotonically_without_scanning_live_missiles(game):
    class NoIteration(list):
        def __iter__(self):
            pytest.fail("ASM allocation rescanned the live missile collection")

    game.asms = NoIteration(game.asms)
    warship = game.warships[0]
    warship.sunk = False
    size = warship.profile.asm_salvo[1]
    warship.pending_asm = [(100, 100, size)] * 100
    previous = game.asm_seq
    game._drain_warship_asm()
    assert not warship.pending_asm
    assert game.asm_seq == previous + 100 * size
    assert game.asms[1].seq == previous + 1
    assert game.asms[-1].seq == game.asm_seq


def test_manually_constructed_missile_ids_are_reconciled_at_save_load(game):
    game.asms.append(ASM(100, 100, 90, 500, game.rng_asm))
    game.load_state(game.save_state())
    game.asms.clear()
    assert game._next_asm_sequence() == 501


@pytest.mark.parametrize("version", range(1, 9))
@pytest.mark.parametrize("wire_age", [.5, 3.0, Torpedo.WIRE_BREAK_S])
def test_legacy_retired_acquired_decoy_migrates_without_losing_datum_or_wire(
        game, tmp_path, version, wire_age):
    torpedo, decoy = game.torpedoes[0], game.decoys[0]
    decoy.x, decoy.y, decoy.depth = torpedo.x + .5, torpedo.y, 50
    torpedo.depth = torpedo.target_depth = 50
    torpedo.guidance_x, torpedo.guidance_y = decoy.x, decoy.y
    torpedo._midcourse_timer = wire_age
    torpedo.update(.05, seeker_candidates=[decoy])
    assert torpedo.seeker_acquired and torpedo.target is decoy
    decoy.dead = True
    game.decoys.clear()

    state = game.save_state()
    state["version"] = version
    row = state["torpedoes_in_flight"][0]
    # Reproduce the previous serializer's sticky acquired target after pruning.
    row["target_id"], row["seeker_acquired"] = decoy.id, torpedo.seeker_acquired
    row.pop("terminal_active")
    row.pop("range_nm")
    expected_datum = torpedo.guidance_x, torpedo.guidance_y
    expected_timer = torpedo._midcourse_timer
    expected_midcourse = torpedo._midcourse
    path = tmp_path / "retired-decoy.json"
    path.write_text(json.dumps(state))
    assert game.load_game(str(path))
    restored = game.torpedoes[0]
    assert restored.target is None and restored._seeker_target is None
    assert not restored.seeker_acquired and restored.terminal_active
    assert (restored.guidance_x, restored.guidance_y) == expected_datum
    assert restored._midcourse_timer == expected_timer
    assert restored._midcourse == expected_midcourse
    assert Game._valid_save_document(game.save_state())
    candidate = game.subs[0]
    candidate.x, candidate.y, candidate.depth = restored.x + .5, restored.y, 50
    restored.update(.05, seeker_candidates=[candidate])
    assert restored.seeker_acquired and restored.target is candidate


@pytest.mark.parametrize("version", range(1, 9))
def test_legacy_multiple_essms_outlive_intercepted_target_without_truth_reconstruction(
        game, tmp_path, version):
    target = game.asms[0]
    target.x, target.y = game.ship.x + 2, game.ship.y
    first = ESSM(target.x - .01, target.y, 90, target, 1,
                 guidance_x=target.x, guidance_y=target.y)
    survivors = [ESSM(game.ship.x, game.ship.y, 90, target, seq,
                      guidance_x=target.x, guidance_y=target.y) for seq in (2, 3)]
    first.update(.05)
    assert first.state == "HIT" and target.state == "ABGEFANGEN"
    for weapon in survivors:
        weapon.update(.05)
        assert weapon.state == "LAUF" and weapon.target is target
    game.asms.clear()
    game.essms = survivors
    state = game.save_state()
    state["version"] = version
    state.pop("asm_seq")
    for row, weapon in zip(state["essms"], survivors):
        row["target_id"] = weapon.target.seq
        for field in ("guidance_x", "guidance_y", "track_target_id", "seeker_acquired"):
            row.pop(field)
    path = tmp_path / "intercepted-asm.json"
    path.write_text(json.dumps(state))
    assert game.load_game(str(path))
    assert not game.asms and len(game.essms) == 2
    for restored, row in zip(game.essms, state["essms"]):
        assert restored.target is None and not restored.seeker_acquired
        assert restored.target_id == target.seq
        remaining = config.ESSM_RANGE_NM - row["travel"]
        assert restored.guidance_x == pytest.approx(row["x"] + remaining)
        assert restored.guidance_y == pytest.approx(row["y"])
        restored.update(.05, candidates=[])
        assert restored.state == "LAUF"
    assert Game._valid_save_document(game.save_state())


@pytest.mark.parametrize("collection", ["torpedoes_in_flight", "essms"])
def test_current_projectile_format_still_rejects_dangling_acquired_references(game, collection):
    before, counters = game.save_state(), counter_state()
    bad = copy.deepcopy(before)
    bad[collection][0]["target_id"] = 999999999
    bad[collection][0]["seeker_acquired"] = True
    assert not game._load_save_data(bad)
    assert game.save_state() == before and counter_state() == counters


@pytest.mark.parametrize("collection", ["torpedoes_in_flight", "essms"])
def test_partial_current_projectile_fields_do_not_enable_legacy_dangling_migration(game, collection):
    before = game.save_state()
    bad = copy.deepcopy(before)
    row = bad[collection][0]
    row["target_id"] = 999999999
    if collection == "torpedoes_in_flight":
        row.pop("terminal_active")  # range_nm still identifies the new serializer.
    else:
        row.pop("guidance_x")
        row.pop("guidance_y")  # track_target_id/seeker state are still new fields.
    assert not game._load_save_data(bad)
    assert game.save_state() == before
