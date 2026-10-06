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
  no_mission: "host_result_no_mission", mission_rejected: "host_result_mission_rejected",
  no_save: "host_result_no_save", save_failed: "host_result_save_failed",
  session_revoked: "host_result_session_revoked", stale_world_session: "host_result_stale",
  stale_world_epoch: "host_result_stale", stale_generation: "host_result_stale",
  role_revoked: "host_result_revoked", expired: "host_result_stale",
  context_invalidated: "host_result_stale", use_lobby: "host_result_use_lobby",
  lobby_counting: "host_result_lobby_counting", lobby_invalid: "host_result_lobby_invalid",
  lobby_confirm: "host_result_lobby_confirm", campaign_unavailable: "host_result_campaign_unavailable",
  lead_unavailable: "host_result_lead_unavailable"};
const SIDES = ["frigate", "uboot"];
// A campaign of one side in the leader's lobby view.
function validCampaign(value) {
  return exactKeys(value, ["status", "port", "lage", "missions", "missions_max", "hotspots"]) &&
    ["none", "active", "won", "lost", "draw"].includes(value.status) && typeof value.port === "boolean" &&
    [value.lage, value.missions, value.missions_max].every((amount) => Number.isSafeInteger(amount) && amount >= 0 && amount <= 1000) &&
    boundedArray(value.hotspots, 16) && value.hotspots.every((spot) =>
      exactKeys(spot, ["id", "name", "scenario", "role"]) && Number.isSafeInteger(spot.id) && spot.id >= 0 && spot.id <= 9999 &&
      typeof spot.name === "string" && spot.name.length <= 48 && typeof spot.scenario === "string" && spot.scenario.length <= 32 &&
      typeof spot.role === "string" && spot.role.length <= 16);
}
// The service record (host_records.py): both sides, bounded lists.
const NAME = /^[a-z][a-z0-9_]{0,23}$/;
const shortText = (value, limit) => typeof value === "string" && value.length <= limit;
const count = (value) => Number.isSafeInteger(value) && value >= 0;
function validLogbookSide(side) {
  return exactKeys(side, ["missions", "wins", "best", "awards", "recent", "known", "ribbons"]) &&
    count(side.missions) && count(side.wins) &&
    boundedArray(side.best, 12) && side.best.every((row) => exactKeys(row, ["scenario", "score"]) &&
      shortText(row.scenario, 64) && Number.isSafeInteger(row.score)) &&
    boundedArray(side.awards, 16) && side.awards.every((row) => exactKeys(row, ["award", "date"]) &&
      NAME.test(row.award) && (row.date === null || shortText(row.date, 16))) &&
    boundedArray(side.recent, 8) && side.recent.every((row) =>
      exactKeys(row, ["date", "scenario", "level", "won", "score", "minutes", "marks"]) &&
      shortText(row.date, 16) && shortText(row.scenario, 64) && NAME.test(row.level) &&
      typeof row.won === "boolean" && Number.isSafeInteger(row.score) && count(row.minutes) &&
      boundedArray(row.marks, 2) && row.marks.every((mark) => ["advisor", "experimental"].includes(mark))) &&
    boundedArray(side.known, 8) && side.known.every((habit) => NAME.test(habit)) &&
    boundedArray(side.ribbons, 32) && side.ribbons.every((row) => exactKeys(row, ["scenario", "won"]) &&
      shortText(row.scenario, 64) && typeof row.won === "boolean");
}
export function validLogbook(value) {
  if (value === null) return true;
  return exactKeys(value, ["learns", "sides"]) && typeof value.learns === "boolean" &&
    exactKeys(value.sides, ["frigate", "boat"]) && validLogbookSide(value.sides.frigate) &&
    validLogbookSide(value.sides.boat);
}
const validLessons = (value) => boundedArray(value, 16) && value.every((row) =>
  exactKeys(row, ["key", "side", "done", "next"]) && NAME.test(row.key) && SIDES.includes(row.side) &&
  typeof row.done === "boolean" && typeof row.next === "boolean");
