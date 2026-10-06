"""Chart labels never cover each other or run off the chart.

A crowded picture like the one reported from the weapons station: two
aircraft with speed vectors right beside the frigate, the assigned target
on a bearing only, a second contact with a TMA fix, the scale line in the
corner and the grid numbers along the edges. Every text drawn on the
frigate's chart (Bridge, Weapons, Helicopter) and on the crewed submarine's
chart is traced with its glyph box; no two may overlap and none may leave
the chart, in English and German (frigate also with large text).
"""

from __future__ import annotations

import itertools

import pygame
import pytest

from src.core import config
from src.core.game import Game
from src.core.preferences import Preferences
from src.core import uboot_local
from src.core.station import Station
from src.sonar.sonar import Contact
from src.ui import layout, map_view


def _game(language: str, large: bool = False) -> Game:
    prefs = Preferences(language=language, fullscreen=False, audio=False,
                        large_text=large, tooltips=False)
    game = Game(seed=1234, start_menu=False, show_splash=False,
                audio_enabled=False, preferences=prefs)
    game.msg_until = 0.0
    return game


def _crowd(game: Game, selected_fix: bool) -> None:
    ship = game.ship
    # Two aircraft passing right over the frigate (one leaving the chart's
    # left edge) and a surface radar track: speed labels near other labels.
    tracks = [
        dict(kind="FLG", track_id="T-A1", target_id=1, source="RADAR",
             x=ship.x - .35, y=ship.y - .25, course=300.0, speed_kn=350.0,
             label="1F05A1", quality=1.0),
        dict(kind="FLG", track_id="T-A2", target_id=2, source="RADAR",
             x=ship.x - .30, y=ship.y - .20, course=300.0, speed_kn=330.0,
             label="E1BF75", quality=1.0),
        dict(kind="FLG", track_id="T-A3", target_id=3, source="RADAR",
             x=ship.x - 1.15, y=ship.y - .55, course=280.0, speed_kn=30.0,
             label="77C0DE", quality=1.0),
        dict(kind="SURFACE", track_id="T-S1", target_id=4, source="RADAR",
             x=ship.x + .2, y=ship.y + .1, course=90.0, speed_kn=14.0,
             label="9A2B44", quality=1.0),
    ]
    game.radar_tracks = lambda: [dict(track) for track in tracks]
    target = Contact(2, 900, "passiv", "sub")
    target.passive_bearing = target.bearing = 100.0
    target.observer_x, target.observer_y = ship.x, ship.y
    fixed = Contact(3, 901, "passiv", "sub")
    fixed.passive_bearing = fixed.bearing = 140.0
    fixed.observed_x, fixed.observed_y = ship.x + .3, ship.y + .35
    fixed.range_est, fixed.range_source, fixed.range_sigma_nm = .46, "tma", .1
    fixed.tma_course, fixed.tma_speed = 60.0, 8.0
    fixed.observer_x, fixed.observer_y = ship.x, ship.y
    game.sonar.contacts[target.id] = target
    game.sonar.contacts[fixed.id] = fixed
    game.target = target
    game.selected_contact = fixed if selected_fix else None
    game.map_follow = True
    game.map_view.scale = 160.0


def _chart(game: Game) -> pygame.Rect:
    with layout.bottom_panel_regions(game.bottom_panel_mode()):
        return pygame.Rect(config.MAP_RECT)


def _problems(game: Game) -> list:
    with layout.capture_text() as traced:
        game.draw()
    chart = _chart(game)
    inside = [item for item in traced if item["ink"].colliderect(chart)
              and chart.collidepoint(item["ink"].center)]
    problems = [f"off chart: {item['text']!r} {item['ink']}"
                for item in inside if not chart.contains(item["ink"])]
    for a, b in itertools.combinations(inside, 2):
        if a["ink"].colliderect(b["ink"]):
            problems.append(f"overlap: {a['text']!r} {a['ink']} / "
                            f"{b['text']!r} {b['ink']}")
    return problems


@pytest.mark.parametrize("language", ["en", "de"])
@pytest.mark.parametrize("station", [Station.BRIDGE, Station.WEAPONS,
                                     Station.HELICOPTER])
@pytest.mark.parametrize("selected_fix", [False, True])
@pytest.mark.parametrize("large", [False, True])
def test_frigate_chart_labels_do_not_overlap(language, station, selected_fix, large):
    game = _game(language, large)
    game.station = station
    game.station_page = 0
    _crowd(game, selected_fix)
    assert _problems(game) == []


