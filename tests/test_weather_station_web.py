"""Weather & sonar analysis dialog in the Remote Crew browser (key 0)."""

import json
from pathlib import Path
import shutil
import subprocess
import time

import pytest
from commander_web import copy_assets, index_html, inject_probe

from src.commander import server
from src.core.game import Game
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
  const press = (key) => document.body.dispatchEvent(new KeyboardEvent("keydown", {key, bubbles: true}));
  async function run() {
    await until(() => !$('shell').hidden, 'translations');
    $('name').value = 'Weather'; $('code').value = __CODE__;
    $('pair-form').requestSubmit();
    await until(() => $('station-tab-bridge'), 'station tabs');
    $('station-tab-bridge').click();
    await until(() => document.body.dataset.remoteRole === 'assigned', 'assigned');
    // Station keys only act while the workstation is shown.
    await until(() => !$('operations').hidden && !$('station-bridge').hidden, 'bridge shown');
    press('0');
    const dialog = $('weather-dialog');
    await until(() => dialog.open && $('weather-environment').children.length >= 8, 'dialog open');
    await until(() => $('weather-flight-status').textContent.length > 0, 'flight status');
    // No bathythermograph yet: no layer, no profile.
    if (!$('weather-profile-text').textContent.includes(__NONE__)) throw new Error('profile before BT');
    // Real flow: close, go to Sonar, take the bathythermograph, reopen.
    press('0');
    await until(() => !dialog.open, 'closed before BT');
    $('station-tab-sonar').click();
    await until(() => !$('station-sonar').hidden && !$('sonar-bt').disabled, 'sonar BT ready');
    press('0');
    await until(() => dialog.open, 'reopened on sonar');
    // The BT action can be refused while the station lease settles: retry
    // the operator action until the measured profile is published.
    for (let attempt = 0; attempt < 20 && $('weather-profile-text').textContent.includes(__NONE__); attempt++) {
      $('sonar-bt').click();
      await sleep(2000);
    }
    await until(() => !$('weather-profile-text').textContent.includes(__NONE__), 'profile after BT', 3000);
    const canvas = $('weather-profile');
    await until(() => canvas.width > 100 && canvas.height > 100, 'canvas size');
    const pixels = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
    let bright = 0;
    for (let index = 0; index < pixels.length; index += 4) if (pixels[index + 1] > 120) bright++;
    if (bright < 200) throw new Error(`profile not drawn: ${bright}`);
    const shell = dialog.querySelector('.weather-shell');
    if (shell.scrollWidth > shell.clientWidth + 1) throw new Error('horizontal overflow');
    press('0');
    await until(() => !dialog.open && dialog.hidden, 'dialog closed by 0');
  }
  run().then(() => document.documentElement.dataset.weatherTest = 'passed', (error) => {
    document.documentElement.dataset.weatherTest = 'failed';
    document.documentElement.dataset.failure = String(error.stack || error);
  });
})();
'''


@pytest.mark.parametrize("width,height", [(1600, 1000), (420, 900)])
def test_weather_dialog_opens_with_0_and_shows_profile_only_after_bt(
        tmp_path, monkeypatch, width, height):
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
    html = inject_probe(index_html(), "weather-test.js")
    copy_assets(tmp_path, html)
    monkeypatch.setattr(server.resources, "files", lambda _package: tmp_path)
    console.activate(game)
    none_text = en[PREFIX + "weather_profile_none"]
    console.server._http.assets["/weather-test.js"] = (
        "text/javascript; charset=utf-8",
        PROBE.replace("__CODE__", json.dumps(console.pairing_code))
        .replace("__NONE__", json.dumps(none_text)).encode("utf-8"))
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
    assert root.get("data-weather-test") == "passed", root.get("data-failure", stderr[-2000:])
