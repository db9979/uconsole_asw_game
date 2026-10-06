"""The uConsole's own microphone: noise discipline (opt-in, level only) and
the talk key of the language model's speech input.

SDL2 capture through ``pygame._sdl2.audio``: the capture thread keeps the
loudness of the newest block; only while the talk key is held
(``begin_recording``/``end_recording``) does it also keep the samples, in
memory and at most ``RECORD_MAX_S``, for one question to the executive
officer (``src/core/game_talk.py``).  Nothing is stored or played.  No
device, no SDL support or a refused device leaves ``available`` False and the
game runs on without it (``src/core/game_noise.py``); ``failure`` then names
the cause the player is shown (``option.microphone.failure.*``).
"""

from __future__ import annotations

import math
import time

import numpy as np

from src.audio import sdl_native

LEVEL_MAX = 20
SAMPLE_RATE = 16000
CHUNK = 512
# -60 dBFS is silence, -10 dBFS a shout (the browser meter maps the same).
FLOOR_DB = -60.0
SPAN_DB = 50.0
# An open device that delivers no block, or only exact digital silence, for
# this long is blocked by the system (Windows/macOS privacy settings): a real
# microphone always carries some noise.
SILENT_AFTER_S = 3.0
# Causes shown to the player (keys ``option.microphone.failure.<cause>``).
FAILURES = ("no_capture", "no_device", "open_failed", "silent")
# The talk key keeps at most this much of one question.
RECORD_MAX_S = 30.0


def level_of(rms: float, maximum: int = LEVEL_MAX) -> int:
    db = 20.0 * math.log10(max(0.0, float(rms)) + 1e-9)
    return max(0, min(maximum, round((db - FLOOR_DB) / SPAN_DB * maximum)))


def _capture_names(sdl_audio) -> list:
    """Names of the capture devices; opens SDL's audio subsystem first when
    the game runs without sound (the mixer then never initialised it)."""
    try:
        return list(sdl_audio.get_audio_device_names(True))
    except Exception:  # noqa: BLE001 - "Audio system not initialised"
        from pygame._sdl2 import sdl2
        sdl2.init_subsystem(sdl2.INIT_AUDIO)
        return list(sdl_audio.get_audio_device_names(True))


class Microphone:
    """One capture device; ``level()`` is the newest loudness 0..LEVEL_MAX."""

    def __init__(self, clock=time.monotonic) -> None:
        self.device = None
        self.available = False
        self.tried = False
        self.failure = ""
        self.detail = ""
        self.name = ""
        self.blocks = 0
        # How the last stop closed the device: "sdl" (GIL released) or
        # "pygame" (fallback when pygame's SDL is out of reach).
        self.released = ""
        self._clock = clock
        self._opened_at = 0.0
        self._heard = False
        self._rms = 0.0
        # The talk key's recording: blocks of samples, or None (not recording).
        self._recording = None
        self._recorded = 0

    def _callback(self, _device, data) -> None:
        samples = np.frombuffer(bytes(data), dtype=np.float32)
        self.blocks += 1
        if samples.size and np.any(samples):
            self._heard = True
        self._rms = float(np.sqrt(np.mean(samples * samples))) if samples.size else 0.0
        recording = self._recording
        if recording is not None and self._recorded < RECORD_MAX_S * SAMPLE_RATE:
            recording.append(samples.copy())
            self._recorded += samples.size

    # -- the talk key ----------------------------------------------------------

    @property
    def recording(self) -> bool:
        return self._recording is not None

    def recorded_s(self) -> float:
        return self._recorded / SAMPLE_RATE

    def begin_recording(self) -> bool:
        """Keep the samples from now on (the device must be open)."""
        if self.device is None:
            return False
        self._recorded = 0
        self._recording = []
        return True

    def end_recording(self) -> np.ndarray:
        """The samples since ``begin_recording`` (mono float32, 16 kHz)."""
        blocks, self._recording = self._recording, None
        self._recorded = 0
        if not blocks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(blocks)[:int(RECORD_MAX_S * SAMPLE_RATE)]

    def start(self) -> bool:
        if self.device is not None:
            return True
        self.tried = True
        self.failure, self.detail = "", ""
        try:
            from pygame._sdl2 import audio as sdl_audio
        except Exception:  # noqa: BLE001 - a pygame without SDL2 capture
            return self._fail("no_capture")
        try:
            names = _capture_names(sdl_audio)
        except Exception as exc:  # noqa: BLE001 - no audio subsystem at all
            return self._fail("no_device", exc)
        if not names:
            return self._fail("no_device")
        try:
            # pygame 2.6 needs the device's name (None is refused with a
            # TypeError); the first one is the system's default input.
            self.device = sdl_audio.AudioDevice(
                devicename=str(names[0]), iscapture=True, frequency=SAMPLE_RATE,
                audioformat=sdl_audio.AUDIO_F32, numchannels=1, chunksize=CHUNK,
                allowed_changes=0, callback=self._callback)
            self.device.pause(0)
        except Exception as exc:  # noqa: BLE001 - no capture: the game runs on without
            self.device = None
            return self._fail("open_failed", exc)
        self.name = str(names[0])
        self.blocks = 0
        self._heard = False
        self._opened_at = self._clock()
        self.available = True
        return True

    def _fail(self, cause: str, exc=None) -> bool:
        self.device = None
        self.available = False
        self.failure = cause
        self.detail = " ".join(str(exc or "").split())[:80]
        return False

    def check(self) -> str:
        """The current failure cause ('' while it works): an open device that
        stays digitally silent is reported, and cleared once sound arrives."""
        if self.device is not None:
            if self._heard:
                self.failure = ""
            elif self._clock() - self._opened_at >= SILENT_AFTER_S:
                self.failure = "silent"
        return self.failure

    def stop(self) -> None:
        """Close the capture without ever hanging the game: pygame's own
        ``pause()``/``close()`` hold the GIL while SDL waits for a running
        callback that needs it (deadlock, 1.3.234).  SDL's close through
        ``ctypes`` releases the GIL; pygame's ``close()`` afterwards only
        forgets the closed id, so its finaliser cannot close another device
        that reuses it."""
        device, self.device = self.device, None
        self._rms = 0.0
        self._recording = None
        self._recorded = 0
        if device is None:
            return
        try:
            device_id = getattr(device, "deviceid", 0)
            if sdl_native.close_audio_device(device_id):
                self.released = "sdl"
            else:
                self.released = "pygame"
                device.pause(1)
            device.close()
        except Exception:  # noqa: BLE001 - closing a lost device
            pass

    def level(self) -> int:
        return level_of(self._rms) if self.device is not None else 0
