"""Real-browser contracts for the Protocol-v2 lobby and role shell."""

import json
import shutil
import subprocess
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import pygame

from src.commander import server as commander_transport
from src.core.game import Game
from src.sonar.sonar import Contact
from test_commander_assets import (ASSETS, PREFIX, Document, browser_contact_analysis,
                                   browser_state, catalogs)


STATIONS = ("bridge", "sonar", "weapons", "damage", "opz", "radio",
            "engine", "helicopter", "eloka")


def _station_record(status="available", *, requested=False, request_generation=0,
                    station_generation=None, command=False, direct_fire=False,
                    sonar_audio=False):
    return {
        "status": status,
        "requested": requested,
        "request_generation": request_generation,
        "station_generation": station_generation,
        "grants": {
            "command": command,
            "direct_fire": direct_fire,
            "sonar_audio": sonar_audio,
        },
    }

BROWSER_SESSION = r"""
"use strict";
const issued = [];
const consoleErrors = [];
const nativeConsoleError = console.error.bind(console);
console.error = (...args) => {
  consoleErrors.push(args.map((item) => String(item?.stack || item)).join(" "));
  nativeConsoleError(...args);
};
const nativeFetch = window.fetch.bind(window);
window.fetch = async (url, options = {}) => {
  const entry = {url: String(url), options};
  issued.push(entry);
  const response = await nativeFetch(url, options);
  if (String(url).endsWith("/api/v2/pair") || String(url).endsWith("/api/v2/session")) {
    try { entry.session = await response.clone().json(); } catch (_) {}
  }
  return response;
};
window.requestAnimationFrame = (callback) => setTimeout(() => callback(performance.now()), 16);
const $test = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const assert = (value, message) => { if (!value) throw new Error(message); };
async function until(check, message) {
  for (let index = 0; index < 700; index++) {
    if (check()) return;
    await sleep(20);
  }
  throw new Error(`${message}; console=${consoleErrors.join(" | ")}`);
}
const operational = () => issued.filter((entry) => /\/api\/v2\/(state|chart|simlog)$/.test(entry.url));
async function run() {
  await until(() => !$test("shell").hidden, "translations loaded");
  assert(issued[0].url.endsWith("/api/v2/session"), "resume is the first request");
  if (location.hash !== "#resumed") {
    $test("name").value = "Lobby Watch";
    $test("code").value = "123ABC";
    $test("pair-form").requestSubmit();
    await until(() => !$test("lobby").hidden, "pair enters authenticated lobby");
    const cards = [...$test("station-cards").children];
    assert(cards.length === 9, "lobby has exactly nine station cards");
    assert(cards.map((card) => card.dataset.station).join(",") === __STATIONS__, "canonical station order");
    assert(cards[1].classList.contains("station-occupied") && cards[0].classList.contains("station-available"), "occupancy is rendered");
    assert(operational().length === 0, "unassigned client fetches no operational state");
    const requestButton = cards[0].querySelector("button");
    assert(requestButton.type === "button" && requestButton.tabIndex === 0, "station request is a native keyboard control");
    requestButton.focus();
    requestButton.dispatchEvent(new PointerEvent("pointerdown", {bubbles: true, pointerType: "touch", isPrimary: true}));
    requestButton.click();
    await until(() => $test("lobby-status").textContent.includes(__PENDING__), "request is visibly pending");
    const mutation = issued.find((entry) => entry.url.endsWith("/api/v2/stations/request"));
    assert(mutation.options.body === JSON.stringify({station: "bridge"}), "station request envelope is exact");
    assert(mutation.options.credentials === "same-origin" && mutation.options.headers["X-U-Jagd-CSRF"] === "csrf-1", "request uses cookie and CSRF");
    await until(() => issued.filter((entry) => entry.url.endsWith("/api/v2/session")).length >= 2, "lobby polls session");
    assert($test("operations").hidden && operational().length === 0, "request never implies an immediate grant");
    await until(() => !$test("operations").hidden, "host grant is discovered by session polling");
    assert($test("role-rail-title").textContent === __BRIDGE__ && !$test("role-rail").hidden, "assigned role is prominent in desktop rail");
    assert(!$test("mobile-station").disabled && $test("mobile-station").value === "bridge", "mobile station switcher reflects assignment");
    assert($test("mobile-station").options.length === 1, "station switcher contains only granted stations");
    $test("add-station").click();
    assert(!$test("lobby").hidden && !$test("lobby-back").hidden && $test("operations").hidden,
      "add station is a separate request view");
    $test("lobby-back").click();
    assert($test("lobby").hidden, "station request view returns without changing the active lease");
    assert($test("propose").disabled, "commands remain gated by session grant");
    assert($test("engine-telegraph").disabled && $test("helicopter-launch").disabled,
      "controls belonging to other roles remain disabled");
    location.hash = "#simlog";
    await sleep(150);
    assert(!issued.some((entry) => entry.url.endsWith("/api/v2/simlog")), "SimLog remains gated by its grant");
    location.hash = "";
    $test("release-station").click();
    await until(() => !$test("lobby").hidden, "release returns to lobby");
    const release = issued.find((entry) => entry.url.endsWith("/api/v2/stations/release"));
    assert(release.options.body === JSON.stringify({station: "bridge", station_generation: 1, active_generation: 1}) &&
      release.options.headers["X-U-Jagd-CSRF"] === "csrf-1", "release envelope and CSRF are exact");
    const afterRelease = operational().length;
    await sleep(1100);
    assert(operational().length === afterRelease, "released client stops operational fetches");
    const damage = [...$test("station-cards").children].find((card) => card.dataset.station === "damage").querySelector("button");
    damage.click();
    await until(() => $test("lobby-status").textContent.includes(__FAILED__), "mutation failure is explicit");
    const failedCount = issued.filter((entry) => entry.url.endsWith("/api/v2/stations/request")).length;
    await sleep(700);
    assert(issued.filter((entry) => entry.url.endsWith("/api/v2/stations/request")).length === failedCount, "failed mutation is never retried");
    await until(() => !$test("operations").hidden && $test("role-rail-title").textContent === __SONAR__, "later host grant is discovered independently");
    await nativeFetch("/test/reload-ready");
    location.hash = "#resumed";
    location.reload();
    return;
  }
  await until(() => !$test("operations").hidden, "assigned cookie session resumes after reload");
  assert(issued[0].session.station === "sonar" && !issued.some((entry) => entry.url.endsWith("/api/v2/pair")), "reload resumes exact role without pairing");
  $test("sonar-control-page").value = "analysis";
  $test("sonar-control-page").dispatchEvent(new Event("change", {bubbles: true}));
  $test("sonar-gain").value = "4";
  $test("sonar-gain").dispatchEvent(new Event("input", {bubbles: true}));
  await until(() => !$test("lobby").hidden, "role loss returns to lobby");
  assert($test("lobby-status").textContent.includes(__REVOKED__), "role loss is explicit");
  assert($test("operations").hidden && !$test("track-list").textContent && !$test("mission-name").textContent, "role loss clears role-local tactical DOM");
  assert($test("sonar-control-page").value === "listen" && $test("sonar-gain").value === "" &&
    $test("sonar-gain").disabled, "role generation change clears local station page and drafts");
  const afterLoss = operational().length;
  await sleep(1100);
  assert(operational().length === afterLoss, "revoked client performs session-only polling");
  document.documentElement.dataset.sessionTest = "passed";
}
window.addEventListener("DOMContentLoaded", () => run().catch((error) => {
  document.documentElement.dataset.sessionTest = "failed";
  document.documentElement.dataset.failure = String(error.stack || error);
}));
"""


