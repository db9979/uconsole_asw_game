"""Solo Remote Crew: one paired browser holds every station of the same game."""

from contextlib import closing
import hashlib
import http.client
import json
import time

import pytest

from src.commander.server import (CommanderServer, OPFOR_ROLES, ROLES, STATIONS,
                                  V2_ACTION_REGISTRY,
                                  V2CommandEnvelope)
from src.core import config
from src.core.game import Game
from src.ui import layout
from commander_fixtures import PLOT, WEATHER_STATION


@pytest.fixture
def server():
    instance = CommanderServer()
    instance.start("127.0.0.1", 0)
    try:
        yield instance
    finally:
        instance.stop()


@pytest.fixture
def game():
    instance = Game(seed=31, start_menu=False, audio_enabled=False, language="en")
    yield instance
    instance.audio.shutdown()
    layout.configure_for(large_text=False)


def request(server, path, method="GET", body=None, cookie=None, csrf=None):
    host, port = server.address
    headers = {}
    if method == "POST":
        headers.update(Origin=f"http://{host}:{port}",
                       **{"Content-Type": "application/json"})
    if cookie:
        headers["Cookie"] = cookie
    if csrf:
        headers["X-U-Jagd-CSRF"] = csrf
    payload = None if body is None else json.dumps(body)
    with closing(http.client.HTTPConnection(host, port, timeout=3)) as connection:
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        return response.status, dict(response.getheaders()), (
            json.loads(raw) if raw else None)


def pair(server, name="Solo"):
    status, headers, session = request(server, "/api/v2/pair", "POST", {
        "code": server.pairing_code, "name": name})
    return status, headers, session


def solo_pair(server):
    server.set_solo_mode(True)
    status, headers, session = pair(server)
    assert status == 200
    return headers["Set-Cookie"].split(";", 1)[0], session


def post_command(server, cookie, session, station, **changes):
    body = {
        "protocol": 2, "id": "c1", "seq": session["next_command_seq"],
        "station": station,
        "station_generation": session["stations"][station]["station_generation"],
        "active_generation": session["active_generation"],
        "world_session": "w", "world_epoch": 0, "resource_revision": 0,
        "action": "acknowledge", "params": {},
    }
    body.update(changes)
    return request(server, "/api/v2/commands", "POST", body, cookie, session["csrf"])


def test_default_pairing_is_the_unchanged_crew_mode(server):
    assert server.solo_mode is False
    status, _, session = pair(server)
    assert status == 200 and session["host"] is None
    assert session["station"] is None and session["simlog"] is False
    assert all(row["status"] == "available" for row in session["stations"].values())


def test_solo_pairing_leases_every_station_with_full_grants(server):
    cookie, session = solo_pair(server)
    assert session["host"] == {"generation": 1}
    assert session["active_station"] == session["station"] == "bridge"
    assert session["simlog"] is True and session["grants"]["simlog"] is True
    assert list(session["stations"]) == list(ROLES)
    # Solo is the frigate console: the submarine roles are never part of it.
    assert all(session["stations"][role]["status"] == "available" for role in OPFOR_ROLES)
    for station in STATIONS:
        row = session["stations"][station]
        assert row["status"] == "mine" and row["station_generation"] >= 1
        assert row["grants"] == {
            "command": True,
            "direct_fire": station in ("weapons", "helicopter", "opz"),
            "sonar_audio": station in ("sonar", "helicopter")}
    # Generations are independent per-station counters.
    assert {session["stations"][station]["station_generation"]
            for station in STATIONS} == {1}


def test_solo_allows_exactly_one_session_until_the_host_removes_it(server):
    _, session = solo_pair(server)
    status, _, body = pair(server, "Second")
    assert (status, body) == (429, {"error": "session_limit"})
    assert server.revoke_client(session["client_id"])
    assert pair(server, "Second")[0] == 200


def test_changing_mode_revokes_sessions_and_rotates_the_code(server):
    code = server.pairing_code
    _, headers, _ = pair(server)
    cookie = headers["Set-Cookie"].split(";", 1)[0]
    server.set_solo_mode(False)  # unchanged mode is not a new security session
    assert server.pairing_code == code
    assert request(server, "/api/v2/session", cookie=cookie)[0] == 200
    server.set_solo_mode(True)
    assert server.pairing_code != code
    assert request(server, "/api/v2/session", cookie=cookie)[0] == 401
    with pytest.raises(ValueError):
        server.set_solo_mode(1)


