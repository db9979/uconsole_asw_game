"""Noise discipline of ``Game``: crew mishaps and the players' voices.

The model is ``src/core/noise_discipline.py``.  At the start of every substep
each platform's ``crew_noise`` is set from stateless draws, the crews' saved
fatigue, morale and silent running, and the held microphone levels (inputs
like held keys, never saved).  An enemy crew within earshot hears it as a
transient on its measured bearing; the own crew is told when it fumbled or
talks too loud.  Reports remember only what they already said.
"""

from __future__ import annotations

import math
import sys

from src.audio.microphone import Microphone
from src.audio.synthesis import bearing_pan
from src.core import config, noise_discipline as nd, opfor
from src.core.i18n import message
from src.sensors import threat_cue

SIDES = ("frigate", "uboot")
VOICE_SOURCES = ("local", "remote")
FRIGATE_KEY = 0


def microphone_state_key(failure: str) -> str:
    """Catalog key of the short state a failed microphone shows in its row."""
    return f"option.microphone.state.{failure}"


def microphone_failure_key(failure: str, platform: str | None = None) -> str:
    """Catalog key of the cause and remedy (Options page 2); a silent device
    names the privacy setting of the player's own system."""
    platform = sys.platform if platform is None else platform
    if failure == "silent":
        if platform.startswith("win"):
            return "option.microphone.failure.silent_windows"
        if platform == "darwin":
            return "option.microphone.failure.silent_macos"
    return f"option.microphone.failure.{failure}"


def platform_key(sub) -> int:
    """Stable per-boat key (entity ids are process-global, the sensor seed is not)."""
    return 1 + int(sub.sensor_seed) % 1_000_000


