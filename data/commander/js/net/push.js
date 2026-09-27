import { S } from "../state/store.js";
import { emit } from "../core/events.js";
import { authenticated } from "../core/format.js";
import { poll } from "./poll.js";

// State push over /ws/v2/state: the host sends the role projection when it
// changes (same bytes as /state), a heartbeat every 2 s while idle.  The
// poll loop consumes pushed states in place of its /state request while the
// push is healthy and keeps polling session metadata, chart and feeds; two
// missed heartbeats put the loop back on its full polling cadence, and the
// socket is retried every 10 s.
export const push = {socket: null, generation: 0, retry: null, latest: null, lastMessage: 0, connected: false};
export const PUSH_HEARTBEAT_MS = 2000;
export const PUSH_RETRY_MS = 10000;

export function pushHealthy() {
  return push.connected && push.socket !== null && performance.now() - push.lastMessage <= 2 * PUSH_HEARTBEAT_MS + 500;
}

function markPush(state) {
  const value = pushHealthy() ? "on" : "off";
  if (document.body.dataset.push !== value) { document.body.dataset.push = value; emit("push", value); }
  if (state) emit("push", value);
}

export function stopStatePush(reason = "station context changed") {
  push.generation += 1;
  clearTimeout(push.retry);
  push.retry = null;
  const socket = push.socket;
  push.socket = null;
  push.connected = false;
  push.latest = null;
  if (socket) socket.close(1000, reason);
  markPush();
}

export function syncStatePush() {
  const allowed = authenticated() && S.session?.station !== null && !document.hidden && typeof window.WebSocket === "function";
  if (!allowed) { if (push.socket) stopStatePush(); return; }
  if (push.socket || push.retry) return;
  const generation = ++push.generation;
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  let socket;
  try { socket = new window.WebSocket(`${scheme}//${location.host}/ws/v2/state`, "u-jagd-state-v2"); }
  catch (_) { return; }
  push.socket = socket;
  socket.addEventListener("open", () => {
    if (generation !== push.generation || push.socket !== socket) { socket.close(); return; }
    push.connected = true;
    push.lastMessage = performance.now();
    markPush();
  });
  socket.addEventListener("message", (event) => {
    if (generation !== push.generation || push.socket !== socket || typeof event.data !== "string") return;
    let state;
    try { state = JSON.parse(event.data); } catch (_) { socket.close(4002, "invalid push frame"); return; }
    push.lastMessage = performance.now();
    if (state && state.heartbeat === true) { markPush(); return; }
    push.latest = state;
    markPush();
    poll();
  });
  socket.addEventListener("close", () => {
    if (push.socket === socket) push.socket = null;
    push.connected = false;
    push.latest = null;
    markPush();
    if (generation === push.generation && authenticated()) {
      push.retry = setTimeout(() => { push.retry = null; syncStatePush(); }, PUSH_RETRY_MS);
    }
  });
  socket.addEventListener("error", () => socket.close());
}

// The poll loop asks for a pushed state newer than its snapshot; a stale
// push (heartbeats missing) is never consumed.
export function takePushedState() {
  if (!pushHealthy() || !push.latest) return null;
  const state = push.latest;
  push.latest = null;
  return state;
}
