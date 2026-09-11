"""Mixed catalog-v2 registries, provenance, and strict reconstruction contracts."""

import copy
import hashlib
import json
import random
import shutil
from dataclasses import FrozenInstanceError, fields
from importlib import resources

import pytest

from src.data import catalog
from tools.gen_contacts import _same_json, validate


GENERIC_SUBMARINE_KEYS = ("diesel_alt", "aip_modern", "ssn")
NAMED_SUBMARINE_KEYS = tuple(f"sub_{index:02d}" for index in range(1, 21))
ALL_SUBMARINE_KEYS = GENERIC_SUBMARINE_KEYS + NAMED_SUBMARINE_KEYS
ALL_WARSHIP_KEYS = tuple(f"warship_{index:02d}" for index in range(1, 29))
ALL_CIVILIAN_KEYS = (
    *(f"tanker_{index:02d}" for index in range(1, 16)),
    *(f"passenger_{index:02d}" for index in range(1, 16)),
    *(f"cargo_{index:02d}" for index in range(1, 16)),
    *(f"aux_{index:02d}" for index in range(1, 11)),
)
ALL_AIRCRAFT_KEYS = ("mil_patrol", "civil_transit")
ALL_ANIMAL_KEYS = ("whale", "fish_school", "jellyfish")
ALL_TORPEDO_KEYS = ("frigate_torp", "helo_torp", "enemy_torp")
ALL_DECOY_KEYS = ("decoy",)


def _copy_catalog(destination):
    source = resources.files("data.contacts")
    for item in source.iterdir():
        if item.name.endswith(".json"):
            shutil.copyfile(item, destination / item.name)


def _downgrade_documents(directory):
    for filename in catalog.CONTACT_FILENAMES:
        path = directory / filename
        document = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps({"version": 1, "entries": document["entries"]}),
                        encoding="utf-8")