// Server mode: the leader's lobby choices (null outside the lobby).
function validLeaderLobby(value) {
  if (value === null) return true;
  return exactKeys(value, ["choice", "side", "versus", "weather", "time", "length", "countdown_s", "confirm", "daily", "campaign"]) &&
    typeof value.choice === "string" && value.choice.length <= 96 && SIDES.includes(value.side) &&
    ["ai", "crew"].includes(value.versus) &&
    [value.weather, value.time, value.length].every((choice) => typeof choice === "string" && choice.length <= 16) &&
    (value.countdown_s === null || Number.isFinite(value.countdown_s) && value.countdown_s >= 0 && value.countdown_s <= 60) &&
    typeof value.confirm === "boolean" && exactKeys(value.daily, SIDES) &&
    SIDES.every((side) => value.daily[side] === null || typeof value.daily[side] === "string" && value.daily[side].length <= 32) &&
    exactKeys(value.campaign, SIDES) && SIDES.every((side) => validCampaign(value.campaign[side]));
}
function validateHost(value) {
  const fields = ["epoch", "difficulty", "difficulty_fields", "lessons", "lobby", "logbook", "missions_revision", "phase", "protocol", "scenario", "scenarios", "session", "slots", "world_mode"];
  if (!exactKeys(value, fields) || value.protocol !== 2 || typeof value.session !== "string" ||
      !Number.isSafeInteger(value.epoch) || value.epoch < 0 ||
      !Number.isSafeInteger(value.missions_revision) || value.missions_revision < 0 ||
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
      !boundedArray(value.scenarios, 128) || !value.scenarios.every((row) => exactKeys(row, ["key", "fixed", "side"]) &&
        typeof row.key === "string" && typeof row.fixed === "boolean" && ["frigate", "uboot"].includes(row.side)) ||
      !validLeaderLobby(value.lobby) || !validLogbook(value.logbook) || !validLessons(value.lessons) ||
      !boundedArray(value.slots, 8) || !value.slots.every((row) => exactKeys(row, ["slot", "saved", "modified"]) &&
        Number.isSafeInteger(row.slot) && row.slot >= 1 && typeof row.saved === "boolean" &&
        (row.modified === null || Number.isSafeInteger(row.modified)))) throw new Error("protocol");
}
export async function pollHost(context) {
  try {
    const next = await request("/host", {guard: () => context === S.generation});
    if (context !== S.generation) return;
    validateHost(next);
    const missionsChanged = S.hostView?.missions_revision !== next.missions_revision;
    S.hostView = next;
    // The own-mission library changed on the host: refresh it when shown.
    if (missionsChanged) emit("missions-revision");
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
// A host command can be sent: solo host, nothing in flight, connected, and a
// host view of the world the console shows. A side switch re-leases every
// station (a new world session or epoch); the console first resyncs its new
// station, and a host view polled just before the switch landed would make
// the command stale.
const hostActionReady = () => Boolean(S.session?.host && S.hostView && !S.hostPending && S.connected &&
  S.v2State && S.hostView.session === S.v2State.session && S.hostView.epoch === S.v2State.epoch);
// Send once the console is ready again (after a side switch), instead of
// dropping the command silently while it resyncs; a console that does not
// become ready reports the command as stale.
export async function sendHostActionWhenReady(action, params, limitMs = 15000) {
  const context = S.generation;
  const deadline = performance.now() + limitMs;
  while (!hostActionReady()) {
    if (context !== S.generation) return;
    if (performance.now() >= deadline) {
      setHostMessage({key: "host_result_stale", status: "rejected"});
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  await sendHostAction(action, params);
}
// The server-mode leader may hold no station: its lobby link counts.
const hostLinked = () => S.connected || Boolean(S.session?.host?.leader) && S.linkState === "lobby";
export async function sendHostAction(action, params) {
  if (!S.session?.host || !S.hostView || S.hostPending || !hostLinked()) return;
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
