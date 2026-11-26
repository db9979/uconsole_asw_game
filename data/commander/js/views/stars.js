// The night sky in the browser eyepieces, the twin of src/ui/stars.py (the
// stars of Tiefenkontakt's sea3d/astro.ts and stars.ts): the Yale bright
// stars in their real places for the sector's latitude, the day of the year
// and the ship's clock, a seeded scatter of faint ones for the optics, and
// the Milky Way (added to the shaded sky by sky.js).  The stars keep their
// true angles: tilting the optics up shows the constellations as they stand.
// Display only.

import { fbm, noise } from "./ocean.js";
import { STAR_COUNT, STARS_B64 } from "./star-catalog.js";

const RAD = Math.PI / 180, EPS = 23.44 * RAD, GOLDEN = 0.6180339887498949;
export const DEFAULT_DAY_OF_YEAR = 80;
const FAINT_COUNT = 24000, FAINT_SEED = 7;
const STAR_WHITE = [.92, .94, 1], REDDENED = [1, .78, .55];
export const MILKY_COLOR = [.72, .78, .92];
const POINT_PX = 1.2;   // stars.py POINT_PX

const clamp = (x, low = 0, high = 1) => Math.min(high, Math.max(low, x));
const smoothstep = (low, high, x) => { const t = clamp((x - low) / (high - low)); return t * t * (3 - 2 * t); };
const mod = (x, m) => ((x % m) + m) % m;
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];

export const equVec = (ra, dec) => [Math.cos(dec * RAD) * Math.cos(ra * RAD), Math.cos(dec * RAD) * Math.sin(ra * RAD), Math.sin(dec * RAD)];
const GAL_POLE = equVec(192.8595, 27.1283), GAL_CENTRE = equVec(266.405, -28.936);

export function sunRa(doy) {
  const lam = (360 / 365 * (doy + 10) - 90) * RAD;
  return mod(Math.atan2(Math.cos(EPS) * Math.sin(lam), Math.cos(lam)) / RAD, 360);
}
export const siderealDeg = (doy, hour) => mod(sunRa(doy) + 15 * (hour - 12), 360);

// Rows: east, north, up of an equatorial unit vector.
export function rotation(lat, lst) {
  const cl = Math.cos(lst * RAD), sl = Math.sin(lst * RAD), cp = Math.cos(lat * RAD), sp = Math.sin(lat * RAD);
  const u0 = [cl, sl, 0], u1 = [-sl, cl, 0], u2 = [0, 0, 1];
  return [u1, u0.map((v, i) => -sp * v + cp * u2[i]), u0.map((v, i) => cp * v + sp * u2[i])];
}
const apply = (rot, v) => rot.map((row) => dot(row, v));

let catalogCache = null;
export function catalog() {
  if (catalogCache) return catalogCache;
  const bin = atob(STARS_B64), pos = new Float64Array(STAR_COUNT * 3), mag = new Float64Array(STAR_COUNT), bv = new Float64Array(STAR_COUNT);
  const u8 = (i) => bin.charCodeAt(i);
  for (let i = 0; i < STAR_COUNT; i++) {
    const o = i * 6;
    pos.set(equVec((u8(o) + u8(o + 1) * 256) / 65535 * 360, (u8(o + 2) + u8(o + 3) * 256) / 65535 * 180 - 90), i * 3);
    mag[i] = u8(o + 4) / 40 - 1.5;
    bv[i] = u8(o + 5) / 80 - .4;
  }
  catalogCache = {pos, mag, bv};
  return catalogCache;
}

