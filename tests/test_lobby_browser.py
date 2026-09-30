"""The multiplayer lobby in a real browser: meet, take a station, tick ready,
and the host's countdown opens every console at once."""

import json
import shutil
import subprocess
import time

import pytest
from commander_web import RealTimeHost, copy_assets, index_html, inject_probe

from src.commander import server as commander_transport
from src.core import config, manual
from src.core.game import Game
from src.core.lobby import COUNTDOWN_S
from test_commander_assets import PREFIX, catalogs

LOBBY_SCRIPT = r"""
(() => {
"use strict";
const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function until(check, message, limit = 3000) {
  for (let index = 0; index < limit; index++) {
    if (check()) return;
    await sleep(20);
  }
  throw new Error(message);
}
async function run() {
  await until(() => !$("shell").hidden, "translations missing");
  const root = document.documentElement;
  $("name").value = "Sonar Sam";
  $("code").value = __CODE__;
  $("code").dispatchEvent(new Event("input"));
  $("pair-form").requestSubmit();
  await until(() => !$("lobby").hidden && !$("lobby-room").hidden, "lobby room not shown");
  root.dataset.mission = $("lobby-room-mission").textContent;
  root.dataset.host = $("lobby-room-host").textContent;
  root.dataset.readyBefore = String($("lobby-ready").disabled);
  document.querySelector("#station-cards [data-station='sonar'] button").click();
  // Holding a station, the crew stays in the room while the lobby is open.
  await until(() => document.body.dataset.remoteRole === "assigned" && !$("lobby-ready").disabled,
    "station not taken");
  root.dataset.roomWithStation = String(!$("lobby").hidden && $("operations").hidden);
  $("lobby-ready").click();
  await until(() => $("lobby-ready").getAttribute("aria-pressed") === "true", "ready not accepted");
  root.dataset.players = $("lobby-room-players").textContent;
  await until(() => /\d/.test($("lobby-room-status").textContent) && $("lobby-room-status").textContent.includes("starts"), "no countdown");
  await until(() => $("lobby").hidden && !$("operations").hidden, "console did not open at the start");
  root.dataset.lobbyTest = "passed";
}

addEventListener("load", () => {
  run().catch((error) => { document.documentElement.dataset.failure = String(error?.stack || error); });
});
})();
"""


def test_crew_meets_readies_and_starts_together(tmp_path, monkeypatch):
    chromium = (shutil.which("chromium") or shutil.which("chromium-browser")
                or shutil.which("google-chrome"))
    if not chromium:
        pytest.skip("Optional lobby browser contract: no installed Chromium")
    monkeypatch.setattr(config, "SAVE_DIR", str(tmp_path / "saves"))
    en, de = catalogs()
    game = Game(seed=917, start_menu=True, audio_enabled=False, language="en")
    console = game.commander
    console.port = 0
    console._translations = {
        "en": {key: value for key, value in en.items() if key.startswith(PREFIX)},
        "de": {key: value for key, value in de.items() if key.startswith(PREFIX)},
    }
    console._contact_analysis_assets = {}
    console._manual_pages = {lang: manual.html_page(lang) for lang in manual.LANGUAGES}
    copy_assets(tmp_path, inject_probe(index_html(), "lobby-test.js"))
    monkeypatch.setattr(commander_transport.resources, "files", lambda _package: tmp_path)
    console.prepare()
    console.hosts = ("127.0.0.1",)
    game.open_lobby()
    assert game.lobby_active and console.address is not None
    console.server._http.assets["/lobby-test.js"] = (
        "text/javascript; charset=utf-8",
        LOBBY_SCRIPT.replace("__CODE__", json.dumps(console.pairing_code)).encode("utf-8"))
    profile = tmp_path / "lobby-browser"
    process = subprocess.Popen(
        [chromium, "--headless", "--no-sandbox", "--disable-gpu",
         "--disable-background-networking", "--no-first-run",
         "--no-default-browser-check", "--disable-dev-shm-usage",
         f"--user-data-dir={profile}", "--window-size=1600,900",
         "--remote-debugging-port=0",
         f"http://{console.address[0]}:{console.address[1]}/"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # The countdown runs on wall time, so the host loop does too.
    host = RealTimeHost(game, profile, period_s=.25)
    started = last = time.monotonic()
    root = {}
    try:
        while time.monotonic() - started < 90:
            root = host.dataset
            if root.get("lobbyTest") == "passed" or "failure" in root:
                break
            console.pump(game)
            players = game.lobby_players()
            if (game.lobby_active and game.lobby.countdown_s is None and players
                    and players[0]["ready"]):
                assert game.lobby.request_start(players) == "started"
            now = time.monotonic()
            game.lobby_tick(now - last)
            last = now
            host.step()
            time.sleep(.02)
    finally:
        host.close()
        process.kill()
        process.wait(timeout=5)
        console.stop()
        game.audio.shutdown()
    assert root.get("lobbyTest") == "passed", root.get("failure", root)
    assert root["mission"] == "Mission: Patrol"
    assert root["host"] == "The uConsole plays the frigate at the Bridge."
    assert root["readyBefore"] == "true"
    assert root["roomWithStation"] == "true"
    assert "Sonar Sam (you)" in root["players"] and "ready" in root["players"]
    assert not game.in_menu and game.lobby_round
