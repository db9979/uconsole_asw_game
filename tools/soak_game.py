"""Long headless soak of the whole game with random operator input.

For each scenario and each side the uConsole can play, a mission runs for
``--minutes`` of simulation time while a seeded random operator presses keys
(with Shift/Ctrl now and then), clicks anywhere on the canvas and drags the
wheel, at every station.  Every ``--check-every`` minutes the mission is saved,
the save goes through JSON and loads into a second game, and both continue for
a while without input: they must stay identical (deterministic continuation).
A mission that ends, or input that leaves it (quit, main menu), starts the
next one.  Frames are drawn every ``--draw-every`` updates so draw paths run
too.

Reported as failures: any exception (with traceback), a save that does not
load or does not continue identically, and resident memory growing by more
than ``--max-growth-mb`` after the first check.  The report is Markdown
(``--report``); the exit code is 1 on any failure.  A save that does not load
is diagnosed (``diagnose_load``: the innermost check that refused it, an
exception swallowed by the restore, or the first field the restored game
writes differently) and, with ``--dump-dir``, kept as gzipped JSON so it can be
loaded again offline.

    python tools/soak_game.py --minutes 10              # every scenario
    python tools/soak_game.py --scenario s8_meerenge --minutes 120

The nightly workflow (.github/workflows/soak.yml) runs it per scenario and
files an issue with the report when it fails.  Not a hardware test: frame time
on the uConsole is out of its scope.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import random
import sys
import time
import traceback
from tempfile import TemporaryDirectory

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from src.core import config  # noqa: E402
from src.core.game import Game  # noqa: E402
from src.core.game_save import _same_save_value  # noqa: E402

DT = 0.1
SIDES = ("frigate", "uboot")
_KEYS = ([getattr(pygame, f"K_{n}") for n in range(10)]
         + [getattr(pygame, f"K_{c}") for c in "abcdefghijklmnopqrstuvwxyz"]
         + [getattr(pygame, f"K_F{n}") for n in range(1, 12)]
         + [pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT,
            pygame.K_RETURN, pygame.K_ESCAPE, pygame.K_TAB, pygame.K_SPACE,
            pygame.K_PAGEUP, pygame.K_PAGEDOWN, pygame.K_BACKSPACE,
            pygame.K_PLUS, pygame.K_MINUS, pygame.K_PERIOD])


def rss_mb() -> float:
    """Resident memory of this process (Linux /proc, else ru_maxrss)."""
    try:
        with open("/proc/self/statm", encoding="ascii") as stream:
            pages = int(stream.read().split()[1])
        return pages * os.sysconf("SC_PAGE_SIZE") / 1e6
    except (OSError, ValueError, AttributeError):
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e3


def first_difference(left, right, path="$"):
    """The JSON path of the first value two save trees disagree on, or None."""
    if isinstance(left, dict) and isinstance(right, dict):
        for key in sorted(set(left) | set(right)):
            if key not in left or key not in right:
                return f"{path}.{key} (only in {'restored' if key in left else 'saved'})"
            found = first_difference(left[key], right[key], f"{path}.{key}")
            if found:
                return found
        return None
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        for index, (a, b) in enumerate(zip(left, right)):
            found = first_difference(a, b, f"{path}[{index}]")
            if found:
                return found
        if len(left) != len(right):
            return f"{path} (length {len(right)} saved, {len(left)} restored)"
        return None
    if _same_save_value(left, right):
        return None
    return f"{path}: saved {_short(right)}, restored {_short(left)}"


def _short(value) -> str:
    text = json.dumps(value, allow_nan=True, default=repr)
    return text if len(text) <= 120 else text[:117] + "..."


def diagnose_load(document: dict) -> str:
    """Why ``Game._load_save_data`` refuses a save, for the soak report.

    Loads the save once more under a tracer and names the innermost function
    of the game that first answered False (a validator), an exception the
    restore swallowed, or, when the restore itself succeeded, the first field
    the restored game saves differently.  Diagnosis only: it never changes how
    the game loads.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(root, "src") + os.sep
    refusals, errors = [], []

    def where(frame) -> str:
        code = frame.f_code
        return (f"{os.path.relpath(code.co_filename, root)}:{frame.f_lineno} "
                f"in {code.co_name}()")

    def tracer(frame, event, arg):
        if not frame.f_code.co_filename.startswith(src):
            return tracer
        if event == "return" and arg is False and len(refusals) < 500_000:
            # A generator's yield is a return event too: all(check(x) for x)
            # links the function, its generator expression and the check.
            refusals.append((id(frame), id(frame.f_back), where(frame)))
        elif (event == "exception" and len(errors) < 3
              and not issubclass(arg[0], (GeneratorExit, StopIteration))):
            kind, value, _tb = arg
            errors.append(f"{kind.__name__}: {value} at {where(frame)}")
        return tracer

    twin = Game(seed=1, start_menu=True, show_splash=False, audio_enabled=False,
                language="en")
    sys.settrace(tracer)
    try:
        loaded = twin._load_save_data(json.loads(json.dumps(document)))
    finally:
        sys.settrace(None)
    if loaded:
        return "loads on a second attempt (state-dependent refusal)"
    lines = []
    # Many helpers answer False on the way; the refusal is the chain of False
    # answers that reached the loader: from the loader's own return, each
    # step is the latest earlier False returned to that frame by a callee.
    chain = []
    index = len(refusals) - 1
    while index >= 0:
        frame_id, _caller, text = refusals[index]
        chain.append(text)
        index -= 1
        while index >= 0 and refusals[index][1] != frame_id:
            index -= 1
    if chain:
        shown = chain[::-1]
        lines.append("refused by: " + " <- ".join(shown[:4])
                     + (" <- ..." if len(shown) > 4 else ""))
    lines += ["exception: " + text for text in errors]
    # Refused by the loader itself: the restore raised or the restored game
    # saves differently; name the first field it writes differently.
    if len(chain) > 1:
        return "\n".join(lines)
    try:
        from src.core.save_migrate import migrate
        data = migrate(json.loads(json.dumps(document)))
        probe = Game(seed=1, start_menu=True, show_splash=False, audio_enabled=False,
                     language="en")
        probe.runtime_catalog = probe._catalog_for_save(data)
        probe._restore_state(data)
        canonical = json.loads(json.dumps(probe.save_state(), allow_nan=True))
        canonical["next_entity_ids"] = data["next_entity_ids"]
        difference = first_difference(canonical, data)
        if difference:
            lines.append("restored game differs at " + difference)
    except Exception as exc:  # noqa: BLE001 - diagnosis must not fail the soak
        lines.append(f"restore raises {type(exc).__name__}: {exc}")
    return "\n".join(lines) or "no reason found"


