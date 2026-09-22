const $ = (id) => document.getElementById(id);
const stations = ["bridge", "sonar", "navigation", "weapons", "radio", "esm", "engine", "damage", "helicopter"];
let socket, context, microphone, capture, held = false, ready = false;
let nextPlay = 0;

function status(message) { $("status").textContent = message; }
function release() {
  if (!held) return;
  held = false;
  $("ptt").setAttribute("aria-pressed", "false");
  capture?.port.postMessage("up");
  if (socket?.readyState === WebSocket.OPEN && ready) socket.send('"ptt_up"');
}
function press() {
  if (held || !ready || document.hidden || socket?.readyState !== WebSocket.OPEN) return;
  held = true;
  $("ptt").setAttribute("aria-pressed", "true");
  socket.send('"ptt_down"');
  capture.port.postMessage("down");
}

function playPcm(bytes) {
  if (!context || bytes.byteLength !== 1921) return;
  const sender = new Uint8Array(bytes)[0];
  if (sender >= stations.length) return;
  const pcm = new DataView(bytes, 1);
  const buffer = context.createBuffer(1, 960, 48000);
  const output = buffer.getChannelData(0);
  for (let i = 0; i < 960; i++) output[i] = pcm.getInt16(i * 2, true) / 32768;
  const source = context.createBufferSource();
  source.buffer = buffer;
  source.connect(context.destination);
  // A small jitter buffer; discard stale audio instead of growing latency.
  if (nextPlay < context.currentTime || nextPlay > context.currentTime + .3)
    nextPlay = context.currentTime + .06;
  source.start(nextPlay);
  nextPlay += .02;
}

async function connect() {
  $("connect").disabled = true;
  try {
    if (!navigator.mediaDevices?.getUserMedia || !window.AudioWorkletNode)
      throw new Error("Mikrofon und AudioWorklet benötigen HTTPS oder localhost.");
    const station = $("station").value;
    const code = $("code").value;
    if (!code) throw new Error("Funkcode eingeben.");
    // Create playback context inside the button gesture for Chrome autoplay.
    context = new AudioContext({sampleRate: 48000});
    await context.resume();
    const scheme = location.protocol === "https:" ? "wss:" : "ws:";
    const wsPort = Number(location.port || (location.protocol === "https:" ? 443 : 80)) + 1;
    socket = new WebSocket(`${scheme}//${location.hostname}:${wsPort}`);
    socket.binaryType = "arraybuffer";
    await new Promise((resolve, reject) => {
      socket.onopen = resolve;
      socket.onerror = () => reject(new Error("Funkserver nicht erreichbar."));
    });
    socket.send(JSON.stringify({type: "join", station, code}));
    $("code").value = "";
    const hello = await new Promise((resolve, reject) => {
      socket.onmessage = (event) => resolve(event.data);
      socket.onclose = () => reject(new Error("Code falsch oder Station bereits belegt."));
    });
    if (JSON.parse(hello).type !== "ready") throw new Error("Ungültige Serverantwort.");
    await context.audioWorklet.addModule("capture-worklet.js");
    microphone = await navigator.mediaDevices.getUserMedia({audio: {
      channelCount: 1, echoCancellation: true, noiseSuppression: true
    }});
    const source = context.createMediaStreamSource(microphone);
    const highpass = context.createBiquadFilter();
    highpass.type = "highpass"; highpass.frequency.value = 300;
    const lowpass = context.createBiquadFilter();
    lowpass.type = "lowpass"; lowpass.frequency.value = 3400;
    const distortion = context.createWaveShaper();
    distortion.curve = Float32Array.from({length: 1024}, (_, i) =>
      Math.tanh(1.5 * (i / 511.5 - 1)) / Math.tanh(1.5));
    capture = new AudioWorkletNode(context, "radio-capture");
    const silent = context.createGain(); silent.gain.value = 0;
    source.connect(highpass).connect(lowpass).connect(distortion).connect(capture)
      .connect(silent).connect(context.destination);
    capture.port.onmessage = ({data}) => {
      if (held && ready && socket.readyState === WebSocket.OPEN && socket.bufferedAmount < 32768)
        socket.send(data);
    };
    await context.resume();
    ready = true;
    $("ptt").disabled = false;
    $("station").disabled = true;
    status("Verbunden. F oder Taste gedrückt halten.");
    socket.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) { playPcm(event.data); return; }
      const message = JSON.parse(event.data);
      if (message.type === "talker")
        status(message.station ? `${message.station} sendet` : "Funk frei");
    };
    socket.onclose = () => {
      release(); ready = false; $("ptt").disabled = true;
      microphone?.getTracks().forEach((track) => track.stop());
      context?.close(); context = null;
      status("Verbindung beendet; Seite neu laden zum Wiederverbinden.");
    };
  } catch (error) {
    socket?.close(); microphone?.getTracks().forEach((track) => track.stop());
    context?.close(); context = null;
    $("connect").disabled = false;
    status(error.message);
  }
}

$("connect").addEventListener("click", connect);
$("ptt").addEventListener("pointerdown", (event) => {
  event.preventDefault(); $("ptt").setPointerCapture(event.pointerId); press();
});
for (const name of ["pointerup", "pointercancel", "lostpointercapture"])
  $("ptt").addEventListener(name, release);
document.addEventListener("keydown", (event) => {
  if (event.code === "KeyF" && !event.repeat && !["INPUT", "SELECT"].includes(document.activeElement.tagName)) {
    event.preventDefault(); press();
  }
});
document.addEventListener("keyup", (event) => { if (event.code === "KeyF") release(); });
window.addEventListener("blur", release);
document.addEventListener("visibilitychange", () => { if (document.hidden) release(); });
