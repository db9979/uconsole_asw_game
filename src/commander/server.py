"""Bounded HTTP transport for Remote Crew protocol v2.

The original Commander listener is unencrypted and trusted-LAN-only. The
optional web-host configuration binds to an explicit trusted LAN address behind
an exact HTTPS proxy.
This module neither imports simulation code nor starts on import.
"""

from collections import OrderedDict, deque
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from importlib import resources
import base64
import hashlib
import io
import ipaddress
import json
import logging
import math
import secrets
import socket
import struct
import threading
import time
import re
import select
import unicodedata
from urllib.parse import urlsplit

from src.commander.assets import static_assets
from src.commander.web_auth import WebHostAuth
from src.core import plot
from src.commander.voice import PCM_BYTES as VOICE_PCM_BYTES, VoicePeer, read_frames
from src.core.config import (NATO_AFFILIATIONS, PLAYER_CLASSES,
                             RADAR_RANGE_SCALES_NM, SHIP_SPEED_MAX_KN,
                             HELO_DIP_DEPTH_MIN_M, HELO_DIP_DEPTH_MAX_M,
                             DIFFICULTY_FIELDS, SAVE_SLOTS, SCENARIO_ORDER)
_log = logging.getLogger(__name__)
_CONNECTION_DEADLINE_S = 3.0
_CONTACT_ASSET_ROUTE = re.compile(
    r"/contact-analysis/[a-z0-9][a-z0-9_.-]{0,95}-(?:cruise|high|radar)\.png").fullmatch
_MAX_PREBUILT_ROUTES = 512  # 3 PNG routes/profile + 1 JSON route; headroom above the current catalog size
_MAX_PREBUILT_FILE_BYTES = 4 * 1024 * 1024
_MAX_PREBUILT_BYTES = 32 * 1024 * 1024
_V2_COOKIE = "ujagd_remote_v2"
_WEB_REQUEST_ID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}").fullmatch
_V2_SESSION_IDLE_S = 8 * 60 * 60
_V2_STATION_LEASE_S = 15.0
_V2_SESSION_LIMIT = 12
STATIONS = ("bridge", "sonar", "weapons", "damage", "opz", "radio",
            "engine", "helicopter", "eloka")
# The crewed hostile submarine's six stations (command, sonar, weapons,
# engine, mast/ESM, navigation). They are leased like the frigate's but never
# belong to the frigate crew: a session holds roles of one side only.
OPFOR_ROLES = ("uboot", "uboot_sonar", "uboot_weapons", "uboot_engine", "uboot_esm",
               "uboot_nav")
# Boat stations served by the command projection (everything but its sonar room).
UBOOT_COMMAND_ROLES = tuple(role for role in OPFOR_ROLES if role != "uboot_sonar")
ROLES = STATIONS + OPFOR_ROLES
# Roles with a sonar room (waterfall stream), and the gated capabilities.
SONAR_ROLES = ("sonar", "uboot_sonar")
DIRECT_FIRE_ROLES = ("weapons", "helicopter", "opz", "uboot_weapons")
SONAR_AUDIO_ROLES = ("sonar", "helicopter", "uboot_sonar")
# Pseudo-role of the solo host command surface. It is never a station lease:
# only a solo session carries it, and STATIONS (and every projection) stays nine.
HOST_ROLE = "host"


def role_side(role):
    """``"opfor"`` for the crewed submarine's roles, else ``"frigate"``."""
    return "opfor" if role in OPFOR_ROLES else "frigate"
HOST_MAX_BYTES = 16 * 1024
STATE_MAX_BYTES = 512 * 1024
CHART_MAX_BYTES = 2 * 1024 * 1024
_V2_STATION_CAPABILITIES = ("command", "direct_fire", "sonar_audio")
SONAR_AUDIO_BYTES = 2048
# Ten seconds of blocks: a client that stalls for a moment catches up in order
# instead of losing audio; older blocks are dropped and reported as a discontinuity.
SONAR_AUDIO_RING_BLOCKS = 40
# A (re)connecting audio socket without a resume cursor receives at most this
# many pending blocks (the browser's priming lead); older ones are skipped and
# the skip shows up as a sequence gap.
SONAR_AUDIO_RESUME_BLOCKS = 8
# Inactivity timeout of an upgraded audio socket. A Wi-Fi stall shorter than
# this keeps the stream; the request-phase timeout (1.5 s) does not apply.
AUDIO_SOCKET_TIMEOUT_S = 6.0
SONAR_AUDIO_FRAMES = 1024
SONAR_AUDIO_RATE = 4096
SONAR_STREAM_ROUTE = "/ws/v2/sonar"
SONAR_AUDIO_STREAM_ROUTES = {"/ws/v2/sonar/audio": "sonar",
                            "/ws/v2/helicopter/audio": "helicopter",
                            "/ws/v2/uboot/audio": "uboot_sonar"}
_AUDIO_POLL_ROUTES = {"/api/v2/sonar/audio": "sonar",
                      "/api/v2/helicopter/audio": "helicopter",
                      "/api/v2/uboot/audio": "uboot_sonar"}
VOICE_STREAM_ROUTE = "/ws/v2/voice"
_AUDIO_RESUME_QUERY = re.compile(r"after=(0|[1-9][0-9]{0,15})").fullmatch


def _audio_resume_cursor(query: str):
    """None (no cursor), an int cursor, or False for a malformed query."""
    if query == "":
        return None
    match = _AUDIO_RESUME_QUERY(query)
    if match is None:
        return False
    value = int(match.group(1))
    return value if value <= _SAFE_INTEGER_MAX else False
SONAR_STREAM_MAGIC = b"UJS2"
SONAR_STREAM_VERSION = 1
SONAR_STREAM_HEADER_BYTES = 60
SONAR_STREAM_MAX_BYTES = 4096
SONAR_SCOPE_ROUTES = frozenset(
    f"/?scope={scope}" for scope in
    ("broadband", "lofar", "demon", "tma", "environment", "active")
)
_WEBSOCKET_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
_SAFE_INTEGER_MAX = 2**53 - 1
_V2_SONAR_AUDIO_FIELDS = {"protocol", "after", "world_session", "world_epoch",
                          "station_generation", "active_generation"}
_V2_COMMAND_FIELDS = {"protocol", "id", "seq", "station", "station_generation",
                      "active_generation", "world_session", "world_epoch", "resource_revision",
                      "action", "params"}
_V2_COMMAND_GLOBAL_LIMIT = 64
_V2_COMMAND_CLIENT_LIMIT = 8
_V2_COMMAND_HISTORY_LIMIT = 64
_V2_COMMAND_MAX_AGE_S = 5.0
_COOKIE_NAME = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+").fullmatch
_COOKIE_VALUE = re.compile(r"[!#$%&'()*+\-./:<=>?@\[\]^_`{|}~0-9A-Za-z]*").fullmatch


def _json_bytes(value):
    return json.dumps(value, allow_nan=False, ensure_ascii=True,
                      separators=(",", ":")).encode("ascii")


def _quantized(values, maximum):
    if not isinstance(values, (list, tuple)):
        return b""
    result = bytearray()
    for value in values[:maximum]:
        if type(value) not in (int, float) or not math.isfinite(value):
            return b""
        result.append(round(max(0.0, min(1.0, value)) * 255))
    return bytes(result)


def _sonar_stream_payload(state, sequence, role="sonar"):
    """Pack one detached projected sonar sample; never inspect simulation objects."""
    try:
        visual = state[role]["visualization"]
        broadband_rows = visual["broadband"]["history"]
        lofar_rows = visual["lofar"]["history"]
        demon_rows = visual["demon"]["history"]
        broadband = _quantized(broadband_rows[-1]["bins"], 180) if broadband_rows else b""
        lofar = _quantized(lofar_rows[-1]["bins"], 256) if lofar_rows else b""
        demon = _quantized(demon_rows[-1]["bins"], 80) if demon_rows else b""
        lofar_spectrum = _quantized(visual["lofar"]["spectrum"], 256)
        demon_spectrum = _quantized(visual["demon"]["spectrum"], 80)
        bearing = (float(lofar_rows[-1]["bearing"]) if lofar_rows else
                   float(visual["receiver"]["listen_bearing"]))
        broadband_age = (float(broadband_rows[-1]["age_s"])
                         if broadband_rows else 0.0)
        lofar_age = float(lofar_rows[-1]["age_s"]) if lofar_rows else 0.0
        demon_age = float(demon_rows[-1]["age_s"]) if demon_rows else 0.0
        epoch = int(state["epoch"])
        sim_time = float(state["clock"]["sim"])
        world_session = str(state["session"])
    except (KeyError, IndexError, TypeError, ValueError, OverflowError):
        return None
    if (not all(math.isfinite(value) and value >= 0 for value in
                (sim_time, broadband_age, lofar_age, demon_age))
            or not math.isfinite(bearing)
            or not 0 <= epoch <= _SAFE_INTEGER_MAX
            or not 1 <= len(world_session) <= 64):
        return None
    header = struct.pack(
        "<4sBBHQQdfHHHHHHfff", SONAR_STREAM_MAGIC, SONAR_STREAM_VERSION, 0,
        SONAR_STREAM_HEADER_BYTES, sequence, epoch, sim_time, bearing,
        len(broadband), len(lofar), len(demon), len(lofar_spectrum),
        len(demon_spectrum), 0, broadband_age, lofar_age, demon_age)
    payload = header + broadband + lofar + demon + lofar_spectrum + demon_spectrum
    if len(header) != SONAR_STREAM_HEADER_BYTES or len(payload) > SONAR_STREAM_MAX_BYTES:
        return None
    return (world_session, epoch), payload


def _websocket_frame(payload, opcode=2):
    length = len(payload)
    if length <= 125:
        return bytes((0x80 | opcode, length)) + payload
    if length <= 65535:
        return bytes((0x80 | opcode, 126)) + struct.pack("!H", length) + payload
    raise ValueError("websocket frame too large")


SIMLOG_MAX_BYTES = 2 * 1024 * 1024
EVENTS_MAX = 128
SIMLOG_ENTRIES_MAX = 64


@dataclass(frozen=True)
class V2Action:
    """Closed command metadata; M6/M7 add schemas and main-thread handlers here."""

    stations: frozenset
    validate_params: object
    direct_fire: bool = False
    phases: frozenset = frozenset({"live"})
    # Only operator annotations of the shared picture are optimistic edits that
    # must match the crew assessment revision the browser saw. Every other
    # action resolves its opaque refs (if any) at apply time, so an unrelated
    # contact change must not reject it.
    revision_bound: bool = False


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


def _track_label_params(params):
    if (type(params) is not dict or set(params) != {"ref", "label"}
            or not _ref(params["ref"]) or type(params["label"]) is not str):
        return False
    label = params["label"]
    return (1 <= len(label) <= 16 and label.isascii()
            and any(char.isalnum() for char in label)
            and all(char.isalnum() or char == "-" for char in label))


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


# Rejections of the crewed submarine's own orders (their own vocabulary,
# never the frigate's words).
UBOOT_REASONS = frozenset((
    "uboot_no_torpedoes", "uboot_reloading", "uboot_out_of_arc", "uboot_no_decoys",
    "uboot_too_deep", "uboot_no_snorkel", "uboot_no_wire", "uboot_mast_depth"))


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


def _sonar_cursor_params(params):
    return (type(params) is dict and set(params) == {"page", "frequency_hz"}
            and params["page"] in ("lofar", "demon")
            and type(params["frequency_hz"]) in (int, float)
            and math.isfinite(params["frequency_hz"])
            and 0.0 <= params["frequency_hz"] <= 300.0)


def _sonar_band_params(params):
    return (type(params) is dict and set(params) == {"low_hz", "high_hz"}
            and all(type(params[name]) in (int, float) and math.isfinite(params[name])
                    for name in ("low_hz", "high_hz"))
            and 0.0 <= params["low_hz"] < params["high_hz"] <= 300.0)


def _tas_side_params(params):
    return (type(params) is dict and set(params) == {"ref", "action"}
            and type(params["ref"]) is str and 0 < len(params["ref"]) <= 64
            and params["action"] in ("flip", "confirm"))


def _demon_band_params(params):
    return (type(params) is dict and set(params) == {"low_hz", "high_hz"}
            and (params["low_hz"], params["high_hz"]) in ((200, 800), (400, 1400),
                                                          (1000, 2000)))


def _assign_profile_params(params):
    key = params.get("profile_key") if type(params) is dict else None
    return (type(params) is dict and set(params) == {"ref", "profile_key"}
            and type(params["ref"]) is str and 0 < len(params["ref"]) <= 64
            and (key is None or (type(key) is str and 0 < len(key) <= 64)))


def _tma_hypothesis_params(params):
    return (type(params) is dict
            and set(params) == {"ref", "course", "speed_kn", "range_nm"}
            and type(params["ref"]) is str and 0 < len(params["ref"]) <= 64
            and all(type(params[name]) in (int, float) and math.isfinite(params[name])
                    for name in ("course", "speed_kn", "range_nm"))
            and 0.0 <= params["course"] < 360.0 and 0.0 <= params["speed_kn"] <= 45.0
            and 0.2 <= params["range_nm"] <= 60.0)


def _plot_add_params(params):
    shape = params.get("shape") if type(params) is dict else None
    if shape not in plot.KINDS:
        return False
    item = {("kind" if key == "shape" else key): value for key, value in params.items()}
    return (set(item) == plot.command_fields(shape)
            and plot.valid_object(dict(item, id=1, t=0.0)))


def _plot_id(value):
    return type(value) is int and 1 <= value <= plot.MAX_ID


def _plot_remove_params(params):
    return type(params) is dict and set(params) == {"id"} and _plot_id(params["id"])


def _plot_relabel_params(params):
    return (type(params) is dict and set(params) == {"id", "label"}
            and _plot_id(params["id"]) and plot.valid_label(params["label"]))


