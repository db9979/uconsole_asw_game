import { S } from "../state/store.js";
import { $, affiliations, domains } from "../core/base.js";
import { classificationText, enumText, number, t, unit } from "../core/format.js";
import { sendStationAction } from "../net/commands.js";
import { animatedPlots, syncPlotAnimation } from "../plot/clock.js";
import { spectrumStates } from "../plot/spectrum.js";
import { sightingText } from "../state/schema.js";
import { visualCanvasIds } from "../state/shared.js";
import { releaseCanvas } from "./chart.js";
import { stopOpzSweepAnimation } from "./role-map.js";
import { stationActionAvailable } from "../state/availability.js";

export function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = String(text ?? "");
  if (className) element.className = className;
  return element;
}
// Visual add-on for high-importance command/fire results, alongside (not
// instead of) the role=status/aria-live text that already carries this to
// screen readers - a busy operator screen can otherwise bury that text.
export function showToast(key, values, variant) {
  const region = $("toast-region");
  if (!region) return;
  const toast = node("p", t(key, values), `toast toast-${variant}`);
  region.appendChild(toast);
  setTimeout(() => toast.remove(), 5000);
}
export function metrics(element, entries) {
  entries.forEach(([key, value], index) => {
    let group = element.children[index];
    if (!group) { group = node("div"); group.append(node("dt"), node("dd")); element.append(group); }
    const label = t(key), raw = String(value ?? ""), none = raw === t("station_none");
    // Nothing published yet reads as a quiet dash; the sentence stays the hover note.
    const text = none ? "\u2014" : raw, cell = group.lastChild;
    if (group.firstChild.textContent !== label) group.firstChild.textContent = label;
    if (cell.textContent !== text) cell.textContent = text;
    if (none) { cell.dataset.empty = "true"; cell.title = raw; }
    else if (cell.dataset.empty) { delete cell.dataset.empty; cell.removeAttribute("title"); }
  });
  while (element.children.length > entries.length) element.lastChild.remove();
}
export const yesNo = (value) => typeof value === "boolean" ? t(value ? "yes" : "no") : t("unavailable");
export const position = (value) => `${unit(value?.x, "NM")} / ${unit(value?.y, "NM")}`;
const rawFields = (value) => Object.entries(value || {}).map(([key, item]) =>
  `${key}: ${Array.isArray(item) ? item.join(", ") : String(item ?? t("unavailable"))}`).join(" / ");
