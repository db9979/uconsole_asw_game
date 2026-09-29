// Exact back-to-front order for the 3D models: the binary space partition of
// src/ui/model_bsp.py with the same rules.  A sort by face centre drew far
// faces over near ones where parts overlap, so the models looked hollow.
const EPS = 1e-6;
const CANDIDATES = 8;
const SPLIT_WEIGHT = 3;

// ``verts`` [[x, y, z]], ``faces`` [[i, ...]] with ``normals`` [[x, y, z]]
// per face, ``lines`` [[a, b, material]].  Returns {verts, faces, faceSrc,
// lines, lineSrc, order(toward)}: split pieces refer to their source face or
// line; ``order`` lists [kind, index] back to front (kind 0 face, 1 line)
// for a viewer far off in model direction ``toward``.
export function buildTree(sourceVerts, sourceFaces, normals, sourceLines) {
  const verts = sourceVerts.map((p) => p.slice());
  const faces = [], faceSrc = [], lines = [], lineSrc = [];
  const nodeNormal = [], nodeDist = [], nodeFaces = [], nodeLines = [], back = [], front = [];
  const dot = (n, p) => n[0] * p[0] + n[1] * p[1] + n[2] * p[2];
  const plane = (item) => [normals[item.src], dot(normals[item.src], verts[item.idx[0]])];
  const sides = (item, n, d) => {
    let hi = -Infinity, lo = Infinity;
    for (const k of item.idx) { const s = dot(n, verts[k]) - d; if (s > hi) hi = s; if (s < lo) lo = s; }
    return [hi, lo];
  };
  const cut = (a, b, sa, sb) => {
    const t = sa / (sa - sb), pa = verts[a], pb = verts[b];
    verts.push([0, 1, 2].map((i) => pa[i] + t * (pb[i] - pa[i])));
    return verts.length - 1;
  };
  const split = (item, n, d) => {
    const s = item.idx.map((k) => dot(n, verts[k]) - d);
    if (item.line) {
      const [a, b] = item.idx, m = cut(a, b, s[0], s[1]);
      const first = {...item, idx: [a, m]}, second = {...item, idx: [m, b]};
      return s[0] > 0 ? [second, first] : [first, second];
    }
    const f = [], bk = [], count = item.idx.length;
    for (let i = 0; i < count; i += 1) {
      const j = (i + 1) % count, a = item.idx[i], sa = s[i], sb = s[j];
      if (sa > EPS) f.push(a);
      else if (sa < -EPS) bk.push(a);
      else { f.push(a); bk.push(a); }
      if ((sa > EPS && sb < -EPS) || (sa < -EPS && sb > EPS)) {
        const m = cut(a, item.idx[j], sa, sb);
        f.push(m); bk.push(m);
      }
    }
    return [bk.length >= 3 ? {...item, idx: bk} : null, f.length >= 3 ? {...item, idx: f} : null];
  };
  const choose = (items, facePos) => {
    if (facePos.length <= 2) return facePos[0];
    const step = Math.max(1, Math.floor(facePos.length / CANDIDATES));
    let best = facePos[0], bestScore = null;
    for (let c = 0, tried = 0; c < facePos.length && tried < CANDIDATES; c += step, tried += 1) {
      const candidate = facePos[c];
      const [n, d] = plane(items[candidate]);
      let fr = 0, bk = 0, sp = 0;
      items.forEach((item, i) => {
        if (i === candidate) return;
        const [hi, lo] = sides(item, n, d);
        if (hi > EPS && lo < -EPS) sp += 1;
        else if (hi > EPS) fr += 1;
        else if (lo < -EPS) bk += 1;
      });
      const score = SPLIT_WEIGHT * sp + Math.abs(fr - bk);
      if (bestScore === null || score < bestScore) { best = candidate; bestScore = score; }
    }
    return best;
  };
  const node = (n, d, on) => {
    const k = nodeNormal.length;
    nodeNormal.push(n); nodeDist.push(d);
    // Coplanar faces keep the mesh's order (a pad drawn over its deck).
    const onFaces = on.filter((item) => !item.line).sort((p, q) => p.src - q.src);
    nodeFaces.push(onFaces.map((item) => { faces.push(item.idx); faceSrc.push(item.src); return faces.length - 1; }));
    nodeLines.push(on.filter((item) => item.line).map((item) => { lines.push(item.idx); lineSrc.push(item.src); return lines.length - 1; }));
    back.push(-1); front.push(-1);
    return k;
  };
  const items = sourceFaces.map((idx, src) => ({idx, src, line: false}))
    .concat(sourceLines.map(([a, b], src) => ({idx: [a, b], src, line: true})));
  let root = -1;
  const stack = [[items, null, 0]];
  while (stack.length) {
    const [list, parent, side] = stack.pop();
    const facePos = [];
    list.forEach((item, i) => { if (!item.line) facePos.push(i); });
    let k;
    if (!facePos.length) {
      k = node([0, 0, 0], 0, list);
    } else {
      const c = choose(list, facePos);
      const [n, d] = plane(list[c]);
      const on = [], bk = [], fr = [];
      list.forEach((item, i) => {
        if (i === c) { on.push(item); return; }
        const [hi, lo] = sides(item, n, d);
        if (hi <= EPS && lo >= -EPS) on.push(item);
        else if (hi <= EPS) bk.push(item);
        else if (lo >= -EPS) fr.push(item);
        else {
          const [pb, pf] = split(item, n, d);
          if (pb) bk.push(pb);
          if (pf) fr.push(pf);
        }
      });
      k = node(n, d, on);
      if (bk.length) stack.push([bk, k, 0]);
      if (fr.length) stack.push([fr, k, 1]);
    }
    if (parent === null) root = k;
    else (side ? front : back)[parent] = k;
  }
  const order = (toward) => {
    const out = [];
    if (root < 0) return out;
    const todo = [[root, false]];
    while (todo.length) {
      const [k, emit] = todo.pop();
      if (emit) {
        for (const i of nodeFaces[k]) out.push([0, i]);
        for (const j of nodeLines[k]) out.push([1, j]);
        continue;
      }
      const viewerFront = dot(nodeNormal[k], toward) > 0;
      const near = viewerFront ? front[k] : back[k], far = viewerFront ? back[k] : front[k];
      if (near >= 0) todo.push([near, false]);
      todo.push([k, true]);
      if (far >= 0) todo.push([far, false]);
    }
    return out;
  };
  return {verts, faces, faceSrc, lines, lineSrc, order};
}
