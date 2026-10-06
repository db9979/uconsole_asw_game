// OPZ chart display settings and their drawing (the browser twin of
// src/core/opz_display.py and src/ui/stations/opz_display_view.py): track
// trails, vector length, labels, the bearing scale, range rings, the
// selected track's CPA and the chart layers. Display only and per browser
// tab (kept in memory, never sent to the host); the buttons are fixed in
// index.html and only their text and pressed state change on a state push.
import { $ } from "../core/base.js";
import { S } from "../state/store.js";
import { finite, hasPosition, t } from "../core/format.js";
import { palette } from "../core/palette.js";
import { fixedText, placeText } from "./label-layout.js";

export const OPZ_DISPLAY_OPTIONS = [
  ["trails", ["off", "3", "6", "12"], "6"],
  ["vectors", ["3", "6", "12", "30"], "3"],
  ["labels", ["full", "brief", "off"], "full"],
  ["compass", ["on", "off"], "on"],
  ["rings", ["on", "off"], "on"],
  ["cpa", ["on", "off"], "on"],
  ["bearings", ["on", "off"], "on"],
  ["uncertainty", ["on", "off"], "on"],
  ["chart", ["on", "off"], "on"],
  ["afterglow", ["on", "off"], "on"],
];
const defaults = () => Object.fromEntries(OPZ_DISPLAY_OPTIONS.map(([key, , value]) => [key, value]));
let settings = defaults();
const CPA_HORIZON_MIN = 120;
const CPA_MIN_RELATIVE_KN = 0.5;
const CPA_DANGER_NM = 2;
// Rings closer than this (px) label only every second ring.
const RANGE_LABEL_H = 13;

export const opzDisplay = () => settings;
export const opzLayer = (key) => settings[key] !== "off";
export const opzVectorMinutes = () => Number(settings.vectors);
export const opzTrailMinutes = () => settings.trails === "off" ? 0 : Number(settings.trails);

export function stepOpzDisplay(key, delta = 1) {
  const option = OPZ_DISPLAY_OPTIONS.find(([name]) => name === key);
  if (!option) return;
  const choices = option[1], index = choices.indexOf(settings[key]);
  settings = {...settings, [key]: choices[(index + delta + choices.length) % choices.length]};
  syncOpzDisplayBar();
}
export function resetOpzDisplay() { settings = defaults(); syncOpzDisplayBar(); }

function valueText(key, value) {
  if ((key === "trails" || key === "vectors") && value !== "off") return t("opz_display_minutes", {minutes: value});
  return t(`opz_display_value_${value}`);
}
// The bar shows only for the OPZ; each button names its layer and value.
export function syncOpzDisplayBar(role = null) {
  const bar = $("opz-display-bar");
  if (!bar) return;
  if (role !== null) bar.hidden = role !== "opz";
  // The two radar switches show the host's radar state (opz_set_radar).
  const radar = S.v2State?.role === "opz" ? S.v2State.opz.radar : null;
  for (const button of bar.querySelectorAll("button[data-opz-radar]")) {
    const domain = button.dataset.opzRadar, on = Boolean(radar?.[domain]);
    const text = `${t(`opz_radar_switch_${domain}`)} ${t(on ? "opz_display_value_on" : "opz_display_value_off")}`;
    if (button.textContent !== text) button.textContent = text;
    if (button.getAttribute("aria-pressed") !== String(on)) button.setAttribute("aria-pressed", String(on));
    button.disabled = !radar?.live;
  }
  for (const button of bar.querySelectorAll("button[data-opz-display]")) {
    const key = button.dataset.opzDisplay;
    if (key === "reset") continue;
    const text = `${t(`opz_display_${key}`)} ${valueText(key, settings[key])}`;
    if (button.textContent !== text) button.textContent = text;
    const pressed = String(settings[key] !== "off");
    if (button.getAttribute("aria-pressed") !== pressed) button.setAttribute("aria-pressed", pressed);
  }
}