@pytest.mark.parametrize("language", ["en", "de"])
def test_weapons_target_is_labelled_once(language):
    game = _game(language)
    game.station = Station.WEAPONS
    _crowd(game, selected_fix=False)
    with layout.capture_text() as traced:
        game.draw()
    chart = _chart(game)
    labels = [item["text"] for item in traced
              if chart.collidepoint(item["ink"].center) and "K02" in item["text"]]
    assert len(labels) == 1, labels
    assert ("Umschalt+A" if language == "de" else "Shift+A") in labels[0]


def test_scale_line_keeps_grid_numbers_out_of_its_band():
    game = _game("de")
    game.station = Station.BRIDGE
    game.draw()
    chart = _chart(game)
    band = map_view.scale_rect(chart)
    for scale in (2.0, 5.0, 12.0, 40.0, 90.0, 160.0, 400.0):
        game.map_view.scale = scale
        for offset in range(0, 40, 4):
            game.map_view.cy = game.ship.y + offset / scale
            game.map_follow = False
            with layout.capture_text() as traced:
                game.draw()
            numbers = [item for item in traced
                       if chart.collidepoint(item["ink"].center)
                       and item["text"].replace(".", "").isdigit()]
            assert all(not item["ink"].colliderect(band) for item in numbers), \
                (scale, offset, [(item["text"], item["ink"]) for item in numbers])


@pytest.mark.parametrize("language", ["en", "de"])
@pytest.mark.parametrize("role", ["uboot", "uboot_nav", "uboot_weapons"])
@pytest.mark.parametrize("scenario", [None, "s5_durchbruch", "s8_meerenge"])
def test_submarine_chart_labels_do_not_overlap(language, role, scenario):
    game = _game(language)
    game.local_side = "uboot"
    if scenario is not None:
        assert game.start_new_game(scenario, "fixed", seed=61)
    for _ in range(600):
        game.update(.1)
    game.msg_until = 0.0
    uboot_local.set_local_station(game, role)
    assert _problems(game) == []


@pytest.mark.parametrize("language", ["en", "de"])
def test_opz_chart_labels_do_not_overlap(language):
    from src.ui.stations import opz
    game = _game(language)
    for _ in range(900):
        game.update(.1)
    game.msg_until = 0.0
    game.station = Station.OPZ
    game.station_page = 0
    with layout.capture_text() as traced:
        game.draw()
    with layout.bottom_panel_regions(game.bottom_panel_mode()):
        chart = pygame.Rect(opz.opz_regions(config.OPZ_STATION_RECT)["chart"])
    inside = [item for item in traced if chart.collidepoint(item["ink"].center)]
    assert inside, "the OPZ chart should carry labels"
    overlaps = [(a["text"], b["text"]) for a, b in itertools.combinations(inside, 2)
                if a["ink"].colliderect(b["ink"])]
    assert overlaps == []


@pytest.mark.parametrize("language", ["en", "de"])
@pytest.mark.parametrize("theme", ["day", "night"])
def test_opz_bearing_scale_numbers_stay_at_their_bearing(language, theme):
    """Reported zoomed far out: "000" left of the ring, "030" outside it,
    "180" by the centre, because the scale numbers stepped aside from the
    "40 NM" ring label like movable labels. Every number now sits at its
    bearing and no ring or scale label covers another at any ring size."""
    import math
    from src.ui.stations import opz, opz_display_view
    prefs = Preferences(language=language, fullscreen=False, audio=False,
                        large_text=False, tooltips=False, theme=theme)
    game = Game(seed=1234, start_menu=False, show_splash=False,
                audio_enabled=False, preferences=prefs)
    game.msg_until = 0.0
    game.station = Station.OPZ
    game.station_page = 0
    game.surface_radar_on = True
    game.set_opz_range(40.0)
    game.draw()
    with layout.bottom_panel_regions(game.bottom_panel_mode()):
        chart = pygame.Rect(opz.opz_regions(config.OPZ_STATION_RECT)["chart"])
    for radius in (40, 60, 70, 90, 95, 110, 130, 160, 200):
        game.opz_map_view.scale = radius / 40.0
        with layout.capture_text() as traced:
            game.draw()
        view = opz._opz_view(game, chart)
        cx, cy = view.world_to_screen(game.ship.x, game.ship.y)
        unit = " sm" if language == "de" else " NM"
        scale = [item for item in traced if chart.collidepoint(item["ink"].center)
                 and (item["text"].endswith(unit) or (
                     len(item["text"]) == 3 and item["text"].isdigit()))]
        numbers = {item["text"]: item for item in scale if not item["text"].endswith(unit)}
        if opz_display_view.compass_numbers_shown(radius):
            assert len(numbers) == 12, (radius, sorted(numbers))
        for text, item in numbers.items():
            bearing = math.radians(int(text))
            dx, dy = item["ink"].centerx - cx, item["ink"].centery - cy
            assert abs(math.hypot(dx, dy) - (radius - 20)) < 8, (radius, text, item["ink"])
            assert abs(dx - math.sin(bearing) * math.hypot(dx, dy)) < 8, (radius, text)
            assert abs(dy + math.cos(bearing) * math.hypot(dx, dy)) < 8, (radius, text)
        assert any(item["text"].startswith("40") for item in scale), radius
        overlaps = [(a["text"], b["text"]) for a, b in itertools.combinations(scale, 2)
                    if a["ink"].colliderect(b["ink"])]
        assert overlaps == [], (radius, overlaps)


