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
