"""Execute the actual browser audio lifecycle with deterministic transport races."""

import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from test_commander_assets import ASSETS, Document


def test_audio_continues_across_metadata_refresh_timeout_and_transient_error(tmp_path):
    chromium = shutil.which("chromium") or shutil.which("chromium-browser")
    if chromium is None:
        pytest.skip("Chromium unavailable")
    js = ASSETS.joinpath("app.js").read_text()
    implementation = js[js.index("  const sonarAudioAuthorized"):js.index("  function node(")]
    script = r"""
const controls = new Map();
const $ = (id) => { if (!controls.has(id)) controls.set(id, {value: 25, setAttribute() {}}); return controls.get(id); };
const t = (key) => key;
const finite = Number.isFinite;
let protocolMode = 'v2', connected = true, generation = 1;
let session = {client_id:'crew', csrf:'csrf', station:'sonar', station_generation:2, grants:{sonar_audio:true}};
let v2State = {session:'world', epoch:1, role:'sonar', phase:'live', clock:{time_scale:1}, sonar:{settings:{station_down:false}}};
let sonarAudioEnabled = true, sonarAudioController = null, sonarAudioSources = [], sonarAudioSequence = null;
let sonarAudioTimer = null, sonarAudioNextTime = 0, sonarAudioGeneration = 0;
let sonarAudioGain = {gain:{value:0}, disconnect() {}}, nextTimer = 0;
const timers = new Map();
const setTimeout = (fn, delay) => { const id = ++nextTimer; timers.set(id, {fn, delay}); return id; };
const clearTimeout = (id) => timers.delete(id);
const starts = [];
const audio = {sampleRate:48000, currentTime:1,
  createBuffer(_channels, size, rate) { return {duration:size/rate, getChannelData() {return new Float32Array(size);}}; },
  createBufferSource() { return {connect(){}, disconnect(){}, stop(){}, start(time){starts.push(time);}}; }
};
let fetch;
const check = (ok, label) => { if (!ok) throw new Error(label); };
""" + implementation + r"""
(async () => {
  let deliver;
  fetch = () => new Promise((resolve) => { deliver = resolve; });
  const pending = pollSonarAudio();
  session = structuredClone(session); // Exactly what the 1 Hz session poll does.
  deliver(new Response(new Uint8Array(2048), {status:200, headers:{
    'Content-Type':'audio/pcm', 'Content-Length':'2048', 'X-U-Jagd-PCM':'s16le',
    'X-U-Jagd-Sample-Rate':'4096', 'X-U-Jagd-Audio-Frames':'1024',
    'X-U-Jagd-Audio-Sequence':'1', 'X-U-Jagd-Audio-Discontinuity':'0'}}));
  await pending;
  check(sonarAudioSequence === 1 && starts.length === 1, 'metadata refresh dropped valid audio');
  check(starts[0] >= 1.25 && starts[0] <= 1.5, 'bounded startup jitter buffer');
  check(timers.has(sonarAudioTimer), 'audio poll not rescheduled');
  audio.currentTime = 1.1;
  fetch = async () => new Response(new Uint8Array(2048), {status:200, headers:{
    'Content-Type':'audio/pcm', 'Content-Length':'2048', 'X-U-Jagd-PCM':'s16le',
    'X-U-Jagd-Sample-Rate':'4096', 'X-U-Jagd-Audio-Frames':'1024',
    'X-U-Jagd-Audio-Sequence':'2', 'X-U-Jagd-Audio-Discontinuity':'0'}});
  await pollSonarAudio();
  check(starts.length === 2 && Math.abs(starts[1] - starts[0] - .25) < .001,
    'contiguous blocks were not scheduled on one audio timeline');
  audio.currentTime = 1.65;
  sonarAudioSources[0].onended();
  fetch = (_url, options) => new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => reject(new DOMException('timeout', 'AbortError'))));
  const timed = pollSonarAudio();
  [...timers.values()].find((timer) => timer.delay === 2000).fn();
  await timed;
  check(sonarAudioEnabled && sonarAudioController === null && timers.has(sonarAudioTimer), 'timeout killed stream');
  fetch = async () => new Response('', {status:500});
  await pollSonarAudio();
  check(sonarAudioEnabled && timers.has(sonarAudioTimer), 'temporary server error killed stream');
  for (const source of sonarAudioSources) source.onended();
  audio.currentTime = 2.2;
  fetch = async () => new Response(new Uint8Array(2048), {status:200, headers:{
    'Content-Type':'audio/pcm', 'Content-Length':'2048', 'X-U-Jagd-PCM':'s16le',
    'X-U-Jagd-Sample-Rate':'4096', 'X-U-Jagd-Audio-Frames':'1024',
    'X-U-Jagd-Audio-Sequence':'3', 'X-U-Jagd-Audio-Discontinuity':'0'}});
  await pollSonarAudio();
  check(starts.length === 3 && starts[2] >= 2.45 && starts[2] <= 2.7,
    'underrun did not rebase to a fresh playout reserve');
  fetch = () => new Promise((resolve) => { deliver = resolve; });
  const revoked = pollSonarAudio();
  stopSonarAudio();
  deliver(new Response(null, {status:204}));
  await revoked;
  check(!sonarAudioEnabled && sonarAudioSources.length === 0 && sonarAudioTimer === null, 'old response revived revoked stream');
  document.documentElement.dataset.result = 'passed';
})().catch((error) => { document.documentElement.dataset.result = 'failed'; document.documentElement.dataset.failure = String(error.stack); });
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
                "--disable-dev-shm-usage", f"--user-data-dir={tmp_path / 'audio-browser'}",
                "--virtual-time-budget=3000", "--dump-dom", f"http://127.0.0.1:{server.server_port}/"],
                capture_output=True, text=True, timeout=30)
        finally:
            server.shutdown()
            thread.join(timeout=5)
    root = next(attrs for tag, attrs in Document(result.stdout).elements if tag == "html")
    assert root.get("data-result") == "passed", root.get("data-failure", result.stderr)
