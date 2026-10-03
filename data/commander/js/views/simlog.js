import { S } from "../state/store.js";
import { $, phases } from "../core/base.js";
import { authenticated, duration, enumText, finite, hasPosition, number, t } from "../core/format.js";
import { colors, palette } from "../core/palette.js";
import { request } from "../net/request.js";
import { drawSymbolOn } from "../plot/symbols.js";
import { buildDisplayModel, contextKey } from "../state/display-model.js";
import { boundedArray, exactKeys, validateV2State } from "../state/schema.js";
import { releaseCanvas, resizeCanvas } from "./chart.js";
import { node } from "./dom.js";
import { renderLobby } from "./lobby.js";
import { schedule } from "../core/scheduler.js";
import { canvas, lookoutCanvas, simlogMapCanvas, simlogMapCtx } from "./canvases.js";

  // Hidden view (#simlog): complete bounded simulation log, read-only.
// Every entry carries its normal role context plus a detached full-truth
// diagnostic snapshot, fully tabulated and plottable on the snapshot map.
export function simlogActive() { return location.hash === "#simlog" && authenticated(); }
export function applySimlogView() {
  const active = simlogActive();
  $("simlog-view").hidden = !active;
  $("operations").hidden = active;
  if (S.session) renderLobby();
  if (active) { releaseCanvas(canvas); releaseCanvas(lookoutCanvas); }
}
function simlogMetricBlock(titleKey, entries) {
  const wrap = node("div", undefined, "simlog-metrics-wrap");
  wrap.append(node("h4", t(titleKey)));
  const dl = node("dl", undefined, "metrics");
  for (const [key, value] of entries) {
    const group = node("div");
    group.append(node("dt", t(key)), node("dd", value));
    dl.append(group);
  }
  wrap.append(dl);
  return wrap;
}
// Map items are supplied by the selected full-truth diagnostic snapshot.
function simlogMapItems(display) {
  const items = [];
  if (hasPosition(display.ownship)) {
    items.push({ section: "ship", value: display.ownship, domain: "SURFACE", color: palette().liveStrong,
      x: display.ownship.x, y: display.ownship.y, label: t("simlog_own") });
  }
  for (const track of display.tracks) {
    if (!hasPosition(track)) continue;
    items.push({ section: "track", value: track, domain: track.domain,
      color: colors[track.affiliation] || colors.UNKNOWN,
      x: track.x, y: track.y, label: track.label });
  }
  return items;
}
function simlogMapBounds(items) {
  if (S.simlogMapFit === "world" && finite(S.chart?.size_nm) && S.chart.size_nm > 0) {
    return { left: 0, right: S.chart.size_nm, top: 0, bottom: S.chart.size_nm };
  }
  if (!items.length) return { left: 0, right: 1, top: 0, bottom: 1 };
  const minX = Math.min(...items.map((item) => item.x));
  const maxX = Math.max(...items.map((item) => item.x));
  const minY = Math.min(...items.map((item) => item.y));
  const maxY = Math.max(...items.map((item) => item.y));
  const span = Math.max(10, maxX - minX, maxY - minY);
  const centerX = (minX + maxX) / 2;
  const centerY = (minY + maxY) / 2;
  const radius = span * .58;
  return { left: centerX - radius, right: centerX + radius,
    top: centerY - radius, bottom: centerY + radius };
}
function simlogMapLabel(item) {
  const parts = [item.label];
  if (finite(item.value.course)) parts.push(`${number(item.value.course, 0)}\u00b0`);
  const speed = finite(item.value.speed) ? item.value.speed : item.value.speed_kn;
  if (finite(speed)) parts.push(`${number(speed, 1)} kn`);
  return parts.join(" \u00b7 ");
}
export function queueSimlogMapDraw() {
  schedule("simlog-map", drawSimlogMap);
}
function drawSimlogMap() {
  if (!S.simlogMapData || !$("simlog-map-dialog").open) return;
  const width = simlogMapCanvas.clientWidth;
  const height = simlogMapCanvas.clientHeight;
  if (!width || !height) return;
  resizeCanvas(simlogMapCanvas, simlogMapCtx, width, height);
  const context = simlogMapCtx;
  context.fillStyle = palette().scopeBg;
  context.fillRect(0, 0, width, height);
  const items = simlogMapItems(S.simlogMapData);
  const bounds = simlogMapBounds(items);
  const pad = Math.max(24, Math.min(width, height) * .06);
  const scale = Math.max(.0001, Math.min((width - pad * 2) / Math.max(.001, bounds.right - bounds.left),
    (height - pad * 2) / Math.max(.001, bounds.bottom - bounds.top)));
  const contentWidth = (bounds.right - bounds.left) * scale;
  const contentHeight = (bounds.bottom - bounds.top) * scale;
  const offsetX = (width - contentWidth) / 2;
  const offsetY = (height - contentHeight) / 2;
  const point = (x, y) => [offsetX + (x - bounds.left) * scale, offsetY + (y - bounds.top) * scale];
  context.strokeStyle = palette().grid;
  context.lineWidth = 1;
  context.beginPath();
  for (let index = 0; index <= 5; index += 1) {
    const x = offsetX + contentWidth * index / 5;
    const y = offsetY + contentHeight * index / 5;
    context.moveTo(x, offsetY); context.lineTo(x, offsetY + contentHeight);
    context.moveTo(offsetX, y); context.lineTo(offsetX + contentWidth, y);
  }
  context.stroke();
  if (S.chart && Array.isArray(S.chart.landmasses)) {
    context.fillStyle = palette().land;
    context.strokeStyle = palette().landEdge;
    for (const land of S.chart.landmasses) {
      if (!land.points.length) continue;
      context.beginPath();
      land.points.forEach(([x, y], index) => {
        const [px, py] = point(x, y);
        if (!index) context.moveTo(px, py); else context.lineTo(px, py);
      });
      context.closePath(); context.fill(); context.stroke();
    }
  }
  context.strokeStyle = palette().lineStrong;
  context.setLineDash([5, 5]);
  context.strokeRect(offsetX, offsetY, contentWidth, contentHeight);
  context.setLineDash([]);
  const fontSize = Math.max(11, parseFloat(getComputedStyle(document.documentElement).fontSize) * .68);
  context.font = `${fontSize}px ui-monospace, monospace`;
  const plotted = items.map((item) => {
    const [x, y] = point(item.x, item.y);
    const course = item.value.course;
    const angle = finite(course) ? course * Math.PI / 180 : null;
    const endX = angle === null ? x : x + Math.sin(angle) * 24;
    const endY = angle === null ? y : y - Math.cos(angle) * 24;
    return { item, x, y, endX, endY };
  });
  const occupied = plotted.map(({ x, y, endX, endY }, index) => ({
    x: Math.min(x, endX) - 9, y: Math.min(y, endY) - 9,
    right: Math.max(x, endX) + 9, bottom: Math.max(y, endY) + 9, index,
  }));
  occupied.push({ x: width - 70, y: 0, right: width, bottom: 48, index: -1 });
  for (const { item, x, y, endX, endY } of plotted) {
    if (finite(item.value.course)) {
      context.strokeStyle = item.color;
      context.lineWidth = 1.4;
      context.beginPath(); context.moveTo(x, y); context.lineTo(endX, endY); context.stroke();
    }
    if (item.section === "ship") {
      context.fillStyle = item.color;
      context.beginPath(); context.arc(x, y, 3.5, 0, Math.PI * 2); context.fill();
    } else {
      drawSymbolOn(context, x, y, item.domain, item.color, 6, item.value?.affiliation);
    }
    if (item.value.sunk === true || item.value.dead === true) {
      context.strokeStyle = item.color;
      context.beginPath(); context.moveTo(x - 8, y - 8); context.lineTo(x + 8, y + 8); context.stroke();
    }
  }
  plotted.forEach(({ item, x }, index) => {
    const label = simlogMapLabel(item);
    const textWidth = context.measureText(label).width;
    const footprint = occupied[index];
    const candidates = [[footprint.right + 4, footprint.y + fontSize],
      [footprint.right + 4, footprint.bottom + fontSize + 3],
      [footprint.x - textWidth - 4, footprint.y + fontSize],
      [x - textWidth / 2, footprint.bottom + fontSize + 4]];
    const candidate = candidates.map(([tx, ty]) => ({ x: tx, y: ty - fontSize, right: tx + textWidth, bottom: ty + 3, ty }))
      .find((box) => box.x >= 3 && box.y >= 3 && box.right <= width - 3 && box.bottom <= height - 3 &&
        occupied.every((other) => box.right < other.x || box.x > other.right ||
          box.bottom < other.y || box.y > other.bottom));
    if (candidate) {
      context.fillStyle = item.color;
      context.fillText(label, candidate.x, candidate.ty);
      occupied.push({ ...candidate, index: -1 });
    }
  });
  context.fillStyle = palette().text;
  context.fillText(t("north"), width - 28, 20);
  context.strokeStyle = palette().text;
  context.beginPath(); context.moveTo(width - 22, 42); context.lineTo(width - 22, 25); context.lineTo(width - 27, 32); context.moveTo(width - 22, 25); context.lineTo(width - 17, 32); context.stroke();
}
export function closeSimlogMap() {
  const dialog = $("simlog-map-dialog");
  if (dialog.open) dialog.close();
  // Cleanup lives on the native "close" event (below) so every dismissal
  // path - this helper, the dialog's own close button, or the browser's
  // built-in Escape handling - converges on the same state reset.
}
function openSimlogMap(data, stamp, seq, latest = false) {
  if (!data || typeof data !== "object") return;
  const dialog = $("simlog-map-dialog");
  if (!dialog.open) {
    S.simlogMapFit = "world";
    $("simlog-map-world").setAttribute("aria-pressed", "true");
    $("simlog-map-units-fit").setAttribute("aria-pressed", "false");
  }
  S.simlogMapData = data;
  S.simlogMapSeq = seq;
  S.simlogMapLatest = latest;
  const items = simlogMapItems(data);
  $("simlog-map-stamp").textContent = stamp;
  $("simlog-map-count").textContent = t("simlog_map_count", { count: number(items.length, 0) });
  $("simlog-map-units").replaceChildren(...items.map((item) => {
    const entry = node("li", `${simlogMapLabel(item)}: ${number(item.x, 1)} / ${number(item.y, 1)} NM`);
    entry.style.setProperty("--unit-color", item.color);
    return entry;
  }));
  if (!dialog.open) { dialog.hidden = false; dialog.showModal(); }
  queueSimlogMapDraw();
}
// ---- Debrief timeline and export (observer and solo host) -----------------
// Marks come from the recorded entries themselves: a new own or hostile
// torpedo (shot), a sunk or dead unit (loss), more contacts than before
// (contact), own damage rising (hit).  Clicking a mark scrubs the current
// snapshot to that entry.
const SIMLOG_MARK_KINDS = ["shot", "enemy_shot", "hit", "contact", "loss"];
function simlogIds(rows) { return new Set((rows || []).map((row) => row.id ?? row.seq ?? null).filter((id) => id !== null)); }
function simlogLosses(rows) { return (rows || []).filter((row) => row.sunk === true || row.dead === true).length; }
export function simlogMarks(entries) {
  const marks = [];
  let previous = null;
  for (const entry of entries) {
    const truth = entry.truth || {};
    const kinds = new Set();
    if (previous) {
      const before = previous.truth || {};
      if ([...simlogIds(truth.torpedoes)].some((id) => !simlogIds(before.torpedoes).has(id))) kinds.add("shot");
      if ([...simlogIds(truth.enemy_torpedoes)].some((id) => !simlogIds(before.enemy_torpedoes).has(id))) kinds.add("enemy_shot");
      if (finite(truth.ship?.damage) && finite(before.ship?.damage) && truth.ship.damage > before.ship.damage + .5) kinds.add("hit");
      const lossesNow = ["subs", "surfaces", "torpedoes", "enemy_torpedoes"].reduce((sum, key) => sum + simlogLosses(truth[key]), 0);
      const lossesBefore = ["subs", "surfaces", "torpedoes", "enemy_torpedoes"].reduce((sum, key) => sum + simlogLosses(before[key]), 0);
      if (lossesNow > lossesBefore) kinds.add("loss");
      const contactsNow = buildDisplayModel(entry.state).tracks.length;
      const contactsBefore = buildDisplayModel(previous.state).tracks.length;
      if (contactsNow > contactsBefore) kinds.add("contact");
    }
    for (const kind of SIMLOG_MARK_KINDS) if (kinds.has(kind)) marks.push({seq: entry.seq, t: entry.t, kind, entry});
    previous = entry;
  }
  return marks;
}
// Both sides' debrief: an observer or the solo session (not the server-mode leader,
// who crews one side like everyone else).
export function debriefAllowed() {
  return S.session?.observer === true || (S.session?.host != null && !S.session.host.leader);
}
function renderTimeline(entries) {
  const bar = $("simlog-timeline");
  $("simlog-export").hidden = !debriefAllowed();
  $("simlog-timeline-section").hidden = !debriefAllowed() || entries.length < 2;
  if (!debriefAllowed() || entries.length < 2) { bar.replaceChildren(); return; }
  const first = entries[0].t, last = entries.at(-1).t;
  const span = Math.max(1, last - first);
  const marks = simlogMarks(entries);
  bar.replaceChildren(...entries.map((entry) => {
    const tick = node("button", undefined, "simlog-tick");
    tick.type = "button";
    tick.style.left = `${((entry.t - first) / span) * 100}%`;
    tick.title = `${entry.stamp} T+${Math.floor(entry.t)}s`;
    tick.setAttribute("aria-label", tick.title);
    tick.dataset.seq = String(entry.seq);
    tick.addEventListener("click", () => scrubTo(entry));
    return tick;
  }), ...marks.map((mark) => {
    const item = node("button", undefined, `simlog-mark simlog-mark-${mark.kind}`);
    item.type = "button";
    item.style.left = `${((mark.t - first) / span) * 100}%`;
    item.title = `${t(`simlog_mark_${mark.kind}`)} T+${Math.floor(mark.t)}s`;
    item.setAttribute("aria-label", item.title);
    item.dataset.kind = mark.kind;
    item.addEventListener("click", () => scrubTo(mark.entry));
    return item;
  }));
  $("simlog-timeline-range").textContent = t("simlog_timeline_range", {from: number(first, 0), to: number(last, 0), marks: number(marks.length, 0)});
}
function scrubTo(entry) {
  S.simlogScrubSeq = entry.seq;
  $("simlog-current").replaceChildren(roleHistorySummary(entry, true));
  for (const tick of $("simlog-timeline").querySelectorAll(".simlog-tick"))
    tick.setAttribute("aria-pressed", String(Number(tick.dataset.seq) === entry.seq));
}
const SIMLOG_EXPORT_FORBIDDEN = new Set(["rng", "rngs", "seed", "seeds", "credential", "credentials", "csrf", "cookie", "token", "settings", "password", "api_key"]);
export function exportable(value) {
  if (Array.isArray(value)) return value.map(exportable);
  if (value && typeof value === "object") {
    const out = {};
    for (const [key, item] of Object.entries(value)) if (!SIMLOG_EXPORT_FORBIDDEN.has(key)) out[key] = exportable(item);
    return out;
  }
  return value;
}
export function exportSimlog() {
  if (!debriefAllowed() || !S.simlogEntries?.length) return;
  const state = S.v2State;
  const payload = exportable({protocol: 2, kind: "u-jagd-debrief", role: state?.role ?? null,
    session: state?.session ?? null, epoch: state?.epoch ?? null, entries: S.simlogEntries});
  const blob = new Blob([JSON.stringify(payload)], {type: "application/json"});
  const url = URL.createObjectURL(blob);
  const link = node("a");
  link.href = url;
  link.download = `u-jagd-debrief-${String(state?.session ?? "world").slice(0, 16)}.json`;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export async function loadSimlog() {
  if (!simlogActive()) return;
  const status = $("simlog-status");
  if (S.session?.station === null || S.session?.simlog !== true) {
    S.latestSimlogState = null;
    status.hidden = false;
    status.textContent = t(S.session?.station === null ? "simlog_station_required" : "simlog_grant_required");
    $("simlog-current").replaceChildren(node("p", t("simlog_state_unavailable"), "empty"));
    $("simlog-list").replaceChildren();
    $("simlog-count").textContent = "";
    return;
  }
  const now = performance.now();
  if (now - S.lastSimlogFetch < 2000) return;
  S.lastSimlogFetch = now;
  const expected = S.v2State;
  if (!expected || expected.role !== S.session.station) return;
  try {
    const value = await request("/simlog");
    validateRoleSimlog(value, expected);
    if (!simlogActive() || contextKey(value) !== contextKey(S.v2State)) return;
    renderRoleSimlog(value.entries);
  } catch (error) {
    S.latestSimlogState = null;
    status.hidden = false;
    status.textContent = t(error.status === 403 ? "simlog_grant_required" : "simlog_unavailable");
    $("simlog-current").replaceChildren(node("p", t("simlog_state_unavailable"), "empty"));
    $("simlog-list").replaceChildren();
    $("simlog-count").textContent = "";
  }
}
function validateRoleSimlog(value, expected) {
  if (!exactKeys(value, ["protocol", "session", "epoch", "role", "entries"]) ||
      value.protocol !== 2 || value.session !== expected.session || value.epoch !== expected.epoch ||
      value.role !== expected.role || !boundedArray(value.entries, 64)) throw new Error("simlog_schema");
  let previous = 0;
  for (const entry of value.entries) {
    if (!exactKeys(entry, ["seq", "t", "stamp", "state", "truth"]) ||
        !Number.isSafeInteger(entry.seq) || entry.seq <= previous || entry.seq < 1 ||
        !finite(entry.t) || entry.t < 0 || entry.t > 1e12 ||
        typeof entry.stamp !== "string" || !entry.stamp || entry.stamp.length > 32) throw new Error("simlog_schema");
    validateV2State(entry.state);
    if (entry.state.session !== value.session || entry.state.epoch !== value.epoch || entry.state.role !== value.role)
      throw new Error("simlog_schema");
    validateSimlogTruth(entry.truth);
    previous = entry.seq;
  }
}
function validateSimlogTruth(value) {
  const arrays = ["subs", "surfaces", "animals", "torpedoes", "enemy_torpedoes", "decoys",
    "asms", "essms", "asrocs", "nixies", "buoys", "flights", "raiders"];
  if (!exactKeys(value, ["mission_t", "result", "world", "ship", "weapons", ...arrays,
    "helo", "radars"]) || arrays.some((key) => !boundedArray(value[key], 1024)) ||
    !value.ship || typeof value.ship !== "object" || !finite(value.ship.x) || !finite(value.ship.y))
    throw new Error("simlog_schema");
  const inspect = (item, depth = 0) => {
    if (depth > 4) throw new Error("simlog_schema");
    if (item === null || typeof item === "string" || typeof item === "boolean") return;
    if (typeof item === "number") { if (!finite(item)) throw new Error("simlog_schema"); return; }
    if (Array.isArray(item)) { item.forEach((child) => inspect(child, depth + 1)); return; }
    if (!item || typeof item !== "object") throw new Error("simlog_schema");
    Object.entries(item).forEach(([key, child]) => {
      if (!key || key.length > 64) throw new Error("simlog_schema");
      inspect(child, depth + 1);
    });
  };
  inspect(value);
}
function simlogTruthDisplay(truth) {
  const tracks = [];
  const add = (rows, domain, affiliation, prefix) => rows.forEach((row) => {
    tracks.push({...row, label: `${prefix}${row.id ?? row.seq ?? ""}`, domain, affiliation,
      speed_kn: row.speed ?? null});
  });
  add(truth.subs, "SUBSURFACE", "HOSTILE", "S-");
  add(truth.surfaces, "SURFACE", "UNKNOWN", "V-");
  add(truth.animals, "SUBSURFACE", "NEUTRAL", "B-");
  add(truth.torpedoes, "SUBSURFACE", "FRIEND", "T-");
  add(truth.enemy_torpedoes, "SUBSURFACE", "HOSTILE", "T-");
  add(truth.decoys, "SUBSURFACE", "UNKNOWN", "D-");
  add(truth.asms, "AIR", "HOSTILE", "M-");
  add(truth.essms, "AIR", "FRIEND", "M-");
  add(truth.asrocs, "AIR", "FRIEND", "M-");
  add(truth.nixies, "SUBSURFACE", "FRIEND", "N-");
  add(truth.buoys, "SUBSURFACE", "FRIEND", "B-");
  add(truth.flights, "AIR", "UNKNOWN", "A-");
  add(truth.raiders, "AIR", "HOSTILE", "R-");
  if (truth.helo.airborne) add([truth.helo], "AIR", "FRIEND", "H-");
  return {ownship: truth.ship, tracks};
}
function simlogTruthTable(titleKey, rows, ownship) {
  const wrap = node("div", undefined, "simlog-table-wrap");
  wrap.tabIndex = 0;
  wrap.append(node("h4", t(titleKey)));
  const table = node("table", undefined, "simlog-table");
  const keys = [...new Set(rows.flatMap((row) => Object.keys(row)))];
  if (rows.some((row) => finite(row.x) && finite(row.y))) keys.splice(Math.min(3, keys.length), 0, "distance_own");
  const head = node("tr");
  keys.forEach((key) => head.append(node("th", key === "distance_own" ? t(key) : key)));
  table.append(head);
  for (const value of rows) {
    const row = node("tr");
    keys.forEach((key) => {
      let cell = value[key];
      if (key === "distance_own") cell = finite(value.x) && finite(value.y)
        ? `${number(Math.hypot(value.x - ownship.x, value.y - ownship.y), 1)} NM` : t("unavailable");
      else if (cell && typeof cell === "object") cell = JSON.stringify(cell);
      else if (cell === null || cell === undefined) cell = t("unavailable");
      row.append(node("td", String(cell)));
    });
    table.append(row);
  }
  wrap.append(table);
  return wrap;
}
function simlogTruthSummary(entry) {
  const truth = entry.truth;
  const root = node("div", undefined, "simlog-current-body");
  root.append(simlogMetricBlock("simlog_own", Object.entries(truth.ship).map(([key, value]) =>
    [key, value && typeof value === "object" ? JSON.stringify(value) : String(value)])));
  root.append(simlogMetricBlock("simlog_world", [...Object.entries(truth.world),
    ["mission_t", truth.mission_t], ["result", truth.result ?? "-"]]));
  root.append(simlogMetricBlock("simlog_weapons", Object.entries(truth.weapons)));
  const display = simlogTruthDisplay(truth);
  const mapButton = node("button", t("simlog_map_open"));
  mapButton.type = "button";
  mapButton.addEventListener("click", () => openSimlogMap(display, entry.stamp, entry.seq,
    entry === S.latestSimlogState));
  root.append(mapButton);
  const sections = [["simlog_cat_subs", truth.subs], ["simlog_cat_surfaces", truth.surfaces],
    ["simlog_cat_animals", truth.animals], ["simlog_cat_torps", truth.torpedoes],
    ["simlog_cat_enemy_torps", truth.enemy_torpedoes], ["simlog_cat_decoys", truth.decoys],
    ["simlog_cat_asms", truth.asms], ["simlog_cat_essms", truth.essms],
    ["simlog_cat_asrocs", truth.asrocs], ["simlog_cat_nixies", truth.nixies],
    ["simlog_cat_buoys", truth.buoys], ["simlog_cat_flights", truth.flights],
    ["simlog_cat_raiders", truth.raiders], ["simlog_cat_helo", [truth.helo]]];
  sections.filter(([, rows]) => rows.length).forEach(([title, rows]) =>
    root.append(simlogTruthTable(title, rows, truth.ship)));
  root.append(simlogTruthTable("simlog_world", [truth.radars], truth.ship));
  return root;
}
function roleHistorySummary(entry, expanded = false) {
  const state = entry.state;
  const display = buildDisplayModel(state);
  if (expanded) return simlogTruthSummary(entry);
  const root = node("div", undefined, "simlog-current-body");
  root.append(simlogMetricBlock("mission", [
    ["mission", state.mission.name],
    ["phase", enumText(phases, state.phase)],
    ["remaining", duration(state.mission.remaining_s)],
    ["mission_clock", duration(state.clock.mission)],
  ]));
  root.append(simlogMetricBlock("station_dashboard", [
    ["role_assigned", t(`station_${state.role}`)],
    ["contacts", number(display.tracks.length, 0)],
    ["world_clock", finite(state.clock.world) ? `${String(Math.floor(state.clock.world) % 24).padStart(2, "0")}:${String(Math.floor(state.clock.world * 60) % 60).padStart(2, "0")}` : t("unavailable")],
  ]));
  return root;
}
function renderRoleSimlog(entries) {
  const status = $("simlog-status");
  $("simlog-count").textContent = number(entries.length, 0);
  if (!entries.length) {
    S.latestSimlogState = null;
    S.simlogEntries = [];
    renderTimeline([]);
    status.hidden = false;
    status.textContent = t("simlog_empty");
    $("simlog-current").replaceChildren(node("p", t("simlog_state_unavailable"), "empty"));
    $("simlog-list").replaceChildren();
    return;
  }
  status.hidden = true;
  S.latestSimlogState = entries.at(-1);
  S.simlogEntries = entries;
  renderTimeline(entries);
  const scrubbed = entries.find((entry) => entry.seq === S.simlogScrubSeq);
  $("simlog-current").replaceChildren(roleHistorySummary(scrubbed ?? S.latestSimlogState, true));
  $("simlog-list").replaceChildren(...[...entries].reverse().map((entry) => {
    const item = node("li", undefined, "simlog-entry");
    item.append(node("span", `${entry.stamp}  T+${Math.floor(entry.t)}s`, "simlog-stamp"),
      node("span", t(`station_${entry.state.role}`), "simlog-cat"));
    const details = node("details", undefined, "simlog-snapshot");
    details.append(node("summary", `${entry.state.mission.name} / ${enumText(phases, entry.state.phase)}`),
      roleHistorySummary(entry));
    details.addEventListener("toggle", () => {
      // Full values (own ship, world, every observation) are built only when opened.
      if (details.open) details.lastChild.replaceWith(roleHistorySummary(entry, true));
    });
    item.append(details);
    return item;
  }));
}
