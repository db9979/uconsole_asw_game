import { S } from "../state/store.js";
import { $, damageStates, isBoatCommand, isSonar, opforRoles } from "../core/base.js";
import { enumText, finite, number, stateText, t, unit } from "../core/format.js";
import { palette, paletteAlpha } from "../core/palette.js";
import { syncPlotAnimation } from "../plot/clock.js";
import { heatmap } from "../plot/heatmap.js";
import { spectrum } from "../plot/spectrum.js";
import { filteredEloka, mapRoles, overviewPlotList, ultraWide, wideScreen } from "../state/shared.js";
import { drawSonarVisuals } from "../stations/sonar-visuals.js";
import { clearVisuals, node } from "./dom.js";
import { drawRoleMap, syncOpzSweepAnimation } from "./role-map.js";
import { drawEmpty, roseFace, visualContext } from "./visual-common.js";
import { schedule } from "../core/scheduler.js";
import { drawRadioVisual } from "../stations/radio.js";
import { drawUbootEngineDials, renderUbootEngineConsole } from "../stations/uboot-engine-room.js";
import { drawEngineDials, renderEngineConsole } from "../stations/engine-room.js";
import { drawShipPlan, renderDamageLamps } from "../stations/damage-plan.js";

function drawDamageVisual() {
  const plot = visualContext("damage-schematic"), payload = S.v2State.damage;
  S.damageHits = [];
  renderDamageLamps(payload);
  if (!plot) return;
  S.damageHits = drawShipPlan(plot, payload, Number($("damage-team").value));
  $("damage-schematic-text").replaceChildren(...payload.compartments.map((room) => node("p", t("damage_compartment_equivalent", {name: room.name, flood: number(room.flood, 0), fire: number(room.fire, 0), flood_trend: number(room.trend.flood_rate, 2), fire_trend: number(room.trend.fire_rate, 2), teams: payload.teams.filter((team) => team.compartment === room.key).map((team) => team.team).join(", ") || t("station_none")}))));
  if (!payload.compartments.length) $("damage-schematic-text").textContent = t("visual_empty");
}
function drawElokaVisual() {
  const plot = visualContext("eloka-scope"), payload = S.v2State.eloka;
  if (!plot) return;
  const intercepts = filteredEloka(payload.intercepts);
  const simNow = finite(S.v2State.clock?.sim) ? S.v2State.clock.sim : 0;
  const scopeWidth = plot.width * .43;
  const radius = Math.min(scopeWidth, plot.height) * .38, cx = scopeWidth / 2, cy = plot.height / 2;
  roseFace(plot.context, cx, cy, radius);
  for (const row of intercepts) { const angle = row.bearing * Math.PI / 180; plot.context.save(); plot.context.globalAlpha = .2 + .8 * row.quality; plot.context.strokeStyle = palette().amber; plot.context.lineWidth = 2 + row.quality * 3; if (row.signal_state !== "LIVE") plot.context.setLineDash([5, 5]); plot.context.beginPath(); plot.context.moveTo(cx, cy); plot.context.lineTo(cx + Math.sin(angle) * radius, cy - Math.cos(angle) * radius); plot.context.stroke(); plot.context.restore(); }
  const focused = intercepts[0];
  const gx = scopeWidth + 12, gy = 16, gw = plot.width - gx - 12, gh = plot.height - 32;
  plot.context.strokeStyle = palette().line; plot.context.lineWidth = 1; plot.context.strokeRect(gx, gy, gw, gh);
  plot.context.beginPath(); plot.context.moveTo(gx, gy + gh * .52); plot.context.lineTo(gx + gw, gy + gh * .52); plot.context.stroke();
  if (focused && gw > 40 && gh > 60) {
    const motionNow = Math.min(simNow, simNow - focused.age_s + 2);
    const rate = .35 + Math.min(2.4, Math.log10(Math.max(1, focused.prf_hz || 500)) * .38);
    const techniqueRate = focused.jamming_technique === "vgpo" ? 1 + (focused.jamming_effectiveness || 0) * 1.8 : 1;
    const phase = (((Math.round(focused.frequency_hz / 1e6) + Math.round(focused.prf_hz || 500)) % 360) * Math.PI / 180) + motionNow * rate * techniqueRate;
    const pulses = Math.max(3, Math.min(12, Math.round(2 + Math.log10(Math.max(1, focused.prf_hz || 500)) * 2)));
    const hop = focused.modulation === "frequency_agile" ? ((Math.floor(motionNow * 2) % 7) - 3) * .025 : 0;
    const centers = (focused.modulation === "frequency_agile" ? [.28, .5, .72] : [.5]).map((value) => value + hop);
    const width = focused.modulation === "continuous_wave" ? .035 : ["pulse_doppler", "frequency_agile"].includes(focused.modulation) ? .09 : .14;
    plot.context.strokeStyle = palette().amber; plot.context.lineWidth = 2; plot.context.beginPath();
    for (let i = 0; i < 40; i++) { const x = i / 39; let value = Math.max(...centers.map((center) => Math.exp(-Math.pow((x - center) / width, 2)))); if (focused.jamming_technique === "noise") value = Math.max(value, (.28 + .08 * Math.sin(i * .71 + motionNow * 5)) * (focused.jamming_effectiveness || 0)); if (focused.jamming_technique === "false_targets") value = Math.max(value, ...centers.map((center) => .55 * (focused.jamming_effectiveness || 0) * Math.exp(-Math.pow((x - center - .14) / width, 2)))); const px = gx + 6 + x * (gw - 12), py = gy + gh * .47 - value * focused.quality * gh * .34; if (i) plot.context.lineTo(px, py); else plot.context.moveTo(px, py); }
    plot.context.stroke(); plot.context.strokeStyle = palette().accent; plot.context.beginPath();
    for (let i = 0; i < 48; i++) { const x = i / 47; const movingX = (x + motionNow * rate * .08 + (focused.jamming_technique === "rgpo" ? motionNow * (focused.jamming_effectiveness || 0) * .03 : 0)) % 1; let value;
      if (focused.modulation === "continuous_wave") value = Math.sin(Math.PI * 10 * x + phase);
      else if (focused.modulation === "frequency_agile") { const steps = [-.75, .15, .7, -.25, .45, -.55, .85, 0]; value = steps[(Math.min(7, Math.floor(movingX * 8)) + Math.floor(motionNow * 2)) % 8]; }
      else if (["pulse", "pulse_doppler"].includes(focused.modulation)) { const envelope = Math.max(0, 1 - ((movingX * pulses) % 1) / .16); value = envelope * 2 - .85; if (focused.modulation === "pulse_doppler") value *= .65 + .35 * Math.sin(Math.PI * 3 * pulses * movingX + phase); }
      else value = .55 * Math.sin(Math.PI * 6 * x + phase) + .25 * Math.sin(Math.PI * 22 * x + phase * .37);
      if (focused.jamming_technique === "noise") value = value * (1 - .45 * (focused.jamming_effectiveness || 0)) + Math.sin(i * 2.17 + motionNow * 11) * .55 * (focused.jamming_effectiveness || 0);
      if (focused.jamming_technique === "false_targets") value += Math.sin(Math.PI * 6 * ((movingX + .14) % 1) + phase) * .35 * (focused.jamming_effectiveness || 0);
      value *= focused.quality;
      const px = gx + 6 + x * (gw - 12), py = gy + gh * .76 - value * gh * .17; if (i) plot.context.lineTo(px, py); else plot.context.moveTo(px, py); }
    plot.context.stroke(); plot.context.fillStyle = palette().text; plot.context.textAlign = "left";
    plot.context.fillText(`${focused.label} / ${focused.modulation}`, gx + 8, gy + 17, gw - 16);
    plot.context.fillStyle = focused.signal_state === "LIVE" ? palette().accent : palette().amber; plot.context.textAlign = "right";
    const signalLabel = focused.signal_state === "MEMORY" ? t("eloka_signal_memory", {age: number(focused.age_s, 0)}) : t(`eloka_signal_${focused.signal_state.toLowerCase()}`);
    plot.context.fillText(signalLabel, gx + gw - 8, gy + 17, gw / 2);
    plot.context.fillStyle = palette().text; plot.context.textAlign = "left";
    plot.context.fillText(`${number(focused.frequency_hz / 1e9, 3)} GHz / ${number(focused.prf_hz, 0)} Hz`, gx + 8, gy + gh - 7, gw - 16);
  }
  if (!intercepts.length) drawEmpty(plot);
  const equivalents = intercepts.map((row) => node("p", t("eloka_equivalent", {ref: row.label, bearing: number(row.bearing, 0), frequency: number(row.frequency_hz, 0), prf: number(row.prf_hz, 0), modulation: row.modulation, candidates: row.candidates.map((item) => item.name).join(", ") || t("station_none"), correlations: row.correlations.map((item) => item.ref).join(", ") || t("station_none")})));
  if (focused) equivalents.push(node("p", t("eloka_signal_equivalent", {ref: focused.label, modulation: focused.modulation, frequency: number(focused.frequency_hz / 1e9, 3), prf: number(focused.prf_hz, 0)})));
  $("eloka-scope-text").replaceChildren(...equivalents);
  if (!intercepts.length) $("eloka-scope-text").textContent = t("visual_empty");
}
// Annunciator lamp on the canvas: an LED, a label and a value in a framed tile.
function canvasLamp(g, x, y, w, h, label, value, color) {
  g.fillStyle = paletteAlpha("raised", .92); g.fillRect(x, y, w, h);
  g.strokeStyle = color; g.globalAlpha = .75; g.strokeRect(x + .5, y + .5, w - 1, h - 1); g.globalAlpha = 1;
  const r = Math.min(7, h / 4), cx = x + 12 + r, cy = y + h / 2;
  g.fillStyle = color; g.shadowColor = color; g.shadowBlur = 8;
  g.beginPath(); g.arc(cx, cy, r, 0, Math.PI * 2); g.fill(); g.shadowBlur = 0;
  g.textAlign = "left"; g.fillStyle = palette().muted; g.fillText(label, cx + r + 8, cy - 4, w / 2);
  g.textAlign = "right"; g.fillStyle = palette().text; g.fillText(value, x + w - 10, cy + 12, w - 2 * r - 30);
}
function drawWeaponsVisual() {
  const plot = visualContext("weapons-system"), payload = S.v2State.weapons;
  if (!plot) return;
  const g = plot.context, p = palette(), readiness = payload.readiness, w = plot.width;
  const down = readiness.station_down, blocked = Boolean(readiness.interlock);
  const stages = [
    [t("weapons_lamp_station"), down ? t("station_down_state") : t("station_live_state"), down ? p.red : p.accent],
    [t("weapons_lamp_roe"), stateText("roe", readiness.roe), p.accent],
    [t("weapons_lamp_interlock"), blocked ? readiness.interlock : readiness.state, blocked ? p.amber : p.accent]];
  const lampW = (w - 20 - 2 * 10) / 3;
  stages.forEach(([label, value, color], index) => canvasLamp(g, 10 + index * (lampW + 10), 12, lampW, 46, label, value, color));
  // Tubes as columns: full when loaded, the reload counts down in the column.
  const tubes = payload.tubes, top = 76, height = Math.max(60, plot.height - top - 12);
  const pitch = Math.min(90, (w - 20) / Math.max(1, tubes.length));
  tubes.forEach((tube, index) => {
    const x = 10 + index * pitch, cw = pitch - 12, ready = tube.state === "ready";
    const color = ready ? p.accent : tube.state === "reloading" ? p.amber : p.muted;
    g.fillStyle = paletteAlpha("raised", .92); g.fillRect(x, top, cw, height);
    g.strokeStyle = p.line; g.strokeRect(x + .5, top + .5, cw - 1, height - 1);
    const fill = ready ? 1 : tube.state === "reloading" ? .35 : 0, inner = height - 46;
    g.fillStyle = color; g.globalAlpha = .55; g.fillRect(x + 4, top + 24 + inner * (1 - fill), cw - 8, inner * fill); g.globalAlpha = 1;
    g.fillStyle = color; g.shadowColor = color; g.shadowBlur = 8;
    g.beginPath(); g.arc(x + cw / 2, top + 12, 5, 0, Math.PI * 2); g.fill(); g.shadowBlur = 0;
    g.textAlign = "center"; g.fillStyle = p.text;
    g.fillText(`${t("weapons_tube")} ${number(tube.tube, 0)}`, x + cw / 2, top + height - 8, cw - 4);
    if (!ready && finite(tube.reload_s)) g.fillText(unit(tube.reload_s, "s", 0), x + cw / 2, top + 24 + inner / 2, cw - 4);
  });
  $("weapons-system-text").textContent = t("weapons_equivalent", {state: readiness.state, interlock: readiness.interlock, tubes: tubes.map((tube) => `${tube.tube}:${tube.state}/${number(tube.reload_s, 0)}s`).join(", ") || t("station_none"), nixies: number(payload.inventory.nixies, 0), active: payload.active_assets.length});
}
function visualStationDown(role) {
  const payload = S.v2State?.[role];
  return isSonar(role) ? payload.settings.station_down : isBoatCommand(role) ? ["sinking", "sunk"].includes(payload.status.state) :
    role === "weapons" ? payload.readiness.station_down :
    role === "opz" ? !payload.radar.live : role === "radio" ? payload.station_down :
    role === "engine" ? payload.machinery.station_state === "ZERSTOERT" : role === "eloka" ? payload.station_down : false;
}
function drawHelicopterAcoustic() {
  const acoustic = S.v2State?.helicopter?.acoustic;
  if (!acoustic || $("helicopter-buoy-console").hidden) return;
  const aged = (rows) => rows.map((bins, index) => ({bins, age_s: (rows.length - 1 - index) * .25}));
  // The buoy relay keeps a fixed number of 0.25 s rows; that span is its time axis.
  const span = (rows) => Math.max(20, rows.length * .25);
  heatmap("helicopter-broadband-canvas", aged(acoustic.broadband_history), null, null, (broadband) => {
    if (!finite(acoustic.listen_bearing)) return;
    broadband.context.strokeStyle = palette().amber;
    const x = acoustic.listen_bearing / 360 * broadband.width;
    broadband.context.beginPath(); broadband.context.moveTo(x, 0);
    broadband.context.lineTo(x, broadband.height); broadband.context.stroke();
  }, span(acoustic.broadband_history));
  spectrum("helicopter-spectrum-canvas", acoustic.spectrum,
    [], acoustic.bin_frequencies_hz, 300);
  heatmap("helicopter-lofar-canvas", aged(acoustic.history), acoustic.bin_frequencies_hz, null, null, span(acoustic.history));
  spectrum("helicopter-demon-canvas", acoustic.demon,
    [], acoustic.demon.map((_, index) => index + 1), 80);
}
function drawRoleVisuals() {
  const role = S.v2State?.role;
  if (!role || $("role-visuals").hidden) return;
  if (mapRoles.has(role) && $("map-visual").hidden === false) drawRoleMap(role);
  if (role === "helicopter") drawHelicopterAcoustic();
  if (isSonar(role)) drawSonarVisuals();
  if (role === "damage") drawDamageVisual();
  if (role === "engine") { renderEngineConsole(S.v2State.engine); drawEngineDials(); }
  if (role === "eloka") drawElokaVisual();
  if (role === "weapons") drawWeaponsVisual();
  if (role === "radio") drawRadioVisual();
  if (role === "uboot_engine") { renderUbootEngineConsole(S.v2State.uboot_engine); drawUbootEngineDials(); }
}
export function queueVisualDraw() {
  schedule("role-visuals", () => { drawRoleVisuals(); syncPlotAnimation(); });
}
export function renderRoleVisuals(role) {
  $("role-visuals").hidden = !role;
  // Very wide screens show the helicopter's acoustic console and map side by side.
  const split = role === "helicopter" && ultraWide.matches;
  $("role-visuals").dataset.split = split ? "on" : "off";
  $("helicopter-visual-tabs").hidden = role !== "helicopter" || split;
  $("helicopter-buoy-console").hidden = role !== "helicopter" || (!split && S.helicopterVisualPage !== "acoustic");
  $("helicopter-dip-display").hidden = role !== "helicopter" || split || S.helicopterVisualPage !== "map";
  for (const mode of ["acoustic", "map"])
    $(`helicopter-visual-${mode}`).setAttribute("aria-selected", String(S.helicopterVisualPage === mode));
  for (const plot of ["broadband", "lofar", "demon"]) {
    $(`helicopter-plot-${plot}`).hidden = S.helicopterPlot !== plot;
    $(`helicopter-acoustic-plot-tabs`).querySelector(`[data-helicopter-plot-tab="${plot}"]`)
      .setAttribute("aria-selected", String(S.helicopterPlot === plot));
  }
  for (const [id, active] of [["map-visual", mapRoles.has(role) && (role !== "helicopter" || split || S.helicopterVisualPage === "map")], ["sonar-visual", isSonar(role)],
    ["damage-visual", role === "damage"], ["engine-visual", role === "engine"],
    ["eloka-visual", role === "eloka"], ["weapons-visual", role === "weapons"], ["radio-visual", role === "radio"],
    ["uboot-engine-visual", role === "uboot_engine"]]) $(id).hidden = !active;
  // Each side has its own grease-pencil plot: the submarine commander draws on
  // the boat's, never the frigate's; the boat's sonar room has none.
  $("plot-tools").hidden = opforRoles.has(role) && !["uboot", "uboot_nav"].includes(role);
  if (!role) { clearVisuals(); return; }
  const stateKey = !S.connected ? "visual_stale" : S.v2State.phase !== "live" ? "visual_inactive" : visualStationDown(role) ? "visual_station_down" : "visual_live";
  $("role-visual-state").textContent = t(stateKey);
  for (const button of $("sonar-page-tabs").querySelectorAll("button")) {
    const selectedPage = button.dataset.sonarVisual === S.sonarVisualPage;
    button.setAttribute("aria-selected", String(selectedPage)); button.tabIndex = selectedPage ? 0 : -1;
  }
  const shownPlots = S.sonarVisualPage === "overview" ? overviewPlotList() : [S.sonarVisualPage];
  $("sonar-plots").dataset.layout = S.sonarVisualPage !== "overview" ? "single" :
    wideScreen.matches ? "overview-wide" : "overview";
  for (const panel of document.querySelectorAll("[data-sonar-plot]")) panel.hidden = !shownPlots.includes(panel.dataset.sonarPlot);
  queueVisualDraw();
  syncOpzSweepAnimation();
}
