"""Own-mission library over Remote Crew (main-thread half).

``MissionLibrary`` builds the detached library publication for the solo host
(every mission of the Mission Editor's store with its validity, side,
fairness hints and the user unit profiles it references), applies the
queued library requests (save, import, delete) to the user store with the
same strict validation as the uConsole editor, and builds the static editor
catalog (profile keys and names, packaged sectors with their coasts).

It runs on the main thread only; the store's own atomic writes and bundle
staging apply. The library is re-read when the store's file signature
changes (stat only, at most every ``LIBRARY_CHECK_S``), never per frame.
Missions stay transient user content: nothing here enters a save.
"""

from __future__ import annotations

import os
from collections import deque

from src.core import config
from src.core.i18n import Translator
from src.core.mission_definition import (EVENT_TYPES, OBJECTIVE_TYPES, PLAYER_SIDES,
                                         SIDES, mission_hints, mission_side,
                                         validate_mission)
from src.data.user_content import BUNDLE_MAX_ITEMS, default_store
from src.data.user_profiles import referenced_user_keys
from src.data.validation import (ContentValidationError, issue, localized_issue,
                                 validate_user_key)

LIBRARY_CHECK_S = 2.0
LIBRARY_MAX_MISSIONS = 64
RESULTS_MAX = 8
ISSUES_MAX = 20
WEATHERS = ("clear", "rain", "storm", "fog")


_TRANSLATORS = {}


def _tr(language):
    if language not in _TRANSLATORS:
        _TRANSLATORS[language] = Translator(language).translate
    return _TRANSLATORS[language]


def _texts(problem) -> dict:
    return {"path": problem.path[:120], "code": problem.code[:32],
            "en": localized_issue(problem, _tr("en"))[:300],
            "de": localized_issue(problem, _tr("de"))[:300]}


def _hint(key, params) -> dict:
    return {"key": key, "en": _tr("en")(key, **params)[:300],
            "de": _tr("de")(key, **params)[:300]}


