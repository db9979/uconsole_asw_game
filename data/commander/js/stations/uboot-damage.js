import { $ } from "../core/base.js";
import { number, t, unit } from "../core/format.js";
import { palette } from "../core/palette.js";
import { dial, pct, renderLampPanel, signed } from "../views/console-kit.js";
import { visualContext } from "../views/visual-common.js";
import { drawBoatSection } from "./damage-section.js";

// The submarine's damage-control stage as a console, like the frigate's
// Damage card: an annunciator panel over the cutaway of the boat
// (damage-section.js, bow right) with water, fire, gas, leaks, bulkhead doors
// and the two teams in each compartment, and gauges for trim, floodwater and
// high-pressure air.
// Own-ship truth only; the table and the team orders below stay the controls.

const onOff = (active) => t(active ? "uboot_lamp_on" : "uboot_lamp_off");

function lamps(payload) {
  const dc = payload.damage_control, ballast = payload.ballast, nav = payload.navigation;
  const rooms = dc.compartments, hurt = dc.crew.casualties;
  const count = (test) => rooms.filter(test).length;
  const leaks = count((row) => row.leak_pct > 0), fires = count((row) => row.fire_pct > 0);
  const gas = count((row) => row.chlorine_pct > 0), shut = count((row) => row.closed);
  const lost = count((row) => row.down), busy = dc.teams.filter((team) => team.task !== "idle").length;
  const wounded = hurt.wounded + hurt.serious, hp = pct(ballast.hp_air_bar, ballast.hp_air_max_bar);
  const rows = [];
  const add = (key, label, level, value) => rows.push([key, label, level, value]);
  add("power", t("uboot_dc_power"), dc.power ? "on" : "alarm", t(dc.power ? "uboot_dc_power_on" : "uboot_dc_power_off"));
  add("flooding", t("uboot_dc_lamp_water"), ballast.flooding_kg > 2000 ? "alarm" : ballast.flooding_kg > 0 ? "caution" : "off",
    unit(ballast.flooding_kg / 1000, "t", 1));
  add("leak", t("uboot_lamp_leak"), leaks ? "alarm" : "off", String(leaks));
  add("fire", t("uboot_lamp_fire"), fires ? "alarm" : "off", String(fires));
  add("gas", t("uboot_lamp_gas"), gas ? "alarm" : "off", String(gas));
  add("down", t("damage_lamp_destroyed"), lost ? "alarm" : "off", String(lost));
  add("bulkheads", t("uboot_dc_lamp_bulkheads"), shut ? "caution" : "off", String(shut));
  add("teams", t("damage_lamp_teams"), busy ? "on" : "off", `${busy}/${dc.teams.length}`);
  add("pumping", t("uboot_dc_lamp_bilge"), dc.pumping ? "on" : "off", onOff(dc.pumping));
  add("wounded", t("crew_wounded"), hurt.serious ? "alarm" : wounded ? "caution" : "off", String(wounded));
  add("trim", t("uboot_trim_angle"), Math.abs(ballast.trim_deg) > 3 ? "caution" : "on", `${signed(ballast.trim_deg, 1)}°`);
  add("hp_air", t("uboot_hp_air"), ballast.blows_left === 0 ? "alarm" : hp !== null && hp < 50 ? "caution" : "on",
    unit(ballast.hp_air_bar, "bar", 0));
  add("overdepth", t("uboot_lamp_overdepth"), nav.depth_m > nav.max_depth_m ? "alarm" : "off", unit(nav.depth_m, "m", 0));
  return rows;
}

export function renderBoatDamageLamps(payload) {
  renderLampPanel($("uboot-dc-lamps"), $("uboot-dc-master"), lamps(payload));
}

function level(row) {
  if (row.down || row.fire_pct > 0 || row.chlorine_pct > 0) return "alarm";
  return row.leak_pct > 0 || row.water_kg > 0 ? "caution" : "on";
}

export function drawBoatDamage(id, payload) {
  const plot = visualContext(id);
  if (!plot) return;
  const {context: g, width, height} = plot, colors = palette(), dc = payload.damage_control;
  const ballast = payload.ballast;
  const rowH = Math.max(14, parseFloat(g.font) * 1.3 || 16);
  const gaugeH = Math.max(90, Math.min(150, height * .36));
  const px = 16, py = rowH + 8, pw = width - 32, ph = Math.max(60, height - gaugeH - py - rowH * 2 - 16);
  const cells = drawBoatSection(g, {x: px, y: py, width: pw, height: ph}, dc.compartments, dc.teams, ballast.trim_deg, colors);
  g.textBaseline = "alphabetic"; g.textAlign = "center";
  dc.compartments.forEach((row) => {
    const cell = cells[row.name], alert = level(row);
    if (!cell) return;
    g.fillStyle = alert === "alarm" ? colors.red : alert === "caution" ? colors.amber : colors.muted;
    g.fillText(t(`uboot_compartment_${row.name}`), cell.x + cell.width / 2, py + ph + rowH, cell.width - 4);
    g.fillStyle = row.water_kg > 0 ? colors.amber : colors.muted;
    g.fillText(unit(row.water_kg / 1000, "t", 1), cell.x + cell.width / 2, py + ph + rowH * 2, cell.width - 4);
  });
  g.fillStyle = colors.muted; g.textAlign = "right"; g.fillText(t("uboot_canvas_bow"), px + pw, py - 6);
  g.textAlign = "left"; g.fillStyle = dc.power ? colors.muted : colors.red;
  g.fillText(dc.power ? t("uboot_dc_power_on") : t("uboot_dc_power_off"), px, py - 6);
  // Gauges: trim, floodwater and high-pressure air.
  const specs = [
    {label: t("uboot_trim_angle"), value: ballast.trim_deg, min: -10, max: 10,
      zones: [[-10, -3, colors.amber], [3, 10, colors.amber]], text: `${signed(ballast.trim_deg, 1)}°`},
    {label: t("uboot_flooding"), value: ballast.flooding_kg / 1000, min: 0, max: 20,
      zones: [[2, 8, colors.amber], [8, 20, colors.red]], text: unit(ballast.flooding_kg / 1000, "t", 1)},
    {label: t("uboot_hp_air"), value: ballast.hp_air_bar, min: 0, max: ballast.hp_air_max_bar || 250,
      zones: [[0, (ballast.hp_air_max_bar || 250) * .25, colors.red], [(ballast.hp_air_max_bar || 250) * .25, (ballast.hp_air_max_bar || 250) * .5, colors.amber]],
      text: unit(ballast.hp_air_bar, "bar", 0), sub: t("uboot_dc_blows_left", {count: number(ballast.blows_left, 0)})},
  ];
  const gy = py + ph + rowH * 2 + 10, each = width / specs.length;
  const radius = Math.max(18, Math.min(each * .28, (gaugeH - rowH * 2) * .45));
  specs.forEach((spec, index) => dial(g, each * (index + .5), gy + radius + 4, radius, each - 12, spec, colors));
}
