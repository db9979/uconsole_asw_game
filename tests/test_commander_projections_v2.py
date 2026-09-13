"""Protocol-v2 role projection boundaries and exact envelopes."""

from copy import deepcopy
from importlib.resources import files
import json
import math
import random

import pytest

from src.enemies.surface import SurfaceShip
from src.commander.projections import ROLE_NAMES, STATE_MAX_BYTES
from src.core import config
from src.core.game import Game
from src.sonar.sonar import Contact
from test_commander_bridge import Server, observe
from src.commander.bridge import CommanderBridge
from src.air.sonobuoy import Sonobuoy
from src.weapons.asw import ASROC
from src.weapons.torpedo import Torpedo


@pytest.fixture
def published():
    game = Game(seed=83, start_menu=False, audio_enabled=False, language="en")
    contact = Contact(1, 7654321, "passiv", "sub")
    contact.update_passive(72.0, .8, .8, "", game.sim_t)
    game.sonar.contacts[contact.target_id] = contact
    observe(game)
    server, bridge = Server(), CommanderBridge()
    bridge.pump(game, server, now=10.0)
    return game, bridge, server


def test_exact_role_envelopes_and_status_only_unassigned(published):
    _, bridge, server = published
    common = {"protocol", "version", "session", "epoch", "revision", "seq",
              "phase", "role", "chart_revision", "clock", "environment", "mission"}
    assert set(server.v2_states) == {None, *ROLE_NAMES}
    assert server.v2_states[None] == dict(
        protocol=2, version=server.state["version"], session=bridge.status["session"],
        epoch=bridge.status["epoch"], revision=bridge.status["revision"],
        seq=bridge.status["seq"], phase=bridge.status["phase"], role=None,
        chart_revision=bridge.status["session"])
    for role in ROLE_NAMES:
        assert set(server.v2_states[role]) == common | {role}
        assert server.v2_states[role]["role"] == role
    assert set(server.v2_charts[None]) == {
        "protocol", "revision", "size_nm", "landmasses", "disclaimer"}
    assert server.v2_charts[None]["landmasses"] == []
    assert all(server.v2_charts[role]["landmasses"] for role in ROLE_NAMES)


def test_role_allowlists_detachment_bounds_and_no_hidden_identifiers(published):
    game, _, server = published
    expected = {
        "bridge": {"navigation", "orders", "threat", "systems",
                   "tactical_summary"},
        "sonar": {"observations", "settings", "visualization"},
        "weapons": {"inventory", "readiness", "designated_target", "navigation",
                    "tactical", "target_choices", "depth_m", "tubes",
                    "own_weapons", "active_assets"},
        "damage": {"compartments", "teams", "total", "sunk"},
        "opz": {"observations", "fusions", "radar", "source_classifications",
                 "designated_target_ref", "own_assets", "defense",
                 "asm_observations"},
        "radio": {"observations", "logged_fixes", "logged_bearings", "messages",
                   "station_down", "navigation", "tactical"},
        "engine": {"propulsion", "machinery", "controls", "environment_effects"},
        "helicopter": {"asset", "waypoint", "buoys", "readiness", "navigation",
                       "tactical", "target_choices"},
        "eloka": {"intercepts", "station_down", "status"},
    }
    encoded = json.dumps(list(server.v2_states.values()), sort_keys=True)
    for forbidden in ('"target_id"', '"track_id"', '"kind"', '"signature"',
                      '"emitter_key"', '"seed"', '"rng"', "7654321"):
        assert forbidden not in encoded
    for role in ROLE_NAMES:
        assert set(server.v2_states[role][role]) == expected[role]
        assert len(json.dumps(server.v2_states[role]).encode("ascii")) <= STATE_MAX_BYTES
    server.v2_states["damage"]["damage"]["compartments"][0]["fire"] = 99
    assert game.damage.compartments["bridge"].fire == 0