def _integration_params(params):
    return (type(params) is dict and set(params) == {"seconds"}
            and type(params["seconds"]) is int and params["seconds"] in (2, 8, 16, 64))


def _team_compartment_params(params):
    return (type(params) is dict and set(params) == {"team", "compartment"}
            and type(params["team"]) is int and 1 <= params["team"] <= 3
            and type(params["compartment"]) is str
            and params["compartment"] in _COMPARTMENTS)


def _annotation_params(params):
    return (type(params) is dict and set(params) == {"ref", "candidate_ref"}
            and _ref(params["ref"]) and _ref(params["candidate_ref"]))


def _ecm_technique_params(params):
    return (type(params) is dict and set(params) == {"ref", "technique"}
            and _ref(params["ref"])
            and params["technique"] in (
                "noise", "rgpo", "vgpo", "false_targets"))


def _waypoint_params(params):
    return (type(params) is dict and set(params) == {"x", "y"}
            and all(type(params[key]) in (int, float)
                    and 0 <= params[key] <= 1000 and math.isfinite(params[key])
                    for key in ("x", "y")))


def _uboot_depth_params(params):
    return (type(params) is dict and set(params) == {"depth_m"}
            and type(params["depth_m"]) in (int, float)
            and math.isfinite(params["depth_m"])
            and 0 <= params["depth_m"] <= 1000)


def _uboot_speed_params(params):
    return (type(params) is dict and set(params) == {"speed_kn"}
            and type(params["speed_kn"]) in (int, float)
            and math.isfinite(params["speed_kn"])
            and 0 <= params["speed_kn"] <= 40)


def _uboot_wire_params(params):
    """Steer a wired crew torpedo: its ref and the new datum from the boat."""
    return (type(params) is dict and set(params) == {"ref", "bearing", "range_nm"}
            and _ref(params["ref"])
            and all(type(params[key]) in (int, float) and math.isfinite(params[key])
                    for key in ("bearing", "range_nm"))
            and 0 <= params["bearing"] < 360 and 0.05 <= params["range_nm"] <= 40)


def _uboot_fire_params(params):
    """A crew shot: a sonar contact ref, or a free bearing with optional range;
    run depth (optional) and one or two torpedoes."""
    if type(params) is not dict or set(params) != {"ref", "bearing", "range_nm",
                                                    "depth_m", "salvo"}:
        return False
    ref, bearing, range_nm = params["ref"], params["bearing"], params["range_nm"]
    depth = params["depth_m"]
    if type(params["salvo"]) is not int or params["salvo"] not in (1, 2):
        return False
    if depth is not None and not (type(depth) in (int, float) and math.isfinite(depth)
                                  and 5 <= depth <= 300):
        return False
    if (ref is None) == (bearing is None):
        return False
    if ref is not None and not _ref(ref):
        return False
    if bearing is not None and not (type(bearing) in (int, float)
                                    and math.isfinite(bearing) and 0 <= bearing < 360):
        return False
    return range_nm is None or (type(range_nm) in (int, float)
                                and math.isfinite(range_nm)
                                and 0.05 <= range_nm <= 40)


def _bearing_params(params):
    return (type(params) is dict and set(params) == {"bearing"}
            and type(params["bearing"]) in (int, float)
            and 0 <= params["bearing"] < 360
            and math.isfinite(params["bearing"]))


def _navigation_proposal_params(params):
    if (type(params) is not dict or not params
            or not set(params) <= {"course", "speed_kn"}):
        return False
    course = params.get("course")
    speed = params.get("speed_kn")
    return ((course is None or type(course) in (int, float)
             and math.isfinite(course) and 0 <= course < 360)
            and (speed is None or type(speed) in (int, float)
                 and math.isfinite(speed) and 0 <= speed <= SHIP_SPEED_MAX_KN)
            and (course is not None or speed is not None))


def _ref_enabled_params(params):
    return (type(params) is dict and set(params) == {"ref", "enabled"}
            and _ref(params.get("ref"))
            and type(params.get("enabled")) is bool)


def _slot_params(params):
    return (type(params) is dict and set(params) == {"slot"}
            and type(params["slot"]) is int and 1 <= params["slot"] <= SAVE_SLOTS)


def _instructor_environment_params(params):
    return (type(params) is dict and set(params) == {"sea_state", "event"}
            and type(params["sea_state"]) is int
            and 0 <= params["sea_state"] <= 6
            and (params["event"] is None or params["event"] in (
                "targets_quiet", "targets_cruise", "targets_flank",
                "torpedo_transient")))


def _new_game_params(params):
    required = {"scenario", "world_mode"}
    if (type(params) is not dict or not required <= set(params)
            or not set(params) <= required | {"difficulty", "seed"}):
        return False
    if not (type(params["scenario"]) is str and params["scenario"] in SCENARIO_ORDER
            and type(params["world_mode"]) is str
            and params["world_mode"] in ("fixed", "procedural", "real_fixed")
            and ("seed" not in params or type(params["seed"]) is int
                 and 1 <= params["seed"] < 1_000_000_000)):
        return False
    if "difficulty" not in params:
        return True
    difficulty = params["difficulty"]
    if type(difficulty) is not dict or set(difficulty) != set(DIFFICULTY_FIELDS):
        return False
    for name, (kind, low, high, _step, _default) in DIFFICULTY_FIELDS.items():
        amount = difficulty[name]
        if kind is int:
            if type(amount) is not int or not low <= amount <= high:
                return False
        elif (type(amount) not in (int, float) or isinstance(amount, bool)
                or not math.isfinite(amount) or not low <= amount <= high):
            return False
    return True


_HOST_ANY = frozenset({"live"})
_HOST_REPLACING = frozenset({"live", "menu", "ended"})
_HOST_STATIONS = frozenset({HOST_ROLE})
# The boat's own plot: its commander and navigator draw on it.
_UBOOT_PLOT = ("uboot", "uboot_nav")

