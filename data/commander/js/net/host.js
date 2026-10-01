import { S } from "../state/store.js";
import { phases } from "../core/base.js";
import { emit } from "../core/events.js";
import { secureId } from "./commands.js";
import { poll } from "./poll.js";
import { request } from "./request.js";
import { forgetSession } from "./session.js";
import { boundedArray, exactKeys } from "../state/schema.js";

// Solo host surface: the published host view and the one host command in
// flight. Rendering follows via the "host" topic.
const hostResultText = {ok: "host_result_ok", phase_blocked: "host_result_phase_blocked",
  no_save: "host_result_no_save", save_failed: "host_result_save_failed",
  session_revoked: "host_result_session_revoked", stale_world_session: "host_result_stale",
  stale_world_epoch: "host_result_stale", stale_generation: "host_result_stale",
  role_revoked: "host_result_revoked", expired: "host_result_stale",
  context_invalidated: "host_result_stale"};
function validateHost(value) {
  const fields = ["epoch", "difficulty", "difficulty_fields", "phase", "protocol", "scenario", "scenarios", "session", "slots", "world_mode"];
  if (!exactKeys(value, fields) || value.protocol !== 2 || typeof value.session !== "string" ||
      !Number.isSafeInteger(value.epoch) || value.epoch < 0 ||
      !Object.hasOwn(phases, value.phase) ||
      !["fixed", "procedural", "real_fixed"].includes(value.world_mode) || typeof value.scenario !== "string" ||
      !boundedArray(value.difficulty_fields, 32) || !value.difficulty_fields.every((row) =>
        exactKeys(row, ["name", "kind", "min", "max", "step", "default"]) &&
        typeof row.name === "string" && ["int", "float"].includes(row.kind) &&
        Number.isFinite(row.min) && Number.isFinite(row.max) && row.min <= row.max &&
        Number.isFinite(row.step) && row.step > 0 &&
        Number.isFinite(row.default) && row.min <= row.default && row.default <= row.max) ||
      !exactKeys(value.difficulty, value.difficulty_fields.map((row) => row.name)) ||
      !value.difficulty_fields.every((row) => {
        const amount = value.difficulty[row.name];
        return row.kind === "int" ? Number.isInteger(amount) && amount >= row.min && amount <= row.max :
          Number.isFinite(amount) && amount >= row.min && amount <= row.max;
      }) ||
      !boundedArray(value.scenarios, 16) || !value.scenarios.every((row) => exactKeys(row, ["key", "fixed", "side"]) &&
        typeof row.key === "string" && typeof row.fixed === "boolean" && ["frigate", "uboot"].includes(row.side)) ||
      !boundedArray(value.slots, 8) || !value.slots.every((row) => exactKeys(row, ["slot", "saved", "modified"]) &&
        Number.isSafeInteger(row.slot) && row.slot >= 1 && typeof row.saved === "boolean" &&
        (row.modified === null || Number.isSafeInteger(row.modified)))) throw new Error("protocol");
}
export async function pollHost(context) {
  try {
    const next = await request("/host", {guard: () => context === S.generation});
    if (context !== S.generation) return;
    validateHost(next);
    S.hostView = next;
  } catch (error) {
    // The host surface can be withdrawn while the session lives: 403 only
    // means "refresh the session", it is not an expired login.
    if (error.status !== 403) throw error;
    S.hostView = null;
    S.lastSessionFetch = 0;
  }
  if (S.hostPending) await pollHostResult(context);
}
function setHostMessage(message) {
  S.hostMessage = message;
  clearTimeout(S.hostMessageTimer);
  if (message && message.status !== "pending") {
    S.hostMessageTimer = setTimeout(() => { S.hostMessage = null; emit("host"); }, 6000);
  }
  emit("host");
}
export async function sendHostAction(action, params) {
  if (!S.session?.host || !S.hostView || S.hostPending || !S.connected) return;
  let id;
  try { id = secureId(); } catch (_) {
    setHostMessage({key: "command_no_crypto", status: "rejected"});
    return;
  }
  const body = Object.freeze({protocol: 2, id, seq: S.nextCommandSeq, station: "host",
    station_generation: S.session.host.generation, active_generation: 0,
    world_session: S.hostView.session, world_epoch: S.hostView.epoch, resource_revision: 0,
    action, params: Object.freeze(params)});
  S.hostPending = {id, seq: body.seq, action};
  setHostMessage({key: "host_result_pending", status: "pending"});
  const context = S.generation;
  try {
    await request("/commands", {method: "POST", body, expected: 202, csrf: S.session.csrf,
      guard: () => context === S.generation && S.hostPending?.id === id});
    S.nextCommandSeq += 1;
    clearTimeout(S.pollTimer);
    if (!S.polling) poll();
  } catch (error) {
    if (context !== S.generation || S.hostPending?.id !== id || error.message === "cancelled") return;
    S.hostPending = null;
    if (error.status === 401) forgetSession("connection_expired");
    else if (error.status === 409 || error.status === 403) {
      S.lastSessionFetch = 0;
      setHostMessage({key: "host_result_stale", status: "rejected"});
    } else setHostMessage({key: "host_result_rejected", status: "rejected"});
  }
}
async function pollHostResult(context) {
  const command = S.hostPending;
  const payload = await request("/results", {guard: () => context === S.generation && S.hostPending === command});
  if (context !== S.generation || S.hostPending !== command || !exactKeys(payload, ["protocol", "results"]) ||
      payload.protocol !== 2 || !boundedArray(payload.results, 64)) throw new Error("results");
  const result = payload.results.find((item) => exactKeys(item, ["id", "seq", "status", "reasoncode"]) &&
    item.id === command.id && item.seq === command.seq && ["applied", "rejected"].includes(item.status) &&
    typeof item.reasoncode === "string" && item.reasoncode.length <= 64);
  if (!result) return;
  S.hostPending = null;
  setHostMessage({key: hostResultText[result.reasoncode] ?? "host_result_rejected",
    status: result.status});
}
