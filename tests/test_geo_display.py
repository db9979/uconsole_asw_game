"""Geographic chart display: degrees and minutes of a real sea area."""

from src.world import geo
from src.world.coastline import Coastline
from src.world.projection import nm_to_lonlat
from src.world.world import World


def test_real_sector_has_a_center_and_the_fixed_chart_none():
    world = World(seed=40)
    lon, lat = geo.chart_center(world)
    center = world.coast.metadata["center"]
    assert (lon, lat) == (center["longitude"], center["latitude"])
    assert geo.chart_center(World(seed=40, coast=Coastline.load())) is None
    assert geo.format_position(World(seed=40, coast=Coastline.load()), 1, 1) is None


def test_position_text_in_degrees_and_minutes():
    assert geo.format_lat(54.3567) == "54°21,4'N"
    assert geo.format_lon(10.1367) == "010°08,2'E"
    assert geo.format_lat(-33.5, decimal_sep=".") == "33°30.0'S"
    assert geo.format_lon(-7.999999, decimal_sep=".") == "008°00.0'W"
    # Rounding never shows 60 minutes.
    assert geo.format_lat(54.99999) == "55°00,0'N"
    world = World(seed=40)
    lon, lat = geo.to_lonlat(world, 250.0, 250.0)
    center = geo.chart_center(world)
    assert abs(lon - center[0]) < 1e-9 and abs(lat - center[1]) < 1e-9
    assert geo.format_position(world, 250.0, 250.0, 1, ".") == (
        f"{geo.format_lat(lat, 1, '.')} {geo.format_lon(lon, 1, '.')}")


def test_graticule_lines_sit_on_their_degrees_and_get_finer_with_zoom():
    world = World(seed=40)
    lon0, lat0 = geo.chart_center(world)
    steps = []
    for scale in (1.0, 6.0, 80.0, 1400.0):
        meridians, parallels, lon_step, lat_step = geo.graticule(
            world, 200.0, 300.0, 200.0, 300.0, scale)
        steps.append(lat_step)
        assert meridians and parallels
        for x_nm, lon in meridians:
            assert abs(nm_to_lonlat(x_nm, 250.0, lon0, lat0)[0] - lon) < 1e-9
            assert abs(round(lon * 60.0 / lon_step) * lon_step - lon * 60.0) < 1e-6
        for y_nm, lat in parallels:
            assert abs(nm_to_lonlat(250.0, y_nm, lon0, lat0)[1] - lat) < 1e-9
            assert abs(round(lat * 60.0 / lat_step) * lat_step - lat * 60.0) < 1e-6
            # Parallels are at least 80 px apart at this scale.
            assert lat_step * scale >= 80.0 or lat_step == geo.GRATICULE_STEPS_MIN[-1]
    assert steps == sorted(steps, reverse=True) and steps[0] > steps[-1]


def test_axis_labels_are_short():
    assert geo.axis_label(54.0, 120.0, True) == "54°N"
    assert geo.axis_label(54.5, 30.0, True) == "54°30'N"
    assert geo.axis_label(7.0, 5.0, False, ".") == "7°00'E"
    assert geo.axis_label(53.335, 0.1, True, ".") == "53°20.1'N"


def _game(language="de"):
    from src.core.game import Game
    from src.core.preferences import Preferences
    prefs = Preferences(language=language, fullscreen=False, audio=False,
                        large_text=False, tooltips=False)
    game = Game(seed=40, start_menu=False, show_splash=False,
                audio_enabled=False, preferences=prefs)
    game.msg_until = 0.0
    return game


def _drawn_texts(game):
    from src.ui import layout
    with layout.capture_text() as traced:
        game.draw()
    return [item["text"] for item in traced]


def test_the_frigate_chart_shows_own_position_and_degree_grid():
    from src.core.station import Station
    game = _game("de")
    game.station = Station.BRIDGE
    texts = _drawn_texts(game)
    assert geo.format_position(game.world, game.ship.x, game.ship.y, 1, ",") in texts
    assert any(text.endswith("'N") or text.endswith("°N") for text in texts)
    assert any(text.endswith("'E") or text.endswith("°E") for text in texts)


def test_the_crewed_boat_chart_shows_its_navigated_position():
    from src.core import boat_nav, uboot_local
    game = _game("en")
    game.local_side = "uboot"
    game.update(0.1)
    boat = uboot_local.boat(game)
    assert boat is not None
    boat.orders.nav[0] += 3.0
    uboot_local.set_local_station(game, "uboot_nav")
    texts = _drawn_texts(game)
    navigated = geo.format_position(game.world, *boat_nav.position(boat), 1, ".")
    true = geo.format_position(game.world, boat.sub.x, boat.sub.y, 1, ".")
    assert navigated in texts and navigated != true


