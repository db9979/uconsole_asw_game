"""The 3D models draw every face after the faces behind it (a binary space
partition, ``src/ui/model_bsp.py`` and its browser twin), and their hulls
are closed, so no model looks hollow from any side."""

import functools
import http.server
import json
import math
import re
import shutil
import subprocess
import threading
from collections import Counter
from pathlib import Path

import numpy as np
import pygame
import pytest

from src.ui import model_bsp, unit_models as um, unit_variants as uv

ROOT = Path(__file__).resolve().parents[1]
W, H = 300, 200
YAWS = (0.3, 1.2, 2.2, 3.3, 4.4, 5.5)
# One of each kind: warship, container stack, ro-ro box, cruise ship,
# submarine and airliner (lines left out: the reference draws faces only).
KEYS = ("warship_05", "cargo_02", "cargo_07", "passenger_01", "sub_12", "civil_transit")


def _without_lines(key):
    mesh = um.mesh_for(key)
    return um.Mesh(mesh.verts, mesh.faces, mesh.mats, mesh.sided, [], mesh.floating)


def _frame(mesh, yaw):
    view = um._view(yaw, um.ELEVATION_RAD)
    horizontal = float(np.max(np.linalg.norm(mesh.verts[:, :2], axis=1)))
    vertical = (horizontal * math.sin(um.ELEVATION_RAD)
                + float(np.max(np.abs(mesh.verts[:, 2]))) * math.cos(um.ELEVATION_RAD))
    reach = max(mesh.radius, um.WATER_RING) if mesh.floating else mesh.radius
    return view, 0.92 * min(W / (2 * reach), H / (2 * vertical))


def _depth_buffer(mesh, yaw):
    """Reference picture: every pixel from its nearest face."""
    view, scale = _frame(mesh, yaw)
    v = mesh.verts @ view.T
    persp = 1 / (1 - v[:, 2] / (5 * mesh.radius))
    sx, sy = W / 2 + v[:, 0] * scale * persp, H / 2 - v[:, 1] * scale * persp
    shade, visible = um._shading(mesh, view)
    colors = np.clip(mesh.colors * shade[:, None], 0, 255).astype(int)
    owner = np.full((H, W), -1)
    depth = np.full((H, W), -1e9)
    yy, xx = np.mgrid[0:H, 0:W] + 0.5
    for fi, face in enumerate(mesh.faces):
        if not visible[fi]:
            continue
        for t in range(1, len(face) - 1):
            a, b, c = face[0], face[t], face[t + 1]
            x0, y0, x1, y1, x2, y2 = sx[a], sy[a], sx[b], sy[b], sx[c], sy[c]
            d = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
            if abs(d) < 1e-9:
                continue
            lx, hx = int(max(0, min(x0, x1, x2))), int(min(W - 1, max(x0, x1, x2)) + 1)
            ly, hy = int(max(0, min(y0, y1, y2))), int(min(H - 1, max(y0, y1, y2)) + 1)
            X, Y = xx[ly:hy + 1, lx:hx + 1], yy[ly:hy + 1, lx:hx + 1]
            l0 = ((y1 - y2) * (X - x2) + (x2 - x1) * (Y - y2)) / d
            l1 = ((y2 - y0) * (X - x2) + (x0 - x2) * (Y - y2)) / d
            l2 = 1 - l0 - l1
            z = l0 * v[a, 2] + l1 * v[b, 2] + l2 * v[c, 2]
            dsub, osub = depth[ly:hy + 1, lx:hx + 1], owner[ly:hy + 1, lx:hx + 1]
            hit = (l0 >= 0) & (l1 >= 0) & (l2 >= 0) & (z > dsub)
            dsub[hit], osub[hit] = z[hit], fi
    picture = np.zeros((H, W, 3), int)
    picture[owner >= 0] = colors[owner[owner >= 0]]
    return picture, owner >= 0


