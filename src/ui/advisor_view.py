"""uConsole pages of the optional language model: the executive officer
(``F7``) and the model's settings (options page 2).

Both pages are fully mouse-operable: every key they take is also a clickable
blue key button (``src/ui/pointer.py``, overlay layer), the mode tabs and
settings rows take a click, the close box presses ``Esc`` and the wheel
scrolls; ``Game.handle_event`` hands their clicks to ``pointer_input`` so
nothing reaches the station behind."""

from __future__ import annotations

import pygame

from src.core import config
from src.core.i18n import localize, localized, message, raw_text
from src.llm import keystore
from src.ui import game_menu, layout, llm_text, overlay_style, pointer, theme

PANEL = pygame.Rect(140, 30, 1000, 660)
TABS_Y = 88
FIELD = pygame.Rect(172, 582, 936, 34)
LOG = pygame.Rect(172, 130, 936, 440)
BUTTONS_Y = 626
BUTTON_H = 30
NOTE = pygame.Rect(172, 662, 936, 26)
SETTINGS_ROW_Y = 120
SETTINGS_PITCH = 62
SETTINGS_BUTTONS_Y = 640


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
    game_menu.close_button(s, PANEL)
    for index, rect in enumerate(tab_rects(5)):
        active = index == game.advisor_mode
        layout.key_button(s, rect, raw_text(str(index + 1)), message(
            "advisor.mode." + ("situation", "question", "order", "classify",
                               "briefing")[index]), size=16)
        if active:
            pygame.draw.rect(s, theme.c("accent"), rect, 2, border_radius=4)
        # A click picks the mode like its number key, also while a question
        # is being typed (where the digit would go into the text).
        pointer.add_action(rect, lambda _pos, index=index: select_mode(game, index))
    if not game.llm_active():
        layout.blit_block(s, "advisor.off", LOG.x, LOG.y, LOG.w, 120,
                          color=config.COLOR_TEXT_DIM, size=18)
        _buttons(s, ((None, "advisor.button.setup", lambda _pos: game.open_llm_settings()),
                     ("Esc", "common.close", pygame.K_ESCAPE)))
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
    game.advisor_scroll_max = top       # display state: where Up/Down start
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
    if lines:
        # The wheel scrolls like Up/Down (pointer_input); the log takes no click.
        pointer.add_hotspot(LOG)
    mode = game.advisor_mode_name()
    if game.advisor_open_proposal() is not None:
        layout.blit_line(s, "advisor.confirm_hint", FIELD, config.COLOR_WARN, size=17)
        first = (("help.key.enter", "advisor.button.yes", pygame.K_RETURN),
                 ("Backspace", "advisor.button.no", pygame.K_BACKSPACE))
    elif mode in ("question", "order"):
        game.advisor_field.draw(s, FIELD, focused=True)
        first = (("help.key.enter", "advisor.button.send", pygame.K_RETURN),)
    else:
        layout.blit_line(s, "advisor.send_hint." + mode, FIELD, config.COLOR_TEXT_DIM, size=17)
        pointer.add_key(FIELD, pygame.K_RETURN)
        first = (("help.key.enter", "advisor.button.send", pygame.K_RETURN),)
    # The talk key (src/core/game_talk.py): held, it records a question.
    talk = ((("Shift+Space", "talk.button.send" if game.talk_state == "recording"
              else "talk.button.speak", (pygame.K_SPACE, pygame.KMOD_SHIFT)),)
            if game.stt.active else ())
    _buttons(s, first + talk + (("↑", "advisor.button.older", pygame.K_UP),
                                ("↓", "advisor.button.newer", pygame.K_DOWN),
                                ("Esc", "common.close", pygame.K_ESCAPE)))
    if game.talk_state != "idle":
        from src.ui.talk_view import header_line
        text, color = header_line(game)
        layout.blit_line(s, text, NOTE, color, size=15, align="center")
    else:
        layout.blit_block(s, "advisor.logbook_note", NOTE.x, NOTE.y, NOTE.w, NOTE.h,
                          color=config.COLOR_TEXT_DIM, size=13, align="center")


def select_mode(game, index: int) -> None:
    """A click on a mode tab (UI state only, like Left/Right or 1-5)."""
    game.advisor_mode = index % 5


