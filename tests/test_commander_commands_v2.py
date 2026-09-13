"""Deterministic protocol-v2 command gateway contracts."""

from contextlib import closing
from dataclasses import replace
import http.client
import json
import random
import threading
import time

import pytest

from src.commander.bridge import CommanderBridge
from src.commander.server import (CommanderServer, STATIONS, V2_ACTION_REGISTRY,
                                  V2CommandEnvelope)
from src.core import config
from src.core.game import Game
from src.enemies.surface import SurfaceShip
from src.sonar.sonar import Contact


@pytest.fixture
def server():
    instance = CommanderServer()
    instance.start("127.0.0.1", 0)
    try:
        yield instance
    finally:
        instance.stop()


def request(server, path, method="GET", body=None, cookie=None, csrf=None,
            origin=True):
    host, port = server.address
    headers = {}
    if method == "POST":
        if origin:
            headers["Origin"] = f"http://{host}:{port}"
        headers["Content-Type"] = "application/json"
    if cookie:
        headers["Cookie"] = cookie
    if csrf:
        headers["X-U-Jagd-CSRF"] = csrf
    payload = None if body is None else json.dumps(body)
    with closing(http.client.HTTPConnection(host, port, timeout=3)) as connection:
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        data = json.loads(response.read())
        return response.status, dict(response.getheaders()), data


def pair(server, name, station):
    status, headers, session = request(server, "/api/v2/pair", "POST", {
        "code": server.pairing_code, "name": name})
    assert status == 200
    cookie = headers["Set-Cookie"].split(";", 1)[0]
    assert server.grant_station(session["client_id"], station)
    assert server.set_client_grant(session["client_id"], "command", True)
    assigned = request(server, "/api/v2/session", cookie=cookie)[2]
    return cookie, assigned


def command(session, *, command_id="one", seq=0, world_session="world",
            world_epoch=3, resource_revision=5, **changes):
    body = {
        "protocol": 2,
        "id": command_id,
        "seq": seq,
        "station": session["station"],
        "station_generation": session["station_generation"],
        "active_generation": session["active_generation"],
        "world_session": world_session,
        "world_epoch": world_epoch,
        "resource_revision": resource_revision,
        "action": "acknowledge",
        "params": {},
    }
    body.update(changes)
    return body


def bridge_command(session, action, value, **changes):
    field = "course" if action == "bridge_set_course" else "speed_kn"
    return command(session, action=action, params={field: value}, **changes)


def station_command(session, action, params, bridge, **changes):
    status = bridge.status
    return command(session, action=action, params=params,
                   world_session=status["session"], world_epoch=status["epoch"],
                   resource_revision=status["revision"], **changes)


def post(server, cookie, session, body):
    return request(server, "/api/v2/commands", "POST", body, cookie,
                   session["csrf"])


def apply_all(server, *, now=None, phase="live", world_session="world",
              world_epoch=3, resource_revision=5, seen=None):
    seen = [] if seen is None else seen
    for envelope in server.drain_commands_v2():
        assert server.apply_command_v2(
            envelope, now=time.monotonic() if now is None else now, phase=phase,
            world_session=world_session, world_epoch=world_epoch,
            resource_revision=resource_revision,
            apply=lambda action, params, envelope=envelope: (
                seen.append((envelope.role, envelope.client_ordinal,
                             envelope.command_id, envelope.seq)) or
                (action == "acknowledge" and params == {})))
    return seen


def results(server, cookie):
    status, _, body = request(server, "/api/v2/results", cookie=cookie)
    assert status == 200 and body["protocol"] == 2
    return body["results"]


def test_endpoint_requires_cookie_origin_csrf_and_exact_closed_schema(server):
    cookie, session = pair(server, "Bridge", "bridge")
    body = command(session)
    assert request(server, "/api/v2/commands", "POST", body, origin=False)[0] == 403
    assert request(server, "/api/v2/commands", "POST", body)[0] == 401
    assert request(server, "/api/v2/commands", "POST", body, cookie)[0] == 403
    assert request(server, "/api/v2/commands", "POST", body, cookie, "bad")[0] == 403
    for invalid in (
        dict(body, protocol=1), dict(body, action="set_course"),
        dict(body, id=""), dict(body, id="x" * 65), dict(body, seq=True),
        dict(body, seq=2**53 - 1), dict(body, seq=2**53), dict(body, station="sonar"),
        {key: value for key, value in body.items() if key != "active_generation"},
        dict(body, active_generation=True),
        dict(body, params={"extra": 1}), dict(body, extra=True),
    ):
        assert post(server, cookie, session, invalid)[0] in (400, 403)
    assert post(server, cookie, session, body)[0] == 202


@pytest.mark.parametrize(("action", "value"), [
    ("bridge_set_course", 0), ("bridge_set_course", 359.999),
    ("bridge_set_speed", 0), ("bridge_set_speed", 25),
])
def test_bridge_action_exact_schemas_accept_bounds(server, action, value):
    cookie, session = pair(server, "Bridge bounds", "bridge")
    assert post(server, cookie, session, bridge_command(session, action, value))[0] == 202


@pytest.mark.parametrize(("action", "params"), [
    ("bridge_set_course", {}), ("bridge_set_course", {"course": 360}),
    ("bridge_set_course", {"course": float("inf")}),
    ("bridge_set_course", {"course": 10**1000}),
    ("bridge_set_course", {"course": 20, "extra": 1}),
    ("bridge_set_speed", {"speed_kn": -1}), ("bridge_set_speed", {"speed_kn": 25.01}),
    ("bridge_set_speed", {"speed_kn": float("nan")}),
])
def test_bridge_action_schemas_reject_wrong_params_and_nonfinite(server, action, params):
    cookie, session = pair(server, "Bridge invalid", "bridge")
    assert post(server, cookie, session, command(
        session, action=action, params=params))[0] == 400