REAL_ROLE_SESSION = r"""
"use strict";
const nativeFetch = window.fetch.bind(window);
const NativeError = window.Error;
const protocolErrors = [];
const consoleErrors = [];
const nativeConsoleError = console.error.bind(console);
console.error = (...args) => {
  consoleErrors.push(args.map((item) => String(item?.stack || item)).join(" "));
  nativeConsoleError(...args);
};
window.Error = function(...args) {
  const error = new NativeError(...args);
  if (["protocol", "chart", "session", "results"].includes(String(args[0]))) protocolErrors.push(error.stack || String(error));
  return error;
};
window.Error.prototype = NativeError.prototype;
const events = [];
let latestRole = null;
let latestStation = null;
let sessionPolls = 0;
let resultPolls = 0;
let wasAssigned = false;
let roleLost = false;
let redactedExposed = false;
const stationActions = [];
const visualDraws = new Set();
const visualCanvasIds = new Set(["role-map", "sonar-broadband", "sonar-lofar", "sonar-demon",
  "sonar-tma-plot", "sonar-environment", "sonar-active", "damage-schematic",
  "engine-instruments", "eloka-scope", "weapons-system"]);
for (const method of ["fillRect", "stroke", "arc"]) {
  const native = CanvasRenderingContext2D.prototype[method];
  CanvasRenderingContext2D.prototype[method] = function(...args) {
    if (visualCanvasIds.has(this.canvas.id)) visualDraws.add(this.canvas.id);
    return native.apply(this, args);
  };
}
window.fetch = async (url, options = {}) => {
  const path = new URL(String(url), location.href).pathname;
  if (path.endsWith("/api/v2/commands") && options.body) {
    stationActions.push(JSON.parse(options.body).action);
  }
  const response = await nativeFetch(url, options);
  if (/\/api\/v2\/(session|state|chart|results)$/.test(path) && response.ok) {
    const value = await response.clone().json();
    if (path.endsWith("/session")) {
      sessionPolls += 1;
      latestStation = value.station;
      if (value.station !== null) wasAssigned = true;
      else if (wasAssigned) roleLost = true;
      events.push(`session:${value.station}`);
    } else if (path.endsWith("/state")) {
      latestRole = value.role;
      events.push(`state:${value.role}`);
    } else if (path.endsWith("/chart")) {
      events.push("chart");
    } else {
      resultPolls += 1;
      events.push(`results:${JSON.stringify(value)}`);
    }
  }
  return response;
};
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const assert = (value, message) => { if (!value) throw new NativeError(message); };
async function until(check, message) {
  for (let index = 0; index < 1500; index++) {
    if (check()) return;
    await sleep(20);
  }
  throw new NativeError(message);
}
async function run() {
  await until(() => !document.getElementById("shell").hidden, "translations loaded");
  document.getElementById("name").value = "Real Role Watch";
  document.getElementById("code").value = __CODE__;
  document.getElementById("pair-form").requestSubmit();
  const rendered = new Set();
  const visualRendered = new Set();
  const layoutChecked = new Set();
  const sonarPages = new Set();
  const clearedCanvases = new Set();
  let previousRole = null;
  const visualFor = {bridge: "role-map", sonar: "sonar-broadband", opz: "role-map",
    eloka: "eloka-scope", engine: "engine-instruments", damage: "damage-schematic",
    radio: "role-map", helicopter: "role-map", weapons: "weapons-system"};
  const equivalentFor = {bridge: "role-map-text", sonar: "sonar-broadband-text", opz: "role-map-text",
    eloka: "eloka-scope-text", engine: "engine-instruments-text", damage: "damage-schematic-text",
    radio: "role-map-text", helicopter: "role-map-text", weapons: "weapons-system-text"};
  let commandSent = false;
  let fusionSent = false;
  let opzDiagnostic = "";
  for (let index = 0; index < 10000; index++) {
    fusionSent = stationActions.includes("opz_create_fusion");
    const connected = document.getElementById("connection").dataset.state === "connected";
    if (latestRole === null && latestStation !== null && !document.getElementById("operations").hidden) redactedExposed = true;
    if (connected && latestRole === latestStation && latestRole !== null &&
        !document.getElementById("operations").hidden) {
      rendered.add(latestRole);
      const station = document.getElementById(`station-${latestRole}`);
      const visualBounds = document.getElementById("role-visuals").getBoundingClientRect();
      const controlBounds = station.querySelector(".station-grid").getBoundingClientRect();
      if (innerWidth >= 1000) {
        assert(visualBounds.width >= innerWidth * .45, `instrument too narrow: ${latestRole}`);
        assert(visualBounds.top < innerHeight * .5, `instrument below fold: ${latestRole}`);
        assert(controlBounds.left >= visualBounds.right - 2, `controls not beside instrument: ${latestRole}`);
      }
      const stationBounds = station.getBoundingClientRect();
      assert(visualBounds.left >= stationBounds.left - 1 && visualBounds.right <= stationBounds.right + 1,
        `instrument exceeds station: ${latestRole}`);
      assert(controlBounds.left >= stationBounds.left - 1 && controlBounds.right <= stationBounds.right + 1,
        `controls exceed station: ${latestRole}`);
      const cards = [...station.querySelectorAll(":scope > .station-grid > *")]
        .filter((element) => !element.hidden && getComputedStyle(element).display !== "none");
      assert(!station.querySelector(":scope > .station-grid > .station-card-view > details"),
        `station information collapsed by default: ${latestRole}`);
      const cardBounds = cards.map((element) => element.getBoundingClientRect());
      assert(cardBounds.every((bounds) => bounds.left >= controlBounds.left - 1 && bounds.right <= controlBounds.right + 1),
        `control card exceeds column: ${latestRole}`);
      assert(cardBounds.every((first, index) => cardBounds.slice(index + 1).every((second) =>
        Math.min(first.right, second.right) - Math.max(first.left, second.left) <= 1 ||
        Math.min(first.bottom, second.bottom) - Math.max(first.top, second.top) <= 1)),
        `control cards overlap: ${latestRole}`);
      const populated = cards.flatMap((card) => [...card.querySelectorAll(".detail-metrics, .station-list")])
        .filter((element) => element.children.length && !element.hidden && getComputedStyle(element).display !== "none");
      assert(populated.every((element) => element.getClientRects().length && element.getBoundingClientRect().height > 0),
        `station values hidden: ${latestRole}`);
      const textOverflow = [...station.querySelectorAll("h2, h3, h4, p, dt, dd, label, button, summary, output")]
        .filter((element) => !element.hidden && getComputedStyle(element).display !== "none" && element.clientWidth > 0)
        .some((element) => element.scrollWidth > element.clientWidth + 2);
      assert(!textOverflow, `station text overflows horizontally: ${latestRole}`);
      layoutChecked.add(latestRole);
      assert(["lookout", "guide", "contacts"].every((name) => document.getElementById(`tab-${name}`).hidden), "legacy tabs still visible");
      const canvas = document.getElementById(visualFor[latestRole]);
      const equivalent = document.getElementById(equivalentFor[latestRole]);
      if (canvas.width > 1 && canvas.height > 1 && equivalent.textContent.trim() && visualDraws.has(canvas.id) &&
          !document.getElementById("role-visuals").hidden) visualRendered.add(latestRole);
      if (previousRole && previousRole !== latestRole) {
        const previousCanvas = visualFor[previousRole];
        if (previousCanvas !== "role-map" && document.getElementById(previousCanvas).width === 1)
          clearedCanvases.add(previousRole);
      }
      previousRole = latestRole;
      if (latestRole === "sonar") {
        const bearingSubmit = document.getElementById("sonar-bearing-submit");
        if (!stationActions.includes("sonar_set_listen_bearing") && !bearingSubmit.disabled) {
          document.getElementById("sonar-tab-broadband").click();
          await sleep(25);
          const broadband = document.getElementById("sonar-broadband");
          const bounds = broadband.getBoundingClientRect();
          const scale = bounds.width / broadband.clientWidth;
          broadband.dispatchEvent(new MouseEvent("click", {
            bubbles: true, clientX: bounds.left + (46 + (broadband.clientWidth - 64) * .25) * scale,
            clientY: bounds.top + bounds.height / 2,
          }));
        }
        const tabs = [...document.querySelectorAll("[data-sonar-visual]")];
        for (const next of tabs.filter((button) => !sonarPages.has(button.dataset.sonarVisual))) {
          next.click();
          const page = next.dataset.sonarVisual;
          const panel = document.querySelector(`[data-sonar-plot="${page}"]`);
          const pageCanvas = panel.querySelector("canvas");
          const pageText = panel.querySelector(".visual-equivalent");
          await sleep(25);
          if (pageCanvas.width > 1 && pageCanvas.height > 1 && pageText.textContent.trim() &&
               visualDraws.has(pageCanvas.id)) sonarPages.add(page);
        }
        if (sonarPages.size === 6 && !document.getElementById("role-visuals").hidden)
          visualRendered.add("sonar");
      }
    }
    const submit = document.getElementById("bridge-course-submit");
    if (!commandSent && latestRole === "bridge" && !submit.disabled) {
      document.getElementById("bridge-course").value = "123";
      document.getElementById("bridge-course-form").requestSubmit();
      commandSent = true;
    }
    const stationSubmit = document.getElementById("apply-classification");
    const sonarActions = stationActions.filter((action) => action === "sonar_classify").length;
    const sonarReleases = stationActions.filter((action) => action === "sonar_set_release").length;
    if (latestRole === "sonar" && sonarActions < 2) {
      const contacts = document.getElementById("track-list").querySelectorAll("button");
      contacts[sonarActions]?.click();
      document.getElementById("classification").value = "U_BOOT";
      if (!stationSubmit.disabled) document.getElementById("classification-form").requestSubmit();
    } else if (latestRole === "sonar" && sonarReleases < 2) {
      const contacts = document.getElementById("track-list").querySelectorAll("button");
      contacts[sonarReleases]?.click();
      const release = document.getElementById("sonar-release");
      if (!release.disabled) release.click();
    }
    if (latestRole === "opz" && !fusionSent) {
      const reports = document.getElementById("track-list").querySelectorAll("button");
      if (reports.length >= 2) {
        reports[0].click(); document.getElementById("opz-mark").click();
        reports[1].click(); document.getElementById("opz-mark").click();
        opzDiagnostic = `reports=${reports.length}, createDisabled=${document.getElementById("opz-create-fusion").disabled}, marks=${document.getElementById("opz-mark-status").textContent}, pending=${document.getElementById("station-command-status").textContent}`;
        if (!document.getElementById("opz-create-fusion").disabled) {
          document.getElementById("opz-create-fusion").click();
        }
      }
    }
    if (["bridge", "sonar", "opz", "eloka", "engine", "damage", "radio", "helicopter", "weapons"].every((role) => rendered.has(role)) &&
        visualRendered.size === 9 && layoutChecked.size === 9 && sonarPages.size === 6 &&
        fusionSent && resultPolls > 0 && sessionPolls >= 12) break;
    await sleep(20);
  }
  assert(protocolErrors.length === 0 && consoleErrors.length === 0,
    `caught JS failures: ${[...protocolErrors, ...consoleErrors].join("\n---\n")}; events=${events.join(",")}`);
  const stateAndCharts = events.filter((entry) => entry === "chart" || entry.startsWith("state:"));
  for (const role of ["bridge", "sonar", "opz", "eloka", "engine", "damage", "radio", "helicopter", "weapons"]) {
    assert(rendered.has(role), `role not rendered: ${role}; opz=${opzDiagnostic}; actions=${stationActions.join(",")}; events=${events.join(",")}`);
    assert(visualRendered.has(role), `role visualization missing: ${role}`);
    assert(layoutChecked.has(role), `role layout unchecked: ${role}`);
    assert(stateAndCharts.some((entry, index) => entry === `state:${role}` &&
      stateAndCharts[index + 1] === "chart" && stateAndCharts[index + 2] === `state:${role}`),
      `missing chart sandwich: ${role}; events=${events.join(",")}`);
  }
  assert(events.includes("state:null"), `unpublished/redacted state was not exercised: ${events.join(",")}`);
  assert(sonarPages.size === 6, `sonar pages not rendered with text equivalents: ${[...sonarPages].join(",")}`);
  assert(["sonar", "eloka", "engine", "damage"].every((role) => clearedCanvases.has(role)),
    `role-switch canvas clearing missing: ${[...clearedCanvases].join(",")}`);
  assert(resultPolls > 0, `result polling missing: ${events.join(",")}`);
  assert(stationActions.filter((action) => action === "sonar_classify").length === 2,
    `Sonar classifications missing: ${stationActions.join(",")}`);
  assert(stationActions.filter((action) => action === "sonar_set_release").length === 2,
    `Sonar releases missing: ${stationActions.join(",")}`);
  assert(stationActions.filter((action) => action === "sonar_set_listen_bearing").length === 1,
    `Broadband bearing click missing: ${stationActions.join(",")}`);
  assert(stationActions.includes("opz_create_fusion"),
    `OPZ fusion missing: ${stationActions.join(",")}`);
  assert(sessionPolls >= 12, `session presence polling stopped: ${sessionPolls}`);
  assert(!roleLost, `station lease expired or role was lost: ${events.join(",")}`);
  assert(!redactedExposed, "redacted state exposed the operational shell");
  document.documentElement.dataset.realRoleTest = "passed";
}
window.addEventListener("error", (event) => {
  document.documentElement.dataset.failure = String(event.error?.stack || event.message);
});
window.addEventListener("unhandledrejection", (event) => {
  document.documentElement.dataset.failure = String(event.reason?.stack || event.reason);
});
window.addEventListener("DOMContentLoaded", () => run().catch((error) => {
  document.documentElement.dataset.realRoleTest = "failed";
  document.documentElement.dataset.failure = String(error.stack || error);
}));
"""


