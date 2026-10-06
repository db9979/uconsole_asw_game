"""The talk key on the uConsole: the KI button in the top bar and the bubble
with the spoken question and the executive officer's answer.

The button (shown while the language model is on) opens the executive
officer's page ready for a typed question; ``Shift+Space`` at any station
records a spoken one (``src/core/game_talk.py``).  The bubble sits over the
top of the station while the officer listens, thinks and answers, and goes
away by itself; its buttons send or repeat, open the chat, and its cross
closes it.  It never passes a click to the station underneath.  Display
only: nothing here touches the simulation.
"""

from __future__ import annotations

import pygame

from src.core import config, status_tips
from src.core.i18n import localize, localized, message, raw_text
from src.ui import game_menu, layout, llm_text, overlay_style, pointer, theme

BUTTON_W = 54
BUTTON_H = 20
GAP = 10
BUBBLE_W = 520
BUBBLE_X = (config.SCREEN_W - BUBBLE_W) // 2
BUBBLE_Y = config.TOP_BAR_H + 6
PAD = 12
TEXT_SIZE = 15
MAX_LINES = 6
BUTTON_ROW_H = 30


def button_rect(right: int) -> pygame.Rect:
    return pygame.Rect(right - BUTTON_W, (config.TOP_BAR_H - BUTTON_H) // 2,
                       BUTTON_W, BUTTON_H)


def _icon(s, box, color) -> None:
    """A speech bubble: rounded body and a tail."""
    body = pygame.Rect(box.x, box.y + 2, 14, 10)
    pygame.draw.rect(s, color, body, 2, border_radius=3)
    pygame.draw.polygon(s, color, ((body.x + 3, body.bottom - 1), (body.x + 3, body.bottom + 4),
                                   (body.x + 8, body.bottom - 1)))


def note(game) -> dict:
    return status_tips.note("talk.button.label", "", "talk.button.why", "talk.button.how",
                            keys=("Shift+Space", "F7"))


@localized
def draw_button(game, s, right: int) -> int:
    """Draw the KI button left of ``right`` (top bar); returns the status
    line's new right edge."""
    if not game.talk_shown():
        return right
    rect = button_rect(right)
    busy = game.talk_state != "idle"
    pygame.draw.rect(s, theme.c("select" if busy else "raised"), rect, border_radius=4)
    pygame.draw.rect(s, config.COLOR_WARN if game.talk_state == "recording"
                     else theme.c("line_strong"), rect, 1, border_radius=4)
    color = config.COLOR_WARN if game.talk_state == "recording" else config.COLOR_TEXT
    _icon(s, pygame.Rect(rect.x + 6, rect.y + 2, 16, rect.h - 4), color)
    layout.blit_line(s, "talk.button", pygame.Rect(rect.x + 24, rect.y + 1, rect.w - 28,
                                                   rect.h - 2),
                     color, size=14, align="center")
    pointer.add_action(rect, lambda _pos: game.open_talk_chat())
    pointer.add_tip(rect, lambda: status_tips.payload(note(game)))
    return rect.x - GAP


def header_line(game):
    state = game.talk_state
    if state == "recording":
        return message("talk.state.recording", seconds=f"{game.talk_recorded_s():.0f}"), \
            config.COLOR_WARN
    if state == "transcribing":
        return message("talk.state.transcribing"), config.COLOR_TEXT_DIM
    bubble = game.talk_bubble or {}
    if bubble.get("error"):
        return message("talk.state.failed", reason=message(
            "talk.error." + str(bubble["error"]))), config.COLOR_WARN
    entry = bubble.get("entry")
    if entry is not None and entry["status"] == "pending":
        return message("talk.state.asking"), config.COLOR_TEXT_DIM
    if entry is not None and entry["status"] == "failed":
        return llm_text.status_text(entry), config.COLOR_WARN
    return message("talk.state.answer"), config.COLOR_OK


