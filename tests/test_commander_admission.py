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


def test_host_decision_is_atomic_and_cannot_take_over(server):
    row = ask(server)
    grants = dict(command=True, direct_fire=False, sonar_audio=True)
    assert server.resolve_station_request(*StationAdmission.key(row), grants)
    state = server.client_statuses()[0]
    assert state["active_station"] == "sonar"
    assert not state["stations"]["sonar"]["requested"]
    assert state["stations"]["sonar"]["grants"] == grants
    assert state["simlog"] is False
    assert not server.resolve_station_request(*StationAdmission.key(row), grants)


def test_arriving_request_defaults_to_normal_station_operation():
    admission = StationAdmission()
    game = Game(seed=7, start_menu=False, audio_enabled=False)
    console = game.commander
    console.server = Requests()
    admission.sync(game, console)
    assert admission.grants == {
        "command": True, "direct_fire": False, "sonar_audio": False}
    game.audio.shutdown()


def test_changed_request_or_occupied_station_never_grants_partial_rights(server):
    row = ask(server, "weapons")
    _, _, _, other = pair_v2(server, "Other")
    assert server.grant_station(other["client_id"], "weapons")
    before = server.client_statuses()
    assert not server.resolve_station_request(*StationAdmission.key(row),
                                              dict(command=True, direct_fire=True, sonar_audio=False))
    assert server.client_statuses() == before
    assert not server.resolve_station_request(row["client_id"], "weapons",
                                              row["request_generation"] + 1)


def test_resolving_additive_requests_preserves_existing_station_authority(server):
    _, cookie, _, client = pair_v2(server, "Multi request")
    for station in ("bridge", "sonar"):
        assert request(server, "/api/v2/stations/request", "POST", {"station": station},
                       cookie, client["csrf"])[0] == 200
    row = server.client_statuses()[0]
    for station in ("bridge", "sonar"):
        detail = row["stations"][station]
        grants = dict(command=True, direct_fire=False,
                      sonar_audio=station == "sonar")
        assert server.resolve_station_request(
            row["client_id"], station, detail["request_generation"], grants)
    resolved = server.client_statuses()[0]
    assert resolved["active_station"] == "sonar"
    assert all(resolved["stations"][station]["leased"]
               for station in ("bridge", "sonar"))
    assert resolved["stations"]["bridge"]["grants"]["command"]
    assert resolved["stations"]["sonar"]["grants"]["sonar_audio"]


class Requests:
    def __init__(self):
        self.rows = [dict(client_id="client", name="{literal} Watch", ordinal=1,
                          active_station=None, stations={
                              "sonar": dict(requested=True, request_generation=1)})]

    def client_statuses(self):
        return deepcopy(self.rows)


@pytest.mark.parametrize("language", ["en", "de"])
def test_popup_waits_for_input_owner_blocks_simulation_and_can_defer(language):
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
    assert game.sim_t == before
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
