import { S } from "../state/store.js";
import { $ } from "../core/base.js";
import { finite, number, selectedTrack, t, unit } from "../core/format.js";
import { palette } from "../core/palette.js";
import { plotAxes } from "../plot/axes.js";
import { registerAnimatedPlot } from "../plot/clock.js";
import { heatmap } from "../plot/heatmap.js";
import { bandSpectrum, drawBandLimits, drawHarmonicGuides } from "../plot/peaks.js";
import { spectrum } from "../plot/spectrum.js";
import { sonarDisplay, sonarHistory } from "../state/shared.js";
import { node, position, yesNo } from "../views/dom.js";
import { drawEmpty, visualContext } from "../views/visual-common.js";
import { DISPLAY_CLOCK_LAG_S, displaySimNow } from "../state/display-clock.js";

export const broadbandVisible = () => S.sonarVisualPage === "broadband" || S.sonarVisualPage === "overview";
export function drawSonarVisuals() {
  const visual = S.v2State.sonar.visualization;
  const historyRows = (name, fallback) => {
    const rows = [...sonarHistory[name].values()].filter((row) => row.stamp >= S.v2State.clock.sim - 600);
    return rows.length ? rows.sort((a, b) => b.stamp - a.stamp) : fallback;
  };
  const broadbandHistory = historyRows("broadband", visual.broadband.history);
  const lofarHistory = historyRows("lofar", visual.lofar.history);
  const demonHistory = historyRows("demon", visual.demon.history);
  heatmap("sonar-broadband", broadbandHistory, null, null, (broadband) => {
    const focusedTrack = selectedTrack();
    const bearing = visual.receiver.listen_bearing % 360;
    const half = visual.receiver.beam_width_deg / 2;
    broadband.context.strokeStyle = palette().muted;
    for (const value of [(bearing - half + 360) % 360, (bearing + half) % 360]) {
      const x = value / 360 * broadband.width;
      broadband.context.beginPath(); broadband.context.moveTo(x, 0);
      broadband.context.lineTo(x, broadband.height); broadband.context.stroke();
    }
    broadband.context.strokeStyle = palette().amber;
    const x = bearing / 360 * broadband.width;
    broadband.context.beginPath(); broadband.context.moveTo(x, 0);
    broadband.context.lineTo(x, broadband.height); broadband.context.stroke();
    if (finite(focusedTrack?.bearing)) {
      const selectedX = focusedTrack.bearing % 360 / 360 * broadband.width;
      broadband.context.strokeStyle = palette().accent;
      broadband.context.lineWidth = 3;
      broadband.context.beginPath(); broadband.context.moveTo(selectedX, 0);
      broadband.context.lineTo(selectedX, broadband.height); broadband.context.stroke();
      broadband.context.lineWidth = 1;
    }
  });
  const lofarGuides = (plot) => {
    drawBandLimits(plot, S.v2State.sonar.settings.band_hz);
    drawHarmonicGuides(plot, S.v2State.sonar.settings.harmonic_hz, 300);
  };
  heatmap("sonar-lofar", lofarHistory, visual.lofar.bin_frequencies_hz, null, lofarGuides);
  const vernier = visual.lofar.vernier;
  if (vernier) {
    // Vernier: the operator's 20 Hz window at native 0.5 Hz resolution.
    spectrum("sonar-spectrum", vernier.bins, [], vernier.bins.map((_, index) => vernier.low_hz + index * vernier.step_hz),
      vernier.high_hz, vernier.low_hz, null);
  } else spectrum("sonar-spectrum", visual.lofar.spectrum, [], visual.lofar.bin_frequencies_hz, 300, 0, lofarGuides);
  bandSpectrum("sonar-band-low", visual.lofar, 0, 40);
  bandSpectrum("sonar-band-mid", visual.lofar, 40, 100);
  bandSpectrum("sonar-band-high", visual.lofar, 100, 300);
  const peak = visual.demon.analysis?.modulation_peak_hz;
  const demonFrequencies = visual.demon.spectrum.map((_, index) => index + 1);
  const demonGuides = (plot) => {
    drawHarmonicGuides(plot, sonarDisplay.demonCursor, 50);
    const tools = S.v2State.sonar.settings.tools;
    plot.context.save(); plot.context.font = "11px ui-monospace, monospace";
    for (const [value, label, color] of [[tools.shaft_hz, "S", palette().accent], [tools.blade_hz, "B", palette().amber]]) {
      if (!finite(value) || value > 50) continue;
      const x = value / 50 * plot.width;
      plot.context.strokeStyle = color; plot.context.fillStyle = color;
      plot.context.beginPath(); plot.context.moveTo(x, 0); plot.context.lineTo(x, plot.height); plot.context.stroke();
      plot.context.fillText(`${label} ${number(value, 1)}`, Math.min(plot.width - 60, x + 3), 26);
    }
    plot.context.restore();
  };
  heatmap("sonar-demon", demonHistory.map((row) => ({...row, bins: row.bins.slice(0, 50)})), demonFrequencies.slice(0, 50), 50, demonGuides);
  spectrum("sonar-demon-spectrum", visual.demon.spectrum.slice(0, 50),
    finite(peak) && peak <= 50 ? [{x: peak / 50, text: `${number(peak, 1)} Hz`}] : [], demonFrequencies.slice(0, 50), 50, 0, demonGuides);
  const tmaSim = S.v2State.clock.sim;
  const drawTma = (wallNow) => {
    let tma = visualContext("sonar-tma-plot");
    if (!tma) return;
    const contacts = visual.tma.filter((row) => row.bearings.length);
    if (!contacts.length) drawEmpty(tma);
    // Bearings age smoothly between publications, in step with the waterfalls.
    const shift = Math.max(0, Math.min(1.5, displaySimNow(wallNow) + DISPLAY_CLOCK_LAG_S - tmaSim));
    const maxAge = Math.max(1, ...contacts.flatMap((track) => track.bearings.map((point) => point.age_s + shift)));
    tma = plotAxes(tma, maxAge, 360, " s", "°");
    contacts.forEach((track, index) => {
      const isSelected = track.ref === S.selected;
      tma.context.strokeStyle = isSelected ? palette().accent : ["#7fb8a5", palette().amber, palette().blue, palette().red][index % 4];
      tma.context.lineWidth = isSelected ? 3 : 1;
      tma.context.beginPath();
      track.bearings.forEach((point, pointIndex) => {
        const x = (point.age_s + shift) / maxAge * tma.width;
        const y = point.bearing / 360 * tma.height;
        pointIndex && Math.abs(point.bearing - track.bearings[pointIndex - 1].bearing) < 180 ? tma.context.lineTo(x, y) : tma.context.moveTo(x, y);
      });
      tma.context.stroke();
      // Operator hypothesis: predicted bearings (measured minus residual).
      if (isSelected && track.residuals_deg.length === track.bearings.length) {
        tma.context.save(); tma.context.setLineDash([5, 4]); tma.context.strokeStyle = palette().amber; tma.context.lineWidth = 2;
        tma.context.beginPath();
        track.bearings.forEach((point, pointIndex) => {
          const predicted = ((point.bearing - track.residuals_deg[pointIndex]) % 360 + 360) % 360;
          const x = (point.age_s + shift) / maxAge * tma.width, y = predicted / 360 * tma.height;
          pointIndex ? tma.context.lineTo(x, y) : tma.context.moveTo(x, y);
        });
        tma.context.stroke(); tma.context.restore();
      }
    });
    tma.context.lineWidth = 1;
    const chosen = visual.tma.find((row) => row.ref === S.selected);
    if (chosen) $("sonar-tma-readout").value = t("sonar_tma_summary", {rate: finite(chosen.summary.rate_deg_min) ? number(chosen.summary.rate_deg_min, 2) : "--", legs: chosen.summary.legs}) + " | " + (chosen.evaluation ? t("sonar_tma_evaluation", {
      rms: number(chosen.evaluation.rms_deg, 1), trend: number(chosen.evaluation.systematic_deg, 1),
      fit: number(chosen.evaluation.fit * 100, 0), observable: number(chosen.evaluation.observability * 100, 0)}) : t("sonar_tma_pending"));
  };
  registerAnimatedPlot("sonar-tma-plot", drawTma);
  drawTma(performance.now());
  let bt = visualContext("sonar-environment");
  if (bt) {
    if (!visual.bt || !visual.bt.depths_m.length) drawEmpty(bt);
    else {
      const min = Math.min(...visual.bt.speeds_m_s), max = Math.max(...visual.bt.speeds_m_s, min + 1);
      const depth = Math.max(1, ...visual.bt.depths_m);
      bt = plotAxes(bt, max - min, depth, " m/s", "m", min);
      bt.context.fillStyle = palette().muted;
      bt.context.fillText(`${number(min, 0)}–${number(max, 0)} m/s`, bt.width / 2, -7);
      if (finite(visual.bt.thermocline_m)) { const y = visual.bt.thermocline_m / depth * bt.height; bt.context.strokeStyle = palette().amber; bt.context.setLineDash([4, 4]); bt.context.beginPath(); bt.context.moveTo(0, y); bt.context.lineTo(bt.width, y); bt.context.stroke(); bt.context.setLineDash([]); }
      bt.context.strokeStyle = palette().blue; bt.context.beginPath();
      const speedX = (speed) => 12 + (speed - min) / (max - min) * (bt.width - 24);
      visual.bt.depths_m.forEach((value, index) => {
        const x = speedX(visual.bt.speeds_m_s[index]);
        const y = value / depth * bt.height;
        index ? bt.context.lineTo(x, y) : bt.context.moveTo(x, y);
      });
      bt.context.stroke();
      // Labelled reference depths: layer, seabed and the sound-speed minimum.
      bt.context.textAlign = "right";
      if (finite(visual.bt.thermocline_m)) {
        bt.context.fillStyle = palette().amber;
        bt.context.fillText(t("sonar_bt_layer", {depth: number(visual.bt.thermocline_m, 0)}),
          bt.width - 4, Math.max(12, visual.bt.thermocline_m / depth * bt.height - 4));
      }
      if (finite(visual.bt.water_depth_m) && visual.bt.water_depth_m <= depth) {
        const y = visual.bt.water_depth_m / depth * bt.height;
        bt.context.strokeStyle = palette().muted; bt.context.beginPath(); bt.context.moveTo(0, y); bt.context.lineTo(bt.width, y); bt.context.stroke();
        bt.context.fillStyle = palette().muted;
        bt.context.fillText(t("sonar_bt_bottom", {depth: number(visual.bt.water_depth_m, 0)}), bt.width - 4, Math.max(12, y - 4));
      }
      const slowest = visual.bt.speeds_m_s.indexOf(min);
      if (slowest >= 0) {
        const x = speedX(min), y = visual.bt.depths_m[slowest] / depth * bt.height;
        bt.context.fillStyle = palette().blue; bt.context.beginPath(); bt.context.arc(x, y, 3.5, 0, Math.PI * 2); bt.context.fill();
        bt.context.textAlign = x < bt.width / 2 ? "left" : "right";
        bt.context.fillText(t("sonar_bt_minimum", {speed: number(min, 0), depth: number(visual.bt.depths_m[slowest], 0)}),
          x + (x < bt.width / 2 ? 8 : -8), Math.min(bt.height - 4, Math.max(12, y + 4)));
      }
      if (finite(sonarDisplay.btCursorDepth) && sonarDisplay.btCursorDepth <= depth) {
        const y = sonarDisplay.btCursorDepth / depth * bt.height;
        bt.context.strokeStyle = palette().accent; bt.context.setLineDash([2, 3]);
        bt.context.beginPath(); bt.context.moveTo(0, y); bt.context.lineTo(bt.width, y); bt.context.stroke();
        bt.context.setLineDash([]);
        if (sonarDisplay.btCursorText) {
          bt.context.fillStyle = palette().accent; bt.context.textAlign = "left";
          bt.context.fillText(sonarDisplay.btCursorText, 4, y > 16 ? y - 4 : y + 13);
        }
      }
      bt.context.textAlign = "center";
    }
  }
  const active = visualContext("sonar-active");
  if (active) {
    const radius = Math.min(active.width, active.height) * .44, cx = active.width / 2, cy = active.height / 2;
    active.context.strokeStyle = palette().line;
    for (const scale of [.25, .5, .75, 1]) { active.context.beginPath(); active.context.arc(cx, cy, radius * scale, 0, Math.PI * 2); active.context.stroke(); }
    const maxRange = Math.max(5, Math.ceil(Math.max(0, ...visual.active_echoes.map((echo) => echo.range_nm)) / 5) * 5);
    active.context.fillStyle = palette().muted; active.context.fillText(`N · ${number(maxRange, 0)} NM`, cx, 18);
    if (visual.bt && finite(visual.bt.thermocline_m) && finite(visual.bt.water_depth_m)) {
      const duct = Math.max(.15, Math.min(.9, visual.bt.thermocline_m / Math.max(1, visual.bt.water_depth_m)));
      active.context.strokeStyle = `${palette().blue}88`;
      active.context.setLineDash([5, 5]); active.context.beginPath(); active.context.arc(cx, cy, radius * duct, 0, Math.PI * 2); active.context.stroke(); active.context.setLineDash([]);
    }
    for (const echo of visual.active_echoes) {
      const angle = echo.bearing * Math.PI / 180;
      const r = echo.range_nm / maxRange * radius;
      const strength = Math.max(.12, Math.min(1, Math.exp(-echo.age_s / 12) * (.35 + Math.max(0, echo.snr_db) / 30)));
      active.context.globalAlpha = strength; active.context.fillStyle = palette().amber; active.context.beginPath();
      active.context.arc(cx + Math.sin(angle) * r, cy - Math.cos(angle) * r, 2 + strength * 3, 0, Math.PI * 2); active.context.fill();
    }
    active.context.globalAlpha = 1;
    if (!visual.active_echoes.length) drawEmpty(active);
  }
  let aScan = visualContext("sonar-a-scan");
  if (aScan) {
    const maxRange = Math.max(5, Math.ceil(Math.max(0, ...visual.active_echoes.map((echo) => echo.range_nm)) / 5) * 5);
    aScan = plotAxes(aScan, maxRange, 1, " NM", "AMP", 0, true);
    const samples = 256;
    const trace = Array.from({length: samples}, (_, index) => .035 + .025 * (1 + Math.sin(index * 12.9898 + visual.active_echoes.length)));
    for (const echo of visual.active_echoes) {
      const center = echo.range_nm / maxRange * (samples - 1);
      const width = Math.max(1, echo.range_uncertainty_nm / maxRange * samples);
      const amplitude = Math.max(.08, Math.min(.95, .18 + echo.snr_db / 35)) * Math.exp(-echo.age_s / 12);
      for (let index = 0; index < samples; index++) trace[index] += amplitude * Math.exp(-.5 * ((index - center) / width) ** 2);
    }
    aScan.context.strokeStyle = palette().accent; aScan.context.beginPath();
    trace.forEach((value, index) => { const x = index / (samples - 1) * aScan.width; const y = aScan.height - Math.min(1, value) * (aScan.height - 8); index ? aScan.context.lineTo(x, y) : aScan.context.moveTo(x, y); });
    aScan.context.stroke();
  }
  $("sonar-broadband-text").textContent = t("sonar_broadband_equivalent", {rows: broadbandHistory.length, bins: broadbandHistory.at(-1)?.bins.length || 0});
  $("sonar-lofar-text").textContent = t("sonar_lofar_equivalent", {rows: lofarHistory.length, bins: visual.lofar.spectrum.length, held: yesNo(visual.lofar.held)});
  $("sonar-demon-text").textContent = t("sonar_demon_equivalent", {rows: demonHistory.length, bins: visual.demon.spectrum.length, hypotheses: visual.demon.analysis?.hypotheses.length || 0});
  for (const item of visual.demon.analysis?.hypotheses || []) $("sonar-demon-text").append(node("p",
    t("sonar_rpm_hypothesis", {blades: item.blades, order: item.order, rpm: number(item.rpm, 1)})));
  $("sonar-tma-text").replaceChildren(...visual.tma.map((row) => node("p", t("sonar_tma_equivalent", {ref: row.ref, points: row.bearings.length, solution: row.solution ? `${position(row.solution)} / ${unit(row.solution.course, "\u00b0", 0)} / ${unit(row.solution.speed_kn, "kn")}` : t("station_none")}))));
  if (!visual.tma.length) $("sonar-tma-text").textContent = t("visual_empty");
  $("sonar-environment-text").textContent = visual.bt ? t("sonar_environment_equivalent", {age: number(visual.bt.age_s, 0), depth: number(visual.bt.water_depth_m, 0), thermocline: number(visual.bt.thermocline_m, 0), array: visual.receiver.array}) : t("visual_empty");
  $("sonar-active-text").textContent = t("sonar_active_equivalent", {count: visual.active_echoes.length});
  for (const echo of visual.active_echoes) $("sonar-active-text").append(node("p", `${unit(echo.bearing, "°", 0)} · ${unit(echo.range_nm, "NM")} ± ${unit(echo.range_uncertainty_nm, "NM")} · ${unit(echo.depth_m, "m", 0)} · ${unit(echo.snr_db, "dB")} · ${unit(echo.age_s, "s")}`));
}
