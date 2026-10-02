"""Remote Crew station leases: grants, requests, handovers and revocation
of the exclusive station roles.  Moved verbatim from ``server.py``;
``CommanderServer`` inherits ``StationLeaseServerMixin``.
"""

from src.commander.v2.wire import (
    ROLES, DIRECT_FIRE_ROLES, SONAR_AUDIO_ROLES, HANDOVER_MAX, _V2_STATION_CAPABILITIES)


class StationLeaseServerMixin:
    """Station-lease half of ``CommanderServer`` (state and lock live on the server)."""

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

    def handover_requests_locked(self, session) -> list[dict]:
        """Pending requests for the stations ``session`` holds, as the
        ``handover`` block of its session body: requester name and ordinal
        only, station order then pairing order, bounded. Observers and phone
        lookouts decide nothing."""
        if session["observer"] or session["lookout_only"]:
            return []
        rows = sorted(((ROLES.index(station), other["ordinal"], station, other)
                       for other in self._sessions_v2.values() if other is not session
                       for station in other["requests"] if station in session["leases"]),
                      key=lambda row: row[:2])
        return [{"station": station, "name": other["name"], "ordinal": other["ordinal"],
                 "request_generation": other["requests"][station]}
                for _index, _ordinal, station, other in rows[:HANDOVER_MAX]]

    def decide_handover_locked(self, holder, station, ordinal, request_generation,
                               accept) -> bool:
        """The holder of ``station`` hands it to the exact pending request of
        the session with ``ordinal`` (full rights, like the host approval) or
        declines it. False when the holder no longer holds the station or the
        request changed (stale)."""
        if (station not in ROLES or type(ordinal) is not int
                or type(request_generation) is not int or type(accept) is not bool
                or holder["observer"] or holder["lookout_only"]
                or station not in holder["leases"]):
            return False
        requester = next((other for other in self._sessions_v2.values()
                          if other["ordinal"] == ordinal and other is not holder), None)
        if (requester is None
                or requester["requests"].get(station) != request_generation):
            return False
        if not accept:
            del requester["requests"][station]
            return True
        if requester["observer"] or self._side_conflict(requester, station):
            return False
        self._release_station_locked(holder, station)
        requester["leases"][station] = {
            "generation": self._station_generations[station],
            "grants": self._station_grants(station),
        }
        del requester["requests"][station]
        self._set_active_station_locked(requester, station)
        return True

    def decide_handover(self, client_id, station, ordinal, request_generation,
                        accept) -> bool:
        """Locked form of ``decide_handover_locked`` for the holder ``client_id``."""
        with self._lock:
            self._expire_locked()
            holder = self._session_by_client_locked(client_id)
            return holder is not None and self.decide_handover_locked(
                holder, station, ordinal, request_generation, accept)

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
