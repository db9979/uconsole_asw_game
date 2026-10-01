"""Own missions in the start menu (``Game`` mixin).

After the side choice, the scenario list ends with a row "Own missions";
it opens the missions of the Mission Editor's library authored for that side
(``side``: frigate or submarine). Enter starts one through the custom-mission
runtime (``start_custom_mission``), with the uConsole on the mission's side.
The list is read once when the screen opens (never per frame).
"""

from __future__ import annotations

from src.core import config
from src.core.i18n import message, raw_text
from src.core.mission_definition import mission_side
from src.data.user_content import default_store
from src.ui import layout, pointer

CUSTOM_SCREEN = "custom"
CUSTOM_ROWS = 9                 # rows shown at once; the list scrolls


class CustomMissionMixin:
    """The "Own missions" row and list of the start menu."""

    def custom_menu_records(self) -> list:
        """The library's missions for the uConsole's side, by name (bounded)."""
        side = "uboot" if self.local_side == "uboot" else "frigate"
        try:
            records = default_store(config.SAVE_DIR).list("mission")
        except (OSError, ValueError):
            records = []
        rows = [record for record in records if mission_side(record.data) == side]
        return sorted(rows, key=lambda record: (str(record.data.get("name", "")).lower(),
                                                record.key))[:200]

    def open_custom_menu(self) -> None:
        self._custom_records = self.custom_menu_records()
        self.menu_screen = CUSTOM_SCREEN
        self.menu_sel = 0

    def start_user_mission(self, definition: dict) -> bool:
        """Start an own mission with the uConsole on the mission's side."""
        self.local_side = mission_side(definition)
        return self.start_custom_mission(definition)

    def _handle_custom_menu_key(self, key) -> None:
        import pygame
        records = getattr(self, "_custom_records", [])
        if key in (pygame.K_ESCAPE, pygame.K_q):
            self.menu_screen = "scenario"
            self.menu_sel = self.custom_row_sel()
            return
        if not records:
            return
        if key == pygame.K_UP:
            self.menu_sel = (self.menu_sel - 1) % len(records)
        elif key == pygame.K_DOWN:
            self.menu_sel = (self.menu_sel + 1) % len(records)
        elif key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN):
            step = CUSTOM_ROWS if key == pygame.K_PAGEDOWN else -CUSTOM_ROWS
            self.menu_sel = max(0, min(len(records) - 1, self.menu_sel + step))
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            record = records[min(self.menu_sel, len(records) - 1)]
            if not self.start_user_mission(record.data):
                self.flash(message("menu.custom.start_failed"), 3.0)

    def custom_row_sel(self) -> int:
        """``menu_sel`` of the scenario list's "Own missions" row."""
        return len(config.SCENARIO_ORDER)

    def _draw_custom_menu(self, center) -> None:
        records = getattr(self, "_custom_records", [])
        side_key = ("menu.custom.title.uboot" if self.local_side == "uboot"
                    else "menu.custom.title.frigate")
        center(self.tr(side_key), 150, color=config.COLOR_TEXT_DIM)
        cx = config.SCREEN_W // 2
        if not records:
            layout.blit_block(self.screen, message("menu.custom.empty"), cx - 420, 220, 840, 120,
                              color=config.COLOR_TEXT_DIM, size=20, align="center")
        first = max(0, min(self.menu_sel - CUSTOM_ROWS // 2, len(records) - CUSTOM_ROWS))
        for row_i, record in enumerate(records[first:first + CUSTOM_ROWS]):
            index = first + row_i
            selected = index == self.menu_sel
            y = 210 + row_i * 36
            pointer.add_action((cx - 420, y - 16, 840, 34),
                               lambda _pos, index=index: self._click_menu_row(
                                   lambda: setattr(self, "menu_sel", index)))
            center(message("menu.choice", marker="► " if selected else "  ",
                           label=raw_text(str(record.data.get("name", record.key)))),
                   y, color=config.COLOR_TEXT if selected else config.COLOR_TEXT_DIM)
        if records:
            record = records[min(self.menu_sel, len(records) - 1)]
            layout.blit_block(self.screen, raw_text(str(record.data.get("description", ""))),
                              cx - 420, 210 + CUSTOM_ROWS * 36 + 4, 840, 56,
                              color=config.COLOR_TEXT_DIM, size=17, align="center")
        center(self.tr("menu.custom.hint"), 590, color=config.COLOR_TEXT_DIM,
               keys=(None, "Enter", "Esc"))
