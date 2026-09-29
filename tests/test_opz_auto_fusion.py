"""Automatic OPZ fusion of reports lying on top of each other, and sources."""

import math

from src.commander.bridge import CommanderBridge
from src.core import config
from src.core.game import Game
from src.core.i18n import localize
from src.core.station import Station
from src.sensors.fusion import (OPZFusionPicture, OPZObservation, auto_fusion_plan,
                                source_group, source_groups)
from src.ui import layout
from src.ui.stations_view import draw_opz_view
from test_commander_bridge import Server


def report(key, source, bearing, range_nm=None, *, kind="SURFACE", unc=.5,
           seen=100.0, course=None, speed=None, label=None):
    x = y = None
    if range_nm is not None:
        x = range_nm * math.sin(math.radians(bearing))
        y = -range_nm * math.cos(math.radians(bearing))
    return OPZObservation(key, source, kind, bearing, range_nm, x, y, course, .8,
                          seen, label or key, bearing_uncertainty_deg=unc,
                          position_seen=seen if x is not None else None,
                          speed_kn=speed)


def one_ship(prefix="O-", bearing=40.0, range_nm=6.0):
    return [report(prefix + "R", "RADAR-S", bearing, range_nm, course=90.0, speed=8.0),
            report(prefix + "V", "LOOKOUT", bearing + .2, range_nm * 1.02),
            report(prefix + "A", "AIS", bearing - .1, range_nm, course=92.0, speed=8.2,
                   label="MV EXAMPLE")]


def fuse(picture, reports, steps=3):
    for _ in range(steps):
        picture.auto_fuse(reports, 0.0, 0.0, 100.0, 60.0)


def test_radar_lookout_and_ais_of_one_ship_become_one_contact():
    picture = OPZFusionPicture()
    reports = one_ship()
    fuse(picture, reports)
    (fusion,) = picture.fusions.values()
    assert fusion.auto and fusion.members == ("O-A", "O-R", "O-V")
    (shown,) = picture.visible(reports, 100.0, 60.0)
    assert shown.source == "FUSION" and shown.kind == "SURFACE"
    assert shown.label == "MV EXAMPLE"
    assert source_groups(shown) == ("radar", "visual", "ais")
    # The member reports stand behind the fusion, in the hidden view.
    picture.show_suppressed = True
    assert {item.observation_id for item in picture.visible(reports, 100.0, 60.0)} == {
        "O-A", "O-R", "O-V"}


def test_plan_is_pure_and_order_independent():
    reports = one_ship() + one_ship("P-", 200.0, 9.0)
    first = auto_fusion_plan(reports, 0.0, 0.0, 100.0)
    assert first == auto_fusion_plan(list(reversed(reports)), 0.0, 0.0, 100.0)
    assert len(first) == 2 and all(target is None for target, _ in first)


def test_two_ships_close_together_stay_apart():
    # Two radar echoes a few cables apart and one lookout report between them:
    # the lookout could be either ship, so nothing is fused automatically.
    reports = [report("O-R1", "RADAR-S", 40.0, 6.0),
               report("O-R2", "RADAR-S", 40.8, 6.1),
               report("O-V", "LOOKOUT", 40.4, 6.05)]
    picture = OPZFusionPicture()
    fuse(picture, reports)
    assert not picture.fusions


def test_bearing_only_reports_are_never_fused_by_themselves():
    reports = [report("O-S", "SONAR-BRG", 90.0, kind="UNKNOWN"),
               report("O-E", "ESM", 90.2, kind="UNKNOWN")]
    assert auto_fusion_plan(reports, 0.0, 0.0, 100.0) == ()
    # A bearing-only ESM report joins an unambiguous positioned radar echo.
    reports = [report("O-R", "RADAR-S", 90.0, 6.0),
               report("O-E", "ESM", 90.3, kind="UNKNOWN", unc=1.0)]
    assert auto_fusion_plan(reports, 0.0, 0.0, 100.0) == ((None, ("O-E", "O-R")),)


def test_poor_matches_and_manual_fusions_are_left_to_the_operator():
    # Inside the suggestion gates, but far from a clear match.
    reports = [report("O-R", "RADAR-S", 90.0, 6.0, course=90.0, speed=8.0),
               report("O-A", "AIS", 90.0, 7.3, course=120.0, speed=10.5)]
    assert auto_fusion_plan(reports, 0.0, 0.0, 100.0) == ()
    picture = OPZFusionPicture()
    reports = one_ship()
    picture.marked = {"O-R", "O-V"}
    manual = picture.create(reports)
    fuse(picture, reports)
    assert set(picture.fusions) == {manual.fusion_id}


