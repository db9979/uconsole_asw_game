"""Weapon orders of the frigate's stations: helicopter torpedo, ESSM,
chaff, Nixie, flak/CIWS release, target selection and classification
interlocks, torpedo settings and launch.  Local keys and Remote Crew
commands pass the same checks.  Moved verbatim from ``game_operator.py``;
``OperatorMixin`` inherits ``WeaponOrdersMixin``.
"""

import math

from src.core import config
from src.core.i18n import display_value, message, raw_text
from src.physics import torpedo_dyn
from src.core.station import Station
from src.core.limits import MAX_DECOYS
from src.enemies.decoy import Decoy
from src.air.asm import ESSM
from src.air import chaff as chaff_physics
from src.weapons.torpedo import Torpedo
from src.weapons.asw import MAX_TOWED_DECOYS, TowedAcousticDecoy
from src.sensors.fusion import live_members


class WeaponOrdersMixin:
    """Weapon-order half of ``OperatorMixin``."""

    def launch_helo_torpedo(self) -> None:
        """Leichttorpedo vom HSP-5 (eigene Munition, nicht Fregatten-Rohre)."""
        if (self.target is None
                or self.sim_t - self.target.last_seen >= config.SONAR_CONTACT_LOST_S):
            self.target = None
            self.flash(message("runtime.target.invalid"))
            return
        self.launch_helicopter_torpedo_at(self.target, self.torpedo_depth)

    def launch_helicopter_torpedo_at(self, contact, depth_m: float):
        """Release a helicopter torpedo against one explicit sonar observation."""
        if (contact is None or type(depth_m) not in (int, float)
                or not math.isfinite(depth_m) or not 10 <= depth_m <= 300
                or self.sim_t - contact.last_seen >= config.SONAR_CONTACT_LOST_S):
            self.flash(message("runtime.target.invalid"))
            return "invalid_target"
        blocked = self._target_affiliation_interlock(contact)
        if blocked is not None:
            self.flash(message("runtime.roe.blocked",
                               affiliation=display_value("affiliation", blocked, self.tr)))
            return "roe_blocked"
        if self.weapons_tight():
            self.flash(message("runtime.roe.weapons_tight"))
            return "roe_blocked"
        if self.roe == "STD" and not self._contact_range_fresh(contact):
            self.flash(message("runtime.target.not_located"))
            return "not_located"
        if self.weapon_classification(contact) != "U_BOOT":
            self.flash(message("runtime.target.air_class"))
            return "not_classified"
        if not self.helo.airborne:
            self.flash(message("runtime.helo.not_airborne"))
            return "not_ready"
        if self.helo.torps <= 0:
            self.flash(message("runtime.helo_no_torpedoes"))
            return "empty"
        if not self.helo.water_entry_clear(self.world):
            self.flash(message("runtime.helo.water_required"))
            return "water_required"
        tgt = self._find_target(contact.target_id)
        lv = self.difficulty
        range_nm = (contact.range_est if contact.range_est is not None
                    else config.ROE_FREE_LAUNCH_RANGE_NM)
        use_fix = (self._contact_range_fresh(contact)
                   and contact.observed_x is not None
                   and contact.observed_y is not None)
        datum = self.helo.release_datum_from_ship_observation(
            self.ship, contact.bearing, range_nm,
            bearing_uncertainty_deg=max(0.0, (1.0 - contact.quality) * 8.0),
            range_uncertainty_nm=contact.range_sigma_nm or 0.0,
            datum_x=contact.observed_x if use_fix else None,
            datum_y=contact.observed_y if use_fix else None)
        torp = self.helo.drop_torpedo(
            tgt, depth_m, self.torpedo_seq + 1,
            kill_dist_nm=lv["kill_dist_nm"], kill_depth_m=lv["kill_depth_m"],
            guidance_x=datum.x_nm, guidance_y=datum.y_nm, world=self.world)
        if torp is None:
            return "not_ready"
        self.torpedo_seq += 1
        self.torpedoes.append(torp)
        self._emit_sound("water_entry")
        self.flash(message("runtime.helo_torpedo.launched",
                           torpedo=self.torpedo_seq), 2.0)
        self.feed.add(self.world.format_time(), "waffen",
                      message("runtime.helo_torpedo.feed",
                              torpedo=self.torpedo_seq, contact=contact.id))
        return True

    @staticmethod
    def _missile_seq(track):
        """Internal missile sequence behind an ``M-`` air track, else None.

        An ASM cue can also sit on an aircraft track; fire control resolves
        the engaged weapon only through the missile's own track namespace.
        """
        track_id = str(getattr(track, "track_id", ""))
        suffix = track_id[2:]
        return int(suffix) if track_id.startswith("M-") and suffix.isdigit() else None

    def _cycle_asm_track(self, delta: int) -> None:
        n = len(self.asm_tracks())
        if n == 0:
            self.asm_sel = 0
            return
        self.asm_sel = (self.asm_sel + delta) % n

    def launch_essm(self) -> None:
        tracks = self.asm_tracks()
        track = tracks[min(self.asm_sel, len(tracks) - 1)] if tracks else None
        self.launch_essm_at(track)

    def launch_essm_at(self, track):
        """Launch against an explicit current positioned ASM observation."""
        profiles = self._air_defense_loadout
        if self.damage.station_down("opz") or self.damage.station_degraded("opz"):
            self.flash(message("runtime.opz.degraded"))
            return "opz_degraded"
        if self.vls_cells <= 0:
            self.flash(message("runtime.vls.empty"))
            return "empty"
        if len(self.essms) >= profiles["vls"]["fire_channels"]:
            self.flash(message("runtime.vls.empty"))
            return "active_limit"
        if not any(item is track for item in self.asm_tracks()):
            self.flash(message("runtime.asm.none"))
            return "invalid_target"
        sam = profiles["sam"]
        if track.range_nm is None or track.range_nm > sam["range_nm"]:
            self.flash(message("runtime.asm.range", range=f"{sam['range_nm']:.0f}"))
            return "out_of_range"
        if (track.x is None or track.y is None or track.position_seen is None
                or self.sim_t - track.position_seen
                > sam["observation_max_age_s"]):
            self.flash(message("runtime.asm.stale"))
            return "stale_ref"
        missile_seq = self._missile_seq(track)
        tgt = next((a for a in self.asms if a.seq == missile_seq), None)
        course = math.degrees(math.atan2(track.x - self.ship.x,
                                        -(track.y - self.ship.y))) % 360.0
        self.essm_seq += 1
        self.essms.append(ESSM(self.ship.x, self.ship.y, course, tgt,
                               self.essm_seq,
                               guidance_x=track.x, guidance_y=track.y,
                               target_id=missile_seq, profile=sam))
        self.vls_cells -= 1
        self._emit_sound("missile_launch")
        self.announce(message("runtime.essm.launched", cells=self.vls_cells),
                      "waffen", 2.0)
        return True

    def launch_chaff(self) -> None:
        tracks = self.asm_tracks()
        track = tracks[min(self.asm_sel, len(tracks) - 1)] if tracks else None
        self.launch_chaff_at(track)

    def launch_chaff_at(self, track):
        """Deploy one softkill round against an explicit ASM observation."""
        if self.damage.station_down("opz"):
            self.flash(message("runtime.chaff.disabled"))
            return "opz_down"
        if self.softkill_store.ready <= 0:
            self.flash(message("runtime.chaff.cooldown", seconds=f"{self.chaff_cd:.0f}"))
            return "not_ready"
        if track is None or not any(item is track for item in self.asm_tracks()):
            self.flash(message("runtime.chaff.none"))
            return "invalid_target"
        a = next((item for item in self.asms
                  if item.seq == self._missile_seq(track)
                  and item.state == "LAUF"), None)
        profile = self._air_defense_loadout["softkill"]
        if (a is not None and track.range_nm is not None
                and track.position_seen is not None
                and self.sim_t - track.position_seen <= self._air_defense_loadout[
                    "sam"]["observation_max_age_s"]
                and track.range_nm <= profile["range_nm"]
                and self.softkill_store.fire()):
            self.chaff_seq += 1
            threat = math.degrees(math.atan2(a.x - self.ship.x,
                                             -(a.y - self.ship.y))) % 360.0
            cloud = chaff_physics.ChaffCloud(
                self.chaff_seq, *chaff_physics.lay_position(
                    self.ship.x, self.ship.y, threat, self.chaff_seq))
            self.chaff_clouds = (self.chaff_clouds + [cloud])[
                -chaff_physics.MAX_CLOUDS:]
            arrival = (math.hypot(a.x - cloud.x, a.y - cloud.y)
                       / max(config.kn_to_nm_per_s(a.speed_kn), 1e-9))
            broke = a.launch_chaff(self.rng_asm, profile, cloud_seq=cloud.seq,
                                   arrival_s=arrival)
            self.chaff_cd = min(self.softkill_store.loading, default=0.0)
            self.announce(message("runtime.chaff.decoyed" if broke
                                  else "runtime.chaff.jammed"), "waffen")
            return True
        else:
            self.flash(message("runtime.chaff.none"))
            return "stale_ref"

    def deploy_nixie(self) -> None:
        """Deploy one finite towed acoustic countermeasure from own ship."""
        self.deploy_nixie_result()

    def deploy_nixie_result(self):
        if len(self.nixies) >= MAX_TOWED_DECOYS:
            self.flash(message("runtime.nixie.active"))
            return "active_limit"
        if not self.nixie_store.fire():
            self.flash(message("runtime.nixie.empty"))
            return "empty"
        definition = self._ownship_loadout["countermeasure"]
        self.nixie_seq += 1
        self.nixies.append(TowedAcousticDecoy(
            self.nixie_seq, self.ship, life_s=definition["active_life_s"],
            tether_nm=definition["tether_nm"], depth_m=definition["depth_m"]))
        self.announce(message("runtime.nixie.deployed",
                              count=self.nixie_store.remaining_total), "waffen")
        return True

    def set_flak_authorized(self, authorized: bool):
        """Fire-release gate for the AA gun; it never engages FLG raiders
        while withheld, regardless of ammo/cooldown/range readiness."""
        if type(authorized) is not bool:
            return "invalid_value"
        if self.damage.station_down("weapons"):
            return "weapons_down"
        self.flak_authorized = authorized
        return True

    def set_ciws_authorized(self, authorized: bool):
        """Fire-release gate for CIWS; it never engages inbound ASMs while
        withheld, regardless of ammo/cooldown/range readiness."""
        if type(authorized) is not bool:
            return "invalid_value"
        if self.damage.station_down("opz"):
            return "opz_down"
        self.ciws_authorized = authorized
        return True

    def set_target(self) -> None:
        contacts = [c for c in self.sonar.active_contacts()
                    if self.sim_t - c.last_seen < config.SONAR_CONTACT_LOST_S]
        if not contacts:
            self.target = None
            self.flash(message("runtime.contacts.none"))
            return
        if self.selected_contact in contacts:
            best = self.selected_contact
        else:
            best = max(contacts, key=lambda c: c.confidence)
        if self.designate_sonar_target(best) is not True:
            return
        self.flash(message("runtime.target.set", contact=best.id), 2.0)

    def torpedo_readiness(self) -> tuple[str, tuple]:
        """Return an operator-readable fire-control state and color."""
        if (self.target is None
                or self.sim_t - self.target.last_seen >= config.SONAR_CONTACT_LOST_S):
            return "BLOCKIERT: KEIN ZIEL", config.COLOR_WARN
        blocked = self._target_affiliation_interlock()
        if blocked is not None:
            return (f"BLOCKIERT: ZUGEHOERIGKEIT {blocked}",
                    config.COLOR_DANGER)
        if self.weapons_tight():
            return "BLOCKIERT: WAFFEN GESPERRT", config.COLOR_DANGER
        if not self._contact_range_fresh(self.target) and self.roe == "STD":
            return "BLOCKIERT: KEINE ENTFERNUNG", config.COLOR_WARN
        if self.weapon_classification(self.target) not in ("U_BOOT", "KAMPFSCHIFF"):
            return ("BLOCKIERT: NICHT ALS U-BOOT/KAMPFSCHIFF KLASSIFIZIERT",
                    config.COLOR_WARN)
        if self.torpedo_count <= 0:
            return "BLOCKIERT: KEINE TORPEDOS", config.COLOR_DANGER
        if self.player_torpedo_battery.ready_count <= 0:
            return "BLOCKIERT: KEIN ROHR BEREIT", config.COLOR_WARN
        if len([t for t in self.torpedoes if t.state == "RUN"]) >= \
                config.TORP_MAX_IN_AIR[config.TORP_DOCTRINE]:
            return "BLOCKIERT: SALVENLIMIT", config.COLOR_WARN
        if self.damage.station_down("weapons") or \
                self.damage.station_degraded("weapons"):
            return "BLOCKIERT: WAFFENZENTRALE GESTOERT", config.COLOR_DANGER
        return "FEUER FREI", config.COLOR_OK

    def _contact_affiliations(self, contact) -> list:
        """Return every OPZ affiliation annotation bound to a sonar target."""
        if contact is None:
            return []
        # Operator annotations outlive measurements. Aircraft/missile sequence
        # IDs are a separate namespace and must not annotate a sonar target.
        affiliations = [self.opz_affiliations.get(
            f"{prefix}-{contact.target_id}", "UNKNOWN")
            for prefix in ("U", "S")]
        self.opz_source_observations()
        affiliations.extend(
            self.opz_affiliation(observation_id)
            for observation_id, source in self._opz_source_bindings.items()
            if (source is contact or getattr(source, "target_id", None)
                == contact.target_id and str(
                    getattr(source, "track_id", "")).split("-", 1)[0]
                in ("U", "S")))
        # An affiliation set on an OPZ fusion covers every sonar report in it.
        affiliations.extend(
            self.opz_fusion.fusion_affiliations[fusion.fusion_id]
            for fusion in self._contact_fusions(contact)
            if fusion.fusion_id in self.opz_fusion.fusion_affiliations)
        return affiliations

    def _contact_fusions(self, contact) -> list:
        """Intact OPZ fusions holding a report bound to this sonar contact.

        Read-only: a fusion counts only while its member reports are current
        (``live_members``, the condition ``OPZFusion.prune`` applies), so the result
        never depends on whether a frame pruned the register first.
        """
        if contact is None or not self.opz_fusion.fusions:
            return []
        current = {item.observation_id for item in self.opz_source_observations()}
        bindings = self._opz_source_bindings
        fusions = []
        for _, fusion in sorted(self.opz_fusion.fusions.items()):
            members = live_members(fusion, current)
            if members is not None and any(bindings.get(member) is contact
                                           for member in members):
                fusions.append(fusion)
        return fusions

    def weapon_classification(self, contact) -> str | None:
        """Operator class that fire control uses for one sonar contact.

        The sonar contact's own class wins; otherwise the class the OPZ gave a
        fusion holding this contact's report applies.
        """
        if contact is None:
            return None
        if contact.player_class in config.PLAYER_CLASSES:
            return contact.player_class
        return next((self.opz_fusion.classifications[fusion.fusion_id]
                     for fusion in self._contact_fusions(contact)
                     if self.opz_fusion.classifications.get(fusion.fusion_id)
                     in config.PLAYER_CLASSES), None)

    def contact_affiliation(self, contact) -> str:
        """Resolve one affiliation for a contact, FRIEND/NEUTRAL taking
        precedence over HOSTILE so callers stay conservative by default."""
        affiliations = self._contact_affiliations(contact)
        return next((value for value in ("FRIEND", "NEUTRAL", "HOSTILE")
                     if value in affiliations), "UNKNOWN")

    def weapons_tight(self) -> bool:
        """Scenario 13 is peacetime: no weapon may be released at a submarine."""
        from src.core import boat_missions
        return boat_missions.mode(self) == "trail"

    def _target_affiliation_interlock(self, contact=None):
        """Return a protected OPZ affiliation for the assigned sonar target."""
        contact = self.target if contact is None else contact
        if contact is None:
            return None
        affiliations = self._contact_affiliations(contact)
        return next((value for value in ("FRIEND", "NEUTRAL")
                     if value in affiliations), None)

    def _contact_range_fresh(self, contact) -> bool:
        if contact is None or contact.range_est is None:
            return False
        observed_at = (contact.range_seen if contact.range_seen is not None
                       else contact.last_seen)
        return self.sim_t - observed_at <= config.SONAR_CONTACT_LOST_S

    # --- M9: Kontakt-Auswahl & manuelle Klassifizierung ---

    def _cycle_selected_contact(self, delta: int) -> None:
        cs = sorted((c for c in self.sonar.contacts.values()
                     if self.sim_t - c.last_seen < config.SONAR_CONTACT_LOST_S),
                    key=lambda c: c.id)
        if not cs:
            self.selected_contact = None
            return
        try:
            i = cs.index(self.selected_contact)
        except ValueError:
            i = -1
        self.selected_contact = cs[(i + delta) % len(cs)]
        if self.sonar.focus_locked:
            self.sonar.reset_listening_history()

    def _cycle_helo_contact(self, delta: int) -> None:
        """W2: browse only what the helicopter's own dip has plotted - its
        own active/passive picture, independent of the ship's sonar picture -
        so the operator can select one and release it to CIC from here."""
        cs = sorted((c for c in self.sonar.contacts.values()
                     if (c.dip_last_seen is not None
                         and 0 <= self.sim_t - c.dip_last_seen
                         < config.SONAR_CONTACT_LOST_S)
                     or any(fix["source"] == "DIPPING"
                            for fix in c.active_fixes(self.sim_t))
                     or any(0 <= self.sim_t - row["measured_at"]
                            < config.SONAR_CONTACT_LOST_S
                            for row in c.buoy_reports.values())),
                    key=lambda c: c.id)
        if not cs:
            self.selected_contact = None
            self.flash(message("runtime.contact.none_selected"))
            return
        try:
            i = cs.index(self.selected_contact)
        except ValueError:
            i = -1
        self.selected_contact = cs[(i + delta) % len(cs)]

    def _cycle_classification(self) -> None:
        if self.selected_contact is None:
            self.flash(message("runtime.contact.none_selected"))
            return
        if self.selected_contact.target_id not in self.sonar.contacts:
            self.selected_contact = None
            return
        c = self.selected_contact
        order = [None] + list(config.PLAYER_CLASSES)
        value = order[(order.index(c.player_class) + 1) % len(order)]
        if self.classify_sonar_contact(c, value) is not True:
            return
        self.flash(message("runtime.contact.classified", contact=c.id,
                           classification=display_value("classification",
                                                        c.player_class, self.tr)), 2.0)

    def _toggle_sonar_release(self) -> None:
        contact = self.selected_contact
        if contact is None:
            self.flash(message("runtime.contact.none_selected"))
            return
        helicopter = self.station is Station.HELICOPTER
        buoy = helicopter and self.helo_sensor_source == "BUOY"
        released = not (contact.buoy_released_to_opz if buoy else
                        contact.dip_released_to_opz if helicopter
                        else contact.released_to_opz)
        if self.release_sonar_contact(contact, released,
                                      source="buoy" if buoy else
                                      "helicopter" if helicopter else "sonar") is not True:
            return
        self.flash(message("runtime.sonar.release" if released
                           else "runtime.sonar.withdraw",
                           contact=contact.id), 2.0)

    def _find_target(self, target_id: int):
        for s in self.subs:
            if s.id == target_id:
                return s
        for a in self.animals:
            if a.id == target_id:
                return a
        for d in self.decoys:
            if d.id == target_id:
                return d
        for civilian in self.civilians:
            if civilian.id == target_id:
                return civilian
        for w in self.warships:
            if w.id == target_id:
                return w
        for t in self.enemy_torpedoes:
            if t.id == target_id:
                return t
        return None

    # --- torpedo settings (type, pattern, enable point, salvo) --------------

    def torpedo_type_choices(self) -> list:
        """(weapon key, profile name, remaining) of every ship torpedo type."""
        battery = self.player_torpedo_battery
        rows = []
        for weapon in self._ownship_loadout["weapons"]:
            profile = self.runtime_catalog.torpedoes.get(weapon["runtime_profile_key"])
            rows.append((weapon["key"], profile.name if profile is not None
                         else weapon["runtime_profile_key"],
                         battery.remaining_of(weapon["key"])))
        return rows

    def set_torpedo_type(self, weapon_key):
        """Select the torpedo type the tubes load next (a tube swaps over if
        none holds it yet). Returns True or a reason code."""
        if weapon_key not in {row[0] for row in self.torpedo_type_choices()}:
            return "invalid_value"
        self.torpedo_type = weapon_key
        if not self.player_torpedo_battery.retask(weapon_key):
            self.flash(message("runtime.torpedo.type_empty"), 2.0)
            return "empty"
        name = next(row[1] for row in self.torpedo_type_choices() if row[0] == weapon_key)
        self.flash(message("runtime.torpedo.type", name=raw_text(name)), 2.0)
        return True

    def _cycle_torpedo_type(self) -> None:
        keys = [row[0] for row in self.torpedo_type_choices()]
        index = keys.index(self.torpedo_type) if self.torpedo_type in keys else -1
        self.set_torpedo_type(keys[(index + 1) % len(keys)])

    def set_torpedo_pattern(self, pattern):
        if pattern not in torpedo_dyn.SEARCH_PATTERNS:
            return "invalid_value"
        self.torpedo_pattern = pattern
        self.flash(message("runtime.torpedo.pattern",
                           pattern=display_value("torpedo_pattern", pattern, self.tr)), 2.0)
        return True

    def _cycle_torpedo_pattern(self) -> None:
        patterns = torpedo_dyn.SEARCH_PATTERNS
        self.set_torpedo_pattern(patterns[(patterns.index(self.torpedo_pattern) + 1)
                                          % len(patterns)])

    def set_torpedo_enable(self, enable_nm):
        if (type(enable_nm) not in (int, float) or not math.isfinite(enable_nm)
                or not torpedo_dyn.ENABLE_RANGE_MIN_NM <= enable_nm
                <= torpedo_dyn.ENABLE_RANGE_MAX_NM):
            return "invalid_value"
        self.torpedo_enable_nm = torpedo_dyn.quantized_enable_nm(enable_nm)
        self.flash(message("runtime.torpedo.enable",
                           range=f"{self.torpedo_enable_nm:.1f}"), 2.0)
        return True

    def _adjust_torpedo_enable(self, steps: int) -> None:
        wanted = self.torpedo_enable_nm + steps * torpedo_dyn.ENABLE_RANGE_STEP_NM
        self.set_torpedo_enable(config.clamp(wanted, torpedo_dyn.ENABLE_RANGE_MIN_NM,
                                             torpedo_dyn.ENABLE_RANGE_MAX_NM))

    def set_torpedo_salvo(self, salvo):
        if type(salvo) is not int or salvo not in torpedo_dyn.SALVO_SIZES:
            return "invalid_value"
        self.torpedo_salvo = salvo
        self.flash(message("runtime.torpedo.salvo", salvo=salvo), 2.0)
        return True

    def _cycle_torpedo_salvo(self) -> None:
        sizes = torpedo_dyn.SALVO_SIZES
        self.set_torpedo_salvo(sizes[(sizes.index(self.torpedo_salvo) + 1) % len(sizes)])

    # Ctrl+Enter is the only fire key: D/A/Z/R/Shift+R at Weapons and D on
    # OPZ page 3 only choose what it fires (operator focus, never saved).
    WEAPON_CHOICES = ("torpedo", "air_torpedo", "asroc", "depth_charges", "rbu",
                      "rbu_defence")
    OPZ_WEAPON_CHOICES = ("essm", "mpa_torpedo")

    def select_weapon(self, kind: str) -> str:
        """Choose the Weapons station's fire key weapon; the chosen one
        again goes back to the ship's torpedo."""
        if kind not in self.WEAPON_CHOICES:
            return self.weapon_select
        if kind == getattr(self, "weapon_select", "torpedo"):
            kind = "torpedo"
        self.weapon_select = kind
        self.flash(message("runtime.weapon.selected",
                           weapon=message("weapons.select." + kind)), 2.0)
        return kind

    def fire_selected_weapon(self):
        """Ctrl+Enter at Weapons: fire the chosen weapon through its own
        order (same checks as every other caller)."""
        kind = getattr(self, "weapon_select", "torpedo")
        if kind == "air_torpedo":
            return self.launch_helo_torpedo()
        if kind == "asroc":
            return self.fire_own_asroc()
        if kind == "depth_charges":
            return self.drop_depth_charges()
        if kind == "rbu":
            return self.fire_rbu()
        if kind == "rbu_defence":
            return self.fire_rbu_defence()
        return self.launch_torpedo()

    def select_opz_weapon(self, kind: str) -> str:
        """OPZ page 3: D chooses the patrol aircraft's torpedo for Ctrl+Enter
        (again: back to ESSM)."""
        if kind not in self.OPZ_WEAPON_CHOICES:
            return self.opz_weapon
        if kind == getattr(self, "opz_weapon", "essm"):
            kind = "essm"
        self.opz_weapon = kind
        self.flash(message("runtime.weapon.selected",
                           weapon=message("weapons.select." + kind)), 2.0)
        return True

    def launch_torpedo(self) -> None:
        if (self.target is None
                or self.sim_t - self.target.last_seen >= config.SONAR_CONTACT_LOST_S):
            self.target = None
            self.flash(message("runtime.target.invalid"))
            return
        self.launch_torpedo_at(self.target, self.torpedo_depth)

    def launch_torpedo_at(self, contact, depth_m: float):
        """Launch from ownship against one explicit sonar observation."""
        if (contact is None or type(depth_m) not in (int, float)
                or not math.isfinite(depth_m) or not 10 <= depth_m <= 300
                or self.sim_t - contact.last_seen >= config.SONAR_CONTACT_LOST_S):
            self.flash(message("runtime.target.invalid"))
            return "invalid_target"
        blocked = self._target_affiliation_interlock(contact)
        if blocked is not None:
            self.flash(message("runtime.roe.blocked",
                               affiliation=display_value("affiliation", blocked, self.tr)))
            return "roe_blocked"
        if self.weapons_tight():
            self.flash(message("runtime.roe.weapons_tight"))
            return "roe_blocked"
        if self.roe == "STD":
            if not self._contact_range_fresh(contact):
                self.flash(message("runtime.target.not_located"))
                return "not_located"
            if self.weapon_classification(contact) not in ("U_BOOT", "KAMPFSCHIFF"):
                self.flash(message("runtime.target.not_classified"))
                return "not_classified"
        else:
            if self.weapon_classification(contact) not in ("U_BOOT", "KAMPFSCHIFF"):
                self.flash(message("runtime.target.not_classified"))
                return "not_classified"
        active_torpedoes = len([t for t in self.torpedoes if t.state == "RUN"])
        salvo_limit = config.TORP_MAX_IN_AIR[config.TORP_DOCTRINE]
        if active_torpedoes >= salvo_limit:
            self.flash(message("runtime.salvo.limit", limit=salvo_limit))
            return "salvo_limit"
        if self.torpedo_count <= 0:
            self.flash(message("event.no_torpedoes"))
            return "empty"
        if self.player_torpedo_battery.ready_count <= 0:
            self.flash(message("runtime.torpedo.no_tube"))
            return "no_tube"
        if self.damage.station_down("weapons"):
            self.flash(message("runtime.weapons.down"))
            return "weapons_down"
        if self.damage.station_degraded("weapons"):
            self.flash(message("runtime.weapons.degraded"))
            return "weapons_degraded"
        tgt = self._find_target(contact.target_id)
        if (contact.observed_x is not None
                and contact.observed_y is not None
                and self._contact_range_fresh(contact)):
            est_x, est_y = contact.observed_x, contact.observed_y
        else:
            range_nm = (contact.range_est if contact.range_est is not None
                        else config.ROE_FREE_LAUNCH_RANGE_NM)
            est_x = self.ship.x + range_nm * math.sin(math.radians(contact.bearing))
            est_y = self.ship.y - range_nm * math.cos(math.radians(contact.bearing))
        course = math.degrees(math.atan2(est_x - self.ship.x,
                                         -(est_y - self.ship.y))) % 360.0
        battery = self.player_torpedo_battery
        if battery.loaded_count(self.torpedo_type) <= 0:
            self.flash(message("runtime.torpedo.no_tube_type"))
            return "no_tube_type"
        # A two-torpedo salvo opens a spread about the line of fire; every
        # weapon gets its own datum turned about the ship by the same angle.
        salvo = 2 if (self.torpedo_salvo == 2
                      and battery.loaded_count(self.torpedo_type) >= 2
                      and active_torpedoes + 2 <= salvo_limit) else 1
        launches = []
        for launch_course in torpedo_dyn.spread_courses(course, salvo):
            offset = config.angle_diff_deg(launch_course, course)
            launches.append((launch_course, *torpedo_dyn.rotate_datum(
                self.ship.x, self.ship.y, est_x, est_y, offset)))
        launched = []
        for launch_course, datum_x, datum_y in launches:
            weapon_key = battery.fire(self.torpedo_type)
            if weapon_key is None:
                break
            self.torpedo_seq += 1
            weapon_definition = next(
                item
                for item in self._ownship_loadout["weapons"]
                if item["key"] == weapon_key)
            profile_key = weapon_definition["runtime_profile_key"]
            profile = self.runtime_catalog.torpedoes[profile_key]
            self.torpedoes.append(Torpedo(self.ship.x, self.ship.y, launch_course,
                                          depth_m, tgt, self.torpedo_seq,
                                          kill_dist_nm=self.difficulty["kill_dist_nm"],
                                          kill_depth_m=self.difficulty["kill_depth_m"],
                                          guidance_x=datum_x, guidance_y=datum_y,
                                          profile=profile, time_since_launch=0.0,
                                          pattern=self.torpedo_pattern,
                                          enable_nm=self.torpedo_enable_nm))
            launched.append(self.torpedo_seq)
        if not launched:
            self.flash(message("runtime.torpedo.no_tube"))
            return "no_tube"
        self.torpedo_count = self.player_torpedo_battery.remaining_total
        # W2: the launch transient itself is a loud, one-time acoustic event,
        # audible passively much farther than a torpedo's own terminal seeker
        # ever gets (TORP_HOME_RANGE_NM) - distinct concept, separate gate.
        for sub in self.subs:
            if (not sub.sunk and sub.state != "SINKING"
                    and math.hypot(self.ship.x - sub.x, self.ship.y - sub.y)
                    <= config.SUB_TORPEDO_ALERT_NM
                    and not self.world.sonar_path_blocked(
                        self.ship.x, self.ship.y, 5.0,
                        sub.x, sub.y, sub.depth)):
                sub.alert_torpedo(source=(self.ship.x, self.ship.y))
        for warship in self.warships:
            if (not warship.sunk and warship.doctrine == "surface_combatant"
                    and math.hypot(self.ship.x - warship.x, self.ship.y - warship.y)
                    <= config.SUB_TORPEDO_ALERT_NM
                    and not self.world.sonar_path_blocked(
                        self.ship.x, self.ship.y, 5.0,
                        warship.x, warship.y, warship.depth)):
                bearing = math.degrees(math.atan2(
                    self.ship.x - warship.x,
                    -(self.ship.y - warship.y))) % 360.0
                warship.alert_torpedo(bearing)
                if (warship.countermeasures_left > 0 and warship.side == "hostile"
                        and len(self.decoys) < MAX_DECOYS):
                    # Stream an acoustic decoy while turning away.
                    warship.countermeasures_left -= 1
                    decoy_profile = self.runtime_catalog.decoys[
                        self.runtime_catalog.runtime_bindings["submarine_decoy"]]
                    self.decoys.append(Decoy(
                        warship.x, warship.y, 10.0, self.rng_asw, decoy_profile,
                        self.runtime_catalog.acoustic_for(decoy_profile.key),
                        source_id=warship.id))
        self._emit_sound("torpedo_launch")
        for torpedo_idx in launched:
            self.flash(message("runtime.torpedo.launched", torpedo=torpedo_idx), 2.0)
            self.feed.add(self.world.format_time(), "waffen",
                          message("runtime.torpedo.feed", torpedo=torpedo_idx,
                                  contact=contact.id))
        return True
