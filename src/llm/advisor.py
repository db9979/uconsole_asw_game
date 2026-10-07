"""The executive officer: situation report, questions, typed orders, contact
classification help, station briefing and the coach's tips.

All of it works only from the asking side's own picture (``facts.py``) and
the player's manual; nothing here reads a hidden entity.  A typed order is
never executed by the model: it becomes a proposal from a closed set of the
station orders the keys already give (course, speed, depth, quiet running,
action stations), each checked by the same validators the Remote Crew
commands use, and runs only after the player confirms it.  Weapons can
never be ordered this way.

Logs are kept per asker ("local" for the uConsole, a session digest for a
browser), bounded and transient: never saved, never shared between askers.
"""

from __future__ import annotations

import math
import re
from collections import OrderedDict, deque

from src.core import config
from src.core.i18n import get_translator
from src.llm import facts, manual_search, prompts
from src.llm.client import clean_text, parse_json_object

KINDS = ("situation", "question", "order", "classify", "briefing", "coach")
# Kinds that help the crew during a mission and mark it "with advisor".
HELP_KINDS = frozenset(("situation", "question", "order", "classify", "coach"))
MAX_LOG = 12
MAX_ASKERS = 12
MAX_PENDING = 3
MAX_TEXT = 300
MAX_ANSWER = 1_600
MAX_COMMANDS = 4
COACH_INTERVAL_S = {"rare": 300.0, "often": 120.0}

# Typed or spoken order -> existing station action, its single parameter
# (None: a one-shot action whose only value is true) and fixed parameters.
ORDER_SET = {
    "frigate": {
        "course": ("bridge_set_course", "course"),
        "speed": ("bridge_set_speed", "speed_kn"),
        "quiet": ("engine_set_quiet_mode", "enabled"),
        "action_stations": ("crew_action_stations", "enabled"),
        "radar": ("opz_set_radar", "enabled", {"domain": "surface"}),
        "ping": ("sonar_active_ping", None),
        "clear_baffles": ("bridge_clear_baffles", None),
        "helicopter_return": ("helicopter_return", None),
    },
    "uboot": {
        "course": ("uboot_set_course", "course"),
        "speed": ("uboot_set_speed", "speed_kn"),
        "depth": ("uboot_set_depth", "depth_m"),
        "silent": ("uboot_silent", "enabled"),
        "action_stations": ("uboot_action_stations", "enabled"),
        "mast": ("uboot_mast", "enabled"),
        "snorkel": ("uboot_snorkel", "enabled"),
        "surface": ("uboot_surface", "enabled"),
        "evade": ("uboot_evade", None),
        "clear_baffles": ("uboot_clear_baffles", None),
    },
}
_ORDER_HELP = {
    "course": "course: integer degrees 0-359 (true heading to steer; for a turn to "
              "starboard or port work it out from the own heading)",
    "speed": "speed: knots (number; 0 stops the engines, 'full ahead' is the top speed)",
    "depth": "depth: metres below the surface (number)",
    "quiet": "quiet: true or false (quiet running of the engines)",
    "silent": "silent: true or false (silent running)",
    "action_stations": "action_stations: true or false (battle stations)",
    "radar": "radar: true or false (surface search radar on or off)",
    "ping": "ping: true (one active sonar transmission)",
    "clear_baffles": "clear_baffles: true (a turn to listen into the baffles)",
    "helicopter_return": "helicopter_return: true (the helicopter flies back to the ship)",
    "mast": "mast: true or false (raise or lower the ESM mast; periscope depth only)",
    "snorkel": "snorkel: true or false (snorkel and run the diesels, or stop)",
    "surface": "surface: true to surface, false for a crash dive",
    "evade": "evade: true (the evasion manoeuvre against a threat)",
}


