"""Deterministic, observation-bounded automation for individual stations."""

from __future__ import annotations

import math

from src.core import config
from src.core.station import Station


AUTOCREW_STATIONS = (
    "bridge", "sonar", "weapons", "damage", "opz", "radio", "engine",
    "helicopter", "eloka",
)
AUTOCREW_VERSION = 1
_CADENCE_S = {
    "bridge": 1.0,
    "sonar": 2.0,
    "weapons": 0.5,
    "damage": 1.0,
    "opz": 0.5,
    "radio": 5.0,
    "engine": 1.0,
    "helicopter": 1.0,
    "eloka": 3.0,
}
_DAMAGE_COMPARTMENT = {
    "bridge": "bridge", "sonar": "sonar", "weapons": "weapons",
    "damage": None, "opz": "opz", "radio": "radio", "engine": "engine",
    "helicopter": "flightdeck", "eloka": "opz",
}
_ACTIONS = frozenset({
    "off", "enabled", "monitoring", "tma", "bt", "tas", "released", "focused",
    "countermeasure", "air_defense", "repair", "hfdf", "identified",
    "limited_speed", "returning",
})


def station_key(station) -> str:
    if isinstance(station, Station):
        return "opz" if station is Station.RADAR else station.name.lower()
    if type(station) is str and station in AUTOCREW_STATIONS:
        return station
    raise ValueError("invalid Autocrew station")


