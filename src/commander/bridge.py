"""Main-thread, observation-only Commander projection and command authority.

Integration: call ``pump(game, server, now=None)`` exactly once per wall frame,
before Game.update(), including blocked frames. ``now`` is monotonic wall time,
not simulation time. HTTP handlers only read server-owned published copies.

``allowed`` is a local grant (initially False), bound on explicit assignment to
the current server's ``lease_generation``. Missing/invalid generations fail
closed. Expiry, re-pairing or transport replacement cannot inherit the grant.
World/sonar replacement revokes the server lease and grant. Only an explicit
grant before the first pump may defer binding until that pump's active lease.
``proposal`` is a detached dict (ref, label, status) or None. ``status`` is a
detached local dict: phase, connected, commands_allowed, session, epoch,
revision, seq. Neither property polls Game. Local accept/reject return bool;
only target acceptance changes Game.target, never selection, focus or weapons.
Navigation requests stage a separate course/speed proposal, never remote steering.
Only local accept_navigation changes helm setpoints after atomic validation.
navigation_proposal is omitted from snapshots when absent; otherwise it contains
course/speed_kn (nullable) and status. It is not persisted or carried across worlds.
The Commander overlay is identified by ``game.commander_open``. Local proposal
decisions may run there, but not in other administration or paused gameplay.

Epoch changes invalidate requests across input-owner/grant/connection changes;
revision tracks annotations, observation enums/eligibility, crew target and
proposal decisions, not movement. References bind to observation AND contact
object identity; the bounded private registry never exposes either object.
All observations, including verified sonar, receive neutral lifetime labels
C001, C002, ... alongside their opaque refs. Producer labels/contact numbers
are never forwarded, except a nonempty observed AIS name when kind is exactly
AIS and source exactly RADAR-S/AIS (at most 128 characters). Losing that AIS
source restores the neutral label; no historical AIS name is carried forward.
Reincarnation rotates both ref and neutral label. The registry retains at most
256 entries; the label counter never wraps, is bounded by 2**53 - 1 and resets
with the session. At exhaustion new observations are omitted until reset.
Identical duplicate IDs replay their original result without applying again;
different payloads with the same ID are rejected. The last 128 IDs are retained.
Damage events mark state/onset/resolution changes, not every percentage tick.
Event seq stays monotonic across sessions for the local alarm's last-seq check.
Chart geometry is copied once per world (20,000 vertices / 1,024 polygons max).
An invalid/oversized chart is omitted in its entirety, never partially drawn.
Menu/editor/splash publish status only: clock values null, mission name/objective
empty and remaining_s null, ownship numeric fields null, damage [], inventory
values null, every helo value null, tracks/events [], crew_target/proposal null.
Results retain {id, status, reasoncode}; no legacy reason alias is published.
The redacted chart is {revision: session, size_nm: 500, landmasses: [],
disclaimer: ""}. Its revision stays session; redaction and return both republish
the chart. Pause/administration retain the read-only observed picture.
Helicopter x/y/course are published only while airborne (AUF/ZURUECK), never
hangar defaults or the last position of a lost asset.
Mission alerts use known remaining seconds crossing 300/120/60 or a transition
to mission_result SIEG/VERLOREN, never hidden objective progress. First-observed
state is a silent baseline; skipped deadlines produce only the most urgent alert.

New translation keys required by the integrating branch (no placeholders):
commander.chart.disclaimer, commander.chart.omitted, commander.event.damage,
commander.event.threat, commander.event.proposal.pending,
commander.event.proposal.accepted, commander.event.proposal.rejected,
commander.event.proposal.expired, commander.event.mission.warning_300,
commander.event.mission.warning_120, commander.event.mission.warning_60,
commander.event.mission.won, commander.event.mission.lost.
Missing keys are displayed as key reports.
"""

from collections import OrderedDict, deque
from copy import deepcopy
from itertools import chain, islice
import math
import secrets
import threading
import time

from src.core import config
from src.core.i18n import localize
from src.core.version import APP_VERSION
from src.commander.server import _command_valid


def _number(value):
    if type(value) not in (int, float):
        return None
    try:
        return value if math.isfinite(value) else None
    except OverflowError:
        return None


def _age(now, timestamp):
    stamp = _number(timestamp)
    return now - stamp if stamp is not None and 0 <= stamp <= now else None


