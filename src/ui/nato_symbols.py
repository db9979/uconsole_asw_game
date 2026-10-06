"""Kleine APP-6-aehnliche Symbole fuer das gemeinsame Lagebild."""

import math

import pygame

from src.core import config
from src.ui import label_layout, layout


# Reassigned with the colour theme (src/ui/theme.THEMED_GLOBALS).
AFFILIATION_COLORS = {
    "UNKNOWN": (251, 191, 36),
    "FRIEND": (96, 165, 250),
    "NEUTRAL": (52, 211, 153),
    "HOSTILE": (248, 113, 113),
}
SELECT_RING = (235, 235, 220)

# APP-6 frame dimension of each glyph domain: surface (full frame), air
# (upper half, open below) or subsurface (lower half, open above).
FRAME_DIMENSION = {"AIR": "air", "ROTARY": "air", "MISSILE": "air",
                   "SUBSURFACE": "subsurface", "UNDERWATER_WEAPON": "subsurface"}


def domain_for_kind(kind: str) -> str:
    kind = kind.upper()
    if kind == "FLG":
        return "AIR"
    if kind == "ASM":
        return "MISSILE"
    if kind == "SUB":
        return "SUBSURFACE"
    if kind == "TORP":
        return "UNDERWATER_WEAPON"
    return "SURFACE" if kind in ("AIS", "SURFACE") else "UNKNOWN"


