// The sky in the browser eyepieces, the twin of src/ui/skyshade.py (the look
// of Tiefenkontakt's sky shader): gradient, dusk glow, the sun's halo, high
// cirrus, the cloud deck lit from the sun's side and the haze band at the
// horizon.  Computed in cells and smoothed up, as a background layer and a
// cloud layer with its cover as alpha; display only.

import { fbm } from "./ocean.js";

const CLOUD_UV = 1800 / 2500, CLOUD_SCALE_M = 2500, CLOUD_WRAP = 2048, CLOUD_START = [17.31, 41.77];
const WIND_ALOFT = 9, CELLS = 1800, MIN_CELL_PX = 24, RAD = Math.PI / 180;
const SUN_COLOR = [1, .957, .878], SUN_DUSK = [1, .627, .376], CIRRUS = [.92, .94, .96];
const CLOUD_BASE = [[.5, .54, .57], [.3, .33, .36]], CLOUD_TOP = [[.97, .97, .96], [.62, .66, .69]];
const MOON_GLOW = [.85, .88, .95];
export const FRACTION_PER_DEG = .7 / 45;
export const SKY_FRAME_MS = 500;

const clamp = (x, low = 0, high = 1) => Math.min(high, Math.max(low, x));
const smoothstep = (low, high, x) => { const t = clamp((x - low) / (high - low)); return t * t * (3 - 2 * t); };
const mod = (x, m) => ((x % m) + m) % m;
const lerp = (a, b, t) => a + (b - a) * t;
const unit = (bearing, alt) => [Math.sin(bearing * RAD) * Math.cos(alt * RAD), Math.cos(bearing * RAD) * Math.cos(alt * RAD), Math.sin(alt * RAD)];

// Degrees above the horizon of a height ``fraction`` of the sky; an optic
// tilted far up looks at the zenith, not past it.
export const elevation = (fraction) => clamp(fraction / FRACTION_PER_DEG, -90, 90);

// ``colors`` as sight-scene.js palette (sky [top, horizon], haze), 0..255.
export function skyParams(sky, colors, {sunEl, moonEl, visibility, ownE, ownN, t}) {
  const light = Number(sky.light), over = clamp(Number(sky.cloud));
  const rain = sky.precipitation === "rain" || sky.precipitation === "snow" ? Number(sky.intensity) : 0;
  const fog = clamp(1 - visibility / 3);
  const toward = (Number(sky.wind_from_deg) + 180) * RAD, wind = [Math.sin(toward), Math.cos(toward)];
  const drift = WIND_ALOFT * 1.5 * t;
  const off = [mod((ownE + wind[0] * drift) / CLOUD_SCALE_M + CLOUD_START[0], CLOUD_WRAP),
    mod((ownN + wind[1] * drift) / CLOUD_SCALE_M + CLOUD_START[1], CLOUD_WRAP)];
  const dusk = Number(sky.dusk), sunAlt = Number(sky.sun_alt_deg);
  const sunUp = clamp(Math.sin(sunAlt * RAD) * 6 + .2) * (1 - .95 * over) * (1 - .9 * rain) * (1 - .8 * fog);
  const moonUp = Number(sky.moon_illumination) * (1 - over) * (sky.moon_alt_deg > 0 ? 1 : 0) * Math.max(0, 1 - light * 2);
  const k = lerp(45, 14, Math.max(rain, over * .5));
  return {
    top: colors.sky[0].map((c) => c / 255), horizon: colors.sky[1].map((c) => c / 255), haze: colors.haze.map((c) => c / 255),
    lit: .05 + .95 * light * light, light, dusk, over, cover: Math.min(1, over * 1.05),
    sun: unit(Number(sky.sun_bearing), sunEl), sunUp, sunColor: SUN_COLOR.map((a, i) => lerp(a, SUN_DUSK[i], dusk)),
    moon: unit(Number(sky.moon_bearing), moonEl), moonUp, hazeK: lerp(k, 2, fog), wind, off,
  };
}

function cloudDens(p, px, py) {
  const wx = fbm(px * .5 + 3.1, py * .5 + 1.7), wy = fbm(px * .5 + 7.7, py * .5 + 4.2);
  const n = fbm(px + wx * 1.4, py + wy * 1.4), thr = lerp(.8, .12, p.cover);
  return smoothstep(thr - .05, thr + .16, n);
}

