"""Every role state a busy mission publishes passes the browser's own validator.

The browser rejects a whole snapshot when one field breaks its schema and then
freezes with "Host sends data this browser cannot read" (1.3.44). This test
plays two busy missions (the frigate with the autocrew on every station
against the AI submarine, and a crewed submarine with its radio, threat
picture and HQ tasks filled), publishes every role's state and chart through
the real bridge at intervals, and runs ``validateState``/``validateChart``
from ``data/commander/js/state`` over all of them in Node. No Chromium needed.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from src.commander.bridge import CommanderBridge
from src.core import config
from src.core.game import Game
from src.core.station import Station

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_boat_radio import BROADCAST, _antenna_up, _step  # noqa: E402
from test_boat_threat import _ping_from  # noqa: E402
from test_commander_bridge import Server  # noqa: E402
from test_opfor_sub import _crewed  # noqa: E402

HARNESS = ROOT / "tests" / "js" / "validate_states.mjs"
FRIGATE_STATIONS = (Station.BRIDGE, Station.SONAR, Station.WEAPONS, Station.DAMAGE,
                    Station.OPZ, Station.RADIO, Station.ENGINE, Station.HELICOPTER,
                    Station.ELOKA)


def _collect(label, server, out):
    for role, state in server.v2_states.items():
        if state is None:
            continue
        chart = (server.v2_charts or {}).get(role)
        out.append({"label": label, "role": role, "state": state, "chart": chart})


def _autocrew_everywhere(game):
    for station in FRIGATE_STATIONS:
        game.autocrew.set_enabled(station, True, game.sim_t)


def _frigate_mission(out, minutes=12, sample_s=60.0):
    game = Game(seed=4242, start_menu=False, audio_enabled=False, language="en")
    _autocrew_everywhere(game)
    server, bridge = Server(), CommanderBridge()
    now = 1.0
    for minute in range(minutes):
        steps = int(sample_s / 0.5)
        for _ in range(steps):
            game.update(0.5)
        bridge.pump(game, server, now=now)
        now += sample_s
        _collect(f"frigate+{minute + 1}min", server, out)
        if game.game_over:
            break
    return game


def _crewed_boat_mission(out):
    game, server, bridge = _crewed(seed=61)
    _autocrew_everywhere(game)
    boat = game.opfor
    _antenna_up(game, boat)
    game.sim_t = BROADCAST + 1.0
    _step(game, boat, game.sim_t + config.UBOOT_RADIO_COPY_S + 1.0)
    _ping_from(game, boat, 120.0, 1.5)
    game._offer_task()
    now = 10.0
    for sample in range(6):
        bridge.pump(game, server, now=now)
        _collect(f"boat+{sample}", server, out)
        _step(game, boat, game.sim_t + 45.0, dt=0.5)
        now += 45.0
    return game


def _validate(rows):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    payload = json.dumps({"states": rows}, allow_nan=False)
    result = subprocess.run([node, str(HARNESS)], input=payload, capture_output=True,
                            text=True, timeout=120, check=False)
    assert result.returncode == 0, result.stderr[-2000:]
    return json.loads(result.stdout)


def test_busy_missions_publish_only_states_the_browser_accepts():
    rows = []
    _frigate_mission(rows)
    _crewed_boat_mission(rows)
    roles = {row["role"] for row in rows}
    # Every frigate station and every submarine station was published.
    assert {"bridge", "sonar", "weapons", "damage", "opz", "radio", "engine",
            "helicopter", "eloka"} <= roles
    assert {"uboot", "uboot_sonar", "uboot_weapons", "uboot_engine", "uboot_esm",
            "uboot_nav", "uboot_radio"} <= {row["state"]["role"] for row in rows}
    report = _validate(rows)
    assert report["checked"] == len(rows)
    assert report["failures"] == []


def test_the_harness_rejects_a_broken_state():
    rows = []
    game = Game(seed=5, start_menu=False, audio_enabled=False, language="en")
    server, bridge = Server(), CommanderBridge()
    bridge.pump(game, server, now=1.0)
    _collect("plain", server, rows)
    bridge_row = next(row for row in rows if row["role"] == "bridge")
    broken = json.loads(json.dumps(bridge_row))
    broken["state"]["bridge"]["kind"] = "oops"
    report = _validate([bridge_row, broken])
    assert report["checked"] == 2 and len(report["failures"]) == 1


def test_a_bridge_route_passes_the_browser_validator():
    rows = []
    game = Game(seed=5, start_menu=False, audio_enabled=False, language="en")
    server, bridge = Server(), CommanderBridge()
    assert game.start_route_pattern("square") == "ok"
    for _ in range(40):
        game.update(0.5)
    bridge.pump(game, server, now=1.0)
    _collect("route", server, rows)
    route = server.v2_states["bridge"]["bridge"]["route"]
    assert route["pattern"] == "square" and route["total"] == 8
    assert [row["number"] for row in route["points"]] == list(
        range(route["index"] + 1, 9))
    report = _validate([row for row in rows if row["role"] == "bridge"])
    assert report["failures"] == []


def test_a_helicopter_rescue_passes_the_browser_validator():
    rows = []
    game = Game(seed=4101, start_menu=False, audio_enabled=False, language="en")
    game.tasking.next_offer_t = 1e9
    task = game._offer_task("sar")
    game.accept_task(task["id"])
    game.helo.launch(game.ship)
    game.helo.x, game.helo.y = task["true_x"], task["true_y"]
    game.helo.set_waypoint(game.helo.x, game.helo.y)
    server, bridge = Server(), CommanderBridge()
    bridge.pump(game, server, now=1.0)
    _collect("rescue-ready", server, rows)
    game.order_helicopter_hoist(True)
    task["aboard"], task["progress"] = 1, 1.0 / task["persons"]
    game.helo.hoist_s = 20.0
    bridge.pump(game, server, now=2.0)
    _collect("rescue-lifting", server, rows)
    helo_rows = [row for row in rows if row["role"] == "helicopter"]
    assert len(helo_rows) == 2
    assert helo_rows[-1]["state"]["helicopter"]["rescue"]["aboard"] == 1
    report = _validate(helo_rows)
    assert report["failures"] == []
