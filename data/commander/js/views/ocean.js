// The sea surface in the browser eyepieces, the twin of src/ui/ocean.py (the
// look of Tiefenkontakt's ocean): each cell of the sea below the horizon is a
// point on the water whose wave normal mirrors the sky, shows the deep
// water, the sun's or moon's glitter, whitecaps and the haze.  Computed in
// cells and smoothed up; display only.

const WK = Array.from({length: 12}, (_, i) => .025 * 44 ** (i / 11));
const SPREAD = [24, -6, 17, -21, 8, -33, 29, -12, 41, -47, 3, 58];
const PH0 = [0, 2.1, 4.4, 1.3, 5.6, 3.2, .7, 4.9, 2.8, 6.0, 1.8, 3.9];
const CHOP0 = WK.findIndex((k) => k >= .15);
const HS = [.05, .25, .8, 1.6, 2.8, 4.2, 6, 8.5, 11, 14];
const PEAK_K = [.9, .6, .38, .24, .15, .1, .075, .055, .045, .04];
const G = 9.81, TAU = 2 * Math.PI, RAD = Math.PI / 180;
const DEEP = [16 / 255, 48 / 255, 58 / 255], SUBSURFACE = [.02, .07, .06], FOAM = [.86, .9, .92];
const SUN_GLITTER = [1, .92, .8], MOON_GLITTER = [.75, .8, .9];
const CELLS = 2400, MIN_CELL_PX = 24, EXTINCTION = 3, FOOT = 1, NOISE_SIZE = 64;

const table = (values, x) => {
  x = Math.min(values.length - 1, Math.max(0, x));
  const i = Math.min(values.length - 2, Math.floor(x));
  return values[i] + (values[i + 1] - values[i]) * (x - i);
};
const smoothstep = (low, high, x) => { const t = Math.min(1, Math.max(0, (x - low) / (high - low))); return t * t * (3 - 2 * t); };
const mod = (x, m) => ((x % m) + m) % m;

export function waves(seaState, windFromDeg, ownE, ownN, t) {
  const toward = (windFromDeg + 180) * RAD, kp = table(PEAK_K, seaState);
  const raw = WK.map((k, i) => {
    const x = Math.log(k / kp) / .55;
    return Math.exp(-.5 * x * x) * (k < kp ? 1 : (kp / k) ** .6) + (k < .05 ? .06 : .012) * (i % 2 === 1 ? .8 : 1.2);
  });
  const sum = raw.reduce((a, b) => a + b, 0), share = raw.map((v) => v / sum);
  const sigma = Math.sqrt(share.reduce((a, v) => a + v * v, 0) / 2);
  const amp = table(HS, seaState) / (4 * sigma);
  const fold = share.reduce((a, v, i) => a + Math.min(5 * amp * v, .75 / WK[i]) * WK[i], 0);
  const direction = SPREAD.map((deg) => [Math.sin(toward + deg * RAD), Math.cos(toward + deg * RAD)]);
  const phase = WK.map((k, i) => mod(k * (direction[i][0] * ownE + direction[i][1] * ownN) - Math.sqrt(G * k) * t + PH0[i], TAU));
  return {amp, chop: Math.min(1, .8 / Math.max(fold, 1e-6)), share, direction, phase, wind: [Math.sin(toward), Math.cos(toward)]};
}

