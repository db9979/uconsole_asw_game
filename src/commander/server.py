"""Bounded HTTP transport for Commander v1 and Remote Crew v2.

HTTP is unencrypted and trusted-LAN-only. Credentials and pairing codes must
not cross an untrusted network. This module neither imports simulation code
nor starts on import.
"""

from collections import OrderedDict, deque
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from importlib import resources
import hashlib
import io
import ipaddress
import json
import math
import secrets
import socket
import threading
import time
import re
import unicodedata

from src.core.config import (NATO_AFFILIATIONS, PLAYER_CLASSES,
                             RADAR_RANGE_SCALES_NM, SHIP_SPEED_MAX_KN,
                             HELO_DIP_DEPTH_MIN_M, HELO_DIP_DEPTH_MAX_M)
_CONNECTION_DEADLINE_S = 3.0
_CONTACT_ASSET_ROUTE = re.compile(
    r"/contact-analysis/[a-z0-9][a-z0-9_.-]{0,95}-(?:cruise|high)\.png").fullmatch
_MAX_PREBUILT_ROUTES = 227
_MAX_PREBUILT_FILE_BYTES = 4 * 1024 * 1024
_MAX_PREBUILT_BYTES = 32 * 1024 * 1024
_V2_COOKIE = "ujagd_remote_v2"
_V2_SESSION_IDLE_S = 8 * 60 * 60
_V2_STATION_LEASE_S = 15.0
_V2_SESSION_LIMIT = 12
STATIONS = ("bridge", "sonar", "weapons", "damage", "opz", "radio",
            "engine", "helicopter", "eloka")
STATE_MAX_BYTES = 512 * 1024
CHART_MAX_BYTES = 2 * 1024 * 1024
_V2_STATION_CAPABILITIES = ("command", "direct_fire", "sonar_audio")
SONAR_AUDIO_BYTES = 2048
SONAR_AUDIO_FRAMES = 1024
SONAR_AUDIO_RATE = 4096
_SAFE_INTEGER_MAX = 2**53 - 1
_V2_SONAR_AUDIO_FIELDS = {"protocol", "after", "world_session", "world_epoch",
                          "station_generation", "active_generation"}
_V2_COMMAND_FIELDS = {"protocol", "id", "seq", "station", "station_generation",
                      "active_generation", "world_session", "world_epoch", "resource_revision",
                      "action", "params"}
_V2_COMMAND_GLOBAL_LIMIT = 64
_V2_COMMAND_CLIENT_LIMIT = 8
_V2_COMMAND_HISTORY_LIMIT = 64
_V2_COMMAND_MAX_AGE_S = 2.0
_COOKIE_NAME = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+").fullmatch
_COOKIE_VALUE = re.compile(r"[!#$%&'()*+\-./:<=>?@\[\]^_`{|}~0-9A-Za-z]*").fullmatch


def _json_bytes(value):
    return json.dumps(value, allow_nan=False, ensure_ascii=True,
                      separators=(",", ":")).encode("ascii")


SIMLOG_MAX_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class V2Action:
    """Closed command metadata; M6/M7 add schemas and main-thread handlers here."""

    stations: frozenset
    validate_params: object
    direct_fire: bool = False


def _no_params(params):
    return type(params) is dict and not params


def _course_params(params):
    return (type(params) is dict and set(params) == {"course"}
            and type(params["course"]) in (int, float)
            and 0 <= params["course"] < 360)


def _speed_params(params):
    return (type(params) is dict and set(params) == {"speed_kn"}
            and type(params["speed_kn"]) in (int, float)
            and 0 <= params["speed_kn"] <= SHIP_SPEED_MAX_KN)


def _ref(value):
    return (type(value) is str and 1 <= len(value) <= 64
            and not any(unicodedata.category(char).startswith("C") for char in value))


def _classification_params(params):
    return (type(params) is dict and set(params) == {"ref", "classification"}
            and _ref(params["ref"])
            and (params["classification"] is None
                 or params["classification"] in PLAYER_CLASSES))


def _release_params(params):
    return (type(params) is dict and set(params) == {"ref", "released"}
            and _ref(params["ref"]) and type(params["released"]) is bool)


def _affiliation_params(params):
    return (type(params) is dict and set(params) == {"ref", "affiliation"}
            and _ref(params["ref"])
            and params["affiliation"] in NATO_AFFILIATIONS)


def _fusion_refs_params(params):
    refs = params.get("refs") if type(params) is dict and set(params) == {"refs"} else None
    return (type(refs) is list and 2 <= len(refs) <= 8
            and all(_ref(ref) for ref in refs) and len(set(refs)) == len(refs))


def _single_ref_params(params):
    return type(params) is dict and set(params) == {"ref"} and _ref(params["ref"])


def _torpedo_params(params):
    return (type(params) is dict and set(params) == {"ref", "depth_m"}
            and _ref(params["ref"])
            and type(params["depth_m"]) in (int, float)
            and math.isfinite(params["depth_m"])
            and 10 <= params["depth_m"] <= 300)


def _radar_params(params):
    return (type(params) is dict and set(params) == {"domain", "enabled"}
            and params["domain"] in ("surface", "air")
            and type(params["enabled"]) is bool)


def _range_params(params):
    return (type(params) is dict and set(params) == {"range_nm"}
            and type(params["range_nm"]) in (int, float)
            and params["range_nm"] in RADAR_RANGE_SCALES_NM)


def _bool_params(name):
    return lambda params: (type(params) is dict and set(params) == {name}
                           and type(params[name]) is bool)


def _enum_params(name, values):
    return lambda params: (type(params) is dict and set(params) == {name}
                           and type(params[name]) is str
                           and params[name] in values)


def _bounded_number_params(name, minimum, maximum, *, nullable=False):
    def validate(params):
        if type(params) is not dict or set(params) != {name}:
            return False
        value = params[name]
        if nullable and value is None:
            return True
        return (type(value) in (int, float)
                and minimum <= value <= maximum and math.isfinite(value))
    return validate


_COMPARTMENTS = frozenset(("bridge", "sonar", "weapons", "opz", "radio",
                           "engine", "flightdeck", "hull_left", "hull_right"))


def _team_compartment_params(params):
    return (type(params) is dict and set(params) == {"team", "compartment"}
            and type(params["team"]) is int and 1 <= params["team"] <= 3
            and type(params["compartment"]) is str
            and params["compartment"] in _COMPARTMENTS)


def _annotation_params(params):
    return (type(params) is dict and set(params) == {"ref", "candidate_ref"}
            and _ref(params["ref"]) and _ref(params["candidate_ref"]))


def _waypoint_params(params):
    return (type(params) is dict and set(params) == {"x", "y"}
            and all(type(params[key]) in (int, float)
                    and 0 <= params[key] <= 1000 and math.isfinite(params[key])
                    for key in ("x", "y")))


def _bearing_params(params):
    return (type(params) is dict and set(params) == {"bearing"}
            and type(params["bearing"]) in (int, float)
            and 0 <= params["bearing"] < 360
            and math.isfinite(params["bearing"]))