def test_solo_leases_survive_a_presence_lapse_but_crew_leases_do_not(server):
    cookie, session = solo_pair(server)
    with server._lock:
        for value in server._sessions_v2.values():
            value["presence"] = time.monotonic() - 3600
    assert all(server.station_leased(station) for station in STATIONS)
    server.set_solo_mode(False)
    _, headers, crew = pair(server)
    assert server.grant_station(crew["client_id"], "bridge")
    with server._lock:
        for value in server._sessions_v2.values():
            value["presence"] = time.monotonic() - 3600
    assert not server.station_leased("bridge")


def test_solo_rebase_keeps_the_browser_paired_under_fresh_generations(server):
    cookie, session = solo_pair(server)
    code = server.pairing_code
    assert request(server, "/api/v2/stations/activate", "POST", {
        "station": "sonar",
        "station_generation": session["stations"]["sonar"]["station_generation"],
        "active_generation": session["active_generation"]}, cookie, session["csrf"])[0] == 200
    queued = post_command(server, cookie, request(
        server, "/api/v2/session", cookie=cookie)[2], "sonar")
    assert queued[0] == 202

    server.solo_rebase()

    assert server.pairing_code == code
    after = request(server, "/api/v2/session", cookie=cookie)[2]
    assert after["csrf"] == session["csrf"] and after["client_id"] == session["client_id"]
    assert after["host"] == {"generation": 2}
    assert after["active_station"] == "sonar"  # the tab the operator was on
    assert after["active_generation"] > session["active_generation"]
    for station in STATIONS:
        assert (after["stations"][station]["station_generation"]
                > session["stations"][station]["station_generation"])
    results = request(server, "/api/v2/results", cookie=cookie)[2]["results"]
    assert [(row["id"], row["status"], row["reasoncode"]) for row in results] == [
        ("c1", "rejected", "session_revoked")]
    # Commands prepared for the old world fail closed on the stale generation.
    stale = post_command(server, cookie, session, "sonar", id="old", seq=after["next_command_seq"])
    assert stale[0] == 409


def test_crew_sessions_are_still_revoked_by_a_rebase(server):
    _, headers, crew = pair(server)
    cookie = headers["Set-Cookie"].split(";", 1)[0]
    assert server.grant_station(crew["client_id"], "bridge")
    server.solo_rebase()
    assert request(server, "/api/v2/session", cookie=cookie)[2]["station"] is None


def test_world_replacement_keeps_a_solo_browser_but_revokes_a_crew_browser(
        game, server):
    bridge = game.commander.bridge
    bridge.pump(game, server, now=time.monotonic())
    cookie, session = solo_pair(server)
    code = server.pairing_code
    bridge.allowed = True
    bridge.pump(game, server, now=time.monotonic())

    game.reset(game.seed)
    bridge.pump(game, server, now=time.monotonic())

    assert server.pairing_code == code
    after = request(server, "/api/v2/session", cookie=cookie)
    assert after[0] == 200 and after[2]["client_id"] == session["client_id"]
    assert all(after[2]["stations"][station]["status"] == "mine" for station in STATIONS)
    assert after[2]["host"]["generation"] == 2

    # The same replacement in crew mode is a hard security boundary.
    server.set_solo_mode(False)
    status, headers, crew = pair(server)
    crew_cookie = headers["Set-Cookie"].split(";", 1)[0]
    bridge.pump(game, server, now=time.monotonic())
    game.reset(game.seed)
    bridge.pump(game, server, now=time.monotonic())
    assert request(server, "/api/v2/session", cookie=crew_cookie)[0] == 401
    assert server.pairing_code != code


def _authority(server, token, session, role):
    digest = hashlib.sha256(token.encode("ascii")).digest()
    lease = session["stations"][role]["station_generation"]
    body = json.dumps({"id": role}).encode("ascii")
    return V2CommandEnvelope(digest, session["client_id"], session["ordinal"], role,
                             lease, session["active_generation"], time.monotonic(),
                             body, role, 0)


