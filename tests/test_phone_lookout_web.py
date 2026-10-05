"""Browser contract of the phone lookout page (/lookout, Chromium)."""

import json
import math
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from commander_web import ASSET_DIR, RealTimeHost, copy_assets

from src.commander import server
from src.core.game import Game
from test_commander_assets import PREFIX, catalogs

pytestmark = pytest.mark.browser  # drives headless Chromium (CI browser job)

sys.path.insert(0, str(Path(__file__).parent))

ENTRY = '<script type="module" src="./js/phone/main.js"></script>'

PROBE = r'''
(() => {
  const $ = (id) => document.getElementById(id);
  const root = document.documentElement;
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  async function until(check, message, limit = 3000) {
    for (let index = 0; index < limit; index++) {
      root.dataset.status = $('phone-status')?.textContent || '';
      root.dataset.bearing = $('phone-bearing')?.textContent || '';
      root.dataset.blocked = $('phone-blocked')?.hidden ? '' : $('phone-blocked-text')?.textContent || '';
      if (check()) return;
      await sleep(20);
    }
    throw new Error(typeof message === 'function' ? message() : message);
  }
  window.addEventListener('error', (event) => { root.dataset.jsError = String(event.message).slice(0, 300); });
  window.addEventListener('unhandledrejection', (event) => { root.dataset.jsError = String(event.reason?.stack || event.reason).slice(0, 600); });
  const tap = (x) => {
    const canvas = $('phone-view'), box = canvas.getBoundingClientRect();
    const at = {pointerId: 7, clientX: box.left + x * box.width, clientY: box.top + box.height / 2, bubbles: true};
    canvas.dispatchEvent(new PointerEvent('pointerdown', at));
    canvas.dispatchEvent(new PointerEvent('pointerup', at));
  };
  const pick = (label) => [...$('phone-categories').querySelectorAll('button')].find((button) => button.textContent === label);
  async function run() {
    await until(() => !$('phone-pair').hidden && $('phone-title') !== null || document.title === 'U-Jagd lookout', 'translations');
    $('phone-name').value = 'Phone';
    // Typed as F9 shows it: with the space, in lower case, O for 0 and l for 1.
    $('phone-code').value = __CODE__;
    $('phone-code').dispatchEvent(new Event('input'));
    $('phone-pair-form').requestSubmit();
    await until(() => !$('phone-watch').hidden && $('phone-blocked').hidden, () => `no eyepiece: ${root.dataset.blocked}`);
    await until(() => /^\d\d\d°$/.test($('phone-bearing').textContent), 'no bearing');
    // A swipe turns the view; "Ahead" brings it back to the bow.
    const canvas = $('phone-view'), box = canvas.getBoundingClientRect(), before = $('phone-bearing').textContent;
    canvas.dispatchEvent(new PointerEvent('pointerdown', {pointerId: 3, clientX: box.left + box.width * .8, clientY: box.top + 50, bubbles: true}));
    canvas.dispatchEvent(new PointerEvent('pointermove', {pointerId: 3, clientX: box.left + box.width * .2, clientY: box.top + 50, bubbles: true}));
    canvas.dispatchEvent(new PointerEvent('pointerup', {pointerId: 3, clientX: box.left + box.width * .2, clientY: box.top + 50, bubbles: true}));
    await until(() => $('phone-bearing').textContent !== before, 'swipe did not turn');
    $('phone-center').click();
    await until(() => $('phone-bearing').textContent === before, 'not back ahead');
    // Tap the ship ahead once the lookout's eye has it, and call it.
    const outlines = async () => (await (await fetch('/api/v2/state', {credentials: 'same-origin'})).json()).lookout.outlines.length;
    for (let index = 0; index < 200 && !(await outlines()); index++) await sleep(250);
    tap(.5);
    await until(() => !$('phone-categories').hidden, 'no category chooser');
    pick('Ship').click();
    await until(() => $('phone-status').textContent.startsWith('Confirmed'), () => `not confirmed: ${$('phone-status').textContent}`);
    await until(() => $('phone-calls').children.length === 1, 'no call in the list');
    // A torpedo astern is not there.
    for (let turn = 0; turn < 12; turn++) $('phone-zoom').click();
    tap(.02);
    await until(() => !$('phone-categories').hidden, 'no chooser at the edge');
    pick('Torpedo').click();
    await until(() => $('phone-status').textContent.startsWith('Not confirmed'), () => `confirmed a phantom: ${$('phone-status').textContent}`);
  }
  run().then(() => { root.dataset.phoneTest = 'passed'; }, (error) => {
    root.dataset.phoneTest = 'failed';
    root.dataset.failure = String(error.stack || error);
  });
})();
'''



def sloppy_code(code):
    """The pairing code the way people type what F9 shows ("021 GSX")."""
    return code[:3].replace("0", "O").replace("1", "l") + " " + code[3:].lower()

