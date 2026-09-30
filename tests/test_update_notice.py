"""Update notice: new releases are shown with their changelog, never installed
until the player presses "Update now" (1.3.107)."""

import io
import json
import time
import urllib.error

import pygame
import pytest

from src.core import game_update
from src.core.game import Game
from src.core.version import APP_VERSION, SAVE_VERSION
from src.launcher import update
from src.ui import layout

CHANGELOG_EN = """# Changelog

## 9.9.9

Release 9.9.9 adds a **lighthouse**. See [the manual](docs/manual.md) and
`L` for the `lamp`.

## 1.3.106

Older.
"""
CHANGELOG_DE = CHANGELOG_EN.replace("adds a", "bringt einen").replace("## 1.3.106", "## 1.0.0")


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _opener(save_version=SAVE_VERSION, tag="v9.9.9", files=None):
    files = files if files is not None else {
        "CHANGELOG.md": CHANGELOG_EN, "CHANGELOG.de.md": CHANGELOG_DE,
        "src/core/version.py": f'APP_VERSION = "9.9.9"\nSAVE_VERSION = {save_version}\n'}
    seen = []

    def opener(request, timeout):
        url = request.full_url
        seen.append(url)
        if url == update.LATEST_RELEASE_API:
            return _Response(json.dumps({
                "tag_name": tag, "draft": False, "prerelease": False, "body": "Body text.",
                "html_url": "https://github.com/db9979/uconsole_asw_game/releases/tag/v9.9.9",
            }).encode())
        prefix = f"https://raw.githubusercontent.com/{update.REPOSITORY}/v9.9.9/"
        assert url.startswith(prefix)
        path = url[len(prefix):]
        if path not in files:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return _Response(files[path].encode())

    opener.seen = seen
    return opener


def test_notice_carries_changelog_in_both_languages_and_save_break():
    notice = update.fetch_notice("1.3.106", opener=_opener(save_version=SAVE_VERSION + 1))
    assert notice.version == "9.9.9"
    assert notice.notes_for("en") == ("Release 9.9.9 adds a lighthouse. See the manual "
                                      "and L for the lamp.")
    assert notice.notes_for("de").startswith("Release 9.9.9 bringt einen lighthouse")
    assert notice.breaks_saves(SAVE_VERSION)
    assert not update.fetch_notice("1.3.106", opener=_opener()).breaks_saves(SAVE_VERSION)
    assert notice.page.endswith("/releases/tag/v9.9.9")


def test_notice_falls_back_to_release_text_and_unknown_save_version():
    notice = update.fetch_notice("1.3.106", opener=_opener(files={}))
    assert notice.notes_for("de") == "Body text."  # English release text
    assert notice.save_version is None and not notice.breaks_saves(SAVE_VERSION)


