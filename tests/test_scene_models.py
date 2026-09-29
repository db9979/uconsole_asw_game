"""3D models in the eyepieces (lookout, binoculars, periscope), turned by
the angle on the bow the observer judges of a made-out silhouette."""

import sys
from pathlib import Path

import pygame
import pytest

from src.commander import projections
from src.core import opfor
from src.sensors import lookout_id
from src.ui import horizon, unit_models, uboot_scope
from src.ui.stations import bridge as bridge_view

sys.path.insert(0, str(Path(__file__).parent))
from test_nav_lights import _neutral_near  # noqa: E402
from test_uboot_scope import _clear, _crewed, _environment, _scope_up  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("course, bearing, expected", [
    (90.0, 0.0, 90.0),       # seen from the south going east: starboard side
    (270.0, 0.0, -90.0),     # going west: port side
    (180.0, 0.0, 0.0),       # coming straight at the observer: bow on
    (0.0, 0.0, 180.0),       # going away: stern on
    (134.0, 0.0, 50.0),      # judged in 10 degree steps
])
def test_angle_on_the_bow(course, bearing, expected):
    assert lookout_id.angle_on_bow(course, bearing) == expected


def test_full_span_turns_the_measured_length_back():
    assert uboot_scope.full_span(2.0, None) == 2.0
    assert uboot_scope.full_span(2.0, 90.0) == pytest.approx(2.0)
    assert uboot_scope.full_span(1.0, 30.0) == pytest.approx(2.0)
    assert uboot_scope.full_span(1.0, 0.0) == pytest.approx(5.0)      # bow on: bounded
    assert uboot_scope.full_span(100.0, 10.0) == 180.0


def test_draw_in_scene_falls_back_and_cuts_at_the_waterline():
    pygame.init()
    s = pygame.Surface((300, 120))
    color = (44, 56, 64)
    assert not unit_models.draw_in_scene(s, "merchant", 150, 80, 200, color, aob_deg=None)
    assert not unit_models.draw_in_scene(s, "merchant", 150, 80, 10, color, aob_deg=60.0)
    assert not unit_models.draw_in_scene(s, "torpedo", 150, 80, 200, color, aob_deg=60.0)
    s.fill((0, 0, 0))
    assert unit_models.draw_in_scene(s, "merchant", 150, 80, 200, color, aob_deg=60.0)
    painted = [(x, y) for x in range(300) for y in range(120) if s.get_at((x, y))[:3] != (0, 0, 0)]
    assert len(painted) > 400
    assert max(y for _x, y in painted) <= 82           # nothing below the waterline
    # Turned: bow on the model is much narrower than abeam.
    widths = {}
    for aob in (0.0, 90.0):
        s.fill((0, 0, 0))
        unit_models.draw_in_scene(s, "warship", 150, 80, 200, color, aob_deg=aob)
        xs = [x for x in range(300) for y in range(120) if s.get_at((x, y))[:3] != (0, 0, 0)]
        widths[aob] = max(xs) - min(xs)
    assert widths[0.0] < widths[90.0] / 3
    # Sprites are cached by class, size, aspect and colour.
    key_count = len(unit_models._SCENE_CACHE)
    unit_models.draw_in_scene(s, "warship", 150, 80, 200, color, aob_deg=90.0)
    assert len(unit_models._SCENE_CACHE) == key_count <= unit_models.SCENE_CACHE_SIZE
    pygame.quit()


def test_the_eyepiece_outline_draws_the_turned_model(monkeypatch):
    pygame.init()
    seen = []
    monkeypatch.setattr(unit_models, "draw_in_scene",
                        lambda *a, aob_deg=None, **k: seen.append(aob_deg) or aob_deg is not None)
    s = pygame.Surface((400, 200))
    horizon.draw_outline(s, "merchant", 200, 100, 80, (44, 56, 64), aob_deg=40.0)
    horizon.draw_outline(s, "merchant", 200, 100, 80, (44, 56, 64))
    assert seen == [40.0, None]
    pygame.quit()


