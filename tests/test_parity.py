"""Web and uConsole show the same operational information."""

from src.commander import projections
from src.core.game import Game
from src.core.station import Station
from src.ui import layout


def test_navigation_projection_carries_the_turn_radius():
    game = Game(seed=9090, start_menu=False, audio_enabled=False)
    game.ship.speed = 12.0
    navigation = projections._own_navigation(game)
    assert "turn_radius_nm" in navigation
    radius = game.ship.turn_radius_nm
    # Straight ahead the radius is infinite, which the projection sends as null.
    assert navigation["turn_radius_nm"] == (radius if radius != float("inf") else None)


def test_ciws_release_is_projected_and_commandable():
    from src.commander.bridge import _opz_set_ciws
    game = Game(seed=9091, start_menu=False, audio_enabled=False)
    assert _opz_set_ciws(game, {"enabled": False}, {}) is True
    assert game.ciws_authorized is False


def test_local_radio_lists_logged_bearings_and_fixes():
    game = Game(seed=9092, start_menu=False, audio_enabled=False)
    game.hfdf_log = [dict(track_id="H-1", label="H-ABC123", bearing=45.0,
                          observer_x=100.0, observer_y=200.0, t=game.sim_t)]
    game.hfdf_fixes = {"H-1": dict(label="H-ABC123", x=110.0, y=190.0,
                                   sigma_nm=2.5, covariance_nm2=(1, 0, 1),
                                   t=game.sim_t)}
    game.station, game.station_page = Station.RADIO, 0
    with layout.capture_text() as text:
        game.draw()
    shown = " ".join(entry["text"] for entry in text)
    assert "H-ABC123" in shown and "045.0" in shown and "2.5" in shown


def test_web_styles_use_tokens_and_the_pygame_theme_covers_chrome():
    import re
    from pathlib import Path
    from src.ui import theme
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from commander_web import client_css_files
    files = client_css_files()
    assert files[0].name == "tokens.css"
    tokens = files[0].read_text(encoding="utf-8")
    # The theme tokens are generated from src/ui/theme.TOKENS; the names the
    # stylesheets use derive from them in one hand-written :root rule, with
    # per-theme overrides for what a plain derivation cannot express.
    begin = "/* BEGIN GENERATED THEME TOKENS (tools/gen_web_schema.py; do not edit by hand) */\n"
    end = "/* END GENERATED THEME TOKENS */\n"
    generated = tokens[tokens.index(begin) + len(begin):tokens.index(end)]
    assert generated == theme.css_tokens()
    rest = tokens[tokens.index(end) + len(end):]
    root = rest[rest.index(":root {"):rest.index("}")]
    for token in ("--aff-unknown", "--aff-friend", "--aff-neutral", "--aff-hostile"):
        assert token + ": var(--t-" in root
    for token in ("--bg-0", "--bg-2", "--bg-3", "--line", "--line-strong", "--text", "--text-dim",
                  "--text-faint", "--live", "--caution", "--alarm", "--info", "--scope", "--shadow"):
        assert f"  {token}: var(--t-" in root, token
    assert set(re.findall(r':root\[data-theme="(\w+)"\] \{', rest)) == {"day", "contrast"}
    # Every colour literal lives in the token file; the rest uses var(--...).
    commander = files[0].parents[1]
    for path in files[1:] + [commander / "admin.css", commander / "manual.css"]:
        assert not re.findall(r"#[0-9a-fA-F]{3,8}\b", path.read_text(encoding="utf-8")), path.name
    for name in ("COLOR_PANEL_BG", "COLOR_FEED_BG", "COLOR_OVERLAY_BG",
                 "COLOR_SELECT_BG", "COLOR_ALARM_BG", "COLOR_TAB_ACTIVE"):
        assert name in theme.CONFIG_COLORS_STANDARD
        assert name in theme.CONFIG_COLORS_HIGH_CONTRAST
