"""No role state may carry a key the browser's validator forbids.

``validateV2State`` (data/commander/js/state/schema.js) walks every published
role state and rejects the whole snapshot when any object has one of its
forbidden keys; the client then freezes with "Host sends data this browser
cannot read". Until 1.3.40 four rows used ``kind`` (the submarine's radio log,
threat intercepts and evasion order, the frigate's HQ tasks), so the picture
froze as soon as one of those lists filled. These checks run without
Chromium, so a plain ``pytest`` catches the next such field.
"""

import json
import re
import sys
from pathlib import Path

from src.commander import projections
from src.commander.v2 import schema as web_schema
from src.core import config

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_boat_radio import BROADCAST, _antenna_up, _step  # noqa: E402
from test_boat_threat import _ping_from  # noqa: E402
from test_opfor_sub import _crewed  # noqa: E402


def _forbidden() -> set:
    text = (ROOT / "data/commander/js/state/schema.js").read_text(encoding="utf-8")
    match = re.search(r"const forbidden = new Set\(\[([^\]]*)\]\)", text)
    assert match, "validateV2State no longer declares its forbidden keys"
    keys = set(re.findall(r'"([^"]+)"', match.group(1)))
    assert "kind" in keys and "target_id" in keys
    return keys


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _strings(key)
            yield from _strings(item)
    elif isinstance(value, (tuple, list, set, frozenset)):
        for item in value:
            yield from _strings(item)


def _forbidden_paths(value, forbidden, path="state"):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in forbidden:
                yield f"{path}.{key}"
            yield from _forbidden_paths(item, forbidden, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _forbidden_paths(item, forbidden, f"{path}[{index}]")


def test_no_web_schema_field_list_names_a_forbidden_key():
    forbidden = _forbidden()
    offenders = sorted(f"{name}: {text}" for name, value in vars(web_schema).items()
                       if name.isupper() and name.endswith("FIELDS")
                       for text in _strings(value) if text in forbidden)
    assert offenders == []


def test_filled_radio_threat_and_task_rows_publish_no_forbidden_key():
    forbidden = _forbidden()
    game, server, bridge = _crewed(seed=61)
    boat = game.opfor
    _antenna_up(game, boat)
    game.sim_t = BROADCAST + 1.0
    _step(game, boat, game.sim_t + config.UBOOT_RADIO_COPY_S + 1.0)
    _ping_from(game, boat, 120.0, 1.5)
    assert game._offer_task() is not None
    bridge.pump(game, server, now=10.0)
    states = json.loads(json.dumps(server.v2_states, allow_nan=False))
    boat_state = states["uboot"]["uboot"]
    assert boat_state["radio"]["log"] and boat_state["threat"]["intercepts"]
    assert boat_state["threat"]["plan"] is not None
    assert states["radio"]["radio"]["tasks"]
    assert projections._uboot_radio(game, boat)["log"][0]["type"] == "broadcast"
    offenders = [path for role, state in states.items() if state is not None
                 for path in _forbidden_paths(state, forbidden, role)]
    assert offenders == []
