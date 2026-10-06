"""What decided a mission: the end panel's line for either side (N5)."""

from src.core import decisive
from src.core.boat_campaign import WINS
from src.core.i18n import Translator, localize


class _Recorder:
    def __init__(self, events, spans=(), frames=(), prefix="debrief."):
        self.events = [dict(t=t, kind=kind, params=params) for t, kind, params in events]
        self._spans = list(spans)
        self.frames = list(frames)
        self.prefix = prefix
        self._ended = True

    def spans(self):
        return self._spans


def _key(line):
    return line["__u_jagd_i18n__"] if line is not None else None


def test_frigate_win_names_contact_and_the_sinking_shot():
    recorder = _Recorder([(300, "first_contact", {}), (900, "own_shot", {"weapon": "T3"}),
                          (1000, "sub_sunk", {"sub": 1}),
                          (1001, "mission_end", {"result": "SIEG"})])
    line = decisive.line(recorder)
    assert _key(line) == "end.decisive.sunk"
    english = localize(line, Translator("en").t)
    assert "5 min" in english and "T3" in english and "15 min" in english
    assert localize(line, Translator("de").t) != english


def test_frigate_loss_names_the_torpedo_bearing():
    recorder = _Recorder([(120, "enemy_shot", {"bearing": 47}), (300, "ship_sunk", {}),
                          (301, "mission_end", {"result": "VERLOREN"})])
    line = decisive.line(recorder)
    assert _key(line) == "end.decisive.ship_sunk" and line["params"]["bearing"] == "047"


def test_frigate_loss_prefers_the_longest_missed_chance():
    spans = [dict(t=100, duration_s=360, min_range_nm=2.4, layer=True),
             dict(t=900, duration_s=600, min_range_nm=3.1, layer=False)]
    recorder = _Recorder([(2000, "mission_end", {"result": "VERLOREN"})], spans=spans)
    line = decisive.line(recorder)
    assert _key(line) == "end.decisive.missed_open" and line["params"]["minutes"] == 10
    never = _Recorder([(2000, "mission_end", {"result": "VERLOREN"})])
    assert _key(decisive.line(never)) == "end.decisive.never_heard"


def test_boat_lines_follow_the_boat_result():
    win = sorted(WINS)[0]
    frames = [dict(ship=dict(x=0.0, y=0.0), subs=[dict(x=4.0, y=3.0)])]
    quiet = _Recorder([(1800, "mission_end", {"result": win})], frames=frames,
                      prefix="debrief.boat.")
    line = decisive.line(quiet)
    assert _key(line) == "end.decisive.boat.never_held" and line["params"]["range"] == "5.0"
    sunk = _Recorder([(400, "enemy_shot", {"bearing": 310}), (500, "ship_sunk", {}),
                      (501, "mission_end", {"result": "sunk"})], prefix="debrief.boat.")
    assert _key(decisive.line(sunk)) == "end.decisive.boat.sunk"
    lesson = _Recorder([(60, "mission_end", {"result": "trained"})], prefix="debrief.boat.")
    assert decisive.line(lesson) is None


def test_unfinished_recording_has_no_line():
    recorder = _Recorder([(10, "first_contact", {})])
    recorder._ended = False
    assert decisive.line(recorder) is None and decisive.line(None) is None


def test_end_panel_and_browser_document_carry_the_line():
    from src.core import debrief_replay
    from src.core.game import Game
    game = Game(seed=7, start_menu=False, audio_enabled=False)
    game.tasking.next_offer_t = 1e9
    for _ in range(20):
        game.update(0.5)
    game._end_mission(False, "test")
    line = game.decisive_end_line()
    assert line is not None and line is game.decisive_end_line()     # cached
    doc = debrief_replay.document(game.frigate_debrief, "frigate")
    assert set(doc["decisive"]) == {"en", "de"}
    assert doc["decisive"]["en"] == localize(line, Translator("en").t)
    assert debrief_replay.document(game.frigate_debrief, "frigate", lesson=True)["decisive"] is None
    game.draw()