// Closest point of approach from the track's reported motion (nautical
// frame: x east, y south); minutes ahead, or null when the two do not close.
export function opzCpa(own, row) {
  if (![own?.x, own?.y, own?.course, own?.speed, row?.x, row?.y, row?.course, row?.speed_kn].every(finite)) return null;
  const rad = Math.PI / 180;
  const ovx = own.speed * Math.sin(own.course * rad) / 60, ovy = -own.speed * Math.cos(own.course * rad) / 60;
  const vx = row.speed_kn * Math.sin(row.course * rad) / 60, vy = -row.speed_kn * Math.cos(row.course * rad) / 60;
  const rx = row.x - own.x, ry = row.y - own.y, dvx = vx - ovx, dvy = vy - ovy;
  const rel2 = dvx * dvx + dvy * dvy;
  if (rel2 * 3600 < CPA_MIN_RELATIVE_KN ** 2) return null;
  const minutes = -(rx * dvx + ry * dvy) / rel2;
  if (minutes <= 0 || minutes > CPA_HORIZON_MIN) return null;
  return {distance: Math.hypot(rx + dvx * minutes, ry + dvy * minutes), minutes,
    own: [own.x + ovx * minutes, own.y + ovy * minutes], track: [row.x + vx * minutes, row.y + vy * minutes]};
}

export function opzLabel(text) {
  if (settings.labels === "off") return null;
  const value = String(text);
  return settings.labels === "brief" && value.length > 6 ? value.slice(0, 6) : value;
}

// Range rings at quarters of the radar range, labelled at the top, and the
// bearing scale on the outer ring with the own course mark.
export function drawOpzRings(context, labels, ox, oy, rangeNm, scale, course, width, height) {
  const radius = rangeNm * scale;
  if (!(radius > 8)) return;
  context.save();
  context.lineWidth = 1;
  if (opzLayer("rings")) {
    context.strokeStyle = palette().lineStrong;
    for (let ring = 1; ring <= 4; ring++) {
      context.beginPath(); context.arc(ox, oy, radius * ring / 4, 0, Math.PI * 2); context.stroke();
    }
  }
  if (opzLayer("compass") && radius >= 24) {
    context.font = "11px sans-serif";
    for (let bearing = 0; bearing < 360; bearing += 10) {
      const rad = bearing * Math.PI / 180, ux = Math.sin(rad), uy = -Math.cos(rad);
      const major = bearing % 30 === 0, inner = radius - (major ? 9 : 5);
      const x = ox + ux * radius, y = oy + uy * radius;
      if (x < 0 || y < 0 || x > width || y > height) continue;
      context.strokeStyle = major ? palette().muted : palette().lineStrong;
      context.beginPath(); context.moveTo(ox + ux * inner, oy + uy * inner); context.lineTo(x, y); context.stroke();
      if (major && radius >= 90) {
        context.fillStyle = palette().muted;
        const text = String(bearing).padStart(3, "0"), depth = 22;
        const w = context.measureText(text).width;
        const tx = ox + ux * (radius - depth) - w / 2, ty = oy + uy * (radius - depth) + 4;
        // Scale numbers stay at their bearing; one pushed aside would read
        // as a different bearing.
        if (tx >= 0 && ty >= 11 && tx + w <= width && ty <= height) fixedText(context, labels, text, tx, ty);
      }
    }
    if (finite(course)) {
      const rad = course * Math.PI / 180, ux = Math.sin(rad), uy = -Math.cos(rad), px = -uy * 5, py = ux * 5;
      const bx = ox + ux * (radius + 1), by = oy + uy * (radius + 1);
      context.fillStyle = palette().text;
      context.beginPath(); context.moveTo(ox + ux * (radius - 12), oy + uy * (radius - 12));
      context.lineTo(bx + px, by + py); context.lineTo(bx - px, by - py); context.closePath(); context.fill();
    }
  }
  if (opzLayer("rings")) {
    // Distances at the top of the rings at fixed places: only every second
    // (or only the outer) ring when they are close, the outer one right of
    // the scale's "000", and one whose place a scale number holds is left out.
    context.fillStyle = palette().muted;
    context.font = "11px sans-serif";
    let stride = 1;
    while (stride < 4 && radius * stride / 4 < RANGE_LABEL_H) stride *= 2;
    const numbers = opzLayer("compass") && radius >= 90;
    for (let ring = stride; ring <= 4; ring += stride) {
      const y = oy - radius * ring / 4;
      const x = ring === 4 && numbers ? ox + context.measureText("000").width / 2 + 4 : ox + 4;
      if (y > 12 && y < height - 4) fixedText(context, labels, `${+(rangeNm * ring / 4).toFixed(1)} NM`, x, y + 12, true);
    }
  }
  context.restore();
}

