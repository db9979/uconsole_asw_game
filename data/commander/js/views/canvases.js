import { S } from "../state/store.js";
import { $ } from "../core/base.js";
import { sonarScopeNames } from "../state/shared.js";

// Canvases that exist once in the page markup.
export const canvas = $("chart");
export const ctx = canvas.getContext("2d");
export const lookoutCanvas = $("lookout");
export const lookoutCtx = lookoutCanvas.getContext("2d");
export const simlogMapCanvas = $("simlog-map");
export const simlogMapCtx = simlogMapCanvas.getContext("2d");
export const roleMapSweepCanvas = $("role-map-sweep");
export const roleMapSweepCtx = roleMapSweepCanvas.getContext("2d");
// A sonar plot opened as its own window (``?scope=lofar``) shows only that plot.
const detachedSonarScope = new URLSearchParams(location.search).get("scope");

export function init() {
  if (sonarScopeNames.has(detachedSonarScope)) {
    document.body.dataset.sonarScope = detachedSonarScope;
    S.sonarVisualPage = detachedSonarScope;
  }
}
