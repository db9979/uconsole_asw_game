import { $ } from "../core/base.js";
import { number, t, unit } from "../core/format.js";
import { palette } from "../core/palette.js";
import { dial, pct, renderLampPanel, signed } from "../views/console-kit.js";
import { visualContext } from "../views/visual-common.js";

// The submarine's damage-control stage as a console, like the frigate's
// Damage card: an annunciator panel over a side view of the pressure hull
// (bow right) with water, fire, gas, leaks, bulkheads and the two teams in
// each compartment, and gauges for trim, floodwater and high-pressure air.
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

function hull(g, x, y, w, h) {
  // A pressure hull seen from the side: round stern left, bow right.
  const r = h / 2;
  g.beginPath();
  g.moveTo(x + r, y); g.lineTo(x + w - r * 1.4, y);
  g.bezierCurveTo(x + w - r * .3, y, x + w, y + r * .55, x + w, y + r);
  g.bezierCurveTo(x + w, y + r * 1.45, x + w - r * .3, y + h, x + w - r * 1.4, y + h);
  g.lineTo(x + r, y + h); g.arc(x + r, y + r, r, Math.PI / 2, Math.PI * 1.5); g.closePath();
}

export function drawBoatDamage(id, payload) {
  const plot = visualContext(id);
  if (!plot) return;
  const {context: g, width, height} = plot, colors = palette(), dc = payload.damage_control;
  const ballast = payload.ballast;
  const rowH = Math.max(14, parseFloat(g.font) * 1.3 || 16);
  const gaugeH = Math.max(90, Math.min(150, height * .36));
  const px = 16, py = rowH + 8, pw = width - 32, ph = Math.max(60, height - gaugeH - py - rowH - 16);
  const count = dc.compartments.length, inset = ph / 2, cell = (pw - inset * 1.6) / count;
  g.save();
  hull(g, px, py, pw, ph);
  g.fillStyle = colors.panel; g.fill(); g.clip();
  dc.compartments.forEach((row, index) => {
    const x = px + inset * .6 + (count - 1 - index) * cell, alert = level(row);
    g.save(); g.beginPath(); g.rect(x, py, cell, ph); g.clip();
    const water = Math.max(0, Math.min(1, row.water_kg / row.capacity_kg));
    if (water > 0) {
      const top = py + ph * (1 - water), sea = g.createLinearGradient(0, top, 0, py + ph);
      sea.addColorStop(0, colors.blue); sea.addColorStop(1, colors.bg);
      g.globalAlpha = .75; g.fillStyle = sea; g.fillRect(x, top, cell, ph * water); g.globalAlpha = 1;
      g.strokeStyle = colors.blue; g.beginPath(); g.moveTo(x, top); g.lineTo(x + cell, top); g.stroke();
    }
    if (row.fire_pct > 0) {
      const glow = g.createRadialGradient(x + cell / 2, py + ph * .65, 2, x + cell / 2, py + ph * .65, Math.max(cell, ph) * .7);
      glow.addColorStop(0, colors.red); glow.addColorStop(1, "transparent");
      g.globalAlpha = Math.min(.85, .25 + row.fire_pct / 120); g.fillStyle = glow; g.fillRect(x, py, cell, ph); g.globalAlpha = 1;
    }
    if (row.chlorine_pct > 0) {
      g.globalAlpha = Math.min(.5, .1 + row.chlorine_pct / 200); g.fillStyle = colors.accent;
      g.fillRect(x, py, cell, ph * .6); g.globalAlpha = 1;
    }
    if (row.down) {
      g.strokeStyle = colors.red; g.globalAlpha = .45; g.lineWidth = 1;
      for (let d = -ph; d < cell; d += 10) { g.beginPath(); g.moveTo(x + d, py + ph); g.lineTo(x + d + ph, py); g.stroke(); }
      g.globalAlpha = 1;
    }
    g.restore();
    // The compartment's state LED and its leak, top of the cell.
    const led = alert === "alarm" ? colors.red : alert === "caution" ? colors.amber : colors.accent;
    g.fillStyle = led; g.shadowColor = led; g.shadowBlur = 6;
    g.beginPath(); g.arc(x + cell / 2, py + 12, 4, 0, Math.PI * 2); g.fill(); g.shadowBlur = 0;
    if (row.leak_pct > 0) {
      g.fillStyle = colors.amber; g.beginPath(); g.arc(x + cell / 2, py + ph - 10, 2 + 4 * row.leak_pct / 100, 0, Math.PI * 2); g.fill();
    }
    // Team badges.
    const teams = dc.teams.filter((team) => team.compartment === row.name);
    teams.forEach((team, n) => {
      const r = Math.max(7, Math.min(11, rowH * .6)), cx = x + cell / 2 + (n - (teams.length - 1) / 2) * (2 * r + 3), cy = py + ph / 2;
      g.fillStyle = colors.accent; g.beginPath(); g.arc(cx, cy, r, 0, Math.PI * 2); g.fill();
      g.fillStyle = colors.bg; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(String(team.team + 1), cx, cy + 1);
    });
  });
  g.restore();
  // Bulkheads between compartments, thick amber where shut; then the hull.
  for (let index = 0; index <= count; index++) {
    const x = px + inset * .6 + index * cell;
    const left = dc.compartments[count - index], right = dc.compartments[count - 1 - index];
    const shut = (left && left.closed) || (right && right.closed);
    if (index === 0 || index === count) continue;
    g.strokeStyle = shut ? colors.amber : colors.line; g.lineWidth = shut ? 4 : 1;
    g.beginPath(); g.moveTo(x, py + 2); g.lineTo(x, py + ph - 2); g.stroke();
  }
  hull(g, px, py, pw, ph);
  g.strokeStyle = colors.accent; g.lineWidth = 2; g.stroke(); g.lineWidth = 1;
  g.textBaseline = "alphabetic"; g.textAlign = "center";
  dc.compartments.forEach((row, index) => {
    const x = px + inset * .6 + (count - 1 - index) * cell, alert = level(row);
    g.fillStyle = alert === "alarm" ? colors.red : alert === "caution" ? colors.amber : colors.muted;
    g.fillText(t(`uboot_compartment_${row.name}`), x + cell / 2, py + ph + rowH, cell - 4);
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
  const gy = py + ph + rowH + 10, each = width / specs.length;
  const radius = Math.max(18, Math.min(each * .28, (gaugeH - rowH * 2) * .45));
  specs.forEach((spec, index) => dial(g, each * (index + .5), gy + radius + 4, radius, each - 12, spec, colors));
}
