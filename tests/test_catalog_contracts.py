"""Strict JSON acceptance, lossless loading, and deliberately limited field effects."""

import copy
import json
import random
import shutil
from dataclasses import replace
from importlib import resources

import pytest

from src.data import catalog, fingerprint
from src.data.user_content import UserContentStore
from src.data.validation import ContentValidationError
from src.ui.unit_editor import (PROFILE_KINDS, UnitDefinition, catalog_builtins,
                                default_unit, unit_field_metadata, validate_unit)
from tools.gen_contacts import validate


@pytest.fixture
def contact_dir(tmp_path):
    for filename in catalog.CONTACT_FIELDS:
        shutil.copyfile(resources.files("data.contacts") / filename, tmp_path / filename)
    return tmp_path


def _edit(directory, filename, mutate):
    path = directory / filename
    document = json.loads(path.read_text(encoding="utf-8"))
    mutate(document)
    path.write_text(json.dumps(document, allow_nan=True), encoding="utf-8")


@pytest.mark.parametrize("version", [None, True, False, "1", 1.0, 0, -1, 2])
def test_runtime_and_tool_reject_invalid_versions(contact_dir, version):
    _edit(contact_dir, "subs.json", lambda d: d.update(version=version))
    for loader in (catalog._load_catalog_from, validate):
        with pytest.raises(ValueError, match="version"):
            loader(contact_dir)


@pytest.mark.parametrize("filename", catalog.CONTACT_FIELDS)
def test_required_fields_cannot_be_replaced_by_loader_defaults(filename):
    source = resources.files("data.contacts") / filename
    with source.open("r", encoding="utf-8") as stream:
        entry = json.load(stream)["entries"][0]
    for field in catalog.CONTACT_FIELDS[filename]:
        incomplete = copy.deepcopy(entry)
        del incomplete[field]
        with pytest.raises(ValueError, match="missing fields"):
            catalog.validate_contact_entry(filename, incomplete)


@pytest.mark.parametrize(("filename", "field", "value"), [
    ("subs.json", "quiet", value) for value in (True, "0.8", None, -0.1, 1.1,
                                                 float("nan"), float("inf"), 10**400)
] + [
    ("subs.json", "torpedoes", 4.5),
    ("subs.json", "torpedoes", False),
    ("subs.json", "torpedoes", -1),
    ("subs.json", "max_depth_m", 0),
    ("subs.json", "speed_kn", [12, 6]),
    ("subs.json", "speed_kn", [6, 6]),
    ("subs.json", "speed_kn", [6, 12, 20]),
    ("subs.json", "speed_kn", "12"),
    ("subs.json", "spawn_weight", -1),
    ("subs.json", "unknown", 1),
    ("subs.json", "key", 123),
    ("subs.json", "name", {}),
    ("warships.json", "hostile", "false"),
    ("warships.json", "hostile", False),
    ("warships.json", "category", []),
    ("warships.json", "callsigns", [4]),
    ("warships.json", "asm_salvo", [1.5, 2]),
    ("warships.json", "asm_cooldown_s", -1),
    ("civilians.json", "esm_prob", 2),
    ("aircraft.json", "kind", {}),
    ("aircraft.json", "esm", 1),
    ("aircraft.json", "loiter_nm", [5, 1]),
    ("aircraft.json", "esm_range_nm", float("inf")),
    ("animals.json", "depth_min", 2000),
    ("animals.json", "size_nm", 0),
    ("animals.json", "lines", [[10, 1, 0]]),
    ("torpedoes.json", "used_by", []),
    ("torpedoes.json", "range_nm", -1),
    ("torpedoes.json", "hit_dist_nm", 0),
    ("torpedoes.json", "acoustic", None),
    ("decoys.json", "chance", 1.01),
    ("decoys.json", "life_s", 0),
    ("decoys.json", "lines", [[20, 2, 1]]),
])
def test_runtime_and_tool_reject_invalid_fields(contact_dir, filename, field, value):
    _edit(contact_dir, filename, lambda d: d["entries"][0].update({field: value}))
    for loader in (catalog._load_catalog_from, validate):
        with pytest.raises(ValueError):
            loader(contact_dir)
    assert catalog.load_catalog(contact_dir, quiet=True).subs == catalog.CATALOG.subs


