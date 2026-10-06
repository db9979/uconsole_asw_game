"""Main-menu page "Report a bug": QR code, report file and browser link.

The page lives on the main menu only (never over a mission). Opening it writes
``~/.u-jagd/bug-report.txt`` and prepares two GitHub new-issue links from
:mod:`src.core.bugreport`: a short one the QR code carries to a phone, and a
full one with the crash-log tail that Enter opens in a local browser when
there is one. File and browser access happen on the key press, never while
drawing. After a crashed launch the main menu preselects this entry.
"""

from __future__ import annotations

import threading
import webbrowser

import pygame

from src.core import bugreport, config, crashlog
from src.core.i18n import message, raw_text
from src.ui import layout, qr

BUG_REPORT_ENTRY = "bug_report"


class BugReportMixin:
    """State and input of the main menu's bug-report page."""

    def _init_bug_report(self) -> None:
        self.bug_report = None
        self.bug_report_offer = bool(crashlog.previous_launch_crashed)
        self._bug_report_qr = None

    def _bug_report_context(self) -> str:
        side = "submarine" if self.local_side == "uboot" else "frigate"
        return f"uConsole, {side}, {self.preferences.language}"

    def open_bug_report(self) -> None:
        """Prepare links and report file, then show the page."""
        context = self._bug_report_context()
        log = bugreport.read_log_tail()
        path = bugreport.write_report(bugreport.report_text(context, log))
        short_url = bugreport.short_issue_url(context)
        self.bug_report = {
            "url": bugreport.issue_url(context, log),
            "short_url": short_url,
            "path": bugreport.display_path(path) if path else None,
            "status": None,
        }
        matrix = qr.encode(short_url)
        self._bug_report_qr = qr.to_surface(matrix, module_px=max(1, 300 // (len(matrix) + 8)),
                                            quiet=4)
        self.bug_report_offer = False
        self.main_menu = False
        self.menu_screen = BUG_REPORT_ENTRY

    def _open_bug_report_browser(self) -> None:
        report = self.bug_report
        report["status"] = "bugreport.browser_opening"

        def run():
            # Launching a browser can take seconds; the menu keeps drawing.
            try:
                opened = webbrowser.open(report["url"], new=2)
            except Exception:  # noqa: BLE001 - any failure means "scan the QR code"
                opened = False
            report["status"] = ("bugreport.browser_opened" if opened
                                else "bugreport.no_browser")

        threading.Thread(target=run, name="bug-report-browser", daemon=True).start()

    def _handle_bug_report_key(self, key) -> None:
        if key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_o):
            self._open_bug_report_browser()
        elif key in (pygame.K_ESCAPE, pygame.K_q, pygame.K_BACKSPACE):
            self.bug_report = None
            self._bug_report_qr = None
            self.menu_screen = "scenario"
            self.main_menu = True
            self.main_menu_sel = self.main_menu_index(BUG_REPORT_ENTRY)

    def _draw_bug_report_page(self, center) -> None:
        s = self.screen
        report = self.bug_report or {}
        center(self.tr("bugreport.title"), 150, color=config.COLOR_WARN)
        code = self._bug_report_qr
        left = 150
        if code is not None:
            rect = code.get_rect(topleft=(left, 190))
            s.blit(code, rect)
            layout.blit_line(s, "bugreport.qr_caption", (left, rect.bottom + 8, rect.width, 22),
                             config.COLOR_TEXT_DIM, size=14, align="center")
        x, w = 500, 640
        layout.blit_block(s, self.tr("bugreport.intro"), x, 190, w, 84,
                          config.COLOR_TEXT, size=18)
        path = report.get("path")
        layout.blit_block(s, message("bugreport.file", path=raw_text(path)) if path
                          else self.tr("bugreport.file_failed"),
                          x, 284, w, 84, config.COLOR_TEXT, size=18)
        layout.blit_block(s, self.tr("bugreport.privacy"), x, 378, w, 60,
                          config.COLOR_TEXT_DIM, size=16)
        status = report.get("status")
        if status:
            layout.blit_line(s, status, (x, 450, w, 26),
                             config.COLOR_WARN if status == "bugreport.no_browser"
                             else config.COLOR_OK, size=18)
        center(self.tr("bugreport.hint"), 560, color=config.COLOR_TEXT_DIM,
               keys=("Enter", "Esc"))


# Main-menu entries in display order (labels in ``MAIN_MENU_LABELS``).
MAIN_MENU_ENTRIES = ("new", "training", "daily", "multiplayer", "server", "campaign", "logbook", "load",
                     "mission_editor", "unit_editor", "contact_analyzer", "options", BUG_REPORT_ENTRY,
                     "quit")
# Catalog key of each entry's label; "continue" leads while an autosave exists.
MAIN_MENU_LABELS = {"continue": "menu.continue", "new": "menu.new_game",
                    "daily": "menu.daily",
                    "multiplayer": "menu.multiplayer",
                    "server": "menu.server",
                    "training": "menu.training", "campaign": "menu.campaign",
                    "logbook": "menu.logbook",
                    "load": "menu.load", "mission_editor": "menu.mission_editor",
                    "unit_editor": "menu.unit_editor",
                    "contact_analyzer": "menu.contact_analyzer",
                    "options": "option.title", BUG_REPORT_ENTRY: "menu.bug_report",
                    "quit": "menu.quit"}
