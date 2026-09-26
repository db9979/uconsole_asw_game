import { S } from "../state/store.js";
import { $ } from "../core/base.js";
import { number, t, unit } from "../core/format.js";
import { palette } from "../core/palette.js";
import { metrics, node } from "./dom.js";
import { drawEmpty, visualContext } from "./visual-common.js";

// --- Weather & sonar analysis dialog (key 0, every station) -------------
export function toggleWeatherStation(force) {
  const dialog = $("weather-dialog");
  const open = force === undefined ? !dialog.open : force;
  if (open && !dialog.open) { dialog.hidden = false; dialog.showModal(); renderWeatherStation(); }
  else if (!open && dialog.open) dialog.close();
}
export function renderWeatherStation() {
  const dialog = $("weather-dialog");
  const ws = S.v2State?.weather_station;
  if (!dialog.open || !ws) return;
  const a = ws.atmosphere, f = ws.flight, p = ws.profile;
  const limit = (value, max, digits = 0) => t("weather_limit_value", {value: number(value, digits), limit: number(max, digits)});
  metrics($("weather-environment"), [
    ["weather_time", `${a.time} · ${t(`weather_daylight_${a.daylight}`)}`],
    ["weather_moon", `${t(`weather_moon_${a.moon_phase}`)} · ${number(a.moon_illumination * 100, 0)} %`],
    ["weather_kind", `${t(`weather_kind_${a.weather}`)} · ${t(`weather_precip_${a.precipitation}`)}`],
    ["weather_visibility", unit(a.visibility_nm, "NM", 1)],
    ["weather_wind", `${number(a.wind_from_deg, 0)}° · ${unit(a.wind_kn, "kn", 0)} · ${t("weather_gust_value", {gust: number(a.gust_kn, 0)})}`],
    ["weather_beaufort", `${a.beaufort} · ${t("weather_sea_state_value", {sea: a.sea_state})}`],
    ["weather_pressure", `${unit(a.pressure_hpa, "hPa", 0)} · ${number(a.pressure_tendency_hpa_3h, 0)} hPa/3h · ${t(`weather_trend_${a.pressure_trend}`)}`],
    ["weather_temperature", `${unit(a.air_temp_c, "°C", 1)} / ${unit(a.sea_temp_c, "°C", 1)}`],
    ["weather_ceiling", a.ceiling_ft === null ? t("weather_ceiling_none") : unit(a.ceiling_ft, "ft", 0)],
    ["weather_icing", t(`weather_icing_${a.icing}`)],
  ]);
  $("weather-storm").hidden = !a.storm_warning;
  $("weather-effects").replaceChildren(...[["solar_heating", "solar"], ["wind_mixing", "wind"], ["freshwater", "rain"]].map(([key, label]) => {
    const item = node("li", t(`weather_effect_${label}`));
    item.dataset.active = String(ws.effects[key]);
    return item;
  }));
  const status = $("weather-flight-status");
  status.textContent = t(`weather_flight_${f.status}`);
  status.dataset.status = f.status;
  metrics($("weather-flight"), [
    ["weather_wind", limit(f.wind_kn, f.limits.wind_kn)],
    ["weather_gust", limit(f.gust_kn, f.limits.gust_kn)],
    ["weather_crosswind", limit(f.crosswind_kn, f.limits.crosswind_kn)],
    ["weather_visibility", limit(f.visibility_nm, f.limits.visibility_nm, 1)],
    ["weather_ceiling", f.ceiling_ft === null ? t("weather_ceiling_none") : limit(f.ceiling_ft, f.limits.ceiling_ft)],
    ["weather_sea_state", limit(f.sea_state, f.limits.sea_state)],
    ["weather_deck_roll", limit(Math.abs(f.roll_deg), f.limits.roll_deg, 1)],
    ["weather_deck_pitch", limit(Math.abs(f.pitch_deg), f.limits.pitch_deg, 1)],
    ["weather_icing", t(`weather_icing_${f.icing}`)],
    ["weather_dipping", t(f.dipping_safe ? "weather_dip_ok" : "weather_dip_blocked")],
  ]);
  const text = $("weather-profile-text");
  if (p === null) {
    text.textContent = t("weather_profile_none");
  } else {
    const shadowCells = p.shadow.reduce((sum, row) => sum + row.filter(Boolean).length, 0);
    text.textContent = [t("weather_profile_text", {
      age: number(p.age_s / 60, 0), offset: number(p.offset_nm, 1), layer: number(p.thermocline_m, 0),
      depth: number(p.water_depth_m, 0),
      sofar: p.sofar_axis_m === null ? t("weather_sofar_none") : t("weather_sofar_depth", {depth: number(p.sofar_axis_m, 0)}),
      shadow: shadowCells, cz: p.cz_bands_nm.map(([low, high]) => `${number(low, 0)}-${number(high, 0)}`).join(" / "),
    }), p.stale ? t("weather_profile_stale") : "",
      p.dip_relative_to_layer ? t(`weather_dip_${p.dip_relative_to_layer}`) : t("weather_shadow_hint")].filter(Boolean).join(" ");
  }
  drawWeatherProfile(p);
}
// Sound speed at a depth, linearly interpolated from a measured profile.
export function profileSpeedAt(depths, speeds, depth) {
  if (!depths.length) return null;
  if (depth <= depths[0]) return speeds[0];
  for (let index = 1; index < depths.length; index++) {
    if (depth <= depths[index]) {
      const upper = depths[index - 1], lower = depths[index];
      const share = lower > upper ? (depth - upper) / (lower - upper) : 0;
      return speeds[index - 1] + share * (speeds[index] - speeds[index - 1]);
    }
  }
  return speeds[speeds.length - 1];
}
function weatherProfileGeometry(p, width, height) {
  const depthMax = Math.max(1, p.depths_m[p.depths_m.length - 1]);
  const top = 18, bottom = height - 18, leftW = Math.max(90, width * .26);
  const sx = leftW + 6, sw = width - sx - 4;
  return {depthMax, top, bottom, leftW, sx, sw};
}
function weatherCursorReading(p, width, height) {
  if (!S.weatherCursor || !p) return null;
  const {depthMax, top, bottom, leftW, sx, sw} = weatherProfileGeometry(p, width, height);
  const {x, y} = S.weatherCursor;
  if (y < top || y > bottom || x < 4 || x > width - 4) return null;
  const depth = (y - top) / (bottom - top) * depthMax;
  const speed = profileSpeedAt(p.depths_m, p.speeds_m_s, depth);
  if (x <= leftW) {
    return {x: null, y, text: t("weather_cursor_depth", {depth: number(depth, 0), speed: number(speed, 1)})};
  }
  if (x < sx) return null;
  const range = (x - sx) / sw * p.range_nm;
  const parts = [t("weather_cursor_section", {range: number(range, 1), depth: number(depth, 0), speed: number(speed, 1)})];
  const column = Math.min(p.shadow.length - 1, Math.floor(range / p.range_nm * p.shadow.length));
  let row = -1;
  for (let index = 0; index + 1 < p.depth_edges_m.length; index++)
    if (depth >= p.depth_edges_m[index] && depth < p.depth_edges_m[index + 1]) row = index;
  if (column >= 0 && row >= 0 && p.shadow[column]?.[row]) parts.push(t("weather_cursor_shadow"));
  if (p.cz_bands_nm.some(([low, high]) => range >= low && range <= high)) parts.push(t("weather_cursor_cz"));
  return {x, y, text: parts.join(" · ")};
}
export function drawWeatherProfile(p) {
  const plot = visualContext("weather-profile");
  if (!plot) return;
  if (p === null) { drawEmpty(plot, "weather_profile_none"); return; }
  const {context, width, height} = plot;
  const colors = palette();
  const {depthMax, top, bottom, leftW} = weatherProfileGeometry(p, width, height);
  const y = (depth) => top + Math.min(1, Math.max(0, depth / depthMax)) * (bottom - top);
  const low = Math.min(...p.speeds_m_s), high = Math.max(...p.speeds_m_s, low + 1);
  context.strokeStyle = colors.line;
  context.strokeRect(4, top, leftW - 8, bottom - top);
  context.strokeStyle = colors.accent;
  context.beginPath();
  p.depths_m.forEach((depth, index) => {
    const x = 10 + (p.speeds_m_s[index] - low) / (high - low) * (leftW - 20);
    if (index) context.lineTo(x, y(depth)); else context.moveTo(x, y(depth));
  });
  context.stroke();
  const sx = leftW + 6, sw = width - sx - 4;
  context.strokeStyle = colors.line;
  context.strokeRect(sx, top, sw, bottom - top);
  context.fillStyle = "rgb(150 50 50 / .45)";
  p.shadow.forEach((row, column) => row.forEach((cell, index) => {
    if (!cell || p.depth_edges_m[index] > depthMax) return;
    const y0 = y(p.depth_edges_m[index]), y1 = y(Math.min(p.depth_edges_m[index + 1], depthMax));
    context.fillRect(sx + column * sw / p.shadow.length, y0, sw / p.shadow.length, Math.max(1, y1 - y0));
  }));
  context.strokeStyle = "#5adc96";
  for (const ray of p.rays) {
    context.beginPath();
    ray.forEach(([range, depth], index) => {
      const x = sx + range / p.range_nm * sw;
      if (index) context.lineTo(x, y(depth)); else context.moveTo(x, y(depth));
    });
    context.stroke();
  }
  context.textAlign = "left";
  for (const [depth, color, key] of [[p.thermocline_m, colors.amber, "weather_layer_label"], [p.sofar_axis_m, colors.blue, "weather_sofar_label"]]) {
    if (depth === null || depth > depthMax) continue;
    context.strokeStyle = color; context.fillStyle = color; context.setLineDash([5, 5]);
    context.beginPath(); context.moveTo(4, y(depth)); context.lineTo(width - 4, y(depth)); context.stroke();
    context.setLineDash([]);
    context.fillText(t(key, {depth: number(depth, 0)}), sx + 8, y(depth) - 4);
  }
  context.fillStyle = colors.muted;
  context.fillText(`${number(depthMax, 0)} m · ${number(low, 0)}-${number(high, 0)} m/s`, 8, height - 4);
  context.textAlign = "right";
  context.fillText(`${number(p.range_nm, 0)} NM`, width - 6, height - 4);
  const reading = weatherCursorReading(p, width, height);
  if (reading) {
    context.strokeStyle = colors.accent; context.setLineDash([2, 3]);
    context.beginPath(); context.moveTo(4, reading.y); context.lineTo(width - 4, reading.y); context.stroke();
    if (reading.x !== null) { context.beginPath(); context.moveTo(reading.x, top); context.lineTo(reading.x, bottom); context.stroke(); }
    context.setLineDash([]);
    const label = reading.text, labelWidth = context.measureText(label).width + 10;
    const lx = Math.min(width - labelWidth - 4, Math.max(4, (reading.x ?? leftW / 2) + 8));
    const ly = reading.y > top + 22 ? reading.y - 18 : reading.y + 6;
    context.fillStyle = colors.panel || "#07151c"; context.fillRect(lx, ly, labelWidth, 16);
    context.fillStyle = colors.accent; context.textAlign = "left";
    context.fillText(label, lx + 5, ly + 12);
  }
}
