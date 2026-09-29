import { $, damageStates } from "../core/base.js";
import { enumText, finite, number, t, unit } from "../core/format.js";
import { palette } from "../core/palette.js";
import { dial, renderLampPanel, signed } from "../views/console-kit.js";

// The frigate's damage-control stage as a console: an annunciator panel over
// a plan of the ship seen from above (bow left, starboard hull on top) with
// water, fire and the teams in each section, and the stability gauges.
// Display plus the hit boxes the click handler assigns teams with.

const SECTIONS = ["sonar", "bridge", "weapons", "opz", "radio", "engine", "flightdeck"];
const SIDES = {hull_right: "top", hull_left: "bottom"};

function level(room) {
  if (room.state === "ZERSTOERT" || room.fire > 0) return "alarm";
  return room.state !== "OK" || room.flood > 0 ? "caution" : "on";
}

export function renderDamageLamps(payload) {
  const rooms = payload.compartments, stability = payload.stability;
  const burning = rooms.filter((room) => room.fire > 0).length;
  const flooding = rooms.filter((room) => room.flood > 0).length;
  const lost = rooms.filter((room) => room.state === "ZERSTOERT").length;
  const busy = payload.teams.filter((team) => team.compartment).length;
  const rising = rooms.filter((room) => room.trend.flood_rate > .005 || room.trend.fire_rate > .005).length;
  const list = Math.abs(stability.list_deg), trim = Math.abs(stability.trim_deg);
  const rows = [];
  const add = (key, label, lamp, value) => rows.push([key, label, lamp, value]);
  add("fire", t("damage_lamp_fire"), burning ? "alarm" : "off", String(burning));
  add("flooding", t("damage_lamp_flooding"), flooding ? "caution" : "off", String(flooding));
  add("destroyed", t("damage_lamp_destroyed"), lost ? "alarm" : "off", String(lost));
  add("rising", t("damage_lamp_rising"), rising ? "caution" : "off", String(rising));
  add("total", t("damage_total"), payload.total >= 30 ? "alarm" : payload.total > 0 ? "caution" : "on", unit(payload.total, "%", 0));
  add("list", t("damage_list"), list >= 10 ? "alarm" : list >= 5 ? "caution" : "on", `${signed(stability.list_deg, 1)}°`);
  add("trim", t("damage_lamp_trim"), trim >= 3 ? "caution" : "on", `${signed(stability.trim_deg, 1)}°`);
  add("counterflood", t("damage_lamp_counterflood"), stability.counterflood_room ? "caution" : stability.can_counterflood ? "on" : "off",
    t(stability.counterflood_room ? "uboot_lamp_on" : "uboot_lamp_off"));
  add("teams", t("damage_lamp_teams"), busy ? "on" : "off", `${busy}/${payload.teams.length}`);
  add("sunk", t("sunk"), payload.sunk ? "alarm" : "off", t(payload.sunk ? "uboot_lamp_on" : "uboot_lamp_off"));
  renderLampPanel($("damage-lamps"), $("damage-master"), rows);
}

function hullPath(g, x, y, w, h) {
  const bow = Math.min(w * .12, h * .8);
  g.beginPath();
  g.moveTo(x, y + h / 2);
  g.bezierCurveTo(x + bow * .35, y + h * .08, x + bow * .6, y, x + bow, y);
  g.lineTo(x + w - 6, y); g.quadraticCurveTo(x + w, y, x + w, y + 6);
  g.lineTo(x + w, y + h - 6); g.quadraticCurveTo(x + w, y + h, x + w - 6, y + h);
  g.lineTo(x + bow, y + h);
  g.bezierCurveTo(x + bow * .6, y + h, x + bow * .35, y + h * .92, x, y + h / 2);
  g.closePath();
  return bow;
}