// Value noise over a fixed lattice (an integer hash, as src/ui/ocean.py).
export const LATTICE = (() => {
  const values = new Float64Array(NOISE_SIZE * NOISE_SIZE);
  for (let i = 0; i < values.length; i++) {
    let x = Math.imul(i, 0x9E3779B1) >>> 0;
    x = (x ^ (x >>> 15)) >>> 0; x = Math.imul(x, 0x85EBCA77) >>> 0;
    x = (x ^ (x >>> 13)) >>> 0; x = Math.imul(x, 0xC2B2AE3D) >>> 0;
    x = (x ^ (x >>> 16)) >>> 0;
    values[i] = x / 4294967296;
  }
  return values;
})();
export function noise(px, py) {
  const ix = Math.floor(px), iy = Math.floor(py), fx = px - ix, fy = py - iy;
  const ux = fx * fx * (3 - 2 * fx), uy = fy * fy * (3 - 2 * fy);
  const i0 = mod(ix, NOISE_SIZE), j0 = mod(iy, NOISE_SIZE), i1 = (i0 + 1) % NOISE_SIZE, j1 = (j0 + 1) % NOISE_SIZE;
  const a = LATTICE[j0 * NOISE_SIZE + i0], b = LATTICE[j0 * NOISE_SIZE + i1];
  const c = LATTICE[j1 * NOISE_SIZE + i0], d = LATTICE[j1 * NOISE_SIZE + i1];
  const top = a + (b - a) * ux;
  return top + ((c + (d - c) * ux) - top) * uy;
}
function fbm(px, py) {
  let value = 0, weight = .5;
  for (let i = 0; i < 4; i++) { value += weight * noise(px, py); px *= 2; py *= 2; weight *= .5; }
  return value;
}
const unit = (bearing, alt) => [Math.sin(bearing * RAD) * Math.cos(alt * RAD), Math.cos(bearing * RAD) * Math.cos(alt * RAD), Math.sin(alt * RAD)];

// ``colors`` as sight-scene.js palette (sky [top, horizon], haze), 0..255.
export function seaParams(sky, colors, {seaState, visibility, eye, ownE, ownN, t}) {
  const light = sky.light, sunUp = Math.min(1, Math.max(0, (sky.sun_alt_deg + 1) / 6));
  const clear = 1 - Math.min(1, Math.max(0, (sky.cloud - .5) * 2));
  const top = colors.sky[0].map((c) => c / 255), horizon = colors.sky[1].map((c) => c / 255), haze = colors.haze.map((c) => c / 255);
  let reflect = horizon.map((c, i) => c + (top[i] - c) * .25);
  reflect = reflect.map((c, i) => c + (haze[i] - c) * .3);
  const reflectTop = top.map((c, i) => c + (horizon[i] - c) * .25);
  return {
    waves: waves(seaState, sky.wind_from_deg, ownE, ownN, t), t, eye: Math.max(1, eye), light,
    deep: DEEP.map((c) => c * (.12 + .88 * light * light)), reflect, reflectTop, haze,
    sun: unit(sky.sun_bearing, sky.sun_alt_deg), moon: unit(sky.moon_bearing, sky.moon_alt_deg),
    sunUp: sunUp * clear, moonLight: sky.moon_illumination * clear * (sky.moon_alt_deg > 0 ? 1 : 0),
    foam: Math.min(1, Math.max(0, (seaState - 2) / 4)), spin: Math.min(1, Math.max(0, (seaState - 4) / 2)),
    rain: sky.precipitation === "rain" ? sky.intensity : 0,
    fog: EXTINCTION / Math.max(50, visibility * 1852), own: [mod(ownE, 32768), mod(ownN, 32768)],
  };
}

