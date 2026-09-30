"""AI hunters: the frigate, its helicopter and the patrol aircraft hunt a crewed
boat when nobody sails the frigate, from the frigate's own observations."""

import math
import sys
from pathlib import Path

from src.core import config, hunter
from src.core.station import Station

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_opfor_sub import _crewed  # noqa: E402
from test_uboot_scope import _local_boat  # noqa: E402


def _place(game, boat, distance_nm, bearing=90.0, depth=60.0):
    rad = math.radians(bearing)
    sub = boat.sub
    sub.x = game.ship.x + distance_nm * math.sin(rad)
    sub.y = game.ship.y - distance_nm * math.cos(rad)
    sub.depth = sub.target_depth = sub.order_depth = depth


def _fix(game, x, y, age_s=60.0):
    game.hfdf_fixes["H-test"] = dict(label="SIG-01", x=x, y=y, sigma_nm=1.0,
                                     covariance_nm2=(1.0, 0.0, 1.0),
                                     t=game.sim_t - age_s)


def _run(game, seconds, dt=0.25):
    end = game.sim_t + seconds
    while game.sim_t < end - 1e-9 and not game.game_over:
        game._update_sim(dt)


def test_the_hunters_take_over_only_when_nobody_sails_the_frigate():
    game, _server, _bridge = _crewed(seed=61)
    assert game.local_side == "frigate" and not hunter.active(game)
    game.commander.solo = True                   # a solo browser plays the boat
    assert hunter.active(game)
    game.commander.solo = False
    game.local_side = "uboot"                    # the uConsole plays the boat
    assert hunter.active(game)
    game.game_over = True
    assert not hunter.active(game)


def test_only_submarine_signatures_classify_a_contact():
    game, _boat = _local_boat(seed=61)
    phrases = hunter.sub_signatures(game)
    assert "Diesel-Propeller, deutlich hörbar" in phrases
    assert "leise, elektrischer Antrieb" in phrases
    # A phrase surface ships share never marks a contact as a submarine.
    assert "kräftige Gasturbinen-Tonals" not in phrases
    assert "stetiger Frachter-Mahl" not in phrases


def test_without_observations_the_frigate_searches_regardless_of_the_boat():
    """The search never looks at the boat: moving it changes nothing."""
    courses = []
    for distance in (40.0, 80.0):
        game, boat = _local_boat(seed=61)
        _place(game, boat, distance, bearing=200.0)
        game.sonar.contacts.clear()
        game.hunter_lead = None                  # no HQ report either
        assert hunter.datum(game) is None
        hunter.bridge(game, None)
        courses.append((round(game.ship.target_course, 6), game.ship.target_speed))
    assert courses[0] == courses[1]
    assert courses[0][1] == hunter.SEARCH_KN


def test_an_hfdf_fix_sends_ship_helicopter_and_patrol_aircraft():
    game, boat = _local_boat(seed=61)
    _place(game, boat, 60.0)
    game.sonar.contacts.clear()
    game.hunter_lead = None                  # no HQ report either
    x, y = game.ship.x + 12.0, game.ship.y
    _fix(game, x, y)
    found = hunter.datum(game)
    assert found["source"] == "hfdf" and (found["x"], found["y"]) == (x, y)
    assert found["contact"] is None                 # nothing to shoot at yet
    hunter.bridge(game, found)
    assert abs(game.ship.target_course - 90.0) < 1.0
    assert game.ship.target_speed == hunter.TRANSIT_KN
    # The deck needs HELO_READY_MEAN_S on average to ready the helicopter.
    for tick in range(1000):
        game.sim_t = tick * hunter.CADENCE_S
        if hunter.helicopter(game, found) == "launched":
            break
    assert game.helo.airborne and game.sim_t > 0.0
    assert hunter.helicopter(game, found) == "moving"
    assert (game.helo.waypoint_x, game.helo.waypoint_y) == (x, y)
    assert hunter.mpa(game, found) == "requested"
    # A stale fix is no datum.
    _fix(game, x, y, age_s=hunter.FIX_MAX_AGE_S + 1.0)
    assert hunter.datum(game) is None


