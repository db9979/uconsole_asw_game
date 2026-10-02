// The hit picture (src/core/hit_view.py, src/ui/hit_inset.py): a small
// window over the station for a few seconds. In sight it is the side's own
// eyepiece trained on the hit; only heard, the bearing with the noise.
import { S } from "../state/store.js";
import { t } from "../core/format.js";
import { drawSightView } from "./sight-scene.js";

const SONAR_SPAN_DEG = 60, SONAR_ROWS = 28, BACK = [6, 18, 26], TRACE = [110, 232, 200];
let panel = null, frame = 0, shownAt = 0, received = null;

function ensurePanel() {
  if (panel) return panel;
  panel = document.createElement("figure");
  panel.id = "hit-view";
  panel.hidden = true;
  panel.setAttribute("aria-live", "polite");
  const caption = document.createElement("figcaption");
  const canvas = document.createElement("canvas");
  canvas.width = 320; canvas.height = 170;
  canvas.setAttribute("aria-hidden", "true");
  panel.append(caption, canvas);
  document.body.append(panel);
  return panel;
}

const noise = (i, k) => { const value = Math.sin(i * 12.9898 + k * 78.233) * 43758.5453; return value - Math.floor(value); };

function drawSonar(g, width, height, bearing, ageS) {
  g.fillStyle = `rgb(${BACK.join(",")})`; g.fillRect(0, 0, width, height);
  const rowH = Math.max(1, Math.floor(height / SONAR_ROWS)), step = Math.floor(ageS * 6);
  for (let r = 0; r < SONAR_ROWS; r += 1) {
    const k = step - r;
    if (k < 0) continue;
    const fade = 1 - .6 * r / SONAR_ROWS, centre = width / 2 + (noise(7, k) - .5) * 6;
    for (let c = 0; c < width; c += 4) {
      let level = .18 * noise(c, k);
      const distance = Math.abs(c - centre) / (width / SONAR_SPAN_DEG);
      if (distance < 3) level += (.9 - .25 * distance) * (.6 + .4 * noise(c + 3, k));
      const shade = Math.max(0, Math.min(1, level * fade));
      if (shade <= .08) continue;
      g.fillStyle = `rgb(${BACK.map((value, index) => Math.round(value + (TRACE[index] - value) * shade)).join(",")})`;
      g.fillRect(c, r * rowH, 4, rowH);
    }
  }
  g.fillStyle = "rgb(120, 180, 170)"; g.font = "11px ui-monospace, monospace"; g.textAlign = "center";
  for (const off of [-20, 0, 20]) {
    const x = width / 2 + off * width / SONAR_SPAN_DEG;
    g.fillText(String(Math.round(((bearing + off) % 360 + 360) % 360)).padStart(3, "0"), x, height - 6);
  }
}

function caption(view) {
  const bearing = String(Math.round(view.bearing) % 360).padStart(3, "0");
  return t(view.mode === "sight" ? "hitview_sight" : view.kind === "breakup" ? "hitview_heard_breakup" : "hitview_heard_hit", {bearing});
}

function draw(now) {
  frame = 0;
  const view = received;
  if (!panel || !view) return;
  const canvas = panel.querySelector("canvas"), g = canvas.getContext("2d");
  const ageS = view.age_s + (now - shownAt) / 1000;
  if (view.mode === "sight") {
    drawSightView(g, canvas.width, canvas.height, {...view, bearing: view.bearing, horizon_offset: 0, horizon_tilt: 0},
      now / 1000);
  } else drawSonar(g, canvas.width, canvas.height, view.bearing, ageS);
  frame = requestAnimationFrame(draw);
}

export function syncHitView(state) {
  const view = state?.hit_view ?? null;
  const box = ensurePanel();
  if (!view) {
    received = null;
    box.hidden = true;
    if (frame) cancelAnimationFrame(frame);
    frame = 0;
    return;
  }
  received = view;
  shownAt = performance.now();
  const text = caption(view);
  const label = box.querySelector("figcaption");
  if (label.textContent !== text) label.textContent = text;
  box.hidden = false;
  if (!frame) frame = requestAnimationFrame(draw);
}
