// Module worker: paints waterfall rasters into an OffscreenCanvas and hands
// the finished bitmap back, so the page's main thread (and the live-sonar
// audio scheduler on it) never runs the per-cell loop.
import { paintHeatmap } from "./heatmap-paint.js";

const MAX_SURFACES = 16;
const surfaces = new Map();

function surfaceFor(id, width, height) {
  let surface = surfaces.get(id);
  if (surface && surface.canvas.width === width && surface.canvas.height === height) return surface;
  const canvas = new OffscreenCanvas(width, height);
  const context = canvas.getContext("2d");
  const image = context.createImageData(width, height);
  surface = {canvas, context, image, pixels: new Uint32Array(image.data.buffer)};
  surfaces.delete(id);
  surfaces.set(id, surface);
  if (surfaces.size > MAX_SURFACES) surfaces.delete(surfaces.keys().next().value);
  return surface;
}

self.onmessage = ({data}) => {
  const {id, seq, job} = data;
  const surface = surfaceFor(id, job.width, job.rasterHeight);
  paintHeatmap(surface.pixels, job);
  surface.context.putImageData(surface.image, 0, 0);
  const bitmap = surface.canvas.transferToImageBitmap();
  self.postMessage({id, seq, bitmap, anchor: job.anchor}, [bitmap]);
};