@pytest.mark.parametrize("language", ["en", "de"])
@pytest.mark.parametrize("station", [Station.BRIDGE, Station.HELICOPTER])
@pytest.mark.parametrize("hover", [False, True])
def test_helicopter_label_and_vector_clear_a_plot_circle(language, station, hover):
    """Reported: "HSP-5" over a plot circle's "SAR 1 R 0.3 NM", the
    helicopter's vector running through the text."""
    game = _game(language)
    game.station = station
    game.station_page = 0
    game.map_follow = True
    game.map_view.scale = 160.0
    helo = game.helo
    helo.launch(game.ship)
    helo.x, helo.y = game.ship.x + .4, game.ship.y + .3
    helo.course = 90.0
    helo.ground_speed_kn = 0.0 if hover else helo.SPEED_KN
    assert game.plot.add(dict(kind="circle", x=helo.x, y=helo.y, radius_nm=.3,
                              label="SAR 1", t=0.0)) == 1
    assert game.plot.add(dict(kind="circle", x=helo.x - .4, y=helo.y - .5, radius_nm=1.5,
                              label="SAR 2", t=0.0)) == 2
    assert _problems(game) == []
    if not hover:
        # The vector line itself keeps clear of the labels too.
        from src.ui import label_layout
        with layout.capture_text() as traced:
            game.draw()
        view = game.map_view
        px, py = view.world_to_screen(helo.x, helo.y)
        texts = [item["ink"] for item in traced
                 if "SAR 1" in item["text"] or item["text"] == "HSP-5"]
        assert texts
        for step in range(8, 60, 4):
            point = (int(px + step), int(py))
            assert not any(rect.collidepoint(point) for rect in texts), (step, texts)


def _off_chart_circles(game: Game, north_nm: float = 12.0) -> None:
    """Reported: the SAR areas off the top of a deeply zoomed chart; their
    labels were pinned to the same spot on the edge, one over the other."""
    ship = game.ship
    for index, (dx, dy, radius) in enumerate(((.3, 0.0, .3), (-.2, -.4, 1.5),
                                              (.1, .3, .8)), start=1):
        assert game.plot.add(dict(kind="circle", x=ship.x + dx, y=ship.y + dy - north_nm,
                                  radius_nm=radius, label=f"SAR {index}", t=0.0)) == index


@pytest.mark.parametrize("language", ["en", "de"])
@pytest.mark.parametrize("station", [Station.BRIDGE, Station.WEAPONS, Station.HELICOPTER])
def test_off_chart_plot_labels_sit_beside_each_other_on_the_edge(language, station):
    game = _game(language)
    game.station = station
    game.station_page = 0
    game.map_follow = True
    game.map_view.scale = 160.0
    _off_chart_circles(game)
    assert _problems(game) == []
    with layout.capture_text() as traced:
        game.draw()
    chart = _chart(game)
    shown = [item["text"] for item in traced
             if "SAR" in item["text"] and chart.contains(item["ink"])]
    assert len(shown) == 3, shown


@pytest.mark.parametrize("language", ["en", "de"])
def test_off_chart_plot_labels_do_not_overlap_on_the_opz_chart(language):
    from src.ui.stations import opz
    game = _game(language)
    game.station = Station.OPZ
    game.station_page = 0
    _off_chart_circles(game, north_nm=60.0)
    game.opz_range_nm = float(min(config.RADAR_RANGE_SCALES_NM))
    with layout.capture_text() as traced:
        game.draw()
    with layout.bottom_panel_regions(game.bottom_panel_mode()):
        chart = pygame.Rect(opz.opz_regions(config.OPZ_STATION_RECT)["chart"])
    inside = [item for item in traced if chart.collidepoint(item["ink"].center)]
    assert len([item for item in inside if "SAR" in item["text"]]) == 3
    overlaps = [(a["text"], b["text"]) for a, b in itertools.combinations(inside, 2)
                if a["ink"].colliderect(b["ink"])]
    assert overlaps == []
