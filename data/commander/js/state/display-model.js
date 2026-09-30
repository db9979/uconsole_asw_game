import { S } from "./store.js";
import { emit } from "../core/events.js";
import { isBoatCommand, isSonar, stationNames } from "../core/base.js";
import { finite } from "../core/format.js";
import { boundedArray, exactKeys, validateV2State } from "./schema.js";
import { filteredEloka } from "./shared.js";

export function buildDisplayModel(state) {
  const emptyOwn = {x: null, y: null, course: null, speed: null, target_course: null, target_speed: null, damage: [], inventory: {}, helo: {}};
  const ownship = structuredClone(emptyOwn);
  let observations = [];
  // OPZ reports inside a fusion: on the map only while managing the picture.
  let fused = new Set();
  const payload = state[state.role];
  if (state.role === "bridge") { Object.assign(ownship, payload.navigation); observations = payload.tactical_summary; }
  if (isSonar(state.role)) observations = payload.observations;
  if (isBoatCommand(state.role)) {
    const nav = payload.navigation;
    Object.assign(ownship, {x: nav.x, y: nav.y, course: nav.course, speed: nav.speed,
      target_course: nav.target_course, target_speed: nav.target_speed});
    observations = payload.contacts;
  }
  if (state.role === "weapons") { Object.assign(ownship, payload.navigation); ownship.inventory = payload.inventory; observations = payload.tactical; }
  if (state.role === "damage") ownship.damage = payload.compartments.map((room) => ({...room, teams: payload.teams.filter((team) => team.compartment === room.key).map((team) => team.team)}));
  if (state.role === "opz") {
    const sourceClasses = new Map(payload.source_classifications.map((row) => [row.ref, row.classification]));
    fused = new Set(payload.fusions.flatMap((row) => row.members));
    observations = [...payload.observations, ...payload.fusions].map((row) => ({...row,
      classification: sourceClasses.get(row.ref) ?? null}));
    Object.assign(ownship, payload.own_assets.ship);
    ownship.helo = payload.own_assets.helicopter;
    const current = new Set(observations.map((row) => row.ref));
    S.opzMarked = new Set([...S.opzMarked].filter((ref) => current.has(ref) &&
      observations.find((row) => row.ref === ref)?.source !== "FUSION"));
    S.opzSuppressed = new Set([...S.opzSuppressed].filter((ref) => current.has(ref)));
  }
  if (state.role === "radio") { Object.assign(ownship, payload.navigation); observations = payload.tactical; }
  if (state.role === "engine") { ownship.speed = payload.propulsion.speed; ownship.target_speed = payload.propulsion.target_speed; }
  if (state.role === "helicopter") { Object.assign(ownship, payload.navigation); ownship.helo = payload.asset; observations = payload.tactical; }
  if (state.role === "eloka") observations = filteredEloka(payload.intercepts);
  const tracks = observations.map((row) => ({ref: row.ref, label: row.label || row.ref,
    domain: row.domain || "UNKNOWN", source: row.source || (state.role === "eloka" ? "ESM" : "HFDF"),
    affiliation: row.affiliation || "UNKNOWN", classification: row.classification ?? null,
    bearing: row.bearing ?? null, range_nm: row.range_nm ?? null, x: row.x ?? null, y: row.y ?? null,
    depth_m: row.depth_m ?? null, altitude_m: row.altitude_m ?? null, course: row.course ?? null, speed_kn: row.speed_kn ?? null,
    observer_x: row.observer_x ?? null, observer_y: row.observer_y ?? null,
    released_to_opz: row.released_to_opz === true,
    eloka_annotated: state.role === "eloka" && Boolean(row.annotation),
    quality: row.quality ?? null, age_s: row.age_s ?? null, fix_age_s: row.fix_age_s ?? null,
    bearing_uncertainty_deg: row.bearing_uncertainty_deg ?? null,
    range_uncertainty_nm: row.range_uncertainty_nm ?? null, fixes: row.fixes || [],
    members: row.members || [],
    can_classify: isSonar(state.role) || state.role === "helicopter" || (state.role === "opz" &&
      (row.source.startsWith("RADAR") || row.source.startsWith("SONAR") ||
       ["HOJ", "FUSION"].includes(row.source))),
    can_propose: state.role === "sonar"})).filter((row) => state.role !== "opz" || S.opzManage || (!S.opzSuppressed.has(row.ref) && !fused.has(row.ref)));
  return {version: state.version, session: state.session, epoch: state.epoch,
    revision: state.revision, seq: state.seq, phase: state.phase,
    chart_revision: state.chart_revision, clock: state.clock,
    environment: state.environment, mission: state.mission, ownship, tracks};
}
export function validateState(state) {
  validateV2State(state);
  if (state.role === null) return;
  const display = buildDisplayModel(state);
  if (typeof display.session !== "string" || !display.session ||
      !Number.isSafeInteger(display.epoch) || !Number.isSafeInteger(display.revision) || !Number.isSafeInteger(display.seq) ||
      display.chart_revision == null ||
      !display.ownship || ["x", "y"].some((key) => display.ownship[key] !== null && !finite(display.ownship[key])) ||
      !display.clock || !display.mission || !Array.isArray(display.tracks) ||
      display.tracks.some((track) => !track || typeof track.ref !== "string" || !track.ref ||
        !Array.isArray(track.fixes) || track.fixes.length > 4 || track.fixes.some((fix) => !fix ||
          !["PING", "DIPPING", "TMA", "SONOBUOY"].includes(fix.source) ||
          ![fix.x, fix.y, fix.measured_at, fix.fixed_at, fix.measurement_age_s,
            fix.fix_age_s, fix.uncertainty_nm, fix.quality].every(finite) ||
          fix.fixed_at < fix.measured_at || fix.measurement_age_s < 0 || fix.fix_age_s < 0 ||
          fix.uncertainty_nm <= 0 || fix.uncertainty_nm > 100 ||
          Math.abs(fix.x) > 1000000 || Math.abs(fix.y) > 1000000 ||
          fix.measured_at < 0 || fix.measured_at > 1000000000000 ||
          fix.fixed_at > 1000000000000 || fix.quality < 0 || fix.quality > 1 ||
          ((fix.depth_m === null) !== (fix.depth_uncertainty_m === null)) ||
          (fix.depth_m !== null && (!finite(fix.depth_m) || !finite(fix.depth_uncertainty_m) ||
            fix.depth_m < 0 || fix.depth_uncertainty_m <= 0))))) throw new Error("protocol");
  if (new Set(display.tracks.map((track) => track.ref)).size !== display.tracks.length) throw new Error("protocol");
  if (display.tracks.some((track) => new Set(track.fixes.map((fix) => fix.source)).size !== track.fixes.length)) throw new Error("protocol");
  const environment = display.environment;
  if (environment != null && (typeof environment !== "object" || Array.isArray(environment) ||
      Object.keys(environment).sort().join(",") !== "effective_sea_state,is_night,rain_intensity,sea_state,storm,visibility_nm,weather,wind_from_deg,wind_speed_kn" ||
      (environment.sea_state !== null && (!Number.isInteger(environment.sea_state) || environment.sea_state < 0 || environment.sea_state > 9)) ||
      (environment.is_night !== null && typeof environment.is_night !== "boolean"))) throw new Error("protocol");
}
export function validateChart(data, state) {
  if (!data || data.protocol !== 2 ||
      data.revision !== state.chart_revision || !finite(data.size_nm) || data.size_nm <= 0 ||
      !Array.isArray(data.landmasses) || data.landmasses.some((land) => !Array.isArray(land.points) ||
        land.points.some((point) => !Array.isArray(point) || point.length !== 2 || !point.every(finite)))) throw new Error("chart");
  if (data.geography !== undefined) {
    const geo = data.geography;
    if (!exactKeys(geo, ["labels", "airbases", "depths", "hazards"]) ||
        !Array.isArray(geo.hazards) || geo.hazards.length > 64 || geo.hazards.some((row) =>
          !exactKeys(row, ["kind", "x", "y", "top_depth_m", "length_m"]) || !["wreck", "rock"].includes(row.kind) ||
          ![row.x, row.y, row.top_depth_m, row.length_m].every(finite)) ||
        ![geo.labels, geo.airbases].every((rows) => Array.isArray(rows) && rows.length <= 128 && rows.every((row) =>
          exactKeys(row, ["name", "x", "y"]) && typeof row.name === "string" && row.name.length <= 96 && finite(row.x) && finite(row.y))) ||
        !Array.isArray(geo.depths) || geo.depths.length > 64 || geo.depths.some((row) =>
          !Array.isArray(row) || row.length > 64 || !row.every(finite))) throw new Error("chart");
  }
}
export function contextKey(value) {
  return value ? `${value.session}\n${value.epoch}\n${value.role}` : null;
}
export function validateProposals(value) {
  if (!exactKeys(value, ["protocol", "session", "epoch", "role", "target", "navigation"]) ||
      value.protocol !== 2 || typeof value.session !== "string" || !value.session || value.session.length > 64 ||
      !Number.isSafeInteger(value.epoch) || value.epoch < 0 || !stationNames.includes(value.role)) throw new Error("proposals");
  const validStatus = (status) => ["pending", "accepted", "rejected", "expired"].includes(status);
  if (value.target !== null && (!exactKeys(value.target, ["ref", "label", "status"]) ||
      value.role !== "sonar" || typeof value.target.ref !== "string" || !value.target.ref || value.target.ref.length > 64 ||
      typeof value.target.label !== "string" || !value.target.label || value.target.label.length > 64 ||
      !validStatus(value.target.status))) throw new Error("proposals");
  if (value.navigation !== null && (!exactKeys(value.navigation, ["course", "speed_kn", "status"]) ||
      value.role !== "bridge" || !validStatus(value.navigation.status) ||
      (value.navigation.course !== null && (!finite(value.navigation.course) || value.navigation.course < 0 || value.navigation.course >= 360)) ||
      (value.navigation.speed_kn !== null && (!finite(value.navigation.speed_kn) || value.navigation.speed_kn < 0 || value.navigation.speed_kn > 31)) ||
      value.navigation.course === null && value.navigation.speed_kn === null)) throw new Error("proposals");
}
export function validateEvents(value) {
  if (!exactKeys(value, ["protocol", "session", "epoch", "role", "latest_seq", "events"]) ||
      value.protocol !== 2 || typeof value.session !== "string" || !value.session || value.session.length > 64 ||
      !Number.isSafeInteger(value.epoch) || value.epoch < 0 || !stationNames.includes(value.role) ||
      !Number.isSafeInteger(value.latest_seq) || value.latest_seq < 0 ||
      !boundedArray(value.events, 128)) throw new Error("events");
  let previous = 0;
  for (const event of value.events) {
    if (!exactKeys(event, ["seq", "kind", "severity", "message"]) ||
        !Number.isSafeInteger(event.seq) || event.seq <= previous || event.seq < 1 || event.seq > value.latest_seq ||
        typeof event.kind !== "string" || !event.kind || event.kind.length > 32 ||
        !["info", "warning"].includes(event.severity) ||
        typeof event.message !== "string" || !event.message || event.message.length > 512) throw new Error("events");
    previous = event.seq;
  }
}
export function useEvents(value, state) {
  const key = contextKey(state);
  let warning = false;
  if (S.eventContext !== key || S.eventBaselinePending || document.hidden || !navigator.onLine) {
    S.eventContext = key;
    S.eventHighWater = value.latest_seq;
    S.eventHistory = value.events.slice(-80);
    if (!document.hidden && navigator.onLine) S.eventBaselinePending = false;
  } else {
    const fresh = value.events.filter((event) => event.seq > S.eventHighWater);
    warning = fresh.some((event) => event.severity === "warning");
    S.eventHistory = [...S.eventHistory, ...fresh].slice(-80);
    S.eventHighWater = Math.max(S.eventHighWater, value.latest_seq);
  }
  emit("events", warning);
}
