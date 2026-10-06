import { S } from "../state/store.js";
import { $ } from "../core/base.js";
import { on } from "../core/events.js";
import { t } from "../core/format.js";
import { ultraWide } from "../state/shared.js";
import { eventMeta } from "./feeds.js";
import { activateTab } from "./lobby.js";
import { renderRoleVisuals } from "./role-visuals.js";

// CIC layout: collapsible docks, the status-bar clock, the alert band and the
// log ticker. Dock state is per viewer and kept in memory only: a reload
// starts from the station defaults again (no browser storage by design).
const DOCKS = ["left", "right", "detail", "log"];
// Alt+, / Alt+. / Alt+L: the bare keys are the uConsole's (seeker enable
// range, volume, lookout range; OPZ fusion), so the docks take Alt.
export const DOCK_KEYS = {Comma: "left", Period: "right", KeyL: "log"};
const wide = matchMedia("(min-width: 1600px)");
const tall = matchMedia("(min-width: 1600px) and (min-height: 1300px)");
const ALERT_S = 20;
let layoutStation;
// Docks the operator opened or closed by hand keep that choice for the
// station; the others follow the picture (see autoDocks).
const manualDocks = new Set();
let alertTimer = null;
let shownAlertSeq = null;

function dockElement(name) {
  return name === "log" ? $("log-drawer") : $(`dock-${name}`);
}

function setDock(name, open) {
  $("cic-grid").dataset[name] = open ? "open" : "closed";
  const dock = dockElement(name);
  dock.dataset.collapsed = String(!open);
  const toggle = dock.querySelector(".dock-toggle");
  toggle.setAttribute("aria-expanded", String(open));
  toggle.title = t(open ? "dock_collapse" : "dock_expand");
}

// Station defaults: the instrument gets the room; the contact list is open
// when the screen is wide enough for three columns; the log opens on tall screens.
function applyDefaults(station) {
  // Tall desktop monitors have room for the operational log as well.
  const defaults = {left: wide.matches, right: true, detail: true, log: tall.matches};
  if (station === "sonar" || station === "uboot_sonar") defaults.detail = wide.matches;
  manualDocks.clear();
  for (const name of DOCKS) setDock(name, defaults[name]);
  autoDocks();
}

export function toggleDock(name) {
  manualDocks.add(name);
  setDock(name, $("cic-grid").dataset[name] !== "open");
}

// Room for the station's controls: an empty contact list folds to its rail
// and the contact detail folds to its title bar while no contact is chosen;
// both open again as soon as there is something to show.
export function autoDocks() {
  if (!layoutStation || $("cic-grid").dataset.tracks === "false") return;
  const grid = $("cic-grid");
  const hasTracks = Boolean(S.snapshot?.tracks?.length);
  if (!manualDocks.has("left") && wide.matches && (grid.dataset.left === "open") !== hasTracks) setDock("left", hasTracks);
  const chosen = Boolean(S.selected);
  if (!manualDocks.has("detail") && (grid.dataset.detail === "open") !== chosen) setDock("detail", chosen);
}

function isTyping(target) {
  return target instanceof Element && (target.closest("input, select, textarea, dialog[open]") || target.isContentEditable);
}

function pad(value) {
  return String(value).padStart(2, "0");
}

function renderClock() {
  const now = new Date();
  $("utc-clock").textContent = `${pad(now.getUTCHours())}:${pad(now.getUTCMinutes())}:${pad(now.getUTCSeconds())}`;
  $("utc-clock").dateTime = now.toISOString();
}

function hideAlert() {
  clearTimeout(alertTimer);
  alertTimer = null;
  $("alert-band").hidden = true;
}

// Newest warning from the live event feed: shown for a short while, pulsing,
// until it ages out or the operator dismisses it.
function renderAlerts(warning) {
  const newest = S.eventHistory.at(-1);
  $("log-ticker").textContent = newest ? `${eventMeta(newest)}  ${newest.message}` : t("no_events");
  $("log-ticker").dataset.severity = newest?.severity ?? "";
  if (!warning) return;
  const alert = [...S.eventHistory].reverse().find((event) => event.severity === "warning");
  if (!alert || alert.seq === shownAlertSeq) return;
  shownAlertSeq = alert.seq;
  $("alert-text").textContent = alert.message;
  $("alert-band").dataset.level = "alarm";
  $("alert-band").hidden = false;
  clearTimeout(alertTimer);
  alertTimer = setTimeout(hideAlert, ALERT_S * 1000);
}

export function init() {
  for (const name of DOCKS) setDock(name, $("cic-grid").dataset[name] !== "closed");
  for (const button of document.querySelectorAll("[data-dock-toggle]"))
    button.addEventListener("click", () => toggleDock(button.dataset.dockToggle));
  for (const button of document.querySelectorAll("[data-overlay-close]"))
    button.addEventListener("click", () => activateTab("operations"));
  // A click on the dimmed CIC around an open sheet (the body's backdrop)
  // closes the sheet; it never reaches the station behind.
  document.body.addEventListener("click", (event) => {
    if (event.target === document.body && document.body.classList.contains("workstation-mode")
        && document.querySelector(".tab-panel:not(#panel-operations):not([hidden])"))
      activateTab("operations");
  });
  $("alert-dismiss").addEventListener("click", hideAlert);
  $("status-more").addEventListener("click", () => {
    const open = $("statusbar").dataset.more !== "open";
    $("statusbar").dataset.more = open ? "open" : "closed";
    $("status-more").setAttribute("aria-expanded", String(open));
  });
  on("layout:station", (station) => {
    if (station === layoutStation) return;
    layoutStation = station;
    applyDefaults(station);
  });
  on("events", renderAlerts);
  on("session:forgotten", () => {
    hideAlert(); shownAlertSeq = null; layoutStation = undefined;
    // A forgotten session decides no station requests.
    $("handover-band").hidden = true;
    $("handover-list").replaceChildren();
    delete $("handover-list").dataset.signature;
  });
  wide.addEventListener("change", () => applyDefaults(layoutStation));
  ultraWide.addEventListener("change", () => { if (S.v2State?.role) renderRoleVisuals(S.v2State.role); });
  document.addEventListener("keydown", (event) => {
    if (!S.session?.station || event.ctrlKey || event.metaKey || event.isComposing ||
        event.repeat || $("operations").hidden || isTyping(event.target)) return;
    if (event.key === "Escape" && !event.altKey && S.activeTab !== "operations") {
      event.preventDefault();
      activateTab("operations");
      return;
    }
    const dock = event.altKey && !event.shiftKey ? DOCK_KEYS[event.code] : undefined;
    if (!dock || !document.body.classList.contains("workstation-mode")) return;
    event.preventDefault();
    toggleDock(dock);
  });
  renderClock();
  setInterval(renderClock, 1000);
}
