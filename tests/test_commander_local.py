"""Local Commander ownership, passive lifecycle, and native-canvas integration."""

from contextlib import closing
from dataclasses import asdict, replace
import http.client
import json
import socket
import threading
import time
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pygame
import pytest

from src.commander import local
from src.commander.local import CommanderConsole
from src.core.game import Game
from src.core.i18n import Translator, load_catalog, pseudolocale
from src.core.station import Station
from src.sonar.sonar import Contact
from src.ui import layout


@pytest.fixture
def game():
    game = Game(seed=31, audio_enabled=False, language="en")
    yield game
    game.commander.stop()
    game.audio.shutdown()
    layout.configure_for(large_text=False)


def key(game, value, **attrs):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=value, **attrs))


class Transport:
    """Detached transport fixture; all decisions still use the real bridge."""
    connected = True
    lease_generation = 1
    pairing_code = "local-code"

    def __init__(self):
        self.queue = []
        self.revocations = 0

    def publish(self, state, chart=None):
        self.state = state

    def drain_commands(self, limit=4):
        batch, self.queue = self.queue[:limit], self.queue[limit:]
        return batch

    def is_current(self, envelope):
        return self.connected and envelope["lease"] == self.lease_generation

    def revoke(self):
        self.revocations += 1
        self.lease_generation += 1
        self.connected = False
        self.queue.clear()

    stop = revoke

    def send(self, action="propose", identity="one", **values):
        state = self.state
        command = dict(id=identity, session=state["session"], epoch=state["epoch"],
                       revision=state["revision"], action=action, **values)
        if action != "propose_navigation":
            command["track"] = state["tracks"][0]["ref"]
        self.queue.append(dict(command=command, lease=self.lease_generation,
                               received_at=time.monotonic()))


def session(game):
    contact = Contact(7, 7654321, "passiv", "sub")
    contact.update_passive(90.0, .8, .8, "", game.sim_t)
    game.sonar.contacts[contact.target_id] = contact
    game.air_picture.observe(
        track_id="U-7654321", kind="UNKNOWN", target_id=contact.target_id,
        source="SONAR-BRG", bearing=90.0, range_nm=None,
        observer_x=game.ship.x, observer_y=game.ship.y, course=None,
        quality=.8, now=game.sim_t, label="K7")
    console = game.commander
    console._prepared = True
    console.server = Transport()
    console.address = ("127.0.0.1", 8765)
    console.bridge.allowed = True
    console.pump(game)
    return console, console.server, contact


@pytest.mark.parametrize("explicit_regrant", [False, True])
def test_local_grant_toggle_binds_repaired_client_before_next_pump(game, explicit_regrant):
    console, server, _ = session(game)
    assert console.bridge.allowed
    server.lease_generation += 1
    assert server.connected and not console.bridge.allowed
    if explicit_regrant:
        console.selection = 3
        console.activate(game)
        assert console.bridge.allowed
    console.pump(game)
    assert console.bridge.allowed is explicit_regrant
    assert server.state["commands_allowed"] is explicit_regrant