def test_control_projection_fields_are_bounded_and_do_not_expose_audio_actions(published):
    game, bridge, server = published
    game.sonar.receiver.peaks = [(12.5, .8), (25.0, .5)]
    game.damage.compartments["engine"].state = "BESCHAEDIGT"
    bridge.pump(game, server, now=10.5)

    sonar = server.v2_states["sonar"]["sonar"]["settings"]
    assert sonar["listen_bearing"] == game.sonar.listen_bearing
    assert set(sonar["tow"]) == {"state", "payout", "available", "handling_ok",
                                  "speed_kn", "speed_min_kn", "speed_max_kn",
                                  "depth_m", "depth_target_m"}
    assert sonar["tow"]["speed_kn"] == game.ship.speed
    assert sonar["tow"]["speed_min_kn"] == config.SONAR_TOWED_HANDLING_MIN_KN
    assert sonar["tow"]["speed_max_kn"] == config.SONAR_TOWED_HANDLING_MAX_KN
    assert set(sonar["bt"]) == {"ready", "cooldown_s", "thermocline_m"}
    assert set(sonar["ping"]) == {"ready", "cooldown_s"}
    assert sonar["harmonic_candidates_hz"] == [12.5, 25.0]
    assert server.v2_states["engine"]["engine"]["controls"] == {
        "orders": ["ASTERN", "STOP", "SLOW", "HALF", "FULL", "FLANK"],
        "speed_max_kn": config.SHIP_SPEED_MAX_KN}
    assert "audition_mode" not in sonar


def test_sonar_visualization_exact_schema_bounds_finite_and_detached(published):
    game, bridge, server = published
    contact = next(iter(game.sonar.contacts.values()))
    for index in range(100):
        stamp = game.sim_t
        game.sonar.broadband_history.append([index / 100] * 180)
        game.sonar.history_times.append(stamp)
        game.sonar.lofar_history.append([index / 100] * config.LOFAR_BINS)
        game.sonar.lofar_times.append(stamp)
        game.sonar.lofar_bearings.append(72.0)
    contact.raw_bearings = [(game.sim_t - index, 72.0 + index / 10, 1.5)
                            for index in range(30, 0, -1)]
    game.sonar.echo_history = [dict(
        t=game.sim_t, contact_id=contact.id, mode="BOW", bearing=71.5,
        range_nm=4.25, depth_m=80.0, range_sigma_nm=.2,
        depth_sigma_m=4.0, snr_db=12.0)]
    game.sonar.bt_profile = dict(
        t=game.sim_t, x=game.ship.x, y=game.ship.y, thermocline_m=81.0,
        water_depth_m=320.0, sea_state=2, depths_m=[0.0, 100.0, 200.0],
        speeds_m_s=[1500.0, 1492.0, 1498.0], cz_bands_nm=[[20.0, 30.0]])
    bridge.pump(game, server, now=10.5)
    visual = server.v2_states["sonar"]["sonar"]["visualization"]

    assert set(visual) == {"broadband", "lofar", "demon", "tma", "bt",
                           "active_echoes", "receiver"}
    assert set(visual["broadband"]) == {
        "bearing_start_deg", "bearing_step_deg", "history"}
    assert set(visual["lofar"]) == {"frequency_min_hz", "frequency_max_hz",
        "bin_frequencies_hz", "history", "spectrum", "held"}
    assert set(visual["demon"]) == {"frequency_min_hz", "frequency_max_hz",
        "bin_step_hz", "spectrum", "analysis"}
    assert set(visual["receiver"]) == {"array", "listen_bearing",
        "beam_width_deg", "listen_mode", "focus_locked", "audio_enabled"}
    assert len(visual["broadband"]["history"]) == config.LOFAR_HISTORY_COLS
    assert visual["broadband"]["bearing_step_deg"] == 2.0
    assert all(len(row["bins"]) == 180 for row in visual["broadband"]["history"])
    assert len(visual["lofar"]["history"]) == config.LOFAR_HISTORY_COLS
    assert all(len(row["bins"]) <= 110 for row in visual["lofar"]["history"])
    assert len(visual["lofar"]["bin_frequencies_hz"]) == config.LOFAR_BINS
    assert len(visual["demon"]["spectrum"]) <= 80
    assert len(visual["tma"]) <= 32
    assert all(len(row["bearings"]) <= 24 for row in visual["tma"])
    assert len(visual["active_echoes"]) <= 40
    assert set(visual["active_echoes"][0]) == {"age_s", "bearing", "range_nm",
        "depth_m", "range_uncertainty_nm", "depth_uncertainty_m", "snr_db",
        "array"}
    assert visual["active_echoes"][0]["range_nm"] == 4.25
    assert visual["bt"]["thermocline_m"] == 81.0

    def assert_finite_arrays(value):
        if isinstance(value, list):
            if value and all(type(item) in (int, float) for item in value):
                assert all(math.isfinite(item) for item in value)
            for item in value:
                assert_finite_arrays(item)
        elif isinstance(value, dict):
            for item in value.values():
                assert_finite_arrays(item)

    assert_finite_arrays(visual)
    snapshot = deepcopy(visual)
    visual["broadband"]["history"][0]["bins"][0] = 99
    assert game.sonar.broadband_history[-config.LOFAR_HISTORY_COLS][0] != 99
    assert len(json.dumps(server.v2_states["sonar"]).encode("ascii")) \
        < STATE_MAX_BYTES // 2
    assert snapshot["bt"]["depths_m"] == [0.0, 100.0, 200.0]


