"""Save-v10 runtime catalog snapshots preserve profile-dependent continuation."""

import copy
import json
import random

import pytest

import src.core.game as game_module
from src.air.flights import Flight
from src.core.game import Game
from src.data import catalog
from src.enemies.decoy import Decoy
from src.enemies.sub import Sub
from src.enemies.surface import SurfaceShip
from src.weapons.torpedo import EnemyTorpedo


def _entry(snapshot, filename, key):
    return next(item for item in snapshot["entries"][filename]
                if item["key"] == key)


def _changed_catalog(snapshot):
    changed = copy.deepcopy(snapshot)
    for item in changed["entries"]["subs.json"]:
        item["max_depth_m"] = 123.0
        item["speed_kn"] = [1.0, 2.0]
        item["acoustic"]["signature_text"] = "changed package submarine"
    for filename in ("warships.json", "civilians.json"):
        for item in changed["entries"][filename]:
            item["speed_kn"] = [1.0, 2.0]
            item["asm_salvo"] = [1, 1]
            item["acoustic"]["signature_text"] = "changed package surface"
    for item in changed["entries"]["animals.json"]:
        item["speed_kn"] = 0.01
        item["signature_text"] = "changed package animal"
    for item in changed["entries"]["aircraft.json"]:
        item["speed_kn"] = 1.0
    for item in changed["entries"]["torpedoes.json"]:
        item["speed_kn"] = 1.0
        item["range_nm"] = 1.0
    for item in changed["entries"]["decoys.json"]:
        item["chance"] = 0.0
        item["life_s"] = 1.0
    for component in changed["components"].values():
        for machine in component["machines"]:
            machine["cruise_speed_kn"] = 2.0
            machine["maximum_speed_kn"] = 4.0
            if machine["quiet_speed_kn"] is not None:
                machine["quiet_speed_kn"] = 1.0
        for sensor in component["sensors"]:
            if sensor["synthetic_range_nm"] is not None:
                sensor["synthetic_range_nm"] = 1.0
    return catalog.catalog_from_runtime_snapshot(changed)


def test_v10_snapshot_is_canonical_runtime_only_json():
    game = Game(seed=2401, start_menu=False)
    state = game.save_state()
    snapshot = state["catalog_snapshot"]

    assert snapshot == game.runtime_catalog.runtime_snapshot()
    assert snapshot["version"] == 2
    assert set(snapshot) == {"version", "entries", "bindings", "components"}
    assert set(snapshot["entries"]) == set(catalog.CONTACT_FILENAMES)
    assert set(snapshot["bindings"]) == set(catalog.RUNTIME_BINDINGS)
    assert set(snapshot["components"]) == set(catalog.CONTACT_FILENAMES)
    assert all(isinstance(entries, list) and entries
               for entries in snapshot["entries"].values())
    assert all(set(component) == {
        "version", "profiles", "references", "machines", "sensors",
        "endurances", "emitters", "weapons", "launchers", "magazines",
        "countermeasures",
    } for component in snapshot["components"].values())

    restored = catalog.catalog_from_runtime_snapshot(
        json.loads(json.dumps(snapshot, allow_nan=False)))
    assert restored.runtime_snapshot() == snapshot
    assert restored.profile_systems == game.runtime_catalog.profile_systems
    assert not restored.sources


def test_snapshot_v1_is_rejected():
    game = Game(seed=2400, start_menu=False)
    state = game.save_state()
    state["catalog_snapshot"]["version"] = 1

    assert not game._load_save_data(state)


