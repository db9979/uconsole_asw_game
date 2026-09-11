"""Nicht-blockierende Pygame-Audioausgabe mit NumPy-Synthese."""

import os
import time
from collections import OrderedDict
from collections.abc import Callable
from copy import deepcopy

import numpy as np
import pygame

from src.audio.receiver import smooth_limit
from src.audio.synthesis import fm_chirp, propeller_block, stereo_bearing, tone
from src.core import config


class AudioEngine:
    """Audioausgabe; bei fehlendem Audiogeraet wird lautlos weiter simuliert."""

    DEBUG_LOG_MAX_BYTES = 1_000_000
    ENGINE_CHANNEL = 0
    SONAR_CHANNEL = 1
    PING_CHANNEL = 2
    ALERT_CHANNEL = 3
    FADE_MS = 35
    SONAR_HOLD_MAX = 2

    # Post-limiter per-channel PCM ceilings, NOT input volume caps. Their
    # weighted sum is .9155, including hard left/right pan and hostile input.
    # This budgets our reserved buses only, not unrelated shared-mixer users.
    SOURCE_LIMITS = {"engine": .18, "sonar": .55, "ping": .40, "alert": .32}
    CHANNEL_GAINS = {"engine": .50, "sonar": .65, "ping": .65, "alert": .65}

    def __init__(self, sample_rate: int = 22050,
                 channels: int = config.AUDIO_CHANNELS,
                 enabled: bool = True, cache_size: int = 32):
        self.sample_rate = sample_rate
        self.channels = channels
        self.configured_enabled = bool(enabled)
        self.enabled = self.configured_enabled
        self.available = False
        self.fatal_error = False
        self._cache_size = max(0, cache_size)
        self._cache: OrderedDict[tuple, pygame.mixer.Sound] = OrderedDict()
        self._engine_channel = None
        self._sonar_channel = None
        self._ping_channel = None
        self._alert_channel = None
        self._engine_phase = 0.0
        self._engine_shaft_phase = 0.0
        self._engine_blocks = 0
        self._engine_rng = np.random.default_rng(17)
        self._engine_filter_state = np.zeros(5, dtype=np.float64)
        self._engine_fading = False
        self._sonar_fading = False
        self._sonar_rate = None
        self._sonar_input_count = 0
        self._sonar_output_count = 0
        self._sonar_previous = None
        self._sonar_last_sound = None
        self._sonar_hold_streak = 0
        self.sonar_holds = 0
        self.engine_dropped_blocks = 0
        self.engine_underruns = 0
        self.sonar_dropped_blocks = 0
        self.alert_dropped_events = 0
        self._audio_debug_enabled = (
            os.environ.get("U_JAGD_AUDIO_DEBUG", "") not in ("", "0"))
        self._audio_debug_due = 0.0
        if not self.enabled:
            return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=sample_rate, size=-16,
                                  channels=channels,
                                  buffer=config.AUDIO_MIXER_BUFFER_SAMPLES,
                                  allowedchanges=0)
            mixer_format = pygame.mixer.get_init()
            if mixer_format is None:
                self.enabled = False
                return
            self.sample_rate, sample_format, self.channels = mixer_format
            # Do not restart a shared mixer or feed it incompatible PCM.
            if sample_format != -16 or self.channels not in (1, 2):
                self.enabled = False
                return
            if pygame.mixer.get_num_channels() < 4:
                pygame.mixer.set_num_channels(4)
            pygame.mixer.set_reserved(4)
            self._engine_channel = pygame.mixer.Channel(self.ENGINE_CHANNEL)
            self._sonar_channel = pygame.mixer.Channel(self.SONAR_CHANNEL)
            self._ping_channel = pygame.mixer.Channel(self.PING_CHANNEL)
            self._alert_channel = pygame.mixer.Channel(self.ALERT_CHANNEL)
            for name, channel in (("engine", self._engine_channel),
                                  ("sonar", self._sonar_channel),
                                  ("ping", self._ping_channel),
                                  ("alert", self._alert_channel)):
                channel.set_volume(self.CHANNEL_GAINS[name])
            self.available = True
        except (pygame.error, TypeError, ValueError, OverflowError):
            self.fatal_error = True
            self.enabled = False

    def availability_status(self) -> dict:
        """Detached durable status; queue pressure is not device failure."""
        return {
            "global_enabled": self.configured_enabled,
            "device_available": bool(self.available),
            "fatal_error": bool(self.fatal_error),
        }

    def _latch_device_error(self) -> None:
        """Latch only confirmed mixer loss, not a transient channel failure."""
        try:
            lost = pygame.mixer.get_init() is None
        except pygame.error:
            lost = True
        if lost:
            self.fatal_error = True
            self.available = False

    def _make_sound(self, samples: np.ndarray, bus: str) -> pygame.mixer.Sound:
        ceiling = self.SOURCE_LIMITS[bus]
        samples = smooth_limit(samples, knee=.75 * ceiling, ceiling=ceiling)
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
        sound = self._make_sound(synthesize(), key[0])
        self._cache[key] = sound
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return sound

    def play_ping(self, frequency_hz: float = 900.0, volume: float = 0.35) -> bool:
        if (not self.enabled or not self.available or self._ping_channel is None):
            return False
        try:
            if self._ping_channel.get_busy():
                return False
            volume = np.clip(float(volume), 0.0, self.SOURCE_LIMITS["ping"])
            sound = self._sound(
                lambda: fm_chirp(frequency_hz * .78, frequency_hz * 1.08,
                                 .45, self.sample_rate, volume,
                                 modulation_hz=7.0, modulation_depth_hz=12.0),
                ("ping", round(frequency_hz), round(float(volume), 2)))
            if sound is None:
                return False
            self._ping_channel.play(sound)
        except pygame.error:
            self._latch_device_error()
            return False
        except (TypeError, ValueError, OverflowError):
            return False
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
        if (not self.enabled or not self.available or self._alert_channel is None):
            return False
        try:
            if (self._alert_channel.get_busy()
                    and self._alert_channel.get_queue() is not None):
                self.alert_dropped_events += 1
                return False
            volume = min(volume, self.SOURCE_LIMITS["alert"])
            sound = self._sound(
                lambda: tone(frequency, duration, self.sample_rate, volume),
                ("alert", kind))
            if sound is None:
                return False
            if self._alert_channel.get_busy():
                self._alert_channel.queue(sound)
            else:
                self._alert_channel.play(sound)
        except pygame.error:
            self._latch_device_error()
            return False
        except (TypeError, ValueError, OverflowError):
            return False
        return True

    def update_engine(self, rpm: float, blade_count: int = 5,
                      cavitation: float = 0.0, volume: float = 0.15) -> bool:
        """Queue a machine block; callers should feed it at approximately 4 Hz."""
        if not self.enabled or not self.available or self._engine_channel is None:
            return False
        try:
            volume = float(volume)
            if not np.isfinite(volume):
                return False
            volume = float(np.clip(volume, 0.0, self.SOURCE_LIMITS["engine"]))
            if volume == 0.0:
                self.stop_engine()
                return True
            busy = self._engine_channel.get_busy()
            if busy and self._engine_channel.get_queue() is not None:
                self.engine_dropped_blocks += 1
                return False
            if not busy and self._engine_blocks:
                self.engine_underruns += 1
            blade_hz = max(.1, rpm / 60 * max(1, blade_count))
            count = max(1, int(.25 * self.sample_rate))
            next_filter = self._engine_filter_state.copy()
            rng_state = deepcopy(self._engine_rng.bit_generator.state)
            try:
                signal = propeller_block(
                    rpm, blade_count, self.sample_rate, amplitude=volume,
                    cavitation=cavitation, phase=self._engine_phase,
                    rng=self._engine_rng, filter_state=next_filter,
                    shaft_phase=self._engine_shaft_phase)
                sound = self._make_sound(signal, "engine")
                if busy:
                    self._engine_channel.queue(sound)
                else:
                    self._engine_channel.play(sound, fade_ms=self.FADE_MS)
            except (pygame.error, TypeError, ValueError, OverflowError):
                self._engine_rng.bit_generator.state = rng_state
                raise
            self._engine_filter_state = next_filter
            self._engine_phase = (self._engine_phase + 2 * np.pi * blade_hz
                                   * count / self.sample_rate) % (2 * np.pi)
            self._engine_shaft_phase = (
                self._engine_shaft_phase + 2 * np.pi * blade_hz / max(1, blade_count)
                * count / self.sample_rate) % (2 * np.pi)
            self._engine_blocks += 1
            self._engine_fading = False
        except pygame.error:
            self._latch_device_error()
            return False
        except (TypeError, ValueError, OverflowError):
            return False
        return True

    def play_sonar(self, samples: np.ndarray, sample_rate: int,
                   volume: float = 0.4, bearing_deg: float | None = None,
                   listener_bearing_deg: float = 0.0,
                   hold: bool = False) -> bool:
        """Play a mono float32 block once; False means invalid or queue full.

        With hold=True an idle channel re-plays the previous block (bounded to
        SONAR_HOLD_MAX consecutive holds) before the new one, so simulation
        clock lag does not open a silent gap at the 4 Hz block boundary.
        Only the current and one pending sound are retained, never cached.
        Volume spans 0..1 before the bus limiter. Linear streaming resampling
        delays by one source sample, so interpolation never predicts a future
        sample or replaces the start of every block with a constant crossfade.
        On a sequence gap/preview discontinuity call stop_sonar(immediate=True)
        first. False never advances resampler state: retry the same block, not
        its successor.
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
                self.sonar_dropped_blocks += 1
                return False
            source_rate = int(sample_rate)
            if self._sonar_rate != source_rate:
                input_start = output_start = 0
                previous = None
            else:
                input_start = self._sonar_input_count
                output_start = self._sonar_output_count
                previous = self._sonar_previous
            # Ceil chooses exactly the output instants before the input end;
            # unlike round, it never needs a second prior sample at a join.
            output_end = ((input_start + samples.size) * self.sample_rate
                          + source_rate - 1) // source_rate
            count = output_end - output_start
            if count < 2:
                return False
            positions = (np.arange(output_start, output_end, dtype=np.float64)
                         * source_rate / self.sample_rate - input_start - 1)
            values = np.concatenate(([0.0 if previous is None else previous], samples))
            signal = np.interp(positions, np.arange(-1, samples.size), values)
            # Headphone volume precedes the soft limiter so turning it down
            # also reduces limiter compression, not only final loudness.
            signal *= np.clip(volume, 0.0, 1.0)
            if previous is None:
                fade_count = min(count, max(2, round(self.sample_rate * 0.005)))
                signal[:fade_count] *= np.linspace(0.0, 1.0, fade_count)
            if self.channels == 2 and bearing_deg is not None:
                signal = stereo_bearing(signal, bearing_deg, listener_bearing_deg)
            sound = self._make_sound(signal, "sonar")
            if self._sonar_channel.get_busy():
                self._sonar_channel.queue(sound)
                self._sonar_hold_streak = 0
            elif (hold and self._sonar_last_sound is not None
                    and self._sonar_hold_streak < self.SONAR_HOLD_MAX):
                self._sonar_channel.play(self._sonar_last_sound,
                                         fade_ms=self.FADE_MS)
                self._sonar_channel.queue(sound)
                self.sonar_holds += 1
                self._sonar_hold_streak += 1
            else:
                self._sonar_channel.play(sound, fade_ms=self.FADE_MS)
                self._sonar_hold_streak = 0
            self._sonar_last_sound = sound
            self._sonar_rate = source_rate
            self._sonar_input_count = input_start + samples.size
            self._sonar_output_count = output_end
            self._sonar_previous = float(samples[-1])
            self._sonar_fading = False
        except pygame.error:
            self._latch_device_error()
            return False
        except (TypeError, ValueError, OverflowError):
            return False
        return True

    def stop_sonar(self, *, immediate: bool = False) -> None:
        """Fade a normal stop; discard queued old-beam audio on discontinuity.

        SDL can promote queued audio after a fade, so sequence gaps, retunes
        and sampled previews must use immediate=True before restarting.
        """
        if immediate:
            self._hard_stop(self._sonar_channel)
            self._sonar_fading = True
        elif self._sonar_channel is not None and not self._sonar_fading:
            try:
                if self._sonar_channel.get_busy():
                    self._sonar_channel.fadeout(self.FADE_MS)
                self._sonar_fading = True
            except pygame.error:
                pass
        self._reset_sonar_stream()

    def hold_sonar(self) -> bool:
        """Replay one retained block when a 1x producer has no new block."""
        if (not self.enabled or not self.available or self._sonar_channel is None
                or self._sonar_last_sound is None
                or self._sonar_hold_streak >= self.SONAR_HOLD_MAX):
            return False
        try:
            if (self._sonar_channel.get_busy()
                    or self._sonar_channel.get_queue() is not None):
                return False
            self._sonar_channel.play(self._sonar_last_sound,
                                     fade_ms=self.FADE_MS)
            self._sonar_hold_streak += 1
            self.sonar_holds += 1
            return True
        except pygame.error:
            return False

    def _reset_sonar_stream(self) -> None:
        self._sonar_rate = None
        self._sonar_input_count = 0
        self._sonar_output_count = 0
        self._sonar_previous = None
        self._sonar_last_sound = None
        self._sonar_hold_streak = 0

    def stop_engine(self) -> None:
        """Fade normal engine transitions without repeatedly restarting the fade."""
        if self._engine_channel is not None and not self._engine_fading:
            try:
                if self._engine_channel.get_busy():
                    self._engine_channel.fadeout(self.FADE_MS)
                self._engine_fading = True
            except pygame.error:
                pass

    def stop(self) -> None:
        self.stop_sonar()
        self.stop_engine()
        self._hard_stop(self._ping_channel)
        self._hard_stop(self._alert_channel)

    def debug_log(self, dt: float, receiver=None) -> None:
        """Optional 1 Hz diagnostics line, enabled via U_JAGD_AUDIO_DEBUG=1.

        Appends one line per second of wall time to audio_debug.log inside the
        save directory, reporting delivery counters and mixer shape for
        on-device (uConsole) crackle diagnosis. No-op unless enabled.
        """
        if not self._audio_debug_enabled:
            return
        try:
            wall_dt = float(dt)
        except (TypeError, ValueError, OverflowError):
            return
        if not np.isfinite(wall_dt) or wall_dt <= 0.0:
            return
        self._audio_debug_due += wall_dt
        if self._audio_debug_due < 1.0:
            return
        self._audio_debug_due %= 1.0
        evictions = getattr(receiver, "evicted_blocks", 0)
        line = ("t={t:.1f} engine_drops={ed} underruns={u} "
                "sonar_drops={sd} sonar_holds={sh} alert_drops={ad} "
                "evictions={ev} rate={r} ch={c}\n").format(
            t=time.monotonic(), ed=self.engine_dropped_blocks,
            u=self.engine_underruns, sd=self.sonar_dropped_blocks,
            sh=self.sonar_holds, ad=self.alert_dropped_events, ev=evictions,
            r=self.sample_rate, c=self.channels)
        try:
            root = os.path.abspath(os.path.expanduser(os.fspath(config.SAVE_DIR)))
            if os.path.lexists(root) and os.path.islink(root):
                return
            os.makedirs(root, mode=0o700, exist_ok=True)
            if os.path.islink(root) or not os.path.isdir(root):
                return
            path = os.path.join(root, "audio_debug.log")
            directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            directory_flags |= getattr(os, "O_NOFOLLOW", 0)
            directory = os.open(root, directory_flags)
            flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
            flags |= getattr(os, "O_NOFOLLOW", 0)
            try:
                descriptor = os.open(os.path.basename(path), flags, 0o600,
                                     dir_fd=directory)
                with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
                    if os.fstat(handle.fileno()).st_size >= self.DEBUG_LOG_MAX_BYTES:
                        handle.seek(0)
                        handle.truncate()
                    handle.write(line)
            finally:
                os.close(directory)
        except OSError:
            pass

    @staticmethod
    def _hard_stop(channel) -> None:
        if channel is None:
            return
        try:
            had_queue = channel.get_queue() is not None
            channel.stop()
            # Some SDL backends promote a queued sound during stop().
            if had_queue:
                channel.stop()
        except pygame.error:
            pass

    def shutdown(self) -> None:
        for channel in (self._engine_channel, self._sonar_channel,
                        self._ping_channel, self._alert_channel):
            self._hard_stop(channel)
        self._reset_sonar_stream()
        self._cache.clear()
        self.available = False
