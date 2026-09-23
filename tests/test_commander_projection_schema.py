"""Real role projections must pass the browser's own v2 state validator.

The browser (data/commander/app.js) checks every published role state with
exact key sets and freezes the picture on any mismatch.  Hand-written
fixtures cannot catch a projection that grows a field, so this test drives a
feature-rich game, collects what the bridge actually publishes for all nine
stations and runs the extracted ``validateV2State`` in headless Chromium.
"""

import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from src.air.asm import ASM
from src.commander.bridge import CommanderBridge
from src.core.game import Game
from src.sonar.sonar import Contact

sys.path.insert(0, str(Path(__file__).parent))
from test_commander_bridge import Server  # noqa: E402

APP = Path("data/commander/app.js")


def _collect_states():
    samples = []
    game = Game(seed=31, start_menu=False, audio_enabled=False, language="en")
    game.paused = False
    game.world.land_blocks_line = lambda *args: False
    bridge, server = CommanderBridge(), Server()
    clock = [100.0]

    def pump():
        clock[0] += 1.0
        bridge.pump(game, server, now=clock[0])
        samples.append(json.loads(json.dumps(server.v2_states, allow_nan=False)))

    pump()
    for actor in game.civilians[:3] + game.warships[:2]:
        actor.x, actor.y = game.ship.x + 8.0, game.ship.y + 3.0
        actor.emitter = True
    sub = game.subs[0]
    sub.x, sub.y = game.ship.x + 25.0, game.ship.y
    game.launch_helicopter()
    missile = ASM(game.ship.x + 12.0, game.ship.y, 270.0, 99, game.rng_asm,
                  game._air_defense_loadout["asm"], datum=(game.ship.x, game.ship.y))
    missile.jammer = False
    game.asms.append(missile)
    game.asm_seq = max(game.asm_seq, 99)
    game.damage.torpedo_hit(impact=(-0.45, 0.0))
    game.damage.missile_hit(0.7, 0.0)
    game.deploy_nixie_result()
    for step in range(260):
        game._update_sim(0.1)
        if step == 60:
            game.set_helicopter_dipping(True)
        if step == 100:
            game.set_helicopter_dipping(False)
        if step == 140:
            game.deploy_helicopter_buoy()
        if step == 200:
            contact = Contact(1, sub.id, "passiv", "sub")
            contact.update_passive(90.0, .9, .9, "K", game.sim_t)
            contact.player_class = "U_BOOT"
            game.sonar.contacts[sub.id] = contact
            game.selected_contact = game.target = contact
            game.roe = "FREI"
            game.launch_torpedo_at(contact, 60.0)
        if step % 40 == 0:
            pump()
    tracks = game.asm_tracks()
    if tracks:
        game.launch_chaff_at(tracks[0])
    for step in range(60):
        game._update_sim(0.1)
        if step % 20 == 0:
            pump()
    assert game.eloka_tracks() and game.buoys
    return samples


def _validator_page(states) -> str:
    app = APP.read_text(encoding="utf-8").split("\n")

    def line_of(pattern):
        return next(i for i, line in enumerate(app) if re.search(pattern, line))

    def statement(pattern):
        index = line_of(pattern)
        lines = [app[index]]
        while not lines[-1].rstrip().endswith(";"):
            index += 1
            lines.append(app[index])
        return "\n".join(lines)

    start = line_of(r"^  const exactKeys = ")
    begin = line_of(r"^  function validateV2State\(state\)")
    end = next(i for i in range(begin + 1, len(app)) if app[i] == "  }")
    validator = "\n".join(app[start:end + 1]).replace(
        "const exactKeys = (value, keys) =>", "const exactKeysRaw = (value, keys) =>", 1)
    validator = validator.replace("  const boundedArray", (
        "  const exactKeys = (value, keys) => { const ok = exactKeysRaw(value, keys);"
        " if (!ok) lastMismatch = {got: value && typeof value === 'object'"
        " ? Object.keys(value).sort() : typeof value, want: [...keys].sort()};"
        " return ok; };\n  const boundedArray"), 1)
    cases = [(index, role, state) for index, sample in enumerate(states)
             for role, state in sample.items() if role not in ("None", "null")
             and state is not None]
    script = "\n".join([
        statement(r"^  const stationNames = "), statement(r"^  const finite = "),
        statement(r"^  const gameEffectKinds = "),
        "let session = null; let lastMismatch = null;", validator,
        f"const cases = {json.dumps(cases)};",
        "const failures = [];",
        "for (const [index, role, state] of cases) {",
        "  session = {station: role}; lastMismatch = null;",
        "  try { validateV2State(state); } catch (error) {",
        "    failures.push(`${index}:${role}:${error.message} ${JSON.stringify(lastMismatch)}`); }",
        "}",
        "document.documentElement.dataset.result ="
        " JSON.stringify({checked: cases.length, failures});",
    ])
    return ("<!doctype html><html><body><script>"
            + script.replace("</script", "<\\/script") + "</script></body></html>")


def test_published_role_states_pass_the_browser_validator(tmp_path):
    chromium = shutil.which("chromium") or shutil.which("chromium-browser")
    if chromium is None:
        pytest.skip("Chromium is not installed")
    states = _collect_states()
    roles = {role for sample in states for role in sample if role not in ("None", "null")}
    assert roles == {"bridge", "sonar", "weapons", "damage", "opz", "radio",
                     "engine", "helicopter", "eloka"}
    page = tmp_path / "validate.html"
    page.write_text(_validator_page(states), encoding="utf-8")
    result = subprocess.run(
        [chromium, "--headless", "--no-sandbox", "--disable-gpu", "--no-first-run",
         "--no-default-browser-check", "--disable-dev-shm-usage",
         f"--user-data-dir={tmp_path / 'profile'}", "--virtual-time-budget=20000",
         "--dump-dom", page.as_uri()], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr[-2000:]
    match = re.search(r'data-result="([^"]*)"', result.stdout)
    assert match, result.stdout[-2000:] + result.stderr[-2000:]
    outcome = json.loads(html.unescape(match.group(1)))
    assert outcome["checked"] >= 9 * len(states) - 9
    assert outcome["failures"] == []
