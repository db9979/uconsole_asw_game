"""Real-browser contract for the solo console: station tabs and host controls.

Drives the packaged page in Chromium against the real Game, CommanderBridge and
a solo CommanderServer. Saves go to a temporary directory only.
"""

import json
import shutil
import subprocess
import time

import pytest
from commander_web import copy_assets, index_html, inject_probe

from src.commander import server as commander_transport
from src.core import config
from src.core.game import Game
from src.sonar.sonar import Contact
from src.core import manual
from test_commander_assets import ASSETS, PREFIX, Document, catalogs


CONSOLE_SCRIPT = r"""
(() => {
"use strict";
const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
class Fail extends Error {}
const assert = (value, message) => { if (!value) throw new Fail(message); };
async function until(check, message, limit = 1500) {
  for (let index = 0; index < limit; index++) {
    if (check()) return;
    await sleep(20);
  }
  throw new Fail(message);
}
const boatScenarios = ["s5_durchbruch", "s6_aufklaerung", "s7_geleitzug", "s8_meerenge",
  "s9_kampfschwimmer", "s10_versorger", "s17_duell", "s18_heimkehr", "s19_abholung",
  "s20_lauschposten", "s22_jagdgruppe", "frei_uboot"];
const scenarioIsBoat = (key) => boatScenarios.includes(key);
const scriptErrors = [];
window.addEventListener("error", (event) => scriptErrors.push(event.message));
window.addEventListener("unhandledrejection", (event) => scriptErrors.push(String(event.reason)));
const active = () => document.querySelector(".station-tab[aria-selected='true']")?.dataset.station;
const showing = (role) => active() === role && !$(`station-${role}`).hidden && !$("operations").hidden;
const fits = (label) => assert(document.documentElement.scrollHeight <= innerHeight + 1,
  `page scrolls instead of fitting the viewport (${label})`);

async function run() {
  await until(() => !$("shell").hidden, "translations missing");
  $("name").value = "Solo";
  $("code").value = __CODE__;
  $("pair-form").requestSubmit();
  await until(() => $("station-tab-bridge") && showing("bridge"), "solo bridge console missing");

  // Solo: one client holds every station, so there is nothing to add or release.
  assert($("station-tabs").children.length === 9, "solo session must show nine station tabs");
  assert([...$("station-tabs").children].every((tab, index) =>
    tab.querySelector(".station-key").textContent === String(index + 1)), "tab hotkey numbers");
  assert($("workstation-add-station").hidden && $("workstation-release").hidden, "add/release shown in solo");
  assert(!$("host-bar").hidden && !$("role-rail").hidden === false, "host bar or role rail state");
  fits("bridge");

  // The operator's picture survives a station switch: returning to a station
  // already visited repaints from its cache without blanking the console, and the
  // map zoom and a half-typed sonar order are still there. (The very first visit
  // to a station has nothing cached and may take one round trip.)
  let blanked = 0;
  new MutationObserver(() => { if ($("operations").hidden) blanked++; })
    .observe($("operations"), {attributes: true, attributeFilter: ["hidden"]});
  const before = $("role-map-scale").textContent;
  $("role-map-zoom-in").click();
  $("role-map-zoom-in").click();
  await until(() => $("role-map-scale").textContent !== before, "map zoom did not change");
  const zoomed = $("role-map-scale").textContent;

  $("station-tab-sonar").click();
  await until(() => showing("sonar"), "sonar tab did not activate");
  await until(() => [...document.querySelectorAll("[data-sonar-plot]")].filter((panel) => !panel.hidden)
    .every((panel) => panel.querySelector("canvas").width > 1), "overview plots not sized");
  const shown = [...document.querySelectorAll("[data-sonar-plot]")].filter((panel) => !panel.hidden);
  assert(shown.length >= 4, `sonar overview shows ${shown.length} plots`);
  assert($("sonar-plots").dataset.layout.startsWith("overview"), "sonar defaults to the overview");
  $("sonar-bearing").value = "77";
  $("sonar-bearing").dispatchEvent(new Event("input", {bubbles: true}));
  fits("sonar");

  blanked = 0;
  $("station-tab-bridge").click();
  await until(() => showing("bridge"), "bridge tab did not activate");
  await until(() => $("role-map-scale").textContent === zoomed, "map zoom was lost on station switch");
  assert(blanked === 0, "the console was blanked during a station switch");
  fits("bridge again");

  // Hotkeys: a digit selects that station, [ and ] step through the held ones.
  blanked = 0;
  document.dispatchEvent(new KeyboardEvent("keydown", {key: "2", bubbles: true}));
  await until(() => showing("sonar"), "hotkey 2 did not select sonar");
  assert(blanked === 0, "the console was blanked returning to a visited station");
  assert($("sonar-bearing").value === "77", "sonar draft was lost on station switch");
  document.dispatchEvent(new KeyboardEvent("keydown", {key: "]", bubbles: true}));
  await until(() => showing("weapons"), "] did not step to weapons");
  blanked = 0;
  document.dispatchEvent(new KeyboardEvent("keydown", {key: "[", bubbles: true}));
  await until(() => showing("sonar"), "[ did not step back to sonar");
  $("sonar-bearing").dispatchEvent(new KeyboardEvent("keydown", {key: "4", bubbles: true}));
  await sleep(300);
  assert(active() === "sonar", "a digit typed into a field switched station");
  assert(blanked === 0, "the console was blanked by hotkey switching to a visited station");

  // Solo host controls.
  // Real time only: no pause and no time compression control.
  assert(!document.getElementById("host-pause"), "pause control remains visible");
  assert(!document.getElementById("host-time-scale"), "time compression control remains visible");

  await until(() => !$("host-save").disabled, "save locked");
  $("host-save").click();
  await until(() => $("host-slot-dialog").open, "save dialog did not open");
  await until(() => !document.querySelector('#host-slot-list button[data-slot="3"]').disabled &&
    !$("host-save").disabled, "save slot unavailable");
  document.querySelector('#host-slot-list button[data-slot="3"]').click();
  assert($("host-status").dataset.status === "pending", "save command was not submitted");
  await until(() => $("host-status").dataset.status === "applied" &&
    !$("host-save").disabled, "save result missing");

  await until(() => !$("host-new").disabled, "new game locked");
  $("host-new").click();
  await until(() => $("host-new-dialog").open, "new game dialog did not open");
  $("host-new-scenario").value = "s1_patrouille";
  $("host-new-scenario").dispatchEvent(new Event("change", {bubbles: true}));
  assert(document.querySelector("#host-new-difficulty input").disabled,
    "a scenario with a fixed difficulty must not offer difficulty controls");
  $("host-new-world").value = "procedural";
  $("host-new-seed").value = "4242";
  $("host-new-form").requestSubmit();
  // The world is replaced; the browser stays paired and returns to the console.
  await until(() => window.__replaced === true || $("host-status").textContent.length > 0, "no new-game result");
  await sleep(1500);
  await until(() => $("station-tab-bridge") && !$("operations").hidden, "console lost after a new game", 3000);
  assert($("station-tabs").children.length === 9, "stations missing after a new game");

  // A new game on the submarine side: the solo session moves to the boat.
  await until(() => !$("host-new").disabled, "new game locked again", 5000);
  $("host-new").click();
  await until(() => $("host-new-dialog").open, "new game dialog did not reopen");
  assert($("host-new-side").value === "frigate", "the side does not start at the frigate");
  assert([...$("host-new-scenario").options].every((option) => !scenarioIsBoat(option.value)),
    "the frigate side lists a submarine scenario");
  $("host-new-side").value = "uboot";
  $("host-new-side").dispatchEvent(new Event("change", {bubbles: true}));
  assert([...$("host-new-scenario").options].length > 0 &&
    [...$("host-new-scenario").options].every((option) => scenarioIsBoat(option.value)),
    "the submarine side lists a frigate scenario");
  $("host-new-seed").value = "4242";
  $("host-new-form").requestSubmit();
  await until(() => $("station-tab-uboot") && !$("station-tab-bridge"),
    "the submarine side was not taken", 3000);
  assert(scriptErrors.length === 0, `script errors: ${scriptErrors.join(" | ")}`);
}

run().then(() => { document.documentElement.dataset.consoleTest = "passed"; },
  (error) => {
    document.documentElement.dataset.consoleTest = "failed";
    document.documentElement.dataset.failure = String(error.stack || error);
  });
})();
"""


