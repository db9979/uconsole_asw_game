import { S } from "../state/store.js";
import { $, affiliations, isBoatCommand } from "../core/base.js";
import { classificationText, enumText, finite, hasPosition, number, t, unit } from "../core/format.js";
import { colors, palette, paletteAlpha, paletteRgb } from "../core/palette.js";
import { drawNatoSymbol } from "../plot/symbols.js";
import { maxRoleMapHits, roleMapViews } from "../state/shared.js";
import { drawPlotLayer, releaseCanvas, renderPlotList, resizeCanvas } from "./chart.js";
import { node, position } from "./dom.js";
import { visualContext } from "./visual-common.js";
import { DISPLAY_CLOCK_LAG_S, displaySimNow } from "../state/display-clock.js";
import { roleMapSweepCanvas, roleMapSweepCtx } from "./canvases.js";
import { labelField, placeText, placeTip, reserveText } from "./label-layout.js";
import { drawAfterglow, drawFurthestOn, drawMapFx, furthestOnNm, mapFxActive } from "./map-fx.js";
import { drawOpzCpa, drawOpzRings, drawOpzTrails, opzLabel, opzLayer, opzVectorMinutes, syncOpzDisplayBar } from "./opz-display.js";

export function mapPayload(role) {
  const payload = S.v2State[role];
  // The bridge's autopilot route: the waypoints still ahead, numbered.
  if (role === "bridge") return {own: payload.navigation, observations: payload.tactical_summary,
    assets: payload.route.points.map((row) => ({x: row.x, y: row.y, waypoint: true,
      display: t("bridge_route_point", {number: row.number})})), bearingLogs: [], fixes: []};
  if (role === "weapons") return {own: payload.navigation, observations: payload.tactical, assets: payload.active_assets, bearingLogs: [], fixes: []};
  if (role === "opz") {
    // Reports inside a fusion are drawn only while managing the picture.
    const fused = new Set(payload.fusions.flatMap((row) => row.members));
    // The consort destroyer (own-force datalink truth), its search point and
    // its sonar's bearing lines.
    const consort = payload.own_assets.consort;
    const consortAssets = consort && !consort.sunk ? [{ref: "consort", display: consort.callsign, x: consort.x, y: consort.y},
      ...(consort.point_x !== null && ["search", "prosecute"].includes(consort.working)
        ? [{x: consort.point_x, y: consort.point_y, waypoint: true, display: t("consort_point")}] : [])] : [];
    return {own: payload.own_assets.ship, observations: [...payload.observations.filter((row) => S.opzManage || !fused.has(row.ref)), ...payload.fusions], assets: [...(payload.own_assets.helicopter.airborne ? [payload.own_assets.helicopter] : []), ...consortAssets, ...payload.own_assets.weapons], bearingLogs: consort && !consort.sunk ? consort.bearings : [], fixes: []};
  }
  if (role === "radio") return {own: payload.navigation, observations: payload.tactical, assets: [], bearingLogs: payload.logged_bearings, fixes: payload.logged_fixes};
  if (isBoatCommand(role)) {
    // The boat's own position (legitimate truth) and its own sonar contacts only.
    const nav = payload.navigation;
    const weapons = payload.weapons;
    return {own: {x: nav.x, y: nav.y, course: nav.course, speed: nav.speed,
      arc: finite(weapons.arc_center_deg) && finite(weapons.arc_width_deg) && weapons.arc_width_deg < 360
        ? {center: weapons.arc_center_deg, width: weapons.arc_width_deg} : null},
      observations: payload.contacts.map((row) => ({...row, domain: "UNKNOWN", affiliation: "UNKNOWN"})),
      assets: payload.own_weapons,
      // ESM mapping: the last bearings of each emitter from where the boat
      // took them, and the crew's cross-fixes with their error ellipse.
      bearingLogs: payload.esm.emitters.flatMap((row) => row.history.slice(-4).map((item) =>
        ({observer_x: item.x, observer_y: item.y, bearing: item.bearing, age_s: item.age_s}))).slice(0, 64),
      fixes: payload.esm.emitters.filter((row) => row.fix).map((row) => ({ref: row.label, display: row.label,
        x: row.fix.x, y: row.fix.y, uncertainty_nm: row.fix.major_nm,
        ellipse: {major: row.fix.major_nm, minor: row.fix.minor_nm, axis: row.fix.axis_deg}})).concat(
        // HQ's latest contact report from the radio room, with its error circle.
        payload.radio.report ? [{ref: "HQ", geo: true, x: payload.radio.report.x, y: payload.radio.report.y,
          uncertainty_nm: payload.radio.report.radius_nm,
          display: t("uboot_radio_chart_label", {age: Math.round((payload.radio.report.age_s ?? 0) / 60)})}] : []),
      // Dead reckoning: the crew's chart (coast, soundings, HQ's report, the
      // route) lies where the navigator believes it lies against the boat.
      geoShift: finite(nav.est_x) && finite(nav.est_y) ? {x: nav.est_x - nav.x, y: nav.est_y - nav.y} : null,
      route: nav.route.points.slice(nav.route.active ? nav.route.index : 0).map(([x, y]) => ({x, y})),
      routeActive: nav.route.active,
      routeWaypoints: nav.route.points.map(([x, y], index) => ({x, y, geo: true, waypoint: true,
        display: t("bridge_route_point", {number: index + 1})}))};
  }
  return {own: payload.navigation, observations: payload.tactical,
    assets: [payload.asset, ...payload.buoys.map((buoy) => ({...buoy, display: buoy.label})),
      ...(payload.waypoint ? [{...payload.waypoint, waypoint: true}] : [])], bearingLogs: [], fixes: []};
}
// The host sweep turns at a constant rate in sim time, so every sample fixes
// one phase offset (bearing - rate * sim). The strobe is drawn against the
// shared smoothed display clock, which only ever advances (with at most
// +/-10 % rate correction), so the beam turns steadily and never steps back
// when a delayed or duplicate publication arrives.
const wrap360 = (value) => ((value % 360) + 360) % 360;
export function currentOpzSweepBearing() {
  const model = S.opzSweepSample;
  if (!model) return null;
  return wrap360(model.offset + (displaySimNow() + DISPLAY_CLOCK_LAG_S) * model.rate);
}
export function updateOpzSweepSample(state) {
  const radar = state?.role === "opz" ? state.opz.radar : null;
  if (!radar || !finite(radar.sweep_bearing) || !finite(state.clock?.sim)) {
    S.opzSweepSample = null; stopOpzSweepAnimation(); return;
  }
  const rate = finite(radar.sweep_rate_deg_s) ? radar.sweep_rate_deg_s : 90;
  S.opzSweepSample = {offset: wrap360(radar.sweep_bearing - state.clock.sim * rate), rate};
}
// The overlay animates while the OPZ radar turns or a moving mark (ping
// wavefront, echo, splash) is still on the chart.
function opzSweepActive() {
  const radar = S.v2State?.role === "opz" ? S.v2State.opz.radar : null;
  const sweeping = S.opzSweepSample?.rate > 0 && radar?.live === true && (radar.surface || radar.air);
  return S.connected && !document.hidden && navigator.onLine !== false && S.v2State?.phase === "live" &&
    (sweeping || mapFxActive(S.v2State?.plot?.fx)) && !$("role-map").closest("[hidden]") &&
    $("role-map").clientWidth > 0 && $("role-map").clientHeight > 0;
}
export function stopOpzSweepAnimation() {
  if (S.opzSweepFrame !== null) cancelAnimationFrame(S.opzSweepFrame);
  S.opzSweepFrame = null;
}
export function syncOpzSweepAnimation() {
  if (!opzSweepActive()) { stopOpzSweepAnimation(); drawOpzSweepOverlay(); return; }
  if (S.opzSweepFrame !== null) return;
  const animate = () => {
    S.opzSweepFrame = null;
    if (!opzSweepActive()) return;
    drawOpzSweepOverlay();
    S.opzSweepFrame = requestAnimationFrame(animate);
  };
  S.opzSweepFrame = requestAnimationFrame(animate);
}
export function roleMapGeometry(role, width = $("role-map").clientWidth, height = $("role-map").clientHeight) {
  const viewState = roleMapViews[role];
  if (!S.chart || !viewState || !width || !height) return null;
  const scale = Math.min(width, height) / S.chart.size_nm * viewState.zoom;
  return {scale, point: (x, y) => [width / 2 + (x - viewState.x) * scale,
    height / 2 + (y - viewState.y) * scale]};
}
function addRoleMapHit(ref, x, y) {
  if (S.roleMapHits.length < maxRoleMapHits && x >= -26 && y >= -26 &&
      x <= $("role-map").clientWidth + 26 && y <= $("role-map").clientHeight + 26) {
    S.roleMapHits.push({ref, x, y});
  }
}
export function drawChartHazards(context, hazards, point, width, height, pxPerNm, info) {
  for (const hazard of hazards) {
    const [x, y] = point(hazard.x, hazard.y);
    if (x < -8 || x > width + 8 || y < -8 || y > height + 8) continue;
    addMapInfo(info, x, y, "hazard", hazard);
    context.save();
    context.lineWidth = 1.5;
    context.strokeStyle = hazard.kind === "wreck" ? palette().muted : palette().amber;
    context.beginPath();
    if (hazard.kind === "wreck") {
      context.moveTo(x - 8, y); context.lineTo(x + 8, y);
      for (const dx of [-4, 0, 4]) { context.moveTo(x + dx, y - 5); context.lineTo(x + dx, y + 5); }
    } else {
      context.moveTo(x - 5, y); context.lineTo(x + 5, y); context.moveTo(x, y - 5); context.lineTo(x, y + 5);
      context.moveTo(x - 4, y - 4); context.lineTo(x + 4, y + 4); context.moveTo(x - 4, y + 4); context.lineTo(x + 4, y - 4);
    }
    context.stroke();
    if (pxPerNm >= 12) {
      context.fillStyle = context.strokeStyle;
      context.textAlign = "left";
      context.fillText(t("chart_hazard_depth", {depth: number(hazard.top_depth_m, 0)}), x + 12, y + 4);
    }
    context.restore();
  }
}
export function addMapInfo(list, x, y, kind, item) {
  if (list.length < 512) list.push({x, y, kind, item});
}
function chartDepthAt(x, y) {
  const grid = S.chart?.geography?.depths;
  if (!Array.isArray(grid) || !grid.length || !finite(S.chart.size_nm)) return null;
  const n = grid.length;
  const row = grid[Math.min(n - 1, Math.max(0, Math.floor(y / S.chart.size_nm * n)))];
  if (!Array.isArray(row) || !row.length) return null;
  const value = row[Math.min(row.length - 1, Math.max(0, Math.floor(x / S.chart.size_nm * row.length)))];
  return finite(value) ? value : null;
}
export function mapTooltipLines(hit, worldX, worldY, own) {
  const lines = [];
  if (hit?.kind === "track") {
    const row = hit.item;
    lines.push(String(row.label || row.ref || ""));
    if (row.source) lines.push(t("map_tip_source", {source: row.source}));
    if (row.classification !== undefined || row.affiliation !== undefined)
      lines.push(t("map_tip_class", {classification: classificationText(row.classification),
        affiliation: enumText(affiliations, row.affiliation)}));
    if (finite(row.bearing)) lines.push(finite(row.range_nm) ?
      t("map_tip_bearing_range", {bearing: number(row.bearing, 0), range: number(row.range_nm, 1)}) :
      t("map_tip_bearing", {bearing: number(row.bearing, 0)}));
    if (finite(row.course)) lines.push(t("map_tip_course", {course: number(row.course, 0),
      speed: finite(row.speed_kn) ? number(row.speed_kn, 0) : "--"}));
    if (finite(row.altitude_m)) lines.push(t("map_tip_altitude", {altitude: number(row.altitude_m, 0)}));
    if (finite(row.age_s)) lines.push(t("map_tip_age", {age: number(row.age_s, 0),
      quality: finite(row.quality) ? number(row.quality * 100, 0) : "--"}));
    return lines;
  }
  if (hit?.kind === "fix") {
    lines.push(t("map_tip_fix", {label: String(hit.item.label || ""), source: String(hit.item.source || "")}));
    if (finite(hit.item.uncertainty_nm)) lines.push(t("map_tip_uncertainty", {value: number(hit.item.uncertainty_nm, 1)}));
    if (finite(hit.item.depth_m)) lines.push(t("map_tip_depth_estimate", {depth: number(hit.item.depth_m, 0)}));
    return lines;
  }
  if (hit?.kind === "own") {
    lines.push(t("map_tip_own"));
    lines.push(t("map_tip_course", {course: number(hit.item.course, 0), speed: number(hit.item.speed, 1)}));
    return lines;
  }
  if (hit?.kind === "asset") {
    lines.push(hit.item.waypoint ? t("station_waypoint") : String(hit.item.display || hit.item.ref || t("helicopter")));
    if (finite(hit.item.depth_m)) lines.push(t("map_tip_depth_estimate", {depth: number(hit.item.depth_m, 0)}));
    if (finite(hit.item.course)) lines.push(t("map_tip_course", {course: number(hit.item.course, 0), speed: "--"}));
    return lines;
  }
  if (hit?.kind === "hazard") {
    const hazard = hit.item;
    lines.push(t(hazard.kind === "wreck" ? "map_tip_wreck" : "map_tip_rock"));
    lines.push(t("map_tip_hazard_top", {depth: number(hazard.top_depth_m, 0)}));
    if (hazard.kind === "wreck") lines.push(t("map_tip_wreck_length", {length: number(hazard.length_m, 0)}));
    lines.push(t("map_tip_hazard_note"));
    return lines;
  }
  if (hit?.kind === "base") {
    lines.push(String(hit.item.name || ""));
    lines.push(t("map_tip_airbase"));
    return lines;
  }
  if (!finite(worldX) || !finite(worldY) || !S.chart || worldX < 0 || worldY < 0 ||
      worldX > S.chart.size_nm || worldY > S.chart.size_nm) return lines;
  lines.push(t("map_tip_position", {x: number(worldX, 1), y: number(worldY, 1)}));
  const depth = chartDepthAt(worldX, worldY);
  if (depth !== null) lines.push(depth <= 0 ? t("map_tip_land") : t("map_tip_chart_depth", {depth: number(depth, 0)}));
  if (own && finite(own.x) && finite(own.y)) {
    const dx = worldX - own.x, dy = worldY - own.y;
    lines.push(t("map_tip_from_own", {bearing: number(((Math.atan2(dx, -dy) * 180 / Math.PI) + 360) % 360, 0),
      range: number(Math.hypot(dx, dy), 1)}));
  }
  return lines;
}
export function showMapTooltip(event, lines) {
  const element = $("map-tooltip");
  if (!lines.length) { element.hidden = true; return; }
  element.replaceChildren(...lines.map((line, index) => node(index ? "span" : "strong", line)));
  element.hidden = false;
  const margin = 14, box = element.getBoundingClientRect();
  const left = Math.min(event.clientX + margin, window.innerWidth - box.width - 4);
  const top = Math.min(event.clientY + margin, window.innerHeight - box.height - 4);
  element.style.left = `${Math.max(4, left)}px`;
  element.style.top = `${Math.max(4, top)}px`;
}
export function hideMapTooltip() {
  $("map-tooltip").hidden = true;
}
export function nearestMapInfo(list, x, y, radius = 14) {
  let best = null;
  for (const hit of list) {
    const distance = Math.hypot(hit.x - x, hit.y - y);
    if (distance <= radius && (best === null || distance < best.distance)) best = {hit, distance};
  }
  return best?.hit || null;
}
export function rayLengthToCanvasEdge(x, y, dx, dy, width, height) {
  const candidates = [];
  if (dx > 0) candidates.push((width - x) / dx);
  else if (dx < 0) candidates.push(-x / dx);
  if (dy > 0) candidates.push((height - y) / dy);
  else if (dy < 0) candidates.push(-y / dy);
  return Math.max(0, Math.min(...candidates.filter((value) => finite(value) && value >= 0)));
}
function drawOpzSweepOverlay() {
  const width = roleMapSweepCanvas.clientWidth;
  const height = roleMapSweepCanvas.clientHeight;
  if (!width || !height || !S.chart || $("role-map-sweep").closest("[hidden]")) {
    releaseCanvas(roleMapSweepCanvas);
    return;
  }
  resizeCanvas(roleMapSweepCanvas, roleMapSweepCtx, width, height);
  roleMapSweepCtx.clearRect(0, 0, width, height);
  const role = S.v2State?.role, fxGeometry = role ? roleMapGeometry(role, width, height) : null;
  // Marks spread only while the mission runs; after the end they hold still.
  if (fxGeometry && S.v2State?.plot?.fx && S.v2State.phase === "live") drawMapFx(roleMapSweepCtx, S.v2State.plot.fx, fxGeometry.point, fxGeometry.scale);
  const radar = S.v2State?.role === "opz" ? S.v2State.opz.radar : null;
  const own = S.v2State?.role === "opz" ? S.v2State.opz.own_assets.ship : null;
  if (!radar?.live || !(radar.surface || radar.air) || !hasPosition(own)) return;
  const geometry = roleMapGeometry("opz", width, height);
  if (!geometry) return;
  const [ox, oy] = geometry.point(own.x, own.y);
  const bearing = S.v2State.phase === "live" && S.connected ?
    currentOpzSweepBearing() ?? radar.sweep_bearing : radar.sweep_bearing;
  if (!finite(bearing)) return;
  const angle = bearing * Math.PI / 180;
  const dx = Math.sin(angle), dy = -Math.cos(angle);
  // The beam reaches as far as the own radar does: the effective range of
  // the longest-reaching active radar, not the display scale or canvas edge.
  const reach = Math.max(radar.surface ? radar.surface_effective_range_nm : 0,
    radar.air ? radar.air_effective_range_nm : 0);
  const length = reach * geometry.scale;
  if (opzLayer("afterglow")) drawAfterglow(roleMapSweepCtx, ox, oy, length, bearing);
  roleMapSweepCtx.strokeStyle = palette().accent;
  roleMapSweepCtx.lineWidth = 1.5;
  roleMapSweepCtx.beginPath();
  roleMapSweepCtx.moveTo(ox, oy);
  roleMapSweepCtx.lineTo(ox + dx * length, oy + dy * length);
  roleMapSweepCtx.stroke();
}
export function drawRoleMap(role) {
  const plot = visualContext("role-map");
  S.roleMapHits = [];
  S.roleMapInfo = [];
  if (!plot || !S.chart) return;
  const payload = S.v2State[role], data = mapPayload(role), viewState = roleMapViews[role];
  syncOpzDisplayBar(role);
  // The OPZ's display settings (opz-display.js); other charts draw everything.
  const opz = role === "opz", layer = (key) => !opz || opzLayer(key);
  plot.context.textAlign = "left";
  plot.context.textBaseline = "alphabetic";
  if (!viewState.initialized) { viewState.initialized = true; viewState.follow = true; viewState.zoom = role === "opz" ? S.chart.size_nm / (2 * payload.radar.range_nm) : 2; }
  const followTarget = role === "helicopter" && payload.asset.airborne && hasPosition(payload.asset) ?
    payload.asset : data.own;
  if (viewState.follow && hasPosition(followTarget)) { viewState.x = followTarget.x; viewState.y = followTarget.y; }
  $("role-map-follow").setAttribute("aria-pressed", String(Boolean(viewState.follow)));
  $("role-map-follow").textContent = t(role === "helicopter" ? "follow_helicopter" : "follow");
  const {scale, point: framePoint} = roleMapGeometry(role, plot.width, plot.height);
  // Chart data in the crew's navigated frame (the boat's dead reckoning).
  const shift = data.geoShift;
  const point = shift ? (x, y) => framePoint(x - shift.x, y - shift.y) : framePoint;
  const geo = S.chart.geography;
  if (geo?.depths.length && layer("chart")) {
    const size = geo.depths.length, cell = S.chart.size_nm / Math.max(1, size - 1);
    const shallow = paletteRgb("shallow"), deepest = paletteRgb("deep");
    for (let y = 0; y < size - 1; y++) for (let x = 0; x < geo.depths[y].length - 1; x++) {
      const [px, py] = point(x * cell, y * cell);
      if (px > plot.width || py > plot.height || px + cell * scale < 0 || py + cell * scale < 0) continue;
      const deep = Math.max(0, Math.min(1, geo.depths[y][x] / 900));
      plot.context.fillStyle = `rgb(${shallow.map((channel, index) => Math.round(channel + (deepest[index] - channel) * deep)).join(" ")})`;
      plot.context.fillRect(px, py, cell * scale + 1, cell * scale + 1);
    }
  }
  const step = viewState.zoom >= 8 ? 10 : viewState.zoom >= 3 ? 25 : 50;
  plot.context.strokeStyle = palette().grid; plot.context.fillStyle = palette().label;
  for (let value = 0; value <= S.chart.size_nm && layer("chart"); value += step) {
    const [x, y] = point(value, value);
    if (x >= 0 && x <= plot.width) { plot.context.beginPath(); plot.context.moveTo(x, 0); plot.context.lineTo(x, plot.height); plot.context.stroke(); }
    if (y >= 0 && y <= plot.height) { plot.context.beginPath(); plot.context.moveTo(0, y); plot.context.lineTo(plot.width, y); plot.context.stroke(); }
  }
  plot.context.strokeStyle = palette().landEdge; plot.context.fillStyle = palette().land;
  for (const land of S.chart.landmasses) {
    plot.context.beginPath(); land.points.forEach(([x, y], index) => { const p = point(x, y); index ? plot.context.lineTo(...p) : plot.context.moveTo(...p); });
    plot.context.closePath(); plot.context.fill(); plot.context.stroke();
  }
  plot.context.font = "12px sans-serif";
  // One label field for the whole map: axis numbers and the north mark are
  // reserved first, contact and speed labels step aside from them.
  const labels = labelField(plot.width, plot.height);
  labels.reserve(plot.width - 40, 4, 36, 18);
  plot.context.lineWidth = 3;
  plot.context.strokeStyle = palette().halo;
  plot.context.fillStyle = palette().text;
  for (let value = 0; value <= S.chart.size_nm && layer("chart"); value += step) {
    const [x, y] = point(value, value), text = String(value);
    if (x >= 0 && x + plot.context.measureText(text).width + 2 <= plot.width) {
      plot.context.strokeText(text, x + 2, plot.height - 5);
      plot.context.fillText(text, x + 2, plot.height - 5);
      reserveText(plot.context, labels, text, x + 2, plot.height - 5);
    }
    if (y >= 10 && y <= plot.height - 20) {
      const baseline = y + 4;
      plot.context.strokeText(text, 4, baseline);
      plot.context.fillText(text, 4, baseline);
      reserveText(plot.context, labels, text, 4, baseline);
    }
  }
  plot.context.lineWidth = 1;
  plot.context.fillStyle = palette().muted;
  for (const label of [...(geo?.labels || []), ...(geo?.airbases || [])]) {
    const [x, y] = point(label.x, label.y);
    if (x >= 0 && x <= plot.width && y >= 0 && y <= plot.height) placeText(plot.context, labels, label.name, x + 5, y - 5);
  }
  for (const base of geo?.airbases || []) { const [x, y] = point(base.x, base.y); plot.context.strokeRect(x - 3, y - 3, 6, 6); addMapInfo(S.roleMapInfo, x, y, "base", base); }
  // Charted wrecks (hull line with masts) and underwater rocks (asterisk).
  drawChartHazards(plot.context, geo?.hazards || [], point, plot.width, plot.height,
    Math.abs(point(1, 0)[0] - point(0, 0)[0]), S.roleMapInfo);
  const [ox, oy] = hasPosition(data.own) ? framePoint(data.own.x, data.own.y) : [plot.width / 2, plot.height / 2];
  labels.reserve(ox - 12, oy - 12, 24, 24);
  if (opz && hasPosition(data.own)) {
    // Range rings, bearing scale and the trails under the live symbols.
    drawOpzRings(plot.context, labels, ox, oy, payload.radar.range_nm, scale, data.own.course, plot.width, plot.height);
    const byRef = new Map(data.observations.map((row) => [row.ref, row]));
    drawOpzTrails(plot.context, payload.trails, (ref) => colors[byRef.get(ref)?.affiliation] || colors.UNKNOWN, framePoint);
  }
  if (hasPosition(data.own)) {
    addRoleMapHit(null, ox, oy);
    addMapInfo(S.roleMapInfo, ox, oy, "own", data.own);
    plot.context.save(); plot.context.translate(ox, oy); plot.context.rotate(data.own.course * Math.PI / 180);
    plot.context.strokeStyle = palette().accent; plot.context.fillStyle = palette().accent; plot.context.beginPath();
    plot.context.moveTo(0, -9); plot.context.lineTo(-5, 6); plot.context.lineTo(5, 6); plot.context.closePath(); plot.context.fill();
    plot.context.beginPath(); plot.context.moveTo(0, -9); plot.context.lineTo(0, -35); plot.context.stroke();
    if (data.own.arc) {
      // Submarine tube firing arc, relative to the bow (own-ship truth).
      const half = data.own.arc.width / 2, center = data.own.arc.center, toRad = Math.PI / 180;
      plot.context.globalAlpha = .18; plot.context.beginPath(); plot.context.moveTo(0, 0);
      plot.context.arc(0, 0, 80, (center - half - 90) * toRad, (center + half - 90) * toRad); plot.context.closePath();
      plot.context.fill(); plot.context.globalAlpha = 1; plot.context.stroke();
    }
    plot.context.restore();
  }
  for (const row of data.observations) {
    const isSelected = row.ref === S.selected;
    plot.context.strokeStyle = isSelected ? palette().accent : colors[row.affiliation] || colors.UNKNOWN;
    plot.context.lineWidth = isSelected ? 3 : 1;
    if (hasPosition(row)) {
      const [x, y] = framePoint(row.x, row.y);
      addRoleMapHit(row.ref, x, y);
      addMapInfo(S.roleMapInfo, x, y, "track", row);
      if (finite(row.range_uncertainty_nm)) { plot.context.beginPath(); plot.context.arc(x, y, row.range_uncertainty_nm * scale, 0, Math.PI * 2); plot.context.stroke(); }
      // Furthest-on circle: how far the contact can have gone since its fix.
      if (opz && layer("uncertainty")) { const reach = furthestOnNm(row.domain, row.age_s); if (reach !== null) drawFurthestOn(plot.context, x, y, reach * scale); }
      // Same NATO symbol as the chart and the uConsole: affiliation frame + domain glyph.
      const symbolColor = colors[row.affiliation] || colors.UNKNOWN;
      drawNatoSymbol(plot.context, x, y, row.affiliation, row.domain, symbolColor, 7);
      plot.context.strokeStyle = isSelected ? palette().accent : symbolColor;
      plot.context.lineWidth = isSelected ? 3 : 1;
      if (isSelected) { plot.context.beginPath(); plot.context.arc(x, y, 14, 0, Math.PI * 2); plot.context.stroke(); }
      plot.context.fillStyle = symbolColor;
      labels.reserve(x - 10, y - 10, 20, 20);
      const label = opz ? opzLabel(row.label || row.ref) : String(row.label || row.ref);
      if (label !== null) placeText(plot.context, labels, label, x + 12, y - 10);
      if (finite(row.course)) {
        // The OPZ draws the distance run in the chosen minutes (as the uConsole).
        const reach = opz && finite(row.speed_kn) ? Math.min(Math.max(10, row.speed_kn * opzVectorMinutes() / 60 * scale), Math.min(plot.width, plot.height) * .45) : 22;
        const angle = row.course * Math.PI / 180, tipX = x + Math.sin(angle) * reach, tipY = y - Math.cos(angle) * reach;
        plot.context.beginPath(); plot.context.moveTo(x, y); plot.context.lineTo(tipX, tipY); plot.context.stroke();
        if (finite(row.speed_kn)) placeTip(plot.context, labels, unit(row.speed_kn, "kn", 0), tipX, tipY, Math.sin(angle), -Math.cos(angle));
      }
    } else if (layer("bearings") && finite(row.bearing) && (hasPosition(data.own) ||
        finite(row.observer_x) && finite(row.observer_y))) {
      const [bx, by] = finite(row.observer_x) && finite(row.observer_y) ?
        framePoint(row.observer_x, row.observer_y) : [ox, oy];
      const angle = row.bearing * Math.PI / 180;
      if (finite(row.bearing_uncertainty_deg)) {
        const delta = row.bearing_uncertainty_deg * Math.PI / 180, length = Math.max(plot.width, plot.height);
        plot.context.fillStyle = paletteAlpha("amber", .08); plot.context.beginPath(); plot.context.moveTo(bx, by);
        plot.context.lineTo(bx + Math.sin(angle - delta) * length, by - Math.cos(angle - delta) * length);
        plot.context.lineTo(bx + Math.sin(angle + delta) * length, by - Math.cos(angle + delta) * length); plot.context.closePath(); plot.context.fill();
      }
      plot.context.setLineDash([5, 5]); plot.context.beginPath(); plot.context.moveTo(bx, by);
      plot.context.lineTo(bx + Math.sin(angle) * Math.max(plot.width, plot.height), by - Math.cos(angle) * Math.max(plot.width, plot.height)); plot.context.stroke(); plot.context.setLineDash([]);
    }
  }
  plot.context.lineWidth = 1;
  for (const log of data.bearingLogs) {
    const [x, y] = framePoint(log.observer_x, log.observer_y), angle = log.bearing * Math.PI / 180;
    plot.context.strokeStyle = palette().amber; plot.context.setLineDash([3, 4]); plot.context.beginPath(); plot.context.moveTo(x, y); plot.context.lineTo(x + Math.sin(angle) * plot.width, y - Math.cos(angle) * plot.width); plot.context.stroke(); plot.context.setLineDash([]);
  }
  if (role === "bridge" && payload.route.points.length && hasPosition(data.own)) {
    // The route leg by leg from the ship through each waypoint still ahead.
    plot.context.strokeStyle = palette().amber; plot.context.setLineDash([6, 4]); plot.context.beginPath();
    plot.context.moveTo(ox, oy);
    for (const row of payload.route.points) plot.context.lineTo(...point(row.x, row.y));
    plot.context.stroke(); plot.context.setLineDash([]);
  }
  if (data.routeActive && data.route.length && hasPosition(data.own)) {
    // The boat's route from the boat through each waypoint still ahead.
    plot.context.strokeStyle = palette().amber; plot.context.setLineDash([6, 4]); plot.context.beginPath();
    plot.context.moveTo(ox, oy);
    for (const row of data.route) plot.context.lineTo(...point(row.x, row.y));
    plot.context.stroke(); plot.context.setLineDash([]);
  }
  for (const item of [...data.fixes, ...data.assets, ...(data.routeWaypoints || [])]) if (hasPosition(item)) {
    const [x, y] = (item.geo ? point : framePoint)(item.x, item.y);
    addRoleMapHit(null, x, y);
    addMapInfo(S.roleMapInfo, x, y, "asset", item);
    plot.context.strokeStyle = item.waypoint ? palette().amber : palette().blue;
    if (item.ellipse) {
      // Error ellipse: axis is a nautical bearing (0 north, clockwise).
      plot.context.beginPath();
      plot.context.ellipse(x, y, Math.max(1, item.ellipse.major * scale), Math.max(1, item.ellipse.minor * scale),
        (item.ellipse.axis - 90) * Math.PI / 180, 0, Math.PI * 2);
      plot.context.stroke();
    } else if (finite(item.uncertainty_nm)) { plot.context.beginPath(); plot.context.arc(x, y, item.uncertainty_nm * scale, 0, Math.PI * 2); plot.context.stroke(); }
    plot.context.strokeRect(x - 4, y - 4, 8, 8);
    plot.context.fillStyle = plot.context.strokeStyle; placeText(plot.context, labels, String(item.waypoint ? item.display || t("station_waypoint") : item.display || item.ref || t("helicopter")), x + 6, y + 12);
  }
  if (role === "opz") {
    // Bare mast/snorkel echoes: an afterglow dot, no symbol; a click marks it.
    for (const blip of payload.radar_blips) {
      const [x, y] = point(blip.x, blip.y);
      addRoleMapHit(blip.ref, x, y);
      plot.context.globalAlpha = Math.max(.25, 1 - blip.age_s / 6);
      plot.context.fillStyle = palette().accent;
      plot.context.beginPath(); plot.context.arc(x, y, 3, 0, Math.PI * 2); plot.context.fill();
      plot.context.globalAlpha = 1;
    }
  }
  if (opz && hasPosition(data.own)) {
    const selected = data.observations.find((row) => row.ref === S.selected);
    if (selected) drawOpzCpa(plot.context, labels, data.own, selected, framePoint);
    if (payload.radar.live && (payload.radar.surface || payload.radar.air)) {
      for (const range of [payload.radar.surface_effective_range_nm, payload.radar.air_effective_range_nm]) if (finite(range)) { plot.context.strokeStyle = palette().lineStrong; plot.context.beginPath(); plot.context.arc(ox, oy, range * scale, 0, Math.PI * 2); plot.context.stroke(); }
    }
    const byRef = new Map(data.observations.map((row) => [row.ref, row]));
    for (const fusion of payload.fusions) if (hasPosition(fusion)) for (const ref of fusion.members) { const member = byRef.get(ref); if (hasPosition(member)) { plot.context.strokeStyle = palette().faint; plot.context.beginPath(); plot.context.moveTo(...point(fusion.x, fusion.y)); plot.context.lineTo(...point(member.x, member.y)); plot.context.stroke(); } }
  }
  drawPlotLayer(plot.context, framePoint, scale, plot.width, plot.height, null, labels);
  renderPlotList();
  $("role-map-scale").textContent = t("role_map_scale", {distance: number(S.chart.size_nm / viewState.zoom, 0)});
  plot.context.save(); plot.context.textAlign = "right"; plot.context.fillStyle = palette().text; plot.context.fillText("N ↑", plot.width - 10, 18); plot.context.restore();
  const equivalent = [t("role_map_own", {position: hasPosition(data.own) ? position(data.own) : t("unavailable")})];
  equivalent.push(...data.observations.map((row) => t("role_map_observation", {ref: row.ref, bearing: number(row.bearing, 0), position: hasPosition(row) ? position(row) : t("bearing_only")})));
  equivalent.push(...data.fixes.map((row) => t("role_map_fix", {ref: row.ref, position: position(row), uncertainty: number(row.uncertainty_nm, 1)})));
  $("role-map-text").replaceChildren(...equivalent.slice(0, 256).map((text) => node("li", text)));
  drawOpzSweepOverlay();
}
