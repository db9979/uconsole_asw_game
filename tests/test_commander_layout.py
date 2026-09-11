"""Dense Commander layout regression, using optional installed Chromium only."""

import json
import shutil
import subprocess
import threading
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock

import pygame
import pytest

from src.commander import local
from src.core.game import Game
from src.core.i18n import Translator, load_catalog, pseudolocale
from src.ui import layout
from test_commander_assets import (ASSETS, PREFIX, Document, browser_contact_analysis,
                                   browser_state, catalogs)


LAYOUT_SCENARIO = r"""
const $ = (id) => document.getElementById(id);
const failures = [];
window.addEventListener("error", (event) => failures.push(event.message));
window.addEventListener("unhandledrejection", (event) => failures.push(String(event.reason)));
window.requestAnimationFrame = (callback) => setTimeout(() => callback(performance.now()), 16);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
let sector;
let lookoutArcs = [];
const strokeRect = CanvasRenderingContext2D.prototype.strokeRect;
CanvasRenderingContext2D.prototype.strokeRect = function (x, y, width, height) {
  if (this.getLineDash().length) sector = {x, y, width, height};
  return strokeRect.call(this, x, y, width, height);
};
const arc = CanvasRenderingContext2D.prototype.arc;
CanvasRenderingContext2D.prototype.arc = function (x, y, radius, start, end, ...rest) {
  if (this.canvas.id === "lookout") lookoutArcs.push({x, y, radius, start, end});
  return arc.call(this, x, y, radius, start, end, ...rest);
};
async function run() {
  for (let i = 0; $("shell").hidden && i < 300; i++) await sleep(20);
  $("code").value = "123ABC";
  $("pair-form").requestSubmit();
  for (let i = 0; $("operations").hidden && i < 300; i++) await sleep(20);
  $("track-list").querySelector("button").click();
  await sleep(100);
  const rect = (element) => {
    const r = element.getBoundingClientRect();
    return {x: r.x, y: r.y, width: r.width, height: r.height, bottom: r.bottom, right: r.right};
  };
  const overlap = (a, b) => Math.min(a.right, b.right) - Math.max(a.x, b.x) > 1 &&
    Math.min(a.bottom, b.bottom) - Math.max(a.y, b.y) > 1;
  const selectors = [".workspace", ".contacts-panel", ".chart-panel", "#chart", ".details-panel", ".support-grid"];
  const boxes = Object.fromEntries(selectors.map((selector) => [selector, rect(document.querySelector(selector))]));
  const panels = [...document.querySelectorAll(".workspace > .panel, .support-grid > .panel")];
  const intersections = [];
  panels.forEach((a, i) => panels.slice(i + 1).forEach((b) => {
    const x = rect(a), y = rect(b);
    if (overlap(x, y)) intersections.push([a.className, b.className]);
  }));
  const navigationControls = [...$("navigation-form").querySelectorAll("label, input, button")];
  const navigationIntersections = [];
  navigationControls.forEach((a, i) => navigationControls.slice(i + 1).forEach((b) => {
    if (overlap(rect(a), rect(b))) navigationIntersections.push([a.id || a.htmlFor, b.id || b.htmlFor]);
  }));
  const navigationLabels = ["navigation-course", "navigation-speed"].every((id) =>
    document.querySelector(`label[for="${id}"]`)?.control === $(id));
  const navigationControlSize = ["navigation-course", "navigation-speed", "propose-navigation"].every((id) => {
    const bounds = rect($(id));
    return bounds.width > 50 && bounds.height >= parseFloat(getComputedStyle(document.documentElement).fontSize) * 2.5;
  });
  const scrolls = {};
  for (const selector of ["#track-list", ".details-panel", "#damage-list", "#event-list"]) {
    const element = document.querySelector(selector);
    const before = rect(element);
    const owner = rect(element.closest(".panel"));
    element.scrollTop = element.scrollHeight;
    scrolls[selector] = {
      height: element.clientHeight, content: element.scrollHeight, moved: element.scrollTop > 0,
      contained: before.y >= owner.y - 1 && before.bottom <= owner.bottom + 1,
      overflow: getComputedStyle(element).overflowY,
    };
    element.scrollTop = 0;
  }
  const last = $("track-list").lastElementChild;
  $("track-list").firstElementChild.focus();
  $("track-list").firstElementChild.dispatchEvent(new KeyboardEvent("keydown", {key: "End", bubbles: true}));
  const visible = Math.min(rect(last).bottom, rect($("track-list")).bottom) - Math.max(rect(last).y, rect($("track-list")).y);
  const keyboardReachable = document.activeElement === last && visible > 50;
  $("track-list").scrollTop = 0;
  $("propose-navigation").scrollIntoView({block: "nearest"});
  $("propose-navigation").focus();
  const navigationAction = rect($("propose-navigation"));
  const detailBounds = rect(document.querySelector(".details-panel"));
  const navigationReachable = document.activeElement === $("propose-navigation") &&
    navigationAction.y >= detailBounds.y - 1 && navigationAction.bottom <= detailBounds.bottom + 1;
  document.querySelector(".details-panel").scrollTop = 0;
  const operationsPanel = $("panel-operations");
  const supportReachable = [...document.querySelectorAll(".support-grid > .panel")].every((panel) => {
    panel.scrollIntoView({block: "start"});
    const bounds = rect(panel);
    const owner = rect(operationsPanel);
    return bounds.y >= owner.y - 1 && bounds.y < owner.bottom - 40;
  });
  document.querySelector("footer").scrollIntoView({block: "end"});
  const footerBounds = rect(document.querySelector("footer"));
  const panelBounds = rect(operationsPanel);
  const footerReachable = footerBounds.y < panelBounds.bottom && footerBounds.bottom > panelBounds.y;
  operationsPanel.scrollTop = Math.min(123, operationsPanel.scrollHeight - operationsPanel.clientHeight);
  const operationScroll = operationsPanel.scrollTop;
  $("tab-lookout").click();
  await new Promise((resolve) => requestAnimationFrame(resolve));
  const inactiveHidden = operationsPanel.hidden && !$("panel-lookout").hidden;
  const lookoutPanel = $("panel-lookout");
  const lookoutCanvas = $("lookout");
  const lookoutChildren = [document.querySelector(".lookout-bar"), $("lookout-scope"), $("lookout-note")];
  const lookoutIntersections = [];
  lookoutChildren.forEach((a, i) => lookoutChildren.slice(i + 1).forEach((b) => {
    if (overlap(rect(a), rect(b))) lookoutIntersections.push([a.className, b.className]);
  }));
  const lookoutBounds = rect(lookoutPanel);
  const lookoutPlot = rect(lookoutCanvas);
  const lookoutControls = [$("lookout-zoom-in"), $("lookout-zoom-out"), $("lookout-reset")];
  $("lookout-reset").focus();
  const lookout = {
    panel: lookoutBounds, plot: lookoutPlot,
    contained: lookoutChildren.every((element) => {
      const bounds = rect(element);
      return bounds.x >= lookoutBounds.x - 1 && bounds.right <= lookoutBounds.right + 1 &&
        bounds.y >= lookoutBounds.y - 1 && bounds.bottom <= lookoutBounds.bottom + 1;
    }),
    intersections: lookoutIntersections,
    controls: lookoutControls.every((control) => {
      const bounds = rect(control);
      return bounds.width > 20 && bounds.height >= 24 && !control.disabled;
    }),
    focus: document.activeElement === $("lookout-reset"),
    backing: [lookoutCanvas.width, lookoutCanvas.height],
    client: [lookoutCanvas.clientWidth, lookoutCanvas.clientHeight],
    overflow: getComputedStyle(lookoutPanel).overflowY,
    panelScroll: lookoutPanel.scrollHeight - lookoutPanel.clientHeight,
    pageHeight: document.documentElement.scrollHeight,
    pageWidth: document.documentElement.scrollWidth,
    pageScroll: window.scrollY,
    rings: lookoutArcs.filter((entry) => Math.abs(entry.x - lookoutCanvas.clientWidth / 2) < 1 &&
      Math.abs(entry.y - lookoutCanvas.clientHeight / 2) < 1).map((entry) => entry.radius),
  };
  $("tab-guide").click();
  const guidePanel = $("panel-guide");
  guidePanel.scrollTop = 0;
  $("guide-nav").querySelector('a[href="#guide-authority"]').click();
  const guideBounds = rect(guidePanel);
  const guide = {
    overflow: getComputedStyle(guidePanel).overflowY,
    moved: guidePanel.scrollTop > 0,
    focus: document.activeElement === $("guide-authority"),
    contained: [...guidePanel.querySelectorAll(".guide-nav, .guide-copy section")].every((element) => {
      const bounds = rect(element);
      return bounds.x >= guideBounds.x - 1 && bounds.right <= guideBounds.right + 1;
    }),
    links: [...$("guide-nav").querySelectorAll("a")].every((link) => {
      const bounds = rect(link);
      return bounds.width > 30 && bounds.height > 20;
    }),
    pageHeight: document.documentElement.scrollHeight,
    pageWidth: document.documentElement.scrollWidth,
    pageScroll: window.scrollY,
  };
  $("tab-contacts").click();
  for (let i = 0; !$('analysis-list').querySelector('button') && i < 300; i++) await sleep(20);
  $('analysis-list').querySelector('button')?.click();
  const analyzerPanel = $('panel-contacts');
  const analyzerList = $('analysis-list');
  const analyzerDetail = document.querySelector('.analyzer-detail');
  analyzerList.scrollTop = analyzerList.scrollHeight;
  analyzerDetail.scrollTop = analyzerDetail.scrollHeight;
  const analyzer = {
    panelOverflow: getComputedStyle(analyzerPanel).overflowY,
    panelScroll: analyzerPanel.scrollHeight - analyzerPanel.clientHeight,
    listOverflow: getComputedStyle(analyzerList).overflowY,
    listMoved: analyzerList.scrollTop > 0,
    detailOverflow: getComputedStyle(analyzerDetail).overflowY,
    detailMoved: analyzerDetail.scrollTop > 0,
    pageHeight: document.documentElement.scrollHeight,
    pageWidth: document.documentElement.scrollWidth,
  };
  $("tab-operations").click();
  await new Promise((resolve) => requestAnimationFrame(resolve));
  const panelScrollPreserved = operationsPanel.scrollTop === operationScroll;
  const tabs = [...document.querySelectorAll('[role="tab"]')];
  const tabIntersections = [];
  tabs.forEach((a, i) => tabs.slice(i + 1).forEach((b) => {
    if (overlap(rect(a), rect(b))) tabIntersections.push([a.id, b.id]);
  }));
  const pageHeight = document.documentElement.scrollHeight;
  const pageScroll = window.scrollY;
  operationsPanel.scrollTop = 0;
  parent.scrollTo(0, 0);
  const frozen = $("chart").toDataURL();
  await sleep(700);
  const report = {
    width: innerWidth, height: innerHeight, boxes, sector, intersections, scrolls, keyboardReachable,
    navigationIntersections, navigationLabels, navigationControlSize, navigationReachable,
    supportReachable, footerReachable, pageHeight, pageScroll, operationScroll,
    panelHeight: operationsPanel.clientHeight, panelOverflow: getComputedStyle(operationsPanel).overflowY,
    panelScrollPreserved, inactiveHidden, tabIntersections, lookout,
    pageWidth: document.documentElement.scrollWidth, contacts: $("track-list").children.length,
    damage: $("damage-list").children.length, errors: failures,
    stable: frozen === $("chart").toDataURL(), guide, analyzer,
  };
  parent.postMessage({layout: report}, location.origin);
}
window.addEventListener("DOMContentLoaded", () => run().catch((error) => {
  parent.postMessage({layout: {error: String(error.stack || error)}}, location.origin);
}));
"""


