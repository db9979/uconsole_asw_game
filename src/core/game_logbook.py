"""The service record in the game: filing a finished mission, the end-panel
line and the main-menu page "Logbook".

``src/core/logbook.py`` holds the record and its file.  A mission is filed
once when it ends, for the side the uConsole played; lessons are not filed.
The page shows one side at a time (``Left``/``Right`` switch).
"""

from __future__ import annotations

import datetime

import pygame

from src.core import boat_campaign, boat_debrief, config
from src.core import logbook as logbook_model
from src.core.i18n import message, raw_text
from src.ui import layout

LOGBOOK_ENTRY = "logbook"
RECENT_ROWS = 4


def _events(recorder, kind: str) -> int:
    if recorder is None:
        return 0
    return sum(1 for event in recorder.events if event["kind"] == kind)


class LogbookMixin:
    """Files missions and shows the logbook page."""

    def _init_logbook(self) -> None:
        self.logbook_result = None
        self.logbook_view = None
        self.logbook_side = "frigate"

    def _logbook_side(self) -> str:
        return ("boat" if getattr(self, "local_side", "frigate") == "uboot"
                and getattr(self, "_opfor", None) is not None else "frigate")

    def _logbook_mission_ended(self) -> None:
        """File the finished mission (never a lesson)."""
        self.logbook_result = None
        if getattr(self, "training", None) is not None:
            return
        side = self._logbook_side()
        level = self.level if self.level in config.LEVELS else config.LEVEL_DEFAULT
        if side == "boat":
            boat = self._opfor
            sub = boat.sub
            outcome = boat_debrief.outcome(self, boat)
            won = outcome in boat_campaign.WINS
            recorder = self.boat_debrief
            damage = float(sub.damage)
            score = logbook_model.boat_score(outcome, damage, int(sub.torpedoes_left), level)
        else:
            won = self.mission_result == "SIEG"
            recorder = self.frigate_debrief
            damage = float(self.damage.total)
            score = int(self.score)
        shots = _events(recorder, "own_shot")
        sunk = _events(recorder, "sub_sunk")
        earned = logbook_model.awards_for(
            won=won, shots=shots, sunk=sunk, damage=damage,
            fired_at=_events(recorder, "enemy_shot") > 0, level=level)
        scenario = ("custom" if self.custom_mission_definition is not None
                    else self.scenario_key)
        book = logbook_model.load_logbook()
        result = book.record(
            date=datetime.date.today().isoformat(), side=side, scenario=scenario,
            level=level, won=won, score=score,
            minutes=max(0, int(self.mission_time // 60)), shots=min(shots, 1000),
            sunk=min(sunk, 100), earned=earned)
        if not logbook_model.save_logbook(book):
            self.flash(message("logbook.save_failed"), 4.0)
            return
        self.logbook_result = result

    def logbook_end_line(self):
        """End-panel line: the side's score, a new best and new awards."""
        result = self.logbook_result
        if result is None:
            return None
        entry = result["entry"]
        parts = [self.tr("logbook.end.score." + entry["side"], score=entry["score"])]
        if result["new_best"]:
            parts.append(self.tr("logbook.end.best"))
        for award in result["awards"]:
            parts.append(self.tr("logbook.award." + award))
        return raw_text(" · ".join(parts))

    # --- the page -------------------------------------------------------------------

    def open_logbook(self) -> None:
        self.logbook_view = logbook_model.load_logbook()
        self.logbook_side = "boat" if getattr(self, "local_side", "frigate") == "uboot" \
            else "frigate"
        self.main_menu = False
        self.menu_screen = LOGBOOK_ENTRY

    def _handle_logbook_key(self, key) -> None:
        if key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_TAB):
            self.logbook_side = "boat" if self.logbook_side == "frigate" else "frigate"
        elif key in (pygame.K_ESCAPE, pygame.K_q, pygame.K_BACKSPACE, pygame.K_RETURN):
            self.logbook_view = None
            self.menu_screen = "scenario"
            self.main_menu = True
            self.main_menu_sel = self.main_menu_index(LOGBOOK_ENTRY)

    def _scenario_label(self, scenario: str) -> str:
        if scenario in config.SCENARIO_NAMES:
            return self.tr("scenario." + config.SCENARIO_NAMES[scenario] + ".title")
        return self.tr("mission.custom")

    def _draw_logbook_page(self, center) -> None:
        s = self.screen
        book = self.logbook_view or logbook_model.Logbook()
        side = self.logbook_side
        center(self.tr("logbook.title." + side), 150, color=config.COLOR_WARN)
        x, w = 180, 920
        missions, wins = book.totals(side)
        layout.blit_line(s, message("logbook.totals", missions=missions, wins=wins),
                         (x, 180, w, 26), config.COLOR_TEXT, size=20)
        # Best scores per scenario.
        layout.blit_line(s, "logbook.best", (x, 214, 440, 24), config.COLOR_TEXT_DIM, size=18)
        best = sorted((key.partition(":")[2], value) for key, value in book.best.items()
                      if key.startswith(side + ":"))
        y = 240
        for scenario, score in best[:7]:
            layout.blit_line(s, message("logbook.best_row", scenario=self._scenario_label(scenario),
                                        score=score), (x, y, 440, 24), config.COLOR_TEXT, size=18)
            y += 24
        if not best:
            layout.blit_line(s, "logbook.none", (x, y, 440, 24), config.COLOR_TEXT_DIM, size=18)
        # Awards of this side, earned or still open.
        ax = x + 470
        layout.blit_line(s, "logbook.awards", (ax, 214, 450, 24), config.COLOR_TEXT_DIM, size=18)
        y = 240
        for award in logbook_model.AWARDS:
            date = book.awards.get(f"{side}:{award}")
            text = (message("logbook.award_earned", award=self.tr("logbook.award." + award),
                            date=raw_text(date)) if date
                    else message("logbook.award_open", award=self.tr("logbook.award." + award)))
            layout.blit_line(s, text, (ax, y, 450, 24),
                             config.COLOR_OK if date else config.COLOR_TEXT_DIM, size=18)
            layout.blit_line(s, "logbook.award_hint." + award, (ax + 16, y + 22, 434, 20),
                             config.COLOR_TEXT_DIM, size=14)
            y += 46
        # The latest missions.
        y = 480
        layout.blit_line(s, "logbook.recent", (x, y, w, 24), config.COLOR_TEXT_DIM, size=18)
        rows = [row for row in book.entries if row["side"] == side][-RECENT_ROWS:]
        for row in reversed(rows):
            y += 24
            layout.blit_line(s, message(
                "logbook.row", date=raw_text(row["date"]),
                scenario=self._scenario_label(row["scenario"]),
                level=self.tr("level." + row["level"]),
                result=self.tr("logbook.won" if row["won"] else "logbook.lost"),
                score=row["score"], minutes=row["minutes"]),
                (x, y, w, 24), config.COLOR_TEXT if row["won"] else config.COLOR_TEXT_DIM,
                size=18)
        if not rows:
            layout.blit_line(s, "logbook.none", (x, y + 24, w, 24), config.COLOR_TEXT_DIM,
                             size=18)
        center(self.tr("logbook.hint"), 608, color=config.COLOR_TEXT_DIM, keys=("→", "Esc"))
