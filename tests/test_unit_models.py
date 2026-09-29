"""Schematic 3D models of the analyzer and the unit editor."""

import math
from pathlib import Path

import numpy as np
import pygame
import pytest

from src.data.catalog import CATALOG
from src.data.user_content import UserContentStore
from src.ui import unit_models
from src.ui.unit_editor import PROFILE_KINDS, UnitEditor, default_unit

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("cls", unit_models.MODEL_CLASSES)
def test_every_model_is_a_bounded_valid_mesh(cls):
    mesh = unit_models.mesh_for(cls)
    assert mesh is unit_models.mesh_for(cls)          # built once
    assert np.isfinite(mesh.verts).all()
    assert np.abs(mesh.verts[:, 0]).max() <= 0.7        # rotor tips pass the ends
    assert 0.3 < mesh.radius < 0.7
    assert len(mesh.faces) >= 50
    count = len(mesh.verts)
    assert all(len(face) >= 3 and all(0 <= i < count for i in face) for face in mesh.faces)
    assert all(0 <= a < count and 0 <= b < count for a, b, _mat in mesh.lines)
    assert set(mesh.mats) <= set(unit_models.MATERIALS)
    assert np.allclose(np.linalg.norm(mesh.normals, axis=1), 1.0)
    assert mesh.floating == (cls in ("warship", "merchant", "unknown"))


def test_lookout_classes_use_the_lookout_silhouettes():
    from src.ui import silhouettes
    lookout = {"warship", "merchant", "unknown", "submarine", "aircraft"}
    assert lookout <= set(silhouettes.PROFILES) and lookout <= set(unit_models.MODEL_CLASSES)
    # The hull's side view is the silhouette's: same highest point.
    for cls in ("warship", "merchant", "unknown"):
        top = max(v for poly in [silhouettes.PROFILES[cls]["hull"],
                                 *silhouettes.PROFILES[cls]["blocks"]] for _u, v in poly)
        assert float(unit_models.mesh_for(cls).verts[:, 2].max()) == pytest.approx(top, abs=1e-6)


def test_every_catalog_profile_has_a_fitting_model():
    classes = unit_models.catalog_model_classes(CATALOG)
    assert set(classes) == set(CATALOG.profile_systems)
    assert set(classes.values()) <= set(unit_models.MODEL_CLASSES)
    # Ships, submarines and aircraft look as the lookout draws them.
    expected = {"diesel_alt": "submarine", "sub_03": "submarine", "tanker_03": "merchant",
                "warship_22": "warship", "aux_01": "warship", "aux_07": "unknown",
                "mil_patrol": "aircraft", "civil_transit": "aircraft",
                "whale": "whale", "fish_school": "fish",
                "jellyfish": "jellyfish", "frigate_torp": "torpedo", "decoy": "decoy"}
    for key, cls in expected.items():
        assert classes[key] == cls, key


@pytest.mark.parametrize("kind", PROFILE_KINDS)
def test_new_editor_profiles_get_a_model_of_their_kind(kind):
    cls = unit_models.unit_model_class(default_unit(kind))
    assert cls in unit_models.MODEL_CLASSES
    assert cls == {"sub": "submarine", "surface": "warship", "aircraft": "aircraft",
                   "animal": "whale", "torpedo": "torpedo", "decoy": "decoy"}[kind]
    # A cloned animal keeps its model through the name.
    assert unit_models.unit_model_class(
        {"profile_kind": "animal", "key": "user.clone", "name": "Fischschwarm"}) == "fish"


def test_draw_is_deterministic_stays_in_its_box_and_turns():
    pygame.init()
    rect = pygame.Rect(40, 30, 320, 240)
    first, second, turned = (pygame.Surface((400, 300)) for _ in range(3))
    for surface, yaw in ((first, 0.6), (second, 0.6), (turned, 2.0)):
        surface.fill((0, 0, 0))
        assert unit_models.draw_model(surface, rect, "warship", yaw=yaw) > 20
    assert pygame.image.tobytes(first, "RGB") == pygame.image.tobytes(second, "RGB")
    assert pygame.image.tobytes(first, "RGB") != pygame.image.tobytes(turned, "RGB")
    # Nothing outside the box, and the clip is restored.
    outside = [first.get_at((x, y)) for x in range(0, 400, 7) for y in (0, 10, 290, 299)]
    assert all(pixel[:3] == (0, 0, 0) for pixel in outside)
    assert first.get_clip() == first.get_rect()
    assert unit_models.turn_angle(10.0) - unit_models.turn_angle(0.0) == pytest.approx(
        10.0 * unit_models.TURN_RAD_S)
    pygame.quit()