def test_one_solo_session_can_hold_target_and_navigation_proposals_at_once(server):
    server.set_solo_mode(True)
    status, headers, session = pair(server)
    cookie = headers["Set-Cookie"].split(";", 1)[0]
    token = cookie.split("=", 1)[1]
    sonar = _authority(server, token, session, "sonar")
    helm = _authority(server, token, session, "bridge")
    assert server.authority_current_v2(sonar) and server.authority_current_v2(helm)

    server.publish_v2(*_publication())
    server.publish_proposals_v2(
        world_session="s", world_epoch=0,
        target_authority=sonar, target={"ref": "r1", "label": "C001",
                                        "status": "pending"},
        navigation_authority=helm, navigation={"course": 90.0, "speed_kn": None,
                                                "status": "pending"})

    bridge_view = request(server, "/api/v2/proposals", cookie=cookie)[2]
    assert bridge_view["role"] == "bridge"
    assert bridge_view["navigation"]["course"] == 90.0 and bridge_view["target"] is None
    assert request(server, "/api/v2/stations/activate", "POST", {
        "station": "sonar",
        "station_generation": session["stations"]["sonar"]["station_generation"],
        "active_generation": session["active_generation"]}, cookie,
        session["csrf"])[0] == 200
    sonar_view = request(server, "/api/v2/proposals", cookie=cookie)[2]
    assert sonar_view["role"] == "sonar" and sonar_view["navigation"] is None
    assert sonar_view["target"]["ref"] == "r1"


def _publication():
    common = dict(protocol=2, version="t", session="s", epoch=0, revision=0, seq=1,
                  phase="live", chart_revision="s", clock={}, environment={},
                  mission={}, autocrew={"enabled": False, "status": "off"}, autocrew_overview=[],
                  audio={"events": []}, weather_station=WEATHER_STATION, plot=PLOT)
    chart = dict(protocol=2, revision="s", size_nm=500, landmasses=[], disclaimer="")
    redacted = {key: common[key] for key in (
        "protocol", "version", "session", "epoch", "revision", "seq", "phase",
        "chart_revision")} | {"role": None}
    states = {None: redacted, **{role: dict(common, role=role, **{role: {}})
                                 for role in ROLES}}
    return states, {None: chart, **{role: chart for role in ROLES}}


def test_publication_serialises_a_shared_chart_once_and_serves_every_role(server):
    states, charts = _publication()
    shared = charts["bridge"]
    assert all(charts[role] is shared for role in STATIONS)
    server.publish_v2(states, charts)
    with server._lock:
        assert all(server._v2_charts[role] == server._v2_charts["bridge"]
                   for role in STATIONS)


def test_autostart_solo_binds_a_listener_in_solo_mode_and_never_persists(game, tmp_path):
    console = game.commander
    console.prepare = lambda: None
    console.hosts, console.host, console.port = ("127.0.0.1",), "127.0.0.1", 0
    try:
        console.autostart_solo()
        assert console.error is None and console.solo is True
        assert console.address is not None and console.server.solo_mode is True
        assert console.pairing_code == console.server.pairing_code
        assert not hasattr(game.preferences, "solo")  # never a saved preference
    finally:
        console.stop()


def test_solo_flag_is_a_launch_option_wired_before_the_main_loop(monkeypatch):
    import main as entry

    calls = []

    class FakeConsole:
        def autostart_solo(self):
            calls.append("solo")

    class FakeGame:
        commander = FakeConsole()

        def __init__(self, **_kwargs):
            calls.append("init")

        def run(self):
            calls.append("run")

    monkeypatch.setattr(entry, "Game", FakeGame)
    monkeypatch.setattr(entry, "load_preferences", lambda: type(
        "P", (), {"fullscreen": False, "audio": False})())
    assert entry.main(["--solo-crew", "--windowed", "5"]) == 0
    assert calls == ["init", "solo", "run"]
    calls.clear()
    assert entry.main(["5"]) == 0
    assert calls == ["init", "run"]


# --- host command surface -------------------------------------------------

@pytest.fixture
def solo(game, server, tmp_path, monkeypatch):
    """A paired solo browser over a real Game/bridge, saving only into tmp_path."""
    from src.core import config
    monkeypatch.setattr(config, "SAVE_DIR", str(tmp_path))
    bridge = game.commander.bridge
    bridge.pump(game, server, now=time.monotonic())
    cookie, session = solo_pair(server)
    bridge.allowed = True
    bridge.pump(game, server, now=time.monotonic())
    return type("Solo", (), dict(game=game, server=server, bridge=bridge,
                                 cookie=cookie, tmp=tmp_path))


def session_of(s):
    return request(s.server, "/api/v2/session", cookie=s.cookie)[2]


