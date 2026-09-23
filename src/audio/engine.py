"""Nicht-blockierende Pygame-Audioausgabe mit NumPy-Synthese."""

import os
import time
from collections import OrderedDict, deque
from collections.abc import Callable
import threading
import weakref

import numpy as np
import pygame

from src.audio.receiver import smooth_limit
from src.audio.synthesis import (active_sonar_ping, combat_effect,
                                 stereo_bearing, tone)
from src.core import config
from src.core.debuglog import append_bounded_log


class AudioEngine:
    """Audioausgabe; bei fehlendem Audiogeraet wird lautlos weiter simuliert."""

    DEBUG_LOG_MAX_BYTES = 1_000_000
    SONAR_CHANNEL = 1
    PING_CHANNEL = 2
    ALERT_CHANNEL = 3
    FADE_MS = 35
    SONAR_HOLD_MAX = 2
    SONAR_BUFFER_S = 1.0
    SONAR_BUFFER_MAX_S = 2.0

    # Post-limiter per-channel PCM ceilings, NOT input volume caps. The gains
    # keep all three reserved buses below full scale even at coincident peaks.
    SOURCE_LIMITS = {"sonar": .55, "ping": .40, "alert": .32}
    CHANNEL_GAINS = {"sonar": .58, "ping": .58, "alert": .58}

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
        self._sonar_channel = None
        self._ping_channel = None
        self._alert_channel = None
        self._sonar_fading = False
        self._sonar_rate = None
        self._sonar_input_count = 0
        self._sonar_output_count = 0
        self._sonar_previous = None
        self._sonar_last_sound = None
        self._sonar_repeat_signal = None
        self._sonar_repeat_sound = None
        self._sonar_neutral_sound = None
        self._sonar_last_fresh_at = None
        self.sonar_stale = False
        self.sonar_local_underruns = 0
        self.sonar_neutral_blocks = 0
        self._sonar_hold_streak = 0
        self._sonar_buffer = deque()
        self._sonar_buffer_duration = 0.0
        self._sonar_buffered = False
        self._sonar_primed = False
        self._sonar_lock = threading.RLock()
        self._sonar_wake = threading.Event()
        self._sonar_exit = threading.Event()
        self._sonar_worker = None
        self._sonar_finalizer = weakref.finalize(
            self, AudioEngine._stop_orphaned_worker,
            self._sonar_exit, self._sonar_wake)
        self._preview_sound = None
        self._preview_channel = None
        self.sonar_holds = 0
        self.sonar_dropped_blocks = 0
        self.alert_dropped_events = 0
        self._audio_debug_enabled = (
            os.environ.get("U_JAGD_AUDIO_DEBUG", "") not in ("", "0"))
        self._audio_debug_due = 0.0
        self._audio_debug_receiver_last = None
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
            self._sonar_channel = pygame.mixer.Channel(self.SONAR_CHANNEL)
            self._ping_channel = pygame.mixer.Channel(self.PING_CHANNEL)
            self._alert_channel = pygame.mixer.Channel(self.ALERT_CHANNEL)
            for name, channel in (("sonar", self._sonar_channel),
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
                lambda: active_sonar_ping(frequency_hz, self.sample_rate,
                                          volume),
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

    def play_effect(self, kind: str) -> bool:
        """Play one bounded local combat/handling effect on the alert bus."""
        if kind not in {"torpedo_launch", "missile_launch", "gunfire",
                        "explosion", "water_entry"}:
            return False
        if (not self.enabled or not self.available or self._alert_channel is None):
            return False
        try:
            if (self._alert_channel.get_busy()
                    and self._alert_channel.get_queue() is not None):
                self.alert_dropped_events += 1
                return False
            sound = self._sound(
                lambda: combat_effect(kind, self.sample_rate,
                                      self.SOURCE_LIMITS["alert"]),
                ("alert", "effect", kind, self.sample_rate))
            if sound is None:
                return False
            if self._alert_channel.get_busy():
                self._alert_channel.queue(sound)
            else:
                self._alert_channel.play(sound)
            return True
        except pygame.error:
            self._latch_device_error()
            return False
        except (TypeError, ValueError, OverflowError):
            return False

    def play_alert(self, kind: str = "danger") -> bool:
        """Kurze priorisierte Meldung fuer Stations- und Gefahrenaudio."""
        tones = {
            "launch": (620.0, 0.18, 0.18),
            "defense": (420.0, 0.12, 0.16),
            "esm": (1040.0, 0.16, 0.16),
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

    def play_sonar(self, samples: np.ndarray, sample_rate: int,
                   volume: float = 0.4, bearing_deg: float | None = None,
                   listener_bearing_deg: float = 0.0,
                   hold: bool = False, buffered: bool = False) -> bool:
        """Play a mono float32 block once; False means invalid or queue full.

        With hold=True an idle channel re-plays the previous block (bounded to
        SONAR_HOLD_MAX consecutive holds) before the new one, so simulation
        clock lag does not open a silent gap at the 4 Hz block boundary.
        Buffered local listening retains at most two seconds of sounds. The
        mixer still holds only its current and next sound.
        Volume spans 0..1 before the bus limiter. Linear streaming resampling
        delays by one source sample, so interpolation never predicts a future
        sample or replaces the start of every block with a constant crossfade.
        An intentional stream change calls stop_sonar(immediate=True); a lost
        receiver block calls discontinue_sonar_input() so queued audio survives.
        False never advances resampler state: retry the same block, not its successor.
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
            with self._sonar_lock:
                if buffered:
                    if self._sonar_buffer_duration + samples.size / sample_rate > self.SONAR_BUFFER_MAX_S + 1e-6:
                        self.sonar_dropped_blocks += 1
                        return False
                elif self._sonar_channel.get_queue() is not None:
                    self.sonar_dropped_blocks += 1
                    return False
            source_rate = int(sample_rate)
            if self._sonar_rate != source_rate or self.sonar_stale:
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
            if buffered:
                with self._sonar_lock:
                    self._sonar_buffered = True
                    self._sonar_buffer.append((sound, count / self.sample_rate,
                                               signal.copy()))
                    self._sonar_buffer_duration += count / self.sample_rate
                    if self._sonar_worker is None:
                        self._sonar_worker = threading.Thread(
                            target=AudioEngine._pump_sonar,
                            args=(weakref.ref(self), self._sonar_wake,
                                  self._sonar_exit),
                            name="u-jagd-sonar-audio", daemon=True)
                        self._sonar_worker.start()
                    self._sonar_wake.set()
            elif self._sonar_channel.get_busy():
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

    @staticmethod
    def _stop_orphaned_worker(exit_event, wake):
        exit_event.set()
        wake.set()

    @staticmethod
    def _pump_sonar(reference, wake, exit_event) -> None:
        """Feed the reserved mixer channel while the simulation thread stalls."""
        while not exit_event.is_set():
            engine = reference()
            if engine is None:
                return
            active = engine._sonar_buffered and engine._sonar_primed
            del engine
            wake.wait(.02 if active else None)
            wake.clear()
            engine = reference()
            if engine is None:
                return
            engine._pump_sonar_once()
            del engine

    def _pump_sonar_once(self) -> None:
        with self._sonar_lock:
            if (not self._sonar_buffered or not self.available
                    or pygame.mixer.get_init() is None):
                return
            try:
                if not self._sonar_primed:
                    if self._sonar_buffer_duration < self.SONAR_BUFFER_S - 1e-6:
                        return
                    self._sonar_primed = True
                if self._sonar_channel.get_queue() is not None:
                    return
                if self._sonar_buffer:
                    sound, duration, signal = self._sonar_buffer.popleft()
                    self._sonar_buffer_duration = max(0.0, self._sonar_buffer_duration - duration)
                    self._sonar_repeat_signal = signal
                    self._sonar_repeat_sound = None
                    self._sonar_last_fresh_at = time.monotonic()
                    self.sonar_stale = False
                elif self._sonar_last_fresh_at is None:
                    return
                elif time.monotonic() - self._sonar_last_fresh_at < 2.0:
                    if self._sonar_repeat_sound is None:
                        signal = self._sonar_repeat_signal.copy()
                        fade = min(len(signal), max(2, round(self.sample_rate * .01)))
                        weight = np.linspace(0.0, 1.0, fade)
                        if signal.ndim == 2:
                            weight = weight[:, None]
                        signal[:fade] = signal[-1] * (1 - weight) + signal[:fade] * weight
                        self._sonar_repeat_sound = self._make_sound(signal, "sonar")
                    sound = self._sonar_repeat_sound
                    self.sonar_holds += 1
                    self.sonar_local_underruns += 1
                else:
                    self.sonar_stale = True
                    self._sonar_previous = None
                    if self._sonar_neutral_sound is None:
                        count = max(2, round(self.sample_rate * .25))
                        noise = np.random.default_rng(1701).uniform(-.006, .006, count)
                        fade = min(count // 2, max(2, round(self.sample_rate * .01)))
                        noise[:fade] *= np.linspace(0.0, 1.0, fade)
                        noise[-fade:] *= np.linspace(1.0, 0.0, fade)
                        self._sonar_neutral_sound = self._make_sound(noise, "sonar")
                    sound = self._sonar_neutral_sound
                    self.sonar_neutral_blocks += 1
                if self._sonar_channel.get_busy():
                    self._sonar_channel.queue(sound)
                else:
                    self._sonar_channel.play(sound, fade_ms=self.FADE_MS)
            except pygame.error:
                self._latch_device_error()

    def stop_sonar(self, *, immediate: bool = False) -> None:
        """Fade a normal stop; discard queued old-beam audio on discontinuity.

        SDL can promote queued audio after a fade, so sequence gaps, retunes
        and sampled previews must use immediate=True before restarting.
        The immediate hard stop is latched: repeat calls while the channel is
        already idle only reset the stream state, they never re-issue stop().
        """
        with self._sonar_lock:
            if immediate or self._sonar_buffered:
                if not self._sonar_fading:
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

    def discontinue_sonar_input(self) -> None:
        """Restart resampling after a lost receiver block without cutting playback."""
        with self._sonar_lock:
            self._sonar_rate = None
            self._sonar_input_count = 0
            self._sonar_output_count = 0
            self._sonar_previous = None
            self._sonar_last_sound = None
            self._sonar_hold_streak = 0

    def hold_sonar(self) -> bool:
        """Replay one retained block when a 1x producer has no new block."""
        if (self._sonar_buffered or not self.enabled or not self.available or self._sonar_channel is None
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
        self._sonar_buffer.clear()
        self._sonar_buffer_duration = 0.0
        self._sonar_buffered = False
        self._sonar_primed = False
        self._sonar_rate = None
        self._sonar_input_count = 0
        self._sonar_output_count = 0
        self._sonar_previous = None
        self._sonar_last_sound = None
        self._sonar_repeat_signal = None
        self._sonar_repeat_sound = None
        self._sonar_last_fresh_at = None
        self.sonar_stale = False
        self._sonar_hold_streak = 0

    def stop(self) -> None:
        self.stop_sonar()
        self._hard_stop(self._ping_channel)
        self._hard_stop(self._alert_channel)

    def play_unit_preview(self, synth: Callable[[], np.ndarray], key: tuple,
                          volume: float = 0.9, loops: int = -1) -> bool:
        """Reference clip on a free, non-reserved channel; loops by default.

        ``synth`` returns a float32 mono array at the active mixer rate; the
        resulting sound is LRU-cached under ``key`` (first element selects
        the bus limiter). Replaces any earlier preview. Deliberately not reached
        by stop(), so the editor's per-frame stop() never cuts a sample.
        """
        if not self.enabled or not self.available:
            return False
        try:
            volume = float(volume)
            if not np.isfinite(volume):
                return False
            if not isinstance(loops, int) or isinstance(loops, bool):
                return False
            self.stop_preview()
            sound = self._sound(synth, key)
            if sound is None:
                return False
            sound.set_volume(float(np.clip(volume, 0.0, 1.0)))
            channel = sound.play(loops)
            if channel is None:
                return False
            self._preview_sound = sound
            self._preview_channel = channel
            return True
        except pygame.error:
            self._latch_device_error()
            self._preview_sound = None
            self._preview_channel = None
            return False
        except (TypeError, ValueError, OverflowError):
            return False

    def stop_preview(self) -> None:
        """Stop the unit-preview clip; deliberately not part of stop(), so the
        editor's per-frame stop() never cuts a reference sample."""
        channel = self._preview_channel
        self._preview_channel = None
        self._preview_sound = None
        if channel is not None:
            try:
                channel.stop()
            except pygame.error:
                self._latch_device_error()

    def preview_playing(self) -> bool:
        """True while a unit-preview clip is on its channel."""
        channel = self._preview_channel
        if channel is None:
            return False
        try:
            return bool(channel.get_busy())
        except pygame.error:
            return False

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
        receiver_blocks = getattr(receiver, "sequence", -1) + 1
        produced = (0 if self._audio_debug_receiver_last is None else
                    max(0, receiver_blocks - self._audio_debug_receiver_last))
        self._audio_debug_receiver_last = receiver_blocks
        line = ("t={t:.1f} receiver_blocks_per_s={rb} sonar_drops={sd} "
                "sonar_holds={sh} alert_drops={ad} "
                "sonar_underruns={su} sonar_neutral={sn} sonar_stale={ss} "
                "buffer_s={bs:.2f} evictions={ev} rate={r} ch={c}\n").format(
            t=time.monotonic(), sd=self.sonar_dropped_blocks,
            sh=self.sonar_holds, ad=self.alert_dropped_events, ev=evictions,
            rb=produced,
            su=self.sonar_local_underruns, sn=self.sonar_neutral_blocks,
            ss=int(self.sonar_stale), bs=self._sonar_buffer_duration,
            r=self.sample_rate, c=self.channels)
        append_bounded_log(config.SAVE_DIR, "audio_debug.log", line,
                           self.DEBUG_LOG_MAX_BYTES)

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
        self._sonar_exit.set()
        self._sonar_wake.set()
        if self._sonar_worker is not None:
            self._sonar_worker.join(timeout=1.0)
        for channel in (self._sonar_channel, self._ping_channel,
                        self._alert_channel):
            self._hard_stop(channel)
        self.stop_preview()
        self._reset_sonar_stream()
        self._cache.clear()
        self.available = False