# A question put as an order ("Volle Fahrt voraus", "come right to 090"):
# the officer only answers questions, so the game itself says that nothing
# was done instead of letting the model repeat the order back as if it had
# been carried out.  Questions (a "?" or a question word first) never match.
_QUESTION_WORDS = frozenset((
    "wie", "was", "wo", "wohin", "woher", "wann", "warum", "wieso", "weshalb", "wer",
    "wen", "wem", "welche", "welcher", "welches", "welchen", "soll", "sollen", "sollte",
    "sollten", "kann", "können", "koennen", "könnte", "darf", "dürfen", "ist", "sind",
    "gibt", "hat", "haben", "wird", "werden", "muss", "müssen", "erkläre",
    "erklär", "sag", "sage", "nenne", "zeig", "zeige",
    "how", "what", "where", "when", "why", "who", "whom", "which", "should", "shall",
    "can", "could", "may", "is", "are", "do", "does", "did", "will", "would", "has",
    "have", "explain", "tell", "describe", "show",
))
_ORDER_PATTERNS = re.compile("|".join((
    # German helm and engine orders
    r"\b(kleine|halbe|volle|äußerste|äusserste|aeusserste|langsame)\s+fahrt\b",
    r"\bfahrt\s+(voraus|zurück|zurueck)\b", r"\balle\s+maschinen\b",
    r"\bmaschinen?\s+(stopp|stop|halt)\b", r"\b(neuer\s+)?kurs\s+\d", r"\bauf\s+kurs\b",
    r"\bruder\b", r"\b(hart\s+)?(steuerbord|backbord)\b", r"\bmittschiffs\b",
    r"\b(tiefe|auf)\s+\d+\s*(m|meter|metern)\b", r"\bsehrohrtiefe\b",
    r"\b(ab|auf)?tauchen\b", r"\bfluten\b", r"\banblasen\b", r"\bfeuer\b",
    r"\brohr\s+\w+\s+los\b", r"\b(los|abfeuern|schießen|schiessen)\b",
    r"\bschleichfahrt\b", r"\bleisefahrt\b", r"\bgefechtsstation(en)?\b",
    r"\b(alarm|stopp)\b", r"\b\d+\s*(knoten|kn)\b",
    # English helm and engine orders
    r"\b(all\s+)?(ahead|astern)\s+(full|flank|standard|slow|one\s+third|two\s+thirds)\b",
    r"\b(full|flank|half|slow)\s+(speed|ahead|astern)\b", r"\ball\s+stop\b",
    r"\b(come|steer|turn)\s+(left|right|to)\b", r"\bcourse\s+\d", r"\brudder\b",
    r"\bmake\s+depth\b", r"\bdepth\s+\d", r"\bperiscope\s+depth\b",
    r"\b(dive|surface|fire|launch|shoot)\b", r"\bsilent\s+running\b",
    r"\bbattle\s+stations\b", r"\bgeneral\s+quarters\b", r"\b\d+\s*(knots|kts)\b",
)))


def looks_like_question(text) -> bool:
    """True when ``text`` plainly asks: a "?" or a question word first."""
    if type(text) is not str:
        return False
    words = re.findall(r"[\wäöüß]+", text.lower())
    return "?" in text or (bool(words) and words[0] in _QUESTION_WORDS)


def looks_like_order(text) -> bool:
    """True when ``text`` reads as an order rather than a question."""
    if type(text) is not str or "?" in text:
        return False
    words = re.findall(r"[\wäöüß]+", text.lower())
    if not words or words[0] in _QUESTION_WORDS:
        return False
    return _ORDER_PATTERNS.search(" ".join(words)) is not None


class _Ready:
    """A reply the game gives itself, without asking the model."""

    finished = True
    ok = True
    error = None

    def __init__(self, text: str) -> None:
        self.text = text


def valid_question(text) -> bool:
    return (type(text) is str and 0 < len(text.strip()) <= MAX_TEXT
            and all(char.isprintable() for char in text))


