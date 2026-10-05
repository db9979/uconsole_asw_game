"""Bounded HTTP transport for Remote Crew protocol v2.

The original Commander listener is unencrypted and trusted-LAN-only. The
optional web-host configuration binds to an explicit trusted LAN address behind
an exact HTTPS proxy.

This module neither imports simulation code nor starts on import. Since plan
1.3 (phase 2, step 6) the wire helpers, the command registry and the routes
live in ``src.commander.v2``; this module owns ``CommanderServer`` and
re-exports the rest."""


from collections import OrderedDict, deque
from importlib import resources
import hashlib
import ipaddress
import math
import secrets
import threading
import time
from urllib.parse import urlsplit

from src.commander.assets import static_assets
from src.commander.web_auth import FailureLimiter, WebHostAuth
from src.core.config import SHIP_SPEED_MAX_KN

from src.commander.missions import MissionLibraryServerMixin
from src.commander.server_mode import SERVER_REASONS, ServerModeServerMixin
from src.commander.advisor_web import AdvisorServerMixin
from src.commander.audio_streams import AudioStreamServerMixin
from src.commander.station_leases import StationLeaseServerMixin
from src.commander.v2.wire import (DEBRIEF_MAX_BYTES, station_grants, _log,
                                   _CONTACT_ASSET_ROUTE, _MAX_PREBUILT_ROUTES,
                                   _MAX_PREBUILT_FILE_BYTES,
                                   _MAX_PREBUILT_BYTES, _WEB_REQUEST_ID,
                                   _V2_SESSION_IDLE_S, _V2_STATION_LEASE_S,
                                   _V2_SESSION_LIMIT, STATIONS,
                                   LOBBY_SEAT_ORDER, OPFOR_ROLES,
                                   UBOOT_COMMAND_ROLES, ROLES, LOOKOUT_ROLES,
                                   MIC_CLIENTS_MAX, MIC_HOLD_S, MIC_LEVEL_MAX,
                                   DIRECT_FIRE_ROLES, SONAR_AUDIO_ROLES,
                                   HOST_ROLE, OBSERVER_MAX, role_side,
                                   HOST_MAX_BYTES, STATE_MAX_BYTES,
                                   CHART_MAX_BYTES, SONAR_AUDIO_BYTES,
                                   SONAR_AUDIO_RING_BLOCKS,
                                   SONAR_AUDIO_RESUME_BLOCKS,
                                   SONAR_AUDIO_FRAMES, SONAR_AUDIO_RATE,
                                   SONAR_STREAM_ROUTE, SONAR_STREAM_MAX_BYTES,
                                   _SAFE_INTEGER_MAX,
                                   _V2_COMMAND_HISTORY_LIMIT,
                                   _V2_COMMAND_MAX_AGE_S, _json_bytes,
                                   _sonar_stream_payload, SIMLOG_MAX_BYTES,
                                   EVENTS_MAX, SIMLOG_ENTRIES_MAX)
from src.commander.v2.commands import (_ref, UBOOT_REASONS, V2_ACTION_REGISTRY,
                                       V2CommandEnvelope, _v2_command_valid)
from src.commander.v2.routes import (  # noqa: F401
    _OVERLOAD_RESPONSE,
    _CONNECTION_SLOT_LIMIT,
    _HTTPServer,
    _Handler)

# The names other modules, tests and tools import through this facade
# (the other imports above serve this module itself).
__all__ = [
    "CommanderServer",
    "DIRECT_FIRE_ROLES",
    "EVENTS_MAX",
    "HOST_ROLE",
    "LOBBY_SEAT_ORDER",
    "OPFOR_ROLES",
    "ROLES",
    "SIMLOG_ENTRIES_MAX",
    "SIMLOG_MAX_BYTES",
    "SONAR_AUDIO_BYTES",
    "SONAR_AUDIO_FRAMES",
    "SONAR_AUDIO_RATE",
    "SONAR_AUDIO_RESUME_BLOCKS",
    "SONAR_AUDIO_RING_BLOCKS",
    "SONAR_AUDIO_ROLES",
    "SONAR_STREAM_MAX_BYTES",
    "SONAR_STREAM_ROUTE",
    "STATE_MAX_BYTES",
    "STATIONS",
    "UBOOT_COMMAND_ROLES",
    "UBOOT_REASONS",
    "V2CommandEnvelope",
    "V2_ACTION_REGISTRY",
    "_CONNECTION_SLOT_LIMIT",
    "_CONTACT_ASSET_ROUTE",
    "_Handler",
    "_OVERLOAD_RESPONSE",
    "_V2_COMMAND_MAX_AGE_S",
    "_json_bytes",
    "_sonar_stream_payload",
]