def _comparable(game) -> dict:
    state = json.loads(json.dumps(game.save_state(), allow_nan=False))
    state.pop("next_entity_ids")
    return state


class Operator:
    """A seeded random operator: keys, modifiers, clicks and the wheel."""

    def __init__(self, seed: int):
        self.rng = random.Random(seed)
        self.held = []

    def events(self):
        rng = self.rng
        out = []
        while self.held and rng.random() < 0.5:
            key = self.held.pop()
            out.append(pygame.event.Event(pygame.KEYUP, key=key, mod=0, unicode=""))
        if rng.random() < 0.12:
            key = rng.choice(_KEYS)
            mod = (pygame.KMOD_SHIFT if rng.random() < 0.15 else 0) | (
                pygame.KMOD_CTRL if rng.random() < 0.08 else 0)
            name = pygame.key.name(key)
            out.append(pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod,
                                          unicode=name if len(name) == 1 else ""))
            self.held.append(key)
        if rng.random() < 0.03:
            pos = (rng.randrange(config.SCREEN_W), rng.randrange(config.SCREEN_H))
            button = rng.choice((1, 1, 1, 3))
            out.append(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=button))
            out.append(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=button))
        if rng.random() < 0.01:
            out.append(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=rng.choice((-1, 1)),
                                          flipped=False))
        return out


