"""The browser radar strobe must turn smoothly although published bearings arrive late."""

import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from test_commander_assets import ASSETS, Document


SCRIPT = r"""
let clock = 0;
const performance = {now: () => clock};
const finite = Number.isFinite;
let opzSweepSample = null;
const stopOpzSweepAnimation = () => {};
__IMPLEMENTATION__
const check = (ok, label) => { if (!ok) throw new Error(label); };

// Deterministic jitter: every published bearing is 0-0.6 s old when it arrives, at 2 Hz.
let seed = 12345;
const random = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
function run(rate, label) {
  opzSweepSample = null;
  clock = 1000;
  const truth = (time) => wrap360(37 + (time / 1000) * rate);
  let nextSample = clock, previous = null, worst = 0, worstSpeed = 0, error = 0;
  for (let frame = 0; frame < 60 * 40; frame++) {
    clock += 1000 / 60;
    if (clock >= nextSample) {
      const age = random() * 600;
      updateOpzSweepSample({role: "opz", opz: {radar: {sweep_bearing: truth(clock - age), sweep_rate_deg_s: rate}}});
      nextSample += 500;
    }
    const bearing = currentOpzSweepBearing();
    if (previous !== null && frame > 60 * 8) {
      const step = wrap180(bearing - previous);
      const nominal = rate / 60;
      worst = Math.max(worst, Math.abs(step - nominal));
      worstSpeed = Math.max(worstSpeed, Math.abs(step / nominal - 1));
      error = Math.max(error, Math.abs(wrap180(bearing - truth(clock))));
    }
    previous = bearing;
  }
  // Nothing may jump: per-frame deviation stays a small fraction of a degree, so
  // the strobe never changes speed by more than the capped slew allows.
  check(worst < .5, `${label}: strobe jumped by ${worst.toFixed(2)} degrees in one frame`);
  check(worstSpeed < .35, `${label}: turning speed varied by ${(worstSpeed * 100).toFixed(0)} percent`);
  // And it stays close to the real sweep (bounded by the sample age, 0.6 s at most).
  check(error < rate * 0.6 + 2, `${label}: strobe drifted ${error.toFixed(1)} degrees from the real sweep`);
}
try {
  run(90, "90 deg/s");
  run(180, "180 deg/s");
  // A restarted sweep (implausible error) must be followed, not slewed to for seconds.
  updateOpzSweepSample({role: "opz", opz: {radar: {sweep_bearing: 10, sweep_rate_deg_s: 90}}});
  const before = currentOpzSweepBearing();
  updateOpzSweepSample({role: "opz", opz: {radar: {sweep_bearing: wrap360(before + 170), sweep_rate_deg_s: 90}}});
  check(Math.abs(wrap180(currentOpzSweepBearing() - wrap360(before + 170))) < 2, "restart not followed");
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
    js = ASSETS.joinpath("app.js").read_text()
    implementation = js[js.index("  const wrap360"):js.index("  function opzSweepActive")]
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
