"""First-launch welcome page ("What do you want to play?").

Shown once after the splash when no ``settings.json`` existed at launch
(``Preferences.onboarded`` False).  Three choices lead straight into a first
step: the frigate lessons, the first submarine lesson, or the Remote Crew
(F9) overlay; Esc or "Main menu" skips.  Any way out persists ``onboarded``.
The page is part of the start menu: it never runs or touches a mission.
"""

from __future__ import annotations

import pygame

from src.core import config, training
from src.core.i18n import message
from src.ui import layout
from src.ui.splash_view import draw_menu_panel

WELCOME_SCREEN = "welcome"
# Choices in display order; keys 1-4 select them.
WELCOME_CHOICES = ("frigate", "submarine", "remote_crew", "menu")
_ROW_Y0 = 212
_ROW_H = 84


class WelcomeMixin:
    """State, keys and drawing of the one-time welcome page."""

    def _init_welcome(self, start_menu: bool) -> None:
        self.welcome_sel = 0
        if (start_menu and not self.web_mode
                and not getattr(self.preferences, "onboarded", True)):
            self.main_menu = False
            self.menu_screen = WELCOME_SCREEN

    @property
    def welcome_active(self) -> bool:
        return (self.in_menu and not self.main_menu
                and self.menu_screen == WELCOME_SCREEN)

    def _finish_onboarding(self) -> None:
        if not self.preferences.onboarded:
            self._set_preference("onboarded", True)

    def _to_main_menu_from_welcome(self, entry: str) -> None:
        self.main_menu = True
        self.menu_screen = "scenario"
        self.menu_sel = 0
        self.main_menu_sel = self.main_menu_index(entry)

    def _choose_welcome(self, choice: str) -> None:
        self._finish_onboarding()
        if choice in ("frigate", "submarine"):
            lesson = (training.FRIGATE_LESSONS[0] if choice == "frigate"
                      else training.BOAT_LESSONS[0])
            self.main_menu = False
            self.menu_screen = "training"
            self.menu_sel = training.LESSONS.index(lesson)
            self.local_side = training.side_of(lesson)
        elif choice == "remote_crew":
            # Closing the overlay lands on the main menu, as F9 from there.
            self._to_main_menu_from_welcome("new")
            self._open_administration("commander")
        else:
            self._to_main_menu_from_welcome("new")

    def _handle_welcome_key(self, key) -> None:
        count = len(WELCOME_CHOICES)
        if key in (pygame.K_UP, pygame.K_LEFT):
            self.welcome_sel = (self.welcome_sel - 1) % count
        elif key in (pygame.K_DOWN, pygame.K_RIGHT, pygame.K_TAB):
            self.welcome_sel = (self.welcome_sel + 1) % count
        elif pygame.K_1 <= key < pygame.K_1 + count:
            self.welcome_sel = key - pygame.K_1
            self._choose_welcome(WELCOME_CHOICES[self.welcome_sel])
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self._choose_welcome(WELCOME_CHOICES[self.welcome_sel])
        elif key in (pygame.K_ESCAPE, pygame.K_q):
            self._choose_welcome("menu")

    def _draw_welcome_page(self) -> None:
        s = self.screen
        cx = config.SCREEN_W // 2
        panel = pygame.Rect(cx - 440, 140, 880, 70 + len(WELCOME_CHOICES) * _ROW_H)
        highlight = pygame.Rect(panel.x + 10, _ROW_Y0 - 6 + self.welcome_sel * _ROW_H,
                                panel.w - 20, _ROW_H - 8)
        draw_menu_panel(s, panel, highlight)
        layout.blit_line(s, "welcome.title", (panel.x + 20, panel.y + 14, panel.w - 40, 40),
                         config.COLOR_WARN, size=28, align="center")
        for index, choice in enumerate(WELCOME_CHOICES):
            selected = index == self.welcome_sel
            y = _ROW_Y0 + index * _ROW_H
            label = message("welcome.choice", index=str(index + 1),
                            label=message(f"welcome.{choice}"))
            layout.blit_line(s, label, (panel.x + 30, y, panel.w - 60, 34),
                             config.COLOR_TEXT if selected else config.COLOR_TEXT_DIM,
                             size=24, align="center")
            layout.blit_line(s, f"welcome.{choice}.note",
                             (panel.x + 30, y + 38, panel.w - 60, 28),
                             config.COLOR_TEXT if selected else config.COLOR_TEXT_DIM,
                             size=17, align="center")
        layout.blit_line(s, "welcome.hint", (cx - 440, panel.bottom + 14, 880, 28),
                         config.COLOR_TEXT_DIM, size=17, align="center")