class NoiseMixin:
    """Crew noise: mishaps under the routine, voices from the microphones."""

    # --- microphone input --------------------------------------------------

    def set_crew_voice(self, side: str, level: int, source: str = "remote") -> bool:
        """The loudest voice level a side's crew reports now (0..VOICE_LEVEL_MAX)."""
        if side not in SIDES or source not in VOICE_SOURCES or type(level) is not int:
            return False
        if not 0 <= level <= nd.VOICE_LEVEL_MAX:
            return False
        voices = self.__dict__.setdefault("_crew_voices", {})
        voices[(side, source)] = (level, self.sim_t)
        return True

    def crew_voice_level(self, side: str) -> int:
        """The side's voice level now: the loudest source still held."""
        voices = self.__dict__.get("_crew_voices") or {}
        level = 0
        for source in VOICE_SOURCES:
            held = voices.get((side, source))
            if held is not None and 0.0 <= self.sim_t - held[1] <= nd.VOICE_HOLD_S:
                level = max(level, held[0])
        return level

    def clear_crew_voices(self) -> None:
        self.__dict__["_crew_voices"] = {}

    def _pump_microphone(self, wall_dt: float) -> None:
        """The uConsole's own microphone (opt-in): its level is held input of
        the local side while a mission runs, like a held key; the meter
        falls back by one step per tenth of a second."""
        mic = self.__dict__.get("microphone")
        running = not (self.web_mode or self.in_menu or self.main_menu
                       or self.game_over or getattr(self, "splash_active", False))
        wanted = bool(getattr(self.preferences, "microphone", False)) and running
        if not wanted:
            if mic is not None and mic.device is not None:
                mic.stop()
            if mic is not None:
                # The next mission opens the device afresh (one try each).
                mic.tried = False
            self.__dict__["mic_level"] = 0
            return
        if mic is None:
            mic = self.__dict__["microphone"] = Microphone()
        if mic.device is None and not mic.tried:
            mic.start()
        self._report_microphone(mic.check())
        fall = self.__dict__.get("mic_fall", 0.0) + max(0.0, wall_dt)
        held = self.__dict__.get("mic_level", 0)
        steps = int(fall / 0.1)
        self.__dict__["mic_fall"] = fall - steps * 0.1
        level = max(mic.level(), held - steps)
        self.__dict__["mic_level"] = level
        side = "uboot" if getattr(self, "local_side", "frigate") == "uboot" else "frigate"
        if level > nd.VOICE_SAFE:
            self.set_crew_voice(side, level, "local")

    def _report_microphone(self, failure: str) -> None:
        """Say once per cause that the switched-on microphone does not work;
        Options page 2 keeps the reason and the remedy on screen."""
        if failure == self.__dict__.get("mic_reported", ""):
            return
        self.__dict__["mic_reported"] = failure
        if failure:
            self.flash(message("status.microphone_failed",
                               state=message(microphone_state_key(failure))), 6.0)

    def close_microphone(self) -> None:
        self.__dict__["mic_reported"] = ""
        mic = self.__dict__.pop("microphone", None)
        if mic is not None:
            mic.stop()

    # --- each substep ------------------------------------------------------

    def _update_crew_noise(self) -> None:
        window = nd.tick(self.sim_t)
        heard = []
        ship = self.ship
        if self.damage.ship_sunk:
            ship.crew_noise = 0.0
        else:
            quiet = bool(ship.quiet_mode)
            kind = nd.mishap(self.seed, FRIGATE_KEY, window,
                             nd.risk_per_h(self.crew_effect(), quiet))
            voice = self.crew_voice_level("frigate")
            base = ship.machinery_noise_level()
            ship.crew_noise = nd.crew_noise(base, kind is not None, voice)
            reach = nd.hear_nm(kind is not None, voice, base)
            self._own_crew_noise("frigate", None, FRIGATE_KEY, window, kind, quiet, voice)
            if reach > 0.0:
                heard.append((FRIGATE_KEY, ship, reach, kind, voice))
        boat = self._opfor
        for sub in self.subs:
            if sub.sunk:
                sub.crew_noise = 0.0
                continue
            crewed = boat is not None and boat.sub is sub
            quiet = nd.sub_quiet(sub)
            effect = boat.watch.effectiveness(self.sim_t) if crewed else 1.0
            key = platform_key(sub)
            kind = nd.mishap(self.seed, key, window, nd.risk_per_h(effect, quiet))
            voice = self.crew_voice_level("uboot") if crewed else 0
            base = 1.0 - sub.machinery_quiet_factor()
            sub.crew_noise = nd.crew_noise(base, kind is not None, voice)
            if crewed:
                self._own_crew_noise("uboot", boat, key, window, kind, quiet, voice)
            reach = nd.hear_nm(kind is not None, voice, base)
            if reach > 0.0:
                heard.append((key, sub, reach, kind, voice))
        for key, source, reach, kind, voice in heard:
            self._hear_crew_noise(key, source, reach, kind, voice, window)

    # --- reports -----------------------------------------------------------

    def _noise_once(self, entry) -> bool:
        said = self.__dict__.setdefault("_noise_said", {})
        if any(at > self.sim_t for at in said.values()):
            said.clear()                    # a new or loaded mission
        if entry in said:
            return False
        said[entry] = self.sim_t
        if len(said) > 64:
            horizon = self.sim_t - 2.0 * nd.VOICE_WARN_S
            for old in [item for item, at in said.items() if at < horizon]:
                del said[old]
        return True

    def _own_crew_noise(self, side, boat, key, window, kind, quiet, voice) -> None:
        """The own crew hears its fumble (only under silent running, when it
        matters) and is told off when it talks far too loud."""
        if kind is not None and quiet and self._noise_once(("own", key, window)):
            if boat is None:
                self._crew_notice("noise.mishap." + kind)
            else:
                boat.orders.event("crew_mishap_" + kind)
                opfor.boat_sound(self, boat, "crew_clank")
        if nd.band(voice) == "far" and self._noise_once(
                ("voice", key, math.floor(self.sim_t / nd.VOICE_WARN_S))):
            if boat is None:
                self._crew_notice("noise.voice_far")
            else:
                boat.orders.event("voice_far")

    def _hear_crew_noise(self, key, source, reach, kind, voice, window) -> None:
        """An enemy crew within earshot hears the transient on its bearing."""
        report = ("mishap", window) if kind is not None else (
            "voice", math.floor(self.sim_t / nd.VOICE_REPORT_S))
        if key == FRIGATE_KEY:
            boat = self._opfor
            if boat is None or boat.sonar_down():
                return
            sub = boat.sub
            ears = 1.0 - 0.8 * sub.noise_level()
            if (math.hypot(source.x - sub.x, source.y - sub.y) > reach * ears
                    or self.world.sonar_path_blocked(source.x, source.y, 5.0,
                                                     sub.x, sub.y, sub.depth)
                    or not self._noise_once(("heard", key) + report)):
                return
            true_bearing = math.degrees(math.atan2(source.x - sub.x, -(source.y - sub.y)))
            bearing = threat_cue.measured_cue_bearing(true_bearing % 360.0, sub.sensor_seed,
                                                      key * 1000 + 777, self.sim_t)
            boat.orders.event("transient_heard" if kind is not None else "voices_heard",
                              bearing=f"{round(bearing) % 360:03d}")
            opfor.boat_sound(self, boat, "crew_transient", bearing)
            return
        if self.damage.ship_sunk or self.damage.station_down("sonar"):
            return
        ship = self.ship
        ears = (ship.passive_sonar_range_nm(
            1.0, int(getattr(self.world, "effective_sea_state", self.world.sea_state)))
            / config.SONAR_PASSIVE_BASE_NM) * self._sonar_range_factor()
        if (math.hypot(source.x - ship.x, source.y - ship.y) > reach * ears
                or self.world.sonar_path_blocked(source.x, source.y, source.depth,
                                                 ship.x, ship.y, 5.0)
                or not self._noise_once(("heard", key) + report)):
            return
        true_bearing = math.degrees(math.atan2(source.x - ship.x, -(source.y - ship.y)))
        bearing = threat_cue.measured_cue_bearing(true_bearing % 360.0, self.seed,
                                                  key * 1000 + 777, self.sim_t)
        notice = message("runtime.noise." + ("transient" if kind is not None else "voices"),
                         bearing=f"{bearing:05.1f}")
        self.flash(notice, 4.0)
        self.feed.add(self.world.format_time(), "sonar", notice)
        self._emit_sound("crew_transient", pan=bearing_pan(bearing, ship.course))
