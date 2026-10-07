"""Asking the executive officer by voice: the talk key at every station.

``Shift+Space`` (the same key at every station of both sides, and in the
browser) opens the uConsole's microphone and keeps what is said while the
key is held; letting go sends it to the speech input
(``src/llm/stt.py``), and the recognised text goes to the executive officer
as an ordinary question (``src/llm/advisor.py``).  A short tap starts the
recording and a second press sends it, so the key need not be held.  The
answer shows in a small bubble over the station (``src/ui/talk_view.py``)
and in the ``F7`` log, and the officer's voice says it when that is on.

The talk key only asks: nothing here gives an order or touches the
simulation.  Everything is wall-time UI state of this launch (never saved,
never read by the simulation); the recording lives in memory only until it
was sent.  A browser station sends its own recording through Remote Crew
(``src/commander/advisor_web.py``) and is answered the same way.
"""

from __future__ import annotations

import time

import pygame

from src.audio.microphone import Microphone
from src.core.i18n import message
from src.llm import advisor as advisor_model, keystore, stt as stt_model
from src.llm.stt import SttConfig, SttService

TALK_KEY = pygame.K_SPACE
TALK_MOD = pygame.KMOD_SHIFT
TALK_LABEL = "Shift+Space"
# A press shorter than this is a tap: the recording goes on until the next
# press (no need to hold the key while speaking).
TAP_S = 0.35
# How long the answer stays in the bubble over the station (wall seconds);
# a problem shows shorter.
BUBBLE_S = 30.0
ERROR_S = 6.0
WEB_MAX = 8
STATES = ("idle", "recording", "transcribing", "asking")


def _host(url: str) -> str:
    from src.core.game_voice import _host as host
    return host(url)


