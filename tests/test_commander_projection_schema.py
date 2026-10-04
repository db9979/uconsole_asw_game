"""Real role projections must pass the browser's own v2 state validator.

The browser (data/commander/js/state/schema.js) checks every published role state with
exact key sets and freezes the picture on any mismatch.  Hand-written
fixtures cannot catch a projection that grows a field, so this test drives a
feature-rich game, collects what the bridge actually publishes for all nine
stations and both crewed-submarine roles and runs the extracted
``validateV2State`` in headless Chromium.
"""

import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from src.commander.server import OPFOR_ROLES

from src.air.asm import ASM
from src.commander.bridge import CommanderBridge
from src.core.game import Game
from src.sonar.sonar import Contact
from src.weapons.torpedo import EnemyTorpedo

sys.path.insert(0, str(Path(__file__).parent))
from test_commander_bridge import Server  # noqa: E402
from commander_web import module_source  # noqa: E402



class _CrewedSubmarineServer(Server):
    """Publication target whose submarine roles are held by a crew."""

    def station_leased(self, role):
        return role in OPFOR_ROLES


def _collect_states():
    samples = []
    game = Game(seed=31, start_menu=False, audio_enabled=False, language="en")
    game.world.land_blocks_line = lambda *args: False
    bridge, server = CommanderBridge(), _CrewedSubmarineServer()
    clock = [100.0]

    def pump():
        clock[0] += 1.0
        bridge.pump(game, server, now=clock[0])
        samples.append(json.loads(json.dumps(server.v2_states, allow_nan=False)))

    pump()
    for actor in game.civilians[:3] + game.warships[:2]:
        actor.x, actor.y = game.ship.x + 8.0, game.ship.y + 3.0
        actor.emitter = True
    # Close enough for the bridge lookout to classify and identify them.
    game.civilians[0].x, game.civilians[0].y = game.ship.x + 2.0, game.ship.y
    game.civilians[1].x, game.civilians[1].y = game.ship.x - 2.0, game.ship.y
    sub = game.subs[0]
    sub.x, sub.y = game.ship.x + 25.0, game.ship.y
    game.launch_helicopter()
    game.helo.launch(game.ship)                 # past the start preparation
    missile = ASM(game.ship.x + 12.0, game.ship.y, 270.0, 99, game.rng_asm,
                  game._air_defense_loadout["asm"], datum=(game.ship.x, game.ship.y))
    missile.jammer = False
    game.asms.append(missile)
    game.asm_seq = max(game.asm_seq, 99)
    game.damage.torpedo_hit(impact=(-0.45, 0.0))
    game.damage.missile_hit(0.7, 0.0)
    game.deploy_nixie_result()
    pump()                      # weather station without a BT measurement
    assert game.measure_sonar_bt() is True
    boat = game.opfor
    assert boat is not None and boat.sub is sub
    for step in range(260):
        game._update_sim(0.1)
        if step == 20:
            with game.sonar_perspective(boat.station):
                assert game.measure_sonar_bt() is True
            assert sub.set_orders(course=270.0, speed=5.0, depth=90.0) is True
        if step == 50:
            with game.sonar_perspective(boat.station):
                assert game.send_active_ping() is True
            assert sub.command_decoy() in (True, "not_ready", "no_decoys")
            # A torpedo of the crewed boat (the fixture parks the boat on
            # land, so place it in open water) appears in ``own_weapons``.
            water = next((game.ship.x + dx, game.ship.y + dy)
                         for dx in range(-60, 61, 4) for dy in range(-60, 61, 4)
                         if game.world.depth_m(game.ship.x + dx, game.ship.y + dy) > 200.0
                         and game.world.depth_m(game.ship.x + dx + 3.0,
                                                game.ship.y + dy) > 200.0)
            game.enemy_torpedoes.append(EnemyTorpedo(
                water[0], water[1], 90.0, 50.0, 1,
                profile=game.runtime_catalog.torpedoes["enemy_torp"],
                launch_platform_id=sub.id))
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
    assert any(sample["uboot"]["uboot"]["own_weapons"] for sample in samples
               if "uboot" in sample.get("uboot", {}))
    bridge_states = [sample["bridge"]["bridge"] for sample in samples[1:]]
    assert any(row["visual_class"] for state in bridge_states
               for row in state["tactical_summary"])
    assert any(row["code"] for state in bridge_states for row in state["sightings"])
    assert all(sample["sonar"]["weather_station"]["profile"] is not None
               for sample in samples[2:])
    return samples


def _validator_page(states) -> str:
    def statement(relative, marker):
        text = module_source(relative, marker)
        return text[:text.index(";\n") + 1]

    schema = module_source("state/schema.js", "const exactKeys = ")
    end = schema.index("\n}\n", schema.index("function validateV2State(state)")) + 3
    validator = schema[:end].replace(
        "const exactKeys = (value, keys) =>", "const exactKeysRaw = (value, keys) =>", 1)
    validator = validator.replace("const boundedArray", (
        "const exactKeys = (value, keys) => { const ok = exactKeysRaw(value, keys);"
        " if (!ok) lastMismatch = {got: value && typeof value === 'object'"
        " ? Object.keys(value).sort() : typeof value, want: [...keys].sort()};"
        " return ok; };\nconst boundedArray"), 1)
    cases = [(index, role, state) for index, sample in enumerate(states)
             for role, state in sample.items() if role not in ("None", "null")
             and state is not None]
    script = "\n".join([
        statement("core/base.js", "const stationNames = "),
        statement("core/base.js", "const opforRoles = "),
        statement("core/base.js", "const lookoutRoles = "),
        statement("core/base.js", "const sessionRoles = "),
        statement("core/base.js", "const isBoatCommand = "),
        statement("core/base.js", "const sonarRoles = "),
        statement("core/base.js", "const isSonar = "), statement("core/format.js", "const finite = "),
        statement("state/shared.js", "const gameEffectKinds = "),
        statement("state/shared.js", "const calloutKinds = "),
        statement("state/shared.js", "const calloutsWithBearing = "),
        "const S = {session: null}; let lastMismatch = null;", validator,
        f"const cases = {json.dumps(cases)};",
        "const failures = [];",
        "for (const [index, role, state] of cases) {",
        "  S.session = {station: role}; lastMismatch = null;",
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
                     "engine", "helicopter", "eloka", "uboot", "uboot_sonar",
                     "uboot_weapons", "uboot_engine", "uboot_esm", "uboot_nav",
                     "uboot_radio", "lookout", "uboot_lookout"}
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
