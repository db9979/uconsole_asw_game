import { S } from "../state/store.js";
import { $, audioRoles } from "../core/base.js";
import { finite, t } from "../core/format.js";
import { calloutKinds, gameEffectKinds } from "../state/shared.js";

// State polling and browser network hints can fail while the dedicated audio
// request still works. The audio endpoint rechecks the session on every block.
export const sonarAudioAuthorized = () => !document.hidden &&
  audioRoles.has(S.session?.station) && S.session.grants.sonar_audio === true &&
  S.v2State?.role === S.session.station && S.v2State.phase === "live" &&
  S.v2State.sonar?.settings?.station_down !== true &&
  (S.session.station !== "helicopter" || S.v2State.helicopter?.acoustic?.ready === true);
const audioRoute = (role) => (role === "helicopter" ? "helicopter" : role === "uboot_sonar" ? "uboot" : "sonar");
const audioPollRoutes = {helicopter: "/api/v2/helicopter/audio", uboot_sonar: "/api/v2/uboot/audio"};
// Blocks arrive at real-time rate, so the standing buffer is the start lead. It
// must outlast a browser main-thread stall or a Wi-Fi hiccup, otherwise every
// such hiccup is an audible gap; live listening tolerates the extra latency.
// (HTTP fallback without AudioWorklet; the worklet keeps the same two-second lead.)
const sonarAudioStartLead = 2.0;
const sonarAudioTargetAhead = 2.5;
const sonarAudioMaxSources = 24;
export const sonarGainValue = () => {
  const value = Number($("volume").value) / 200;
  const helicopterLevel = S.session?.station === "helicopter"
    ? Number($("helicopter-audio-volume").value) / 100 : 1;
  return finite(value) && finite(helicopterLevel)
    ? Math.max(0, Math.min(.5, value * helicopterLevel)) : 0;
};
export const sonarFilterValues = () => {
  const prefix = S.session?.station === "helicopter" ? "helicopter" : "sonar";
  return [Number($(`${prefix}-audio-highpass`).value),
    Number($(`${prefix}-audio-lowpass`).value)];
};
function playGameEffect(kind, pan = null) {
  if (!S.soundEnabled || !S.audio || S.audio.state !== "running" || document.hidden || !gameEffectKinds.has(kind)) return;
  const volume = Math.max(0, Math.min(1, Number($("volume").value) / 100));
  if (!volume) return;
  const profile = {
    sonar_ping: [720, 980, .62, .10, "sine"], esm_contact: [1040, 1320, .16, .10, "sine"],
    torpedo_launch: [95, 38, .72, .16, "sawtooth"],
    missile_launch: [150, 1250, .9, .13, "sawtooth"], gunfire: [115, 52, .42, .16, "square"],
    explosion: [68, 25, 1.1, .20, "sawtooth"], water_entry: [260, 90, .58, .11, "triangle"],
    // The engine telegraph's ring as the order drops in.
    telegraph: [1180, 1180, .9, .07, "sine"],
    // Returned echoes: CW a steady carrier tone, LFM a short 100 Hz sweep.
    sonar_echo_cw: [900, 900, .55, .07, "sine"], sonar_echo_cw_faint: [900, 900, .55, .025, "sine"],
    sonar_echo_lfm: [850, 950, .32, .08, "sine"], sonar_echo_lfm_faint: [850, 950, .32, .03, "sine"],
    alarm: [880, 660, .6, .12, "square"],
    // Inside the crewed boat: the hull groaning deep down, a hull failure's
    // crack and detonations close by or far off.
    hull_creak: [88, 70, 1.8, .10, "sawtooth"], hull_crack: [180, 46, .5, .22, "square"],
    detonation_near: [60, 24, 1.6, .22, "sawtooth"], detonation_far: [42, 22, 2.4, .09, "triangle"],
    // Another platform's active ping: heard by the frigate, or on the hull.
    enemy_ping: [1300, 1300, .5, .08, "sine"], ping_heard: [1300, 1300, .6, .10, "sine"],
  }[kind];
  const [startHz, endHz, duration, gainLevel, type] = profile;
  const oscillator = S.audio.createOscillator();
  const gain = S.audio.createGain();
  const now = S.audio.currentTime;
  oscillator.type = type;
  oscillator.frequency.setValueAtTime(startHz, now);
  if (kind.startsWith("sonar_echo_lfm") || kind === "hull_creak") oscillator.frequency.linearRampToValueAtTime(endHz, now + duration);
  else oscillator.frequency.setValueAtTime(endHz, now + duration);
  gain.gain.setValueAtTime(0, now);
  gain.gain.linearRampToValueAtTime(volume * gainLevel, now + .012);
  gain.gain.linearRampToValueAtTime(0, now + duration);
  oscillator.connect(gain);
  // Directional hearing: the host places each cue left or right of the
  // ship's (or submarine's) head from the bearing it was heard on.
  const panner = Number.isFinite(pan) && typeof S.audio.createStereoPanner === "function"
    ? S.audio.createStereoPanner() : null;
  if (panner) {
    panner.pan.setValueAtTime(Math.max(-1, Math.min(1, pan)), now);
    gain.connect(panner);
    panner.connect(S.audio.destination);
  } else gain.connect(S.audio.destination);
  oscillator.start(now);
  oscillator.stop(now + duration + .02);
  oscillator.onended = () => { oscillator.disconnect(); gain.disconnect(); if (panner) panner.disconnect(); };
}
// Spoken crew reports: SpeechSynthesis in this browser's language, at most
// three sentences queued; the host sends only the report kind and bearing.
const speechQueueMax = 3;
function speakCallout(row) {
  if (!S.speechEnabled || document.hidden || !calloutKinds.has(row.key) ||
      !("speechSynthesis" in window) || S.speechQueued >= speechQueueMax) return;
  const bearing = row.bearing === null ? "" :
    String(row.bearing).padStart(3, "0").split("").map((digit) => t(`callout_digit_${digit}`)).join(" ");
  const utterance = new SpeechSynthesisUtterance(t(`callout_${row.key}`, {bearing}));
  utterance.lang = S.language === "de" ? "de-DE" : "en-GB";
  utterance.rate = 1.1;
  S.speechQueued += 1;
  utterance.onend = utterance.onerror = () => { S.speechQueued = Math.max(0, S.speechQueued - 1); };
  window.speechSynthesis.speak(utterance);
}
export function stopSpeech() {
  S.speechQueued = 0;
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
}
function syncCallouts(context) {
  const rows = Array.isArray(S.v2State?.audio?.callouts) ? S.v2State.audio.callouts : [];
  const latest = rows.length ? rows.at(-1).seq : 0;
  if (context !== S.calloutContext) {
    S.calloutContext = context;
    S.calloutHighWater = latest;
    return;
  }
  for (const row of rows) if (row.seq > S.calloutHighWater) speakCallout(row);
  S.calloutHighWater = Math.max(S.calloutHighWater, latest);
}
export function syncGameAudio() {
  // The general sound control plays bounded one-shot events only. Live sonar
  // remains an explicit, separately authorized station function.
  const stateAudio = S.v2State?.audio;
  const context = S.v2State ? `${S.v2State.session}:${S.v2State.epoch}` : null;
  const events = Array.isArray(stateAudio?.events) ? stateAudio.events : [];
  const latest = events.length ? events.at(-1).seq : 0;
  syncCallouts(context);
  if (context !== S.gameSoundContext) {
    S.gameSoundContext = context;
    S.gameSoundHighWater = latest;
  } else {
    for (const event of events) if (event.seq > S.gameSoundHighWater) playGameEffect(event.cue, event.pan);
    S.gameSoundHighWater = Math.max(S.gameSoundHighWater, latest);
  }
}
export function renderSonarAudio(key) {
  const button = $("sonar-live-toggle");
  button.textContent = t(S.sonarAudioEnabled ? "sonar_live_stop" : "sonar_live_start");
  button.setAttribute("aria-pressed", String(S.sonarAudioEnabled));
  button.disabled = !S.sonarAudioEnabled && !(audioRoles.has(S.session?.station) && S.session?.grants.sonar_audio === true &&
    (S.session.station !== "helicopter" || S.v2State?.helicopter?.acoustic?.ready === true));
  const receiverRequired = S.session?.station === "helicopter" && S.v2State?.helicopter?.acoustic?.ready !== true;
  $("sonar-live-status").textContent = t(receiverRequired ? "sonar_live_receiver_required" :
    S.sonarAudioEnabled && S.sonarAudioMetrics.stale ? "sonar_live_stale" :
    key || (S.sonarAudioEnabled ? "sonar_live_waiting" : "sonar_live_off"));
}
export function stopSonarAudio(key = "sonar_live_off") {
  S.sonarAudioGeneration += 1;
  S.sonarAudioEnabled = false;
  S.sonarAudioMetrics = {buffered: 0, gaps: 0, evictions: 0, dropped: 0, concealed: 0, rate: 1, stale: false};
  window.uJagdAudioDiagnostics = Object.freeze({bufferedSeconds: 0,
    sequenceGaps: 0, droppedBlocks: 0, evictedBlocks: 0, concealedBlocks: 0, playbackRate: 1,
    stale: false, transport: "off"});
  clearTimeout(S.sonarAudioTimer);
  S.sonarAudioTimer = null;
  S.sonarAudioController?.abort();
  S.sonarAudioController = null;
  clearTimeout(S.sonarAudioReconnect);
  S.sonarAudioReconnect = null;
  S.sonarAudioSocket?.close();
  S.sonarAudioSocket = null;
  S.sonarAudioWorklet?.port.postMessage({type: "reset"});
  S.sonarAudioWorklet?.disconnect();
  S.sonarAudioWorklet = null;
  for (const source of S.sonarAudioSources) { try { source.stop(); } catch (_) {} source.disconnect(); }
  S.sonarAudioSources = [];
  S.sonarAudioSequence = null;
  S.sonarAudioNextTime = 0;
  S.sonarAudioGain?.disconnect();
  S.sonarAudioGain = null;
  if (typeof S.sonarAudioHighpass !== "undefined") {
    S.sonarAudioHighpass?.disconnect();
    S.sonarAudioHighpass = null;
  }
  if (typeof S.sonarAudioLowpass !== "undefined") {
    S.sonarAudioLowpass?.disconnect();
    S.sonarAudioLowpass = null;
  }
  renderSonarAudio(key);
}
export function scheduleSonarAudioPoll(delay = 0) {
  clearTimeout(S.sonarAudioTimer);
  if (S.sonarAudioEnabled && !S.sonarAudioSocket) S.sonarAudioTimer = setTimeout(pollSonarAudio, delay);
}
export function openSonarAudioSocket() {
  if (!S.sonarAudioEnabled || !S.sonarAudioWorklet || S.sonarAudioSocket || !sonarAudioAuthorized()) return;
  const role = S.session.station;
  const client = S.session.client_id;
  const lease = S.session.station_generation;
  const active = S.session.active_generation;
  const world = S.v2State.session;
  const epoch = S.v2State.epoch;
  const streamGeneration = S.sonarAudioGeneration;
  const current = () => S.sonarAudioEnabled && streamGeneration === S.sonarAudioGeneration &&
    S.session?.client_id === client && S.session?.station === role &&
    S.session?.station_generation === lease && S.session?.active_generation === active &&
    S.v2State?.session === world && S.v2State?.epoch === epoch;
  // Same listener, lease and role; only the world epoch moved on.
  const resumable = () => S.sonarAudioEnabled && streamGeneration === S.sonarAudioGeneration &&
    S.session?.client_id === client && S.session?.station === role &&
    S.session?.station_generation === lease && S.session?.active_generation === active;
  let socket;
  try {
    const scheme = location.protocol === "https:" ? "wss:" : "ws:";
    // Resume behind the last accepted block: the host never re-sends audio
    // the worklet already holds, and numbering never restarts within a run.
    const resume = Number.isSafeInteger(S.sonarAudioSequence) && S.sonarAudioSequence >= 0
      ? `?after=${S.sonarAudioSequence}` : "";
    socket = new WebSocket(`${scheme}//${location.host}/ws/v2/${audioRoute(role)}/audio${resume}`, "u-jagd-audio-v2");
  } catch (_) { scheduleSonarAudioPoll(0); return; }
  socket.binaryType = "arraybuffer";
  S.sonarAudioSocket = socket;
  socket.onopen = () => { if (!current()) socket.close(); else clearTimeout(S.sonarAudioTimer); };
  socket.onmessage = ({data}) => {
    if (!current() || !(data instanceof ArrayBuffer) || data.byteLength !== 2060) { socket.close(); return; }
    const view = new DataView(data);
    if (view.getUint32(0, false) !== 0x554a4132) { socket.close(); return; }
    const sequence = Number(view.getBigUint64(4, true));
    if (!Number.isSafeInteger(sequence) || sequence < 1) { socket.close(); return; }
    S.sonarAudioSequence = sequence;
    const bytes = data.slice(12);
    S.sonarAudioWorklet.port.postMessage({type: "pcm", sequence,
      bytes}, [bytes]);
    if (!S.sonarAudioMetrics.stale) renderSonarAudio("sonar_live_playing");
  };
  socket.onclose = () => {
    if (S.sonarAudioSocket === socket) S.sonarAudioSocket = null;
    if (current()) {
      scheduleSonarAudioPoll(0);
      S.sonarAudioReconnect = setTimeout(openSonarAudioSocket, 500);
    } else if (resumable()) {
      // The host's local input advanced the epoch: reconnect at once.
      clearTimeout(S.sonarAudioReconnect);
      S.sonarAudioReconnect = setTimeout(openSonarAudioSocket, 50);
    }
  };
  socket.onerror = () => socket.close();
}
export async function readSonarPcm(response) {
  const reader = response.body?.getReader?.();
  if (!reader) throw new Error("audio_protocol");
  const output = new Uint8Array(2048);
  let offset = 0;
  let complete = false;
  try {
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      if (!(value instanceof Uint8Array) || offset + value.byteLength > output.byteLength)
        throw new Error("audio_protocol");
      output.set(value, offset);
      offset += value.byteLength;
    }
    if (offset !== output.byteLength) throw new Error("audio_protocol");
    complete = true;
    return output.buffer;
  } finally {
    if (!complete) await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
export async function pollSonarAudio() {
  if (!S.sonarAudioEnabled || S.sonarAudioController || S.sonarAudioSocket?.readyState === WebSocket.OPEN) return;
  if (!sonarAudioAuthorized()) { stopSonarAudio("sonar_live_unavailable"); return; }
  S.sonarAudioSources = S.sonarAudioSources.filter((source) => !source.__ended);
  const queuedAhead = Math.max(0, S.sonarAudioNextTime - S.audio.currentTime);
  if (S.sonarAudioSources.length >= sonarAudioMaxSources || queuedAhead >= sonarAudioTargetAhead) {
    scheduleSonarAudioPoll(Math.max(20, Math.min(80,
      (queuedAhead - sonarAudioTargetAhead) * 1000)));
    return;
  }
  const context = S.generation;
  const streamGeneration = S.sonarAudioGeneration;
  const expectedSession = {client_id: S.session.client_id, csrf: S.session.csrf,
    station_generation: S.session.station_generation, active_generation: S.session.active_generation,
    world: S.v2State.session, epoch: S.v2State.epoch};
  const currentStream = () => context === S.generation && streamGeneration === S.sonarAudioGeneration &&
    S.sonarAudioEnabled && S.session?.client_id === expectedSession.client_id &&
    S.session?.station_generation === expectedSession.station_generation &&
    S.session?.active_generation === expectedSession.active_generation &&
    S.v2State?.session === expectedSession.world && S.v2State?.epoch === expectedSession.epoch;
  // Same listener and lease, only the world epoch moved on (the host's local
  // input advances it): the next poll carries the new epoch and continues.
  const resumable = () => context === S.generation && streamGeneration === S.sonarAudioGeneration &&
    S.sonarAudioEnabled && S.session?.client_id === expectedSession.client_id &&
    S.session?.station_generation === expectedSession.station_generation &&
    S.session?.active_generation === expectedSession.active_generation;
  const controller = new AbortController();
  S.sonarAudioController = controller;
  const timeout = setTimeout(() => controller.abort(), 2000);
  let response;
  try {
    response = await fetch(audioPollRoutes[S.session?.station] ?? "/api/v2/sonar/audio", {
      method: "POST", credentials: "same-origin", cache: "no-store", redirect: "error", mode: "same-origin",
      signal: controller.signal,
      headers: {Accept: "audio/pcm", "Content-Type": "application/json", "X-U-Jagd-CSRF": expectedSession.csrf},
      body: JSON.stringify({protocol: 2, after: S.sonarAudioSequence, world_session: expectedSession.world,
        world_epoch: expectedSession.epoch, station_generation: expectedSession.station_generation,
        active_generation: expectedSession.active_generation}),
    });
    if (!currentStream()) return;
    if (response.status === 204) {
      if (![null, "0"].includes(response.headers.get("content-length"))) throw new Error("audio_protocol");
      renderSonarAudio("sonar_live_waiting");
      scheduleSonarAudioPoll(60);
      return;
    }
    if ([401, 403, 409].includes(response.status)) { stopSonarAudio("sonar_live_unavailable"); return; }
    if (response.status >= 500 || response.status === 429) {
      renderSonarAudio("sonar_live_waiting");
      return;
    }
    const sequence = Number(response.headers.get("x-u-jagd-audio-sequence"));
    const discontinuity = response.headers.get("x-u-jagd-audio-discontinuity");
    const contentType = (response.headers.get("content-type") || "").split(";", 1)[0].trim().toLowerCase();
    if (response.status !== 200 || contentType !== "audio/pcm" ||
        response.headers.get("x-u-jagd-pcm") !== "s16le" || response.headers.get("x-u-jagd-sample-rate") !== "4096" ||
        response.headers.get("x-u-jagd-audio-frames") !== "1024" ||
        !Number.isSafeInteger(sequence) || sequence < 1 || !["0", "1"].includes(discontinuity)) throw new Error("audio_protocol");
    const bytes = await readSonarPcm(response);
    if (!currentStream()) return;
    if (bytes.byteLength !== 2048) throw new Error("audio_protocol");
    const gap = discontinuity === "1" || S.sonarAudioSequence !== null && sequence !== S.sonarAudioSequence + 1;
    S.sonarAudioSequence = sequence;
    if (S.sonarAudioWorklet) {
      S.sonarAudioWorklet.port.postMessage({type: "pcm", sequence, bytes}, [bytes]);
      if (!S.sonarAudioMetrics.stale) renderSonarAudio("sonar_live_playing");
      return;
    }
    const view = new DataView(bytes);
    const outputFrames = Math.max(1, Math.round(1024 * S.audio.sampleRate / 4096));
    const buffer = S.audio.createBuffer(1, outputFrames, S.audio.sampleRate);
    const channel = buffer.getChannelData(0);
    for (let index = 0; index < outputFrames; index++) {
      const position = index * 4096 / S.audio.sampleRate;
      const left = Math.min(1023, Math.floor(position));
      const right = Math.min(1023, left + 1);
      const fraction = position - left;
      channel[index] = (view.getInt16(left * 2, true) * (1 - fraction) + view.getInt16(right * 2, true) * fraction) / 32768;
    }
    // An overrun skips old data, but audio already queued is still valid.
    // Keep its timeline and soften the first samples of the new block.
    if (gap) for (let index = 0; index < Math.min(channel.length, Math.round(S.audio.sampleRate * .01)); index++)
      channel[index] *= index / Math.max(1, Math.round(S.audio.sampleRate * .01));
    S.sonarAudioSources = S.sonarAudioSources.filter((source) => !source.__ended);
    if (S.sonarAudioSources.length >= sonarAudioMaxSources) throw new Error("audio_protocol");
    S.sonarAudioGain.gain.value = sonarGainValue();
    const start = S.sonarAudioNextTime > S.audio.currentTime + .03
      ? S.sonarAudioNextTime : S.audio.currentTime + sonarAudioStartLead;
    if (start > S.audio.currentTime + 7.0) throw new Error("audio_protocol");
    const source = S.audio.createBufferSource();
    source.buffer = buffer;
    source.connect(S.sonarAudioGain);
    source.__ended = false;
    source.onended = () => {
      source.__ended = true;
      source.disconnect();
      scheduleSonarAudioPoll(0);
    };
    source.start(start);
    S.sonarAudioNextTime = start + buffer.duration;
    S.sonarAudioSources.push(source);
    renderSonarAudio("sonar_live_playing");
    scheduleSonarAudioPoll(0);
  } catch (error) {
    if (currentStream()) {
      if (error.message === "audio_protocol") stopSonarAudio("sonar_live_failed");
      else renderSonarAudio("sonar_live_waiting");
    }
  } finally {
    clearTimeout(timeout);
    if (S.sonarAudioController === controller) S.sonarAudioController = null;
    // Every nonterminal exit must keep the stream alive, including timeouts
    // and session metadata refreshes concurrent with this request.
    if (currentStream()) scheduleSonarAudioPoll(response?.status === 200 ? 20 : 100);
    else if (resumable()) scheduleSonarAudioPoll(20);
  }
}
