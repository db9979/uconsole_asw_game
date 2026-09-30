// Chart label placement that keeps labels from covering each other (the
// browser twin of src/ui/label_layout.py, same candidates and rules). Pure
// canvas geometry: the result depends only on call order and text widths.
const MAX_RECTS = 160;
const GAP = 2;

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
  const reserve = (x, y, w, h) => { if (rects.length < MAX_RECTS) rects.push({ x, y, w, h }); };
  return {
    reserve,
    // candidates: top-left points; returns the chosen box {x, y, w, h}.
    place(w, h, candidates) {
      let best = null, bestCost = Infinity;
      for (const [cx, cy] of candidates) {
        const r = clamp(cx, cy, w, h), cost = overlap(r);
        if (cost === 0) { best = r; break; }
        if (cost < bestCost) { best = r; bestCost = cost; }
      }
      best ||= clamp(0, 0, w, h);
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
