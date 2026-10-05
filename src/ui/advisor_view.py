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
        first = (("Enter", "advisor.button.yes", pygame.K_RETURN),
                 ("Backspace", "advisor.button.no", pygame.K_BACKSPACE))
    elif mode in ("question", "order"):
        game.advisor_field.draw(s, FIELD, focused=True)
        first = (("Enter", "advisor.button.send", pygame.K_RETURN),)
    else:
        layout.blit_line(s, "advisor.send_hint." + mode, FIELD, config.COLOR_TEXT_DIM, size=17)
        pointer.add_key(FIELD, pygame.K_RETURN)
        first = (("Enter", "advisor.button.send", pygame.K_RETURN),)
    _buttons(s, first + (("↑", "advisor.button.older", pygame.K_UP),
                         ("↓", "advisor.button.newer", pygame.K_DOWN),
                         ("Esc", "common.close", pygame.K_ESCAPE)))
    layout.blit_block(s, "advisor.logbook_note", NOTE.x, NOTE.y, NOTE.w, NOTE.h,
                      color=config.COLOR_TEXT_DIM, size=13, align="center")


def select_mode(game, index: int) -> None:
    """A click on a mode tab (UI state only, like Left/Right or 1-5)."""
    game.advisor_mode = index % 5


def button_rects(count: int, y: int = BUTTONS_Y) -> tuple:
    """Equal key buttons side by side across the panel's inner width."""
    gap = 10
    width = (PANEL.w - 64 - gap * (count - 1)) // count
    return tuple(pygame.Rect(PANEL.x + 32 + index * (width + gap), y, width, BUTTON_H)
                 for index in range(count))


def _buttons(s, specs, y: int = BUTTONS_Y) -> None:
    """Draw ``(key cap, label, key or action)`` buttons; a click presses the
    key (or runs the action) through the overlay's pointer layer."""
    for (cap, label, spec), rect in zip(specs, button_rects(len(specs), y)):
        if cap is None:
            pygame.draw.rect(s, theme.c("raised"), rect, border_radius=4)
            pygame.draw.rect(s, theme.c("line_strong"), rect, 1, border_radius=4)
            layout.blit_line(s, label, rect.inflate(-12, -4), config.COLOR_TEXT, size=15,
                             align="center")
        else:
            layout.key_button(s, rect, cap if cap.startswith("help.")
                              else raw_text(cap), label, size=15)
        pointer.add_spec(rect, spec)


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

    # The configured key (read when it was set), never the key file per frame.
    key = game.llm.config.api_key
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
    game_menu.close_button(s, PANEL)
    editing = game.llm_field is not None
    for index, (name, rect) in enumerate(zip(LLM_ROWS, settings_row_rects())):
        selected = index == game.llm_sel
        if not editing:
            # A click on a row picks it and changes it like Enter.
            pointer.add_action(rect, lambda _pos, index=index: click_llm_row(game, index))
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
    if editing:
        _buttons(s, (("Enter", "llm.button.save", pygame.K_RETURN),
                     ("Esc", "llm.button.cancel", pygame.K_ESCAPE)), SETTINGS_BUTTONS_Y)
    else:
        _buttons(s, (("↑", "llm.button.up", pygame.K_UP),
                     ("↓", "llm.button.down", pygame.K_DOWN),
                     ("←", "llm.button.previous", pygame.K_LEFT),
                     ("→", "llm.button.next", pygame.K_RIGHT),
                     ("Enter", "llm.button.change", pygame.K_RETURN),
                     ("Esc", "llm.button.back", pygame.K_ESCAPE)), SETTINGS_BUTTONS_Y)


def click_llm_row(game, index: int) -> None:
    """Select settings row ``index`` and change it as Enter would."""
    from src.core import pointer_input
    game.llm_sel = index
    pointer_input.press(game, pygame.K_RETURN)


def _test_text(game):
    state = game.llm_test_state()
    if state is None:
        return message("llm.test.idle")
    if state["status"] == "pending":
        return message("llm.state.pending")
    if state["status"] == "done":
        return message("llm.test.ok", seconds=f"{state['latency_s']:.1f}")
    return llm_text.status_text(state)
