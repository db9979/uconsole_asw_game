"""Save v16 persistence of the game: canonical document, strict validation,
transactional candidate restore and the five slots (``Game`` mixin).

Every method here is a verbatim move from ``game.py`` (plan 1.3, phase 2,
step 1); the persistence contract is unchanged."""

from collections import deque
import copy
import json
import math
import os
import weakref

import pygame

from src.audio.receiver import AcousticReceiver
from src.core import config
from src.core.plot import PlotLayer
from src.core.autocrew import AutocrewController
from src.core.i18n import message
from src.core.mission import Mission
from src.core.station import Station
from src.core import opfor
from src.core.version import SAVE_SCHEMA, SAVE_VERSION
from src.sensors.ais import AISReceiver
from src.sonar import analysis_tools
from src.ship import damage as damage_physics
from src.core.save_schema import SAVE_ROOT_FIELDS
from src.data import fingerprint as fingerprint_mod
from src.enemies.animal import Animal
from src.enemies.decoy import Decoy
from src.enemies.sub import Sub
from src.enemies.ballast import BoatBallast
from src.enemies.damage_control import BoatDamageControl
from src.core.tasking import TaskBoard
from src.core.incidents import IncidentBoard
from src.core.hq_reports import HqReports
from src.core.crew import CrewState
from src.air.mpa import PatrolAircraft
from src.enemies.endurance import SubmarineEndurance
from src.enemies.surface import SurfaceShip
from src.sensors.tracks import TrackPicture
from src.sensors.esm import ESM_STATE_VERSION, ECMJammer, ESMPicture
from src.sensors.platform import PlatformSensorSuite
from src.ship.damage import DamageModel
from src.ship.ship import Ship
from src.sonar.sonar import Contact, SonarSystem, TowState, beam_width_deg
from src.sonar.tma import BearingPoint, BearingTrack
from src.ui import layout
from src.ui.stations_view import opz_ppi_rect
from src.air.asm import ASM, ESSM
from src.air import chaff as chaff_physics
from src.air.helicopter import Helicopter
from src.air.flights import Flight, FlightManager
from src.air.raid import RaidPhase, Raider
from src.air.sonobuoy import Sonobuoy
from src.world.world import World
from src.world.coastline import Coastline
from src.world.grounding import GroundingContact, HullSpec
from src.weapons.depth_charge import DepthCharge
from src.weapons.torpedo import EnemyTorpedo, Torpedo
from src.weapons.asw import (
    ASROC,
    ASW_STATE_VERSION,
    ConsumableStore,
    TowedAcousticDecoy,
    WeaponBattery)
from src.weapons.air_defense import AIR_DEFENSE_STATE_VERSION

from src.core.limits import MAX_AIR_PICTURE_TRACKS
from src.ship.route import Route


MAX_SAVE_DOCUMENT_BYTES = 64 * 1024 * 1024


def _read_save_document(path):
    if os.path.getsize(path) > MAX_SAVE_DOCUMENT_BYTES:
        raise ValueError("save document too large")
    with open(path, "rb") as stream:
        raw = stream.read(MAX_SAVE_DOCUMENT_BYTES + 1)
    if len(raw) > MAX_SAVE_DOCUMENT_BYTES:
        raise ValueError("save document too large")
    return json.loads(raw.decode("utf-8"))


# ``_valid_difficulty_dict`` and the comparison helpers are re-exported for
# ``game.py`` and the tests that import them from there.
from src.core.save_validate import (  # noqa: F401
    _same_save_value, _same_save_value_strict, _valid_crew_block,
    _valid_difficulty_dict, catalog_for_save, valid_save_document)


