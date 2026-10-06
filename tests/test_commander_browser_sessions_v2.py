"""Real-browser contracts for the Protocol-v2 lobby and role shell."""

import json
import shutil
import subprocess
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from commander_web import copy_assets, index_html, inject_probe, page_dataset, WEB_ROUTES
import pygame

from src.commander import server as commander_transport
from src.core.game import Game
from src.sonar.sonar import Contact
from src.core import manual
from test_commander_assets import (ASSETS, PREFIX, Document, browser_contact_analysis,
                                   browser_state, catalogs)
from commander_fixtures import CREW_NOISE, PLOT, WEATHER_STATION



# The bridge lookout's binoculars (clear night, nothing in sight).
# The bridge's autopilot route with no waypoints.
ROUTE = {"pattern": "manual", "index": 0, "total": 0, "points": []}
LOOKOUT = dict(course=90.0, speed_kn=12.0, fov_deg=16.0, visibility_nm=30.0, sea_state=2.0,
               horizon_offset=0.0, horizon_tilt=0.0, motion_pitch=0.0, motion_roll=0.0,
               outlines=[],
               sky=dict(light=0.0, dusk=0.0, cloud=0.25, precipitation="none", intensity=0.0,
                        wind_from_deg=270.0, sun_bearing=300.0, sun_alt_deg=-20.0,
                        moon_bearing=180.0, moon_alt_deg=30.0, moon_illumination=0.8,
                        moon_waxing=True, glow=0.0, storm=0.0, lightning=0.0,
                        lightning_bearing=0.0), events=[])

def _projected(name):
    """A block exactly as the host projects it for a fresh game."""
    from src.commander import projections
    game = Game(seed=3, start_menu=False, audio_enabled=False, language="en")
    return getattr(projections, name)(game)


def _projected_mpa():
    return _projected("_mpa")


def _projected_crew():
    return _projected("_crew")


STATIONS = ("bridge", "sonar", "weapons", "damage", "opz", "radio",
            "engine", "helicopter", "eloka", "uboot", "uboot_sonar",
            "uboot_weapons", "uboot_engine", "uboot_esm", "uboot_nav", "uboot_radio")
