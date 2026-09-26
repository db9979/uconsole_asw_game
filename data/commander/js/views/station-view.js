import { S } from "../state/store.js";
import { emit } from "../core/events.js";
import { stopSonarAudio } from "../audio/audio.js";
import { $, isSonar, opforRoles, panelRole } from "../core/base.js";
import { t } from "../core/format.js";
import { stopSonarStream } from "../net/sonar-stream.js";
import { defaultSonarPage, lookoutView, roleCache, roleMapViews, sonarHistory, tabNames, trackRoles, view } from "../state/shared.js";
import { renderBridgeStation } from "../stations/bridge.js";
import { renderDamageStation } from "../stations/damage.js";
import { renderElokaStation } from "../stations/eloka.js";
import { renderEngineStation } from "../stations/engine.js";
import { renderHelicopterStation } from "../stations/helicopter.js";
import { renderOpzStation } from "../stations/opz.js";
import { renderRadioStation } from "../stations/radio.js";
import { renderSonarStation } from "../stations/sonar.js";
import { renderUbootStation } from "../stations/uboot.js";
import { renderWeaponsStation } from "../stations/weapons.js";
import { releaseCanvas } from "./chart.js";
import { renderSonarControlPage } from "./controls.js";
import { clearFireDrafts, clearVisuals } from "./dom.js";
import { activateTab } from "./lobby.js";
import { queueVisualDraw, renderRoleVisuals } from "./role-visuals.js";
import { canvas, lookoutCanvas } from "./canvases.js";

