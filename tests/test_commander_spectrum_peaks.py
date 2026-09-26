"""Browser spectrum peak labels use the same rule as the uConsole sonar."""

import json
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pytest

from src.ui import sonar_view
from commander_web import module_source
from test_commander_assets import Document


def _cases():
    rng = np.random.default_rng(7)
    frequencies = np.arange(1.0, 51.0)
    skewed = np.full(50, .05)
    skewed[[10, 11, 12]] = [.4, .9, .6]
    skewed[30] = .5
    lofar = np.concatenate((np.arange(40) + .5, 41 + np.arange(30) * 2.0,
                            102.5 + np.arange(40) * 5.0))
    noisy = rng.uniform(.02, .12, lofar.size)
    noisy[[20, 55, 90]] = [.8, .6, .45]
    return [
        (skewed.tolist(), frequencies.tolist(), 8, 0.0),
        (skewed.tolist(), frequencies.tolist(), 1, 0.0),
        (noisy.tolist(), lofar.tolist(), 8, 12.0),
        ((np.full(50, .05) + np.sin(frequencies) * .004).tolist(), frequencies.tolist(), 8, 0.0),
    ]


def test_browser_peak_finder_matches_python(tmp_path):
    chromium = shutil.which("chromium") or shutil.which("chromium-browser")
    if chromium is None:
        pytest.skip("Chromium unavailable")
    finder = module_source("plot/peaks.js", "const PEAK_LABEL_W", "function drawPeakLabels")
    placements = [
        [(100, 60, 28, "a", .9), (112, 60, 28, "b", .5), (125, 62, 28, "c", .4), (200, 5, 28, "d", .8),
         (100, 60, 28, "e", .1)],
        [(10, 50, 28, "a", .9), (290, 3, 28, "b", .7)],
    ]
    bounds = [(300, 80), (300, 80), (60, 20)]
    placements.append([(30, 15, 28, "a", .9), (30, 15, 28, "b", .5)])
    cases = _cases()
    script = finder + f"""
const cases = {json.dumps(cases)};
const placements = {json.dumps(placements)};
const bounds = {json.dumps(bounds)};
document.documentElement.dataset.result = JSON.stringify({{
  peaks: cases.map(([values, hz, limit, separation]) =>
    spectrumPeaks(values, hz, limit, separation).map((peak) => [peak.hz, peak.level])),
  placed: placements.map((apexes, index) => placePeakLabels(apexes.map(([x, y, w, text, level]) => ({{x, y, w, text, level}})), ...bounds[index], [])
    .map((label) => [label.text, label.above, label.box.x])),
}});
"""

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
                "--disable-dev-shm-usage", f"--user-data-dir={tmp_path / 'peak-browser'}",
                "--virtual-time-budget=2000", "--dump-dom", f"http://127.0.0.1:{server.server_port}/"],
                capture_output=True, text=True, timeout=30)
        finally:
            server.shutdown()
            thread.join(timeout=5)
    root = next(attrs for tag, attrs in Document(result.stdout).elements if tag == "html")
    result = json.loads(root["data-result"])
    browser = result["peaks"]
    placed = [[[text, above, box.x] for box, text, _, _, above in
               sonar_view.place_peak_labels(apexes, (0, 0, *size))]
              for apexes, size in zip(placements, bounds)]
    # Strongest first; "b" moves beside its apex, "c" one row lower; in the
    # narrow strip the weaker "b" finds no free place and is dropped.
    assert [[row[0] for row in rows] for rows in placed] == [
        ["a", "d", "b", "c", "e"], ["a", "b"], ["a"]]
    assert [row[1] for row in placed[0]] == [True, False, False, False, False]
    assert result["placed"] == placed
    expected = [sonar_view.spectrum_peaks(values, hz, limit, separation)
                for values, hz, limit, separation in cases]
    assert [len(rows) for rows in expected] == [2, 1, 3, 0]
    assert len(browser) == len(expected)
    for got, want in zip(browser, expected):
        assert np.allclose(np.asarray(got).reshape(-1, 2), np.asarray(want).reshape(-1, 2))
