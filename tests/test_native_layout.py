"""Semantic workstation layout checks at the native 1280x720 canvas."""

from types import SimpleNamespace as NS
import random

import pygame

from src.core import config
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
        lines.append(text)
        return original_line(screen, text, *args, **kwargs)

    def record_status(screen, x, y, w, label, value, *args, **kwargs):
        lines.append(f"{label} {value}")
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
    assert any("TMA KURS" in line and "FAHRT" in line and "Q 72%" in line
               for line in lines)
    assert "ZIEL ZUGEWIESEN" in lines
    assert "LOESUNG GUELTIG" in lines
    assert "FREIGABE AUTORISIERT" in lines
    assert "WAFFE BEREIT" in lines


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