class Soak:
    def __init__(self, args, scenario: str, side: str, seed: int):
        self.args = args
        self.scenario = scenario
        self.side = side
        self.seed = seed
        self.failures = []
        self.missions = 0
        self.outcomes = {}
        self.checks = 0
        self.events = 0
        self.rss = []

    def new_game(self, index: int):
        game = Game(seed=self.seed + index, start_menu=False, show_splash=False,
                    audio_enabled=False, language="en")
        assert game.start_new_game(self.scenario, "fixed", seed=self.seed + index)
        if self.side == "uboot":
            game.local_side = "uboot"
            game._update(0.05)
        self.missions += 1
        return game

    def fail(self, kind: str, detail: str) -> None:
        if len(self.failures) < 20:
            self.failures.append((kind, detail))

    def dump(self, document: dict, game) -> str:
        """Keep a refused save in ``--dump-dir``; the report names the file."""
        if not self.args.dump_dir:
            return ""
        os.makedirs(self.args.dump_dir, exist_ok=True)
        name = f"{self.scenario}-{self.side}-{self.seed}-t{game.sim_t:.0f}.json.gz"
        path = os.path.join(self.args.dump_dir, name)
        with gzip.open(path, "wt", encoding="utf-8") as stream:
            json.dump(document, stream, allow_nan=False, sort_keys=True)
        return f"\nsave kept as {name}"

    def mission_left(self, game) -> bool:
        return (not game.running or game.main_menu or game.in_menu
                or game.editor is not None or game.game_over)

    def check_continuation(self, game) -> None:
        self.checks += 1
        document = json.loads(json.dumps(game.save_state(), allow_nan=False))
        twin = Game(seed=1, start_menu=True, show_splash=False, audio_enabled=False,
                    language="en")
        if not twin._load_save_data(document):
            self.fail("save", f"t={game.sim_t:.0f}s: the save does not load\n"
                              + diagnose_load(document) + self.dump(document, game))
            return
        original = Game(seed=1, start_menu=True, show_splash=False,
                        audio_enabled=False, language="en")
        if not original._load_save_data(json.loads(json.dumps(document))):
            self.fail("save", f"t={game.sim_t:.0f}s: the save does not load twice")
            return
        for _ in range(int(self.args.check_s / DT)):
            original.update(DT)
            twin.update(DT)
        if not _same_save_value(_comparable(original), _comparable(twin)):
            self.fail("determinism",
                      f"t={game.sim_t:.0f}s: two loads of one save diverged within "
                      f"{self.args.check_s:.0f} s")

    def run(self) -> None:
        operator = Operator(self.seed)
        game = self.new_game(0)
        steps = int(self.args.minutes * 60.0 / DT)
        check_every = max(1, int(self.args.check_every * 60.0 / DT))
        for step in range(1, steps + 1):
            try:
                for event in operator.events():
                    self.events += 1
                    game.handle_event(event)
                game.update(DT)
                if step % self.args.draw_every == 0:
                    game.draw()
            except Exception:  # noqa: BLE001 - the soak records every failure
                self.fail("exception", f"{self.scenario}/{self.side} step {step} "
                                       f"t={getattr(game, 'sim_t', 0):.0f}s station="
                                       f"{getattr(game, 'station', '?')}\n"
                                       + traceback.format_exc(limit=12))
                game = self.new_game(self.missions)
                continue
            if self.mission_left(game):
                reason = "ended" if game.game_over else "left"
                self.outcomes[reason] = self.outcomes.get(reason, 0) + 1
                game = self.new_game(self.missions)
                continue
            if step % check_every == 0:
                try:
                    self.check_continuation(game)
                except Exception:  # noqa: BLE001
                    self.fail("save", traceback.format_exc(limit=12))
                self.rss.append(rss_mb())
        if len(self.rss) >= 2 and self.rss[-1] - self.rss[0] > self.args.max_growth_mb:
            self.fail("memory", f"resident memory grew {self.rss[0]:.0f} -> "
                                f"{self.rss[-1]:.0f} MB")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scenario", action="append",
                        help="scenario key (repeatable; default: all)")
    parser.add_argument("--side", action="append", choices=SIDES)
    parser.add_argument("--minutes", type=float, default=10.0,
                        help="simulation minutes per scenario and side")
    parser.add_argument("--check-every", type=float, default=10.0,
                        help="minutes between save/continuation checks")
    parser.add_argument("--check-s", type=float, default=30.0,
                        help="seconds both loaded copies run on")
    parser.add_argument("--draw-every", type=int, default=10)
    parser.add_argument("--max-growth-mb", type=float, default=200.0)
    parser.add_argument("--seed", type=int, default=None,
                        help="default: from the date, so each night differs")
    parser.add_argument("--report", default=None)
    parser.add_argument("--dump-dir", default=None,
                        help="keep every save that does not load here (gzipped JSON)")
    args = parser.parse_args(argv)
    scenarios = args.scenario or list(config.SCENARIO_ORDER)
    unknown = [key for key in scenarios if key not in config.SCENARIOS]
    if unknown:
        parser.error(f"unknown scenario: {', '.join(unknown)}")
    seed = args.seed if args.seed is not None else int(time.strftime("%Y%m%d")) % 900_000_000 + 1
    lines = [f"# Soak report (seed {seed}, {args.minutes:g} sim min per run)", ""]
    failed = False
    previous = config.SAVE_DIR, config.SAVE_PATH
    with TemporaryDirectory(prefix="u-jagd-soak-") as saves:
        config.SAVE_DIR = saves
        config.SAVE_PATH = os.path.join(saves, "save.json")
        try:
            for scenario in scenarios:
                for side in args.side or SIDES:
                    started = time.perf_counter()
                    soak = Soak(args, scenario, side, seed)
                    soak.run()
                    wall = time.perf_counter() - started
                    status = "FAIL" if soak.failures else "ok"
                    failed = failed or bool(soak.failures)
                    summary = (f"- **{scenario} / {side}: {status}** - {soak.missions} "
                               f"missions ({soak.outcomes or 'none ended'}), "
                               f"{soak.events} input events, {soak.checks} save checks, "
                               f"memory {', '.join(f'{v:.0f}' for v in soak.rss[:1] + soak.rss[-1:])}"
                               f" MB, {wall:.0f} s wall")
                    print(summary, flush=True)
                    lines.append(summary)
                    for kind, detail in soak.failures:
                        lines += ["", f"  {kind}:", "", "```", detail.rstrip(), "```"]
        finally:
            config.SAVE_DIR, config.SAVE_PATH = previous
    lines += ["", f"Re-run: `python tools/soak_game.py --seed {seed} "
                  f"--minutes {args.minutes:g}" + "".join(
                      f" --scenario {key}" for key in (args.scenario or [])) + "`"]
    report = "\n".join(lines) + "\n"
    if args.report:
        with open(args.report, "w", encoding="utf-8") as stream:
            stream.write(report)
    print("RESULT: FAIL" if failed else "RESULT: OK")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
