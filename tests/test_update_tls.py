"""The update check over HTTPS in the packaged programs, and how a failed
check shows (1.3.172: the macOS app never offered updates, because its
Python found no root certificates and every request failed verification)."""

import ssl
import time
import urllib.error

import pygame
import pytest

from src.core import https
from src.core.game import Game
from src.core.preferences import Preferences
from src.launcher import update
from src.ui import layout


@pytest.fixture
def fresh_context(monkeypatch):
    monkeypatch.setattr(https, "_context", None)
    yield
    https._context = None


def test_extra_certificates_verify_when_the_default_store_is_empty(monkeypatch, fresh_context):
    certifi = pytest.importorskip("certifi")
    # As on a player's Mac: OpenSSL's default certificate paths lead nowhere.
    monkeypatch.setenv("SSL_CERT_FILE", "/nonexistent/cert.pem")
    monkeypatch.setenv("SSL_CERT_DIR", "/nonexistent")
    assert ssl.create_default_context().cert_store_stats()["x509_ca"] == 0
    monkeypatch.setattr(https, "ca_files", lambda: (certifi.where(),))
    context = https.ssl_context()
    assert context.cert_store_stats()["x509_ca"] > 50
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    assert https.ssl_context() is context  # built once


def test_a_broken_certificate_file_keeps_the_default_store(monkeypatch, tmp_path, fresh_context):
    broken = tmp_path / "cert.pem"
    broken.write_text("not a certificate")
    monkeypatch.setattr(https, "ca_files", lambda: (str(broken),))
    assert https.ssl_context().verify_mode == ssl.CERT_REQUIRED


def test_ca_files_lists_only_existing_files(monkeypatch, tmp_path):
    existing = tmp_path / "ca.pem"
    existing.write_text("x")
    monkeypatch.setattr(https, "certifi_file", lambda: None)
    monkeypatch.setattr(https, "_EXTRA_CA_FILES", (str(existing), str(tmp_path / "gone.pem")))
    assert https.ca_files() == (str(existing),)


def test_update_requests_use_the_verifying_context(monkeypatch, fresh_context):
    seen = {}

    def fake(request, timeout, context):
        seen.update(timeout=timeout, context=context)
        raise urllib.error.URLError(OSError("down"))

    monkeypatch.setattr(https.urllib.request, "urlopen", fake)
    with pytest.raises(update.UpdateError):
        update.fetch_notice("1.3.100")
    assert seen["context"] is https.ssl_context()


def _cert_error():
    return ssl.SSLCertVerificationError(
        1, "[SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate")


def test_failure_reasons():
    def wrapped(exc):
        try:
            try:
                raise exc
            except Exception as inner:
                raise update.UpdateError(str(inner)) from inner
        except update.UpdateError as outer:
            return update.failure_reason(outer)

    assert wrapped(urllib.error.URLError(_cert_error())) == "tls"
    assert wrapped(_cert_error()) == "tls"
    assert wrapped(urllib.error.URLError(OSError("Name or service not known"))) == "offline"
    assert wrapped(TimeoutError("timed out")) == "offline"
    assert wrapped(urllib.error.HTTPError("u", 403, "rate limited", {}, None)) == "http"
    assert wrapped(ValueError("bad json")) == "other"
    assert set(update.FAILURE_REASONS) == {"tls", "offline", "http", "other"}


def _game(**kwargs):
    return Game(seed=7, start_menu=True, audio_enabled=False, **kwargs)


def _texts(game):
    with layout.capture_text() as texts:
        game.draw()
    return " ".join(item["text"] for item in texts)


def _check(game, monkeypatch, error):
    monkeypatch.delenv("U_JAGD_NO_UPDATE_CHECK", raising=False)
    monkeypatch.delenv("U_JAGD_NO_UPDATE", raising=False)

    def fail(current):
        try:
            raise error
        except Exception as exc:
            raise update.UpdateError(str(exc)) from exc

    monkeypatch.setattr(update, "fetch_notice", fail)
    assert game.start_update_check("browser")
    game._update_thread.join(5)


@pytest.mark.parametrize("language,title,reason", [
    ("en", "Update check failed", "certificate"),
    ("de", "Update-Prüfung fehlgeschlagen", "Zertifikat"),
])
def test_failed_check_shows_why_on_splash_and_menu(monkeypatch, language, title, reason):
    game = _game(show_splash=True, preferences=Preferences(language=language))
    _check(game, monkeypatch, urllib.error.URLError(_cert_error()))
    assert game.update_check_error == "tls" and game.update_notice is None
    with layout.capture_truncations() as cut:
        text = _texts(game)
    assert title in text and reason in text
    assert not cut
    splash_button = game._update_button
    assert splash_button is not None
    game.splash_active = False
    text = _texts(game)
    assert title in text
    assert game._update_button.right < 380 and game._update_button.bottom <= 560


def test_u_checks_again_and_shows_the_notice(monkeypatch):
    game = _game(show_splash=True)
    _check(game, monkeypatch, urllib.error.URLError(OSError("offline")))
    assert game.update_check_error == "offline"
    notice = update.Notice("9.9.9", update.RELEASES_PAGE, {"en": "New."}, None)
    monkeypatch.setattr(update, "fetch_notice", lambda current: notice)
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_u, mod=0))
    for _ in range(250):
        if game.update_notice is not None:
            break
        time.sleep(0.02)
    assert game.update_notice is notice and game.update_check_error is None
    assert "9.9.9" in _texts(game) and game.running


def test_no_failure_panel_without_a_failed_check():
    game = _game(show_splash=True)
    assert not game.update_error_visible()
    assert "Update check failed" not in _texts(game)