def test_operational_projection_is_deterministic_for_unchanged_game(published):
    game, bridge, server = published
    first = {role: deepcopy(server.v2_states[role][role]) for role in ROLE_NAMES}
    bridge.pump(game, server, now=10.5)
    second = {role: server.v2_states[role][role] for role in ROLE_NAMES}
    assert second == first


def test_sonar_display_id_matches_native_contact_before_and_after_opz_release(published):
    game, bridge, server = published
    contact = next(iter(game.sonar.contacts.values()))
    display_id = f"K{contact.id:02d}"
    sonar_row = server.v2_states["sonar"]["sonar"]["observations"][0]
    assert sonar_row["label"] == display_id
    assert game.private_sonar_observations()[0].label == display_id

    contact.released_to_opz = True
    bridge.pump(game, server, now=10.5)
    opz_row = next(row for row in server.v2_states["opz"]["opz"]["observations"]
                   if row["source"].startswith("SONAR"))
    native_row = next(row for row in game.opz_source_observations()
                      if row.source.startswith("SONAR"))
    assert opz_row["label"] == native_row.label == display_id
    assert sonar_row["ref"] == opz_row["ref"] != display_id


def test_known_chart_geography_is_bounded_detached_and_host_authored(published):
    game, _, server = published
    geography = server.v2_charts["bridge"]["geography"]
    assert set(geography) == {"labels", "airbases", "depths"}
    assert len(geography["labels"]) <= 128 and len(geography["airbases"]) <= 128
    assert len(geography["depths"]) <= 64
    for row in geography["airbases"]:
        assert any((row["name"], row["x"], row["y"]) ==
                   (base["name"], base["x"], base["y"])
                   for base in game.world.coast.airbases)
    if geography["depths"]:
        before = game.world.coast._bathymetry["values"][0][0]
        geography["depths"][0][0] = -999
        assert game.world.coast._bathymetry["values"][0][0] == before
        assert server.v2_charts["sonar"]["geography"]["depths"][0][0] == before


def test_map_roles_only_receive_shared_published_tactical_rows(published):
    _, _, server = published
    opz = server.v2_states["opz"]["opz"]
    released = {row["ref"] for row in opz["observations"] + opz["fusions"]}
    weapons = server.v2_states["weapons"]["weapons"]
    helicopter = server.v2_states["helicopter"]["helicopter"]
    radio = server.v2_states["radio"]["radio"]
    assert {row["ref"] for row in weapons["tactical"]} <= released
    assert {row["ref"] for row in helicopter["tactical"]} <= released
    assert all(row["source"].startswith("SONAR")
               for row in weapons["target_choices"])
    assert all(row["source"].startswith("SONAR")
               for row in helicopter["target_choices"])
    assert not released.intersection(row["ref"] for row in weapons["target_choices"])
    assert not released.intersection(row["ref"] for row in helicopter["target_choices"])
    assert {row["ref"] for row in radio["tactical"]
            if row["source"] != "HFDF"} <= released
    assert all(len(role["tactical"]) <= 128 for role in
               (weapons, helicopter, radio))
    assert len(weapons["target_choices"]) <= 128
    assert len(helicopter["target_choices"]) <= 128
    sonar_only = {row["ref"] for row in
                  server.v2_states["sonar"]["sonar"]["observations"]} - released
    assert not sonar_only.intersection(row["ref"] for row in weapons["tactical"])
    assert not sonar_only.intersection(row["ref"] for row in helicopter["tactical"])


def test_direct_fire_refs_are_role_scoped_and_chaff_uses_ready_inventory(published):
    game, bridge, server = published
    weapons = server.v2_states["weapons"]["weapons"]
    helicopter = server.v2_states["helicopter"]["helicopter"]
    weapons_refs = {row["ref"] for row in weapons["target_choices"]}
    helicopter_refs = {row["ref"] for row in helicopter["target_choices"]}
    sonar_refs = {row["ref"] for row in server.v2_states["sonar"]["sonar"][
        "observations"]}
    assert weapons_refs and helicopter_refs
    assert weapons_refs.isdisjoint(helicopter_refs | sonar_refs)
    assert all(row["source"].startswith("SONAR")
               for row in weapons["target_choices"] + helicopter["target_choices"])

    game.softkill_store.ready = 0
    game.chaff_cd = 0
    bridge.pump(game, server, now=10.5)
    assert server.v2_states["weapons"]["weapons"]["inventory"]["chaff_ready"] is False
    assert server.v2_states["opz"]["opz"]["defense"]["chaff_ready"] is False


