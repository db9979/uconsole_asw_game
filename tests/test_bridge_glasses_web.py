"""Browser contract of the bridge lookout's binoculars (Chromium)."""

import json
import math
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
      root.dataset.status = $('bridge-glasses-status')?.textContent || '';
      root.dataset.command = `${$('command-status')?.textContent || ''} | ${$('station-command-status')?.textContent || ''}`;
      root.dataset.clock = `virtual=${Math.round(performance.now())} wall=${Date.now() - wallStart} connection=${$('connection')?.textContent} role=${document.body.dataset.remoteRole}`;
      if (check()) return;
      await sleep(20);
    }
    throw new Error(typeof message === 'function' ? message() : message);
  }
  const status = () => $('bridge-glasses-status').textContent;
  const wallStart = Date.now();
  const nativeError = console.error;
  console.error = (...parts) => {
    root.dataset.consoleError = parts.map((part) => part?.stack || String(part)).join(' ').slice(0, 600);
    nativeError(...parts);
  };
  window.addEventListener('error', (event) => { root.dataset.jsError = String(event.message).slice(0, 300); });
  window.addEventListener('unhandledrejection', (event) => { root.dataset.jsError = String(event.reason?.stack || event.reason).slice(0, 600); });
  async function run() {
    await until(() => !$('shell').hidden, 'translations');
    $('name').value = 'Lookout'; $('code').value = __CODE__;
    $('pair-form').requestSubmit();
    await until(() => document.body.dataset.remoteRole === 'assigned' &&
      !$('station-bridge').hidden && !$('bridge-glasses-canvas').closest('[hidden]'), 'binoculars card',
      200000);  // the grant waits on the host loop; virtual time runs ahead of it
    await until(() => status().includes('Line of sight'), () => `no line of sight: ${status()}`);
    const relative = () => (status().match(/bow (\d+)/) || [])[1];
    document.querySelector('[data-glasses-turn="10"]').click();
    await until(() => relative() === '010', () => `no 10 degree step: ${status()}`);
    $('bridge-glasses-bow').click();
    await until(() => relative() === '000', () => `not back to the bow: ${status()}`);
    // Tilt, zoom and stabilizer stay in this browser.
    document.querySelector('[data-optics="glasses"] [data-optics-tilt="2"]').click();
    document.querySelector('[data-optics="glasses"] [data-optics-zoom="1"]').click();
    const stabilizer = document.querySelector('[data-optics="glasses"] [data-optics-stabilizer]');
    stabilizer.click();
    if (stabilizer.getAttribute('aria-pressed') !== 'true') throw new Error('stabilizer not pressed');
    await until(() => status().includes('+2°') && status().includes('8°'), () => `no optics in: ${status()}`);
    document.querySelector('[data-optics="glasses"] [data-optics-zoom="-1"]').click();
    document.querySelector('[data-optics="glasses"] [data-optics-tilt="-2"]').click();
    const canvas = $('bridge-glasses-canvas');
    // The neutral merchant crossing ahead shows its red port side light.
    const redLight = () => {
      const data = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
      for (let index = 0; index < data.length; index += 4)
        if (data[index] > 220 && data[index + 1] < 110 && data[index + 2] < 100) return true;
      return false;
    };
    await until(redLight, 'no port side light in the binoculars');
    const pixels = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
    const colors = new Set();
    for (let index = 0; index < pixels.length; index += 4 * 97)
      colors.add(`${pixels[index]},${pixels[index + 1]},${pixels[index + 2]}`);
    if (colors.size < 8) throw new Error(`flat binoculars: ${colors.size} colours`);
    root.dataset.colors = String(colors.size);
    // The weather instrument is a small eyepiece into the wind with the
    // turquoise wind rose in its corner.
    const weather = $('bridge-weather-canvas').getContext('2d');
    const near = (data, rgb) => {
      for (let index = 0; index < data.length; index += 4)
        if (Math.abs(data[index] - rgb[0]) + Math.abs(data[index + 1] - rgb[1]) + Math.abs(data[index + 2] - rgb[2]) < 24) return true;
      return false;
    };
    await until(() => near(weather.getImageData(0, 0, 60, 60).data, [120, 214, 180]), 'no wind rose in the weather picture');
    if (!near(weather.getImageData(300, 0, 60, 30).data, [40, 96, 90])) throw new Error('no brackets on the weather picture');
  }
  run().then(() => { root.dataset.scopeTest = 'passed'; }, (error) => {
    root.dataset.scopeTest = 'failed';
    root.dataset.failure = String(error.stack || error);
  });
})();
'''


def test_bridge_binoculars_train_in_the_browser(tmp_path, monkeypatch):
    chromium = (shutil.which("chromium") or shutil.which("chromium-browser")
                or shutil.which("google-chrome"))
    if not chromium:
        pytest.skip("Optional binoculars browser contract: no Chromium")
    en, de = catalogs()
    game = Game(seed=917, start_menu=False, audio_enabled=False, language="en")
    game.world.hour = 23.0
    # A neutral merchant 1 NM ahead crossing from right to left (port side).
    merchant = game.civilians[0]
    for other in game.civilians[1:] + game.warships:
        other.x, other.y = game.ship.x + 60.0, game.ship.y + 60.0
    ahead = math.radians(game.ship.course)
    merchant.x = game.ship.x + math.sin(ahead)
    merchant.y = game.ship.y - math.cos(ahead)
    merchant.course = (game.ship.course - 90.0) % 360.0
    merchant.speed = 0.0
    game.world.land_blocks_line = lambda *args: False
    console = game.commander
    console.port = 0
    console._translations = {
        "en": {key: value for key, value in en.items() if key.startswith(PREFIX)},
        "de": {key: value for key, value in de.items() if key.startswith(PREFIX)},
    }
    console._contact_analysis_assets = {}
    console._manual_pages = {}
    html = inject_probe(index_html(), "glasses-test.js")
    copy_assets(tmp_path, html)
    monkeypatch.setattr(server.resources, "files", lambda _package: tmp_path)
    console.activate(game)
    console.server._http.assets["/glasses-test.js"] = (
        "text/javascript; charset=utf-8",
        PROBE.replace("__CODE__", json.dumps(console.pairing_code)).encode("utf-8"))
    process = subprocess.Popen([
        chromium, "--headless", "--no-sandbox", "--disable-gpu",
        "--disable-background-networking", "--no-first-run",
        "--no-default-browser-check", "--disable-dev-shm-usage",
        f"--user-data-dir={tmp_path / 'browser'}", "--window-size=1600,1000",
        "--virtual-time-budget=120000", "--dump-dom",
        f"http://{console.address[0]}:{console.address[1]}/",
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    started = time.monotonic()
    granted = False
    try:
        while process.poll() is None and time.monotonic() - started < 120:
            if not granted:
                clients = console.server.client_statuses()
                if clients:
                    assert console.server.grant_station(clients[0]["client_id"], "bridge")
                    granted = True
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
    assert root.get("data-scope-test") == "passed", (
        root.get("data-status"), root.get("data-console-error"), root.get("data-js-error"),
        root.get("data-failure", stderr[-300:]))
