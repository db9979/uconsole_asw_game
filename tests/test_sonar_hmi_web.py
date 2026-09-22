import json
from pathlib import Path
import shutil
import subprocess
import time

import pytest

from src.commander import bridge, server
from src.core.game import Game
from test_commander_assets import ASSETS, Document, PREFIX, catalogs


ROOT = Path(__file__).resolve().parents[1]


def test_sonar_hmi_assets_expose_bounded_operator_controls():
    html = (ROOT / "data/commander/index.html").read_text()
    js = (ROOT / "data/commander/app.js").read_text()
    css = (ROOT / "data/commander/style.css").read_text()

    for element_id in (
        "sonar-black-level", "sonar-contrast", "sonar-history",
        "sonar-palette", "sonar-audio-highpass", "sonar-audio-lowpass",
        "sonar-cursor-readout", "sonar-detach", "sonar-a-scan",
    ):
        assert f'id="{element_id}"' in html
    assert "new Uint32Array(image.data.buffer)" in js
    assert "drawHarmonicGuides" in js
    assert "createBiquadFilter" in js
    assert "Math.exp(-echo.age_s / 12)" in js
    assert "function accumulateSonarHistory" in js
    assert "row.stamp < state.clock.sim - 605" in js
    assert 'sendStationAction("sonar_set_focus", {ref: nearest.row.ref})' in js
    assert 'value="0"' in html
    assert 'contrast: 2.5' in js
    assert "?scope=${encodeURIComponent(scope)}" in js
    assert '.station-section:not([hidden]) > :not(#role-visuals)' in css
    detached_hide = css.split(
        'body[data-sonar-scope][data-remote-role="assigned"] .masthead,', 1)[1]
    detached_hide = detached_hide.split('{ display: none !important; }', 1)[0]
    assert '.station-section,' not in detached_hide


def test_instructor_environment_is_solo_host_only_and_refreshes_weather():
    spec = server.V2_ACTION_REGISTRY["host_instructor_environment"]
    assert spec.stations == frozenset({server.HOST_ROLE})
    assert spec.validate_params({"sea_state": 0, "event": None})
    assert spec.validate_params({"sea_state": 6, "event": "targets_flank"})
    assert not spec.validate_params({"sea_state": 7, "event": None})
    assert not spec.validate_params({"sea_state": True, "event": None})

    class World:
        sea_state = 3
        refreshed = False

        def refresh_weather(self):
            self.refreshed = True

    game = type("Game", (), {"world": World(), "subs": []})()
    assert bridge._host_instructor_environment(
        game, {"sea_state": 5, "event": None}) is True
    assert game.world.sea_state == 5
    assert game.world.refreshed is True

    motion = type("Motion", (), {"maximum_speed_kn": 20.0})()
    sub = type("Sub", (), {"side": "hostile", "sunk": False,
                            "state": "PATROLLE", "id": 1,
                            "motion": motion, "speed": 2.0})()
    game.subs = [sub]
    assert bridge._host_instructor_environment(
        game, {"sea_state": 4, "event": "targets_flank"}) is True
    assert sub.speed == 20.0


def test_detached_broadband_scope_renders_live_energy_in_chromium(tmp_path, monkeypatch):
    chromium = (shutil.which("chromium") or shutil.which("chromium-browser")
                or shutil.which("google-chrome"))
    if not chromium:
        pytest.skip("Optional detached Sonar browser contract: no Chromium")
    probe = r'''
(() => {
  const $ = (id) => document.getElementById(id);
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  async function until(check, message, limit = 800) {
    for (let index = 0; index < limit; index++) {
      if (check()) return;
      await sleep(20);
    }
    throw new Error(message);
  }
  async function run() {
    await until(() => !$('shell').hidden, 'translations');
    $('name').value = 'Detached'; $('code').value = __CODE__;
    $('pair-form').requestSubmit();
    await until(() => $('station-tab-sonar'), 'station tabs');
    $('station-tab-sonar').click();
    await until(() => document.body.dataset.remoteRole === 'assigned' &&
      !$('role-visuals').hidden && !$('sonar-visual').hidden, 'sonar visual');
    const canvas = $('sonar-broadband');
    await until(() => canvas.width > 100 && canvas.height > 100, 'canvas size');
    await sleep(1200);
    const station = $('station-sonar');
    if (getComputedStyle(station).display === 'none' ||
        getComputedStyle($('role-visuals')).display === 'none') throw new Error('scope hidden');
    const bounds = canvas.getBoundingClientRect();
    if (bounds.width < 300 || bounds.height < 150) throw new Error('scope too small');
    const pixels = canvas.getContext('2d').getImageData(
      50, 10, Math.max(1, canvas.width - 75), Math.max(1, canvas.height - 55)).data;
    let visible = 0;
    for (let index = 0; index < pixels.length; index += 4)
      if (pixels[index] > 18 || pixels[index + 1] > 24 || pixels[index + 2] > 18) visible++;
    if (visible < 20) throw new Error(`no broadband energy: ${visible}`);
  }
  run().then(() => document.documentElement.dataset.scopeTest = 'passed', (error) => {
    document.documentElement.dataset.scopeTest = 'failed';
    document.documentElement.dataset.failure = String(error.stack || error);
  });
})();
'''
    en, de = catalogs()
    game = Game(seed=913, start_menu=False, audio_enabled=False, language="en")
    console = game.commander
    console.solo = True
    console.port = 0
    console._translations = {
        "en": {key: value for key, value in en.items() if key.startswith(PREFIX)},
        "de": {key: value for key, value in de.items() if key.startswith(PREFIX)},
    }
    console._contact_analysis_assets = {}
    html = ASSETS.joinpath("index.html").read_text().replace(
        '<script src="./app.js" defer>',
        '<script src="./scope-test.js" defer></script><script src="./app.js" defer>')
    for name, payload in (("index.html", html),
                          ("app.js", ASSETS.joinpath("app.js").read_text()),
                          ("style.css", ASSETS.joinpath("style.css").read_text()),
                          ("sonar-audio-worklet.js", ASSETS.joinpath("sonar-audio-worklet.js").read_text())):
        (tmp_path / name).write_text(payload, encoding="utf-8")
    monkeypatch.setattr(server.resources, "files", lambda _package: tmp_path)
    console.activate(game)
    console.server._http.assets["/scope-test.js"] = (
        "text/javascript; charset=utf-8",
        probe.replace("__CODE__", json.dumps(console.pairing_code)).encode("utf-8"))
    console.bridge.allowed = True
    process = subprocess.Popen([
        chromium, "--headless", "--no-sandbox", "--disable-gpu",
        "--disable-background-networking", "--no-first-run",
        "--no-default-browser-check", "--disable-dev-shm-usage",
        f"--user-data-dir={tmp_path / 'browser'}", "--virtual-time-budget=30000",
        "--window-size=1280,800", "--dump-dom",
        f"http://{console.address[0]}:{console.address[1]}/?scope=broadband",
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    started = time.monotonic()
    try:
        while process.poll() is None and time.monotonic() - started < 30:
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
    assert root.get("data-scope-test") == "passed", root.get("data-failure", stderr)