def _wrong_area(key, monkeypatch) -> float:
    """Worst share of the model's area, over six angles, that the drawn
    picture shows in another colour than the depth buffer (solid areas only:
    pixel steps along edges do not count)."""
    mesh = _without_lines(key)
    monkeypatch.setattr(um, "mesh_for", lambda _key: mesh)
    worst = 0.0
    for yaw in YAWS:
        reference, mask = _depth_buffer(mesh, yaw)
        s = pygame.Surface((W, H))
        um.draw_model(s, (0, 0, W, H), key, yaw=yaw)
        drawn = pygame.surfarray.array3d(s).transpose(1, 0, 2).astype(int)
        inner = mask.copy()
        for grid in (inner,):
            grid[1:] &= mask[:-1]
            grid[:-1] &= mask[1:]
            grid[:, 1:] &= mask[:, :-1]
            grid[:, :-1] &= mask[:, 1:]
        wrong = (np.abs(reference - drawn).sum(axis=2) > 30) & inner
        solid = wrong.copy()
        solid[1:] &= wrong[:-1]
        solid[:-1] &= wrong[1:]
        solid[:, 1:] &= wrong[:, :-1]
        solid[:, :-1] &= wrong[:, 1:]
        worst = max(worst, solid.sum() / max(1, inner.sum()))
    return worst


@pytest.mark.parametrize("key", KEYS)
def test_drawn_models_match_a_depth_buffer_from_every_side(key, monkeypatch):
    # A sort by face centre got up to a fifth of these pictures wrong
    # (decks over superstructures, far plating through near plating); what
    # is left are faces lying in one plane, where the depth buffer flickers.
    assert _wrong_area(key, monkeypatch) < 0.05


def test_ship_hulls_are_closed_and_face_outward():
    calls = []
    original = um._hull

    def spy(b, *args, **kwargs):
        start = len(b.faces)
        original(b, *args, **kwargs)
        calls.append((b, start, len(b.faces)))

    for key in ("warship_05", "cargo_01", "tanker_03", "warship_13", "passenger_01"):
        calls.clear()
        um._hull = spy
        try:
            uv._ship(key, uv.specs()[key])
        finally:
            um._hull = original
        b, start, end = calls[0]
        welded = {}
        ids = [welded.setdefault(tuple(np.round(p, 6)), len(welded)) for p in b.verts]
        edges = Counter()
        for face, two in zip(b.faces[start:end], b.sided[start:end]):
            assert not two, key            # plating is one-sided, culled from inside
            ring = [ids[i] for i in face]
            edges.update(zip(ring, ring[1:] + ring[:1]))
        points = {i: p for p, i in welded.items()}
        end = max(abs(p[0]) for p in points.values())

        def collapsed(a, c):
            # A stem or stern drawn in to a line leaves no face to close.
            pa, pc = points[a], points[c]
            return abs(abs(pa[0]) - end) < 1e-6 and pa[0] == pc[0] and pa[2] == pc[2]

        # Every edge is met once each way: closed, consistently wound.
        assert all(n == 1 for n in edges.values()), key
        assert all(edges[(c, a)] == 1 or collapsed(a, c) for a, c in edges), key


def test_the_partition_orders_crossing_faces_and_splits_them():
    b = um._Builder()
    b.plate([(-1, 0, -1), (1, 0, -1), (1, 0, 1), (-1, 0, 1)], "hull")      # y = 0 wall
    b.plate([(0, -1, -1), (0, 1, -1), (0, 1, 1), (0, -1, 1)], "deck")      # x = 0 wall
    tree = model_bsp.Tree(b.mesh(False))
    assert len(tree.faces) == 3                       # one wall cut by the other
    for toward in ((1, 1, 0.2), (-1, 1, 0.2), (1, -1, 0.2), (-1, -1, 0.2)):
        order = [i for kind, i in tree.order(toward) if kind == 0]
        centre = [tree.verts[list(tree.faces[i])].mean(axis=0) @ np.asarray(toward)
                  for i in order]
        # The piece nearest the viewer comes last.
        assert centre[-1] == max(centre)


