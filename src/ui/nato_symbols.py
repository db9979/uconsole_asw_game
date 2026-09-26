"""Kleine APP-6-aehnliche Symbole fuer das gemeinsame Lagebild."""

import math

import pygame

from src.core import config


AFFILIATION_COLORS = {
    "UNKNOWN": (235, 205, 80),
    "FRIEND": (90, 170, 255),
    "NEUTRAL": (80, 210, 130),
    "HOSTILE": (245, 90, 80),
}

DOMAIN_LABELS = {
    "UNKNOWN": "Unbekannt",
    "SURFACE": "See",
    "SUBSURFACE": "Untersee",
    "AIR": "Luft",
    "MISSILE": "Flugkoerper",
    "UNDERWATER_WEAPON": "Unterwasserwaffe",
}


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

    if affiliation == "HOSTILE":
        frame = [(x, y - height), (x + half, y),
                 (x, y + height), (x - half, y)]
        pygame.draw.polygon(surface, color, frame, 2)
    elif affiliation == "NEUTRAL":
        pygame.draw.rect(surface, color,
                         (x - half, y - height, half * 2, height * 2), 2)
    elif affiliation == "FRIEND":
        pygame.draw.rect(surface, color,
                         (x - half - 2, y - height, half * 2 + 4, height * 2), 2)
    # Unknown affiliation: no frame, only the domain glyph (colour marks it).

    if domain == "AIR":
        pygame.draw.lines(surface, color, False,
                          [(x - 4, y + 3), (x, y - 3), (x + 4, y + 3)], 2)
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
        pygame.draw.circle(surface, (235, 235, 220), (x, y), half + 7, 1)
    return color


def draw_motion_vector(surface, center, course_deg, speed_kn, px_per_nm,
                        color, minutes=config.MOTION_VECTOR_WINDOW_MIN,
                        max_px=None, font=None):
    """Vektor von center in Kursrichtung, Laenge proportional zur in
    `minutes` zurueckgelegten Distanz. Ohne Speed nur ein kurzer Heading-Tick."""
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
    if font is not None and speed_kn is not None:
        surface.blit(font.render(f"{speed_kn:.0f}kn", True, color),
                     (int(end[0]) + 4, int(end[1]) - 6))
    return end
