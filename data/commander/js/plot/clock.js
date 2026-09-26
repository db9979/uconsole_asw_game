import { S } from "../state/store.js";
import { $, isSonar } from "../core/base.js";

// Plots redrawn on every animation frame between publications, by canvas id.
// A frame only blits cached rasters and strokes a few hundred points.
export const animatedPlots = new Map();
let plotFrame = null;
let plotLastDraw = 0;
export function registerAnimatedPlot(id, draw) {
  animatedPlots.set(id, {role: S.v2State?.role, draw});
}
function plotAnimation(now) {
  plotFrame = null;
  if (now - plotLastDraw >= 30) {
    plotLastDraw = now;
    for (const [id, plot] of animatedPlots) {
      const element = $(id);
      if (plot.role !== S.v2State?.role || !element || element.closest("[hidden]")) continue;
      plot.draw(now);
    }
  }
  syncPlotAnimation();
}
export function syncPlotAnimation() {
  const role = S.v2State?.role;
  const active = !document.hidden && S.connected && S.v2State?.phase === "live" && (isSonar(role) || role === "helicopter") &&
    !$("role-visuals").hidden && [...animatedPlots.values()].some((plot) => plot.role === role);
  if (active && plotFrame === null) plotFrame = requestAnimationFrame(plotAnimation);
  if (!active && plotFrame !== null) { cancelAnimationFrame(plotFrame); plotFrame = null; }
}