def command_help(side: str, game=None) -> str:
    lines = ["- " + _ORDER_HELP[name] for name in ORDER_SET[side]]
    boat = getattr(game, "opfor", None) if side == "uboot" else None
    if boat is not None:
        from src.core import opfor
        presets = [f"{name.replace('_', ' ')} {round(depth)} m"
                   for name, depth in opfor.depth_presets(game, boat).items()
                   if depth is not None]
        if presets:
            lines.append("Depths now: " + ", ".join(presets))
    return "\n".join(lines)


def parse_order(side: str, payload) -> list | None:
    """The model's order JSON as ``[{type, value, action, params}]`` or None.

    Every command must be in the side's order set and pass the action's own
    Remote Crew validator; one bad command rejects the whole proposal.
    """
    from src.commander.v2.commands import V2_ACTION_REGISTRY

    if not isinstance(payload, dict) or not isinstance(payload.get("commands"), list):
        return None
    commands = payload["commands"]
    if len(commands) > MAX_COMMANDS:
        return None
    out = []
    for row in commands:
        if not isinstance(row, dict) or row.get("type") not in ORDER_SET[side]:
            return None
        action, name, *fixed = ORDER_SET[side][row["type"]]
        value = row.get("value")
        if name is None:
            if value not in (True, "true", "on", 1):
                return None
            value = True
        elif name == "enabled":
            if isinstance(value, str) and value.lower() in ("true", "false", "on", "off"):
                value = value.lower() in ("true", "on")
            if type(value) is not bool:
                return None
        else:
            if isinstance(value, str):
                try:
                    value = float(value)
                except ValueError:
                    return None
            if type(value) not in (int, float) or not math.isfinite(value):
                return None
            value = round(float(value)) % 360 if name == "course" else round(float(value), 1)
        params = {} if name is None else dict(*fixed, **{name: value})
        if not V2_ACTION_REGISTRY[action].validate_params(params):
            return None
        out.append(dict(type=row["type"], value=value, action=action, params=params))
    return out


def classify_lines(game, side: str, station=None) -> str:
    """The selected contact's measured features and the class library."""
    lines = []
    now = game.sim_t
    if side == "uboot":
        boat = getattr(game, "opfor", None)
        contact = boat.station.selected_contact if boat is not None else None
        if contact is None:
            return ""
        bearing = (contact.passive_bearing if contact.passive_bearing is not None
                   else contact.bearing)
        lines.append(f"Selected contact K{contact.id:02d}: bearing {bearing:03.0f}, "
                     f"heard for {max(0.0, now - contact.first_seen):.0f} s"
                     if hasattr(contact, "first_seen") else
                     f"Selected contact K{contact.id:02d}: bearing {bearing:03.0f}")
        if contact.player_class in config.PLAYER_CLASSES:
            lines.append(f"Current operator class: {contact.player_class}")
        return "\n".join(lines)
    if str(getattr(station, "name", station)).lower() == "eloka":
        track = game.selected_eloka_track()
        if track is None:
            return ""
        lines.append(f"Selected ESM track {track.track_key}: bearing {track.bearing:03.0f}")
        for candidate in game.eloka_display_candidates(track)[:5]:
            lines.append(f"- emitter candidate {candidate.emitter_key}")
        return "\n".join(lines)
    contact = getattr(game, "selected_contact", None)
    if contact is None:
        return ""
    bearing = (contact.passive_bearing if getattr(contact, "passive_bearing", None) is not None
               else contact.bearing)
    lines.append(f"Selected sonar contact {game.contact_display_id(contact)}: "
                 f"bearing {bearing:03.0f}")
    if contact.player_class in config.PLAYER_CLASSES:
        lines.append(f"Current operator class: {contact.player_class}")
    tools = getattr(game, "sonar_tools", None)
    if tools is not None:
        marks = []
        if tools.shaft_hz:
            marks.append(f"shaft line {tools.shaft_hz:.2f} Hz")
        if tools.blade_hz:
            marks.append(f"blade line {tools.blade_hz:.2f} Hz")
        if getattr(game, "sonar_harmonic_hz", None):
            marks.append(f"LOFAR fundamental {game.sonar_harmonic_hz:.1f} Hz")
        lines.append("Operator's marks: " + (", ".join(marks) if marks else "none yet"))
        try:
            ranking = game.sonar_class_library(limit=5)
        except Exception:  # noqa: BLE001 - help text only
            ranking = []
        for signature, fit in ranking:
            lines.append(f"- class library: {signature.key} fit {fit:.2f}")
    if getattr(contact, "tma_quality", 0) and contact.tma_course is not None:
        lines.append(f"TMA: course {contact.tma_course:03.0f}, speed "
                     f"{contact.tma_speed:.0f} kn, quality {contact.tma_quality:.2f}")
    return "\n".join(lines)


