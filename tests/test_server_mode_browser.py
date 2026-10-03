"""Server mode in a real browser: the leading browser picks the mission,
starts it for everyone and brings the crew back to the lobby."""

import json
import shutil
import subprocess
import time

import pytest
from commander_web import RealTimeHost, copy_assets, index_html, inject_probe

from src.commander import server as commander_transport
from src.core import config, daily, manual
from src.core.game import Game
from test_commander_assets import PREFIX, catalogs

LEADER_SCRIPT = r"""
(() => {
"use strict";
const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function until(check, message, limit = 3000) {
  document.documentElement.dataset.step = message;
  for (let index = 0; index < limit; index++) {
    if (check()) return;
    await sleep(20);
  }
  throw new Error(`${message}: status=${$("host-status").textContent} lobby=${$("lobby").hidden} ` +
    `room=${$("lobby-room").hidden} form=${$("leader-form").hidden} ops=${$("operations").hidden} role=${document.body.dataset.remoteRole}`);
}
async function run() {
  await until(() => !$("shell").hidden, "translations missing");
  const root = document.documentElement;
  $("name").value = "Lead";
  $("code").value = __CODE__;
  $("code").dispatchEvent(new Event("input"));
  $("pair-form").requestSubmit();
  await until(() => !$("lobby-room").hidden && !$("leader-form").hidden, "leader form not shown");
  await until(() => [...$("leader-mission").options].some((option) => option.value === "daily"),
    "no daily mission choice");
  root.dataset.host = $("lobby-room-host").textContent;
  root.dataset.groups = [...$("leader-mission").querySelectorAll("optgroup")].map((group) => group.label).join("|");
  root.dataset.newGameHidden = String($("host-new").hidden);
  $("leader-mission").value = "daily";
  $("leader-mission").dispatchEvent(new Event("change"));
  await until(() => $("lobby-room-mission").textContent.includes("Daily mission"), "choice not taken");
  await until(() => $("leader-weather").disabled, "daily mission keeps its weather");
  root.dataset.mission = $("lobby-room-mission").textContent;
  // Not everyone is ready (the leader itself): the first start asks.
  await until(() => !$("leader-start").disabled, "start not ready");
  $("leader-start").click();
  await until(() => $("leader-start").textContent === "Start anyway", "no confirmation");
  await until(() => !$("leader-start").disabled, "start not ready again");
  $("leader-start").click();
  await until(() => $("lobby").hidden && !$("operations").hidden, "console did not open", 6000);
  await until(() => !$("host-end").hidden && !$("host-end").disabled, "no way back to the lobby");
  $("host-end").click();
  await until(() => !$("lobby").hidden && !$("leader-form").hidden, "lobby did not return", 1500);
  root.dataset.leaderTest = "passed";
}

addEventListener("load", () => {
  run().catch((error) => { document.documentElement.dataset.failure = String(error?.stack || error); });
});
})();
"""


def test_the_leader_runs_the_lobby_from_the_browser(tmp_path, monkeypatch):
    chromium = (shutil.which("chromium") or shutil.which("chromium-browser")
                or shutil.which("google-chrome"))
    if not chromium:
        pytest.skip("Optional server-mode browser contract: no installed Chromium")
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
    copy_assets(tmp_path, inject_probe(index_html(), "leader-test.js"))
    monkeypatch.setattr(commander_transport.resources, "files", lambda _package: tmp_path)
    console.prepare()
    console.hosts = ("127.0.0.1",)
    game.start_server_mode()
    assert game.lobby_active and console.address is not None
    console.server._http.assets["/leader-test.js"] = (
        "text/javascript; charset=utf-8",
        LEADER_SCRIPT.replace("__CODE__", json.dumps(console.pairing_code)).encode("utf-8"))
    profile = tmp_path / "leader-browser"
    process = subprocess.Popen(
        [chromium, "--headless", "--no-sandbox", "--disable-gpu",
         "--disable-background-networking", "--no-first-run",
         "--no-default-browser-check", "--disable-dev-shm-usage",
         f"--user-data-dir={profile}", "--window-size=1600,900",
         "--remote-debugging-port=0",
         f"http://{console.address[0]}:{console.address[1]}/"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    host = RealTimeHost(game, profile, period_s=.25)
    started = last = time.monotonic()
    root = {}
    rounds = []
    try:
        while time.monotonic() - started < 120:
            root = host.dataset
            if root.get("leaderTest") == "passed" or "failure" in root:
                break
            console.pump(game)
            now = time.monotonic()
            game.lobby_tick(now - last)
            last = now
            if not game.in_menu and not rounds:
                rounds.append((game.scenario_key, game.seed, game.host_only))
            host.step()
            time.sleep(.02)
    finally:
        host.close()
        process.kill()
        process.wait(timeout=5)
        console.stop()
        game.audio.shutdown()
    assert root.get("leaderTest") == "passed", root.get("failure", root)
    assert root["host"].startswith("Server mode: the uConsole only serves. Lead leads")
    assert "Daily mission" in root["groups"] and root["newGameHidden"] == "true"
    day = daily.today()
    assert rounds == [(daily.scenario_for(day, "frigate"), daily.seed_for(day, "frigate"), True)]
    assert game.lobby_active and game.server_mode
