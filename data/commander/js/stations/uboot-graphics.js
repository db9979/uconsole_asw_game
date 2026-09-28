import { finite, number, t } from "../core/format.js";
import { palette } from "../core/palette.js";
import { drawEmpty, visualContext } from "../views/visual-common.js";
import { drawSightView } from "../views/sight-scene.js";

// Boat instruments drawn from the boat's own picture only: its depth and
// orders, the charted bottom, the layer of its own BT measurement, and the
// bearings its own ESM and alarms measured.

function label(g, text, x, y, color, align = "left") {
  g.fillStyle = color; g.textAlign = align; g.textBaseline = "middle";
  g.fillText(text, x, y);
}

// Water column: surface, periscope depth, layer (after BT), ordered and safe
// depth, the seabed and the boat itself at its depth.
export function drawBoatDepth(id, payload) {
  const plot = visualContext(id);
  if (!plot) return;
  const {context: g, width, height} = plot, colors = palette();
  const nav = payload.navigation, presets = nav.depth_presets;
  const bottom = finite(nav.water_depth_m) ? nav.water_depth_m : null;
  const scaleMax = Math.max(100, bottom ?? 0, nav.crush_depth_m, nav.depth_m, nav.target_depth_m) * 1.06;
  const left = 46, right = Math.max(left + 60, width * .55), top = 14, bottom_px = height - 12;
  const y = (depth) => top + (bottom_px - top) * Math.max(0, Math.min(1, depth / scaleMax));
  const water = g.createLinearGradient(0, top, 0, bottom_px);
  water.addColorStop(0, colors.blue); water.addColorStop(1, colors.scopeBg);
  g.globalAlpha = .35; g.fillStyle = water; g.fillRect(left, top, right - left, bottom_px - top); g.globalAlpha = 1;
  if (bottom !== null && bottom < scaleMax) {
    g.fillStyle = colors.line; g.fillRect(left, y(bottom), right - left, bottom_px - y(bottom));
    g.strokeStyle = colors.muted; g.beginPath(); g.moveTo(left, y(bottom)); g.lineTo(right, y(bottom)); g.stroke();
  }
  g.strokeStyle = colors.line; g.lineWidth = 1; g.strokeRect(left, top, right - left, bottom_px - top);
  const step = scaleMax <= 600 ? 100 : scaleMax <= 1200 ? 200 : 500;
  for (let depth = 0; depth <= scaleMax; depth += step) label(g, String(depth), left - 6, y(depth), colors.muted, "right");
  // Reference lines, labelled in a column right of the water so they never overlap.
  const marks = [];
  const line = (depth, color, dash, text) => {
    if (!finite(depth)) return;
    g.setLineDash(dash); g.strokeStyle = color; g.lineWidth = 1.5;
    g.beginPath(); g.moveTo(left, y(depth)); g.lineTo(right, y(depth)); g.stroke(); g.setLineDash([]);
    marks.push([y(depth), text, color]);
  };
  line(presets.periscope, colors.amber, [2, 4], t("uboot_depth_mark_periscope", {depth: number(presets.periscope, 0)}));
  line(presets.layer, colors.accent, [8, 4], t("uboot_depth_mark_layer", {depth: number(presets.layer, 0)}));
  line(nav.safe_depth_m, colors.red, [6, 4], t("uboot_depth_mark_safe", {depth: number(nav.safe_depth_m, 0)}));
  line(nav.crush_depth_m, colors.red, [], t("uboot_depth_mark_crush", {depth: number(nav.crush_depth_m, 0)}));
  line(nav.target_depth_m, colors.text, [3, 3], t("uboot_depth_mark_order", {depth: number(nav.target_depth_m, 0)}));
  if (bottom !== null) marks.push([y(Math.min(bottom, scaleMax)), t("uboot_depth_mark_bottom", {depth: number(bottom, 0)}), colors.muted]);
  // The boat: hull and sail at its depth, the dive direction as an arrow.
  const cx = (left + right) / 2, cy = y(nav.depth_m);
  g.fillStyle = colors.accent; g.beginPath(); g.ellipse(cx, cy, 22, 6, 0, 0, Math.PI * 2); g.fill();
  g.fillRect(cx - 4, cy - 11, 9, 6);
  if (Math.abs(nav.target_depth_m - nav.depth_m) > 2) {
    const dir = nav.target_depth_m > nav.depth_m ? 1 : -1;
    g.strokeStyle = colors.accent; g.lineWidth = 2; g.beginPath();
    g.moveTo(cx + 32, cy); g.lineTo(cx + 32, cy + dir * 18); g.lineTo(cx + 27, cy + dir * 12);
    g.moveTo(cx + 32, cy + dir * 18); g.lineTo(cx + 37, cy + dir * 12); g.stroke();
  }
  marks.push([cy, t("uboot_depth_mark_boat", {depth: number(nav.depth_m, 0)}), colors.accent]);
  marks.sort((a, b) => a[0] - b[0]);
  let last = -Infinity;
  for (const [my, text, color] of marks) {
    const ly = Math.max(my, last + 15);
    last = ly;
    g.strokeStyle = color; g.globalAlpha = .5; g.beginPath(); g.moveTo(right, my); g.lineTo(right + 8, ly); g.stroke(); g.globalAlpha = 1;
    label(g, text, right + 12, ly, color);
  }
  if (!finite(presets.layer)) label(g, t("uboot_depth_no_bt"), left + 6, bottom_px - 10, colors.muted);
}

