"""Update notice on the start screen and the main menu (1.3.110).

A published newer release is never installed on its own. At launch a daemon
thread asks GitHub once (``src/launcher/update.fetch_notice``); when a newer
release exists, the splash and the main menu show its version, its changelog
entry in the game language, whether saves stop loading (a different
``SAVE_VERSION``) and an "Update now" button (key U or a click).

The button hands over to whatever installed the game: the Windows program
downloads its new ``.exe`` in the background (size and SHA-256 checked), swaps
it in once it has closed and starts it (``src/launcher/update.py``); the macOS
app downloads its processor's zip, unpacks the new ``U-Jagd.app`` beside the
running one and swaps the bundle once it has closed; in the
``starter`` mode it exits with ``UPDATE_EXIT_CODE`` and the Windows entry
point (``src/launcher/entry.py``) does that. The uConsole launcher (``u_jagd_updater.py install``) waits for the game
to close, updates, then starts it again. Any other install opens the release
page in the browser. Nothing here touches simulation state.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import webbrowser

import pygame

from src.core import config
from src.core.i18n import message, raw_text
from src.core import save_migrate
from src.core.version import APP_VERSION, SAVE_VERSION
from src.launcher import update
from src.launcher.update import UPDATE_EXIT_CODE
from src.ui import layout

UPDATE_MODES = ("windows", "macos", "starter", "uconsole", "browser")
ROOT = Path(__file__).resolve().parents[2]
UPDATER = ROOT / "packaging" / "uconsole" / "u_jagd_updater.py"
# Start screen: top right, over the sky; main menu: left of the entries.
SPLASH_NOTICE_RECT = (792, 26, 462, 282)
MENU_NOTICE_RECT = (24, 148, 344, 412)
PANEL_FILL = (4, 16, 20, 205)
ACCENT = (236, 204, 128)


def default_update_mode() -> str:
    """How "Update now" installs: the uConsole launcher for its own checkout."""
    if getattr(sys, "frozen", False):
        if sys.platform != "darwin":
            return "windows"
        # A bundle macOS runs translocated, or in a folder this user cannot
        # write, cannot replace itself: those open the release page.
        replaceable = (update.mac_bundle(sys.executable) is not None
                       and update.mac_asset_name() is not None)
        return "macos" if replaceable else "browser"
    if (os.name == "posix" and UPDATER.exists() and (ROOT / ".git").exists()
            and Path(sys.prefix).resolve() == (ROOT / ".venv").resolve()):
        return "uconsole"
    return "browser"


def remove_stale_download() -> None:
    """Delete an ``<exe>.new`` left by an update that could not swap in."""
    if sys.platform == "darwin":
        bundle = update.mac_bundle(sys.executable)
        if bundle is not None:
            update.remove_mac_leftovers(bundle)
        return
    for suffix in (".new", ".new.part"):
        try:
            os.remove(os.path.abspath(sys.executable) + suffix)
        except OSError:
            pass


class UpdateNoticeMixin:
    def _init_update_notice(self) -> None:
        self.update_notice = None
        self.update_mode = "browser"
        self.update_args: tuple = ()
        self.update_failed = False
        self.update_exit_code = 0
        self._update_thread = None
        self._update_button = None
        # Windows download: percent while running, then the file to swap in.
        self.update_progress = None
        self._update_ready = None

    def start_update_check(self, mode: str | None = None, args=()) -> bool:
        """Ask GitHub once in the background; False when checks are off."""
        if (os.environ.get("U_JAGD_NO_UPDATE_CHECK") or os.environ.get("U_JAGD_NO_UPDATE")
                or self.web_mode or self._update_thread is not None):
            return False
        self.update_mode = mode if mode in UPDATE_MODES else default_update_mode()
        self.update_args = tuple(str(arg) for arg in args)
        if self.update_mode in ("windows", "macos"):
            remove_stale_download()

        def work() -> None:
            try:
                notice = update.fetch_notice(APP_VERSION)
            except update.UpdateError:
                return  # offline: no notice at all
            self.update_notice = notice  # one reference store, read by draw

        self._update_thread = threading.Thread(target=work, name="update-check", daemon=True)
        self._update_thread.start()
        return True

    def update_notice_visible(self) -> bool:
        return self.update_notice is not None and (
            self.splash_active
            or (self.in_menu and self.main_menu and self.editor is None
                and not self.administration_open and not self.welcome_active))

    # --- action -------------------------------------------------------------

    def request_update(self) -> bool:
        """"Update now": hand over to the installer; True when the game ends."""
        notice = self.update_notice
        if notice is None:
            return False
        if self.update_mode == "windows":
            self._download_windows_update(notice)
            return False
        if self.update_mode == "macos":
            self._download_macos_update(notice)
            return False
        if self.update_mode == "starter":
            self.update_exit_code = UPDATE_EXIT_CODE
            self.running = False
            return True
        if self.update_mode == "uconsole" and self._spawn_updater():
            self.running = False
            return True
        if self.update_mode == "uconsole":
            self.update_failed = True
            return False
        webbrowser.open(notice.page)
        return False

    def _spawn_updater(self) -> bool:
        """Start ``u_jagd_updater.py install``; it waits until this game quits."""
        python = shutil.which("python3") or sys.executable
        try:
            subprocess.Popen([python, str(UPDATER), "install", *self.update_args],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, close_fds=True,
                             start_new_session=True)
        except OSError:
            return False
        return True

    def _download_windows_update(self, notice) -> None:
        """Fetch the new program beside this one; ``update_tick`` swaps it."""
        if self.update_progress is not None:
            return  # already downloading
        self.update_failed = False
        self.update_progress = 0
        executable = os.path.abspath(sys.executable)
        target = f"{executable}.new"

        def progress(done: int, total: int) -> None:
            self.update_progress = int(done * 100 / max(1, total))

        def work() -> None:
            try:
                release = update.check_latest(APP_VERSION)
                if release is None:
                    webbrowser.open(notice.page)
                    self.update_progress = None
                    return
                update.download(release, target, progress=progress)
            except update.UpdateError:
                self.update_failed = True
                self.update_progress = None
                return
            self._update_ready = (executable, target)

        threading.Thread(target=work, name="update-download", daemon=True).start()

    def _download_macos_update(self, notice) -> None:
        """Fetch and unpack the new app beside this one; ``update_tick`` swaps it."""
        if self.update_progress is not None:
            return  # already downloading
        bundle = update.mac_bundle(sys.executable)
        asset = update.mac_asset_name()
        if bundle is None or asset is None:
            webbrowser.open(notice.page)
            return
        self.update_failed = False
        self.update_progress = 0

        def progress(done: int, total: int) -> None:
            # The last percent is the unpacking.
            self.update_progress = min(99, int(done * 100 / max(1, total)))

        def work() -> None:
            try:
                release = update.check_latest(APP_VERSION, asset_name=asset)
                if release is None:
                    webbrowser.open(notice.page)
                    self.update_progress = None
                    return
                update.download(release, bundle.archive, progress=progress)
                update.unpack_app(bundle.archive, bundle)
            except update.UpdateError:
                update.remove_mac_leftovers(bundle)
                self.update_failed = True
                self.update_progress = None
                return
            self.update_progress = 100
            self._update_ready = bundle

        threading.Thread(target=work, name="update-download", daemon=True).start()

    def update_tick(self) -> None:
        """Main loop: once the download is complete, swap and restart."""
        ready, self._update_ready = self._update_ready, None
        if ready is None:
            return
        log = str(Path.home() / ".u-jagd" / "updater.log")
        try:
            if isinstance(ready, update.MacBundle):
                update.launch_mac_install(ready, log=log)
            else:
                update.launch_install(*ready, log=log)
        except update.UpdateError:
            self.update_failed = True
            self.update_progress = None
            return
        self.running = False  # the script replaces the file once we have exited

    def handle_update_event(self, e) -> bool:
        """Key U or a click on the button while the notice shows."""
        if not self.update_notice_visible():
            return False
        if e.type == pygame.KEYDOWN and e.key == pygame.K_u:
            self.request_update()
            return True
        if e.type == pygame.MOUSEBUTTONDOWN and getattr(e, "button", 0) == 1:
            canvas = self._window_to_canvas(getattr(e, "pos", None))
            if (canvas is not None and self._update_button is not None
                    and self._update_button.collidepoint(canvas)):
                self.request_update()
                return True
        return False

    # --- drawing ------------------------------------------------------------

    def draw_update_notice(self, surface, splash: bool) -> None:
        notice = self.update_notice
        self._update_button = None
        if notice is None:
            return
        rect = pygame.Rect(SPLASH_NOTICE_RECT if splash else MENU_NOTICE_RECT)
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel.fill(PANEL_FILL)
        surface.blit(panel, rect)
        pygame.draw.rect(surface, ACCENT, rect, 1)
        layout.corner_brackets(surface, rect)
        x, w = rect.x + 12, rect.w - 24
        y = rect.y + 8
        layout.blit_line(surface, message("update.available", version=notice.version),
                         (x, y, w, 26), ACCENT, size=20)
        y += 26
        layout.blit_line(surface, message("update.installed", version=APP_VERSION),
                         (x, y, w, 20), config.COLOR_TEXT_DIM, size=14)
        y += 22
        button_h = 34
        # Saves from format MIGRATE_FROM on are lifted by newer releases.
        warn_h = 58 if (notice.breaks_saves(SAVE_VERSION)
                        and SAVE_VERSION < save_migrate.MIGRATE_FROM) else 0
        notes_h = rect.bottom - 10 - button_h - 6 - warn_h - y
        notes = notice.notes_for(self.translator.language)
        if notes and notes_h > 16:
            layout.blit_block(surface, raw_text(notes), x, y, w, notes_h,
                              config.COLOR_TEXT, size=14, min_size=12)
        y += max(0, notes_h)
        if warn_h:
            layout.blit_block(surface, "update.saves_break", x, y, w, warn_h,
                              config.COLOR_WARN, size=14, min_size=12)
            y += warn_h
        button = pygame.Rect(x, rect.bottom - 10 - button_h, w, button_h)
        pygame.draw.rect(surface, (18, 60, 56), button, border_radius=4)
        pygame.draw.rect(surface, ACCENT, button, 1, border_radius=4)
        if self.update_failed:
            label = "update.failed"
        elif self.update_progress is not None:
            label = message("update.downloading", percent=self.update_progress)
        elif self.update_mode == "browser":
            label = "update.button_browser"
        else:
            label = "update.button"
        layout.blit_line(surface, label, button.inflate(-12, -6), ACCENT, size=18,
                         align="center")
        self._update_button = button
