import json

from src.core.preferences import (Preferences, default_preferences_path,
                                  load_preferences, save_preferences)


def test_required_default_preferences_path(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))   # Path.home() on Windows
    # conftest isolates the session; the wrapped function is the real one.
    real = getattr(default_preferences_path, "__wrapped__", default_preferences_path)
    assert real() == tmp_path / ".u-jagd" / "settings.json"


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
    # Only an absent file is a first launch that shows the welcome page.
    # A new player also starts on the short missions.
    assert load_preferences(tmp_path / "missing.json") == Preferences(
        language="de", onboarded=False, mission_length="short")

    path = tmp_path / "preferences.json"
    path.write_text("not json", encoding="utf-8")
    assert load_preferences(path) == expected


def test_onboarded_is_strict_and_legacy_files_count_as_onboarded(tmp_path):
    path = tmp_path / "preferences.json"
    path.write_text(json.dumps({"language": "de", "audio": False}),
                    encoding="utf-8")
    assert load_preferences(path).onboarded is True
    for bad in ("no", 0, None, [], {}):
        path.write_text(json.dumps({"onboarded": bad}), encoding="utf-8")
        assert load_preferences(path).onboarded is True
    path.write_text(json.dumps({"onboarded": False}), encoding="utf-8")
    assert load_preferences(path).onboarded is False
    expected = Preferences(onboarded=False)
    save_preferences(expected, path)
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


def test_frame_rate_round_trip_and_invalid_values(tmp_path):
    path = tmp_path / "preferences.json"
    assert Preferences().frame_rate == 30
    save_preferences(Preferences(language="en", frame_rate=60), path)
    assert load_preferences(path).frame_rate == 60
    for bad in (45, 60.0, "60", True, None, -30):
        path.write_text(json.dumps({"language": "en", "frame_rate": bad}),
                        encoding="utf-8")
        assert load_preferences(path).frame_rate == 30


def test_windows_default_graphics_keeps_the_line_switch_in_step(monkeypatch):
    from src.core import preferences as preferences_module
    monkeypatch.setattr(preferences_module, "_default_graphics", lambda: "full")
    fresh = preferences_module.Preferences()
    assert fresh.graphics == "full" and fresh.aa_lines is True


def test_mission_length_and_lessons_done_round_trip_and_are_strict(tmp_path):
    path = tmp_path / "preferences.json"
    expected = Preferences(mission_length="short", lessons_done=("sonar", "air"))
    save_preferences(expected, path)
    assert load_preferences(path) == expected
    path.write_text(json.dumps({"mission_length": "endless",
                                "lessons_done": ["sonar", "a/b", 3, "sonar", "x" * 40]}),
                    encoding="utf-8")
    loaded = load_preferences(path)
    assert loaded.mission_length == Preferences().mission_length == "normal"
    assert loaded.lessons_done == ("sonar",)
    path.write_text(json.dumps({"lessons_done": "sonar"}), encoding="utf-8")
    assert load_preferences(path).lessons_done == ()