DIRECT_FIRE_BROWSER = r"""
"use strict";
const nativeFetch = window.fetch.bind(window);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const assert = (value, message) => { if (!value) throw new Error(message); };
const $test = (id) => document.getElementById(id);
const session = __SESSION__;
const states = __STATES__;
const chart = __CHART__;
const commands = [];
let results = [];
let failNext = false;
let currentRef = "weapon-ref-a";
const browserErrors = [];
window.addEventListener("error", (event) => browserErrors.push(event.message));
window.addEventListener("unhandledrejection", (event) => browserErrors.push(String(event.reason)));
const nativeConsoleError = console.error.bind(console);
console.error = (...args) => { browserErrors.push(args.map(String).join(" ")); nativeConsoleError(...args); };
function switchRole(role) {
  session.active_station = role;
  session.active_generation += 1;
  session.station = role;
  session.station_generation = session.stations[role].station_generation;
  session.grants = {...session.stations[role].grants, simlog: session.simlog};
}
function state() {
  const value = structuredClone(states[session.station]);
  value.seq += commands.length;
  if (session.station === "weapons") {
    value.weapons.target_choices[0].ref = currentRef;
    value.weapons.tubes[0].state = document.documentElement.dataset.notReady === "true" ? "reloading" : "ready";
  }
  return value;
}
window.fetch = async (url, options = {}) => {
  const path = new URL(String(url), location.href).pathname;
  if (path === "/api/v2/session") return new Response(JSON.stringify(session), {status: session.client_id ? 200 : 401});
  if (path === "/api/v1/ui") return nativeFetch(url, options);
  if (path === "/api/v1/contacts") return new Response(JSON.stringify({version: 1, profiles: []}), {status: 200});
  if (path === "/api/v2/pair") return new Response(JSON.stringify(session), {status: 200});
  if (path === "/api/v2/state") return new Response(JSON.stringify(state()), {status: 200});
  if (path === "/api/v2/chart") return new Response(JSON.stringify(chart), {status: 200});
  if (path === "/api/v2/results") {
    const value = results;
    results = [];
    return new Response(JSON.stringify({protocol: 2, results: value}), {status: 200});
  }
  if (path === "/api/v2/commands") {
    const body = JSON.parse(options.body);
    commands.push(body);
    if (failNext) { failNext = false; return new Response("", {status: 503}); }
    results.push({id: body.id, seq: body.seq, status: body.action === "opz_launch_chaff" ? "rejected" : "applied",
      reasoncode: body.action === "opz_launch_chaff" ? "not_ready" : "ok"});
    return new Response("", {status: 202});
  }
  throw new Error(`unexpected request ${path}`);
};
async function until(check, message) {
  for (let index = 0; index < 700; index++) { if (check()) return; await sleep(20); }
  throw new Error(`${message}; connection=${$test("connection")?.textContent}; errors=${browserErrors.join(" | ")}`);
}
const exact = (body, action, params, station) => {
  assert(Object.keys(body).sort().join(",") === "action,active_generation,id,params,protocol,resource_revision,seq,station,station_generation,world_epoch,world_session", `${action} envelope fields`);
  assert(body.protocol === 2 && body.action === action && body.station === station, `${action} routing`);
  assert(JSON.stringify(body.params) === JSON.stringify(params), `${action} exact params: ${JSON.stringify(body.params)}`);
  assert(!JSON.stringify(body).includes("target_id") && !JSON.stringify(body).includes("track_id"), `${action} leaked identifier`);
};
async function fire(id, expectedCount) {
  const button = $test(id);
  button.click();
  assert(commands.length === expectedCount, `${id} first activation sent a command`);
  assert(button.classList.contains("armed"), `${id} did not enter confirmation state`);
  button.click();
  await until(() => commands.length === expectedCount + 1, `${id} did not send after confirmation`);
}
async function terminal() {
  await until(() => !$test("station-command-status").textContent.includes("Pending") &&
    !$test("station-command-status").textContent.includes("Ausstehend") &&
    $test("station-command-status").textContent, "terminal result missing");
}
async function run() {
  await until(() => !$test("shell").hidden, "translations missing");
  await until(() => !$test("station-weapons").hidden, "Weapons role missing");
  assert($test("weapons-fire-torpedo").disabled && $test("weapons-fire-status").textContent.includes(__REVOKED__), "direct-fire grant is not explicit");
  session.grants.direct_fire = true;
  session.stations.weapons.grants.direct_fire = true;
  await until(() => !$test("weapons-fire-target").disabled, "direct-fire grant not discovered");
  $test("weapons-fire-target").value = currentRef;
  $test("weapons-fire-target").dispatchEvent(new Event("change", {bubbles: true}));
  $test("weapons-fire-depth").value = "90";
  $test("weapons-fire-depth").dispatchEvent(new Event("input", {bubbles: true}));
  $test("weapons-fire-torpedo").click();
  document.documentElement.dataset.notReady = "true";
  await until(() => $test("weapons-fire-torpedo").disabled && !$test("weapons-fire-torpedo").classList.contains("armed"), "readiness change did not clear confirmation");
  document.documentElement.dataset.notReady = "false";
  await until(() => !$test("weapons-fire-torpedo").disabled, "readiness did not recover");
  $test("weapons-fire-torpedo").click();
  currentRef = "weapon-ref-b";
  await until(() => $test("weapons-fire-target").value === "" && !$test("weapons-fire-torpedo").classList.contains("armed"), "ref replacement did not clear draft and confirmation");
  $test("weapons-fire-target").value = currentRef;
  $test("weapons-fire-target").dispatchEvent(new Event("change", {bubbles: true}));
  await fire("weapons-fire-torpedo", 0);
  exact(commands[0], "weapons_launch_torpedo", {ref: currentRef, depth_m: 90}, "weapons");
  await terminal();
  $test("weapons-fire-target").value = currentRef;
  $test("weapons-fire-target").dispatchEvent(new Event("change", {bubbles: true}));
  $test("weapons-fire-depth").value = "110";
  $test("weapons-fire-depth").dispatchEvent(new Event("input", {bubbles: true}));
  await fire("weapons-fire-helicopter", 1);
  exact(commands[1], "helicopter_launch_torpedo", {ref: currentRef, depth_m: 110}, "weapons");
  await terminal();
  failNext = true;
  await fire("weapons-fire-nixie", 2);
  exact(commands[2], "weapons_deploy_nixie", {}, "weapons");
  await sleep(1600);
  assert(commands.length === 3, "uncertain direct-fire command was retried");
  switchRole("opz");
  await until(() => !$test("station-opz").hidden && $test("station-weapons").hidden, "wrong-role controls survived role switch");
  assert($test("weapons-fire-target").value === "" && $test("weapons-fire-depth").value === "", "Weapons fire draft survived role switch");
  const roleMap = $test("role-map"), mapRect = roleMap.getBoundingClientRect();
  await until(() => roleMap.width > 1 && mapRect.width > 100, "OPZ role map missing");
  const sweepFrame = roleMap.toDataURL();
  await until(() => roleMap.toDataURL() !== sweepFrame, "published OPZ sweep does not animate between samples");
  states.opz.phase = "paused";
  await until(() => $test("role-visual-state").textContent.includes("Paused") ||
    $test("role-visual-state").textContent.includes("Pausiert"), "paused OPZ state missing");
  await sleep(80);
  const pausedFrame = roleMap.toDataURL();
  await sleep(120);
  assert(roleMap.toDataURL() === pausedFrame, "OPZ sweep continues while paused");
  states.opz.phase = "live";
  await until(() => !$test("opz-fire-target").disabled, "OPZ did not resume");
  states.opz.opz.radar.surface = false; states.opz.opz.radar.air = false;
  await until(() => !$test("opz-radar-surface").checked && !$test("opz-radar-air").checked,
    "radars-off state missing");
  await sleep(80);
  const radarsOffFrame = roleMap.toDataURL();
  await sleep(120);
  assert(roleMap.toDataURL() === radarsOffFrame, "OPZ sweep continues with both radars off");
  states.opz.opz.radar.surface = true; states.opz.opz.radar.air = true;
  await until(() => $test("opz-radar-surface").checked && $test("opz-radar-air").checked,
    "radars did not resume");
  const mapScale = Math.min(mapRect.width, mapRect.height) / 80;
  const contactX = mapRect.left + mapRect.width / 2 + 8 * mapScale;
  const contactY = mapRect.top + mapRect.height / 2 - 8 * mapScale;
  const capture = roleMap.setPointerCapture, release = roleMap.releasePointerCapture;
  roleMap.setPointerCapture = () => {}; roleMap.releasePointerCapture = () => {};
  roleMap.dispatchEvent(new PointerEvent("pointerdown", {bubbles: true, pointerId: 41, isPrimary: true, button: 0, clientX: contactX, clientY: contactY}));
  roleMap.dispatchEvent(new PointerEvent("pointermove", {bubbles: true, pointerId: 41, isPrimary: true, clientX: contactX + 4, clientY: contactY}));
  roleMap.dispatchEvent(new PointerEvent("pointerup", {bubbles: true, pointerId: 41, isPrimary: true, button: 0, clientX: contactX + 4, clientY: contactY}));
  roleMap.setPointerCapture = capture; roleMap.releasePointerCapture = release;
  assert($test("detail-label").textContent === "Current ASM observation" &&
    $test("detail-metrics").textContent.includes("480"),
    "sub-threshold role-map click does not select a positioned contact or show projected speed");
  $test("opz-fire-target").value = "asm-ref";
  $test("opz-fire-target").dispatchEvent(new Event("change", {bubbles: true}));
  await fire("opz-fire-essm", 3);
  exact(commands[3], "opz_launch_essm", {ref: "asm-ref"}, "opz");
  await terminal();
  $test("opz-fire-target").value = "asm-ref";
  $test("opz-fire-target").dispatchEvent(new Event("change", {bubbles: true}));
  await fire("opz-fire-chaff", 4);
  exact(commands[4], "opz_launch_chaff", {ref: "asm-ref"}, "opz");
  await until(() => $test("station-command-status").textContent.includes(__NOT_READY__), "localized terminal reason missing");
  switchRole("helicopter");
  await until(() => !$test("station-helicopter").hidden && !$test("helicopter-fire-target").disabled, "Helicopter release view missing");
  assert($test("opz-fire-target").value === "", "OPZ fire draft survived role switch");
  const heloMap = $test("role-map"), heloRect = heloMap.getBoundingClientRect();
  const emptyX = heloRect.left + heloRect.width * .75, emptyY = heloRect.top + heloRect.height * .75;
  const heloCapture = heloMap.setPointerCapture, heloRelease = heloMap.releasePointerCapture;
  heloMap.setPointerCapture = () => {}; heloMap.releasePointerCapture = () => {};
  for (const [type, x] of [["pointerdown", emptyX], ["pointermove", emptyX + 4], ["pointerup", emptyX + 4]]) {
    heloMap.dispatchEvent(new PointerEvent(type, {bubbles: true, pointerId: 42, isPrimary: true, button: 0, clientX: x, clientY: emptyY}));
  }
  await until(() => commands.length === 6, "empty helicopter-map click did not set waypoint");
  exact(commands[5], "helicopter_set_waypoint", commands[5].params, "helicopter");
  assert(Object.keys(commands[5].params).sort().join(",") === "x,y" &&
    Object.values(commands[5].params).every((value) => Number.isFinite(value) && value >= 0 && value <= 1000),
    "map waypoint coordinates are not finite and bounded");
  await terminal();
  for (const [type, x] of [["pointerdown", emptyX], ["pointermove", emptyX + 6], ["pointerup", emptyX + 6]]) {
    heloMap.dispatchEvent(new PointerEvent(type, {bubbles: true, pointerId: 43, isPrimary: true, button: 0, clientX: x, clientY: emptyY}));
  }
  heloMap.setPointerCapture = heloCapture; heloMap.releasePointerCapture = heloRelease;
  await sleep(80);
  assert(commands.length === 6, "role-map drag above five pixels issued a waypoint");
  switchRole("damage");
  await until(() => !$test("station-damage").hidden && !$test("damage-team").disabled &&
    $test("damage-schematic").width > 1, "actionable damage schematic missing");
  const damageMap = $test("damage-schematic"), damageRect = damageMap.getBoundingClientRect();
  damageMap.dispatchEvent(new MouseEvent("click", {bubbles: true,
    clientX: damageRect.left + damageRect.width * .2, clientY: damageRect.top + damageRect.height * .5}));
  await until(() => commands.length === 7, "damage schematic did not assign selected team");
  exact(commands[6], "damage_assign_team", {team: 1, compartment: "engine"}, "damage");
  await terminal();
  $test("damage-team").value = "2";
  $test("damage-team").dispatchEvent(new Event("change", {bubbles: true}));
  damageMap.dispatchEvent(new MouseEvent("click", {bubbles: true,
    clientX: damageRect.left + damageRect.width * .2, clientY: damageRect.top + damageRect.height * .5}));
  await until(() => commands.length === 8, "damage schematic did not unassign selected team");
  exact(commands[7], "damage_unassign_team", {team: 2, compartment: "engine"}, "damage");
  document.documentElement.dataset.directFire = "passed";
}
window.addEventListener("DOMContentLoaded", () => run().catch((error) => {
  document.documentElement.dataset.directFire = "failed";
  document.documentElement.dataset.failure = String(error.stack || error);
}));
"""