def button_rects(count: int, y: int = BUTTONS_Y, needs=None) -> tuple:
    """Key buttons side by side across the panel's inner width; with
    ``needs`` (each button's natural width) the spare room is shared evenly,
    so a long German key name never cuts its label."""
    gap = 10
    room = PANEL.w - 64 - gap * (count - 1)
    needs = list(needs) if needs else [0] * count
    total = sum(needs)
    if total > room:
        widths = [room * need // total for need in needs]
    else:
        widths = [need + (room - total) // count for need in needs]
    rects, x = [], PANEL.x + 32
    for width in widths:
        rects.append(pygame.Rect(x, y, width, BUTTON_H))
        x += width + gap
    return tuple(rects)


def _button_need(cap, label) -> int:
    from src.core.i18n import key_label
    face = layout.font(15)
    width = layout.text_width(face, localize(label)) + 16
    if cap is not None:
        width += layout.text_width(face, key_label(
            cap if cap.startswith("help.") else raw_text(cap))) + 14
    return width


def _buttons(s, specs, y: int = BUTTONS_Y) -> None:
    """Draw ``(key cap, label, key or action)`` buttons; a click presses the
    key (or runs the action) through the overlay's pointer layer."""
    needs = [_button_need(cap, label) for cap, label, _spec in specs]
    for (cap, label, spec), rect in zip(specs, button_rects(len(specs), y, needs)):
        if cap is None:
            pygame.draw.rect(s, theme.c("raised"), rect, border_radius=4)
            pygame.draw.rect(s, theme.c("line_strong"), rect, 1, border_radius=4)
            layout.blit_line(s, label, rect.inflate(-12, -4), config.COLOR_TEXT, size=15,
                             align="center")
        else:
            layout.key_button(s, rect, cap if cap.startswith("help.")
                              else raw_text(cap), label, size=15)
        pointer.add_spec(rect, spec)


# The log page has ten rows: a tighter pitch, still clear of the footer.
LOG_PITCH = 48


def settings_row_rects(count: int = 8) -> tuple:
    pitch, height = (SETTINGS_PITCH, 54) if count <= 8 else (LOG_PITCH, 46)
    return tuple(pygame.Rect(PANEL.x + 60, SETTINGS_ROW_Y + index * pitch,
                             PANEL.w - 120, height) for index in range(count))


def page_tab_rects() -> tuple:
    """The settings' five page tabs (language model, voice, how it sounds,
    log reports, speech input) in one row left of the close box; the
    chosen tab names the page."""
    count, gap = 5, 8
    left = PANEL.x + 24
    right = game_menu.close_rect(PANEL).x - 12
    width = (right - left - gap * (count - 1)) // count
    return tuple(pygame.Rect(left + index * (width + gap), PANEL.y + 14, width, 34)
                 for index in range(count))


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


def _log_values(game) -> dict:
    from src.core import config
    prefs = game.preferences
    values = {"tts_log": _on_off(prefs.tts_log)}
    for group in config.LOG_VOICE_GROUPS:
        values[f"tts_log_{group}"] = _on_off(getattr(prefs, f"tts_log_{group}"))
    return values


def _log_help(game, name):
    """Under a station's row: how many entries it logged lately."""
    if name == "tts_log":
        return "voice.help.tts_log"
    return message("voice.log.count", count=game.log_voice_count(name[len("tts_log_"):]))


@localized
def draw_llm_settings(game) -> None:
    from src.core.game_advisor import LLM_PAGES

    s = game.screen
    page = game.llm_page % len(LLM_PAGES)
    overlay_style.panel(s, PANEL)
    game_menu.close_button(s, PANEL)
    for index, rect in enumerate(page_tab_rects()):
        active = index == page
        if active:
            overlay_style.highlight(s, rect)
        pygame.draw.rect(s, config.COLOR_TEXT_DIM, rect, 1)
        layout.blit_line(s, message("llm.page", number=index + 1,
                                    name=message(("llm.page.model", "llm.page.voice",
                                                  "llm.page.tune", "llm.page.log",
                                                  "llm.page.stt")[index])),
                         rect.inflate(-8, -4), overlay_style.text_color(active),
                         size=16, align="center")
        pointer.add_action(rect, lambda _pos, index=index: game.set_llm_page(index))
    layout.blit_line(s, ("llm.subtitle", "voice.subtitle", "voice.tune_subtitle",
                         "voice.log_subtitle", "stt.subtitle")[page],
                     (PANEL.x + 32, PANEL.y + 56, PANEL.w - 64, 24),
                     config.COLOR_TEXT_DIM, size=15, align="center")
    rows = LLM_PAGES[page]
    values = (_llm_values(game) if page == 0 else _log_values(game) if page == 3
              else _stt_values(game) if page == 4 else _voice_values(game))
    prefix = "llm" if page == 0 else "stt" if page == 4 else "voice"
    for index, (name, rect) in enumerate(zip(rows, settings_row_rects(len(rows)))):
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
            layout.blit_line(s, _log_help(game, name) if page == 3 else f"{prefix}.help." + name,
                             (rect.x + 16, rect.y + 26, rect.w - 16, 22),
                             config.COLOR_TEXT_DIM, size=14)
            pointer.add_action(rect, lambda _pos, index=index: game.click_llm_row(index))
    if game.llm_field is not None:
        _buttons(s, (("help.key.enter", "llm.button.save", pygame.K_RETURN),
                     ("Esc", "llm.button.cancel", pygame.K_ESCAPE)), SETTINGS_BUTTONS_Y)
    else:
        _buttons(s, (("↑", "llm.button.up", pygame.K_UP),
                     ("↓", "llm.button.down", pygame.K_DOWN),
                     ("←", "llm.button.previous", pygame.K_LEFT),
                     ("→", "llm.button.next", pygame.K_RIGHT),
                     ("help.key.enter", "llm.button.change", pygame.K_RETURN),
                     ("Tab", "llm.button.page", pygame.K_TAB),
                     ("Esc", "llm.button.back", pygame.K_ESCAPE)), SETTINGS_BUTTONS_Y)


def _stt_values(game) -> dict:
    prefs = game.preferences
    source = game.stt_key_source()
    key = game.stt.config.api_key
    return {
        "stt_enabled": _on_off(prefs.stt_enabled),
        "stt_url": raw_text(prefs.stt_url),
        "stt_model": raw_text(prefs.stt_model),
        "stt_key": message("stt.key_env") if source == "env"
        else message("stt.key_shared", masked=raw_text(keystore.mask(key)))
        if source == "shared" else raw_text(keystore.mask(key)),
        "stt_test": _stt_test_text(game),
    }


def _stt_test_text(game):
    state = game.stt_test_state()
    if state is None:
        return message("stt.test.idle")
    if state["status"] == "pending":
        return message("voice.test.pending")
    if state["status"] == "done":
        return message("stt.test.ok", seconds=f"{state['latency_s']:.1f}")
    return message("stt.test.failed",
                   reason=message("talk.error." + str(state.get("error") or "network")))


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
