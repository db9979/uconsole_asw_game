"""The numeric-entry overlay names every boat entry in both languages
(it once showed the raw key ``input.uboot_depth``)."""

import json
from pathlib import Path

import pygame

from src.core import uboot_local

ROOT = Path(__file__).resolve().parents[1]
MODES = ("uboot_course", "uboot_speed", "uboot_depth", "uboot_bearing", "uboot_range",
         "uboot_torpedo_depth", "uboot_wire_bearing", "uboot_wire_range")


def test_every_boat_entry_has_an_overlay_label():
    for language in ("en", "de"):
        catalog = json.loads((ROOT / "data" / "i18n" / f"{language}.json").read_text("utf-8"))
        for mode in MODES:
            assert catalog.get(f"input.{mode}"), (language, mode)


def test_overlay_shows_text_not_the_key(monkeypatch):
    from test_uboot_scope import _local_boat
    game, _boat = _local_boat()
    shown = []
    real = game.tr
    monkeypatch.setattr(game, "tr", lambda key, **values: shown.append(real(key, **values))
                        or shown[-1])
    for mode in ("uboot_course", "uboot_speed", "uboot_depth"):
        uboot_local.begin_input(game, mode)
        game.draw_navigation_input()
        game.input_mode = None
    assert shown and not any(text.startswith("input.") for text in shown)
    pygame.event.clear()