V2_ACTION_REGISTRY = {
    "acknowledge": V2Action(frozenset(STATIONS), _no_params),
    "bridge_set_course": V2Action(frozenset({"bridge"}), _course_params),
    "bridge_set_speed": V2Action(frozenset({"bridge"}), _speed_params),
    "sonar_classify": V2Action(frozenset({"sonar"}), _classification_params),
    "sonar_set_release": V2Action(frozenset({"sonar"}), _release_params),
    "opz_classify": V2Action(frozenset({"opz"}), _classification_params),
    "opz_affiliate": V2Action(frozenset({"opz"}), _affiliation_params),
    "opz_create_fusion": V2Action(frozenset({"opz"}), _fusion_refs_params),
    "opz_dissolve_fusion": V2Action(frozenset({"opz"}), _single_ref_params),
    "opz_set_radar": V2Action(frozenset({"opz"}), _radar_params),
    "opz_set_range": V2Action(frozenset({"opz"}), _range_params),
    "opz_designate_target": V2Action(frozenset({"opz"}), _single_ref_params),
    "engine_set_telegraph": V2Action(frozenset({"engine"}), _enum_params(
        "order", ("ASTERN", "STOP", "SLOW", "HALF", "FULL", "FLANK"))),
    "engine_set_course": V2Action(frozenset({"engine"}), _course_params),
    "engine_set_speed": V2Action(frozenset({"engine"}), _speed_params),
    "engine_set_quiet_mode": V2Action(frozenset({"engine"}),
                                      _bool_params("enabled")),
    "damage_assign_team": V2Action(frozenset({"damage"}),
                                   _team_compartment_params),
    "damage_unassign_team": V2Action(frozenset({"damage"}),
                                     _team_compartment_params),
    "radio_capture_hfdf": V2Action(frozenset({"radio"}), _single_ref_params),
    "eloka_annotate": V2Action(frozenset({"eloka"}), _annotation_params),
    "eloka_clear_annotation": V2Action(frozenset({"eloka"}), _single_ref_params),
    "sonar_set_listen_bearing": V2Action(frozenset({"sonar"}), _bearing_params),
    "sonar_set_focus": V2Action(frozenset({"sonar"}), _single_ref_params),
    "sonar_clear_focus": V2Action(frozenset({"sonar"}), _no_params),
    "sonar_set_array_mode": V2Action(frozenset({"sonar"}),
        _enum_params("mode", ("BOW", "TOWED"))),
    "sonar_set_tas": V2Action(frozenset({"sonar"}), _bool_params("deployed")),
    "sonar_set_tow_depth": V2Action(frozenset({"sonar"}),
        _bounded_number_params("depth_m", 20, 260)),
    "sonar_measure_bt": V2Action(frozenset({"sonar"}), _no_params),
    "sonar_active_ping": V2Action(frozenset({"sonar"}), _no_params),
    "sonar_set_tma_enabled": V2Action(frozenset({"sonar"}),
                                      _bool_params("enabled")),
    "sonar_set_gain": V2Action(frozenset({"sonar"}),
        _bounded_number_params("gain_db", -12, 24)),
    "sonar_set_audition_mode": V2Action(frozenset({"sonar"}),
        _enum_params("mode", ("BROADBAND", "FILTERED", "HETERODYNE"))),
    "sonar_set_band_preset": V2Action(frozenset({"sonar"}),
        _enum_params("preset", ("FULL", "LOW", "SHAFT", "MID"))),
    "sonar_set_notch": V2Action(frozenset({"sonar"}), _bool_params("enabled")),
    "sonar_set_peak_hold": V2Action(frozenset({"sonar"}),
                                    _bool_params("enabled")),
    "sonar_set_harmonic": V2Action(frozenset({"sonar"}),
        _bounded_number_params("frequency_hz", 0.000001, 300, nullable=True)),
    "sonar_designate_target": V2Action(frozenset({"sonar"}), _single_ref_params),
    "helicopter_launch": V2Action(frozenset({"helicopter"}), _no_params),
    "helicopter_return": V2Action(frozenset({"helicopter"}), _no_params),
    "helicopter_set_waypoint": V2Action(frozenset({"helicopter"}),
                                        _waypoint_params),
    "helicopter_deploy_buoy": V2Action(frozenset({"helicopter"}), _no_params),
    "helicopter_set_dipping": V2Action(frozenset({"helicopter"}),
                                        _bool_params("deployed")),
    "helicopter_set_dip_depth": V2Action(frozenset({"helicopter"}),
        _bounded_number_params("depth_m", HELO_DIP_DEPTH_MIN_M,
                               HELO_DIP_DEPTH_MAX_M)),
    "helicopter_dipping_ping": V2Action(frozenset({"helicopter"}), _no_params),
    "weapons_launch_torpedo": V2Action(
        frozenset({"weapons"}), _torpedo_params, direct_fire=True),
    "helicopter_launch_torpedo": V2Action(
        frozenset({"weapons", "helicopter"}), _torpedo_params,
        direct_fire=True),
    "weapons_deploy_nixie": V2Action(
        frozenset({"weapons"}), _no_params, direct_fire=True),
    "opz_launch_essm": V2Action(
        frozenset({"opz"}), _single_ref_params, direct_fire=True),
    "opz_launch_chaff": V2Action(
        frozenset({"opz"}), _single_ref_params, direct_fire=True),
}


@dataclass(frozen=True)
class V2CommandEnvelope:
    """Detached transport record containing no session or simulation objects."""

    session_digest: bytes
    client_id: str
    client_ordinal: int
    role: str
    lease_generation: int
    active_generation: int
    received_at: float
    body_bytes: bytes
    command_id: str
    seq: int

    def body(self):
        return json.loads(self.body_bytes.decode("ascii"), object_pairs_hook=_object,
                          parse_float=_number, parse_constant=_number)


def _v2_command_valid(command):
    if (type(command) is not dict or set(command) != _V2_COMMAND_FIELDS
            or command.get("protocol") != 2):
        return False
    action = command.get("action")
    spec = V2_ACTION_REGISTRY.get(action) if type(action) is str else None
    if spec is None or command.get("station") not in spec.stations:
        return False
    for field in ("id", "world_session"):
        value = command.get(field)
        if (type(value) is not str or not 1 <= len(value) <= 64
                or any(unicodedata.category(char).startswith("C") for char in value)):
            return False
    for field in ("seq", "station_generation", "active_generation", "world_epoch",
                  "resource_revision"):
        maximum = 2**53 - 2 if field == "seq" else 2**53 - 1
        if type(command.get(field)) is not int or not 0 <= command[field] <= maximum:
            return False
    return spec.validate_params(command.get("params")) is True


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _number(text):
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("nonfinite number")
    return value


def _command_valid(command):
    if not isinstance(command, dict):
        return False
    action = command.get("action")
    if action not in ("classify", "affiliate", "propose", "clear_proposal", "propose_navigation"):
        return False
    required = {"id", "session", "epoch", "revision", "action"}
    if action == "propose_navigation":
        fields = command.keys() & {"course", "speed_kn"}
        if (not fields or not required <= command.keys()
                or command.keys() - required - fields
                or any(type(command[key]) is not str or not 0 < len(command[key]) <= 64
                       for key in ("id", "session"))
                or any(type(command[key]) is not int or not 0 <= command[key] <= 2**53 - 1
                       for key in ("epoch", "revision"))):
            return False
        # Bounds also reject nonfinite floats without converting hostile large ints.
        return all(type(command[key]) in (int, float) and
                   (0 <= command[key] < 360 if key == "course"
                    else 0 <= command[key] <= SHIP_SPEED_MAX_KN) for key in fields)
    if action != "clear_proposal":
        required.add("track")
    if action in ("classify", "affiliate"):
        required.add("value")
    allowed = required | ({"track"} if action == "clear_proposal" else set())
    if not required <= command.keys() or command.keys() - allowed:
        return False
    for key in ("id", "session", "track"):
        if key in command and (not isinstance(command[key], str)
                               or len(command[key]) > 64):
            return False
    for key in ("epoch", "revision"):
        if type(command[key]) is not int or command[key] < 0:
            return False
    return "value" not in command or command["value"] is None or isinstance(command["value"], str)


