"""Browser contract of the periscope view of the crewed boat (Chromium)."""

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
from src.core import config
from src.core.game import Game
from src.sensors.platform import MAST_DEPTH_M
from test_commander_assets import Document, PREFIX, catalogs

sys.path.insert(0, str(Path(__file__).parent))


PROBE = r'''
(() => {
  const $ = (id) => document.getElementById(id);
  const root = document.documentElement;
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  async function until(check, message, limit = 3000) {
    for (let index = 0; index < limit; index++) {
      root.dataset.status = $('uboot-scope-status')?.textContent || '';
      root.dataset.command = `${$('command-status')?.textContent || ''} | ${$('station-command-status')?.textContent || ''}`;
      root.dataset.clock = `virtual=${Math.round(performance.now())} wall=${Date.now() - wallStart} connection=${$('connection')?.textContent} role=${document.body.dataset.remoteRole}`;
      if (check()) return;
      await sleep(20);
    }
    throw new Error(typeof message === 'function' ? message() : message);
  }
  const status = () => $('uboot-scope-status').textContent;
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
    $('name').value = 'Mast'; $('code').value = __CODE__;
    $('pair-form').requestSubmit();
    await until(() => $('station-tab-uboot_esm'), 'mast station tab');
    $('station-tab-uboot_esm').click();
    root.dataset.stage = 'panel';
    await until(() => document.body.dataset.remoteRole === 'assigned' &&
      !$('station-uboot').hidden && !$('uboot-scope-canvas').closest('[hidden]'), 'scope card');
    await until(() => status().length > 0, 'scope status');
    // An order goes out only while the browser's command context is current
    // (chart, epoch, no pending command); like an operator, press again
    // until the state confirms it.
    async function order(act, check, message) {
      for (let attempt = 0; attempt < 30; attempt++) {
        act();
        for (let tick = 0; tick < 100; tick++) {
          if (check()) return;
          await sleep(20);
        }
      }
      throw new Error(typeof message === 'function' ? message() : message);
    }
    root.dataset.stage = 'mast up';
    const mastUp = document.querySelector('[data-uboot-mode="uboot_mast"][data-enabled="true"]');
    await until(() => mastUp.dataset.ready === 'true', 'boat not at periscope depth in the browser');
    await order(() => mastUp.click(), () => status().includes('Line of sight'), () => `scope stays dark: ${status()}`);
    root.dataset.stage = 'train';
    await order(() => document.querySelector('[data-uboot-scope-turn="2"]').click(),
      () => status().includes('relative 002'), () => `no 2 degree step: ${status()}`);
    await order(() => { $('uboot-scope-relative').value = '090'; $('uboot-scope-form').requestSubmit(); },
      () => status().includes('relative 090'), () => `no trained bearing: ${status()}`);
    root.dataset.stage = 'picture';
    const canvas = $('uboot-scope-canvas');
    const g = canvas.getContext('2d');
    const pixels = g.getImageData(0, 0, canvas.width, canvas.height).data;
    const colors = new Set();
    for (let index = 0; index < pixels.length; index += 4 * 97)
      colors.add(`${pixels[index]},${pixels[index + 1]},${pixels[index + 2]}`);
    if (colors.size < 4) throw new Error(`flat eyepiece: ${colors.size} colours`);
    root.dataset.stage = 'sighting';
    await order(() => { $('uboot-scope-relative').value = '0'; $('uboot-scope-form').requestSubmit(); },
      () => status().includes('relative 000'), () => `not back ahead: ${status()}`);
    await until(() => $('uboot-sightings').querySelector('.station-row'), 'no sighting listed');
    await until(() => $('uboot-scope-mark').dataset.ready === 'true', 'stadimeter not ready');
    await order(() => $('uboot-scope-mark').click(),
      () => $('uboot-sightings').textContent.includes('NM'), 'no stadimeter range listed');
    root.dataset.rows = String($('uboot-sightings').querySelectorAll('.station-row').length);
  }
  run().then(() => { root.dataset.scopeTest = 'passed'; }, (error) => {
    root.dataset.scopeTest = 'failed';
    root.dataset.failure = String(error.stack || error);
  });
})();
'''