// ESM and alarm rose: bow up is the boat's heading; intercepted radar
// bearings as strobes, the last ping and torpedo alarm as marked bearings.
export function drawBoatEsm(id, payload) {
  const plot = visualContext(id);
  if (!plot) return;
  const {context: g, width, height} = plot, colors = palette();
  const nav = payload.navigation, status = payload.status, alarms = payload.alarms;
  const radius = Math.max(20, Math.min(width, height) / 2 - 24), cx = width / 2, cy = height / 2;
  const rad = (degrees) => (degrees - 90) * Math.PI / 180;
  const at = (degrees, r) => [cx + Math.cos(rad(degrees)) * r, cy + Math.sin(rad(degrees)) * r];
  g.strokeStyle = colors.line; g.lineWidth = 1;
  for (const ring of [.5, 1]) { g.beginPath(); g.arc(cx, cy, radius * ring, 0, Math.PI * 2); g.stroke(); }
  for (let degrees = 0; degrees < 360; degrees += 10) {
    const major = degrees % 30 === 0;
    const [x1, y1] = at(degrees, radius), [x2, y2] = at(degrees, radius - (major ? 9 : 4));
    g.beginPath(); g.moveTo(x1, y1); g.lineTo(x2, y2); g.stroke();
    if (major) { const [tx, ty] = at(degrees, radius + 12); label(g, degrees === 0 ? "N" : String(degrees).padStart(3, "0"), tx, ty, colors.muted, "center"); }
  }
  // Own heading.
  g.strokeStyle = colors.blue; g.lineWidth = 2;
  const [hx, hy] = at(nav.course, radius * .35);
  g.beginPath(); g.moveTo(cx, cy); g.lineTo(hx, hy); g.stroke();
  // ESM strobes per emitter: live ones bright with their number, remembered
  // ones faint (the crew's list survives the mast going down).
  // Emitters on nearly the same bearing get their labels stepped inwards.
  const steps = new Map();
  let previous = null, step = 0;
  for (const row of [...payload.esm.emitters].sort((a, b) => a.bearing - b.bearing)) {
    step = previous !== null && row.bearing - previous < 8 ? step + 1 : 0;
    steps.set(row, step); previous = row.bearing;
  }
  for (const row of payload.esm.emitters) {
    const fresh = row.live ? 1 : .3;
    const color = row.mast_threat ? colors.red : colors.amber;
    const spread = Math.max(2, row.bearing_uncertainty_deg * 1.7);
    g.globalAlpha = .16 * fresh; g.fillStyle = color;
    g.beginPath(); g.moveTo(cx, cy); g.arc(cx, cy, radius, rad(row.bearing - spread), rad(row.bearing + spread)); g.closePath(); g.fill();
    g.globalAlpha = fresh; g.strokeStyle = color; g.lineWidth = row.live ? 2 : 1;
    const [x, y] = at(row.bearing, radius);
    g.beginPath(); g.moveTo(cx, cy); g.lineTo(x, y); g.stroke();
    const [lx, ly] = at(row.bearing, Math.max(radius * .3, radius * .82 - steps.get(row) * 16));
    const across = rad(row.bearing) + Math.PI / 2;
    label(g, `${row.label} ${number(row.bearing, 0).padStart(3, "0")}\u00b0`, lx + Math.cos(across) * 14,
      ly + Math.sin(across) * 14, color, "center");
    g.globalAlpha = 1;
  }
  const alarm = (age, bearing, color, key) => {
    if (age === null || bearing === null || age > 120) return;
    g.globalAlpha = Math.max(.3, 1 - age / 120); g.setLineDash([6, 4]); g.strokeStyle = color; g.lineWidth = 2.5;
    const [x, y] = at(bearing, radius);
    g.beginPath(); g.moveTo(cx, cy); g.lineTo(x, y); g.stroke(); g.setLineDash([]);
    // Label beside the line (offset across it), so the dashes stay readable.
    const [lx, ly] = at(bearing, radius * .62);
    const across = rad(bearing) + Math.PI / 2;
    label(g, t(key, {bearing: number(bearing, 0).padStart(3, "0")}), lx + Math.cos(across) * 14,
      ly + Math.sin(across) * 14, color, "center");
    g.globalAlpha = 1;
  };
  alarm(alarms.ping_age_s, alarms.ping_bearing, colors.amber, "uboot_rose_ping");
  alarm(alarms.torpedo_age_s, alarms.torpedo_bearing, colors.red, "uboot_rose_torpedo");
  if (!status.mast) label(g, t("uboot_esm_mast_down"), cx, cy + radius * .6, colors.muted, "center");
  else if (!payload.esm.emitters.length) label(g, t("uboot_esm_none"), cx, cy + radius * .6, colors.muted, "center");
  if (!finite(nav.course)) drawEmpty(plot);
}