def test_snapshot_remains_authoritative_after_packaged_defaults_change(monkeypatch):
    game = Game(seed=2402, start_menu=False)
    decoy_profile = game.runtime_catalog.decoys[
        game.runtime_catalog.runtime_bindings["submarine_decoy"]]
    game.decoys.append(Decoy(
        game.ship.x + 1.0, game.ship.y, 40.0, game.rng_world, decoy_profile,
        game.runtime_catalog.acoustic_for(decoy_profile.key)))
    enemy_profile = game.runtime_catalog.torpedoes[
        game.runtime_catalog.runtime_bindings["enemy_torpedo"]]
    source = Sub(
        game.ship.x + 3.0, game.ship.y, 40.0, 0.0, "sub_03",
        random.Random(2402), runtime_catalog=game.runtime_catalog,
        asw_rng=game.rng_asw)
    game.subs.append(source)
    game.decoys[0].source_id = source.id
    if source.countermeasure_store is not None:
        assert source.countermeasure_store.fire()
    if source.weapon_battery is not None:
        weapon_key = source.weapon_battery.fire()
        assert weapon_key is not None
        source.torpedoes_left = source.weapon_battery.remaining_total
    else:
        weapon_key = None
        source.torpedoes_left -= 1
    game.enemy_torpedoes.append(EnemyTorpedo(
        game.ship.x + 2.0, game.ship.y, 270.0, 10.0, 1, enemy_profile,
        guidance_x=game.ship.x, guidance_y=game.ship.y,
        launch_platform_id=source.id, launch_weapon_key=weapon_key))
    state = game.save_state()
    original = copy.deepcopy(state["catalog_snapshot"])
    changed_package = _changed_catalog(original)
    monkeypatch.setattr(game_module, "CATALOG", changed_package)

    game.load_state(state)

    assert game.runtime_catalog.runtime_snapshot() == original
    assert game.runtime_catalog is not changed_package
    assert game.sonar.acoustic_profiles is game.runtime_catalog.acoustic_profiles
    assert all(sub.stype.profile is game.runtime_catalog.subs[sub.stype.key]
               for sub in game.subs)
    assert all(animal.profile is game.runtime_catalog.animals[animal.atype.key]
               for animal in game.animals)
    assert all(ship.profile is game.runtime_catalog.surfaces[ship.signature_key]
               for ship in game.civilians + game.warships)
    assert all(decoy.profile is game.runtime_catalog.decoys[decoy.profile.key]
               for decoy in game.decoys)
    assert all(torpedo.profile is game.runtime_catalog.torpedoes[torpedo.profile_key]
               for torpedo in game.enemy_torpedoes)
    assert game.helo.torpedo_profile is game.runtime_catalog.torpedoes[
        game.runtime_catalog.runtime_bindings["helicopter_torpedo"]]
    assert game.flights.catalog is game.runtime_catalog
    assert all(flight.profile is game.runtime_catalog.aircraft[flight.akey]
               for flight in game.flights.flights)

    fresh = Game(seed=2402, start_menu=False)
    assert fresh.runtime_catalog is changed_package
    assert fresh.subs[0].stype.max_depth_m == 123.0
    assert fresh.flights.flights[0].speed == 1.0


def test_snapshotless_v10_is_rejected():
    game = Game(seed=2403, start_menu=False)
    state = game.save_state()
    state.pop("catalog_snapshot")

    assert not game._load_save_data(state)


def test_save_reader_rejects_oversize_before_json_parse(tmp_path, monkeypatch):
    game = Game(seed=2411, start_menu=False)
    path = tmp_path / "oversize.json"
    path.write_bytes(b" " * 129)
    monkeypatch.setattr(game_module, "MAX_SAVE_DOCUMENT_BYTES", 128)

    assert not game.load_game(str(path))


def test_malformed_snapshot_is_rejected_before_live_state_changes():
    game = Game(seed=2404, start_menu=False)
    state = game.save_state()
    live_catalog = game.runtime_catalog
    live_ship = game.ship
    cases = []

    bad = copy.deepcopy(state)
    bad["catalog_snapshot"]["version"] = True
    cases.append(bad)
    bad = copy.deepcopy(state)
    bad["catalog_snapshot"]["extra"] = []
    cases.append(bad)
    bad = copy.deepcopy(state)
    del bad["catalog_snapshot"]["entries"]["animals.json"]
    cases.append(bad)
    bad = copy.deepcopy(state)
    bad["catalog_snapshot"]["entries"]["subs.json"].append(
        copy.deepcopy(bad["catalog_snapshot"]["entries"]["subs.json"][0]))
    cases.append(bad)
    bad = copy.deepcopy(state)
    bad["catalog_snapshot"]["bindings"]["enemy_torpedo"] = "frigate_torp"
    cases.append(bad)
    bad = copy.deepcopy(state)
    bad["catalog_snapshot"]["entries"]["subs.json"][0]["quiet"] = float("nan")
    cases.append(bad)
    bad = copy.deepcopy(state)
    bad["catalog_snapshot"]["components"]["subs.json"]["extra"] = []
    cases.append(bad)
    bad = copy.deepcopy(state)
    bad["catalog_snapshot"]["components"]["subs.json"]["sensors"][0][
        "cadence_s"] = float("nan")
    cases.append(bad)
    bad = copy.deepcopy(state)
    bad["catalog_snapshot"]["components"]["subs.json"]["sensors"][0][
        "cadence_s"] = 5e-324
    cases.append(bad)

    for malformed in cases:
        assert not game._load_save_data(malformed)
        assert game.runtime_catalog is live_catalog
        assert game.ship is live_ship