def _direct_fire_browser_states():
    common = dict(protocol=2, version="test", session="fire-world", epoch=2,
                  revision=7, seq=1, phase="live", chart_revision="fire-world",
                  clock=dict(sim=10.0, mission=10.0, time_scale=1.0, world=12.0),
                  environment=dict(sea_state=2, is_night=False),
                  mission=dict(name="Fire test", objective="Observe", remaining_s=500.0))
    navigation = dict(x=250.0, y=250.0, course=0.0, speed=10.0,
                      target_course=0.0, target_speed=10.0, rudder_angle=0.0,
                      yaw_rate=0.0)
    weapon_row = dict(ref="weapon-ref-a", label="Eligible sonar observation",
                      domain="SUBSURFACE", source="SONAR", affiliation="HOSTILE",
                      classification="U_BOOT", bearing=30.0, range_nm=4.0,
                      x=252.0, y=247.0, depth_m=80.0, course=180.0,
                      speed_kn=5.0, quality=.9, age_s=.5, fix_age_s=.5,
                      bearing_uncertainty_deg=1.0, range_uncertainty_nm=.2)
    tactical_row = {key: value for key, value in weapon_row.items()
                    if key not in {"classification", "depth_m", "fix_age_s"}}
    tactical_row.update(observer_x=250.0, observer_y=250.0)
    weapons = dict(common, role="weapons", weapons=dict(
        inventory=dict(torpedoes=4, vls=8, ciws=200, aa=40,
                       chaff_ready=True, nixies=2),
        readiness=dict(station_down=False, roe="FREE", ciws_ready=True,
                       aa_ready=True, state="available", interlock="clear",
                       reload_s=0.0), designated_target=None,
        navigation=navigation, tactical=[], target_choices=[weapon_row], depth_m=90.0,
        tubes=[dict(tube=1, state="ready", reload_s=0.0)], own_weapons=[],
        active_assets=[]))
    asm_row = dict(tactical_row, ref="asm-ref", label="Current ASM observation",
                    domain="AIR", source="RADAR_AIR", bearing=45.0,
                    range_nm=12.0, x=258.0, y=242.0, speed_kn=480.0)
    helicopter_asset = dict(
        state="AUF", airborne=True, x=251.0, y=249.0, course=30.0,
        fuel_s=900.0, torpedoes=1, buoys=2, hovering=False,
        dip_state="STOWED", dip_depth_m=0.0, dip_depth_target_m=20.0,
        dip_water_depth_m=200.0, dip_ping_ready=False, dip_ping_cooldown_s=0.0)
    opz = dict(common, role="opz", opz=dict(
        observations=[asm_row], fusions=[],
        radar=dict(surface=True, air=True, range_nm=40, live=True,
                   sweep_bearing=20.0, sweep_rate_deg_s=180.0, weather_severity=.1,
                   surface_effective_range_nm=35.0, air_effective_range_nm=38.0),
        defense=dict(vls=8, ciws=200, aa=40, chaff_ready=True,
                     ciws_ready=True, aa_ready=True), asm_observations=[asm_row],
        source_classifications=[], designated_target_ref=None,
        own_assets=dict(ship=navigation, helicopter=helicopter_asset)))
    helicopter = dict(common, role="helicopter", helicopter=dict(
        asset=helicopter_asset, waypoint=None, buoys=[], navigation=navigation,
        tactical=[], target_choices=[weapon_row],
        readiness=dict(flightdeck_down=False, deck_state="OK", can_launch=False,
                        can_return=True, can_set_waypoint=True, can_deploy_buoy=True,
                        can_set_dipping=True, can_set_dip_depth=False,
                        can_dipping_ping=False,
                        rtb_margin_s=600.0)))
    damage = dict(common, role="damage", damage=dict(
        compartments=[dict(key="engine", name="Engine", state="BESCHAEDIGT",
                           flood=20.0, fire=10.0, repairable=True,
                           trend=dict(flood_rate=.1, fire_rate=-.2, repairable=True))],
        teams=[dict(team=1, compartment=None), dict(team=2, compartment="engine")],
        total=15.0, sunk=False))
    return {"weapons": weapons, "opz": opz, "helicopter": helicopter,
            "damage": damage}


