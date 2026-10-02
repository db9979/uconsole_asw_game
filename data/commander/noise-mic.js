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
    emit({on: false, level: 0, failure});
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
      emit({on: false, level: 0, failure: "mic_needs_https"});
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
    } catch (_) {
      stop("mic_denied");
    } finally {
      starting = false;
    }
  }

  $("mic-toggle")?.addEventListener("click", () => (stream || starting ? stop() : start()));
  window.addEventListener("u-jagd-mic-stop", () => { if (stream) stop(); });
  window.addEventListener("pagehide", () => { if (stream) stop(); });
})();