def test_snapshot_profile_references_are_strict():
    game = Game(seed=2405, start_menu=False)
    state = game.save_state()
    mutations = [
        lambda value: value["subs"][0].update(stype="missing"),
        lambda value: value["animals"][0].update(atype="missing"),
        lambda value: value["civilians"][0].update(signature_key="missing"),
        lambda value: value["flights"]["items"][0].update(akey="missing"),
        lambda value: value["helo"].update(torpedo_profile_key="enemy_torp"),
    ]
    for mutate in mutations:
        malformed = copy.deepcopy(state)
        mutate(malformed)
        assert not game._load_save_data(malformed)


def test_pending_asm_validation_uses_snapshot_profile(monkeypatch):
    game = Game(seed=2406, start_menu=False)
    profile = game.runtime_catalog.surfaces["warship_01"]
    warship = SurfaceShip(
        game.ship.x + 20.0, game.ship.y, random.Random(8), hostile=True,
        profile=profile)
    warship.pending_asm = [(game.ship.x, game.ship.y, 3)]
    game.warships = [warship]
    state = game.save_state()
    _entry(state["catalog_snapshot"], "warships.json", "warship_01")[
        "asm_salvo"] = [3, 3]
    monkeypatch.setattr(
        game_module, "CATALOG", _changed_catalog(state["catalog_snapshot"]))

    assert game._load_save_data(copy.deepcopy(state))

    invalid = copy.deepcopy(state)
    x, y, _ = invalid["warships"][0]["pending_asm"][0]
    invalid["warships"][0]["pending_asm"][0] = (x, y, 4)
    assert not game._load_save_data(invalid)


def test_changed_package_split_run_keeps_snapshot_continuation(monkeypatch):
    source = Game(seed=2412, start_menu=False)
    source.warships.append(SurfaceShip(
        source.ship.x + 1.0, source.ship.y, random.Random(91), side="hostile",
        doctrine="surface_combatant",
        profile=source.runtime_catalog.surfaces["warship_01"],
        runtime_catalog=source.runtime_catalog))
    for sub in source.subs:
        sub.turn_left = 0.1
    for animal in source.animals:
        animal.turn_left = 0.1
    for ship in source.civilians + source.warships:
        ship.turn_left = 0.1
    state = source.save_state()

    control = Game(seed=1, start_menu=False)
    control.load_state(copy.deepcopy(state))
    changed_package = _changed_catalog(state["catalog_snapshot"])
    monkeypatch.setattr(game_module, "CATALOG", changed_package)
    restored = Game(seed=1, start_menu=False)
    restored.load_state(copy.deepcopy(state))

    for _ in range(20):
        control._update_sim(0.1)
        restored._update_sim(0.1)

    def continuation(game):
        return {
            "subs": [(item.x, item.y, item.depth, item.course, item.speed,
                      item.state, item.rng.getstate()) for item in game.subs],
            "animals": [(item.x, item.y, item.depth, item.course, item.speed,
                         item.rng.getstate()) for item in game.animals],
            "surfaces": [(item.x, item.y, item.course, item.speed,
                           item.rng.getstate(), item.sensor_suite.serialize())
                          for item in game.civilians + game.warships],
            "flights": [(item.x, item.y, item.course, item.speed,
                         item.sensor_bearing, item.sensor_age)
                        for item in game.flights.flights],
            "rngs": game.save_state()["rngs"],
        }

    assert continuation(restored) == continuation(control)


def test_r10_all_submarine_components_roundtrip_from_catalog_snapshot():
    game = Game(seed=2413, start_menu=False)
    game.subs = [
        Sub(game.ship.x + index / 10.0, game.ship.y + 1.0, 50.0, 0.0, key,
            random.Random(5000 + index), runtime_catalog=game.runtime_catalog,
            asw_rng=game.rng_asw)
        for index, key in enumerate(game.runtime_catalog.subs)
    ]
    expected = [(
        sub.stype.key,
        sub.weapon_battery.serialize(),
        sub.countermeasure_store.serialize(),
        sub.sensor_suite.serialize(),
    ) for sub in game.subs]
    state = game.save_state()

    restored = Game(seed=1, start_menu=False)
    assert restored._load_save_data(copy.deepcopy(state))
    assert [(
        sub.stype.key,
        sub.weapon_battery.serialize(),
        sub.countermeasure_store.serialize(),
        sub.sensor_suite.serialize(),
    ) for sub in restored.subs] == expected
    assert restored.runtime_catalog.runtime_snapshot() == state["catalog_snapshot"]


