"""The operator-facing pictures of the game: OPZ observations, tracks, fusion
and affiliation, the shared plot layer, ELOKA analysis, weather and lookout
reports, and the SimLog history (``Game`` mixin). Views consume these; none
of them discovers hidden entity state.

Verbatim moves from ``game.py`` (plan 1.3, phase 2, step 4b)."""

import hashlib
import math
from dataclasses import replace

import pygame

from src.core import callouts, config
from src.core import plot as plot_geometry
from src.core.i18n import display_value, message, raw_text
from src.core.station import Station
from src.core.limits import MAX_OPZ_TRACK_LABELS, MAX_TRACK_DISPLAY_ID_LEN
from src.sensors import visual as visual_physics
from src.sensors import lookout_id
from src.world import atmosphere as atmosphere_physics
from src.world import ocean as ocean_physics
from src.sonar import raytrace as sonar_raytrace
from src.sensors.fusion import (OPZObservation, live_members, source_classification,
                                suggest_correlations, suggestion_key)
from src.sensors.esm import (
    ESM_MAX_ANNOTATIONS,
    ESMCorrelationEvidence,
    ECM_TECHNIQUES,
    analyze_signal,
    correlate_observations,
    estimated_range_nm,
    filter_and_sort_tracks,
    library_emitters,
    rank_emitters)
from src.sonar.sonar import Contact
from src.air import helicopter as helicopter_physics
# Shared display/help constants and helpers (re-exported for tests/tools).
# Names tests and tools import from ``src.core.game`` (kept as re-exports).