def test_default_off_has_no_network_or_server_resources(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("passive construction attempted a network/server resource")

    monkeypatch.setattr(local.socket, "socket", forbidden)
    monkeypatch.setattr(local, "CommanderServer", forbidden)
    monkeypatch.setattr(local, "load_catalog", forbidden)
    before = set(threading.enumerate())
    game = Game(seed=31, audio_enabled=False)
    console = game.commander
    assert console.server is None and console.address is None
    assert console.host == "127.0.0.1" and console.port == 8765
    assert not console.bridge.allowed and not game.commander_open
    console.pump(game)
    game.reset(32)
    game.load_state(game.save_state())
    assert game.commander is console and not console._prepared
    assert set(threading.enumerate()) == before
    console.stop()
    game.audio.shutdown()


def test_prepare_is_bounded_local_discovery_not_a_listener(monkeypatch):
    fcntl = pytest.importorskip("fcntl")
    probe = Mock()
    probe.__enter__ = Mock(return_value=probe)
    probe.__exit__ = Mock(return_value=False)
    factory = Mock(return_value=probe)
    monkeypatch.setattr(local.socket, "socket", factory)
    monkeypatch.setattr(local.socket, "if_nameindex", lambda: [(i, f"eth{i}") for i in range(100)])
    addresses = ("10.1.2.3", "192.168.2.3", "0.0.0.0", "8.8.8.8", "169.254.1.1")
    calls = []

    def ioctl(fd, operation, request):
        assert operation == 0x8915 and len(request) == 256
        address = addresses[len(calls) % len(addresses)]
        calls.append(request)
        return bytes(20) + socket.inet_aton(address) + bytes(232)

    monkeypatch.setattr(fcntl, "ioctl", ioctl)
    console = CommanderConsole()
    console.prepare()
    console.prepare()
    assert console.hosts == ("127.0.0.1", "10.1.2.3", "192.168.2.3")
    assert console.host == "127.0.0.1" and console.server is None
    assert len(calls) == 64
    factory.assert_called_once_with(socket.AF_INET, socket.SOCK_DGRAM)
    probe.__exit__.assert_called_once()


def test_prepare_failure_keeps_explicit_loopback(monkeypatch):
    monkeypatch.setattr(local.socket, "socket", Mock(side_effect=OSError("private detail")))
    console = CommanderConsole()
    console.prepare()
    assert console.hosts == ("127.0.0.1",) and console.error is None


def test_activation_prebuilds_contact_assets_once_on_calling_thread(monkeypatch):
    calls = []
    payload = {"/api/v1/contacts": ("application/json; charset=utf-8", b"{}")}

    def load_assets():
        calls.append(threading.get_ident())
        return payload

    class Server:
        connected = False
        pairing_code = "123ABC"

        def __init__(self, **kwargs):
            assert kwargs["contact_analysis_assets"] is payload
            self.address = None

        def start(self, host, port):
            self.address = (host, port)

        def stop(self):
            pass

    console = CommanderConsole()
    console._prepared = True
    console._translations = {"en": {}, "de": {}}
    monkeypatch.setattr(local, "load_contact_analysis_assets", load_assets)
    monkeypatch.setattr(local, "CommanderServer", Server)
    game = NS()
    console.activate(game)
    console.activate(game)
    console.activate(game)
    assert calls == [threading.get_ident()]
    assert console._contact_analysis_assets is payload


def test_options_six_and_f9_live_menu_ownership(game, monkeypatch):
    monkeypatch.setattr(game.commander, "prepare", Mock())
    key(game, pygame.K_F10)
    assert game.options_open
    for _ in range(5):
        key(game, pygame.K_DOWN)
    assert game.options_sel == 5
    key(game, pygame.K_RETURN)
    assert game.commander_open and game.administration_open and not game.options_open
    key(game, pygame.K_ESCAPE)
    assert not game.administration_open
    key(game, pygame.K_F9)
    assert game.commander_open
    key(game, pygame.K_F9)
    assert not game.commander_open
    game.in_menu = game.main_menu = True
    key(game, pygame.K_F9)
    assert game.commander_open and game.in_menu
    assert game.commander.server is None


@pytest.mark.parametrize("owner", ["editor", "input_mode", "options_open", "help_open",
                                    "nations_open", "save_ui", "quit_confirm", "splash_active"])
def test_f9_does_not_steal_existing_owner(game, owner):
    value = (NS(mode="browser", handle_event=Mock()) if owner == "editor" else
             "course" if owner == "input_mode" else "load" if owner == "save_ui" else True)
    setattr(game, owner, value)
    key(game, pygame.K_F9)
    assert not game.commander_open and game.commander.server is None
    if owner != "splash_active":
        assert getattr(game, owner) is value


def test_admin_blocks_held_mouse_joystick_weapons_and_simulation(game):
    game.commander._prepared = True
    game.held.add(pygame.K_LEFT)
    game._joy_turn = 1
    game._map_drag = (10, 20)
    key(game, pygame.K_F9)
    assert not game.held and game._joy_turn == 0 and game._map_drag is None
    before = game.ship.target_course, game.ship.target_speed, game.sim_t, game.station
    for event in (
        pygame.event.Event(pygame.JOYAXISMOTION, axis=0, value=1),
        pygame.event.Event(pygame.JOYBUTTONDOWN, button=0),
        pygame.event.Event(pygame.MOUSEWHEEL, y=1, x=0),
        pygame.event.Event(pygame.MOUSEMOTION, pos=(800, 500), rel=(50, 50), buttons=(1, 0, 0)),
    ):
        game.handle_event(event)
    key(game, pygame.K_3)
    key(game, pygame.K_LEFT)
    game.commander.selection = 5
    key(game, pygame.K_RETURN, mod=pygame.KMOD_CTRL)
    # Enter remains a local proposal decision, never station weapon input.
    assert game.commander.server is None
    game.update(.1)
    assert (game.ship.target_course, game.ship.target_speed, game.sim_t, game.station) == before
    assert not game.torpedoes and not game.held


def test_clicks_share_rows_and_reject_letterbox(game, monkeypatch):
    game.commander._prepared = True
    game._open_administration("options")
    monkeypatch.setattr(pygame.display, "get_window_size", lambda: (1280, 1000))
    rect = game._options_row_rects()[5]
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                        pos=(rect.centerx, 20)))
    assert game.options_open
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                        pos=(rect.centerx, rect.centery + 140)))
    assert game.commander_open
    activate = Mock()
    monkeypatch.setattr(game.commander, "activate", activate)
    rect = game.commander.row_rects()[5]
    event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                              pos=(rect.centerx, rect.centery + 140))
    game.handle_event(event)
    assert game.commander.selection == 5 and not activate.called
    game.handle_event(event)
    activate.assert_called_once_with(game)


