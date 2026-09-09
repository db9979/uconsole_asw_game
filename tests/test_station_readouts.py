"""Operator-facing station regressions using public observations only."""

from dataclasses import replace

import pygame
import pytest

from src.core import config
from src.core.game import Game
from src.core.i18n import Translator
from src.core.station import Station
from src.sonar.sonar import Contact
from src.ui import layout, nato_symbols, stations_view, weapons_view


@pytest.fixture
def game():
    return Game(seed=811, start_menu=False)


@pytest.mark.parametrize("language", ["en", "de"])
@pytest.mark.parametrize("large", [False, True])
def test_full_weapon_solution_and_readiness_fit(game, monkeypatch, language, large):
    monkeypatch.setattr(config, "STATION_RECT", (640, 30, 640, 510))
    game.preferences = replace(game.preferences, large_text=large)
    game.sim_t = 100.0
    c = Contact(7, 77, "ping", "sub")
    c.update_ping(90.0, 6.0, 65.0, .9, 98.0)
    c.observed_x, c.observed_y = game.ship.x + 6.0, game.ship.y
    c.range_source = "buoy"
    c.range_seen = 95.0
    c.range_sigma_nm = .25
    c.tma_course, c.tma_speed, c.tma_quality = 145.0, 7.0, .72
    c.player_class = "U_BOOT"
    game.target = c
    translator = Translator(language)
    with layout.capture_text() as text:
        weapons_view.draw_weapons_panel(game, tr=translator.t)
    regions = weapons_view.weapons_regions(game)
    solution = [item for item in text if regions["solution"].contains(item["bounds"])]
    rendered = "\n".join(item["text"] for item in solution)
    assert "6.0 NM" in rendered
    assert translator.t("map.source.buoy") in rendered
    assert "PING" not in rendered
    assert "145.0" in rendered and "7.0 kn" in rendered and "72%" in rendered
    assert "65" in rendered and str(int(game.torpedo_depth)) in rendered
    assert "TRUE/N 090" in rendered and "REL" in rendered
    assert translator.t("weapons.readiness.clear") in rendered
    assert "..." not in rendered
    assert all(item["bounds"].contains(item["rect"]) for item in solution)
    assert all(regions["solution"].contains(item["rect"]) for item in solution)
    assert all(item["bounds"].contains(item["rect"]) for item in text), [
        item for item in text if not item["bounds"].contains(item["rect"])]


def test_weapon_solution_stage_uses_same_freshness_as_launch(game, monkeypatch):
    monkeypatch.setattr(config, "STATION_RECT", (640, 30, 640, 510))
    game.sim_t = config.SONAR_CONTACT_LOST_S + 10
    c = Contact(7, 77, "ping", "sub")
    c.update_ping(90.0, 6.0, 65.0, .9, 0.0)
    c.player_class = "U_BOOT"
    c.last_seen = game.sim_t
    game.target = c
    assert not game._contact_range_fresh(c)
    with layout.capture_text() as text:
        weapons_view.draw_weapons_panel(game, tr=Translator("en").t)
    rendered = "\n".join(item["text"] for item in text)
    assert "PENDING" in rendered and "VALID" not in rendered
    assert "BLOCKED: NO RANGE" in rendered

    game.roe = "FREE"
    with layout.capture_text() as text:
        weapons_view.draw_weapons_panel(game, tr=Translator("en").t)
    rendered = "\n".join(item["text"] for item in text)
    assert "MANUAL" in rendered and "VALID" not in rendered
    assert "CLEAR TO FIRE" in rendered


def test_active_weapon_uses_profile_runtime_range(game, monkeypatch):
    monkeypatch.setattr(config, "STATION_RECT", (640, 30, 640, 510))
    game.torpedoes = [type("DisplayedWeapon", (), {
        "idx": 4, "range_nm": 3.0, "travel": 1.0,
        "speed_nm_per_s": 1.0,
        "seeker_acquired": False, "guidance_distance_nm": lambda self: 4.0,
    })()]
    with layout.capture_text() as text:
        weapons_view.draw_weapons_panel(game, tr=Translator("en").t)
    rendered = "\n".join(item["text"] for item in text)
    assert "REM 2.0NM" in rendered


