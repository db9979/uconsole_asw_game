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
