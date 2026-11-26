// The start screen's look for the browser eyepieces (periscope, binoculars):
// the same picture as src/ui/sight_scene.py and src/ui/horizon.py on the
// uConsole.  Sky, stars, sun or moon, clouds, the sea in motion, silhouettes
// in steel with a lit rim, rain, snow or fog, the bearing scale and the
// corner brackets, the land in sight.  Display only: every value comes from the detached state
// (the view's ``sky`` block and outlines); the phase is the wall clock.
import { drawInScene } from "./model-view.js";
import { DETAIL_MIN_PX, FOAM, NAV_LIGHT, PROFILES } from "./silhouette-profiles.js";
import { drawOcean } from "./ocean.js";
import { drawSightEvents } from "./sight-events.js";
import { palette as themePalette } from "../core/palette.js";

const SKY_NIGHT = [[3, 7, 16], [20, 44, 62]], SKY_DAY = [[34, 88, 118], [138, 176, 182]], SKY_DUSK = [[24, 30, 60], [204, 128, 78]];
const SEA_NIGHT = [[10, 44, 58], [2, 9, 15]], SEA_DAY = [[24, 78, 92], [6, 34, 46]], SEA_DUSK = [[44, 50, 66], [8, 14, 26]];
const OVERCAST_DAY = [108, 120, 126], OVERCAST_NIGHT = [18, 24, 30];
const HAZE_DAY = [150, 160, 165], HAZE_NIGHT = [34, 44, 50];
const MOON = [214, 222, 206], MOON_DARK = [26, 34, 42], SUN_DAY = [255, 244, 210], SUN_DUSK = [255, 178, 96];
const STEEL_NIGHT = [19, 36, 46], STEEL_DAY = [44, 56, 64], RIM_NIGHT = [84, 150, 158], RIM_DAY = [170, 196, 200];
const WINDOW_LIGHT = [250, 205, 120], FRAME = [40, 96, 90], WIND_ARROW = [120, 214, 180];
// The scale and the crosshair are instrument furniture, not the scene: theme tokens.
const SCALE = () => themePalette().live, CROSSHAIR = () => themePalette().accent;
const STABILIZED_RESIDUAL = .12;   // src/ui/horizon.py
// Below this elevation an aircraft stands on the moving sea horizon in front of the sea (LOW_AIR_DEG).
const LOW_AIR_DEG = 1;
const VISIBILITY_MAX_NM = 30, BODY_MAX_ALT_DEG = 45, SCALE_LABEL_MIN_PX = 36;