def test_periscope_view_trains_and_reads_the_stadimeter_in_the_browser(tmp_path, monkeypatch):
    chromium = (shutil.which("chromium") or shutil.which("chromium-browser")
                or shutil.which("google-chrome"))
    if not chromium:
        pytest.skip("Optional periscope browser contract: no Chromium")
    en, de = catalogs()
    game = Game(seed=917, start_menu=False, audio_enabled=False, language="en")
    game.world.hour = 12.0
    game._lookout_environment = lambda: dict(
        visibility_nm=config.WEATHER_VISIBILITY_MAX_NM, night=False, illumination=0.1,
        sea_state=1)
    console = game.commander
    console.port = 0
    console._translations = {
        "en": {key: value for key, value in en.items() if key.startswith(PREFIX)},
        "de": {key: value for key, value in de.items() if key.startswith(PREFIX)},
    }
    console._contact_analysis_assets = {}
    console._manual_pages = {}
    html = inject_probe(index_html(), "scope-test.js")
    copy_assets(tmp_path, html)
    monkeypatch.setattr(server.resources, "files", lambda _package: tmp_path)
    console.activate(game)
    console.server._http.assets["/scope-test.js"] = (
        "text/javascript; charset=utf-8",
        PROBE.replace("__CODE__", json.dumps(console.pairing_code)).encode("utf-8"))
    console.bridge.allowed = True
    applied = []
    original_apply = console.bridge._apply_opfor_action

    def recording_apply(game_, action, params, role):
        result = original_apply(game_, action, params, role)
        applied.append((action, params, role, result))
        return result
    console.bridge._apply_opfor_action = recording_apply
    process = subprocess.Popen([
        chromium, "--headless", "--no-sandbox", "--disable-gpu",
        "--disable-background-networking", "--no-first-run",
        "--no-default-browser-check", "--disable-dev-shm-usage",
        f"--user-data-dir={tmp_path / 'browser'}", "--window-size=1600,1000",
        # Presence is refreshed by the client's session polling timer: the
        # virtual-time budget must outlast the whole probe (see the real
        # browser session test), or the lease lapses after 15 s.
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
                    assert console.server.grant_station(client, "uboot_esm")
                    assert console.server.set_client_grant(client, "uboot_esm", "command", True)
                    granted = True
            if game.opfor is not None:
                sub = game.opfor.sub
                if boat is None:
                    # Once: the boat at periscope depth and stopped, the
                    # frigate two miles dead ahead, beam on and stopped (the
                    # picture the optics see; the browser never learns where
                    # it is).  Orders advance the world epoch, so they are
                    # not repeated per frame.
                    boat = game.opfor
                    sub.depth = sub.target_depth = sub.order_depth = MAST_DEPTH_M - 3.0
                    sub.set_orders(speed=0.0)
                    rad = math.radians(sub.course)
                    game.ship.x = sub.x + 2.0 * math.sin(rad)
                    game.ship.y = sub.y - 2.0 * math.cos(rad)
                    game.ship.course = (sub.course + 90.0) % 360.0
                    game.ship.speed = 0.0
                    if hasattr(game.ship, "target_speed"):
                        game.ship.target_speed = 0.0
                elif abs(sub.depth - (MAST_DEPTH_M - 3.0)) > 0.5:
                    sub.depth = sub.target_depth = MAST_DEPTH_M - 3.0
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
        root.get("data-stage"), root.get("data-status"), root.get("data-command"),
        root.get("data-console-error"), root.get("data-failure", stderr[-300:]), applied[:12])
    assert boat is not None and boat.orders.mast
    assert boat.orders.scope_rel_deg == 0.0
    ranged = [row for row in boat.orders.sightings if row["range_nm"] is not None]
    assert ranged and ranged[0]["cls"] in ("warship", "unknown")
    assert int(root.get("data-rows", "0")) >= 1
    assert [row[0] for row in applied][:1] == ["uboot_mast"]
    assert {row[0] for row in applied} == {"uboot_mast", "uboot_scope_bearing", "uboot_scope_mark"}
    assert all(row[2] == "uboot_esm" and row[3] is True for row in applied)
    assert "\u00b0\u00b0" not in root.get("data-status", "")


def test_periscope_card_offers_the_mast_to_its_owner_and_names_it_for_command():
    html = index_html()
    card = html[html.index('class="station-card-view station-wide uboot-scope-card"'):]
    card = card[:card.index("</article>")]
    # Command and the Mast & ESM station raise the mast from the periscope card itself.
    assert 'data-uboot-stations="uboot uboot_esm"><button type="button" data-uboot-mode="uboot_mast" data-enabled="true"' in card
    assert 'data-uboot-mode="uboot_mast" data-enabled="false"' in card
    # The hint still names the other station that can raise it.
    for catalog in catalogs():
        assert "ESM" in catalog["commander.web.uboot_scope_mast_down"]
