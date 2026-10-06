"""Guided training missions in the game (main menu "Training").

``src/core/training.py`` defines the lessons; this mixin starts one through
the custom-mission runtime, advances its coach from the mission's slow
stage and draws the step hint.  A lesson whose objective is to survive
ends as won once its last step is done.
"""

from __future__ import annotations

import math

import pygame

from src.core import config, training
from src.core.i18n import message
from src.ui import layout, menu_list, pointer

# Lessons shown at once on the training page (the list scrolls).
TRAINING_ROWS = 6


class TrainingMixin:
    """Lesson start, step coaching and the hint banner."""

    def start_training(self, lesson: str) -> bool:
        definition = training.lesson_definition(lesson, self.seed)
        # A lesson sets the side it teaches (it is outside any mission here).
        self.local_side = training.side_of(lesson)
        if not self.start_custom_mission(definition):
            return False
        self.training = training.TrainingCoach(lesson, definition["player"]["course_deg"])
        if lesson in training.BOAT_LESSONS:
            self.claim_opfor_sub()
            if self.opfor is not None:
                self.opfor.notice(self.sim_t, "mission", message("training.lesson_brief." + lesson),
                                  stamp=self.world.format_time())
            return True
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
        if training.frigate_should_ping(self, coach):
            coach.next_ping_t = self.sim_t + training.BOAT_PING_INTERVAL_S
            with self.sonar_perspective(self._frigate_sonar):
                self.send_active_ping()
        if coach.lesson == "air":
            self._update_lesson_missile(coach)
        if (coach.lesson == "torpedo" and not self.game_over
                and float(self.damage.total) > 0.0):
            # The torpedo found the ship: the lesson is lost, R repeats it.
            self._end_mission(False, message("training.torpedo_hit"))
            return
        passed = coach.advance(self)
        if not passed:
            return
        if coach.done:
            self._remember_lesson(coach.lesson)
        text = message("training.step_done", step=str(coach.step),
                       steps=str(len(coach.steps)))
        if coach.lesson in training.BOAT_LESSONS and self.opfor is not None:
            self.opfor.notice(self.sim_t, "mission", text, stamp=self.world.format_time())
        else:
            self.feed.add(self.world.format_time(), "mission", text)
        if coach.done and not self.game_over:
            if self.mission.win_mode == "survive":
                self._end_mission(True, message("training.complete"))
            else:
                self.flash(message("training.complete"), 4.0)

    def _update_lesson_missile(self, coach) -> None:
        """The air-defence lesson's missile: note how the last one ended,
        launch the next when it is due (``training.lesson_missile_due``)."""
        alive = training.missiles_alive(self)
        if coach.missile_alive and not alive:
            hit = float(self.damage.total) > coach.damage_at_launch
            coach.missile_result = "hit" if hit else "down"
            coach.next_ping_t = self.sim_t + training.MISSILE_AGAIN_S
            if hit or not self.essm_seq:
                self.flash(message("training.missile_again"), 4.0)
        coach.missile_alive = alive
        if training.lesson_missile_due(self, coach):
            self._launch_lesson_missile()
            coach.missile_alive = True
            coach.missile_result = None
            coach.damage_at_launch = float(self.damage.total)

    def _launch_lesson_missile(self) -> None:
        """One sea-skimmer in cruise flight from the lesson's fixed bearing,
        aimed at the ship (as a mission's missile wave, ``_maybe_spawn_asm``)."""
        from src.air.asm import ASM
        bearing = math.radians(training.MISSILE_BEARING_DEG)
        x = config.clamp(self.ship.x + training.MISSILE_RANGE_NM * math.sin(bearing),
                         0.0, self.world.size_nm)
        y = config.clamp(self.ship.y - training.MISSILE_RANGE_NM * math.cos(bearing),
                         0.0, self.world.size_nm)
        course = math.degrees(math.atan2(self.ship.x - x, -(self.ship.y - y))) % 360.0
        self.asms.append(ASM(x, y, course, self._next_asm_sequence(), self.rng_asm,
                             self._air_defense_loadout["asm"],
                             datum=(self.ship.x, self.ship.y)))

    def lessons_done(self) -> tuple:
        return training.valid_done(getattr(self.preferences, "lessons_done", ()))

    def _remember_lesson(self, lesson: str) -> None:
        """A finished lesson keeps its tick mark (settings, not the save)."""
        done = self.lessons_done()
        if lesson not in done:
            self._set_preference("lessons_done", training.valid_done(done + (lesson,)))

    def start_next_lesson(self) -> bool:
        """After a finished lesson: the next one in menu order."""
        coach = getattr(self, "training", None)
        lesson = None if coach is None else training.following(coach.lesson)
        if lesson is None or not coach.done:
            return False
        return self.start_training(lesson)

    def draw_training_hint(self, rect=None) -> None:
        coach = getattr(self, "training", None)
        if coach is None or self.game_over:
            return
        rect = pygame.Rect(rect or (300, config.SCREEN_H - 190, 680, 46))
        pygame.draw.rect(self.screen, config.COLOR_OVERLAY_BG, rect)
        pygame.draw.rect(self.screen, config.COLOR_WARN, rect, 1)
        step = min(coach.step + 1, len(coach.steps))
        layout.blit_block(self.screen, message("training.hint", step=str(step),
                                               steps=str(len(coach.steps)),
                                               hint=message(coach.hint_key())),
                          rect.x + 10, rect.y + 3, rect.w - 20, rect.h - 6,
                          config.COLOR_WARN, size=17, align="center", valign="center")

    def open_training_menu(self) -> None:
        """The training page, opened on the next lesson not yet done."""
        self.main_menu = False
        self.menu_screen = "training"
        upcoming = training.next_lesson(self.lessons_done())
        self.menu_sel = training.LESSONS.index(upcoming) if upcoming is not None else 0

    def end_keys(self, keys: tuple) -> tuple:
        """The end panel's keys, with N for the next lesson after a finished one."""
        coach = getattr(self, "training", None)
        if coach is not None and coach.done and training.following(coach.lesson) is not None:
            return keys[:2] + (("N", "end.key.next_lesson"),) + keys[2:]
        return keys

    def _draw_training_menu(self, center) -> None:
        center(self.tr("training.menu_title"), 150, color=config.COLOR_TEXT_DIM)
        done = self.lessons_done()
        upcoming = training.next_lesson(done)
        count = len(training.LESSONS)
        first = menu_list.first_row(count, self.menu_sel, TRAINING_ROWS)
        for index in range(first, min(count, first + TRAINING_ROWS)):
            lesson = training.LESSONS[index]
            y = 200 + (index - first) * 62
            selected = index == self.menu_sel
            title = self.tr("training.lesson." + lesson)
            if lesson in training.BOAT_LESSONS:
                title = message("training.boat_title", title=title)
            # A click on a lesson starts it (like selecting it and Enter).
            pointer.add_action((config.SCREEN_W // 2 - 420, y - 16, 840, 58),
                               lambda _pos, index=index: self._click_menu_row(
                                   lambda: setattr(self, "menu_sel", index)))
            if lesson in done:
                title = message("training.title_done", title=title)
            elif lesson == upcoming:
                title = message("training.title_next", title=title)
            center(message("training.menu_choice", marker="► " if selected else "  ",
                           index=str(index + 1), title=title),
                   y, color=config.COLOR_TEXT if selected
                   else config.COLOR_TEXT_DIM, width=840)
            layout.blit_line(self.screen, "training.lesson_note." + lesson,
                             (config.SCREEN_W // 2 - 420, y + 20, 840, 24),
                             config.COLOR_TEXT_DIM, size=17, align="center")
        menu_list.draw_scrollbar(self.screen, (config.SCREEN_W // 2 + 432, 184,
                                               8, TRAINING_ROWS * 62),
                                 first, TRAINING_ROWS, count)
        center(message("training.progress", done=len(done), lessons=count), 566,
               color=config.COLOR_OK if upcoming is None else config.COLOR_TEXT_DIM)
        center(self.tr("training.menu_hint"), 598, color=config.COLOR_TEXT_DIM,
               keys=(None, "Enter", "Esc"))
