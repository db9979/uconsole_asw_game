#!/usr/bin/env python3
"""Headless fairness measurement: AI hunter frigate against a submarine.

Run from anywhere (the repository is found from this file)::

    python tools/fairness.py --short --scenarios s1 s5 s7 --seeds 1-20 --jobs 3 --out run.json
    python tools/fairness.py --short --crewed --scenarios s5 s7 --out crewed.json

The frigate is crewed by ``src/core/hunter.py`` (always active), the
submarine by its own AI (``src/enemies/sub.py``, ``src/core/boat_ai.py``) or,
with ``--crewed``, as the crewed boat run entirely by the crew assist
(``src/core/boat_autocrew.py``), as a newcomer leaning on the assist would
play it.  Each run prints one JSON row: ``result`` (``SIEG`` = the frigate
side wins), the reason key, mission time and torpedoes fired by each side
(``boat_torpedoes``: the crewed boat's own shots).

Every game runs in its own fresh process (``spawn``, one task per worker):
entity ids and other module state carry across games in one process and
change the results, so a run's outcome must not depend on which games ran
before it in the same worker.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

KEYS = {"s1": "s1_patrouille", "s2": "s2_doppeljagd", "s3": "s3_abfang",
        "s5": "s5_durchbruch", "s6": "s6_aufklaerung", "s7": "s7_geleitzug",
        "s8": "s8_meerenge", "s9": "s9_kampfschwimmer", "s10": "s10_versorger",
        "s11": "s11_geleitschutz", "s12": "s12_datum", "s13": "s13_fuehlung",
        "s14": "s14_hafenschutz", "s15": "s15_versorgung", "s16": "s16_seenot",
        "s17": "s17_duell", "s18": "s18_heimkehr", "s19": "s19_abholung",
        "s20": "s20_lauschposten", "s21": "s21_suchgruppe", "s22": "s22_jagdgruppe"}
DEFAULT_SEEDS = "1-20"


def parse_seeds(text: str) -> list:
    """``"1-20"``, ``"7"`` or ``"1,3,5-8"`` as a sorted list of distinct seeds."""
    seeds = set()
    for part in str(text).split(","):
        part = part.strip()
        if not part:
            raise ValueError("empty seed")
        low, dash, high = part.partition("-")
        first = int(low)
        last = int(high) if dash else first
        if first < 0 or last < first:
            raise ValueError(f"bad seed range {part!r}")
        seeds.update(range(first, last + 1))
    return sorted(seeds)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--scenarios", nargs="+", default=list(KEYS), choices=list(KEYS),
                        metavar="sN", help="scenario labels s1 ... s22 (default: all)")
    parser.add_argument("--seeds", default=DEFAULT_SEEDS, type=parse_seeds,
                        help="seeds, e.g. 1-20 or 1,3,5-8 (default 1-20)")
    parser.add_argument("--dt", type=float, default=0.1, help="simulation step (s)")
    parser.add_argument("--jobs", type=int, default=2, help="parallel processes")
    parser.add_argument("--idle", action="store_true", help="the frigate does nothing")
    parser.add_argument("--crewed", action="store_true",
                        help="the submarine is the crewed boat run by the crew assist")
    parser.add_argument("--short", action="store_true", help="the short mission variant")
    parser.add_argument("--max-sim-s", type=float, default=None,
                        help="stop each game after this much mission time (smoke runs)")
    parser.add_argument("--out", help="write rows and summary to this JSON file")
    return parser


def run(job) -> dict:
    """One game, start to end (call in a fresh process)."""
    scenario, seed, dt, idle, crewed, short, max_sim_s = job
    from src.core import hunter
    from src.core.game import Game
    if not idle:
        hunter.active = lambda game: not game.game_over and not game.damage.ship_sunk
    game = Game(seed=seed, start_menu=False, audio_enabled=False)
    if crewed:
        from src.core import boat_autocrew
        boat_autocrew.held = lambda game, role: False
        game.local_side = "uboot"
    if short:
        game.start_length = "short"
    game.start_new_game(KEYS[scenario], "fixed", seed=seed)
    if crewed:
        game.autocrew.set_assist(True, game.sim_t)
        game._update(0.05)          # binds the crewed boat, as on the uConsole
    boat = getattr(game, "_opfor", None) if crewed else None
    boat_sub = boat.sub if boat is not None else None
    boat_load = boat_sub.torpedoes_left if boat_sub is not None else None
    started = time.time()
    enemy = 0
    seen = set()
    limit = getattr(game.mission, "time_limit_s", None) or 20000.0
    limit += 60.0
    if max_sim_s is not None:
        limit = min(limit, float(max_sim_s))
    while not game.game_over and game.mission_time < limit:
        game._update_sim(dt)
        for torpedo in game.enemy_torpedoes:
            if id(torpedo) not in seen:
                seen.add(id(torpedo))
                enemy += 1
    reason = game.result_reason
    key = reason.get("__u_jagd_i18n__") if isinstance(reason, dict) else None
    key = key or getattr(reason, "key", None) or str(reason)
    return dict(scenario=scenario, seed=seed, short=bool(short and game.short_mission),
                crewed=bool(crewed and game._opfor is not None),
                result=game.mission_result, reason=key, t=round(game.mission_time),
                enemy_torpedoes=enemy, own_torpedoes=getattr(game, "torpedo_seq", None),
                subs_sunk=sum(1 for sub in game.subs if sub.sunk),
                boat_torpedoes=(None if boat_sub is None
                                else boat_load - boat_sub.torpedoes_left),
                wall=round(time.time() - started))


def summarise(rows) -> dict:
    summary = {}
    for row in sorted(rows, key=lambda row: (row["scenario"], row["seed"])):
        entry = summary.setdefault(row["scenario"], {"frigate": 0, "boat": 0, "open": 0,
                                                     "runs": 0})
        entry["runs"] += 1
        if row["result"] is None:
            entry["open"] += 1
        else:
            entry["frigate" if row["result"] == "SIEG" else "boat"] += 1
    return summary


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    jobs = [(scenario, seed, args.dt, args.idle, args.crewed, args.short, args.max_sim_s)
            for scenario in args.scenarios for seed in args.seeds]
    # A fresh interpreter per game: no entity ids or caches carried over.
    context = multiprocessing.get_context("spawn")
    rows = []
    with context.Pool(max(1, args.jobs), maxtasksperchild=1) as pool:
        for row in pool.imap_unordered(run, jobs):
            print(json.dumps(row), flush=True)
            rows.append(row)
    rows.sort(key=lambda row: (row["scenario"], row["seed"]))
    summary = summarise(rows)
    print(json.dumps(summary, indent=1))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as stream:
            json.dump({"rows": rows, "summary": summary}, stream, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
