"""Chart and plot line primitives with an optional anti-aliased path.

``ENABLED`` follows the ``aa_lines`` preference (set by
``layout.configure_for``).  Off, every call is the plain ``pygame.draw``
primitive it replaces; on, one-pixel lines and polygon edges go through
``pygame.gfxdraw`` (thicker lines keep the plain path, gfxdraw has no
width).  Display only; nothing here touches simulation state.

gfxdraw takes signed 16-bit coordinates, so a strongly zoomed chart
(1400 px/NM puts distant waypoints hundreds of thousands of pixels away)
would overflow it.  Segments and polygons are therefore clipped to the
surface's clip rect (grown by a small margin) before they reach gfxdraw.
"""

import pygame
from pygame import gfxdraw

ENABLED = False

# Margin around the clip rect: far outside points are cut back to it, so
# every coordinate handed to gfxdraw stays well inside 16 bits.
CLIP_MARGIN_PX = 8.0


def _points(points) -> list:
    return [(int(round(x)), int(round(y))) for x, y in points]


def _bounds(surface) -> tuple:
    clip = surface.get_clip()
    m = CLIP_MARGIN_PX
    return clip.x - m, clip.y - m, clip.right + m, clip.bottom + m


def clip_segment(start, end, bounds):
    """Liang-Barsky: the part of start-end inside ``bounds`` (left, top,
    right, bottom), or None when the segment misses it."""
    (x0, y0), (x1, y1) = start, end
    left, top, right, bottom = bounds
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - left), (dx, right - x0), (-dy, y0 - top), (dy, bottom - y0)):
        if p == 0:
            if q < 0:
                return None
            continue
        t = q / p
        if p < 0:
            if t > t1:
                return None
            t0 = max(t0, t)
        else:
            if t < t0:
                return None
            t1 = min(t1, t)
    return (x0 + t0 * dx, y0 + t0 * dy), (x0 + t1 * dx, y0 + t1 * dy)


def clip_polygon(points, bounds) -> list:
    """Sutherland-Hodgman: ``points`` cut to ``bounds`` (left, top, right,
    bottom).  A polygon already inside is returned unchanged."""
    left, top, right, bottom = bounds
    pts = list(points)
    if all(left <= x <= right and top <= y <= bottom for x, y in pts):
        return pts
    for edge in range(4):
        if not pts:
            break
        out = []
        prev = pts[-1]
        for cur in pts:
            inside_cur = _inside(cur, edge, bounds)
            inside_prev = _inside(prev, edge, bounds)
            if inside_cur:
                if not inside_prev:
                    out.append(_cross(prev, cur, edge, bounds))
                out.append(cur)
            elif inside_prev:
                out.append(_cross(prev, cur, edge, bounds))
            prev = cur
        pts = out
    return pts


def _inside(point, edge, bounds) -> bool:
    x, y = point
    left, top, right, bottom = bounds
    return (x >= left, y >= top, x <= right, y <= bottom)[edge]


def _cross(a, b, edge, bounds):
    (x0, y0), (x1, y1) = a, b
    left, top, right, bottom = bounds
    if edge in (0, 2):
        bound = left if edge == 0 else right
        t = (bound - x0) / (x1 - x0)
        return bound, y0 + (y1 - y0) * t
    bound = top if edge == 1 else bottom
    t = (bound - y0) / (y1 - y0)
    return x0 + (x1 - x0) * t, bound


def _aa_segment(surface, color, start, end, bounds) -> None:
    seg = clip_segment(start, end, bounds)
    if seg is not None:
        (x0, y0), (x1, y1) = _points(seg)
        gfxdraw.line(surface, x0, y0, x1, y1, color)


def line(surface, color, start, end, width: int = 1) -> None:
    if ENABLED and width == 1:
        _aa_segment(surface, color, start, end, _bounds(surface))
        return
    pygame.draw.line(surface, color, start, end, width)


def lines(surface, color, closed: bool, points, width: int = 1) -> None:
    if ENABLED and width == 1 and len(points) >= 2:
        pts = list(points)
        bounds = _bounds(surface)
        for start, end in zip(pts, pts[1:] + (pts[:1] if closed else [])):
            _aa_segment(surface, color, start, end, bounds)
        return
    pygame.draw.lines(surface, color, closed, points, width)


def polygon(surface, color, points, width: int = 0) -> None:
    if ENABLED and width <= 1 and len(points) >= 3:
        pts = clip_polygon(points, _bounds(surface))
        if len(pts) < 3:
            return
        pts = _points(pts)
        if width == 0:
            gfxdraw.filled_polygon(surface, pts, color)
        gfxdraw.aapolygon(surface, pts, color)
        return
    pygame.draw.polygon(surface, color, points, width)
