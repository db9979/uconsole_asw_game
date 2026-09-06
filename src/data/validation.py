"""Shared validation primitives for user-authored editor content."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


USER_KEY_RE = re.compile(r"^user\.[a-z0-9][a-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}" if self.path else self.message


class ContentValidationError(ValueError):
    """Raised when content cannot safely be persisted or imported."""

    def __init__(self, issues: Iterable[ValidationIssue]):
        self.issues = tuple(issues)
        super().__init__("; ".join(map(str, self.issues)) or "invalid content")


def issue(path: str, code: str, message: str) -> ValidationIssue:
    return ValidationIssue(path, code, message)


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def finite_number(value: Any, path: str, *, minimum: float | None = None,
                  maximum: float | None = None) -> list[ValidationIssue]:
    if not is_number(value) or not math.isfinite(float(value)):
        return [issue(path, "finite", "must be a finite number")]
    result = []
    if minimum is not None and value < minimum:
        result.append(issue(path, "range", f"must be at least {minimum:g}"))
    if maximum is not None and value > maximum:
        result.append(issue(path, "range", f"must be at most {maximum:g}"))
    return result


def integer(value: Any, path: str, *, minimum: int | None = None,
            maximum: int | None = None) -> list[ValidationIssue]:
    if not isinstance(value, int) or isinstance(value, bool):
        return [issue(path, "integer", "must be an integer")]
    return finite_number(value, path, minimum=minimum, maximum=maximum)


def text(value: Any, path: str, *, required: bool = True,
         maximum: int = 256) -> list[ValidationIssue]:
    if not isinstance(value, str):
        return [issue(path, "string", "must be text")]
    if required and not value.strip():
        return [issue(path, "required", "must not be empty")]
    if len(value) > maximum:
        return [issue(path, "length", f"must contain at most {maximum} characters")]
    if any(ord(char) < 32 and char not in "\n\t" for char in value):
        return [issue(path, "characters", "contains control characters")]
    return []


def enum(value: Any, path: str, choices: Iterable[str]) -> list[ValidationIssue]:
    choices = tuple(choices)
    if value not in choices:
        return [issue(path, "enum", f"must be one of: {', '.join(choices)}")]
    return []


def mapping(value: Any, path: str) -> list[ValidationIssue]:
    return [] if isinstance(value, Mapping) else [issue(path, "object", "must be an object")]


def sequence(value: Any, path: str) -> list[ValidationIssue]:
    return [] if isinstance(value, list) else [issue(path, "array", "must be an array")]


def pair(value: Any, path: str, *, minimum: float | None = None,
         maximum: float | None = None, ordered: bool = True,
         integer_values: bool = False) -> list[ValidationIssue]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return [issue(path, "pair", "must contain exactly two values")]
    check = integer if integer_values else finite_number
    result = check(value[0], f"{path}[0]", minimum=minimum, maximum=maximum)
    result += check(value[1], f"{path}[1]", minimum=minimum, maximum=maximum)
    if not result and ordered and value[0] > value[1]:
        result.append(issue(path, "order", "minimum must not exceed maximum"))
    return result


def unique(values: Iterable[Any], path: str) -> list[ValidationIssue]:
    result, seen = [], set()
    for index, value in enumerate(values):
        try:
            duplicate = value in seen
            seen.add(value)
        except TypeError:
            duplicate = False
        if duplicate:
            result.append(issue(f"{path}[{index}]", "duplicate", f"duplicate value {value!r}"))
    return result


def validate_user_key(key: Any, path: str = "key") -> list[ValidationIssue]:
    if not isinstance(key, str) or not USER_KEY_RE.fullmatch(key):
        return [issue(path, "user_key",
                      "must match user.<lowercase letters, digits, _ or ->")]
    return []


def safe_content_path(root: str | Path, key: str, *, suffix: str = ".json") -> Path:
    """Return a confined path for a validated user key.

    Existing symlinks are rejected, including a symlinked storage root. This is
    deliberately stricter than a simple ``resolve`` prefix check.
    """
    problems = validate_user_key(key)
    if problems:
        raise ContentValidationError(problems)
    root = Path(root).expanduser()
    if root.exists() and root.is_symlink():
        raise ContentValidationError([issue("path", "symlink", "storage root must not be a symlink")])
    resolved_root = root.resolve(strict=False)
    candidate = root / f"{key}{suffix}"
    if candidate.exists() and candidate.is_symlink():
        raise ContentValidationError([issue("path", "symlink", "content file must not be a symlink")])
    try:
        candidate.resolve(strict=False).relative_to(resolved_root)
    except ValueError as exc:
        raise ContentValidationError([issue("path", "traversal", "path escapes storage root")]) from exc
    return candidate


def raise_for_issues(issues: Iterable[ValidationIssue]) -> None:
    problems = tuple(issues)
    if problems:
        raise ContentValidationError(problems)
