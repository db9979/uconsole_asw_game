"""Per-type variants of the schematic 3D models.

Every catalog ship, submarine and aircraft type gets its own model built
from the public main dimensions and general arrangement of the real class
(``data/unit_models/variants.json``: length, beam, draught, where bridge,
masts, funnels, guns, launchers, flight deck, cranes and cargo stand, the
submarine's sail, planes and rudders, the aircraft's wing and tail).  The
same type always looks the same; a type without an entry keeps the model of
its class.  Positions ``u`` run from the bow (0) to the stern (1), heights
are metres above the waterline (submarines: above the hull axis) and every
model is scaled to length 1 like the class models.
"""
from __future__ import annotations

import json
import math
import zlib
from importlib import resources

from src.ui import unit_models as um

VARIANTS_RESOURCE = ("data.unit_models", "variants.json")
SHIP_LAYOUTS = ("warship", "carrier", "container", "tanker", "lng", "bulk", "roro",
                "car_carrier", "cruise", "ferry", "general_cargo", "heavy_lift", "reefer",
                "tug", "trawler", "research", "offshore", "rescue", "pilot", "mcm",
                "replenishment")
BOWS = ("raked", "bulbous", "plumb", "wave_piercing", "tumblehome")
MAST_KINDS = ("lattice", "pole", "enclosed")
SUB_SHAPES = ("teardrop", "cylinder", "double_hull_wide")
AIRCRAFT_KINDS = ("fighter", "attack", "airliner", "helicopter")
MAX_PARTS = 8
_NAVAL = ("warship", "carrier", "mcm", "replenishment")
_WHITE = ("cruise", "ferry", "research", "rescue", "pilot")
_FULL = ("tanker", "lng", "bulk", "car_carrier", "roro", "container", "reefer",
         "general_cargo", "heavy_lift")
_HULL_COLOURS = {"tanker": ("tanker", "black", "merchant"), "lng": ("tanker", "merchant"),
                 "tug": ("tanker", "black", "merchant"), "trawler": ("merchant", "tanker", "black"),
                 "offshore": ("tanker", "merchant", "black")}
_CARGO_COLOURS = ("merchant", "tanker", "black", "box_c")
_BOXES = ("box_a", "box_b", "box_c", "box_d")

_SPECS: dict | None = None
_MESHES: dict = {}


# --- the data ----------------------------------------------------------------
def _number(value, low: float, high: float) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"number out of range {low}..{high}: {value!r}")
    return float(value)


def _span(item, keys=("from", "to")) -> None:
    a, b = (_number(item[k], 0.0, 1.0) for k in keys)
    if a >= b:
        raise ValueError(f"empty span {item!r}")


def _exact(item, required: set, optional: set = frozenset()) -> None:
    if not isinstance(item, dict) or not required <= set(item) <= required | optional:
        raise ValueError(f"unexpected keys {sorted(item) if isinstance(item, dict) else item!r}")


def _parts(items, required: set, check) -> None:
    if not isinstance(items, list) or len(items) > MAX_PARTS:
        raise ValueError(f"bad part list {items!r}")
    for item in items:
        _exact(item, required)
        check(item)


