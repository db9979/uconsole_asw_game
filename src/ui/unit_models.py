"""Schematic 3D models of the catalog units for the analyzer and editors.

The surface ships and the submarine are lofted from the lookout side
profiles (:mod:`src.ui.silhouettes`): the profile gives every height, a plan
shape gives the beam, and each superstructure block is extruded across the
deck.  Aircraft, torpedoes, decoys and animals are bodies of revolution with
flat plates for wings, fins and flukes.  Everything is display only: models
are built once per class from constants, the turn angle comes from the
caller's wall clock and nothing here reads an entity or simulation state.

Model space: ``x`` forward (bow at +x), ``y`` to port, ``z`` up; the unit
is the overall length, so every model runs from ``x = -0.5`` to ``0.5``.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import numpy as np
import pygame

from src.sensors import lookout_id
from src.ui import model_bsp, silhouettes

# The lookout's classes (the same silhouettes the eyepieces draw) plus the
# units no lookout ever sees: torpedoes, decoys and animals.
MODEL_CLASSES = ("warship", "merchant", "unknown", "submarine", "aircraft",
                 "torpedo", "decoy", "whale", "fish", "jellyfish")

MATERIALS = {
    "hull": (150, 160, 168), "deck": (104, 112, 116), "super": (182, 190, 196),
    "bottom": (126, 54, 46), "dark": (46, 50, 54),
    "merchant": (44, 72, 102), "white": (226, 226, 216), "tanker": (122, 44, 38),
    "box_a": (156, 72, 56), "box_b": (62, 94, 134), "box_c": (72, 124, 88),
    "box_d": (176, 124, 52), "boat": (208, 112, 44),
    "sub": (80, 88, 96), "air": (196, 202, 208), "mil": (122, 134, 132),
    "canopy": (58, 92, 124), "torpedo": (86, 100, 78), "decoy": (170, 150, 70),
    "whale": (72, 84, 100), "belly": (150, 160, 170), "fish": (150, 172, 184),
    "jelly": (176, 146, 206), "pad": (78, 96, 86), "black": (44, 48, 54),
}
MATERIAL_NAMES = tuple(MATERIALS)
# Sea around a floating hull: an outline ring at the waterline.
WATER = (42, 96, 116)
WATER_RING = 0.56
# The aircraft silhouette hovers over its waterline; its model is centred.
AIRCRAFT_LIFT = 0.555
# Camera elevation above the horizon and turn rate of the turntable.
ELEVATION_RAD = math.radians(22.0)
TURN_RAD_S = 0.45
# Light from the upper left, in view space (x right, y up, z towards viewer).
_LIGHT = np.array([-0.45, 0.62, 0.64]) / np.linalg.norm([-0.45, 0.62, 0.64])


class Mesh:
    """Indexed polygons with per-face material and precomputed normals."""

    def __init__(self, verts, faces, mats, sided, lines, floating):
        self.verts = np.asarray(verts, dtype=float)
        self.faces = [tuple(face) for face in faces]
        self.mats = list(mats)
        self.sided = np.asarray(sided, dtype=bool)
        self.lines = list(lines)
        self.floating = floating
        normals, centroids = [], []
        for face in self.faces:
            pts = self.verts[list(face)]
            normals.append(_newell(pts))
            centroids.append(pts.mean(axis=0))
        self.normals = np.asarray(normals, dtype=float).reshape(-1, 3)
        self.centroids = np.asarray(centroids, dtype=float).reshape(-1, 3)
        self.radius = float(np.max(np.linalg.norm(self.verts, axis=1)))
        self.colors = np.asarray([MATERIALS[m] for m in self.mats], dtype=float).reshape(-1, 3)

    def to_json(self) -> dict:
        """Plain data for the browser renderer (coordinates in thousandths)."""
        # Corners at the same (rounded) point are sent once.
        index, verts, remap = {}, [], []
        for p in self.verts:
            key = tuple(int(round(float(c) * 1000)) for c in p)
            if key not in index:
                index[key] = len(index)
                verts.extend(key)
            remap.append(index[key])
        return {
            "v": verts,
            "f": [[remap[k] for k in face] for face in self.faces],
            "m": [MATERIAL_NAMES.index(m) for m in self.mats],
            "s": [i for i, two in enumerate(self.sided) if two],
            "l": [[remap[a], remap[b], MATERIAL_NAMES.index(m)] for a, b, m in self.lines],
            "w": self.floating,
        }


def _newell(pts) -> np.ndarray:
    n = np.zeros(3)
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        n += ((a[1] - b[1]) * (a[2] + b[2]), (a[2] - b[2]) * (a[0] + b[0]),
              (a[0] - b[0]) * (a[1] + b[1]))
    length = float(np.linalg.norm(n))
    return n / length if length > 1e-12 else np.array([0.0, 0.0, 1.0])


class _Builder:
    def __init__(self):
        self.verts, self.faces, self.mats, self.sided, self.lines = [], [], [], [], []

    def vertex(self, p) -> int:
        self.verts.append(tuple(float(c) for c in p))
        return len(self.verts) - 1

    def face(self, idx, mat, center=None, two_sided=False) -> None:
        idx = list(idx)
        # Drop repeated corners (a pointed bow or stern collapses a quad).
        clean = [i for k, i in enumerate(idx)
                 if self.verts[i] != self.verts[idx[k - 1]]]
        if len(clean) < 3:
            return
        pts = np.array([self.verts[i] for i in clean])
        if float(np.linalg.norm(np.cross(pts[1:-1] - pts[0], pts[2:] - pts[0]).sum(axis=0))) < 1e-10:
            return  # Flat to a line: a collapsed stem or stern section.
        if center is not None:
            if np.dot(_newell(pts), pts.mean(axis=0) - np.asarray(center)) < 0:
                clean.reverse()
        self.faces.append(clean)
        self.mats.append(mat)
        self.sided.append(two_sided)

    def line(self, p, q, mat="dark") -> None:
        self.lines.append((self.vertex(p), self.vertex(q), mat))

    def plate(self, points, mat) -> None:
        self.face([self.vertex(p) for p in points], mat, two_sided=True)

    def mesh(self, floating: bool) -> Mesh:
        return Mesh(self.verts, self.faces, self.mats, self.sided, self.lines, floating)


def _x(u: float) -> float:
    """Hull unit (0 bow .. 1 stern) to model x (bow at +0.5)."""
    return 0.5 - u


def _envelope(poly, u: float) -> tuple:
    """Lowest and highest ``v`` of polygon ``poly`` on the vertical at ``u``."""
    hits = []
    for (u0, v0), (u1, v1) in zip(poly, poly[1:] + poly[:1]):
        if min(u0, u1) - 1e-9 <= u <= max(u0, u1) + 1e-9:
            if abs(u1 - u0) < 1e-9:
                hits += [v0, v1]
            else:
                hits.append(v0 + (v1 - v0) * (u - u0) / (u1 - u0))
    return (min(hits), max(hits)) if hits else (0.0, 0.0)


def _plan(u: float, entrance: float = 0.32, transom: float = 0.72) -> float:
    """Half-beam fraction along the hull: fine bow, parallel body, transom."""
    if u < entrance:
        return max(0.02, math.sin(0.5 * math.pi * u / entrance) ** 0.85)
    if u > 0.82:
        return 1.0 - (1.0 - transom) * ((u - 0.82) / 0.18) ** 2
    return 1.0


# Points per side of a hull section (deck edge to keel, keel excluded).
SECTION_SIDE = 4


def _hull(b: _Builder, poly, beam: float, draft: float, *, side="hull",
          deck="deck", stations: int = 18, transom: float = 0.72,
          entrance: float = 0.32) -> None:
    """Loft a hull: the profile's top edge is the deck, its lower edge the
    stem; below the waterline a rounded underbody down to ``draft``."""
    us = [0.0] + [((i + 0.5) / stations) ** 1.0 for i in range(stations)] + [1.0]
    rings = []
    for u in us:
        low, top = _envelope(poly, u)
        half = beam * _plan(u, entrance, transom)
        depth = draft * (0.35 + 0.65 * _plan(u, 0.22, 0.4)) if low <= 1e-6 else 0.0
        zb = low
        x = _x(u)
        if zb > 1e-6 and u < 0.5:
            # The raked stem: a V from the deck edge down to the stem line.
            rise = top - zb
            flank = [(half * (1.0 - t), zb + rise * (1.0 - t) ** 1.6)
                     for t in (k / SECTION_SIDE for k in range(SECTION_SIDE))]
            section = [(-y, z) for y, z in flank] + [(0.0, zb)] + flank[::-1]
        else:
            # A round bilge into a flat floor: sampled closely enough that
            # the underbody reads as one smooth surface.
            bilge = [(half * math.cos(a) ** 0.55,
                      zb - depth * math.sin(a) ** 0.8)
                     for a in (math.pi * k / 6 for k in range(1, 3))]
            section = ([(-half, top), (-half, zb)] + [(-y, z) for y, z in bilge]
                       + [(0.0, zb - depth)] + [(y, z) for y, z in reversed(bilge)]
                       + [(half, zb), (half, top)])
        rings.append([b.vertex((x, y, z)) for y, z in section])
    # Every section runs the same way round, so one winding closes the
    # plating outward everywhere (a per-face guess flips folded stem faces).
    mid = len(rings) // 2
    probe = [b.verts[i] for i in (rings[mid][2], rings[mid][3], rings[mid + 1][3],
                                  rings[mid + 1][2])]
    outward = _newell(np.array(probe))[2] < 0.0
    for i in range(len(rings) - 1):
        r0, r1 = rings[i], rings[i + 1]
        cx = 0.5 * (b.verts[r0[0]][0] + b.verts[r1[0]][0])
        for k in range(len(r0) - 1):
            zmid = (b.verts[r0[k]][2] + b.verts[r0[k + 1]][2]) / 2
            mat = "bottom" if zmid < -1e-6 else side
            quad = (r0[k], r0[k + 1], r1[k + 1], r1[k])
            b.face(quad if outward else quad[::-1], mat)
        b.face((r0[-1], r1[-1], r1[0], r0[0]), deck, center=(cx, 0.0, -1.0))
    for ring, inner in ((rings[-1], rings[-2]), (rings[0], rings[1])):
        zs = [b.verts[i][2] for i in ring]
        b.face(ring, side, center=(b.verts[inner[0]][0], 0.0, 0.5 * (min(zs) + max(zs))))


def _prism(b: _Builder, poly, half_width: float, mat: str, y: float = 0.0) -> None:
    """Extrude a profile polygon ``(u, v)`` across ``y ± half_width``."""
    left = [b.vertex((_x(u), y + half_width, v)) for u, v in poly]
    right = [b.vertex((_x(u), y - half_width, v)) for u, v in poly]
    cu = sum(u for u, _v in poly) / len(poly)
    cv = sum(v for _u, v in poly) / len(poly)
    center = (_x(cu), y, cv)
    b.face(left, mat, center=center)
    b.face(right, mat, center=center)
    n = len(poly)
    for k in range(n):
        b.face((left[k], left[(k + 1) % n], right[(k + 1) % n], right[k]), mat,
               center=center)


def _blocks(b: _Builder, blocks, beam: float, mats, overrides=None) -> None:
    """Superstructure blocks: as wide as the deck allows, masts thin."""
    overrides = overrides or {}
    for index, poly in enumerate(blocks):
        us = [u for u, _v in poly]
        if index in overrides:
            half, y = overrides[index]
            for offset in ((y, -y) if y else (0.0,)):
                _prism(b, poly, half, mats[index], offset)
            continue
        uc = (min(us) + max(us)) / 2
        half = min(0.8 * beam * _plan(uc), 0.5 * (max(us) - min(us)))
        _prism(b, poly, max(0.003, half), mats[index])


def _revolve(b: _Builder, radii, mat: str, *, segments: int = 12, z0: float = 0.0,
             y0: float = 0.0, x0: float = 0.0, length: float = 1.0,
             zscale: float = 1.0, belly: str | None = None) -> None:
    """Body of revolution along x from ``(u, r)`` samples (u 0 = nose)."""
    rings = []
    for u, r in radii:
        x = x0 + (0.5 - u) * length
        if r <= 1e-6:
            rings.append([b.vertex((x, y0, z0))] * segments)
            continue
        rings.append([b.vertex((x, y0 + r * length * math.cos(2 * math.pi * k / segments),
                                z0 + zscale * r * length * math.sin(2 * math.pi * k / segments)))
                      for k in range(segments)])
    for i in range(len(rings) - 1):
        cx = x0 + (0.5 - (radii[i][0] + radii[i + 1][0]) / 2) * length
        for k in range(segments):
            k1 = (k + 1) % segments
            lower = math.sin(2 * math.pi * (k + 0.5) / segments) < -0.2
            b.face((rings[i][k], rings[i][k1], rings[i + 1][k1], rings[i + 1][k]),
                   belly if belly and lower else mat, center=(cx, y0, z0))
    for ring, u in ((rings[0], radii[0][0]), (rings[-1], radii[-1][0])):
        if len(set(ring)) > 2:
            b.face(ring, mat, center=(x0 + (0.5 - 0.5) * length, y0, z0))


def _radii(fn, n: int = 24):
    return [(i / n, fn(i / n)) for i in range(n + 1)]


def _ship(profile, beam, draft, mats, *, side="hull", deck="deck",
          overrides=None, lines=True, extra=None, transom=0.72) -> Mesh:
    b = _Builder()
    _hull(b, profile["hull"], beam, draft, side=side, deck=deck, transom=transom)
    blocks = list(profile["blocks"]) + list(extra or [])
    _blocks(b, blocks, beam, mats, overrides)
    if lines:
        for (u0, v0), (u1, v1) in profile["lines"]:
            b.line((_x(u0), 0.0, v0), (_x(u1), 0.0, v1))
    return b.mesh(True)


def _warship() -> Mesh:
    p = silhouettes.PROFILES["warship"]
    mats = ["super"] * len(p["blocks"])
    mats[10] = "boat"                 # RHIB, one each side
    mats[6] = "super"
    b = _Builder()
    beam = 0.064
    _hull(b, p["hull"], beam, 0.034)
    _blocks(b, p["blocks"], beam, mats, {10: (0.012, 0.05)})
    for (u0, v0), (u1, v1) in p["lines"][:-1]:
        b.line((_x(u0), 0.0, v0), (_x(u1), 0.0, v1))
    # Funnel cap and radar antenna.
    fu, fv = p["funnel_top"]
    b.plate([(_x(fu - 0.03), 0.02, fv), (_x(fu + 0.03), 0.02, fv),
             (_x(fu + 0.03), -0.02, fv), (_x(fu - 0.03), -0.02, fv)], "dark")
    ru, rv, half = p["radar"]
    b.plate([(_x(ru), -half, rv - 0.006), (_x(ru), half, rv - 0.006),
             (_x(ru), half, rv + 0.006), (_x(ru), -half, rv + 0.006)], "dark")
    return b.mesh(True)


_MERCHANT = silhouettes.PROFILES["merchant"]
_HOUSE = _MERCHANT["blocks"][6:]      # house, wings, funnel, fore mast
_FORECASTLE = _MERCHANT["blocks"][0]


def _merchant() -> Mesh:
    p = _MERCHANT
    boxes = ["box_a", "box_b", "box_c", "box_d", "box_a"]
    mats = ["merchant"] + boxes + ["white", "white", "tanker", "white"]
    return _ship(p, 0.074, 0.042, mats, side="merchant",
                 overrides={7: (0.074, 0.0), 9: (0.003, 0.0)}, lines=False)


def _unknown() -> Mesh:
    p = silhouettes.PROFILES["unknown"]
    return _ship(p, 0.14, 0.07, ["white", "white", "deck"], side="merchant",
                 overrides={0: (0.1, 0.0), 1: (0.004, 0.0), 2: (0.08, 0.0)},
                 transom=0.8)


def _submarine() -> Mesh:
    p = silhouettes.PROFILES["submarine"]
    b = _Builder()
    radii = [(u, _envelope(p["hull"], u)[1]) for u in
             [i / 20 for i in range(21)]]
    _revolve(b, radii, "sub", segments=12)
    _prism(b, p["blocks"][0], 0.012, "sub")
    # Sail planes, X rudders and the retracted mast.
    for side in (1, -1):
        b.plate([(_x(0.215), 0.0, 0.1), (_x(0.26), 0.0, 0.1),
                 (_x(0.255), side * 0.05, 0.1), (_x(0.228), side * 0.05, 0.1)], "sub")
        for up in (1, -1):
            b.plate([(_x(0.90), 0.0, 0.0), (_x(0.99), 0.0, 0.0),
                     (_x(0.99), side * 0.055, up * 0.055),
                     (_x(0.94), side * 0.05, up * 0.05)], "sub")
    b.line((_x(0.27), 0.0, 0.132), (_x(0.27), 0.0, 0.16))
    return b.mesh(False)


def _helicopter() -> Mesh:
    """The lookout's aircraft: cabin and tail boom lofted from its profile,
    rotor head, main and tail rotor blades and the skids."""
    p = silhouettes.PROFILES["aircraft"]
    b = _Builder()
    lift = AIRCRAFT_LIFT
    rings = []
    for i in range(21):
        u = i / 20
        low, top = _envelope(p["hull"], u)
        half = 0.5 * (top - low) * (1.0 if u < 0.55 else 0.55)
        mid = 0.5 * (top + low) - lift
        rings.append([b.vertex((_x(u), half * math.cos(a), mid + 0.5 * (top - low) * math.sin(a)))
                      for a in [k * math.pi / 5 for k in range(10)]])
    for i in range(len(rings) - 1):
        cx = 0.5 * (b.verts[rings[i][0]][0] + b.verts[rings[i + 1][0]][0])
        for k in range(10):
            k1 = (k + 1) % 10
            b.face((rings[i][k], rings[i][k1], rings[i + 1][k1], rings[i + 1][k]), "mil",
                   center=(cx, 0.0, 0.55 - lift))
    for ring in (rings[0], rings[-1]):
        b.face(ring, "mil", center=(0.0, 0.0, 0.55 - lift))
    head = [(u, v - lift) for u, v in p["blocks"][0]]
    _prism(b, head, 0.02, "dark")
    hu, hv, half = p["rotor"]
    for angle in (0.35, 0.35 + math.pi / 2):
        ca, sa = math.cos(angle), math.sin(angle)
        wx, wy = -sa * 0.018, ca * 0.018
        x0, y0 = _x(hu), 0.0
        b.plate([(x0 - ca * half + wx, y0 - sa * half + wy, hv - lift),
                 (x0 + ca * half + wx, y0 + sa * half + wy, hv - lift),
                 (x0 + ca * half - wx, y0 + sa * half - wy, hv - lift),
                 (x0 - ca * half - wx, y0 - sa * half - wy, hv - lift)], "dark")
    tu, tv, tr = p["tail_rotor"]
    b.plate([(_x(tu) - tr, 0.03, tv - lift - 0.008), (_x(tu) + tr, 0.03, tv - lift + 0.008),
             (_x(tu) + tr, 0.03, tv - lift - 0.008), (_x(tu) - tr, 0.03, tv - lift + 0.008)], "dark")
    for (u0, v0), (u1, v1) in p["lines"]:
        for side in (0.05, -0.05):
            b.line((_x(u0), side, v0 - lift), (_x(u1), side, v1 - lift))
    return b.mesh(False)


def _torpedo(radius=0.042, mat="torpedo", decoy=False) -> Mesh:
    b = _Builder()
    nose = 0.06 if decoy else 0.12

    def r(u):
        if u < nose:
            return radius * math.sqrt(max(0.0, 1.0 - ((nose - u) / nose) ** 2))
        if u > 0.86:
            return radius * (1.0 - 0.6 * (u - 0.86) / 0.14)
        return radius
    _revolve(b, _radii(r, 12), mat, segments=10)
    for angle in range(4):
        a = math.pi / 4 + angle * math.pi / 2
        cy, cz = math.cos(a), math.sin(a)
        b.plate([(-0.36, cy * radius * 0.8, cz * radius * 0.8),
                 (-0.47, cy * radius * 0.6, cz * radius * 0.6),
                 (-0.48, cy * radius * 1.9, cz * radius * 1.9),
                 (-0.42, cy * radius * 1.9, cz * radius * 1.9)], "dark")
    return b.mesh(False)


def _whale() -> Mesh:
    b = _Builder()

    def r(u):
        if u < 0.2:
            return 0.085 * math.sqrt(max(0.0, 1.0 - ((0.2 - u) / 0.2) ** 2)) + 0.01
        return max(0.004, 0.095 * (1.0 - ((u - 0.2) / 0.8) ** 1.6))
    _revolve(b, _radii(r, 18), "whale", segments=10, zscale=0.8, belly="belly")
    b.plate([(-0.44, 0.0, 0.0), (-0.52, 0.13, 0.01), (-0.55, 0.11, 0.01),
             (-0.5, 0.0, 0.0), (-0.55, -0.11, 0.01), (-0.52, -0.13, 0.01)], "whale")
    for side in (1, -1):
        b.plate([(0.18, side * 0.07, -0.03), (0.1, side * 0.07, -0.035),
                 (0.02, side * 0.2, -0.07), (0.06, side * 0.2, -0.07)], "whale")
    b.plate([(-0.18, 0.0, 0.05), (-0.26, 0.0, 0.05), (-0.25, 0.0, 0.085)], "whale")
    return b.mesh(False)


# Where the fish of a school swim, as (x, y, z, scale): fixed, not random.
_SCHOOL = ((0.3, 0.0, 0.02, 1.0), (0.12, 0.16, -0.04, 0.9), (0.1, -0.15, 0.06, 0.95),
           (-0.08, 0.02, -0.1, 1.0), (-0.1, 0.24, 0.08, 0.85), (-0.12, -0.26, -0.02, 0.9),
           (-0.3, 0.1, 0.0, 0.95), (-0.32, -0.12, 0.1, 0.8), (0.28, -0.3, -0.08, 0.85))


def _fish() -> Mesh:
    b = _Builder()
    for x, y, z, s in _SCHOOL:
        _revolve(b, _radii(lambda u: 0.18 * math.sin(math.pi * min(1.0, u * 1.15)) + 0.001, 6),
                 "fish", segments=6, length=0.2 * s, x0=x, y0=y, z0=z, zscale=1.2,
                 belly="belly")
        tail = x - 0.1 * s
        b.plate([(tail, y, z), (tail - 0.05 * s, y, z + 0.03 * s),
                 (tail - 0.05 * s, y, z - 0.03 * s)], "fish")
    return b.mesh(False)


def _jellyfish() -> Mesh:
    b = _Builder()
    segments, rings = 14, 7
    ring_idx = []
    for i in range(rings + 1):
        phi = 0.5 * math.pi * i / rings          # 0 = crown, pi/2 = rim
        r, z = 0.34 * math.sin(phi), 0.22 * math.cos(phi) + 0.05
        ring_idx.append([b.vertex((r * math.cos(2 * math.pi * k / segments),
                                   r * math.sin(2 * math.pi * k / segments), z))
                         for k in range(segments)])
    for i in range(rings):
        for k in range(segments):
            k1 = (k + 1) % segments
            b.face((ring_idx[i][k], ring_idx[i][k1], ring_idx[i + 1][k1],
                    ring_idx[i + 1][k]), "jelly", center=(0.0, 0.0, 0.0), two_sided=True)
    for k in range(0, segments, 2):
        a = 2 * math.pi * k / segments
        px, py = 0.3 * math.cos(a), 0.3 * math.sin(a)
        prev = (px, py, 0.05)
        for j in range(1, 6):
            point = (px * (1 - 0.08 * j) + 0.03 * math.sin(j + k),
                     py * (1 - 0.08 * j), 0.05 - 0.09 * j)
            b.line(prev, point, "jelly")
            prev = point
    return b.mesh(False)


_BUILDERS = {
    "warship": _warship, "merchant": _merchant, "unknown": _unknown,
    "submarine": _submarine, "aircraft": _helicopter,
    "torpedo": _torpedo, "decoy": lambda: _torpedo(0.07, "decoy", decoy=True),
    "whale": _whale, "fish": _fish, "jellyfish": _jellyfish,
}
_CACHE: dict[str, Mesh] = {}


def mesh_for(cls: str) -> Mesh:
    """The model of ``cls``, a class or a catalog type with its own variant
    (``src/ui/unit_variants.py``); anything else gets the small craft.
    Built once; the cache holds at most one mesh per entry of
    ``MODEL_CLASSES``."""
    if cls not in _BUILDERS:
        from src.ui import unit_variants
        variant = unit_variants.variant_mesh(cls) if isinstance(cls, str) else None
        if variant is not None:
            return variant
        cls = "unknown"
    mesh = _CACHE.get(cls)
    if mesh is None:
        mesh = _CACHE[cls] = _BUILDERS[cls]()
    return mesh


# The eyepiece class of what the lookout recognises (as src/ui/stations/bridge.py).
_LOOKOUT_WARSHIPS = ("WARSHIP", "CARRIER", "CRUISER", "DESTROYER", "FRIGATE",
                     "CORVETTE", "NAVAL_AUXILIARY", "MINE_WARFARE")
_LOOKOUT_MERCHANTS = ("MERCHANT", "TANKER", "CARGO", "PASSENGER")
_ANIMALS = {"fish_school": "fish", "jellyfish": "jellyfish"}


def model_class(kind: str, key: str = "", *, category: str | None = None,
                name: str = "") -> str:
    """Model class of a profile: ``kind`` is the unit editor's profile kind
    (``sub``, ``surface``, ``aircraft``, ``animal``, ``torpedo``, ``decoy``).
    Surface ships, submarines and aircraft get the silhouette the lookout
    draws for them."""
    if kind == "sub":
        return "submarine"
    if kind == "surface":
        profile = SimpleNamespace(key=key.rsplit(".", 1)[-1], category=category or "",
                                  name=name)
        recognized = lookout_id.surface_classes(profile)[0]
        if recognized in _LOOKOUT_WARSHIPS:
            return "warship"
        return "merchant" if recognized in _LOOKOUT_MERCHANTS else "unknown"
    if kind == "aircraft":
        return "aircraft"
    if kind == "animal":
        short = key.rsplit(".", 1)[-1]
        return _ANIMALS.get(short, "fish" if "fish" in short else
                            "jellyfish" if "jelly" in short else "whale")
    if kind in ("torpedo", "decoy"):
        return kind
    return "unknown"


_RESOURCE_KINDS = {"subs.json": "sub", "warships.json": "surface",
                   "civilians.json": "surface", "aircraft.json": "aircraft",
                   "animals.json": "animal", "torpedoes.json": "torpedo",
                   "decoys.json": "decoy"}


def catalog_model_classes(cat) -> dict:
    """Model class of every analyzer profile of catalog ``cat``, by key."""
    result = {}
    for key, resource in cat.profile_resources.items():
        kind = _RESOURCE_KINDS.get(resource, "")
        surface = cat.surfaces.get(key) if kind == "surface" else None
        result[key] = model_class(kind, key, category=getattr(surface, "category", None),
                                  name=str(getattr(surface, "name", "")))
    return result


def model_key(key, cls: str) -> str:
    """The model to draw for catalog type ``key`` of class ``cls``: its own
    variant when it has one, else the class model."""
    from src.ui import unit_variants
    return key if unit_variants.has_variant(key) else cls


def unit_model_class(data) -> str:
    """Model class of a unit editor record (built-in clone or user profile);
    an animal is told apart by its key or, for a clone, by its name."""
    kind, key = str(data.get("profile_kind", "")), str(data.get("key", ""))
    if kind == "animal":
        name = str(data.get("name", "")).lower()
        if "fisch" in name or "fish" in name:
            key = "fish"
        elif "qualle" in name or "jelly" in name:
            key = "jellyfish"
    return model_key(key, model_class(kind, key, category=data.get("category"),
                                      name=str(data.get("name", ""))))


def _view(yaw: float, elevation: float) -> np.ndarray:
    """Rows: screen right, screen up, towards the viewer."""
    cy, sy = math.cos(yaw), math.sin(yaw)
    ce, se = math.cos(elevation), math.sin(elevation)
    turn = np.array([[cy, -sy, 0.0], [sy, cy, 0.0], [0.0, 0.0, 1.0]])
    tilt = np.array([[1.0, 0.0, 0.0], [0.0, se, ce], [0.0, -ce, se]])
    return tilt @ turn


def turn_angle(t: float) -> float:
    """Turntable yaw at display time ``t`` (s), starting bow to the left."""
    return 0.6 + TURN_RAD_S * t


def _shading(mesh, view) -> tuple:
    """Per mesh face: light factor and whether it shows (front faces, and
    both sides of two-sided plates)."""
    normals = mesh.normals @ view.T
    facing = normals[:, 2] > 0.0
    lit = np.where(facing | ~mesh.sided, np.maximum(0.0, normals @ _LIGHT),
                   np.abs(normals @ _LIGHT))
    return 0.34 + 0.66 * lit, facing | mesh.sided


def draw_model(surface: pygame.Surface, rect, cls: str, t: float | None = None, *,
               yaw: float | None = None, elevation: float = ELEVATION_RAD) -> int:
    """Draw model ``cls`` fitted into ``rect``, turning with wall time ``t``
    (seconds, default ``pygame.time.get_ticks()``); returns faces drawn."""
    rect = pygame.Rect(rect)
    if rect.width < 8 or rect.height < 8:
        return 0
    mesh = mesh_for(cls)
    if yaw is None:
        yaw = turn_angle(pygame.time.get_ticks() / 1000.0 if t is None else t)
    view = _view(yaw, elevation)
    tree = model_bsp.tree_for(cls, mesh)
    verts = tree.verts @ view.T
    horizontal = float(np.max(np.linalg.norm(mesh.verts[:, :2], axis=1)))
    vertical = (horizontal * math.sin(elevation)
                + float(np.max(np.abs(mesh.verts[:, 2]))) * math.cos(elevation))
    # Fixed for the model (not the current angle), so it never pulses.
    reach = max(mesh.radius, WATER_RING) if mesh.floating else mesh.radius
    scale = 0.92 * min(rect.width / (2.0 * reach), rect.height / (2.0 * vertical))
    # Weak perspective: nearer parts a little larger.
    persp = 1.0 / (1.0 - verts[:, 2] / (5.0 * mesh.radius))
    sx = rect.centerx + verts[:, 0] * scale * persp
    sy = rect.centery - verts[:, 1] * scale * persp
    shades, visible = _shading(mesh, view)
    shades = np.clip(mesh.colors * shades[:, None], 0, 255).astype(int)
    clip = surface.get_clip()
    surface.set_clip(rect.clip(clip) if clip else rect)
    if mesh.floating:
        ring = [(rect.centerx + scale * WATER_RING * math.cos(a),
                 rect.centery - scale * WATER_RING * math.sin(a) * math.sin(elevation))
                for a in [k * math.pi / 24 for k in range(48)]]
        pygame.draw.lines(surface, WATER, True, ring, 1)
    drawn = 0
    line_w = max(1, int(scale / 260))
    for kind, i in tree.order(view[2]):
        if kind:
            a, b = tree.lines[i]
            mat = mesh.lines[tree.line_src[i]][2]
            pygame.draw.line(surface, MATERIALS[mat] if mat != "dark" else (30, 34, 38),
                             (sx[a], sy[a]), (sx[b], sy[b]), line_w)
            continue
        src = tree.face_src[i]
        if not visible[src]:
            continue
        pygame.draw.polygon(surface, tuple(shades[src]), [(sx[k], sy[k]) for k in tree.faces[i]])
        drawn += 1
    surface.set_clip(clip)
    return drawn


# Turntable updates per second: the uConsole redraws the model at this rate
# and blits the cached picture in between.
TURN_UPDATES_HZ = 12.0


class ModelView:
    """A turning model in a fixed box, redrawn only when its angle steps."""

    def __init__(self):
        self._key = None
        self._surface: pygame.Surface | None = None

    def draw(self, surface: pygame.Surface, rect, cls: str, t: float | None = None,
             background=(0, 0, 0)) -> None:
        rect = pygame.Rect(rect)
        if rect.width < 8 or rect.height < 8:
            return
        now = pygame.time.get_ticks() / 1000.0 if t is None else t
        step = int(now * TURN_UPDATES_HZ)
        key = (cls, rect.size, tuple(background), step)
        if key != self._key or self._surface is None:
            if self._surface is None or self._surface.get_size() != rect.size:
                self._surface = pygame.Surface(rect.size)
            self._surface.fill(background)
            draw_model(self._surface, self._surface.get_rect(), cls,
                       yaw=turn_angle(step / TURN_UPDATES_HZ))
            self._key = key
        surface.blit(self._surface, rect)


# Eyepieces (lookout, binoculars, periscope): the observer looks at a
# vessel from just above the sea, so the view is nearly level.
SCENE_ELEVATION_RAD = math.radians(4.0)
# Below this drawn length the silhouette is drawn instead (no detail left).
SCENE_MIN_PX = 16
SCENE_CACHE_SIZE = 32
# Classes the eyepieces turn by their angle on the bow.
SCENE_CLASSES = ("warship", "merchant", "unknown", "submarine", "aircraft")
_SCENE_CACHE: dict = {}
_COLORKEY = (255, 0, 255)


def scene_yaw(aob_deg: float) -> float:
    """Model yaw for an observer ``aob_deg`` off the bow (starboard
    positive): abeam to starboard the bow points right, bow on at 0."""
    return math.radians(aob_deg - 90.0)


def _scene_sprite(cls: str, length_px: int, aob_deg: float, color, surface_only: bool):
    key = (cls, length_px, aob_deg, tuple(color), surface_only)
    sprite = _SCENE_CACHE.pop(key, None)
    if sprite is None:
        sprite = _render_scene_sprite(cls, length_px, aob_deg, color, surface_only)
        while len(_SCENE_CACHE) >= SCENE_CACHE_SIZE:
            _SCENE_CACHE.pop(next(iter(_SCENE_CACHE)))
    _SCENE_CACHE[key] = sprite
    return sprite


def _render_scene_sprite(cls, length_px, aob_deg, color, surface_only):
    """(surface, origin) of the model lit like the eyepiece: the materials
    darkened to the scene's steel tone and blended with it (haze, night)."""
    mesh = mesh_for(cls)
    view = _view(scene_yaw(aob_deg), SCENE_ELEVATION_RAD)
    tree = model_bsp.tree_for(cls, mesh)
    verts = tree.verts @ view.T
    sx, sy = verts[:, 0] * length_px, -verts[:, 1] * length_px
    left, top = int(math.floor(sx.min())) - 2, int(math.floor(sy.min())) - 2
    width = int(math.ceil(sx.max())) - left + 3
    height = int(math.ceil(sy.max())) - top + 3
    sprite = pygame.Surface((max(1, width), max(1, height)))
    sprite.fill(_COLORKEY)
    sprite.set_colorkey(_COLORKEY)
    shade, visible = _shading(mesh, view)
    steel = np.asarray(color, dtype=float)
    tone = min(1.25, max(0.05, float(steel.mean()) / 150.0))
    shade = shade[:, None]
    shades = np.clip(0.5 * mesh.colors * shade * tone + 0.5 * steel * (0.55 + 0.6 * shade),
                     0, 254).astype(int)
    px, py = sx - left, sy - top
    line_color = tuple(int(c * 0.6) for c in steel)
    for kind, i in tree.order(view[2]):
        if kind:
            a, b = tree.lines[i]
            pygame.draw.line(sprite, line_color, (px[a], py[a]), (px[b], py[b]),
                             max(1, int(length_px / 260)))
            continue
        src = tree.face_src[i]
        if visible[src]:
            pygame.draw.polygon(sprite, tuple(shades[src]),
                                [(px[k], py[k]) for k in tree.faces[i]])
    if surface_only:
        # The hull below the waterline stays in the sea: cut the picture at
        # the waterline (level within a pixel at this elevation).
        cut = -top + 1 + int(math.ceil(0.1 * math.sin(SCENE_ELEVATION_RAD) * length_px))
        if cut < height:
            sprite.fill(_COLORKEY, (0, cut, width, height - cut))
    return sprite, (-left, -top)


