"""uConsole pages of the optional language model: the executive officer
(``F7``) and the model's settings (options page 2)."""

from __future__ import annotations

import pygame

from src.core import config
from src.core.i18n import localize, localized, message, raw_text
from src.llm import keystore
from src.ui import layout, llm_text, overlay_style

PANEL = pygame.Rect(140, 30, 1000, 660)
TABS_Y = 88
FIELD = pygame.Rect(172, 600, 936, 34)
LOG = pygame.Rect(172, 130, 936, 456)
SETTINGS_ROW_Y = 120
SETTINGS_PITCH = 62


def tab_rects(count: int) -> tuple:
    width = (PANEL.w - 64) // count
    return tuple(pygame.Rect(PANEL.x + 32 + index * width, TABS_Y, width - 8, 32)
                 for index in range(count))


def _entry_lines(game, entry) -> list:
    """(text, color) rows of one log entry."""
    rows = []
    kind = message("advisor.mode." + entry["kind"])
    head = message("advisor.asked", kind=kind) if not entry["question"] else message(
        "advisor.asked_text", kind=kind, text=raw_text(entry["question"]))
    rows.append((head, config.COLOR_TEXT_DIM))
    state = llm_text.status_text(entry) if entry["status"] != "done" else None
    if state is not None:
        rows.append((state, config.COLOR_WARN))
        if entry["answer"]:
            rows.append((raw_text(entry["answer"]), config.COLOR_TEXT))
        return rows
    if entry["answer"]:
        rows.append((raw_text(entry["answer"]), config.COLOR_TEXT))
    if entry["proposal"]:
        for command in entry["proposal"]:
            rows.append((message("advisor.command." + command["type"],
                                 value=_value(command["value"])), config.COLOR_OK))
        if entry["applied"]:
            rows.append((message("advisor.order_applied"), config.COLOR_OK))
        elif entry.get("discarded"):
            rows.append((message("advisor.order_discarded"), config.COLOR_TEXT_DIM))
        else:
            rows.append((message("advisor.order_confirm"), config.COLOR_WARN))
    return rows


def _value(value):
    if value is True:
        return message("common.on")
    if value is False:
        return message("common.off")
    return raw_text(f"{value:g}")


