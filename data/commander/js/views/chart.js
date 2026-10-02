import { S } from "../state/store.js";
import { $ } from "../core/base.js";
import { chartMatches, finite, hasPosition, number, t } from "../core/format.js";
import { colors, palette } from "../core/palette.js";
import { sendStationAction } from "../net/commands.js";
import { drawSymbol } from "../plot/symbols.js";
import { mapRoles, maxCanvasPixels, view } from "../state/shared.js";
import { node } from "./dom.js";
import { addMapInfo, currentOpzSweepBearing, drawChartHazards, mapPayload, rayLengthToCanvasEdge } from "./role-map.js";
import { queueVisualDraw } from "./role-visuals.js";
import { schedule } from "../core/scheduler.js";
import { stationActionAvailable } from "../state/availability.js";
import { canvas, ctx } from "./canvases.js";
import { labelField, placeText, reserveText } from "./label-layout.js";

export function chartGeometry() {
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  const scale = Math.min(width, height) / S.chart.size_nm * .9 * view.zoom;
  return { width, height, scale, point: (x, y) => [width / 2 + (x - view.x) * scale, height / 2 + (y - view.y) * scale] };
}
export function fitChart() {
  view.x = S.chart.size_nm / 2;
  view.y = S.chart.size_nm / 2;
  view.zoom = 1;
  view.follow = false;
  view.initialized = true;
  $("follow").setAttribute("aria-pressed", "false");
  queueDraw();
}
export function queueDraw() {
  schedule("chart", drawChart);
}
export function releaseCanvas(element) {
  if (element.width !== 1 || element.height !== 1) {
    element.width = 1;
    element.height = 1;
  }
}
export function resizeCanvas(element, context, width, height) {
  const requested = Math.min(window.devicePixelRatio || 1, 3);
  const dpr = Math.min(requested, Math.sqrt(maxCanvasPixels / Math.max(1, width * height)));
  const pixelWidth = Math.max(1, Math.round(width * dpr));
  const pixelHeight = Math.max(1, Math.round(height * dpr));
  if (element.width !== pixelWidth || element.height !== pixelHeight) {
    element.width = pixelWidth;
    element.height = pixelHeight;
  }
  context.setTransform(dpr, 0, 0, dpr, 0, 0);
  return dpr;
}
// Chart water in the light of the game clock: three stages, as on the
// uConsole (src/world/atmosphere.daylight_stage, src/ui/theme.WATER_TINT).
const DAYLIGHT_START_H = 5.5, DAYLIGHT_END_H = 19.5, DUSK_HALF_WIDTH_H = 1;
const WATER_TINT = {day: 1, dusk: .8, night: .6};
const SEA_BASE = [12, 28, 38];
export function daylightStage(hour) {
  if (!finite(hour)) return "day";
  const h = ((hour % 24) + 24) % 24;
  if (h < DAYLIGHT_START_H || h >= DAYLIGHT_END_H) return "night";
  if (h < DAYLIGHT_START_H + DUSK_HALF_WIDTH_H || h >= DAYLIGHT_END_H - DUSK_HALF_WIDTH_H) return "dusk";
  return "day";
}
export function seaColor(stage) {
  const factor = WATER_TINT[stage] ?? 1;
  return `rgb(${SEA_BASE.map((channel) => Math.round(channel * factor)).join(", ")})`;
}
// Rain and storm as a dashed diagonal hatch over the chart (display only,
// from the published environment block).
const WEATHER_BAND_MIN_RAIN = .25;
export function drawWeatherBand(ctx, width, height, environment) {
  if (!environment) return;
  const rain = Math.max(0, Math.min(1, environment.rain_intensity ?? 0));
  const storm = environment.weather === "storm";
  if (rain < WEATHER_BAND_MIN_RAIN && !storm) return;
  const strength = Math.max(0, Math.min(1, (rain - WEATHER_BAND_MIN_RAIN) / (1 - WEATHER_BAND_MIN_RAIN)));
  const spacing = Math.max(6, Math.round(46 + (18 - 46) * strength));
  ctx.save();
  ctx.globalAlpha = (28 + (70 - 28) * strength) / 255;
  ctx.strokeStyle = storm ? "#f0b64a" : "#aabec8";
  ctx.lineWidth = 1;
  ctx.setLineDash([9, 7]);
  ctx.beginPath();
  for (let start = -height; start < width; start += spacing) {
    ctx.moveTo(start, height); ctx.lineTo(start + height, 0);
  }
  ctx.stroke();
  ctx.setLineDash([]);
  if (storm) { ctx.globalAlpha = 1; ctx.strokeStyle = "#f0b64a"; ctx.lineWidth = 2; ctx.strokeRect(1, 1, width - 2, height - 2); }
  ctx.restore();
}

