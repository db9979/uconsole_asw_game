import { S } from "../state/store.js";
import { $, sideStations, stationKey } from "../core/base.js";
import { on } from "../core/events.js";

// The uConsole's key scheme in the browser: the same function has the same
// key at every station of both sides. Each binding presses a visible control
// of the held station (a click on a button, focus on a value field, a step on
// a list); nothing here sends a command itself, so every key passes the same
// checks as the mouse. Ctrl+Enter only arms a weapon: the fire dialog still
// asks for its own confirmation. Every bound control shows its key as a cap.
const MAP_ROLES = ["bridge", "weapons", "helicopter", "uboot", "uboot_weapons", "uboot_esm", "uboot_nav", "uboot_radio", "uboot_engine"];
const BOAT = ["uboot", "uboot_weapons", "uboot_esm", "uboot_nav", "uboot_radio", "uboot_engine"];
const SONARS = ["sonar", "uboot_sonar"];
const FIRE = "Ctrl+Enter";
const ZOOM = ["help.control.zoom", "help.uboot.zoom"];
const FOLLOW = ["help.control.follow", "help.uboot.follow"];

// A row's action button of the held station's selected contact.
const selectedAction = (list, action) => () => S.selected === null || S.selected === undefined ? null :
  document.querySelector(`#${list} [data-row-key="${CSS.escape(String(S.selected))}"] [data-station-action="${action}"]`);
const radioCapture = () => document.querySelector('#radio-observations .radio-channel.selected [data-station-action="radio_capture_hfdf"]');
const action = (name) => `[data-station-action="${name}"]`;
const mode = (name) => `#station-uboot [data-uboot-mode="${name}"]`;

