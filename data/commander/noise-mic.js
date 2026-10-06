"use strict";
// Noise discipline (src/core/noise_discipline.py): the player's own
// microphone, opt-in and kept apart from the Commander app like voice.js.
// Nothing is recorded or played: only a loudness level 0..20 leaves this
// file, as a "u-jagd-mic" event the app sends on to the host.
(() => {
  const $ = (id) => document.getElementById(id);
  const MAX = 20, SAMPLE_MS = 100;
  let stream = null, context = null, analyser = null, buffer = null;
  let timer = 0, level = 0, starting = false;
  const emit = (detail) => window.dispatchEvent(new CustomEvent("u-jagd-mic", {detail}));

  function stop(failure = "") {
    clearInterval(timer); timer = 0;
    stream?.getTracks().forEach((track) => track.stop());
    stream = null; analyser = null; level = 0;
    if (context) context.close().catch(() => {});
    context = null;
    emit({on: false, level: 0, failure, attempt: Boolean(failure)});
  }

  function sample() {
    if (!analyser) return;
    analyser.getFloatTimeDomainData(buffer);
    let sum = 0;
    for (let i = 0; i < buffer.length; i += 1) sum += buffer[i] * buffer[i];
    const db = 20 * Math.log10(Math.sqrt(sum / buffer.length) + 1e-9);
    // -60 dBFS is silence, -10 dBFS a shout; the level falls back slowly.
    const now = Math.max(0, Math.min(MAX, Math.round((db + 60) / 50 * MAX)));
    level = Math.max(now, level - 1);
    emit({on: true, level, failure: ""});
  }

  async function start() {
    if (starting || stream) return;
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      emit({on: false, level: 0, failure: "mic_needs_https", attempt: true});
      return;
    }
    starting = true;
    try {
      stream = await navigator.mediaDevices.getUserMedia({audio: {
        echoCancellation: true, noiseSuppression: false, autoGainControl: false}});
      context = new AudioContext();
      analyser = context.createAnalyser();
      analyser.fftSize = 1024;
      buffer = new Float32Array(analyser.fftSize);
      context.createMediaStreamSource(stream).connect(analyser);
      timer = setInterval(sample, SAMPLE_MS);
      emit({on: true, level: 0, failure: ""});
    } catch (error) {
      // NotAllowedError: refused by the player or the browser settings;
      // NotFoundError/NotReadableError: no input or one held by another app.
      stop(error?.name === "NotFoundError" ? "mic_missing"
        : error?.name === "NotReadableError" ? "mic_busy" : "mic_denied");
    } finally {
      starting = false;
    }
  }

  $("mic-toggle")?.addEventListener("click", () => (stream || starting ? stop() : start()));
  window.addEventListener("u-jagd-mic-stop", () => { if (stream) stop(); });
  window.addEventListener("pagehide", () => { if (stream) stop(); });
})();

// The talk key (src/core/game_talk.py): while the player holds Shift+Space,
// the question is kept in memory, then handed to the app once as 16 kHz mono
// 16-bit PCM (base64) in a "u-jagd-talk" event; the app posts it to the host,
// whose speech input turns it into text. Nothing is stored or played.
(() => {
  const RATE = 16000, MAX_S = 20, BLOCK = 4096;
  let stream = null, context = null, node = null, source = null;
  let chunks = [], length = 0, starting = false, wanted = false;
  const emit = (detail) => window.dispatchEvent(new CustomEvent("u-jagd-talk", {detail}));

  function close() {
    node?.disconnect(); source?.disconnect();
    stream?.getTracks().forEach((track) => track.stop());
    if (context) context.close().catch(() => {});
    stream = null; context = null; node = null; source = null;
  }

  // Down to 16 kHz by averaging (the voice band survives, no aliasing worth naming).
  function resample(input, rate) {
    const step = rate / RATE;
    const out = new Float32Array(Math.floor(input.length / step));
    for (let i = 0; i < out.length; i += 1) {
      const from = Math.floor(i * step), to = Math.max(from + 1, Math.floor((i + 1) * step));
      let sum = 0;
      for (let j = from; j < to; j += 1) sum += input[j];
      out[i] = sum / (to - from);
    }
    return out;
  }

  function encode() {
    const total = Math.min(length, RATE * MAX_S);
    const pcm = new Uint8Array(total * 2);
    const view = new DataView(pcm.buffer);
    let offset = 0;
    for (const chunk of chunks) for (let i = 0; i < chunk.length && offset < total; i += 1, offset += 1) {
      view.setInt16(offset * 2, Math.max(-32768, Math.min(32767, Math.round(chunk[i] * 32767))), true);
    }
    let text = "";
    for (let i = 0; i < pcm.length; i += 0x8000) text += String.fromCharCode(...pcm.subarray(i, i + 0x8000));
    return btoa(text);
  }

  async function start() {
    wanted = true;
    if (starting || stream) return;
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      wanted = false;
      emit({state: "failed", failure: "mic_needs_https"});
      return;
    }
    starting = true;
    chunks = []; length = 0;
    try {
      stream = await navigator.mediaDevices.getUserMedia({audio: {
        channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true}});
      context = new AudioContext();
      source = context.createMediaStreamSource(stream);
      node = context.createScriptProcessor(BLOCK, 1, 1);
      const rate = context.sampleRate;
      node.onaudioprocess = (event) => {
        if (length >= RATE * MAX_S) return;
        const block = resample(event.inputBuffer.getChannelData(0), rate);
        chunks.push(block); length += block.length;
      };
      source.connect(node); node.connect(context.destination);
      emit({state: "recording"});
      if (!wanted) stop();
    } catch (error) {
      close();
      wanted = false;
      emit({state: "failed", failure: error?.name === "NotFoundError" ? "mic_missing"
        : error?.name === "NotReadableError" ? "mic_busy" : "mic_denied"});
    } finally {
      starting = false;
    }
  }

  function stop() {
    wanted = false;
    if (!stream) return;
    const audio = length ? encode() : "";
    chunks = []; length = 0;
    close();
    emit({state: "done", audio});
  }

  function cancel() {
    wanted = false;
    chunks = []; length = 0;
    if (stream) close();
  }

  window.addEventListener("u-jagd-talk-start", start);
  window.addEventListener("u-jagd-talk-stop", stop);
  window.addEventListener("u-jagd-talk-cancel", cancel);
  window.addEventListener("pagehide", cancel);
})();