def test_bridge_actions_require_bridge_role_but_not_direct_fire(server):
    cookie, session = pair(server, "Sonar", "sonar")
    body = bridge_command(session, "bridge_set_course", 90, station="bridge")
    assert post(server, cookie, session, body)[0] == 403
    bridge_cookie, bridge_session = pair(server, "Helm", "bridge")
    assert bridge_session["grants"]["direct_fire"] is False
    assert post(server, bridge_cookie, bridge_session,
                bridge_command(bridge_session, "bridge_set_course", 90))[0] == 202


def test_detached_envelope_and_deterministic_station_client_fifo_order(server):
    clients = [pair(server, name, station) for name, station in (
        ("Sonar first", "sonar"), ("Bridge first", "bridge"),
        ("Bridge second", "bridge"))]
    # The second bridge grant revoked the first; assign it another canonical role.
    first_bridge = clients[1][1]
    assert server.grant_station(first_bridge["client_id"], "damage")
    assert server.set_client_grant(first_bridge["client_id"], "command", True)
    clients[1] = (clients[1][0], request(
        server, "/api/v2/session", cookie=clients[1][0])[2])
    for index in (2, 0, 1):
        cookie, session = clients[index]
        for seq in (10, 11):
            assert post(server, cookie, session, command(
                session, command_id=f"{index}-{seq}", seq=seq))[0] == 202
    for index in (1, 2, 0, 2):
        assert results(server, clients[index][0]) == []
    envelopes = server.drain_commands_v2()
    assert all(type(item) is V2CommandEnvelope and type(item.body_bytes) is bytes
               for item in envelopes)
    assert all(item.active_generation >= 1 for item in envelopes)
    assert [(item.role, item.client_ordinal, item.seq) for item in envelopes] == [
        ("bridge", 2, 10), ("bridge", 2, 11),
        ("sonar", 0, 10), ("sonar", 0, 11),
        ("damage", 1, 10), ("damage", 1, 11),
    ]
    detached = envelopes[0].body()
    detached["params"]["changed"] = True
    assert envelopes[0].body()["params"] == {}


def test_exactly_once_duplicate_conflict_sequence_and_history_bound(server):
    cookie, session = pair(server, "Operator", "opz")
    body = command(session)
    assert post(server, cookie, session, body)[0] == 202
    assert request(server, "/api/v2/session", cookie=cookie)[2]["next_command_seq"] == 1
    assert post(server, cookie, session, body)[2] == {"status": "pending", "id": "one"}
    assert post(server, cookie, session, dict(body, world_epoch=4))[2] == {
        "error": "duplicate_id_conflict"}
    assert apply_all(server) == [("opz", session["ordinal"], "one", 0)]
    assert post(server, cookie, session, body)[2]["status"] == "applied"
    assert request(server, "/api/v2/session", cookie=cookie)[2]["next_command_seq"] == 1
    assert server.drain_commands_v2() == []
    assert post(server, cookie, session, command(
        session, command_id="old", seq=0))[2] == {"error": "out_of_order"}

    for seq in range(1, 70):
        body = command(session, command_id=f"id-{seq}", seq=seq)
        assert post(server, cookie, session, body)[0] == 202
        apply_all(server)
    assert len(results(server, cookie)) == 64
    with server._lock:
        stored = next(iter(server._sessions_v2.values()))
        assert len(stored["command_ids"]) == 64


def test_per_client_global_bounds_and_pressure_isolation(server):
    clients = [pair(server, f"Client {index}", station)
               for index, station in enumerate(STATIONS)]
    first_cookie, first = clients[0]
    for seq in range(8):
        assert post(server, first_cookie, first, command(
            first, command_id=f"first-{seq}", seq=seq))[0] == 202
    assert post(server, first_cookie, first, command(
        first, command_id="first-full", seq=8))[2] == {"error": "client_queue_full"}
    detached = server.drain_commands_v2()
    assert post(server, first_cookie, first, command(
        first, command_id="first-full", seq=8))[2] == {"error": "client_queue_full"}
    for envelope in detached:
        assert server.apply_command_v2(
            envelope, now=envelope.received_at, phase="live", world_session="world",
            world_epoch=3, resource_revision=5, apply=lambda *_: True)
    assert post(server, first_cookie, first, command(
        first, command_id="first-full", seq=8))[0] == 202
    second_cookie, second = clients[1]
    assert post(server, second_cookie, second, command(second))[0] == 202
    server.invalidate_v2_commands()

    for client_index, (cookie, session) in enumerate(clients[:8]):
        start = 20 + client_index * 10
        for offset in range(8):
            assert post(server, cookie, session, command(
                session, command_id=f"global-{client_index}-{offset}",
                seq=start + offset))[0] == 202
    ninth_cookie, ninth = clients[8]
    assert post(server, ninth_cookie, ninth, command(
        ninth, command_id="global-full", seq=100))[2] == {"error": "queue_full"}


@pytest.mark.parametrize(("changes", "reason"), [
    ({"world_session": "other"}, "stale_world_session"),
    ({"world_epoch": 4}, "stale_world_epoch"),
    ({"resource_revision": 6}, "revision_conflict"),
])
def test_main_thread_rejects_stale_world_context(server, changes, reason):
    cookie, session = pair(server, reason, "radio")
    assert post(server, cookie, session, command(session, **changes))[0] == 202
    apply_all(server)
    assert results(server, cookie)[-1]["reasoncode"] == reason


def test_main_thread_rechecks_age_phase_generation_and_grant(server):
    cookie, session = pair(server, "Checks", "engine")
    cases = []
    for seq in range(5):
        assert post(server, cookie, session, command(
            session, command_id=str(seq), seq=seq))[0] == 202
        cases.append(server.drain_commands_v2()[0])
    assert server.apply_command_v2(cases[0], now=cases[0].received_at + 2.001,
        phase="live", world_session="world", world_epoch=3, resource_revision=5,
        apply=lambda *_: True)
    assert server.apply_command_v2(cases[1], now=cases[1].received_at,
        phase="paused", world_session="world", world_epoch=3, resource_revision=5,
        apply=lambda *_: True)
    changed_generation = replace(cases[2], lease_generation=cases[2].lease_generation + 1)
    assert server.apply_command_v2(changed_generation, now=cases[2].received_at,
        phase="live", world_session="world", world_epoch=3, resource_revision=5,
        apply=lambda *_: True)
    changed_active = replace(cases[3], active_generation=cases[3].active_generation + 1)
    assert server.apply_command_v2(changed_active, now=cases[3].received_at,
        phase="live", world_session="world", world_epoch=3, resource_revision=5,
        apply=lambda *_: True)
    assert server.set_client_grant(session["client_id"], "command", False)
    assert server.apply_command_v2(cases[4], now=cases[4].received_at,
        phase="live", world_session="world", world_epoch=3, resource_revision=5,
        apply=lambda *_: True)
    assert [row["reasoncode"] for row in results(server, cookie)] == [
        "expired", "phase_blocked", "stale_generation",
        "stale_active_generation", "grant_revoked"]


