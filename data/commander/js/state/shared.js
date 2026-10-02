// Distinguishes "server sent something this client cannot parse" (a real
// bug, not a network blip) from ordinary transient failures, and gives
// the operator an honest signal once a transient failure has been
// retrying for a while instead of "retrying automatically" forever with
// no escalation.
export const PROTOCOL_ERROR_MESSAGES = new Set(["protocol", "session", "chart", "events",
  "proposals", "results", "simlog_schema", "catalog"]);
export const ESCALATE_AFTER_FAILURES = 10;
// Below this, a stale poll is shown as a low-alarm "reconnecting" notice
// rather than the full amber "stale" treatment - most blips clear before
// this many consecutive failures. Purely cosmetic: linkState/connected and
// the action-locking gate they drive are untouched.
export const NOTICE_AFTER_FAILURES = 2;
// Purely client-local presentation state; never sent to the host or saved.
export const elokaFilters = {status: "OPERATIONAL", threat: "ALL", band: "ALL"};
const elokaThreatRank = {unknown: 0, low: 1, medium: 2, high: 3, critical: 4};
const elokaSignalRank = {LIVE: 0, RECENT: 1, MEMORY: 2, UNCONFIRMED: 3};
export function filteredEloka(intercepts) {
  const minimum = elokaFilters.threat === "ALL" ? -1 : elokaThreatRank[elokaFilters.threat.toLowerCase()];
  return intercepts.filter((row) => {
    if (row.jamming) return true;
    if (elokaFilters.status === "OPERATIONAL" && !row.operational) return false;
    if (["LIVE", "MEMORY"].includes(elokaFilters.status) && row.signal_state !== elokaFilters.status) return false;
    if ((elokaThreatRank[row.threat] ?? 0) < minimum) return false;
    return elokaFilters.band === "ALL" || row.frequency_band === elokaFilters.band;
  }).sort((a, b) => Number(b.jamming) - Number(a.jamming) ||
    (elokaThreatRank[b.threat] ?? 0) - (elokaThreatRank[a.threat] ?? 0) ||
    (elokaSignalRank[a.signal_state] ?? 9) - (elokaSignalRank[b.signal_state] ?? 9) ||
    b.quality - a.quality || a.age_s - b.age_s || a.label.localeCompare(b.label));
}
// Last accepted state per station. A station switch inside one world shows
// the target's cached picture at once (marked stale, commands disabled) until
// its fresh state arrives; a world/lease change clears every entry.
export const roleCache = new Map();
export const gameEffectKinds = new Set(["sonar_ping", "esm_contact", "torpedo_launch", "missile_launch", "gunfire", "explosion", "water_entry", "telegraph",
  "sonar_echo_cw", "sonar_echo_cw_faint", "sonar_echo_lfm", "sonar_echo_lfm_faint", "alarm",
  "hull_creak", "hull_crack", "detonation_near", "detonation_far", "enemy_ping", "ping_heard",
  "general_alarm", "hull_slam", "alarm_bell", "fans_down", "fans_up", "thunder",
  // A detonation close to the own ship: the picture shakes (no sound of its own).
  "shock_light", "shock_heavy",
  // A homing torpedo's seeker pulses: slow searching, fast once locked on.
  "torpedo_seeker",
  // Noise discipline: the own crew's fumble, an enemy crew's heard transient.
  "crew_clank", "crew_transient"]);
// Spoken crew reports (src/core/callouts.py KEYS); the text is the browser's own.
export const calloutKinds = new Set(["torpedo", "contact", "breakup", "torpedo_away", "hit", "won", "lost",
  "action_stations", "mpa_on_station", "ping", "dipping", "buoy_ping", "splash", "evade", "mast_threat", "leak", "fire",
  "detonation_near", "detonation", "broadcast", "broadcast_report", "sighting_warship", "sighting_merchant",
  "sighting_aircraft", "sighting_torpedo", "sighting_unknown", "test_depth_near", "test_depth_over", "hull_damage",
  "lookout_contact", "lookout_ship", "lookout_warship", "lookout_merchant", "lookout_aircraft", "lookout_submarine", "lookout_torpedo"]);
export const calloutsWithBearing = new Set(["torpedo", "contact", "breakup", "ping", "dipping", "buoy_ping", "splash",
  "detonation_near", "detonation", "sighting_warship", "sighting_merchant", "sighting_aircraft", "sighting_torpedo",
  "sighting_unknown",
  "lookout_contact", "lookout_ship", "lookout_warship", "lookout_merchant", "lookout_aircraft", "lookout_submarine", "lookout_torpedo"]);
export const view = { x: 0, y: 0, zoom: 1, follow: false, initialized: false };
export const lookoutRanges = [5, 10, 25, 50, 100, 200];
export const lookoutView = { rangeNm: 100 };
export const maxCanvasPixels = 8000000;
export const tabNames = ["operations", "lookout", "guide", "contacts"];
export const visualCanvasIds = ["role-map", "role-map-sweep", "sonar-broadband", "sonar-lofar", "sonar-spectrum",
  "sonar-band-low", "sonar-band-mid", "sonar-band-high", "sonar-demon", "sonar-demon-spectrum",
  "sonar-tma-plot", "sonar-environment", "sonar-active", "sonar-a-scan", "damage-schematic",
  "engine-instruments", "eloka-scope", "weapons-system", "helicopter-broadband-canvas",
  "helicopter-lofar-canvas", "helicopter-demon-canvas", "uboot-engine-dials"];
// The radio room has no chart: its instrument is the HF/DF scope.
export const mapRoles = new Set(["bridge", "weapons", "opz", "helicopter", "uboot", "uboot_weapons", "uboot_nav", "uboot_esm",
  "uboot_radio"]);
export const trackRoles = new Set(["bridge", "sonar", "weapons", "opz", "helicopter", "eloka", "uboot", "uboot_sonar",
  "uboot_weapons", "uboot_nav"]);
export const roleMapViews = Object.fromEntries([...mapRoles].map((role) => [role, {x: 250, y: 250, zoom: 1}]));
export const maxRoleMapHits = 512;
export const defaultSonarPage = () => matchMedia("(min-width: 851px)").matches ? "overview" : "broadband";
// The browser runs on a desktop PC: on a wide screen the overview shows all six
// plots at once, otherwise the four that matter most.
export const wideScreen = matchMedia("(min-width: 1800px) and (min-height: 850px)");
// Ultra-wide and 4K monitors: instruments that are tabs elsewhere sit side by side.
export const ultraWide = matchMedia("(min-width: 2400px) and (min-height: 1000px)");
export const overviewPlotList = () => wideScreen.matches ? ["broadband", "lofar", "demon", "tma", "environment", "active"] :
  ["broadband", "lofar", "demon", "tma"];
export const sonarScopeNames = new Set(["broadband", "lofar", "demon", "tma", "environment", "active"]);
export const sonarDisplay = {black: 0, contrast: 2.5, history: 300, palette: "green", demonCursor: null, btCursorDepth: null};
export const sonarHistory = {context: null, broadband: new Map(), lofar: new Map(), demon: new Map()};
export const sonarStream = {socket: null, connected: false, retry: null, generation: 0,
  sequence: -1, lofarSpectrum: [], demonSpectrum: []};
