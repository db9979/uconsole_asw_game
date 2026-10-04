import { S } from "../state/store.js";
import { $ } from "../core/base.js";
import { finite, number, t, unit } from "../core/format.js";
import { node } from "../views/dom.js";
import { drawDialPanel, keyed, lampTip, pct, renderLampPanel, signed } from "../views/console-kit.js";
import { palette } from "../core/palette.js";
import { visualContext } from "../views/visual-common.js";
import { drawBoatSection } from "./damage-section.js";

// The submarine's engine-room control console on the stage: an annunciator
// panel of status lamps, round gauges, tank columns and the compartment
// mimic. Everything comes from the boat's own plant, tanks and damage
// report (own-ship truth); nothing here is an order, the dock keeps those.

const onOff = (active) => t(active ? "uboot_lamp_on" : "uboot_lamp_off");

// One lamp: [key, label, level, value]. A lamp whose system the boat does
// not have (a nuclear plant has no battery, diesel or air stores) is left out.
function lamps(payload) {
  const nav = payload.navigation, status = payload.status, plant = payload.plant;
  const ballast = payload.ballast, dc = payload.damage_control, air = plant.air;
  const nuclear = plant.propulsion === "nuclear";
  const rows = [];
  // Each lamp carries the host's note on why it shows what it shows.
  const add = (key, label, level, value) => rows.push([key, label, level, value, undefined,
    lampTip(`sys_${key}`) ?? lampTip(key === "cavitating" ? "cavitation" : key)]);
  // Propulsion.
  add("motor", t(nuclear ? "uboot_lamp_reactor" : "uboot_lamp_motor"), nav.speed > .05 ? "on" : "off", unit(nav.speed, "kn"));
  add("silent", t("uboot_chip_silent"), status.silent ? (status.quiet ? "on" : "caution") : "off", onOff(status.silent));
  add("cavitating", t("uboot_chip_cavitating"), nav.cavitating ? "alarm" : "off", onOff(nav.cavitating));
  if (!nuclear) {
    add("snorkel", t("uboot_chip_snorkel"), status.snorkeling ? "caution" : "off", onOff(status.snorkeling));
    // The diesels run only while snorkelling; the plant reports their rating.
    add("generator", t("uboot_lamp_generator"), status.snorkeling ? "on" : "off",
      status.snorkeling ? unit(plant.generator_kw, "kW", 0) : onOff(false));
    if (plant.aip_kw !== null) add("aip", t("uboot_aip"), plant.aip_kw > 0 ? "on" : "off", unit(plant.aip_kw, "kW", 0));
    // Energy and stores.
    const battery = pct(plant.battery_kwh, plant.battery_capacity_kwh);
    add("battery", t("uboot_battery"), battery === null ? "off" : battery <= 3 ? "alarm" : battery <= 20 ? "caution" : "on", unit(battery, "%", 0));
    add("charging", t("uboot_lamp_charging"), plant.net_kw > 0 ? "on" : "off", `${signed(plant.net_kw, 0)} kW`);
    if (plant.fuel_l !== null) {
      const fuel = pct(plant.fuel_l, plant.fuel_capacity_l);
      add("fuel", t("uboot_lamp_fuel"), fuel === null ? "off" : fuel <= 0 ? "alarm" : fuel <= 10 ? "caution" : "on", unit(fuel, "%", 0));
    }
  }
  if (air) {
    const level = air.level === "danger" ? "alarm" : air.level === "caution" ? "caution" : "on";
    add("o2", t("uboot_o2"), level, unit(air.o2_pct, "%", 1));
    add("co2", t("uboot_co2"), level, unit(air.co2_pct, "%", 2));
    add("absorber", t("uboot_absorber"), air.absorber_pct <= 0 ? "alarm" : air.absorber_pct <= 25 ? "caution" : "on", unit(air.absorber_pct, "%", 0));
    add("candle", t("uboot_lamp_candle"), air.candle_left_s > 0 ? "on" : "off", onOff(air.candle_left_s > 0));
  }
  // Tanks and high-pressure air.
  add("mbt", t("uboot_mbt"), ballast.blowing ? "caution" : ballast.mbt_pct >= 100 ? "on" : "off", unit(ballast.mbt_pct, "%", 0));
  add("blowing", t("uboot_lamp_blowing"), ballast.blowing ? "caution" : "off", onOff(ballast.blowing));
  add("venting", t("uboot_lamp_venting"), ballast.venting ? "on" : "off", t(ballast.venting ? "uboot_lamp_open" : "uboot_lamp_closed"));
  const hp = pct(ballast.hp_air_bar, ballast.hp_air_max_bar);
  add("hp_air", t("uboot_hp_air"), ballast.blows_left === 0 ? "alarm" : hp !== null && hp < 50 ? "caution" : "on", unit(ballast.hp_air_bar, "bar", 0));
  add("compressor", t("uboot_lamp_compressor"), ballast.compressor ? "on" : "off", onOff(ballast.compressor));
  add("pumps", t("uboot_pumps"), ballast.pumping ? "on" : "off", onOff(ballast.pumping));
  add("trim_auto", t("uboot_trim_auto"), ballast.auto ? "on" : "off", onOff(ballast.auto));
  add("trim", t("uboot_trim_angle"), Math.abs(ballast.trim_deg) > 3 ? "caution" : "on", `${signed(ballast.trim_deg, 1)}°`);
  // Safety: power, water, fire, gas, depth.
  const rooms = dc.compartments;
  const count = (test) => rooms.filter(test).length;
  add("power", t("uboot_dc_power"), dc.power ? "on" : "alarm", t(dc.power ? "uboot_dc_power_on" : "uboot_dc_power_off"));
  add("flooding", t("uboot_flooding"), ballast.flooding_kg > 2000 ? "alarm" : ballast.flooding_kg > 0 ? "caution" : "off", unit(ballast.flooding_kg / 1000, "t", 1));
  add("leak", t("uboot_lamp_leak"), count((row) => row.leak_pct > 0) ? "alarm" : "off", String(count((row) => row.leak_pct > 0)));
  add("fire", t("uboot_lamp_fire"), count((row) => row.fire_pct > 0) ? "alarm" : "off", String(count((row) => row.fire_pct > 0)));
  add("gas", t("uboot_lamp_gas"), count((row) => row.chlorine_pct > 0) ? "alarm" : "off", String(count((row) => row.chlorine_pct > 0)));
  add("overdepth", t("uboot_lamp_overdepth"), nav.depth_m > nav.max_depth_m ? "alarm" : "off", unit(nav.depth_m, "m", 0));
  add("ascent", t("uboot_emergency_ascent"), status.emergency_ascent ? "alarm" : "off", onOff(status.emergency_ascent));
  add("bottom", t("uboot_chip_bottom"), status.bottomed ? "on" : "off", onOff(status.bottomed));
  return rows;
}

