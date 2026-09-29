import { S } from "../state/store.js";
import { $ } from "../core/base.js";
import { duration, number, stateText, t, unit } from "../core/format.js";
import { actionButton, fillFireTargets, metrics, node, sonarEntries, stationRows, yesNo } from "../views/dom.js";
import { renderCrew } from "../views/crew.js";
import { drawBoatBallast, drawBoatDamage, drawBoatDepth, drawBoatEsm, drawBoatScope } from "./uboot-graphics.js";

// Alarm age with the boat's own measured bearing (never the source's truth).
const alarmText = (age, bearing) => age === null ? t("station_none")
  : bearing === null ? unit(age, "s", 0) : t("uboot_alarm_bearing", {bearing: number(bearing, 0), age: number(age, 0)});

// Telegraph steps as on the uConsole (config.UBOOT_SPEED_STEPS_KN plus the maximum).
export const ubootSpeedSteps = (maximum) => [...[0, 3, 6, 10, 15].filter((speed) => speed < maximum), maximum];

// Every boat station shares one panel; each shows the cards its watch
// operates (data-uboot-stations lists the stations that see an element).
function showStationCards(role) {
  for (const element of document.querySelectorAll("#station-uboot [data-uboot-stations]"))
    element.hidden = !element.dataset.ubootStations.split(" ").includes(role);
  $("station-uboot-title").textContent = t(`station_${role}`);
  document.querySelector("#station-uboot .uboot-grid").dataset.role = role;
}

// The torpedo room: each tube's state, with its load or flood order.
function renderTubes(tubes) {
  $("uboot-tubes").replaceChildren(...(tubes.length ? tubes.map((row, index) => {
    const line = node("p", undefined, "uboot-log-line");
    line.append(node("span", t(`uboot_tube_${row.state}`, {tube: index + 1, seconds: number(row.seconds, 0)})));
    if (row.state === "empty") line.append(actionButton("uboot_tube_load", "uboot_tube_load", {tube: index}));
    if (row.state === "dry") line.append(actionButton("uboot_tube_flood", "uboot_tube_flood", {tube: index}),
      actionButton("uboot_tube_flood_quiet", "uboot_tube_flood_quiet", {tube: index}));
    return line;
  }) : [node("p", t("station_none"), "uboot-log-line")]));
}

// The boat log as compact lines, newest first.
function renderLog(feed) {
  $("uboot-feed").replaceChildren(...(feed.length ? [...feed].reverse().map((row) => {
    const line = node("p", undefined, "uboot-log-line");
    line.append(node("span", t("uboot_log_age", {age: number(row.age_s ?? 0, 0)}), "uboot-log-age"), node("span", row.message));
    return line;
  }) : [node("p", t("station_none"), "uboot-log-line")]));
}

// Large readouts: actual value, the order under it, and a level for colour.
function renderReadouts(nav, status) {
  const battery = status.battery === null ? null : status.battery * 100;
  const heading = (value) => `${number(value, 0).padStart(3, "0")}°`;
  const rows = [
    ["course", heading(nav.course), t("uboot_ordered_value", {value: heading(nav.target_course)}), ""],
    ["speed", unit(nav.speed, "kn"), t("uboot_ordered_value", {value: unit(nav.target_speed, "kn")}), nav.cavitating ? "alarm" : ""],
    ["depth", unit(nav.depth_m, "m", 0), t("uboot_ordered_value", {value: unit(nav.target_depth_m, "m", 0)}), ""],
    ["uboot_battery", battery === null ? t("unavailable") : unit(battery, "%", 0), status.endurance_phase ? t(`uboot_phase_${status.endurance_phase.toLowerCase()}`) : "",
      battery !== null && battery <= 3 ? "alarm" : battery !== null && battery <= 20 ? "caution" : ""],
  ];
  const box = $("uboot-readouts");
  if (box.children.length !== rows.length) {
    box.replaceChildren(...rows.map(() => {
      const cell = node("div", undefined, "uboot-readout");
      cell.append(node("span", undefined, "uboot-readout-label"), node("strong"), node("span", undefined, "uboot-readout-sub"));
      return cell;
    }));
  }
  rows.forEach(([key, value, sub, level], index) => {
    const cell = box.children[index];
    cell.dataset.level = level;
    cell.children[0].textContent = t(key);
    cell.children[1].textContent = value;
    cell.children[2].textContent = sub;
  });
  // The battery cell carries a fill gauge.
  box.children[3].dataset.gauge = "true";
  box.children[3].style.setProperty("--fill", battery === null ? "0%" : `${Math.max(0, Math.min(100, battery))}%`);
}

