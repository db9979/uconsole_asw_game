import { $ } from "../core/base.js";
import { number, t, unit } from "../core/format.js";
import { palette } from "../core/palette.js";
import { dial, renderLampPanel, signed } from "../views/console-kit.js";
import { drawFrigateProfile, drawFrigateSection } from "./damage-section.js";

// The frigate's damage-control stage as a console: an annunciator panel over
// the side profile and the listing cross-section (damage-section.js, the
// same drawing as the uConsole) and the stability gauges. Display plus the
// hit boxes the click handler assigns teams with.

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

// Draws the plan and the gauges into ``plot``; returns the hit boxes.
export function drawShipPlan(plot, payload, selectedTeam) {
  const g = plot.context, colors = palette();
  const row = Math.max(14, parseFloat(g.font) * 1.3 || 16);
  const gaugeH = Math.max(110, Math.min(190, plot.height * .3));
  const planH = Math.max(120, plot.height - gaugeH - 24);
  const px = 18, py = 14, pw = plot.width - 36;
  const sectionW = Math.max(90, Math.min(pw * .22, planH));
  const profile = {x: px, y: py, width: pw - sectionW - 10, height: planH - row - 4};
  const section = {x: px + pw - sectionW, y: py, width: sectionW, height: planH - row - 4};
  const hits = [...drawFrigateProfile(g, profile, payload, colors, selectedTeam),
    ...drawFrigateSection(g, section, payload, colors, selectedTeam)];
  const stability = payload.stability;
  g.textBaseline = "top"; g.textAlign = "left"; g.fillStyle = colors.blue;
  g.fillText(t("damage_profile_draft", {draft: number(stability.draft_m, 1), trim: signed(stability.trim_deg, 1)}), px, py + planH - row, profile.width);
  g.textAlign = "center"; g.fillStyle = Math.abs(stability.list_deg) >= 5 ? colors.amber : colors.muted;
  g.fillText(t("damage_section_list", {list: signed(stability.list_deg, 1)}), section.x + section.width / 2, py + planH - row, section.width);
  // Stability and flooding gauges under the plan.
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
  const boxes = hits.map(({key, x, y, width, height}) => ({key, x: Math.round(x), y: Math.round(y), width: Math.round(width), height: Math.round(height)}));
  plot.element.dataset.hits = JSON.stringify(boxes);
  return boxes;
}
