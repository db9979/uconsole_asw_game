"""List the GitHub releases older than the current one (one tag per line).

The Windows workflow keeps only the newest release: after publishing
``v<APP_VERSION>`` it pipes every release tag into
``python tools/prune_releases.py <APP_VERSION>`` and deletes the releases
printed here. Git tags stay, so older versions remain checkable. Only tags of
the form ``vX.Y.Z`` older than the current version are printed; anything
newer (a later run that finished first) or unparsable is never touched.
"""

from __future__ import annotations

import re
import sys

_TAG = re.compile(r"v(\d+)\.(\d+)\.(\d+)")


def _version(text: str) -> tuple[int, int, int] | None:
    match = _TAG.fullmatch(text.strip())
    return tuple(int(part) for part in match.groups()) if match else None


def older_tags(current: str, tags) -> list[str]:
    keep = _version(f"v{current}")
    if keep is None:
        raise ValueError(f"invalid version {current!r}")
    return [tag.strip() for tag in tags
            if (version := _version(tag)) is not None and version < keep]


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: prune_releases.py VERSION < tags", file=sys.stderr)
        return 2
    for tag in older_tags(argv[0], sys.stdin):
        print(tag)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