const clamp = (value, low = 0, high = 1) => Math.max(low, Math.min(high, value));
export const mix = (a, b, k) => a.map((value, index) => Math.round(value + (b[index] - value) * clamp(k)));
export const rgb = (c) => `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
const wrap = (deg) => ((deg % 360) + 540) % 360 - 180;

// Stars and clouds in bearing space (fixed seed; cosmetic only).
const FIELD = (() => {
  let seed = 217;
  const random = () => { seed = (seed + 0x6D2B79F5) | 0; let x = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    x = (x + Math.imul(x ^ (x >>> 7), 61 | x)) ^ x; return ((x ^ (x >>> 14)) >>> 0) / 4294967296; };
  const stars = Array.from({length: 220}, () => [random() * 360, random() ** .8, random() * Math.PI * 2, .6 + random() * 1.6, random() < .12]);
  const clouds = Array.from({length: 26}, () => [random() * 360, .25 + random() * .7, 6 + random() * 16, .05 + random() * .07, random()]);
  return {stars, clouds};
})();

function pair(night, day, glow, light, dusk) {
  return night.map((color, index) => mix(mix(color, day[index], light), glow[index], dusk * .7));
}

export function palette(sky, haze) {
  const {light, dusk, cloud} = sky;
  const hazeColor = mix(HAZE_NIGHT, HAZE_DAY, light), overcast = mix(OVERCAST_NIGHT, OVERCAST_DAY, light);
  const grey = Math.max(0, cloud - .5) * 1.2;
  const skyPair = pair(SKY_NIGHT, SKY_DAY, SKY_DUSK, light, dusk * (1 - grey)).map((c) => mix(mix(c, overcast, grey * .8), hazeColor, haze * .7));
  const seaPair = pair(SEA_NIGHT, SEA_DAY, SEA_DUSK, light, dusk).map((c) => mix(mix(c, overcast, grey * .3), hazeColor, haze * .35));
  return {sky: skyPair, sea: seaPair, haze: hazeColor,
    wave: mix(mix([22, 70, 80], [58, 112, 122], light), hazeColor, haze * .5),
    crest: mix(mix([96, 150, 156], [186, 212, 214], light), hazeColor, haze * .5),
    steel: mix(STEEL_NIGHT, STEEL_DAY, light), rim: mix(mix(RIM_NIGHT, RIM_DAY, light), SUN_DUSK, dusk * .5),
    cloud: mix(mix([26, 36, 46], [196, 204, 208], light), [196, 130, 96], dusk * .6),
    cloudRim: mix(mix([70, 96, 108], [238, 242, 242], light), [250, 190, 130], dusk * .7),
    // Glowing plankton in stirred water (night bloom, 0..1).
    glow: (Number(sky.glow) || 0) * (1 - haze * .6)};
}
// Bioluminescence: wakes and torpedo tracks glow blue-green by ``foamGlow``
// (set from the sky while the afloat outlines are drawn).
const GLOW = [70, 235, 205];
let foamGlow = 0;
const foamColor = () => rgb(mix(FOAM, GLOW, clamp(foamGlow)));

// --- silhouettes (the uConsole's profiles, generated) -----------------------
// Height of the aircraft's body in its profile (src/ui/silhouettes.py).
const AIRCRAFT_CENTRE_V = .555;

// ``aloft``: an aircraft centred on ``base`` (its elevation) instead of
// hovering over the horizon.
function frameFor(cls, cx, base, width, t, facing = -1, aloft = false) {
  const profile = PROFILES[cls] || PROFILES.unknown;
  const lift = aloft ? -AIRCRAFT_CENTRE_V * width : profile.hover ? width * (.25 + .02 * Math.sin(t * 1.3)) : 0;
  const pitch = profile.pitch_deg * Math.PI / 180 * Math.sin(2 * Math.PI * profile.pitch_hz * t);
  const cos = Math.cos(pitch), sin = Math.sin(pitch), left = cx - width / 2, baseY = base - lift;
  const point = (u, v) => {
    const du = u - .5, ru = (du * cos - v * sin) * (facing > 0 ? -1 : 1), rv = du * sin + v * cos;
    return [left + (.5 + ru) * width, baseY - rv * width];
  };
  return {point, poly: (points) => points.map(([u, v]) => point(u, v))};
}

function path(g, points, close = true) {
  g.beginPath(); points.forEach(([x, y], index) => index ? g.lineTo(x, y) : g.moveTo(x, y)); if (close) g.closePath();
}

function line(g, a, b, color, width = 1) {
  g.strokeStyle = color; g.lineWidth = width; g.beginPath(); g.moveTo(a[0], a[1]); g.lineTo(b[0], b[1]); g.stroke();
}

// Navigation lights: code "<L|R><masts><r|-><g|-><s|->" (src/sensors/nav_lights.py);
// drawn at any size, since at night the lights are what the eye picks up first.
export const navFacing = (code) => (typeof code === "string" && code[0] === "R" ? 1 : -1);

// A red beacon flash every second, a white strobe double flash every 1.2 s.
function antiCollision(t) {
  const phase = t % 1.2;
  return [t % 1 < .12, phase < .06 || (phase >= .18 && phase < .24)];
}

function drawNavLights(g, cls, frame, width, code, t, navPoints = null) {
  const aircraft = code.slice(5) === "AC";
  const nav = aircraft ? PROFILES.aircraft.nav : navPoints || (PROFILES[cls] || PROFILES.merchant).nav || PROFILES.merchant.nav;
  const core = Math.max(1, Math.min(3, Math.floor(width / 150))), points = [], roundLights = code.slice(5);
  // A trawler's single masthead light stands abaft and above her green.
  const mast = roundLights === "GW" ? nav.mast.slice(1) : nav.mast;
  for (let index = 0; index < Number(code[1]); index++) points.push([mast[index], "white"]);
  const [su, sv] = nav.side, red = code[2] === "r", green = code[3] === "g";
  if (red && green) points.push([[su - .004, sv], "red"], [[su + .004, sv], "green"]);
  else if (red) points.push([[su, sv], "red"]);
  else if (green) points.push([[su, sv], "green"]);
  if (code[4] === "s") points.push([nav.stern, "white"]);
  const spots = points.map(([[u, v], name]) => [frame.point(u, v), name]);
  if (aircraft) {
    const [beacon, strobe] = antiCollision(t);
    if (beacon) for (const [u, v] of nav.beacon) spots.push([frame.point(u, v), "red"]);
    if (strobe) spots.push([frame.point(...nav.strobe), "white"]);
  } else if (roundLights) {
    // All-round lights down the mast (mine clearance: masthead and each yardarm).
    const [x, y] = frame.point(...nav.round), step = Math.max(core * 2 + 3, width * .02);
    const names = {W: "white", R: "red", G: "green"};
    if (roundLights === "GGG") spots.push([[x, y - step], "green"], [[x - step, y], "green"], [[x + step, y], "green"]);
    else [...roundLights].forEach((letter, index) => spots.push([[x, y - step * (roundLights.length - index)], names[letter]]));
  }
  for (const [[x, y], name] of spots) {
    const color = NAV_LIGHT[name];
    g.fillStyle = rgb(color.map((c) => Math.floor(c * .45)));
    g.beginPath(); g.arc(x, y, core + 2, 0, 2 * Math.PI); g.fill();
    g.fillStyle = rgb(color);
    g.beginPath(); g.arc(x, y, core, 0, 2 * Math.PI); g.fill();
  }
}

// With the judged angle on the bow ``aob`` a large enough ship, submarine or
// aircraft is drawn as its 3D model turned to that aspect.
// The bubble track of a running torpedo (src/ui/silhouettes.py draw_bubble_track).
function drawBubbleTrack(g, cx, base, width, t) {
  width = Math.max(3, width);
  const left = cx - width / 2, foam = foamColor();
  line(g, [left, base + 1], [left + width, base + 1], foam, Math.max(1, Math.min(3, Math.floor(width / 40) + 1)));
  const count = Math.max(3, Math.min(18, Math.floor(width / 8)));
  g.strokeStyle = foam; g.lineWidth = 1;
  for (let k = 0; k < count; k++) {
    const phase = ((t * .7 + k * .618) % 1 + 1) % 1, radius = Math.max(1, Math.floor(1 + 2 * Math.sin(Math.PI * phase)));
    g.beginPath(); g.arc(left + width * ((k + .5) / count), base + 1, radius, 0, Math.PI * 2); g.stroke();
  }
}

export function drawProfile(g, cls, cx, base, width, fill, {t = 0, rim = null, lights = null, nav = null, aloft = false, aob = null, model = null} = {}) {
  width = Math.max(3, width);
  const scene = drawInScene(g, cls, cx, base, width, fill, aob, aloft, model);
  if (scene) {
    if (typeof nav === "string") drawNavLights(g, cls, scene, Math.floor(width), nav, t, scene.nav);
    return;
  }
  if (cls === "torpedo") {
    drawBubbleTrack(g, cx, base, width, t);
    return;
  }
  const facing = navFacing(nav);
  const profile = PROFILES[cls] || PROFILES.unknown, frame = frameFor(cls, cx, base, width, t, facing, aloft);
  const detail = width >= DETAIL_MIN_PX, fillColor = rgb(fill), rimColor = rim ? rgb(rim) : fillColor;
  const polys = [frame.poly(profile.hull), ...profile.blocks.map((block) => frame.poly(block))];
  g.fillStyle = fillColor;
  for (const poly of polys) { path(g, poly); g.fill(); }
  const lineWidth = Math.max(1, Math.floor(width / 260));
  for (const [a, b] of profile.lines) line(g, frame.point(...a), frame.point(...b), detail ? rimColor : fillColor, lineWidth);
  if (profile.rotor) {
    const [hu, hv, half] = profile.rotor, blade = Math.abs(Math.cos(t * 23));
    line(g, frame.point(hu - half * blade, hv), frame.point(hu + half * blade, hv), rimColor, 2);
    line(g, frame.point(hu - half, hv), frame.point(hu + half, hv), rimColor, 1);
  }
  if (profile.radar && detail) {
    const [ru, rv, half] = profile.radar, span = half * Math.abs(Math.cos(t * 2.6));
    line(g, frame.point(ru - span, rv), frame.point(ru + span, rv), rimColor, Math.max(1, Math.floor(width / 200)));
  }
  if (detail && rim) {
    g.strokeStyle = rimColor; g.lineWidth = 1;
    for (const poly of polys) { path(g, poly); g.stroke(); }
    g.fillStyle = rimColor;
    for (const panel of profile.panels) { path(g, frame.poly(panel)); g.fill(); }
  }
  if (detail && lights) {
    const size = Math.max(1, Math.floor(width / 180));
    g.fillStyle = rgb(lights);
    for (const [u, v] of profile.windows) { const [x, y] = frame.point(u, v); g.fillRect(Math.floor(x), Math.floor(y), size + 1, size); }
  }
  if (profile.wake && detail) {
    const bow = frame.point(.03, 0), stern = frame.point(1, 0), foam = foamColor();
    for (let index = 0; index < 3; index++) {
      const phase = (t * 1.7 + index * .33) % 1, reach = width * (.01 + .035 * phase), rise = width * .018 * (1 - phase);
      line(g, [bow[0] + facing * reach * .3, bow[1]], [bow[0] + facing * reach, bow[1] - rise], foam);
    }
    const step = Math.max(3, width * .04), offset = (t * 18) % (2 * step);
    for (let k = 0; k < 6; k++) {
      const start = offset + k * 2 * step;
      if (start > width * .35) break;
      line(g, [stern[0] - facing * start, stern[1]], [stern[0] - facing * (start + step * .8), stern[1]], foam);
    }
  }
  if (typeof nav === "string") drawNavLights(g, cls, frame, width, nav, t);
}

// --- the land (src/ui/horizon.py: land_wire, _land_columns, _draw_land) -----
const LAND_NIGHT = [8, 20, 26], LAND_HAZE_MIN = .06, LAND_HAZE = .8, LAND_COLUMN_PX = 6;
let landCache = null;
// src/ui/horizon.py: the land colours (sand, grass, rock, snow) and the palette
// the packed land indexes (land_palette).
const LAND_SAND = [138, 132, 112], LAND_GRASS = [77, 90, 68], LAND_ROCK = [95, 95, 90], LAND_SNOW = [217, 220, 220];
const LAND_PALETTE_STEPS = 32;
const roundHalfEven = (value) => {
  const floor = Math.floor(value), rest = value - floor;
  return rest > .5 || (rest === .5 && floor % 2) ? floor + 1 : floor;
};
export const LAND_PALETTE = (() => {
  const steps = Array.from({length: LAND_PALETTE_STEPS}, (_, k) => k / (LAND_PALETTE_STEPS - 1));
  const lerp = (a, b, t) => a.map((value, index) => roundHalfEven(value + (b[index] - value) * t));
  return [LAND_SAND, ...steps.map((t) => lerp(LAND_GRASS, LAND_ROCK, t)), ...steps.map((t) => lerp(LAND_SNOW, LAND_ROCK, t))];
})();
// The packed land: per band (near to far) and ray the rise above the sea
// horizon (deg, NaN none), the crest's range (NM) and its day colour.
export function decodeLand(land) {
  if (!land || typeof land.data !== "string") return null;
  if (landCache?.data === land.data) return landCache.value;
  const bytes = Uint8Array.from(atob(land.data), (ch) => ch.charCodeAt(0));
  const {bands, rays} = land;
  const u16 = (at) => bytes[at] | (bytes[at + 1] << 8);
  let at = 0;
  const value = [];
  for (let band = 0; band < bands; band++) {
    const rise = new Float32Array(rays).fill(NaN), range = new Float32Array(rays).fill(Infinity);
    const color = Array.from({length: rays}, () => LAND_ROCK);
    if (at + 2 > bytes.length) return null;
    const runs = u16(at); at += 2;
    for (let run = 0; run < runs; run++) {
      if (at + 4 > bytes.length) return null;
      const start = u16(at), count = u16(at + 2); at += 4;
      if (start + count > rays || at + count * 4 > bytes.length) return null;
      for (let ray = start; ray < start + count; ray++, at += 4) {
        rise[ray] = u16(at) / 100; range[ray] = bytes[at + 2] * .25;
        color[ray] = LAND_PALETTE[bytes[at + 3]] ?? LAND_ROCK;
      }
    }
    value.push({rise, range, color});
  }
  landCache = {data: land.data, value: {rays, bands: value}};
  return landCache.value;
}

// The land bands far to near, each a run of polygons from the moving sea
// horizon up to its crests; in a narrow field heights and colours blend
// between the rays.
function drawLand(g, w, v, colors, light) {
  const land = decodeLand(v.land);
  if (!land) return;
  const step = 360 / land.rays, sub = Math.max(1, Math.ceil(step * w.pxPerDeg / LAND_COLUMN_PX));
  const first = Math.floor((v.bearing - v.fov_deg / 2) / step) - 1, last = Math.ceil((v.bearing + v.fov_deg / 2) / step) + 1;
  const visibility = Math.max(Number(v.visibility_nm) || 0, .1), lit = clamp(light * 1.25);
  const flush = (run, color, fade) => {
    if (run.length < 2 || !color) return;
    g.fillStyle = rgb(color); g.beginPath();
    run.forEach(([x, top], index) => (index ? g.lineTo(x, top) : g.moveTo(x, top)));
    for (let index = run.length - 1; index >= 0; index--) g.lineTo(run[index][0], run[index][2] + 1);
    g.closePath(); g.fill();
    g.strokeStyle = rgb(mix(colors.rim, colors.haze, .3 + .6 * fade)); g.lineWidth = 1; g.beginPath();
    run.forEach(([x, top], index) => (index ? g.lineTo(x, top) : g.moveTo(x, top)));
    g.stroke();
  };
  for (let band = land.bands.length - 1; band >= 0; band--) {
    const {rise, range, color: day} = land.bands[band];
    let run = [], runColor = null, runFade = 0;
    for (let k = first * sub; k <= last * sub; k++) {
      const position = k / sub, index = Math.floor(position), t = position - index;
      const a = ((index % land.rays) + land.rays) % land.rays, b = (a + 1) % land.rays;
      const both = Number.isFinite(rise[a]) && Number.isFinite(rise[b]), near = t < .5 ? a : b;
      const r = both ? rise[a] * (1 - t) + rise[b] * t : rise[near];
      const d = both ? range[a] * (1 - t) + range[b] * t : range[near];
      const x = w.width / 2 + wrap(position * step - v.bearing) * w.pxPerDeg;
      if (!Number.isFinite(d) || d > visibility || !Number.isFinite(r)) {
        flush(run, runColor, runFade); run = []; runColor = null; continue;
      }
      if (run.length && x - run[run.length - 1][0] >= w.width) { flush(run, runColor, runFade); run = []; }
      const base = w.base(x), point = [x, base - Math.max(2, r * w.pxPerDeg), base];
      const fade = Math.min(1, d / visibility);
      const dayColor = both ? day[a].map((c, i) => c * (1 - t) + day[b][i] * t) : day[near];
      const shade = LAND_NIGHT.map((c, i) => Math.trunc(c + (Math.trunc(dayColor[i]) - c) * lit));
      const color = mix(shade, colors.haze, LAND_HAZE_MIN + LAND_HAZE * fade * fade).map((c) => c - (c % 3));
      if (run.length && String(color) !== String(runColor)) {
        run.push(point); flush(run, runColor, runFade); run = [point];
      } else run.push(point);
      runColor = color; runFade = fade;
    }
    flush(run, runColor, runFade);
  }
}

// --- the picture ------------------------------------------------------------
function view(width, height, v) {
  const pxPerDeg = width / v.fov_deg;
  // A stabilized optic keeps STABILIZED_RESIDUAL of the hull's motion;
  // tilting it up (elevation_deg) moves the sky and the horizon down.
  const steady = v.stabilized ? STABILIZED_RESIDUAL : 1, lift = (v.elevation_deg || 0) * pxPerDeg;
  const horizon = height / 2 + v.horizon_offset * steady * (height / 260) + lift;
  const tilt = v.horizon_tilt * steady;
  const skyH = Math.max(8, height / 2), skyY = skyH + lift;  // the sky stays still: nominal horizon
  return {width, height, pxPerDeg, horizon, tilt, skyH, skyY, los: v.bearing,
    x: (bearing) => width / 2 + wrap(bearing - v.bearing) * pxPerDeg,
    base: (x) => horizon + Math.tan(tilt) * (x - width / 2),
    visible: (bearing, half = 0) => Math.abs(wrap(bearing - v.bearing)) <= v.fov_deg / 2 + half};
}

const bodyFraction = (alt) => .12 + .7 * clamp(alt / BODY_MAX_ALT_DEG);

function drawSky(g, w, sky, colors, t, haze, aloft = null) {
  const gradient = g.createLinearGradient(0, w.skyY + 40 - w.height, 0, w.skyY + 40);
  gradient.addColorStop(0, rgb(colors.sky[0])); gradient.addColorStop(1, rgb(colors.sky[1]));
  g.fillStyle = gradient; g.fillRect(0, 0, w.width, w.height);
  const stars = (1 - sky.light * 1.8) * (1 - sky.cloud) * (1 - haze);
  if (stars > .05) {
    for (const [bearing, alt, phase, speed, bright] of FIELD.stars) {
      if (!w.visible(bearing)) continue;
      const x = w.x(bearing), y = w.skyY - (.08 + .92 * alt) * w.skyH;
      if (y < 2) continue;
      const glow = (.55 + .45 * Math.sin(t * speed + phase)) * stars, level = Math.round((bright ? 150 : 90) * glow + 30 * stars);
      g.fillStyle = rgb(mix(colors.sky[0], [level + 40, level + 40, Math.min(255, level + 70)], stars));
      g.fillRect(Math.floor(x), Math.floor(y), bright ? 2 : 1, bright ? 2 : 1);
    }
  }
  const cover = 1 - clamp((sky.cloud - .6) * 2.5), radius = Math.max(4, Math.floor(.55 * w.pxPerDeg));
  const disc = (x, y, color, glows) => {
    for (const [r, k] of glows) { g.fillStyle = rgb(mix(color, colors.sky[1], k)); g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.fill(); }
    g.fillStyle = rgb(color); g.beginPath(); g.arc(x, y, radius, 0, Math.PI * 2); g.fill();
  };
  if (sky.light > .05 && sky.sun_alt_deg > -1 && cover > .05 && w.visible(sky.sun_bearing, 2)) {
    const x = w.x(sky.sun_bearing), y = w.skyY - bodyFraction(sky.sun_alt_deg) * w.skyH;
    disc(x, y, mix(mix(SUN_DAY, SUN_DUSK, sky.dusk), colors.sky[1], 1 - cover), [[radius * 3, .85], [radius * 2, .7]]);
  }
  if (sky.light < .6 && sky.moon_alt_deg > 0 && sky.moon_illumination > .03 && cover > .05 && w.visible(sky.moon_bearing, 2)) {
    const x = w.x(sky.moon_bearing), y = w.skyY - bodyFraction(sky.moon_alt_deg) * w.skyH;
    disc(x, y, mix(MOON, colors.sky[1], (1 - cover) + haze * .5), [[radius * 4, .9], [radius * 3, .82], [radius * 2, .7]]);
    if (sky.moon_illumination < .97) {
      const shift = (sky.moon_waxing ? -1 : 1) * 2 * radius * sky.moon_illumination;
      g.save(); g.beginPath(); g.arc(x, y, radius + .5, 0, Math.PI * 2); g.clip();
      g.fillStyle = rgb(mix(MOON_DARK, colors.sky[1], .3)); g.beginPath(); g.arc(x + shift, y, radius, 0, Math.PI * 2); g.fill();
      g.restore();
    }
  }
  if (aloft) aloft();
  if (sky.cloud > .2 && haze <= .85) {
    const count = Math.floor(FIELD.clouds.length * clamp((sky.cloud - .15) / .85));
    const drift = t * .05 * (Math.sin((sky.wind_from_deg - w.los) * Math.PI / 180) > 0 ? 1 : -1);
    const moonlit = sky.light > .3 || (sky.moon_alt_deg > 0 && sky.moon_illumination > .3);
    const base = mix(colors.cloud, colors.haze, haze * .6), rim = mix(colors.cloudRim, colors.haze, haze * .6);
    for (const [start, alt, widthDeg, height, shade] of FIELD.clouds.slice(0, count)) {
      const bearing = start + drift;
      if (!w.visible(bearing, widthDeg)) continue;
      const x = w.x(bearing), y = w.skyY - alt * w.skyH, cw = widthDeg * w.pxPerDeg, ch = Math.max(4, height * w.skyH * 1.6);
      const puffs = [[0, 0, 1, .6], [-.25, -.25, .5, .6], [.2, -.3, .45, .7], [.3, .05, .5, .5]];
      puffs.forEach(([dx, dy, fw, fh], index) => {
        const ex = x + dx * cw, ey = y + dy * ch;
        if (moonlit && index) { g.fillStyle = rgb(rim); g.beginPath(); g.ellipse(ex, ey - 1, fw * cw / 2, fh * ch / 2, 0, 0, Math.PI * 2); g.fill(); }
        g.fillStyle = rgb(mix(base, colors.sky[0], .25 * shade)); g.beginPath(); g.ellipse(ex, ey, fw * cw / 2, fh * ch / 2, 0, 0, Math.PI * 2); g.fill();
      });
    }
  }
}

// Horizon motion seen lookRelDeg off the bow (src/ui/horizon.py view_motion):
// ahead the pitch lifts it and the roll tilts it, abeam the other way round.
export function viewMotion(pitch, roll, lookRelDeg = 0) {
  const look = lookRelDeg * Math.PI / 180;
  const lift = pitch * Math.cos(look) + roll * Math.sin(look), lean = roll * Math.cos(look) - pitch * Math.sin(look);
  return [Math.max(-40, Math.min(40, lift * 260)), Math.max(-.25, Math.min(.25, lean * .6))];
}

// The frigate's bow and stern from the bridge lookout, her beam and the Kelvin angle
// (src/ui/sight_scene.py).
const OWN_BOW_M = 40, OWN_STERN_M = 100, OWN_BEAM_M = 17, KELVIN_DEG = 19.47, WAKE_FOAM = 48, BOW_SPRAY = 28;
const RAD = Math.PI / 180;
// The periscope's eye just above the surface (config.UBOOT_SCOPE_EYE_HEIGHT_M).
export const SCOPE_EYE_M = 2.5;
const FLOW = new WeakMap();

// Display-only integral of ``rates`` over the display clock per canvas, so a
// change of speed or view bends the motion instead of making the sea jump.
function flow(key, t, rates) {
  const state = FLOW.get(key), dt = state ? t - state.t : -1;
  const values = dt >= 0 && dt <= 2 ? state.values.map((value, i) => value + rates[i] * dt) : rates.map((rate) => rate * t);
  FLOW.set(key, {t, values});
  return values;
}

// How far below the sea horizon an eye ``eye`` metres up sees the water
// ``distance`` metres away, degrees (0 at and beyond the horizon), as
// sight_scene.waterline_drop_deg.
export function waterlineDropDeg(distance, eye) {
  return Math.max(0, (Math.atan2(eye, Math.max(1, distance)) - Math.sqrt(2 * eye / 7.3e6)) / RAD);
}
// An outline's range, NM; infinite when unknown (on the horizon, behind every ranged one).
export function rowRange(row) {
  const value = row.range_nm;
  return Number.isFinite(value) && value > 0 ? value : Infinity;
}

// The picture row of a point on the sea ``distance`` metres from an eye ``eye`` metres up.
function seaY(w, bearing, distance, eye) {
  return w.base(w.x(bearing)) + waterlineDropDeg(distance, eye) * w.pxPerDeg;
}
const seaPoint = (w, bearing, distance, eye) => [w.x(bearing), seaY(w, bearing, distance, eye)];

// Bow wave and wake of the own ship in true perspective from the eye: the
// wake runs astern between the arms of the Kelvin wave, the bow wave curls
// out from the stem (tilt down to see it; from further up only its spray).
function drawWay(g, w, colors, way, t, haze) {
  const speed = Number(way.speed_kn) || 0;
  if (speed < 1 || way.hull === false) return;
  const course = way.course_deg, eye = way.eye_m ?? 18;
  const strength = clamp(speed / 20) * (1 - haze * .7), glow = (colors.glow || 0) * strength;
  const foam = mix(mix(colors.sea[0], colors.crest, .35 + .55 * strength), GLOW, .85 * glow);
  const stern = (course + 180) % 360, fov = w.width / w.pxPerDeg;
  if (w.visible(stern, 40)) {
    const length = 150 + speed * 120, steps = 16, edges = [[], []];
    let previous = null;
    for (let i = 0; i <= steps; i++) {
      const along = length * (i / steps) ** 1.6, d = OWN_STERN_M + along;
      const rag = 1 + .05 * Math.sin(along * .03 + t * 1.3), half = (OWN_BEAM_M / 2 + along * .02) * rag;
      const edge = Math.atan2(half, d) / RAD;
      const left = seaPoint(w, stern - edge, d, eye), right = seaPoint(w, stern + edge, d, eye);
      edges[0].push(left); edges[1].push(right);
      if (previous) {
        g.globalAlpha = (.08 + .17 * strength) * (1 - i / steps);
        g.fillStyle = rgb(colors.crest);
        path(g, [previous[0], previous[1], right, left]); g.fill();
        g.globalAlpha = 1;
      }
      previous = [left, right];
    }
    g.lineWidth = 1; g.strokeStyle = rgb(mix(mix(colors.sea[0], colors.crest, .15 + .3 * strength), GLOW, .6 * glow));
    for (const edge of edges) { path(g, edge, false); g.stroke(); }
    for (let k = 0; k < WAKE_FOAM; k++) {
      const phase = ((t * (.05 + speed * .006) + k * .382) % 1 + 1) % 1;
      const along = length * phase ** 1.6, d = OWN_STERN_M + along;
      const lateral = ((k * k * .618 + k * .29) % 1 - .5) * (OWN_BEAM_M + along * .04);
      const [x, y] = seaPoint(w, stern + Math.atan2(lateral, d) / RAD, d, eye);
      const half = Math.max(1, w.pxPerDeg * Math.atan2(3, d) / RAD);
      line(g, [x - half, y], [x + half, y], rgb(mix(foam, colors.sea[0], .2 + .8 * phase)));
    }
  }
  for (const side of [-1, 1]) {
    const points = [];
    for (let i = 1; i < 16; i++) {
      const run = 20 * 1.45 ** i, ahead = -(OWN_STERN_M + run * Math.cos(KELVIN_DEG * RAD));
      const lateral = side * (OWN_BEAM_M / 2 + run * Math.sin(KELVIN_DEG * RAD));
      const bearing = course + Math.atan2(lateral, ahead) / RAD;
      if (w.visible(bearing, 2)) points.push(seaPoint(w, bearing, Math.hypot(ahead, lateral), eye));
    }
    if (points.length >= 2) {
      g.lineWidth = 1; g.strokeStyle = rgb(mix(colors.crest, colors.sea[0], .5 - .3 * strength));
      path(g, points, false); g.stroke();
    }
  }
  if (seaY(w, course, OWN_BOW_M, eye) > w.height && w.visible(course, 30)) {
    const band = w.height * (.08 + .14 * strength), grow = w.width / 400, spread = Math.min(26, .45 * fov);
    for (let k = 0; k < BOW_SPRAY; k++) {
      const side = k % 2 ? -1 : 1, phase = ((t * (.3 + speed * .025) + k * .382) % 1 + 1) % 1;
      const lift = Math.sin(Math.PI * phase) * (.4 + .6 * ((k * k * .618) % 1));
      const x = w.x(course + side * (.5 + spread * phase)), y = w.height - band * lift;
      const half = (3 + 8 * strength * (1 - phase)) * grow;
      line(g, [x - half, y], [x + half, y], rgb(mix(colors.crest, colors.sea[0], .15 + .7 * phase)), strength > .5 ? 2 : 1);
    }
  }
  for (const side of [-1, 1]) {
    const points = [];
    for (let i = 0; i < 12; i++) {
      const run = OWN_BOW_M * 1.6 * i / 11, ahead = OWN_BOW_M - run * Math.cos(28 * RAD);
      const lateral = side * (1 + run * Math.sin(28 * RAD)) + .6 * speed / 10 * Math.sin(t * 3.1 + i * .9 + side);
      const bearing = course + Math.atan2(lateral, ahead) / RAD;
      if (!w.visible(bearing, 4)) continue;
      const point = seaPoint(w, bearing, Math.hypot(ahead, lateral), eye);
      if (point[1] <= w.height + 40) points.push(point);
    }
    if (points.length >= 2) {
      g.lineWidth = Math.max(1, Math.min(4, Math.floor(1 + strength * w.height / 160)));
      g.strokeStyle = rgb(mix(foam, colors.crest, strength)); path(g, points, false); g.stroke();
    }
  }
  g.lineWidth = 1;
}

// The sea as a field of wave rows in perspective: a clean horizon with fine
// crests below it, toward the eye ever longer and higher waves, all moving
// with the swell (bearing space, so the field slides past as the view turns).
// The shaded sea of Tiefenkontakt (ocean.js, src/ui/ocean.py): the wave field
// hangs on the sea, so the own way streams it past the eye.
function drawShadedSea(g, w, sky, colors, v, t, haze, eye) {
  const way = v.way ?? null, speed = way ? (Number(way.speed_kn) || 0) * 1852 / 3600 : 0;
  const course = way ? (Number(way.course_deg) || 0) * RAD : 0;
  const [ownE, ownN] = flow(g.canvas ?? g, t, [speed * Math.sin(course), speed * Math.cos(course)]);
  drawOcean(g, w, sky, colors, {seaState: v.sea_state, visibility: v.visibility_nm, eye, ownE, ownN, t});
  if (way) drawWay(g, w, colors, way, t, haze);
}
// Lightning (src/world/thunder.py, src/ui/sight_scene.py draw_lightning):
// the state carries a strike's brightness and bearing while it flashes; the
// page holds each new strike for FLASH_MS of its own time so a 4 Hz state
// still shows it, with the same double flicker as the uConsole.
const FLASH_MS = 700;
const LIGHTNING = [200, 196, 255], BOLT = [238, 236, 255];
let strike = null;

function drawLightning(g, w, sky) {
  const now = performance.now(), level = Number(sky.lightning) || 0, bearing = Number(sky.lightning_bearing) || 0;
  if (level > .02 && (!strike || strike.bearing !== bearing)) strike = { bearing, level, at: now };
  if (!strike) return;
  const age = (now - strike.at) / 1000;
  if (age > FLASH_MS / 1000) { if (level <= .02) strike = null; return; }
  const flicker = age < .12 || (age > .22 && age < .3) ? 1 : .45;
  const light = strike.level * flicker * Math.sqrt(1 - age / (FLASH_MS / 1000));
  g.save(); g.globalCompositeOperation = "lighter";
  g.fillStyle = `rgba(${LIGHTNING.join(", ")}, ${(.3 * light).toFixed(3)})`; g.fillRect(0, 0, w.width, w.height);
  g.restore();
  if (!w.visible(strike.bearing, 0)) return;
  let x = w.x(strike.bearing), y = 0;
  const bottom = w.base(x), step = Math.max(6, bottom / 9), seed = Math.floor(strike.bearing * 100);
  const points = [[x, y]];
  for (let index = 1; y < bottom; index++) {
    y = Math.min(bottom, y + step);
    x += (((seed * (index * 7 + 3)) % 23) - 11) * w.width / 1200;
    points.push([x, y]);
  }
  const width = light > .5 ? 2 : 1, color = rgb(mix(LIGHTNING, BOLT, light));
  for (let index = 1; index < points.length; index++) line(g, points[index - 1], points[index], color, width);
  g.lineWidth = 1;
}

function drawWeather(g, w, sky, colors, visibility, t, haze) {
  if (visibility < 3) {
    const band = w.height * (.1 + .25 * (1 - visibility / 3)), y0 = w.horizon - band / 2;
    const gradient = g.createLinearGradient(0, y0, 0, y0 + band), haze0 = colors.haze.join(", ");
    gradient.addColorStop(0, `rgba(${haze0}, 0)`); gradient.addColorStop(.5, `rgba(${haze0}, .67)`); gradient.addColorStop(1, `rgba(${haze0}, 0)`);
    g.fillStyle = gradient; g.fillRect(0, y0, w.width, band);
  }
  drawLightning(g, w, sky);
  if (sky.precipitation === "none" || sky.intensity <= 0) return;
  // A thunderstorm pours: up to 60 % more streaks.
  sky = { ...sky, intensity: sky.intensity * (1 + .6 * (Number(sky.storm) || 0)) };
  const lateral = Math.sin((sky.wind_from_deg - w.los + 180) * Math.PI / 180);
  const color = rgb(mix(mix([70, 96, 104], [196, 208, 212], sky.light), colors.haze, haze * .3));
  const mod = (value, size) => ((value % size) + size) % size;
  if (sky.precipitation === "rain") {
    const length = 10 + 10 * sky.intensity;
    for (let index = 0; index < Math.floor(70 * sky.intensity); index++) {
      const x = mod(index * 97 + t * 40 * lateral, w.width), y = mod(index * 53 + t * 420, w.height);
      line(g, [x, y], [x + lateral * length * .4, y + length], color);
    }
  } else {
    g.fillStyle = color;
    for (let index = 0; index < Math.floor(60 * sky.intensity); index++) {
      const x = mod(index * 97 + 13 * Math.sin(t * .7 + index) + t * 22 * lateral, w.width);
      const y = mod(index * 53 + t * (26 + (index % 5) * 6), w.height), size = index % 3 === 0 ? 3 : 2;
      g.fillRect(x, y, size, size);
    }
  }
}

// Water on the periscope's head glass (src/ui/sight_scene.py lens_water):
// [cover 0..1 from below, drops 0..1].  ``raisedS``: seconds since the head
// came out of the water (null when unknown or long ago).
const RAISE_DRAIN_S = 1.4, WASH_SEA_MIN = 3.5, DROPS_S = 2.5, DROP_COUNT = 18;
const WATER_COLOR = [12, 58, 66], WATER_FOAM = [150, 214, 208];
export function lensWater(t, seaState, raisedS = null) {
  let cover = 0, drops = 0;
  if (Number.isFinite(raisedS) && raisedS >= 0) {
    cover = clamp(1 - raisedS / RAISE_DRAIN_S);
    drops = raisedS < RAISE_DRAIN_S + DROPS_S ? clamp(1 - (raisedS - RAISE_DRAIN_S) / DROPS_S) : 0;
  }
  if (seaState >= WASH_SEA_MIN) {
    const period = 5 + seaState, phase = t / period, wave = Math.floor(phase);
    const amp = .75 + .25 * Math.sin(wave * 1.7), crest = amp * Math.sin(2 * Math.PI * phase);
    const threshold = 1.1 - .12 * seaState;
    cover = Math.max(cover, clamp((crest - threshold) / Math.max(.05, 1 - threshold)) * .9);
    const since = (phase - wave - .25) * period;
    if (amp > threshold && since >= 0 && since <= DROPS_S + period * .25)
      drops = Math.max(drops, clamp(1 - Math.max(0, since - period * .25) / DROPS_S));
  }
  return [cover, drops];
}

function drawLensWater(g, width, height, cover, drops, t) {
  if (cover > .01) {
    const top = height - cover * height, step = Math.max(6, Math.floor(width / 60));
    g.beginPath(); g.moveTo(0, height);
    const edge = [];
    for (let x = 0; x <= width + step; x += step) {
      const px = Math.min(x, width);
      edge.push([px, top + 5 * Math.sin(px / 37 + t * 3.1) + 3 * Math.sin(px / 11 - t * 5.3)]);
    }
    for (const [x, y] of edge) g.lineTo(x, y);
    g.lineTo(width, height); g.closePath(); g.fillStyle = rgb(WATER_COLOR); g.fill();
    g.strokeStyle = rgb(WATER_FOAM); g.lineWidth = 2; g.beginPath();
    edge.forEach(([x, y], index) => index ? g.lineTo(x, y) : g.moveTo(x, y)); g.stroke();
  }
  if (drops > .02) {
    const count = Math.floor(DROP_COUNT * drops);
    for (let index = 0; index < count; index++) {
      const fx = (index * .5698 + .13) % 1, fy = (index * .7549 + .29) % 1;
      const x = fx * width, y = (fy * .85 + .06 * (1 - drops)) * height;
      const radius = Math.max(2, Math.floor((3 + (index % 4) * 2) * width / 600 + 1));
      g.strokeStyle = rgb(WATER_FOAM); g.lineWidth = 1; g.beginPath(); g.arc(x, y, radius, 0, Math.PI * 2); g.stroke();
      g.fillStyle = "rgb(230, 250, 250)"; g.beginPath(); g.arc(x - radius * .4, y - radius * .4, Math.max(1, Math.floor(radius / 3)), 0, Math.PI * 2); g.fill();
    }
  }
}

// Bow wave and wake of a made-out ship (src/ui/ship_way.py): ``level`` 0..1
// is the white water the eye sees, ``aob`` places bow and stern.
const WAY_FOAM = [236, 246, 246];
function drawShipWay(g, cx, base, width, aob, level, t, foam, sea) {
  if (!Number.isFinite(level) || level < .05 || width < 8 || !Number.isFinite(aob)) return;
  const side = Math.sin(aob * Math.PI / 180), toward = Math.cos(aob * Math.PI / 180);
  const face = side >= 0 ? 1 : -1, half = width / 2 * Math.max(.12, Math.abs(side));
  const bowX = cx + face * half, sternX = cx - face * half;
  const white = mix(sea, foam, .55 + .45 * level);
  const rise = Math.max(1.5, width * .07 * level), spread = width * (.05 + .1 * level) * (.5 + .5 * Math.abs(toward));
  for (let k = 0; k < 3; k += 1) {
    const phase = (t * (.8 + 1.4 * level) + k * .33) % 1, reach = spread * (.4 + .6 * phase), lift = rise * (1 - phase);
    for (const dir of [-1, 1]) line(g, [bowX, base - lift * .3], [bowX + dir * reach, base - lift * (.2 + .8 * (1 - phase))], rgb(white));
  }
  line(g, [bowX - face * width * .03, base], [bowX + face * spread * .5, base], rgb(white), level > .5 ? 2 : 1);
  line(g, [bowX, base], [bowX + (sternX - bowX) * (.3 + .4 * level), base], rgb(mix(sea, foam, .3 + .5 * level)));
  const length = width * (.3 + 1.4 * level), across = Math.max(.15, Math.abs(side)), steps = 7;
  for (let i = 0; i < steps; i += 1) {
    const f = i / steps, x0 = sternX - face * length * f * across, x1 = sternX - face * length * (i + 1) / steps * across;
    const band = 1 + 4 * level * f, color = rgb(mix(white, sea, .1 + .8 * f));
    if (toward < 0) line(g, [x0, base + band * .3], [x1, base + band + 2 * level * -toward * (i + 1)], color);
    else line(g, [x0, base + 1 + band / 2], [x1, base + 1 + band / 2], color, Math.max(1, Math.floor(band)));
  }
}

// The optics' rim (src/ui/sight_scene.py eyepiece_mask): two overlapping
// round fields for binoculars, a rounded field for the periscope.
const EYEPIECE_SOFT = .07, EYEPIECE_RIM = [4, 10, 14], eyepieceMasks = new Map();
function eyepieceMask(width, height, kind) {
  const w = Math.max(2, Math.round(width)), h = Math.max(2, Math.round(height)), key = `${w}x${h}:${kind}`;
  let mask = eyepieceMasks.get(key);
  if (mask) return mask;
  mask = document.createElement("canvas");
  mask.width = w; mask.height = h;
  const context = mask.getContext("2d"), image = context.createImageData(w, h), data = image.data;
  const r = h / 2, centers = [Math.min(w / 2, r), Math.max(w / 2, w - r)], soft = EYEPIECE_SOFT * 2;
  for (let y = 0; y < h; y += 1) {
    for (let x = 0; x < w; x += 1) {
      const px = x + .5, py = y + .5;
      const d = kind === "binoculars"
        ? Math.min(Math.hypot(px - centers[0], py - r), Math.hypot(px - centers[1], py - r)) / r
        : ((Math.abs(px - w / 2) / (w / 2)) ** 6 + (Math.abs(py - r) / r) ** 6) ** (1 / 6);
      const index = (y * w + x) * 4;
      data[index] = EYEPIECE_RIM[0]; data[index + 1] = EYEPIECE_RIM[1]; data[index + 2] = EYEPIECE_RIM[2];
      data[index + 3] = Math.round(clamp((d - (1 - soft)) / soft) * 255);
    }
  }
  context.putImageData(image, 0, 0);
  if (eyepieceMasks.size > 6) eyepieceMasks.delete(eyepieceMasks.keys().next().value);
  eyepieceMasks.set(key, mask);
  return mask;
}
function drawEyepiece(g, width, height, kind) {
  if (kind === "binoculars" || kind === "scope") g.drawImage(eyepieceMask(width, height, kind), 0, 0, width, height);
}

function drawFrame(g, width, height) {
  g.strokeStyle = rgb(mix(FRAME, [0, 0, 0], .4)); g.lineWidth = 1; g.strokeRect(.5, .5, width - 1, height - 1);
  const size = Math.max(6, Math.min(18, width / 6, height / 4));
  g.strokeStyle = rgb(FRAME); g.lineWidth = 2;
  for (const [x, y, dx, dy] of [[4, 4, 1, 1], [width - 4, 4, -1, 1], [4, height - 4, 1, -1], [width - 4, height - 4, -1, -1]]) {
    g.beginPath(); g.moveTo(x + dx * size, y); g.lineTo(x, y); g.lineTo(x, y + dy * size); g.stroke();
  }
}

// Wind rose: north up, the arrow blows from where the wind comes.
function drawWindRose(g, height, colors, windFromDeg) {
  const radius = Math.max(8, Math.min(20, Math.floor(height / 5))), cx = radius + 7, cy = radius + 7;
  const angle = windFromDeg * Math.PI / 180, dx = Math.sin(angle), dy = -Math.cos(angle);
  g.fillStyle = rgb(mix(colors.sky[0], [0, 0, 0], .5)); g.beginPath(); g.arc(cx, cy, radius, 0, Math.PI * 2); g.fill();
  g.strokeStyle = rgb(FRAME); g.lineWidth = 1; g.stroke();
  const head = [cx - dx * (radius - 4), cy - dy * (radius - 4)], barb = Math.max(5, radius / 3);
  line(g, [cx + dx * (radius - 3), cy + dy * (radius - 3)], head, rgb(WIND_ARROW), 2);
  g.fillStyle = rgb(WIND_ARROW); g.beginPath(); g.moveTo(...head);
  g.lineTo(head[0] + dx * barb * 1.6 - dy * barb * .6, head[1] + dy * barb * 1.6 + dx * barb * .6);
  g.lineTo(head[0] + dx * barb * 1.6 + dy * barb * .6, head[1] + dy * barb * 1.6 - dx * barb * .6); g.fill();
}

// One eyepiece picture.  ``v``: bearing (line of sight), fov_deg,
// horizon_offset, horizon_tilt, visibility_nm, sea_state, sky, outlines
// ([{bearing, span_deg, cls, stale, lights, elevation_deg, aob_deg, model, way, range_nm}];
// a ranged ship floats as far below the horizon as the eye ``eye_m`` (or the
// way's, else the bridge lookout's 18 m) sees its waterline, nearer ones in front), the events the eye
// sees happen (``events``, src/core/sight_events.py) and an optional window_deg crosshair;
// no_scale hides the bearing scale, wind_rose_deg draws the weather
// instrument's wind rose in the top left corner; way ({speed_kn, course_deg,
// eye_m, hull}) is the own way through the water (wave stream, bow wave, wake).
export function drawSightView(g, width, height, v, t, labelFont = "11px ui-monospace, monospace") {
  const w = view(width, height, v), haze = 1 - clamp(v.visibility_nm / VISIBILITY_MAX_NM);
  const sky = v.sky, colors = palette(sky, haze);
  const lit = sky.light < .45;
  const aloft = (row) => Number.isFinite(row.elevation_deg);
  const eye = Number.isFinite(v.eye_m) ? v.eye_m : v.way?.eye_m ?? 18;
  const drawRows = (rows) => {
    for (const row of rows) {
      if (!w.visible(row.bearing, row.span_deg / 2)) continue;
      const cx = w.x(row.bearing), fade = row.stale ? .55 : haze * .6;
      // Aircraft hang in the still sky at their elevation, behind the clouds.
      const base = !aloft(row) ? w.base(cx) + waterlineDropDeg(rowRange(row) * 1852, eye) * w.pxPerDeg : row.elevation_deg < LOW_AIR_DEG ? w.base(cx) - row.elevation_deg * w.pxPerDeg
        : w.skyY - row.elevation_deg * w.pxPerDeg;
      const span = Math.min(width, Math.max(3, row.span_deg * w.pxPerDeg));
      if (!aloft(row) && !row.stale) drawShipWay(g, cx, base, span, row.aob_deg ?? null, row.way ?? null, t, mix(WAY_FOAM, colors.haze, haze * .6), colors.sea[0]);
      drawProfile(g, row.cls, cx, base, span, mix(colors.steel, colors.haze, fade),
        {t, rim: mix(colors.rim, colors.haze, fade), lights: lit && !row.stale ? WINDOW_LIGHT : null,
          nav: row.stale ? null : row.lights ?? null, aloft: aloft(row), aob: row.stale ? null : row.aob_deg ?? null, model: row.stale ? null : row.model ?? null});
    }
  };
  // Aircraft high over the sea horizon hang in the sky behind the clouds; a low one (hovering,
  // the own helicopter close aboard or over its deck) stands in front of the sea.
  const high = (row) => aloft(row) && row.elevation_deg >= LOW_AIR_DEG;
  const airborne = v.outlines.filter(high);
  drawSky(g, w, sky, colors, t, haze, airborne.length ? () => drawRows(airborne) : null);
  drawShadedSea(g, w, sky, colors, v, t, haze, eye);
  drawLand(g, w, v, colors, sky.light);
  foamGlow = colors.glow;
  // Back to front: the farthest first, so a nearer ship hides a farther one.
  drawRows(v.outlines.filter((row) => !high(row)).sort((a, b) => (rowRange(a) === rowRange(b) ? 0 : rowRange(b) - rowRange(a))));
  foamGlow = 0;
  if (Array.isArray(v.events) && v.events.length) drawSightEvents(g, w, colors, sky, v.events, haze, t);
  drawWeather(g, w, sky, colors, v.visibility_nm, t, haze);
  // A periscope's head glass: water running off after raising, waves washing over.
  if (v.lens) drawLensWater(g, width, height, ...lensWater(t, v.sea_state, v.lens.raised_s ?? null), t);
  if (v.eyepiece) drawEyepiece(g, width, height, v.eyepiece);
  if (Number.isFinite(v.wind_rose_deg)) drawWindRose(g, height, colors, v.wind_rose_deg);
  const labelStep = [10, 30, 45, 90].find((step) => step * w.pxPerDeg >= SCALE_LABEL_MIN_PX) ?? 90;
  const first = Math.floor((v.bearing - v.fov_deg / 2) / 5) * 5;
  g.font = labelFont; g.textAlign = "center"; g.textBaseline = "top";
  for (let tick = first; !v.no_scale && tick <= first + v.fov_deg + 10; tick += 5) {
    const off = wrap(tick - v.bearing);
    if (Math.abs(off) > v.fov_deg / 2) continue;
    const tx = (off + v.fov_deg / 2) * w.pxPerDeg, major = ((tick % labelStep) + labelStep) % labelStep === 0;
    if (!major && tick % 10 && 5 * w.pxPerDeg < 6) continue;
    line(g, [tx, 0], [tx, major ? 10 : 5], SCALE());
    if (major && height >= 40) { g.fillStyle = SCALE(); g.fillText(String(((tick % 360) + 360) % 360).padStart(3, "0"), tx, 12); }
  }
  if (Number.isFinite(v.window_deg)) {
    const window = v.window_deg * w.pxPerDeg, cx = width / 2, cy = height / 2;
    line(g, [cx, 26], [cx, height], CROSSHAIR());
    line(g, [cx - window, cy], [cx + window, cy], CROSSHAIR());
    for (const mark of [-1, 1]) line(g, [cx + mark * window, cy - 4], [cx + mark * window, cy + 4], CROSSHAIR());
  }
  if (height >= 60) {
    g.fillStyle = CROSSHAIR(); g.textBaseline = "bottom";
    if (v.stabilized && v.stab_label) { g.textAlign = "left"; g.fillText(v.stab_label, 10, height - 8); }
    if (v.optics_label) { g.textAlign = "right"; g.fillText(v.optics_label, width - 10, height - 8); }
  }
  drawFrame(g, width, height);
}
