import { S } from "./store.js";
import { isBoatCommand, isSonar, lookoutRoles, opforRoles, sessionRoles, stationNames } from "../core/base.js";
import { finite, t } from "../core/format.js";
import { calloutKinds, calloutsWithBearing, gameEffectKinds } from "./shared.js";

export const exactKeys = (value, keys) => value && typeof value === "object" && !Array.isArray(value) && Object.keys(value).sort().join(",") === [...keys].sort().join(",");
export const boundedArray = (value, maximum) => Array.isArray(value) && value.length <= maximum;
// Bridge-lookout classes (src/sensors/lookout_id.py): an observation, not
// an operator classification.
const sightingClasses = ["MERCHANT", "TANKER", "CARGO", "PASSENGER", "WARSHIP", "CARRIER", "CRUISER", "DESTROYER",
  "FRIGATE", "CORVETTE", "MINE_WARFARE", "NAVAL_AUXILIARY", "SERVICE", "TUG", "RESEARCH", "OFFSHORE", "FISHING",
  "SMALL_CRAFT", "RESCUE", "SUBMARINE", "PERISCOPE", "AIRLINER", "MILITARY_AIRCRAFT", "COMBAT_AIRCRAFT", "TORPEDO_WAKE", "SHIP", "LAND"];
const sightingKinds = ["SURFACE", "SUB", "MAST", "FLG", "TORP", "LIGHTS"];
const sightingLightsOk = (row) => row.sighted === "LIGHTS"
  ? typeof row.lights === "string" && /^[LR][012][r-][g-][s-](GW|WR|RWR|GGG|AC)?$/.test(row.lights) : row.lights === null;
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
  if (!exactKeys(plot, ["objects", "max_objects", "max_label", "trail", "fx"]) || !Number.isInteger(plot.max_objects) ||
      !Number.isInteger(plot.max_label) || !boundedArray(plot.objects, plot.max_objects)) return false;
  // Own track (own-platform truth): at most two hours of [x, y] points.
  if (!boundedArray(plot.trail, 240) ||
      !plot.trail.every((row) => Array.isArray(row) && row.length === 2 && finite(row[0]) && finite(row[1]))) return false;
  // Moving chart marks (own pings, their echoes, own charges): [age_s, x, y].
  const fxRows = (rows, maximum) => boundedArray(rows, maximum) && rows.every((row) => Array.isArray(row) &&
    row.length === 3 && row.every(finite) && row[0] >= 0);
  if (!exactKeys(plot.fx, ["pings", "echoes", "splashes"]) || !fxRows(plot.fx.pings, 6) ||
      !fxRows(plot.fx.echoes, 12) || !fxRows(plot.fx.splashes, 12)) return false;
  const ids = new Set();
  return plot.objects.every((item) => {
    const fields = item && PLOT_FIELDS[item.shape];
    if (!fields || !exactKeys(item, fields) || !Number.isSafeInteger(item.id) || item.id < 1 || ids.has(item.id) ||
        typeof item.label !== "string" || item.label.length > plot.max_label) return false;
    ids.add(item.id);
    return fields.filter((key) => !["id", "shape", "label"].includes(key)).every((key) => finite(item[key]));
  });
}
// ``boat``: a submarine role gets the boat block instead of flight weather
// and no cloud ceiling or icing; ``fields`` are the generated allowlists.
function validBoatWeather(b, fields) {
  const nonNegative = ["mast_radar_nm", "mast_radar_calm_nm", "sighting_nm", "sighting_ref_nm", "snorkel_max_kn", "snorkel_noise_db"];
  return exactKeys(b, fields.boat) && nonNegative.every((key) => finite(b[key]) && b[key] >= 0) &&
    typeof b.snorkel_available === "boolean" && typeof b.snorkeling === "boolean" &&
    boundedArray(b.ambient_bands_hz, 8) && b.ambient_bands_hz.length >= 1 && b.ambient_bands_hz.every((value) => finite(value) && value > 0) &&
    boundedArray(b.ambient_excess_db, 8) && b.ambient_excess_db.length === b.ambient_bands_hz.length && b.ambient_excess_db.every((value) => finite(value)) &&
    boundedArray(b.snorkel_lines_hz, 4) && b.snorkel_lines_hz.every((value) => finite(value) && value > 0);
}
function validWeatherStation(ws, boat, fields) {
  const nullableFinite = (value) => value === null || finite(value);
  const flightKeys = ["status", "launch_safe", "dipping_safe", "deck_safe", "wind_kn", "gust_kn", "crosswind_kn", "visibility_nm", "ceiling_ft", "icing", "sea_state", "roll_deg", "pitch_deg", "limits"];
  const limitKeys = ["wind_kn", "gust_kn", "crosswind_kn", "visibility_nm", "ceiling_ft", "sea_state", "roll_deg", "pitch_deg"];
  const profileKeys = ["age_s", "offset_nm", "stale", "thermocline_m", "water_depth_m", "depths_m", "speeds_m_s", "sofar_axis_m", "cz_bands_nm", "range_nm", "rays", "depth_edges_m", "shadow", "dip_relative_to_layer"];
  if (!exactKeys(ws, ["atmosphere", "effects", boat ? "boat" : "flight", "profile"])) return false;
  const a = ws.atmosphere, f = ws.flight, p = ws.profile;
  if (!exactKeys(a, boat ? fields.boatAtmosphere : fields.atmosphere) || !["clear", "rain", "storm", "fog", "snow"].includes(a.weather) ||
      !["none", "rain", "snow"].includes(a.precipitation) || !["rising", "steady", "falling", "falling_rapidly"].includes(a.pressure_trend) ||
      (!boat && !["none", "light", "severe"].includes(a.icing)) || !["day", "civil_twilight", "nautical_twilight", "night"].includes(a.daylight) ||
      !["new", "waxing_crescent", "first_quarter", "waxing_gibbous", "full", "waning_gibbous", "last_quarter", "waning_crescent"].includes(a.moon_phase) ||
      typeof a.storm_warning !== "boolean" || typeof a.time !== "string" || !/^\d\d:\d\d$/.test(a.time) ||
      !Number.isInteger(a.beaufort) || a.beaufort < 0 || a.beaufort > 12 || !Number.isInteger(a.sea_state) || a.sea_state < 0 || a.sea_state > 6 ||
      !["rain_intensity", "visibility_nm", "wind_from_deg", "wind_kn", "gust_kn", "pressure_hpa", "pressure_tendency_hpa_3h", "air_temp_c", "sea_temp_c", "cloud_cover", "sun_elevation_deg", "moon_illumination"].every((key) => finite(a[key])) ||
      (!boat && !nullableFinite(a.ceiling_ft))) return false;
  if (!exactKeys(ws.effects, ["solar_heating", "wind_mixing", "freshwater"]) || Object.values(ws.effects).some((value) => typeof value !== "boolean")) return false;
  if (boat) {
    if (!validBoatWeather(ws.boat, fields)) return false;
  } else if (!exactKeys(f, flightKeys) || !["clear", "limited", "no_go"].includes(f.status) || !["none", "light", "severe"].includes(f.icing) ||
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
// Hover notes of the station's lamps: why each shows what it shows.
function lampTipsOk(tips) {
  const text = (value, max) => typeof value === "string" && value.length <= max;
  return !!tips && typeof tips === "object" && !Array.isArray(tips) && Object.keys(tips).length <= 80 &&
    Object.entries(tips).every(([key, tip]) => /^[a-z0-9_]{1,32}$/.test(key) &&
      exactKeys(tip, ["title", "label", "value", "level", "lines", "keys"]) && text(tip.title, 120) &&
      text(tip.label, 60) && text(tip.value, 60) && ["", "off", "on", "caution", "alarm"].includes(tip.level) &&
      boundedArray(tip.lines, 8) && tip.lines.every((line) => text(line, 240)) &&
      boundedArray(tip.keys, 8) && tip.keys.every((key) => text(key, 16)));
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
  const common = [...status, "clock", "environment", "mission", "autocrew", "autocrew_overview", "audio", "weather_station", "plot", "alarms", "hit_view", "crew_noise", "lamp_tips"];
  if (!sessionRoles.includes(state.role) || state.role !== S.session?.station ||
      !exactKeys(state, [...common, state.role]) || !exactKeys(state.clock, ["sim", "mission", "world"]) ||
      !exactKeys(state.environment, ["sea_state", "effective_sea_state", "is_night", "weather", "wind_from_deg", "wind_speed_kn", "rain_intensity", "visibility_nm", "storm"]) ||
      !Number.isInteger(state.environment.sea_state) || state.environment.sea_state < 0 || state.environment.sea_state > 6 ||
      !finite(state.environment.effective_sea_state) || state.environment.effective_sea_state < 0 || state.environment.effective_sea_state > 6 ||
      typeof state.environment.is_night !== "boolean" || !["clear", "rain", "storm", "fog"].includes(state.environment.weather) ||
      !finite(state.environment.wind_from_deg) || state.environment.wind_from_deg < 0 || state.environment.wind_from_deg >= 360 ||
      !finite(state.environment.wind_speed_kn) || state.environment.wind_speed_kn < 0 || state.environment.wind_speed_kn > 80 ||
      !finite(state.environment.rain_intensity) || state.environment.rain_intensity < 0 || state.environment.rain_intensity > 1 ||
      !finite(state.environment.visibility_nm) || state.environment.visibility_nm < .1 || state.environment.visibility_nm > 30 ||
      !finite(state.environment.storm) || state.environment.storm < 0 || state.environment.storm > 1 ||
      !exactKeys(state.autocrew, ["enabled", "status"]) || typeof state.autocrew.enabled !== "boolean" ||
      !["off", "active", "suspended_remote", "suspended_local", "blocked_damage"].includes(state.autocrew.status) ||
      !boundedArray(state.autocrew_overview, 9) || state.autocrew_overview.some((row) => !exactKeys(row, ["station", "enabled", "status"]) ||
        !stationNames.includes(row.station) || typeof row.enabled !== "boolean" ||
        !["off", "active", "suspended_remote", "suspended_local", "blocked_damage"].includes(row.status)) ||
      !exactKeys(state.mission, ["name", "objective", "remaining_s"]) || !lampTipsOk(state.lamp_tips) ||
      !boundedArray(state.alarms, 9) || state.alarms.some((row) => !exactKeys(row, ["station", "level"]) ||
        !stationNames.includes(row.station) || !["warn", "danger"].includes(row.level)) ||
      !exactKeys(state.audio, ["events", "callouts"]) ||
      !boundedArray(state.audio.callouts, 16) ||
      state.audio.callouts.some((row, index, rows) => !exactKeys(row, ["seq", "key", "bearing"]) ||
        !Number.isSafeInteger(row.seq) || row.seq < 1 || !calloutKinds.has(row.key) ||
        (calloutsWithBearing.has(row.key) ? !Number.isInteger(row.bearing) || row.bearing < 0 || row.bearing > 359
          : row.bearing !== null) ||
        index > 0 && row.seq <= rows[index - 1].seq) ||
      !boundedArray(state.audio.events, 16) ||
      state.audio.events.some((event, index, events) => !exactKeys(event, ["seq", "cue", "pan"]) ||
        !Number.isSafeInteger(event.seq) || event.seq < 1 || !gameEffectKinds.has(event.cue) ||
        event.pan !== null && (!Number.isFinite(event.pan) || event.pan < -1 || event.pan > 1) ||
        index > 0 && event.seq <= events[index - 1].seq)) throw new Error("protocol");
  if (!validPlot(state.plot)) throw new Error("protocol");
  const payload = state[state.role];
  // BEGIN GENERATED (tools/gen_web_schema.py; do not edit by hand)
  const shapes = {
    bridge: ["navigation", "orders", "threat", "systems", "tactical_summary", "sightings", "crew", "lookout", "route"],
    damage: ["compartments", "teams", "total", "sunk", "stability", "crew"],
    eloka: ["intercepts", "station_down", "status", "hardware"],
    engine: ["propulsion", "machinery", "controls", "environment_effects", "compartments"],
    helicopter: ["asset", "waypoint", "buoys", "buoy_observations", "acoustic", "navigation", "tactical", "target_choices", "readiness", "dip_observations", "dip_environment"],
    lookout: ["side", "available", "manned", "course", "speed_kn", "relative_deg", "fov_deg", "powers", "window_deg", "visibility_nm", "sea_state", "horizon_offset", "horizon_tilt", "motion_pitch", "motion_roll", "sky", "outlines", "calls", "events"],
    opz: ["observations", "fusions", "suggestions", "radar", "defense", "asm_observations", "source_classifications", "radar_blips", "designated_target_ref", "own_assets", "trails"],
    radio: ["observations", "logged_fixes", "logged_bearings", "messages", "station_down", "navigation", "tactical", "tasks", "can_request_ras", "can_contact_report", "can_request_support"],
    sonar: ["observations", "settings", "visualization"],
    uboot: ["navigation", "status", "weapons", "alarms", "contacts", "own_weapons", "designated_target_ref", "feed", "scope", "plant", "esm", "ballast", "damage_control", "threat", "radio"],
    uboot_engine: ["navigation", "status", "weapons", "alarms", "contacts", "own_weapons", "designated_target_ref", "feed", "scope", "plant", "esm", "ballast", "damage_control", "threat", "radio"],
    uboot_esm: ["navigation", "status", "weapons", "alarms", "contacts", "own_weapons", "designated_target_ref", "feed", "scope", "plant", "esm", "ballast", "damage_control", "threat", "radio"],
    uboot_lookout: ["side", "available", "manned", "course", "speed_kn", "relative_deg", "fov_deg", "powers", "window_deg", "visibility_nm", "sea_state", "horizon_offset", "horizon_tilt", "motion_pitch", "motion_roll", "sky", "outlines", "calls", "events"],
    uboot_nav: ["navigation", "status", "weapons", "alarms", "contacts", "own_weapons", "designated_target_ref", "feed", "scope", "plant", "esm", "ballast", "damage_control", "threat", "radio"],
    uboot_radio: ["navigation", "status", "weapons", "alarms", "contacts", "own_weapons", "designated_target_ref", "feed", "scope", "plant", "esm", "ballast", "damage_control", "threat", "radio"],
    uboot_sonar: ["observations", "settings", "visualization"],
    uboot_weapons: ["navigation", "status", "weapons", "alarms", "contacts", "own_weapons", "designated_target_ref", "feed", "scope", "plant", "esm", "ballast", "damage_control", "threat", "radio"],
    weapons: ["inventory", "readiness", "designated_target", "navigation", "tactical", "target_choices", "depth_m", "tubes", "settings", "own_weapons", "active_assets"],
  };
  const tacticalFields = ["ref", "label", "domain", "source", "affiliation", "bearing", "range_nm", "x", "y", "course", "speed_kn", "altitude_m", "observer_x", "observer_y", "quality", "age_s", "bearing_uncertainty_deg", "range_uncertainty_nm", "visual_class", "visual_type"];
  const sonarFields = ["ref", "label", "source", "classification", "profile", "bearing", "range_nm", "x", "y", "depth_m", "course", "speed_kn", "quality", "age_s", "fix_age_s", "bearing_uncertainty_deg", "range_uncertainty_nm", "observer_x", "observer_y", "released_to_opz", "fixes"];
  const radioFields = ["ref", "label", "bearing", "quality", "age_s", "bearing_uncertainty_deg"];
  const radioTaskFields = {
    row: ["id", "type", "state", "name", "persons", "x", "y", "radius_nm", "course", "speed_kn", "bearing", "range_nm", "respond_s", "remaining_s", "progress", "sighted", "verdict", "points", "can_answer"],
    kinds: ["sar", "identify", "datum", "ras", "emcon", "patrol"],
    states: ["offered", "active", "done", "failed", "declined"],
  };
  const crewFields = {
    row: ["on_watch", "watches", "watch_left_s", "turnover", "action_stations", "morale", "effectiveness", "casualties"],
    watch: ["index", "fatigue", "on_duty"],
    casualties: ["wounded", "serious", "returned", "stations", "medic", "spare", "reassign_in_s"],
    casualtyStation: ["station", "gaps", "posts"],
    stations: ["sonar", "weapons", "damage"],
  };
  const mpaFields = {
    row: ["state", "airborne", "x", "y", "course", "bearing", "range_nm", "waypoint_x", "waypoint_y", "station_left_s", "ready_in_s", "sorties_left", "buoys", "torpedoes", "radar", "mad", "buoy_mode", "pattern", "pattern_points", "datalink", "relayed"],
    states: ["BASE", "TRANSIT", "STATION", "RTB"],
  };
  const consortFields = {
    row: ["callsign", "sunk", "datalink", "x", "y", "course", "speed_kn", "bearing", "range_nm", "mode", "working", "station", "point_x", "point_y", "active", "weapons_free", "asroc", "bearings"],
    bearing: ["observer_x", "observer_y", "bearing", "uncertainty_deg", "age_s"],
    modes: ["auto", "formation", "search", "prosecute", "hold"],
    stations: ["starboard", "ahead", "port", "astern"],
  };
  const opzSuggestionFields = ["key", "refs", "bearing", "bearing_delta_deg", "distance_nm", "course_delta_deg", "speed_delta_kn", "class_match"];
  const opzTrailFields = {
    row: ["ref", "points"],
    max: 48,
    points: 24,
  };
  const helicopterTacticalFields = ["ref", "label", "domain", "source", "affiliation", "bearing", "range_nm", "x", "y", "course", "speed_kn", "altitude_m", "observer_x", "observer_y", "quality", "age_s", "bearing_uncertainty_deg", "range_uncertainty_nm", "visual_class", "visual_type", "classification", "released_to_opz"];
  const weatherFields = {
    atmosphere: ["weather", "precipitation", "rain_intensity", "visibility_nm", "sea_state", "wind_from_deg", "wind_kn", "gust_kn", "beaufort", "pressure_hpa", "pressure_tendency_hpa_3h", "pressure_trend", "storm_warning", "air_temp_c", "sea_temp_c", "cloud_cover", "ceiling_ft", "icing", "sun_elevation_deg", "daylight", "moon_phase", "moon_illumination", "time"],
    boatAtmosphere: ["weather", "precipitation", "rain_intensity", "visibility_nm", "sea_state", "wind_from_deg", "wind_kn", "gust_kn", "beaufort", "pressure_hpa", "pressure_tendency_hpa_3h", "pressure_trend", "storm_warning", "air_temp_c", "sea_temp_c", "cloud_cover", "sun_elevation_deg", "daylight", "moon_phase", "moon_illumination", "time"],
    boat: ["mast_radar_nm", "mast_radar_calm_nm", "sighting_nm", "sighting_ref_nm", "ambient_bands_hz", "ambient_excess_db", "snorkel_available", "snorkeling", "snorkel_max_kn", "snorkel_noise_db", "snorkel_lines_hz"],
  };
  const sightFields = {
    sky: ["light", "dusk", "cloud", "precipitation", "intensity", "wind_from_deg", "sun_bearing", "sun_alt_deg", "moon_bearing", "moon_alt_deg", "moon_illumination", "moon_waxing", "glow", "storm", "lightning", "lightning_bearing"],
    glasses: ["course", "speed_kn", "fov_deg", "visibility_nm", "sea_state", "horizon_offset", "horizon_tilt", "motion_pitch", "motion_roll", "sky", "outlines", "events"],
    outline: ["bearing", "span_deg", "cls", "stale", "lights", "elevation_deg", "aob_deg", "model", "way", "range_nm"],
    classes: ["warship", "merchant", "aircraft", "torpedo", "unknown"],
    event: ["type", "bearing", "range_nm", "age_s", "dur_s", "size_m", "level"],
    eventKinds: ["column", "blast", "fire", "sinking"],
    phone: ["side", "available", "manned", "course", "speed_kn", "relative_deg", "fov_deg", "powers", "window_deg", "visibility_nm", "sea_state", "horizon_offset", "horizon_tilt", "motion_pitch", "motion_roll", "sky", "outlines", "calls", "events"],
    phoneOutline: ["bearing", "span_deg", "cls", "stale", "lights", "elevation_deg", "aob_deg", "model", "way", "range_nm", "called"],
    call: ["seq", "age_s", "category", "bearing", "range_nm", "confirmed"],
    callCategories: ["contact", "ship", "warship", "merchant", "aircraft", "submarine", "torpedo"],
  };
  const routeFields = {
    row: ["pattern", "index", "total", "points"],
    point: ["number", "x", "y"],
    patterns: ["manual", "zigzag", "square"],
  };
  const boatFields = {
    plant: ["propulsion", "phase", "battery_kwh", "battery_capacity_kwh", "aip_kwh", "aip_capacity_kwh", "aip_kw", "load_kw", "supply_kw", "net_kw", "empty_s", "full_s", "generator_kw", "fuel_l", "fuel_capacity_l", "charge_rate", "snorkel_rate", "endurance", "air"],
    air: ["o2_pct", "co2_pct", "absorber_pct", "absorber_sets", "candles", "candle_left_s", "level", "efficiency"],
    ballast: ["blowing", "venting", "auto", "pumping", "compressor", "hp_air_bar", "hp_air_max_bar", "blows_left", "mbt_pct", "regulating_kg", "regulating_order_kg", "regulating_capacity_kg", "trim_kg", "trim_order_kg", "trim_capacity_kg", "load_kg", "flooding_kg", "residual_kg", "trim_deg", "drift_mps"],
    ballastFlags: ["blowing", "venting", "auto", "pumping", "compressor"],
    damage: ["power", "pumping", "compartments", "teams", "crew"],
    compartment: ["name", "water_kg", "capacity_kg", "leak_pct", "fire_pct", "chlorine_pct", "closed", "down"],
    dcTeam: ["team", "compartment", "task", "transit_s"],
    compartments: ["bow", "control", "quarters", "battery", "engine", "stern"],
    dcTasks: ["idle", "seal", "pump", "fire"],
    esm: ["mast_up", "mast_s", "mast_time_s", "mast_threat", "mast_radar_nm", "wash", "emitters"],
    esmEmitter: ["number", "label", "bearing", "bearing_uncertainty_deg", "frequency_hz", "band", "prf_hz", "modulation", "signal_db", "trend", "trend_db_min", "age_s", "live", "quality", "classification", "candidates", "range_estimate_nm", "mast_threat", "scan", "scan_period_s", "history", "fix"],
    esmHistory: ["age_s", "x", "y", "bearing"],
    esmFix: ["x", "y", "major_nm", "minor_nm", "axis_deg", "lines", "consistent"],
    esmCandidate: ["name", "role", "fit"],
    threat: ["intercepts", "counts", "loudest_db", "echo_likely", "trend", "layer", "layer_m", "depth_m", "noise", "mast", "esm_count", "advice", "plan", "clock"],
    intercept: ["type", "bearing", "level_db", "age_s"],
    interceptKinds: ["hull", "dipping", "buoy", "splash", "torpedo"],
    advice: ["uboot.advice.torpedo", "uboot.advice.mast_down", "uboot.advice.slow_down", "uboot.advice.measure_layer", "uboot.advice.go_below", "uboot.advice.evade"],
    evadePlan: ["type", "bearing", "course", "speed_kn", "depth_m", "silent", "decoy"],
    radio: ["antenna", "broadcast", "copied", "next_s", "copy", "send", "transmitting", "sitreps", "ack_due", "report", "log", "vlf", "order", "worded", "orders_done", "orders_failed", "buoy", "buoy_payout", "buoy_rx"],
    radioLog: ["seq", "type", "age_s", "number", "ack", "report", "order"],
    radioLogKinds: ["broadcast", "sent", "aborted"],
    radioBuoyStates: ["stowed", "streaming", "out", "recovering", "lost"],
    radioReport: ["x", "y", "radius_nm", "course", "speed_kn", "age_s"],
    radioOrder: ["id", "type", "x", "y", "radius_nm", "left_s"],
    radioOrderKinds: ["area", "report", "silence", "attack", "landing", "supply", "recon"],
  };
  // END GENERATED
  if (!validWeatherStation(state.weather_station, opforRoles.has(state.role) || state.role === "uboot_lookout", weatherFields)) throw new Error("protocol");
  if (!exactKeys(payload, shapes[state.role])) throw new Error("protocol");
  const rowsExact = (rows, maximum, fields) => {
    if (!boundedArray(rows, maximum)) throw new Error("protocol");
    rows.forEach((row) => v2Observation(row, fields));
  };
  const tacticalRows = (rows, maximum, extraFields = []) => {
    if (!boundedArray(rows, maximum)) throw new Error("protocol");
    rows.forEach((row) => {
      v2Observation(row, [...tacticalFields, ...extraFields]);
      if (!validSightingClass(row.visual_class, row.visual_type)) throw new Error("protocol");
      if (row.speed_kn !== null && !finite(row.speed_kn)) throw new Error("protocol");
      if (row.altitude_m !== null && (!finite(row.altitude_m) || row.altitude_m < 0 || row.altitude_m > 30000)) throw new Error("protocol");
    });
  };
  // The patrol aircraft: position and waypoint only while airborne.
  const nullableFinite = (value) => value === null || finite(value);
  const mpaOk = (mpa) => exactKeys(mpa, mpaFields.row) && mpaFields.states.includes(mpa.state) &&
    typeof mpa.airborne === "boolean" && typeof mpa.radar === "boolean" && typeof mpa.mad === "boolean" &&
    typeof mpa.datalink === "boolean" &&
    ["x", "y", "course", "bearing", "range_nm", "waypoint_x", "waypoint_y", "station_left_s", "ready_in_s"]
      .every((key) => nullableFinite(mpa[key]) && (mpa.airborne || key === "ready_in_s" || mpa[key] === null)) &&
    ["sorties_left", "buoys", "torpedoes", "relayed"].every((key) => Number.isInteger(mpa[key]) && mpa[key] >= 0 && mpa[key] <= 64) &&
    ["PASSIVE", "ACTIVE"].includes(mpa.buoy_mode) && ["single", "field", "barrier", "circle"].includes(mpa.pattern) &&
    boundedArray(mpa.pattern_points, 4) && mpa.pattern_points.every((row) => exactKeys(row, ["x", "y"]) && finite(row.x) && finite(row.y));
  // The consort destroyer: commanded own-force state, or null without one.
  const consortOk = (row) => row === null || (exactKeys(row, consortFields.row) &&
    typeof row.callsign === "string" && row.callsign.length > 0 && row.callsign.length <= 40 &&
    ["sunk", "datalink", "active", "weapons_free"].every((key) => typeof row[key] === "boolean") &&
    ["x", "y", "course", "speed_kn", "bearing", "range_nm"].every((key) => finite(row[key])) &&
    ["point_x", "point_y"].every((key) => nullableFinite(row[key])) &&
    consortFields.modes.includes(row.mode) && consortFields.modes.includes(row.working) &&
    consortFields.stations.includes(row.station) &&
    Number.isInteger(row.asroc) && row.asroc >= 0 && row.asroc <= 64 &&
    boundedArray(row.bearings, 8) && row.bearings.every((bearing) => exactKeys(bearing, consortFields.bearing) &&
      consortFields.bearing.every((key) => finite(bearing[key]))));
  // A crew's watch bill: three watches, fatigue and morale 0..1.
  // The eyepieces' sky and the bridge lookout's binoculars (display only).
  const skyOk = (sky) => exactKeys(sky, sightFields.sky) &&
    ["none", "rain", "snow"].includes(sky.precipitation) && typeof sky.moon_waxing === "boolean" &&
    sightFields.sky.every((key) => ["precipitation", "moon_waxing"].includes(key) || finite(sky[key])) &&
    [sky.light, sky.dusk, sky.cloud, sky.intensity, sky.moon_illumination].every((value) => value >= 0 && value <= 1);
  const navLightsOk = (code) => code === null || (typeof code === "string" && /^[LR][012][r-][g-][s-](GW|WR|RWR|GGG|AC)?$/.test(code));
  // Down to -30°: the own helicopter on the flight deck below the bridge (src/ui/own_helo.py).
  const elevationOk = (value) => value === null || (finite(value) && value >= -30 && value <= 90);
  const aobOk = (value) => value === null || (finite(value) && value >= -180 && value <= 180);
  const modelOk = (value) => value === null || (typeof value === "string" && /^[a-z0-9_]{1,32}$/.test(value));
  const wayOk = (value) => value === null || (finite(value) && value >= 0 && value <= 1);
  // What the eye sees happen: water columns, fire, sinkings (display only).
  const sightEventsOk = (rows) => boundedArray(rows, 8) && rows.every((row) => exactKeys(row, sightFields.event) &&
    sightFields.eventKinds.includes(row.type) && finite(row.bearing) && row.bearing >= 0 && row.bearing < 360 &&
    finite(row.range_nm) && row.range_nm >= 0 && finite(row.age_s) && row.age_s >= 0 &&
    finite(row.dur_s) && row.dur_s > 0 && finite(row.size_m) && row.size_m > 0 &&
    finite(row.level) && row.level >= 0 && row.level <= 1);
  const glassesOk = (glasses) => exactKeys(glasses, sightFields.glasses) && skyOk(glasses.sky) && sightEventsOk(glasses.events) &&
    ["course", "speed_kn", "fov_deg", "visibility_nm", "sea_state", "horizon_offset", "horizon_tilt", "motion_pitch", "motion_roll"].every((key) => finite(glasses[key])) &&
    glasses.fov_deg > 0 && glasses.fov_deg <= 180 &&
    boundedArray(glasses.outlines, 16) && glasses.outlines.every((row) => exactKeys(row, sightFields.outline) &&
      finite(row.bearing) && finite(row.span_deg) && row.span_deg > 0 && sightFields.classes.includes(row.cls) &&
      typeof row.stale === "boolean" && navLightsOk(row.lights) && elevationOk(row.elevation_deg) && aobOk(row.aob_deg) && modelOk(row.model) &&
      wayOk(row.way));
  const crewOk = (crew) => exactKeys(crew, crewFields.row) &&
    Number.isInteger(crew.on_watch) && crew.on_watch >= 1 && crew.on_watch <= 3 &&
    Array.isArray(crew.watches) && crew.watches.length === 3 &&
    crew.watches.every((row, index) => exactKeys(row, crewFields.watch) && row.index === index + 1 &&
      finite(row.fatigue) && row.fatigue >= 0 && row.fatigue <= 1 && typeof row.on_duty === "boolean") &&
    (crew.watch_left_s === null || (finite(crew.watch_left_s) && crew.watch_left_s >= 0)) &&
    typeof crew.turnover === "boolean" && typeof crew.action_stations === "boolean" &&
    finite(crew.morale) && crew.morale >= 0 && crew.morale <= 1 &&
    finite(crew.effectiveness) && crew.effectiveness > 0 && crew.effectiveness <= 2 &&
    exactKeys(crew.casualties, crewFields.casualties) &&
    [crew.casualties.wounded, crew.casualties.serious, crew.casualties.returned, crew.casualties.spare]
      .every((value) => Number.isInteger(value) && value >= 0 && value <= 10000) &&
    Array.isArray(crew.casualties.stations) && crew.casualties.stations.length === crewFields.stations.length &&
    crew.casualties.stations.every((row, index) => exactKeys(row, crewFields.casualtyStation) &&
      row.station === crewFields.stations[index] && Number.isInteger(row.posts) && row.posts > 0 && row.posts <= 32 &&
      Number.isInteger(row.gaps) && row.gaps >= 0 && row.gaps <= row.posts) &&
    (crew.casualties.medic === null || crewFields.stations.includes(crew.casualties.medic)) &&
    finite(crew.casualties.reassign_in_s) && crew.casualties.reassign_in_s >= 0;
  // A phone lookout: its eyepiece, what its eye has (called or not) and its calls.
  const phoneOk = (view) => exactKeys(view, sightFields.phone) && skyOk(view.sky) && sightEventsOk(view.events) &&
    view.side === (state.role === "lookout" ? "frigate" : "boat") &&
    ["available", "manned"].every((key) => typeof view[key] === "boolean") &&
    ["course", "speed_kn", "fov_deg", "visibility_nm", "sea_state", "horizon_offset", "horizon_tilt"].every((key) => finite(view[key])) &&
    ["relative_deg", "window_deg", "motion_pitch", "motion_roll"].every((key) => nullableFinite(view[key])) &&
    view.fov_deg > 0 && view.fov_deg <= 180 &&
    boundedArray(view.powers, 4) && view.powers.length >= 1 && view.powers.every((value) => finite(value) && value >= 1 && value <= 16) &&
    boundedArray(view.outlines, 24) && view.outlines.every((row) => exactKeys(row, sightFields.phoneOutline) &&
      finite(row.bearing) && finite(row.span_deg) && row.span_deg > 0 && sightFields.classes.includes(row.cls) &&
      typeof row.stale === "boolean" && typeof row.called === "boolean" && navLightsOk(row.lights) &&
      elevationOk(row.elevation_deg) && aobOk(row.aob_deg) && modelOk(row.model) && wayOk(row.way) &&
      (row.range_nm === null || (finite(row.range_nm) && row.range_nm >= 0))) &&
    boundedArray(view.calls, 8) && view.calls.every((row) => exactKeys(row, sightFields.call) &&
      Number.isSafeInteger(row.seq) && row.seq >= 1 && finite(row.age_s) && row.age_s >= 0 &&
      sightFields.callCategories.includes(row.category) && finite(row.bearing) && row.bearing >= 0 && row.bearing < 360 &&
      (row.range_nm === null || (finite(row.range_nm) && row.range_nm >= 0)) && typeof row.confirmed === "boolean");
  // The hit picture (src/core/hit_view.py): null, or a hit in sight (the
  // side's own eyepiece toward it) or only heard (its bearing).
  // Noise discipline (src/core/noise_discipline.py): the crew's held
  // microphone level and its thresholds.
  const noise = state.crew_noise;
  if (!exactKeys(noise, ["voice", "safe", "loud", "max", "quiet"]) ||
      !Number.isSafeInteger(noise.max) || noise.max < 1 || noise.max > 100 ||
      ![noise.voice, noise.safe, noise.loud].every((value) => Number.isSafeInteger(value) && value >= 0 && value <= noise.max) ||
      noise.safe > noise.loud || typeof noise.quiet !== "boolean") throw new Error("protocol");
  const hit = state.hit_view;
  const outlineOk = (row) => exactKeys(row, sightFields.outline) &&
    finite(row.bearing) && finite(row.span_deg) && row.span_deg > 0 && sightFields.classes.includes(row.cls) &&
    typeof row.stale === "boolean" && navLightsOk(row.lights) && elevationOk(row.elevation_deg) && aobOk(row.aob_deg) &&
    modelOk(row.model) && wayOk(row.way);
  if (hit !== null && (!exactKeys(hit, ["mode", "kind", "bearing", "age_s", "fov_deg", "visibility_nm", "sea_state", "sky", "outlines", "events"]) ||
      ![["sight", ["column", "blast", "sinking"]], ["sonar", ["hit", "breakup"]]].some(([mode, kinds]) => hit.mode === mode && kinds.includes(hit.kind)) ||
      !finite(hit.bearing) || hit.bearing < 0 || hit.bearing >= 360 || !finite(hit.age_s) || hit.age_s < 0 ||
      !finite(hit.fov_deg) || hit.fov_deg <= 0 || hit.fov_deg > 90 ||
      (hit.mode === "sight" ? !finite(hit.visibility_nm) || !finite(hit.sea_state) || !skyOk(hit.sky) ||
        !boundedArray(hit.outlines, 12) || !hit.outlines.every(outlineOk) || !sightEventsOk(hit.events)
        : hit.visibility_nm !== null || hit.sea_state !== null || hit.sky !== null ||
          !Array.isArray(hit.outlines) || hit.outlines.length || !Array.isArray(hit.events) || hit.events.length)))
    throw new Error("protocol");
  if (lookoutRoles.includes(state.role)) {
    if (!phoneOk(payload)) throw new Error("protocol");
  } else if (state.role === "bridge") {
    if (!crewOk(payload.crew) || !glassesOk(payload.lookout)) throw new Error("protocol");
    // The autopilot route: the waypoints still ahead, numbered from 1.
    const route = payload.route;
    if (!exactKeys(route, routeFields.row) || !routeFields.patterns.includes(route.pattern) ||
        !Number.isInteger(route.total) || route.total < 0 || route.total > 16 ||
        !Number.isInteger(route.index) || route.index < 0 || route.index > route.total ||
        !boundedArray(route.points, 16) || route.points.length !== route.total - route.index ||
        route.points.some((row, index) => !exactKeys(row, routeFields.point) ||
          row.number !== route.index + index + 1 || !finite(row.x) || !finite(row.y))) throw new Error("protocol");
    if (!exactKeys(payload.navigation, ["x", "y", "course", "speed", "target_course", "target_speed", "rudder_angle", "yaw_rate", "turn_radius_nm"])) throw new Error("protocol");
    if (!exactKeys(payload.orders, ["station_down", "speed_max_kn", "telegraph", "noise", "cavitating"]) ||
        typeof payload.orders.station_down !== "boolean" || !finite(payload.orders.speed_max_kn) ||
        typeof payload.orders.cavitating !== "boolean" || payload.orders.speed_max_kn < 0 || payload.orders.speed_max_kn > 100 ||
        !exactKeys(payload.threat, ["observations", "count", "average_flood", "torpedoes"]) ||
        !boundedArray(payload.threat.torpedoes, 8) || payload.threat.torpedoes.some((row) =>
          !exactKeys(row, ["source", "bearing", "age_s", "tti_s"]) || !["transient", "seeker", "locked", "flood", "classified"].includes(row.source) ||
          (row.tti_s !== null && (!finite(row.tti_s) || row.tti_s < 0)) ||
          !finite(row.bearing) || row.bearing < 0 || row.bearing >= 360 || !finite(row.age_s) || row.age_s < 0) ||
        !boundedArray(payload.systems, 32) || payload.systems.some((row) => !exactKeys(row, ["key", "state", "down"]) || typeof row.down !== "boolean")) throw new Error("protocol");
    tacticalRows(payload.threat.observations, 128);
    tacticalRows(payload.tactical_summary, 256);
    if (!boundedArray(payload.sightings, 24) || payload.sightings.some((row) =>
        !exactKeys(row, ["time", "sighted", "code", "type", "bearing", "range_nm", "lights"]) || typeof row.time !== "string" || row.time.length > 8 ||
        !sightingLightsOk(row) ||
        (row.code === null ? !sightingKinds.includes(row.sighted) || row.type !== null : row.sighted !== null || !validSightingClass(row.code, row.type)) ||
        !finite(row.bearing) || row.bearing < 0 || row.bearing >= 360 || !finite(row.range_nm) || row.range_nm < 0 || row.range_nm > 1000)) throw new Error("protocol");
  } else if (isSonar(state.role)) {
    rowsExact(payload.observations, 256, sonarFields);
    const settings = payload.settings;
    if (!exactKeys(settings, ["mode", "page", "listen_bearing", "focus_ref", "target_ref", "station_down", "tow", "vds", "bt", "ping", "tma_enabled", "gain_db", "band_preset", "band_hz", "notch", "peak_hold", "harmonic_hz", "harmonic_candidates_hz", "audio_enabled", "volume", "quiet_mode", "tools"]) ||
        !["BOW", "TOWED", "VDS"].includes(settings.mode) || typeof settings.station_down !== "boolean" ||
        !exactKeys(settings.tools, ["assist", "lofar_cursor_hz", "demon_cursor_hz", "integration_s", "vernier", "shaft_hz", "blade_hz", "operator_notch_hz", "demon_band_hz", "heterodyne_hz", "library_marks", "library"]) ||
        !Number.isInteger(settings.tools.library_marks) || settings.tools.library_marks < 0 || settings.tools.library_marks > 3 ||
        !boundedArray(settings.tools.library, 3) || settings.tools.library.some((row) => !exactKeys(row, ["name", "fit"]) || typeof row.name !== "string" || row.name.length > 48 || !finite(row.fit) || row.fit < 0 || row.fit > 1) ||
        !boundedArray(settings.tools.demon_band_hz, 2) || settings.tools.demon_band_hz.some((value) => !finite(value)) || !finite(settings.tools.heterodyne_hz) ||
        typeof settings.tools.assist !== "boolean" || typeof settings.tools.vernier !== "boolean" ||
        ![2, 8, 16, 64].includes(settings.tools.integration_s) ||
        [settings.tools.lofar_cursor_hz, settings.tools.demon_cursor_hz].some((value) => !finite(value) || value < 0 || value > 300) ||
        [settings.tools.shaft_hz, settings.tools.blade_hz, settings.tools.operator_notch_hz].some((value) => value !== null && (!finite(value) || value < 0 || value > 300)) ||
        !exactKeys(settings.tow, ["state", "payout", "available", "handling_ok", "speed_kn", "speed_min_kn", "speed_max_kn", "depth_m", "depth_target_m"]) ||
        !finite(settings.tow.speed_kn) || !finite(settings.tow.speed_min_kn) || !finite(settings.tow.speed_max_kn) ||
        !exactKeys(settings.vds, ["state", "payout", "available", "handling_ok", "speed_min_kn", "speed_max_kn", "max_sea_state", "depth_m", "depth_target_m"]) ||
        [settings.vds.payout, settings.vds.speed_min_kn, settings.vds.speed_max_kn, settings.vds.max_sea_state,
          settings.vds.depth_m, settings.vds.depth_target_m].some((value) => !finite(value)) ||
        settings.vds.payout < 0 || settings.vds.payout > 1 || settings.vds.depth_m < 0 || settings.vds.depth_m > 1000 ||
        typeof settings.vds.state !== "string" || settings.vds.state.length > 32 ||
        !exactKeys(settings.bt, ["ready", "cooldown_s", "thermocline_m"]) ||
        !exactKeys(settings.ping, ["ready", "cooldown_s"]) ||
        settings.tow.speed_kn < 0 || settings.tow.speed_kn > 100 || settings.tow.speed_min_kn < 0 ||
        settings.tow.speed_max_kn > 100 || settings.tow.speed_min_kn > settings.tow.speed_max_kn ||
        !boundedArray(settings.band_hz, 2) || settings.band_hz.length !== 2 ||
        !boundedArray(settings.harmonic_candidates_hz, 64) ||
        [settings.tow.available, settings.tow.handling_ok, settings.vds.available, settings.vds.handling_ok, settings.bt.ready, settings.ping.ready,
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
        !exactKeys(visual.receiver, ["array", "listen_bearing", "beam_width_deg", "listen_mode", "focus_locked", "audio_enabled", "own_course", "baffle_half_deg"]) || !finite(visual.receiver.baffle_half_deg) || !["BROADBAND", "FILTERED", "HETERODYNE"].includes(visual.receiver.listen_mode) || typeof visual.receiver.focus_locked !== "boolean" || typeof visual.receiver.audio_enabled !== "boolean") throw new Error("protocol");
  } else if (isBoatCommand(state.role)) {
    const nav = payload.navigation, status = payload.status, weapons = payload.weapons, alarms = payload.alarms;
    const navNumbers = ["x", "y", "course", "target_course", "speed", "target_speed", "depth_m", "target_depth_m", "safe_depth_m", "max_depth_m", "crush_depth_m", "max_speed_kn", "noise", "est_x", "est_y", "dr_error_nm", "fix_age_s", "fix_progress"];
    if (!exactKeys(nav, [...navNumbers, "water_depth_m", "under_keel_m", "obstacle_ahead_nm", "depth_presets", "cavitating", "route", "sounder"]) || navNumbers.some((key) => !finite(nav[key])) ||
        !exactKeys(nav.sounder, ["past", "ahead", "scale_m", "window_s", "ahead_nm", "warn_m", "caution_m"]) ||
        [nav.sounder.scale_m, nav.sounder.window_s, nav.sounder.ahead_nm, nav.sounder.warn_m, nav.sounder.caution_m].some((value) => !finite(value) || value <= 0) ||
        !boundedArray(nav.sounder.past, 64) || nav.sounder.past.some((row) => !boundedArray(row, 3) || row.length !== 3 || !row.every(finite)) ||
        !boundedArray(nav.sounder.ahead, 32) || nav.sounder.ahead.some((row) => !boundedArray(row, 2) || row.length !== 2 || !row.every(finite)) ||
        !exactKeys(nav.route, ["points", "index", "type", "active"]) || !boundedArray(nav.route.points, 16) ||
        nav.route.points.some((point) => !boundedArray(point, 2) || point.length !== 2 || !point.every(finite)) ||
        !Number.isInteger(nav.route.index) || nav.route.index < 0 || !["manual", "zigzag", "square"].includes(nav.route.type) ||
        typeof nav.route.active !== "boolean" ||
        !exactKeys(nav.depth_presets, ["periscope", "snorkel", "above_layer", "below_layer", "deep", "layer"]) ||
        Object.values(nav.depth_presets).some((value) => value !== null && (!finite(value) || value < 0 || value > 1000)) ||
        [nav.water_depth_m, nav.under_keel_m, nav.obstacle_ahead_nm].some((value) => value !== null && !finite(value)) || typeof nav.cavitating !== "boolean" ||
        !exactKeys(status, ["state", "damage", "emergency_ascent", "blow_available", "battery", "endurance_phase", "transmitting", "snorkel_available", "snorkeling", "silent", "quiet", "bottomed", "surfaced", "mast"]) ||
        [status.snorkel_available, status.snorkeling, status.silent, status.quiet, status.bottomed, status.surfaced, status.mast].some((value) => typeof value !== "boolean") ||
        !["manual", "ai", "sinking", "sunk"].includes(status.state) || !finite(status.damage) ||
        [status.emergency_ascent, status.blow_available, status.transmitting].some((value) => typeof value !== "boolean") ||
        (status.battery !== null && !finite(status.battery)) ||
        (status.endurance_phase !== null && (typeof status.endurance_phase !== "string" || status.endurance_phase.length > 16)) ||
        !exactKeys(weapons, ["torpedoes", "tubes_ready", "tubes", "reload_s", "ready", "reason", "arc_center_deg", "arc_width_deg", "decoys", "decoy_ready", "pattern", "enable_nm"]) ||
        !["straight", "snake", "circle", "helix"].includes(weapons.pattern) || !finite(weapons.enable_nm) ||
        !boundedArray(weapons.tubes, 32) || weapons.tubes.some((row) => !exactKeys(row, ["state", "seconds"]) ||
          !["empty", "loading", "dry", "flooding", "flooded"].includes(row.state) || (row.seconds !== null && !finite(row.seconds))) ||
        [weapons.torpedoes, weapons.tubes_ready, weapons.decoys].some((value) => !Number.isInteger(value) || value < 0) ||
        typeof weapons.ready !== "boolean" || typeof weapons.decoy_ready !== "boolean" ||
        (weapons.reason !== null && !["not_ready", "no_torpedoes", "reloading", "out_of_arc", "uboot_compartment_down", "uboot_tube_dry"].includes(weapons.reason)) ||
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
    // The periscope: line of sight, light and the crew's own sightings (no target truth).
    const scope = payload.scope;
    const scopeNumbers = ["relative_deg", "bearing", "course", "speed_kn", "fov_deg", "window_deg", "visibility_nm", "sea_state", "horizon_offset", "horizon_tilt"];
    if (!exactKeys(scope, ["available", "night", ...scopeNumbers, "sky", "sightings", "events"]) || !skyOk(scope.sky) ||
        !sightEventsOk(scope.events) ||
        typeof scope.available !== "boolean" || typeof scope.night !== "boolean" ||
        scopeNumbers.some((key) => !finite(scope[key])) || scope.relative_deg < 0 || scope.relative_deg >= 360 ||
        !boundedArray(scope.sightings, 16) || scope.sightings.some((row) =>
          !exactKeys(row, ["ref", "category", "cls", "bearing", "span_deg", "quality", "age_s", "range_nm", "range_sigma_nm", "range_age_s", "solution", "lights", "elevation_deg", "aob_deg", "model", "way"]) || !navLightsOk(row.lights) ||
          !elevationOk(row.elevation_deg) || !aobOk(row.aob_deg) || !modelOk(row.model) || !wayOk(row.way) ||
          (row.solution !== null && (!exactKeys(row.solution, ["marks", "course", "speed_kn", "lead_deg", "run_s", "quality"]) ||
            !Number.isSafeInteger(row.solution.marks) || row.solution.marks < 1 || row.solution.marks > 6 ||
            [row.solution.course, row.solution.speed_kn, row.solution.lead_deg, row.solution.run_s].some((value) => value !== null && !finite(value)) ||
            !finite(row.solution.quality))) ||
          typeof row.ref !== "string" || row.ref.length > 16 || !["SURFACE", "FLG", "TORP"].includes(row.category) ||
          !["warship", "merchant", "aircraft", "torpedo", "unknown"].includes(row.cls) ||
          [row.bearing, row.span_deg, row.quality].some((value) => !finite(value)) || (row.age_s !== null && !finite(row.age_s)) ||
          [row.range_nm, row.range_sigma_nm, row.range_age_s].some((value) => value !== null && !finite(value)))) throw new Error("protocol");
    // The boat's plant and stores: own-ship numbers (null where the boat has none).
    const plant = payload.plant;
    const plantNumbers = boatFields.plant.filter((key) => !["propulsion", "phase", "charge_rate", "snorkel_rate", "endurance", "air"].includes(key));
    const air = plant && plant.air;
    const airNumbers = ["o2_pct", "co2_pct", "absorber_pct", "candle_left_s", "efficiency"];
    if (!exactKeys(plant, boatFields.plant) || !["nuclear", "diesel", "aip"].includes(plant.propulsion) ||
        (plant.phase !== null && (typeof plant.phase !== "string" || plant.phase.length > 16)) ||
        plantNumbers.some((key) => plant[key] !== null && !finite(plant[key])) ||
        [plant.charge_rate, plant.snorkel_rate].some((value) => value !== null && !["full", "half", "vent"].includes(value)) ||
        !boundedArray(plant.endurance, 8) || plant.endurance.some((row) => !exactKeys(row, ["speed_kn", "hours"]) || !finite(row.speed_kn) || (row.hours !== null && !finite(row.hours))) ||
        (air !== null && (!exactKeys(air, boatFields.air) || airNumbers.some((key) => !finite(air[key])) ||
          [air.absorber_sets, air.candles].some((value) => !Number.isInteger(value) || value < 0) ||
          !["ok", "caution", "danger"].includes(air.level))) ||
        (plant.propulsion === "nuclear") !== (air === null)) throw new Error("protocol");
    // Tanks, trim and air bottles: own-ship flags and numbers.
    const ballast = payload.ballast;
    if (!exactKeys(ballast, boatFields.ballast) ||
        boatFields.ballastFlags.some((key) => typeof ballast[key] !== "boolean") ||
        boatFields.ballast.filter((key) => !boatFields.ballastFlags.includes(key)).some((key) => !finite(ballast[key])) ||
        !Number.isInteger(ballast.blows_left) || ballast.blows_left < 0) throw new Error("protocol");
    // Compartments and damage-control teams: own-ship state, closed vocabulary.
    const damage = payload.damage_control;
    if (!exactKeys(damage, boatFields.damage) || !crewOk(damage.crew) ||
        typeof damage.power !== "boolean" || typeof damage.pumping !== "boolean" ||
        !Array.isArray(damage.compartments) || damage.compartments.length !== boatFields.compartments.length ||
        damage.compartments.some((row, index) => !exactKeys(row, boatFields.compartment) ||
          row.name !== boatFields.compartments[index] ||
          typeof row.closed !== "boolean" || typeof row.down !== "boolean" ||
          ["water_kg", "capacity_kg", "leak_pct", "fire_pct", "chlorine_pct"].some((key) => !finite(row[key]))) ||
        !Array.isArray(damage.teams) || damage.teams.length !== 2 ||
        damage.teams.some((row, index) => !exactKeys(row, boatFields.dcTeam) || row.team !== index ||
          !boatFields.compartments.includes(row.compartment) || !boatFields.dcTasks.includes(row.task) ||
          !finite(row.transit_s))) throw new Error("protocol");
    // The boat's own ESM picture: measured parameters, own-position history,
    // crew cross-fix and library classification (never identity or position).
    const esm = payload.esm;
    const nullableNumber = (value) => value === null || finite(value);
    const candidateOk = (row) => exactKeys(row, boatFields.esmCandidate) && typeof row.name === "string" && row.name.length <= 64 &&
      typeof row.role === "string" && row.role.length <= 32 && ["good", "fair", "poor"].includes(row.fit);
    if (!exactKeys(esm, boatFields.esm) || typeof esm.mast_up !== "boolean" || typeof esm.mast_threat !== "boolean" ||
        !nullableNumber(esm.mast_s) || !finite(esm.mast_time_s) || !finite(esm.mast_radar_nm) || !finite(esm.wash) ||
        !boundedArray(esm.emitters, 16) || esm.emitters.some((row) => !exactKeys(row, boatFields.esmEmitter) ||
          !Number.isSafeInteger(row.number) || row.number < 1 || typeof row.label !== "string" || row.label.length > 24 ||
          ["bearing", "bearing_uncertainty_deg", "frequency_hz", "signal_db", "quality"].some((key) => !finite(row[key])) ||
          [row.prf_hz, row.trend_db_min, row.age_s, row.range_estimate_nm, row.scan_period_s].some((value) => !nullableNumber(value)) ||
          ![null, "rotating", "steady"].includes(row.scan) || (row.scan === null) !== (row.scan_period_s === null) ||
          !["a_c", "d", "e_f", "g_h", "i_j", "k"].includes(row.band) ||
          !["continuous_wave", "frequency_agile", "pulse", "pulse_doppler", "unknown"].includes(row.modulation) ||
          ![null, "rising", "steady", "falling"].includes(row.trend) ||
          typeof row.live !== "boolean" || typeof row.mast_threat !== "boolean" ||
          (row.classification !== null && !candidateOk(row.classification)) ||
          !boundedArray(row.candidates, 8) || !row.candidates.every(candidateOk) ||
          !boundedArray(row.history, 16) || row.history.some((item) => !exactKeys(item, boatFields.esmHistory) ||
            ["x", "y", "bearing"].some((key) => !finite(item[key])) || !nullableNumber(item.age_s)) ||
          (row.fix !== null && (!exactKeys(row.fix, boatFields.esmFix) ||
            ["x", "y", "major_nm", "minor_nm", "axis_deg"].some((key) => !finite(row.fix[key])) ||
            !Number.isInteger(row.fix.lines) || typeof row.fix.consistent !== "boolean")))) throw new Error("protocol");
    // Counter-detection picture: the boat's own intercepts and own state only.
    const threat = payload.threat;
    const plan = threat && threat.plan;
    if (!exactKeys(threat, boatFields.threat) || !exactKeys(threat.counts, boatFields.interceptKinds) ||
        boatFields.interceptKinds.some((kind) => !Number.isInteger(threat.counts[kind]) || threat.counts[kind] < 0) ||
        !boundedArray(threat.intercepts, 12) || threat.intercepts.some((row) => !exactKeys(row, boatFields.intercept) ||
          !boatFields.interceptKinds.includes(row.type) || !finite(row.bearing) || !finite(row.age_s) ||
          !nullableNumber(row.level_db)) ||
        ![threat.loudest_db, threat.layer_m].every(nullableNumber) || !finite(threat.depth_m) ||
        typeof threat.echo_likely !== "boolean" || typeof threat.mast !== "boolean" ||
        ![null, "rising", "steady", "falling"].includes(threat.trend) ||
        !["unknown", "in", "above", "below"].includes(threat.layer) ||
        !["cavitating", "snorkel", "quiet", "loud", "moderate"].includes(threat.noise) ||
        !Number.isInteger(threat.esm_count) || threat.esm_count < 0 ||
        !boundedArray(threat.advice, 4) || !threat.advice.every((key) => boatFields.advice.includes(key)) ||
        (plan !== null && (!exactKeys(plan, boatFields.evadePlan) || !["torpedo", "ping"].includes(plan.type) ||
          ["bearing", "course", "speed_kn", "depth_m"].some((key) => !finite(plan[key])) ||
          typeof plan.silent !== "boolean" || typeof plan.decoy !== "boolean")) ||
        (threat.clock !== null && (!exactKeys(threat.clock, ["bearing", "tti_s"]) ||
          !finite(threat.clock.bearing) || !finite(threat.clock.tti_s) || threat.clock.tti_s < 0))) throw new Error("protocol");
    // Radio room: schedule, own transmissions and HQ's (modelled) contact report.
    const radio = payload.radio;
    const radioReport = (report) => report === null || (exactKeys(report, boatFields.radioReport) &&
      ["x", "y", "radius_nm", "course", "speed_kn"].every((key) => finite(report[key])) && nullableNumber(report.age_s));
    if (!exactKeys(radio, boatFields.radio) ||
        ["antenna", "copied", "transmitting", "ack_due"].some((key) => typeof radio[key] !== "boolean") ||
        !Number.isInteger(radio.broadcast) || radio.broadcast < 0 || !Number.isInteger(radio.sitreps) || radio.sitreps < 0 ||
        !finite(radio.next_s) || !nullableNumber(radio.copy) || !nullableNumber(radio.send) || !radioReport(radio.report) ||
        !boundedArray(radio.log, 12) || radio.log.some((row) => !exactKeys(row, boatFields.radioLog) ||
          !Number.isInteger(row.seq) || !boatFields.radioLogKinds.includes(row.type) || !nullableNumber(row.age_s) ||
          (row.number !== null && !Number.isInteger(row.number)) || typeof row.ack !== "boolean" || !radioReport(row.report) ||
          (row.order !== null && !Number.isInteger(row.order))) ||
        typeof radio.vlf !== "boolean" || (radio.worded !== null && typeof radio.worded !== "string") ||
        !Number.isInteger(radio.orders_done) || !Number.isInteger(radio.orders_failed) ||
        !boatFields.radioBuoyStates.includes(radio.buoy) || !finite(radio.buoy_payout) || typeof radio.buoy_rx !== "boolean" ||
        (radio.order !== null && (!exactKeys(radio.order, boatFields.radioOrder) || !Number.isInteger(radio.order.id) ||
          !boatFields.radioOrderKinds.includes(radio.order.type) || !finite(radio.order.left_s) ||
          ["x", "y", "radius_nm"].some((key) => !nullableNumber(radio.order[key]))))) throw new Error("protocol");
  } else if (state.role === "weapons") {
    if (!exactKeys(payload.settings, ["torpedo_type", "choices", "pattern", "enable_nm", "salvo"]) ||
        !boundedArray(payload.settings.choices, 8) ||
        !payload.settings.choices.every((row) => exactKeys(row, ["key", "name", "stock", "loaded"])) ||
        !["snake", "circle", "helix"].includes(payload.settings.pattern) || ![1, 2].includes(payload.settings.salvo) ||
        !exactKeys(payload.inventory, ["torpedoes", "vls", "ciws", "aa", "chaff_ready", "nixies", "asroc", "depth_charges", "rbu"]) ||
        !exactKeys(payload.readiness, ["station_down", "roe", "ciws_ready", "rbu_ready", "torpedo_warning", "aa_ready", "state", "interlock", "reload_s"]) ||
        (payload.designated_target !== null && !exactKeys(payload.designated_target, ["ref", "label", "domain", "source", "affiliation", "classification", "bearing", "range_nm", "x", "y", "depth_m", "course", "speed_kn", "quality", "age_s", "fix_age_s", "bearing_uncertainty_deg", "range_uncertainty_nm"])) ||
        !exactKeys(payload.navigation, ["x", "y", "course", "speed", "target_course", "target_speed", "rudder_angle", "yaw_rate", "turn_radius_nm"]) ||
        !boundedArray(payload.tubes, 16) || payload.tubes.some((row) => !exactKeys(row, ["tube", "state", "reload_s"])) ||
        !boundedArray(payload.own_weapons, 96) || payload.own_weapons.some((row) => !exactKeys(row, ["ref", "x", "y", "depth_m", "course", "state"])) ||
        !boundedArray(payload.active_assets, 104) || payload.active_assets.some((row) => !exactKeys(row, ["ref", "x", "y", "depth_m", "course", "state"]))) throw new Error("protocol");
    tacticalRows(payload.tactical, 128);
    rowsExact(payload.target_choices, 128, ["ref", "label", "domain", "source", "affiliation", "classification", "bearing", "range_nm", "x", "y", "depth_m", "course", "speed_kn", "quality", "age_s", "fix_age_s", "bearing_uncertainty_deg", "range_uncertainty_nm"]);
  } else if (state.role === "damage") {
    if (!crewOk(payload.crew) || !boundedArray(payload.compartments, 16) || payload.compartments.some((row) => !exactKeys(row, ["key", "name", "state", "flood", "fire", "leak", "inflow", "repairable", "trend"]) || typeof row.repairable !== "boolean" || !["none", "open", "patched"].includes(row.leak) || !finite(row.inflow) || !exactKeys(row.trend, ["flood_rate", "fire_rate", "repairable"])) ||
        !boundedArray(payload.teams, 16) || payload.teams.some((row) => !exactKeys(row, ["team", "compartment", "transit_s"]) || !finite(row.transit_s) || row.transit_s < 0) ||
        !exactKeys(payload.stability, ["list_deg", "draft_m", "trim_deg", "counterflood_room", "can_counterflood"]) || !finite(payload.stability.draft_m) ||
        typeof payload.stability.can_counterflood !== "boolean") throw new Error("protocol");
  } else if (state.role === "opz") {
    tacticalRows(payload.observations, 256);
    tacticalRows(payload.fusions, 32, ["members"]);
    const rawRefs = new Set(payload.observations.map((row) => row.ref));
    const pictureRefs = new Set([...rawRefs, ...payload.fusions.map((row) => row.ref)]);
    if (!boundedArray(payload.suggestions, 4) || payload.suggestions.some((row) => !exactKeys(row, opzSuggestionFields) ||
        !Array.isArray(row.refs) || row.refs.length !== 2 || row.refs[0] === row.refs[1] ||
        row.refs.some((ref) => typeof ref !== "string" || !rawRefs.has(ref)) || row.key !== row.refs.join("+") ||
        !finite(row.bearing) || !finite(row.bearing_delta_deg) || row.bearing_delta_deg < 0 ||
        !(row.distance_nm === null || (finite(row.distance_nm) && row.distance_nm >= 0)) ||
        !(row.course_delta_deg === null || (finite(row.course_delta_deg) && row.course_delta_deg >= 0)) ||
        !(row.speed_delta_kn === null || (finite(row.speed_delta_kn) && row.speed_delta_kn >= 0)) ||
        !(row.class_match === null || typeof row.class_match === "boolean"))) throw new Error("protocol");
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
         !boundedArray(payload.trails, opzTrailFields.max) || payload.trails.some((row) => !exactKeys(row, opzTrailFields.row) ||
           !pictureRefs.has(row.ref) || !boundedArray(row.points, opzTrailFields.points) ||
           row.points.some((point) => !Array.isArray(point) || point.length !== 3 || !point.every(finite) || point[2] < 0)) ||
         !boundedArray(payload.radar_blips, 16) || payload.radar_blips.some((row) => !exactKeys(row, ["ref", "x", "y", "age_s"]) ||
           typeof row.ref !== "string" || !/^blip-[0-9]{1,18}$/.test(row.ref) || [row.x, row.y, row.age_s].some((value) => !finite(value)))) throw new Error("protocol");
    tacticalRows(payload.asm_observations, 128);
    if (payload.designated_target_ref !== null && (typeof payload.designated_target_ref !== "string" || !pictureRefs.has(payload.designated_target_ref))) throw new Error("protocol");
    if (!exactKeys(payload.own_assets, ["ship", "helicopter", "mpa", "consort", "weapons"]) || !mpaOk(payload.own_assets.mpa) ||
        !consortOk(payload.own_assets.consort) ||
        !boundedArray(payload.own_assets.weapons, 104) || payload.own_assets.weapons.some((row) => !exactKeys(row, ["ref", "x", "y", "depth_m", "course", "state"])) ||
        !exactKeys(payload.own_assets.ship, ["x", "y", "course", "speed", "target_course", "target_speed", "rudder_angle", "yaw_rate", "turn_radius_nm"]) ||
        !exactKeys(payload.own_assets.helicopter, ["state", "airborne", "x", "y", "course", "fuel_s", "torpedoes", "buoys", "hovering", "dip_state", "dip_depth_m", "dip_depth_target_m", "dip_water_depth_m", "dip_ping_ready", "dip_ping_cooldown_s"])) throw new Error("protocol");
  } else if (state.role === "radio") {
    rowsExact(payload.observations, 256, [...radioFields, "frequency_khz", "propagation", "can_capture"]);
    if (payload.observations.some((row) => (row.frequency_khz !== null && (!finite(row.frequency_khz) || row.frequency_khz <= 0)) ||
        ![null, "GROUND", "SKY"].includes(row.propagation))) throw new Error("protocol");
    if (!boundedArray(payload.logged_fixes, 256) || payload.logged_fixes.some((row) => !exactKeys(row, ["ref", "x", "y", "uncertainty_nm", "age_s", "covariance_nm2"]) || row.covariance_nm2 !== null && (!boundedArray(row.covariance_nm2, 3) || row.covariance_nm2.length !== 3)) ||
        !boundedArray(payload.logged_bearings, 256) || payload.logged_bearings.some((row) => !exactKeys(row, ["ref", "bearing", "observer_x", "observer_y", "age_s"])) ||
        !boundedArray(payload.messages, 40) || payload.messages.some((row) => !exactKeys(row, ["stamp", "text"])) ||
        typeof payload.station_down !== "boolean" || typeof payload.can_request_ras !== "boolean" ||
        typeof payload.can_contact_report !== "boolean" || typeof payload.can_request_support !== "boolean" ||
        payload.observations.some((row) => typeof row.can_capture !== "boolean") ||
        !exactKeys(payload.navigation, ["x", "y", "course", "speed", "target_course", "target_speed", "rudder_angle", "yaw_rate", "turn_radius_nm"])) throw new Error("protocol");
    tacticalRows(payload.tactical, 128);
    const nullableFinite = (value) => value === null || finite(value);
    if (!boundedArray(payload.tasks, 8) || payload.tasks.some((row) => !exactKeys(row, radioTaskFields.row) ||
        !Number.isSafeInteger(row.id) || row.id < 1 || !radioTaskFields.kinds.includes(row.type) ||
        !radioTaskFields.states.includes(row.state) || (row.name !== null && (typeof row.name !== "string" || row.name.length > 24)) ||
        !Number.isInteger(row.persons) || row.persons < 0 || [row.x, row.y, row.radius_nm, row.bearing, row.range_nm, row.progress].some((value) => !finite(value)) ||
        [row.course, row.speed_kn, row.respond_s, row.remaining_s].some((value) => !nullableFinite(value)) ||
        typeof row.sighted !== "boolean" || typeof row.can_answer !== "boolean" || ![null, "clear", "suspect"].includes(row.verdict) ||
        !Number.isInteger(row.points))) throw new Error("protocol");
  } else if (state.role === "engine") {
    if (!exactKeys(payload.propulsion, ["course", "target_course", "speed", "target_speed", "telegraph", "rpm", "quiet_mode", "plant_mode", "cavitating", "fuel_kg", "fuel_capacity_kg", "fuel_burn_kg_h", "fuel_endurance_h", "fuel_range_nm"]) ||
        !["AUTO", "DIESEL", "TURBINE"].includes(payload.propulsion.plant_mode) ||
        !exactKeys(payload.machinery, ["station_state", "speed_cap", "effective_speed_cap", "flood", "fire", "repair_teams", "repair_trend", "noise", "grounded"]) ||
        !boundedArray(payload.machinery.repair_teams, 16) || !exactKeys(payload.machinery.repair_trend, ["flood_rate", "fire_rate", "repairable"]) ||
        !exactKeys(payload.controls, ["orders", "plants", "speed_max_kn", "rpm_max", "noise_max"]) || !boundedArray(payload.controls.orders, 6) ||
        !finite(payload.controls.rpm_max) || !finite(payload.controls.noise_max) ||
        !boundedArray(payload.compartments, 16) || payload.compartments.some((row) => !exactKeys(row, ["key", "state", "flood", "fire", "teams"]) ||
          typeof row.key !== "string" || typeof row.state !== "string" || !finite(row.flood) || !finite(row.fire) ||
          !boundedArray(row.teams, 16) || row.teams.some((team) => !Number.isSafeInteger(team))) ||
        !boundedArray(payload.controls.plants, 3) || payload.controls.plants.join(",") !== "AUTO,DIESEL,TURBINE" ||
        payload.controls.orders.join(",") !== "ASTERN,STOP,SLOW,HALF,FULL,FLANK" ||
        !exactKeys(payload.environment_effects, ["sea_state", "roll", "pitch", "tas_available", "tas_performance"])) throw new Error("protocol");
  } else if (state.role === "helicopter") {
    if (!exactKeys(payload.asset, ["state", "airborne", "x", "y", "course", "fuel_s", "torpedoes", "buoys", "hovering", "dip_state", "dip_depth_m", "dip_depth_target_m", "dip_water_depth_m", "dip_ping_ready", "dip_ping_cooldown_s", "buoy_mode", "pattern", "pattern_remaining", "mad_mode", "radar", "radar_switch"]) ||
        !["single", "field", "barrier", "circle"].includes(payload.asset.pattern) || typeof payload.asset.mad_mode !== "boolean" ||
        typeof payload.asset.radar !== "boolean" || typeof payload.asset.radar_switch !== "boolean" ||
        (payload.waypoint !== null && !exactKeys(payload.waypoint, ["x", "y"])) ||
        !boundedArray(payload.buoys, 64) || payload.buoys.some((row) => !exactKeys(row, ["ref", "label", "x", "y", "battery_s", "active", "mode"]) || typeof row.label !== "string" || !/^SB[0-9]{2,}$/.test(row.label) || !["ACTIVE", "PASSIVE"].includes(row.mode)) ||
        !exactKeys(payload.navigation, ["x", "y", "course", "speed", "target_course", "target_speed", "rudder_angle", "yaw_rate", "turn_radius_nm"]) ||
        !exactKeys(payload.readiness, ["flightdeck_down", "deck_state", "can_launch", "can_return", "can_set_waypoint", "can_deploy_buoy", "can_pattern", "can_mad", "can_set_dipping", "can_set_dip_depth", "can_dipping_ping", "weather_launch_safe", "weather_dipping_safe", "crosswind_kn", "rtb_margin_s", "deck_motion"]) ||
        !exactKeys(payload.readiness.deck_motion, ["roll_deg", "pitch_deg", "roll_limit_deg", "pitch_limit_deg", "quiet_s", "window_s", "window_open"]) ||
        typeof payload.readiness.deck_motion.window_open !== "boolean" ||
        !["roll_deg", "pitch_deg"].every((key) => finite(payload.readiness.deck_motion[key]) && Math.abs(payload.readiness.deck_motion[key]) <= 90) ||
        !["roll_limit_deg", "pitch_limit_deg", "quiet_s", "window_s"].every((key) => finite(payload.readiness.deck_motion[key]) && payload.readiness.deck_motion[key] >= 0 && payload.readiness.deck_motion[key] <= 3600) ||
        [payload.readiness.flightdeck_down, payload.readiness.can_launch, payload.readiness.can_return, payload.readiness.can_set_waypoint, payload.readiness.can_deploy_buoy, payload.readiness.can_set_dipping, payload.readiness.can_set_dip_depth, payload.readiness.can_dipping_ping, payload.readiness.weather_launch_safe, payload.readiness.weather_dipping_safe].some((value) => typeof value !== "boolean") ||
        !finite(payload.readiness.crosswind_kn) || payload.readiness.crosswind_kn < 0 || payload.readiness.crosswind_kn > 80) throw new Error("protocol");
    tacticalRows(payload.tactical, 128, helicopterTacticalFields.slice(tacticalFields.length));
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
    if (!boundedArray(payload.intercepts, 64) || payload.intercepts.some((row) => !exactKeys(row, ["ref", "label", "group", "bearing", "bearing_uncertainty_deg", "frequency_hz", "frequency_band", "prf_hz", "modulation", "quality", "age_s", "radar_type", "threat", "signal_state", "operational", "ambiguous", "synthetic_assumption", "auto_jamming", "jamming", "jamming_effectiveness", "jamming_technique", "ecm_power_draw", "is_locked_on", "hoj_risk", "annotation", "candidates", "correlations", "signal_db", "range_estimate_nm", "scan_period_s"]) ||
        typeof row.group !== "string" || !row.group || row.group.length > 64 ||
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
