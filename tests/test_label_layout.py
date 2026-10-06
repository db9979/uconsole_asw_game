"""Chart labels step aside instead of covering each other."""

import itertools
import math

import pygame

from src.ui import label_layout


def test_second_label_moves_off_the_first():
    field = label_layout.LabelField((0, 0, 400, 300))
    first = field.place((40, 16), label_layout.around((100, 100), (40, 16)))
    second = field.place((40, 16), label_layout.around((102, 101), (40, 16)))
    assert first.topleft == (100, 100)
    assert not first.colliderect(second)


def test_label_stays_inside_the_chart():
    field = label_layout.LabelField((10, 10, 200, 100))
    rect = field.place((60, 16), label_layout.around((190, 0), (60, 16)))
    assert pygame.Rect(10, 10, 200, 100).contains(rect)


def test_reserved_symbol_is_kept_free():
    field = label_layout.LabelField((0, 0, 400, 300))
    field.reserve((95, 95, 30, 30))
    rect = field.place((40, 16), label_layout.around((100, 100), (40, 16)))
    assert not rect.colliderect(pygame.Rect(95, 95, 30, 30))


def test_crowded_label_is_never_dropped_and_placement_is_deterministic():
    def run():
        field = label_layout.LabelField((0, 0, 120, 40))
        return [field.place((50, 16), label_layout.around((30, 10), (50, 16))).topleft
                for _ in range(12)]
    first = run()
    assert len(first) == 12
    assert first == run()


def test_bearing_labels_slide_along_their_line():
    field = label_layout.LabelField((0, 0, 600, 600))
    origin, unit = (300, 300), (0.0, -1.0)
    a = field.place((30, 16), label_layout.along(origin, unit, (90, 125, 160), (30, 16)))
    b = field.place((30, 16), label_layout.along(origin, unit, (90, 125, 160), (30, 16)))
    assert not a.colliderect(b)


def test_map_label_uses_the_active_scope():
    from types import SimpleNamespace
    from src.ui.map_view import _map_label
    pygame.font.init()
    surface = pygame.Surface((400, 300))
    game = SimpleNamespace(font=pygame.font.Font(None, 18))
    with label_layout.label_scope((0, 0, 400, 300)) as field:
        _map_label(surface, game, "K02", (100, 100), (255, 255, 255), (0, 0, 400, 300))
        _map_label(surface, game, "K06", (101, 100), (255, 255, 255), (0, 0, 400, 300))
    assert len(field.rects) == 2
    assert not field.rects[0].colliderect(field.rects[1])


def test_labels_of_points_far_off_the_chart_sit_beside_each_other():
    """Every candidate of a point far above the chart clamps to the same spot
    on the top edge; the labels slide apart instead of stacking."""
    field = label_layout.LabelField((0, 0, 600, 400))
    rects = [field.place((110, 16), label_layout.around((300 + dx, -900), (110, 16)))
             for dx in (0, 8, -5, 3)]
    for a, b in itertools.combinations(rects, 2):
        assert not a.colliderect(b), (a, b)
    assert all(pygame.Rect(0, 0, 600, 400).contains(rect) for rect in rects)


def test_web_twin_slides_edge_labels_apart_too():
    import json
    import shutil
    import subprocess
    from pathlib import Path
    node = shutil.which("node")
    if node is None:
        import pytest
        pytest.skip("node not installed")
    module = (Path(__file__).resolve().parents[1] / "data/commander/js/views/label-layout.js").as_uri()
    script = (f"import {{ labelField, around, edgeAnchor }} from {json.dumps(module)};"
              "const f = labelField(600, 400); const out = [];"
              "for (const dx of [0, 8, -5, 3]) out.push(f.place(110, 16, around(300 + dx, -900, 110, 16)));"
              "console.log(JSON.stringify({out, edge: edgeAnchor(600, 400, 300, -900)}));")
    result = subprocess.run([node, "--input-type=module", "-e", script],
                            capture_output=True, text=True, check=True, timeout=30)
    data = json.loads(result.stdout)
    rects = [pygame.Rect(r["x"], r["y"], r["w"], r["h"]) for r in data["out"]]
    for a, b in itertools.combinations(rects, 2):
        assert not a.colliderect(b), (a, b)
    ex, ey, ux, uy = data["edge"]
    assert (round(ex), round(ey)) == (300, 10) and (ux, uy) == (0, -1)


