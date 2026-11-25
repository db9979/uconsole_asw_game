"""The log read aloud for browser stations (optional speech service).

The uConsole reads its own side's log entries aloud with the speech service
(``src/core/game_voice.py``).  A browser station hears its side's log the
same way: while the browser's switch "Read log aloud" is on, it asks
``GET /api/v2/voice/log`` about once a second for the clips of its own side
(sequence number, station of the log, and whether the crew already calls the
entry out) and fetches each at ``GET /api/v2/voice/log?seq=<n>`` (16-bit
mono PCM, its rate in a header).  Asking marks the side as listening; the
host only asks its speech service for a side somebody listens to, and the
speech service and its key never leave the host.  ``?probe=1`` only tells
whether the host reads aloud at all (to show the switch) and listens to
nothing.  Nothing here is saved.
"""

from __future__ import annotations

import time

from src.commander.advisor_web import side_of_role
from src.commander.v2.wire import LOOKOUT_ROLES, _json_bytes

LOG_VOICE_ROUTE = "/api/v2/voice/log"
LOG_VOICE_CLIP_ROUTE = LOG_VOICE_ROUTE + "?seq="
# Whether the host reads aloud at all, without listening (no clips).
LOG_VOICE_PROBE_ROUTE = LOG_VOICE_ROUTE + "?probe=1"
# A side counts as listening this long after its last index request.
LISTEN_S = 6.0
SIDES = ("frigate", "uboot")


class LogVoiceServerMixin:
    """Published clips and the listening sides in ``CommanderServer``."""

    def _init_log_voice(self):
        self._log_voices = {}
        self._log_voice_rate = 0
        self._log_voice_on = False
        self._log_listeners = {}

    def _clear_log_voice_locked(self):
        self._log_voices = {}
        self._log_listeners = {}

    def publish_log_voice(self, clips: dict, rate: int, on: bool) -> None:
        """``clips``: side -> {seq: (group, called, PCM bytes)} (detached,
        bounded by the game); ``on``: the host reads logs aloud at all."""
        with self._lock:
            self._log_voices = clips
            self._log_voice_rate = int(rate)
            self._log_voice_on = bool(on)

    def log_voice_listeners(self, now: float | None = None) -> frozenset:
        """The sides a browser asked about within ``LISTEN_S``."""
        now = time.monotonic() if now is None else now
        with self._lock:
            return frozenset(side for side, when in self._log_listeners.items()
                             if now - when <= LISTEN_S)

    @staticmethod
    def _log_voice_side(session):
        role = session["active_station"]
        if role is None or session.get("observer") or role in LOOKOUT_ROLES:
            return None
        return side_of_role(role)

    def log_voice_index_locked(self, session, probe: bool = False):
        side = self._log_voice_side(session)
        if side is None:
            return None
        if probe:
            return _json_bytes({"protocol": 2, "on": self._log_voice_on, "clips": []})
        if self._log_voice_on:
            self._log_listeners[side] = time.monotonic()
        clips = self._log_voices.get(side, {}) if self._log_voice_on else {}
        return _json_bytes({
            "protocol": 2, "on": self._log_voice_on,
            "clips": [{"seq": int(seq), "group": str(group), "called": bool(called)}
                      for seq, (group, called, _pcm) in clips.items()]})

    def log_voice_clip_locked(self, session, path: str):
        """``(pcm, rate)`` of one clip of the session's own side, or None."""
        side = self._log_voice_side(session)
        text = path[len(LOG_VOICE_CLIP_ROUTE):]
        if (side is None or not path.startswith(LOG_VOICE_CLIP_ROUTE) or not text.isdigit()
                or len(text) > 9):
            return None
        row = self._log_voices.get(side, {}).get(int(text))
        return None if row is None else (row[2], self._log_voice_rate)


def pump_log_voice(server, game, published: dict) -> None:
    """Main thread: hand the listening sides to the game, publish new clips."""
    if not hasattr(server, "log_voice_listeners") or not hasattr(game, "web_log_clips"):
        return
    game.web_log_sides = server.log_voice_listeners()
    voice = getattr(game, "voice", None)
    on = bool(voice is not None and voice.active and game.preferences.tts_log)
    key = (on, tuple((side, tuple(clips)) for side, clips in sorted(game.web_log_clips.items())),
           getattr(game, "web_voice_rate", 0))
    if published.get("key") == key:
        return
    clips = {side: dict(rows) for side, rows in game.web_log_clips.items() if side in SIDES}
    server.publish_log_voice(clips, getattr(game, "web_voice_rate", 0), on)
    published["key"] = key
