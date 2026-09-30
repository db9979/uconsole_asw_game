import { $ } from "../core/base.js";
import { t } from "../core/format.js";
import { palette } from "../core/palette.js";
import { releaseCanvas, resizeCanvas } from "./chart.js";

export function visualContext(id) {
  const element = $(id);
  if (element.closest("[hidden]")) { releaseCanvas(element); return null; }
  const width = element.clientWidth;
  const height = element.clientHeight;
  if (!width || !height) return null;
  const context = element.getContext("2d");
  resizeCanvas(element, context, width, height);
  context.fillStyle = palette().scopeBg;
  context.fillRect(0, 0, width, height);
  context.font = `${Math.max(11, parseFloat(getComputedStyle(document.documentElement).fontSize) * .68)}px "JetBrains Mono", ui-monospace, monospace`;
  context.lineWidth = 1.5;
  return {element, context, width, height};
}
export function drawEmpty(plot, key = "visual_empty") {
  // A resting scope: faint graticule, so an empty panel still reads as an instrument.
  const g = plot.context, colors = palette();
  g.save(); g.strokeStyle = colors.line; g.globalAlpha = .55; g.lineWidth = 1;
  for (let i = 1; i < 6; i++) {
    const x = Math.round(plot.width * i / 6) + .5, y = Math.round(plot.height * i / 6) + .5;
    g.beginPath(); g.moveTo(x, 0); g.lineTo(x, plot.height); g.moveTo(0, y); g.lineTo(plot.width, y); g.stroke();
  }
  g.restore();
  plot.context.fillStyle = palette().muted;
  plot.context.textAlign = "center";
  plot.context.fillText(t(key), plot.width / 2, plot.height / 2);
}
