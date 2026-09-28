"""Phone lookouts: calls, confirmation, suppressed automatic reports, the
roles' pairing and the self-signed HTTPS listener (src/core/phone_lookout.py,
src/commander/tls.py)."""

import datetime
import json
import math
import os
import ssl
import sys
from contextlib import closing
from pathlib import Path
import http.client

import pytest

from src.commander import CommanderServer, tls
from src.commander import server as transport
from src.core import config, opfor, phone_lookout

sys.path.insert(0, str(Path(__file__).parent))
from commander_web import top_level_files  # noqa: E402
from test_commander_sessions_v2 import request  # noqa: E402
from test_opfor_sub import _crewed, _feed_texts, _game  # noqa: E402
from test_uboot_scope import _clear, _place_frigate, _scope_up  # noqa: E402


# --- the frigate's lookout ----------------------------------------------------------

def _watch(monkeypatch, *roles):
    monkeypatch.setattr(phone_lookout, "manned", lambda _game, role: role in roles)


def _ship_ahead(distance_nm=2.0):
    game = _game(917)
    game.world.hour = 12.0
    ship = game.civilians[0]
    for other in game.civilians[1:] + game.warships:
        other.x, other.y = game.ship.x + 60.0, game.ship.y + 60.0
    ahead = math.radians(game.ship.course)
    ship.x = game.ship.x + distance_nm * math.sin(ahead)
    ship.y = game.ship.y - distance_nm * math.cos(ahead)
    ship.speed = 0.0
    game.world.land_blocks_line = lambda *args: False
    return game


def _run(game, seconds):
    for _ in range(int(seconds / .05)):
        game.update(.05)


def test_manned_lookout_only_sees_until_the_phone_calls(monkeypatch):
    _watch(monkeypatch, "lookout")
    game = _ship_ahead()
    _run(game, 2.0)
    assert game.lookout_phone
    assert game.lookout_sightings() == [] and game.lookout_reports == []
    assert len(game.lookout_eye) == 1
    eye = next(iter(game.lookout_eye.values()))
    assert abs(((eye.bearing - game.ship.course + 180) % 360) - 180) < 3
    # Wrong category, wrong bearing, wrong range: refused and logged.
    assert phone_lookout.call(game, "aircraft", eye.bearing) == "lookout_not_confirmed"
    assert phone_lookout.call(game, "ship", (eye.bearing + 40) % 360) == "lookout_not_confirmed"
    assert phone_lookout.call(game, "ship", eye.bearing, 9.0) == "lookout_not_confirmed"
    assert game.lookout_sightings() == []
    assert phone_lookout.call(game, "ship", (eye.bearing + 6) % 360, 2.5) is True
    tracks = game.lookout_sightings()
    assert len(tracks) == 1 and tracks[0].source == "LOOKOUT"
    assert len(game.lookout_reports) == 1
    assert game.callouts.detached()[-1]["key"] == "lookout_ship"
    # Once called, the lookout keeps following it; calling it again repeats the report.
    _run(game, 1.0)
    assert game.lookout_sightings() and not game.lookout_eye
    assert phone_lookout.call(game, "ship", tracks[0].bearing) is True
    assert [row["confirmed"] for row in game.lookout_calls] == [False, False, False, True, True]
    assert [row["category"] for row in phone_lookout.calls(game, "frigate")][:2] == ["ship", "ship"]


def test_unmanned_lookout_reports_by_itself(monkeypatch):
    _watch(monkeypatch)
    game = _ship_ahead()
    _run(game, 2.0)
    assert not game.lookout_phone and not game.lookout_eye
    assert game.lookout_sightings() and game.lookout_reports


def test_phone_projection_carries_outlines_and_calls_without_truth(monkeypatch):
    from src.commander.lookout_projection import build_lookout_states
    from src.commander.v2 import schema
    _watch(monkeypatch, "lookout")
    game = _ship_ahead()
    _run(game, 2.0)
    eye = next(iter(game.lookout_eye.values()))
    phone_lookout.call(game, "torpedo", (eye.bearing + 180) % 360)
    status = dict(session="s", epoch=1, revision=1, seq=1, phase="live")
    states = build_lookout_states(game, status, None, dict(role=None))
    view = states["lookout"]["lookout"]
    assert tuple(view) == schema.LOOKOUT_PHONE_FIELDS
    assert view["manned"] and view["side"] == "frigate"
    assert len(view["outlines"]) == 1 and not view["outlines"][0]["called"]
    assert set(view["outlines"][0]) == set(schema.LOOKOUT_PHONE_OUTLINE_FIELDS)
    assert view["calls"][0]["category"] == "torpedo" and not view["calls"][0]["confirmed"]
    text = json.dumps(states)
    for forbidden in ("target_id", "track_id", '"kind"', "signature", "emitter_key", "seed", "rng"):
        assert forbidden not in text
    assert states["uboot_lookout"] == {"role": None}


