"""Player torpedoes are guided by a datum only, never by the hidden target.

Every launch site passes a commanded datum, a save with a running torpedo
without one is rejected, and the no-datum path of ``Torpedo`` and
``Helicopter.drop_torpedo`` no longer reads the target object.
"""

import ast
import copy
import pathlib
import random

from src.air.helicopter import Helicopter
from src.core.game import Game
from src.core.save_validate import valid_save_document
from src.weapons.torpedo import Torpedo

ROOT = pathlib.Path(__file__).resolve().parents[1]


class _HiddenTarget:
    """A target whose truth must not be read: any attribute access fails."""

    def __getattr__(self, name):
        raise AssertionError(f"hidden target read: {name}")


def _calls(name):
    """Every call ``name(...)`` or ``obj.name(...)`` in the source tree."""
    found = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            called = (func.id if isinstance(func, ast.Name)
                      else func.attr if isinstance(func, ast.Attribute) else None)
            if called == name:
                found.append((path.relative_to(ROOT), node))
    return found


def test_every_player_torpedo_launch_passes_a_datum():
    for name in ("Torpedo", "drop_torpedo"):
        calls = _calls(name)
        assert calls, name
        for path, node in calls:
            keywords = {keyword.arg for keyword in node.keywords}
            assert {"guidance_x", "guidance_y"} <= keywords, (path, node.lineno)


def test_a_saved_running_torpedo_needs_its_datum():
    from src.sonar.sonar import Contact

    game = Game(seed=402, start_menu=False, audio_enabled=False)
    sub = game.subs[0]
    contact = Contact(41, sub.id, "passiv", "sub")
    contact.update_passive(90.0, 1.0, .8, "", game.sim_t)
    contact.range_est, contact.range_source, contact.range_seen = 5.0, "ping", game.sim_t
    contact.observed_x, contact.observed_y = game.ship.x + 5.0, game.ship.y
    contact.player_class = "U_BOOT"
    game.sonar.contacts[sub.id] = contact
    game.roe = "FREE"
    assert game.launch_torpedo_at(contact, 60.0) is True
    assert game.torpedoes[-1].guidance_x is not None
    data = game.save_state()
    assert valid_save_document(copy.deepcopy(data))
    for field in ("guidance_x", "guidance_y"):
        broken = copy.deepcopy(data)
        broken["torpedoes_in_flight"][0][field] = None
        assert not valid_save_document(broken)


def test_torpedo_without_datum_holds_course_without_reading_the_target():
    torpedo = Torpedo(0.0, 0.0, 45.0, 50.0, _HiddenTarget(), 1,
                      time_since_launch=None)
    for _ in range(40):
        torpedo.update(0.5, seeker_candidates=[])
    assert torpedo.state == "RUN"
    assert not torpedo.terminal_active and not torpedo.seeker_acquired
    assert torpedo.guidance_distance_nm() == float("inf")
    # The serpentine search wanders around the launch course only.
    assert abs(((torpedo.course - 45.0 + 180.0) % 360.0) - 180.0) < 20.0


def test_helicopter_drop_without_datum_never_aims_at_the_target():
    helicopter = Helicopter(random.Random(1))
    helicopter.state = "AUF"
    helicopter.course = 123.0
    torpedo = helicopter.drop_torpedo(_HiddenTarget(), 50.0, 1)
    assert torpedo is not None
    assert torpedo.course == 123.0
    assert torpedo.guidance_x is None and torpedo.guidance_y is None


def test_helicopter_drop_with_datum_aims_at_the_datum():
    helicopter = Helicopter(random.Random(1))
    helicopter.state = "AUF"
    helicopter.x, helicopter.y = 10.0, 10.0
    torpedo = helicopter.drop_torpedo(_HiddenTarget(), 50.0, 1,
                                      guidance_x=11.0, guidance_y=10.0)
    assert torpedo.course == 90.0
    assert (torpedo.guidance_x, torpedo.guidance_y) == (11.0, 10.0)