def test_main_thread_rechecks_detached_session_identity(server):
    cookie, session = pair(server, "Identity", "eloka")
    assert post(server, cookie, session, command(session))[0] == 202
    envelope = server.drain_commands_v2()[0]
    called = []
    assert not server.apply_command_v2(
        replace(envelope, session_digest=b"x" * 32), now=envelope.received_at,
        phase="live", world_session="world", world_epoch=3, resource_revision=5,
        apply=lambda *_: called.append(True) or True)
    assert called == [] and results(server, cookie) == []
    assert server.apply_command_v2(
        envelope, now=envelope.received_at, phase="live", world_session="world",
        world_epoch=3, resource_revision=5, apply=lambda *_: True)


def test_results_are_isolated_and_invalidation_rejects_only_unsafe_queue(server):
    first_cookie, first = pair(server, "First", "damage")
    second_cookie, second = pair(server, "Second", "helicopter")
    assert post(server, first_cookie, first, command(first))[0] == 202
    assert post(server, second_cookie, second, command(second))[0] == 202
    server.invalidate_v2_commands("context_invalidated")
    assert results(server, first_cookie) == [{
        "id": "one", "seq": 0, "status": "rejected",
        "reasoncode": "context_invalidated"}]
    assert results(server, second_cookie) == [{
        "id": "one", "seq": 0, "status": "rejected",
        "reasoncode": "context_invalidated"}]
    assert server.drain_commands_v2() == []


def test_role_release_rejects_queue_and_clears_authority(server):
    cookie, session = pair(server, "Release", "weapons")
    original = command(session)
    assert post(server, cookie, session, original)[0] == 202
    status, _, released = request(server, "/api/v2/stations/release", "POST", {
        "station": session["station"],
        "station_generation": session["station_generation"],
        "active_generation": session["active_generation"],
    }, cookie, session["csrf"])
    assert status == 200 and released["station"] is None
    assert results(server, cookie)[-1]["reasoncode"] == "role_revoked"
    status, _, replay = post(server, cookie, session, original)
    assert status == 200 and replay["reasoncode"] == "role_revoked"
    with server._lock:
        stored = next(iter(server._sessions_v2.values()))
        assert stored["held_commands"] == {} and not stored["command_queue"]


def test_active_switch_retains_old_queue_but_inactive_revoke_is_station_scoped(server):
    cookie, bridge = pair(server, "Multi command", "bridge")
    client_id = bridge["client_id"]
    assert server.grant_station(client_id, "sonar")
    assert server.set_client_grant(client_id, "sonar", "command", True)
    assert post(server, cookie, bridge, command(bridge, command_id="bridge", seq=0))[0] == 202

    refreshed = request(server, "/api/v2/session", cookie=cookie)[2]
    sonar_generation = refreshed["stations"]["sonar"]["station_generation"]
    assert server.activate_station(client_id, "sonar", sonar_generation)
    assert results(server, cookie) == []
    sonar = request(server, "/api/v2/session", cookie=cookie)[2]
    assert sonar["active_station"] == "sonar" and sonar["active_generation"] == 2
    assert post(server, cookie, sonar, command(
        sonar, command_id="sonar", seq=1, station="sonar",
        station_generation=sonar_generation))[0] == 202
    assert server.revoke_station("bridge")
    assert [item.command_id for item in server.drain_commands_v2()] == ["sonar"]


def test_bridge_applies_acknowledge_on_main_thread_without_rng_or_save_mutation(server):
    game = Game(seed=411, start_menu=False, audio_enabled=False, language="en")
    bridge = CommanderBridge()
    try:
        now = time.monotonic()
        bridge.pump(game, server, now=now)
        cookie, session = pair(server, "Bridge pump", "bridge")
        status = bridge.status
        body = command(session, command_id="remote-command-persistence-sentinel",
                       world_session=status["session"],
                       world_epoch=status["epoch"], resource_revision=status["revision"])
        before, rng = game.save_state(), random.getstate()
        assert post(server, cookie, session, body)[0] == 202
        assert game.save_state() == before
        bridge.pump(game, server, now=time.monotonic())
        assert game.save_state() == before and random.getstate() == rng
        assert results(server, cookie)[-1]["reasoncode"] == "ok"
        encoded = json.dumps(game.save_state())
        assert "command_queue" not in encoded
        assert "remote-command-persistence-sentinel" not in encoded
    finally:
        game.audio.shutdown()


def test_bridge_orders_share_local_model_without_changing_local_ui_state(server):
    game = Game(seed=412, start_menu=False, audio_enabled=False, language="en")
    bridge = CommanderBridge()
    try:
        bridge.pump(game, server, now=time.monotonic())
        cookie, session = pair(server, "Remote helm", "bridge")
        bridge.pump(game, server, now=time.monotonic())
        status = bridge.status
        game.station = game.station.__class__.SONAR
        game.selected_contact_id = 77
        game.held.add(12345)
        before_ui = (game.station, game.selected_contact_id, set(game.held),
                     game.input_mode, game.input_buffer)
        for seq, (action, value) in enumerate((
                ("bridge_set_course", 123.5), ("bridge_set_speed", 7.25))):
            assert post(server, cookie, session, bridge_command(session, action, value,
                command_id=f"order-{seq}", seq=seq, world_session=status["session"],
                world_epoch=status["epoch"], resource_revision=status["revision"]))[0] == 202
            bridge.pump(game, server, now=time.monotonic())
        assert game.ship.target_course == 123.5
        assert game.ship.target_speed == 7.25 and not game.ship.astern
        assert game.ship.order_idx == min(range(len(config.TELEGRAPH_ORDERS)),
            key=lambda index: abs(config.TELEGRAPH_ORDERS[index][1] - 7.25))
        assert (game.station, game.selected_contact_id, set(game.held),
                game.input_mode, game.input_buffer) == before_ui
        assert [row["reasoncode"] for row in results(server, cookie)[-2:]] == ["ok", "ok"]
    finally:
        game.audio.shutdown()


