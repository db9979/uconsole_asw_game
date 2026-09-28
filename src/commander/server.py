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
from src.commander.web_auth import WebHostAuth
from src.core.config import SHIP_SPEED_MAX_KN

from src.commander.v2.wire import (
    station_grants,  # noqa: F401
    _log,
    _CONNECTION_DEADLINE_S,
    _CONTACT_ASSET_ROUTE,
    _MAX_PREBUILT_ROUTES,
    _MAX_PREBUILT_FILE_BYTES,
    _MAX_PREBUILT_BYTES,
    _V2_COOKIE,
    _WEB_REQUEST_ID,
    _V2_SESSION_IDLE_S,
    _V2_STATION_LEASE_S,
    _V2_SESSION_LIMIT,
    STATIONS,
    OPFOR_ROLES,
    UBOOT_COMMAND_ROLES,
    ROLES,
    LOOKOUT_ROLES,
    SONAR_ROLES,
    DIRECT_FIRE_ROLES,
    SONAR_AUDIO_ROLES,
    HOST_ROLE,
    OBSERVER_MAX,
    role_side,
    HOST_MAX_BYTES,
    STATE_MAX_BYTES,
    CHART_MAX_BYTES,
    _V2_STATION_CAPABILITIES,
    SONAR_AUDIO_BYTES,
    SONAR_AUDIO_RING_BLOCKS,
    SONAR_AUDIO_RESUME_BLOCKS,
    AUDIO_SOCKET_TIMEOUT_S,
    SONAR_AUDIO_FRAMES,
    SONAR_AUDIO_RATE,
    SONAR_STREAM_ROUTE,
    SONAR_AUDIO_STREAM_ROUTES,
    _AUDIO_POLL_ROUTES,
    VOICE_STREAM_ROUTE,
    _AUDIO_RESUME_QUERY,
    _audio_resume_cursor,
    SONAR_STREAM_MAGIC,
    SONAR_STREAM_VERSION,
    SONAR_STREAM_HEADER_BYTES,
    SONAR_STREAM_MAX_BYTES,
    SONAR_SCOPE_ROUTES,
    _WEBSOCKET_GUID,
    _SAFE_INTEGER_MAX,
    _V2_SONAR_AUDIO_FIELDS,
    _V2_COMMAND_FIELDS,
    _V2_COMMAND_GLOBAL_LIMIT,
    _V2_COMMAND_CLIENT_LIMIT,
    _V2_COMMAND_HISTORY_LIMIT,
    _V2_COMMAND_MAX_AGE_S,
    _COOKIE_NAME,
    _COOKIE_VALUE,
    _json_bytes,
    _quantized,
    _sonar_stream_payload,
    _websocket_frame,
    SIMLOG_MAX_BYTES,
    EVENTS_MAX,
    SIMLOG_ENTRIES_MAX)
from src.commander.v2.commands import (  # noqa: F401
    V2Action,
    _no_params,
    _course_params,
    _speed_params,
    _ref,
    _classification_params,
    _release_params,
    _affiliation_params,
    _fusion_refs_params,
    _single_ref_params,
    _track_label_params,
    _torpedo_params,
    _radar_params,
    _range_params,
    UBOOT_REASONS,
    _bool_params,
    _enum_params,
    _bounded_number_params,
    _COMPARTMENTS,
    _sonar_cursor_params,
    _sonar_band_params,
    _tas_side_params,
    _demon_band_params,
    _assign_profile_params,
    _tma_hypothesis_params,
    _plot_add_params,
    _plot_id,
    _plot_remove_params,
    _plot_relabel_params,
    _integration_params,
    _team_compartment_params,
    _annotation_params,
    _ecm_technique_params,
    _waypoint_params,
    _uboot_depth_params,
    _uboot_speed_params,
    _uboot_wire_params,
    _uboot_fire_params,
    _bearing_params,
    _navigation_proposal_params,
    _ref_enabled_params,
    _slot_params,
    _instructor_environment_params,
    _new_game_params,
    _HOST_ANY,
    _HOST_REPLACING,
    _HOST_STATIONS,
    _UBOOT_PLOT,
    V2_ACTION_REGISTRY,
    V2CommandEnvelope,
    _v2_command_valid,
    _object,
    _number)
from src.commander.v2.routes import (  # noqa: F401
    _OVERLOAD_RESPONSE,
    _CONNECTION_SLOT_LIMIT,
    _HTTPServer,
    _Handler)

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
        # State push: bumps on every publish and authority change; one
        # socket per session (digest -> client token).
        self._state_push_sequence = 0
        self._state_push_clients = {}
        self._state_push_enabled = True
        # Voice starts enabled in the web-host room; the host's option row
        # switches it off (plan 1.3, phase 12).
        self._voice_enabled = True
        self._voice_peers = {}
        self._voice_talker = None
        self._v2_proposals = {}
        self._v2_host = _json_bytes({"protocol": 2, "phase": "blocked"})
        self._v2_events = {}
        self._v2_private_events = {}
        self._v2_simlogs = {}
        # id(entry) -> (entry, compact JSON bytes) of the last SimLog publication
        # (main thread only); holding the entry keeps its id from being reused.
        self._v2_simlog_entry_bytes = {}
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
                self._voice_enabled = True
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
        if "sonar" in (session["active_station"], station):
            self._clear_sonar_audio_locked()
        if "helicopter" in (session["active_station"], station):
            self._clear_helicopter_audio_locked()
        if "uboot_sonar" in (session["active_station"], station):
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
        return token, session

    def _pair_admitted_locked(self, lookout) -> bool:
        """Room for one more session: the crew limit, or in solo mode the solo
        session plus one phone lookout per lookout role."""
        if not self._solo:
            return len(self._sessions_v2) < _V2_SESSION_LIMIT
        phones = sum(1 for session in self._sessions_v2.values() if session["lookout_only"])
        if lookout is not None:
            return phones < len(LOOKOUT_ROLES)
        return len(self._sessions_v2) - phones < 1

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

    def _set_observer_locked(self, session, enabled: bool) -> bool:
        """Make a session a read-only observer (at most OBSERVER_MAX), or a
        plain client again.  An observer holds no lease, views any station,
        gets the SimLog and never commands; nothing of it is persisted."""
        if enabled:
            if session["observer"]:
                return True
            if session["solo_host"] or session["web_host"]:
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
            if (session is None or session["observer"]
                    or self._side_conflict(session, station)):
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
                or capability not in (*_V2_STATION_CAPABILITIES, "simlog", "observer")
                or type(enabled) is not bool):
            raise ValueError("invalid client grant")
        with self._lock:
            self._expire_locked()
            session = self._session_by_client_locked(client_id)
            if session is None:
                return False
            if capability == "observer":
                return self._set_observer_locked(session, enabled)
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
                                "lookout_not_confirmed", *UBOOT_REASONS}
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