// Cross-section of the boat (bow to the right): main ballast fore and aft,
// trim tanks at the ends of the pressure hull, the regulating tank amidships
// and the air bottles, the whole boat tilted by its trim angle (drawn three
// times steeper so a degree shows).
export function drawBoatBallast(id, payload) {
  const plot = visualContext(id);
  if (!plot) return;
  const {context: g, width, height} = plot, colors = palette(), b = payload.ballast;
  const cx = width / 2, cy = height * .46, hw = Math.min(width * .44, 420), hh = Math.min(height * .2, hw * .22);
  const water = colors.blue, fill = (x, y, w, h, fraction, color) => {
    const part = Math.max(0, Math.min(1, fraction));
    g.globalAlpha = .75; g.fillStyle = color; g.fillRect(x, y + h * (1 - part), w, h * part); g.globalAlpha = 1;
    g.strokeStyle = colors.line; g.lineWidth = 1; g.strokeRect(x, y, w, h);
  };
  g.save();
  g.translate(cx, cy);
  g.rotate(Math.max(-12, Math.min(12, b.trim_deg * 3)) * Math.PI / 180);
  // Outer hull and the pressure hull inside it.
  g.strokeStyle = colors.muted; g.lineWidth = 1.5;
  g.beginPath(); g.moveTo(-hw, 0); g.quadraticCurveTo(-hw, -hh, -hw * .8, -hh); g.lineTo(hw * .75, -hh);
  g.quadraticCurveTo(hw, -hh * .6, hw, 0); g.quadraticCurveTo(hw, hh * .6, hw * .75, hh); g.lineTo(-hw * .8, hh);
  g.quadraticCurveTo(-hw, hh, -hw, 0); g.stroke();
  g.fillStyle = colors.muted; g.fillRect(-hw * .12, -hh * 1.9, hw * .2, hh * .9);
  const mbtW = hw * .18, inner = hh * .7;
  fill(-hw * .84, -inner, mbtW, inner * 2, b.mbt_pct / 100, water);
  fill(hw * .78 - mbtW, -inner, mbtW, inner * 2, b.mbt_pct / 100, water);
  const tankW = hw * .14, tankH = inner;
  const fore = .5 + .5 * b.trim_kg / b.trim_capacity_kg;
  fill(hw * .55 - tankW, -tankH / 2, tankW, tankH, fore, colors.amber);
  fill(-hw * .55, -tankH / 2, tankW, tankH, 1 - fore, colors.amber);
  fill(-tankW, -tankH / 2, tankW * 2, tankH, .5 + .5 * b.regulating_kg / b.regulating_capacity_kg, colors.accent);
  g.restore();
  // Tank names under the hull, the air bottles below them.
  const below = cy + hh + 26;
  label(g, t("uboot_canvas_mbt"), cx - hw * .75, below, colors.muted, "center");
  label(g, t("uboot_canvas_trim"), cx - hw * .48, below, colors.muted, "center");
  label(g, t("uboot_canvas_regulating"), cx, below, colors.muted, "center");
  label(g, t("uboot_canvas_trim"), cx + hw * .48, below, colors.muted, "center");
  label(g, t("uboot_canvas_mbt"), cx + hw * .69, below, colors.muted, "center");
  label(g, t("uboot_canvas_bow"), cx + hw, cy - hh - 14, colors.muted, "right");
  const barY = height - 34, barW = hw * 2, air = b.hp_air_bar / b.hp_air_max_bar;
  g.fillStyle = b.blows_left === 0 ? colors.red : colors.accent;
  g.fillRect(cx - hw, barY, barW * Math.max(0, Math.min(1, air)), 10);
  g.strokeStyle = colors.line; g.strokeRect(cx - hw, barY, barW, 10);
  label(g, t("uboot_canvas_air", {bar: number(b.hp_air_bar, 0), blows: b.blows_left}), cx - hw, barY - 10, colors.muted);
  label(g, t("uboot_trim_angle_value", {angle: `${b.trim_deg > 0 ? "+" : ""}${number(b.trim_deg, 1)}`}), cx + hw, barY - 10,
    Math.abs(b.trim_deg) > 3 ? colors.amber : colors.muted, "right");
}

