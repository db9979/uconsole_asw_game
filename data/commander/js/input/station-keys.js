import { S } from "../state/store.js";
import { $ } from "../core/base.js";

// The uConsole's key scheme in the browser: the same function has the same
// key at every station of both sides. Each binding presses a visible control
// of the held station (a click on a button, focus on a value field, a step on
// a list); nothing here sends a command itself, so every key passes the same
// checks as the mouse. Ctrl+Enter only arms a weapon: the fire dialog still
// asks for its own confirmation. Every bound control shows its key as a cap.
const MAP_ROLES = ["bridge", "weapons", "helicopter", "uboot", "uboot_weapons", "uboot_esm", "uboot_nav", "uboot_radio", "uboot_engine"];
const SONARS = ["sonar", "uboot_sonar"];
const FIRE = "Ctrl+Enter";

// [roles, key, targets, how]; key is "Shift+A", "Ctrl+Enter", "PageDown", ...
// how: "click" (default), "focus" (a value field: type, then Enter), "step+1"/"step-1" (a list).
export const STATION_KEYS = [
  [MAP_ROLES, "E", ["#role-map-zoom-in"]],
  [MAP_ROLES, "Q", ["#role-map-zoom-out"]],
  [MAP_ROLES, "K", ["#role-map-follow"]],
  [MAP_ROLES, "Home", ["#role-map-fit"]],
  [["bridge"], "C", ["#bridge-course"], "focus"],
  [["bridge"], "V", ["#bridge-speed"], "focus"],
  [["bridge"], "Ctrl+B", ["#bridge-clear-baffles"]],
  [["engine"], "C", ["#engine-course"], "focus"],
  [["engine"], "V", ["#engine-speed"], "focus"],
  [["engine"], "A", ["#engine-quiet"]],
  [SONARS, "Shift+A", ["#sonar-ping"]],
  [SONARS, "J", ["#sonar-live-toggle"]],
  [SONARS, "PageDown", ["#sonar-page-tabs"], "step+1"],
  [SONARS, "PageUp", ["#sonar-page-tabs"], "step-1"],
  [["weapons"], FIRE, ["#weapons-fire-torpedo"]],
  [["weapons"], "T", ["#weapons-fire-depth"], "focus"],
  [["opz"], FIRE, ["#opz-fire-essm"]],
  [["opz"], "R", ["#opz-radar-surface"]],
  [["opz"], "Shift+R", ["#opz-radar-air"]],
  [["opz"], "E", ["#opz-range"], "step-1"],
  [["opz"], "Q", ["#opz-range"], "step+1"],
  [["helicopter"], "H", ["#helicopter-launch", "#helicopter-return"]],
  [["helicopter"], "B", ["#helicopter-buoy"]],
  [["helicopter"], "Ctrl+R", ["#helicopter-radar"]],
  [["helicopter"], "Shift+M", ["#helicopter-mad"]],
  [["helicopter"], "Shift+A", ["#helicopter-dip-ping"]],
  [["helicopter"], FIRE, ["#helicopter-fire-torpedo"]],
  [["uboot", "uboot_nav"], "C", ["#uboot-course"], "focus"],
  [["uboot", "uboot_nav"], "D", ["#uboot-depth"], "focus"],
  [["uboot", "uboot_engine"], "V", ["#uboot-speed"], "focus"],
  [["uboot"], "Shift+A", ["#uboot-ping"]],
  [["uboot"], "Ctrl+B", ["#uboot-clear-baffles"]],
  [["uboot_weapons"], FIRE, ["#uboot-fire"]],
  [["uboot_weapons"], "V", ["#uboot-decoy"]],
  [["uboot_weapons"], "T", ["#uboot-fire-depth"], "focus"],
];

const GERMAN = {Ctrl: "Strg", PageUp: "Bild↑", PageDown: "Bild↓", Home: "Pos1"};
const ENGLISH = {PageUp: "PgUp", PageDown: "PgDn"};

export function keyLabel(key, language = S.language) {
  const names = language === "de" ? GERMAN : ENGLISH;
  return key.split("+").map((part) => names[part] ?? part).join("+");
}

function parse(key) {
  const parts = key.split("+");
  return {key: parts.at(-1), ctrl: parts.includes("Ctrl"), shift: parts.includes("Shift")};
}

function usable(element) {
  return element && !element.disabled && !element.closest("[hidden]") && element.getClientRects().length > 0;
}

// The element that carries the cap: a value field's submit button, a
// checkbox's label, a list's own label; otherwise the control itself.
function capHost(element) {
  if (element.matches("input[type=checkbox], select")) return document.querySelector(`label[for="${element.id}"]`) ?? element;
  if (element.matches("input")) return element.form?.querySelector("button[type=submit]") ?? element;
  return element;
}

export function markStationKeys() {
  const seen = new Map();
  for (const [, key, targets, how] of STATION_KEYS) for (const selector of targets) {
    const element = document.querySelector(selector);
    if (!element) continue;
    const host = how?.startsWith("step") && !element.matches("select") ? element : capHost(element);
    seen.set(host, [...(seen.get(host) ?? []), keyLabel(key)]);
  }
  for (const [host, caps] of seen) host.dataset.keycap = [...new Set(caps)].join(" / ");
}

function step(element, delta) {
  if (element.matches("select")) {
    const index = Math.max(0, Math.min(element.options.length - 1, element.selectedIndex + delta));
    if (index === element.selectedIndex) return;
    element.selectedIndex = index;
    element.dispatchEvent(new Event("change", {bubbles: true}));
    return;
  }
  const tabs = [...element.querySelectorAll("button")].filter(usable);
  if (!tabs.length) return;
  const index = tabs.findIndex((tab) => tab.getAttribute("aria-selected") === "true");
  tabs[(index + delta + tabs.length) % tabs.length].click();
}

export function bindingFor(role, event) {
  const key = event.key.length === 1 ? event.key.toUpperCase() : event.key;
  for (const binding of STATION_KEYS) {
    const want = parse(binding[1]);
    if (!binding[0].includes(role) || want.key !== key || want.ctrl !== event.ctrlKey || want.shift !== event.shiftKey) continue;
    const element = binding[2].map((selector) => document.querySelector(selector)).find(usable);
    if (element) return {element, how: binding[3] ?? "click"};
  }
  return null;
}

export function init() {
  markStationKeys();
  window.addEventListener("u-jagd-language", () => queueMicrotask(markStationKeys));
  document.addEventListener("keydown", (event) => {
    const role = S.v2State?.role;
    if (!role || S.session?.station !== role || event.altKey || event.metaKey || event.isComposing ||
        event.repeat || event.defaultPrevented || $("operations").hidden) return;
    const target = event.target;
    if (target instanceof Element && (target.closest("input, select, textarea, dialog[open]") || target.isContentEditable)) return;
    const binding = bindingFor(role, event);
    if (!binding) return;
    event.preventDefault();
    if (binding.how === "focus") { binding.element.focus(); binding.element.select?.(); }
    else if (binding.how.startsWith("step")) step(binding.element, binding.how === "step+1" ? 1 : -1);
    else binding.element.click();
  });
}
