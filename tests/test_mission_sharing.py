"""Sharing custom missions: an export lands in the exchange folder with the
user units it references, the import list reads that folder, an identical
item is no collision, and a hostile file stays rejected."""

import json

import pygame
import pytest

from src.core.mission_definition import default_mission, mission_hints
from src.data.user_content import BUNDLE_MAX_BYTES, default_store
from src.data.validation import ContentValidationError
from src.ui.mission_editor import MissionEditor


def _unit():
    with open("data/editor_templates/unit_sub.json", encoding="utf-8") as stream:
        return json.load(stream)


def _mission(key="user.shared"):
    mission = default_mission(key)
    unit = _unit()
    mission["units"]["exact"] = [{"id": "boat", "profile": unit["key"], "side": "hostile",
                                  "placement": {"kind": "fixed", "x": 300.0, "y": 250.0},
                                  "course_deg": 0.0, "speed_kn": 4.0}]
    mission["objective"]["target_ids"] = ["boat"]
    return mission


def test_export_packs_the_referenced_user_units_into_the_exchange_folder(tmp_path):
    store = default_store(tmp_path / "a")
    store.save("unit", _unit())
    path = store.export_mission(_mission())
    assert path.parent == store.share_root and path.name == "user.shared.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert [unit["key"] for unit in payload["units"]] == [_unit()["key"]]
    other = default_store(tmp_path / "b")
    (other.share_root).mkdir(parents=True)
    (other.share_root / "friend.json").write_bytes(path.read_bytes())
    (other.share_root / "broken.json").write_text("{", encoding="utf-8")
    rows = other.shared_files()
    assert [row.path.name for row in rows] == ["broken.json", "friend.json"]
    assert rows[0].error and rows[1].missions == (("user.shared", "New mission", "frigate"),)
    assert rows[1].units == 1
    records = other.import_bundle(rows[1].path)
    assert {record.key for record in records} == {"user.shared", _unit()["key"]}
    # The same file again is no collision; a changed mission is one.
    assert other.import_bundle(rows[1].path) == []
    changed = json.loads(path.read_text(encoding="utf-8"))
    changed["missions"][0]["name"] = "Changed"
    with pytest.raises(ContentValidationError) as error:
        other.import_bundle(changed)
    assert error.value.issues[0].code == "exists"
    assert other.import_bundle(changed, overwrite=True)[0].data["name"] == "Changed"


def test_a_missing_user_unit_blocks_the_export(tmp_path):
    with pytest.raises(ContentValidationError) as error:
        default_store(tmp_path).export_mission(_mission())
    assert error.value.issues[0].code == "missing"


def test_hostile_bundle_files_are_rejected(tmp_path):
    store = default_store(tmp_path)
    store.share_root.mkdir(parents=True)
    big = store.share_root / "big.json"
    big.write_bytes(b" " * (BUNDLE_MAX_BYTES + 1))
    nan = store.share_root / "nan.json"
    nan.write_text('{"format": "u-jagd.editor-bundle", "version": 1, "missions": [],'
                   ' "units": [], "x": NaN}', encoding="utf-8")
    extra = {"format": "u-jagd.editor-bundle", "version": 1, "missions": [], "units": [],
             "script": "x"}
    for source in (big, nan, extra):
        with pytest.raises((ContentValidationError, ValueError)):
            store.import_bundle(source)
    assert all(row.error for row in store.shared_files())


def test_editor_shares_and_imports_through_the_list(tmp_path):
    pygame.init()
    source = default_store(tmp_path / "a")
    source.save("mission", _mission("user.plain") | {"units": {"exact": [], "random_groups": []},
                                                     "objective": default_mission()["objective"]})
    editor = MissionEditor(store=source, profile_keys=set())
    editor.listbox.selected = 0
    key = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e, mod=pygame.KMOD_CTRL, unicode="")
    assert editor.handle_event(key)
    shared = source.share_root / "user.plain.json"
    assert shared.exists()
    target = default_store(tmp_path / "b")
    target.share_root.mkdir(parents=True)
    (target.share_root / "x.json").write_bytes(shared.read_bytes())
    other = MissionEditor(store=target, profile_keys=set())
    other.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_i,
                                          mod=pygame.KMOD_CTRL, unicode=""))
    assert other.share_open and len(other.share_files) == 1
    other.draw(pygame.Surface((1280, 720)))
    other.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0, unicode=""))
    assert not other.share_open
    assert [record.key for record in other.records] == ["user.plain"]
    pygame.quit()


def test_fairness_hints_name_a_side_that_can_hardly_win():
    mission = default_mission("user.far")
    mission["units"]["exact"] = [{"id": "sub", "profile": "sub_03", "side": "hostile",
                                  "placement": {"kind": "fixed", "x": 300.0, "y": 300.0},
                                  "course_deg": 0.0, "speed_kn": 4.0}]
    mission["objective"].update(type="sink", target_ids=["sub"], time_limit_s=1800.0)
    assert [key for key, _ in mission_hints(mission)] == ["editor.hint.sink_far.frigate"]
    mission["objective"]["time_limit_s"] = 8 * 3600.0
    assert mission_hints(mission) == []
    boat = default_mission("user.close")
    boat.update(side="uboot", boat_id="sub")
    boat["units"]["exact"] = [dict(mission["units"]["exact"][0],
                                   placement={"kind": "fixed", "x": 251.0, "y": 250.0})]
    boat["objective"].update(type="survive", target_ids=[])
    assert [key for key, _ in mission_hints(boat)] == ["editor.hint.boat_close"]