// Mode and alarm chips: lit when active, coloured by urgency.
function renderChips(nav, status, alarms, scope) {
  const modes = [
    ["uboot_chip_silent", status.silent, status.quiet ? "on" : "caution"],
    ["uboot_chip_snorkel", status.snorkeling, "caution"],
    ["uboot_chip_mast", status.mast, "caution"],
    ["uboot_chip_scope", scope.available, "caution"],
    ["uboot_chip_bottom", status.bottomed, "on"],
    ["uboot_chip_cavitating", nav.cavitating, "alarm"],
    ["uboot_chip_transmitting", status.transmitting, "caution"],
  ];
  const rows = modes.map(([key, active, level]) => [t(key), active ? level : "off"]);
  if (nav.depth_m > nav.max_depth_m)
    rows.push([t("uboot_chip_overdepth", {test: number(nav.max_depth_m, 0), crush: number(nav.crush_depth_m, 0)}), "alarm"]);
  if (alarms.torpedo_age_s !== null && alarms.torpedo_age_s < 120)
    rows.push([t("uboot_chip_torpedo", {value: alarmText(alarms.torpedo_age_s, alarms.torpedo_bearing)}), "alarm"]);
  if (alarms.ping_age_s !== null && alarms.ping_age_s < 120)
    rows.push([t("uboot_chip_ping", {value: alarmText(alarms.ping_age_s, alarms.ping_bearing)}), "caution"]);
  if (alarms.esm.length) rows.push([t("uboot_chip_esm", {count: alarms.esm.length}), "caution"]);
  $("uboot-chips").replaceChildren(...rows.map(([text, level]) => {
    const chip = node("span", text, "uboot-chip");
    chip.dataset.level = level;
    return chip;
  }));
}

// Paired on/off orders: the button of the current state is pressed and not offered again.
function renderModePairs(nav, status, ballast) {
  const state = {uboot_silent: status.silent, uboot_snorkel: status.snorkeling, uboot_mast: status.mast,
    uboot_bottom: status.bottomed, uboot_trim_auto: ballast.auto};
  const possible = {uboot_snorkel: status.snorkel_available,
    uboot_mast: status.mast || nav.depth_m <= (nav.depth_presets.periscope ?? 0) + 3.5};
  for (const button of document.querySelectorAll("#station-uboot [data-uboot-mode]")) {
    const mode = button.dataset.ubootMode, enabled = button.dataset.enabled === "true";
    button.setAttribute("aria-pressed", String(state[mode] === enabled));
    button.dataset.ready = String(state[mode] !== enabled && (!enabled || (possible[mode] ?? true)));
  }
}

// One-step depth orders; a preset without its basis (snorkel, BT) is not offered.
function renderPresets(nav) {
  for (const button of document.querySelectorAll("#station-uboot [data-uboot-depth-preset]")) {
    const depth = nav.depth_presets[button.dataset.ubootDepthPreset];
    button.dataset.depth = depth === null ? "" : String(Math.round(depth));
    button.dataset.ready = String(depth !== null);
    button.textContent = t(`uboot_preset_${button.dataset.ubootDepthPreset}`,
      {depth: depth === null ? "--" : number(depth, 0)});
    button.setAttribute("aria-pressed", String(depth !== null && Math.abs(nav.target_depth_m - Math.round(depth)) < 1));
  }
}

