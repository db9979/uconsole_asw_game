import { $ } from "../core/base.js";
import { S } from "../state/store.js";
import { finite, number, t } from "../core/format.js";
import { palette } from "../core/palette.js";
import { node } from "./dom.js";
import { setLampTip } from "./lamp-tip.js";
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

// Lamps are [key, label, level, value, control, tip]; the master lamp counts
// alarms and cautions. ``tip`` is the lamp's hover note (``lamp_tips``).
export function renderLampPanel(box, master, rows) {
  renderLamps(box, rows);
  const alarms = rows.filter((row) => row[2] === "alarm").length, cautions = rows.filter((row) => row[2] === "caution").length;
  master.dataset.state = alarms ? "alarm" : cautions ? "caution" : "live";
  master.textContent = alarms ? t("uboot_engine_master_alarm", {count: alarms})
    : cautions ? t("uboot_engine_master_caution", {count: cautions}) : t("uboot_engine_master_clear");
}

// A lamp with a control (the row's fifth entry: the id of the station's own
// button or switch, or a function returning the control to press, such as the
// not-pressed button of an on/off pair) works that control when clicked, as
// on the uConsole, so the order takes the same path as the button itself.
const lampControls = new WeakMap();
const controlOf = (control) => typeof control === "function" ? control() : control ? $(control) : null;
function pressLampControl(cell) {
  const control = cell.dataset.control ? controlOf(lampControls.get(cell)) : null;
  if (control && !control.disabled) control.click();
}

// The not-pressed, visible button of one of the boat's on/off pairs: a lamp or
// chip of that mode switches it over (A silent running, N snorkel, P mast ...).
export function modeSwitch(mode) {
  return () => [...document.querySelectorAll(`[data-uboot-mode="${mode}"]`)]
    .filter((button) => !button.closest("[hidden]") && button.getClientRects().length > 0)
    .find((button) => button.getAttribute("aria-pressed") !== "true") ?? null;
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
    cell.addEventListener("click", () => pressLampControl(cell));
    cell.addEventListener("keydown", (event) => {
      if (!cell.dataset.control || (event.key !== "Enter" && event.key !== " ")) return;
      event.preventDefault();
      pressLampControl(cell);
    });
    return cell;
  });
  rows.forEach(([, label, level, value, control, tip], index) => {
    const cell = cells[index];
    cell.dataset.level = level;
    setLampTip(cell, tip);
    if (tip && !cell.hasAttribute("tabindex")) cell.tabIndex = 0;
    cell.children[1].textContent = label;
    cell.children[2].textContent = value;
    const target = controlOf(control);
    const live = Boolean(target && !target.disabled && !target.hidden);
    lampControls.set(cell, control);
    if (live) {
      const name = typeof control === "function" ? "switch" : control;
      if (cell.dataset.control !== name) {
        cell.dataset.control = name;
        cell.setAttribute("role", "button");
        cell.tabIndex = 0;
      }
    } else if (cell.dataset.control) {
      delete cell.dataset.control;
      cell.setAttribute("role", "listitem");
      if (!tip) cell.removeAttribute("tabindex");
    }
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

// Needles with mass (src/ui/instruments.py needle): each follows its value
// like a damped spring on the wall clock, so it swings in and settles; a
// needle not drawn for half a second starts at its value again.
const NEEDLE_OMEGA = 7, NEEDLE_ZETA = .5, NEEDLE_RESET_S = .5;
const needles = new Map(), panels = new Map();
function needle(key, target, span) {
  const now = performance.now() / 1000, state = needles.get(key);
  if (!finite(target)) { needles.delete(key); return {value: target, settled: true}; }
  if (!state || !(now - state.t >= 0 && now - state.t <= NEEDLE_RESET_S)) {
    needles.set(key, {value: target, velocity: 0, t: now});
    return {value: target, settled: true};
  }
  let {value, velocity} = state, elapsed = now - state.t;
  while (elapsed > 1e-6) {
    const step = Math.min(elapsed, 1 / 120), accel = NEEDLE_OMEGA ** 2 * (target - value) - 2 * NEEDLE_ZETA * NEEDLE_OMEGA * velocity;
    velocity += accel * step; value += velocity * step; elapsed -= step;
  }
  needles.set(key, {value, velocity, t: now});
  // A gauge without a finite span settles relative to its value, so its
  // needle never keeps the page animating.
  const scale = finite(span) && Math.abs(span) > 0 ? Math.abs(span) : Math.max(1, Math.abs(target));
  return {value, settled: Math.abs(target - value) < scale * .002 && Math.abs(velocity) < scale * .01};
}

function paintDials(canvasId) {
  const panel = panels.get(canvasId);
  if (!panel) return false;
  panel.frame = null;
  const plot = visualContext(canvasId);
  if (!plot) return false;
  const {context: g, width, height} = plot, specs = panel.specs, colors = panel.colors;
  const fit = (columns) => {
    const rows = Math.ceil(specs.length / columns), cellW = width / columns, cellH = height / rows;
    return {columns, cellW, cellH, radius: Math.min(cellW * .36, (cellH - 44) * .5)};
  };
  const {columns, cellW, cellH, radius: best} = [specs.length, Math.ceil(specs.length / 2), Math.ceil(specs.length / 3)]
    .map(fit).reduce((a, b) => b.radius > a.radius ? b : a);
  const radius = Math.max(18, best);
  let moving = false;
  specs.forEach((spec, index) => {
    const x = cellW * (index % columns + .5), y = cellH * Math.floor(index / columns) + cellH * .5 - 12;
    const shown = needle(`${canvasId}:${index}`, spec.value, spec.max - spec.min);
    moving ||= !shown.settled;
    dial(g, x, y, radius, cellW - 10, {...spec, value: shown.value}, colors);
  });
  if (moving) panel.frame = requestAnimationFrame(() => paintDials(canvasId));
  return true;
}

// The gauges in one, two or three rows (whichever gives the largest dials),
// with a text equivalent of each.
export function drawDialPanel(canvasId, textId, makeSpecs) {
  const colors = palette(), specs = makeSpecs(colors), previous = panels.get(canvasId);
  if (previous?.frame) cancelAnimationFrame(previous.frame);
  panels.set(canvasId, {specs, colors, frame: null});
  if (!paintDials(canvasId)) return;
  const box = $(textId), tag = box.tagName === "UL" ? "li" : "p";
  box.replaceChildren(...specs.map((spec) => node(tag, `${spec.label}: ${spec.text}${spec.sub ? ` (${spec.sub})` : ""}`)));
}

// The hover note of lamp ``name`` in the current role state, if any.
export function lampTip(name) {
  const tips = S.v2State?.lamp_tips;
  return tips && Object.prototype.hasOwnProperty.call(tips, name) ? tips[name] : undefined;
}

// Every note of the role state as a lamp (stations whose lamps all come from
// the host: bridge, CIC, radio room, damage control).
export function renderNoteLamps(box) {
  const tips = S.v2State?.lamp_tips || {};
  renderLamps(box, Object.keys(tips).map((name) => noteLamp(name, name)).filter(Boolean));
}

// A lamp drawn wholly from its note: label, value and level come from the host.
export function noteLamp(key, name, control) {
  const tip = lampTip(name);
  return tip ? [key, tip.label, tip.level || "off", tip.value, control, tip] : null;
}