@pytest.mark.parametrize(("field", "value"), [
    ("blades", [True]), ("blades", [5.0]), ("blades", [0]), ("blades", [5, 5]),
    ("rpm_range", [1, 1]), ("rpm_range", [float("nan"), 10]),
    ("tonal_band_hz", [-1, 10]), ("tonal_band_hz", [20, 10]),
    ("broadband", [True, 10, 20]), ("broadband", [0.5, 20, 10]),
    ("broadband", [0.5, 0, 10]), ("broadband", [0.5, 10]),
    ("secondary_tonals", [[10, 0.5, -1]]), ("secondary_tonals", [[10, 0.5]]),
    ("category", "FAHRZEUG"), ("propulsion", "unknown"),
    ("cavitation_tendency", "0.5"), ("key", "ignored"), ("unknown", 1),
])
def test_runtime_and_tool_reject_invalid_acoustics(contact_dir, field, value):
    _edit(contact_dir, "subs.json",
          lambda d: d["entries"][0]["acoustic"].update({field: value}))
    for loader in (catalog._load_catalog_from, validate):
        with pytest.raises(ValueError):
            loader(contact_dir)


@pytest.mark.parametrize("raw", [
    '{"version": 1, "version": 1, "entries": []}',
    '{"version": 1, "entries": [{"key": "a", "key": "a"}]}',
    '{"version": 1, "entries": [{"acoustic": {"blades": [], "blades": []}}]}',
    '[]', '{"entries": []}', '{"version": 1, "entries": [], "extra": 0}',
])
def test_runtime_and_tool_reject_duplicate_members_and_bad_envelopes(contact_dir, raw):
    (contact_dir / "subs.json").write_text(raw, encoding="utf-8")
    for loader in (catalog._load_catalog_from, validate):
        with pytest.raises(ValueError):
            loader(contact_dir)


@pytest.mark.parametrize("collision", ["same_file", "cross_file", "library"])
def test_profile_ids_cannot_silently_overwrite(contact_dir, collision):
    if collision == "same_file":
        _edit(contact_dir, "subs.json", lambda d: d["entries"].append(d["entries"][0]))
    elif collision == "cross_file":
        _edit(contact_dir, "warships.json", lambda d: d["entries"][0].update(key="diesel_alt"))
    else:
        _edit(contact_dir, "animals.json", lambda d: d["entries"][0].update(key="animal"))
    for loader in (catalog._load_catalog_from, validate):
        with pytest.raises(ValueError, match="duplicate"):
            loader(contact_dir)


def test_valid_json_edits_survive_runtime_load_without_coercion_or_loss(contact_dir):
    # The tool compares every loaded field against JSON, not just profile counts.
    _edit(contact_dir, "subs.json", lambda d: d["entries"][0].update(
        speed_kn=[4, 13], quiet=0.4, torpedoes=7, aggression=0.2, spawn_weight=3))
    _edit(contact_dir, "subs.json", lambda d: d["entries"][0]["acoustic"].update(
        blades=[3, 7], broadband=[0.4, 20, 200], secondary_tonals=[[12, 0.2, 1]],
        rpm_range=[0, 0], tonal_band_hz=[0, 0]))
    _edit(contact_dir, "torpedoes.json", lambda d: d["entries"][0].update(range_nm=42))
    loaded = validate(contact_dir)
    sub = loaded.subs["diesel_alt"]
    assert sub.speed_kn == (4, 13)
    assert sub.torpedoes == 7
    assert sub.acoustic.blade_counts == (3, 7)
    assert sub.acoustic.rpm_range == sub.acoustic.tonal_band_hz == (0, 0)
    assert loaded.torpedoes["frigate_torp"].range_nm == 42
    assert loaded.acoustic_for("decoy") is not None


def test_capability_metadata_uses_json_propulsion_not_legacy_key():
    for profile in catalog.CATALOG.subs.values():
        nuclear = profile.acoustic.propulsion == "elektrisch/Kernantrieb"
        assert profile.is_nuclear is nuclear
        assert profile.requires_air is not nuclear
        assert replace(profile, key="unrelated").is_nuclear is nuclear
    conventional = catalog.CATALOG.subs["diesel_alt"]
    changed = replace(conventional, acoustic=replace(
        conventional.acoustic, propulsion="elektrisch/Kernantrieb"))
    assert changed.is_nuclear and not changed.requires_air


