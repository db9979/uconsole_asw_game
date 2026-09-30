"""Mission debrief: bounded recording, events, missed chances, the page."""

import json

import pygame

from src.core import config, debrief
from src.core.debrief import DebriefRecorder, missed_chances
from src.core.game import Game
from src.sonar.sonar import Contact


def _game(seed=7):
    game = Game(seed=seed, start_menu=False, audio_enabled=False)
    game.tasking.next_offer_t = 1e9
    return game


def _key(game, key, mod=0):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod, unicode=""))


def _frame(t, sub_xy, heard=False, layer=True):
    return dict(t=t, ship=dict(x=0.0, y=0.0, course=0), assets=[], errors=[],
                own_weapons=[], enemy_weapons=[], buoys=[],
                subs=[dict(id=1, x=sub_xy[0], y=sub_xy[1], depth=120, sunk=False,
                           hostile=True, layer=layer)],
                known=[dict(label="S1", bearing=0.0, x=None, y=None, target=1)] if heard else [])


def test_recording_is_bounded_and_keeps_the_whole_mission(monkeypatch):
    monkeypatch.setattr(config, "DEBRIEF_MAX_FRAMES", 8)
    recorder = DebriefRecorder()
    t = 0.0
    for _ in range(40):
        if recorder.due(t):
            recorder.add_frame(_frame(t, (10.0, 0.0)))
        t += 5.0
    assert len(recorder.frames) < 8
    assert recorder.frames[0]["t"] == 0.0 and recorder.frames[-1]["t"] >= 150.0
    assert recorder.interval_s > config.DEBRIEF_INTERVAL_S


def test_missed_chance_needs_a_close_unheard_boat_for_five_minutes():
    frames = [_frame(t, (3.0, 0.0)) for t in range(0, 400, 10)]
    spans = missed_chances(frames)
    assert len(spans) == 1 and spans[0]["duration_s"] >= 300 and spans[0]["layer"]
    heard = [_frame(t, (3.0, 0.0), heard=t > 100) for t in range(0, 400, 10)]
    assert missed_chances(heard) == []
    far = [_frame(t, (9.0, 0.0)) for t in range(0, 400, 10)]
    assert missed_chances(far) == []


def test_events_from_contacts_shots_and_the_end(monkeypatch):
    game = _game()
    sub = next(sub for sub in game.subs if sub.side == "hostile")
    contact = Contact(1, sub.id, "passiv", "sub")
    contact.bearing = 45.0
    monkeypatch.setattr(game.sonar, "active_contacts", lambda: [contact])
    recorder = game.debrief
    recorder.observe(game, 10.0)
    contact.observed_x, contact.observed_y = sub.x + .5, sub.y
    contact.player_class = "U_BOOT"
    recorder.observe(game, 20.0)
    recorder.observe(game, 30.0)
    kinds = [event["kind"] for event in recorder.events]
    assert kinds == ["first_contact", "first_fix", "classified"]
    frame = debrief.capture(game, 30.0)
    assert frame["errors"] == [0.5] and frame["known"][0]["target"] == sub.id
    sub.sunk = True
    recorder.observe(game, 40.0)
    game.mission_time = 50.0
    game._end_mission(True, "test")
    kinds = [event["kind"] for event in recorder.events]
    assert kinds[-2:] == ["sub_sunk", "mission_end"]
    assert recorder.metrics()["first_contact_t"] == 10.0
    assert json.loads(json.dumps(recorder.frames)) == recorder.frames


def test_recording_runs_with_the_mission_and_never_enters_the_save():
    game = _game()
    for _ in range(80):
        game.update(0.5)
    assert game.debrief.frames and game.debrief.frames[0]["t"] <= config.DEBRIEF_INTERVAL_S
    assert "debrief" not in game.save_state()
    document = json.loads(json.dumps(game.save_state()))
    other = _game()
    for _ in range(40):
        other.update(0.5)
    assert other._load_save_data(document)
    assert other.debrief.frames == []            # covers the mission from the load on


