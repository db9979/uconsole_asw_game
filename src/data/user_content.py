"""Safe persistence and portable bundles for editor-authored content."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from src.data.validation import (ContentValidationError, ValidationIssue, issue,
                                 raise_for_issues, safe_content_path,
                                 validate_user_key)


DEFAULT_ROOT = Path.home() / ".u-jagd"
BUNDLE_FORMAT = "u-jagd.editor-bundle"
BUNDLE_VERSION = 1


@dataclass(frozen=True)
class ContentRecord:
    key: str
    kind: str
    data: dict[str, Any]
    builtin: bool = False
    source: Path | None = None

    @property
    def read_only(self) -> bool:
        return self.builtin


def atomic_write_json(path: str | Path, value: Any) -> Path:
    """Write JSON completely or leave the prior file untouched."""
    path = Path(path)
    temporary = _stage_json(path, value)
    try:
        os.replace(temporary, path)
    except BaseException:
        _remove_if_present(temporary)
        raise
    return path


def _stage_json(path: Path, value: Any) -> Path:
    """Serialize JSON beside its destination without changing the destination."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.parent.is_symlink() or (path.exists() and path.is_symlink()):
        raise ContentValidationError([issue("path", "symlink", "refusing symlinked path")])
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp",
                                         dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True,
                      allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        _remove_if_present(temporary)
        raise
    return Path(temporary)


def _stage_bytes(path: Path, value: bytes) -> Path:
    """Stage an exact backup beside an existing destination."""
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".bak",
                                         dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        _remove_if_present(temporary)
        raise
    return Path(temporary)


def _remove_if_present(path: str | Path) -> None:
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


