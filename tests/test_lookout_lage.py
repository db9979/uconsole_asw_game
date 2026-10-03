"""Other ships in the eyepieces as the eye sees them from the own ship: the
bearing places them, the angle on the bow turns them (bow left or right,
toward or away) and the range sets how far below the sea horizon their
waterline lies; a nearer ship stands in front of a farther one."""

import json
import math
import re
from pathlib import Path

import numpy as np
import pygame
import pytest

from src.core.game import Game
from src.sensors import lookout_id
from src.sensors.visual import LOOKOUT_EYE_HEIGHT_M
from src.ui import horizon, sight_scene, unit_models
from src.ui.stations import bridge as bridge_view

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _pygame():
    pygame.init()
    yield


def _bow_on_screen(aob_deg):
    """(right, toward) of the model's bow (+x) as the eyepiece turns it."""
    view = unit_models._view(unit_models.scene_yaw(aob_deg), unit_models.SCENE_ELEVATION_RAD)
    right, _up, toward = view @ np.array([0.5, 0.0, 0.0])
    return right, toward


@pytest.mark.parametrize("own_bearing, target_course, aob, bow", [
    # Dead ahead, coming at us: bow on.
    (0.0, 180.0, 0.0, "toward"),
    # Dead ahead, running away: stern on.
    (0.0, 0.0, 180.0, "away"),
    # Abeam to starboard (bearing 090) heading north: we see her port side,
    # her bow points left (north is left when looking east).
    (90.0, 0.0, -90.0, "left"),
    # Abeam to port (bearing 270) heading north: starboard side, bow right.
    (270.0, 0.0, 90.0, "right"),
    # North-east of us heading east (crossing ahead to the right, opening):
    # her starboard quarter, bow right and away.
    (45.0, 90.0, 140.0, "right"),
    # North-east of us heading west (crossing ahead to the left, closing):
    # her port bow, bow left and toward us.
    (45.0, 270.0, -40.0, "left"),
])
def test_angle_on_bow_turns_the_bow_to_the_right_side(own_bearing, target_course, aob, bow):
    judged = lookout_id.angle_on_bow(target_course, own_bearing)
    assert judged == pytest.approx(aob)
    right, toward = _bow_on_screen(judged)
    if bow == "toward":
        assert toward > 0.4 and abs(right) < 1e-6
    elif bow == "away":
        assert toward < -0.4 and abs(right) < 1e-6
    elif bow == "right":
        assert right > 0.3
    else:
        assert right < -0.3
    # The quarter a crossing ship shows: closing bow toward, opening away.
    if abs(judged) < 90.0:
        assert toward > 0.0
    elif abs(judged) > 90.0:
        assert toward < 0.0


def test_the_waterline_drops_below_the_horizon_close_aboard():
    eye = LOOKOUT_EYE_HEIGHT_M
    half = sight_scene.waterline_drop_deg(0.5 * 1852.0, eye)
    one = sight_scene.waterline_drop_deg(1852.0, eye)
    assert half == pytest.approx(0.97, abs=0.03)
    assert one == pytest.approx(0.43, abs=0.03)
    assert half > one > sight_scene.waterline_drop_deg(3 * 1852.0, eye) > 0.0
    # Beyond the eye's sea horizon (about 9 NM from 18 m) it sits on the line.
    assert sight_scene.waterline_drop_deg(12 * 1852.0, eye) == 0.0
    assert sight_scene.waterline_drop_deg(math.inf, eye) == 0.0
    # The periscope's eye just above the water hardly looks down at all.
    assert sight_scene.waterline_drop_deg(0.5 * 1852.0, 2.5) < 0.12


def _drawn(monkeypatch, outlines, **kwargs):
    calls = []
    monkeypatch.setattr(horizon, "draw_outline",
                        lambda s, cls, cx, base, width, *a, **k: calls.append((cls, cx, base)))
    surface = pygame.Surface((640, 320))
    args = dict(line_of_sight=0.0, fov_deg=16.0, night=False, visibility_nm=20.0,
                motion=(0.0, 0.0), outlines=outlines, sea_state=0.0)
    args.update(kwargs)
    horizon.draw_horizon(surface, (0, 0, 640, 320), **args)
    return calls


def _row(bearing, cls, range_nm):
    return (bearing, 2.0, cls, False, None, None, 90.0, None, None, range_nm)


