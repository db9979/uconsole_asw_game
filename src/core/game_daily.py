"""The daily mission in the game: its main-menu page and its logbook line.

``src/core/daily.py`` picks the day's mission per side.  The page shows both
sides' missions of the day with today's best score; Enter starts the chosen
side's mission with the day's seed in the day's real sea area and the normal
length.
"""

from __future__ import annotations

import pygame

from src.core import config, daily
from src.core import logbook as logbook_model
from src.core.i18n import message
from src.ui import layout, pointer

DAILY_ENTRY = "daily"
SIDES = ("frigate", "uboot")


def logbook_side(side: str) -> str:
    return "boat" if side == "uboot" else "frigate"


class DailyMixin:
    """Main-menu page "Daily mission" and filing its best score."""

    def open_daily(self) -> None:
        self.daily_book = logbook_model.load_logbook()
        self.main_menu = False
        self.menu_screen = DAILY_ENTRY
        self.menu_sel = 1 if getattr(self, "local_side", "frigate") == "uboot" else 0

    def start_daily(self, side: str) -> None:
        day = daily.today()
        self.local_side = side
        self.seed = daily.seed_for(day, side)
        self.scenario_key = daily.scenario_for(day, side)
        self.world_mode = daily.WORLD_MODE
        self.start_weather = "random"
        self.start_time = "random"
        self.start_length = "normal"
        self._start_menu_mission()

    def _handle_daily_key(self, key) -> None:
        if key in (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT, pygame.K_TAB):
            self.menu_sel = 1 - (self.menu_sel % 2)
        elif key in (pygame.K_1, pygame.K_2):
            self.menu_sel = 0 if key == pygame.K_1 else 1
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            self.start_daily(SIDES[self.menu_sel % 2])
        elif key in (pygame.K_ESCAPE, pygame.K_q, pygame.K_BACKSPACE):
            self.main_menu = True
            self.main_menu_sel = self.main_menu_index(DAILY_ENTRY)

    def _draw_daily_page(self, center) -> None:
        day = daily.today()
        book = getattr(self, "daily_book", None) or logbook_model.Logbook()
        center(message("daily.title", date=day.strftime("%d.%m.%Y")), 160,
               color=config.COLOR_WARN)
        center(self.tr("daily.intro"), 196, color=config.COLOR_TEXT_DIM)
        cx = config.SCREEN_W // 2
        for index, side in enumerate(SIDES):
            selected = index == self.menu_sel % 2
            y = 262 + index * 110
            pointer.add_action((cx - 430, y - 30, 860, 96),
                               lambda _pos, index=index: self._click_menu_row(
                                   lambda: setattr(self, "menu_sel", index)))
            scenario = daily.scenario_for(day, side)
            title = self.tr("scenario." + config.SCENARIO_NAMES[scenario] + ".title")
            center(message("daily.row", marker="► " if selected else "  ",
                           side=self.tr("daily.side." + side), title=title),
                   y, color=config.COLOR_TEXT if selected else config.COLOR_TEXT_DIM)
            best = book.best.get(f"{logbook_side(side)}:{daily.best_key(day)}")
            layout.blit_line(self.screen, message("daily.best", score=best) if best
                             else "daily.no_best", (cx - 420, y + 22, 840, 24),
                             config.COLOR_TEXT_DIM, size=17, align="center")
        center(self.tr("daily.hint"), 590, color=config.COLOR_TEXT_DIM,
               keys=(None, "Enter", "Esc"))

    def _file_daily(self, book, side: str, scenario: str, won: bool, score: int):
        """A finished daily mission keeps the day's best score; returns
        whether this one is a new daily best, or None for no daily mission."""
        day = daily.match(int(self.seed), scenario,
                          "uboot" if side == "boat" else "frigate")
        if (day is None or self.custom_mission_definition is not None
                or self.world_mode != daily.WORLD_MODE
                or getattr(self, "start_length", "normal") != "normal"):
            return None
        return book.record_daily(side, daily.best_key(day), won, score, daily.KEEP_DAYS)