function renderLamps(payload) {
  renderLampPanel($("uboot-engine-lamps"), $("uboot-engine-master"), lamps(payload));
}

// Tank columns: [key, label, fill 0..100 or signed -100..100, level, text, centred].
function tanks(payload) {
  const plant = payload.plant, ballast = payload.ballast, air = plant.air;
  const rows = [];
  const add = (...row) => rows.push(row);
  if (plant.propulsion !== "nuclear") {
    const battery = pct(plant.battery_kwh, plant.battery_capacity_kwh);
    add("battery", t("uboot_battery"), battery, battery !== null && battery <= 3 ? "alarm" : battery !== null && battery <= 20 ? "caution" : "",
      unit(battery, "%", 0), false);
    if (plant.fuel_l !== null) {
      const fuel = pct(plant.fuel_l, plant.fuel_capacity_l);
      add("fuel", t("uboot_lamp_fuel"), fuel, fuel !== null && fuel <= 10 ? "caution" : "", unit(plant.fuel_l / 1000, "m³", 1), false);
    }
    if (plant.aip_kwh !== null) {
      const aip = pct(plant.aip_kwh, plant.aip_capacity_kwh);
      add("aip", t("uboot_aip"), aip, aip !== null && aip <= 10 ? "caution" : "", unit(aip, "%", 0), false);
    }
  }
  if (air) add("absorber", t("uboot_absorber"), air.absorber_pct, air.absorber_pct <= 25 ? "caution" : "",
    unit(air.absorber_pct, "%", 0), false);
  const hp = pct(ballast.hp_air_bar, ballast.hp_air_max_bar);
  add("hp_air", t("uboot_hp_air"), hp, ballast.blows_left === 0 ? "alarm" : hp !== null && hp < 50 ? "caution" : "",
    unit(ballast.hp_air_bar, "bar", 0), false);
  add("mbt", t("uboot_mbt"), ballast.mbt_pct, ballast.blowing ? "caution" : "", unit(ballast.mbt_pct, "%", 0), false);
  const centred = (value, capacity) => capacity ? Math.max(-100, Math.min(100, value / capacity * 100)) : 0;
  add("regulating", t("uboot_regulating"), centred(ballast.regulating_kg, ballast.regulating_capacity_kg), "",
    `${signed(ballast.regulating_kg / 1000, 1)} t`, true);
  add("trim", t("uboot_lamp_trim_tanks"), centred(ballast.trim_kg, ballast.trim_capacity_kg), "",
    `${signed(ballast.trim_kg / 1000, 1)} t`, true);
  return rows;
}