def test_native_status_semantic_sentinels_and_exact_subschemas(published):
    game, bridge, server = published
    bridge.pump(game, server, now=10.5)
    weapons = server.v2_states["weapons"]["weapons"]
    assert weapons["designated_target"] is None
    assert weapons["depth_m"] == game.torpedo_depth
    assert set(weapons["readiness"]) == {"station_down", "roe", "ciws_ready",
        "aa_ready", "state", "interlock", "reload_s"}
    assert all(set(row) == {"tube", "state", "reload_s"}
               for row in weapons["tubes"])
    assert set(server.v2_states["opz"]["opz"]["radar"]) == {
        "surface", "air", "range_nm", "live", "sweep_bearing",
        "sweep_rate_deg_s",
        "weather_severity", "surface_effective_range_nm",
        "air_effective_range_nm"}
    assert server.v2_states["sonar"]["sonar"]["visualization"]["bt"] is None
    assert server.v2_states["eloka"]["eloka"]["status"] == "live"
    engine = server.v2_states["engine"]["engine"]
    assert engine["machinery"]["effective_speed_cap"] == \
        game.damage.engine_speed_cap()
    assert engine["machinery"]["noise"] == game.ship.noise_level()
    assert server.v2_states["helicopter"]["helicopter"]["readiness"][
        "rtb_margin_s"] is None


def test_future_and_stale_observations_omitted_without_rng_or_state_mutation(published):
    game, bridge, server = published
    observe(game, "A-900", "FLG", "RADAR-L", now=game.sim_t + 1)
    before, rng = game.save_state(), random.getstate()
    bridge.pump(game, server, now=10.5)
    assert all(row["ref"] for row in server.v2_states["opz"]["opz"]["observations"])
    assert len(server.v2_states["opz"]["opz"]["observations"]) == 0
    game.sim_t += max(config.SONAR_CONTACT_LOST_S, config.RADAR_TRACK_STALE_S) + 1
    bridge.pump(game, server, now=11.0)
    assert server.v2_states["sonar"]["sonar"]["observations"] == []
    assert game.save_state() != before  # only the explicit simulation clock edit differs
    assert random.getstate() == rng


def test_remote_eloka_correlations_use_radar_evidence_only(published, monkeypatch):
    game, bridge, server = published
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)
    emitter = SurfaceShip(
        game.ship.x + 4.0, game.ship.y, random.Random(18), hostile=True,
        profile=game.runtime_catalog.surfaces["warship_01"],
        runtime_catalog=game.runtime_catalog)
    emitter.emitter = True
    game.civilians = []
    game.warships = [emitter]
    game.flights.flights = []
    game.radar_on = False
    game._update_esm_picture()
    track = game.eloka_tracks()[0]
    sonar = game.air_picture._tracks["U-7654321"]
    sonar.bearing = sonar.raw_bearing = track.bearing

    bridge.pump(game, server, now=10.5)
    intercept = server.v2_states["eloka"]["eloka"]["intercepts"][0]
    assert intercept["correlations"] == []

    observe(game, "S-900", "SURFACE", "RADAR-S")
    radar = game.air_picture._tracks["S-900"]
    radar.bearing = radar.raw_bearing = track.bearing
    bridge.pump(game, server, now=11.0)
    correlations = server.v2_states["eloka"]["eloka"]["intercepts"][0][
        "correlations"]
    assert len(correlations) == 1


@pytest.mark.parametrize("field,value", [
    ("in_menu", True), ("main_menu", True), ("editor", object()),
    ("splash_active", True),
])
def test_redacted_phases_clear_every_role_and_chart(published, field, value):
    game, bridge, server = published
    setattr(game, field, value)
    bridge.pump(game, server, now=10.1)
    assert all(state == server.v2_states[None] for state in server.v2_states.values())
    assert all(chart == server.v2_charts[None] for chart in server.v2_charts.values())
    assert set(server.v2_states[None]) == {"protocol", "version", "session", "epoch",
        "revision", "seq", "phase", "role", "chart_revision"}


def test_world_replacement_publishes_one_immediate_redacted_generation(published):
    game, bridge, server = published
    game.world = deepcopy(game.world)
    bridge.pump(game, server, now=10.1)
    assert all(state["role"] is None for state in server.v2_states.values())
    assert all(not chart["landmasses"] for chart in server.v2_charts.values())