def test_partitions_are_built_once_and_quickly():
    import time
    for key in ("sub_12", "cargo_02", "warship_05"):
        mesh = um.mesh_for(key)
        start = time.perf_counter()
        tree = model_bsp.tree_for(key, mesh)
        assert time.perf_counter() - start < 0.5
        assert model_bsp.tree_for(key, mesh) is tree
        assert len(tree.faces) < 3 * len(mesh.faces)


def test_browser_builds_the_same_partition_in_real_chromium(tmp_path):
    chromium = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
    if not chromium:
        pytest.skip("Chromium is not installed")
    keys = ("warship_05", "sub_12", "civil_transit")
    expected = {}
    for key in keys:
        data = uv.variant_mesh(key).to_json()
        verts = np.asarray(data["v"], dtype=float).reshape(-1, 3) / 1000
        mesh = um.Mesh(verts, data["f"], ["hull"] * len(data["f"]), [False] * len(data["f"]),
                       [(a, c, "dark") for a, c, _m in data["l"]], data["w"])
        tree = model_bsp.Tree(mesh)
        toward = um._view(1.1, um.ELEVATION_RAD)[2]
        expected[key] = {"faces": len(tree.faces), "lines": len(tree.lines),
                         "order": [[k, i] for k, i in tree.order(toward)][:400]}
    (tmp_path / "js").symlink_to(ROOT / "data" / "commander" / "js")
    (tmp_path / "index.html").write_text("""<!doctype html><html><body><pre id="out"></pre>
<script type="module">
import { buildTree } from "./js/views/model-bsp.js";
import { loadVariant } from "./js/views/model-view.js";
const out = {};
for (const [key, group] of [["warship_05", "naval"], ["sub_12", "subs"], ["civil_transit", "naval"]]) {
  const module = await import(`./js/views/unit-variants-${group}.js`);
  const data = module.VARIANTS[key];
  const verts = [];
  for (let i = 0; i < data.v.length; i += 3) verts.push([data.v[i] / 1000, data.v[i + 1] / 1000, data.v[i + 2] / 1000]);
  const newell = (points) => { const n = [0, 0, 0];
    for (let i = 0; i < points.length; i += 1) { const a = points[i], b = points[(i + 1) % points.length];
      n[0] += (a[1] - b[1]) * (a[2] + b[2]); n[1] += (a[2] - b[2]) * (a[0] + b[0]); n[2] += (a[0] - b[0]) * (a[1] + b[1]); }
    const l = Math.hypot(...n); return l > 1e-12 ? n.map((c) => c / l) : [0, 0, 1]; };
  const tree = buildTree(verts, data.f, data.f.map((f) => newell(f.map((k) => verts[k]))), data.l);
  const yaw = 1.1, e = __ELEVATION__;
  const toward = [-Math.cos(e) * Math.sin(yaw), -Math.cos(e) * Math.cos(yaw), Math.sin(e)];
  out[key] = {faces: tree.faces.length, lines: tree.lines.length, order: tree.order(toward).slice(0, 400)};
}
out.loaded = await loadVariant("warship_05");
document.getElementById("out").textContent = JSON.stringify(out);
</script></body></html>""".replace("__ELEVATION__", repr(um.ELEVATION_RAD)), encoding="utf-8")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path))
    handler.log_message = lambda *args: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        result = subprocess.run(
            [chromium, "--headless", "--no-sandbox", "--disable-gpu",
             f"--user-data-dir={tmp_path / 'profile'}", "--virtual-time-budget=8000",
             "--dump-dom", f"http://127.0.0.1:{server.server_address[1]}/index.html"],
            capture_output=True, text=True, timeout=90)
    finally:
        server.shutdown()
    match = re.search(r'<pre id="out">(.*?)</pre>', result.stdout, re.S)
    assert match and match.group(1), result.stderr[-2000:]
    out = json.loads(match.group(1).replace("&quot;", '"'))
    assert out.pop("loaded") is True
    assert out == expected