def test_direct_fire_grants_confirmation_exact_bodies_and_role_switch_in_chromium(tmp_path):
    chromium = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
    if not chromium:
        pytest.skip("Optional direct-fire browser contract: no installed Chromium")
    en, de = catalogs()
    stations = {station: _station_record() for station in STATIONS}
    for station, generation in (("weapons", 1), ("opz", 2),
                                ("helicopter", 3), ("damage", 4)):
        stations[station] = _station_record(
            "mine", station_generation=generation, command=True,
            direct_fire=station in {"opz", "helicopter"})
    session = dict(protocol=2, client_id="fire-client", name="Fire Watch",
                   csrf="fire-csrf", ordinal=0, presence=1.0,
                   next_command_seq=0, station="weapons", requested_station=None,
                   station_generation=1, active_station="weapons",
                   active_generation=1, simlog=False, stations=stations,
                   grants=dict(command=True, direct_fire=False, simlog=False,
                               sonar_audio=False))
    chart = dict(protocol=2, revision="fire-world", size_nm=500.0,
                 landmasses=[], disclaimer="Synthetic test chart")
    html = ASSETS.joinpath("index.html").read_text().replace(
        '<script src="./app.js" defer>',
        '<script src="./direct-fire-test.js" defer></script><script src="./app.js" defer>')
    script = (DIRECT_FIRE_BROWSER.replace("__SESSION__", json.dumps(session))
              .replace("__STATES__", json.dumps(_direct_fire_browser_states()))
              .replace("__CHART__", json.dumps(chart))
              .replace("__REVOKED__", json.dumps(en[PREFIX + "fire_revoked"].split(".")[0]))
              .replace("__NOT_READY__", json.dumps(en[PREFIX + "reason_not_ready"].split(".")[0])))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def reply(self, content, mime="application/json"):
            body = content if isinstance(content, bytes) else content.encode() if isinstance(content, str) else json.dumps(content).encode()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/":
                self.reply(html, "text/html")
            elif self.path == "/direct-fire-test.js":
                self.reply(script, "text/javascript")
            elif self.path in ("/app.js", "/style.css"):
                self.reply(ASSETS.joinpath(self.path[1:]).read_bytes(),
                           "text/javascript" if self.path.endswith("js") else "text/css")
            elif self.path in ("/api/v1/ui?lang=en", "/api/v1/ui?lang=de"):
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
             f"--user-data-dir={tmp_path / 'direct-fire-browser'}",
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
    assert root.get("data-direct-fire") == "passed", root.get(
        "data-failure", result.stdout[-5000:] + result.stderr[-2000:])


