"""Same seed, second game in the same process: identical course.

Entity ids come from process-global class counters that ``reset()`` does not
rewind, so a stateless draw keyed on an entity id differs between two games
with the same seed. Draws are keyed on the entity's saved ``sensor_seed``."""

import re
from pathlib import Path

from src.core.game import Game

ROOT = Path(__file__).resolve().parents[1]
SEED = 77


def _game(scenario="s2_doppeljagd"):
    game = Game(seed=SEED, start_menu=False, audio_enabled=False)
    game.reset(SEED, scenario)
    return game


def _run(game, seconds, dt=0.25):
    end = game.sim_t + seconds
    while game.sim_t < end - 1e-9 and not game.game_over:
        game._update_sim(dt)


def _snap(game):
    def r(value):
        return round(float(value), 5)
    return dict(
        ship=(r(game.ship.x), r(game.ship.y), r(game.ship.course), r(game.ship.speed)),
        subs=[(s.sensor_seed, r(s.x), r(s.y), r(s.depth), s.state, s.torpedoes_left)
              for s in game.subs],
        civilians=[(c.sensor_seed, r(c.x), r(c.y), c.sunk) for c in game.civilians],
        air=sorted((t.kind, t.source, r(t.bearing), r(t.range_nm or -1.0))
                   for t in game.air_picture.tracks(game.sim_t)),
        sonar=sorted(r(c.bearing) for c in game.sonar.contacts.values()),
        score=game.score,
    )


def _sweep(game):
    for number, ship in enumerate(game.civilians + game.warships):
        game.sim_t = 8.0 + 2.0 * number
        game._airborne_radar_sweep(2.0, ship.x + 8.0, ship.y, 3000.0, 60.0,
                                   "mpa-radar-", "M-", "RADAR-MPA")
    return sorted((round(t.bearing, 6), round(t.range_nm, 6))
                  for t in game.air_picture.tracks(game.sim_t)
                  if t.source == "RADAR-MPA")


def test_second_game_with_same_seed_runs_identically():
    first = _game()
    first.toggle_crew_assist()
    first.request_mpa()
    _run(first, 120.0)
    second = _game()
    second.toggle_crew_assist()
    second.request_mpa()
    _run(second, 120.0)
    assert [s.id for s in second.subs] != [s.id for s in first.subs]
    assert _snap(first) == _snap(second)


def test_airborne_radar_draws_do_not_depend_on_entity_ids():
    first, second = _game(), _game()
    assert [c.id for c in second.civilians] != [c.id for c in first.civilians]
    tracks = _sweep(first)
    assert tracks and tracks == _sweep(second)


def test_boat_draws_do_not_depend_on_entity_ids():
    first, second = _game(), _game()
    for a, b in zip(first.subs, second.subs):
        assert a.id != b.id and a.sensor_seed == b.sensor_seed
        a.memory["contact"] = b.memory["contact"] = object()
        a.memory["contact_age"] = b.memory["contact_age"] = 0.0
        a.depth = b.depth = 10.0
        for now in range(0, 7200, 50):
            assert (a.contact_report_on_air(SEED, float(now))
                    == b.contact_report_on_air(SEED, float(now)))


def test_no_stateless_draw_is_keyed_on_an_entity_id():
    """Lint: ``detrand.*(..., x.id, ...)`` would bring the bug back. Sonar
    contact ids are numbered per game (``Sonar._next_contact_id``)."""
    allowed = {"contact.id"}
    pattern = re.compile(r"detrand\.\w+\((?:[^()]|\([^()]*\))*?\b\w+\.id\b", re.S)
    offenders = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        offenders += [f"{path.relative_to(ROOT)}:{text.count(chr(10), 0, m.start()) + 1}"
                      for m in pattern.finditer(text)
                      if m.group(0).rsplit(",", 1)[-1].strip() not in allowed]
    assert offenders == []
