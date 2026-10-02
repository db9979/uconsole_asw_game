"""Drawing of the language model's texts: report, review and advisor answers.

Plain wrapped text in a bounded rect with a scroll offset; the waiting,
failed and switched-off states say so in the player's language.
"""

from __future__ import annotations

import pygame

from src.core import config
from src.core.i18n import message, raw_text
from src.ui import layout

ERROR_KEYS = ("disabled", "bad_url", "network", "timeout", "auth", "rate_limit",
              "server", "bad_reply", "thinking", "busy")


def status_text(state):
    """One line for a job's state, or None when its text is ready."""
    if state is None:
        return message("llm.state.off")
    if state.get("status") == "pending":
        return message("llm.state.pending")
    if state.get("status") == "failed":
        error = state.get("error")
        return message("llm.state.failed", reason=message(
            "llm.error." + (error if error in ERROR_KEYS else "network")))
    return None


def wrapped(text: str, width: int, size: int) -> list:
    return layout.wrap_text(text, layout.font(size), width)


def draw_text(s, rect, text: str, scroll: int = 0, *, size: int = 15,
              color=config.COLOR_TEXT) -> int:
    """Draw wrapped ``text`` from line ``scroll``; returns the line count."""
    rect = pygame.Rect(rect)
    lines = wrapped(text, rect.w, size)
    pitch = layout.line_pitch(size, 2)
    visible = max(1, rect.h // pitch)
    start = max(0, min(scroll, max(0, len(lines) - visible)))
    with layout.clip_to(s, rect):
        for index, line in enumerate(lines[start:start + visible]):
            layout.blit_line(s, raw_text(line), (rect.x, rect.y + index * pitch, rect.w, pitch),
                             color, size=size)
    if len(lines) > visible:
        layout.blit_line(s, message("llm.scroll", line=start + 1, lines=len(lines)),
                         (rect.x, rect.bottom - pitch, rect.w, pitch), config.COLOR_TEXT_DIM,
                         size=12, align="right")
    return len(lines)


def draw_state(s, rect, state, *, size: int = 15) -> None:
    """The text of a finished job, or its status line."""
    line = status_text(state)
    if line is not None:
        layout.blit_block(s, line, rect[0], rect[1], rect[2], rect[3],
                          color=config.COLOR_TEXT_DIM, size=size)
        return
    draw_text(s, rect, state.get("text", ""), state.get("scroll", 0), size=size)