def _body(game) -> list:
    """(text, color) rows under the header: the question, then the answer."""
    bubble = game.talk_bubble or {}
    rows = []
    if bubble.get("question"):
        rows.append((message("talk.you", text=raw_text(bubble["question"])),
                     config.COLOR_TEXT_DIM))
    entry = bubble.get("entry")
    if entry is not None and entry.get("answer"):
        rows.append((raw_text(entry["answer"]), config.COLOR_TEXT))
    return rows


def bubble_rect(lines: int) -> pygame.Rect:
    pitch = layout.line_pitch(TEXT_SIZE, 2)
    height = PAD + 22 + lines * pitch + (6 if lines else 0) + BUTTON_ROW_H + PAD
    return pygame.Rect(BUBBLE_X, BUBBLE_Y, BUBBLE_W, height)


def _wrapped(game) -> list:
    width = BUBBLE_W - 2 * PAD
    lines = []
    for text, color in _body(game):
        for line in llm_text.wrapped(localize(text), width, TEXT_SIZE):
            lines.append((line, color))
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES]
        last, color = lines[-1]
        lines[-1] = (layout.fit_line(last + " …", layout.font(TEXT_SIZE), width), color)
        lines.append((None, None))     # marker: the rest is in F7
    return lines


@localized
def draw_bubble(game, s) -> None:
    if not game.talk_bubble_shown() or game.input_mode is not None:
        return
    lines = _wrapped(game)
    more = bool(lines) and lines[-1][0] is None
    if more:
        lines = lines[:-1]
    panel = bubble_rect(len(lines))
    # Opaque: the station's own text never shows through the answer.
    pygame.draw.rect(s, config.COLOR_PANEL_BG, panel)
    overlay_style.panel(s, panel)
    pointer.add_blocker(panel)
    close = game_menu.close_rect(panel)
    game_menu.draw_close_box(s, panel)
    pointer.add_action(close, lambda _pos: game.close_talk_bubble())
    text, color = header_line(game)
    layout.blit_line(s, text, (panel.x + PAD, panel.y + PAD, close.x - panel.x - 2 * PAD, 22),
                     color, size=16)
    if game.talk_state == "recording":
        _meter(s, pygame.Rect(panel.x + PAD, panel.y + PAD + 22, panel.w - 2 * PAD - 40, 4),
               game.talk_level())
    pitch = layout.line_pitch(TEXT_SIZE, 2)
    y = panel.y + PAD + 28
    for line, line_color in lines:
        layout.blit_line(s, raw_text(line), (panel.x + PAD, y, panel.w - 2 * PAD, pitch),
                         line_color, size=TEXT_SIZE)
        y += pitch
    row = pygame.Rect(panel.x + PAD, panel.bottom - PAD - BUTTON_ROW_H + 4,
                      panel.w - 2 * PAD, BUTTON_ROW_H - 4)
    half = (row.w - 10) // 2
    talk = pygame.Rect(row.x, row.y, half, row.h)
    chat = pygame.Rect(talk.right + 10, row.y, row.w - half - 10, row.h)
    label = ("talk.button.send" if game.talk_state == "recording"
             else "talk.button.speak")
    layout.key_button(s, talk, "Shift+Space", label, size=14)
    pointer.add_action(talk, lambda _pos: game.talk_toggle())
    layout.key_button(s, chat, "F7", "talk.button.more" if more else "talk.button.chat",
                      size=14)
    pointer.add_action(chat, lambda _pos: game.open_talk_chat())


def _meter(s, rect, level: int) -> None:
    from src.audio.microphone import LEVEL_MAX
    pygame.draw.rect(s, theme.c("well"), rect)
    filled = rect.w * max(0, min(LEVEL_MAX, level)) // LEVEL_MAX
    if filled:
        pygame.draw.rect(s, config.COLOR_WARN, (rect.x, rect.y, filled, rect.h))