let faintCache = null;
export function faint() {
  if (faintCache) return faintCache;
  let s = FAINT_SEED >>> 0;
  const rnd = () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  const pos = new Float64Array(FAINT_COUNT * 3), mag = new Float64Array(FAINT_COUNT), bv = new Float64Array(FAINT_COUNT);
  const lo = 10 ** (.47 * 4.6), hi = 10 ** (.47 * 8);
  for (let i = 0; i < FAINT_COUNT;) {
    const z = rnd() * 2 - 1, a = rnd() * Math.PI * 2, r = Math.sqrt(1 - z * z);
    const v = [r * Math.cos(a), r * Math.sin(a), z], b = dot(v, GAL_POLE);
    if (rnd() > .3 + .7 * Math.exp(-(b * b) / .06)) continue;
    pos.set(v, i * 3);
    mag[i] = Math.log10(lo + rnd() * (hi - lo)) / .47;
    const product = rnd() * rnd();
    bv[i] = -.1 + 1.5 * product + .3 * rnd();
    i++;
  }
  faintCache = {pos, mag, bv};
  return faintCache;
}

export function limitingMag(sunEl, light) {
  const bySun = -1 + Math.max(0, -sunEl - 3) * .45, byLight = 5 - Math.max(0, light - .13) * 30;
  return Math.max(-2, Math.min(5, bySun, byLight));
}

const unit = (bearing, alt) => [Math.sin(bearing * RAD) * Math.cos(alt * RAD), Math.cos(bearing * RAD) * Math.cos(alt * RAD), Math.sin(alt * RAD)];

// As stars.conditions: ``hazeK`` from sky.js hazeK.
export function conditions(sky, {fov, visibility, hazeK}) {
  const light = Number(sky.light), over = clamp(Number(sky.cloud));
  const precip = sky.precipitation === "rain" || sky.precipitation === "snow" ? Number(sky.intensity) : 0;
  const fog = clamp(1 - visibility / 3);
  const lat = Number(sky.latitude ?? 55), doy = Number(sky.day_of_year ?? DEFAULT_DAY_OF_YEAR), hour = Number(sky.hour ?? 0);
  const rot = rotation(lat, siderealDeg(doy, hour));
  const moonAlt = Number(sky.moon_alt_deg);
  const moon = clamp(Math.sin(moonAlt * RAD) * 4) * (1 - over) * clamp(Number(sky.moon_illumination));
  const gainMag = Math.max(1, 55 / Math.max(1, fov));
  const lim = limitingMag(Number(sky.sun_alt_deg), light) + 2.5 * Math.log10(gainMag);
  const clear = (1 - precip) * (1 - Math.min(1, fog * 1.5)) * (1 - smoothstep(.8, .97, over));
  const show = clear > .01 && lim > -1.6;
  return {lat, doy, hour, rot, lim, gain: clear * Math.min(1.6, gainMag ** .25), px: POINT_PX * (1 + .12 * Math.log2(gainMag)),
    ext: .25 + .3 * Math.min(1, precip + fog + over * .3), hazeK: hazeK * 1.4,
    moon: unit(Number(sky.moon_bearing), moonAlt), moonK: moon, show, faint: show && lim - .4 * moon > 4.5,
    milky: show ? clear * smoothstep(3.8, 4.8, lim) * (1 - .6 * moon) : 0,
    galPole: apply(rot, GAL_POLE), galCentre: apply(rot, GAL_CENTRE)};
}

let local = {key: "", value: null};
function localStars(c, withFaint) {
  const key = [c.lat, c.doy, c.hour, withFaint].join("|");
  if (local.key === key) return local.value;
  const sets = withFaint ? [catalog(), faint()] : [catalog()];
  const n = sets.reduce((sum, set) => sum + set.mag.length, 0);
  const d = new Float64Array(n * 3), mag = new Float64Array(n), bv = new Float64Array(n);
  const bearing = new Float64Array(n), elev = new Float64Array(n), phase = new Float64Array(n);
  let i = 0;
  for (const set of sets) {
    for (let k = 0; k < set.mag.length; k++, i++) {
      const p = [set.pos[k * 3], set.pos[k * 3 + 1], set.pos[k * 3 + 2]], v = apply(c.rot, p);
      d.set(v, i * 3);
      mag[i] = set.mag[k];
      bv[i] = set.bv[k];
      bearing[i] = mod(Math.atan2(v[0], v[1]) / RAD, 360);
      elev[i] = Math.asin(clamp(v[2], -1, 1)) / RAD;
      phase[i] = (i * GOLDEN % 1) * Math.PI * 2;
    }
  }
  local = {key, value: {d, mag, bv, bearing, elev, phase}};
  return local.value;
}

