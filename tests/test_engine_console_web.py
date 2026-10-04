"""Browser contract of the frigate's engine-room console (Chromium)."""

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from commander_web import copy_assets, index_html, inject_probe

from src.commander import server
from src.core.game import Game
from test_commander_assets import Document, PREFIX, catalogs

sys.path.insert(0, str(Path(__file__).parent))


PROBE = r'''
(() => {
  const $ = (id) => document.getElementById(id);
  const root = document.documentElement;
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  async function until(check, message, limit = 3000) {
    for (let index = 0; index < limit; index++) {
      if (check()) return;
      await sleep(20);
    }
    throw new Error(typeof message === 'function' ? message() : message);
  }
  window.addEventListener('error', (event) => { root.dataset.jsError = String(event.message).slice(0, 300); });
  window.addEventListener('unhandledrejection', (event) => { root.dataset.jsError = String(event.reason?.stack || event.reason).slice(0, 600); });
  const lamp = (key) => $('engine-lamps').querySelector(`[data-key="${key}"]`);
  async function run() {
    await until(() => !$('shell').hidden, 'translations');
    $('name').value = 'Engine'; $('code').value = __CODE__;
    $('pair-form').requestSubmit();
    await until(() => $('station-tab-engine'), 'engine station tab');
    $('station-tab-engine').click();
    root.dataset.stage = 'console';
    await until(() => document.body.dataset.remoteRole === 'assigned' && !$('engine-visual').hidden, 'console hidden');
    await until(() => $('engine-lamps').children.length >= 16, () => `lamps: ${$('engine-lamps').children.length}`);
    root.dataset.stage = 'lamps';
    await until(() => lamp('fire')?.dataset.level === 'alarm', () => `fire lamp: ${lamp('fire')?.dataset.level}`);
    await until(() => lamp('ship_flood')?.dataset.level === 'caution', () => `flood lamp: ${lamp('ship_flood')?.dataset.level}`);
    if (lamp('fuel')?.dataset.level !== 'on') throw new Error(`fuel lamp: ${lamp('fuel')?.dataset.level}`);
    if (lamp('grounded').dataset.level !== 'off') throw new Error('grounded lamp lit');
    if ($('engine-master').dataset.state !== 'alarm') throw new Error(`master: ${$('engine-master').dataset.state}`);
    root.dataset.stage = 'lamp-tip';
    // Hovering a lamp says why it is lit, from the host's lamp_tips.
    lamp('fire').dispatchEvent(new MouseEvent('mouseenter'));
    await until(() => $('lamp-tip') && !$('lamp-tip').hidden && $('lamp-tip').querySelector('strong')?.textContent,
      'no lamp note on hover');
    root.dataset.lampTip = $('lamp-tip').textContent.slice(0, 200);
    lamp('fire').dispatchEvent(new MouseEvent('mouseleave'));
    if (!$('lamp-tip').hidden) throw new Error('lamp note stays after leaving');
    root.dataset.stage = 'mimic';
    const rooms = [...$('engine-compartments').children];
    if (rooms.length !== 9) throw new Error(`rooms: ${rooms.length}`);
    if (rooms[0].dataset.side !== 'starboard' || rooms.at(-1).dataset.side !== 'port') throw new Error('hull sides out of place');
    if (rooms[1].dataset.key !== 'sonar') throw new Error(`bow section: ${rooms[1].dataset.key}`);
    const engine = rooms.find((room) => room.dataset.key === 'engine');
    if (engine.querySelector('[data-lamp="fire"]').dataset.level !== 'alarm') throw new Error('engine fire lamp dark');
    if (!engine.querySelector('.console-room-team').textContent.includes('2')) throw new Error('no team in the engine room');
    const port = rooms.find((room) => room.dataset.key === 'hull_left');
    if (port.querySelector('[data-lamp="flood"]').dataset.level === 'off') throw new Error('port flood lamp dark');
    root.dataset.stage = 'fuel';
    if ($('engine-fuel-readouts').children.length !== 5) throw new Error('fuel readouts');
    if (!$('engine-fuel-tank').style.getPropertyValue('--fill')) throw new Error('fuel column empty');
    root.dataset.stage = 'dials';
    await until(() => $('engine-instruments-text').children.length === 6, () => `dials: ${$('engine-instruments-text').children.length}`);
    const canvas = $('engine-instruments');
    const pixels = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
    const colors = new Set();
    for (let index = 0; index < pixels.length; index += 4 * 53)
      colors.add(`${pixels[index]},${pixels[index + 1]},${pixels[index + 2]}`);
    if (colors.size < 4) throw new Error(`flat gauges: ${colors.size} colours`);
    const stage = $('stage').getBoundingClientRect(), panel = $('engine-visual').getBoundingClientRect();
    if (panel.left < stage.left - 1 || panel.right > stage.right + 1) throw new Error('console leaves the stage');
    if (document.documentElement.scrollWidth > innerWidth) throw new Error('page overflows');
    root.dataset.lamps = String($('engine-lamps').children.length);
  }
  run().then(() => { root.dataset.engineTest = 'passed'; }, (error) => {
    root.dataset.engineTest = 'failed';
    root.dataset.failure = String(error.stack || error);
  });
})();
'''


