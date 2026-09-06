"""Procedural startup artwork for the uConsole release."""

import math

import pygame

from src.core import config
from src.core.i18n import localized
from src.core.version import SPLASH_TEXT
from src.ui import layout


@localized
def draw_splash(surface: pygame.Surface, elapsed_s: float,
                 duration_s: float = 4.5, tr=None) -> None:
    """Draw an original radar/sonar/ASW splash without external assets."""
    surface.fill((3, 10, 16))
    width, height = surface.get_size()
    horizon = int(height * .43)

    # Night sea and restrained phosphor grid.
    pygame.draw.rect(surface, (5, 20, 27), (0, horizon, width, height - horizon))
    for y in range(horizon, height, 34):
        pygame.draw.line(surface, (9, 41, 45), (0, y), (width, y), 1)
    for x in range(0, width, 64):
        pygame.draw.line(surface, (7, 31, 38), (x, horizon), (x, height), 1)

    # Generic frigate silhouette with mast and rotating radar antenna.
    hull = [(110, horizon - 8), (535, horizon - 8), (470, horizon + 56),
            (175, horizon + 56)]
    pygame.draw.polygon(surface, (20, 50, 58), hull)
    pygame.draw.lines(surface, (75, 205, 168), False, hull[:3], 2)
    pygame.draw.rect(surface, (17, 46, 53), (225, horizon - 64, 210, 56))
    pygame.draw.polygon(surface, (17, 46, 53),
                        [(280, horizon - 64), (330, horizon - 112),
                         (390, horizon - 64)])
    pygame.draw.line(surface, (80, 210, 170),
                     (336, horizon - 110), (336, horizon - 174), 3)
    sweep = elapsed_s * 2.4
    antenna_dx = int(math.cos(sweep) * 42)
    pygame.draw.line(surface, (130, 245, 188),
                     (336 - antenna_dx, horizon - 165),
                     (336 + antenna_dx, horizon - 165), 3)

    # Radar scope and sweep.
    center = (940, 225)
    radius = 145
    pygame.draw.circle(surface, (8, 28, 25), center, radius)
    for ring in (48, 96, 144):
        pygame.draw.circle(surface, (26, 94, 75), center, ring, 1)
    pygame.draw.line(surface, (26, 94, 75),
                     (center[0] - radius, center[1]),
                     (center[0] + radius, center[1]), 1)
    pygame.draw.line(surface, (26, 94, 75),
                     (center[0], center[1] - radius),
                     (center[0], center[1] + radius), 1)
    angle = elapsed_s * 1.7
    end = (int(center[0] + radius * math.sin(angle)),
           int(center[1] - radius * math.cos(angle)))
    pygame.draw.line(surface, (95, 238, 159), center, end, 2)
    pygame.draw.circle(surface, (180, 255, 190),
                       (center[0] + 62, center[1] - 37), 4)

    # Underwater submarine and expanding sonar arcs.
    sub_y = 535
    pygame.draw.ellipse(surface, (15, 43, 52), (520, sub_y, 290, 54))
    pygame.draw.polygon(surface, (15, 43, 52),
                        [(790, sub_y + 5), (860, sub_y + 27),
                         (790, sub_y + 49)])
    pygame.draw.rect(surface, (15, 43, 52), (635, sub_y - 29, 55, 34))
    pygame.draw.line(surface, (56, 167, 164), (520, sub_y + 27),
                     (810, sub_y + 27), 2)
    phase = (elapsed_s * 85.0) % 180.0
    for offset in (0, 58, 116):
        sonar_r = int(phase + offset)
        if sonar_r < 190:
            pygame.draw.arc(surface, (38, 123, 126),
                            (655 - sonar_r, sub_y + 27 - sonar_r,
                             sonar_r * 2, sonar_r * 2),
                            math.radians(195), math.radians(345), 2)

    # Fade only affects text; geometry stays visible during skip debounce.
    fade_in = min(1.0, elapsed_s / .8)
    fade_out = min(1.0, max(0.0, duration_s - elapsed_s) / .7)
    intensity = max(.15, min(fade_in, fade_out))
    title_color = tuple(int(c * intensity) for c in (145, 255, 198))
    layout.blit_line(surface, "U-JAGD / ASW", (70, 68, 650, 62),
                     title_color, size=42)
    layout.blit_line(surface, SPLASH_TEXT, (70, 640, width - 140, 34),
                     title_color, size=20, align="center")
    layout.blit_line(surface, "SONAR  •  RADAR  •  TAKTISCHE FÜHRUNG",
                     (70, 132, 650, 28), (70, 155, 138), size=16)
