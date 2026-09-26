"""Bridge-lookout reports on the Remote Crew bridge (browser rendering)."""

import json
import random
from pathlib import Path
import shutil
import subprocess
import time

import pytest
from commander_web import copy_assets, index_html, inject_probe

from src.commander import server
from src.core.game import Game
from src.enemies.surface import SurfaceShip
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
    $('name').value = 'Lookout'; $('code').value = __CODE__;
    $('pair-form').requestSubmit();
    await until(() => $('station-tab-bridge'), 'station tabs');
    $('station-tab-bridge').click();
    await until(() => !$('operations').hidden && !$('station-bridge').hidden, 'bridge shown');
    const list = $('bridge-sightings');
    await until(() => [...list.children].some((item) => item.textContent.includes(__FRIGATE__)), 'frigate report', 3000);
    const text = list.textContent;
    if (!text.includes('Admiral-Gorshkov-Fregatte') || !text.includes('°')) throw new Error(`report text: ${text}`);
    const tactical = $('bridge-tactical').textContent;
    if (!tactical.includes(__SIGHTING__)) throw new Error('tactical row without lookout class');
    const card = list.closest('.station-card-view');
    if (card.scrollWidth > card.clientWidth + 1) throw new Error('horizontal overflow');
  }
  run().then(() => document.documentElement.dataset.lookoutTest = 'passed', (error) => {
    document.documentElement.dataset.lookoutTest = 'failed';
    document.documentElement.dataset.failure = String(error.stack || error);
  });
})();
'''


@pytest.mark.parametrize("width,height", [(1600, 1000), (420, 900)])
def test_web_bridge_lists_lookout_reports_with_class_and_type(
        tmp_path, monkeypatch, width, height):
    chromium = (shutil.which("chromium") or shutil.which("chromium-browser")
                or shutil.which("google-chrome"))
    if not chromium:
        pytest.skip("Optional browser contract: no Chromium")
    en, de = catalogs()
    game = Game(seed=4242, start_menu=False, audio_enabled=False, language="en")
    game.world.land_blocks_line = lambda *args: False
    frigate = SurfaceShip(game.ship.x + 1.5, game.ship.y, random.Random(41),
                          profile=game.runtime_catalog.surfaces["warship_24"],
                          runtime_catalog=game.runtime_catalog)
    frigate.speed = frigate.target_speed = 0.0
    game.warships = [frigate]
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
    html = inject_probe(index_html(), "lookout-test.js")
    copy_assets(tmp_path, html)
    monkeypatch.setattr(server.resources, "files", lambda _package: tmp_path)
    console.activate(game)
    console.server._http.assets["/lookout-test.js"] = (
        "text/javascript; charset=utf-8",
        PROBE.replace("__CODE__", json.dumps(console.pairing_code))
        .replace("__FRIGATE__", json.dumps(en[PREFIX + "sighting_class_frigate"]))
        .replace("__SIGHTING__", json.dumps(en[PREFIX + "sighting"])).encode("utf-8"))
    console.bridge.allowed = True
    process = subprocess.Popen([
        chromium, "--headless", "--no-sandbox", "--disable-gpu",
        "--disable-background-networking", "--no-first-run",
        "--no-default-browser-check", "--disable-dev-shm-usage",
        f"--user-data-dir={tmp_path / 'browser'}", "--virtual-time-budget=150000",
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
    assert root.get("data-lookout-test") == "passed", root.get("data-failure", stderr[-2000:])
