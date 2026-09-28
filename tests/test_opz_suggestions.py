"""OPZ correlation suggestions: pure model, local keys and Remote Crew."""

import copy
import html
import json
import math
import random
import re
import shutil
import subprocess

import pygame
import pytest

from src.commander.bridge import CommanderBridge
from src.commander.v2.commands import V2_ACTION_REGISTRY
from src.core import config
from src.core.game import Game
from src.core.station import Station
from src.sensors.fusion import OPZObservation, suggest_correlations
from src.sonar.sonar import Contact
from src.ui.stations_view import draw_opz_view
from test_commander_bridge import Server
from test_commander_projection_schema import _validator_page


def report(key, source, bearing, *, x=None, y=None, unc=None, kind="UNKNOWN",
           seen=100.0, observer=None):
    return OPZObservation(
        key, source, kind, bearing, None if x is None else math.hypot(x, y), x, y,
        None, .8, seen, key, bearing_uncertainty_deg=unc,
        observer_x=None if observer is None else observer[0],
        observer_y=None if observer is None else observer[1])


def at(bearing, range_nm):
    rad = math.radians(bearing)
    return dict(x=range_nm * math.sin(rad), y=-range_nm * math.cos(rad))


def suggest(reports, **kwargs):
    return suggest_correlations(reports, 0.0, 0.0, 100.0, **kwargs)


def test_matching_bearings_from_different_sensors_are_suggested():
    sonar = report("O-A", "SONAR-BRG", 87.0, unc=2.0)
    radar = report("O-B", "RADAR-S", 0.0, unc=.5, kind="SURFACE", **at(88.0, 6.0))
    esm = report("O-C", "ESM", 200.0, unc=1.0)
    (only,) = suggest((sonar, radar, esm))
    assert only.members == ("O-A", "O-B") and only.key == "O-A+O-B"
    assert abs(only.bearing - 87.5) < 1e-6 and abs(only.bearing_delta_deg - 1.0) < 1e-6
    assert only.distance_nm is None


def test_mismatching_bearings_positions_and_same_sensor_are_not_suggested():
    assert not suggest((report("O-A", "SONAR-BRG", 87.0, unc=1.0),
                        report("O-B", "ESM", 97.0, unc=1.0)))
    # Same bearing, but positions 4 NM apart at 6 and 10 NM range.
    assert not suggest((report("O-A", "SONAR-PING", 0, **at(90.0, 6.0)),
                        report("O-B", "RADAR-S", 0, kind="SURFACE", **at(90.0, 10.0))))
    # Two radar tracks on one bearing are one sensor, not a correlation.
    assert not suggest((report("O-A", "RADAR-S", 0, kind="SURFACE", **at(90.0, 6.0)),
                        report("O-B", "RADAR-L", 0, kind="SURFACE", **at(90.2, 6.0))))
    # Sonar never pairs with an air track; stale and remote reports are skipped.
    assert not suggest((report("O-A", "SONAR-BRG", 90.0),
                        report("O-B", "RADAR-L", 0, kind="FLG", **at(90.0, 6.0))))
    assert not suggest((report("O-A", "SONAR-BRG", 90.0, seen=10.0),
                        report("O-B", "ESM", 90.0)))
    assert not suggest((report("O-A", "SONAR-BRG", 90.0, observer=(5.0, 5.0)),
                        report("O-B", "ESM", 90.0)))
    assert not suggest((report("O-A", "SONAR-BUOY-01-PASSIVE", 90.0),
                        report("O-B", "ESM", 90.0)))


def test_uncertainty_widens_the_bearing_gate_up_to_its_cap():
    narrow = (report("O-A", "SONAR-BRG", 90.0, unc=.1), report("O-B", "ESM", 93.0, unc=.1))
    wide = (report("O-A", "SONAR-BRG", 90.0, unc=3.0), report("O-B", "ESM", 93.0, unc=2.0))
    capped = (report("O-A", "SONAR-BRG", 90.0, unc=20.0), report("O-B", "ESM", 99.0, unc=20.0))
    assert not suggest(narrow) and len(suggest(wide)) == 1 and not suggest(capped)