def test_no_notice_for_current_older_or_missing_releases():
    for tag in ("v1.3.106", "v1.0.0", "latest"):
        assert update.fetch_notice("1.3.106", opener=_opener(tag=tag)) is None

    def missing(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

    assert update.fetch_notice("1.3.106", opener=missing) is None

    def offline(request, timeout):
        raise urllib.error.URLError("offline")

    with pytest.raises(update.UpdateError):
        update.fetch_notice("1.3.106", opener=offline)


def test_plain_notes_are_bounded_and_markdown_free():
    text = update.plain_notes("# Head\n\n" + "word " * 500)
    assert len(text) <= update.MAX_NOTES_CHARS and text.endswith("…")
    assert "#" not in text
    assert update.plain_notes(None) == ""
    assert update.changelog_entry(CHANGELOG_EN, "1.3.106") == "Older."
    assert update.changelog_entry(CHANGELOG_EN, "2.0.0") == ""


def _notice(save_version=SAVE_VERSION):
    return update.Notice("9.9.9", update.RELEASES_PAGE,
                         {"en": "Adds a lighthouse.", "de": "Bringt einen Leuchtturm."},
                         save_version)


def _game(**kwargs):
    return Game(seed=7, start_menu=True, audio_enabled=False, **kwargs)


def test_check_is_off_in_tests_and_web_mode(monkeypatch):
    game = _game(show_splash=True)
    monkeypatch.setenv("U_JAGD_NO_UPDATE_CHECK", "1")
    assert game.start_update_check() is False
    monkeypatch.delenv("U_JAGD_NO_UPDATE_CHECK")
    monkeypatch.delenv("U_JAGD_NO_UPDATE", raising=False)
    game.web_mode = True
    assert game.start_update_check() is False


def test_background_check_sets_the_notice_without_installing(monkeypatch):
    monkeypatch.delenv("U_JAGD_NO_UPDATE_CHECK", raising=False)
    monkeypatch.delenv("U_JAGD_NO_UPDATE", raising=False)
    monkeypatch.setattr(update, "fetch_notice", lambda current: _notice())
    game = _game(show_splash=True)
    assert game.start_update_check("browser") is True
    game._update_thread.join(5)
    assert game.update_notice.version == "9.9.9" and game.running
    monkeypatch.setattr(update, "fetch_notice",
                        lambda current: (_ for _ in ()).throw(update.UpdateError("offline")))
    offline = _game(show_splash=True)
    offline.start_update_check("browser")
    offline._update_thread.join(5)
    assert offline.update_notice is None


def _texts(game):
    with layout.capture_text() as texts:
        game.draw()
    return " ".join(item["text"] for item in texts)


def test_splash_and_main_menu_show_version_notes_and_save_warning():
    game = _game(show_splash=True)
    game.update_notice = _notice(save_version=SAVE_VERSION + 1)
    text = _texts(game)
    assert "9.9.9" in text and "lighthouse" in text and "Update now" in text
    assert "will not load" in text
    assert game._update_button is not None
    game.splash_active = False
    game.update_notice = _notice()
    text = _texts(game)
    assert "9.9.9" in text and "will not load" not in text
    assert game._update_button.right < 380  # left of the main-menu panel
    assert game._update_button.bottom <= 560  # above the world and seed lines
    game.update_notice = None
    assert "9.9.9" not in _texts(game)


def test_german_notice_uses_german_notes():
    from src.core.preferences import Preferences
    game = _game(show_splash=True, preferences=Preferences(language="de"))
    game.update_notice = _notice(save_version=SAVE_VERSION + 1)
    text = _texts(game)
    assert "Leuchtturm" in text and "Jetzt updaten" in text and "nicht mehr" in text


def test_windows_downloads_in_the_game_then_swaps_and_quits(monkeypatch, tmp_path):
    exe = tmp_path / "U-Jagd-Windows.exe"
    monkeypatch.setattr(game_update.sys, "executable", str(exe))
    (tmp_path / "U-Jagd-Windows.exe.new").write_bytes(b"old")
    release = update.Release("9.9.9", "https://github.com/x.exe", 3, None, update.RELEASES_PAGE)
    monkeypatch.setattr(update, "check_latest", lambda current: release)
    downloads, installs = [], []

    def download(rel, target, progress=None):
        progress(3, 3)
        downloads.append(target)

    monkeypatch.setattr(update, "download", download)
    monkeypatch.setattr(update, "launch_install",
                        lambda exe_path, target, log=None: installs.append((exe_path, target)))
    monkeypatch.delenv("U_JAGD_NO_UPDATE_CHECK", raising=False)
    monkeypatch.delenv("U_JAGD_NO_UPDATE", raising=False)
    monkeypatch.setattr(update, "fetch_notice", lambda current: None)
    game = _game(show_splash=True)
    game.start_update_check("windows")
    assert not (tmp_path / "U-Jagd-Windows.exe.new").exists()  # stale swap removed
    game._update_thread.join(5)
    game.update_notice = _notice()
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_u, mod=0))
    for _ in range(100):
        if game._update_ready is not None:
            break
        time.sleep(0.02)
    assert downloads == [f"{exe}.new"] and game.update_progress == 100
    assert "100 %" in _texts(game)
    game.update_tick()
    assert installs == [(str(exe), f"{exe}.new")] and not game.running