def test_a_near_ship_sits_lower_and_in_front_of_a_far_one(monkeypatch):
    near, far, unknown = _row(1.0, "warship", 0.5), _row(2.0, "merchant", 4.0), _row(
        -3.0, "unknown", None)
    calls = _drawn(monkeypatch, [near, unknown, far])
    # Back to front whatever the list order: unranged, far, near.
    assert [cls for cls, _cx, _base in calls] == ["unknown", "merchant", "warship"]
    bases = {cls: base for cls, _cx, base in calls}
    horizon_y = 160
    px_per_deg = 640 / 16.0
    assert bases["unknown"] == horizon_y
    drop = sight_scene.waterline_drop_deg(0.5 * 1852.0, LOOKOUT_EYE_HEIGHT_M)
    assert bases["warship"] - horizon_y == int(drop * px_per_deg)
    assert bases["warship"] > bases["merchant"] >= horizon_y
    # The periscope's low eye: the same ship hardly below the line.
    low = _drawn(monkeypatch, [near], eye_m=2.5)
    assert low[0][2] - horizon_y < bases["warship"] - horizon_y
    # A way that names its eye sets it too.
    assert _drawn(monkeypatch, [near], way=dict(speed_kn=0.0, course_deg=0.0,
                                                eye_m=2.5, hull=False))[0][2] == low[0][2]


def _place(entity, origin, distance_nm, bearing_deg):
    rad = math.radians(bearing_deg)
    entity.x = origin.x + distance_nm * math.sin(rad)
    entity.y = origin.y - distance_nm * math.cos(rad)


def test_the_lookout_sees_a_crossing_ship_as_she_lies():
    game = Game(seed=5, start_menu=False, audio_enabled=False, language="en")
    warship = game.warships[0]
    for other in game.civilians + game.warships[1:]:
        _place(other, game.ship, 40.0, 180.0)
    for sub in game.subs:
        sub.depth = max(sub.depth, 100.0)
    for _ in range(60):
        game.ship.course = game.ship.target_course = 0.0
        game.ship.speed = game.ship.target_speed = 0.0
        _place(warship, game.ship, 0.6, 45.0)
        warship.course = warship.target_course = 90.0
        game.world.hour = 12.0
        game._update(0.25)
    rows = bridge_view.eye_outlines(game, game.lookout_sightings())
    assert len(rows) == 1
    bearing, _span, cls, _stale, _lights, elevation, aob, _model, _way, range_nm = rows[0]
    assert cls == "warship" and elevation is None
    assert bearing == pytest.approx(45.0, abs=1.5)
    # Her starboard quarter: bow to the right, running away.
    assert aob == pytest.approx(140.0)
    assert range_nm == pytest.approx(0.6, rel=0.25)


def test_browser_places_the_waterline_as_the_uconsole(tmp_path):
    import functools
    import http.server
    import shutil
    import subprocess
    import threading

    chromium = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
    if not chromium:
        pytest.skip("Chromium is not installed")
    cases = [(0.25, 18.0), (0.5, 18.0), (1.0, 18.0), (3.0, 18.0), (12.0, 18.0), (0.5, 2.5)]
    (tmp_path / "js").symlink_to(ROOT / "data" / "commander" / "js")
    (tmp_path / "index.html").write_text("""<!doctype html><html><body><pre id="out"></pre>
<script type="module">
import { waterlineDropDeg, rowRange } from "./js/views/sight-scene.js";
const cases = __CASES__;
const rows = [{range_nm: 0.5}, {range_nm: null}, {range_nm: 4}];
const order = rows.slice().sort((a, b) => (rowRange(a) === rowRange(b) ? 0 : rowRange(b) - rowRange(a)));
document.getElementById("out").textContent = JSON.stringify({
  drops: cases.map(([nm, eye]) => waterlineDropDeg(nm * 1852, eye)),
  order: order.map((row) => row.range_nm)});
</script></body></html>""".replace("__CASES__", json.dumps(cases)), encoding="utf-8")
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
    expected = [sight_scene.waterline_drop_deg(nm * 1852.0, eye) for nm, eye in cases]
    assert out["drops"] == pytest.approx(expected, abs=1e-9)
    assert out["order"] == [None, 4, 0.5]
