"""The uConsole's own microphone for noise discipline (opt-in, level only).

SDL2 capture through ``pygame._sdl2.audio``: the capture thread keeps only
the loudness of the newest block; nothing is recorded, stored or played.  No
device, no SDL support or a refused device leaves ``available`` False and the
game runs on without it (``src/core/game_noise.py``).
"""

from __future__ import annotations

import math

import numpy as np

LEVEL_MAX = 20
SAMPLE_RATE = 16000
CHUNK = 512
# -60 dBFS is silence, -10 dBFS a shout (the browser meter maps the same).
FLOOR_DB = -60.0
SPAN_DB = 50.0


def level_of(rms: float, maximum: int = LEVEL_MAX) -> int:
    db = 20.0 * math.log10(max(0.0, float(rms)) + 1e-9)
    return max(0, min(maximum, round((db - FLOOR_DB) / SPAN_DB * maximum)))


class Microphone:
    """One capture device; ``level()`` is the newest loudness 0..LEVEL_MAX."""

    def __init__(self) -> None:
        self.device = None
        self.available = False
        self.tried = False
        self._rms = 0.0

    def _callback(self, _device, data) -> None:
        samples = np.frombuffer(bytes(data), dtype=np.float32)
        self._rms = float(np.sqrt(np.mean(samples * samples))) if samples.size else 0.0

    def start(self) -> bool:
        if self.device is not None:
            return True
        self.tried = True
        try:
            from pygame._sdl2 import audio as sdl_audio
            if not sdl_audio.get_audio_device_names(True):
                return False
            self.device = sdl_audio.AudioDevice(
                devicename=None, iscapture=True, frequency=SAMPLE_RATE,
                audioformat=sdl_audio.AUDIO_F32, numchannels=1, chunksize=CHUNK,
                allowed_changes=0, callback=self._callback)
            self.device.pause(0)
        except Exception:  # noqa: BLE001 - no capture: the game runs on without
            self.device = None
            self.available = False
            return False
        self.available = True
        return True

    def stop(self) -> None:
        device, self.device = self.device, None
        self._rms = 0.0
        if device is not None:
            try:
                device.pause(1)
                device.close()
            except Exception:  # noqa: BLE001 - closing a lost device
                pass

    def level(self) -> int:
        return level_of(self._rms) if self.device is not None else 0
