"""Browser contract of the submarine's engine-room console (Chromium)."""

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
  const lamp = (key) => $('uboot-engine-lamps').querySelector(`[data-key="${key}"]`);
  async function run() {
    await until(() => !$('shell').hidden, 'translations');
    $('name').value = 'Engine'; $('code').value = __CODE__;
    $('pair-form').requestSubmit();
    await until(() => $('station-tab-uboot_engine'), 'engine station tab');
    $('station-tab-uboot_engine').click();
    root.dataset.stage = 'console';
    await until(() => document.body.dataset.remoteRole === 'assigned' && !$('uboot-engine-visual').hidden, 'console hidden');
    // The stage carries the console, not an empty picture.
    await until(() => $('uboot-engine-lamps').children.length >= 20, () => `lamps: ${$('uboot-engine-lamps').children.length}`);
    root.dataset.stage = 'lamps';
    await until(() => lamp('leak')?.dataset.level === 'alarm', () => `leak lamp: ${lamp('leak')?.dataset.level}`);
    await until(() => lamp('snorkel')?.dataset.level === 'caution', () => `snorkel lamp: ${lamp('snorkel')?.dataset.level}`);
    if (lamp('battery')?.dataset.level !== 'on') throw new Error(`battery lamp: ${lamp('battery')?.dataset.level}`);
    if (lamp('fire').dataset.level !== 'off') throw new Error('fire lamp lit');
    if ($('uboot-engine-master').dataset.state !== 'alarm') throw new Error(`master: ${$('uboot-engine-master').dataset.state}`);
    root.dataset.stage = 'mimic';
    const rooms = [...$('uboot-engine-compartments').children];
    if (rooms.length !== 6) throw new Error(`rooms: ${rooms.length}`);
    const stern = rooms.find((room) => room.dataset.key === 'stern');
    if (stern.querySelector('[data-lamp="leak"]').dataset.level !== 'alarm') throw new Error('stern leak lamp dark');
    if (!stern.querySelector('.console-room-team').textContent.includes('1')) throw new Error('no team in the stern');
    const engine = rooms.find((room) => room.dataset.key === 'engine');
    if (engine.querySelector('[data-lamp="bulkhead"]').dataset.level !== 'on') throw new Error('engine bulkhead not shut');
    root.dataset.stage = 'tanks';
    const tanks = [...$('uboot-engine-tanks').children].map((cell) => cell.dataset.key);
    for (const key of ['battery', 'fuel', 'hp_air', 'mbt', 'regulating', 'trim'])
      if (!tanks.includes(key)) throw new Error(`tank ${key} missing: ${tanks}`);
    root.dataset.stage = 'dials';
    await until(() => $('uboot-engine-dials-text').children.length === 6, () => `dials: ${$('uboot-engine-dials-text').children.length}`);
    const canvas = $('uboot-engine-dials');
    const pixels = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
    const colors = new Set();
    for (let index = 0; index < pixels.length; index += 4 * 53)
      colors.add(`${pixels[index]},${pixels[index + 1]},${pixels[index + 2]}`);
    if (colors.size < 4) throw new Error(`flat gauges: ${colors.size} colours`);
    // The console sits in the stage; the dock keeps the orders.
    const stage = $('stage').getBoundingClientRect(), panel = $('uboot-engine-visual').getBoundingClientRect();
    if (panel.left < stage.left - 1 || panel.right > stage.right + 1) throw new Error('console leaves the stage');
    if (document.documentElement.scrollWidth > innerWidth) throw new Error('page overflows');
    root.dataset.lamps = String($('uboot-engine-lamps').children.length);
  }
  run().then(() => { root.dataset.engineTest = 'passed'; }, (error) => {
    root.dataset.engineTest = 'failed';
    root.dataset.failure = String(error.stack || error);
  });
})();
'''


def test_engine_room_console_shows_lamps_gauges_tanks_and_compartments(tmp_path, monkeypatch):
    chromium = (shutil.which("chromium") or shutil.which("chromium-browser")
                or shutil.which("google-chrome"))
    if not chromium:
        pytest.skip("Optional engine-room browser contract: no Chromium")
    en, de = catalogs()
    game = Game(seed=1234, start_menu=False, audio_enabled=False, language="en")
    game.reset(1234, "s7_geleitzug")          # a diesel-electric boat
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
    boat = None
    try:
        while process.poll() is None and time.monotonic() - started < 120:
            if not granted:
                clients = console.server.client_statuses()
                if clients:
                    client = clients[0]["client_id"]
                    assert console.server.grant_station(client, "uboot_engine")
                    assert console.server.set_client_grant(client, "uboot_engine", "command", True)
                    granted = True
            if game.opfor is not None and boat is None:
                # Once: at snorkel depth with the diesels running, a hole in
                # the stern with team 1 on it and the engine room shut.
                boat = game.opfor
                sub = boat.sub
                sub.depth = sub.target_depth = sub.order_depth = float(
                    sub.endurance.profile.snorkel_depth_m)
                sub.endurance.battery_kwh = sub.endurance.profile.battery_capacity_kwh * 0.6
                assert sub.command_snorkel(True) is True
                sub.damage_control.hull_leak(0.4, 1234, where="stern")
                assert sub.command_dc_team(0, "stern", "seal") is True
                assert sub.command_bulkhead("engine", True) is True
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
    assert boat is not None and boat.sub.endurance is not None
    assert int(root.get("data-lamps", "0")) >= 20