def validate_spec(key: str, spec) -> str:
    """Kind of a variant spec (``ship``, ``sub`` or ``aircraft``); raises
    ``ValueError`` on anything outside the strict schema."""
    common = {"name", "source"}
    if not isinstance(spec, dict) or type(spec.get("name")) is not str \
            or type(spec.get("source")) is not str:
        raise ValueError(f"{key}: name and source required")
    if "layout" in spec:
        _exact(spec, common | {"length_m", "beam_m", "draft_m", "deck_m", "bow", "layout",
                               "superstructure", "masts", "funnels", "guns", "vls",
                               "helideck", "cranes", "cargo", "island"},
               {"flight_deck_beam_m"})
        length = _number(spec["length_m"], 10.0, 450.0)
        _number(spec["beam_m"], 2.0, length / 2.5)
        _number(spec["draft_m"], 0.5, 30.0)
        _number(spec["deck_m"], 0.5, 40.0)
        if spec["bow"] not in BOWS or spec["layout"] not in SHIP_LAYOUTS:
            raise ValueError(f"{key}: bow or layout")
        top = lambda item: _number(item["top_m"], 0.5, 120.0)  # noqa: E731
        _parts(spec["superstructure"], {"from", "to", "top_m", "width"},
               lambda i: (_span(i), top(i), _number(i["width"], 0.05, 1.0)))
        _parts(spec["masts"], {"u", "top_m", "kind"},
               lambda i: (_number(i["u"], 0.0, 1.0), top(i),
                          i["kind"] in MAST_KINDS or _raise(key, "mast kind")))
        _parts(spec["funnels"], {"u", "top_m"}, lambda i: (_number(i["u"], 0.0, 1.0), top(i)))
        _parts(spec["guns"], {"u"}, lambda i: _number(i["u"], 0.0, 1.0))
        _parts(spec["vls"], {"from", "to"}, _span)
        _parts(spec["cranes"], {"u", "top_m"}, lambda i: (_number(i["u"], 0.0, 1.0), top(i)))
        for name, keys in (("helideck", {"from", "to"}), ("cargo", {"from", "to", "top_m"}),
                           ("island", {"from", "to", "top_m"})):
            if spec[name] is not None:
                _exact(spec[name], keys)
                _span(spec[name])
                if "top_m" in keys:
                    top(spec[name])
        if "flight_deck_beam_m" in spec:
            _number(spec["flight_deck_beam_m"], spec["beam_m"], length / 2.5)
        return "ship"
    if "sail" in spec:
        _exact(spec, common | {"length_m", "beam_m", "sail", "sail_planes", "rudders",
                               "hump", "shape"})
        length = _number(spec["length_m"], 20.0, 200.0)
        _number(spec["beam_m"], 2.0, length / 4.0)
        _exact(spec["sail"], {"from", "to", "top_m"})
        _span(spec["sail"])
        _number(spec["sail"]["top_m"], 1.0, 25.0)
        if type(spec["sail_planes"]) is not bool or spec["rudders"] not in ("cross", "x") \
                or spec["shape"] not in SUB_SHAPES:
            raise ValueError(f"{key}: planes, rudders or shape")
        if spec["hump"] is not None:
            _exact(spec["hump"], {"from", "to", "top_m"})
            _span(spec["hump"])
            _number(spec["hump"]["top_m"], 1.0, 25.0)
        return "sub"
    _exact(spec, common | {"length_m", "wingspan_m", "height_m", "kind", "wing_u",
                           "sweep_deg", "tail", "engines"})
    _number(spec["length_m"], 5.0, 90.0)
    _number(spec["wingspan_m"], 5.0, 90.0)
    _number(spec["height_m"], 1.0, 25.0)
    _exact(spec["wing_u"], {"from", "to"})
    _span(spec["wing_u"])
    _number(spec["sweep_deg"], 0.0, 70.0)
    if spec["kind"] not in AIRCRAFT_KINDS or spec["tail"] not in ("single", "twin") \
            or spec["engines"] not in ("fuselage", "underwing"):
        raise ValueError(f"{key}: kind, tail or engines")
    return "aircraft"


def _raise(key, what):
    raise ValueError(f"{key}: {what}")


def specs() -> dict:
    """Every variant spec by catalog key, validated once."""
    global _SPECS
    if _SPECS is None:
        package, name = VARIANTS_RESOURCE
        data = json.loads(resources.files(package).joinpath(name).read_text(encoding="utf-8"))
        if not isinstance(data, dict) or set(data) != {"version", "note", "variants"} \
                or data["version"] != 1 or not isinstance(data["variants"], dict):
            raise ValueError("variants.json: bad document")
        for key, spec in data["variants"].items():
            validate_spec(key, spec)
        _SPECS = dict(sorted(data["variants"].items()))
    return _SPECS


def has_variant(key) -> bool:
    return isinstance(key, str) and key in specs()


def _pick(key: str, options) -> str:
    """A stable choice per type (the same colour on every run)."""
    return options[zlib.crc32(key.encode("utf-8")) % len(options)]


# --- ships -------------------------------------------------------------------
def _box(b, u0, u1, z0, z1, half, mat, y=0.0, rake=0.0) -> None:
    """A deckhouse from ``u0`` (forward) to ``u1``, its front raked aft."""
    um._prism(b, [(u0 + rake, z1), (u1, z1), (u1, z0), (u0, z0)], half, mat, y)


