import { S } from "../state/store.js";
import { finite } from "../core/format.js";
import { heatmapPalette, heatmapRasters, plotAxes } from "./axes.js";
import { registerAnimatedPlot } from "./clock.js";
import { sonarDisplay } from "../state/shared.js";
import { drawEmpty, visualContext } from "../views/visual-common.js";
import { DISPLAY_CLOCK_LAG_S, displaySimNow } from "../state/display-clock.js";
import { paintHeatmap } from "./heatmap-paint.js";
import { heatmapWorker } from "./heatmap-worker-client.js";

// A waterfall has tens of thousands of cells. Painting each with fillRect blocked
// the browser's main thread long enough to starve the live-sonar audio scheduler,
// so the cells are written into one pixel buffer. The buffer is positioned by
// row time stamps and rebuilt only when rows or display settings change; each
// animation frame merely blits it at the display clock's offset. Where the
// browser has OffscreenCanvas in workers the rebuild runs in a worker too.
export function heatmap(id, rows, frequencies = null, axisMaximum = null, overlay = null, historyS = sonarDisplay.history) {
  const now = S.v2State?.clock?.sim ?? 0;
  rows = rows.map((row) => finite(row.stamp) ? row : {...row, stamp: now - row.age_s})
    .filter((row) => row.stamp >= now - historyS - 5 && row.bins.length);
  const spec = {rows, frequencies, axisMaximum, overlay, historyS};
  const draw = (wallNow) => drawHeatmap(id, spec, wallNow);
  registerAnimatedPlot(id, draw);
  return draw(performance.now());
}
// The rows packed into typed arrays: the one input of paintHeatmap, which a
// worker takes by transfer instead of a structured clone of every row object.
function heatmapJob(spec, width, height, pixelsPerSecond, headroom) {
  const {rows, frequencies, historyS} = spec;
  const stamps = new Float64Array(rows.length), offsets = new Uint32Array(rows.length + 1);
  let total = 0, count = 0, anchor = -Infinity;
  rows.forEach((row, index) => {
    stamps[index] = row.stamp;
    anchor = Math.max(anchor, row.stamp);
    count = Math.max(count, row.bins.length);
    offsets[index] = total;
    total += row.bins.length;
  });
  offsets[rows.length] = total;
  const bins = new Float32Array(total);
  rows.forEach((row, index) => bins.set(row.bins, offsets[index]));
  const sorted = Array.from(stamps).sort((a, b) => a - b);
  const gaps = sorted.slice(1).map((stamp, index) => stamp - sorted[index]).filter((gap) => gap > 0);
  const samplePeriod = gaps.length ? gaps.sort((a, b) => a - b)[Math.floor(gaps.length / 2)] : .25;
  return {width, rasterHeight: height + headroom, headroom, pixelsPerSecond, historyS,
    xmax: spec.axisMaximum ?? (frequencies ? 300 : 360), count,
    black: sonarDisplay.black, contrast: sonarDisplay.contrast, colors: heatmapPalette(), anchor,
    cellHeight: Math.max(1, Math.round(samplePeriod * pixelsPerSecond)),
    stamps, offsets, bins, frequencies: frequencies ? Float64Array.from(frequencies) : null};
}
function heatmapRaster(id, spec, width, height, pixelsPerSecond, headroom) {
  let raster = heatmapRasters.get(id);
  const settings = [width, height, headroom, spec.historyS, sonarDisplay.palette, sonarDisplay.black, sonarDisplay.contrast,
    document.documentElement.dataset.theme].join(":");
  if (raster?.rows === spec.rows && raster.settings === settings) return raster;
  const job = heatmapJob(spec, width, height, pixelsPerSecond, headroom);
  const worker = heatmapWorker();
  if (worker) {
    // Until the worker answers, the previous bitmap keeps scrolling by its
    // own anchor; the first one simply shows the empty plot background.
    if (!raster || raster.context) raster = {canvas: null, anchor: job.anchor};
    Object.assign(raster, {rows: spec.rows, settings});
    heatmapRasters.set(id, raster);
    worker.render(id, job, (bitmap, anchor) => {
      if (heatmapRasters.get(id) !== raster) { bitmap.close?.(); return; }
      raster.canvas?.close?.();
      Object.assign(raster, {canvas: bitmap, anchor});
    });
    return raster;
  }
  if (!raster?.context || raster.canvas.width !== width || raster.canvas.height !== job.rasterHeight) {
    const off = document.createElement("canvas");
    off.width = width; off.height = job.rasterHeight;
    const context = off.getContext("2d");
    const image = context.createImageData(width, job.rasterHeight);
    raster = {canvas: off, context, image, pixels: new Uint32Array(image.data.buffer)};
    heatmapRasters.set(id, raster);
  }
  Object.assign(raster, {rows: spec.rows, settings, anchor: job.anchor});
  paintHeatmap(raster.pixels, job);
  raster.context.putImageData(raster.image, 0, 0);
  return raster;
}
// The empty paper of the waterfall: the ramp's lowest level as CSS colour.
function paperColor(lut) {
  const value = lut[0], little = new Uint8Array(new Uint32Array([1]).buffer)[0] === 1;
  const [r, g, b] = little ? [value & 255, (value >>> 8) & 255, (value >>> 16) & 255] : [value >>> 24, (value >>> 16) & 255, (value >>> 8) & 255];
  return `rgb(${r}, ${g}, ${b})`;
}
function drawHeatmap(id, spec, wallNow) {
  const plot = visualContext(id);
  if (!plot) return null;
  if (!spec.rows.length) { drawEmpty(plot); return null; }
  const xmax = spec.axisMaximum ?? (spec.frequencies ? 300 : 360);
  // A fixed time axis: rows scroll down through it rather than the axis
  // rescaling while the history fills.
  const area = plotAxes(plot, xmax, spec.historyS, spec.frequencies ? " Hz" : "°", "s");
  const width = Math.max(1, Math.round(area.width)), height = Math.max(1, Math.round(area.height));
  const pixelsPerSecond = height / spec.historyS;
  const headroom = Math.min(height, Math.ceil((DISPLAY_CLOCK_LAG_S + 1.5) * pixelsPerSecond) + 2);
  const raster = heatmapRaster(id, spec, width, height, pixelsPerSecond, headroom);
  const dpr = area.context.getTransform().a || 1;
  const scaleY = area.height / height;
  const offset = Math.round(((displaySimNow(wallNow) - raster.anchor) * pixelsPerSecond - headroom) * scaleY * dpr) / dpr;
  const context = area.context;
  context.save();
  context.beginPath(); context.rect(0, 0, area.width, area.height); context.clip();
  context.fillStyle = paperColor(heatmapPalette()); context.fillRect(0, 0, area.width, area.height);
  context.imageSmoothingEnabled = false;
  if (raster.canvas) context.drawImage(raster.canvas, 0, offset, area.width, (height + headroom) * scaleY);
  context.restore();
  spec.overlay?.(area);
  return area;
}
