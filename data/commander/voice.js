"use strict";
// Voice is an independent, transient browser channel. It never calls game commands.
(() => {
  const $ = (id) => document.getElementById(id);
  // Sender byte: the index in the host's ROLES order (frigate, then boat);
  // each unit's crew only ever hears its own unit.
  const stations = ["bridge", "sonar", "weapons", "damage", "opz", "radio",
    "engine", "helicopter", "eloka", "uboot", "uboot_sonar", "uboot_weapons",
    "uboot_engine", "uboot_esm", "uboot_nav", "uboot_radio"];
  let strings = {}, availability = null, socket = null, context = null;
  let stream = null, capture = null, held = false, ready = false, starting = false;
  let station = null, generation = 0, lastError = "";
  let translationSerial = 0;
  let nextPlay = 0;
  const t = (key) => strings[`commander.web.${key}`] || key;
  const label = (name) => t(`station_${name}`);

  async function translations() {
    const serial = ++translationSerial;
    const language = $("language").value === "de" ? "de" : "en";
    try {
      const response = await fetch(`/api/v2/ui?lang=${language}`, {cache: "no-store"});
      if (response.ok) {
        const values = await response.json();
        if (serial === translationSerial) strings = values;
      }
    } catch (_) { /* The next status poll can retry. */ }
    render();
  }

  function release() {
    if (!held) return;
    held = false;
    $("voice-ptt").setAttribute("aria-pressed", "false");
    capture?.port.postMessage("up");
    if (ready && socket?.readyState === WebSocket.OPEN) socket.send("up");
  }
  function press() {
    if (held || !ready || document.hidden || socket?.readyState !== WebSocket.OPEN) return;
    held = true;
    $("voice-ptt").setAttribute("aria-pressed", "true");
    socket.send("down");
    capture.port.postMessage("down");
  }
  function stop() {
    generation += 1;
    release();
    ready = false; starting = false;
    const oldSocket = socket; socket = null;
    if (oldSocket && oldSocket.readyState < WebSocket.CLOSING) oldSocket.close();
    stream?.getTracks().forEach((track) => track.stop()); stream = null;
    if (context) context.close(); context = null;
    capture = null; station = null; nextPlay = 0;
    render();
  }

  function render() {
    $("voice-enable").disabled = ready || starting || !availability?.enabled || !availability.station;
    $("voice-enable").textContent = t("voice_start");
    $("voice-stop").disabled = !ready && !starting;
    $("voice-stop").textContent = t("voice_stop");
    $("voice-ptt").disabled = !ready;
    $("voice-ptt").textContent = t("voice_ptt");
    $("voice-status").textContent = !availability?.enabled ? t("voice_disabled")
      : !availability.station ? t("voice_no_station")
      : lastError ? t(lastError)
      : availability.talker ? t("voice_talker").replace("{station}", label(availability.talker))
      : ready ? t("voice_ready") : t("voice_available");
  }

  function play(bytes) {
    if (!context || bytes.byteLength !== 1921) return;
    const sender = new Uint8Array(bytes)[0];
    if (sender >= stations.length) return;
    const pcm = new DataView(bytes, 1);
    const buffer = context.createBuffer(1, 960, 48000);
    const samples = buffer.getChannelData(0);
    for (let i = 0; i < 960; i++) samples[i] = pcm.getInt16(i * 2, true) / 32768;
    const source = context.createBufferSource();
    source.buffer = buffer; source.connect(context.destination);
    if (nextPlay < context.currentTime || nextPlay > context.currentTime + .3)
      nextPlay = context.currentTime + .06;
    source.start(nextPlay); nextPlay += .02;
  }

  async function start() {
    if (ready || starting || !availability?.enabled || !availability.station) return;
    starting = true;
    lastError = "";
    const started = generation;
    station = availability.station;
    render();
    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.AudioWorkletNode)
        throw new Error(t("voice_secure_context"));
      const voiceContext = new AudioContext({sampleRate: 48000});
      context = voiceContext;
      await voiceContext.resume();
      await voiceContext.audioWorklet.addModule("/voice-worklet.js");
      if (generation !== started) return;
      const acquired = await navigator.mediaDevices.getUserMedia({audio: {
        channelCount: 1, echoCancellation: true, noiseSuppression: true
      }});
      if (generation !== started) { acquired.getTracks().forEach((track) => track.stop()); return; }
      stream = acquired;
      const source = context.createMediaStreamSource(stream);
      const high = context.createBiquadFilter();
      high.type = "highpass"; high.frequency.value = 300;
      const low = context.createBiquadFilter();
      low.type = "lowpass"; low.frequency.value = 3400;
      const distortion = context.createWaveShaper();
      distortion.curve = Float32Array.from({length: 1024}, (_, i) =>
        Math.tanh(1.5 * (i / 511.5 - 1)) / Math.tanh(1.5));
      capture = new AudioWorkletNode(context, "crew-voice-capture");
      const silence = context.createGain(); silence.gain.value = 0;
      source.connect(high).connect(low).connect(distortion).connect(capture)
        .connect(silence).connect(context.destination);
      const scheme = location.protocol === "https:" ? "wss:" : "ws:";
      const currentSocket = new WebSocket(`${scheme}//${location.host}/ws/v2/voice`,
        ["u-jagd-voice-v2", `ujagd-csrf.${availability.csrf}`]);
      socket = currentSocket;
      socket.binaryType = "arraybuffer";
      capture.port.onmessage = ({data}) => {
        if (held && ready && socket === currentSocket &&
            currentSocket.readyState === WebSocket.OPEN && currentSocket.bufferedAmount < 32768)
          currentSocket.send(data);
      };
      socket.onmessage = (event) => {
        if (event.data instanceof ArrayBuffer) { play(event.data); return; }
        try {
          const message = JSON.parse(event.data);
          if (message.type === "ready" && message.station === station) {
            starting = false; ready = true; availability.talker = message.talker; render();
          } else if (message.type === "talker") {
            availability.talker = message.station; render();
          }
        } catch (_) { stop(); }
      };
      socket.onclose = () => { if (socket === currentSocket) {
        stop(); lastError = "voice_disconnected"; render();
      } };
      socket.onerror = () => { if (socket === currentSocket) {
        stop(); lastError = "voice_disconnected"; render();
      } };
    } catch (error) {
      stop(); lastError = error.message || "voice_error"; render();
    }
  }

  async function poll() {
    try {
      const response = await fetch("/api/v2/voice/status", {credentials: "same-origin", cache: "no-store"});
      if (!response.ok) {
        if (response.status === 401 || response.status === 403 || response.status === 404) {
          availability = null;
          if (ready || starting) stop();
          render();
        }
        return; // A busy server must not drop a working voice socket.
      }
      availability = await response.json();
      if ((ready || starting) && (!availability?.enabled || availability.station !== station)) stop();
    } catch (_) { return; }
    render();
  }

  $("voice-enable").addEventListener("click", start);
  $("voice-stop").addEventListener("click", stop);
  $("voice-ptt").addEventListener("pointerdown", (event) => {
    event.preventDefault(); $("voice-ptt").setPointerCapture(event.pointerId); press();
  });
  for (const name of ["pointerup", "pointercancel", "lostpointercapture"])
    $("voice-ptt").addEventListener(name, release);
  document.addEventListener("keydown", (event) => {
    const target = event.target;
    const editing = target instanceof Element && (
      target.closest("input, select, textarea, dialog[open]") || target.isContentEditable);
    if (event.code !== "KeyF" || event.repeat || event.ctrlKey || event.altKey || event.metaKey ||
        editing) return;
    if (ready) { event.preventDefault(); press(); }
  });
  document.addEventListener("keyup", (event) => { if (event.code === "KeyF") release(); });
  window.addEventListener("blur", release);
  document.addEventListener("visibilitychange", () => { if (document.hidden) release(); });
  $("language").addEventListener("change", translations);
  window.addEventListener("u-jagd-language", (event) => {
    translationSerial += 1;
    strings = event.detail.translations;
    render();
  });
  translations(); poll(); setInterval(poll, 2000);
})();