class CommanderServer:
    """Thread-safe byte snapshots and leased commands, with explicit lifecycle.

    ``address`` is available only while started. ``publish(..., chart=None)``
    retains the previous chart. Command timestamps use ``time.monotonic()``.
    Pairing codes are case-sensitive DDDLLL (ASCII digits/uppercase letters),
    remain stable for this server object, and allow five misses per rolling
    minute across all clients. A security lockout or explicit new-session
    ``revoke()`` rotates the code; ordinary stop/start and pairing do not.
    Starting requires the three packaged ``data.commander`` assets.
    """

    def __init__(self, translations=None, contact_analysis_assets=None):
        self._lock = threading.RLock()
        self._lifecycle = threading.Lock()
        self._http = None
        self._thread = None
        self._running = False
        self._code_index = None
        self._rotate_code_locked()
        self._pair_failures = deque()
        self._token = None
        self._sessions_v2 = {}
        self._next_v2_ordinal = 0
        self._station_generations = {station: 0 for station in STATIONS}
        self._lease = 0
        self._last_get = 0.0
        self._commands = deque()
        self._sonar_audio = deque(maxlen=2)
        self._sonar_audio_context = None
        self._sonar_audio_sequence = 0
        self._snapshot = b"{}"
        self._chart = b"{}"
        self._simlog = b"[]"
        unpublished = dict(protocol=2, version="", session="unpublished", epoch=0,
                           revision=0, seq=0, phase="blocked", role=None,
                           chart_revision="unpublished")
        empty_chart = dict(protocol=2, revision="unpublished", size_nm=500,
                           landmasses=[], disclaimer="")
        self._v2_states = {role: _json_bytes(unpublished)
                           for role in (None, *STATIONS)}
        self._v2_charts = {role: _json_bytes(empty_chart)
                           for role in (None, *STATIONS)}
        supplied = {} if contact_analysis_assets is None else contact_analysis_assets
        if not isinstance(supplied, dict) or len(supplied) > _MAX_PREBUILT_ROUTES:
            raise ValueError("invalid prebuilt Commander assets")
        prebuilt = {}
        total = 0
        for route, value in supplied.items():
            if (not isinstance(route, str) or not isinstance(value, tuple)
                    or len(value) != 2):
                raise ValueError("invalid prebuilt Commander asset")
            content_type, body = value
            valid_route = (route == "/api/v1/contacts"
                           and content_type == "application/json; charset=utf-8") or (
                               _CONTACT_ASSET_ROUTE(route) is not None
                               and ".." not in route
                               and content_type == "image/png")
            if (not valid_route or type(body) is not bytes
                    or not body or len(body) > _MAX_PREBUILT_FILE_BYTES):
                raise ValueError("invalid prebuilt Commander asset")
            total += len(body)
            if total > _MAX_PREBUILT_BYTES:
                raise ValueError("prebuilt Commander asset size limit exceeded")
            prebuilt[route] = (content_type, body)
        if prebuilt and "/api/v1/contacts" not in prebuilt:
            raise ValueError("contact projection route required")
        self._prebuilt_assets = prebuilt
        translations = translations or {}
        self._translations = {
            lang: _json_bytes({key: value for key, value in translations.get(lang, {}).items()
                               if isinstance(key, str) and key.startswith("commander.web.")
                               and isinstance(value, str)})
            for lang in ("en", "de")
        }

    def start(self, host: str, port: int = 8765):
        """Bind only an explicit RFC1918 or loopback IPv4 address (port 0 allowed)."""
        if not isinstance(host, str):
            raise ValueError("explicit private or loopback IPv4 required")
        address = ipaddress.IPv4Address(host)
        if not (address.is_loopback or any(address in ipaddress.IPv4Network(network)
                for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))):
            raise ValueError("explicit private or loopback IPv4 required")
        if type(port) is not int or (port != 0 and not 1024 <= port <= 65535):
            raise ValueError("invalid port")
        with self._lifecycle:
            with self._lock:
                if self._running:
                    raise RuntimeError("Commander server already started")
            root = resources.files("data.commander")
            assets = {
                route: (content_type, root.joinpath(name).read_bytes())
                for route, name, content_type in (
                    ("/", "index.html", "text/html; charset=utf-8"),
                    ("/app.js", "app.js", "text/javascript; charset=utf-8"),
                    ("/style.css", "style.css", "text/css; charset=utf-8"),
                )
            }
            if assets.keys() & self._prebuilt_assets.keys():
                raise ValueError("duplicate Commander asset route")
            assets.update(self._prebuilt_assets)
            http = _HTTPServer((str(address), port), self, assets)
            thread = threading.Thread(target=http.serve_forever,
                                      kwargs={"poll_interval": 0.05},
                                      name="commander-listener", daemon=True)
            with self._lock:
                self._http = http
                self._thread = thread
                self._running = True
            try:
                thread.start()
            except BaseException:
                with self._lock:
                    self._running = False
                    self._http = self._thread = None
                http.server_close()
                raise

    def stop(self):
        """Revoke access, close active sockets, and join within a bounded interval."""
        with self._lifecycle:
            with self._lock:
                http, thread = self._http, self._thread
                self._running = False
                self._http = self._thread = None
                self._revoke_locked()
            if http is not None:
                http.shutdown()
                http.server_close()
                with http.work_lock:
                    workers = list(http.workers.items())
                for worker, connection in workers:
                    http._interrupt_connection(connection)
                    connection.close()
                deadline = time.monotonic() + 2.0
                for worker, _ in workers:
                    worker.join(max(0.0, deadline - time.monotonic()))
                thread.join(max(0.0, deadline - time.monotonic()))

    @property
    def address(self) -> tuple[str, int]:
        with self._lock:
            if self._http is None:
                raise RuntimeError("Commander server is not started")
            return self._http.server_address

    @property
    def pairing_code(self) -> str:
        with self._lock:
            self._expire_locked()
            return self._code

    @property
    def connected(self) -> bool:
        with self._lock:
            self._expire_locked()
            return self._running and self._token is not None

    @property
    def lease_generation(self) -> int:
        """Read-only authorization generation, including any elapsed lease expiry."""
        with self._lock:
            self._expire_locked()
            return self._lease

    def _rotate_code_locked(self):
        # Draw uniformly from the entire format space except the predecessor,
        # skipping its index instead of retrying a possible collision.
        index = secrets.randbelow(1000 * 26**3 - (self._code_index is not None))
        if self._code_index is not None and index >= self._code_index:
            index += 1
        self._code_index = index
        digits, letters = divmod(index, 26**3)
        self._code = f"{digits:03d}" + "".join(
            chr(65 + letters // divisor % 26) for divisor in (26**2, 26, 1))

    def _revoke_locked(self, *, rotate_code=False):
        self._clear_sonar_audio_locked()
        self._token = None
        for session in self._sessions_v2.values():
            self._clear_session_authority_locked(session, "session_revoked")
        self._sessions_v2.clear()
        self._lease += 1
        self._commands.clear()
        if rotate_code:
            self._rotate_code_locked()

    def _clear_sonar_audio_locked(self):
        self._sonar_audio.clear()
        self._sonar_audio_context = None
        self._sonar_audio_sequence = 0

    @staticmethod
    def _station_grants(station=None):
        return {
            "command": station in STATIONS,
            "direct_fire": False,
            "sonar_audio": False,
        }

    def _set_active_station_locked(self, session, station, reason="active_station_changed"):
        if station is not None and station not in session["leases"]:
            return False
        if session["active_station"] == station:
            return True
        if "sonar" in (session["active_station"], station):
            self._clear_sonar_audio_locked()
        session["active_station"] = station
        session["active_generation"] += 1
        session["held_commands"].clear()
        return True

    def _reject_station_commands_locked(self, session, station, reason):
        retained = deque()
        while session["command_queue"]:
            envelope = session["command_queue"].popleft()
            if envelope.role == station:
                self._finish_v2_locked(session, envelope, "rejected", reason)
            else:
                retained.append(envelope)
        session["command_queue"].extend(retained)
        session["held_commands"].clear()

    def _release_station_locked(self, session, station, reason="role_revoked"):
        lease = session["leases"].get(station)
        if lease is None:
            session["requests"].pop(station, None)
            return False
        self._reject_station_commands_locked(session, station, reason)
        if station == "sonar":
            self._clear_sonar_audio_locked()
        del session["leases"][station]
        session["requests"].pop(station, None)
        self._station_generations[station] += 1
        if session["active_station"] == station:
            replacement = next((item for item in STATIONS if item in session["leases"]), None)
            self._set_active_station_locked(session, replacement, reason)
        return True

    def _clear_session_authority_locked(self, session, reason="session_revoked"):
        for station in tuple(STATIONS):
            if station in session["leases"]:
                self._release_station_locked(session, station, reason)
        session["requests"].clear()
        session["simlog"] = False
        session["held_commands"].clear()

    @staticmethod
    def _trim_command_history_locked(session):
        history = session["command_ids"]
        while len(history) > _V2_COMMAND_HISTORY_LIMIT:
            key = next((key for key, entry in history.items()
                        if entry[1] is not None), None)
            if key is None:
                break
            del history[key]

    @staticmethod
    def _pending_command_count_locked(session):
        return sum(entry[1] is None for entry in session["command_ids"].values())

    def _finish_v2_locked(self, session, envelope, status, reason):
        entry = session["command_ids"].get(envelope.command_id)
        if entry is None or entry[0] != envelope.body_bytes or entry[1] is not None:
            return False
        result = {"id": envelope.command_id, "seq": envelope.seq,
                  "status": status, "reasoncode": reason}
        session["command_ids"][envelope.command_id] = (entry[0], result)
        session["command_results"].append(result)
        self._trim_command_history_locked(session)
        return True

    def _reject_session_commands_locked(self, session, reason):
        queue = session["command_queue"]
        while queue:
            self._finish_v2_locked(session, queue.popleft(), "rejected", reason)
        session["held_commands"].clear()

    def _reject_direct_fire_commands_locked(self, session, station):
        retained = deque()
        while session["command_queue"]:
            envelope = session["command_queue"].popleft()
            try:
                spec = V2_ACTION_REGISTRY.get(envelope.body().get("action"))
            except (UnicodeDecodeError, ValueError, TypeError):
                spec = None
            if envelope.role == station and spec is not None and spec.direct_fire:
                self._finish_v2_locked(
                    session, envelope, "rejected", "direct_fire_unavailable")
            else:
                retained.append(envelope)
        session["command_queue"].extend(retained)

    def _session_by_client_locked(self, client_id):
        return next((session for session in self._sessions_v2.values()
                     if session["client_id"] == client_id), None)

    def _expire_locked(self):
        now = time.monotonic()
        while self._pair_failures and now - self._pair_failures[0] >= 60.0:
            self._pair_failures.popleft()
        for digest, session in tuple(self._sessions_v2.items()):
            if now - session["last_get"] >= _V2_SESSION_IDLE_S:
                self._clear_session_authority_locked(session)
                del self._sessions_v2[digest]
            elif session["leases"] and now - session["presence"] >= _V2_STATION_LEASE_S:
                self._clear_session_authority_locked(session, "role_revoked")
        if self._token is not None and now - self._last_get >= 30.0:
            self._revoke_locked()

    def revoke(self):
        """Begin a new game/server security session and rotate its join code."""
        with self._lock:
            self._revoke_locked(rotate_code=True)
            self._pair_failures.clear()

    def client_statuses(self) -> list[dict]:
        """Return a detached, deterministic local-host roster."""
        with self._lock:
            self._expire_locked()
            station_order = {station: index for index, station in enumerate(STATIONS)}
            sessions = sorted(
                self._sessions_v2.values(),
                key=lambda session: (
                    station_order.get(session["active_station"], len(STATIONS)),
                    session["ordinal"],
                ),
            )
            return [{
                "client_id": session["client_id"],
                "name": session["name"],
                "ordinal": session["ordinal"],
                "active_station": session["active_station"],
                "active_generation": session["active_generation"],
                "simlog": session["simlog"],
                "stations": {
                    station: {
                        "leased": station in session["leases"],
                        "requested": station in session["requests"],
                        "station_generation": (session["leases"][station]["generation"]
                                               if station in session["leases"] else None),
                        "request_generation": session["requests"].get(station, 0),
                        "grants": (dict(session["leases"][station]["grants"])
                                   if station in session["leases"]
                                   else self._station_grants()),
                    } for station in STATIONS
                },
                "presence": session["presence"],
            } for session in sessions]

    def station_leased(self, station: str) -> bool:
        """Return whether a v2 client currently owns this station."""
        if station not in STATIONS:
            raise ValueError("invalid station")
        with self._lock:
            self._expire_locked()
            return any(station in session["leases"]
                       for session in self._sessions_v2.values())

    def grant_station(self, client_id, station) -> bool:
        if not isinstance(client_id, str) or station not in STATIONS:
            raise ValueError("invalid client or station")
        with self._lock:
            self._expire_locked()
            session = self._session_by_client_locked(client_id)
            if session is None:
                return False
            holder = next((candidate for candidate in self._sessions_v2.values()
                           if station in candidate["leases"]), None)
            if holder is session:
                self._reject_station_commands_locked(session, station, "role_revoked")
                session["leases"][station]["grants"] = self._station_grants(station)
                session["requests"].pop(station, None)
                return True
            if holder is not None:
                self._release_station_locked(holder, station)
            else:
                self._station_generations[station] += 1
            session["leases"][station] = {
                "generation": self._station_generations[station],
                "grants": self._station_grants(station),
            }
            session["requests"].pop(station, None)
            if session["active_station"] is None:
                self._set_active_station_locked(session, station)
            return True

    def resolve_station_request(self, client_id, station, request_generation, grants=None) -> bool:
        """Atomically decide an exact pending request; never take over a lease."""
        capabilities = {"command", "direct_fire", "sonar_audio"}
        if (type(client_id) is not str or station not in STATIONS
                or type(request_generation) is not int
                or grants is not None and (type(grants) is not dict
                    or set(grants) != capabilities
                    or any(type(value) is not bool for value in grants.values()))):
            return False
        if grants is not None and (
                not grants["command"]
                or grants["direct_fire"] and station not in ("weapons", "helicopter", "opz")
                or grants["sonar_audio"] and station != "sonar"):
            return False
        with self._lock:
            self._expire_locked()
            session = self._session_by_client_locked(client_id)
            if session is None or session["requests"].get(station) != request_generation:
                return False
            if grants is None:
                del session["requests"][station]
                return True
            if any(station in item["leases"] for item in self._sessions_v2.values()):
                return False
            self._station_generations[station] += 1
            session["leases"][station] = {
                "generation": self._station_generations[station],
                "grants": dict(grants),
            }
            del session["requests"][station]
            self._set_active_station_locked(session, station)
            return True

    def reject_station_request(self, client_id, station=None, request_generation=None) -> bool:
        if (not isinstance(client_id, str) or station is not None and station not in STATIONS
                or request_generation is not None and type(request_generation) is not int):
            raise ValueError("invalid client")
        with self._lock:
            self._expire_locked()
            session = self._session_by_client_locked(client_id)
            if session is None:
                return False
            if station is None:
                station = next((item for item in STATIONS if item in session["requests"]), None)
            if station is None or station not in session["requests"]:
                return False
            if (request_generation is not None
                    and session["requests"][station] != request_generation):
                return False
            del session["requests"][station]
            return True

    def revoke_station(self, station) -> bool:
        if station not in STATIONS:
            raise ValueError("invalid station")
        with self._lock:
            self._expire_locked()
            holder = next((session for session in self._sessions_v2.values()
                           if station in session["leases"]), None)
            if holder is None:
                return False
            self._release_station_locked(holder, station)
            return True

    def revoke_client(self, client_id) -> bool:
        if not isinstance(client_id, str):
            raise ValueError("invalid client")
        with self._lock:
            self._expire_locked()
            for digest, session in tuple(self._sessions_v2.items()):
                if session["client_id"] == client_id:
                    self._clear_session_authority_locked(session)
                    del self._sessions_v2[digest]
                    return True
            return False

    def set_client_grant(self, client_id, *args) -> bool:
        """Set a station grant, or the session-wide SimLog grant.

        The explicit form is ``(client_id, station, capability, enabled)``. The
        legacy host-call form infers the active station and remains accepted so
        existing local integrations do not gain authority accidentally.
        """
        explicit_station = len(args) == 3
        if len(args) == 2:
            station, capability, enabled = None, *args
        elif len(args) == 3:
            station, capability, enabled = args
        else:
            raise ValueError("invalid client grant")
        if (not isinstance(client_id, str)
                or capability not in (*_V2_STATION_CAPABILITIES, "simlog")
                or type(enabled) is not bool):
            raise ValueError("invalid client grant")
        with self._lock:
            self._expire_locked()
            session = self._session_by_client_locked(client_id)
            if session is None:
                return False
            if capability == "simlog":
                session["simlog"] = enabled
                return True
            station = session["active_station"] if station is None else station
            if station not in STATIONS:
                if explicit_station:
                    raise ValueError("invalid client grant")
                return False
            lease = session["leases"].get(station)
            if lease is None:
                return False
            if capability == "direct_fire" and enabled and (
                    not lease["grants"]["command"]
                    or station not in ("weapons", "helicopter", "opz")):
                return False
            if capability == "sonar_audio" and enabled and station != "sonar":
                return False
            lease["grants"][capability] = enabled
            if capability == "command" and not enabled:
                lease["grants"]["direct_fire"] = False
                self._reject_station_commands_locked(session, station, "grant_revoked")
            elif capability == "direct_fire" and not enabled:
                self._reject_direct_fire_commands_locked(session, station)
            elif capability == "sonar_audio" and not enabled:
                self._clear_sonar_audio_locked()
            return True

    def activate_station(self, client_id, station, station_generation) -> bool:
        if (not isinstance(client_id, str) or station not in STATIONS
                or type(station_generation) is not int):
            raise ValueError("invalid station activation")
        with self._lock:
            self._expire_locked()
            session = self._session_by_client_locked(client_id)
            lease = None if session is None else session["leases"].get(station)
            if lease is None or lease["generation"] != station_generation:
                return False
            return self._set_active_station_locked(session, station)

    def revoke_all(self):
        """Release every v2 role and grant while retaining authenticated clients."""
        with self._lock:
            self._expire_locked()
            for session in self._sessions_v2.values():
                self._clear_session_authority_locked(session, "role_revoked")

    def invalidate_v2_commands(self, reason="context_invalidated"):
        """Reject all queued v2 input and clear future held-control state."""
        if type(reason) is not str or not reason:
            raise ValueError("invalid command invalidation reason")
        with self._lock:
            for session in self._sessions_v2.values():
                self._reject_session_commands_locked(session, reason)

    def drain_commands_v2(self) -> list[V2CommandEnvelope]:
        """Detach one deterministic frame batch in station/client/FIFO order."""
        with self._lock:
            self._expire_locked()
            order = {station: index for index, station in enumerate(STATIONS)}
            result = []
            for session in self._sessions_v2.values():
                result.extend(session["command_queue"])
                session["command_queue"].clear()
            return sorted(result, key=lambda envelope: (
                order[envelope.role], envelope.client_ordinal, envelope.seq))

    def apply_command_v2(self, envelope, *, now, phase, world_session,
                         world_epoch, resource_revision, apply):
        """Revalidate and complete one command atomically on the caller's thread."""
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError("v2 commands require the main thread")
        if type(envelope) is not V2CommandEnvelope or not callable(apply):
            raise ValueError("invalid v2 command application")
        reason = "invalid_schema"
        with self._lock:
            self._expire_locked()
            session = self._sessions_v2.get(envelope.session_digest)
            body = envelope.body()
            spec = V2_ACTION_REGISTRY.get(body.get("action"))
            if (session is None or session.get("client_id") != envelope.client_id
                    or session.get("ordinal") != envelope.client_ordinal):
                return False
            if not _v2_command_valid(body) or spec is None:
                reason = "invalid_schema"
            elif (envelope.role not in session["leases"]
                  or body["station"] != envelope.role):
                reason = "role_revoked"
            elif (session["leases"][envelope.role]["generation"] != envelope.lease_generation
                  or body["station_generation"] != envelope.lease_generation):
                reason = "stale_generation"
            elif body["active_generation"] != envelope.active_generation:
                reason = "stale_active_generation"
            elif spec.direct_fire and (
                    not session["leases"][envelope.role]["grants"]["command"]
                    or not session["leases"][envelope.role]["grants"]["direct_fire"]
                    or type(now) not in (int, float) or not math.isfinite(now)
                    or not 0 <= now - envelope.received_at <= 1.0
                    or type(session.get("presence")) not in (int, float)
                    or not 0 <= now - session["presence"] <= 2.0):
                reason = "direct_fire_unavailable"
            elif not session["leases"][envelope.role]["grants"]["command"]:
                reason = "grant_revoked"
            elif (type(now) not in (int, float) or not math.isfinite(now)
                  or not 0 <= now - envelope.received_at <= _V2_COMMAND_MAX_AGE_S):
                reason = "expired"
            elif phase != "live":
                reason = "phase_blocked"
            elif body["world_session"] != world_session:
                reason = "stale_world_session"
            elif body["world_epoch"] != world_epoch:
                reason = "stale_world_epoch"
            elif body["resource_revision"] != resource_revision:
                reason = "revision_conflict"
            else:
                try:
                    applied = apply(body["action"], dict(body["params"]))
                except Exception:
                    applied = False
                reason = ("ok" if applied is True or applied == "ok" else applied
                          if type(applied) is str and applied in {
                              "bridge_down", "sonar_down", "opz_down",
                              "engine_down", "radio_down", "flightdeck_down",
                              "invalid_value", "phase_blocked", "unknown_ref",
                              "stale_ref", "source_owned", "fusion_rejected",
                               "not_ready", "no_solution", "no_buoys",
                               "water_required", "tas_fault", "invalid_target",
                               "roe_blocked", "not_located", "not_classified",
                               "salvo_limit", "empty", "no_tube",
                               "weapons_down", "weapons_degraded", "out_of_range",
                                "opz_degraded", "active_limit", "no_fuel",
                                "weather_unsafe"}
                          else "action_rejected")
            return self._finish_v2_locked(
                session, envelope, "applied" if reason == "ok" else "rejected", reason)

    def publish(self, snapshot: dict, chart: dict | None = None):
        if not isinstance(snapshot, dict) or (chart is not None and not isinstance(chart, dict)):
            raise TypeError("snapshot and chart must be dictionaries")
        snapshot_bytes = _json_bytes(snapshot)
        chart_bytes = None if chart is None else _json_bytes(chart)
        with self._lock:
            self._snapshot = snapshot_bytes
            if chart_bytes is not None:
                self._chart = chart_bytes

    def publish_v2(self, states: dict, charts: dict):
        """Atomically replace immutable, role-keyed protocol-v2 publications."""
        expected = {None, *STATIONS}
        status_fields = {"protocol", "version", "session", "epoch", "revision",
                         "seq", "phase", "role", "chart_revision"}
        assigned_fields = status_fields | {"clock", "environment", "mission",
                                           "autocrew"}
        if (not isinstance(states, dict) or not isinstance(charts, dict)
                or set(states) != expected or set(charts) != expected):
            raise ValueError("invalid v2 publication")
        encoded_states, encoded_charts = {}, {}
        for role in (None, *STATIONS):
            state, chart = states[role], charts[role]
            redacted = state == states[None] and chart == charts[None]
            if (not isinstance(state, dict) or not isinstance(chart, dict)
                    or state.get("protocol") != 2
                    or (role is None and (state.get("role") is not None
                                         or set(state) != status_fields))
                    or (role is not None and not redacted
                        and (state.get("role") != role
                             or set(state) != assigned_fields | {role}))
                    or (role is not None and state.get("role") is None and not redacted)
                    or chart.get("protocol") != 2
                    or state.get("chart_revision") != chart.get("revision")):
                raise ValueError("invalid v2 publication")
            try:
                state_bytes, chart_bytes = _json_bytes(state), _json_bytes(chart)
            except (TypeError, ValueError, OverflowError):
                raise ValueError("invalid v2 publication") from None
            if len(state_bytes) > STATE_MAX_BYTES or len(chart_bytes) > CHART_MAX_BYTES:
                raise ValueError("v2 publication size limit exceeded")
            encoded_states[role], encoded_charts[role] = state_bytes, chart_bytes
        with self._lock:
            self._v2_states = encoded_states
            self._v2_charts = encoded_charts

    def clear_sonar_audio(self):
        """Clear every live-audio byte and context without touching a session."""
        with self._lock:
            self._clear_sonar_audio_locked()

    def prepare_sonar_audio(self, *, world_session: str, world_epoch: int):
        """Bind an empty stream to the current granted sonar holder."""
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError("sonar audio preparation requires the main thread")
        if (type(world_session) is not str or not world_session
                or type(world_epoch) is not int or world_epoch < 0):
            raise ValueError("invalid sonar audio context")
        with self._lock:
            self._expire_locked()
            holder = next(((digest, session) for digest, session
                           in self._sessions_v2.items()
                           if "sonar" in session["leases"]
                           and session["active_station"] == "sonar"), None)
            if (holder is None
                    or not holder[1]["leases"]["sonar"]["grants"]["sonar_audio"]):
                self._clear_sonar_audio_locked()
                return None
            generation = holder[1]["leases"]["sonar"]["generation"]
            context = (holder[0], generation, holder[1]["active_generation"],
                       world_session, world_epoch)
            if context != self._sonar_audio_context:
                self._clear_sonar_audio_locked()
                self._sonar_audio_context = context
            return generation

    def publish_sonar_audio(self, pcm: bytes, *, world_session: str,
                            world_epoch: int, station_generation: int):
        """Publish one immutable receiver block from the main thread only."""
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError("sonar audio publication requires the main thread")
        if (type(pcm) is not bytes or len(pcm) != SONAR_AUDIO_BYTES
                or type(world_session) is not str or not world_session
                or type(world_epoch) is not int or world_epoch < 0
                or type(station_generation) is not int or station_generation < 0):
            raise ValueError("invalid sonar audio publication")
        with self._lock:
            self._expire_locked()
            holder = next(((digest, session) for digest, session
                           in self._sessions_v2.items()
                           if "sonar" in session["leases"]
                           and session["active_station"] == "sonar"), None)
            if holder is None:
                self._clear_sonar_audio_locked()
                return False
            context = (holder[0], station_generation,
                       holder[1]["active_generation"], world_session, world_epoch)
            if (not holder[1]["leases"]["sonar"]["grants"]["sonar_audio"]
                    or holder[1]["leases"]["sonar"]["generation"] != station_generation
                    or context != self._sonar_audio_context):
                self._clear_sonar_audio_locked()
                return False
            if self._sonar_audio_sequence >= _SAFE_INTEGER_MAX:
                self._clear_sonar_audio_locked()
                self._sonar_audio_context = context
            self._sonar_audio_sequence += 1
            self._sonar_audio.append((self._sonar_audio_sequence, pcm))
            return True

    def publish_simlog(self, payload: bytes):
        """Cache the bounded simulation-log payload (JSON array of objects)."""
        if type(payload) is not bytes or len(payload) > SIMLOG_MAX_BYTES:
            raise ValueError("invalid simlog payload")
        try:
            rows = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ValueError("invalid simlog payload") from None
        if not isinstance(rows, list) or not all(type(row) is dict
                                                 for row in rows):
            raise ValueError("invalid simlog payload")
        with self._lock:
            self._simlog = payload

    def drain_commands(self, limit=4) -> list:
        """Drain FIFO, including aged commands for explicit is_current rejection."""
        if type(limit) is not int or limit < 0:
            raise ValueError("limit must be a nonnegative integer")
        with self._lock:
            self._expire_locked()
            return [self._commands.popleft() for _ in range(min(limit, len(self._commands)))]

    def is_current(self, envelope) -> bool:
        with self._lock:
            self._expire_locked()
            if not isinstance(envelope, dict):
                return False
            stamp = envelope.get("received_at")
            return (self._running and self._token is not None
                    and type(envelope.get("lease")) is int
                    and envelope["lease"] == self._lease
                    and type(stamp) in (int, float)
                    and 0.0 <= time.monotonic() - stamp <= 5.0)


class _HTTPServer(HTTPServer):
    allow_reuse_address = True
    request_queue_size = 4

    def __init__(self, address, owner, assets):
        self.owner = owner
        self.assets = assets
        self.slots = threading.BoundedSemaphore(4)
        self.work_lock = threading.Lock()
        self.workers = {}
        super().__init__(address, _Handler)
        host, port = self.server_address
        self.hosts = {f"{host}:{port}"}
        if ipaddress.IPv4Address(host).is_loopback:
            self.hosts.add(f"localhost:{port}")

    def process_request(self, request, client_address):
        deadline = time.monotonic() + _CONNECTION_DEADLINE_S
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        request.settimeout(1.5)
        worker = threading.Thread(target=self._work, args=(request, client_address, deadline),
                                  name="commander-request", daemon=True)
        with self.work_lock:
            self.workers[worker] = request
        try:
            worker.start()
        except BaseException:
            with self.work_lock:
                self.workers.pop(worker)
            self.slots.release()
            self.shutdown_request(request)
            raise

    @staticmethod
    def _interrupt_connection(request):
        try:
            request.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def _work(self, request, client_address, deadline):
        # A socket inactivity timeout alone can be extended forever by trickled
        # bytes, including inside buffered readline/read calls. Interrupt all I/O
        # at the absolute deadline; keep the worker slot until its timer is joined.
        timer = threading.Timer(max(0.0, deadline - time.monotonic()),
                                self._interrupt_connection, args=(request,))
        timer.name = "commander-deadline"
        timer.daemon = True
        try:
            timer.start()
            self.finish_request(request, client_address)
        except (OSError, ValueError, RuntimeError):
            pass
        finally:
            timer.cancel()
            if timer.ident is not None:
                timer.join()
            self.shutdown_request(request)
            with self.work_lock:
                self.workers.pop(threading.current_thread(), None)
            self.slots.release()

    def handle_error(self, request, client_address):
        # Never include request data, credentials, or client addresses in logs.
        pass


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        pass

    def send_error(self, code, message=None, explain=None):
        self._reply(code, {"error": "invalid_request"})

    def _reply(self, status, value, content_type="application/json; charset=utf-8",
               set_cookie=None):
        body = value if isinstance(value, bytes) else _json_bytes(value)
        self.send_response_only(status)
        for key, value in (
            ("Content-Type", content_type), ("Content-Length", str(len(body))),
            ("Connection", "close"), ("Cache-Control", "no-store"),
            ("X-Content-Type-Options", "nosniff"), ("X-Frame-Options", "DENY"),
            ("Referrer-Policy", "no-referrer"),
            ("Permissions-Policy", "camera=(), microphone=(), geolocation=()"),
            ("Content-Security-Policy", "default-src 'none'; script-src 'self'; "
             "style-src 'self'; img-src 'self'; connect-src 'self'; "
             "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"),
        ):
            self.send_header(key, value)
        if set_cookie is not None:
            self.send_header("Set-Cookie", set_cookie)
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def _sonar_audio_reply(self, status, body=b"", *, sequence=None,
                           discontinuity=False):
        self.send_response_only(status)
        if status == 200:
            self.send_header("Content-Type", "audio/pcm")
            self.send_header("X-U-Jagd-PCM", "s16le")
            self.send_header("X-U-Jagd-Sample-Rate", str(SONAR_AUDIO_RATE))
            self.send_header("X-U-Jagd-Audio-Frames", str(SONAR_AUDIO_FRAMES))
            self.send_header("X-U-Jagd-Audio-Sequence", str(sequence))
            self.send_header("X-U-Jagd-Audio-Discontinuity",
                             "1" if discontinuity else "0")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if body:
            self.wfile.write(body)
        self.close_connection = True

    def handle_one_request(self):
        # Bound the raw parser input, including aggregate headers, before the
        # standard library parses it. One request per connection avoids framing
        # disagreements and keeps shutdown and worker ownership simple.
        self.close_connection = True
        self.request_version = "HTTP/1.1"
        self.command = None
        self.requestline = ""
        received_at = time.monotonic()
        self.raw_requestline = self.rfile.readline(1153)
        if not self.raw_requestline:
            return
        parts = self.raw_requestline.split(b" ")
        if (len(self.raw_requestline) > 1152 or len(parts) != 3
                or not self.raw_requestline.endswith(b"\r\n")
                or parts[2] not in (b"HTTP/1.0\r\n", b"HTTP/1.1\r\n")
                or len(parts[1]) > 1024 or not parts[1].startswith(b"/")
                or parts[1].startswith(b"//")
                or any(c < 33 or c > 126 for c in parts[0] + parts[1])):
            self.send_error(400)
            return
        headers = bytearray()
        for _ in range(65):
            line = self.rfile.readline(8193)
            headers.extend(line)
            if len(headers) > 8192:
                self.send_error(431)
                return
            if line == b"\r\n":
                break
            name, separator, value = line.partition(b":")
            if (not line.endswith(b"\r\n") or not separator or not name
                    or any(c not in b"!#$%&'*+-.^_`|~0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
                           for c in name)
                    or any(c < 32 or c > 126 for c in value[:-2])):
                self.send_error(400)
                return
        else:
            self.send_error(431)
            return
        stream = self.rfile
        self.rfile = io.BytesIO(headers)
        try:
            if not self.parse_request():
                return
        finally:
            self.rfile = stream
        self.close_connection = True
        for name in ("Host", "Origin", "Content-Length", "Content-Type", "Authorization",
                     "Cookie", "X-U-Jagd-CSRF"):
            if len(self.headers.get_all(name, [])) > 1:
                self.send_error(400)
                return
        host = self.headers.get("Host")
        origin = self.headers.get("Origin")
        if host not in self.server.hosts:
            self.send_error(403)
            return
        if (origin is not None and origin != f"http://{host}") or (self.command == "POST" and origin is None):
            self.send_error(403)
            return
        if "Transfer-Encoding" in self.headers or "Expect" in self.headers:
            self.send_error(400)
            return
        if self.command not in ("GET", "POST"):
            self.send_error(405)
            return
        length = self.headers.get("Content-Length", "0")
        if not length.isascii() or not length.isdecimal() or len(length) > 10:
            self.send_error(400)
            return
        length = int(length)
        if length > 4096:
            self.send_error(413)
            return
        if self.command == "GET":
            if length:
                self.send_error(400)
                return
            self._get()
            return
        if self.path == "/api/v2/logout" and length == 0:
            self._post(None, received_at)
            return
        if self.headers.get("Content-Type", "").lower() != "application/json":
            self.send_error(415)
            return
        if "Content-Length" not in self.headers or length == 0:
            self.send_error(400)
            return
        raw = self.rfile.read(length)
        try:
            if len(raw) != length:
                raise ValueError("incomplete body")
            body = json.loads(raw.decode("utf-8"), object_pairs_hook=_object,
                              parse_float=_number, parse_constant=_number)
        except (ValueError, RecursionError):
            self.send_error(400)
            return
        self._post(body, received_at)

    def handle_expect_100(self):
        self.send_error(400)
        return False

    def _authenticated_locked(self, renew=False):
        owner = self.server.owner
        owner._expire_locked()
        supplied = self.headers.get("Authorization", "")
        if (not owner._running or owner._token is None
                or not secrets.compare_digest(supplied.encode("utf-8"),
                                              f"Bearer {owner._token}".encode("ascii"))):
            return False
        if renew:
            owner._last_get = time.monotonic()
        return True

    @staticmethod
    def _session_v2_body(session, sessions):
        occupied = {station: candidate for candidate in sessions.values()
                    for station in candidate["leases"]}
        active = session["active_station"]
        active_lease = session["leases"].get(active)
        requested = next((station for station in STATIONS
                          if station in session["requests"]), None)
        active_grants = (CommanderServer._station_grants() if active_lease is None
                         else dict(active_lease["grants"]))
        return {
            "protocol": 2,
            "client_id": session["client_id"],
            "name": session["name"],
            "csrf": session["csrf"],
            "ordinal": session["ordinal"],
            "active_station": session["active_station"],
            "active_generation": session["active_generation"],
            # Active-role aliases keep the existing v2 shell usable until its
            # multi-station switcher consumes the nested records below.
            "station": active,
            "requested_station": requested,
            "station_generation": (0 if active_lease is None
                                   else active_lease["generation"]),
            "next_command_seq": session["last_command_seq"] + 1,
            "simlog": session["simlog"],
            "grants": dict(active_grants, simlog=session["simlog"]),
            "presence": session["presence"],
            "stations": {
                station: {
                    "status": ("available" if station not in occupied else
                               "mine" if occupied[station] is session else "occupied"),
                    "requested": station in session["requests"],
                    "request_generation": session["requests"].get(station, 0),
                    "station_generation": (session["leases"][station]["generation"]
                                           if station in session["leases"] else None),
                    "grants": (dict(session["leases"][station]["grants"])
                               if station in session["leases"] else
                               CommanderServer._station_grants()),
                }
                for station in STATIONS
            },
        }

    def _cookie_v2(self):
        raw = self.headers.get("Cookie")
        if raw is None:
            return None, False
        values = []
        for part in raw.split(";"):
            part = part.strip()
            name, separator, value = part.partition("=")
            if (not separator or _COOKIE_NAME(name) is None
                    or _COOKIE_VALUE(value) is None):
                raise ValueError("malformed cookie")
            if name == _V2_COOKIE:
                values.append(value)
        if len(values) > 1:
            raise ValueError("ambiguous session cookie")
        return (values[0] if values else None), bool(values)

    def _authenticated_v2_locked(self, renew=False):
        token, presented = self._cookie_v2()
        owner = self.server.owner
        owner._expire_locked()
        if token is None or not owner._running:
            return None, None, presented
        digest = hashlib.sha256(token.encode("ascii")).digest()
        session = owner._sessions_v2.get(digest)
        if session is None:
            return None, None, True
        if renew:
            session["last_get"] = time.monotonic()
        return session, digest, True

    @staticmethod
    def _v2_cookie(token):
        return f"{_V2_COOKIE}={token}; Path=/api/v2; HttpOnly; SameSite=Strict"

    @staticmethod
    def _clear_v2_cookie():
        return (f"{_V2_COOKIE}=; Path=/api/v2; HttpOnly; SameSite=Strict; "
                "Max-Age=0")

    def _v2_unauthorized(self, presented):
        self._reply(401, {"error": "unauthorized"},
                    set_cookie=self._clear_v2_cookie() if presented else None)

    def _get(self):
        owner = self.server.owner
        if self.path in self.server.assets:
            content_type, body = self.server.assets[self.path]
            self._reply(200, body, content_type)
        elif self.path in ("/api/v1/ui?lang=en", "/api/v1/ui?lang=de"):
            self._reply(200, owner._translations[self.path[-2:]])
        elif self.path in ("/api/v1/state", "/api/v1/chart", "/api/v1/simlog"):
            with owner._lock:
                authenticated = self._authenticated_locked(renew=True)
                body = (owner._snapshot if self.path == "/api/v1/state"
                        else owner._simlog if self.path == "/api/v1/simlog"
                        else owner._chart)
            if authenticated:
                self._reply(200, body)
            else:
                self.send_error(401)
        elif self.path in ("/api/v2/session", "/api/v2/state", "/api/v2/chart",
                           "/api/v2/results", "/api/v2/simlog"):
            try:
                with owner._lock:
                    session, _, presented = self._authenticated_v2_locked(renew=True)
                    if session is not None and self.path == "/api/v2/session":
                        session["presence"] = time.monotonic()
                    role = session["active_station"] if session is not None else None
                    # The shared v1 log contains ground truth. Protocol v2 stays
                    # closed until it has per-role projected history.
                    body = (self._session_v2_body(session, owner._sessions_v2) if session is not None
                             and self.path == "/api/v2/session"
                            else _json_bytes({"protocol": 2, "results": [
                                dict(result) for result in session["command_results"]]})
                            if session is not None and self.path == "/api/v2/results"
                            else None if self.path == "/api/v2/simlog"
                             else owner._v2_states[role] if self.path == "/api/v2/state"
                            else owner._v2_charts[role] if self.path == "/api/v2/chart"
                            else None)
            except (UnicodeEncodeError, ValueError):
                self.send_error(400)
                return
            if session is not None and body is not None:
                self._reply(200, body)
            elif session is not None:
                self.send_error(403)
            else:
                self._v2_unauthorized(presented)
        else:
            self.send_error(404)

    def _post(self, body, received_at):
        owner = self.server.owner
        status, response = 404, {"error": "not_found"}
        audio_reply = None
        with owner._lock:
            owner._expire_locked()
            if self.path == "/api/v1/pair":
                if not owner._running:
                    status, response = 503, {"error": "unavailable"}
                elif owner._token is not None or owner._sessions_v2:
                    status, response = 409, {"error": "already_paired"}
                elif len(owner._pair_failures) >= 5:
                    status, response = 429, {"error": "pairing_rate_limited"}
                elif not isinstance(body, dict) or body.keys() != {"code"} or not isinstance(body["code"], str):
                    status, response = 400, {"error": "invalid_request"}
                elif not secrets.compare_digest(body["code"].encode("utf-8", errors="surrogatepass"),
                                                owner._code.encode("ascii")):
                    owner._pair_failures.append(time.monotonic())
                    if len(owner._pair_failures) == 5:
                        owner._rotate_code_locked()
                    status, response = 403, {"error": "invalid_code"}
                else:
                    owner._lease += 1
                    owner._token = secrets.token_urlsafe(32)
                    owner._last_get = time.monotonic()
                    status, response = 200, {"token": owner._token}
            elif self.path == "/api/v2/pair":
                if not owner._running:
                    status, response = 503, {"error": "unavailable"}
                elif owner._token is not None:
                    status, response = 409, {"error": "already_paired"}
                elif len(owner._pair_failures) >= 5:
                    status, response = 429, {"error": "pairing_rate_limited"}
                elif (not isinstance(body, dict) or body.keys() != {"code", "name"}
                      or not isinstance(body["code"], str)
                      or not isinstance(body["name"], str)):
                    status, response = 400, {"error": "invalid_request"}
                else:
                    name = body["name"].strip()
                    if (not 1 <= len(name) <= 32
                            or any(unicodedata.category(char).startswith("C") for char in name)):
                        status, response = 400, {"error": "invalid_request"}
                    elif len(owner._sessions_v2) >= _V2_SESSION_LIMIT:
                        status, response = 429, {"error": "session_limit"}
                    elif not secrets.compare_digest(
                            body["code"].encode("utf-8", errors="surrogatepass"),
                            owner._code.encode("ascii")):
                        owner._pair_failures.append(time.monotonic())
                        if len(owner._pair_failures) == 5:
                            owner._rotate_code_locked()
                        status, response = 403, {"error": "invalid_code"}
                    else:
                        token = secrets.token_urlsafe(32)
                        session = {
                            "client_id": secrets.token_urlsafe(18),
                            "name": name,
                            "csrf": secrets.token_urlsafe(32),
                            "ordinal": owner._next_v2_ordinal,
                            "requests": {},
                            "next_request_generation": 0,
                            "leases": {},
                            "active_station": None,
                            "active_generation": 0,
                            "simlog": False,
                            "presence": time.monotonic(),
                            "last_get": time.monotonic(),
                            "last_command_seq": -1,
                            "command_queue": deque(),
                            "command_ids": OrderedDict(),
                            "command_results": deque(maxlen=_V2_COMMAND_HISTORY_LIMIT),
                            "held_commands": {},
                        }
                        owner._next_v2_ordinal += 1
                        owner._sessions_v2[hashlib.sha256(token.encode("ascii")).digest()] = session
                        self._reply(200, self._session_v2_body(session, owner._sessions_v2),
                                    set_cookie=self._v2_cookie(token))
                        return
            elif self.path in ("/api/v2/stations/request", "/api/v2/stations/activate",
                               "/api/v2/stations/release"):
                try:
                    session, _, presented = self._authenticated_v2_locked(renew=True)
                except (UnicodeEncodeError, ValueError):
                    status, response = 400, {"error": "invalid_request"}
                else:
                    if session is None:
                        self._v2_unauthorized(presented)
                        return
                    csrf = self.headers.get("X-U-Jagd-CSRF")
                    if (csrf is None or not secrets.compare_digest(
                            csrf.encode("utf-8", errors="surrogatepass"),
                            session["csrf"].encode("ascii"))):
                        status, response = 403, {"error": "forbidden"}
                    elif self.path.endswith("/request"):
                        if (not isinstance(body, dict) or body.keys() != {"station"}
                                or body["station"] not in STATIONS):
                            status, response = 400, {"error": "invalid_request"}
                        else:
                            station = body["station"]
                            if station not in session["leases"] and station not in session["requests"]:
                                session["next_request_generation"] += 1
                                session["requests"][station] = session["next_request_generation"]
                            status = 200
                            response = self._session_v2_body(session, owner._sessions_v2)
                    elif (type(body) is not dict
                          or set(body) != {"station", "station_generation",
                                           "active_generation"}
                          or body["station"] not in STATIONS
                          or type(body["station_generation"]) is not int
                          or not 0 <= body["station_generation"] <= _SAFE_INTEGER_MAX
                          or type(body["active_generation"]) is not int
                          or not 0 <= body["active_generation"] <= _SAFE_INTEGER_MAX):
                        status, response = 400, {"error": "invalid_request"}
                    elif (body["station"] not in session["leases"]
                          or session["leases"][body["station"]]["generation"]
                          != body["station_generation"]):
                        status, response = 409, {"error": "stale_generation"}
                    elif self.path.endswith("/activate"):
                        owner._set_active_station_locked(session, body["station"])
                        status = 200
                        response = self._session_v2_body(session, owner._sessions_v2)
                    elif (body["active_generation"] != session["active_generation"]
                          or body["station"] != session["active_station"]):
                        status, response = 409, {"error": "stale_active_generation"}
                    else:
                        owner._release_station_locked(session, body["station"])
                        status = 200
                        response = self._session_v2_body(session, owner._sessions_v2)
            elif self.path == "/api/v2/logout":
                try:
                    session, digest, presented = self._authenticated_v2_locked(renew=True)
                except (UnicodeEncodeError, ValueError):
                    status, response = 400, {"error": "invalid_request"}
                else:
                    csrf = self.headers.get("X-U-Jagd-CSRF")
                    if session is None:
                        self._v2_unauthorized(presented)
                        return
                    if (body not in (None, {}) or csrf is None
                            or not secrets.compare_digest(
                                csrf.encode("utf-8", errors="surrogatepass"),
                                session["csrf"].encode("ascii"))):
                        status, response = 403, {"error": "forbidden"}
                    else:
                        owner._clear_session_authority_locked(session)
                        del owner._sessions_v2[digest]
                        self._reply(200, {"status": "logged_out"},
                                    set_cookie=self._clear_v2_cookie())
                        return
            elif self.path == "/api/v2/commands":
                try:
                    session, digest, presented = self._authenticated_v2_locked(renew=True)
                except (UnicodeEncodeError, ValueError):
                    status, response = 400, {"error": "invalid_request"}
                else:
                    if session is None:
                        self._v2_unauthorized(presented)
                        return
                    csrf = self.headers.get("X-U-Jagd-CSRF")
                    if (csrf is None or not secrets.compare_digest(
                            csrf.encode("utf-8", errors="surrogatepass"),
                            session["csrf"].encode("ascii"))):
                        status, response = 403, {"error": "forbidden"}
                    elif not _v2_command_valid(body):
                        status, response = 400, {"error": "invalid_command"}
                    else:
                        encoded = _json_bytes(body)
                        previous = session["command_ids"].get(body["id"])
                        if previous is not None:
                            if previous[0] != encoded:
                                status, response = 409, {"error": "duplicate_id_conflict"}
                            elif previous[1] is None:
                                status, response = 202, {"status": "pending", "id": body["id"]}
                            else:
                                status, response = 200, dict(previous[1])
                        elif (body["station"] != session["active_station"]
                              or body["station"] not in session["leases"]
                              or not session["leases"][body["station"]]["grants"]["command"]):
                            status, response = 403, {"error": "forbidden"}
                        elif (body["station_generation"]
                              != session["leases"][body["station"]]["generation"]):
                            status, response = 409, {"error": "stale_generation"}
                        elif body["active_generation"] != session["active_generation"]:
                            status, response = 409, {"error": "stale_active_generation"}
                        elif body["seq"] <= session["last_command_seq"]:
                            status, response = 409, {"error": "out_of_order"}
                        elif time.monotonic() - received_at > _V2_COMMAND_MAX_AGE_S:
                            status, response = 408, {"error": "expired_request"}
                        elif owner._pending_command_count_locked(
                                session) >= _V2_COMMAND_CLIENT_LIMIT:
                            status, response = 429, {"error": "client_queue_full"}
                        elif sum(owner._pending_command_count_locked(candidate)
                                 for candidate in owner._sessions_v2.values()
                                 ) >= _V2_COMMAND_GLOBAL_LIMIT:
                            status, response = 429, {"error": "queue_full"}
                        else:
                            envelope = V2CommandEnvelope(
                                digest, session["client_id"], session["ordinal"],
                                body["station"], body["station_generation"],
                                body["active_generation"],
                                received_at, encoded, body["id"], body["seq"])
                            session["command_queue"].append(envelope)
                            session["command_ids"][body["id"]] = (encoded, None)
                            session["last_command_seq"] = body["seq"]
                            owner._trim_command_history_locked(session)
                            status, response = 202, {"status": "pending", "id": body["id"]}
            elif self.path == "/api/v2/sonar/audio":
                try:
                    session, digest, presented = self._authenticated_v2_locked(renew=True)
                except (UnicodeEncodeError, ValueError):
                    status, response = 400, {"error": "invalid_request"}
                else:
                    if session is None:
                        self._v2_unauthorized(presented)
                        return
                    csrf = self.headers.get("X-U-Jagd-CSRF")
                    if (csrf is None or not secrets.compare_digest(
                            csrf.encode("utf-8", errors="surrogatepass"),
                            session["csrf"].encode("ascii"))):
                        status, response = 403, {"error": "forbidden"}
                    elif (type(body) is not dict or set(body) != _V2_SONAR_AUDIO_FIELDS
                          or body["protocol"] != 2
                          or (body["after"] is not None and
                              (type(body["after"]) is not int or not 0 <= body["after"] <= _SAFE_INTEGER_MAX))
                          or type(body["world_session"]) is not str
                          or not 1 <= len(body["world_session"]) <= 64
                          or type(body["world_epoch"]) is not int
                          or not 0 <= body["world_epoch"] <= _SAFE_INTEGER_MAX
                          or type(body["station_generation"]) is not int
                          or not 0 <= body["station_generation"] <= _SAFE_INTEGER_MAX
                          or type(body["active_generation"]) is not int
                          or not 0 <= body["active_generation"] <= _SAFE_INTEGER_MAX):
                        status, response = 400, {"error": "invalid_request"}
                    elif (session["active_station"] != "sonar"
                          or "sonar" not in session["leases"]
                          or not session["leases"]["sonar"]["grants"]["sonar_audio"]):
                        status, response = 403, {"error": "forbidden"}
                    elif (body["station_generation"]
                          != session["leases"]["sonar"]["generation"]):
                        status, response = 409, {"error": "stale_context"}
                    elif body["active_generation"] != session["active_generation"]:
                        status, response = 409, {"error": "stale_context"}
                    else:
                        context = (digest, session["leases"]["sonar"]["generation"],
                                   session["active_generation"],
                                   body["world_session"], body["world_epoch"])
                        if owner._sonar_audio_context != context:
                            status, response = 503, {"error": "unavailable"}
                        else:
                            after = body["after"]
                            available = [block for block in owner._sonar_audio
                                         if after is None or block[0] > after]
                            if not available:
                                audio_reply = (204, b"", None, False)
                            else:
                                overrun = (after is not None and owner._sonar_audio
                                           and after < owner._sonar_audio[0][0] - 1)
                                sequence, pcm = available[-1] if after is None or overrun else available[0]
                                audio_reply = (200, pcm, sequence, bool(overrun))
            elif self.path == "/api/v1/commands":
                if not self._authenticated_locked():
                    status, response = 401, {"error": "unauthorized"}
                elif not _command_valid(body):
                    status, response = 400, {"error": "invalid_command"}
                elif time.monotonic() - received_at > 5.0:
                    status, response = 408, {"error": "expired_request"}
                elif len(owner._commands) >= 32:
                    status, response = 429, {"error": "queue_full"}
                else:
                    owner._commands.append({"command": body, "lease": owner._lease,
                                            "received_at": received_at})
                    status, response = 202, {"status": "queued", "id": body["id"]}
        if audio_reply is not None:
            # A slow audio socket must never hold the lock needed by the main
            # thread, heartbeats, station grants, or command acceptance.
            code, pcm, sequence, discontinuity = audio_reply
            self._sonar_audio_reply(code, pcm, sequence=sequence, discontinuity=discontinuity)
        else:
            self._reply(status, response)
