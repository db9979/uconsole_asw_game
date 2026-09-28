"""LAN pairing in a real browser, and the hint for browsers that are not Chromium.

Pairs the packaged page in Chromium against the real Game and a crew-mode
CommanderServer (the F9 LAN listener). A Firefox user agent must see the
browser hint and still pair; a client whose modules fail to start must not
stay silently on its loading screen.
"""

import json
import re
import shutil
import subprocess
import time

import pytest
from commander_web import copy_assets, index_html, inject_probe

from src.commander import server as commander_transport
from src.commander.assets import static_assets
from src.core import config, manual
from src.core.game import Game
from test_commander_assets import ASSETS, PREFIX, Document, catalogs

FIREFOX = "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0"

PAIR_SCRIPT = r"""
(() => {
"use strict";
const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function until(check, message, limit = 1500) {
  for (let index = 0; index < limit; index++) {
    if (check()) return;
    await sleep(20);
  }
  throw new Error(message);
}
async function run() {
  await until(() => !$("shell").hidden, "translations missing");
  const root = document.documentElement;
  root.dataset.hintVisible = String(!$("browser-hint").hidden);
  root.dataset.hintText = $("browser-hint").textContent;
  $("name").value = "LAN";
  $("code").value = __CODE__;
  $("pair-form").requestSubmit();
  await until(() => $("pairing").hidden && !$("lobby").hidden, "pairing did not reach the lobby: " + $("pair-error").textContent);
  // A fresh session never held a station, so nothing was revoked.
  root.dataset.lobbyStatus = $("lobby-status").textContent;
  // A free station is leased at once and its console opens.
  document.querySelector("#station-cards [data-station='bridge'] button").click();
  await until(() => document.body.dataset.remoteRole === "assigned" && !$("operations").hidden,
    "bridge console did not open: " + $("lobby-status").textContent);
  root.dataset.pairTest = "passed";
}
addEventListener("load", () => {
  run().catch((error) => { document.documentElement.dataset.failure = String(error?.stack || error); });
});
})();
"""


def _chromium():
    chromium = (shutil.which("chromium") or shutil.which("chromium-browser")
                or shutil.which("google-chrome"))
    if not chromium:
        pytest.skip("Optional pairing browser contract: no installed Chromium")
    return chromium


