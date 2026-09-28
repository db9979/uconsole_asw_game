import { $, heloStates } from "../core/base.js";
import { enumText, number, t, unit } from "../core/format.js";
import { actionButton, fillFireTargets, metrics, position, stationRows, tacticalEntries, yesNo } from "../views/dom.js";

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
  // Correlation suggestions: the operator fuses one through the ordinary
  // manual fusion action or dismisses it; nothing is fused by itself.
  const labels = new Map(payload.observations.map((row) => [row.ref, row.label]));
  stationRows($("opz-suggestions"), payload.suggestions, (row) => [
    ["reference", row.refs.map((ref) => labels.get(ref) ?? ref).join(" + ")],
    ["bearing", unit(row.bearing, "\u00b0", 0)],
    ["suggestion_bearing_delta", unit(row.bearing_delta_deg, "\u00b0", 1)],
    ["suggestion_distance", unit(row.distance_nm, "NM")]], "station_none", (row) => [
    actionButton("opz_confirm_suggestion", "opz_create_fusion", {refs: [...row.refs]}),
    actionButton("opz_dismiss_suggestion", "opz_dismiss_suggestion", {refs: [...row.refs]})]);
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
  renderMpa(payload.own_assets.mpa);
}

// The patrol aircraft: state, stores and the orders the OPZ may give it.
const mpaStates = {BASE: "mpa_state_base", TRANSIT: "mpa_state_transit", STATION: "mpa_state_station", RTB: "mpa_state_rtb"};
function renderMpa(mpa) {
  const rows = [["state", t(mpaStates[mpa.state])]];
  if (mpa.airborne) {
    rows.push(["position", position(mpa)], ["bearing", unit(mpa.bearing, "\u00b0", 0)],
      ["range", unit(mpa.range_nm, "NM", 0)], ["mpa_station_left", unit(mpa.station_left_s / 60, "min", 0)],
      ["mpa_datalink", yesNo(mpa.datalink)], ["mpa_relayed", number(mpa.relayed, 0)]);
  } else {
    rows.push(["mpa_ready_in", mpa.ready_in_s === null ? t("mpa_no_sorties") : unit(mpa.ready_in_s / 60, "min", 0)]);
  }
  rows.push(["buoys", number(mpa.buoys, 0)], ["torpedoes", number(mpa.torpedoes, 0)],
    ["mpa_sorties_left", number(mpa.sorties_left, 0)], ["mpa_radar", yesNo(mpa.radar)],
    ["mpa_buoy_mode", t(mpa.buoy_mode === "ACTIVE" ? "mpa_buoy_active" : "mpa_buoy_passive")],
    ["helicopter_pattern", t(`buoy_pattern_${mpa.pattern}`)]);
  metrics($("opz-mpa"), rows);
  const tasking = mpa.state === "TRANSIT" || mpa.state === "STATION";
  $("opz-mpa-actions").replaceChildren(
    mpa.airborne ? actionButton("mpa_return", "mpa_return", {}, tasking)
      : actionButton("mpa_request", "mpa_request", {}, mpa.ready_in_s === 0),
    actionButton("mpa_drop_buoy", "mpa_drop_buoy", {}, tasking && mpa.buoys > 0),
    actionButton(mpa.radar ? "mpa_radar_off" : "mpa_radar_on", "mpa_set_radar", {enabled: !mpa.radar}),
    actionButton(mpa.buoy_mode === "ACTIVE" ? "mpa_buoy_passive_order" : "mpa_buoy_active_order",
      "mpa_set_buoy_mode", {mode: mpa.buoy_mode === "ACTIVE" ? "PASSIVE" : "ACTIVE"}));
}
