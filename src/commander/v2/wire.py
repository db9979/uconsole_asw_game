"""Wire-level constants and helpers of Remote Crew v2: role tables, session and
lease limits, JSON/audio payload encoders and WebSocket framing (verbatim
from ``server.py``)."""


import json
import logging
import math
import struct
import re



# The public logger name predates the split (tests and operators filter on it).
_log = logging.getLogger("src.commander.server")
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


def station_grants(station=None):
    """A granted station always carries every right it can have; the host
    only ever takes rights away (``set_client_grant``) or the station."""
    return {
        "command": station in ROLES,
        "direct_fire": station in DIRECT_FIRE_ROLES,
        "sonar_audio": station in SONAR_AUDIO_ROLES,
    }
