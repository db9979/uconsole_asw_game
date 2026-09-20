"""Isolated tests for the one-shot API probes used by the options-menu
'API test' button - network I/O is mocked, no real sockets are opened."""

import json
import urllib.request

from src.network import adsb_client, ais_client

_BBOX = ((53.0, 7.0), (55.0, 9.0))


class _FakeWebsocket:
    def __init__(self, recv_raw=None, recv_exc=None):
        self.sent = []
        self._recv_raw = recv_raw
        self._recv_exc = recv_exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def send(self, message):
        self.sent.append(message)

    async def recv(self):
        if self._recv_exc is not None:
            raise self._recv_exc
        return self._recv_raw


def test_ais_test_connection_ok_on_subscription_confirmation(monkeypatch):
    import websockets

    connect_kwargs = {}
    fake_ws = _FakeWebsocket(recv_raw=json.dumps({
        "MessageType": "SubscriptionConfirmation",
        "Message": {"SubscriptionConfirmation": {"CompressionEnabled": True}},
    }))
    def _connect(*args, **kwargs):
        connect_kwargs.update(kwargs)
        return fake_ws

    monkeypatch.setattr(websockets, "connect", _connect)
    ok, reason = ais_client.test_connection("valid-key", _BBOX, timeout=1.0)
    assert ok is True
    assert reason is None
    subscription = json.loads(fake_ws.sent[0])
    assert subscription["APIKey"] == "valid-key"
    assert {"PositionReport", "StandardClassBPositionReport",
            "ExtendedClassBPositionReport", "StaticDataReport"} <= set(
                subscription["FilterMessageTypes"])
    assert connect_kwargs["compression"] == "deflate"


def test_ais_test_connection_reports_missing_confirmation(monkeypatch):
    import asyncio
    import websockets

    fake_ws = _FakeWebsocket(recv_exc=asyncio.TimeoutError())
    monkeypatch.setattr(websockets, "connect", lambda *a, **k: fake_ws)
    ok, reason = ais_client.test_connection("valid-key", _BBOX, timeout=0.1)
    assert ok is False
    assert reason == "no subscription confirmation received"


def test_ais_client_accepts_class_b_position_reports(monkeypatch):
    client = ais_client.AisStreamClient("key", _BBOX)
    monkeypatch.setattr(ais_client.time, "time", lambda: 123.0)
    raw = json.dumps({
        "MessageType": "ExtendedClassBPositionReport",
        "MetaData": {"MMSI": 211123456, "ShipName": "CLASS B"},
        "Message": {"ExtendedClassBPositionReport": {
            "Latitude": 54.1, "Longitude": 8.2, "Sog": 7.5,
            "Cog": 91.0, "TrueHeading": 90, "Type": 70,
        }},
    })

    assert client._handle_message(raw) is True
    assert client.reports.get_nowait() == {
        "mmsi": 211123456, "lat": 54.1, "lon": 8.2,
        "name": "CLASS B", "ts": 123.0, "cog": 91.0, "sog": 7.5,
        "heading": 90, "position_accuracy": None, "nav_status": None,
        "ship_type": 70,
    }


def test_ais_client_reads_user_id_and_ship_static_details(monkeypatch):
    client = ais_client.AisStreamClient("key", _BBOX)
    monkeypatch.setattr(ais_client.time, "time", lambda: 123.0)
    raw = json.dumps({
        "MessageType": "ShipStaticData",
        "MetaData": {},
        "Message": {"ShipStaticData": {
            "UserID": 211123456, "Name": "NORDSTERN@@@@", "CallSign": "DABC@@",
            "ImoNumber": 9876543, "Type": 70, "Destination": "HAMBURG@@",
            "MaximumStaticDraught": 7.4,
            "Dimension": {"A": 80, "B": 20, "C": 8, "D": 7},
        }},
    })

    assert client._handle_message(raw) is True
    assert client.reports.get_nowait() == {
        "mmsi": 211123456, "lat": None, "lon": None,
        "name": "NORDSTERN", "ts": 123.0, "ship_type": 70,
        "callsign": "DABC", "imo": 9876543, "destination": "HAMBURG",
        "draught_m": 7.4, "length_m": 100.0, "width_m": 15.0,
    }


def test_ais_client_reads_class_b_static_data_report(monkeypatch):
    client = ais_client.AisStreamClient("key", _BBOX)
    monkeypatch.setattr(ais_client.time, "time", lambda: 123.0)
    raw = json.dumps({
        "MessageType": "StaticDataReport",
        "MetaData": {},
        "Message": {"StaticDataReport": {
            "UserID": 211654321, "PartNumber": 1,
            "ReportA": {"Name": "CLASS B TEST"},
            "ReportB": {"CallSign": "DBCD", "ShipType": 60,
                        "Dimension": {"A": 10, "B": 5, "C": 3, "D": 2}},
        }},
    })

    assert client._handle_message(raw) is True
    report = client.reports.get_nowait()
    assert report == {
        "mmsi": 211654321, "lat": None, "lon": None,
        "name": "CLASS B TEST", "ts": 123.0, "callsign": "DBCD",
        "ship_type": 60, "length_m": 15.0, "width_m": 5.0,
    }


def test_ais_test_connection_reports_service_error(monkeypatch):
    import websockets

    fake_ws = _FakeWebsocket(recv_raw=json.dumps({"error": "invalid api key"}))
    monkeypatch.setattr(websockets, "connect", lambda *a, **k: fake_ws)
    ok, reason = ais_client.test_connection("bad-key", _BBOX, timeout=1.0)
    assert ok is False
    assert reason == "invalid api key"


def test_ais_test_connection_reports_connect_failure(monkeypatch):
    import websockets

    def _raise(*a, **k):
        raise OSError("connection refused")

    monkeypatch.setattr(websockets, "connect", _raise)
    ok, reason = ais_client.test_connection("key", _BBOX, timeout=1.0)
    assert ok is False
    assert "connection refused" in reason


class _FakeHttpResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._payload


def test_adsb_test_connection_ok(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **k: _FakeHttpResponse({"states": []}))
    ok, reason = adsb_client.test_connection("", _BBOX)
    assert ok is True
    assert reason is None


def test_adsb_test_connection_reports_error(monkeypatch):
    def _raise(*a, **k):
        raise OSError("timed out")

    monkeypatch.setattr(urllib.request, "urlopen", _raise)
    ok, reason = adsb_client.test_connection("", _BBOX)
    assert ok is False
    assert reason == "timed out"