def _pair(tmp_path, monkeypatch, *extra_args):
    chromium = _chromium()
    monkeypatch.setattr(config, "SAVE_DIR", str(tmp_path / "saves"))
    en, de = catalogs()
    game = Game(seed=917, start_menu=False, audio_enabled=False, language="en")
    console = game.commander
    console.solo = False
    console.port = 0
    console._translations = {
        "en": {key: value for key, value in en.items() if key.startswith(PREFIX)},
        "de": {key: value for key, value in de.items() if key.startswith(PREFIX)},
    }
    console._contact_analysis_assets = {}
    console._manual_pages = {lang: manual.html_page(lang) for lang in manual.LANGUAGES}
    copy_assets(tmp_path, inject_probe(index_html(), "pair-test.js"))
    monkeypatch.setattr(commander_transport.resources, "files", lambda _package: tmp_path)

    console.activate(game)
    assert console.address is not None and console.server.solo_mode is False
    console.server._http.assets["/pair-test.js"] = (
        "text/javascript; charset=utf-8",
        PAIR_SCRIPT.replace("__CODE__", json.dumps(console.pairing_code)).encode("utf-8"))
    process = subprocess.Popen(
        [chromium, "--headless", "--no-sandbox", "--disable-gpu",
         "--disable-background-networking", "--no-first-run",
         "--no-default-browser-check", "--disable-dev-shm-usage",
         f"--user-data-dir={tmp_path / 'pair-browser'}", "--virtual-time-budget=20000",
         "--window-size=1600,900", *extra_args, "--dump-dom",
         f"http://{console.address[0]}:{console.address[1]}/"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    started = time.monotonic()
    try:
        while process.poll() is None and time.monotonic() - started < 120:
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
    assert root.get("data-pair-test") == "passed", root.get(
        "data-failure", stdout[-4000:] + stderr[-2000:])
    return root, en


def test_lan_pairing_reaches_the_lobby_in_chromium_without_a_browser_hint(
        tmp_path, monkeypatch):
    root, _en = _pair(tmp_path, monkeypatch)
    assert root.get("data-browser") == "chromium"
    assert root.get("data-hint-visible") == "false"
    assert root.get("data-lobby-status") == _en[PREFIX + "lobby_waiting"]


def test_firefox_sees_the_browser_hint_and_can_still_pair(tmp_path, monkeypatch):
    root, en = _pair(tmp_path, monkeypatch, f"--user-agent={FIREFOX}")
    assert root.get("data-browser") == "other"
    assert root.get("data-hint-visible") == "true"
    assert root.get("data-hint-text") == en[PREFIX + "browser_hint"]


def test_a_client_that_cannot_start_explains_itself(tmp_path, monkeypatch):
    """Modules that fail to load leave the loading screen with a browser note."""
    chromium = _chromium()
    en, de = catalogs()
    translations = {
        "en": {key: value for key, value in en.items() if key.startswith(PREFIX)},
        "de": {key: value for key, value in de.items() if key.startswith(PREFIX)},
    }
    copy_assets(tmp_path)
    (tmp_path / "js" / "main.js").write_text(
        'throw new Error("module client unsupported");\n', encoding="utf-8")
    monkeypatch.setattr(commander_transport.resources, "files", lambda _package: tmp_path)
    server = commander_transport.CommanderServer(translations=translations,
                                                 contact_analysis_assets={})
    server.start("127.0.0.1", 0)
    try:
        host, port = server.address
        result = subprocess.run(
            [chromium, "--headless", "--no-sandbox", "--disable-gpu",
             "--disable-background-networking", "--no-first-run",
             "--no-default-browser-check", "--disable-dev-shm-usage",
             f"--user-data-dir={tmp_path / 'stall-browser'}", "--lang=de-DE",
             "--virtual-time-budget=20000", "--dump-dom", f"http://{host}:{port}/"],
            capture_output=True, text=True, timeout=90)
    finally:
        server.stop()
    root = next((attrs for tag, attrs in Document(result.stdout).elements if tag == "html"), {})
    assert root.get("data-startup") == "stalled", result.stdout[-3000:] + result.stderr[-1500:]
    note = re.search(r'<p id="bootstrap-hint"([^>]*)>(.*?)</p>', result.stdout, re.S)
    assert note is not None and "hidden" not in note.group(1)
    # navigator.language decides the catalog; headless Chromium may ignore --lang.
    assert note.group(2) in (en[PREFIX + "browser_stalled"], de[PREFIX + "browser_stalled"])


def test_browser_check_ships_with_every_listener_and_runs_before_the_client():
    page = index_html()
    check = '<script src="./js/browser-check.js" defer></script>'
    assert page.index(check) < page.index('<script type="module" src="./js/main.js">')
    for web_host in (False, True):
        routes = static_assets(web_host, ASSETS)
        assert check.encode() in routes["/"][1]
        assert "/js/browser-check.js" in routes
    source = ASSETS.joinpath("js", "browser-check.js").read_text(encoding="utf-8")
    # A classic script: module syntax would fail exactly where it is needed.
    assert not re.search(r"^\s*(import|export)\b", source, re.M)
    assert "innerHTML" not in source
    en, de = catalogs()
    for key in ("browser_hint", "browser_stalled"):
        assert PREFIX + key in en and PREFIX + key in de


def test_navigation_proposal_limit_matches_the_frigate_top_speed():
    limit = config.SHIP_SPEED_MAX_KN
    page = index_html()
    field = re.search(r'id="navigation-speed"[^>]*max="([0-9.]+)"', page)
    assert field is not None and float(field.group(1)) == limit
    for relative in (("js", "input", "wiring.js"), ("js", "state", "display-model.js")):
        source = ASSETS.joinpath(*relative).read_text(encoding="utf-8")
        assert re.search(rf"speed(?:_kn)? > {limit:g}\b", source), relative
        assert "> 25)" not in source, relative
