"""Resource/catalog contracts; optional real Chromium tests need no driver or Node."""

import json
import re
import shutil
import subprocess
import threading
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from string import Formatter

import pytest

from src.core.version import APP_VERSION
from src.data.contact_analysis import project_contact_catalog


ROOT = Path(__file__).resolve().parents[1]
ASSETS = resources.files("data.commander")
PREFIX = "commander.web."


class Document(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.elements = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def catalogs():
    return [json.loads((ROOT / "data" / "i18n" / f"{lang}.json").read_text())
            for lang in ("en", "de")]


def test_commander_resources_are_self_contained_and_csp_safe():
    assert all(ASSETS.joinpath(name).is_file() for name in ("__init__.py", "index.html", "app.js", "style.css"))
    html = ASSETS.joinpath("index.html").read_text()
    js = ASSETS.joinpath("app.js").read_text()
    css = ASSETS.joinpath("style.css").read_text()
    document = Document(html)
    ids = [attrs["id"] for _, attrs in document.elements if "id" in attrs]
    assert len(ids) == len(set(ids))
    assert set(re.findall(r'\$\("([\w-]+)"\)', js)) <= set(ids)
    code = next(attrs for _, attrs in document.elements if attrs.get("id") == "code")
    assert code["maxlength"] == "6" and code["pattern"] == "[0-9]{3}[A-Za-z]{3}"
    assert code["autocapitalize"] == "characters" and code["autocomplete"] == "off"
    assert code["placeholder"] == "482KMT" and code["aria-describedby"] in ids
    tabs = [attrs for _, attrs in document.elements if attrs.get("role") == "tab"]
    panels = [attrs for _, attrs in document.elements if attrs.get("role") == "tabpanel"]
    assert len(tabs) == len(panels) == 4
    assert sum(tab.get("aria-selected") == "true" and tab.get("tabindex") == "0"
               for tab in tabs) == 1
    assert all(tab.get("type") == "button" and tab["aria-controls"] in ids for tab in tabs)
    assert all(panel["aria-labelledby"] in ids for panel in panels)
    assert {tab["aria-controls"] for tab in tabs} == {panel["id"] for panel in panels}
    assert sum("hidden" not in panel for panel in panels) == 1
    lookout = next(attrs for _, attrs in document.elements
                   if attrs.get("id") == "panel-lookout")
    assert "pending-panel" not in lookout.get("class", "")
    assert {"lookout", "lookout-zoom-in", "lookout-zoom-out", "lookout-reset",
            "lookout-range", "lookout-sea", "lookout-light", "lookout-note"} <= set(ids)
    for tag, attrs in document.elements:
        assert not any(key.startswith("on") or key == "style" for key in attrs)
        assert tag not in {"iframe", "img", "object", "embed", "style"}
        for key in ("src", "href"):
            if key in attrs:
                assert (attrs[key] in {"./app.js", "./style.css"}
                        or key == "href" and attrs[key].startswith("#guide-"))
    csp = next(attrs["content"] for _, attrs in document.elements if attrs.get("http-equiv") == "Content-Security-Policy")
    assert "default-src 'none'" in csp
    assert "connect-src 'self'" in csp
    assert "img-src 'self'" in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
    for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "localStorage", "sessionStorage", "indexedDB", "document.cookie", "Math.random", "getUserMedia", "eval(", "new Function", "WebSocket", "https://", "http://"):
        assert forbidden not in js
    assert "@import" not in css and "url(" not in css
    assert "AbortController" in js and 'headers.Authorization = `Bearer ${credential}`' in js
    assert "crypto.randomUUID" in js and "crypto.getRandomValues" in js
    assert 'request("/state")' in js and 'request("/chart")' in js
    assert 'request("/commands"' in js and 'expected: 202' in js
    assert "result.reasoncode" in js and not re.search(r"result\.reason\b", js)
    lookout_renderer = js.split("function drawLookout()", 1)[1].split(
        "function changeLookoutRange", 1)[0]
    assert "chart" not in lookout_renderer and "sendCommand" not in lookout_renderer
    assert "snapshot.tracks" in lookout_renderer and "snapshot.ownship" in lookout_renderer
    analyzer_renderer = js.split("function renderContactAnalysis()", 1)[1].split(
        "function renderConnection", 1)[0]
    assert "sendCommand" not in analyzer_renderer and 'request("/commands"' not in analyzer_renderer
    assert "analysisSelected" in analyzer_renderer and "textContent" in analyzer_renderer
    assert 'request("/contacts", { auth: false })' in js
    assert js.count('request("/contacts", { auth: false })') == 1
    assert "innerHTML" not in analyzer_renderer
    assert 'image.alt = descriptions.join(" ")' in analyzer_renderer
    assert "machine.cruise_lines" in analyzer_renderer
    assert "machine.cruise_broadband" in analyzer_renderer
    assert "analyzer_spectrum_legend" in html
    assert "analyzer_hypothesis_legend" in html


def test_guide_is_complete_static_content_with_panel_local_navigation():
    html = ASSETS.joinpath("index.html").read_text()
    js = ASSETS.joinpath("app.js").read_text()
    css = ASSETS.joinpath("style.css").read_text()
    document = Document(html)
    guide = next(attrs for _, attrs in document.elements
                 if attrs.get("id") == "panel-guide")
    assert "pending-panel" not in guide["class"]
    links = [attrs for tag, attrs in document.elements
             if tag == "a" and attrs.get("href", "").startswith("#guide-")]
    expected = {"guide-access", "guide-operations", "guide-observations",
                "guide-proposals", "guide-eloka", "guide-analyzer",
                "guide-connection", "guide-authority"}
    ids = {attrs["id"] for _, attrs in document.elements if "id" in attrs}
    assert {link["href"][1:] for link in links} == expected <= ids
    assert all("data-i18n" in link for link in links)
    guide_handler = js.split(
        'for (const link of document.querySelectorAll("#guide-nav a"))', 1
    )[1].split('$("track-list").addEventListener', 1)[0]
    assert "event.preventDefault()" in guide_handler
    assert 'const panel = $("panel-guide")' in guide_handler
    assert "panel.scrollTop" in guide_handler and "window.scroll" not in guide_handler
    assert "sendCommand" not in guide_handler and 'request("/commands"' not in guide_handler
    assert re.search(r"\.guide-panel:not\(\[hidden\]\).*display: block", css)
    assert re.search(r"\.tab-panel \{[^}]*overflow-y: auto", css)


def test_contacts_panel_owns_bounded_browser_and_detail_scrolling():
    html = ASSETS.joinpath("index.html").read_text()
    css = ASSETS.joinpath("style.css").read_text()
    document = Document(html)
    contacts = next(attrs for _, attrs in document.elements
                    if attrs.get("id") == "panel-contacts")
    assert "pending-panel" not in contacts["class"]
    ids = {attrs["id"] for _, attrs in document.elements if "id" in attrs}
    assert {"analysis-filter", "analysis-category", "analysis-list",
            "analysis-profile", "analysis-images"} <= ids
    assert 'maxlength="96"' in html
    assert re.search(r"\.analyzer-panel:not\(\[hidden\]\).*overflow: hidden", css)
    assert re.search(r"\.analysis-list \{[^}]*overflow-y: auto", css)
    assert re.search(r"\.analyzer-detail \{[^}]*overflow-y: auto", css)
    assert "silhouette" not in ASSETS.joinpath("app.js").read_text().lower()
    for catalog in catalogs():
        spectrum = catalog[PREFIX + "analyzer_spectrum_legend"]
        hypothesis = catalog[PREFIX + "analyzer_hypothesis_legend"]
        assert "5 Hz-10 kHz" in spectrum
        assert "0-80" in hypothesis
        assert "DEMON" in hypothesis
        assert any(word in hypothesis.lower() for word in ("measurement", "messung"))


