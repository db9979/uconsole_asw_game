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
mission's sink objective.  The defence lessons place no submarine: in the
air-defence lesson the coach launches one sea-skimming missile at the ship
(``lesson_missile_due``; another one while the student has not yet fired an
ESSM and none is in the air), the ESM lesson places a merchant whose
navigation radar the ESM hears, and the torpedo lesson a hostile torpedo
already running at the ship, against which the student streams the Nixie.

A finished lesson is remembered in the settings (``lessons_done``) for the
tick marks of the training page and its "next lesson".

The boat lessons (``BOAT_LESSONS``) put the uConsole on the submarine: the
student crews the lesson's boat and the frigate follows a plain script
(course and speed, and in the evasion lesson active pings: every
``BOAT_PING_INTERVAL_S`` until the evasion order, afterwards only while its
own sonar still holds the boat).  Their checks read the boat's own picture.
"""

from __future__ import annotations

from src.core import boat_threat, config
from src.core.station import Station

FRIGATE_LESSONS = ("sonar", "tma", "attack", "helo", "air", "esm", "torpedo")
BOAT_LESSONS = ("boat_listen", "boat_evade")
LESSONS = FRIGATE_LESSONS + BOAT_LESSONS
KEY_PREFIX = "user.training-"
# The scripted frigate of the evasion lesson pings this often (s).
BOAT_PING_INTERVAL_S = 45.0
# The air-defence lesson: the first missile this long after the start, a
# further one this long after the last has gone, from this far off.
MISSILE_FIRST_S = 40.0
MISSILE_AGAIN_S = 30.0
MISSILE_RANGE_NM = 20.0
MISSILE_BEARING_DEG = 60.0
# The torpedo lesson's speed orders (``config.TELEGRAPH_ORDERS`` indices):
# HALF or FULL. At SLOW the Nixie does not draw the torpedo off the ship,
# at FLANK the torpedo still finds the ship (measured, lesson setup).
NIXIE_ORDERS = (2, 3)


def side_of(lesson: str) -> str:
    """The side the uConsole plays in a lesson."""
    return "uboot" if lesson in BOAT_LESSONS else "frigate"


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


def _missile_tracks(game) -> bool:
    return bool(game.asm_tracks())


def _essm_fired(game) -> bool:
    return game.essm_seq > 0


def missiles_alive(game) -> bool:
    return any(asm.state in ("LAUF", "CHAFF") for asm in game.asms)


def _missile_down(game, coach) -> bool:
    """The lesson's last missile was shot down (it did not hit the ship)."""
    return coach.missile_result == "down" and not missiles_alive(game)


def _esm_intercept(game) -> bool:
    return bool(game.eloka_tracks())


def _esm_annotated(game) -> bool:
    return bool(game.eloka_annotations)


def _torpedo_heard(game) -> bool:
    return bool(game.torpedo_warnings(held=False))


def _nixie_speed(game) -> bool:
    """HALF or FULL ordered, the speed the Nixie works at."""
    return not game.ship.astern and game.ship.order_idx in NIXIE_ORDERS


def _torpedoes_gone(game) -> bool:
    return not game.enemy_torpedoes and not game.damage.ship_sunk


def _boat(game):
    return game.opfor if getattr(game, "local_side", "frigate") == "uboot" else None


def _boat_contacts(game):
    boat = _boat(game)
    return [] if boat is None else list(boat.station.sonar.active_contacts())


def _boat_sonar(game) -> bool:
    return _boat(game) is not None and game.station is Station.SONAR


def _boat_warship(game) -> bool:
    return any(contact.player_class == "KAMPFSCHIFF" for contact in _boat_contacts(game))


def _boat_layer(game) -> str:
    boat = _boat(game)
    return "unknown" if boat is None else boat_threat.layer_state(boat)[0]


def _boat_threat_page(game) -> bool:
    from src.ui import uboot_view
    boat = _boat(game)
    return boat is not None and uboot_view.page_name(game, boat) == "UBOOT_THREAT"


def _boat_pinged(game) -> bool:
    boat = _boat(game)
    return boat is not None and any(row["kind"] in ("hull", "dipping", "buoy")
                                    for row in boat.intercepts)


def _boat_evaded(game) -> bool:
    boat = _boat(game)
    return boat is not None and boat.evaded_t is not None


