import { S } from "../state/store.js";
import { finite } from "../core/format.js";
import { heatmapPalette, heatmapRasters, plotAxes } from "./axes.js";
import { registerAnimatedPlot } from "./clock.js";
import { sonarDisplay } from "../state/shared.js";
import { drawEmpty, visualContext } from "../views/visual-common.js";
import { DISPLAY_CLOCK_LAG_S, displaySimNow } from "../state/display-clock.js";

// A waterfall has tens of thousands of cells. Painting each with fillRect blocked
// the browser's main thread long enough to starve the live-sonar audio scheduler,
// so the cells are written into one pixel buffer. The buffer is positioned by
// row time stamps and rebuilt only when rows or display settings change; each
// animation frame merely blits it at the display clock's offset.
export function heatmap(id, rows, frequencies = null, axisMaximum = null, overlay = null, historyS = sonarDisplay.history) {
  const now = S.v2State?.clock?.sim ?? 0;
  rows = rows.map((row) => finite(row.stamp) ? row : {...row, stamp: now - row.age_s})
    .filter((row) => row.stamp >= now - historyS - 5 && row.bins.length);
  const spec = {rows, frequencies, axisMaximum, overlay, historyS};
  const draw = (wallNow) => drawHeatmap(id, spec, wallNow);
  registerAnimatedPlot(id, draw);
  return draw(performance.now());
}
function heatmapRaster(id, spec, width, height, pixelsPerSecond, headroom) {
  const {rows, frequencies, historyS} = spec;
  let raster = heatmapRasters.get(id);
  const settings = [width, height, headroom, historyS, sonarDisplay.palette, sonarDisplay.black, sonarDisplay.contrast].join(":");
  if (raster?.rows === rows && raster.settings === settings) return raster;
  const rasterHeight = height + headroom;
  if (!raster || raster.canvas.width !== width || raster.canvas.height !== rasterHeight) {
    const off = document.createElement("canvas");
    off.width = width; off.height = rasterHeight;
    const context = off.getContext("2d");
    const image = context.createImageData(width, rasterHeight);
    raster = {canvas: off, context, image, pixels: new Uint32Array(image.data.buffer)};
    heatmapRasters.set(id, raster);
  }
  const anchor = Math.max(...rows.map((row) => row.stamp));
  Object.assign(raster, {rows, settings, anchor});
  const pixels = raster.pixels;
  const colors = heatmapPalette();
  pixels.fill(colors[0]);
  const xmax = spec.axisMaximum ?? (frequencies ? 300 : 360);
  const count = Math.max(...rows.map((row) => row.bins.length));
  const stamps = rows.map((row) => row.stamp).sort((a, b) => a - b);
  const gaps = stamps.slice(1).map((stamp, index) => stamp - stamps[index]).filter((gap) => gap > 0);
  const samplePeriod = gaps.length ? gaps.sort((a, b) => a - b)[Math.floor(gaps.length / 2)] : .25;
  const cellHeight = Math.max(1, Math.round(samplePeriod * pixelsPerSecond));
  for (const row of rows) {
    const age = anchor - row.stamp;
    const y0 = Math.floor(headroom + age * pixelsPerSecond);
    if (y0 < 0 || y0 >= rasterHeight) continue;
    const y1 = Math.min(rasterHeight, y0 + cellHeight);
    const persistence = Math.exp(-age / Math.max(8, historyS * .8));
    for (let x = 0; x < row.bins.length; x++) {
      const raw = Math.max(0, Math.min(1, row.bins[x]));
      const level = Math.max(0, Math.min(1, (raw - sonarDisplay.black) / Math.max(.01, 1 - sonarDisplay.black) * sonarDisplay.contrast * persistence));
      const start = frequencies ? frequencies[x] / xmax : x / count;
      const end = frequencies ? (frequencies[x + 1] ?? xmax) / xmax : (x + 1) / count;
      const x0 = Math.min(width - 1, Math.max(0, Math.floor(start * width)));
      const x1 = Math.min(width, Math.max(x0 + 1, Math.floor(end * width)));
      const color = colors[Math.round(level * 255)];
      for (let y = y0; y < y1; y++) pixels.fill(color, y * width + x0, y * width + x1);
    }
  }
  raster.context.putImageData(raster.image, 0, 0);
  return raster;
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
  context.fillStyle = "#030806"; context.fillRect(0, 0, area.width, area.height);
  context.imageSmoothingEnabled = false;
  context.drawImage(raster.canvas, 0, offset, area.width, (height + headroom) * scaleY);
  context.restore();
  spec.overlay?.(area);
  return area;
}
