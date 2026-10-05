"""An AI submarine runs from the torpedo it heard, not from the frigate (save v53)."""

import json
import math
import random

from src.core import save_migrate
from src.core.game import Game
from src.enemies.sub import Sub


class _World:
    size_nm = 500.0

    def thermocline_depth_m(self, x, y):
        return 60.0

    def on_land(self, x, y):
        return False

    def depth_m(self, x, y):
        return 1000.0

    def sonar_path_blocked(self, *args):
        return False


def test_an_ai_submarine_opens_the_range_to_a_torpedo_from_another_bearing():
    sub = Sub(250.0, 250.0, 80.0, 90.0, "aip_modern", random.Random(3))
    # The frigate is heard to the north, the torpedo comes from the south.
    sub.memory["contact_bearing"] = 0.0
    sub.memory["contact_age"] = 0.0
    torpedo = (250.0, 251.0)
    sub.alert_torpedo(source=torpedo)
    assert sub.torpedo_threat_bearing == 180.0
    start = math.hypot(sub.x - torpedo[0], sub.y - torpedo[1])
    world = _World()
    for _ in range(int(120 / 0.1)):
        sub.update(0.1, None, world)
    assert math.hypot(sub.x - torpedo[0], sub.y - torpedo[1]) > start


def test_the_threat_bearing_survives_save_and_load():
    game = Game(seed=11, start_menu=False, show_splash=False, audio_enabled=False,
                language="en")
    assert game.start_new_game("s2_doppeljagd", "fixed", seed=11)
    sub = game.subs[0]
    sub.torpedo_threat_bearing = 123.5
    state = json.loads(json.dumps(game.save_state(), allow_nan=False))
    assert state["subs"][0]["torpedo_threat_bearing"] == 123.5
    other = Game(seed=1, start_menu=False, show_splash=False, audio_enabled=False,
                 language="en")
    assert other._load_save_data(state)
    assert other.subs[0].torpedo_threat_bearing == 123.5


def test_a_v52_save_lifts_with_no_heard_torpedo():
    doc = {"version": 52, "save_schema": "u-jagd-save-v52",
           "subs": [{"id": 1}, {"id": 2}]}
    lifted = save_migrate.migrate(doc)
    assert lifted["version"] == 53
    assert [row["torpedo_threat_bearing"] for row in lifted["subs"]] == [None, None]