function bvColour(bv) {
  const s1 = smoothstep(-.3, .1, bv), s2 = smoothstep(.1, .65, bv), s3 = smoothstep(.65, 1.6, bv);
  return [[.66, .9, 1, 1], [.76, .93, .95, .8], [1, 1, .86, .6]].map(([a, b, c2, d2]) => {
    let c = a + (b - a) * s1;
    c += (c2 - c) * s2;
    return c + (d2 - c) * s3;
  });
}

// The stars in a picture along ``los`` with ``fov`` across, up to ``topDeg``:
// {bearing, elev, alpha, rgb (flat, 3 a star), sigma} as stars.points.
export function points(c, los, fov, topDeg, t) {
  const out = {bearing: [], elev: [], alpha: [], rgb: [], sigma: []};
  if (!c.show) return out;
  const star = localStars(c, c.faint), tt = t % 1000;
  for (let i = 0; i < star.mag.length; i++) {
    const off = mod(star.bearing[i] - los + 180, 360) - 180, el = star.elev[i];
    if (!(Math.abs(off) <= fov / 2 + .5 && el > 0 && el <= topDeg)) continue;
    const dx = star.d[i * 3], dy = star.d[i * 3 + 1], dz = star.d[i * 3 + 2], s = Math.max(dz, 0);
    const airmass = 1 / (s + .025 * Math.exp(-11 * s)), m = star.mag[i] + c.ext * (airmass - 1);
    const toward = Math.max(dx * c.moon[0] + dy * c.moon[1] + dz * c.moon[2], 0);
    const lim = c.lim - c.moonK * (.4 + 3 * toward ** 12);
    if (!(m <= lim + .3)) continue;
    const ph = star.phase[i], amp = .08 + .55 * (1 - s) ** 5;
    const twinkle = 1 + amp * (.6 * Math.sin(tt * 7.3 + ph) + .4 * Math.sin(tt * 17.9 + ph * 3.7));
    const p = 10 ** (-.12 * (m - 1)) * twinkle, hz = Math.exp(-s * c.hazeK);
    const vis = smoothstep(lim + .3, lim - .5, m) * (1 - hz) * smoothstep(0, .035, dz) * c.gain;
    const alpha = clamp(p * 1.25) * vis;
    if (!(alpha >= .004)) continue;
    const k = clamp(.35 + .35 * p, 0, .85), col = bvColour(star.bv[i]), red = clamp((airmass - 1) / 12);
    for (let j = 0; j < 3; j++) out.rgb.push((STAR_WHITE[j] + (col[j] - STAR_WHITE[j]) * k) * (1 + (REDDENED[j] - 1) * red));
    out.bearing.push(star.bearing[i]);
    out.elev.push(el);
    out.alpha.push(alpha);
    out.sigma.push(c.px * (.62 + .3 * clamp(p, 0, 2.6)));
  }
  return out;
}

function mwClouds(lon, b) {
  const gx = lon * 16, gy = b * 16;
  const clump = smoothstep(.25, .75, fbm(gx + 17, gy + 3)), lane = smoothstep(.45, .7, fbm(gx * 1.7 + 5, gy * 1.7 + 11));
  return (.35 + 1.1 * clump) * (1 - .5 * lane) * (.85 + .3 * noise(gx * 8.75, gy * 8.75));
}

