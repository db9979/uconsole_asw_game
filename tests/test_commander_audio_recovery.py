"""Execute the actual browser audio lifecycle with deterministic transport races."""

from commander_web import run_module_probe


def test_audio_continues_across_metadata_refresh_timeout_and_transient_error(tmp_path):
    script = r"""
import { S } from "./js/state/store.js";
import { pollSonarAudio, readSonarPcm, sonarAudioAuthorized, stopSonarAudio } from "./js/audio/audio.js";
let nextTimer = 0;
const timers = new Map();
globalThis.setTimeout = (fn, delay) => { const id = ++nextTimer; timers.set(id, {fn, delay}); return id; };
globalThis.clearTimeout = (id) => timers.delete(id);
const starts = [];
Object.assign(S, {
  connected: true, generation: 1,
  session: {client_id:'crew', csrf:'csrf', station:'sonar', station_generation:2, grants:{sonar_audio:true}},
  v2State: {session:'world', epoch:1, role:'sonar', phase:'live', clock:{}, sonar:{settings:{station_down:false}}},
  sonarAudioEnabled: true, sonarAudioController: null, sonarAudioSources: [], sonarAudioSequence: null,
  sonarAudioTimer: null, sonarAudioNextTime: 0, sonarAudioGeneration: 0,
  sonarAudioSocket: null, sonarAudioWorklet: null, sonarAudioReconnect: null,
  sonarAudioMetrics: {buffered:0, gaps:0, concealed:0, rate:1, stale:false},
  sonarAudioGain: {gain:{value:0}, disconnect() {}},
  audio: {sampleRate:48000, currentTime:1,
    createBuffer(_channels, size, rate) { return {duration:size/rate, getChannelData() {return new Float32Array(size);}}; },
    createBufferSource() { return {connect(){}, disconnect(){}, stop(){this.stopped=true;}, start(time){starts.push(time);}}; }},
});
const check = (ok, label) => { if (!ok) throw new Error(label); };
(async () => {
  let deliver;
  globalThis.fetch = () => new Promise((resolve) => { deliver = resolve; });
  const pending = pollSonarAudio();
  S.session = structuredClone(S.session); // Exactly what the 1 Hz session poll does.
  deliver(new Response(new Uint8Array(2048), {status:200, headers:{
    'Content-Type':'audio/pcm', 'Content-Length':'2048', 'X-U-Jagd-PCM':'s16le',
    'X-U-Jagd-Sample-Rate':'4096', 'X-U-Jagd-Audio-Frames':'1024',
    'X-U-Jagd-Audio-Sequence':'1', 'X-U-Jagd-Audio-Discontinuity':'0'}}));
  await pending;
  check(S.sonarAudioSequence === 1 && starts.length === 1, 'metadata refresh dropped valid audio');
  check(starts[0] >= 2.0 && starts[0] <= 2.1, 'bounded startup jitter buffer');
  check(timers.has(S.sonarAudioTimer), 'audio poll not rescheduled');
  S.audio.currentTime = 1.1;
  globalThis.fetch = async () => new Response(new Uint8Array(2048), {status:200, headers:{
    'Content-Type':'audio/pcm', 'Content-Length':'2048', 'X-U-Jagd-PCM':'s16le',
    'X-U-Jagd-Sample-Rate':'4096', 'X-U-Jagd-Audio-Frames':'1024',
    'X-U-Jagd-Audio-Sequence':'2', 'X-U-Jagd-Audio-Discontinuity':'0'}});
  await pollSonarAudio();
  check(starts.length === 2 && Math.abs(starts[1] - starts[0] - .25) < .001,
    'contiguous blocks were not scheduled on one audio timeline');
  globalThis.fetch = async () => new Response(null, {status:204}); // Proxies may omit Content-Length: 0.
  await pollSonarAudio();
  check(S.sonarAudioEnabled && timers.has(S.sonarAudioTimer), 'empty proxy response killed stream');
  // A failed state poll or transient 503 must not throw away already scheduled
  // PCM. The S.audio endpoint itself remains the authority for every request.
  S.connected = false;
  check(sonarAudioAuthorized(), 'stale state poll revoked audio');
  globalThis.fetch = async () => new Response('', {status:503});
  await pollSonarAudio();
  check(S.sonarAudioEnabled && starts.length === 2 && timers.has(S.sonarAudioTimer),
    'temporary audio unavailability killed buffered playback');
  S.connected = true;
  S.audio.currentTime = 1.65;
  S.sonarAudioSources[0].onended();
  globalThis.fetch = (_url, options) => new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => reject(new DOMException('timeout', 'AbortError'))));
  const timed = pollSonarAudio();
  [...timers.values()].find((timer) => timer.delay === 2000).fn();
  await timed;
  check(S.sonarAudioEnabled && S.sonarAudioController === null && timers.has(S.sonarAudioTimer), 'timeout killed stream');
  globalThis.fetch = async () => new Response('', {status:500});
  await pollSonarAudio();
  check(S.sonarAudioEnabled && timers.has(S.sonarAudioTimer), 'temporary server error killed stream');
  for (const source of S.sonarAudioSources) source.onended();
  S.audio.currentTime = 8.0;  // past the scheduled timeline: an underrun
  globalThis.fetch = async () => new Response(new Uint8Array(2048), {status:200, headers:{
    'Content-Type':'audio/pcm; charset=binary', 'X-U-Jagd-PCM':'s16le',
    'X-U-Jagd-Sample-Rate':'4096', 'X-U-Jagd-Audio-Frames':'1024',
    'X-U-Jagd-Audio-Sequence':'3', 'X-U-Jagd-Audio-Discontinuity':'0'}});
  await pollSonarAudio();
  check(starts.length === 3 && starts[2] >= 9.0 && starts[2] <= 9.1,
    'proxied PCM or underrun was rejected');
  const queued = S.sonarAudioSources.at(-1);
  globalThis.fetch = async () => new Response(new Uint8Array(2048), {status:200, headers:{
    'Content-Type':'audio/pcm', 'X-U-Jagd-PCM':'s16le',
    'X-U-Jagd-Sample-Rate':'4096', 'X-U-Jagd-Audio-Frames':'1024',
    'X-U-Jagd-Audio-Sequence':'5', 'X-U-Jagd-Audio-Discontinuity':'1'}});
  await pollSonarAudio();
  check(!queued.stopped && starts.length === 4 && Math.abs(starts[3] - starts[2] - .25) < .001,
    'discontinuity stopped already queued audio');
  for (const size of [2047, 2049]) {
    try {
      await readSonarPcm(new Response(new Uint8Array(size)));
      throw new Error('wrong-sized PCM was accepted');
    } catch (error) { check(error.message === 'audio_protocol', 'wrong-sized PCM wrong error'); }
  }
  globalThis.fetch = () => new Promise((resolve) => { deliver = resolve; });
  const revoked = pollSonarAudio();
  stopSonarAudio();
  deliver(new Response(null, {status:204}));
  await revoked;
  check(!S.sonarAudioEnabled && S.sonarAudioSources.length === 0 && S.sonarAudioTimer === null, 'old response revived revoked stream');
  document.documentElement.dataset.result = 'passed';
})().catch((error) => { document.documentElement.dataset.result = 'failed'; document.documentElement.dataset.failure = String(error.stack); });
"""
    root = run_module_probe(tmp_path, script, budget_ms=3000)
    assert root.get("data-result") == "passed", root.get("data-failure")
