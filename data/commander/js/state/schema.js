import { S } from "./store.js";
import { isBoatCommand, isSonar, stationNames } from "../core/base.js";
import { finite, t } from "../core/format.js";
import { gameEffectKinds } from "./shared.js";

export const exactKeys = (value, keys) => value && typeof value === "object" && !Array.isArray(value) && Object.keys(value).sort().join(",") === [...keys].sort().join(",");
export const boundedArray = (value, maximum) => Array.isArray(value) && value.length <= maximum;
// Bridge-lookout classes (src/sensors/lookout_id.py): an observation, not
// an operator classification.
const sightingClasses = ["MERCHANT", "TANKER", "CARGO", "PASSENGER", "WARSHIP", "CARRIER", "CRUISER", "DESTROYER",
  "FRIGATE", "CORVETTE", "MINE_WARFARE", "NAVAL_AUXILIARY", "SERVICE", "TUG", "RESEARCH", "OFFSHORE", "FISHING",
  "SMALL_CRAFT", "RESCUE", "SUBMARINE", "AIRLINER", "MILITARY_AIRCRAFT", "COMBAT_AIRCRAFT", "TORPEDO_WAKE", "SHIP", "LAND"];
const sightingKinds = ["SURFACE", "SUB", "FLG", "TORP"];
function validSightingClass(code, type) {
  if (code === null) return type === null;
  return sightingClasses.includes(code) && (type === null || (typeof type === "string" && type.length > 0 && type.length <= 80));
}
export function sightingText(code, type) {
  const what = t(`sighting_class_${code.toLowerCase()}`);
  return type === null ? what : t("sighting_with_type", { what, type });
}
function v2Observation(row, fields) {
  if (!exactKeys(row, fields) || typeof row.ref !== "string" || !row.ref || row.ref.length > 64) throw new Error("protocol");
}
// Weather & sonar analysis block, common to every role.  The ocean profile
// is null until the sonar has taken a bathythermograph measurement.
const PLOT_FIELDS = {
  mark: ["id", "shape", "label", "t", "x", "y"],
  ruler: ["id", "shape", "label", "t", "x", "y", "x2", "y2"],
  bearing: ["id", "shape", "label", "t", "x", "y", "bearing"],
  circle: ["id", "shape", "label", "t", "x", "y", "radius_nm"],
  dr: ["id", "shape", "label", "t", "x", "y", "course", "speed_kn", "now_x", "now_y", "cpa_nm", "cpa_s"],
};
function validPlot(plot) {
  if (!exactKeys(plot, ["objects", "max_objects", "max_label"]) || !Number.isInteger(plot.max_objects) ||
      !Number.isInteger(plot.max_label) || !boundedArray(plot.objects, plot.max_objects)) return false;
  const ids = new Set();
  return plot.objects.every((item) => {
    const fields = item && PLOT_FIELDS[item.shape];
    if (!fields || !exactKeys(item, fields) || !Number.isSafeInteger(item.id) || item.id < 1 || ids.has(item.id) ||
        typeof item.label !== "string" || item.label.length > plot.max_label) return false;
    ids.add(item.id);
    return fields.filter((key) => !["id", "shape", "label"].includes(key)).every((key) => finite(item[key]));
  });
}
function validWeatherStation(ws) {
  const nullableFinite = (value) => value === null || finite(value);
  const atmosphereKeys = ["weather", "precipitation", "rain_intensity", "visibility_nm", "sea_state", "wind_from_deg", "wind_kn", "gust_kn", "beaufort", "pressure_hpa", "pressure_tendency_hpa_3h", "pressure_trend", "storm_warning", "air_temp_c", "sea_temp_c", "cloud_cover", "ceiling_ft", "icing", "sun_elevation_deg", "daylight", "moon_phase", "moon_illumination", "time"];
  const flightKeys = ["status", "launch_safe", "dipping_safe", "deck_safe", "wind_kn", "gust_kn", "crosswind_kn", "visibility_nm", "ceiling_ft", "icing", "sea_state", "roll_deg", "pitch_deg", "limits"];
  const limitKeys = ["wind_kn", "gust_kn", "crosswind_kn", "visibility_nm", "ceiling_ft", "sea_state", "roll_deg", "pitch_deg"];
  const profileKeys = ["age_s", "offset_nm", "stale", "thermocline_m", "water_depth_m", "depths_m", "speeds_m_s", "sofar_axis_m", "cz_bands_nm", "range_nm", "rays", "depth_edges_m", "shadow", "dip_relative_to_layer"];
  if (!exactKeys(ws, ["atmosphere", "effects", "flight", "profile"])) return false;
  const a = ws.atmosphere, f = ws.flight, p = ws.profile;
  if (!exactKeys(a, atmosphereKeys) || !["clear", "rain", "storm", "fog", "snow"].includes(a.weather) ||
      !["none", "rain", "snow"].includes(a.precipitation) || !["rising", "steady", "falling", "falling_rapidly"].includes(a.pressure_trend) ||
      !["none", "light", "severe"].includes(a.icing) || !["day", "civil_twilight", "nautical_twilight", "night"].includes(a.daylight) ||
      !["new", "waxing_crescent", "first_quarter", "waxing_gibbous", "full", "waning_gibbous", "last_quarter", "waning_crescent"].includes(a.moon_phase) ||
      typeof a.storm_warning !== "boolean" || typeof a.time !== "string" || !/^\d\d:\d\d$/.test(a.time) ||
      !Number.isInteger(a.beaufort) || a.beaufort < 0 || a.beaufort > 12 || !Number.isInteger(a.sea_state) || a.sea_state < 0 || a.sea_state > 6 ||
      !["rain_intensity", "visibility_nm", "wind_from_deg", "wind_kn", "gust_kn", "pressure_hpa", "pressure_tendency_hpa_3h", "air_temp_c", "sea_temp_c", "cloud_cover", "sun_elevation_deg", "moon_illumination"].every((key) => finite(a[key])) ||
      !nullableFinite(a.ceiling_ft)) return false;
  if (!exactKeys(ws.effects, ["solar_heating", "wind_mixing", "freshwater"]) || Object.values(ws.effects).some((value) => typeof value !== "boolean")) return false;
  if (!exactKeys(f, flightKeys) || !["clear", "limited", "no_go"].includes(f.status) || !["none", "light", "severe"].includes(f.icing) ||
      ["launch_safe", "dipping_safe", "deck_safe"].some((key) => typeof f[key] !== "boolean") ||
      !["wind_kn", "gust_kn", "crosswind_kn", "visibility_nm", "roll_deg", "pitch_deg"].every((key) => finite(f[key])) || !nullableFinite(f.ceiling_ft) ||
      !Number.isInteger(f.sea_state) || !exactKeys(f.limits, limitKeys) || !Object.values(f.limits).every((value) => finite(value))) return false;
  if (p === null) return true;
  const pairs = (rows, maximum) => boundedArray(rows, maximum) && rows.every((row) => Array.isArray(row) && row.length === 2 && row.every((value) => finite(value)));
  return exactKeys(p, profileKeys) && typeof p.stale === "boolean" &&
    ["age_s", "offset_nm", "thermocline_m", "water_depth_m", "range_nm"].every((key) => finite(p[key]) && p[key] >= 0) && nullableFinite(p.sofar_axis_m) &&
    boundedArray(p.depths_m, 64) && boundedArray(p.speeds_m_s, 64) && p.depths_m.length === p.speeds_m_s.length && p.depths_m.length >= 2 &&
    [...p.depths_m, ...p.speeds_m_s].every((value) => finite(value)) && pairs(p.cz_bands_nm, 8) &&
    boundedArray(p.rays, 9) && p.rays.every((ray) => pairs(ray, 64)) &&
    boundedArray(p.depth_edges_m, 32) && p.depth_edges_m.length >= 2 && p.depth_edges_m.every((value) => finite(value)) &&
    boundedArray(p.shadow, 32) && p.shadow.every((row) => boundedArray(row, 32) && row.length === p.depth_edges_m.length - 1 && row.every((cell) => typeof cell === "boolean")) &&
    (p.dip_relative_to_layer === null || ["above", "below"].includes(p.dip_relative_to_layer));
}
export function validateV2State(state) {
  const status = ["protocol", "version", "session", "epoch", "revision", "seq", "phase", "role", "chart_revision"];
  if (!state || state.protocol !== 2 || typeof state.version !== "string" ||
      typeof state.session !== "string" || !state.session || state.session.length > 64 ||
      ![state.epoch, state.revision, state.seq].every((value) => Number.isSafeInteger(value) && value >= 0) ||
      state.chart_revision !== state.session) throw new Error("protocol");
  if (state.role === null) {
    if (!exactKeys(state, status)) throw new Error("protocol");
    return;
  }
  const common = [...status, "clock", "environment", "mission", "autocrew", "autocrew_overview", "audio", "weather_station", "plot"];
  if (!stationNames.includes(state.role) || state.role !== S.session?.station ||
      !exactKeys(state, [...common, state.role]) || !exactKeys(state.clock, ["sim", "mission", "world"]) ||
      !exactKeys(state.environment, ["sea_state", "effective_sea_state", "is_night", "weather", "wind_from_deg", "wind_speed_kn", "rain_intensity", "visibility_nm"]) ||
      !Number.isInteger(state.environment.sea_state) || state.environment.sea_state < 0 || state.environment.sea_state > 6 ||
      !finite(state.environment.effective_sea_state) || state.environment.effective_sea_state < 0 || state.environment.effective_sea_state > 6 ||
      typeof state.environment.is_night !== "boolean" || !["clear", "rain", "storm", "fog"].includes(state.environment.weather) ||
      !finite(state.environment.wind_from_deg) || state.environment.wind_from_deg < 0 || state.environment.wind_from_deg >= 360 ||
      !finite(state.environment.wind_speed_kn) || state.environment.wind_speed_kn < 0 || state.environment.wind_speed_kn > 80 ||
      !finite(state.environment.rain_intensity) || state.environment.rain_intensity < 0 || state.environment.rain_intensity > 1 ||
      !finite(state.environment.visibility_nm) || state.environment.visibility_nm < .1 || state.environment.visibility_nm > 30 ||
      !exactKeys(state.autocrew, ["enabled", "status"]) || typeof state.autocrew.enabled !== "boolean" ||
      !["off", "active", "suspended_remote", "blocked_damage"].includes(state.autocrew.status) ||
      !boundedArray(state.autocrew_overview, 9) || state.autocrew_overview.some((row) => !exactKeys(row, ["station", "enabled", "status"]) ||
        !stationNames.includes(row.station) || typeof row.enabled !== "boolean" ||
        !["off", "active", "suspended_remote", "blocked_damage"].includes(row.status)) ||
      !exactKeys(state.mission, ["name", "objective", "remaining_s"]) ||
      !exactKeys(state.audio, ["events"]) ||
      !boundedArray(state.audio.events, 16) ||
      state.audio.events.some((event, index, events) => !exactKeys(event, ["seq", "cue"]) ||
        !Number.isSafeInteger(event.seq) || event.seq < 1 || !gameEffectKinds.has(event.cue) ||
        index > 0 && event.seq <= events[index - 1].seq)) throw new Error("protocol");
  if (!validWeatherStation(state.weather_station) || !validPlot(state.plot)) throw new Error("protocol");
  const payload = state[state.role];
  const shapes = {
    bridge: ["navigation", "orders", "threat", "systems", "tactical_summary", "sightings"], sonar: ["observations", "settings", "visualization"],
    weapons: ["inventory", "readiness", "designated_target", "navigation", "tactical", "target_choices", "depth_m", "tubes", "settings", "own_weapons", "active_assets"],
    damage: ["compartments", "teams", "total", "sunk"],
    opz: ["observations", "fusions", "radar", "defense", "asm_observations", "source_classifications", "radar_blips", "designated_target_ref", "own_assets"],
    radio: ["observations", "logged_fixes", "logged_bearings", "messages", "station_down", "navigation", "tactical"],
    engine: ["propulsion", "machinery", "controls", "environment_effects"],
    helicopter: ["asset", "waypoint", "buoys", "buoy_observations", "acoustic", "navigation", "tactical", "target_choices", "readiness", "dip_observations", "dip_environment"], eloka: ["intercepts", "station_down", "status", "hardware"],
    uboot: ["navigation", "status", "weapons", "alarms", "contacts", "own_weapons", "designated_target_ref", "feed"],
    uboot_weapons: ["navigation", "status", "weapons", "alarms", "contacts", "own_weapons", "designated_target_ref", "feed"],
    uboot_engine: ["navigation", "status", "weapons", "alarms", "contacts", "own_weapons", "designated_target_ref", "feed"],
    uboot_esm: ["navigation", "status", "weapons", "alarms", "contacts", "own_weapons", "designated_target_ref", "feed"],
    uboot_nav: ["navigation", "status", "weapons", "alarms", "contacts", "own_weapons", "designated_target_ref", "feed"],
    uboot_sonar: ["observations", "settings", "visualization"],
  };
  if (!exactKeys(payload, shapes[state.role])) throw new Error("protocol");
  const rowsExact = (rows, maximum, fields) => {
    if (!boundedArray(rows, maximum)) throw new Error("protocol");
    rows.forEach((row) => v2Observation(row, fields));
  };
  const tacticalFields = ["ref", "label", "domain", "source", "affiliation", "bearing", "range_nm", "x", "y", "course", "speed_kn", "altitude_m", "observer_x", "observer_y", "quality", "age_s", "bearing_uncertainty_deg", "range_uncertainty_nm", "visual_class", "visual_type"];
  const tacticalRows = (rows, maximum, extraFields = []) => {
    if (!boundedArray(rows, maximum)) throw new Error("protocol");
    rows.forEach((row) => {
      v2Observation(row, [...tacticalFields, ...extraFields]);
      if (!validSightingClass(row.visual_class, row.visual_type)) throw new Error("protocol");
      if (row.speed_kn !== null && !finite(row.speed_kn)) throw new Error("protocol");
      if (row.altitude_m !== null && (!finite(row.altitude_m) || row.altitude_m < 0 || row.altitude_m > 30000)) throw new Error("protocol");
    });
  };
  const sonarFields = ["ref", "label", "source", "classification", "profile", "bearing", "range_nm", "x", "y", "depth_m", "course", "speed_kn", "quality", "age_s", "fix_age_s", "bearing_uncertainty_deg", "range_uncertainty_nm", "observer_x", "observer_y", "released_to_opz", "fixes"];
  if (state.role === "bridge") {
    if (!exactKeys(payload.navigation, ["x", "y", "course", "speed", "target_course", "target_speed", "rudder_angle", "yaw_rate", "turn_radius_nm"])) throw new Error("protocol");
    if (!exactKeys(payload.orders, ["station_down", "speed_max_kn", "telegraph", "noise", "cavitating"]) ||
        typeof payload.orders.station_down !== "boolean" || !finite(payload.orders.speed_max_kn) ||
        typeof payload.orders.cavitating !== "boolean" || payload.orders.speed_max_kn < 0 || payload.orders.speed_max_kn > 100 ||
        !exactKeys(payload.threat, ["observations", "count", "average_flood", "torpedoes"]) ||
        !boundedArray(payload.threat.torpedoes, 8) || payload.threat.torpedoes.some((row) =>
          !exactKeys(row, ["source", "bearing", "age_s"]) || !["transient", "seeker", "classified"].includes(row.source) ||
          !finite(row.bearing) || row.bearing < 0 || row.bearing >= 360 || !finite(row.age_s) || row.age_s < 0) ||
        !boundedArray(payload.systems, 32) || payload.systems.some((row) => !exactKeys(row, ["key", "state", "down"]) || typeof row.down !== "boolean")) throw new Error("protocol");
    tacticalRows(payload.threat.observations, 128);
    tacticalRows(payload.tactical_summary, 256);
    if (!boundedArray(payload.sightings, 24) || payload.sightings.some((row) =>
        !exactKeys(row, ["time", "sighted", "code", "type", "bearing", "range_nm"]) || typeof row.time !== "string" || row.time.length > 8 ||
        (row.code === null ? !sightingKinds.includes(row.sighted) || row.type !== null : row.sighted !== null || !validSightingClass(row.code, row.type)) ||
        !finite(row.bearing) || row.bearing < 0 || row.bearing >= 360 || !finite(row.range_nm) || row.range_nm < 0 || row.range_nm > 1000)) throw new Error("protocol");
  } else if (isSonar(state.role)) {
    rowsExact(payload.observations, 256, sonarFields);
    const settings = payload.settings;
    if (!exactKeys(settings, ["mode", "page", "listen_bearing", "focus_ref", "target_ref", "station_down", "tow", "bt", "ping", "tma_enabled", "gain_db", "band_preset", "band_hz", "notch", "peak_hold", "harmonic_hz", "harmonic_candidates_hz", "audio_enabled", "volume", "quiet_mode", "tools"]) ||
        !["BOW", "TOWED"].includes(settings.mode) || typeof settings.station_down !== "boolean" ||
        !exactKeys(settings.tools, ["assist", "lofar_cursor_hz", "demon_cursor_hz", "integration_s", "vernier", "shaft_hz", "blade_hz", "operator_notch_hz", "demon_band_hz", "heterodyne_hz"]) ||
        !boundedArray(settings.tools.demon_band_hz, 2) || settings.tools.demon_band_hz.some((value) => !finite(value)) || !finite(settings.tools.heterodyne_hz) ||
        typeof settings.tools.assist !== "boolean" || typeof settings.tools.vernier !== "boolean" ||
        ![2, 8, 16, 64].includes(settings.tools.integration_s) ||
        [settings.tools.lofar_cursor_hz, settings.tools.demon_cursor_hz].some((value) => !finite(value) || value < 0 || value > 300) ||
        [settings.tools.shaft_hz, settings.tools.blade_hz, settings.tools.operator_notch_hz].some((value) => value !== null && (!finite(value) || value < 0 || value > 300)) ||
        !exactKeys(settings.tow, ["state", "payout", "available", "handling_ok", "speed_kn", "speed_min_kn", "speed_max_kn", "depth_m", "depth_target_m"]) ||
        !finite(settings.tow.speed_kn) || !finite(settings.tow.speed_min_kn) || !finite(settings.tow.speed_max_kn) ||
        !exactKeys(settings.bt, ["ready", "cooldown_s", "thermocline_m"]) ||
        !exactKeys(settings.ping, ["ready", "cooldown_s"]) ||
        settings.tow.speed_kn < 0 || settings.tow.speed_kn > 100 || settings.tow.speed_min_kn < 0 ||
        settings.tow.speed_max_kn > 100 || settings.tow.speed_min_kn > settings.tow.speed_max_kn ||
        !boundedArray(settings.band_hz, 2) || settings.band_hz.length !== 2 ||
        !boundedArray(settings.harmonic_candidates_hz, 64) ||
        [settings.tow.available, settings.tow.handling_ok, settings.bt.ready, settings.ping.ready,
          settings.tma_enabled, settings.notch, settings.peak_hold, settings.audio_enabled,
          settings.quiet_mode].some((value) => typeof value !== "boolean")) throw new Error("protocol");
    const visual = payload.visualization;
    if (!exactKeys(visual, ["broadband", "lofar", "demon", "tma", "bt", "active_echoes", "receiver"]) ||
        !exactKeys(visual.broadband, ["bearing_start_deg", "bearing_step_deg", "history"]) ||
        !boundedArray(visual.broadband.history, 120) || visual.broadband.history.some((row) => !exactKeys(row, ["age_s", "bins"]) || !boundedArray(row.bins, 180)) ||
        !exactKeys(visual.lofar, ["frequency_min_hz", "frequency_max_hz", "bin_frequencies_hz", "history", "spectrum", "held", "vernier"]) ||
        (visual.lofar.vernier !== null && (!exactKeys(visual.lofar.vernier, ["low_hz", "high_hz", "step_hz", "bins"]) || !boundedArray(visual.lofar.vernier.bins, 64) || !finite(visual.lofar.vernier.low_hz) || !finite(visual.lofar.vernier.high_hz))) ||
        !boundedArray(visual.lofar.bin_frequencies_hz, 256) || !boundedArray(visual.lofar.spectrum, 256) ||
        !boundedArray(visual.lofar.history, 80) || visual.lofar.history.some((row) => !exactKeys(row, ["age_s", "bearing", "bins"]) || !boundedArray(row.bins, 110)) || typeof visual.lofar.held !== "boolean" ||
        !exactKeys(visual.demon, ["frequency_min_hz", "frequency_max_hz", "bin_step_hz", "spectrum", "history", "analysis"]) || !boundedArray(visual.demon.spectrum, 80) ||
        !boundedArray(visual.demon.history, 120) || visual.demon.history.some((row) => !exactKeys(row, ["age_s", "bins"]) || !boundedArray(row.bins, 80)) ||
        (visual.demon.analysis !== null && (!exactKeys(visual.demon.analysis, ["modulation_peak_hz", "detection_confidence", "cavitation", "tonal_hz", "hypotheses"]) || !boundedArray(visual.demon.analysis.hypotheses, 20) || visual.demon.analysis.hypotheses.some((row) => !exactKeys(row, ["blades", "order", "rpm"])))) ||
        !boundedArray(visual.tma, 32) || visual.tma.some((row) => !exactKeys(row, ["ref", "bearings", "solution", "summary", "hypothesis", "evaluation", "residuals_deg", "proposal"]) ||
          !exactKeys(row.summary, ["rate_deg_min", "legs"]) || !Number.isInteger(row.summary.legs) ||
          !exactKeys(row.hypothesis, ["course", "speed_kn", "range_nm"]) || !finite(row.hypothesis.course) || !finite(row.hypothesis.speed_kn) || !finite(row.hypothesis.range_nm) ||
          (row.evaluation !== null && !exactKeys(row.evaluation, ["rms_deg", "systematic_deg", "fit", "observability"])) ||
          !boundedArray(row.residuals_deg, 24) || row.residuals_deg.some((value) => !finite(value)) ||
          (row.proposal !== null && !exactKeys(row.proposal, ["course", "speed_kn", "range_nm"])) || !boundedArray(row.bearings, 24) || row.bearings.some((point) => !exactKeys(point, ["age_s", "bearing", "uncertainty_deg", "own_x", "own_y", "own_course"])) || row.solution !== null && !exactKeys(row.solution, ["x", "y", "course", "speed_kn", "quality", "age_s", "uncertainty_nm"])) ||
        (visual.bt !== null && (!exactKeys(visual.bt, ["age_s", "thermocline_m", "water_depth_m", "sea_state", "depths_m", "speeds_m_s", "cz_bands_nm"]) || !boundedArray(visual.bt.depths_m, 64) || !boundedArray(visual.bt.speeds_m_s, 64) || visual.bt.depths_m.length !== visual.bt.speeds_m_s.length || !boundedArray(visual.bt.cz_bands_nm, 8) || visual.bt.cz_bands_nm.some((band) => !boundedArray(band, 2) || band.length !== 2))) ||
        !boundedArray(visual.active_echoes, 40) || visual.active_echoes.some((row) => !exactKeys(row, ["age_s", "bearing", "range_nm", "depth_m", "range_uncertainty_nm", "depth_uncertainty_m", "snr_db", "array"])) ||
        !exactKeys(visual.receiver, ["array", "listen_bearing", "beam_width_deg", "listen_mode", "focus_locked", "audio_enabled"]) || !["BROADBAND", "FILTERED", "HETERODYNE"].includes(visual.receiver.listen_mode) || typeof visual.receiver.focus_locked !== "boolean" || typeof visual.receiver.audio_enabled !== "boolean") throw new Error("protocol");
  } else if (isBoatCommand(state.role)) {
    const nav = payload.navigation, status = payload.status, weapons = payload.weapons, alarms = payload.alarms;
    const navNumbers = ["x", "y", "course", "target_course", "speed", "target_speed", "depth_m", "target_depth_m", "safe_depth_m", "max_depth_m", "max_speed_kn", "noise"];
    if (!exactKeys(nav, [...navNumbers, "water_depth_m", "under_keel_m", "obstacle_ahead_nm", "depth_presets", "cavitating"]) || navNumbers.some((key) => !finite(nav[key])) ||
        !exactKeys(nav.depth_presets, ["periscope", "snorkel", "above_layer", "below_layer", "deep", "layer"]) ||
        Object.values(nav.depth_presets).some((value) => value !== null && (!finite(value) || value < 0 || value > 1000)) ||
        [nav.water_depth_m, nav.under_keel_m, nav.obstacle_ahead_nm].some((value) => value !== null && !finite(value)) || typeof nav.cavitating !== "boolean" ||
        !exactKeys(status, ["state", "damage", "emergency_ascent", "blow_available", "battery", "endurance_phase", "transmitting", "snorkel_available", "snorkeling", "silent", "quiet", "bottomed", "mast"]) ||
        [status.snorkel_available, status.snorkeling, status.silent, status.quiet, status.bottomed, status.mast].some((value) => typeof value !== "boolean") ||
        !["manual", "ai", "sinking", "sunk"].includes(status.state) || !finite(status.damage) ||
        [status.emergency_ascent, status.blow_available, status.transmitting].some((value) => typeof value !== "boolean") ||
        (status.battery !== null && !finite(status.battery)) ||
        (status.endurance_phase !== null && (typeof status.endurance_phase !== "string" || status.endurance_phase.length > 16)) ||
        !exactKeys(weapons, ["torpedoes", "tubes_ready", "reload_s", "ready", "reason", "arc_center_deg", "arc_width_deg", "decoys", "decoy_ready"]) ||
        [weapons.torpedoes, weapons.tubes_ready, weapons.decoys].some((value) => !Number.isInteger(value) || value < 0) ||
        typeof weapons.ready !== "boolean" || typeof weapons.decoy_ready !== "boolean" ||
        (weapons.reason !== null && !["not_ready", "no_torpedoes", "reloading", "out_of_arc"].includes(weapons.reason)) ||
        [weapons.reload_s, weapons.arc_center_deg, weapons.arc_width_deg].some((value) => value !== null && !finite(value)) ||
        !exactKeys(alarms, ["ping_age_s", "torpedo_age_s", "ping_bearing", "torpedo_bearing", "esm"]) ||
        [alarms.ping_age_s, alarms.torpedo_age_s, alarms.ping_bearing, alarms.torpedo_bearing].some((value) => value !== null && !finite(value)) ||
        !boundedArray(alarms.esm, 16) || alarms.esm.some((row) => !exactKeys(row, ["bearing", "quality", "age_s"]) ||
          [row.bearing, row.quality, row.age_s].some((value) => !finite(value))) ||
        (payload.designated_target_ref !== null && typeof payload.designated_target_ref !== "string") ||
        !boundedArray(payload.feed, 16) || payload.feed.some((row) => !exactKeys(row, ["seq", "age_s", "message"]) ||
          !Number.isSafeInteger(row.seq) || typeof row.message !== "string" || row.message.length > 256 ||
          (row.age_s !== null && !finite(row.age_s)))) throw new Error("protocol");
    rowsExact(payload.contacts, 128, sonarFields);
    if (!boundedArray(payload.own_weapons, 16) || payload.own_weapons.some((row) =>
      !exactKeys(row, ["ref", "x", "y", "depth_m", "course", "state", "wire", "datum_bearing", "datum_range_nm"]) ||
      ![null, "ACTIVE", "BROKEN", "CUT"].includes(row.wire) ||
      [row.datum_bearing, row.datum_range_nm].some((value) => value !== null && !finite(value)))) throw new Error("protocol");
  } else if (state.role === "weapons") {
    if (!exactKeys(payload.settings, ["torpedo_type", "choices", "pattern", "enable_nm", "salvo"]) ||
        !boundedArray(payload.settings.choices, 8) ||
        !payload.settings.choices.every((row) => exactKeys(row, ["key", "name", "stock", "loaded"])) ||
        !["snake", "circle", "helix"].includes(payload.settings.pattern) || ![1, 2].includes(payload.settings.salvo) ||
        !exactKeys(payload.inventory, ["torpedoes", "vls", "ciws", "aa", "chaff_ready", "nixies"]) ||
        !exactKeys(payload.readiness, ["station_down", "roe", "ciws_ready", "aa_ready", "state", "interlock", "reload_s"]) ||
        (payload.designated_target !== null && !exactKeys(payload.designated_target, ["ref", "label", "domain", "source", "affiliation", "classification", "bearing", "range_nm", "x", "y", "depth_m", "course", "speed_kn", "quality", "age_s", "fix_age_s", "bearing_uncertainty_deg", "range_uncertainty_nm"])) ||
        !exactKeys(payload.navigation, ["x", "y", "course", "speed", "target_course", "target_speed", "rudder_angle", "yaw_rate", "turn_radius_nm"]) ||
        !boundedArray(payload.tubes, 16) || payload.tubes.some((row) => !exactKeys(row, ["tube", "state", "reload_s"])) ||
        !boundedArray(payload.own_weapons, 96) || payload.own_weapons.some((row) => !exactKeys(row, ["ref", "x", "y", "depth_m", "course", "state"])) ||
        !boundedArray(payload.active_assets, 104) || payload.active_assets.some((row) => !exactKeys(row, ["ref", "x", "y", "depth_m", "course", "state"]))) throw new Error("protocol");
    tacticalRows(payload.tactical, 128);
    rowsExact(payload.target_choices, 128, ["ref", "label", "domain", "source", "affiliation", "classification", "bearing", "range_nm", "x", "y", "depth_m", "course", "speed_kn", "quality", "age_s", "fix_age_s", "bearing_uncertainty_deg", "range_uncertainty_nm"]);
  } else if (state.role === "damage") {
    if (!boundedArray(payload.compartments, 16) || payload.compartments.some((row) => !exactKeys(row, ["key", "name", "state", "flood", "fire", "repairable", "trend"]) || typeof row.repairable !== "boolean" || !exactKeys(row.trend, ["flood_rate", "fire_rate", "repairable"])) ||
        !boundedArray(payload.teams, 16) || payload.teams.some((row) => !exactKeys(row, ["team", "compartment"]))) throw new Error("protocol");
  } else if (state.role === "opz") {
    tacticalRows(payload.observations, 256);
    tacticalRows(payload.fusions, 32, ["members"]);
    const rawRefs = new Set(payload.observations.map((row) => row.ref));
    const pictureRefs = new Set([...rawRefs, ...payload.fusions.map((row) => row.ref)]);
    const radarFields = ["surface", "air", "range_nm", "live", "sweep_bearing", "sweep_rate_deg_s", "weather_severity", "surface_effective_range_nm", "air_effective_range_nm"];
    if (!exactKeys(payload.radar, radarFields) ||
        typeof payload.radar.surface !== "boolean" || typeof payload.radar.air !== "boolean" ||
        typeof payload.radar.live !== "boolean" || ![10, 20, 40, 80, 120].includes(payload.radar.range_nm) ||
        (!finite(payload.radar.sweep_rate_deg_s) || payload.radar.sweep_rate_deg_s < 0 || payload.radar.sweep_rate_deg_s > 720) ||
        payload.fusions.some((row) => !boundedArray(row.members, 8) || row.members.length < 2 ||
          row.source !== "FUSION" || new Set(row.members).size !== row.members.length ||
          row.members.some((ref) => typeof ref !== "string" || !rawRefs.has(ref))) ||
        !boundedArray(payload.source_classifications, 256) ||
        payload.source_classifications.some((row) => !exactKeys(row, ["ref", "source", "classification"]) ||
          !pictureRefs.has(row.ref) || typeof row.source !== "string" ||
          typeof row.classification !== "string" || !row.classification || row.classification.length > 128) ||
         new Set(payload.source_classifications.map((row) => row.ref)).size !== payload.source_classifications.length ||
         !exactKeys(payload.defense, ["vls", "ciws", "aa", "chaff_ready", "ciws_ready", "aa_ready", "ciws_released"]) || typeof payload.defense.ciws_released !== "boolean" ||
         !boundedArray(payload.radar_blips, 16) || payload.radar_blips.some((row) => !exactKeys(row, ["ref", "x", "y", "age_s"]) ||
           typeof row.ref !== "string" || !/^blip-[0-9]{1,18}$/.test(row.ref) || [row.x, row.y, row.age_s].some((value) => !finite(value)))) throw new Error("protocol");
    tacticalRows(payload.asm_observations, 128);
    if (payload.designated_target_ref !== null && (typeof payload.designated_target_ref !== "string" || !pictureRefs.has(payload.designated_target_ref))) throw new Error("protocol");
    if (!exactKeys(payload.own_assets, ["ship", "helicopter", "weapons"]) ||
        !boundedArray(payload.own_assets.weapons, 104) || payload.own_assets.weapons.some((row) => !exactKeys(row, ["ref", "x", "y", "depth_m", "course", "state"])) ||
        !exactKeys(payload.own_assets.ship, ["x", "y", "course", "speed", "target_course", "target_speed", "rudder_angle", "yaw_rate", "turn_radius_nm"]) ||
        !exactKeys(payload.own_assets.helicopter, ["state", "airborne", "x", "y", "course", "fuel_s", "torpedoes", "buoys", "hovering", "dip_state", "dip_depth_m", "dip_depth_target_m", "dip_water_depth_m", "dip_ping_ready", "dip_ping_cooldown_s"])) throw new Error("protocol");
  } else if (state.role === "radio") {
    rowsExact(payload.observations, 256, ["ref", "label", "bearing", "quality", "age_s", "bearing_uncertainty_deg", "frequency_khz", "propagation", "can_capture"]);
    if (payload.observations.some((row) => (row.frequency_khz !== null && (!finite(row.frequency_khz) || row.frequency_khz <= 0)) ||
        ![null, "GROUND", "SKY"].includes(row.propagation))) throw new Error("protocol");
    if (!boundedArray(payload.logged_fixes, 256) || payload.logged_fixes.some((row) => !exactKeys(row, ["ref", "x", "y", "uncertainty_nm", "age_s", "covariance_nm2"]) || row.covariance_nm2 !== null && (!boundedArray(row.covariance_nm2, 3) || row.covariance_nm2.length !== 3)) ||
        !boundedArray(payload.logged_bearings, 256) || payload.logged_bearings.some((row) => !exactKeys(row, ["ref", "bearing", "observer_x", "observer_y", "age_s"])) ||
        !boundedArray(payload.messages, 40) || payload.messages.some((row) => !exactKeys(row, ["stamp", "text"])) ||
        typeof payload.station_down !== "boolean" || payload.observations.some((row) => typeof row.can_capture !== "boolean") ||
        !exactKeys(payload.navigation, ["x", "y", "course", "speed", "target_course", "target_speed", "rudder_angle", "yaw_rate", "turn_radius_nm"])) throw new Error("protocol");
    tacticalRows(payload.tactical, 128);
  } else if (state.role === "engine") {
    if (!exactKeys(payload.propulsion, ["course", "target_course", "speed", "target_speed", "telegraph", "rpm", "quiet_mode", "cavitating", "fuel_kg", "fuel_capacity_kg", "fuel_burn_kg_h", "fuel_endurance_h", "fuel_range_nm"]) ||
        !exactKeys(payload.machinery, ["station_state", "speed_cap", "effective_speed_cap", "flood", "fire", "repair_teams", "repair_trend", "noise", "grounded"]) ||
        !boundedArray(payload.machinery.repair_teams, 16) || !exactKeys(payload.machinery.repair_trend, ["flood_rate", "fire_rate", "repairable"]) ||
        !exactKeys(payload.controls, ["orders", "speed_max_kn"]) || !boundedArray(payload.controls.orders, 6) ||
        payload.controls.orders.join(",") !== "ASTERN,STOP,SLOW,HALF,FULL,FLANK" ||
        !exactKeys(payload.environment_effects, ["sea_state", "roll", "pitch", "tas_available", "tas_performance"])) throw new Error("protocol");
  } else if (state.role === "helicopter") {
    if (!exactKeys(payload.asset, ["state", "airborne", "x", "y", "course", "fuel_s", "torpedoes", "buoys", "hovering", "dip_state", "dip_depth_m", "dip_depth_target_m", "dip_water_depth_m", "dip_ping_ready", "dip_ping_cooldown_s", "buoy_mode"]) ||
        (payload.waypoint !== null && !exactKeys(payload.waypoint, ["x", "y"])) ||
        !boundedArray(payload.buoys, 64) || payload.buoys.some((row) => !exactKeys(row, ["ref", "label", "x", "y", "battery_s", "active", "mode"]) || typeof row.label !== "string" || !/^SB[0-9]{2,}$/.test(row.label) || !["ACTIVE", "PASSIVE"].includes(row.mode)) ||
        !exactKeys(payload.navigation, ["x", "y", "course", "speed", "target_course", "target_speed", "rudder_angle", "yaw_rate", "turn_radius_nm"]) ||
        !exactKeys(payload.readiness, ["flightdeck_down", "deck_state", "can_launch", "can_return", "can_set_waypoint", "can_deploy_buoy", "can_set_dipping", "can_set_dip_depth", "can_dipping_ping", "weather_launch_safe", "weather_dipping_safe", "crosswind_kn", "rtb_margin_s"]) ||
        [payload.readiness.flightdeck_down, payload.readiness.can_launch, payload.readiness.can_return, payload.readiness.can_set_waypoint, payload.readiness.can_deploy_buoy, payload.readiness.can_set_dipping, payload.readiness.can_set_dip_depth, payload.readiness.can_dipping_ping, payload.readiness.weather_launch_safe, payload.readiness.weather_dipping_safe].some((value) => typeof value !== "boolean") ||
        !finite(payload.readiness.crosswind_kn) || payload.readiness.crosswind_kn < 0 || payload.readiness.crosswind_kn > 80) throw new Error("protocol");
    tacticalRows(payload.tactical, 128, ["classification", "released_to_opz"]);
    rowsExact(payload.dip_observations, 128, ["ref", "label", "bearing", "bearing_uncertainty_deg", "age_s", "range_nm", "active_bearing", "range_uncertainty_nm", "depth_m", "depth_uncertainty_m", "fix_age_s", "classification", "qualified", "released_to_opz"]);
    rowsExact(payload.buoy_observations, 128, ["ref", "label", "buoy_label", "mode", "bearing", "bearing_uncertainty_deg", "range_nm", "x", "y", "observer_x", "observer_y", "age_s", "quality", "qualified", "released_to_opz"]);
    if (!exactKeys(payload.acoustic, ["source", "sources", "spectrum", "history", "ready",
        "bin_frequencies_hz", "broadband", "broadband_history", "demon", "demon_history",
        "listen_bearing", "audition_mode", "band_preset", "gain_db", "notch"]) ||
        typeof payload.acoustic.ready !== "boolean" ||
        !(payload.acoustic.listen_bearing === null || finite(payload.acoustic.listen_bearing) &&
          payload.acoustic.listen_bearing >= 0 && payload.acoustic.listen_bearing < 360) ||
        !["BROADBAND", "FILTERED", "HETERODYNE"].includes(payload.acoustic.audition_mode) ||
        !["FULL", "LOW", "SHAFT", "MID"].includes(payload.acoustic.band_preset) ||
        !finite(payload.acoustic.gain_db) || payload.acoustic.gain_db < -12 || payload.acoustic.gain_db > 24 ||
        typeof payload.acoustic.notch !== "boolean" ||
        !boundedArray(payload.acoustic.sources, 6) || !payload.acoustic.sources.includes(payload.acoustic.source) ||
        !boundedArray(payload.acoustic.spectrum, 256) || !boundedArray(payload.acoustic.bin_frequencies_hz, 256) ||
        payload.acoustic.spectrum.length !== payload.acoustic.bin_frequencies_hz.length ||
        !boundedArray(payload.acoustic.broadband, 180) || !boundedArray(payload.acoustic.demon, 80) ||
        !["spectrum", "bin_frequencies_hz", "broadband", "demon"].every((key) =>
          payload.acoustic[key].every((value) => finite(value))) ||
        !["history", "broadband_history", "demon_history"].every((key) =>
          boundedArray(payload.acoustic[key], 64) && payload.acoustic[key].every((row) =>
            boundedArray(row, 256) && row.every((value) => finite(value))))) throw new Error("protocol");
    if (!exactKeys(payload.dip_environment, ["water_depth_m", "thermocline_m", "depth_limit_m", "bottom_clearance_m", "winch_rate_m_s", "below_thermocline"]) ||
        Object.entries(payload.dip_environment).some(([key, value]) => value !== null &&
          (key === "below_thermocline" ? typeof value !== "boolean" : !finite(value))) ||
        payload.dip_environment.winch_rate_m_s <= 0) throw new Error("protocol");
    rowsExact(payload.target_choices, 128, ["ref", "label", "domain", "source", "affiliation", "classification", "bearing", "range_nm", "x", "y", "depth_m", "course", "speed_kn", "quality", "age_s", "fix_age_s", "bearing_uncertainty_deg", "range_uncertainty_nm"]);
  } else if (state.role === "eloka") {
    if (!boundedArray(payload.intercepts, 64) || payload.intercepts.some((row) => !exactKeys(row, ["ref", "label", "bearing", "bearing_uncertainty_deg", "frequency_hz", "frequency_band", "prf_hz", "modulation", "quality", "age_s", "radar_type", "threat", "signal_state", "operational", "ambiguous", "synthetic_assumption", "auto_jamming", "jamming", "jamming_effectiveness", "jamming_technique", "ecm_power_draw", "is_locked_on", "hoj_risk", "annotation", "candidates", "correlations", "signal_db", "range_estimate_nm", "scan_period_s"]) ||
        typeof row.synthetic_assumption !== "boolean" || typeof row.auto_jamming !== "boolean" || typeof row.jamming !== "boolean" ||
        !finite(row.signal_db) || [row.range_estimate_nm, row.scan_period_s].some((value) => value !== null && (!finite(value) || value < 0)) ||
        typeof row.is_locked_on !== "boolean" || typeof row.hoj_risk !== "boolean" || !["a_c", "d", "e_f", "g_h", "i_j", "k"].includes(row.frequency_band) ||
        (row.jamming_technique !== null && !["noise", "rgpo", "vgpo", "false_targets"].includes(row.jamming_technique)) ||
        typeof row.ambiguous !== "boolean" || typeof row.operational !== "boolean" || !["LIVE", "RECENT", "MEMORY", "UNCONFIRMED"].includes(row.signal_state) || !["low", "medium", "high", "critical", "unknown"].includes(row.threat) ||
        !boundedArray(row.candidates, 32) || row.candidates.some((item) => !exactKeys(item, ["ref", "name", "score"]) || (item.score !== null && !finite(item.score))) ||
        !boundedArray(row.correlations, 8) || row.correlations.some((item) => !exactKeys(item, ["ref", "source", "score", "ambiguous", "evidence"]) || !exactKeys(item.evidence, ["bearing", "bearing_uncertainty_deg", "age_s", "position_available"])))) throw new Error("protocol");
    if (typeof payload.station_down !== "boolean" || !["down", "live"].includes(payload.status)) throw new Error("protocol");
    if (!exactKeys(payload.hardware, ["df_sensors", "broadband_sensors", "ecm_channels", "frequency_min_hz", "frequency_max_hz", "reaction_s"]) ||
        payload.hardware.df_sensors !== 4 || payload.hardware.broadband_sensors !== 1 || payload.hardware.ecm_channels !== 4 ||
        !finite(payload.hardware.frequency_min_hz) || !finite(payload.hardware.frequency_max_hz) || !finite(payload.hardware.reaction_s)) throw new Error("protocol");
  }
  const arrays = [];
  for (const key of ["tactical_summary", "observations", "own_weapons", "compartments", "teams", "logged_fixes", "logged_bearings", "messages", "buoys", "intercepts"]) {
    if (Object.hasOwn(payload, key)) arrays.push(payload[key]);
  }
  if (arrays.some((rows) => !boundedArray(rows, 256))) throw new Error("protocol");
  const forbidden = new Set(["target_id", "track_id", "kind", "signature", "emitter_key", "seed", "rng"]);
  const inspect = (value, depth = 0) => {
    if (depth > 8) throw new Error("protocol");
    if (value === null || typeof value === "boolean" || typeof value === "string") return;
    if (typeof value === "number") { if (!finite(value)) throw new Error("protocol"); return; }
    if (Array.isArray(value)) { if (value.length > 256) throw new Error("protocol"); value.forEach((item) => inspect(item, depth + 1)); return; }
    if (!value || typeof value !== "object") throw new Error("protocol");
    for (const [key, item] of Object.entries(value)) { if (forbidden.has(key)) throw new Error("protocol"); inspect(item, depth + 1); }
  };
  inspect(state);
}