// The colour (0..1) of the sea seen at true ``bearing`` and ``below`` degrees
// under the sea horizon, the cell ``cellDeg`` wide; into ``out`` at ``at``.
export function shade(p, bearing, below, cellDeg, out, at = 0) {
  const eye = p.eye, dip = Math.sqrt(2 * eye / 7.3e6), w = p.waves;
  const down = Math.max(below, 1e-4) * RAD + dip, distance = eye / Math.tan(down);
  const se = Math.sin(bearing * RAD), sn = Math.cos(bearing * RAD), e = se * distance, n = sn * distance;
  const cosD = Math.cos(down), sinD = Math.sin(down);
  const view = [-se * cosD, -sn * cosD, sinD];
  const cell = cellDeg * RAD;
  const foot = Math.max(Math.sqrt(distance * cell * distance * cell / Math.max(sinD, 1e-4)) * FOOT, .05);
  let ge = 0, gn = 0, height = 0, chop = 0, shortSum = 0;
  for (let i = 0; i < 12; i++) {
    const lam = TAU / WK[i], weight = w.share[i] * (1 - smoothstep(lam * .15, lam * .35, foot));
    const psi = WK[i] * (e * w.direction[i][0] + n * w.direction[i][1]) + w.phase[i];
    const c = Math.cos(psi), s = Math.sin(psi);
    ge += weight * WK[i] * c * w.direction[i][0]; gn += weight * WK[i] * c * w.direction[i][1];
    height += weight * s;
    if (i >= CHOP0) { chop += weight * s; shortSum += w.share[i]; }
  }
  let nx = -ge * w.amp * 1.2, ny = -gn * w.amp * 1.2, nz = 1;
  const seaE = e + p.own[0], seaN = n + p.own[1];
  const near = (1 - smoothstep(60, 900, distance)) * (1 - smoothstep(.4, 1.6, foot));
  if (near > 0) {
    const qx = seaE + w.wind[0] * p.t * .7, qy = seaN + w.wind[1] * p.t * .7;
    nx += (noise(qx, qy) - .5) * .12 * near;
    ny += (noise(qx * 2 + 4, qy * 2 + 4) - .5) * .12 * near;
  }
  if (p.rain > 0) {
    const pock = p.rain * (1 - smoothstep(.1, .75, foot)) * (1 - smoothstep(80, 450, distance));
    const rx = seaE * 3, ry = seaN * 3;
    nx += (noise(rx + p.t * 11, ry + p.t * 11) - .5) * .8 * pock;
    ny += (noise(rx * 1.7 - p.t * 9, ry * 1.7 - p.t * 9) - .5) * .8 * pock;
  }
  const len = Math.hypot(nx, ny, nz); nx /= len; ny /= len; nz /= len;
  const facing = nx * view[0] + ny * view[1] + nz * view[2];
  const fresnel = (1 - Math.max(facing, 0)) ** 4;
  const mirror = [2 * facing * nx - view[0], 2 * facing * ny - view[1], 2 * facing * nz - view[2]];
  const up = smoothstep(0, .7, mirror[2]), mix = Math.min(1, Math.max(0, .08 + fresnel * .85));
  const color = [0, 1, 2].map((i) => {
    const sky = p.reflect[i] + (p.reflectTop[i] - p.reflect[i]) * up;
    return p.deep[i] + (sky - p.deep[i]) * mix + SUBSURFACE[i] * Math.max(0, height) * p.light;
  });
  if (p.sunUp > 0) {
    const sd = Math.max(mirror[0] * p.sun[0] + mirror[1] * p.sun[1] + mirror[2] * p.sun[2], 0);
    const k = (sd ** 400 * 1.4 + sd ** 60 * .45 + sd ** 30 * .12) * p.sunUp;
    for (let i = 0; i < 3; i++) color[i] += SUN_GLITTER[i] * k;
  }
  if (p.moonLight > 0 && p.sunUp < 1) {
    const md = Math.max(mirror[0] * p.moon[0] + mirror[1] * p.moon[1] + mirror[2] * p.moon[2], 0);
    const k = (md ** 160 * .9 + md ** 40 * .3) * (1 - p.sunUp) * p.moonLight;
    for (let i = 0; i < 3; i++) color[i] += MOON_GLITTER[i] * k;
  }
  if (p.foam > 0) {
    const [wa, wb] = w.wind;
    const wx = e * wa + n * wb + (p.own[0] * wa + p.own[1] * wb);
    const wy = -e * wb + n * wa + (-p.own[0] * wb + p.own[1] * wa);
    const chopN = chop / Math.max(shortSum, 1e-3);
    const pf = fbm(wx * .0625 + p.t * .03, wy * .125);
    let fine = noise(seaE * .5 + wa * p.t * .4, seaN * .5 + wb * p.t * .4);
    fine += (.5 - fine) * smoothstep(1, 4, foot);
    const m = .42 * chopN + .12 * height + .9 * pf - 1 + .3 * p.foam;
    let foam = smoothstep(0, .12, m) * smoothstep(.25, .7, fine);
    const far = 1 - smoothstep(400, 2500, distance);
    foam = (.05 * p.foam + (foam - .05 * p.foam) * far) * p.foam;
    if (p.spin > 0) {
      const sy = wy + (noise(wx * .05, wy * .05) - .5) * 14;
      const lane = noise(wx * .03 + p.t * .05, sy * .45);
      const patchy = smoothstep(.4, .75, noise(wx * .012 + 9, wy * .05 + 9));
      const sharp = 1 - smoothstep(.6, 2.5, foot);
      foam += p.spin * (.08 + (smoothstep(.6, .82, lane) * patchy * .45 - .08) * sharp) * far;
    }
    const k = Math.min(1, Math.max(0, foam)) * .85;
    for (let i = 0; i < 3; i++) color[i] += (FOAM[i] * (.1 + .9 * p.light) - color[i]) * k;
  }
  const fog = 1 - Math.exp(-distance * p.fog);
  for (let i = 0; i < 3; i++) out[at + i] = Math.min(1, Math.max(0, color[i] + (p.haze[i] - color[i]) * fog));
  return out;
}