class _ScenePoints:
    """Projects silhouette points ``(u, v)`` like the model (for the lights)."""

    def __init__(self, cls, cx, base_y, length_px, aob_deg):
        self.view = _view(scene_yaw(aob_deg), SCENE_ELEVATION_RAD)
        self.cx, self.base_y, self.width = cx, base_y, length_px
        self.lift = AIRCRAFT_LIFT if cls == "aircraft" else 0.0

    def point(self, u: float, v: float) -> tuple:
        x, y, _z = self.view @ np.array([_x(u), 0.0, v - self.lift])
        return (self.cx + x * self.width, self.base_y - y * self.width)


def draw_in_scene(s, cls: str, cx: float, base_y: float, width: float, color, *,
                  aob_deg: float | None, aloft: bool = False, nav: str | None = None,
                  t: float = 0.0, model: str | None = None) -> bool:
    """Draw ``cls`` in an eyepiece turned by the judged angle on the bow,
    ``width`` px long, afloat on ``base_y`` (``aloft``: an aircraft centred
    on it), as the variant of the identified type ``model`` when there is
    one; False when it is too small or not turned, so the caller draws the
    flat silhouette instead."""
    if aob_deg is None or cls not in SCENE_CLASSES or width < SCENE_MIN_PX:
        return False
    length_px = int(width)
    if cls == "aircraft" and not aloft:
        base_y -= 0.25 * length_px          # hovering over the horizon
    surface_only = cls != "aircraft"
    # An identified type is drawn as its own variant (``model``).
    key = model_key(model, cls) if model is not None else cls
    # Colours in steps of 4 so a slowly changing sky rebuilds rarely.
    sprite, (ox, oy) = _scene_sprite(key, length_px, float(aob_deg),
                                     tuple(int(c) // 4 * 4 for c in color), surface_only)
    s.blit(sprite, (int(cx) - ox, int(base_y) - oy))
    if nav is not None:
        from src.ui import unit_variants
        points = unit_variants.ship_nav(key) if key != cls else None
        silhouettes.draw_nav_lights(s, cls, _ScenePoints(cls, cx, base_y, length_px, aob_deg),
                                    length_px, nav, t, nav_points=points)
    return True