# Session records list the phone lookouts after the workstations.
SESSION_ROLES = STATIONS + ("lookout", "uboot_lookout")


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
let tones = 0;
let gameEffects = 0;
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
class TestAudio {
  constructor() { this.state = "suspended"; this.currentTime = 0; this.destination = {}; }
  async resume() { this.state = "running"; }
  async suspend() { this.state = "suspended"; }
  createOscillator() {
    tones++;
    let waveform = "sine";
    return {get type() { return waveform; }, set type(value) { waveform = value; if (value === "square" || value === "triangle") gameEffects++; },
      frequency: {setValueAtTime() {}}, connect() {}, disconnect() {}, start() {}, stop() { setTimeout(() => this.onended?.(), 1); }};
  }
  createGain() { return {gain: {setValueAtTime() {}, linearRampToValueAtTime() {}}, connect() {}, disconnect() {}}; }
}
window.AudioContext = TestAudio;
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
const operational = () => issued.filter((entry) => /\/api\/v2\/(state|chart|proposals|events|simlog)$/.test(entry.url));
async function run() {
  await until(() => !$test("shell").hidden, "translations loaded");
  assert(issued[0].url.endsWith("/api/v2/session"), "resume is the first request");
  if (location.hash !== "#resumed") {
    $test("name").value = "Lobby Watch";
    $test("code").value = "123ABC";
    $test("pair-form").requestSubmit();
    await until(() => $test("pairing").hidden && !$test("simlog-view").hidden,
      "pair preserves the initial unassigned SimLog route");
    const cards = [...$test("station-cards").children];
    assert(cards.length === 16, "lobby has nine frigate and seven submarine station cards");
    assert(cards.map((card) => card.dataset.station).join(",") === __STATIONS__, "canonical station order");
    assert(cards[1].classList.contains("station-occupied") && cards[0].classList.contains("station-available"), "occupancy is rendered");
    assert(operational().length === 0, "unassigned client fetches no operational state");
    await sleep(1100);
    assert(location.hash === "#simlog" && !$test("simlog-view").hidden && $test("lobby").hidden && $test("operations").hidden,
      "unassigned SimLog route remains stable across session polling");
    const simlogBounds = $test("simlog-view").getBoundingClientRect();
    assert(simlogBounds.width > 0 && simlogBounds.height > 0 && simlogBounds.bottom <= innerHeight + 1,
      "unassigned SimLog route is laid out inside the viewport");
    assert($test("simlog-status").textContent.includes(__SIMLOG_STATION__),
      "unassigned SimLog route explains its station requirement");
    assert(operational().length === 0, "unassigned SimLog route fetches no operational data");
    location.hash = "";
    await until(() => !$test("lobby").hidden, "leaving SimLog returns to station selection");
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
    assert($test("target-proposal").hidden && !$test("navigation-proposal").hidden,
      "bridge sees only navigation proposals");
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
    await until(() => !$test("simlog-view").hidden, "assigned SimLog route becomes visible");
    await sleep(1100);
    assert(!$test("simlog-view").hidden && $test("operations").hidden,
      "assigned SimLog route remains stable across session polling");
    assert($test("simlog-status").textContent.includes(__SIMLOG_GRANT__),
      "SimLog route explains its missing host grant");
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
  await until(() => !$test("target-proposal").hidden && $test("navigation-proposal").hidden &&
    $test("proposal-status").textContent.includes("Sierra 01"), "sonar sees only its target proposal");
  await until(() => $test("event-list").textContent.includes("Baseline warning"), "event baseline rendered");
  $test("sound").click();
  await until(() => $test("sound").getAttribute("aria-pressed") === "true", "sound enabled");
  assert(tones === 0, "enabling sound must not start ambient audio");
  await nativeFetch("/test/new-warning");
  await until(() => $test("event-list").textContent.includes("New warning") && tones === 1,
    "a subsequent warning is rendered and alerted once");
  await nativeFetch("/test/new-sound");
  await until(() => gameEffects === 1, "a new game sound is synthesized once");
  await sleep(350);
  assert(gameEffects === 1, "game sound sequences are deduplicated");
  await nativeFetch("/test/allow-role-loss");
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
  if (["protocol", "chart", "session", "proposals", "events", "results", "simlog_schema"].includes(String(args[0]))) protocolErrors.push(error.stack || String(error));
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
  "engine-instruments", "eloka-scope", "radio-df-scope", "weapons-system", "helicopter-lofar-canvas",
  "helicopter-broadband-canvas", "helicopter-demon-canvas", "helicopter-dip-canvas"]);
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
  if (/\/api\/v2\/(session|state|chart|proposals|events|results)$/.test(path) && response.ok) {
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
    } else if (path.endsWith("/results")) {
      resultPolls += 1;
      events.push(`results:${JSON.stringify(value)}`);
    }
  }
  return response;
};
// A pushed state stands in for a /state request: log it the same way.
const NativeSocket = window.WebSocket;
window.WebSocket = function(url, protocol) {
  const socket = new NativeSocket(url, protocol);
  if (String(url).endsWith("/ws/v2/state")) socket.addEventListener("message", ({data}) => {
    try { const value = JSON.parse(data); latestRole = value.role; events.push(`state:${value.role}`); } catch (_) {}
  });
  return socket;
};
window.WebSocket.prototype = NativeSocket.prototype;
Object.assign(window.WebSocket, {CONNECTING: 0, OPEN: 1, CLOSING: 2, CLOSED: 3});
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const assert = (value, message) => { if (!value) throw new NativeError(message); };
async function until(check, message) {
  for (let index = 0; index < 1500; index++) {
    if (check()) return;
    await sleep(20);
  }
  throw new NativeError(typeof message === "function" ? message() : message);
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
  let tasReasonChecked = false;
  const clearedCanvases = new Set();
  let previousRole = null;
  const visualFor = {bridge: "role-map", sonar: "sonar-broadband", opz: "role-map",
    eloka: "eloka-scope", engine: "engine-instruments", damage: "damage-schematic",
    radio: "radio-df-scope", helicopter: "helicopter-lofar-canvas", weapons: "weapons-system"};
  const equivalentFor = {bridge: "role-map-text", sonar: "sonar-broadband-text", opz: "role-map-text",
    eloka: "eloka-scope-text", engine: "engine-instruments-text", damage: "damage-schematic-text",
    radio: "radio-df-scope-text", helicopter: "helicopter-acoustic-text", weapons: "weapons-system-text"};
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
      const trackRoles = new Set(["bridge", "sonar", "weapons", "opz", "helicopter", "eloka"]);
      const grid = document.getElementById("cic-grid");
      if (innerWidth >= 1000) {
        assert(visualBounds.width >= innerWidth * .45, `instrument too narrow: ${latestRole}`);
        assert(visualBounds.top < innerHeight * .5, `instrument below fold: ${latestRole}`);
        assert(controlBounds.left >= visualBounds.right - 2, `controls not beside instrument: ${latestRole}`);
        if (trackRoles.has(latestRole)) {
          // CIC layout: contacts dock | full-height instrument | station dock,
          // with the contact detail dock under (or, from 2400 px, beside) it.
          const contactsBounds = document.getElementById("dock-left").getBoundingClientRect();
          const detailsBounds = document.getElementById("dock-detail").getBoundingClientRect();
          const dockBounds = document.getElementById("dock-right").getBoundingClientRect();
          const gridBox = grid.getBoundingClientRect();
          assert(grid.dataset.tracks === "true" && contactsBounds.right <= visualBounds.left + 2,
            `contacts are not left of the instrument: ${latestRole}`);
          assert(detailsBounds.left >= visualBounds.right - 2 &&
            (detailsBounds.top >= dockBounds.bottom - 2 || detailsBounds.left >= dockBounds.right - 2),
            `contact detail is not beside the instrument next to the controls: ${latestRole}`);
          assert(detailsBounds.bottom <= gridBox.bottom + 1 && contactsBounds.bottom <= gridBox.bottom + 1,
            `track panels exceed station: ${latestRole}`);
          assert(document.documentElement.scrollHeight <= innerHeight + 1,
            `page scrolls instead of fitting one viewport: ${latestRole}`);
        }
      }
      const stationBounds = grid.getBoundingClientRect();
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
      assert(cards.every((card) => {
        const bounds = card.getBoundingClientRect();
        return [...card.children].filter((element) => !element.hidden && getComputedStyle(element).display !== "none")
          .every((element) => {
            const child = element.getBoundingClientRect();
            return child.top >= bounds.top - 1 && child.bottom <= bounds.bottom + 1;
          });
      }), `control content exceeds its card: ${latestRole}`);
      assert(cardBounds.every((first, index) => cardBounds.slice(index + 1).every((second) =>
        Math.min(first.right, second.right) - Math.max(first.left, second.left) <= 1 ||
        Math.min(first.bottom, second.bottom) - Math.max(first.top, second.top) <= 1)),
        `control cards overlap: ${latestRole}`);
      const populated = cards.flatMap((card) => [...card.querySelectorAll(".detail-metrics, .station-list")])
        .filter((element) => element.children.length && !element.hidden && getComputedStyle(element).display !== "none");
      assert(populated.every((element) => element.getClientRects().length && element.getBoundingClientRect().height > 0),
        `station values hidden: ${latestRole}`);
      const textOverflow = [...station.querySelectorAll("h2, h3, h4, p, dt, dd, label, button, summary, output")]
        .filter((element) => !element.hidden && getComputedStyle(element).display !== "none" && element.clientWidth > 1)
        .filter((element) => element.scrollWidth > element.clientWidth + 2)
        .map((element) => `${element.tagName.toLowerCase()}#${element.id}.${element.className}`);
      assert(!textOverflow.length, `station text overflows horizontally: ${latestRole} ${textOverflow.join(",")}`);
      const unexplained = [...station.querySelectorAll("button:disabled")]
        .filter((button) => !button.hidden && getComputedStyle(button).display !== "none" && !button.title);
      assert(unexplained.length === 0, `disabled controls lack reasons: ${latestRole} / ${unexplained.map((button) => button.id || button.textContent).join(",")}`);
      layoutChecked.add(latestRole);
      assert(["lookout", "guide", "contacts"].every((name) => document.getElementById(`tab-${name}`).hidden), "legacy tabs still visible");
      const canvas = document.getElementById(visualFor[latestRole]);
      const equivalent = document.getElementById(equivalentFor[latestRole]);
      if (innerWidth >= 1000 && visualFor[latestRole] === "role-map") {
        for (let attempt = 0; attempt < 10 && canvas.getBoundingClientRect().height < 120; attempt++)
          await sleep(20);
        assert(canvas.getBoundingClientRect().height >= 120,
          `role map is not large enough: ${latestRole} ${canvas.getBoundingClientRect().height}px / frame ${canvas.parentElement.getBoundingClientRect().height}px`);
      }
      if (canvas.width > 1 && canvas.height > 1 && equivalent.textContent.trim() && visualDraws.has(canvas.id) &&
          !document.getElementById("role-visuals").hidden) visualRendered.add(latestRole);
      if (previousRole && previousRole !== latestRole) {
        const previousCanvas = visualFor[previousRole];
        if (previousCanvas !== "role-map" && document.getElementById(previousCanvas).width === 1)
          clearedCanvases.add(previousRole);
      }
      previousRole = latestRole;
      if (latestRole === "sonar") {
        assert(!document.querySelector('[data-station-action="sonar_set_release"]'),
          "Sonar has a duplicate CIC release button outside contact detail");
        assert(document.querySelectorAll("#sonar-release").length === 1,
          "Sonar contact detail must own one CIC release button");
        const tas = document.getElementById("sonar-tas");
        const explain = document.getElementById("disabled-control-explain");
        if (tas.disabled && tas.title.includes("12") && tas.dataset.disabledReason === tas.title && !explain.hidden) {
          explain.click();
          tasReasonChecked = document.getElementById("disabled-control-help").textContent.includes(tas.title);
        }
        const bearingSubmit = document.getElementById("sonar-bearing-submit");
        if (!stationActions.includes("sonar_set_listen_bearing") && !bearingSubmit.disabled) {
          document.getElementById("sonar-tab-broadband").click();
          await sleep(25);
          const broadband = document.getElementById("sonar-broadband");
          const bounds = broadband.getBoundingClientRect();
          const scale = bounds.width / broadband.clientWidth;
          const tapX = bounds.left + (46 + (broadband.clientWidth - 64) * .25) * scale;
          const tapY = bounds.top + bounds.height / 2;
          // Pointer Events, not a synthetic click - matches the real
          // pointerdown/pointerup tap-vs-drag handling the control uses.
          const capture = broadband.setPointerCapture, release = broadband.releasePointerCapture;
          broadband.setPointerCapture = () => {}; broadband.releasePointerCapture = () => {};
          for (const type of ["pointerdown", "pointerup"]) broadband.dispatchEvent(new PointerEvent(type, {
            bubbles: true, pointerId: 51, isPrimary: true, button: 0, clientX: tapX, clientY: tapY,
          }));
          broadband.setPointerCapture = capture; broadband.releasePointerCapture = release;
        }
        // "overview" is a layout mode showing several pages at once, not a page.
        const overview = document.querySelector('[data-sonar-visual="overview"]');
        if (!overview) throw new NativeError("sonar overview tab missing");
        overview.click();
        await sleep(25);
        const shown = [...document.querySelectorAll("[data-sonar-plot]")].filter((panel) => !panel.hidden);
        // The host may move the role on during the wait; judge sonar only.
        if (latestRole === "sonar" && !document.getElementById("sonar-visual").hidden && shown.length < 4)
          throw new NativeError(`sonar overview shows ${shown.length} plots`);
        const tabs = [...document.querySelectorAll("[data-sonar-visual]")]
          .filter((button) => button.dataset.sonarVisual !== "overview");
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
      if (latestRole === "helicopter") {
        // The layout settles after the role switch; wait like the other plots.
        // At 1280x720 the plots are about 200 px; Chrome's font metrics on
        // the CI runner leave them a pixel short, so allow a small margin.
        await until(() => canvas.getBoundingClientRect().height >= 190,
          () => `Helicopter LOFAR view is too small: ${canvas.getBoundingClientRect().height}px`);
        for (const plot of ["broadband", "demon"]) {
          document.querySelector(`[data-helicopter-plot-tab="${plot}"]`).click();
          const plotCanvas = document.getElementById(`helicopter-${plot}-canvas`);
          await until(() => plotCanvas.getBoundingClientRect().height >= 190 &&
            visualDraws.has(plotCanvas.id),
            `Helicopter ${plot} view is too small or not drawn: ${plotCanvas.getBoundingClientRect().height}px, drawn=${visualDraws.has(plotCanvas.id)}`);
        }
        document.querySelector('[data-helicopter-plot-tab="lofar"]').click();
        document.getElementById("helicopter-visual-dip").click();
        const dipCanvas = document.getElementById("helicopter-dip-canvas");
        await until(() => dipCanvas.getBoundingClientRect().height >= 300 &&
          dipCanvas.getBoundingClientRect().width >= 300 && visualDraws.has(dipCanvas.id),
          () => `Helicopter dipping sonar picture is too small or not drawn: ${dipCanvas.getBoundingClientRect().width}x${dipCanvas.getBoundingClientRect().height}px, drawn=${visualDraws.has(dipCanvas.id)}`);
        document.getElementById("helicopter-visual-map").click();
        for (let attempt = 0; attempt < 20 && document.getElementById("role-map").getBoundingClientRect().height < 120; attempt++)
          await sleep(20);
        const heliMap = document.getElementById("role-map");
        assert(heliMap.getBoundingClientRect().height >= 120,
          `Helicopter tactical map is too small after switching views: ${heliMap.getBoundingClientRect().height}px, panel ${heliMap.closest("#map-visual").getBoundingClientRect().height}px, hidden=${heliMap.closest("#map-visual").hidden}`);
        document.getElementById("helicopter-visual-acoustic").click();
        assert(!document.getElementById("classification-form").hidden,
          "Dipping-sonar classification is hidden in contact detail");
        assert(!document.querySelector('[data-station-action="sonar_set_release"]'),
          "Helicopter has a duplicate CIC release button");
      }
      if (latestRole === "eloka") {
        const intercepts = document.getElementById("eloka-intercepts");
        assert(getComputedStyle(intercepts.closest(".station-card-view")).display !== "none",
          "ESM annotation controls are hidden in the workstation");
      }
      // Tell the host which roles are fully checked, so it moves on only then.
      document.documentElement.dataset.rolesDone =
        [...layoutChecked].filter((role) => visualRendered.has(role)).join(",");
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
      const release = document.getElementById("sonar-release");
      if (release.disabled) { await sleep(20); continue; }
      const contacts = document.getElementById("track-list").querySelectorAll("button");
      contacts[sonarReleases]?.click();
      await until(() => stationActions.filter((action) => action === "sonar_set_focus").length >= 3 + sonarReleases,
        () => `Sonar focus did not follow release-contact selection: ${stationActions.join(",")}`);
      await until(() => !release.disabled, "Sonar release stayed disabled after focus");
      release.click();
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
  assert(tasReasonChecked, "TAS speed lock has no specific localized explanation");
  assert(["sonar", "eloka", "engine", "damage"].every((role) => clearedCanvases.has(role)),
    `role-switch canvas clearing missing: ${[...clearedCanvases].join(",")}`);
  assert(resultPolls > 0, `result polling missing: ${events.join(",")}`);
  assert(stationActions.filter((action) => action === "sonar_classify").length === 2,
    `Sonar classifications missing: ${stationActions.join(",")}`);
  assert(stationActions.filter((action) => action === "sonar_set_release").length === 2,
    `Sonar releases missing: ${stationActions.join(",")}`);
  assert(stationActions.filter((action) => action === "sonar_set_listen_bearing").length === 1,
    `Broadband bearing click missing: ${stationActions.join(",")}`);
  assert(stationActions.filter((action) => action === "sonar_set_focus").length === 4,
    `Sonar track selection did not follow the listening focus: ${stationActions.join(",")}`);
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
const stationActivations = [];
let backgroundStarts = 0;
let backgroundStops = 0;
class TestAudio {
  constructor() { this.state = "suspended"; this.currentTime = 0; this.sampleRate = 8000; this.destination = {}; }
  async resume() { this.state = "running"; }
  async suspend() { this.state = "suspended"; }
  createBuffer(_channels, frames) { const data = new Float32Array(frames); return {getChannelData: () => data}; }
  createBufferSource() {
    return {loop: false, connect() {}, disconnect() {}, start() { backgroundStarts++; },
      stop() { backgroundStops++; }, onended: null};
  }
  createGain() { return {gain: {value: 0, setValueAtTime() {}, linearRampToValueAtTime() {}}, connect() {}, disconnect() {}}; }
  createOscillator() { return {frequency: {setValueAtTime() {}}, connect() {}, disconnect() {}, start() {}, stop() {}}; }
}
window.AudioContext = TestAudio;
let roleMapLeftLabels = 0;
let roleMapSweepEndpoint = null;
let roleMapShipOrigin = null;
let roleMapSweepOrigin = null;
const nativeFillText = CanvasRenderingContext2D.prototype.fillText;
const nativeLineTo = CanvasRenderingContext2D.prototype.lineTo;
const nativeMoveTo = CanvasRenderingContext2D.prototype.moveTo;
const nativeTranslate = CanvasRenderingContext2D.prototype.translate;
CanvasRenderingContext2D.prototype.translate = function(x, y) {
  if (this.canvas.id === "role-map") roleMapShipOrigin = {x, y};
  return nativeTranslate.call(this, x, y);
};
CanvasRenderingContext2D.prototype.moveTo = function(x, y) {
  if (this.canvas.id === "role-map-sweep") roleMapSweepOrigin = {x, y};
  return nativeMoveTo.call(this, x, y);
};
CanvasRenderingContext2D.prototype.lineTo = function(x, y) {
  if (this.canvas.id === "role-map-sweep") roleMapSweepEndpoint = {x, y};
  return nativeLineTo.call(this, x, y);
};
CanvasRenderingContext2D.prototype.fillText = function(text, x, y, ...rest) {
  if (this.canvas.id === "role-map" && /^\d+$/.test(text) && x <= 4) {
    assert(this.textAlign === "left", "left map coordinate is not left aligned");
    const bounds = this.measureText(text);
    assert(x >= 0 && x + bounds.width <= this.canvas.clientWidth && y >= 0 && y <= this.canvas.clientHeight,
      "left map coordinate is clipped");
    roleMapLeftLabels++;
  }
  return nativeFillText.call(this, text, x, y, ...rest);
};
let results = [];
let failNext = false;
let currentRef = "weapon-ref-a";
const browserErrors = [];
window.addEventListener("error", (event) => browserErrors.push(event.message));
window.addEventListener("unhandledrejection", (event) => browserErrors.push(String(event.reason)));
const nativeConsoleError = console.error.bind(console);
console.error = (...args) => { browserErrors.push(args.map((item) => item?.stack || String(item)).join(" ")); nativeConsoleError(...args); };
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
  if (path === "/api/v2/ui") return nativeFetch(url, options);
  if (path === "/api/v2/contacts") return new Response(JSON.stringify({version: 1, profiles: []}), {status: 200});
  if (path === "/api/v2/pair") return new Response(JSON.stringify(session), {status: 200});
  if (path === "/api/v2/state") return new Response(JSON.stringify(state()), {status: 200});
  if (path === "/api/v2/chart") return new Response(JSON.stringify(chart), {status: 200});
  if (path === "/api/v2/proposals") {
    const current = state();
    return new Response(JSON.stringify({protocol: 2, session: current.session, epoch: current.epoch,
      role: current.role, target: null, navigation: null}), {status: 200});
  }
  if (path === "/api/v2/events") {
    const current = state();
    return new Response(JSON.stringify({protocol: 2, session: current.session, epoch: current.epoch,
      role: current.role, latest_seq: 0, events: []}), {status: 200});
  }
  if (path === "/api/v2/stations/activate") {
    const body = JSON.parse(options.body);
    stationActivations.push(body);
    await sleep(100);
    if (body.station_generation !== session.stations[body.station]?.station_generation) {
      return new Response("", {status: 409});
    }
    switchRole(body.station);
    return new Response(JSON.stringify(session), {status: 200});
  }
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
// A canvas whose backing store matches its current layout box (the page's
// resizeCanvas() rule): reading clientWidth/clientHeight forces layout now,
// while the redraw for a layout change waits for a ResizeObserver callback,
// which runs only in a rendering step. Under --virtual-time-budget, on a
// loaded host, timers can race far ahead of rendering steps, so a canvas
// could look "settled" for 80 ms and still owe that redraw (CI: "OPZ sweep
// continues after the mission ended" with the sweep layer 6-33 px shorter
// after the redraw).
function canvasCaughtUp(canvas) {
  const width = canvas.clientWidth, height = canvas.clientHeight;
  const dpr = Math.min(Math.min(window.devicePixelRatio || 1, 3), Math.sqrt(8000000 / Math.max(1, width * height)));
  return canvas.width === Math.max(1, Math.round(width * dpr)) &&
    canvas.height === Math.max(1, Math.round(height * dpr));
}
// The overlay may still be redrawn once after a state change (a layout or
// resize pass); wait until it has caught up with its layout and two samples
// 80 ms apart agree, then return it.
async function settledFrame(canvas) {
  let previous = null;
  for (let index = 0; index < 40; index++) {
    const frame = canvasCaughtUp(canvas) ? canvas.toDataURL() : null;
    if (frame !== null && frame === previous) return frame;
    previous = frame;
    await sleep(80);
  }
  return canvas.toDataURL();
}
// A still overlay is unchanged 120 ms later. A layout change in between is a
// resize redraw, not motion: settle again and compare at the new size.
async function stillAfter(canvas) {
  for (let attempt = 0; attempt < 5; attempt++) {
    const frame = await settledFrame(canvas);
    const size = `${canvas.clientWidth}x${canvas.clientHeight}`;
    await sleep(120);
    if (`${canvas.clientWidth}x${canvas.clientHeight}` !== size || !canvasCaughtUp(canvas)) continue;
    return canvas.toDataURL() === frame;
  }
  return false;
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
  assert($test("fire-confirm-dialog").open, `${id} did not open the confirmation dialog`);
  $test("fire-confirm-confirm").click();
  await until(() => commands.length === expectedCount + 1, `${id} did not send after confirmation`);
}
async function terminal() {
  await until(() => !$test("station-command-status").textContent.includes("Pending") &&
    !$test("station-command-status").textContent.includes("Ausstehend") &&
    $test("station-command-status").textContent, "terminal result missing");
}
async function selectStation(id, role) {
  const previousGeneration = session.active_generation;
  if (id === "mobile-station") {
    const select = $test(id);
    select.value = role;
    select.dispatchEvent(new Event("change", {bubbles: true}));
  } else {
    $test(`station-tab-${role}`).click();  // the desktop switcher is the station tab bar
  }
  assert($test(`station-tab-${role}`).getAttribute("aria-selected") === "true" && $test("mobile-station").value === role,
    `${id} did not retain the requested station while activation was pending`);
  await until(() => session.station === role && !$test(`station-${role}`).hidden,
    `${id} did not activate ${role}`);
  const activation = stationActivations.at(-1);
  assert(JSON.stringify(activation) === JSON.stringify({station: role,
    station_generation: session.stations[role].station_generation,
    active_generation: previousGeneration}), `${id} activation envelope`);
}
async function run() {
  await until(() => !$test("shell").hidden, "translations missing");
  await until(() => !$test("station-weapons").hidden, "Weapons role missing");
  const stableTab = $test("station-tab-weapons");
  await sleep(1200);
  assert($test("station-tab-weapons") === stableTab,
    "station polling rebuilt the station tab bar");
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
  await selectStation("station-tabs", "opz");
  await until(() => !$test("station-opz").hidden && $test("station-weapons").hidden, "wrong-role controls survived role switch");
  assert($test("weapons-fire-target").value === "" && $test("weapons-fire-depth").value === "", "Weapons fire draft survived role switch");
  const roleMap = $test("role-map"), sweepLayer = $test("role-map-sweep"), mapRect = roleMap.getBoundingClientRect();
  await until(() => roleMap.width > 1 && mapRect.width > 100, "OPZ role map missing");
  await until(() => sweepLayer.width > 1 && roleMapSweepEndpoint, "OPZ sweep overlay missing");
  const sweepFrame = sweepLayer.toDataURL();
  await until(() => sweepLayer.toDataURL() !== sweepFrame, "published OPZ sweep does not animate between samples");
  const edge = roleMapSweepEndpoint;
  const sweepLength = Math.hypot(edge.x - roleMapSweepOrigin.x, edge.y - roleMapSweepOrigin.y);
  // Default OPZ zoom fits the selected radar range to the shorter map dimension
  // (viewState.zoom = chart.size_nm / (2 * range_nm)). The beam reaches the
  // longest *effective* radar range (38 of 40 NM in this fixture, weather),
  // regardless of bearing, never the canvas edge itself.
  const expectedSweepLength = Math.min(sweepLayer.clientWidth, sweepLayer.clientHeight) / 2 * 38 / 40;
  assert(Math.abs(sweepLength - expectedSweepLength) < 3,
    `OPZ sweep length ${sweepLength} does not match the radar range (expected ~${expectedSweepLength})`);
  const sweepRect = sweepLayer.getBoundingClientRect();
  assert(roleMapShipOrigin && roleMapSweepOrigin &&
    Math.abs(mapRect.left + roleMapShipOrigin.x - sweepRect.left - roleMapSweepOrigin.x) < 2 &&
    Math.abs(mapRect.top + roleMapShipOrigin.y - sweepRect.top - roleMapSweepOrigin.y) < 2,
    `OPZ sweep does not start at the ship: ship=${JSON.stringify(roleMapShipOrigin)} sweep=${JSON.stringify(roleMapSweepOrigin)} map=${JSON.stringify(mapRect)} layer=${JSON.stringify(sweepRect)}`);
  let baseRedraws = 0;
  const baseObserver = new MutationObserver(() => { baseRedraws++; });
  baseObserver.observe($test("role-map-text"), {childList: true});
  await sleep(120);
  baseObserver.disconnect();
  assert(baseRedraws <= 1, "OPZ redraws the whole map on every sweep frame");
  // Ping rings and splashes animate on the same layer while they spread;
  // clear them so only the sweep itself is compared below.
  states.opz.plot = {...states.opz.plot, fx: {pings: [], echoes: [], splashes: []}};
  states.opz.phase = "ended";
  await until(() => $test("role-visual-state").textContent.includes("inactive") ||
    $test("role-visual-state").textContent.includes("inaktiv"), "ended OPZ state missing");
  assert(await stillAfter(sweepLayer), "OPZ sweep continues after the mission ended");
  states.opz.phase = "live";
  await until(() => !$test("opz-fire-target").disabled, "OPZ did not resume");
  states.opz.opz.radar.surface = false; states.opz.opz.radar.air = false;
  await until(() => !$test("opz-radar-surface").checked && !$test("opz-radar-air").checked,
    "radars-off state missing");
  assert(await stillAfter(sweepLayer), "OPZ sweep continues with both radars off");
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
  await selectStation("mobile-station", "helicopter");
  await until(() => !$test("station-helicopter").hidden && !$test("helicopter-fire-target").disabled, "Helicopter release view missing");
  assert(!$test("helicopter-buoy-console").hidden && $test("helicopter-dip-display").hidden,
    "Helicopter acoustic analysis is not the primary workstation view");
  // The dipping-sonar picture and the tactical map are pages of their own;
  // Page Down steps from the acoustic page to the dipping sonar, then the map.
  document.dispatchEvent(new KeyboardEvent("keydown", {key: "PageDown", bubbles: true}));
  const dipDisplay = $test("helicopter-dip-display");
  const dipRect = dipDisplay.getBoundingClientRect();
  assert(!dipDisplay.hidden && dipDisplay.parentElement === $test("role-visuals") &&
    dipRect.width > 100 && dipRect.height > 100 && $test("map-visual").hidden &&
    $test("helicopter-visual-dip").getAttribute("aria-selected") === "true",
    "Page Down does not open the dipping sonar page on its own");
  $test("helicopter-visual-next").click();
  assert(dipDisplay.hidden && !$test("map-visual").hidden &&
    $test("helicopter-visual-map").getAttribute("aria-selected") === "true",
    "The page key chip does not step from the dipping sonar to the map");
  await until(() => $test("role-map-follow").textContent.includes("helicopter") ||
    $test("role-map-follow").textContent.includes("Hubschrauber"),
    "Helicopter map does not identify its follow target");
  const buoyNames = [...$test("helicopter-buoys").querySelectorAll("h4")].map((item) => item.textContent);
  assert(JSON.stringify(buoyNames) === JSON.stringify(["SB01", "SB02"]),
    `Sonobuoy names are not short and sequential: ${buoyNames.join(",")}`);
  assert(!$test("helicopter-buoys").textContent.includes("opaque-buoy"),
    "opaque Sonobuoy reference is visible");
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
  await selectStation("station-tabs", "damage");
  await until(() => !$test("station-damage").hidden && !$test("damage-team").disabled &&
    $test("damage-schematic").width > 1, "actionable damage schematic missing");
  assert($test("helicopter-dip-display").hidden, "Helicopter sonar remains visible at another station");
  const damageMap = $test("damage-schematic");
  // The plan can resize once a result arrives (the text equivalent below
  // wraps), so each click aims at the canvas where it is now.
  const clickDamagePlan = () => {
    const rect = damageMap.getBoundingClientRect();
    const engine = JSON.parse(damageMap.dataset.hits || "[]").find((hit) => hit.key === "engine");
    assert(engine, "damage profile has no engine room");
    damageMap.dispatchEvent(new MouseEvent("click", {bubbles: true,
      clientX: rect.left + engine.x + engine.width / 2, clientY: rect.top + engine.y + engine.height / 2}));
  };
  clickDamagePlan();
  await until(() => commands.length === 7, "damage schematic did not assign selected team");
  exact(commands[6], "damage_assign_team", {team: 1, compartment: "engine"}, "damage");
  await terminal();
  $test("damage-team").value = "2";
  $test("damage-team").dispatchEvent(new Event("change", {bubbles: true}));
  clickDamagePlan();
  await until(() => commands.length === 8, "damage schematic did not unassign selected team");
  exact(commands[7], "damage_unassign_team", {team: 2, compartment: "engine"}, "damage");
  states.bridge.bridge.orders.cavitating = true;
  await selectStation("mobile-station", "bridge");
  $test("sound").click();
  await until(() => $test("sound").getAttribute("aria-pressed") === "true", "sound did not enable");
  await sleep(1200);
  assert(backgroundStarts === 0 && backgroundStops === 0,
    "sound opt-in or repeated Bridge snapshots started background audio");
  states.bridge.bridge.orders.cavitating = false;
  await sleep(100);
  states.bridge.bridge.orders.cavitating = true;
  await sleep(100);
  $test("volume").value = "0";
  $test("volume").dispatchEvent(new Event("input", {bubbles: true}));
  $test("volume").value = "50";
  $test("volume").dispatchEvent(new Event("input", {bubbles: true}));
  await selectStation("station-tabs", "damage");
  assert(backgroundStarts === 0 && backgroundStops === 0,
    "state, volume, or role changes started background audio");
  assert(roleMapLeftLabels > 0, "left role-map coordinates were not drawn");
  assert(stationActivations.length === 5, "station selectors did not issue exactly one activation each");
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
                   clock=dict(sim=10.0, mission=10.0, world=12.0),
                   environment=dict(sea_state=2, effective_sea_state=2.4,
                                    is_night=False, weather="clear",
                                    wind_from_deg=245.0, wind_speed_kn=12.0,
                                    rain_intensity=.1, visibility_nm=24.0, storm=0.0),
                   mission=dict(name="Fire test", objective="Observe", remaining_s=500.0),
                   autocrew=dict(enabled=False, status="off"), autocrew_overview=[],
                   audio=dict(events=[], callouts=[]), weather_station=WEATHER_STATION, plot=PLOT,
                   alarms=[], hit_view=None, crew_noise=CREW_NOISE, lamp_tips={})
    navigation = dict(x=250.0, y=250.0, course=0.0, speed=10.0,
                      target_course=0.0, target_speed=10.0, rudder_angle=0.0,
                      yaw_rate=0.0, turn_radius_nm=None)
    weapon_row = dict(ref="weapon-ref-a", label="Eligible sonar observation",
                      domain="SUBSURFACE", source="SONAR", affiliation="HOSTILE",
                      classification="U_BOOT", bearing=30.0, range_nm=4.0,
                      x=252.0, y=247.0, depth_m=80.0, course=180.0,
                      speed_kn=5.0, quality=.9, age_s=.5, fix_age_s=.5,
                      bearing_uncertainty_deg=1.0, range_uncertainty_nm=.2)
    tactical_row = {key: value for key, value in weapon_row.items()
                    if key not in {"classification", "depth_m", "fix_age_s"}}
    tactical_row.update(observer_x=250.0, observer_y=250.0, altitude_m=None,
                       visual_class=None, visual_type=None)
    weapons = dict(common, role="weapons", weapons=dict(
        inventory=dict(torpedoes=4, vls=8, ciws=200, aa=40,
                       chaff_ready=True, nixies=2, asroc=4, depth_charges=20, rbu=36),
        readiness=dict(station_down=False, roe="FREE", ciws_ready=True,
                       rbu_ready=True, torpedo_warning=False,
                       aa_ready=True, state="available", interlock="clear", stage="fire",
                       reload_s=0.0), designated_target=None,
        navigation=navigation, tactical=[], target_choices=[weapon_row], depth_m=90.0,
        tubes=[dict(tube=1, state="ready", reload_s=0.0)], own_weapons=[],
        active_assets=[],
        settings=dict(torpedo_type="frigate_torp", pattern="snake", enable_nm=1.0, salvo=1,
                      choices=[dict(key="frigate_torp", name="Mk1", stock=4, loaded=2)])))
    asm_row = dict(tactical_row, ref="asm-ref", label="Current ASM observation",
                    domain="AIR", source="RADAR_AIR", bearing=45.0,
                    range_nm=12.0, x=258.0, y=242.0, speed_kn=480.0)
    helicopter_asset = dict(
        state="AUF", airborne=True, x=251.0, y=249.0, course=30.0,
        fuel_s=900.0, torpedoes=1, buoys=2, hovering=False,
        dip_state="STOWED", dip_depth_m=0.0, dip_depth_target_m=20.0,
        dip_water_depth_m=200.0, dip_ping_ready=False, dip_ping_cooldown_s=0.0, prep_s=None, refuel_s=None)
    opz = dict(common, role="opz", opz=dict(
        observations=[asm_row], fusions=[], suggestions=[],
        radar=dict(surface=True, air=True, range_nm=40, live=True,
                   sweep_bearing=20.0, sweep_rate_deg_s=180.0, weather_severity=.1,
                   surface_effective_range_nm=35.0, air_effective_range_nm=38.0),
        defense=dict(vls=8, ciws=200, aa=40, chaff_ready=True,
                     ciws_ready=True, aa_ready=True, ciws_released=True),
        asm_observations=[asm_row],
        source_classifications=[], radar_blips=[], designated_target_ref=None,
        own_assets=dict(ship=navigation, helicopter=helicopter_asset,
                        mpa=_projected_mpa(), consort=None, weapons=[
            dict(ref="opaque-torpedo-reference-one", x=251.0, y=249.0, depth_m=60.0,
                 course=90.0, state="RUN")]), trails=[]))
    helicopter = dict(common, role="helicopter", helicopter=dict(
        asset=dict(helicopter_asset, buoy_mode="PASSIVE", pattern="single",
                   pattern_remaining=0, mad_mode=False, radar=True, radar_switch=True), waypoint=None,
        buoys=[dict(ref="opaque-buoy-reference-one", label="SB01", x=252.0, y=248.0,
                    battery_s=500.0, active=True, mode="PASSIVE"),
               dict(ref="opaque-buoy-reference-two", label="SB02", x=253.0, y=247.0,
                    battery_s=400.0, active=False, mode="PASSIVE")],
        buoy_observations=[], acoustic=dict(source="DIP", sources=["DIP", "SB1", "SB2"], ready=False,
            spectrum=[], history=[], bin_frequencies_hz=[], broadband=[], broadband_history=[],
            demon=[], demon_history=[], listen_bearing=None, audition_mode="BROADBAND",
            band_preset="FULL", gain_db=0.0, notch=False), navigation=navigation,
        tactical=[], target_choices=[weapon_row], dip_observations=[dict(
            ref="dip-ref", label="K01", bearing=123.0,
            bearing_uncertainty_deg=1.5, age_s=2.0, range_nm=4.0,
            active_bearing=125.0, range_uncertainty_nm=.2,
            depth_m=55.0, depth_uncertainty_m=3.0, fix_age_s=3.0,
            classification=None, qualified=False, released_to_opz=False)],
        dip_environment=dict(water_depth_m=200.0, thermocline_m=60.0,
                             depth_limit_m=190.0, bottom_clearance_m=None,
                             winch_rate_m_s=2.5, below_thermocline=None),
        rescue=None,
        readiness=dict(flightdeck_down=False, deck_state="OK", can_launch=False,
                        can_return=True, can_set_waypoint=True, can_deploy_buoy=True,
                         can_pattern=True, can_mad=True,
                         can_set_dipping=True, can_set_dip_depth=False,
                         can_dipping_ping=False,
                         weather_launch_safe=True,
                         weather_dipping_safe=True, crosswind_kn=4.0,
                         rtb_margin_s=600.0,
                         deck_motion=dict(roll_deg=2.0, pitch_deg=-1.0, roll_limit_deg=8.0,
                                          pitch_limit_deg=3.5, quiet_s=9.0, window_s=6.0,
                                          window_open=True))))
    damage = dict(common, role="damage", damage=dict(
        compartments=[dict(key="engine", name="Engine", state="BESCHAEDIGT",
                           flood=20.0, fire=10.0, leak="patched", inflow=0.0, repairable=True,
                           trend=dict(flood_rate=.1, fire_rate=-.2, repairable=True))],
        teams=[dict(team=1, compartment=None, transit_s=0.0), dict(team=2, compartment="engine", transit_s=0.0)],
        total=15.0, sunk=False,
        stability=dict(list_deg=0.5, draft_m=7.5, trim_deg=-0.2, counterflood_room=None,
                       can_counterflood=True), crew=_projected_crew()))
    bridge = dict(common, role="bridge", bridge=dict(crew=_projected_crew(),
        navigation=navigation, tactical_summary=[], sightings=[], lookout=LOOKOUT,
        route=ROUTE,
        orders=dict(station_down=False, speed_max_kn=25.0, telegraph="FULL",
                    noise=.8, cavitating=False),
        threat=dict(observations=[], count=0, average_flood=0.0, torpedoes=[]),
        systems=[dict(key="bridge", state="OK", down=False)]))
    return {"weapons": weapons, "opz": opz, "helicopter": helicopter,
            "damage": damage, "bridge": bridge}


@pytest.mark.parametrize("width,height", [(500, 844), (1280, 720), (1920, 1080)])
def test_direct_fire_grants_confirmation_exact_bodies_and_role_switch_in_chromium(tmp_path, width, height):
    chromium = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
    if not chromium:
        pytest.skip("Optional direct-fire browser contract: no installed Chromium")
    en, de = catalogs()
    stations = {station: _station_record() for station in SESSION_ROLES}
    for station, generation in (("weapons", 1), ("opz", 2),
                                ("helicopter", 3), ("damage", 4),
                                ("bridge", 5)):
        stations[station] = _station_record(
            "mine", station_generation=generation, command=True,
            direct_fire=station in {"opz", "helicopter"})
    session = dict(protocol=2, client_id="fire-client", name="Fire Watch",
                   csrf="fire-csrf", ordinal=0, presence=1.0, host=None, lobby=None, handover=[],
                   next_command_seq=0, observer=False, station="weapons", requested_station=None,
                   station_generation=1, active_station="weapons",
                   active_generation=1, simlog=False, stations=stations,
                   grants=dict(command=True, direct_fire=False, simlog=False,
                               sonar_audio=False))
    chart = dict(protocol=2, revision="fire-world", size_nm=500.0,
                 landmasses=[], disclaimer="Synthetic test chart")
    html = inject_probe(index_html(), "direct-fire-test.js")
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
                 f"--user-data-dir={tmp_path / 'direct-fire-browser'}",
                 f"--window-size={width},{height}",
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
    legacy["sound_events"] = [{"seq": 1, "cue": "explosion", "pan": None}]

    def tactical_row(row):
        result = {key: row[key] for key in (
            "ref", "label", "domain", "source", "affiliation", "bearing",
            "range_nm", "x", "y", "course", "speed_kn", "quality", "age_s",
            "bearing_uncertainty_deg", "range_uncertainty_nm")}
        result.update(observer_x=legacy["ownship"]["x"],
                      observer_y=legacy["ownship"]["y"], altitude_m=None,
                      visual_class=None, visual_type=None)
        return result

    def sonar_row(row):
        result = {key: row[key] for key in (
            "ref", "label", "source", "classification", "bearing", "range_nm",
            "x", "y", "depth_m", "course", "speed_kn", "quality", "age_s",
            "fix_age_s", "bearing_uncertainty_deg", "range_uncertainty_nm",
            "fixes")}
        result.update(observer_x=legacy["ownship"]["x"],
                      observer_y=legacy["ownship"]["y"], released_to_opz=False,
                      profile=None)
        return result

    def state_for(role):
        common = {key: legacy[key] for key in (
            "version", "session", "epoch", "revision", "seq", "phase",
            "chart_revision", "clock", "environment", "mission")}
        common.update(protocol=2, role=role)
        common["environment"] = dict(
            sea_state=legacy["environment"]["sea_state"],
            effective_sea_state=float(legacy["environment"]["sea_state"]),
            is_night=legacy["environment"]["is_night"], weather="clear",
            wind_from_deg=220.0, wind_speed_kn=10.0,
            rain_intensity=0.0, visibility_nm=30.0, storm=0.0)
        common["autocrew"] = {"enabled": False, "status": "off"}
        common["autocrew_overview"] = []
        common["audio"] = {"events": list(legacy["sound_events"]), "callouts": []}
        common["weather_station"] = WEATHER_STATION
        common["plot"] = PLOT
        common["alarms"] = []
        common["hit_view"] = None
        common["crew_noise"] = CREW_NOISE
        common["lamp_tips"] = {}
        if role == "bridge":
            common[role] = {"navigation": {key: legacy["ownship"][key] for key in (
                "x", "y", "course", "speed", "target_course", "target_speed")},
                            "tactical_summary": [tactical_row(row)
                                                 for row in legacy["tracks"]]}
            common[role]["navigation"].update(rudder_angle=0.0, yaw_rate=0.0, turn_radius_nm=None)
            common[role]["orders"] = {"station_down": False, "speed_max_kn": 25,
                                      "telegraph": "HALF", "noise": .2,
                                      "cavitating": False}
            common[role]["sightings"] = []
            common[role]["lookout"] = LOOKOUT
            common[role]["route"] = ROUTE
            common[role]["crew"] = _projected_crew()
            common[role]["threat"] = {"observations": [], "count": 0,
                                       "average_flood": 0.0, "torpedoes": []}
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
                                     "speed_kn": 10.0, "speed_min_kn": 3.0,
                                     "speed_max_kn": 12.0,
                                     "depth_m": 20.0, "depth_target_m": 20.0},
                             "vds": {"state": "STOWED", "payout": 0.0,
                                     "available": False, "handling_ok": True,
                                     "speed_min_kn": 3.0, "speed_max_kn": 15.0,
                                     "max_sea_state": 5, "depth_m": 50.0,
                                     "depth_target_m": 50.0},
                             "bt": {"ready": True, "cooldown_s": 0.0,
                                    "thermocline_m": None},
                             "ping": {"ready": True, "cooldown_s": 0.0, "pulse": "CW"},
                             "tma_enabled": False, "tma_method": "hypothesis", "gain_db": 0.0,
                             "band_preset": "FULL", "band_hz": [0.0, 300.0],
                             "notch": False, "peak_hold": False,
                             "harmonic_hz": None,
                             "harmonic_candidates_hz": [12.5, 25.0],
                             "audio_enabled": True, "volume": .5,
                              "quiet_mode": False,
                              "tools": {"assist": False, "lofar_cursor_hz": 50.0,
                                        "demon_cursor_hz": 10.0, "integration_s": 2,
                                        "vernier": False, "shaft_hz": None,
                                        "blade_hz": None, "operator_notch_hz": None,
                                        "demon_band_hz": [400.0, 1400.0],
                                        "heterodyne_hz": 700.0, "library_marks": 0,
                                        "library": []}},
                "visualization": {
                    "broadband": {"bearing_start_deg": 0.0,
                                  "bearing_step_deg": 4.0, "history": []},
                    "lofar": {"frequency_min_hz": 0.0,
                              "frequency_max_hz": 300.0,
                              "bin_frequencies_hz": [], "history": [],
                              "spectrum": [], "held": False, "vernier": None},
                        "demon": {"frequency_min_hz": 1.0,
                                  "frequency_max_hz": 80.0, "bin_step_hz": 1.0,
                                  "spectrum": [], "history": [], "analysis": None},
                    "tma": [], "bt": None, "active_echoes": [],
                        "receiver": {"array": "BOW", "listen_bearing": 25.0,
                                     "beam_width_deg": 30.0, "listen_mode": "BROADBAND",
                                     "focus_locked": False, "audio_enabled": False,
                                     "own_course": 90.0, "baffle_half_deg": 30.0}}}
        return common
    chart = {"protocol": 2, "revision": legacy["chart_revision"], "size_nm": 500,
             "landmasses": [], "disclaimer": "Synthetic test chart"}
    html = inject_probe(index_html(), "session-test.js")
    script = (BROWSER_SESSION.replace("__STATIONS__", json.dumps(",".join(STATIONS)))
              .replace("__PENDING__", json.dumps(en[PREFIX + "station_requested"]))
              .replace("__FAILED__", json.dumps(en[PREFIX + "station_mutation_failed"].split(".")[0]))
              .replace("__REVOKED__", json.dumps(en[PREFIX + "role_revoked"].split(".")[0]))
              .replace("__SIMLOG_STATION__", json.dumps(en[PREFIX + "simlog_station_required"]))
              .replace("__SIMLOG_GRANT__", json.dumps(en[PREFIX + "simlog_grant_required"]))
              .replace("__BRIDGE__", json.dumps(en[PREFIX + "station_bridge"]))
              .replace("__SONAR__", json.dumps(en[PREFIX + "station_sonar"])))

    class Handler(BaseHTTPRequestHandler):
        session = None
        cookie = "browser-cookie-secret"
        request_polls = 0
        reload_ready = False
        reload_polls = 0
        sonar_event_polls = 0
        publish_warning = False

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
            elif self.path in WEB_ROUTES:
                self.reply(200, WEB_ROUTES[self.path][1], WEB_ROUTES[self.path][0])
            elif self.path in ("/api/v2/ui?lang=en", "/api/v2/ui?lang=de"):
                source = de if self.path.endswith("de") else en
                self.reply(200, {key: value for key, value in source.items() if key.startswith(PREFIX)})
            elif self.path == "/api/v2/contacts":
                self.reply(200, browser_contact_analysis())
            elif self.path == "/test/reload-ready":
                type(self).reload_ready = True
                type(self).reload_polls = 0
                self.reply(200, {})
            elif self.path == "/test/new-warning":
                type(self).publish_warning = True
                self.reply(200, {})
            elif self.path == "/test/new-sound":
                legacy["sound_events"].append({"seq": 2, "cue": "gunfire", "pan": None})
                type(self).reload_polls = -100
                self.reply(200, {})
            elif self.path == "/test/allow-role-loss":
                type(self).reload_polls = 1
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
            elif self.path in ("/api/v2/proposals", "/api/v2/events", "/api/v2/simlog") and self.authenticated():
                cls = type(self)
                role = cls.session["station"]
                state = state_for(role)
                if self.path == "/api/v2/proposals":
                    self.reply(200, {"protocol": 2, "session": state["session"],
                                     "epoch": state["epoch"], "role": role,
                                     "target": ({"ref": state["sonar"]["observations"][0]["ref"],
                                                 "label": "Sierra 01", "status": "pending"}
                                                if role == "sonar" else None),
                                     "navigation": None})
                elif self.path == "/api/v2/events":
                    rows = []
                    if role == "sonar":
                        cls.sonar_event_polls += 1
                        rows = [{"seq": 1, "kind": "mission", "severity": "warning",
                                 "message": "Baseline warning",
                                 "stamp": "08:00", "tag": "MIS"}]
                        if cls.publish_warning:
                            rows.append({"seq": 2, "kind": "mission", "severity": "warning",
                                         "message": "New warning",
                                 "stamp": "08:00", "tag": "MIS"})
                    self.reply(200, {"protocol": 2, "session": state["session"],
                                     "epoch": state["epoch"], "role": role,
                                     "latest_seq": rows[-1]["seq"] if rows else 0,
                                     "events": rows})
                elif cls.session["simlog"]:
                    self.reply(200, {"protocol": 2, "session": state["session"],
                                     "epoch": state["epoch"], "role": role,
                                     "entries": [{"seq": 1, "t": 1.0, "stamp": "00:01",
                                                  "state": state}]})
                else:
                    self.reply(403, {"error": "forbidden"})
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
                                "next_command_seq": 0, "observer": False, "active_station": None,
                                "active_generation": 0, "simlog": False, "host": None, "lobby": None, "handover": [],
                                "station": None, "requested_station": None,
                                "station_generation": 0,
                                "grants": {"command": False, "direct_fire": False,
                                           "simlog": False, "sonar_audio": False},
                                "stations": {
                                    station: _station_record(
                                        "occupied" if station == "sonar" else "available")
                                    for station in SESSION_ROLES
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
             f"http://127.0.0.1:{server.server_port}/#simlog"],
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
    game.ship.speed = 15.0
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
    # Pre-rendered like the assets: resources.files is redirected below.
    console._manual_pages = {}
    console._manual_pages = {lang: manual.html_page(lang) for lang in manual.LANGUAGES}
    html = inject_probe(index_html(), "real-role-test.js")
    copy_assets(tmp_path, html)
    monkeypatch.setattr(commander_transport.resources, "files", lambda _package: tmp_path)

    # Use the actual F9 owner transition, then start the selected server row while
    # administration remains open. No bridge publication exists when Chromium pairs.
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F9))
    assert game.commander_open and game.administration_open
    console.activate(game)
    assert console.address is not None, console.error
    script = REAL_ROLE_SESSION.replace("__CODE__", json.dumps(console.pairing_code))
    (tmp_path / "real-role-test.js").write_text(script, encoding="utf-8")
    # CommanderServer loads its immutable assets at start; add only the test hook
    # to that real server's route table after startup.
    console.server._http.assets["/real-role-test.js"] = (
        "text/javascript; charset=utf-8", script.encode("utf-8"))

    # The page's result is read over DevTools while it runs, so the host loop
    # stops as soon as the probe settles instead of at a fixed deadline.
    profile = tmp_path / "real-browser"
    log = (tmp_path / "chromium.log").open("wb")
    process = subprocess.Popen(
        [chromium, "--headless", "--no-sandbox", "--disable-gpu",
         "--disable-background-networking", "--no-first-run",
         "--no-default-browser-check", "--disable-dev-shm-usage",
         f"--user-data-dir={profile}", "--virtual-time-budget=300000",
         f"--window-size={width},{height}", "--remote-debugging-port=0",
         f"http://{console.address[0]}:{console.address[1]}/"],
        stdout=subprocess.DEVNULL, stderr=log,
    )
    roles = ("bridge", "sonar", "opz", "eloka", "engine", "damage",
             "radio", "helicopter", "weapons")
    role_index = -1
    presence_marks = []
    bridge_live = False
    started = time.monotonic()
    read_at = started
    root = {}

    def grant_and_activate(client_id, station):
        assert console.server.grant_station(client_id, station)
        status = next(row for row in console.server.client_statuses()
                      if row["client_id"] == client_id)
        generation = status["stations"][station]["station_generation"]
        assert console.server.activate_station(client_id, station, generation)

    try:
        while process.poll() is None and time.monotonic() - started < 90:
            if time.monotonic() - read_at > .5:
                read_at = time.monotonic()
                root = page_dataset(profile) or root
                # Once the probe passed, stay until the last role's presence
                # has cycled too (asserted below).
                if (root.get("realRoleTest") == "failed" or (
                        root.get("realRoleTest") and len(presence_marks) >= 3)):
                    break
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
                  # The first mark can be the previous role's poll: one more
                  # lets the browser poll this role's state on both sides of
                  # its chart fetch before the host moves it on.
                  and len(presence_marks) >= 4
                  # A slow browser finishes this role's checks first.
                  and roles[role_index] in root.get("rolesDone", "").split(",")):
                role_index += 1
                grant_and_activate(roster[0]["client_id"], roles[role_index])
                assert console.server.set_client_grant(
                    roster[0]["client_id"], "command", True)
                presence_marks.clear()
            time.sleep(.02)
    finally:
        process.kill()
        process.wait(timeout=5)
        log.close()
        console.stop()
        game.audio.shutdown()

    assert root.get("realRoleTest") == "passed", root.get(
        "failure", (tmp_path / "chromium.log").read_text(errors="replace")[-3000:])
    assert role_index == len(roles) - 1
    assert all(contact.player_class == "U_BOOT"
               for contact in game.sonar.contacts.values())
    assert all(contact.released_to_opz for contact in game.sonar.contacts.values())
    assert len(game.opz_fusion.fusions) == 1
    assert len(presence_marks) >= 3
