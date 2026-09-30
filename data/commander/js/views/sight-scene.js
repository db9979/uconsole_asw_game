// The start screen's look for the browser eyepieces (periscope, binoculars):
// the same picture as src/ui/sight_scene.py and src/ui/horizon.py on the
// uConsole.  Sky, stars, sun or moon, clouds, the sea in motion, silhouettes
// in steel with a lit rim, rain, snow or fog, the bearing scale and the
// corner brackets.  Display only: every value comes from the detached state
// (the view's ``sky`` block and outlines); the phase is the wall clock.
import { drawInScene } from "./model-view.js";
import { DETAIL_MIN_PX, FOAM, NAV_LIGHT, PROFILES } from "./silhouette-profiles.js";
import { drawSightEvents } from "./sight-events.js";

const SKY_NIGHT = [[3, 7, 16], [20, 44, 62]], SKY_DAY = [[34, 88, 118], [138, 176, 182]], SKY_DUSK = [[24, 30, 60], [204, 128, 78]];
const SEA_NIGHT = [[10, 44, 58], [2, 9, 15]], SEA_DAY = [[24, 78, 92], [6, 34, 46]], SEA_DUSK = [[44, 50, 66], [8, 14, 26]];
const OVERCAST_DAY = [108, 120, 126], OVERCAST_NIGHT = [18, 24, 30];
const HAZE_DAY = [150, 160, 165], HAZE_NIGHT = [34, 44, 50];
const MOON = [214, 222, 206], MOON_DARK = [26, 34, 42], SUN_DAY = [255, 244, 210], SUN_DUSK = [255, 178, 96];
const STEEL_NIGHT = [19, 36, 46], STEEL_DAY = [44, 56, 64], RIM_NIGHT = [84, 150, 158], RIM_DAY = [170, 196, 200];
const WINDOW_LIGHT = [250, 205, 120], FRAME = [40, 96, 90], WIND_ARROW = [120, 214, 180];
const SCALE = "rgb(170, 232, 208)", CROSSHAIR = "rgb(120, 214, 180)";
const STABILIZED_RESIDUAL = .12;   // src/ui/horizon.py
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
    cloudRim: mix(mix([70, 96, 108], [238, 242, 242], light), [250, 190, 130], dusk * .7)};
}

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
  const left = cx - width / 2, foam = rgb(FOAM);
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
    const bow = frame.point(.03, 0), stern = frame.point(1, 0), foam = rgb(FOAM);
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

// The sea as seen (src/ui/sight_scene.py sea_aspect): head 1 into the sea,
// -1 down-sea; cross +1 when the waves run left to right.
export function seaAspect(windFromDeg, lineOfSight) {
  const angle = (windFromDeg - lineOfSight) * Math.PI / 180;
  return [Math.cos(angle), -Math.sin(angle)];
}

// Rows of waves between the horizon and the bottom (src/ui/sight_scene.py).
const SEA_ROWS = 18;
// Own way through the water (src/ui/sight_scene.py): rows per second and knot
// toward the eye looking ahead, sideways stream per knot looking abeam; the
// frigate's bow and stern from the bridge lookout, her beam and the Kelvin angle.
const WAY_ROWS_PER_KN = .04, WAY_SIDE_PER_KN = .15;
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

// The picture row of a point on the sea ``distance`` metres from an eye ``eye`` metres up.
function seaY(w, bearing, distance, eye) {
  const below = (Math.atan2(eye, Math.max(1, distance)) - Math.sqrt(2 * eye / 7.3e6)) / RAD;
  return w.base(w.x(bearing)) + Math.max(0, below) * w.pxPerDeg;
}
const seaPoint = (w, bearing, distance, eye) => [w.x(bearing), seaY(w, bearing, distance, eye)];

