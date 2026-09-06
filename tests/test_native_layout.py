"""Semantic workstation layout checks at the native 1280x720 canvas."""

from types import SimpleNamespace as NS
import random

import pygame

from src.core import config
from src.core.i18n import localize
from src.ship.damage import DamageModel
from src.ui import layout, stations_view, weapons_view


def test_weapons_panel_has_fixed_solution_readiness_inventory_and_active_sections(monkeypatch):
    pygame.font.init()
    monkeypatch.setattr(config, "STATION_RECT", (640, 30, 640, 510))
    titles = []
    original = layout.box

    def record(screen, rect, title="", **kwargs):
        titles.append((title, pygame.Rect(rect)))
        return original(screen, rect, title, **kwargs)

    monkeypatch.setattr(layout, "box", record)
    game = NS(
        screen=pygame.Surface((1280, 720)), target=None,
        torpedo_readiness=lambda: ("ROHRE BEREIT", config.COLOR_OK),
        torpedo_count=4, torpedo_total=4, torpedo_depth=50.0,
        torpedoes=[], roe="FREIGABE",
        helo=NS(torps=2, buoys_left=6, airborne=False),
    )

    weapons_view.draw_weapons_panel(game)

    names = {title for title, _ in titles}
    assert {"FEUERLEITLOESUNG", "EINSATZSTUFEN", "BESTAND",
            "AKTIVE WAFFEN", "EINSATZ"} <= names
    assert all(rect.left >= 640 and rect.right <= 1280 for _, rect in titles)
    assert all(rect.top >= 30 and rect.bottom <= 540 for _, rect in titles)


def test_weapons_panel_shows_tma_evidence_and_engagement_stages(monkeypatch):
    pygame.font.init()
    monkeypatch.setattr(config, "STATION_RECT", (640, 30, 640, 510))
    lines = []
    original_line = layout.blit_line
    original_status = layout.status_line

    def record_line(screen, text, *args, **kwargs):
        lines.append(localize(text))
        return original_line(screen, text, *args, **kwargs)

    def record_status(screen, x, y, w, label, value, *args, **kwargs):
        lines.append(f"{localize(label)} {localize(value)}")
        return original_status(screen, x, y, w, label, value, *args, **kwargs)

    monkeypatch.setattr(layout, "blit_line", record_line)
    monkeypatch.setattr(layout, "status_line", record_status)
    contact = NS(id=3, display_label="U-Boot", bearing=80.0, range_est=6.0,
                 confidence=.8, range_source="tma", last_seen=90.0,
                 range_sigma_nm=1.2, depth_est=None, player_class="U_BOOT",
                 tma_course=145.0, tma_speed=7.0, tma_quality=.72)
    game = NS(
        screen=pygame.Surface((1280, 720)), target=contact, sim_t=100.0,
        torpedo_readiness=lambda: ("FEUER FREI", config.COLOR_OK),
        torpedo_count=4, torpedo_total=4, torpedo_depth=50.0,
        torpedoes=[], roe="STD",
        helo=NS(torps=2, buoys_left=6, airborne=False),
    )
    weapons_view.draw_weapons_panel(game)
    assert any("TMA COURSE" in line and "SPEED" in line and "Q 72%" in line
                for line in lines)
    assert "Target ASSIGNED" in lines
    assert "Solution VALID" in lines
    assert "Authorization AUTHORIZED" in lines
    assert "Weapon READY" in lines


