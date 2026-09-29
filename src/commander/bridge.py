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
The simulation never pauses: local menus and overlays own local input only, so
the phase stays live behind them and local proposal decisions remain possible.

Epoch changes invalidate requests across input-owner/grant/connection changes;
revision tracks annotations, observation enums/eligibility, crew target and
proposal decisions, not movement. References bind to observation AND contact
object identity; the bounded private registry never exposes either object.
All observations, including verified sonar, receive neutral lifetime labels
C001, C002, ... alongside their opaque refs. Producer labels/contact numbers
and the external origin of live-traffic entities are never forwarded.
Reincarnation rotates both ref and neutral label. The registry retains at most
256 entries; the label counter never wraps, is bounded by 2**53 - 1 and resets
with the session. At exhaustion new observations are omitted until reset.
Identical duplicate IDs replay their original result without applying again;
different payloads with the same ID are rejected. The last 128 IDs are retained.
Damage events mark state/onset/resolution changes, not every percentage tick.
Event seq stays monotonic across sessions for the local alarm's last-seq check.
Chart geometry is copied once per world (20,000 vertices / 1,024 polygons max).
An invalid/oversized chart is omitted in its entirety, never partially drawn.
Menu/editor/splash publish status only: clock/environment values null, mission
name/objective empty and remaining_s null, ownship numeric fields null, damage
[], inventory values null, every helo value null, tracks/events [],
crew_target/proposal null.
Results retain {id, status, reasoncode}; no legacy reason alias is published.
The redacted chart is {revision: session, size_nm: 500, landmasses: [],
disclaimer: ""}. Its revision stays session; redaction and return both republish
the chart.
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
import os
import secrets
import threading
import time

import numpy as np

from src.audio.receiver import smooth_limit
from src.sonar.sonar import SonarSystem
from src.core import config, opfor
from src.sensors import lookout_id
from src.commander.lookout_projection import build_lookout_states
from src.commander.server import (HOST_ROLE, OPFOR_ROLES, ROLES, UBOOT_COMMAND_ROLES, SIMLOG_ENTRIES_MAX,
                                  SIMLOG_MAX_BYTES, V2_ACTION_REGISTRY, _json_bytes)
from src.commander.projections import (ROLE_NAMES, build_opfor_states,
                                       build_role_states, known_chart,
                                       redacted_chart, redacted_state)


from src.commander.actions import (  # noqa: F401 - re-exported
    _number,
    _acknowledge,
    _bridge_set_course,
    _bridge_set_speed,
    _bridge_route_add,
    _bridge_route_pattern,
    _bridge_route_clear,
    _bound,
    _sonar_classify,
    _sonar_set_release,
    _helicopter_qualify,
    _helicopter_buoy_release,
    _opz_id,
    _opz_classify,
    _opz_affiliate,
    _opz_set_track_id,
    _opz_create_fusion,
    _opz_dissolve_fusion,
    _opz_dismiss_suggestion,
    _opz_set_ciws,
    _opz_set_radar,
    _opz_set_range,
    _opz_designate_target,
    _engine_set_telegraph,
    _engine_set_course,
    _engine_set_speed,
    _engine_set_quiet_mode,
    _engine_set_plant,
    _damage_counterflood,
    _damage_assign_team,
    _damage_unassign_team,
    _radio_capture_hfdf,
    _crew_action_stations,
    _crew_watch_change,
    _radio_task_accept,
    _radio_request_ras,
    _radio_task_decline,
    _eloka_annotate,
    _eloka_clear_annotation,
    _eloka_set_jamming,
    _eloka_set_technique,
    _eloka_set_auto,
    _sonar_contact,
    _sonar_set_listen_bearing,
    _sonar_set_focus,
    _sonar_clear_focus,
    _sonar_set_array_mode,
    _sonar_set_tas,
    _sonar_set_tow_depth,
    _sonar_set_vds,
    _sonar_set_vds_depth,
    _opz_mark_blip,
    _sonar_measure_bt,
    _sonar_active_ping,
    _sonar_set_tma_enabled,
    _sonar_set_gain,
    _sonar_set_audition_mode,
    _sonar_set_band_preset,
    _sonar_set_notch,
    _sonar_set_peak_hold,
    _sonar_set_harmonic,
    _sonar_set_cursor,
    _sonar_mark_line,
    _plot_add,
    _plot_remove,
    _plot_relabel,
    _plot_clear,
    _sonar_set_integration,
    _sonar_set_vernier,
    _sonar_set_band,
    _sonar_set_operator_notch,
    _sonar_tas_side,
    _sonar_set_demon_band,
    _sonar_set_heterodyne,
    _sonar_assign_profile,
    _sonar_tma_set,
    _sonar_tma_accept,
    _sonar_tma_copy_proposal,
    _sonar_designate_target,
    _helicopter_launch,
    _helicopter_return,
    _helicopter_set_waypoint,
    _helicopter_deploy_buoy,
    _helicopter_set_pattern,
    _helicopter_set_mad,
    _helicopter_set_buoy_mode,
    _helicopter_set_listen_source,
    _helicopter_set_listen_bearing,
    _helicopter_clear_listen_bearing,
    _helicopter_set_audio_mode,
    _helicopter_set_audio_band,
    _helicopter_set_audio_gain,
    _helicopter_set_audio_notch,
    _helicopter_set_dipping,
    _helicopter_set_dip_depth,
    _helicopter_dipping_ping,
    _direct_observation,
    _weapons_launch_torpedo,
    _helicopter_launch_torpedo,
    _mpa_request,
    _mpa_return,
    _mpa_set_waypoint,
    _mpa_set_pattern,
    _mpa_drop_buoy,
    _mpa_set_buoy_mode,
    _mpa_set_radar,
    _mpa_attack,
    _weapons_set_torpedo_settings,
    _weapons_deploy_nixie,
    _weapons_fire_asroc,
    _weapons_drop_depth_charges,
    _opz_launch_essm,
    _opz_launch_chaff,
    _UBOOT_REASONS,
    _uboot_result,
    _uboot_set_course,
    _uboot_set_speed,
    _uboot_set_depth,
    _uboot_fire,
    _uboot_decoy,
    _uboot_tube_load,
    _uboot_tube_flood,
    _uboot_tube_flood_quiet,
    _uboot_evade,
    _uboot_blow,
    _uboot_snorkel,
    _uboot_charge_rate,
    _uboot_absorber,
    _uboot_o2_candle,
    _uboot_trim_auto,
    _uboot_ballast,
    _uboot_dc_team,
    _uboot_bulkhead,
    _uboot_action_stations,
    _uboot_watch_change,
    _uboot_mast,
    _uboot_radio_send,
    _uboot_silent,
    _uboot_bottom,
    _uboot_scope_bearing,
    _uboot_scope_mark,
    _uboot_scope_fire,
    _uboot_lookout_call,
    _lookout_call,
    _uboot_esm_classify,
    _uboot_esm_plot,
    _UBOOT_ACTION_HANDLERS,
    _V2_ACTION_HANDLERS,
    _host_save,
    _host_load,
    _host_new_game,
    _host_instructor_environment,
    _host_instructor_event,
    _HOST_ACTION_HANDLERS)




def _age(now, timestamp):
    stamp = _number(timestamp)
    return now - stamp if stamp is not None and 0 <= stamp <= now else None