def _ship(key: str, spec: dict) -> um.Mesh:
    length = spec["length_m"]
    m = lambda metres: metres / length  # noqa: E731
    layout, bow = spec["layout"], spec["bow"]
    naval = layout in _NAVAL
    beam, draft, deck = m(spec["beam_m"]) / 2, m(spec["draft_m"]), m(spec["deck_m"])
    side = "hull" if naval else "white" if layout in _WHITE else \
        _pick(key, _HULL_COLOURS.get(layout, _CARGO_COLOURS))
    house = "super" if naval else "white"
    entrance = 0.2 if layout in _FULL else 0.35 if naval else 0.3
    aft = deck * (0.8 if spec["helideck"] else 0.95)
    if bow in ("wave_piercing", "tumblehome"):
        poly = [(0.0, 0.0), (0.97, 0.0), (1.0, aft), (0.3, deck), (0.08, deck)]
    else:
        rake = {"raked": 0.045, "bulbous": 0.025, "plumb": 0.008}[bow]
        poly = [(0.0, deck * 1.18), (rake, 0.0), (0.97, 0.0), (1.0, aft), (0.3, deck),
                (0.08, deck * 1.12)]
    b = um._Builder()
    um._hull(b, poly, beam, draft, side=side, stations=14, entrance=entrance,
             transom=0.9 if layout in _FULL else 0.72)
    x = um._x
    width = lambda u: beam * um._plan(u, entrance, 0.9 if layout in _FULL else 0.72)  # noqa: E731
    tops = []
    # Flight deck overhang of a carrier and its island to starboard.
    if spec.get("flight_deck_beam_m"):
        half = m(spec["flight_deck_beam_m"]) / 2
        z = deck + 0.004
        b.plate([(x(0.02), 0.6 * half, z), (x(0.98), 0.9 * half, z),
                 (x(0.98), -half, z), (x(0.1), -0.7 * half, z)], "deck")
        for side_y in (0.6 * half, -0.7 * half):
            b.line((x(0.1), side_y, z + 0.001), (x(0.9), side_y * 1.2, z + 0.001), "white")
    if spec["island"]:
        i = spec["island"]
        half = min(beam * 0.3, 0.02)
        y = -(m(spec.get("flight_deck_beam_m") or spec["beam_m"]) / 2 - half * 1.5)
        _box(b, i["from"], i["to"], deck, m(i["top_m"]), half, house, y)
        tops.append((i["from"], i["to"], m(i["top_m"])))
    for s in spec["superstructure"]:
        uc = (s["from"] + s["to"]) / 2
        top = m(s["top_m"])
        _box(b, s["from"], s["to"], deck, top, max(0.004, s["width"] * width(uc)),
             house, rake=0.15 * (top - deck) if naval else 0.0)
        tops.append((s["from"], s["to"], top))
        if layout in ("cruise", "ferry") and top - deck > 0.02:
            # Rows of cabin windows and balconies down both sides.
            half = max(0.004, s["width"] * width(uc)) + 0.0005
            rows = min(8, int((top - deck) / m(3.0)))
            for k in range(1, rows):
                z = deck + (top - deck) * k / rows
                for y in (half, -half):
                    b.line((x(s["from"] + 0.01), y, z), (x(s["to"] - 0.01), y, z), "dark")

    def base(u: float) -> float:
        return max([t for u0, u1, t in tops if u0 - 0.005 <= u <= u1 + 0.005] + [deck])

    # Cargo: container bays, tank deck, domes, car-carrier box.
    c = spec["cargo"]
    if c:
        top = m(c["top_m"])
        if layout in ("container", "general_cargo", "reefer", "heavy_lift"):
            u, n = c["from"], 0
            bay = 0.055 if layout == "container" else 0.09
            while u < c["to"] - 0.01:
                u1 = min(c["to"], u + bay)
                mat = _BOXES[(zlib.crc32(key.encode()) + n) % len(_BOXES)]
                _box(b, u, u1 - 0.004, deck, top, 0.92 * width((u + u1) / 2), mat)
                u, n = u1, n + 1
        elif layout == "lng":
            # Membrane tanks under a raised trunk deck with the pipe run.
            _box(b, c["from"], c["to"], deck, top, 0.72 * beam, side)
            b.line((x(c["from"]), 0.0, top + 0.003), (x(c["to"]), 0.0, top + 0.003), "dark")
        elif layout in ("car_carrier", "roro"):
            _box(b, c["from"], c["to"], deck, top, 0.98 * beam, side)
            tops.append((c["from"], c["to"], top))
        else:                       # tanker and bulk deck: pipes or hatches
            if layout == "bulk":
                steps = 7
                for k in range(steps):
                    u0 = c["from"] + (c["to"] - c["from"]) * k / steps
                    u1 = u0 + 0.7 * (c["to"] - c["from"]) / steps
                    _box(b, u0, u1, deck, deck + 0.006, 0.6 * beam, "deck")
            else:
                for y in (0.15 * beam, -0.15 * beam):
                    b.line((x(c["from"]), y, deck + 0.004), (x(c["to"]), y, deck + 0.004), "dark")
                _box(b, 0.5 - 0.01, 0.5 + 0.01, deck, deck + 0.02, 0.5 * beam, "dark")
    for v in spec["vls"]:
        z = deck + 0.002
        half = 0.45 * width((v["from"] + v["to"]) / 2)
        b.plate([(x(v["from"]), half, z), (x(v["to"]), half, z),
                 (x(v["to"]), -half, z), (x(v["from"]), -half, z)], "dark")
    if spec["helideck"]:
        h = spec["helideck"]
        z = aft + 0.001
        half = 0.9 * width((h["from"] + h["to"]) / 2)
        b.plate([(x(h["from"]), half, z), (x(h["to"]), half * 0.9, z),
                 (x(h["to"]), -half * 0.9, z), (x(h["from"]), -half, z)], "pad")
        uc = (h["from"] + h["to"]) / 2
        for d in (-1, 1):
            b.line((x(uc + d * 0.02), 0.0, z + 0.001), (x(uc - d * 0.02), 0.0, z + 0.001), "white")
    for g in spec["guns"]:
        u, z0 = g["u"], base(g["u"])
        half = 0.35 * width(u)
        _box(b, u - 0.012, u + 0.012, z0, z0 + 0.011, max(0.004, half), house,
             rake=0.006)
        b.line((x(u - 0.008), 0.0, z0 + 0.006), (x(u - 0.05), 0.0, z0 + 0.008), "dark")
    for f in spec["funnels"]:
        u, top = f["u"], m(f["top_m"])
        z0 = base(u)
        if top > z0:
            half = 0.3 * width(u)
            _box(b, u - 0.014, u + 0.018, z0, top, max(0.004, half),
                 "black" if not naval else house, rake=0.01)
    for mast in spec["masts"]:
        u, top = mast["u"], m(mast["top_m"])
        z0 = base(u)
        if top <= z0:
            continue
        if mast["kind"] == "enclosed":
            um._prism(b, [(u - 0.012, z0), (u - 0.006, top), (u + 0.006, top), (u + 0.014, z0)],
                      min(0.012, 0.4 * width(u)), house)
        elif mast["kind"] == "lattice":
            foot = 0.012
            for dx, dy in ((-foot, foot), (foot, foot), (foot, -foot), (-foot, -foot)):
                b.line((x(u) + dx, dy, z0), (x(u), 0.0, top), "dark")
            b.line((x(u), -0.03, 0.75 * top + 0.25 * z0), (x(u), 0.03, 0.75 * top + 0.25 * z0),
                   "dark")
        else:
            b.line((x(u), 0.0, z0), (x(u), 0.0, top), "dark")
            b.line((x(u), -0.015, 0.85 * top + 0.15 * z0), (x(u), 0.015, 0.85 * top + 0.15 * z0),
                   "dark")
    for crane in spec["cranes"]:
        u, top = crane["u"], m(crane["top_m"])
        z0 = base(u)
        b.line((x(u), 0.0, z0), (x(u), 0.0, top), "boat")
        b.line((x(u), 0.0, top), (x(u - 0.06), 0.0, 0.5 * (top + z0)), "boat")
    return b.mesh(True)


