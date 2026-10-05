"""The OPZ picture is computed once per drawn frame and its affiliation
lookup uses an index instead of a scan per track: same results, less work."""

from src.air.live_aircraft import LiveAircraft
from src.core.game import Game
from src.core.station import Station


def _game_with_aircraft(count=6):
    game = Game(seed=4242, start_menu=False, audio_enabled=False)
    game.sim_t = 10.0
    game.air_radar_on = True
    for index in range(count):
        seq = game.flights.next_seq()
        game.live_traffic.aircraft[f"memo{index}"] = LiveAircraft(
            f"memo{index}", "TEST", seq, x=game.ship.x + 2.0 + index,
            y=game.ship.y, altitude_m=3000.0, course=90.0, speed_kn=200.0, t=0.0)
    for _ in range(60):
        game.update(0.1)
    return game


def test_draw_memo_returns_the_same_tracks_and_is_dropped_after_the_frame():
    game = _game_with_aircraft()
    game.station = Station.OPZ
    plain = game.opz_tracks()
    assert plain
    calls = []
    original = game._opz_tracks_now

    def counted():
        calls.append(1)
        return original()

    game._opz_tracks_now = counted
    game.draw()
    assert len(calls) == 1
    assert game._opz_draw_memo is None
    assert [t.track_id for t in game.opz_tracks()] == [t.track_id for t in plain]


def test_affiliation_index_follows_new_bindings():
    game = _game_with_aircraft()
    game.opz_tracks()
    for observation_id, source in list(game._opz_source_bindings.items()):
        track_id = getattr(source, "track_id", None)
        if track_id is None:
            continue
        expected = next(key for key, item in game._opz_source_bindings.items()
                        if getattr(item, "track_id", None) == track_id)
        assert game._opz_binding_for_source(track_id) == expected
        game.opz_affiliations[observation_id] = "HOSTILE"
        assert game.opz_affiliation(track_id) == "HOSTILE"
    game._opz_source_bindings = {}
    assert game._opz_binding_for_source("A-1") is None
