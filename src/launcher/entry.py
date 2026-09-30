"""Entry point of the packaged Windows program.

``U-Jagd-Windows.exe [ARGS]`` starts the game straight away with the normal
command line of ``main.py``; everything else (multiplayer, side, station) is
chosen inside the game. A leading ``--game`` (the old starter's form) is
accepted and ignored. ``--self-test REPORT`` and ``--update-self-test
REPORT`` are the headless build checks used by the release workflow.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys


def log_path() -> Path:
    return Path.home() / ".u-jagd" / "logs" / "server.log"


def _ensure_streams():
    """A windowed build has no console: keep tracebacks in the server log."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = open(path, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stdout or stream
    sys.stderr = sys.stderr or stream


def self_test(report: str) -> int:
    """Start a mission headless, serve Remote Crew on loopback, fetch pages."""
    import json
    import tempfile
    import traceback
    import urllib.request

    os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ["SDL_AUDIODRIVER"] = "dummy"
    results = {}
    code = 1
    try:
        from src.core import config
        from src.core.game import Game
        from src.core.preferences import Preferences
        from src.core.version import APP_VERSION

        results["version"] = APP_VERSION
        previous = config.SAVE_DIR, config.SAVE_PATH
        with tempfile.TemporaryDirectory(prefix="u-jagd-selftest-") as saves:
            config.SAVE_DIR = saves
            config.SAVE_PATH = os.path.join(saves, "save.json")
            game = None
            try:
                game = Game(seed=1234, start_menu=False, fullscreen=False,
                            audio_enabled=False, preferences=Preferences(language="en"))
                for _ in range(30):
                    game.update(1 / 30)
                    game.draw()
                results["sim_t"] = round(game.sim_t, 3)
                console = game.commander
                console.prepare = lambda: None
                console.hosts, console.port = ("127.0.0.1",), 0
                console.autostart()
                console.pump(game)
                host, port = console.address
                for path in ("/", "/manual-en"):
                    with urllib.request.urlopen(f"http://{host}:{port}{path}",
                                                timeout=10) as response:
                        results[path] = response.status
                results["code"] = bool(console.pairing_code)
            finally:
                if game is not None:
                    game.commander.stop()
                config.SAVE_DIR, config.SAVE_PATH = previous
        code = 0 if all(results.get(p) == 200 for p in ("/", "/manual-en")) else 1
    except Exception:  # noqa: BLE001 - the report carries the traceback
        results["error"] = traceback.format_exc()
    results["ok"] = code == 0
    with open(report, "w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2)
    return code


def update_self_test(report: str) -> int:
    """Swap in ``<exe>.new`` exactly as "Install update" does, then exit.

    The install script restarts the swapped executable with ``--self-test
    REPORT``; the release workflow checks that the report appears and that
    no ``.new`` file is left behind.
    """
    import time

    from src.launcher import update

    executable = os.path.abspath(sys.executable)
    update.launch_install(executable, f"{executable}.new", ("--self-test", report))
    time.sleep(3)  # hold the file like a closing game window
    return 0


def remove_stale_update() -> None:
    """Delete an ``<exe>.new`` left by an update that could not swap in."""
    if getattr(sys, "frozen", False):
        for suffix in (".new", ".new.part"):
            try:
                os.remove(os.path.abspath(sys.executable) + suffix)
            except OSError:
                pass


def _install_update(code: int) -> int:
    """After the game asked for an update, swap in ``<exe>.new`` and restart.

    The game downloads and verifies the new program itself and then quits
    with ``update.UPDATE_EXIT_CODE``; only the frozen program can replace its
    own file. Returns 0 once the install script runs, else ``code``.
    """
    from src.launcher import update

    if not getattr(sys, "frozen", False):
        return code
    executable = os.path.abspath(sys.executable)
    downloaded = f"{executable}.new"
    if not os.path.isfile(downloaded):
        return code
    try:
        update.launch_install(executable, downloaded, log=str(log_path()))
    except update.UpdateError:
        return code
    return 0


def run_game(argv: list[str]) -> int:
    """Run the game with ``main.py``'s command line; return its exit code."""
    _ensure_streams()
    remove_stale_update()
    import main as game_main
    from src.launcher import update

    code = game_main.main(argv)
    update_code = getattr(update, "UPDATE_EXIT_CODE", None)
    if update_code is not None and code == update_code:
        return _install_update(code)
    return code


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--self-test"] and len(argv) == 2:
        return self_test(argv[1])
    if argv[:1] == ["--update-self-test"] and len(argv) == 2:
        return update_self_test(argv[1])
    if argv[:1] == ["--game"]:
        argv = argv[1:]
    return run_game(argv)


if __name__ == "__main__":
    raise SystemExit(main())
