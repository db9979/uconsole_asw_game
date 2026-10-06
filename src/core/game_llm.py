"""The optional language-model link inside the game (``src/llm``).

One ``LlmService`` per game; every job (radio wording, after-action report,
executive officer, coach, service-record review, mission generator,
experimental opponent advisor) submits through it and is collected by
``llm_tick`` once per main-loop frame, on wall time, outside the
simulation.  With the link off or unreachable every job simply does not
run and the game shows its own texts: the offline game is unchanged.
"""

from __future__ import annotations

import datetime

from src.core import logbook as logbook_model
from src.core.i18n import localize, message, raw_text, translation_scope
from src.llm import advisor as advisor_model, facts, keystore, opponent, prompts
from src.llm.client import LlmConfig, LlmService, clean_text
from src.llm.mission_gen import MissionGenerator
from src.llm.radio import RadioVoice, message_key

LOCAL = "local"
SIDES = ("frigate", "uboot")


def valid_llm_state(value) -> bool:
    """The save's ``llm`` block (v49)."""
    from src.core.save_schema import LLM_FIELDS

    return (isinstance(value, dict) and set(value) == LLM_FIELDS
            and isinstance(value["advisor_sides"], list)
            and len(value["advisor_sides"]) == len(set(value["advisor_sides"]))
            and all(side in SIDES for side in value["advisor_sides"])
            and type(value["experimental"]) is bool
            and opponent.valid_state(value["opfor"]))
REPORT_MAX = 2_000
REVIEW_ENTRIES = 30