def test_commander_catalogs_cover_markup_and_script():
    en, de = catalogs()
    english = {key: value for key, value in en.items() if key.startswith(PREFIX)}
    german = {key: value for key, value in de.items() if key.startswith(PREFIX)}
    assert english.keys() == german.keys()
    assert len(english) >= 100
    for key, value in english.items():
        assert isinstance(value, str) and value and isinstance(german[key], str) and german[key]
        fields = lambda text: {field for _, field, _, _ in Formatter().parse(text) if field is not None}
        assert fields(value) == fields(german[key])
        assert all(field.isidentifier() for field in fields(value))
    html = ASSETS.joinpath("index.html").read_text()
    js = ASSETS.joinpath("app.js").read_text()
    markup_keys = set(re.findall(r'data-i18n(?:-aria)?="([\w]+)"', html))
    literal_keys = set(re.findall(r'\bt\("([\w]+)"', js))
    metric_keys = set(re.findall(r'\["([a-z_]+)", (?:unit\(|number\(|t\(|`|track\.|item\.|helo\.|typeof |finite\()', js))
    dynamic_keys = set(re.findall(r'"((?:aff_|class_|domain_|command_|proposal_|connection_|sound_|phase_|damage_|helo_|reason_)[a-z_]+)"', js))
    dynamic_keys |= {"connection_syncing", "connection_connected", "connection_stale", "connection_unpaired"}
    assert {PREFIX + key for key in markup_keys | literal_keys | metric_keys | dynamic_keys} <= english.keys()
    for reason in ("invalid_schema", "unauthorized", "stale_session", "stale_epoch", "commands_blocked",
                   "duplicate_id", "revision_conflict", "unknown_track", "ineligible_track", "ok"):
        assert f'{reason}: "reason_{reason}"' in js
        key = PREFIX + "reason_" + reason
        assert english[key] != reason and german[key] != reason and english[key] != german[key]
    assert not any(item.name.endswith(".json") for item in ASSETS.iterdir())


