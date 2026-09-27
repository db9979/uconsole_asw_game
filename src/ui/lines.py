"""Chart and plot line primitives with an optional anti-aliased path.

``ENABLED`` follows the ``aa_lines`` preference (set by
``layout.configure_for``).  Off, every call is the plain ``pygame.draw``
primitive it replaces; on, one-pixel lines and polygon edges go through
``pygame.gfxdraw`` (thicker lines keep the plain path, gfxdraw has no
width).  Display only; nothing here touches simulation state.
"""

import pygame
from pygame import gfxdraw

ENABLED = False


def _points(points) -> list:
    return [(int(round(x)), int(round(y))) for x, y in points]


def line(surface, color, start, end, width: int = 1) -> None:
    if ENABLED and width == 1:
        (x0, y0), (x1, y1) = _points((start, end))
        gfxdraw.line(surface, x0, y0, x1, y1, color)
        return
    pygame.draw.line(surface, color, start, end, width)


def lines(surface, color, closed: bool, points, width: int = 1) -> None:
    if ENABLED and width == 1 and len(points) >= 2:
        pts = _points(points)
        for (x0, y0), (x1, y1) in zip(pts, pts[1:] + (pts[:1] if closed else [])):
            gfxdraw.line(surface, x0, y0, x1, y1, color)
        return
    pygame.draw.lines(surface, color, closed, points, width)


def polygon(surface, color, points, width: int = 0) -> None:
    if ENABLED and width <= 1 and len(points) >= 3:
        pts = _points(points)
        if width == 0:
            gfxdraw.filled_polygon(surface, pts, color)
        gfxdraw.aapolygon(surface, pts, color)
        return
    pygame.draw.polygon(surface, color, points, width)
