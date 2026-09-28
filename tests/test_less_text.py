"""uConsole screens carry less text: short bars, fresh-only alarms, four keys."""

import math
import sys
from pathlib import Path

import pygame

from src.core import uboot_local
from src.core.i18n import localize
from src.core.station import Station
from src.ui import map_view, uboot_view

sys.path.insert(0, str(Path(__file__).parent))
from test_opfor_sub import _crewed  # noqa: E402


def _drawn_texts(monkeypatch, module):
    texts = []
    original = module.layout.blit_line

    def record(surface, text, *args, **kwargs):
        texts.append(str(localize(text)))
        return original(surface, text, *args, **kwargs)

    monkeypatch.setattr(module.layout, "blit_line", record)
    return texts


def test_frigate_top_bar_names_station_mission_clock_speed_course(monkeypatch):
    game, _server, _bridge = _crewed(seed=31)
    game.station = Station.SONAR
    texts = _drawn_texts(monkeypatch, map_view)
    game.draw_top_bar()
    parts = texts[0].split(" · ")
    assert parts[0] == "SONAR" and parts[2] == game.world.format_time()
    assert parts[1] == game.top_bar_scenario()
    assert parts[3] == f"{game.ship.speed:.1f} kn"
    assert parts[4] == f"{game.ship.course % 360:03.0f}°"


def test_chart_header_shows_only_the_scale(monkeypatch):
    game, _server, _bridge = _crewed(seed=31)
    game.station = Station.BRIDGE
    texts = _drawn_texts(monkeypatch, map_view)
    game.draw()
    header = [text for text in texts if text.split()[1:2] == ["NM"]]
    assert header and all("|" not in text and "coastal" not in text for text in header)


def test_stale_ping_leaves_only_the_top_bar_marker():
    game, _server, _bridge = _crewed(seed=31)
    boat = game.opfor
    game.local_side = "uboot"
    boat.sub.crew.ping_bearing = 259.0
    boat.sub.memory["last_ping_age"] = 5.0
    rows = uboot_view.threat_rows(game, boat)
    assert [fresh for text, _level, fresh in rows
            if text["__u_jagd_i18n__"] == "uboot.threat.ping_bearing"] == [True]
    assert uboot_view._draw_threat_bar(game.screen, game, boat, 0, 0, 400) > 0
    boat.sub.memory["last_ping_age"] = uboot_view.THREAT_FRESH_S + 10.0
    rows = uboot_view.threat_rows(game, boat)
    assert rows and not any(fresh for _text, _level, fresh in rows)
    # Still listed on the threat page, but no box on every station.
    assert uboot_view.threats(game, boat)
    assert uboot_view._draw_threat_bar(game.screen, game, boat, 0, 0, 400) == 0
    boat.sub.memory["last_ping_age"] = math.inf
    assert uboot_view._draw_threat_bar(game.screen, game, boat, 0, 0, 400) == 0


def test_submarine_footers_have_at_most_four_keys():
    assert max(len(specs) for specs in uboot_view._FOOTERS.values()) <= 4


def test_tube_line_lists_only_tubes_that_are_not_ready():
    game, _server, _bridge = _crewed(seed=31)
    sub = game.opfor.sub
    assert uboot_view.tube_line(sub, busy_only=True) is None
    game.local_side = "uboot"
    uboot_local.set_local_station(game, "uboot_weapons")
    pygame.display.set_mode((1280, 720))
    uboot_view.draw(game)