BROWSER_CONTRACT = r"""
"use strict";
const $test = (id) => document.getElementById(id);
const failures = [];
window.addEventListener("error", (event) => failures.push(event.message));
window.addEventListener("unhandledrejection", (event) => failures.push(String(event.reason)));
const assert = (condition, message) => { if (!condition) throw new Error(message); };
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
// Chromium's dump-dom virtual clock can starve compositor frames. Drive the
// same on-demand canvas callbacks with that clock, not a wall-time compositor.
window.requestAnimationFrame = (callback) => setTimeout(() => callback(performance.now()), 16);
window.cancelAnimationFrame = clearTimeout;
async function until(predicate, message) {
  for (let i = 0; i < 900; i++) { if (predicate()) return; await sleep(20); }
  throw new Error(message);
}
const nativeFetch = window.fetch.bind(window);
const issued = [];
const commands = [];
let active = 0, maxActive = 0, charts = 0, stateCalls = 0, tones = 0;
let offline = false, mismatch = false, loseAck = false, holdState = false, stalledSeq = false;
let reconcileActor = false, publishActorResults = false, rejectRetry = false, actorEffects = 0;
const actorResults = new Map();
let lastSignal = null;
const liveFixture = __STATE__;
const statusFixture = __STATUS_STATE__;
const fixture = structuredClone(statusFixture);
const drawnFixes = new Map();
const drawnSonarFixes = new Map();
let canvasFrame = {texts: [], translations: [], fills: 0};
let lookoutFrame = {texts: [], translations: [], rotations: [], arcs: [], fills: 0};
const nativeFillRect = CanvasRenderingContext2D.prototype.fillRect;
CanvasRenderingContext2D.prototype.fillRect = function (...args) {
  if (this.canvas.id === "lookout") lookoutFrame = {texts: [], translations: [], rotations: [], arcs: [], fills: 0};
  else canvasFrame = {texts: [], translations: [], fills: 0};
  return nativeFillRect.apply(this, args);
};
const nativeTranslate = CanvasRenderingContext2D.prototype.translate;
CanvasRenderingContext2D.prototype.translate = function (x, y) {
  (this.canvas.id === "lookout" ? lookoutFrame : canvasFrame).translations.push({x, y});
  return nativeTranslate.call(this, x, y);
};
const nativeRotate = CanvasRenderingContext2D.prototype.rotate;
CanvasRenderingContext2D.prototype.rotate = function (angle) {
  if (this.canvas.id === "lookout") lookoutFrame.rotations.push(angle);
  return nativeRotate.call(this, angle);
};
const nativeFill = CanvasRenderingContext2D.prototype.fill;
CanvasRenderingContext2D.prototype.fill = function (...args) {
  (this.canvas.id === "lookout" ? lookoutFrame : canvasFrame).fills++;
  return nativeFill.apply(this, args);
};
const nativeArc = CanvasRenderingContext2D.prototype.arc;
CanvasRenderingContext2D.prototype.arc = function (x, y, radius, start, end, ...rest) {
  if (this.canvas.id === "lookout") lookoutFrame.arcs.push({x, y, radius, start, end});
  return nativeArc.call(this, x, y, radius, start, end, ...rest);
};
const nativeFillText = CanvasRenderingContext2D.prototype.fillText;
CanvasRenderingContext2D.prototype.fillText = function (text, x, y, ...rest) {
  if (/^[-\d.,]+$/.test(text)) {
    assert(text !== "-0", "chart grid does not label the origin as negative zero");
    assert(x >= 0 && x + this.measureText(text).width <= this.canvas.clientWidth &&
      y >= parseFloat(this.font) && y <= this.canvas.clientHeight, "numeric chart labels remain inside the canvas");
  }
  (this.canvas.id === "lookout" ? lookoutFrame : canvasFrame).texts.push(text);
  if (fixture.tracks.some((track) => track.label === text)) drawnFixes.set(text, {x, y});
  if (/ (PING|TMA|SONOBUOY)$/.test(text)) drawnSonarFixes.set(text, {x, y});
  return nativeFillText.call(this, text, x, y, ...rest);
};
const chartFixture = {revision: "chart-A", size_nm: 500, landmasses: [{points: [[20, 20], [160, 40], [90, 160], [20, 20]]}], disclaimer: "Synthetic test geography <script>not markup</script>"};
class TestAudio {
  constructor() { this.state = "suspended"; this.currentTime = 0; this.destination = {}; }
  async resume() { this.state = "running"; }
  async suspend() { this.state = "suspended"; }
  createOscillator() {
    tones++;
    return {frequency: {setValueAtTime() {}}, connect() {}, disconnect() {}, start() {}, stop() { setTimeout(() => this.onended?.(), 300); }};
  }
  createGain() { return {gain: {setValueAtTime() {}, linearRampToValueAtTime() {}}, connect() {}, disconnect() {}}; }
}
window.AudioContext = TestAudio;
window.fetch = async (url, options = {}) => {
  issued.push({url: String(url), options});
  active++; maxActive = Math.max(maxActive, active);
  try {
    assert(options.signal instanceof AbortSignal, "every request has an abort deadline");
    assert(!String(url).includes("test-secret"), "token absent from URL");
    const path = new URL(url, location.href).pathname;
    if (path === "/api/v1/ui" || path === "/api/v1/contacts") {
      assert(!options.headers.Authorization, "public static data has no bearer token");
      return await nativeFetch(url, options);
    }
    if (path === "/api/v1/pair") return await nativeFetch(url, options);
    assert(options.headers.Authorization === "Bearer test-secret", "authenticated request header");
    if (path === "/api/v1/commands") {
      const command = JSON.parse(options.body);
      commands.push(command);
      if (loseAck) throw new TypeError("lost acknowledgement");
      if (rejectRetry) return new Response("", {status: 429});
      if (reconcileActor) {
        // A small crew actor fixture: ID replay precedes revision checks. It
        // lets the browser prove that reconciliation does not create new actions.
        let previous = actorResults.get(command.id);
        if (previous) {
          assert(previous.envelope === options.body, "replay has the identical serialized envelope");
        } else {
          const applied = command.revision === fixture.revision;
          const result = {id: command.id, status: applied ? "applied" : "rejected", reasoncode: applied ? "ok" : "revision_conflict"};
          previous = {envelope: options.body, result};
          actorResults.set(command.id, previous);
          if (applied) {
            actorEffects++;
            fixture.revision++;
            fixture.proposal = {ref: command.track, label: "Reconciled proposal", status: "pending"};
          }
        }
        if (publishActorResults) fixture.results.push(structuredClone(previous.result));
      }
      return await nativeFetch(url, options);
    }
    if (path === "/api/v1/state") {
      stateCalls++;
      lastSignal = options.signal;
      if (holdState) await new Promise((resolve, reject) => options.signal.addEventListener("abort", () => reject(new DOMException("timeout", "AbortError")), {once: true}));
      if (offline) throw new TypeError("offline");
      if (!stalledSeq) fixture.seq++;
      await sleep(15);
      return new Response(JSON.stringify(fixture), {status: 200});
    }
    if (path === "/api/v1/chart") {
      charts++;
      await sleep(15);
      const picture = fixture.ownship.x === null ? {size_nm: 500, landmasses: [], disclaimer: ""} : chartFixture;
      return new Response(JSON.stringify({...picture, revision: mismatch ? "wrong-chart" : fixture.chart_revision}), {status: 200});
    }
    throw new Error("unexpected request " + path);
  } finally { active--; }
};

async function runContract() {
  await until(() => !$test("shell").hidden, "translations bootstrap");
  assert($test("operations").hidden, "no data before pairing");
  assert(issued[0].url.includes("/api/v1/ui?lang="), "translations fetched first");
  assert($test("sound").getAttribute("aria-pressed") === "false" && tones === 0, "muted by default");
  assert($test("code").maxLength === 6 && $test("code").autocapitalize === "characters", "six-character code input with capitalization hint");
  for (const invalid of ["123456", "ABC123", "12ABCD", "123AB", "123ABCD", "123A!C"]) {
    $test("code").value = invalid;
    assert(!$test("code").checkValidity(), "native validation rejects malformed code " + invalid);
    $test("pair-form").requestSubmit();
  }
  await sleep(50);
  assert(!issued.some((entry) => entry.url === "/api/v1/pair"), "invalid codes never reach the network");
  $test("code").value = "123ABC";
  assert($test("code").checkValidity(), "three digits followed by three uppercase letters accepted");
  $test("pair-form").requestSubmit();
  await until(() => $test("pair-error").textContent && !$test("pair-submit").disabled, "rate-limited pairing returns an editable form");
  assert($test("pair-error").textContent.includes("Wait") && $test("pair-error").textContent.includes("new code"), "pairing failure advises waiting or a new code");
  assert($test("code").value === "" && $test("operations").hidden, "failed pairing clears code and reveals no session");
  await sleep(650);
  assert(issued.filter((entry) => entry.url === "/api/v1/pair").length === 1, "rate-limited pairing never retries automatically");
  $test("code").value = "123abc";
  assert($test("code").checkValidity(), "lowercase letters pass native validation before normalization");
  $test("pair-form").requestSubmit();
  await until(() => !$test("operations").hidden, "first matched chart and session");
  await sleep(50);
  assert(charts === 1 && stateCalls >= 2, "chart sandwiched by snapshots");
  assert($test("connection").dataset.state === "connected" && $test("phase").textContent === "Menu", "status-only menu is a healthy connection");
  assert($test("mission-name").textContent === "" && $test("objective").textContent === "", "status-only mission is empty");
  assert([...$test("own-metrics").querySelectorAll("dd")].every((value) => /^[\s/-]+$/.test(value.textContent)), "null ownship metrics are unavailable, not zero");
  assert([...$test("inventory").querySelectorAll("dd"), ...$test("mission-metrics").querySelectorAll("dd")].every((value) => value.textContent === "--"), "null inventory and clock stay unavailable");
  assert(!$test("track-list").querySelector("button") && !$test("damage-list").querySelector(".damage-row"), "status-only snapshot has no contacts or damage");
  assert($test("follow").disabled && $test("follow").getAttribute("aria-pressed") === "false", "no follow without an ownship position");
  $test("follow").dispatchEvent(new Event("click"));
  $test("zoom-in").click();
  await sleep(50);
  assert($test("follow").getAttribute("aria-pressed") === "false", "follow handler cannot invent a position");
  assert(canvasFrame.texts.length > 0 && canvasFrame.translations.length === 0 && canvasFrame.fills === 0, "menu draws chart grid but no ownship, helicopter, land or bearing wedges");
  assert(!canvasFrame.texts.includes("Own ship") && !canvasFrame.texts.includes("Own helicopter"), "no imaginary asset labels");
  assert($test("propose").disabled && $test("apply-classification").disabled && $test("apply-affiliation").disabled && $test("clear-proposal").disabled, "status-only commands are blocked");
  await sleep(650);
  assert($test("connection").dataset.state === "connected" && commands.length === 0, "status-only polling stays healthy without commands");
  const menuSession = fixture.session, menuRevision = fixture.chart_revision;
  Object.assign(fixture, structuredClone(liveFixture), {epoch: fixture.epoch + 1, seq: fixture.seq});
  await until(() => !$test("operations").hidden && $test("mission-name").textContent === liveFixture.mission.name, "live mission after menu");
  await sleep(50);
  assert(fixture.session === menuSession && fixture.chart_revision === menuRevision && charts === 2, "epoch change refetches chart even with unchanged session and chart revision");
  assert($test("chart-disclaimer").textContent === chartFixture.disclaimer && canvasFrame.fills > 0, "live chart replaces the redacted chart");
  assert(!$test("follow").disabled && canvasFrame.translations.length === 1 && canvasFrame.texts.includes("Own ship"), "live ownship geometry returns");
  assert(!document.body.textContent.includes("test-secret"), "token never rendered");
  assert(localStorage.length === 0 && sessionStorage.length === 0, "no persistent token");
  assert($test("code").value === "", "code cleared");
  assert($test("mission-name").textContent === fixture.mission.name && !$test("mission-name").children.length, "authored mission is inert text");
  assert($test("chart-disclaimer").children.length === 0, "disclaimer is inert text");
  const bounds = $test("chart").getBoundingClientRect();
  assert(innerWidth === __WIDTH__, "requested CSS viewport width: " + innerWidth);
  assert(bounds.width > 200 && bounds.height > 200, "responsive chart is visible");
  assert(document.documentElement.scrollWidth <= innerWidth + 1, "no horizontal page overflow");
  assert(document.documentElement.scrollHeight <= innerHeight + 1, "authenticated shell fits the viewport");
  assert($test("chart").width >= bounds.width, "high DPI backing canvas");
  assert(!drawnFixes.has(fixture.tracks[0].label), "bearing-only contact has no invented position marker");
  const fix = drawnFixes.get(fixture.tracks[1].label), air = drawnFixes.get(fixture.tracks[2].label);
  assert(fix && air && Math.abs((air.x - fix.x) / 50 - (air.y - fix.y) / -30) < .001, "equal X/Y scale, north up");
  const teamCounts = [...$test("damage-list").querySelectorAll(".metrics")].map((list) => list.lastElementChild.textContent);
  assert(teamCounts[0] === "Assigned teams (count)2" && teamCounts[1] === "Assigned teams (count)0", "team ID arrays display explicit counts, including empty assignments");
  const heloLabels = {AUF: "Airborne", HANGAR: "In hangar", ZURUECK: "Returning", VERLOREN: "Lost"};
  for (const state of ["AUF", "HANGAR", "ZURUECK", "VERLOREN"]) {
    Object.assign(fixture.ownship.helo, {state, x: 310, y: 300, course: 10});
    await until(() => $test("helo-metrics").textContent.includes(heloLabels[state]), "helicopter state snapshot " + state);
    await sleep(50);
    assert(canvasFrame.texts.includes("Own helicopter") === ["AUF", "ZURUECK"].includes(state), "only airborne helicopter states plot, even if stale coordinates exist: " + state);
  }
  fixture.ownship.helo = structuredClone(liveFixture.ownship.helo);
  const first = $test("track-list").querySelector("button");
  first.focus(); first.click();
  assert($test("detail-label").textContent === fixture.tracks[0].label, "local selection details");
  const sonarLabel = `${fixture.tracks[1].label} PING`;
  const sonarFix = drawnSonarFixes.get(sonarLabel);
  assert(sonarFix, "nested sonar fix is rendered under its opaque parent");
  fixture.tracks[1].fixes = [];
  await until(() => !canvasFrame.texts.includes(sonarLabel), "expired nested fix leaves draw geometry");
  const staleX = bounds.left + sonarFix.x - 9, staleY = bounds.top + sonarFix.y + 8;
  const oldSetCapture = $test("chart").setPointerCapture, oldReleaseCapture = $test("chart").releasePointerCapture;
  $test("chart").setPointerCapture = () => {};
  $test("chart").releasePointerCapture = () => {};
  for (const type of ["pointerdown", "pointerup"]) $test("chart").dispatchEvent(new PointerEvent(type, {
    bubbles: true, pointerId: 77, isPrimary: true, button: 0, clientX: staleX, clientY: staleY,
  }));
  $test("chart").setPointerCapture = oldSetCapture;
  $test("chart").releasePointerCapture = oldReleaseCapture;
  assert($test("detail-label").textContent === fixture.tracks[0].label,
    "removed sonar fix is no longer clickable");
  first.focus();
  if (innerWidth > 1250) {
    const supportGrid = document.querySelector(".support-grid");
    const support = supportGrid.getBoundingClientRect();
    const panel = document.querySelector(".chart-panel").getBoundingClientRect();
    const plot = $test("chart").getBoundingClientRect();
    assert(panel.bottom <= support.top, "support panels follow the workspace without overlap");
    const operationsPanel = $test("panel-operations");
    assert(support.bottom <= operationsPanel.scrollHeight + operationsPanel.getBoundingClientRect().top + 1, "support panels remain in the Operations scroller");
    assert(plot.height > 200 && plot.bottom <= panel.bottom, "bounded desktop chart retains a usable, contained plot");
    const details = document.querySelector(".details-panel");
    assert(getComputedStyle(details).overflowY === "auto", "long contact assessments scroll inside their panel");
    $test("propose-navigation").scrollIntoView({block: "nearest"});
    const action = $test("propose-navigation").getBoundingClientRect();
    const detailBounds = details.getBoundingClientRect();
    assert(action.top >= detailBounds.top && action.bottom <= detailBounds.bottom, "navigation action is reachable inside contact details");
    supportGrid.scrollIntoView({block: "start"});
    const reached = supportGrid.getBoundingClientRect();
    const operationBounds = operationsPanel.getBoundingClientRect();
    assert(reached.top >= operationBounds.top - 1 && reached.top < operationBounds.bottom, "Operations scrolling reaches support panels");
    operationsPanel.scrollTop = 0;
    details.scrollTop = 0;
  }
  $test("affiliation").value = "HOSTILE";
  $test("affiliation").dispatchEvent(new Event("change", {bubbles: true}));
  await sleep(650);
  assert(commands.length === 0 && fixture.crew_target === "fix-2", "selection and drafts never send commands");
  assert(document.activeElement === first, "poll preserves keyboard focus");
  assert($test("affiliation").value === "HOSTILE", "poll preserves operator draft");
  $test("navigation-course").value = "87.5";
  const commandsBeforeTabs = commands.length;
  const operationScale = $test("chart-scale").textContent;
  const tab = (name) => $test(`tab-${name}`);
  tab("lookout").click();
  await new Promise((resolve) => requestAnimationFrame(resolve));
  assert(tab("lookout").getAttribute("aria-selected") === "true" && !$test("panel-lookout").hidden && $test("panel-operations").hidden, "click activates the Lookout tab");
  const lookoutBounds = $test("lookout").getBoundingClientRect();
  const requestedDpr = Math.min(devicePixelRatio || 1, 3);
  const lookoutDpr = Math.min(requestedDpr, Math.sqrt(8000000 /
    Math.max(1, $test("lookout").clientWidth * $test("lookout").clientHeight)));
  assert(lookoutBounds.width > 100 && lookoutBounds.height > 50 &&
    $test("lookout").width === Math.round($test("lookout").clientWidth * lookoutDpr) &&
    $test("lookout").height === Math.round($test("lookout").clientHeight * lookoutDpr), "Lookout canvas has exact responsive backing dimensions");
  assert($test("lookout-sea").textContent === "3" && $test("lookout-light").textContent === "Day" &&
    $test("lookout-scope").dataset.light === "day", "snapshot environment drives Lookout status and palette");
  assert(lookoutFrame.arcs.filter((arc) => Math.abs(arc.radius - 4) < .01).length === 1 &&
    lookoutFrame.texts.includes(fixture.tracks[1].label) && !lookoutFrame.texts.includes(fixture.tracks[0].label),
    "positioned observations are points while bearing-only reports have no invented point or label position");
  const center = {x: lookoutBounds.width / 2, y: lookoutBounds.height / 2};
  const rings = lookoutFrame.arcs.filter((arc) => Math.abs((arc.end - arc.start) - Math.PI * 2) < .001 &&
    Math.abs(arc.x - center.x) < 1 && Math.abs(arc.y - center.y) < 1);
  const lookoutRadius = Math.max(...rings.map((ring) => ring.radius));
  const point = lookoutFrame.arcs.find((arc) => Math.abs(arc.radius - 4) < .01);
  const expectedScale = lookoutRadius / 100;
  assert(Math.abs(point.x - (center.x + 20 * expectedScale)) < 1 &&
    Math.abs(point.y - (center.y - 50 * expectedScale)) < 1, "positioned Lookout point uses equal north-up snapshot scale");
  const indicator = lookoutFrame.translations.find((entry) => Math.hypot(entry.x - center.x, entry.y - center.y) > 20);
  assert(indicator && Math.abs(indicator.x - (center.x + Math.sin(35 * Math.PI / 180) * lookoutRadius)) < 1 &&
    Math.abs(indicator.y - (center.y - Math.cos(35 * Math.PI / 180) * lookoutRadius)) < 1,
    "bearing-only report is marked at the correct nautical display edge");
  assert(lookoutFrame.rotations.some((angle) => Math.abs(angle - 15 * Math.PI / 180) < .001),
    "own course vector uses the published nautical heading");
  assert($test("lookout-observations").textContent.includes(fixture.tracks[0].label) &&
    $test("lookout-observations").textContent.includes("bearing-only observation") &&
    $test("lookout-own").textContent.includes("15"), "Lookout canvas has a current accessible text equivalent");
  fixture.environment.is_night = true;
  await until(() => $test("lookout-scope").dataset.light === "night" && $test("lookout-light").textContent === "Night", "night snapshot updates Lookout presentation");
  fixture.environment.is_night = false;
  await until(() => $test("lookout-scope").dataset.light === "day", "day snapshot restores Lookout presentation");
  const lookoutRange = $test("lookout-range").textContent;
  $test("lookout-zoom-in").click();
  await new Promise((resolve) => requestAnimationFrame(resolve));
  assert($test("lookout-range").textContent !== lookoutRange && $test("chart-scale").textContent === operationScale,
    "Lookout range is independent from Operations chart scale");
  $test("lookout-reset").click();
  $test("lookout").dispatchEvent(new WheelEvent("wheel", {deltaY: 1, bubbles: true, cancelable: true}));
  $test("lookout").dispatchEvent(new KeyboardEvent("keydown", {key: "Home", bubbles: true, cancelable: true}));
  await new Promise((resolve) => requestAnimationFrame(resolve));
  assert($test("lookout-range").textContent === lookoutRange && commands.length === commandsBeforeTabs,
    "Lookout controls remain browser-local and Home restores its default range");
  $test("lookout").style.width = "300px";
  $test("lookout").style.height = "180px";
  const resizedDpr = Math.min(requestedDpr, Math.sqrt(8000000 / (300 * 180)));
  await until(() => $test("lookout").clientWidth === 300 && $test("lookout").clientHeight === 180 &&
    $test("lookout").width === Math.round(300 * resizedDpr) && $test("lookout").height === Math.round(180 * resizedDpr),
    "active Lookout resize updates both backing dimensions");
  await new Promise((resolve) => requestAnimationFrame(resolve));
  const resizedRings = lookoutFrame.arcs.filter((arc) => Math.abs((arc.end - arc.start) - Math.PI * 2) < .001 &&
    Math.abs(arc.x - 150) < 1 && Math.abs(arc.y - 90) < 1);
  assert(resizedRings.length === 4 && Math.max(...resizedRings.map((ring) => ring.radius)) < 90,
    "Lookout geometry recenters after active resize");
  $test("lookout").style.removeProperty("width");
  $test("lookout").style.removeProperty("height");
  await until(() => $test("lookout").clientWidth > 300 && $test("lookout").height ===
    Math.round($test("lookout").clientHeight * Math.min(requestedDpr, Math.sqrt(8000000 /
      Math.max(1, $test("lookout").clientWidth * $test("lookout").clientHeight)))),
    "Lookout restores responsive backing dimensions after resize");
  await new Promise((resolve) => requestAnimationFrame(resolve));
  const restoredRings = lookoutFrame.arcs.filter((arc) => Math.abs((arc.end - arc.start) - Math.PI * 2) < .001 &&
    Math.abs(arc.x - $test("lookout").clientWidth / 2) < 1 && Math.abs(arc.y - $test("lookout").clientHeight / 2) < 1);
  assert(Math.abs(Math.max(...restoredRings.map((ring) => ring.radius)) - lookoutRadius) < 1,
    "Lookout geometry restores after responsive resize");
  assert($test("chart").width === 1 && $test("chart").height === 1, "inactive Operations canvas releases its backing store");
  tab("lookout").dispatchEvent(new KeyboardEvent("keydown", {key: "End", bubbles: true}));
  assert(document.activeElement === tab("contacts") && tab("contacts").getAttribute("aria-selected") === "true", "End activates the final tab");
  assert($test("lookout").width === 1 && $test("lookout").height === 1, "inactive Lookout canvas releases its backing store");
  await until(() => $test("analysis-list").querySelector("button"), "static contact analysis loads once");
  const operationSelection = $test("detail-label").textContent;
  const commandsBeforeAnalysis = commands.length;
  $test("analysis-list").querySelector("button").click();
  assert($test("analysis-name").textContent === "Reference Unit <inert>" &&
    $test("detail-label").textContent === operationSelection && first.getAttribute("aria-pressed") === "true",
    "analyzer selection is independent and uses inert text");
  $test("analysis-filter").value = "no-match";
  $test("analysis-filter").dispatchEvent(new Event("input"));
  assert(!$test("analysis-list").querySelector("button") && commands.length === commandsBeforeAnalysis,
    "analyzer filtering is bounded and never calls a command path");
  $test("analysis-filter").value = "";
  $test("analysis-filter").dispatchEvent(new Event("input"));
  tab("contacts").dispatchEvent(new KeyboardEvent("keydown", {key: "ArrowRight", bubbles: true}));
  assert(document.activeElement === tab("operations") && tab("operations").getAttribute("aria-selected") === "true", "Right arrow wraps to Operations");
  tab("operations").dispatchEvent(new KeyboardEvent("keydown", {key: "ArrowLeft", bubbles: true}));
  assert(document.activeElement === tab("contacts"), "Left arrow wraps to Contacts");
  tab("contacts").dispatchEvent(new KeyboardEvent("keydown", {key: "Home", bubbles: true}));
  await new Promise((resolve) => requestAnimationFrame(resolve));
  assert(document.activeElement === tab("operations") && !$test("panel-operations").hidden, "Home restores Operations");
  assert(first.getAttribute("aria-pressed") === "true" && $test("detail-label").textContent === fixture.tracks[0].label && $test("affiliation").value === "HOSTILE" && $test("navigation-course").value === "87.5", "tab round trip preserves selection and drafts");
  assert(commands.length === commandsBeforeTabs && $test("chart").width > 0 && $test("chart").height > 0, "tab switching sends no command and redraws Operations");
  tab("guide").click();
  await sleep(650);
  assert(tab("guide").getAttribute("aria-selected") === "true", "poll preserves active tab");
  const guidePanel = $test("panel-guide");
  guidePanel.scrollTop = 0;
  const commandsBeforeGuide = commands.length;
  $test("guide-nav").querySelector('a[href="#guide-authority"]').click();
  assert(guidePanel.scrollTop > 0 && document.activeElement === $test("guide-authority") &&
    window.scrollY === 0 && location.hash === "", "guide navigation scrolls and focuses only inside the Guide panel");
  assert(commands.length === commandsBeforeGuide, "guide navigation has no command coupling");
  $test("language").value = "de";
  $test("language").dispatchEvent(new Event("change"));
  await until(() => document.documentElement.lang === "de", "tab language switch");
  assert(tab("guide").getAttribute("aria-selected") === "true" &&
    $test("guide-authority").textContent.includes("niemals direkt steuern"),
    "language switch preserves and retranslates the active guide");
  $test("language").value = "en";
  $test("language").dispatchEvent(new Event("change"));
  await until(() => document.documentElement.lang === "en", "restore language after tab check");
  tab("operations").click();
  $test("apply-affiliation").click();
  await until(() => commands.length === 1, "explicit affiliation submit");
  await sleep(650);
  assert($test("command-status").dataset.status === "pending" && $test("propose").disabled, "202 is pending, one action at a time");
  assert(commands[0].action === "affiliate" && commands[0].value === "HOSTILE" && commands[0].track === "bearing-1", "exact annotation envelope");
  assert(commands[0].session === fixture.session && commands[0].epoch === fixture.epoch && Number.isInteger(commands[0].revision), "optimistic context envelope");
  assert(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(commands[0].id), "secure UUID");
  fixture.results = [{id: commands[0].id, status: "applied", reasoncode: "ok"}];
  await until(() => $test("command-status").dataset.status === "applied", "authoritative result settles pending");
  // Exercise the secure random fallback used on a plain HTTP LAN origin.
  Object.defineProperty(crypto, "randomUUID", {value: undefined, configurable: true});
  $test("classification").value = "";
  $test("apply-classification").click();
  await until(() => commands.length === 2, "explicit clear classification");
  assert(commands[1].action === "classify" && commands[1].value === null, "null classification is explicit");
  assert(commands[1].id !== commands[0].id && commands[1].id.length === 36, "secure fallback UUID");
  fixture.results.push({id: commands[1].id, status: "rejected", reasoncode: "revision_conflict"});
  await until(() => $test("command-status").dataset.status === "rejected", "rejection result");
  assert($test("command-status").textContent.includes("The assessment has changed."), "known reason code is meaningful English");
  $test("language").value = "de";
  $test("language").dispatchEvent(new Event("change"));
  await until(() => document.documentElement.lang === "de", "rejection language switch");
  assert($test("command-status").textContent.includes("Die Bewertung hat sich geaendert."), "stored reason code retranslates into German");
  $test("language").value = "en";
  $test("language").dispatchEvent(new Event("change"));
  await until(() => document.documentElement.lang === "en", "restore English after rejection check");
  $test("propose").click();
  await until(() => commands.length === 3, "proposal sent");
  assert(commands[2].action === "propose" && !("value" in commands[2]), "proposal has no invented value");
  assert(fixture.crew_target === "fix-2", "proposal never assigns crew target");
  await until(() => !$test("retry-command").disabled, "acknowledged command with no result becomes manually reconcilable");
  assert(commands.length === 3 && $test("propose").disabled && $test("command-status").dataset.status === "pending", "missing result never triggers resend or automatic unlock");
  fixture.proposal = {ref: "bearing-1", label: "Sierra 01", status: "pending"};
  fixture.results.push({id: commands[2].id, status: "applied", reasoncode: "ok"});
  await until(() => !$test("clear-proposal").disabled, "proposal can be cleared after result");
  $test("clear-proposal").click();
  await until(() => commands.length === 4, "clear proposal sent");
  assert(commands[3].action === "clear_proposal" && !("track" in commands[3]) && !("value" in commands[3]), "clear omits track and value");
  fixture.results.push({id: commands[3].id, status: "rejected", reasoncode: "queue_expired"});
  await until(() => !$test("propose").disabled, "authoritative expiry result releases pending action");
  assert($test("command-status").dataset.status === "rejected" && $test("command-status").textContent.includes("queue_expired"), "unknown expiry reason remains safe technical text");
  $test("sound").click();
  await until(() => $test("sound").getAttribute("aria-pressed") === "true", "sound enabled by gesture");
  assert(tones === 0, "enabling sound does not replay old events");
  fixture.events.push({seq: 2, kind: "sensor", severity: "warning", message: "New alarm"});
  await until(() => tones === 1, "new alert gets one tone");
  await sleep(650);
  assert(tones === 1, "event sequences deduplicated");
  offline = true;
  await until(() => $test("connection").dataset.state === "stale", "disconnect is stale");
  assert($test("propose").disabled, "stale actions disabled");
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  const frozen = $test("chart").toDataURL();
  const frozenSize = [$test("chart").width, $test("chart").height];
  await sleep(1100);
  assert($test("chart").toDataURL() === frozen, "no extrapolated motion while disconnected: " + frozenSize + " -> " + [$test("chart").width, $test("chart").height]);
  fixture.events.push({seq: 3, kind: "sensor", severity: "critical", message: "Reconnect backlog"});
  offline = false;
  window.dispatchEvent(new Event("online"));
  await until(() => $test("connection").dataset.state === "connected", "reconnect");
  assert(tones === 1, "no reconnect alert backlog");
  loseAck = true;
  $test("propose").click();
  await until(() => commands.length === 5 && $test("command-status").textContent.includes("uncertain"), "lost ack remains uncertain");
  loseAck = false;
  await sleep(1000);
  assert(commands.length === 5 && $test("propose").disabled, "uncertain command never auto retries or unlocks");
  await until(() => !$test("retry-command").disabled, "manual reconciliation available after cooldown");
  assert($test("command-retry-note").textContent.includes("first time") && $test("command-retry-note").textContent.includes("5 seconds"), "explicit first-application warning and retry rate");
  const originalEnvelope = issued.filter((entry) => entry.url === "/api/v1/commands").at(-1).options.body;
  $test("track-list").querySelectorAll("button")[1].click();
  $test("affiliation").value = "NEUTRAL";
  reconcileActor = true;
  $test("retry-command").click();
  for (let i = 0; i < 10; i++) $test("retry-command").dispatchEvent(new Event("click"));
  await until(() => commands.length === 6, "explicit retry reaches actor for the first time");
  assert(JSON.stringify(commands[5]) === originalEnvelope && actorEffects === 1, "retry preserves original ID/envelope despite changed selection and may first apply");
  assert(fixture.proposal.ref === "bearing-1" && fixture.crew_target === "fix-2", "actor changes only the original proposal, not crew target or new selection");
  await sleep(1000);
  assert(commands.length === 6 && $test("retry-command").disabled && $test("apply-affiliation").disabled, "in-flight and cooldown clicks cannot duplicate a request or unlock other actions");
  await until(() => !$test("retry-command").disabled, "next manual attempt after cooldown");
  rejectRetry = true;
  $test("retry-command").click();
  await until(() => commands.length === 7, "retry can be refused by HTTP transport");
  await sleep(100);
  assert($test("command-status").dataset.status === "pending" && $test("apply-affiliation").disabled && actorEffects === 1, "HTTP rejection of retry never erases an unresolved original action");
  rejectRetry = false;
  await until(() => !$test("retry-command").disabled, "reconcile again only after another cooldown");
  publishActorResults = true;
  $test("retry-command").click();
  await until(() => $test("command-status").dataset.status === "applied", "identical replay recovers authoritative result");
  assert(commands.length === 8 && actorEffects === 1 && actorResults.size === 1, "actor deduplicates repeat ID before current revision check");
  assert(commands.slice(4).every((command) => JSON.stringify(command) === originalEnvelope), "every manual attempt preserves all envelope fields and the original ID");
  assert($test("command-reconcile").hidden && !$test("apply-affiliation").disabled, "only authoritative result clears pending and retry UI");
  assert(localStorage.length === 0 && sessionStorage.length === 0 && !document.body.textContent.includes(commands[4].id), "cached reconciliation envelope stays in JS memory only");
  first.click();
  reconcileActor = false;
  stalledSeq = true;
  await until(() => $test("connection").dataset.state === "stale", "unchanging producer sequence is stale even with HTTP 200");
  assert($test("propose").disabled, "stalled producer locks actions");
  stalledSeq = false;
  await until(() => $test("connection").dataset.state === "connected", "producer recovery");
  holdState = true;
  const callsBeforeTimeout = stateCalls;
  await until(() => stateCalls > callsBeforeTimeout && lastSignal?.aborted, "stalled fetch aborted");
  assert($test("connection").dataset.state === "stale", "deadline marks stale");
  holdState = false;
  window.dispatchEvent(new Event("online"));
  await until(() => $test("connection").dataset.state === "connected", "timeout recovery");
  fixture.session = "session-B"; fixture.chart_revision = "chart-B";
  fixture.mission.name = "Second session"; mismatch = true;
  await until(() => $test("operations").hidden, "old session hidden before new chart");
  await sleep(1200);
  assert($test("operations").hidden, "mismatched chart cannot reveal data");
  mismatch = false;
  window.dispatchEvent(new Event("online"));
  await until(() => !$test("operations").hidden && $test("mission-name").textContent === "Second session", "new matching session committed");
  assert($test("track-detail").hidden, "selection resets across session");
  $test("language").value = "de";
  $test("language").dispatchEvent(new Event("change"));
  await until(() => document.documentElement.lang === "de", "German catalog switch");
  assert($test("pair-submit").textContent === "Station verbinden", "German labels from root catalog");
  assert(document.documentElement.scrollWidth <= innerWidth + 1, "German layout does not overflow");
  assert($test("damage-list").textContent.includes("Zugewiesene Teams (Anzahl)"), "team count label is localized in German");
  fixture.commands_allowed = false;
  await sleep(600);
  $test("track-list").querySelector("button").click();
  assert($test("propose").disabled && $test("apply-affiliation").disabled, "read only phase blocks commands");
  $test("follow").click();
  assert($test("follow").getAttribute("aria-pressed") === "true", "live ownship can be followed before redaction");
  const chartsBeforeBlocked = charts;
  const blockedSession = fixture.session, blockedRevision = fixture.chart_revision;
  Object.assign(fixture, structuredClone(statusFixture), {
    phase: "blocked", session: fixture.session, chart_revision: fixture.chart_revision,
    epoch: fixture.epoch + 1, seq: fixture.seq,
  });
  await until(() => !$test("operations").hidden && $test("mission-name").textContent === "" && $test("connection").dataset.state === "connected", "live to blocked status-only snapshot remains healthy");
  await sleep(50);
  assert(charts === chartsBeforeBlocked + 1 && fixture.session === blockedSession && fixture.chart_revision === blockedRevision, "blocked epoch replaces live chart at the same revision");
  assert($test("chart-disclaimer").textContent === "" && !$test("track-list").querySelector("button") && $test("track-detail").hidden, "blocked snapshot clears live chart and contact display");
  assert($test("follow").disabled && $test("follow").getAttribute("aria-pressed") === "false", "redaction cancels active follow");
  $test("follow").dispatchEvent(new Event("click"));
  $test("zoom-in").click();
  await sleep(50);
  assert(canvasFrame.texts.length > 0 && canvasFrame.translations.length === 0 && canvasFrame.fills === 0, "blocked geometry contains no previous or imaginary ownship");
  assert(!canvasFrame.texts.includes("Eigenes Schiff") && !canvasFrame.texts.includes("Eigener Hubschrauber"), "blocked geometry has no asset labels in German");
  tab("lookout").click();
  await new Promise((resolve) => requestAnimationFrame(resolve));
  assert($test("lookout-sea").textContent === "--" && $test("lookout-light").textContent === "--" &&
    lookoutFrame.arcs.length === 0 && lookoutFrame.translations.length === 0,
    "status-only redaction clears prior Lookout environment and geometry");
  assert($test("propose").disabled && $test("apply-classification").disabled && $test("apply-affiliation").disabled && $test("clear-proposal").disabled, "blocked status-only commands stay disabled");
  await sleep(650);
  assert($test("connection").dataset.state === "connected" && commands.length === 8, "blocked polling is healthy and sends no commands");
  assert(maxActive === 1, "at most one outstanding request");
  assert(!failures.length, "browser errors: " + failures.join("; "));
  Object.assign(fixture, structuredClone(liveFixture), {
    session: fixture.session, chart_revision: fixture.chart_revision,
    epoch: fixture.epoch + 1, seq: fixture.seq,
  });
  await until(() => $test("lookout-sea").textContent === "3" && $test("lookout-observations").children.length === 3,
    "live Lookout data returns before direct disconnect");
  $test("disconnect").click();
  assert($test("operations").hidden && !$test("pairing").hidden, "disconnect hides private data");
  assert($test("track-list").children.length === 0 && !$test("lookout-sea").textContent &&
    !$test("lookout-light").textContent && !$test("lookout-observations").textContent &&
    $test("lookout-scope").dataset.light === "unknown", "disconnect clears private DOM");
  document.documentElement.dataset.contract = "passed";
  if (parent !== window) parent.postMessage({contract: "passed"}, location.origin);
}
window.addEventListener("DOMContentLoaded", () => runContract().catch((error) => {
  document.documentElement.dataset.contract = "failed";
  document.documentElement.dataset.failure = String(error.stack || error);
  if (parent !== window) parent.postMessage({contract: "failed", failure: String(error.stack || error)}, location.origin);
}));
"""


