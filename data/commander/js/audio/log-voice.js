import { S } from "../state/store.js";
import { $ } from "../core/base.js";
import { request } from "../net/request.js";
import { boundedArray, exactKeys } from "../state/schema.js";
import { audioContext, queueVoice, stopVoice } from "./host-voice.js";

// ---- The log read aloud (src/commander/log_voice_web.py) -------------------------
// While "Read the log aloud" is on, the browser asks the host about once a
// second for the clips of its own side's log and plays each new one with the
// host's voice, every station with its own voice and net.  Entries the crew
// calls out are skipped while "Speak crew reports" says them here already.
// Without the host's voice the switch stays hidden and nothing is asked.
const POLL_MS = 1200;
const PROBE_MS = 15000;
const state = {timer: null, heard: null, on: false, context: null};

export function validLogVoice(value) {
  return exactKeys(value, ["protocol", "on", "clips"]) && value.protocol === 2 &&
    typeof value.on === "boolean" && boundedArray(value.clips, 16) &&
    value.clips.every((row) => exactKeys(row, ["seq", "group", "called"]) && Number.isInteger(row.seq) &&
      row.seq > 0 && typeof row.group === "string" && typeof row.called === "boolean");
}

function wanted() { return $("log-voice")?.checked === true && !document.hidden; }

function context() {
  // A crew page holding a station: never the lookout phones or the lobby.
  return S.session?.station ? `${S.generation}:${S.session.station}` : null;
}

// Listening: the host reads this side's log while the browser asks.
async function listen() {
  clearTimeout(state.timer);
  state.timer = null;
  if (!wanted()) return;
  const here = context();
  if (here !== null) {
    try {
      const value = await request("/voice/log");
      if (validLogVoice(value)) {
        state.on = value.on;
        if (here !== state.context) {
          // A new station or side: start after what is already there.
          state.context = here;
          state.heard = null;
        }
        const latest = value.clips.reduce((top, row) => Math.max(top, row.seq), 0);
        if (state.heard === null) state.heard = latest;
        for (const row of value.clips) {
          if (row.seq <= state.heard || row.called && S.speechEnabled) continue;
          queueVoice(`/api/v2/voice/log?seq=${row.seq}`, wanted);
        }
        state.heard = Math.max(state.heard, latest);
      }
    } catch (_) { /* the next poll retries */ }
  }
  render();
  if (wanted()) state.timer = setTimeout(listen, POLL_MS);
}

// Not listening: only whether the host reads aloud at all (shows the switch).
async function probe() {
  if (context() === null || wanted()) return;
  try {
    const value = await request("/voice/log?probe=1");
    if (validLogVoice(value)) state.on = value.on;
  } catch (_) { /* keep the last answer */ }
  render();
}

function render() {
  const label = $("log-voice")?.closest("label");
  if (label) label.hidden = !state.on && !$("log-voice").checked;
}

export function init() {
  const box = $("log-voice");
  if (!box) return;
  box.addEventListener("change", () => {
    if (box.checked) { audioContext(); state.heard = null; listen(); } else stopVoice();
  });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) listen(); });
  setInterval(probe, PROBE_MS);
  probe();
}