// [roles, key, targets, how, help]: key is "Shift+A", "Ctrl+Enter", "PageDown", ...;
// targets are selectors or functions returning an element; how:
// "click" (default), "focus" (a value field: type, then Enter), "step+1"/"step-1"
// (a list or tab row, stops at its ends), "cycle" (a list, wraps round and
// applies on change), "cycle:<apply>" (a list, then the apply button),
// "order+1"/"order-1" (a telegraph: a list plus its send button, or a row of
// step buttons), "toggle" (the not-pressed button of an on/off pair).
// help names the uConsole's key help row of the same function (src/core/help.py),
// or null for a browser-only key that the uConsole does not use there
// (tests/test_web_key_parity.py checks both).
export const STATION_KEYS = [
  [MAP_ROLES, "E", ["#role-map-zoom-in"], "click", ZOOM],
  [MAP_ROLES, "Q", ["#role-map-zoom-out"], "click", ZOOM],
  [MAP_ROLES, "K", ["#role-map-follow"], "click", FOLLOW],
  [MAP_ROLES, "Home", ["#role-map-fit"], "click", null],
  // Bridge.
  [["bridge"], "C", ["#bridge-course"], "focus", "help.control.course_input"],
  [["bridge"], "V", ["#bridge-speed"], "focus", "help.control.speed_input"],
  [["bridge"], "+", ["#bridge-telegraph-up"], "click", "help.control.engine_order"],
  [["bridge"], "-", ["#bridge-telegraph-down"], "click", "help.control.engine_order"],
  [["bridge"], "G", [`#bridge-crew-actions ${action("crew_action_stations")}`], "click", "help.control.action_stations"],
  [["bridge"], "W", ["#bridge-route-zigzag"], "click", "help.bridge.route_pattern"],
  [["bridge"], "Backspace", ["#bridge-route-clear"], "click", "help.bridge.route_clear"],
  [["bridge"], "Ctrl+B", ["#bridge-clear-baffles"], "click", "help.bridge.clear_baffles"],
  // Engine room.
  [["engine"], "C", ["#engine-course"], "focus", "help.control.course_input"],
  [["engine"], "V", ["#engine-speed"], "focus", "help.control.speed_input"],
  [["engine"], "A", ["#engine-quiet"], "click", "help.control.quiet"],
  [["engine"], "+", ["#engine-telegraph"], "order+1", "help.control.engine"],
  [["engine"], "-", ["#engine-telegraph"], "order-1", "help.control.engine"],
  [["engine"], "G", ["#engine-plant"], "cycle:#engine-plant-apply", "help.control.plant"],
  // Sonar (both sides).
  [SONARS, "Shift+A", ["#sonar-ping"], "click", ["help.control.active_ping", "help.uboot_global.ping"]],
  [SONARS, "W", ["#sonar-pulse"], "cycle", "help.control.pulse"],
  [SONARS, "Shift+T", ["#sonar-tma-method"], "cycle", "help.control.tma_method"],
  [SONARS, "E", ["#sonar-bt"], "click", "help.control.bt"],
  [SONARS, "R", ["#sonar-bearing"], "focus", "help.control.listen_input"],
  [SONARS, "N", ["#sonar-notch"], "click", "help.control.notch"],
  [SONARS, "Space", ["#sonar-peak"], "click", "help.control.peak"],
  [SONARS, "J", ["#sonar-live-toggle"], "click", "help.control.audio"],
  [SONARS, "M", [`#selection-station-actions ${action("sonar_designate_target")}`], "click", "help.control.target"],
  [SONARS, "C", ["#classification"], "focus", "help.control.classify"],
  [["sonar"], "G", ["#sonar-release"], "click", "help.control.sonar_release"],
  [["sonar"], "Y", ["#sonar-tas"], "click", "help.control.tas"],
  [["sonar"], "Shift+Y", ["#sonar-vds"], "click", "help.control.vds"],
  [SONARS, "PageDown", ["#sonar-page-tabs"], "step+1", "help.control.pages"],
  [SONARS, "PageUp", ["#sonar-page-tabs"], "step-1", "help.control.pages"],
  // Weapons: D, A, Z, R, Shift+R and V arm their weapon; the dialog confirms.
  [["weapons"], FIRE, ["#weapons-fire-torpedo"], "click", "help.control.fire"],
  [["weapons"], "T", ["#weapons-fire-depth"], "focus", "help.control.torp_depth_input"],
  [["weapons"], "W", ["#weapons-torpedo-type"], "cycle:#weapons-settings-apply", "help.control.torp_type"],
  [["weapons"], "X", ["#weapons-pattern"], "cycle:#weapons-settings-apply", "help.control.torp_pattern"],
  [["weapons"], "Y", ["#weapons-salvo"], "cycle:#weapons-settings-apply", "help.control.torp_salvo"],
  [["weapons"], "D", ["#weapons-fire-helicopter"], "click", "help.control.air_torp"],
  [["weapons"], "V", ["#weapons-fire-nixie"], "click", "help.control.nixie"],
  [["weapons"], "A", ["#weapons-fire-asroc"], "click", "help.control.asroc"],
  [["weapons"], "Z", ["#weapons-drop-depth-charges"], "click", "help.control.depth_charges"],
  [["weapons"], "R", ["#weapons-fire-rbu"], "click", "help.control.rbu"],
  [["weapons"], "Shift+R", ["#weapons-rbu-defence"], "click", "help.control.rbu_defence"],
  // OPZ.
  [["opz"], FIRE, ["#opz-fire-essm"], "click", "help.control.essm"],
  [["opz"], "G", ["#opz-fire-chaff"], "click", "help.control.chaff"],
  [["opz"], "R", ["#opz-radar-surface"], "click", "help.control.surface_radar"],
  [["opz"], "Shift+R", ["#opz-radar-air"], "click", "help.control.air_radar"],
  [["opz"], "I", ["#opz-ciws"], "click", "help.control.ciws_release"],
  [["opz"], "M", ["#opz-designate"], "click", "help.control.designate"],
  [["opz"], "E", ["#opz-range"], "step-1", "help.control.radar_range"],
  [["opz"], "Q", ["#opz-range"], "step+1", "help.control.radar_range"],
  [["opz"], "H", [`#opz-mpa-actions ${action("mpa_request")}`, `#opz-mpa-actions ${action("mpa_return")}`], "click", "help.control.mpa_request"],
  [["opz"], "B", [`#opz-mpa-actions ${action("mpa_drop_buoy")}`], "click", "help.control.mpa_buoy"],
  [["opz"], "Shift+B", [`#opz-mpa-actions ${action("mpa_set_buoy_mode")}`], "click", "help.control.mpa_buoy_mode"],
  [["opz"], "Ctrl+R", [`#opz-mpa-actions ${action("mpa_set_radar")}`], "click", "help.control.mpa_radar"],
  [["opz"], "Shift+M", [`#opz-mpa-actions ${action("mpa_set_mad")}`], "click", "help.control.mpa_mad"],
  [["opz"], "D", ["#opz-fire-mpa"], "click", "help.control.mpa_attack"],
  // Radio room.
  [["radio"], "Enter", [radioCapture], "click", "help.control.log_bearing"],
  [["radio"], "A", [`#radio-tasks ${action("radio_task_accept")}`], "click", "help.control.task_accept"],
  [["radio"], "D", [`#radio-tasks ${action("radio_task_decline")}`], "click", "help.control.task_decline"],
  [["radio"], "R", [`#radio-tasks ${action("radio_request_ras")}`], "click", "help.control.ras_request"],
  [["radio"], "K", [`#radio-tasks ${action("radio_contact_report")}`], "click", "help.control.contact_report"],
  [["radio"], "H", [`#radio-tasks ${action("radio_request_support")}`], "click", "help.control.request_support"],
  // Damage control.
  [["damage"], "ArrowUp", ["#damage-team"], "step-1", "help.control.team"],
  [["damage"], "ArrowDown", ["#damage-team"], "step+1", "help.control.team"],
  [["damage"], "C", ["#damage-counterflood"], "click", "help.control.counterflood"],
  [["damage"], "G", [`#damage-crew-actions ${action("crew_action_stations")}`], "click", "help.control.action_stations_crew"],
  [["damage"], "W", [`#damage-crew-actions ${action("crew_watch_change")}`], "click", "help.control.watch_change"],
  [["damage"], "M", [`#damage-crew-actions ${action("crew_casualty_medic")}`], "click", "help.control.casualty_medic"],
  [["damage"], "U", [`#damage-crew-actions ${action("crew_casualty_reassign")}`], "click", "help.control.casualty_reassign"],
  // Helicopter.
  [["helicopter"], "H", ["#helicopter-launch", "#helicopter-return"], "click", "help.control.helo_toggle"],
  [["helicopter"], "B", ["#helicopter-buoy"], "click", "help.control.drop_buoy"],
  [["helicopter"], "Shift+B", ["#helicopter-buoy-mode"], "cycle", "help.control.buoy_mode"],
  [["helicopter"], "X", ["#helicopter-pattern"], "cycle:#helicopter-pattern-apply", "help.control.buoy_pattern"],
  [["helicopter"], "Ctrl+R", ["#helicopter-radar"], "click", "help.control.helo_radar"],
  [["helicopter"], "Shift+M", ["#helicopter-mad"], "click", "help.control.mad"],
  [["helicopter"], "Z", ["#helicopter-hoist"], "click", "help.control.helo_hoist"],
  [["helicopter"], "Y", ["#helicopter-dip-toggle"], "click", "help.control.dip_toggle"],
  [["helicopter"], "Shift+A", ["#helicopter-dip-ping"], "click", "help.control.dip_ping"],
  [["helicopter"], "F", ["#helicopter-qualify"], "click", "help.control.helo_qualify"],
  [["helicopter"], "G", ["#helicopter-buoy-release"], "click", "help.control.helo_contact_release"],
  [["helicopter"], "C", ["#classification"], "focus", "help.control.classify"],
  [["helicopter"], FIRE, ["#helicopter-fire-torpedo"], "click", "help.control.drop_torp"],
  // ELOKA (F, Shift+F, Ctrl+F, Z and the arrows: eloka-filters.js).
  [["eloka"], "E", [selectedAction("eloka-intercepts", "eloka_set_jamming")], "click", "help.control.eloka_jamming"],
  [["eloka"], "Shift+E", [selectedAction("eloka-intercepts", "eloka_set_technique")], "click", "help.control.eloka_technique"],
  [["eloka"], "A", [selectedAction("eloka-intercepts", "eloka_set_auto")], "click", "help.control.eloka_auto"],
  [["eloka"], "C", [selectedAction("eloka-intercepts", "eloka_annotate")], "click", "help.control.eloka_annotation"],
  // The submarine's stations.
  [["uboot", "uboot_nav"], "C", ["#uboot-course"], "focus", "help.uboot.orders"],
  [["uboot", "uboot_nav"], "D", ["#uboot-depth"], "focus", "help.uboot.orders"],
  [["uboot", "uboot_engine"], "V", ["#uboot-speed"], "focus", "help.uboot.orders"],
  [["uboot", "uboot_engine"], "+", ["#station-uboot .uboot-telegraph"], "order+1", "help.uboot.telegraph"],
  [["uboot", "uboot_engine"], "-", ["#station-uboot .uboot-telegraph"], "order-1", "help.uboot.telegraph"],
  [BOAT, "Shift+A", ["#uboot-ping"], "click", "help.uboot_global.ping"],
  [BOAT, "Ctrl+B", ["#uboot-clear-baffles"], "click", "help.uboot.clear_baffles"],
  [BOAT, "A", [mode("uboot_silent")], "toggle", "help.uboot.silent"],
  [BOAT, "N", [mode("uboot_snorkel")], "toggle", "help.uboot.snorkel"],
  [BOAT, "P", [mode("uboot_mast")], "toggle", "help.uboot.mast"],
  [BOAT, "Shift+G", [mode("uboot_bottom")], "toggle", "help.uboot.bottom"],
  [BOAT, "Shift+H", [mode("uboot_surface")], "toggle", "help.uboot.surface"],
  [BOAT, "B", [mode("uboot_buoy")], "toggle", "help.uboot.buoy"],
  [BOAT, "Z", [mode("uboot_trim_auto")], "toggle", "help.uboot.trim_auto"],
  [BOAT, "I", ["#uboot-evade"], "click", "help.uboot.evade"],
  [BOAT, "O", ["#uboot-o2-candle"], "click", "help.uboot.o2_candle"],
  [BOAT, "Shift+O", ["#uboot-absorber"], "click", "help.uboot.absorber"],
  [BOAT, "Backspace", ["#uboot-route-clear"], "click", "help.uboot.route_clear"],
  [BOAT, "G", [`#uboot-crew-actions ${action("uboot_action_stations")}`], "click", "help.uboot.action_stations"],
  [BOAT, "M", [`#uboot-crew-actions ${action("uboot_casualty_medic")}`], "click", "help.uboot.casualty_medic"],
  [BOAT, "U", [`#uboot-crew-actions ${action("uboot_casualty_reassign")}`], "click", "help.uboot.casualty_reassign"],
  [["uboot_radio"], "Enter", ["#uboot-radio-send"], "click", "help.uboot.radio_send"],
  [["uboot"], FIRE, ["#uboot-scope-fire"], "click", "help.uboot.scope_fire"],
  [["uboot_weapons"], FIRE, ["#uboot-fire"], "click", "help.uboot.fire"],
  [["uboot_weapons"], "V", ["#uboot-decoy"], "click", "help.uboot.decoy"],
  [["uboot_weapons"], "T", ["#uboot-fire-depth"], "focus", "help.uboot.torpedo_depth"],
  [["uboot_weapons"], "Y", ["#uboot-fire-salvo"], "cycle", "help.uboot.salvo"],
  [["uboot_weapons"], "X", ["#uboot-seeker-pattern"], "cycle:#uboot-seeker-apply", "help.uboot.torpedo_pattern"],
  [["uboot_weapons"], "W", ["#uboot-wire-steer"], "click", "help.uboot.wire_steer"],
  [["uboot_weapons"], "Shift+W", ["#uboot-wire-cut"], "click", "help.uboot.wire_cut"],
];