def test_damaged_bridge_rejects_course_without_mutation_but_preserves_speed_behavior(server):
    game = Game(seed=413, start_menu=False, audio_enabled=False, language="en")
    bridge = CommanderBridge()
    try:
        bridge.pump(game, server, now=time.monotonic())
        cookie, session = pair(server, "Damaged helm", "bridge")
        bridge.pump(game, server, now=time.monotonic())
        status = bridge.status
        game.damage.compartments["bridge"].state = "ZERSTOERT"
        original_course = game.ship.target_course
        for seq, (action, value) in enumerate((
                ("bridge_set_course", 240), ("bridge_set_speed", 4))):
            assert post(server, cookie, session, bridge_command(session, action, value,
                command_id=f"damage-{seq}", seq=seq, world_session=status["session"],
                world_epoch=status["epoch"], resource_revision=status["revision"]))[0] == 202
            bridge.pump(game, server, now=time.monotonic())
        assert game.ship.target_course == original_course
        assert game.ship.target_speed == 4
        assert [row["reasoncode"] for row in results(server, cookie)[-2:]] == [
            "bridge_down", "ok"]
    finally:
        game.audio.shutdown()


def test_bridge_and_action_callback_never_run_on_transport_thread(server):
    cookie, session = pair(server, "Thread", "sonar")
    assert post(server, cookie, session, command(session))[0] == 202
    envelope = server.drain_commands_v2()[0]
    called = []

    errors = []

    def worker():
        _capture_error(errors, server.apply_command_v2, envelope,
            now=time.monotonic(), phase="live", world_session="world",
            world_epoch=3, resource_revision=5,
            apply=lambda *_: called.append(threading.current_thread().name) or True)

    thread = threading.Thread(target=worker, name="deliberate-non-main")
    thread.start()
    thread.join()
    assert called == []
    assert len(errors) == 1 and "main thread" in str(errors[0])
    game = Game(seed=12, audio_enabled=False)
    try:
        bridge = CommanderBridge()
        errors = []
        thread = threading.Thread(target=lambda: _capture_error(
            errors, bridge.pump, game, server), name="transport-like")
        thread.start()
        thread.join()
        assert len(errors) == 1 and "main thread" in str(errors[0])
    finally:
        game.audio.shutdown()


@pytest.mark.parametrize(("station", "action", "params"), [
    ("sonar", "sonar_classify", {"ref": "opaque", "classification": None}),
    ("sonar", "sonar_classify", {"ref": "opaque", "classification": "U_BOOT"}),
    ("opz", "opz_classify", {"ref": "opaque", "classification": "KAMPFSCHIFF"}),
    ("opz", "opz_affiliate", {"ref": "opaque", "affiliation": "HOSTILE"}),
    ("opz", "opz_create_fusion", {"refs": ["one", "two"]}),
    ("opz", "opz_dissolve_fusion", {"ref": "fusion"}),
    ("opz", "opz_set_radar", {"domain": "air", "enabled": False}),
    ("opz", "opz_set_range", {"range_nm": config.RADAR_RANGE_SCALES_NM[-1]}),
])
def test_sonar_and_opz_action_schemas_are_exact(server, station, action, params):
    cookie, session = pair(server, action, station)
    valid = command(session, action=action, params=params)
    assert post(server, cookie, session, valid)[0] == 202
    server.invalidate_v2_commands()
    invalid = dict(params, unexpected=True)
    assert post(server, cookie, session, command(
        session, command_id="invalid", seq=1, action=action, params=invalid))[0] == 400


def test_fusion_schema_rejects_duplicate_refs_and_action_role_mismatch(server):
    cookie, session = pair(server, "OPZ schema", "opz")
    duplicate = command(session, action="opz_create_fusion",
                        params={"refs": ["same", "same"]})
    assert post(server, cookie, session, duplicate)[0] == 400
    wrong_role = command(session, station="sonar", action="sonar_classify",
                         params={"ref": "opaque", "classification": None})
    assert post(server, cookie, session, wrong_role)[0] == 403


@pytest.mark.parametrize(("station", "action", "params"), [
    ("engine", "engine_set_telegraph", {"order": "ASTERN"}),
    ("engine", "engine_set_speed", {"speed_kn": 12.5}),
    ("engine", "engine_set_quiet_mode", {"enabled": True}),
    ("damage", "damage_assign_team", {"team": 1, "compartment": "engine"}),
    ("damage", "damage_unassign_team", {"team": 3, "compartment": "engine"}),
    ("radio", "radio_capture_hfdf", {"ref": "opaque"}),
    ("eloka", "eloka_annotate", {"ref": "opaque", "candidate_ref": "choice"}),
    ("eloka", "eloka_clear_annotation", {"ref": "opaque"}),
    ("sonar", "sonar_set_listen_bearing", {"bearing": 359.5}),
    ("sonar", "sonar_set_focus", {"ref": "opaque"}),
    ("sonar", "sonar_clear_focus", {}),
    ("sonar", "sonar_set_array_mode", {"mode": "TOWED"}),
    ("sonar", "sonar_set_tas", {"deployed": True}),
    ("sonar", "sonar_set_tow_depth", {"depth_m": 100}),
    ("sonar", "sonar_measure_bt", {}),
    ("sonar", "sonar_active_ping", {}),
    ("sonar", "sonar_set_tma_enabled", {"enabled": False}),
    ("sonar", "sonar_set_gain", {"gain_db": -12}),
    ("sonar", "sonar_set_band_preset", {"preset": "SHAFT"}),
    ("sonar", "sonar_set_notch", {"enabled": True}),
    ("sonar", "sonar_set_peak_hold", {"enabled": True}),
    ("sonar", "sonar_set_harmonic", {"frequency_hz": None}),
    ("sonar", "sonar_designate_target", {"ref": "opaque"}),
    ("opz", "opz_designate_target", {"ref": "opaque"}),
    ("helicopter", "helicopter_launch", {}),
    ("helicopter", "helicopter_return", {}),
    ("helicopter", "helicopter_set_waypoint", {"x": 250.0, "y": 251.0}),
    ("helicopter", "helicopter_deploy_buoy", {}),
])
def test_remaining_nonlethal_action_schemas_are_exact(server, station, action, params):
    cookie, session = pair(server, action, station)
    assert post(server, cookie, session, command(
        session, action=action, params=params))[0] == 202
    server.invalidate_v2_commands()
    assert post(server, cookie, session, command(
        session, command_id="extra", seq=1, action=action,
        params=dict(params, extra=True)))[0] == 400