def test_solo_console_tabs_keep_state_and_host_controls_drive_the_game(
        tmp_path, monkeypatch):
    chromium = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
    if not chromium:
        pytest.skip("Optional solo console browser contract: no installed Chromium")
    saves = tmp_path / "saves"
    monkeypatch.setattr(config, "SAVE_DIR", str(saves))
    en, de = catalogs()
    game = Game(seed=913, start_menu=False, audio_enabled=False, language="en")
    game.sonar.contacts.clear()
    for target_id, bearing in ((99001, 28.0), (99002, 52.0)):
        contact = Contact(target_id - 99000, target_id, "passiv", "sub")
        contact.update_passive(bearing, .8, .8, "hidden", game.sim_t)
        game.sonar.contacts[target_id] = contact
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
    console._manual_pages = {lang: manual.html_page(lang) for lang in manual.LANGUAGES}
    html = inject_probe(index_html(), "console-test.js")
    copy_assets(tmp_path, html)
    monkeypatch.setattr(commander_transport.resources, "files", lambda _package: tmp_path)

    console.activate(game)
    assert console.address is not None and console.server.solo_mode is True
    script = CONSOLE_SCRIPT.replace("__CODE__", json.dumps(console.pairing_code))
    console.server._http.assets["/console-test.js"] = (
        "text/javascript; charset=utf-8", script.encode("utf-8"))
    console.bridge.allowed = True

    process = subprocess.Popen(
        [chromium, "--headless", "--no-sandbox", "--disable-gpu",
         "--disable-background-networking", "--no-first-run",
         "--no-default-browser-check", "--disable-dev-shm-usage",
         f"--user-data-dir={tmp_path / 'console-browser'}", "--virtual-time-budget=300000",
         "--window-size=1600,900", "--dump-dom",
         f"http://{console.address[0]}:{console.address[1]}/"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    started = time.monotonic()
    try:
        # Wall-clock budget: the page needs about 80 s on an idle four-core
        # host; under a parallel test run (pytest-xdist) Chromium gets less
        # CPU, so the pump keeps going for up to 300 s (the page's own
        # virtual-time budget) before giving up.
        while process.poll() is None and time.monotonic() - started < 300:
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
    assert root.get("data-console-test") == "passed", root.get(
        "data-failure", stdout[-4000:] + stderr[-2000:])
    assert (saves / "slot3.json").is_file()
    # The last new game ran on the submarine side, whose list starts at the breakthrough.
    assert (game.seed, game.scenario_key, game.world_mode) == (4242, "s5_durchbruch", "procedural")
