import { S } from "../state/store.js";
import { $ } from "../core/base.js";
import { on } from "../core/events.js";
import { t } from "../core/format.js";
import { ultraWide } from "../state/shared.js";
import { activateTab } from "./lobby.js";
import { renderRoleVisuals } from "./role-visuals.js";

// CIC layout: collapsible docks, the status-bar clock, the alert band and the
// log ticker. Dock state is per viewer and kept in memory only: a reload
// starts from the station defaults again (no browser storage by design).
const DOCKS = ["left", "right", "detail", "log"];
const DOCK_KEYS = {",": "left", ".": "right", "l": "log", "L": "log"};
const wide = matchMedia("(min-width: 1600px)");
const tall = matchMedia("(min-width: 1600px) and (min-height: 1300px)");
const ALERT_S = 20;
let layoutStation;
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
  for (const name of DOCKS) setDock(name, defaults[name]);
}

export function toggleDock(name) {
  setDock(name, $("cic-grid").dataset[name] !== "open");
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
  $("log-ticker").textContent = newest ? `${newest.seq} / ${newest.kind}  ${newest.message}` : t("no_events");
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
  $("alert-dismiss").addEventListener("click", hideAlert);
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
    if (!S.session?.station || event.ctrlKey || event.altKey || event.metaKey || event.isComposing ||
        event.repeat || $("operations").hidden || isTyping(event.target)) return;
    if (event.key === "Escape" && S.activeTab !== "operations") {
      event.preventDefault();
      activateTab("operations");
      return;
    }
    const dock = DOCK_KEYS[event.key];
    if (!dock || !document.body.classList.contains("workstation-mode")) return;
    event.preventDefault();
    toggleDock(dock);
  });
  renderClock();
  setInterval(renderClock, 1000);
}
