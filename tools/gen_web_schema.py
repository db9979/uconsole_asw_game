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
import os
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
sys.path.insert(0, str(ROOT))

from src.commander.v2 import schema  # noqa: E402

SCHEMA_JS = ROOT / "data" / "commander" / "js" / "state" / "schema.js"
PROFILES_JS = ROOT / "data" / "commander" / "js" / "views" / "silhouette-profiles.js"
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
    lines.append("  const radioTaskFields = {\n")
    lines.append(f"    row: {_array(schema.RADIO_TASK_FIELDS)},\n")
    lines.append(f"    kinds: {_array(schema.RADIO_TASK_KINDS)},\n")
    lines.append(f"    states: {_array(schema.RADIO_TASK_STATES)},\n")
    lines.append("  };\n")
    lines.append("  const crewFields = {\n")
    lines.append(f"    row: {_array(schema.CREW_FIELDS)},\n")
    lines.append(f"    watch: {_array(schema.CREW_WATCH_FIELDS)},\n")
    lines.append("  };\n")
    lines.append("  const mpaFields = {\n")
    lines.append(f"    row: {_array(schema.MPA_FIELDS)},\n")
    lines.append(f"    states: {_array(schema.MPA_STATES)},\n")
    lines.append("  };\n")
    lines.append("  const opzSuggestionFields = "
                 f"{_array(schema.OPZ_SUGGESTION_FIELDS)};\n")
    lines.append("  const helicopterTacticalFields = "
                 f"{_array(schema.HELICOPTER_TACTICAL_FIELDS)};\n")
    lines.append("  const weatherFields = {\n")
    lines.append(f"    atmosphere: {_array(schema.WEATHER_ATMOSPHERE_FIELDS)},\n")
    lines.append(f"    boatAtmosphere: {_array(schema.WEATHER_BOAT_ATMOSPHERE_FIELDS)},\n")
    lines.append(f"    boat: {_array(schema.WEATHER_BOAT_FIELDS)},\n")
    lines.append("  };\n")
    lines.append("  const sightFields = {\n")
    lines.append(f"    sky: {_array(schema.SKY_FIELDS)},\n")
    lines.append(f"    glasses: {_array(schema.LOOKOUT_GLASSES_FIELDS)},\n")
    lines.append(f"    outline: {_array(schema.LOOKOUT_OUTLINE_FIELDS)},\n")
    lines.append(f"    classes: {_array(schema.SIGHT_CLASSES)},\n")
    lines.append(f"    phone: {_array(schema.LOOKOUT_PHONE_FIELDS)},\n")
    lines.append(f"    phoneOutline: {_array(schema.LOOKOUT_PHONE_OUTLINE_FIELDS)},\n")
    lines.append(f"    call: {_array(schema.LOOKOUT_CALL_FIELDS)},\n")
    lines.append(f"    callCategories: {_array(schema.LOOKOUT_CALL_CATEGORIES)},\n")
    lines.append("  };\n")
    lines.append("  const routeFields = {\n")
    lines.append(f"    row: {_array(schema.BRIDGE_ROUTE_FIELDS)},\n")
    lines.append(f"    point: {_array(schema.BRIDGE_ROUTE_POINT_FIELDS)},\n")
    lines.append(f"    patterns: {_array(schema.BRIDGE_ROUTE_PATTERNS)},\n")
    lines.append("  };\n")
    lines.append("  const boatFields = {\n")
    lines.append(f"    plant: {_array(schema.UBOOT_PLANT_FIELDS)},\n")
    lines.append(f"    air: {_array(schema.UBOOT_AIR_FIELDS)},\n")
    lines.append(f"    ballast: {_array(schema.UBOOT_BALLAST_FIELDS)},\n")
    lines.append(f"    ballastFlags: {_array(schema.UBOOT_BALLAST_FLAGS)},\n")
    lines.append(f"    damage: {_array(schema.UBOOT_DAMAGE_FIELDS)},\n")
    lines.append(f"    compartment: {_array(schema.UBOOT_COMPARTMENT_FIELDS)},\n")
    lines.append(f"    dcTeam: {_array(schema.UBOOT_DC_TEAM_FIELDS)},\n")
    lines.append(f"    compartments: {_array(schema.UBOOT_COMPARTMENTS)},\n")
    lines.append(f"    dcTasks: {_array(schema.UBOOT_DC_TASKS)},\n")
    lines.append(f"    esm: {_array(schema.UBOOT_ESM_FIELDS)},\n")
    lines.append(f"    esmEmitter: {_array(schema.UBOOT_ESM_EMITTER_FIELDS)},\n")
    lines.append(f"    esmHistory: {_array(schema.UBOOT_ESM_HISTORY_FIELDS)},\n")
    lines.append(f"    esmFix: {_array(schema.UBOOT_ESM_FIX_FIELDS)},\n")
    lines.append(f"    esmCandidate: {_array(schema.UBOOT_ESM_CANDIDATE_FIELDS)},\n")
    lines.append(f"    threat: {_array(schema.UBOOT_THREAT_FIELDS)},\n")
    lines.append(f"    intercept: {_array(schema.UBOOT_INTERCEPT_FIELDS)},\n")
    lines.append(f"    interceptKinds: {_array(schema.UBOOT_INTERCEPT_KINDS)},\n")
    lines.append(f"    advice: {_array(schema.UBOOT_THREAT_ADVICE)},\n")
    lines.append(f"    evadePlan: {_array(schema.UBOOT_EVADE_PLAN_FIELDS)},\n")
    lines.append(f"    radio: {_array(schema.UBOOT_RADIO_FIELDS)},\n")
    lines.append(f"    radioLog: {_array(schema.UBOOT_RADIO_LOG_FIELDS)},\n")
    lines.append(f"    radioLogKinds: {_array(schema.UBOOT_RADIO_LOG_KINDS)},\n")
    lines.append(f"    radioReport: {_array(schema.UBOOT_RADIO_REPORT_FIELDS)},\n")
    lines.append("  };\n")
    lines.append(END)
    return "".join(lines)


