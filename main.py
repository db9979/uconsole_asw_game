#!/usr/bin/env python3
"""U-Jagd – Fregatten-U-Jagd-Strategiespiel für die uConsole."""

import argparse
import random

from src.core.game import Game
from src.core.preferences import load_preferences
from src.core.version import APP_VERSION


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="ASW-Simulation fuer die uConsole")
    parser.add_argument("seed", nargs="?", type=int)
    parser.add_argument("--windowed", action="store_true")
    parser.add_argument("--no-audio", action="store_true")
    parser.add_argument("--version", action="version", version=APP_VERSION)
    args = parser.parse_args(argv)
    preferences = load_preferences()
    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(
        1, 1_000_000_000)
    Game(seed=seed, start_menu=True,
         preferences=preferences,
         fullscreen=preferences.fullscreen and not args.windowed,
         show_splash=True,
         audio_enabled=preferences.audio and not args.no_audio).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
