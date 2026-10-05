// Chart label placement that keeps labels from covering each other (the
// browser twin of src/ui/label_layout.py, same candidates and rules). Pure
// canvas geometry: the result depends only on call order and text widths.
const MAX_RECTS = 160;
const GAP = 2;
const SLIDE_STEPS = 6;

export function labelField(width, height) {
  const rects = [];
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
    // Whether a box keeps clear of every label placed so far.
    isFree: (x, y, w, h) => overlap({ x, y, w, h }) === 0,
    // candidates: top-left points; returns the chosen box {x, y, w, h}.
    place(w, h, candidates) {
      let best = null, bestCost = Infinity;
      for (const [cx, cy] of candidates) {
        const r = clamp(cx, cy, w, h), cost = overlap(r);
        if (cost === 0) { best = r; break; }
        if (cost < bestCost) { best = r; bestCost = cost; }
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

// Draw ``text`` with its baseline at the chosen box (canvas textBaseline
// "alphabetic"); x/y are the preferred baseline position as before.
export function placeText(context, field, text, x, y, maxWidth) {
  const size = parseFloat(context.font) || 12;
  const w = Math.min(maxWidth || Infinity, context.measureText(text).width), h = size;
  const box = field.place(w, h, around(x, y - h, w, h));
  context.fillText(text, box.x, box.y + h, maxWidth);
}

// Speed label past a motion vector's tip (unit direction ux, uy), on the far
// side from its own line, like the uConsole chart; steps aside like any label.
export function placeTip(context, field, text, tipX, tipY, ux, uy) {
  const size = parseFloat(context.font) || 12;
  const w = context.measureText(text).width, h = size;
  const x = ux >= -.2 ? tipX + 4 : tipX - 4 - w, y = tipY - h / 2 + uy * (h / 2 + 2);
  const box = field.place(w, h, around(x, y, w, h, 4));
  context.fillText(text, box.x, box.y + h);
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