def test_loopback_start_bind_failure_disable_and_translation_cache(game, monkeypatch):
    console = game.commander
    console._prepared = True
    console.port = 0
    calls = []

    def catalog(language):
        calls.append(language)
        return load_catalog(language)

    monkeypatch.setattr(local, "load_catalog", catalog)
    console.activate(game)
    assert console.error is None and console.address[0] == "127.0.0.1"
    assert console.address[1] > 0 and console.pairing_code
    with closing(http.client.HTTPConnection(*console.address, timeout=2)) as client:
        client.request("GET", "/api/v1/ui?lang=de")
        response = client.getresponse()
        translations = json.loads(response.read())
        assert response.status == 200
        assert translations and all(key.startswith("commander.web.") for key in translations)
    other = CommanderConsole()
    other._prepared = True
    other.port = console.address[1]
    other.activate(game)
    assert other.address is None and other.error == "commander.local.error.start"
    assert "127.0.0.1" not in other.error
    other.stop()
    host, port = console.host, console.port
    for selection in (1, 2):
        console.selection = selection
        console.activate(game)
    assert (console.host, console.port) == (host, port)
    console.selection = 0
    started = time.monotonic()
    console.activate(game)
    assert time.monotonic() - started < 3
    assert console.address is None and not console.connected and console.pairing_code is None
    assert not any(t.name.startswith("commander-") for t in threading.enumerate())
    calls.clear()
    console.activate(game)
    assert not calls and console.address is not None


def test_port_host_and_grant_are_transient_local_controls(game):
    console = game.commander
    console._prepared = True
    console.hosts = ("127.0.0.1", "192.168.1.2")
    console.selection = 1
    console.handle_key(game, pygame.K_RIGHT)
    assert console.host == "192.168.1.2"
    console.selection = 2
    console.handle_key(game, pygame.K_PLUS)
    assert console.port == 8766
    console.handle_key(game, pygame.K_MINUS)
    assert console.port == 8765
    console.port = 1024
    console.handle_key(game, pygame.K_MINUS)
    assert console.port == 1024
    console.port = 65535
    console.handle_key(game, pygame.K_PLUS)
    assert console.port == 65535
    console.selection = 3
    console.activate(game)
    assert not console.bridge.allowed
    saved = json.dumps(game.save_state())
    prefs = json.dumps(asdict(game.preferences))
    assert all(value not in saved + prefs for value in ("192.168.1.2", '"8765"', '"commander"'))


