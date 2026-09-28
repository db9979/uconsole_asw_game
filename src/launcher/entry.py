"""Entry point of the packaged Windows program.

``U-Jagd.exe`` opens the starter window; ``U-Jagd.exe --game …`` runs the
game itself with the normal command line of ``main.py`` (the starter launches
itself this way); ``U-Jagd.exe --self-test REPORT`` is the headless build
check used by the release workflow.
"""

from __future__ import annotations

import os
import sys


def _ensure_streams():
    """A windowed build has no console: keep tracebacks in the server log."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    from src.launcher.app import log_path

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
        results["gui"] = _gui_self_test()
        if os.name == "nt" and results["gui"] != "ok":
            code = 1
    except Exception:  # noqa: BLE001 - the report carries the traceback
        results["error"] = traceback.format_exc()
    results["ok"] = code == 0
    with open(report, "w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2)
    return code


def _gui_self_test() -> str:
    """Build the starter window once (Tk bundled, QR drawn), then close it."""
    try:
        import tkinter as tk

        from src.launcher.app import Starter

        root = tk.Tk()
        try:
            root.withdraw()
            starter = Starter(root, check_updates=False)
            starter._show_status({"state": "running", "url": "http://192.168.1.2:8765/",
                                  "code": "123ABC", "solo": False})
            root.update()
            if not starter.qr.find_all():
                return "qr missing"
        finally:
            root.destroy()
    except Exception as exc:  # noqa: BLE001 - reported, fatal only on Windows
        return f"{type(exc).__name__}: {exc}"
    return "ok"


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--game"]:
        _ensure_streams()
        import main as game_main

        return game_main.main(argv[1:])
    if argv[:1] == ["--self-test"] and len(argv) == 2:
        return self_test(argv[1])
    from src.launcher.app import run

    return run()


if __name__ == "__main__":
    raise SystemExit(main())
