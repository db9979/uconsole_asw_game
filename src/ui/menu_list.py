"""Scrolling lists of the start menu (display only).

A menu list shows at most ``rows`` entries at once; the window follows the
selection, so Up/Down, PgUp/PgDn, the mouse wheel and the number keys reach
every entry however long the list grows. A slim scroll bar with arrow marks
at the panel's right edge shows that more entries lie above or below.
"""

from __future__ import annotations

import pygame

# Scroll bar colours of the menu panel (``splash_view.draw_menu_panel``).
TRACK_COLOR = (24, 64, 60)
THUMB_COLOR = (98, 180, 164)
ARROW_COLOR = (150, 240, 205)


def first_row(count: int, selected: int, rows: int) -> int:
    """Index of the first visible entry: the selection stays in view,
    near the middle once the list is longer than the window."""
    if rows <= 0 or count <= rows:
        return 0
    selected = max(0, min(count - 1, int(selected)))
    return max(0, min(selected - rows // 2, count - rows))


def page_step(count: int, selected: int, rows: int, direction: int) -> int:
    """Selection after PgUp (``direction`` -1) or PgDn (+1): one window on,
    clamped at the list's ends (no wrap)."""
    if count <= 0:
        return 0
    return max(0, min(count - 1, int(selected) + direction * max(1, rows - 1)))


def draw_scrollbar(surface, rect, first: int, rows: int, count: int) -> None:
    """Track, thumb and arrow marks inside ``rect`` (nothing when all fit)."""
    if count <= rows or rows <= 0:
        return
    rect = pygame.Rect(rect)
    arrow = 8
    track = pygame.Rect(rect.x, rect.y + arrow + 4, rect.w,
                        max(1, rect.h - 2 * (arrow + 4)))
    pygame.draw.rect(surface, TRACK_COLOR, track, border_radius=2)
    thumb_h = max(12, round(track.h * rows / count))
    span = track.h - thumb_h
    top = track.y + round(span * first / max(1, count - rows))
    pygame.draw.rect(surface, THUMB_COLOR, (track.x, top, track.w, thumb_h),
                     border_radius=2)
    cx = rect.centerx
    up = ARROW_COLOR if first > 0 else TRACK_COLOR
    down = ARROW_COLOR if first + rows < count else TRACK_COLOR
    pygame.draw.polygon(surface, up, ((cx, rect.y), (cx - arrow // 2 - 2, rect.y + arrow),
                                      (cx + arrow // 2 + 2, rect.y + arrow)))
    pygame.draw.polygon(surface, down, ((cx, rect.bottom), (cx - arrow // 2 - 2,
                                                            rect.bottom - arrow),
                                        (cx + arrow // 2 + 2, rect.bottom - arrow)))