def web_catalog(catalog) -> dict:
    """The browser's catalog: every ``commander.web.*`` key plus the chart's
    country names (``country.<slug>`` served as ``commander.web.country_<slug>``)."""
    out = {key: value for key, value in catalog.items()
           if isinstance(key, str) and key.startswith("commander.web.") and isinstance(value, str)}
    out.update({"commander.web.country_" + key[len("country."):]: value
                for key, value in catalog.items()
                if isinstance(key, str) and key.startswith("country.") and isinstance(value, str)})
    return out


class CommanderServer(AudioStreamServerMixin, StationLeaseServerMixin,
                      MissionLibraryServerMixin, AdvisorServerMixin,
                      ServerModeServerMixin):
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
        self._https = None
        self._https_thread = None
        self._running = False
        self._code_index = None
        self._rotate_code_locked()
        # Wrong pairing codes per source address (one stranger never locks out
        # the crew) and, on the LAN listener only, all of them together: five
        # within 60 s rotate the code there. The web-host room never rotates
        # on anonymous failures (its code is handed out by the host).
        self._pair_failures = FailureLimiter()
        self._pair_code_failures = deque()
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
        # State push: bumps on every publish and authority change; one
        # socket per session (digest -> client token).
        self._state_push_sequence = 0
        self._state_push_clients = {}
        # Noise discipline: each crew browser's latest microphone level
        # (digest -> (level, monotonic time)); transient, never saved.
        self._mic_levels = {}
        self._state_push_enabled = True
        # Voice starts enabled in the web-host room; the host's option row
        # switches it off (plan 1.3, phase 12).
        self._voice_enabled = True
        self._voice_peers = {}
        # One push-to-talk talker per unit: the frigate's crew and the
        # boat's crew each have their own voice room (``role_side``).
        self._voice_talkers = {}
        self._v2_proposals = {}
        # The multiplayer lobby the uConsole host has open (main thread
        # publishes it, sessions read it); None while no lobby is open.
        self._lobby = None
        # Crew versus crew (``lock_teams``): sessions keep their team.
        self._teams_locked = False
        self._v2_host = _json_bytes({"protocol": 2, "phase": "blocked"})
        self._init_missions()
        self._init_advisor()
        self._init_server_mode()
        self._v2_events = {}
        self._v2_private_events = {}
        self._v2_events_fingerprint = None
        self._v2_simlogs = {}
        # id(entry) -> (entry, compact JSON bytes) of the last SimLog publication
        # (main thread only); holding the entry keeps its id from being reused.
        self._v2_simlog_entry_bytes = {}
        self._v2_debriefs = {}
        unpublished = dict(protocol=2, version="", session="unpublished", epoch=0,
                           revision=0, seq=0, phase="blocked", role=None,
                           chart_revision="unpublished")
        empty_chart = dict(protocol=2, revision="unpublished", size_nm=500,
                           landmasses=[], disclaimer="")
        self._v2_states = {role: _json_bytes(unpublished)
                           for role in (None, *ROLES)}
        self._v2_sonar_compact_state = self._v2_states["sonar"]
        self._v2_state_heads = {role: ("unpublished", 0) for role in (None, *ROLES)}
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
            lang: _json_bytes(web_catalog(translations.get(lang, {})))
            for lang in ("en", "de")
        }
        # The host's saved language: the pages open in it until a browser
        # switches (plain str swap, read by the transport threads).
        self._host_language = "en"

    def set_host_language(self, language) -> None:
        """Main thread: the language new browser pages start in."""
        if language in ("en", "de"):
            self._host_language = language

    def start(self, host: str, port: int = 8765, *, tls_context=None, tls_port=None):
        """Bind only an explicit RFC1918 or loopback IPv4 address (port 0 allowed).

        With ``tls_context`` the same routes are also served over HTTPS on
        ``tls_port`` (default the next port; 0 picks a free one) for the phone
        lookouts, whose gyroscope and microphone need a secure context."""
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
            secure = None
            if tls_context is not None:
                if tls_port is None:
                    tls_port = 0 if port == 0 else http.server_address[1] + 1
                if type(tls_port) is not int or (tls_port != 0
                                                 and not 1024 <= tls_port <= 65535):
                    http.server_close()
                    raise ValueError("invalid port")
                try:
                    secure = _HTTPServer((str(address), tls_port), self, assets,
                                         tls=tls_context)
                except OSError:
                    # The HTTPS port is taken: the crew still plays on HTTP
                    # (``tls_address`` stays None; the phone falls back to swiping).
                    secure = None
                except BaseException:
                    http.server_close()
                    raise
            thread = threading.Thread(target=http.serve_forever,
                                      kwargs={"poll_interval": 0.05},
                                      name="commander-listener", daemon=True)
            secure_thread = (None if secure is None else threading.Thread(
                target=secure.serve_forever, kwargs={"poll_interval": 0.05},
                name="commander-listener-tls", daemon=True))
            with self._lock:
                self._http = http
                self._thread = thread
                self._https = secure
                self._https_thread = secure_thread
                self._running = True
                self._voice_enabled = True
            try:
                thread.start()
                if secure_thread is not None:
                    secure_thread.start()
            except BaseException:
                with self._lock:
                    self._running = False
                    self._http = self._thread = None
                    self._https = self._https_thread = None
                http.shutdown() if thread.is_alive() else None
                http.server_close()
                if secure is not None:
                    secure.server_close()
                raise

    def stop(self):
        """Revoke access, close active sockets, and join within a bounded interval."""
        with self._lifecycle:
            with self._lock:
                listeners = [(self._http, self._thread), (self._https, self._https_thread)]
                self._running = False
                self._voice_enabled = False
                self._http = self._thread = None
                self._https = self._https_thread = None
                self._revoke_locked()
            deadline = time.monotonic() + 2.0
            for http, thread in listeners:
                if http is None:
                    continue
                http.shutdown()
                http.server_close()
                with http.work_lock:
                    workers = list(http.workers.items())
                for worker, connection in workers:
                    http._interrupt_connection(connection)
                    connection.close()
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
    def tls_address(self):
        """The phone lookouts' HTTPS address, or None without it."""
        with self._lock:
            return None if self._https is None else self._https.server_address

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

    def _record_pair_failure_locked(self, source):
        """Count a wrong pairing code against its source address.

        On the LAN listener five wrong codes in 60 s from anyone rotate the
        code (brute-force guard, as before). The web-host room keeps its code:
        rotating it on anonymous failures would let a stranger on the public
        proxy invalidate the code the host has handed to the crew.
        """
        self._pair_failures.record(source)
        if self.web_auth is not None:
            return
        self._pair_code_failures.append(time.monotonic())
        if len(self._pair_code_failures) >= 5:
            self._pair_code_failures.clear()
            self._rotate_code_locked()

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
        self._voice_talkers.clear()
        self._voice_peers.clear()
        self._mic_levels.clear()
        self._clear_sonar_audio_locked()
        self._clear_helicopter_audio_locked()
        self._clear_uboot_audio_locked()
        self._sonar_stream_sequence += 1
        self._sonar_stream_context = None
        self._sonar_stream_payload = None
        self._uboot_stream_context = None
        self._uboot_stream_payload = None
        self._state_push_sequence += 1
        self._sonar_stream_condition.notify_all()
        self._sonar_stream_clients.clear()
        self._state_push_clients.clear()
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
        self._clear_missions_locked()
        self._clear_advisor_locked()
        self._v2_events.clear()
        self._v2_private_events.clear()
        self._v2_simlogs.clear()
        self._v2_debriefs.clear()
        if rotate_code:
            self._rotate_code_locked()

    def _side_conflict(self, session, station):
        """A session never holds (or requests into) roles of both sides, and
        in a crew-versus-crew round never changes its team."""
        side = role_side(station)
        if any(role_side(role) != side for role in session["leases"]):
            return True
        if not getattr(self, "_teams_locked", False) or session["observer"]:
            return False
        if session.get("team") is None and session["leases"]:
            session["team"] = role_side(next(iter(session["leases"])))
        team = session.get("team")
        return team is not None and team != side

    def lock_teams(self, locked: bool) -> None:
        """Crew versus crew: while ``locked`` every browser stays with the unit
        it crews when the round starts (or first takes); never persisted."""
        with self._lock:
            self._teams_locked = bool(locked)
            for session in self._sessions_v2.values():
                session["team"] = (role_side(next(iter(session["leases"])))
                                   if locked and session["leases"]
                                   and not session["observer"]
                                   and not session.get("web_host") else None)

    def teams_locked(self) -> bool:
        with self._lock:
            return self._teams_locked

    # The grant table lives in wire.py so the routes can build session bodies
    # without importing this module.
    _station_grants = staticmethod(station_grants)

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
        if (station is not None and station not in session["leases"]
                and not session["observer"]):
            return False
        if session["active_station"] == station:
            return True
        peer = next((candidate for candidate in self._voice_peers.values()
                     if candidate.session is session), None)
        if peer is not None:
            self._voice_disconnect_locked(peer)
        # The audio ring belongs to the lease holder of its station. Only that
        # session switching to or from it restarts the stream; an observer (or
        # any session without the lease) looking at the station must never cut
        # the real operator's live audio.
        switched = (session["active_station"], station)
        if "sonar" in switched and "sonar" in session["leases"]:
            self._clear_sonar_audio_locked()
        if "helicopter" in switched and "helicopter" in session["leases"]:
            self._clear_helicopter_audio_locked()
        if "uboot_sonar" in switched and "uboot_sonar" in session["leases"]:
            self._clear_uboot_audio_locked()
        session["active_station"] = station
        session["active_generation"] += 1
        session["held_commands"].clear()
        self._state_push_sequence += 1
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
        if session["observer"]:
            session["observer"] = False
            self._set_active_station_locked(session, None, reason)
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
        while self._pair_code_failures and now - self._pair_code_failures[0] >= 60.0:
            self._pair_code_failures.popleft()
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
        self._ensure_leader_locked()

    def _new_session_locked(self, name: str, *, web_host=False, lookout=None):
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
            "observer": False,
            "solo_host": False,
            # Server mode: this crew browser leads (host commands beside
            # its stations, ``server_mode.py``).
            "leader": False,
            "web_host": web_host,
            # A phone lookout session (paired from /lookout): it only ever
            # holds a lookout role, also beside a solo session.
            "lookout_only": lookout is not None,
            "host_generation": 0,
            "presence": time.monotonic(),
            "last_get": time.monotonic(),
            "last_command_seq": -1,
            "command_queue": deque(),
            "command_ids": OrderedDict(),
            "command_results": deque(maxlen=_V2_COMMAND_HISTORY_LIMIT),
            "held_commands": {},
            # Lobby "ready" tick: transient, cleared whenever a lobby closes.
            "ready": False,
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
        elif lookout is not None:
            self._auto_grant_locked(session, lookout)
        elif self._solo:
            self._solo_grant_all_locked(session)
        elif self._lobby is not None:
            self._lobby_seat_locked(session)
        return token, session

    def _lobby_seat_locked(self, session):
        """Seat a browser that pairs into an open lobby on the first free
        station of the host's unit in ``LOBBY_SEAT_ORDER`` (never the
        uConsole's own station). Against a second crew it joins the unit with
        fewer humans (the frigate, with more stations, on a tie)."""
        side = self._lobby.get("side")
        if self._lobby.get("versus") == "crew":
            counts = {"frigate": 0, "uboot": 0}
            if self._lobby.get("host_station") is not None:
                counts[side] += 1
            for other in self._sessions_v2.values():
                if other is not session and other["leases"] and not other["observer"]:
                    counts["uboot" if role_side(next(iter(other["leases"]))) == "opfor"
                           else "frigate"] += 1
            side = min(("frigate", "uboot"), key=lambda unit: counts[unit])
        order = LOBBY_SEAT_ORDER.get(side, ())
        for station in order:
            if (station != self._lobby.get("host_station")
                    and self._auto_grant_locked(session, station)):
                return station
        return None

    def _pair_admitted_locked(self, lookout) -> bool:
        """Room for one more session: the crew limit, or in solo mode the solo
        session plus one phone lookout per lookout role."""
        if not self._solo:
            return len(self._sessions_v2) < _V2_SESSION_LIMIT
        phones = sum(1 for session in self._sessions_v2.values() if session["lookout_only"])
        if lookout is not None:
            return phones < len(LOOKOUT_ROLES)
        return len(self._sessions_v2) - phones < 1


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
            self._v2_debriefs.clear()

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
            peer = (self._voice_talkers.get("frigate")
                    or self._voice_talkers.get("opfor"))
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
                self._voice_talkers.clear()
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

    def voice_talker_for_locked(self, station):
        """The station talking in ``station``'s unit voice room, or None."""
        peer = self._voice_talkers.get(role_side(station))
        return None if peer is None else peer.station

    def voice_press_locked(self, peer) -> None:
        """Push-to-talk: ``peer`` takes its unit's room if nobody talks there."""
        team = role_side(peer.station)
        if self._voice_talkers.get(team) is None:
            self._voice_talkers[team] = peer
            self._voice_status_locked(team)

    def voice_release_locked(self, peer) -> None:
        team = role_side(peer.station)
        if self._voice_talkers.get(team) is peer:
            del self._voice_talkers[team]
            self._voice_status_locked(team)

    def voice_relay_locked(self, peer, payload) -> None:
        """One PCM frame of the talker to the other peers of its unit only: a
        crew never hears the other unit's crew."""
        team = role_side(peer.station)
        if self._voice_talkers.get(team) is not peer:
            return
        frame = bytes((ROLES.index(peer.station),)) + payload
        for other in self._voice_peers.values():
            if other is not peer and role_side(other.station) == team:
                other.enqueue(2, frame)

    def _voice_status_locked(self, team):
        talker = self._voice_talkers.get(team)
        payload = _json_bytes({"type": "talker",
                               "station": None if talker is None else talker.station})
        for peer in self._voice_peers.values():
            if role_side(peer.station) == team:
                peer.outgoing.append((1, payload))

    def _voice_disconnect_locked(self, peer):
        if self._voice_peers.get(peer.digest) is peer:
            del self._voice_peers[peer.digest]
        self.voice_release_locked(peer)

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
            self._pair_code_failures.clear()

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
                self._pair_code_failures.clear()

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
            self._v2_debriefs.clear()
            for session in self._sessions_v2.values():
                self._reject_session_commands_locked(session, "session_revoked")
                if not session["solo_host"]:
                    self._clear_session_authority_locked(session)
                    continue
                active = session["active_station"]
                for station in tuple(session["leases"]):
                    self._release_station_locked(session, station, "session_revoked")
                self._solo_grant_all_locked(session, active)

    def _set_observer_locked(self, session, enabled: bool) -> bool:
        """Make a session a read-only observer (at most OBSERVER_MAX), or a
        plain client again.  An observer holds no lease, views any station,
        gets the SimLog and never commands; nothing of it is persisted."""
        if enabled:
            if session["observer"]:
                return True
            if session["solo_host"] or session["web_host"] or session["leader"]:
                return False
            others = sum(1 for candidate in self._sessions_v2.values()
                         if candidate["observer"] and candidate is not session)
            if others >= OBSERVER_MAX:
                return False
            self._clear_session_authority_locked(session, "observer")
            session["observer"] = True
            session["simlog"] = True
        else:
            if not session["observer"]:
                return True
            session["observer"] = False
            session["simlog"] = False
            self._set_active_station_locked(session, None, "observer_revoked")
        self._state_push_sequence += 1
        self._sonar_stream_condition.notify_all()
        return True

    def observer_count(self) -> int:
        with self._lock:
            return sum(1 for session in self._sessions_v2.values() if session["observer"])

    def set_state_push(self, enabled: bool) -> None:
        """Host switch of the state push route; off closes every push socket
        and the browsers fall back to polling (never persisted)."""
        with self._sonar_stream_condition:
            self._state_push_enabled = bool(enabled)
            self._state_push_sequence += 1
            if not enabled:
                self._state_push_clients.clear()
            self._sonar_stream_condition.notify_all()

    def state_push_clients(self) -> int:
        with self._lock:
            return len(self._state_push_clients)

    def publish_lobby(self, room) -> None:
        """Publish the host's open lobby (``None`` closes it).

        ``room`` is a detached dict of JSON values (mission, mission_name,
        side, host_station, countdown_s). Closing a lobby clears every ready tick,
        so the next round starts with nobody ready.
        """
        with self._lock:
            if room is None and self._lobby is not None:
                for session in self._sessions_v2.values():
                    session["ready"] = False
            # ``mission_name``: an own mission's authored name (else None).
            # ``versus``: "crew" when a second crew plays the other unit.
            previous = self._lobby
            self._lobby = None if room is None else {"mission_name": None, "versus": "ai",
                                                     **dict(room)}
            if (previous is not None and self._lobby is not None
                    and self._lobby.get("versus") != "crew"
                    and previous.get("side") != self._lobby.get("side")):
                self._lobby_follow_side_locked()

    def _lobby_follow_side_locked(self):
        """Against the AI every crew browser sails the lobby's unit: when the
        unit changes, a browser on the other unit's stations is moved to the
        first free station of the new one (in pairing order)."""
        side = "opfor" if self._lobby.get("side") == "uboot" else "frigate"
        moved = False
        for session in sorted(self._sessions_v2.values(), key=lambda item: item["ordinal"]):
            if (session["observer"] or session["lookout_only"] or session.get("web_host")
                    or session["solo_host"]):
                continue
            held = [station for station in session["leases"]
                    if station not in LOOKOUT_ROLES and role_side(station) != side]
            if not held:
                continue
            for station in held:
                self._release_station_locked(session, station, "role_revoked")
            session["requests"].clear()
            session["ready"] = False
            self._lobby_seat_locked(session)
            moved = True
        if moved:
            self._state_push_sequence += 1
            self._sonar_stream_condition.notify_all()

    def set_mic_level_locked(self, session, digest, level, now) -> bool:
        """One crew browser's microphone level (transport thread): only a
        station holder on a leased station, never a phone or an observer."""
        role = session["active_station"]
        if (type(level) is not int or not 0 <= level <= MIC_LEVEL_MAX
                or session["lookout_only"] or session["observer"]
                or role not in ROLES or role in LOOKOUT_ROLES
                or role not in session["leases"]):
            return False
        if digest not in self._mic_levels and len(self._mic_levels) >= MIC_CLIENTS_MAX:
            return False
        self._mic_levels[digest] = (level, float(now))
        return True

    def mic_levels(self, now=None) -> dict:
        """The loudest held microphone level per side (``frigate``/``uboot``)
        of the sessions still holding a station; stale reports are dropped."""
        now = time.monotonic() if now is None else now
        levels = {"frigate": 0, "uboot": 0}
        with self._lock:
            for digest, (level, at) in list(self._mic_levels.items()):
                session = self._sessions_v2.get(digest)
                role = None if session is None else session["active_station"]
                if (session is None or not 0.0 <= now - at <= MIC_HOLD_S
                        or role not in session["leases"]):
                    del self._mic_levels[digest]
                    continue
                side = "uboot" if role_side(role) == "opfor" else "frigate"
                levels[side] = max(levels[side], level)
        return levels

    def set_ready_locked(self, session, ready: bool) -> bool:
        """Tick or clear a crew session's lobby ready flag (transport thread)."""
        if (self._lobby is None or type(ready) is not bool
                or session["lookout_only"] or session["observer"]):
            return False
        session["ready"] = ready
        return True

    def lobby_players_locked(self, viewer=None) -> list[dict]:
        """Lobby roster: every crew browser (no phone lookout), in pairing order."""
        return [{
            "name": session["name"],
            "stations": [station for station in ROLES if station in session["leases"]],
            "ready": session["ready"],
            "observer": session["observer"],
            "you": session is viewer,
            # Server mode: the leading browser, and the ordinal a lead
            # handover names (``host_pass_lead``).
            "leader": bool(session.get("leader")),
            "ordinal": session["ordinal"],
        } for session in sorted(self._sessions_v2.values(), key=lambda item: item["ordinal"])
            if not session["lookout_only"]]

    def lobby_players(self) -> list[dict]:
        with self._lock:
            self._expire_locked()
            return self.lobby_players_locked()

    def lobby_body_locked(self, session):
        """The ``lobby`` block of a session body, or None without an open lobby."""
        if self._lobby is None or session["lookout_only"]:
            return None
        return dict(self._lobby, ready=session["ready"],
                    players=self.lobby_players_locked(session))

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
                "observer": session["observer"],
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
        """Revalidate, apply and complete one command on the main thread.

        Three steps. (1) Under the lock: revalidate the exact origin (client,
        role, lease and active generation, grants, age, phase, world session,
        epoch, revision). The envelope is already detached by
        ``drain_commands_v2``, so it is claimed by this call alone. (2) Without
        the lock: ``apply`` (a host load/new game/save can take seconds; every
        transport thread keeps serving meanwhile). Only the main thread
        mutates the world, phase, epoch and revision, and this is the main
        thread, so nothing checked in (1) about the world can change before
        ``apply`` runs. Transport threads may revoke a lease or grant during
        ``apply``; that revocation is ordered after this command, exactly as if
        it had arrived a moment later under the old single lock section
        (stale queued commands are still rejected by the revocation itself).
        (3) Under the lock again: record the result once. ``_finish_v2_locked``
        refuses a second result for the same command id, so exactly-once
        holds even if the session was revoked in between.
        """
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
            entry = session["command_ids"].get(envelope.command_id)
            if entry is None or entry[0] != envelope.body_bytes or entry[1] is not None:
                return False  # already completed (or never accepted): never twice
            is_host = envelope.role == HOST_ROLE
            if not _v2_command_valid(body) or spec is None:
                reason = "invalid_schema"
            elif ((not self._host_surface(session) if is_host
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
                reason = None  # validated: apply below, outside the lock
            if reason is not None:
                return self._finish_v2_locked(session, envelope, "rejected", reason)
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
                        "no_mission", "mission_rejected",
                        "lookout_not_confirmed", "no_consort", "consort_lost",
                        "no_link", "stale_fix", "busy", "no_weapon", "no_track",
                        *UBOOT_REASONS, *SERVER_REASONS}
                  else "action_rejected")
        with self._lock:
            return self._finish_v2_locked(
                session, envelope, "applied" if reason == "ok" else "rejected", reason)

    def publish_v2(self, states: dict, charts: dict):
        """Atomically replace immutable, role-keyed protocol-v2 publications."""
        expected = {None, *ROLES}
        status_fields = {"protocol", "version", "session", "epoch", "revision",
                         "seq", "phase", "role", "chart_revision"}
        assigned_fields = status_fields | {"clock", "environment", "mission",
                                           "autocrew", "autocrew_overview", "audio",
                                           "weather_station", "plot", "alarms",
                                           "hit_view", "crew_noise", "lamp_tips"}
        if (not isinstance(states, dict) or not isinstance(charts, dict)
                or set(states) != expected or set(charts) != expected):
            raise ValueError("invalid v2 publication")
        encoded_states, encoded_charts = {}, {}
        # (world session, epoch) per role, kept beside the encoded state so the
        # proposal/event/SimLog polls never re-parse a state of up to 512 KiB.
        heads = {}
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
            heads[role] = (state["session"], state["epoch"])
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
            self._v2_state_heads = heads
            self._v2_charts = encoded_charts
            self._v2_sonar_compact_state = compact_sonar or encoded_states["sonar"]
            self._sonar_stream_sequence += 1
            self._state_push_sequence += 1
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
                    or set(row) != {"seq", "kind", "severity", "message", "stamp", "tag"}
                    or type(row["seq"]) is not int
                    or not previous < row["seq"] <= _SAFE_INTEGER_MAX
                    or type(row["kind"]) is not str or not 1 <= len(row["kind"]) <= 32
                    or row["severity"] not in ("info", "warning")
                    or type(row["message"]) is not str
                    or not 1 <= len(row["message"]) <= 512
                    or type(row["stamp"]) is not str or len(row["stamp"]) > 32
                    or type(row["tag"]) is not str or len(row["tag"]) > 8):
                return False
            previous = row["seq"]
        return True

    def publish_events_v2(self, *, world_session, world_epoch, latest_seq,
                          events_by_role, private_events=(), fingerprint=None):
        """Publish bounded role events plus proposal events for exact origins.

        A ``fingerprint`` equal to the last publication's (with no private
        events and nothing cleared since) skips the unchanged documents.
        """
        if (fingerprint is not None and not private_events
                and fingerprint == self._v2_events_fingerprint):
            with self._lock:
                if self._v2_events and not self._v2_private_events:
                    return
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
                # Stored with its role: the poll serves it only to that role
                # without re-parsing the document.
                encoded_private[digest] = (role, _json_bytes({
                    "protocol": 2, "session": world_session, "epoch": world_epoch,
                    "role": role, "latest_seq": latest_seq, "events": merged}))
            self._v2_events = base
            self._v2_private_events = encoded_private
            self._v2_events_fingerprint = fingerprint

    def publish_simlog_v2(self, *, world_session, world_epoch, entries_by_role):
        """Publish bounded host-granted histories including diagnostic truth."""
        if (not _ref(world_session) or type(world_epoch) is not int
                or not 0 <= world_epoch <= _SAFE_INTEGER_MAX
                or type(entries_by_role) is not dict
                or set(entries_by_role) != set(ROLES)):
            raise ValueError("invalid v2 simlog publication")
        encoded = {}
        cache, kept = self._v2_simlog_entry_bytes, {}
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
                cached = cache.get(id(entry))
                if cached is None or cached[0] is not entry:
                    cached = (entry, _json_bytes(entry))
                kept[id(entry)] = cached
                detached.append(cached[1])
            # Byte-identical to encoding the whole document, but each entry is
            # encoded once across publications instead of on every new row.
            envelope = _json_bytes({
                "protocol": 2, "session": world_session, "epoch": world_epoch,
                "role": role, "entries": []})
            payload = envelope[:-2] + b",".join(detached) + envelope[-2:]
            if len(payload) > SIMLOG_MAX_BYTES:
                raise ValueError("v2 simlog publication size limit exceeded")
            encoded[role] = payload
        self._v2_simlog_entry_bytes = kept
        with self._lock:
            self._v2_simlogs = encoded

    def publish_debrief_v2(self, *, world_session, world_epoch, documents):
        """Publish the finished mission's debrief replay per side (``frigate``,
        ``uboot``); an empty mapping withdraws it (a mission is running)."""
        if (not _ref(world_session) or type(world_epoch) is not int
                or type(documents) is not dict
                or not set(documents) <= {"frigate", "uboot"}):
            raise ValueError("invalid v2 debrief publication")
        encoded = {}
        for side, document in documents.items():
            if (type(document) is not dict or document.get("side") != side
                    or set(document) != {"side", "frames", "events", "speeds"}):
                raise ValueError("invalid v2 debrief publication")
            payload = _json_bytes(dict(document, protocol=2, available=True,
                                       session=world_session, epoch=world_epoch))
            if len(payload) > DEBRIEF_MAX_BYTES:
                raise ValueError("v2 debrief publication size limit exceeded")
            encoded[side] = payload
        with self._lock:
            self._v2_debriefs = encoded
