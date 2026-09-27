"""The crewed boat's periscope: sightings, stadimeter, diesel snorkel noise,
projection boundary, saves and the local keys (plan 1.3, phase 9)."""

import json
import math
import sys
from dataclasses import replace
from pathlib import Path

import pygame
import pytest

from src.commander import projections
from src.core import config, opfor, uboot_local
from src.core.i18n import Translator, pseudolocale
from src.core.save_schema import CREW_ORDERS_FIELDS, CREW_SIGHTING_FIELDS
from src.core.station import Station
from src.sensors.platform import MAST_DEPTH_M
from src.sonar.platforms import OWNSHIP_TARGET_ID
from src.sonar.sonar import Contact
from src.ui import layout

sys.path.insert(0, str(Path(__file__).parent))
from test_opfor_sub import _boat_apply, _crewed, _feed_texts, _game  # noqa: E402


def _place_frigate(game, boat, distance_nm, bearing=45.0):
    sub = boat.sub
    rad = math.radians(bearing)
    game.ship.x = sub.x + distance_nm * math.sin(rad)
    game.ship.y = sub.y - distance_nm * math.cos(rad)
    game.ship.course = (bearing + 90.0) % 360.0     # beam on


def _environment(night=False):
    return dict(visibility_nm=config.WEATHER_VISIBILITY_MAX_NM, night=night,
                illumination=0.1, sea_state=1)


def _clear(game, night=False):
    """Clear weather, calm sea, moonless: what the boat's optics see."""
    game._lookout_environment = lambda: _environment(night)
    game.world.hour = 1.0 if night else 12.0


def _scope_up(boat):
    sub = boat.sub
    sub.depth = sub.target_depth = sub.order_depth = MAST_DEPTH_M - 3.0
    assert sub.command_mast(True) is True
    assert opfor.scope_available(boat)


def _local_boat(seed=5):
    game = _game(seed)
    game.local_side = "uboot"
    game._update(0.05)
    assert game.opfor is not None
    return game, game.opfor


def _key(game, key, mod=0):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod, unicode=""))


def test_sighting_needs_the_mast_up_and_the_target_in_sight():
    game, _server, _bridge = _crewed(seed=61)
    boat = game.opfor
    _clear(game)
    _place_frigate(game, boat, 3.0, bearing=45.0)
    opfor.update_sightings(game, boat)
    assert boat.orders.sightings == []                 # mast down
    _scope_up(boat)
    opfor.update_crew(game, boat)
    rows = boat.orders.sightings
    assert len(rows) == 1 and rows[0]["cls"] == "warship" and rows[0]["kind"] == "SURFACE"
    assert abs(((rows[0]["bearing"] - 45.0 + 180.0) % 360.0) - 180.0) <= 4.0
    assert rows[0]["range_nm"] is None and rows[0]["target_id"] == OWNSHIP_TARGET_ID
    assert any("warship in sight" in text for text in _feed_texts(game))
    # Beyond the optical horizon of a periscope nothing is seen.
    _place_frigate(game, boat, 25.0)
    for _ in range(int(config.UBOOT_SIGHTING_LOST_S / 0.25) + 2):
        game.sim_t += 0.25
        opfor.update_sightings(game, boat)
    assert boat.orders.sightings == []
    # Lowering the mast clears the picture at once.
    _place_frigate(game, boat, 3.0)
    opfor.update_sightings(game, boat)
    assert boat.orders.sightings
    boat.sub.command_mast(False)
    opfor.update_sightings(game, boat)
    assert boat.orders.sightings == []


def test_night_shortens_the_periscope_range():
    game, _server, _bridge = _crewed(seed=62)
    boat = game.opfor
    _scope_up(boat)
    day, night = _environment(False), _environment(True)
    _clear(game, night=True)
    # A distance the day optics resolve and the night optics do not.
    distance = next(d / 10.0 for d in range(120, 5, -1) if
                    opfor._SCOPE_MODEL.margin("SURFACE", d / 10.0,
                                              eye_m=config.UBOOT_SCOPE_EYE_HEIGHT_M, **day)
                    >= 1.0 > opfor._SCOPE_MODEL.margin(
                        "SURFACE", d / 10.0, eye_m=config.UBOOT_SCOPE_EYE_HEIGHT_M, **night))
    _place_frigate(game, boat, distance)
    opfor.update_sightings(game, boat)
    assert boat.orders.sightings == []
    _clear(game)
    opfor.update_sightings(game, boat)
    assert [row["cls"] for row in boat.orders.sightings] in (["warship"], ["unknown"])