def test_suggestions_are_deterministic_bounded_and_skip_fused_and_dismissed():
    reports = []
    for index in range(12):
        bearing = index * 25.0
        reports.append(report(f"O-S{index:02d}", "SONAR-BRG", bearing + .3 * (index % 3)))
        reports.append(report(f"O-E{index:02d}", "ESM", bearing))
    first = suggest(reports)
    shuffled = list(reports)
    random.Random(4).shuffle(shuffled)
    assert suggest(shuffled) == first
    assert len(first) == config.OPZ_SUGGEST_MAX
    members = [key for item in first for key in item.members]
    assert len(members) == len(set(members))
    assert [item.score for item in first] == sorted(item.score for item in first)
    top = first[0]
    assert top.key not in {item.key for item in suggest(reports, dismissed={top.key})}
    fused = suggest(reports, fused=set(top.members))
    assert all(not set(item.members) & set(top.members) for item in fused)


def _game():
    game = Game(seed=1907, start_menu=False, audio_enabled=False, language="en")
    game.station = Station.OPZ
    game.air_picture._tracks.clear()
    game.sonar.contacts.clear()
    contact = Contact(3, 88003, "passiv", "sub")
    contact.update_passive(87.0, .8, .8, "hidden producer label", game.sim_t)
    contact.released_to_opz = True
    game.sonar.contacts[contact.target_id] = contact
    sonar_bearing = next(item for item in game.opz_source_observations()
                         if item.source.startswith("SONAR")).bearing
    game.air_picture.observe(
        track_id="S-88004", kind="SURFACE", target_id=88004, source="RADAR-S",
        bearing=sonar_bearing + .5, range_nm=6.0, observer_x=game.ship.x,
        observer_y=game.ship.y, course=None, quality=.9, now=game.sim_t,
        label="hidden", bearing_uncertainty_deg=.5)
    game.air_picture.observe(
        track_id="S-88005", kind="SURFACE", target_id=88005, source="RADAR-S",
        bearing=(sonar_bearing + 120.0) % 360.0, range_nm=9.0, observer_x=game.ship.x,
        observer_y=game.ship.y, course=None, quality=.9, now=game.sim_t,
        label="hidden", bearing_uncertainty_deg=.5)
    return game


def press(game, key, mod=0):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod))


def test_u_fuses_the_top_suggestion_through_the_manual_fusion():
    game = _game()
    try:
        (suggestion,) = game.opz_suggestions()
        assert game.opz_suggestions() is game.opz_suggestions()  # cached per tick
        draw_opz_view(game)
        assert not game.opz_fusion.fusions
        press(game, pygame.K_u)
        (fusion,) = game.opz_fusion.fusions.values()
        assert fusion.members == suggestion.members
        assert game.opz_selected_track_id == fusion.fusion_id
        assert game.opz_suggestions() == ()
        press(game, pygame.K_u)  # nothing left: a notice only
        assert len(game.opz_fusion.fusions) == 1
    finally:
        game.audio.shutdown()


def test_shift_u_dismisses_without_fusing_and_stays_transient():
    game = _game()
    try:
        (suggestion,) = game.opz_suggestions()
        press(game, pygame.K_u, pygame.KMOD_SHIFT)
        assert not game.opz_fusion.fusions and game.opz_suggestions() == ()
        assert suggestion.key in game.opz_fusion.dismissed
        assert game.dismiss_opz_suggestion(list(suggestion.members)) == "stale_ref"
        game.opz_fusion.clear()
        assert game.opz_suggestions()[0].key == suggestion.key
        # Other stations never receive the key.
        game.station = Station.BRIDGE
        press(game, pygame.K_u, pygame.KMOD_SHIFT)
        assert not game.opz_fusion.dismissed
    finally:
        game.audio.shutdown()