def test_engine_native_layout_uses_two_equal_work_columns(monkeypatch):
    pygame.font.init()
    monkeypatch.setattr(config, "STATION_RECT", (0, 30, 1280, 510))
    boxes = []
    original = layout.box

    def record(screen, rect, title="", **kwargs):
        boxes.append((title, pygame.Rect(rect)))
        return original(screen, rect, title, **kwargs)

    monkeypatch.setattr(layout, "box", record)
    ship = NS(
        telegraph="HALF", order_idx=2, speed=10.0, target_speed=10.0,
        cavitating=False, roll=1.0, pitch=.5, quiet_mode=False,
        rpm=lambda: 120.0, noise_level=lambda: .3,
        passive_sonar_range_nm=lambda *args: 15.0,
    )
    damage = DamageModel(random.Random(1))
    game = NS(screen=pygame.Surface((1280, 720)), ship=ship, damage=damage,
              world=NS(sea_state=2), sonar_mode="BOW")

    stations_view.draw_engine_view(game)

    columns = {title: rect for title, rect in boxes}
    assert columns["FAHRTBEFEHL"].right < columns["ANTRIEB / AKUSTIK"].left
    assert abs(columns["FAHRTBEFEHL"].w - columns["ANTRIEB / AKUSTIK"].w) <= 1


def test_damage_native_layout_has_selected_detail_panel(monkeypatch):
    pygame.font.init()
    monkeypatch.setattr(config, "STATION_RECT", (0, 30, 1280, 510))
    titles = []
    original = layout.box

    def record(screen, rect, title="", **kwargs):
        titles.append(title)
        return original(screen, rect, title, **kwargs)

    monkeypatch.setattr(layout, "box", record)
    damage = DamageModel(random.Random(2))
    damage.compartments["sonar"].state = "FLUTEND"
    damage.compartments["sonar"].flood = 42.0
    cursor = list(damage.compartments).index("sonar")
    game = NS(screen=pygame.Surface((1280, 720)), damage=damage,
              dmg_cursor=cursor, dmg_team=1)

    stations_view.draw_damage_view(game)

    assert "AUSWAHL / MASSNAHMEN" in titles


def test_helicopter_regions_are_shared_bounded_and_adapt_to_large_text(monkeypatch):
    pygame.font.init()
    monkeypatch.setattr(config, "STATION_RECT", (640, 30, 640, 510))
    normal_game = NS(preferences=NS(large_text=False))
    large_game = NS(preferences=NS(large_text=True))
    normal = stations_view.helicopter_regions(normal_game)
    large = stations_view.helicopter_regions(large_game)
    station = pygame.Rect(config.STATION_RECT)

    for regions in (normal, large):
        assert all(station.contains(regions[name])
                   for name in ("status", "resources", "rules"))
        assert regions["status"].bottom < regions["resources"].top
        assert regions["resources"].bottom < regions["rules"].top
        assert regions["rules"].h >= 100
    assert large["status"].h > normal["status"].h
    layout.configure_for(large_text=False)


def test_large_text_helicopter_resource_lines_have_full_text_bounds(monkeypatch):
    pygame.font.init()
    monkeypatch.setattr(config, "STATION_RECT", (640, 30, 640, 510))
    game = NS(
        screen=pygame.Surface((1280, 720)), preferences=NS(large_text=True),
        helo=NS(state="HANGAR", airborne=False, fuel_s=1800.0, x=0.0, y=0.0,
                course=0.0, torps=2, buoys_left=6),
        ship=NS(x=0.0, y=0.0, course=0.0), buoys=[],
        _helo_waypoint_polar=lambda: (0.0, 10.0),
    )
    calls = []
    original = layout.blit_line

    def record(screen, text, rect, color, size=14, align="left"):
        if text in {"LUFTTORPEDOS", "SONARBOJEN BEREIT", "SONARBOJEN AKTIV", "DATALINK",
                    "2", "6", "0", "STANDBY"}:
            calls.append((text, pygame.Rect(rect), size))
        return original(screen, text, rect, color, size=size, align=align)

    monkeypatch.setattr(layout, "blit_line", record)
    stations_view.draw_helicopter_view(game)
    assert len(calls) == 8
    for _, rect, size in calls:
        assert rect.h >= layout.font(size).get_linesize()
    for label, value in zip(calls[::2], calls[1::2]):
        assert label[1].bottom <= value[1].top
    layout.configure_for(large_text=False)
