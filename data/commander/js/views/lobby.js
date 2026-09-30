import { S } from "../state/store.js";
import { renderSonarAudio, sonarAudioAuthorized, stopSonarAudio } from "../audio/audio.js";
import { $, opforRoles, sideStations, stationNames } from "../core/base.js";
import { authenticated, t } from "../core/format.js";
import { poll } from "../net/poll.js";
import { request } from "../net/request.js";
import { forgetSession, setConnection, validateSession } from "../net/session.js";
import { stopSonarStream } from "../net/sonar-stream.js";
import { buildDisplayModel } from "../state/display-model.js";
import { roleCache, tabNames } from "../state/shared.js";
import { renderContactAnalysis } from "./analyzer.js";
import { queueDraw, releaseCanvas } from "./chart.js";
import { renderDisabledReasons } from "./controls.js";
import { clearFireDrafts, clearVisuals, node } from "./dom.js";
import { renderHost, scenarioText } from "./host.js";
import { queueLookoutDraw, renderLookoutStatus } from "./lookout.js";
import { renderSnapshot } from "./render.js";
import { syncOpzSweepAnimation } from "./role-map.js";
import { queueVisualDraw } from "./role-visuals.js";
import { loadSimlog, simlogActive } from "./simlog.js";
import { renderStationTabs } from "./station-tabs.js";
import { clearRoleState } from "./station-view.js";
import { canvas, lookoutCanvas } from "./canvases.js";
import { renderEvents } from "./feeds.js";