def test_manned_stations_are_left_to_their_crew(monkeypatch):
    game, boat = _local_boat(seed=61)
    _place(game, boat, 60.0)
    game.sonar.contacts.clear()
    game.hunter_lead = None                  # no HQ report either
    _fix(game, game.ship.x + 12.0, game.ship.y)
    monkeypatch.setattr(game.commander, "station_leased", lambda station: True)
    course, speed = game.ship.target_course, game.ship.target_speed
    game.sim_t = 10.0
    hunter.update(game, hunter.CADENCE_S)
    assert (game.ship.target_course, game.ship.target_speed) == (course, speed)
    assert game.helo.state == "HANGAR" and game.mpa.state == "BASE"
    # Only the bridge free: the ship turns, the aircraft stay put.
    monkeypatch.setattr(game.commander, "station_leased",
                        lambda station: station is not Station.BRIDGE)
    game.sim_t = 12.0
    hunter.update(game, hunter.CADENCE_S)
    assert game.ship.target_speed == hunter.TRANSIT_KN
    assert game.helo.state == "HANGAR" and game.mpa.state == "BASE"


def test_a_heard_boat_is_classified_pinged_and_attacked():
    game, boat = _local_boat(seed=61)
    game.world.land_blocks_line = lambda *args: False
    _place(game, boat, 3.0, bearing=90.0, depth=60.0)
    game.hunter_lead = None                  # moved away from HQ's start report
    sub = boat.sub
    assert sub.set_orders(course=0.0, speed=8.0, depth=60.0) is True
    stores = (game.torpedo_count, game.helo.torps)
    # Classifying and readying the helicopter take the crew minutes.
    _run(game, 1800.0)
    rows = [contact for contact in game.sonar.contacts.values()
            if contact.target_id == sub.id]
    assert rows and rows[0].player_class == "U_BOOT"
    assert game.torpedo_count < stores[0] or sub.sunk          # the ship fired
    assert game.helo.torps < stores[1] or sub.sunk             # and the helicopter
    # One weapon per launcher in the water at a time.
    for origin, most in (("frigate", game.torpedo_salvo), ("helo", 1), ("mpa", 1)):
        assert sum(torpedo.state == "RUN" and torpedo.launch_origin == origin
                   for torpedo in game.torpedoes) <= most


def test_the_hunt_is_deterministic():
    states = []
    for _ in range(2):
        game, boat = _local_boat(seed=61)
        _place(game, boat, 3.0, bearing=90.0)
        _run(game, 120.0)
        states.append((game.ship.x, game.ship.y, game.ship.target_course,
                       game.ship.target_speed, game.helo.state, len(game.torpedoes),
                       game.sonar_ping_count if hasattr(game, "sonar_ping_count") else 0))
    assert states[0] == states[1]


def test_the_frigate_hunts_without_the_autocrew():
    game, boat = _local_boat(seed=61)
    assert not any(game.autocrew.enabled.values())
    _place(game, boat, 60.0)
    game.sonar.contacts.clear()
    game.hunter_lead = None                  # no HQ report either
    _fix(game, game.ship.x, game.ship.y - 12.0)
    _run(game, 4.0)
    assert abs(((game.ship.target_course + 180.0) % 360.0) - 180.0) < 1.0
    assert game.ship.target_speed == min(hunter.TRANSIT_KN, config.SHIP_SPEED_MAX_KN)


def _mast_up(game, boat, distance_nm=6.0, bearing=90.0):
    from src.sensors.platform import MAST_DEPTH_M
    _place(game, boat, distance_nm, bearing=bearing, depth=MAST_DEPTH_M - 3.0)
    assert boat.sub.command_mast(True) is True
    game.surface_radar_on = True
    game.world.land_blocks_line = lambda *args: False
    game._radar_conditions = lambda: dict(sea_state=1, rain_intensity=0.0, capability=1.0)