@pytest.mark.parametrize("language", ["en", "de"])
def test_long_weapon_interlock_reason_is_fully_visible(game, monkeypatch, language):
    monkeypatch.setattr(config, "STATION_RECT", (640, 30, 640, 510))
    game.preferences = replace(game.preferences, large_text=True)
    c = Contact(7, 77, "ping", "sub")
    c.update_ping(90.0, 6.0, 65.0, .9, game.sim_t)
    game.target = c
    translator = Translator(language)
    with layout.capture_text() as text:
        weapons_view.draw_weapons_panel(game, tr=translator.t)
    rendered = " ".join(item["text"] for item in text)
    assert translator.t("weapons.readiness.classification") in rendered
    assert all(item["bounds"].contains(item["rect"]) for item in text)


@pytest.mark.parametrize("state", ["HANGAR", "VERLOREN"])
def test_non_airborne_helo_has_no_fictitious_navigation_or_rtb(game, monkeypatch, state):
    monkeypatch.setattr(config, "STATION_RECT", (640, 30, 640, 510))
    game.helo.state = state
    game.helo.fuel_s = 0
    game.helo.x, game.helo.y = game.ship.x + 900, game.ship.y - 700
    with layout.capture_text() as text:
        stations_view.draw_helicopter_view(game, tr=Translator("en").t)
    rendered = "\n".join(item["text"] for item in text)
    assert "0.0 NM" not in rendered and "TRUE/N 0" not in rendered
    assert "RTB margin: --" in rendered
    assert "RTB margin: -" not in rendered.replace("RTB margin: --", "")
    game.station = Station.HELICOPTER
    game.tr = Translator("en").t
    payload = stations_view.station_hit_target(
        game, stations_view.helicopter_regions(game)["status"].center)
    assert not any("bearing" in line.lower() for line in payload["lines"])
    with layout.capture_text() as text:
        weapons_view.draw_weapons_panel(game, tr=Translator("en").t)
    assert Translator("en").t("enum.helo." + state) in "\n".join(i["text"] for i in text)


def test_bridge_bearing_only_asm_is_still_a_threat(game, monkeypatch):
    monkeypatch.setattr(config, "STATION_RECT", (640, 30, 640, 510))
    game.air_picture._tracks.clear()
    game.air_picture.observe(track_id="M-1", kind="ASM", target_id=1,
        source="HOJ", bearing=120.0, range_nm=None,
        observer_x=game.ship.x, observer_y=game.ship.y, course=None,
        quality=.5, now=game.sim_t, label="M-1")
    with layout.capture_text() as text:
        stations_view.draw_bridge_view(game, tr=Translator("en").t)
    rendered = "\n".join(item["text"] for item in text)
    assert "ASM" in rendered and "120" in rendered
    assert Translator("en").t("panel.no_threat") not in rendered


def test_opz_keeps_selected_asm_visible_after_first_three(game, monkeypatch):
    monkeypatch.setattr(config, "STATION_RECT", (0, 30, 1280, 510))
    game.air_picture._tracks.clear()
    for i in range(6):
        game.air_picture.observe(track_id=f"M-{i}", kind="ASM", target_id=i,
            source="RADAR", bearing=90.0, range_nm=5.0,
            observer_x=game.ship.x, observer_y=game.ship.y, course=270.0,
            quality=.8, now=game.sim_t, label=f"MISSILE-{i}")
    game.asm_sel = 5
    selected = game.asm_tracks()[5]
    with layout.capture_text() as text:
        stations_view.draw_opz_view(game, tr=Translator("en").t)
    assert any(">" in item["text"] and selected.label in item["text"] for item in text)


def test_unknown_domain_has_no_surface_glyph():
    assert nato_symbols.domain_for_kind("UNKNOWN") == "UNKNOWN"
    assert nato_symbols.domain_for_kind("AIS") == "SURFACE"
    unknown = pygame.Surface((40, 40))
    surface = pygame.Surface((40, 40))
    nato_symbols.draw_symbol(unknown, (20, 20), "UNKNOWN", "UNKNOWN")
    nato_symbols.draw_symbol(surface, (20, 20), "UNKNOWN", "SURFACE")
    assert pygame.image.tobytes(unknown, "RGB") != pygame.image.tobytes(surface, "RGB")


def test_engine_does_not_promise_unavailable_tas_advantage(game, monkeypatch):
    monkeypatch.setattr(config, "STATION_RECT", (0, 30, 1280, 510))
    game.sonar_mode = "TOWED"
    assert not game.sonar._tow_available()
    with layout.capture_text() as text:
        stations_view.draw_engine_view(game, tr=Translator("en").t)
    assert "TAS unavailable" in "\n".join(item["text"] for item in text)