function badge(g, x, y, r, text, colors, selected) {
  g.fillStyle = selected ? colors.amber : colors.accent;
  g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.fill();
  g.fillStyle = colors.bg; g.textAlign = "center"; g.textBaseline = "middle";
  g.fillText(text, x, y + 1);
}

function room(g, box, data, teams, selectedTeam, colors) {
  const {x, y, width: w, height: h} = box;
  const alert = level(data);
  const edge = alert === "alarm" ? colors.red : alert === "caution" ? colors.amber : colors.line;
  g.save();
  g.beginPath(); g.rect(x, y, w, h); g.clip();
  const water = h * Math.max(0, Math.min(100, data.flood)) / 100;
  if (water > 0) {
    const sea = g.createLinearGradient(0, y + h - water, 0, y + h);
    sea.addColorStop(0, colors.blue); sea.addColorStop(1, colors.bg);
    g.globalAlpha = .75; g.fillStyle = sea; g.fillRect(x, y + h - water, w, water); g.globalAlpha = 1;
    g.strokeStyle = colors.blue; g.beginPath(); g.moveTo(x, y + h - water); g.lineTo(x + w, y + h - water); g.stroke();
  }
  if (data.fire > 0) {
    const glow = g.createRadialGradient(x + w / 2, y + h * .6, 2, x + w / 2, y + h * .6, Math.max(w, h) * .7);
    glow.addColorStop(0, colors.red); glow.addColorStop(1, "transparent");
    g.globalAlpha = Math.min(.85, .25 + data.fire / 120); g.fillStyle = glow; g.fillRect(x, y, w, h); g.globalAlpha = 1;
  }
  if (data.state === "ZERSTOERT") {
    g.strokeStyle = colors.red; g.globalAlpha = .45; g.lineWidth = 1;
    for (let d = -h; d < w; d += 12) { g.beginPath(); g.moveTo(x + d, y + h); g.lineTo(x + d + h, y); g.stroke(); }
    g.globalAlpha = 1;
  }
  g.restore();
  const mine = teams.some((team) => team.team === selectedTeam);
  g.strokeStyle = mine ? colors.accent : edge; g.lineWidth = mine ? 3 : alert === "on" ? 1 : 2;
  g.strokeRect(x + .5, y + .5, w - 1, h - 1);
  return {x, y, w, h, mine};
}

function label(g, box, data, colors, row) {
  const {x, y, width: w} = box;
  g.textAlign = "center"; g.textBaseline = "top";
  g.fillStyle = colors.text; g.fillText(data.name, x + w / 2, y + 6, w - 8);
  const alert = level(data);
  g.fillStyle = alert === "alarm" ? colors.red : alert === "caution" ? colors.amber : colors.muted;
  g.fillText(enumText(damageStates, data.state), x + w / 2, y + 6 + row, w - 8);
  const parts = [];
  if (data.flood > 0) parts.push(t("damage_plan_water", {value: number(data.flood, 0)}));
  if (data.fire > 0) parts.push(t("damage_plan_fire", {value: number(data.fire, 0)}));
  if (parts.length) { g.fillStyle = colors.text; g.fillText(parts.join(" · "), x + w / 2, y + 6 + row * 2, w - 8); }
}

