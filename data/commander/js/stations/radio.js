import { S } from "../state/store.js";
import { $ } from "../core/base.js";
import { finite, number, t, unit } from "../core/format.js";
import { palette } from "../core/palette.js";
import { actionButton, node, position, stationRows } from "../views/dom.js";
import { selectTrack } from "../views/tracks.js";
import { drawEmpty, visualContext } from "../views/visual-common.js";

// The radio room: HF/DF receiver channels, the bearing scope and the message
// teletype. Everything shown is the operator's own published observation.
const S_METER_SEGMENTS = 10;

export function renderRadioStation(payload) {
  renderChannels(payload);
  renderTeletype(payload);
  renderTasks(payload);
  $("radio-df-state").textContent = t(payload.station_down ? "radio_df_down" : "radio_df_live");
  $("radio-df-state").dataset.state = payload.station_down ? "down" : "live";
  stationRows($("radio-fixes"), payload.logged_fixes, (row) => [["reference", row.ref], ["position", position(row)],
    ["uncertainty", unit(row.uncertainty_nm, "NM")], ["age", unit(row.age_s, "s", 0)],
    ["covariance", row.covariance_nm2 ? row.covariance_nm2.map((value) => number(value, 2)).join(" / ") : t("unavailable")]]);
  stationRows($("radio-bearings"), payload.logged_bearings, (row) => [["reference", row.ref],
    ["bearing", unit(row.bearing, "°", 0)], ["observer_position", `${unit(row.observer_x, "NM")} / ${unit(row.observer_y, "NM")}`],
    ["age", unit(row.age_s, "s", 0)]]);
}

function frequencyText(row) {
  return finite(row.frequency_khz) ? number(row.frequency_khz, 1) : "----.-";
}

function sMeter(quality) {
  const meter = node("span", undefined, "radio-smeter");
  meter.setAttribute("role", "meter");
  meter.setAttribute("aria-valuemin", "0");
  meter.setAttribute("aria-valuemax", "1");
  meter.setAttribute("aria-valuenow", String(finite(quality) ? quality : 0));
  meter.setAttribute("aria-label", t("radio_signal_strength"));
  const lit = Math.round((finite(quality) ? Math.max(0, Math.min(1, quality)) : 0) * S_METER_SEGMENTS);
  for (let index = 0; index < S_METER_SEGMENTS; index++)
    meter.append(node("i", undefined, index < lit ? (index >= S_METER_SEGMENTS - 2 ? "on hot" : "on") : ""));
  return meter;
}

function channel(row) {
  const item = node("article", undefined, "radio-channel");
  item.setAttribute("role", "listitem");
  item.dataset.rowKey = row.ref;
  item.classList.toggle("selected", S.selected === row.ref);
  item.classList.toggle("stale", row.age_s > 60);
  const tune = node("button", undefined, "radio-tune");
  tune.type = "button";
  tune.setAttribute("aria-pressed", String(S.selected === row.ref));
  tune.addEventListener("click", () => selectTrack(row.ref));
  const dial = node("span", undefined, "radio-dial");
  dial.append(node("span", frequencyText(row), "radio-frequency"), node("span", "kHz", "radio-unit-label"));
  const mode = node("span", row.propagation ? t(`radio_mode_${row.propagation.toLowerCase()}`) : t("radio_mode_unknown"),
    `radio-mode ${row.propagation ? row.propagation.toLowerCase() : "unknown"}`);
  const meta = node("span", undefined, "radio-meta");
  meta.append(node("strong", row.label, "radio-label"),
    node("span", `${unit(row.bearing, "°", 0)} ±${number(row.bearing_uncertainty_deg, 0)}°`, "radio-bearing"),
    node("span", unit(row.age_s, "s", 0), "radio-age"));
  tune.append(dial, mode, sMeter(row.quality), meta);
  item.append(tune, actionButton("radio_capture", "radio_capture_hfdf", {ref: row.ref}, row.can_capture));
  return item;
}

function renderChannels(payload) {
  const list = $("radio-observations");
  const rows = [...payload.observations].sort((a, b) => (a.age_s ?? 1e9) - (b.age_s ?? 1e9));
  $("radio-channel-count").textContent = t("radio_channel_count", {count: rows.length});
  list.replaceChildren(...rows.map(channel));
  if (payload.station_down) list.prepend(node("p", t("station_down_state"), "station-alert"));
  if (!rows.length) list.append(node("p", t("radio_no_signal"), "empty radio-idle"));
}

