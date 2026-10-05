"""Browser contract of the observer role: read-only station views and the
debrief timeline with export in the SimLog page (Chromium)."""

import json
import shutil
import subprocess
import sys
import time
from dataclasses import replace
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
  const nativeFetch = window.fetch;
  async function until(check, message, limit = 3000) {
    for (let index = 0; index < limit; index++) {
      root.dataset.observer = document.body.dataset.observer || '';
      root.dataset.lobby = $('lobby-status')?.textContent || '';
      if (check()) return;
      if (index % 5 === 0) await nativeFetch('/observer-test-tick').catch(() => {});
      await sleep(20);
    }
    throw new Error(typeof message === 'function' ? message() : message);
  }
  async function run() {
    await until(() => !$('shell').hidden, 'translations');
    $('name').value = 'Observer'; $('code').value = __CODE__;
    $('pair-form').requestSubmit();
    root.dataset.stage = 'observer grant';
    await until(() => document.body.dataset.observer === 'true', 'never became an observer');
    root.dataset.stage = 'view bridge';
    const card = document.querySelector('#station-cards section[data-station="bridge"]');
    await until(() => card && !card.hidden && !card.querySelector('button').disabled, 'bridge card not offered');
    card.querySelector('button').click();
    await until(() => document.body.dataset.remoteRole === 'assigned' && !$('station-bridge').hidden, 'bridge view not shown');
    await until(() => $('role-grants').textContent.length > 0, 'role text');
    root.dataset.roleText = $('role-grants').textContent;
    if (!$('navigation-course').disabled) throw new Error('bridge controls enabled for an observer');
    root.dataset.stage = 'both sides';
    const opfor = document.querySelector('#side-choice button[data-side="opfor"]');
    if (opfor.disabled) throw new Error('observer cannot look at the other unit');
    root.dataset.stage = 'simlog';
    location.hash = '#simlog';
    await until(() => !$('simlog-view').hidden, 'SimLog view missing');
    await until(() => !$('simlog-timeline-section').hidden && $('simlog-timeline').querySelectorAll('.simlog-tick').length >= 2,
      () => `timeline not rendered: ${$('simlog-status').textContent} count=${$('simlog-count').textContent}`, 6000);
    root.dataset.ticks = String($('simlog-timeline').querySelectorAll('.simlog-tick').length);
    root.dataset.marks = String($('simlog-timeline').querySelectorAll('.simlog-mark').length);
    if ($('simlog-export').hidden) throw new Error('export hidden for an observer');
    const first = $('simlog-timeline').querySelector('.simlog-tick');
    first.click();
    await until(() => first.getAttribute('aria-pressed') === 'true', 'scrubbing did not select the entry');
    root.dataset.scrubbed = first.dataset.seq;
    // Export builds a JSON blob without secrets (checked through the module hook).
    let exported = null;
    const nativeCreate = URL.createObjectURL;
    URL.createObjectURL = (blob) => { exported = blob; return 'blob:test'; };
    $('simlog-export').click();
    await until(() => exported !== null, 'export produced no blob');
    URL.createObjectURL = nativeCreate;
    const text = await exported.text();
    const payload = JSON.parse(text);
    root.dataset.exportKind = payload.kind;
    root.dataset.exportEntries = String(payload.entries.length);
    const forbidden = ['"rng"', '"seed"', '"csrf"', '"cookie"', '"token"', '"settings"', '"credential'];
    for (const word of forbidden) if (text.includes(word)) throw new Error(`export carries ${word}`);
  }
  run().then(() => { root.dataset.observerTest = 'passed'; }, (error) => {
    root.dataset.observerTest = 'failed';
    root.dataset.failure = String(error.stack || error);
  });
})();
'''


def test_observer_views_read_only_and_debriefs_in_the_browser(tmp_path, monkeypatch):
    chromium = (shutil.which("chromium") or shutil.which("chromium-browser")
                or shutil.which("google-chrome"))
    if not chromium:
        pytest.skip("Optional observer browser contract: no Chromium")
    en, de = catalogs()
    game = Game(seed=921, start_menu=False, audio_enabled=False, language="en")
    game.preferences = replace(game.preferences, simlog=True)
    console = game.commander
    console.port = 0
    console._translations = {
        "en": {key: value for key, value in en.items() if key.startswith(PREFIX)},
        "de": {key: value for key, value in de.items() if key.startswith(PREFIX)},
    }
    console._contact_analysis_assets = {}
    console._manual_pages = {}
    html = inject_probe(index_html(), "observer-test.js")
    copy_assets(tmp_path, html)
    monkeypatch.setattr(server.resources, "files", lambda _package: tmp_path)
    console.activate(game)
    console.server._http.assets["/observer-test.js"] = (
        "text/javascript; charset=utf-8",
        PROBE.replace("__CODE__", json.dumps(console.pairing_code)).encode("utf-8"))
    console.server._http.assets["/observer-test-tick"] = ("text/plain; charset=utf-8", b"ok")
    console.bridge.allowed = True
    # Real time, not a virtual-time budget: the timeline needs SimLog entries
    # the live host writes every SIMLOG_INTERVAL_S of simulation, and virtual
    # time ran ahead of a host loop slowed by a loaded runner ("timeline not
    # rendered"). The page is read over DevTools and the run ends when the
    # probe reports.
    profile = tmp_path / "browser"
    process = subprocess.Popen([
        chromium, "--headless", "--no-sandbox", "--disable-gpu",
        "--disable-background-networking", "--no-first-run",
        "--no-default-browser-check", "--disable-dev-shm-usage",
        f"--user-data-dir={profile}", "--window-size=1920,1080",
        "--force-device-scale-factor=1", "--remote-debugging-port=0",
        f"http://{console.address[0]}:{console.address[1]}/",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    host = RealTimeHost(game, profile, period_s=.25)
    root = {}
    started = time.monotonic()
    granted = False
    try:
        while process.poll() is None and time.monotonic() - started < 150:
            root = host.dataset or root
            if root.get("observerTest"):
                break
            if not granted:
                clients = console.server.client_statuses()
                if clients:
                    assert console.server.set_client_grant(clients[0]["client_id"], "observer", True)
                    granted = True
            console.pump(game)
            host.step()
            time.sleep(.02)
    finally:
        host.close()
        process.kill()
        process.wait(timeout=5)
        console.stop()
        game.audio.shutdown()
    assert root.get("observerTest") == "passed", (
        root.get("stage"), root.get("observer"), root.get("lobby"), root.get("failure"))
    assert granted and console.server.observer_count() == 0     # revoked with the stop
    assert int(root.get("ticks", "0")) >= 2
    assert root.get("exportKind") == "u-jagd-debrief"
    assert int(root.get("exportEntries", "0")) >= 2
    assert "read-only" in root.get("roleText", "").lower() or "observer" in root.get("roleText", "").lower()
