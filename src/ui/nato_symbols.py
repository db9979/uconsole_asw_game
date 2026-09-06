"""Kleine APP-6-aehnliche Symbole fuer das gemeinsame Lagebild."""

import pygame


AFFILIATION_COLORS = {
    "UNKNOWN": (235, 205, 80),
    "FRIEND": (90, 170, 255),
    "NEUTRAL": (80, 210, 130),
    "HOSTILE": (245, 90, 80),
}

DOMAIN_LABELS = {
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
    return "SURFACE"


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
    else:
        # Unbekannt: stilisierter Vierpass statt fontabhaengigem APP-6-Glyph.
        frame = [(x - half, y), (x - half // 2, y - height),
                 (x + half // 2, y - height), (x + half, y),
                 (x + half // 2, y + height), (x - half // 2, y + height)]
        pygame.draw.polygon(surface, color, frame, 2)

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
    else:
        pygame.draw.line(surface, color, (x - 5, y + 2), (x + 5, y + 2), 2)
        pygame.draw.arc(surface, color, (x - 5, y - 3, 10, 7), 0, 3.14159, 1)

    if selected:
        pygame.draw.circle(surface, (235, 235, 220), (x, y), half + 7, 1)
    return color