def ship_nav(key: str) -> dict | None:
    """Navigation light positions ``(u, v)`` of a ship variant in the class
    profiles' units (``src/ui/silhouettes.py``): masthead lights on the masts,
    side lights at the bridge, the stern light on the transom."""
    spec = specs().get(key)
    if not spec or "layout" not in spec:
        return None
    m = lambda metres: metres / spec["length_m"]  # noqa: E731
    masts = sorted(spec["masts"], key=lambda item: item["u"])
    blocks = spec["superstructure"] or ([spec["island"]] if spec["island"] else [])
    bridge = min(blocks, key=lambda item: item["from"]) if blocks else None
    deck = m(spec["deck_m"])
    mast_points = [(item["u"], m(item["top_m"])) for item in masts[:2]]
    if not mast_points:
        mast_points = [(bridge["from"], m(bridge["top_m"]) + 0.02) if bridge else (0.3, deck + 0.05)]
    if len(mast_points) == 1:
        # The code may ask for two masthead lights: the second abaft, higher.
        u, v = mast_points[0]
        mast_points.append((min(0.98, u + 0.1), v + 0.02))
    side = (bridge["from"] + 0.01, 0.8 * m(bridge["top_m"]) + 0.2 * deck) if bridge \
        else (0.3, deck + 0.01)
    return {"mast": mast_points, "side": side, "stern": (0.995, 0.8 * deck),
            "round": mast_points[0]}


