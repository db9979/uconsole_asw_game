// Water columns, fireballs, fire and smoke and sinking ships in the browser
// eyepieces: the same pictures as src/ui/sight_events_view.py.  Each row
// (src/core/sight_events.py) carries its age at publication; between two
// publications it ages with the wall clock.  Display only.
const WHITE_WATER = [236, 244, 246], FLASH = [255, 236, 170], FIRE = [255, 150, 44], FIRE_CORE = [255, 226, 120];
const SMOKE_DAY = [58, 60, 62], SMOKE_NIGHT = [16, 18, 22], HULL_DARK = [28, 34, 40];
const SMOKE_PUFFS = 14, COLUMN_PUFFS = 11;
const received = new WeakMap();

const clamp = (value, low = 0, high = 1) => Math.max(low, Math.min(high, value));
const mix = (a, b, k) => a.map((value, index) => Math.round(value + (b[index] - value) * clamp(k)));
const rgb = (c) => `rgb(${c[0]}, ${c[1]}, ${c[2]})`;

function px(w, metres, rangeNm) {
  return w.pxPerDeg * Math.atan2(metres, Math.max(30, rangeNm * 1852)) * 180 / Math.PI;
}

function disc(g, x, y, radius, color) {
  g.fillStyle = rgb(color); g.beginPath(); g.arc(x, y, Math.max(1, radius), 0, Math.PI * 2); g.fill();
}

function ellipse(g, x, y, rx, ry, color) {
  g.fillStyle = rgb(color); g.beginPath(); g.ellipse(x, y, Math.max(1, rx), Math.max(1, ry), 0, 0, Math.PI * 2); g.fill();
}

// ``w``: the eyepiece geometry of sight-scene.js; ``t``: the display clock.
export function drawSightEvents(g, w, colors, sky, events, haze, t) {
  const wall = performance.now();
  if (!received.has(events)) received.set(events, wall);
  const since = (wall - received.get(events)) / 1000;
  const night = sky.light < .35;
  const drift = Math.sin((sky.wind_from_deg + 180 - w.los) * Math.PI / 180);
  for (const row of [...events].sort((a, b) => b.range_nm - a.range_nm)) {
    const age = row.age_s + since;
    if (age < 0 || age > row.dur_s || !w.visible(row.bearing, 3)) continue;
    const x = w.x(row.bearing), base = w.base(x), fade = Math.min(1, haze * .7 + row.range_nm / 40);
    if (row.type === "column") column(g, w, colors, row, age, x, base, fade, night);
    else if (row.type === "blast") blast(g, w, colors, row, age, x, base, fade, night, drift);
    else if (row.type === "fire") fire(g, w, colors, row, x, base, fade, night, drift, t);
    else if (row.type === "sinking") sinking(g, w, colors, row, age, x, base, fade, night);
  }
}

function column(g, w, colors, row, age, x, base, fade, night) {
  const height = px(w, row.size_m, row.range_nm);
  if (height < 1) return;
  const rise = Math.min(1, age / 2), fall = Math.max(0, (age - 5) / 10);
  const top = height * rise * (1 - Math.min(1, fall) * .95), width = Math.max(2, height * .28);
  const water = mix(night ? [70, 86, 92] : WHITE_WATER, colors.haze, fade);
  const spray = mix(water, colors.sea[0], Math.min(1, age / row.dur_s * 1.4));
  if (age < .6 && night) disc(g, x, base - 1, width * (1.2 - age), mix(FLASH, colors.haze, fade));
  for (let k = 0; top > 1 && k < COLUMN_PUFFS; k++) {
    const f = k / (COLUMN_PUFFS - 1), wobble = Math.sin(k * 1.9 + age * 1.3) * width * .15 * f;
    disc(g, x + wobble, base - top * f, width * (.35 + .45 * f) * (1 + fall * .8), f < .2 ? spray : water);
  }
  const spread = width * (.8 + Math.min(3.5, age * .25));
  ellipse(g, x, base, spread, Math.max(1, spread * .12), spray);
}

function blast(g, w, colors, row, age, x, base, fade, night, drift) {
  const size = Math.max(2, px(w, row.size_m, row.range_nm));
  if (age < 3) {
    const k = age / 3;
    disc(g, x, base - size * .5, size * (.6 + k), mix(FIRE, colors.haze, fade * .6 + k * .4));
    disc(g, x, base - size * .5, size * .45 * (1 - k), mix(FIRE_CORE, FIRE, k));
  }
  const smoke = mix(night ? SMOKE_NIGHT : SMOKE_DAY, colors.haze, fade);
  for (let k = 0; k < 6; k++) {
    const f = Math.min(1, age / 14) * (.3 + k / 8);
    disc(g, x + drift * size * 2 * f, base - size * (.6 + 3 * f), size * (.5 + .9 * f), smoke);
  }
}

function fire(g, w, colors, row, x, base, fade, night, drift, t) {
  if (row.level <= .02) return;
  const hull = px(w, row.size_m, row.range_nm), plume = px(w, 180, row.range_nm) * (.4 + .6 * row.level);
  if (!night && plume >= 2) {
    const smoke = mix(SMOKE_DAY, colors.haze, fade);
    for (let k = 0; k < SMOKE_PUFFS; k++) {
      const f = ((t * .03 + k / SMOKE_PUFFS) % 1 + 1) % 1;
      disc(g, x + drift * plume * 1.4 * f ** 1.3 + Math.sin(k * 2.3) * hull * .05, base - plume * f - hull * .05,
        plume * (.06 + .22 * f), mix(smoke, colors.haze, f * .7));
    }
  }
  const flame = Math.max(1, hull * .06 * (.5 + row.level)), glow = mix(FIRE, colors.haze, fade * (night ? .3 : .6));
  for (let k = 0; k < 3; k++) {
    const flicker = .7 + .3 * Math.sin(t * (7 + k * 2.3) + k * 1.7);
    disc(g, x + (k - 1) * hull * .08, base - flame * .6, flame * flicker, glow);
  }
  if (night) disc(g, x, base - flame * .6, flame * .5, mix(FIRE_CORE, colors.haze, fade * .3));
}

const HULL_OUTLINE = [[-.5, 0], [-.46, 1.5], [-.1, 1], [.3, 1], [.32, 1.8], [.42, 1.8], [.44, 1], [.5, 1], [.5, 0]];

function sinking(g, w, colors, row, age, x, base, fade, night) {
  const length = px(w, row.size_m, row.range_nm);
  if (length < 2) return;
  const p = Math.min(1, age / (row.dur_s * .8)), tilt = (8 + 32 * Math.min(1, p * 1.5)) * Math.PI / 180;
  const height = length * .12, drop = (length * Math.sin(tilt) * .5 + height) * p * 1.3;
  if (p < 1) {
    g.save(); g.beginPath(); g.rect(0, 0, w.width, base); g.clip();
    g.fillStyle = rgb(mix(night ? [10, 14, 18] : HULL_DARK, colors.haze, fade)); g.beginPath();
    HULL_OUTLINE.forEach(([u, v], index) => {
      const hx = x + u * length * Math.cos(tilt) - v * height * Math.sin(tilt);
      const hy = base + drop - v * height + u * length * Math.sin(tilt);
      if (index) g.lineTo(hx, hy); else g.moveTo(hx, hy);
    });
    g.closePath(); g.fill(); g.restore();
  }
  const spread = length * (.3 + .5 * p);
  ellipse(g, x, base, spread, Math.max(1, spread * .05), mix(night ? [60, 76, 82] : WHITE_WATER, colors.sea[0], .3 + p * .5));
}