const GERMAN = {Ctrl: "Strg", Shift: "Umschalt", Enter: "Eingabe", Backspace: "Rücktaste", PageUp: "Bild↑", PageDown: "Bild↓", Home: "Pos1",
  Space: "Leertaste", ArrowUp: "↑", ArrowDown: "↓"};
const ENGLISH = {PageUp: "PgUp", PageDown: "PgDn", ArrowUp: "↑", ArrowDown: "↓"};

export function keyLabel(key, language = S.language) {
  const names = language === "de" ? GERMAN : ENGLISH;
  // "+" and "-" name a key of their own, never a combination.
  if (key === "+" || key === "-") return key;
  return key.split("+").map((part) => names[part] ?? part).join("+");
}

function parse(key) {
  if (key === "+" || key === "-") return {key, ctrl: false, shift: null};
  const parts = key.split("+");
  return {key: parts.at(-1), ctrl: parts.includes("Ctrl"), shift: parts.includes("Shift")};
}

function usable(element) {
  return element && !element.disabled && !element.closest("[hidden]") && element.getClientRects().length > 0;
}

// A list stepped by a key may sit on a hidden control page: it still works.
function reachable(element, how) {
  return how.startsWith("cycle") ? element && !element.disabled : usable(element);
}

const resolve = (target) => typeof target === "function" ? target() : document.querySelector(target);

