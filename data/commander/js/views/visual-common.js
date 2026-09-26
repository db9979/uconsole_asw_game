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
  plot.context.fillStyle = palette().muted;
  plot.context.textAlign = "center";
  plot.context.fillText(t(key), plot.width / 2, plot.height / 2);
}