def test_the_opz_marks_a_mast_blip_and_the_hunt_goes_there():
    game, boat = _local_boat(seed=62)
    game.sonar.contacts.clear()
    game.hunter_lead = None                  # no HQ report either
    _mast_up(game, boat, 3.0, bearing=90.0)
    sub = boat.sub
    for _ in range(240):
        game._update_sim(0.25)
        if hunter.mast_tracks(game):
            break
    tracks = hunter.mast_tracks(game)
    assert tracks and tracks[0]["track_id"].startswith("R-")
    found = hunter.datum(game)
    assert found["source"] in ("radar", "sonar")
    if found["source"] == "radar":
        assert math.hypot(found["x"] - sub.x, found["y"] - sub.y) < 1.5
    # The marks survive a save: a loaded game carries the same radar picture.
    import copy
    import json
    data = json.loads(json.dumps(game.save_state()))
    marks = copy.deepcopy(data["radar_marks"])
    assert marks["marked"] and marks["blip_seq"] >= 1
    assert game._load_save_data(copy.deepcopy(data))
    assert json.loads(json.dumps(game.save_state()))["radar_marks"] == marks
    for mutate in (lambda m: m.update(blip_seq=-1),
                   lambda m: m["marked"][0].__setitem__(1, ""),
                   lambda m: m["marked"].append(list(m["marked"][0])),
                   lambda m: m.update(extra=1)):
        broken = copy.deepcopy(data)
        mutate(broken["radar_marks"])
        assert not game._load_save_data(broken)


def test_the_freshest_of_mast_track_hfdf_fix_and_hq_report_is_the_datum():
    game, boat = _local_boat(seed=63)
    _place(game, boat, 60.0)
    game.sonar.contacts.clear()
    game.hunter_lead = None                  # no HQ report either
    assert hunter.datum(game) is None
    task = dict(id=99, kind="datum", state="offered", offered_t=game.sim_t,
                respond_by_t=game.sim_t + 600.0, deadline_t=game.sim_t + 3600.0,
                ended_t=None, x=game.ship.x + 20.0, y=game.ship.y, radius_nm=5.0,
                course=None, speed_kn=None, report_t=game.sim_t, name="", persons=0,
                target_id=None, true_x=None, true_y=None, progress=0.0, sighted=False,
                plot_id=None, verdict=None, points=0)
    game.tasking.tasks.append(task)
    found = hunter.datum(game)
    assert found["source"] == "hq" and (found["x"], found["y"]) == (task["x"], task["y"])
    assert hunter.asroc(game, found) == "monitoring"       # a report is no firing datum
    game.sim_t += 300.0
    _fix(game, game.ship.x, game.ship.y - 15.0, age_s=60.0)
    assert hunter.datum(game)["source"] == "hfdf"           # fresher than the report
    _fix(game, game.ship.x, game.ship.y - 15.0, age_s=400.0)
    assert hunter.datum(game)["source"] == "hq"
    task["state"] = "declined"
    assert hunter.datum(game)["source"] == "hfdf"


def test_a_located_boat_is_passed_to_a_friendly_escorts_asroc():
    import random
    from src.enemies.surface import SurfaceShip
    game, boat = _local_boat(seed=64)
    catalog = game.runtime_catalog
    escort = SurfaceShip(game.ship.x - 2.0, game.ship.y, rng=random.Random(1), hostile=False,
                         profile=catalog.surfaces["warship_01"], side="friendly",
                         doctrine="surface_combatant", runtime_catalog=catalog)
    assert escort.asroc_weapon_key() is not None
    game.warships.append(escort)
    low, high = catalog.weapons[escort.asroc_weapon_key()].engagement_range_nm
    x, y = escort.x + (low + high) / 2.0, escort.y
    found = {"x": x, "y": y, "contact": None, "source": "radar", "age": 10.0}
    game.sim_t = hunter.ASROC_EVERY_S * 3.0 + 0.5            # a window tick
    assert hunter.asroc(game, dict(found, age=hunter.ASROC_DATUM_S + 1.0)) == "monitoring"
    assert hunter.asroc(game, found) == "asroc"
    assert escort.pending_asroc and escort.pending_asroc[0]["datum_x"] == x
    assert hunter.asroc(game, found) == "monitoring"         # one in hand at a time
    far = dict(found, x=escort.x + high + 5.0)
    escort.pending_asroc.clear()
    assert hunter.asroc(game, far) == "monitoring"          # out of the weapon's range


