"""Mouse-over tooltips on the Remote Crew maps."""

import json
from pathlib import Path
import shutil
import subprocess
import time

import pytest
from commander_web import copy_assets, index_html, inject_probe

from src.commander import server
from src.core.game import Game
from test_commander_assets import ASSETS, Document, PREFIX, catalogs

PROBE = r'''
(() => {
  const $ = (id) => document.getElementById(id);
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  async function until(check, message, limit = 900) {
    for (let index = 0; index < limit; index++) {
      if (check()) return;
      await sleep(20);
    }
    throw new Error(message);
  }
  async function run() {
    await until(() => !$('shell').hidden, 'translations');
    $('name').value = 'Hover'; $('code').value = __CODE__;
    $('pair-form').requestSubmit();
    await until(() => $('station-tab-bridge'), 'station tabs');
    $('station-tab-bridge').click();
    await until(() => !$('operations').hidden && !$('station-bridge').hidden, 'bridge shown');
    const map = $('role-map');
    await until(() => map.clientWidth > 200 && map.clientHeight > 150, 'map size');
    await sleep(800);
    const rect = map.getBoundingClientRect();
    const seen = new Set();
    for (let y = 8; y < rect.height; y += 8) {
      for (let x = 8; x < rect.width; x += 8) {
        map.dispatchEvent(new PointerEvent('pointermove', {clientX: rect.left + x, clientY: rect.top + y,
          pointerType: 'mouse', bubbles: true}));
        const tip = $('map-tooltip');
        if (!tip.hidden && tip.firstChild) seen.add(tip.firstChild.textContent);
      }
    }
    const lines = [...seen];
    if (!lines.includes(__OWN__)) throw new Error('no own-ship tooltip: ' + lines.slice(0, 8).join(' | '));
    if (!lines.some((line) => line.startsWith(__POS__))) throw new Error('no position tooltip');
    map.dispatchEvent(new PointerEvent('pointerleave', {bubbles: true}));
    if (!$('map-tooltip').hidden) throw new Error('tooltip stays after leaving the map');
  }
  run().then(() => document.documentElement.dataset.hoverTest = 'passed', (error) => {
    document.documentElement.dataset.hoverTest = 'failed';
    document.documentElement.dataset.failure = String(error.stack || error);
  });
})();
'''


def test_role_map_mouse_over_describes_own_ship_and_positions(tmp_path, monkeypatch):
    width, height = 1600, 1000
    chromium = (shutil.which("chromium") or shutil.which("chromium-browser")
                or shutil.which("google-chrome"))
    if not chromium:
        pytest.skip("Optional browser contract: no Chromium")
    en, de = catalogs()
    game = Game(seed=4242, start_menu=False, audio_enabled=False, language="en")
    console = game.commander
    console.solo = True
    console.port = 0
    console._translations = {
        "en": {key: value for key, value in en.items() if key.startswith(PREFIX)},
        "de": {key: value for key, value in de.items() if key.startswith(PREFIX)},
    }
    console._contact_analysis_assets = {}
    # Pre-rendered like the assets: resources.files is redirected below.
    console._manual_pages = {}
    html = inject_probe(index_html(), "hover-test.js")
    copy_assets(tmp_path, html)
    monkeypatch.setattr(server.resources, "files", lambda _package: tmp_path)
    console.activate(game)
    own_text = en[PREFIX + "map_tip_own"]
    position_prefix = en[PREFIX + "map_tip_position"].split("{")[0]
    console.server._http.assets["/hover-test.js"] = (
        "text/javascript; charset=utf-8",
        PROBE.replace("__CODE__", json.dumps(console.pairing_code))
        .replace("__OWN__", json.dumps(own_text))
        .replace("__POS__", json.dumps(position_prefix)).encode("utf-8"))
    console.bridge.allowed = True
    process = subprocess.Popen([
        chromium, "--headless", "--no-sandbox", "--disable-gpu",
        "--disable-background-networking", "--no-first-run",
        "--no-default-browser-check", "--disable-dev-shm-usage",
        f"--user-data-dir={tmp_path / 'browser'}", "--virtual-time-budget=60000",
        f"--window-size={width},{height}", "--dump-dom",
        f"http://{console.address[0]}:{console.address[1]}/",
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    started = time.monotonic()
    try:
        while process.poll() is None and time.monotonic() - started < 90:
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
    assert process.returncode == 0, stderr
    root = next((attrs for tag, attrs in Document(stdout).elements if tag == "html"), {})
    assert root.get("data-hover-test") == "passed", root.get("data-failure", stderr[-2000:])
