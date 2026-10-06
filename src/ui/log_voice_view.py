"""The F11 log's read-aloud buttons: one per station of the log.

With the language model's voice set up (``src/core/game_voice.py``) the
bottom line of the F11 log shows a button per station that logs on this
side ("SONAR on"); a click mutes or unmutes that station's entries, like its
row on options page 2, page 4.  Display and settings only, never the
simulation.
"""

from __future__ import annotations

import pygame

from src.core import config
from src.core.i18n import localize, message, raw_text
from src.ui import layout, pointer

CHIP_H = 24
CHIP_GAP = 6
CHIP_SIZE = 13
# The groups the crewed submarine's log uses (its radio room logs as "funk").
BOAT_GROUPS = ("navigation", "funk", "sonar", "waffen", "schaden", "mission")


def shown(game) -> bool:
    """The buttons appear while the voice can read the log."""
    voice = getattr(game, "voice", None)
    return bool(voice is not None and voice.active and game.preferences.tts_log)


def groups(game) -> tuple:
    return BOAT_GROUPS if getattr(game, "local_side", "frigate") == "uboot" \
        else config.LOG_VOICE_GROUPS


def _chip_text(group: str, on: bool):
    return message("feed.voice.chip", tag=raw_text(config.FEED_CATEGORIES[group][1]),
                   state=message("common.on" if on else "common.off"))


def chip_rects(game, rect) -> tuple:
    """``(label rect, [(group, chip rect)])`` along ``rect``'s bottom line;
    each button as wide as its longer label ("SONAR Aus"), the spare room
    shared evenly, so no label is ever cut."""
    rect = pygame.Rect(rect)
    names = groups(game)
    face = layout.font(CHIP_SIZE)
    label_w = min(rect.w // 5, layout.text_width(face, localize("feed.voice.label")) + 12)
    needs = [max(layout.text_width(face, localize(_chip_text(group, on))) for on in (True, False))
             + 18 for group in names]
    room = rect.w - label_w - CHIP_GAP * len(names)
    spare = max(0, room - sum(needs)) // len(names)
    widths = [need + min(spare, 40) if sum(needs) <= room else room * need // sum(needs)
              for need in needs]
    x = rect.x + label_w + CHIP_GAP
    chips = []
    for group, width in zip(names, widths):
        chips.append((group, pygame.Rect(x, rect.bottom - CHIP_H, width, CHIP_H)))
        x += width + CHIP_GAP
    return pygame.Rect(rect.x, rect.bottom - CHIP_H, label_w, CHIP_H), chips


def draw(game, rect) -> None:
    """Draw the buttons on the bottom line of ``rect`` (the log column)."""
    s = game.screen
    label, chips = chip_rects(game, rect)
    layout.blit_line(s, "feed.voice.label", label, config.COLOR_TEXT_DIM, size=CHIP_SIZE)
    for group, chip in chips:
        on = game.log_voice_on(group)
        tag = config.FEED_CATEGORIES[group][1]
        layout.key_button(s, chip, "", _chip_text(group, on), size=CHIP_SIZE, active=on)
        pointer.add_action(chip, lambda _pos, group=group: game.toggle_log_voice(group))
        pointer.add_tip(chip, lambda group=group, tag=tag: layout.tooltip_payload(
            message("feed.voice.tip_title", tag=raw_text(tag)),
            message("feed.voice.tip_on" if game.log_voice_on(group) else "feed.voice.tip_off"),
            message("voice.log.count", count=game.log_voice_count(group))))
