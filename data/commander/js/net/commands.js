import { S } from "../state/store.js";
import { emit } from "../core/events.js";
import { finite } from "../core/format.js";
import { request } from "./request.js";
import { forgetSession, setConnection } from "./session.js";
import { bridgeOrderAvailable, stationActionAvailable } from "../state/availability.js";
import { boundedArray, exactKeys } from "../state/schema.js";

export function secureId() {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
// Posts a bridge order; the view validates the form and passes the number.
export async function sendBridgeOrder(kind, value) {
  if (!bridgeOrderAvailable(kind)) return;
  const maximum = kind === "course" ? 360 : S.v2State.bridge.orders.speed_max_kn;
  if (!finite(value) || value < 0 || value > maximum || (kind === "course" && value === 360)) {
    S.commandMessage = {key: "bridge_order_invalid", status: "rejected"};
    emit("command", true);
    return;
  }
  let id;
  try { id = secureId(); } catch (_) {
    S.commandMessage = {key: "command_no_crypto", status: "rejected"};
    emit("command", true);
    return;
  }
  const body = Object.freeze({protocol: 2, id, seq: S.nextCommandSeq,
    station: "bridge", station_generation: S.session.station_generation,
    active_generation: S.session.active_generation,
    world_session: S.v2State.session, world_epoch: S.v2State.epoch,
    resource_revision: S.v2State.revision, action: `bridge_set_${kind}`,
    params: Object.freeze({[kind === "course" ? "course" : "speed_kn"]: value})});
  S.pending = {id, body, uncertain: false, inFlight: true, retryAt: 0};
  S.commandMessage = null;
  emit("command", true);
  const context = S.generation;
  try {
    await request("/commands", {method: "POST", body, expected: 202, csrf: S.session.csrf,
      guard: () => context === S.generation && S.pending?.id === id});
    S.nextCommandSeq += 1;
  } catch (error) {
    if (context !== S.generation || S.pending?.id !== id || error.message === "cancelled") return;
    S.pending.uncertain = true;
    if (error.status === 401 || error.status === 403) forgetSession("connection_expired");
    else if (!error.status || error.status >= 500) setConnection("stale");
    else { S.commandMessage = {key: "bridge_order_http_rejected", status: "rejected", reasoncode: "action_rejected"}; S.pending = null; }
  } finally {
    if (S.pending?.id === id) {
      S.pending.inFlight = false;
      S.pending.retryAt = performance.now() + 5000;
    }
    emit("command", true);
  }
}
export async function sendStationAction(action, params) {
  if (!stationActionAvailable()) return;
  let id;
  try { id = secureId(); } catch (_) {
    S.commandMessage = {key: "command_no_crypto", status: "rejected"};
    emit("command", false);
    return;
  }
  const body = Object.freeze({protocol: 2, id, seq: S.nextCommandSeq,
    station: S.session.station, station_generation: S.session.station_generation,
    active_generation: S.session.active_generation,
    world_session: S.v2State.session, world_epoch: S.v2State.epoch,
    resource_revision: S.v2State.revision, action, params: Object.freeze(params)});
  S.pending = {id, body, uncertain: false, inFlight: true, retryAt: 0};
  if (action === "sonar_set_focus") S.requestedSonarFocus = params.ref;
  S.commandMessage = null;
  emit("command", false);
  const context = S.generation;
  try {
    await request("/commands", {method: "POST", body, expected: 202, csrf: S.session.csrf,
      guard: () => context === S.generation && S.pending?.id === id});
    S.nextCommandSeq += 1;
  } catch (error) {
    if (context !== S.generation || S.pending?.id !== id || error.message === "cancelled") return;
    S.pending.uncertain = true;
    if (error.status === 401 || error.status === 403) forgetSession("connection_expired");
    else if (!error.status || error.status >= 500) setConnection("stale");
    else {
      S.commandMessage = {key: "command_rejected", status: "rejected", reasoncode: "action_rejected"};
      if (action === "sonar_set_focus") S.requestedSonarFocus = null;
      S.pending = null;
    }
  } finally {
    if (S.pending?.id === id) {
      S.pending.inFlight = false;
      S.pending.retryAt = performance.now() + 5000;
    }
    emit("command", false);
  }
}
export async function retryPendingCommand() {
  const command = S.pending;
  if (!command?.uncertain || command.inFlight || performance.now() < command.retryAt ||
      !S.connected || S.session?.grants.command !== true ||
      command.body.station !== S.session.station || command.body.station_generation !== S.session.station_generation ||
      command.body.active_generation !== S.session.active_generation ||
      command.body.world_session !== S.v2State?.session || command.body.world_epoch !== S.v2State?.epoch) return;
  command.inFlight = true;
  emit("command", false);
  const context = S.generation;
  try {
    await request("/commands", {method: "POST", body: command.body, expected: 202, csrf: S.session.csrf,
      guard: () => context === S.generation && S.pending === command});
    S.nextCommandSeq = Math.max(S.nextCommandSeq, command.body.seq + 1);
  } catch (error) {
    if (context !== S.generation || S.pending !== command || error.message === "cancelled") return;
    if (error.status === 401 || error.status === 403) forgetSession("connection_expired");
    else if (!error.status || error.status >= 500) setConnection("stale");
  } finally {
    if (S.pending === command) {
      command.inFlight = false;
      command.retryAt = performance.now() + 5000;
      emit("command", false);
    }
  }
}
export async function pollV2Result(context) {
  const command = S.pending;
  const payload = await request("/results", {guard: () => context === S.generation && S.pending === command});
  if (context !== S.generation || S.pending !== command || !exactKeys(payload, ["protocol", "results"]) ||
      payload.protocol !== 2 || !boundedArray(payload.results, 64)) throw new Error("results");
  const result = payload.results.find((item) => exactKeys(item, ["id", "seq", "status", "reasoncode"]) &&
    item.id === command.id && item.seq === command.body.seq && ["applied", "rejected"].includes(item.status) &&
    typeof item.reasoncode === "string" && item.reasoncode.length <= 64);
  if (!result) return;
  const bridge = command.body.action.startsWith("bridge_");
  S.commandMessage = {key: result.status === "applied" ?
    (bridge ? "bridge_order_applied" : "command_applied") :
    (bridge ? "bridge_order_rejected" : "command_rejected"),
    status: result.status, reasoncode: result.reasoncode};
  if (result.status === "rejected" && command.body.action === "sonar_set_focus") S.requestedSonarFocus = null;
  S.pending = null;
  // The snapshot in hand predates the result: keep the operator's picks until
  // the next one, which carries the command's effect (see poll.js).
  S.clearDraftsAfter = S.snapshot?.seq ?? -1;
  emit("command:settled");
}
