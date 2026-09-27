"""Browser contract of the state push: the console runs on pushed states,
falls back to polling when the push drops and picks it up again (Chromium)."""

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
  let statePolls = 0;
  const nativeFetch = window.fetch;
  window.fetch = async (...args) => {
    const response = await nativeFetch(...args);
    if (String(args[0]).includes('/api/v2/state') && response.status === 200) statePolls++;
    return response;
  };
  // Virtual time races ahead while the page idles; a real round trip every
  // few iterations keeps the waits in step with the host.
  async function until(check, message, limit = 3000) {
    for (let index = 0; index < limit; index++) {
      root.dataset.push = document.body.dataset.push || '';
      root.dataset.connection = $('connection')?.textContent || '';
      if (check()) return;
      if (index % 5 === 0) await nativeFetch('/push-test-tick').catch(() => {});
      await sleep(20);
    }
    throw new Error(typeof message === 'function' ? message() : message);
  }
  const signal = (name) => nativeFetch(`/push-test-${name}`).catch(() => {});
  const pushed = () => document.body.dataset.push === 'on';
  async function run() {
    await until(() => !$('shell').hidden, 'translations');
    $('name').value = 'Push'; $('code').value = __CODE__;
    $('pair-form').requestSubmit();
    await until(() => $('station-tab-bridge'), 'bridge tab');
    $('station-tab-bridge').click();
    root.dataset.stage = 'panel';
    await until(() => document.body.dataset.remoteRole === 'assigned' && !$('station-bridge').hidden, 'bridge panel');
    root.dataset.stage = 'push on';
    await until(pushed, 'push never connected');
    // Pushed states drive the console: the /state polls slow down while the
    // push is healthy (the loop keeps polling presence, chart and feeds).
    const before = statePolls;
    await sleep(6000);
    root.dataset.pollsWhilePushed = String(statePolls - before);
    root.dataset.stage = 'host drops push';
    await signal('drop');
    await until(() => !pushed(), 'push still on after the host switched it off', 6000);
    root.dataset.stage = 'polling fallback';
    const polledBefore = statePolls;
    await until(() => statePolls >= polledBefore + 4, 'no state polls after the push dropped', 6000);
    if (!$('connection').textContent.includes('Connected')) throw new Error(`not connected: ${$('connection').textContent}`);
    root.dataset.stage = 'push back';
    await signal('restore');
    await until(pushed, 'push not retried after the host switched it on', 6000);
    const timing = window.uJagdChartTiming || {frames: 0, totalMs: 0, maxMs: 0};
    root.dataset.chartFrames = String(timing.frames);
    root.dataset.chartMeanMs = String(timing.frames ? timing.totalMs / timing.frames : 0);
    root.dataset.chartMaxMs = String(timing.maxMs);
  }
  run().then(() => { root.dataset.pushTest = 'passed'; }, (error) => {
    root.dataset.pushTest = 'failed';
    root.dataset.failure = String(error.stack || error);
  });
})();
'''


def test_console_runs_on_pushed_state_and_falls_back_to_polling(tmp_path, monkeypatch):
    chromium = (shutil.which("chromium") or shutil.which("chromium-browser")
                or shutil.which("google-chrome"))
    if not chromium:
        pytest.skip("Optional state push browser contract: no Chromium")
    en, de = catalogs()
    game = Game(seed=919, start_menu=False, audio_enabled=False, language="en")
    console = game.commander
    console.port = 0
    console._translations = {
        "en": {key: value for key, value in en.items() if key.startswith(PREFIX)},
        "de": {key: value for key, value in de.items() if key.startswith(PREFIX)},
    }
    console._contact_analysis_assets = {}
    console._manual_pages = {}
    html = inject_probe(index_html(), "push-test.js")
    copy_assets(tmp_path, html)
    monkeypatch.setattr(server.resources, "files", lambda _package: tmp_path)
    console.activate(game)
    console.server._http.assets["/push-test.js"] = (
        "text/javascript; charset=utf-8",
        PROBE.replace("__CODE__", json.dumps(console.pairing_code)).encode("utf-8"))

    class Signals(dict):
        """The probe reaches the host by fetching tiny assets; the lookups
        are the signal (the transport threads never touch the game)."""

        def __init__(self, assets):
            super().__init__(assets)
            self.seen = set()
            for name in ("tick", "drop", "restore"):
                self[f"/push-test-{name}"] = ("text/plain; charset=utf-8", b"ok")

        def __contains__(self, key):
            if isinstance(key, str) and key.startswith("/push-test-"):
                self.seen.add(key)
            return super().__contains__(key)

    signals = Signals(console.server._http.assets)
    console.server._http.assets = signals
    console.bridge.allowed = True
    process = subprocess.Popen([
        chromium, "--headless", "--no-sandbox", "--disable-gpu",
        "--disable-background-networking", "--no-first-run",
        "--no-default-browser-check", "--disable-dev-shm-usage",
        f"--user-data-dir={tmp_path / 'browser'}", "--window-size=2560,1440",
        "--force-device-scale-factor=1",
        "--virtual-time-budget=300000", "--dump-dom",
        f"http://{console.address[0]}:{console.address[1]}/",
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    started = time.monotonic()
    granted = False
    dropped = restored = False
    push_seen = 0
    try:
        while process.poll() is None and time.monotonic() - started < 150:
            if not granted:
                clients = console.server.client_statuses()
                if clients:
                    assert console.server.grant_station(clients[0]["client_id"], "bridge")
                    granted = True
            push_seen = max(push_seen, console.server.state_push_clients())
            # The probe signals the host through asset fetches: drop the push
            # once the browser ran on it, restore it later.
            if push_seen and not dropped and "/push-test-drop" in signals.seen:
                console.server.set_state_push(False)
                dropped = True
            elif dropped and not restored and "/push-test-restore" in signals.seen:
                console.server.set_state_push(True)
                restored = True
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
    assert root.get("data-push-test") == "passed", (
        root.get("data-stage"), root.get("data-push"), root.get("data-connection"),
        root.get("data-failure", stderr[-400:]), push_seen, dropped, restored)
    assert push_seen >= 1 and dropped and restored
    # Chart frame time at 2560x1440 (software rendering in headless Chromium):
    # logged for the hardware checklist, sanity-bounded here.
    frames = int(root.get("data-chart-frames", "0"))
    mean_ms = float(root.get("data-chart-mean-ms", "0"))
    print(f"chart frames={frames} mean_ms={mean_ms:.2f} max_ms={root.get('data-chart-max-ms')}")
    assert frames >= 1 and mean_ms < 50.0
    assert int(root.get("data-polls-while-pushed", "99")) <= 6