V2_ACTION_REGISTRY = {
    "acknowledge": V2Action(frozenset(ROLES), _no_params),
    # Shared chart plot: every station may draw, relabel and erase.
    # The submarine commander's plot actions reach the boat's own plot.
    "plot_add": V2Action(frozenset((*STATIONS, *_UBOOT_PLOT)), _plot_add_params),
    "plot_remove": V2Action(frozenset((*STATIONS, *_UBOOT_PLOT)), _plot_remove_params),
    "plot_relabel": V2Action(frozenset((*STATIONS, *_UBOOT_PLOT)), _plot_relabel_params),
    "plot_clear": V2Action(frozenset((*STATIONS, *_UBOOT_PLOT)), _no_params),
    # Solo-only host controls: admitted only for a session carrying the host
    # surface, and each action states the exact phases it may run in.
    "host_save": V2Action(_HOST_STATIONS, _slot_params, phases=_HOST_ANY),
    "host_load": V2Action(_HOST_STATIONS, _slot_params, phases=_HOST_REPLACING),
    "host_new_game": V2Action(_HOST_STATIONS, _new_game_params,
                              phases=_HOST_REPLACING),
    "host_instructor_environment": V2Action(
        _HOST_STATIONS, _instructor_environment_params, phases=_HOST_ANY),
    "bridge_set_course": V2Action(frozenset({"bridge"}), _course_params),
    "bridge_set_speed": V2Action(frozenset({"bridge"}), _speed_params),
    "propose_navigation": V2Action(frozenset({"bridge"}),
                                    _navigation_proposal_params),
    "sonar_classify": V2Action(frozenset({"sonar", "helicopter", "uboot_sonar"}), _classification_params,
        revision_bound=True),
    "sonar_set_release": V2Action(frozenset({"sonar", "helicopter"}), _release_params,
        revision_bound=True),
    "helicopter_qualify": V2Action(frozenset({"helicopter"}), _ref_enabled_params,
        revision_bound=True),
    "helicopter_buoy_release": V2Action(frozenset({"helicopter"}), _release_params,
        revision_bound=True),
    "propose_target": V2Action(frozenset({"sonar"}), _single_ref_params,
        revision_bound=True),
    "clear_target_proposal": V2Action(frozenset({"sonar"}), _no_params),
    "opz_classify": V2Action(frozenset({"opz"}), _classification_params,
        revision_bound=True),
    "opz_affiliate": V2Action(frozenset({"opz"}), _affiliation_params,
        revision_bound=True),
    "opz_set_track_id": V2Action(frozenset({"opz"}), _track_label_params,
        revision_bound=True),
    "opz_create_fusion": V2Action(frozenset({"opz"}), _fusion_refs_params,
        revision_bound=True),
    "opz_dissolve_fusion": V2Action(frozenset({"opz"}), _single_ref_params,
        revision_bound=True),
    "opz_set_radar": V2Action(frozenset({"opz"}), _radar_params),
    "opz_mark_blip": V2Action(frozenset({"opz"}), _single_ref_params),
    "opz_set_ciws": V2Action(frozenset({"opz"}), _bool_params("enabled")),
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
    "eloka_annotate": V2Action(frozenset({"eloka"}), _annotation_params,
        revision_bound=True),
    "eloka_clear_annotation": V2Action(frozenset({"eloka"}), _single_ref_params,
        revision_bound=True),
    "eloka_set_jamming": V2Action(frozenset({"eloka"}), _ref_enabled_params),
    "eloka_set_technique": V2Action(
        frozenset({"eloka"}), _ecm_technique_params),
    "eloka_set_auto": V2Action(frozenset({"eloka"}), _bool_params("enabled")),
    "sonar_set_listen_bearing": V2Action(frozenset({"sonar", "uboot_sonar"}), _bearing_params),
    "sonar_set_focus": V2Action(frozenset({"sonar", "uboot_sonar"}), _single_ref_params),
    "sonar_clear_focus": V2Action(frozenset({"sonar", "uboot_sonar"}), _no_params),
    "sonar_set_array_mode": V2Action(frozenset({"sonar"}),
        _enum_params("mode", ("BOW", "TOWED"))),
    "sonar_set_tas": V2Action(frozenset({"sonar"}), _bool_params("deployed")),
    "sonar_set_tow_depth": V2Action(frozenset({"sonar"}),
        _bounded_number_params("depth_m", 20, 260)),
    # The submarine commander may ping and take a BT without its sonar room.
    "sonar_measure_bt": V2Action(frozenset({"sonar", "uboot_sonar", "uboot"}), _no_params),
    "sonar_active_ping": V2Action(frozenset({"sonar", "uboot_sonar", "uboot"}), _no_params),
    "sonar_set_tma_enabled": V2Action(frozenset({"sonar", "uboot_sonar"}),
                                      _bool_params("enabled")),
    "sonar_set_gain": V2Action(frozenset({"sonar", "uboot_sonar"}),
        _bounded_number_params("gain_db", -12, 24)),
    "sonar_set_audition_mode": V2Action(frozenset({"sonar", "uboot_sonar"}),
        _enum_params("mode", ("BROADBAND", "FILTERED", "HETERODYNE"))),
    "sonar_set_band_preset": V2Action(frozenset({"sonar", "uboot_sonar"}),
        _enum_params("preset", ("FULL", "LOW", "SHAFT", "MID"))),
    "sonar_set_notch": V2Action(frozenset({"sonar", "uboot_sonar"}), _bool_params("enabled")),
    "sonar_set_cursor": V2Action(frozenset({"sonar", "uboot_sonar"}), _sonar_cursor_params),
    "sonar_mark_line": V2Action(frozenset({"sonar", "uboot_sonar"}),
        _enum_params("page", ("lofar", "demon"))),
    "sonar_set_integration": V2Action(frozenset({"sonar", "uboot_sonar"}), _integration_params),
    "sonar_set_vernier": V2Action(frozenset({"sonar", "uboot_sonar"}), _bool_params("enabled")),
    "sonar_set_band": V2Action(frozenset({"sonar", "uboot_sonar"}), _sonar_band_params),
    "sonar_set_operator_notch": V2Action(frozenset({"sonar", "uboot_sonar"}),
        _bounded_number_params("frequency_hz", 0.000001, 300, nullable=True)),
    "sonar_set_peak_hold": V2Action(frozenset({"sonar", "uboot_sonar"}),
                                    _bool_params("enabled")),
    "sonar_set_harmonic": V2Action(frozenset({"sonar", "uboot_sonar"}),
        _bounded_number_params("frequency_hz", 0.000001, 300, nullable=True)),
    "sonar_designate_target": V2Action(frozenset({"sonar", "uboot_sonar"}), _single_ref_params),
    "sonar_tma_set": V2Action(frozenset({"sonar", "uboot_sonar"}), _tma_hypothesis_params),
    "sonar_assign_profile": V2Action(frozenset({"sonar", "uboot_sonar"}), _assign_profile_params),
    "sonar_tas_side": V2Action(frozenset({"sonar"}), _tas_side_params),
    "sonar_set_demon_band": V2Action(frozenset({"sonar", "uboot_sonar"}), _demon_band_params),
    "sonar_set_heterodyne": V2Action(frozenset({"sonar", "uboot_sonar"}),
        _bounded_number_params("frequency_hz", 400, 1200)),
    "sonar_tma_accept": V2Action(frozenset({"sonar", "uboot_sonar"}), _single_ref_params),
    "sonar_tma_copy_proposal": V2Action(frozenset({"sonar", "uboot_sonar"}), _single_ref_params),
    "helicopter_launch": V2Action(frozenset({"helicopter"}), _no_params),
    "helicopter_return": V2Action(frozenset({"helicopter"}), _no_params),
    "helicopter_set_waypoint": V2Action(frozenset({"helicopter"}),
                                        _waypoint_params),
    "helicopter_deploy_buoy": V2Action(frozenset({"helicopter"}), _no_params),
    "helicopter_set_buoy_mode": V2Action(frozenset({"helicopter"}),
        _enum_params("mode", ("PASSIVE", "ACTIVE"))),
    "helicopter_set_listen_source": V2Action(frozenset({"helicopter"}),
        lambda params: (type(params) is dict and set(params) == {"source"}
                        and type(params["source"]) is str
                        and (params["source"] == "DIP" or
                             params["source"].startswith("SB")
                             and params["source"][2:].isdigit()
                             and len(params["source"]) <= 5))),
    "helicopter_set_listen_bearing": V2Action(frozenset({"helicopter"}),
        _bounded_number_params("bearing", 0.0, 359.99999999999994)),
    "helicopter_clear_listen_bearing": V2Action(frozenset({"helicopter"}), _no_params),
    "helicopter_set_audio_mode": V2Action(frozenset({"helicopter"}),
        _enum_params("mode", ("BROADBAND", "FILTERED", "HETERODYNE"))),
    "helicopter_set_audio_band": V2Action(frozenset({"helicopter"}),
        _enum_params("preset", ("FULL", "LOW", "SHAFT", "MID"))),
    "helicopter_set_audio_gain": V2Action(frozenset({"helicopter"}),
        _bounded_number_params("gain_db", -12.0, 24.0)),
    "helicopter_set_audio_notch": V2Action(frozenset({"helicopter"}),
        _bool_params("enabled")),
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
    # The crewed submarine's commander.
    # Each boat order belongs to the station that does it aboard; the commander
    # keeps course, speed and depth.
    "uboot_set_course": V2Action(frozenset({"uboot", "uboot_nav"}), _course_params),
    "uboot_set_speed": V2Action(frozenset({"uboot", "uboot_engine"}), _uboot_speed_params),
    "uboot_set_depth": V2Action(frozenset({"uboot", "uboot_nav"}), _uboot_depth_params),
    "uboot_fire": V2Action(frozenset({"uboot_weapons"}), _uboot_fire_params,
                           direct_fire=True),
    "uboot_decoy": V2Action(frozenset({"uboot_weapons"}), _no_params),
    "uboot_blow": V2Action(frozenset({"uboot", "uboot_engine"}), _no_params),
    "uboot_snorkel": V2Action(frozenset({"uboot_engine"}), _bool_params("enabled")),
    "uboot_mast": V2Action(frozenset({"uboot_esm"}), _bool_params("enabled")),
    "uboot_wire_steer": V2Action(frozenset({"uboot_weapons"}), _uboot_wire_params),
    "uboot_wire_cut": V2Action(frozenset({"uboot_weapons"}), _single_ref_params),
    "uboot_silent": V2Action(frozenset({"uboot", "uboot_engine"}), _bool_params("enabled")),
    "uboot_bottom": V2Action(frozenset({"uboot", "uboot_nav"}), _bool_params("enabled")),
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
    if (spec is None or type(command.get("station")) is not str
            or command["station"] not in spec.stations):
        return False
    # The host surface has no station-activation context to bind to.
    if command["station"] == HOST_ROLE and command.get("active_generation") != 0:
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


class CommanderServer:
    """Thread-safe v2 publications and leased commands, with explicit lifecycle.

    ``address`` is available only while started. Command timestamps use
    ``time.monotonic()``.
    Pairing codes are case-sensitive DDDLLL (ASCII digits/uppercase letters),
    remain stable for this server object, and allow five misses per rolling
    minute across all clients. A security lockout or explicit new-session
    ``revoke()`` rotates the code; ordinary stop/start and pairing do not.
    Starting requires the packaged ``data.commander`` assets.
    """

    def __init__(self, translations=None, contact_analysis_assets=None,
                 web_auth: WebHostAuth | None = None, public_origin: str | None = None,
                 manual_pages=None):
        # The web-host room always sits behind its proxy. The local Commander
        # listener may add an HTTPS proxy origin next to its direct LAN address.
        if web_auth is not None and public_origin is None:
            raise ValueError("web auth requires a public origin")
        if public_origin is not None:
            parsed = urlsplit(public_origin)
            if (parsed.scheme != "https" or not parsed.hostname or parsed.path
                    or parsed.query or parsed.fragment or parsed.username
                    or parsed.password or public_origin.endswith("/")):
                raise ValueError("an exact HTTPS origin is required")
        self.web_auth = web_auth
        self.public_origin = public_origin
        self._web_host_digest = None
        self._web_admin_queue = deque(maxlen=32)
        self._web_admin_results = OrderedDict()
        self._web_admin_seen = OrderedDict()
        self._web_admin_inflight = set()
        self._web_options_state = _json_bytes({})
        self._web_proposals = {"target": None, "navigation": None}
        self._lock = threading.RLock()
        self._lifecycle = threading.Lock()
        self._http = None
        self._thread = None
        self._running = False
        self._code_index = None
        self._rotate_code_locked()
        self._pair_failures = deque()
        self._sessions_v2 = {}
        self._solo = False
        self._next_v2_ordinal = 0
        self._station_generations = {station: 0 for station in ROLES}
        self._sonar_audio = deque(maxlen=SONAR_AUDIO_RING_BLOCKS)
        self._sonar_audio_context = None
        self._sonar_audio_sequence = 0
        self._helicopter_audio = deque(maxlen=SONAR_AUDIO_RING_BLOCKS)
        self._helicopter_audio_context = None
        self._helicopter_audio_sequence = 0
        self._uboot_audio = deque(maxlen=SONAR_AUDIO_RING_BLOCKS)
        self._uboot_audio_context = None
        self._uboot_audio_sequence = 0
        self._audio_condition = threading.Condition(self._lock)
        self._audio_clients = {}
        self._audio_stats = {}
        self._sonar_stream_sequence = 0
        self._sonar_stream_context = None
        self._sonar_stream_payload = None
        self._uboot_stream_context = None
        self._uboot_stream_payload = None
        self._sonar_stream_condition = threading.Condition(self._lock)
        self._sonar_stream_clients = {}
        self._voice_enabled = False
        self._voice_peers = {}
        self._voice_talker = None
        self._v2_proposals = {}
        self._v2_host = _json_bytes({"protocol": 2, "phase": "blocked"})
        self._v2_events = {}
        self._v2_private_events = {}
        self._v2_simlogs = {}
        unpublished = dict(protocol=2, version="", session="unpublished", epoch=0,
                           revision=0, seq=0, phase="blocked", role=None,
                           chart_revision="unpublished")
        empty_chart = dict(protocol=2, revision="unpublished", size_nm=500,
                           landmasses=[], disclaimer="")
        self._v2_states = {role: _json_bytes(unpublished)
                           for role in (None, *ROLES)}
        self._v2_sonar_compact_state = self._v2_states["sonar"]
        self._v2_charts = {role: _json_bytes(empty_chart)
                           for role in (None, *ROLES)}
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
            valid_route = (route == "/api/v2/contacts"
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
        if prebuilt and "/api/v2/contacts" not in prebuilt:
            raise ValueError("contact projection route required")
        self._prebuilt_assets = prebuilt
        # Pre-rendered, script-free player manual (src/core/manual.py) per language.
        pages = {} if manual_pages is None else manual_pages
        if not isinstance(pages, dict) or not set(pages) <= {"en", "de"}:
            raise ValueError("invalid manual pages")
        self._manual_pages = {}
        for lang, page in pages.items():
            if (not isinstance(page, str) or not page
                    or len(page.encode("utf-8")) > _MAX_PREBUILT_FILE_BYTES):
                raise ValueError("invalid manual page")
            self._manual_pages[f"/manual-{lang}"] = ("text/html; charset=utf-8",
                                                    page.encode("utf-8"))
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
            assets = static_assets(self.web_auth is not None,
                                   resources.files("data.commander"))
            assets.update(self._manual_pages)
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
                self._voice_enabled = False
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
            return self._running and bool(self._sessions_v2)

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
        self._voice_talker = None
        self._voice_peers.clear()
        self._clear_sonar_audio_locked()
        self._clear_helicopter_audio_locked()
        self._clear_uboot_audio_locked()
        self._sonar_stream_sequence += 1
        self._sonar_stream_context = None
        self._sonar_stream_payload = None
        self._uboot_stream_context = None
        self._uboot_stream_payload = None
        self._sonar_stream_condition.notify_all()
        self._sonar_stream_clients.clear()
        for session in self._sessions_v2.values():
            self._clear_session_authority_locked(session, "session_revoked")
        self._sessions_v2.clear()
        self._web_host_digest = None
        self._web_admin_queue.clear()
        self._web_admin_inflight.clear()
        self._web_admin_seen.clear()
        self._web_admin_results.clear()
        self._v2_proposals.clear()
        self._v2_host = _json_bytes({"protocol": 2, "phase": "blocked"})
        self._v2_events.clear()
        self._v2_private_events.clear()
        self._v2_simlogs.clear()
        if rotate_code:
            self._rotate_code_locked()

    def _clear_sonar_audio_locked(self):
        # Numbering never restarts while the server lives: a browser worklet
        # de-duplicates by sequence, so a restart at 1 would make it drop every
        # new block until the count passed the old one. A cleared stream that
        # had content skips one number so the restart shows as a gap.
        if self._sonar_audio:
            self._sonar_audio_sequence += 1
        self._sonar_audio.clear()
        self._sonar_audio_context = None
        self._audio_condition.notify_all()

    def _clear_helicopter_audio_locked(self):
        # Numbering never restarts while the server lives: a browser worklet
        # de-duplicates by sequence, so a restart at 1 would make it drop every
        # new block until the count passed the old one. A cleared stream that
        # had content skips one number so the restart shows as a gap.
        if self._helicopter_audio:
            self._helicopter_audio_sequence += 1
        self._helicopter_audio.clear()
        self._helicopter_audio_context = None
        self._audio_condition.notify_all()

    def _clear_uboot_audio_locked(self):
        # Numbering never restarts while the server lives: a browser worklet
        # de-duplicates by sequence, so a restart at 1 would make it drop every
        # new block until the count passed the old one. A cleared stream that
        # had content skips one number so the restart shows as a gap.
        if self._uboot_audio:
            self._uboot_audio_sequence += 1
        self._uboot_audio.clear()
        self._uboot_audio_context = None
        self._audio_condition.notify_all()

    def _clear_role_audio_locked(self, role):
        if role == "sonar":
            self._clear_sonar_audio_locked()
        elif role == "helicopter":
            self._clear_helicopter_audio_locked()
        elif role == "uboot_sonar":
            self._clear_uboot_audio_locked()

    def _audio_ring(self, role):
        """(blocks, context) of one audio role's stream."""
        if role == "sonar":
            return self._sonar_audio, self._sonar_audio_context
        if role == "helicopter":
            return self._helicopter_audio, self._helicopter_audio_context
        return self._uboot_audio, self._uboot_audio_context

    def _stream_for(self, role):
        """(context, payload) of one sonar room's waterfall stream."""
        if role == "uboot_sonar":
            return self._uboot_stream_context, self._uboot_stream_payload
        return self._sonar_stream_context, self._sonar_stream_payload

    @staticmethod
    def _side_conflict(session, station):
        """A session never holds (or requests into) roles of both sides."""
        side = role_side(station)
        return any(role_side(role) != side for role in session["leases"])

    @staticmethod
    def _station_grants(station=None):
        """A granted station always carries every right it can have; the host
        only ever takes rights away (``set_client_grant``) or the station."""
        return {
            "command": station in ROLES,
            "direct_fire": station in DIRECT_FIRE_ROLES,
            "sonar_audio": station in SONAR_AUDIO_ROLES,
        }

    def _station_free_locked(self, session, station):
        """Free for ``session``: unheld, or held only as the web host's placeholder."""
        holder = next((candidate for candidate in self._sessions_v2.values()
                       if station in candidate["leases"]), None)
        return holder is None or (holder is not session and holder.get("web_host")
                                  and not session.get("web_host"))

    def _auto_grant_locked(self, session, station):
        """Lease a free station straight away with its full rights (no host step)."""
        if (station in session["leases"] or self._side_conflict(session, station)
                or not self._station_free_locked(session, station)):
            return False
        holder = next((candidate for candidate in self._sessions_v2.values()
                       if station in candidate["leases"]), None)
        if holder is not None:
            self._release_station_locked(holder, station)
        else:
            self._station_generations[station] += 1
        session["leases"][station] = {
            "generation": self._station_generations[station],
            "grants": self._station_grants(station),
        }
        session["requests"].pop(station, None)
        self._set_active_station_locked(session, station)
        return True

    def _grant_waiting_requests_locked(self):
        """Oldest waiting request first: a station that became free goes to it."""
        waiting = sorted(((session["ordinal"], generation, station, session)
                          for session in self._sessions_v2.values()
                          for station, generation in session["requests"].items()),
                         key=lambda row: row[:3])
        for _ordinal, _generation, station, session in waiting:
            if station in session["requests"]:
                self._auto_grant_locked(session, station)

    def _set_active_station_locked(self, session, station, reason="active_station_changed"):
        if station is not None and station not in session["leases"]:
            return False
        if session["active_station"] == station:
            return True
        peer = next((candidate for candidate in self._voice_peers.values()
                     if candidate.session is session), None)
        if peer is not None:
            self._voice_disconnect_locked(peer)
        if "sonar" in (session["active_station"], station):
            self._clear_sonar_audio_locked()
        if "helicopter" in (session["active_station"], station):
            self._clear_helicopter_audio_locked()
        if "uboot_sonar" in (session["active_station"], station):
            self._clear_uboot_audio_locked()
        session["active_station"] = station
        session["active_generation"] += 1
        session["held_commands"].clear()
        self._sonar_stream_condition.notify_all()
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
        peer = next((candidate for candidate in self._voice_peers.values()
                     if candidate.session is session and candidate.station == station), None)
        if peer is not None:
            self._voice_disconnect_locked(peer)
        self._reject_station_commands_locked(session, station, reason)
        if station == "sonar":
            self._clear_sonar_audio_locked()
        if station == "helicopter":
            self._clear_helicopter_audio_locked()
        if station == "uboot_sonar":
            self._clear_uboot_audio_locked()
        del session["leases"][station]
        session["requests"].pop(station, None)
        self._station_generations[station] += 1
        if session["active_station"] == station:
            replacement = next((item for item in ROLES if item in session["leases"]), None)
            self._set_active_station_locked(session, replacement, reason)
        return True

    def _clear_session_authority_locked(self, session, reason="session_revoked"):
        for station in tuple(ROLES):
            if station in session["leases"]:
                self._release_station_locked(session, station, reason)
        session["requests"].clear()
        session["simlog"] = False
        if session["solo_host"]:
            self._reject_station_commands_locked(session, HOST_ROLE, reason)
            session["solo_host"] = False
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

    def _authority_current_locked(self, envelope):
        if type(envelope) is not V2CommandEnvelope:
            return False
        session = self._sessions_v2.get(envelope.session_digest)
        lease = None if session is None else session["leases"].get(envelope.role)
        # A solo session holds every station at once, so a proposal made from one
        # station stays current while the browser looks at another one; the
        # lease generation and grant below still bind it to its exact origin.
        active_current = (session is not None and (
            session["solo_host"]
            or (session["active_station"] == envelope.role
                and session["active_generation"] == envelope.active_generation)))
        return (session is not None
                and session["client_id"] == envelope.client_id
                and session["ordinal"] == envelope.client_ordinal
                and active_current
                and lease is not None
                and lease["generation"] == envelope.lease_generation
                and lease["grants"]["command"] is True)

    def authority_current_v2(self, envelope) -> bool:
        """Recheck an exact proposal origin without exposing session objects."""
        with self._lock:
            self._expire_locked()
            return self._authority_current_locked(envelope)

    def _expire_locked(self):
        now = time.monotonic()
        while self._pair_failures and now - self._pair_failures[0] >= 60.0:
            self._pair_failures.popleft()
        for digest, session in tuple(self._sessions_v2.items()):
            if now - session["last_get"] >= _V2_SESSION_IDLE_S:
                self._clear_session_authority_locked(session)
                del self._sessions_v2[digest]
            elif (session["leases"] and not session["solo_host"]
                  and now - session["presence"] >= _V2_STATION_LEASE_S):
                # A solo session has no competing client to free stations for;
                # direct fire still requires fresh presence at apply time.
                self._clear_session_authority_locked(session, "role_revoked")
        if self._web_host_digest not in self._sessions_v2:
            self._web_host_digest = None
        self._grant_waiting_requests_locked()

    def _new_session_locked(self, name: str, *, web_host=False):
        token = secrets.token_urlsafe(32)
        session = {
            "client_id": secrets.token_urlsafe(18),
            "name": name,
            "csrf": secrets.token_urlsafe(32),
            "ordinal": self._next_v2_ordinal,
            "requests": {},
            "next_request_generation": 0,
            "leases": {},
            "active_station": None,
            "active_generation": 0,
            "simlog": False,
            "solo_host": False,
            "web_host": web_host,
            "host_generation": 0,
            "presence": time.monotonic(),
            "last_get": time.monotonic(),
            "last_command_seq": -1,
            "command_queue": deque(),
            "command_ids": OrderedDict(),
            "command_results": deque(maxlen=_V2_COMMAND_HISTORY_LIMIT),
            "held_commands": {},
        }
        self._next_v2_ordinal += 1
        digest = hashlib.sha256(token.encode("ascii")).digest()
        self._sessions_v2[digest] = session
        if web_host:
            self._web_host_digest = digest
            session["solo_host"] = True
            session["host_generation"] += 1
            session["simlog"] = True
            self._web_grant_available_locked(session)
        elif self._solo:
            self._solo_grant_all_locked(session)
        return token, session

    def web_host_session(self):
        with self._lock:
            self._expire_locked()
            return self._sessions_v2.get(self._web_host_digest)

    def _web_grant_available_locked(self, session):
        for station in STATIONS:
            if not any(station in candidate["leases"]
                       for candidate in self._sessions_v2.values()):
                self._station_generations[station] += 1
                session["leases"][station] = {
                    "generation": self._station_generations[station],
                    "grants": self._solo_grants(station),
                }
        if session["active_station"] not in session["leases"]:
            self._set_active_station_locked(session, next(iter(session["leases"]), None))

    def web_rebase(self):
        """Keep authenticated clients, clear old commands and crew authority."""
        with self._lock:
            while self._web_admin_queue:
                request_id, _, _ = self._web_admin_queue.popleft()
                self.finish_web_admin(request_id, {"ok": False, "error": "world_replaced"})
            for session in self._sessions_v2.values():
                self._clear_session_authority_locked(session)
            host = self._sessions_v2.get(self._web_host_digest)
            if host is not None:
                host["solo_host"] = True
                host["host_generation"] += 1
                host["simlog"] = True
                self._web_grant_available_locked(host)
            self._v2_proposals.clear()
            self._v2_events.clear()
            self._v2_private_events.clear()
            self._v2_simlogs.clear()

    def web_reclaim_available(self):
        with self._lock:
            host = self._sessions_v2.get(self._web_host_digest)
            if host is not None:
                self._web_grant_available_locked(host)

    def drain_web_admin(self):
        with self._lock:
            items = list(self._web_admin_queue)
            self._web_admin_queue.clear()
            self._web_admin_inflight.update(row[0] for row in items)
            return items

    def reject_web_admin_pending(self, reason="world_replaced"):
        with self._lock:
            while self._web_admin_queue:
                request_id, _, _ = self._web_admin_queue.popleft()
                self.finish_web_admin(request_id, {"ok": False, "error": reason})

    def finish_web_admin(self, request_id, ok):
        with self._lock:
            self._web_admin_inflight.discard(request_id)
            if request_id not in self._web_admin_seen:
                return
            self._web_admin_results[request_id] = ok
            while len(self._web_admin_results) > 8:
                self._web_admin_results.popitem(last=False)

    def _enqueue_web_admin_locked(self, digest, body, request_id):
        if request_id is None or _WEB_REQUEST_ID(request_id) is None:
            return 400, {"error": "invalid_request_id"}
        encoded = _json_bytes(body)
        previous = self._web_admin_seen.get(request_id)
        if previous is not None:
            if previous != encoded:
                return 409, {"error": "duplicate_id_conflict"}
            if request_id in self._web_admin_results:
                return 200, {"id": request_id,
                             "result": self._web_admin_results[request_id]}
            if (request_id in self._web_admin_inflight
                    or any(row[0] == request_id for row in self._web_admin_queue)):
                return 202, {"id": request_id}
            return 409, {"error": "result_expired"}
        if len(self._web_admin_queue) >= 32:
            return 429, {"error": "queue_full"}
        self._web_admin_queue.append((request_id, digest, body))
        self._web_admin_seen[request_id] = encoded
        while len(self._web_admin_seen) > 64:
            pending = self._web_admin_inflight | {
                row[0] for row in self._web_admin_queue}
            oldest = next((key for key in self._web_admin_seen if key not in pending), None)
            if oldest is None:
                break
            del self._web_admin_seen[oldest]
        return 202, {"id": request_id}

    def publish_web_options(self, snapshot):
        payload = _json_bytes(snapshot)
        if len(payload) > 4096:
            raise ValueError("web options snapshot too large")
        with self._lock:
            self._web_options_state = payload

    @property
    def voice_talker(self):
        """Detached station label for an optional Pygame status display."""
        with self._lock:
            peer = self._voice_talker
            return None if peer is None else peer.station

    @property
    def voice_enabled(self):
        with self._lock:
            return self._voice_enabled

    def set_voice_enabled(self, enabled):
        if type(enabled) is not bool or self.web_auth is None:
            raise ValueError("web-host voice option requires a bool")
        with self._lock:
            self._voice_enabled = enabled
            if not enabled:
                self._voice_talker = None
                for peer in self._voice_peers.values():
                    peer.outgoing.clear()

    def _voice_valid_locked(self, peer):
        session = self._sessions_v2.get(peer.digest)
        lease = None if session is None else session["leases"].get(peer.station)
        return (self._running and self._voice_enabled
                and self._voice_peers.get(peer.digest) is peer
                and session is peer.session and lease is not None
                and lease["generation"] == peer.lease_generation
                and session["active_station"] == peer.station
                and session["active_generation"] == peer.active_generation)

    def _voice_status_locked(self):
        talker = self._voice_talker
        payload = _json_bytes({"type": "talker",
                               "station": None if talker is None else talker.station})
        for peer in self._voice_peers.values():
            peer.outgoing.append((1, payload))

    def _voice_disconnect_locked(self, peer):
        if self._voice_peers.get(peer.digest) is peer:
            del self._voice_peers[peer.digest]
        if self._voice_talker is peer:
            self._voice_talker = None
            self._voice_status_locked()

    def publish_web_proposals(self, snapshot):
        payload = _json_bytes(snapshot)
        if len(payload) > 4096:
            raise ValueError("web proposals too large")
        with self._lock:
            self._web_proposals = snapshot

    def revoke(self):
        """Begin a new game/server security session and rotate its join code."""
        with self._lock:
            self._revoke_locked(rotate_code=True)
            self._pair_failures.clear()

    @property
    def solo_mode(self) -> bool:
        with self._lock:
            return self._solo

    def solo_browser_present(self, max_age=5.0):
        """Whether the paired solo browser polled its session within ``max_age`` s.

        Host-local liveness only; it never grants or clears any authority.
        """
        with self._lock:
            self._expire_locked()
            if not (self._running and self._solo):
                return False
            now = time.monotonic()
            return any(session["solo_host"] and 0 <= now - session["presence"] <= max_age
                       for session in self._sessions_v2.values())

    def set_solo_mode(self, enabled):
        """Switch between crew and solo operation; every change is a new security session.

        Solo mode is an explicit host decision: a single paired browser holds all
        nine stations at once and may use the host command surface. Changing the
        mode revokes all sessions and rotates the join code, so a client can never
        carry authority across the switch.
        """
        if type(enabled) is not bool:
            raise ValueError("solo mode must be a bool")
        with self._lock:
            if enabled is not self._solo:
                self._solo = enabled
                self._revoke_locked(rotate_code=True)
                self._pair_failures.clear()

    @staticmethod
    def _solo_grants(station):
        return CommanderServer._station_grants(station)

    def _solo_grant_all_locked(self, session, active=None):
        """Lease every station of one side to the single solo session with full
        grants: the frigate's nine, or the boat's six when ``active`` is a boat
        station (the solo player chose to play the submarine)."""
        stations = OPFOR_ROLES if role_side(active) == "opfor" else STATIONS
        for station in stations:
            self._station_generations[station] += 1
            session["leases"][station] = {
                "generation": self._station_generations[station],
                "grants": self._solo_grants(station),
            }
        session["requests"].clear()
        session["simlog"] = True
        session["solo_host"] = True
        session["host_generation"] += 1
        session["active_station"] = None
        self._set_active_station_locked(
            session, active if active in session["leases"] else stations[0])

    def _solo_switch_side_locked(self, session, station):
        """The solo player picks the other unit: all stations change side."""
        for held in tuple(session["leases"]):
            self._release_station_locked(session, held, "role_revoked")
        self._solo_grant_all_locked(session, station)

    def solo_rebase(self):
        """Keep the solo session across a world replacement, as a fresh authority.

        Session, cookie, CSRF and command history survive so the browser can read
        the result of the very command that replaced the world. Every queued or
        held command is rejected, every station is re-leased under a new
        generation and the active generation advances, so anything the browser
        prepared for the old world fails closed. The join code is not rotated.
        """
        with self._lock:
            self._expire_locked()
            self._clear_sonar_audio_locked()
            self._clear_helicopter_audio_locked()
            self._clear_uboot_audio_locked()
            self._v2_proposals.clear()
            self._v2_host = _json_bytes({"protocol": 2, "phase": "blocked"})
            self._v2_events.clear()
            self._v2_private_events.clear()
            self._v2_simlogs.clear()
            for session in self._sessions_v2.values():
                self._reject_session_commands_locked(session, "session_revoked")
                if not session["solo_host"]:
                    self._clear_session_authority_locked(session)
                    continue
                active = session["active_station"]
                for station in tuple(session["leases"]):
                    self._release_station_locked(session, station, "session_revoked")
                self._solo_grant_all_locked(session, active)

    def client_statuses(self) -> list[dict]:
        """Return a detached, deterministic local-host roster."""
        with self._lock:
            self._expire_locked()
            station_order = {station: index for index, station in enumerate(ROLES)}
            sessions = sorted(
                self._sessions_v2.values(),
                key=lambda session: (
                    station_order.get(session["active_station"], len(ROLES)),
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
                    } for station in ROLES
                },
                "presence": session["presence"],
            } for session in sessions]

    def station_leased(self, station: str) -> bool:
        """Return whether a v2 client currently owns this station."""
        if station not in ROLES:
            raise ValueError("invalid station")
        with self._lock:
            self._expire_locked()
            return any(station in session["leases"]
                       for session in self._sessions_v2.values())

    def grant_station(self, client_id, station) -> bool:
        if not isinstance(client_id, str) or station not in ROLES:
            raise ValueError("invalid client or station")
        with self._lock:
            self._expire_locked()
            session = self._session_by_client_locked(client_id)
            if session is None or self._side_conflict(session, station):
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

    def resolve_station_request(self, client_id, station, request_generation, grants=None,
                                *, takeover=False) -> bool:
        """Atomically decide an exact pending request; only a host decision with
        ``takeover`` hands a held station over (with its full rights)."""
        capabilities = {"command", "direct_fire", "sonar_audio"}
        if (type(client_id) is not str or station not in ROLES
                or type(request_generation) is not int
                or grants is not None and (type(grants) is not dict
                    or set(grants) != capabilities
                    or any(type(value) is not bool for value in grants.values()))):
            return False
        if grants is not None and (
                not grants["command"]
                or grants["direct_fire"] and station not in DIRECT_FIRE_ROLES
                or grants["sonar_audio"] and station not in SONAR_AUDIO_ROLES):
            return False
        with self._lock:
            self._expire_locked()
            session = self._session_by_client_locked(client_id)
            if session is None or session["requests"].get(station) != request_generation:
                return False
            if grants is None:
                del session["requests"][station]
                return True
            holder = next((item for item in self._sessions_v2.values()
                           if station in item["leases"]), None)
            if (holder is not None and not takeover) or self._side_conflict(session, station):
                return False
            if holder is not None:
                self._release_station_locked(holder, station)
            else:
                self._station_generations[station] += 1
            session["leases"][station] = {
                "generation": self._station_generations[station],
                "grants": dict(grants),
            }
            del session["requests"][station]
            self._set_active_station_locked(session, station)
            return True

    def reject_station_request(self, client_id, station=None, request_generation=None) -> bool:
        if (not isinstance(client_id, str) or station is not None and station not in ROLES
                or request_generation is not None and type(request_generation) is not int):
            raise ValueError("invalid client")
        with self._lock:
            self._expire_locked()
            session = self._session_by_client_locked(client_id)
            if session is None:
                return False
            if station is None:
                station = next((item for item in ROLES if item in session["requests"]), None)
            if station is None or station not in session["requests"]:
                return False
            if (request_generation is not None
                    and session["requests"][station] != request_generation):
                return False
            del session["requests"][station]
            return True

    def revoke_station(self, station) -> bool:
        if station not in ROLES:
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
            if station not in ROLES:
                if explicit_station:
                    raise ValueError("invalid client grant")
                return False
            lease = session["leases"].get(station)
            if lease is None:
                return False
            if capability == "direct_fire" and enabled and (
                    not lease["grants"]["command"]
                    or station not in DIRECT_FIRE_ROLES):
                return False
            if capability == "sonar_audio" and enabled and station not in SONAR_AUDIO_ROLES:
                return False
            changed = lease["grants"][capability] != enabled
            lease["grants"][capability] = enabled
            if capability == "command" and not enabled:
                lease["grants"]["direct_fire"] = False
                self._reject_station_commands_locked(session, station, "grant_revoked")
                if changed and session["active_station"] == station:
                    session["active_generation"] += 1
                    session["held_commands"].clear()
            elif capability == "direct_fire" and not enabled:
                self._reject_direct_fire_commands_locked(session, station)
            elif capability == "sonar_audio" and not enabled:
                self._clear_role_audio_locked(station)
            return True

    def activate_station(self, client_id, station, station_generation) -> bool:
        if (not isinstance(client_id, str) or station not in ROLES
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
            self._clear_sonar_audio_locked()
            self._clear_helicopter_audio_locked()
            self._clear_uboot_audio_locked()
            for session in self._sessions_v2.values():
                self._reject_session_commands_locked(session, reason)

    def drain_commands_v2(self) -> list[V2CommandEnvelope]:
        """Detach one deterministic frame batch in station/client/FIFO order."""
        with self._lock:
            self._expire_locked()
            # Host controls run first in a frame, then stations in fixed order.
            order = {station: index for index, station in enumerate(ROLES)}
            order[HOST_ROLE] = -1
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
            is_host = envelope.role == HOST_ROLE
            if not _v2_command_valid(body) or spec is None:
                reason = "invalid_schema"
            elif ((not session["solo_host"] if is_host
                   else envelope.role not in session["leases"])
                  or body["station"] != envelope.role):
                reason = "role_revoked"
            elif ((session["host_generation"] if is_host
                   else session["leases"][envelope.role]["generation"])
                  != envelope.lease_generation
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
            elif (not is_host
                  and not session["leases"][envelope.role]["grants"]["command"]):
                reason = "grant_revoked"
            elif (type(now) not in (int, float) or not math.isfinite(now)
                  or not 0 <= now - envelope.received_at <= _V2_COMMAND_MAX_AGE_S):
                reason = "expired"
            elif phase not in spec.phases:
                reason = "phase_blocked"
            elif body["world_session"] != world_session:
                reason = "stale_world_session"
            elif not is_host and body["world_epoch"] != world_epoch:
                # Host controls bind the world session only: load and new game move
                # the epoch themselves, and queued input is invalidated anyway.
                reason = "stale_world_epoch"
            elif (spec.revision_bound
                  and body["resource_revision"] != resource_revision):
                # Host controls are never revision-bound: they reference no resource.
                reason = "revision_conflict"
            else:
                try:
                    applied = apply(body["action"], dict(body["params"]))
                except Exception as exc:
                    # Never log params/credentials/client addresses; type + action name only.
                    _log.warning("command apply failed: %s (%s)",
                                 body["action"], type(exc).__name__)
                    applied = False
                reason = ("ok" if applied is True or applied == "ok" else applied
                          if type(applied) is str and applied in {
                              "bridge_down", "sonar_down", "opz_down",
                              "engine_down", "radio_down", "flightdeck_down",
                               "invalid_value", "phase_blocked", "unknown_ref",
                               "stale_ref", "source_owned", "fusion_rejected",
                               "ineligible_track", "proposal_pending",
                               "not_ready", "no_solution", "no_buoys",
                               "water_required", "tas_fault", "invalid_target",
                               "roe_blocked", "not_located", "not_classified",
                               "salvo_limit", "empty", "no_tube",
                               "weapons_down", "weapons_degraded", "out_of_range",
                                "opz_degraded", "active_limit", "no_fuel",
                                "weather_unsafe", "no_save", "save_failed",
                                *UBOOT_REASONS}
                          else "action_rejected")
            return self._finish_v2_locked(
                session, envelope, "applied" if reason == "ok" else "rejected", reason)

    def publish_v2(self, states: dict, charts: dict):
        """Atomically replace immutable, role-keyed protocol-v2 publications."""
        expected = {None, *ROLES}
        status_fields = {"protocol", "version", "session", "epoch", "revision",
                         "seq", "phase", "role", "chart_revision"}
        assigned_fields = status_fields | {"clock", "environment", "mission",
                                           "autocrew", "autocrew_overview", "audio",
                                           "weather_station", "plot"}
        if (not isinstance(states, dict) or not isinstance(charts, dict)
                or set(states) != expected or set(charts) != expected):
            raise ValueError("invalid v2 publication")
        encoded_states, encoded_charts = {}, {}
        compact_sonar = None
        # Roles with identical visibility share one chart object, so it is
        # serialised once per publication instead of once per role.
        chart_bytes_by_object = {}
        for role in (None, *ROLES):
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
                state_bytes = _json_bytes(state)
                chart_bytes = chart_bytes_by_object.get(id(chart))
                if chart_bytes is None:
                    chart_bytes = chart_bytes_by_object[id(chart)] = _json_bytes(chart)
            except (TypeError, ValueError, OverflowError):
                raise ValueError("invalid v2 publication") from None
            if len(state_bytes) > STATE_MAX_BYTES or len(chart_bytes) > CHART_MAX_BYTES:
                raise ValueError("v2 publication size limit exceeded")
            encoded_states[role], encoded_charts[role] = state_bytes, chart_bytes
            if (role == "sonar" and state.get("role") == "sonar"
                    and isinstance(state.get("sonar"), dict)
                    and isinstance(state["sonar"].get("visualization"), dict)):
                # Shallow copies down to the streamed arrays: the poll view
                # shares every other (immutable, already encoded) value.
                visual = dict(state["sonar"]["visualization"])
                for name, keys in (("broadband", ("history",)),
                                   ("lofar", ("history", "spectrum")),
                                   ("demon", ("history", "spectrum"))):
                    section = visual.get(name)
                    if isinstance(section, dict):
                        visual[name] = dict(section, **{key: [] for key in keys})
                compact_sonar = _json_bytes(
                    dict(state, sonar=dict(state["sonar"], visualization=visual)))
        with self._lock:
            self._v2_states = encoded_states
            self._v2_charts = encoded_charts
            self._v2_sonar_compact_state = compact_sonar or encoded_states["sonar"]
            self._sonar_stream_sequence += 1
            packed = (_sonar_stream_payload(states["sonar"],
                                             self._sonar_stream_sequence)
                      if states["sonar"].get("role") == "sonar" else None)
            if packed is None:
                self._sonar_stream_context = None
                self._sonar_stream_payload = None
            else:
                self._sonar_stream_context, self._sonar_stream_payload = packed
            packed = (_sonar_stream_payload(states["uboot_sonar"],
                                             self._sonar_stream_sequence, "uboot_sonar")
                      if states["uboot_sonar"].get("role") == "uboot_sonar" else None)
            if packed is None:
                self._uboot_stream_context = None
                self._uboot_stream_payload = None
            else:
                self._uboot_stream_context, self._uboot_stream_payload = packed
            self._sonar_stream_condition.notify_all()

    def publish_host_v2(self, host: dict):
        """Publish the solo host view; only sessions with the host surface read it."""
        if (type(host) is not dict or host.get("protocol") != 2
                or type(host.get("phase")) is not str):
            raise ValueError("invalid v2 host publication")
        try:
            encoded = _json_bytes(host)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("invalid v2 host publication") from None
        if len(encoded) > HOST_MAX_BYTES:
            raise ValueError("v2 host publication size limit exceeded")
        with self._lock:
            self._v2_host = encoded

    @staticmethod
    def _proposal_value(value, navigation):
        if value is None:
            return True
        if type(value) is not dict or value.get("status") not in {
                "pending", "accepted", "rejected", "expired"}:
            return False
        if navigation:
            return (set(value) == {"course", "speed_kn", "status"}
                    and (value["course"] is None or type(value["course"]) in (int, float)
                         and math.isfinite(value["course"])
                         and 0 <= value["course"] < 360)
                    and (value["speed_kn"] is None or type(value["speed_kn"]) in (int, float)
                         and math.isfinite(value["speed_kn"])
                         and 0 <= value["speed_kn"] <= SHIP_SPEED_MAX_KN)
                    and (value["course"] is not None or value["speed_kn"] is not None))
        return (set(value) == {"ref", "label", "status"}
                and _ref(value["ref"]) and type(value["label"]) is str
                and 1 <= len(value["label"]) <= 64)

    def publish_proposals_v2(self, *, world_session, world_epoch,
                             target_authority=None, target=None,
                             navigation_authority=None, navigation=None):
        """Publish proposal views only to their exact current origin sessions."""
        if (not _ref(world_session) or type(world_epoch) is not int
                or not 0 <= world_epoch <= _SAFE_INTEGER_MAX
                or not self._proposal_value(target, False)
                or not self._proposal_value(navigation, True)
                or (target is None) != (target_authority is None)
                or (navigation is None) != (navigation_authority is None)
                or target_authority is not None and (
                    type(target_authority) is not V2CommandEnvelope
                    or target_authority.role != "sonar")
                or navigation_authority is not None and (
                    type(navigation_authority) is not V2CommandEnvelope
                    or navigation_authority.role != "bridge")):
            raise ValueError("invalid v2 proposal publication")
        with self._lock:
            self._expire_locked()
            # One record per (session, role): a session that holds several
            # stations may have a sonar target and a bridge navigation proposal
            # pending at once, and each is only served to its own active role.
            records = {}
            for authority, kind, value in (
                    (target_authority, "target", target),
                    (navigation_authority, "navigation", navigation)):
                if authority is None or not self._authority_current_locked(authority):
                    continue
                record = records.setdefault((authority.session_digest, authority.role), {
                    "protocol": 2, "session": world_session, "epoch": world_epoch,
                    "role": authority.role, "target": None, "navigation": None})
                record[kind] = dict(value)
            self._v2_proposals = {key: _json_bytes(value)
                                  for key, value in records.items()}

    @staticmethod
    def _event_rows(rows):
        if type(rows) is not list or len(rows) > EVENTS_MAX:
            return False
        previous = 0
        for row in rows:
            if (type(row) is not dict
                    or set(row) != {"seq", "kind", "severity", "message"}
                    or type(row["seq"]) is not int
                    or not previous < row["seq"] <= _SAFE_INTEGER_MAX
                    or type(row["kind"]) is not str or not 1 <= len(row["kind"]) <= 32
                    or row["severity"] not in ("info", "warning")
                    or type(row["message"]) is not str
                    or not 1 <= len(row["message"]) <= 512):
                return False
            previous = row["seq"]
        return True

    def publish_events_v2(self, *, world_session, world_epoch, latest_seq,
                          events_by_role, private_events=()):
        """Publish bounded role events plus proposal events for exact origins."""
        if (not _ref(world_session) or type(world_epoch) is not int
                or not 0 <= world_epoch <= _SAFE_INTEGER_MAX
                or type(latest_seq) is not int
                or not 0 <= latest_seq <= _SAFE_INTEGER_MAX
                or type(events_by_role) is not dict
                or set(events_by_role) != set(ROLES)
                or any(not self._event_rows(rows)
                       or rows and rows[-1]["seq"] > latest_seq
                       for rows in events_by_role.values())
                or type(private_events) not in (list, tuple)):
            raise ValueError("invalid v2 event publication")
        with self._lock:
            self._expire_locked()
            base = {}
            for role in ROLES:
                base[role] = _json_bytes({
                    "protocol": 2, "session": world_session, "epoch": world_epoch,
                    "role": role, "latest_seq": latest_seq,
                    "events": [dict(row) for row in events_by_role[role]]})
            private = {}
            for item in private_events:
                if (type(item) not in (list, tuple) or len(item) != 2
                        or type(item[0]) is not V2CommandEnvelope
                        or not self._event_rows([item[1]])
                        or item[1]["seq"] > latest_seq):
                    raise ValueError("invalid v2 event publication")
                authority, event = item
                if not self._authority_current_locked(authority):
                    continue
                private.setdefault(authority.session_digest, []).append(dict(event))
            encoded_private = {}
            for digest, rows in private.items():
                session = self._sessions_v2[digest]
                role = session["active_station"]
                merged = sorted(events_by_role[role] + rows,
                                key=lambda row: row["seq"])[-EVENTS_MAX:]
                encoded_private[digest] = _json_bytes({
                    "protocol": 2, "session": world_session, "epoch": world_epoch,
                    "role": role, "latest_seq": latest_seq, "events": merged})
            self._v2_events = base
            self._v2_private_events = encoded_private

    def publish_simlog_v2(self, *, world_session, world_epoch, entries_by_role):
        """Publish bounded host-granted histories including diagnostic truth."""
        if (not _ref(world_session) or type(world_epoch) is not int
                or not 0 <= world_epoch <= _SAFE_INTEGER_MAX
                or type(entries_by_role) is not dict
                or set(entries_by_role) != set(ROLES)):
            raise ValueError("invalid v2 simlog publication")
        encoded = {}
        for role, entries in entries_by_role.items():
            if type(entries) is not list or len(entries) > SIMLOG_ENTRIES_MAX:
                raise ValueError("invalid v2 simlog publication")
            previous = 0
            detached = []
            for entry in entries:
                if (type(entry) is not dict
                        or set(entry) != {"seq", "t", "stamp", "state", "truth"}
                        or type(entry["seq"]) is not int
                        or not previous < entry["seq"] <= _SAFE_INTEGER_MAX
                        or type(entry["t"]) not in (int, float)
                        or not math.isfinite(entry["t"]) or entry["t"] < 0
                        or type(entry["stamp"]) is not str
                        or len(entry["stamp"]) > 32
                        or type(entry["state"]) is not dict
                        or entry["state"].get("protocol") != 2
                        or entry["state"].get("role") != role
                        or entry["state"].get("session") != world_session
                        or entry["state"].get("epoch") != world_epoch
                        or type(entry["truth"]) is not dict
                        or set(entry["truth"]) != {
                            "mission_t", "result", "world", "ship",
                            "weapons", "subs", "surfaces", "animals", "torpedoes",
                            "enemy_torpedoes", "decoys", "asms", "essms", "asrocs",
                            "nixies", "buoys", "helo", "flights", "raiders", "radars"}
                        or any(type(entry["truth"].get(key)) is not list
                               or len(entry["truth"][key]) > 1024
                               for key in ("subs", "surfaces", "animals", "torpedoes",
                                           "enemy_torpedoes", "decoys", "asms", "essms",
                                           "asrocs", "nixies", "buoys", "flights",
                                           "raiders"))):
                    raise ValueError("invalid v2 simlog publication")
                previous = entry["seq"]
                detached.append(entry)
            payload = _json_bytes({
                "protocol": 2, "session": world_session, "epoch": world_epoch,
                "role": role, "entries": detached})
            if len(payload) > SIMLOG_MAX_BYTES:
                raise ValueError("v2 simlog publication size limit exceeded")
            encoded[role] = payload
        with self._lock:
            self._v2_simlogs = encoded

    def clear_sonar_audio(self):
        """Clear every live-audio byte and context without touching a session."""
        with self._lock:
            self._clear_sonar_audio_locked()

    def clear_helicopter_audio(self):
        with self._lock:
            self._clear_helicopter_audio_locked()

    def clear_uboot_audio(self):
        with self._lock:
            self._clear_uboot_audio_locked()

    def mark_audio_discontinuity(self, role: str) -> bool:
        """Skip one sequence number of a live stream (main thread only).

        The receiver restarted (a retuned listening bearing), so the next block
        does not continue the previous waveform. Every browser transport sees
        the gap and crossfades instead of joining unrelated audio. Nothing is
        marked on an unbound stream.
        """
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError("audio discontinuity requires the main thread")
        if role not in SONAR_AUDIO_ROLES:
            raise ValueError("unknown audio role")
        with self._lock:
            if self._audio_ring(role)[1] is None:
                return False
            if role == "sonar":
                self._sonar_audio_sequence += 1
            elif role == "helicopter":
                self._helicopter_audio_sequence += 1
            else:
                self._uboot_audio_sequence += 1
            self.audio_stream_stats_locked(role)["discontinuities"] += 1
            return True

    def audio_stream_stats_locked(self, role: str) -> dict:
        """Bounded per-role transport counters (diagnostics only)."""
        stats = self._audio_stats.get(role)
        if stats is None:
            stats = self._audio_stats[role] = {
                "skipped_blocks": 0, "send_timeouts": 0, "discontinuities": 0,
                "connections": 0}
        return stats

    def audio_stream_stats(self) -> dict:
        """Detached copy of the per-role audio transport counters."""
        with self._lock:
            return {role: dict(self.audio_stream_stats_locked(role))
                    for role in SONAR_AUDIO_ROLES}

    def _uboot_audio_holder_locked(self):
        return next(((digest, session) for digest, session
                     in self._sessions_v2.items()
                     if "uboot_sonar" in session["leases"]
                     and session["active_station"] == "uboot_sonar"), None)

    def prepare_uboot_audio(self, *, world_session: str, world_epoch: int):
        """Bind an empty stream to the current granted submarine sonar holder."""
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError("uboot audio preparation requires the main thread")
        if (type(world_session) is not str or not world_session
                or type(world_epoch) is not int or world_epoch < 0):
            raise ValueError("invalid uboot audio context")
        with self._lock:
            self._expire_locked()
            holder = self._uboot_audio_holder_locked()
            if (holder is None
                    or not holder[1]["leases"]["uboot_sonar"]["grants"]["sonar_audio"]):
                self._clear_uboot_audio_locked()
                return None
            generation = holder[1]["leases"]["uboot_sonar"]["generation"]
            context = (holder[0], generation, holder[1]["active_generation"],
                       world_session, world_epoch)
            if context != self._uboot_audio_context:
                self._clear_uboot_audio_locked()
                self._uboot_audio_context = context
            return generation

    def publish_uboot_audio(self, pcm: bytes, *, world_session: str,
                            world_epoch: int, station_generation: int):
        """Publish one submarine sonar receiver block from the main thread."""
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError("uboot audio publication requires the main thread")
        if (type(pcm) is not bytes or len(pcm) != SONAR_AUDIO_BYTES
                or type(world_session) is not str or not world_session
                or type(world_epoch) is not int or world_epoch < 0
                or type(station_generation) is not int or station_generation < 0):
            raise ValueError("invalid uboot audio publication")
        with self._lock:
            self._expire_locked()
            holder = self._uboot_audio_holder_locked()
            if holder is None:
                self._clear_uboot_audio_locked()
                return False
            lease = holder[1]["leases"]["uboot_sonar"]
            context = (holder[0], station_generation,
                       holder[1]["active_generation"], world_session, world_epoch)
            if (not lease["grants"]["sonar_audio"]
                    or lease["generation"] != station_generation
                    or context != self._uboot_audio_context):
                self._clear_uboot_audio_locked()
                return False
            if self._uboot_audio_sequence >= _SAFE_INTEGER_MAX:
                self._clear_uboot_audio_locked()
                self._uboot_audio_sequence = 0
                self._uboot_audio_context = context
            self._uboot_audio_sequence += 1
            self._uboot_audio.append((self._uboot_audio_sequence, pcm))
            self._audio_condition.notify_all()
            return True

    def prepare_helicopter_audio(self, *, world_session: str, world_epoch: int):
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError("helicopter audio preparation requires the main thread")
        with self._lock:
            self._expire_locked()
            holder = next(((digest, session) for digest, session
                           in self._sessions_v2.items()
                           if "helicopter" in session["leases"]
                           and session["active_station"] == "helicopter"), None)
            if (holder is None or not holder[1]["leases"]["helicopter"]
                    ["grants"]["sonar_audio"]):
                self._clear_helicopter_audio_locked()
                return None
            generation = holder[1]["leases"]["helicopter"]["generation"]
            context = (holder[0], generation, holder[1]["active_generation"],
                       world_session, world_epoch)
            if context != self._helicopter_audio_context:
                self._clear_helicopter_audio_locked()
                self._helicopter_audio_context = context
            return generation

    def publish_helicopter_audio(self, pcm: bytes, *, world_session: str,
                                 world_epoch: int, station_generation: int):
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError("helicopter audio publication requires the main thread")
        if type(pcm) is not bytes or len(pcm) != SONAR_AUDIO_BYTES:
            raise ValueError("invalid helicopter audio block")
        with self._lock:
            self._expire_locked()
            holder = next(((digest, session) for digest, session
                           in self._sessions_v2.items()
                           if "helicopter" in session["leases"]
                           and session["active_station"] == "helicopter"), None)
            if holder is None:
                self._clear_helicopter_audio_locked()
                return False
            context = (holder[0], station_generation,
                       holder[1]["active_generation"], world_session, world_epoch)
            if (not holder[1]["leases"]["helicopter"]["grants"]["sonar_audio"]
                    or holder[1]["leases"]["helicopter"]["generation"]
                    != station_generation or context != self._helicopter_audio_context):
                self._clear_helicopter_audio_locked()
                return False
            if self._helicopter_audio_sequence >= _SAFE_INTEGER_MAX:
                self._clear_helicopter_audio_locked()
                self._helicopter_audio_sequence = 0
                self._helicopter_audio_context = context
            self._helicopter_audio_sequence += 1
            self._helicopter_audio.append((self._helicopter_audio_sequence, pcm))
            self._audio_condition.notify_all()
            return True

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
                self._sonar_audio_sequence = 0
                self._sonar_audio_context = context
            self._sonar_audio_sequence += 1
            self._sonar_audio.append((self._sonar_audio_sequence, pcm))
            self._audio_condition.notify_all()
            return True

_OVERLOAD_RESPONSE = (
    b"HTTP/1.1 503 Service Unavailable\r\n"
    b"Connection: close\r\n"
    b"Content-Length: 0\r\n"
    b"\r\n"
)
# Up to 9 stations poll at 2 Hz plus a sonar audio stream; headroom above that.
# Nine voice sockets, a sonar stream and short HTTP polls need separate slots.
_CONNECTION_SLOT_LIMIT = 28

class _HTTPServer(HTTPServer):
    allow_reuse_address = True
    request_queue_size = _CONNECTION_SLOT_LIMIT

    def __init__(self, address, owner, assets):
        self.owner = owner
        self.assets = assets
        self.slots = threading.BoundedSemaphore(_CONNECTION_SLOT_LIMIT)
        self.work_lock = threading.Lock()
        self.workers = {}
        self.upgrade_events = {}
        super().__init__(address, _Handler)
        host, port = self.server_address
        self.direct_hosts = {f"{host}:{port}"}
        if ipaddress.IPv4Address(host).is_loopback:
            self.direct_hosts.add(f"localhost:{port}")
        self.public_hosts = set()
        if owner.public_origin is not None:
            public = urlsplit(owner.public_origin)
            self.public_hosts.add(public.netloc)
            if public.port is None:
                # Some proxies forward the default HTTPS port explicitly.
                self.public_hosts.add(f"{public.netloc}:443")
        self.hosts = self.direct_hosts | self.public_hosts

    def allowed_origins(self, host) -> frozenset:
        """Exact browser origins valid for a request that reached ``host``.

        The web-host room is reachable only through its HTTPS proxy. The local
        listener accepts its direct LAN origin and, when configured, the proxy
        origin as well (a proxy may forward its own name or the upstream).
        """
        owner = self.owner
        if owner.web_auth is not None and owner.public_origin is not None:
            return frozenset((owner.public_origin,))
        origins = set()
        if owner.public_origin is not None:
            origins.add(owner.public_origin)
        if host in self.direct_hosts:
            origins.add(f"http://{host}")
        return frozenset(origins)

    def process_request(self, request, client_address):
        deadline = time.monotonic() + _CONNECTION_DEADLINE_S
        if not self.slots.acquire(blocking=False):
            try:
                request.sendall(_OVERLOAD_RESPONSE)
            except OSError:
                pass
            self.shutdown_request(request)
            return
        request.settimeout(1.5)
        worker = threading.Thread(target=self._work, args=(request, client_address, deadline),
                                  name="commander-request", daemon=True)
        with self.work_lock:
            self.workers[worker] = request
            self.upgrade_events[worker] = threading.Event()
        try:
            worker.start()
        except BaseException:
            with self.work_lock:
                self.workers.pop(worker)
                self.upgrade_events.pop(worker, None)
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
        with self.work_lock:
            upgraded = self.upgrade_events[threading.current_thread()]
        def interrupt_if_http():
            if not upgraded.is_set():
                self._interrupt_connection(request)
        timer = threading.Timer(max(0.0, deadline - time.monotonic()),
                                interrupt_if_http)
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
                self.upgrade_events.pop(threading.current_thread(), None)
            self.slots.release()

    def mark_upgraded(self):
        with self.work_lock:
            event = self.upgrade_events.get(threading.current_thread())
            if event is None:
                return False
            event.set()
            return True

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
            ("Permissions-Policy", "camera=(), microphone=(self), geolocation=()"),
            ("Content-Security-Policy", "default-src 'none'; script-src 'self'; "
             "style-src 'self'; img-src 'self'; font-src 'self'; connect-src 'self'; "
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
                    or any((c < 32 and c != 9) or c > 126 for c in value[:-2])):
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
        for name in ("Host", "Origin", "Content-Length", "Content-Type",
                     "Authorization", "Cookie", "X-U-Jagd-CSRF", "Upgrade",
                     "X-U-Jagd-Request-ID",
                     "Sec-WebSocket-Key", "Sec-WebSocket-Version",
                     "Sec-WebSocket-Protocol"):
            if len(self.headers.get_all(name, [])) > 1:
                self.send_error(400)
                return
        host = self.headers.get("Host")
        origin = self.headers.get("Origin")
        if host not in self.server.hosts:
            self.send_error(403)
            return
        if ((origin is not None and origin not in self.server.allowed_origins(host))
                or (self.command == "POST" and origin is None)):
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

    @staticmethod
    def _session_v2_body(session, sessions):
        occupied = {station: candidate for candidate in sessions.values()
                    for station in candidate["leases"]}
        active = session["active_station"]
        active_lease = session["leases"].get(active)
        requested = next((station for station in ROLES
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
            # Host command surface: only a solo session carries one.
            "host": ({"generation": session["host_generation"]}
                     if session["solo_host"] else None),
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
                for station in ROLES
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

    def _via_https_proxy(self) -> bool:
        """This request came through the HTTPS proxy, not the direct LAN URL."""
        owner = self.server.owner
        return owner.public_origin is not None and (
            owner.web_auth is not None
            or self.headers.get("Origin") == owner.public_origin
            or self.headers.get("Host") in self.server.public_hosts)

    def _v2_cookie(self, token):
        # Secure only on the HTTPS path: a browser drops a Secure cookie that
        # arrives over the plain-HTTP LAN address.
        secure = "; Secure" if self._via_https_proxy() else ""
        return f"{_V2_COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict{secure}"

    def _clear_v2_cookie(self):
        secure = "; Secure" if self._via_https_proxy() else ""
        return (f"{_V2_COOKIE}=; Path=/; HttpOnly; SameSite=Strict; "
                f"Max-Age=0{secure}")

    def _v2_unauthorized(self, presented):
        self._reply(401, {"error": "unauthorized"},
                    set_cookie=self._clear_v2_cookie() if presented else None)

    def _sonar_websocket(self):
        """Stream immutable projected samples to one active Sonar client."""
        owner = self.server.owner
        allowed_origins = self.server.allowed_origins(self.headers.get("Host"))
        if (self.headers.get("Origin") not in allowed_origins
                or self.headers.get("Upgrade", "").lower() != "websocket"
                or "upgrade" not in {item.strip().lower() for item in
                                      self.headers.get("Connection", "").split(",")}
                or self.headers.get("Sec-WebSocket-Version") != "13"
                or self.headers.get("Sec-WebSocket-Protocol") != "u-jagd-sonar-v2"):
            self.send_error(400)
            return
        key = self.headers.get("Sec-WebSocket-Key")
        try:
            decoded_key = base64.b64decode(key or "", validate=True)
        except (ValueError, TypeError):
            decoded_key = b""
        if len(decoded_key) != 16:
            self.send_error(400)
            return
        client_token = object()
        with owner._lock:
            owner._expire_locked()
            try:
                session, digest, presented = self._authenticated_v2_locked(renew=True)
            except (UnicodeEncodeError, ValueError):
                self.send_error(400)
                return
            if session is None:
                self._v2_unauthorized(presented)
                return
            stream_role = session["active_station"]
            lease = session["leases"].get(stream_role)
            stream_context, stream_payload = owner._stream_for(stream_role)
            if (stream_role not in SONAR_ROLES or lease is None
                    or stream_payload is None or stream_context is None):
                self.send_error(403)
                return
            if digest in owner._sonar_stream_clients:
                self._reply(409, {"error": "stream_exists"})
                return
            station_generation = lease["generation"]
            active_generation = session["active_generation"]
            world_context = stream_context
            owner._sonar_stream_clients[digest] = client_token
        accept = base64.b64encode(hashlib.sha1(
            key.encode("ascii") + _WEBSOCKET_GUID).digest()).decode("ascii")
        self.send_response_only(101)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.send_header("Sec-WebSocket-Protocol", "u-jagd-sonar-v2")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not self.server.mark_upgraded():
            return
        last_sequence = -1
        try:
            while True:
                with owner._sonar_stream_condition:
                    owner._expire_locked()
                    current = owner._sessions_v2.get(digest)
                    lease = None if current is None else current["leases"].get(stream_role)
                    stream_context, stream_payload = owner._stream_for(stream_role)
                    valid = (owner._running and current is session
                             and owner._sonar_stream_clients.get(digest) is client_token
                             and current["active_station"] == stream_role
                             and lease is not None
                             and lease["generation"] == station_generation
                             and current["active_generation"] == active_generation
                             and stream_context == world_context)
                    if not valid:
                        break
                    if owner._sonar_stream_sequence == last_sequence:
                        owner._sonar_stream_condition.wait(timeout=1.0)
                        continue
                    last_sequence = owner._sonar_stream_sequence
                    payload = stream_payload
                    current["last_get"] = time.monotonic()
                if payload is not None:
                    self.connection.sendall(_websocket_frame(payload))
        except (OSError, TimeoutError, ValueError):
            pass
        finally:
            with owner._lock:
                if owner._sonar_stream_clients.get(digest) is client_token:
                    del owner._sonar_stream_clients[digest]
            try:
                self.connection.sendall(_websocket_frame(
                    struct.pack("!H", 1008), opcode=8))
            except OSError:
                pass
        self.close_connection = True

    def _audio_websocket(self, role, after=None):
        """Send detached PCM to the current audio lease; never read game state.

        ``after`` is the browser's last accepted sequence: a reconnect resumes
        behind it instead of re-sending blocks the worklet already holds.
        """
        owner = self.server.owner
        allowed_origins = self.server.allowed_origins(self.headers.get("Host"))
        if (self.headers.get("Origin") not in allowed_origins
                or self.headers.get("Upgrade", "").lower() != "websocket"
                or "upgrade" not in {part.strip().lower() for part in
                                      self.headers.get("Connection", "").split(",")}
                or self.headers.get("Sec-WebSocket-Version") != "13"
                or self.headers.get("Sec-WebSocket-Protocol") != "u-jagd-audio-v2"):
            self.send_error(400)
            return
        key = self.headers.get("Sec-WebSocket-Key")
        try:
            valid_key = len(base64.b64decode(key or "", validate=True)) == 16
        except (ValueError, TypeError):
            valid_key = False
        if not valid_key:
            self.send_error(400)
            return
        marker = object()
        with owner._audio_condition:
            owner._expire_locked()
            try:
                session, digest, presented = self._authenticated_v2_locked(renew=True)
            except (UnicodeEncodeError, ValueError):
                self.send_error(400)
                return
            if session is None:
                self._v2_unauthorized(presented)
                return
            lease = session["leases"].get(role)
            context = owner._audio_ring(role)[1]
            if (session["active_station"] != role or lease is None
                    or not lease["grants"]["sonar_audio"] or context is None
                    or context[:3] != (digest, lease["generation"],
                                       session["active_generation"])):
                self.send_error(403)
                return
            client_key = (digest, role)
            if client_key in owner._audio_clients:
                self._reply(409, {"error": "stream_exists"})
                return
            owner._audio_clients[client_key] = marker
            owner.audio_stream_stats_locked(role)["connections"] += 1
        accept = base64.b64encode(hashlib.sha1(
            key.encode("ascii") + _WEBSOCKET_GUID).digest()).decode("ascii")
        self.send_response_only(101)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.send_header("Sec-WebSocket-Protocol", "u-jagd-audio-v2")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not self.server.mark_upgraded():
            with owner._audio_condition:
                owner._audio_clients.pop(client_key, None)
            return
        try:
            # Send each 250 ms block at once; Nagle would batch small frames
            # into bursts the browser has to absorb as jitter.
            self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except (OSError, AttributeError):
            pass
        try:
            self.connection.settimeout(AUDIO_SOCKET_TIMEOUT_S)
        except OSError:
            pass
        last_sequence = after
        try:
            while True:
                with owner._audio_condition:
                    owner._expire_locked()
                    current = owner._sessions_v2.get(digest)
                    lease = None if current is None else current["leases"].get(role)
                    audio_context = owner._audio_ring(role)[1]
                    if (not owner._running or current is not session
                            or owner._audio_clients.get(client_key) is not marker
                            or current["active_station"] != role or lease is None
                            or not lease["grants"]["sonar_audio"]
                            or audio_context != context):
                        break
                    blocks = owner._audio_ring(role)[0]
                    available = [entry for entry in blocks
                                 if last_sequence is None or entry[0] > last_sequence]
                    if not available:
                        owner._audio_condition.wait(timeout=.5)
                        continue
                    # A slow socket skips old samples; never build an unbounded
                    # per-client backlog or hold the simulation lock while sending.
                    if len(available) > SONAR_AUDIO_RESUME_BLOCKS:
                        owner.audio_stream_stats_locked(role)["skipped_blocks"] += (
                            len(available) - SONAR_AUDIO_RESUME_BLOCKS)
                        sequence, pcm = available[-SONAR_AUDIO_RESUME_BLOCKS]
                    else:
                        sequence, pcm = available[0]
                    last_sequence = sequence
                    current["last_get"] = time.monotonic()
                self.connection.sendall(_websocket_frame(
                    b"UJA2" + struct.pack("<Q", sequence) + pcm))
        except TimeoutError:
            with owner._audio_condition:
                owner.audio_stream_stats_locked(role)["send_timeouts"] += 1
        except (OSError, ValueError):
            pass
        finally:
            with owner._audio_condition:
                if owner._audio_clients.get(client_key) is marker:
                    del owner._audio_clients[client_key]
            try:
                self.connection.sendall(_websocket_frame(
                    struct.pack("!H", 1008), opcode=8))
            except OSError:
                pass
        self.close_connection = True

    def _voice_websocket(self):
        """Relay authenticated, leased PTT audio without touching simulation."""
        owner = self.server.owner
        allowed_origins = self.server.allowed_origins(self.headers.get("Host"))
        protocols = [item.strip() for item in
                     self.headers.get("Sec-WebSocket-Protocol", "").split(",")]
        if (owner.web_auth is None or self.headers.get("Origin") not in allowed_origins
                or self.headers.get("Upgrade", "").lower() != "websocket"
                or "upgrade" not in {item.strip().lower() for item in
                                      self.headers.get("Connection", "").split(",")}
                or self.headers.get("Sec-WebSocket-Version") != "13"
                or len(protocols) != 2 or protocols[0] != "u-jagd-voice-v2"
                or not protocols[1].startswith("ujagd-csrf.")):
            self.send_error(400)
            return
        key = self.headers.get("Sec-WebSocket-Key")
        try:
            decoded_key = base64.b64decode(key or "", validate=True)
        except (ValueError, TypeError):
            decoded_key = b""
        if len(decoded_key) != 16:
            self.send_error(400)
            return
        with owner._lock:
            try:
                session, digest, presented = self._authenticated_v2_locked(renew=True)
            except (UnicodeEncodeError, ValueError):
                self.send_error(400)
                return
            if session is None:
                self._v2_unauthorized(presented)
                return
            if not secrets.compare_digest(protocols[1][len("ujagd-csrf."):],
                                          session["csrf"]):
                self.send_error(403)
                return
            station = session["active_station"]
            lease = session["leases"].get(station)
            if (not owner._voice_enabled or station not in STATIONS or lease is None):
                self.send_error(403)
                return
            if digest in owner._voice_peers:
                self._reply(409, {"error": "stream_exists"})
                return
            peer = VoicePeer(digest, session, station, lease["generation"],
                             session["active_generation"])
            owner._voice_peers[digest] = peer
            peer.enqueue(1, _json_bytes({
                "type": "ready", "station": station,
                "talker": (None if owner._voice_talker is None
                           else owner._voice_talker.station)}))
        accept = base64.b64encode(hashlib.sha1(
            key.encode("ascii") + _WEBSOCKET_GUID).digest()).decode("ascii")
        self.send_response_only(101)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.send_header("Sec-WebSocket-Protocol", "u-jagd-voice-v2")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not self.server.mark_upgraded():
            with owner._lock:
                owner._voice_disconnect_locked(peer)
            return
        self.connection.settimeout(0.2)
        try:
            while True:
                with owner._lock:
                    owner._expire_locked()
                    if not owner._voice_valid_locked(peer):
                        break
                    pending = list(peer.outgoing)
                    peer.outgoing.clear()
                for opcode, payload in pending:
                    self.connection.sendall(_websocket_frame(payload, opcode=opcode))
                readable, _, _ = select.select([self.connection], [], [], 0.025)
                if not readable:
                    continue
                chunk = self.connection.recv(4096)
                if not chunk:
                    break
                peer.incoming.extend(chunk)
                for opcode, payload in read_frames(peer.incoming):
                    if opcode == 8:
                        return
                    if opcode == 9:
                        self.connection.sendall(_websocket_frame(payload, opcode=10))
                        continue
                    with owner._lock:
                        if not owner._voice_valid_locked(peer):
                            return
                        if opcode == 1 and payload == b"down":
                            if owner._voice_talker is None:
                                owner._voice_talker = peer
                                owner._voice_status_locked()
                        elif opcode == 1 and payload == b"up":
                            if owner._voice_talker is peer:
                                owner._voice_talker = None
                                owner._voice_status_locked()
                        elif opcode == 2 and len(payload) == VOICE_PCM_BYTES:
                            if owner._voice_talker is peer:
                                frame = bytes((STATIONS.index(peer.station),)) + payload
                                for other in owner._voice_peers.values():
                                    if other is not peer:
                                        other.enqueue(2, frame)
                        else:
                            return
                # A TCP read can contain several valid frames. Bound only the
                # unparsed remainder, never the complete batch before parsing.
                if len(peer.incoming) > 4096:
                    break
        except (OSError, ValueError, TimeoutError):
            pass
        finally:
            with owner._lock:
                owner._voice_disconnect_locked(peer)
            try:
                self.connection.sendall(_websocket_frame(struct.pack("!H", 1008), opcode=8))
            except OSError:
                pass
            self.close_connection = True

    def _get(self):
        owner = self.server.owner
        if owner.web_auth is not None and self.path == "/api/v2/web/status":
            self._reply(200, {"configured": owner.web_auth.configured})
        elif owner.web_auth is not None and self.path == "/api/v2/web/room":
            with owner._lock:
                session, _, presented = self._authenticated_v2_locked(renew=True)
                if session is None or not session.get("web_host"):
                    self._v2_unauthorized(presented)
                    return
                session["presence"] = time.monotonic()
                body = {
                    "csrf": session["csrf"], "code": owner._code,
                    "clients": [row for row in owner.client_statuses()
                                if row["client_id"] != session["client_id"]],
                    "results": dict(owner._web_admin_results),
                    "proposals": dict(owner._web_proposals),
                }
            self._reply(200, body)
        elif owner.web_auth is not None and self.path == "/api/v2/web/options":
            with owner._lock:
                session, digest, presented = self._authenticated_v2_locked(renew=True)
                if session is None or digest != owner._web_host_digest:
                    self._v2_unauthorized(presented)
                    return
                body = owner._web_options_state
            self._reply(200, body)
        elif owner.web_auth is not None and self.path == "/api/v2/voice/status":
            with owner._lock:
                session, _, presented = self._authenticated_v2_locked(renew=True)
                if session is None:
                    self._v2_unauthorized(presented)
                    return
                station = session["active_station"]
                body = {"enabled": owner._voice_enabled,
                        "station": station if station in session["leases"] else None,
                        "csrf": session["csrf"],
                        "talker": (None if owner._voice_talker is None
                                   else owner._voice_talker.station)}
            self._reply(200, body)
        elif self.path == SONAR_STREAM_ROUTE:
            self._sonar_websocket()
        elif self.path.partition("?")[0] in SONAR_AUDIO_STREAM_ROUTES:
            route, _, query = self.path.partition("?")
            after = _audio_resume_cursor(query)
            if after is False:
                self.send_error(400)
            else:
                self._audio_websocket(SONAR_AUDIO_STREAM_ROUTES[route], after=after)
        elif self.path == VOICE_STREAM_ROUTE:
            self._voice_websocket()
        elif self.path in SONAR_SCOPE_ROUTES:
            content_type, body = self.server.assets["/"]
            self._reply(200, body, content_type)
        elif self.path in self.server.assets:
            content_type, body = self.server.assets[self.path]
            self._reply(200, body, content_type)
        elif self.path in ("/api/v2/ui?lang=en", "/api/v2/ui?lang=de"):
            self._reply(200, owner._translations[self.path[-2:]])
        elif self.path in ("/api/v2/session", "/api/v2/state",
                           "/api/v2/state?sonar=stream", "/api/v2/chart",
                           "/api/v2/results", "/api/v2/proposals",
                           "/api/v2/events", "/api/v2/simlog", "/api/v2/host"):
            try:
                with owner._lock:
                    session, digest, presented = self._authenticated_v2_locked(renew=True)
                    if session is not None and self.path == "/api/v2/session":
                        session["presence"] = time.monotonic()
                    role = session["active_station"] if session is not None else None
                    body = None
                    if session is not None and self.path == "/api/v2/session":
                        body = self._session_v2_body(session, owner._sessions_v2)
                    elif session is not None and self.path == "/api/v2/results":
                        body = _json_bytes({"protocol": 2, "results": [
                            dict(result) for result in session["command_results"]]})
                    elif session is not None and self.path == "/api/v2/host":
                        body = owner._v2_host if session["solo_host"] else None
                    elif session is not None and self.path in (
                            "/api/v2/state", "/api/v2/state?sonar=stream"):
                        body = (owner._v2_sonar_compact_state
                                if self.path.endswith("?sonar=stream")
                                and role == "sonar" else owner._v2_states[role])
                    elif session is not None and self.path == "/api/v2/chart":
                        body = owner._v2_charts[role]
                    elif session is not None and self.path == "/api/v2/proposals":
                        body = (owner._v2_proposals.get((digest, role))
                                if role is not None else None)
                        if body is None and role is not None:
                            state = json.loads(owner._v2_states[role].decode("ascii"))
                            body = _json_bytes({"protocol": 2,
                                "session": state["session"], "epoch": state["epoch"],
                                "role": role, "target": None, "navigation": None})
                    elif session is not None and self.path == "/api/v2/events":
                        cached = (owner._v2_private_events.get(digest)
                                  if role is not None else None)
                        if cached is not None and json.loads(
                                cached.decode("ascii")).get("role") == role:
                            body = cached
                        elif role is not None:
                            body = owner._v2_events.get(role)
                        if body is None and role is not None:
                            state = json.loads(owner._v2_states[role].decode("ascii"))
                            body = _json_bytes({"protocol": 2,
                                "session": state["session"], "epoch": state["epoch"],
                                "role": role, "latest_seq": 0, "events": []})
                    elif session is not None and self.path == "/api/v2/simlog":
                        body = (owner._v2_simlogs.get(role) if role is not None
                                and session["simlog"] else None)
                        if body is None and role is not None and session["simlog"]:
                            state = json.loads(owner._v2_states[role].decode("ascii"))
                            body = _json_bytes({"protocol": 2,
                                "session": state["session"], "epoch": state["epoch"],
                                "role": role, "entries": []})
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
            if owner.web_auth is not None and self.path == "/api/v2/web/setup":
                if (type(body) is not dict or set(body) != {"code", "password"}
                        or type(body["code"]) is not str
                        or type(body["password"]) is not str):
                    status, response = 400, {"error": "invalid_request"}
                elif owner.web_auth.configured:
                    status, response = 409, {"error": "already_configured"}
                elif owner.web_auth.setup(body["code"], body["password"]):
                    status, response = 200, {"status": "configured"}
                else:
                    status, response = 403, {"error": "setup_failed"}
            elif owner.web_auth is not None and self.path == "/api/v2/web/login":
                if (type(body) is not dict or set(body) != {"password"}
                        or type(body["password"]) is not str):
                    status, response = 400, {"error": "invalid_request"}
                elif not owner.web_auth.verify(body["password"]):
                    status, response = 403, {"error": "invalid_credentials"}
                else:
                    old = owner._sessions_v2.pop(owner._web_host_digest, None)
                    if old is not None:
                        owner._clear_session_authority_locked(old)
                    owner._web_admin_queue.clear()
                    owner._web_admin_inflight.clear()
                    owner._web_admin_seen.clear()
                    owner._web_admin_results.clear()
                    token, session = owner._new_session_locked("Host", web_host=True)
                    self._reply(200, self._session_v2_body(session, owner._sessions_v2),
                                set_cookie=self._v2_cookie(token))
                    return
            elif owner.web_auth is not None and self.path == "/api/v2/web/admin":
                try:
                    session, digest, presented = self._authenticated_v2_locked(renew=True)
                except (UnicodeEncodeError, ValueError):
                    status, response = 400, {"error": "invalid_request"}
                else:
                    if session is None or digest != owner._web_host_digest:
                        self._v2_unauthorized(presented)
                        return
                    csrf = self.headers.get("X-U-Jagd-CSRF")
                    if (csrf is None or not secrets.compare_digest(
                            csrf.encode("utf-8", errors="surrogatepass"),
                            session["csrf"].encode("ascii"))):
                        status, response = 403, {"error": "forbidden"}
                    elif (type(body) is not dict or set(body) != {"action", "client_id", "station", "value"}
                          or type(body["action"]) is not str
                          or body["action"] not in {
                              "assign", "revoke", "revoke_client", "command", "direct_fire",
                              "sonar_audio", "simlog", "rotate_code", "accept_target",
                              "reject_target", "accept_navigation", "reject_navigation"}
                          or type(body["client_id"]) is not str
                          or len(body["client_id"]) > 64
                          or type(body["station"]) is not str
                          or body["station"] not in (*ROLES, "")
                          or type(body["value"]) is not bool):
                        status, response = 400, {"error": "invalid_request"}
                    elif ((body["action"] in {"assign", "revoke", "command",
                                                 "direct_fire", "sonar_audio"}
                           and (not body["client_id"] or body["station"] not in ROLES))
                          or (body["action"] in {"revoke_client", "simlog"}
                              and (not body["client_id"] or body["station"] != ""))
                          or (body["action"] in {"rotate_code", "accept_target",
                                                 "reject_target", "accept_navigation",
                                                 "reject_navigation"}
                              and (body["client_id"] or body["station"] or body["value"]))
                          or (body["action"] in {"assign", "revoke", "revoke_client"}
                              and body["value"])):
                        status, response = 400, {"error": "invalid_request"}
                    else:
                        status, response = owner._enqueue_web_admin_locked(
                            digest, dict(body), self.headers.get("X-U-Jagd-Request-ID"))
            elif owner.web_auth is not None and self.path == "/api/v2/web/options":
                try:
                    session, digest, presented = self._authenticated_v2_locked(renew=True)
                except (UnicodeEncodeError, ValueError):
                    status, response = 400, {"error": "invalid_request"}
                else:
                    if session is None or digest != owner._web_host_digest:
                        self._v2_unauthorized(presented)
                        return
                    csrf = self.headers.get("X-U-Jagd-CSRF")
                    bool_names = {"simlog", "live_ais_enabled", "live_adsb_enabled",
                                  "voice_enabled"}
                    string_names = {"aisstream_api_key", "opensky_credentials"}
                    if (csrf is None or not secrets.compare_digest(
                            csrf.encode("utf-8", errors="surrogatepass"),
                            session["csrf"].encode("ascii"))):
                        status, response = 403, {"error": "forbidden"}
                    elif (type(body) is not dict or set(body) != {"name", "value"}
                          or type(body["name"]) is not str
                          or (body["name"] not in bool_names | string_names | {"language"})
                          or (body["name"] in bool_names and type(body["value"]) is not bool)
                          or (body["name"] in string_names and (
                              type(body["value"]) is not str or len(body["value"]) > 256))
                          or (body["name"] == "language" and body["value"] not in ("en", "de"))):
                        status, response = 400, {"error": "invalid_request"}
                    else:
                        status, response = owner._enqueue_web_admin_locked(
                            digest, {"action": "option", "name": body["name"],
                                     "value": body["value"]},
                            self.headers.get("X-U-Jagd-Request-ID"))
            elif self.path == "/api/v2/pair":
                if not owner._running:
                    status, response = 503, {"error": "unavailable"}
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
                    elif len(owner._sessions_v2) >= (1 if owner._solo
                                                     else _V2_SESSION_LIMIT):
                        status, response = 429, {"error": "session_limit"}
                    elif not secrets.compare_digest(
                            body["code"].encode("utf-8", errors="surrogatepass"),
                            owner._code.encode("ascii")):
                        owner._pair_failures.append(time.monotonic())
                        if len(owner._pair_failures) == 5:
                            owner._rotate_code_locked()
                        status, response = 403, {"error": "invalid_code"}
                    else:
                        token, session = owner._new_session_locked(name)
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
                                or body["station"] not in ROLES):
                            status, response = 400, {"error": "invalid_request"}
                        else:
                            station = body["station"]
                            if session["solo_host"] and owner._solo and owner._side_conflict(
                                    session, station):
                                # Solo: choosing a station of the other unit moves
                                # the whole session to that unit.
                                owner._solo_switch_side_locked(session, station)
                            elif (not owner._auto_grant_locked(session, station)
                                    and station not in session["leases"]
                                    and station not in session["requests"]
                                    and not owner._side_conflict(session, station)):
                                # Held by a crewmate: the host decides (takeover).
                                session["next_request_generation"] += 1
                                session["requests"][station] = session["next_request_generation"]
                            status = 200
                            response = self._session_v2_body(session, owner._sessions_v2)
                    elif (type(body) is not dict
                          or set(body) != {"station", "station_generation",
                                           "active_generation"}
                          or body["station"] not in ROLES
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
                        elif (not session["solo_host"] if body["station"] == HOST_ROLE
                              else (body["station"] != session["active_station"]
                                    or body["station"] not in session["leases"]
                                    or not session["leases"][body["station"]]["grants"]["command"])):
                            status, response = 403, {"error": "forbidden"}
                        elif (body["station_generation"]
                              != (session["host_generation"] if body["station"] == HOST_ROLE
                                  else session["leases"][body["station"]]["generation"])):
                            status, response = 409, {"error": "stale_generation"}
                        elif (body["station"] != HOST_ROLE
                              and body["active_generation"] != session["active_generation"]):
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
            elif self.path in _AUDIO_POLL_ROUTES:
                audio_role = _AUDIO_POLL_ROUTES[self.path]
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
                    elif (session["active_station"] != audio_role
                          or audio_role not in session["leases"]
                          or not session["leases"][audio_role]["grants"]["sonar_audio"]):
                        status, response = 403, {"error": "forbidden"}
                    elif (body["station_generation"]
                          != session["leases"][audio_role]["generation"]):
                        status, response = 409, {"error": "stale_context"}
                    elif body["active_generation"] != session["active_generation"]:
                        status, response = 409, {"error": "stale_context"}
                    else:
                        context = (digest, session["leases"][audio_role]["generation"],
                                   session["active_generation"],
                                   body["world_session"], body["world_epoch"])
                        audio_blocks, audio_context = owner._audio_ring(audio_role)
                        if audio_context != context:
                            status, response = 503, {"error": "unavailable"}
                        else:
                            after = body["after"]
                            available = [block for block in audio_blocks
                                         if after is None or block[0] > after]
                            if (not available and after is not None and audio_blocks
                                    and after > audio_blocks[-1][0]):
                                # The publisher restarted its sequence within
                                # the same world context. Rebase the listener
                                # instead of returning 204 forever.
                                sequence, pcm = audio_blocks[-1]
                                audio_reply = (200, pcm, sequence, True)
                            elif not available:
                                audio_reply = (204, b"", None, False)
                            else:
                                overrun = (after is not None and audio_blocks
                                           and after < audio_blocks[0][0] - 1)
                                sequence, pcm = available[-1] if after is None or overrun else available[0]
                                audio_reply = (200, pcm, sequence, bool(overrun))
        if audio_reply is not None:
            # A slow audio socket must never hold the lock needed by the main
            # thread, heartbeats, station grants, or command acceptance.
            code, pcm, sequence, discontinuity = audio_reply
            self._sonar_audio_reply(code, pcm, sequence=sequence, discontinuity=discontinuity)
        else:
            self._reply(status, response)