// Frame-time probe of the chart (display only; read by the browser tests).
const chartTiming = {frames: 0, totalMs: 0, lastMs: 0, maxMs: 0};
window.uJagdChartTiming = chartTiming;
function drawChart() {
  const started = performance.now();
  try { drawChartFrame(); } finally {
    const elapsed = performance.now() - started;
    chartTiming.frames += 1; chartTiming.totalMs += elapsed; chartTiming.lastMs = elapsed;
    if (elapsed > chartTiming.maxMs) chartTiming.maxMs = elapsed;
  }
}
function drawChartFrame() {
  if (!S.snapshot || !chartMatches(S.snapshot) || $("panel-operations").hidden) return;
  const own = S.snapshot.ownship;
  const ownPosition = hasPosition(own);
  if (view.follow && ownPosition) { view.x = own.x; view.y = own.y; }
  const { width, height, scale, point } = chartGeometry();
  if (!width || !height) return;
  resizeCanvas(canvas, ctx, width, height);
  ctx.fillStyle = seaColor(daylightStage(S.v2State?.clock?.world));
  ctx.fillRect(0, 0, width, height);
  const fontSize = Math.max(12, parseFloat(getComputedStyle(document.documentElement).fontSize) * .74);
  ctx.font = `${fontSize}px ui-monospace, monospace`;
  const left = view.x - width / (2 * scale);
  const right = view.x + width / (2 * scale);
  const top = view.y - height / (2 * scale);
  const bottom = view.y + height / (2 * scale);
  const rough = 110 / scale;
  const power = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 5, 10].find((n) => n * power >= rough) * power;
  // One label field for the chart: axis numbers, radar ring ranges and the
  // north mark are reserved, track and fix labels step aside from them.
  const labels = labelField(width, height);
  labels.reserve(width - 34, 8, 30, 42);
  ctx.lineWidth = 1;
  ctx.strokeStyle = "#233741";
  ctx.fillStyle = "#8ba4ad";
  ctx.beginPath();
  for (let x = Math.ceil(left / step) * step; x < right; x += step) {
    const px = point(x, 0)[0];
    ctx.moveTo(px, 0); ctx.lineTo(px, height);
    const label = number(x || 0, step < 1 ? 1 : 0);
    if (px + 4 + ctx.measureText(label).width <= width - 4) { ctx.fillText(label, px + 4, height - 9); reserveText(ctx, labels, label, px + 4, height - 9); }
  }
  for (let y = Math.ceil(top / step) * step; y < bottom; y += step) {
    const py = point(0, y)[1];
    ctx.moveTo(0, py); ctx.lineTo(width, py);
    if (py >= fontSize + 5 && py < height - fontSize - 12) {
      const label = number(y || 0, step < 1 ? 1 : 0);
      ctx.fillText(label, 6, py - 5); reserveText(ctx, labels, label, 6, py - 5);
    }
  }
  ctx.stroke();
  ctx.fillStyle = "#283c40";
  ctx.strokeStyle = "#607e78";
  for (const land of S.chart.landmasses) {
    // Cull in world coordinates before allocating/translating polygon vertices.
    if (!land.points.length || land.points.every(([x]) => x < left) || land.points.every(([x]) => x > right) ||
        land.points.every(([, y]) => y < top) || land.points.every(([, y]) => y > bottom)) continue;
    ctx.beginPath();
    land.points.forEach(([x, y], index) => { const [px, py] = point(x, y); if (!index) ctx.moveTo(px, py); else ctx.lineTo(px, py); });
    ctx.closePath(); ctx.fill(); ctx.stroke();
  }
  const [zeroX, zeroY] = point(0, 0);
  ctx.strokeStyle = "#58707c";
  ctx.setLineDash([5, 5]);
  ctx.strokeRect(zeroX, zeroY, S.chart.size_nm * scale, S.chart.size_nm * scale);
  ctx.setLineDash([]);
  drawWeatherBand(ctx, width, height, S.v2State?.environment);
  S.chartHits = [];
  S.chartInfo = [];
  drawChartHazards(ctx, S.chart.geography?.hazards || [], point, width, height, scale, S.chartInfo);
  // Status-only snapshots intentionally omit ownship geometry. Null is not 0.
  const [ox, oy] = ownPosition ? point(own.x, own.y) : [null, null];
  const rayLength = ownPosition ? Math.hypot(width, height) + Math.hypot(ox - width / 2, oy - height / 2) : null;
  const radar = S.v2State?.role === "opz" ? S.v2State.opz.radar : null;
  if (ownPosition && radar?.live && (radar.surface || radar.air)) {
    ctx.strokeStyle = "#426b62";
    ctx.globalAlpha = .55;
    for (const fraction of [.25, .5, .75, 1]) {
      ctx.beginPath(); ctx.arc(ox, oy, radar.range_nm * fraction * scale, 0, Math.PI * 2); ctx.stroke();
    }
    // Range labels at the top of each ring, beside the north axis.
    ctx.save();
    ctx.globalAlpha = .9; ctx.fillStyle = "#8fbfb0"; ctx.textAlign = "left"; ctx.textBaseline = "top";
    for (const fraction of [.25, .5, .75, 1]) {
      const ringRange = radar.range_nm * fraction;
      const ring = t("radar_ring", {range: number(ringRange, Number.isInteger(ringRange) ? 0 : 1)});
      ctx.fillText(ring, ox + 4, oy - ringRange * scale + 2);
      labels.reserve(ox + 4, oy - ringRange * scale + 2, ctx.measureText(ring).width, fontSize + 2);
    }
    ctx.restore();
    const displayedSweep = S.v2State?.phase === "live" ?
      currentOpzSweepBearing() : radar.sweep_bearing;
    const sweep = displayedSweep * Math.PI / 180;
    const sweepDx = Math.sin(sweep), sweepDy = -Math.cos(sweep);
    const sweepLength = rayLengthToCanvasEdge(ox, oy, sweepDx, sweepDy, width, height);
    ctx.strokeStyle = "#8de6c4";
    ctx.beginPath(); ctx.moveTo(ox, oy);
    ctx.lineTo(ox + sweepDx * sweepLength, oy + sweepDy * sweepLength); ctx.stroke();
    ctx.globalAlpha = 1;
  }
  // No integration, dead reckoning or animation of tracks: only published fixes.
  // Positioned tracks outside the view (plus their uncertainty ring) are
  // culled in world coordinates before any point transform.
  const cullMargin = 60 / scale;
  if (ownPosition) labels.reserve(ox - 12, oy - 12, 24, 24);
  for (const track of S.snapshot.tracks) {
    if (finite(track.x) && finite(track.y)) {
      const ring = finite(track.range_uncertainty_nm) ? Math.max(0, track.range_uncertainty_nm) : 0;
      if (track.x + ring < left - cullMargin || track.x - ring > right + cullMargin ||
          track.y + ring < top - cullMargin || track.y - ring > bottom + cullMargin) continue;
    }
    const color = colors[track.affiliation] || colors.UNKNOWN;
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = track.ref === S.selected ? 2 : 1;
    if (!finite(track.x) || !finite(track.y)) {
      // A bearing starts at the platform that measured it (buoy, dip,
      // logged HFDF position), as on the role map; else at own ship.
      const observed = finite(track.observer_x) && finite(track.observer_y);
      if (!finite(track.bearing) || (!ownPosition && !observed)) continue;
      const [bx, by] = observed ? point(track.observer_x, track.observer_y) : [ox, oy];
      const reach = Math.hypot(width, height) + Math.hypot(bx - width / 2, by - height / 2);
      const angle = track.bearing * Math.PI / 180 - Math.PI / 2;
      const uncertainty = finite(track.bearing_uncertainty_deg) ? Math.min(180, Math.max(0, track.bearing_uncertainty_deg)) * Math.PI / 180 : 0;
      if (uncertainty) {
        ctx.globalAlpha = track.ref === S.selected ? .13 : .055;
        ctx.beginPath(); ctx.moveTo(bx, by); ctx.arc(bx, by, reach, angle - uncertainty, angle + uncertainty); ctx.closePath(); ctx.fill(); ctx.globalAlpha = 1;
      }
      ctx.beginPath(); ctx.moveTo(bx, by); ctx.lineTo(bx + Math.cos(angle) * reach, by + Math.sin(angle) * reach);
      if (track.ref === S.selected) { ctx.strokeStyle = palette().accent; ctx.lineWidth = 4; ctx.stroke(); }
      ctx.strokeStyle = color; ctx.lineWidth = 1; ctx.setLineDash([6, 6]); ctx.stroke(); ctx.setLineDash([]);
      // A ray is intentionally not pickable as a fictitious contact position.
      continue;
    }
    const [x, y] = point(track.x, track.y);
    const radius = finite(track.range_uncertainty_nm) ? Math.max(0, track.range_uncertainty_nm) * scale : 0;
    if (x + radius < -60 || y + radius < -60 || x - radius > width + 60 || y - radius > height + 60) continue;
    if (radius > 1) {
      ctx.globalAlpha = .16; ctx.beginPath(); ctx.arc(x, y, radius, 0, Math.PI * 2); ctx.stroke(); ctx.globalAlpha = 1;
    }
    if (radar && track.source.startsWith("RADAR")) {
      ctx.strokeStyle = color; ctx.globalAlpha = .18;
      for (const glow of [8, 13, 19]) { ctx.beginPath(); ctx.arc(x, y, glow, 0, Math.PI * 2); ctx.stroke(); }
      ctx.globalAlpha = 1;
    }
    drawSymbol(x, y, track.domain, color, fontSize * .65, track.affiliation);
    if (track.ref === S.selected) { ctx.strokeStyle = palette().accent; ctx.lineWidth = 2; ctx.strokeRect(x - 25, y - 25, 50, 50); }
    ctx.fillStyle = color;
    labels.reserve(x - 12, y - 12, 24, 24);
    placeText(ctx, labels, String(track.label ?? ""), x + 31, y - 9, Math.max(60, width - x - 37));
    S.chartHits.push({ ref: track.ref, x, y });
    addMapInfo(S.chartInfo, x, y, "track", track);
  }
  // Independent sonar fixes share their parent track identity and are rebuilt
  // from the current snapshot on every draw, so stale markers cannot be hit.
  for (const track of S.snapshot.tracks) {
    for (const fix of track.fixes) {
      const [x, y] = point(fix.x, fix.y);
      const radius = Math.max(2, fix.uncertainty_nm * scale);
      if (x + radius < -60 || y + radius < -60 || x - radius > width + 60 || y - radius > height + 60) continue;
      ctx.strokeStyle = fix.source === "PING" ? "#59d8dc" : fix.source === "TMA" ? palette().amber : "#83c99a";
      ctx.lineWidth = track.ref === S.selected ? 2 : 1;
      ctx.beginPath(); ctx.arc(x, y, radius, 0, Math.PI * 2); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(x - 6, y); ctx.lineTo(x + 6, y); ctx.moveTo(x, y - 6); ctx.lineTo(x, y + 6); ctx.stroke();
      ctx.fillStyle = ctx.strokeStyle;
      placeText(ctx, labels, `${String(track.label ?? "")} ${fix.source}`, x + 9, y - 8, Math.max(50, width - x - 13));
      S.chartHits.push({ ref: track.ref, x, y });
      addMapInfo(S.chartInfo, x, y, "fix", {...fix, label: track.label});
    }
  }
  if (ownPosition) {
    addMapInfo(S.chartInfo, ox, oy, "own", own);
    ctx.save();
    ctx.translate(ox, oy);
    ctx.strokeStyle = palette().accent; ctx.fillStyle = "#183e3c"; ctx.lineWidth = 2;
    ctx.beginPath();
    if (finite(own.course)) {
      ctx.rotate(own.course * Math.PI / 180);
      ctx.moveTo(0, -13); ctx.lineTo(7, 9); ctx.lineTo(-7, 9); ctx.closePath(); ctx.fill(); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(0, -16); ctx.lineTo(0, -35); ctx.stroke();
    } else {
      ctx.arc(0, 0, 8, 0, Math.PI * 2); ctx.stroke();
    }
    ctx.restore();
    ctx.fillStyle = palette().accent; placeText(ctx, labels, t("ownship"), ox + 15, oy + 18);
  }
  const helo = own.helo;
  if (hasPosition(helo) && ["AUF", "ZURUECK"].includes(helo.state)) {
    const [hx, hy] = point(helo.x, helo.y);
    if (hx > -30 && hy > -30 && hx < width + 30 && hy < height + 30) {
      drawSymbol(hx, hy, "AIR", palette().accent, 8);
      ctx.fillStyle = palette().accent; placeText(ctx, labels, t("helicopter"), hx + 15, hy + 5);
    }
  }
  if (S.v2State?.plot) drawPlotLayer(ctx, point, scale, width, height, null);
  ctx.fillStyle = "#c6d6d9"; ctx.fillText(t("north"), width - 27, 25);
  ctx.strokeStyle = "#c6d6d9"; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(width - 23, 47); ctx.lineTo(width - 23, 31); ctx.lineTo(width - 27, 37); ctx.moveTo(width - 23, 31); ctx.lineTo(width - 19, 37); ctx.stroke();
  $("chart-scale").textContent = t("chart_scale", { distance: number(step, step < 1 ? 1 : 0) });
}
// Shared crew plot (marks, rulers, bearing lines, circles, DR lines): the
// same objects the uConsole draws, from the common "plot" projection.
function plotBearingDistance(x1, y1, x2, y2) {
  const dx = x2 - x1, dy = y2 - y1;
  return [((Math.atan2(dx, -dy) * 180 / Math.PI) % 360 + 360) % 360, Math.hypot(dx, dy)];
}
function plotText(item) {
  if (item.shape === "ruler") {
    const [bearing, distance] = plotBearingDistance(item.x, item.y, item.x2, item.y2);
    return t("plot_ruler", {label: item.label, bearing: number(bearing, 0).padStart(3, "0"), range: number(distance, 1)});
  }
  if (item.shape === "bearing") return t("plot_bearing", {label: item.label, bearing: number(item.bearing, 0).padStart(3, "0")});
  if (item.shape === "circle") return t("plot_circle", {label: item.label, range: number(item.radius_nm, 1)});
  if (item.shape === "dr") return t("plot_dr", {label: item.label, range: number(item.cpa_nm, 1), minutes: number(item.cpa_s / 60, 0)});
  return item.label;
}
function plotLabel() {
  return $("plot-label-input").value.trim().slice(0, S.v2State?.plot?.max_label || 24);
}
export function plotClick(role, worldX, worldY) {
  const tool = $("plot-tool").value, label = plotLabel(), own = mapPayload(role).own;
  if (!stationActionAvailable() || !finite(worldX) || !finite(worldY) ||
      Math.abs(worldX) > 1000 || Math.abs(worldY) > 1000) return;
  const tenth = (value) => (Math.round(value * 10) / 10) % 360;
  if (tool === "mark") { sendStationAction("plot_add", {shape: "mark", x: worldX, y: worldY, label}); return; }
  if (tool === "bearing") {
    if (!hasPosition(own)) return;
    const [bearing, distance] = plotBearingDistance(own.x, own.y, worldX, worldY);
    if (distance > 0) sendStationAction("plot_add", {shape: "bearing", x: own.x, y: own.y, bearing: tenth(bearing), label});
    return;
  }
  if (!S.plotAnchor || S.plotAnchor.role !== role || S.plotAnchor.tool !== tool) {
    S.plotAnchor = {role, tool, x: worldX, y: worldY};
    queueVisualDraw();
    return;
  }
  const anchor = S.plotAnchor;
  S.plotAnchor = null;
  const [bearing, distance] = plotBearingDistance(anchor.x, anchor.y, worldX, worldY);
  if (tool === "ruler") {
    sendStationAction("plot_add", {shape: "ruler", x: anchor.x, y: anchor.y, x2: worldX, y2: worldY, label});
  } else if (tool === "circle" && distance > 0 && distance <= 200) {
    sendStationAction("plot_add", {shape: "circle", x: anchor.x, y: anchor.y, radius_nm: Math.round(distance * 100) / 100, label});
  } else if (tool === "dr" && distance > 0) {
    const speed = Number($("plot-speed").value);
    if (finite(speed) && speed >= 0 && speed <= 60) {
      sendStationAction("plot_add", {shape: "dr", x: anchor.x, y: anchor.y, course: tenth(bearing), speed_kn: speed, label});
    }
  }
  queueVisualDraw();
}
// Plot the selected track's measured bearing from its observer position.
export function plotTrackBearing() {
  const role = S.v2State?.role;
  if (!mapRoles.has(role)) return;
  const data = mapPayload(role), row = data.observations.find((item) => item.ref === S.selected);
  if (!row || !finite(row.bearing)) return;
  const origin = finite(row.observer_x) && finite(row.observer_y) ? {x: row.observer_x, y: row.observer_y} : data.own;
  if (!hasPosition(origin)) return;
  sendStationAction("plot_add", {shape: "bearing", x: origin.x, y: origin.y,
    bearing: (Math.round(row.bearing * 10) / 10) % 360, label: (plotLabel() || String(row.label || row.ref)).slice(0, 24)});
}
export function renderPlotList() {
  const objects = S.v2State?.plot?.objects || [];
  const key = JSON.stringify(objects.map((item) => [item.id, plotText(item)]));
  if (key === S.plotListKey) return;
  S.plotListKey = key;
  $("plot-list").replaceChildren(...objects.map((item) => {
    const row = node("li", plotText(item));
    const rename = node("button", t("plot_rename"));
    rename.type = "button";
    rename.addEventListener("click", () => sendStationAction("plot_relabel", {id: item.id, label: plotLabel()}));
    const remove = node("button", t("plot_delete"));
    remove.type = "button";
    remove.addEventListener("click", () => sendStationAction("plot_remove", {id: item.id}));
    row.append(" ", rename, " ", remove);
    return row;
  }));
}
export function drawPlotLayer(context, point, scale, width, height, info) {
  const objects = S.v2State?.plot?.objects || [];
  const far = 2 * Math.hypot(width, height) / Math.max(scale, 1e-6);
  context.save();
  // Own track (a point every 30 s of the last two hours), under the plot.
  const trail = S.v2State?.plot?.trail || [];
  if (trail.length > 1) {
    context.strokeStyle = palette().accent; context.fillStyle = palette().accent;
    context.globalAlpha = .35; context.lineWidth = 1; context.beginPath();
    trail.forEach(([tx, ty], index) => { const [px, py] = point(tx, ty); if (index) context.lineTo(px, py); else context.moveTo(px, py); });
    context.stroke(); context.globalAlpha = .7;
    for (const [tx, ty] of trail) { const [px, py] = point(tx, ty); if (px > -4 && py > -4 && px < width + 4 && py < height + 4) context.fillRect(px - 1, py - 1, 2, 2); }
    context.globalAlpha = 1;
  }
  context.strokeStyle = palette().plot; context.fillStyle = palette().plot; context.lineWidth = 1.5;
  for (const item of objects) {
    const [x, y] = point(item.x, item.y);
    let [lx, ly] = [x, y];
    context.beginPath();
    if (item.shape === "mark") {
      context.moveTo(x - 6, y - 6); context.lineTo(x + 6, y + 6); context.moveTo(x - 6, y + 6); context.lineTo(x + 6, y - 6);
    } else if (item.shape === "ruler") {
      const [x2, y2] = point(item.x2, item.y2);
      context.moveTo(x, y); context.lineTo(x2, y2);
      context.moveTo(x + 3, y); context.arc(x, y, 3, 0, Math.PI * 2); context.moveTo(x2 + 3, y2); context.arc(x2, y2, 3, 0, Math.PI * 2);
      [lx, ly] = [(x + x2) / 2, (y + y2) / 2];
    } else if (item.shape === "bearing") {
      const angle = item.bearing * Math.PI / 180, [ex, ey] = point(item.x + Math.sin(angle) * far, item.y - Math.cos(angle) * far);
      context.setLineDash([8, 8]); context.moveTo(x, y); context.lineTo(ex, ey); context.stroke(); context.setLineDash([]);
      context.beginPath(); context.arc(x, y, 3, 0, Math.PI * 2);
    } else if (item.shape === "circle") {
      context.arc(x, y, Math.max(2, item.radius_nm * scale), 0, Math.PI * 2);
    } else if (item.shape === "dr") {
      const [nx, ny] = point(item.now_x, item.now_y), angle = item.course * Math.PI / 180;
      const ahead = item.speed_kn / 3600 * 1800;
      const [ax, ay] = point(item.now_x + Math.sin(angle) * ahead, item.now_y - Math.cos(angle) * ahead);
      context.moveTo(x, y); context.lineTo(nx, ny); context.stroke();
      context.setLineDash([8, 8]); context.beginPath(); context.moveTo(nx, ny); context.lineTo(ax, ay); context.stroke(); context.setLineDash([]);
      context.beginPath(); context.rect(nx - 4, ny - 4, 8, 8);
      [lx, ly] = [nx, ny];
    }
    context.stroke();
    context.fillText(plotText(item), lx + 8, ly - 6);
    if (info) addMapInfo(info, lx, ly, "plot", item);
  }
  const anchor = S.plotAnchor && S.plotAnchor.role === S.v2State?.role ? S.plotAnchor : null;
  if (anchor) {
    const [x, y] = point(anchor.x, anchor.y);
    context.beginPath(); context.arc(x, y, 5, 0, Math.PI * 2); context.stroke();
  }
  context.restore();
}
