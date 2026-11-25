import { S } from "../state/store.js";

// ---- The host's voice ------------------------------------------------------------
// The executive officer's spoken answers (views/advisor.js) and the log read
// aloud (audio/log-voice.js) come from the host's speech service as 16-bit
// mono PCM.  Both play one after the other on one chain, each clip as one
// sound, so two voices never talk over each other.
const VOICE_MAX_BYTES = 16 * 1024 * 1024;
let chain = Promise.resolve();
let source = null;

export async function audioContext() {
  const Audio = window.AudioContext || window.webkitAudioContext;
  if (!Audio) return null;
  if (!S.audio) S.audio = new Audio();
  if (S.audio.state !== "running") await S.audio.resume().catch(() => {});
  return S.audio.state === "running" ? S.audio : null;
}

// Fetch one clip and play it; `wanted()` is asked again before it sounds.
async function play(url, wanted) {
  if (!wanted()) return;
  const response = await fetch(url, {
    cache: "no-store", credentials: "same-origin", redirect: "error", mode: "same-origin"});
  const rate = Number(response.headers.get("X-U-Jagd-Sample-Rate"));
  if (response.status !== 200 || response.headers.get("X-U-Jagd-PCM") !== "s16le" ||
      !(rate >= 8000 && rate <= 48000)) return;
  const raw = await response.arrayBuffer();
  if (raw.byteLength < 2 || raw.byteLength > VOICE_MAX_BYTES || !wanted()) return;
  const context = await audioContext();
  if (!context) return;
  const samples = new Int16Array(raw, 0, raw.byteLength >> 1);
  const buffer = context.createBuffer(1, samples.length, rate);
  const channel = buffer.getChannelData(0);
  for (let index = 0; index < samples.length; index++) channel[index] = samples[index] / 32768;
  const node = context.createBufferSource();
  node.buffer = buffer;
  node.connect(context.destination);
  source = node;
  await new Promise((resolve) => { node.onended = resolve; node.start(); });
  node.disconnect();
  if (source === node) source = null;
}

export function queueVoice(url, wanted) {
  chain = chain.then(() => play(url, wanted)).catch(() => {});
}

export function stopVoice() {
  try { source?.stop(); } catch (_) { /* already ended */ }
  source = null;
}
