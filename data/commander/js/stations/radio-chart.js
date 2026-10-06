import { S } from "../state/store.js";
import { $ } from "../core/base.js";
import { finite, number, t } from "../core/format.js";
import { colors, palette } from "../core/palette.js";
import { drawNatoSymbol } from "../plot/symbols.js";
import { node } from "../views/dom.js";
import { drawEmpty, visualContext } from "../views/visual-common.js";

// The HF/DF cross-fix chart (as the uConsole's radio page 1,
// src/ui/stations/radio_chart.py): only what the radio room published -
// logged bearings from where they were taken, the live intercepts from the
// own ship, crossings of two logged bearings of one signal and the
// computed fixes with their error ellipse. Own ship and the known coast are
// the only other things on it; it never shows an emitter the room did not fix.
export const CHART_WINDOW_S = 300;
const CHART_MIN_HALF_NM = 20, CHART_MAX_HALF_NM = 160, CROSS_BASE_MIN_NM = 1;
const LIVE_FADE_S = 60;

function intersection(first, second) {
  const a = first.bearing * Math.PI / 180, b = second.bearing * Math.PI / 180;
  const [dx1, dy1, dx2, dy2] = [Math.sin(a), -Math.cos(a), Math.sin(b), -Math.cos(b)];
  const det = dx1 * -dy2 - dy1 * -dx2;
  if (Math.abs(det) < 1e-6) return null;
  const ox = second.observer_x - first.observer_x, oy = second.observer_y - first.observer_y;
  const along = (ox * -dy2 - oy * -dx2) / det, other = (dx1 * oy - dy1 * ox) / det;
  // Both lines run forward from their observers.
  if (along <= 0 || other <= 0) return null;
  return [first.observer_x + along * dx1, first.observer_y + along * dy1];
}

// The chart's items from the radio projection (pure, testable).
export function chartItems(payload) {
  const ship = payload.navigation;
  const logged = payload.logged_bearings.filter((row) => [row.bearing, row.observer_x, row.observer_y, row.age_s].every(finite) &&
    row.age_s <= CHART_WINDOW_S);
  const live = payload.observations.filter((row) => finite(row.bearing) && finite(ship?.x) && finite(ship?.y)).slice(0, 12)
    .map((row) => ({ref: row.ref, label: row.label, bearing: row.bearing, observer_x: ship.x, observer_y: ship.y,
      error: finite(row.bearing_uncertainty_deg) ? row.bearing_uncertainty_deg : 3, age_s: finite(row.age_s) ? row.age_s : 0}));
  const crossings = [];
  logged.forEach((first, index) => logged.slice(index + 1).forEach((second) => {
    if (first.ref !== second.ref || Math.hypot(first.observer_x - second.observer_x,
      first.observer_y - second.observer_y) < CROSS_BASE_MIN_NM) return;
    const point = intersection(first, second);
    if (point) crossings.push({ref: first.ref, x: point[0], y: point[1], age_s: Math.max(first.age_s, second.age_s)});
  }));
  const fixes = payload.logged_fixes.filter((fix) => [fix.x, fix.y, fix.uncertainty_nm, fix.age_s].every(finite) &&
    fix.age_s <= CHART_WINDOW_S);
  return {ship, logged, live, crossings, fixes};
}

// North-up camera that holds the ship, every observer position and fix.
export function chartView(items, width, height) {
  const xs = [items.ship.x], ys = [items.ship.y];
  for (const row of [...items.logged, ...items.live]) { xs.push(row.observer_x); ys.push(row.observer_y); }
  for (const row of items.crossings) { xs.push(row.x); ys.push(row.y); }
  for (const fix of items.fixes) {
    xs.push(fix.x - 2 * fix.uncertainty_nm, fix.x + 2 * fix.uncertainty_nm);
    ys.push(fix.y - 2 * fix.uncertainty_nm, fix.y + 2 * fix.uncertainty_nm);
  }
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2, cy = (Math.min(...ys) + Math.max(...ys)) / 2;
  const half = Math.max(CHART_MIN_HALF_NM, Math.min(CHART_MAX_HALF_NM,
    .6 * Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys))));
  const scale = Math.min(width, height) / (2 * half);
  return {scale, half, cx, cy, point: (x, y) => [width / 2 + (x - cx) * scale, height / 2 + (y - cy) * scale]};
}

// The error ellipse of a fix: its covariance (NM²) when published, else a circle.
export function ellipseAxes(fix) {
  const covariance = fix.covariance_nm2;
  if (!Array.isArray(covariance) || covariance.length !== 3 || !covariance.every(finite))
    return {major: fix.uncertainty_nm, minor: fix.uncertainty_nm, angle: 0};
  const [xx, xy, yy] = covariance, spread = Math.hypot(xx - yy, 2 * xy);
  return {major: Math.sqrt(Math.max(0, (xx + yy + spread) / 2)), minor: Math.sqrt(Math.max(0, (xx + yy - spread) / 2)),
    angle: .5 * Math.atan2(2 * xy, xx - yy)};
}

const fade = (age, window) => Math.max(.25, 1 - .75 * Math.max(0, Math.min(1, age / window)));

