"""F4 map page: every contact in the game on one chart.

Host-local diagnostics only (same trust level as the F4 list): the items come
from ``Game._simlog_state_data()``, i.e. simulation truth, never from the
observation pictures. Read-only; the land layer is cached per view so the
draw path does no per-frame polygon transforms on the uConsole.
"""

import math

import pygame

from src.core import config
from src.ui import layout
from src.ui import hires


FIT_WORLD = "world"
FIT_UNITS = "units"
LABEL_MAX = 90
LEGEND_W = 310
_GRID_STEPS = (5, 10, 20, 50, 100, 200, 500)
_LIVE_RING = (110, 215, 255)

# group -> (legend key, color, marker shape)
GROUPS = {
    "own": ("simlog.view.own", (161, 231, 204), "circle"),
    "subs": ("simlog.view.subs", (255, 144, 144), "diamond"),
    "warships": ("simlog.view.map_warships", (255, 159, 110), "circle"),
    "civilians": ("simlog.view.map_civilians", (243, 197, 119), "circle"),
    "live_ships": ("simlog.view.map_live_ships", _LIVE_RING, "circle"),
    "flights": ("simlog.view.flights", (212, 195, 123), "triangle"),
    "live_air": ("simlog.view.map_live_air", _LIVE_RING, "triangle"),
    "raiders": ("simlog.view.raiders", (255, 90, 90), "triangle"),
    "helo": ("simlog.view.helo", (161, 231, 204), "triangle"),
    "animals": ("simlog.view.animals", (143, 223, 171), "dot"),
    "torpedoes": ("simlog.view.torps", (129, 197, 255), "square"),
    "enemy_torpedoes": ("simlog.view.enemy_torps", (255, 102, 102), "square"),
    "decoys": ("simlog.view.decoys", (200, 156, 255), "square"),
    "asms": ("simlog.view.asms", (255, 159, 110), "square"),
    "essms": ("simlog.view.essms", (143, 207, 255), "square"),
    "asrocs": ("simlog.view.asrocs", (240, 220, 133), "square"),
    "nixies": ("simlog.view.nixies", (200, 156, 255), "dot"),
    "buoys": ("simlog.view.buoys", (118, 213, 176), "dot"),
}

_land_cache: dict = {}


def map_items(snap: dict) -> list[dict]:
    """Flatten the state snapshot into positioned, plottable items."""
    items: list[dict] = []

    def add(group, row, label, dead=False):
        if row.get("x") is None or row.get("y") is None:
            return
        items.append(dict(group=group, label=label, x=row["x"], y=row["y"],
                          course=row.get("course"), dead=bool(dead)))

    add("own", snap["ship"], "")
    for row in snap["subs"]:
        add("subs", row, str(row["id"]), row["sunk"])
    for row in snap["surfaces"]:
        group = ("warships" if row["kind"] == "warship"
                 else "live_ships" if row.get("mmsi") is not None
                 else "civilians")
        add(group, row, str(row["id"]), row["sunk"])
    for row in snap["flights"]:
        add("live_air" if row["kind"] == "live" else "flights", row,
            f"A-{row['seq']}")
    for row in snap["raiders"]:
        add("raiders", row, f"R-{row['seq']}")
    helo = snap["helo"]
    if helo.get("airborne"):
        add("helo", helo, "")
    for row in snap["animals"]:
        add("animals", row, str(row["id"]), row["dead"])
    for row in snap["torpedoes"]:
        add("torpedoes", row, f"T{row['id']}")
    for row in snap["enemy_torpedoes"]:
        add("enemy_torpedoes", row, f"T{row['id']}")
    for row in snap["decoys"]:
        add("decoys", row, f"D{row['id']}", row["dead"])
    for group in ("asms", "essms", "asrocs"):
        for row in snap[group]:
            add(group, row, f"M{row['seq']}")
    for row in snap["nixies"]:
        add("nixies", row, "", row["dead"])
    for row in snap["buoys"]:
        add("buoys", row, "")
    return items


def _bounds(game, items, fit):
    if fit == FIT_WORLD or not items:
        size = float(game.world.size_nm)
        return 0.0, 0.0, size, size
    xs = [item["x"] for item in items]
    ys = [item["y"] for item in items]
    span = max(10.0, max(xs) - min(xs), max(ys) - min(ys))
    cx, cy = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
    # Quantized so the cached land layer is not rebuilt on every frame.
    cx, cy = round(cx / 5.0) * 5.0, round(cy / 5.0) * 5.0
    radius = math.ceil(span * 0.58 / 5.0) * 5.0
    return cx - radius, cy - radius, cx + radius, cy + radius


def _land_surface(game, plot, view, scale, offset):
    coast = game.world.coast
    key = (id(coast), len(coast.landmasses), tuple(view), plot.size, hires.SCALE)
    cached = _land_cache.get("land")
    if cached is not None and cached[0] == key:
        return cached[1]
    surface = hires.surface(plot.size)
    surface.fill(config.COLOR_GEO_BG)
    left, top, right, bottom = view
    for land in coast.landmasses:
        bx0, by0, bx1, by1 = land.bounds
        if bx1 < left or bx0 > right or by1 < top or by0 > bottom:
            continue
        points = [(offset[0] + (x - left) * scale, offset[1] + (y - top) * scale)
                  for x, y in land.points]
        if len(points) >= 3:
            pygame.draw.polygon(surface, config.COLOR_LAND, points)
            pygame.draw.polygon(surface, config.COLOR_LAND_EDGE, points, 1)
    _land_cache["land"] = (key, surface)
    return surface