// HQ tasks: the order as HQ gave it, its clock and, for an open offer, the
// radio room's answer.  Positions are HQ's reports, never the truth.
const CLOSED_TASK_STATES = "done failed declined".split(" ");

function taskFacts(row) {
  const facts = [t("radio_task_position", {bearing: number(row.bearing, 0), range: number(row.range_nm, 1),
    radius: number(row.radius_nm, 1)})];
  if (finite(row.course)) facts.push(t("radio_task_motion", {course: number(row.course, 0), speed: number(row.speed_kn, 0)}));
  if (finite(row.respond_s)) facts.push(t("radio_task_respond", {seconds: number(row.respond_s, 0)}));
  else if (finite(row.remaining_s)) facts.push(t("radio_task_remaining", {minutes: number(row.remaining_s / 60, 0)}));
  if (row.type === "sar" && !CLOSED_TASK_STATES.includes(row.state))
    facts.push(t(row.sighted ? "radio_task_sighted" : "radio_task_not_sighted"));
  if (row.state === "active" && row.type !== "identify")
    facts.push(t("radio_task_progress", {progress: number(row.progress * 100, 0)}));
  if (row.verdict) facts.push(t(`radio_task_verdict_${row.verdict}`));
  if (CLOSED_TASK_STATES.includes(row.state))
    facts.push(t("radio_task_points", {points: `${row.points > 0 ? "+" : ""}${row.points}`}));
  return facts.join(" · ");
}

function taskCard(row) {
  const card = node("article", undefined, "radio-task");
  card.setAttribute("role", "listitem");
  card.dataset.state = row.state;
  card.dataset.rowKey = String(row.id);
  const head = node("div", undefined, "radio-task-head");
  head.append(node("strong", `${row.type.toUpperCase()} ${row.id} · ${t(`radio_task_kind_${row.type}`)}`),
    node("span", t(`radio_task_state_${row.state}`), "radio-task-state"));
  card.append(head, node("p", t(`radio_task_brief_${row.type}`, {name: row.name ?? "-", persons: row.persons}), "radio-task-brief"),
    node("p", taskFacts(row), "radio-task-facts"));
  if (row.state === "offered") {
    const actions = node("div", undefined, "radio-task-actions");
    actions.append(actionButton("radio_task_accept", "radio_task_accept", {task: row.id}, row.can_answer),
      actionButton("radio_task_decline", "radio_task_decline", {task: row.id}, row.can_answer));
    card.append(actions);
  }
  return card;
}

function renderTasks(payload) {
  const list = $("radio-tasks");
  const open = payload.tasks.filter((row) => !CLOSED_TASK_STATES.includes(row.state)).length;
  $("radio-task-count").textContent = t("radio_task_count", {open});
  list.replaceChildren(...payload.tasks.map(taskCard));
  if (!payload.tasks.length) list.append(node("p", t("radio_task_none"), "empty radio-idle"));
  const request = node("div", undefined, "radio-task-actions");
  request.append(actionButton("radio_request_ras", "radio_request_ras", {}, payload.can_request_ras));
  list.append(request);
}

function renderTeletype(payload) {
  const list = $("radio-messages");
  const follow = list.scrollHeight - list.scrollTop - list.clientHeight < 24;
  // Oldest first, newest at the bottom like paper leaving the printer.
  list.replaceChildren(...payload.messages.map((row, index) => {
    const line = node("li", undefined, index === payload.messages.length - 1 ? "latest" : "");
    line.append(node("time", row.stamp, "radio-stamp"), node("span", row.text, "radio-text"));
    return line;
  }));
  if (!payload.messages.length) list.append(node("li", t("radio_no_traffic"), "radio-idle"));
  if (follow) list.scrollTop = list.scrollHeight;
}