function renderTanks(payload) {
  const rows = tanks(payload);
  const cells = keyed($("uboot-engine-tanks"), rows.map((row) => row[0]), (key) => {
    const cell = node("div", undefined, "console-tank");
    cell.setAttribute("role", "listitem");
    cell.dataset.key = key;
    const tube = node("span", undefined, "console-tank-tube");
    tube.setAttribute("aria-hidden", "true");
    tube.append(node("span", undefined, "console-tank-fill"));
    cell.append(node("span", undefined, "console-tank-label"), tube, node("strong", undefined, "console-tank-value"));
    return cell;
  });
  rows.forEach(([, label, fill, level, text, centre], index) => {
    const cell = cells[index];
    cell.dataset.level = level;
    cell.dataset.centred = String(centre);
    const value = finite(fill) ? fill : 0;
    // A centred column fills up (+, heavy) or down (-, light) from its middle.
    cell.style.setProperty("--fill", `${centre ? Math.abs(value) / 2 : value}%`);
    cell.dataset.sign = value < 0 ? "minus" : "plus";
    cell.children[0].textContent = label;
    cell.children[2].textContent = text;
  });
}

// Compartment row under the cutaway, stern to bow by CSS order: name, water
// and the teams working in it (the lamps stay for screen readers and tests).
function renderMimic(payload) {
  const dc = payload.damage_control;
  const cells = keyed($("uboot-engine-compartments"), dc.compartments.map((row) => row.name), (name) => {
    const cell = node("div", undefined, "console-room");
    cell.setAttribute("role", "listitem");
    cell.dataset.key = name;
    const water = node("span", undefined, "console-room-water");
    water.setAttribute("aria-hidden", "true");
    const leds = node("div", undefined, "console-room-leds");
    for (const key of ["leak", "fire", "gas", "bulkhead"]) {
      const lamp = node("span", undefined, "console-room-led");
      lamp.dataset.lamp = key;
      leds.append(lamp);
    }
    cell.append(water, node("span", t(`uboot_compartment_${name}`), "console-room-name"),
      node("span", undefined, "console-room-value"), leds, node("span", undefined, "console-room-team"));
    return cell;
  });
  dc.compartments.forEach((row, index) => {
    const cell = cells[index];
    const fill = pct(row.water_kg, row.capacity_kg) ?? 0;
    cell.style.setProperty("--water", `${fill}%`);
    cell.dataset.down = String(row.down);
    cell.children[1].textContent = t(`uboot_compartment_${row.name}`);
    cell.children[2].textContent = row.down ? t("uboot_mimic_down") : t("uboot_mimic_water", {value: number(row.water_kg / 1000, 1)});
    const states = {leak: row.leak_pct > 0 ? "alarm" : "off", fire: row.fire_pct > 0 ? "alarm" : "off",
      gas: row.chlorine_pct > 0 ? "alarm" : "off", bulkhead: row.closed ? "on" : "off"};
    for (const lamp of cell.children[3].children) {
      const key = lamp.dataset.lamp;
      lamp.dataset.level = states[key];
      lamp.textContent = key === "bulkhead" ? t(row.closed ? "uboot_lamp_closed" : "uboot_lamp_open")
        : t(`uboot_lamp_${key}`);
    }
    const teams = dc.teams.filter((team) => team.compartment === row.name).map((team) => String(team.team + 1));
    cell.children[4].textContent = teams.length ? t("uboot_mimic_team", {teams: teams.join(", ")}) : "";
  });
}

