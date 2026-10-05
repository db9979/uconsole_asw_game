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
    if entry["status"] == "pending":
        state = message("advisor.pending")
    else:
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


TAB_W = 170


def page_tab_rects() -> tuple:
    """The settings' page tabs (language model; voice, how it sounds)
    left and right of the title."""
    right = PANEL.right - 24 - 48
    return (pygame.Rect(PANEL.x + 24, PANEL.y + 14, TAB_W, 34),
            pygame.Rect(right - 2 * TAB_W - 8, PANEL.y + 14, TAB_W, 34),
            pygame.Rect(right - TAB_W, PANEL.y + 14, TAB_W, 34))


def _title_rect() -> pygame.Rect:
    tabs = page_tab_rects()
    return pygame.Rect(tabs[0].right + 8, PANEL.y + 12, tabs[1].x - tabs[0].right - 16, 40)


def _on_off(value):
    return message("common.on" if value else "common.off")


def _llm_values(game) -> dict:
    prefs = game.preferences
    # The configured key (read when it was set), never the key file per frame.
    key = game.llm.config.api_key
    return {
        "llm_enabled": _on_off(prefs.llm_enabled),
        "llm_url": raw_text(prefs.llm_url),
        "llm_model": raw_text(prefs.llm_model),
        "llm_key": message("llm.key_env") if keystore.key_from_env()
        else raw_text(keystore.mask(key)),
        "llm_radio": _on_off(prefs.llm_radio),
        "llm_coach": message("llm.coach." + prefs.llm_coach),
        "llm_opfor": _on_off(prefs.llm_opfor),
        "test": _test_text(game),
    }


def _voice_values(game) -> dict:
    prefs = game.preferences
    source = game.voice_key_source()
    key = game.voice.config.api_key
    return {
        "tts_enabled": _on_off(prefs.tts_enabled),
        "tts_url": raw_text(prefs.tts_url),
        "tts_model": raw_text(prefs.tts_model),
        "tts_voice": raw_text(prefs.tts_voice),
        "tts_key": message("voice.key_env") if source == "env"
        else message("voice.key_shared", masked=raw_text(keystore.mask(key)))
        if source == "shared" else raw_text(keystore.mask(key)),
        "tts_xo": _on_off(prefs.tts_xo),
        "tts_crew": _on_off(prefs.tts_crew),
        "tts_test": _voice_test_text(game),
        "tts_temperature": raw_text(f"{prefs.tts_temperature:.2f}"),
        "tts_top_p": raw_text(f"{prefs.tts_top_p:.2f}"),
        "tts_seed": message("voice.seed_random") if prefs.tts_seed < 0
        else raw_text(str(prefs.tts_seed)),
        "tts_clean": _on_off(prefs.tts_clean),
    }


@localized
def draw_llm_settings(game) -> None:
    from src.core.game_advisor import LLM_PAGES
    from src.ui import game_menu, pointer

    s = game.screen
    page = game.llm_page % len(LLM_PAGES)
    overlay_style.panel(s, PANEL)
    overlay_style.title(s, ("llm.title", "voice.title", "voice.tune_title")[page],
                        _title_rect(), size=26)
    game_menu.close_button(s, PANEL)
    for index, rect in enumerate(page_tab_rects()):
        active = index == page
        if active:
            overlay_style.highlight(s, rect)
        pygame.draw.rect(s, config.COLOR_TEXT_DIM, rect, 1)
        layout.blit_line(s, message("llm.page", number=index + 1,
                                    name=message(("llm.page.model", "llm.page.voice",
                                                  "llm.page.tune")[index])),
                         rect.inflate(-8, -4), overlay_style.text_color(active),
                         size=16, align="center")
        pointer.add_action(rect, lambda _pos, index=index: game.set_llm_page(index))
    layout.blit_line(s, ("llm.subtitle", "voice.subtitle", "voice.tune_subtitle")[page],
                     (PANEL.x + 32, PANEL.y + 56, PANEL.w - 64, 24),
                     config.COLOR_TEXT_DIM, size=15, align="center")
    rows = LLM_PAGES[page]
    values = _llm_values(game) if page == 0 else _voice_values(game)
    prefix = "llm" if page == 0 else "voice"
    for index, (name, rect) in enumerate(zip(rows, settings_row_rects())):
        selected = index == game.llm_sel
        if selected:
            overlay_style.highlight(s, (rect.x - 6, rect.y - 4, rect.w + 12, 30))
        color = overlay_style.text_color(selected)
        layout.blit_line(s, message("llm.row", label=message(f"{prefix}.label." + name),
                                    value=values[name]),
                         (rect.x, rect.y, rect.w, 24), color, size=18)
        if game.llm_field is not None and game.llm_field_name == name:
            game.llm_field.draw(s, pygame.Rect(rect.x, rect.y + 26, rect.w, 28), focused=True)
        else:
            layout.blit_line(s, f"{prefix}.help." + name,
                             (rect.x + 16, rect.y + 26, rect.w - 16, 22),
                             config.COLOR_TEXT_DIM, size=14)
            pointer.add_action(rect, lambda _pos, index=index: game.click_llm_row(index))
    _footer(s, "llm.keys")


def _voice_test_text(game):
    state = game.voice_test_state()
    if state is None:
        return message("voice.test.idle")
    if state["status"] == "pending":
        return message("voice.test.pending")
    if state["status"] == "done":
        return message("voice.test.ok", seconds=f"{state['latency_s']:.1f}")
    return message("voice.test.failed",
                   reason=message("voice.error." + str(state.get("error") or "network")))


def _test_text(game):
    state = game.llm_test_state()
    if state is None:
        return message("llm.test.idle")
    if state["status"] == "pending":
        return message("llm.state.pending")
    if state["status"] == "done":
        return message("llm.test.ok", seconds=f"{state['latency_s']:.1f}")
    return llm_text.status_text(state)