@pytest.mark.parametrize(("action", "params"), [
    ("engine_set_telegraph", {"order": "AHEAD"}),
    ("engine_set_quiet_mode", {"enabled": 1}),
    ("damage_assign_team", {"team": True, "compartment": "engine"}),
    ("damage_assign_team", {"team": 1, "compartment": "unknown"}),
    ("sonar_set_listen_bearing", {"bearing": 360}),
    ("sonar_set_tow_depth", {"depth_m": float("inf")}),
    ("sonar_set_tow_depth", {"depth_m": 10**1000}),
    ("sonar_set_gain", {"gain_db": 24.01}),
    ("sonar_set_band_preset", {"preset": "CUSTOM"}),
    ("sonar_set_harmonic", {"frequency_hz": 0}),
    ("helicopter_set_waypoint", {"x": -1, "y": 2}),
    ("helicopter_set_waypoint", {"x": 10**1000, "y": 2}),
])
def test_remaining_nonlethal_schemas_reject_invalid_values(server, action, params):
    station = next(iter(V2_ACTION_REGISTRY[action].stations))
    cookie, session = pair(server, "invalid", station)
    assert post(server, cookie, session, command(
        session, action=action, params=params))[0] == 400


@pytest.mark.parametrize(("station", "action", "params"), [
    ("engine", "engine_set_telegraph", {"order": "STOP"}),
    ("damage", "damage_unassign_team", {"team": 1, "compartment": "engine"}),
    ("radio", "radio_capture_hfdf", {"ref": "opaque"}),
    ("eloka", "eloka_clear_annotation", {"ref": "opaque"}),
    ("sonar", "sonar_set_gain", {"gain_db": 0}),
    ("opz", "opz_designate_target", {"ref": "opaque"}),
    ("helicopter", "helicopter_return", {}),
])
def test_remaining_actions_are_phase_blocked_before_callback(
        server, station, action, params):
    cookie, session = pair(server, "blocked", station)
    assert post(server, cookie, session, command(
        session, action=action, params=params))[0] == 202
    envelope = server.drain_commands_v2()[0]
    called = []
    assert server.apply_command_v2(
        envelope, now=envelope.received_at, phase="paused", world_session="world",
        world_epoch=3, resource_revision=5,
        apply=lambda *_: called.append(True) or True)
    assert called == []
    assert results(server, cookie)[-1]["reasoncode"] == "phase_blocked"


def test_remaining_action_rejects_session_with_wrong_role(server):
    cookie, session = pair(server, "wrong role", "bridge")
    body = command(session, station="engine", action="engine_set_telegraph",
                   params={"order": "STOP"})
    assert post(server, cookie, session, body)[0] == 403


def test_v2_registry_exposes_no_host_audio_control():
    assert not any(token in action for action in V2_ACTION_REGISTRY
                   for token in ("audio", "volume", "audition"))


@pytest.mark.parametrize(("station", "action", "params"), [
    ("weapons", "weapons_launch_torpedo", {"ref": "opaque", "depth_m": 10}),
    ("weapons", "helicopter_launch_torpedo", {"ref": "opaque", "depth_m": 300}),
    ("helicopter", "helicopter_launch_torpedo", {"ref": "opaque", "depth_m": 80}),
    ("weapons", "weapons_deploy_nixie", {}),
    ("opz", "opz_launch_essm", {"ref": "opaque"}),
    ("opz", "opz_launch_chaff", {"ref": "opaque"}),
])
def test_direct_fire_registry_schema_roles_and_grants(server, station, action, params):
    spec = V2_ACTION_REGISTRY[action]
    assert spec.direct_fire is True and station in spec.stations
    cookie, session = pair(server, action, station)
    assert server.set_client_grant(session["client_id"], "direct_fire", True)
    assert post(server, cookie, session, command(
        session, action=action, params=params))[0] == 202


@pytest.mark.parametrize("depth", [9.999, 300.001, True, float("nan"), float("inf")])
def test_direct_fire_torpedo_depth_schema_rejects_outside_exact_bounds(server, depth):
    cookie, session = pair(server, "depth", "weapons")
    assert post(server, cookie, session, command(
        session, action="weapons_launch_torpedo",
        params={"ref": "opaque", "depth_m": depth}))[0] == 400


def test_direct_fire_grant_is_limited_to_lethal_roles_and_revocation_filters_queue(server):
    bridge_cookie, bridge_session = pair(server, "no fire", "bridge")
    assert not server.set_client_grant(bridge_session["client_id"], "direct_fire", True)
    cookie, session = pair(server, "weapons", "weapons")
    assert server.set_client_grant(session["client_id"], "direct_fire", True)
    fire = command(session, command_id="fire", seq=0,
                   action="weapons_deploy_nixie", params={})
    safe = command(session, command_id="safe", seq=1)
    assert post(server, cookie, session, fire)[0] == 202
    assert post(server, cookie, session, safe)[0] == 202
    assert server.set_client_grant(session["client_id"], "direct_fire", False)
    assert results(server, cookie)[-1]["reasoncode"] == "direct_fire_unavailable"
    assert [item.command_id for item in server.drain_commands_v2()] == ["safe"]