class PicturesMixin:
    """Picture half of ``Game``: what the stations and browsers are shown."""

    def radar_tracks(self) -> list:
        """Compatibility view of the persistent surface/air picture."""
        tracks = []
        for t in self.air_picture.tracks(self.sim_t):
            if "AIS" in t.source.upper():
                continue
            derived_course, derived_speed = t.derived_motion()
            tracks.append(dict(
                kind=t.kind, track_id=t.track_id, target_id=t.target_id,
                source=t.source, dist=t.range_nm, bearing=t.bearing,
                x=t.x, y=t.y,
                course=t.course if t.course is not None else derived_course,
                speed_kn=derived_speed,
                quality=t.display_quality(self.sim_t, self.air_picture.stale_s),
                label=self.opz_track_label(
                    self._opz_observation_id("picture", t.track_id),
                    self._opz_observation_id("picture", t.track_id)[-6:]),
                hostile=t.hostile, jamming=t.jamming,
                age=t.age(self.sim_t), position_seen=t.position_seen,
                bearing_uncertainty_deg=t.bearing_uncertainty_deg,
                altitude_m=t.altitude_m,
                visual=t.label if t.source == "LOOKOUT" else None))
        return tracks

    def _opz_observation_id(self, namespace: str, identity: object) -> str:
        return "O-" + self._observation_key("opz-" + namespace, identity)

    def opz_track_label(self, observation_id: str, fallback: str) -> str:
        """Return the one shared, operator-visible ID for an observation."""
        return self.opz_track_labels.get(observation_id, fallback)

    def contact_display_id(self, contact: Contact) -> str:
        if self._sonar_ctx is not self._frigate_sonar:
            # A crewed boat's contacts never carry frigate OPZ labels.
            return f"K{contact.id:02d}"
        observation_id = self._opz_observation_id("sonar", contact.target_id)
        return self.opz_track_label(observation_id, f"K{contact.id:02d}")

    def set_opz_track_label(self, observation_id: str, label: str):
        """Assign an OPZ-authored display ID without changing track identity."""
        if self.damage.station_down("opz"):
            return "opz_down"
        if (type(label) is not str or not 1 <= len(label) <= MAX_TRACK_DISPLAY_ID_LEN
                or not label.isascii()
                or any(not (char.isalnum() or char == "-") for char in label)
                or not any(char.isalnum() for char in label)):
            return "invalid_value"
        current = {item.observation_id for item in self.opz_published_observations()}
        if observation_id not in current:
            return "stale_ref"
        if (observation_id not in self.opz_track_labels
                and len(self.opz_track_labels) >= MAX_OPZ_TRACK_LABELS):
            del self.opz_track_labels[next(iter(self.opz_track_labels))]
        self.opz_track_labels[observation_id] = label.upper()
        return True

    def _detached_air_observations(self) -> list[OPZObservation]:
        observations = []
        bindings = {}
        for track in self.air_picture.tracks(self.sim_t):
            # Sonar owns its release policy and detached report identity. Legacy
            # save-backed mirrors are never consumed as OPZ source reports.
            if track.source.startswith("SONAR") or "AIS" in track.source.upper():
                continue
            observation_id = self._opz_observation_id("picture", track.track_id)
            classification = (self.opz_fusion.classifications.get(observation_id)
                              if (track.source.startswith("RADAR")
                                  or track.source == "HOJ")
                              else self.released_esm_labels().get(track.track_id)
                              if track.source == "ESM" else None)
            kind = "UNKNOWN" if track.source == "ESM" else track.kind
            derived_course, derived_speed = track.derived_motion()
            observation = OPZObservation(
                observation_id, track.source, kind, track.bearing, track.range_nm,
                track.x, track.y,
                track.course if track.course is not None else derived_course,
                track.quality, track.last_seen,
                self.opz_track_label(observation_id, observation_id[-6:]), classification,
                track.bearing_uncertainty_deg, track.position_seen, track.jamming,
                speed_kn=derived_speed, altitude_m=track.altitude_m,
                visual=track.label if track.source == "LOOKOUT" else None)
            observations.append(observation)
            bindings[observation_id] = track
        self._opz_source_bindings = bindings
        return observations

    def _ais_opz_observations(self) -> list[OPZObservation]:
        """Received AIS reports as OPZ reports: the reported position
        dead-reckoned to now, reported course and speed and the ship's name
        once its static message is in. A report is what the ship broadcast,
        never its live state; stale dynamic data drops out."""
        observations = []
        for target_id in sorted(self.ais.reports):
            report = self.ais.reports[target_id]
            if not self.ais.fresh(report, self.sim_t):
                continue
            x, y = self.ais.position_for(report, self.sim_t)
            dx, dy = x - self.ship.x, y - self.ship.y
            observation_id = self._opz_observation_id("ais", target_id)
            fallback = "AIS-" + observation_id[-4:]
            observations.append(OPZObservation(
                observation_id, "AIS", "SURFACE",
                math.degrees(math.atan2(dx, -dy)) % 360.0, math.hypot(dx, dy), x, y,
                report.cog, config.AIS_OPZ_QUALITY, report.t_dynamic,
                self.opz_track_label(observation_id, (report.name or fallback)[:24]),
                self.opz_fusion.classifications.get(observation_id),
                config.AIS_OPZ_BEARING_UNC_DEG, report.t_dynamic,
                speed_kn=report.sog))
            self._opz_source_bindings[observation_id] = report
        return observations

    def _sonar_opz_observations(self, released_only: bool) -> list[OPZObservation]:
        """Return detached Sonar reports without carrying contact identity."""
        observations = []
        for _, contact in sorted(self.sonar.contacts.items()):
            if ((released_only and not contact.released_to_opz)
                    or not 0.0 <= self.sim_t - contact.last_seen
                    < config.SONAR_CONTACT_LOST_S):
                continue
            observation_id = self._opz_observation_id("sonar", contact.target_id)
            fixes = tuple(fix for fix in contact.active_fixes(self.sim_t)
                          if fix["source"] not in ("DIPPING", "SONOBUOY"))
            ship_passive_seen = (contact._bearing_filter_t
                                 if contact._bearing_filter_t is not None
                                 else contact.last_seen)
            ship_passive_current = (contact.passive_bearing is not None
                                    and 0 <= self.sim_t - ship_passive_seen
                                    < config.SONAR_CONTACT_LOST_S)
            if released_only and not ship_passive_current and not fixes:
                continue
            fix_by_source = {item["source"]: item for item in fixes}
            fix = max(fixes, key=lambda item: (item["fixed_at"], item["source"])) \
                if fixes else None
            x = fix["x"] if fix is not None else None
            y = fix["y"] if fix is not None else None
            observer_x = (contact.ship_observer_x
                          if ship_passive_current and contact.ship_observer_x is not None
                          else self.ship.x if ship_passive_current
                          else contact.observer_x)
            observer_y = (contact.ship_observer_y
                          if ship_passive_current and contact.ship_observer_y is not None
                          else self.ship.y if ship_passive_current
                          else contact.observer_y)
            bearing_uncertainty_deg = contact.bearing_uncertainty_deg
            if x is not None and y is not None:
                dx, dy = x - self.ship.x, y - self.ship.y
                bearing = math.degrees(math.atan2(dx, -dy)) % 360.0
                range_nm = math.hypot(dx, dy)
                source = "SONAR-" + fix["source"]
            elif ship_passive_current:
                bearing = contact.passive_bearing
                range_nm = None
                source = contact.passive_source
            elif not released_only and contact.dip_bearing is not None:
                bearing = contact.dip_bearing
                range_nm = None
                source = "SONAR-DIP-BRG"
                observer_x, observer_y = contact.dip_observer_x, contact.dip_observer_y
                bearing_uncertainty_deg = contact.dip_bearing_uncertainty_deg
            else:
                continue
            course = contact.tma_course if "TMA" in fix_by_source else None
            speed = contact.tma_speed if "TMA" in fix_by_source else None
            depth = (contact.depth_est
                     if "PING" in fix_by_source or "DIPPING" in fix_by_source
                     else None)
            observation = OPZObservation(
                observation_id, source, "UNKNOWN", bearing, range_nm, x, y, course,
                max(contact.quality, contact.confidence),
                (fix["measured_at"] if fix is not None
                 else ship_passive_seen if ship_passive_current
                 else contact.last_seen),
                self.opz_track_label(observation_id, f"K{contact.id:02d}"), (contact.player_class
                                      if contact.player_class in config.PLAYER_CLASSES
                                      else None),
                bearing_uncertainty_deg,
                fix["measured_at"] if fix is not None else None,
                depth_m=depth, speed_kn=speed,
                observer_x=observer_x, observer_y=observer_y,
                released_to_opz=contact.released_to_opz)
            observations.append(observation)
            self._opz_source_bindings[observation_id] = contact
        return observations

    def private_sonar_observations(self) -> tuple[OPZObservation, ...]:
        """Fresh private acoustic reports for role-specific projections."""
        return tuple((*self._sonar_opz_observations(False),
                      *self._buoy_opz_observations(released_only=False)))

    def _helicopter_opz_observations(self) -> list[OPZObservation]:
        """The helicopter's separately released, measured dip reports."""
        reports = []
        for _, contact in sorted(self.sonar.contacts.items()):
            if not contact.dip_released_to_opz:
                continue
            passive = (contact.dip_bearing is not None
                       and contact.dip_last_seen is not None
                       and 0 <= self.sim_t - contact.dip_last_seen
                       < config.SONAR_CONTACT_LOST_S)
            fixes = [fix for fix in contact.active_fixes(self.sim_t)
                     if fix["source"] in ("DIPPING", "MAD")]
            fix = max(fixes, key=lambda item: item["fixed_at"]) if fixes else None
            if not passive and fix is None:
                continue
            origin_x = contact.dip_observer_x if passive else contact.observer_x
            origin_y = contact.dip_observer_y if passive else contact.observer_y
            bearing = (contact.dip_bearing if passive else math.degrees(
                math.atan2(fix["x"] - origin_x, -(fix["y"] - origin_y))) % 360.0)
            range_nm = (None if passive else math.hypot(
                fix["x"] - origin_x, fix["y"] - origin_y))
            observation_id = self._opz_observation_id("sonar-dip", contact.target_id)
            reports.append(OPZObservation(
                observation_id,
                "SONAR-DIP-BRG" if passive else (
                    "HELO-MAD" if fix["source"] == "MAD" else "SONAR-DIPPING"),
                "UNKNOWN", bearing, range_nm,
                None if passive else fix["x"],
                None if passive else fix["y"], None,
                max(contact.quality, contact.confidence),
                max(contact.dip_last_seen if passive else 0.0,
                    fix["measured_at"] if fix is not None else 0.0),
                self.opz_track_label(observation_id, f"K{contact.id:02d} H"),
                contact.player_class if contact.player_class in config.PLAYER_CLASSES
                else None,
                contact.dip_bearing_uncertainty_deg if passive else None,
                fix["measured_at"] if not passive else None,
                depth_m=fix["depth_m"] if not passive else None,
                observer_x=origin_x, observer_y=origin_y,
                released_to_opz=True))
            self._opz_source_bindings[observation_id] = contact
        return reports

    def _buoy_opz_observations(self, released_only=True) -> list[OPZObservation]:
        reports = []
        for _, contact in sorted(self.sonar.contacts.items()):
            if released_only and (not contact.helo_qualified
                                  or not contact.buoy_released_to_opz):
                continue
            for seq, row in sorted(contact.buoy_reports.items()):
                if not 0 <= self.sim_t - row["measured_at"] < config.SONAR_CONTACT_LOST_S:
                    continue
                observation_id = self._opz_observation_id(
                    f"sonar-buoy-{seq}", contact.target_id)
                reports.append(OPZObservation(
                    observation_id, f"SONAR-BUOY-{seq:02d}-{row['mode']}", "UNKNOWN",
                    row["bearing"], row["range_nm"], row["x"], row["y"],
                    None, row["quality"], row["measured_at"],
                    self.opz_track_label(observation_id, f"B{seq:02d} K{contact.id:02d}"),
                    contact.player_class, row["bearing_uncertainty_deg"],
                    row["measured_at"] if row["x"] is not None else None,
                    observer_x=row["observer_x"], observer_y=row["observer_y"],
                    released_to_opz=bool(contact.helo_qualified
                                         and contact.buoy_released_to_opz)))
                self._opz_source_bindings[observation_id] = contact
        return reports

    def opz_source_observations(self) -> tuple[OPZObservation, ...]:
        if id(self.world) != self._opz_world_identity:
            self.opz_fusion.clear()
            self.opz_track_labels.clear()
            self.opz_selected_track_id = None
            self._opz_world_identity = id(self.world)
        observations = self._detached_air_observations()
        observations.extend(self._sonar_opz_observations(True))
        observations.extend(self._helicopter_opz_observations())
        observations.extend(self._buoy_opz_observations())
        observations.extend(self._ais_opz_observations())
        return tuple(sorted(observations, key=lambda item: item.observation_id))

    def opz_published_observations(self) -> tuple[OPZObservation, ...]:
        """Shared OPZ picture, unaffected by host-local suppression."""
        observations = self.opz_source_observations()
        self.opz_fusion.prune(observations)
        fused = [self.opz_fusion.computed(item, observations, self.sim_t,
                                          self.air_picture.stale_s)
                 for item in self.opz_fusion.fusions.values()]
        fused = [replace(item, label=self.opz_track_label(
            item.observation_id, item.label)) for item in fused if item is not None]
        return tuple(sorted((*observations, *(item for item in fused if item is not None)),
                            key=lambda item: item.observation_id))

    def asm_tracks(self) -> list:
        return [t for t in self.air_picture.tracks(self.sim_t, ("ASM",))
                if t.source in ("RADAR", "RADAR-L", "HOJ", "DATALINK")]

    def opz_tracks(self) -> list:
        """Host-visible OPZ reports, with local suppression applied."""
        observations = self.opz_source_observations()
        visible = self.opz_fusion.visible(observations, self.sim_t,
                                          self.air_picture.stale_s)
        return [replace(item, label=self.opz_track_label(
            item.observation_id, item.label)) for item in visible]

    def filtered_opz_tracks(self) -> list:
        """Presentation-only OPZ register filter; never alters observations."""
        tracks = self.opz_tracks()
        selected = getattr(self, "opz_contact_filter", "ALL")
        if selected == "ALL":
            return tracks
        if selected in ("RADAR", "SONAR"):
            return [track for track in tracks
                    if track.source.startswith(selected)]
        if selected == "ESM":
            return [track for track in tracks if track.source == "ESM"]
        kind_domains = {
            "AIS": "SURFACE", "SURFACE": "SURFACE", "SUB": "SUBSURFACE",
            "TORP": "SUBSURFACE", "FLG": "AIR", "ASM": "AIR",
        }
        # Sonar reports carry no sensor domain; the operator's classification
        # (an annotation, not truth) sorts them into the display filter.
        class_domains = {
            "U_BOOT": "SUBSURFACE", "TORPEDO": "SUBSURFACE",
            "KAMPFSCHIFF": "SURFACE", "FAHRZEUG": "SURFACE", "FLUGZEUG": "AIR",
        }
        return [track for track in tracks
                if kind_domains.get(track.kind, class_domains.get(
                    track.classification, "UNKNOWN")) == selected]

    def _cycle_opz_contact_filter(self) -> None:
        filters = ("ALL", "RADAR", "SONAR", "ESM", "AIR", "SURFACE",
                   "SUBSURFACE")
        current = getattr(self, "opz_contact_filter", "ALL")
        index = filters.index(current) if current in filters else 0
        self.opz_contact_filter = filters[(index + 1) % len(filters)]
        tracks = self.filtered_opz_tracks()
        if not any(track.track_id == self.opz_selected_track_id
                   for track in tracks):
            self.opz_selected_track_id = tracks[0].track_id if tracks else None
        self.flash(message(
            "runtime.cic.filter",
            filter=display_value("contact_filter", self.opz_contact_filter,
                                 self.tr)), 1.5)

    # --- Shared operator plot layer ----------------------------------------

    PLOT_TOOL_KEYS = {pygame.K_m: "mark", pygame.K_r: "ruler",
                      pygame.K_b: "bearing", pygame.K_c: "circle",
                      pygame.K_d: "dr"}
    PLOT_CURSOR_STEP_PX = 6
    PLOT_CURSOR_STEP_FAST_PX = 40
    PLOT_PICK_PX = 12

    def _reset_plot_ui(self) -> None:
        """Transient plot-mode state; the drawing itself lives in ``plot``."""
        self.plot_mode = False
        self.plot_tool = "mark"
        self.plot_cursor = (0.0, 0.0)
        self.plot_anchor = None
        self._plot_dr_pending = None

    # ``layer`` selects another crew's plot (the crewed submarine's own);
    # by default the frigate crew's shared plot.
    def plot_add(self, kind, x, y, label="", *, layer=None, **fields):
        """Add one crew drawing at sim time now; returns its id or an error."""
        if kind not in plot_geometry.KINDS:
            return "invalid_value"
        target = self.plot if layer is None else layer
        return target.add({"kind": kind, "label": label,
                           "t": float(self.sim_t), "x": x, "y": y, **fields})

    def plot_remove(self, object_id, *, layer=None):
        return True if (self.plot if layer is None else layer).remove(object_id) else "stale_ref"

    def plot_clear(self, *, layer=None):
        (self.plot if layer is None else layer).clear()
        return True

    def plot_relabel(self, object_id, label, *, layer=None):
        if not plot_geometry.valid_label(label):
            return "invalid_value"
        return True if (self.plot if layer is None else layer).relabel(object_id, label) else "stale_ref"

    def _plot_view(self):
        """The chart camera of the current station, or None without a chart."""
        if self.station is Station.OPZ:
            self._configure_opz_map_view()
            return self.opz_map_view
        if self._map_station_visible():
            self.map_view.set_rect(config.MAP_RECT)
            return self.map_view
        return None

    def toggle_plot_mode(self):
        if self.plot_mode:
            self._reset_plot_ui()
            self.flash(message("plot.flash.off"), 1.5)
            return False
        if self._plot_view() is None:
            self.flash(message("plot.flash.no_chart"), 2.0)
            return None
        self._clear_station_input()
        self.plot_mode = True
        self.plot_anchor = None
        self.plot_cursor = (self.ship.x, self.ship.y)
        self.flash(message("plot.flash.on"), 2.0)
        return True

    def _plot_flash_result(self, result) -> None:
        if isinstance(result, str):
            self.flash(message("plot.flash.full" if result == "full"
                               else "plot.flash.invalid"), 2.0)
        else:
            item = next((obj for obj in self.plot.objects if obj["id"] == result), None)
            if item is not None:
                self.flash(message("plot.flash.added", label=item["label"]), 1.5)

    def _plot_commit_point(self, x=None, y=None) -> None:
        """Enter/click: place the cursor point for the active tool."""
        if x is not None:
            self.plot_cursor = (x, y)
        cx, cy = self.plot_cursor
        tool = self.plot_tool
        if tool == "mark":
            self._plot_flash_result(self.plot_add("mark", cx, cy))
            return
        if tool == "bearing":
            brg, dist = plot_geometry.bearing_distance(self.ship.x, self.ship.y, cx, cy)
            result = (self.plot_add("bearing", self.ship.x, self.ship.y,
                                    bearing=round(brg, 1) % 360.0)
                      if dist > 0.0 else "invalid_value")
            self._plot_flash_result(result)
            return
        if self.plot_anchor is None:
            self.plot_anchor = (cx, cy)
            self.flash(message("plot.flash.second_point"), 2.0)
            return
        ax, ay = self.plot_anchor
        self.plot_anchor = None
        brg, dist = plot_geometry.bearing_distance(ax, ay, cx, cy)
        if tool == "ruler":
            result = self.plot_add("ruler", ax, ay, x2=cx, y2=cy)
        elif tool == "circle":
            result = self.plot_add("circle", ax, ay, radius_nm=round(dist, 2))
        else:
            if dist <= 0.0:
                self._plot_flash_result("invalid_value")
                return
            self._plot_dr_pending = (ax, ay, round(brg, 1) % 360.0)
            self._begin_numeric_input("plot_speed")
            return
        self._plot_flash_result(result)

    def selected_opz_track(self):
        return next((track for track in self.opz_tracks()
                     if track.track_id == self.opz_selected_track_id), None)

    def designate_opz_track(self) -> None:
        """Hand an observed CIC track to weapons without exposing world truth."""
        track = self.selected_opz_track()
        if track is None:
            self.flash(message("runtime.cic.none"))
            return
        result = self.designate_opz_observation(track.observation_id)
        if result is not True:
            ambiguous = (track.source == "FUSION"
                         and len(self._fusion_contacts(track)) > 1)
            self.flash(message("runtime.cic.fusion_ambiguous" if ambiguous
                               else "runtime.cic.no_solution"))
            return
        self.selected_contact = self.target
        self.flash(message("runtime.cic.designated", track=track.track_id))

    def designate_opz_observation(self, observation_id: str):
        if self.damage.station_down("opz"):
            return "opz_down"
        track = next((item for item in self.opz_published_observations()
                      if item.observation_id == observation_id), None)
        if track is None:
            return "stale_ref"
        if track.source == "FUSION":
            # A fusion hands over its sonar report only when that is unique.
            contacts = self._fusion_contacts(track)
            contact = contacts[0] if len(contacts) == 1 else None
        else:
            bound = self._opz_source_bindings.get(track.observation_id)
            contact = (bound if isinstance(bound, Contact) else
                       next((c for c in self.sonar.contacts.values()
                             if getattr(bound, "target_id", None) == c.target_id),
                            None))
        if (contact is None or self.sonar.contacts.get(contact.target_id) is not contact
                or not 0 <= self.sim_t - contact.last_seen
                < config.SONAR_CONTACT_LOST_S):
            return "no_solution"
        self.target = contact
        return True

    def _fusion_contacts(self, track) -> list:
        """Distinct sonar contacts behind the member reports of one fusion."""
        contacts = []
        for member in getattr(track, "members", ()):
            bound = self._opz_source_bindings.get(member)
            if isinstance(bound, Contact) and not any(
                    item is bound for item in contacts):
                contacts.append(bound)
        return contacts

    def opz_affiliation(self, track_id: str) -> str:
        if track_id not in self.opz_affiliations:
            source_key = getattr(self._opz_source_bindings.get(track_id),
                                 "track_id", None)
            bound = self._opz_source_bindings.get(track_id)
            if isinstance(bound, Contact):
                legacy_key = f"U-{bound.target_id}"
                if legacy_key in self.opz_affiliations:
                    track_id = legacy_key
            if source_key in self.opz_affiliations:
                track_id = source_key
            else:
                opaque = next((key for key, source in self._opz_source_bindings.items()
                               if getattr(source, "track_id", None) == track_id), None)
                if opaque is not None:
                    track_id = opaque
        if (track_id not in self.opz_affiliations
                and track_id not in self.opz_fusion.fusion_affiliations):
            # A report inside a fusion carries the fusion's affiliation, so
            # fire control on the underlying track follows the operator's
            # call on the fused contact (an explicit call on the report wins).
            track_id = next((key for key, fusion in sorted(self.opz_fusion.fusions.items())
                             if key in self.opz_fusion.fusion_affiliations
                             and track_id in (live_members(
                                 fusion, self._opz_source_bindings) or ())), track_id)
        value = self.opz_fusion.fusion_affiliations.get(
            track_id, self.opz_affiliations.get(track_id, "UNKNOWN"))
        return value if value in config.NATO_AFFILIATIONS else "UNKNOWN"

    def opz_source_classification(self, observation_id: str) -> str | None:
        return source_classification(observation_id,
                                     self.opz_published_observations())

    def classify_sonar_contact(self, contact, classification):
        if self._sonar_down():
            return "sonar_down"
        if classification is not None and classification not in config.PLAYER_CLASSES:
            return "invalid_value"
        if (not isinstance(contact, Contact)
                or self.sonar.contacts.get(contact.target_id) is not contact):
            return "stale_ref"
        if not 0 <= self.sim_t - contact.last_seen < config.SONAR_CONTACT_LOST_S:
            return "stale_ref"
        contact.player_class = classification
        return True

    def release_sonar_contact(self, contact, released: bool, *, source="sonar"):
        if type(released) is not bool:
            return "invalid_value"
        if source not in ("sonar", "helicopter", "buoy"):
            return "invalid_value"
        if self.damage.station_down("sonar"):
            return "sonar_down"
        if (not isinstance(contact, Contact)
                or self.sonar.contacts.get(contact.target_id) is not contact
                or not 0 <= self.sim_t - contact.last_seen
                < config.SONAR_CONTACT_LOST_S):
            return "stale_ref"
        if source == "helicopter":
            dip_current = (contact.dip_last_seen is not None
                           and 0 <= self.sim_t - contact.dip_last_seen
                           < config.SONAR_CONTACT_LOST_S)
            dip_fix = any(fix["source"] == "DIPPING"
                          for fix in contact.active_fixes(self.sim_t))
            if not dip_current and not dip_fix:
                return "stale_ref"
            if released and not contact.helo_qualified:
                return "not_qualified"
            contact.dip_released_to_opz = released
        elif source == "buoy":
            if not any(0 <= self.sim_t - row["measured_at"] < config.SONAR_CONTACT_LOST_S
                       for row in contact.buoy_reports.values()):
                return "stale_ref"
            if released and not contact.helo_qualified:
                return "not_qualified"
            contact.buoy_released_to_opz = released
        else:
            contact.released_to_opz = released
        return True

    def qualify_helicopter_contact(self, contact, qualified: bool):
        if type(qualified) is not bool:
            return "invalid_value"
        if self.damage.station_down("sonar"):
            return "sonar_down"
        if (not isinstance(contact, Contact)
                or self.sonar.contacts.get(contact.target_id) is not contact
                or not 0 <= self.sim_t - contact.last_seen < config.SONAR_CONTACT_LOST_S):
            return "stale_ref"
        if not (any(0 <= self.sim_t - row["measured_at"]
                    < config.SONAR_CONTACT_LOST_S
                    for row in contact.buoy_reports.values())
                or contact.dip_last_seen is not None
                and 0 <= self.sim_t - contact.dip_last_seen
                < config.SONAR_CONTACT_LOST_S
                or any(fix["source"] == "DIPPING"
                       for fix in contact.active_fixes(self.sim_t))):
            return "stale_ref"
        contact.helo_qualified = qualified
        if not qualified:
            contact.dip_released_to_opz = False
            contact.buoy_released_to_opz = False
        return True

    def classify_opz_observation(self, observation_id: str, classification):
        if self.damage.station_down("opz"):
            return "opz_down"
        if classification is not None and classification not in config.PLAYER_CLASSES:
            return "invalid_value"
        track = next((item for item in self.opz_published_observations()
                      if item.observation_id == observation_id), None)
        if track is None:
            return "stale_ref"
        if track.source.startswith("SONAR"):
            # A sonar-origin contact is classified on the contact itself
            # (shared with the Sonar/Helicopter stations), not in the OPZ
            # fusion overlay used for radar-only tracks.
            contact = self._opz_source_bindings.get(observation_id)
            if (not isinstance(contact, Contact)
                    or self.sonar.contacts.get(contact.target_id) is not contact):
                return "stale_ref"
            return self.classify_sonar_contact(contact, classification)
        if not (track.source.startswith("RADAR")
                or track.source in ("HOJ", "FUSION")):
            return "source_owned"
        if classification is None:
            self.opz_fusion.classifications.pop(observation_id, None)
        else:
            self.opz_fusion.classifications[observation_id] = classification
        return True

    def affiliate_opz_observation(self, observation_id: str, affiliation: str):
        if self.damage.station_down("opz"):
            return "opz_down"
        if affiliation not in config.NATO_AFFILIATIONS:
            return "invalid_value"
        track = next((item for item in self.opz_published_observations()
                      if item.observation_id == observation_id), None)
        if track is None:
            return "stale_ref"
        destination = (self.opz_fusion.fusion_affiliations
                       if track.source == "FUSION" else self.opz_affiliations)
        destination[observation_id] = affiliation
        self._sync_live_engagement_hold(observation_id, track.track_id, affiliation)
        for member in track.members if track.source == "FUSION" else ():
            if member not in self.opz_affiliations:
                self._sync_live_engagement_hold(member, track.label, affiliation)
        return True

    def _live_aircraft_icao_for_track_id(self, track_id) -> str | None:
        """Resolve an air-picture 'A-<seq>' track id to its live ADS-B icao24,
        if that id happens to be bound to a real LiveAircraft rather than a
        simulated Flight (both intentionally share the same id namespace)."""
        if not isinstance(track_id, str) or not track_id.startswith("A-"):
            return None
        try:
            seq = int(track_id[2:])
        except ValueError:
            return None
        return next((icao24 for icao24, aircraft in self.live_traffic.aircraft.items()
                     if aircraft.seq == seq), None)

    def _sync_live_engagement_hold(self, observation_id: str, display_id: str,
                                    affiliation: str) -> None:
        """Real ADS-B traffic is indistinguishable from a simulated contact,
        so a manual HOSTILE call on it is a possible political incident, not
        a weapons release. Any prior engagement confirmation is revoked here
        and must be freshly re-affirmed (confirm_live_engagement) every time
        the classification turns HOSTILE again."""
        bound = self._opz_source_bindings.get(observation_id)
        icao24 = self._live_aircraft_icao_for_track_id(getattr(bound, "track_id", None))
        if icao24 is None:
            return
        self.live_engage_authorized.discard(icao24)
        if affiliation == "HOSTILE":
            self.live_engage_confirm_pending = icao24
            self.flash(message("runtime.cic.hostile_confirm_required",
                               track=display_id), 5.0)
            self.feed.add(self.world.format_time(), "opz",
                          message("runtime.cic.hostile_confirm_required",
                                  track=display_id))
        elif self.live_engage_confirm_pending == icao24:
            self.live_engage_confirm_pending = None

    def live_engagement_pending_for_observation(self, observation_id: str) -> bool:
        """Whether this OPZ observation is the live contact currently
        awaiting an attack confirmation (see _sync_live_engagement_hold)."""
        if self.live_engage_confirm_pending is None:
            return False
        bound = self._opz_source_bindings.get(observation_id)
        icao24 = self._live_aircraft_icao_for_track_id(getattr(bound, "track_id", None))
        return icao24 == self.live_engage_confirm_pending

    def confirm_live_engagement(self) -> bool:
        """OPZ 'Enter': explicit player affirmation to fire on the live,
        real-world contact currently awaiting confirmation after being
        classified HOSTILE. See _sync_live_engagement_hold."""
        icao24 = self.live_engage_confirm_pending
        if icao24 is None or icao24 not in self.live_traffic.aircraft:
            return False
        self.live_engage_authorized.add(icao24)
        self.live_engage_confirm_pending = None
        self.flash(message("runtime.cic.hostile_confirmed"), 2.5)
        self.feed.add(self.world.format_time(), "opz",
                      message("runtime.cic.hostile_confirmed"))
        return True

    def create_opz_fusion(self, observation_ids):
        if self.damage.station_down("opz"):
            return "opz_down"
        if (type(observation_ids) not in (list, tuple)
                or not config.OPZ_FUSION_MEMBER_MIN <= len(observation_ids)
                <= config.OPZ_FUSION_MEMBER_MAX
                or len(set(observation_ids)) != len(observation_ids)):
            return "invalid_value"
        sources = self.opz_source_observations()
        current = {item.observation_id for item in sources}
        if any(key not in current for key in observation_ids):
            return "stale_ref"
        self.opz_fusion.marked = set(observation_ids)
        fusion = self.opz_fusion.create(sources)
        if fusion is None:
            return "fusion_rejected"
        self.opz_selected_track_id = fusion.fusion_id
        return True

    def dissolve_opz_fusion(self, observation_id: str):
        if self.damage.station_down("opz"):
            return "opz_down"
        if observation_id not in self.opz_fusion.fusions:
            return "stale_ref"
        self.opz_fusion.dissolve(observation_id)
        if self.opz_selected_track_id == observation_id:
            self.opz_selected_track_id = None
        return True

    def _update_opz_picture(self) -> None:
        """Fuse reports of different sensors lying on top of each other.

        Runs on simulation time (every ``OPZ_AUTO_FUSE_INTERVAL_S``) from the
        OPZ's published reports only, so the result never depends on drawing
        or on browser polling. A selected report that joins a fusion hands
        the selection to the fusion."""
        step = int(self.sim_t // config.OPZ_AUTO_FUSE_INTERVAL_S)
        if step == self._opz_auto_fuse_step:
            return
        self._opz_auto_fuse_step = step
        if self.damage.station_down("opz"):
            return
        observations = self.opz_source_observations()
        for fusion_id in self.opz_fusion.auto_fuse(
                observations, self.ship.x, self.ship.y, self.sim_t,
                self.air_picture.stale_s):
            if self.opz_selected_track_id in self.opz_fusion.fusions[fusion_id].members:
                self.opz_selected_track_id = fusion_id

    def opz_suggestions(self) -> tuple:
        """Correlation suggestions from the OPZ's own published reports.

        Pure in its inputs (reports, own position, time, fusions, dismissals)
        and cached on exactly those, so drawing and projecting in the same
        tick never repeat the pair scan."""
        if self.damage.station_down("opz"):
            return ()
        observations = self.opz_source_observations()
        self.opz_fusion.prune(observations)
        fused = tuple(sorted({member for fusion in self.opz_fusion.fusions.values()
                              for member in fusion.members}))
        signature = (self.sim_t, self.ship.x, self.ship.y, fused,
                     tuple(self.opz_fusion.dismissed),
                     tuple((item.observation_id, item.source, item.kind,
                            item.bearing, item.x, item.y, item.last_seen,
                            item.bearing_uncertainty_deg, item.observer_x,
                            item.observer_y, item.course, item.speed_kn,
                            item.classification) for item in observations))
        cached = getattr(self, "_opz_suggestion_cache", None)
        if cached is not None and cached[0] == signature:
            return cached[1]
        suggestions = suggest_correlations(
            observations, self.ship.x, self.ship.y, self.sim_t,
            fused=fused, dismissed=self.opz_fusion.dismissed)
        self._opz_suggestion_cache = (signature, suggestions)
        return suggestions

    def opz_suggestion_labels(self, suggestion) -> tuple[str, str]:
        """Operator-visible IDs of a suggestion's two reports."""
        labels = {item.observation_id: item.label
                  for item in self.opz_source_observations()}
        return tuple(self.opz_track_label(key, labels.get(key, key[-6:]))
                     for key in suggestion.members)

    def dismiss_opz_suggestion(self, observation_ids):
        """Drop one current suggestion (transient, like the fusions)."""
        if self.damage.station_down("opz"):
            return "opz_down"
        if (type(observation_ids) not in (list, tuple) or len(observation_ids) != 2
                or len(set(observation_ids)) != 2):
            return "invalid_value"
        key = suggestion_key(observation_ids)
        if all(item.key != key for item in self.opz_suggestions()):
            return "stale_ref"
        self.opz_fusion.dismiss(key)
        return True

    def _accept_opz_suggestion(self) -> None:
        """OPZ 'U': fuse the top suggestion through the manual fusion path."""
        suggestions = self.opz_suggestions()
        if not suggestions:
            self.flash(message("runtime.cic.suggestion_none"))
            return
        first, second = self.opz_suggestion_labels(suggestions[0])
        if self.create_opz_fusion(list(suggestions[0].members)) is not True:
            self.flash(message("runtime.cic.fusion_rejected"))
            return
        self.flash(message("runtime.cic.suggestion_fused",
                           first=first, second=second), 2.0)

    def _dismiss_opz_suggestion(self) -> None:
        """OPZ 'Shift+U': dismiss the top suggestion."""
        suggestions = self.opz_suggestions()
        if not suggestions:
            self.flash(message("runtime.cic.suggestion_none"))
            return
        first, second = self.opz_suggestion_labels(suggestions[0])
        if self.dismiss_opz_suggestion(list(suggestions[0].members)) is True:
            self.flash(message("runtime.cic.suggestion_dismissed",
                               first=first, second=second), 2.0)

    def _cycle_opz_track(self, delta: int) -> None:
        tracks = self.filtered_opz_tracks()
        if not tracks:
            self.opz_selected_track_id = None
            return
        ids = [track.track_id for track in tracks]
        try:
            index = ids.index(self.opz_selected_track_id)
        except ValueError:
            index = -1 if delta > 0 else 0
        self.opz_selected_track_id = ids[(index + delta) % len(ids)]

    def _cycle_opz_affiliation(self) -> None:
        track = self.selected_opz_track()
        if track is None:
            self.flash(message("runtime.cic.none_select"))
            return
        current = self.opz_affiliation(track.track_id)
        order = config.NATO_AFFILIATIONS
        value = order[(order.index(current) + 1) % len(order)]
        if self.affiliate_opz_observation(track.track_id, value) is not True:
            return
        self.flash(message("runtime.cic.affiliation", track=track.track_id,
                           affiliation=display_value("affiliation", value, self.tr)), 2.0)

    def _cycle_opz_classification(self) -> None:
        track = self.selected_opz_track()
        if track is None:
            self.flash(message("runtime.cic.none_select"))
            return
        if track.source.startswith("SONAR"):
            contact = self._opz_source_bindings.get(track.observation_id)
            if not isinstance(contact, Contact):
                self.flash(message("runtime.cic.source_owned"))
                return
            current = contact.player_class
        elif (track.source.startswith("RADAR")
              or track.source in ("HOJ", "FUSION")):
            current = self.opz_fusion.classifications.get(track.observation_id)
        else:
            self.flash(message("runtime.cic.source_owned"))
            return
        order = (None, *config.PLAYER_CLASSES)
        value = order[(order.index(current) + 1) % len(order)]
        self.classify_opz_observation(track.observation_id, value)

    def _toggle_opz_mark(self) -> None:
        track = self.selected_opz_track()
        if track is None or track.source == "FUSION":
            return
        if track.observation_id in self.opz_fusion.marked:
            self.opz_fusion.marked.remove(track.observation_id)
        else:
            self.opz_fusion.marked.add(track.observation_id)

    def _create_opz_fusion(self) -> None:
        result = self.create_opz_fusion(tuple(self.opz_fusion.marked))
        if result is not True:
            self.flash(message("runtime.cic.fusion_rejected"))

    def _dissolve_opz_fusion(self) -> None:
        if self.opz_selected_track_id:
            self.dissolve_opz_fusion(self.opz_selected_track_id)

    def _toggle_opz_suppression(self) -> None:
        track = self.selected_opz_track()
        if track is None:
            return
        key = track.observation_id
        if key in self.opz_fusion.suppressed:
            self.opz_fusion.suppressed.remove(key)
        else:
            self.opz_fusion.suppressed.add(key)

    def eloka_tracks(self) -> tuple:
        """Return detached passive intercepts in stable picture order."""
        return self.esm_picture.tracks(self.sim_t)

    def eloka_visible_tracks(self) -> tuple:
        """Return the one filtered/sorted list used by ELOKA presentation."""
        return filter_and_sort_tracks(
            self.eloka_tracks(), self.sim_t, self.eloka_display_analysis,
            status=self.eloka_status_filter,
            minimum_threat=self.eloka_threat_filter,
            band=self.eloka_band_filter,
            annotated_keys=self.eloka_annotations,
            jamming_keys=(channel.track_key
                          for channel in self.ecm_jammer.channels))

    def _reconcile_eloka_selection(self) -> None:
        visible = self.eloka_visible_tracks()
        keys = {track.track_key for track in visible}
        if self.eloka_selected_track_key not in keys:
            self.eloka_selected_track_key = (visible[0].track_key
                                             if visible else None)

    def _cycle_eloka_filter(self, kind: str) -> None:
        names = {
            "status": ("eloka_status_filter",
                       ("OPERATIONAL", "LIVE", "MEMORY", "ALL")),
            "threat": ("eloka_threat_filter",
                       ("ALL", "LOW", "MEDIUM", "HIGH", "CRITICAL")),
            "band": ("eloka_band_filter",
                     ("ALL", "A_C", "D", "E_F", "G_H", "I_J", "K")),
        }
        attribute, values = names[kind]
        current = getattr(self, attribute)
        setattr(self, attribute, values[(values.index(current) + 1) % len(values)])
        self._reconcile_eloka_selection()

    def selected_eloka_track(self):
        return next((track for track in self.eloka_tracks()
                     if track.track_key == self.eloka_selected_track_key), None)

    def _cycle_eloka_track(self, delta: int) -> None:
        if self.damage.station_down("opz"):
            return
        tracks = self.eloka_visible_tracks()
        if not tracks:
            self.eloka_selected_track_key = None
            return
        keys = [track.track_key for track in tracks]
        try:
            index = keys.index(self.eloka_selected_track_key)
        except ValueError:
            index = -1 if delta > 0 else 0
        self.eloka_selected_track_key = keys[(index + delta) % len(keys)]

    def eloka_candidates(self, track=None) -> tuple:
        if self.damage.station_down("opz"):
            return ()
        track = track or self.selected_eloka_track()
        return (() if track is None else
                rank_emitters(track, self.runtime_catalog.emitters))

    def eloka_display_candidates(self, track=None) -> tuple:
        """Emitter choices shown to the operator: ranked with scores only as
        a training aid; otherwise an unranked library range lookup."""
        if self.operator_assist():
            return self.eloka_candidates(track)
        if self.damage.station_down("opz"):
            return ()
        track = track or self.selected_eloka_track()
        return (() if track is None else
                library_emitters(track, self.runtime_catalog.emitters))

    def eloka_display_analysis(self, track=None):
        """Radar type/threat inferred from the catalog: training aid only."""
        return self.eloka_analysis(track) if self.operator_assist() else None

    def eloka_display_range(self, track):
        return self.eloka_range_estimate(track) if self.operator_assist() else None

    ELOKA_ANALYSIS_CACHE_MAX = 256

    def eloka_analysis(self, track=None):
        track = track or self.selected_eloka_track()
        if track is None:
            return None
        # The ranking depends only on the measured fingerprint and the
        # immutable runtime catalog; memoize it (bounded, never saved).
        emitters = self.runtime_catalog.emitters
        if self.__dict__.get("_eloka_analysis_owner") is not emitters:
            self._eloka_analysis_owner = emitters
            self._eloka_analysis_cache = {}
        key = (track.frequency_hz, track.prf_hz, track.modulation_code)
        cache = self._eloka_analysis_cache
        result = cache.get(key)
        if result is None:
            if len(cache) >= self.ELOKA_ANALYSIS_CACHE_MAX:
                cache.clear()
            result = cache[key] = analyze_signal(track, emitters)
        return result

    def eloka_range_estimate(self, track=None) -> float | None:
        """Range implied by the intercept's peak level, assuming the power
        class of the best-ranked catalog hypothesis (never emitter truth)."""
        track = track or self.selected_eloka_track()
        analysis = self.eloka_analysis(track)
        if analysis is None or not analysis.candidates or track.signal_db <= 0.0:
            return None
        emitter = self.runtime_catalog.emitters.get(
            analysis.candidates[0].emitter_key)
        return estimated_range_nm(track, getattr(emitter, "power_class", "medium"))

    def deploy_jamming(self, track, technique=None):
        if self.damage.station_down("opz"):
            return "opz_down"
        if track is None or not any(item is track for item in self.eloka_tracks()):
            return "stale_ref"
        return self.ecm_jammer.deploy_jamming(
            track, self.sim_t, technique=technique)

    def set_jamming_technique(self, track, technique: str):
        if self.damage.station_down("opz"):
            return "opz_down"
        if track is None or not any(item is track for item in self.eloka_tracks()):
            return "stale_ref"
        return self.ecm_jammer.set_technique(track, technique, self.sim_t)

    def _cycle_jamming_technique(self, track) -> str | None:
        if track is None:
            return None
        channel = next((item for item in self.ecm_jammer.channels
                        if item.track_key == track.track_key), None)
        current = (channel.technique if channel is not None else
                   self.ecm_jammer.recommended_technique(track))
        index = ECM_TECHNIQUES.index(current)
        technique = ECM_TECHNIQUES[(index + 1) % len(ECM_TECHNIQUES)]
        return (technique if self.set_jamming_technique(track, technique) is True
                else None)

    def set_jamming(self, track, enabled: bool):
        if type(enabled) is not bool:
            return "invalid"
        active = (track is not None and any(
            channel.track_key == track.track_key
            for channel in self.ecm_jammer.channels))
        if active == enabled:
            return True
        return self.deploy_jamming(track)

    def set_ecm_auto(self, enabled: bool):
        if type(enabled) is not bool:
            return "invalid"
        if self.damage.station_down("opz"):
            return "opz_down"
        self.ecm_jammer.auto_enabled = enabled
        if not enabled:
            self.ecm_jammer.channels = [channel for channel in
                self.ecm_jammer.channels if not channel.automatic]
        return True

    def eloka_annotation(self, track_key: str) -> str | None:
        emitter_key = self.eloka_annotations.get(track_key)
        emitter = self.runtime_catalog.emitters.get(emitter_key)
        return emitter_key if emitter is not None and emitter.domain == "radar" else None

    def eloka_emitter_name(self, emitter_key: str | None) -> str | None:
        """Display name of the platform owning an ESM emitter, or None."""
        if not isinstance(emitter_key, str):
            return None
        name = self.runtime_catalog.emitter_name(emitter_key)
        if name is None:
            # Library emitters have no owning platform: a missile seeker is
            # named by what it is.
            emitter = self.runtime_catalog.emitters.get(emitter_key)
            if getattr(emitter, "radar_role", None) == "missile_seeker":
                name = self.tr("eloka.emitter.asm_seeker")
            elif emitter_key == config.HELO_RADAR_EMITTER:
                name = self.tr("eloka.emitter.helicopter_radar")
            elif emitter_key == config.MPA_RADAR_EMITTER:
                name = self.tr("eloka.emitter.mpa_radar")
        return name

    def eloka_annotation_name(self, track_key: str) -> str | None:
        """Operator annotation resolved to the owning platform's name."""
        return self.eloka_emitter_name(self.eloka_annotation(track_key))

    def annotate_eloka_intercept(self, track, emitter_key: str):
        if self.damage.station_down("opz"):
            return "opz_down"
        if not any(item is track for item in self.eloka_tracks()):
            return "stale_ref"
        candidates = {item.emitter_key for item in rank_emitters(
            track, self.runtime_catalog.emitters,
            maximum=len(self.runtime_catalog.emitters))}
        if type(emitter_key) is not str or emitter_key not in candidates:
            return "stale_ref"
        previous = self.eloka_annotation(track.track_key)
        if previous is not None and previous != emitter_key:
            self._remove_released_esm(track.track_key, previous)
        self.eloka_annotations[track.track_key] = emitter_key
        while len(self.eloka_annotations) > ESM_MAX_ANNOTATIONS:
            del self.eloka_annotations[min(self.eloka_annotations)]
        self._publish_released_esm()
        return True

    def clear_eloka_annotation(self, track):
        if self.damage.station_down("opz"):
            return "opz_down"
        if not any(item is track for item in self.eloka_tracks()):
            return "stale_ref"
        previous = self.eloka_annotation(track.track_key)
        self.eloka_annotations.pop(track.track_key, None)
        if previous is not None:
            self._remove_released_esm(track.track_key, previous)
        self._publish_released_esm()
        return True

    def _remove_released_esm(self, track_key: str, emitter_key: str) -> None:
        identity = self._observation_key(
            "esm-release", f"{track_key}:{emitter_key}")
        self.air_picture._tracks.pop(f"E-{identity}", None)

    def _cycle_eloka_annotation(self) -> None:
        if self.damage.station_down("opz"):
            self.flash(message("runtime.eloka.disabled"))
            return
        track = self.selected_eloka_track()
        if track is None:
            self.flash(message("runtime.eloka.none_select"))
            return
        # Training: likeliest first. Otherwise the library range lookup in
        # name order, so the first press does not reveal the best match.
        choices = ([candidate.emitter_key for candidate in rank_emitters(
            track, self.runtime_catalog.emitters,
            maximum=len(self.runtime_catalog.emitters))]
            if self.operator_assist() else sorted(
                (candidate.emitter_key for candidate in library_emitters(
                    track, self.runtime_catalog.emitters,
                    maximum=len(self.runtime_catalog.emitters))),
                key=lambda key: (str(self.eloka_emitter_name(key) or key), key)))
        current = self.eloka_annotation(track.track_key)
        index = choices.index(current) if current in choices else -1
        if index + 1 >= len(choices):
            self.clear_eloka_annotation(track)
            assignment = self.tr("common.unknown")
        else:
            key = choices[index + 1]
            self.annotate_eloka_intercept(track, key)
            assignment = self.eloka_emitter_name(key) or key
        self.flash(message("runtime.eloka.annotation",
                           track=track.track_key, assignment=assignment), 2.0)

    def _publish_released_esm(self) -> None:
        """Release only operator-classified, bearing-only ESM observations."""
        for track in self.eloka_tracks():
            emitter_key = self.eloka_annotation(track.track_key)
            label = self.eloka_emitter_name(emitter_key)
            if emitter_key is None or label is None:
                continue
            identity = self._observation_key(
                "esm-release", f"{track.track_key}:{emitter_key}")
            self.air_picture.observe(
                track_id=f"E-{identity}", kind="UNKNOWN", target_id=0,
                source="ESM", bearing=track.bearing, range_nm=None,
                observer_x=track.observer_x, observer_y=track.observer_y,
                course=None, quality=track.quality, now=track.last_seen,
                label=label, hostile=False,
                bearing_uncertainty_deg=track.bearing_uncertainty_deg)

    def released_esm_labels(self) -> dict[str, str]:
        """Return detached operator-approved labels keyed by public track ID."""
        released = {}
        for track in self.eloka_tracks():
            emitter_key = self.eloka_annotation(track.track_key)
            label = self.eloka_emitter_name(emitter_key)
            if emitter_key is not None and label is not None:
                identity = self._observation_key(
                    "esm-release", f"{track.track_key}:{emitter_key}")
                released[f"E-{identity}"] = label
        return released

    def eloka_correlations(self, track=None) -> tuple:
        """Compare ESM and public radar evidence without target identity."""
        if self.damage.station_down("opz"):
            return ()
        track = track or self.selected_eloka_track()
        if track is None:
            return ()
        raw_evidence = []
        for observed in self.air_picture._tracks.values():
            if (not isinstance(observed.source, str)
                    or not observed.source.startswith("RADAR")
                    or "AIS" in observed.source.upper()):
                continue
            values = (observed.bearing, observed.last_seen)
            optional = (observed.bearing_uncertainty_deg, observed.x,
                        observed.y, observed.position_seen)
            if (not all(isinstance(value, (int, float))
                        and not isinstance(value, bool) and math.isfinite(value)
                        for value in values)
                    or any(value is not None and (
                        not isinstance(value, (int, float))
                        or isinstance(value, bool) or not math.isfinite(value))
                           for value in optional)
                    or (observed.x is None) != (observed.y is None)
                    or not 0.0 <= observed.bearing < 360.0):
                continue
            observed_at = (observed.position_seen if observed.x is not None
                           and observed.position_seen is not None
                           else observed.last_seen)
            if not 0.0 <= observed_at <= self.sim_t \
                    or self.sim_t - observed_at > 30.0:
                continue
            raw_evidence.append((observed.source, observed.bearing,
                                 observed.bearing_uncertainty_deg,
                                 observed.x, observed.y, observed_at))
        evidence = []
        evidence_order = lambda row: (
            row[0], row[1], -1.0 if row[2] is None else row[2],
            0 if row[3] is None else 1,
            0.0 if row[3] is None else row[3],
            0.0 if row[4] is None else row[4], row[5])
        used_keys = set()
        for values in sorted(raw_evidence, key=evidence_order):
            source, bearing, uncertainty, x, y, observed_at = values
            digest = hashlib.blake2b(repr(values).encode("utf-8"),
                                     digest_size=5).hexdigest().upper()
            track_id = f"OBS-{digest}"
            suffix = 2
            while track_id in used_keys:
                track_id = f"OBS-{digest}-{suffix}"
                suffix += 1
            used_keys.add(track_id)
            evidence.append(ESMCorrelationEvidence(
                track_id=track_id, source=source, bearing=bearing,
                bearing_uncertainty_deg=uncertainty, x=x, y=y,
                observed_at=observed_at))
        return correlate_observations(track, evidence, self.sim_t)

    def atmosphere(self) -> dict:
        """Own-ship atmosphere (barometer, thermometer, wind, sky), derived
        from the weather system; observation-safe (no future values)."""
        world = self.world
        weather = world.weather_values()
        kind = world.weather_kind()
        source_sea, target_sea, elapsed = world.weather_epoch()
        pressure, tendency = atmosphere_physics.barometer(
            self.seed, source_sea, target_sea, elapsed)
        trend = atmosphere_physics.pressure_trend(tendency)
        rain = weather["rain_intensity"]
        wind = weather["wind_speed_kn"]
        sst = world.ocean.sea_surface_temperature_c(world.hour)
        cloud = atmosphere_physics.cloud_cover(kind, rain)
        air = atmosphere_physics.air_temperature_c(
            sst, world.ocean.day_of_year, world.hour, weather["wind_from_deg"],
            wind, cloud)
        precipitation = atmosphere_physics.precipitation(rain, air)
        latitude = world.latitude_deg()
        latitude = (atmosphere_physics.DEFAULT_LATITUDE_DEG if latitude is None
                    else latitude)
        sun = atmosphere_physics.sun_elevation_deg(
            latitude, world.ocean.day_of_year, world.hour)
        lunar_age = self.lunar_age_days()
        return dict(
            weather=("snow" if precipitation == "snow" else kind),
            precipitation=precipitation, rain_intensity=rain,
            visibility_nm=weather["visibility_nm"],
            sea_state=int(round(weather["sea_state"])),
            wind_from_deg=weather["wind_from_deg"], wind_kn=wind,
            gust_kn=atmosphere_physics.gust_kn(wind, weather["sea_state"]),
            beaufort=atmosphere_physics.beaufort(wind),
            pressure_hpa=pressure, pressure_tendency_hpa_3h=tendency,
            pressure_trend=trend,
            storm_warning=atmosphere_physics.storm_warning(pressure, trend),
            air_temp_c=air, sea_temp_c=sst, cloud_cover=cloud,
            ceiling_ft=atmosphere_physics.cloud_ceiling_ft(
                kind, rain, weather["visibility_nm"]),
            icing=atmosphere_physics.icing(air, precipitation, wind),
            sun_elevation_deg=sun,
            daylight=atmosphere_physics.daylight(sun),
            moon_phase=atmosphere_physics.moon_phase(lunar_age),
            moon_illumination=visual_physics.moon_illumination(lunar_age),
            time=world.format_time())

    def helicopter_weather(self) -> dict:
        """Return one shared, observation-safe flight-weather decision."""
        weather = self.world.weather_values()
        atmosphere = self.atmosphere()
        relative = math.radians(config.angle_diff_deg(
            weather["wind_from_deg"], self.ship.course))
        crosswind = abs(weather["wind_speed_kn"] * math.sin(relative))
        launch_safe = (
            weather["wind_speed_kn"] <= config.HELO_LAUNCH_WIND_MAX_KN
            and crosswind <= config.HELO_LAUNCH_CROSSWIND_MAX_KN
            and weather["visibility_nm"] >= config.HELO_LAUNCH_VISIBILITY_MIN_NM
            and weather["sea_state"] <= config.HELO_LAUNCH_SEA_STATE_MAX)
        gust = atmosphere["gust_kn"]
        ceiling = atmosphere["ceiling_ft"]
        icing = atmosphere["icing"]
        launch_weather = (launch_safe
                          and gust <= config.HELO_LAUNCH_GUST_MAX_KN
                          and (ceiling is None or ceiling >= config.HELO_CEILING_MIN_FT)
                          and icing != "severe")
        # Launch and recovery also need a deck-motion window (own ship).
        deck_safe = helicopter_physics.deck_within_limits(self.ship.roll, self.ship.pitch)
        launch_safe = launch_weather and deck_safe
        dipping_safe = (
            weather["wind_speed_kn"] <= config.HELO_DIP_WIND_MAX_KN
            and weather["visibility_nm"] >= config.HELO_DIP_VISIBILITY_MIN_NM
            and weather["sea_state"] <= config.HELO_DIP_SEA_STATE_MAX
            # Winch and cable ice up: no dipping in icing conditions.
            and icing == "none")
        # Flight-weather category: NO-GO outside the launch weather limits,
        # LIMITED near a limit (80 %) or in light icing, else CLEAR.
        margins = (
            weather["wind_speed_kn"] / config.HELO_LAUNCH_WIND_MAX_KN,
            gust / config.HELO_LAUNCH_GUST_MAX_KN,
            crosswind / config.HELO_LAUNCH_CROSSWIND_MAX_KN,
            weather["sea_state"] / config.HELO_LAUNCH_SEA_STATE_MAX,
            config.HELO_LAUNCH_VISIBILITY_MIN_NM / max(weather["visibility_nm"], 1e-3),
            (0.0 if ceiling is None else config.HELO_CEILING_MIN_FT / max(ceiling, 1.0)))
        status = ("no_go" if not launch_weather else
                  "limited" if icing != "none" or max(margins) >= 0.8 else "clear")
        return dict(weather, crosswind_kn=crosswind, deck_safe=deck_safe,
                    launch_safe=launch_safe, dipping_safe=dipping_safe,
                    gust_kn=gust, ceiling_ft=ceiling, icing=icing, status=status)

    WEATHER_PROFILE_STALE_S = 1800.0
    WEATHER_PROFILE_STALE_NM = 10.0
    WEATHER_RAY_SOURCE_DEPTH_M = 5.0      # hull sonar

    def weather_station_data(self) -> dict:
        """Observation-safe data for the weather & sonar analysis panel.

        Atmosphere and flight weather come from own-ship instruments.  The
        ocean profile - layer, sound-speed curve, shadow zone, SOFAR axis,
        rays - exists only after the sonar has taken a bathythermograph
        measurement, and is always that measurement (with its age), never
        the modelled truth."""
        atmosphere = self.atmosphere()
        effects = dict(
            solar_heating=(atmosphere["daylight"] == "day"
                           and atmosphere["sun_elevation_deg"] >= 20.0
                           and atmosphere["cloud_cover"] < 0.6),
            wind_mixing=atmosphere["wind_kn"] >= ocean_physics.MLD_WIND_THRESHOLD_KN,
            freshwater=atmosphere["precipitation"] != "none")
        boat = self._opfor
        if boat is not None and self._sonar_ctx is boat.station:
            # The crewed boat has no flight deck: no flight weather, cloud
            # ceiling or icing, but what the weather does to the boat itself.
            return dict(
                atmosphere={key: value for key, value in atmosphere.items()
                            if key not in self.WEATHER_BOAT_OMITTED},
                effects=effects, boat=self._weather_boat_block(boat.sub),
                profile=self._weather_station_profile())
        flight = self.helicopter_weather()
        return dict(
            atmosphere=atmosphere, effects=effects,
            flight=dict(
                status=flight["status"], launch_safe=flight["launch_safe"],
                dipping_safe=flight["dipping_safe"], deck_safe=flight["deck_safe"],
                wind_kn=flight["wind_speed_kn"], gust_kn=flight["gust_kn"],
                crosswind_kn=flight["crosswind_kn"],
                visibility_nm=flight["visibility_nm"],
                ceiling_ft=flight["ceiling_ft"], icing=flight["icing"],
                sea_state=int(round(flight["sea_state"])),
                # A crewed boat's instruments never report the frigate's motion.
                roll_deg=(self.ship.roll if self._sonar_ctx is self._frigate_sonar
                          else 0.0),
                pitch_deg=(self.ship.pitch if self._sonar_ctx is self._frigate_sonar
                           else 0.0),
                limits=dict(
                    wind_kn=config.HELO_LAUNCH_WIND_MAX_KN,
                    gust_kn=config.HELO_LAUNCH_GUST_MAX_KN,
                    crosswind_kn=config.HELO_LAUNCH_CROSSWIND_MAX_KN,
                    visibility_nm=config.HELO_LAUNCH_VISIBILITY_MIN_NM,
                    ceiling_ft=config.HELO_CEILING_MIN_FT,
                    sea_state=config.HELO_LAUNCH_SEA_STATE_MAX,
                    roll_deg=helicopter_physics.DECK_ROLL_LIMIT_DEG,
                    pitch_deg=helicopter_physics.DECK_PITCH_LIMIT_DEG)),
            profile=self._weather_station_profile())

    # Atmosphere rows that only matter for flying (the boat side omits them).
    WEATHER_BOAT_OMITTED = ("ceiling_ft", "icing")

    def _weather_boat_block(self, sub) -> dict:
        """What the weather does to the crewed boat (environment and own boat
        only, never another platform's state).

        * Mast radar: the range at which a reference surface-search radar
          (the frigate class's nominal set, undamaged) sees a raised mast or
          snorkel head with Pd = 0.5 per look in this sea and rain, capped by
          the radar horizon - the same model the simulation uses for mast
          echoes (``SUB_MAST_RCS_FACTOR``, sea clutter, rain loss).
        * Optics: the range at which a ship's lookout sights the boat
          surfaced, in this light, visibility and sea (the lookout contrast
          model); a raised mast at periscope depth is never sighted.
        * Ambient noise: wind and rain above the calm reference (sea state 1,
          no rain) per sonar band; it masks the boat from passive sonar and
          dampens the boat's own listening alike.
        * Snorkel: speed ceiling, radiated penalty and diesel lines."""
        from src.core.boat_esm import mast_radar_nm
        from src.core.game_sim import LOOKOUT_MODEL
        from src.sonar import equation as sonar_equation
        world = self.world
        sea = float(getattr(world, "effective_sea_state", world.sea_state))
        rain = config.clamp(float(getattr(world, "rain_intensity", 0.0)), 0.0, 1.0)
        light = self._lookout_environment()
        bands = tuple(float(band) for band in sonar_equation.BANDS_HZ)
        excess = [sonar_equation.ambient_noise_db(band, sea, rain)
                  - sonar_equation.ambient_noise_db(
                      band, sonar_equation.REFERENCE_SEA_STATE, 0.0)
                  for band in bands]
        return dict(
            mast_radar_nm=mast_radar_nm(sea, rain),
            mast_radar_calm_nm=mast_radar_nm(0.0, 0.0),
            sighting_nm=LOOKOUT_MODEL.sighting_range_nm("SUB", **light),
            sighting_ref_nm=float(config.LOOKOUT_SUB_RANGE_NM),
            ambient_bands_hz=list(bands), ambient_excess_db=excess,
            snorkel_available=sub.endurance is not None,
            snorkeling=bool(sub.snorkeling),
            snorkel_max_kn=float(config.UBOOT_SNORKEL_MAX_KN),
            snorkel_noise_db=float(config.UBOOT_SNORKEL_NOISE_DB),
            snorkel_lines_hz=[float(line[0]) for line in config.UBOOT_SNORKEL_LINES])

    def _weather_station_profile(self) -> dict | None:
        bt = self.sonar.bt_profile
        if bt is None:
            return None
        age = max(0.0, self.sim_t - bt["t"])
        observer = self.sonar_observer
        offset = math.hypot(observer.x - bt["x"], observer.y - bt["y"])
        # Wind of the measurement's sea-state band keeps the picture fixed
        # for one measurement (a pure, cached function of it).
        wind = ocean_physics.MLD_WIND_THRESHOLD_KN * bt["sea_state"] / 3.0
        picture = sonar_raytrace.ray_picture(
            bt["depths_m"], bt["speeds_m_s"], bt["water_depth_m"],
            self.WEATHER_RAY_SOURCE_DEPTH_M, self.world.seabed_at(bt["x"], bt["y"]),
            wind, bt["thermocline_m"])
        dip = None
        if (self._sonar_ctx is self._frigate_sonar and self.helo.airborne
                and self.helo.dip_state != "STOWED"):
            dip = ("below" if self.helo.dip_depth_m >= bt["thermocline_m"]
                   else "above")
        return dict(
            age_s=age, offset_nm=offset,
            stale=(age > self.WEATHER_PROFILE_STALE_S
                   or offset > self.WEATHER_PROFILE_STALE_NM),
            thermocline_m=bt["thermocline_m"], water_depth_m=bt["water_depth_m"],
            depths_m=list(bt["depths_m"]), speeds_m_s=list(bt["speeds_m_s"]),
            sofar_axis_m=ocean_physics.sofar_axis_m(
                bt["depths_m"], bt["speeds_m_s"], bt["water_depth_m"]),
            cz_bands_nm=[list(band) for band in bt["cz_bands_nm"]],
            range_nm=picture["range_nm"], rays=picture["rays"],
            depth_edges_m=picture["depth_edges_m"], shadow=picture["shadow"],
            dip_relative_to_layer=dip)

    def lookout_report_text(self, report: dict):
        """Localizable report line: 'Bridge lookout: frigate bearing 040, 3.8 NM'."""
        return message("lookout.report", what=self.lookout_report_what(report),
                       bearing=f"{report['bearing']:03.0f}",
                       range=f"{report['range_nm']:.1f}")

    def lookout_report_what(self, report: dict):
        if report["code"] is None:
            return message(f"lookout.detect.{report['kind'].lower()}")
        what = message(f"lookout.class.{report['code'].lower()}")
        if report["type_name"]:
            what = message("lookout.with_type", what=what,
                           type=raw_text(report["type_name"]))
        return what

    def lookout_visual_what(self, label):
        """What the lookout reported for a visual track label, or None."""
        _level, code, type_key = lookout_id.decode(label)
        if code is None:
            return None
        return self.lookout_report_what(dict(
            kind=None, code=code, type_name=self.lookout_type_name(type_key)))

    def lookout_type_name(self, type_key: str | None) -> str | None:
        if type_key is None:
            return None
        profile = (self.runtime_catalog.surfaces.get(type_key)
                   or self.runtime_catalog.aircraft.get(type_key))
        return None if profile is None else str(profile.name)

    def _record_simlog(self, stamp: str, category: str, text) -> None:
        """Simulationsprotokoll: alle Feed-Ereignisse, optionsgesteuert, begrenzt.

        Speichert das Rohtext (message-/RawText-Objekt); die Lokalisierung
        erfolgt erst beim Commander-Publish (Sprache kann wechseln).
        Every event is also offered to the spoken crew reports.
        """
        self.callouts.add(text)
        if not self.preferences.simlog:
            return
        self._simlog_seq += 1
        self.simlog.append({
            "seq": self._simlog_seq,
            "t": self.sim_t,
            "stamp": stamp,
            "cat": category,
            "text": text,
        })

    def _pump_speech(self) -> None:
        """Say the local side's new crew reports aloud (option on, espeak found).

        Wall clock only: the speaker polls its process and never blocks.
        """
        boat = getattr(self, "_opfor", None)
        log = (boat.callouts if getattr(self, "local_side", "frigate") == "uboot"
               and boat is not None else self.callouts)
        rows = log.rows
        if not rows or rows[-1]["seq"] <= log.spoken:
            self.speaker.pump()
            return
        fresh = [row for row in rows if row["seq"] > log.spoken]
        log.spoken = rows[-1]["seq"]
        if (self.preferences.speech and self.speaker.available
                and (log is self.callouts) == (getattr(self, "local_side", "frigate")
                                               == "frigate")):
            for row in fresh:
                self.speaker.say(callouts.spoken_text(row, self.tr),
                                 self.preferences.language)
        self.speaker.pump()

    def _record_simlog_state(self, dt: float) -> None:
        """Periodischer Zustandssnapshot des kompletten Simulationshintergrunds.

        Rein lesend (kein RNG, keine Zustandsaenderung); Laeuft nur im
        Simulationsfortschritt, nicht in Pause/Menue/Editor.  Feeds the
        (equally read-only) mission debrief recorder first.
        """
        self._record_debrief(dt)
        if not self.preferences.simlog:
            self._simlog_acc = 0.0
            return
        self._simlog_acc += dt
        if self._simlog_acc < config.SIMLOG_INTERVAL_S:
            return
        self._simlog_acc = 0.0
        self._simlog_seq += 1
        self.simlog.append({
            "seq": self._simlog_seq,
            "t": self.sim_t,
            "stamp": self.world.format_time(),
            "cat": "state",
            "text": "",
            "data": self._simlog_state_data(),
        })

    def _simlog_state_data(self) -> dict:
        """Kompakter, JSON-faechiger Zustand aller Einheiten, Waffen und Welt."""
        def r2(v):
            return None if v is None else round(float(v), 2)

        def r1(v):
            return None if v is None else round(float(v), 1)

        ship = self.ship
        snap = {
            "mission_t": r2(self.mission_time),
            "result": self.mission_result,
            "world": {"hour": r1(self.world.hour),
                      "sea_state": self.world.sea_state,
                      "night": self.world.is_night()},
            "ship": {"x": r2(ship.x), "y": r2(ship.y),
                     "course": r1(ship.course), "speed": r1(ship.speed),
                     "damage": r1(self.damage.total),
                     "sunk": self.damage.ship_sunk,
                     "stations": {k: self.damage.station_down(k)
                                  for k in ("bridge", "sonar", "weapons", "opz",
                                            "radio", "engine", "flightdeck")}},
            "weapons": {"torpedoes": self.torpedo_count,
                        "vls": self.vls_cells, "ciws": self.ciws_ammo,
                        "aa": self.aa_ammo, "chaff_cd": r2(self.chaff_cd)},
            "subs": [{"id": s.id, "x": r2(s.x), "y": r2(s.y),
                      "depth": r1(s.depth), "course": r1(s.course),
                      "speed": r1(s.speed), "state": s.state,
                      "torps": s.torpedoes_left, "sunk": s.sunk}
                     for s in self.subs],
            "surfaces": ([{"id": w.id, "kind": "warship",
                           "name": getattr(w, "name", None),
                           "callsign": getattr(w, "callsign", None),
                           "mmsi": None, "imo": None, "ship_type": None,
                           "destination": None, "draught_m": None,
                           "length_m": None, "width_m": None,
                           "nav_status": None, "ais_heading": None,
                           "position_accuracy": None, "x": r2(w.x),
                           "y": r2(w.y), "course": r1(w.course),
                           "speed": r1(w.speed), "sunk": w.sunk,
                           "damage": r1(w.damage)}
                          for w in self.warships]
                         + [{"id": c.id, "kind": "civilian",
                             "name": getattr(c, "name", None),
                             "callsign": getattr(c, "callsign", None),
                             "mmsi": getattr(c, "live_mmsi", None),
                             "imo": getattr(c, "live_ais_details", {}).get("imo"),
                             "ship_type": getattr(c, "live_ais_details", {}).get("ship_type"),
                             "destination": getattr(c, "live_ais_details", {}).get("destination"),
                             "draught_m": getattr(c, "live_ais_details", {}).get("draught_m"),
                             "length_m": getattr(c, "live_ais_details", {}).get("length_m"),
                             "width_m": getattr(c, "live_ais_details", {}).get("width_m"),
                             "nav_status": getattr(c, "live_ais_details", {}).get("nav_status"),
                             "ais_heading": getattr(c, "live_ais_details", {}).get("heading"),
                             "position_accuracy": getattr(c, "live_ais_details", {}).get("position_accuracy"),
                             "x": r2(c.x),
                             "y": r2(c.y), "course": r1(c.course),
                             "speed": r1(c.speed), "sunk": c.sunk,
                             "damage": r1(c.damage)}
                            for c in self.civilians]),
            "animals": [{"id": a.id, "x": r2(a.x), "y": r2(a.y),
                         "dead": a.dead} for a in self.animals],
            "torpedoes": [{"id": t.idx, "x": r2(t.x), "y": r2(t.y),
                           "depth": r1(t.depth), "course": r1(t.course),
                           "state": t.state,
                           "target": getattr(t.target, "id", None)}
                          for t in self.torpedoes],
            "enemy_torpedoes": [{"id": t.id, "x": r2(t.x), "y": r2(t.y),
                                 "depth": r1(t.depth), "course": r1(t.course),
                                 "state": t.state}
                                for t in self.enemy_torpedoes],
            "decoys": [{"id": d.id, "x": r2(d.x), "y": r2(d.y),
                        "depth": r1(d.depth), "life": r1(d.life),
                        "dead": d.dead} for d in self.decoys],
            "asms": [{"seq": a.seq, "x": r2(a.x), "y": r2(a.y),
                      "course": r1(a.course), "state": a.state,
                      "jammer": a.jammer} for a in self.asms],
            "essms": [{"seq": e.seq, "x": r2(e.x), "y": r2(e.y),
                       "course": r1(e.course), "state": e.state}
                      for e in self.essms],
            "asrocs": [{"seq": a.seq, "x": r2(a.x), "y": r2(a.y),
                        "course": r1(a.course), "state": a.state}
                       for a in self.asrocs],
            "nixies": [{"seq": n.seq, "x": r2(n.x), "y": r2(n.y),
                        "depth": r1(n.depth), "dead": n.dead}
                       for n in self.nixies],
            "buoys": [{"seq": b.seq, "x": r2(b.x), "y": r2(b.y),
                       "battery_s": r1(b.battery_s), "active": b.active}
                      for b in self.buoys],
            "helo": {"state": self.helo.state, "x": r2(self.helo.x),
                     "y": r2(self.helo.y), "airborne": self.helo.airborne},
            "flights": ([{"seq": f.seq, "kind": f.kind, "callsign": None,
                          "icao24": None, "x": r2(f.x), "y": r2(f.y),
                          "course": r1(f.course), "speed": r1(f.speed),
                          "alt_m": None}
                         for f in self.flights.flights]
                        + [{"seq": a.seq, "kind": "live",
                            "callsign": a.callsign, "icao24": a.icao24,
                            "x": r2(a.x), "y": r2(a.y),
                            "course": r1(a.course), "speed": r1(a.speed),
                            "alt_m": r1(a.altitude_m)}
                           for a in sorted(self.live_traffic.aircraft.values(),
                                           key=lambda item: item.seq)
                           if not a.despawned]),
            "raiders": [{"seq": r.seq, "x": r2(r.x), "y": r2(r.y),
                         "course": r1(r.course), "phase": r.phase.value,
                         "hp": r.hp, "pending_asm": r.pending_asm}
                        for r in self.raiders],
            "radars": {"surface": self.surface_radar_on,
                       "air": self.air_radar_on},
        }
        return snap
