import { palette } from "../core/palette.js";
import { plotAxes } from "./axes.js";
import { registerAnimatedPlot } from "./clock.js";
import { drawPeakLabels } from "./peaks.js";
import { drawEmpty, visualContext } from "../views/visual-common.js";

// Spectra ease towards each publication instead of jumping to it.
const SPECTRUM_SMOOTHING_S = .15;
export const spectrumStates = new Map();
export function spectrum(id, values, markers = [], frequencies = null, xmax = 80, xmin = 0, overlay = null) {
  const spec = {values, markers, frequencies, xmax, xmin, overlay};
  const draw = (wallNow) => drawSpectrum(id, spec, wallNow);
  registerAnimatedPlot(id, draw);
  return draw(performance.now());
}
function easedSpectrum(id, values, wallNow) {
  const maximum = Math.max(1e-6, ...values.map((value) => Math.abs(value)));
  let state = spectrumStates.get(id);
  if (!state || state.values.length !== values.length) {
    state = {values: Float64Array.from(values), maximum, wall: wallNow};
    spectrumStates.set(id, state);
    return state;
  }
  const alpha = 1 - Math.exp(-Math.max(0, wallNow - state.wall) / 1000 / SPECTRUM_SMOOTHING_S);
  for (let index = 0; index < values.length; index++) state.values[index] += (values[index] - state.values[index]) * alpha;
  state.maximum += (maximum - state.maximum) * alpha;
  state.wall = wallNow;
  return state;
}
function drawSpectrum(id, spec, wallNow) {
  const {markers, frequencies, xmax, xmin} = spec;
  let plot = visualContext(id);
  if (!plot) return;
  if (!spec.values.length) { spectrumStates.delete(id); drawEmpty(plot); return; }
  const eased = easedSpectrum(id, spec.values, wallNow);
  const values = eased.values;
  let maximum = eased.maximum;
  for (const value of values) maximum = Math.max(maximum, Math.abs(value));
  plot = plotAxes(plot, xmax - xmin, maximum, " Hz", "rel.", xmin, true);
  plot.context.strokeStyle = palette().accent;
  plot.context.beginPath();
  values.forEach((value, index) => {
    const x = frequencies ? (frequencies[index] - xmin) / (xmax - xmin) * plot.width : values.length === 1 ? 0 : index / (values.length - 1) * plot.width;
    const y = plot.height - Math.max(0, value) / maximum * (plot.height - 12);
    index ? plot.context.lineTo(x, y) : plot.context.moveTo(x, y);
  });
  plot.context.stroke();
  drawPeakLabels(plot, values, frequencies, xmin, xmax, maximum, markers);
  plot.context.fillStyle = palette().amber;
  for (const marker of markers.slice(0, 20)) plot.context.fillText(marker.text, Math.max(2, Math.min(plot.width - 50, marker.x * plot.width)), 14);
  spec.overlay?.(plot);
  return plot;
}
