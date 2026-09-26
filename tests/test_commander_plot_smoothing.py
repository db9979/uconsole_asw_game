"""Browser waterfalls scroll smoothly although sonar data is published at 2 Hz."""

import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from commander_web import module_source
from test_commander_assets import Document


SCRIPT = r"""
let clock = 0;
const performance = {now: () => clock};
const finite = Number.isFinite;
const S = {v2State: null, connected: true};
const sonarDisplay = {black: 0, contrast: 1, history: 300, palette: "green", demonCursor: null};
const heatmapRasters = new Map();
const registerAnimatedPlot = () => {};
const drawEmpty = () => { throw new Error("waterfall drawn empty"); };
const heatmapPalette = () => Uint32Array.from({length: 256}, (_, index) => ((255 << 24) | (index << 8)) >>> 0);
const canvas = document.createElement("canvas");
canvas.width = 300; canvas.height = 200;
document.body.append(canvas);
const plotContext = canvas.getContext("2d");
const visualContext = () => ({element: canvas, context: plotContext, width: 300, height: 200});
const plotAxes = (plot) => ({...plot, width: 300, height: 200});
let rasterBuilds = 0;
const nativePut = CanvasRenderingContext2D.prototype.putImageData;
CanvasRenderingContext2D.prototype.putImageData = function (...args) { rasterBuilds++; return nativePut.apply(this, args); };
__CLOCK__
__HEATMAP__
__SPECTRUM__
const check = (ok, label) => { if (!ok) throw new Error(label); };
const state = (sim, phase = "live", epoch = 1) =>
  ({session: "s", epoch, phase, clock: {sim}});

// Deterministic 0-0.2 s arrival jitter on 2 Hz publications.
let seed = 4242;
const random = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;

function smoothClock() {
  displayClock.context = null;
  clock = 10000;
  const start = clock;
  const arrivals = [];
  for (let publish = 0; publish < 80; publish++) arrivals.push({wall: start + publish * 500 + random() * 200, sim: publish * .5});
  let previous = null, newest = -Infinity;
  for (let frame = 0; frame < 60 * 38; frame++) {
    clock = start + frame * 1000 / 60;
    while (arrivals.length && arrivals[0].wall <= clock) {
      const sample = arrivals.shift();
      newest = Math.max(newest, sample.sim);
      sampleDisplayClock(state(sample.sim), sample.sim);
    }
    const shown = displaySimNow(clock);
    const truth = (clock - start) / 1000;
    if (frame > 120) {
      const step = shown - previous, nominal = 1 / 60;
      check(step >= nominal * .85 && step <= nominal * 1.15, `uneven frame step ${step} (nominal ${nominal})`);
      check(shown <= newest, `display clock ${shown} ran past published data ${newest}`);
      check(truth - shown < 2, `display clock lags ${truth - shown}`);
    }
    previous = shown;
  }
}

try {
  smoothClock();

  // An ended mission (no world running) stands still; there is no pause.
  displayClock.context = null;
  clock = 0;
  sampleDisplayClock(state(50, "ended"));
  const ended = displaySimNow(clock);
  for (let frame = 1; frame <= 120; frame++) { clock = frame * 1000 / 60; displaySimNow(clock); }
  check(displaySimNow(clock) - ended < .15, `ended waterfall kept scrolling ${displaySimNow(clock) - ended}`);

  // A new world epoch is followed at once instead of slewed to.
  sampleDisplayClock(state(3, "live", 2));
  check(Math.abs(displaySimNow(clock) - (3 - DISPLAY_CLOCK_LAG_S)) < .01, "new epoch not followed");

  // Between publications the raster is only blitted lower, never rebuilt.
  displayClock.context = null;
  clock = 1000;
  S.v2State = state(10);
  sampleDisplayClock(S.v2State);
  const rows = [];
  for (let stamp = 0; stamp <= 10; stamp += .25) rows.push({stamp, bins: Array(36).fill(Math.abs(stamp - 5) < .01 ? 1 : 0)});
  heatmap("waterfall", rows, null, null, null, 20);
  const brightRow = () => {
    const data = plotContext.getImageData(150, 0, 1, 200).data;
    let best = 0;
    for (let y = 1; y < 200; y++) if (data[y * 4 + 1] > data[best * 4 + 1]) best = y;
    return best;
  };
  const spec = {rows: rows.filter((row) => row.stamp >= -15), frequencies: null, axisMaximum: null, overlay: null, historyS: 20};
  drawHeatmap("waterfall", spec, clock);
  const builds = rasterBuilds, first = brightRow();
  let last = first;
  for (let frame = 1; frame <= 30; frame++) {
    clock = 1000 + frame * 1000 / 60;
    drawHeatmap("waterfall", spec, clock);
    const row = brightRow();
    check(row >= last && row - last <= 1, `waterfall jumped from ${last} to ${row}`);
    last = row;
  }
  // 10 px per second on a 200 px, 20 s axis: half a second scrolls 5 px.
  check(Math.abs(last - first - 5) <= 1, `waterfall scrolled ${last - first} px in 0.5 s`);
  check(rasterBuilds === builds, "waterfall raster rebuilt without new rows");
  // The fixed 20 s axis puts the 5 s old row (0.75 s display lag) near 42 px.
  check(Math.abs(first - (10 - DISPLAY_CLOCK_LAG_S - 5) * 10) <= 2, `bright row at ${first}`);

  // Spectra ease towards a publication instead of jumping to it.
  easedSpectrum("spectrum", [0, 0], 0);
  const eased = easedSpectrum("spectrum", [1, 1], 150).values[0];
  check(eased > .55 && eased < .7, `spectrum eased to ${eased} after one time constant`);
  check(easedSpectrum("spectrum", [1, 1], 1500).values[0] > .99, "spectrum did not settle");
  document.documentElement.dataset.result = "passed";
} catch (error) {
  document.documentElement.dataset.result = "failed";
  document.documentElement.dataset.failure = String(error.stack);
}
"""


def test_waterfalls_and_spectra_move_smoothly_between_publications(tmp_path):
    chromium = shutil.which("chromium") or shutil.which("chromium-browser")
    if chromium is None:
        pytest.skip("Chromium unavailable")
    script = (SCRIPT
              .replace("__CLOCK__", module_source("state/display-clock.js", "const DISPLAY_CLOCK_LAG_S"))
              .replace("__HEATMAP__", module_source("plot/heatmap.js", "function heatmap("))
              .replace("__SPECTRUM__", module_source("plot/spectrum.js", "const SPECTRUM_SMOOTHING_S",
                                                     "function drawSpectrum")))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            payload = (script if self.path == "/test.js" else
                       '<!doctype html><body><script src="/test.js"></script></body>').encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript" if self.path == "/test.js" else "text/html")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = subprocess.run([chromium, "--headless", "--no-sandbox", "--disable-gpu",
                "--disable-dev-shm-usage", f"--user-data-dir={tmp_path / 'plot-browser'}",
                "--virtual-time-budget=3000", "--dump-dom", f"http://127.0.0.1:{server.server_port}/"],
                capture_output=True, text=True, timeout=30)
        finally:
            server.shutdown()
            thread.join(timeout=5)
    root = next(attrs for tag, attrs in Document(result.stdout).elements if tag == "html")
    assert root.get("data-result") == "passed", root.get("data-failure", result.stderr)
