"""Bounded ASW stores, launchers, ASROC transit, and acoustic softkill."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

from src.core import config
from src.weapons import depth_charge


MAX_TUBES = 32
MAX_MAGAZINES = 16
MAX_COUNTERMEASURE_READY = 32
MAX_ASROCS = 128
MAX_TOWED_DECOYS = 4
ASW_STATE_VERSION = 1


def _integer(value, low: int, high: int, where: str) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{where}: bounded integer expected")
    return value


def _number(value, low: float, high: float, where: str) -> float:
    if (type(value) not in (int, float) or not math.isfinite(value)
            or not low <= value <= high):
        raise ValueError(f"{where}: bounded number expected")
    return float(value)


def _key(value, prefix: str, where: str) -> str:
    if (not isinstance(value, str) or not value.startswith(prefix)
            or len(value) > 128):
        raise ValueError(f"{where}: logical key expected")
    return value


def _object(value, fields: set[str], where: str) -> dict:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{where}: exact object expected")
    return value


@lru_cache(maxsize=1)
def ownship_loadout() -> dict:
    """Load and strictly validate the fictional F-217 ASW mission loadout."""
    path = resources.files("data.loadouts") / "ownship.json"
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    return validate_ownship_loadout(value)


def validate_ownship_loadout(value) -> dict:
    """Validate a detached F-217 loadout snapshot without filesystem access."""
    _object(value, {"version", "weapons", "launcher", "magazines",
                    "countermeasure"}, "ownship")
    if value["version"] != 2:
        raise ValueError("ownship.version: unsupported version")
    weapons = value["weapons"]
    if not isinstance(weapons, list) or not 1 <= len(weapons) <= 8:
        raise ValueError("ownship.weapons: bounded non-empty list expected")
    weapon_keys = set()
    for index, weapon in enumerate(weapons):
        _object(weapon, {"key", "runtime_profile_key"},
                f"ownship.weapons[{index}]")
        key = _key(weapon["key"], "weapon.", "ownship weapon key")
        _key(weapon["runtime_profile_key"], "", "runtime profile key")
        if key in weapon_keys:
            raise ValueError("ownship.weapons: duplicate key")
        weapon_keys.add(key)
    launcher = _object(value["launcher"], {
        "key", "mount_count", "ready_count", "reload_s", "weapon_keys"},
        "ownship.launcher")
    _key(launcher["key"], "launcher.", "ownship.launcher.key")
    mounts = _integer(launcher["mount_count"], 1, MAX_TUBES,
                      "ownship.launcher.mount_count")
    _integer(launcher["ready_count"], 0, mounts,
             "ownship.launcher.ready_count")
    _number(launcher["reload_s"], 0, 604800, "ownship.launcher.reload_s")
    if (not isinstance(launcher["weapon_keys"], list)
            or not launcher["weapon_keys"]
            or len(set(launcher["weapon_keys"])) != len(launcher["weapon_keys"])
            or not set(launcher["weapon_keys"]) <= weapon_keys):
        raise ValueError("ownship.launcher.weapon_keys: invalid compatibility")
    magazines = value["magazines"]
    if (not isinstance(magazines, list)
            or not 1 <= len(magazines) <= MAX_MAGAZINES):
        raise ValueError("ownship.magazines: bounded non-empty list expected")
    magazine_keys, magazine_weapons = set(), set()
    for index, magazine in enumerate(magazines):
        _object(magazine, {"key", "weapon_key", "share"},
                f"ownship.magazines[{index}]")
        key = _key(magazine["key"], "magazine.", "ownship.magazine.key")
        if magazine["weapon_key"] not in weapon_keys:
            raise ValueError("ownship.magazine.weapon_key: unknown weapon")
        if key in magazine_keys or magazine["weapon_key"] in magazine_weapons:
            raise ValueError("ownship.magazines: duplicate magazine or weapon")
        magazine_keys.add(key)
        magazine_weapons.add(magazine["weapon_key"])
        _integer(magazine["share"], 1, 100, f"ownship.magazines[{index}].share")
    countermeasure = _object(value["countermeasure"], {
        "key", "effect_type", "payload_key", "mission_count", "ready_count",
        "reload_s", "active_life_s", "tether_nm", "depth_m"},
        "ownship.countermeasure")
    _key(countermeasure["key"], "countermeasure.", "countermeasure.key")
    if countermeasure["effect_type"] != "towed_acoustic":
        raise ValueError("countermeasure.effect_type: towed_acoustic expected")
    _key(countermeasure["payload_key"], "", "countermeasure.payload_key")
    total = _integer(countermeasure["mission_count"], 0, 100,
                     "countermeasure.mission_count")
    _integer(countermeasure["ready_count"], 0,
             min(total, MAX_COUNTERMEASURE_READY), "countermeasure.ready_count")
    _number(countermeasure["reload_s"], 0, 604800, "countermeasure.reload_s")
    _number(countermeasure["active_life_s"], 1, 86400,
            "countermeasure.active_life_s")
    _number(countermeasure["tether_nm"], .01, 5, "countermeasure.tether_nm")
    _number(countermeasure["depth_m"], 0, 1000, "countermeasure.depth_m")
    return value


def split_stock(total: int, magazines) -> list[int]:
    """Mission stock per magazine from the loadout shares: every magazine but
    the first gets ``floor(total * share / sum)``, the first the remainder,
    so the total never changes and the primary type keeps the odd weapon."""
    total = max(0, int(total))
    shares = [int(magazine["share"]) for magazine in magazines]
    weight = max(1, sum(shares))
    secondary = [total * share // weight for share in shares[1:]]
    return [total - sum(secondary)] + secondary


@dataclass(slots=True)
class MagazineState:
    key: str
    weapon_key: str
    capacity: int
    stowed: int


@dataclass(slots=True)
class TubeState:
    index: int
    loaded_weapon_key: str | None = None
    loading_weapon_key: str | None = None
    reload_remaining_s: float = 0.0


class WeaponBattery:
    """One typed launcher with finite magazines and deterministic tube order."""

    def __init__(self, launcher_key: str, mount_count: int, ready_count: int,
                 reload_s: float, weapon_keys, magazines):
        self.launcher_key = launcher_key
        self.mount_count = int(mount_count)
        self.reload_s = float(reload_s)
        self.weapon_keys = tuple(weapon_keys)
        self.magazines = {
            item.key: MagazineState(item.key, item.weapon_key,
                                    int(item.capacity), int(item.stowed))
            for item in magazines
        }
        self.tubes = [TubeState(index) for index in range(self.mount_count)]
        # The type the tubes load next (the operator's selection; not saved
        # by the battery, the game restores it from its weapon settings).
        self.preferred_weapon_key = None
        # The tube the last ``fire`` emptied (transient, for the caller).
        self.last_fired_tube = None
        for tube in self.tubes[:min(int(ready_count), self.mount_count)]:
            weapon_key = self._reserve_weapon()
            if weapon_key is not None:
                tube.loaded_weapon_key = weapon_key

    @classmethod
    def from_catalog(cls, runtime_catalog, profile_key: str,
                     weapon_type: str) -> WeaponBattery | None:
        systems = runtime_catalog.profile_systems.get(profile_key)
        if systems is None:
            return None
        launchers = [runtime_catalog.launchers[key]
                     for key in systems.launcher_keys
                     if any(runtime_catalog.weapons[weapon].weapon_type == weapon_type
                            for weapon in runtime_catalog.launchers[key].weapon_keys)]
        if not launchers:
            return None
        launcher = sorted(launchers, key=lambda item: item.key)[0]
        compatible = tuple(key for key in launcher.weapon_keys
                           if runtime_catalog.weapons[key].weapon_type == weapon_type)
        magazines = []
        for key in sorted(systems.magazine_keys):
            profile = runtime_catalog.magazines[key]
            if profile.weapon_key in compatible:
                magazines.append(MagazineState(
                    key, profile.weapon_key, profile.mission_count,
                    profile.mission_count))
        if not magazines:
            return None
        return cls(launcher.key, launcher.mount_count, launcher.ready_count,
                   launcher.reload_s, compatible, magazines)

    @classmethod
    def ownship(cls, torpedo_count: int, definition=None) -> WeaponBattery:
        definition = definition or ownship_loadout()
        launcher = definition["launcher"]
        capacities = split_stock(int(torpedo_count), definition["magazines"])
        return cls(launcher["key"], launcher["mount_count"],
                   launcher["ready_count"], launcher["reload_s"],
                   launcher["weapon_keys"], [MagazineState(
                       magazine["key"], magazine["weapon_key"], capacity, capacity)
                       for magazine, capacity in zip(definition["magazines"], capacities)])

    def _reserve_weapon(self, preferred: str | None = None) -> str | None:
        """Take one stowed weapon: the preferred type first, else any type the
        launcher accepts (a tube never stays empty because one type ran out)."""
        choices = sorted(self.magazines.values(), key=lambda item: item.key)
        for wanted in ((preferred,) if preferred is not None else ()) + (None,):
            for magazine in choices:
                if (magazine.stowed > 0 and magazine.weapon_key in self.weapon_keys
                        and (wanted is None or magazine.weapon_key == wanted)):
                    magazine.stowed -= 1
                    return magazine.weapon_key
        return None

    def stowed_of(self, weapon_key: str) -> int:
        return sum(item.stowed for item in self.magazines.values()
                   if item.weapon_key == weapon_key)

    def remaining_of(self, weapon_key: str) -> int:
        """Stowed plus loaded plus loading weapons of one type."""
        return (self.stowed_of(weapon_key)
                + sum(tube.loaded_weapon_key == weapon_key for tube in self.tubes)
                + sum(tube.loading_weapon_key == weapon_key for tube in self.tubes))

    def loaded_count(self, weapon_key: str) -> int:
        return sum(tube.loaded_weapon_key == weapon_key for tube in self.tubes)

    def retask(self, weapon_key: str) -> bool:
        """Make ``weapon_key`` the type the tubes load next and, if no tube holds
        it yet, swap one tube over: its weapon returns to the magazine and the
        tube reloads with the wanted type. True when the type is or will be
        available in a tube."""
        if weapon_key not in self.weapon_keys:
            return False
        self.preferred_weapon_key = weapon_key
        if any(tube.loaded_weapon_key == weapon_key
               or tube.loading_weapon_key == weapon_key for tube in self.tubes):
            return True
        if self.stowed_of(weapon_key) <= 0:
            return False
        tube = next((item for item in self.tubes if item.loading_weapon_key is not None),
                    None) or next((item for item in self.tubes
                                   if item.loaded_weapon_key is not None), None)
        if tube is None:
            return False
        returned = tube.loading_weapon_key or tube.loaded_weapon_key
        for magazine in self.magazines.values():
            if magazine.weapon_key == returned and magazine.stowed < magazine.capacity:
                magazine.stowed += 1
                break
        tube.loaded_weapon_key = tube.loading_weapon_key = None
        tube.reload_remaining_s = 0.0
        self._start_reload(tube, weapon_key)
        return True

    @property
    def ready_count(self) -> int:
        return sum(tube.loaded_weapon_key is not None for tube in self.tubes)

    @property
    def loading_count(self) -> int:
        return sum(tube.loading_weapon_key is not None for tube in self.tubes)

    @property
    def remaining_total(self) -> int:
        return (sum(item.stowed for item in self.magazines.values())
                + self.ready_count + self.loading_count)

    @property
    def capacity_total(self) -> int:
        return sum(item.capacity for item in self.magazines.values())

    @property
    def next_reload_s(self) -> float:
        values = [tube.reload_remaining_s for tube in self.tubes
                  if tube.loading_weapon_key is not None]
        return min(values, default=0.0)

    def fire(self, weapon_key: str | None = None, *, tubes=None,
             auto_reload: bool = True) -> str | None:
        """Fire the first loaded tube (of ``tubes`` when given, by index);
        without ``auto_reload`` the tube stays empty until it is loaded."""
        tube = next((item for item in self.tubes
                     if item.loaded_weapon_key is not None
                     and (tubes is None or item.index in tubes)
                     and (weapon_key is None
                          or item.loaded_weapon_key == weapon_key)), None)
        if tube is None:
            return None
        fired = tube.loaded_weapon_key
        tube.loaded_weapon_key = None
        self.last_fired_tube = tube.index
        if auto_reload:
            self._start_reload(tube, fired)
        return fired

    def load_tube(self, index: int, preferred: str | None = None) -> bool:
        """Start loading one empty tube from the magazine (a crew's order)."""
        if not 0 <= index < len(self.tubes):
            return False
        tube = self.tubes[index]
        if tube.loaded_weapon_key is not None or tube.loading_weapon_key is not None:
            return False
        self._start_reload(tube, preferred if preferred is not None
                           else self.preferred_weapon_key)
        return tube.loaded_weapon_key is not None or tube.loading_weapon_key is not None

    def _start_reload(self, tube: TubeState, preferred: str | None = None) -> None:
        weapon_key = self._reserve_weapon(preferred)
        if weapon_key is None:
            return
        if self.reload_s <= 0.0:
            tube.loaded_weapon_key = weapon_key
        else:
            tube.loading_weapon_key = weapon_key
            tube.reload_remaining_s = self.reload_s

    def limit_to(self, count: int) -> None:
        """Keep at most ``count`` weapons aboard (a carried campaign stock):
        stowed weapons go first, then tubes still loading, then loaded ones."""
        count = max(0, int(count))
        for magazine in sorted(self.magazines.values(), key=lambda item: item.key,
                               reverse=True):
            excess = self.remaining_total - count
            if excess <= 0:
                return
            taken = min(excess, magazine.stowed)
            magazine.stowed -= taken
        for tube in reversed(self.tubes):
            if self.remaining_total <= count:
                return
            if tube.loading_weapon_key is not None:
                tube.loading_weapon_key = None
                tube.reload_remaining_s = 0.0
        for tube in reversed(self.tubes):
            if self.remaining_total <= count:
                return
            tube.loaded_weapon_key = None

    def replenish(self) -> None:
        """Replenishment at sea: every magazine back to its mission load
        (weapons in the tubes count against their own type)."""
        self.restock(self.capacity_total)

    def restock(self, count: int) -> int:
        """One load of a replenishment: at most ``count`` weapons into the
        magazines, never above their mission load (weapons in the tubes count
        against their own type). Returns how many came aboard."""
        left = max(0, int(count))
        in_tubes = {}
        for tube in self.tubes:
            for key in (tube.loaded_weapon_key, tube.loading_weapon_key):
                if key is not None:
                    in_tubes[key] = in_tubes.get(key, 0) + 1
        for magazine in sorted(self.magazines.values(), key=lambda item: item.key):
            held = in_tubes.get(magazine.weapon_key, 0)
            counted = min(held, magazine.capacity)
            in_tubes[magazine.weapon_key] = held - counted
            taken = min(left, max(0, magazine.capacity - counted - magazine.stowed))
            magazine.stowed += taken
            left -= taken
        return max(0, int(count)) - left

    def update(self, dt: float, readiness_scale: float = 1.0, *,
               auto_reload: bool = True) -> None:
        """Advance loading; ``auto_reload`` refills empty tubes on its own (a
        crewed submarine loads each tube on the crew's order instead)."""
        step = max(0.0, float(dt) * max(0.0, readiness_scale))
        for tube in self.tubes:
            if tube.loading_weapon_key is None:
                if tube.loaded_weapon_key is None and auto_reload:
                    self._start_reload(tube, self.preferred_weapon_key)
                continue
            tube.reload_remaining_s = max(0.0, tube.reload_remaining_s - step)
            if tube.reload_remaining_s <= 1e-9:
                tube.reload_remaining_s = 0.0
                tube.loaded_weapon_key = tube.loading_weapon_key
                tube.loading_weapon_key = None

    def serialize(self) -> dict:
        return {
            "launcher_key": self.launcher_key,
            "mount_count": self.mount_count,
            "reload_s": self.reload_s,
            "weapon_keys": list(self.weapon_keys),
            "magazines": [
                {"key": item.key, "weapon_key": item.weapon_key,
                 "capacity": item.capacity, "stowed": item.stowed}
                for item in sorted(self.magazines.values(), key=lambda item: item.key)
            ],
            "tubes": [
                {"index": item.index,
                 "loaded_weapon_key": item.loaded_weapon_key,
                 "loading_weapon_key": item.loading_weapon_key,
                 "reload_remaining_s": item.reload_remaining_s}
                for item in self.tubes
            ],
        }

    @classmethod
    def restore(cls, value: dict) -> WeaponBattery:
        if not valid_battery_state(value):
            raise ValueError("invalid ASW battery state")
        magazines = [MagazineState(row["key"], row["weapon_key"],
                                    row["capacity"], row["stowed"])
                     for row in value["magazines"]]
        battery = cls(value["launcher_key"], value["mount_count"], 0,
                      value["reload_s"], value["weapon_keys"], magazines)
        battery.tubes = [TubeState(row["index"], row["loaded_weapon_key"],
                                   row["loading_weapon_key"],
                                   float(row["reload_remaining_s"]))
                         for row in value["tubes"]]
        return battery


def valid_battery_state(value) -> bool:
    try:
        _object(value, {"launcher_key", "mount_count", "reload_s", "weapon_keys",
                        "magazines", "tubes"}, "battery")
        _key(value["launcher_key"], "launcher.", "battery.launcher_key")
        mounts = _integer(value["mount_count"], 1, MAX_TUBES,
                          "battery.mount_count")
        reload_s = _number(value["reload_s"], 0, 604800, "battery.reload_s")
        weapon_keys = value["weapon_keys"]
        if (not isinstance(weapon_keys, list) or not weapon_keys
                or len(weapon_keys) > 32 or len(set(weapon_keys)) != len(weapon_keys)):
            return False
        for key in weapon_keys:
            _key(key, "weapon.", "battery.weapon_key")
        magazines = value["magazines"]
        if (not isinstance(magazines, list) or not magazines
                or len(magazines) > MAX_MAGAZINES):
            return False
        seen = set()
        for row in magazines:
            _object(row, {"key", "weapon_key", "capacity", "stowed"}, "magazine")
            key = _key(row["key"], "magazine.", "magazine.key")
            if key in seen or row["weapon_key"] not in weapon_keys:
                return False
            seen.add(key)
            capacity = _integer(row["capacity"], 0, 10000, "magazine.capacity")
            _integer(row["stowed"], 0, capacity, "magazine.stowed")
        tubes = value["tubes"]
        if not isinstance(tubes, list) or len(tubes) != mounts:
            return False
        for index, row in enumerate(tubes):
            _object(row, {"index", "loaded_weapon_key", "loading_weapon_key",
                          "reload_remaining_s"}, "tube")
            if row["index"] != index:
                return False
            loaded, loading = row["loaded_weapon_key"], row["loading_weapon_key"]
            if loaded is not None and loaded not in weapon_keys:
                return False
            if loading is not None and loading not in weapon_keys:
                return False
            if loaded is not None and loading is not None:
                return False
            remaining = _number(row["reload_remaining_s"], 0, reload_s, "tube.reload")
            if (loading is None) != (remaining == 0.0):
                return False
        total = (sum(row["stowed"] for row in magazines)
                 + sum(row["loaded_weapon_key"] is not None
                        or row["loading_weapon_key"] is not None for row in tubes))
        if total > sum(row["capacity"] for row in magazines):
            return False
        for weapon_key in weapon_keys:
            available = sum(row["capacity"] for row in magazines
                            if row["weapon_key"] == weapon_key)
            retained = sum(row["stowed"] for row in magazines
                           if row["weapon_key"] == weapon_key)
            retained += sum(row["loaded_weapon_key"] == weapon_key
                            or row["loading_weapon_key"] == weapon_key
                            for row in tubes)
            if retained > available:
                return False
        return True
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def battery_matches_catalog(value, runtime_catalog, profile_key: str,
                            weapon_type: str) -> bool:
    """Require a saved battery to match one profile's catalog components."""
    if not valid_battery_state(value):
        return False
    systems = runtime_catalog.profile_systems.get(profile_key)
    launcher = runtime_catalog.launchers.get(value["launcher_key"])
    if systems is None or launcher is None \
            or launcher.key not in systems.launcher_keys:
        return False
    compatible = tuple(key for key in launcher.weapon_keys
                       if runtime_catalog.weapons[key].weapon_type == weapon_type)
    if (tuple(value["weapon_keys"]) != compatible
            or value["mount_count"] != launcher.mount_count
            or value["reload_s"] != launcher.reload_s):
        return False
    expected = {
        key: runtime_catalog.magazines[key]
        for key in systems.magazine_keys
        if runtime_catalog.magazines[key].weapon_key in compatible
    }
    magazines = {row["key"]: row for row in value["magazines"]}
    return set(magazines) == set(expected) and all(
        magazines[key]["weapon_key"] == profile.weapon_key
        and magazines[key]["capacity"] == profile.mission_count
        for key, profile in expected.items())


class ConsumableStore:
    """Finite ready/stowed consumables with deterministic reload slots."""

    def __init__(self, key: str, effect_type: str, payload_key: str | None,
                 mission_count: int, ready_count: int, reload_s: float):
        self.key = key
        self.effect_type = effect_type
        self.payload_key = payload_key
        self.capacity = int(mission_count)
        self.ready = min(int(ready_count), self.capacity)
        self.stowed = self.capacity - self.ready
        self.reload_s = float(reload_s)
        self.loading: list[float] = []

    @classmethod
    def from_catalog(cls, runtime_catalog, profile_key: str,
                     effect_type: str) -> ConsumableStore | None:
        systems = runtime_catalog.profile_systems.get(profile_key)
        if systems is None:
            return None
        profiles = [runtime_catalog.countermeasures[key]
                    for key in systems.countermeasure_keys
                    if runtime_catalog.countermeasures[key].effect_type == effect_type]
        if not profiles:
            return None
        profile = sorted(profiles, key=lambda item: item.key)[0]
        return cls(profile.key, profile.effect_type, profile.payload_key,
                   profile.mission_count, profile.ready_count, profile.reload_s)

    @classmethod
    def ownship(cls, definition=None) -> ConsumableStore:
        value = (definition or ownship_loadout())["countermeasure"]
        return cls(value["key"], value["effect_type"], value["payload_key"],
                   value["mission_count"], value["ready_count"], value["reload_s"])

    @property
    def remaining_total(self) -> int:
        return self.ready + self.stowed + len(self.loading)

    def restock(self, count: int) -> int:
        """Replenishment at sea: at most ``count`` into the stowage, never
        above the mission load. Returns how many came aboard."""
        taken = min(max(0, int(count)), max(0, self.capacity - self.remaining_total))
        self.stowed += taken
        if self.ready + len(self.loading) == 0 and self.stowed > 0:
            # An empty launcher starts loading from the new stowage.
            self.stowed -= 1
            if self.reload_s <= 0:
                self.ready += 1
            else:
                self.loading.append(self.reload_s)
        return taken

    def fire(self) -> bool:
        if self.ready <= 0:
            return False
        self.ready -= 1
        if self.stowed > 0:
            self.stowed -= 1
            if self.reload_s <= 0:
                self.ready += 1
            else:
                self.loading.append(self.reload_s)
        return True

    def update(self, dt: float) -> None:
        completed = 0
        updated = []
        for remaining in self.loading:
            remaining = max(0.0, remaining - max(0.0, dt))
            if remaining <= 0.0:
                completed += 1
            else:
                updated.append(remaining)
        self.loading = updated
        self.ready += completed

    def serialize(self) -> dict:
        return {"key": self.key, "effect_type": self.effect_type,
                "payload_key": self.payload_key, "capacity": self.capacity,
                "ready": self.ready, "stowed": self.stowed,
                "reload_s": self.reload_s, "loading": list(self.loading)}

    @classmethod
    def restore(cls, value: dict) -> ConsumableStore:
        if not valid_consumable_state(value):
            raise ValueError("invalid consumable state")
        result = cls(value["key"], value["effect_type"], value["payload_key"],
                     value["capacity"], 0, value["reload_s"])
        result.ready, result.stowed = value["ready"], value["stowed"]
        result.loading = [float(item) for item in value["loading"]]
        return result


def valid_consumable_state(value) -> bool:
    try:
        _object(value, {"key", "effect_type", "payload_key", "capacity", "ready",
                        "stowed", "reload_s", "loading"}, "consumable")
        _key(value["key"], "countermeasure.", "consumable.key")
        if value["effect_type"] not in (
                "acoustic_decoy", "towed_acoustic", "chaff", "rf_softkill"):
            return False
        if value["payload_key"] is not None:
            _key(value["payload_key"], "", "consumable.payload_key")
        capacity = _integer(value["capacity"], 0, 10000, "consumable.capacity")
        ready = _integer(value["ready"], 0, min(capacity, MAX_COUNTERMEASURE_READY),
                         "consumable.ready")
        stowed = _integer(value["stowed"], 0, capacity, "consumable.stowed")
        reload_s = _number(value["reload_s"], 0, 604800, "consumable.reload_s")
        loading = value["loading"]
        if not isinstance(loading, list) or len(loading) > MAX_COUNTERMEASURE_READY:
            return False
        if any(_number(item, 0, reload_s, "consumable.loading") <= 0
               for item in loading):
            return False
        return ready + stowed + len(loading) <= capacity
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def consumable_matches_catalog(value, runtime_catalog, profile_key: str,
                               effect_type: str) -> bool:
    """Require a saved consumable store to match a profile component."""
    if not valid_consumable_state(value):
        return False
    systems = runtime_catalog.profile_systems.get(profile_key)
    profile = runtime_catalog.countermeasures.get(value["key"])
    if (systems is None or profile is None
            or profile.key not in systems.countermeasure_keys
            or profile.effect_type != effect_type):
        return False
    return (value["effect_type"] == profile.effect_type
            and value["payload_key"] == profile.payload_key
            and value["capacity"] == profile.mission_count
            and value["reload_s"] == profile.reload_s
            and value["ready"] + len(value["loading"]) <= profile.ready_count)


class ASROC:
    """Ballistic transit to an immutable observed datum."""

    def __init__(self, x: float, y: float, datum_x: float, datum_y: float,
                 seq: int, weapon_key: str, payload_profile_key: str,
                 speed_kn: float, range_nm: float, side: str,
                 target_depth_m: float = 60.0,
                 launch_platform_id: int | None = None):
        self.x, self.y = x, y
        self.datum_x, self.datum_y = datum_x, datum_y
        self.seq = seq
        self.weapon_key = weapon_key
        self.payload_profile_key = payload_profile_key
        self.speed_kn = speed_kn
        self.range_nm = range_nm
        self.side = side
        self.launch_platform_id = launch_platform_id
        self.target_depth_m = target_depth_m
        self.travel = 0.0
        self.state = "FLIGHT"
        self.course = math.degrees(math.atan2(datum_x - x, -(datum_y - y))) % 360.0

    def update(self, dt: float, world=None) -> bool:
        """Advance transit and return true exactly on a valid water entry."""
        if self.state != "FLIGHT":
            return False
        distance = math.hypot(self.datum_x - self.x, self.datum_y - self.y)
        step = min(distance, config.kn_to_nm_per_s(self.speed_kn) * max(0.0, dt),
                   max(0.0, self.range_nm - self.travel))
        self.x += step * math.sin(math.radians(self.course))
        self.y -= step * math.cos(math.radians(self.course))
        self.travel += step
        if distance <= step + 1e-9:
            self.x, self.y = self.datum_x, self.datum_y
            clear = (world is None or (
                0 <= self.x <= world.size_nm and 0 <= self.y <= world.size_nm
                and not world.on_land(self.x, self.y)
                and world.depth_m(self.x, self.y) > 5.0))
            self.state = "WATER_ENTRY" if clear else "SASE"
            return clear
        if self.travel >= self.range_nm:
            self.state = "SASE"
        return False

    def serialize(self) -> dict:
        return {key: getattr(self, key) for key in (
            "x", "y", "datum_x", "datum_y", "seq", "weapon_key",
            "payload_profile_key", "speed_kn", "range_nm", "side",
            "launch_platform_id", "target_depth_m", "travel", "state",
            "course")}

    @classmethod
    def restore(cls, value: dict) -> ASROC:
        result = cls(value["x"], value["y"], value["datum_x"], value["datum_y"],
                     value["seq"], value["weapon_key"],
                     value["payload_profile_key"], value["speed_kn"],
                     value["range_nm"], value["side"], value["target_depth_m"],
                     value["launch_platform_id"])
        result.travel = value["travel"]
        result.state = value["state"]
        result.course = value["course"]
        return result


NIXIE_LEVEL_DB = 12.0          # designed emission above a quiet hull
NIXIE_MAX_TOW_KN = 25.0        # the tow cable parts above this speed
NIXIE_DESIGN_TOW_KN = 15.0     # speed at which it streams at its design depth
NIXIE_HEADING_TAU_S = 60.0     # cable lag in turns


class TowedAcousticDecoy:
    """Towed acoustic decoy on a cable.

    Quasi-static cable equilibrium: hydrodynamic drag (~v^2) against the
    body's wet weight sets the cable angle, so the decoy streams deeper and
    closer astern when the ship slows and shallower/farther when it speeds up
    (depth ~ design depth * (v_design / v)^2, bounded).  The tow bearing lags
    the ship's course in turns; above NIXIE_MAX_TOW_KN the cable parts.  The
    emitted level is designed louder than a quiet hull and it moves with the
    ship, so a Doppler-gated seeker cannot reject it."""

    acoustic_level_db = NIXIE_LEVEL_DB

    def __init__(self, seq: int, ship, *, life_s: float, tether_nm: float,
                 depth_m: float, tow_heading: float | None = None):
        self.seq = seq
        self.life = life_s
        self.tether_nm = tether_nm
        self.design_depth = depth_m
        self.depth = depth_m
        self.dead = False
        self.state = "RUN"
        self.sunk = False
        self.speed_kn = float(getattr(ship, "speed", NIXIE_DESIGN_TOW_KN))
        self.tow_heading = (ship.course % 360.0 if tow_heading is None
                            else tow_heading % 360.0)
        self.x, self.y = ship.x, ship.y
        self._place(ship)

    def _place(self, ship) -> None:
        speed = max(3.0, self.speed_kn)
        factor = min(6.0, max(0.5, (NIXIE_DESIGN_TOW_KN / speed) ** 2))
        cable_m = self.tether_nm * 1852.0
        self.depth = min(self.design_depth * factor, 0.9 * cable_m)
        layback_nm = math.sqrt(max(0.0, cable_m ** 2 - self.depth ** 2)) / 1852.0
        angle = math.radians((self.tow_heading + 180.0) % 360.0)
        self.x = ship.x + layback_nm * math.sin(angle)
        self.y = ship.y - layback_nm * math.cos(angle)

    def update(self, dt: float, ship, world) -> None:
        if self.dead:
            return
        self.life = max(0.0, self.life - max(0.0, dt))
        self.speed_kn = float(getattr(ship, "speed", self.speed_kn))
        if self.life <= 0.0 or self.speed_kn > NIXIE_MAX_TOW_KN:
            self.dead = True
            self.state = "SASE"
            return
        self.tow_heading = (self.tow_heading + config.angle_diff_deg(
            ship.course, self.tow_heading) * (1.0 - math.exp(
                -max(0.0, dt) / NIXIE_HEADING_TAU_S))) % 360.0
        self._place(ship)
        if world is not None and (world.on_land(self.x, self.y)
                                  or world.depth_m(self.x, self.y) <= self.depth):
            self.dead = True
            self.state = "SASE"

    def serialize(self) -> dict:
        return {"seq": self.seq, "x": self.x, "y": self.y,
                "depth": self.design_depth, "life": self.life,
                "tether_nm": self.tether_nm, "dead": self.dead,
                "state": self.state, "tow_heading": self.tow_heading}

    @classmethod
    def restore(cls, value: dict, ship) -> TowedAcousticDecoy:
        result = cls(value["seq"], ship, life_s=value["life"],
                     tether_nm=value["tether_nm"], depth_m=value["depth"],
                     tow_heading=value["tow_heading"])
        result.x, result.y = value["x"], value["y"]
        result.dead, result.state = value["dead"], value["state"]
        return result


def valid_asw_state(value, torpedo_total: int, torpedo_count: int,
                    runtime_catalog) -> bool:
    """Validate the complete ASW block in the canonical save schema."""
    try:
        _object(value, {"version", "loadout", "player_battery",
                        "countermeasure", "nixies", "nixie_seq", "asrocs",
                        "asroc_seq", "depth_charges", "depth_charge_seq",
                        "own_stores"}, "asw")
        if not depth_charge.valid_state(value["depth_charges"],
                                        value["depth_charge_seq"],
                                        value["own_stores"], 1_000_000.0):
            return False
        if value["version"] != ASW_STATE_VERSION:
            return False
        if not valid_battery_state(value["player_battery"]):
            return False
        battery = WeaponBattery.restore(value["player_battery"])
        if (battery.capacity_total != torpedo_total
                or battery.remaining_total != torpedo_count):
            return False
        definition = validate_ownship_loadout(value["loadout"])
        if any((profile := runtime_catalog.torpedoes.get(
                weapon["runtime_profile_key"])) is None
               or profile.used_by != "frigate" for weapon in definition["weapons"]):
            return False
        launcher = definition["launcher"]
        battery_state = value["player_battery"]
        magazines = sorted(battery_state["magazines"], key=lambda row: row["key"])
        expected = sorted(zip(definition["magazines"],
                              split_stock(torpedo_total, definition["magazines"])),
                          key=lambda pair: pair[0]["key"])
        if (battery_state["launcher_key"] != launcher["key"]
                or battery_state["mount_count"] != launcher["mount_count"]
                or battery_state["reload_s"] != launcher["reload_s"]
                or battery_state["weapon_keys"] != launcher["weapon_keys"]
                or len(magazines) != len(expected)
                or any(row["key"] != magazine["key"]
                       or row["weapon_key"] != magazine["weapon_key"]
                       or row["capacity"] != capacity
                       for row, (magazine, capacity) in zip(magazines, expected))):
            return False
        if not valid_consumable_state(value["countermeasure"]):
            return False
        countermeasure = definition["countermeasure"]
        store = value["countermeasure"]
        if (store["key"] != countermeasure["key"]
                or store["effect_type"] != countermeasure["effect_type"]
                or store["payload_key"] != countermeasure["payload_key"]
                or store["capacity"] != countermeasure["mission_count"]
                or store["reload_s"] != countermeasure["reload_s"]
                or store["ready"] + len(store["loading"])
                    > countermeasure["ready_count"]):
            return False
        nixie_seq = _integer(value["nixie_seq"], 0, 2**63 - 1, "asw.nixie_seq")
        nixies = value["nixies"]
        if not isinstance(nixies, list) or len(nixies) > MAX_TOWED_DECOYS:
            return False
        if len(nixies) > store["capacity"] - (
                store["ready"] + store["stowed"] + len(store["loading"])):
            return False
        nixie_ids = set()
        for row in nixies:
            _object(row, {"seq", "x", "y", "depth", "life", "tether_nm",
                          "dead", "state", "tow_heading"},
                    "asw.nixie")
            heading = _number(row["tow_heading"], 0, 360, "asw.nixie.tow_heading")
            if heading >= 360:
                return False
            seq = _integer(row["seq"], 1, nixie_seq, "asw.nixie.seq")
            if seq in nixie_ids:
                return False
            nixie_ids.add(seq)
            _number(row["x"], -1_000_000, 1_000_000, "asw.nixie.x")
            _number(row["y"], -1_000_000, 1_000_000, "asw.nixie.y")
            _number(row["depth"], 0, 1000, "asw.nixie.depth")
            life = _number(row["life"], 0, 86400, "asw.nixie.life")
            _number(row["tether_nm"], .01, 5, "asw.nixie.tether_nm")
            if (type(row["dead"]) is not bool
                    or row["state"] not in ("RUN", "SASE")
                    or row["dead"] != (row["state"] == "SASE")
                    or (not row["dead"] and life <= 0)
                    or life > countermeasure["active_life_s"]
                    or row["depth"] != countermeasure["depth_m"]
                    or row["tether_nm"] != countermeasure["tether_nm"]):
                return False
        asroc_seq = _integer(value["asroc_seq"], 0, 2**63 - 1, "asw.asroc_seq")
        asrocs = value["asrocs"]
        if not isinstance(asrocs, list) or len(asrocs) > MAX_ASROCS:
            return False
        asroc_ids = set()
        own_asrocs = 0
        for row in asrocs:
            _object(row, {"x", "y", "datum_x", "datum_y", "seq", "weapon_key",
                          "payload_profile_key", "speed_kn", "range_nm", "side",
                          "launch_platform_id", "target_depth_m", "travel",
                          "state", "course"}, "asroc")
            seq = _integer(row["seq"], 1, asroc_seq, "asroc.seq")
            # The frigate's own ASROC has no platform id and its own key.
            own = row["weapon_key"] == depth_charge.OWN_ASROC_KEY
            if own:
                if row["launch_platform_id"] is not None:
                    return False
                own_asrocs += 1
            else:
                _integer(row["launch_platform_id"], 1, 2**63 - 1,
                         "asroc.launch_platform_id")
            if seq in asroc_ids:
                return False
            asroc_ids.add(seq)
            for field in ("x", "y", "datum_x", "datum_y"):
                _number(row[field], -1_000_000, 1_000_000, f"asroc.{field}")
            _key(row["weapon_key"], "weapon.", "asroc.weapon_key")
            weapon = runtime_catalog.weapons.get(row["weapon_key"])
            profile = runtime_catalog.torpedoes.get(row["payload_profile_key"])
            if own:
                maximum_speed, maximum_range = (depth_charge.OWN_ASROC_SPEED_KN,
                                                depth_charge.OWN_ASROC_RANGE_NM[1])
            elif weapon is not None:
                maximum_speed, maximum_range = (weapon.maximum_speed_kn,
                                                weapon.engagement_range_nm[1])
            if ((not own and (weapon is None or weapon.weapon_type != "asroc"))
                    or profile is None or profile.used_by not in ("frigate", "helo")
                    or row["payload_profile_key"] != runtime_catalog.runtime_bindings[
                        "helicopter_torpedo"]):
                return False
            speed = _number(row["speed_kn"], .001, 10000, "asroc.speed_kn")
            distance = _number(row["range_nm"], .001, 10000, "asroc.range_nm")
            if speed != maximum_speed or distance != maximum_range:
                return False
            _number(row["target_depth_m"], 0, 10000, "asroc.target_depth_m")
            _number(row["travel"], 0, distance, "asroc.travel")
            course = _number(row["course"], 0, 360, "asroc.course")
            if course == 360 or row["side"] != "friendly":
                return False
            if row["state"] != "FLIGHT":
                return False
        # Own ASROCs in flight came out of the ship's store.
        if own_asrocs > depth_charge.OWN_ASROC_STOCK - value["own_stores"]["asroc"]:
            return False
        return True
    except (KeyError, TypeError, ValueError, OverflowError):
        return False