def test_position_message_follows_the_reader_language():
    from src.core.i18n import Translator, localize
    world = World(seed=40)
    position = geo.position_message(world, 250.0, 250.0)
    lon, lat = geo.to_lonlat(world, 250.0, 250.0)
    assert localize(position, Translator("en").t) == geo.format_position(world, 250.0, 250.0, 1, ".")
    assert localize(position, Translator("de").t) == geo.format_position(world, 250.0, 250.0, 1, ",")
    fixed = World(seed=40, coast=Coastline.load())
    assert geo.position_message(fixed, 1, 1) is None
    assert geo.position_fields(fixed, 12.34, 5.0) == dict(x="12.3", y="5.0")
    assert geo.position_key("task.offer.datum", geo.position_fields(fixed, 1, 1)) == "task.offer.datum"
    text = geo.position_text("radio.report.contact_ack", world, 250.0, 250.0)
    assert localize(text, Translator("en").t).endswith(geo.format_position(world, 250.0, 250.0, 1, "."))


def test_hq_task_offer_names_its_position_in_degrees_and_minutes():
    import json
    from src.core.i18n import Translator, localize
    game = _game("de")
    game.tasking.next_offer_t = 1e9
    game._offer_task("datum")
    (task,) = game.tasking.tasks
    offers = [text for _, text in game.messages if "task.offer." in json.dumps(text)]
    assert offers and offers[-1]["__u_jagd_i18n__"].endswith(".geo")
    wanted = geo.format_position(game.world, task["x"], task["y"], 1, ",")
    assert wanted in localize(offers[-1], Translator("de").t)


def _traced(game):
    from src.ui import layout
    with layout.capture_text() as traced:
        game.draw()
    return traced


def _geo_labels(items, rect):
    return [item for item in items
            if rect.contains(item["ink"]) and item["text"].endswith(("'N", "°N", "'E", "°E"))]


def test_the_opz_plot_shows_position_and_degree_grid_without_overlap():
    import pygame
    from src.core.station import Station
    from src.core import config
    from src.ui.stations.opz import opz_regions
    for scale in (None, 3.0, 12.0):
        game = _game("de")
        game.station = Station.OPZ
        if scale is not None:
            game.opz_map_view.scale = scale
        traced = _traced(game)
        position = geo.format_position(game.world, game.ship.x, game.ship.y, 1, ",")
        chart = pygame.Rect(opz_regions(config.OPZ_STATION_RECT)["chart"])
        assert any(item["text"] == position and chart.contains(item["ink"]) for item in traced)
        labels = _geo_labels(traced, chart)
        assert any(item["text"].endswith(("'N", "°N")) for item in labels if item["text"] != position)
        assert any(item["text"].endswith(("'E", "°E")) for item in labels if item["text"] != position)
        inside = [item for item in traced if chart.contains(item["ink"])]
        for index, first in enumerate(inside):
            for second in inside[index + 1:]:
                assert not first["ink"].colliderect(second["ink"]), (first["text"], second["text"])


def test_the_radio_cross_fix_chart_shows_position_and_degree_grid():
    from src.core.station import Station
    game = _game("en")
    game.station = Station.RADIO
    game.station_page = 0
    texts = _drawn_texts(game)
    assert geo.format_position(game.world, game.ship.x, game.ship.y, 1, ".") in texts
    assert any(text.endswith(("'N", "°N")) for text in texts)
    assert any(text.endswith(("'E", "°E")) for text in texts)


def test_the_boat_pilot_chart_shows_its_navigated_position_and_grid():
    from src.core import boat_nav, uboot_local
    from src.ui import uboot_pilot
    game = _game("de")
    game.local_side = "uboot"
    game.update(0.1)
    boat = uboot_local.boat(game)
    boat.orders.nav[0] += 1.0
    uboot_local.set_local_station(game, "uboot_nav")
    texts = _drawn_texts(game)
    navigated = geo.format_position(game.world, *boat_nav.position(boat), 1, ",")
    # Once on the big chart, once on the pilot chart.
    assert texts.count(navigated) == 2
    columns, rows = uboot_pilot.geo_grid.screen_graticule(
        game, uboot_pilot.pilot_view(game, boat.sub, (0, 0, 600, 200)), (0, 0, 600, 200))
    assert columns and rows