def test_edge_anchor_puts_off_chart_points_on_the_edge():
    from src.ui import plot_view
    chart = pygame.Rect(100, 50, 600, 400)
    (x, y), (ux, uy) = plot_view.edge_anchor(chart, (400, -5000))
    assert (round(x), round(y)) == (400, 60) and (round(ux), round(uy)) == (0, -1)
    (x, y), _ = plot_view.edge_anchor(chart, (9000, 250))
    assert (round(x), round(y)) == (690, 250)


def test_labels_keep_off_reserved_lines():
    """A label never lies across a motion vector or a trail (bug report
    2026-10-06: the course line ran through every ship's name)."""
    field = label_layout.LabelField((0, 0, 400, 300))
    field.reserve_line((100, 100), (180, 100))
    rect = field.place((60, 14), label_layout.around((110, 93), (60, 14)))
    assert not rect.inflate(2, 2).clipline((100, 100), (180, 100))


def test_beside_puts_the_label_abeam_of_the_course():
    size = (60, 14)
    east = pygame.Rect(label_layout.beside((200, 150), size, 90.0)[0], size)
    assert east.top > 150 and east.left < 200 < east.right   # below, centred
    north = pygame.Rect(label_layout.beside((200, 150), size, 0.0)[0], size)
    assert north.left > 200 and north.top < 150 < north.bottom   # right, level
    for course in range(0, 360, 15):
        rect = pygame.Rect(label_layout.beside((200, 150), size, float(course))[0], size)
        tip = (200 + 80 * math.sin(math.radians(course)),
               150 - 80 * math.cos(math.radians(course)))
        trail = (200 - 80 * math.sin(math.radians(course)),
                 150 + 80 * math.cos(math.radians(course)))
        assert not rect.clipline((200, 150), tip), course
        assert not rect.clipline((200, 150), trail), course


def test_keyed_label_keeps_its_spot_while_free():
    """A label returns to last frame's spot instead of jumping to the first
    candidate whenever that one frees up again."""
    candidates = [(10, 10), (10, 40), (10, 70)]
    first = label_layout.LabelField((0, 0, 200, 200))
    first.reserve((10, 10, 40, 14))
    assert first.place((40, 14), candidates, key="test-keep").topleft == (10, 40)
    second = label_layout.LabelField((0, 0, 200, 200))
    assert second.place((40, 14), candidates, key="test-keep").topleft == (10, 40)
    third = label_layout.LabelField((0, 0, 200, 200))
    third.reserve((10, 40, 40, 14))
    assert third.place((40, 14), candidates, key="test-keep").topleft == (10, 10)


def test_deferred_scope_places_labels_after_lines():
    surface = pygame.Surface((400, 300))
    pygame.font.init()
    with label_layout.label_scope((0, 0, 400, 300), deferred=True) as field:
        label_layout.blit_line(surface, "LABEL", (110, 93, 80, 14), (255, 255, 255))
        assert field.rects == []           # not yet placed
        label_layout.reserve_segment((100, 100), (220, 100))
    assert len(field.rects) == 1
    assert not field.rects[0].clipline((100, 100), (220, 100))


def test_web_twin_keeps_labels_off_lines_and_remembers_spots():
    import json
    import shutil
    import subprocess
    from pathlib import Path
    node = shutil.which("node")
    if node is None:
        import pytest
        pytest.skip("node not installed")
    module = (Path(__file__).resolve().parents[1] / "data/commander/js/views/label-layout.js").as_uri()
    script = (f"import {{ labelField, around, beside }} from {json.dumps(module)};"
              "const f = labelField(400, 300); f.reserveLine(100, 100, 180, 100);"
              "const a = f.place(60, 14, around(110, 93, 60, 14), 'k');"
              "const g = labelField(400, 300);"
              "const b = g.place(60, 14, around(110, 93, 60, 14), 'k');"
              "const east = beside(200, 150, 60, 14, 90)[0];"
              "console.log(JSON.stringify({a, b, east}));")
    result = subprocess.run([node, "--input-type=module", "-e", script],
                            capture_output=True, text=True, check=True, timeout=30)
    data = json.loads(result.stdout)
    a = pygame.Rect(data["a"]["x"], data["a"]["y"], data["a"]["w"], data["a"]["h"])
    assert not a.inflate(2, 2).clipline((100, 100), (180, 100))
    assert (data["b"]["x"], data["b"]["y"]) == (data["a"]["x"], data["a"]["y"])
    east = pygame.Rect(data["east"][0], data["east"][1], 60, 14)
    assert east.top > 150 and east.left < 200 < east.right
    # Same candidates as the uConsole.
    assert tuple(data["east"]) == label_layout.beside((200, 150), (60, 14), 90.0)[0]