def _v2_documents(directory):
    _copy_catalog(directory)
    _downgrade_documents(directory)
    path = directory / "warships.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    profile_key = document["entries"][0]["key"]
    document.update(
        version=2,
        profiles=[{
            "profile_key": profile_key,
            "reference_key": "reference.warship_01",
            "machine_key": "machine.warship_01",
            "sensor_keys": ["sensor.warship_01.radar"],
            "emitter_keys": ["emitter.warship_01.radar"],
            "launcher_keys": ["launcher.warship_01.tubes"],
            "magazine_keys": ["magazine.warship_01.torpedoes"],
            "countermeasure_keys": ["countermeasure.warship_01.decoy"],
        }],
        references=[{
            "key": "reference.warship_01", "variant": "Flight IIA",
            "variant_year": 2000, "refit_year": None, "aliases": ["DDG"],
            "roles": ["air_defense", "anti_submarine"], "hull_type": "destroyer",
            "displacement_tonnes": 9500, "displacement_basis": "full_load",
            "length_m": 155, "beam_waterline_m": 20.0, "beam_overall_m": 20.4,
            "flight_deck_width_m": None, "draft_m": 9.3,
            "ship_crew": [300, 330], "air_group_crew": None,
        }],
        machines=[{
            "key": "machine.warship_01", "cruise_speed_kn": 18,
            "maximum_speed_kn": 30, "quiet_speed_kn": 12,
            "propulsion_codes": ["gas_turbine"], "motor_rpm": None,
            "shaft_rpm": [100, 200], "propulsor_type": "propeller",
            "blade_count": None, "cruise_lines": [[20, 0.4, 1]],
            "high_speed_lines": [[40, 0.6, 2]],
            "cruise_broadband": [0.4, 10, 300],
            "high_speed_broadband": [0.7, 10, 350],
        }],
        sensors=[{
            "key": "sensor.warship_01.radar", "domain": "radar",
            "modes": ["active"], "emits": True,
            "emitter_key": "emitter.warship_01.radar", "synthetic_range_nm": 250,
            "sensitivity_db": -90, "cadence_s": 2,
            "bearing_uncertainty_deg": 1, "range_uncertainty_nm": 0.2,
            "depth_uncertainty_m": None,
        }],
        emitters=[{
            "key": "emitter.warship_01.radar", "domain": "radar",
            "frequency_band_hz": [8_000_000_000, 12_000_000_000],
            "prf_band_hz": None, "modulation_codes": ["unknown"],
        }],
        weapons=[{
            "key": "weapon.lightweight_torpedo", "weapon_type": "torpedo",
            "target_domains": ["subsurface"], "runtime_profile_key": "frigate_torp",
            "maximum_speed_kn": 45, "engagement_range_nm": [0, 12],
            "seeker_type": "acoustic_active", "guidance_type": "homing",
            "payload_type": "high_explosive",
        }],
        launchers=[{
            "key": "launcher.warship_01.tubes", "launcher_type": "torpedo_tube",
            "mount_count": 2, "ready_count": 2, "reload_s": 30,
            "arc_center_deg": 0, "arc_width_deg": 360, "vls_cells": None,
            "weapon_keys": ["weapon.lightweight_torpedo"],
        }],
        magazines=[{
            "key": "magazine.warship_01.torpedoes",
            "weapon_key": "weapon.lightweight_torpedo",
            "mission_count": 8,
        }],
        countermeasures=[{
            "key": "countermeasure.warship_01.decoy", "effect_type": "acoustic_decoy",
            "payload_key": "decoy", "mission_count": 8, "ready_count": 2,
            "reload_s": 30,
        }],
    )
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    source_document = {
        "version": 1,
        "sources": [
            {"id": "source.public", "kind": "public_source", "title": "Public fact sheet",
             "publisher": "Public publisher", "url": "https://example.com/fact-sheet",
             "reference": "2000 baseline", "retrieved": "2026-09-08", "license": None},
            {"id": "source.manufacturer", "kind": "manufacturer", "title": "Product page",
             "publisher": "Example builder", "url": "https://example.com/product",
             "reference": "Public page", "retrieved": "2026-09-08", "license": None},
            {"id": "u-jagd.game-model", "kind": "game_assumption",
             "title": "U-Jagd synthetic gameplay model", "publisher": None, "url": None,
             "reference": "0.1.7", "retrieved": None, "license": "MIT"},
        ],
        "claims": [
            {"resource": "warships.json", "profile_key": profile_key,
             "field_paths": ["/reference/length_m", "/reference/ship_crew"],
             "status": "published", "source_ids": ["source.public", "source.manufacturer"]},
            {"resource": "warships.json", "profile_key": profile_key,
             "field_paths": ["/reference/displacement_tonnes"], "status": "derived",
             "source_ids": ["source.public"]},
            {"resource": "warships.json", "profile_key": profile_key,
             "field_paths": ["/machine/cruise_lines"], "status": "game_assumption",
             "source_ids": ["u-jagd.game-model"]},
            {"resource": "warships.json", "profile_key": profile_key,
             "field_paths": ["/reference/flight_deck_width_m"], "status": "unknown",
             "source_ids": []},
        ],
    }
    claimed = {path for claim in source_document["claims"]
               for path in claim["field_paths"]}
    components = [
        ("reference", document["references"][0]),
        ("machine", document["machines"][0]),
    ]
    for registry in ("sensors", "emitters", "weapons", "launchers",
                     "magazines", "countermeasures"):
        components.extend((f"{registry}/{component['key']}", component)
                          for component in document[registry])
    missing = {"game_assumption": [], "unknown": []}
    for prefix, component in components:
        for field, value in component.items():
            field_path = f"/{prefix}/{field}"
            if field != "key" and field_path not in claimed:
                missing["unknown" if value is None else "game_assumption"].append(
                    field_path)
    for status, field_paths in missing.items():
        if field_paths:
            source_document["claims"].append({
                "resource": "warships.json", "profile_key": profile_key,
                "field_paths": field_paths, "status": status,
                "source_ids": ([] if status == "unknown"
                               else ["u-jagd.game-model"]),
            })
    (directory / "sources.json").write_text(
        json.dumps(source_document, indent=2) + "\n", encoding="utf-8")
    return document, source_document, profile_key


def test_packaged_migration_versions_counts_and_provenance():
    assert {name for name, version in catalog.CATALOG.document_versions.items()
            if version == 2} == set(catalog.CONTACT_FILENAMES)
    assert set(catalog.CATALOG.profile_systems) == set(
        ALL_SUBMARINE_KEYS) | set(ALL_WARSHIP_KEYS) | set(ALL_CIVILIAN_KEYS) \
        | set(ALL_AIRCRAFT_KEYS) | set(ALL_ANIMAL_KEYS) \
        | set(ALL_TORPEDO_KEYS) | set(ALL_DECOY_KEYS)
    assert len(catalog.CATALOG.references) == len(catalog.CATALOG.machines) == 115
    assert len(catalog.CATALOG.sensors) == 216
    assert len(catalog.CATALOG.emitters) == 85
    assert len(catalog.CATALOG.weapons) == 51
    assert len(catalog.CATALOG.launchers) == 51
    assert len(catalog.CATALOG.magazines) == 51
    assert len(catalog.CATALOG.countermeasures) == 51
    assert len(catalog.CATALOG.sources) == 15
    assert len(catalog.CATALOG.provenance_claims) == 366
    assert len(catalog.CATALOG.subs) + len(catalog.CATALOG.surfaces) \
        + len(catalog.CATALOG.aircraft) + len(catalog.CATALOG.animals) \
        + len(catalog.CATALOG.torpedoes) + len(catalog.CATALOG.decoys) == 115
    assert len(catalog.CATALOG.acoustic_profiles) == 109
    source = resources.files("data.contacts")
    reconstructed = catalog.CATALOG.reconstruct_documents()
    for filename in catalog.CONTACT_FILENAMES:
        assert _same_json(reconstructed[filename], catalog._read_json(source / filename))