def test_remote_opz_projection_confirm_and_dismiss():
    game = _game()
    bridge, server = CommanderBridge(), Server()
    try:
        bridge.pump(game, server, now=10.0)
        picture = server.v2_states["opz"]["opz"]
        (row,) = picture["suggestions"]
        assert set(row) == {"key", "refs", "bearing", "bearing_delta_deg", "distance_nm"}
        assert set(row["refs"]) <= {item["ref"] for item in picture["observations"]}
        assert row["key"] == "+".join(row["refs"])
        encoded = json.dumps(picture["suggestions"])
        assert "8800" not in encoded and "O-" not in encoded
        action = V2_ACTION_REGISTRY["opz_dismiss_suggestion"]
        assert action.stations == frozenset({"opz"})
        assert action.validate_params({"refs": list(row["refs"])})
        assert not action.validate_params({"refs": [row["refs"][0]] * 2})
        assert not action.validate_params({"refs": row["refs"][:1]})
        assert not action.validate_params({"refs": list(row["refs"]), "extra": 1})

        _rows, bindings = bridge._tracks(game)
        assert CommanderBridge._apply_v2_action(
            game, "opz_dismiss_suggestion", {"refs": list(row["refs"])},
            bindings, "opz") is True
        assert game.opz_suggestions() == ()
        assert CommanderBridge._apply_v2_action(
            game, "opz_dismiss_suggestion", {"refs": ["nope", row["refs"][0]]},
            bindings, "opz") == "unknown_ref"
        game.opz_fusion.dismissed.clear()
        bridge.pump(game, server, now=11.0)
        (row,) = server.v2_states["opz"]["opz"]["suggestions"]
        _rows, bindings = bridge._tracks(game)
        assert CommanderBridge._apply_v2_action(
            game, "opz_create_fusion", {"refs": list(row["refs"])},
            bindings, "opz") is True
        bridge.pump(game, server, now=12.0)
        picture = server.v2_states["opz"]["opz"]
        assert picture["suggestions"] == [] and len(picture["fusions"]) == 1
        assert set(picture["fusions"][0]["members"]) == set(row["refs"])
    finally:
        game.audio.shutdown()


def test_browser_validator_accepts_suggestions_and_rejects_foreign_refs(tmp_path):
    chromium = shutil.which("chromium") or shutil.which("chromium-browser")
    if chromium is None:
        pytest.skip("Chromium is not installed")
    game = _game()
    bridge, server = CommanderBridge(), Server()
    try:
        bridge.pump(game, server, now=10.0)
    finally:
        game.audio.shutdown()
    valid = json.loads(json.dumps({"opz": server.v2_states["opz"]}))
    assert len(valid["opz"]["opz"]["suggestions"]) == 1
    foreign = copy.deepcopy(valid)
    row = foreign["opz"]["opz"]["suggestions"][0]
    row["refs"][1] = "not-a-published-ref"
    row["key"] = "+".join(row["refs"])
    extra = copy.deepcopy(valid)
    extra["opz"]["opz"]["suggestions"][0]["x"] = 1.0
    page = tmp_path / "validate.html"
    page.write_text(_validator_page([valid, foreign, extra]), encoding="utf-8")
    result = subprocess.run(
        [chromium, "--headless", "--no-sandbox", "--disable-gpu", "--no-first-run",
         "--no-default-browser-check", "--disable-dev-shm-usage",
         f"--user-data-dir={tmp_path / 'profile'}", "--virtual-time-budget=5000",
         "--dump-dom", page.as_uri()], capture_output=True, text=True, timeout=120)
    match = re.search(r'data-result="([^"]*)"', result.stdout)
    assert match, result.stdout[-2000:] + result.stderr[-2000:]
    outcome = json.loads(html.unescape(match.group(1)))
    assert outcome["checked"] == 3
    assert sorted(item.split(":")[0] for item in outcome["failures"]) == ["1", "2"]