// The attack computer's estimate on one sighting: course, speed, lead and run.
function solutionText(solution, heading) {
  if (!solution) return t("station_none");
  if (solution.course === null) return t("uboot_solution_marks", {marks: solution.marks});
  const course = heading(solution.course), speed = unit(solution.speed_kn, "kn", 0);
  if (solution.lead_deg === null) return t("uboot_solution_no_intercept", {course, speed});
  const total = Math.round(solution.run_s);
  const run = `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
  return t("uboot_solution_value", {course, speed, lead: `${number(solution.lead_deg, 0)}\u00b0`,
    run, marks: solution.marks});
}

// The periscope: line of sight and light, its controls, and the crew's sightings.
function renderScope(payload) {
  const scope = payload.scope;
  const heading = (value) => `${number(value, 0).padStart(3, "0")}\u00b0`;
  const digits = (value) => number(value, 0).padStart(3, "0");
  $("uboot-scope-status").textContent = scope.available
    ? `${t("uboot_scope_bearing", {bearing: digits(scope.bearing), relative: digits(scope.relative_deg)})} \u00b7 ${t("uboot_scope_conditions", {
      light: t(scope.night ? "uboot_scope_night" : "uboot_scope_day"), visibility: number(scope.visibility_nm, 0), sea: number(scope.sea_state, 0)})}`
    : t("uboot_scope_mast_down");
  for (const button of document.querySelectorAll("[data-uboot-scope-turn]")) button.dataset.ready = String(scope.available);
  const inWindow = scope.available && scope.sightings.some((row) => row.age_s !== null && row.age_s <= 1 &&
    Math.abs(((row.bearing - scope.bearing + 540) % 360) - 180) <= scope.window_deg && row.cls !== "aircraft" && row.cls !== "torpedo");
  $("uboot-scope-mark").dataset.ready = String(inWindow);
  $("uboot-scope-fire").dataset.ready = String(inWindow && scope.sightings.some((row) => row.solution
    && row.solution.lead_deg !== null && row.age_s !== null && row.age_s <= 1
    && Math.abs(((row.bearing - scope.bearing + 540) % 360) - 180) <= scope.window_deg));
  if (!S.stationDrafts.has("uboot-scope-relative")) $("uboot-scope-relative").value = String(Math.round(scope.relative_deg));
  const rows = [...scope.sightings].sort((a, b) => Math.abs(((a.bearing - scope.bearing + 540) % 360) - 180) - Math.abs(((b.bearing - scope.bearing + 540) % 360) - 180));
  stationRows($("uboot-sightings"), rows, (row) => [["reference", heading(row.bearing)],
    ["uboot_sighting_class", t(`uboot_sighting_${row.cls}`)], ["uboot_sighting_span", unit(row.span_deg * 60, "\u2032", 0)],
    ["quality", number(row.quality, 2)], ["age", unit(row.age_s, "s", 0)],
    ["uboot_sighting_range", row.range_nm === null ? t("station_none")
      : `${unit(row.range_nm, "NM")} \u00b1${unit(row.range_sigma_nm, "NM")} (${unit(row.range_age_s, "s", 0)})`],
    ["uboot_sighting_solution", solutionText(row.solution, heading)]],
  scope.available ? "uboot_no_sighting" : "uboot_scope_mast_down");
  drawBoatScope("uboot-scope-canvas", payload);
  drawBoatBallast("uboot-ballast-canvas", payload);
}

// Energy and stores: bars, energy balance, endurance dived by speed and the boat's air.
const percent = (value, capacity) => value === null || !capacity ? null : Math.max(0, Math.min(100, value / capacity * 100));
// Tanks, trim and air bottles: the engineer's numbers and the crew's orders.
const tonnes = (kg) => `${kg > 0 ? "+" : ""}${number(kg / 1000, 1)}`;
function renderBallast(ballast) {
  const mbt = ballast.blowing ? "uboot_mbt_blowing" : ballast.venting ? "uboot_mbt_venting"
    : ballast.mbt_pct >= 100 ? "uboot_mbt_dived" : "uboot_mbt_blown";
  const residual = ballast.residual_kg, weight = number(Math.abs(residual) / 1000, 1);
  const heavy = residual > 20 ? t("uboot_heavy", {weight}) : residual < -20 ? t("uboot_light", {weight}) : t("uboot_neutral");
  metrics($("uboot-ballast"), [
    ["uboot_mbt", t(mbt, {pct: number(ballast.mbt_pct, 0)})],
    ["uboot_hp_air", t(ballast.compressor ? "uboot_hp_air_compressor" : "uboot_hp_air_value",
      {bar: number(ballast.hp_air_bar, 0), max: number(ballast.hp_air_max_bar, 0), blows: ballast.blows_left})],
    ["uboot_trim_auto", t(ballast.auto ? "uboot_trim_auto_on" : "uboot_trim_auto_off")],
    ["uboot_regulating", t("uboot_tank_value", {value: tonnes(ballast.regulating_kg), order: tonnes(ballast.regulating_order_kg)})],
    ["uboot_trim_tanks", t("uboot_tank_value", {value: tonnes(ballast.trim_kg), order: tonnes(ballast.trim_order_kg)})],
    ["uboot_weight", heavy], ["uboot_trim_angle", t("uboot_trim_angle_value", {angle: `${ballast.trim_deg > 0 ? "+" : ""}${number(ballast.trim_deg, 1)}`})],
    ["uboot_drift", t("uboot_drift_value", {rate: `${ballast.drift_mps > 0 ? "+" : ""}${number(ballast.drift_mps, 2)}`})],
    ["uboot_flooding", unit(ballast.flooding_kg / 1000, "t", 1)],
    ["uboot_pumps", t(ballast.pumping ? "uboot_pumps_on" : "uboot_pumps_off")]]);
  const warnings = [];
  if (Math.abs(residual) > 2000) warnings.push(t(residual > 0 ? "uboot_ballast_warning_heavy" : "uboot_ballast_warning_light", {weight}));
  if (Math.abs(ballast.trim_deg) > 3) warnings.push(t("uboot_ballast_warning_angle", {angle: number(ballast.trim_deg, 1)}));
  if (ballast.blows_left === 0) warnings.push(t("uboot_ballast_warning_air"));
  $("uboot-ballast-warning").hidden = warnings.length === 0;
  $("uboot-ballast-warning").textContent = warnings.join(" ");
  $("uboot-ballast").dataset.level = warnings.length ? "caution" : "ok";
  for (const button of document.querySelectorAll("[data-uboot-ballast]")) {
    const regulating = button.dataset.ubootBallast === "regulating", up = button.dataset.direction === "1";
    const order = regulating ? ballast.regulating_order_kg : ballast.trim_order_kg;
    const capacity = regulating ? ballast.regulating_capacity_kg : ballast.trim_capacity_kg;
    button.dataset.ready = String(up ? order < capacity : order > -capacity);
  }
}

// Damage control: one row per compartment (water, leak, fire, gas, the
// bulkhead switch), the two teams and the power.
function renderDamage(dc) {
  const pct = (value) => number(value, 0);
  $("uboot-dc-rows").replaceChildren(...dc.compartments.map((row) => {
    const line = document.createElement("tr");
    line.dataset.down = String(row.down);
    line.dataset.alert = String(row.fire_pct > 0 || row.leak_pct > 0 || row.chlorine_pct > 0);
    const bulkhead = node("button", t(row.closed ? "uboot_dc_bulkhead_open" : "uboot_dc_bulkhead_close"));
    bulkhead.type = "button";
    bulkhead.dataset.ubootBulkhead = row.name;
    bulkhead.dataset.closed = String(!row.closed);
    bulkhead.setAttribute("aria-pressed", String(row.closed));
    bulkhead.setAttribute("aria-label", t(row.closed ? "uboot_dc_bulkhead_open_label" : "uboot_dc_bulkhead_close_label",
      {compartment: t(`uboot_compartment_${row.name}`)}));
    const switchCell = document.createElement("td");
    switchCell.append(bulkhead);
    const teams = dc.teams.filter((team) => team.compartment === row.name).map((team) => String(team.team + 1));
    const name = node("th", t(`uboot_compartment_${row.name}`));
    name.scope = "row";
    line.append(name, ...[number(row.water_kg / 1000, 1), pct(row.leak_pct), pct(row.fire_pct), pct(row.chlorine_pct),
      teams.length ? teams.join(", ") : "\u2013"].map((text) => node("td", text)), switchCell);
    return line;
  }));
  renderCrew($("uboot-crew"), $("uboot-crew-actions"), dc.crew,
    {actionStations: "uboot_action_stations", watchChange: "uboot_watch_change",
      medic: "uboot_casualty_medic", reassign: "uboot_casualty_reassign"});
  metrics($("uboot-dc-teams"), [["uboot_dc_power", t(dc.power ? "uboot_dc_power_on" : "uboot_dc_power_off")],
    ...dc.teams.map((team) => [`uboot_dc_team_${team.team + 1}`, team.transit_s > 0
      ? t("uboot_dc_team_transit", {compartment: t(`uboot_compartment_${team.compartment}`), seconds: number(team.transit_s, 0)})
      : t("uboot_dc_team_at", {compartment: t(`uboot_compartment_${team.compartment}`), task: t(`uboot_dc_task_${team.task}`)})])]);
  const warnings = [];
  if (!dc.power) warnings.push(t("uboot_dc_warning_power"));
  const burning = dc.compartments.filter((row) => row.fire_pct > 0).map((row) => t(`uboot_compartment_${row.name}`));
  if (burning.length) warnings.push(t("uboot_dc_warning_fire", {compartments: burning.join(", ")}));
  const leaking = dc.compartments.filter((row) => row.leak_pct > 0).map((row) => t(`uboot_compartment_${row.name}`));
  if (leaking.length) warnings.push(t("uboot_dc_warning_leak", {compartments: leaking.join(", ")}));
  if (dc.compartments.some((row) => row.chlorine_pct > 0)) warnings.push(t("uboot_dc_warning_gas"));
  $("uboot-dc-warning").hidden = warnings.length === 0;
  $("uboot-dc-warning").textContent = warnings.join(" ");
}

function renderSupply(plant) {
  const air = plant.air;
  const bars = [["uboot_battery", percent(plant.battery_kwh, plant.battery_capacity_kwh), 20, 3,
    plant.battery_kwh === null ? null : `${number(plant.battery_kwh, 0)} / ${unit(plant.battery_capacity_kwh, "kWh", 0)}`]];
  if (plant.aip_kwh !== null) bars.push(["uboot_aip", percent(plant.aip_kwh, plant.aip_capacity_kwh), 10, 0,
    `${number(plant.aip_kwh, 0)} / ${unit(plant.aip_capacity_kwh, "kWh", 0)}`]);
  if (plant.fuel_l !== null) bars.push(["uboot_fuel", percent(plant.fuel_l, plant.fuel_capacity_l), 10, 0,
    `${number(plant.fuel_l / 1000, 1)} / ${unit(plant.fuel_capacity_l / 1000, "m\u00b3", 1)}`]);
  if (air) bars.push(["uboot_absorber", air.absorber_pct, 25, 0, t("uboot_absorber_value", {pct: number(air.absorber_pct, 0), sets: air.absorber_sets})]);
  const box = $("uboot-supply-bars");
  box.replaceChildren(...(plant.propulsion === "nuclear" ? [node("p", t("uboot_nuclear_plant"), "uboot-bar-note")] : bars.map(([key, fill, caution, alarm, text]) => {
    const bar = node("div", undefined, "uboot-bar");
    bar.dataset.level = fill === null ? "" : fill <= alarm ? "alarm" : fill <= caution ? "caution" : "";
    bar.style.setProperty("--fill", `${fill ?? 0}%`);
    bar.append(node("span", t(key), "uboot-bar-label"), node("strong", fill === null ? t("unavailable") : unit(fill, "%", 0)), node("span", text ?? "", "uboot-bar-sub"));
    return bar;
  })));
  const nuclear = plant.propulsion === "nuclear";
  // A nuclear boat has no battery forecast, diesel or air stores to order.
  const role = S.v2State?.role || "uboot";
  for (const id of ["uboot-charge-rates", "uboot-endurance-section", "uboot-air-orders"])
    $(id).hidden = nuclear || (id !== "uboot-endurance-section" && role !== "uboot_engine");
  metrics($("uboot-energy"), nuclear ? [["uboot_plant_kind", t("uboot_plant_nuclear")]] : [
    ["uboot_plant_kind", t(`uboot_plant_${plant.propulsion}`)], ["uboot_endurance_phase", plant.phase ? t(`uboot_phase_${plant.phase.toLowerCase()}`) : t("unavailable")],
    ["uboot_load", unit(plant.load_kw, "kW", 0)], ["uboot_supply", unit(plant.supply_kw, "kW", 0)],
    ["uboot_net", `${plant.net_kw > 0 ? "+" : ""}${unit(plant.net_kw, "kW", 0)}`],
    [plant.full_s !== null ? "uboot_battery_full_in" : "uboot_battery_empty_in", duration(plant.full_s ?? plant.empty_s)],
    ["uboot_generator", unit(plant.generator_kw, "kW", 0)], ["uboot_charge_rate", t(`uboot_charge_${plant.charge_rate}`)],
    ["uboot_snorkel_rate", t(`uboot_charge_${plant.snorkel_rate}`)],
    ...(plant.aip_kw !== null ? [["uboot_aip_power", unit(plant.aip_kw, "kW", 0)]] : [])]);
  for (const button of document.querySelectorAll("[data-uboot-charge-rate]")) {
    button.setAttribute("aria-pressed", String(plant.charge_rate === button.dataset.ubootChargeRate));
    button.dataset.ready = String(!nuclear && plant.charge_rate !== button.dataset.ubootChargeRate);
  }
  const body = $("uboot-endurance");
  body.replaceChildren(...(nuclear ? [] : plant.endurance.map((row) => {
    const line = document.createElement("tr");
    line.append(node("th", unit(row.speed_kn, "kn", 0)), node("td", row.hours === null ? "\u221e" : row.hours >= 9999 ? "> 9999 h" : unit(row.hours, "h", 1)),
      node("td", row.hours === null || row.hours >= 9999 ? "\u221e" : unit(row.speed_kn * row.hours, "NM", 0)));
    line.firstChild.scope = "row";
    return line;
  })));
  metrics($("uboot-air"), air ? [["uboot_o2", unit(air.o2_pct, "%", 1)], ["uboot_co2", unit(air.co2_pct, "%", 2)],
    ["uboot_air_level", t(`uboot_air_${air.level}`)], ["uboot_crew_efficiency", unit(air.efficiency * 100, "%", 0)],
    ["uboot_absorber_sets", number(air.absorber_sets, 0)], ["uboot_candles", number(air.candles, 0)],
    ["uboot_candle_burning", air.candle_left_s > 0 ? duration(air.candle_left_s) : t("no")]]
    : [["uboot_air_level", t("uboot_air_nuclear")]]);
  $("uboot-air").dataset.level = air?.level ?? "ok";
  $("uboot-absorber").dataset.ready = String(!!air && air.absorber_sets > 0);
  $("uboot-o2-candle").dataset.ready = String(!!air && air.candles > 0 && air.candle_left_s <= 0);
  const warning = air && air.level !== "ok" ? t(`uboot_air_warning_${air.level}`)
    : plant.fuel_l !== null && plant.fuel_capacity_l && plant.fuel_l <= plant.fuel_capacity_l * .1 ? t("uboot_fuel_low") : "";
  $("uboot-air-warning").hidden = !warning;
  $("uboot-air-warning").textContent = warning;
}

// The mast station's ESM picture: mast time, the crew's emitter list and
// the selected emitter's evaluation (classification, cross-fix, plot).
const bandText = (band) => String(band || "").toUpperCase().replace("_", "/");
const bearingText = (value) => `${number(value, 0).padStart(3, "0")}\u00b0`;
const esmSelected = (esm) => esm.emitters.find((row) => row.number === S.ubootEsmSelected) || null;
const trendText = (row) => row.trend === null ? "\u2013"
  : `${t(`uboot_esm_trend_${row.trend}`)} ${number(row.trend_db_min, 1)}`;
const fixText = (fix) => fix === null ? "\u2013" : t("uboot_esm_fix_value",
  {x: number(fix.x, 1), y: number(fix.y, 1), major: number(fix.major_nm, 1), minor: number(fix.minor_nm, 1)});
function renderEsm(esm, status) {
  const over = esm.mast_up && esm.mast_s > esm.mast_time_s;
  const mast = $("uboot-esm-mast");
  mast.dataset.level = esm.mast_threat ? "alarm" : over ? "caution" : "ok";
  metrics(mast, [["uboot_mast", yesNo(status.mast)],
    ["uboot_esm_mast_time", esm.mast_up ? t("uboot_esm_mast_time_value", {elapsed: number(esm.mast_s, 0), limit: number(esm.mast_time_s, 0)})
      : t("uboot_esm_mast_time_limit", {limit: number(esm.mast_time_s, 0)})],
    ["uboot_esm_mast_radar", unit(esm.mast_radar_nm, "NM")],
    ["uboot_esm_wash", unit(esm.wash * 100, "%", 0)]]);
  const warning = esm.mast_threat ? t("uboot_esm_threat_warning") : over ? t("uboot_esm_overtime_warning") : "";
  $("uboot-esm-warning").hidden = !warning;
  $("uboot-esm-warning").textContent = warning;
  if (!esmSelected(esm)) S.ubootEsmSelected = esm.emitters[0]?.number ?? null;
  $("uboot-esm-emitters").replaceChildren(...esm.emitters.map((row) => {
    const line = document.createElement("tr");
    line.dataset.live = String(row.live);
    line.dataset.threat = String(row.mast_threat);
    line.setAttribute("aria-selected", String(row.number === S.ubootEsmSelected));
    const pick = node("button", row.label);
    pick.type = "button";
    pick.dataset.ubootEsmEmitter = String(row.number);
    pick.setAttribute("aria-label", t("uboot_esm_select", {label: row.label}));
    const first = document.createElement("td");
    first.append(pick);
    line.append(first, ...[bearingText(row.bearing), bandText(row.band),
      number(row.signal_db, 0), trendText(row), row.classification ? row.classification.name : "\u2013",
      row.fix ? unit(row.fix.major_nm, "NM") : "\u2013"].map((text) => node("td", text)));
    return line;
  }));
  $("uboot-esm-empty").hidden = esm.emitters.length > 0;
  $("uboot-esm-empty").textContent = status.mast ? t("uboot_esm_none") : t("uboot_esm_mast_down");
  const row = esmSelected(esm);
  $("uboot-esm-detail").hidden = row === null;
  if (row === null) return;
  $("uboot-esm-detail-title").textContent = t("uboot_esm_detail_title", {label: row.label});
  metrics($("uboot-esm-detail-metrics"), [
    ["bearing", `${bearingText(row.bearing)} \u00b1${number(row.bearing_uncertainty_deg, 1)}`],
    ["frequency", unit(row.frequency_hz / 1e9, "GHz", 2)], ["uboot_esm_col_band", bandText(row.band)],
    ["prf", row.prf_hz === null ? t("unavailable") : unit(row.prf_hz, "Hz", 0)],
    ["modulation", stateText("uboot_esm_mod", row.modulation)],
    ["uboot_esm_col_level", unit(row.signal_db, "dB", 0)], ["uboot_esm_col_trend", trendText(row)],
    ["age", unit(row.age_s, "s", 0)],
    ["uboot_esm_range", t("uboot_esm_range_value", {range: number(row.range_estimate_nm, 1)})],
    ["uboot_esm_scan", row.scan === null ? t("uboot_esm_scan_measuring")
      : t(`uboot_esm_scan_${row.scan}`, {period: number(row.scan_period_s, 1)})],
    ["uboot_esm_col_fix", row.fix ? fixText(row.fix) : t("uboot_esm_no_fix")],
    ["uboot_esm_fix_state", row.fix === null ? t("unavailable") : t(row.fix.consistent ? "uboot_esm_fix_consistent" : "uboot_esm_fix_inconsistent", {lines: row.fix.lines})],
    ["uboot_esm_col_class", row.classification ? `${row.classification.name} (${stateText("uboot_esm_role", row.classification.role)}, ${t(`uboot_esm_fit_${row.classification.fit}`)})` : t("uboot_esm_unclassified")]]);
  const select = $("uboot-esm-class");
  if (!S.stationDrafts.has("uboot-esm-class") || select.dataset.emitter !== String(row.number)) {
    S.stationDrafts.delete("uboot-esm-class");
    select.dataset.emitter = String(row.number);
    const options = [Object.assign(document.createElement("option"), {value: "-1", textContent: t("uboot_esm_unclassified")}),
      ...row.candidates.map((candidate, index) => Object.assign(document.createElement("option"),
        {value: String(index), textContent: `${candidate.name} (${stateText("uboot_esm_role", candidate.role)}, ${t(`uboot_esm_fit_${candidate.fit}`)})`}))];
    select.replaceChildren(...options);
    const current = row.classification ? row.candidates.findIndex((candidate) =>
      candidate.name === row.classification.name && candidate.role === row.classification.role) : -1;
    select.value = String(current);
  }
  $("uboot-esm-plot").textContent = t(row.fix ? "uboot_esm_to_plot_fix" : "uboot_esm_to_plot_bearing");
}

// Counter-detection picture: the boat's own intercepts, layer and noise,
// and the evasion order the button gives (own measurements only).
// Radio room: HQ broadcast schedule, own situation reports and HQ's contact
// report (modelled intelligence with its age and error circle).
function radioReportText(report, nav) {
  const dx = report.x - nav.x, dy = report.y - nav.y;
  const bearing = (Math.atan2(dx, -dy) * 180 / Math.PI + 360) % 360;
  return t("uboot_radio_report_value", {bearing: number(bearing, 0), range: number(Math.hypot(dx, dy), 1),
    radius: number(report.radius_nm, 0), course: number(report.course, 0), speed: number(report.speed_kn, 0),
    age: number((report.age_s ?? 0) / 60, 0)});
}

function radioLogText(row) {
  const age = duration(row.age_s);
  if (row.type === "broadcast") {
    const text = t(row.report ? "uboot_radio_log_broadcast_report" : "uboot_radio_log_broadcast", {age, number: row.number});
    const acked = row.ack ? t("uboot_radio_log_with_ack", {entry: text}) : text;
    return row.order !== null ? t("uboot_radio_log_with_order", {entry: acked, number: row.order}) : acked;
  }
  return row.type === "sent" ? t("uboot_radio_log_sent", {age, number: row.number}) : t("uboot_radio_log_aborted", {age});
}

function radioOrderText(radio, nav) {
  const order = radio.order;
  if (order === null) return t("uboot_radio_order_none");
  const left = duration(order.left_s);
  if (order.type !== "area") return t(`uboot_radio_order_${order.type}`, {number: order.id, left});
  const dx = order.x - nav.x, dy = order.y - nav.y;
  return t("uboot_radio_order_area", {number: order.id, left, radius: number(order.radius_nm, 0),
    bearing: number((Math.atan2(dx, -dy) * 180 / Math.PI + 360) % 360, 0), range: number(Math.hypot(dx, dy), 1)});
}

function renderRadio(radio, nav) {
  const broadcast = radio.copied ? t("uboot_radio_copied", {number: radio.broadcast})
    : radio.copy !== null ? t("uboot_radio_copying", {number: radio.broadcast, percent: number(radio.copy * 100, 0)})
    : t("uboot_radio_missed", {number: radio.broadcast});
  metrics($("uboot-radio"), [
    ["uboot_radio_antenna", t(radio.antenna ? "uboot_radio_antenna_up" : radio.vlf ? "uboot_radio_vlf" : "uboot_radio_antenna_down")],
    ["uboot_radio_broadcast", broadcast], ["uboot_radio_next", duration(radio.next_s)],
    ["uboot_radio_sitreps", t(radio.ack_due ? "uboot_radio_sitreps_ack" : "uboot_radio_sitreps_value", {count: radio.sitreps})]]);
  $("uboot-radio-warning").hidden = !radio.transmitting;
  $("uboot-radio-warning").textContent = t("uboot_radio_on_air", {percent: number((radio.send ?? 0) * 100, 0)});
  $("uboot-radio-send").dataset.ready = String(radio.antenna && !radio.transmitting);
  $("uboot-radio-status").textContent = radio.antenna ? "" : t("uboot_radio_need_antenna");
  metrics($("uboot-radio-report"), [["uboot_radio_report", radio.report ? radioReportText(radio.report, nav) : t("uboot_radio_no_report")],
    ["uboot_radio_order", radioOrderText(radio, nav)],
    ["uboot_radio_orders", t("uboot_radio_orders_value", {done: radio.orders_done, failed: radio.orders_failed})]]);
  $("uboot-radio-log").replaceChildren(...(radio.log.length ? radio.log.map((row) => node("p", radioLogText(row), "uboot-log-line"))
    : [node("p", t("uboot_radio_log_empty"), "uboot-log-line")]));
}

function renderThreat(threat) {
  const counts = threat.counts;
  metrics($("uboot-threat"), [
    ["uboot_threat_pings", t("uboot_threat_pings_value", {hull: counts.hull, dipping: counts.dipping, buoy: counts.buoy})],
    ["uboot_threat_loudest", threat.loudest_db === null ? t("station_none")
      : `${unit(threat.loudest_db, "dB", 0)} ${t(threat.echo_likely ? "uboot_threat_echo_likely" : "uboot_threat_echo_unlikely")}`],
    ["uboot_threat_trend", t(`uboot_threat_trend_${threat.trend || "none"}`)],
    ["uboot_threat_other", t("uboot_threat_other_value", {splash: counts.splash, torpedo: counts.torpedo, esm: threat.esm_count})],
    ["uboot_threat_layer", t(`uboot_threat_layer_${threat.layer}`, {depth: number(threat.depth_m, 0), layer: threat.layer_m === null ? "-" : number(threat.layer_m, 0)})],
    ["uboot_threat_noise", t(`uboot_threat_noise_${threat.noise}`)]]);
  $("uboot-threat-warning").hidden = !threat.echo_likely && counts.torpedo === 0;
  $("uboot-threat-warning").textContent = counts.torpedo ? t("uboot_threat_torpedo_warning") : t("uboot_threat_echo_warning");
  const advice = threat.advice.map((key) => node("p", t(key.replaceAll(".", "_")), "uboot-log-line"));
  $("uboot-threat-advice").replaceChildren(...(advice.length ? advice : [node("p", t("uboot_advice_none"), "uboot-log-line")]));
  const plan = threat.plan;
  $("uboot-evade").dataset.ready = String(plan !== null);
  $("uboot-evade-plan").textContent = plan === null ? t("uboot_evade_no_plan")
    : t("uboot_evade_plan", {course: number(plan.course, 0), speed: number(plan.speed_kn, 0), depth: number(plan.depth_m, 0),
      source: t(`uboot_threat_kind_${plan.type}`)});
  $("uboot-threat-intercepts").replaceChildren(...(threat.intercepts.length ? threat.intercepts.map((row) => {
    const line = node("p", undefined, "uboot-log-line");
    line.append(node("span", t("uboot_log_age", {age: number(row.age_s, 0)}), "uboot-log-age"),
      node("span", row.level_db === null
        ? t("uboot_threat_row_bearing", {kind: t(`uboot_threat_kind_${row.type}`), bearing: number(row.bearing, 0)})
        : t("uboot_threat_row", {kind: t(`uboot_threat_kind_${row.type}`), bearing: number(row.bearing, 0),
          level: number(row.level_db, 0)})));
    return line;
  }) : [node("p", t("station_none"), "uboot-log-line")]));
}

export function renderUbootStation(payload) {
  showStationCards(S.v2State?.role || "uboot");
  const nav = payload.navigation, status = payload.status, weapons = payload.weapons, alarms = payload.alarms;
  renderReadouts(nav, status);
  renderChips(nav, status, alarms, payload.scope);
  renderModePairs(nav, status, payload.ballast);
  renderPresets(nav);
  metrics($("uboot-navigation"), [
    ["uboot_under_keel", unit(nav.under_keel_m, "m", 0)],
    ["uboot_obstacle_ahead", nav.obstacle_ahead_nm === null ? t("station_none") : unit(nav.obstacle_ahead_nm, "NM")],
    ["uboot_water_depth", unit(nav.water_depth_m, "m", 0)], ["uboot_safe_depth", unit(nav.safe_depth_m, "m", 0)],
    ["uboot_layer", nav.depth_presets.layer === null ? t("uboot_layer_unknown") : unit(nav.depth_presets.layer, "m", 0)]]);
  // Chart check along the ordered course and water under the keel.
  const obstacle = nav.obstacle_ahead_nm !== null && nav.target_speed > 0;
  const shallow = nav.under_keel_m !== null && nav.under_keel_m < 15 && !status.bottomed;
  $("uboot-nav-warning").hidden = !obstacle && !shallow;
  $("uboot-nav-warning").textContent = obstacle ? t("uboot_obstacle_warning", {distance: number(nav.obstacle_ahead_nm, 1)})
    : shallow ? t("uboot_shallow_warning", {depth: number(nav.under_keel_m, 0)}) : "";
  const steps = ubootSpeedSteps(nav.max_speed_kn);
  for (const button of document.querySelectorAll("[data-uboot-speed-step]")) {
    // Six buttons: stop, the intermediate steps below the maximum, then AK.
    const index = Number(button.dataset.ubootSpeedStep);
    const step = index === 5 ? steps.length - 1 : index;
    button.hidden = index !== 5 && index >= steps.length - 1;
    button.dataset.speed = String(steps[step]);
    button.textContent = t(`uboot_step_${index}`, {speed: number(steps[step], 0)});
    button.setAttribute("aria-pressed", String(Math.abs(nav.target_speed - steps[step]) < .05));
  }
  metrics($("uboot-status"), [["state", t(`uboot_state_${status.state}`)], ["uboot_damage", unit(status.damage, "%", 0)],
    ["uboot_noise", number(nav.noise, 2)], ["uboot_quiet", yesNo(status.quiet)],
    ["uboot_blow_available", `${yesNo(status.blow_available)} (${t("uboot_hp_air_value", {bar: number(payload.ballast.hp_air_bar, 0), max: number(payload.ballast.hp_air_max_bar, 0), blows: payload.ballast.blows_left})})`], ["uboot_emergency_ascent", yesNo(status.emergency_ascent)]]);
  metrics($("uboot-weapon-status"), [["torpedoes", number(weapons.torpedoes, 0)],
    ["uboot_tubes_ready", number(weapons.tubes_ready, 0)], ["reload", unit(weapons.reload_s, "s", 0)],
    ["uboot_decoys", number(weapons.decoys, 0)],
    ["uboot_torpedo_alarm", alarmText(alarms.torpedo_age_s, alarms.torpedo_bearing)]]);
  renderTubes(weapons.tubes);
  metrics($("uboot-alarms"), [
    ["uboot_ping_heard", alarmText(alarms.ping_age_s, alarms.ping_bearing)],
    ["uboot_torpedo_alarm", alarmText(alarms.torpedo_age_s, alarms.torpedo_bearing)]]);
  renderEsm(payload.esm, status);
  renderThreat(payload.threat);
  renderRadio(payload.radio, nav);
  document.body.classList.toggle("uboot-torpedo-alarm", alarms.torpedo_age_s !== null && alarms.torpedo_age_s < 60);
  if (!S.stationDrafts.has("uboot-depth")) $("uboot-depth").max = String(Math.floor(nav.crush_depth_m));
  if (!S.stationDrafts.has("uboot-speed")) $("uboot-speed").max = String(nav.max_speed_kn);
  $("uboot-decoy").dataset.ready = String(weapons.decoy_ready);
  $("uboot-blow").dataset.ready = String(status.blow_available && !status.emergency_ascent && nav.depth_m > 30);
  $("uboot-battery-warning").hidden = status.battery === null || status.battery > .2;
  $("uboot-battery-warning").textContent = status.battery !== null && status.battery <= .03 ? t("uboot_battery_empty") : t("uboot_battery_low");
  fillFireTargets("uboot-fire-target", payload.contacts, payload.designated_target_ref);
  const wired = payload.own_weapons.map((row, index) => ({...row, label: `T${index + 1}`}));
  stationRows($("uboot-weapons"), wired, (row) => [["reference", row.label], ["depth", unit(row.depth_m, "m", 0)],
    ["course", unit(row.course, "°", 0)], ["uboot_wire", t(row.wire === "CUT" ? "uboot_wire_cut_state" : `uboot_wire_${(row.wire || "none").toLowerCase()}`)],
    ["uboot_datum", row.datum_bearing === null ? t("unavailable") : `${unit(row.datum_bearing, "°", 0)} / ${unit(row.datum_range_nm, "NM")}`]], "uboot_no_weapons");
  const select = $("uboot-wire-weapon"), active = wired.filter((row) => row.wire === "ACTIVE");
  const previous = select.value;
  select.replaceChildren(...active.map((row) => Object.assign(document.createElement("option"), {value: row.ref, textContent: row.label})));
  if (active.some((row) => row.ref === previous)) select.value = previous;
  $("uboot-wire-steer").dataset.ready = $("uboot-wire-cut").dataset.ready = String(active.length > 0);
  stationRows($("uboot-contacts"), payload.contacts, sonarEntries);
  renderLog(payload.feed);
  drawBoatDepth("uboot-depth-canvas", payload);
  drawBoatEsm("uboot-esm-canvas", payload);
  renderScope(payload);
  renderSupply(payload.plant);
  renderBallast(payload.ballast);
  drawBoatBallast("uboot-ballast-canvas", payload);
  renderDamage(payload.damage_control);
  drawBoatDamage("uboot-dc-canvas", payload);
}

// Redraw the boat instruments only, when a canvas changes size: one that was
// 0x0 at the last state push (layout still settling) would otherwise stay blank.
export function drawUbootGraphics(payload) {
  if (!payload?.esm) return;
  drawBoatDepth("uboot-depth-canvas", payload);
  drawBoatEsm("uboot-esm-canvas", payload);
  drawBoatScope("uboot-scope-canvas", payload);
  drawBoatBallast("uboot-ballast-canvas", payload);
  drawBoatDamage("uboot-dc-canvas", payload);
}