// Draws the plan and the gauges into ``plot``; returns the hit boxes.
export function drawShipPlan(plot, payload, selectedTeam) {
  const g = plot.context, colors = palette();
  const row = Math.max(14, parseFloat(g.font) * 1.3 || 16);
  const byKey = new Map(payload.compartments.map((data) => [data.key, data]));
  const gaugeH = Math.max(110, Math.min(190, plot.height * .3));
  const planH = Math.max(120, plot.height - gaugeH - 24);
  const px = 18, py = 14, pw = plot.width - 36;
  const hits = [];
  g.save();
  const bow = hullPath(g, px, py, pw, planH);
  g.fillStyle = colors.panel; g.fill();
  g.clip();
  const strip = Math.max(row * 2.2, planH * .16);
  const sides = Object.keys(SIDES).filter((key) => byKey.has(key));
  const top = py + (byKey.has("hull_right") ? strip + 4 : 6), bottom = py + planH - (byKey.has("hull_left") ? strip + 4 : 6);
  for (const key of sides) {
    const box = {x: px + bow * .75, y: SIDES[key] === "top" ? py + 3 : py + planH - strip - 3, width: pw - bow * .75 - 3, height: strip};
    room(g, box, byKey.get(key), payload.teams.filter((team) => team.compartment === key), selectedTeam, colors);
    g.textAlign = "left"; g.textBaseline = "middle"; g.fillStyle = colors.text;
    const data = byKey.get(key), alert = level(data);
    g.fillText(`${data.name} · ${enumText(damageStates, data.state)}${data.flood > 0 ? ` · ${t("damage_plan_water", {value: number(data.flood, 0)})}` : ""}`,
      box.x + 10, box.y + box.height / 2, box.width * .7);
    g.fillStyle = alert === "alarm" ? colors.red : alert === "caution" ? colors.amber : colors.accent;
    g.beginPath(); g.arc(box.x + box.width - 14, box.y + box.height / 2, 5, 0, Math.PI * 2); g.fill();
    hits.push({key, x: box.x, y: box.y, width: box.width, height: box.height, teams: payload.teams.filter((team) => team.compartment === key)});
  }
  const keys = SECTIONS.filter((key) => byKey.has(key));
  const inner = {x: px + bow * .42, width: pw - bow * .42 - 4};
  const each = inner.width / Math.max(1, keys.length);
  keys.forEach((key, index) => {
    const box = {x: inner.x + index * each + 2, y: top, width: each - 4, height: bottom - top};
    room(g, box, byKey.get(key), payload.teams.filter((team) => team.compartment === key), selectedTeam, colors);
    label(g, box, byKey.get(key), colors, row);
    hits.push({key, ...box, teams: payload.teams.filter((team) => team.compartment === key)});
  });
  // Team badges, the selected team amber.
  for (const hit of hits) {
    hit.teams.forEach((team, index) => {
      const r = Math.max(9, Math.min(13, row * .7));
      const cx = hit.x + hit.width / 2 + (index - (hit.teams.length - 1) / 2) * (2 * r + 4);
      const cy = SIDES[hit.key] ? hit.y + hit.height / 2 : hit.y + hit.height - r - 8;
      badge(g, SIDES[hit.key] ? hit.x + hit.width * .75 + index * (2 * r + 4) : cx, cy, r, String(team.team), colors, team.team === selectedTeam);
    });
  }
  g.restore();
  hullPath(g, px, py, pw, planH);
  g.strokeStyle = colors.accent; g.lineWidth = 2; g.stroke();
  // Stability and flooding gauges under the plan.
  const stability = payload.stability;
  const specs = [
    {label: t("damage_list"), value: stability.list_deg, min: -20, max: 20,
      zones: [[-20, -10, colors.red], [-10, -5, colors.amber], [5, 10, colors.amber], [10, 20, colors.red]],
      text: `${signed(stability.list_deg, 1)}°`},
    {label: t("damage_lamp_trim"), value: stability.trim_deg, min: -6, max: 6,
      zones: [[-6, -3, colors.amber], [3, 6, colors.amber]], text: `${signed(stability.trim_deg, 1)}°`},
    {label: t("damage_total"), value: payload.total, min: 0, max: 100,
      zones: [[30, 60, colors.amber], [60, 100, colors.red]], text: unit(payload.total, "%", 0)},
  ];
  const gy = py + planH + 12, cell = plot.width / specs.length;
  const radius = Math.max(20, Math.min(cell * .3, (gaugeH - row * 2) * .45));
  specs.forEach((spec, index) => dial(g, cell * (index + .5), gy + radius + 6, radius, cell - 12, spec, colors));
  return hits.map(({key, x, y, width, height}) => ({key, x, y, width, height}));
}