def _listen_esm(game, seconds=120):
    for _ in range(seconds):
        game.sim_t += 1.0
        game._update_esm_picture()
    game.sonar.contacts.clear()
    game.hunter_lead = None                  # no HQ report either


def test_an_esm_bearing_on_a_mast_radar_becomes_the_search_line():
    game, boat = _local_boat(seed=61)
    _place(game, boat, 15.0, bearing=90.0, depth=12.0)
    _listen_esm(game)
    lines = hunter.esm_bearings(game)
    assert len(lines) == 1 and abs(lines[0].bearing - 90.0) < 5.0
    found = hunter.datum(game)
    assert found["source"] == "esm" and "x" not in found
    assert abs(found["bearing"] - lines[0].bearing) < 1e-9
    point = hunter.datum_point(game, found)
    assert abs(point[1] - game.ship.y) < 2.0 and point[0] > game.ship.x
    hunter.bridge(game, found)
    assert game.ship.target_speed == hunter.LEAD_KN


def test_a_ship_on_the_bearing_explains_the_radar(monkeypatch):
    game, boat = _local_boat(seed=61)
    _place(game, boat, 15.0, bearing=90.0, depth=12.0)
    _listen_esm(game)
    monkeypatch.setattr(hunter, "_surface_bearings", lambda _game: [92.0])
    assert hunter.esm_bearings(game) == []
    assert hunter.datum(game) is None


def test_a_deep_boat_radiates_nothing_for_the_esm():
    game, boat = _local_boat(seed=61)
    _place(game, boat, 15.0, bearing=90.0, depth=60.0)
    _listen_esm(game)
    assert hunter.esm_bearings(game) == []
    assert hunter.datum(game) is None


def test_the_submarine_radar_library_holds_only_submarine_emitters():
    game, _boat = _local_boat(seed=61)
    keys = hunter.sub_emitters(game)
    assert "emitter.sub_01.mast_radar" in keys
    assert not any(key.startswith("emitter.aux_") for key in keys)
    assert config.HELO_RADAR_EMITTER not in keys


def test_a_bare_bearing_sends_no_patrol_aircraft():
    """1.3.74: the patrol aircraft flies to a position only; a sonar bearing
    alone leaves it at base."""
    game, boat = _local_boat(seed=61)
    _place(game, boat, 60.0)
    game.sonar.contacts.clear()
    game.hunter_lead = None                  # no HQ report either
    found = {"bearing": 90.0, "contact": None, "source": "hfdf"}
    assert hunter.mpa(game, found) == "monitoring" and game.mpa.state == "BASE"


def test_recognising_a_submarine_takes_the_operator_minutes():
    """1.3.74: per cadence tick a contact is recognised with the chance
    CADENCE_S / CLASSIFY_MEAN_S, so the first call comes after minutes."""
    game, _boat = _local_boat(seed=61)

    class Row:
        id = 7

    ticks = []
    for seed in range(20):
        game.seed = seed
        tick = 0
        while True:
            game.sim_t = tick * hunter.CADENCE_S
            if hunter._recognised(game, Row):
                break
            tick += 1
        ticks.append(tick * hunter.CADENCE_S)
    mean = sum(ticks) / len(ticks)
    assert 60.0 < mean < 400.0


