// The start screen's look for the browser eyepieces (periscope, binoculars):
// the same picture as src/ui/sight_scene.py and src/ui/horizon.py on the
// uConsole.  Sky, stars, sun or moon, clouds, the sea in motion, silhouettes
// in steel with a lit rim, rain, snow or fog, the bearing scale and the
// corner brackets.  Display only: every value comes from the detached state
// (the view's ``sky`` block and outlines); the phase is the wall clock.
import { DETAIL_MIN_PX, FOAM, NAV_LIGHT, PROFILES } from "./silhouette-profiles.js";

const SKY_NIGHT = [[3, 7, 16], [20, 44, 62]], SKY_DAY = [[34, 88, 118], [138, 176, 182]], SKY_DUSK = [[24, 30, 60], [204, 128, 78]];
const SEA_NIGHT = [[10, 44, 58], [2, 9, 15]], SEA_DAY = [[24, 78, 92], [6, 34, 46]], SEA_DUSK = [[44, 50, 66], [8, 14, 26]];
const OVERCAST_DAY = [108, 120, 126], OVERCAST_NIGHT = [18, 24, 30];
const HAZE_DAY = [150, 160, 165], HAZE_NIGHT = [34, 44, 50];
const MOON = [214, 222, 206], MOON_DARK = [26, 34, 42], SUN_DAY = [255, 244, 210], SUN_DUSK = [255, 178, 96];
const STEEL_NIGHT = [19, 36, 46], STEEL_DAY = [44, 56, 64], RIM_NIGHT = [84, 150, 158], RIM_DAY = [170, 196, 200];
const WINDOW_LIGHT = [250, 205, 120], FRAME = [40, 96, 90];
const SCALE = "rgb(170, 232, 208)", CROSSHAIR = "rgb(120, 214, 180)";
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
function frameFor(cls, cx, base, width, t, facing = -1) {
  const profile = PROFILES[cls] || PROFILES.unknown;
  const lift = profile.hover ? width * (.25 + .02 * Math.sin(t * 1.3)) : 0;
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

function drawNavLights(g, cls, frame, width, code, t) {
  const aircraft = code.slice(5) === "AC";
  const nav = aircraft ? PROFILES.aircraft.nav : (PROFILES[cls] || PROFILES.merchant).nav || PROFILES.merchant.nav;
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

export function drawProfile(g, cls, cx, base, width, fill, {t = 0, rim = null, lights = null, nav = null} = {}) {
  width = Math.max(3, width);
  if (cls === "torpedo") {
    line(g, [cx - width / 2, base + 1], [cx + width / 2, base + 1], rgb(FOAM), Math.max(1, Math.min(3, width / 12)));
    return;
  }
  const facing = navFacing(nav);
  const profile = PROFILES[cls] || PROFILES.unknown, frame = frameFor(cls, cx, base, width, t, facing);
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
  const horizon = height / 2 + v.horizon_offset * (height / 260);
  const tilt = v.horizon_tilt;
  const skyH = Math.max(8, height / 2);  // the sky stays still: nominal horizon
  return {width, height, pxPerDeg, horizon, tilt, skyH, los: v.bearing,
    x: (bearing) => width / 2 + wrap(bearing - v.bearing) * pxPerDeg,
    base: (x) => horizon + Math.tan(tilt) * (x - width / 2),
    visible: (bearing, half = 0) => Math.abs(wrap(bearing - v.bearing)) <= v.fov_deg / 2 + half};
}

const bodyFraction = (alt) => .12 + .7 * clamp(alt / BODY_MAX_ALT_DEG);

function drawSky(g, w, sky, colors, t, haze) {
  const gradient = g.createLinearGradient(0, w.skyH + 40 - w.height, 0, w.skyH + 40);
  gradient.addColorStop(0, rgb(colors.sky[0])); gradient.addColorStop(1, rgb(colors.sky[1]));
  g.fillStyle = gradient; g.fillRect(0, 0, w.width, w.height);
  const stars = (1 - sky.light * 1.8) * (1 - sky.cloud) * (1 - haze);
  if (stars > .05) {
    for (const [bearing, alt, phase, speed, bright] of FIELD.stars) {
      if (!w.visible(bearing)) continue;
      const x = w.x(bearing), y = w.skyH - (.08 + .92 * alt) * w.skyH;
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
    const x = w.x(sky.sun_bearing), y = w.skyH - bodyFraction(sky.sun_alt_deg) * w.skyH;
    disc(x, y, mix(mix(SUN_DAY, SUN_DUSK, sky.dusk), colors.sky[1], 1 - cover), [[radius * 3, .85], [radius * 2, .7]]);
  }
  if (sky.light < .6 && sky.moon_alt_deg > 0 && sky.moon_illumination > .03 && cover > .05 && w.visible(sky.moon_bearing, 2)) {
    const x = w.x(sky.moon_bearing), y = w.skyH - bodyFraction(sky.moon_alt_deg) * w.skyH;
    disc(x, y, mix(MOON, colors.sky[1], (1 - cover) + haze * .5), [[radius * 4, .9], [radius * 3, .82], [radius * 2, .7]]);
    if (sky.moon_illumination < .97) {
      const shift = (sky.moon_waxing ? -1 : 1) * 2 * radius * sky.moon_illumination;
      g.save(); g.beginPath(); g.arc(x, y, radius + .5, 0, Math.PI * 2); g.clip();
      g.fillStyle = rgb(mix(MOON_DARK, colors.sky[1], .3)); g.beginPath(); g.arc(x + shift, y, radius, 0, Math.PI * 2); g.fill();
      g.restore();
    }
  }
  if (sky.cloud > .2 && haze <= .85) {
    const count = Math.floor(FIELD.clouds.length * clamp((sky.cloud - .15) / .85));
    const drift = t * .05 * (Math.sin((sky.wind_from_deg - w.los) * Math.PI / 180) > 0 ? 1 : -1);
    const moonlit = sky.light > .3 || (sky.moon_alt_deg > 0 && sky.moon_illumination > .3);
    const base = mix(colors.cloud, colors.haze, haze * .6), rim = mix(colors.cloudRim, colors.haze, haze * .6);
    for (const [start, alt, widthDeg, height, shade] of FIELD.clouds.slice(0, count)) {
      const bearing = start + drift;
      if (!w.visible(bearing, widthDeg)) continue;
      const x = w.x(bearing), y = w.skyH - alt * w.skyH, cw = widthDeg * w.pxPerDeg, ch = Math.max(4, height * w.skyH * 1.6);
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

function drawSea(g, w, sky, colors, seaState, t, haze) {
  const amp = .6 + .35 * seaState, step = Math.max(6, Math.floor(w.width / 60)), crest = [];
  const [head, cross] = seaAspect(sky.wind_from_deg, w.los);
  // The pattern lies on the sea (bearing space) and runs with the swell.
  const anchor = w.los * w.pxPerDeg, swell = cross * t * 14;
  for (let x = 0; x <= w.width + step; x += step) {
    crest.push([x, w.base(x) + amp * Math.sin((x + anchor - swell) * .045 + t * 1.6 * Math.abs(head)) +
      .6 * amp * Math.sin((x + anchor - swell) * .013 - t * .9)]);
  }
  const top = Math.min(w.base(0), w.base(w.width));
  const gradient = g.createLinearGradient(0, top, 0, w.height);
  gradient.addColorStop(0, rgb(colors.sea[0])); gradient.addColorStop(1, rgb(colors.sea[1]));
  g.fillStyle = gradient; path(g, [...crest, [w.width, w.height], [0, w.height]]); g.fill();
  // Into or down the sea long rows come at the eye or run away; across it
  // short crests run sideways and lean with the perspective.
  const rows = 9, below = w.height - w.horizon, along = Math.abs(head), roll = (((t * .12 * head) % 1) + 1) % 1;
  for (let index = 0; index <= rows; index++) {
    const row = index + roll, depth = below * (row / rows) ** 1.7;
    if (depth < 3 || row > rows) continue;
    const spacing = Math.floor(24 + row * 10), length = (6 + row * 3) * (.55 + 1.1 * along);
    const lean = cross * (1 + row * .7) * (1 - along);
    const offset = (((anchor + t * (6 + row * 3) * cross) % (2 * spacing)) + 2 * spacing) % (2 * spacing);
    let shade = mix(colors.wave, colors.sea[1], row / (rows + 3));
    if (head < 0) shade = mix(shade, colors.sea[1], .35 * -head);   // down-sea: the waves' backs
    for (let x = -2 * spacing; x < w.width; x += spacing) {
      if ((Math.floor(x / spacing) + index) % 2) continue;
      const x0 = x - offset, y0 = w.base(x0) + depth;
      line(g, [x0, y0], [x0 + length, y0 - lean], rgb(shade));
      if (seaState >= 4 && (Math.floor(x / spacing) * 7 + index) % 5 === 0) line(g, [x0 + 2, y0 - 1], [x0 + length - 2, y0 - 1 - lean], rgb(colors.crest));
    }
  }
  g.strokeStyle = rgb(colors.crest); g.lineWidth = 1; path(g, crest, false); g.stroke();
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

// One eyepiece picture.  ``v``: bearing (line of sight), fov_deg,
// horizon_offset, horizon_tilt, visibility_nm, sea_state, sky, outlines
// ([{bearing, span_deg, cls, stale, lights}]) and an optional window_deg crosshair.
export function drawSightView(g, width, height, v, t, labelFont = "11px ui-monospace, monospace") {
  const w = view(width, height, v), haze = 1 - clamp(v.visibility_nm / VISIBILITY_MAX_NM);
  const sky = v.sky, colors = palette(sky, haze);
  drawSky(g, w, sky, colors, t, haze);
  drawSea(g, w, sky, colors, v.sea_state, t, haze);
  const lit = sky.light < .45;
  for (const row of v.outlines) {
    if (!w.visible(row.bearing, row.span_deg / 2)) continue;
    const cx = w.x(row.bearing), fade = row.stale ? .55 : haze * .6;
    drawProfile(g, row.cls, cx, w.base(cx), Math.min(width, Math.max(3, row.span_deg * w.pxPerDeg)), mix(colors.steel, colors.haze, fade),
      {t, rim: mix(colors.rim, colors.haze, fade), lights: lit && !row.stale ? WINDOW_LIGHT : null,
        nav: row.stale ? null : row.lights ?? null});
  }
  drawWeather(g, w, sky, colors, v.visibility_nm, t, haze);
  const labelStep = [10, 30, 45, 90].find((step) => step * w.pxPerDeg >= SCALE_LABEL_MIN_PX) ?? 90;
  const first = Math.floor((v.bearing - v.fov_deg / 2) / 5) * 5;
  g.font = labelFont; g.textAlign = "center"; g.textBaseline = "top";
  for (let tick = first; tick <= first + v.fov_deg + 10; tick += 5) {
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
  drawFrame(g, width, height);
}