def _draw_marker(surface, shape, color, x, y, dead):
    size = 5
    if shape == "circle":
        pygame.draw.circle(surface, color, (x, y), size, 1 if dead else 0)
    elif shape == "dot":
        pygame.draw.circle(surface, color, (x, y), 2)
    elif shape == "square":
        pygame.draw.rect(surface, color, (x - 3, y - 3, 6, 6), 1)
    elif shape == "diamond":
        pygame.draw.polygon(surface, color, [(x, y - size - 1), (x + size + 1, y),
                                             (x, y + size + 1), (x - size - 1, y)],
                            1 if dead else 0)
    else:
        pygame.draw.polygon(surface, color, [(x, y - size - 1), (x + size, y + size),
                                             (x - size, y + size)],
                            1 if dead else 0)
    if dead:
        pygame.draw.line(surface, config.COLOR_DANGER, (x - 7, y - 7), (x + 7, y + 7), 2)
        pygame.draw.line(surface, config.COLOR_DANGER, (x - 7, y + 7), (x + 7, y - 7), 2)


def _draw_grid(surface, face, view, scale, offset, plot_size):
    left, top, right, bottom = view
    span = max(right - left, bottom - top)
    step = next((s for s in _GRID_STEPS if span / s <= 12), _GRID_STEPS[-1])
    x = math.ceil(left / step) * step
    while x <= right:
        px = offset[0] + (x - left) * scale
        pygame.draw.line(surface, config.COLOR_GEO_GRID, (px, 0), (px, plot_size[1]))
        surface.blit(face.render(f"{x:.0f}", True, config.COLOR_TEXT_DIM), (px + 2, 2))
        x += step
    y = math.ceil(top / step) * step
    while y <= bottom:
        py = offset[1] + (y - top) * scale
        pygame.draw.line(surface, config.COLOR_GEO_GRID, (0, py), (plot_size[0], py))
        surface.blit(face.render(f"{y:.0f}", True, config.COLOR_TEXT_DIM), (2, py + 2))
        y += step


def draw_map(game, tr, snap, body, fit) -> None:
    """Chart on the left, legend with per-group counts on the right."""
    s = game.screen
    items = map_items(snap)
    plot = pygame.Rect(body.x, body.y, body.w - LEGEND_W - 8, body.h)
    legend = pygame.Rect(plot.right + 8, body.y, LEGEND_W, body.h)
    view = _bounds(game, items, fit)
    left, top, right, bottom = view
    pad = 6
    scale = max(1e-4, min((plot.w - 2 * pad) / max(1e-3, right - left),
                          (plot.h - 2 * pad) / max(1e-3, bottom - top)))
    offset = ((plot.w - (right - left) * scale) / 2.0,
              (plot.h - (bottom - top) * scale) / 2.0)
    tiny = layout.font(12)
    label_face = layout.font(13)
    chart = hires.surface(plot.size)
    chart.blit(_land_surface(game, plot, view, scale, offset), (0, 0))
    _draw_grid(chart, tiny, view, scale, offset, plot.size)
    pygame.draw.rect(chart, config.COLOR_SONAR_RING,
                     (offset[0], offset[1], (right - left) * scale,
                      (bottom - top) * scale), 1)
    labelled = 0
    for item in items:
        _, color, shape = GROUPS[item["group"]]
        px = offset[0] + (item["x"] - left) * scale
        py = offset[1] + (item["y"] - top) * scale
        if not (-10 <= px <= plot.w + 10 and -10 <= py <= plot.h + 10):
            continue
        if item["course"] is not None and not item["dead"]:
            angle = math.radians(item["course"])
            pygame.draw.line(chart, color, (px, py),
                             (px + math.sin(angle) * 16, py - math.cos(angle) * 16), 1)
        if item["group"] in ("live_ships", "live_air"):
            pygame.draw.circle(chart, _LIVE_RING, (px, py), 9, 1)
        _draw_marker(chart, shape, color, px, py, item["dead"])
        if item["label"] and labelled < LABEL_MAX:
            chart.blit(label_face.render(item["label"], True, color), (px + 8, py - 7))
            labelled += 1
    s.blit(chart, plot.topleft)
    pygame.draw.rect(s, config.COLOR_SONAR_RING, plot, 1)

    pygame.draw.rect(s, config.COLOR_PANEL_BG, legend)
    pygame.draw.rect(s, config.COLOR_SONAR_RING, legend, 1)
    row_h = int(layout.font(15).get_linesize() * 1.2)
    y = legend.y + 8
    counts = {}
    for item in items:
        counts[item["group"]] = counts.get(item["group"], 0) + 1
    face = layout.font(15)
    head = tr("simlog.view.map_count", count=len(items))
    s.blit(face.render(layout.ellipsize(head, face, legend.w - 20), True,
                       config.COLOR_WARN), (legend.x + 10, y))
    y += row_h
    fit_key = ("simlog.view.map_fit_world" if fit == FIT_WORLD
               else "simlog.view.map_fit_units")
    s.blit(face.render(layout.ellipsize(tr(fit_key), face, legend.w - 20), True,
                       config.COLOR_TEXT_DIM), (legend.x + 10, y))
    y += row_h + 6
    for group, (key, color, shape) in GROUPS.items():
        if group not in counts:
            continue
        if y + row_h > legend.bottom - 4:
            break
        _draw_marker(s, shape, color, legend.x + 16, y + row_h // 2 - 2, False)
        if group in ("live_ships", "live_air"):
            pygame.draw.circle(s, _LIVE_RING, (legend.x + 16, y + row_h // 2 - 2), 9, 1)
        text = f"{tr(key)}: {counts[group]}"
        s.blit(face.render(layout.ellipsize(text, face, legend.w - 44), True,
                           config.COLOR_TEXT), (legend.x + 34, y))
        y += row_h