def test_owner_roundtrip_invalidates_queue_without_revoking_pair(game):
    console, server, contact = session(game)
    server.send("classify", value="U_BOOT")
    epoch = console.bridge.status["epoch"]
    key(game, pygame.K_F9)
    key(game, pygame.K_DOWN)
    key(game, pygame.K_ESCAPE)
    assert console.bridge.status["epoch"] == epoch + 2
    console.pump(game)
    assert contact.player_class is None
    assert server.state["results"][-1]["reasoncode"] == "stale_epoch"
    assert server.connected and server.revocations == 0
    console.selection = 3
    console.activate(game)
    assert not console.bridge.allowed and server.connected
    console.activate(game)
    assert console.bridge.allowed
    console.selection = 4
    console.activate(game)
    assert not console.bridge.allowed and not server.connected and server.revocations == 1


@pytest.mark.parametrize("accept", [True, False])
def test_pending_decision_requires_local_confirmation_preserves_focus(game, accept):
    console, server, contact = session(game)
    game.station = Station.SONAR
    selected = Contact(8, 7654322, "passiv", "sub")
    game.selected_contact = selected
    game.sonar.focus_locked = True
    game.sonar._listen_target_id = selected.target_id
    game.opz_selected_track_id = "selected-observation"
    server.send()
    console.pump(game)
    assert game.target is None
    key(game, pygame.K_F9)
    console.pump(game)
    console.selection = 5 if accept else 6
    key(game, pygame.K_RETURN)
    assert game.target is (contact if accept else None)
    assert console.bridge.proposal["status"] == ("accepted" if accept else "rejected")
    assert game.station is Station.SONAR and game.selected_contact is selected
    assert game.sonar.focus_locked and game.sonar._listen_target_id == selected.target_id
    assert game.opz_selected_track_id == "selected-observation"
    assert not game.torpedoes and game.commander_open


@pytest.mark.parametrize("kind,accept", [
    ("target", True), ("target", False), ("navigation", True), ("navigation", False),
])
def test_crew_message_box_single_proposal_decisions_are_local_and_non_pausing(
        game, kind, accept):
    console, server, contact = session(game)
    before_t = game.sim_t
    if kind == "target":
        server.send()
    else:
        server.send("propose_navigation", course=123.5, speed_kn=17.0)
    console.pump(game)

    assert console.confirm_visible(game) and console.confirm_kind == kind
    assert not game.paused and not game.administration_open
    game.update(.1)
    assert game.sim_t > before_t
    key(game, pygame.K_F6 if accept else pygame.K_F7)

    proposal = (console.bridge.proposal if kind == "target"
                else console.bridge.navigation_proposal)
    assert proposal["status"] == ("accepted" if accept else "rejected")
    assert not console.confirm_visible(game)
    assert game.target is (contact if kind == "target" and accept else None)
    if kind == "navigation" and accept:
        assert (game.ship.target_course, game.ship.target_speed) == (123.5, 17.0)


def test_crew_message_box_target_first_cycles_and_esc_suppresses_only_sequence(game):
    console, server, _ = session(game)
    server.send(identity="target")
    console.pump(game)
    server.send("propose_navigation", identity="navigation", course=222.0)
    console.pump(game)

    assert console.confirm_visible(game) and console.confirm_kind == "target"
    key(game, pygame.K_F8)
    assert console.confirm_kind == "navigation"
    key(game, pygame.K_F8)
    assert console.confirm_kind == "target"
    sequence = console.bridge.proposal_sequence
    key(game, pygame.K_ESCAPE)
    assert not console.confirm_visible(game)
    assert console.bridge.proposal["status"] == "pending"
    console.pump(game)
    assert not console.confirm_visible(game)

    game._open_administration("commander")
    assert console.bridge.reject_proposal(game)
    console.pump(game)
    game._open_administration("")
    console.pump(game)
    assert console.bridge.proposal_sequence == sequence
    assert console.confirm_visible(game) and console.confirm_kind == "navigation"


