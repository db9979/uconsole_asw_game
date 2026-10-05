"""Real-browser contract for host-granted full-truth SimLog diagnostics."""

import json
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from commander_web import index_html, inject_probe, WEB_ROUTES

from test_commander_assets import ASSETS, PREFIX, Document, catalogs
from test_commander_browser_sessions_v2 import (SESSION_ROLES, STATIONS, _direct_fire_browser_states,
                                                _station_record)


SIMLOG_BROWSER = r"""
"use strict";
const nativeFetch = window.fetch.bind(window);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const assert = (value, message) => { if (!value) throw new Error(message); };
const $test = (id) => document.getElementById(id);
const session = __SESSION__;
const simlog = __SIMLOG__;
const state = __STATE__;
const chart = __CHART__;
const errors = [];
window.addEventListener("error", (event) => errors.push(event.message));
window.addEventListener("unhandledrejection", (event) => errors.push(String(event.reason)));
window.requestAnimationFrame = (callback) => setTimeout(() => callback(performance.now()), 16);
location.hash = "#simlog";
window.fetch = async (url, options = {}) => {
  const path = new URL(String(url), location.href).pathname;
  if (path === "/api/v2/session") return new Response(JSON.stringify(session), {status: 200});
  if (path === "/api/v2/ui") return nativeFetch(url, options);
  if (path === "/api/v2/contacts") return new Response(JSON.stringify({version: 1, profiles: []}), {status: 200});
  if (path === "/api/v2/state") return new Response(JSON.stringify(state), {status: 200});
  if (path === "/api/v2/chart") return new Response(JSON.stringify(chart), {status: 200});
  if (path === "/api/v2/simlog") return new Response(JSON.stringify(simlog), {status: 200});
  if (path === "/api/v2/proposals") return new Response(JSON.stringify({protocol: 2, session: state.session,
    epoch: state.epoch, role: state.role, target: null, navigation: null}), {status: 200});
  if (path === "/api/v2/events") return new Response(JSON.stringify({protocol: 2, session: state.session,
    epoch: state.epoch, role: state.role, latest_seq: 0, events: []}), {status: 200});
  if (path === "/api/v2/results") return new Response(JSON.stringify({protocol: 2, results: []}), {status: 200});
  throw new Error(`unexpected request ${path}`);
};
async function until(check, message) {
  for (let index = 0; index < 700; index++) { if (check()) return; await sleep(20); }
  throw new Error(`${message}; errors=${errors.join(" | ")}; status=${$test("simlog-status")?.textContent}`);
}
async function run() {
  await until(() => !$test("simlog-view").hidden, "SimLog view missing");
  await until(() => $test("simlog-current").querySelector("table.simlog-table"), "contact table missing");
  const tables = [...$test("simlog-current").querySelectorAll("table.simlog-table")];
  const headers = tables.map((table) => [...table.querySelectorAll("th")].map((cell) => cell.textContent));
  assert(headers.some((row) => row.includes(__DISTANCE_OWN__)), `own-ship distance column missing: ${headers.flat().join(",")}`);
  const rows = tables.flatMap((table) => [...table.querySelectorAll("tr")].slice(1).map((row) => [...row.children].map((cell) => cell.textContent)));
  assert(rows.length >= 4, `all truth sections are listed: ${rows.length}`);
  const air = rows.find((row) => row.includes("A-3"));
  assert(air, "aircraft row missing");
  assert(air.some((cell) => cell.includes("10668") || cell.includes("10,668") || cell.includes("10.668")), `altitude shown: ${air.join("|")}`);
  assert(air.some((cell) => cell === "live"), `aircraft kind shown: ${air.join("|")}`);
  const ship = rows.find((row) => row[0] === "S-4");
  assert(ship, "surface truth row shown");
  const shipHeaders = headers[tables.findIndex((table) => [...table.querySelectorAll("td")].some((cell) => cell.textContent === "S-4"))];
  const distanceIndex = shipHeaders.indexOf(__DISTANCE_OWN__);
  assert(ship[distanceIndex].includes("11.2") || ship[distanceIndex].includes("11,2"),
    `distance to own ship shown: ${ship.join("|")}`);
  const text = $test("simlog-current").textContent;
  assert(text.includes("120"), "own ship values shown");
  assert($test("simlog-current").querySelectorAll(".simlog-metrics-wrap").length >= 3, "own ship, environment and weapons shown");
  const button = [...$test("simlog-current").querySelectorAll("button")].find((item) => item.textContent === __MAP_OPEN__);
  assert(button, "map button missing");
  button.click();
  await until(() => $test("simlog-map-dialog").open, "map dialog did not open");
  assert(!$test("simlog-map-dialog").hidden, "map dialog is visible");
  assert($test("simlog-map-count").textContent.includes("3"), `own ship plus both contacts plotted: ${$test("simlog-map-count").textContent}`);
  assert($test("simlog-map-units").children.length === 3, "plotted unit list");
  await sleep(150);
  assert($test("simlog-map").width > 1, "map canvas was drawn");
  $test("simlog-map-close").click();
  await until(() => !$test("simlog-map-dialog").open && $test("simlog-map-dialog").hidden, "map dialog closes");
  assert(errors.length === 0, `no script errors: ${errors.join(" | ")}`);
  document.documentElement.setAttribute("data-simlog-test", "passed");
}
run().catch((error) => {
  document.documentElement.setAttribute("data-simlog-test", "failed");
  document.documentElement.setAttribute("data-failure", String(error.stack || error));
});
"""