class MissionLibrary:
    """Library publication and request application for one bridge."""

    def __init__(self, root=None):
        self._root = root
        self._signature = None
        self._checked_at = None
        self._view = None
        self.revision = 0
        self._results = deque(maxlen=RESULTS_MAX)

    def store(self):
        return default_store(self._root if self._root is not None else config.SAVE_DIR)

    def _profile_keys(self, store) -> set:
        from src.data.catalog import CATALOG
        from src.ui.unit_editor import catalog_builtins
        return set(catalog_builtins(CATALOG)) | {record.key for record in store.list("unit")}

    def _file_signature(self, store) -> tuple:
        rows = []
        for kind in ("mission", "unit"):
            root = store.roots[kind]
            try:
                entries = sorted(os.scandir(root), key=lambda entry: entry.name) \
                    if root.is_dir() and not root.is_symlink() else []
            except OSError:
                entries = []
            for entry in entries[:4 * LIBRARY_MAX_MISSIONS]:
                try:
                    info = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                rows.append((kind, entry.name, info.st_size, info.st_mtime_ns))
        return tuple(rows)

    def view(self, now: float, force: bool = False) -> dict:
        """The library publication (rebuilt only when the store changed)."""
        if (not force and self._view is not None and self._checked_at is not None
                and now - self._checked_at < LIBRARY_CHECK_S):
            return self._view
        self._checked_at = now
        store = self.store()
        signature = self._file_signature(store)
        if not force and self._view is not None and signature == self._signature:
            return self._view
        self._signature = signature
        self.revision += 1
        self._view = self._build(store)
        return self._view

    def _build(self, store) -> dict:
        records = store.list("mission")
        units = {record.key: record.data for record in store.list("unit")}
        profiles = self._profile_keys(store)
        truncated = len(records) > LIBRARY_MAX_MISSIONS
        missions, wanted = [], set()
        for record in records[:LIBRARY_MAX_MISSIONS]:
            data = record.data
            problems = validate_mission(data, profiles)
            referenced = referenced_user_keys(data)
            wanted.update(key for key in referenced if key in units)
            missions.append({
                "key": record.key,
                "name": str(data.get("name", ""))[:80],
                "side": mission_side(data),
                "objective": str(data.get("objective", {}).get("type", "")),
                "valid": not problems,
                "issues": [_texts(problem) for problem in problems[:ISSUES_MAX]],
                "hints": [_hint(key, params) for key, params in mission_hints(data)],
                "units": referenced,
                "data": data,
            })
        user_profiles = [{"key": key, "kind": str(data.get("profile_kind", "")),
                          "name": str(data.get("name", key))[:80],
                          "warship": data.get("category") == "KAMPFSCHIFF"}
                         for key, data in sorted(units.items())][:4 * LIBRARY_MAX_MISSIONS]
        return {"protocol": 2, "revision": self.revision, "missions": missions,
                "units": [units[key] for key in sorted(wanted)],
                "user_profiles": user_profiles,
                "results": list(self._results), "truncated": truncated}

    def apply(self, op) -> dict:
        """Apply one queued request to the store; the result joins the view."""
        body = op.body
        store = self.store()
        try:
            if body["op"] == "delete":
                key = body["key"]
                if not store.delete("mission", key):
                    raise ContentValidationError([issue("key", "missing", "no such mission")])
            elif body["op"] == "save":
                mission = body["mission"]
                problems = (list(validate_user_key(mission.get("key")))
                            + validate_mission(mission, self._profile_keys(store)))
                if problems:
                    raise ContentValidationError(problems)
                path = store.path_for("mission", mission["key"])
                if path.exists() and not body["overwrite"]:
                    raise ContentValidationError([
                        issue("key", "exists", "content already exists")])
                store.save("mission", mission)
            else:
                bundle = body["bundle"]
                missions = bundle.get("missions") if isinstance(bundle, dict) else None
                if isinstance(missions, list) and len(missions) > BUNDLE_MAX_ITEMS:
                    raise ContentValidationError([issue("missions", "size", "too many items")])
                store.import_bundle(bundle, overwrite=body["overwrite"])
        except ContentValidationError as error:
            result = {"id": body["id"], "status": "rejected",
                      "reason": ("exists" if any(problem.code == "exists"
                                                 for problem in error.issues) else "invalid"),
                      "issues": [_texts(problem) for problem in error.issues[:ISSUES_MAX]]}
        except (OSError, ValueError, TypeError, KeyError, RecursionError):
            result = {"id": body["id"], "status": "rejected", "reason": "failed", "issues": []}
        else:
            result = {"id": body["id"], "status": "applied", "reason": "ok", "issues": []}
        self._results.append(result)
        self._view = None                     # republish with the result
        return result

    # -- the mission generator (optional language model) ---------------------

    @staticmethod
    def generated_key(op_id: str) -> str:
        """The key a generated mission is stored under (the page knows it too)."""
        return "user.llm_" + "".join(char for char in op_id.lower() if char in "0123456789abcdef")[:12]

    def generate(self, op, game) -> None:
        """Ask the model for a mission; the result arrives through ``generated``."""
        body = op.body
        gen = getattr(game, "mission_gen", None)
        reason = "llm_off"
        if gen is not None:
            reason = gen.start(game.llm, game.llm_language(), body["side"], body["request"],
                               key=self.generated_key(body["id"]), owner=("web", body["id"]),
                               profile_keys=self._profile_keys(self.store()))
        if reason is not None:
            self._results.append({"id": body["id"], "status": "rejected",
                                  "reason": reason[:16], "issues": []})
            self._view = None

    def generated(self, game) -> bool:
        """Store a finished generation of the page; True when a result joined."""
        gen = getattr(game, "mission_gen", None)
        if (gen is None or gen.status not in ("done", "failed")
                or not isinstance(gen.owner, tuple) or gen.owner[0] != "web"):
            return False
        op_id = gen.owner[1]
        if gen.status == "done":
            store = self.store()
            try:
                if store.path_for("mission", gen.mission["key"]).exists():
                    raise ContentValidationError([issue("key", "exists", "content already exists")])
                store.save("mission", gen.mission)
            except ContentValidationError as error:
                result = {"id": op_id, "status": "rejected", "reason": "invalid",
                          "issues": [_texts(problem) for problem in error.issues[:ISSUES_MAX]]}
            except (OSError, ValueError, TypeError):
                result = {"id": op_id, "status": "rejected", "reason": "failed", "issues": []}
            else:
                result = {"id": op_id, "status": "applied", "reason": "generated", "issues": []}
        else:
            result = {"id": op_id, "status": "rejected",
                      "reason": ("llm_" + (gen.error or "failed"))[:16],
                      "issues": [_texts(problem) for problem in gen.issues[:ISSUES_MAX]]}
        gen.reset()
        self._results.append(result)
        self._view = None
        return True

    def mission(self, key):
        """A stored mission's definition by key (None when absent or invalid)."""
        try:
            return self.store().load("mission", key)
        except (OSError, ValueError, ContentValidationError):
            return None


def editor_catalog() -> tuple[dict, dict]:
    """The static editor catalog and the coast outlines of every sector."""
    from src.data.catalog import CATALOG
    from src.ui.mission_editor import sector_summaries
    from src.ui.unit_editor import catalog_builtins
    profiles = []
    for key, (kind, profile) in sorted(catalog_builtins(CATALOG).items()):
        category = getattr(profile, "category", None)
        if kind == "torpedo" and getattr(profile, "used_by", "") != "enemy":
            continue
        profiles.append({"key": key, "kind": kind, "name": str(getattr(profile, "name", key))[:80],
                         "warship": category == "KAMPFSCHIFF"})
    sectors, coasts = [], {}
    for index, countries, outlines in sector_summaries():
        sectors.append({"index": index, "countries": list(countries[:4])})
        coasts[index] = {"index": index, "outlines": [
            [[round(x, 1), round(y, 1)] for x, y in outline] for outline in outlines]}
    catalog = {"protocol": 2, "world_size_nm": float(config.WORLD_SIZE_NM),
               "profiles": profiles, "sectors": sectors,
               "sides": list(SIDES), "player_sides": list(PLAYER_SIDES),
               "objectives": list(OBJECTIVE_TYPES), "events": list(EVENT_TYPES),
               "weathers": list(WEATHERS)}
    return catalog, coasts
