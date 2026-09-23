"""Bounded binary Sonar stream over the authenticated protocol-v2 session."""

import base64
import json
import os
import socket
import struct

import pytest

from src.commander import server as transport
from test_commander_sessions_v2 import pair_v2, projection_states, server


def _publish_sonar(server):
    states = projection_states("stream-world")
    state = states["sonar"]
    state["clock"] = {"sim": 12.5}
    state["sonar"] = {"visualization": {
        "broadband": {"history": [{"age_s": 1.5, "bins": [0.0, .5, 1.0]}]},
        "lofar": {"history": [{"age_s": .25, "bearing": 72.0,
                                "bins": [.1, .2]}],
                  "spectrum": [.25, .75]},
        "demon": {"history": [{"age_s": .5, "bins": [.4]}],
                  "spectrum": [.6]},
        "receiver": {"listen_bearing": 71.0},
    }}
    chart = dict(protocol=2, revision="stream-world", size_nm=500,
                 landmasses=[], disclaimer="")
    server.publish_v2(states, {role: chart for role in states})


def test_binary_sonar_payload_is_versioned_bounded_and_quantized():
    state = projection_states("stream-world")["sonar"]
    state["clock"] = {"sim": 12.5}
    state["sonar"] = {"visualization": {
        "broadband": {"history": [{"age_s": 1.0, "bins": [0, .5, 1]}]},
        "lofar": {"history": [{"age_s": .25, "bearing": 15,
                                "bins": [.25]}], "spectrum": [.75]},
        "demon": {"history": [], "spectrum": []},
        "receiver": {"listen_bearing": 15},
    }}
    context, payload = transport._sonar_stream_payload(state, 7)
    assert context == ("stream-world", 0)
    assert payload[:4] == b"UJS2" and payload[4] == 1
    assert len(payload) <= transport.SONAR_STREAM_MAX_BYTES
    header = struct.unpack("<4sBBHQQdfHHHHHHfff", payload[:60])
    assert header[3:6] == (60, 7, 0)
    assert header[8:13] == (3, 1, 0, 1, 0)
    assert payload[60:] == bytes((0, 128, 255, 64, 191))


def test_compact_poll_projection_omits_only_streamed_sonar_arrays(server):
    _publish_sonar(server)
    compact = json.loads(server._v2_sonar_compact_state)
    visual = compact["sonar"]["visualization"]
    assert visual["broadband"]["history"] == []
    assert visual["lofar"]["history"] == []
    assert visual["lofar"]["spectrum"] == []
    assert visual["demon"]["history"] == []
    assert visual["demon"]["spectrum"] == []
    assert visual["receiver"] == {"listen_bearing": 71.0}


def test_websocket_requires_session_and_active_sonar_lease(server):
    _publish_sonar(server)
    _, cookie, _, paired = pair_v2(server, "Sonar stream")
    assert server.grant_station(paired["client_id"], "sonar")
    host, port = server.address
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    request = (
        f"GET {transport.SONAR_STREAM_ROUTE} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\nOrigin: http://{host}:{port}\r\n"
        "Upgrade: websocket\r\nConnection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
        "Sec-WebSocket-Protocol: u-jagd-sonar-v2\r\n"
        f"Cookie: {cookie}\r\n\r\n").encode("ascii")
    with socket.create_connection(server.address, timeout=3) as connection:
        connection.sendall(request)
        received = bytearray()
        while b"\r\n\r\n" not in received:
            received.extend(connection.recv(4096))
        headers, frame = bytes(received).split(b"\r\n\r\n", 1)
        assert headers.startswith(b"HTTP/1.1 101")
        assert b"Sec-WebSocket-Protocol: u-jagd-sonar-v2" in headers
        while len(frame) < 2:
            frame += connection.recv(4096)
        assert frame[0] == 0x82
        length = frame[1] & 0x7f
        if length == 126:
            while len(frame) < 4:
                frame += connection.recv(4096)
            length = struct.unpack("!H", frame[2:4])[0]
            offset = 4
        else:
            offset = 2
        while len(frame) < offset + length:
            frame += connection.recv(4096)
        assert frame[offset:offset + 4] == b"UJS2"
        assert length <= transport.SONAR_STREAM_MAX_BYTES


@pytest.mark.parametrize("role", ("sonar", "helicopter"))
def test_audio_websocket_is_leased_sequenced_and_revoked(server, role):
    _, cookie, _, paired = pair_v2(server, "Audio stream")
    client_id = paired["client_id"]
    assert server.grant_station(client_id, role)
    assert server.set_client_grant(client_id, role, "sonar_audio", True)
    prepare = (server.prepare_sonar_audio if role == "sonar"
               else server.prepare_helicopter_audio)
    publish = (server.publish_sonar_audio if role == "sonar"
               else server.publish_helicopter_audio)
    generation = prepare(world_session="audio-world", world_epoch=3)
    assert generation is not None
    pcm = bytes(transport.SONAR_AUDIO_BYTES)
    for _ in range(6):
        assert publish(pcm, world_session="audio-world",
                       world_epoch=3, station_generation=generation)
    host, port = server.address
    key = base64.b64encode(os.urandom(16)).decode("ascii")

    def handshake(cookie_value):
        cookie_header = f"Cookie: {cookie_value}\r\n" if cookie_value else ""
        return (f"GET /ws/v2/{role}/audio HTTP/1.1\r\nHost: {host}:{port}\r\n"
                f"Origin: http://{host}:{port}\r\nUpgrade: websocket\r\n"
                f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                "Sec-WebSocket-Version: 13\r\nSec-WebSocket-Protocol: u-jagd-audio-v2\r\n"
                f"{cookie_header}"
                "\r\n").encode("ascii")

    with socket.create_connection(server.address, timeout=3) as unauthorized:
        unauthorized.sendall(handshake(""))
        assert unauthorized.recv(1024).startswith(b"HTTP/1.1 401")
    with socket.create_connection(server.address, timeout=3) as connection:
        connection.settimeout(3)
        connection.sendall(handshake(cookie))
        received = bytearray()
        while b"\r\n\r\n" not in received:
            received.extend(connection.recv(4096))
        headers, frame = bytes(received).split(b"\r\n\r\n", 1)
        assert headers.startswith(b"HTTP/1.1 101")
        while len(frame) < 4:
            frame += connection.recv(4096)
        assert frame[0] == 0x82 and frame[1] == 126
        size = struct.unpack("!H", frame[2:4])[0]
        while len(frame) < size + 4:
            frame += connection.recv(4096)
        payload = frame[4:4 + size]
        assert len(payload) == 2060 and payload[:4] == b"UJA2"
        assert struct.unpack("<Q", payload[4:12])[0] == 3
        assert payload[12:] == pcm
        assert server.set_client_grant(client_id, role, "sonar_audio", False)
        # Already queued frames may arrive first. The worker must close after
        # its next bounded lease check rather than keep streaming indefinitely.
        while connection.recv(4096):
            pass
    assert server.set_client_grant(client_id, role, "sonar_audio", True)
    generation = prepare(world_session="audio-world", world_epoch=3)
    assert publish(pcm, world_session="audio-world", world_epoch=3,
                   station_generation=generation)
    with socket.create_connection(server.address, timeout=3) as reconnected:
        reconnected.settimeout(3)
        reconnected.sendall(handshake(cookie))
        response = bytearray()
        while b"\r\n\r\n" not in response:
            response.extend(reconnected.recv(4096))
        assert response.startswith(b"HTTP/1.1 101")
