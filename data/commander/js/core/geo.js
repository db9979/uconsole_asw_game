// Geographic chart display, as on the uConsole (src/world/geo.py): a real sea
// area's chart is projected around its centre (local equirectangular, 60 NM
// per degree of latitude). Display only; positions and ranges stay in NM.
import { S } from "../state/store.js";

const STEPS_MIN = [0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300];
const finiteNumber = (value) => typeof value === "number" && Number.isFinite(value);

export function chartCenter() {
  const center = S.chart?.geography?.center;
  return center && finiteNumber(center.lat) && finiteNumber(center.lon) ? center : null;
}

const lonNmPerMinute = (lat) => Math.cos(lat * Math.PI / 180);

export function toLonLat(x, y) {
  const center = chartCenter();
  if (!center || !finiteNumber(x) || !finiteNumber(y)) return null;
  const half = S.chart.size_nm / 2;
  const lat = center.lat + (half - y) / 60;
  const lon = ((center.lon + (x - half) / (60 * lonNmPerMinute(center.lat)) + 540) % 360) - 180;
  return {lat, lon};
}

const stepFor = (pxPerMinute, minPx) => STEPS_MIN.find((step) => step * pxPerMinute >= minPx) ?? STEPS_MIN.at(-1);

// Meridians {x, lon} and parallels {y, lat} inside the NM box.
export function graticule(left, right, top, bottom, scale, latMinPx = 80, lonMinPx = 120) {
  const center = chartCenter();
  if (!center) return null;
  const half = S.chart.size_nm / 2, lonNm = lonNmPerMinute(center.lat);
  const latStep = stepFor(scale, latMinPx), lonStep = stepFor(scale * lonNm, lonMinPx);
  const parallels = [], meridians = [];
  const latA = center.lat * 60 + (half - top), latB = center.lat * 60 + (half - bottom);
  for (let k = Math.ceil(Math.min(latA, latB) / latStep - 1e-9), end = Math.floor(Math.max(latA, latB) / latStep + 1e-9);
    k <= end && parallels.length < 400; k++) {
    const minutes = k * latStep;
    parallels.push({y: half - (minutes - center.lat * 60), lat: minutes / 60});
  }
  const lonA = center.lon * 60 + (left - half) / lonNm, lonB = center.lon * 60 + (right - half) / lonNm;
  for (let k = Math.ceil(Math.min(lonA, lonB) / lonStep - 1e-9), end = Math.floor(Math.max(lonA, lonB) / lonStep + 1e-9);
    k <= end && meridians.length < 400; k++) {
    const minutes = k * lonStep;
    meridians.push({x: half + (minutes - center.lon * 60) * lonNm, lon: ((minutes / 60 + 540) % 360) - 180});
  }
  return {meridians, parallels, lonStep, latStep};
}

const sep = () => (S.language === "de" ? "," : ".");
function split(value, decimals) {
  const total = Number((Math.abs(value) * 60).toFixed(decimals));
  const degrees = Math.floor(total / 60);
  return {degrees, minutes: total - degrees * 60};
}
const minutesText = (minutes, decimals) =>
  minutes.toFixed(decimals).padStart(decimals ? 3 + decimals : 2, "0").replace(".", sep());

export function formatLat(lat, decimals = 1) {
  const {degrees, minutes} = split(lat, decimals);
  return `${String(degrees).padStart(2, "0")}°${minutesText(minutes, decimals)}'${lat >= 0 ? "N" : "S"}`;
}
export function formatLon(lon, decimals = 1) {
  const {degrees, minutes} = split(lon, decimals);
  return `${String(degrees).padStart(3, "0")}°${minutesText(minutes, decimals)}'${lon >= 0 ? "E" : "W"}`;
}
// "54°20,5'N 010°08,2'E", or null without a real sea area.
export function formatPosition(x, y, decimals = 1) {
  const point = toLonLat(x, y);
  return point ? `${formatLat(point.lat, decimals)} ${formatLon(point.lon, decimals)}` : null;
}
// Short graticule label: "54°N" for whole-degree spacing, else "54°20'N".
export function axisLabel(value, step, isLat) {
  const decimals = step >= 1 ? 0 : 1;
  const {degrees, minutes} = split(value, decimals);
  const hemi = isLat ? (value >= 0 ? "N" : "S") : (value >= 0 ? "E" : "W");
  return step >= 60 ? `${degrees}°${hemi}` : `${degrees}°${minutesText(minutes, decimals)}'${hemi}`;
}