def _fresh(now, timestamp, lifetime):
    age = _age(now, timestamp)
    return age is not None and age <= lifetime


class CommanderBridge:
    def __init__(self):
        self._server = None
        self._allowed = False
        self._grant_lease = None
        self._identity = None
        self._session = secrets.token_urlsafe(24)
        self._epoch = 0
        self._revision = 0
        self._seq = 0
        self._event_seq = 0
        self._pending_seq = 0
        self._refs = {}
        self._label_seq = 0
        self._proposal = None
        self._proposal_contact = None
        self._proposal_lease = None
        self._navigation_proposal = None
        self._navigation_lease = None
        self.navigation_error = None
        self._ids = OrderedDict()
        self._results = deque(maxlen=32)
        self._events = deque(maxlen=128)
        self._fingerprint = None
        self._gate = None
        self._damage = None
        self._threats = None
        self._mission_state = None
        self._mission_warned = set()
        self._chart = None
        self._chart_world = None
        self._published_chart = None
        self._language = None
        self._last_publish = None
        self._dirty = True
        self._status = dict(phase="blocked", connected=False,
                            commands_allowed=False, session=self._session,
                             epoch=0, revision=0, seq=0)

    @staticmethod
    def _transport_lease(server):
        lease = getattr(server, "lease_generation", None)
        return lease if type(lease) is int and lease >= 0 else None

    @property
    def allowed(self) -> bool:
        if not self._allowed or self._server is None:
            return self._allowed
        return (self._grant_lease is not None
                and self._server.connected
                and self._grant_lease == self._transport_lease(self._server))

    @allowed.setter
    def allowed(self, value):
        self._main_thread()
        self._allowed = value is True
        self._grant_lease = (self._transport_lease(self._server)
                             if self._allowed and self._server is not None else None)
        if self._server is not None and not self.allowed:
            self._allowed = False
            self._grant_lease = None
        if (not self._allowed and self._navigation_proposal is not None
                and self._navigation_proposal["status"] == "pending"):
            self._proposal_status("expired", navigation=True)
        self._dirty = True

    @property
    def proposal(self):
        return None if self._proposal is None else dict(self._proposal)

    @property
    def navigation_proposal(self):
        return None if self._navigation_proposal is None else dict(self._navigation_proposal)

    @property
    def status(self):
        return dict(self._status)

    @property
    def proposal_sequence(self):
        """Monotonic local notice identity; unchanged by polling/annotations."""
        return self._pending_seq

    def invalidate_commands(self):
        """Invalidate queued input across local owner changes without revoking pairing."""
        self._main_thread()
        self._epoch += 1
        self._status["epoch"] = self._epoch
        self._dirty = True

    @staticmethod
    def _main_thread():
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError("CommanderBridge requires the main thread")

    @staticmethod
    def _phase(game, local=False):
        if not game.running or game.game_over:
            return "ended"
        if game.in_menu or getattr(game, "main_menu", False):
            return "menu"
        if game.editor is not None or game.splash_active:
            return "blocked"
        if game.paused:
            return "paused"
        commander = bool(getattr(game, "commander_open", False))
        other_admin = (game.help_open or game.nations_open or game.quit_confirm
                       or game.save_ui is not None or game.options_open)
        if (other_admin or game.input_mode is not None
                or (not local and (game.administration_open or commander))
                or (local and game.administration_open and not commander)):
            return "blocked"
        return "live"

    def _event(self, kind, severity, key):
        self._event_seq += 1
        self._events.append(dict(seq=self._event_seq, kind=kind,
                                 severity=severity, message=key))
        self._dirty = True

    def _proposal_status(self, status, *, navigation=False):
        if navigation:
            self._navigation_proposal = dict(self._navigation_proposal, status=status)
        else:
            self._proposal = dict(self._proposal, status=status)
        self._revision += 1
        self._status["revision"] = self._revision
        self._event("proposal", "info", ("commander.nav." if navigation
                                        else "commander.event.proposal.") + status)
        if status == "pending":
            self._pending_seq = self._event_seq

    def _contact(self, game, track_id, source):
        # Aircraft/missile/radio namespaces must never alias sonar target IDs.
        if not track_id.startswith("U-") or not source.startswith("SONAR-"):
            return None
        suffix = track_id[2:]
        if not suffix.isascii() or not suffix.isdigit() or len(suffix) > 20:
            return None
        target_id = int(suffix)
        if track_id != f"U-{target_id}":
            return None
        contact = game.sonar.contacts.get(target_id)
        if contact is None or contact.target_id != target_id:
            return None
        return contact

    def _tracks(self, game):
        rows, bindings, refs = [], {}, {}
        observations = chain(game.opz_tracks(), game.hfdf_bearings())
        # Bound both projection work and the registry, even with fake transports.
        for track in islice(observations, 512):
            if len(rows) == 256:
                break
            key, source = track.track_id, track.source
            if key in refs:
                continue
            lifetime = 300.0 if source == "HFDF" else config.RADAR_TRACK_STALE_S
            if not _fresh(game.sim_t, track.last_seen, lifetime):
                continue
            associated = self._contact(game, key, source)
            previous = self._refs.get(key)
            if previous is not None and previous[0] is track and previous[1] is associated:
                ref, label = previous[2:]
            else:
                if self._label_seq >= 2**53 - 1:
                    continue
                self._label_seq += 1
                ref, label = secrets.token_urlsafe(18), f"C{self._label_seq:03d}"
            # Strong references prevent Python id reuse between consecutive pumps.
            refs[key] = (track, associated, ref, label)
            if track.kind == "AIS" and source == "RADAR-S/AIS":
                observed_name = track.label
                if type(observed_name) is str and observed_name.strip():
                    label = observed_name[:128]
            contact = (associated if associated is not None
                       and _fresh(game.sim_t, associated.last_seen,
                                  config.SONAR_CONTACT_LOST_S)
                       and game.sim_t - associated.last_seen < config.SONAR_CONTACT_LOST_S
                       else None)
            fix_age = _age(game.sim_t, track.position_seen)
            positioned = (source not in ("HFDF", "SONAR-BRG")
                          and _fresh(game.sim_t, track.position_seen, lifetime))
            row = dict(ref=ref, label=label,
                       domain={"AIS": "SURFACE", "SURFACE": "SURFACE",
                               "SUB": "SUBSURFACE", "TORP": "SUBSURFACE",
                               "FLG": "AIR", "ASM": "AIR"}.get(track.kind, "UNKNOWN"),
                       source=str(source)[:64], affiliation=game.opz_affiliation(key),
                       classification=None, bearing=_number(track.bearing),
                       range_nm=None,
                       x=_number(track.x) if positioned else None,
                       y=_number(track.y) if positioned else None,
                       depth_m=None, course=_number(track.course) if positioned else None,
                       speed_kn=None, quality=_number(track.display_quality(game.sim_t, lifetime)),
                       age_s=_age(game.sim_t, track.last_seen), fix_age_s=fix_age,
                       bearing_uncertainty_deg=_number(track.bearing_uncertainty_deg),
                       range_uncertainty_nm=None, can_classify=contact is not None,
                       can_propose=contact is not None)
            if key.startswith("U-") or source.startswith("SONAR-"):
                # Never trust a mirrored sonar fix after its source evidence dies.
                for field in ("range_nm", "x", "y", "course", "fix_age_s"):
                    row[field] = None
                if source.startswith("SONAR-"):
                    row["source"] = "SONAR-BRG"
            if contact is not None:
                row["classification"] = (contact.player_class
                    if contact.player_class in config.PLAYER_CLASSES else None)
                row["bearing"] = _number(contact.passive_bearing
                    if contact.passive_bearing is not None else contact.bearing)
                row["age_s"] = _age(game.sim_t, contact.last_seen)
                row["quality"] = _number(max(contact.quality, contact.confidence))
                row["bearing_uncertainty_deg"] = _number(contact.bearing_uncertainty_deg)
                fix_lifetime = (config.SONAR_PING_FIX_MAX_AGE_S
                                if contact.range_source == "ping"
                                else config.SONAR_CONTACT_LOST_S)
                row["fix_age_s"] = _age(game.sim_t, contact.range_seen)
                if (contact.range_source in ("ping", "tma", "buoy")
                        and _fresh(game.sim_t, contact.range_seen, fix_lifetime)):
                    row.update(source="SONAR-" + contact.range_source.upper(),
                               x=_number(contact.observed_x), y=_number(contact.observed_y),
                               bearing=_number(contact.bearing),
                               range_uncertainty_nm=_number(contact.range_sigma_nm))
                    if contact.range_source == "ping":
                        row["depth_m"] = _number(contact.depth_est)
                if (_fresh(game.sim_t, contact.tma_seen, config.SONAR_CONTACT_LOST_S)
                        and contact.tma_quality >= config.TMA_RANGE_MIN_QUALITY):
                    row["course"] = _number(contact.tma_course)
                    row["speed_kn"] = _number(contact.tma_speed)
            if row["x"] is not None and row["y"] is not None:
                dx, dy = row["x"] - game.ship.x, row["y"] - game.ship.y
                row["bearing"] = math.degrees(math.atan2(dx, -dy)) % 360.0
                row["range_nm"] = math.hypot(dx, dy)
            else:
                row["x"] = row["y"] = None
                if contact is None:
                    row["course"] = None
            rows.append(row)
            bindings[ref] = (key, source, contact, track.kind in ("ASM", "TORP"))
        self._refs = refs
        return rows, bindings

    def _annotations(self, game, rows, bindings):
        target = next((row["ref"] for row in rows
                       if bindings[row["ref"]][2] is not None
                       and bindings[row["ref"]][2] is game.target), None)
        fingerprint = (tuple((r["ref"], r["label"], r["classification"], r["affiliation"],
                              r["domain"], r["source"], r["can_classify"], r["can_propose"])
                             for r in rows), target)
        if self._fingerprint is not None and fingerprint != self._fingerprint:
            self._revision += 1
            self._dirty = True
        self._fingerprint = fingerprint
        return target

    def _build_chart(self, game):
        if self._chart_world != id(game.world):
            landmasses, count = [], 0
            omitted = False
            for land in islice(game.world.coast.landmasses, 1025):
                points = land.points
                count += len(points)
                if count > 20000 or len(landmasses) >= 1024 or len(points) < 3:
                    omitted = True
                    break
                polygon = []
                for point in points:
                    if (not isinstance(point, (list, tuple)) or len(point) != 2
                            or any(_number(v) is None for v in point)):
                        omitted = True
                        break
                    polygon.append(list(point))
                if omitted:
                    break
                landmasses.append(dict(points=polygon))
            self._chart = dict(revision=self._session, size_nm=game.world.size_nm,
                               landmasses=[] if omitted else landmasses,
                               disclaimer="commander.chart.omitted" if omitted
                               else "commander.chart.disclaimer")
            self._chart_world = id(game.world)
        self._chart["revision"] = self._session

    def _command(self, game, server, envelope, now, rows, bindings):
        command = envelope.get("command") if type(envelope) is dict else None
        command_id = command.get("id") if type(command) is dict else None
        valid_id = type(command_id) is str and 0 < len(command_id) <= 64
        reason = "invalid_schema"
        valid = (type(command) is dict
                 and {"id", "session", "epoch", "revision", "action"} <= command.keys()
                 and not command.keys() - {"id", "session", "epoch", "revision", "action", "track", "value"}
                 and valid_id and type(command["session"]) is str
                 and 0 < len(command["session"]) <= 64
                 and type(command["epoch"]) is int and 0 <= command["epoch"] <= 2**53 - 1
                 and type(command["revision"]) is int and 0 <= command["revision"] <= 2**53 - 1
                 and type(command["action"]) is str
                 and command["action"] in ("classify", "affiliate", "propose", "clear_proposal")
                 and ("track" not in command or
                      type(command["track"]) is str and 0 < len(command["track"]) <= 64)
                 and (command.get("value") is None or
                      type(command["value"]) is str and len(command["value"]) <= 64))
        if valid:
            action, value, ref = command["action"], command.get("value"), command.get("track")
            valid = ((action == "classify" and ref is not None and "value" in command
                      and (value is None or value in config.PLAYER_CLASSES))
                     or (action == "affiliate" and ref is not None and value in config.NATO_AFFILIATIONS)
                     or (action == "propose" and ref is not None and "value" not in command)
                     or (action == "clear_proposal" and "value" not in command))
        if (type(command) is dict and command.get("action") == "propose_navigation"
                and _command_valid(command)):
            valid = True
            action, value, ref = command["action"], None, None
        if valid:
            if (set(envelope) != {"command", "lease", "received_at"}
                    or type(envelope["lease"]) is not int
                    or not _fresh(now, envelope["received_at"], 5.0)
                    or not server.is_current(envelope)):
                reason = "unauthorized"
            elif command["session"] != self._session:
                reason = "stale_session"
            elif command["epoch"] != self._epoch:
                reason = "stale_epoch"
            elif (not self.allowed or envelope["lease"] != self._grant_lease
                  or not self._status["commands_allowed"]):
                reason = "commands_blocked"
            elif command_id in self._ids:
                previous, result = self._ids[command_id]
                if previous == command:
                    self._results.append(dict(result))
                    self._dirty = True
                    return
                reason = "duplicate_id"
            elif command["revision"] != self._revision:
                reason = "revision_conflict"
            elif action not in ("clear_proposal", "propose_navigation") and ref not in bindings:
                reason = "unknown_track"
            elif (action == "clear_proposal" and ref is not None
                  and (self._proposal is None or ref != self._proposal["ref"])):
                reason = "unknown_track"
            elif action in ("classify", "propose") and bindings[ref][2] is None:
                reason = "ineligible_track"
            else:
                reason = "ok"
                if action == "classify":
                    bindings[ref][2].player_class = value
                elif action == "affiliate":
                    game.opz_affiliations[bindings[ref][0]] = value
                elif action == "propose":
                    row = next(r for r in rows if r["ref"] == ref)
                    self._proposal = dict(ref=ref, label=row["label"], status="pending")
                    self._proposal_contact = bindings[ref][2]
                    self._proposal_lease = envelope["lease"]
                    self._proposal_status("pending")
                elif action == "propose_navigation":
                    self._navigation_proposal = dict(course=command.get("course"),
                        speed_kn=command.get("speed_kn"), status="pending")
                    self._navigation_lease = envelope["lease"]
                    self.navigation_error = None
                    self._proposal_status("pending", navigation=True)
                elif self._proposal is not None:
                    self._proposal_status("rejected")
                    self._proposal = self._proposal_contact = self._proposal_lease = None
        result = dict(id=command_id if valid_id else "", status="applied" if reason == "ok"
                      else "rejected", reasoncode=reason)
        if (valid and command["session"] == self._session
                and command_id not in self._ids):
            self._ids[command_id] = (dict(command), dict(result))
            if len(self._ids) > 128:
                self._ids.popitem(last=False)
        self._results.append(result)
        self._dirty = True

    def pump(self, game, server, now=None):
        """Project and drain at most four commands; publish at 2 Hz/no catchup."""
        self._main_thread()
        now = time.monotonic() if now is None else now
        if _number(now) is None or now < 0:
            raise ValueError("now must be finite monotonic seconds")
        if self._server is None:
            if self._allowed:
                self._grant_lease = self._transport_lease(server)
        elif self._server is not server:
            self.allowed = False
        self._server = server
        identity = (id(game.world), id(game.sonar))
        if identity != self._identity:
            if self._identity is not None:
                self.allowed = False
                server.revoke()
                self._session = secrets.token_urlsafe(24)
                self._epoch += 1
                self._revision = self._seq = 0
                self._refs.clear()
                self._label_seq = 0
                self._ids.clear()
                self._results.clear()
                self._events.clear()
                self._proposal = self._proposal_contact = self._proposal_lease = None
                self._navigation_proposal = self._navigation_lease = None
                self.navigation_error = None
                self._fingerprint = self._damage = self._threats = None
                self._mission_state = None
                self._mission_warned.clear()
                self._gate = None
            self._identity = identity
            self._dirty = True
        phase = self._phase(game)
        connected = bool(server.connected)
        lease = self._transport_lease(server)
        if self._allowed and not self.allowed:
            self.allowed = False
        gate = (phase, self.allowed is True, connected, bool(game.help_open),
                bool(game.nations_open), bool(game.quit_confirm), game.save_ui,
                bool(game.options_open), bool(getattr(game, "commander_open", False)),
                game.input_mode, id(game.editor), bool(game.splash_active),
                bool(game.paused), bool(game.in_menu), bool(game.main_menu),
                bool(game.running), bool(game.game_over), lease, id(server))
        if gate != self._gate:
            if self._gate is not None:
                self._epoch += 1
            self._gate = gate
            self._dirty = True
        self._status.update(phase=phase, connected=connected,
                            commands_allowed=self.allowed is True and connected and phase == "live")
        redacted = (game.in_menu or game.main_menu or game.editor is not None
                    or game.splash_active)
        if redacted:
            self._refs.clear()
            if self._proposal is not None:
                self._proposal = self._proposal_contact = self._proposal_lease = None
                self._revision += 1
                self._dirty = True
            if self._navigation_proposal is not None:
                self._navigation_proposal = self._navigation_lease = None
                self._revision += 1
                self._dirty = True
            self._events.clear()
            self._damage = self._threats = self._mission_state = None
            rows, bindings = [], {}
        else:
            rows, bindings = self._tracks(game)
        target = self._annotations(game, rows, bindings)
        if self._proposal is not None and self._proposal["status"] == "pending":
            bound = bindings.get(self._proposal["ref"])
            if (not connected or self.allowed is not True or bound is None
                    or self._proposal_lease != lease
                    or bound[2] is not self._proposal_contact):
                self._proposal_status("expired")
        if (self._navigation_proposal is not None
                and self._navigation_proposal["status"] == "pending"
                and (not connected or not self.allowed or self._navigation_lease != lease)):
            self._proposal_status("expired", navigation=True)
        for envelope in islice(server.drain_commands(limit=4), 4):
            self._command(game, server, envelope, now, rows, bindings)
            if not redacted:
                rows, bindings = self._tracks(game)
                target = self._annotations(game, rows, bindings)
        # HTTP threads may expire/re-pair while this frame drains its batch.
        if self._allowed and not self.allowed:
            self.allowed = False
            self._status["commands_allowed"] = False
            if self._proposal is not None and self._proposal["status"] == "pending":
                self._proposal_status("expired")
        damage, remaining = [], None
        if not redacted:
            damage = [dict(key=c.key, name=game.tr("compartment." + c.key),
                           state=c.state, flood=c.flood, fire=c.fire,
                           teams=game.damage.teams_on(c.key))
                      for c in game.damage.compartments.values()]
            damage_state = tuple((r["key"], r["state"], r["flood"] > 0, r["fire"] > 0)
                                 for r in damage)
            if self._damage is not None and damage_state != self._damage:
                self._event("damage", "warning", "commander.event.damage")
            self._damage = damage_state
            threats = {r["ref"] for r in rows if bindings[r["ref"]][3] or r["source"] == "HOJ"
                       or r["affiliation"] == "HOSTILE"}
            if self._threats is not None and threats - self._threats:
                self._event("threat", "warning", "commander.event.threat")
            self._threats = threats
            remaining = _number(game.mission.remaining_s(game.mission_time))
            result = game.mission_result
            if self._mission_state is not None:
                previous_remaining, previous_result = self._mission_state
                if result in ("SIEG", "VERLOREN") and result != previous_result:
                    self._event("mission", "info" if result == "SIEG" else "warning",
                                "commander.event.mission." + ("won" if result == "SIEG" else "lost"))
                elif (result is None and phase != "ended" and remaining is not None
                      and remaining > 0 and previous_remaining is not None):
                    crossed = {threshold for threshold in (300, 120, 60)
                               if previous_remaining > threshold >= remaining
                               and threshold not in self._mission_warned}
                    if crossed:
                        self._mission_warned.update(crossed)
                        self._event("mission", "warning",
                                    "commander.event.mission.warning_" + str(min(crossed)))
            self._mission_state = (remaining, result)
        self._status.update(session=self._session, epoch=self._epoch,
                            revision=self._revision, seq=self._seq)
        if self._language != game.preferences.language:
            self._language = game.preferences.language
            self._dirty = True
        if not self._dirty and self._last_publish is not None and now - self._last_publish < .5:
            return
        ownship = {key: None for key in
                   ("x", "y", "course", "speed", "target_course", "target_speed")}
        ownship.update(damage=damage, inventory=dict.fromkeys(
            ("torpedoes", "vls", "ciws", "chaff_ready")), helo=dict.fromkeys(
                ("state", "x", "y", "course", "fuel_s", "torpedoes", "buoys")))
        clock = dict.fromkeys(("sim", "mission", "time_scale", "world"))
        mission = dict(name="", objective="", remaining_s=None)
        chart = dict(revision=self._session, size_nm=500, landmasses=[], disclaimer="")
        if not redacted:
            self._build_chart(game)
            ship, helo = game.ship, game.helo
            airborne = helo.airborne
            ownship.update({key: _number(getattr(ship, key)) for key in
                            ("x", "y", "course", "speed", "target_course", "target_speed")})
            ownship.update(inventory=dict(
                torpedoes=game.torpedo_count, vls=game.vls_cells, ciws=game.ciws_ammo,
                chaff_ready=game.chaff_cd <= 0), helo=dict(
                    state=helo.state, x=_number(helo.x) if airborne else None,
                    y=_number(helo.y) if airborne else None,
                    course=_number(helo.course) if airborne else None,
                    fuel_s=helo.fuel_s, torpedoes=helo.torps, buoys=helo.buoys_left))
            clock = dict(sim=game.sim_t, mission=game.mission_time,
                         time_scale=game.time_scale, world=game.world.hour)
            mission = dict(name=localize(game.mission_name_display(), game.tr),
                           objective=localize(game.mission_objective_display(), game.tr),
                           remaining_s=remaining)
            chart = dict(self._chart, disclaimer=game.tr(self._chart["disclaimer"]))
        self._seq += 1
        self._status["seq"] = self._seq
        state = dict(protocol=1, version=APP_VERSION, session=self._session,
                     epoch=self._epoch, revision=self._revision, seq=self._seq,
                     phase=phase, commands_allowed=self._status["commands_allowed"],
                     language=game.preferences.language,
                      clock=clock, mission=mission,
                     ownship=ownship, tracks=rows, crew_target=target,
                     proposal=self.proposal,
                     events=[dict(e, message=game.tr(e["message"])) for e in self._events],
                      results=list(self._results), chart_revision=self._session)
        if self._navigation_proposal is not None:
            state["navigation_proposal"] = self.navigation_proposal
        chart_key = (self._session, self._language, redacted)
        if chart_key == self._published_chart:
            chart = None
        # Publication transfers no mutable references back into Game or the bridge.
        server.publish(deepcopy(state), chart=deepcopy(chart))
        self._published_chart = chart_key
        self._last_publish = now
        self._dirty = False

    def _decide(self, game, accepted):
        self._main_thread()
        if (self._identity != (id(game.world), id(game.sonar))
                or self._phase(game, local=True) != "live"
                or self.allowed is not True or self._server is None
                or not self._server.connected
                or self._proposal is None or self._proposal["status"] != "pending"):
            return False
        rows, bindings = self._tracks(game)
        bound = bindings.get(self._proposal["ref"])
        if (self._proposal_lease != self._grant_lease or bound is None
                or bound[2] is None or bound[2] is not self._proposal_contact):
            self._proposal_status("expired")
            return False
        if accepted:
            game.target = bound[2]
        self._proposal_status("accepted" if accepted else "rejected")
        self._annotations(game, rows, bindings)
        self._status["revision"] = self._revision
        return True

    def accept_proposal(self, game) -> bool:
        return self._decide(game, True)

    def reject_proposal(self, game) -> bool:
        return self._decide(game, False)

    def _decide_navigation(self, game, accepted):
        self._main_thread()
        self.navigation_error = "commander.local.error.proposal"
        proposal = self._navigation_proposal
        if (self._identity != (id(game.world), id(game.sonar))
                or self._phase(game, local=True) != "live"
                or not self.allowed or self._server is None or not self._server.connected
                or proposal is None or proposal["status"] != "pending"):
            return False
        if self._navigation_lease != self._grant_lease:
            self._proposal_status("expired", navigation=True)
            return False
        if accepted:
            course, speed = proposal["course"], proposal["speed_kn"]
            # Validate the whole order before either setpoint changes.
            if ((course is None and speed is None)
                    or (course is not None and (_number(course) is None or not 0 <= course < 360))
                    or (speed is not None and (_number(speed) is None
                                              or not 0 <= speed <= config.SHIP_SPEED_MAX_KN))):
                self.navigation_error = "commander.local.navigation.invalid"
                return False
            if course is not None and game.damage.station_down("bridge"):
                self.navigation_error = "commander.local.navigation.bridge_down"
                return False
            if course is not None:
                game.ship.target_course = course
            if speed is not None:
                game.ship.target_speed = speed
                game.ship.order_idx = min(range(len(config.TELEGRAPH_ORDERS)),
                    key=lambda i: abs(config.TELEGRAPH_ORDERS[i][1] - speed))
        self._proposal_status("accepted" if accepted else "rejected", navigation=True)
        self.navigation_error = None
        return True

    def accept_navigation(self, game) -> bool:
        """Explicit local crew confirmation; remote requests only stage proposals."""
        return self._decide_navigation(game, True)

    def reject_navigation(self, game) -> bool:
        return self._decide_navigation(game, False)