def test_stadimeter_ranges_the_sighting_under_the_crosshair_with_uncertainty():
    game, _server, _bridge = _crewed(seed=63)
    boat = game.opfor
    sub = boat.sub
    _clear(game)
    assert opfor.stadimeter(game, boat) == "uboot_mast_down"
    _scope_up(boat)
    _place_frigate(game, boat, 2.0, bearing=(sub.course + 30.0) % 360.0)
    opfor.update_sightings(game, boat)
    row = boat.orders.sightings[0]
    assert opfor.stadimeter(game, boat) == "uboot_no_sighting"   # crosshair dead ahead
    opfor.set_scope_relative(boat, (row["bearing"] - sub.course) % 360.0)
    assert opfor.sighting_in_crosshair(boat, game.sim_t) is row
    assert opfor.stadimeter(game, boat) is True
    assert row["range_nm"] is not None and row["range_t"] == game.sim_t
    # Beam on with a generic length: within a quarter of the true distance.
    assert 1.4 <= row["range_nm"] <= 2.6
    assert row["range_sigma_nm"] == pytest.approx(row["range_nm"] * config.UBOOT_STADIMETER_ERR_FRAC)
    # The boat's sonar contact of the same target gets a VISUAL fix, usable
    # for the shot like a ping fix, and it expires after 120 s.
    contact = Contact(1, OWNSHIP_TARGET_ID, "passive", "SURFACE")
    contact._fx, contact._fy = sub.x, sub.y
    boat.station.sonar.contacts[OWNSHIP_TARGET_ID] = contact
    assert opfor.stadimeter(game, boat) is True
    fixes = contact.active_fixes(game.sim_t)
    assert [fix["source"] for fix in fixes] == ["VISUAL"]
    assert contact.range_source == "visual" and contact.observed_x is not None
    assert not contact.active_fixes(game.sim_t + config.SONAR_PING_FIX_MAX_AGE_S + 1.0)
    # Aircraft and wakes carry no stadimeter reading.
    row["cls"] = "aircraft"
    assert opfor.stadimeter(game, boat) == "uboot_no_stadimeter"


def test_unrecognized_or_bow_on_target_reads_long():
    game, _server, _bridge = _crewed(seed=64)
    boat = game.opfor
    sub = boat.sub
    _clear(game)
    _scope_up(boat)
    bearing = (sub.course + 10.0) % 360.0
    _place_frigate(game, boat, 2.0, bearing=bearing)
    game.ship.course = bearing                           # bow on: short silhouette
    opfor.update_sightings(game, boat)
    row = boat.orders.sightings[0]
    opfor.set_scope_relative(boat, (row["bearing"] - sub.course) % 360.0)
    assert opfor.stadimeter(game, boat) is True
    assert row["range_nm"] > 2.0 * 2.0


def test_snorkelling_diesels_are_loud():
    game, _server, _bridge = _crewed(seed=65)
    sub = game.opfor.sub
    if sub.endurance is None:
        pytest.skip("nuclear boat in this seed")
    sub.depth = sub.target_depth = sub.order_depth = sub.endurance.profile.snorkel_depth_m
    quiet_before = sub.noise_level()
    level_before = sub.source_level_offset_db()
    lines_before = {round(f) for f, _a, _w in sub.lofar_lines(game.sim_t)}
    assert sub.command_snorkel(True) is True and sub.snorkeling
    assert sub.source_level_offset_db() == pytest.approx(level_before + config.UBOOT_SNORKEL_NOISE_DB)
    assert sub.noise_level() > quiet_before
    lines = {round(f) for f, _a, _w in sub.lofar_lines(game.sim_t)}
    assert {50, 100} <= lines and {50, 100} <= lines - lines_before | {50, 100}
    sub.command_snorkel(False)
    assert sub.source_level_offset_db() == pytest.approx(level_before)