// Bow wave and wake of the own ship in true perspective from the eye: the
// wake runs astern between the arms of the Kelvin wave, the bow wave curls
// out from the stem (tilt down to see it; from further up only its spray).
function drawWay(g, w, colors, way, t, haze) {
  const speed = Number(way.speed_kn) || 0;
  if (speed < 1 || way.hull === false) return;
  const course = way.course_deg, eye = way.eye_m ?? 18;
  const strength = clamp(speed / 20) * (1 - haze * .7), foam = mix(colors.sea[0], colors.crest, .35 + .55 * strength);
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
        g.fillStyle = rgb(mix(colors.sea[0], colors.wave, (.04 + .1 * strength) * (1 - i / steps)));
        path(g, [previous[0], previous[1], right, left]); g.fill();
      }
      previous = [left, right];
    }
    g.lineWidth = 1; g.strokeStyle = rgb(mix(colors.sea[0], colors.crest, .15 + .3 * strength));
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
function drawSea(g, w, sky, colors, seaState, t, haze, way = null) {
  const step = Math.max(4, Math.floor(w.width / 90));
  const [head, cross] = seaAspect(sky.wind_from_deg, w.los), along = Math.abs(head);
  const anchor = w.los * w.pxPerDeg;
  const top = Math.min(w.base(0), w.base(w.width));
  const gradient = g.createLinearGradient(0, top, 0, w.height);
  gradient.addColorStop(0, rgb(colors.sea[0])); gradient.addColorStop(1, rgb(colors.sea[1]));
  g.fillStyle = gradient; path(g, [[0, w.base(0)], [w.width, w.base(w.width)], [w.width, w.height], [0, w.height]]); g.fill();
  const below = Math.max(1, w.height - w.horizon), nearAmp = (1.2 + .9 * seaState) * w.height / 280;
  // Into or down the sea the rows come at the eye or run away (new rows are
  // born at the horizon); across it they run sideways.  The own way adds the
  // water streaming past: toward the eye ahead, away astern, bow to stern abeam.
  const speed = way ? Number(way.speed_kn) || 0 : 0, rel = way ? (w.los - way.course_deg) * RAD : 0;
  const [cycles, side] = flow(g, t, [.35 * head + WAY_ROWS_PER_KN * speed * Math.cos(rel),
    cross + WAY_SIDE_PER_KN * speed * Math.sin(rel)]);
  const roll = ((cycles % 1) + 1) % 1, born = Math.floor(cycles);
  const trough = mix(colors.sea[0], colors.sea[1], .45);
  for (let index = 0; index <= SEA_ROWS; index++) {
    const f = (index + roll) / SEA_ROWS;
    if (f > 1) continue;
    const depth = below * f ** 1.9;
    if (depth < 1) continue;
    const near = depth / below, n = index - born;
    const amp = Math.max(.35, nearAmp * near), wavelength = (10 + 150 * near) * (.45 + .9 * along);
    const k = 2 * Math.PI / wavelength, drift = side * (4 + 40 * near), phase = n * 1.7 + t * 1.4 * (1 - along);
    const points = [];
    for (let x = -step; x < w.width + step; x += step) {
      const u = (x + anchor - drift) * k + phase;
      points.push([x, w.base(x) + depth - amp * (Math.sin(u) + .35 * Math.sin(2.1 * u + n))]);
    }
    let light = mix(mix(colors.sea[0], colors.wave, .35 + .65 * near), colors.haze, haze * (1 - near) * .6);
    if (head < 0) light = mix(light, colors.sea[1], .35 * -head);   // down-sea: the waves' backs
    const width = near > .55 && w.height >= 200 ? 2 : 1;
    g.lineWidth = width;
    if (near > .12) {
      g.strokeStyle = rgb(mix(trough, colors.sea[1], f * .9));
      path(g, points.map(([x, y]) => [x, y + Math.max(1, amp * .8)]), false); g.stroke();
    }
    g.strokeStyle = rgb(light); path(g, points, false); g.stroke();
    if (seaState >= 4 && near > .08) {
      // White caps on the highest crests.
      const half = Math.max(1, wavelength * .08), every = Math.max(2, 9 - Math.floor(seaState));
      for (let i = 1; i < points.length - 1; i++) {
        const [x, y] = points[i];
        if (y < points[i - 1][1] && y <= points[i + 1][1] && (((i * 7 + n * 3) % every) + every) % every === 0)
          line(g, [x - half, y], [x + half, y], rgb(colors.crest), width);
      }
    }
  }
  g.lineWidth = 1;
  line(g, [0, w.base(0)], [w.width, w.base(w.width)], rgb(mix(colors.crest, colors.haze, .4)));
  if (way) drawWay(g, w, colors, way, t, haze);
  let strength = 0, bearing = 0, glint = [150, 170, 170];
  if (sky.light < .5 && sky.moon_alt_deg > 0) { strength = sky.moon_illumination * (1 - sky.light * 2); bearing = sky.moon_bearing; }
  else if (sky.light >= .5 && sky.sun_alt_deg > -1) { strength = .8; bearing = sky.sun_bearing; glint = mix([226, 236, 236], SUN_DUSK, sky.dusk); }
  strength *= (1 - clamp((sky.cloud - .5) * 2)) * (1 - haze);
  if (strength > .1 && w.visible(bearing, 6)) {
    const cx = w.x(bearing), color = rgb(mix(colors.sea[0], glint, strength));
    for (let index = 0; index < 14; index++) {
      const shimmer = Math.sin(t * 2.4 + index * 1.7);
      if (shimmer < -.2) continue;
      const y = w.base(cx) + 4 + index * index * .9;
      if (y > w.height) break;
      const half = (4 + index * 2.5 * (.5 + .5 * shimmer)) * (w.width / 600 + .4);
      line(g, [cx - half, y], [cx + half, y], color);
    }
  }
}