class SaveMixin:
    """Save/load half of ``Game``: ``save_state``/``_restore_state`` and the strict
    document validator, plus the slot helpers."""

    @staticmethod
    def _rng_state(r) -> list:
        st = r.getstate()
        return [st[0], list(st[1]), st[2]]

    def _crew_state(self, entity_ids):
        """Save v15 ``crew``: the crewed boat's binding, or None."""
        boat = self._opfor
        if boat is None or boat.sub not in self.subs or not boat.sub.manual:
            return None
        source_ids = {source.id for source in boat.sonar_targets(self)}
        with self.sonar_perspective(boat.station):
            station = dict(
                mode=self.sonar_mode,
                controls=self._sonar_controls_state(),
                sonar=self._sonar_system_state(set(entity_ids) | source_ids),
                selected_contact_id=(self.selected_contact.id
                                     if self.selected_contact else None),
                target_id=self.target.target_id if self.target else None,
                rng=self._rng_state(self.sonar.rng))
        return dict(boat.to_save(), sub_id=boat.sub_id,
                    hold_s=self._opfor_hold_s, station=station)

    def _restore_crew(self, crew, by_id) -> None:
        """Rebind the crewed boat of a validated save (after every entity)."""
        self._opfor = None
        self._opfor_hold_s = 0.0
        if crew is None:
            return
        sub = next(s for s in self.subs if s.id == crew["sub_id"])
        boat = opfor.CrewedBoat(sub, self.runtime_catalog)
        boat.restore(crew)
        station = crew["station"]
        targets = {source.id: source for source in boat.sonar_targets(self)}
        with self.sonar_perspective(boat.station):
            self.sonar_mode = station["mode"]
            self._restore_sonar_controls(station["controls"])
            self._restore_sonar_system(station["sonar"], {**by_id, **targets},
                                       observer=boat.station.observer)
            self._restore_rng(self.sonar.rng, station["rng"])
            self.selected_contact = (
                self.sonar.contacts.get(int(station["selected_contact_id"]))
                if station["selected_contact_id"] is not None else None)
            self.target = (self.sonar.contacts.get(int(station["target_id"]))
                           if station["target_id"] is not None else None)
        self._opfor = boat
        self._opfor_hold_s = float(crew["hold_s"])

    def _sonar_controls_state(self) -> dict:
        """Operator controls of the active sonar workstation."""
        return dict(
            gain_db=self.sonar.gain_db,
            band_low_hz=self.sonar.band_low_hz,
            band_high_hz=self.sonar.band_high_hz,
            notch_enabled=self.sonar.notch_enabled,
            peak_hold=self.sonar.peak_hold,
            focus_locked=self.sonar.focus_locked,
            tma_enabled=self.sonar.tma_enabled,
            listen_bearing=self.sonar.listen_bearing,
            listen_filtered=self.sonar.listen_filtered,
            audition_mode=self.sonar.audition_mode,
            sonar_page=self.sonar_page, audio_enabled=self.sonar_audio_enabled,
            volume=self.sonar_volume, tma_method=self.tma_method)

    def _sonar_system_state(self, entity_ids) -> dict:
        """Contacts, histories and queues of the active sonar system."""
        return {
            "next_id": max(
                self.sonar._next_contact_id,
                max((contact.id + 1 for contact in self.sonar.contacts.values()),
                    default=1)),
            "contacts": {
                str(cid): dict(
                    contact_id=c.id, target_id=c.target_id, origin=c.origin, kind=c.kind,
                    bearing=c.bearing, range_est=c.range_est,
                    range_sigma_nm=c.range_sigma_nm,
                    range_source=c.range_source, range_seen=c.range_seen,
                    confidence=c.confidence,
                    quality=c.quality, last_seen=c.last_seen,
                    depth_est=c.depth_est, depth_sigma_m=c.depth_sigma_m,
                    player_class=c.player_class,
                    player_profile=c.player_profile,
                    released_to_opz=c.released_to_opz,
                    dip_released_to_opz=c.dip_released_to_opz,
                    ship_observer_x=c.ship_observer_x,
                    ship_observer_y=c.ship_observer_y,
                    passive_source=c.passive_source,
                    observer_x=c.observer_x, observer_y=c.observer_y,
                    signature=c.signature, snr=c.snr,
                    passive_bearing=c.passive_bearing,
                    raw_bearing=c.raw_bearing,
                    raw_bearings=c.raw_bearings,
                    passive_epoch=c._passive_epoch,
                    bearing_filter_t=c._bearing_filter_t,
                    bearing_filter_rate_deg_s=c._bearing_filter_rate_deg_s,
                    bearing_filter_uncertainty_deg=(
                        c._bearing_filter_uncertainty_deg),
                    bearing_uncertainty_deg=c.bearing_uncertainty_deg,
                    ping_pos=c.ping_pos,
                    observed_x=c.observed_x, observed_y=c.observed_y,
                    array_observations=c.array_observations,
                    fusion_status=c.fusion_status,
                    fusion_delta_deg=c.fusion_delta_deg,
                    fused_quality=c.fused_quality,
                    tma_pos=c.tma_pos, tma_course=c.tma_course,
                    tma_speed=c.tma_speed, tma_quality=c.tma_quality,
                    tma_seen=c.tma_seen,
                    tma_ellipse=(list(c.tma_ellipse)
                                 if c.tma_ellipse is not None else None),
                    towed_ambiguous=c.towed_ambiguous,
                    towed_resolved=c.towed_resolved,
                    towed_side=c.towed_side,
                    ambiguity_axis=c.ambiguity_axis,
                    mirror_bearing=c.mirror_bearing,
                    tonal_hz=c.tonal_hz,
                    buoy_fixes=list(c.buoy_fixes[-80:]),
                    buoy_reports={str(seq): dict(report)
                                  for seq, report in c.buoy_reports.items()},
                    helo_qualified=c.helo_qualified,
                    buoy_released_to_opz=c.buoy_released_to_opz,
                    fixes=[dict(fix) for fix in c.active_fixes(self.sim_t)],
                    dip_bearing=c.dip_bearing,
                    dip_bearing_uncertainty_deg=c.dip_bearing_uncertainty_deg,
                    dip_last_seen=c.dip_last_seen,
                    dip_observer_x=c.dip_observer_x,
                    dip_observer_y=c.dip_observer_y)
                for cid, c in self.sonar.contacts.items()},
            "lofar": self.sonar.lofar_history,
            "lofar_times": self.sonar.lofar_times,
            "lofar_bearings": self.sonar.lofar_bearings,
            "broadband": self.sonar.broadband_history,
            "history_times": self.sonar.history_times,
            "tracks": {
                str(target_id): [
                    dict(t=p.t, bearing=p.bearing, fx=p.fx, fy=p.fy,
                         fcourse=p.fcourse,
                         uncertainty_deg=p.uncertainty_deg,
                         freq_hz=p.freq_hz, fspeed=p.fspeed)
                    for p in track.pts]
                for target_id, track in self.sonar._tracks.items()},
            "track_versions": {
                str(target_id): track.version
                for target_id, track in self.sonar._tracks.items()},
            "tma_versions": {
                str(target_id): version
                for target_id, version in self.sonar._tma_versions.items()},
            "tma_next": {
                str(target_id): next_t
                for target_id, next_t in self.sonar._tma_next.items()},
            "pending_pings": [dict(target_id=p["target"].id,
                                    sent_at=p["sent_at"],
                                    ready_at=p["ready_at"],
                                    range_factor=p["range_factor"],
                                    mode=p["mode"],
                                    snapshot=dict(p["snapshot"]))
                              for p in self.sonar._pending_pings
                              if p["target"].id in entity_ids],
            "towed_depth_m": self.sonar.towed_depth_m,
            "towed_depth_target_m": self.sonar.towed_depth_target_m,
            "tow_state": self.sonar.tow_state.value,
            "tow_payout": self.sonar.tow_payout,
            "tow_heading_deg": self.sonar.tow_heading_deg,
            "tow_settle_s": self.sonar._tow_settle_s,
            "tow_handling_ok": self.sonar._tow_handling_ok,
            "vds_state": self.sonar.vds_state.value,
            "vds_payout": self.sonar.vds_payout,
            "vds_depth_m": self.sonar.vds_depth_m,
            "vds_depth_target_m": self.sonar.vds_depth_target_m,
            "vds_settle_s": self.sonar._vds_settle_s,
            "vds_handling_ok": self.sonar._vds_handling_ok,
            "ping_cooldown": self.sonar.ping_cooldown,
            "ping_active": self.sonar.ping_active,
            "ping_anim_timer": self.sonar._ping_anim_timer,
            "echo_history": list(self.sonar.echo_history),
            "bt_profile": self.sonar.bt_profile,
            "bt_cooldown": self.sonar.bt_cooldown,
            "ping_pulse": self.sonar.ping_pulse,
            "pending_clutter": [dict(ready_at=item["ready_at"], mode=item["mode"],
                                     snapshot=dict(item["snapshot"]))
                                for item in self.sonar._pending_clutter],
        }

    def _restore_sonar_controls(self, sonar_controls) -> None:
        self.sonar.gain_db = sonar_controls["gain_db"]
        self.sonar.band_low_hz = sonar_controls["band_low_hz"]
        self.sonar.band_high_hz = sonar_controls["band_high_hz"]
        self.sonar.notch_enabled = sonar_controls["notch_enabled"]
        self.sonar.peak_hold = sonar_controls["peak_hold"]
        self.sonar.focus_locked = sonar_controls["focus_locked"]
        self.sonar.tma_enabled = sonar_controls["tma_enabled"]
        self.sonar.listen_bearing = sonar_controls["listen_bearing"]
        self.sonar.set_audition_mode(sonar_controls["audition_mode"])
        self.sonar.beam_width_deg = beam_width_deg(self.sonar_mode)
        self.sonar._receiver_mode = self.sonar_mode
        self.sonar_page = sonar_controls["sonar_page"]
        self.tma_method = sonar_controls["tma_method"]
        self.sonar_audio_enabled = sonar_controls["audio_enabled"]
        self.sonar_volume = sonar_controls["volume"]
        self._sonar_audio_sequence = -1

    def _restore_sonar_system(self, sn, by_id, observer=None) -> None:
        if sn:
            self.sonar._next_contact_id = sn.get("next_id", 1)
            for cid, cd in sn.get("contacts", {}).items():
                c = Contact(contact_id=cd.get("contact_id", int(cid)), target_id=cd["target_id"],
                            origin=cd.get("origin", "passiv"),
                            kind=cd.get("kind", "sub"))
                c.bearing = cd.get("bearing", 0.0)
                c.range_est = cd.get("range_est")
                c.range_sigma_nm = cd.get("range_sigma_nm")
                c.range_source = cd.get("range_source")
                c.range_seen = cd.get("range_seen")
                c.confidence = cd.get("confidence", 0.0)
                c.quality = cd.get("quality", 0.0)
                c.last_seen = cd.get("last_seen", 0.0)
                c.depth_est = cd.get("depth_est")
                c.depth_sigma_m = cd.get("depth_sigma_m")
                c.player_class = cd.get("player_class")
                c.player_profile = cd["player_profile"]
                c.released_to_opz = cd["released_to_opz"]
                c.dip_released_to_opz = cd.get("dip_released_to_opz", False)
                c.ship_observer_x = cd.get("ship_observer_x")
                c.ship_observer_y = cd.get("ship_observer_y")
                c.passive_source = cd["passive_source"]
                c.observer_x, c.observer_y = cd["observer_x"], cd["observer_y"]
                c.signature = cd.get("signature", "")
                c.snr = cd.get("snr", -99.0)
                c.passive_bearing = cd.get("passive_bearing")
                c.raw_bearing = cd.get("raw_bearing")
                c.raw_bearings = [tuple(row) for row in cd.get(
                    "raw_bearings", [])[-config.BEARING_TRACK_MAX_PTS:]]
                c._passive_epoch = cd.get("passive_epoch")
                c._bearing_filter_t = cd.get("bearing_filter_t")
                c._bearing_filter_rate_deg_s = cd.get(
                    "bearing_filter_rate_deg_s", 0.0)
                c.bearing_uncertainty_deg = cd.get("bearing_uncertainty_deg")
                c._bearing_filter_uncertainty_deg = cd.get(
                    "bearing_filter_uncertainty_deg",
                    c.bearing_uncertainty_deg)
                c.ping_pos = tuple(cd["ping_pos"]) if cd.get("ping_pos") else None
                c.observed_x = cd.get("observed_x")
                c.observed_y = cd.get("observed_y")
                c.array_observations = dict(cd.get("array_observations", {}))
                c.fusion_status = cd.get("fusion_status", "KEINE DATEN")
                c.fusion_delta_deg = cd.get("fusion_delta_deg")
                c.fused_quality = cd.get("fused_quality", 0.0)
                c.tma_pos = tuple(cd["tma_pos"]) if cd.get("tma_pos") else None
                c.tma_course = cd.get("tma_course")
                c.tma_speed = cd.get("tma_speed")
                c.tma_quality = cd.get("tma_quality", 0.0)
                c.tma_seen = cd.get("tma_seen", c.range_seen if c.range_source == "tma" else None)
                c.tma_ellipse = (tuple(cd["tma_ellipse"])
                                 if cd["tma_ellipse"] is not None else None)
                c.towed_ambiguous = cd["towed_ambiguous"]
                c.towed_resolved = cd["towed_resolved"]
                c.towed_side = cd["towed_side"]
                c.ambiguity_axis = cd["ambiguity_axis"]
                c.mirror_bearing = cd["mirror_bearing"]
                c.tonal_hz = cd["tonal_hz"]
                c.buoy_fixes = [tuple(row) for row in cd.get("buoy_fixes", [])]
                c.buoy_reports = {int(seq): dict(row) for seq, row in
                                  cd.get("buoy_reports", {}).items()}
                c.helo_qualified = cd.get("helo_qualified", False)
                c.buoy_released_to_opz = cd.get("buoy_released_to_opz", False)
                c.fixes = {fix["source"]: dict(fix) for fix in cd["fixes"]}
                c.dip_bearing = cd.get("dip_bearing")
                c.dip_bearing_uncertainty_deg = cd.get("dip_bearing_uncertainty_deg")
                c.dip_last_seen = cd.get("dip_last_seen")
                c.dip_observer_x = cd.get("dip_observer_x")
                c.dip_observer_y = cd.get("dip_observer_y")
                c._fx = c.observer_x
                c._fy = c.observer_y
                if c.observed_x is None or c.observed_y is None:
                    if c.range_source == "tma" and c.tma_pos is not None:
                        c.observed_x, c.observed_y = c.tma_pos
                    elif c.range_source == "ping" and c.ping_pos is not None:
                        c.observed_x, c.observed_y = c.ping_pos
                    elif c.range_source in ("ping", "buoy") \
                            and c.range_est is not None:
                        brg = math.radians(c.bearing)
                        c.observed_x = self.ship.x + c.range_est * math.sin(brg)
                        c.observed_y = self.ship.y - c.range_est * math.cos(brg)
                        if c.range_source == "ping":
                            c.ping_pos = (c.observed_x, c.observed_y)
                self.sonar.contacts[c.target_id] = c
            self.sonar.lofar_history = [list(col)
                                        for col in sn.get("lofar", [])]
            self.sonar.lofar_times = list(sn.get("lofar_times", []))
            self.sonar.lofar_bearings = list(sn.get("lofar_bearings", []))
            self.sonar.broadband_history = [list(row) for row in sn.get("broadband", [])]
            self.sonar.history_times = list(sn.get("history_times", []))
            self.sonar.towed_depth_m = sn.get(
                "towed_depth_m", config.SONAR_TOWED_DEPTH_M)
            self.sonar.towed_depth_target_m = sn.get(
                "towed_depth_target_m", self.sonar.towed_depth_m)
            try:
                self.sonar.tow_state = TowState(sn.get("tow_state", "STOWED"))
            except (TypeError, ValueError):
                self.sonar.tow_state = TowState.STOWED
            self.sonar.tow_payout = config.clamp(float(sn.get("tow_payout", 0.0)), 0.0, 1.0)
            self.sonar.tow_heading_deg = float(sn.get("tow_heading_deg", 0.0)) % 360.0
            self.sonar._tow_settle_s = config.clamp(
                float(sn.get("tow_settle_s", 0.0)), 0.0, config.SONAR_TOWED_SETTLE_S)
            self.sonar._tow_handling_ok = bool(sn.get("tow_handling_ok", True))
            self.sonar.vds_state = TowState(sn["vds_state"])
            self.sonar.vds_payout = float(sn["vds_payout"])
            self.sonar.vds_depth_m = float(sn["vds_depth_m"])
            self.sonar.vds_depth_target_m = float(sn["vds_depth_target_m"])
            self.sonar._vds_settle_s = float(sn["vds_settle_s"])
            self.sonar._vds_handling_ok = sn["vds_handling_ok"]
            self.sonar.ping_cooldown = max(0.0, float(sn.get("ping_cooldown", 0.0)))
            self.sonar.ping_active = bool(sn.get("ping_active", False))
            self.sonar._ping_anim_timer = max(0.0, float(sn.get("ping_anim_timer", 0.0)))
            self.sonar.echo_history = list(sn.get("echo_history", []))[-config.SONAR_ECHO_HISTORY_MAX:]
            self.sonar.bt_profile = sn.get("bt_profile")
            self.sonar.bt_cooldown = sn.get("bt_cooldown", 0.0)
            track_versions = sn.get("track_versions", {})
            for target_id, points in sn.get("tracks", {}).items():
                track = BearingTrack()
                track.pts = [BearingPoint(p["t"], p["bearing"], p["fx"],
                                          p["fy"], p["fcourse"],
                                          p.get("uncertainty_deg"),
                                          p["freq_hz"], p["fspeed"])
                             for p in points[-config.BEARING_TRACK_MAX_PTS:]]
                track.version = track_versions.get(target_id, len(track.pts))
                self.sonar._tracks[int(target_id)] = track
            self.sonar._tma_versions = {
                int(target_id): version
                for target_id, version in sn.get("tma_versions", {}).items()
                if int(target_id) in self.sonar._tracks
            }
            self.sonar._tma_next = {
                int(target_id): float(next_t)
                for target_id, next_t in sn.get("tma_next", {}).items()
                if int(target_id) in self.sonar._tracks
            }
            self.sonar.ping_pulse = sn["ping_pulse"]
            self.sonar._pending_clutter = [
                dict(ready_at=item["ready_at"], mode=item["mode"],
                     snapshot=dict(item["snapshot"]))
                for item in sn["pending_clutter"]]
            for pd in sn.get("pending_pings", []):
                target = by_id.get(pd.get("target_id"))
                if target is not None:
                    mode = pd["mode"]
                    self.sonar._pending_pings.append({
                        "target": target,
                        "frigate": self.ship if observer is None else observer,
                        "world": self.world,
                        "sent_at": pd["sent_at"],
                        "ready_at": pd["ready_at"],
                        "range_factor": pd["range_factor"],
                        "mode": mode,
                        "snapshot": dict(pd["snapshot"]),
                    })

    def save_state(self) -> dict:
        """Return the complete canonical save state for this release."""
        opz_map = self._opz_map_save_values()
        entity_groups = {
            "sub": (Sub, self.subs), "animal": (Animal, self.animals),
            "surface": (SurfaceShip, self.civilians + self.warships),
            "decoy": (Decoy, self.decoys),
            "enemy_torpedo": (EnemyTorpedo, self.enemy_torpedoes),
        }
        entity_ids = {entity.id for _, entities in entity_groups.values()
                      for entity in entities}
        asm_ids = {a.seq for a in self.asms}
        return {
            "version": SAVE_VERSION,
            "save_schema": SAVE_SCHEMA,
            "platform_state_version": 1,
            "catalog_snapshot": self.runtime_catalog.runtime_snapshot(),
            "next_entity_ids": {
                key: max(cls._next_id, max((e.id + 1 for e in entities), default=0))
                for key, (cls, entities) in entity_groups.items()},
            "autocrew": self.autocrew.serialize(),
            "ais": self.ais.serialize(),
            "plot": self.plot.to_save(),
            "route": self.route.serialize(),
            "seed": self.seed,
            "mission_type": self.mission.type_key,
            "mission_time": self.mission_time,
            "mission_events": list(self.mission_events_pending),
            "tasking": self.tasking.serialize(),
            "incidents": self.incidents.serialize(),
            "hq_reports": self.hq_reports.serialize(),
            "rbu": self.rbu_serialize(),
            "casualties": self.casualties_serialize(),
            "baffle_clear": (None if self.baffle_clear is None
                             else [float(value) for value in self.baffle_clear]),
            "hunter_esm": [dict(row) for row in self.hunter_esm],
            "watch": self.crew_watch.serialize(),
            "mpa": self.mpa.serialize(),
            "ping_intercepts": [list(row) for row in sorted(self._ping_intercepts)],
            "radar_marks": dict(
                blip_seq=int(self.radar_blip_seq),
                blips=[dict(blip) for blip in self.radar_blips],
                marked=[[int(sub_id), str(track_id), float(last)] for sub_id, (track_id, last)
                        in sorted(self._radar_marked.items())]),
            "score": self.score,
            "incident": self.incident,
            "mission_result": self.mission_result,
            "result_reason": self.result_reason,
            "ship": dict(x=self.ship.x, y=self.ship.y, course=self.ship.course,
                         target_course=self.ship.target_course,
                         speed=self.ship.speed, target_speed=self.ship.target_speed,
                         order_idx=self.ship.order_idx,
                         astern=self.ship.astern,
                         hull=self.ship.hull_spec.to_dict(),
                         grounding=dict(
                             latched=self.ship.grounding_latched,
                             last_safe_pose=list(
                                 self.ship.last_safe_pose if self.ship.grounding_latched
                                 else (self.ship.x, self.ship.y, self.ship.course)),
                             contact=(None if self.ship.grounding_contact is None else
                                      dict(kind=self.ship.grounding_contact.kind,
                                           x_nm=self.ship.grounding_contact.x_nm,
                                           y_nm=self.ship.grounding_contact.y_nm,
                                           normal_x=self.ship.grounding_contact.normal_x,
                                           normal_y=self.ship.grounding_contact.normal_y,
                                           hull_longitudinal=self.ship.grounding_contact.hull_longitudinal,
                                           hull_lateral=self.ship.grounding_contact.hull_lateral))),
                         turn_rate_scale=self.ship.turn_rate_scale,
                         rudder_angle=self.ship.rudder_angle,
                         yaw_rate=self.ship.yaw_rate,
                          roll=self.ship.roll, pitch=self.ship.pitch,
                          roll_rate=self.ship.roll_rate,
                          pitch_rate=self.ship.pitch_rate,
                          wake=[list(point) for point in self.ship.wake],
                          quiet_mode=self.ship.quiet_mode,
                          plant_mode=self.ship.plant_mode,
                          fuel_capacity_kg=self.ship.fuel_capacity_kg,
                          fuel_kg=self.ship.fuel_kg,
                          clock=self.ship._clock),
            "torpedoes": dict(total=self.torpedo_total, count=self.torpedo_count,
                               depth=self.torpedo_depth),
            "asw": {
                "version": ASW_STATE_VERSION,
                "loadout": copy.deepcopy(self._ownship_loadout),
                "player_battery": self.player_torpedo_battery.serialize(),
                "countermeasure": self.nixie_store.serialize(),
                "nixies": [item.serialize() for item in self.nixies],
                "nixie_seq": self.nixie_seq,
                "asrocs": [item.serialize() for item in self.asrocs],
                "asroc_seq": self.asroc_seq,
                "depth_charges": [item.serialize() for item in self.depth_charges],
                "depth_charge_seq": self.depth_charge_seq,
                "own_stores": {"depth_charges": self.depth_charges_left,
                               "asroc": self.own_asrocs_left,
                               "depth_charge_reload_s": self.depth_charge_reload_s},
            },
            "air_defense": {
                "version": AIR_DEFENSE_STATE_VERSION,
                "loadout": copy.deepcopy(self._air_defense_loadout),
                "sam_remaining": self.vls_cells,
                "essm_seq": max([self.essm_seq] + [item.seq for item in self.essms]),
                "softkill": self.softkill_store.serialize(),
                "aa_ammo": self.aa_ammo,
                "aa_cooldown_s": self.aa_cooldown_s,
                "raiders": [dict(x=r.x, y=r.y, course=r.course, seq=r.seq,
                                  phase=r.phase.value, hp=r.hp,
                                  salvo_cd=r.salto_cd,
                                  pending_asm=r.pending_asm,
                                  attack_t=r.attack_t,
                                  altitude_m=r.altitude_m, popup_t=r.popup_t)
                             for r in self.raiders],
                "raider_seq": self.raid_seq,
                "waves_spawned": self.raid_waves_spawned,
            },
            "level": self.level,
            "mission_name": self.mission.name,
            "mission_runtime": dict(
                name=self.mission.name, win_mode=self.mission.win_mode,
                time_limit_s=self.mission.time_limit_s,
                asm_count=self.mission.asm_count,
                custom_definition=self.custom_mission_definition,
                units={key: int(value) for key, value in sorted(self.mission_units.items())},
                difficulty=dict(self.difficulty)),
            "damage": dict(
                repair_mult=self.damage.repair_mult,
                compartments={k: dict(state=c.state, flood=c.flood, fire=c.fire,
                                      hole_m2=c.hole_m2, heat_s=c.heat_s,
                                      shorted=c.shorted,
                                      counterflood=self.damage.counterflood.get(k, 0.0))
                              for k, c in self.damage.compartments.items()},
                teams={str(k): v for k, v in self.damage.teams.items()},
                team_position={str(k): v for k, v
                               in self.damage.team_position.items()},
                team_eta={str(k): v for k, v in self.damage.team_eta.items()},
                patch_kits=self.damage.patch_kits,
                cooked_off=self.damage.cooked_off,
                capsized=self.damage.capsized,
                draft_m=self.damage.draft_m),
            "world": dict(hour=self.world.hour,
                           sea_state=self.world.sea_state,
                           weather_shift_timer=self.world.weather_shift_timer,
                           weather_override=self.world.weather_override,
                           ocean=self.world.ocean.serialize(),
                           mode=self.world_mode,
                           generator=("natural-earth-v1"
                                      if self.world_mode in ("procedural", "real_fixed")
                                      else "fixed-reference-v1"),
                           coast=self.world.coast.to_dict()),
            "sonar_mode": self.sonar_mode,
            "sonar_controls": self._sonar_controls_state(),
            "radars": dict(surface=self.surface_radar_on,
                           air=self.air_radar_on,
                           range_nm=self.opz_range_nm,
                           scan_phase=self.radar_scan_phase,
                           scan_pending_deg=self.radar_scan_pending_deg),
            "roe": self.roe,
            "asm_spawned": self.asm_spawned,
            "air_threat_reported": self.air_threat_reported,
            "asm_seq": max([self.asm_seq, self.asm_spawned] + list(asm_ids)
                           + [e.target_id for e in self.essms if e.target_id is not None]
                           + [t.target_id for t in self.air_picture._tracks.values()
                              if self._missile_seq(t) is not None]),
            "warship_asm_seq": self.warship_asm_seq,
            "vls_cells": self.vls_cells,
            "ciws_ammo": self.ciws_ammo,
            "ciws_cooldown_s": self.ciws_cooldown_s,
            "ciws_mount_deg": self.ciws_mount_deg,
            "chaff_clouds": [cloud.to_dict() for cloud in self.chaff_clouds],
            "chaff_seq": self.chaff_seq,
            "air_picture": self.air_picture.serialize(),
            "opz_affiliations": dict(self.opz_affiliations),
            "esm": {
                "version": ESM_STATE_VERSION,
                "track_seq": self.esm_picture.track_seq,
                "picture": self.esm_picture.serialize(),
                "selected_track_key": self.eloka_selected_track_key,
                "annotations": [
                    {"track_key": track_key, "emitter_key": emitter_key}
                    for track_key, emitter_key in sorted(
                        self.eloka_annotations.items())
                ],
                "ecm": self.ecm_jammer.serialize(),
            },
            "radio_picture": self.radio_picture.serialize(),
            "radio_sel": self.radio_sel,
            "hfdf_log": self.hfdf_log,
            "hfdf_fixes": self.hfdf_fixes,
            "schedulers": dict(sensor=self._sensor_acc,
                                esm=self._esm_acc,
                                radio=self._radio_acc,
                               slow=self._slow_acc),
            "torpedo_seq": self.torpedo_seq,
            "buoy_seq": self.buoy_seq,
            "chaff_cd": self.chaff_cd,
            "hq_timer": self.hq_timer,
            "asm_sel": self.asm_sel,
            "dmg_cursor": self.dmg_cursor,
            "dmg_team": self.dmg_team,
            "messages": [list(m) for m in self.messages],
            "helo": dict(state=self.helo.state, x=self.helo.x, y=self.helo.y,
                           torpedo_profile_key=self.helo.torpedo_profile.key,
                           course=self.helo.course, torps=self.helo.torps,
                           buoys_left=self.helo.buoys_left, fuel_s=self.helo.fuel_s,
                           waypoint_x=self.helo.waypoint_x,
                           waypoint_y=self.helo.waypoint_y,
                           dip_state=self.helo.dip_state,
                           dip_depth_m=self.helo.dip_depth_m,
                           dip_depth_target_m=self.helo.dip_depth_target_m,
                           dip_water_depth_m=self.helo.dip_water_depth_m,
                           dip_ping_cooldown=self.helo.dip_ping_cooldown,
                           hover_x=self.helo.hover_x, hover_y=self.helo.hover_y,
                           pattern=self.helo.pattern,
                           pattern_queue=[list(point) for point in self.helo.pattern_queue],
                           mad_mode=self.helo.mad_mode,
                           radar_on=self.helo.radar_on),
            "subs": [dict(id=s.id, x=s.x, y=s.y, depth=s.depth, course=s.course,
                           state=s.state, speed=s.speed, damage=s.damage,
                           torpedoes_left=s.torpedoes_left, heard_ping=s.heard_ping,
                           asw_battery=(s.weapon_battery.serialize()
                                        if s.weapon_battery is not None else None),
                           countermeasure_store=(s.countermeasure_store.serialize()
                                                 if s.countermeasure_store is not None
                                                 else None),
                          stype=s.stype.key, start_pos=s.start_pos,
                          evac_left=s.evac_left, sink_left=s.sink_left,
                           quiet_mult=s.quiet_mult, attack_mult=s.attack_mult,
                           attack_cooldown=s.attack_cooldown,
                           attack_left=s.attack_left,
                           solution_threshold=s.solution_threshold,
                           fingerprint=s.fingerprint.to_dict(),
                          torpedo_alerted=s.torpedo_alerted,
                           decoy_cd=s._decoy_cd,
                           active_ping_cd=s._active_ping_cd,
                           radar_hold_s=s.radar_hold_s,
                           speed_order=s.speed_order,
                           tma_track=[dict(t=p.t, bearing=p.bearing, fx=p.fx, fy=p.fy,
                                           fcourse=p.fcourse,
                                           uncertainty_deg=p.uncertainty_deg,
                                           fspeed=p.fspeed)
                                      for p in s.tma_track.pts],
                           tma_track_id=s.tma_track_id,
                           tma_next_t=s.tma_next_t,
                           torpedo_alarm_left=s.torpedo_alarm_left,
                           blow_available=s.blow_available,
                           emergency_ascent=s.emergency_ascent,
                           transient_left=s.transient_left,
                           flood_noise_left=s.flood_noise_left,
                           flood_quiet=s.flood_quiet, flood_seq=s.flood_seq,
                           ai_tube_left=s.ai_tube_left,
                           ai_fire_pending=s.ai_fire_pending,
                           hull_fatigue=s.hull_fatigue,
                           turn_left=s.turn_left, turn_delta=s.turn_delta,
                           target_course=s.target_course,
                           target_depth=s.target_depth,
                           depth_rate_mps=s.depth_rate_mps,
                           evade_offset=s.evade_offset,
                          sensor_seed=s.sensor_seed,
                           memory={key: (None if key in (
                               "last_ping_age", "last_torpedo_age")
                               and value == float("inf") else value)
                               for key, value in s.memory.items()},
                           pending_torpedoes=list(s.pending_torpedoes),
                            pending_decoys=list(s.pending_decoys),
                            manual=s.manual, order_course=s.order_course,
                            order_speed=s.order_speed, order_depth=s.order_depth,
                            last_bottom_m=s.last_bottom_m,
                            manual_ping_pending=s._manual_ping_pending,
                            ballast=s.ballast.serialize(),
                            damage_control=s.damage_control.serialize(),
                            decision_reason=s.decision_reason,
                            endurance=(s.endurance.serialize()
                                       if s.endurance is not None else None),
                            platform=s.sensor_suite.serialize())
                     for s in self.subs],
            "animals": [dict(id=a.id, x=a.x, y=a.y, depth=a.depth,
                             course=a.course, speed=a.speed,
                              atype=a.atype.key, dead=a.dead,
                              turn_left=a.turn_left, turn_delta=a.turn_delta,
                              target_course=a.target_course,
                              target_depth=a.target_depth,
                             sensor_seed=a.sensor_seed)
                        for a in self.animals],
            "civilians": [dict(id=c.id, x=c.x, y=c.y, course=c.course,
                                speed=c.speed, name=c.name, sunk=c.sunk,
                                damage=c.damage, emitter=c.emitter,
                                depth=c.depth, signature_key=c.signature_key,
                                 turn_left=c.turn_left, turn_delta=c.turn_delta,
                                 target_course=c.target_course,
                                 target_speed=c.target_speed,
                                 orbit_direction=c.orbit_direction,
                                 sensor_contact=c.sensor_contact,
                                 sensor_contact_age=c.sensor_contact_age,
                                 sunk_score_awarded=c.sunk_score_awarded,
                                 torpedo_evade_left=c._torpedo_evade_left,
                                 torpedo_threat_bearing=c._torpedo_threat_bearing,
                                 sensor_seed=c.sensor_seed,
                                 fingerprint=c.fingerprint.to_dict(),
                                 platform=c.sensor_suite.serialize())
                          for c in self.civilians],
            "warships": [dict(id=w.id, x=w.x, y=w.y, course=w.course,
                               speed=w.speed, name=w.name, sunk=w.sunk,
                               damage=w.damage, emitter=w.emitter,
                               depth=w.depth, signature_key=w.signature_key,
                                turn_left=w.turn_left, turn_delta=w.turn_delta,
                                target_course=w.target_course,
                                target_speed=w.target_speed,
                                waypoint=(list(w.waypoint)
                                          if w.waypoint is not None else None),
                                orbit_direction=w.orbit_direction,
                                sensor_contact=w.sensor_contact,
                                sensor_contact_age=w.sensor_contact_age,
                                sunk_score_awarded=w.sunk_score_awarded,
                                torpedo_evade_left=w._torpedo_evade_left,
                                countermeasures_left=w.countermeasures_left,
                                torpedo_threat_bearing=w._torpedo_threat_bearing,
                                 pending_asm=list(w.pending_asm),
                                 asroc_battery=(w.asroc_battery.serialize()
                                                if w.asroc_battery is not None
                                                else None),
                                 pending_asroc=list(w.pending_asroc),
                                 asw_last_seen=w.asw_last_seen,
                               sensor_seed=w.sensor_seed,
                               attack_left=w.attack_left,
                                anchor=(list(w.anchor)
                                        if w.anchor is not None else None),
                                fingerprint=w.fingerprint.to_dict(),
                                platform=w.sensor_suite.serialize())
                          for w in self.warships],
            "decoys": [dict(id=d.id, x=d.x, y=d.y, depth=d.depth,
                              course=d.course, speed=d.speed, life=d.life,
                              sensor_seed=d.sensor_seed,
                              profile_key=d.profile.key, source_id=d.source_id)
                       for d in self.decoys],
            # Phase 2: laufende Projektil-/Sensoren-Objekte
            "torpedoes_in_flight": [
                dict(x=t.x, y=t.y, course=t.course, depth=t.depth,
                     travel=t.travel, state=t.state, idx=t.idx,
                     target_depth=t.target_depth,
                      target_id=(t.target.id if t.target is not None
                                 and t.target.id in entity_ids else None),
                      speed_kn=t.speed_kn,
                      range_nm=t.range_nm, terminal_active=t.terminal_active,
                     guidance_x=t.guidance_x, guidance_y=t.guidance_y,
                      seeker_acquired=(t.seeker_acquired and t.target is not None
                                       and t.target.id in entity_ids),
                       profile_key=t.profile_key, launch_origin=t.launch_origin,
                       launch_platform_id=t.launch_platform_id,
                       launch_weapon_key=t.launch_weapon_key,
                     search_phase=t._search_phase, midcourse=t._midcourse,
                     midcourse_timer=t._midcourse_timer,
                     kill_dist_nm=t.kill_dist_nm, kill_depth_m=t.kill_depth_m,
                     time_since_launch=t.time_since_launch,
                     energy_s=t.energy_s, motor_fraction=t.motor_fraction,
                     depth_rate=t.depth_rate, wire_ship_out_nm=t.wire_ship_out_nm,
                     wire_stress_s=t.wire_stress_s,
                     rejected_ids=list(t.rejected_ids),
                     pattern=t.pattern, enable_nm=t.enable_nm,
                     turns_done=t._turns_done)
                for t in self.torpedoes],
            "enemy_torpedoes": [
                dict(id=t.id, x=t.x, y=t.y, course=t.course, depth=t.depth,
                      travel=t.travel, idx=t.idx, profile_key=t.profile_key,
                      guidance_x=t.guidance_x, guidance_y=t.guidance_y,
                       terminal_active=t.terminal_active,
                       seeker_acquired=t.seeker_acquired,
                       launch_platform_id=t.launch_platform_id,
                       launch_weapon_key=t.launch_weapon_key,
                       seeker_target=("ship" if t._seeker_target is self.ship else
                                     f"nixie:{t._seeker_target.seq}"
                                     if t._seeker_target in self.nixies else None),
                       time_since_launch=t.time_since_launch,
                       energy_s=t.energy_s, motor_fraction=t.motor_fraction,
                       depth_rate=t.depth_rate, target_depth=t.target_depth)
                for t in self.enemy_torpedoes],
            "asms": [dict(x=a.x, y=a.y, course=a.course, seq=a.seq,
                            profile_key=a.profile_key,
                            state=a.state, jammer=a.jammer,
                           age_s=a.age_s, travel=a.travel,
                          chaff_left=a.chaff_left, broken=a.broken,
                          speed_kn=a.speed_kn, boosting=a.boosting,
                          altitude_m=a.altitude_m, datum_x=a.datum_x,
                          datum_y=a.datum_y, lock_s=a.lock_s, locked=a.locked,
                          los_prev=a.los_prev, chaff_cloud=a.chaff_cloud)
                     for a in self.asms],
            "essms": [dict(x=e.x, y=e.y, course=e.course, seq=e.seq,
                             profile_key=e.profile_key,
                             state=e.state, travel=e.travel,
                            guidance_x=e.guidance_x, guidance_y=e.guidance_y,
                            track_target_id=e.target_id,
                            seeker_acquired=(e.seeker_acquired and e.target is not None
                                             and e.target.seq in asm_ids),
                            target_id=(e.target.seq if e.target is not None
                                       and e.target.seq in asm_ids else None),
                            los_prev=e.los_prev)
                      for e in self.essms],
            "buoys": [dict(x=b.x, y=b.y, seq=b.seq, battery_s=b.battery_s,
                           mode=b.mode, last_ping_epoch=b.last_ping_epoch,
                           owner=b.owner)
                      for b in self.buoys],
            "flights": {
                "seq": self.flights._seq,
                "spawn_cd": self.flights._spawn_cd,
                "items": [dict(kind=f.kind, seq=f.seq,
                                 base_id=f.base_id,
                                 dest_id=f.dest.get("id") if f.dest else None,
                                 x=f.x, y=f.y, course=f.course,
                                 akey=f.akey,
                                  loiter_nm=f.loiter_nm,
                                  radar_emitting=f.radar_emitting,
                                  sensor_bearing=f.sensor_bearing, sensor_age=f.sensor_age,
                                 waypoints=getattr(f, "waypoints", None),
                                 waypoint_idx=getattr(f, "waypoint_idx", 0),
                                total_dist=f.total_dist,
                                traveled=f.traveled, active=f.active,
                                platform=f.sensor_suite.serialize())
                           for f in self.flights.flights],
            },
            "sonar": self._sonar_system_state(entity_ids),
            "crew": self._crew_state(entity_ids),
            "weapon_settings": dict(torpedo_type=self.torpedo_type,
                                    pattern=self.torpedo_pattern,
                                    enable_nm=self.torpedo_enable_nm,
                                    salvo=self.torpedo_salvo),
            "sim_t": self.sim_t,
            # Legacy v12 fields: the game always runs at 1x and never pauses.
            "time_scale_idx": 0,
            "scenario_key": self.scenario_key,
            "ui": dict(
                station=self.station.name,
                target_id=self.target.target_id if self.target else None,
                selected_contact_id=(self.selected_contact.id
                                     if self.selected_contact else None),
                opz_selected_track_id=(None if self.opz_selected_track_id
                                       in self.opz_fusion.fusions
                                       else self.opz_selected_track_id),
                map_cx=self.map_view.cx, map_cy=self.map_view.cy,
                map_scale=self.map_view.scale,
                map_follow=self.map_follow,
                opz_map_cx=opz_map.cx,
                opz_map_cy=opz_map.cy,
                opz_map_scale=opz_map.scale,
                opz_map_follow=self.opz_map_follow,
                paused=False,
                local_side=self.local_side,
                tooltips_enabled=getattr(self, "tooltips_enabled", True),
                pinned_tooltip=layout.valid_tooltip(
                    getattr(self, "pinned_tooltip", None)),
                tooltip_anchor=list(self._tooltip_anchor)
                if self._tooltip_anchor is not None else None,
            ),
            "rngs": {
                "world": self._rng_state(self.rng_world),
                "world_weather": self._rng_state(self.world.rng),
                "asm": self._rng_state(self.rng_asm),
                "damage": self._rng_state(self.damage.rng),
                "helo": self._rng_state(self.helo.rng),
                "sonar": self._rng_state(self.sonar.rng),
                "flight": self._rng_state(self.flights.rng),
                "asw": self._rng_state(self.rng_asw),
                "raid": self._rng_state(self.rng_raid),
            },
        }

    def save_game(self, path: str = None) -> str:
        import tempfile
        path = path or config.SAVE_PATH
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=parent, delete=False) as f:
                temporary = f.name
                json.dump(self.save_state(), f, indent=1, allow_nan=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None and os.path.exists(temporary):
                os.unlink(temporary)
        return path

    @staticmethod
    def _restore_rng(r: "random.Random", data) -> None:
        r.setstate((data[0], tuple(data[1]), data[2]))

    def load_state(self, data: dict) -> None:
        """Restore transactionally, including direct in-memory callers."""
        if not self._load_save_data(data):
            raise ValueError("invalid save state")

    def _restore_state(self, data: dict) -> None:
        import random

        def restore_entity(cls, *args, **kwargs):
            # Constructors allocate first. Account for these temporary IDs even
            # if a later constructor/restoration step fails.
            self._restore_id_allocations[cls] += 1
            return cls(*args, **kwargs)

        def restore_platform(entity, row, profile_key):
            state = row["platform"]
            side = state["side"]
            doctrine = state["doctrine"]
            entity.side = side
            entity.doctrine = doctrine
            entity.sensor_suite = PlatformSensorSuite(
                self.runtime_catalog, profile_key, entity.sensor_seed,
                side=side, doctrine=doctrine, now=self.sim_t,
                datalink_group=state["datalink_group"])
            entity.sensor_suite.restore(
                state, self.runtime_catalog, profile_key, self.sim_t)

        seed = data["seed"]
        w = data["world"]
        coast_data = w["coast"]
        coast = Coastline(coast_data, float(coast_data["world_nm"]))
        self.world_mode = w["mode"]
        self.world = World(seed=seed, coast=coast)
        self.world.hour = w["hour"]
        self.world.sea_state = w["sea_state"]
        self.world.weather_shift_timer = w["weather_shift_timer"]
        self.world.weather_override = w["weather_override"]
        self.world.ocean.restore(w["ocean"])
        self.seed = seed
        self.sonar = SonarSystem(
            seed=seed, acoustic_profiles=self.runtime_catalog.acoustic_profiles)
        self.sonar_harmonic_hz = None
        # Operator LOFAR/DEMON tools: cursor, marks, integration (UI only).
        self.sonar_tools = analysis_tools.AcousticToolState()
        # Operator TMA hypotheses per sonar target (transient UI state).
        self.tma_hypotheses = {}
        # Shared operator plot layer (chart marks, rulers, bearing lines...).
        self.plot = PlotLayer()
        self._reset_plot_ui()
        rng = random.Random(seed + 99999)
        self.rng_world = rng
        ship = data["ship"]
        self.flights = FlightManager(
            self.world.coast, random.Random(seed + 2024), self.runtime_catalog,
            near=(ship["x"], ship["y"]))
        self.ship = Ship(x_nm=ship["x"], y_nm=ship["y"],
                         course_deg=ship["course"])
        self.live_traffic.configure(self, self.world, self.preferences)
        self.ship.target_course = ship["target_course"]
        self.ship.speed = ship["speed"]
        self.ship.target_speed = ship["target_speed"]
        self.ship.order_idx = ship["order_idx"]
        self.ship.astern = ship["astern"]
        self.ship.hull_spec = HullSpec(**ship["hull"])
        grounding = ship["grounding"]
        self.ship.grounding_latched = grounding["latched"]
        self.ship.last_safe_pose = tuple(grounding["last_safe_pose"])
        self.ship.grounding_contact = (None if grounding["contact"] is None
                                       else GroundingContact(**grounding["contact"]))
        self.ship.turn_rate_scale = ship["turn_rate_scale"]
        self.ship.rudder_angle = ship["rudder_angle"]
        self.ship.yaw_rate = ship["yaw_rate"]
        self.ship.roll = ship["roll"]
        self.ship.pitch = ship["pitch"]
        self.ship.roll_rate = ship["roll_rate"]
        self.ship.pitch_rate = ship["pitch_rate"]
        self.ship.wake = [list(point) for point in ship["wake"]]
        self.ship.quiet_mode = ship["quiet_mode"]
        self.ship.plant_mode = ship["plant_mode"]
        self.ship.fuel_capacity_kg = ship["fuel_capacity_kg"]
        self.ship.fuel_kg = ship["fuel_kg"]
        self.ship._clock = ship["clock"]
        self.autocrew = AutocrewController.restore(data["autocrew"])
        self.autocrew_overview_open = False
        self.weather_station_open = False
        runtime_mission = data["mission_runtime"]
        self.difficulty = {
            name: (int(runtime_mission["difficulty"][name]) if kind is int
                   else float(runtime_mission["difficulty"][name]))
            for name, (kind, *_rest) in config.DIFFICULTY_FIELDS.items()}
        self.mission = Mission(seed, type_key=data["mission_type"],
                               difficulty=self.difficulty)
        self.mission.name = runtime_mission["name"]
        self.mission.win_mode = runtime_mission["win_mode"]
        self.mission.time_limit_s = float(runtime_mission["time_limit_s"])
        self.mission.asm_count = runtime_mission["asm_count"]
        self.custom_mission_definition = runtime_mission["custom_definition"]
        self.mission_units = {str(key): int(value)
                              for key, value in runtime_mission["units"].items()}
        if self.custom_mission_definition is not None:
            environment = self.custom_mission_definition.get("environment", {})
            thermo = environment.get("thermocline_depth_m")
            if isinstance(thermo, (int, float)) and not isinstance(thermo, bool):
                self.world._thermo = [[float(thermo) for _ in row]
                                      for row in self.world._thermo]
        self.mission_time = data["mission_time"]
        self.mission_events_pending = [str(item) for item in data["mission_events"]]
        self.tasking = TaskBoard.restore(data["tasking"])
        self.incidents = IncidentBoard.restore(data["incidents"])
        self.hq_reports = HqReports.restore(data["hq_reports"])
        self.rbu_restore(data["rbu"])
        self.casualties_restore(data["casualties"])
        self.baffle_clear = (None if data["baffle_clear"] is None
                             else [float(value) for value in data["baffle_clear"]])
        self.hunter_esm = [dict(row) for row in data["hunter_esm"]]
        self.task_sel = 0
        self.crew_watch = CrewState.restore(data["watch"])
        self.mpa = PatrolAircraft.restore(data["mpa"], self.world.size_nm)
        self._ping_intercepts = [tuple(row) for row in data["ping_intercepts"]]
        marks = data["radar_marks"]
        self.radar_blip_seq = marks["blip_seq"]
        self.radar_blips = deque((dict(blip) for blip in marks["blips"]),
                                 maxlen=config.RADAR_BLIP_MAX)
        self._radar_marked = {sub_id: (track_id, last) for sub_id, track_id, last
                              in marks["marked"]}
        self.score = data["score"]
        self.incident = data["incident"]
        self.sim_t = data["sim_t"]
        self.scenario_key = data["scenario_key"]
        self.level = data["level"]
        tp = data["torpedoes"]
        self.torpedo_total = tp["total"]
        self.torpedo_count = tp["count"]
        self.torpedo_depth = tp["depth"]
        asw = data["asw"]
        self._ownship_loadout = copy.deepcopy(asw["loadout"])
        self.player_torpedo_battery = WeaponBattery.restore(
            asw["player_battery"])
        self.nixie_store = ConsumableStore.restore(asw["countermeasure"])
        self.nixies = [TowedAcousticDecoy.restore(row, self.ship)
                       for row in asw["nixies"]]
        self.nixie_seq = asw["nixie_seq"]
        self.asrocs = [ASROC.restore(row) for row in asw["asrocs"]]
        self.asroc_seq = asw["asroc_seq"]
        self.depth_charges = [DepthCharge.restore(row) for row in asw["depth_charges"]]
        self.depth_charge_seq = asw["depth_charge_seq"]
        self.depth_charges_left = asw["own_stores"]["depth_charges"]
        self.own_asrocs_left = asw["own_stores"]["asroc"]
        self.depth_charge_reload_s = asw["own_stores"]["depth_charge_reload_s"]
        air_defense = data["air_defense"]
        self._air_defense_loadout = copy.deepcopy(air_defense["loadout"])
        self.asm_speed_kn = self._air_defense_loadout["asm"]["speed_kn"]
        self.vls_loadout_total = self._air_defense_loadout["vls"]["sam_loadout"]
        self.softkill_store = ConsumableStore.restore(air_defense["softkill"])
        self.essm_seq = air_defense["essm_seq"]
        self.aa_ammo = air_defense["aa_ammo"]
        self.aa_cooldown_s = air_defense["aa_cooldown_s"]
        self.raid_seq = air_defense["raider_seq"]
        self.raid_waves_spawned = air_defense["waves_spawned"]
        self.raiders = []
        for row in air_defense["raiders"]:
            raider = Raider(row["x"], row["y"], row["course"], row["seq"],
                            self.rng_raid,
                            self._air_defense_loadout["raider"])
            raider.phase = RaidPhase.parse(row["phase"])
            raider.hp = row["hp"]
            raider.salto_cd = row["salvo_cd"]
            raider.pending_asm = row["pending_asm"]
            raider.attack_t = row["attack_t"]
            raider.altitude_m = row["altitude_m"]
            raider.popup_t = row["popup_t"]
            self.raiders.append(raider)
        self.target = None
        self.selected_contact = None
        self.torpedoes = []
        self.enemy_torpedoes = []
        self.warships = []
        self.warship_anchor = None
        # Schadenszustand (Phase 2: repair_mult wiederherstellen)
        dmg = data["damage"]
        self.damage = DamageModel(random.Random(seed + 777),
                                  repair_mult=dmg["repair_mult"])
        for k, c in dmg["compartments"].items():
            self.damage.compartments[k].state = c["state"]
            self.damage.compartments[k].flood = c["flood"]
            self.damage.compartments[k].fire = c["fire"]
            self.damage.compartments[k].hole_m2 = c["hole_m2"]
            self.damage.compartments[k].heat_s = c["heat_s"]
            self.damage.compartments[k].shorted = c["shorted"]
            if k in self.damage.counterflood:
                self.damage.counterflood[k] = c["counterflood"]
        self.damage.teams.update({int(k): v for k, v in dmg["teams"].items()})
        self.damage.team_position.update(
            {int(k): v for k, v in dmg["team_position"].items()})
        self.damage.team_eta.update({int(k): v for k, v in dmg["team_eta"].items()})
        self.damage.patch_kits = dmg["patch_kits"]
        self.damage.cooked_off = dmg["cooked_off"]
        self.damage.capsized = dmg["capsized"]
        self.damage.draft_m = dmg["draft_m"]
        self.damage.total = sum(c.flood for c in self.damage.compartments.values())
        self.damage.ship_sunk = (self.damage.capsized or self.damage.flood_mass_kg()
                                 >= damage_physics.RESERVE_BUOYANCY_KG)
        # M10–M16
        self.sonar_mode = data["sonar_mode"]
        self.sonar_harmonic_hz = None
        # Operator LOFAR/DEMON tools: cursor, marks, integration (UI only).
        self.sonar_tools = analysis_tools.AcousticToolState()
        # Operator TMA hypotheses per sonar target (transient UI state).
        self.tma_hypotheses = {}
        # Shared operator plot layer (chart marks, rulers, bearing lines...).
        self.plot = PlotLayer()
        self._reset_plot_ui()
        self._restore_sonar_controls(data["sonar_controls"])
        radars = data["radars"]
        self.surface_radar_on = radars["surface"]
        self.air_radar_on = radars["air"]
        self.opz_range_nm = radars["range_nm"]
        self.radar_scan_phase = radars["scan_phase"]
        self.radar_scan_pending_deg = radars["scan_pending_deg"]
        self.roe = data["roe"]
        self.asm_spawned = data["asm_spawned"]
        self.air_threat_reported = data["air_threat_reported"]
        self.vls_cells = data["vls_cells"]
        self.ciws_ammo = data["ciws_ammo"]
        self.ciws_cooldown_s = data["ciws_cooldown_s"]
        self.ciws_mount_deg = data["ciws_mount_deg"]
        self.chaff_clouds = [chaff_physics.ChaffCloud(**row)
                             for row in data["chaff_clouds"]]
        self.chaff_seq = data["chaff_seq"]
        self.air_picture = TrackPicture(
            config.RADAR_TRACK_STALE_S, maximum=MAX_AIR_PICTURE_TRACKS)
        self.air_picture.restore(data["air_picture"])
        self.ais = AISReceiver(data["seed"])
        self.ais.restore(data["ais"])
        self.plot = PlotLayer.from_save(data["plot"])
        self._reset_plot_ui()
        self.route = Route.restore(data["route"])
        self._raider_visible_last = any(
            track.track_id.startswith("R-")
            for track in self.air_picture.tracks(self.sim_t, ("FLG", "ASM")))
        self.opz_affiliations = dict(data["opz_affiliations"])
        self.opz_track_labels = {}
        self.opz_selected_track_id = None
        self.opz_fusion.clear()
        self._opz_source_bindings = {}
        self.esm_picture = ESMPicture()
        self.ecm_jammer = ECMJammer()
        self.eloka_selected_track_key = None
        self.eloka_annotations = {}
        esm = data["esm"]
        self.esm_picture.restore(esm["picture"], esm["track_seq"], self.sim_t)
        self.ecm_jammer.restore(esm["ecm"], {
            track.track_key for track in self.esm_picture.tracks(self.sim_t)},
            self.sim_t)
        self.eloka_selected_track_key = esm["selected_track_key"]
        self.eloka_annotations = {
            row["track_key"]: row["emitter_key"]
            for row in esm["annotations"]
        }
        self.radio_picture = TrackPicture(300.0)
        self.radio_picture.restore(data["radio_picture"])
        self.radio_sel = data["radio_sel"]
        self.hfdf_log = list(data["hfdf_log"])
        self.hfdf_fixes = dict(data["hfdf_fixes"])
        schedulers = data["schedulers"]
        self._sensor_acc = schedulers["sensor"]
        self._esm_acc = schedulers["esm"]
        self._radio_acc = schedulers["radio"]
        self._slow_acc = schedulers["slow"]
        self.torpedo_seq = data["torpedo_seq"]
        self.messages = [tuple(m) for m in data["messages"]]
        self._reset_lookout_reports()
        self.buoys = []
        self.buoy_seq = data["buoy_seq"]
        self.helo_buoy_mode = "PASSIVE"
        self.helo_sensor_source = "DIP"
        self.helo_listen_source = "DIP"
        self.helo_listen_bearing = None
        self.helo_audio_enabled = True
        self.helo_audio_band = "FULL"
        self.helo_acoustic_page = 1
        self.helo_audition = SonarSystem(seed=self.seed + 45678, acoustic_profiles=())
        self.helo_receiver = AcousticReceiver(seed=seed + 45677)
        self.helo_spectra = []
        self.helo_broadband_history = []
        self.helo_demon_history = []
        self._helo_receiver_timer = 0.0
        self.asms = []
        self.essms = []
        self.chaff_cd = data["chaff_cd"]
        self.dmg_cursor = data["dmg_cursor"]
        self.dmg_team = data["dmg_team"]
        self.asm_sel = data["asm_sel"]
        self.hq_timer = data["hq_timer"]
        self.rng_asm = random.Random(seed + 31337)
        self.rng_asw = random.Random(seed + 27182)
        self._joy_acc = 0.0
        self._joy_x_acc = 0.0
        self._joy_turn = 0
        hd = data["helo"]
        helo_profile_key = hd["torpedo_profile_key"]
        self.helo = Helicopter(
            random.Random(seed + 555),
            self.runtime_catalog.torpedoes[helo_profile_key])
        self.helo.state = hd["state"]
        self.helo.x, self.helo.y = hd["x"], hd["y"]
        self.helo.course = hd["course"]
        self.helo.torps = hd["torps"]
        self.helo.buoys_left = hd["buoys_left"]
        self.helo.fuel_s = hd["fuel_s"]
        self.helo.waypoint_x = hd["waypoint_x"]
        self.helo.waypoint_y = hd["waypoint_y"]
        self.helo.dip_state = hd["dip_state"]
        self.helo.dip_depth_m = hd["dip_depth_m"]
        self.helo.dip_depth_target_m = hd["dip_depth_target_m"]
        self.helo.dip_water_depth_m = hd["dip_water_depth_m"]
        self.helo.dip_ping_cooldown = hd["dip_ping_cooldown"]
        self.helo.hover_x, self.helo.hover_y = hd["hover_x"], hd["hover_y"]
        self.helo.pattern = hd["pattern"]
        self.helo.pattern_queue = [tuple(point) for point in hd["pattern_queue"]]
        self.helo.mad_mode = hd["mad_mode"]
        self.helo.radar_on = hd["radar_on"]
        # U-Boote (Phase 2: vollstaendiger KI-Zustand)
        self.subs = []
        for sd in data["subs"]:
            sub_profile = self.runtime_catalog.subs[sd["stype"]]
            decoy_profile = self.runtime_catalog.decoys[
                self.runtime_catalog.runtime_bindings["submarine_decoy"]]
            enemy_torpedo_profile = self.runtime_catalog.torpedoes[
                self.runtime_catalog.runtime_bindings["enemy_torpedo"]]
            s = restore_entity(Sub, sd["x"], sd["y"], depth_m=sd["depth"], course_deg=sd["course"],
                    stype_key=sd["stype"], rng=rng, profile=sub_profile,
                    decoy_profile=decoy_profile,
                    enemy_torpedo_profile=enemy_torpedo_profile,
                    side=sd["platform"]["side"],
                    runtime_catalog=self.runtime_catalog, asw_rng=self.rng_asw)
            s.id = sd["id"]
            s.start_pos = tuple(sd["start_pos"])
            s.state = sd["state"]
            s.speed = sd["speed"]
            s.damage = sd["damage"]
            s.torpedoes_left = sd["torpedoes_left"]
            if sd["asw_battery"] is not None:
                s.weapon_battery = WeaponBattery.restore(sd["asw_battery"])
            if sd["countermeasure_store"] is not None:
                s.countermeasure_store = ConsumableStore.restore(
                    sd["countermeasure_store"])
            s.heard_ping = sd["heard_ping"]
            s.evac_left = sd["evac_left"]
            s.sink_left = sd["sink_left"]
            s.sunk = sd["state"] == "SUNK"
            s.quiet_mult = sd["quiet_mult"]
            s.attack_mult = sd["attack_mult"]
            s.attack_cooldown = sd["attack_cooldown"]
            s.attack_left = sd["attack_left"]
            s.solution_threshold = sd["solution_threshold"]
            s.torpedo_alerted = sd["torpedo_alerted"]
            s._decoy_cd = sd["decoy_cd"]
            s._active_ping_cd = sd["active_ping_cd"]
            s.radar_hold_s = sd["radar_hold_s"]
            s.speed_order = sd["speed_order"]
            s.tma_track = BearingTrack()
            s.tma_track.pts = [BearingPoint(p["t"], p["bearing"], p["fx"], p["fy"],
                                            p["fcourse"], p["uncertainty_deg"],
                                            None, p["fspeed"])
                               for p in sd["tma_track"]]
            s.tma_track.version = len(s.tma_track.pts)
            s.tma_track_id = sd["tma_track_id"]
            s.tma_next_t = sd["tma_next_t"]
            s.torpedo_alarm_left = sd["torpedo_alarm_left"]
            s._last_actual_speed = s.speed
            s.blow_available = sd["blow_available"]
            s.emergency_ascent = sd["emergency_ascent"]
            s.transient_left = sd["transient_left"]
            s.flood_noise_left = sd["flood_noise_left"]
            s.flood_quiet = sd["flood_quiet"]
            s.flood_seq = sd["flood_seq"]
            s.ai_tube_left = sd["ai_tube_left"]
            s.ai_fire_pending = sd["ai_fire_pending"]
            s.hull_fatigue = sd["hull_fatigue"]
            s.turn_left = sd["turn_left"]
            s.turn_delta = sd["turn_delta"]
            s.target_course = sd["target_course"]
            s.target_depth = sd["target_depth"]
            s.depth_rate_mps = sd["depth_rate_mps"]
            s.evade_offset = sd["evade_offset"]
            s.sensor_seed = sd["sensor_seed"]
            s.fingerprint = fingerprint_mod.Fingerprint.from_dict(
                sd["fingerprint"])
            restore_platform(s, sd, sd["stype"])
            s.memory.update(sd["memory"])
            for age in ("last_ping_age", "last_torpedo_age"):
                if s.memory[age] is None:
                    s.memory[age] = float("inf")
            s.pending_torpedoes = [tuple(row) for row in sd["pending_torpedoes"]]
            s.pending_decoys = [tuple(row) for row in sd["pending_decoys"]]
            s.decision_reason = sd["decision_reason"]
            s.manual = sd["manual"]
            s.order_course = sd["order_course"]
            s.order_speed = sd["order_speed"]
            s.order_depth = sd["order_depth"]
            s.last_bottom_m = sd["last_bottom_m"]
            s._manual_ping_pending = sd["manual_ping_pending"]
            s.ballast = BoatBallast.restore(sd["ballast"])
            s.damage_control = BoatDamageControl.restore(sd["damage_control"])
            endurance_profile = self.runtime_catalog.endurances.get(
                f"endurance.{sd['stype']}")
            s.endurance = (None if endurance_profile is None else
                            SubmarineEndurance.restore(
                                endurance_profile, sd["endurance"]))
            self.subs.append(s)
        # Tiere
        self.animals = []
        for ad in data["animals"]:
            a = restore_entity(
                Animal, ad["x"], ad["y"], ad["atype"], rng=rng,
                depth_m=ad["depth"],
                profile=self.runtime_catalog.animals[ad["atype"]])
            a.id = ad["id"]
            a.course = ad["course"]
            a.speed = ad["speed"]
            a.dead = ad["dead"]
            a.turn_left = ad["turn_left"]
            a.turn_delta = ad["turn_delta"]
            a.target_course = ad["target_course"]
            a.target_depth = ad["target_depth"]
            a.sensor_seed = ad["sensor_seed"]
            self.animals.append(a)
        # Zivile
        self.civilians = []
        for cd in data["civilians"]:
            prof = self.runtime_catalog.surfaces[cd["signature_key"]]
            c = restore_entity(
                SurfaceShip, cd["x"], cd["y"], rng=rng, profile=prof,
                side=cd["platform"]["side"],
                doctrine=cd["platform"]["doctrine"],
                runtime_catalog=self.runtime_catalog)
            c.id = cd["id"]
            c.course = cd["course"]
            c.speed = cd["speed"]
            c.depth = cd["depth"]
            c.name = cd["name"]
            c.sunk = cd["sunk"]
            c.damage = cd["damage"]
            c.emitter = cd["emitter"]
            c.turn_left = cd["turn_left"]
            c.turn_delta = cd["turn_delta"]
            c.target_course = cd["target_course"]
            c.target_speed = cd["target_speed"]
            c.orbit_direction = cd["orbit_direction"]
            c.sensor_contact = (tuple(cd["sensor_contact"])
                                if cd["sensor_contact"] is not None else None)
            c.sensor_contact_age = cd["sensor_contact_age"]
            c.sunk_score_awarded = cd["sunk_score_awarded"]
            c._torpedo_evade_left = cd["torpedo_evade_left"]
            c._torpedo_threat_bearing = cd["torpedo_threat_bearing"]
            c.sensor_seed = cd["sensor_seed"]
            c.fingerprint = fingerprint_mod.Fingerprint.from_dict(
                cd["fingerprint"])
            restore_platform(c, cd, c.signature_key)
            self.civilians.append(c)
        # KAMPFSCHIFF: feindliche Kriegsschiffe (v4)
        self.warships = []
        for wd in data["warships"]:
            prof = self.runtime_catalog.surfaces[wd["signature_key"]]
            w = restore_entity(
                SurfaceShip, wd["x"], wd["y"], rng=rng,
                side=wd["platform"]["side"],
                doctrine=wd["platform"]["doctrine"],
                profile=prof, runtime_catalog=self.runtime_catalog)
            w.id = wd["id"]
            w.course = wd["course"]
            w.speed = wd["speed"]
            w.name = wd["name"]
            w.sunk = wd["sunk"]
            w.damage = wd["damage"]
            w.emitter = wd["emitter"]
            w.turn_left = wd["turn_left"]
            w.turn_delta = wd["turn_delta"]
            w.target_course = wd["target_course"]
            w.target_speed = wd["target_speed"]
            w.waypoint = (tuple(wd["waypoint"])
                          if wd["waypoint"] is not None else None)
            w.orbit_direction = wd["orbit_direction"]
            w.sensor_contact = (tuple(wd["sensor_contact"])
                                if wd["sensor_contact"] is not None else None)
            w.sensor_contact_age = wd["sensor_contact_age"]
            w.sunk_score_awarded = wd["sunk_score_awarded"]
            w._torpedo_evade_left = wd["torpedo_evade_left"]
            w.countermeasures_left = wd["countermeasures_left"]
            w._torpedo_threat_bearing = wd["torpedo_threat_bearing"]
            w.pending_asm = [tuple(row) for row in wd["pending_asm"]]
            if wd["asroc_battery"] is not None:
                w.asroc_battery = WeaponBattery.restore(wd["asroc_battery"])
            w.pending_asroc = [dict(row) for row in wd["pending_asroc"]]
            w.asw_last_seen = wd["asw_last_seen"]
            w.sensor_seed = wd["sensor_seed"]
            w.attack_left = wd["attack_left"]
            w.anchor = tuple(wd["anchor"]) if wd["anchor"] is not None else None
            w.fingerprint = fingerprint_mod.Fingerprint.from_dict(
                wd["fingerprint"])
            restore_platform(w, wd, w.signature_key)
            self.warships.append(w)
        # W2: Dekoys
        self.decoys = []
        for dd in data["decoys"]:
            decoy_key = dd["profile_key"]
            decoy_profile = self.runtime_catalog.decoys[decoy_key]
            d = restore_entity(
                Decoy, dd["x"], dd["y"], dd["depth"], rng,
                decoy_profile, self.runtime_catalog.acoustic_for(decoy_key),
                source_id=dd["source_id"])
            d.id = dd["id"]
            d.course = dd["course"]
            d.speed = dd["speed"]
            d.life = dd["life"]
            d.dead = False
            d.sensor_seed = dd["sensor_seed"]
            self.decoys.append(d)
        # Phase 2: laufende Entitaeten + Sensoren
        by_id = ({s.id: s for s in self.subs}
                  | {a.id: a for a in self.animals}
                  | {d.id: d for d in self.decoys}
                  | {c.id: c for c in self.civilians}
                  | {w.id: w for w in self.warships})
        for td in data["torpedoes_in_flight"]:
            tgt = by_id.get(td.get("target_id"))
            torpedo_key = td["profile_key"]
            profile = self.runtime_catalog.torpedoes[torpedo_key]
            t = Torpedo(td["x"], td["y"], td["course"],
                        td["target_depth"], tgt,
                        td["idx"],
                        kill_dist_nm=td["kill_dist_nm"],
                        kill_depth_m=td["kill_depth_m"],
                        speed_kn=td["speed_kn"],
                         guidance_x=td["guidance_x"], guidance_y=td["guidance_y"],
                         range_nm=td["range_nm"], profile=profile,
                         launch_origin=td["launch_origin"],
                         launch_platform_id=td["launch_platform_id"],
                         launch_weapon_key=td["launch_weapon_key"],
                         time_since_launch=td["time_since_launch"],
                         pattern=td["pattern"], enable_nm=td["enable_nm"])
            t._turns_done = td["turns_done"]
            t.depth = td["depth"]
            t.travel = td["travel"]
            t.seeker_acquired = td["seeker_acquired"]
            t.terminal_active = td["terminal_active"]
            t.state = td["state"]
            t._search_phase = td["search_phase"]
            t._midcourse = td["midcourse"]
            t._midcourse_timer = td["midcourse_timer"]
            t.energy_s = td["energy_s"]
            t.motor_fraction = td["motor_fraction"]
            t.depth_rate = td["depth_rate"]
            t.wire_ship_out_nm = td["wire_ship_out_nm"]
            t.wire_stress_s = td["wire_stress_s"]
            t.rejected_ids = list(td["rejected_ids"])
            self.torpedoes.append(t)
        for ed in data["enemy_torpedoes"]:
            enemy_key = ed["profile_key"]
            profile = self.runtime_catalog.torpedoes[enemy_key]
            self.enemy_torpedoes.append(
                restore_entity(EnemyTorpedo, ed["x"], ed["y"], ed["course"], ed["depth"],
                                 ed["idx"], profile=profile,
                                 guidance_x=ed["guidance_x"],
                                 guidance_y=ed["guidance_y"],
                                 launch_platform_id=ed["launch_platform_id"],
                                 launch_weapon_key=ed["launch_weapon_key"],
                                 time_since_launch=ed["time_since_launch"]))
            self.enemy_torpedoes[-1].travel = ed["travel"]
            self.enemy_torpedoes[-1].id = ed["id"]
            self.enemy_torpedoes[-1].terminal_active = ed["terminal_active"]
            self.enemy_torpedoes[-1].seeker_acquired = ed["seeker_acquired"]
            self.enemy_torpedoes[-1].energy_s = ed["energy_s"]
            self.enemy_torpedoes[-1].motor_fraction = ed["motor_fraction"]
            self.enemy_torpedoes[-1].depth_rate = ed["depth_rate"]
            self.enemy_torpedoes[-1].target_depth = ed["target_depth"]
            seeker_target = ed["seeker_target"]
            self.enemy_torpedoes[-1]._seeker_target = (
                (self.ship if seeker_target == "ship" else
                 next((item for item in self.nixies
                       if seeker_target == f"nixie:{item.seq}"), None))
                if self.enemy_torpedoes[-1].seeker_acquired else None)
        by_id.update((t.id, t) for t in self.enemy_torpedoes)
        for torpedo, td in zip(self.torpedoes, data["torpedoes_in_flight"]):
            torpedo.target = by_id.get(td.get("target_id"))
            torpedo._seeker_target = torpedo.target if torpedo.seeker_acquired else None
        self.asms = []
        for a in data["asms"]:
            asm = ASM(a["x"], a["y"], a["course"], a["seq"], self.rng_asm,
                      self._air_defense_loadout["asm"])
            asm.state = a["state"]
            asm.jammer = a["jammer"]
            asm.chaff_left = a["chaff_left"]
            asm.broken = a["broken"]
            asm.age_s = a["age_s"]
            asm.travel = a["travel"]
            for key in ("speed_kn", "boosting", "altitude_m", "datum_x", "datum_y",
                        "lock_s", "locked", "los_prev", "chaff_cloud"):
                setattr(asm, key, a[key])
            self.asms.append(asm)
        self.warship_asm_seq = data["warship_asm_seq"]
        self.essms = []
        for e in data["essms"]:
            tgt = next((a for a in self.asms if a.seq == e.get("target_id")),
                       None)
            essm = ESSM(e["x"], e["y"], e["course"], tgt, e["seq"],
                         guidance_x=e["guidance_x"],
                         guidance_y=e["guidance_y"],
                         target_id=e["track_target_id"],
                         profile=self._air_defense_loadout["sam"])
            essm.travel = e["travel"]
            essm.state = e["state"]
            essm.seeker_acquired = e["seeker_acquired"]
            essm.los_prev = e["los_prev"]
            self.essms.append(essm)
        self.asm_seq = data["asm_seq"]
        for bd in data["buoys"]:
            b = Sonobuoy(bd["x"], bd["y"], bd["seq"], bd["mode"], owner=bd["owner"])
            b.battery_s = bd["battery_s"]
            b.last_ping_epoch = bd.get("last_ping_epoch", -1)
            self.buoys.append(b)
        if not self.helicopter_audio_ready():
            passive = next((b for b in sorted(self.buoys, key=lambda item: item.seq)
                            if b.active and b.mode == "PASSIVE"), None)
            if passive is not None:
                self.helo_listen_source = f"SB{passive.seq}"
        flight_data = data["flights"]
        bases = {b["id"]: b for b in self.world.coast.airbases}
        restored = []
        for fd in flight_data["items"]:
                base = bases[fd["base_id"]]
                dest = bases.get(fd["dest_id"])
                flight = Flight(fd["kind"], base, dest=dest,
                                loiter_nm=fd["loiter_nm"],
                                 rng=self.flights.rng, seq=fd["seq"],
                                 akey=fd["akey"], catalog=self.runtime_catalog,
                                 side=fd["platform"]["side"],
                                 doctrine=fd["platform"]["doctrine"])
                flight.x = fd["x"]
                flight.y = fd["y"]
                flight.course = fd["course"]
                flight.total_dist = fd["total_dist"]
                flight.traveled = fd["traveled"]
                flight.radar_emitting = fd["radar_emitting"]
                flight.sensor_bearing = fd["sensor_bearing"]
                flight.sensor_age = fd["sensor_age"]
                flight.active = fd["active"]
                restore_platform(flight, fd, flight.akey)
                if fd["waypoints"]:
                    flight.waypoints = [tuple(p) for p in fd["waypoints"]]
                    flight.waypoint_idx = fd["waypoint_idx"]
                restored.append(flight)
        self.flights.flights = restored
        self.flights._seq = flight_data["seq"]
        self.flights._spawn_cd = flight_data["spawn_cd"]
        self._restore_sonar_system(data.get("sonar"), by_id)
        self._restore_crew(data["crew"], by_id)
        self._apply_crew_effects()
        settings = data["weapon_settings"]
        self.torpedo_type = settings["torpedo_type"]
        self.torpedo_pattern = settings["pattern"]
        self.torpedo_enable_nm = settings["enable_nm"]
        self.torpedo_salvo = settings["salvo"]
        self.player_torpedo_battery.preferred_weapon_key = self.torpedo_type
        self._last_tow_state = self.sonar.tow_state
        # Intercepts already audible at save time were announced then.
        self.torpedo_cues = []
        self._torpedo_cues_reported = weakref.WeakKeyDictionary()
        for cue in self.current_torpedo_cues():
            self._torpedo_cues_reported.setdefault(cue["owner"], set()).add(cue["report"])
            self.torpedo_cues.append(dict(cue, serial=id(torpedo)))
        # Phase 2: RNG-Zustaende (deterministischer Fortgang)
        rg = data["rngs"]
        self._restore_rng(rng, rg["world"])
        self._restore_rng(self.world.rng, rg["world_weather"])
        self.world.refresh_weather()
        self._restore_rng(self.rng_asm, rg["asm"])
        self._restore_rng(self.damage.rng, rg["damage"])
        self._restore_rng(self.helo.rng, rg["helo"])
        self._restore_rng(self.sonar.rng, rg["sonar"])
        self._restore_rng(self.flights.rng, rg["flight"])
        self._restore_rng(self.rng_asw, rg["asw"])
        self._restore_rng(self.rng_raid, rg["raid"])
        # Zustand und sichtbarer Bedienfokus
        ui = data.get("ui", {})
        self.station = Station[ui["station"]]
        self.local_side = ui["local_side"]
        self.station_page = 0
        self.running = True
        self.held = set()
        self.msg = ""
        self.msg_until = 0.0
        self.input_mode = None
        self.input_buffer = ""
        self._mission_warnings = set()
        self._open_administration("")
        self._t = 0.0
        self.map_view.scale = ui.get("map_scale", config.MAP_ZOOM_DEFAULT_PX_PER_NM)
        self.map_view.cx = ui.get("map_cx", self.ship.x)
        self.map_view.cy = ui.get("map_cy", self.ship.y)
        self.map_follow = bool(ui.get("map_follow", True))
        self.opz_map_view.scale = ui["opz_map_scale"]
        self.opz_map_view.cx = ui["opz_map_cx"]
        self.opz_map_view.cy = ui["opz_map_cy"]
        self.opz_map_follow = ui["opz_map_follow"]
        self.tooltips_enabled = bool(ui.get("tooltips_enabled", True))
        self.pinned_tooltip = (layout.valid_tooltip(ui.get("pinned_tooltip"))
                               if self.tooltips_enabled else None)
        anchor = ui.get("tooltip_anchor")
        valid_anchor = (isinstance(anchor, list) and len(anchor) == 2
                        and all(isinstance(value, (int, float))
                                and math.isfinite(value) for value in anchor))
        self._tooltip_anchor = (tuple(anchor) if self.pinned_tooltip is not None
                                and valid_anchor else None)
        self.map_view.clamp_center()
        self._configure_opz_map_view()
        self.opz_map_view.clamp_center()
        target_id = ui.get("target_id")
        selected_id = ui.get("selected_contact_id")
        opz_selected_id = ui.get("opz_selected_track_id")
        if isinstance(opz_selected_id, str):
            self.opz_selected_track_id = opz_selected_id
        if target_id is not None:
            self.target = self.sonar.contacts.get(int(target_id))
        if selected_id is not None:
            self.selected_contact = next((c for c in self.sonar.contacts.values()
                                          if c.id == int(selected_id)), None)
        if self.selected_contact is not None and self.sonar.focus_locked:
            self.sonar._listen_target_id = self.selected_contact.target_id
        self.mission_result = data.get("mission_result")
        self.result_reason = data.get("result_reason", "")
        self.game_over = bool(self.damage.ship_sunk) or self.incident \
            or self.mission_result is not None

    def load_game(self, path: str = None) -> bool:
        path = path or config.SAVE_PATH
        if not os.path.exists(path):
            return False
        try:
            data = _read_save_document(path)
        except (OSError, ValueError, RecursionError):
            return False
        return self._load_save_data(data)

    # Static aliases kept for callers and tests (``Game._valid_save_document``).
    _catalog_for_save = staticmethod(catalog_for_save)
    _valid_save_document = staticmethod(valid_save_document)

    def _load_save_data(self, data: dict) -> bool:
        try:
            if (not isinstance(data, dict)
                    or type(data.get("time_scale_idx")) is not int
                    or not 0 <= data["time_scale_idx"] < 6):
                return False
            runtime_catalog = self._catalog_for_save(data)
            # Earlier saves may have been written while accelerated or paused.
            # Keep the save shape, but every accepted game resumes live at 1x.
            ui = data.get("ui")
            if set(data) == SAVE_ROOT_FIELDS and (
                    data["time_scale_idx"] > 0
                    or (isinstance(ui, dict) and ui.get("paused", False) is not False)):
                data = copy.deepcopy(data)
                data["time_scale_idx"] = 0
                if isinstance(data["ui"], dict) and "paused" in data["ui"]:
                    data["ui"]["paused"] = False
        except (KeyError, TypeError, ValueError, OverflowError, RecursionError):
            return False
        if not self._valid_save_document(data, runtime_catalog):
            return False
        if self._sonar_ctx is not self._frigate_sonar:
            raise RuntimeError("load inside a sonar perspective")
        candidate = copy.copy(self)
        candidate.runtime_catalog = runtime_catalog
        # Own workstation copy: a failed restore must not touch the live one.
        candidate._frigate_sonar = copy.copy(self._frigate_sonar)
        candidate._sonar_ctx = candidate._frigate_sonar
        # The crewed boat is a transient binding: a load always drops it.
        candidate._opfor = None
        candidate.held = set(self.held)
        candidate.map_view = copy.copy(self.map_view)
        candidate.opz_map_view = copy.copy(self.opz_map_view)
        candidate.torpedo_cues = list(self.torpedo_cues)
        candidate._torpedo_cues_reported = weakref.WeakKeyDictionary(
            self._torpedo_cues_reported)
        candidate.audio = copy.copy(self.audio)
        candidate.audio.stop_sonar = lambda immediate=False: None
        id_classes = (Sub, Animal, SurfaceShip, Decoy, EnemyTorpedo)
        next_ids = tuple(cls._next_id for cls in id_classes)
        candidate._restore_id_allocations = dict.fromkeys(id_classes, 0)
        restored = False
        try:
            candidate._restore_state(data)
            canonical = candidate.save_state()
            # Constructor allocations are rolled back below; they are not part
            # of the candidate's persisted identity high-water marks.
            canonical["next_entity_ids"] = data["next_entity_ids"]
            if not _same_save_value(canonical, data):
                return False
            restored = True
        except Exception:
            return False
        finally:
            groups = (("sub", candidate.subs), ("animal", candidate.animals),
                      ("surface", candidate.civilians + candidate.warships),
                      ("decoy", candidate.decoys),
                      ("enemy_torpedo", candidate.enemy_torpedoes))
            for cls, baseline, (key, entities) in zip(id_classes, next_ids, groups):
                current = cls._next_id
                # Never rewind another instance's allocations. Remove only a
                # contiguous run known to consist solely of restoration IDs.
                if current == baseline + candidate._restore_id_allocations[cls]:
                    current = baseline
                if restored:
                    current = max(current, data["next_entity_ids"][key],
                                  max((entity.id + 1 for entity in entities), default=1))
                cls._next_id = current
            del candidate._restore_id_allocations
        candidate.audio = self.audio
        self.__dict__.update(candidate.__dict__)
        if self._opfor is not None:
            # The crew of the loaded boat is not connected yet: keep the
            # binding for the hold so the returning crew resumes its orders.
            self._opfor_hold_s = max(self._opfor_hold_s, config.UBOOT_RESTORE_HOLD_S)
        self.in_menu = False
        self.main_menu = False
        self.feed.clear()
        self._reset_debrief()
        self._restore_training()
        # The load itself took wall time; it is not simulation time to catch up.
        self._frame_clock_reset = True
        return True

    # --- W4: Save-Slots 1-5 ---

    def save_to_slot(self, slot: int) -> None:
        if type(slot) is not int or not 1 <= slot <= 5:
            raise ValueError("slot must be an integer from 1 to 5")
        path = os.path.join(config.SAVE_DIR, f"slot{slot}.json")
        self.save_game(path)
        self.announce(message("status.save_feed", slot=slot), "mission", 2.0)

    def load_from_slot(self, slot: int) -> bool:
        if type(slot) is not int or not 1 <= slot <= 5:
            raise ValueError("slot must be an integer from 1 to 5")
        path = os.path.join(config.SAVE_DIR, f"slot{slot}.json")
        if not os.path.exists(path):
            return False
        try:
            data = _read_save_document(path)
        except (OSError, ValueError, RecursionError):
            return False
        if not self._load_save_data(data):
            return False
        self.announce(message("status.loaded", slot=slot), "mission", 2.0)
        return True

    # --- W4: Hauptmenü (Szenario -> [Level] -> Briefing) ---

    def _opz_map_save_values(self):
        """Return a canonical camera snapshot without mutating live UI state."""
        view = copy.copy(self.opz_map_view)
        chart = pygame.Rect(opz_ppi_rect(config.OPZ_STATION_RECT))
        view.world_size = self.world.size_nm
        view.set_rect(tuple(chart))
        view.min_scale = min(chart.w, chart.h) / self.world.size_nm
        view.max_scale = max(view.min_scale, min(chart.w, chart.h) / (
            2.0 * config.OPZ_MAP_MAX_ZOOM_RADIUS_NM))
        view.scale = config.clamp(view.scale, view.min_scale, view.max_scale)
        if self.opz_map_follow:
            view.cx, view.cy = self.ship.x, self.ship.y
        view.clamp_center()
        return view