def test_v2_lobby_requests_grants_release_reload_and_role_loss_in_real_chromium(tmp_path):
    chromium = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
    if not chromium:
        pytest.skip("Optional browser session contract: no installed Chromium")
    en, de = catalogs()
    legacy = browser_state()
    legacy["chart_revision"] = legacy["session"]

    def tactical_row(row):
        result = {key: row[key] for key in (
            "ref", "label", "domain", "source", "affiliation", "bearing",
            "range_nm", "x", "y", "course", "speed_kn", "quality", "age_s",
            "bearing_uncertainty_deg", "range_uncertainty_nm")}
        result.update(observer_x=legacy["ownship"]["x"],
                      observer_y=legacy["ownship"]["y"])
        return result

    def sonar_row(row):
        result = {key: row[key] for key in (
            "ref", "label", "source", "classification", "bearing", "range_nm",
            "x", "y", "depth_m", "course", "speed_kn", "quality", "age_s",
            "fix_age_s", "bearing_uncertainty_deg", "range_uncertainty_nm",
            "fixes")}
        result.update(observer_x=legacy["ownship"]["x"],
                      observer_y=legacy["ownship"]["y"], released_to_opz=False)
        return result

    def state_for(role):
        common = {key: legacy[key] for key in (
            "version", "session", "epoch", "revision", "seq", "phase",
            "chart_revision", "clock", "environment", "mission")}
        common.update(protocol=2, role=role)
        if role == "bridge":
            common[role] = {"navigation": {key: legacy["ownship"][key] for key in (
                "x", "y", "course", "speed", "target_course", "target_speed")},
                            "tactical_summary": [tactical_row(row)
                                                 for row in legacy["tracks"]]}
            common[role]["navigation"].update(rudder_angle=0.0, yaw_rate=0.0)
            common[role]["orders"] = {"station_down": False, "speed_max_kn": 25,
                                      "telegraph": "HALF", "noise": .2,
                                      "cavitating": False}
            common[role]["threat"] = {"observations": [], "count": 0,
                                       "average_flood": 0.0}
            common[role]["systems"] = [{"key": "bridge", "state": "OK",
                                         "down": False}]
        else:
            common[role] = {"observations": [sonar_row(row)
                                             for row in legacy["tracks"]],
                "settings": {"mode": "BOW", "page": 0, "listen_bearing": 25.0,
                             "focus_ref": None, "target_ref": None,
                             "station_down": False,
                             "tow": {"state": "STOWED", "payout": 0.0,
                                     "available": False, "handling_ok": True,
                                     "depth_m": 20.0, "depth_target_m": 20.0},
                             "bt": {"ready": True, "cooldown_s": 0.0,
                                    "thermocline_m": None},
                             "ping": {"ready": True, "cooldown_s": 0.0},
                             "tma_enabled": False, "gain_db": 0.0,
                             "band_preset": "FULL", "band_hz": [0.0, 300.0],
                             "notch": False, "peak_hold": False,
                             "harmonic_hz": None,
                             "harmonic_candidates_hz": [12.5, 25.0],
                             "audio_enabled": True, "volume": .5,
                              "quiet_mode": False},
                "visualization": {
                    "broadband": {"bearing_start_deg": 0.0,
                                  "bearing_step_deg": 4.0, "history": []},
                    "lofar": {"frequency_min_hz": 0.0,
                              "frequency_max_hz": 300.0,
                              "bin_frequencies_hz": [], "history": [],
                              "spectrum": [], "held": False},
                    "demon": {"frequency_min_hz": 1.0,
                              "frequency_max_hz": 80.0, "bin_step_hz": 1.0,
                              "spectrum": [], "analysis": None},
                    "tma": [], "bt": None, "active_echoes": [],
                    "receiver": {"array": "BOW", "listen_bearing": 25.0,
                                 "beam_width_deg": 30.0, "listen_mode": "RAW",
                                 "focus_locked": False, "audio_enabled": False}}}
        return common
    chart = {"protocol": 2, "revision": legacy["chart_revision"], "size_nm": 500,
             "landmasses": [], "disclaimer": "Synthetic test chart"}
    html = ASSETS.joinpath("index.html").read_text().replace(
        '<script src="./app.js" defer>',
        '<script src="./session-test.js" defer></script><script src="./app.js" defer>')
    script = (BROWSER_SESSION.replace("__STATIONS__", json.dumps(",".join(STATIONS)))
              .replace("__PENDING__", json.dumps(en[PREFIX + "station_requested"]))
              .replace("__FAILED__", json.dumps(en[PREFIX + "station_mutation_failed"].split(".")[0]))
              .replace("__REVOKED__", json.dumps(en[PREFIX + "role_revoked"].split(".")[0]))
              .replace("__BRIDGE__", json.dumps(en[PREFIX + "station_bridge"]))
              .replace("__SONAR__", json.dumps(en[PREFIX + "station_sonar"])))

    class Handler(BaseHTTPRequestHandler):
        session = None
        cookie = "browser-cookie-secret"
        request_polls = 0
        reload_ready = False
        reload_polls = 0

        def log_message(self, *_args):
            pass

        def reply(self, status, value, mime="application/json", cookie=None):
            body = value if isinstance(value, bytes) else value.encode() if isinstance(value, str) else json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Cache-Control", "no-store")
            if cookie:
                self.send_header("Set-Cookie", cookie)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def authenticated(self):
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            return cookie.get("ujagd_remote_v2", {}).value == self.cookie if cookie.get("ujagd_remote_v2") else False

        @classmethod
        def session_body(cls):
            return json.loads(json.dumps(cls.session))

        def do_GET(self):
            if self.path == "/":
                self.reply(200, html, "text/html")
            elif self.path == "/session-test.js":
                self.reply(200, script, "text/javascript")
            elif self.path in ("/app.js", "/style.css"):
                mime = "text/javascript" if self.path.endswith("js") else "text/css"
                self.reply(200, ASSETS.joinpath(self.path[1:]).read_bytes(), mime)
            elif self.path in ("/api/v1/ui?lang=en", "/api/v1/ui?lang=de"):
                source = de if self.path.endswith("de") else en
                self.reply(200, {key: value for key, value in source.items() if key.startswith(PREFIX)})
            elif self.path == "/api/v1/contacts":
                self.reply(200, browser_contact_analysis())
            elif self.path == "/test/reload-ready":
                type(self).reload_ready = True
                type(self).reload_polls = 0
                self.reply(200, {})
            elif self.path == "/api/v2/session" and self.authenticated():
                cls = type(self)
                if cls.reload_ready:
                    cls.reload_polls += 1
                    if cls.reload_polls >= 2:
                        cls.session["stations"]["sonar"] = _station_record()
                        cls.session.update(
                            station=None, active_station=None, requested_station=None,
                            station_generation=0, active_generation=4)
                        cls.session["grants"] = {"command": False, "direct_fire": False,
                                                 "simlog": False, "sonar_audio": False}
                elif cls.session["requested_station"] == "bridge":
                    cls.request_polls += 1
                    if cls.request_polls >= 2:
                        cls.session["stations"]["bridge"] = _station_record(
                            "mine", station_generation=1)
                        cls.session.update(
                            station="bridge", active_station="bridge",
                            active_generation=1, requested_station=None,
                            station_generation=1)
                self.reply(200, cls.session_body())
            elif self.path == "/api/v2/session":
                self.reply(401, {"error": "unauthorized"})
            elif self.path == "/api/v2/state" and self.authenticated():
                legacy["seq"] += 1
                self.reply(200, state_for(type(self).session["station"]))
            elif self.path == "/api/v2/chart" and self.authenticated():
                self.reply(200, chart)
            else:
                self.reply(404, {"error": "not_found"})

        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            body = json.loads(raw) if raw else None
            cls = type(self)
            csrf_ok = self.headers.get("X-U-Jagd-CSRF") == "csrf-1"
            if self.path == "/api/v2/pair" and body == {"code": "123ABC", "name": "Lobby Watch"}:
                cls.session = {"protocol": 2, "client_id": "client-1", "name": "Lobby Watch",
                                "csrf": "csrf-1", "ordinal": 0, "presence": 1.0,
                                "next_command_seq": 0, "active_station": None,
                                "active_generation": 0, "simlog": False,
                                "station": None, "requested_station": None,
                                "station_generation": 0,
                                "grants": {"command": False, "direct_fire": False,
                                           "simlog": False, "sonar_audio": False},
                                "stations": {
                                    station: _station_record(
                                        "occupied" if station == "sonar" else "available")
                                    for station in STATIONS
                                }}
                self.reply(200, cls.session_body(), cookie=f"ujagd_remote_v2={cls.cookie}; Path=/api/v2; HttpOnly; SameSite=Strict")
            elif self.path == "/api/v2/stations/request" and self.authenticated() and csrf_ok and body == {"station": "bridge"}:
                cls.session["requested_station"] = "bridge"
                cls.session["stations"]["bridge"].update(
                    requested=True, request_generation=1)
                self.reply(200, cls.session_body())
            elif self.path == "/api/v2/stations/request" and self.authenticated() and csrf_ok and body == {"station": "damage"}:
                cls.session["stations"]["sonar"] = _station_record(
                    "mine", station_generation=3)
                cls.session.update(
                    station="sonar", active_station="sonar", active_generation=3,
                    requested_station=None, station_generation=3)
                self.reply(503, {"error": "unavailable"})
            elif (self.path == "/api/v2/stations/release" and self.authenticated()
                  and csrf_ok and body == {"station": "bridge", "station_generation": 1,
                                          "active_generation": 1}):
                cls.session["stations"]["bridge"] = _station_record()
                cls.session.update(
                    station=None, active_station=None, active_generation=2,
                    requested_station=None, station_generation=0)
                self.reply(200, cls.session_body())
            else:
                self.reply(404, {"error": "not_found"})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(
            [chromium, "--headless", "--no-sandbox", "--disable-gpu",
             "--disable-background-networking", "--no-first-run",
             "--no-default-browser-check", "--disable-dev-shm-usage",
             f"--user-data-dir={tmp_path / 'browser'}", "--virtual-time-budget=30000", "--dump-dom",
             f"http://127.0.0.1:{server.server_port}/"],
            capture_output=True, text=True, timeout=50,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert result.returncode == 0, result.stderr
    root = next((attrs for tag, attrs in Document(result.stdout).elements if tag == "html"), {})
    assert root.get("data-session-test") == "passed", root.get(
        "data-failure", result.stdout[-4000:] + result.stderr[-2000:])


@pytest.mark.parametrize("width,height", [(1280, 720), (390, 844)])
def test_real_v2_role_states_survive_unpublished_admin_grants_and_presence(
        tmp_path, monkeypatch, width, height):
    chromium = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
    if not chromium:
        pytest.skip("Optional real role browser contract: no installed Chromium")
    en, de = catalogs()
    game = Game(seed=913, start_menu=False, audio_enabled=False, language="en")
    game.sonar.contacts.clear()
    for target_id, bearing in ((99001, 28.0), (99002, 52.0)):
        contact = Contact(target_id - 99000, target_id, "passiv", "sub")
        contact.update_passive(bearing, .8, .8, "hidden", game.sim_t)
        game.sonar.contacts[target_id] = contact
    console = game.commander
    console.port = 0
    console._translations = {
        "en": {key: value for key, value in en.items() if key.startswith(PREFIX)},
        "de": {key: value for key, value in de.items() if key.startswith(PREFIX)},
    }
    console._contact_analysis_assets = {}
    html = ASSETS.joinpath("index.html").read_text().replace(
        '<script src="./app.js" defer>',
        '<script src="./real-role-test.js" defer></script><script src="./app.js" defer>')
    for name, payload in (
        ("index.html", html),
        ("app.js", ASSETS.joinpath("app.js").read_text()),
        ("style.css", ASSETS.joinpath("style.css").read_text()),
    ):
        (tmp_path / name).write_text(payload, encoding="utf-8")
    monkeypatch.setattr(commander_transport.resources, "files", lambda _package: tmp_path)

    # Use the actual F9 owner transition, then start the selected server row while
    # administration remains open. No bridge publication exists when Chromium pairs.
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F9))
    assert game.commander_open and game.administration_open
    console.activate(game)
    assert console.address is not None
    script = REAL_ROLE_SESSION.replace("__CODE__", json.dumps(console.pairing_code))
    (tmp_path / "real-role-test.js").write_text(script, encoding="utf-8")
    # CommanderServer loads its immutable assets at start; add only the test hook
    # to that real server's route table after startup.
    console.server._http.assets["/real-role-test.js"] = (
        "text/javascript; charset=utf-8", script.encode("utf-8"))

    process = subprocess.Popen(
        [chromium, "--headless", "--no-sandbox", "--disable-gpu",
         "--disable-background-networking", "--no-first-run",
         "--no-default-browser-check", "--disable-dev-shm-usage",
             f"--user-data-dir={tmp_path / 'real-browser'}", "--virtual-time-budget=300000",
             f"--window-size={width},{height}",
             f"--screenshot={tmp_path / f'workstation-{width}x{height}.png'}",
         "--dump-dom", f"http://{console.address[0]}:{console.address[1]}/"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    roles = ("bridge", "sonar", "opz", "eloka", "engine", "damage",
             "radio", "helicopter", "weapons")
    role_index = -1
    presence_marks = []
    bridge_live = False
    started = time.monotonic()

    def grant_and_activate(client_id, station):
        assert console.server.grant_station(client_id, station)
        status = next(row for row in console.server.client_statuses()
                      if row["client_id"] == client_id)
        generation = status["stations"][station]["station_generation"]
        assert console.server.activate_station(client_id, station, generation)

    try:
        while process.poll() is None and time.monotonic() - started < 50:
            roster = console.server.client_statuses()
            if roster and role_index < 0:
                grant_and_activate(roster[0]["client_id"], roles[0])
                assert console.server.set_client_grant(
                    roster[0]["client_id"], "command", True)
                role_index = 0
                # Let the assigned browser fetch the server's initial exact
                # status-only cache before the first Game/bridge publication.
                time.sleep(.35)
            if roster and roster[0]["presence"] not in presence_marks:
                presence_marks.append(roster[0]["presence"])
            if role_index >= 0:
                console.pump(game)
            if role_index == 0 and len(presence_marks) >= 3 and not bridge_live:
                assert game.commander_open and console.active_crew
                before = game.sim_t
                game.update(.01)
                assert game.sim_t > before
                assert console.server.set_client_grant(roster[0]["client_id"], "command", True)
                bridge_live = True
            if (role_index == 0 and bridge_live and game.ship.target_course == 123
                    and len(presence_marks) >= 5):
                grant_and_activate(roster[0]["client_id"], roles[1])
                assert console.server.set_client_grant(
                    roster[0]["client_id"], "command", True)
                role_index = 1
                presence_marks.clear()
            elif (role_index == 1 and len(presence_marks) >= 3
                  and all(contact.player_class == "U_BOOT"
                          and contact.released_to_opz
                          for contact in game.sonar.contacts.values())):
                role_index += 1
                grant_and_activate(roster[0]["client_id"], roles[role_index])
                assert console.server.set_client_grant(
                    roster[0]["client_id"], "command", True)
                presence_marks.clear()
            elif (role_index == 2 and len(presence_marks) >= 3
                  and len(game.opz_fusion.fusions) == 1):
                role_index += 1
                grant_and_activate(roster[0]["client_id"], roles[role_index])
                presence_marks.clear()
            elif (3 <= role_index < len(roles) - 1
                  and len(presence_marks) >= 3):
                role_index += 1
                grant_and_activate(roster[0]["client_id"], roles[role_index])
                assert console.server.set_client_grant(
                    roster[0]["client_id"], "command", True)
                presence_marks.clear()
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
    assert root.get("data-real-role-test") == "passed", root.get(
        "data-failure", stdout[-6000:] + stderr[-3000:])
    assert role_index == len(roles) - 1
    assert all(contact.player_class == "U_BOOT"
               for contact in game.sonar.contacts.values())
    assert all(contact.released_to_opz for contact in game.sonar.contacts.values())
    assert len(game.opz_fusion.fusions) == 1
    assert len(presence_marks) >= 3
