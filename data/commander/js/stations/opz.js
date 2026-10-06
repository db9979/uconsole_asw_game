import { $, heloStates } from "../core/base.js";
import { S } from "../state/store.js";
import { heloStateText, number, t, unit } from "../core/format.js";
import { actionButton, fillFireTargets, metrics, patchChildren, position, stationRows, tacticalEntries, yesNo } from "../views/dom.js";
import { renderNoteLamps } from "../views/console-kit.js";

export function renderOpzStation(payload) {
  renderNoteLamps($("opz-lamps"));
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
  // Reports inside a fusion stand behind it: listed only while managing.
  const fused = new Set(payload.fusions.flatMap((row) => row.members));
  const labels = new Map(payload.observations.map((row) => [row.ref, row.label]));
  const sources = new Map(payload.observations.map((row) => [row.ref, row.source]));
  stationRows($("opz-observations"), payload.observations.filter((row) => S.opzManage || !fused.has(row.ref)), tacticalEntries);
  stationRows($("opz-fusions"), payload.fusions, (row) => [...tacticalEntries(row),
    ["fusion_sources", sourceNames(row.members.map((ref) => sources.get(ref)))],
    ["fusion_members", row.members.map((ref) => labels.get(ref) ?? ref).join(", ")]]);
  // Correlation suggestions: the OPZ fuses unambiguous matches by itself;
  // the operator fuses a remaining one through the ordinary manual fusion
  // action or dismisses it.
  stationRows($("opz-suggestions"), payload.suggestions, (row) => [
    ["reference", row.refs.map((ref) => labels.get(ref) ?? ref).join(" + ")],
    ["bearing", unit(row.bearing, "\u00b0", 0)],
    ["suggestion_bearing_delta", unit(row.bearing_delta_deg, "\u00b0", 1)],
    ["suggestion_distance", unit(row.distance_nm, "NM")],
    ["suggestion_course_delta", unit(row.course_delta_deg, "\u00b0", 0)],
    ["suggestion_speed_delta", unit(row.speed_delta_kn, "kn", 1)],
    ["suggestion_class", row.class_match === null ? "\u2014" : yesNo(row.class_match)]], "station_none", (row) => [
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
      [["reference", asset.name], ["state", heloStateText(heloStates, asset)], ["airborne", yesNo(asset.airborne)],
        ["position", position(asset)], ["course", unit(asset.course, "\u00b0", 0)], ["fuel", unit(asset.fuel_s, "s", 0)],
        ["torpedoes", number(asset.torpedoes, 0)], ["buoys", number(asset.buoys, 0)]]);
  renderMpa(payload.own_assets.mpa);
  renderConsort(payload.own_assets.consort);
}

// The consort destroyer of a group hunt: its orders, state and stores.
const consortModes = "auto formation search prosecute hold".split(" ");
const consortStations = "starboard ahead port astern".split(" ");
function renderConsort(consort) {
  $("opz-consort-card").hidden = consort === null;
  if (consort === null) return;
  const rows = [["consort_ship", consort.callsign], ["state", t(consort.sunk ? "consort_lost" : "consort_afloat")]];
  if (!consort.sunk) {
    rows.push(["position", position(consort)], ["bearing", unit(consort.bearing, "\u00b0", 0)],
      ["range", unit(consort.range_nm, "NM", 1)], ["course", unit(consort.course, "\u00b0", 0)],
      ["speed", unit(consort.speed_kn, "kn")], ["consort_datalink", yesNo(consort.datalink)],
      ["consort_order", t(`consort_mode_${consort.mode}`)], ["consort_working", t(`consort_mode_${consort.working}`)],
      ["consort_station", t(`consort_station_${consort.station}`)], ["consort_active", yesNo(consort.active)],
      ["consort_weapons_free", yesNo(consort.weapons_free)], ["consort_asroc", number(consort.asroc, 0)],
      ["consort_bearings", number(consort.bearings.length, 0)]);
  }
  metrics($("opz-consort"), rows);
  const live = !consort.sunk && consort.datalink;
  const next = consortStations[(consortStations.indexOf(consort.station) + 1) % consortStations.length];
  patchChildren($("opz-consort-actions"), [
    ...consortModes.filter((mode) => mode !== "formation").map((mode) =>
      actionButton(`consort_order_${mode}`, "consort_set_mode", {mode}, live && consort.mode !== mode)),
    actionButton("consort_next_station", "consort_set_station", {station: next}, live),
    actionButton(consort.active ? "consort_active_off" : "consort_active_on", "consort_set_active", {enabled: !consort.active}, live),
    actionButton(consort.weapons_free ? "consort_weapons_tight" : "consort_weapons_free_order", "consort_set_weapons", {enabled: !consort.weapons_free}, live),
    actionButton("consort_fire", "consort_fire", {}, live && consort.asroc > 0)]);
}

// Sensor groups of report sources, in display order (``source_group`` in
// src/sensors/fusion.py).
const sourceGroups = "radar visual ais esm sonar helo buoy mpa hfdf hoj datalink".split(" ");
function sourceGroup(source) {
  if (typeof source !== "string") return "datalink";
  if (source.startsWith("SONAR-DIP") || source.startsWith("HELO")) return "helo";
  if (source.startsWith("SONAR-BUOY")) return "buoy";
  if (source.startsWith("SONAR")) return "sonar";
  if (source.startsWith("RADAR-MPA")) return "mpa";
  if (source.startsWith("RADAR")) return "radar";
  if (source.startsWith("HFDF")) return "hfdf";
  return {LOOKOUT: "visual", AIS: "ais", ESM: "esm", HOJ: "hoj"}[source] || "datalink";
}
export function sourceNames(list) {
  const groups = new Set(list.map(sourceGroup));
  return sourceGroups.filter((group) => groups.has(group)).map((group) => t(`source_${group}`)).join(" \u00b7 ");
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
    ["mpa_sorties_left", number(mpa.sorties_left, 0)], ["mpa_radar", yesNo(mpa.radar)], ["mpa_mad", yesNo(mpa.mad)],
    ["mpa_buoy_mode", t(mpa.buoy_mode === "ACTIVE" ? "mpa_buoy_active" : "mpa_buoy_passive")],
    ["helicopter_pattern", t(`buoy_pattern_${mpa.pattern}`)]);
  metrics($("opz-mpa"), rows);
  const tasking = mpa.state === "TRANSIT" || mpa.state === "STATION";
  patchChildren($("opz-mpa-actions"), [
    mpa.airborne ? actionButton("mpa_return", "mpa_return", {}, tasking)
      : actionButton("mpa_request", "mpa_request", {}, mpa.ready_in_s === 0),
    actionButton("mpa_drop_buoy", "mpa_drop_buoy", {}, tasking && mpa.buoys > 0),
    actionButton(mpa.radar ? "mpa_radar_off" : "mpa_radar_on", "mpa_set_radar", {enabled: !mpa.radar}),
    actionButton(mpa.mad ? "mpa_mad_off" : "mpa_mad_on", "mpa_set_mad", {enabled: !mpa.mad}),
    actionButton(mpa.buoy_mode === "ACTIVE" ? "mpa_buoy_passive_order" : "mpa_buoy_active_order",
      "mpa_set_buoy_mode", {mode: mpa.buoy_mode === "ACTIVE" ? "PASSIVE" : "ACTIVE"})]);
}