def test_projection_carries_sightings_without_truth():
    game, _server, _bridge = _crewed(seed=66)
    boat = game.opfor
    _clear(game)
    _scope_up(boat)
    _place_frigate(game, boat, 3.0, bearing=100.0)
    opfor.update_sightings(game, boat)
    scope = projections._uboot_scope(game, boat)
    assert scope["available"] and scope["night"] is False
    assert set(scope) == {"available", "relative_deg", "bearing", "fov_deg", "window_deg",
                          "night", "visibility_nm", "sea_state", "horizon_offset",
                          "horizon_tilt", "sightings"}
    row = next(row for row in scope["sightings"] if row["cls"] == "warship")
    assert set(row) == {"ref", "category", "cls", "bearing", "span_deg", "quality", "age_s",
                        "range_nm", "range_sigma_nm", "range_age_s"}
    assert "target_id" not in row and "aspect" not in row and "x" not in row
    assert "kind" not in row                       # a key the browser's inspector forbids
    assert row["bearing"] != pytest.approx(100.0, abs=1e-9)   # measured, not the truth
    json.dumps(scope, allow_nan=False)
    # The command handlers of the browser stations.
    apply = _boat_apply(game, _bridge)
    assert apply("uboot_scope_bearing", {"relative_deg": 270.0}) is True
    assert boat.orders.scope_rel_deg == 270.0
    assert apply("uboot_scope_mark", {}) == "uboot_no_sighting"
    from src.commander.server import V2_ACTION_REGISTRY
    spec = V2_ACTION_REGISTRY["uboot_scope_bearing"]
    assert spec.stations == frozenset({"uboot", "uboot_esm"})
    assert spec.validate_params({"relative_deg": 12.5}) and not spec.validate_params({"relative_deg": 360})
    assert not spec.validate_params({"bearing": 1.0})


def test_sightings_and_scope_survive_a_save_and_bad_rows_are_rejected(tmp_path):
    game, _server, _bridge = _crewed(seed=67)
    boat = game.opfor
    _clear(game)
    _scope_up(boat)
    _place_frigate(game, boat, 2.5, bearing=(boat.sub.course + 20.0) % 360.0)
    opfor.update_sightings(game, boat)
    row = boat.orders.sightings[0]
    opfor.set_scope_relative(boat, (row["bearing"] - boat.sub.course) % 360.0)
    assert opfor.stadimeter(game, boat) is True
    state = json.loads(json.dumps(game.save_state(), allow_nan=False))
    orders = state["crew"]["orders"]
    assert set(orders) == CREW_ORDERS_FIELDS
    assert set(orders["sightings"][0]) == CREW_SIGHTING_FIELDS
    assert orders["sightings"][0]["range_nm"] == pytest.approx(row["range_nm"])
    other = _game(seed=67)
    assert other._load_save_data(json.loads(json.dumps(state)))
    restored = other.opfor.orders
    assert restored.scope_rel_deg == boat.orders.scope_rel_deg
    assert restored.sightings == boat.orders.sightings
    assert sorted(restored._sightings_seen) == orders["sightings_seen"]
    for mutate in (
            lambda o: o["sightings"][0].__setitem__("target_id", 424242),
            lambda o: o["sightings"][0].__setitem__("cls", "frigate"),
            lambda o: o["sightings"][0].__setitem__("kind", "FLG"),
            lambda o: o["sightings"][0].__setitem__("range_sigma_nm", None),
            lambda o: o["sightings"][0].__setitem__("bearing", 360.0),
            lambda o: o["sightings"][0].pop("aspect"),
            lambda o: o.__setitem__("scope_rel_deg", -1.0),
            lambda o: o.__setitem__("sightings_seen", ["b", "a"]),
            lambda o: o.pop("scope_rel_deg")):
        broken = json.loads(json.dumps(state))
        mutate(broken["crew"]["orders"])
        fresh = _game(seed=67)
        before = fresh.save_state()
        assert not fresh._load_save_data(broken)
        assert fresh.save_state() == before


