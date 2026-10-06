"""HTTP and WebSocket routes of Remote Crew v2: the bounded listener and the
request handler for pairing, state, commands, audio, voice and assets
(verbatim from ``server.py``)."""


from http.server import BaseHTTPRequestHandler, HTTPServer
import base64
import hashlib
import io
import ipaddress
import json
import secrets
import socket
import struct
import threading
import time
import select
import unicodedata
from urllib.parse import urlsplit

from src.core.version import APP_VERSION
from src.commander.voice import PCM_BYTES as VOICE_PCM_BYTES, VoicePeer, read_frames
from src.commander.v2.commands import (
    V2CommandEnvelope,
    _number,
    _object,
    _v2_command_valid)
from src.commander.missions import MISSION_UPLOAD_MAX_BYTES
from src.commander.advisor_web import VOICE_ROUTE as ADVISOR_VOICE_ROUTE
from src.commander.advisor_web import SPEECH_MAX_BYTES, SPEECH_ROUTE
from src.commander.v2.wire import (
    station_grants,
    AUDIO_SOCKET_TIMEOUT_S,
    HOST_ROLE,
    ROLES,
    LOOKOUT_ROLES,
    MIC_ROUTE,
    OPFOR_ROLES,
    VOICE_ROLES,
    SONAR_AUDIO_FRAMES,
    SONAR_AUDIO_RATE,
    SONAR_AUDIO_RESUME_BLOCKS,
    SONAR_AUDIO_STREAM_ROUTES,
    SONAR_ROLES,
    SONAR_SCOPE_ROUTES,
    SONAR_STREAM_ROUTE,
    STATE_PUSH_HEARTBEAT,
    STATE_PUSH_HEARTBEAT_S,
    STATE_PUSH_MAX_HZ,
    STATE_PUSH_PROTOCOL,
    STATE_PUSH_ROUTE,
    VOICE_STREAM_ROUTE,
    _AUDIO_POLL_ROUTES,
    _CONNECTION_DEADLINE_S,
    _COOKIE_NAME,
    _COOKIE_VALUE,
    _SAFE_INTEGER_MAX,
    _V2_COMMAND_CLIENT_LIMIT,
    _V2_COMMAND_GLOBAL_LIMIT,
    _V2_COMMAND_MAX_AGE_S,
    _V2_COOKIE,
    _V2_SONAR_AUDIO_FIELDS,
    _WEBSOCKET_GUID,
    _audio_resume_cursor,
    _json_bytes,
    _websocket_frame)


_OVERLOAD_RESPONSE = (
    b"HTTP/1.1 503 Service Unavailable\r\n"
    b"Connection: close\r\n"
    b"Content-Length: 0\r\n"
    b"\r\n"
)
# Up to 9 stations poll at 2 Hz plus a sonar audio stream; headroom above that.
# Nine voice sockets, a sonar stream and short HTTP polls need separate slots.
_CONNECTION_SLOT_LIMIT = 28
_COLOR_SCHEME_META = b'<meta name="color-scheme" content="dark">'


def _with_host_language(page: bytes, language: str) -> bytes:
    """Name the host's saved language in a page (after its color-scheme
    meta); the page opens in it and the browser can switch for itself."""
    if language not in ("en", "de"):
        return page
    return page.replace(_COLOR_SCHEME_META, _COLOR_SCHEME_META
                        + b'\n  <meta name="u-jagd-host-language" content="'
                        + language.encode("ascii") + b'">', 1)


