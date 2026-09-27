"""Guided training missions: short lessons with step hints.

Each lesson is an ordinary authored mission (``lesson_definition``) run by
the custom-mission runtime, plus a list of steps.  A step names what the
player should do next and a check that reads the game's operator-facing
state (station, own orders, sonar contacts, weapons in the water).  The
coach advances as soon as a check holds, so it never needs saved state: a
loaded lesson starts again at step 1 and passes the steps that are already
true within a moment.

Lessons 1, 2 and 4 place their submarine as a neutral boat so it never
fires at the student; lesson 3 is a real (hostile) attack and ends with the
mission's sink objective.
"""

from __future__ import annotations

from src.core import config
from src.core.station import Station

LESSONS = ("sonar", "tma", "attack", "helo")
KEY_PREFIX = "user.training-"


def _contacts(game):
    return list(game.sonar.active_contacts())


def _any_contact(game) -> bool:
    return bool(_contacts(game))


def _classified(game) -> bool:
    return any(contact.player_class == "U_BOOT" for contact in _contacts(game))


def _leg_changed(game, coach) -> bool:
    return abs(config.angle_diff_deg(game.ship.course, coach.start_course)) >= 30.0


def _tma_solution(game) -> bool:
    return any(contact.range_source == "tma" or contact.tma_quality >= 0.5
               for contact in _contacts(game))


def _range_known(game) -> bool:
    return any(contact.range_est is not None for contact in _contacts(game))


# Each step: (hint key, check(game, coach) -> bool).
STEPS = {
    "sonar": (
        ("training.step.go_sonar", lambda g, c: g.station is Station.SONAR),
        ("training.step.contact", lambda g, c: _any_contact(g)),
        ("training.step.follow", lambda g, c: bool(g.sonar.focus_locked)),
        ("training.step.classify", lambda g, c: _classified(g)),
    ),
    "tma": (
        ("training.step.go_sonar", lambda g, c: g.station is Station.SONAR),
        ("training.step.contact", lambda g, c: _any_contact(g)),
        ("training.step.tma_on", lambda g, c: bool(g.sonar.tma_enabled)),
        ("training.step.leg", _leg_changed),
        ("training.step.solution", lambda g, c: _tma_solution(g)),
    ),
    "attack": (
        ("training.step.contact", lambda g, c: _any_contact(g)),
        ("training.step.range", lambda g, c: _range_known(g)),
        ("training.step.classify", lambda g, c: _classified(g)),
        ("training.step.designate", lambda g, c: g.target is not None),
        ("training.step.go_weapons", lambda g, c: g.station is Station.WEAPONS),
        ("training.step.fire", lambda g, c: bool(g.torpedoes)),
        ("training.step.hit", lambda g, c: g.game_over),
    ),
    "helo": (
        ("training.step.go_helo", lambda g, c: g.station is Station.HELICOPTER),
        ("training.step.launch", lambda g, c: g.helo.airborne),
        ("training.step.buoy", lambda g, c: any(
            getattr(buoy, "owner", "HELO") == "HELO" for buoy in g.buoys)),
        ("training.step.buoy_contact", lambda g, c: any(
            contact.buoy_reports for contact in _contacts(g))),
        ("training.step.classify", lambda g, c: _classified(g)),
    ),
}

# Where the boat lies from the ship (east, north in NM), how it moves.
_SETUP = {
    "sonar": dict(offset=(5.0, -3.0), course=90.0, speed=5.0, side="neutral"),
    "tma": dict(offset=(7.0, -5.0), course=200.0, speed=6.0, side="neutral"),
    "attack": dict(offset=(3.0, -3.0), course=120.0, speed=5.0, side="hostile"),
    "helo": dict(offset=(-9.0, -6.0), course=60.0, speed=4.0, side="neutral"),
}
PLAYER = (250.0, 250.0)


def lesson_key(lesson: str) -> str:
    return KEY_PREFIX + lesson


def lesson_of(definition) -> str | None:
    """The lesson a (saved) mission definition belongs to, if any."""
    if not isinstance(definition, dict):
        return None
    key = definition.get("key")
    if type(key) is not str or not key.startswith(KEY_PREFIX):
        return None
    lesson = key[len(KEY_PREFIX):]
    return lesson if lesson in LESSONS else None


def lesson_definition(lesson: str, seed: int) -> dict:
    """The authored mission of one lesson (validated like any user mission)."""
    setup = _SETUP[lesson]
    px, py = PLAYER
    sub = dict(id="boat", profile="diesel_alt", side=setup["side"],
               placement=dict(kind="fixed", x=px + setup["offset"][0],
                              y=py + setup["offset"][1]),
               course_deg=setup["course"], speed_kn=setup["speed"], depth_m=60.0)
    objective = (dict(type="sink", target_ids=["boat"], time_limit_s=7200.0)
                 if setup["side"] == "hostile"
                 else dict(type="survive", target_ids=[], time_limit_s=7200.0))
    return {
        "version": 1,
        "key": lesson_key(lesson),
        "name": "Training " + str(LESSONS.index(lesson) + 1),
        "description": "Guided lesson",
        "seed": int(seed),
        "world": {"kind": "fixed", "size_nm": config.WORLD_SIZE_NM, "sectors": []},
        "player": {"x": px, "y": py, "course_deg": 0.0, "speed_kn": 6.0},
        "environment": {"sea_state": 2, "time_hour": 12.0,
                        "thermocline_depth_m": 150.0, "weather": "clear"},
        "units": {"exact": [sub], "random_groups": []},
        "objective": objective,
        "events": [],
    }


class TrainingCoach:
    """The current lesson's step (not saved; see the module note)."""

    def __init__(self, lesson: str, start_course: float):
        if lesson not in LESSONS:
            raise ValueError(lesson)
        self.lesson = lesson
        self.start_course = float(start_course)
        self.step = 0
        self.done = False

    @property
    def steps(self):
        return STEPS[self.lesson]

    def hint_key(self) -> str:
        return "training.done" if self.done else self.steps[self.step][0]

    def advance(self, game) -> list[str]:
        """Pass every step whose check holds; returns the passed hint keys."""
        passed = []
        while not self.done and self.steps[self.step][1](game, self):
            passed.append(self.steps[self.step][0])
            self.step += 1
            if self.step >= len(self.steps):
                self.done = True
        return passed
