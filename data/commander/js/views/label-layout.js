// Chart label placement that keeps labels from covering each other, the
// symbols and the drawn lines (motion vectors, trails, bearing lines): the
// browser twin of src/ui/label_layout.py, same candidates and rules. Canvas
// geometry: the result depends on call order, text widths and, for a label
// placed with a key, the spot it took last time (kept while it stays free,
// so labels do not jump between redraws).
const MAX_RECTS = 160;
const MAX_LINES = 320;
const LINE_COST = 6;
const GAP = 2;
const SLIDE_STEPS = 6;
const MEMORY_MAX = 512;
const memory = new Map();

// Length of the part of segment a-b inside box r (Liang-Barsky clipping).
function clippedLength(r, ax, ay, bx, by) {
  let t0 = 0, t1 = 1;
  const dx = bx - ax, dy = by - ay;
  for (const [p, q] of [[-dx, ax - r.x], [dx, r.x + r.w - ax], [-dy, ay - r.y], [dy, r.y + r.h - ay]]) {
    if (p === 0) { if (q < 0) return 0; continue; }
    const t = q / p;
    if (p < 0) { if (t > t1) return 0; if (t > t0) t0 = t; } else { if (t < t0) return 0; if (t < t1) t1 = t; }
  }
  return Math.hypot(dx, dy) * (t1 - t0) + 1;
}

export function labelField(width, height) {
  const rects = [], lines = [];
  const clamp = (x, y, w, h) => ({
    x: Math.min(Math.max(Math.round(x), 2), Math.max(2, width - w - 2)),
    y: Math.min(Math.max(Math.round(y), 2), Math.max(2, height - h - 2)), w, h,
  });
  const overlap = (r) => {
    let total = 0;
    for (const o of rects) {
      const w = Math.min(r.x + r.w + GAP, o.x + o.w) - Math.max(r.x - GAP, o.x);
      const h = Math.min(r.y + r.h + GAP, o.y + o.h) - Math.max(r.y - GAP, o.y);
      if (w > 0 && h > 0) total += w * h;
    }
    for (const [ax, ay, bx, by, lw] of lines) {
      if (Math.max(ax, bx) + lw < r.x - GAP || Math.min(ax, bx) - lw > r.x + r.w + GAP
        || Math.max(ay, by) + lw < r.y - GAP || Math.min(ay, by) - lw > r.y + r.h + GAP) continue;
      total += clippedLength({ x: r.x - GAP - lw / 2, y: r.y - GAP - lw / 2, w: r.w + 2 * GAP + lw, h: r.h + 2 * GAP + lw },
        ax, ay, bx, by) * LINE_COST;
    }
    return total;
  };
  // Candidates around a point far off the chart all clamp to one spot on
  // its edge; sliding a label height or width at a time sets such edge
  // labels beside each other instead of on top.
  const slide = (r, cost) => {
    let best = r, bestCost = cost;
    for (let k = 1; k <= SLIDE_STEPS; k += 1) {
      for (const [dx, dy] of [[0, k * (r.h + GAP)], [0, -k * (r.h + GAP)], [-k * (r.w + GAP), 0], [k * (r.w + GAP), 0]]) {
        const moved = clamp(r.x + dx, r.y + dy, r.w, r.h), movedCost = overlap(moved);
        if (movedCost === 0) return moved;
        if (movedCost < bestCost) { best = moved; bestCost = movedCost; }
      }
    }
    return best;
  };
  const reserve = (x, y, w, h) => { if (rects.length < MAX_RECTS) rects.push({ x, y, w, h }); };
  return {
    reserve,
    // Keep later labels off a drawn line (a motion vector, a trail piece).
    reserveLine(ax, ay, bx, by, lineWidth = 4) { if (lines.length < MAX_LINES) lines.push([ax, ay, bx, by, lineWidth]); },
    // Whether a box keeps clear of every label placed so far.
    isFree: (x, y, w, h) => overlap({ x, y, w, h }) === 0,
    // candidates: top-left points; returns the chosen box {x, y, w, h}. With
    // a key the candidate this label took last time is tried first.
    place(w, h, candidates, key = null) {
      let best = null, bestCost = Infinity, chosen = null;
      const order = candidates.map((_, index) => index), last = key === null ? undefined : memory.get(key);
      if (last !== undefined && last < order.length) { order.splice(last, 1); order.unshift(last); }
      for (const index of order) {
        const [cx, cy] = candidates[index], r = clamp(cx, cy, w, h), cost = overlap(r);
        if (cost === 0) { best = r; bestCost = 0; chosen = index; break; }
        if (cost < bestCost) { best = r; bestCost = cost; chosen = index; }
      }
      if (key !== null && chosen !== null) {
        memory.delete(key); memory.set(key, chosen);
        while (memory.size > MEMORY_MAX) memory.delete(memory.keys().next().value);
      }
      if (!best) best = clamp(0, 0, w, h);
      else if (bestCost > 0) best = slide(best, bestCost);
      reserve(best.x, best.y, best.w, best.h);
      return best;
    },
  };
}