def test_model_view_redraws_only_when_the_turn_steps(monkeypatch):
    pygame.init()
    calls = []
    real = unit_models.draw_model
    monkeypatch.setattr(unit_models, "draw_model",
                        lambda *a, **k: calls.append(k["yaw"]) or real(*a, **k))
    view = unit_models.ModelView()
    screen = pygame.Surface((300, 200))
    rect = pygame.Rect(0, 0, 300, 200)
    view.draw(screen, rect, "submarine", t=1.0)
    view.draw(screen, rect, "submarine", t=1.0 + 0.2 / unit_models.TURN_UPDATES_HZ)
    assert len(calls) == 1
    view.draw(screen, rect, "submarine", t=1.0 + 1.5 / unit_models.TURN_UPDATES_HZ)
    view.draw(screen, rect, "jet", t=1.0 + 1.5 / unit_models.TURN_UPDATES_HZ)
    assert len(calls) == 3
    pygame.quit()


def test_unit_editor_shows_the_model_in_browser_and_editor(tmp_path):
    pygame.init()
    editor = UnitEditor(CATALOG, UserContentStore(tmp_path))
    screen = pygame.Surface((1280, 720))
    editor._set_filter("tanker_03")
    editor.draw(screen)
    box = editor._rects["model"]
    assert box is not None and screen.get_rect().contains(box)
    assert box.height > 200
    editor.open_selected()
    editor.draw(screen)
    box = editor._rects["model"]
    assert box is not None and screen.get_rect().contains(box)
    wiki = editor._rects.get("open_wiki")
    assert wiki is None or wiki.bottom <= box.top
    pygame.quit()


def test_browser_models_are_generated_from_the_python_meshes():
    from tools import gen_web_schema

    generated = (ROOT / "data/commander/js/views/unit-models.js").read_text(encoding="utf-8")
    assert generated == gen_web_schema.render_models()
    assert len(generated.encode("utf-8")) < 120_000
    analyzer = (ROOT / "data/commander/js/views/analyzer.js").read_text(encoding="utf-8")
    assert 'from "./model-view.js"' in analyzer
    view = (ROOT / "data/commander/js/views/model-view.js").read_text(encoding="utf-8")
    # Same turn rate, view and fit as the uConsole.
    for name in ("TURN_RAD_S", "ELEVATION_RAD", "WATER_RING", "LIGHT"):
        assert name in view
    assert math.isclose(unit_models.ELEVATION_RAD, math.radians(22.0))


def test_browser_draws_every_model_in_real_chromium(tmp_path):
    import functools
    import http.server
    import shutil
    import subprocess
    import threading

    chromium = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
    if not chromium:
        pytest.skip("Chromium is not installed")
    (tmp_path / "js").symlink_to(ROOT / "data" / "commander" / "js")
    (tmp_path / "index.html").write_text("""<!doctype html><html><body><pre id="out"></pre>
<script type="module">
import { drawModel, modelClass } from "./js/views/model-view.js";
import { MODELS } from "./js/views/unit-models.js";
const counts = {};
for (const cls of Object.keys(MODELS)) {
  const canvas = document.createElement("canvas");
  canvas.width = 240; canvas.height = 160;
  const ctx = canvas.getContext("2d");
  drawModel(ctx, 240, 160, cls, 0.6);
  const data = ctx.getImageData(0, 0, 240, 160).data;
  let painted = 0;
  for (let i = 3; i < data.length; i += 4) if (data[i]) painted += 1;
  counts[cls] = painted;
}
counts.__tanker = modelClass("tanker_03");
counts.__unknown = modelClass("user.none");
document.getElementById("out").textContent = JSON.stringify(counts);
</script></body></html>""", encoding="utf-8")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path))
    handler.log_message = lambda *args: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(
            [chromium, "--headless", "--no-sandbox", "--disable-gpu",
             f"--user-data-dir={tmp_path / 'profile'}", "--virtual-time-budget=5000",
             "--dump-dom", f"http://127.0.0.1:{server.server_address[1]}/index.html"],
            capture_output=True, text=True, timeout=90)
    finally:
        server.shutdown()
    import json
    import re
    match = re.search(r'<pre id="out">(.*?)</pre>', result.stdout, re.S)
    assert match and match.group(1), result.stderr[-2000:]
    counts = json.loads(match.group(1).replace("&quot;", '"'))
    assert counts.pop("__tanker") == "merchant" and counts.pop("__unknown") == "unknown"
    assert set(counts) == set(unit_models.MODEL_CLASSES)
    assert all(painted > 500 for painted in counts.values()), counts