@pytest.mark.parametrize("width,height", [(1920, 1080), (2560, 1440), (3840, 2160), (1280, 720), (390, 844)])
@pytest.mark.parametrize("zoom", [1, 2], ids=["100pct", "200pct-reflow"])
@pytest.mark.parametrize("language", ["en", "de"])
def test_dense_commander_layout(tmp_path, width, height, zoom, language):
    chromium = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
    if not chromium:
        pytest.skip("Optional layout regression: no installed Chromium")
    # Browser zoom halves the CSS viewport and doubles physical pixels. Use a
    # same-origin frame for exact reflow, including below Chromium's 500px minimum.
    css_width, css_height = width // zoom, height // zoom
    state = browser_state()
    state["ownship"].update(x=180, y=320)
    prototype = state["tracks"][1]
    state["tracks"] = [dict(prototype, ref=f"fix-{i}", label=f"Contact-{i}-" + "LongUnbrokenLabel" * 6,
                            x=30 + i % 12 * 40, y=30 + i // 12 * 40,
                            source="LongUnbrokenSource" * 6) for i in range(120)]
    state["ownship"]["damage"] = [dict(key=f"room-{i}", name=f"Compartment-{i}-" + "LongDamageLabel" * 8,
                                       state="BESCHAEDIGT", flood=12, fire=9, teams=[1, 3]) for i in range(9)]
    state["events"] = [dict(seq=i, kind="sensor", severity="warning", message="LongEventMessage" * 20)
                       for i in range(1, 81)]
    state["mission"].update(name="Long mission name " * 6, objective="LongObjective" * 12)
    chart = dict(revision=state["chart_revision"], size_nm=500,
                 landmasses=[dict(points=[[20, 20], [160, 40], [90, 160]])],
                 disclaimer="Synthetic test geography, not real bathymetry. " * 4)
    catalog = catalogs()[language == "de"]
    analysis = browser_contact_analysis()
    prototype = analysis["profiles"][0]
    prototype["reference"]["roles"] = ["LongReferenceRole" * 7 for _ in range(64)]
    analysis["profiles"] = [dict(prototype, key=f"reference_{index}",
                                 name=f"Reference profile {index}") for index in range(160)]
    html = ASSETS.joinpath("index.html").read_text().replace(
        '<script src="./app.js" defer>', '<script src="./layout.js" defer></script><script src="./app.js" defer>')

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
            if self.path == "/viewport":
                self.reply(f'<!doctype html><html><head><script src="/viewport.js" defer></script></head>'
                           f'<body style="margin:0"><iframe src="/" width="{css_width}" height="{css_height}" '
                           f'style="border:0;transform:scale({zoom});transform-origin:top left"></iframe></body></html>', "text/html")
            elif self.path == "/viewport.js":
                self.reply('window.addEventListener("message", (event) => {'
                           'if (event.origin === location.origin && event.data?.layout) '
                           'document.documentElement.dataset.layout = JSON.stringify(event.data.layout);});', "text/javascript")
            elif self.path == "/":
                self.reply(html, "text/html")
            elif self.path == "/layout.js":
                self.reply(LAYOUT_SCENARIO, "text/javascript")
            elif self.path in ("/app.js", "/style.css"):
                self.reply(ASSETS.joinpath(self.path[1:]).read_text(), "text/javascript" if self.path.endswith("js") else "text/css")
            elif self.path.startswith("/api/v1/ui?"):
                self.reply(json.dumps({key: value for key, value in catalog.items() if key.startswith(PREFIX)}))
            elif self.path == "/api/v1/state":
                state["seq"] += 1
                self.reply(json.dumps(state))
            elif self.path == "/api/v1/chart":
                self.reply(json.dumps(chart))
            elif self.path == "/api/v1/contacts":
                self.reply(json.dumps(analysis))
            else:
                self.send_error(404)

        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            if self.path == "/api/v1/pair":
                self.reply(json.dumps({"token": "layout-test-token"}))
            else:
                self.send_error(405)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(
            [chromium, "--headless", "--no-sandbox", "--disable-gpu", "--disable-background-networking",
             "--no-first-run", "--no-default-browser-check", "--disable-dev-shm-usage",
             f"--user-data-dir={tmp_path / 'browser'}", f"--window-size={width},{height}",
             "--force-device-scale-factor=1", "--virtual-time-budget=5000", "--dump-dom",
             f"http://127.0.0.1:{server.server_port}/viewport"],
            capture_output=True, text=True, timeout=45,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert result.returncode == 0, result.stderr
    document = Document(result.stdout)
    root = next(attrs for tag, attrs in document.elements if tag == "html")
    assert "data-layout" in root, result.stdout[-3000:]
    report = json.loads(root["data-layout"])
    (tmp_path / "layout.json").write_text(json.dumps(report, indent=2))
    print(f"{language} {width}x{height} {zoom}x: {json.dumps(report)}")
    assert "error" not in report, report
    assert not report["errors"]
    assert report["contacts"] == 120 and report["damage"] == 9
    assert report["width"] == css_width and report["height"] == css_height
    assert report["pageWidth"] <= css_width + 1
    assert not report["intersections"]
    assert not report["navigationIntersections"]
    assert report["navigationLabels"] and report["navigationControlSize"]
    assert report["keyboardReachable"] and report["navigationReachable"]
    assert report["supportReachable"] and report["footerReachable"]
    assert report["pageHeight"] <= css_height + 1
    assert report["pageScroll"] == 0
    assert report["panelHeight"] > 50 and report["panelOverflow"] == "auto"
    assert report["operationScroll"] > 0 and report["panelScrollPreserved"]
    assert report["inactiveHidden"] and not report["tabIntersections"]
    lookout = report["lookout"]
    assert lookout["contained"] and not lookout["intersections"]
    assert lookout["controls"] and lookout["focus"]
    assert lookout["plot"]["width"] > 50 and lookout["plot"]["height"] > 30
    assert lookout["backing"] == lookout["client"]
    assert lookout["overflow"] == "hidden" and lookout["panelScroll"] <= 1
    assert lookout["pageWidth"] <= css_width + 1 and lookout["pageHeight"] <= css_height + 1
    assert lookout["pageScroll"] == 0
    rings = sorted(set(round(radius, 3) for radius in lookout["rings"]))
    if lookout["client"][1] < 120:
        assert len(rings) >= 2 and rings[-1] > 15
        assert rings[-1] - rings[-2] > 7
    else:
        assert len(rings) >= 4
    assert max(rings) <= min(lookout["client"]) / 2 + 1
    assert report["stable"]
    guide = report["guide"]
    assert guide["overflow"] == "auto" and guide["moved"] and guide["focus"]
    assert guide["contained"] and guide["links"]
    assert guide["pageWidth"] <= css_width + 1 and guide["pageHeight"] <= css_height + 1
    assert guide["pageScroll"] == 0
    analyzer = report["analyzer"]
    assert analyzer["panelOverflow"] == "hidden" and analyzer["panelScroll"] <= 1
    assert analyzer["listOverflow"] == analyzer["detailOverflow"] == "auto"
    assert analyzer["listMoved"] and analyzer["detailMoved"]
    assert analyzer["pageWidth"] <= css_width + 1 and analyzer["pageHeight"] <= css_height + 1
    for selector, scroll in report["scrolls"].items():
        assert scroll["height"] > 50, selector
        assert scroll["contained"] and scroll["overflow"] == "auto", (selector, scroll)
        assert scroll["moved"] == (scroll["content"] > scroll["height"]), (selector, scroll)
    boxes = report["boxes"]
    plot = boxes["#chart"]
    assert plot["bottom"] <= boxes[".chart-panel"]["bottom"]
    assert abs(report["sector"]["width"] - report["sector"]["height"]) < .01
    assert abs(report["sector"]["width"] - min(plot["width"], plot["height"]) * .9) < 2
    assert abs(report["sector"]["x"] + report["sector"]["width"] / 2 - plot["width"] / 2) < 1
    assert abs(report["sector"]["y"] + report["sector"]["height"] / 2 - plot["height"] / 2) < 1
    if css_width > 1500:
        assert .70 * css_height <= plot["height"] <= .75 * css_height
        assert plot["width"] > .60 * css_width
    else:
        assert boxes[".chart-panel"]["bottom"] <= boxes[".contacts-panel"]["y"]
        assert boxes[".chart-panel"]["bottom"] <= boxes[".details-panel"]["y"]


@pytest.mark.parametrize(("width", "height", "zoom"), [
    (844, 390, 1), (844, 390, 2), (1280, 1024, 4),
])
@pytest.mark.parametrize("language", ["en", "de"])
def test_short_landscape_and_400_percent_lookout_layout(
        tmp_path, width, height, zoom, language):
    test_dense_commander_layout(tmp_path, width, height, zoom, language)


@pytest.mark.parametrize("language", ["en", "de", "pseudo"])
@pytest.mark.parametrize("large", [False, True])
@pytest.mark.parametrize("kind", ["target", "navigation"])
def test_native_crew_confirmation_layout_is_bounded(language, large, kind, monkeypatch):
    game = Game(seed=73, audio_enabled=False, language="en")
    try:
        game.preferences = replace(game.preferences, large_text=large)
        game.translator = Translator("en")
        if language == "pseudo":
            game.translator.catalog = pseudolocale(load_catalog("en"))
        elif language == "de":
            game.translator = Translator("de")
        game.tr = game.translator.t
        game._apply_text_size()
        console = game.commander
        console.address = ("192.168.100.200", 65535)
        console.server = type("Server", (), {
            "connected": True, "stop": lambda self: None,
        })()
        console.bridge._allowed = True
        console.bridge._proposal = dict(
            ref="ref", label="{authored} " + "K" * 256, status="pending")
        console.bridge._navigation_proposal = dict(
            course=359.999, speed_kn=25.0, status="pending")
        console.bridge._pending_seq = 9
        console._confirm_signature, _ = console._confirmation_state()
        console._confirm_identity = (id(game.world), id(game.sonar))
        console._confirm_requested = True
        console.confirm_kind = kind
        monkeypatch.setattr(local, "load_catalog", Mock(
            side_effect=AssertionError("draw I/O")))
        with layout.capture_text() as text:
            console.draw_confirm(game)
        canvas = pygame.Rect(0, 0, 1280, 720)
        assert text
        assert canvas.contains(console.confirm_rect())
        assert all(canvas.contains(rect) for rect in console.confirm_button_rects())
        for entry in text:
            assert canvas.contains(entry["bounds"]), entry
            assert entry["bounds"].contains(entry["rect"]), entry
            assert "commander.confirm" not in entry["text"], entry
    finally:
        game.commander.stop()
        game.audio.shutdown()
        layout.configure_for(large_text=False)