// Damage control: the pressure hull cut into its compartments (bow to the
// right) with the water in each, a flame bar for fire, a green frame for
// chlorine gas (accent), a dot for an open leak, thick bulkheads where they are shut
// and the two teams by number.
export function drawBoatDamage(id, payload) {
  const plot = visualContext(id);
  if (!plot) return;
  const {context: g, width, height} = plot, colors = palette(), dc = payload.damage_control;
  const count = dc.compartments.length, left = 28, right = width - 28, top = 26, bottom = height - 30;
  const cell = (right - left) / count;
  g.strokeStyle = colors.muted; g.lineWidth = 1.5;
  g.beginPath(); g.moveTo(left, top); g.lineTo(8, (top + bottom) / 2); g.lineTo(left, bottom);
  g.moveTo(right, top); g.lineTo(width - 8, (top + bottom) / 2); g.lineTo(right, bottom); g.stroke();
  dc.compartments.forEach((row, index) => {
    const x = left + (count - 1 - index) * cell, h = bottom - top;
    const water = Math.max(0, Math.min(1, row.water_kg / row.capacity_kg));
    g.globalAlpha = .75; g.fillStyle = colors.blue; g.fillRect(x, top + h * (1 - water), cell, h * water); g.globalAlpha = 1;
    if (row.fire_pct > 0) { g.fillStyle = colors.red; g.fillRect(x + 4, top + 4, (cell - 8) * row.fire_pct / 100, 8); }
    if (row.chlorine_pct > 0) {
      g.strokeStyle = colors.accent; g.lineWidth = 1 + 3 * row.chlorine_pct / 100; g.strokeRect(x + 5, top + 16, cell - 10, h - 22);
    }
    if (row.leak_pct > 0) {
      g.fillStyle = colors.amber; g.beginPath(); g.arc(x + cell / 2, bottom - 8, 2 + 5 * row.leak_pct / 100, 0, Math.PI * 2); g.fill();
    }
    g.strokeStyle = row.down ? colors.red : colors.line; g.lineWidth = row.down ? 2 : 1; g.strokeRect(x, top, cell, h);
    if (row.closed) {
      g.strokeStyle = colors.amber; g.lineWidth = 4;
      g.beginPath(); g.moveTo(x, top - 6); g.lineTo(x, bottom + 6); g.moveTo(x + cell, top - 6); g.lineTo(x + cell, bottom + 6); g.stroke();
    }
    const teams = dc.teams.filter((team) => team.compartment === row.name).map((team) => String(team.team + 1));
    if (teams.length) label(g, teams.join(" "), x + cell / 2, top + 28, colors.text, "center");
    label(g, t(`uboot_compartment_${row.name}`), x + cell / 2, bottom + 14, row.down ? colors.red : colors.muted, "center");
  });
  label(g, t("uboot_canvas_bow"), right, top - 12, colors.muted, "right");
  label(g, dc.power ? t("uboot_dc_power_on") : t("uboot_dc_power_off"), left, top - 12, dc.power ? colors.muted : colors.red);
}

