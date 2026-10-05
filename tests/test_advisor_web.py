"""The executive officer in the Remote Crew browser: the button appears only
with the host's language model on, a situation report comes back, and a
typed order runs only after the player gives it, as ordinary station
commands."""

import dataclasses
import json
import shutil
import subprocess
import time

import pytest
from commander_web import copy_assets, index_html, inject_probe

from src.commander import server
from src.core.game import Game
from test_commander_assets import Document, PREFIX, catalogs
from llm_fake import FakeLlmServer

PROBE = r'''
(() => {
  const $ = (id) => document.getElementById(id);
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  async function until(check, message, limit = 1500) {
    for (let index = 0; index < limit; index++) {
      if (check()) return;
      await sleep(20);
    }
    throw new Error(message);
  }
  const errors = [];
  window.addEventListener('error', (event) => errors.push(String(event.message)));
  window.addEventListener('unhandledrejection', (event) => errors.push(String(event.reason)));
  async function run() {
    await until(() => !$('shell').hidden, 'translations');
    $('name').value = 'XO'; $('code').value = __CODE__;
    $('pair-form').requestSubmit();
    await until(() => !$('advisor-open').hidden, 'advisor button', 3000);
    // The header button stays on one line (it was squeezed into a letter column).
    const button = $('advisor-open').getBoundingClientRect();
    if (button.height > 48 || button.width < button.height)
      throw new Error(`advisor button squeezed: ${Math.round(button.width)}x${Math.round(button.height)}`);
    $('advisor-open').click();
    const dialog = $('advisor-dialog');
    await until(() => dialog.open, 'dialog');
    $('advisor-send').click();
    await until(() => $('advisor-log').textContent.includes('All quiet'), 'situation answer', 3000);
    dialog.querySelector('[data-advisor-mode="order"]').click();
    await until(() => !$('advisor-text').hidden, 'order field');
    $('advisor-text').value = 'come to 120';
    $('advisor-send').click();
    let give = null;
    await until(() => {
      give = [...$('advisor-log').querySelectorAll('button')].find((b) => !b.disabled);
      return give;
    }, 'order proposal', 3000);
    give.click();
    await until(() => $('advisor-status').textContent.length > 0 &&
      $('advisor-log').textContent.length > 0 && !$('advisor-log').querySelector('button'), 'order given', 3000);
    // "Given" only means sent: wait until the host applied it to the ship.
    let ordered = null;
    for (let index = 0; index < 300 && ordered !== 120; index++) {
      try {
        const state = await (await fetch('/api/v2/state', {credentials: 'same-origin'})).json();
        const find = (value) => {
          if (!value || typeof value !== 'object') return null;
          if (typeof value.target_course === 'number') return value.target_course;
          for (const item of Object.values(value)) { const hit = find(item); if (hit !== null) return hit; }
          return null;
        };
        ordered = find(state);
        if (ordered !== null) ordered = Math.round(ordered);
      } catch (_) {}
      if (ordered !== 120) await sleep(100);
    }
    if (ordered !== 120)
      throw new Error(`order not applied: target course ${ordered}, status "${$('advisor-status').textContent}", ` +
        `command "${$('command-status').textContent}" (${$('command-status').dataset.status})`);
  }
  run().then(() => document.documentElement.dataset.advisorTest = 'passed', (error) => {
    document.documentElement.dataset.advisorTest = 'failed';
    document.documentElement.dataset.failure = String(error.stack || error) + ' ' + errors.join(' | ');
  });
})();
'''


def _reply(body):
    if body.get("response_format"):
        return json.dumps({"commands": [{"type": "course", "value": 120}], "say": "Course 120."})
    return "All quiet, two merchants."


def test_browser_asks_the_executive_officer_and_gives_a_confirmed_order(tmp_path, monkeypatch):
    chromium = (shutil.which("chromium") or shutil.which("chromium-browser")
                or shutil.which("google-chrome"))
    if not chromium:
        pytest.skip("Optional browser contract: no Chromium")
    en, de = catalogs()
    with FakeLlmServer(_reply) as llm:
        game = Game(seed=4243, start_menu=False, audio_enabled=False, language="en")
        game.preferences = dataclasses.replace(game.preferences, llm_enabled=True,
                                               llm_url=llm.url, llm_model="m")
        game.configure_llm()
        console = game.commander
        console.solo = True
        console.port = 0
        console._translations = {
            "en": {key: value for key, value in en.items() if key.startswith(PREFIX)},
            "de": {key: value for key, value in de.items() if key.startswith(PREFIX)},
        }
        console._contact_analysis_assets = {}
        console._manual_pages = {}
        html = inject_probe(index_html(), "advisor-test.js")
        copy_assets(tmp_path, html)
        original = server.resources.files
        monkeypatch.setattr(server.resources, "files",
                            lambda package: tmp_path if package == "data.commander" else original(package))
        console.activate(game)
        console.server._http.assets["/advisor-test.js"] = (
            "text/javascript; charset=utf-8",
            PROBE.replace("__CODE__", json.dumps(console.pairing_code)).encode("utf-8"))
        console.bridge.allowed = True
        process = subprocess.Popen([
            chromium, "--headless", "--no-sandbox", "--disable-gpu",
            "--disable-background-networking", "--no-first-run",
            "--no-default-browser-check", "--disable-dev-shm-usage",
            f"--user-data-dir={tmp_path / 'browser'}", "--virtual-time-budget=150000",
            "--window-size=1600,1000", "--dump-dom",
            f"http://{console.address[0]}:{console.address[1]}/",
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        started = time.monotonic()
        try:
            while process.poll() is None and time.monotonic() - started < 140:
                console.pump(game)
                game.update(.02)
                game.llm_tick()
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
    assert root.get("data-advisor-test") == "passed", root.get("data-failure", stderr[-2000:])
    assert round(game.ship.target_course) == 120
    assert "frigate" in game.llm_advisor_sides
