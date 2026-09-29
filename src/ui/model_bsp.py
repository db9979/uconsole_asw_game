"""Exact back-to-front order for the 3D models (``unit_models``).

A sort by face centre draws a far face over a near one wherever parts of
different size overlap (a deck over its superstructure, a wing through the
fuselage), so the models looked hollow.  A binary space partition built
once per mesh splits the faces that cross each other and gives, for any
view direction, an order in which every face is drawn after all faces
behind it.  The browser (``data/commander/js/views/model-bsp.js``) builds
the same tree with the same rules.
"""

from __future__ import annotations

import numpy as np

# Plane distance under which a point counts as on the plane (model units,
# the model is one long).
EPS = 1e-6
# Splitter candidates tried per node (evenly spread over its faces).
CANDIDATES = 8
# A split costs this many faces of imbalance.
SPLIT_WEIGHT = 3


class Tree:
    """Split faces and lines of one mesh and the partition over them.

    ``verts`` extends the mesh's vertices by the split points; ``faces`` are
    vertex index tuples with ``face_src`` the mesh face each piece comes
    from (material, normal, two-sidedness); ``lines`` likewise with
    ``line_src``.  Node ``k`` has the plane ``normal[k]·p = dist[k]``, the
    faces and lines lying in it and its ``back``/``front`` children (-1:
    none)."""

    def __init__(self, mesh):
        self._v = np.array(mesh.verts, dtype=float).reshape(-1, 3)
        self._count = len(self._v)
        self.faces: list[tuple] = []
        self.face_src: list[int] = []
        self.lines: list[tuple] = []
        self.line_src: list[int] = []
        self._normal, self._dist, self.node_faces, self.node_lines = [], [], [], []
        self._back, self._front = [], []
        items = [("f", tuple(face), i) for i, face in enumerate(mesh.faces)]
        items += [("l", (a, b), j) for j, (a, b, _mat) in enumerate(mesh.lines)]
        self._planes = mesh.normals
        self.root = self._build(items)
        self.verts = self._v[:self._count].copy()
        self.normal = np.asarray(self._normal, dtype=float).reshape(-1, 3)
        self.dist = np.asarray(self._dist, dtype=float)
        self.back = self._back
        self.front = self._front
        del self._v, self._normal, self._dist, self._back, self._front, self._planes

    # -- construction -----------------------------------------------------
    def _plane(self, item) -> tuple:
        _kind, idx, src = item
        normal = self._planes[src]
        return normal, float(self._v[idx[0]] @ normal)

    @staticmethod
    def _sides(points, offsets, normal, dist) -> tuple:
        """Highest and lowest signed distance of every item's corners."""
        s = points @ normal - dist
        return np.maximum.reduceat(s, offsets), np.minimum.reduceat(s, offsets)

    def _choose(self, items, faces, points, offsets) -> int:
        """Index (into ``items``) of the splitter: few splits, balanced."""
        if len(faces) <= 2:
            return faces[0]
        step = max(1, len(faces) // CANDIDATES)
        best, best_score = faces[0], None
        for c in faces[::step][:CANDIDATES]:
            hi, lo = self._sides(points, offsets, *self._plane(items[c]))
            split = (hi > EPS) & (lo < -EPS)
            front = (lo >= -EPS) & (hi > EPS)
            back = (hi <= EPS) & (lo < -EPS)
            split[c] = front[c] = back[c] = False
            score = SPLIT_WEIGHT * int(split.sum()) + abs(int(front.sum()) - int(back.sum()))
            if best_score is None or score < best_score:
                best, best_score = c, score
        return best

    def _cut(self, a: int, b: int, sa: float, sb: float) -> int:
        if self._count == len(self._v):
            self._v = np.concatenate([self._v, np.zeros_like(self._v)])
        t = sa / (sa - sb)
        self._v[self._count] = self._v[a] + t * (self._v[b] - self._v[a])
        self._count += 1
        return self._count - 1

    def _split(self, item, normal, dist) -> tuple:
        """(back, front) pieces of an item that crosses the plane."""
        kind, idx, src = item
        s = [float(self._v[k] @ normal) - dist for k in idx]
        if kind == "l":
            a, b = idx
            m = self._cut(a, b, s[0], s[1])
            if s[0] > 0:
                return (kind, (m, b), src), (kind, (a, m), src)
            return (kind, (a, m), src), (kind, (m, b), src)
        front, back = [], []
        n = len(idx)
        for i in range(n):
            j = (i + 1) % n
            a, sa, sb = idx[i], s[i], s[j]
            if sa > EPS:
                front.append(a)
            elif sa < -EPS:
                back.append(a)
            else:
                front.append(a)
                back.append(a)
            if (sa > EPS and sb < -EPS) or (sa < -EPS and sb > EPS):
                m = self._cut(a, idx[j], sa, sb)
                front.append(m)
                back.append(m)
        return ((kind, tuple(back), src) if len(back) >= 3 else None,
                (kind, tuple(front), src) if len(front) >= 3 else None)

    def _build(self, items) -> int:
        """Iterative build (convex parts make the tree deep)."""
        root = [-1]
        stack = [(items, root, 0)]
        while stack:
            items, slot, index = stack.pop()
            faces = [i for i, item in enumerate(items) if item[0] == "f"]
            if not faces:
                slot[index] = self._node(np.zeros(3), 0.0, [], items)
                continue
            lengths = [len(item[1]) for item in items]
            offsets = np.cumsum([0] + lengths[:-1])
            points = self._v[[k for item in items for k in item[1]]]
            c = self._choose(items, faces, points, offsets)
            normal, dist = self._plane(items[c])
            hi, lo = self._sides(points, offsets, normal, dist)
            on_mask = (hi <= EPS) & (lo >= -EPS)
            # A slightly warped quad still lies in its own plane.
            on_mask[c] = True
            on, back, front = [], [], []
            for i, item in enumerate(items):
                if on_mask[i]:
                    on.append(item)
                elif hi[i] <= EPS:
                    back.append(item)
                elif lo[i] >= -EPS:
                    front.append(item)
                else:
                    piece_back, piece_front = self._split(item, normal, dist)
                    if piece_back is not None:
                        back.append(piece_back)
                    if piece_front is not None:
                        front.append(piece_front)
            node = self._node(normal, dist, [i for i in on if i[0] == "f"],
                              [i for i in on if i[0] == "l"])
            slot[index] = node
            if back:
                stack.append((back, self._back, node))
            if front:
                stack.append((front, self._front, node))
        return root[0]

    def _node(self, normal, dist, faces, lines) -> int:
        k = len(self._normal)
        self._normal.append(tuple(float(c) for c in normal))
        self._dist.append(float(dist))
        # Coplanar faces keep the mesh's order (a pad drawn over its deck).
        ids = []
        for _kind, idx, src in sorted(faces, key=lambda item: item[2]):
            self.faces.append(idx)
            self.face_src.append(src)
            ids.append(len(self.faces) - 1)
        self.node_faces.append(ids)
        lids = []
        for _kind, idx, src in lines:
            self.lines.append(idx)
            self.line_src.append(src)
            lids.append(len(self.lines) - 1)
        self.node_lines.append(lids)
        self._back.append(-1)
        self._front.append(-1)
        return k

    # -- traversal --------------------------------------------------------
    def order(self, toward) -> list:
        """``(kind, index)`` back to front for a viewer far off in model
        direction ``toward``: kind 0 a face, 1 a line."""
        if self.root < 0:
            return []
        viewer_front = (self.normal @ np.asarray(toward, dtype=float)) > 0.0
        out = []
        stack = [(self.root, False)]
        while stack:
            node, emit = stack.pop()
            if emit:
                out.extend((0, i) for i in self.node_faces[node])
                out.extend((1, j) for j in self.node_lines[node])
                continue
            near, far = ((self._front_of(node), self._back_of(node)) if viewer_front[node]
                         else (self._back_of(node), self._front_of(node)))
            if near >= 0:
                stack.append((near, False))
            stack.append((node, True))
            if far >= 0:
                stack.append((far, False))
        return out

    def _front_of(self, node: int) -> int:
        return self.front[node]

    def _back_of(self, node: int) -> int:
        return self.back[node]


_TREES: dict = {}


def tree_for(key: str, mesh) -> Tree:
    """The mesh's partition, built on first use and kept (meshes are
    fixed per key)."""
    tree = _TREES.get(key)
    if tree is None or tree.mesh_id != id(mesh):
        tree = Tree(mesh)
        tree.mesh_id = id(mesh)
        _TREES[key] = tree
    return tree