def test_r10_all_warship_components_roundtrip_from_catalog_snapshot():
    game = Game(seed=2414, start_menu=False)
    game.warships = [
        SurfaceShip(
            game.ship.x + index / 10.0, game.ship.y + 2.0,
            random.Random(6000 + index), side="hostile",
            doctrine="surface_combatant",
            profile=game.runtime_catalog.surfaces[key],
            runtime_catalog=game.runtime_catalog)
        for index, key in enumerate(
            f"warship_{number:02d}" for number in range(1, 29))
    ]
    expected = [(
        ship.signature_key,
        ship.asroc_battery.serialize() if ship.asroc_battery is not None else None,
        ship.sensor_suite.serialize(),
    ) for ship in game.warships]
    state = game.save_state()

    restored = Game(seed=1, start_menu=False)
    assert restored._load_save_data(copy.deepcopy(state))
    assert [(
        ship.signature_key,
        ship.asroc_battery.serialize() if ship.asroc_battery is not None else None,
        ship.sensor_suite.serialize(),
    ) for ship in restored.warships] == expected
    assert restored.runtime_catalog.runtime_snapshot() == state["catalog_snapshot"]


def test_r10_all_civilian_components_roundtrip_from_catalog_snapshot():
    game = Game(seed=2415, start_menu=False)
    game.civilians = [
        SurfaceShip(
            game.ship.x + index / 10.0, game.ship.y + 3.0,
            random.Random(7000 + index), side="neutral",
            doctrine="surface_transit", profile=profile,
            runtime_catalog=game.runtime_catalog)
        for index, profile in enumerate(game.runtime_catalog.civilian_surfaces)
    ]
    expected = [(ship.signature_key, ship.sensor_suite.serialize())
                for ship in game.civilians]
    state = game.save_state()

    restored = Game(seed=1, start_menu=False)
    assert restored._load_save_data(copy.deepcopy(state))
    assert [(ship.signature_key, ship.sensor_suite.serialize())
            for ship in restored.civilians] == expected
    assert restored.runtime_catalog.runtime_snapshot() == state["catalog_snapshot"]


def test_r10_all_aircraft_components_roundtrip_from_catalog_snapshot():
    game = Game(seed=2416, start_menu=False)
    bases = game.world.coast.airbases
    game.flights.flights = [
        Flight(
            profile.kind, bases[0],
            dest=(bases[1] if profile.kind == "civil" else None),
            rng=random.Random(8000 + index), seq=index + 1, akey=profile.key,
            catalog=game.runtime_catalog)
        for index, profile in enumerate(game.runtime_catalog.aircraft.values())
    ]
    expected = [(flight.akey, flight.sensor_suite.serialize())
                for flight in game.flights.flights]
    state = game.save_state()

    restored = Game(seed=1, start_menu=False)
    assert restored._load_save_data(copy.deepcopy(state))
    assert [(flight.akey, flight.sensor_suite.serialize())
            for flight in restored.flights.flights] == expected
    assert restored.runtime_catalog.runtime_snapshot() == state["catalog_snapshot"]


def test_r10_batch5_components_and_library_roundtrip_from_catalog_snapshot():
    snapshot = catalog.CATALOG.runtime_snapshot()
    restored = catalog.catalog_from_runtime_snapshot(
        json.loads(json.dumps(snapshot, allow_nan=False)))
    roundtrip = restored.runtime_snapshot()
    for filename in ("animals.json", "torpedoes.json", "decoys.json", "acoustics.json"):
        assert roundtrip["components"][filename] == snapshot["components"][filename]
    assert restored.acoustic_profiles == catalog.CATALOG.acoustic_profiles
    assert tuple(restored.animals) == tuple(catalog.CATALOG.animals)
    assert tuple(restored.torpedoes) == tuple(catalog.CATALOG.torpedoes)
    assert tuple(restored.decoys) == tuple(catalog.CATALOG.decoys)
