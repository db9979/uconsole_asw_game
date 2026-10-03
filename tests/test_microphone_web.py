"""Noise discipline in the crew browser: on plain HTTP the microphone is
refused by every browser, so the page says so where it can be read and
offers the switch to the host's HTTPS page."""

import json
from pathlib import Path
import shutil
import subprocess
import time

import pytest
from commander_web import RealTimeHost, copy_assets, index_html, inject_probe

from src.commander import server
from src.core.game import Game
from test_commander_assets import PREFIX, catalogs

PROBE = r'''
(() => {
  // The host listens on loopback, which browsers already trust: stand in
  // for a LAN address on plain HTTP.
  Object.defineProperty(window, 'isSecureContext', {get: () => false});
  const $ = (id) => document.getElementById(id);
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  async function until(check, message, limit_ms = 30000) {
    const deadline = Date.now() + limit_ms;
    while (Date.now() < deadline) {
      if (check()) return;
      await sleep(20);
    }
    const group = $('mic-discipline');
    throw new Error(`${message} (mic group hidden=${group?.hidden}, rects=${group?.getClientRects().length})`);
  }
  const visible = (id) => {
    const node = $(id);
    return node && !node.hidden && node.getClientRects().length > 0;
  };
  async function run() {
    await until(() => !$('shell').hidden, 'translations');
    $('name').value = 'Mic'; $('code').value = __CODE__;
    $('pair-form').requestSubmit();
    await until(() => $('station-tab-bridge'), 'station tabs');
    $('station-tab-bridge').click();
    await until(() => visible('mic-discipline'), 'mic group');
    if (visible('mic-problem')) throw new Error('problem shown before any try');
    $('mic-toggle').click();
    await until(() => visible('mic-problem') && visible('mic-secure'), 'https offer');
    const text = $('mic-problem-text').textContent;
    if (!text.includes(__NEEDS__) || !text.includes(__HINT__)) throw new Error('text: ' + text);
    // The box hangs below the header and never widens the page.
    if (document.documentElement.scrollWidth > innerWidth) throw new Error('page scrolls sideways');
    $('mic-problem-close').click();
    await until(() => !visible('mic-problem'), 'closed');
    $('mic-toggle').click();
    await until(() => visible('mic-problem'), 'shown again on a new try');
    document.documentElement.dataset.micTest = 'shown';
    // Switching frees the stations (logout) before the HTTPS page loads;
    // the host reads the result first.
    await sleep(2000);
    $('mic-secure').click();
  }
  run().catch((error) => {
    document.documentElement.dataset.micTest = 'failed';
    document.documentElement.dataset.failure = String(error.stack || error);
  });
})();
'''


@pytest.mark.parametrize("width,height", [(1280, 720), (1600, 1000)])
def test_plain_http_page_offers_the_https_page_for_the_microphone(
        tmp_path, monkeypatch, width, height):
    chromium = (shutil.which("chromium") or shutil.which("chromium-browser")
                or shutil.which("google-chrome"))
    if not chromium:
        pytest.skip("Optional browser contract: no Chromium")
    en, de = catalogs()
    game = Game(seed=4243, start_menu=False, audio_enabled=False, language="en")
    console = game.commander
    console.solo = True
    console.port = 0
    console._translations = {
        "en": {key: value for key, value in en.items() if key.startswith(PREFIX)},
        "de": {key: value for key, value in de.items() if key.startswith(PREFIX)},
    }
    console._contact_analysis_assets = {}
    console._manual_pages = {}
    html = inject_probe(index_html(), "mic-test.js")
    copy_assets(tmp_path, html)
    monkeypatch.setattr(server.resources, "files", lambda _package: tmp_path)
    console.activate(game)
    assert console.tls_address is not None, console.tls_error
    console.server._http.assets["/mic-test.js"] = (
        "text/javascript; charset=utf-8",
        PROBE.replace("__CODE__", json.dumps(console.pairing_code))
        .replace("__NEEDS__", json.dumps(en[PREFIX + "mic_needs_https"]))
        .replace("__HINT__", json.dumps(en[PREFIX + "mic_secure_hint"])).encode("utf-8"))
    console.bridge.allowed = True
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
    shown = False
    logged_out = False
    started = time.monotonic()
    try:
        while process.poll() is None and time.monotonic() - started < 120:
            root = host.dataset or root
            if root.get("micTest") == "failed":
                break
            shown = shown or root.get("micTest") == "shown"
            console.pump(game)
            host.step()
            if shown and not console.server.client_statuses():
                logged_out = True
                break
            time.sleep(.02)
    finally:
        host.close()
        process.kill()
        process.wait(timeout=5)
        console.stop()
        game.audio.shutdown()
    assert shown, root.get("failure", root)
    assert logged_out
