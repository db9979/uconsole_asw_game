"""Browser contract of the boat's route, dead reckoning and seeker settings (Chromium)."""

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from commander_web import RealTimeHost, copy_assets, index_html, inject_probe

from src.commander import server
from src.core.game import Game
from test_commander_assets import PREFIX, catalogs

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
  async function nav() {
    await until(() => !$('uboot-route-status').closest('[hidden]') && $('uboot-route-status').textContent,
      'route status hidden');
    await until(() => $('uboot-navigation').textContent.includes('±'), () => `dr: ${$('uboot-navigation').textContent}`);
    $('uboot-route-zigzag').click();
    await until(() => $('uboot-route-status').textContent.includes('Zigzag'),
      () => `route: ${$('uboot-route-status').textContent}`);
    if ($('uboot-route-clear').disabled) throw new Error('clear not offered');
    root.dataset.route = $('uboot-route-status').textContent;
    // The echo sounder: its strip is shown and drawn, its least-clearance line set.
    await until(() => $('uboot-sounder-text').textContent.includes('m'), () => `sounder: ${$('uboot-sounder-text').textContent}`);
    const canvas = $('uboot-sounder-canvas');
    if (canvas.closest('[hidden]') || canvas.clientHeight < 100) throw new Error('sounder hidden');
    const pixels = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
    const colors = new Set();
    for (let index = 0; index < pixels.length; index += 4 * 37)
      colors.add(`${pixels[index]},${pixels[index + 1]},${pixels[index + 2]}`);
    if (colors.size < 4) throw new Error(`flat sounder: ${colors.size} colours`);
  }
  async function weapons() {
    await until(() => !$('uboot-seeker-pattern').closest('[hidden]') && $('uboot-seeker-enable').value === '3',
      () => `seeker: ${$('uboot-seeker-enable').value}`);
    if ($('uboot-seeker-pattern').value !== 'straight') throw new Error(`pattern ${$('uboot-seeker-pattern').value}`);
    $('uboot-seeker-pattern').value = 'circle';
    $('uboot-seeker-pattern').dispatchEvent(new Event('change'));
    $('uboot-seeker-enable').value = '1.6';
    $('uboot-seeker-enable').dispatchEvent(new Event('input'));
    $('uboot-seeker-apply').click();
    await sleep(1500);
    if ($('uboot-seeker-pattern').value !== 'circle') throw new Error('pattern reverted');
  }
  async function run() {
    await until(() => !$('shell').hidden, 'translations');
    $('name').value = 'Nav'; $('code').value = __CODE__;
    $('pair-form').requestSubmit();
    await until(() => $('station-tab-__ROLE__'), 'station tab');
    $('station-tab-__ROLE__').click();
    await until(() => document.body.dataset.remoteRole === 'assigned', 'not assigned');
    if ('__ROLE__' === 'uboot_nav') await nav(); else await weapons();
    if (document.documentElement.scrollWidth > innerWidth) throw new Error('page overflows');
  }
  run().then(() => { root.dataset.navTest = 'passed'; }, (error) => {
    root.dataset.navTest = 'failed';
    root.dataset.failure = String(error.stack || error);
  });
})();
'''


@pytest.mark.parametrize("role", ["uboot_nav", "uboot_weapons"])
def test_route_dead_reckoning_and_seeker_in_the_browser(tmp_path, monkeypatch, role):
    chromium = (shutil.which("chromium") or shutil.which("chromium-browser")
                or shutil.which("google-chrome"))
    if not chromium:
        pytest.skip("Optional boat navigation browser contract: no Chromium")
    en, de = catalogs()
    game = Game(seed=1234, start_menu=False, audio_enabled=False, language="en")
    game.reset(1234, "s7_geleitzug")
    console = game.commander
    console.port = 0
    console._translations = {
        "en": {key: value for key, value in en.items() if key.startswith(PREFIX)},
        "de": {key: value for key, value in de.items() if key.startswith(PREFIX)},
    }
    console._contact_analysis_assets = {}
    console._manual_pages = {}
    html = inject_probe(index_html(), "nav-test.js")
    copy_assets(tmp_path, html)
    monkeypatch.setattr(server.resources, "files", lambda _package: tmp_path)
    console.activate(game)
    console.server._http.assets["/nav-test.js"] = (
        "text/javascript; charset=utf-8",
        PROBE.replace("__CODE__", json.dumps(console.pairing_code))
        .replace("__ROLE__", role).encode("utf-8"))
    console.bridge.allowed = True
    # Real time, not a virtual-time budget: the probe races a live host, and
    # waiting for Chromium to burn a fixed virtual budget took about the whole
    # wall-clock cap even on an idle machine, so a loaded runner ran out of time
    # (subprocess.TimeoutExpired). The page's result is read over DevTools and
    # the run ends as soon as the probe reports.
    profile = tmp_path / "browser"
    process = subprocess.Popen([
        chromium, "--headless", "--no-sandbox", "--disable-gpu",
        "--disable-background-networking", "--no-first-run",
        "--no-default-browser-check", "--disable-dev-shm-usage",
        f"--user-data-dir={profile}", "--window-size=1600,1000",
        "--force-device-scale-factor=1", "--remote-debugging-port=0",
        f"http://{console.address[0]}:{console.address[1]}/",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    host = RealTimeHost(game, profile, period_s=.25)
    root = {}
    granted = False
    boat = None
    started = time.monotonic()
    try:
        while process.poll() is None and time.monotonic() - started < 180:
            root = host.dataset or root
            if root.get("navTest"):
                break
            if not granted:
                clients = console.server.client_statuses()
                if clients:
                    client = clients[0]["client_id"]
                    assert console.server.grant_station(client, role)
                    assert console.server.set_client_grant(client, role, "command", True)
                    granted = True
            if game.opfor is not None:
                boat = game.opfor
                boat.orders.nav[2] = max(boat.orders.nav[2], 1800.0)
            console.pump(game)
            host.step()
            time.sleep(.02)
    finally:
        host.close()
        process.kill()
        process.wait(timeout=5)
        console.stop()
        game.audio.shutdown()
    assert root.get("navTest") == "passed", (root.get("jsError"), root.get("failure"))
    orders = boat.orders
    if role == "uboot_nav":
        assert orders.route.kind == "zigzag" and orders.route.active
    else:
        assert (orders.torpedo_pattern, orders.torpedo_enable_nm) == ("circle", 1.6)