def test_direct_fire_application_age_and_presence_boundaries_are_closed(server):
    cookie, session = pair(server, "boundaries", "opz")
    assert server.set_client_grant(session["client_id"], "direct_fire", True)
    envelopes = []
    for seq in range(3):
        body = command(session, command_id=f"fire-{seq}", seq=seq,
                       action="opz_launch_essm", params={"ref": "opaque"})
        assert post(server, cookie, session, body)[0] == 202
        envelopes.append(server.drain_commands_v2()[0])
    with server._lock:
        stored = next(item for item in server._sessions_v2.values()
                      if item["client_id"] == session["client_id"])
        stored["presence"] = envelopes[0].received_at - 1.0
    assert server.apply_command_v2(envelopes[0], now=envelopes[0].received_at + 1.0,
        phase="live", world_session="world", world_epoch=3, resource_revision=5,
        apply=lambda *_: True)
    with server._lock:
        stored["presence"] = envelopes[1].received_at - 1.0
    assert server.apply_command_v2(envelopes[1], now=envelopes[1].received_at + 1.000001,
        phase="live", world_session="world", world_epoch=3, resource_revision=5,
        apply=lambda *_: True)
    with server._lock:
        stored["presence"] = envelopes[2].received_at - 2.000001
    assert server.apply_command_v2(envelopes[2], now=envelopes[2].received_at,
        phase="live", world_session="world", world_epoch=3, resource_revision=5,
        apply=lambda *_: True)
    assert [row["reasoncode"] for row in results(server, cookie)[-3:]] == [
        "ok", "direct_fire_unavailable", "direct_fire_unavailable"]


def test_actual_game_sonar_release_opz_visibility_and_fusion(server):
    game = Game(seed=414, start_menu=False, audio_enabled=False, language="en")
    bridge = CommanderBridge()
    try:
        game.sonar.contacts.clear()
        for target_id, bearing in ((88001, 30.0), (88002, 55.0)):
            contact = Contact(target_id - 88000, target_id, "passiv", "sub")
            contact.update_passive(bearing, .8, .8, "hidden", game.sim_t)
            game.sonar.contacts[target_id] = contact
        bridge.pump(game, server, now=time.monotonic())
        sonar_cookie, sonar_session = pair(server, "Remote sonar", "sonar")
        bridge.pump(game, server, now=time.monotonic())
        sonar_state = request(server, "/api/v2/state", cookie=sonar_cookie)[2]
        refs = [row["ref"] for row in sonar_state["sonar"]["observations"]]
        for seq, ref in enumerate(refs):
            body = station_command(sonar_session, "sonar_classify",
                                   {"ref": ref, "classification": "U_BOOT"},
                                   bridge, command_id=f"classify-{seq}", seq=seq * 2)
            assert post(server, sonar_cookie, sonar_session, body)[0] == 202
            bridge.pump(game, server, now=time.monotonic())
            release = station_command(sonar_session, "sonar_set_release",
                                      {"ref": ref, "released": True}, bridge,
                                      command_id=f"release-{seq}", seq=seq * 2 + 1)
            assert post(server, sonar_cookie, sonar_session, release)[0] == 202
            bridge.pump(game, server, now=time.monotonic())
            sonar_state = request(server, "/api/v2/state", cookie=sonar_cookie)[2]
        assert all(contact.player_class == "U_BOOT"
                   for contact in game.sonar.contacts.values())

        opz_cookie, opz_session = pair(server, "Remote OPZ", "opz")
        bridge.pump(game, server, now=time.monotonic())
        picture = request(server, "/api/v2/state", cookie=opz_cookie)[2]["opz"]
        assert len(picture["observations"]) == 2
        source_owned = station_command(opz_session, "opz_classify", {
            "ref": picture["observations"][0]["ref"],
            "classification": "KAMPFSCHIFF"}, bridge,
            command_id="source-owned", seq=0)
        assert post(server, opz_cookie, opz_session, source_owned)[0] == 202
        bridge.pump(game, server, now=time.monotonic())
        assert results(server, opz_cookie)[-1]["reasoncode"] == "source_owned"
        fusion = station_command(opz_session, "opz_create_fusion",
            {"refs": [row["ref"] for row in picture["observations"]]}, bridge,
            command_id="fusion", seq=1)
        assert post(server, opz_cookie, opz_session, fusion)[0] == 202
        bridge.pump(game, server, now=time.monotonic())
        picture = request(server, "/api/v2/state", cookie=opz_cookie)[2]["opz"]
        assert len(picture["fusions"]) == 1
        assert set(picture["fusions"][0]["members"]) == {
            row["ref"] for row in picture["observations"]}
        designation = station_command(opz_session, "opz_designate_target", {
            "ref": picture["observations"][0]["ref"]}, bridge,
            command_id="designation", seq=2)
        assert post(server, opz_cookie, opz_session, designation)[0] == 202
        bridge.pump(game, server, now=time.monotonic())
        assert results(server, opz_cookie)[-1]["reasoncode"] == "ok"
        assert game.target in game.sonar.contacts.values()
        encoded = json.dumps(picture)
        assert "88001" not in encoded and "88002" not in encoded and "hidden" not in encoded
    finally:
        game.audio.shutdown()


def submit(game, bridge, server, cookie, session, action, params, seq):
    body = station_command(session, action, params, bridge,
                           command_id=f"{action}-{seq}", seq=seq)
    assert post(server, cookie, session, body)[0] == 202
    bridge.pump(game, server, now=time.monotonic())
    return results(server, cookie)[-1]


