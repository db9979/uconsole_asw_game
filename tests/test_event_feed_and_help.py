"""Regression coverage for persistent notices and station command help."""

from src.core import config
from src.core.game import Game
from src.core.help import get_help
from src.core.i18n import localize, message
from src.core.station import Station


def _help_keys(station):
    _intro, controls, _notes, _tactics = get_help(station, lambda key: key)
    return {key: action for key, action in controls}


def test_every_emitted_feed_category_has_a_visible_tag():
    assert "opz" in config.FEED_CATEGORIES
    assert all(tag != "?" for _color, tag in config.FEED_CATEGORIES.values())


def test_mission_result_is_retained_in_event_feed():
    game = Game(seed=9191, start_menu=False)
    game.feed.clear()

    game._end_mission(False, message("end.reason.time_limit"))
    assert localize(game.feed.entries[-1].text, game.tr) == game.tr(
        "runtime.mission.lost")
    assert game.feed.entries[-1].category == "mission"


def test_every_radio_message_is_mirrored_to_the_event_feed():
    game = Game(seed=9292, start_menu=False)
    game.feed.clear()
    game.messages.clear()
    notice = message("runtime.hq.threat_unknown")

    game.hq_msg(notice)

    assert game.messages[-1][1] is notice
    assert game.feed.entries[-1].text is notice
    assert game.feed.entries[-1].category == "funk"


def test_context_help_covers_new_station_commands():
    sonar = _help_keys(Station.SONAR)
    assert sonar["Shift+C"] == "help.control.display_palette"
    assert sonar["Ctrl+I / Ctrl+O"] == "help.control.display_black"

    weapons = _help_keys(Station.WEAPONS)
    assert weapons["F"] == "help.control.flak_release"

    opz = _help_keys(Station.OPZ)
    assert opz["Shift+F"] == "help.control.opz_filter"
    assert opz["J"] == "help.control.opz_track_id"
    assert opz["I"] == "help.control.ciws_release"
    assert opz["Enter"] == "help.control.confirm_live_engage"

    helicopter = _help_keys(Station.HELICOPTER)
    assert helicopter["G / Shift+G"] == "help.control.helo_contact_release"

    eloka = _help_keys(Station.ELOKA)
    for key in ("F / Shift+F / B", "J", "Shift+J", "A", "M"):
        assert key in eloka


def test_flash_banner_follows_game_language(monkeypatch):
    from src.core.game import Game
    from src.core.i18n import localize, message
    from src.ui import layout

    game = Game(seed=5, start_menu=False, audio_enabled=False, language="de")
    shown = []
    original = layout.blit_block
    monkeypatch.setattr(layout, "blit_block", lambda surface, text, *args, **kwargs: (
        shown.append(localize(text)), original(surface, text, *args, **kwargs))[1])
    game.flash(message("runtime.contacts.none"), 5.0)
    game.draw()
    assert "Keine Kontakte" in shown and "No contacts" not in shown
