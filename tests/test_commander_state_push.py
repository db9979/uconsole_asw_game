"""State push over ``/ws/v2/state``: same projection as the poll route, sent
on change at a bounded rate with heartbeats, closed on authority loss."""

import base64
import json
import os
import socket
import struct
import time

import pytest

from src.commander import server as transport
from src.commander.v2 import wire
from test_commander_sessions_v2 import pair_v2, projection_states, request, server


def _publish(server, revision="push-world", seq=1):
    states = projection_states(revision)
    for state in states.values():
        state["seq"] = seq
    chart = dict(protocol=2, revision=revision, size_nm=500, landmasses=[], disclaimer="")
    server.publish_v2(states, {role: chart for role in states})


def _handshake(server, cookie, protocol=wire.STATE_PUSH_PROTOCOL, route=wire.STATE_PUSH_ROUTE):
    host, port = server.address
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    connection = socket.create_connection(server.address, timeout=5)
    connection.sendall((
        f"GET {route} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\nOrigin: http://{host}:{port}\r\n"
        "Upgrade: websocket\r\nConnection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
        f"Sec-WebSocket-Protocol: {protocol}\r\n"
        f"Cookie: {cookie}\r\n\r\n").encode("ascii"))
    received = bytearray()
    while b"\r\n\r\n" not in received:
        chunk = connection.recv(4096)
        if not chunk:
            break
        received.extend(chunk)
    headers, rest = bytes(received).split(b"\r\n\r\n", 1)
    return connection, headers, bytearray(rest)


def _frame(connection, buffer, timeout=5.0):
    """(opcode, payload, arrival time) of the next server frame."""
    deadline = time.monotonic() + timeout
    while True:
        if len(buffer) >= 2:
            opcode = buffer[0] & 0x0F
            length = buffer[1] & 0x7F
            offset = 2
            if length == 126 and len(buffer) >= 4:
                length = struct.unpack("!H", buffer[2:4])[0]
                offset = 4
            elif length == 127 and len(buffer) >= 10:
                length = struct.unpack("!Q", buffer[2:10])[0]
                offset = 10
            elif length >= 126:
                length = None
            if length is not None and len(buffer) >= offset + length:
                payload = bytes(buffer[offset:offset + length])
                del buffer[:offset + length]
                return opcode, payload, time.monotonic()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("no websocket frame")
        connection.settimeout(remaining)
        chunk = connection.recv(65536)
        if not chunk:
            raise ConnectionError("socket closed")
        buffer.extend(chunk)


def test_push_sends_the_poll_projection_then_changes_and_heartbeats(server):
    _publish(server)
    _, cookie, _, paired = pair_v2(server, "Push bridge")
    assert server.grant_station(paired["client_id"], "bridge")
    status, _, polled = request(server, "/api/v2/state", cookie=cookie)
    assert status == 200
    connection, headers, buffer = _handshake(server, cookie)
    try:
        assert headers.startswith(b"HTTP/1.1 101")
        assert b"Sec-WebSocket-Protocol: u-jagd-state-v2" in headers
        opcode, payload, first_at = _frame(connection, buffer)
        assert opcode == 1                                 # text frame
        assert json.loads(payload) == polled               # same projection as the poll
        assert server.state_push_clients() == 1
        # Idle: a heartbeat about every 2 s, no repeated state.
        opcode, payload, beat_at = _frame(connection, buffer)
        assert opcode == 1 and json.loads(payload) == {"protocol": 2, "heartbeat": True}
        assert 1.5 <= beat_at - first_at <= 3.5
        # A publish reaches the socket; several rapid publishes are paced at 4 Hz
        # and only the latest state arrives.
        sent_at = time.monotonic()
        _publish(server, seq=2)
        opcode, payload, second_at = _frame(connection, buffer)
        assert json.loads(payload)["seq"] == 2 and second_at - sent_at < 1.5
        for seq in (3, 4, 5, 6):
            _publish(server, seq=seq)
        opcode, payload, third_at = _frame(connection, buffer)
        state = json.loads(payload)
        assert state.get("heartbeat") is not True and state["seq"] == 6
        assert third_at - second_at >= 1.0 / wire.STATE_PUSH_MAX_HZ - 0.05
        # A second push socket for the same session is refused.
        other, other_headers, _ = _handshake(server, cookie)
        other.close()
        assert other_headers.startswith(b"HTTP/1.1 409")
        # Losing the station closes the push with a policy close frame.
        assert server.set_client_grant(paired["client_id"], "bridge", "command", True)
        assert server.revoke_station("bridge")
        while True:
            opcode, payload, _ = _frame(connection, buffer)
            if opcode == 8:
                break
        assert struct.unpack("!H", payload[:2])[0] == 1008
    finally:
        connection.close()
    deadline = time.monotonic() + 3.0
    while server.state_push_clients() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.state_push_clients() == 0


def test_push_needs_a_session_a_lease_the_protocol_and_the_host_switch(server):
    _publish(server)
    _, cookie, _, paired = pair_v2(server, "Push lobby")
    connection, headers, _ = _handshake(server, cookie)
    connection.close()
    assert headers.startswith(b"HTTP/1.1 403")            # no station
    assert server.grant_station(paired["client_id"], "opz")
    connection, headers, _ = _handshake(server, cookie, protocol="u-jagd-sonar-v2")
    connection.close()
    assert headers.startswith(b"HTTP/1.1 400")            # wrong subprotocol
    connection, headers, _ = _handshake(server, "ujagd_remote_v2=nope")
    connection.close()
    assert headers.startswith(b"HTTP/1.1 401")
    server.set_state_push(False)
    connection, headers, _ = _handshake(server, cookie)
    connection.close()
    assert headers.startswith(b"HTTP/1.1 403")            # host switched the push off
    server.set_state_push(True)
    connection, headers, buffer = _handshake(server, cookie)
    try:
        assert headers.startswith(b"HTTP/1.1 101")
        opcode, payload, _ = _frame(connection, buffer)
        assert opcode == 1 and json.loads(payload)["role"] == "opz"
        server.set_state_push(False)                        # drops the open socket
        while True:
            opcode, payload, _ = _frame(connection, buffer)
            if opcode == 8:
                break
    finally:
        connection.close()


def test_large_frames_carry_a_64_bit_length():
    payload = b"x" * 70000
    frame = wire._websocket_frame(payload, opcode=1)
    assert frame[:2] == bytes((0x81, 127))
    assert struct.unpack("!Q", frame[2:10])[0] == 70000 and frame[10:] == payload
    with pytest.raises(ValueError):
        wire._websocket_frame(b"y" * (wire.STATE_MAX_BYTES + 1))
    assert transport.STATE_MAX_BYTES == wire.STATE_MAX_BYTES