def test_two_esm_lines_from_a_mile_apart_cross_into_a_datum():
    game, boat = _local_boat(seed=61)
    _place(game, boat, 15.0, bearing=90.0, depth=12.0)
    truth = (boat.sub.x, boat.sub.y)
    _listen_esm(game)
    assert hunter.log_esm(game) is True
    assert hunter.log_esm(game) is False              # no new line without a baseline
    assert hunter.datum(game)["source"] == "esm" and "x" not in hunter.datum(game)
    game.ship.y -= 5.0                                # run 5 NM north
    _listen_esm(game, 30)
    assert hunter.log_esm(game) is True
    found = hunter.datum(game)
    assert found["source"] == "esm" and found["contact"] is None
    assert math.hypot(found["x"] - truth[0], found["y"] - truth[1]) < 3.0
    # An ESM fix is too coarse for a friendly escort's ASROC.
    assert hunter.asroc(game, found) == "monitoring"
    # The lines are saved and restored exactly; malformed lines are rejected.
    state = game.save_state()
    assert state["hunter_esm"] == game.hunter_esm and len(state["hunter_esm"]) == 2
    assert hunter.valid_esm_log(state["hunter_esm"], game.sim_t)
    assert not hunter.valid_esm_log(state["hunter_esm"], game.sim_t - 1000.0)
    assert not hunter.valid_esm_log([dict(state["hunter_esm"][0], bearing=360.0)], game.sim_t)
    assert not hunter.valid_esm_log([dict(state["hunter_esm"][0], extra=1.0)], game.sim_t)
    # Old lines lapse.
    game.sim_t += hunter.ESM_FIX_S + 1.0
    hunter.log_esm(game)
    assert hunter.esm_fix(game) is None


def test_bearing_lines_cross_only_ahead_and_steeply_enough():
    a = dict(t=0.0, x=0.0, y=0.0, bearing=90.0)
    b = dict(t=0.0, x=0.0, y=-10.0, bearing=135.0)
    x, y = hunter.cross(a, b)
    assert abs(x - 10.0) < 1e-9 and abs(y) < 1e-9
    assert hunter.cross(a, dict(b, bearing=315.0)) is None          # behind
    assert hunter.cross(a, dict(b, y=-1.0, bearing=95.0)) is None   # too shallow


def test_an_ai_submarine_holding_the_frigate_reports_it_on_hf():
    from src.core.game import Game
    game = Game(seed=7, start_menu=False, show_splash=False)
    sub = next(item for item in game.subs if not item.manual)
    sub.memory["contact"] = dict(x=game.ship.x, y=game.ship.y)
    sub.memory["contact_age"] = 30.0
    sub.depth = 60.0
    assert not any(sub.contact_report_on_air(game.seed, t * 5.0) for t in range(360))
    sub.depth = 15.0
    on = [t * 5.0 for t in range(360) if sub.contact_report_on_air(game.seed, t * 5.0)]
    assert 1 <= len(on) <= 4 and on[-1] - on[0] < config.SUB_REPORT_TX_S
    sub.memory["contact_age"] = config.SUB_REPORT_CONTACT_S + 1.0
    assert not sub.contact_report_on_air(game.seed, on[0])
    sub.memory["contact_age"] = 30.0
    # The frigate's HF/DF hears the call.
    sub.x, sub.y = game.ship.x + 20.0, game.ship.y
    game.world.land_blocks_line = lambda *args: False
    game.sim_t = on[0]
    game._update_radio_picture()
    assert any(report.track_id == f"H-{sub.id}" for report in game.hfdf_bearings())


def _boat_mission(key="s5_durchbruch", seed=3):
    from src.core.game import Game
    game = Game(seed=seed, start_menu=False, audio_enabled=False)
    game.start_new_game(key, "fixed", seed=seed)
    return game


