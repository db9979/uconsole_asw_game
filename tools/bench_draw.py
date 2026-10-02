"""Headless frame-cost benchmark of every station on both sides.

Starts one mission per side the uConsole can play, warms it up, then times
``--frames`` frames of ``game.update(dt)`` and ``game.draw()`` at each frigate
station and at each boat station page (the sonar room included).  Prints
mean and max milliseconds per frame for update and draw separately, and with
``--profile`` the hottest functions of the draws on the side given.

    python tools/bench_draw.py                      # both sides, every view
    python tools/bench_draw.py --side uboot --profile uboot --frames 60

Not a hardware test: absolute numbers from a desktop CPU are several times
lower than on the uConsole; compare views and sides with each other.
"""

from __future__ import annotations

import argparse
import cProfile
import io
import os
import pstats
import sys
import time
from tempfile import TemporaryDirectory

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core import config, uboot_local  # noqa: E402
from src.core.game import Game  # noqa: E402
from src.core.station import Station  # noqa: E402
from src.ui import uboot_view  # noqa: E402

SIDES = ("frigate", "uboot")


def side_scenario(side: str, scenario: str | None) -> str:
    """The scenario given, else the first one the menus list for ``side``."""
    return scenario or config.scenarios_for_side(side)[0]


def new_game(scenario: str, side: str, seed: int, warmup_s: float, dt: float,
             audio: bool = False) -> Game:
    game = Game(seed=seed, start_menu=False, show_splash=False, audio_enabled=audio,
                language="en")
    assert game.start_new_game(scenario, "fixed", seed=seed)
    game.local_side = side
    for _ in range(int(warmup_s / dt)):
        game.update(dt)
    game.msg_until = 0.0
    return game


def views(game, side: str):
    """``(label, select)`` for every station view of the side."""
    out = []
    if side == "frigate":
        for station in list(Station):
            def select(station=station):
                game.station = station
                game.station_page = 2 if station is Station.HELICOPTER else 0
            out.append((station.name.lower(), select))
        return out
    for role in uboot_local.OPFOR_ROLES:
        if role == "uboot_sonar":
            def select(role=role):
                uboot_local.set_local_station(game, role)
            out.append((role, select))
            continue
        for index, page in enumerate(uboot_view.station_pages(role)):
            def select(role=role, index=index):
                uboot_local.set_local_station(game, role)
                game.opfor.command_page = index
            out.append((f"{role}/{page.lower()}", select))
    return out


def time_view(game, select, frames: int, dt: float, profiler=None):
    select()
    for _ in range(3):  # first frames fill caches
        game.update(dt)
        game.draw()
    update_ms, draw_ms = [], []
    for _ in range(frames):
        started = time.perf_counter()
        game.update(dt)
        middle = time.perf_counter()
        if profiler is not None:
            profiler.enable()
        game.draw()
        if profiler is not None:
            profiler.disable()
        ended = time.perf_counter()
        update_ms.append(1000.0 * (middle - started))
        draw_ms.append(1000.0 * (ended - middle))
    return update_ms, draw_ms


def run(args) -> dict:
    results = {}
    profiles = {}
    for side in args.side or SIDES:
        game = new_game(side_scenario(side, args.scenario), side, args.seed,
                        args.warmup, args.dt, args.audio)
        if side == "uboot" and args.silent and game.opfor is not None:
            # Silent running rigs the boat for red light (a full-screen tint).
            game.opfor.orders.silent = True
        profiler = cProfile.Profile() if args.profile == side else None
        rows = []
        for label, select in views(game, side):
            if args.view and not any(part in label for part in args.view):
                continue
            update_ms, draw_ms = time_view(game, select, args.frames, args.dt, profiler)
            rows.append((label, sum(update_ms) / len(update_ms), max(update_ms),
                         sum(draw_ms) / len(draw_ms), max(draw_ms)))
        results[side] = rows
        if profiler is not None:
            profiles[side] = profiler
    return results, profiles


def report(results) -> str:
    lines = [f"{'side':8} {'view':28} {'upd mean':>9} {'upd max':>8} "
             f"{'draw mean':>10} {'draw max':>9}"]
    for side, rows in results.items():
        for label, umean, umax, dmean, dmax in rows:
            lines.append(f"{side:8} {label:28} {umean:9.2f} {umax:8.2f} "
                         f"{dmean:10.2f} {dmax:9.2f}")
        if rows:
            lines.append(f"{side:8} {'(mean of views)':28} "
                         f"{sum(r[1] for r in rows) / len(rows):9.2f} {'':8} "
                         f"{sum(r[3] for r in rows) / len(rows):10.2f}")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scenario", default=None,
                        help="default: the first scenario of each side")
    parser.add_argument("--silent", action="store_true",
                        help="the boat runs silent (red light over every boat view)")
    parser.add_argument("--audio", action="store_true",
                        help="run the audio engine too (SDL dummy driver)")
    parser.add_argument("--side", action="append", choices=SIDES)
    parser.add_argument("--view", action="append",
                        help="only views whose label contains this (repeatable)")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--frames", type=int, default=90)
    parser.add_argument("--dt", type=float, default=1.0 / 30.0)
    parser.add_argument("--warmup", type=float, default=120.0,
                        help="simulation seconds before timing")
    parser.add_argument("--profile", choices=SIDES, default=None)
    parser.add_argument("--top", type=int, default=40)
    args = parser.parse_args(argv)
    previous = config.SAVE_DIR, config.SAVE_PATH
    with TemporaryDirectory(prefix="u-jagd-bench-") as saves:
        config.SAVE_DIR = saves
        config.SAVE_PATH = os.path.join(saves, "save.json")
        try:
            results, profiles = run(args)
        finally:
            config.SAVE_DIR, config.SAVE_PATH = previous
    print(report(results))
    for side, profiler in profiles.items():
        stream = io.StringIO()
        stats = pstats.Stats(profiler, stream=stream)
        stats.sort_stats("cumulative").print_stats(args.top)
        stats.sort_stats("tottime").print_stats(args.top)
        print(f"\n--- draw profile, {side} ---\n{stream.getvalue()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
