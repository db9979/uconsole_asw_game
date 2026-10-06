"""The holder decides a station request in a real browser: a second crew
session asks for the station this browser holds, the prompt appears at the
holder and "Hand over" passes the station on (Chromium)."""

from contextlib import closing
import http.client
import json
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
  const $ = (id) => document.getElementById(id);
  const root = document.documentElement;
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  async function until(check, message, limit = 3000) {
    for (let index = 0; index < limit; index++) {
      if (check()) return;
      await sleep(20);
    }
    throw new Error(message);
  }
  async function run() {
    await until(() => !$('shell').hidden, 'translations');
    root.dataset.bandBefore = String($('handover-band').hidden);
    $('name').value = 'Holder'; $('code').value = __CODE__;
    $('pair-form').requestSubmit();
    await until(() => !$('lobby').hidden && document.querySelector("#station-cards [data-station='weapons'] button"), 'lobby');
    document.querySelector("#station-cards [data-station='weapons'] button").click();
    await until(() => document.body.dataset.remoteRole === 'assigned', 'weapons not taken');
    root.dataset.stage = 'holding';
    await until(() => !$('handover-band').hidden, 'no handover prompt', 6000);
    const item = $('handover-list').querySelector('li');
    root.dataset.prompt = item.querySelector('p').textContent;
    const buttons = [...item.querySelectorAll('button')];
    root.dataset.buttons = buttons.map((button) => `${button.type}:${button.textContent}`).join('|');
    const band = $('handover-band').getBoundingClientRect();
    root.dataset.bandInView = String(band.width > 0 && band.height > 0 && band.left >= 0 &&
      band.bottom <= innerHeight && band.right <= innerWidth);
    const accept = buttons.find((button) => button.dataset.accept === 'true');
    accept.focus();
    root.dataset.focusable = String(document.activeElement === accept);
    // Click the live button once it is enabled; a re-render or a station
    // request still in flight on a slow runner may have replaced or
    // disabled the one read above.
    const handedOver = () => $('handover-band').hidden && document.body.dataset.remoteRole === 'lobby';
    for (let attempt = 0; attempt < 30 && !handedOver(); attempt++) {
      const live = [...$('handover-list').querySelectorAll('button')]
        .find((button) => button.dataset.accept === 'true');
      if (live && !live.disabled) live.click();
      for (let index = 0; index < 100 && !handedOver(); index++) await sleep(20);
    }
    await until(handedOver, 'station not handed over');
    root.dataset.occupancy = document.querySelector("#station-cards [data-station='weapons']").className;
  }
  run().then(() => { root.dataset.handoverTest = 'passed'; }, (error) => {
    root.dataset.handoverTest = 'failed';
    root.dataset.failure = String(error.stack || error);
  });
})();
'''


def _post(address, path, body, cookie=None, csrf=None):
    host, port = address
    headers = {"Origin": f"http://{host}:{port}", "Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    if csrf:
        headers["X-U-Jagd-CSRF"] = csrf
    with closing(http.client.HTTPConnection(host, port, timeout=3)) as connection:
        connection.request("POST", path, body=json.dumps(body).encode("utf-8"),
                           headers=headers)
        response = connection.getresponse()
        payload = json.loads(response.read())
        return response.status, response.getheader("Set-Cookie"), payload


def test_holder_sees_request_and_hands_station_over(tmp_path, monkeypatch):
    chromium = (shutil.which("chromium") or shutil.which("chromium-browser")
                or shutil.which("google-chrome"))
    if not chromium:
        pytest.skip("Optional handover browser contract: no Chromium")
    en, de = catalogs()
    game = Game(seed=921, start_menu=False, audio_enabled=False, language="en")
    console = game.commander
    console.port = 0
    console._translations = {
        "en": {key: value for key, value in en.items() if key.startswith(PREFIX)},
        "de": {key: value for key, value in de.items() if key.startswith(PREFIX)},
    }
    console._contact_analysis_assets = {}
    console._manual_pages = {}
    copy_assets(tmp_path, inject_probe(index_html(), "handover-test.js"))
    monkeypatch.setattr(server.resources, "files", lambda _package: tmp_path)
    console.activate(game)
    console.server._http.assets["/handover-test.js"] = (
        "text/javascript; charset=utf-8",
        PROBE.replace("__CODE__", json.dumps(console.pairing_code)).encode("utf-8"))
    console.bridge.allowed = True
    profile = tmp_path / "browser"
    process = subprocess.Popen([
        chromium, "--headless", "--no-sandbox", "--disable-gpu",
        "--disable-background-networking", "--no-first-run",
        "--no-default-browser-check", "--disable-dev-shm-usage",
        f"--user-data-dir={profile}", "--window-size=1600,900",
        "--force-device-scale-factor=1", "--remote-debugging-port=0",
        f"http://{console.address[0]}:{console.address[1]}/",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    host = RealTimeHost(game, profile, period_s=.25)
    asker = None
    root = {}
    # A slow runner may reach the holding stage late; give the request its
    # own time after it is sent instead of one budget from launch.
    deadline = time.monotonic() + 90
    try:
        while process.poll() is None and time.monotonic() < deadline:
            root = host.dataset or root
            if root.get("handoverTest"):
                break
            if asker is None and root.get("stage") == "holding":
                status, cookie, paired = _post(console.address, "/api/v2/pair",
                                               {"code": console.pairing_code, "name": "Asker"})
                assert status == 200
                cookie = cookie.split(";", 1)[0]
                status, _, asked = _post(console.address, "/api/v2/stations/request",
                                         {"station": "weapons"}, cookie, paired["csrf"])
                assert status == 200 and asked["requested_station"] == "weapons"
                asker = paired["client_id"]
                deadline = max(deadline, time.monotonic() + 60)
            console.pump(game)
            host.step()
            time.sleep(.02)
        statuses = {status["name"]: status for status in console.server.client_statuses()}
    finally:
        host.close()
        process.kill()
        process.wait(timeout=5)
        console.stop()
        game.audio.shutdown()
    assert root.get("handoverTest") == "passed", (root.get("stage"), root.get("failure"))
    assert root["bandBefore"] == "true"
    assert root["prompt"] == "Asker asks for Weapons"
    assert root["buttons"] == "button:Hand over|button:Keep station"
    assert root["bandInView"] == "true" and root["focusable"] == "true"
    assert "station-occupied" in root["occupancy"]
    assert statuses["Asker"]["stations"]["weapons"]["leased"]
    assert statuses["Asker"]["stations"]["weapons"]["grants"] == {
        "command": True, "direct_fire": True, "sonar_audio": False}
    assert not statuses["Holder"]["stations"]["weapons"]["leased"]
