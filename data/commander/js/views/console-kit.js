import { $ } from "../core/base.js";
import { finite, number, t } from "../core/format.js";
import { palette } from "../core/palette.js";
import { node } from "./dom.js";
import { visualContext } from "./visual-common.js";

// Shared parts of the engine-room control consoles (frigate and submarine):
// an annunciator panel of status lamps with its master lamp and a row of
// round gauges on one canvas. Lamp levels: off, on, caution, alarm.

export const pct = (value, capacity) => !finite(value) || !capacity ? null : Math.max(0, Math.min(100, value / capacity * 100));
export const signed = (value, digits) => `${value > 0 ? "+" : ""}${number(value, digits)}`;

// Keyed children: rebuilt only when the set of lamps changes (another boat or ship).
export function keyed(box, keys, make) {
  const signature = keys.join(" ");
  if (box.dataset.keys !== signature) {
    box.replaceChildren(...keys.map(make));
    box.dataset.keys = signature;
  }
  return [...box.children];
}

// Lamps are [key, label, level, value]; the master lamp counts alarms and cautions.
export function renderLampPanel(box, master, rows) {
  renderLamps(box, rows);
  const alarms = rows.filter((row) => row[2] === "alarm").length, cautions = rows.filter((row) => row[2] === "caution").length;
  master.dataset.state = alarms ? "alarm" : cautions ? "caution" : "live";
  master.textContent = alarms ? t("uboot_engine_master_alarm", {count: alarms})
    : cautions ? t("uboot_engine_master_caution", {count: cautions}) : t("uboot_engine_master_clear");
}

// The lamps alone, without a master lamp (the sonar's listening console).
export function renderLamps(box, rows) {
  const cells = keyed(box, rows.map((row) => row[0]), (key) => {
    const cell = node("div", undefined, "console-lamp");
    cell.setAttribute("role", "listitem");
    cell.dataset.key = key;
    const led = node("span", undefined, "console-led");
    led.setAttribute("aria-hidden", "true");
    cell.append(led, node("span", undefined, "console-lamp-label"), node("span", undefined, "console-lamp-value"));
    return cell;
  });
  rows.forEach(([, label, level, value], index) => {
    const cell = cells[index];
    cell.dataset.level = level;
    cell.children[1].textContent = label;
    cell.children[2].textContent = value;
  });
}

// Round gauge with its scale, coloured zones, needle and ordered value.
export function dial(g, x, y, radius, room, spec, colors) {
  const {value, min, max, order, zones = [], label, text, sub} = spec;
  const start = Math.PI * .75, sweep = Math.PI * 1.5;
  const angle = (v) => start + sweep * Math.max(0, Math.min(1, (v - min) / Math.max(1e-6, max - min)));
  g.lineWidth = Math.max(3, radius * .09);
  g.strokeStyle = colors.line; g.beginPath(); g.arc(x, y, radius, start, start + sweep); g.stroke();
  for (const [from, to, color] of zones) { g.strokeStyle = color; g.beginPath(); g.arc(x, y, radius, angle(from), angle(to)); g.stroke(); }
  g.lineWidth = 1; g.strokeStyle = colors.muted;
  for (let i = 0; i <= 10; i++) {
    const a = start + sweep * i / 10, inner = radius * (i % 5 ? .84 : .76);
    g.beginPath(); g.moveTo(x + Math.cos(a) * inner, y + Math.sin(a) * inner);
    g.lineTo(x + Math.cos(a) * radius * .92, y + Math.sin(a) * radius * .92); g.stroke();
  }
  if (finite(order)) {
    const a = angle(order);
    g.fillStyle = colors.amber; g.beginPath();
    g.moveTo(x + Math.cos(a) * radius * 1.14, y + Math.sin(a) * radius * 1.14);
    g.lineTo(x + Math.cos(a - .07) * radius * 1.3, y + Math.sin(a - .07) * radius * 1.3);
    g.lineTo(x + Math.cos(a + .07) * radius * 1.3, y + Math.sin(a + .07) * radius * 1.3); g.fill();
  }
  if (finite(value)) {
    const a = angle(value);
    g.strokeStyle = colors.accent; g.lineWidth = 2.5; g.beginPath();
    g.moveTo(x - Math.cos(a) * radius * .12, y - Math.sin(a) * radius * .12);
    g.lineTo(x + Math.cos(a) * radius * .8, y + Math.sin(a) * radius * .8); g.stroke();
  }
  g.fillStyle = colors.text; g.beginPath(); g.arc(x, y, Math.max(3, radius * .07), 0, Math.PI * 2); g.fill();
  g.textAlign = "center"; g.textBaseline = "middle";
  g.fillStyle = colors.text; g.fillText(text, x, y + radius * .45, radius * 1.8);
  g.fillStyle = colors.muted; g.fillText(label, x, y + radius * .95, room);
  if (sub) g.fillText(sub, x, y + radius * .95 + 16, room);
}

// The gauges in one, two or three rows (whichever gives the largest dials),
// with a text equivalent of each.
export function drawDialPanel(canvasId, textId, makeSpecs) {
  const plot = visualContext(canvasId);
  if (!plot) return;
  const {context: g, width, height} = plot, colors = palette();
  const specs = makeSpecs(colors);
  const fit = (columns) => {
    const rows = Math.ceil(specs.length / columns), cellW = width / columns, cellH = height / rows;
    return {columns, cellW, cellH, radius: Math.min(cellW * .36, (cellH - 44) * .5)};
  };
  const {columns, cellW, cellH, radius: best} = [specs.length, Math.ceil(specs.length / 2), Math.ceil(specs.length / 3)]
    .map(fit).reduce((a, b) => b.radius > a.radius ? b : a);
  const radius = Math.max(18, best);
  specs.forEach((spec, index) => {
    const x = cellW * (index % columns + .5), y = cellH * Math.floor(index / columns) + cellH * .5 - 12;
    dial(g, x, y, radius, cellW - 10, spec, colors);
  });
  const box = $(textId), tag = box.tagName === "UL" ? "li" : "p";
  box.replaceChildren(...specs.map((spec) => node(tag, `${spec.label}: ${spec.text}${spec.sub ? ` (${spec.sub})` : ""}`)));
}
