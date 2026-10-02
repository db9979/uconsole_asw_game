"""Group hunt: the consort destroyer of scenarios s21 and s22 (src/core/consort.py)."""

import json
import math

import pygame
import pytest

from src.commander import projections
from src.commander.v2 import schema
from src.commander.v2.commands import V2_ACTION_REGISTRY as V2_ACTIONS
from src.core import config, consort as consort_model, save_migrate
from src.core.consort import ConsortOrders
from src.core.game import Game
from src.core.save_validate import valid_save_document
from src.core.station import Station


def _game(key="s21_suchgruppe", seed=5):
    game = Game(seed=seed, start_menu=False, audio_enabled=False)
    game.reset(seed, key)
    return game


def _run(game, seconds):
    for _ in range(int(seconds * 10)):
        game.update(0.1)


def test_only_group_hunts_bring_a_commanded_destroyer():
    assert _game("s2_doppeljagd").consort is None
    for key in ("s21_suchgruppe", "s22_jagdgruppe"):
        game = _game(key)
        ship = game.consort_ship()
        assert ship is not None and ship.commanded and ship.side == "friendly"
        assert ship.signature_key == config.CONSORT_PROFILE
        assert math.isclose(math.hypot(ship.x - game.ship.x, ship.y - game.ship.y),
                            config.CONSORT_STATION_NM, abs_tol=1.0)
    assert config.scenario_side("s21_suchgruppe") == "frigate"
    assert config.scenario_side("s22_jagdgruppe") == "uboot"


def test_the_destroyer_never_shifts_the_worlds_draws():
    """Its own random stream: the submarines start where they would without it."""
    plain = Game(seed=5, start_menu=False, audio_enabled=False)
    plain.reset(5, "s21_suchgruppe")
    state = plain.rng_world.getstate()
    config.SCENARIOS["s21_suchgruppe"]["consort"] = False
    try:
        bare = Game(seed=5, start_menu=False, audio_enabled=False)
        bare.reset(5, "s21_suchgruppe")
    finally:
        config.SCENARIOS["s21_suchgruppe"]["consort"] = True
    assert bare.rng_world.getstate() == state
    assert [(sub.x, sub.y) for sub in bare.subs] == [(sub.x, sub.y) for sub in plain.subs]


def test_orders_steer_it_and_are_refused_without_link_or_opz():
    game = _game()
    assert game.set_consort_mode("nonsense") == "invalid_value"
    assert game.set_consort_point(game.ship.x + 20.0, game.ship.y) is True
    assert game.consort.mode == "search"
    mode, point, _active = game.consort_effective()
    assert mode == "search" and point == (game.ship.x + 20.0, game.ship.y)
    _run(game, 5)
    ship = game.consort_ship()
    assert abs(config.angle_diff_deg(ship.target_course, consort_model.bearing(
        ship.x, ship.y, *point))) < 1.0
    assert game.set_consort_mode("hold") is True
    _run(game, 2)
    assert ship.target_speed <= config.CONSORT_HOLD_KN
    assert game.cycle_consort_station() is True
    assert (game.consort.mode, game.consort.station) == ("formation", "ahead")
    ship.x += config.CONSORT_DATALINK_NM + 5.0
    assert game.set_consort_mode("auto") == "no_link"
    ship.x -= config.CONSORT_DATALINK_NM + 5.0
    game.damage.station_down = lambda station: station == "opz"
    assert game.set_consort_active(True) == "opz_down"


def test_auto_prosecutes_a_classified_located_submarine():
    game = _game()
    _run(game, 30)
    assert game.consort_effective()[0] == "formation"
    sub = game.subs[0]
    contact = game.sonar._get_contact(sub)
    contact._fx, contact._fy = game.ship.x, game.ship.y
    contact.update_mad(sub.x, sub.y, game.sim_t, 0.3, 0.8)
    assert game.consort_effective()[0] == "formation"       # not classified yet
    contact.player_class = "U_BOOT"
    mode, point, active = game.consort_effective()
    assert mode == "prosecute" and active and point == (sub.x, sub.y)


def test_its_sonar_reaches_the_frigate_only_as_measurements():
    game = _game()
    game.set_consort_active(True)
    sub = game.subs[0]
    ship = game.consort_ship()
    # Put the boat inside the active sonar's reach.
    sub.x, sub.y = ship.x + 2.0, ship.y + 1.0
    # Only the active echo here: a passive cross-fix (tested below) may also
    # land on the contact, with its own wider error and no depth.
    game._consort_passive_reports = lambda _ship: None
    heard = []
    sub.hear_ping = lambda source=None, kind="hull": heard.append((source, kind))
    _run(game, 25)
    contact = game.sonar.contacts.get(sub.id)
    assert contact is not None and "CONSORT" in contact.fixes
    fix = contact.fixes["CONSORT"]
    assert math.hypot(fix["x"] - sub.x, fix["y"] - sub.y) < 1.0
    assert fix["depth_m"] is not None
    assert heard and heard[0][1] == "hull"
    view = game.consort_view()
    assert set(view) >= {"bearings", "x", "y", "mode", "working", "asroc"}
    assert all(set(row) == {"x", "y", "bearing", "uncertainty_deg", "t", "quality"}
               for row in view["bearings"])