// The element that carries the cap: a value field's submit button, a
// checkbox's label, a list's own label; otherwise the control itself.
function capHost(element) {
  // A checkbox cannot show a cap of its own (replaced element): use its label.
  if (element.matches("input[type=checkbox], select")) {
    return element.closest("label") ?? document.querySelector(`label[for="${element.id}"]`) ?? element;
  }
  if (element.matches("input")) return element.form?.querySelector("button[type=submit]") ?? element;
  return element;
}

// Caps of the held station only: several stations share one control (the
// helicopter's live sonar button is the sonar's), and a cap must name a key
// that works here.
const marked = new Set();

// Called after every render too (rows are rebuilt and lose their caps); only
// changed caps are written, so an unchanged page sees no DOM mutation.
export function markStationKeys(role = S.v2State?.role) {
  const seen = new Map();
  for (const [roles, key, targets, how] of STATION_KEYS) for (const target of targets) {
    if (!roles.includes(role)) continue;
    const element = resolve(target);
    if (!element) continue;
    const host = (how ?? "").match(/^(step|order)/) && !element.matches("select") ? element : capHost(element);
    seen.set(host, [...(seen.get(host) ?? []), keyLabel(key)]);
  }
  for (const host of [...marked]) if (!seen.has(host)) {
    delete host.dataset.keycap;
    marked.delete(host);
  }
  for (const [host, caps] of seen) {
    const text = [...new Set(caps)].join(" / ");
    if (host.dataset.keycap !== text) host.dataset.keycap = text;
    marked.add(host);
  }
}

