"""The three uConsole pages of 2026-09-30: the boat's navigation page with
pilot chart and echo sounder, the helicopter's status console and the radio
room's HF/DF cross-fix chart (rendering, bounds, observation boundary)."""

import math

import pygame
import pytest

from src.core import config, echo_sounder, uboot_local
from src.core.echo_sounder import EchoSounder
from src.core.game import Game
from src.core.i18n import Translator
from src.core.station import Station
from src.ui import layout, pointer, uboot_pilot, uboot_view
from src.ui.stations import radio_chart
from src.ui.stations.helicopter import home_polar, state_lamps


def _game(language="en", seed=83):
    return Game(seed=seed, start_menu=False, audio_enabled=False, language=language)


def _boat(language="en"):
    game = _game(language)
    game.local_side = "uboot"
    game._update(0.05)
    assert game.opfor is not None
    uboot_local.set_local_station(game, "uboot_nav")
    game.opfor.command_page = 0
    return game, game.opfor


def _draw_checked(game):
    """Draw one frame; every text stays inside its bounds and is never cut."""
    with layout.capture_text() as text, layout.capture_truncations() as cut:
        game.draw()
    assert game.screen.get_size() == (1280, 720)
    assert all(item["bounds"].contains(item["rect"]) for item in text)
    return " ".join(item["text"] for item in text), [item["text"] for item in cut]


# --- echo sounder --------------------------------------------------------------

def test_echo_sounder_is_bounded_and_sampled_on_sim_time():
    sounder = EchoSounder()
    taken = [sounder.sample(t * 0.25, 1.0, 2.0, 300.0, 50.0) for t in range(40)]
    # One sample per SAMPLE_S of simulation time, however often it is asked.
    assert sum(taken) == math.ceil(40 * 0.25 / echo_sounder.SAMPLE_S)
    for step in range(1000):
        sounder.sample(10.0 + step * echo_sounder.SAMPLE_S, 1.0, 2.0, 300.0, 50.0)
    assert len(sounder.samples) == echo_sounder.SAMPLES_MAX
    now = sounder.samples[-1][0]
    assert all(now - row[0] <= echo_sounder.WINDOW_S for row in sounder.window(now))
    assert not sounder.sample(now + 60.0, 1.0, 2.0, float("nan"), 50.0)
    assert not sounder.sample(now + 60.0, 1.0, 2.0, None, 50.0)
    # A clock that runs backwards (another world) restarts the trace.
    assert sounder.sample(5.0, 1.0, 2.0, 120.0, 100.0)
    assert len(sounder.samples) == 1
    assert sounder.least_clearance(5.0) == pytest.approx(20.0)


def test_crewed_boat_samples_its_own_sounding_and_never_saves_it():
    game, boat = _boat()
    for _ in range(int(40 / 0.25)):
        game._update(0.25)
    rows = list(boat.sounder.samples)
    assert 6 <= len(rows) <= 10
    t, x, y, bottom, depth = rows[-1]
    sub = boat.sub
    assert math.hypot(x - sub.x, y - sub.y) < 0.2
    assert depth == pytest.approx(sub.depth, abs=5.0)
    assert bottom == pytest.approx(sub.last_bottom_m, rel=0.1)
    assert "sounder" not in boat.to_save()


# --- boat navigation page ------------------------------------------------------

@pytest.mark.parametrize("language", ["en", "de"])
def test_boat_navigation_opens_on_chart_and_sounder(language):
    game, boat = _boat(language)
    assert uboot_view.station_pages("uboot_nav") == ("UBOOT_PILOT", "UBOOT_NAV", "UBOOT_THREAT")
    assert uboot_view.page_name(game, boat) == "UBOOT_PILOT"
    for _ in range(80):
        game._update(0.25)
    rendered, cut = _draw_checked(game)
    tr = Translator(language).t
    assert tr("uboot.pilot.lamp.keel") in rendered
    assert tr("uboot.pilot.sounder") in rendered
    assert tr("station.page.uboot_pilot") in rendered
    # The tab of the second page reads "Navigation", never a re-translation.
    assert "Navigation" in rendered and " navigation " not in f" {rendered} "
    assert not cut


def test_boat_navigation_page_reads_only_own_ship_and_chart():
    game, boat = _boat()
    for _ in range(40):
        game._update(0.25)
    panel = pygame.Rect(config.STATION_PANEL_RECT)
    game.draw()
    before = game.screen.subsurface(panel).copy()
    # Move the frigate and every other boat: the page must not change.
    game.ship.x += 3.0
    game.ship.y -= 2.0
    for sub in game.subs:
        if sub is not boat.sub:
            sub.x += 2.0
            sub.depth = 33.0
    game.draw()
    after = game.screen.subsurface(panel).copy()
    assert pygame.image.tobytes(before, "RGB") == pygame.image.tobytes(after, "RGB")


def test_click_on_pilot_chart_orders_the_course_to_that_point():
    game, boat = _boat()
    game.draw()
    sub = boat.sub
    targets = [target for target in pointer.targets("station")
               if target.action is not None and target.rect.w > 300]
    assert targets
    chart = targets[0].rect
    east = (chart.centerx + 100, chart.centery)
    assert uboot_pilot.bearing_at(game, sub, chart, east) == 90
    assert uboot_pilot.bearing_at(game, sub, chart, (chart.centerx, chart.y + 5)) == 0
    targets[0].action(east)
    assert sub.order_course == pytest.approx(90.0)