def test_hqs_start_report_leads_the_search_until_the_ship_is_there():
    game, boat = _local_boat(seed=61)
    _place(game, boat, 60.0)
    game.sonar.contacts.clear()
    game.hunter_lead = None
    hunter.set_hq_lead(game, 90.0, 30.0)
    found = hunter.datum(game)
    assert found["source"] == "lead"
    assert abs(found["x"] - (game.ship.x + 30.0)) < 1e-6 and abs(found["y"] - game.ship.y) < 1e-6
    hunter.bridge(game, found)
    assert round(game.ship.target_course) == 90 and game.ship.target_speed == hunter.LEAD_KN
    # A bare report never sends a torpedo or an ASROC after it.
    assert found["source"] not in ("sonar",)
    game.ship.x += 30.0 - hunter.LEAD_CLEAR_NM + 0.5
    hunter.note_lead(game)
    assert game.hunter_lead is None and hunter.datum(game) is None


def test_hqs_start_report_goes_stale():
    game, boat = _local_boat(seed=61)
    _place(game, boat, 60.0)
    game.sonar.contacts.clear()
    game.hunter_lead = None
    hunter.set_hq_lead(game, 90.0, 30.0)
    game.hunter_lead["hq"]["t"] = game.sim_t - hunter.LEAD_HQ_S - 1.0
    assert hunter.hq_area(game) is None and hunter.datum(game) is None
    hunter.note_lead(game)
    assert game.hunter_lead is None


def test_a_lost_sonar_bearing_is_run_down_then_given_up():
    game, boat = _local_boat(seed=61)
    _place(game, boat, 60.0)
    game.sonar.contacts.clear()
    ship = game.ship
    game.hunter_lead = {"hq": None,
                        "sonar": hunter._line(game.sim_t, ship.x, ship.y, 90.0, None)}
    found = hunter.datum(game)
    assert found["source"] == "lead"
    assert abs(found["x"] - (ship.x + hunter.BEARING_DATUM_NM)) < 1e-6
    # The point stays ahead of the ship as it runs down the line.
    ship.x += 10.0
    assert abs(hunter.datum(game)["x"] - (ship.x + hunter.BEARING_DATUM_NM)) < 1e-6
    ship.x += hunter.LEAD_MAX_NM
    assert hunter.datum(game) is None
    ship.x -= hunter.LEAD_MAX_NM
    game.hunter_lead["sonar"]["t"] = game.sim_t - hunter.LEAD_SONAR_S - 1.0
    hunter.note_lead(game)
    assert game.hunter_lead is None


def test_a_heard_submarine_leaves_a_sonar_lead(monkeypatch):
    game, boat = _local_boat(seed=61)
    game.hunter_lead = None

    class Contact:
        observer_x, observer_y, bearing = game.ship.x, game.ship.y, 45.0
    monkeypatch.setattr(hunter, "hunt_contacts", lambda _game: [Contact()])
    monkeypatch.setattr(hunter, "_fresh", lambda _game, _contact, _age: True)
    hunter.note_lead(game)
    line = game.hunter_lead["sonar"]
    assert line["bearing"] == 45.0 and line["range"] is None and line["t"] == game.sim_t
    assert game.hunter_lead["hq"] is None


def test_the_hunters_lead_survives_save_and_load_and_is_validated():
    game, boat = _local_boat(seed=61)
    hunter.set_hq_lead(game, 123.0, 40.0)
    game.hunter_lead["sonar"] = hunter._line(game.sim_t, game.ship.x, game.ship.y, 10.0, None)
    state = game.save_state()
    assert state["hunter_lead"] == game.hunter_lead
    assert state["hunter_lead"] is not game.hunter_lead
    game.hunter_lead = None
    assert game._load_save_data(state)
    assert game.hunter_lead == state["hunter_lead"]
    t = game.sim_t
    good = state["hunter_lead"]
    assert hunter.valid_lead(None, t) and hunter.valid_lead(good, t)
    assert not hunter.valid_lead({"hq": None, "sonar": None}, t)
    assert not hunter.valid_lead({"hq": None}, t)
    bad = dict(good, hq=dict(good["hq"], range=None))
    assert not hunter.valid_lead(bad, t)
    bad = dict(good, sonar=dict(good["sonar"], bearing=360.0))
    assert not hunter.valid_lead(bad, t)
    bad = dict(good, sonar=dict(good["sonar"], t=t + 1.0))
    assert not hunter.valid_lead(bad, t)
    bad = dict(good, hq=dict(good["hq"], x=float("nan")))
    assert not hunter.valid_lead(bad, t)
    bad = dict(good, hq=dict(good["hq"], extra=1.0))
    assert not hunter.valid_lead(bad, t)