def _rounded(value):
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, (list, tuple)):
        return [_rounded(item) for item in value]
    if isinstance(value, dict):
        return {key: _rounded(item) for key, item in sorted(value.items())}
    return value


def render_profiles() -> str:
    """The silhouettes of ``src/ui/silhouettes.py`` as a browser module, so
    the browser eyepieces draw exactly the uConsole's shapes."""
    from src.ui import silhouettes
    body = json.dumps(_rounded(silhouettes.PROFILES), separators=(",", ":"), sort_keys=True)
    return ("// GENERATED by tools/gen_web_schema.py from src/ui/silhouettes.py;"
            " do not edit by hand.\n"
            f"export const PROFILES = {body};\n"
            f"export const DETAIL_MIN_PX = {silhouettes.DETAIL_MIN_PX};\n"
            f"export const FOAM = {_array(silhouettes.FOAM)};\n"
            "export const NAV_LIGHT = {%s};\n" % ", ".join(
                f"{name}: {_array(color)}" for name, color in sorted(silhouettes.NAV_LIGHT.items())))


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
    profiles = render_profiles()
    profiles_current = PROFILES_JS.read_text(encoding="utf-8") if PROFILES_JS.exists() else ""
    if args.check:
        if rendered != current:
            print("schema.js: generated block out of date; run tools/gen_web_schema.py",
                  file=sys.stderr)
            return 1
        if profiles != profiles_current:
            print("silhouette-profiles.js out of date; run tools/gen_web_schema.py",
                  file=sys.stderr)
            return 1
        print("web schema up to date")
        return 0
    if profiles != profiles_current:
        PROFILES_JS.write_text(profiles, encoding="utf-8", newline="\n")
        print(f"wrote {PROFILES_JS.relative_to(ROOT)}")
    if rendered != current:
        SCHEMA_JS.write_text(rendered, encoding="utf-8", newline="\n")
        shown = SCHEMA_JS.relative_to(ROOT) if SCHEMA_JS.is_relative_to(ROOT) else SCHEMA_JS
        print(f"wrote {shown}")
    else:
        print("web schema unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