def test_r10_batch1_migrates_every_submarine_in_legacy_order():
    assert tuple(catalog.CATALOG.subs) == ALL_SUBMARINE_KEYS
    assert tuple(key for key in catalog.CATALOG.profile_systems
                 if key in catalog.CATALOG.subs) == ALL_SUBMARINE_KEYS
    assert tuple(key for key in catalog.CATALOG.subs
                 if not key.startswith("sub_")) == GENERIC_SUBMARINE_KEYS

    for key in ALL_SUBMARINE_KEYS:
        systems = catalog.CATALOG.profile_systems[key]
        assert systems.reference_key == f"reference.{key}"
        assert systems.machine_key == f"machine.{key}"
        assert systems.sensor_keys == (f"sensor.{key}.sonar", f"sensor.{key}.esm")
        assert systems.emitter_keys == ()
        assert systems.launcher_keys == (f"launcher.{key}.tubes",)
        assert systems.magazine_keys == (f"magazine.{key}.torpedoes",)
        assert systems.countermeasure_keys == (f"countermeasure.{key}.decoy",)


def test_r10_batch1_keeps_legacy_entries_and_spawn_selection_stable():
    entries = catalog.CATALOG.reconstruct_documents()["subs.json"]["entries"]
    assert tuple(entry["key"] for entry in entries) == ALL_SUBMARINE_KEYS
    encoded = json.dumps(
        entries, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert hashlib.sha256(encoded).hexdigest() == \
        "25a51032dcba8956ede1ff4d09cba539ec14c84a226033b2e9165f59f166f5d9"
    assert [catalog.CATALOG.pick_sub(random.Random(seed)).key for seed in range(20)] == [
        "sub_17", "aip_modern", "sub_19", "sub_01", "sub_01", "sub_11",
        "sub_15", "sub_03", "sub_01", "sub_07", "sub_10", "sub_06",
        "sub_07", "sub_02", "aip_modern", "sub_20", "sub_04", "sub_08",
        "ssn", "sub_12",
    ]


def test_r10_batch2_migrates_every_warship_in_legacy_order():
    assert tuple(profile.key for profile in catalog.CATALOG.hostile_surfaces) == \
        ALL_WARSHIP_KEYS
    assert tuple(key for key in catalog.CATALOG.profile_systems
                 if key in ALL_WARSHIP_KEYS) == ALL_WARSHIP_KEYS

    for key in ALL_WARSHIP_KEYS:
        systems = catalog.CATALOG.profile_systems[key]
        assert systems.reference_key == f"reference.{key}"
        assert systems.machine_key == f"machine.{key}"
        assert systems.sensor_keys == (f"sensor.{key}.radar", f"sensor.{key}.sonar")
        assert systems.emitter_keys == (f"emitter.{key}.radar",)
        assert systems.countermeasure_keys == (f"countermeasure.{key}.softkill",)
    for key in ALL_WARSHIP_KEYS[2:24]:
        systems = catalog.CATALOG.profile_systems[key]
        assert systems.launcher_keys == (f"launcher.{key}.asm",)
        assert systems.magazine_keys == (f"magazine.{key}.asm",)


def test_r10_batch2_keeps_warship_entries_and_spawn_selection_stable():
    entries = catalog.CATALOG.reconstruct_documents()["warships.json"]["entries"]
    assert tuple(entry["key"] for entry in entries) == ALL_WARSHIP_KEYS
    encoded = json.dumps(
        entries, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert hashlib.sha256(encoded).hexdigest() == \
        "21c4f75329d1afd209bf1b79c0f59d32cc58847910fca408f7e8d0570e8bfd0d"
    assert [catalog.CATALOG.pick_surface(random.Random(seed), hostile=True).key
            for seed in range(10)] == [
        "warship_22", "warship_04", "warship_24", "warship_06", "warship_06",
        "warship_16", "warship_20", "warship_09", "warship_06", "warship_12",
    ]


def test_r10_batch3_migrates_every_civilian_in_legacy_order_without_armament():
    assert tuple(profile.key for profile in catalog.CATALOG.civilian_surfaces) == \
        ALL_CIVILIAN_KEYS
    assert tuple(key for key in catalog.CATALOG.profile_systems
                 if key in ALL_CIVILIAN_KEYS) == ALL_CIVILIAN_KEYS

    for key in ALL_CIVILIAN_KEYS:
        systems = catalog.CATALOG.profile_systems[key]
        assert systems.reference_key == f"reference.{key}"
        assert systems.machine_key == f"machine.{key}"
        assert systems.sensor_keys == (f"sensor.{key}.radar", f"sensor.{key}.ais")
        assert systems.emitter_keys == (f"emitter.{key}.radar",)
        assert systems.launcher_keys == systems.magazine_keys == \
            systems.countermeasure_keys == ()
    document = catalog.CATALOG.reconstruct_documents()["civilians.json"]
    assert document["weapons"] == document["launchers"] == \
        document["magazines"] == document["countermeasures"] == []


def test_r10_batch3_keeps_civilian_entries_and_spawn_selection_stable():
    entries = catalog.CATALOG.reconstruct_documents()["civilians.json"]["entries"]
    assert tuple(entry["key"] for entry in entries) == ALL_CIVILIAN_KEYS
    encoded = json.dumps(
        entries, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert hashlib.sha256(encoded).hexdigest() == \
        "5ac1e45fd372942f2979472f89fdb51dd6d6729bfe85b11110a07b3df8d9ca1d"
    assert [catalog.CATALOG.pick_surface(random.Random(seed)).key
            for seed in range(20)] == [
        "aux_02", "tanker_08", "aux_08", "tanker_14", "tanker_13",
        "cargo_05", "cargo_14", "passenger_03", "tanker_13", "passenger_11",
        "cargo_02", "passenger_10", "passenger_12", "tanker_15", "tanker_06",
        "aux_09", "passenger_05", "passenger_14", "tanker_10", "cargo_08",
    ]


def test_r10_batch3_preserves_explicitly_generic_panamax_archetype():
    reference = catalog.CATALOG.references["reference.cargo_05"]
    assert reference.variant == "Generic Panamax container-ship archetype"
    assert reference.aliases == ("Panamax container ship",)
    assert reference.hull_type == "container_ship"


def test_r10_batch4_migrates_every_aircraft_in_legacy_order_without_armament():
    assert tuple(catalog.CATALOG.aircraft) == ALL_AIRCRAFT_KEYS
    assert tuple(key for key in catalog.CATALOG.profile_systems
                 if key in catalog.CATALOG.aircraft) == ALL_AIRCRAFT_KEYS
    expected_sensors = {
        "mil_patrol": ("sensor.mil_patrol.radar", "sensor.mil_patrol.esm"),
        "civil_transit": (
            "sensor.civil_transit.radar", "sensor.civil_transit.ais"),
    }
    for key in ALL_AIRCRAFT_KEYS:
        systems = catalog.CATALOG.profile_systems[key]
        assert systems.reference_key == f"reference.{key}"
        assert systems.machine_key == f"machine.{key}"
        assert systems.sensor_keys == expected_sensors[key]
        assert systems.emitter_keys == (f"emitter.{key}.radar",)
        assert systems.launcher_keys == systems.magazine_keys == \
            systems.countermeasure_keys == ()
    document = catalog.CATALOG.reconstruct_documents()["aircraft.json"]
    assert document["weapons"] == document["launchers"] == \
        document["magazines"] == document["countermeasures"] == []


def test_r10_batch4_keeps_aircraft_entries_and_spawn_selection_stable():
    entries = catalog.CATALOG.reconstruct_documents()["aircraft.json"]["entries"]
    assert tuple(entry["key"] for entry in entries) == ALL_AIRCRAFT_KEYS
    encoded = json.dumps(
        entries, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert hashlib.sha256(encoded).hexdigest() == \
        "ec0d82921231f2535cdf8be96286026804f8cb504472cb8ec818a9693eccfc38"
    assert [catalog.CATALOG.pick_aircraft(random.Random(seed), "military").key
            for seed in range(10)] == ["mil_patrol"] * 10
    assert [catalog.CATALOG.pick_aircraft(random.Random(seed), "civil").key
            for seed in range(10)] == ["civil_transit"] * 10


def test_r10_batch5_migrates_only_applicable_components_in_legacy_order():
    families = {
        "animals.json": ALL_ANIMAL_KEYS,
        "torpedoes.json": ALL_TORPEDO_KEYS,
        "decoys.json": ALL_DECOY_KEYS,
    }
    documents = catalog.CATALOG.reconstruct_documents()
    for filename, keys in families.items():
        assert tuple(item["key"] for item in documents[filename]["entries"]) == keys
        assert tuple(item["profile_key"] for item in documents[filename]["profiles"]) == keys
        assert documents[filename]["sensors"] == documents[filename]["emitters"] == []
        assert documents[filename]["weapons"] == documents[filename]["launchers"] == []
        assert documents[filename]["magazines"] == documents[filename]["countermeasures"] == []
        for key in keys:
            systems = catalog.CATALOG.profile_systems[key]
            assert systems.reference_key == f"reference.{key}"
            assert systems.machine_key == f"machine.{key}"
            assert systems.sensor_keys == systems.emitter_keys == ()
            assert systems.launcher_keys == systems.magazine_keys == \
                systems.countermeasure_keys == ()
            assert catalog.CATALOG.machines[systems.machine_key].propulsor_type == "unknown"

    library = documents["acoustics.json"]
    assert tuple(item["key"] for item in library["entries"]) == ("animal", "decoy")
    assert all(library.get(field, []) == [] for field, _ in catalog.V2_REGISTRIES)


def test_r10_batch5_keeps_entries_and_animal_selection_stable():
    expected_hashes = {
        "animals.json": "cadf35eb577b40c7c8423d34efe1508649af243dace298db692b745fb6b2f013",
        "torpedoes.json": "5cc7e61090a804829a847eaae19e04710ec4faac4275c6b0cac6f46b33b29874",
        "decoys.json": "ff0670aca47965e350a64a3b41a9912316e20bb73888888a58b4fe59e8b04c9a",
        "acoustics.json": "7ce16f23502f8ddf140e96d6b105117a1ac83eccd2a5e2a2f5c33fc3f947eb01",
    }
    documents = catalog.CATALOG.reconstruct_documents()
    for filename, expected in expected_hashes.items():
        encoded = json.dumps(
            documents[filename]["entries"], ensure_ascii=False,
            separators=(",", ":")).encode("utf-8")
        assert hashlib.sha256(encoded).hexdigest() == expected
    assert [catalog.CATALOG.pick_animal(random.Random(seed)).key
            for seed in range(10)] == [
                "jellyfish", "whale", "jellyfish", "whale", "whale",
                "fish_school", "jellyfish", "whale", "whale", "fish_school",
            ]


def test_migrated_claims_cover_every_component_field():
    expected = set()
    registries = {
        "endurances": catalog.CATALOG.endurances,
        "sensors": catalog.CATALOG.sensors,
        "emitters": catalog.CATALOG.emitters,
        "launchers": catalog.CATALOG.launchers,
        "magazines": catalog.CATALOG.magazines,
        "countermeasures": catalog.CATALOG.countermeasures,
    }
    for profile_key, systems in catalog.CATALOG.profile_systems.items():
        resource = catalog.CATALOG.profile_resources[profile_key]
        reference = catalog.CATALOG.references[systems.reference_key]
        machine = catalog.CATALOG.machines[systems.machine_key]
        expected.update((resource, profile_key, f"/reference/{field.name}")
                        for field in fields(reference) if field.name != "key")
        expected.update((resource, profile_key, f"/machine/{field.name}")
                        for field in fields(machine) if field.name != "key")
        for registry_name, keys in (
                ("endurances", ((f"endurance.{profile_key}",)
                                if f"endurance.{profile_key}" in
                                catalog.CATALOG.endurances else ())),
                ("sensors", systems.sensor_keys),
                ("emitters", systems.emitter_keys),
                ("launchers", systems.launcher_keys),
                ("magazines", systems.magazine_keys),
                ("countermeasures", systems.countermeasure_keys)):
            for key in keys:
                component = registries[registry_name][key]
                expected.update((resource, profile_key,
                                 f"/{registry_name}/{key}/{field.name}")
                                for field in fields(component) if field.name != "key")
        weapon_keys = {
            weapon_key for launcher_key in systems.launcher_keys
            for weapon_key in catalog.CATALOG.launchers[launcher_key].weapon_keys
        } | {
            catalog.CATALOG.magazines[key].weapon_key for key in systems.magazine_keys
        }
        for key in weapon_keys:
            component = catalog.CATALOG.weapons[key]
            expected.update((resource, profile_key, f"/weapons/{key}/{field.name}")
                            for field in fields(component) if field.name != "key")
        if resource not in ("animals.json", "torpedoes.json", "decoys.json"):
            assert max(line.relative_level for line in machine.cruise_lines) == 1.0
            assert max(line.relative_level for line in machine.high_speed_lines) == 1.0
        assert all(0 <= line.relative_level <= 1 for line in (
            *machine.cruise_lines, *machine.high_speed_lines))
    claimed = {
        (claim.resource, claim.profile_key, path)
        for claim in catalog.CATALOG.provenance_claims for path in claim.field_paths
    }
    assert claimed == expected
    assert not any(
        "waveops" in " ".join(filter(None, (
            source.id, source.title, source.publisher, source.url))).lower()
        or "mnw" in " ".join(filter(None, (
            source.id, source.title, source.publisher, source.url))).lower()
        for source in catalog.CATALOG.sources.values())


def test_r4_pilot_capacity_and_mission_load_are_separate_and_not_runtime_effective():
    expected = {
        "warship_01": (96, 8), "warship_02": (122, 8),
        "warship_25": (112, 8), "warship_26": (64, 8),
    }
    for profile_key, (cells, mission_count) in expected.items():
        systems = catalog.CATALOG.profile_systems[profile_key]
        launcher = catalog.CATALOG.launchers[systems.launcher_keys[0]]
        magazine = catalog.CATALOG.magazines[systems.magazine_keys[0]]
        assert launcher.vls_cells == cells
        assert magazine.mission_count == mission_count < cells
    assert catalog.CATALOG.profile_systems["warship_27"].launcher_keys == (
        "launcher.warship_27.ciws",)
    assert catalog.CATALOG.profile_systems["warship_28"].launcher_keys == (
        "launcher.warship_28.sam",)


def test_r4_new_profiles_are_appended_without_changing_legacy_spawn_pool():
    assert [profile.key for profile in catalog.CATALOG.hostile_surfaces][-3:] == [
        "warship_26", "warship_27", "warship_28",
    ]
    assert [profile.key for profile in catalog.CATALOG.legacy_hostile_surfaces] == [
        f"warship_{index:02d}" for index in range(1, 26)
    ]
    assert [catalog.CATALOG.pick_surface(random.Random(seed), hostile=True).key
            for seed in range(10)] == [
        "warship_22", "warship_04", "warship_24", "warship_06", "warship_06",
        "warship_16", "warship_20", "warship_09", "warship_06", "warship_12",
    ]
    assert all(catalog.CATALOG.surfaces[key].spawn_weight == 0 for key in (
        "warship_26", "warship_27", "warship_28"))


def test_r4_legacy_runtime_profiles_remain_unchanged_and_new_data_is_conservative():
    expected = {
        "warship_01": ((12.0, 28.0), (186.0, 686.0), 0.51),
        "warship_02": ((12.0, 28.0), (193.0, 693.0), 0.55),
        "warship_25": ((12.0, 28.0), (214.0, 714.0), 0.51),
    }
    for key, values in expected.items():
        profile = catalog.CATALOG.surfaces[key]
        assert (profile.speed_kn, profile.acoustic.rpm_range,
                profile.acoustic.cavitation_tendency) == values
    for key in ("sub_03", "sub_14"):
        profile = catalog.CATALOG.subs[key]
        assert (profile.speed_kn, profile.max_depth_m, profile.torpedoes,
                profile.acoustic.rpm_range) == ((14.0, 18.0), 400.0, 8, (120.0, 360.0))
    cargo = catalog.CATALOG.surfaces["cargo_05"]
    assert (cargo.speed_kn, cargo.acoustic.rpm_range,
            cargo.acoustic.cavitation_tendency) == ((12.0, 20.0), (114.0, 514.0), 0.78)
    type_052d = catalog.CATALOG.references["reference.warship_26"]
    assert (type_052d.beam_waterline_m, type_052d.draft_m) == (17.2, 6.2)
    nimitz = catalog.CATALOG.references["reference.warship_28"]
    assert (nimitz.displacement_tonnes, nimitz.length_m,
            nimitz.ship_crew, nimitz.air_group_crew) == (None, None, None, None)


def test_mixed_v1_v2_catalog_loads_immutable_registries_and_reconstructs_exactly(tmp_path):
    expected, expected_sources, profile_key = _v2_documents(tmp_path)
    loaded = validate(tmp_path)

    assert loaded.document_versions["warships.json"] == 2
    assert all(version == 1 for name, version in loaded.document_versions.items()
               if name != "warships.json")
    systems = loaded.profile_systems[profile_key]
    assert systems.reference_key == "reference.warship_01"
    assert loaded.references[systems.reference_key].length_m == 155.0
    assert loaded.machines[systems.machine_key].cruise_lines[0].relative_level == 0.4
    assert loaded.sensors[systems.sensor_keys[0]].sensitivity_db == -90.0
    assert loaded.emitters[systems.emitter_keys[0]].prf_band_hz is None
    assert loaded.weapons["weapon.lightweight_torpedo"].runtime_profile_key == "frigate_torp"
    assert loaded.launchers[systems.launcher_keys[0]].weapon_keys == ("weapon.lightweight_torpedo",)
    assert loaded.magazines[systems.magazine_keys[0]].mission_count == 8
    assert loaded.countermeasures[systems.countermeasure_keys[0]].payload_key == "decoy"
    assert len(loaded.sources) == 3
    assert len(loaded.provenance_claims) == len(expected_sources["claims"])
    reconstructed = loaded.reconstruct_documents()["warships.json"]
    assert _same_json(reconstructed, expected)
    assert type(reconstructed["references"][0]["length_m"]) is int
    assert _same_json(loaded.reconstruct_provenance(), expected_sources)
    reconstructed["references"][0]["length_m"] = 1
    assert loaded.reconstruct_documents()["warships.json"]["references"][0]["length_m"] == 155
    with pytest.raises(TypeError):
        loaded.references["other"] = loaded.references[systems.reference_key]
    with pytest.raises(FrozenInstanceError):
        loaded.references[systems.reference_key].length_m = 1


def test_v2_requires_manifest_but_all_v1_external_catalog_does_not(tmp_path):
    _copy_catalog(tmp_path)
    _downgrade_documents(tmp_path)
    (tmp_path / "sources.json").unlink()
    assert catalog._load_catalog_from(tmp_path).document_versions["warships.json"] == 1
    document = json.loads((tmp_path / "warships.json").read_text(encoding="utf-8"))
    document.update(version=2, profiles=[], references=[], machines=[], sensors=[], emitters=[],
                    weapons=[], launchers=[], magazines=[], countermeasures=[])
    (tmp_path / "warships.json").write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="sources.json"):
        catalog._load_catalog_from(tmp_path)


@pytest.mark.parametrize(("target", "mutate", "message"), [
    ("document", lambda d: d.update(extra=True), "unknown fields"),
    ("document", lambda d: d["references"][0].update(length_m=True), "number"),
    ("document", lambda d: d["profiles"][0].update(reference_key="reference.missing"), "unknown references"),
    ("document", lambda d: d["sensors"][0].update(emitter_key="emitter.missing"), "emitter"),
    ("document", lambda d: d["launchers"][0].update(weapon_keys=["weapon.missing"]), "weapon"),
    ("document", lambda d: d["weapons"][0].update(key="sensor.wrong"), "logical key"),
    ("document", lambda d: d["sensors"][0].update(emits=False), "emission state"),
    ("document", lambda d: d["profiles"][0].update(launcher_keys=[]), "compatible launcher"),
    ("document", lambda d: d["countermeasures"][0].update(payload_key="../decoy"), "logical key"),
    ("document", lambda d: d["entries"][0].update(key="../warship"), "logical key"),
    ("document", lambda d: d["weapons"][0].update(weapon_type="sam"), "only torpedoes"),
    ("document", lambda d: d["launchers"][0].update(launcher_type="ciws"), "incompatible weapon"),
    ("document", lambda d: d["launchers"][0].update(weapon_keys=[]), "non-empty array"),
    ("document", lambda d: d["launchers"][0].update(
        launcher_type="vls", vls_cells=0), "number outside"),
    ("sources", lambda d: d["sources"][0].update(url="file:///etc/passwd"), "HTTPS URL"),
    ("sources", lambda d: d["claims"][0].update(resource="../warships.json"), "resource"),
    ("sources", lambda d: d["claims"][0].update(field_paths=["/reference/../length_m"]), "field path"),
    ("sources", lambda d: d["claims"][0].update(source_ids=["u-jagd.game-model"]), "public sources"),
    ("sources", lambda d: d["claims"][3].update(source_ids=["source.public"]), "cannot cite"),
    ("sources", lambda d: d["claims"][3].update(
        status="published", source_ids=["source.public"]), "cannot reference null"),
])
def test_v2_rejects_unknown_typed_unresolved_and_hostile_values(
        tmp_path, target, mutate, message):
    document, source_document, _ = _v2_documents(tmp_path)
    changed = copy.deepcopy(document if target == "document" else source_document)
    mutate(changed)
    filename = "warships.json" if target == "document" else "sources.json"
    (tmp_path / filename).write_text(json.dumps(changed, allow_nan=True), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        catalog._load_catalog_from(tmp_path)
    assert catalog.load_catalog(tmp_path, quiet=True).subs == catalog.CATALOG.subs


def test_batch5_rejects_platform_components_for_library_animals_and_decoys(tmp_path):
    _copy_catalog(tmp_path)
    animal_path = tmp_path / "animals.json"
    document = json.loads(animal_path.read_text(encoding="utf-8"))
    document["sensors"] = [{
        "key": "sensor.whale.sonar", "domain": "sonar", "modes": ["passive"],
        "emits": False, "emitter_key": None, "synthetic_range_nm": 1,
        "sensitivity_db": 0, "cadence_s": 1, "bearing_uncertainty_deg": 1,
        "range_uncertainty_nm": None, "depth_uncertainty_m": None,
    }]
    document["profiles"][0]["sensor_keys"] = ["sensor.whale.sonar"]
    animal_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="reference and machine only"):
        catalog._load_catalog_from(tmp_path)

    _copy_catalog(tmp_path)
    library_path = tmp_path / "acoustics.json"
    document = json.loads(library_path.read_text(encoding="utf-8"))
    document["profiles"] = [copy.deepcopy(
        json.loads((tmp_path / "decoys.json").read_text(encoding="utf-8"))["profiles"][0])]
    document["profiles"][0]["profile_key"] = "animal"
    library_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="library signatures"):
        catalog._load_catalog_from(tmp_path)


def test_batch5_rejects_operational_components_for_torpedoes(tmp_path):
    _copy_catalog(tmp_path)
    path = tmp_path / "torpedoes.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["sensors"] = [{
        "key": "sensor.torpedo.radar", "domain": "sonar", "modes": ["passive"],
        "emits": False, "emitter_key": None, "synthetic_range_nm": 1,
        "sensitivity_db": 0, "cadence_s": 1, "bearing_uncertainty_deg": 1,
        "range_uncertainty_nm": 1, "depth_uncertainty_m": None,
    }]
    document["profiles"][0]["sensor_keys"] = ["sensor.torpedo.radar"]
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="reference and machine only"):
        catalog._load_catalog_from(tmp_path)