def test_cross_fix_needs_a_good_cut():
    assert consort_model.cross_fix((0.0, 0.0, 90.0), (0.0, 5.0, 90.0), 30.0) is None
    x, y, geometry = consort_model.cross_fix((0.0, 0.0, 90.0), (5.0, 5.0, 0.0), 30.0)
    assert (round(x, 6), round(y, 6)) == (5.0, 0.0) and geometry == pytest.approx(1.0)
    assert consort_model.cross_fix((0.0, 0.0, 270.0), (5.0, 5.0, 0.0), 30.0) is None


def test_weapons_free_fires_one_asroc_on_a_fresh_fix():
    game = _game()
    ship = game.consort_ship()
    sub = game.subs[0]
    sub.x, sub.y = ship.x + 4.0, ship.y
    contact = game.sonar._get_contact(sub)
    contact._fx, contact._fy = game.ship.x, game.ship.y
    contact.update_mad(sub.x, sub.y, game.sim_t, 0.3, 0.8)
    contact.player_class = "U_BOOT"
    assert game.consort_fire_on_prosecution() is True
    assert game.consort_fire_on_prosecution() == "busy"
    game.update(0.1)
    assert any(item.launch_platform_id == ship.id for item in game.asrocs)
    assert game.consort.last_shot_s == pytest.approx(0.0, abs=0.2)


def test_save_round_trip_and_strict_validation():
    game = _game("s22_jagdgruppe")
    game.set_consort_active(True)
    _run(game, 30)
    data = json.loads(json.dumps(game.save_state()))
    assert valid_save_document(data)
    loaded = Game(seed=1, start_menu=False, audio_enabled=False)
    loaded.load_state(data)
    assert loaded.consort.serialize() == data["consort"]
    assert loaded.consort_ship().commanded
    for bad in ({**data["consort"], "mode": "attack"},
                {**data["consort"], "warship_id": 1},
                {**data["consort"], "extra": 1}):
        assert not valid_save_document({**data, "consort": bad})
    assert ConsortOrders.valid_state(None, 500.0, 0.0)


def test_older_saves_get_no_consort():
    doc = {"version": 46}
    save_migrate.STEPS[46](doc)
    assert doc["consort"] is None


def _key(game, code, mod=0):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=code, mod=mod))


@pytest.mark.parametrize("language", ["en", "de"])
def test_opz_group_page_keys_and_drawing(language):
    from src.core.i18n import Translator
    game = _game()
    game.tr = Translator(language).t
    game.station = Station.OPZ
    game.station_page = 3
    game.draw()
    _key(game, pygame.K_a, pygame.KMOD_SHIFT)
    _key(game, pygame.K_w, pygame.KMOD_SHIFT)
    assert game.consort.active and game.consort.weapons_free
    _key(game, pygame.K_x)
    assert game.consort.mode == "search"
    _key(game, pygame.K_h)
    assert game.consort.mode == "hold"
    _key(game, pygame.K_y)
    assert game.consort.mode == "auto"
    game.draw()
    # Without a consort the page says so and the keys are refused.
    plain = _game("s1_patrouille")
    plain.station, plain.station_page = Station.OPZ, 3
    plain.draw()
    assert plain.set_consort_mode("hold") == "no_consort"


def test_remote_crew_projection_and_actions():
    game = _game()
    _run(game, 20)
    row = projections._consort(game)
    assert tuple(row) == schema.CONSORT_FIELDS
    assert all(tuple(bearing) == schema.CONSORT_BEARING_FIELDS for bearing in row["bearings"])
    assert projections._consort(_game("s1_patrouille")) is None
    for action in ("consort_set_mode", "consort_set_point", "consort_set_station",
                   "consort_set_active", "consort_set_weapons", "consort_fire"):
        assert V2_ACTIONS[action].stations == frozenset({"opz"})
    assert V2_ACTIONS["consort_fire"].direct_fire
    assert V2_ACTIONS["consort_set_mode"].validate_params({"mode": "prosecute"})
    assert not V2_ACTIONS["consort_set_mode"].validate_params({"mode": "attack"})


def test_its_hull_sonar_hears_only_near_and_slow():
    game = _game()
    ship = game.consort_ship()
    sub = game.subs[0]
    sub.x, sub.y = ship.x + config.CONSORT_PASSIVE_NM + 2.0, ship.y
    game._consort_passive_reports(ship)
    assert game._consort_bearings == {}
    sub.x = ship.x + 3.0
    ship.speed = config.CONSORT_PASSIVE_MAX_KN + 5.0
    game._consort_passive_reports(ship)
    assert game._consort_bearings == {}


def test_hunter_group_destroyer_has_two_asroc():
    assert _game("s22_jagdgruppe").consort_view()["asroc"] == 2
    assert _game("s21_suchgruppe").consort_view()["asroc"] == 8


def test_the_hunters_use_its_asroc_only_without_a_person_in_the_opz(monkeypatch):
    from src.core import hunter
    game = _game()
    ship = game.consort_ship()
    sub = game.subs[0]
    sub.x, sub.y = ship.x + 4.0, ship.y
    found = dict(x=sub.x, y=sub.y, source="sonar", age=0.0, contact=None)
    monkeypatch.setattr(hunter, "_window", lambda game, every: True)
    monkeypatch.setattr(hunter, "manned", lambda game, station: station == Station.OPZ)
    assert hunter.asroc(game, found) == "monitoring"      # weapons tight, OPZ crewed
    game.consort.weapons_free = True
    assert hunter.asroc(game, found) == "asroc"