def test_json_fingerprint_fields_have_effect_without_changing_draw_order():
    signature = catalog.CATALOG.subs["diesel_alt"].acoustic
    original_rng, edited_rng = random.Random(14), random.Random(14)
    original = fingerprint.roll_fingerprint(original_rng, signature)
    changed = fingerprint.roll_fingerprint(edited_rng, replace(
        signature, blade_counts=(3,), cavitation_tendency=0,
        broadband=(0.2, 10, 100)))
    assert changed.blades == 3
    assert changed.cavitation == 0
    assert changed.bb_level != original.bb_level
    assert changed.bb_low_hz != original.bb_low_hz
    assert changed.bb_high_hz != original.bb_high_hz
    assert changed.rate_scale == original.rate_scale
    assert changed.offsets == original.offsets
    assert edited_rng.getstate() == original_rng.getstate()


def test_descriptive_and_library_fields_do_not_drive_fingerprint():
    signature = catalog.CATALOG.subs["diesel_alt"].acoustic
    changed = replace(signature, label="Different label", signature_text="Different prose",
                      propulsion="Different description", rpm_range=(1, 2))
    assert fingerprint.roll_from_seed(25, signature) == fingerprint.roll_from_seed(25, changed)


def test_rpm_reference_affects_classification_score(monkeypatch):
    signature = catalog.CATALOG.subs["diesel_alt"].acoustic
    rpm = sum(signature.rpm_range) / 2
    measurement = (signature.blade_counts[0] * rpm / 60, rpm,
                   sum(signature.tonal_band_hz) / 2, signature.cavitation_tendency)
    monkeypatch.setattr(catalog.CATALOG, "acoustic_profiles", (signature,))
    original_score = catalog.rank_signatures(*measurement)[0][1]
    monkeypatch.setattr(catalog.CATALOG, "acoustic_profiles",
                        (replace(signature, rpm_range=(999, 1000)),))
    changed_score = catalog.rank_signatures(*measurement)[0][1]
    assert original_score - changed_score == pytest.approx(0.45)


@pytest.mark.parametrize("kind", PROFILE_KINDS)
def test_unit_schema_rejects_unknown_fields_and_stays_editor_only(kind):
    unit = default_unit(kind)
    assert not validate_unit(unit)
    assert all(not field.effective for field in unit_field_metadata(kind).values())
    unit["unimplemented_capability"] = True
    assert any(problem.path == "unimplemented_capability" for problem in validate_unit(unit))


@pytest.mark.parametrize(("field", "value"), [
    ("version", True), ("version", 1.0), ("version", 2), ("torpedoes", 1.5),
    ("quiet", float("inf")), ("speed_kn", [20, 10]), ("profile_kind", []),
])
def test_unit_schema_rejects_invalid_typed_values(field, value):
    unit = default_unit("sub")
    unit[field] = value
    assert validate_unit(unit)


def test_acoustic_schema_retains_legacy_clone_key_but_rejects_unknowns(tmp_path):
    store = UserContentStore(tmp_path)
    for key, (kind, profile) in catalog_builtins(catalog.CATALOG).items():
        clone = UnitDefinition.clone_builtin(profile, kind, f"user.{key}")
        assert not clone.validate(), key
        if clone.data.get("acoustic") is not None:
            assert clone.data["acoustic"]["key"] == key
    clone = UnitDefinition.clone_builtin(catalog.CATALOG.subs["ssn"], "sub", "user.clone")
    saved = copy.deepcopy(clone.data)
    store.save("unit", saved)
    assert store.list("unit")[0].data == saved
    assert "user.clone" not in catalog.load_catalog().subs
    clone.data["acoustic"]["unimplemented_capability"] = True
    assert any(p.path == "acoustic.unimplemented_capability" for p in clone.validate())
    with pytest.raises(ContentValidationError):
        store.save("unit", clone.data)
    assert store.list("unit")[0].data == saved
    del clone.data["acoustic"]["unimplemented_capability"]
    clone.data["acoustic"]["key"] = 12
    assert any(p.path == "acoustic.key" for p in clone.validate())
