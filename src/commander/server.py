"""Bounded HTTP transport for a single Commander on a trusted LAN.

HTTP is unencrypted. Tokens and pairing codes must not cross an untrusted
network. This module neither imports simulation code nor starts on import.
"""

from collections import deque
from http.server import BaseHTTPRequestHandler, HTTPServer
from importlib import resources
import io
import ipaddress
import json
import math
import secrets
import socket
import threading
import time
import re

from src.core.config import SHIP_SPEED_MAX_KN


_CONNECTION_DEADLINE_S = 3.0
_CONTACT_ASSET_ROUTE = re.compile(
    r"/contact-analysis/[a-z0-9][a-z0-9_.-]{0,95}-(?:cruise|high)\.png").fullmatch
_MAX_PREBUILT_ROUTES = 227
_MAX_PREBUILT_FILE_BYTES = 4 * 1024 * 1024
_MAX_PREBUILT_BYTES = 32 * 1024 * 1024


def _json_bytes(value):
    return json.dumps(value, allow_nan=False, ensure_ascii=True,
                      separators=(",", ":")).encode("ascii")


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
    expire after 300 unpaired seconds, and allow five misses per rolling minute
    across all clients. Only explicit local ``revoke()`` resets that budget.
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
        self._lease = 0
        self._last_get = 0.0
        self._commands = deque()
        self._snapshot = b"{}"
        self._chart = b"{}"
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
        self._code_created = time.monotonic()

    def _revoke_locked(self):
        self._token = None
        self._lease += 1
        self._commands.clear()
        self._rotate_code_locked()

    def _expire_locked(self):
        now = time.monotonic()
        while self._pair_failures and now - self._pair_failures[0] >= 60.0:
            self._pair_failures.popleft()
        if self._token is not None and now - self._last_get >= 30.0:
            self._revoke_locked()
        elif self._token is None and now - self._code_created >= 300.0:
            self._rotate_code_locked()

    def revoke(self):
        with self._lock:
            self._revoke_locked()
            self._pair_failures.clear()

    def publish(self, snapshot: dict, chart: dict | None = None):
        if not isinstance(snapshot, dict) or (chart is not None and not isinstance(chart, dict)):
            raise TypeError("snapshot and chart must be dictionaries")
        snapshot_bytes = _json_bytes(snapshot)
        chart_bytes = None if chart is None else _json_bytes(chart)
        with self._lock:
            self._snapshot = snapshot_bytes
            if chart_bytes is not None:
                self._chart = chart_bytes

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

    def _reply(self, status, value, content_type="application/json; charset=utf-8"):
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
        self.end_headers()
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
        for name in ("Host", "Origin", "Content-Length", "Content-Type", "Authorization"):
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

    def _get(self):
        owner = self.server.owner
        if self.path in self.server.assets:
            content_type, body = self.server.assets[self.path]
            self._reply(200, body, content_type)
        elif self.path in ("/api/v1/ui?lang=en", "/api/v1/ui?lang=de"):
            self._reply(200, owner._translations[self.path[-2:]])
        elif self.path in ("/api/v1/state", "/api/v1/chart"):
            with owner._lock:
                authenticated = self._authenticated_locked(renew=True)
                body = owner._snapshot if self.path == "/api/v1/state" else owner._chart
            if authenticated:
                self._reply(200, body)
            else:
                self.send_error(401)
        else:
            self.send_error(404)

    def _post(self, body, received_at):
        owner = self.server.owner
        status, response = 404, {"error": "not_found"}
        with owner._lock:
            owner._expire_locked()
            if self.path == "/api/v1/pair":
                if not owner._running:
                    status, response = 503, {"error": "unavailable"}
                elif owner._token is not None:
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
                    owner._rotate_code_locked()
                    owner._last_get = time.monotonic()
                    status, response = 200, {"token": owner._token}
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
        self._reply(status, response)
