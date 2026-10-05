"""Waterfall rasters painted in the OffscreenCanvas worker match the main-thread painter."""

import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from commander_web import ASSET_DIR, page_dataset

# The page script runs under the listener's own Content-Security-Policy, so a
# worker the policy would refuse fails this test instead of silently falling back.
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
       "font-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; "
       "form-action 'self'")

PAGE = '<!doctype html><body><canvas id="probe"></canvas><script type="module" src="/probe.js"></script></body>'

PROBE = r"""
import { heatmapWorker } from "/js/plot/heatmap-worker-client.js";
import { paintHeatmap } from "/js/plot/heatmap-paint.js";

const html = document.documentElement;
globalThis.uJagdHeatmapWorker = true;
const check = (ok, label) => { if (!ok) throw new Error(label); };
const width = 180, rasterHeight = 120;
const colors = Uint32Array.from({length: 256}, (_, index) => ((255 << 24) | (index << 8) | (255 - index)) >>> 0);

function job(shift = 0) {
  const rows = 40, count = 36;
  const stamps = new Float64Array(rows), offsets = new Uint32Array(rows + 1), bins = new Float32Array(rows * count);
  for (let row = 0; row < rows; row++) {
    stamps[row] = row * .25;
    offsets[row] = row * count;
    for (let x = 0; x < count; x++) bins[row * count + x] = ((x * 7 + row * 3 + shift) % 17) / 16;
  }
  offsets[rows] = rows * count;
  return {width, rasterHeight, headroom: 12, pixelsPerSecond: 10, historyS: 10, xmax: 360, count,
    black: .1, contrast: 1.2, colors, anchor: 9.75, cellHeight: 3, stamps, offsets, bins, frequencies: null};
}

function pixelsOf(bitmap) {
  const canvas = document.getElementById("probe");
  canvas.width = width; canvas.height = rasterHeight;
  const context = canvas.getContext("2d");
  context.clearRect(0, 0, width, rasterHeight);
  context.drawImage(bitmap, 0, 0);
  return new Uint32Array(context.getImageData(0, 0, width, rasterHeight).data.buffer);
}

const rendered = (worker, id, input) => new Promise((resolve, reject) => {
  const timer = setTimeout(() => reject(new Error("worker did not answer")), 4000);
  worker.render(id, input, (bitmap, anchor) => { clearTimeout(timer); resolve({bitmap, anchor}); });
});

try {
  const worker = heatmapWorker();
  check(worker !== null && html.dataset.heatmapWorker === "on", `worker path ${html.dataset.heatmapWorker}`);
  check(heatmapWorker() === worker, "worker client not reused");
  const expected = new Uint32Array(width * rasterHeight);
  paintHeatmap(expected, job());
  const {bitmap, anchor} = await rendered(worker, "waterfall", job());
  check(anchor === 9.75, `anchor ${anchor}`);
  check(bitmap.width === width && bitmap.height === rasterHeight, "bitmap size");
  const actual = pixelsOf(bitmap);
  const mismatch = actual.findIndex((value, index) => value !== expected[index]);
  check(mismatch < 0, `worker pixel ${mismatch} differs`);

  // Jobs arriving while one is painted replace each other: the plot gets the
  // first raster and then only the newest, never a queue of stale ones.
  const seen = [];
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`coalesced jobs stalled at ${seen}`)), 4000);
    for (const shift of [1, 2, 3]) {
      worker.render("lofar", job(shift), (frame) => {
        seen.push(shift);
        frame.close();
        if (shift === 3) { clearTimeout(timer); resolve(); }
      });
    }
  });
  check(seen.join() === "1,3", `delivered ${seen}`);
  html.dataset.result = "passed";
} catch (error) {
  html.dataset.result = "failed";
  html.dataset.failure = String(error.stack || error);
}
"""


def test_worker_rasters_match_the_main_thread_painter(tmp_path):
    chromium = shutil.which("chromium") or shutil.which("chromium-browser")
    if chromium is None:
        pytest.skip("Chromium unavailable")
    js_root = (ASSET_DIR / "js").resolve()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            if self.path == "/":
                payload, mime = PAGE.encode(), "text/html"
            elif self.path == "/probe.js":
                payload, mime = PROBE.encode(), "text/javascript"
            elif self.path.startswith("/js/plot/") and self.path.endswith(".js"):
                target = (js_root / self.path[len("/js/"):]).resolve()
                if js_root not in target.parents or not target.is_file():
                    self.send_error(404)
                    return
                payload, mime = target.read_bytes(), "text/javascript"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        # Real time, not --virtual-time-budget: virtual time never lets the
        # worker thread answer before the page is dumped.
        profile = tmp_path / "heatmap-worker"
        process = subprocess.Popen([chromium, "--headless", "--no-sandbox", "--disable-gpu",
            "--disable-dev-shm-usage", "--no-first-run", f"--user-data-dir={profile}",
            "--remote-debugging-port=0", f"http://127.0.0.1:{server.server_port}/"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        root = {}
        try:
            started = time.monotonic()
            while process.poll() is None and time.monotonic() - started < 45:
                root = page_dataset(profile) or root
                if root.get("result"):
                    break
                time.sleep(.2)
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
            server.shutdown()
            thread.join(timeout=5)
    assert root.get("result") == "passed", root.get("failure", root)