def test_web_simlog_shows_all_projected_values_and_a_map_in_chromium(tmp_path):
    chromium = (shutil.which("chromium") or shutil.which("chromium-browser")
                or shutil.which("google-chrome"))
    if not chromium:
        pytest.skip("Optional web SimLog browser contract: no installed Chromium")
    en, de = catalogs()
    stations = {station: _station_record() for station in SESSION_ROLES}
    stations["opz"] = _station_record("mine", station_generation=1, command=True)
    session = dict(protocol=2, client_id="log-client", name="Log Watch",
                   csrf="log-csrf", ordinal=0, presence=1.0, next_command_seq=0, host=None, lobby=None, handover=[], observer=False,
                   station="opz", requested_station=None, station_generation=1,
                   active_station="opz", active_generation=1, simlog=True,
                   stations=stations,
                   grants=dict(command=True, direct_fire=False, simlog=True,
                               sonar_audio=False))
    state = _direct_fire_browser_states()["opz"]
    row = dict(state["opz"]["observations"][0])
    air = dict(row, ref="air-ref", label="A-3", domain="AIR", source="RADAR-L",
               bearing=80.0, range_nm=30.0, x=280.0, y=245.0, course=90.0,
               speed_kn=447.0, altitude_m=10668.0)
    surface = dict(row, ref="ship-ref", label="S-4", domain="SURFACE",
                   source="RADAR-S", x=255.0, y=240.0, course=45.0,
                   speed_kn=14.0, altitude_m=None)
    state["opz"]["observations"] = [air, surface]
    state["opz"]["asm_observations"] = []
    state["opz"]["source_classifications"] = [
        dict(ref="air-ref", source="RADAR-L", classification="FLUGZEUG")]
    state["opz"]["own_assets"]["ship"]["speed"] = 120.0
    truth = dict(mission_t=10.0, result=None,
                 world=dict(hour=12.0, sea_state=2, night=False),
                 ship=dict(x=250.0, y=250.0, course=0.0, speed=120.0,
                           damage=0.0, sunk=False, stations={}),
                 weapons=dict(torpedoes=8, vls=16, ciws=500, aa=200,
                              chaff_cd=0.0),
                 subs=[], surfaces=[dict(id="S-4", kind="warship", name=None,
                                         mmsi=None, x=255.0, y=240.0,
                                         course=45.0, speed=14.0, sunk=False,
                                         damage=0.0)],
                 animals=[], torpedoes=[], enemy_torpedoes=[], decoys=[],
                 asms=[], essms=[], asrocs=[], nixies=[], buoys=[],
                 helo=dict(state="READY", x=250.0, y=250.0, airborne=False),
                 flights=[dict(seq=3, kind="live", callsign="A-3",
                               icao24="abc123", x=280.0, y=245.0,
                               course=90.0, speed=447.0, alt_m=10668.0)],
                 raiders=[], radars=dict(surface=True, air=True))
    simlog = dict(protocol=2, session=state["session"], epoch=state["epoch"],
                  role="opz", entries=[dict(seq=1, t=10.0, stamp="12:00",
                                            state=state, truth=truth)])
    chart = dict(protocol=2, revision=state["session"], size_nm=500.0,
                 landmasses=[], disclaimer="Synthetic test chart")
    html = inject_probe(index_html(), "simlog-test.js")
    script = (SIMLOG_BROWSER.replace("__SESSION__", json.dumps(session))
              .replace("__SIMLOG__", json.dumps(simlog))
              .replace("__STATE__", json.dumps(state))
              .replace("__CHART__", json.dumps(chart))
              .replace("__AIRCRAFT__", json.dumps(en[PREFIX + "class_aircraft"]))
              .replace("__DISTANCE_OWN__", json.dumps(en[PREFIX + "distance_own"]))
              .replace("__MAP_OPEN__", json.dumps(en[PREFIX + "simlog_map_open"])))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def reply(self, content, mime="application/json"):
            body = (content if isinstance(content, bytes) else content.encode()
                    if isinstance(content, str) else json.dumps(content).encode())
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/":
                self.reply(html, "text/html")
            elif self.path == "/simlog-test.js":
                self.reply(script, "text/javascript")
            elif self.path in WEB_ROUTES:
                self.reply(WEB_ROUTES[self.path][1], WEB_ROUTES[self.path][0])
            elif self.path in ("/api/v2/ui?lang=en", "/api/v2/ui?lang=de"):
                source = de if self.path.endswith("de") else en
                self.reply({key: value for key, value in source.items()
                            if key.startswith(PREFIX)})
            else:
                self.send_error(404)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(
            [chromium, "--headless", "--no-sandbox", "--disable-gpu",
             "--disable-background-networking", "--no-first-run",
             "--no-default-browser-check", "--disable-dev-shm-usage",
             f"--user-data-dir={tmp_path / 'simlog-browser'}",
             "--virtual-time-budget=30000", "--dump-dom",
             f"http://127.0.0.1:{server.server_port}/"],
            capture_output=True, text=True, timeout=45)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert result.returncode == 0, result.stderr
    root = next((attrs for tag, attrs in Document(result.stdout).elements
                 if tag == "html"), {})
    assert root.get("data-simlog-test") == "passed", root.get(
        "data-failure", result.stdout[-5000:] + result.stderr[-2000:])