def test_phone_lookout_pairs_turns_and_calls(tmp_path, monkeypatch):
    chromium = (shutil.which("chromium") or shutil.which("chromium-browser")
                or shutil.which("google-chrome"))
    if not chromium:
        pytest.skip("Optional phone lookout browser contract: no Chromium")
    en, de = catalogs()
    game = Game(seed=917, start_menu=False, audio_enabled=False, language="en")
    game.world.hour = 12.0
    merchant = game.civilians[0]
    for other in game.civilians[1:] + game.warships:
        other.x, other.y = game.ship.x + 60.0, game.ship.y + 60.0
    ahead = math.radians(game.ship.course)
    merchant.x = game.ship.x + 2.0 * math.sin(ahead)
    merchant.y = game.ship.y - 2.0 * math.cos(ahead)
    merchant.course = (game.ship.course - 90.0) % 360.0
    merchant.speed = 0.0
    game.world.land_blocks_line = lambda *args: False
    console = game.commander
    console.port = 0
    console._translations = {
        "en": {key: value for key, value in en.items() if key.startswith(PREFIX)},
        "de": {key: value for key, value in de.items() if key.startswith(PREFIX)},
    }
    console._contact_analysis_assets = {}
    console._manual_pages = {}
    copy_assets(tmp_path)
    page = (ASSET_DIR / "lookout.html").read_text(encoding="utf-8")
    assert ENTRY in page
    (tmp_path / "lookout.html").write_text(
        page.replace(ENTRY, '<script src="./phone-test.js" defer></script>' + ENTRY), "utf-8")
    monkeypatch.setattr(server.resources, "files", lambda _package: tmp_path)
    console.activate(game)
    console.server._http.assets["/phone-test.js"] = (
        "text/javascript; charset=utf-8",
        PROBE.replace("__CODE__", json.dumps(sloppy_code(console.pairing_code))).encode("utf-8"))
    # Real time (as the submarine sonar test): virtual time would run the
    # page far ahead of the host, which applies the calls.
    profile = tmp_path / "browser"
    log = (tmp_path / "chromium.log").open("wb")
    process = subprocess.Popen([
        chromium, "--headless", "--no-sandbox", "--disable-gpu",
        "--disable-background-networking", "--no-first-run",
        "--no-default-browser-check", "--disable-dev-shm-usage",
        f"--user-data-dir={profile}", "--window-size=420,860",
        "--remote-debugging-port=0",
        f"http://{console.address[0]}:{console.address[1]}/lookout",
    ], stdout=subprocess.DEVNULL, stderr=log)
    started = time.monotonic()
    root = {}
    host = RealTimeHost(game, profile)
    try:
        while process.poll() is None and time.monotonic() - started < 120:
            root = host.dataset or root
            if root.get("phoneTest"):
                break
            console.pump(game)
            host.step()
            time.sleep(.02)
    finally:
        host.close()
        process.kill()
        process.wait(timeout=5)
        log.close()
        console.stop()
        game.audio.shutdown()
    assert root.get("phoneTest") == "passed", (
        root.get("status"), root.get("bearing"), root.get("blocked"), root.get("jsError"),
        root.get("failure", (tmp_path / "chromium.log").read_text(errors="replace")[-2000:]),
        list(game.lookout_calls))
    calls = list(game.lookout_calls)
    assert [(row["category"], row["confirmed"]) for row in calls] == [
        ("ship", True), ("torpedo", False)]


def test_phone_page_is_self_contained_and_translated():
    import re

    from commander_web import ASSET_DIR as ASSETS_DIR
    from test_commander_assets import Document
    html = (ASSETS_DIR / "lookout.html").read_text(encoding="utf-8")
    document = Document(html)
    ids = [attrs["id"] for _, attrs in document.elements if "id" in attrs]
    assert len(ids) == len(set(ids))
    scripts = "\n".join(path.read_text(encoding="utf-8")
                        for path in sorted((ASSETS_DIR / "js" / "phone").glob("*.js")))
    assert set(re.findall(r'\$\("([\w-]+)"\)', scripts)) <= set(ids)
    assert "Content-Security-Policy" in html and "<script>" not in html and "style=" not in html
    code = next(attrs for _, attrs in document.elements if attrs.get("id") == "phone-code")
    assert code["maxlength"] == "12" and code["autocomplete"] == "off"
    en, de = catalogs()
    keys = {attrs.get("data-i18n") or attrs.get("data-i18n-aria")
            for _, attrs in document.elements
            if "data-i18n" in attrs or "data-i18n-aria" in attrs}
    keys |= set(re.findall(r'\bt\("([a-z0-9_]+)"', scripts))
    keys |= {f"phone_category_{category}" for category in (
        "contact", "ship", "warship", "merchant", "aircraft", "submarine", "torpedo")}
    for key in keys:
        assert PREFIX + key in en and PREFIX + key in de, key
    # The phone page never reads a pairing code or a credential from its URL.
    assert "location.search" not in scripts and "location.hash" not in scripts
    assert "localStorage" not in scripts and "document.cookie" not in scripts