# --- the boat's periscope -----------------------------------------------------------

def test_phone_periscope_calls_replace_the_crews_sighting_notices(monkeypatch):
    _watch(monkeypatch, "uboot_lookout")
    game, _server, _bridge = _crewed(seed=61)
    boat = game.opfor
    _clear(game)
    _place_frigate(game, boat, 3.0, bearing=45.0)
    _scope_up(boat)
    opfor.update_crew(game, boat)
    rows = boat.orders.sightings
    assert len(rows) == 1 and rows[0]["cls"] == "warship"
    assert not any("warship in sight" in text for text in _feed_texts(game))
    assert phone_lookout.boat_call(game, boat, "merchant", 45.0) == "lookout_not_confirmed"
    assert phone_lookout.boat_call(game, boat, "warship", 225.0) == "lookout_not_confirmed"
    assert phone_lookout.boat_call(game, boat, "warship", 48.0) is True
    assert any("Periscope reports: warship" in text for text in _feed_texts(game))
    assert [row["confirmed"] for row in phone_lookout.calls(game, "boat")] == [True, False, False]
    boat.sub.command_mast(False)
    assert phone_lookout.boat_call(game, boat, "warship", 48.0) == "uboot_mast_down"


def test_lookout_call_parameters_are_strict():
    from src.commander.v2.commands import V2_ACTION_REGISTRY
    check = V2_ACTION_REGISTRY["lookout_call"].validate_params
    assert check({"category": "ship", "bearing": 40.0, "range_nm": None})
    assert check({"category": "torpedo", "bearing": 0, "range_nm": 5})
    for bad in ({"category": "ship", "bearing": 360, "range_nm": None},
                {"category": "whale", "bearing": 40, "range_nm": None},
                {"category": "ship", "bearing": 40, "range_nm": 0},
                {"category": "ship", "bearing": 40, "range_nm": 61},
                {"category": "ship", "bearing": float("nan"), "range_nm": None},
                {"category": "ship", "bearing": 40},
                {"category": "ship", "bearing": True, "range_nm": None}):
        assert not check(bad), bad
    assert V2_ACTION_REGISTRY["lookout_call"].stations == frozenset({"lookout", "uboot_lookout"})


# --- pairing ------------------------------------------------------------------------

@pytest.fixture
def crew_server(tmp_path, monkeypatch):
    for name in top_level_files():
        (tmp_path / name).write_text(name, encoding="utf-8")
    monkeypatch.setattr(transport.resources, "files", lambda package: tmp_path)
    instance = CommanderServer()
    instance.start("127.0.0.1", 0)
    try:
        yield instance
    finally:
        instance.stop()


def _pair(server, role=None, name="Phone"):
    body = {"code": server.pairing_code, "name": name}
    if role is not None:
        body["role"] = role
    status, headers, payload = request(server, "/api/v2/pair", "POST", body)
    cookie = headers.get("Set-Cookie", "").split(";", 1)[0] or None
    return status, cookie, payload


def test_a_phone_pairs_straight_onto_its_role_and_nothing_else(crew_server):
    status, cookie, body = _pair(crew_server, "lookout")
    assert status == 200 and body["station"] == "lookout" and body["grants"]["command"]
    assert crew_server.station_leased("lookout")
    status, _headers, payload = request(crew_server, "/api/v2/stations/request", "POST",
                                        {"station": "bridge"}, cookie=cookie, csrf=body["csrf"])
    assert status == 403
    status, _headers, payload = request(crew_server, "/api/v2/stations/request", "POST",
                                        {"station": "uboot_lookout"}, cookie=cookie,
                                        csrf=body["csrf"])
    assert status == 200
    # A second phone on the same role waits for it.
    status, _cookie, second = _pair(crew_server, "lookout", "Second")
    assert status == 200 and second["station"] is None
    assert _pair(crew_server, "bridge")[0] == 400


def test_solo_mode_admits_one_phone_per_lookout_role(crew_server):
    crew_server.set_solo_mode(True)
    assert _pair(crew_server)[0] == 200                        # the solo session
    assert _pair(crew_server)[0] == 429                        # no second desktop
    assert _pair(crew_server, "lookout")[0] == 200
    assert _pair(crew_server, "uboot_lookout")[0] == 200
    assert _pair(crew_server, "lookout")[0] == 429


