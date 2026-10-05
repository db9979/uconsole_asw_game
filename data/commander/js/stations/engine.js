import { S } from "../state/store.js";
import { $, damageStates } from "../core/base.js";
import { enumText, number, t, unit } from "../core/format.js";
import { metrics, node, yesNo } from "../views/dom.js";

export function renderEngineStation(payload) {
  const propulsion = payload.propulsion;
  metrics($("engine-propulsion"), [["course", unit(propulsion.course, "\u00b0", 0)], ["ordered_course", unit(propulsion.target_course, "\u00b0", 0)],
    ["speed", unit(propulsion.speed, "kn")], ["ordered_speed", unit(propulsion.target_speed, "kn")],
    ["telegraph", t(`telegraph_${propulsion.telegraph.toLowerCase()}`)], ["rpm", unit(propulsion.rpm, "RPM", 0)], ["quiet_mode", yesNo(propulsion.quiet_mode)],
    ["plant_mode", t(`plant_${propulsion.plant_mode.toLowerCase()}`)],
    ["cavitating", yesNo(propulsion.cavitating)], ["engine_fuel", unit(propulsion.fuel_kg / 1000, "t")],
    ["engine_fuel_capacity", unit(propulsion.fuel_capacity_kg / 1000, "t")], ["engine_fuel_burn", unit(propulsion.fuel_burn_kg_h, "kg/h", 0)],
    ["engine_endurance", unit(propulsion.fuel_endurance_h, "h", 0)], ["engine_range", unit(propulsion.fuel_range_nm, "NM", 0)]]);
  const machinery = payload.machinery;
  metrics($("engine-machinery"), [["station_state", enumText(damageStates, machinery.station_state)], ["speed_cap", unit(machinery.speed_cap, "kn")],
    ["effective_speed_cap", unit(machinery.effective_speed_cap, "kn")], ["flood", unit(machinery.flood, "%")],
    ["fire", unit(machinery.fire, "%")], ["engine_repair_teams", machinery.repair_teams.join(", ") || t("station_none")],
    ["engine_flood_trend", unit(machinery.repair_trend.flood_rate, "%/s")],
    ["engine_fire_trend", unit(machinery.repair_trend.fire_rate, "%/s")],
    ["noise", number(machinery.noise, 2)], ["grounded", yesNo(machinery.grounded)]]);
  const effects = payload.environment_effects;
  metrics($("engine-environment"), [["sea_state", number(effects.sea_state, 0)], ["roll", unit(effects.roll, "\u00b0")],
    ["pitch", unit(effects.pitch, "\u00b0")], ["tas_available", yesNo(effects.tas_available)],
    ["tas_performance", number(effects.tas_performance, 2)]]);
  const controls = payload.controls;
  if (!$("engine-telegraph").options.length) $("engine-telegraph").replaceChildren(...controls.orders.map((order) => {
    const option = node("option", t(`telegraph_${order.toLowerCase()}`)); option.value = order; return option;
  }));
  for (const option of $("engine-telegraph").options) option.textContent = t(`telegraph_${option.value.toLowerCase()}`);
  if (!S.stationDrafts.has("engine-telegraph")) $("engine-telegraph").value = propulsion.telegraph;
  if (!S.stationDrafts.has("engine-course")) $("engine-course").value = String(propulsion.target_course);
  $("engine-speed").max = String(Math.min(controls.speed_max_kn, machinery.speed_cap));
  $("engine-quiet").textContent = t(propulsion.quiet_mode ? "engine_quiet_disable" : "engine_quiet_enable");
  $("engine-quiet").setAttribute("aria-pressed", String(propulsion.quiet_mode));
  if (!S.stationDrafts.has("engine-plant")) $("engine-plant").value = propulsion.plant_mode;
}