def host_body(s, action, params, cid, **changes):
    session = session_of(s)
    status = s.bridge.status
    body = {
        "protocol": 2, "id": cid, "seq": session["next_command_seq"],
        "station": "host", "station_generation": session["host"]["generation"],
        "active_generation": 0, "world_session": status["session"],
        "world_epoch": status["epoch"], "resource_revision": status["revision"],
        "action": action, "params": params,
    }
    body.update(changes)
    return body


def send(s, body):
    return request(s.server, "/api/v2/commands", "POST", body, s.cookie,
                   session_of(s)["csrf"])


def host(s, action, params, cid):
    """Post one host command, run the frame, and return its terminal result.

    A frame first settles any gate change (load, new game) so the body carries
    the epoch the browser would have read from the published state.
    """
    s.bridge.pump(s.game, s.server, now=time.monotonic())
    status, _, reply = send(s, host_body(s, action, params, cid))
    assert (status, reply["status"]) == (202, "pending")
    s.bridge.pump(s.game, s.server, now=time.monotonic())
    rows = request(s.server, "/api/v2/results", cookie=s.cookie)[2]["results"]
    return next(row for row in rows if row["id"] == cid)


def host_view(s):
    status, _, body = request(s.server, "/api/v2/host", cookie=s.cookie)
    assert status == 200
    return body


def test_host_view_is_published_only_to_a_solo_session(solo):
    view = host_view(solo)
    assert view["protocol"] == 2 and view["phase"] == "live"
    # Real time only: the host view carries no pause or time-scale state.
    assert "paused" not in view and "time_scale" not in view
    assert [row["key"] for row in view["scenarios"]] == [
        "s1_patrouille", "s2_doppeljagd", "s3_abfang", "s4_zufall"]
    assert [row["name"] for row in view["difficulty_fields"]] == list(
        config.DIFFICULTY_FIELD_ORDER)
    assert view["difficulty"] == config.DEFAULT_DIFFICULTY
    assert [row["slot"] for row in view["slots"]] == [1, 2, 3, 4, 5]
    assert all(row == {"slot": row["slot"], "saved": False, "modified": None}
               for row in view["slots"])
    assert request(solo.server, "/api/v2/host")[0] == 401


def test_crew_sessions_have_no_host_surface(server, game):
    game.commander.bridge.pump(game, server, now=time.monotonic())
    status, headers, session = pair(server)
    cookie = headers["Set-Cookie"].split(";", 1)[0]
    assert request(server, "/api/v2/host", cookie=cookie)[0] == 403
    body = {"protocol": 2, "id": "h", "seq": 0, "station": "host",
            "station_generation": 0, "active_generation": 0, "world_session": "w",
            "world_epoch": 0, "resource_revision": 0, "action": "host_save",
            "params": {"slot": 1}}
    assert request(server, "/api/v2/commands", "POST", body, cookie,
                   session["csrf"])[0] == 403


@pytest.mark.parametrize(("action", "params"), [
    ("host_pause", {}), ("host_resume", {}), ("host_time_scale", {"index": 0}),
])
def test_there_is_no_pause_or_time_scale_host_command(solo, action, params):
    assert action not in V2_ACTION_REGISTRY
    assert send(solo, host_body(solo, action, params, "gone"))[0] == 400
    before = solo.game.sim_t
    solo.game.update(.1)
    assert solo.game.sim_t > before


@pytest.mark.parametrize(("action", "params"), [
    ("host_pause", {"x": 1}), ("host_time_scale", {"index": 6}),
    ("host_time_scale", {"index": -1}), ("host_time_scale", {"index": True}),
    ("host_time_scale", {"index": 1.0}), ("host_save", {"slot": 0}),
    ("host_save", {"slot": 6}), ("host_save", {"slot": True}),
    ("host_load", {"slot": "1"}), ("host_load", {}),
    ("host_new_game", {"scenario": "s1_patrouille"}),
    ("host_new_game", {"scenario": "nope", "world_mode": "fixed"}),
    ("host_new_game", {"scenario": "s1_patrouille", "world_mode": "flat"}),
    ("host_new_game", {"scenario": "s4_zufall", "world_mode": "fixed", "level": "x"}),
    ("host_new_game", {"scenario": "s4_zufall", "world_mode": "fixed", "difficulty": {}}),
    ("host_new_game", {"scenario": "s4_zufall", "world_mode": "fixed",
                        "difficulty": {**config.DEFAULT_DIFFICULTY, "quiet_mult": 999.0}}),
    ("host_new_game", {"scenario": "s4_zufall", "world_mode": "fixed", "seed": 0}),
    ("host_new_game", {"scenario": "s4_zufall", "world_mode": "fixed", "seed": True}),
    ("host_new_game", {"scenario": "s4_zufall", "world_mode": "fixed",
                        "seed": 1_000_000_000}),
    ("host_new_game", {"scenario": ["s1_patrouille"], "world_mode": "fixed"}),
    ("host_new_game", {"scenario": "s4_zufall", "world_mode": "fixed", "extra": 1}),
])
def test_host_action_schemas_are_closed_and_strict(solo, action, params):
    assert send(solo, host_body(solo, action, params, "bad"))[0] == 400


