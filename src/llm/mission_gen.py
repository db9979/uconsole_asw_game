"""Mission generator: a mission from a few words, through the strict validator.

The player describes a mission ("two submarines in fog at night, protect the
tanker"); the model answers with a mission in the Mission Editor's format.
The answer is never trusted: it is merged onto the editor's default mission
(unknown fields dropped, world fixed at 500 NM, own key and version), the
frigate's sink targets are set to every placed hostile submarine as the
runtime requires, and then the same ``validate_mission`` the editor and the
web planner use decides.  On problems the model gets one chance to fix them;
a second failure returns the problems and nothing is stored.

The result is an ordinary editor mission: it opens in the Mission Editor (or
lands in the web planner's library) for the player to check, change, save
and start.  Wall time only; nothing here touches a running mission.
"""

from __future__ import annotations

import copy
import json

from src.core.mission_definition import (OBJECTIVE_TYPES, PLAYER_SIDES,
                                         default_mission, validate_mission)
from src.llm import prompts
from src.llm.client import parse_json_object

REQUEST_MAX = 500
PROFILES_MAX = 60
ISSUES_MAX = 8
_TOP = ("name", "description", "seed", "side", "boat_id", "player", "environment",
        "units", "objective", "events")
_KIND_ORDER = ("sub", "surface", "aircraft", "animal", "decoy", "torpedo")


def valid_request(text) -> bool:
    return (type(text) is str and 0 < len(text.strip()) <= REQUEST_MAX
            and all(char.isprintable() for char in text))


def builtin_profiles() -> dict:
    """{key: kind} of every packaged unit profile the editor offers."""
    from src.data.catalog import CATALOG
    from src.ui.unit_editor import catalog_builtins

    return {key: kind for key, (kind, profile) in catalog_builtins(CATALOG).items()
            if kind != "torpedo" or getattr(profile, "used_by", "") == "enemy"}