// Earlier published positions of each report, oldest faintest.
export function drawOpzTrails(context, trails, colorOf, point, labels = null) {
  const minutes = opzTrailMinutes();
  if (!minutes || !Array.isArray(trails)) return;
  context.save();
  for (const trail of trails) {
    const rows = trail.points.filter((row) => row[2] <= minutes * 60 + 1e-6);
    if (!rows.length) continue;
    context.strokeStyle = context.fillStyle = colorOf(trail.ref);
    rows.forEach(([x, y], index) => {
      const [px, py] = point(x, y), weight = .2 + .6 * (index + 1) / rows.length;
      context.globalAlpha = weight * .45;
      if (index) {
        const [qx, qy] = point(rows[index - 1][0], rows[index - 1][1]);
        context.beginPath(); context.moveTo(qx, qy); context.lineTo(px, py); context.stroke();
        if (labels) labels.reserveLine(qx, qy, px, py);
      }
      context.globalAlpha = weight;
      context.beginPath(); context.arc(px, py, 2, 0, Math.PI * 2); context.fill();
    });
  }
  context.restore();
}

export function drawOpzCpa(context, labels, own, row, point) {
  if (!opzLayer("cpa") || !hasPosition(row)) return;
  const cpa = opzCpa(own, row);
  if (!cpa) return;
  const color = cpa.distance < CPA_DANGER_NM ? palette().red : palette().amber;
  const [ox, oy] = point(own.x, own.y), [tx, ty] = point(row.x, row.y);
  const [ax, ay] = point(...cpa.own), [bx, by] = point(...cpa.track);
  context.save();
  context.strokeStyle = color; context.lineWidth = 1;
  context.globalAlpha = .6; context.setLineDash([5, 5]);
  context.beginPath(); context.moveTo(ox, oy); context.lineTo(ax, ay); context.moveTo(tx, ty); context.lineTo(bx, by); context.stroke();
  context.globalAlpha = 1; context.setLineDash([]);
  context.beginPath(); context.moveTo(ax, ay); context.lineTo(bx, by); context.stroke();
  for (const [x, y] of [[ax, ay], [bx, by]]) { context.beginPath(); context.arc(x, y, 3, 0, Math.PI * 2); context.stroke(); }
  context.fillStyle = color; context.font = "12px sans-serif";
  placeText(context, labels, t("opz_cpa_label", {distance: cpa.distance.toFixed(1), minutes: cpa.minutes.toFixed(0)}),
    (ax + bx) / 2 + 8, (ay + by) / 2 - 4);
  context.restore();
}

export function wireOpzDisplayBar(sendRadar) {
  const bar = $("opz-display-bar");
  if (!bar) return;
  bar.addEventListener("click", (event) => {
    const radar = event.target.closest("button[data-opz-radar]");
    if (radar) { sendRadar(radar.dataset.opzRadar, radar.getAttribute("aria-pressed") !== "true"); return; }
    const button = event.target.closest("button[data-opz-display]");
    if (!button) return;
    if (button.dataset.opzDisplay === "reset") resetOpzDisplay();
    else stepOpzDisplay(button.dataset.opzDisplay, event.shiftKey ? -1 : 1);
    bar.dispatchEvent(new CustomEvent("opz-display-change", {bubbles: true}));
  });
}