def test_a_frigate_mission_starts_with_hqs_lead_a_boat_mission_without():
    from src.core.game import Game
    game = Game(seed=5, start_menu=False, audio_enabled=False)
    game.start_new_game("s1_patrouille", "fixed", seed=5)
    assert game.hunter_lead is not None and game.hunter_lead["hq"] is not None
    assert hunter.fire_range_nm(game) == hunter.SHIP_FIRE_NM
    boat_game = _boat_mission()
    assert boat_game.hunter_lead is None
    hunter.set_hq_lead(boat_game, 90.0, 20.0)
    assert boat_game.hunter_lead is None
    # Guarding its post the frigate holds its own torpedo to close range.
    assert hunter.fire_range_nm(boat_game) == hunter.GUARD_FIRE_NM < hunter.SHIP_FIRE_NM


def test_a_radar_radiating_for_long_is_a_ship_not_a_mast():
    game, boat = _local_boat(seed=61)
    _place(game, boat, 15.0, bearing=90.0, depth=12.0)
    _listen_esm(game)
    assert len(hunter.esm_bearings(game)) == 1
    _listen_esm(game, int(hunter.ESM_STEADY_S))
    assert hunter.esm_bearings(game) == []


def test_the_reconnaissance_boat_comes_up_for_its_look_despite_a_ping():
    game = _boat_mission("s6_aufklaerung")
    sub = next(sub for sub in game.subs if sub.side == "hostile")
    sub.mission_orders = (0.0, 4.0, 14.0)
    sub.memory["last_torpedo_age"] = float("inf")
    assert sub.evade_depth(80.0, 200.0) == 14.0
    # A torpedo in the water sends it deep.
    sub.memory["last_torpedo_age"] = 0.0
    assert sub.evade_depth(80.0, 200.0) == 120.0
    # A deep transit order or no mission keeps the old evasion.
    sub.memory["last_torpedo_age"] = float("inf")
    sub.mission_orders = (0.0, 4.0, 60.0)
    assert sub.evade_depth(80.0, 200.0) == 120.0
    sub.mission_orders = None
    assert sub.evade_depth(80.0, 110.0) == 110.0


def test_guarding_its_post_the_frigate_has_no_patrol_aircraft_and_a_short_helicopter():
    game = _boat_mission()
    ship = game.ship
    far = {"x": ship.x + hunter.HELO_GUARD_NM + 2.0, "y": ship.y, "contact": None,
           "source": "hfdf", "age": 0.0}
    assert hunter.mpa(game, far) == "monitoring" and game.mpa.state == "BASE"
    assert game.helo.state == "HANGAR"
    assert hunter.helicopter(game, far) == "monitoring" and game.helo.state == "HANGAR"
    assert hunter.HELO_GUARD_NM < hunter.HELO_RANGE_NM


def test_a_mission_boat_presses_on_through_a_ping_but_not_a_torpedo():
    game = _boat_mission()
    sub = next(sub for sub in game.subs if sub.side == "hostile")
    sub.mission_orders = (123.0, 6.0, 80.0)
    sub.memory["last_torpedo_age"] = float("inf")
    assert sub._mission_pressing_on()
    sub.memory["last_torpedo_age"] = 0.0
    assert not sub._mission_pressing_on()
    sub.memory["last_torpedo_age"] = float("inf")
    sub.mission_orders = None
    assert not sub._mission_pressing_on()
