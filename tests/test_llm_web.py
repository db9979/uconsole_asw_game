"""Remote Crew side of the optional language model: the executive officer's
queue and log per asker, and the web planner's mission generator."""

import threading
from types import SimpleNamespace

from src.commander import advisor_web
from src.commander.mission_library import MissionLibrary
from src.commander.missions import valid_mission_op
from src.core.mission_definition import default_mission


class _Server(advisor_web.AdvisorServerMixin):
    def __init__(self):
        self._lock = threading.Lock()
        self._sessions_v2 = {}
        self._init_advisor()


def _session(client, station="bridge", **extra):
    return dict(client_id=client, ordinal=1, active_station=station, **extra)


def test_advisor_body_shape_is_strict():
    ok = advisor_web.valid_advisor_body
    assert ok({"kind": "situation", "text": ""})
    assert ok({"kind": "order", "text": "come to 120"})
    assert not ok({"kind": "situation", "text": "x"})          # no text for a report
    assert not ok({"kind": "order", "text": ""})
    assert not ok({"kind": "order", "text": "x" * 301})
    assert not ok({"kind": "fire", "text": ""})
    assert not ok({"kind": "situation", "text": "", "extra": 1})


def test_queue_is_per_asker_and_never_for_observers_or_lookouts():
    server = _Server()
    one, two = _session("a"), _session("b", "uboot")
    server._sessions_v2 = {"a": one, "b": two}
    body = {"kind": "situation", "text": ""}
    assert server.enqueue_advisor_locked(one, body) == "pending"
    assert server.enqueue_advisor_locked(one, body) == "busy"
    assert server.enqueue_advisor_locked(two, body) == "pending"
    assert server.enqueue_advisor_locked(_session("c", observer=True), body) == "forbidden"
    assert server.enqueue_advisor_locked(_session("d", "lookout"), body) == "forbidden"
    assert server.enqueue_advisor_locked(_session("e", None), body) == "forbidden"
    items = server.take_advisor_requests()
    assert [(item.asker, advisor_web.side_of_role(item.role)) for item in items] == [
        ("web:a:1", "frigate"), ("web:b:1", "uboot")]


def test_pump_answers_and_publishes_only_the_askers_own_log():
    server = _Server()
    one, two = _session("a"), _session("b")
    server._sessions_v2 = {"a": one, "b": two}
    server.enqueue_advisor_locked(one, {"kind": "briefing", "text": ""})
    asked = []
    entry = dict(seq=1, kind="briefing", question="", answer="Watch the layer.",
                 status="done", error=None, proposal=None, applied=False)
    advisor = SimpleNamespace(version=1, logs={"web:a:1": [entry]})

    def advisor_ask(kind, text, *, asker, side, station):
        asked.append((kind, asker, side, station))
        return entry

    game = SimpleNamespace(advisor=advisor, advisor_ask=advisor_ask, game_over=False,
                           llm_active=lambda: True, llm_report=lambda side: None)
    published = {}
    advisor_web.pump_advisor(server, game, published)
    assert asked == [("briefing", "web:a:1", "frigate", "bridge")]
    import json
    mine = json.loads(server.advisor_body_locked(one))
    theirs = json.loads(server.advisor_body_locked(two))
    assert mine["available"] and mine["log"][0]["answer"] == "Watch the layer."
    assert theirs["log"] == []


def test_generate_op_shape_and_result(tmp_path):
    base = {"protocol": 2, "id": "4f2a-11", "op": "generate"}
    assert valid_mission_op(dict(base, request="two subs in fog", side="frigate"))
    assert not valid_mission_op(dict(base, request="", side="frigate"))
    assert not valid_mission_op(dict(base, request="x", side="destroyer"))
    assert not valid_mission_op(dict(base, request="x" * 501, side="uboot"))
    library = MissionLibrary(root=tmp_path)
    key = library.generated_key("4F2A-11ab-cd")
    assert key == "user.llm_4f2a11abcd"
    mission = default_mission(key)
    gen = SimpleNamespace(status="done", owner=("web", "4F2A-11ab-cd"), mission=mission,
                          error=None, issues=[], reset=lambda: None)
    assert library.generated(SimpleNamespace(mission_gen=gen))
    view = library.view(0.0, force=True)
    assert view["results"][-1] == {"id": "4F2A-11ab-cd", "status": "applied",
                                   "reason": "generated", "issues": []}
    assert any(row["key"] == key for row in view["missions"])
    # Without a model the request is refused at once.
    off = SimpleNamespace(start=lambda *a, **k: "llm_off")
    library.generate(SimpleNamespace(body=dict(base, request="x", side="frigate")),
                     SimpleNamespace(mission_gen=off, llm=None, llm_language=lambda: "en"))
    assert library.view(0.0, force=True)["results"][-1]["reason"] == "llm_off"
