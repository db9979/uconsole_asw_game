import { S } from "../state/store.js";
import { $ } from "../core/base.js";
import { number, t, unit } from "../core/format.js";
import { sightingText } from "../state/schema.js";
import { metrics, node, position, stationRows, tacticalEntries, yesNo } from "../views/dom.js";
import { DISPLAY_CLOCK_LAG_S, displaySimNow } from "../state/display-clock.js";
import { renderCrew } from "../views/crew.js";
import { drawSightView, viewMotion } from "../views/sight-scene.js";
import { createOptics, opticsFov, opticsText, wireOptics } from "../views/optics.js";
import { visualContext } from "../views/visual-common.js";

const WEATHER_FOV_DEG = 120;  // sight_scene.INSTRUMENT_FOV_DEG

// The lookout's binoculars: trained relative to the bow in this browser only
// (presentation, like the uConsole's binoculars); the picture shows his own
// sightings from the published ``lookout`` block.
const glasses = {relative: 0, wired: false,
  // Zoom binoculars (config.LOOKOUT_GLASSES_POWERS, _ELEVATION_DEG).
  optics: createOptics([1, 2, 4], [-20, 45])};
function wireGlasses() {
  if (glasses.wired) return;
  glasses.wired = true;
  for (const button of document.querySelectorAll("[data-glasses-turn]"))
    button.addEventListener("click", () => {
      glasses.relative = ((glasses.relative + Number(button.dataset.glassesTurn)) % 360 + 360) % 360;
      renderGlassesStatus(); drawBridgeGlasses(performance.now());
    });
  wireOptics(document.querySelector('[data-optics="glasses"]'), glasses.optics,
    () => { renderGlassesStatus(); drawBridgeGlasses(performance.now()); });
  $("bridge-glasses-bow").addEventListener("click", () => {
    glasses.relative = 0; renderGlassesStatus(); drawBridgeGlasses(performance.now());
  });
}
function renderGlassesStatus() {
  const lookout = S.v2State?.bridge?.lookout;
  if (!lookout) return;
  const bearing = (lookout.course + glasses.relative) % 360;
  const text = `${t("glasses_bearing", {bearing: number(bearing, 0).padStart(3, "0"),
    relative: number(glasses.relative, 0).padStart(3, "0")})} · ${opticsText(glasses.optics, lookout.fov_deg)}`;
  if ($("bridge-glasses-status").textContent !== text) $("bridge-glasses-status").textContent = text;
}
export function drawBridgeGlasses(now) {
  const lookout = S.v2State?.bridge?.lookout;
  if (!lookout || S.session?.station !== "bridge") return;
  const plot = visualContext("bridge-glasses-canvas");
  if (!plot) return;
  // The hull's pitch and roll seen along this browser's own line of sight.
  const [offset, tilt] = viewMotion(lookout.motion_pitch, lookout.motion_roll, glasses.relative);
  drawSightView(plot.context, plot.width, plot.height,
    {...lookout, bearing: (lookout.course + glasses.relative) % 360, horizon_offset: offset, horizon_tilt: tilt,
      fov_deg: opticsFov(glasses.optics, lookout.fov_deg), elevation_deg: glasses.optics.elevation,
      stabilized: glasses.optics.stabilized, stab_label: t("sight_stabilized"),
      optics_label: opticsText(glasses.optics, lookout.fov_deg),
      way: {speed_kn: lookout.speed_kn, course_deg: lookout.course}, eyepiece: "binoculars"},
    now / 1000, plot.context.font);
}

