"""Per-type variants of the 3D models: every catalog ship, submarine and
aircraft type has its own model from its real dimensions and arrangement,
the same type always the same, and the eyepieces show the type the eye
sees."""

import copy
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pygame
import pytest

from src.data.catalog import CATALOG
from src.ui import unit_models, unit_variants
from src.ui.stations import bridge as bridge_view

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))

_TYPE_RESOURCES = ("warships.json", "civilians.json", "subs.json", "aircraft.json")


def test_every_ship_submarine_and_aircraft_type_has_a_variant():
    types = {key for key, resource in CATALOG.profile_resources.items()
             if resource in _TYPE_RESOURCES}
    assert types <= set(unit_variants.specs())
    assert set(unit_variants.specs()) <= set(CATALOG.surfaces) | set(CATALOG.subs) \
        | set(CATALOG.aircraft)
    for key, spec in unit_variants.specs().items():
        assert spec["source"] == "typical" or spec["source"].startswith(
            ("https://en.wikipedia.org/", "https://de.wikipedia.org/")), key


@pytest.mark.parametrize("key", sorted(json.loads(
    (ROOT / "data/unit_models/variants.json").read_text(encoding="utf-8"))["variants"]))
def test_every_variant_is_a_bounded_mesh_in_its_proportions(key):
    spec = unit_variants.specs()[key]
    mesh = unit_variants.variant_mesh(key)
    assert mesh is unit_variants.variant_mesh(key) is unit_models.mesh_for(key)
    assert np.isfinite(mesh.verts).all()
    assert np.abs(mesh.verts[:, 0]).max() <= 0.7
    count = len(mesh.verts)
    assert all(len(face) >= 3 and all(0 <= i < count for i in face) for face in mesh.faces)
    assert set(mesh.mats) <= set(unit_models.MATERIALS)
    kind = unit_variants.validate_spec(key, spec)
    assert mesh.floating == (kind == "ship")
    if kind == "ship":
        # Beam and length as the real ship (the hull, not a carrier's flight deck).
        hull = mesh.verts[mesh.verts[:, 2] <= spec["deck_m"] / spec["length_m"] + 1e-6]
        width = hull[:, 1].max() - hull[:, 1].min()
        if "flight_deck_beam_m" not in spec:
            assert width == pytest.approx(spec["beam_m"] / spec["length_m"], rel=0.05)
        assert mesh.verts[:, 2].min() == pytest.approx(-spec["draft_m"] / spec["length_m"],
                                                       rel=0.05)


def test_types_of_one_class_look_different_and_the_same_type_the_same():
    frigates = ["warship_05", "warship_07", "warship_13", "warship_30"]
    shapes = {key: unit_variants.variant_mesh(key).verts.tobytes() for key in frigates}
    assert len(set(shapes.values())) == len(frigates)
    # Two catalog entries of the same class share their data and look.
    specs = unit_variants.specs()
    same = {k: v for k, v in specs.items() if k != "warship_09"}
    twin = [k for k, v in same.items()
            if {a: b for a, b in v.items() if a != "name"}
            == {a: b for a, b in specs["warship_09"].items() if a != "name"}]
    for key in twin:
        assert unit_variants.variant_mesh(key).verts.tobytes() == \
            unit_variants.variant_mesh("warship_09").verts.tobytes()


def test_strict_schema_rejects_malformed_specs():
    spec = copy.deepcopy(unit_variants.specs()["warship_05"])
    assert unit_variants.validate_spec("x", spec) == "ship"
    for change in (lambda s: s.update(length_m=float("nan")),
                   lambda s: s.update(extra=1),
                   lambda s: s.update(layout="spaceship"),
                   lambda s: s["superstructure"].append({"from": 0.5, "to": 0.4,
                                                          "top_m": 10, "width": 0.5}),
                   lambda s: s["masts"].append({"u": 0.5, "top_m": 10, "kind": "tree"}),
                   lambda s: s.update(beam_m=True)):
        bad = copy.deepcopy(spec)
        change(bad)
        with pytest.raises((ValueError, KeyError)):
            unit_variants.validate_spec("x", bad)


def test_models_fall_back_to_the_class():
    assert unit_models.model_key("tanker_03", "merchant") == "tanker_03"
    assert unit_models.model_key("user.mine", "merchant") == "merchant"
    assert unit_models.model_key(None, "warship") == "warship"
    assert unit_models.mesh_for("no_such_type") is unit_models.mesh_for("unknown")
    assert unit_models.unit_model_class({"profile_kind": "surface", "key": "warship_05"}) \
        == "warship_05"
    assert unit_models.unit_model_class({"profile_kind": "surface", "key": "user.boat",
                                         "category": "KAMPFSCHIFF"}) == "warship"


def test_the_eye_sees_the_type_of_the_entity():
    ship = SimpleNamespace(profile=SimpleNamespace(key="warship_01"))
    flight = SimpleNamespace(akey="civil_transit")
    boat = SimpleNamespace(key="sub_11")
    assert unit_variants.entity_model(ship) == "warship_01"
    assert unit_variants.entity_model(flight) == "civil_transit"
    assert unit_variants.entity_model(boat) == "sub_11"
    assert unit_variants.entity_model(SimpleNamespace()) is None
    assert unit_variants.entity_model(None, own_ship=True) == unit_variants.OWN_SHIP_KEY


