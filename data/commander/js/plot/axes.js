import { number } from "../core/format.js";
import { palette } from "../core/palette.js";
import { sonarDisplay } from "../state/shared.js";

export function plotAxes(plot, xmax, ymax, xunit, yunit, xorigin = 0, reverseY = false) {
  const context = plot.context;
  const {left, top, width, height} = plotArea(plot.width, plot.height);
  context.fillStyle = palette().muted; context.strokeStyle = palette().line; context.textAlign = "center";
  for (let tick = 0; tick <= 4; tick++) {
    const x = left + tick * width / 4, y = top + tick * height / 4;
    context.fillText(`${number(xorigin + xmax * tick / 4, 0)}${tick === 4 ? xunit : ""}`, x, top + height + 20);
    context.textAlign = "right"; context.fillText(`${number(ymax * (reverseY ? 1 - tick / 4 : tick / 4), ymax < 2 ? 1 : 0)}`, left - 6, y + 4); context.textAlign = "center";
    context.beginPath(); context.moveTo(x, top); context.lineTo(x, top + height); context.stroke();
  }
  context.fillText(yunit, left, 14);
  context.translate(left, top);
  return {...plot, width, height};
}
export function plotArea(width, height) {
  const left = 46, top = 22;
  return {left, top, width: Math.max(1, width - left - 18),
    height: Math.max(1, height - top - 30)};
}
// One packed 0xAABBGGRR colour per quantised level, in the byte order the
// Uint32 view of ImageData uses on this platform.
const heatmapPalettes = new Map();
export function heatmapPalette() {
  if (heatmapPalettes.has(sonarDisplay.palette)) return heatmapPalettes.get(sonarDisplay.palette);
  const little = new Uint8Array(new Uint32Array([1]).buffer)[0] === 1;
  const channels = {green: [68, 255, 154], amber: [255, 184, 62], cyan: [65, 225, 255]}[sonarDisplay.palette] || [68, 255, 154];
  const lut = Uint32Array.from({length: 256}, (_, index) => {
    const level = (index / 255) ** .72;
    const r = Math.round(3 + level * channels[0]), g = Math.round(8 + level * channels[1]), b = Math.round(6 + level * channels[2]);
    return little ? ((255 << 24) | (b << 16) | (g << 8) | r) >>> 0 : ((r << 24) | (g << 16) | (b << 8) | 255) >>> 0;
  });
  heatmapPalettes.set(sonarDisplay.palette, lut);
  return lut;
}
export const heatmapRasters = new Map();
