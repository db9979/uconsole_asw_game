"""Own missions in the Remote Crew browser: the solo host plans a mission,
saves it to the uConsole's library, finds it in the list and starts it."""

import json
from pathlib import Path
import shutil
import subprocess
import time

import pytest
from commander_web import copy_assets, index_html, inject_probe

from src.commander import server
from src.core.game import Game
from test_commander_assets import Document, PREFIX, catalogs

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
  const errors = [];
  window.addEventListener('error', (event) => errors.push(String(event.message)));
  window.addEventListener('unhandledrejection', (event) => errors.push(String(event.reason)));
  const overflow = (element) => element.scrollWidth > element.clientWidth + 1;
  // The start order must reach the host before the probe reports, or the
  // browser may exit with the request still unsent.
  let startAnswered = false;
  const realFetch = window.fetch.bind(window);
  window.fetch = (url, options = {}) => {
    const reply = realFetch(url, options);
    if (String(options.body || '').includes('host_start_mission'))
      reply.then(() => { startAnswered = true; }, () => {});
    return reply;
  };
  async function run() {
    await until(() => !$('shell').hidden, 'translations');
    $('name').value = 'Planner'; $('code').value = __CODE__;
    $('pair-form').requestSubmit();
    await until(() => !$('host-bar').hidden && !$('host-missions').disabled, 'missions button', 3000);
    $('host-missions').click();
    const dialog = $('missions-dialog');
    await until(() => dialog.open && !$('missions-empty').hidden, 'empty library');
    $('missions-new').click();
    await until(() => !$('missions-editor').hidden && $('missions-panel').querySelector('input'), 'editor');
    const key = $('missions-panel').querySelector('input');
    key.value = 'user.browser_plan';
    key.dispatchEvent(new Event('change'));
    const name = $('missions-panel').querySelectorAll('input')[1];
    name.value = 'Browser plan';
    name.dispatchEvent(new Event('change'));
    for (const tab of ['world', 'units', 'objective', 'events', 'overview']) {
      $(`missions-tab-${tab}`).click();
      await until(() => $(`missions-tab-${tab}`).getAttribute('aria-selected') === 'true', `tab ${tab}`);
      if (overflow(dialog)) throw new Error(`horizontal overflow on ${tab}`);
    }
    const canvas = $('missions-map');
    await until(() => canvas.width > 50 && canvas.height > 50, 'map size');
    $('missions-save').click();
    await until(() => $('missions-status').dataset.status === 'applied', 'saved', 1500);
    $('missions-back').click();
    await until(() => $('missions-list').querySelectorAll('li').length === 1, 'listed', 1500);
    const row = $('missions-list').querySelector('li');
    if (!row.textContent.includes('Browser plan')) throw new Error('row name');
    const start = row.querySelector('.missions-row-actions button.primary');
    if (start.disabled) throw new Error('start disabled');
    start.click();
    await until(() => !dialog.open, 'dialog closes on start', 1500);
    await until(() => startAnswered, 'start order answered', 1500);
  }
  run().then(() => document.documentElement.dataset.missionsTest = 'passed', (error) => {
    document.documentElement.dataset.missionsTest = 'failed';
    document.documentElement.dataset.failure = String(error.stack || error) + ' ' + errors.join(' | ');
  });
})();
'''


@pytest.mark.parametrize("width,height", [(1600, 1000), (420, 900)])
def test_solo_host_plans_saves_and_starts_an_own_mission(tmp_path, monkeypatch, width, height):
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
    console._manual_pages = {}
    html = inject_probe(index_html(), "missions-test.js")
    copy_assets(tmp_path, html)
    # Only the web client is served from the copy; catalogs and coasts stay packaged.
    original = server.resources.files
    monkeypatch.setattr(server.resources, "files",
                        lambda package: tmp_path if package == "data.commander" else original(package))
    console.activate(game)
    console.server._http.assets["/missions-test.js"] = (
        "text/javascript; charset=utf-8",
        PROBE.replace("__CODE__", json.dumps(console.pairing_code)).encode("utf-8"))
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
        # The browser may exit right after its start request was queued;
        # apply what reached the host before judging the result.
        settle = time.monotonic()
        while (game.custom_mission_definition is None
               and time.monotonic() - settle < 3):
            console.pump(game)
            game.update(.02)
            time.sleep(.02)
    finally:
        if process.poll() is None:
            process.kill()
            stdout, stderr = process.communicate(timeout=5)
        console.stop()
        game.audio.shutdown()
    assert process.returncode == 0, stderr
    root = next((attrs for tag, attrs in Document(stdout).elements if tag == "html"), {})
    assert root.get("data-missions-test") == "passed", root.get("data-failure", stderr[-2000:])
    assert (game.custom_mission_definition or {}).get("key") == "user.browser_plan"
