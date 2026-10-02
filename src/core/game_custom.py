"""The start menu's mission lists (``Game`` mixin).

After the side choice, the side's scenarios are listed in a scrolling panel
(``SCENARIO_ROWS`` at once, ``src/ui/menu_list.py``) under which the selected
mission's objective is shown. The list ends with a row "Own missions";
it opens the missions of the Mission Editor's library authored for that side
(``side``: frigate or submarine). Enter starts one through the custom-mission
runtime (``start_custom_mission``), with the uConsole on the mission's side.
The list is read once when the screen opens (never per frame).
"""

from __future__ import annotations

import pygame

from src.core import config
from src.core.i18n import message, raw_text
from src.core.mission_definition import mission_side
from src.data.user_content import default_store
from src.ui import layout, menu_list, pointer
from src.ui.splash_view import draw_menu_panel

CUSTOM_SCREEN = "custom"
CUSTOM_ROWS = 9                 # rows shown at once; the list scrolls
SCENARIO_ROWS = 9               # scenario rows shown at once; the list scrolls
LIST_ROW_H = 36                 # pitch of a mission row
LIST_TOP = 178                  # top of the list panel (below the page title)
LIST_W = 800                    # width of the list panel
LIST_TEXT_W = LIST_W - 64       # row text, clear of the scroll bar
NOTE_H = 66                     # the selected mission's note under the panel
MENU_HINT_Y = 596               # key hint line under a list page


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
            self.menu_sel = menu_list.page_step(
                len(records), self.menu_sel, CUSTOM_ROWS,
                1 if key == pygame.K_PAGEDOWN else -1)
        elif key in (pygame.K_HOME, pygame.K_END):
            self.menu_sel = 0 if key == pygame.K_HOME else len(records) - 1
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            record = records[min(self.menu_sel, len(records) - 1)]
            if not self.start_user_mission(record.data):
                self.flash(message("menu.custom.start_failed"), 3.0)

    def custom_row_sel(self) -> int:
        """``menu_sel`` of the scenario list's "Own missions" row."""
        return len(config.SCENARIO_ORDER)

    def scenario_menu_rows(self) -> list:
        """``menu_sel`` values of the scenario list: the side's scenarios
        (indices into ``SCENARIO_ORDER``), then the own-missions row."""
        return ([config.SCENARIO_ORDER.index(key)
                 for key in config.scenarios_for_side(self.local_side)]
                + [self.custom_row_sel()])

    def _list_panel(self, count: int, rows: int, selected: int):
        """Panel, first visible entry and row centre of a scrolling list."""
        cx = config.SCREEN_W // 2
        first = menu_list.first_row(count, selected, rows)
        shown = max(1, min(count, rows))
        panel = pygame.Rect(cx - LIST_W // 2, LIST_TOP, LIST_W, shown * LIST_ROW_H + 12)
        highlight = pygame.Rect(0, 0, 0, 0)
        if first <= selected < first + shown:
            highlight = pygame.Rect(panel.x + 10, panel.y + 6 + (selected - first) * LIST_ROW_H,
                                    panel.w - 44, LIST_ROW_H - 2)
        draw_menu_panel(self.screen, panel, highlight)
        menu_list.draw_scrollbar(self.screen, (panel.right - 22, panel.y + 8, 8, panel.h - 16),
                                 first, rows, count)
        return panel, first, shown

    def _draw_scenario_list(self, center, row) -> None:
        """The side's scenarios and the own-missions row, scrolling."""
        sels = self.scenario_menu_rows()
        custom = self.custom_row_sel()
        pos = sels.index(custom if self.menu_sel == custom else self.scenario_menu_index())
        panel, first, shown = self._list_panel(len(sels), SCENARIO_ROWS, pos)
        for index in range(first, first + shown):
            sel = sels[index]
            y = panel.y + 6 + (index - first) * LIST_ROW_H + LIST_ROW_H // 2
            row(y, LIST_ROW_H - 2, lambda sel=sel: setattr(self, "menu_sel", sel),
                panel.w - 44)
            chosen = index == pos
            marker = "► " if chosen else "  "
            color = config.COLOR_TEXT if chosen else config.COLOR_TEXT_DIM
            if sel == custom:
                center(message("menu.custom.row", marker=marker), y, color=color,
                       width=LIST_TEXT_W)
                continue
            key = config.SCENARIO_ORDER[sel]
            level = self.tr("menu.difficulty_fixed"
                            if config.SCENARIOS[key]["difficulty"] is not None
                            else "menu.difficulty_custom")
            title = self.tr("scenario." + config.SCENARIO_NAMES[key] + ".title")
            center(message("menu.scenario_choice", index=index + 1, marker=marker,
                           title=title, level=level), y, color=color, width=LIST_TEXT_W)
        # Under the list: the start of the selected mission's briefing.
        note = (message("menu.custom.row_note") if sels[pos] == custom else message(
            "scenario." + config.SCENARIO_NAMES[config.SCENARIO_ORDER[sels[pos]]] + ".brief"))
        layout.blit_block(self.screen, note, panel.x + 20, panel.bottom + 8,
                          panel.w - 40, NOTE_H, color=config.COLOR_TEXT_DIM, size=17,
                          align="center")

    def _draw_custom_menu(self, center) -> None:
        records = getattr(self, "_custom_records", [])
        side_key = ("menu.custom.title.uboot" if self.local_side == "uboot"
                    else "menu.custom.title.frigate")
        center(self.tr(side_key), 150, color=config.COLOR_TEXT_DIM)
        cx = config.SCREEN_W // 2
        if not records:
            layout.blit_block(self.screen, message("menu.custom.empty"), cx - 420, 220, 840, 120,
                              color=config.COLOR_TEXT_DIM, size=20, align="center")
        else:
            panel, first, shown = self._list_panel(len(records), CUSTOM_ROWS,
                                                   self.menu_sel)
            for index in range(first, first + shown):
                record = records[index]
                selected = index == self.menu_sel
                y = panel.y + 6 + (index - first) * LIST_ROW_H + LIST_ROW_H // 2
                pointer.add_action((panel.x + 10, y - LIST_ROW_H // 2, panel.w - 44,
                                    LIST_ROW_H - 2),
                                   lambda _pos, index=index: self._click_menu_row(
                                       lambda: setattr(self, "menu_sel", index)))
                center(message("menu.choice", marker="► " if selected else "  ",
                               label=raw_text(str(record.data.get("name", record.key)))),
                       y, color=config.COLOR_TEXT if selected else config.COLOR_TEXT_DIM,
                       width=LIST_TEXT_W)
            record = records[min(self.menu_sel, len(records) - 1)]
            layout.blit_block(self.screen, raw_text(str(record.data.get("description", ""))),
                              panel.x + 20, panel.bottom + 8, panel.w - 40, NOTE_H,
                              color=config.COLOR_TEXT_DIM, size=17, align="center")
        center(self.tr("menu.custom.hint"), MENU_HINT_Y, color=config.COLOR_TEXT_DIM,
               keys=(None, "Enter", "Esc"))
