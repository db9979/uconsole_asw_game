#!/usr/bin/env python3
"""Small start window shown by the uConsole launcher while it updates.

Run with the game's venv Python (it needs Pygame).  The launcher writes one
status per line to stdin:

``status<TAB>text``     show ``text``
``close<TAB>seconds``   close after that many seconds, even after end of file

Otherwise the window closes when stdin reaches end of file.  The launcher hands the write
end on to the game, which closes it after its first frame (``U_JAGD_SPLASH_FD``),
so this window stays until the game is actually visible, and also closes if the
game crashes on start.
"""

from __future__ import annotations

import math
import os
import select
import sys
import time

os.environ.setdefault("SDL_VIDEO_CENTERED", "1")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

WIDTH, HEIGHT = 520, 150
MAX_LIFETIME_S = 20 * 60
BG = (8, 26, 38)
FG = (214, 226, 232)
DIM = (120, 150, 165)
ACCENT = (111, 211, 160)


def read_lines(fd: int, buffer: bytearray) -> tuple[list[str], bool]:
    """Complete lines available on fd without blocking, and whether EOF came."""
    lines: list[str] = []
    eof = False
    while select.select([fd], [], [], 0)[0]:
        chunk = os.read(fd, 4096)
        if not chunk:
            eof = True
            break
        buffer.extend(chunk)
    while b"\n" in buffer:
        line, _, rest = bytes(buffer).partition(b"\n")
        buffer[:] = rest
        lines.append(line.decode("utf-8", "replace"))
    return lines, eof


def main() -> int:
    try:
        import pygame
    except ImportError:
        return 0
    pygame.display.init()
    pygame.font.init()
    try:
        screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.NOFRAME)
    except pygame.error:
        return 0
    pygame.display.set_caption("U-Jagd Start")
    title_font = pygame.font.Font(None, 44)
    text_font = pygame.font.Font(None, 28)
    title = title_font.render("U-Jagd", True, FG)
    status = ""
    close_at = None
    started = time.monotonic()
    buffer = bytearray()
    fd = sys.stdin.fileno()
    clock = pygame.time.Clock()
    while True:
        if fd is not None:
            lines, eof = read_lines(fd, buffer)
            if eof:
                fd = None  # a pending "close" still shows its message first
        else:
            lines, eof = [], True
        for line in lines:
            kind, _, value = line.partition("\t")
            if kind == "status":
                status = value[:80]
            elif kind == "close":
                try:
                    close_at = time.monotonic() + max(0.0, min(30.0, float(value)))
                except ValueError:
                    close_at = time.monotonic()
        now = time.monotonic()
        if (eof and close_at is None) or (close_at is not None and now >= close_at) \
                or now - started > MAX_LIFETIME_S:
            break
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                close_at = now
        screen.fill(BG)
        pygame.draw.rect(screen, DIM, screen.get_rect(), 1)
        screen.blit(title, (24, 22))
        # A sonar sweep so the window visibly works while git/pip block.
        cx, cy, r = WIDTH - 70, HEIGHT // 2, 44
        pygame.draw.circle(screen, DIM, (cx, cy), r, 1)
        pygame.draw.circle(screen, DIM, (cx, cy), r // 2, 1)
        angle = (now - started) * 2.2
        pygame.draw.line(screen, ACCENT, (cx, cy),
                         (cx + r * math.sin(angle), cy - r * math.cos(angle)), 2)
        screen.blit(text_font.render(status, True, FG), (24, 80))
        pygame.display.flip()
        clock.tick(20)
    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