@pytest.mark.parametrize("changes", [
    {"active_generation": 1}, {"station_generation": 99},
    {"station": "bridge"}, {"active_generation": True},
])
def test_host_commands_bind_to_the_host_generation_not_a_station(solo, changes):
    status = send(solo, host_body(solo, "host_save", {"slot": 1}, "x", **changes))[0]
    assert status in (400, 403, 409)
    solo.bridge.pump(solo.game, solo.server, now=time.monotonic())
    assert not (solo.tmp / "slot1.json").exists()


def test_host_save_and_load_round_trip_through_a_temporary_slot(solo):
    assert host(solo, "host_load", {"slot": 2}, "l0")["reasoncode"] == "no_save"
    assert host(solo, "host_save", {"slot": 2}, "s1")["reasoncode"] == "ok"
    assert (solo.tmp / "slot2.json").is_file()
    slots = {row["slot"]: row for row in host_view(solo)["slots"]}
    assert slots[2]["saved"] is True and isinstance(slots[2]["modified"], int)
    assert slots[1]["saved"] is False

    solo.game.sim_t += 100.0
    generation = session_of(solo)["stations"]["sonar"]["station_generation"]
    assert host(solo, "host_load", {"slot": 2}, "l1")["reasoncode"] == "ok"
    assert solo.game.sim_t < 100.0
    solo.bridge.pump(solo.game, solo.server, now=time.monotonic())  # rebase frame
    # The browser is still paired, under fresh generations, with the result readable.
    after = session_of(solo)
    assert after["stations"]["sonar"]["station_generation"] > generation
    assert all(after["stations"][station]["status"] == "mine" for station in STATIONS)


def test_a_corrupt_slot_fails_the_load_and_leaves_the_live_game_unchanged(solo):
    (solo.tmp / "slot3.json").write_text("{not json", encoding="utf-8")
    world, sim = id(solo.game.world), solo.game.sim_t
    assert host(solo, "host_load", {"slot": 3}, "l1")["reasoncode"] == "no_save"
    assert id(solo.game.world) == world and solo.game.sim_t == sim
    assert session_of(solo)["host"] == {"generation": 1}  # no rebase happened


def test_host_new_game_replaces_the_world_and_keeps_the_browser_paired(solo):
    old_world = id(solo.game.world)
    difficulty = {**config.DEFAULT_DIFFICULTY, "quiet_mult": 0.8}
    result = host(solo, "host_new_game", {
        "scenario": "s4_zufall", "world_mode": "procedural",
        "difficulty": difficulty, "seed": 4242}, "n1")
    assert result["reasoncode"] == "ok"
    assert id(solo.game.world) != old_world
    assert (solo.game.seed, solo.game.scenario_key, solo.game.world_mode,
            solo.game.difficulty) == (4242, "s4_zufall", "procedural", difficulty)
    solo.bridge.pump(solo.game, solo.server, now=time.monotonic())
    assert session_of(solo)["host"] == {"generation": 2}
    assert host_view(solo)["scenario"] == "s4_zufall"


def test_fixed_scenarios_ignore_a_requested_difficulty_and_random_seed_is_drawn(solo):
    difficulty = {**config.DEFAULT_DIFFICULTY, "quiet_mult": 0.5}
    assert host(solo, "host_new_game", {
        "scenario": "s1_patrouille", "world_mode": "procedural",
        "difficulty": difficulty}, "n1")["reasoncode"] == "ok"
    # The scenario fixes its own difficulty; the requested one is not applied.
    assert solo.game.difficulty == {**config.DEFAULT_DIFFICULTY,
                                    **config.SCENARIOS["s1_patrouille"]["difficulty"]}
    assert 1 <= solo.game.seed < 1_000_000_000


