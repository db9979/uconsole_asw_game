// The ELOKA list switches above the bearing rose (the browser twin of the
// uConsole's key chips F, Shift+F, Ctrl+F and Z) and the step through the
// selected emitter group (←/→). Client-local presentation state only: the
// buttons are fixed in index.html, a state push only changes their text.
import { $ } from "../core/base.js";
import { number, selectedTrack, t } from "../core/format.js";
import { S } from "../state/store.js";
import { buildDisplayModel } from "../state/display-model.js";
import { elokaFilters, filteredEloka, groupedEloka, stepElokaFilter } from "../state/shared.js";
import { renderSnapshot } from "../views/render.js";

const SELECTS = {status: "eloka-status-filter", threat: "eloka-threat-filter", band: "eloka-band-filter"};

function valueText(key) {
  const value = elokaFilters[key];
  if (key === "group") return t(value ? "opz_display_value_on" : "opz_display_value_off");
  if (key === "band") return value === "ALL" ? t("eloka_filter_all") : value.toUpperCase().replace("_", "/");
  if (key === "threat") return value === "ALL" ? t("eloka_filter_all") : t(`eloka_threat_${value.toLowerCase()}`);
  return t(`eloka_filter_${value.toLowerCase()}`);
}
function selectedGroup() {
  const payload = S.v2State?.role === "eloka" ? S.v2State.eloka : null;
  const track = selectedTrack();
  if (!payload || !track?.eloka) return {members: [], index: -1};
  const members = track.eloka.members;
  return {members, index: members.indexOf(track.ref)};
}
export function syncElokaFilterBar() {
  const bar = $("eloka-filter-bar");
  if (!bar) return;
  for (const button of bar.querySelectorAll("button[data-eloka-filter]")) {
    const key = button.dataset.elokaFilter, text = `${t(`eloka_chip_${key}`)}: ${valueText(key)}`;
    const label = button.querySelector("span");
    if (label.textContent !== text) label.textContent = text;
    if (key === "group" && button.getAttribute("aria-pressed") !== String(elokaFilters.group))
      button.setAttribute("aria-pressed", String(elokaFilters.group));
  }
  for (const [key, id] of Object.entries(SELECTS)) if ($(id) && $(id).value !== elokaFilters[key]) $(id).value = elokaFilters[key];
  const {members, index} = selectedGroup();
  const position = members.length > 1 ? t("eloka_group_position", {index: number(index + 1, 0), count: number(members.length, 0)}) : t("eloka_group_single");
  if ($("eloka-group-position").textContent !== position) $("eloka-group-position").textContent = position;
  for (const button of bar.querySelectorAll("button[data-eloka-member]")) button.disabled = members.length < 2;
  const payload = S.v2State?.role === "eloka" ? S.v2State.eloka : null;
  const count = payload ? t("eloka_bar_count", {emitters: number(groupedEloka(payload.intercepts).length, 0),
    visible: number(filteredEloka(payload.intercepts).length, 0), total: number(payload.intercepts.length, 0)}) : "";
  if ($("eloka-bar-count").textContent !== count) $("eloka-bar-count").textContent = count;
}
function refresh() {
  if (S.v2State?.role === "eloka") {
    S.snapshot = buildDisplayModel(S.v2State);
    if (!selectedTrack()) S.selected = null;
    renderSnapshot();
  }
  syncElokaFilterBar();
}
export function changeElokaFilter(key, value = undefined) {
  if (value === undefined) stepElokaFilter(key); else elokaFilters[key] = value;
  refresh();
}
export function stepElokaMember(delta) {
  const {members, index} = selectedGroup();
  if (members.length < 2) return;
  S.selected = members[(index + delta + members.length) % members.length];
  refresh();
}
export function init() {
  const bar = $("eloka-filter-bar");
  for (const button of bar.querySelectorAll("button[data-eloka-filter]"))
    button.addEventListener("click", () => changeElokaFilter(button.dataset.elokaFilter));
  for (const button of bar.querySelectorAll("button[data-eloka-member]"))
    button.addEventListener("click", () => stepElokaMember(Number(button.dataset.elokaMember)));
  for (const [key, id] of Object.entries(SELECTS)) $(id).addEventListener("change", () => changeElokaFilter(key, $(id).value));
  // The same keys as the uConsole while this browser holds the ELOKA.
  document.addEventListener("keydown", (event) => {
    if (S.session?.station !== "eloka" || S.v2State?.role !== "eloka" || event.altKey || event.metaKey ||
        event.repeat || event.isComposing || $("operations").hidden) return;
    const target = event.target;
    if (target instanceof Element && (target.closest("input, select, textarea, dialog[open]") || target.isContentEditable)) return;
    const key = event.key.toLowerCase();
    let action = null;
    if (key === "f") action = () => changeElokaFilter(event.ctrlKey ? "band" : event.shiftKey ? "threat" : "status");
    else if (key === "z" && !event.ctrlKey) action = () => changeElokaFilter("group");
    else if ((event.key === "ArrowLeft" || event.key === "ArrowRight") && !event.ctrlKey &&
             !(target instanceof Element && target.closest("[role=tab], canvas")))
      action = () => stepElokaMember(event.key === "ArrowRight" ? 1 : -1);
    if (!action) return;
    event.preventDefault();
    action();
  });
}
