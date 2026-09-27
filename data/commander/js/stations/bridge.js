import { S } from "../state/store.js";
import { $ } from "../core/base.js";
import { number, t, unit } from "../core/format.js";
import { sightingText } from "../state/schema.js";
import { metrics, node, position, stationRows, tacticalEntries, yesNo } from "../views/dom.js";
import { DISPLAY_CLOCK_LAG_S, displaySimNow } from "../state/display-clock.js";
import { renderCrew } from "../views/crew.js";

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
  stationRows($("bridge-tactical"), payload.tactical_summary, tacticalEntries);
  renderSightings(payload.sightings);
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
function renderSightings(rows) {
  const list = $("bridge-sightings");
  const lines = rows.map((row) => t("sighting_report", {
    time: row.time, what: row.code === null ? t(`sighting_detect_${row.sighted.toLowerCase()}`) : sightingText(row.code, row.type),
    bearing: number(row.bearing, 0).padStart(3, "0"), range: number(row.range_nm, 1)}));
  if (!lines.length) lines.push(t("sightings_none"));
  [...list.children].slice(lines.length).forEach((item) => item.remove());
  lines.forEach((text, index) => {
    const item = list.children[index] || list.appendChild(node("li"));
    if (item.textContent !== text) item.textContent = text;
  });
}
function drawBridgeWeather(now) {
  const weather = S.v2State?.environment;
  if (!weather || S.session?.station !== "bridge") return;
  const canvas = $("bridge-weather-canvas"), context = canvas.getContext("2d");
  const width = canvas.width, height = canvas.height, horizon = Math.floor(height / 2);
  const phase = displaySimNow(now) + DISPLAY_CLOCK_LAG_S;
  const gradient = context.createLinearGradient(0, 0, 0, horizon);
  gradient.addColorStop(0, weather.is_night ? "#050e1b" : "#19465c");
  gradient.addColorStop(1, weather.is_night ? "#26353e" : "#789ba0");
  context.fillStyle = gradient; context.fillRect(0, 0, width, horizon);
  context.fillStyle = weather.is_night ? "#08232f" : "#0c3641";
  context.fillRect(0, horizon, width, height - horizon);
  context.fillStyle = weather.is_night ? "#bed2cd" : "#f4cc5c";
  const dayStart = 5.5, dayEnd = 19.5;
  const progress = weather.is_night ? ((S.v2State.clock.world - dayEnd + 24) % 24) / (24 - dayEnd + dayStart) : Math.max(0, Math.min(1, (S.v2State.clock.world - dayStart) / (dayEnd - dayStart)));
  const lightX = 24 + progress * (width - 48), lightY = horizon - 12 - Math.sin(progress * Math.PI) * 32;
  context.beginPath(); context.arc(lightX, lightY, 12, 0, Math.PI * 2); context.fill();
  const sea = weather.effective_sea_state;
  context.strokeStyle = sea >= 5 ? "#f3cf79" : "#63b5b5";
  context.lineWidth = 2;
  for (let band = 0; band < 3; band += 1) {
    context.beginPath();
    const amplitude = 3 + sea * (.8 + band * .16), wavelength = Math.max(28, 62 - sea * 4 + band * 10);
    for (let x = 0; x <= width + 4; x += 4) {
      const y = horizon + 15 + band * 20 + Math.sin(x / wavelength * Math.PI * 2 + phase * (.7 + weather.wind_speed_kn / 35 + band * .18) + weather.wind_from_deg * Math.PI / 180) * amplitude;
      if (x === 0) context.moveTo(x, y); else context.lineTo(x, y);
    }
    context.stroke();
  }
  context.strokeStyle = "#80aeb8"; context.lineWidth = 1;
  for (let i = 0; i < Math.floor(weather.rain_intensity * 44); i += 1) {
    const x = (i * 47 + phase * 31) % (width + 20) - 10, y = (i * 23 + phase * 53) % height;
    context.beginPath(); context.moveTo(x, y); context.lineTo(x - 5, y + 13); context.stroke();
  }
  const haze = 1 - Math.max(0, Math.min(1, weather.visibility_nm / 30));
  context.fillStyle = `rgba(180, 194, 190, ${haze * .55})`; context.fillRect(0, 0, width, height);
  const windAngle = weather.wind_from_deg * Math.PI / 180, cx = 28, cy = 28;
  context.fillStyle = "rgba(4, 18, 24, .75)"; context.beginPath(); context.arc(cx, cy, 20, 0, Math.PI * 2); context.fill();
  context.strokeStyle = "#f3cf79"; context.lineWidth = 3; context.beginPath();
  context.moveTo(cx + Math.sin(windAngle) * 17, cy - Math.cos(windAngle) * 17); context.lineTo(cx, cy); context.stroke();
}
function weatherAnimation(now) {
  S.weatherFrame = null;
  if (now - S.weatherLastDraw >= 66) { S.weatherLastDraw = now; drawBridgeWeather(now); }
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
