"""Summarise a hardware run on the uConsole for docs/hardware-acceptance.md.

Run the game with the debug logs on, play for the time the checklist asks,
quit, then run this on the same device:

    U_JAGD_PERF_DEBUG=1 U_JAGD_AUDIO_DEBUG=1 .venv/bin/python main.py
    .venv/bin/python tools/hw_report.py

It reads ``~/.u-jagd/perf_debug.log`` and ``audio_debug.log`` (or the files
given with ``--perf``/``--audio``), skips the first seconds of the start,
and prints the values the "Allgemein" table asks for with a verdict each, plus
``vcgencmd get_throttled`` when the tool exists. Read-only: it never writes to
the save directory. Exit code 0 when every measured row passes, 1 otherwise,
2 when no log was found.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_DIR = Path.home() / ".u-jagd"
PAIR = re.compile(r"([a-z_]+)=([-+0-9.]+)")


def read_rows(path: Path) -> list[dict]:
    rows = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return rows
    for line in text.splitlines():
        row = {}
        for key, value in PAIR.findall(line):
            try:
                row[key] = float(value)
            except ValueError:
                continue
        if "t" in row:
            rows.append(row)
    return rows


def last_run(rows: list[dict], gap_s: float = 30.0) -> list[dict]:
    """The rows of the newest run: the log is appended across launches, a
    jump in the monotonic time (or back) starts a new run."""
    start = 0
    for index in range(1, len(rows)):
        step = rows[index]["t"] - rows[index - 1]["t"]
        if step < 0.0 or step > gap_s:
            start = index
    return rows[start:]


def summarise_perf(rows: list[dict], skip_s: float, fps_cap: int) -> list[tuple]:
    if not rows:
        return []
    begin = rows[0]["t"] + skip_s
    body = [row for row in rows if row["t"] >= begin] or rows
    fps = [row.get("fps", 0.0) for row in body]
    mean_fps = sum(fps) / len(fps)
    mean_frame_ms = 1000.0 / mean_fps if mean_fps > 0 else float("inf")
    frame_max = max(row.get("frame_max_ms", 0.0) for row in body)
    commander_max = max(row.get("commander_max_ms", 0.0) for row in body)
    dropped = max(row.get("sim_dropped_ms", 0.0) for row in body) - min(
        row.get("sim_dropped_ms", 0.0) for row in body)
    budget = 1000.0 / fps_cap
    minutes = (body[-1]["t"] - body[0]["t"]) / 60.0
    return [
        ("Laufzeit ausgewertet", f"{minutes:.1f} min", None),
        # At the cap the mean frame is the budget itself: allow 1 ms.
        (f"Frame-Zeit Mittel ({fps_cap} FPS)", f"{mean_frame_ms:.1f} ms",
         mean_frame_ms <= budget + 1.0),
        ("frame_max_ms nach dem Start", f"{frame_max:.0f} ms", frame_max < 100.0),
        ("sim_dropped_ms im Lauf", f"{dropped:.0f} ms", dropped <= 0.0),
        ("commander_max_ms", f"{commander_max:.1f} ms", commander_max < 60.0),
    ]


def summarise_audio(rows: list[dict], skip_s: float) -> list[tuple]:
    if not rows:
        return []
    begin = rows[0]["t"] + skip_s
    body = [row for row in rows if row["t"] >= begin] or rows
    idle = body[-1].get("channel_idle", 0.0) - body[0].get("channel_idle", 0.0)
    underruns = body[-1].get("sonar_underruns", 0.0) - body[0].get("sonar_underruns", 0.0)
    return [
        ("channel_idle im Lauf", f"{idle:.0f}", idle <= 0.0),
        ("sonar_underruns im Lauf", f"{underruns:.0f}", None),
    ]


def throttled() -> tuple | None:
    tool = shutil.which("vcgencmd")
    if not tool:
        return None
    try:
        out = subprocess.run([tool, "get_throttled"], capture_output=True, text=True,
                             timeout=5, check=False).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    value = out.partition("=")[2] or out
    return ("vcgencmd get_throttled", value, value.lower() in ("0x0", "0"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--perf", type=Path, default=DEFAULT_DIR / "perf_debug.log")
    parser.add_argument("--audio", type=Path, default=DEFAULT_DIR / "audio_debug.log")
    parser.add_argument("--fps", type=int, choices=(30, 60), default=30,
                        help="frame-rate preference of the run (default 30)")
    parser.add_argument("--skip", type=float, default=20.0,
                        help="seconds at the start that are not judged (default 20)")
    args = parser.parse_args(argv)
    perf = summarise_perf(last_run(read_rows(args.perf)), args.skip, args.fps)
    audio = summarise_audio(last_run(read_rows(args.audio)), args.skip)
    if not perf and not audio:
        print(f"Keine Messwerte in {args.perf} oder {args.audio}. "
              "Spiel mit U_JAGD_PERF_DEBUG=1 U_JAGD_AUDIO_DEBUG=1 starten.")
        return 2
    rows = perf + audio
    heat = throttled()
    if heat:
        rows.append(heat)
    failed = False
    print("| Prüfpunkt | Wert | Ergebnis |")
    print("|---|---|---|")
    for name, value, ok in rows:
        verdict = "" if ok is None else ("ok" if ok else "abweichung")
        failed = failed or ok is False
        print(f"| {name} | {value} | {verdict} |")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