def _boat_quiet_deep(game) -> bool:
    boat = _boat(game)
    if boat is None:
        return False
    sub = boat.sub
    return boat.orders.quiet_active(sub) and sub.depth >= 100.0


def _boat_shaken_off(game) -> bool:
    boat = _boat(game)
    return boat is not None and boat_threat.alarm_source(boat) is None


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
        # Only a won lesson counts as hit; a lost one never logs this step.
        ("training.step.hit", lambda g, c: g.game_over and g.mission_result == "SIEG"),
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
    "air": (
        ("training.step.go_opz", lambda g, c: g.station is Station.OPZ),
        ("training.step.missile", lambda g, c: _missile_tracks(g)),
        ("training.step.essm", lambda g, c: _essm_fired(g)),
        ("training.step.missile_down", _missile_down),
    ),
    "esm": (
        ("training.step.go_eloka", lambda g, c: g.station is Station.ELOKA),
        ("training.step.intercept", lambda g, c: _esm_intercept(g)),
        ("training.step.annotate", lambda g, c: _esm_annotated(g)),
        ("training.step.esm_opz", lambda g, c: g.station is Station.OPZ),
    ),
    "torpedo": (
        ("training.step.torpedo_heard", lambda g, c: _torpedo_heard(g)),
        ("training.step.go_weapons", lambda g, c: g.station is Station.WEAPONS),
        ("training.step.nixie", lambda g, c: bool(g.nixies)),
        ("training.step.nixie_speed", lambda g, c: _nixie_speed(g)),
        ("training.step.torpedo_gone", lambda g, c: _torpedoes_gone(g)),
    ),
    "boat_listen": (
        ("training.step.boat_sonar", lambda g, c: _boat_sonar(g)),
        ("training.step.boat_contact", lambda g, c: bool(_boat_contacts(g))),
        ("training.step.boat_classify", lambda g, c: _boat_warship(g)),
        ("training.step.boat_bt", lambda g, c: _boat_layer(g) != "unknown"),
        ("training.step.boat_below", lambda g, c: _boat_layer(g) == "below"),
    ),
    "boat_evade": (
        ("training.step.boat_threat_page", lambda g, c: _boat_threat_page(g)),
        ("training.step.boat_pinged", lambda g, c: _boat_pinged(g)),
        ("training.step.boat_evade", lambda g, c: _boat_evaded(g)),
        ("training.step.boat_quiet", lambda g, c: _boat_quiet_deep(g)),
        ("training.step.boat_shaken", lambda g, c: _boat_shaken_off(g)),
    ),
}

