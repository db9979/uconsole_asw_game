import json
from pathlib import Path

import pytest

import src.data.user_content as user_content
from src.core.mission_definition import default_mission, static_preview, validate_mission
from src.data.user_content import BUNDLE_FORMAT, UserContentStore
from src.data.validation import ContentValidationError, safe_content_path
from src.ui.unit_editor import PROFILE_KINDS, default_unit, validate_unit
from src.ui.editor_widgets import parse_value


def test_defaults_and_templates_are_strictly_valid():
    assert not validate_mission(default_mission())
    for kind in PROFILE_KINDS:
        assert not validate_unit(default_unit(kind)), kind
    root = Path(__file__).parents[1] / "data" / "editor_templates"
    assert not validate_mission(json.loads((root / "mission.json").read_text()))
    for kind in PROFILE_KINDS:
        assert not validate_unit(json.loads((root / f"unit_{kind}.json").read_text()))


def test_finite_duplicate_enum_and_reference_validation():
    unit = default_unit("sub")
    unit["quiet"] = float("nan")
    unit["acoustic"]["blades"] = [5, 5]
    assert {problem.code for problem in validate_unit(unit)} >= {"finite", "duplicate"}

    mission = default_mission()
    mission["objective"]["target_ids"] = ["missing"]
    mission["environment"]["weather"] = "space"
    assert {problem.code for problem in validate_mission(mission)} >= {"reference", "enum"}


@pytest.mark.parametrize("key", ["../escape", "user../escape", "user.foo/bar", "/user.foo", "builtin"])
def test_no_path_traversal(tmp_path, key):
    with pytest.raises(ContentValidationError):
        safe_content_path(tmp_path, key)


def test_bundle_validates_everything_before_atomic_writes(tmp_path):
    store = UserContentStore(tmp_path, validate_mission, validate_unit)
    good = default_unit("animal", "user.good")
    bad = default_unit("sub", "user.bad")
    bad["speed_kn"] = [20, 10]
    bundle = {"format": BUNDLE_FORMAT, "version": 1, "missions": [],
              "units": [good, bad]}
    with pytest.raises(ContentValidationError):
        store.import_bundle(bundle)
    assert store.list("unit") == []


def test_bundle_staging_failure_leaves_every_destination_untouched(tmp_path, monkeypatch):
    store = UserContentStore(tmp_path, validate_mission, validate_unit)
    original = default_unit("animal", "user.existing")
    store.save("unit", original)
    existing_path = store.path_for("unit", original["key"])
    original_bytes = existing_path.read_bytes()
    replacement = dict(original, name="Replacement")
    added = default_unit("animal", "user.added")
    real_stage = user_content._stage_json

    def fail_second_stage(path, value):
        if value["key"] == "user.added":
            raise OSError("injected staging failure")
        return real_stage(path, value)

    monkeypatch.setattr(user_content, "_stage_json", fail_second_stage)
    bundle = {"format": BUNDLE_FORMAT, "version": 1, "missions": [],
              "units": [replacement, added]}
    with pytest.raises(OSError, match="injected staging failure"):
        store.import_bundle(bundle, overwrite=True)

    assert existing_path.read_bytes() == original_bytes
    assert not store.path_for("unit", added["key"]).exists()
    assert not list((tmp_path / "units").glob(".*.tmp"))
    assert not list((tmp_path / "units").glob(".*.bak"))


def test_bundle_commit_failure_restores_overwrites_and_removes_new_files(
        tmp_path, monkeypatch):
    store = UserContentStore(tmp_path, validate_mission, validate_unit)
    original = default_unit("animal", "user.existing")
    store.save("unit", original)
    existing_path = store.path_for("unit", original["key"])
    original_bytes = existing_path.read_bytes()
    replacement = dict(original, name="Replacement")
    added = default_unit("animal", "user.added")
    failing = default_unit("animal", "user.failing")
    real_replace = user_content.os.replace

    def fail_late_commit(source, destination):
        if Path(destination).name == "user.failing.json":
            raise OSError("injected commit failure")
        return real_replace(source, destination)

    monkeypatch.setattr(user_content.os, "replace", fail_late_commit)
    bundle = {"format": BUNDLE_FORMAT, "version": 1, "missions": [],
              "units": [replacement, added, failing]}
    with pytest.raises(OSError, match="injected commit failure"):
        store.import_bundle(bundle, overwrite=True)

    assert existing_path.read_bytes() == original_bytes
    assert not store.path_for("unit", added["key"]).exists()
    assert not store.path_for("unit", failing["key"]).exists()
    assert not list((tmp_path / "units").glob(".*.tmp"))
    assert not list((tmp_path / "units").glob(".*.bak"))


def test_seeded_preview_is_stable_and_resolves_groups():
    mission = default_mission()
    mission["world"]["sectors"] = [{"id": "a", "x": 10, "y": 20,
                                      "width": 30, "height": 40}]
    mission["units"]["random_groups"] = [{"id": "g", "profiles": ["a", "b"],
                                            "side": "hostile", "count": [2, 2],
                                            "placement": {"kind": "sector", "sector": "a"}}]
    first = static_preview(mission)
    assert first == static_preview(mission)
    assert len(first["markers"]) == 3
    assert not first["runtime_effective"]


def test_editor_value_parser_preserves_types_and_rejects_code_or_nonfinite_json():
    assert parse_value("false", True) is False
    assert parse_value("12", 1) == 12
    assert parse_value("1.25", 1.0) == 1.25
    assert parse_value('["a",2]', []) == ["a", 2]
    with pytest.raises(ValueError):
        parse_value('__import__("os").system("false")', [])
    with pytest.raises(ValueError):
        parse_value("[1e999]", [])