PARSER_PROBE = r"""
import { parseReport } from "./js/phone/speech.js";
import { lineOfSight } from "./js/phone/orientation.js";
const context = {course: 10, viewBearing: 123};
const heard = [
  "Schiff Peilung 040, Entfernung 5 Meilen",
  "Flugzeug Steuerbord 30",
  "U-Boot Peilung null vier null 3 Seemeilen",
  "aircraft bearing 0 4 0 range 8 miles",
  "Kriegsschiff Backbord 45 Entfernung 12,5 Seemeilen",
  "Kontakt voraus 5 Kabel",
  "hallo welt",
  "Torpedo",
  "merchant ship bearing 270 range 70 miles",
].map((text) => parseReport(text, context));
const round = (sight) => sight && [Math.round(sight.heading), Math.round(sight.elevation)];
const sights = [lineOfSight(0, 90, 0), lineOfSight(90, 90, 0), lineOfSight(0, 100, 0), lineOfSight(0, 0, 0)].map(round);
document.documentElement.dataset.result = JSON.stringify({heard, sights});
"""


def test_spoken_reports_and_phone_heading(tmp_path):
    from commander_web import run_module_probe
    root = run_module_probe(tmp_path, PARSER_PROBE)
    assert "data-result" in root, root.get("data-failure")
    result = json.loads(root["data-result"])
    rows = [None if row is None else (row["category"], row["bearing"], row["range_nm"])
            for row in result["heard"]]
    assert rows == [
        ("ship", 40, 5), ("aircraft", 40, None), ("submarine", 40, 3),
        ("aircraft", 40, 8), ("warship", 325, 12.5), ("contact", 10, 0.5),
        None, ("torpedo", 123, None), ("merchant", 270, None)]
    # Upright facing north, turned left to west, tilted up 10°, flat on its back.
    assert result["sights"] == [[0, 0], [270, 0], [0, 10], None]


LISTENER_PROBE = r"""
import { createListener, iosWithoutSafari, speechErrorKey } from "./js/phone/speech.js";
// A scripted stand-in for the browser's speech service: each run replays events.
let script = [];
class FakeRecognition {
  start() {
    queueMicrotask(() => {
      for (const [kind, value] of script) {
        if (kind === "result") this.onresult({results: [Object.assign(
          value.texts.map((transcript) => ({transcript})), {isFinal: value.final})]});
        if (kind === "error") this.onerror({error: value});
      }
      this.onend();
    });
  }
  stop() {}
}
window.SpeechRecognition = window.webkitSpeechRecognition = FakeRecognition;
const run = (events) => new Promise((resolve) => {
  script = events;
  const log = [];
  createListener({language: "de", onHeard: (texts) => log.push(["heard", texts]),
    onError: (code) => log.push(["error", code]), onEnd: () => resolve(log)});
});
const runs = [
  await run([["result", {texts: ["Schiff Peilung 040"], final: true}]]),
  // Safari may end without a final result: the last interim one is what was said.
  await run([["result", {texts: ["Schiff"], final: false}], ["result", {texts: ["Schiff Peilung 090"], final: false}]]),
  await run([]),
  await run([["error", "service-not-allowed"]]),
];
const keys = ["aborted", "not-allowed", "service-not-allowed", "no-speech", "audio-capture",
  "network", "language-not-supported"].map(speechErrorKey);
const agents = [
  "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/129.0.6668.46 Mobile/15E148 Safari/604.1",
  "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
  "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Mobile Safari/537.36",
].map((agent) => iosWithoutSafari(agent));
document.documentElement.dataset.result = JSON.stringify({runs, keys, agents});
"""


def test_speech_failures_say_what_went_wrong(tmp_path):
    """Each Web Speech error has its own advice; the rest name their code."""
    from commander_web import run_module_probe
    root = run_module_probe(tmp_path, LISTENER_PROBE)
    assert "data-result" in root, root.get("data-failure")
    result = json.loads(root["data-result"])
    assert result["runs"] == [
        [["heard", ["Schiff Peilung 040"]]],
        [["heard", ["Schiff Peilung 090"]]],
        [["error", "no-speech"]],
        [["error", "service-not-allowed"]],
    ]
    assert result["keys"] == [
        None, "phone_mic_denied", "phone_speech_service", "phone_speech_silent",
        "phone_mic_busy", "phone_speech_network", "phone_speech_failed"]
    en, de = catalogs()
    for key in filter(None, result["keys"]):
        assert PREFIX + key in en and PREFIX + key in de, key
    assert "{error}" in en[PREFIX + "phone_speech_failed"]
    assert "{error}" in de[PREFIX + "phone_speech_failed"]
    assert "Siri" in de[PREFIX + "phone_speech_service"]
    # Chrome on the iPhone gets the Safari hint; Safari and Android Chrome do not.
    assert result["agents"] == [True, False, False]


def test_iphone_browsers_other_than_safari_are_pointed_to_safari():
    source = (ASSET_DIR / "js" / "phone" / "speech.js").read_text(encoding="utf-8")
    assert r"CriOS|FxiOS|EdgiOS" in source
    main = (ASSET_DIR / "js" / "phone" / "main.js").read_text(encoding="utf-8")
    assert main.count('t("phone_speech_use_safari")') == 2
