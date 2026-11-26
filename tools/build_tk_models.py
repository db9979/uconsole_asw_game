"""Builds data/unit_models/tiefenkontakt.json.gz from the Tiefenkontakt ship models.

Tiefenkontakt (github.com/db9979/tiefenkontakt) draws its ships with Three.js.
``tools/tiefenkontakt/export_models.mts`` writes them as raw triangles; this
tool turns them into the polygon meshes our painter (``src/ui/model_bsp.py``)
draws on the uConsole and in the browser:

* axes and scale of ``src/ui/unit_models.py``: ``x`` forward (bow +0.5),
  ``y`` to port, ``z`` up, the overall length is one;
* corners snapped to a fine grid, slivers too small to ever show dropped;
* neighbouring triangles of one colour in one plane joined into convex
  polygons (a box side becomes one quad again);
* the colours reduced to a shared palette (``tk0`` ... materials);
* the navigation lamps as ``(u, v)`` points of the silhouette profiles.

Usage::

    npx tsx tools/tiefenkontakt/export_models.mts <tiefenkontakt dir> raw.json
    python tools/build_tk_models.py raw.json
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "unit_models" / "tiefenkontakt.json.gz"
# Grid the corners snap to and the smallest triangle kept (fractions of the length).
SNAP = 1 / 1600
MIN_AREA = (1 / 400) ** 2
# Faces with normals closer than this (1 - cos) count as one plane.
PLANE_TOL = 6e-3
PALETTE_SIZE = 40
# Designs no catalog type is drawn as (src/ui/tk_models.design_for).
UNUSED = {"yacht"}
# Share of triangles the quadric decimation keeps on the smooth submarine
# hulls, and how hard it collapses (ships are boxes: the plane merge does).
KEEP_SUBS = 0.35
AGGRESSION = 5
# Three.js lights its Lambert colours; our painter shades the bare colour.
BRIGHTEN = 1.3


def _snap(tris, cols, length):
    grid = length * SNAP
    min_area = MIN_AREA * length * length
    index, faces, colours = {}, [], []
    for tri, col in zip(tris, cols):
        if 0.5 * np.linalg.norm(np.cross(tri[1] - tri[0], tri[2] - tri[0])) < min_area:
            continue
        ids = []
        for corner in np.round(tri / grid).astype(np.int64):
            ids.append(index.setdefault(tuple(corner), len(index)))
        if len(set(ids)) == 3:
            faces.append(ids)
            colours.append(col)
    verts = np.array(sorted(index, key=index.get), dtype=float) * grid
    return verts, faces, colours


def _normal(verts, face):
    pts = verts[face]
    n = np.zeros(3)
    for a, b in zip(pts, np.roll(pts, -1, axis=0)):
        n += ((a[1] - b[1]) * (a[2] + b[2]), (a[2] - b[2]) * (a[0] + b[0]),
              (a[0] - b[0]) * (a[1] + b[1]))
    length = float(np.linalg.norm(n))
    return n / length if length > 1e-12 else None


def _convex(verts, poly, normal):
    pts = verts[poly]
    nxt, after = np.roll(pts, -1, axis=0), np.roll(pts, -2, axis=0)
    return bool(np.all(np.cross(nxt - pts, after - nxt) @ normal >= -1e-9))


def _decimate(verts, faces, colours, keep):
    """Quadric edge collapse per colour (the borders between colours stay):
    curved hulls, domes and masts lose most of their many thin triangles."""
    if keep >= 1.0:
        return verts, faces, colours
    import fast_simplification
    out_v, out_f, out_c = [], [], []
    by_colour = {}
    for face, col in zip(faces, colours):
        by_colour.setdefault(col, []).append(face)
    for col, group in sorted(by_colour.items()):
        group = np.asarray(group, dtype=np.int64)
        used, inverse = np.unique(group, return_inverse=True)
        pts, tri = verts[used], inverse.reshape(-1, 3)
        if len(tri) > 24:
            pts, tri = fast_simplification.simplify(pts.astype(np.float32), tri.astype(np.int32),
                                                    target_reduction=1.0 - keep, agg=AGGRESSION)
        base = sum(len(v) for v in out_v)
        out_v.append(np.asarray(pts, dtype=float))
        for t in np.asarray(tri):
            if len(set(t.tolist())) == 3:
                out_f.append([int(k) + base for k in t])
                out_c.append(col)
    return np.concatenate(out_v), out_f, out_c


def _merge(verts, faces, colours, tol):
    """Joins neighbours sharing an edge, colour and plane while convex."""
    faces = [list(f) for f in faces]
    normals = [_normal(verts, f) for f in faces]
    alive = {i for i, n in enumerate(normals) if n is not None}
    edges = {}
    for i in alive:
        f = faces[i]
        for k in range(len(f)):
            edges[(f[k], f[(k + 1) % len(f)])] = i
    flat = 1e-4 * float(np.abs(verts).max())
    changed = True
    while changed:
        changed = False
        for i in sorted(alive):
            if i not in alive:
                continue
            f = faces[i]
            for k in range(len(f)):
                a, b = f[k], f[(k + 1) % len(f)]
                j = edges.get((b, a))
                if j is None or j == i or j not in alive or colours[j] != colours[i]:
                    continue
                if normals[i] @ normals[j] < 1 - tol:
                    continue
                g = faces[j]
                if abs(normals[i] @ (verts[g].mean(axis=0) - verts[f[0]])) > flat:
                    continue
                m = g.index(b)
                new = f[:k + 1] + [g[(m + 2 + t) % len(g)] for t in range(len(g) - 2)] + f[k + 1:]
                if len(set(new)) != len(new) or not _convex(verts, new, normals[i]):
                    continue
                for poly in (f, g):
                    for kk in range(len(poly)):
                        edges.pop((poly[kk], poly[(kk + 1) % len(poly)]), None)
                alive.discard(j)
                faces[i] = new
                for kk in range(len(new)):
                    edges[(new[kk], new[(kk + 1) % len(new)])] = i
                changed = True
                break
    keep = sorted(alive)
    return [faces[i] for i in keep], [colours[i] for i in keep]


def _palette(colours, size):
    """k-means over all face colours (deterministic start: spread by count)."""
    data = np.asarray(colours, dtype=float)
    unique, counts = np.unique(data, axis=0, return_counts=True)
    order = np.argsort(-counts)
    centres = unique[order[:size]].copy()
    for _ in range(30):
        d = ((unique[:, None, :] - centres[None]) ** 2).sum(axis=2)
        nearest = d.argmin(axis=1)
        for c in range(len(centres)):
            mask = nearest == c
            if mask.any():
                centres[c] = np.average(unique[mask], axis=0, weights=counts[mask])
    return np.clip(np.round(centres), 0, 255).astype(int)


def _nav(lamps, z_mid, length):
    """Lamp positions as silhouette ``(u, v)``: u from the bow (0) to the
    stern (1), v the height above the waterline, both in lengths."""
    if not lamps:
        return None
    uv = {kind: [] for kind in "WRG"}
    for x, y, z, kind in lamps:
        uv[kind].append((round(0.5 - (z - z_mid) / length, 4), round(y / length, 4)))
    white = sorted(uv["W"], key=lambda p: -p[1])
    mast, stern = white[0], max(white, key=lambda p: p[0])
    side = uv["R"][0] if uv["R"] else (mast[0], mast[1] * 0.4)
    second = (round(min(0.98, mast[0] + 0.1), 4), round(mast[1] + 0.02, 4))
    return {"mast": [list(mast), list(second)], "side": list(side), "stern": list(stern),
            "round": list(mast)}


def build(raw: dict) -> dict:
    meshes = {}
    for name, model in raw["models"].items():
        if name in UNUSED:
            continue
        tris = np.asarray(model["t"], dtype=float).reshape(-1, 3, 3)
        # The merge keys: colour and two-sidedness.
        cols = [tuple(c) + (int(two),) for c, two in
                zip(np.asarray(model["c"], dtype=int).reshape(-1, 3), model["s"])]
        z = tris[..., 2]
        length = float(z.max() - z.min())
        z_mid = float(z.max() + z.min()) / 2
        verts, faces, colours = _snap(tris, cols, length)
        verts, faces, colours = _decimate(verts, faces, colours,
                                           KEEP_SUBS if name.startswith("ss") else 1.0)
        faces, colours = _merge(verts, faces, colours, PLANE_TOL)
        # Tiefenkontakt: bow +z, port +x, up +y (metres) -> ours, one length.
        ours = np.stack([(verts[:, 2] - z_mid), verts[:, 0], verts[:, 1]], axis=1) / length
        used = sorted({k for f in faces for k in f})
        remap = {k: i for i, k in enumerate(used)}
        meshes[name] = {
            "length_m": round(length, 2),
            "beam_m": round(float(tris[..., 0].max() - tris[..., 0].min()), 2),
            "v": [int(round(c * 10000)) for k in used for c in ours[k]],
            "f": [[remap[k] for k in f] for f in faces],
            "colours": [c[:3] for c in colours],
            "s": [i for i, c in enumerate(colours) if c[3]],
            "nav": _nav(model.get("nav"), z_mid, length),
        }
    palette = _palette([c for m in meshes.values() for c in m["colours"]], PALETTE_SIZE)
    bright = np.clip(np.round(palette * BRIGHTEN), 0, 255).astype(int)
    for mesh in meshes.values():
        data = np.asarray(mesh.pop("colours"), dtype=float)
        mesh["m"] = ((data[:, None, :] - palette[None]) ** 2).sum(axis=2).argmin(axis=1).tolist()
    return {
        "note": "GENERATED by tools/build_tk_models.py from the Tiefenkontakt ship models; "
                "coordinates in 1/10000 of the overall length (x forward, y port, z up).",
        "source": raw.get("source"), "commit": raw.get("commit"),
        "palette": bright.tolist(),
        "models": meshes,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("raw", type=Path, help="output of tools/tiefenkontakt/export_models.mts")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    data = build(json.loads(args.raw.read_text(encoding="utf-8")))
    text = json.dumps(data, separators=(",", ":"), sort_keys=True)
    # mtime 0: the same input gives the same bytes.
    args.out.write_bytes(gzip.compress((text + "\n").encode("utf-8"), 9, mtime=0))
    for name, mesh in data["models"].items():
        print(f"{name:15s} {len(mesh['f']):5d} faces {len(mesh['v']) // 3:5d} corners")
    print(f"{args.out} {args.out.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