def test_ship_variants_carry_their_light_positions():
    nav = unit_variants.ship_nav("warship_05")
    assert len(nav["mast"]) == 2 and nav["stern"][0] > 0.9
    for key in unit_variants.specs():
        points = unit_variants.ship_nav(key)
        if points is not None:
            assert len(points["mast"]) >= 2
            assert all(0.0 <= u <= 1.0 for u, _v in points["mast"])
    assert unit_variants.ship_nav("sub_03") is None


def test_the_eyepiece_draws_the_variant_the_eye_sees():
    pygame.init()
    color = (44, 56, 64)
    pictures = {}
    for model in (None, "warship_05", "warship_15"):
        s = pygame.Surface((300, 120))
        s.fill((0, 0, 0))
        assert unit_models.draw_in_scene(s, "warship", 150, 80, 200, color, aob_deg=90.0,
                                         model=model, nav="R2-g-")
        pictures[model] = pygame.image.tobytes(s, "RGB")
    assert len(set(pictures.values())) == 3
    pygame.quit()


def test_the_lookout_picture_names_the_seen_type_his_report_does_not():
    from test_uboot_scope import _crewed, _environment
    game, _server, _bridge = _crewed(seed=61)
    game._lookout_environment = lambda: _environment(False)
    game.crew_effect = lambda: 1.0
    ship = game.civilians[0]
    for other in game.civilians[1:] + game.warships:
        other.x, other.y = game.ship.x + 60.0, game.ship.y + 60.0
    ship.x, ship.y, ship.course = game.ship.x, game.ship.y - 1.0, 270.0
    game.world.land_blocks_line = lambda *args: False
    rows = []
    for _ in range(40):
        game.sim_t += 1.0
        game._update_lookout_picture()
        rows = [row for row in bridge_view.lookout_outlines(game, game.lookout_sightings())
                if row[7] is not None]
        if rows:
            break
    assert rows and rows[0][7] == ship.profile.key
    from src.commander import projections
    glasses = projections._lookout_glasses(game)
    assert [row["model"] for row in glasses["outlines"] if row["model"]] == [ship.profile.key]


def test_browser_variant_modules_are_generated_and_bounded():
    from tools import gen_web_schema
    models = (ROOT / "data/commander/js/views/unit-models.js").read_text(encoding="utf-8")
    assert "export const VARIANT_GROUPS = " in models
    total = 0
    for group in gen_web_schema.VARIANT_GROUPS:
        path = gen_web_schema.variants_js(group)
        text = path.read_text(encoding="utf-8")
        assert text == gen_web_schema.render_variants(group)
        assert len(text.encode("utf-8")) < 360_000
        total += len(text)
    assert total < 900_000
    groups = {unit_variants.group_of(key) for key in unit_variants.specs()}
    assert groups == set(gen_web_schema.VARIANT_GROUPS)


def test_browser_loads_and_draws_variants_in_real_chromium(tmp_path):
    import functools
    import http.server
    import re
    import shutil
    import subprocess
    import threading

    chromium = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
    if not chromium:
        pytest.skip("Chromium is not installed")
    (tmp_path / "js").symlink_to(ROOT / "data" / "commander" / "js")
    (tmp_path / "index.html").write_text("""<!doctype html><html><body><pre id="out"></pre>
<script type="module">
import { drawInScene, loadVariant, modelKey } from "./js/views/model-view.js";
const paint = (model) => {
  const canvas = document.createElement("canvas");
  canvas.width = 300; canvas.height = 120;
  const g = canvas.getContext("2d");
  const frame = drawInScene(g, "warship", 150, 80, 200, [44, 56, 64], 90, false, model);
  return [canvas.toDataURL(), frame && frame.nav ? frame.nav.mast.length : 0];
};
const before = modelKey("warship_05", "warship");
await loadVariant("warship_05");
await loadVariant("sub_03");
const out = {before, after: modelKey("warship_05", "warship"), sub: modelKey("sub_03", "submarine"),
  none: modelKey("user.x", "merchant"), missing: await loadVariant("user.x")};
const [cls] = paint(null), [variant, masts] = paint("warship_05");
out.differs = cls !== variant; out.masts = masts;
document.getElementById("out").textContent = JSON.stringify(out);
</script></body></html>""", encoding="utf-8")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path))
    handler.log_message = lambda *args: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        result = subprocess.run(
            [chromium, "--headless", "--no-sandbox", "--disable-gpu",
             f"--user-data-dir={tmp_path / 'profile'}", "--virtual-time-budget=5000",
             "--dump-dom", f"http://127.0.0.1:{server.server_address[1]}/index.html"],
            capture_output=True, text=True, timeout=90)
    finally:
        server.shutdown()
    match = re.search(r'<pre id="out">(.*?)</pre>', result.stdout, re.S)
    assert match and match.group(1), result.stderr[-2000:]
    out = json.loads(match.group(1).replace("&quot;", '"'))
    assert out == {"before": "warship", "after": "warship_05", "sub": "sub_03",
                   "none": "merchant", "missing": False, "differs": True, "masts": 2}