def test_crew_message_box_open_clears_controls_once_and_pause_blocks_decisions(
        game, monkeypatch):
    console, server, _ = session(game)
    clear = Mock(wraps=game._clear_controls)
    monkeypatch.setattr(game, "_clear_controls", clear)
    game.held.add(pygame.K_LEFT)
    game._joy_turn = 1
    game._map_drag = (10, 20)
    server.send()
    console.pump(game)
    console.pump(game)
    assert clear.call_count == 1
    assert not game.held and game._joy_turn == 0 and game._map_drag is None

    key(game, pygame.K_p)
    assert game.paused and console.confirm_visible(game)
    key(game, pygame.K_F6)
    assert console.bridge.proposal["status"] == "pending"
    key(game, pygame.K_p)
    key(game, pygame.K_F6)
    assert not game.paused and console.bridge.proposal["status"] == "accepted"


@pytest.mark.parametrize("owner,value", [
    ("in_menu", True), ("main_menu", True), ("editor", NS()),
    ("splash_active", True), ("game_over", True), ("help_open", True),
    ("commander_open", True),
])
def test_crew_message_box_hidden_behind_non_live_views(game, owner, value):
    console, server, _ = session(game)
    server.send()
    console.pump(game)
    assert console.confirm_visible(game)
    setattr(game, owner, value)
    assert not console.confirm_visible(game)


@pytest.mark.parametrize("change", [
    "grant", "revoke", "lease", "disconnect", "world", "expiry",
])
def test_crew_message_box_closes_on_authority_or_world_loss(game, change):
    console, server, _ = session(game)
    server.send()
    console.pump(game)
    assert console.confirm_visible(game)
    if change == "grant":
        console.bridge.allowed = False
    elif change == "revoke":
        server.revoke()
    elif change == "lease":
        server.lease_generation += 1
    elif change == "disconnect":
        server.connected = False
    elif change == "world":
        game.reset(32)
    else:
        game.sonar.contacts.clear()
        console.pump(game)
    assert not console.confirm_visible(game)
    console.pump(game)
    assert not console.confirm_visible(game)


def test_crew_message_box_same_sequence_does_not_return_after_local_regrant(game):
    console, server, _ = session(game)
    server.send()
    console.pump(game)
    assert console.confirm_visible(game)
    console.bridge.allowed = False
    assert not console.confirm_visible(game)
    console.bridge.allowed = True
    console.pump(game)
    assert not console.confirm_visible(game)


def test_crew_message_box_mouse_select_then_confirm_and_letterbox_rejection(game, monkeypatch):
    console, server, contact = session(game)
    server.send()
    console.pump(game)
    monkeypatch.setattr(pygame.display, "get_window_size", lambda: (1280, 1000))
    accept = console.confirm_button_rects()[0]

    game.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=(accept.centerx, 20)))
    assert game.target is None
    event = pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=(accept.centerx, accept.centery + 140))
    game.handle_event(event)
    assert game.target is None and console.confirm_visible(game)
    game.handle_event(event)
    assert game.target is contact and not console.confirm_visible(game)


def test_crew_message_box_only_consumes_clicks_inside_panel(game):
    console, server, _ = session(game)
    server.send()
    console.pump(game)

    assert not console.handle_confirm_click(game, (10, 10))
    assert console.handle_confirm_click(game, console.confirm_rect().center)