class TalkMixin:
    def _init_talk(self) -> None:
        self.stt = SttService(self._stt_config())
        self.stt_test = None
        self.talk_state = "idle"
        self.talk_bubble = None
        self._talk_pressed_at = None    # wall time the key went down (held)
        self._talk_started_at = 0.0
        self._talk_request = None
        self._talk_entry = None
        self._talk_eat_space = False
        # Browser stations' recordings being transcribed, by asker, and the
        # reasons to publish to them (src/commander/advisor_web.py).
        self._talk_web: dict = {}
        self._talk_web_updates: list = []
        # Spoken orders waiting for the model: seq -> (side, role, any station).
        self._talk_orders: dict = {}

    # -- configuration -------------------------------------------------------------

    def stt_key_source(self) -> str:
        """"env", "own", "shared" (the voice's or the model's key, same
        server) or "none"; read when it was configured, never per frame."""
        return getattr(self, "_stt_key_source", "none")

    def _stt_config(self) -> SttConfig:
        prefs = self.preferences
        key = keystore.load_key(keystore.STT_ENV_NAME, keystore.STT_FILE_NAME)
        source = ("env" if keystore.key_from_env(keystore.STT_ENV_NAME)
                  else "own" if key else "none")
        if not key:
            host = _host(prefs.stt_url)
            if host and host == _host(prefs.tts_url):
                key = keystore.load_key(keystore.VOICE_ENV_NAME, keystore.VOICE_FILE_NAME)
            if not key and host and host == _host(prefs.llm_url):
                key = keystore.load_key()
            source = "shared" if key else "none"
        self._stt_key_source = source
        return SttConfig(enabled=bool(prefs.stt_enabled), base_url=prefs.stt_url,
                         model=prefs.stt_model, api_key=key)

    def configure_stt(self) -> None:
        if hasattr(self, "stt"):
            self.stt.configure(self._stt_config())

    def set_stt_preference(self, name: str, value) -> None:
        self._set_preference(name, value)
        self.configure_stt()
        if name == "stt_enabled" and not value:
            self.talk_cancel()

    def save_stt_key(self, value: str) -> bool:
        ok = keystore.save_key(value, keystore.STT_FILE_NAME)
        self.configure_stt()
        return ok

    # -- availability --------------------------------------------------------------

    def talk_reason(self):
        """Why the talk key cannot ask now (a ``talk.reason.*`` key), or None."""
        if not self.stt.active:
            return "stt_off"
        if not self.llm_active():
            return "llm_off"
        if not self._advisor_mission_running():
            return "not_ready"
        return None

    def _talk_key_context(self) -> bool:
        """The talk key belongs to a running mission at a station (or the
        executive officer's page), never to a menu or another overlay."""
        if (getattr(self, "web_mode", False) or self.splash_active or self.in_menu
                or self.editor is not None or self.simlog_view_open or self.game_over):
            return False
        return not self.administration_open or self.advisor_open

    def talk_shown(self) -> bool:
        """The talk button in the top bar: the model is on."""
        return self.llm_active()

    # -- keys ----------------------------------------------------------------------

    def talk_key_event(self, e) -> bool:
        """``Shift+Space`` down, its release and the space it would type;
        True when the event was the talk key's."""
        if e.type == pygame.TEXTINPUT:
            if self._talk_eat_space and getattr(e, "text", "") == " ":
                self._talk_eat_space = False
                return True
            return False
        if e.type == pygame.KEYDOWN:
            self._talk_eat_space = False
            if e.key != TALK_KEY or not getattr(e, "mod", 0) & TALK_MOD:
                return False
            if not self._talk_key_context():
                return False
            self._talk_eat_space = True
            self.talk_press()
            return True
        if e.type == pygame.KEYUP and self._talk_pressed_at is not None:
            if e.key in (TALK_KEY, pygame.K_LSHIFT, pygame.K_RSHIFT):
                self.talk_release()
                return e.key == TALK_KEY
        return False

    def talk_press(self) -> None:
        """The key (or the talk button) went down: start, or send a tapped
        recording."""
        if self.talk_state == "recording":
            if self._talk_pressed_at is None:
                self._talk_send()
            return
        reason = self.talk_reason()
        if reason is not None:
            self.flash(message("talk.reason." + reason), 3.0)
            return
        if self.talk_state != "idle":
            self.flash(message("talk.reason.busy"), 2.0)
            return
        mic = self.__dict__.get("microphone")
        if mic is None:
            mic = self.__dict__["microphone"] = Microphone()
        if mic.device is None:
            mic.start()
        if not mic.begin_recording():
            self.flash(message("talk.reason.no_mic", state=message(
                "option.microphone.failure." + (mic.failure or "no_device"))), 4.0)
            return
        now = time.monotonic()
        self.talk_state = "recording"
        self._talk_pressed_at = self._talk_started_at = now
        self.talk_bubble = dict(question="", entry=None, error=None, until=None)

    def talk_release(self) -> None:
        pressed, self._talk_pressed_at = self._talk_pressed_at, None
        if self.talk_state != "recording" or pressed is None:
            return
        if time.monotonic() - pressed < TAP_S:
            return          # a tap: keeps recording until the next press
        self._talk_send()

    def talk_toggle(self) -> None:
        """A click on the bubble's talk key: start, or send."""
        if self.talk_state == "recording":
            self._talk_pressed_at = None
            self._talk_send()
        else:
            self.talk_press()
            self._talk_pressed_at = None

    def talk_cancel(self) -> None:
        """Drop the recording (focus lost, the speech input switched off, a
        new world); an answer already asked for still arrives in F7."""
        self._talk_pressed_at = None
        if getattr(self, "talk_state", "idle") == "recording":
            mic = self.__dict__.get("microphone")
            if mic is not None:
                mic.end_recording()
            self.talk_bubble = None
        if getattr(self, "talk_state", "idle") != "asking":
            self._talk_request = None
            self.talk_state = "idle"

    def talk_recorded_s(self) -> float:
        if self.talk_state != "recording":
            return 0.0
        return max(0.0, time.monotonic() - self._talk_started_at)

    def talk_level(self) -> int:
        mic = self.__dict__.get("microphone")
        return mic.level() if mic is not None and self.talk_state == "recording" else 0

    def _talk_send(self) -> None:
        mic = self.__dict__.get("microphone")
        samples = mic.end_recording() if mic is not None else None
        request = (self.stt.transcribe(samples, self.llm_language())
                   if samples is not None else None)
        if request is None:
            self._talk_fail("busy")
            return
        self._talk_request = request
        self.talk_state = "transcribing"

    def _talk_fail(self, error: str) -> None:
        self.talk_state = "idle"
        self._talk_request = None
        self._talk_entry = None
        self.talk_bubble = dict(question="", entry=None, error=error,
                                until=time.monotonic() + ERROR_S)

    def close_talk_bubble(self) -> None:
        self.talk_bubble = None

    def open_talk_chat(self) -> None:
        """The talk button: the executive officer's page, ready for a typed
        question."""
        from src.core.game_advisor import ADVISOR_MODES
        self.advisor_mode = ADVISOR_MODES.index("question")
        self.talk_bubble = None
        self._open_administration("advisor")

    def talk_bubble_shown(self) -> bool:
        bubble = self.talk_bubble
        if bubble is None or self.administration_open:
            return False
        return bubble["until"] is None or time.monotonic() < bubble["until"]

    # -- the per-frame pump (wall time) ---------------------------------------------

    def talk_tick(self) -> None:
        if not hasattr(self, "stt"):
            return
        now = time.monotonic()
        if self.talk_state == "recording":
            if self.talk_reason() is not None:
                self.talk_cancel()
            elif now - self._talk_started_at >= stt_model.MAX_AUDIO_S:
                self._talk_pressed_at = None
                self._talk_send()
        request = self._talk_request
        if self.talk_state == "transcribing" and request is not None and request.finished:
            self._talk_request = None
            if not request.ok:
                self._talk_fail(request.error or "network")
            elif not request.text:
                self._talk_fail("no_speech")
            else:
                result = self._talk_ask(request.text, side=self.advisor_side(), role=None,
                                        anywhere=True)
                if isinstance(result, dict):
                    self._talk_entry = result
                    self.talk_state = "asking"
                    self.talk_bubble = dict(question=request.text, entry=result,
                                            error=None, until=None)
                else:
                    self._talk_fail(result)
        entry = self._talk_entry
        if self.talk_state == "asking" and entry is not None and entry["status"] != "pending":
            self.talk_state = "idle"
            self._talk_entry = None
            if self.talk_bubble is not None and self.talk_bubble["entry"] is entry:
                self.talk_bubble["until"] = now + BUBBLE_S
        self._talk_web_tick()

    # -- browser stations (Remote Crew) ---------------------------------------------

    def talk_submit_web(self, asker: str, samples, side: str, role: str,
                        anywhere: bool = False) -> str:
        """A browser station's recording: "transcribing", or why not.
        ``anywhere``: the session holds every station (solo mode), so a
        spoken order is not limited to ``role``'s own commands."""
        if not self.stt.active:
            return "stt_off"
        if not self.llm_active():
            return "llm_off"
        if not self._advisor_mission_running():
            return "not_ready"
        if asker in self._talk_web or len(self._talk_web) >= WEB_MAX:
            return "llm_busy"
        request = self.stt.transcribe(samples, self.llm_language(), tag=asker)
        if request is None:
            return "llm_busy"
        self._talk_web[asker] = (request, side, role, anywhere)
        return "transcribing"

    def _talk_web_tick(self) -> None:
        for asker, (request, side, role, anywhere) in list(self._talk_web.items()):
            if not request.finished:
                continue
            del self._talk_web[asker]
            if not request.ok:
                reason = "stt_" + str(request.error or "network")
            elif not request.text:
                reason = "stt_no_speech"
            else:
                result = self._talk_ask(request.text, asker=asker, side=side, role=role,
                                        anywhere=anywhere)
                reason = result if isinstance(result, str) else None
            self._talk_web_updates.append((asker, reason))
        del self._talk_web_updates[:-WEB_MAX]

    # -- spoken orders -----------------------------------------------------------------

    def _talk_ask(self, text: str, *, side: str, role, anywhere: bool, asker: str = "local"):
        """Hand what was said to the officer: the model turns an order into
        the fixed order set, carried out once it is back
        (``talk_order_finished``), and answers anything else as a question.
        A plain question skips that step; in multiplayer (other people
        crew the stations) everything is a question and no order is taken."""
        if self.advisor_orders_locked() or advisor_model.looks_like_question(text):
            return self.advisor_ask("question", text, asker=asker, side=side,
                                    station=role)
        result = self.advisor_ask("order", text, asker=asker, side=side, station=role,
                                  spoken=True)
        if isinstance(result, dict):
            self._talk_orders[result["seq"]] = (side, role, anywhere)
            del_old = len(self._talk_orders) - 2 * WEB_MAX
            for seq in list(self._talk_orders)[:max(0, del_old)]:
                del self._talk_orders[seq]
        return result

    def talk_order_finished(self, entry: dict) -> None:
        """A spoken order is back from the model: carry it out at once and
        let the officer report only what was really done (never weapons;
        a browser station gives only its own station's commands).  What
        turned out to be a question keeps the officer's answer."""
        info = getattr(self, "_talk_orders", {}).pop(entry["seq"], None)
        if info is None or entry["kind"] == "question":
            return
        side, role, anywhere = info
        proposal = entry["proposal"] if entry["status"] == "done" else None
        if not proposal:
            key = ("advisor.spoken.not_possible" if entry["error"] == "not_possible"
                   else "advisor.spoken.not_understood")
            entry.update(status="done", error=None, proposal=None, answer=self.tr(key))
            return
        from src.commander.v2.commands import V2_ACTION_REGISTRY

        done, refused = [], []
        for command in proposal:
            allowed = anywhere or role in V2_ACTION_REGISTRY[command["action"]].stations
            ok = (allowed and self._advisor_mission_running()
                  and not self.advisor_orders_locked()
                  and advisor_model.apply_proposal(self, side, [command])[0])
            (done if ok else refused).append(self._talk_command_text(command))
        if done and refused:
            answer = self.tr("advisor.spoken.partial", done=", ".join(done),
                             refused=", ".join(refused))
        elif done:
            answer = self.tr("advisor.spoken.done", orders=", ".join(done))
        else:
            answer = self.tr("advisor.spoken.refused", orders=", ".join(refused))
        entry.update(proposal=None, applied=True, answer=answer)

    def _talk_command_text(self, command: dict) -> str:
        value = command["value"]
        if command["params"] == {}:
            return self.tr("advisor.command." + command["type"])
        if value is True or value is False:
            value = self.tr("common.on" if value else "common.off")
        else:
            value = f"{value:g}"
        return self.tr("advisor.command." + command["type"], value=value)

    def talk_web_updates(self) -> list:
        """Finished browser recordings since the last call: (asker, reason)."""
        updates, self._talk_web_updates = self._talk_web_updates, []
        return updates

    def _reset_talk(self) -> None:
        """A new or loaded world: no recording, bubble or browser request."""
        if not hasattr(self, "stt"):
            return
        self.talk_cancel()
        self.talk_state = "idle"
        self._talk_request = None
        self._talk_entry = None
        self.talk_bubble = None
        self._talk_web = {}
        self._talk_web_updates = []
        self._talk_orders = {}

    # -- settings test ---------------------------------------------------------------

    def start_stt_test(self) -> bool:
        """Send a second of quiet tone: shows that the service answers and
        how long it took."""
        if not self.stt.active:
            self.stt_test = dict(status="failed", error="disabled")
            return False
        import numpy as np
        rate = stt_model.SAMPLE_RATE
        tone = (0.05 * np.sin(2 * np.pi * 440.0 * np.arange(rate) / rate)).astype(np.float32)
        request = self.stt.transcribe(tone, self.llm_language(), tag="test", check=False)
        if request is None:
            self.stt_test = dict(status="failed", error="busy")
            return False
        self.stt_test = dict(status="pending", request=request)
        return True

    def stt_test_state(self) -> dict | None:
        test = self.stt_test
        if test is None or test["status"] != "pending":
            return test
        request = test["request"]
        if not request.finished:
            return test
        self.stt_test = (dict(status="done", latency_s=request.latency_s or 0.0)
                         if request.ok else dict(status="failed", error=request.error))
        return self.stt_test