# Where the boat lies from the ship (east, north in NM), how it moves.
_SETUP = {
    "sonar": dict(offset=(5.0, -3.0), course=90.0, speed=5.0, side="neutral"),
    "tma": dict(offset=(7.0, -5.0), course=200.0, speed=6.0, side="neutral"),
    "attack": dict(offset=(3.0, -3.0), course=120.0, speed=5.0, side="hostile"),
    "helo": dict(offset=(-9.0, -6.0), course=60.0, speed=4.0, side="neutral"),
    # The defence lessons: a merchant for the ESM, a torpedo running at the
    # ship (aimed ahead of it); the air-defence lesson places nothing.
    "air": dict(units=(), ship_speed=12.0),
    "esm": dict(units=(dict(id="merchant", profile="cargo_01", side="neutral",
                            offset=(14.0, -9.0), course=250.0, speed=10.0),),
                ship_speed=10.0),
    "torpedo": dict(units=(dict(id="torpedo", profile="enemy_torp", side="hostile",
                                offset=(3.0, -2.0), course=262.0, speed=40.0,
                                depth=20.0),),
                    ship_speed=6.0),
    # The boat lessons: the crewed boat is the lesson's (hostile) boat.
    "boat_listen": dict(offset=(4.0, -6.0), course=270.0, speed=3.0, side="hostile",
                        depth=50.0, layer=80.0, ship_speed=8.0),
    "boat_evade": dict(offset=(2.0, -3.0), course=180.0, speed=3.0, side="hostile",
                       depth=50.0, layer=80.0, ship_speed=8.0, ship_course=90.0),
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
    if "units" in setup:
        units = [dict(id=row["id"], profile=row["profile"], side=row["side"],
                      placement=dict(kind="fixed", x=px + row["offset"][0],
                                     y=py + row["offset"][1]),
                      course_deg=row["course"], speed_kn=row["speed"],
                      depth_m=row.get("depth", 0.0))
                 for row in setup["units"]]
        objective = dict(type="survive", target_ids=[], time_limit_s=7200.0)
    else:
        units = [dict(id="boat", profile="diesel_alt", side=setup["side"],
                      placement=dict(kind="fixed", x=px + setup["offset"][0],
                                     y=py + setup["offset"][1]),
                      course_deg=setup["course"], speed_kn=setup["speed"],
                      depth_m=setup.get("depth", 60.0))]
        objective = (dict(type="sink", target_ids=["boat"], time_limit_s=7200.0)
                     if setup["side"] == "hostile" and lesson not in BOAT_LESSONS
                     else dict(type="survive", target_ids=[], time_limit_s=7200.0))
    return {
        "version": 1,
        "key": lesson_key(lesson),
        "name": "Training " + str(LESSONS.index(lesson) + 1),
        "description": "Guided lesson",
        "seed": int(seed),
        "world": {"kind": "fixed", "size_nm": config.WORLD_SIZE_NM, "sectors": []},
        "player": {"x": px, "y": py, "course_deg": setup.get("ship_course", 0.0),
                   "speed_kn": setup.get("ship_speed", 6.0)},
        "environment": {"sea_state": 2, "time_hour": 12.0,
                        "thermocline_depth_m": setup.get("layer", 150.0),
                        "weather": "clear"},
        "units": {"exact": units, "random_groups": []},
        "objective": objective,
        "events": [],
    }


def next_lesson(done) -> str | None:
    """The first lesson not yet done, in menu order (None: all done)."""
    return next((lesson for lesson in LESSONS if lesson not in done), None)


def following(lesson: str) -> str | None:
    """The lesson after ``lesson`` in menu order, or None after the last."""
    index = LESSONS.index(lesson)
    return LESSONS[index + 1] if index + 1 < len(LESSONS) else None


def valid_done(value) -> tuple:
    """Lessons done from the settings: known lessons, menu order, no repeats."""
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(lesson for lesson in LESSONS if lesson in value)


class TrainingCoach:
    """The current lesson's step (not saved; see the module note)."""

    def __init__(self, lesson: str, start_course: float):
        if lesson not in LESSONS:
            raise ValueError(lesson)
        self.lesson = lesson
        self.start_course = float(start_course)
        self.step = 0
        self.done = False
        self.next_ping_t = 0.0      # the evasion lesson's scripted frigate
        # The air-defence lesson's missile: in the air at the last look,
        # how the last one ended ("down" or "hit"), the damage before it.
        self.missile_alive = False
        self.missile_result = None
        self.damage_at_launch = 0.0

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


def frigate_should_ping(game, coach) -> bool:
    """The evasion lesson's frigate: search pings, then only while they echo.

    Until the evasion order it pings on a fixed interval; afterwards it sends
    one more ping and keeps pinging only while its last ping still returned
    an echo from the boat (its own sonar), so a boat that got out of the
    beam and below the layer is lost.
    """
    if coach.lesson != "boat_evade" or coach.done or game.sim_t < coach.next_ping_t:
        return False
    boat = _boat(game)
    if boat is None or boat.sub.sunk:
        return False
    if boat.evaded_t is None or coach.next_ping_t <= boat.evaded_t:
        return True
    window = BOAT_PING_INTERVAL_S + 15.0
    return any(contact.target_id == boat.sub.id and contact.range_source == "ping"
               and 0.0 <= game.sim_t - contact.range_seen <= window
               for contact in game.sonar.active_contacts())


def lesson_missile_due(game, coach) -> bool:
    """The air-defence lesson launches a missile: the first
    ``MISSILE_FIRST_S`` into the lesson, then, until one is shot down after
    the student fired an ESSM, another ``MISSILE_AGAIN_S`` after the last
    has gone (shot down by the CIWS or the chaff, or hit)."""
    if coach.lesson != "air" or coach.done or game.game_over or missiles_alive(game):
        return False
    if game.asm_seq == 0:
        return game.mission_time >= MISSILE_FIRST_S
    return game.sim_t >= coach.next_ping_t
