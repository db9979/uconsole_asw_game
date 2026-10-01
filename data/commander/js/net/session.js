import { S } from "../state/store.js";
import { emit } from "../core/events.js";
import { audioRoles, directFireRoles, sessionRoles } from "../core/base.js";
import { finite } from "../core/format.js";
import { request } from "./request.js";
import { exactKeys } from "../state/schema.js";
import { lookoutView, view } from "../state/shared.js";

// Link state for the whole client; views follow via the "connection" topic.
export function setConnection(state, message = null) {
  S.linkState = state;
  S.connected = state === "connected";
  emit("connection", message);
}
export function forgetSession(message = "connection_unpaired") {
  emit("session:forgetting");
  S.generation += 1;
  S.session = null;
  S.activatingStation = null;
  S.stationPickerOpen = false;
  S.lastSessionFetch = 0;
  S.activeRequest?.abort();
  clearTimeout(S.pollTimer);
  emit("role:clear");
  S.snapshot = null;
  S.chart = null;
  S.chartSession = null;
  S.chartEpoch = null;
  S.chartRole = null;
  S.selected = null;
  S.pending = null;
  S.commandMessage = null;
  view.initialized = false;
  lookoutView.rangeNm = 100;
  S.failures = 0;
  S.lastSuccess = 0;
  S.latestSimlogState = null;
  S.proposals = null;
  S.eventContext = null;
  S.eventHighWater = 0;
  S.eventHistory = [];
  S.lobbyMessage = null;
  S.lobbyRoomMessage = null;
  S.stationMutation = false;
  S.hostView = null;
  S.hostPending = null;
  S.hostMessage = null;
  emit("session:forgotten");
  setConnection("unpaired", message);
}
// The host's open multiplayer lobby: mission, the uConsole's unit and
// station, the countdown and every crew browser with its ready tick.
function validLobby(lobby) {
  if (lobby === null) return true;
  return exactKeys(lobby, ["mission", "mission_name", "side", "host_station", "countdown_s", "ready", "players"]) &&
    typeof lobby.mission === "string" && lobby.mission.length <= 32 &&
    (lobby.mission_name === null || typeof lobby.mission_name === "string" && lobby.mission_name.length <= 80) &&
    ["frigate", "uboot"].includes(lobby.side) && (lobby.host_station === null || sessionRoles.includes(lobby.host_station)) &&
    (lobby.countdown_s === null || finite(lobby.countdown_s) && lobby.countdown_s >= 0 && lobby.countdown_s <= 60) &&
    typeof lobby.ready === "boolean" && Array.isArray(lobby.players) && lobby.players.length <= 12 &&
    lobby.players.every((player) => exactKeys(player, ["name", "stations", "ready", "observer", "you"]) &&
      typeof player.name === "string" && player.name.length >= 1 && player.name.length <= 32 &&
      Array.isArray(player.stations) && player.stations.length <= sessionRoles.length &&
      player.stations.every((station) => sessionRoles.includes(station)) &&
      typeof player.ready === "boolean" && typeof player.observer === "boolean" && typeof player.you === "boolean");
}
// Crewmates asking for a station this browser holds: it hands it over or
// keeps it (POST /stations/handover). Requester name and ordinal only.
function validHandover(value) {
  if (!Array.isArray(value.handover) || value.handover.length > 16) return false;
  if (value.observer && value.handover.length) return false;
  return value.handover.every((entry) => exactKeys(entry, ["station", "name", "ordinal", "request_generation"]) &&
    sessionRoles.includes(entry.station) && value.stations[entry.station].status === "mine" &&
    typeof entry.name === "string" && entry.name.length >= 1 && entry.name.length <= 32 &&
    Number.isSafeInteger(entry.ordinal) && entry.ordinal >= 0 && entry.ordinal !== value.ordinal &&
    Number.isSafeInteger(entry.request_generation) && entry.request_generation >= 1);
}
export function validateSession(value) {
  const fields = ["active_generation", "active_station", "client_id", "csrf", "grants", "handover", "name", "host", "lobby", "next_command_seq", "observer", "ordinal", "presence", "protocol", "requested_station", "simlog", "station", "station_generation", "stations"];
  if (!value || typeof value !== "object" || Array.isArray(value) ||
      Object.keys(value).sort().join(",") !== fields.sort().join(",") || value.protocol !== 2 ||
      typeof value.client_id !== "string" || !value.client_id || value.client_id.length > 128 ||
      typeof value.name !== "string" || value.name.length < 1 || value.name.length > 32 ||
      typeof value.csrf !== "string" || !value.csrf || value.csrf.length > 256 ||
       !Number.isSafeInteger(value.ordinal) || value.ordinal < 0 ||
      !Number.isSafeInteger(value.active_generation) || value.active_generation < 0 ||
      !Number.isSafeInteger(value.station_generation) || value.station_generation < 0 ||
      !Number.isSafeInteger(value.next_command_seq) || value.next_command_seq < 0 ||
      !finite(value.presence) || value.presence < 0 ||
      (value.station !== null && !sessionRoles.includes(value.station)) ||
      (value.requested_station !== null && !sessionRoles.includes(value.requested_station)) ||
      !value.grants || typeof value.grants !== "object" || Array.isArray(value.grants) ||
      Object.keys(value.grants).sort().join(",") !== "command,direct_fire,simlog,sonar_audio" ||
      Object.values(value.grants).some((grant) => typeof grant !== "boolean") ||
      (value.grants.command && value.station === null) ||
      (value.grants.direct_fire && (!value.grants.command || !directFireRoles.has(value.station))) ||
      (value.grants.sonar_audio && !audioRoles.has(value.station)) ||
      typeof value.simlog !== "boolean" || value.grants.simlog !== value.simlog ||
      typeof value.observer !== "boolean" || (value.observer && (value.grants.command || value.host !== null || !value.simlog)) ||
      (value.host !== null && (!exactKeys(value.host, ["generation"]) ||
        !Number.isSafeInteger(value.host.generation) || value.host.generation < 0)) ||
      value.active_station !== value.station || !validLobby(value.lobby) ||
      !value.stations || typeof value.stations !== "object" || Array.isArray(value.stations) ||
      Object.keys(value.stations).join(",") !== sessionRoles.join(",")) throw new Error("session");
  for (const station of sessionRoles) {
    const record = value.stations[station];
    if (!exactKeys(record, ["status", "requested", "request_generation", "station_generation", "grants"]) ||
        !["available", "occupied", "mine"].includes(record.status) ||
        typeof record.requested !== "boolean" ||
        !Number.isSafeInteger(record.request_generation) || record.request_generation < 0 ||
        (record.station_generation !== null && (!Number.isSafeInteger(record.station_generation) || record.station_generation < 0)) ||
        !exactKeys(record.grants, ["command", "direct_fire", "sonar_audio"]) ||
        Object.values(record.grants).some((grant) => typeof grant !== "boolean") ||
        (record.status === "mine") !== (record.station_generation !== null) ||
        record.grants.direct_fire && (!record.grants.command || !directFireRoles.has(station)) ||
        record.grants.sonar_audio && !audioRoles.has(station)) throw new Error("session");
  }
  const mine = sessionRoles.filter((station) => value.stations[station].status === "mine");
  if ((value.station === null) !== (mine.length === 0) ||
      value.station !== null && !mine.includes(value.station) ||
      value.requested_station !== null && !value.stations[value.requested_station].requested ||
      value.station !== null && (value.station_generation !== value.stations[value.station].station_generation ||
        value.grants.command !== value.stations[value.station].grants.command ||
        value.grants.direct_fire !== value.stations[value.station].grants.direct_fire ||
        value.grants.sonar_audio !== value.stations[value.station].grants.sonar_audio) ||
      !validHandover(value)) throw new Error("session");
}
export async function resumeSession() {
  try {
    const resumed = await request("/session", { auth: false });
    validateSession(resumed);
    S.pairingAvailable = true;
    emit("session:metadata", resumed);
    return true;
  } catch (error) {
    S.pairingAvailable = error.status === 401;
    if (!S.pairingAvailable) setConnection("stale");
    return false;
  }
}