class AutocrewController:
    """Own bounded station policies and their deterministic due times."""

    def __init__(self):
        self.enabled = {key: False for key in AUTOCREW_STATIONS}
        self.next_due_s = {key: 0.0 for key in AUTOCREW_STATIONS}
        self.last_action = {key: "off" for key in AUTOCREW_STATIONS}

    def set_enabled(self, station, enabled: bool, now: float) -> bool:
        key = station_key(station)
        if (type(enabled) is not bool or type(now) not in (int, float)
                or isinstance(now, bool) or not math.isfinite(now) or now < 0.0):
            raise ValueError("invalid Autocrew state")
        self.enabled[key] = enabled
        self.next_due_s[key] = float(now)
        self.last_action[key] = "enabled" if enabled else "off"
        return enabled

    def toggle(self, station, now: float) -> bool:
        key = station_key(station)
        return self.set_enabled(key, not self.enabled[key], now)

    def status(self, game, station) -> str:
        key = station_key(station)
        if not self.enabled[key]:
            return "off"
        enum_station = Station[key.upper()]
        if game.commander.station_leased(enum_station):
            return "suspended_remote"
        compartment = _DAMAGE_COMPARTMENT[key]
        if compartment is not None and game.damage.station_down(compartment):
            return "blocked_damage"
        return "active"

    def update(self, game) -> None:
        for key in AUTOCREW_STATIONS:
            due = self.next_due_s[key]
            if game.sim_t + 1e-9 < due or self.status(game, key) != "active":
                continue
            action = getattr(self, f"_{key}")(game)
            self.last_action[key] = action if action in _ACTIONS else "monitoring"
            cadence = _CADENCE_S[key]
            periods = max(1, int(math.floor((game.sim_t - due) / cadence)) + 1)
            self.next_due_s[key] = due + periods * cadence

    def serialize(self) -> dict:
        return {
            "version": AUTOCREW_VERSION,
            "stations": {
                key: {
                    "enabled": self.enabled[key],
                    "next_due_s": self.next_due_s[key],
                    "last_action": self.last_action[key],
                }
                for key in AUTOCREW_STATIONS
            },
        }

    @classmethod
    def restore(cls, data):
        if not cls.valid_state(data):
            raise ValueError("invalid Autocrew state")
        result = cls()
        for key, row in data["stations"].items():
            result.enabled[key] = row["enabled"]
            result.next_due_s[key] = float(row["next_due_s"])
            result.last_action[key] = row["last_action"]
        return result

    @staticmethod
    def valid_state(data, sim_t=None) -> bool:
        if (not isinstance(data, dict) or set(data) != {"version", "stations"}
                or type(data.get("version")) is not int
                or data["version"] != AUTOCREW_VERSION
                or not isinstance(data.get("stations"), dict)
                or set(data["stations"]) != set(AUTOCREW_STATIONS)):
            return False
        if (sim_t is not None and (type(sim_t) not in (int, float)
                                   or isinstance(sim_t, bool)
                                   or not math.isfinite(sim_t) or sim_t < 0.0)):
            return False
        maximum = 1e12 if sim_t is None else min(1e12, sim_t + max(_CADENCE_S.values()))
        for row in data["stations"].values():
            if (not isinstance(row, dict)
                    or set(row) != {"enabled", "next_due_s", "last_action"}
                    or type(row["enabled"]) is not bool
                    or type(row["next_due_s"]) not in (int, float)
                    or isinstance(row["next_due_s"], bool)
                    or not math.isfinite(row["next_due_s"])
                    or not 0.0 <= row["next_due_s"] <= maximum
                    or type(row["last_action"]) is not str
                    or row["last_action"] not in _ACTIONS):
                return False
        return True

    @staticmethod
    def _bridge(game):
        return "monitoring"

    @staticmethod
    def _sonar(game):
        if not game.sonar.tma_enabled:
            return ("tma" if game.set_sonar_tma_enabled(True) is True
                    else "monitoring")
        if game.sonar.bt_cooldown <= 0.0 and game.measure_sonar_bt() is True:
            return "bt"
        contacts = [contact for contact in game.sonar.contacts.values()
                    if 0.0 <= game.sim_t - contact.last_seen <= 2.0]
        for contact in sorted(contacts, key=lambda item: item.id):
            if contact.player_class in config.PLAYER_CLASSES and not contact.released_to_opz:
                if game.release_sonar_contact(contact, True) is True:
                    return "released"
        if contacts and (game.selected_contact not in contacts
                         or not game.sonar.focus_locked):
            best = max(contacts, key=lambda contact: (
                contact.quality, contact.confidence, -contact.id))
            if game.set_sonar_focus(best) is True:
                return "focused"
        tow = game.sonar.tow_status(game.ship.speed)
        if 3.0 <= game.ship.speed <= 12.0 and tow["state"] == "STOWED":
            return "tas" if game.set_sonar_tas(True) is True else "monitoring"
        if tow["available"] and game.sonar_mode != "TOWED":
            return ("tas" if game.set_sonar_array_mode("TOWED") is True
                    else "monitoring")
        return "monitoring"

    @staticmethod
    def _weapons(game):
        observed = any(
            contact.kind == "torpedo"
            and 0.0 <= game.sim_t - contact.last_seen <= 2.0
            for contact in game.sonar.contacts.values())
        if observed and not game.nixies and game.nixie_store.ready > 0:
            if game.deploy_nixie_result() is True:
                return "countermeasure"
        return "monitoring"

    @staticmethod
    def _damage(game):
        candidates = game.damage.repair_candidates()
        if not candidates:
            for team in sorted(game.damage.teams):
                destination = game.damage.teams[team]
                if destination is not None:
                    game.unassign_damage_team(team, destination)
            return "monitoring"
        order = tuple(game.damage.compartments)
        assigned = {key: 0 for key in candidates}
        changed = False
        for team in sorted(game.damage.teams):
            def priority(key):
                room = game.damage.compartments[key]
                critical = 30.0 if key in ("engine", "bridge", "opz", "weapons") else 0.0
                score = room.fire * 3.0 + room.flood + critical
                return (score / (1.0 + assigned[key] * 0.6), -order.index(key))

            destination = max(candidates, key=priority)
            assigned[destination] += 1
            if game.damage.teams[team] != destination:
                changed = game.assign_damage_team(team, destination) is True or changed
        return "repair" if changed else "monitoring"

    @staticmethod
    def _opz(game):
        tracks = sorted(
            game.asm_tracks(),
            key=lambda track: (float("inf") if track.range_nm is None else track.range_nm,
                               track.track_id))
        if not tracks:
            return "monitoring"
        track = tracks[0]
        loadout = game._air_defense_loadout
        current = any(item.seq == track.target_id and item.state == "LAUF"
                      for item in game.asms)
        positioned = (track.range_nm is not None and track.x is not None
                      and track.y is not None and track.position_seen is not None
                      and game.sim_t - track.position_seen
                      <= loadout["sam"]["observation_max_age_s"])
        if not current or not positioned:
            return "monitoring"
        if (game.softkill_store.ready > 0
                and track.range_nm <= loadout["softkill"]["range_nm"]):
            if game.launch_chaff_at(track) is True:
                return "air_defense"
        already_engaged = any(item.target_id == track.target_id for item in game.essms)
        if (not already_engaged and not game.damage.station_degraded("opz")
                and game.vls_cells > 0
                and len(game.essms) < loadout["vls"]["fire_channels"]
                and track.range_nm <= loadout["sam"]["range_nm"]
                and game.launch_essm_at(track) is True):
            return "air_defense"
        return "monitoring"

    @staticmethod
    def _radio(game):
        for report in sorted(game.hfdf_bearings(), key=game.hfdf_display_id):
            if report.age(game.sim_t) > config.RADAR_TRACK_STALE_S:
                continue
            previous = next((row for row in reversed(game.hfdf_log)
                             if row["track_id"] == report.track_id), None)
            baseline_ready = (previous is None or math.hypot(
                previous["observer_x"] - game.ship.x,
                previous["observer_y"] - game.ship.y) >= 1.0)
            if baseline_ready and game.capture_hfdf_report(report) is True:
                return "hfdf"
        return "monitoring"

    @staticmethod
    def _engine(game):
        cap = game.damage.engine_speed_cap()
        if game.ship.target_speed > cap:
            if game.set_engine_speed(cap) in (True, "ok"):
                return "limited_speed"
        return "monitoring"

    @staticmethod
    def _helicopter(game):
        # The aircraft model already performs distance-aware reserve recovery.
        return "monitoring"

    @staticmethod
    def _eloka(game):
        for track in sorted(game.eloka_tracks(), key=lambda item: item.track_key):
            if (game.eloka_annotation(track.track_key) is not None
                    or track.age(game.sim_t) > 5.0 or track.quality < 0.65):
                continue
            candidates = game.eloka_candidates(track)
            if not candidates:
                continue
            runner_up = candidates[1].score if len(candidates) > 1 else 0.0
            if candidates[0].score >= 0.85 and candidates[0].score - runner_up >= 0.15:
                if game.annotate_eloka_intercept(track, candidates[0].emitter_key) is True:
                    return "identified"
        return "monitoring"
