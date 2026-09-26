import { finite, number, t } from "../core/format.js";
import { palette } from "../core/palette.js";
import { drawEmpty, visualContext } from "../views/visual-common.js";

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
  const scaleMax = Math.max(100, bottom ?? 0, nav.max_depth_m, nav.depth_m, nav.target_depth_m) * 1.06;
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
  // ESM strobes (only with the mast up).
  for (const row of alarms.esm) {
    const fresh = Math.max(.25, 1 - row.age_s / 60);
    g.globalAlpha = .18 * fresh; g.fillStyle = colors.amber;
    g.beginPath(); g.moveTo(cx, cy); g.arc(cx, cy, radius, rad(row.bearing - 4), rad(row.bearing + 4)); g.closePath(); g.fill();
    g.globalAlpha = fresh; g.strokeStyle = colors.amber; g.lineWidth = 2;
    const [x, y] = at(row.bearing, radius);
    g.beginPath(); g.moveTo(cx, cy); g.lineTo(x, y); g.stroke();
    const [lx, ly] = at(row.bearing, radius * .8);
    const across = rad(row.bearing) + Math.PI / 2;
    label(g, `${number(row.bearing, 0).padStart(3, "0")}\u00b0`, lx + Math.cos(across) * 12,
      ly + Math.sin(across) * 12, colors.amber, "center");
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
  else if (!alarms.esm.length) label(g, t("uboot_esm_none"), cx, cy + radius * .6, colors.muted, "center");
  if (!finite(nav.course)) drawEmpty(plot);
}