export function drawRadioChart() {
  const plot = visualContext("radio-hfdf-chart"), payload = S.v2State?.radio;
  if (!plot || !payload) return;
  const items = chartItems(payload);
  const text = $("radio-hfdf-chart-text");
  if (!finite(items.ship?.x) || !finite(items.ship?.y)) { drawEmpty(plot, "radio_chart_empty"); text.textContent = t("radio_chart_empty"); return; }
  const {context: g, width, height} = plot, tone = palette();
  const view = chartView(items, width, height), point = view.point;
  const reach = 2 * Math.max(width, height) / view.scale;
  const rayEnd = (row, bearing = row.bearing) => {
    const rad = bearing * Math.PI / 180;
    return point(row.observer_x + reach * Math.sin(rad), row.observer_y - reach * Math.cos(rad));
  };
  // Plotting sheet: grid and the known coast.
  const step = [5, 10, 20, 50].find((value) => value * view.scale >= 60) ?? 100;
  g.strokeStyle = tone.grid; g.lineWidth = 1;
  const left = view.cx - width / 2 / view.scale, right = view.cx + width / 2 / view.scale;
  const top = view.cy - height / 2 / view.scale, bottom = view.cy + height / 2 / view.scale;
  for (let value = Math.ceil(left / step) * step; value <= right; value += step) {
    const [x] = point(value, 0);
    g.beginPath(); g.moveTo(x, 0); g.lineTo(x, height); g.stroke();
  }
  for (let value = Math.ceil(top / step) * step; value <= bottom; value += step) {
    const [, y] = point(0, value);
    g.beginPath(); g.moveTo(0, y); g.lineTo(width, y); g.stroke();
  }
  g.strokeStyle = tone.landEdge; g.fillStyle = tone.land;
  for (const land of S.chart?.landmasses ?? []) {
    g.beginPath(); land.points.forEach(([x, y], index) => { const p = point(x, y); index ? g.lineTo(...p) : g.moveTo(...p); });
    g.closePath(); g.fill(); g.stroke();
  }
  // Live intercepts from the own ship: an error wedge and a thin line.
  for (const row of items.live) {
    const selected = row.ref === S.selected, [ox, oy] = point(row.observer_x, row.observer_y);
    g.globalAlpha = .18 * fade(row.age_s, LIVE_FADE_S);
    g.fillStyle = selected ? tone.accent : tone.amber;
    const [ax, ay] = rayEnd(row, row.bearing - row.error), [bx, by] = rayEnd(row, row.bearing + row.error);
    g.beginPath(); g.moveTo(ox, oy); g.lineTo(ax, ay); g.lineTo(bx, by); g.closePath(); g.fill();
    g.globalAlpha = fade(row.age_s, LIVE_FADE_S);
    g.strokeStyle = selected ? tone.accent : tone.amber; g.lineWidth = selected ? 2 : 1;
    g.beginPath(); g.moveTo(ox, oy); g.lineTo(...rayEnd(row)); g.stroke();
  }
  // Logged bearings, each from where it was taken.
  g.lineWidth = 2;
  for (const row of items.logged) {
    g.globalAlpha = fade(row.age_s, CHART_WINDOW_S); g.strokeStyle = tone.live;
    const [ox, oy] = point(row.observer_x, row.observer_y);
    g.beginPath(); g.moveTo(ox, oy); g.lineTo(...rayEnd(row)); g.stroke();
    g.beginPath(); g.arc(ox, oy, 4, 0, Math.PI * 2); g.stroke();
  }
  g.lineWidth = 1.5;
  for (const row of items.crossings) {
    g.globalAlpha = fade(row.age_s, CHART_WINDOW_S); g.strokeStyle = tone.amber;
    const [px, py] = point(row.x, row.y);
    g.beginPath(); g.moveTo(px, py - 5); g.lineTo(px + 5, py); g.lineTo(px, py + 5); g.lineTo(px - 5, py); g.closePath(); g.stroke();
  }
  // Fixes with their error ellipse (2 sigma would double it; the uConsole draws 1 sigma).
  g.font = "12px sans-serif"; g.textAlign = "left"; g.textBaseline = "bottom";
  for (const fix of items.fixes) {
    g.globalAlpha = fade(fix.age_s, CHART_WINDOW_S); g.strokeStyle = g.fillStyle = tone.green;
    const [px, py] = point(fix.x, fix.y), axes = ellipseAxes(fix);
    g.lineWidth = 2; g.beginPath();
    g.ellipse(px, py, Math.max(3, axes.major * view.scale), Math.max(2, axes.minor * view.scale), axes.angle, 0, Math.PI * 2);
    g.stroke();
    g.beginPath(); g.arc(px, py, 3, 0, Math.PI * 2); g.fill();
    g.fillText(t("radio_chart_fix_label", {label: fix.ref, sigma: number(fix.uncertainty_nm, 1)}), px + 8, py - 6);
  }
  g.globalAlpha = 1;
  // Own ship last, on top: NATO friendly surface symbol and heading.
  const [sx, sy] = point(items.ship.x, items.ship.y);
  const heading = (items.ship.course ?? 0) * Math.PI / 180, own = colors.FRIEND || tone.blue;
  g.strokeStyle = own; g.lineWidth = 2;
  g.beginPath(); g.moveTo(sx, sy); g.lineTo(sx + 18 * Math.sin(heading), sy - 18 * Math.cos(heading)); g.stroke();
  drawNatoSymbol(g, sx, sy, "FRIEND", "SURFACE", own, 8);
  g.fillStyle = tone.muted; g.textAlign = "right"; g.textBaseline = "top";
  g.fillText(t("radio_chart_scale", {range: number(2 * view.half, 0)}), width - 6, 4);
  if (!items.logged.length && !items.live.length && !items.fixes.length) {
    g.textAlign = "left"; g.fillText(t("radio_chart_empty"), 8, 4);
  }
  text.replaceChildren(...(items.fixes.length ? items.fixes.map((fix) => node("li",
    t("radio_chart_fix_label", {label: fix.ref, sigma: number(fix.uncertainty_nm, 1)}))) : [node("li", t("radio_chart_empty"))]));
}
