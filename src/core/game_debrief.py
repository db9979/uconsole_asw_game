"""The mission debrief in the game: recording while it runs, the page after.

``src/core/debrief.py`` records; this mixin feeds it from the read-only
end of each simulation step, closes it when the mission ends and owns the
debrief page's input (opened with ``D`` from the end panel).
"""

from __future__ import annotations

import pygame

from src.core import config
from src.core.boat_debrief import BoatDebriefRecorder
from src.core.debrief import DebriefRecorder
from src.core.debrief_replay import Replay


class DebriefMixin:
    """Bounded mission recording and the post-mission debrief page.

    The frigate's recording always runs; a crewed boat gets a second one
    from its own point of view.  The page shows the local side's."""

    def _reset_debrief(self) -> None:
        self.frigate_debrief = DebriefRecorder()
        self.boat_debrief = None
        self.debrief = self.frigate_debrief
        self.debrief_open = False
        self.debrief_report_open = False
        self.debrief_report_scroll = 0
        self.debrief_index = 0
        self.debrief_replay = Replay()
        self._debrief_acc = 0.0

    def _debrief_recorders(self):
        yield self.frigate_debrief
        boat = getattr(self, "_opfor", None)
        if boat is not None:
            if self.boat_debrief is None or self.boat_debrief.sub_id != boat.sub_id:
                self.boat_debrief = BoatDebriefRecorder(boat.sub_id)
            yield self.boat_debrief

    def _record_debrief(self, dt: float) -> None:
        """Read-only: events once a second, a frame every interval."""
        if self.game_over:
            return
        self._debrief_acc += dt
        if self._debrief_acc < config.DEBRIEF_EVENT_S:
            return
        self._debrief_acc = 0.0
        for recorder in self._debrief_recorders():
            recorder.observe(self, self.mission_time)
            if recorder.due(self.mission_time):
                recorder.add_frame(recorder.capture(self, self.mission_time))

    def _finish_debrief(self) -> None:
        for recorder in self._debrief_recorders():
            recorder.finish(self, self.mission_time)

    # --- the page -------------------------------------------------------------------

    def open_debrief(self) -> bool:
        if not self.game_over:
            return False          # never during a mission: the truth is in it
        self.debrief = (self.boat_debrief if getattr(self, "local_side", "frigate") == "uboot"
                        and self.boat_debrief is not None else self.frigate_debrief)
        self.debrief_open = True
        self.debrief_index = max(0, len(self.debrief.frames) - 1)
        self.debrief_replay = Replay()
        self._seek_debrief_frame()
        return True

    def _seek_debrief_frame(self) -> None:
        """Put the replay cursor on the selected frame (and stop playing)."""
        frames = self.debrief.frames
        self.debrief_replay.playing = False
        if frames:
            self.debrief_replay.seek(frames[max(0, min(self.debrief_index, len(frames) - 1))]["t"])

    def advance_debrief_replay(self, wall_now: float) -> None:
        """Move a playing replay on by the wall time since the last frame."""
        replay = self.debrief_replay
        if replay.playing:
            replay.advance(self.debrief.frames, wall_now)
            self.debrief_index = self.debrief.frame_index_at(replay.t)

    def toggle_debrief_replay(self) -> None:
        self.debrief_replay.toggle(self.debrief.frames)

    def cycle_debrief_speed(self) -> None:
        self.debrief_replay.cycle_speed()

    def close_debrief(self) -> None:
        self.debrief_open = False

    def _step_debrief(self, frames: int) -> None:
        last = max(0, len(self.debrief.frames) - 1)
        self.debrief_index = max(0, min(last, self.debrief_index + frames))

    def _jump_debrief_event(self, direction: int) -> None:
        frames = self.debrief.frames
        if not frames:
            return
        now = frames[self.debrief_index]["t"]
        times = sorted({event["t"] for event in self.debrief.events})
        if direction > 0:
            target = next((t for t in times if t > now + 1e-6), None)
        else:
            target = next((t for t in reversed(times) if t < now - 1e-6), None)
        if target is not None:
            index = self.debrief.frame_index_at(target)
            if direction > 0 and frames[index]["t"] < target and index + 1 < len(frames):
                index += 1
            if index == self.debrief_index:
                index = max(0, min(len(frames) - 1, index + direction))
            self.debrief_index = index

    def _handle_debrief_key(self, key: int, mod: int = 0) -> None:
        big = 6 if mod & pygame.KMOD_SHIFT else 1
        if key == pygame.K_b:
            # The language model's after-action report in the side panel.
            self.debrief_report_open = not getattr(self, "debrief_report_open", False)
            self.debrief_report_scroll = 0
            return
        if getattr(self, "debrief_report_open", False) and key in (
                pygame.K_UP, pygame.K_DOWN, pygame.K_PAGEUP, pygame.K_PAGEDOWN):
            step = 8 if key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN) else 1
            if key in (pygame.K_UP, pygame.K_PAGEUP):
                step = -step
            self.debrief_report_scroll = max(0, self.debrief_report_scroll + step)
            return
        if key == pygame.K_SPACE:
            self.toggle_debrief_replay()
            return
        if key == pygame.K_TAB:
            self.cycle_debrief_speed()
            return
        previous = self.debrief_index
        self._debrief_navigate(key, big)
        if self.debrief_index != previous or key in (pygame.K_HOME, pygame.K_END):
            self._seek_debrief_frame()

    def _debrief_navigate(self, key: int, big: int) -> None:
        if key in (pygame.K_ESCAPE, pygame.K_d):
            self.close_debrief()
        elif key == pygame.K_LEFT:
            self._step_debrief(-big)
        elif key == pygame.K_RIGHT:
            self._step_debrief(big)
        elif key == pygame.K_HOME:
            self.debrief_index = 0
        elif key == pygame.K_END:
            self._step_debrief(len(self.debrief.frames))
        elif key in (pygame.K_PAGEUP, pygame.K_UP):
            self._jump_debrief_event(-1)
        elif key in (pygame.K_PAGEDOWN, pygame.K_DOWN):
            self._jump_debrief_event(1)

    def _handle_debrief_click(self, canvas) -> None:
        from src.ui.debrief_view import replay_button_at, timeline_index_at
        button = replay_button_at(canvas)
        if button == "play":
            self.toggle_debrief_replay()
            return
        if button == "speed":
            self.cycle_debrief_speed()
            return
        index = timeline_index_at(self, canvas)
        if index is not None:
            self.debrief_index = index
            self._seek_debrief_frame()