export function gridSize(width, height) {
  const total = Math.min(CELLS, width * height / MIN_CELL_PX);
  const cell = Math.max(1, Math.sqrt(width * height / (total * 2)));
  return [Math.max(2, Math.round(width / (cell * 2))), Math.max(2, Math.round(height / cell))];
}

// A page shows several sight pictures (binoculars, lookout strip, weather
// picture) each animating every frame; the waves are shaded at most every
// SEA_FRAME_MS per picture and the last shading is reused in between, while
// a turned or tilted view is shaded again at once.
export const SEA_FRAME_MS = 50;
const shaded = new WeakMap();
// The shaded sea below the moving horizon of view ``w`` (sight-scene.js).
export function drawOcean(g, w, sky, colors, options) {
  const top = Math.max(0, Math.floor(Math.min(w.base(0), w.base(w.width))) - 1);
  if (top >= w.height || typeof document === "undefined") return;
  const width = w.width, height = w.height - top, [columns, rows] = gridSize(width, height);
  const owner = g.canvas ?? g;
  let last = shaded.get(owner);
  if (!last) { last = {canvas: document.createElement("canvas"), at: -Infinity, view: ""}; shaded.set(owner, last); }
  const canvas = last.canvas, now = performance.now();
  const view = `${columns}x${rows}:${top}:${w.los.toFixed(2)}:${w.pxPerDeg.toFixed(3)}:${w.base(0).toFixed(1)}:${w.base(width).toFixed(1)}`;
  if (view !== last.view || !(now - last.at < SEA_FRAME_MS)) {
    last.view = view; last.at = now;
    shadeInto(canvas, w, top, width, height, columns, rows, seaParams(sky, colors, options));
  }
  g.save();
  g.beginPath(); g.moveTo(0, w.base(0)); g.lineTo(width, w.base(width)); g.lineTo(width, w.height); g.lineTo(0, w.height); g.closePath();
  g.clip();
  g.imageSmoothingEnabled = true;
  g.drawImage(canvas, 0, top, width, height);
  g.restore();
}

function shadeInto(canvas, w, top, width, height, columns, rows, p) {
  if (canvas.width !== columns || canvas.height !== rows) { canvas.width = columns; canvas.height = rows; }
  const small = canvas.getContext("2d"), image = small.createImageData(columns, rows), rgb = new Float64Array(3);
  const cellDeg = width / columns / w.pxPerDeg, minBelow = .5 * height / rows / w.pxPerDeg;
  for (let row = 0; row < rows; row++) {
    const y = top + (row + .5) * height / rows;
    for (let column = 0; column < columns; column++) {
      const x = (column + .5) * width / columns;
      const below = Math.max((y - w.base(x)) / w.pxPerDeg, minBelow);
      shade(p, w.los + (x - width / 2) / w.pxPerDeg, below, cellDeg, rgb);
      const at = (row * columns + column) * 4;
      image.data[at] = Math.round(rgb[0] * 255); image.data[at + 1] = Math.round(rgb[1] * 255);
      image.data[at + 2] = Math.round(rgb[2] * 255); image.data[at + 3] = 255;
    }
  }
  small.putImageData(image, 0, 0);
}
