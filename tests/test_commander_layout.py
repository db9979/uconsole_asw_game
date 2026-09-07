"""Dense Commander layout regression, using optional installed Chromium only."""

import json
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from test_commander_assets import ASSETS, PREFIX, Document, browser_state, catalogs


LAYOUT_SCENARIO = r"""
const $ = (id) => document.getElementById(id);
const failures = [];
window.addEventListener("error", (event) => failures.push(event.message));
window.addEventListener("unhandledrejection", (event) => failures.push(String(event.reason)));
window.requestAnimationFrame = (callback) => setTimeout(() => callback(performance.now()), 16);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
let sector;
const strokeRect = CanvasRenderingContext2D.prototype.strokeRect;
CanvasRenderingContext2D.prototype.strokeRect = function (x, y, width, height) {
  if (this.getLineDash().length) sector = {x, y, width, height};
  return strokeRect.call(this, x, y, width, height);
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
  const selectors = [".workspace", ".contacts-panel", ".chart-panel", "#chart", ".details-panel", ".support-grid"];
  const boxes = Object.fromEntries(selectors.map((selector) => [selector, rect(document.querySelector(selector))]));
  const panels = [...document.querySelectorAll(".workspace > .panel, .support-grid > .panel")];
  const intersections = [];
  panels.forEach((a, i) => panels.slice(i + 1).forEach((b) => {
    const x = rect(a), y = rect(b);
    if (Math.min(x.right, y.right) - Math.max(x.x, y.x) > 1 &&
        Math.min(x.bottom, y.bottom) - Math.max(x.y, y.y) > 1) intersections.push([a.className, b.className]);
  }));
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
  window.scrollTo(0, 0);
  parent.scrollTo(0, 0);
  const frozen = $("chart").toDataURL();
  await sleep(700);
  const report = {
    width: innerWidth, height: innerHeight, boxes, sector, intersections, scrolls, keyboardReachable,
    pageWidth: document.documentElement.scrollWidth, contacts: $("track-list").children.length,
    damage: $("damage-list").children.length, errors: failures,
    stable: frozen === $("chart").toDataURL(),
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
    assert report["keyboardReachable"] and report["stable"]
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
