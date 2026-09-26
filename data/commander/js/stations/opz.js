import { $, heloStates } from "../core/base.js";
import { enumText, number, t, unit } from "../core/format.js";
import { fillFireTargets, metrics, position, stationRows, tacticalEntries, yesNo } from "../views/dom.js";

export function renderOpzStation(payload) {
  const radar = payload.radar;
  metrics($("opz-radar-summary"), [["opz_surface_radar", yesNo(radar.surface)], ["opz_air_radar", yesNo(radar.air)],
    ["opz_range", unit(radar.range_nm, "NM")], ["radar_live", yesNo(radar.live)],
    ["radar_sweep", unit(radar.sweep_bearing, "\u00b0", 0)], ["weather_severity", number(radar.weather_severity, 2)],
    ["surface_range", unit(radar.surface_effective_range_nm, "NM")], ["air_range", unit(radar.air_effective_range_nm, "NM")],
    ["sonar_target", payload.designated_target_ref || t("station_no_target")]]);
  metrics($("opz-defense"), [["vls", number(payload.defense.vls, 0)], ["ciws", number(payload.defense.ciws, 0)],
    ["aa", number(payload.defense.aa, 0)], ["chaff", yesNo(payload.defense.chaff_ready)],
    ["ciws_ready", yesNo(payload.defense.ciws_ready)], ["aa_ready", yesNo(payload.defense.aa_ready)],
    ["opz_ciws_release", yesNo(payload.defense.ciws_released)]]);
  $("opz-ciws").checked = payload.defense.ciws_released;
  fillFireTargets("opz-fire-target", payload.asm_observations);
  stationRows($("opz-observations"), payload.observations, tacticalEntries);
  stationRows($("opz-fusions"), payload.fusions, (row) => [...tacticalEntries(row), ["fusion_members", row.members.join(", ")]]);
  stationRows($("opz-classifications"), payload.source_classifications, (row) => [["reference", row.ref],
    ["source", row.source], ["classification", row.classification]]);
  const ship = payload.own_assets.ship;
  const helicopter = payload.own_assets.helicopter;
  stationRows($("opz-assets"), [{name: t("ownship"), ...ship}, {name: t("helicopter"), ...helicopter}], (asset) =>
    asset.name === t("ownship") ? [["reference", asset.name], ["position", position(asset)],
      ["course", unit(asset.course, "\u00b0", 0)], ["speed", unit(asset.speed, "kn")],
      ["ordered_course", unit(asset.target_course, "\u00b0", 0)], ["ordered_speed", unit(asset.target_speed, "kn")],
      ["rudder_angle", unit(asset.rudder_angle, "\u00b0")], ["yaw_rate", unit(asset.yaw_rate, "\u00b0/s")]] :
      [["reference", asset.name], ["state", enumText(heloStates, asset.state)], ["airborne", yesNo(asset.airborne)],
        ["position", position(asset)], ["course", unit(asset.course, "\u00b0", 0)], ["fuel", unit(asset.fuel_s, "s", 0)],
        ["torpedoes", number(asset.torpedoes, 0)], ["buoys", number(asset.buoys, 0)]]);
}
