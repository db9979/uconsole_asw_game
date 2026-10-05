"""Exercise the real audio processor with a stalled producer in Chromium."""

import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from test_commander_assets import ASSETS, Document

pytestmark = pytest.mark.browser  # drives headless Chromium (CI browser job)


def test_audio_worklet_is_elastic_conceals_marks_stale_and_recovers(tmp_path):
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
  const tone = (sequence) => {
    const bytes = new ArrayBuffer(2048);
    const pcm = new Int16Array(bytes);
    for (let i = 0; i < 1024; i++) pcm[i] = Math.round(8000 * Math.sin(2 * Math.PI * 97 * ((sequence - 1) * 1024 + i) / 4096));
    return bytes;
  };
  const feed = (stream, sequence) => stream.port.onmessage({data:{type:'pcm', sequence, bytes: tone(sequence)}});
  const output = [[new Float32Array(128)]];
  const run = (stream, frames, sink) => {
    for (let done = 0; done < frames; done += 128) {
      stream.process([], output);
      if (sink) sink.push(...output[0][0]);
    }
  };

  // Startup waits for eight blocks (two seconds), then plays the joined tone without steps.
  const PRIME = 8;
  sampleRate = 48000;
  let stream = new Processor();
  for (let i = 1; i < PRIME; i++) feed(stream, i);
  run(stream, 1280);
  if (stream.primed || output[0][0].some(x => x !== 0)) throw Error('early start');
  let sequence = PRIME;
  feed(stream, sequence);
  const played = [];
  // Producer 1 % slow against the audio clock: steered, never concealed.
  let produced = PRIME * 12000;
  for (let frame = 0; frame < 48000 * 60; frame += 128) {
    if (frame * .99 >= produced - PRIME * 12000) { feed(stream, ++sequence); produced += 12000; }
    run(stream, 128, frame > 48000 * 50 ? played : null);
  }
  if (!stream.primed || stream.concealed !== 0 || stream.stale) throw Error('drift underrun ' + stream.concealed);
  if (!(stream.rate < 1 && stream.rate >= .98)) throw Error('rate ' + stream.rate);
  let maxStep = 0;
  for (let i = 1; i < played.length; i++) maxStep = Math.max(maxStep, Math.abs(played[i] - played[i - 1]));
  // A 97 Hz tone at 48 kHz moves at most ~0.0031 per sample at 0.244 peak.
  if (maxStep > .004) throw Error('block join step ' + maxStep);

  // Stall: non-periodic concealment, then stale neutral noise (after 3 s).
  sampleRate = 4096;
  stream = new Processor();
  for (let i = 1; i <= PRIME; i++) feed(stream, i);
  run(stream, PRIME * 1024 + 256);
  if (stream.concealed < 1 || stream.stale) throw Error('conceal');
  const first = Array.from(stream.current);
  run(stream, 1024);
  if (first.every((x, i) => x === stream.current[i])) throw Error('concealment repeats');
  run(stream, 4 * 4096);
  if (!stream.stale || !stream.port.messages.some(x => x.type === 'stale' && x.value)) throw Error('stale');
  if (!output[0][0].some(x => x !== 0)) throw Error('neutral noise');
  // Three blocks are not enough to resume (REFILL_BLOCKS = 4); the fourth is.
  let next = PRIME + 2;
  for (let i = 0; i < 3; i++) { feed(stream, next++); run(stream, 512); }
  if (!stream.stale || stream.gaps < 1) throw Error('refill');
  feed(stream, next++);
  run(stream, 256);
  if (stream.stale || !stream.port.messages.some(x => x.type === 'stale' && !x.value)) throw Error('recovery');
  for (; next <= 80; next++) feed(stream, next);
  if (stream.blocks.length > 24 || stream.evictions < 1) throw Error('backpressure');
  // A re-sent (old or repeated) sequence is a duplicate: counted, never queued.
  const queued = stream.blocks.length;
  feed(stream, 80); feed(stream, 12);
  if (stream.dropped !== 2 || stream.blocks.length !== queued) throw Error('duplicate ' + stream.dropped);
  run(stream, 4096);
  const metrics = stream.port.messages.filter(x => x.type === 'metrics').at(-1);
  if (!metrics || !('concealed' in metrics) || !('rate' in metrics) || metrics.dropped !== 2) throw Error('metrics');
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