export function renderLobby() {
  if (!S.session) return;
  const assigned = S.session.station !== null;
  const simlog = simlogActive();
  // While the host has the multiplayer lobby open the crew meets here, also
  // those who already hold a station.
  const room = S.session.host === null && !simlog ? S.session.lobby : null;
  $("pairing").hidden = true;
  $("lobby").hidden = simlog || assigned && !S.stationPickerOpen && room === null ||
    S.session.host !== null && S.hostView?.phase === "menu";
  $("lobby-back").hidden = !assigned || room !== null;
  // A solo session holds every station, so there is nothing to add or release.
  const solo = S.session.host !== null;
  $("role-rail").hidden = !assigned || S.stationPickerOpen || solo;
  $("mobile-role").hidden = !assigned || S.stationPickerOpen;
  for (const id of ["mobile-add-station", "mobile-release-station"]) $(id).hidden = solo;
  const rolePublished = S.v2State?.role === S.session.station;
  const hostMenu = S.session.host !== null && S.hostView?.phase === "menu";
  $("operations").hidden = simlog || !assigned || S.stationPickerOpen || !rolePublished || hostMenu || room !== null;
  renderLobbyRoom(room);
  renderHandover();
  $("simlog-view").hidden = !simlog;
  if (simlog) loadSimlog();
  document.body.dataset.remoteRole = assigned ? "assigned" : "lobby";
  const observer = S.session.observer === true;
  document.body.dataset.observer = String(observer);
  const requested = S.session.requested_station;
  $("lobby-status").textContent = S.lobbyMessage ? t(S.lobbyMessage) : requested ?
    t("lobby_pending", { station: t(`station_${requested}`) }) : observer ? t("lobby_observer") : t("lobby_waiting");
  if ($("station-cards").children.length !== stationNames.length ||
      stationNames.some((station, index) => $("station-cards").children[index]?.dataset.station !== station)) {
    $("station-cards").replaceChildren(...stationNames.map((station) => {
      const card = node("section");
      card.dataset.station = station;
      const button = node("button");
      button.type = "button";
      button.dataset.station = station;
      button.addEventListener("click", () => requestStation(station));
      card.append(node("h2"), node("p", undefined, "station-occupancy"), button);
      return card;
    }));
  }
  // One unit at a time: the side of the held stations, else the lobby choice.
  const side = S.session.station !== null && S.session.observer !== true ? (opforRoles.has(S.session.station) ? "opfor" : "frigate") : S.lobbySide;
  for (const button of $("side-choice").querySelectorAll("button")) {
    button.setAttribute("aria-pressed", String(button.dataset.side === side));
    // An observer looks at both units; a crew member stays with one.
    button.disabled = !observer && S.session.station !== null && button.dataset.side !== side;
  }
  stationNames.forEach((station, index) => {
    const record = S.session.stations[station];
    $("station-cards").children[index].hidden = (opforRoles.has(station) ? "opfor" : "frigate") !== side;
    const state = record.status;
    const card = $("station-cards").children[index];
    const [heading, occupancy, button] = card.children;
    card.className = `station-card station-${state}`;
    heading.textContent = t(`station_${station}`);
    occupancy.textContent = t(`occupancy_${state}`);
    // A free station is taken at once with all its rights; one a crewmate
    // holds is requested; the holder or the host may hand it over.
    button.textContent = observer ? t("station_view") : record.requested ? t("station_requested")
      : t(state === "available" ? "station_take" : "station_request");
    button.disabled = S.stationMutation || requested !== null || state === "mine";
  });
  if (!assigned) { renderDisabledReasons(); return; }
  const role = t(`station_${S.session.station}`);
  $("role-rail-title").textContent = role;
  $("role-grants").textContent = t(observer ? "role_observer" : S.session.grants.command ? "role_commands" : "role_read_only");
  $("role-status").textContent = S.lobbyMessage ? t(S.lobbyMessage) : requested ?
    t("lobby_pending", { station: t(`station_${requested}`) }) : "";
  $("release-station").disabled = S.stationMutation;
  $("mobile-release-station").disabled = S.stationMutation;
  for (const id of ["add-station", "mobile-add-station", "workstation-add-station"]) {
    $(id).disabled = S.stationMutation || requested !== null;
  }
  const displayedStation = S.activatingStation && S.session.stations[S.activatingStation]?.status === "mine" ?
    S.activatingStation : S.session.station;
  const leasedStations = stationNames.filter((station) => S.session.stations[station].status === "mine");
  for (const id of ["mobile-station"]) {
    const select = $(id);
    const signature = leasedStations.map((station) => `${station}:${t(`station_${station}`)}`).join("|");
    if (select.dataset.options !== signature) {
      select.replaceChildren(...leasedStations.map((station) => {
      const option = node("option", t(`station_${station}`));
      option.value = station;
      return option;
      }));
      select.dataset.options = signature;
    }
    if (document.activeElement !== select || S.stationMutation) select.value = displayedStation;
    select.disabled = S.stationMutation;
  }
  renderStationTabs(leasedStations, displayedStation);
  // A session only ever holds one side, so "all" means every role of that side.
  $("workstation-add-station").hidden =
    leasedStations.length === sideStations(S.session.station ?? "bridge").length;
  $("workstation-release").hidden = solo;
  renderHost();
  renderDisabledReasons();
}
function renderLobbyRoom(room) {
  $("lobby-room").hidden = room === null;
  if (room === null) return;
  $("lobby-room-mission").textContent = t("lobby_room_mission", {mission: t(scenarioText[room.mission] ?? "unknown")});
  const side = t(`lobby_room_side_${room.side}`);
  $("lobby-room-host").textContent = room.host_station === null ? t("lobby_room_host_only")
    : t("lobby_room_host", {side, station: t(`station_${room.host_station}`)});
  const hostStations = room.host_station === null ? [] : [room.host_station];
  const rows = [[t("lobby_player_host"), hostStations, "lobby_player_ready"],
    ...room.players.map((player) => [player.you ? t("lobby_player_you", {name: player.name}) : player.name,
      player.stations, player.observer ? "lobby_player_observer" : player.ready ? "lobby_player_ready" : "lobby_player_waiting"])];
  $("lobby-room-players").replaceChildren(...rows.map(([name, stations, state]) => {
    const item = node("li");
    item.dataset.state = state;
    item.append(node("strong", name), node("span", stations.length
      ? stations.map((station) => t(`station_${station}`)).join(", ") : t("lobby_player_none")), node("em", t(state)));
    return item;
  }));
  const holding = stationNames.some((station) => S.session.stations[station].status === "mine");
  const observer = S.session.observer === true;
  $("lobby-room-status").textContent = room.countdown_s !== null
    ? t("lobby_countdown", {seconds: Math.max(1, Math.ceil(room.countdown_s))})
    : S.lobbyRoomMessage ? t(S.lobbyRoomMessage) : !holding && !observer ? t("lobby_ready_need_station") : t("lobby_waiting_host");
  const ready = $("lobby-ready");
  ready.hidden = observer;
  ready.textContent = t(room.ready ? "lobby_unready" : "lobby_ready");
  ready.setAttribute("aria-pressed", String(room.ready));
  ready.disabled = S.stationMutation || !holding && !room.ready;
}
// A crewmate asks for a station this browser holds: hand it over or keep it.
// Rebuilt only when the list changes, so keyboard focus stays on its button.
function renderHandover() {
  const entries = S.session.handover;
  $("handover-band").hidden = entries.length === 0;
  const list = $("handover-list");
  const signature = entries.map((entry) => `${entry.station}:${entry.ordinal}:${entry.request_generation}:${entry.name}`).join("|") +
    `#${document.documentElement.lang}`;
  if (list.dataset.signature !== signature) {
    list.replaceChildren(...entries.map((entry) => {
      const item = node("li");
      item.append(node("p", t("handover_request", {name: entry.name, station: t(`station_${entry.station}`)})));
      for (const [accept, label] of [[true, "handover_accept"], [false, "handover_keep"]]) {
        const button = node("button", t(label));
        button.type = "button";
        if (accept) button.className = "primary";
        button.dataset.station = entry.station;
        button.dataset.ordinal = String(entry.ordinal);
        button.dataset.requestGeneration = String(entry.request_generation);
        button.dataset.accept = String(accept);
        item.append(button);
      }
      return item;
    }));
    list.dataset.signature = signature;
  }
  for (const button of list.querySelectorAll("button")) button.disabled = S.stationMutation;
}
export function decideHandover(button) {
  const station = button?.dataset?.station;
  const ordinal = Number(button?.dataset?.ordinal);
  const generation = Number(button?.dataset?.requestGeneration);
  const entry = S.session?.handover?.find((item) => item.station === station &&
    item.ordinal === ordinal && item.request_generation === generation);
  if (!entry || S.stationMutation) return;
  mutateStation("/stations/handover", {station, ordinal, request_generation: generation,
    accept: button.dataset.accept === "true"});
}
export async function toggleReady() {
  const room = S.session?.lobby;
  if (!room || S.stationMutation) return;
  S.stationMutation = true;
  S.lobbyRoomMessage = null;
  const context = S.generation;
  try {
    const result = await request("/lobby/ready", { method: "POST", body: {ready: !room.ready},
      csrf: S.session.csrf, guard: () => context === S.generation });
    if (context !== S.generation) return;
    acceptSession(result);
  } catch (error) {
    if (context !== S.generation || error.message === "cancelled") return;
    if (error.status === 401) forgetSession("connection_expired");
    else S.lobbyRoomMessage = "lobby_ready_failed";
  } finally {
    if (context === S.generation) {
      S.stationMutation = false;
      renderLobby();
    }
  }
}
function switchRole(from, to) {
  if (S.v2State?.role === from) roleCache.set(from, S.v2State);
  stopSonarAudio();
  stopSonarStream();
  // Everything bound to the old station's authority is dropped: the pending
  // command, armed fire, queued focus and the per-station feeds. Map views,
  // selection, form contents and the sonar page belong to the operator and stay.
  S.pending = null;
  S.commandMessage = null;
  S.queuedSonarFocus = null;
  S.requestedSonarFocus = null;
  clearFireDrafts();
  S.stationRenderSignature = null;
  S.proposals = null;
  S.eventContext = null;
  S.eventHighWater = 0;
  S.eventHistory = [];
  renderEvents();
  clearVisuals();
  const cached = roleCache.get(to) ?? null;
  S.v2State = cached;
  S.snapshot = cached ? buildDisplayModel(cached) : null;
  S.roleStale = true;
  document.body.dataset.roleStale = "true";
  if (S.snapshot && S.chart) {
    // Paint immediately from the cache; the fresh state replaces it next poll.
    renderSnapshot();
  }
}
export function acceptSession(next) {
  validateSession(next);
  const previous = S.session;
  const changed = previous && (previous.station !== next.station ||
    previous.station_generation !== next.station_generation ||
    previous.active_generation !== next.active_generation);
  const lostRole = previous != null && previous.station !== null && next.station === null;
  // A plain activation moves between leases this client already held under the
  // same generations; any lease, grant or world change is a full reset.
  const activation = changed && previous.station !== null && next.station !== null &&
    previous.station !== next.station &&
    stationNames.every((name) => previous.stations[name].status === next.stations[name].status &&
      previous.stations[name].station_generation === next.stations[name].station_generation);
  if (!activation && changed) clearRoleState();
  if (previous?.requested_station &&
      next.stations[previous.requested_station]?.status === "mine") S.stationPickerOpen = false;
  S.session = next;
  if (activation) switchRole(previous.station, next.station);
  if (S.sonarAudioEnabled && !sonarAudioAuthorized()) stopSonarAudio("sonar_live_unavailable");
  S.nextCommandSeq = next.next_command_seq;
  S.lastSessionFetch = performance.now();
  if (lostRole) S.lobbyMessage = "role_revoked";
  else if (next.station !== null) S.lobbyMessage = null;
  else if (previous?.requested_station && next.requested_station === null) S.lobbyMessage = "lobby_request_cleared";
  renderLobby();
  renderSonarAudio();
}
export async function mutateStation(path, body) {
  if (!S.session || S.stationMutation) return;
  S.stationMutation = true;
  S.lobbyMessage = null;
  renderLobby();
  const context = S.generation;
  const csrf = S.session.csrf;
  try {
    const result = await request(path, { method: "POST", body, csrf, guard: () => context === S.generation });
    if (context !== S.generation) return;
    acceptSession(result);
  } catch (error) {
    if (context !== S.generation || error.message === "cancelled") return;
    if (error.status === 401 || error.status === 403) forgetSession("connection_expired");
    else if (error.status === 409) {
      try { acceptSession(await request("/session")); } catch (_) { setConnection("stale"); }
    } else {
      S.lobbyMessage = "station_mutation_failed";
      setConnection("stale");
    }
  } finally {
    if (context === S.generation) {
      S.stationMutation = false;
      if (path === "/stations/activate") {
        S.activatingStation = null;
        // Do not wait for the next 500 ms tick: fetch the new station now.
        if (authenticated() && !S.polling) { clearTimeout(S.pollTimer); poll(); }
      }
      renderLobby();
    }
  }
}
export function chooseSide(side) {
  if (!["frigate", "opfor"].includes(side)) return;
  S.lobbySide = side;
  renderLobby();
}
// Solo: the one browser plays the other unit; the server moves every station.
export function switchSoloSide() {
  if (S.session?.host === null || S.session?.station == null || S.stationMutation) return;
  const target = opforRoles.has(S.session.station) ? "bridge" : "uboot";
  mutateStation("/stations/request", { station: target });
}
function requestStation(station) {
  if (!stationNames.includes(station) || S.session?.stations[station]?.status === "mine" ||
      S.session.requested_station !== null) return;
  if (S.session.observer) {
    // Observers hold no lease: the view switches straight away (generation 0).
    S.activatingStation = station;
    mutateStation("/stations/activate", {station, station_generation: 0,
      active_generation: S.session.active_generation});
    return;
  }
  mutateStation("/stations/request", { station });
}
export function chooseStation(station) {
  const record = S.session?.stations?.[station];
  if (!record || S.stationMutation || station === S.session.station) return;
  if (record.status === "mine") {
    if (S.activeTab !== "operations") activateTab("operations", false);
    S.activatingStation = station;
    mutateStation("/stations/activate", {
      station, station_generation: record.station_generation,
      active_generation: S.session.active_generation,
    });
  }
}
export function activateTab(name, focus = true) {
  if (!tabNames.includes(name)) return;
  S.activeTab = name;
  for (const candidate of tabNames) {
    const selectedTab = candidate === name;
    const tab = $(`tab-${candidate}`);
    tab.setAttribute("aria-selected", String(selectedTab));
    tab.tabIndex = selectedTab ? 0 : -1;
    // At a workstation the other tabs open as overlays above the live CIC.
    $(`panel-${candidate}`).hidden = !selectedTab &&
      !(candidate === "operations" && document.body.classList.contains("workstation-mode"));
  }
  if (name !== "operations") releaseCanvas(canvas);
  if (name !== "lookout") {
    releaseCanvas(lookoutCanvas);
    $("lookout-observations").replaceChildren();
  }
  if (focus) (name !== "operations" ? $(`panel-${name}`) : $(`tab-${name}`)).focus();
  if (name === "operations") { queueDraw(); queueVisualDraw(); }
  if (name === "lookout") { renderLookoutStatus(); queueLookoutDraw(); }
  if (name === "contacts") renderContactAnalysis();
  syncOpzSweepAnimation();
}