def test_frigate_engine_console_shows_lamps_gauges_fuel_and_sections(tmp_path, monkeypatch):
    chromium = (shutil.which("chromium") or shutil.which("chromium-browser")
                or shutil.which("google-chrome"))
    if not chromium:
        pytest.skip("Optional engine-room browser contract: no Chromium")
    en, de = catalogs()
    game = Game(seed=1234, start_menu=False, audio_enabled=False, language="en")
    console = game.commander
    console.port = 0
    console._translations = {
        "en": {key: value for key, value in en.items() if key.startswith(PREFIX)},
        "de": {key: value for key, value in de.items() if key.startswith(PREFIX)},
    }
    console._contact_analysis_assets = {}
    console._manual_pages = {}
    html = inject_probe(index_html(), "engine-test.js")
    copy_assets(tmp_path, html)
    monkeypatch.setattr(server.resources, "files", lambda _package: tmp_path)
    console.activate(game)
    console.server._http.assets["/engine-test.js"] = (
        "text/javascript; charset=utf-8",
        PROBE.replace("__CODE__", json.dumps(console.pairing_code)).encode("utf-8"))
    console.bridge.allowed = True
    process = subprocess.Popen([
        chromium, "--headless", "--no-sandbox", "--disable-gpu",
        "--disable-background-networking", "--no-first-run",
        "--no-default-browser-check", "--disable-dev-shm-usage",
        f"--user-data-dir={tmp_path / 'browser'}", "--window-size=1600,1000",
        "--virtual-time-budget=300000", "--dump-dom",
        f"http://{console.address[0]}:{console.address[1]}/",
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    started = time.monotonic()
    granted = False
    damaged = False
    try:
        while process.poll() is None and time.monotonic() - started < 120:
            if not granted:
                clients = console.server.client_statuses()
                if clients:
                    client = clients[0]["client_id"]
                    assert console.server.grant_station(client, "engine")
                    assert console.server.set_client_grant(client, "engine", "command", True)
                    granted = True
            if granted and not damaged:
                # Once: fire in the engine room with team 2 on it, water in
                # the port hull.
                damaged = True
                game.damage.compartments["engine"].fire = 30.0
                game.damage.compartments["hull_left"].flood = 20.0
                game.damage.teams = {1: None, 2: "engine", 3: None}
            console.pump(game)
            game.update(.02)
            time.sleep(.02)
        stdout, stderr = process.communicate(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
            stdout, stderr = process.communicate(timeout=5)
        console.stop()
        game.audio.shutdown()
    root = next((attrs for tag, attrs in Document(stdout).elements if tag == "html"), {})
    assert root.get("data-engine-test") == "passed", (
        root.get("data-stage"), root.get("data-js-error"), root.get("data-failure", stderr[-300:]))
    assert damaged
    assert int(root.get("data-lamps", "0")) >= 16
    assert "fire" in root.get("data-lamp-tip", "").lower()
