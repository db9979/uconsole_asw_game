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
from collections import OrderedDict, deque

from src.core import config
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

# Typed order -> existing station action and its single parameter.
ORDER_SET = {
    "frigate": {
        "course": ("bridge_set_course", "course"),
        "speed": ("bridge_set_speed", "speed_kn"),
        "quiet": ("engine_set_quiet_mode", "enabled"),
        "action_stations": ("crew_action_stations", "enabled"),
    },
    "uboot": {
        "course": ("uboot_set_course", "course"),
        "speed": ("uboot_set_speed", "speed_kn"),
        "depth": ("uboot_set_depth", "depth_m"),
        "silent": ("uboot_silent", "enabled"),
        "action_stations": ("uboot_action_stations", "enabled"),
    },
}
_ORDER_HELP = {
    "course": "course: integer degrees 0-359 (true heading to steer)",
    "speed": "speed: knots (number)",
    "depth": "depth: metres below the surface (number)",
    "quiet": "quiet: true or false (quiet running of the engines)",
    "silent": "silent: true or false (silent running)",
    "action_stations": "action_stations: true or false (battle stations)",
}


def valid_question(text) -> bool:
    return (type(text) is str and 0 < len(text.strip()) <= MAX_TEXT
            and all(char.isprintable() for char in text))


def command_help(side: str) -> str:
    return "\n".join("- " + _ORDER_HELP[name] for name in ORDER_SET[side])


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
        action, name = ORDER_SET[side][row["type"]]
        value = row.get("value")
        if name == "enabled":
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
        params = {name: value}
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
        self._seq = 0
        self.version = 0
        self.coach_next_wall = None

    def reset(self) -> None:
        self.version += 1
        self.logs.clear()
        self._pending.clear()
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
            text: str = "", station=None):
        """Queue one question; the new entry, or a reason string."""
        if kind not in KINDS:
            return "invalid_value"
        if kind in ("question", "order") and not valid_question(text):
            return "invalid_value"
        if not service.active:
            return "llm_off"
        if self.pending(asker) or len(self._pending) >= MAX_PENDING:
            return "llm_busy"
        picture = facts.situation(game, side)
        extra = ""
        if kind == "question":
            hint = str(getattr(station, "name", station or "")).lower() or None
            extra = manual_search.excerpts(text, language, hint)
        elif kind == "classify":
            extra = classify_lines(game, side, station)
            if not extra:
                return "no_contact"
        elif kind == "briefing":
            slug = str(getattr(station, "name", station or "")).lower()
            extra = briefing_lines(game, side, slug)
        if kind == "order":
            messages = prompts.order(language, side, picture, command_help(side), text)
            request = service.submit("order", messages, max_tokens=220, temperature=0.1,
                                     json_mode=True)
        else:
            messages = prompts.advisor(language, side, kind, picture, text, extra)
            request = service.submit("advisor", messages, max_tokens=420, temperature=0.5)
        if request is None:
            return "llm_busy"
        entry = self._entry(asker, kind, " ".join(text.split()))
        self._pending.append((asker, entry, request, side))
        return entry

    def poll(self) -> list:
        """Collect finished answers; returns the entries that changed."""
        changed, still = [], []
        for asker, entry, request, side in self._pending:
            if not request.finished:
                still.append((asker, entry, request, side))
                continue
            if not request.ok:
                entry.update(status="failed", error=request.error or "network")
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
