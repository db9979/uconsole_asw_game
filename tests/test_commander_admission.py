"""Station requests own input and are granted as one host decision."""

from copy import deepcopy

import pygame
import pytest

from src.core.game import Game
from src.commander.admission import StationAdmission
from test_commander_sessions_v2 import server, pair_v2, request


def ask(server, station="sonar"):
    _, cookie, _, client = pair_v2(server)
    assert request(server, "/api/v2/stations/request", "POST", {"station": station},
                   cookie, client["csrf"])[0] == 200
    row = server.client_statuses()[-1]
    return dict(row, requested_station=station,
                request_generation=row["stations"][station]["request_generation"])


def test_free_station_is_leased_at_once_with_all_its_rights(server):
    _, cookie, _, client = pair_v2(server)
    assert request(server, "/api/v2/stations/request", "POST", {"station": "sonar"},
                   cookie, client["csrf"])[0] == 200
    state = server.client_statuses()[0]
    assert state["active_station"] == "sonar"
    assert not state["stations"]["sonar"]["requested"]
    assert state["stations"]["sonar"]["grants"] == {
        "command": True, "direct_fire": False, "sonar_audio": True}
    assert state["simlog"] is False  # Diagnostics stay a separate host grant.


def test_held_station_waits_for_the_host_who_hands_it_over(server):
    _, _, _, holder = pair_v2(server, "Holder")
    assert server.grant_station(holder["client_id"], "weapons")
    row = ask(server, "weapons")
    assert row["stations"]["weapons"]["requested"]
    full = dict(command=True, direct_fire=True, sonar_audio=False)
    # Without a takeover decision a held station is never handed over.
    assert not server.resolve_station_request(*StationAdmission.key(row), full)
    assert not server.resolve_station_request(*StationAdmission.key(row),
                                              dict(full, command=False), takeover=True)
    assert server.resolve_station_request(*StationAdmission.key(row), full, takeover=True)
    states = {item["client_id"]: item for item in server.client_statuses()}
    assert not states[holder["client_id"]]["stations"]["weapons"]["leased"]
    assert states[row["client_id"]]["stations"]["weapons"]["grants"] == full
    assert not server.resolve_station_request(*StationAdmission.key(row), full, takeover=True)


def test_arriving_request_defaults_to_later():
    admission = StationAdmission()
    game = Game(seed=7, start_menu=False, audio_enabled=False)
    console = game.commander
    console.server = Requests()
    admission.sync(game, console)
    assert admission.request is not None and admission.selection == 2
    game.audio.shutdown()


def test_changed_request_never_hands_anything_over(server):
    _, _, _, other = pair_v2(server, "Other")
    assert server.grant_station(other["client_id"], "weapons")
    row = ask(server, "weapons")
    before = server.client_statuses()
    assert not server.resolve_station_request(row["client_id"], "weapons",
                                              row["request_generation"] + 1,
                                              dict(command=True, direct_fire=True,
                                                   sonar_audio=False), takeover=True)
    assert server.client_statuses() == before


def test_released_station_goes_to_the_oldest_waiting_request(server):
    _, _, _, holder = pair_v2(server, "Holder")
    assert server.grant_station(holder["client_id"], "bridge")
    row = ask(server, "bridge")
    assert server.revoke_station("bridge")
    states = {item["client_id"]: item for item in server.client_statuses()}
    assert states[row["client_id"]]["stations"]["bridge"]["leased"]
    assert not states[row["client_id"]]["stations"]["bridge"]["requested"]


def test_additive_free_stations_are_all_leased(server):
    _, cookie, _, client = pair_v2(server, "Multi request")
    for station in ("bridge", "sonar"):
        assert request(server, "/api/v2/stations/request", "POST", {"station": station},
                       cookie, client["csrf"])[0] == 200
    resolved = server.client_statuses()[0]
    assert resolved["active_station"] == "sonar"
    assert all(resolved["stations"][station]["leased"] for station in ("bridge", "sonar"))
    assert resolved["stations"]["sonar"]["grants"]["sonar_audio"]


class Requests:
    def __init__(self):
        self.rows = [dict(client_id="client", name="{literal} Watch", ordinal=1,
                          active_station=None, stations={
                              "sonar": dict(requested=True, request_generation=1)})]

    def client_statuses(self):
        return deepcopy(self.rows)


@pytest.mark.parametrize("language", ["en", "de"])
def test_popup_waits_for_input_owner_keeps_simulation_live_and_can_defer(language):
    game = Game(seed=7, start_menu=False, audio_enabled=False, language=language)
    console = game.commander
    console.server = Requests()
    admission = console.admission
    game._open_administration("help")
    admission.sync(game, console)
    assert admission.request is None and game.help_open
    game._open_administration("")
    game.held.add(pygame.K_LEFT)
    admission.sync(game, console)
    assert admission.request and game.commander_open and not game.held
    before = game.sim_t
    game.update(.1)
    assert game.sim_t > before
    console.draw(game)
    assert all(pygame.Rect(0, 0, 1280, 720).contains(rect) for rect in admission.rects())
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert admission.request is None and not game.administration_open
    admission.sync(game, console)
    assert admission.request is None  # Polling does not reopen a deferred request.
    console.server.rows[0]["stations"]["sonar"]["request_generation"] += 1
    admission.sync(game, console)
    assert admission.request is not None
    console.server.rows.clear()
    admission.sync(game, console)
    assert admission.request is None and not game.administration_open
    game.audio.shutdown()