def test_notice_once_per_new_pending_with_wall_rate_limit(game, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(local.time, "monotonic", lambda: now[0])
    flash, alert = Mock(), Mock()
    monkeypatch.setattr(game, "flash", flash)
    monkeypatch.setattr(game.audio, "play_alert", alert)
    console, server, _ = session(game)
    assert not flash.called and not alert.called
    server.send()
    console.pump(game)
    for _ in range(10):
        console.pump(game)
    assert flash.call_count == alert.call_count == 1
    now[0] = 100.1
    server.send(identity="two")
    console.pump(game)
    assert flash.call_count == 1
    assert server.state["results"][-1]["reasoncode"] == "proposal_pending"
    game.commander_open = True
    assert console.bridge.reject_proposal(game)
    console.pump(game)
    game.commander_open = False
    console.pump(game)
    server.send(identity="three")
    console.pump(game)
    assert flash.call_count == 1
    now[0] = 102.0
    console.pump(game)
    console.pump(game)
    assert flash.call_count == alert.call_count == 2


def test_failed_candidate_load_never_touches_console_completed_load_waits_for_pump(game, monkeypatch):
    console, server, _ = session(game)
    server.send()
    console.pump(game)
    key(game, pygame.K_F9)
    data = game.save_state()
    before = console.bridge.status, console.bridge.proposal, server.revocations
    restore = Game._restore_state

    def fail_after_restore(candidate, state):
        restore(candidate, state)
        assert candidate.commander is console
        assert not candidate.commander_open
        raise ValueError("late failure after administration reset")

    monkeypatch.setattr(Game, "_restore_state", fail_after_restore)
    with pytest.raises(ValueError):
        game.load_state(data)
    assert (console.bridge.status, console.bridge.proposal, server.revocations) == before
    assert game.commander_open and server.connected and console.bridge.allowed
    monkeypatch.setattr(Game, "_restore_state", restore)
    game.load_state(data)
    assert game.commander is console and not game.commander_open
    assert (console.bridge.status, console.bridge.proposal, server.revocations) == before
    console.pump(game)
    assert server.revocations == before[2] + 1 and not console.bridge.allowed
    assert console.bridge.status["session"] != before[0]["session"]
    assert console.bridge.proposal is None


@pytest.mark.parametrize("fail", [False, True])
def test_run_pumps_before_update_even_paused_and_always_stops(game, monkeypatch, fail):
    order = []
    game.paused = True
    monkeypatch.setattr(pygame.event, "get", lambda: [])
    monkeypatch.setattr(game.commander, "pump", lambda current: order.append("pump"))
    monkeypatch.setattr(game.commander, "stop", lambda: order.append("stop"))
    monkeypatch.setattr(game, "draw", lambda: order.append("draw"))
    monkeypatch.setattr(game, "compose_frame", lambda: None)

    def update(dt, audio_dt=None):
        order.append("update")
        game.running = False
        if fail:
            raise RuntimeError("frame failure")

    monkeypatch.setattr(game, "update", update)
    if fail:
        with pytest.raises(RuntimeError, match="frame failure"):
            game.run()
        assert order == ["pump", "update", "stop"]
    else:
        game.run()
        assert order == ["pump", "update", "draw", "stop"]


@pytest.mark.parametrize("language", ["en", "de", "pseudo"])
@pytest.mark.parametrize("large", [False, True])
def test_options_and_commander_layout_bounds_no_draw_io(game, monkeypatch, language, large):
    game.preferences = replace(game.preferences, large_text=large)
    game.translator = (Translator("en", pseudolocale()) if language == "pseudo"
                       else Translator(language))
    game.tr = game.translator.t
    game._apply_text_size()
    console = game.commander
    console.address = ("192.168.100.200", 65535)
    console.pairing_code = "A" * 22
    console.bridge._proposal = dict(ref="ref", label="{authored} " + "K" * 128, status="pending")
    console.error = "commander.local.error.proposal"
    monkeypatch.setattr(local, "load_catalog", Mock(side_effect=AssertionError("draw I/O")))
    monkeypatch.setattr(local.socket, "socket", Mock(side_effect=AssertionError("draw socket")))
    with layout.capture_text() as text:
        game.draw_options_overlay()
        console.draw(game)
    canvas = pygame.Rect(0, 0, 1280, 720)
    assert text
    for entry in text:
        assert canvas.contains(entry["bounds"]), entry
        assert entry["bounds"].contains(entry["rect"]), entry
        assert "commander.local." not in entry["text"], entry
    for rows in (game._options_row_rects(), console.row_rects()):
        assert all(canvas.contains(row) for row in rows)
        assert all(a.bottom < b.top for a, b in zip(rows, rows[1:]))
    assert any(console.pairing_code in item["text"] for item in text)
    console.address = None


def test_bridge_translation_contract():
    suffixes = ("chart.disclaimer", "chart.omitted", "event.damage", "event.threat",
                "event.proposal.pending", "event.proposal.accepted", "event.proposal.rejected",
                "event.proposal.expired", "event.mission.warning_300", "event.mission.warning_120",
                "event.mission.warning_60", "event.mission.won", "event.mission.lost")
    for suffix in suffixes:
        key = "commander." + suffix
        en, de = Translator("en").t(key), Translator("de").t(key)
        assert en != key and de != key and en != de