@localized
def draw_advisor_overlay(game) -> None:
    s = game.screen
    overlay_style.panel(s, PANEL)
    overlay_style.title(s, "advisor.title", (PANEL.x + 32, PANEL.y + 12, PANEL.w - 64, 40),
                        size=28)
    for index, rect in enumerate(tab_rects(5)):
        active = index == game.advisor_mode
        if active:
            overlay_style.highlight(s, rect)
        pygame.draw.rect(s, config.COLOR_TEXT_DIM, rect, 1)
        layout.blit_line(s, message("advisor.tab", number=index + 1, mode=message(
            "advisor.mode." + ("situation", "question", "order", "classify",
                               "briefing")[index])),
                         rect.inflate(-6, -4), overlay_style.text_color(active),
                         size=16, align="center")
    if not game.llm_active():
        layout.blit_block(s, "advisor.off", LOG.x, LOG.y, LOG.w, 120,
                          color=config.COLOR_TEXT_DIM, size=18)
        _footer(s, "advisor.keys_off")
        return
    # The log: newest at the bottom, scrolled with Up/Down.
    rows = []
    for entry in game.advisor.log("local"):
        rows.extend(_entry_lines(game, entry))
        rows.append((None, None))
    lines = []
    width = LOG.w - 8
    for text, color in rows:
        if text is None:
            lines.append(("", color))
            continue
        for line in llm_text.wrapped(localize(text), width, 15):
            lines.append((line, color))
    pitch = layout.line_pitch(15, 2)
    visible = max(1, LOG.h // pitch)
    top = max(0, len(lines) - visible)
    if game.advisor_scroll is not None:
        top = min(top, game.advisor_scroll)
    pygame.draw.rect(s, config.COLOR_PANEL_BG, LOG.inflate(8, 8))
    if not lines:
        layout.blit_block(s, "advisor.mode_help." + game.advisor_mode_name(), LOG.x, LOG.y,
                          LOG.w, 120, color=config.COLOR_TEXT_DIM, size=16)
    with layout.clip_to(s, LOG):
        for index, (line, color) in enumerate(lines[top:top + visible]):
            if line:
                layout.blit_line(s, raw_text(line), (LOG.x, LOG.y + index * pitch, LOG.w, pitch),
                                 color, size=15)
    mode = game.advisor_mode_name()
    if game.advisor_open_proposal() is not None:
        layout.blit_line(s, "advisor.confirm_hint", FIELD, config.COLOR_WARN, size=17)
    elif mode in ("question", "order"):
        game.advisor_field.draw(s, FIELD, focused=True)
    else:
        layout.blit_line(s, "advisor.send_hint." + mode, FIELD, config.COLOR_TEXT_DIM, size=17)
    _footer(s, "advisor.keys")


def _footer(s, key) -> None:
    layout.blit_block(s, key, PANEL.x + 32, PANEL.bottom - 46, PANEL.w - 64, 40,
                      color=config.COLOR_TEXT_DIM, size=14, align="center")


def settings_row_rects() -> tuple:
    return tuple(pygame.Rect(PANEL.x + 60, SETTINGS_ROW_Y + index * SETTINGS_PITCH,
                             PANEL.w - 120, 54) for index in range(8))


@localized
def draw_llm_settings(game) -> None:
    s = game.screen
    prefs = game.preferences
    overlay_style.panel(s, PANEL)
    overlay_style.title(s, "llm.title", (PANEL.x + 32, PANEL.y + 12, PANEL.w - 64, 40), size=28)
    layout.blit_line(s, "llm.subtitle", (PANEL.x + 32, PANEL.y + 56, PANEL.w - 64, 24),
                     config.COLOR_TEXT_DIM, size=15, align="center")
    from src.core.game_advisor import LLM_ROWS

    def on_off(value):
        return message("common.on" if value else "common.off")

    key = keystore.load_key()
    values = {
        "llm_enabled": on_off(prefs.llm_enabled),
        "llm_url": raw_text(prefs.llm_url),
        "llm_model": raw_text(prefs.llm_model),
        "llm_key": message("llm.key_env") if keystore.key_from_env()
        else raw_text(keystore.mask(key)),
        "llm_radio": on_off(prefs.llm_radio),
        "llm_coach": message("llm.coach." + prefs.llm_coach),
        "llm_opfor": on_off(prefs.llm_opfor),
        "test": _test_text(game),
    }
    for index, (name, rect) in enumerate(zip(LLM_ROWS, settings_row_rects())):
        selected = index == game.llm_sel
        if selected:
            overlay_style.highlight(s, (rect.x - 6, rect.y - 4, rect.w + 12, 30))
        color = overlay_style.text_color(selected)
        layout.blit_line(s, message("llm.row", label=message("llm.label." + name),
                                    value=values[name]),
                         (rect.x, rect.y, rect.w, 24), color, size=18)
        if game.llm_field is not None and game.llm_field_name == name:
            game.llm_field.draw(s, pygame.Rect(rect.x, rect.y + 26, rect.w, 28), focused=True)
        else:
            layout.blit_line(s, "llm.help." + name, (rect.x + 16, rect.y + 26, rect.w - 16, 22),
                             config.COLOR_TEXT_DIM, size=14)
    _footer(s, "llm.keys")


def _test_text(game):
    state = game.llm_test_state()
    if state is None:
        return message("llm.test.idle")
    if state["status"] == "pending":
        return message("llm.state.pending")
    if state["status"] == "done":
        return message("llm.test.ok", seconds=f"{state['latency_s']:.1f}")
    return llm_text.status_text(state)