def schema_help(side: str, profiles: dict) -> str:
    """The mission format for the model, with the profile keys it may use."""
    example = default_mission("user.example")
    example.update(side=side, name="Example", description="One line for the briefing.")
    if side == "uboot":
        example["boat_id"] = "boat"
        example["units"]["exact"] = [
            {"id": "boat", "profile": _first(profiles, "sub"), "side": "hostile",
             "placement": {"kind": "fixed", "x": 250.0, "y": 230.0},
             "course_deg": 90.0, "speed_kn": 5.0, "depth_m": 60.0},
            {"id": "tanker", "profile": _first(profiles, "surface"), "side": "neutral",
             "placement": {"kind": "fixed", "x": 280.0, "y": 240.0},
             "course_deg": 270.0, "speed_kn": 12.0}]
        example["objective"].update(type="sink", target_ids=["tanker"])
    else:
        example["units"]["exact"] = [
            {"id": "sub1", "profile": _first(profiles, "sub"), "side": "hostile",
             "placement": {"kind": "fixed", "x": 262.0, "y": 238.0},
             "course_deg": 200.0, "speed_kn": 5.0, "depth_m": 80.0}]
        example["objective"].update(type="sink", target_ids=["sub1"])
    example["events"] = [{"id": "e1", "at_s": 600.0, "type": "message",
                          "message": "HQ: contact reported to the north."}]
    rows = []
    for kind in _KIND_ORDER:
        keys = sorted(key for key, value in profiles.items() if value == kind)
        if keys:
            rows.append(f"- {kind}: " + ", ".join(keys[:PROFILES_MAX // 3]))
    objectives = ", ".join(OBJECTIVE_TYPES if side == "frigate" else ("sink", "survive", "reach"))
    return (
        "Format (JSON, all distances in nautical miles on a 500 x 500 NM map, x east, "
        "y south, the player near the middle; courses in degrees 0-359; time in seconds):\n"
        + json.dumps(example, ensure_ascii=False) + "\n"
        "Rules:\n"
        f"- side is \"{side}\" (do not change it).\n"
        "- units.exact: placed units; side is hostile, friendly or neutral; depth_m only for "
        "submarines. Keep units within 5 to 40 NM of the player.\n"
        "- units.random_groups (optional): {id, profiles:[keys], count:[min,max], side, "
        "placement}.\n"
        f"- objective.type: one of {objectives}; time_limit_s 1800 to 7200; target_ids "
        "name unit ids; reach needs objective.reach {x, y, radius_nm}.\n"
        + ("- boat_id names the player's own submarine: a placed hostile submarine.\n"
           if side == "uboot" else
           "- sink: target_ids are the hostile submarines; protect: friendly or neutral "
           "ships to keep afloat.\n")
        + "- environment.weather: clear, rain, storm or fog; sea_state 0-9; time_hour 0-23.9.\n"
        "- events (optional): {id, at_s, type: message|weather|objective|spawn, ...}.\n"
        "Profile keys you may use:\n" + "\n".join(rows))


def _first(profiles: dict, kind: str) -> str:
    keys = sorted(key for key, value in profiles.items() if value == kind)
    return keys[0] if keys else "unknown"


def normalize(answer, key: str, side: str, profiles: dict) -> dict | None:
    """The model's mission merged onto the defaults; None when no object came."""
    if not isinstance(answer, dict):
        return None
    if isinstance(answer.get("mission"), dict):
        answer = answer["mission"]
    mission = default_mission(key)
    for name in _TOP:
        if name not in answer:
            continue
        value = copy.deepcopy(answer[name])
        if isinstance(mission.get(name), dict) and isinstance(value, dict):
            merged = dict(mission[name])
            merged.update({k: v for k, v in value.items() if k in mission[name]})
            mission[name] = merged
        else:
            mission[name] = value
    mission.update(version=default_mission()["version"], key=key, side=side,
                   world={"kind": "fixed", "size_nm": 500.0, "sectors": []})
    if side == "frigate":
        mission["boat_id"] = ""
    units = mission.get("units")
    if isinstance(units, dict):
        units.setdefault("exact", [])
        units.setdefault("random_groups", [])
    objective = mission.get("objective")
    if isinstance(objective, dict):
        objective.setdefault("reach", {"x": 250.0, "y": 250.0, "radius_nm": 2.0})
        objective.setdefault("target_ids", [])
        exact = units.get("exact") if isinstance(units, dict) else None
        if side == "frigate" and objective.get("type") == "sink" and isinstance(exact, list):
            # The runtime sinks exactly every placed hostile submarine.
            objective["target_ids"] = [
                unit.get("id") for unit in exact
                if isinstance(unit, dict) and unit.get("side") == "hostile"
                and profiles.get(unit.get("profile")) == "sub"]
    if not isinstance(mission.get("events"), list):
        mission["events"] = []
    return mission


class MissionGenerator:
    """One generation at a time; ``owner`` tells who asked (editor or web)."""

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self.status = "idle"          # idle | pending | done | failed
        self.owner = None
        self.mission = None
        self.error = None
        self.issues = []
        self._request = None
        self._messages = None
        self._fixed = False
        self._key = None
        self._side = "frigate"
        self._profiles = {}
        self._profile_keys = None
        self._service = None

    @property
    def busy(self) -> bool:
        return self.status == "pending"

    def start(self, service, language: str, side: str, text: str, *, key: str, owner,
              profiles: dict | None = None, profile_keys=None):
        """Ask the model; None when sent, else why not (llm_off, llm_busy,
        invalid_value)."""
        if side not in PLAYER_SIDES or not valid_request(text):
            return "invalid_value"
        if not service.active:
            return "llm_off"
        if self.busy:
            return "llm_busy"
        profiles = dict(profiles if profiles is not None else builtin_profiles())
        messages = prompts.mission(language, schema_help(side, profiles), " ".join(text.split()))
        request = service.submit("mission", messages, max_tokens=1_600, temperature=0.7,
                                 json_mode=True)
        if request is None:
            return "llm_busy"
        self.reset()
        self.status, self.owner = "pending", owner
        self._request, self._messages = request, messages
        self._key, self._side, self._profiles = key, side, profiles
        self._profile_keys = set(profile_keys) if profile_keys is not None else set(profiles)
        self._service = service
        return None

    def poll(self) -> bool:
        """True when the job just finished (done or failed)."""
        request = self._request
        if self.status != "pending" or request is None or not request.finished:
            return False
        if not request.ok:
            return self._fail(request.error or "network")
        mission = normalize(parse_json_object(request.text), self._key, self._side,
                            self._profiles)
        problems = (validate_mission(mission, self._profile_keys) if mission is not None
                    else None)
        if mission is not None and not problems:
            self.status, self.mission, self._request = "done", mission, None
            return True
        if not self._fixed:
            # One chance to fix what the validator found.
            listing = ("no JSON object found" if problems is None else "\n".join(
                f"- {problem.path}: {problem.message}" for problem in problems[:ISSUES_MAX]))
            messages = self._messages + [{"role": "assistant", "content": request.text[:6_000]},
                                         prompts.mission_fix(listing)]
            retry = self._service.submit("mission", messages, max_tokens=1_600,
                                         temperature=0.3, json_mode=True)
            if retry is not None:
                self._fixed, self._request = True, retry
                return False
        self.issues = list(problems or ())[:ISSUES_MAX]
        return self._fail("bad_reply")

    def _fail(self, error: str) -> bool:
        self.status, self.error, self._request = "failed", error, None
        return True
