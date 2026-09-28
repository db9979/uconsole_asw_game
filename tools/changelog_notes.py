"""Print one release's entry from CHANGELOG.md (release notes for GitHub).

`python tools/changelog_notes.py 1.3.12` prints the text under `## 1.3.12`;
`--check` verifies that the newest entry of CHANGELOG.md and CHANGELOG.de.md
is the current `APP_VERSION` and that each README carries only that release.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_HEADING = re.compile(r"^## (\d+\.\d+\.\d+)\s*$", re.MULTILINE)
# A release paragraph opens with "Release x.y.z" (EN) or "Version x.y.z" (DE).
_README_RELEASE = re.compile(r"^(?:Release|Version) \d+\.\d+\.\d+ ", re.MULTILINE)


def versions(text: str) -> list[str]:
    return _HEADING.findall(text)


def entry(text: str, version: str) -> str:
    matches = list(_HEADING.finditer(text))
    for index, match in enumerate(matches):
        if match.group(1) == version:
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            return text[match.end():end].strip()
    raise KeyError(version)


def check(root: Path = ROOT) -> list[str]:
    sys.path.insert(0, str(root))
    from src.core.version import APP_VERSION
    problems = []
    for name in ("CHANGELOG.md", "CHANGELOG.de.md"):
        found = versions((root / name).read_text(encoding="utf-8"))
        if not found or found[0] != APP_VERSION:
            problems.append(f"{name}: newest entry {found[:1]} is not {APP_VERSION}")
        if len(found) != len(set(found)):
            problems.append(f"{name}: duplicate entries")
    for name in ("README.md", "README.de.md"):
        releases = _README_RELEASE.findall((root / name).read_text(encoding="utf-8"))
        if len(releases) != 1 or APP_VERSION not in releases[0]:
            problems.append(f"{name}: must describe only release {APP_VERSION}, "
                            f"found {len(releases)} release paragraphs")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", nargs="?")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--file", type=Path, default=ROOT / "CHANGELOG.md")
    args = parser.parse_args(argv)
    if args.check:
        problems = check()
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1 if problems else 0
    if not args.version:
        parser.error("a version or --check is required")
    try:
        print(entry(args.file.read_text(encoding="utf-8"), args.version))
    except KeyError:
        print(f"no entry for {args.version} in {args.file}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