// Bearing scope: north up, one strobe fan per intercept (width = bearing
// error, brightness = quality and freshness), logged bearings as dashed
// history lines, own heading as a tick on the rim.
export function drawRadioVisual() {
  const plot = visualContext("radio-df-scope"), payload = S.v2State?.radio;
  if (!plot || !payload) return;
  const {context: g, width, height} = plot, colors = palette();
  const radius = Math.max(10, Math.min(width, height) / 2 - 28), cx = width / 2, cy = height / 2;
  const rad = (degrees) => (degrees - 90) * Math.PI / 180;
  const at = (degrees, r) => [cx + Math.cos(rad(degrees)) * r, cy + Math.sin(rad(degrees)) * r];
  g.strokeStyle = colors.line; g.lineWidth = 1;
  for (const ring of [.25, .5, .75, 1]) { g.beginPath(); g.arc(cx, cy, radius * ring, 0, Math.PI * 2); g.stroke(); }
  g.fillStyle = colors.muted; g.textAlign = "center"; g.textBaseline = "middle";
  for (let degrees = 0; degrees < 360; degrees += 10) {
    const major = degrees % 30 === 0;
    const [x1, y1] = at(degrees, radius), [x2, y2] = at(degrees, radius - (major ? 10 : 5));
    g.beginPath(); g.moveTo(x1, y1); g.lineTo(x2, y2); g.stroke();
    if (major) { const [tx, ty] = at(degrees, radius + 14); g.fillText(degrees === 0 ? "N" : String(degrees).padStart(3, "0"), tx, ty); }
  }
  if (!payload.observations.length && !payload.logged_bearings.length) {
    drawEmpty(plot, "radio_no_signal");
    $("radio-df-scope-text").textContent = t("radio_no_signal");
    return;
  }
  g.setLineDash([4, 5]); g.strokeStyle = colors.muted; g.globalAlpha = .45;
  for (const row of payload.logged_bearings) {
    if (!finite(row.bearing)) continue;
    const [x, y] = at(row.bearing, radius);
    g.beginPath(); g.moveTo(cx, cy); g.lineTo(x, y); g.stroke();
  }
  g.setLineDash([]); g.globalAlpha = 1;
  for (const row of payload.observations) {
    if (!finite(row.bearing)) continue;
    const selected = row.ref === S.selected;
    const fresh = Math.max(.25, 1 - (finite(row.age_s) ? row.age_s : 300) / 300);
    const quality = finite(row.quality) ? Math.max(.15, row.quality) : .5;
    const spread = Math.max(1, finite(row.bearing_uncertainty_deg) ? row.bearing_uncertainty_deg : 3);
    g.globalAlpha = .12 + .3 * quality * fresh;
    g.fillStyle = selected ? colors.accent : colors.amber;
    g.beginPath(); g.moveTo(cx, cy); g.arc(cx, cy, radius, rad(row.bearing - spread), rad(row.bearing + spread)); g.closePath(); g.fill();
    g.globalAlpha = .4 + .6 * fresh;
    g.strokeStyle = selected ? colors.accent : colors.amber; g.lineWidth = selected ? 2.5 : 1.5;
    const [x, y] = at(row.bearing, radius * (.55 + .45 * quality));
    g.beginPath(); g.moveTo(cx, cy); g.lineTo(x, y); g.stroke();
    g.globalAlpha = 1; g.fillStyle = selected ? colors.accent : colors.text;
    const [lx, ly] = at(row.bearing, radius * .6 * (.55 + .45 * quality) + 18);
    g.fillText(`${row.label}${finite(row.frequency_khz) ? ` ${number(row.frequency_khz, 0)}` : ""}`, lx, ly);
  }
  g.lineWidth = 1.5;
  const course = payload.navigation?.course;
  if (finite(course)) {
    g.strokeStyle = colors.blue; g.fillStyle = colors.blue;
    const [x1, y1] = at(course, radius + 2), [x2, y2] = at(course, radius - 16);
    g.beginPath(); g.moveTo(x1, y1); g.lineTo(x2, y2); g.stroke();
    g.beginPath(); g.arc(cx, cy, 3, 0, Math.PI * 2); g.fill();
  }
  $("radio-df-scope-text").replaceChildren(...payload.observations.map((row) =>
    node("li", `${row.label}: ${unit(row.bearing, "°", 0)} ±${number(row.bearing_uncertainty_deg, 0)}°, ${frequencyText(row)} kHz`)));
}
