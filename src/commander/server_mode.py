"""Server mode over Remote Crew: the uConsole only serves, a browser leads.

In server mode (``--server`` or the main menu's "Server" entry) the uConsole
works no station and shows only how to join and who is aboard. One crew
browser is the game leader: it gets the host command surface next to its
stations, so it picks and starts the lobby's mission, saves, loads and ends
a mission. Everything else stays ordinary crew mode: every browser takes its
own stations, the AI mans the free ones.

The leader is the oldest paired crew browser (never a phone lookout, an
observer or the web-host placeholder). While it is away (no session poll
for ``_V2_STATION_LEASE_S``) and another crew browser is present, the lead
passes on; the leader may also hand it to a crewmate. Gaining or losing the
lead advances the session's host generation, so a host command prepared
before fails closed.

``crew_rebase`` keeps the crew across a world replacement (a lobby round's
start, a load): sessions, cookies and join code survive, every held station
is leased again under a fresh generation and all queued input is rejected.

Nothing here is saved or put into settings.
"""

from __future__ import annotations

import time

from src.commander.v2.wire import HOST_ROLE, _V2_STATION_LEASE_S, _json_bytes

# Result reasons of the leader's host actions (``src/commander/actions.py``).
SERVER_REASONS = frozenset({"use_lobby", "lobby_counting", "lobby_invalid",
                            "lobby_confirm", "campaign_unavailable",
                            "lead_unavailable"})


class ServerModeServerMixin:
    """Leader selection and the crew-keeping world rebase."""

    def _init_server_mode(self) -> None:
        self._server_mode = False

    @property
    def server_mode(self) -> bool:
        with self._lock:
            return self._server_mode

    def set_server_mode(self, enabled: bool) -> None:
        """Switch server mode; the lead goes to the oldest crew browser."""
        if type(enabled) is not bool:
            raise ValueError("server mode must be a bool")
        with self._lock:
            if enabled is self._server_mode:
                return
            self._server_mode = enabled
            for session in self._sessions_v2.values():
                self._drop_leader_locked(session)
            self._ensure_leader_locked()
            self._state_push_sequence += 1
            self._sonar_stream_condition.notify_all()

    @staticmethod
    def _host_surface(session) -> bool:
        """The session may send host commands: the solo session or the leader."""
        return bool(session["solo_host"] or session.get("leader"))

    @staticmethod
    def _leader_eligible(session) -> bool:
        return not (session["lookout_only"] or session["observer"]
                    or session.get("web_host"))

    def _drop_leader_locked(self, session, reason="role_revoked") -> None:
        if session.get("leader"):
            self._reject_station_commands_locked(session, HOST_ROLE, reason)
            session["leader"] = False
            session["host_generation"] += 1

    def _make_leader_locked(self, session) -> None:
        session["leader"] = True
        session["host_generation"] += 1
        self._state_push_sequence += 1
        self._sonar_stream_condition.notify_all()

    def _ensure_leader_locked(self) -> None:
        """Keep exactly one leader in server mode (none outside it)."""
        if not self._server_mode:
            return
        now = time.monotonic()
        eligible = sorted((session for session in self._sessions_v2.values()
                           if self._leader_eligible(session)),
                          key=lambda session: session["ordinal"])
        present = [session for session in eligible
                   if 0 <= now - session["presence"] < _V2_STATION_LEASE_S]
        current = next((session for session in self._sessions_v2.values()
                        if session.get("leader")), None)
        if current is not None and not self._leader_eligible(current):
            self._drop_leader_locked(current)
            current = None
        if current is not None and (current in present or not present):
            return
        candidates = present or eligible
        if not candidates:
            return
        if current is not None:
            self._drop_leader_locked(current)
        self._make_leader_locked(candidates[0])

    def pass_leader(self, ordinal) -> bool:
        """The leader hands the lead to the crew browser with ``ordinal``."""
        if type(ordinal) is not int:
            return False
        with self._lock:
            self._expire_locked()
            if not self._server_mode:
                return False
            target = next((session for session in self._sessions_v2.values()
                           if session["ordinal"] == ordinal), None)
            if target is None or not self._leader_eligible(target):
                return False
            if target.get("leader"):
                return True
            for session in self._sessions_v2.values():
                self._drop_leader_locked(session)
            self._make_leader_locked(target)
            return True

    def leader_name(self):
        """The leader's display name (the uConsole's server screen), or None."""
        with self._lock:
            self._expire_locked()
            return next((session["name"] for session in self._sessions_v2.values()
                         if session.get("leader")), None)

    def crew_rebase(self) -> None:
        """Keep every crew session across a world replacement.

        Sessions, cookies, CSRF tokens, command history and the join code
        survive. Every queued or held command is rejected, every held station
        is leased again under a new generation with its grants and the active
        generation advances, so nothing prepared for the old world can act on
        the new one. The leader keeps its host generation (as the solo session
        does): its host commands name the world session they were made for.
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
                active = session["active_station"]
                held = [(station, dict(lease["grants"]))
                        for station, lease in session["leases"].items()]
                for station, _grants in held:
                    self._release_station_locked(session, station, "session_revoked")
                for station, grants in held:
                    self._station_generations[station] += 1
                    session["leases"][station] = {
                        "generation": self._station_generations[station],
                        "grants": grants,
                    }
                session["requests"].clear()
                session["active_station"] = None
                if active is not None and (active in session["leases"]
                                           or session["observer"]):
                    self._set_active_station_locked(session, active)
                elif session["leases"]:
                    self._set_active_station_locked(session, next(iter(session["leases"])))
                else:
                    session["active_generation"] += 1
            self._state_push_sequence += 1
            self._sonar_stream_condition.notify_all()
