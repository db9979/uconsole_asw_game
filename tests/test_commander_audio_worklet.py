"""Exercise the real audio processor with a stalled producer in Chromium."""

import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from test_commander_assets import ASSETS, Document


def test_audio_worklet_repeats_then_marks_stale_and_recovers(tmp_path):
    chromium = shutil.which("chromium") or shutil.which("chromium-browser")
    if chromium is None:
        pytest.skip("Chromium unavailable")
    processor = ASSETS.joinpath("sonar-audio-worklet.js").read_text()
    script = """
var sampleRate = 4096;
let Processor;
class AudioWorkletProcessor {
  constructor() { this.port = {onmessage:null, messages:[], postMessage(value) {this.messages.push(value);}}; }
}
function registerProcessor(_name, ctor) { Processor = ctor; }
""" + processor + """
try {
  const stream = new Processor();
  const output = [[new Float32Array(128)]];
  const feed = (sequence) => {
    const bytes = new ArrayBuffer(2048);
    new Int16Array(bytes).fill(8000);
    stream.port.onmessage({data:{type:'pcm', sequence, bytes}});
  };
  for (let i=1; i<=4; i++) feed(i);
  for (let i=0; i<32; i++) stream.process([], output);
  if (!stream.primed || stream.stale || stream.lastSequence !== 4) throw Error('startup');
  for (let i=0; i<80; i++) stream.process([], output);
  if (!stream.stale || !stream.port.messages.some(x => x.type === 'stale' && x.value)) throw Error('stale');
  if (!output[0][0].some(x => x !== 0)) throw Error('neutral noise');
  for (let i=6; i<=40; i++) feed(i);
  if (stream.blocks.length > 8 || stream.gaps < 1) throw Error('backpressure');
  for (let i=0; i<8; i++) stream.process([], output);
  if (stream.stale || !stream.port.messages.some(x => x.type === 'stale' && !x.value)) throw Error('recovery');
  stream.port.onmessage({data:{type:'reset'}});
  if (stream.blocks.length || stream.primed || stream.lastSequence !== null) throw Error('reset');
  document.documentElement.dataset.result = 'passed';
} catch (error) { document.documentElement.dataset.result = 'failed'; document.documentElement.dataset.failure = String(error); }
"""

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
                "--disable-dev-shm-usage", f"--user-data-dir={tmp_path / 'worklet-browser'}",
                "--virtual-time-budget=3000", "--dump-dom", f"http://127.0.0.1:{server.server_port}/"],
                capture_output=True, text=True, timeout=30)
        finally:
            server.shutdown()
            thread.join(timeout=5)
    root = next(attrs for tag, attrs in Document(result.stdout).elements if tag == "html")
    assert root.get("data-result") == "passed", root.get("data-failure", result.stderr)
