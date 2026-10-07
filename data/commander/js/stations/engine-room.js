import { S } from "../state/store.js";
import { $, damageStates } from "../core/base.js";
import { enumText, finite, number, t, unit } from "../core/format.js";
import { node } from "../views/dom.js";
import { drawDialPanel, keyed, lampTip, pct, renderLampPanel, signed } from "../views/console-kit.js";

// The frigate's engine-room control console on the stage, like the
// submarine's: an annunciator panel of status lamps, round gauges, the fuel
// bunker and a mimic of the ship's sections. Everything is own-ship truth
// from the engine role's projection; the orders stay in the station dock.

const onOff = (active) => t(active ? "uboot_lamp_on" : "uboot_lamp_off");
// Sections from bow to stern (by their position in the hull), the two
// hull sides as long strips: starboard above, port below (bow on the left).
const SECTIONS = ["sonar", "bridge", "weapons", "opz", "radio", "engine", "flightdeck"];
const SIDES = {hull_right: "starboard", hull_left: "port"};
const stateLevel = (state) => state === "ZERSTOERT" ? "alarm" : state === "OK" ? "on" : "caution";

// A plant lamp chooses its plant: the list takes the mode and its apply
// button sends the order, as a choice in the list would.
const plantSwitch = (mode) => () => {
  const select = $("engine-plant"), apply = $("engine-plant-apply");
  if (!select || !apply || [...select.options].every((option) => option.value !== mode)) return null;
  return {disabled: apply.disabled || select.disabled, hidden: apply.hidden,
    click() { select.value = mode; select.dispatchEvent(new Event("change", {bubbles: true})); apply.click(); }};
};

function lamps(payload) {
  const p = payload.propulsion, m = payload.machinery, e = payload.environment_effects, c = payload.controls;
  const rows = [];
  // Each lamp's hover note from the host (why it shows what it shows).
  const notes = {auto: "plant", diesel: "plant", turbine: "plant", cavitating: "cavitation", teams: "repairs",
    ship_fire: "fires_aboard", ship_flood: "flooded", tas: "sonar"};
  const add = (key, label, level, value, control) => rows.push([key, label, level, value, control, lampTip(notes[key] || key)]);
  const turning = p.speed > .05 || p.telegraph !== "STOP";
  add("shaft", t("engine_lamp_shaft"), turning ? (p.telegraph === "ASTERN" ? "caution" : "on") : "off",
    t(`telegraph_${p.telegraph.toLowerCase()}`));
  add("auto", t("engine_lamp_auto"), p.plant_mode === "AUTO" ? "on" : "off", onOff(p.plant_mode === "AUTO"), plantSwitch("AUTO"));
  add("diesel", t("engine_lamp_diesel"), p.plant_mode === "DIESEL" ? "on" : "off", onOff(p.plant_mode === "DIESEL"), plantSwitch("DIESEL"));
  add("turbine", t("engine_lamp_turbine"), p.plant_mode === "TURBINE" ? "on" : "off", onOff(p.plant_mode === "TURBINE"), plantSwitch("TURBINE"));
  add("quiet", t("quiet_mode"), p.quiet_mode ? "on" : "off", onOff(p.quiet_mode), "engine-quiet");
  add("cavitating", t("uboot_chip_cavitating"), p.cavitating ? "alarm" : "off", onOff(p.cavitating));
  const fuel = pct(p.fuel_kg, p.fuel_capacity_kg);
  add("fuel", t("uboot_lamp_fuel"), fuel === null ? "off" : fuel <= 5 ? "alarm" : fuel <= 20 ? "caution" : "on", unit(fuel, "%", 0));
  const capped = finite(m.effective_speed_cap) && m.effective_speed_cap < c.speed_max_kn - .05;
  add("speed_cap", t("engine_lamp_speed_cap"), capped ? "caution" : "off", unit(m.effective_speed_cap, "kn", 0));
  add("machinery", t("engine_lamp_machinery"), stateLevel(m.station_state), enumText(damageStates, m.station_state));
  add("flooding", t("uboot_flooding"), m.flood >= 50 ? "alarm" : m.flood > 0 ? "caution" : "off", unit(m.flood, "%", 0));
  add("fire", t("uboot_lamp_fire"), m.fire > 0 ? "alarm" : "off", unit(m.fire, "%", 0));
  add("teams", t("engine_lamp_teams"), m.repair_teams.length ? "on" : "off", m.repair_teams.length ? m.repair_teams.join(", ") : onOff(false));
  const rooms = payload.compartments;
  const burning = rooms.filter((row) => row.fire > 0).length, flooding = rooms.filter((row) => row.flood > 0).length;
  add("ship_fire", t("engine_lamp_ship_fire"), burning ? "alarm" : "off", String(burning));
  add("ship_flood", t("engine_lamp_ship_flood"), flooding ? "caution" : "off", String(flooding));
  add("grounded", t("grounded"), m.grounded ? "alarm" : "off", onOff(m.grounded));
  add("tas", t("engine_lamp_tas"), e.tas_available ? "on" : "caution", onOff(e.tas_available));
  add("sea", t("sea_state"), e.sea_state >= 5 ? "caution" : "on", number(e.sea_state, 0));
  add("roll", t("roll"), Math.abs(e.roll) > 15 ? "caution" : "on", `${signed(e.roll, 1)}°`);
  return rows;
}