// Brightness of the Milky Way at a true direction (deg), as stars.milky_way.
export function milkyWay(c, bearing, elev) {
  if (c.milky <= .002) return 0;
  const ce = Math.cos(elev * RAD), d = [Math.sin(bearing * RAD) * ce, Math.cos(bearing * RAD) * ce, Math.sin(elev * RAD)];
  if (!(d[2] > 0)) return 0;
  const pole = c.galPole, centre = c.galCentre, b = dot(d, pole);
  const pl = d.map((v, i) => v - b * pole[i]), shifted = pl.map((v) => v + 1e-5);
  const l = dot(shifted, centre) / Math.hypot(...shifted), toC = .5 + .5 * l, w = .09 + .09 * toC * toC;
  if (!(Math.abs(b) < 2 * w)) return 0;
  const band = Math.exp(-b * b / (w * w));
  const cross = [pole[1] * centre[2] - pole[2] * centre[1], pole[2] * centre[0] - pole[0] * centre[2], pole[0] * centre[1] - pole[1] * centre[0]];
  const lon = Math.atan2(dot(pl, cross), dot(pl, centre));
  let cl = mwClouds(lon, b);
  if (Math.abs(lon) > 2.7) cl += (mwClouds(lon - Math.sign(lon) * 6.2832, b) - cl) * .5 * smoothstep(2.7, 3.1416, Math.abs(lon));
  const rift = 1 - .6 * Math.exp(-(((b - .015) / .025) ** 2)) * smoothstep(-.3, .7, l);
  const mw = (.35 + .65 * toC * toC) * band * cl * rift;
  return mw * c.milky * .022 * smoothstep(0, .25, d[2]) * (1 - Math.exp(-d[2] * c.hazeK / 1.4));
}

const toLinear = (c) => c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4;
const toSrgb = (c) => { c = clamp(c); return c <= .0031308 ? c * 12.92 : 1.055 * c ** (1 / 2.4) - .055; };

// The sky colour back[at..at+2] (sRGB 0..1) with the Milky Way added as light.
export function addMilkyWay(back, value, at = 0) {
  for (let i = 0; i < 3; i++) back[at + i] = toSrgb(toLinear(back[at + i]) + value * MILKY_COLOR[i]);
}

// The stars of view ``w`` (sight-scene.js) added like light onto ``g``.
const layers = new WeakMap();
export function drawStars(g, w, c, t) {
  if (!c.show || typeof document === "undefined") return;
  const topDeg = w.skyY / w.pxPerDeg + 1;
  if (topDeg <= 0) return;
  const pts = points(c, w.los, w.fov, topDeg, t);
  if (!pts.alpha.length) return;
  const owner = g.canvas ?? g, width = Math.max(1, Math.floor(w.width)), height = Math.max(1, Math.floor(w.height));
  let layer = layers.get(owner);
  if (!layer || layer.canvas.width !== width || layer.canvas.height !== height) {
    const canvas = document.createElement("canvas");
    canvas.width = width; canvas.height = height;
    layer = {canvas, image: canvas.getContext("2d").createImageData(width, height), sum: new Float32Array(width * height * 3)};
    layers.set(owner, layer);
  }
  const {image, sum} = layer, data = image.data, touched = [];
  sum.fill(0);
  for (let i = 0; i < pts.alpha.length; i++) {
    const x0 = width / 2 + (mod(pts.bearing[i] - w.los + 180, 360) - 180) * w.pxPerDeg, y0 = w.skyY - pts.elev[i] * w.pxPerDeg;
    const cx = Math.floor(x0), cy = Math.floor(y0), spread = 2 * pts.sigma[i] ** 2, light = pts.alpha[i] * 255;
    for (let dx = -1; dx <= 1; dx++) {
      for (let dy = -1; dy <= 1; dy++) {
        const x = cx + dx, y = cy + dy;
        if (x < 0 || x >= width || y < 0 || y >= height) continue;
        const weight = Math.exp(-(dx * dx + dy * dy) / spread) * light, at = (y * width + x) * 3;
        if (sum[at] === 0 && sum[at + 1] === 0 && sum[at + 2] === 0) touched.push(at);
        for (let j = 0; j < 3; j++) sum[at + j] += pts.rgb[i * 3 + j] * weight;
      }
    }
  }
  data.fill(0);
  for (const at of touched) {
    const px = at / 3 * 4;
    for (let j = 0; j < 3; j++) data[px + j] = sum[at + j];
    data[px + 3] = 255;
  }
  const lg = layer.canvas.getContext("2d");
  lg.putImageData(image, 0, 0);
  g.save();
  g.globalCompositeOperation = "lighter";
  g.drawImage(layer.canvas, 0, 0);
  g.restore();
}
