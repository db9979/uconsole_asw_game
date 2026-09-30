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
from src.audio.synthesis import (active_sonar_ping, atmosphere_effect, boat_effect,
                                 combat_effect,
                                 sonar_echo, stereo_bearing, stereo_pan,
                                 tone)
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
    # Buffered listening starts once SONAR_BUFFER_S is queued (the standing
    # lead behind the display) and retains at most SONAR_BUFFER_MAX_S. The
    # maximum must cover target + SIM_CATCHUP_MAX_S + one block (with margin),
    # so a catch-up burst after a long frame never rejects a block (a rejected
    # block would be evicted from the receiver's two-block window: a gap).
    SONAR_BUFFER_S = 1.5
    SONAR_BUFFER_MAX_S = 5.0
    # Elastic buffered playback: the queued (not yet mixer-held) duration is
    # steered towards SONAR_TARGET_S by resampling at most SONAR_RATE_MAX
    # faster or slower, in SONAR_RATE_STEP increments. After an underrun the
    # queue refills to SONAR_REFILL_S under concealment instead of stuttering.
    # The 1.5 s lead outlasts main-thread stalls (Remote Crew publication,
    # catch-up frames) that the 2 % steering could never make up.
    SONAR_TARGET_S = 1.5
    SONAR_RATE_MAX = 0.02
    SONAR_RATE_STEP = 0.0025
    SONAR_RATE_GAIN = 0.05
    SONAR_LEVEL_SMOOTHING = 0.05
    SONAR_REFILL_S = 1.0
    SONAR_STALE_S = 3.0
    SONAR_CONCEAL_GRAIN_S = 0.128
    # A pump iteration later than this counts as late: the mixer holds only
    # the current and one queued block, so a starved worker lets it run dry.
    SONAR_PUMP_LATE_S = 0.25

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
        # Local one-shot effects (pings, echoes, combat, alerts). Off while the
        # uConsole plays the submarine: it must never hear the frigate's cues.
        self.local_effects = True
        self.available = False
        self.fatal_error = False
        self._cache_size = max(0, cache_size)
        self._cache: OrderedDict[tuple, pygame.mixer.Sound] = OrderedDict()
        self._sonar_channel = None
        self._ping_channel = None
        self._alert_channel = None
        self._sonar_fading = False
        self._sonar_rate = None
        self._sonar_out_rate = None
        self._sonar_input_count = 0
        self._sonar_output_count = 0
        self._sonar_previous = None
        self._sonar_last_sound = None
        self._sonar_history = deque(maxlen=2)
        self._sonar_last_value = None
        self._sonar_tail_value = None
        self._sonar_concealing = False
        self._sonar_refilling = False
        self._sonar_conceal_seed = 0x5A17
        self._sonar_level_ema = None
        self.sonar_rate_adjust = 0.0
        self.sonar_concealed_blocks = 0
        self._sonar_neutral_sound = None
        self._sonar_last_fresh_at = None
        self.sonar_stale = False
        self.sonar_local_underruns = 0
        self.sonar_neutral_blocks = 0
        # True audible gaps: the primed mixer channel was found idle.
        self.sonar_channel_idle = 0
        # Worker scheduling: iterations later than SONAR_PUMP_LATE_S, and the
        # longest gap between two iterations since the last debug line.
        self.sonar_pump_late = 0
        self.sonar_pump_late_max_s = 0.0
        self._sonar_pump_last_at = None
        # Receiver sequence breaks seen by the producer (retunes and blocks
        # the frame loop never got to play before the receiver replaced them).
        self.sonar_input_gaps = 0
        # Queued sounds found stranded on an idle channel (see
        # _release_stranded_queue) and sonar workers restarted after dying.
        self.sonar_queue_stranded = 0
        self._sonar_stranded_candidate = None
        self.sonar_worker_restarts = 0
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

    def _make_sound(self, samples: np.ndarray, bus: str,
                    pan: float | None = None) -> pygame.mixer.Sound:
        ceiling = self.SOURCE_LIMITS[bus]
        if self.channels == 2 and pan is not None and np.ndim(samples) == 1:
            # Directional hearing: the sound sits where it was heard.
            samples = stereo_pan(samples, pan)
        samples = smooth_limit(samples, knee=.75 * ceiling, ceiling=ceiling)
        pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype(np.int16)
        if self.channels == 2 and pcm.ndim == 1:
            pcm = np.repeat(pcm[:, None], 2, axis=1)
        return pygame.sndarray.make_sound(np.ascontiguousarray(pcm))

    def _sound(self, synthesize: Callable[[], np.ndarray],
               key: tuple, pan: float | None = None) -> pygame.mixer.Sound | None:
        if not self.enabled or not self.available:
            return None
        if pan is not None:
            pan = float(np.clip(pan, -1.0, 1.0))
            key = key + (("pan", round(pan, 3)),)
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached
        sound = self._make_sound(synthesize(), key[0], pan)
        self._cache[key] = sound
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return sound

    def play_ping(self, frequency_hz: float = 900.0, volume: float = 0.35,
                  pan: float | None = None) -> bool:
        if (not self.enabled or not self.available or self._ping_channel is None
                or not self.local_effects):
            return False
        try:
            if self._ping_channel.get_busy():
                return False
            volume = np.clip(float(volume), 0.0, self.SOURCE_LIMITS["ping"])
            sound = self._sound(
                lambda: active_sonar_ping(frequency_hz, self.sample_rate,
                                          volume),
                ("ping", round(frequency_hz), round(float(volume), 2)), pan)
            if sound is None:
                return False
            self._ping_channel.play(sound)
        except pygame.error:
            self._latch_device_error()
            return False
        except (TypeError, ValueError, OverflowError):
            return False
        return True

    def play_echo(self, pulse: str, level: float, frequency_hz: float = 900.0,
                  volume: float = 0.35, pan: float | None = None) -> bool:
        """Play one returned echo on the ping bus; a busy bus queues it once.

        ``level`` (0..1) is quantized so repeated echoes reuse cached sounds.
        """
        if (not self.enabled or not self.available or self._ping_channel is None
                or not self.local_effects):
            return False
        try:
            level = round(float(np.clip(level, 0.0, 1.0)) * 10) / 10
            volume = float(np.clip(volume, 0.0, self.SOURCE_LIMITS["ping"]))
            sound = self._sound(
                lambda: sonar_echo(frequency_hz, pulse, level, self.sample_rate,
                                   volume),
                ("ping", "echo", str(pulse), level, round(frequency_hz),
                 round(volume, 2)), pan)
            if sound is None:
                return False
            if not self._ping_channel.get_busy():
                self._ping_channel.play(sound)
            elif self._ping_channel.get_queue() is None:
                self._ping_channel.queue(sound)
            else:
                return False
        except pygame.error:
            self._latch_device_error()
            return False
        except (TypeError, ValueError, OverflowError):
            return False
        return True

    def play_effect(self, kind: str, pan: float | None = None) -> bool:
        """Play one bounded local combat/handling effect on the alert bus,
        placed left or right by ``pan`` (see ``synthesis.bearing_pan``)."""
        atmosphere = kind in ("general_alarm", "hull_slam")
        if kind not in {"torpedo_launch", "missile_launch", "gunfire",
                        "explosion", "water_entry"} and not atmosphere:
            return False
        if (not self.enabled or not self.available or self._alert_channel is None
                or not self.local_effects):
            return False
        try:
            if (self._alert_channel.get_busy()
                    and self._alert_channel.get_queue() is not None):
                self.alert_dropped_events += 1
                return False
            synthesize = atmosphere_effect if atmosphere else combat_effect
            sound = self._sound(
                lambda: synthesize(kind, self.sample_rate, self.SOURCE_LIMITS["alert"]),
                ("alert", "effect", kind, self.sample_rate), pan)
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

    BOAT_CUES = frozenset({"hull_creak", "hull_crack", "detonation_near",
                           "detonation_far", "ping_heard", "alarm_bell",
                           "fans_down", "fans_up"})

    def play_boat_cue(self, kind: str, pan: float | None = None) -> bool:
        """One atmosphere cue inside the crewed boat (the uConsole as the boat;
        ``local_effects`` is off there, so this is the boat's only effect)."""
        if kind not in self.BOAT_CUES:
            return False
        if not self.enabled or not self.available or self._alert_channel is None:
            return False
        try:
            if (self._alert_channel.get_busy()
                    and self._alert_channel.get_queue() is not None):
                self.alert_dropped_events += 1
                return False
            sound = self._sound(
                lambda: (atmosphere_effect if kind in ("alarm_bell", "fans_down", "fans_up")
                         else boat_effect)(kind, self.sample_rate, self.SOURCE_LIMITS["alert"]),
                ("alert", "boat", kind, self.sample_rate), pan)
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
        if (not self.enabled or not self.available or self._alert_channel is None
                or not self.local_effects):
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
        Buffered local listening retains at most SONAR_BUFFER_MAX_S of sounds.
        The mixer still holds only its current and next sound.
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
                    out_rate = self._elastic_output_rate()
                else:
                    if self._sonar_channel.get_queue() is not None:
                        self.sonar_dropped_blocks += 1
                        return False
                    out_rate = self.sample_rate
            source_rate = int(sample_rate)
            if self._sonar_rate != source_rate or self.sonar_stale:
                input_start = output_start = 0
                previous = None
            else:
                input_start = self._sonar_input_count
                output_start = self._sonar_output_count
                previous = self._sonar_previous
                if self._sonar_out_rate != out_rate:
                    # Rebase the exact counters onto the new output rate: the
                    # next output instant moves by less than one output sample.
                    offset = output_start * source_rate - input_start * self._sonar_out_rate
                    input_start = 0
                    output_start = -((-offset * out_rate)
                                     // (self._sonar_out_rate * source_rate))
            # Ceil chooses exactly the output instants before the input end;
            # unlike round, it never needs a second prior sample at a join.
            # An elastic out_rate above the mixer rate yields more samples per
            # input block, i.e. slightly slower playback, and vice versa.
            output_end = ((input_start + samples.size) * out_rate
                          + source_rate - 1) // source_rate
            count = output_end - output_start
            if count < 2:
                return False
            positions = (np.arange(output_start, output_end, dtype=np.float64)
                         * source_rate / out_rate - input_start - 1)
            values = np.concatenate(([0.0 if previous is None else previous], samples))
            signal = np.interp(positions, np.arange(-1, samples.size), values)
            # Headphone volume precedes the soft limiter so turning it down
            # also reduces limiter compression, not only final loudness.
            signal *= np.clip(volume, 0.0, 1.0)
            with self._sonar_lock:
                tail = self._sonar_tail_value if buffered else None
            if previous is None and tail is None:
                fade_count = min(count, max(2, round(self.sample_rate * 0.005)))
                signal[:fade_count] *= np.linspace(0.0, 1.0, fade_count)
            if self.channels == 2 and bearing_deg is not None:
                signal = stereo_bearing(signal, bearing_deg, listener_bearing_deg)
            if previous is None and tail is not None:
                # A retune or lost block continues the queued stream: join
                # the new beam to its last sample instead of dipping to zero.
                if np.shape(tail) == signal.shape[1:]:
                    fade_count = min(count, max(2, round(self.sample_rate * .01)))
                    weight = np.linspace(0.0, 1.0, fade_count)
                    if signal.ndim == 2:
                        weight = weight[:, None]
                    signal[:fade_count] = (tail * (1 - weight)
                                           + signal[:fade_count] * weight)
                else:
                    fade_count = min(count, max(2, round(self.sample_rate * 0.005)))
                    weight = np.linspace(0.0, 1.0, fade_count)
                    signal[:fade_count] *= (weight[:, None] if signal.ndim == 2
                                            else weight)
            sound = self._make_sound(signal, "sonar")
            if buffered:
                with self._sonar_lock:
                    self._sonar_buffered = True
                    self._sonar_buffer.append((sound, count / self.sample_rate,
                                               signal.copy()))
                    self._sonar_tail_value = np.array(signal[-1], copy=True)
                    self._sonar_buffer_duration += count / self.sample_rate
                    if (self._sonar_worker is not None
                            and not self._sonar_worker.is_alive()):
                        # A dead worker never feeds the mixer again: the
                        # buffer fills and the sonar stays silent for good.
                        self._sonar_worker = None
                        self.sonar_worker_restarts += 1
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
            self._sonar_out_rate = out_rate
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

    def _elastic_output_rate(self) -> int:
        """Resampling output rate that steers the queue towards its target.

        Called under the sonar lock for each buffered block. Before the
        startup cushion exists, and after any reset, the rate is exact.
        A queue below target plays slightly slower (more output samples per
        block), above target slightly faster, by at most SONAR_RATE_MAX.
        """
        if not self._sonar_primed or self._sonar_refilling:
            self._sonar_level_ema = None
            self.sonar_rate_adjust = 0.0
            return self.sample_rate
        level = self._sonar_buffer_duration
        if self._sonar_level_ema is None:
            self._sonar_level_ema = level
        else:
            self._sonar_level_ema += self.SONAR_LEVEL_SMOOTHING * (
                level - self._sonar_level_ema)
        error = self._sonar_level_ema - self.SONAR_TARGET_S
        adjust = float(np.clip(-self.SONAR_RATE_GAIN * error,
                               -self.SONAR_RATE_MAX, self.SONAR_RATE_MAX))
        # Quantized and slew-limited to one step per block, so the tiny pitch
        # correction never wobbles audibly.
        adjust = round(adjust / self.SONAR_RATE_STEP) * self.SONAR_RATE_STEP
        adjust = float(np.clip(adjust, self.sonar_rate_adjust - self.SONAR_RATE_STEP,
                               self.sonar_rate_adjust + self.SONAR_RATE_STEP))
        self.sonar_rate_adjust = adjust
        return round(self.sample_rate * (1.0 + adjust))

    def _conceal_signal(self) -> np.ndarray | None:
        """A non-periodic 0.25 s stand-in built from recently played audio.

        Overlap-added grains with random offsets keep level and spectrum of
        the last half second without the looping stutter of a repeated block.
        The power-complementary sine window keeps uncorrelated grains at a
        constant level. The start is joined to the last played sample.
        """
        if not self._sonar_history:
            return None
        source = np.concatenate(tuple(self._sonar_history))
        count = max(2, round(self.sample_rate * .25))
        grain = min(round(self.sample_rate * self.SONAR_CONCEAL_GRAIN_S),
                    source.shape[0])
        if grain < 16:
            return None
        grain -= grain % 2
        hop = grain // 2
        window = np.sin(np.pi * (np.arange(grain) + .5) / grain)
        if source.ndim == 2:
            window = window[:, None]
        output = np.zeros((count + 2 * grain,) + source.shape[1:])
        for start in range(0, count + grain + 1, hop):
            self._sonar_conceal_seed = (self._sonar_conceal_seed * 1664525
                                        + 1013904223) % 2**32
            offset = self._sonar_conceal_seed % (source.shape[0] - grain + 1)
            output[start:start + grain] += source[offset:offset + grain] * window
        signal = output[grain:grain + count]
        self._join_to_last_value(signal)
        return signal

    def _join_to_last_value(self, signal: np.ndarray) -> None:
        """Crossfade the first 10 ms from the last played sample in place."""
        if self._sonar_last_value is None:
            return
        fade = min(len(signal), max(2, round(self.sample_rate * .01)))
        weight = np.linspace(0.0, 1.0, fade)
        if signal.ndim == 2:
            weight = weight[:, None]
        signal[:fade] = (self._sonar_last_value * (1 - weight)
                         + signal[:fade] * weight)

    def _pump_sonar_once(self) -> None:
        with self._sonar_lock:
            if (not self._sonar_buffered or not self.available
                    or pygame.mixer.get_init() is None):
                self._sonar_pump_last_at = None
                return
            try:
                if not self._sonar_primed:
                    if self._sonar_buffer_duration < self.SONAR_BUFFER_S - 1e-6:
                        return
                    self._sonar_primed = True
                    self._sonar_pump_last_at = None
                now = time.monotonic()
                if self._sonar_pump_last_at is not None:
                    gap = now - self._sonar_pump_last_at
                    if gap > self.SONAR_PUMP_LATE_S:
                        self.sonar_pump_late += 1
                    self.sonar_pump_late_max_s = max(self.sonar_pump_late_max_s, gap)
                self._sonar_pump_last_at = now
                if (self._sonar_channel.get_queue() is not None
                        and not self._release_stranded_queue()):
                    return
                self._sonar_stranded_candidate = None
                if (self._sonar_last_fresh_at is not None
                        and not self._sonar_channel.get_busy()):
                    # The mixer ran dry between two iterations: an audible dip
                    # (the next play() fades in) that no other counter sees.
                    self.sonar_channel_idle += 1
                if (self._sonar_refilling and self._sonar_buffer_duration
                        >= self.SONAR_REFILL_S - 1e-6):
                    self._sonar_refilling = False
                if self._sonar_buffer and not self._sonar_refilling:
                    sound, duration, signal = self._sonar_buffer.popleft()
                    self._sonar_buffer_duration = max(0.0, self._sonar_buffer_duration - duration)
                    if self._sonar_concealing or self.sonar_stale:
                        # Resume without a step from the stand-in audio.
                        signal = signal.copy()
                        self._join_to_last_value(signal)
                        sound = self._make_sound(signal, "sonar")
                    self._sonar_concealing = False
                    self._sonar_history.append(signal)
                    self._sonar_last_value = signal[-1].copy()
                    self._sonar_last_fresh_at = time.monotonic()
                    self.sonar_stale = False
                elif self._sonar_last_fresh_at is None:
                    return
                elif (time.monotonic() - self._sonar_last_fresh_at
                        < self.SONAR_STALE_S
                        and (signal := self._conceal_signal()) is not None):
                    if not self._sonar_concealing:
                        self.sonar_local_underruns += 1
                    self._sonar_concealing = True
                    self._sonar_refilling = True
                    self._sonar_last_value = signal[-1].copy()
                    sound = self._make_sound(signal, "sonar")
                    self.sonar_holds += 1
                    self.sonar_concealed_blocks += 1
                else:
                    self.sonar_stale = True
                    self._sonar_concealing = False
                    self._sonar_refilling = True
                    self._sonar_previous = None
                    self._sonar_history.clear()
                    self._sonar_last_value = None
                    self._sonar_tail_value = None
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

    def _release_stranded_queue(self) -> bool:
        """Recover a queued sound that an idle sonar channel will never play.

        pygame's end-of-sound callback looks at the channel's queue before it
        takes the GIL; a queue() landing in that window is stored after the
        callback found nothing queued. The channel then stays idle with a
        sound queued forever, and the pump (which waits for a free queue slot)
        never refills it: the sonar is silent until the engine is rebuilt.
        The same sound must be seen stranded on two iterations in a row, so
        the instant between a sound's end and its queue's promotion is not
        mistaken for it. A stranded sound of the running stream is replayed
        (play() also clears the queue); after a stream reset it is stale and
        the next play() of the new stream discards it. True lets the caller
        refill the channel. Called under the sonar lock.
        """
        queued = self._sonar_channel.get_queue()
        if queued is None or self._sonar_channel.get_busy():
            self._sonar_stranded_candidate = None
            return queued is None
        if self._sonar_last_fresh_at is None:
            self._sonar_stranded_candidate = None
            return True
        if self._sonar_stranded_candidate is not queued:
            self._sonar_stranded_candidate = queued
            return False
        self._sonar_stranded_candidate = None
        self.sonar_queue_stranded += 1
        self.sonar_channel_idle += 1
        self._sonar_channel.play(queued, fade_ms=self.FADE_MS)
        return False

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
            self.sonar_input_gaps += 1
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
        self._sonar_out_rate = None
        self._sonar_history.clear()
        self._sonar_last_value = None
        self._sonar_tail_value = None
        self._sonar_concealing = False
        self._sonar_refilling = False
        self._sonar_level_ema = None
        self.sonar_rate_adjust = 0.0
        self._sonar_last_fresh_at = None
        self.sonar_stale = False
        self._sonar_hold_streak = 0
        self._sonar_pump_last_at = None
        self._sonar_stranded_candidate = None

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
        with self._sonar_lock:
            late_max_ms = self.sonar_pump_late_max_s * 1000.0
            self.sonar_pump_late_max_s = 0.0
        line = ("t={t:.1f} receiver_blocks_per_s={rb} sonar_drops={sd} "
                "sonar_holds={sh} alert_drops={ad} "
                "sonar_underruns={su} sonar_concealed={sc} sonar_neutral={sn} "
                "sonar_stale={ss} buffer_s={bs:.2f} rate_adj={ra:+.4f} "
                "channel_idle={ci} pump_late={pl} pump_late_max_ms={pm:.0f} "
                "queue_stranded={qs} worker_restarts={wr} "
                "input_gaps={ig} evictions={ev} rate={r} ch={c}\n").format(
            qs=self.sonar_queue_stranded, wr=self.sonar_worker_restarts,
            sc=self.sonar_concealed_blocks, ra=self.sonar_rate_adjust,
            t=time.monotonic(), sd=self.sonar_dropped_blocks,
            sh=self.sonar_holds, ad=self.alert_dropped_events, ev=evictions,
            rb=produced,
            su=self.sonar_local_underruns, sn=self.sonar_neutral_blocks,
            ss=int(self.sonar_stale), bs=self._sonar_buffer_duration,
            ci=self.sonar_channel_idle, pl=self.sonar_pump_late, pm=late_max_ms,
            ig=self.sonar_input_gaps,
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
