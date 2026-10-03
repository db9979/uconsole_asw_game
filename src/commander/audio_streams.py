"""Remote Crew audio streams: the sonar, helicopter-dipping and boat
listening rings, their per-role clearing, discontinuity marks, statistics
and the main-thread prepare/publish entry points.  Moved verbatim from
``server.py``; ``CommanderServer`` inherits ``AudioStreamServerMixin``.
"""

import threading

from src.commander.v2.wire import (
    SONAR_AUDIO_ROLES, SONAR_AUDIO_BYTES, _SAFE_INTEGER_MAX)


class AudioStreamServerMixin:
    """Audio-stream half of ``CommanderServer`` (state and lock live on the server)."""

    def _clear_sonar_audio_locked(self):
        # Numbering never restarts while the server lives: a browser worklet
        # de-duplicates by sequence, so a restart at 1 would make it drop every
        # new block until the count passed the old one. A cleared stream that
        # had content skips one number so the restart shows as a gap.
        if self._sonar_audio:
            self._sonar_audio_sequence += 1
        self._sonar_audio.clear()
        self._sonar_audio_context = None
        self._audio_condition.notify_all()

    def _clear_helicopter_audio_locked(self):
        # Numbering never restarts while the server lives: a browser worklet
        # de-duplicates by sequence, so a restart at 1 would make it drop every
        # new block until the count passed the old one. A cleared stream that
        # had content skips one number so the restart shows as a gap.
        if self._helicopter_audio:
            self._helicopter_audio_sequence += 1
        self._helicopter_audio.clear()
        self._helicopter_audio_context = None
        self._audio_condition.notify_all()

    def _clear_uboot_audio_locked(self):
        # Numbering never restarts while the server lives: a browser worklet
        # de-duplicates by sequence, so a restart at 1 would make it drop every
        # new block until the count passed the old one. A cleared stream that
        # had content skips one number so the restart shows as a gap.
        if self._uboot_audio:
            self._uboot_audio_sequence += 1
        self._uboot_audio.clear()
        self._uboot_audio_context = None
        self._audio_condition.notify_all()

    def _clear_role_audio_locked(self, role):
        if role == "sonar":
            self._clear_sonar_audio_locked()
        elif role == "helicopter":
            self._clear_helicopter_audio_locked()
        elif role == "uboot_sonar":
            self._clear_uboot_audio_locked()

    def _audio_ring(self, role):
        """(blocks, context) of one audio role's stream."""
        if role == "sonar":
            return self._sonar_audio, self._sonar_audio_context
        if role == "helicopter":
            return self._helicopter_audio, self._helicopter_audio_context
        return self._uboot_audio, self._uboot_audio_context

    def _stream_for(self, role):
        """(context, payload) of one sonar room's waterfall stream."""
        if role == "uboot_sonar":
            return self._uboot_stream_context, self._uboot_stream_payload
        return self._sonar_stream_context, self._sonar_stream_payload

    def clear_sonar_audio(self):
        """Clear every live-audio byte and context without touching a session."""
        with self._lock:
            self._clear_sonar_audio_locked()

    def clear_helicopter_audio(self):
        with self._lock:
            self._clear_helicopter_audio_locked()

    def clear_uboot_audio(self):
        with self._lock:
            self._clear_uboot_audio_locked()

    def mark_audio_discontinuity(self, role: str) -> bool:
        """Skip one sequence number of a live stream (main thread only).

        The receiver restarted (a retuned listening bearing), so the next block
        does not continue the previous waveform. Every browser transport sees
        the gap and crossfades instead of joining unrelated audio. Nothing is
        marked on an unbound stream.
        """
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError("audio discontinuity requires the main thread")
        if role not in SONAR_AUDIO_ROLES:
            raise ValueError("unknown audio role")
        with self._lock:
            if self._audio_ring(role)[1] is None:
                return False
            if role == "sonar":
                self._sonar_audio_sequence += 1
            elif role == "helicopter":
                self._helicopter_audio_sequence += 1
            else:
                self._uboot_audio_sequence += 1
            self.audio_stream_stats_locked(role)["discontinuities"] += 1
            return True

    def audio_stream_stats_locked(self, role: str) -> dict:
        """Bounded per-role transport counters (diagnostics only)."""
        stats = self._audio_stats.get(role)
        if stats is None:
            stats = self._audio_stats[role] = {
                "skipped_blocks": 0, "send_timeouts": 0, "discontinuities": 0,
                "connections": 0}
        return stats

    def audio_stream_stats(self) -> dict:
        """Detached copy of the per-role audio transport counters."""
        with self._lock:
            return {role: dict(self.audio_stream_stats_locked(role))
                    for role in SONAR_AUDIO_ROLES}

    def _uboot_audio_holder_locked(self):
        return next(((digest, session) for digest, session
                     in self._sessions_v2.items()
                     if "uboot_sonar" in session["leases"]
                     and session["active_station"] == "uboot_sonar"), None)

    def prepare_uboot_audio(self, *, world_session: str, world_epoch: int):
        """Bind an empty stream to the current granted submarine sonar holder."""
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError("uboot audio preparation requires the main thread")
        if (type(world_session) is not str or not world_session
                or type(world_epoch) is not int or world_epoch < 0):
            raise ValueError("invalid uboot audio context")
        with self._lock:
            self._expire_locked()
            holder = self._uboot_audio_holder_locked()
            if (holder is None
                    or not holder[1]["leases"]["uboot_sonar"]["grants"]["sonar_audio"]):
                self._clear_uboot_audio_locked()
                return None
            generation = holder[1]["leases"]["uboot_sonar"]["generation"]
            context = (holder[0], generation, holder[1]["active_generation"],
                       world_session, world_epoch)
            if context != self._uboot_audio_context:
                self._clear_uboot_audio_locked()
                self._uboot_audio_context = context
            return generation

    def publish_uboot_audio(self, pcm: bytes, *, world_session: str,
                            world_epoch: int, station_generation: int):
        """Publish one submarine sonar receiver block from the main thread."""
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError("uboot audio publication requires the main thread")
        if (type(pcm) is not bytes or len(pcm) != SONAR_AUDIO_BYTES
                or type(world_session) is not str or not world_session
                or type(world_epoch) is not int or world_epoch < 0
                or type(station_generation) is not int or station_generation < 0):
            raise ValueError("invalid uboot audio publication")
        with self._lock:
            self._expire_locked()
            holder = self._uboot_audio_holder_locked()
            if holder is None:
                self._clear_uboot_audio_locked()
                return False
            lease = holder[1]["leases"]["uboot_sonar"]
            context = (holder[0], station_generation,
                       holder[1]["active_generation"], world_session, world_epoch)
            if (not lease["grants"]["sonar_audio"]
                    or lease["generation"] != station_generation
                    or context != self._uboot_audio_context):
                self._clear_uboot_audio_locked()
                return False
            if self._uboot_audio_sequence >= _SAFE_INTEGER_MAX:
                self._clear_uboot_audio_locked()
                self._uboot_audio_sequence = 0
                self._uboot_audio_context = context
            self._uboot_audio_sequence += 1
            self._uboot_audio.append((self._uboot_audio_sequence, pcm))
            self._audio_condition.notify_all()
            return True

    def prepare_helicopter_audio(self, *, world_session: str, world_epoch: int):
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError("helicopter audio preparation requires the main thread")
        with self._lock:
            self._expire_locked()
            holder = next(((digest, session) for digest, session
                           in self._sessions_v2.items()
                           if "helicopter" in session["leases"]
                           and session["active_station"] == "helicopter"), None)
            if (holder is None or not holder[1]["leases"]["helicopter"]
                    ["grants"]["sonar_audio"]):
                self._clear_helicopter_audio_locked()
                return None
            generation = holder[1]["leases"]["helicopter"]["generation"]
            context = (holder[0], generation, holder[1]["active_generation"],
                       world_session, world_epoch)
            if context != self._helicopter_audio_context:
                self._clear_helicopter_audio_locked()
                self._helicopter_audio_context = context
            return generation

    def publish_helicopter_audio(self, pcm: bytes, *, world_session: str,
                                 world_epoch: int, station_generation: int):
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError("helicopter audio publication requires the main thread")
        if type(pcm) is not bytes or len(pcm) != SONAR_AUDIO_BYTES:
            raise ValueError("invalid helicopter audio block")
        with self._lock:
            self._expire_locked()
            holder = next(((digest, session) for digest, session
                           in self._sessions_v2.items()
                           if "helicopter" in session["leases"]
                           and session["active_station"] == "helicopter"), None)
            if holder is None:
                self._clear_helicopter_audio_locked()
                return False
            context = (holder[0], station_generation,
                       holder[1]["active_generation"], world_session, world_epoch)
            if (not holder[1]["leases"]["helicopter"]["grants"]["sonar_audio"]
                    or holder[1]["leases"]["helicopter"]["generation"]
                    != station_generation or context != self._helicopter_audio_context):
                self._clear_helicopter_audio_locked()
                return False
            if self._helicopter_audio_sequence >= _SAFE_INTEGER_MAX:
                self._clear_helicopter_audio_locked()
                self._helicopter_audio_sequence = 0
                self._helicopter_audio_context = context
            self._helicopter_audio_sequence += 1
            self._helicopter_audio.append((self._helicopter_audio_sequence, pcm))
            self._audio_condition.notify_all()
            return True

    def prepare_sonar_audio(self, *, world_session: str, world_epoch: int):
        """Bind an empty stream to the current granted sonar holder."""
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError("sonar audio preparation requires the main thread")
        if (type(world_session) is not str or not world_session
                or type(world_epoch) is not int or world_epoch < 0):
            raise ValueError("invalid sonar audio context")
        with self._lock:
            self._expire_locked()
            holder = next(((digest, session) for digest, session
                           in self._sessions_v2.items()
                           if "sonar" in session["leases"]
                           and session["active_station"] == "sonar"), None)
            if (holder is None
                    or not holder[1]["leases"]["sonar"]["grants"]["sonar_audio"]):
                self._clear_sonar_audio_locked()
                return None
            generation = holder[1]["leases"]["sonar"]["generation"]
            context = (holder[0], generation, holder[1]["active_generation"],
                       world_session, world_epoch)
            if context != self._sonar_audio_context:
                self._clear_sonar_audio_locked()
                self._sonar_audio_context = context
            return generation

    def publish_sonar_audio(self, pcm: bytes, *, world_session: str,
                            world_epoch: int, station_generation: int):
        """Publish one immutable receiver block from the main thread only."""
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError("sonar audio publication requires the main thread")
        if (type(pcm) is not bytes or len(pcm) != SONAR_AUDIO_BYTES
                or type(world_session) is not str or not world_session
                or type(world_epoch) is not int or world_epoch < 0
                or type(station_generation) is not int or station_generation < 0):
            raise ValueError("invalid sonar audio publication")
        with self._lock:
            self._expire_locked()
            holder = next(((digest, session) for digest, session
                           in self._sessions_v2.items()
                           if "sonar" in session["leases"]
                           and session["active_station"] == "sonar"), None)
            if holder is None:
                self._clear_sonar_audio_locked()
                return False
            context = (holder[0], station_generation,
                       holder[1]["active_generation"], world_session, world_epoch)
            if (not holder[1]["leases"]["sonar"]["grants"]["sonar_audio"]
                    or holder[1]["leases"]["sonar"]["generation"] != station_generation
                    or context != self._sonar_audio_context):
                self._clear_sonar_audio_locked()
                return False
            if self._sonar_audio_sequence >= _SAFE_INTEGER_MAX:
                self._clear_sonar_audio_locked()
                self._sonar_audio_sequence = 0
                self._sonar_audio_context = context
            self._sonar_audio_sequence += 1
            self._sonar_audio.append((self._sonar_audio_sequence, pcm))
            self._audio_condition.notify_all()
            return True
