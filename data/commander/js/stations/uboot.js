import { S } from "../state/store.js";
import { $ } from "../core/base.js";
import { duration, number, t, unit } from "../core/format.js";
import { fillFireTargets, metrics, node, sonarEntries, stationRows, yesNo } from "../views/dom.js";
import { drawBoatDepth, drawBoatEsm, drawBoatScope } from "./uboot-graphics.js";

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
function renderModePairs(nav, status) {
  const state = {uboot_silent: status.silent, uboot_snorkel: status.snorkeling, uboot_mast: status.mast,
    uboot_bottom: status.bottomed};
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
  if (!S.stationDrafts.has("uboot-scope-relative")) $("uboot-scope-relative").value = String(Math.round(scope.relative_deg));
  const rows = [...scope.sightings].sort((a, b) => Math.abs(((a.bearing - scope.bearing + 540) % 360) - 180) - Math.abs(((b.bearing - scope.bearing + 540) % 360) - 180));
  stationRows($("uboot-sightings"), rows, (row) => [["reference", heading(row.bearing)],
    ["uboot_sighting_class", t(`uboot_sighting_${row.cls}`)], ["uboot_sighting_span", unit(row.span_deg * 60, "\u2032", 0)],
    ["quality", number(row.quality, 2)], ["age", unit(row.age_s, "s", 0)],
    ["uboot_sighting_range", row.range_nm === null ? t("station_none")
      : `${unit(row.range_nm, "NM")} \u00b1${unit(row.range_sigma_nm, "NM")} (${unit(row.range_age_s, "s", 0)})`]],
  scope.available ? "uboot_no_sighting" : "uboot_scope_mast_down");
  drawBoatScope("uboot-scope-canvas", payload);
}

// Energy and stores: bars, energy balance, endurance dived by speed and the boat's air.
const percent = (value, capacity) => value === null || !capacity ? null : Math.max(0, Math.min(100, value / capacity * 100));
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

export function renderUbootStation(payload) {
  showStationCards(S.v2State?.role || "uboot");
  const nav = payload.navigation, status = payload.status, weapons = payload.weapons, alarms = payload.alarms;
  renderReadouts(nav, status);
  renderChips(nav, status, alarms, payload.scope);
  renderModePairs(nav, status);
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
    ["uboot_blow_available", yesNo(status.blow_available)], ["uboot_emergency_ascent", yesNo(status.emergency_ascent)]]);
  metrics($("uboot-weapon-status"), [["torpedoes", number(weapons.torpedoes, 0)],
    ["uboot_tubes_ready", number(weapons.tubes_ready, 0)], ["reload", unit(weapons.reload_s, "s", 0)],
    ["uboot_decoys", number(weapons.decoys, 0)],
    ["uboot_torpedo_alarm", alarmText(alarms.torpedo_age_s, alarms.torpedo_bearing)]]);
  metrics($("uboot-alarms"), [["uboot_mast", yesNo(status.mast)],
    ["uboot_ping_heard", alarmText(alarms.ping_age_s, alarms.ping_bearing)],
    ["uboot_torpedo_alarm", alarmText(alarms.torpedo_age_s, alarms.torpedo_bearing)]]);
  stationRows($("uboot-esm"), alarms.esm.map((row, index) => ({...row, key: index})),
    (row) => [["bearing", unit(row.bearing, "°", 0)], ["quality", unit(row.quality * 100, "%", 0)], ["age", unit(row.age_s, "s", 0)]],
    status.mast ? "uboot_esm_none" : "uboot_esm_mast_down");
  document.body.classList.toggle("uboot-torpedo-alarm", alarms.torpedo_age_s !== null && alarms.torpedo_age_s < 60);
  if (!S.stationDrafts.has("uboot-depth")) $("uboot-depth").max = String(nav.max_depth_m);
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
}
