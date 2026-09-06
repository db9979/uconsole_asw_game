"""Nicht-blockierende Pygame-Audioausgabe mit NumPy-Synthese."""

from collections import OrderedDict
from collections.abc import Callable

import numpy as np
import pygame

from src.audio.synthesis import fm_chirp, propeller_block, stereo_bearing, tone


class AudioEngine:
    """Audioausgabe; bei fehlendem Audiogeraet wird lautlos weiter simuliert."""

    def __init__(self, sample_rate: int = 22050, channels: int = 2,
                 enabled: bool = True, cache_size: int = 32):
        self.sample_rate = sample_rate
        self.channels = channels
        self.enabled = bool(enabled)
        self.available = False
        self._cache_size = max(0, cache_size)
        self._cache: OrderedDict[tuple, pygame.mixer.Sound] = OrderedDict()
        self._engine_channel = None
        self._sonar_channel = None
        self._engine_phase = 0.0
        self._engine_blocks = 0
        if not self.enabled:
            return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=sample_rate, size=-16,
                                  channels=channels, buffer=512, allowedchanges=0)
            mixer_format = pygame.mixer.get_init()
            if mixer_format is None:
                self.enabled = False
                return
            self.sample_rate, sample_format, self.channels = mixer_format
            # Do not restart a shared mixer or feed it incompatible PCM.
            if sample_format != -16 or self.channels not in (1, 2):
                self.enabled = False
                return
            if pygame.mixer.get_num_channels() < 3:
                pygame.mixer.set_num_channels(3)
            pygame.mixer.set_reserved(2)
            self._engine_channel = pygame.mixer.Channel(0)
            self._sonar_channel = pygame.mixer.Channel(1)
            self.available = True
        except pygame.error:
            self.enabled = False

    def _make_sound(self, samples: np.ndarray) -> pygame.mixer.Sound:
        pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype(np.int16)
        if self.channels == 2 and pcm.ndim == 1:
            pcm = np.repeat(pcm[:, None], 2, axis=1)
        return pygame.sndarray.make_sound(np.ascontiguousarray(pcm))

    def _sound(self, synthesize: Callable[[], np.ndarray],
               key: tuple) -> pygame.mixer.Sound | None:
        if not self.enabled or not self.available:
            return None
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached
        sound = self._make_sound(synthesize())
        self._cache[key] = sound
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return sound

    def play_ping(self, frequency_hz: float = 900.0, volume: float = 0.35) -> bool:
        sound = self._sound(
            lambda: fm_chirp(frequency_hz * .78, frequency_hz * 1.08,
                             .45, self.sample_rate, volume,
                             modulation_hz=7.0, modulation_depth_hz=12.0),
            ("ping", round(frequency_hz), round(volume, 2)))
        if sound is None:
            return False
        sound.play()
        return True

    def play_alert(self, kind: str = "danger") -> bool:
        """Kurze priorisierte Meldung fuer Stations- und Gefahrenaudio."""
        tones = {
            "launch": (620.0, 0.18, 0.18),
            "defense": (420.0, 0.12, 0.16),
            "danger": (180.0, 0.28, 0.28),
            "damage": (110.0, 0.35, 0.32),
        }
        frequency, duration, volume = tones.get(kind, tones["danger"])
        sound = self._sound(
            lambda: tone(frequency, duration, self.sample_rate, volume),
            ("alert", kind))
        if sound is None:
            return False
        sound.play()
        return True

    def update_engine(self, rpm: float, blade_count: int = 5,
                      cavitation: float = 0.0, volume: float = 0.15) -> bool:
        """Spielt einen kurzen Maschinenblock; Aufrufer sollte nur 4 Hz triggern."""
        if not self.enabled or not self.available:
            return False
        if self._engine_channel is not None and not self._engine_channel.get_busy():
            blade_hz = max(.1, rpm / 60 * max(1, blade_count))
            count = max(1, int(.25 * self.sample_rate))
            sound = self._sound(
                lambda: propeller_block(
                    rpm, blade_count, self.sample_rate, amplitude=volume,
                    cavitation=cavitation, phase=self._engine_phase,
                    seed=17 + self._engine_blocks),
                ("engine", self._engine_blocks, round(rpm), blade_count,
                 round(cavitation, 2), round(volume, 3)))
            if sound is None:
                return False
            self._engine_channel.play(sound)
            self._engine_phase = (self._engine_phase + 2 * np.pi * blade_hz
                                  * count / self.sample_rate) % (2 * np.pi)
            self._engine_blocks += 1
        return True

    def play_sonar(self, samples: np.ndarray, sample_rate: int,
                   volume: float = 0.4, bearing_deg: float | None = None,
                   listener_bearing_deg: float = 0.0) -> bool:
        """Play a mono float32 block once; False means invalid or queue full.

        Only the current and one pending sound are retained, never cached.
        """
        if not self.enabled or not self.available or self._sonar_channel is None:
            return False
        if (not isinstance(samples, np.ndarray) or samples.ndim != 1
                or samples.size < 2 or samples.dtype.kind not in "fiu"
                or not isinstance(sample_rate, (int, np.integer))
                or isinstance(sample_rate, (bool, np.bool_)) or sample_rate <= 0):
            return False
        try:
            volume = float(volume)
        except (TypeError, ValueError, OverflowError):
            return False
        if not np.isfinite(volume) or not np.all(np.isfinite(samples)):
            return False
        count = round(samples.size * self.sample_rate / int(sample_rate))
        if count < 2:
            return False
        try:
            if self._sonar_channel.get_queue() is not None:
                return False
            positions = np.arange(count, dtype=np.float64) * sample_rate / self.sample_rate
            signal = np.interp(positions, np.arange(samples.size), samples)
            signal = np.clip(signal, -1.0, 1.0) * np.clip(volume, 0.0, 1.0)
            fade_count = min(count // 2, max(2, round(self.sample_rate * 0.005)))
            fade = np.linspace(0.0, 1.0, fade_count)
            signal[:fade_count] *= fade
            signal[-fade_count:] *= fade[::-1]
            if self.channels == 2 and bearing_deg is not None:
                signal = stereo_bearing(signal, bearing_deg, listener_bearing_deg)
            sound = self._make_sound(signal)
            if self._sonar_channel.get_busy():
                self._sonar_channel.queue(sound)
            else:
                self._sonar_channel.play(sound)
        except (pygame.error, TypeError, ValueError, OverflowError):
            return False
        return True

    def stop_sonar(self) -> None:
        """Clear current and pending sonar audio on pause or tuning changes."""
        if self._sonar_channel is not None:
            had_queue = self._sonar_channel.get_queue() is not None
            self._sonar_channel.stop()
            # Some SDL backends promote a queued sound during stop().
            if had_queue:
                self._sonar_channel.stop()

    def stop(self) -> None:
        self.stop_sonar()
        if self._engine_channel is not None:
            self._engine_channel.stop()

    def shutdown(self) -> None:
        self.stop()
        self._cache.clear()
        self.available = False
