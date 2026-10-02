export const $ = (id) => document.getElementById(id);
export const prefix = "commander.web.";
export const domains = { UNKNOWN: "domain_unknown", SURFACE: "domain_surface", SUBSURFACE: "domain_subsurface", AIR: "domain_air" };
export const affiliations = { UNKNOWN: "aff_unknown", FRIEND: "aff_friend", NEUTRAL: "aff_neutral", HOSTILE: "aff_hostile" };
export const classes = { U_BOOT: "class_submarine", KAMPFSCHIFF: "class_warship", BIOLOGISCH: "class_biological", FAHRZEUG: "class_vehicle", FLUGZEUG: "class_aircraft", TORPEDO: "class_torpedo" };
export const phases = { live: "phase_live", menu: "phase_menu", blocked: "phase_blocked", ended: "phase_ended" };
export const damageStates = { OK: "damage_ok", FLUTEND: "damage_flooding", BESCHAEDIGT: "damage_damaged", ZERSTOERT: "damage_destroyed" };
export const heloStates = { HANGAR: "helo_stowed", AUF: "helo_airborne", ZURUECK: "helo_returning", VERLOREN: "helo_lost" };
// Nine frigate stations, then the crewed submarine's seven (the opposing
// side). A session only ever holds roles of one side.
export const stationNames = ["bridge", "sonar", "weapons", "damage", "opz", "radio", "engine", "helicopter", "eloka",
  "uboot", "uboot_sonar", "uboot_weapons", "uboot_engine", "uboot_esm", "uboot_nav", "uboot_radio"];
export const opforRoles = new Set(["uboot", "uboot_sonar", "uboot_weapons", "uboot_engine", "uboot_esm", "uboot_nav",
  "uboot_radio"]);
// Phone lookouts (/lookout page): never a workstation tab, but every session
// record lists them after the workstations.
export const lookoutRoles = ["lookout", "uboot_lookout"];
export const sessionRoles = [...stationNames, ...lookoutRoles];
// The boat's stations besides its sonar room share one projection and panel.
export const isBoatCommand = (role) => opforRoles.has(role) && role !== "uboot_sonar";
// Both sonar rooms share one panel; the submarine's has no towed array.
const sonarRoles = new Set(["sonar", "uboot_sonar"]);
export const isSonar = (role) => sonarRoles.has(role);
export const panelRole = (role) => (role === "uboot_sonar" ? "sonar" : isBoatCommand(role) ? "uboot" : role);
// Station hotkeys/numbers count within one side: 1-9 frigate, 1-2 submarine.
export const sideStations = (station) => stationNames.filter((name) => opforRoles.has(name) === opforRoles.has(station));
export const stationKey = (station) => sideStations(station).indexOf(station) + 1;
export const reasons = {
  invalid_schema: "reason_invalid_schema", unauthorized: "reason_unauthorized",
  stale_session: "reason_stale_session", stale_epoch: "reason_stale_epoch",
  commands_blocked: "reason_commands_blocked", duplicate_id: "reason_duplicate_id",
  revision_conflict: "reason_revision_conflict", unknown_track: "reason_unknown_track",
  ineligible_track: "reason_ineligible_track", proposal_pending: "reason_proposal_pending",
  stale_generation: "reason_stale_generation", grant_revoked: "reason_grant_revoked",
  role_revoked: "reason_role_revoked", phase_blocked: "reason_phase_blocked",
  stale_world_session: "reason_stale_world_session", stale_world_epoch: "reason_stale_world_epoch",
  bridge_down: "reason_bridge_down", invalid_value: "reason_invalid_value",
  sonar_down: "reason_sonar_down", opz_down: "reason_opz_down",
  engine_down: "reason_engine_down", radio_down: "reason_radio_down",
  flightdeck_down: "reason_flightdeck_down", not_ready: "reason_not_ready",
  no_solution: "reason_no_solution", no_buoys: "reason_no_buoys",
  water_required: "reason_water_required", tas_fault: "reason_tas_fault",
  unknown_ref: "reason_unknown_ref", stale_ref: "reason_stale_ref",
  source_owned: "reason_source_owned", fusion_rejected: "reason_fusion_rejected",
  action_rejected: "reason_action_rejected", expired: "reason_expired",
  context_invalidated: "reason_context_invalidated",
  direct_fire_unavailable: "reason_direct_fire_unavailable",
  no_consort: "reason_no_consort", consort_lost: "reason_consort_lost", no_link: "reason_no_link",
  stale_fix: "reason_stale_fix", busy: "reason_busy", no_weapon: "reason_no_weapon",
  no_track: "reason_no_track",
  uboot_no_torpedoes: "reason_uboot_no_torpedoes", uboot_reloading: "reason_uboot_reloading",
  uboot_out_of_arc: "reason_uboot_out_of_arc", uboot_no_decoys: "reason_uboot_no_decoys",
  uboot_no_threat: "reason_uboot_no_threat", uboot_not_surfaced: "reason_uboot_not_surfaced",
  uboot_too_deep: "reason_uboot_too_deep", uboot_no_snorkel: "reason_uboot_no_snorkel",
  uboot_no_wire: "reason_uboot_no_wire", uboot_mast_depth: "reason_uboot_mast_depth", uboot_buoy_lost: "reason_uboot_buoy_lost",
  uboot_mast_down: "reason_uboot_mast_down", uboot_no_sighting: "reason_uboot_no_sighting",
  uboot_no_stadimeter: "reason_uboot_no_stadimeter",
  uboot_no_absorbers: "reason_uboot_no_absorbers", uboot_no_candles: "reason_uboot_no_candles",
  uboot_candle_burning: "reason_uboot_candle_burning",
  uboot_no_air_stores: "reason_uboot_no_air_stores",
  uboot_no_antenna: "reason_uboot_no_antenna", uboot_transmitting: "reason_uboot_transmitting",
  uboot_no_solution: "reason_uboot_no_solution",
  uboot_tube_dry: "reason_uboot_tube_dry", uboot_tubes_full: "reason_uboot_tubes_full",
  uboot_no_dry_tube: "reason_uboot_no_dry_tube", uboot_route_full: "reason_uboot_route_full",
  ok: "reason_ok",
};
// Listening streams: frigate sonar, helicopter and the submarine's sonar room.
export const audioRoles = new Set(["sonar", "helicopter", "uboot_sonar"]);
export const directFireRoles = new Set(["weapons", "helicopter", "opz", "uboot_weapons"]);