class LlmMixin:
    """State and wiring of the optional model link."""

    def _init_llm(self) -> None:
        self.llm = LlmService(self._llm_config())
        self.llm_radio = RadioVoice()
        self.advisor = advisor_model.Advisor()
        self.llm_reports: dict = {}
        self.llm_review = None
        self.llm_test = None
        self.mission_gen = MissionGenerator()
        self._llm_report_requests: dict = {}
        self._llm_review_request = None
        self._reset_llm_mission()

    def _llm_config(self) -> LlmConfig:
        prefs = self.preferences
        return LlmConfig(enabled=bool(prefs.llm_enabled), base_url=prefs.llm_url,
                         model=prefs.llm_model, api_key=keystore.load_key())

    def configure_llm(self) -> None:
        self.llm.configure(self._llm_config())

    def llm_active(self) -> bool:
        return self.llm.active

    def llm_language(self) -> str:
        language = getattr(self.preferences, "language", "en")
        return language if language in prompts.LANGUAGE else "en"

    def _reset_llm_mission(self) -> None:
        """A new mission: no styled radio, report, advice or advisor mark."""
        self._reset_llm_transient()
        # Sides ("frigate", "uboot") whose crew used the advisor's help in
        # this mission (saved): their logbook entry is marked.
        self.llm_advisor_sides = set()
        self.llm_experimental = False
        # The experimental opponent's plan in force (saved), or None.
        self.llm_opfor = None

    def _reset_llm_transient(self) -> None:
        """Loaded or new world: drop what belongs to the old picture (the
        saved marks stay)."""
        self.llm_radio.reset()
        self._llm_boat_offered = set()
        self.advisor.reset()
        self.llm_reports = {}
        self._llm_report_requests = {}
        self._llm_opfor_request = None
        self._llm_opfor_next = None
        self._llm_opfor_side = None
        self._reset_talk()

    # -- the per-frame pump (wall time, outside the simulation) ----------------

    def llm_tick(self) -> None:
        if not hasattr(self, "llm"):
            return
        self._llm_boat_orders()
        self.llm_radio.poll()
        for entry in self.advisor.poll():
            if entry["kind"] == "coach" and entry["status"] == "done":
                self._coach_banner(entry["answer"])
            # The executive officer says his answer (game_voice.py).
            self.voice_advisor_entry(entry)
        # Answers spoken for browser stations, kept until fetched.
        self._pump_web_voice()
        self._poll_llm_reports()
        self._poll_llm_review()
        self._poll_mission_generator()
        self._llm_opfor_tick()
        self._coach_tick()
        # The talk key: speech input and its question (game_talk.py).
        self.talk_tick()

    # -- save (v49) ------------------------------------------------------------

    def llm_serialize(self) -> dict:
        return {"advisor_sides": sorted(self.llm_advisor_sides),
                "experimental": bool(self.llm_experimental),
                "opfor": None if self.llm_opfor is None else dict(self.llm_opfor)}

    def llm_restore(self, data: dict) -> None:
        self.llm_advisor_sides = set(data["advisor_sides"])
        self.llm_experimental = bool(data["experimental"])
        self.llm_opfor = None if data["opfor"] is None else dict(data["opfor"])

    # -- 10: experimental opponent (not scored) --------------------------------

    def llm_opfor_side(self):
        """"subs" or "hunter" when the experimental opponent may run, else None."""
        if not (self.preferences.llm_opfor and self.llm.active) or not self._advisor_mission_running():
            return None
        if (getattr(self, "training", None) is not None
                or getattr(self, "campaign_mission", False)
                or self._llm_daily_running() or self.llm_pvp()):
            return None
        if getattr(self, "_opfor", None) is None:
            return "subs"
        from src.core import hunter
        return "hunter" if hunter.active(self) else None

    def _llm_daily_running(self) -> bool:
        """This mission is today's daily mission (scored for everyone alike)."""
        from src.core import daily
        side = "uboot" if getattr(self, "_opfor", None) is not None else "frigate"
        return (self.custom_mission_definition is None
                and self.world_mode == daily.WORLD_MODE
                and daily.match(int(self.seed), self.scenario_key, side) is not None)

    def llm_opfor_plan(self, side: str):
        """The plan the AI side follows (saved, so it holds after a load)."""
        plan = self.llm_opfor
        return plan["plan"] if plan is not None and plan["side"] == side else None

    def _llm_opfor_tick(self) -> None:
        side = self.llm_opfor_side()
        request = self._llm_opfor_request
        if request is not None and request.finished:
            self._llm_opfor_request = None
            chosen = opponent.parse(self._llm_opfor_side, request.text) if request.ok else None
            if chosen is not None and side == self._llm_opfor_side:
                self.llm_opfor = {"side": side, "plan": chosen[0], "since": float(self.sim_t)}
                self.llm_experimental = True
        if side is None or self._llm_opfor_request is not None:
            return
        if self._llm_opfor_next is None:
            self._llm_opfor_next = float(self.sim_t)
        if self.sim_t < self._llm_opfor_next:
            return
        self._llm_opfor_next = float(self.sim_t) + opponent.INTERVAL_S
        self._llm_opfor_side = side
        self._llm_opfor_request = opponent.request(self.llm, side, self)

    # -- 7: mission generator (Mission Editor; the web planner in the bridge) --

    def generate_mission(self, text: str, side: str):
        """Mission Editor: ask for a mission; None when sent, else why not."""
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        keys = getattr(getattr(self, "editor", None), "profile_keys", None)
        return self.mission_gen.start(
            self.llm, self.llm_language(), side, text, key=f"user.llm_{stamp}",
            owner="editor", profile_keys=keys)

    def _poll_mission_generator(self) -> None:
        gen = self.mission_gen
        if not gen.poll() or gen.owner != "editor":
            return
        editor = getattr(self, "editor", None)
        if editor is not None and hasattr(editor, "generated"):
            editor.generated(gen.mission, gen.error, gen.issues)
        gen.reset()

    # -- 1: radio messages worded like radio traffic ----------------------------

    def llm_radio_offer(self, stamp, text, side: str = "frigate") -> None:
        if not (self.llm.active and self.preferences.llm_radio):
            return
        with translation_scope(self.tr):
            original = localize(text, self.tr)
        self.llm_radio.offer(self.llm, self.llm_language(), side,
                             message_key(stamp, original), original)

    def llm_radio_text(self, stamp, text):
        """The worded version of one radio message, or None."""
        if not self.llm_radio.styled:
            return None
        return self.llm_radio.get(message_key(stamp, localize(text, self.tr)))

    def _llm_boat_orders(self) -> None:
        """Offer the crewed boat's open HQ order once for wording."""
        boat = getattr(self, "_opfor", None)
        if boat is None or not (self.llm.active and self.preferences.llm_radio):
            return
        order = boat.radio.active_order()
        if order is None or order["id"] in self._llm_boat_offered:
            return
        from src.ui.uboot_radio import order_line
        self._llm_boat_offered.add(order["id"])
        with translation_scope(self.tr):
            original = localize(order_line(self, boat), self.tr)
        self.llm_radio.offer(self.llm, self.llm_language(), "uboot",
                             f"boat-order-{order['id']}", original)

    def llm_boat_order_text(self, order):
        if order is None or not self.llm_radio.styled:
            return None
        return self.llm_radio.get(f"boat-order-{order['id']}")

    # -- 3: after-action report ----------------------------------------------

    def _llm_mission_ended(self) -> None:
        """Queue one report per recorded side (the mission is over: truth allowed)."""
        if not self.llm.active:
            return
        sides = [("frigate", self.frigate_debrief)]
        if getattr(self, "boat_debrief", None) is not None:
            sides.append(("uboot", self.boat_debrief))
        for side, recorder in sides:
            text = self._debrief_facts(side, recorder)
            request = self.llm.submit("debrief", prompts.debrief(self.llm_language(), side, text),
                                      max_tokens=600, temperature=0.4)
            if request is not None:
                self._llm_report_requests[side] = request
                self.llm_reports[side] = dict(status="pending", text="")

    def _debrief_facts(self, side: str, recorder) -> str:
        from src.ui.debrief_view import event_text

        metrics = recorder.metrics()
        prefix = "debrief." if side == "frigate" else "debrief.boat."
        lines = [f"Side: {side}",
                 f"Mission: {localize(self.mission_name_display(), self.tr)}",
                 f"Duration: {metrics['duration_t'] / 60.0:.0f} min"]
        for name in ("first_contact_t", "first_fix_t", "classified_t"):
            value = metrics.get(name)
            if value is not None:
                lines.append(f"{name.replace('_t', '').replace('_', ' ')}: "
                             f"{value / 60.0:.1f} min")
        lines.append(f"Own shots: {metrics['shots']}, submarines sunk: {metrics['sunk']}, "
                     f"missed chances: {metrics['missed']}")
        if metrics.get("mean_error_nm") is not None:
            lines.append(f"Mean plot error: {metrics['mean_error_nm']:.2f} NM")
        lines.append("Timeline:")
        with translation_scope(self.tr):
            for event in recorder.events[-40:]:
                lines.append(f"- {event['t'] / 60.0:5.1f} min {event_text(event, prefix)}")
        return "\n".join(lines)

    def _poll_llm_reports(self) -> None:
        for side, request in list(self._llm_report_requests.items()):
            if not request.finished:
                continue
            del self._llm_report_requests[side]
            if not request.ok:
                self.llm_reports[side] = dict(status="failed", text="", error=request.error)
                continue
            text = clean_text(request.text, REPORT_MAX)
            self.llm_reports[side] = dict(status="done", text=text)
            self._logbook_attach_report(side, text)

    def llm_report(self, side: str):
        return self.llm_reports.get(side)

    def _logbook_attach_report(self, side: str, text: str) -> None:
        result = getattr(self, "logbook_result", None)
        local = "boat" if self._logbook_side() == "boat" else "frigate"
        if result is None or ("uboot" if local == "boat" else "frigate") != side:
            return
        book = logbook_model.load_logbook()
        if book.attach_report(result["entry"], text):
            logbook_model.save_logbook(book)

    # -- 12 to 15, 17: the executive officer ---------------------------------

    def advisor_side(self) -> str:
        return facts.side_of(self)

    def advisor_station(self):
        if self.advisor_side() == "uboot":
            return getattr(self, "uboot_station", "uboot")
        return self.station

    def _advisor_mission_running(self) -> bool:
        return not (self.main_menu or self.in_menu or self.game_over
                    or getattr(self, "editor", None) is not None)

    def advisor_ask(self, kind: str, text: str = "", *, asker: str = LOCAL,
                    side: str | None = None, station=None):
        """Ask the executive officer; the log entry or a reason key."""
        if not self._advisor_mission_running():
            return "not_ready"
        side = side or self.advisor_side()
        station = station if station is not None else self.advisor_station()
        result = self.advisor.ask(self.llm, self, asker, kind, side=side,
                                  language=self.llm_language(), text=text, station=station)
        if (isinstance(result, dict) and kind in advisor_model.HELP_KINDS
                and not (kind == "question" and advisor_model.looks_like_order(text))):
            self.llm_advisor_sides.add(side)
        return result

    @property
    def llm_advisor_used(self) -> bool:
        """The uConsole's own side had the advisor's help in this mission."""
        return self.advisor_side() in getattr(self, "llm_advisor_sides", ())

    def advisor_confirm(self, seq: int, *, asker: str = LOCAL, side: str | None = None):
        """Run a typed order the player confirmed (uConsole only; a browser
        sends the same station commands itself)."""
        entry = self.advisor.find(asker, seq)
        if entry is None or entry["proposal"] is None or entry["applied"]:
            return "stale_ref"
        if not self._advisor_mission_running():
            return "not_ready"
        results = advisor_model.apply_proposal(self, side or self.advisor_side(),
                                               entry["proposal"])
        entry["applied"] = True
        entry["results"] = results
        return all(results)

    def _coach_tick(self) -> None:
        level = getattr(self.preferences, "llm_coach", "off")
        interval = advisor_model.COACH_INTERVAL_S.get(level)
        if (interval is None or not self.llm.active or not self._advisor_mission_running()
                or self.llm_pvp()):
            self.advisor.coach_next_wall = None
            return
        now = self._t
        if self.advisor.coach_next_wall is None:
            self.advisor.coach_next_wall = now + interval
            return
        if now < self.advisor.coach_next_wall:
            return
        self.advisor.coach_next_wall = now + interval
        self.advisor_ask("coach")

    def _coach_banner(self, text: str) -> None:
        """The coach's tip as the banner of the uConsole's own side."""
        self.msg = message("llm.coach.flash", text=raw_text(text))
        self.msg_until = self._t + 10.0

    def llm_pvp(self) -> bool:
        """Two human crews against each other (the boat crewed by people and
        the frigate not sailed by the AI hunter)."""
        if getattr(self, "_opfor", None) is None:
            return False
        from src.core import hunter
        return not hunter.active(self)

    # -- 16: service-record review --------------------------------------------

    def request_logbook_review(self) -> bool:
        if not self.llm.active or self._llm_review_request is not None:
            return False
        book = getattr(self, "logbook_view", None) or logbook_model.load_logbook()
        if not book.entries:
            return False
        lines = []
        for side in logbook_model.SIDES:
            missions, wins = book.totals(side)
            lines.append(f"{side}: {missions} missions, {wins} won")
        lines.append("Latest missions (date, side, scenario, level, won, score, minutes, "
                     "shots, sunk, advisor):")
        for row in book.entries[-REVIEW_ENTRIES:]:
            lines.append(", ".join(str(row.get(name, "")) for name in (
                "date", "side", "scenario", "level", "won", "score", "minutes", "shots",
                "sunk")) + (", with advisor" if row.get("advisor") else ""))
        request = self.llm.submit("logbook", prompts.logbook(self.llm_language(),
                                                             "\n".join(lines)),
                                  max_tokens=500, temperature=0.4)
        if request is None:
            return False
        self._llm_review_request = request
        self.llm_review = dict(status="pending", text="")
        return True

    def _poll_llm_review(self) -> None:
        request = self._llm_review_request
        if request is None or not request.finished:
            return
        self._llm_review_request = None
        self.llm_review = (dict(status="done", text=clean_text(request.text, REPORT_MAX))
                           if request.ok else dict(status="failed", text="",
                                                   error=request.error))

    # -- settings ----------------------------------------------------------------

    def start_llm_test(self) -> bool:
        """One short request to show whether the server answers."""
        if not self.llm.active:
            self.llm_test = dict(status="failed", error="disabled")
            return False
        request = self.llm.submit("test", [
            {"role": "system", "content": "Reply with the single word OK."},
            {"role": "user", "content": "Radio check."}], max_tokens=32, temperature=0.0)
        self.llm_test = dict(status="pending", request=request,
                             started=datetime.datetime.now())
        if request is None:
            self.llm_test = dict(status="failed", error="busy")
            return False
        return True

    def llm_test_state(self) -> dict | None:
        test = self.llm_test
        if test is None or test["status"] != "pending":
            return test
        request = test["request"]
        if not request.finished:
            return test
        self.llm_test = (dict(status="done", latency_s=request.latency_s or 0.0)
                         if request.ok else dict(status="failed", error=request.error))
        return self.llm_test

    def set_llm_preference(self, name: str, value) -> None:
        self._set_preference(name, value)
        self.configure_llm()
        if name == "llm_url":
            self.configure_voice()      # it may share the model's key
            self.configure_stt()

    def save_llm_key(self, value: str) -> bool:
        ok = keystore.save_key(value)
        self.configure_llm()
        self.configure_voice()
        self.configure_stt()
        return ok
