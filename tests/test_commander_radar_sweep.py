"""The browser radar strobe must turn smoothly although published bearings arrive late."""

import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from commander_web import module_source
from test_commander_assets import Document

pytestmark = pytest.mark.browser  # drives headless Chromium (CI browser job)


SCRIPT = r"""
let clock = 0;
const performance = {now: () => clock};
const finite = Number.isFinite;
const S = {opzSweepSample: null, v2State: null, connected: true};
const stopOpzSweepAnimation = () => {};
__IMPLEMENTATION__
const wrap180 = (value) => wrap360(value + 180) - 180;
const check = (ok, label) => { if (!ok) throw new Error(label); };

// Deterministic jitter: the host publishes at 2 Hz; every publication reaches the
// page 0-0.6 s late, sometimes out of order, and often twice (stream + poll).
let seed = 12345;
const random = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
const state = (sim, rate) => ({session: "s", epoch: 1, phase: "live", role: "opz", clock: {sim},
  opz: {radar: {sweep_bearing: wrap360(37 + sim * rate), sweep_rate_deg_s: rate}}});
function run(rate, label) {
  S.opzSweepSample = null;
  displayClock.context = null;
  clock = 1000;
  const start = clock;
  const truth = (time) => wrap360(37 + ((time - start) / 1000) * rate);
  const arrivals = [];
  let nextPublish = clock, previous = null, worst = 0, worstSpeed = 0, error = 0, backwards = 0;
  for (let frame = 0; frame < 60 * 40; frame++) {
    clock += 1000 / 60;
    while (clock >= nextPublish) {
      const sim = (nextPublish - start) / 1000;
      arrivals.push({at: nextPublish + random() * 600, sim});
      if (random() < .5) arrivals.push({at: nextPublish + random() * 600, sim});
      nextPublish += 500;
    }
    arrivals.sort((a, b) => a.at - b.at);
    while (arrivals.length && arrivals[0].at <= clock) {
      const s = state(arrivals.shift().sim, rate);
      sampleDisplayClock(s);
      updateOpzSweepSample(s);
    }
    const bearing = currentOpzSweepBearing();
    if (bearing === null) continue;
    if (previous !== null && frame > 60 * 8) {
      const step = wrap180(bearing - previous);
      const nominal = rate / 60;
      if (step < 0) backwards++;
      worst = Math.max(worst, Math.abs(step - nominal));
      worstSpeed = Math.max(worstSpeed, Math.abs(step / nominal - 1));
      error = Math.max(error, Math.abs(wrap180(bearing - truth(clock))));
    }
    previous = bearing;
  }
  check(backwards === 0, `${label}: strobe turned backwards ${backwards} times`);
  check(worst < rate / 60 * .12, `${label}: strobe jumped by ${worst.toFixed(2)} degrees in one frame`);
  check(worstSpeed < .15, `${label}: turning speed varied by ${(worstSpeed * 100).toFixed(0)} percent`);
  // And it stays close to the real sweep (bounded by the arrival delay, 0.6 s at most).
  check(error < rate * 0.6 + 2, `${label}: strobe drifted ${error.toFixed(1)} degrees from the real sweep`);
}
try {
  run(90, "90 deg/s");
  run(180, "180 deg/s");
  document.documentElement.dataset.result = "passed";
} catch (error) {
  document.documentElement.dataset.result = "failed";
  document.documentElement.dataset.failure = String(error.stack);
}
"""

def test_radar_strobe_is_smooth_despite_late_published_bearings(tmp_path):
    chromium = shutil.which("chromium") or shutil.which("chromium-browser")
    if chromium is None:
        pytest.skip("Chromium unavailable")
    implementation = (module_source("state/display-clock.js", "const DISPLAY_CLOCK_LAG_S") +
                      module_source("views/role-map.js", "const wrap360", "function opzSweepActive"))
    script = SCRIPT.replace("__IMPLEMENTATION__", implementation)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            payload = (script if self.path == "/test.js" else
                       '<!doctype html><script src="/test.js"></script>').encode()
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
                "--disable-dev-shm-usage", f"--user-data-dir={tmp_path / 'sweep-browser'}",
                "--virtual-time-budget=3000", "--dump-dom", f"http://127.0.0.1:{server.server_port}/"],
                capture_output=True, text=True, timeout=30)
        finally:
            server.shutdown()
            thread.join(timeout=5)
    root = next(attrs for tag, attrs in Document(result.stdout).elements if tag == "html")
    assert root.get("data-result") == "passed", root.get("data-failure", result.stderr)