export function actionButton(labelKey, action, params, ready = true, values = {}) {
  const button = node("button", t(labelKey, values), "station-action");
  button.type = "button";
  button.dataset.stationAction = action;
  button.dataset.ready = String(ready);
  button.dataset.stationParams = JSON.stringify(params ?? {});
  button.disabled = !stationActionAvailable() || !ready;
  button.addEventListener("click", () => sendStationAction(action, params));
  return button;
}
export function clearFireConfirmation() {
  S.fireConfirmation = null;
  clearTimeout(S.fireConfirmationTimer);
  S.fireConfirmationTimer = null;
  const dialog = $("fire-confirm-dialog");
  if (dialog?.open) dialog.close();
}
export function clearFireDrafts() {
  clearFireConfirmation();
  for (const id of ["weapons-fire-target", "weapons-fire-depth", "helicopter-fire-target",
    "helicopter-fire-depth", "opz-fire-target", "uboot-fire-target", "uboot-fire-bearing", "uboot-fire-range"]) {
    S.stationDrafts.delete(id);
    $(id).value = "";
  }
}
// A control the operator is using (focused, a drop-down list open) is left
// alone by state pushes: rebuilding or re-setting it would close the list or
// throw the pick away. The first push after it loses focus catches it up.
export const inUse = (element) => element === document.activeElement;
export function setControlValue(element, value) {
  if (!inUse(element) && element.value !== value) element.value = value;
}
// Replace a drop-down's options only when they changed and it is not in use;
// the chosen value survives when it is still offered. `rows` is [[value, text]].
export function setOptions(select, rows) {
  const signature = JSON.stringify(rows);
  if (inUse(select) || select.dataset.optionsSignature === signature) return false;
  const previous = select.value;
  select.replaceChildren(...rows.map(([value, text]) => {
    const option = node("option", text);
    option.value = value;
    return option;
  }));
  select.dataset.optionsSignature = signature;
  if (rows.some(([value]) => value === previous)) select.value = previous;
  return true;
}
// Bring `element`'s children in line with freshly built `nodes`, keeping every
// element whose tag, row key and action parameters match: a button under the
// pointer stays the same button, so a click is not lost when a push lands
// between press and release.
export function patchChildren(element, nodes) {
  nodes.forEach((fresh, index) => {
    const current = element.childNodes[index];
    if (!current) element.append(fresh);
    else if (!patchNode(current, fresh)) current.replaceWith(fresh);
  });
  while (element.childNodes.length > nodes.length) element.lastChild.remove();
}
function patchNode(current, fresh) {
  if (current.nodeType !== fresh.nodeType || current.nodeName !== fresh.nodeName) return false;
  if (current.nodeType !== Node.ELEMENT_NODE) {
    if (current.nodeValue !== fresh.nodeValue) current.nodeValue = fresh.nodeValue;
    return true;
  }
  for (const key of ["rowKey", "stationParams", "stationAction"])
    if (current.dataset[key] !== fresh.dataset[key]) return false;
  for (const {name} of [...current.attributes]) if (!fresh.hasAttribute(name)) current.removeAttribute(name);
  for (const {name, value} of [...fresh.attributes]) if (current.getAttribute(name) !== value) current.setAttribute(name, value);
  if ("disabled" in current && current.disabled !== fresh.disabled) current.disabled = fresh.disabled;
  patchChildren(current, [...fresh.childNodes]);
  return true;
}
export function fillFireTargets(id, rows, designated = null) {
  const select = $(id);
  if (inUse(select)) return;
  // Without an operator draft, the sonar room's designated target is preselected.
  const previous = S.stationDrafts.has(id) ? select.value : designated || "";
  setOptions(select, [["", t("fire_select_target")], ...rows.map((row) => [row.ref, t("fire_target_option", {
    label: row.label || row.ref, bearing: number(row.bearing, 0), range: number(row.range_nm, 1),
  })])]);
  select.value = rows.some((row) => row.ref === previous) ? previous : "";
  if (previous && !select.value) clearFireConfirmation();
}
export function stationRows(element, rows, entryBuilder, emptyKey = "station_none", actionBuilder = null) {
  const existing = new Map([...element.children].map((child) => [child.dataset.rowKey, child]));
  const live = new Set();
  rows.forEach((row, index) => {
    const key = String(row.ref ?? row.key ?? row.team ?? row.tube ?? index);
    live.add(key);
    let article = existing.get(key);
    if (!article) {
      article = node("article", undefined, "station-row"); article.dataset.rowKey = key;
      article.append(node("h4"), node("dl", undefined, "detail-metrics"), node("div", undefined, "station-row-actions"));
    }
    const entries = entryBuilder(row, index);
    const title = entries.shift();
    article.firstChild.textContent = String(title[1] ?? "");
    metrics(article.children[1], entries);
    const actions = actionBuilder?.(row) || [];
    const signature = JSON.stringify(actions.map((button) => [button.textContent, button.dataset, button.disabled]));
    if (signature !== article.dataset.actions) { article.lastChild.replaceChildren(...actions); article.dataset.actions = signature; }
    article.lastChild.hidden = !actions.length;
    if (element.children[index] !== article) element.insertBefore(article, element.children[index] || null);
  });
  for (const child of [...element.children]) if (!live.has(child.dataset.rowKey)) child.remove();
  if (!rows.length) element.replaceChildren(node("p", t(emptyKey), "empty"));
}
export function clearVisuals() {
  animatedPlots.clear();
  spectrumStates.clear();
  syncPlotAnimation();
  stopOpzSweepAnimation();
  S.roleMapHits = [];
  S.roleMapInfo = [];
  S.damageHits = [];
  for (const id of visualCanvasIds) releaseCanvas($(id));
  for (const element of document.querySelectorAll(".visual-equivalent")) element.replaceChildren();
  $("role-visual-state").textContent = "";
  $("role-map-scale").textContent = "";
}
export function tacticalEntries(row) {
  return [["reference", row.label], ["domain", enumText(domains, row.domain)],
    ["source", row.source], ["affiliation", enumText(affiliations, row.affiliation)],
    ["bearing", unit(row.bearing, "\u00b0", 0)], ["range", unit(row.range_nm, "NM")],
    ["position", position(row)], ["course", unit(row.course, "\u00b0", 0)], ["speed", unit(row.speed_kn, "kn")],
    ...(row.domain === "AIR" ? [["altitude", unit(row.altitude_m, "m", 0)]] : []),
    ["quality", number(row.quality, 2)], ["age", unit(row.age_s, "s", 0)],
    ["bearing_uncertainty", unit(row.bearing_uncertainty_deg, "\u00b0")],
    ["range_uncertainty", unit(row.range_uncertainty_nm, "NM")],
    ...(row.visual_class ? [["sighting", sightingText(row.visual_class, row.visual_type)]] : [])];
}
export function sonarEntries(row) {
  return [["reference", row.label], ["source", row.source],
    ["classification", classificationText(row.classification)], ["catalog_profile", row.profile || t("station_none")],
    ["bearing", unit(row.bearing, "\u00b0", 0)],
    ["range", unit(row.range_nm, "NM")], ["position", position(row)], ["depth", unit(row.depth_m, "m", 0)],
    ["course", unit(row.course, "\u00b0", 0)], ["speed", unit(row.speed_kn, "kn")],
    ["quality", number(row.quality, 2)], ["age", unit(row.age_s, "s", 0)],
    ["fix_age", unit(row.fix_age_s, "s", 0)], ["bearing_uncertainty", unit(row.bearing_uncertainty_deg, "\u00b0")],
    ["range_uncertainty", unit(row.range_uncertainty_nm, "NM")],
    ["station_fixes", row.fixes.map((fix) => rawFields(fix)).join(" | ") || t("station_none")]];
}
export function weaponTargetEntries(row) {
  return [["reference", row.label], ["domain", enumText(domains, row.domain)],
    ["source", row.source], ["affiliation", enumText(affiliations, row.affiliation)],
    ["classification", classificationText(row.classification)], ["bearing", unit(row.bearing, "\u00b0", 0)],
    ["range", unit(row.range_nm, "NM")], ["position", position(row)], ["depth", unit(row.depth_m, "m", 0)],
    ["course", unit(row.course, "\u00b0", 0)], ["speed", unit(row.speed_kn, "kn")],
    ["quality", number(row.quality, 2)], ["age", unit(row.age_s, "s", 0)], ["fix_age", unit(row.fix_age_s, "s", 0)],
    ["bearing_uncertainty", unit(row.bearing_uncertainty_deg, "\u00b0")],
    ["range_uncertainty", unit(row.range_uncertainty_nm, "NM")]];
}