def browser_state():
    tracks = []
    for ref, domain, x, y in [("bearing-1", "SUBSURFACE", None, None), ("fix-2", "SURFACE", 270, 200), ("air-3", "AIR", 320, 170)]:
        tracks.append(dict(ref=ref, label=f"{ref} <b>observed</b>", domain=domain,
                           source="PASSIVE" if x is None else "RADAR", affiliation="UNKNOWN",
                           classification=None, bearing=35, range_nm=None if x is None else 50,
                           x=x, y=y, depth_m=None, course=None, speed_kn=None,
                            quality=.65, age_s=2, fix_age_s=None if x is None else 2,
                            bearing_uncertainty_deg=5, range_uncertainty_nm=None,
                            fixes=[],
                            can_classify=domain == "SUBSURFACE", can_propose=domain == "SUBSURFACE"))
    tracks[1]["fixes"] = [dict(source="PING", x=290, y=220,
        measured_at=80, fixed_at=82, measurement_age_s=10, fix_age_s=8,
        uncertainty_nm=1.5, depth_m=70, depth_uncertainty_m=2, quality=.9)]
    return dict(protocol=1, version=APP_VERSION, session="session-A", epoch=1, revision=12,
                 seq=1, phase="live", commands_allowed=True, language="en",
                 clock=dict(sim=90, mission=90, time_scale=1, world=12.5),
                 environment=dict(sea_state=3, is_night=False),
                mission=dict(name="Northern watch <img src=x onerror=alert(1)>", objective="Maintain the observation picture", remaining_s=900),
                ownship=dict(x=250, y=250, course=15, speed=12, target_course=20, target_speed=15,
                             damage=[dict(key="bridge", name="Bridge", state="OK", flood=0, fire=0, teams=[1, 3]),
                                     dict(key="engine", name="Engine", state="OK", flood=0, fire=0, teams=[])],
                             inventory=dict(torpedoes=8, vls=16, ciws=800, chaff_ready=True),
                             helo=dict(state="HANGAR", x=None, y=None, course=None, fuel_s=1800, torpedoes=2, buoys=6)),
                tracks=tracks, crew_target="fix-2", proposal=None,
                events=[dict(seq=1, kind="mission", severity="warning", message="Initial backlog <b>inert</b>")],
                results=[], chart_revision="chart-A")