def _visual(game, label):
    """Lookout class/type of a visual report; None for every other source."""
    _level, code, type_key = lookout_id.decode(label)
    name = game.lookout_type_name(type_key) if code is not None else None
    return dict(visual_class=code, visual_type=None if name is None else name[:80])


def _fresh(now, timestamp, lifetime):
    age = _age(now, timestamp)
    return age is not None and age <= lifetime


def sonar_pcm_s16le(samples) -> bytes:
    """Deterministically limit one detached receiver block to mono s16le PCM."""
    source = np.asarray(samples)
    if source.ndim != 1 or source.size != 1024:
        raise ValueError("sonar audio requires exactly 1024 samples")
    limited = smooth_limit(source, knee=0.75, ceiling=0.98)
    return np.rint(limited.astype(np.float64) * 32767.0).astype("<i2").tobytes()


class CommanderBridge:
    def __init__(self):
        self._server = None
        self._allowed = True
        self._grant_lease = None
        self._identity = None
        self._session = secrets.token_urlsafe(24)
        self._epoch = 0
        self._revision = 0
        self._seq = 0
        self._event_seq = 0
        self._pending_seq = 0
        self._refs = {}
        self._esm_refs = {}
        self._esm_candidate_refs = {}
        self._asset_refs = {}
        self._buoy_labels = {}
        self._buoy_label_seq = 0
        self._direct_fire_refs = {}
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
        self._chart_publication = None
        self._simlog_fingerprint = None
        self._v2_simlog_seq = 0
        self._v2_simlog = {role: deque(maxlen=SIMLOG_ENTRIES_MAX)
                           for role in ROLES}
        # id(entry) -> (entry, compact JSON length); holding the entry keeps
        # its id from being reused while the size is cached.
        self._v2_simlog_bytes = {}
        # The crewed submarine's own contact refs: target_id -> (contact, ref, label).
        self._opfor_refs = {}
        self._uboot_audio_context = None
        self._uboot_audio_receiver_sequence = None
        self._uboot_audio_filter = None
        self._last_v2_states = None
        self._language = None
        self._last_publish = None
        self._slots = None
        self._slots_at = None
        self._audio_context = None
        self._audio_receiver_sequence = None
        self._audio_filter = None
        self._dirty = True
        self._status = dict(phase="blocked", connected=False,
                            commands_allowed=False, session=self._session,
                             epoch=0, revision=0, seq=0)

    @property
    def allowed(self) -> bool:
        return self._allowed

    @allowed.setter
    def allowed(self, value):
        self._main_thread()
        self._allowed = value is True
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
        for history in self._v2_simlog.values():
            history.clear()
        self._last_v2_states = None
        self._simlog_fingerprint = None
        if self._server is not None and hasattr(self._server, "invalidate_v2_commands"):
            self._server.invalidate_v2_commands("context_invalidated")
        self._dirty = True

    @staticmethod
    def _main_thread():
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError("CommanderBridge requires the main thread")

    @staticmethod
    def _phase(game):
        # The mission never pauses: local menus and overlays only own local
        # input, so the crew stays live behind them.
        if not game.running or game.game_over:
            return "ended"
        if game.in_menu or getattr(game, "main_menu", False):
            return "menu"
        if game.splash_active:
            return "blocked"
        return "live"

    def _event(self, kind, severity, key, authority=None):
        roles = {
            "damage": frozenset(("bridge", "damage")),
            "threat": frozenset(("bridge", "opz", "weapons")),
            "mission": frozenset(ROLE_NAMES),
        }.get(kind, frozenset())
        self._event_seq += 1
        self._events.append(dict(seq=self._event_seq, kind=kind,
                                 severity=severity, message=key,
                                 _roles=roles, _authority=authority))
        self._dirty = True

    def _proposal_status(self, status, *, navigation=False):
        if navigation:
            self._navigation_proposal = dict(self._navigation_proposal, status=status)
        else:
            self._proposal = dict(self._proposal, status=status)
        if status != "pending":
            self._revision += 1
            self._status["revision"] = self._revision
        authority = (self._navigation_lease if navigation else self._proposal_lease)
        self._event("proposal", "info", ("commander.nav." if navigation
                                        else "commander.event.proposal.") + status,
                    authority=authority)
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
        opz = game.opz_published_observations()
        opz_ids = {item.observation_id for item in opz}
        sonar = game.private_sonar_observations()
        observations = chain(opz, sonar, game.hfdf_bearings())
        # Bound both projection work and the registry, even with fake transports.
        for track in islice(observations, 512):
            if len(rows) == 256:
                break
            key, source = track.track_id, track.source
            if key in refs:
                continue
            lifetime = (300.0 if source == "HFDF" else
                        max(config.SONAR_CONTACT_LOST_S,
                            config.SONAR_PING_FIX_MAX_AGE_S)
                        if source.startswith("SONAR") else
                        config.RADAR_TRACK_STALE_S)
            if not _fresh(game.sim_t, track.last_seen, lifetime):
                continue
            associated = game._opz_source_bindings.get(key)
            if associated is not None and not hasattr(associated, "player_class"):
                associated = None
            if source == "HFDF":
                associated = self._contact(game, key, source)
            identity = (game._opz_source_bindings.get(key)
                        or game.opz_fusion.fusions.get(key) or track)
            previous = self._refs.get(key)
            if previous is not None and previous[0] is identity and previous[1] is associated:
                ref, label = previous[2:]
            else:
                if self._label_seq >= 2**53 - 1:
                    continue
                self._label_seq += 1
                ref, label = secrets.token_urlsafe(18), f"C{self._label_seq:03d}"
            # Strong references prevent Python id reuse between consecutive pumps.
            refs[key] = (identity, associated, ref, label)
            contact = (associated if associated is not None
                       and _fresh(game.sim_t, associated.last_seen,
                                  config.SONAR_CONTACT_LOST_S)
                       and game.sim_t - associated.last_seen < config.SONAR_CONTACT_LOST_S
                        else None)
            fix_contact = associated
            fix_age = _age(game.sim_t, track.position_seen)
            positioned = (source not in ("HFDF", "SONAR-BRG", "SONAR")
                          and _fresh(game.sim_t, track.position_seen, lifetime))
            if source.startswith("SONAR") and associated is not None:
                display_id = str(track.label)[:64]
            elif source == "HFDF":
                display_id = game.hfdf_display_id(track)
            elif key in opz_ids:
                display_id = str(track.label)[:64]
            else:
                display_id = label
            hf_mode = getattr(track, "propagation", None) if source == "HFDF" else None
            row = dict(ref=ref, label=label, _display_id=display_id,
                       # Measured HF carrier and propagation mode (radio room only).
                       _frequency_hz=(_number(getattr(track, "frequency_hz", None))
                                      if source == "HFDF" else None),
                       _propagation=hf_mode if hf_mode in ("GROUND", "SKY") else None,
                       domain={"AIS": "SURFACE", "SURFACE": "SURFACE",
                               "SUB": "SUBSURFACE", "TORP": "SUBSURFACE",
                               "FLG": "AIR", "ASM": "AIR"}.get(track.kind, "UNKNOWN"),
                        source=str(source)[:64], affiliation=game.opz_affiliation(key),
                        classification=getattr(track, "classification", None),
                        profile=(game.profile_name(associated.player_profile)[:128]
                                 if associated is not None
                                 and getattr(associated, "player_profile", None)
                                 else None),
                        bearing=_number(track.bearing),
                       range_nm=None,
                       x=_number(track.x) if positioned else None,
                       y=_number(track.y) if positioned else None,
                       depth_m=None, course=_number(track.course) if positioned else None,
                        speed_kn=_number(getattr(track, "speed_kn", None)) if positioned else None,
                        altitude_m=(_number(getattr(track, "altitude_m", None))
                                    if positioned else None),
                        observer_x=_number(getattr(track, "observer_x", None)),
                        observer_y=_number(getattr(track, "observer_y", None)),
                        released_to_opz=bool(getattr(track, "released_to_opz", False)),
                        quality=_number(track.display_quality(game.sim_t, lifetime)),
                       age_s=_age(game.sim_t, track.last_seen), fix_age_s=fix_age,
                       bearing_uncertainty_deg=_number(track.bearing_uncertainty_deg),
                         range_uncertainty_nm=None,
                         **_visual(game, getattr(track, "visual", None)),
                         fixes=[], can_classify=contact is not None,
                         can_propose=contact is not None, _opz=key in opz_ids)
            dip_report = source in ("SONAR-DIP-BRG", "SONAR-DIPPING")
            buoy_report = source.startswith("SONAR-BUOY-")
            if source.startswith("SONAR") and not dip_report and not buoy_report:
                # Never trust a mirrored sonar fix after its source evidence dies.
                for field in ("range_nm", "x", "y", "course", "fix_age_s"):
                    row[field] = None
                if source.startswith("SONAR-") and source not in (
                        "SONAR-DIP-BRG", "SONAR-DIPPING"):
                    row["source"] = "SONAR-BRG"
            if contact is not None:
                row["classification"] = (contact.player_class
                    if contact.player_class in config.PLAYER_CLASSES else None)
                if not dip_report and not buoy_report:
                    row["bearing"] = _number(contact.passive_bearing
                        if contact.passive_bearing is not None else contact.bearing)
                row["age_s"] = _age(game.sim_t, track.last_seen)
                row["quality"] = _number(max(contact.quality, contact.confidence))
                if not dip_report and not buoy_report:
                    row["bearing_uncertainty_deg"] = _number(contact.bearing_uncertainty_deg)
                    row["observer_x"] = _number(track.observer_x)
                    row["observer_y"] = _number(track.observer_y)
                    row["released_to_opz"] = bool(contact.released_to_opz)
                else:
                    row["released_to_opz"] = bool(contact.dip_released_to_opz)
            if fix_contact is not None and not dip_report and not buoy_report:
                row["fixes"] = [dict(
                    source=fix["source"], x=_number(fix["x"]), y=_number(fix["y"]),
                    measured_at=_number(fix["measured_at"]),
                    fixed_at=_number(fix["fixed_at"]),
                    measurement_age_s=_age(game.sim_t, fix["measured_at"]),
                    fix_age_s=_age(game.sim_t, fix["fixed_at"]),
                    uncertainty_nm=_number(fix["uncertainty_nm"]),
                    depth_m=_number(fix["depth_m"]),
                    depth_uncertainty_m=_number(fix["depth_uncertainty_m"]),
                    quality=_number(fix["quality"]))
                    for fix in fix_contact.active_fixes(game.sim_t)
                    if fix["source"] not in ("DIPPING", "SONOBUOY")]
            if contact is not None and not buoy_report:
                fix_lifetime = (config.SONAR_PING_FIX_MAX_AGE_S
                                if contact.range_source == "ping"
                                else config.SONAR_CONTACT_LOST_S)
                row["fix_age_s"] = _age(game.sim_t, contact.range_seen)
                if (contact.range_source in ("ping", "tma")
                        and row["fixes"]
                        and _fresh(game.sim_t, contact.range_seen, fix_lifetime)):
                    latest_fix = max(row["fixes"], key=lambda item: (
                        item["measured_at"], item["source"])) if row["fixes"] else None
                    observed_source = (latest_fix["source"] if latest_fix is not None
                                       else contact.range_source.upper())
                    row.update(source="SONAR-" + observed_source,
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
                observer_x = (row["observer_x"] if dip_report or buoy_report else game.ship.x)
                observer_y = (row["observer_y"] if dip_report or buoy_report else game.ship.y)
                dx, dy = row["x"] - observer_x, row["y"] - observer_y
                row["bearing"] = math.degrees(math.atan2(dx, -dy)) % 360.0
                row["range_nm"] = math.hypot(dx, dy)
            else:
                row["x"] = row["y"] = None
                if contact is None:
                    row["course"] = None
            rows.append(row)
            bindings[ref] = (key, source, contact, key in opz_ids, identity)
        self._refs = refs
        return rows, bindings

    def _annotations(self, game, rows, bindings):
        target = next((row["ref"] for row in rows
                       if bindings[row["ref"]][2] is not None
                       and bindings[row["ref"]][2] is game.target), None)
        public_fields = (
            "ref", "label", "_display_id", "classification", "affiliation", "domain", "source",
            "released_to_opz", "can_classify", "can_propose", "_opz",
        )
        fingerprint = (tuple(tuple(r[field] for field in public_fields)
                             for r in rows), target)
        if self._fingerprint is not None and fingerprint != self._fingerprint:
            self._revision += 1
            self._dirty = True
        self._fingerprint = fingerprint
        return target

    def _refresh_direct_fire_refs(self, game, rows, bindings):
        """Maintain role-scoped refs only for currently projected fire inputs."""
        current = {}
        asm_tracks = {id(track): track for track in game.asm_tracks()}
        sam_age = game._air_defense_loadout["sam"]["observation_max_age_s"]
        for row in rows:
            binding = bindings[row["ref"]]
            candidates = []
            if binding[2] is not None and binding[1].startswith("SONAR"):
                roles = (("helicopter",) if binding[1].startswith("SONAR-BUOY-")
                         else ("weapons", "helicopter"))
                candidates.extend((role, "sonar") for role in roles)
            track = asm_tracks.get(id(binding[4]))
            if (track is not None and row.get("_opz") and row["domain"] == "AIR"
                    and row["source"] != "FUSION" and row["x"] is not None
                    and row["y"] is not None and track.position_seen is not None
                    and 0 <= game.sim_t - track.position_seen <= sam_age):
                candidates.append(("opz", "asm"))
            for role, kind in candidates:
                key = (role, kind, binding[0])
                previous = self._direct_fire_refs.get(key)
                token = (previous[1] if previous is not None
                         and previous[0] is binding[4] else secrets.token_urlsafe(18))
                direct_binding = (binding[0], "DIRECT_" + kind.upper(),
                                  binding[2], binding[3], binding[4], role)
                current[key] = (binding[4], token, row["ref"], direct_binding)
        self._direct_fire_refs = current
        return {role: {entry[2]: entry[1] for key, entry in current.items()
                       if key[0] == role} for role in ("weapons", "helicopter", "opz")}

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
            self._chart_geography = dict(labels=[], airbases=[], depths=[], hazards=[])
            # Charted wrecks and underwater rocks are public chart content.
            charted = getattr(game.world, "charted_hazards", None)
            for hazard in islice(charted() if charted is not None else (), 64):
                self._chart_geography["hazards"].append(dict(
                    kind=hazard.kind, x=_number(hazard.x_nm), y=_number(hazard.y_nm),
                    top_depth_m=_number(hazard.top_depth_m),
                    length_m=_number(hazard.length_m)))
            for land in islice(game.world.coast.landmasses, 128):
                if getattr(land, "name", None) and hasattr(land, "centroid"):
                    x, y = land.centroid
                    self._chart_geography["labels"].append(dict(
                        name=str(land.name)[:96], x=_number(x), y=_number(y)))
            for base in islice(getattr(game.world.coast, "airbases", ()), 128):
                if _number(base.get("x")) is not None and _number(base.get("y")) is not None:
                    self._chart_geography["airbases"].append(dict(
                        name=str(base.get("name", ""))[:96], x=base["x"], y=base["y"]))
            bathymetry = getattr(game.world.coast, "_bathymetry", None)
            if bathymetry and type(bathymetry.get("values")) is list:
                grid = bathymetry["values"]
                if len(grid) <= 64 and all(type(row) is list and len(row) <= 64
                        and all(_number(value) is not None for value in row) for row in grid):
                    self._chart_geography["depths"] = [list(row) for row in grid]
        self._chart["revision"] = self._session

    @staticmethod
    def _apply_v2_action(game, action, params, bindings, role=None):
        handler = _V2_ACTION_HANDLERS.get(action)
        if handler is None:
            return False
        if action == "sonar_set_release":
            return handler(game, params, bindings, role)
        return handler(game, params, bindings)

    def _apply_proposal_v2(self, envelope, action, params, rows, bindings):
        if action == "propose_target":
            if self._proposal is not None and self._proposal["status"] == "pending":
                return "proposal_pending"
            binding = bindings.get(params["ref"])
            if binding is None:
                return "unknown_ref"
            if binding[2] is None:
                return "ineligible_track"
            row = next((item for item in rows if item["ref"] == params["ref"]), None)
            if row is None:
                return "unknown_ref"
            self._proposal = dict(ref=params["ref"], label=row["label"],
                                  status="pending")
            self._proposal_contact = binding[2]
            self._proposal_lease = envelope
            self._proposal_status("pending")
            return True
        if action == "clear_target_proposal":
            if (self._proposal is None or self._proposal_lease is None
                    or self._proposal_lease.session_digest != envelope.session_digest):
                return "unknown_ref"
            self._proposal_status("rejected")
            self._proposal = self._proposal_contact = self._proposal_lease = None
            return True
        if action == "propose_navigation":
            if (self._navigation_proposal is not None
                    and self._navigation_proposal["status"] == "pending"):
                return "proposal_pending"
            self._navigation_proposal = dict(course=params.get("course"),
                speed_kn=params.get("speed_kn"), status="pending")
            self._navigation_lease = envelope
            self.navigation_error = None
            self._proposal_status("pending", navigation=True)
            return True
        return False

    def _opfor_tracks(self, game, boat):
        """Rows and bindings of the crewed boat's own sonar contacts only."""
        rows, bindings, refs = [], {}, {}
        if boat is None:
            self._opfor_refs = refs
            return rows, bindings
        observer = boat.station.observer
        now = game.sim_t
        for target_id, contact in islice(sorted(boat.station.sonar.contacts.items()), 128):
            if not _fresh(now, contact.last_seen, config.SONAR_CONTACT_LOST_S):
                continue
            previous = self._opfor_refs.get(target_id)
            ref = (previous[1] if previous is not None and previous[0] is contact
                   else secrets.token_urlsafe(18))
            refs[target_id] = (contact, ref)
            fixes = [fix for fix in contact.active_fixes(now)
                     if fix["source"] in ("PING", "TMA")]
            source = contact.passive_source or "SONAR-BRG"
            bearing = (contact.passive_bearing if contact.passive_bearing is not None
                       else contact.bearing)
            x = y = range_nm = course = speed = depth = None
            fix_lifetime = (config.SONAR_PING_FIX_MAX_AGE_S
                            if contact.range_source == "ping"
                            else config.SONAR_CONTACT_LOST_S)
            if (contact.range_source in ("ping", "tma") and fixes
                    and _fresh(now, contact.range_seen, fix_lifetime)
                    and contact.observed_x is not None and contact.observed_y is not None):
                latest = max(fixes, key=lambda item: (item["measured_at"], item["source"]))
                source = "SONAR-" + latest["source"]
                x, y = contact.observed_x, contact.observed_y
                dx, dy = x - observer.x, y - observer.y
                bearing = math.degrees(math.atan2(dx, -dy)) % 360.0
                range_nm = math.hypot(dx, dy)
                if contact.range_source == "ping":
                    depth = contact.depth_est
            if (_fresh(now, contact.tma_seen, config.SONAR_CONTACT_LOST_S)
                    and contact.tma_quality >= config.TMA_RANGE_MIN_QUALITY
                    and x is not None):
                course, speed = contact.tma_course, contact.tma_speed
            row = dict(
                ref=ref, label=f"K{contact.id:02d}", domain="UNKNOWN",
                source=str(source)[:64], affiliation="UNKNOWN",
                classification=(contact.player_class
                                if contact.player_class in config.PLAYER_CLASSES
                                else None),
                profile=(game.profile_name(contact.player_profile)[:128]
                         if getattr(contact, "player_profile", None) else None),
                bearing=_number(bearing), range_nm=_number(range_nm),
                x=_number(x), y=_number(y), depth_m=_number(depth),
                course=_number(course), speed_kn=_number(speed), altitude_m=None,
                quality=_number(max(contact.quality, contact.confidence)),
                age_s=_age(now, contact.last_seen),
                fix_age_s=(_age(now, contact.range_seen) if x is not None else None),
                bearing_uncertainty_deg=_number(contact.bearing_uncertainty_deg),
                range_uncertainty_nm=(_number(contact.range_sigma_nm)
                                      if x is not None else None),
                observer_x=_number(contact.ship_observer_x),
                observer_y=_number(contact.ship_observer_y),
                released_to_opz=False, visual_class=None, visual_type=None,
                fixes=[dict(
                    source=fix["source"], x=_number(fix["x"]), y=_number(fix["y"]),
                    measured_at=_number(fix["measured_at"]),
                    fixed_at=_number(fix["fixed_at"]),
                    measurement_age_s=_age(now, fix["measured_at"]),
                    fix_age_s=_age(now, fix["fixed_at"]),
                    uncertainty_nm=_number(fix["uncertainty_nm"]),
                    depth_m=_number(fix["depth_m"]),
                    depth_uncertainty_m=_number(fix["depth_uncertainty_m"]),
                    quality=_number(fix["quality"])) for fix in fixes],
                can_classify=True, can_propose=False, _opz=False)
            rows.append(row)
            bindings[ref] = (f"U-{target_id}", row["source"], contact, False, contact)
        self._opfor_refs = refs
        return rows, bindings

    def _sync_opfor(self, game, server, phase):
        """Bind the crewed submarine while a crew holds one of its roles."""
        local = getattr(game, "local_side", "frigate") == "uboot"
        leased = False
        if hasattr(server, "station_leased"):
            # Browsers may crew the boat's stations beside the uConsole; the
            # uConsole then leaves a browser-held station alone.
            leased = any(server.station_leased(role) for role in OPFOR_ROLES)
        if phase == "live" and (leased or local):
            game.claim_opfor_sub()
        elif (game.opfor is not None and not local
              and getattr(game, "_opfor_hold_s", 0.0) <= 0.0):
            # A boat restored by a load keeps its crew binding for the hold
            # so a returning crew resumes its orders; then the AI takes over.
            game.release_opfor_sub()
            self._opfor_refs = {}

    def _apply_opfor_action(self, game, action, params, role):
        spec = V2_ACTION_REGISTRY.get(action)
        if spec is None or role not in spec.stations:
            # Defense in depth: the transport already admits only allowlisted
            # actions per role; a submarine role never reaches frigate actions.
            return False
        boat = game.opfor
        if boat is None:
            return "not_ready"
        _rows, bindings = self._opfor_tracks(game, boat)
        if role != "uboot_sonar" and action in ("uboot_wire_steer", "uboot_wire_cut"):
            torpedo = next((asset for (namespace, _key), (asset, ref)
                            in self._asset_refs.items()
                            if namespace == "uboot_torpedo" and ref == params["ref"]), None)
            if torpedo is None or torpedo.state != "RUN":
                return "unknown_ref"
            if action == "uboot_wire_cut":
                return opfor.wire_cut(boat, torpedo)
            return opfor.wire_steer(boat, torpedo, params["bearing"], params["range_nm"])
        if role != "uboot_sonar" and action.startswith("plot_"):
            # The boat's crew draws on the boat's own plot, never the frigate's.
            return _V2_ACTION_HANDLERS[action](game, params, bindings, layer=boat.plot)
        if role == "uboot" and action in ("sonar_active_ping", "sonar_measure_bt"):
            with game.sonar_perspective(boat.station):
                return _V2_ACTION_HANDLERS[action](game, params, bindings)
        if role in UBOOT_COMMAND_ROLES or role == "uboot_lookout":
            handler = _UBOOT_ACTION_HANDLERS.get(action)
            return False if handler is None else handler(game, boat, params, bindings)
        handler = _V2_ACTION_HANDLERS.get(action)
        if handler is None or action == "sonar_set_release":
            return False
        with game.sonar_perspective(boat.station):
            return handler(game, params, bindings)

    def _commands_v2(self, game, server, now, phase, *, realtime=False):
        if not hasattr(server, "drain_commands_v2"):
            return False
        drained = False
        bridge_course = None
        identity = (id(game.world), id(game.sonar))
        envelopes = server.drain_commands_v2()
        # One timestamp for the detached batch keeps freshness independent of
        # station ordering and the cost of earlier commands in this frame.
        apply_now = time.monotonic() if realtime and envelopes else now
        for envelope in envelopes:
            drained = True
            # HTTP workers may enqueue after this frame's projection clock was
            # sampled. Recheck age after detaching the batch, while explicit
            # test clocks remain reproducible.
            if (id(game.world), id(game.sonar)) != identity:
                # An earlier command in this frame replaced the world. Anything
                # prepared for the old world fails closed, never on the new one.
                server.apply_command_v2(
                    envelope, now=apply_now, phase="blocked", world_session=self._session,
                    world_epoch=self._epoch, resource_revision=self._revision,
                    apply=lambda action, params: False)
                continue
            if envelope.role in OPFOR_ROLES or envelope.role == "uboot_lookout":
                server.apply_command_v2(
                    envelope, now=apply_now, phase=phase, world_session=self._session,
                    world_epoch=self._epoch, resource_revision=self._revision,
                    apply=lambda action, params, role=envelope.role: (
                        self._apply_opfor_action(game, action, params, role)))
                continue
            if envelope.role == HOST_ROLE:
                server.apply_command_v2(
                    envelope, now=apply_now, phase=phase, world_session=self._session,
                    world_epoch=self._epoch, resource_revision=self._revision,
                    apply=lambda action, params: (
                        _HOST_ACTION_HANDLERS[action](game, params)
                        if action in _HOST_ACTION_HANDLERS else False))
                phase = self._phase(game)  # load/new game changes what may follow
                self._slots_at = None  # a save may have changed the slot list
                self._dirty = True  # publish the new host view immediately
                continue
            rows, bindings = self._tracks(game)
            self._refresh_direct_fire_refs(game, rows, bindings)
            bindings.update((entry[1], entry[3])
                            for key, entry in self._direct_fire_refs.items()
                            if key[0] == envelope.role)
            for track_key, (track, ref) in self._esm_refs.items():
                bindings[ref] = (track_key, "ELOKA", track, False, track)
            for (track_key, emitter_key), (track, ref) in self._esm_candidate_refs.items():
                bindings[ref] = (emitter_key, "ELOKA_CANDIDATE", track,
                                 False, track_key)
            def apply_action(action, params, bindings=bindings):
                nonlocal bridge_course
                if action in ("propose_target", "clear_target_proposal",
                              "propose_navigation"):
                    result = self._apply_proposal_v2(
                        envelope, action, params, rows, bindings)
                else:
                    result = self._apply_v2_action(
                        game, action, params, bindings, envelope.role)
                if action == "bridge_set_course" and result in (True, "ok"):
                    bridge_course = params["course"]
                return result

            server.apply_command_v2(
                envelope, now=apply_now, phase=phase, world_session=self._session,
                world_epoch=self._epoch, resource_revision=self._revision,
                apply=apply_action)
        if bridge_course is not None:
            # Preserve station/client/FIFO application while resolving the one
            # shared setpoint with explicit Bridge authority.
            game.ship.target_course = bridge_course
        return drained

    def _settle_gate(self, game, server, phase):
        """Advance the epoch and drop queued input when the input owner changed."""
        # Only world lifecycle changes invalidate queued input; local overlays
        # never stop the simulation, so they do not either.
        gate = (phase, bool(game.splash_active), bool(game.in_menu), bool(game.main_menu),
                bool(game.running), bool(game.game_over), id(server))
        if gate != self._gate:
            if self._gate is not None:
                self._epoch += 1
                if hasattr(server, "invalidate_v2_commands"):
                    server.invalidate_v2_commands("context_invalidated")
                self._v2_simlog_seq = (game.simlog[-1]["seq"]
                                       if game.simlog else self._v2_simlog_seq)
                for history in self._v2_simlog.values():
                    history.clear()
                self._last_v2_states = None
                self._simlog_fingerprint = None
            self._gate = gate
            self._dirty = True

    def pump(self, game, server, now=None):
        """Project and drain at most four commands; publish at 2 Hz/no catchup."""
        self._main_thread()
        realtime = now is None
        now = time.monotonic() if now is None else now
        if _number(now) is None or now < 0:
            raise ValueError("now must be finite monotonic seconds")
        if self._server is not None and self._server is not server:
            self.allowed = False
        self._server = server
        if hasattr(server, "set_host_language"):
            server.set_host_language(game.preferences.language)
        identity = (id(game.world), id(game.sonar))
        world_replaced = self._identity is not None and identity != self._identity
        if identity != self._identity:
            if self._identity is not None:
                game.opz_fusion.clear()
                game.opz_selected_track_id = None
                self.allowed = False
                if getattr(server, "web_auth", None) is not None:
                    server.web_rebase()
                elif getattr(server, "solo_mode", False) is True:
                    # The solo browser is the console: keep its session and
                    # re-lease every station under fresh generations.
                    server.solo_rebase()
                else:
                    server.revoke()
                self._session = secrets.token_urlsafe(24)
                self._epoch += 1
                self._revision = self._seq = 0
                self._refs.clear()
                self._esm_refs.clear()
                self._esm_candidate_refs.clear()
                self._asset_refs.clear()
                self._buoy_labels.clear()
                self._buoy_label_seq = 0
                self._direct_fire_refs.clear()
                self._label_seq = 0
                self._ids.clear()
                self._results.clear()
                self._events.clear()
                self._proposal = self._proposal_contact = self._proposal_lease = None
                self._navigation_proposal = self._navigation_lease = None
                self._v2_simlog_seq = 0
                for history in self._v2_simlog.values():
                    history.clear()
                self._last_v2_states = None
                self._simlog_fingerprint = None
                self.navigation_error = None
                self._fingerprint = self._damage = self._threats = None
                self._mission_state = None
                self._mission_warned.clear()
                self._gate = None
            self._identity = identity
            self._dirty = True
        phase = self._phase(game)
        connected = bool(server.connected)
        self._settle_gate(game, server, phase)
        self._sync_opfor(game, server, phase)
        self._publish_sonar_audio(game, server, phase)
        self._publish_helicopter_audio(game, server, phase)
        self._publish_uboot_audio(game, server, phase)
        self._status.update(phase=phase, connected=connected,
                            commands_allowed=self.allowed is True and connected and phase == "live")
        redacted = game.in_menu or game.main_menu or game.splash_active
        self._publish_role_simlog(server, game, redacted)
        if redacted:
            self._refs.clear()
            self._esm_refs.clear()
            self._esm_candidate_refs.clear()
            self._direct_fire_refs.clear()
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
            rows, bindings, direct_fire_refs = [], {}, {}
        else:
            rows, bindings = self._tracks(game)
            direct_fire_refs = self._refresh_direct_fire_refs(game, rows, bindings)
        target = self._annotations(game, rows, bindings)
        if self._proposal is not None and self._proposal["status"] == "pending":
            bound = bindings.get(self._proposal["ref"])
            if (not connected or self.allowed is not True or bound is None
                    or not server.authority_current_v2(self._proposal_lease)
                    or bound[2] is not self._proposal_contact):
                self._proposal_status("expired")
        if (self._navigation_proposal is not None
                and self._navigation_proposal["status"] == "pending"
                and (not connected or not self.allowed
                     or not server.authority_current_v2(self._navigation_lease))):
            self._proposal_status("expired", navigation=True)
        drained = self._commands_v2(game, server, now, phase, realtime=realtime)
        if (id(game.world), id(game.sonar)) != self._identity:
            # A host command replaced the world: never publish it under the old
            # session. The next pump rebases (solo) before anything is shown.
            self._dirty = True
            return
        if drained:
            # A host command may have loaded or started a world: settle that change
            # in this very frame, so the browser never sees the new state while the
            # bridge still owes an epoch bump (which would eat its next command).
            phase = self._phase(game)
            self._settle_gate(game, server, phase)
            self._status.update(phase=phase, epoch=self._epoch, commands_allowed=(
                self.allowed is True and connected and phase == "live"))
        if drained and not redacted:
            rows, bindings = self._tracks(game)
            direct_fire_refs = self._refresh_direct_fire_refs(game, rows, bindings)
            target = self._annotations(game, rows, bindings)
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
            threats = {r["ref"] for r in rows
                       if r["source"] == "HOJ" or r["affiliation"] == "HOSTILE"}
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
        if not redacted:
            self._build_chart(game)
        self._seq += 1
        self._status["seq"] = self._seq
        if redacted or world_replaced:
            unassigned = redacted_state(self._status)
            redacted_v2_chart = redacted_chart(self._status)
            states = {role: deepcopy(unassigned) for role in (None, *ROLES)}
            charts = {role: deepcopy(redacted_v2_chart) for role in (None, *ROLES)}
        else:
            current_esm = {}
            for track in game.eloka_tracks():
                previous = self._esm_refs.get(track.track_key)
                ref = (previous[1] if previous is not None and previous[0] is track
                       else secrets.token_urlsafe(18))
                current_esm[track.track_key] = (track, ref)
            self._esm_refs = current_esm
            current_candidates = {}
            for track in game.eloka_tracks():
                for candidate in game.eloka_display_candidates(track)[:32]:
                    key = (track.track_key, candidate.emitter_key)
                    previous = self._esm_candidate_refs.get(key)
                    ref = (previous[1] if previous is not None
                           and previous[0] is track else secrets.token_urlsafe(18))
                    current_candidates[key] = (track, ref)
            self._esm_candidate_refs = current_candidates
            current_assets = {}
            current_buoy_labels = {}
            bounded_assets = (
                ("torpedo", sorted(game.torpedoes,
                                   key=lambda item: item.idx)[:64]),
                ("asroc", sorted(game.asrocs,
                                 key=lambda item: item.seq)[:32]),
                ("buoy", sorted(game.buoys,
                                key=lambda item: item.seq)[:64]),
                ("nixie", sorted(game.nixies,
                                 key=lambda item: item.seq)[:8]),
                # The crewed boat's own torpedoes (its commanded weapons).
                ("uboot_torpedo", [] if game.opfor is None else sorted(
                    (item for item in game.enemy_torpedoes
                     if item.launch_platform_id == game.opfor.sub.id
                     and item.state == "RUN"), key=lambda item: item.id)[:16]),
            )
            for namespace, assets in bounded_assets:
                for asset in assets:
                    key = (namespace, id(asset))
                    previous = self._asset_refs.get(key)
                    ref = (previous[1] if previous is not None
                           and previous[0] is asset else secrets.token_urlsafe(18))
                    current_assets[key] = (asset, ref)
                    if namespace == "buoy":
                        previous_label = self._buoy_labels.get(key)
                        if previous_label is not None and previous_label[0] is asset:
                            label = previous_label[1]
                        else:
                            self._buoy_label_seq += 1
                            label = f"SB{self._buoy_label_seq:02d}"
                        current_buoy_labels[key] = (asset, label)
            self._asset_refs = current_assets
            self._buoy_labels = current_buoy_labels
            ref_by_track = {key: binding[2] for key, binding in self._refs.items()}
            focus_ref = next((binding[2] for binding in self._refs.values()
                              if binding[1] is game.selected_contact), None)
            sonar_refs = {binding[2]: binding[1] for binding in self._refs.values()
                          if binding[1] is not None}
            states = {None: redacted_state(self._status)}
            states.update(build_role_states(
                game, self._status, rows, target, focus_ref, ref_by_track,
                {key: value[1] for key, value in current_esm.items()},
                {key: value[1] for key, value in current_assets.items()},
                {key: value[1] for key, value in current_buoy_labels.items()},
                {key: value[1] for key, value in current_candidates.items()},
                sonar_refs, direct_fire_refs))
            boat = game.opfor
            opfor_rows, opfor_bindings = self._opfor_tracks(game, boat)
            opfor_sonar_refs = {row["ref"]: opfor_bindings[row["ref"]][2]
                                for row in opfor_rows}
            opfor_target = opfor_focus = None
            if boat is not None:
                opfor_target = next((row["ref"] for row in opfor_rows
                                     if opfor_sonar_refs[row["ref"]] is boat.station.target),
                                    None)
                opfor_focus = next((row["ref"] for row in opfor_rows
                                    if opfor_sonar_refs[row["ref"]]
                                    is boat.station.selected_contact), None)
            opfor_states = build_opfor_states(
                game, self._status, boat, opfor_rows, opfor_target, opfor_focus,
                opfor_sonar_refs, {key: value[1] for key, value in current_assets.items()})
            for role in OPFOR_ROLES:
                states[role] = opfor_states.get(role, deepcopy(states[None]))
            states.update(build_lookout_states(game, self._status, boat, states[None]))
            # The known chart is identical for every role and constant for a
            # world/session/language, so build it once and share one object.
            chart_key = (self._chart_world, self._session, self._language)
            if self._chart_publication is None or self._chart_publication[0] != chart_key:
                known_v2_chart = known_chart(self._status, dict(
                    self._chart, disclaimer=game.tr(self._chart["disclaimer"])))
                known_v2_chart["geography"] = deepcopy(self._chart_geography)
                self._chart_publication = (chart_key, known_v2_chart)
            known_v2_chart = self._chart_publication[1]
            charts = {None: redacted_chart(self._status)}
            charts.update({role: known_v2_chart for role in ROLE_NAMES})
            # Without a crewed boat its roles stay redacted (state and chart).
            charts.update({role: (known_v2_chart if game.opfor is not None
                                  else deepcopy(charts[None]))
                           for role in (*OPFOR_ROLES, "uboot_lookout")})
            charts["lookout"] = known_v2_chart
        server.publish_v2(states, charts)
        if ((getattr(server, "solo_mode", False) is True
             or getattr(server, "web_auth", None) is not None)
                and hasattr(server, "publish_host_v2")):
            server.publish_host_v2(self._host_view(game, phase, now))
        server.publish_proposals_v2(
            world_session=self._session, world_epoch=self._epoch,
            target_authority=self._proposal_lease, target=self.proposal,
            navigation_authority=self._navigation_lease,
            navigation=self.navigation_proposal)
        self._publish_events_v2(server, game)
        # Fresh objects per publication, encoded above and never mutated
        # afterwards; _publish_role_simlog copies the ones it appends.
        self._last_v2_states = (None if redacted or world_replaced else
                                {role: states[role] for role in ROLES})
        self._last_publish = now
        self._dirty = False

    @staticmethod
    def _slot_rows():
        """Metadata only (stat, never parse): which save slots hold a file."""
        rows = []
        for slot in range(1, config.SAVE_SLOTS + 1):
            path = os.path.join(config.SAVE_DIR, f"slot{slot}.json")
            try:
                info = os.stat(path)
            except OSError:
                rows.append(dict(slot=slot, saved=False, modified=None))
            else:
                rows.append(dict(slot=slot, saved=info.st_size > 0,
                                 modified=int(info.st_mtime)))
        return rows

    def _host_view(self, game, phase, now):
        """Detached solo host view: clock, phase, scenario choices and save slots."""
        if self._slots is None or self._slots_at is None or now - self._slots_at >= 2.0:
            self._slots = self._slot_rows()
            self._slots_at = now
        return dict(
            protocol=2, session=self._session, epoch=self._epoch, phase=phase,
            world_mode=game.world_mode, scenario=game.scenario_key,
            difficulty=dict(game.menu_difficulty),
            scenarios=[dict(key=key, fixed=config.SCENARIOS[key]["difficulty"] is not None)
                       for key in config.SCENARIO_ORDER],
            difficulty_fields=[
                dict(name=name, kind=("int" if kind is int else "float"),
                     min=low, max=high, step=step, default=default)
                for name, (kind, low, high, step, default)
                in config.DIFFICULTY_FIELDS.items()],
            slots=[dict(row) for row in self._slots])

    def _publish_sonar_audio(self, game, server, phase):
        """Copy only complete mixed receiver blocks on the main thread."""
        receiver = game.sonar.receiver
        eligible = (phase == "live" and not game.damage.station_down("sonar")
                    and hasattr(server, "prepare_sonar_audio")
                    and hasattr(server, "publish_sonar_audio"))
        if not eligible:
            if hasattr(server, "clear_sonar_audio"):
                server.clear_sonar_audio()
            self._audio_context = None
            self._audio_receiver_sequence = receiver.sequence
            self._audio_filter = None
            return
        generation = server.prepare_sonar_audio(
            world_session=self._session, world_epoch=self._epoch)
        context = (id(receiver), self._session, self._epoch, generation)
        if generation is None:
            self._audio_context = None
            self._audio_receiver_sequence = receiver.sequence
            self._audio_filter = None
            return
        if context != self._audio_context:
            self._audio_context = context
            self._audio_receiver_sequence = receiver.sequence
            self._audio_filter = SonarSystem(seed=0, acoustic_profiles=())
            return
        for sequence, samples in receiver.blocks_since(self._audio_receiver_sequence):
            if sequence != self._audio_receiver_sequence + 1:
                # The receiver restarted (retune): the browser must crossfade.
                self._audio_filter.reset_audition_audio()
                if hasattr(server, "mark_audio_discontinuity"):
                    server.mark_audio_discontinuity("sonar")
            self._audio_filter.audition_mode = game.sonar.audition_mode
            self._audio_filter.band_low_hz = game.sonar.band_low_hz
            self._audio_filter.band_high_hz = game.sonar.band_high_hz
            self._audio_filter.notch_enabled = game.sonar.notch_enabled
            self._audio_filter._own_line_hz = game.sonar._own_line_hz
            self._audio_filter.gain_db = game.sonar.gain_db
            pcm = sonar_pcm_s16le(
                self._audio_filter.listening_samples(samples, block_id=sequence))
            server.publish_sonar_audio(
                pcm, world_session=self._session, world_epoch=self._epoch,
                station_generation=generation)
            self._audio_receiver_sequence = sequence

    def _publish_uboot_audio(self, game, server, phase):
        """The crewed boat's own hull-array receiver, for its sonar room only."""
        boat = game.opfor
        eligible = (phase == "live" and boat is not None and not boat.sonar_down()
                    and hasattr(server, "prepare_uboot_audio")
                    and hasattr(server, "publish_uboot_audio"))
        if not eligible:
            if hasattr(server, "clear_uboot_audio"):
                server.clear_uboot_audio()
            self._uboot_audio_context = None
            self._uboot_audio_receiver_sequence = None
            self._uboot_audio_filter = None
            return
        sonar = boat.station.sonar
        receiver = sonar.receiver
        generation = server.prepare_uboot_audio(
            world_session=self._session, world_epoch=self._epoch)
        context = (id(receiver), self._session, self._epoch, generation)
        if generation is None or context != self._uboot_audio_context:
            self._uboot_audio_context = context if generation is not None else None
            self._uboot_audio_receiver_sequence = receiver.sequence
            self._uboot_audio_filter = (SonarSystem(seed=0, acoustic_profiles=())
                                        if generation is not None else None)
            return
        for sequence, samples in receiver.blocks_since(self._uboot_audio_receiver_sequence):
            audition = self._uboot_audio_filter
            if sequence != self._uboot_audio_receiver_sequence + 1:
                audition.reset_audition_audio()
                if hasattr(server, "mark_audio_discontinuity"):
                    server.mark_audio_discontinuity("uboot_sonar")
            audition.audition_mode = sonar.audition_mode
            audition.band_low_hz = sonar.band_low_hz
            audition.band_high_hz = sonar.band_high_hz
            audition.notch_enabled = sonar.notch_enabled
            audition._own_line_hz = sonar._own_line_hz
            audition.gain_db = sonar.gain_db
            server.publish_uboot_audio(
                sonar_pcm_s16le(audition.listening_samples(samples, block_id=sequence)),
                world_session=self._session, world_epoch=self._epoch,
                station_generation=generation)
            self._uboot_audio_receiver_sequence = sequence

    def _publish_helicopter_audio(self, game, server, phase):
        receiver = game.helo_receiver
        eligible = (phase == "live" and not game.damage.station_down("sonar")
                    and game.helicopter_audio_ready()
                    and hasattr(server, "prepare_helicopter_audio")
                    and hasattr(server, "publish_helicopter_audio"))
        if not eligible:
            if hasattr(server, "clear_helicopter_audio"):
                server.clear_helicopter_audio()
            self._helicopter_audio_context = None
            self._helicopter_audio_receiver_sequence = receiver.sequence
            self._helicopter_audio_filter = None
            return
        generation = server.prepare_helicopter_audio(
            world_session=self._session, world_epoch=self._epoch)
        context = (id(receiver), game.helo_listen_source, self._session,
                   self._epoch, generation)
        if generation is None or context != getattr(self, "_helicopter_audio_context", None):
            if generation is not None and hasattr(server, "clear_helicopter_audio"):
                server.clear_helicopter_audio()
                generation = server.prepare_helicopter_audio(
                    world_session=self._session, world_epoch=self._epoch)
                context = (id(receiver), game.helo_listen_source, self._session,
                           self._epoch, generation)
            self._helicopter_audio_context = context if generation is not None else None
            self._helicopter_audio_receiver_sequence = receiver.sequence
            self._helicopter_audio_filter = (SonarSystem(seed=0, acoustic_profiles=())
                                             if generation is not None else None)
            return
        for sequence, samples in receiver.blocks_since(
                self._helicopter_audio_receiver_sequence):
            audition = self._helicopter_audio_filter
            if sequence != self._helicopter_audio_receiver_sequence + 1:
                audition.reset_audition_audio()
                if hasattr(server, "mark_audio_discontinuity"):
                    server.mark_audio_discontinuity("helicopter")
            controls = game.helo_audition
            audition.audition_mode = controls.audition_mode
            audition.band_low_hz = controls.band_low_hz
            audition.band_high_hz = controls.band_high_hz
            audition.notch_enabled = controls.notch_enabled
            audition.gain_db = controls.gain_db
            server.publish_helicopter_audio(
                sonar_pcm_s16le(audition.listening_samples(samples, block_id=sequence)),
                world_session=self._session,
                world_epoch=self._epoch, station_generation=generation)
            self._helicopter_audio_receiver_sequence = sequence

    def _publish_role_simlog(self, server, game, redacted) -> None:
        """Publish host-granted diagnostics with role context and full truth."""
        source = list(game.simlog)
        latest = source[-1]["seq"] if source else self._v2_simlog_seq
        enabled = bool(game.preferences.simlog) and not redacted
        if not enabled:
            for history in self._v2_simlog.values():
                history.clear()
            self._v2_simlog_seq = latest
        elif self._last_v2_states is None:
            self._v2_simlog_seq = latest
        elif self._last_v2_states is not None:
            for row in source:
                if row["seq"] <= self._v2_simlog_seq:
                    continue
                # One detached truth per row, shared read-only by every role's
                # entry (it is only ever serialized).
                truth = deepcopy(row.get("data") or game._simlog_state_data())
                for role in ROLES:
                    if self._last_v2_states[role].get("role") != role:
                        # A redacted role (no crewed submarine) has no history.
                        continue
                    self._v2_simlog[role].append(dict(
                        seq=row["seq"], t=row["t"], stamp=row["stamp"],
                        state=deepcopy(self._last_v2_states[role]),
                        truth=truth))
                self._v2_simlog_seq = row["seq"]
        entries = {role: list(history) for role, history in self._v2_simlog.items()}
        cache, kept = self._v2_simlog_bytes, {}
        for role, rows in entries.items():
            # Compact JSON of the published document is its empty envelope plus
            # every entry plus one comma between entries, so each entry is
            # encoded once and trimming never re-encodes the whole history.
            sizes = []
            for row in rows:
                cached = cache.get(id(row))
                if cached is None or cached[0] is not row:
                    cached = (row, len(_json_bytes(row)))
                sizes.append(cached)
            total = len(_json_bytes({
                "protocol": 2, "session": self._session, "epoch": self._epoch,
                "role": role, "entries": []}))
            total += sum(size for _, size in sizes) + max(len(rows) - 1, 0)
            trimmed = 0
            while trimmed < len(rows) and total > SIMLOG_MAX_BYTES:
                total -= sizes[trimmed][1] + (1 if trimmed < len(rows) - 1 else 0)
                trimmed += 1
            if trimmed:
                del rows[:trimmed]
                self._v2_simlog[role] = deque(rows, maxlen=SIMLOG_ENTRIES_MAX)
            kept.update((id(row), size) for row, size in zip(rows, sizes[trimmed:]))
        self._v2_simlog_bytes = kept
        fingerprint = (self._session, self._epoch, enabled,
                       tuple((role, len(rows), rows[-1]["seq"] if rows else 0)
                             for role, rows in entries.items()))
        if fingerprint != self._simlog_fingerprint:
            server.publish_simlog_v2(
                world_session=self._session, world_epoch=self._epoch,
                entries_by_role=entries)
            self._simlog_fingerprint = fingerprint

    def _publish_events_v2(self, server, game):
        public = {role: [] for role in ROLES}
        private = []
        for stored in self._events:
            row = {key: stored[key] for key in ("seq", "kind", "severity")}
            row["message"] = game.tr(stored["message"])
            authority = stored["_authority"]
            if authority is not None:
                private.append((authority, row))
            else:
                for role in stored["_roles"]:
                    public[role].append(dict(row))
        server.publish_events_v2(
            world_session=self._session, world_epoch=self._epoch,
            latest_seq=self._event_seq, events_by_role=public,
            private_events=private)

    def _decide(self, game, accepted):
        self._main_thread()
        if (self._identity != (id(game.world), id(game.sonar))
                or self._phase(game) != "live"
                or self.allowed is not True or self._server is None
                or not self._server.connected
                or self._proposal is None or self._proposal["status"] != "pending"):
            return False
        rows, bindings = self._tracks(game)
        bound = bindings.get(self._proposal["ref"])
        if (not self._server.authority_current_v2(self._proposal_lease)
                or bound is None
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
                or self._phase(game) != "live"
                or not self.allowed or self._server is None or not self._server.connected
                or proposal is None or proposal["status"] != "pending"):
            return False
        if not self._server.authority_current_v2(self._navigation_lease):
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
                game.ship.astern = False
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