// Candidate top-left points around a preferred position (right of the
// symbol), stepping down and up, then mirrored to the symbol's left side.
export function around(x, y, w, h, gap = 14) {
  const step = h + GAP, left = x - w - 2 * gap;
  return [[x, y], [x, y + step], [x, y - step], [left, y], [left, y + step], [left, y - step],
    [x, y + 2 * step], [x, y - 2 * step], [left, y + 2 * step], [left, y - 2 * step]];
}

// Candidates for a moving contact's label: abeam of its course (starboard,
// then port), clear of its motion vector ahead and its trail astern; then the
// quarters and bows, then the usual ring. Without a course, right of it.
export function beside(x, y, w, h, course, gap = 10) {
  const ring = around(x + gap, y - h - 2, w, h, gap);
  if (!Number.isFinite(course)) return ring;
  const points = [];
  for (const offset of [90, -90, 135, -135, 45, -45]) {
    const rad = (course + offset) * Math.PI / 180, ux = Math.sin(rad), uy = -Math.cos(rad);
    const reach = gap + Math.abs(ux) * w / 2 + Math.abs(uy) * h / 2;
    points.push([Math.round(x + ux * reach - w / 2), Math.round(y + uy * reach - h / 2)]);
  }
  return points.concat(ring);
}

// A moving contact's name (with its speed) abeam of its course at symbol x, y.
export function placeBeside(context, field, text, x, y, course, key = null) {
  const size = parseFloat(context.font) || 12;
  const w = context.measureText(text).width, h = size;
  const box = field.place(w, h, beside(x, y, w, h, course), key);
  context.fillText(text, box.x, box.y + h);
}

// Draw ``text`` with its baseline at the chosen box (canvas textBaseline
// "alphabetic"); x/y are the preferred baseline position as before.
export function placeText(context, field, text, x, y, maxWidth) {
  const size = parseFloat(context.font) || 12;
  const w = Math.min(maxWidth || Infinity, context.measureText(text).width), h = size;
  const box = field.place(w, h, around(x, y - h, w, h));
  context.fillText(text, box.x, box.y + h, maxWidth);
}

// A label that belongs to one exact place (a bearing scale number, a range
// ring's distance): drawn at baseline x, y and never moved; later labels keep
// off it. With skipIfTaken a label whose place is already held is left out.
export function fixedText(context, field, text, x, y, skipIfTaken = false) {
  const size = parseFloat(context.font) || 12, w = context.measureText(text).width;
  if (skipIfTaken && !field.isFree(x, y - size, w, size + 2)) return false;
  field.reserve(x, y - size, w, size + 2);
  context.fillText(text, x, y);
  return true;
}

// Keep later labels off text drawn at a fixed place (baseline x, y).
export function reserveText(context, field, text, x, y) {
  const size = parseFloat(context.font) || 12;
  field.reserve(x, y - size, context.measureText(text).width, size + 2);
}

// Where the ray from the chart's centre to an off-chart point crosses the
// chart edge (pulled ``inset`` pixels in), and its unit direction.
export function edgeAnchor(width, height, x, y, inset = 10) {
  const cx = width / 2, cy = height / 2, dx = x - cx, dy = y - cy, length = Math.hypot(dx, dy);
  if (length < 1e-9) return [cx, cy, 0, -1];
  const halfW = Math.max(1, cx - inset), halfH = Math.max(1, cy - inset);
  const k = Math.min(dx ? halfW / Math.abs(dx) : Infinity, dy ? halfH / Math.abs(dy) : Infinity);
  return [cx + dx * k, cy + dy * k, dx / length, dy / length];
}