export function renderStationView() {
  const active = S.v2State?.role;
  document.body.classList.toggle("workstation-mode", Boolean(active));
  $("workstation-tools").hidden = !active;
  $("workstation-station-label").hidden = !active;
  for (const name of ["lookout", "guide", "contacts"]) $(`tab-${name}`).hidden = Boolean(active);
  $("tab-operations").textContent = active ? t(`station_${active}`) : t("tab_operations");
  $("workstation-lookout").hidden = active !== "bridge";
  $("workstation-guide").hidden = !active;
  $("panel-guide").querySelector(".guide-layout").hidden = Boolean(active);
  if (active) {
    $("workstation-guide-title").textContent = t(`station_${active}`);
    $("workstation-guide-body").textContent = t(`workstation_help_${active}`);
    $("workstation-manual-link").href = `/manual-${S.language}#${opforRoles.has(active) ? "ref-opfor" : `station-${active}`}`;
  }
  if (active) {
    const grid = $(`station-${panelRole(active)}`).querySelector(".station-grid");
    // Instruments, docks and the role-specific control groups have fixed homes
    // in the markup; only the live-listening strip follows the acoustic panel.
    $("bridge-orders").hidden = active !== "bridge";
    $("opz-controls").hidden = active !== "opz";
    $("helicopter-dipping-controls").hidden = active !== "helicopter";
    if (active === "helicopter" && $("sonar-live-toggle").parentElement?.parentElement !== $("helicopter-buoy-console"))
      $("helicopter-buoy-console").prepend($("sonar-live-toggle").parentElement);
    if (isSonar(active) && $("sonar-live-toggle").parentElement?.parentElement !== $("sonar-visual"))
      $("sonar-visual").prepend($("sonar-live-toggle").parentElement);
    const controls = grid.querySelector(":scope > .station-controls");
    if (controls && grid.firstElementChild !== controls) grid.prepend(controls);
    const fire = grid.querySelector(":scope > .direct-fire-controls");
    if (active === "weapons" && fire && grid.firstElementChild !== fire) grid.prepend(fire);
  } else {
    $("bridge-orders").hidden = true;
    $("opz-controls").hidden = true;
    $("helicopter-dipping-controls").hidden = true;
  }
  $("cic-grid").dataset.tracks = String(!active || trackRoles.has(active));
  // The radio room keeps the contact detail (opened from a receiver channel).
  $("cic-grid").dataset.layout = active === "radio" ? "radio" : "";
  emit("layout:station", active);
  $("station-view").hidden = !active;
  for (const section of document.querySelectorAll("[data-station-role]")) {
    section.hidden = section.dataset.stationRole !== panelRole(active);
    if (section.hidden) for (const container of section.querySelectorAll("dl, .station-list")) container.replaceChildren();
  }
  renderRoleVisuals(active);
  if (!active) return;
  const signature = `${S.language}:${active}:${JSON.stringify(S.v2State[active])}:${JSON.stringify(S.v2State.environment)}`;
  if (signature === S.stationRenderSignature) return;
  S.stationRenderSignature = signature;
  const renderers = {bridge: renderBridgeStation, sonar: renderSonarStation, weapons: renderWeaponsStation,
    damage: renderDamageStation, opz: renderOpzStation, radio: renderRadioStation, engine: renderEngineStation,
    helicopter: renderHelicopterStation, eloka: renderElokaStation,
    uboot: renderUbootStation, uboot_sonar: renderSonarStation};
  renderers[active](S.v2State[active]);
  queueVisualDraw();
}
export function clearRoleState() {
  stopSonarAudio();
  stopSonarStream();
  roleCache.clear();
  S.roleStale = false;
  document.body.removeAttribute("data-role-stale");
  document.body.classList.remove("workstation-mode");
  $("workstation-tools").hidden = true;
  $("workstation-station-label").hidden = true;
  for (const name of tabNames) $(`tab-${name}`).hidden = false;
  S.snapshot = null;
  S.chart = null;
  S.chartSession = null;
  S.chartEpoch = null;
  S.chartRole = null;
  S.selected = null;
  S.queuedSonarFocus = null;
  S.pending = null;
  S.v2State = null;
  sonarHistory.context = null;
  for (const name of ["broadband", "lofar", "demon"]) sonarHistory[name].clear();
  S.stationDrafts.clear();
  clearFireDrafts();
  S.stationRenderSignature = null;
  S.sonarVisualPage = defaultSonarPage();
  clearVisuals();
  for (const state of Object.values(roleMapViews)) { state.initialized = false; state.follow = false; }
  $("role-visuals").hidden = true;
  S.commandMessage = null;
  S.opzMarked.clear();
  S.opzSuppressed.clear();
  S.opzManage = false;
  $("opz-manage").checked = false;
  S.latestSimlogState = null;
  S.lastSimlogFetch = 0;
  S.proposals = null;
  S.eventContext = null;
  S.eventHighWater = 0;
  S.eventHistory = [];
  view.initialized = false;
  view.follow = false;
  lookoutView.rangeNm = 100;
  S.activeTab = "operations";
  $("navigation-form").reset();
  $("bridge-course-form").reset();
  $("bridge-speed-form").reset();
  for (const id of ["sonar-bearing-form", "sonar-depth-form", "sonar-gain-form", "sonar-harmonic-form",
    "engine-course-form", "engine-speed-form", "helicopter-waypoint-form", "helicopter-dip-depth-form",
    "uboot-course-form", "uboot-speed-form", "uboot-depth-form"]) $(id).reset();
  $("sonar-control-page").value = "listen";
  renderSonarControlPage();
  $("navigation-status").textContent = "";
  $("track-list").replaceChildren();
  $("station-view").hidden = true;
  $("cic-grid").dataset.tracks = "true";
  for (const section of document.querySelectorAll("[data-station-role]")) {
    section.hidden = true;
    for (const container of section.querySelectorAll("dl, .station-list")) container.replaceChildren();
  }
  $("track-detail").hidden = true;
  for (const id of ["detail-label", "detail-badges", "detail-metrics", "mission-name", "objective",
    "mission-metrics", "chart-disclaimer", "proposal-status", "command-status", "snapshot-meta", "lookout-sea",
    "lookout-light", "lookout-own", "lookout-observations", "bridge-order-values",
    "bridge-order-status", "opz-mark-status", "opz-release-status", "station-command-status",
    "autocrew-status", "bridge-weather-text"]) $(id).replaceChildren();
  $("simlog-list").replaceChildren();
  $("simlog-current").replaceChildren();
  releaseCanvas(canvas);
  releaseCanvas(lookoutCanvas);
  activateTab("operations", false);
}