class UserContentStore:
    """Mission/unit JSON store with injectable roots and validators."""

    def __init__(self, root: str | Path = DEFAULT_ROOT,
                 mission_validator: Callable[[Mapping[str, Any]], Iterable[ValidationIssue]] | None = None,
                 unit_validator: Callable[[Mapping[str, Any]], Iterable[ValidationIssue]] | None = None):
        self.root = Path(root).expanduser()
        self.roots = {"mission": self.root / "missions", "unit": self.root / "units"}
        self.validators = {"mission": mission_validator, "unit": unit_validator}

    def _kind(self, kind: str) -> str:
        normalized = kind.removesuffix("s")
        if normalized not in self.roots:
            raise ValueError("kind must be 'mission' or 'unit'")
        return normalized

    def path_for(self, kind: str, key: str) -> Path:
        if self.root.exists() and self.root.is_symlink():
            raise ContentValidationError([
                issue("path", "symlink", "storage root must not be a symlink")])
        return safe_content_path(self.roots[self._kind(kind)], key)

    def validate(self, kind: str, data: Mapping[str, Any]) -> tuple[ValidationIssue, ...]:
        kind = self._kind(kind)
        problems = list(validate_user_key(data.get("key"))) if isinstance(data, Mapping) else [
            issue("", "object", "content must be an object")]
        validator = self.validators[kind]
        if validator is None:
            if kind == "mission":
                from src.core.mission_definition import validate_mission
                validator = validate_mission
            else:
                from src.ui.unit_editor import validate_unit
                validator = validate_unit
        if validator is not None and isinstance(data, Mapping):
            problems.extend(validator(data))
        return tuple(problems)

    def save(self, kind: str, data: Mapping[str, Any]) -> Path:
        kind = self._kind(kind)
        raise_for_issues(self.validate(kind, data))
        return atomic_write_json(self.path_for(kind, str(data["key"])), dict(data))

    def load(self, kind: str, key: str) -> dict[str, Any]:
        path = self.path_for(kind, key)
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
        raise_for_issues(self.validate(kind, value))
        return value

    def list(self, kind: str) -> list[ContentRecord]:
        kind = self._kind(kind)
        root = self.roots[kind]
        if not root.exists() or root.is_symlink():
            return []
        records = []
        for path in sorted(root.glob("user.*.json")):
            if path.is_symlink() or not path.is_file():
                continue
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                if not self.validate(kind, value) and path == self.path_for(kind, value["key"]):
                    records.append(ContentRecord(value["key"], kind, value, source=path))
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                continue
        return records

    def delete(self, kind: str, key: str) -> bool:
        path = self.path_for(kind, key)
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return False

    def export_bundle(self, path: str | Path, *, missions: Iterable[Mapping[str, Any]] = (),
                      units: Iterable[Mapping[str, Any]] = ()) -> Path:
        payload = {"format": BUNDLE_FORMAT, "version": BUNDLE_VERSION,
                   "missions": [dict(item) for item in missions],
                   "units": [dict(item) for item in units]}
        problems = self._validate_bundle(payload)
        raise_for_issues(problems)
        return atomic_write_json(path, payload)

    def import_bundle(self, source: str | Path | Mapping[str, Any], *,
                      overwrite: bool = False) -> list[ContentRecord]:
        if isinstance(source, Mapping):
            payload = dict(source)
        else:
            with Path(source).open("r", encoding="utf-8") as stream:
                payload = json.load(stream)
        raise_for_issues(self._validate_bundle(payload))
        pending = []
        for plural, kind in (("missions", "mission"), ("units", "unit")):
            for data in payload[plural]:
                path = self.path_for(kind, data["key"])
                if path.exists() and not overwrite:
                    raise ContentValidationError([
                        issue(f"{plural}.{data['key']}", "exists", "content already exists")])
                pending.append((kind, data, path))
        # Validation and collision checks happen before the first write.
        staged: list[tuple[str, Mapping[str, Any], Path, Path, Path | None]] = []
        try:
            for kind, data, path in pending:
                temporary = _stage_json(path, data)
                try:
                    backup = _stage_bytes(path, path.read_bytes()) if path.exists() else None
                except BaseException:
                    _remove_if_present(temporary)
                    raise
                staged.append((kind, data, path, temporary, backup))
        except BaseException:
            for _, _, _, temporary, backup in staged:
                _remove_if_present(temporary)
                if backup is not None:
                    _remove_if_present(backup)
            raise

        committed = []
        try:
            # Staging can take time, so recheck confinement and symlinks before
            # making the first externally visible change.
            for kind, data, path, _, _ in staged:
                if self.path_for(kind, data["key"]) != path:
                    raise ContentValidationError([
                        issue("path", "traversal", "content destination changed")])
            for item in staged:
                os.replace(item[3], item[2])
                committed.append(item)
        except BaseException as commit_error:
            rollback_errors = []
            retained_backups = set()
            for _, _, path, _, backup in reversed(committed):
                try:
                    if backup is None:
                        _remove_if_present(path)
                    else:
                        os.replace(backup, path)
                except BaseException as rollback_error:
                    rollback_errors.append(rollback_error)
                    if backup is not None:
                        retained_backups.add(backup)
            for _, _, _, temporary, backup in staged:
                _remove_if_present(temporary)
                if backup is not None and backup not in retained_backups:
                    _remove_if_present(backup)
            if rollback_errors:
                raise BaseExceptionGroup(
                    "bundle commit failed and rollback was incomplete",
                    [commit_error, *rollback_errors])
            raise

        for _, _, _, _, backup in staged:
            if backup is not None:
                _remove_if_present(backup)
        return [ContentRecord(data["key"], kind, dict(data), source=path)
                for kind, data, path, _, _ in staged]

    def _validate_bundle(self, payload: Any) -> list[ValidationIssue]:
        if not isinstance(payload, Mapping):
            return [issue("bundle", "object", "bundle must be an object")]
        problems = []
        if payload.get("format") != BUNDLE_FORMAT:
            problems.append(issue("format", "format", f"must be {BUNDLE_FORMAT!r}"))
        if payload.get("version") != BUNDLE_VERSION:
            problems.append(issue("version", "version", f"must be {BUNDLE_VERSION}"))
        all_keys = set()
        for plural, kind in (("missions", "mission"), ("units", "unit")):
            values = payload.get(plural)
            if not isinstance(values, list):
                problems.append(issue(plural, "array", "must be an array"))
                continue
            for index, value in enumerate(values):
                base = f"{plural}[{index}]"
                if not isinstance(value, Mapping):
                    problems.append(issue(base, "object", "must be an object"))
                    continue
                for problem in self.validate(kind, value):
                    problems.append(issue(f"{base}.{problem.path}".rstrip("."),
                                          problem.code, problem.message))
                key = value.get("key")
                marker = (kind, key)
                if marker in all_keys:
                    problems.append(issue(f"{base}.key", "duplicate", "duplicate bundle key"))
                all_keys.add(marker)
        return problems


def default_store(root: str | Path = DEFAULT_ROOT) -> UserContentStore:
    """Construct a fully validating store without import-time circular imports."""
    from src.core.mission_definition import validate_mission
    from src.ui.unit_editor import validate_unit
    return UserContentStore(root, validate_mission, validate_unit)
