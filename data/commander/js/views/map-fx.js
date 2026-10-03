// Moving marks on the browser charts, as src/ui/map_fx_view.py draws them on
// the uConsole: the own ping's wavefront running out at the speed of sound,
// echoes lighting up where they place their reflector, rings where own
// charges went off, the radar's afterglow behind its beam and the
// furthest-on circle round an ageing fix.  Display only: rows come from the
// plot's ``fx`` block ([age_s, x, y]) and age with the wall clock between
// publications.
import { isLightTheme } from "../core/palette.js";

const SOUND_MPS = 1500, PING_SHOW_S = 60, ECHO_SHOW_S = 4, SPLASH_SHOW_S = 20;
const FOC_MIN_AGE_S = 60, FOC_MAX_NM = 25, FOC_SPEED_KN = {SUBSURFACE: 20, SURFACE: 30};
const AFTERGLOW_DEG = 40, AFTERGLOW_STEPS = 26;
const received = new WeakMap();
// Mark colours per theme (src/ui/theme.THEMED_GLOBALS map_fx_view): bright
// on the dark chart, dark on the light one.
const FX_COLORS = {night: {ping: "110, 190, 255", echo: "255, 236, 150", splash: "255, 214, 120", foc: "240, 190, 90", glow: "70, 190, 130"},
  day: {ping: "29, 78, 216", echo: "161, 98, 7", splash: "180, 83, 9", foc: "180, 83, 9", glow: "4, 120, 87"}};
const fxColors = () => FX_COLORS[isLightTheme() ? "day" : "night"];

function since(fx) {
  const wall = performance.now();
  if (!received.has(fx)) received.set(fx, wall);
  return (wall - received.get(fx)) / 1000;
}

// True while a mark still moves (the chart animates until they are gone).
export function mapFxActive(fx) {
  if (!fx) return false;
  const extra = since(fx);
  return fx.pings.some((row) => row[0] + extra <= PING_SHOW_S) || fx.echoes.some((row) => row[0] + extra <= ECHO_SHOW_S) ||
    fx.splashes.some((row) => row[0] + extra <= SPLASH_SHOW_S);
}

export function drawMapFx(g, fx, point, scale) {
  if (!fx) return;
  const extra = since(fx), fxc = fxColors();
  g.save();
  for (const [age0, x, y] of fx.pings) {
    const age = age0 + extra;
    if (age > PING_SHOW_S) continue;
    const [cx, cy] = point(x, y), radius = age * SOUND_MPS / 1852 * scale, fade = 1 - age / PING_SHOW_S;
    if (radius < 2) continue;
    g.strokeStyle = `rgba(${fxc.ping}, ${.85 * fade})`; g.lineWidth = 2;
    g.beginPath(); g.arc(cx, cy, radius, 0, Math.PI * 2); g.stroke();
    if (radius > 8) {
      g.strokeStyle = `rgba(${fxc.ping}, ${.35 * fade})`; g.lineWidth = 1;
      g.beginPath(); g.arc(cx, cy, radius - 5, 0, Math.PI * 2); g.stroke();
    }
  }
  for (const [age0, x, y] of fx.echoes) {
    const age = age0 + extra;
    if (age > ECHO_SHOW_S) continue;
    const [cx, cy] = point(x, y), k = 1 - age / ECHO_SHOW_S;
    g.strokeStyle = g.fillStyle = `rgba(${fxc.echo}, ${k})`; g.lineWidth = 2;
    g.beginPath(); g.arc(cx, cy, 3 + 9 * (1 - k), 0, Math.PI * 2); g.stroke();
    g.beginPath(); g.arc(cx, cy, 2, 0, Math.PI * 2); g.fill();
  }
  for (const [age0, x, y] of fx.splashes) {
    const age = age0 + extra;
    if (age > SPLASH_SHOW_S) continue;
    const [cx, cy] = point(x, y), k = 1 - age / SPLASH_SHOW_S;
    g.lineWidth = 1;
    for (let ring = 0; ring < 3; ring++) {
      const radius = 3 + (age * 2 + ring * 5) % 18;
      g.strokeStyle = `rgba(${fxc.splash}, ${k * (1 - radius / 22)})`;
      g.beginPath(); g.arc(cx, cy, radius, 0, Math.PI * 2); g.stroke();
    }
  }
  g.restore();
}

// The circle a contact of ``domain`` can have reached since a fix ``ageS`` old.
export function furthestOnNm(domain, ageS) {
  const speed = FOC_SPEED_KN[domain];
  if (!speed || !(ageS >= FOC_MIN_AGE_S)) return null;
  return Math.min(FOC_MAX_NM, ageS * speed / 3600);
}

export function drawFurthestOn(g, cx, cy, radius) {
  if (!(radius >= 4)) return;
  g.save(); g.strokeStyle = `rgba(${fxColors().foc}, .7)`; g.lineWidth = 1; g.setLineDash([4, 4]);
  g.beginPath(); g.arc(cx, cy, radius, 0, Math.PI * 2); g.stroke(); g.restore();
}

// The phosphor afterglow behind a clockwise radar beam at ``bearing``.
export function drawAfterglow(g, cx, cy, radius, bearing) {
  const glow = fxColors().glow;
  g.save(); g.lineWidth = 2;
  for (let step = 1; step <= AFTERGLOW_STEPS; step++) {
    const k = 1 - step / (AFTERGLOW_STEPS + 1), angle = (bearing - AFTERGLOW_DEG * step / AFTERGLOW_STEPS) * Math.PI / 180;
    g.strokeStyle = `rgba(${glow}, ${.45 * k * k})`;
    g.beginPath(); g.moveTo(cx, cy); g.lineTo(cx + radius * Math.sin(angle), cy - radius * Math.cos(angle)); g.stroke();
  }
  g.restore();
}
