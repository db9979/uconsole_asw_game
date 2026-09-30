#!/usr/bin/env python3
"""U-Jagd – Fregatten-U-Jagd-Strategiespiel für die uConsole."""

import argparse
import ipaddress
import os
import random
from pathlib import Path
from urllib.parse import urlsplit

from src.core.crashlog import run_logged
from src.core.game import Game
from src.core.preferences import load_preferences
from src.core.version import APP_VERSION
from src.commander.web_auth import WebHostAuth


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="ASW-Simulation fuer die uConsole")
    parser.add_argument("seed", nargs="?", type=int)
    parser.add_argument("--windowed", action="store_true")
    parser.add_argument("--no-audio", action="store_true")
    parser.add_argument("--multiplayer", action="store_true",
                        help="go straight into the multiplayer lobby after the "
                             "splash, as the main-menu entry does (Remote Crew "
                             "starts in crew mode)")
    # Old name of --multiplayer, kept so existing shortcuts keep working.
    parser.add_argument("--remote-crew", dest="multiplayer", action="store_true",
                        help=argparse.SUPPRESS)
    # Advanced: one paired browser operates every station and the game
    # controls (this launch only, never persisted); the game has no menu row.
    parser.add_argument("--solo-crew", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--web-host", action="store_true",
                        help="run one browser-only room behind a local HTTPS reverse proxy")
    parser.add_argument("--public-origin", metavar="HTTPS_ORIGIN",
                        help="exact public HTTPS origin used by the reverse proxy; "
                             "without --web-host, Remote Crew (F9 or the lobby) "
                             "answers on this proxy origin and on its LAN address")
    parser.add_argument("--web-port", type=int, default=8765)
    parser.add_argument("--web-bind", default="127.0.0.1", metavar="PRIVATE_IP",
                        help="IPv4 address to listen on; use the device's private LAN IP "
                             "when the HTTPS proxy runs on another trusted LAN host")
    parser.add_argument("--reset-web-host-password", action="store_true",
                        help="reset the web host password during this web-host launch")
    parser.add_argument("--version", action="version", version=APP_VERSION)
    args = parser.parse_args(argv)
    if args.web_host and not args.public_origin:
        parser.error("--web-host requires --public-origin")
    if args.web_host and (args.multiplayer or args.solo_crew):
        parser.error("--web-host excludes --multiplayer and --solo-crew")
    if args.multiplayer and args.solo_crew:
        parser.error("--multiplayer excludes --solo-crew")
    if args.web_bind != "127.0.0.1" and not args.web_host:
        parser.error("--web-bind requires --web-host")
    if args.reset_web_host_password and not args.web_host:
        parser.error("--reset-web-host-password requires --web-host")
    if args.public_origin is not None:
        try:
            origin = urlsplit(args.public_origin)
            valid_origin = (origin.scheme == "https" and bool(origin.hostname)
                            and not origin.path and not origin.query and not origin.fragment
                            and not origin.username and not origin.password
                            and not args.public_origin.endswith("/")
                            and origin.port != 0)
        except ValueError:
            valid_origin = False
        if not valid_origin:
            parser.error("--public-origin must be an exact HTTPS origin")
    if not 1024 <= args.web_port <= 65535:
        parser.error("--web-port must be between 1024 and 65535")
    if args.web_host:
        try:
            bind = ipaddress.IPv4Address(args.web_bind)
        except ipaddress.AddressValueError:
            parser.error("--web-bind must be a private or loopback IPv4 address")
        if not (bind.is_loopback or any(bind in ipaddress.IPv4Network(network)
                for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))):
            parser.error("--web-bind must be a private or loopback IPv4 address")
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        os.environ["SDL_AUDIODRIVER"] = "dummy"
    # Without a terminal (uConsole menu entry) a crash would leave no trace:
    # ~/.u-jagd/crash.log records start, end and any traceback or fatal signal.
    return run_logged(lambda: _start(args))


def _start(args) -> int:
    auth = WebHostAuth(Path.home() / ".u-jagd" / "web-host.json") if args.web_host else None
    if args.reset_web_host_password:
        auth.reset_local()
    preferences = load_preferences()
    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(
        1, 1_000_000_000)
    game = Game(seed=seed, start_menu=True,
                preferences=preferences,
                fullscreen=preferences.fullscreen and not args.windowed and not args.web_host,
                show_splash=not args.web_host,
                audio_enabled=preferences.audio and not args.no_audio and not args.web_host,
                web_mode=args.web_host)
    if args.web_host:
        try:
            game.commander.start_web(auth, args.public_origin, args.web_port,
                                     args.web_bind)
        except Exception:
            game.commander.stop()
            game.audio.shutdown()
            import pygame
            pygame.quit()
            raise
        if not auth.configured:
            print(f"Web host setup code (15 minutes): {auth.setup_code}", flush=True)
        print(f"Web room: {args.public_origin}/admin", flush=True)
        print(f"Proxy upstream: http://{args.web_bind}:{args.web_port}", flush=True)
    elif args.public_origin is not None:
        # Local game: Remote Crew (F9) also answers behind this HTTPS proxy.
        game.commander.public_origin = args.public_origin
    if (args.solo_crew or args.multiplayer) and args.web_port != 8765:
        game.commander.port = args.web_port
    if args.solo_crew:
        game.commander.autostart_solo()
    elif args.multiplayer:
        # As the main-menu entry: the lobby starts Remote Crew in crew mode.
        game.open_lobby()
    game.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