def briefing_lines(game, side: str, station_slug: str) -> str:
    from src.core import help as help_module

    keys = ()
    if side == "uboot":
        keys = help_module.UBOOT_SOP.get(station_slug, ())
    else:
        for station, steps in help_module.STATION_SOP.items():
            if station.name.lower() == station_slug:
                keys = steps
    steps = [game.tr(key) for key in keys]
    return ("Station: " + station_slug + "\nStation procedure:\n"
            + "\n".join(f"{i}. {text}" for i, text in enumerate(steps, 1)))


class Advisor:
    def __init__(self):
        self.logs: OrderedDict[str, deque] = OrderedDict()
        self._pending: list = []
        self._spoken: set = set()
        self._seq = 0
        self.version = 0
        self.coach_next_wall = None

    def reset(self) -> None:
        self.version += 1
        self.logs.clear()
        self._pending.clear()
        self._spoken.clear()
        self.coach_next_wall = None

    def log(self, asker: str) -> list:
        return list(self.logs.get(asker, ()))

    def pending(self, asker: str) -> bool:
        return any(row[0] == asker for row in self._pending)

    def _entry(self, asker: str, kind: str, question: str) -> dict:
        self._seq += 1
        entry = dict(seq=self._seq, kind=kind, question=question, answer="",
                     status="pending", error=None, proposal=None, applied=False)
        log = self.logs.get(asker)
        if log is None:
            while len(self.logs) >= MAX_ASKERS:
                self.logs.popitem(last=False)
            log = self.logs[asker] = deque(maxlen=MAX_LOG)
        self.logs.move_to_end(asker)
        log.append(entry)
        self.version += 1
        return entry

    def ask(self, service, game, asker: str, kind: str, *, side: str, language: str,
            text: str = "", station=None, spoken: bool = False,
            orders_locked: bool = False):
        """Queue one question; the new entry, or a reason string.

        ``spoken``: what the captain said with the talk key, as an "order"
        entry the model either turns into commands or, when it is no order,
        answers as a question (the entry's kind then becomes "question").
        ``orders_locked``: other people crew the stations (multiplayer), so
        the officer takes no orders, typed or spoken."""
        if kind not in KINDS:
            return "invalid_value"
        if kind in ("question", "order") and not valid_question(text):
            return "invalid_value"
        if not service.active:
            return "llm_off"
        if self.pending(asker) or len(self._pending) >= MAX_PENDING:
            return "llm_busy"
        if kind == "order" and orders_locked and not spoken:
            return "orders_locked"
        if kind == "question" and looks_like_order(text):
            answer = get_translator(language).translate(
                "advisor.orders_locked" if orders_locked else "advisor.not_an_order")
            entry = self._entry(asker, kind, " ".join(text.split()))
            self._pending.append((asker, entry, _Ready(answer), side))
            return entry
        picture = facts.situation(game, side)
        extra = ""
        if kind == "question" or spoken:
            hint = str(getattr(station, "name", station or "")).lower() or None
            extra = manual_search.excerpts(text, language, hint)
        elif kind == "classify":
            extra = classify_lines(game, side, station)
            if not extra:
                return "no_contact"
        elif kind == "briefing":
            slug = str(getattr(station, "name", station or "")).lower()
            extra = briefing_lines(game, side, slug)
        if kind == "order" and spoken:
            messages = prompts.spoken(language, side, picture, command_help(side, game),
                                      text, extra)
            request = service.submit("order", messages, max_tokens=480, temperature=0.2,
                                     json_mode=True)
        elif kind == "order":
            messages = prompts.order(language, side, picture, command_help(side, game), text)
            request = service.submit("order", messages, max_tokens=220, temperature=0.1,
                                     json_mode=True)
        else:
            messages = prompts.advisor(language, side, kind, picture, text, extra,
                                       orders_locked=orders_locked)
            request = service.submit("advisor", messages, max_tokens=420, temperature=0.5)
        if request is None:
            return "llm_busy"
        entry = self._entry(asker, kind, " ".join(text.split()))
        self._pending.append((asker, entry, request, side))
        if spoken:
            self._spoken.add(entry["seq"])
        return entry

    def poll(self) -> list:
        """Collect finished answers; returns the entries that changed."""
        changed, still = [], []
        for asker, entry, request, side in self._pending:
            if not request.finished:
                still.append((asker, entry, request, side))
                continue
            spoken = entry["seq"] in self._spoken
            self._spoken.discard(entry["seq"])
            if not request.ok:
                entry.update(status="failed", error=request.error or "network")
            elif spoken:
                self._finish_spoken(side, entry, parse_json_object(request.text))
            elif entry["kind"] == "order":
                payload = parse_json_object(request.text)
                proposal = parse_order(side, payload)
                say = clean_text((payload or {}).get("say", ""), 240) if payload else ""
                if proposal is None:
                    entry.update(status="failed", error="bad_reply", answer=say)
                else:
                    entry.update(status="done", proposal=proposal, answer=say)
            else:
                entry.update(status="done", answer=clean_text(request.text, MAX_ANSWER))
            changed.append(entry)
        self._pending = still
        if changed:
            self.version += 1
        return changed

    @staticmethod
    def _finish_spoken(side: str, entry: dict, payload) -> None:
        """Commands for the game to carry out, or the answer to a question;
        a reply that is neither stays "not understood" (status failed)."""
        if not isinstance(payload, dict) or not isinstance(payload.get("commands"), list):
            entry.update(status="failed", error="bad_reply")
            return
        if payload["commands"]:
            proposal = parse_order(side, payload)
            if proposal is None:
                entry.update(status="failed", error="bad_reply")
            else:
                entry.update(status="done", proposal=proposal,
                             answer=clean_text(payload.get("say", ""), 240))
            return
        if payload.get("refused") is True:
            entry.update(status="failed", error="not_possible")
            return
        answer = clean_text(payload.get("answer") or "", MAX_ANSWER)
        if not answer:
            entry.update(status="failed", error="bad_reply")
        else:
            entry.update(kind="question", status="done", proposal=None, answer=answer)

    def find(self, asker: str, seq: int):
        return next((entry for entry in self.logs.get(asker, ()) if entry["seq"] == seq), None)


def apply_proposal(game, side: str, proposal) -> list:
    """Run a confirmed order through the station handlers; result per command."""
    from src.commander import actions

    results = []
    for command in proposal or ():
        action, params = command["action"], dict(command["params"])
        if side == "uboot":
            boat = getattr(game, "opfor", None)
            handler = actions._UBOOT_ACTION_HANDLERS.get(action)
            result = ("not_ready" if boat is None or handler is None
                      else handler(game, boat, params, None))
        else:
            handler = actions._V2_ACTION_HANDLERS.get(action)
            result = "not_ready" if handler is None else handler(game, params, None)
        results.append(result is True or result == "ok")
    return results
