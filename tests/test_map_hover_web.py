"""Mouse-over tooltips on the Remote Crew maps."""

import json
from pathlib import Path
import shutil
import subprocess
import time

import pytest
from commander_web import RealTimeHost, copy_assets, index_html, inject_probe

from src.commander import server
from src.core.game import Game
from test_commander_assets import ASSETS, PREFIX, catalogs

pytestmark = pytest.mark.browser  # drives headless Chromium (CI browser job)

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
    // Sweep the pointer over the whole map; the own ship and positions are
    // described once the host's picture has been drawn (a fixed pause raced
    // the first state and chart on a loaded host).
    const sweep = () => {
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
      return [...seen];
    };
    const isPosition = (line) => line.startsWith(__POS__) || /^\d{2}°\d{2}[.,]\d'[NS] \d{3}°\d{2}[.,]\d'[EW]$/.test(line);
    let lines = [];
    const described = () => {
      lines = sweep();
      return lines.includes(__OWN__) && lines.some(isPosition);
    };
    for (let index = 0; index < 60 && !described(); index++) await sleep(250);
    if (!lines.includes(__OWN__)) throw new Error('no own-ship tooltip: ' + lines.slice(0, 8).join(' | '));
    if (!lines.some(isPosition)) throw new Error('no position tooltip');
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
    # Real time, not a virtual-time budget: the map is drawn from the live
    # host's state and chart. The page is read over DevTools and the run ends
    # when the probe reports.
    profile = tmp_path / "browser"
    process = subprocess.Popen([
        chromium, "--headless", "--no-sandbox", "--disable-gpu",
        "--disable-background-networking", "--no-first-run",
        "--no-default-browser-check", "--disable-dev-shm-usage",
        f"--user-data-dir={profile}", "--remote-debugging-port=0",
        f"--window-size={width},{height}", "--force-device-scale-factor=1",
        f"http://{console.address[0]}:{console.address[1]}/",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    host = RealTimeHost(game, profile, period_s=.25)
    root = {}
    started = time.monotonic()
    try:
        while process.poll() is None and time.monotonic() - started < 120:
            root = host.dataset or root
            if root.get("hoverTest"):
                break
            console.pump(game)
            host.step()
            time.sleep(.02)
    finally:
        host.close()
        process.kill()
        process.wait(timeout=5)
        console.stop()
        game.audio.shutdown()
    assert root.get("hoverTest") == "passed", root.get("failure", root)