function dialSpecs(payload, colors) {
  const nav = payload.navigation, plant = payload.plant, ballast = payload.ballast;
  const ordered = (value) => t("uboot_ordered_value", {value});
  const specs = [
    {label: t("speed"), value: nav.speed, min: 0, max: Math.max(1, nav.max_speed_kn), order: nav.target_speed,
      text: unit(nav.speed, "kn"), sub: ordered(unit(nav.target_speed, "kn"))},
    {label: t("depth"), value: nav.depth_m, min: 0, max: Math.max(50, nav.crush_depth_m), order: nav.target_depth_m,
      zones: [[nav.max_depth_m, nav.crush_depth_m, colors.amber]], text: unit(nav.depth_m, "m", 0),
      sub: ordered(unit(nav.target_depth_m, "m", 0))},
    {label: t("uboot_hp_air"), value: ballast.hp_air_bar, min: 0, max: Math.max(1, ballast.hp_air_max_bar),
      zones: [[0, ballast.hp_air_max_bar * .25, colors.red]], text: unit(ballast.hp_air_bar, "bar", 0),
      sub: t("uboot_engine_blows", {count: ballast.blows_left})},
    {label: t("uboot_trim_angle"), value: ballast.trim_deg, min: -10, max: 10,
      zones: [[-10, -3, colors.amber], [3, 10, colors.amber]], text: `${signed(ballast.trim_deg, 1)}°`,
      sub: t("uboot_engine_drift", {rate: signed(ballast.drift_mps, 2)})},
  ];
  if (plant.propulsion !== "nuclear") {
    const battery = pct(plant.battery_kwh, plant.battery_capacity_kwh);
    const span = Math.max(100, Math.ceil(Math.max(Math.abs(plant.load_kw ?? 0), Math.abs(plant.supply_kw ?? 0)) / 100) * 100);
    specs.splice(1, 0,
      {label: t("uboot_battery"), value: battery, min: 0, max: 100, zones: [[0, 3, colors.red], [3, 20, colors.amber]],
        text: unit(battery, "%", 0), sub: plant.phase ? t(`uboot_phase_${plant.phase.toLowerCase()}`) : ""},
      {label: t("uboot_net"), value: plant.net_kw, min: -span, max: span, zones: [[-span, 0, colors.amber]],
        text: `${signed(plant.net_kw, 0)} kW`, sub: t("uboot_engine_load", {load: number(plant.load_kw, 0), supply: number(plant.supply_kw, 0)})});
  }
  return specs;
}

export function drawUbootEngineDials() {
  const payload = S.v2State?.uboot_engine;
  if (!payload?.plant) return;
  drawDialPanel("uboot-engine-dials", "uboot-engine-dials-text", (colors) => dialSpecs(payload, colors));
  const plot = visualContext("uboot-engine-cutaway");
  if (plot) {
    const dc = payload.damage_control;
    drawBoatSection(plot.context, {x: 4, y: 4, width: plot.width - 8, height: plot.height - 8},
      dc.compartments, dc.teams, payload.ballast.trim_deg, palette());
  }
}

export function renderUbootEngineConsole(payload) {
  if (!payload?.plant || $("uboot-engine-visual").hidden) return;
  renderLamps(payload);
  renderTanks(payload);
  renderMimic(payload);
}