def test_engine_and_damage_actions_match_result_helpers_without_ui_cursor_mutation(server):
    game = Game(seed=415, start_menu=False, audio_enabled=False, language="en")
    bridge = CommanderBridge()
    try:
        bridge.pump(game, server, now=time.monotonic())
        engine_cookie, engine = pair(server, "Engineer", "engine")
        bridge.pump(game, server, now=time.monotonic())
        ui = (game.station, game.dmg_team, game.dmg_cursor, game.selected_contact)
        actions = [
            ("engine_set_telegraph", {"order": "ASTERN"}),
            ("engine_set_speed", {"speed_kn": 8.5}),
            ("engine_set_quiet_mode", {"enabled": True}),
        ]
        for seq, (action, params) in enumerate(actions):
            assert submit(game, bridge, server, engine_cookie, engine,
                          action, params, seq)["reasoncode"] == "ok"
        assert game.ship.telegraph == "HALF"
        assert game.ship.target_speed == 8.5 and game.ship.quiet_mode
        assert (game.station, game.dmg_team, game.dmg_cursor,
                game.selected_contact) == ui

        game.damage.compartments["engine"].state = "BESCHAEDIGT"
        damage_cookie, damage = pair(server, "Damage", "damage")
        bridge.pump(game, server, now=time.monotonic())
        assert submit(game, bridge, server, damage_cookie, damage,
                      "damage_assign_team", {"team": 2, "compartment": "engine"},
                      0)["reasoncode"] == "ok"
        assert game.damage.teams[2] == "engine"
        assert submit(game, bridge, server, damage_cookie, damage,
                      "damage_unassign_team", {"team": 2, "compartment": "engine"},
                      1)["reasoncode"] == "ok"
        assert game.damage.teams[2] is None

        game.damage.compartments["engine"].state = "ZERSTOERT"
        before = (game.ship.telegraph, game.ship.target_speed, game.ship.quiet_mode)
        assert submit(game, bridge, server, engine_cookie, engine,
                      "engine_set_quiet_mode", {"enabled": False},
                      3)["reasoncode"] == "engine_down"
        assert (game.ship.telegraph, game.ship.target_speed,
                game.ship.quiet_mode) == before
    finally:
        game.audio.shutdown()


def test_sonar_authoritative_controls_use_explicit_values_and_refs(server):
    from src.sonar.sonar import TowState

    game = Game(seed=416, start_menu=False, audio_enabled=False, language="en")
    bridge = CommanderBridge()
    try:
        game.sonar.contacts.clear()
        contact = Contact(1, 99101, "passiv", "sub")
        contact.update_passive(72.0, .8, .8, "hidden", game.sim_t)
        game.sonar.contacts[contact.target_id] = contact
        game.sonar.receiver.peaks = [(17.5, .8)]
        bridge.pump(game, server, now=time.monotonic())
        cookie, session = pair(server, "Sonar controls", "sonar")
        bridge.pump(game, server, now=time.monotonic())
        state = request(server, "/api/v2/state", cookie=cookie)[2]["sonar"]
        ref = state["observations"][0]["ref"]
        commands = [
            ("sonar_set_harmonic", {"frequency_hz": 17.5}),
            ("sonar_set_listen_bearing", {"bearing": 123.5}),
            ("sonar_set_focus", {"ref": ref}),
            ("sonar_clear_focus", {}),
            ("sonar_set_array_mode", {"mode": "TOWED"}),
            ("sonar_set_tas", {"deployed": True}),
            ("sonar_set_tma_enabled", {"enabled": False}),
            ("sonar_set_gain", {"gain_db": 9.0}),
            ("sonar_set_band_preset", {"preset": "SHAFT"}),
            ("sonar_set_notch", {"enabled": True}),
            ("sonar_set_peak_hold", {"enabled": True}),
            ("sonar_designate_target", {"ref": ref}),
        ]
        for seq, (action, params) in enumerate(commands):
            assert submit(game, bridge, server, cookie, session,
                          action, params, seq)["reasoncode"] == "ok"
        assert game.sonar.listen_bearing == 72.0
        assert not game.sonar.focus_locked and game.selected_contact is contact
        assert game.sonar_mode == "TOWED"
        assert game.sonar.tow_state == TowState.DEPLOYING
        assert not game.sonar.tma_enabled and game.sonar.gain_db == 9.0
        assert (game.sonar.band_low_hz, game.sonar.band_high_hz) == (8.0, 55.0)
        assert game.sonar.notch_enabled and game.sonar.peak_hold
        assert game.sonar_harmonic_hz == 17.5 and game.target is contact

        next_seq = len(commands)
        assert submit(game, bridge, server, cookie, session,
                      "sonar_active_ping", {}, next_seq)["reasoncode"] == "not_ready"
        assert game.sonar.ping_cooldown == 0
        assert submit(game, bridge, server, cookie, session,
                      "sonar_set_array_mode", {"mode": "BOW"},
                      next_seq + 1)["reasoncode"] == "ok"
        assert submit(game, bridge, server, cookie, session,
                      "sonar_active_ping", {}, next_seq + 2)["reasoncode"] == "ok"
        cooldown = game.sonar.ping_cooldown
        assert submit(game, bridge, server, cookie, session,
                      "sonar_active_ping", {}, next_seq + 3)["reasoncode"] == "not_ready"
        assert game.sonar.ping_cooldown == cooldown

        game.sonar.tow_state = TowState.STREAMED
        game.sonar.tow_payout = 1.0
        assert submit(game, bridge, server, cookie, session,
                      "sonar_set_tow_depth", {"depth_m": 80.0},
                      next_seq + 4)["reasoncode"] == "ok"
        assert game.sonar.towed_depth_target_m == 80.0
        game.damage.compartments["sonar"].state = "ZERSTOERT"
        assert submit(game, bridge, server, cookie, session,
                      "sonar_set_gain", {"gain_db": -3.0},
                      next_seq + 5)["reasoncode"] == "sonar_down"
        assert game.sonar.gain_db == 9.0
    finally:
        game.audio.shutdown()


def test_bt_duplicate_replay_does_not_draw_rng_or_mutate_again(server):
    game = Game(seed=417, start_menu=False, audio_enabled=False, language="en")
    bridge = CommanderBridge()
    try:
        bridge.pump(game, server, now=time.monotonic())
        cookie, session = pair(server, "BT", "sonar")
        bridge.pump(game, server, now=time.monotonic())
        body = station_command(session, "sonar_measure_bt", {}, bridge,
                               command_id="bt-once", seq=0)
        assert post(server, cookie, session, body)[0] == 202
        bridge.pump(game, server, now=time.monotonic())
        after = game.save_state()
        assert post(server, cookie, session, body)[0] == 200
        bridge.pump(game, server, now=time.monotonic())
        assert game.save_state() == after
    finally:
        game.audio.shutdown()