def draw_symbol(surface, center, affiliation: str, domain: str,
                size: int = 16, selected: bool = False) -> tuple:
    """Zeichne NATO-Rahmen plus Domaenenzeichen; liefere die verwendete Farbe."""
    x, y = int(center[0]), int(center[1])
    half = max(5, int(size) // 2)
    height = max(6, int(size * 0.65))
    color = AFFILIATION_COLORS.get(affiliation, AFFILIATION_COLORS["UNKNOWN"])

    _draw_frame(surface, (x, y), affiliation, FRAME_DIMENSION.get(domain, "surface"),
                half, height, color)

    if domain == "AIR":
        pygame.draw.lines(surface, color, False,
                          [(x - 4, y + 3), (x, y - 3), (x + 4, y + 3)], 2)
    elif domain == "ROTARY":
        # Rotary wing (APP-6 / MIL-STD-2525 helicopter icon): a bow tie of
        # two rotor blades meeting at the hub.
        g = max(4, half - 2)
        pygame.draw.polygon(surface, color, [(x - g, y - g // 2), (x, y), (x - g, y + g // 2)], 2)
        pygame.draw.polygon(surface, color, [(x + g, y - g // 2), (x, y), (x + g, y + g // 2)], 2)
    elif domain == "MISSILE":
        pygame.draw.line(surface, color, (x, y + 4), (x, y - 4), 2)
        pygame.draw.lines(surface, color, False,
                          [(x - 3, y - 1), (x, y - 4), (x + 3, y - 1)], 2)
    elif domain == "SUBSURFACE":
        # Keel and conning tower: distinct from the surface-domain wave.
        pygame.draw.arc(surface, color, (x - 6, y - 2, 12, 7), 3.14159, 6.28318, 2)
        pygame.draw.line(surface, color, (x - 2, y + 1), (x - 2, y - 2), 2)
        pygame.draw.line(surface, color, (x - 2, y - 2), (x + 2, y - 2), 2)
    elif domain == "UNDERWATER_WEAPON":
        # Horizontal weapon body with nose and contra-rotating tail marks.
        pygame.draw.line(surface, color, (x - 5, y), (x + 4, y), 2)
        pygame.draw.lines(surface, color, False,
                          [(x + 2, y - 2), (x + 5, y), (x + 2, y + 2)], 2)
        pygame.draw.line(surface, color, (x - 5, y), (x - 2, y - 3), 1)
        pygame.draw.line(surface, color, (x - 5, y), (x - 2, y + 3), 1)
    elif domain == "SURFACE":
        pygame.draw.line(surface, color, (x - 5, y + 2), (x + 5, y + 2), 2)
        pygame.draw.arc(surface, color, (x - 5, y - 3, 10, 7), 0, 3.14159, 1)
    else:
        pygame.draw.circle(surface, color, (x, y), 2, 1)

    if selected:
        pygame.draw.circle(surface, SELECT_RING, (x, y), half + 7, 1)
    return color


def _draw_frame(surface, center, affiliation: str, dimension: str, half: int,
                height: int, color) -> None:
    """The APP-6 frame of an affiliation in its dimension: friend circle
    (air dome, subsurface bowl), hostile diamond, neutral square, each cut
    to its upper (air) or lower (subsurface) half; unknown: no frame (the
    colour marks it, keeps crowded charts readable)."""
    x, y = center
    if affiliation == "FRIEND":
        radius = half + 2
        box = (x - radius, y - radius, radius * 2, radius * 2)
        if dimension == "air":
            pygame.draw.arc(surface, color, box, 0.0, math.pi, 2)
        elif dimension == "subsurface":
            pygame.draw.arc(surface, color, box, math.pi, 2 * math.pi, 2)
        else:
            pygame.draw.circle(surface, color, (x, y), radius, 2)
    elif affiliation == "HOSTILE":
        if dimension == "air":
            pygame.draw.lines(surface, color, False,
                              [(x - half, y + 2), (x, y - height), (x + half, y + 2)], 2)
        elif dimension == "subsurface":
            pygame.draw.lines(surface, color, False,
                              [(x - half, y - 2), (x, y + height), (x + half, y - 2)], 2)
        else:
            pygame.draw.polygon(surface, color, [(x, y - height), (x + half, y),
                                                 (x, y + height), (x - half, y)], 2)
    elif affiliation == "NEUTRAL":
        if dimension == "air":
            pygame.draw.lines(surface, color, False,
                              [(x - half, y + 3), (x - half, y - height),
                               (x + half, y - height), (x + half, y + 3)], 2)
        elif dimension == "subsurface":
            pygame.draw.lines(surface, color, False,
                              [(x - half, y - 3), (x - half, y + height),
                               (x + half, y + height), (x + half, y - 3)], 2)
        else:
            pygame.draw.rect(surface, color,
                             (x - half, y - height, half * 2, height * 2), 2)


def draw_own_ship(surface, center, heading_deg, size: int = 18, color=None) -> tuple:
    """The own frigate on every chart: the APP-6 friendly surface frame
    (circle) with its heading line from the frame's rim."""
    color = color or AFFILIATION_COLORS["FRIEND"]
    draw_symbol(surface, center, "FRIEND", "SURFACE", size)
    draw_heading(surface, center, heading_deg, size, color)
    return color


def draw_heading(surface, center, heading_deg, size: int, color, length: int | None = None):
    """A heading staff from the frame's rim along ``heading_deg``."""
    if heading_deg is None:
        return
    ang = math.radians(heading_deg)
    rim = max(5, int(size) // 2) + 2
    length = length if length is not None else rim + 12
    x, y = center
    start = (x + rim * math.sin(ang), y - rim * math.cos(ang))
    end = (x + length * math.sin(ang), y - length * math.cos(ang))
    pygame.draw.line(surface, color, start, end, 2)


def draw_motion_vector(surface, center, course_deg, speed_kn, px_per_nm,
                        color, minutes=config.MOTION_VECTOR_WINDOW_MIN,
                        max_px=None, font=None, key=None):
    """Vektor von center in Kursrichtung, Laenge proportional zur in
    `minutes` zurueckgelegten Distanz. Ohne Speed nur ein kurzer Heading-Tick.
    In a chart's label scope the line keeps later labels off it."""
    if course_deg is None:
        return None
    ang = math.radians(course_deg)
    if speed_kn is not None:
        length = speed_kn * (minutes / 60.0) * px_per_nm
        if max_px is not None:
            length = min(length, max_px)
    else:
        length = 10.0  # Kurs bekannt, Speed noch nicht aufgeloest
    end = (center[0] + length * math.sin(ang), center[1] - length * math.cos(ang))
    pygame.draw.line(surface, color, center, end, 2)
    label_layout.reserve_segment(center, end)
    if font is not None and speed_kn is not None:
        text = f"{speed_kn:.0f}kn"
        clip = surface.get_clip()

        def draw_speed() -> None:
            image = font.render(text, True, color)
            # Past the vector tip, on the far side from its own line, never
            # across another label or off the chart.
            width, height = image.get_size()
            ux, uy = math.sin(ang), -math.cos(ang)
            x = end[0] + 4 if ux >= -0.2 else end[0] - 4 - width
            y = end[1] - height / 2 + uy * (height / 2 + 2)
            pos = (int(x), int(y))
            rect = label_layout.free_rect(
                (width, height), label_layout.around(pos, (width, height), 4),
                clip, key)
            layout.record_text(text, rect, clip, image)
            surface.blit(image, rect)

        label_layout.later(draw_speed)
    return end
