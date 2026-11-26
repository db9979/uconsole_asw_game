"""The ship and submarine designs of Tiefenkontakt (the browser game) in the
analyzer and the eyepieces: provenance, which catalog types get which
design, the stretch to the real type, the background build that keeps the
uConsole responsive and the browser modules."""

import json
from pathlib import Path

import numpy as np
import pygame
import pytest

from src.ui import model_bsp, tk_models, unit_models, unit_variants

ROOT = Path(__file__).resolve().parents[1]


def test_designs_carry_their_source_and_are_valid_meshes():
    data = tk_models.data()
    assert data["source"] == "https://github.com/db9979/tiefenkontakt"
    assert len(data["commit"]) == 40
    assert set(tk_models.palette()) <= set(unit_models.MATERIALS)
    for name in tk_models.names():
        model = data["models"][name]
        verts = tk_models.base_verts(name)
        assert np.isfinite(verts).all()
        # Length one, bow forward, waterline at zero.
        assert -0.501 <= verts[:, 0].min() < verts[:, 0].max() <= 0.501
        assert verts[:, 0].max() - verts[:, 0].min() > 0.97
        assert verts[:, 2].min() < 0 < verts[:, 2].max()
        count = len(verts)
        assert all(len(f) >= 3 and all(0 <= k < count for k in f) for f in model["f"])
        assert len(model["m"]) == len(model["f"])
        assert all(0 <= m < len(data["palette"]) for m in model["m"])
        # Detailed, but bounded for the uConsole's painter.
        assert 500 < len(model["f"]) < 3500, name


def test_every_design_is_used_and_fitting_types_get_one():
    used = {(unit_variants.tk_ref(key) or {}).get("tk") for key in unit_variants.specs()}
    assert set(tk_models.names()) <= used
    expected = {"warship_05": ("ffg", "ffk", "ffv"), "warship_15": ("kor",),
                "cargo_02": ("container",), "cargo_04": ("convoy_feeder",),
                "tanker_11": ("tanker",), "cargo_06": ("convoy_bulk",),
                "aux_02": ("schlepper",), "aux_07": ("fischer",),
                "sub_03": ("ssw",), "aip_modern": ("ssc",), "ssn": ("ssn",)}
    for key, designs in expected.items():
        assert unit_variants.tk_ref(key)["tk"] in designs, key
    # Carriers, cruisers, big destroyers, cruise ships, auxiliaries and
    # aircraft keep their own distinct models.
    for key in ("warship_28", "warship_22", "warship_03", "passenger_01", "tanker_14",
                "aux_01", "civil_transit"):
        assert unit_variants.tk_ref(key) is None, key


def test_ships_are_stretched_to_the_real_draught_and_lights_sit_on_the_design():
    spec = unit_variants.specs()["cargo_02"]
    mesh = unit_variants.variant_mesh("cargo_02")
    assert mesh.verts[:, 2].min() == pytest.approx(-spec["draft_m"] / spec["length_m"], rel=1e-3)
    nav = unit_variants.ship_nav("cargo_02")
    top = float(mesh.verts[:, 2].max())
    assert 0 < nav["mast"][0][1] <= top + 1e-6
    assert all(0.0 <= u <= 1.0 for u, _v in nav["mast"]) and nav["stern"][0] > 0.9
    # A submarine: heights about the hull axis as our own boats.
    sub = unit_variants.variant_mesh("sub_03")
    spec = unit_variants.specs()["sub_03"]
    width = sub.verts[:, 1].max() - sub.verts[:, 1].min()
    assert width == pytest.approx(spec["beam_m"] / spec["length_m"], rel=1e-3)
    assert sub.verts[:, 2].min() == pytest.approx(-width / 2, rel=1e-3)
    assert not sub.floating


def test_the_detailed_design_is_built_in_the_background(monkeypatch):
    monkeypatch.setattr(model_bsp, "BACKGROUND", True)
    monkeypatch.setattr(model_bsp, "_TREES", {})
    pygame.init()
    s = pygame.Surface((300, 120))
    args = ("warship", 150, 80, 200, (44, 56, 64))
    # First sight: the silhouette, while the partition is built beside the loop.
    assert not unit_models.draw_in_scene(s, *args, aob_deg=90.0, model="warship_05")
    model_bsp.wait_for_background()
    assert unit_models.draw_in_scene(s, *args, aob_deg=90.0, model="warship_05")
    # Our own small models are drawn at once.
    assert unit_models.draw_in_scene(s, *args, aob_deg=90.0, model="warship_22")


def test_sprites_grow_in_steps_and_show_their_paint_by_day():
    assert [unit_models.scene_length(w) for w in (20, 47, 48, 50, 100, 103, 240, 250)] == \
        [20, 47, 48, 50, 100, 100, 240, 250]
    assert unit_models.scene_length(110) == unit_models.scene_length(111) == 108
    day, night, haze = (44, 56, 64), (19, 36, 46), (150, 160, 165)
    assert unit_models.scene_vivid(day) > 0.95
    assert 0.2 < unit_models.scene_vivid(night) < 0.6
    assert unit_models.scene_vivid(haze) == 0.0
    red = np.array([[200.0, 40.0, 40.0]])
    assert unit_models.scene_shades(red, [1.0], day)[0, 0] > \
        unit_models.scene_shades(red, [1.0], night)[0, 0]


def test_browser_modules_of_the_designs_are_generated_and_bounded():
    from tools import gen_web_schema
    for name in tk_models.names():
        path = gen_web_schema.tk_js(name)
        text = path.read_text(encoding="utf-8")
        assert text == gen_web_schema.render_tk(name)
        assert len(text.encode("utf-8")) < 160_000
    generated = sorted(p.stem for p in gen_web_schema.tk_js("x").parent.glob("*.js"))
    assert generated == sorted(tk_models.names())
    view = (ROOT / "data/commander/js/views/model-view.js").read_text(encoding="utf-8")
    assert "export function stretchDesign" in view and "sceneLength" in view
    module = (ROOT / "data/commander/js/views/unit-variants-civil.js").read_text(encoding="utf-8")
    variants = json.loads(module.split("export const VARIANTS = ", 1)[1].split(";\n", 1)[0])
    assert variants["cargo_02"] == unit_variants.tk_ref("cargo_02")