def test_helicopter_actions_validate_damage_state_and_explicit_waypoint(server):
    game = Game(seed=418, start_menu=False, audio_enabled=False, language="en")
    bridge = CommanderBridge()
    try:
        bridge.pump(game, server, now=time.monotonic())
        cookie, session = pair(server, "Air", "helicopter")
        bridge.pump(game, server, now=time.monotonic())
        game.damage.compartments["flightdeck"].state = "ZERSTOERT"
        assert submit(game, bridge, server, cookie, session,
                      "helicopter_launch", {}, 0)["reasoncode"] == "flightdeck_down"
        assert game.helo.state == "HANGAR"
        game.damage.compartments["flightdeck"].state = "OK"
        assert submit(game, bridge, server, cookie, session,
                      "helicopter_launch", {}, 1)["reasoncode"] == "ok"
        x = min(game.world.size_nm, game.ship.x + 3.0)
        y = min(game.world.size_nm, game.ship.y + 2.0)
        assert submit(game, bridge, server, cookie, session,
                      "helicopter_set_waypoint", {"x": x, "y": y},
                      2)["reasoncode"] == "ok"
        assert (game.helo.waypoint_x, game.helo.waypoint_y) == (x, y)
        assert submit(game, bridge, server, cookie, session,
                      "helicopter_deploy_buoy", {}, 3)["reasoncode"] == "ok"
        assert len(game.buoys) == 1 and game.helo.buoys_left == config.BUOY_COUNT - 1
        assert submit(game, bridge, server, cookie, session,
                      "helicopter_return", {}, 4)["reasoncode"] == "ok"
        assert game.helo.state == "ZURUECK"
    finally:
        game.audio.shutdown()


def test_radio_capture_uses_current_opaque_hfdf_ref(server):
    game = Game(seed=419, start_menu=False, audio_enabled=False, language="en")
    bridge = CommanderBridge()
    try:
        game.radio_picture.observe(
            track_id="H-99881", kind="HF", target_id=99881, source="HFDF",
            bearing=40.0, range_nm=None, observer_x=game.ship.x,
            observer_y=game.ship.y, course=None, quality=.7, now=game.sim_t,
            label="hidden-radio-id", bearing_uncertainty_deg=4.0)
        bridge.pump(game, server, now=time.monotonic())
        cookie, session = pair(server, "Radio", "radio")
        bridge.pump(game, server, now=time.monotonic())
        state = request(server, "/api/v2/state", cookie=cookie)[2]["radio"]
        ref = state["observations"][0]["ref"]
        assert "99881" not in json.dumps(state) and "hidden-radio-id" not in json.dumps(state)
        assert submit(game, bridge, server, cookie, session,
                      "radio_capture_hfdf", {"ref": ref}, 0)["reasoncode"] == "ok"
        assert len(game.hfdf_log) == 1
        before = list(game.hfdf_log)
        assert submit(game, bridge, server, cookie, session,
                      "radio_capture_hfdf", {"ref": "not-current"},
                      1)["reasoncode"] == "unknown_ref"
        assert game.hfdf_log == before
    finally:
        game.audio.shutdown()


def test_eloka_annotation_uses_opaque_intercept_and_candidate_refs(
        server, monkeypatch):
    game = Game(seed=420, start_menu=False, audio_enabled=False, language="en")
    bridge = CommanderBridge()
    try:
        monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)
        emitter = SurfaceShip(
            game.ship.x + 4.0, game.ship.y, random.Random(18), hostile=True,
            profile=game.runtime_catalog.surfaces["warship_01"],
            runtime_catalog=game.runtime_catalog)
        emitter.emitter = True
        game.civilians = []
        game.warships = [emitter]
        game.flights.flights = []
        game._update_esm_picture()
        bridge.pump(game, server, now=time.monotonic())
        cookie, session = pair(server, "ELOKA", "eloka")
        bridge.pump(game, server, now=time.monotonic())
        state = request(server, "/api/v2/state", cookie=cookie)[2]["eloka"]
        intercept = state["intercepts"][0]
        candidate = intercept["candidates"][0]
        encoded = json.dumps(state)
        assert set(candidate) == {"ref", "name", "score"}
        assert "emitter_key" not in encoded and candidate["ref"] != intercept["ref"]
        assert submit(game, bridge, server, cookie, session, "eloka_annotate", {
            "ref": intercept["ref"], "candidate_ref": candidate["ref"]},
            0)["reasoncode"] == "ok"
        assert len(game.eloka_annotations) == 1
        assert submit(game, bridge, server, cookie, session,
                      "eloka_clear_annotation", {"ref": intercept["ref"]},
                      1)["reasoncode"] == "ok"
        assert game.eloka_annotations == {}
    finally:
        game.audio.shutdown()


def test_stale_bound_sonar_ref_is_rejected_without_selection_or_target_mutation():
    game = Game(seed=421, start_menu=False, audio_enabled=False, language="en")
    try:
        contact = Contact(1, 99201, "passiv", "sub")
        contact.update_passive(80.0, .8, .8, "", game.sim_t)
        game.sonar.contacts[contact.target_id] = contact
        bindings = {"old": ("opaque", "SONAR-BRG", contact, True, contact)}
        del game.sonar.contacts[contact.target_id]
        before = (game.selected_contact, game.target, game.sonar.listen_bearing)
        assert CommanderBridge._apply_v2_action(
            game, "sonar_set_focus", {"ref": "old"}, bindings) == "stale_ref"
        assert (game.selected_contact, game.target, game.sonar.listen_bearing) == before
    finally:
        game.audio.shutdown()


def _capture_error(errors, function, *args, **kwargs):
    try:
        function(*args, **kwargs)
    except Exception as error:
        errors.append(error)