def browser_status_state():
    state = browser_state()
    state.update(phase="menu", commands_allowed=False,
                  clock={key: None for key in state["clock"]},
                  environment=dict(sea_state=None, is_night=None),
                 mission=dict(name="", objective="", remaining_s=None),
                 ownship=dict(x=None, y=None, course=None, speed=None,
                              target_course=None, target_speed=None, damage=[],
                              inventory={key: None for key in state["ownship"]["inventory"]},
                              helo={key: None for key in state["ownship"]["helo"]}),
                 tracks=[], crew_target=None, proposal=None, events=[], results=[])
    return state


def browser_contact_analysis():
    return dict(version=1, profiles=[dict(
        key="reference_unit", name="Reference Unit <inert>", resource="subs.json",
        reference=dict(variant="Test", variant_year=None, refit_year=None,
                       aliases=["Sample"], roles=["reference"], hull_type="single",
                       displacement_tonnes=2000, displacement_basis="submerged",
                       length_m=80, beam_waterline_m=None, beam_overall_m=9,
                       flight_deck_width_m=None, draft_m=7, ship_crew=None,
                       air_group_crew=None),
        machine=dict(cruise_speed_kn=8, maximum_speed_kn=18,
                      quiet_speed_kn=5, propulsion_codes=["DE"], motor_rpm=None,
                      shaft_rpm=None, propulsor_type="propeller", blade_count=None,
                      cruise_lines=[], high_speed_lines=[], cruise_broadband=None,
                      high_speed_broadband=None),
        components={key: [] for key in ("sensors", "emitters", "weapons", "launchers",
                                        "magazines", "countermeasures")},
        assets={},
    )])