def test_the_lookout_judges_the_aspect_of_a_recognized_ship():
    game, _server, _bridge = _crewed(seed=61)
    game._lookout_environment = lambda: _environment(False)
    game.crew_effect = lambda: 1.0
    ship = game.civilians[0]
    for other in game.civilians[1:] + game.warships:
        other.x, other.y = game.ship.x + 60.0, game.ship.y + 60.0
    ship.x, ship.y, ship.course = game.ship.x, game.ship.y - 1.0, 270.0
    game.world.land_blocks_line = lambda *args: False
    for _ in range(40):
        game.sim_t += 1.0
        game._update_lookout_picture()
        rows = bridge_view.lookout_outlines(game, game.lookout_sightings())
        if any(row[6] is not None for row in rows):
            break
    turned = [row for row in rows if row[6] is not None]
    assert turned and turned[0][6] == -90.0          # port side, bow to the left
    glasses = projections._lookout_glasses(game)
    assert [row["aob_deg"] for row in glasses["outlines"] if row["aob_deg"] is not None] == [-90.0]
    # A ship out of sight loses its judged aspect.
    ship.x, ship.y = game.ship.x + 80.0, game.ship.y
    for _ in range(12):
        game.sim_t += 5.0
        game._update_lookout_picture()
    rows = bridge_view.lookout_outlines(game, game.lookout_sightings())
    assert all(row[6] is None for row in rows)


def test_the_periscope_judges_the_aspect_and_the_full_length():
    game, _server, _bridge = _crewed(seed=61)
    boat = game.opfor
    _scope_up(boat)
    _clear(game)
    _neutral_near(game, boat, course=90.0)
    opfor.update_sightings(game, boat)
    rows = [row for row in boat.orders.sightings if row["cls"] in ("merchant", "unknown")]
    assert rows, boat.orders.sightings
    assert boat.orders._aspect[rows[0]["ref"]] == 90.0
    outlines = [row for row in uboot_scope.scope_outlines(game, boat) if row[6] is not None]
    assert outlines and outlines[0][6] == 90.0
    scope = projections._uboot_scope(game, boat)
    assert [row["aob_deg"] for row in scope["sightings"] if row["aob_deg"] is not None] == [90.0]


def test_browser_eyepieces_use_the_same_models():
    scene = (ROOT / "data/commander/js/views/sight-scene.js").read_text(encoding="utf-8")
    assert 'import { drawInScene } from "./model-view.js"' in scene
    assert "row.aob_deg" in scene
    graphics = (ROOT / "data/commander/js/stations/uboot-graphics.js").read_text(encoding="utf-8")
    assert "fullSpan(row.span_deg, row.aob_deg)" in graphics
    models = (ROOT / "data/commander/js/views/unit-models.js").read_text(encoding="utf-8")
    assert f"export const SCENE_MIN_PX = {unit_models.SCENE_MIN_PX};" in models


def test_browser_draws_the_turned_models_in_real_chromium(tmp_path):
    import functools
    import http.server
    import json
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
import { drawInScene } from "./js/views/model-view.js";
const out = {};
for (const [cls, aob] of [["merchant", 60], ["warship", 0], ["submarine", 120], ["aircraft", 90]]) {
  const canvas = document.createElement("canvas");
  canvas.width = 300; canvas.height = 160;
  const g = canvas.getContext("2d");
  const frame = drawInScene(g, cls, 150, 100, 200, [44, 56, 64], aob);
  const data = g.getImageData(0, 0, 300, 160).data;
  let painted = 0, low = 0;
  for (let i = 3; i < data.length; i += 4) if (data[i]) { painted += 1; low = Math.max(low, Math.floor((i >> 2) / 300)); }
  out[cls] = [painted, low, !!frame];
}
out.flat = drawInScene(document.createElement("canvas").getContext("2d"), "merchant", 0, 0, 200, [0, 0, 0], null);
out.small = drawInScene(document.createElement("canvas").getContext("2d"), "merchant", 0, 0, 10, [0, 0, 0], 60);
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
    assert out.pop("flat") is None and out.pop("small") is None
    for cls, (painted, low, frame) in out.items():
        assert frame and painted > 300, cls
        if cls != "aircraft":
            assert low <= 102, cls              # cut at the waterline
