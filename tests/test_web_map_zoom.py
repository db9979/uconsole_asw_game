"""The browser charts zoom in as far as the uConsole's (half a sea mile)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from src.core import config

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "data" / "commander" / "js"


def _run(script: str) -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    module = (JS / "core" / "map-zoom.js").as_uri()
    result = subprocess.run(
        [node, "--input-type=module", "-e", f"import * as z from {json.dumps(module)};\n{script}"],
        capture_output=True, text=True, timeout=30, check=True)
    return json.loads(result.stdout)


def test_deepest_zoom_matches_the_uconsole_detail_zoom():
    # The uConsole's detail zoom shows 0.5 NM on the chart height.
    uconsole_nm = config.MAP_ZOOM_STEPS_NM[-1]
    out = _run("""console.log(JSON.stringify({
      detail: z.MAP_DETAIL_NM,
      roleMax: z.mapZoomMax(500), chartMax: z.mapZoomMax(500, .9),
      clampedIn: z.clampMapZoom(1e9, 500), clampedOut: z.clampMapZoom(1e-9, 500),
      oldLimit: z.clampMapZoom(32 * 1.4, 500)}));""")
    assert out["detail"] <= uconsole_nm
    # Role map: shorter side = size / zoom; operations chart fits 90 %.
    assert 500 / out["roleMax"] == pytest.approx(uconsole_nm)
    assert 500 / (out["chartMax"] * .9) == pytest.approx(uconsole_nm)
    assert out["clampedIn"] == out["roleMax"] and out["clampedOut"] == .5
    # The former limit (32x, about 16 NM wide) no longer stops zooming.
    assert out["oldLimit"] == pytest.approx(44.8)


def test_grid_gets_finer_at_deep_zoom():
    out = _run("""console.log(JSON.stringify([
      z.mapGridStep(1.4, 80), z.mapGridStep(1400, 80), z.mapGridStep(2800, 80),
      z.stepDecimals(10), z.stepDecimals(.5), z.stepDecimals(.05)]));""")
    assert out == [100, 0.1, 0.05, 0, 1, 2]


def test_every_web_chart_uses_the_shared_zoom_range_and_pinch():
    wiring = (JS / "input" / "wiring.js").read_text(encoding="utf-8")
    lookout = (JS / "views" / "lookout.js").read_text(encoding="utf-8")
    assert "Math.min(32," not in wiring and "Math.min(256," not in lookout
    assert "clampMapZoom(state.zoom * factor, S.chart.size_nm)" in wiring
    assert "clampMapZoom(view.zoom * factor, S.chart.size_nm, .9)" in lookout
    # Pinch on touch for the station chart and the operations chart.
    assert 'wirePinch($("role-map"), changeRoleMapZoom)' in wiring
    assert "wirePinch(canvas, zoom)" in wiring