# --- submarines --------------------------------------------------------------
def _sub(key: str, spec: dict) -> um.Mesh:
    length = spec["length_m"]
    m = lambda metres: metres / length  # noqa: E731
    radius = m(spec["beam_m"]) / 2
    shape = spec["shape"]
    nose, tail = {"teardrop": (0.16, 0.45), "cylinder": (0.1, 0.3),
                  "double_hull_wide": (0.14, 0.32)}[shape]

    def r(u: float) -> float:
        if u < nose:
            return radius * math.sqrt(max(0.0, 1.0 - ((nose - u) / nose) ** 2))
        if u > 1.0 - tail:
            k = (u - (1.0 - tail)) / tail
            return radius * max(0.06, 1.0 - k ** 1.6)
        return radius

    b = um._Builder()
    zscale = 0.85 if shape == "double_hull_wide" else 1.0
    um._revolve(b, [(i / 16, r(i / 16)) for i in range(17)], "sub", segments=10,
                zscale=zscale)
    x = um._x
    s = spec["sail"]
    top = m(s["top_m"])
    half = max(0.004, min(0.35 * radius, 0.012))
    um._prism(b, [(s["from"] + 0.01, top), (s["to"] - 0.005, top), (s["to"] + 0.012, 0.6 * radius),
                  (s["from"], 0.6 * radius)], half, "sub")
    if spec["hump"]:
        h = spec["hump"]
        um._prism(b, [(h["from"], m(h["top_m"])), (h["to"], m(h["top_m"])),
                      (h["to"] + 0.04, 0.5 * radius), (h["from"] - 0.03, 0.5 * radius)],
                  0.7 * radius, "sub")
    for sy in (1, -1):
        if spec["sail_planes"]:
            z = 0.6 * top + 0.4 * radius
            b.plate([(x(s["from"] + 0.005), 0.0, z), (x(s["from"] + 0.04), 0.0, z),
                     (x(s["from"] + 0.035), sy * 3.2 * radius, z),
                     (x(s["from"] + 0.015), sy * 3.2 * radius, z)], "sub")
        else:
            b.plate([(x(0.06), sy * 0.9 * radius, 0.3 * radius), (x(0.1), sy * 0.9 * radius, 0.3 * radius),
                     (x(0.095), sy * 1.9 * radius, 0.3 * radius), (x(0.07), sy * 1.9 * radius, 0.3 * radius)],
                    "sub")
        fins = ((sy * 1.4 * radius, 0.0), (0.0, sy * 1.4 * radius)) if spec["rudders"] == "cross" \
            else ((sy * radius, radius), (sy * radius, -radius))
        for fy, fz in fins:
            b.plate([(x(0.9), 0.0, 0.0), (x(0.985), 0.0, 0.0), (x(0.985), fy, fz),
                     (x(0.93), 0.9 * fy, 0.9 * fz)], "sub")
    b.line((x(s["from"] + 0.03), 0.0, top), (x(s["from"] + 0.03), 0.0, top + 0.02))
    return b.mesh(False)