function engineDialSpecs(payload, colors) {
  const p = payload.propulsion, m = payload.machinery, e = payload.environment_effects, c = payload.controls;
  const fuel = pct(p.fuel_kg, p.fuel_capacity_kg);
  return [
    {label: t("speed"), value: p.speed, min: 0, max: Math.max(1, c.speed_max_kn), order: p.target_speed,
      zones: finite(m.effective_speed_cap) && m.effective_speed_cap < c.speed_max_kn ? [[m.effective_speed_cap, c.speed_max_kn, colors.red]] : [],
      text: unit(p.speed, "kn"), sub: t("uboot_ordered_value", {value: unit(p.target_speed, "kn")})},
    {label: t("rpm"), value: p.rpm, min: 0, max: Math.max(1, c.rpm_max), text: unit(p.rpm, "RPM", 0),
      sub: t(`telegraph_${p.telegraph.toLowerCase()}`)},
    {label: t("noise"), value: m.noise, min: 0, max: Math.max(.1, c.noise_max), zones: [[.85, c.noise_max, colors.red]],
      text: number(m.noise, 2), sub: t(`engine_plant_short_${p.plant_mode.toLowerCase()}`)},
    {label: t("uboot_lamp_fuel"), value: fuel, min: 0, max: 100, zones: [[0, 5, colors.red], [5, 20, colors.amber]],
      text: unit(fuel, "%", 0), sub: unit(p.fuel_burn_kg_h, "kg/h", 0)},
    {label: t("roll"), value: e.roll, min: -30, max: 30, zones: [[-30, -15, colors.amber], [15, 30, colors.amber]],
      text: `${signed(e.roll, 1)}°`, sub: t("engine_sea_value", {sea: number(e.sea_state, 0)})},
    {label: t("pitch"), value: e.pitch, min: -10, max: 10, zones: [[-10, -5, colors.amber], [5, 10, colors.amber]],
      text: `${signed(e.pitch, 1)}°`, sub: ""},
  ];
}

function renderFuel(payload) {
  const p = payload.propulsion, fuel = pct(p.fuel_kg, p.fuel_capacity_kg) ?? 0;
  const tank = $("engine-fuel-tank");
  tank.dataset.level = fuel <= 5 ? "alarm" : fuel <= 20 ? "caution" : "";
  tank.style.setProperty("--fill", `${fuel}%`);
  tank.querySelector(".console-tank-value").textContent = unit(fuel, "%", 0);
  const rows = [["engine_fuel", unit(p.fuel_kg / 1000, "t", 1)], ["engine_fuel_capacity", unit(p.fuel_capacity_kg / 1000, "t", 0)],
    ["engine_fuel_burn", unit(p.fuel_burn_kg_h, "kg/h", 0)], ["engine_endurance", unit(p.fuel_endurance_h, "h", 0)],
    ["engine_range", unit(p.fuel_range_nm, "NM", 0)]];
  const cells = keyed($("engine-fuel-readouts"), rows.map((row) => row[0]), () => {
    const cell = node("div", undefined, "console-readout");
    cell.append(node("span"), node("strong"));
    return cell;
  });
  rows.forEach(([key, value], index) => {
    cells[index].children[0].textContent = t(key);
    cells[index].children[1].textContent = value;
  });
}

function roomCell(key) {
  const cell = node("div", undefined, "console-room");
  cell.setAttribute("role", "listitem");
  cell.dataset.key = key;
  if (SIDES[key]) cell.dataset.side = SIDES[key];
  const water = node("span", undefined, "console-room-water");
  water.setAttribute("aria-hidden", "true");
  const leds = node("div", undefined, "console-room-leds");
  for (const lamp of ["state", "flood", "fire"]) {
    const led = node("span", undefined, "console-room-led");
    led.dataset.lamp = lamp;
    leds.append(led);
  }
  cell.append(water, node("span", t(`engine_room_${key}`), "console-room-name"),
    node("span", undefined, "console-room-value"), leds, node("span", undefined, "console-room-team"));
  return cell;
}

function renderSections(payload) {
  const byKey = new Map(payload.compartments.map((row) => [row.key, row]));
  const order = ["hull_right", ...SECTIONS, "hull_left"].filter((key) => byKey.has(key));
  const cells = keyed($("engine-compartments"), order, roomCell);
  order.forEach((key, index) => {
    const row = byKey.get(key), cell = cells[index];
    cell.style.setProperty("--water", `${Math.max(0, Math.min(100, row.flood))}%`);
    cell.dataset.down = String(row.state === "ZERSTOERT");
    cell.children[1].textContent = t(`engine_room_${key}`);
    cell.children[2].textContent = enumText(damageStates, row.state);
    const levels = {state: stateLevel(row.state), flood: row.flood > 0 ? (row.flood >= 50 ? "alarm" : "caution") : "off",
      fire: row.fire > 0 ? "alarm" : "off"};
    const texts = {state: enumText(damageStates, row.state), flood: t("engine_room_flood", {value: number(row.flood, 0)}),
      fire: t("engine_room_fire", {value: number(row.fire, 0)})};
    for (const lamp of cell.children[3].children) {
      lamp.dataset.level = levels[lamp.dataset.lamp];
      lamp.textContent = texts[lamp.dataset.lamp];
    }
    cell.children[4].textContent = row.teams.length ? t("uboot_mimic_team", {teams: row.teams.join(", ")}) : "";
  });
}

export function drawEngineDials() {
  const payload = S.v2State?.engine;
  if (payload?.propulsion) drawDialPanel("engine-instruments", "engine-instruments-text", (colors) => engineDialSpecs(payload, colors));
}

export function renderEngineConsole(payload) {
  if (!payload?.propulsion || $("engine-visual").hidden) return;
  renderLampPanel($("engine-lamps"), $("engine-master"), lamps(payload));
  renderFuel(payload);
  renderSections(payload);
}
