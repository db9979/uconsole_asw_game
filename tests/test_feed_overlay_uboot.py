"""F11 on the submarine side opens the boat log, as it does on the frigate."""

import pygame

from src.core.game import Game


def test_f11_on_the_submarine_side_shows_the_boat_log(monkeypatch):
    game = Game(seed=913, start_menu=False, audio_enabled=False, language="en")
    try:
        game.local_side = "uboot"
        boat = game.claim_opfor_sub()
        boat.notice(game.sim_t, "sonar", "Boat log line", stamp="08:05")
        game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F11, mod=0,
                                             unicode=""))
        assert game.feed_overlay_open
        shown = {}

        def overlay(entries=None, telemetry=None):
            shown["entries"] = [(entry.stamp, entry.text) for entry in entries]
            shown["telemetry"] = [row[0] for row in telemetry]

        monkeypatch.setattr(game, "draw_feed_overlay", overlay)
        game._draw()
        assert shown["entries"][-1] == ("08:05", "Boat log line")
        assert shown["telemetry"][0] == "uboot.telemetry.course_speed"
        monkeypatch.undo()
        game._draw()  # the real overlay draws without error
        for index in range(40):
            boat.notice(game.sim_t, "navigation", f"Line {index}", stamp="08:06")
        game._draw()
        # The headless window is the canvas: the wheel over the log scrolls it.
        center = game.feed_overlay_rect().center
        assert game._window_to_canvas(center) == center
        game.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=1, pos=center))
        assert game.feed_overlay_scroll > 0
        game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F11, mod=0,
                                             unicode=""))
        assert not game.feed_overlay_open
    finally:
        game.audio.shutdown()
