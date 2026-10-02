"""A homing torpedo's terminal phase is audible: ping rate, steady bearing, clock."""

import pytest

from src.core import config, torpedo_seeker
from src.core.game import Game
from src.core.i18n import localize
from src.sensors import threat_cue


def test_locked_seeker_pings_four_times_faster():
    counts = {}
    for acquired in (False, True):
        ear = torpedo_seeker.SeekerEar()
        events = []
        for step in range(81):
            events += ear.hear(7, 90.0 + step * 2.0, step * 0.25, acquired)
        counts[acquired] = events.count("ping")
    assert counts[False] in (9, 10)
    assert 39 <= counts[True] <= 40


def test_steady_bearing_is_reported_once_and_a_drifting_one_never():
    steady, drifting = torpedo_seeker.SeekerEar(), torpedo_seeker.SeekerEar()
    calls_steady, calls_drift = [], []
    for step in range(120):
        t = step * 0.25
        calls_steady += steady.hear(1, 359.8 + 0.2 * (step % 2), t, True)
        calls_drift += drifting.hear(1, 40.0 + 1.5 * t, t, True)
    assert calls_steady.count("steady") == 1
    assert "steady" not in calls_drift


def test_bearing_rate_unwraps_north():
    rows = [(t, (358.0 + 0.5 * t) % 360.0) for t in range(12)]
    assert torpedo_seeker.bearing_rate(rows) == pytest.approx(0.5)
    assert torpedo_seeker.bearing_rate(rows[:4]) is None


def test_ear_forgets_torpedoes_no_longer_heard():
    ear = torpedo_seeker.SeekerEar()
    ear.hear(1, 10.0, 0.0, False)
    ear.hear(2, 20.0, 0.0, False)
    ear.forget([2])
    assert set(ear.ticks) == {2} and set(ear.samples) == {2}


def test_clock_is_rough_deterministic_and_bounded():
    a = torpedo_seeker.estimated_tti(1.0, 11, 5, 12.0)
    assert a == torpedo_seeker.estimated_tti(1.0, 11, 5, 13.0)
    exact = 1.0 / (torpedo_seeker.ASSUMED_KN / 3600.0)
    assert 0.3 * exact <= a <= 3.0 * exact
    assert torpedo_seeker.estimated_tti(500.0, 11, 5, 0.0) == torpedo_seeker.TTI_MAX_S


def test_cue_kind_tells_locked_from_searching():
    assert threat_cue.torpedo_cue_kind(99.0, True, 1.0) == "seeker"
    assert threat_cue.torpedo_cue_kind(99.0, True, 1.0, acquired=True) == "locked"
    assert threat_cue.torpedo_cue_kind(
        99.0, True, config.TORP_SEEKER_INTERCEPT_NM + 1, acquired=True) is None


@pytest.fixture
def game(monkeypatch):
    value = Game(seed=4242, start_menu=False, audio_enabled=False)
    monkeypatch.setattr(value.world, "sonar_path_blocked", lambda *args: False)
    value.subs = []
    value.enemy_torpedoes = []
    return value


class _Torpedo:
    """A running homing torpedo as the cues see it (weakly referenced)."""

    def __init__(self, **values):
        self.__dict__.update(values)


def _torpedo(game, acquired):
    return _Torpedo(state="RUN", x=game.ship.x, y=game.ship.y - 0.8, depth=30.0,
                    time_since_launch=200.0, terminal_active=True,
                    seeker_acquired=acquired, launch_platform_id=3, idx=1)


def test_frigate_hears_the_lock_with_a_clock_and_fast_pings(game):
    game.enemy_torpedoes = [_torpedo(game, True)]
    start = len(game._sound_events)
    for _ in range(20):
        game.sim_t += 0.25
        game._update_torpedo_cues()
    warning = game.torpedo_warnings()[0]
    assert warning["source"] == "locked" and warning["tti_s"] > 0.0
    pings = [event for event in list(game._sound_events)[start:]
             if event["kind"] == "torpedo_seeker"]
    assert len(pings) >= 8
    texts = [localize(item.text, game.tr) for item in game.feed.recent(5)]
    assert any(str(round(warning["tti_s"])) in text or "locked" in text.lower() for text in texts)


def test_a_searching_seeker_carries_no_clock(game):
    game.enemy_torpedoes = [_torpedo(game, False)]
    game.sim_t += 0.25
    game._update_torpedo_cues()
    warning = game.torpedo_warnings()[0]
    assert warning["source"] == "seeker" and warning["tti_s"] is None


def test_crewed_boat_hears_the_lock_with_a_clock(monkeypatch):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from test_opfor_sub import _crewed

    from src.core import boat_threat, opfor

    game, _server, _bridge = _crewed()
    boat = game.opfor
    sub = boat.sub
    monkeypatch.setattr(game.world, "sonar_path_blocked", lambda *args: False)
    torpedo = _Torpedo(state="RUN", x=sub.x + 0.6, y=sub.y, depth=sub.depth,
                       terminal_active=True, seeker_acquired=True,
                       launch_platform_id=0, idx=2)
    game.torpedoes = [torpedo]
    for _ in range(12):
        game.sim_t += 0.25
        opfor.hear_seekers(game, boat)
    clock = boat_threat.picture(game, boat)["clock"]
    assert clock is not None and 60 <= clock["bearing"] <= 120 and clock["tti_s"] > 0
    assert [key for key, _ in boat.orders._events].count("torpedo_locked") == 1
    assert [row["kind"] for row in boat.sound_events].count("torpedo_seeker") >= 4
    game.torpedoes = []
    opfor.hear_seekers(game, boat)
    assert boat_threat.picture(game, boat)["clock"] is None