def test_shared_loader_rejects_incomplete_provenance_coverage(tmp_path):
    _copy_catalog(tmp_path)
    path = tmp_path / "sources.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["claims"][0]["field_paths"].pop()
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="incomplete field coverage"):
        catalog._load_catalog_from(tmp_path)


def test_shared_loader_rejects_empty_provenance_for_v2_catalog(tmp_path):
    _copy_catalog(tmp_path)
    path = tmp_path / "sources.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["sources"] = []
    document["claims"] = []
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="incomplete field coverage"):
        catalog._load_catalog_from(tmp_path)


def test_v2_duplicate_members_are_rejected_at_nested_levels(tmp_path):
    _v2_documents(tmp_path)
    path = tmp_path / "sources.json"
    text = path.read_text(encoding="utf-8").replace(
        '"title": "Public fact sheet"',
        '"title": "Public fact sheet", "title": "duplicate"', 1)
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON key"):
        catalog._load_catalog_from(tmp_path)


@pytest.mark.parametrize("url", [
    "https://localhost./source", "https://127.1/source", "https://2130706433/source",
    "https://intranet/source", "https://./source", "https://example.com:bad/source",
    "https://source.local/page", "https://source.home.arpa/page",
    "https://127.0.0.1.nip.io/page",
])
def test_v2_source_urls_must_have_public_https_authorities(tmp_path, url):
    _, source_document, _ = _v2_documents(tmp_path)
    source_document["sources"][0]["url"] = url
    (tmp_path / "sources.json").write_text(json.dumps(source_document), encoding="utf-8")
    with pytest.raises(ValueError, match="public HTTPS URL"):
        catalog._load_catalog_from(tmp_path)


