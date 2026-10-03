import { number } from "../core/format.js";
import { palette, themeName } from "../core/palette.js";
import { sonarDisplay } from "../state/shared.js";

export function plotAxes(plot, xmax, ymax, xunit, yunit, xorigin = 0, reverseY = false) {
  const context = plot.context;
  const {left, top, width, height} = plotArea(plot.width, plot.height);
  context.fillStyle = palette().muted; context.strokeStyle = palette().line; context.textAlign = "center";
  for (let tick = 0; tick <= 4; tick++) {
    const x = left + tick * width / 4, y = top + tick * height / 4;
    context.fillText(`${number(xorigin + xmax * tick / 4, 0)}${tick === 4 ? xunit : ""}`, x, top + height + 20);
    // A short plot labels only its ends and middle, so the values never overlap.
    if (height >= 64 || tick % 2 === 0) {
      context.textAlign = "right";
      context.fillText(`${number(ymax * (reverseY ? 1 - tick / 4 : tick / 4), ymax < .5 ? 2 : ymax < 2 ? 1 : 0)}`, left - 6, y + 4);
      context.textAlign = "center";
    }
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
// Uint32 view of ImageData uses on this platform. The ramp follows the theme
// (src/ui/theme.PHOSPHOR_PALETTES): a dark scope to a bright trace at night
// and in high contrast, paper to dark ink by day like a LOFARgram recorder.
const heatmapPalettes = new Map();
const HEATMAP_RAMPS = {
  night: {paper: [3, 8, 6], ink: {green: [71, 263, 160], amber: [258, 192, 68], cyan: [68, 233, 261]}},
  contrast: {paper: [0, 0, 0], ink: {green: [68, 255, 154], amber: [255, 184, 62], cyan: [86, 180, 233]}},
  day: {paper: [244, 247, 246], ink: {green: [4, 78, 58], amber: [124, 54, 8], cyan: [14, 88, 110]}},
};
export function heatmapPalette() {
  const theme = themeName(), key = `${theme}:${sonarDisplay.palette}`;
  if (heatmapPalettes.has(key)) return heatmapPalettes.get(key);
  const little = new Uint8Array(new Uint32Array([1]).buffer)[0] === 1;
  const ramp = HEATMAP_RAMPS[theme] || HEATMAP_RAMPS.night;
  const ink = ramp.ink[sonarDisplay.palette] || ramp.ink.green;
  const lut = Uint32Array.from({length: 256}, (_, index) => {
    const level = (index / 255) ** .72;
    const [r, g, b] = ramp.paper.map((paper, channel) => Math.max(0, Math.min(255, Math.round(paper + level * (ink[channel] - paper)))));
    return little ? ((255 << 24) | (b << 16) | (g << 8) | r) >>> 0 : ((r << 24) | (g << 16) | (b << 8) | 255) >>> 0;
  });
  heatmapPalettes.set(key, lut);
  return lut;
}
export const heatmapRasters = new Map();
