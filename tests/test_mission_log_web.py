"""The web mission log in real Chromium shows the uConsole's F11 log.

Dominik found the browser's "Einsatzprotokoll" always empty: it only ever
carried a few browser alerts. Each side's stations now list that side's F11
log (the frigate's event feed, the submarine's boat log), newest first; a
long log scrolls inside its drawer, and a new line is added without
rebuilding the rows already shown.
"""

import json
import shutil
import subprocess
import time

import pytest
from commander_web import copy_assets, index_html, inject_probe, page_dataset

from src.commander import server
from src.core.game import Game
from src.core.i18n import localize
from test_commander_assets import PREFIX, catalogs

LONG = ("Lange Meldung mit vielen Wörtern, damit die Zeile im Protokoll umbrechen muss: "
        "Peilung 135°, Entfernung 12,5 NM, Klassifizierung unbestätigt, an die OPZ weitergegeben.")
CATEGORIES = ("funk", "sonar", "waffen", "schaden", "mission", "navigation", "opz")

PROBE = r'''
(() => {
  const $ = (id) => document.getElementById(id);
  const root = document.documentElement;
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  async function until(check, message) {
    for (let index = 0; index < 3000; index++) {
      if (check()) return;
      await sleep(20);
    }
    throw new Error(typeof message === 'function' ? message() : message);
  }
  const texts = () => [...$('event-list').querySelectorAll('.event-text')].map((item) => item.textContent);
  async function run() {
    await until(() => !$('shell').hidden, 'translations');
    $('name').value = 'Log'; $('code').value = __CODE__;
    $('pair-form').requestSubmit();
    await until(() => $('station-tab-__ROLE__'), 'station tab');
    $('station-tab-__ROLE__').click();
    await until(() => document.body.dataset.remoteRole === 'assigned', 'assigned');
    await until(() => texts().length >= __COUNT__, () => `log rows: ${texts().length}`);
    const list = $('event-list');
    // The station's layout defaults settle first; then the log is opened.
    await until(() => {
      if ($('cic-grid').dataset.log !== 'open') document.querySelector('[data-dock-toggle="log"]').click();
      return list.clientHeight > 0;
    }, 'log drawer open');
    const first = list.firstElementChild;
    root.dataset.meta = first.querySelector('.event-meta').textContent;
    root.dataset.scroll = JSON.stringify([list.scrollHeight, list.clientHeight,
      $('stage').getBoundingClientRect().height, document.documentElement.scrollWidth, innerWidth]);
    root.dataset.baseline = JSON.stringify(texts());
    await until(() => texts()[0] === 'Neue Zeile', 'new line on top');
    if (list.children[1] !== first) throw new Error('rows rebuilt for a new line');
    root.dataset.texts = JSON.stringify(texts());
  }
  run().then(() => { root.dataset.logTest = 'passed'; }, (error) => {
    root.dataset.logTest = 'failed';
    root.dataset.failure = String(error.stack || error);
  });
})();
'''


@pytest.mark.parametrize("side", ["frigate", "uboot"])
def test_web_mission_log_lists_the_f11_log(tmp_path, monkeypatch, side):
    chromium = shutil.which("chromium") or shutil.which("chromium-browser")
    if not chromium:
        pytest.skip("Optional mission log browser contract: no Chromium")
    role = "bridge" if side == "frigate" else "uboot"
    en, de = catalogs()
    game = Game(seed=913, start_menu=False, audio_enabled=False, language="de")
    console = game.commander
    console.port = 0
    console._translations = {
        "en": {key: value for key, value in en.items() if key.startswith(PREFIX)},
        "de": {key: value for key, value in de.items() if key.startswith(PREFIX)},
    }
    console._contact_analysis_assets = {}
    console._manual_pages = {}
    html = inject_probe(index_html(), "log-test.js")
    copy_assets(tmp_path, html)
    monkeypatch.setattr(server.resources, "files", lambda _package: tmp_path)
    console.activate(game)
    count = 60 if side == "uboot" else 120
    console.server._http.assets["/log-test.js"] = (
        "text/javascript; charset=utf-8",
        PROBE.replace("__CODE__", json.dumps(console.pairing_code))
        .replace("__ROLE__", role).replace("__COUNT__", str(count)).encode("utf-8"))
    console.bridge.allowed = True
    if side == "uboot":
        game.local_side = "uboot"
        boat = game.claim_opfor_sub()
        for index in range(count):
            boat.notice(game.sim_t, CATEGORIES[index % 7], f"{index:03d} {LONG}",
                        stamp="08:%02d" % (index % 60))
    else:
        for index in range(count):
            game.feed.add("08:%02d" % (index % 60), CATEGORIES[index % 7],
                          f"{index:03d} {LONG}")

    def f11_texts():
        if side == "uboot":
            return [str(localize(row["text"], game.tr)) for row in game.opfor.feed][::-1]
        return [str(localize(entry.text, game.tr)) for entry in game.feed.entries][::-1]

    profile = tmp_path / "browser"
    log = (tmp_path / "chromium.log").open("wb")
    process = subprocess.Popen([
        chromium, "--headless", "--no-sandbox", "--disable-gpu",
        "--disable-background-networking", "--no-first-run",
        "--no-default-browser-check", "--disable-dev-shm-usage",
        f"--user-data-dir={profile}", "--window-size=1600,1000",
        "--remote-debugging-port=0",
        f"http://{console.address[0]}:{console.address[1]}/",
    ], stdout=subprocess.DEVNULL, stderr=log)
    granted = added = False
    baseline = None
    root = {}
    started = time.monotonic()
    try:
        # No simulation steps: the published log is exactly the log above.
        while process.poll() is None and time.monotonic() - started < 120:
            if not granted:
                clients = console.server.client_statuses()
                if clients:
                    assert console.server.grant_station(clients[0]["client_id"], role)
                    granted = True
            console.pump(game)
            time.sleep(.05)
            root = page_dataset(profile) or root
            if root.get("baseline") and not added:
                baseline = f11_texts()
                if side == "uboot":
                    game.opfor.notice(game.sim_t, "sonar", "Neue Zeile", stamp="09:00")
                else:
                    game.feed.add("09:00", "sonar", "Neue Zeile")
                added = True
            if root.get("logTest"):
                break
    finally:
        process.kill()
        process.wait(timeout=5)
        log.close()
        console.stop()
        game.audio.shutdown()
    assert root.get("logTest") == "passed", root.get(
        "failure", (tmp_path / "chromium.log").read_text(errors="replace")[-2000:])
    # The browser lists the F11 log, newest first, before and after a new line.
    assert json.loads(root["baseline"]) == baseline
    assert json.loads(root["texts"]) == f11_texts()
    assert root["meta"].startswith("[08:")
    # A long log scrolls inside its drawer and leaves the chart its room.
    scroll_h, client_h, stage_h, page_w, view_w = json.loads(root["scroll"])
    assert scroll_h > client_h and client_h <= 260
    assert stage_h > 400
    assert page_w <= view_w
