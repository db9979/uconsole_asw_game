"""Bug report: GitHub issue links, anonymized log, report file, menu page."""

from urllib.parse import parse_qs, urlsplit

import pygame

from src.core import bugreport, crashlog
from src.core.game import Game
from src.core.game_bugreport import BUG_REPORT_ENTRY, MAIN_MENU_ENTRIES
from src.core.version import APP_VERSION
from src.ui import qr

TRACEBACK = """=== 2026-09-28 12:00:00 U-Jagd 1.3.36 started (pid 1, Python 3.11, aarch64)
--- 2026-09-28 12:01:00 U-Jagd 1.3.36 crashed (main loop):
Traceback (most recent call last):
  File "/home/dominik/games/u-jagd/src/core/game_pictures.py", line 10, in _simlog
AttributeError: 'Torpedo' object has no attribute 'id'
=== 2026-09-28 12:01:00 U-Jagd 1.3.36 ended: crash
"""


def _query(url):
    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == bugreport.NEW_ISSUE_URL
    return {key: values[0] for key, values in parse_qs(parts.query).items()}


def test_anonymize_removes_home_and_user():
    text = ("/home/dominik/games/x.py C:\\Users\\Dominik\\AppData C:/Users/eve/x "
            "/Users/anna/y dominik logged")
    out = bugreport.anonymize(text, home="/home/dominik", users=["dominik"])
    assert "dominik" not in out and "Dominik" not in out
    assert "eve" not in out and "anna" not in out
    assert out.startswith("~/games/x.py")


def test_issue_url_carries_version_platform_and_log():
    query = _query(bugreport.issue_url("uConsole menu", TRACEBACK))
    assert query["template"] == bugreport.ISSUE_TEMPLATE
    assert query["version"] == APP_VERSION
    assert "AttributeError: 'Torpedo' object has no attribute 'id'" in query["title"]
    assert "AttributeError" in query["log"]
    assert "/home/dominik" not in query["log"]


def test_issue_url_keeps_the_newest_lines_within_the_limit():
    log = "\n".join(f"line {i:05d} " + "x" * 60 for i in range(2000)) + "\nValueError: last"
    url = bugreport.issue_url("", log)
    assert len(url) <= bugreport.URL_MAX_CHARS
    query = _query(url)
    assert query["log"].endswith("ValueError: last")
    assert "line 00000" not in query["log"]


def test_short_url_fits_the_qr_code():
    url = bugreport.short_issue_url("context " * 50)
    assert len(url) <= bugreport.QR_URL_MAX_CHARS
    assert "log" not in _query(url)
    qr.encode(url)  # raises if the payload does not fit


def test_report_file_is_written_atomically(tmp_path):
    path = bugreport.write_report(bugreport.report_text("ctx", TRACEBACK), root=str(tmp_path))
    assert path == str(tmp_path / bugreport.REPORT_FILE)
    text = (tmp_path / bugreport.REPORT_FILE).read_text(encoding="utf-8")
    assert f"Version: {APP_VERSION}" in text and "AttributeError" in text
    assert not (tmp_path / (bugreport.REPORT_FILE + ".tmp")).exists()


def test_report_file_refuses_symlink(tmp_path):
    target = tmp_path / "elsewhere.txt"
    target.write_text("keep", encoding="utf-8")
    (tmp_path / bugreport.REPORT_FILE).symlink_to(target)
    assert bugreport.write_report("x", root=str(tmp_path)) is None
    assert target.read_text(encoding="utf-8") == "keep"


def test_last_launch_crashed(tmp_path):
    log = tmp_path / crashlog.CRASH_LOG
    assert crashlog.last_launch_crashed(str(tmp_path)) is False
    log.write_text(TRACEBACK, encoding="utf-8")
    assert crashlog.last_launch_crashed(str(tmp_path)) is True
    with log.open("a", encoding="utf-8") as handle:
        handle.write("=== 2026-09-28 13:00:00 U-Jagd 1.3.40 started (pid 2, Python 3.11, x)\n"
                     "--- 2026-09-28 13:00:05 mission s1_patrouille, world fixed\n"
                     "=== 2026-09-28 13:10:00 U-Jagd 1.3.40 ended: normal\n")
    assert crashlog.last_launch_crashed(str(tmp_path)) is False
    with log.open("a", encoding="utf-8") as handle:
        handle.write("=== 2026-09-28 14:00:00 U-Jagd 1.3.40 started (pid 3, Python 3.11, x)\n")
    assert crashlog.last_launch_crashed(str(tmp_path)) is True


def test_install_remembers_previous_crash_and_notes_missions(tmp_path):
    (tmp_path / crashlog.CRASH_LOG).write_text(TRACEBACK, encoding="utf-8")
    session = crashlog.install(str(tmp_path))
    try:
        assert crashlog.previous_launch_crashed is True
        crashlog.note("mission s1_patrouille, world fixed")
    finally:
        crashlog.finish(session, "normal")
        crashlog.previous_launch_crashed = False
    text = (tmp_path / crashlog.CRASH_LOG).read_text(encoding="utf-8")
    assert "mission s1_patrouille, world fixed" in text
    crashlog.note("after finish")
    assert "after finish" not in (tmp_path / crashlog.CRASH_LOG).read_text(encoding="utf-8")


def _key(game, key):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode=""))


def test_main_menu_bug_report_page(tmp_path, monkeypatch):
    monkeypatch.setattr(bugreport.config, "SAVE_DIR", str(tmp_path))
    (tmp_path / crashlog.CRASH_LOG).write_text(TRACEBACK, encoding="utf-8")
    game = Game(seed=7, start_menu=True, show_splash=False, audio_enabled=False)
    game.main_menu_sel = MAIN_MENU_ENTRIES.index(BUG_REPORT_ENTRY)
    _key(game, pygame.K_RETURN)
    assert game.menu_screen == BUG_REPORT_ENTRY and not game.main_menu
    assert (tmp_path / bugreport.REPORT_FILE).exists()
    assert "AttributeError" in _query(game.bug_report["url"])["log"]
    assert len(game.bug_report["short_url"]) <= bugreport.QR_URL_MAX_CHARS
    game.draw_menu()
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda url, new=0: opened.append(url) or False)
    _key(game, pygame.K_RETURN)
    for thread in __import__("threading").enumerate():
        if thread.name == "bug-report-browser":
            thread.join(timeout=2)
    assert opened == [game.bug_report["url"]]
    assert game.bug_report["status"] == "bugreport.no_browser"
    game.draw_menu()
    _key(game, pygame.K_ESCAPE)
    assert game.main_menu and game.menu_screen != BUG_REPORT_ENTRY
    assert game.main_menu_sel == MAIN_MENU_ENTRIES.index(BUG_REPORT_ENTRY)


def test_crashed_launch_preselects_bug_report(monkeypatch):
    monkeypatch.setattr(crashlog, "previous_launch_crashed", True)
    game = Game(seed=7, start_menu=True, show_splash=False, audio_enabled=False)
    assert game.bug_report_offer
    assert game.main_menu_sel == MAIN_MENU_ENTRIES.index(BUG_REPORT_ENTRY)
    game.draw_menu()