// The eyepiece: sky and sea in the light the optics see, the horizon in
// motion, the bearing scale, the crosshair with the stadimeter window and
// the outlines of the crew's own sightings inside the field of view.
// The periscope picture: state arrives at most 4 Hz, so the view eases its
// bearing and horizon toward the latest state every animation frame instead
// of jumping once per state (time constant SCOPE_EASE_S, wall clock only;
// display only, the orders and the stadimeter use the published state).
const SCOPE_EASE_S = 0.25;
const scopeView = {id: null, target: null, shown: null, frame: null, last: 0};
const wrap180 = (deg) => ((deg + 540) % 360) - 180;

function scopeStep(now) {
  scopeView.frame = null;
  const {target, shown} = scopeView;
  if (!target || !shown) return;
  const dt = Math.min(.25, Math.max(0, (now - scopeView.last) / 1000));
  scopeView.last = now;
  const k = 1 - Math.exp(-dt / SCOPE_EASE_S);
  shown.bearing = (shown.bearing + wrap180(target.bearing - shown.bearing) * k + 360) % 360;
  shown.horizon_offset += (target.horizon_offset - shown.horizon_offset) * k;
  shown.horizon_tilt += (target.horizon_tilt - shown.horizon_tilt) * k;
  if (!drawScopeFrame(scopeView.id, {...target, bearing: shown.bearing,
    horizon_offset: shown.horizon_offset, horizon_tilt: shown.horizon_tilt})) return;
  // Waves, clouds and weather move on: keep drawing while the picture shows.
  if (!document.hidden) scopeView.frame = requestAnimationFrame(scopeStep);
}

export function drawBoatScope(id, payload) {
  const scope = payload.scope;
  const smooth = scope.available && finite(scope.bearing) && finite(scope.horizon_offset) && finite(scope.horizon_tilt);
  const continuing = smooth && scopeView.id === id && scopeView.shown !== null;
  scopeView.id = id;
  scopeView.target = smooth ? scope : null;
  if (!smooth) {
    scopeView.shown = null;
    if (scopeView.frame !== null) cancelAnimationFrame(scopeView.frame);
    scopeView.frame = null;
    drawScopeFrame(id, scope);
    return;
  }
  if (!continuing) {
    scopeView.shown = {bearing: scope.bearing, horizon_offset: scope.horizon_offset, horizon_tilt: scope.horizon_tilt};
  }
  if (!drawScopeFrame(id, {...scope, ...scopeView.shown})) return;
  if (scopeView.frame === null) {
    scopeView.last = performance.now();
    scopeView.frame = requestAnimationFrame(scopeStep);
  }
}

function drawScopeFrame(id, scope) {
  const plot = visualContext(id);
  if (!plot) return false;
  const {context: g, width, height} = plot, colors = palette();
  if (!scope.available) {
    label(g, t("uboot_scope_mast_down"), width / 2, height / 2, colors.muted, "center");
    return true;
  }
  drawSightView(g, width, height, {...scope, window_deg: scope.window_deg,
    outlines: scope.sightings.map((row) => ({bearing: row.bearing, span_deg: row.span_deg, cls: row.cls,
      stale: row.age_s === null || row.age_s > 1}))}, performance.now() / 1000, g.font);
  if (!finite(scope.bearing)) drawEmpty(plot);
  return true;
}
