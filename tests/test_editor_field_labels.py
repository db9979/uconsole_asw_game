"""Every field row the editors show has a catalog label (no raw key on screen)."""

import copy
import json
from pathlib import Path

from src.core.i18n import load_catalog
from src.ui import editor_widgets as widgets


def _template(name):
    root = Path(__file__).parents[1] / "data" / "editor_templates"
    return json.loads((root / name).read_text(encoding="utf-8"))


def test_mission_editor_rows_have_labels():
    catalog = load_catalog("en")
    mission = _template("mission.json")
    unit = {"id": "u1", "kind": "surface", "placement": {"kind": "fixed", "sector": "",
                                                         "x": 1.0, "y": 2.0}}
    subsets = [mission["world"], mission["player"], mission["environment"],
               dict(mission["objective"], reach={"x": 1.0, "y": 1.0, "radius_nm": 2.0}),
               unit, *mission["units"]["exact"], *mission["units"]["random_groups"],
               *mission["events"]]
    labels = {row.label for subset in subsets
              for row in widgets.mapping_rows(copy.deepcopy(subset))}
    assert sorted(label for label in labels if label not in catalog) == []
