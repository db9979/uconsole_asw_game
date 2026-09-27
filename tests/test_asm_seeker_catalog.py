"""The anti-ship missile seeker is a catalogued library emitter and is heard
only above the mast's radar horizon."""

import copy
import json
import random
import shutil
from pathlib import Path

import pytest

from src.air.asm import ASM
from src.core import config
from src.core.game import Game
from src.data import catalog as contact_catalog
from src.sensors.esm import (
    ESMMeasurement, ESMPicture, RadarSuiteController, SignalType,
    analyze_signal, library_emitters)
from src.weapons.air_defense import air_defense_loadout

SEEKER_KEY = "emitter.air_defense.asm.seeker"


@pytest.fixture
def game():
    result = Game(seed=4711, start_menu=False, audio_enabled=False)
    result.sim_t = 10.0
    result.mission.asm_count = 0
    for name in ("subs", "civilians", "warships", "raiders", "asms"):
        getattr(result, name).clear()
    result.flights.flights.clear()
    result.live_traffic.aircraft.clear()
    result.esm_picture = ESMPicture()
    return result


def seeker_track(emitter):
    signal = RadarSuiteController((emitter,), 3).active_signals(
        1.0, 0.0, 0.0, terminal=True)[0]
    picture = ESMPicture()
    picture.observe_batch([ESMMeasurement(
        0, 0, 90, 1, signal.frequency_hz, signal.prf_hz,
        signal.modulation_code, .9, 1.0)], 1.0)
    return picture.tracks(1.0)[0]


def test_loadout_names_the_catalogued_seeker(game):
    assert air_defense_loadout()["asm"]["seeker_emitter_key"] == SEEKER_KEY
    emitter = contact_catalog.CATALOG.emitters[SEEKER_KEY]
    assert emitter.radar_role == "missile_seeker"
    assert emitter.modulation_codes == ("pulse_doppler",)
    # A weapon library entry: no platform suite radiates it.
    assert all(SEEKER_KEY not in systems.emitter_keys
               for systems in contact_catalog.CATALOG.profile_systems.values())
    assert game._asm_seeker_emitter(game._air_defense_loadout["asm"]) is emitter


def test_seeker_intercept_ranks_as_missile_seeker_not_navigation_radar(game):
    emitters = game.runtime_catalog.emitters
    track = seeker_track(emitters[SEEKER_KEY])
    analysis = analyze_signal(track, emitters)
    best = analysis.candidates[0].score
    seeker = next(item for item in analysis.candidates
                  if item.emitter_key == SEEKER_KEY)
    assert seeker.score == best == 1.0
    # No navigation radar scores level with the seeker; an attack aircraft's
    # pulse-Doppler fire-control radar can, so a tie stays a tie.
    assert all(emitters[item.emitter_key].radar_role in (
        "missile_seeker", "fire_control")
        for item in analysis.candidates if item.score >= best - .10)
    assert analysis.radar_type in (SignalType.MISSILE_SEEKER,
                                   SignalType.FIRE_CONTROL)
    assert SEEKER_KEY in {item.emitter_key
                          for item in library_emitters(track, emitters)}


def test_seeker_has_a_localized_library_name(game):
    assert game.eloka_emitter_name(SEEKER_KEY) == "Anti-ship missile seeker"
    assert game.eloka_emitter_name("emitter.su_25.radar") is not None


def test_platform_attached_missile_seeker_is_rejected(tmp_path):
    source = Path(contact_catalog.__file__).resolve().parents[2] / "data" / "contacts"
    target = tmp_path / "contacts"
    shutil.copytree(source, target)
    path = target / "aircraft.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    profile = next(item for item in document["profiles"]
                   if item["profile_key"] == "su_25")
    profile["emitter_keys"].append(SEEKER_KEY)
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="missile seeker attached"):
        contact_catalog._load_catalog_from(target)


def test_snapshot_without_seeker_keeps_emitting_the_packaged_signature(game):
    snapshot = copy.deepcopy(game.runtime_catalog.runtime_snapshot())
    component = snapshot["components"]["aircraft.json"]
    component["emitters"] = [row for row in component["emitters"]
                             if row["key"] != SEEKER_KEY]
    game.runtime_catalog = contact_catalog.catalog_from_runtime_snapshot(snapshot)
    assert SEEKER_KEY not in game.runtime_catalog.emitters
    emitter = game._asm_seeker_emitter(game._air_defense_loadout["asm"])
    assert emitter is contact_catalog.CATALOG.emitters[SEEKER_KEY]


def _seeker_heard(game, distance_nm, altitude_m):
    missile = ASM(game.ship.x + distance_nm, game.ship.y, 270, 1,
                  random.Random(5), game._air_defense_loadout["asm"],
                  altitude_m=altitude_m)
    missile.jammer = False
    assert missile.seeker_active(game.ship)
    game.asms[:] = [missile]
    game.esm_picture = ESMPicture()
    game._update_esm_picture()
    return any(abs(((track.bearing - 90.0) + 180.0) % 360.0 - 180.0) < 15.0
               for track in game.esm_picture.tracks(game.sim_t))


def test_seeker_below_the_radar_horizon_is_not_heard(game):
    horizon = config.radar_horizon_nm(config.RADAR_ANTENNA_HEIGHT_M, 0.0)
    assert horizon < 12.0 < air_defense_loadout()["asm"]["seeker_active_range_nm"]
    assert not _seeker_heard(game, 12.0, 0.0)
    assert _seeker_heard(game, 12.0, 20.0)
    assert _seeker_heard(game, horizon - 1.0, 0.0)


def test_own_ecm_cannot_reach_a_seeker_below_the_horizon(game):
    missile = ASM(game.ship.x + 12.0, game.ship.y, 270, 1, random.Random(5),
                  game._air_defense_loadout["asm"], altitude_m=0.0)
    captured = {}

    def effect_details_on(signal, distance, *, line_of_sight, **_kwargs):
        captured["line_of_sight"] = line_of_sight
        return None

    game.ecm_jammer.channels.append(object())
    game.ecm_jammer.effect_details_on = effect_details_on
    game._ecm_effect_against_asm(missile)
    assert captured["line_of_sight"] is False
    missile.altitude_m = 20.0
    game._ecm_effect_against_asm(missile)
    assert captured["line_of_sight"] is True