function step(element, delta, wrap = false) {
  if (element.matches("select")) {
    const count = element.options.length;
    if (!count) return false;
    const index = wrap ? (element.selectedIndex + delta + count) % count
      : Math.max(0, Math.min(count - 1, element.selectedIndex + delta));
    if (index === element.selectedIndex) return false;
    element.selectedIndex = index;
    element.dispatchEvent(new Event("change", {bubbles: true}));
    return true;
  }
  const tabs = [...element.querySelectorAll("button")].filter(usable);
  if (!tabs.length) return false;
  const pressed = tabs.findIndex((tab) => tab.getAttribute("aria-selected") === "true" || tab.getAttribute("aria-pressed") === "true");
  const index = pressed < 0 ? (delta > 0 ? 0 : tabs.length - 1) : (pressed + delta + tabs.length) % tabs.length;
  if (!wrap && pressed >= 0 && (pressed + delta < 0 || pressed + delta >= tabs.length)) return false;
  tabs[index].click();
  return true;
}

function apply(element, how) {
  if (how === "focus") { element.focus(); element.select?.(); return; }
  if (how.startsWith("step")) { step(element, how === "step+1" ? 1 : -1); return; }
  if (how.startsWith("cycle")) {
    if (step(element, 1, true) && how.includes(":")) document.querySelector(how.slice(how.indexOf(":") + 1))?.click();
    return;
  }
  if (how.startsWith("order")) {
    const delta = how === "order+1" ? 1 : -1;
    if (element.matches("select")) {
      if (step(element, delta)) $(`${element.id}-submit`)?.click();
    } else step(element, delta);
    return;
  }
  if (how === "toggle") {
    const pair = [...document.querySelectorAll(`[data-uboot-mode="${element.dataset.ubootMode}"]`)].filter(usable);
    (pair.find((button) => button.getAttribute("aria-pressed") !== "true") ?? element).click();
    return;
  }
  element.click();
}

function eventKey(event) {
  if (event.key === " ") return "Space";
  return event.key.length === 1 ? event.key.toUpperCase() : event.key;
}

export function bindingFor(role, event) {
  const key = eventKey(event);
  for (const binding of STATION_KEYS) {
    const want = parse(binding[1]);
    if (!binding[0].includes(role) || want.key !== key || want.ctrl !== event.ctrlKey ||
        (want.shift !== null && want.shift !== event.shiftKey)) continue;
    const how = binding[3] ?? "click";
    const element = binding[2].map(resolve).find((item) => reachable(item, how));
    if (element) return {element, how};
  }
  return null;
}

// The station's own number again turns its page, as on the uConsole.
function samePage(role, event) {
  if (!/^[1-9]$/.test(event.key) || event.shiftKey || event.ctrlKey) return null;
  const station = sideStations(role)[Number(event.key) - 1];
  if (station !== role || stationKey(role) !== Number(event.key)) return null;
  return bindingFor(role, {key: "PageDown", ctrlKey: false, shiftKey: false});
}

export function init() {
  markStationKeys();
  window.addEventListener("u-jagd-language", () => queueMicrotask(() => markStationKeys()));
  on("layout:station", (station) => markStationKeys(station));
  document.addEventListener("keydown", (event) => {
    const role = S.v2State?.role;
    if (!role || S.session?.station !== role || event.altKey || event.metaKey || event.isComposing ||
        event.repeat || event.defaultPrevented || $("operations").hidden) return;
    const target = event.target;
    if (target instanceof Element && (target.closest("input, select, textarea, dialog[open]") || target.isContentEditable)) return;
    // Enter and Space keep their own meaning on a focused button or link.
    if ((event.key === "Enter" || event.key === " ") && target instanceof Element &&
        target.closest("button, a, summary, [role=tab], [role=button]")) return;
    const binding = bindingFor(role, event) ?? samePage(role, event);
    if (!binding) return;
    event.preventDefault();
    apply(binding.element, binding.how);
  });
}