function drawWeather(g, w, sky, colors, visibility, t, haze) {
  if (visibility < 3) {
    const band = w.height * (.1 + .25 * (1 - visibility / 3)), y0 = w.horizon - band / 2;
    const gradient = g.createLinearGradient(0, y0, 0, y0 + band), haze0 = colors.haze.join(", ");
    gradient.addColorStop(0, `rgba(${haze0}, 0)`); gradient.addColorStop(.5, `rgba(${haze0}, .67)`); gradient.addColorStop(1, `rgba(${haze0}, 0)`);
    g.fillStyle = gradient; g.fillRect(0, y0, w.width, band);
  }
  if (sky.precipitation === "none" || sky.intensity <= 0) return;
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
// ([{bearing, span_deg, cls, stale, lights, elevation_deg, aob_deg, model}]), the events the eye
// sees happen (``events``, src/core/sight_events.py) and an optional window_deg crosshair;
// no_scale hides the bearing scale, wind_rose_deg draws the weather
// instrument's wind rose in the top left corner; way ({speed_kn, course_deg,
// eye_m, hull}) is the own way through the water (wave stream, bow wave, wake).
export function drawSightView(g, width, height, v, t, labelFont = "11px ui-monospace, monospace") {
  const w = view(width, height, v), haze = 1 - clamp(v.visibility_nm / VISIBILITY_MAX_NM);
  const sky = v.sky, colors = palette(sky, haze);
  const lit = sky.light < .45;
  const aloft = (row) => Number.isFinite(row.elevation_deg);
  const drawRows = (rows) => {
    for (const row of rows) {
      if (!w.visible(row.bearing, row.span_deg / 2)) continue;
      const cx = w.x(row.bearing), fade = row.stale ? .55 : haze * .6;
      // Aircraft hang in the still sky at their elevation, behind the clouds.
      const base = aloft(row) ? w.skyY - row.elevation_deg * w.pxPerDeg : w.base(cx);
      drawProfile(g, row.cls, cx, base, Math.min(width, Math.max(3, row.span_deg * w.pxPerDeg)), mix(colors.steel, colors.haze, fade),
        {t, rim: mix(colors.rim, colors.haze, fade), lights: lit && !row.stale ? WINDOW_LIGHT : null,
          nav: row.stale ? null : row.lights ?? null, aloft: aloft(row), aob: row.stale ? null : row.aob_deg ?? null, model: row.stale ? null : row.model ?? null});
    }
  };
  const airborne = v.outlines.filter(aloft);
  drawSky(g, w, sky, colors, t, haze, airborne.length ? () => drawRows(airborne) : null);
  drawSea(g, w, sky, colors, v.sea_state, t, haze, v.way ?? null);
  drawRows(v.outlines.filter((row) => !aloft(row)));
  if (Array.isArray(v.events) && v.events.length) drawSightEvents(g, w, colors, sky, v.events, haze, t);
  drawWeather(g, w, sky, colors, v.visibility_nm, t, haze);
  if (Number.isFinite(v.wind_rose_deg)) drawWindRose(g, height, colors, v.wind_rose_deg);
  const labelStep = [10, 30, 45, 90].find((step) => step * w.pxPerDeg >= SCALE_LABEL_MIN_PX) ?? 90;
  const first = Math.floor((v.bearing - v.fov_deg / 2) / 5) * 5;
  g.font = labelFont; g.textAlign = "center"; g.textBaseline = "top";
  for (let tick = first; !v.no_scale && tick <= first + v.fov_deg + 10; tick += 5) {
    const off = wrap(tick - v.bearing);
    if (Math.abs(off) > v.fov_deg / 2) continue;
    const tx = (off + v.fov_deg / 2) * w.pxPerDeg, major = ((tick % labelStep) + labelStep) % labelStep === 0;
    if (!major && tick % 10 && 5 * w.pxPerDeg < 6) continue;
    line(g, [tx, 0], [tx, major ? 10 : 5], SCALE);
    if (major && height >= 40) { g.fillStyle = SCALE; g.fillText(String(((tick % 360) + 360) % 360).padStart(3, "0"), tx, 12); }
  }
  if (Number.isFinite(v.window_deg)) {
    const window = v.window_deg * w.pxPerDeg, cx = width / 2, cy = height / 2;
    line(g, [cx, 26], [cx, height], CROSSHAIR);
    line(g, [cx - window, cy], [cx + window, cy], CROSSHAIR);
    for (const mark of [-1, 1]) line(g, [cx + mark * window, cy - 4], [cx + mark * window, cy + 4], CROSSHAIR);
  }
  if (height >= 60) {
    g.fillStyle = CROSSHAIR; g.textBaseline = "bottom";
    if (v.stabilized && v.stab_label) { g.textAlign = "left"; g.fillText(v.stab_label, 10, height - 8); }
    if (v.optics_label) { g.textAlign = "right"; g.fillText(v.optics_label, width - 10, height - 8); }
  }
  drawFrame(g, width, height);
}
