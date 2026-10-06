"""The executive officer over Remote Crew (optional language model).

A browser holding a station asks at ``POST /api/v2/advisor`` (situation,
question, typed order, classification help, briefing); the request is
checked for shape here, queued detached and answered on the main thread by
the same advisor the uConsole uses (``src/llm/advisor.py``), from the
picture of the asker's own side only.  ``GET /api/v2/advisor`` returns the
asker's own log, never another client's, and after the mission the own
side's after-action report.

A typed order comes back as a proposal of ordinary station commands; the
browser sends them itself after the player confirms, through the normal
command pipeline with all of its checks.  Nothing here is saved.

With the host's voice set up the answer is spoken too: the host asks its
speech service (``src/core/game_voice.py``), the log entry then carries
``voice: true`` and the browser that asked fetches the audio at
``GET /api/v2/advisor/voice?seq=<n>`` (16-bit mono PCM, its rate in a
header), only its own; the service and its key stay on the host.
"""

from __future__ import annotations

from collections import deque

from src.commander.v2.wire import LOOKOUT_ROLES, OPFOR_ROLES, _json_bytes

ADVISOR_KINDS = ("situation", "question", "order", "classify", "briefing")
TEXT_KINDS = ("question", "order")
QUEUE_MAX = 8
TEXT_MAX = 300
VIEW_MAX_BYTES = 64 * 1024
VOICE_ROUTE = "/api/v2/advisor/voice?seq="


def valid_advisor_body(body) -> bool:
    if type(body) is not dict or set(body) != {"kind", "text"}:
        return False
    if body["kind"] not in ADVISOR_KINDS or type(body["text"]) is not str:
        return False
    text = body["text"]
    if body["kind"] in TEXT_KINDS:
        return 0 < len(text.strip()) <= TEXT_MAX and all(char.isprintable() for char in text)
    return text == ""


def side_of_role(role: str) -> str:
    return "uboot" if role in OPFOR_ROLES else "frigate"


class AdvisorRequest:
    __slots__ = ("asker", "client_id", "ordinal", "role", "kind", "text")

    def __init__(self, asker, client_id, ordinal, role, kind, text):
        self.asker = asker
        self.client_id = client_id
        self.ordinal = ordinal
        self.role = role
        self.kind = kind
        self.text = text


def asker_of(session) -> str:
    return f"web:{session['client_id']}:{session['ordinal']}"


class AdvisorServerMixin:
    """Request queue and publications of the advisor in ``CommanderServer``."""

    def _init_advisor(self):
        self._advisor_requests = deque()
        self._advisor_available = False
        self._advisor_logs = {}
        self._advisor_reasons = {}
        self._advisor_reports = {}
        self._advisor_voices = {}
        self._advisor_voice_rate = 0
        self._advisor_voice_on = False

    def _clear_advisor_locked(self):
        self._advisor_requests.clear()
        self._advisor_logs = {}
        self._advisor_reasons = {}
        self._advisor_reports = {}
        self._advisor_voices = {}

    def enqueue_advisor_locked(self, session, body) -> str:
        """"pending", or why not: "forbidden", "invalid", "busy", "queue_full"."""
        role = session["active_station"]
        if role is None or session.get("observer") or role in LOOKOUT_ROLES:
            return "forbidden"
        if not valid_advisor_body(body):
            return "invalid"
        asker = asker_of(session)
        if any(item.asker == asker for item in self._advisor_requests):
            return "busy"
        if len(self._advisor_requests) >= QUEUE_MAX:
            return "queue_full"
        self._advisor_requests.append(AdvisorRequest(
            asker, session["client_id"], session["ordinal"], role, body["kind"], body["text"]))
        return "pending"

    def take_advisor_requests(self) -> list:
        """Detach the queued requests whose session still holds that role."""
        with self._lock:
            items, self._advisor_requests = list(self._advisor_requests), deque()
            live = {(session["client_id"], session["ordinal"], session["active_station"])
                    for session in self._sessions_v2.values()}
        return [item for item in items if (item.client_id, item.ordinal, item.role) in live]

    def publish_advisor(self, available: bool, logs: dict, reasons: dict, reports: dict) -> None:
        with self._lock:
            self._advisor_available = bool(available)
            self._advisor_logs = logs
            self._advisor_reasons = reasons
            self._advisor_reports = reports

    def publish_advisor_voice(self, voices: dict, rate: int, on: bool = True) -> None:
        """``voices``: asker -> {seq: PCM bytes} (detached, bounded by the game);
        ``on``: the host speaks the officer's answers at all."""
        with self._lock:
            self._advisor_voices = voices
            self._advisor_voice_rate = int(rate)
            self._advisor_voice_on = bool(on)

    def advisor_voice_locked(self, session, path: str):
        """``(pcm, rate)`` of one of the asker's own spoken answers, or None."""
        role = session["active_station"]
        if role is None or session.get("observer") or role in LOOKOUT_ROLES:
            return None
        text = path[len(VOICE_ROUTE):]
        if not path.startswith(VOICE_ROUTE) or not text.isdigit() or len(text) > 9:
            return None
        pcm = self._advisor_voices.get(asker_of(session), {}).get(int(text))
        return None if pcm is None else (pcm, self._advisor_voice_rate)

    def advisor_body_locked(self, session):
        role = session["active_station"]
        if role is None or session.get("observer") or role in LOOKOUT_ROLES:
            return None
        asker = asker_of(session)
        log = self._advisor_logs.get(asker, [])
        body = _json_bytes({
            "protocol": 2, "available": self._advisor_available,
            # The host's voice says the answers: the browser waits for them.
            "voice": self._advisor_voice_on,
            "pending": any(item.asker == asker for item in self._advisor_requests)
            or any(row["status"] == "pending" for row in log),
            "reason": self._advisor_reasons.get(asker),
            "log": log, "report": self._advisor_reports.get(side_of_role(role))})
        return body if len(body) <= VIEW_MAX_BYTES else None