def test_local_scope_page_keys_and_pages():
    from src.ui import uboot_view
    game, boat = _local_boat()
    sub = boat.sub
    _clear(game)
    assert uboot_view.UBOOT_PAGES == ("UBOOT_NAV", "UBOOT_WEAPONS", "UBOOT_SCOPE", "UBOOT_THREAT")
    assert uboot_view.station_pages("uboot_esm") == ("UBOOT_ESM", "UBOOT_SCOPE")
    _key(game, pygame.K_1)
    _key(game, pygame.K_1)
    assert boat.command_page == 2 and uboot_view.page_name(game, boat) == "UBOOT_SCOPE"
    _key(game, pygame.K_1)
    assert boat.command_page == 3 and uboot_view.page_name(game, boat) == "UBOOT_THREAT"
    _key(game, pygame.K_1)
    assert boat.command_page == 0
    _key(game, pygame.K_PAGEUP)
    assert boat.command_page == 3          # the threat page
    _key(game, pygame.K_PAGEUP)
    assert boat.command_page == 2
    # Arrows train the scope on that page only; Shift turns fast.
    _key(game, pygame.K_RIGHT)
    assert boat.orders.scope_rel_deg == config.UBOOT_SCOPE_STEP_DEG
    _key(game, pygame.K_LEFT, pygame.KMOD_SHIFT)
    assert boat.orders.scope_rel_deg == pytest.approx(
        (config.UBOOT_SCOPE_STEP_DEG - config.UBOOT_SCOPE_STEP_FAST_DEG) % 360.0)
    _key(game, pygame.K_PAGEDOWN)
    assert boat.command_page == 3
    _key(game, pygame.K_RIGHT)
    assert boat.orders.scope_rel_deg == pytest.approx(
        (config.UBOOT_SCOPE_STEP_DEG - config.UBOOT_SCOPE_STEP_FAST_DEG) % 360.0)
    # Enter reads the stadimeter (the mast station's key P raises the mast).
    _key(game, pygame.K_PAGEUP)
    _key(game, pygame.K_RETURN)
    assert boat.orders.sightings == [] and not boat.orders.mast
    _key(game, pygame.K_5)
    sub.depth = sub.target_depth = sub.order_depth = MAST_DEPTH_M - 3.0
    _key(game, pygame.K_p)
    assert boat.orders.mast
    _key(game, pygame.K_5)                                 # Mast & ESM page 2: periscope
    assert uboot_view.page_name(game, boat) == "UBOOT_SCOPE"
    bearing = (sub.course + 20.0) % 360.0
    _place_frigate(game, boat, 2.0, bearing=bearing)
    opfor.update_crew(game, boat)
    row = boat.orders.sightings[0]
    opfor.set_scope_relative(boat, (row["bearing"] - sub.course) % 360.0)
    _key(game, pygame.K_RETURN)
    assert row["range_nm"] is not None
    assert any("Stadimeter" in text for text in _feed_texts(game))


@pytest.mark.parametrize("translator", [Translator("en"), Translator("de"),
                                        Translator("en", catalog=pseudolocale())])
@pytest.mark.parametrize("large_text", [False, True])
def test_scope_page_draws_in_every_language_and_text_size(translator, large_text):
    from src.ui import uboot_view
    game, boat = _local_boat(seed=7)
    game.translator, game.tr = translator, translator.t
    game.preferences = replace(game.preferences, large_text=large_text)
    layout.configure_for(game)
    sub = boat.sub
    _clear(game)
    game.station = Station.BRIDGE
    boat.command_page = 2
    game.draw()                                           # mast down: message
    _scope_up(boat)
    for bearing in (10.0, 40.0, 200.0):
        _place_frigate(game, boat, 2.0 + bearing / 100.0, bearing=(sub.course + bearing) % 360.0)
        opfor.update_crew(game, boat)
    opfor.set_scope_relative(boat, 10.0)
    opfor.stadimeter(game, boat)
    game.world.hour = 23.0                                 # night picture
    game.draw()
    uboot_local.set_local_station(game, "uboot_esm")
    boat.command_page = 1
    game.draw()
    rect = pygame.Rect(config.STATION_PANEL_RECT)
    assert game.screen.get_bounding_rect().w <= config.SCREEN_W
    assert rect.w > 0
    layout.configure_for(large_text=False)