# --- aircraft ----------------------------------------------------------------
def _aircraft(key: str, spec: dict) -> um.Mesh:
    if spec["kind"] == "helicopter":
        return um.mesh_for("aircraft")
    length = spec["length_m"]
    m = lambda metres: metres / length  # noqa: E731
    airliner = spec["kind"] == "airliner"
    radius = 0.055 if airliner else 0.045
    mat = "air" if airliner else "mil"
    b = um._Builder()

    def r(u: float) -> float:
        if u < 0.15:
            return radius * math.sqrt(max(0.0, 1 - ((0.15 - u) / 0.15) ** 2))
        if u > 0.7:
            return radius * max(0.15, 1 - ((u - 0.7) / 0.3) * 0.85)
        return radius

    um._revolve(b, [(i / 20, r(i / 20)) for i in range(21)], mat, segments=10)
    x = um._x
    w = spec["wing_u"]
    span = m(spec["wingspan_m"]) / 2
    sweep = math.tan(math.radians(spec["sweep_deg"])) * span
    chord = w["to"] - w["from"]
    tip = 0.3 * chord if not airliner else 0.25 * chord
    z = -0.3 * radius if airliner else 0.0
    for sy in (1, -1):
        b.plate([(x(w["from"]), 0.0, z), (x(w["to"]), 0.0, z),
                 (x(w["from"] + sweep + tip), sy * span, z + (0.02 if airliner else 0.0)),
                 (x(w["from"] + sweep), sy * span, z + (0.02 if airliner else 0.0))], mat)
        stab = 0.35 * span if airliner else 0.4 * span
        b.plate([(x(0.82), 0.0, 0.2 * radius), (x(0.97), 0.0, 0.2 * radius),
                 (x(0.99), sy * stab, 0.25 * radius), (x(0.93), sy * stab, 0.25 * radius)], mat)
        if spec["engines"] == "underwing":
            ey = sy * 0.34 * span
            um._revolve(b, [(0.0, 0.0), (0.05, 0.6), (0.5, 0.6), (1.0, 0.4)], "dark",
                        segments=8, x0=x(w["from"] + 0.34 * sweep - 0.04), y0=ey,
                        z0=z - 0.03, length=0.1)
    fin_h = m(spec["height_m"]) - radius
    fins = (0.0,) if spec["tail"] == "single" else (0.4 * radius, -0.4 * radius)
    for fy in fins:
        b.plate([(x(0.78), fy, radius * 0.6), (x(0.95), fy, radius * 0.6),
                 (x(0.99), fy, fin_h), (x(0.92), fy, fin_h)], mat)
    # Cockpit glazing.
    b.plate([(x(0.05), 0.02, 0.8 * radius), (x(0.12), 0.02, 1.0 * radius),
             (x(0.12), -0.02, 1.0 * radius), (x(0.05), -0.02, 0.8 * radius)], "canopy")
    return b.mesh(False)


_KINDS = {"ship": _ship, "sub": _sub, "aircraft": _aircraft}


def variant_mesh(key: str) -> um.Mesh | None:
    """The model of catalog type ``key``, built once; None without a spec."""
    spec = specs().get(key)
    if spec is None:
        return None
    mesh = _MESHES.get(key)
    if mesh is None:
        mesh = _MESHES[key] = _KINDS[validate_spec(key, spec)](key, spec)
    return mesh


def entity_model(entity, own_ship: bool = False) -> str | None:
    """The type an observer sees of a simulated ``entity`` by eye (its
    catalog key, when that type has its own model).  Only the eyepiece
    pictures use it: what is seen is the real ship, and telling which one
    it is stays the watch's job (their reports carry only what they made
    out)."""
    if own_ship:
        return OWN_SHIP_KEY if has_variant(OWN_SHIP_KEY) else None
    profile = getattr(entity, "profile", None)
    for key in (getattr(profile, "key", None), getattr(entity, "akey", None),
                getattr(entity, "key", None)):
        if has_variant(key):
            return key
    return None


# The frigate F217 Bayern of the Brandenburg class.
OWN_SHIP_KEY = "warship_30"


def group_of(key: str) -> str:
    """Browser module a variant ships in (loaded only when needed)."""
    spec = specs()[key]
    if "sail" in spec:
        return "subs"
    if "layout" in spec and spec["layout"] in _NAVAL:
        return "naval"
    return "civil" if "layout" in spec else "naval"