def test_keel_clearance_levels():
    assert uboot_pilot.clearance_level(None) == "off"
    assert uboot_pilot.clearance_level(config.UBOOT_UNDER_KEEL_WARN_M - 1) == "alarm"
    assert uboot_pilot.clearance_level(uboot_pilot.PILOT_CAUTION_M - 1) == "caution"
    assert uboot_pilot.clearance_level(500.0) == "on"


# --- helicopter status console -------------------------------------------------

@pytest.mark.parametrize("language", ["en", "de"])
@pytest.mark.parametrize("airborne", [False, True])
def test_helicopter_status_console_renders_bounded(language, airborne):
    game = _game(language)
    game.station, game.station_page = Station.HELICOPTER, 0
    if airborne:
        game.helo.launch(game.ship)
        game.helo.set_waypoint(game.ship.x + 4.0, game.ship.y - 3.0)
        for _ in range(240):
            game._update(0.25)
    rendered, cut = _draw_checked(game)
    tr = Translator(language).t
    for key in ("helo.console.state.hangar", "helo.console.state.returning",
                "helo.console.fuel", "helo.console.launch_weather", "helo.air_torpedoes"):
        assert tr(key) in rendered
    assert not cut
    if airborne:
        bearing, distance, _minutes = home_polar(game, game.helo)
        assert f"{bearing:03.0f}°" in rendered
        assert distance > 0.5


def test_helicopter_state_lamps_light_exactly_the_state():
    game = _game()
    weather = game.helicopter_weather()
    levels = [level for _label, _value, level in state_lamps(game, game.helo, weather)]
    assert levels[0] == "on" and levels[2:] == ["off", "off", "off"]
    game.helo.launch(game.ship)
    levels = [level for _label, _value, level in state_lamps(game, game.helo, weather)]
    assert levels == ["off", "off", "on", "off", "off"]
    game.helo.state = "VERLOREN"
    levels = [level for _label, _value, level in state_lamps(game, game.helo, weather)]
    assert levels[2] == "alarm"


# --- radio cross-fix chart -----------------------------------------------------

def _logged_picture(game):
    ship = game.ship
    emitter = (ship.x + 30.0, ship.y - 22.0)

    def bearing(ox, oy):
        return math.degrees(math.atan2(emitter[0] - ox, -(emitter[1] - oy))) % 360.0

    rows = [("trk-a", ship.x - 10.0, ship.y + 30.0, game.sim_t - 200.0),
            ("trk-a", ship.x - 1.0, ship.y + 0.5, game.sim_t - 40.0)]
    game.hfdf_log = [dict(track_id=track, label="H-ABC123", bearing=bearing(ox, oy),
                          observer_x=ox, observer_y=oy, t=t) for track, ox, oy, t in rows]
    x, y, _geometry = game._bearing_intersection(*game.hfdf_log)
    game.hfdf_fixes = {"trk-a": dict(label="H-ABC123", x=x, y=y, sigma_nm=2.0,
                                     covariance_nm2=(4.0, 1.0, 2.0), t=game.sim_t - 40.0)}
    return x, y


@pytest.mark.parametrize("language", ["en", "de"])
def test_radio_page_draws_the_cross_fix_chart(language):
    game = _game(language)
    game.station, game.station_page = Station.RADIO, 0
    _logged_picture(game)
    rendered, cut = _draw_checked(game)
    tr = Translator(language).t
    assert tr("panel.hfdf_chart") in rendered
    assert "H-ABC123" in rendered
    assert not cut


def test_cross_fix_chart_shows_only_published_hfdf_data():
    game = _game()
    game.hfdf_log, game.hfdf_fixes = [], {}
    game.radio_picture.tracks = lambda now, kinds=None: []
    items = radio_chart.chart_items(game)
    assert items == dict(logged=[], live=[], crossings=[], fixes=[])
    x, y = _logged_picture(game)
    items = radio_chart.chart_items(game)
    assert [row["label"] for row in items["logged"]] == ["H-ABC123", "H-ABC123"]
    assert items["crossings"][0]["x"] == pytest.approx(x)
    assert items["fixes"][0]["x"] == pytest.approx(x) and items["fixes"][0]["y"] == pytest.approx(y)
    # No hostile truth: moving every submarine changes nothing on the chart.
    for sub in game.subs:
        sub.x += 5.0
    assert radio_chart.chart_items(game) == items
    # Old lines leave the chart after the window.
    game.sim_t += radio_chart.CHART_WINDOW_S + 1.0
    assert radio_chart.chart_items(game)["logged"] == []
    view = radio_chart.chart_view(game, items, pygame.Rect(0, 0, 600, 400))
    assert radio_chart.chart_half_nm(view) >= radio_chart.CHART_MIN_HALF_NM


def test_radio_chart_tooltip_follows_the_drawn_region():
    from src.ui import stations_view
    game = _game()
    game.station, game.station_page = Station.RADIO, 0
    game.draw()
    rect = pygame.Rect(config.STATION_RECT)
    from src.ui.stations.common import _station_content_top
    from src.core.commands import STATION_PAGES
    cy = _station_content_top(rect, len(STATION_PAGES[Station.RADIO]))
    regions = stations_view.hfdf_regions(rect.x + 14, cy, rect.w - 28, rect.bottom - cy - 34)
    payload = stations_view.station_hit_target(game, regions["right"].center)
    assert payload["id"] == "radio:chart"
    payload = stations_view.station_hit_target(game, regions["left"].center)
    assert payload["id"].startswith("radio:")
    assert payload["id"] != "radio:chart"
