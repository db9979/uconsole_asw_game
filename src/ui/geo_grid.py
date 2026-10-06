"""Meridians, parallels and their degree/minute labels for the station charts.

The Bridge and boat charts draw theirs in :func:`src.ui.map_view.draw_chart_geography`;
the OPZ plot, the radio room's cross-fix chart and the boat's pilot chart use
these helpers so every chart of a real sea area reads in latitude and
longitude.  A world without a chart centre (the fixed chart) has no
graticule: the callers keep their NM grid there.  Display only.
"""

import pygame

from src.core import config
from src.core.i18n import raw_text
from src.ui import label_layout, layout, lines
from src.world import geo


def screen_graticule(game, view, rect, lat_min_px=80.0, lon_min_px=120.0):
    """``(columns, rows)`` of the graticule visible in ``rect`` through
    ``view`` (a camera with ``screen_to_world``/``world_to_screen``):
    columns ``[(px, label)]`` of the meridians, rows ``[(py, label)]`` of
    the parallels.  None without a chart centre."""
    world = game.world
    rect = pygame.Rect(rect)
    left, top = view.screen_to_world(rect.x, rect.y)
    right, bottom = view.screen_to_world(rect.right, rect.bottom)
    size = float(world.size_nm)
    grid = geo.graticule(world, max(0.0, min(left, right)), min(size, max(left, right)),
                         max(0.0, min(top, bottom)), min(size, max(top, bottom)),
                         view.scale, lat_min_px, lon_min_px)
    if grid is None:
        return None
    meridians, parallels, lon_step, lat_step = grid
    sep = geo.decimal_sep(game)
    columns = [(view.world_to_screen(x_nm, 0.0)[0], geo.axis_label(lon, lon_step, False, sep))
               for x_nm, lon in meridians]
    rows = [(view.world_to_screen(0.0, y_nm)[1], geo.axis_label(lat, lat_step, True, sep))
            for y_nm, lat in parallels]
    return columns, rows


def draw_lines(surface, rect, columns, rows, color=None) -> None:
    """The graticule's lines across ``rect``."""
    rect = pygame.Rect(rect)
    color = config.COLOR_GEO_GRID if color is None else color
    for px, _text in columns:
        if rect.left <= px <= rect.right:
            lines.line(surface, color, (int(px), rect.top), (int(px), rect.bottom - 1), 1)
    for py, _text in rows:
        if rect.top <= py <= rect.bottom:
            lines.line(surface, color, (rect.left, int(py)), (rect.right - 1, int(py)), 1)


def draw_labels(surface, rect, columns, rows, size=None, top_clear=0) -> list:
    """Axis numbers: longitudes along the bottom edge, latitudes along the
    left edge.  Each stays at its line; one whose place another chart label
    already holds (inside a label scope) is left out, as is one that would
    run off the chart or into the corner.  ``top_clear`` keeps the latitude
    numbers below a band along the top edge.  Returns the drawn texts."""
    rect = pygame.Rect(rect)
    size = layout.MIN_OPERATIONAL_FONT if size is None else size
    face = layout.font(size)
    height = face.get_linesize()
    left_w = max([layout.text_width(face, text) for _px, text in rows] + [0]) + 6
    bottom = rect.bottom - height - 2
    shown = []
    for px, text in columns:
        x = int(px) + 3
        width = layout.text_width(face, text) + 2
        if x < rect.x + left_w or x + width > rect.right - 2:
            continue
        if label_layout.blit_fixed(surface, raw_text(text), (x, bottom, width + 2, height),
                                   config.COLOR_TEXT_DIM, size=size, skip_if_taken=True):
            shown.append(text)
    for py, text in rows:
        y = int(py) + 2
        if y < rect.y + top_clear or y + height > bottom:
            continue
        width = layout.text_width(face, text) + 2
        if label_layout.blit_fixed(surface, raw_text(text), (rect.x + 3, y, width + 2, height),
                                   config.COLOR_TEXT_DIM, size=size, skip_if_taken=True):
            shown.append(text)
    return shown


def position_rect(game, rect, size=None, corner="topright"):
    """The box of the own position line in a corner of ``rect``,
    or None without a chart centre."""
    text = geo.format_position(game.world, 0.0, 0.0, 1, geo.decimal_sep(game))
    if text is None:
        return None
    rect = pygame.Rect(rect)
    face = layout.font(layout.MIN_OPERATIONAL_FONT if size is None else size)
    # Sized for the widest position, so the box never jumps with the minutes.
    width = min(rect.w - 8, layout.text_width(face, "00°00,0'N 000°00,0'W") + 4)
    height = face.get_linesize()
    x = rect.right - 4 - width if corner.endswith("right") else rect.x + 4
    y = rect.y + 4 if corner.startswith("top") else rect.bottom - 4 - height
    return pygame.Rect(x, y, width, height)


def draw_position(surface, game, rect, x_nm, y_nm, size=None, corner="topright"):
    """The own position in degrees and minutes in a corner of the chart
    (reserved inside a label scope, so chart labels step aside); returns the
    box drawn, or None without a chart centre."""
    text = geo.format_position(game.world, x_nm, y_nm, 1, geo.decimal_sep(game))
    box = position_rect(game, rect, size, corner)
    if text is None or box is None:
        return None
    field = label_layout.active()
    if field is not None:
        field.reserve(box)
    layout.blit_line(surface, raw_text(text), box, config.COLOR_TEXT,
                     size=layout.MIN_OPERATIONAL_FONT if size is None else size,
                     align="right" if corner.endswith("right") else "left")
    return box
