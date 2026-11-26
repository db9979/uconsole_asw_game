"""The ship and submarine models of Tiefenkontakt in the analyzer and eyepieces.

Tiefenkontakt (the browser game, github.com/db9979/tiefenkontakt) builds
detailed low-poly ships with Three.js.  ``tools/build_tk_models.py`` turns
them into the polygon meshes of ``data/unit_models/tiefenkontakt.json.gz``
(our axes, length one, a shared colour palette).  Here a catalog type that
fits one of those designs gets it, stretched to the type's real beam and
draught (``variant_ref``); everything else keeps the model
``src/ui/unit_variants.py`` builds from its spec.  Display only: nothing
here reads an entity or the simulation.
"""

from __future__ import annotations

import gzip
import json
import zlib
# Bound at import: web tests redirect importlib.resources.files to a page copy.
from importlib.resources import files as resource_files

import numpy as np

RESOURCE = ("data.unit_models", "tiefenkontakt.json.gz")
# Coordinates in the file are 1/SCALE of the overall length.
SCALE = 10000
_DATA: dict | None = None


def data() -> dict:
    global _DATA
    if _DATA is None:
        package, name = RESOURCE
        raw = resource_files(package).joinpath(name).read_bytes()
        _DATA = json.loads(gzip.decompress(raw).decode("utf-8"))
    return _DATA


def palette() -> dict:
    """The models' colours as materials ``tk0`` ... for ``unit_models.MATERIALS``."""
    return {f"tk{i}": tuple(c) for i, c in enumerate(data()["palette"])}


def names() -> tuple:
    return tuple(sorted(data()["models"]))


def base_verts(name: str) -> np.ndarray:
    return np.asarray(data()["models"][name]["v"], dtype=float).reshape(-1, 3) / SCALE


# Corvettes, frigates and the smaller destroyers of the catalog get one of
# Tiefenkontakt's escorts (the corvette for the short ones), always the same
# per type; the big destroyers and cruisers keep their own distinct models.
_ESCORTS = ("ffg", "ffk", "ffv")
ESCORT_MAX_M = 160.0


def _pick(spec: dict, options) -> str:
    """A stable choice per spec: catalog entries of one class share it."""
    text = json.dumps({k: v for k, v in spec.items() if k != "name"}, sort_keys=True)
    return options[zlib.crc32(text.encode("utf-8")) % len(options)]


def design_for(key: str, spec: dict) -> str | None:
    """The Tiefenkontakt design catalog type ``key`` is drawn as, or None
    where none fits (carriers, cruise ships, auxiliaries: our own model)."""
    length = spec["length_m"]
    if "sail" in spec:
        shape = spec["shape"]
        if shape == "double_hull_wide":
            return "ssn"
        if shape == "teardrop":
            return "ssc" if length < 60 else "ssa"
        return "ssw" if length >= 95 else "ssk"
    layout = spec.get("layout")
    if layout == "warship":
        if length > ESCORT_MAX_M:
            return None
        return "kor" if length < 95 else _pick(spec, _ESCORTS)
    return {
        "container": "container" if length >= 250 else "convoy_feeder",
        "tanker": "tanker" if length >= 250 else "convoy_tanker",
        "bulk": "convoy_bulk", "reefer": "convoy_reefer", "roro": "convoy_roro",
        "car_carrier": "convoy_roro", "general_cargo": "convoy_cargo",
        "heavy_lift": "merchant", "ferry": "faehre", "tug": "schlepper",
        "trawler": "fischer",
    }.get(layout)


def variant_ref(key: str, spec: dict) -> dict | None:
    """``{"tk": design, "k": [ky, kup, kdown, dz]}``: the design and how its
    corners are stretched for this type (``y *= ky``; ``z`` above zero
    ``*= kup``, below ``*= kdown``, after shifting by ``dz``), or None."""
    name = design_for(key, spec)
    if name is None:
        return None
    verts = base_verts(name)
    length = spec["length_m"]
    beam = spec["beam_m"] / length
    if "sail" in spec:
        # Submarines: heights about the hull axis, the hull round in section.
        dz = -(verts[:, 2].min() + (verts[:, 1].max() - verts[:, 1].min()) / 2)
        ky = beam / float(verts[:, 1].max() - verts[:, 1].min())
        return {"tk": name, "k": [round(ky, 5), round(ky, 5), round(ky, 5), round(float(dz), 5)]}
    kdown = (spec["draft_m"] / length) / float(-verts[:, 2].min())
    deck = spec["deck_m"] / length
    # The beam as the hull below the deck is wide (what the spec gives).
    hull = verts[verts[:, 2] <= deck + 1e-6]
    ky = beam / float(hull[:, 1].max() - hull[:, 1].min())
    return {"tk": name, "k": [round(ky, 5), 1.0, round(kdown, 5), 0.0]}


def stretched(name: str, k) -> np.ndarray:
    ky, kup, kdown, dz = k
    verts = base_verts(name).copy()
    verts[:, 2] += dz
    verts[:, 1] *= ky
    verts[:, 2] *= np.where(verts[:, 2] > 0, kup, kdown)
    return verts


def mesh(ref: dict, floating: bool):
    """The stretched design as a ``unit_models.Mesh``."""
    from src.ui import unit_models as um
    model = data()["models"][ref["tk"]]
    two = set(model["s"])
    count = len(model["f"])
    return um.Mesh(stretched(ref["tk"], ref["k"]), model["f"],
                   [f"tk{m}" for m in model["m"]], [i in two for i in range(count)], [],
                   floating)


def nav(ref: dict) -> dict | None:
    """Light positions ``(u, v)`` of the design (as ``unit_variants.ship_nav``)."""
    points = data()["models"][ref["tk"]]["nav"]
    if points is None:
        return None
    kup = ref["k"][1]
    lift = lambda p: (p[0], round(p[1] * kup, 4))  # noqa: E731
    return {"mast": [lift(p) for p in points["mast"]], "side": lift(points["side"]),
            "stern": lift(points["stern"]), "round": lift(points["round"])}


def browser_model(name: str) -> dict:
    """The browser's mesh data of a design (as ``Mesh.to_json``: thousandths,
    material indices into the generated ``MATERIALS``)."""
    from src.ui import unit_models as um
    model = data()["models"][name]
    first = um.MATERIAL_NAMES.index("tk0")
    return {"v": [int(round(c / (SCALE / 1000))) for c in model["v"]],
            "f": model["f"], "m": [first + m for m in model["m"]], "s": model["s"],
            "l": [], "w": True}