def test_own_asset_refs_are_opaque_stable_and_rotate_for_replacements(published):
    game, bridge, server = published
    torpedo = Torpedo(game.ship.x, game.ship.y, 20, 40, None, 71001)
    asroc = ASROC(game.ship.x, game.ship.y, game.ship.x + 1, game.ship.y + 1,
                  72001, "weapon.test", "frigate_torp", 500, 8, "friendly")
    buoy = Sonobuoy(game.ship.x + 2, game.ship.y + 2, 73001)
    game.torpedoes = [torpedo]
    game.asrocs = [asroc]
    game.buoys = [buoy]

    bridge.pump(game, server, now=10.5)
    weapons = server.v2_states["weapons"]["weapons"]["own_weapons"]
    buoys = server.v2_states["helicopter"]["helicopter"]["buoys"]
    assert len(weapons) == 2 and len(buoys) == 1
    assert all(set(row) == {"ref", "x", "y", "depth_m", "course", "state"}
               for row in weapons)
    encoded = json.dumps({"weapons": weapons, "buoys": buoys}, sort_keys=True)
    assert all(str(internal) not in encoded for internal in (71001, 72001, 73001))
    assert buoys[0]["label"] == "SB01"
    first_weapon_refs = [row["ref"] for row in weapons]
    first_buoy_ref = buoys[0]["ref"]

    bridge.pump(game, server, now=11.0)
    assert [row["ref"] for row in
            server.v2_states["weapons"]["weapons"]["own_weapons"]] == first_weapon_refs
    assert server.v2_states["helicopter"]["helicopter"]["buoys"][0]["ref"] == first_buoy_ref

    game.torpedoes = [Torpedo(torpedo.x, torpedo.y, torpedo.course,
                              torpedo.target_depth, None, torpedo.idx)]
    game.asrocs = [ASROC(asroc.x, asroc.y, asroc.datum_x, asroc.datum_y,
                         asroc.seq, asroc.weapon_key, asroc.payload_profile_key,
                         asroc.speed_kn, asroc.range_nm, asroc.side)]
    game.buoys = [Sonobuoy(buoy.x, buoy.y, buoy.seq)]
    bridge.pump(game, server, now=11.5)
    replacement_refs = [row["ref"] for row in
                        server.v2_states["weapons"]["weapons"]["own_weapons"]]
    replacement_buoy_ref = server.v2_states[
        "helicopter"]["helicopter"]["buoys"][0]["ref"]
    assert all(current != previous for current, previous in
               zip(replacement_refs, first_weapon_refs))
    assert replacement_buoy_ref != first_buoy_ref


def test_sonobuoy_labels_do_not_change_when_an_older_buoy_expires(published):
    game, bridge, server = published
    first = Sonobuoy(game.ship.x, game.ship.y, 70001)
    second = Sonobuoy(game.ship.x + 1, game.ship.y + 1, 70002)
    game.buoys = [first]
    bridge.pump(game, server, now=10.5)
    projected = server.v2_states["helicopter"]["helicopter"]["buoys"]
    assert [row["label"] for row in projected] == ["SB01"]
    game.buoys.append(second)
    bridge.pump(game, server, now=11.0)
    projected = server.v2_states["helicopter"]["helicopter"]["buoys"]
    assert [row["label"] for row in projected] == ["SB01", "SB02"]
    game.buoys.remove(first)
    bridge.pump(game, server, now=11.5)
    projected = server.v2_states["helicopter"]["helicopter"]["buoys"]
    assert [row["label"] for row in projected] == ["SB02"]


def test_own_asset_refs_rotate_after_world_change(published):
    game, bridge, server = published
    game.torpedoes = [Torpedo(game.ship.x, game.ship.y, 20, 40, None, 1)]
    bridge.pump(game, server, now=10.5)
    original = server.v2_states["weapons"]["weapons"]["own_weapons"][0]["ref"]

    game.world = deepcopy(game.world)
    bridge.pump(game, server, now=10.6)
    assert all(state["role"] is None for state in server.v2_states.values())
    bridge.pump(game, server, now=11.1)
    replacement = server.v2_states["weapons"]["weapons"]["own_weapons"][0]["ref"]
    assert replacement != original


def test_browser_exact_validator_accepts_unified_own_weapon_shape():
    script = files("data.commander").joinpath("app.js").read_text(encoding="utf-8")
    schema = ('!exactKeys(row, ["ref", "x", "y", "depth_m", '
              '"course", "state"])')
    assert schema in script
    assert "own_weapons.some((row)" in script