def test_dissolved_fusion_stays_apart_until_a_report_is_new():
    picture = OPZFusionPicture()
    reports = one_ship()
    fuse(picture, reports)
    (key,) = picture.fusions
    assert picture.dissolve(key)
    fuse(picture, reports)
    assert not picture.fusions


def test_fusion_keeps_its_identity_while_two_reports_remain():
    picture = OPZFusionPicture()
    reports = one_ship()
    fuse(picture, reports)
    (key,) = picture.fusions
    picture.classifications[key] = "FAHRZEUG"
    without_lookout = [item for item in reports if item.source != "LOOKOUT"]
    # Between correlation steps the fusion stands on its current members.
    computed = picture.computed(picture.fusions[key], without_lookout, 100.0, 60.0)
    assert computed.members == ("O-A", "O-R")
    picture.prune(without_lookout)
    assert picture.fusions[key].members == ("O-A", "O-R", "O-V")
    fuse(picture, without_lookout, 1)
    assert picture.fusions[key].members == ("O-A", "O-R")
    assert picture.classifications[key] == "FAHRZEUG"
    fuse(picture, reports, 1)
    assert list(picture.fusions) == [key]
    assert picture.fusions[key].members == ("O-A", "O-R", "O-V")
    fuse(picture, reports[:1], 1)
    assert not picture.fusions and key not in picture.classifications


def test_source_groups_name_every_sensor():
    assert [source_group(item) for item in (
        "RADAR-S", "RADAR-L", "RADAR-MPA", "LOOKOUT", "AIS", "ESM", "SONAR-BRG",
        "SONAR-TMA", "SONAR-DIPPING", "HELO-MAD", "SONAR-BUOY-01-PASSIVE",
        "HFDF", "HFDF-FIX", "HOJ", "DATALINK")] == [
        "radar", "radar", "mpa", "visual", "ais", "esm", "sonar", "sonar", "helo",
        "helo", "buoy", "hfdf", "hfdf", "hoj", "datalink"]


def _game():
    game = Game(seed=1911, start_menu=False, audio_enabled=False, language="en")
    game.station = Station.OPZ
    game.air_picture._tracks.clear()
    game.sonar.contacts.clear()
    for track_id, source in (("S-91001", "RADAR-S"), ("L-91001", "LOOKOUT")):
        game.air_picture.observe(
            track_id=track_id, kind="SURFACE", target_id=91001, source=source,
            bearing=40.0, range_nm=6.0, observer_x=game.ship.x,
            observer_y=game.ship.y, course=None, quality=.9, now=game.sim_t,
            label="hidden", bearing_uncertainty_deg=.5)
    return game


def test_game_fuses_on_simulation_time_and_shows_the_sources(monkeypatch):
    game = _game()
    (radar,) = [item for item in game.opz_tracks() if item.source == "RADAR-S"]
    game.opz_selected_track_id = radar.observation_id
    draw_opz_view(game)
    assert not game.opz_fusion.fusions  # drawing never fuses
    game._update_opz_picture()
    (fusion,) = game.opz_tracks()
    assert fusion.source == "FUSION" and game.opz_selected_track_id == fusion.track_id
    game.station_page = 1
    shown = []
    real = layout.blit_line
    monkeypatch.setattr(layout, "blit_line", lambda surface, text, *args, **kwargs: (
        shown.append(localize(text, game.tr)),
        real(surface, text, *args, **kwargs))[1])
    draw_opz_view(game)
    assert any("Sources" in str(text) and "Radar · Lookout" in str(text)
               for text in shown)
    game.station_page = 0
    shown.clear()
    draw_opz_view(game)
    assert "RV" in shown

    bridge, server = CommanderBridge(), Server()
    bridge.pump(game, server, now=10.0)
    opz = server.v2_states["opz"]["opz"]
    (row,) = opz["fusions"]
    assert len(row["members"]) == 2
    assert {item["source"] for item in opz["observations"]
            if item["ref"] in row["members"]} == {"RADAR-S", "LOOKOUT"}


def test_down_opz_fuses_nothing():
    game = _game()
    game.damage.station_down = lambda key: key == "opz"
    game._update_opz_picture()
    assert not game.opz_fusion.fusions


def test_auto_fusion_cadence_is_simulation_time():
    game = _game()
    game._update_opz_picture()
    (key,) = game.opz_fusion.fusions
    game.dissolve_opz_fusion(key)
    game.opz_fusion.dismissed.clear()
    game._update_opz_picture()  # same simulation second: no new pass
    assert not game.opz_fusion.fusions
    game.sim_t += config.OPZ_AUTO_FUSE_INTERVAL_S
    game._update_opz_picture()
    assert len(game.opz_fusion.fusions) == 1