export function renderBridgeStation(payload) {
  const navigation = payload.navigation;
  renderCrew($("bridge-crew"), $("bridge-crew-actions"), payload.crew, {actionStations: "crew_action_stations"});
  metrics($("bridge-navigation"), [["position", position(navigation)], ["course", unit(navigation.course, "\u00b0", 0)],
    ["speed", unit(navigation.speed, "kn")], ["ordered_course", unit(navigation.target_course, "\u00b0", 0)],
    ["ordered_speed", unit(navigation.target_speed, "kn")], ["rudder_angle", unit(navigation.rudder_angle, "\u00b0")],
    ["yaw_rate", unit(navigation.yaw_rate, "\u00b0/s")], ["turn_radius", unit(navigation.turn_radius_nm, "NM", 2)]]);
  metrics($("bridge-orders-summary"), [["station_down", yesNo(payload.orders.station_down)],
    ["speed_max", unit(payload.orders.speed_max_kn, "kn")], ["telegraph", t(`telegraph_${payload.orders.telegraph.toLowerCase()}`)],
    ["noise", number(payload.orders.noise, 2)], ["cavitating", yesNo(payload.orders.cavitating)],
    ["threat_count", number(payload.threat.count, 0)], ["flood", unit(payload.threat.average_flood, "%")],
    ["systems_down", payload.systems.filter((item) => item.down).map((item) => item.key).join(", ") || t("station_none")],
    ["threat_tracks", payload.threat.observations.map((row) => row.label).join(", ") || t("station_none")],
    ["torpedo_warning", payload.threat.torpedoes.length ? t(`torpedo_warning_${payload.threat.torpedoes[0].source}`, {
      bearing: number(payload.threat.torpedoes[0].bearing, 1), age: number(payload.threat.torpedoes[0].age_s, 0)}) : t("torpedo_warning_none")]]);
  renderRoute(payload.route);
  stationRows($("bridge-tactical"), payload.tactical_summary, tacticalEntries);
  renderSightings(payload.sightings);
  wireGlasses();
  renderGlassesStatus();
  drawBridgeGlasses(performance.now());
  drawBridgeWeather(performance.now());
  syncWeatherAnimation();
  const weather = S.v2State.environment;
  $("bridge-weather-text").textContent = t("weather_equivalent", {
    kind: t(`weather_${weather.weather}`), light: t(weather.is_night ? "weather_night" : "weather_day"),
    sea: number(weather.effective_sea_state, 1), direction: number(weather.wind_from_deg, 0),
    speed: number(weather.wind_speed_kn, 0), rain: number(weather.rain_intensity * 100, 0),
    visibility: number(weather.visibility_nm, 1),
  });
}
// The autopilot route: next waypoint with bearing and distance, or none.
function renderRoute(route) {
  const next = route.points[0], own = S.v2State.bridge.navigation;
  let text = t("bridge_route_none");
  if (next) {
    const dx = next.x - own.x, dy = next.y - own.y;
    text = t("bridge_route_next", {pattern: t(`bridge_route_pattern_${route.pattern}`), number: next.number,
      total: route.total, bearing: number((Math.atan2(dx, -dy) * 180 / Math.PI + 360) % 360, 0).padStart(3, "0"),
      range: number(Math.hypot(dx, dy), 1)});
  }
  if ($("bridge-route-status").textContent !== text) $("bridge-route-status").textContent = text;
  $("bridge-route-clear").disabled = !next;
  $("bridge-route-mode").setAttribute("aria-pressed", String(S.bridgeRouteMode));
}
// What the lookout reads from a navigation-light code (nav_lights.describe).
function lightsText(code) {
  const masts = Number(code[1]), red = code[2] === "r", green = code[3] === "g", stern = code[4] === "s";
  const extra = code.slice(5).toLowerCase();
  const lights = [...(masts ? [`masthead${masts}`] : []), ...(red ? ["red"] : []), ...(green ? ["green"] : []),
    ...(stern ? ["stern"] : []), ...(extra ? [extra] : [])].map((name) => t(`sighting_light_${name}`));
  const aspect = red && green ? "head_on" : green ? "starboard" : red ? "port" : stern ? "stern" : masts ? "masthead" : "";
  const meaning = [...(aspect ? [t(`sighting_aspect_${aspect}`)] : []), ...(extra ? [t(`sighting_work_${extra}`)] : [])];
  return t("sighting_lights", {lights: lights.join(", "), meaning: meaning.join(", ")});
}
function renderSightings(rows) {
  const list = $("bridge-sightings");
  const lines = rows.map((row) => t("sighting_report", {
    time: row.time, what: row.sighted === "LIGHTS" ? lightsText(row.lights) :
      row.code === null ? t(`sighting_detect_${row.sighted.toLowerCase()}`) : sightingText(row.code, row.type),
    bearing: number(row.bearing, 0).padStart(3, "0"), range: number(row.range_nm, 1)}));
  if (!lines.length) lines.push(t("sightings_none"));
  [...list.children].slice(lines.length).forEach((item) => item.remove());
  lines.forEach((text, index) => {
    const item = list.children[index] || list.appendChild(node("li"));
    if (item.textContent !== text) item.textContent = text;
  });
}
// The weather instrument: a small eyepiece picture into the wind in the
// start screen's look (sight_scene.draw_instrument on the uConsole).
function drawBridgeWeather(now) {
  const weather = S.v2State?.environment, sky = S.v2State?.bridge?.lookout?.sky;
  if (!weather || !sky || S.session?.station !== "bridge") return;
  const canvas = $("bridge-weather-canvas"), context = canvas.getContext("2d");
  drawSightView(context, canvas.width, canvas.height, {bearing: weather.wind_from_deg, fov_deg: WEATHER_FOV_DEG,
    horizon_offset: 0, horizon_tilt: 0, visibility_nm: weather.visibility_nm, sea_state: weather.effective_sea_state,
    sky, outlines: [], no_scale: true, wind_rose_deg: weather.wind_from_deg}, displaySimNow(now) + DISPLAY_CLOCK_LAG_S);
}
function weatherAnimation(now) {
  S.weatherFrame = null;
  if (now - S.weatherLastDraw >= 66) { S.weatherLastDraw = now; drawBridgeWeather(now); drawBridgeGlasses(now); }
  syncWeatherAnimation();
}
export function syncWeatherAnimation() {
  const active = !document.hidden && S.connected && S.session?.station === "bridge" && S.v2State?.role === "bridge";
  if (active && S.weatherFrame === null && S.weatherTimer === null) S.weatherTimer = setTimeout(() => {
    S.weatherTimer = null; S.weatherFrame = requestAnimationFrame(weatherAnimation);
  }, 66);
  if (!active) {
    if (S.weatherFrame !== null) cancelAnimationFrame(S.weatherFrame);
    if (S.weatherTimer !== null) clearTimeout(S.weatherTimer);
    S.weatherFrame = null; S.weatherTimer = null;
  }
}