def test_commands_after_a_world_replacing_command_fail_closed_in_the_same_frame(solo):
    replace = host_body(solo, "host_new_game", {
        "scenario": "s1_patrouille", "world_mode": "procedural", "seed": 7}, "n1")
    assert send(solo, replace)[0] == 202
    late = host_body(solo, "host_save", {"slot": 1}, "late")
    late["seq"] = replace["seq"] + 1
    assert send(solo, late)[0] == 202
    solo.bridge.pump(solo.game, solo.server, now=time.monotonic())
    rows = request(solo.server, "/api/v2/results", cookie=solo.cookie)[2]["results"]
    assert [(row["id"], row["reasoncode"]) for row in rows] == [
        ("n1", "ok"), ("late", "phase_blocked")]
    assert not (solo.tmp / "slot1.json").exists()


def test_host_commands_run_before_station_commands_in_a_frame(solo):
    session = session_of(solo)
    course = {"protocol": 2, "id": "c", "seq": session["next_command_seq"],
              "station": "bridge",
              "station_generation": session["stations"]["bridge"]["station_generation"],
              "active_generation": session["active_generation"],
              "world_session": solo.bridge.status["session"],
              "world_epoch": solo.bridge.status["epoch"],
              "resource_revision": solo.bridge.status["revision"],
              "action": "bridge_set_course", "params": {"course": 45.0}}
    assert send(solo, course)[0] == 202
    save = host_body(solo, "host_save", {"slot": 1}, "p")
    assert send(solo, save)[0] == 202
    order = [(envelope.role, envelope.command_id)
             for envelope in solo.server.drain_commands_v2()]
    assert order == [("host", "p"), ("bridge", "c")]


def test_menu_allows_starting_a_game_and_host_overlays_block_nothing(solo):
    solo.game.main_menu = True
    solo.bridge.pump(solo.game, solo.server, now=time.monotonic() + 1)
    assert host_view(solo)["phase"] == "menu"
    assert host(solo, "host_save", {"slot": 1}, "p")["reasoncode"] == "phase_blocked"
    assert host(solo, "host_new_game", {
        "scenario": "s1_patrouille", "world_mode": "procedural", "seed": 9},
        "n")["reasoncode"] == "ok"
    assert solo.game.main_menu is False and solo.game.in_menu is False

    solo.bridge.pump(solo.game, solo.server, now=time.monotonic() + 2)
    solo.game.help_open = True  # a host-side overlay owns local input only
    solo.bridge.pump(solo.game, solo.server, now=time.monotonic() + 3)
    assert host_view(solo)["phase"] == "live"
    assert host(solo, "host_save", {"slot": 1}, "save")["reasoncode"] == "ok"
    assert host(solo, "host_load", {"slot": 1}, "load")["reasoncode"] == "ok"


def test_revoking_the_solo_session_removes_the_host_surface_and_queued_commands(solo):
    queued = host_body(solo, "host_save", {"slot": 1}, "q")
    assert send(solo, queued)[0] == 202
    solo.server.revoke_all()
    rows = request(solo.server, "/api/v2/results", cookie=solo.cookie)[2]["results"]
    assert [(row["id"], row["reasoncode"]) for row in rows] == [("q", "role_revoked")]
    assert session_of(solo)["host"] is None
    assert request(solo.server, "/api/v2/host", cookie=solo.cookie)[0] == 403
    assert send(solo, dict(queued, id="after", seq=queued["seq"] + 1))[0] == 403


def test_a_replayed_host_command_id_is_applied_once(solo):
    body = host_body(solo, "host_instructor_environment",
                     {"sea_state": 5, "event": None}, "dup")
    assert send(solo, body)[0] == 202
    solo.bridge.pump(solo.game, solo.server, now=time.monotonic())
    assert solo.game.world.sea_state == 5
    solo.game.world.sea_state = 2
    status, _, replay = send(solo, body)
    assert (status, replay["status"]) == (200, "applied")
    solo.bridge.pump(solo.game, solo.server, now=time.monotonic())
    assert solo.game.world.sea_state == 2
    assert send(solo, dict(body, action="host_save", params={"slot": 1}))[0] == 409