@pytest.mark.parametrize(("registry", "key"), [
    ("references", "machine.wrong"), ("machines", "reference.wrong"),
    ("sensors", "emitter.wrong"), ("emitters", "sensor.wrong"),
    ("weapons", "launcher.wrong"), ("launchers", "magazine.wrong"),
    ("magazines", "countermeasure.wrong"), ("countermeasures", "reference.wrong"),
    ("references", "reference."), ("machines", "machine..wrong"),
    ("sensors", "sensor.-wrong"),
])
def test_v2_component_keys_enforce_namespaces(tmp_path, registry, key):
    document, _, _ = _v2_documents(tmp_path)
    document[registry][0]["key"] = key
    (tmp_path / "warships.json").write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="logical key"):
        catalog._load_catalog_from(tmp_path)


def test_catalog_documents_have_byte_and_entry_limits(tmp_path):
    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b" " * (catalog.MAX_CATALOG_DOCUMENT_BYTES + 1))
    with pytest.raises(ValueError, match="size limit"):
        catalog._read_json(oversized)

    nested = tmp_path / "nested.json"
    nested.write_text("[" * 100_000 + "0" + "]" * 100_000, encoding="utf-8")
    with pytest.raises(ValueError, match="nesting limit"):
        catalog._read_json(nested)

    _copy_catalog(tmp_path)
    document = json.loads((tmp_path / "subs.json").read_text(encoding="utf-8"))
    document["entries"] = [document["entries"][0]] * (catalog.MAX_CATALOG_ENTRIES + 1)
    (tmp_path / "subs.json").write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="bounded non-empty"):
        catalog._load_catalog_from(tmp_path)
