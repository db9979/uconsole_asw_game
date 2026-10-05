"""Saves the nightly soak found refused (tools/soak_game.py diagnose_load).

Each case is a game state the simulation reaches on its own that the strict
validator used to reject, so "Continue" or a slot would not load.
"""

import json

from src.core.game import Game
from src.sensors.platform import SONAR_SIGNAL_MAX


def _game(scenario="s3_abfang", seed=20261003):
    game = Game(seed=seed, start_menu=False, show_splash=False, audio_enabled=False,
                language="en")
    assert game.start_new_game(scenario, "fixed", seed=seed)
    for _ in range(30):
        game.update(0.1)
    return game


def _reloads(game) -> bool:
    document = json.loads(json.dumps(game.save_state(), allow_nan=False))
    twin = Game(seed=1, start_menu=True, show_splash=False, audio_enabled=False,
                language="en")
    return twin._load_save_data(document)


def test_a_boat_remembering_a_loud_contact_saves_and_loads():
    # Soak s3_abfang/frigate t=326 s: an AI boat's solution remembered the
    # received signal 1.29, above the frigate's own noise figure (1.17) the
    # validator wrongly used as the bound; the signal reaches SONAR_SIGNAL_MAX.
    game = _game()
    sub = next(sub for sub in game.subs if not sub.sunk)
    sub.memory["contact"] = dict(x=sub.x + 3.0, y=sub.y, speed=15.0, course=269.0,
                                 noise=SONAR_SIGNAL_MAX)
    sub.memory["contact_age"] = 0.0
    assert _reloads(game)


def test_a_contact_noise_above_the_signal_limit_is_still_refused():
    game = _game()
    sub = next(sub for sub in game.subs if not sub.sunk)
    sub.memory["contact"] = dict(x=sub.x + 3.0, y=sub.y, speed=15.0, course=269.0,
                                 noise=SONAR_SIGNAL_MAX + 0.5)
    assert not _reloads(game)


def _loads(document) -> bool:
    twin = Game(seed=1, start_menu=True, show_splash=False, audio_enabled=False,
                language="en")
    return twin._load_save_data(json.loads(json.dumps(document)))


def test_broken_flight_waypoints_and_sub_start_are_refused():
    # Found by fuzzing: these loaded and crashed the simulation later.
    game = _game()
    document = json.loads(json.dumps(game.save_state(), allow_nan=False))
    assert document["flights"]["items"] and document["subs"]
    assert _loads(document)
    for bad in ([[1.0]], [["a", "b"]], [[1.0, 2.0, 3.0]], "xy", [[1e300, 0.0]],
                [[0.0, 0.0]] * 17):
        broken = json.loads(json.dumps(document))
        broken["flights"]["items"][0]["waypoints"] = bad
        assert not _loads(broken), bad
    broken = json.loads(json.dumps(document))
    flight = broken["flights"]["items"][0]
    flight["waypoints"] = [[1.0, 2.0], [3.0, 4.0]]
    flight["waypoint_idx"] = 5
    assert not _loads(broken)
    for bad in (None, [1.0], ["a", 2.0], [1.0, 2.0, 3.0], 7):
        broken = json.loads(json.dumps(document))
        broken["subs"][0]["start_pos"] = bad
        assert not _loads(broken), bad