def web_entry(entry, voice: bool = False) -> dict:
    """One log entry as the browser receives it (detached, bounded);
    ``voice``: its spoken answer is ready to fetch."""
    from src.commander.v2.commands import V2_ACTION_REGISTRY

    proposal = None
    if entry["proposal"] is not None:
        # Each command names the stations that may give it: the browser sends
        # it only from one of them, through the normal command pipeline.
        proposal = [dict(type=row["type"], value=row["value"], action=row["action"],
                         params=dict(row["params"]),
                         stations=sorted(V2_ACTION_REGISTRY[row["action"]].stations))
                    for row in entry["proposal"]]
    return dict(seq=int(entry["seq"]), kind=entry["kind"], question=entry["question"][:TEXT_MAX],
                answer=entry["answer"][:1_600], status=entry["status"],
                error=entry["error"], proposal=proposal, voice=bool(voice))


def pump_advisor(server, game, published: dict) -> None:
    """Main thread: answer queued requests, publish what changed."""
    if not hasattr(server, "take_advisor_requests") or not hasattr(game, "advisor"):
        return
    reasons = dict(published.get("reasons", {}))
    for item in server.take_advisor_requests():
        result = game.advisor_ask(item.kind, item.text, asker=item.asker,
                                  side=side_of_role(item.role), station=item.role)
        reasons[item.asker] = result if isinstance(result, str) else None
    reports = {}
    if game.game_over:
        for side in ("frigate", "uboot"):
            state = game.llm_report(side)
            if state is not None:
                reports[side] = dict(status=state["status"], text=state.get("text", ""),
                                     error=state.get("error"))
    clips = getattr(game, "web_voice_clips", {})
    voice = getattr(game, "voice", None)
    voiced = (tuple(clips), bool(voice is not None and voice.active
                                 and game.preferences.tts_xo))
    key = (game.llm_active(), game.advisor.version, tuple(sorted(reasons.items())),
           tuple(sorted((side, row["status"]) for side, row in reports.items())), voiced)
    if published.get("key") == key:
        return
    if published.get("voiced") != voiced and hasattr(server, "publish_advisor_voice"):
        voices = {}
        for (asker, seq), pcm in clips.items():
            voices.setdefault(asker, {})[seq] = pcm
        server.publish_advisor_voice(voices, getattr(game, "web_voice_rate", 0), voiced[1])
    logs = {asker: [web_entry(entry, (asker, entry["seq"]) in clips) for entry in rows]
            for asker, rows in game.advisor.logs.items() if asker.startswith("web:")}
    server.publish_advisor(game.llm_active(), logs, reasons, reports)
    published.update(key=key, reasons=reasons, voiced=voiced)