// The sky at ``bearing``/``elev`` (deg): background into back[at..at+2],
// cloud colour into cloud[at..at+2]; returns the cloud cover (0..1).
export function shade(p, bearing, elev, back, cloud, at = 0) {
  const b = bearing * RAD, e = elev * RAD, ce = Math.cos(e);
  const dx = Math.sin(b) * ce, dy = Math.cos(b) * ce, dz = Math.sin(e), h = Math.max(dz, 0), lit = p.lit;
  const [sx, sy, sz] = p.sun, s = Math.max(dx * sx + dy * sy + dz * sz, 0);
  const grade = clamp(h * 2.4) ** .55;
  const col = [0, 1, 2].map((i) => lerp(p.horizon[i], p.top[i], grade));
  const flat = Math.hypot(dx, dy) + 1e-9, sflat = Math.hypot(sx, sy) + 1e-9;
  const az = (dx * sx + dy * sy) / (flat * sflat) * .5 + .5;
  const warmT = az ** 12 * (1 - h), low7 = (1 - h) ** 7 * az ** 3 * 1.5, low3 = (1 - h) ** 3 * az ** 1.5 * .15;
  const glowK = p.dusk * (1 - .75 * p.over) * (lit + .3);
  const warm = [lerp(1, 1, warmT), lerp(.38, .7, warmT), lerp(.12, .35, warmT)], dim = [.9, .45, .3];
  const glow = [0, 1, 2].map((i) => (warm[i] * low7 + dim[i] * low3) * glowK);
  const clear = 1 - .85 * p.over, halo = (s ** 6 * .18 + s ** 60 * .35) * p.sunUp * clear;
  const [mx, my, mz] = p.moon, m = Math.max(dx * mx + dy * my + dz * mz, 0), moon = m ** 200 * .08 * p.moonUp;
  for (let i = 0; i < 3; i++) col[i] += glow[i] + p.sunColor[i] * halo + MOON_GLOW[i] * moon;
  const up = Math.max(dz, .05), [wx, wy] = p.wind;
  const cx = dx / up * .25 + p.off[0] * .37, cy = dy / up * .25 + p.off[1] * .37;
  const q1 = cx * wx + cy * wy, q2 = -cx * wy + cy * wx;
  const ci = dz > 0 ? smoothstep(.55, .85, fbm(q1 * .5, q2 * 5)) * smoothstep(.05, .4, dz) * (1 - p.cover) : 0;
  for (let i = 0; i < 3; i++) col[i] = lerp(col[i], CIRRUS[i] * lit, ci * .35);
  const lift = Math.max(dz, .02), ux = dx / lift * CLOUD_UV + p.off[0], uy = dy / lift * CLOUD_UV + p.off[1];
  const dens = cloudDens(p, ux, uy), far = smoothstep(.03, .22, dz);
  const c = dz > 0 ? clamp(p.cover * 1.25) * (1 - far) + dens * far : 0;
  const toward = dz > .03 ? cloudDens(p, ux + sx / sflat * .12, uy + sy / sflat * .12) : c;
  const over = p.over, tone = clamp(.62 + (c - toward) * 1.6 * (1 - .75 * over) - over * .35);
  const dusky = p.dusk * az * az * .8 * (1 - over), lining = s ** 14 * (1 - c) * 1.2 * p.sunUp, tint = [1.35, .85, .6];
  const hz = dz < 0 ? 1 : Math.exp(-h * p.hazeK);
  for (let i = 0; i < 3; i++) {
    const base = lerp(CLOUD_BASE[0][i], CLOUD_BASE[1][i], over), top = lerp(CLOUD_TOP[0][i], CLOUD_TOP[1][i], over);
    let cc = base + (top - base) * tone;
    cc = lerp(cc, cc * tint[i], dusky);
    cc = (cc + p.sunColor[i] * lining) * lit;
    back[at + i] = clamp(lerp(col[i], p.haze[i], hz) + glow[i] * hz * .8);
    cloud[at + i] = clamp(lerp(cc, p.haze[i], hz) + glow[i] * hz * .8);
  }
  return clamp(c);
}

export function gridSize(width, height) {
  const total = Math.min(CELLS, width * height / MIN_CELL_PX);
  const cell = Math.max(1, Math.sqrt(width * height / total));
  return [Math.max(2, Math.round(width / cell)), Math.max(2, Math.round(height / cell))];
}

// The sky of view ``w`` (sight-scene.js) as two canvases {back, deck}, kept
// per picture while nothing visible changes (at most SKY_FRAME_MS old).
const shaded = new WeakMap();
export function skyLayers(owner, w, sky, colors, options) {
  if (typeof document === "undefined") return null;
  const width = w.width, height = w.height, [columns, rows] = gridSize(width, height);
  let last = shaded.get(owner);
  if (!last) {
    last = {back: document.createElement("canvas"), deck: document.createElement("canvas"), key: ""};
    shaded.set(owner, last);
  }
  const key = [columns, rows, w.los.toFixed(2), w.skyY.toFixed(1), w.skyH.toFixed(1), w.pxPerDeg.toFixed(3),
    Math.floor(options.t * 1000 / SKY_FRAME_MS), Math.round(options.ownE / 10), Math.round(options.ownN / 10),
    options.sunEl.toFixed(1), options.moonEl.toFixed(1), options.visibility.toFixed(1),
    JSON.stringify(sky), colors.sky.join(), colors.haze.join()].join("|");
  if (key === last.key) return last;
  last.key = key;
  const p = skyParams(sky, colors, options);
  for (const canvas of [last.back, last.deck]) {
    if (canvas.width !== columns || canvas.height !== rows) { canvas.width = columns; canvas.height = rows; }
  }
  const backG = last.back.getContext("2d"), deckG = last.deck.getContext("2d");
  const backImage = backG.createImageData(columns, rows), deckImage = deckG.createImageData(columns, rows);
  const back = new Float64Array(3), cloud = new Float64Array(3);
  for (let row = 0; row < rows; row++) {
    const y = (row + .5) * height / rows, el = elevation((w.skyY - y) / w.skyH);
    for (let column = 0; column < columns; column++) {
      const x = (column + .5) * width / columns;
      const cover = shade(p, w.los + (x - width / 2) / w.pxPerDeg, el, back, cloud);
      const at = (row * columns + column) * 4;
      for (let i = 0; i < 3; i++) {
        backImage.data[at + i] = Math.round(back[i] * 255);
        deckImage.data[at + i] = Math.round(cloud[i] * 255);
      }
      backImage.data[at + 3] = 255;
      deckImage.data[at + 3] = Math.round(cover * 255);
    }
  }
  backG.putImageData(backImage, 0, 0);
  deckG.putImageData(deckImage, 0, 0);
  return last;
}