class _HTTPServer(HTTPServer):
    # On Windows SO_REUSEADDR lets a second program bind the same port and
    # take over the listener; there the port is held exclusively instead.
    allow_reuse_address = not hasattr(socket, "SO_EXCLUSIVEADDRUSE")
    request_queue_size = _CONNECTION_SLOT_LIMIT

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def __init__(self, address, owner, assets, tls=None):
        self.owner = owner
        self.assets = assets
        # The phone lookouts' HTTPS listener (src/commander/tls.py): the same
        # routes behind a per-connection TLS handshake in the worker thread.
        self.tls = tls
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
            origins.add(f"{'https' if self.tls is not None else 'http'}://{host}")
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
            if self.tls is not None:
                # The handshake runs here, bounded by the same deadline; the
                # wrapped socket keeps the descriptor the timer shuts down.
                request = self.tls.wrap_socket(request, server_side=True,
                                               do_handshake_on_connect=False)
                with self.work_lock:
                    self.workers[threading.current_thread()] = request
                request.do_handshake()
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
            # The browser reloads itself when the host was updated under it.
            ("X-U-Jagd-Version", APP_VERSION),
            ("X-Content-Type-Options", "nosniff"), ("X-Frame-Options", "DENY"),
            # Not "no-referrer": with it the Fetch standard makes Safari and
            # Firefox send "Origin: null" on the pages' same-origin POSTs,
            # which the exact Origin check refuses (pairing then fails).
            # "same-origin" still sends no referrer to any other site.
            ("Referrer-Policy", "same-origin"),
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

    def _voice_reply(self, pcm: bytes, rate: int):
        self.send_response_only(200)
        self.send_header("Content-Type", "audio/pcm")
        self.send_header("X-U-Jagd-PCM", "s16le")
        self.send_header("X-U-Jagd-Sample-Rate", str(int(rate)))
        self.send_header("Content-Length", str(len(pcm)))
        self.send_header("Connection", "close")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-U-Jagd-Version", APP_VERSION)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(pcm)
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
        # Only a mission upload (solo host, checked in _post) may be larger.
        if length > (MISSION_UPLOAD_MAX_BYTES if self.command == "POST"
                     and self.path == "/api/v2/missions" else
                     # A spoken question to the executive officer.
                     SPEECH_MAX_BYTES if self.command == "POST"
                     and self.path == SPEECH_ROUTE else 4096):
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
    def _session_v2_body(session, sessions, owner=None):
        occupied = {station: candidate for candidate in sessions.values()
                    for station in candidate["leases"]}
        active = session["active_station"]
        active_lease = session["leases"].get(active)
        requested = next((station for station in ROLES
                          if station in session["requests"]), None)
        active_grants = (station_grants() if active_lease is None
                         else dict(active_lease["grants"]))
        observer = session["observer"]

        def status(station):
            if observer and station == active:
                return "mine"                     # the observer's read-only view
            return ("available" if station not in occupied else
                    "mine" if occupied[station] is session else "occupied")
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
            "observer": observer,
            "grants": dict(active_grants, simlog=session["simlog"]),
            "presence": session["presence"],
            # Host command surface: only a solo session carries one.
            # Server mode: the leading crew browser carries it beside its stations.
            "host": ({"generation": session["host_generation"],
                      "leader": bool(session.get("leader"))}
                     if session["solo_host"] or session.get("leader") else None),
            # The host's open multiplayer lobby (players, mission, countdown).
            "lobby": owner.lobby_body_locked(session) if owner is not None else None,
            # Crewmates asking for a station this session holds: the holder
            # hands it over or keeps it (``/api/v2/stations/handover``).
            "handover": (owner.handover_requests_locked(session)
                         if owner is not None else []),
            "stations": {
                station: {
                    "status": status(station),
                    "requested": station in session["requests"],
                    "request_generation": session["requests"].get(station, 0),
                    "station_generation": (session["leases"][station]["generation"]
                                           if station in session["leases"] else
                                           0 if observer and station == active else None),
                    "grants": (dict(session["leases"][station]["grants"])
                               if station in session["leases"] else
                               station_grants()),
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
        """This request came through HTTPS (the proxy or the phone listener),
        not the direct plain-HTTP LAN URL."""
        owner = self.server.owner
        if self.server.tls is not None:
            return True
        return owner.public_origin is not None and (
            owner.web_auth is not None
            or self.headers.get("Origin") == owner.public_origin
            or self.headers.get("Host") in self.server.public_hosts)

    def _source_address(self):
        """The address failed logins and pairings are counted against.

        The socket peer, unless ``--public-origin`` names a reverse proxy: then
        the rightmost ``X-Forwarded-For`` entry, the one that proxy appended
        (entries further left are client-supplied). A missing or malformed
        header falls back to the peer, never to a shared bucket.
        """
        peer = str(self.client_address[0]) if self.client_address else ""
        if self.server.owner.public_origin is None:
            return peer
        forwarded = self.headers.get("X-Forwarded-For")
        if type(forwarded) is not str or len(forwarded) > 1024:
            return peer
        candidate = forwarded.rsplit(",", 1)[-1].strip()
        try:
            return "fwd:" + str(ipaddress.ip_address(candidate))
        except ValueError:
            return peer

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
            # One stream per client: a reconnect supersedes the client's older
            # socket, whose worker may still idle on a peer that is gone.
            if owner._sonar_stream_clients.pop(digest, None) is not None:
                owner._sonar_stream_condition.notify_all()
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
            with owner._lock:
                if owner._sonar_stream_clients.get(digest) is client_token:
                    del owner._sonar_stream_clients[digest]
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

    def _state_websocket(self):
        """Push the active role's projection to one client as it changes.

        Same bytes as ``GET /api/v2/state`` (the compact sonar view while the
        client streams sonar), at most ``STATE_PUSH_MAX_HZ``, a heartbeat every
        ``STATE_PUSH_HEARTBEAT_S`` while nothing changes; only the latest state
        is ever queued (a slow client skips intermediate states).  Closes on
        role loss, world replacement or the host's push switch.
        """
        owner = self.server.owner
        allowed_origins = self.server.allowed_origins(self.headers.get("Host"))
        if (self.headers.get("Origin") not in allowed_origins
                or self.headers.get("Upgrade", "").lower() != "websocket"
                or "upgrade" not in {item.strip().lower() for item in
                                      self.headers.get("Connection", "").split(",")}
                or self.headers.get("Sec-WebSocket-Version") != "13"
                or self.headers.get("Sec-WebSocket-Protocol") != STATE_PUSH_PROTOCOL):
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
            role = session["active_station"]
            lease = session["leases"].get(role)
            observer = session["observer"]
            if (not owner._state_push_enabled or role not in ROLES
                    or (lease is None and not observer)):
                self.send_error(403)
                return
            if digest in owner._state_push_clients:
                self._reply(409, {"error": "push_exists"})
                return
            station_generation = 0 if observer else lease["generation"]
            active_generation = session["active_generation"]
            owner._state_push_clients[digest] = client_token
        accept = base64.b64encode(hashlib.sha1(
            key.encode("ascii") + _WEBSOCKET_GUID).digest()).decode("ascii")
        self.send_response_only(101)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.send_header("Sec-WebSocket-Protocol", STATE_PUSH_PROTOCOL)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not self.server.mark_upgraded():
            return
        last_sequence = -1
        last_sent = 0.0
        min_interval = 1.0 / STATE_PUSH_MAX_HZ
        try:
            while True:
                with owner._sonar_stream_condition:
                    owner._expire_locked()
                    current = owner._sessions_v2.get(digest)
                    lease = None if current is None else current["leases"].get(role)
                    valid = (owner._running and owner._state_push_enabled
                             and current is session
                             and owner._state_push_clients.get(digest) is client_token
                             and current["active_station"] == role
                             and (current["observer"] if observer else
                                  lease is not None
                                  and lease["generation"] == station_generation)
                             and current["active_generation"] == active_generation)
                    if not valid:
                        break
                    now = time.monotonic()
                    if owner._state_push_sequence == last_sequence:
                        if now - last_sent >= STATE_PUSH_HEARTBEAT_S:
                            payload = STATE_PUSH_HEARTBEAT
                        else:
                            owner._sonar_stream_condition.wait(
                                timeout=max(0.05, STATE_PUSH_HEARTBEAT_S - (now - last_sent)))
                            continue
                    elif now - last_sent < min_interval:
                        owner._sonar_stream_condition.wait(timeout=min_interval - (now - last_sent))
                        continue
                    else:
                        last_sequence = owner._state_push_sequence
                        payload = (owner._v2_sonar_compact_state
                                   if role == "sonar" and digest in owner._sonar_stream_clients
                                   else owner._v2_states[role])
                    current["last_get"] = now
                    last_sent = now
                self.connection.sendall(_websocket_frame(payload, opcode=1))
        except (OSError, TimeoutError, ValueError):
            pass
        finally:
            with owner._lock:
                if owner._state_push_clients.get(digest) is client_token:
                    del owner._state_push_clients[digest]
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
            # One stream per client and role: a reconnect supersedes the
            # client's older socket, whose worker may still idle on a peer that
            # is gone (it notices only at its next send or lease check).
            if owner._audio_clients.pop(client_key, None) is not None:
                owner._audio_condition.notify_all()
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
                if owner._audio_clients.get(client_key) is marker:
                    del owner._audio_clients[client_key]
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
            if (not owner._voice_enabled or station not in VOICE_ROLES or lease is None):
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
                "talker": owner.voice_talker_for_locked(station)}))
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
                # A TLS socket may hold decrypted bytes select() cannot see.
                buffered = getattr(self.connection, "pending", lambda: 0)()
                readable = buffered or select.select([self.connection], [], [], 0.025)[0]
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
                            owner.voice_press_locked(peer)
                        elif opcode == 1 and payload == b"up":
                            owner.voice_release_locked(peer)
                        elif opcode == 2 and len(payload) == VOICE_PCM_BYTES:
                            owner.voice_relay_locked(peer, payload)
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
                        "talker": (owner.voice_talker_for_locked(station)
                                   if station in VOICE_ROLES else None)}
            self._reply(200, body)
        elif self.path == SONAR_STREAM_ROUTE:
            self._sonar_websocket()
        elif self.path == STATE_PUSH_ROUTE:
            self._state_websocket()
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
            self._reply(200, _with_host_language(body, owner._host_language), content_type)
        elif self.path in self.server.assets:
            content_type, body = self.server.assets[self.path]
            if content_type.startswith("text/html"):
                body = _with_host_language(body, owner._host_language)
            self._reply(200, body, content_type)
        elif self.path in ("/api/v2/ui?lang=en", "/api/v2/ui?lang=de"):
            self._reply(200, owner._translations[self.path[-2:]])
        elif self.path == "/api/v2/secure":
            # Noise discipline: browsers hand out the microphone only in a
            # secure context, so a crew page on plain HTTP learns the port
            # of the HTTPS listener (None without one) to switch over.
            secure = owner.tls_address
            self._reply(200, {"protocol": 2,
                              "port": None if secure is None else int(secure[1])})
        elif self.path.startswith(ADVISOR_VOICE_ROUTE):
            # The executive officer's spoken answer, for its asker only.
            try:
                with owner._lock:
                    session, _, presented = self._authenticated_v2_locked(renew=True)
                    clip = (owner.advisor_voice_locked(session, self.path)
                            if session is not None else None)
            except (UnicodeEncodeError, ValueError):
                self.send_error(400)
                return
            if session is None:
                self._v2_unauthorized(presented)
            elif clip is None:
                self.send_error(404)
            else:
                self._voice_reply(*clip)
        elif self.path in ("/api/v2/session", "/api/v2/state",
                           "/api/v2/state?sonar=stream", "/api/v2/chart",
                           "/api/v2/results", "/api/v2/proposals",
                           "/api/v2/events", "/api/v2/simlog", "/api/v2/host",
                           "/api/v2/debrief", "/api/v2/advisor"):
            try:
                with owner._lock:
                    session, digest, presented = self._authenticated_v2_locked(renew=True)
                    if session is not None and self.path == "/api/v2/session":
                        session["presence"] = time.monotonic()
                    role = session["active_station"] if session is not None else None
                    body = None
                    if session is not None and self.path == "/api/v2/session":
                        body = self._session_v2_body(session, owner._sessions_v2, owner)
                    elif session is not None and self.path == "/api/v2/results":
                        body = _json_bytes({"protocol": 2, "results": [
                            dict(result) for result in session["command_results"]]})
                    elif session is not None and self.path == "/api/v2/host":
                        body = owner._v2_host if owner._host_surface(session) else None
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
                            # The small head stored at publish time; the full
                            # role state (up to 512 KiB) is never re-parsed.
                            world, epoch = owner._v2_state_heads[role]
                            body = _json_bytes({"protocol": 2,
                                "session": world, "epoch": epoch,
                                "role": role, "target": None, "navigation": None})
                    elif session is not None and self.path == "/api/v2/events":
                        cached = (owner._v2_private_events.get(digest)
                                  if role is not None else None)
                        if cached is not None and cached[0] == role:
                            body = cached[1]
                        elif role is not None:
                            body = owner._v2_events.get(role)
                        if body is None and role is not None:
                            world, epoch = owner._v2_state_heads[role]
                            body = _json_bytes({"protocol": 2,
                                "session": world, "epoch": epoch,
                                "role": role, "latest_seq": 0, "events": []})
                    elif session is not None and self.path == "/api/v2/debrief":
                        # Only after the mission ends, and only the own side's.
                        side = "uboot" if role in (*OPFOR_ROLES, "uboot_lookout") else "frigate"
                        body = (owner._v2_debriefs.get(side) if role is not None else None
                                ) or _json_bytes({"protocol": 2, "available": False})
                    elif session is not None and self.path == "/api/v2/advisor":
                        # The asker's own log (src/commander/advisor_web.py).
                        body = owner.advisor_body_locked(session)
                    elif session is not None and self.path == "/api/v2/simlog":
                        body = (owner._v2_simlogs.get(role) if role is not None
                                and session["simlog"] else None)
                        if body is None and role is not None and session["simlog"]:
                            world, epoch = owner._v2_state_heads[role]
                            body = _json_bytes({"protocol": 2,
                                "session": world, "epoch": epoch,
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
        elif (self.path in ("/api/v2/missions", "/api/v2/editor/catalog")
              or self.path.startswith("/api/v2/editor/sector?i=")):
            # The own-mission library: the solo host surface only.
            try:
                with owner._lock:
                    session, _, presented = self._authenticated_v2_locked(renew=True)
                    body = (owner.mission_route_body_locked(session, self.path)
                            if session is not None else None)
            except (UnicodeEncodeError, ValueError):
                self.send_error(400)
                return
            if session is None:
                self._v2_unauthorized(presented)
            elif body is None:
                self.send_error(403 if not owner._host_surface(session) else 404)
            else:
                self._reply(200, body)
        else:
            self.send_error(404)

    def _post(self, body, received_at):
        owner = self.server.owner
        status, response = 404, {"error": "not_found"}
        audio_reply = None
        # The web host's password check (scrypt, 16 MiB and noticeable CPU)
        # runs before the global lock: a stranger's login attempt must never
        # stall the main thread or any stream. WebHostAuth has its own lock
        # and counts failures per source address.
        if owner.web_auth is not None and self.path == "/api/v2/web/setup":
            if (type(body) is not dict or set(body) != {"code", "password"}
                    or type(body["code"]) is not str
                    or type(body["password"]) is not str):
                status, response = 400, {"error": "invalid_request"}
            elif owner.web_auth.configured:
                status, response = 409, {"error": "already_configured"}
            elif owner.web_auth.setup(body["code"], body["password"],
                                      self._source_address()):
                status, response = 200, {"status": "configured"}
            else:
                status, response = 403, {"error": "setup_failed"}
            self._reply(status, response)
            return
        if owner.web_auth is not None and self.path == "/api/v2/web/login":
            if (type(body) is not dict or set(body) != {"password"}
                    or type(body["password"]) is not str):
                self._reply(400, {"error": "invalid_request"})
                return
            if not owner.web_auth.verify(body["password"], self._source_address()):
                self._reply(403, {"error": "invalid_credentials"})
                return
            with owner._lock:
                owner._expire_locked()
                old = owner._sessions_v2.pop(owner._web_host_digest, None)
                if old is not None:
                    owner._clear_session_authority_locked(old)
                owner._web_admin_queue.clear()
                owner._web_admin_inflight.clear()
                owner._web_admin_seen.clear()
                owner._web_admin_results.clear()
                token, session = owner._new_session_locked("Host", web_host=True)
                reply = self._session_v2_body(session, owner._sessions_v2, owner)
            self._reply(200, reply, set_cookie=self._v2_cookie(token))
            return
        with owner._lock:
            owner._expire_locked()
            if owner.web_auth is not None and self.path == "/api/v2/web/admin":
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
                              "sonar_audio", "simlog", "observer", "rotate_code", "accept_target",
                              "reject_target", "accept_navigation", "reject_navigation",
                              "shutdown"}
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
                              and body["value"])
                          or (body["action"] == "shutdown"
                              and (body["client_id"] or body["station"]
                                   or body["value"] is not True))):
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
                elif not owner._pair_failures.allowed(self._source_address()):
                    status, response = 429, {"error": "pairing_rate_limited"}
                elif (not isinstance(body, dict)
                      or body.keys() not in ({"code", "name"}, {"code", "name", "role"})
                      or not isinstance(body["code"], str)
                      or not isinstance(body["name"], str)
                      or body.get("role", LOOKOUT_ROLES[0]) not in LOOKOUT_ROLES):
                    status, response = 400, {"error": "invalid_request"}
                else:
                    name = body["name"].strip()
                    if (not 1 <= len(name) <= 32
                            or any(unicodedata.category(char).startswith("C") for char in name)):
                        status, response = 400, {"error": "invalid_request"}
                    elif not owner._pair_admitted_locked(body.get("role")):
                        status, response = 429, {"error": "session_limit"}
                    elif not secrets.compare_digest(
                            body["code"].encode("utf-8", errors="surrogatepass"),
                            owner._code.encode("ascii")):
                        owner._record_pair_failure_locked(self._source_address())
                        status, response = 403, {"error": "invalid_code"}
                    else:
                        token, session = owner._new_session_locked(
                            name, lookout=body.get("role"))
                        self._reply(200, self._session_v2_body(session, owner._sessions_v2, owner),
                                    set_cookie=self._v2_cookie(token))
                        return
            elif self.path in ("/api/v2/advisor", SPEECH_ROUTE):
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
                    else:
                        result = owner.enqueue_advisor_locked(
                            session, body, speech=self.path == SPEECH_ROUTE)
                        status, response = {
                            "pending": (202, {"status": "pending"}),
                            "forbidden": (403, {"error": "forbidden"}),
                            "invalid": (400, {"error": "invalid_request"}),
                            "busy": (429, {"error": "busy"}),
                            "queue_full": (429, {"error": "queue_full"}),
                        }[result]
            elif self.path == MIC_ROUTE:
                # Noise discipline: the crew browser's microphone level.
                try:
                    session, digest, presented = self._authenticated_v2_locked(renew=False)
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
                    elif type(body) is not dict or set(body) != {"protocol", "level"} \
                            or body["protocol"] != 2:
                        status, response = 400, {"error": "invalid_request"}
                    elif not owner.set_mic_level_locked(session, digest, body["level"],
                                                        time.monotonic()):
                        status, response = 409, {"error": "no_station"}
                    else:
                        status, response = 200, {"status": "ok"}
            elif self.path == "/api/v2/lobby/ready":
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
                    elif (type(body) is not dict or set(body) != {"ready"}
                          or type(body["ready"]) is not bool):
                        status, response = 400, {"error": "invalid_request"}
                    elif not owner.set_ready_locked(session, body["ready"]):
                        # No lobby open, or a phone lookout / observer.
                        status, response = 409, {"error": "no_lobby"}
                    else:
                        status = 200
                        response = self._session_v2_body(session, owner._sessions_v2, owner)
            elif self.path == "/api/v2/missions":
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
                    else:
                        result = owner.enqueue_mission_op_locked(session, body)
                        status, response = {
                            "pending": (202, {"status": "pending", "id": body.get("id")
                                              if type(body) is dict else None}),
                            "forbidden": (403, {"error": "forbidden"}),
                            "invalid": (400, {"error": "invalid_request"}),
                            "queue_full": (429, {"error": "queue_full"}),
                        }[result]
            elif self.path == "/api/v2/stations/handover":
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
                    elif (type(body) is not dict
                          or set(body) != {"station", "ordinal", "request_generation", "accept"}
                          or type(body["station"]) is not str or body["station"] not in ROLES
                          or type(body["ordinal"]) is not int
                          or not 0 <= body["ordinal"] <= _SAFE_INTEGER_MAX
                          or type(body["request_generation"]) is not int
                          or not 0 <= body["request_generation"] <= _SAFE_INTEGER_MAX
                          or type(body["accept"]) is not bool):
                        status, response = 400, {"error": "invalid_request"}
                    elif session["observer"] or session["lookout_only"]:
                        status, response = 403, {"error": "forbidden"}
                    elif not owner.decide_handover_locked(
                            session, body["station"], body["ordinal"],
                            body["request_generation"], body["accept"]):
                        # The station changed hands or the request moved on.
                        status, response = 409, {"error": "stale_request"}
                    else:
                        status = 200
                        response = self._session_v2_body(session, owner._sessions_v2, owner)
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
                        elif session["observer"]:
                            status, response = 403, {"error": "observer"}
                        elif (session["lookout_only"] or owner._solo and not session["solo_host"]
                              ) and body["station"] not in LOOKOUT_ROLES:
                            # A phone lookout (or a second browser beside a
                            # solo session) only ever takes a lookout role.
                            status, response = 403, {"error": "forbidden"}
                        else:
                            station = body["station"]
                            if (session["solo_host"] and owner._solo
                                    and station not in LOOKOUT_ROLES
                                    and owner._side_conflict(session, station)):
                                # Solo: choosing a station of the other unit moves
                                # the whole session to that unit.
                                owner._solo_switch_side_locked(session, station)
                            elif (not owner._auto_grant_locked(session, station)
                                    and station not in session["leases"]
                                    and station not in session["requests"]
                                    and not owner._side_conflict(session, station)):
                                # Held by a crewmate: the holder (handover) or the host decides.
                                session["next_request_generation"] += 1
                                session["requests"][station] = session["next_request_generation"]
                            status = 200
                            response = self._session_v2_body(session, owner._sessions_v2, owner)
                    elif (type(body) is not dict
                          or set(body) != {"station", "station_generation",
                                           "active_generation"}
                          or body["station"] not in ROLES
                          or type(body["station_generation"]) is not int
                          or not 0 <= body["station_generation"] <= _SAFE_INTEGER_MAX
                          or type(body["active_generation"]) is not int
                          or not 0 <= body["active_generation"] <= _SAFE_INTEGER_MAX):
                        status, response = 400, {"error": "invalid_request"}
                    elif session["observer"]:
                        # An observer views any station without a lease.
                        if body["station_generation"] != 0:
                            status, response = 409, {"error": "stale_generation"}
                        else:
                            owner._set_active_station_locked(
                                session, body["station"] if self.path.endswith("/activate")
                                else None)
                            status = 200
                            response = self._session_v2_body(session, owner._sessions_v2, owner)
                    elif (body["station"] not in session["leases"]
                          or session["leases"][body["station"]]["generation"]
                          != body["station_generation"]):
                        status, response = 409, {"error": "stale_generation"}
                    elif self.path.endswith("/activate"):
                        owner._set_active_station_locked(session, body["station"])
                        status = 200
                        response = self._session_v2_body(session, owner._sessions_v2, owner)
                    elif (body["active_generation"] != session["active_generation"]
                          or body["station"] != session["active_station"]):
                        status, response = 409, {"error": "stale_active_generation"}
                    else:
                        owner._release_station_locked(session, body["station"])
                        status = 200
                        response = self._session_v2_body(session, owner._sessions_v2, owner)
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
                        elif (not owner._host_surface(session) if body["station"] == HOST_ROLE
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