@pytest.mark.parametrize("width,height", [(1920, 1080), (2560, 1440), (3840, 2160), (390, 844)])
def test_commander_browser_contract_when_chromium_available(tmp_path, width, height):
    chromium = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
    if not chromium:
        pytest.skip("Optional browser contract: no installed Chromium")
    html = ASSETS.joinpath("index.html").read_text().replace(
        '<script src="./app.js" defer>', '<script src="./contract.js" defer></script><script src="./app.js" defer>')
    script = (BROWSER_CONTRACT.replace("__STATE__", json.dumps(browser_state()))
              .replace("__STATUS_STATE__", json.dumps(browser_status_state()))
              .replace("__WIDTH__", str(width)))
    requests = []
    problems = []
    en, de = catalogs()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def reply(self, status, content, mime):
            content = content.encode()
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            if self.path == "/viewport":
                # Desktop Chromium has a 500px minimum window. A same-origin
                # fixture frame gives the app a real 390px CSS viewport instead.
                self.reply(200, f'<!doctype html><html><head><script src="/viewport.js" defer></script></head>'
                           f'<body><iframe src="/" width="{width}" height="{height}" frameborder="0"></iframe></body></html>', "text/html")
            elif self.path == "/viewport.js":
                self.reply(200, 'window.addEventListener("message", (event) => {'
                           'if (event.origin === location.origin && event.data?.contract) {'
                           'document.documentElement.dataset.contract = event.data.contract;'
                           'document.documentElement.dataset.failure = event.data.failure || "";'
                           '}});', "text/javascript")
            elif self.path in ("/", "/index.html"):
                self.reply(200, html, "text/html")
            elif self.path == "/contract.js":
                self.reply(200, script, "text/javascript")
            elif self.path in ("/app.js", "/style.css"):
                self.reply(200, ASSETS.joinpath(self.path[1:]).read_text(), "text/javascript" if self.path.endswith("js") else "text/css")
            elif self.path in ("/api/v1/ui?lang=en", "/api/v1/ui?lang=de"):
                source = de if self.path.endswith("de") else en
                self.reply(200, json.dumps({key: value for key, value in source.items() if key.startswith(PREFIX)}), "application/json")
            elif self.path == "/api/v1/contacts":
                self.reply(200, json.dumps(browser_contact_analysis()), "application/json")
            else:
                self.reply(404, "", "text/plain")

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, body))
            if self.headers.get("Origin") != f"http://127.0.0.1:{self.server.server_port}":
                problems.append("Browser did not supply same-origin Origin on POST")
            if self.path == "/api/v1/pair":
                if body != {"code": "123ABC"}:
                    problems.append("Incorrect pairing envelope")
                if len([path for path, _ in requests if path == "/api/v1/pair"]) == 1:
                    self.reply(429, json.dumps({"error": "rate_limited"}), "application/json")
                else:
                    self.reply(200, json.dumps({"token": "test-secret"}), "application/json")
            elif self.path == "/api/v1/commands":
                if self.headers.get("Authorization") != "Bearer test-secret":
                    problems.append("Missing command authorization")
                self.reply(202, "", "application/json")
            else:
                self.reply(404, "", "text/plain")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(
            [chromium, "--headless", "--no-sandbox", "--disable-gpu", "--disable-background-networking",
             "--no-first-run", "--no-default-browser-check", "--disable-dev-shm-usage",
             f"--user-data-dir={tmp_path / 'browser'}", f"--window-size={width},{height}",
             "--force-device-scale-factor=1.5", "--virtual-time-budget=90000", "--dump-dom",
             f"http://127.0.0.1:{server.server_port}/{'viewport' if width < 500 else ''}"],
            capture_output=True, text=True, timeout=60,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert result.returncode == 0, result.stderr
    document = Document(result.stdout)
    root = next((attrs for tag, attrs in document.elements if tag == "html"), {})
    assert root.get("data-contract") == "passed", root.get("data-failure", result.stdout[-5000:] + result.stderr[-2000:])
    assert not problems
    assert [body for path, body in requests if path == "/api/v1/pair"] == [{"code": "123ABC"}, {"code": "123ABC"}]
    assert len([path for path, _ in requests if path == "/api/v1/commands"]) == 6


def test_contact_analyzer_rejects_schema_error_when_chromium_available(tmp_path):
    chromium = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
    if not chromium:
        pytest.skip("Optional browser contract: no installed Chromium")
    html = ASSETS.joinpath("index.html").read_text().replace(
        '<script src="./app.js" defer>',
        '<script src="./schema-test.js" defer></script><script src="./app.js" defer>')
    en = catalogs()[0]
    requests = []
    malformed_analysis = project_contact_catalog()
    malformed_analysis["profiles"][0]["reference"] = None
    probe = r"""
window.addEventListener("DOMContentLoaded", async () => {
  for (let i = 0; !document.getElementById("analysis-status").textContent.includes("unavailable or invalid") && i < 300; i++)
    await new Promise((resolve) => setTimeout(resolve, 20));
  const status = document.getElementById("analysis-status");
  document.documentElement.dataset.schema = status.textContent.includes("unavailable or invalid") &&
    !document.getElementById("analysis-list").children.length ? "rejected" : "failed";
});
"""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def reply(self, content, mime="application/json"):
            body = content.encode()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            requests.append(self.path)
            if self.path == "/":
                self.reply(html, "text/html")
            elif self.path == "/schema-test.js":
                self.reply(probe, "text/javascript")
            elif self.path in ("/app.js", "/style.css"):
                mime = "text/javascript" if self.path.endswith("js") else "text/css"
                self.reply(ASSETS.joinpath(self.path[1:]).read_text(), mime)
            elif self.path == "/api/v1/ui?lang=en":
                self.reply(json.dumps({key: value for key, value in en.items()
                                       if key.startswith(PREFIX)}))
            elif self.path == "/api/v1/contacts":
                self.reply(json.dumps(malformed_analysis))
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
             f"--user-data-dir={tmp_path / 'browser'}", "--virtual-time-budget=10000",
             "--dump-dom", f"http://127.0.0.1:{server.server_port}/"],
            capture_output=True, text=True, timeout=30,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert result.returncode == 0, result.stderr
    root = next(attrs for tag, attrs in Document(result.stdout).elements if tag == "html")
    assert root.get("data-schema") == "rejected"
    assert requests.count("/api/v1/contacts") == 1
    assert not any(path == "/api/v1/commands" for path in requests)
