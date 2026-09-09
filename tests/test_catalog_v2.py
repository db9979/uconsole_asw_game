"""Mixed catalog-v2 registries, provenance, and strict reconstruction contracts."""

import copy
import json
import random
import shutil
from dataclasses import FrozenInstanceError, fields
from importlib import resources

import pytest

from src.data import catalog
from tools.gen_contacts import _same_json, validate


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
    (directory / "sources.json").write_text(
        json.dumps(source_document, indent=2) + "\n", encoding="utf-8")
    return document, source_document, profile_key


def test_packaged_r4_pilot_versions_counts_and_provenance():
    assert {name for name, version in catalog.CATALOG.document_versions.items()
            if version == 2} == {"subs.json", "warships.json", "civilians.json"}
    assert set(catalog.CATALOG.profile_systems) == {
        "warship_01", "warship_02", "warship_25", "warship_26", "warship_27",
        "warship_28", "sub_03", "sub_14", "cargo_05",
    }
    assert len(catalog.CATALOG.references) == len(catalog.CATALOG.machines) == 9
    assert len(catalog.CATALOG.sensors) == 18
    assert len(catalog.CATALOG.emitters) == 7
    assert len(catalog.CATALOG.weapons) == 8
    assert len(catalog.CATALOG.launchers) == 8
    assert len(catalog.CATALOG.magazines) == 8
    assert len(catalog.CATALOG.countermeasures) == 8
    assert len(catalog.CATALOG.sources) == 15
    assert len(catalog.CATALOG.provenance_claims) == 52
    assert len(catalog.CATALOG.subs) + len(catalog.CATALOG.surfaces) \
        + len(catalog.CATALOG.aircraft) + len(catalog.CATALOG.animals) \
        + len(catalog.CATALOG.torpedoes) + len(catalog.CATALOG.decoys) == 115
    assert len(catalog.CATALOG.acoustic_profiles) == 109
    source = resources.files("data.contacts")
    reconstructed = catalog.CATALOG.reconstruct_documents()
    for filename in catalog.CONTACT_FILENAMES:
        assert _same_json(reconstructed[filename], catalog._read_json(source / filename))


def test_r4_pilot_claims_cover_every_component_field():
    expected = set()
    registries = {
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
    assert len(loaded.sources) == 3 and len(loaded.provenance_claims) == 4
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
