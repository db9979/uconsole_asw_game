"""The service record and the training lessons for the browser's host surface.

The solo browser (or the server-mode leader) reads the logbook (``logbook.json``:
missions, best scores, awards, a ribbon per scenario, what the enemy learnt)
and the list of training lessons with their tick marks through the host view,
as the uConsole's main menu shows them. Only the player's own record and fixed lesson names go out: no save
data, no mission state. The logbook file is re-read only when its size or
modification time changes (checked with the save slots, every 2 s).
"""

from __future__ import annotations

import os

from src.core import daily, habits, logbook, training

LOGBOOK_BEST_MAX = 12
LOGBOOK_RECENT_MAX = 8
LOGBOOK_RIBBONS_MAX = 32
LOGBOOK_SIDES = ("frigate", "boat")
LOGBOOK_MARKS = ("advisor", "experimental")


def logbook_stamp():
    """(size, mtime_ns) of the logbook file, or None without one."""
    try:
        info = os.stat(logbook.logbook_path())
    except OSError:
        return None
    return (info.st_size, info.st_mtime_ns)


def _date(value):
    return None if value is None else str(value)[:16]


def _side(book, side: str, learns: bool) -> dict:
    missions, wins = book.totals(side)
    best = sorted((key.partition(":")[2], value) for key, value in book.best.items()
                  if key.startswith(side + ":")
                  and not daily.is_daily_key(key.partition(":")[2]))[:LOGBOOK_BEST_MAX]
    rows = [row for row in book.entries if row["side"] == side][-LOGBOOK_RECENT_MAX:]
    return dict(
        missions=int(missions), wins=int(wins),
        best=[dict(scenario=str(scenario)[:64], score=int(score)) for scenario, score in best],
        awards=[dict(award=award, date=_date(book.awards.get(f"{side}:{award}")))
                for award in logbook.AWARDS],
        recent=[dict(date=str(row["date"])[:16], scenario=str(row["scenario"])[:64],
                     level=row["level"],
                     won=bool(row["won"]), score=int(row["score"]),
                     minutes=int(row["minutes"]),
                     marks=[mark for mark in LOGBOOK_MARKS if row.get(mark)])
                for row in reversed(rows)],
        known=list(habits.known(book.entries, side)) if learns else [],
        ribbons=[dict(scenario=str(scenario)[:64], won=bool(won))
                 for scenario, won in book.ribbons(side)][:LOGBOOK_RIBBONS_MAX])


def logbook_view(book, learns: bool) -> dict:
    """The host view's ``logbook`` block: both sides of the service record."""
    return dict(learns=bool(learns),
                sides={side: _side(book, side, bool(learns)) for side in LOGBOOK_SIDES})


def lessons_view(done=()) -> list:
    """The training lessons in menu order, each with the side it teaches,
    whether it was finished once and whether it is the next one to take."""
    done = training.valid_done(done)
    upcoming = training.next_lesson(done)
    return [dict(key=lesson, side=training.side_of(lesson), done=lesson in done,
                 next=lesson == upcoming) for lesson in training.LESSONS]
