"""Guided training missions in the game (main menu "Training").

``src/core/training.py`` defines the lessons; this mixin starts one through
the custom-mission runtime, advances its coach from the mission's slow
stage and draws the step hint.  A lesson whose objective is to survive
ends as won once its last step is done.
"""

from __future__ import annotations

import pygame

from src.core import config, training
from src.core.i18n import message
from src.ui import layout


class TrainingMixin:
    """Lesson start, step coaching and the hint banner."""

    def start_training(self, lesson: str) -> bool:
        definition = training.lesson_definition(lesson, self.seed)
        if not self.start_custom_mission(definition):
            return False
        self.training = training.TrainingCoach(lesson, definition["player"]["course_deg"])
        self.hq_msg(message("training.lesson_brief." + lesson))
        return True

    def _restore_training(self) -> None:
        """A loaded lesson gets its coach back (from step 1; see training.py)."""
        definition = getattr(self, "custom_mission_definition", None)
        lesson = training.lesson_of(definition)
        self.training = (None if lesson is None else
                         training.TrainingCoach(lesson, definition["player"]["course_deg"]))

    def _update_training(self) -> None:
        coach = getattr(self, "training", None)
        if coach is None or coach.done and self.game_over:
            return
        passed = coach.advance(self)
        if not passed:
            return
        text = message("training.step_done", step=str(coach.step),
                       steps=str(len(coach.steps)))
        self.feed.add(self.world.format_time(), "mission", text)
        if coach.done and not self.game_over:
            if self.mission.win_mode == "survive":
                self._end_mission(True, message("training.complete"))
            else:
                self.flash(message("training.complete"), 4.0)

    def draw_training_hint(self) -> None:
        coach = getattr(self, "training", None)
        if coach is None or self.game_over:
            return
        rect = pygame.Rect(300, config.SCREEN_H - 190, 680, 46)
        pygame.draw.rect(self.screen, config.COLOR_OVERLAY_BG, rect)
        pygame.draw.rect(self.screen, config.COLOR_WARN, rect, 1)
        step = min(coach.step + 1, len(coach.steps))
        layout.blit_block(self.screen, message("training.hint", step=str(step),
                                               steps=str(len(coach.steps)),
                                               hint=message(coach.hint_key())),
                          rect.x + 10, rect.y + 3, rect.w - 20, rect.h - 6,
                          config.COLOR_WARN, size=17, align="center", valign="center")

    def _draw_training_menu(self, center) -> None:
        center(self.tr("training.menu_title"), 150, color=config.COLOR_TEXT_DIM)
        for index, lesson in enumerate(training.LESSONS):
            selected = index == self.menu_sel
            center(message("training.menu_choice", marker="► " if selected else "  ",
                           index=str(index + 1), title=self.tr("training.lesson." + lesson)),
                   230 + index * 70, color=config.COLOR_TEXT if selected
                   else config.COLOR_TEXT_DIM)
            layout.blit_line(self.screen, "training.lesson_note." + lesson,
                             (config.SCREEN_W // 2 - 420, 250 + index * 70, 840, 24),
                             config.COLOR_TEXT_DIM, size=17, align="center")
        center(self.tr("training.menu_hint"), 540, color=config.COLOR_TEXT_DIM)
