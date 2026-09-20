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
                           audio=False, large_text=True, tooltips=False)
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
        "audio": False, "large_text": 1, "tooltips": "yes",
    }), encoding="utf-8")
    assert load_preferences(path) == Preferences(
        language="en", fullscreen=True, audio=False, large_text=False,
        tooltips=True)


def test_legacy_preferences_default_tooltips_on(tmp_path):
    path = tmp_path / "preferences.json"
    path.write_text(json.dumps({"language": "de", "audio": False}),
                    encoding="utf-8")
    assert load_preferences(path).tooltips is True


def test_legacy_preferences_default_night_mode_off(tmp_path):
    path = tmp_path / "preferences.json"
    path.write_text(json.dumps({"language": "de", "audio": False}),
                    encoding="utf-8")
    assert load_preferences(path).night_mode is False


def test_night_mode_round_trips(tmp_path):
    path = tmp_path / "preferences.json"
    expected = Preferences(night_mode=True)
    assert save_preferences(expected, path) == path
    assert load_preferences(path) == expected


def test_legacy_preferences_default_high_contrast_off(tmp_path):
    path = tmp_path / "preferences.json"
    path.write_text(json.dumps({"language": "de", "audio": False}),
                    encoding="utf-8")
    assert load_preferences(path).high_contrast is False


def test_high_contrast_round_trips(tmp_path):
    path = tmp_path / "preferences.json"
    expected = Preferences(high_contrast=True)
    assert save_preferences(expected, path) == path
    assert load_preferences(path) == expected


def test_legacy_preferences_default_live_traffic_off(tmp_path):
    path = tmp_path / "preferences.json"
    path.write_text(json.dumps({"language": "de", "audio": False}),
                    encoding="utf-8")
    loaded = load_preferences(path)
    assert loaded.live_ais_enabled is False
    assert loaded.live_adsb_enabled is False
    assert loaded.aisstream_api_key == ""
    assert loaded.opensky_credentials == ""


def test_live_traffic_preferences_round_trip(tmp_path):
    path = tmp_path / "preferences.json"
    expected = Preferences(live_ais_enabled=True, live_adsb_enabled=True,
                           aisstream_api_key="abc123",
                           opensky_credentials="id:secret")
    assert save_preferences(expected, path) == path
    assert load_preferences(path) == expected


def test_invalid_live_traffic_fields_fall_back_to_defaults(tmp_path):
    path = tmp_path / "preferences.json"
    path.write_text(json.dumps({
        "live_ais_enabled": "yes", "live_adsb_enabled": 1,
        "aisstream_api_key": 12345, "opensky_credentials": None,
    }), encoding="utf-8")
    loaded = load_preferences(path)
    assert loaded.live_ais_enabled is False
    assert loaded.live_adsb_enabled is False
    assert loaded.aisstream_api_key == ""
    assert loaded.opensky_credentials == ""


def test_credential_fields_are_length_limited(tmp_path):
    path = tmp_path / "preferences.json"
    path.write_text(json.dumps({"aisstream_api_key": "x" * 500}),
                    encoding="utf-8")
    assert len(load_preferences(path).aisstream_api_key) == 256