# --- HTTPS --------------------------------------------------------------------------

def test_certificate_names_the_address_and_is_reused(tmp_path):
    now = datetime.datetime(2026, 9, 28, tzinfo=datetime.timezone.utc)
    cert, key = tls.ensure_certificate(str(tmp_path / "tls"), "192.168.4.7", now=now)
    assert os.stat(key).st_mode & 0o777 == 0o600
    first = Path(cert).read_bytes()
    decoded = ssl._ssl._test_decode_cert(cert)
    assert ("IP Address", "192.168.4.7") in decoded["subjectAltName"]
    assert ("DNS", "localhost") in decoded["subjectAltName"]
    assert tls.ensure_certificate(str(tmp_path / "tls"), "192.168.4.7", now=now)[0] == cert
    assert Path(cert).read_bytes() == first
    # A new address or the end of its validity makes a new one.
    tls.ensure_certificate(str(tmp_path / "tls"), "10.0.0.2", now=now)
    assert Path(cert).read_bytes() != first
    second = Path(cert).read_bytes()
    later = now + datetime.timedelta(days=tls.VALID_DAYS - tls.RENEW_DAYS + 1)
    tls.ensure_certificate(str(tmp_path / "tls"), "10.0.0.2", now=later)
    assert Path(cert).read_bytes() != second
    assert len(tls.fingerprint(cert).split(":")) == 32
    (tmp_path / "real").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "real")
    with pytest.raises(OSError):
        tls.ensure_certificate(str(tmp_path / "link"), "10.0.0.2")
    with pytest.raises(ValueError):
        tls.ensure_certificate(str(tmp_path / "tls"), "../etc")


def test_signature_verifies():
    import hashlib
    secret = 0x1234567
    public = tls._multiply(secret)
    assert tls._on_curve(public)
    digest = hashlib.sha256(b"u-jagd").digest()
    r, s = tls._sign(secret, digest)
    assert tls._verify(public, digest, r, s)
    assert not tls._verify(public, hashlib.sha256(b"other").digest(), r, s)


def test_https_listener_serves_the_phone_page(tmp_path, monkeypatch):
    for name in top_level_files():
        (tmp_path / name).write_text(name, encoding="utf-8")
    monkeypatch.setattr(transport.resources, "files", lambda package: tmp_path)
    cert, key = tls.ensure_certificate(str(tmp_path / "tls"), "127.0.0.1")
    instance = CommanderServer()
    instance.start("127.0.0.1", 0, tls_context=tls.context(cert, key), tls_port=0)
    try:
        host, port = instance.tls_address
        client = ssl.create_default_context(cafile=cert)      # the phone, once accepted
        with closing(http.client.HTTPSConnection(host, port, timeout=5, context=client)) as link:
            link.request("GET", "/lookout")
            response = link.getresponse()
            assert response.status == 200 and response.read() == b"lookout.html"
        # Pairing over HTTPS accepts the HTTPS origin and marks the cookie Secure.
        with closing(http.client.HTTPSConnection(host, port, timeout=5, context=client)) as link:
            link.request("POST", "/api/v2/pair", body=json.dumps(
                {"code": instance.pairing_code, "name": "Phone", "role": "lookout"}),
                headers={"Origin": f"https://{host}:{port}", "Content-Type": "application/json"})
            response = link.getresponse()
            response.read()
            assert response.status == 200
            assert "Secure" in response.getheader("Set-Cookie")
        # A plain-HTTP origin is refused on the HTTPS listener.
        with closing(http.client.HTTPSConnection(host, port, timeout=5, context=client)) as link:
            link.request("POST", "/api/v2/pair", body=json.dumps(
                {"code": instance.pairing_code, "name": "Phone", "role": "lookout"}),
                headers={"Origin": f"http://{host}:{port}", "Content-Type": "application/json"})
            response = link.getresponse()
            response.read()
            assert response.status == 403
        # An untrusting client sees the self-signed certificate and stops.
        with pytest.raises(ssl.SSLError):
            with closing(http.client.HTTPSConnection(
                    host, port, timeout=5, context=ssl.create_default_context())) as link:
                link.request("GET", "/lookout")
                link.getresponse()
        # The plain listener keeps serving.
        assert request(instance, "/lookout")[0] == 200
    finally:
        instance.stop()
    assert instance.tls_address is None
