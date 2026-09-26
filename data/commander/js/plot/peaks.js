import { S } from "../state/store.js";
import { finite, number } from "../core/format.js";
import { palette } from "../core/palette.js";
import { spectrum } from "./spectrum.js";

// Same rule as sonar_view.spectrum_peaks: prominent local maxima above the
// median floor, parabola-refined, strongest first and thinned so labels
// never overlap.
const PEAK_LABEL_W = 30;
function spectrumPeaks(values, frequencies, limit, minSeparation) {
  const count = values.length;
  if (count < 3 || frequencies.length !== count || limit <= 0) return [];
  const v = Array.from(values, (value) => Number.isFinite(value) ? value : 0);
  const top = Math.max(...v);
  const sorted = [...v].sort((a, b) => a - b);
  const floor = count % 2 ? sorted[(count - 1) / 2] : (sorted[count / 2 - 1] + sorted[count / 2]) / 2;
  const span = top - floor;
  if (top < .03 || span <= 1e-6) return [];
  const threshold = Math.max(floor + .25 * span, floor * 1.6, .03);
  const candidates = [];
  for (let i = 1; i < count - 1; i++) {
    if (!(v[i] > v[i - 1] && v[i] >= v[i + 1] && v[i] >= threshold)) continue;
    const left = Math.min(...v.slice(Math.max(0, i - 4), i));
    const right = Math.min(...v.slice(i + 1, i + 5));
    if (v[i] - Math.max(left, right) < .1 * span) continue;
    const [x0, x1, x2] = [frequencies[i - 1], frequencies[i], frequencies[i + 1]];
    const [y0, y1, y2] = [v[i - 1], v[i], v[i + 1]];
    const denominator = (x0 - x1) * (x0 - x2) * (x1 - x2);
    let hz = x1;
    if (Math.abs(denominator) > 1e-12) {
      const a = (x2 * (y1 - y0) + x1 * (y0 - y2) + x0 * (y2 - y1)) / denominator;
      const b = (x2 * x2 * (y0 - y1) + x1 * x1 * (y2 - y0) + x0 * x0 * (y1 - y2)) / denominator;
      if (a < 0) hz = Math.max(x0, Math.min(x2, -b / (2 * a)));
    }
    candidates.push({hz, level: v[i], index: i});
  }
  candidates.sort((a, b) => b.level - a.level || a.index - b.index);
  const chosen = [];
  for (const peak of candidates) {
    if (chosen.every((other) => Math.abs(peak.hz - other.hz) >= minSeparation)) chosen.push(peak);
    if (chosen.length >= limit) break;
  }
  return chosen.sort((a, b) => a.hz - b.hz);
}
// Same rule as sonar_view.place_peak_labels: strongest first, above the
// apex or beside it, and a value with no free place is dropped.
function placePeakLabels(apexes, width, height, obstacles) {
  const taken = [...obstacles], placed = [];
  const collides = (box) => taken.some((other) => box.x - 2 < other.x + other.w && other.x < box.x + box.w + 2 && box.y < other.y + other.h && other.y < box.y + box.h);
  for (const apex of [...apexes].sort((a, b) => b.level - a.level || a.x - b.x)) {
    const sideTop = Math.max(1, apex.y - 6);
    const options = [[{x: apex.x - apex.w / 2, y: apex.y - 15, w: apex.w, h: 12}, true]];
    for (const top of [sideTop, sideTop + 12]) for (const x of [apex.x + 4, apex.x - 4 - apex.w]) options.push([{x, y: top, w: apex.w, h: 12}, false]);
    for (const [box, above] of options) {
      if (box.x < 0 || box.y < 0 || box.x + box.w > width || box.y + box.h > height || collides(box)) continue;
      taken.push(box); placed.push({...apex, box, above});
      break;
    }
  }
  return placed;
}
export function drawPeakLabels(plot, values, frequencies, xmin, xmax, maximum, markers) {
  // Automatic peak labels are a training aid; off, the operator reads lines
  // with the cursor (same rule as the uConsole).
  if (S.v2State?.sonar?.settings?.tools && !S.v2State.sonar.settings.tools.assist) return;
  if (plot.width < PEAK_LABEL_W || xmax <= xmin) return;
  const hz = frequencies ?? Array.from(values, (_, index) => values.length === 1 ? xmin : xmin + index / (values.length - 1) * (xmax - xmin));
  const scale = plot.width / (xmax - xmin);
  const normalised = Array.from(values, (value) => Math.max(0, value) / maximum);
  const context = plot.context;
  context.save();
  context.font = "10px ui-monospace, monospace";
  const markerBoxes = markers.slice(0, 20).map((marker) => ({x: Math.max(2, Math.min(plot.width - 50, marker.x * plot.width)), y: 3, w: context.measureText(marker.text).width, h: 13}));
  const apexes = [];
  for (const peak of spectrumPeaks(normalised, hz, 12, 0)) {
    const x = (peak.hz - xmin) * scale;
    if (x < 0 || x > plot.width || markers.some((marker) => Math.abs(marker.x * plot.width - x) < 4)) continue;
    const text = peak.hz < 100 ? number(peak.hz, 1) : number(peak.hz, 0);
    apexes.push({x, y: plot.height - peak.level * (plot.height - 12), w: context.measureText(text).width, text, level: peak.level});
  }
  context.fillStyle = palette().text;
  context.strokeStyle = palette().text;
  context.textBaseline = "top";
  for (const label of placePeakLabels(apexes, plot.width, plot.height, markerBoxes)) {
    if (label.above) { context.beginPath(); context.moveTo(label.x, label.y - 1); context.lineTo(label.x, label.y - 4); context.stroke(); }
    context.fillText(label.text, label.box.x, label.box.y);
  }
  context.restore();
}
export function drawBandLimits(plot, band, maximum = 300) {
  if (!plot || !Array.isArray(band) || band.length !== 2) return;
  plot.context.strokeStyle = palette().amber;
  for (const frequency of band) {
    const x = Math.max(0, Math.min(plot.width, frequency / maximum * plot.width));
    plot.context.beginPath(); plot.context.moveTo(x, 0);
    plot.context.lineTo(x, plot.height); plot.context.stroke();
  }
}
export function drawHarmonicGuides(plot, fundamental, maximum) {
  if (!plot || !finite(fundamental) || fundamental <= 0) return;
  plot.context.save();
  plot.context.strokeStyle = palette().amber;
  plot.context.fillStyle = palette().amber;
  plot.context.setLineDash([3, 3]);
  plot.context.font = "10px ui-monospace, monospace";
  for (let order = 1; order <= 12 && fundamental * order <= maximum; order++) {
    const hz = fundamental * order;
    const x = hz / maximum * plot.width;
    plot.context.beginPath(); plot.context.moveTo(x, 0); plot.context.lineTo(x, plot.height); plot.context.stroke();
    plot.context.fillText(`${order}f`, Math.min(plot.width - 18, x + 2), 11);
  }
  plot.context.restore();
}
export function bandSpectrum(id, visual, low, high) {
  const pairs = visual.bin_frequencies_hz.map((frequency, index) =>
    [frequency, visual.spectrum[index]]).filter(([frequency]) => frequency >= low && frequency <= high);
  spectrum(id, pairs.map((pair) => pair[1]), [], pairs.map((pair) => pair[0]), high, low);
}
