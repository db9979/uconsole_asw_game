"""FLAK-Freigabe gegen echten ADS-B-Flugverkehr: real air traffic is never
auto-hostile. The AA gun may only ever engage a live aircraft once the
player has manually classified its OPZ track as HOSTILE (the same IFF
affiliation workflow used for every other radar/sonar contact) - this is a
regression test for the bug where any real aircraft in range was auto-shot
down within seconds, ending the mission via an instant "political incident".

A HOSTILE call alone still isn't enough to fire: because a real contact is
indistinguishable from a simulated one, a mistaken IFF classification is
itself already a political incident risk, so the player must separately and
explicitly confirm the attack (OPZ "Enter") before the AA gun is released -
and that confirmation is revoked and must be given again every time the
classification freshly turns HOSTILE."""

import pytest

from src.air.live_aircraft import LiveAircraft
from src.core.game import Game


@pytest.fixture
def game():
    result = Game(seed=4242, start_menu=False, audio_enabled=False)
    result.sim_t = 10.0
    result.mission.asm_count = 0  # keine Raider-Wellen sollen die AA-Kanone belegen
    return result


def _place_close_low_aircraft(game, icao24, *, dx_nm=1.0, altitude_m=200.0,
                              speed_kn=90.0):
    # Reale und simulierte Fluege teilen sich denselben Sequenzzaehler
    # (FlightManager.next_seq), damit Track-IDs ununterscheidbar bleiben.
    seq = game.flights.next_seq()
    aircraft = LiveAircraft(icao24, "TEST", seq, x=game.ship.x + dx_nm,
                            y=game.ship.y, altitude_m=altitude_m,
                            course=90.0, speed_kn=speed_kn, t=0.0)
    game.live_traffic.aircraft[icao24] = aircraft
    return aircraft


def _classify_as_hostile(game, aircraft) -> None:
    track_id = f"A-{aircraft.seq}"
    game.opz_tracks()  # populates _opz_source_bindings as a side effect
    observation_id = next(
        obs_id for obs_id, track in game._opz_source_bindings.items()
        if getattr(track, "track_id", None) == track_id)
    game.opz_selected_track_id = observation_id
    for _ in range(3):  # UNKNOWN -> FRIEND -> NEUTRAL -> HOSTILE
        game._cycle_opz_affiliation()
    assert game.opz_affiliation(track_id) == "HOSTILE"


def test_unclassified_real_aircraft_is_never_auto_engaged(game):
    assert game.flak_authorized is True
    aircraft = _place_close_low_aircraft(game, "unclass1")
    for _ in range(300):
        game.update(0.1, audio_dt=0.1)
    assert aircraft.despawned is False
    assert game.incident is False
    assert game.opz_affiliation(f"A-{aircraft.seq}") == "UNKNOWN"


def test_hostile_classification_alone_still_withholds_fire_pending_confirmation(game):
    """Classifying a real contact HOSTILE is a possible political incident by
    itself and must never auto-authorize weapons - the AA gun stays silent
    until the player separately confirms the attack."""
    aircraft = _place_close_low_aircraft(game, "unconfirmed1")
    for _ in range(5):
        game.update(0.1, audio_dt=0.1)
    _classify_as_hostile(game, aircraft)
    assert game.live_engage_confirm_pending == "unconfirmed1"
    for _ in range(300):
        game.update(0.1, audio_dt=0.1)
    assert aircraft.despawned is False
    assert game.incident is False


def test_manually_classified_hostile_aircraft_can_be_engaged_after_confirmation(game):
    aircraft = _place_close_low_aircraft(game, "hostile1")
    for _ in range(5):
        game.update(0.1, audio_dt=0.1)
    _classify_as_hostile(game, aircraft)
    assert game.confirm_live_engagement() is True
    for _ in range(300):
        game.update(0.1, audio_dt=0.1)
    assert aircraft.despawned is True
    assert "hostile1" not in game.live_traffic.aircraft
    assert game.incident is True


def test_reclassifying_hostile_again_requires_a_fresh_confirmation(game):
    """Confirming once must not authorize the next hostile call: cycling the
    IFF affiliation away and back to HOSTILE (or a stray re-classification)
    revokes the earlier confirmation and demands a renewed one."""
    aircraft = _place_close_low_aircraft(game, "hostile3")
    for _ in range(5):
        game.update(0.1, audio_dt=0.1)
    _classify_as_hostile(game, aircraft)
    assert game.confirm_live_engagement() is True
    assert "hostile3" in game.live_engage_authorized
    # Cycle HOSTILE -> UNKNOWN -> ... -> HOSTILE again.
    game._cycle_opz_affiliation()
    for _ in range(3):
        game._cycle_opz_affiliation()
    assert game.opz_affiliation(f"A-{aircraft.seq}") == "HOSTILE"
    assert "hostile3" not in game.live_engage_authorized
    assert game.live_engage_confirm_pending == "hostile3"
    for _ in range(300):
        game.update(0.1, audio_dt=0.1)
    assert aircraft.despawned is False
    assert game.incident is False


def test_destroyed_icao24_is_removed_from_active_tracking(game):
    aircraft = _place_close_low_aircraft(game, "hostile2")
    for _ in range(5):
        game.update(0.1, audio_dt=0.1)
    _classify_as_hostile(game, aircraft)
    assert game.confirm_live_engagement() is True
    for _ in range(300):
        game.update(0.1, audio_dt=0.1)
        if aircraft.despawned:
            break
    assert aircraft.despawned is True
    assert "hostile2" in game.live_traffic._destroyed_icao24


def test_live_aircraft_track_id_is_indistinguishable_from_simulated_flights(game):
    """Players must not be able to tell real ADS-B contacts apart from
    simulated `Flight`s by track-ID shape (no ICAO24 hex, no distinct
    prefix) or by numbering range (shared seq counter, see
    FlightManager.next_seq)."""
    simulated_seq_before = game.flights.next_seq()
    aircraft = _place_close_low_aircraft(game, "abc123")
    assert aircraft.seq == simulated_seq_before + 1  # same monotonic counter
    for _ in range(5):
        game.update(0.1, audio_dt=0.1)
    track_id = f"A-{aircraft.seq}"
    tracks = {t.track_id for t in game.air_picture.tracks(game.sim_t, ("FLG",))}
    assert track_id in tracks
    assert not any("abc123" in t for t in tracks)  # icao24 never leaks
    assert not any(t.startswith("AD-") for t in tracks)  # no distinct prefix
