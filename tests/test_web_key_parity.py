"""The browser's station keys are the uConsole's keys (improvement plan W2).

Owner rule: the same function has the same key at every station, on both
sides and in the browser. Every binding of ``data/commander/js/input/
station-keys.js`` names the uConsole key-help row of the same function
(``src/core/help.py``); the key must be listed in that row for that station.
A browser-only key (help ``null``) must not be one the uConsole uses at
that station. The four keys that meant something else in the browser
(+ / -, ", / .", L, [ / ]) are the uConsole's again.
"""
import json
import re

import pytest

from commander_web import run_module_probe
from src.core import help as game_help
from src.core.i18n import Translator
from src.core.station import Station

_EN = Translator("en").t
_FRIGATE = {
    "bridge": Station.BRIDGE, "sonar": Station.SONAR, "weapons": Station.WEAPONS,
    "damage": Station.DAMAGE, "opz": Station.OPZ, "radio": Station.RADIO,
    "engine": Station.ENGINE, "helicopter": Station.HELICOPTER, "eloka": Station.ELOKA,
}
_BOAT = ("uboot", "uboot_sonar", "uboot_weapons", "uboot_esm", "uboot_nav",
         "uboot_radio", "uboot_engine")
_ARROWS = {"←": "ArrowLeft", "→": "ArrowRight", "↑": "ArrowUp", "↓": "ArrowDown",
           "<-": "ArrowLeft", "->": "ArrowRight"}


def _keys(column: str) -> set:
    """The keys a help row's key column names (English spelling)."""
    text = _EN(column) if column.startswith("help.key.") else column
    text = re.sub(r"\([^)]*\)", "", text)
    text = (text.replace("Page Up / Down", "PageUp / PageDown")
            .replace("Page Up/Down", "PageUp / PageDown")
            .replace("Hold Up / Down", "ArrowUp / ArrowDown")
            .replace("Up / Down", "ArrowUp / ArrowDown")
            .replace("Arrow keys", "ArrowUp / ArrowDown / ArrowLeft / ArrowRight"))
    keys = set()
    for part in re.split(r" / | \| | · ", text):
        for token in ([part] if part.strip() in ("+", "-", "/") else part.split("/")):
            token = token.strip()
            for arrow, name in _ARROWS.items():
                token = token.replace(arrow, name)
            if token.upper() == "SPACE":
                token = "Space"
            if token:
                keys.add(token)
    return keys


def _rows(role: str) -> list:
    """(key column, action) rows of the uConsole help that apply at ``role``."""
    rows = []
    if role in _FRIGATE:
        rows += game_help.STATION_HELP[_FRIGATE[role]][1] + game_help._GLOBAL_HELP[1]
    if role in _BOAT:
        rows += game_help._UBOOT_HELP[1] + game_help._UBOOT_GLOBAL_HELP[1]
    if role == "uboot_sonar":
        rows += game_help.STATION_HELP[Station.SONAR][1]
    return rows


@pytest.fixture(scope="module")
def bindings(tmp_path_factory):
    probe = r"""
import { STATION_KEYS } from "./js/input/station-keys.js";
import { DOCK_KEYS } from "./js/views/layout.js";
document.documentElement.dataset.result = JSON.stringify({
  keys: STATION_KEYS.map(([roles, key, _targets, how, help]) => [roles, key, how ?? "click", help ?? null]),
  docks: DOCK_KEYS});
"""
    root = run_module_probe(tmp_path_factory.mktemp("keys"), probe)
    assert "data-result" in root, root.get("data-failure")
    return json.loads(root["data-result"])


def test_every_browser_key_is_the_uconsole_key_of_the_same_function(bindings):
    wrong = []
    for roles, key, _how, help_key in bindings["keys"]:
        wanted = [help_key] if isinstance(help_key, str) else help_key
        for role in roles:
            rows = _rows(role)
            if wanted is None:
                # A browser-only key must be free at that station.
                if any(key in _keys(column) for column, _ in rows):
                    wrong.append((role, key, "browser-only key used by the uConsole"))
                continue
            columns = [column for column, action in rows if action in wanted]
            if not columns:
                wrong.append((role, key, f"no uConsole help row {wanted}"))
            elif not any(key in _keys(column) for column in columns):
                wrong.append((role, key, f"uConsole uses {columns} for {wanted}"))
    assert not wrong, wrong


def test_radio_damage_and_eloka_have_station_keys(bindings):
    roles = {role for roles, *_ in bindings["keys"] for role in roles}
    assert {"radio", "damage", "eloka", "engine", "opz", "weapons"} <= roles
    sonar = {key for roles, key, *_ in bindings["keys"] if "sonar" in roles}
    # W1: LFM pulse and the TMA method, as with W / Shift+T on the uConsole.
    assert {"W", "Shift+T"} <= sonar


def test_conflicting_keys_mean_what_they_mean_on_the_uconsole(bindings):
    # + / - is the telegraph (bridge, engine, submarine), never a zoom.
    telegraph = {(key, help_key if isinstance(help_key, str) else tuple(help_key))
                 for roles, key, _how, help_key in bindings["keys"] if key in ("+", "-")}
    assert {help_key for _key, help_key in telegraph} <= {
        "help.control.engine_order", "help.control.engine", "help.uboot.telegraph"}
    # The docks and the log moved to Alt: the bare , . and L stay free.
    assert bindings["docks"] == {"Comma": "left", "Period": "right", "KeyL": "log"}
    web = dict((column, action) for column, action in game_help._WEB_HELP[1])
    assert web.get("Alt+, / Alt+.") == "help.web.docks" and web.get("Alt+L") == "help.web.log"
    assert "[ / ]" not in web and ", / ." not in web and "L" not in web
    assert web.get("+ / -") == "help.web.telegraph" and web.get("Q / E") == "help.web.map_zoom"


def test_browser_handlers_no_longer_take_the_conflicting_keys():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "data" / "commander" / "js"
    tabs = (root / "views" / "station-tabs.js").read_text()
    assert 'event.key === "["' not in tabs and 'event.key === "]"' not in tabs
    wiring = (root / "input" / "wiring.js").read_text()
    # Map and lookout zoom with Q / E only.
    assert '["+", "=", "-"' not in wiring and 'event.key === "+"' not in wiring
