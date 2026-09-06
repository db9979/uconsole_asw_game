import json

from src.core.preferences import (Preferences, default_preferences_path,
                                  load_preferences, save_preferences)


def test_required_default_preferences_path(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert default_preferences_path() == tmp_path / ".u-jagd" / "settings.json"


def set_locale(monkeypatch, value):
    for name in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LANG", value)


def test_preferences_round_trip_at_configurable_path(tmp_path):
    path = tmp_path / "nested" / "preferences.json"
    expected = Preferences(language="de", fullscreen=False,
                           audio=False, large_text=True)
    assert save_preferences(expected, path) == path
    assert load_preferences(path) == expected
    assert not list(path.parent.glob("*.tmp"))


def test_missing_and_corrupt_preferences_use_defaults(tmp_path, monkeypatch):
    set_locale(monkeypatch, "de_DE.UTF-8")
    expected = Preferences(language="de")
    assert load_preferences(tmp_path / "missing.json") == expected

    path = tmp_path / "preferences.json"
    path.write_text("not json", encoding="utf-8")
    assert load_preferences(path) == expected


def test_invalid_fields_are_individually_replaced_by_defaults(tmp_path,
                                                               monkeypatch):
    set_locale(monkeypatch, "en_US.UTF-8")
    path = tmp_path / "preferences.json"
    path.write_text(json.dumps({
        "language": "fr", "fullscreen": "yes",
        "audio": False, "large_text": 1,
    }), encoding="utf-8")
    assert load_preferences(path) == Preferences(
        language="en", fullscreen=True, audio=False, large_text=False)