def test_windows_download_failure_can_be_retried(monkeypatch):
    def fail(current):
        raise update.UpdateError("offline")

    monkeypatch.setattr(update, "check_latest", fail)
    game = _game(show_splash=False)
    game.update_notice = _notice()
    game.update_mode = "windows"
    game.request_update()
    for _ in range(100):
        if game.update_failed:
            break
        time.sleep(0.02)
    assert game.update_failed and game.update_progress is None and game.running


def test_u_on_splash_hands_over_to_the_starter():
    game = _game(show_splash=True)
    game.update_notice = _notice()
    game.update_mode = "starter"
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_u, mod=0))
    assert not game.running and game.update_exit_code == update.UPDATE_EXIT_CODE


def test_u_without_notice_only_leaves_the_splash():
    game = _game(show_splash=True)
    game.splash_started_at -= 1.0
    game.update_mode = "starter"
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_u, mod=0))
    assert game.running and not game.splash_active and game.update_exit_code == 0


def test_uconsole_mode_starts_the_launcher_and_quits(monkeypatch):
    started = []
    monkeypatch.setattr(game_update.subprocess, "Popen",
                        lambda args, **kwargs: started.append((args, kwargs)))
    game = _game(show_splash=False)
    game.update_notice = _notice()
    game.update_mode = "uconsole"
    game.update_args = ("--windowed",)
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_u, mod=0))
    args, kwargs = started[0]
    assert args[1:] == [str(game_update.UPDATER), "install", "--windowed"]
    assert kwargs["close_fds"] and kwargs["start_new_session"]
    assert not game.running and game.update_exit_code == 0


def test_uconsole_mode_reports_a_failed_start(monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("no python3")

    monkeypatch.setattr(game_update.subprocess, "Popen", fail)
    game = _game(show_splash=False)
    game.update_notice = _notice()
    game.update_mode = "uconsole"
    assert game.request_update() is False and game.running and game.update_failed
    assert "try again" in _texts(game)


def test_other_installs_open_the_release_page(monkeypatch):
    opened = []
    monkeypatch.setattr(game_update.webbrowser, "open", opened.append)
    game = _game(show_splash=False)
    game.update_notice = _notice()
    game.update_mode = "browser"
    game.draw()
    center = game._update_button.center
    monkeypatch.setattr(game, "_window_to_canvas", lambda pos: pos)
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=center))
    assert opened == [update.RELEASES_PAGE] and game.running


def test_notice_hidden_under_overlays_and_during_a_mission():
    game = _game(show_splash=False)
    game.update_notice = _notice()
    assert game.update_notice_visible()
    game._open_administration("quit")
    assert not game.update_notice_visible()
    game2 = Game(seed=7, start_menu=False, show_splash=False, audio_enabled=False)
    game2.update_notice = _notice()
    assert not game2.update_notice_visible()


def test_main_returns_the_update_exit_code(monkeypatch):
    import main as entry

    calls = []

    class FakeGame:
        update_exit_code = 0

        def __init__(self, **_kwargs):
            self.commander = type("C", (), {"port": 8765, "status_path": None})()

        def start_update_check(self, mode=None, args=()):
            calls.append((mode, tuple(args)))

        def run(self):
            self.update_exit_code = update.UPDATE_EXIT_CODE

    monkeypatch.setattr(entry, "Game", FakeGame)
    monkeypatch.setattr(entry, "load_preferences", lambda: type(
        "P", (), {"fullscreen": False, "audio": False})())
    assert entry.main(["--windowed", "5"]) == update.UPDATE_EXIT_CODE
    assert calls == [(None, ("--windowed", "5"))]
    assert APP_VERSION