def test_page_opens_only_after_the_end_and_owns_input():
    game = _game()
    for _ in range(60):
        game.update(0.5)
    assert game.open_debrief() is False
    _key(game, pygame.K_d)
    assert not game.debrief_open
    game._end_mission(False, "test")
    _key(game, pygame.K_d)
    assert game.debrief_open
    last = game.debrief_index
    _key(game, pygame.K_LEFT)
    assert game.debrief_index == last - 1
    _key(game, pygame.K_HOME)
    assert game.debrief_index == 0
    _key(game, pygame.K_PAGEDOWN)
    assert game.debrief_index > 0
    game.draw()
    _key(game, pygame.K_ESCAPE)                  # closes the page, not the game
    assert not game.debrief_open and not game.quit_confirm
    game.draw()


def test_replay_interpolates_and_flashes_events():
    from src.core import debrief_replay
    frames = [_frame(0.0, (0.0, 0.0)), _frame(60.0, (6.0, 0.0))]
    frames[1]["ship"] = dict(x=2.0, y=0.0, course=90)
    moved = debrief_replay.interpolate(frames, 30.0)
    assert moved["subs"][0]["x"] == 3.0 and moved["ship"]["x"] == 1.0
    assert moved["ship"]["course"] == 45.0
    assert debrief_replay.interpolate(frames, 99.0) is frames[-1]
    events = [dict(t=20.0, kind="own_shot", params={}), dict(t=25.0, kind="missed", params={})]
    assert [e["kind"] for e, _k in debrief_replay.flashes(events, 21.0, 10)] == ["own_shot"]
    assert debrief_replay.flashes(events, 20.0 + 10 * debrief_replay.FLASH_WALL_S + 1, 10) == []


def test_replay_plays_at_ten_and_sixty_times_on_wall_time():
    from src.core import debrief_replay
    frames = [_frame(0.0, (0.0, 0.0)), _frame(600.0, (1.0, 0.0))]
    replay = debrief_replay.Replay()
    replay.toggle(frames)
    replay.advance(frames, 100.0)
    replay.advance(frames, 100.2)
    assert abs(replay.t - 2.0) < 1e-9
    replay.cycle_speed()
    replay.advance(frames, 100.4)
    assert abs(replay.t - 14.0) < 1e-9
    for step in range(1, 200):
        replay.advance(frames, 100.4 + step * 0.2)
    assert replay.t == 600.0 and not replay.playing


def test_replay_keys_and_buttons_on_the_page():
    game = _game()
    for _ in range(60):
        game.update(0.5)
    game._end_mission(False, "test")
    _key(game, pygame.K_d)
    _key(game, pygame.K_HOME)
    assert game.debrief_replay.t == game.debrief.frames[0]["t"]
    _key(game, pygame.K_SPACE)
    assert game.debrief_replay.playing
    _key(game, pygame.K_TAB)
    assert game.debrief_replay.speed == 60
    game.draw()
    from src.ui.debrief_view import PLAY
    game._handle_debrief_click(PLAY.center)
    assert not game.debrief_replay.playing
    game.draw()


def test_replay_document_for_the_browser_is_detached_and_bilingual():
    from src.core import debrief_replay
    game = _game()
    for _ in range(60):
        game.update(0.5)
    game._end_mission(False, "test")
    doc = debrief_replay.document(game.frigate_debrief, "frigate")
    json.dumps(doc, allow_nan=False)
    assert doc["side"] == "frigate" and doc["frames"]
    assert all("target" not in row for frame in doc["frames"] for row in frame["known"])
    assert doc["events"][-1]["type"] == "mission_end"
    assert doc["events"][-1]["en"] != doc["events"][-1]["de"]


def test_bridge_publishes_the_replay_only_after_the_end():
    from src.commander.bridge import CommanderBridge
    from test_commander_bridge import Server
    game = _game()
    for _ in range(20):
        game.update(0.5)
    server, bridge = Server(), CommanderBridge()
    bridge.pump(game, server, now=10.0)
    assert server.debriefs["documents"] == {}
    game._end_mission(False, "test")
    bridge.pump(game, server, now=11.0)
    documents = server.debriefs["documents"]
    assert set(documents) == {"frigate"} and documents["frigate"]["frames"]
