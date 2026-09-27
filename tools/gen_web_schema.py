#!/usr/bin/env python3
"""Render the browser schema's allowlists from the Python source of truth.

``data/commander/js/state/schema.js`` keeps its hand-written validation
logic; the role shapes and row field arrays between the ``GENERATED``
markers are rendered from ``src/commander/v2/schema.py``.  ``--check``
(CI) fails when the file differs from a fresh render; without it the block
is rewritten in place.  Output is deterministic (sorted roles, fixed
formatting, LF line endings).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.commander.v2 import schema  # noqa: E402

SCHEMA_JS = ROOT / "data" / "commander" / "js" / "state" / "schema.js"
BEGIN = "  // BEGIN GENERATED (tools/gen_web_schema.py; do not edit by hand)\n"
END = "  // END GENERATED\n"


def _array(values) -> str:
    return "[" + ", ".join(json.dumps(value) for value in values) + "]"


def render_block() -> str:
    lines = [BEGIN, "  const shapes = {\n"]
    for role in sorted(schema.ROLE_SHAPES):
        lines.append(f"    {role}: {_array(schema.ROLE_SHAPES[role])},\n")
    lines.append("  };\n")
    lines.append(f"  const tacticalFields = {_array(schema.TACTICAL_FIELDS)};\n")
    lines.append(f"  const sonarFields = {_array(schema.SONAR_FIELDS)};\n")
    lines.append(f"  const radioFields = {_array(schema.RADIO_FIELDS)};\n")
    lines.append("  const helicopterTacticalFields = "
                 f"{_array(schema.HELICOPTER_TACTICAL_FIELDS)};\n")
    lines.append(END)
    return "".join(lines)


def render(text: str) -> str:
    start = text.index(BEGIN)
    end = text.index(END) + len(END)
    return text[:start] + render_block() + text[end:]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="fail when schema.js differs from a fresh render")
    args = parser.parse_args(argv)
    current = SCHEMA_JS.read_text(encoding="utf-8")
    try:
        rendered = render(current)
    except ValueError:
        print("schema.js: generated block markers missing", file=sys.stderr)
        return 2
    if args.check:
        if rendered != current:
            print("schema.js: generated block out of date; run tools/gen_web_schema.py",
                  file=sys.stderr)
            return 1
        print("web schema up to date")
        return 0
    if rendered != current:
        SCHEMA_JS.write_text(rendered, encoding="utf-8", newline="\n")
        shown = SCHEMA_JS.relative_to(ROOT) if SCHEMA_JS.is_relative_to(ROOT) else SCHEMA_JS
        print(f"wrote {shown}")
    else:
        print("web schema unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
