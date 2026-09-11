"""Main-thread Commander authority, bounded projection and observation boundary."""

from copy import deepcopy
from dataclasses import replace
import json
import math
import random
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace as NS

import pytest

from src.commander.bridge import CommanderBridge
from src.core import config
from src.core.game import Game
from src.core.i18n import Translator
from src.core.version import APP_VERSION
from src.sonar.sonar import Contact, SonarSystem


class Server:
    def __init__(self):
        self.connected = True
        self.lease = 1
        self.queue = []
        self.publications = []
        self.chart = None
        self.revocations = 0

    @property
    def lease_generation(self):
        return self.lease

    def publish(self, state, chart=None):
        json.dumps(state, allow_nan=False)
        if chart is not None:
            json.dumps(chart, allow_nan=False)
            self.chart = chart
        self.state = state
        self.publications.append((state, chart))

    def drain_commands(self, limit=4):
        assert limit == 4
        commands, self.queue = self.queue[:limit], self.queue[limit:]
        return commands

    def is_current(self, envelope):
        return self.connected and envelope["lease"] == self.lease

    def revoke(self):
        self.revocations += 1
        self.lease += 1
        self.connected = False
        self.queue.clear()

    def send(self, command, now=100.0, **changes):
        envelope = dict(command=command, received_at=now, lease=self.lease)
        envelope.update(changes)
        self.queue.append(envelope)


@pytest.fixture
def game():
    return Game(seed=31, start_menu=False, audio_enabled=False, language="en")


def observe(game, key="U-7654321", kind="UNKNOWN", source="SONAR-BRG", now=None):
    return game.air_picture.observe(
        track_id=key, kind=kind, target_id=int(key.split("-")[1]),
        source=source, bearing=90.0, range_nm=None,
        observer_x=game.ship.x, observer_y=game.ship.y, course=None,
        quality=.8, now=game.sim_t if now is None else now, label="K7")


def contact(game):
    c = Contact(7, 7654321, "passiv", "sub")
    c.update_passive(90.0, .8, .8, "", game.sim_t)
    game.sonar.contacts[c.target_id] = c
    observe(game)
    return c


def start(game, allowed=True):
    bridge, server = CommanderBridge(), Server()
    assert not bridge.allowed
    bridge.allowed = allowed
    bridge.pump(game, server, now=100.0)
    return bridge, server


def command(server, action="classify", value="U_BOOT", command_id="one", ref=None):
    state = server.state
    request = dict(id=command_id, session=state["session"], epoch=state["epoch"],
                   revision=state["revision"], action=action)
    if action != "clear_proposal" or ref is not None:
        request["track"] = ref or (state["tracks"][0]["ref"] if state["tracks"] else "missing")
    if action in ("classify", "affiliate"):
        request["value"] = value
    return request


def propose(game, bridge, server):
    server.send(command(server, "propose", None))
    bridge.pump(game, server, now=100.1)
    assert server.state["results"][-1]["status"] == "applied"
    assert bridge.proposal["status"] == "pending"


def test_exact_snapshot_shape_and_own_truth(game):
    contact(game)
    bridge, server = start(game)
    state = server.state
    assert set(state) == {"protocol", "version", "session", "epoch", "revision", "seq",
                          "phase", "commands_allowed", "language", "clock", "mission",
                          "ownship", "tracks", "crew_target", "proposal", "events",
                          "results", "chart_revision", "environment"}
    assert state["protocol"] == 1 and state["version"] == APP_VERSION
    assert state["commands_allowed"] is True and state["phase"] == "live"
    assert state["language"] == "en"
    assert set(state["clock"]) == {"sim", "mission", "time_scale", "world"}
    assert state["environment"] == {
        "sea_state": game.world.sea_state, "is_night": game.world.is_night()}
    assert set(state["mission"]) == {"name", "objective", "remaining_s"}
    assert set(state["ownship"]) == {"x", "y", "course", "speed", "target_course",
                                   "target_speed", "damage", "inventory", "helo"}
    assert state["ownship"]["x"] == game.ship.x
    assert set(state["ownship"]["damage"][0]) == {"key", "name", "state", "flood", "fire", "teams"}
    assert set(state["ownship"]["inventory"]) == {"torpedoes", "vls", "ciws", "chaff_ready"}
    assert set(state["ownship"]["helo"]) == {"state", "x", "y", "course", "fuel_s", "torpedoes", "buoys"}
    assert set(state["tracks"][0]) == {"ref", "label", "domain", "source", "affiliation",
        "classification", "bearing", "range_nm", "x", "y", "depth_m", "course", "speed_kn",
        "quality", "age_s", "fix_age_s", "bearing_uncertainty_deg", "range_uncertainty_nm",
        "fixes", "can_classify", "can_propose"}
    assert state["tracks"][0]["domain"] == "UNKNOWN"
    assert state["tracks"][0]["label"] == "C001"
    assert state["tracks"][0]["x"] is None
    assert set(server.chart) == {"revision", "size_nm", "landmasses", "disclaimer"}
    assert server.chart["revision"] == state["session"] == state["chart_revision"]
    assert all(set(land) == {"points"} for land in server.chart["landmasses"])
    encoded = json.dumps(state)
    assert "7654321" not in encoded
    assert all('"' + key + '"' not in encoded for key in ("target_id", "kind", "seed", "signature"))
    status = bridge.status
    status["epoch"] = -100
    assert bridge.status["epoch"] == state["epoch"]


def test_all_current_sonar_fixes_are_nested_detached_under_one_opaque_track(game):
    c = contact(game)
    c._publish_fix("PING", game.sim_t, game.sim_t, 10, 20, .2, .9, 80, 2)
    c._publish_fix("TMA", game.sim_t, game.sim_t, 11, 21, 2, .7)
    c._publish_fix("SONOBUOY", game.sim_t, game.sim_t, 12, 22, 1, .8)
    _, server = start(game)
    row = server.state["tracks"][0]
    assert [fix["source"] for fix in row["fixes"]] == [
        "PING", "TMA", "SONOBUOY"]
    assert all(set(fix) == {"source", "x", "y", "measured_at", "fixed_at",
                           "measurement_age_s", "fix_age_s", "uncertainty_nm",
                           "depth_m", "depth_uncertainty_m", "quality"}
               for fix in row["fixes"])
    assert "target_id" not in repr(row["fixes"])
    row["fixes"][0]["x"] = -1
    assert c.fixes["PING"]["x"] == 10


def test_wall_cadence_no_catchup_and_immediate_transitions(game):
    bridge, server = start(game)
    for now in (100.01, 100.1, 100.49):
        game.sim_t += 100
        bridge.pump(game, server, now=now)
    assert len(server.publications) == 1
    bridge.pump(game, server, now=100.5)
    assert len(server.publications) == 2
    assert server.publications[-1][1] is None
    bridge.pump(game, server, now=500.0)
    bridge.pump(game, server, now=500.01)
    assert len(server.publications) == 3
    game.paused = True
    bridge.pump(game, server, now=500.02)
    assert server.state["phase"] == "paused" and len(server.publications) == 4
    bridge.allowed = False
    bridge.pump(game, server, now=500.03)
    assert len(server.publications) == 5


@pytest.mark.parametrize(("hour", "night"), [
    (5.49, True), (5.5, False), (19.49, False), (19.5, True),
])
def test_environment_uses_authoritative_day_night_boundary(game, hour, night):
    game.world.hour = hour
    bridge, server = start(game)
    assert server.state["environment"] == {
        "sea_state": game.world.sea_state, "is_night": night}


@pytest.mark.parametrize(("field", "value", "phase"), [
    ("paused", True, "paused"), ("in_menu", True, "menu"), ("main_menu", True, "menu"),
    ("editor", object(), "blocked"), ("splash_active", True, "blocked"),
    ("running", False, "ended"), ("game_over", True, "ended"),
    ("help_open", True, "blocked"), ("nations_open", True, "blocked"),
    ("quit_confirm", True, "blocked"), ("save_ui", "load", "blocked"),
    ("options_open", True, "blocked"), ("input_mode", "course", "blocked"),
    ("commander_open", True, "blocked"),
])
def test_phase_transition_rejects_pretransition_commands(game, field, value, phase):
    c = contact(game)
    bridge, server = start(game)
    old = command(server)
    server.send(old)
    setattr(game, field, value)
    bridge.pump(game, server, now=100.1)
    assert server.state["phase"] == phase
    assert not server.state["commands_allowed"]
    assert server.state["epoch"] > old["epoch"]
    assert server.state["results"][-1]["reasoncode"] == "stale_epoch"
    assert c.player_class is None


def test_blocked_owner_switch_and_resume_both_invalidate(game):
    contact(game)
    bridge, server = start(game)
    game.help_open = True
    bridge.pump(game, server, now=100.1)
    previous = command(server)
    game.help_open, game.nations_open = False, True
    server.send(previous)
    bridge.pump(game, server, now=100.2)
    assert server.state["results"][-1]["reasoncode"] == "stale_epoch"
    previous = command(server, command_id="two")
    game.nations_open = False
    server.send(previous)
    bridge.pump(game, server, now=100.3)
    assert server.state["results"][-1]["reasoncode"] == "stale_epoch"


@pytest.mark.parametrize("gate", ["grant", "connection"])
def test_gate_required_even_with_current_epoch(game, gate):
    c = contact(game)
    bridge, server = start(game, allowed=gate != "grant")
    if gate == "connection":
        server.connected = False
        bridge.pump(game, server, now=100.01)
    server.send(command(server))
    bridge.pump(game, server, now=100.1)
    assert c.player_class is None
    assert server.state["results"][-1]["status"] == "rejected"


@pytest.mark.parametrize("replacement", ["world", "sonar", "load"])
def test_lifecycle_fresh_session_revokes_and_forgets(game, replacement):
    contact(game)
    bridge, server = start(game)
    propose(game, bridge, server)
    old_state = deepcopy(server.state)
    old_command = command(server, command_id="old")
    if replacement == "load":
        game.save_to_slot(1)
        assert game.load_from_slot(1)
    elif replacement == "world":
        game.world = deepcopy(game.world)
    else:
        game.sonar = SonarSystem(31)
    server.send(old_command)
    bridge.pump(game, server, now=100.2)
    assert server.revocations == 1
    assert not bridge.allowed and bridge.proposal is None
    assert server.state["session"] != old_state["session"]
    assert server.state["epoch"] > old_state["epoch"]
    assert not server.state["results"] and not server.state["events"]
    assert not bridge._ids
    assert server.chart["revision"] == server.state["session"]
    if server.state["tracks"]:
        assert server.state["tracks"][0]["ref"] != old_state["tracks"][0]["ref"]
    server.connected = bridge.allowed = True
    bridge.pump(game, server, now=100.3)
    server.send(old_command, now=100.3)
    bridge.pump(game, server, now=100.4)
    assert server.state["results"][-1]["reasoncode"] == "stale_session"


def test_candidate_creation_and_failed_load_do_not_revoke(game):
    bridge, server = start(game)
    candidate = Game(seed=62, audio_enabled=False)
    assert candidate.world is not game.world
    assert not game.load_from_slot(5)
    bridge.pump(game, server, now=100.1)
    assert server.revocations == 0 and bridge.allowed


@pytest.mark.parametrize("classification", [None, *config.PLAYER_CLASSES])
def test_exact_classification_without_focus_or_control_changes(game, classification):
    c = contact(game)
    c.player_class = "FAHRZEUG"
    game.sonar.focus_locked = True
    game.sonar.listen_bearing = 123
    bridge, server = start(game)
    revision = server.state["revision"]
    server.send(command(server, value=classification))
    bridge.pump(game, server, now=100.1)
    assert c.player_class == classification
    assert game.target is game.selected_contact is None
    assert game.sonar.focus_locked and game.sonar.listen_bearing == 123
    assert server.state["results"][-1] == dict(id="one", status="applied", reasoncode="ok")
    assert server.state["revision"] == revision + (classification != "FAHRZEUG")
    assert server.state["tracks"][0]["classification"] == classification


@pytest.mark.parametrize("affiliation", config.NATO_AFFILIATIONS)
def test_exact_affiliation_on_public_nonsonar_track(game, affiliation):
    observe(game, "A-7654321", "FLG", "RADAR-L")
    bridge, server = start(game)
    revision = server.state["revision"]
    server.send(command(server, "affiliate", affiliation))
    bridge.pump(game, server, now=100.1)
    assert game.opz_affiliation("A-7654321") == affiliation
    assert game.opz_selected_track_id is None
    assert server.state["revision"] == revision + (affiliation != "UNKNOWN")
    assert server.state["tracks"][0]["affiliation"] == affiliation


@pytest.mark.parametrize("changes", [
    {"action": "fire"}, {"value": "sub"}, {"value": []}, {"value": 1},
    {"epoch": True}, {"revision": -1}, {"revision": 2**60}, {"id": ""},
    {"id": "a" * 65}, {"session": "a" * 65}, {"track": "a" * 65},
    {"session": []}, {"track": {}}, {"unexpected": 1},
    {"action": "propose", "value": "U_BOOT"}, {"action": "affiliate", "value": None},
    {"action": "propose", "value": None}, {"action": "clear_proposal", "value": None},
    {"track": None},
])
def test_strict_schema_even_with_fake_transport(game, changes):
    c = contact(game)
    bridge, server = start(game)
    request = command(server)
    request.update(changes)
    server.send(request)
    bridge.pump(game, server, now=100.1)
    assert server.state["results"][-1]["reasoncode"] == "invalid_schema"
    assert c.player_class is None


@pytest.mark.parametrize("changes", [
    {"lease": 2}, {"lease": True}, {"received_at": 94.9}, {"received_at": 101},
    {"received_at": None}, {"received_at": float("nan")}, {"received_at": 10**400},
    {"extra": True},
])
def test_authentication_and_monotonic_ttl_checked_in_bridge(game, changes):
    c = contact(game)
    bridge, server = start(game)
    server.send(command(server), **changes)
    bridge.pump(game, server, now=100.1)
    assert server.state["results"][-1]["reasoncode"] == "unauthorized"
    assert c.player_class is None


def test_dedup_conflicts_and_local_annotation_revision_before_commands(game):
    c = contact(game)
    bridge, server = start(game)
    request = command(server)
    server.send(request)
    bridge.pump(game, server, now=100.1)
    revision = server.state["revision"]
    server.send(request)
    bridge.pump(game, server, now=100.2)
    assert server.state["revision"] == revision
    assert server.state["results"][-1]["status"] == "applied"
    server.send(dict(request, value="BIOLOGISCH"))
    bridge.pump(game, server, now=100.3)
    assert server.state["results"][-1]["reasoncode"] == "duplicate_id"
    stale = command(server, command_id="local-conflict")
    c.player_class = "BIOLOGISCH"
    server.send(stale)
    bridge.pump(game, server, now=100.4)
    assert server.state["revision"] > revision
    assert server.state["results"][-1]["reasoncode"] == "revision_conflict"
    assert c.player_class == "BIOLOGISCH"
    stale = command(server, command_id="affiliation-conflict")
    game.opz_affiliations["U-7654321"] = "FRIEND"
    server.send(stale)
    bridge.pump(game, server, now=100.45)
    assert server.state["results"][-1]["reasoncode"] == "revision_conflict"


def test_local_crew_target_changes_revision(game):
    c = contact(game)
    bridge, server = start(game)
    server.send(command(server))
    game.target = c
    bridge.pump(game, server, now=100.1)
    assert server.state["results"][-1]["reasoncode"] == "revision_conflict"
    assert server.state["crew_target"] == server.state["tracks"][0]["ref"]


def test_four_command_cap_and_bounded_dedup_results(game):
    contact(game)
    bridge, server = start(game)
    for i in range(140):
        server.send(command(server, command_id=str(i)))
    bridge.pump(game, server, now=100.1)
    assert len(server.queue) == 136 and len(server.state["results"]) == 4
    for i in range(34):
        bridge.pump(game, server, now=100.2 + i / 100)
    assert not server.queue
    assert len(bridge._ids) == 128 and len(server.state["results"]) == 32


@pytest.mark.parametrize("prefix,kind,source", [
    ("A", "FLG", "RADAR-L"), ("M", "ASM", "HOJ"), ("S", "SURFACE", "RADAR-S"),
    ("W", "SURFACE", "RADAR-S"), ("H", "SUB", "HFDF-FIX"),
    ("U", "UNKNOWN", "RADAR-S"),
])
def test_numeric_id_never_cross_associates_namespaces(game, prefix, kind, source):
    c = contact(game)
    game.air_picture._tracks.clear()
    observe(game, f"{prefix}-7654321", kind, source)
    bridge, server = start(game)
    row = server.state["tracks"][0]
    assert not row["can_classify"] and not row["can_propose"]
    for index, action in enumerate(("classify", "propose")):
        server.send(command(server, action, "U_BOOT" if action == "classify" else None,
                            command_id=str(index)))
        bridge.pump(game, server, now=100.1 + index / 100)
        assert server.state["results"][-1]["reasoncode"] == "ineligible_track"
    assert c.player_class is None and bridge.proposal is None


def test_proposal_accept_local_overlay_only_changes_target(game):
    c = contact(game)
    bridge, server = start(game)
    game.sonar.focus_locked = True
    game.sonar.listen_bearing = 271
    propose(game, bridge, server)
    detached = bridge.proposal
    detached["status"] = "accepted"
    assert bridge.proposal["status"] == "pending" and game.target is None
    game.commander_open = True
    bridge.pump(game, server, now=100.2)
    assert not server.state["commands_allowed"]
    assert bridge.accept_proposal(game)
    assert game.target is c and game.selected_contact is None
    assert game.sonar.focus_locked and game.sonar.listen_bearing == 271
    assert bridge.proposal["status"] == "accepted"
    assert not bridge.accept_proposal(game)
    bridge.pump(game, server, now=100.3)
    assert server.state["crew_target"] == bridge.proposal["ref"]


@pytest.mark.parametrize("field,value", [
    ("paused", True), ("in_menu", True), ("editor", object()), ("game_over", True),
    ("splash_active", True), ("running", False), ("input_mode", "speed"),
    ("help_open", True), ("save_ui", "save"),
])
def test_local_decisions_block_other_owners(game, field, value):
    contact(game)
    bridge, server = start(game)
    propose(game, bridge, server)
    game.commander_open = True
    setattr(game, field, value)
    assert not bridge.accept_proposal(game) and not bridge.reject_proposal(game)
    assert game.target is None


@pytest.mark.parametrize("loss", ["stale", "replaced", "missing", "world"])
def test_accept_revalidates_without_waiting_for_pump(game, loss):
    c = contact(game)
    bridge, server = start(game)
    propose(game, bridge, server)
    if loss == "stale":
        game.sim_t += config.SONAR_CONTACT_LOST_S
    elif loss == "replaced":
        game.sonar.contacts[c.target_id] = deepcopy(c)
    elif loss == "missing":
        game.sonar.contacts.clear()
    else:
        game.world = deepcopy(game.world)
    assert not bridge.accept_proposal(game)
    assert game.target is None


def test_reject_clear_and_omitted_unused_command_fields(game):
    contact(game)
    bridge, server = start(game)
    request = command(server, "propose", None)
    assert "value" not in request
    server.send(request)
    bridge.pump(game, server, now=100.1)
    assert bridge.reject_proposal(game)
    assert bridge.proposal["status"] == "rejected" and game.target is None
    bridge.pump(game, server, now=100.2)
    clear = command(server, "clear_proposal", None, command_id="clear")
    assert "track" not in clear and "value" not in clear
    server.send(clear)
    bridge.pump(game, server, now=100.3)
    assert bridge.proposal is None
    assert server.state["results"][-1]["status"] == "applied"


def test_fresh_target_proposal_cannot_replace_pending_and_duplicate_replays(game):
    first = contact(game)
    second = Contact(8, 7654322, "passiv", "sub")
    second.update_passive(120.0, .8, .8, "", game.sim_t)
    game.sonar.contacts[second.target_id] = second
    observe(game, "U-7654322")
    bridge, server = start(game)
    original = command(server, "propose", None)
    server.send(original)
    bridge.pump(game, server, now=100.1)
    pending = bridge.proposal
    revision = server.state["revision"]

    server.send(original)
    bridge.pump(game, server, now=100.2)
    assert server.state["results"][-1] == dict(id="one", status="applied", reasoncode="ok")
    assert bridge.proposal == pending and server.state["revision"] == revision

    second_ref = next(row["ref"] for row in server.state["tracks"]
                      if row["ref"] != pending["ref"])
    server.send(command(server, "propose", None, command_id="two", ref=second_ref))
    bridge.pump(game, server, now=100.3)
    assert server.state["results"][-1] == dict(
        id="two", status="rejected", reasoncode="proposal_pending")
    assert bridge.proposal == pending and bridge._proposal_contact is first


def test_same_batch_target_replacement_reports_pending_not_revision(game):
    first = contact(game)
    second = Contact(8, 7654322, "passiv", "sub")
    second.update_passive(120.0, .8, .8, "", game.sim_t)
    game.sonar.contacts[second.target_id] = second
    observe(game, "U-7654322")
    bridge, server = start(game)
    refs = [row["ref"] for row in server.state["tracks"] if row["can_propose"]]

    server.send(command(server, "propose", None, command_id="first", ref=refs[0]))
    server.send(command(server, "propose", None, command_id="second", ref=refs[1]))
    bridge.pump(game, server, now=100.1)

    assert [result["reasoncode"] for result in server.state["results"][-2:]] == [
        "ok", "proposal_pending"]
    assert bridge._proposal_contact in (first, second)


@pytest.mark.parametrize("revoke", ["grant", "connection"])
def test_local_decisions_recheck_revocation_before_next_pump(game, revoke):
    contact(game)
    bridge, server = start(game)
    propose(game, bridge, server)
    if revoke == "grant":
        bridge.allowed = False
    else:
        server.revoke()
    assert not bridge.accept_proposal(game) and not bridge.reject_proposal(game)
    bridge.pump(game, server, now=100.2)
    assert bridge.proposal["status"] == "expired"
    assert game.target is None


def test_alarm_sequence_remains_monotonic_after_world_transition(game):
    bridge, server = start(game)
    game.damage.compartments["engine"].fire = 10
    bridge.pump(game, server, now=100.1)
    previous = server.state["events"][-1]["seq"]
    game.world = deepcopy(game.world)
    bridge.pump(game, server, now=100.2)
    assert server.state["events"] == []
    game.damage.compartments["engine"].fire = 0
    bridge.pump(game, server, now=100.3)
    assert server.state["events"][-1]["seq"] > previous


@pytest.mark.parametrize("source", ["ping", "tma", "buoy"])
@pytest.mark.parametrize("evidence", ["fresh", "missing", "future", "expired"])
def test_sonar_fix_evidence_never_falls_back_to_last_seen_or_mirrored_fix(game, source, evidence):
    game.sim_t = 300.0
    c = contact(game)
    c.range_source, c.range_est, c.range_sigma_nm = source, 12.0, .3
    c.observed_x, c.observed_y, c.depth_est = 123.0, 124.0, 60.0
    c.tma_course, c.tma_speed, c.tma_quality = 42.0, 9.0, 1.0
    lifetime = config.SONAR_PING_FIX_MAX_AGE_S if source == "ping" else config.SONAR_CONTACT_LOST_S
    c.range_seen = {"fresh": 299, "missing": None, "future": 301,
                    "expired": 300 - lifetime - .01}[evidence]
    c.tma_seen = 299 if evidence == "fresh" else None
    mirrored = game.opz_tracks()[0]
    mirrored.source, mirrored.range_nm = "SONAR-" + source.upper(), 999.0
    mirrored.x, mirrored.y, mirrored.course, mirrored.position_seen = 999.0, 999.0, 999.0, 300.0
    before = deepcopy(c.__dict__)
    bridge, server = start(game)
    row = server.state["tracks"][0]
    assert c.__dict__ == before
    assert row["age_s"] == 0
    if evidence == "fresh":
        assert (row["x"], row["y"], row["fix_age_s"]) == (123, 124, 1)
        assert row["range_nm"] == pytest.approx(math.hypot(123 - game.ship.x, 124 - game.ship.y))
        assert row["source"] == "SONAR-" + source.upper()
        assert row["course"] == 42 and row["speed_kn"] == 9
        assert row["depth_m"] == (60 if source == "ping" else None)
    else:
        assert all(row[key] is None for key in ("range_nm", "x", "y", "depth_m", "course", "speed_kn"))
        assert row["source"] == "SONAR-BRG"


def test_missing_sonar_association_does_not_use_public_mirror_fix(game):
    observed = observe(game, source="SONAR-PING")
    observed.range_nm, observed.x, observed.y, observed.position_seen = 12, 30, 40, 0
    bridge, server = start(game)
    row = server.state["tracks"][0]
    assert row["x"] is None and row["range_nm"] is None and not row["can_propose"]


def test_public_radar_position_timestamp_and_hfdf_bearing_only(game):
    game.sim_t = 100
    t = observe(game, "A-1", "FLG", "ESM")
    t.x, t.y, t.range_nm, t.course = 31, 32, 12, 90
    t.position_seen = 100 - config.RADAR_TRACK_STALE_S - 1
    game.radio_picture.observe(track_id="H-5", kind="HF", target_id=5, source="HFDF",
        bearing=123, range_nm=None, observer_x=0, observer_y=0, course=None,
        quality=.5, now=0, label="SIG-05")
    bridge, server = start(game)
    radar, radio = server.state["tracks"]
    assert radar["x"] is None and radar["course"] is None
    assert radar["fix_age_s"] == config.RADAR_TRACK_STALE_S + 1
    assert radio["bearing"] == 123 and radio["age_s"] == 100
    assert radio["domain"] == "UNKNOWN" and radio["x"] is None
    t.position_seen = 99
    bridge.pump(game, server, now=100.5)
    assert server.state["tracks"][0]["x"] == 31


def test_future_observations_omitted_and_registry_bounded(game):
    for index in range(400):
        observe(game, f"A-{index}", "FLG", "RADAR-L")
    future = observe(game, "A-99999", "FLG", "RADAR-L", now=100)
    bridge, server = start(game)
    assert len(server.state["tracks"]) == len(bridge._refs) == 256
    assert bridge._label_seq == 256
    assert future.track_id not in bridge._refs
    game.sim_t = config.RADAR_TRACK_STALE_S + 1
    bridge.pump(game, server, now=100.5)
    assert server.state["tracks"] == [] and not bridge._refs


def test_chart_cached_and_oversized_or_invalid_chart_explicitly_omitted(game):
    bridge, server = start(game)
    first = deepcopy(server.chart)
    game.world.coast.landmasses = [NS(points=[(float("nan"), 0)] * 3)]
    bridge.pump(game, server, now=101)
    assert server.chart == first
    for points in ([(0, 0)] * 20001, [(float("nan"), 0)] * 3):
        game.world = deepcopy(game.world)
        game.world.coast.landmasses = [NS(points=points)]
        bridge.pump(game, server, now=102)
        assert server.chart["landmasses"] == []
        assert server.chart["disclaimer"] == game.tr("commander.chart.omitted")


def test_public_events_baseline_bounds_and_locale_change(game):
    bridge, server = start(game)
    assert not server.state["events"]
    room = game.damage.compartments["engine"]
    for i in range(140):
        room.fire = (i % 2) * 10
        bridge.pump(game, server, now=100.1 + i / 100)
    assert len(server.state["events"]) == 128
    last = server.state["events"][-1]["seq"]
    observe(game, "M-1", "ASM", "HOJ")
    bridge.pump(game, server, now=102)
    event = server.state["events"][-1]
    assert set(event) == {"seq", "kind", "severity", "message"}
    assert event["kind"] == "threat" and event["seq"] == last + 1
    bridge.pump(game, server, now=103)
    assert server.state["events"][-1]["seq"] == event["seq"]
    game.preferences = replace(game.preferences, language="de")
    game.tr = Translator("de").t
    bridge.pump(game, server, now=103.01)
    assert server.state["language"] == "de"
    assert server.state["ownship"]["damage"][0]["name"] == game.tr("compartment.bridge")


@pytest.mark.parametrize("kind", ["ASM", "TORP"])
def test_hidden_weapon_kind_cannot_raise_threat_without_public_evidence(game, kind):
    bridge, server = start(game)
    observe(game, "M-1", kind, "RADAR-L")
    bridge.pump(game, server, now=100.1)
    assert server.state["events"] == []
    assert '"kind"' not in json.dumps(server.state["tracks"])

    server.send(command(server, "affiliate", "HOSTILE"))
    bridge.pump(game, server, now=100.2)
    assert server.state["events"][-1]["kind"] == "threat"


def test_polling_hidden_truth_traps_and_detached_publications(game, monkeypatch):
    contact(game)
    before = game.save_state()

    def forbidden(*args, **kwargs):
        raise AssertionError("hidden truth or mutating helper accessed")

    class Trap:
        __iter__ = __getattr__ = __len__ = forbidden

    with monkeypatch.context() as patch:
        for name in ("subs", "animals", "civilians", "warships", "asms", "flights",
                     "enemy_torpedoes", "feed", "messages"):
            patch.setattr(game, name, Trap())
        for name in ("save_state", "_find_target", "designate_opz_track",
                     "set_target", "_cycle_classification", "_cycle_opz_affiliation"):
            patch.setattr(game, name, forbidden)
        patch.setattr(Contact, "expire_ping_fix", forbidden)
        # Contact.kind/signature are hidden; public SensorTrack.kind is an observation.
        patch.setattr(Contact, "kind", property(forbidden), raising=False)
        patch.setattr(Contact, "signature", property(forbidden), raising=False)
        bridge, server = start(game)
        for i in range(90):
            bridge.pump(game, server, now=100.1 + i / 60)
        server.state["tracks"][0]["classification"] = "BIOLOGISCH"
        server.state["ownship"]["damage"][0]["teams"].append(999)
        server.chart["landmasses"].clear()
    assert game.save_state() == before


def test_polling_does_not_change_deterministic_continuation(game):
    before = game.save_state()
    rng = random.getstate()
    bridge, server = start(game)
    for i in range(30):
        bridge.pump(game, server, now=100 + i / 60)
    assert game.save_state() == before and random.getstate() == rng
    game.save_to_slot(1)
    for _ in range(10):
        game.update(1 / 60)
    expected = game.save_state()
    assert game.load_from_slot(1)
    for i in range(10):
        bridge.pump(game, server, now=101 + i / 60)
        game.update(1 / 60)
    assert game.save_state() == expected


def test_only_main_thread_may_access_game(game):
    bridge, server = start(game)
    with ThreadPoolExecutor(max_workers=1) as executor:
        for method, args in ((bridge.pump, (game, server)),
                             (bridge.accept_proposal, (game,)),
                             (bridge.reject_proposal, (game,))):
            with pytest.raises(RuntimeError, match="main thread"):
                executor.submit(method, *args).result()


@pytest.mark.parametrize("replacement", ["track", "contact"])
def test_reincarnation_between_pumps_rotates_reference_and_expires_proposal(game, replacement):
    c = contact(game)
    bridge, server = start(game)
    propose(game, bridge, server)
    old_ref = bridge.proposal["ref"]
    old_label = bridge.proposal["label"]
    old_revision = server.state["revision"]
    request = command(server, command_id="before-replacement")
    original = game.opz_tracks()[0]
    if replacement == "track":
        new = deepcopy(original)
        assert new == original and new is not original
        game.air_picture._tracks[original.track_id] = new
    else:
        game.sonar.contacts[c.target_id] = deepcopy(c)
    server.send(request)
    bridge.pump(game, server, now=100.2)
    row = server.state["tracks"][0]
    assert row["ref"] != old_ref
    assert row["label"] != old_label
    assert server.state["revision"] > old_revision
    assert bridge.proposal == dict(ref=old_ref, label=old_label, status="expired")
    assert server.state["results"][-1]["reasoncode"] == "revision_conflict"
    assert not bridge.accept_proposal(game)
    server.send(command(server, ref=old_ref, command_id="old-reference"))
    bridge.pump(game, server, now=100.3)
    assert server.state["results"][-1]["reasoncode"] == "unknown_track"
    assert game.target is None and c.player_class is None
    assert game.sonar.contacts[c.target_id].player_class is None
    assert bridge._refs[original.track_id][0] is game.opz_tracks()[0]
    assert bridge._refs[original.track_id][1] is game.sonar.contacts[c.target_id]
    assert json.loads(json.dumps(server.state)) == server.state


def test_replaced_track_invalidates_local_accept_without_pump(game):
    contact(game)
    bridge, server = start(game)
    propose(game, bridge, server)
    old = game.opz_tracks()[0]
    game.air_picture._tracks[old.track_id] = deepcopy(old)
    assert not bridge.accept_proposal(game)
    assert bridge.proposal["status"] == "expired" and game.target is None


@pytest.mark.parametrize("field", ["in_menu", "main_menu", "editor", "splash_active"])
@pytest.mark.parametrize("initial", [True, False])
def test_status_only_schema_never_reads_tactical_or_pregenerated_data(game, monkeypatch, field, initial):
    contact(game)
    if initial:
        bridge, server = CommanderBridge(), Server()
        bridge.allowed = True
    else:
        bridge, server = start(game)
        propose(game, bridge, server)
        server.send(command(server, command_id="redacted-command"))
    before = game.save_state()

    def forbidden(*args, **kwargs):
        raise AssertionError("status-only projection accessed tactical data")

    class Trap:
        __getattr__ = __iter__ = __len__ = forbidden

    with monkeypatch.context() as patch:
        patch.setattr(game, field, object() if field == "editor" else True)
        for name in ("ship", "helo", "mission", "damage", "sim_t", "mission_time", "mission_result"):
            patch.setattr(game, name, Trap())
        for name in ("coast", "hour", "size_nm", "sea_state", "is_night"):
            patch.setattr(game.world, name, Trap())
        patch.setattr(game.sonar, "contacts", Trap())
        for name in ("opz_tracks", "hfdf_bearings", "mission_name_display", "mission_objective_display"):
            patch.setattr(game, name, forbidden)
        patch.setattr(bridge, "_build_chart", forbidden)
        bridge.pump(game, server, now=100.2)
        state = server.state
        expected_results = ([] if initial else [dict(id="one", status="applied", reasoncode="ok"),
            dict(id="redacted-command", status="rejected", reasoncode="stale_epoch")])
        assert state == dict(
            protocol=1, version=APP_VERSION, session=bridge.status["session"],
            epoch=bridge.status["epoch"], revision=bridge.status["revision"], seq=bridge.status["seq"],
            phase="menu" if field in ("in_menu", "main_menu") else "blocked",
            commands_allowed=False, language="en",
            clock=dict(sim=None, mission=None, time_scale=None, world=None),
            environment=dict(sea_state=None, is_night=None),
            mission=dict(name="", objective="", remaining_s=None),
            ownship=dict(x=None, y=None, course=None, speed=None, target_course=None, target_speed=None,
                         damage=[], inventory=dict(torpedoes=None, vls=None, ciws=None, chaff_ready=None),
                         helo=dict(state=None, x=None, y=None, course=None, fuel_s=None, torpedoes=None, buoys=None)),
            tracks=[], crew_target=None, proposal=None, events=[], results=expected_results,
            chart_revision=bridge.status["session"])
        assert server.chart == dict(revision=state["session"], size_nm=500, landmasses=[], disclaimer="")
        assert bridge.proposal is None and not bridge._refs
        if initial:
            assert bridge._chart is None
        bridge.pump(game, server, now=100.7)
        assert server.publications[-1][1] is None
    assert game.save_state() == before
    bridge.pump(game, server, now=100.8)
    assert server.publications[-1][1] is not None
    assert server.chart["revision"] == state["session"]
    assert server.chart["landmasses"]
    assert server.state["ownship"]["x"] == game.ship.x and server.state["tracks"]


@pytest.mark.parametrize("field,value", [("paused", True), ("help_open", True),
                                         ("save_ui", "save"), ("commander_open", True)])
def test_pause_and_administration_keep_read_only_observed_picture(game, field, value):
    contact(game)
    bridge, server = start(game)
    previous = deepcopy(server.state)
    chart = deepcopy(server.chart)
    setattr(game, field, value)
    before = game.save_state()
    bridge.pump(game, server, now=100.1)
    assert game.save_state() == before
    assert not server.state["commands_allowed"]
    for key in ("tracks", "ownship", "clock", "environment", "mission"):
        assert server.state[key] == previous[key]
    assert server.chart == chart


@pytest.mark.parametrize("sonar", [False, True])
def test_position_uses_current_ship_and_late_ping_source_without_stale_motion(game, sonar):
    game.ship.x = game.ship.y = 100
    if sonar:
        c = contact(game)
        c._fx = c._fy = 100
    else:
        t = observe(game, "A-1", "FLG", "RADAR-L")
    bridge, server = start(game)
    old_ref, revision = server.state["tracks"][0]["ref"], server.state["revision"]
    if sonar:
        c.update_ping(90, 10, 60, 1, game.sim_t)
        c.tma_course, c.tma_speed, c.tma_quality = 222, 9, 1
        c.tma_seen = None
        assert game.opz_tracks()[0].source == "SONAR-BRG"
    else:
        t.x, t.y, t.position_seen = 110, 100, game.sim_t
        t.bearing, t.range_nm, t.course = 90, 10, 222
    game.ship.x, game.ship.y = 107, 104
    before = game.save_state()
    bridge.pump(game, server, now=100.5)
    row = server.state["tracks"][0]
    assert row["ref"] == old_ref
    assert row["range_nm"] == pytest.approx(5)
    assert row["bearing"] == pytest.approx(math.degrees(math.atan2(3, 4)))
    assert row["source"] == ("SONAR-PING" if sonar else "RADAR-L")
    assert row["course"] == (None if sonar else 222)
    assert row["depth_m"] == (60 if sonar else None)
    assert server.state["revision"] == revision + sonar
    assert game.save_state() == before
    revision = server.state["revision"]
    game.ship.x += 1
    bridge.pump(game, server, now=101)
    assert server.state["tracks"][0]["range_nm"] == pytest.approx(math.hypot(2, 4))
    assert server.state["revision"] == revision
    game.sim_t = max(config.SONAR_CONTACT_LOST_S, config.SONAR_PING_FIX_MAX_AGE_S,
                     config.RADAR_TRACK_STALE_S) + 1
    game.opz_tracks()  # Merely polling must not expire/replace the object.
    stored = game.air_picture._tracks["U-7654321" if sonar else "A-1"]
    stored.last_seen = game.sim_t
    if sonar:
        c.last_seen = game.sim_t
        c.tma_seen = 0
    bridge.pump(game, server, now=101.5)
    row = server.state["tracks"][0]
    assert all(row[key] is None for key in ("x", "y", "range_nm", "course", "speed_kn", "depth_m"))
    if sonar:
        assert row["source"] == "SONAR-BRG" and server.state["revision"] == revision + 1


def test_observation_domain_enum_changes_revision_not_reference(game):
    t = observe(game, "A-1", "UNKNOWN", "RADAR-L")
    bridge, server = start(game)
    ref, revision = server.state["tracks"][0]["ref"], server.state["revision"]
    t.kind = "FLG"
    bridge.pump(game, server, now=100.1)
    assert server.state["tracks"][0]["domain"] == "AIR"
    assert server.state["tracks"][0]["ref"] == ref
    assert server.state["revision"] == revision + 1


def test_status_getter_is_detached_and_never_polls_game_or_server(game):
    bridge, server = start(game)
    expected = bridge.status
    before = game.save_state()

    class Trap:
        def __getattr__(self, name):
            raise AssertionError("status getter polled transport")

    bridge._server = Trap()
    for _ in range(10):
        returned = bridge.status
        assert returned == expected
        returned["commands_allowed"] = False
        returned["extra"] = object()
    assert game.save_state() == before
    assert set(bridge.status) == {"phase", "connected", "commands_allowed", "session", "epoch", "revision", "seq"}


@pytest.mark.parametrize("threshold", [300, 120, 60])
def test_known_mission_deadline_crossing_emits_once_without_poll_replays(game, threshold):
    game.mission.time_limit_s = 600
    game.mission_time = 600 - threshold - .1
    bridge, server = start(game)
    assert not server.state["events"]
    game.mission_time += .1
    bridge.pump(game, server, now=100.1)
    event = server.state["events"][-1]
    assert event == dict(seq=1, kind="mission", severity="warning",
                         message=game.tr(f"commander.event.mission.warning_{threshold}"))
    for i in range(10):
        bridge.pump(game, server, now=100.2 + i / 10)
    assert server.state["events"] == [event]
    game.mission_time -= 1
    bridge.pump(game, server, now=102)
    game.mission_time += 1
    bridge.pump(game, server, now=103)
    assert server.state["events"] == [event]


@pytest.mark.parametrize("result,key,severity", [("SIEG", "won", "info"), ("VERLOREN", "lost", "warning")])
def test_known_mission_result_only_emits_on_transition(game, result, key, severity):
    bridge, server = start(game)
    game.mission_result, game.game_over = result, True
    bridge.pump(game, server, now=100.1)
    event = server.state["events"][-1]
    assert event["kind"] == "mission" and event["severity"] == severity
    assert event["message"] == game.tr("commander.event.mission." + key)
    assert server.state["phase"] == "ended"
    bridge.pump(game, server, now=101)
    assert server.state["events"] == [event]
    game.world = deepcopy(game.world)
    bridge.pump(game, server, now=102)
    assert server.state["events"] == []


def test_mission_warning_skips_historical_stack_and_unknown_result(game):
    game.mission.time_limit_s = 600
    bridge, server = start(game)
    game.mission_time = 550
    bridge.pump(game, server, now=100.1)
    assert len(server.state["events"]) == 1
    assert server.state["events"][0]["message"] == game.tr("commander.event.mission.warning_60")
    game.mission_result = "not-a-public-result"
    bridge.pump(game, server, now=101)
    assert len(server.state["events"]) == 1
    fresh, other = start(game)
    assert other.state["events"] == []


def test_threat_refs_and_alarm_ids_stable_during_polling_and_in_place_updates(game):
    bridge, server = start(game)
    t = observe(game, "M-1", "ASM", "HOJ")
    bridge.pump(game, server, now=100.1)
    ref = server.state["tracks"][0]["ref"]
    event = deepcopy(server.state["events"])
    for i in range(10):
        t.bearing += 1
        t.quality -= .01
        bridge.pump(game, server, now=100.2 + i / 10)
        assert server.state["tracks"][0]["ref"] == ref
        assert server.state["events"] == event


def test_command_id_accepts_exactly_64_characters(game):
    contact(game)
    bridge, server = start(game)
    request = command(server, command_id="a" * 64)
    server.send(request)
    bridge.pump(game, server, now=100.1)
    assert server.state["results"][-1] == dict(id="a" * 64, status="applied", reasoncode="ok")


def test_repair_between_pumps_revokes_grant_even_when_connected_stays_true(game):
    c = contact(game)
    bridge, server = start(game)
    propose(game, bridge, server)
    previous_epoch = server.state["epoch"]
    server.lease += 1
    assert server.connected and not bridge.allowed
    server.send(command(server, command_id="new-client"))
    bridge.pump(game, server, now=100.2)
    assert not bridge.allowed and not bridge._allowed
    assert server.state["epoch"] > previous_epoch
    assert not server.state["commands_allowed"]
    assert bridge.proposal["status"] == "expired"
    server.send(command(server, command_id="new-context"))
    bridge.pump(game, server, now=100.3)
    assert server.state["results"][-1]["reasoncode"] == "commands_blocked"
    assert c.player_class is None
    bridge.allowed = True
    bridge.pump(game, server, now=100.4)
    assert bridge.allowed and server.state["commands_allowed"]


def test_explicit_grant_for_new_pair_before_pump_is_preserved_not_old_proposal(game):
    contact(game)
    bridge, server = start(game)
    propose(game, bridge, server)
    server.lease += 1
    bridge.allowed = True
    assert bridge.allowed
    assert not bridge.accept_proposal(game)
    bridge.pump(game, server, now=100.2)
    assert bridge.allowed and server.state["commands_allowed"]
    assert bridge.proposal["status"] == "expired"
    assert game.target is None


def test_local_proposal_cannot_inherit_lease_before_pump(game):
    contact(game)
    bridge, server = start(game)
    propose(game, bridge, server)
    server.lease += 1
    assert not bridge.accept_proposal(game) and not bridge.reject_proposal(game)
    assert game.target is None


def test_initial_grant_only_binds_first_transport_once(game):
    contact(game)
    bridge, server = start(game)
    assert bridge.allowed and bridge._grant_lease == server.lease_generation
    replacement = Server()
    assert replacement.lease_generation == server.lease_generation
    bridge.pump(game, replacement, now=100.1)
    assert not bridge.allowed and not replacement.state["commands_allowed"]
    bridge.allowed = True
    bridge.pump(game, replacement, now=100.2)
    assert bridge.allowed and replacement.state["commands_allowed"]
    bridge.allowed = False
    replacement.lease += 1
    bridge.pump(game, replacement, now=100.3)
    assert not bridge.allowed


@pytest.mark.parametrize("generation", [None, True, -1, "1"])
def test_transport_without_valid_generation_fails_closed(game, monkeypatch, generation):
    c = contact(game)
    monkeypatch.setattr(Server, "lease_generation", generation)
    bridge, server = start(game)
    assert not bridge.allowed and not server.state["commands_allowed"]
    bridge.allowed = True
    assert not bridge.allowed
    server.send(command(server))
    bridge.pump(game, server, now=100.1)
    assert server.state["results"][-1]["reasoncode"] == "commands_blocked"
    assert c.player_class is None


def test_missing_generation_has_no_permissive_legacy_fallback(game, monkeypatch):
    monkeypatch.delattr(Server, "lease_generation")
    bridge, server = start(game)
    assert server.connected and server.lease == 1
    assert not bridge.allowed and not server.state["commands_allowed"]


def test_lease_change_during_drain_cannot_use_cached_frame_grant(game, monkeypatch):
    c = contact(game)
    bridge, server = start(game)

    def drain(limit=4):
        server.lease += 1
        return [dict(command=command(server), lease=server.lease, received_at=100.1)]

    monkeypatch.setattr(server, "drain_commands", drain)
    bridge.pump(game, server, now=100.1)
    assert not bridge.allowed and not server.state["commands_allowed"]
    assert server.state["results"][-1]["reasoncode"] == "commands_blocked"
    assert c.player_class is None


@pytest.mark.parametrize("explicit_regrant", [False, True])
def test_real_http_expire_repair_between_pumps_never_inherits_grant(game, monkeypatch, explicit_regrant):
    import http.client

    from src.commander import server as transport

    clock = [100.0]
    monkeypatch.setattr(transport, "time", NS(monotonic=lambda: clock[0]))
    server = transport.CommanderServer()
    server.start("127.0.0.1", 0)

    def request(path, token=None, body=None):
        host, port = server.address
        connection = http.client.HTTPConnection(host, port, timeout=3)
        headers = {"Origin": f"http://{host}:{port}", "Content-Type": "application/json"}
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        try:
            connection.request("GET" if body is None else "POST", "/api/v1/" + path,
                               body=None if body is None else json.dumps(body), headers=headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def http_command(state, identity, value):
        return dict(id=identity, session=state["session"], epoch=state["epoch"],
                    revision=state["revision"], track=state["tracks"][0]["ref"],
                    action="classify", value=value)

    try:
        c = contact(game)
        bridge = CommanderBridge()
        bridge.pump(game, server, now=clock[0])
        status, paired = request("pair", body={"code": server.pairing_code})
        assert status == 200
        old_token, old_lease = paired["token"], server.lease_generation
        bridge.allowed = True
        bridge.pump(game, server, now=clock[0])
        _, state = request("state", old_token)
        assert state["commands_allowed"]
        assert request("commands", old_token, http_command(state, "old-authorized", "U_BOOT"))[0] == 202
        bridge.pump(game, server, now=clock[0])
        assert c.player_class == "U_BOOT"
        _, state = request("state", old_token)
        assert request("commands", old_token, http_command(state, "old-pending", "BIOLOGISCH"))[0] == 202
        old_envelope = server.drain_commands()[0]
        assert old_envelope["lease"] == old_lease and server.is_current(old_envelope)

        # Both expiration and replacement pairing happen without a bridge pump.
        clock[0] += 31
        status, paired = request("pair", body={"code": server.pairing_code})
        assert status == 200
        new_token = paired["token"]
        assert new_token != old_token and server.connected
        assert server.lease_generation > old_lease
        assert not server.is_current(dict(old_envelope, received_at=clock[0]))
        assert request("commands", old_token, http_command(state, "old-token", "BIOLOGISCH"))[0] == 401
        assert not bridge.allowed
        if explicit_regrant:
            bridge.allowed = True
        assert request("commands", new_token, http_command(state, "new-old-context", "BIOLOGISCH"))[0] == 202
        bridge.pump(game, server, now=clock[0])
        _, state = request("state", new_token)
        assert state["results"][-1]["status"] == "rejected"
        assert c.player_class == "U_BOOT"
        assert bridge.allowed is explicit_regrant
        assert state["commands_allowed"] is explicit_regrant

        if not explicit_regrant:
            assert request("commands", new_token, http_command(state, "new-no-grant", "BIOLOGISCH"))[0] == 202
            bridge.pump(game, server, now=clock[0])
            _, state = request("state", new_token)
            assert state["results"][-1]["reasoncode"] == "commands_blocked"
            assert c.player_class == "U_BOOT"
            bridge.allowed = True
            bridge.pump(game, server, now=clock[0])
            _, state = request("state", new_token)
        assert request("commands", new_token, http_command(state, "new-authorized", "BIOLOGISCH"))[0] == 202
        bridge.pump(game, server, now=clock[0])
        _, state = request("state", new_token)
        assert state["results"][-1] == dict(id="new-authorized", status="applied", reasoncode="ok")
        assert c.player_class == "BIOLOGISCH"

        expired = http_command(state, "queued-expired", "FAHRZEUG")
        assert request("commands", new_token, expired)[0] == 202
        clock[0] += 5.1
        bridge.pump(game, server, now=clock[0])
        status, state = request("state", new_token)
        assert status == 200 and state["commands_allowed"]
        assert state["results"][-1] == dict(id="queued-expired", status="rejected", reasoncode="unauthorized")
        assert c.player_class == "BIOLOGISCH"
        assert server.drain_commands() == []
    finally:
        server.stop()


@pytest.mark.parametrize("key,kind,source,producer_label", [
    ("S-987654321", "SURFACE", "RADAR-S", "S-987654321"),
    ("W-987654321", "SURFACE", "RADAR-S", "W-987654321"),
    ("H-987654321", "HF", "HFDF", "SIG-987654321"),
    ("M-987654321", "ASM", "HOJ", "A-987654321"),
    ("A-987654321", "FLG", "RADAR-L", "A-987654321"),
    ("S-987654321", "AIS", "ESM", "SECRET OLD AIS NAME"),
    ("S-987654321", "SURFACE", "RADAR-S/AIS", "SECRET NOT AIS"),
    ("S-987654321", "AIS", "RADAR-S/AIS-FAKE", "SECRET NOT MODELED AIS"),
])
def test_generic_labels_never_forward_producer_ids_or_namespace(game, key, kind, source, producer_label):
    t = observe(game, key, kind, source)
    t.label = producer_label
    bridge, server = start(game)
    row = server.state["tracks"][0]
    assert row["label"] == "C001"
    encoded = json.dumps(server.state)
    assert "987654321" not in encoded and producer_label not in encoded
    t.label = "DIFFERENT SECRET LABEL"
    revision = server.state["revision"]
    bridge.pump(game, server, now=100.5)
    assert server.state["tracks"][0]["label"] == "C001"
    assert server.state["tracks"][0]["ref"] == row["ref"]
    assert server.state["revision"] == revision


def test_generic_and_sonar_projection_never_even_read_producer_label_or_contact_number(game, monkeypatch):
    c = contact(game)
    for key, kind, source in (("S-1", "SURFACE", "ESM"), ("W-2", "SURFACE", "RADAR-S"),
                              ("H-3", "HF", "HFDF"), ("M-4", "ASM", "RADAR-L")):
        observe(game, key, kind, source)

    def forbidden(*args):
        raise AssertionError("producer identity read for a neutral label")

    monkeypatch.setattr(type(game.opz_tracks()[0]), "label", property(forbidden), raising=False)
    monkeypatch.setattr(Contact, "id", property(forbidden), raising=False)
    bridge, server = start(game)
    assert [t["label"] for t in server.state["tracks"]] == [f"C{i:03d}" for i in range(1, 6)]
    sonar = next(t for t in server.state["tracks"] if t["can_propose"])
    server.send(command(server, "propose", ref=sonar["ref"]))
    bridge.pump(game, server, now=100.1)
    assert bridge.proposal == dict(ref=sonar["ref"], label=sonar["label"], status="pending")
    assert bridge.accept_proposal(game) and game.target is c


@pytest.mark.parametrize("name", ["MV Observed Name", "<observed>{name}", "N" * 200, "", "   ", None, 123])
def test_only_modeled_ais_names_are_preserved_with_bounded_string_values(game, name):
    t = observe(game, "S-987654321", "AIS", "RADAR-S/AIS")
    t.label = name
    bridge, server = start(game)
    expected = name[:128] if type(name) is str and name.strip() else "C001"
    assert server.state["tracks"][0]["label"] == expected
    assert "987654321" not in json.dumps(server.state)


def test_losing_ais_source_does_not_carry_forward_observed_name(game):
    t = observe(game, "S-1", "AIS", "RADAR-S/AIS")
    t.label = "MV Observed Name"
    bridge, server = start(game)
    ref, revision = server.state["tracks"][0]["ref"], server.state["revision"]
    t.source = "ESM"
    bridge.pump(game, server, now=100.1)
    assert server.state["tracks"][0]["ref"] == ref
    assert server.state["tracks"][0]["label"] == "C001"
    assert server.state["revision"] > revision
    t.source = "RADAR-S/AIS"
    t.label = "MV Newly Observed Name"
    bridge.pump(game, server, now=100.2)
    assert server.state["tracks"][0]["label"] == t.label
    revision = server.state["revision"]
    t.label = "MV Changed Observation"
    bridge.pump(game, server, now=100.3)
    assert server.state["tracks"][0]["label"] == t.label
    assert server.state["revision"] > revision


def test_label_counter_is_bounded_never_wraps_and_resets_only_with_session(game):
    contact(game)
    bridge, server = start(game)
    bridge._label_seq = 2**53 - 2
    observe(game, "A-1", "FLG", "RADAR-L")
    bridge.pump(game, server, now=100.1)
    assert bridge._label_seq == 2**53 - 1
    assert {t["label"] for t in server.state["tracks"]} == {"C001", f"C{2**53 - 1}"}
    observe(game, "W-2", "SURFACE", "RADAR-S")
    bridge.pump(game, server, now=100.6)
    assert len(bridge._refs) == 2 and "W-2" not in bridge._refs
    assert bridge._label_seq == 2**53 - 1
    session = server.state["session"]
    game.world = deepcopy(game.world)
    bridge.pump(game, server, now=100.7)
    assert server.state["session"] != session and bridge._label_seq == 3
    assert [t["label"] for t in server.state["tracks"]] == ["C001", "C002", "C003"]


def test_redaction_reacquisition_does_not_reuse_old_label_in_same_session(game):
    contact(game)
    bridge, server = start(game)
    before = server.state
    game.in_menu = True
    bridge.pump(game, server, now=100.1)
    assert bridge._label_seq == 1 and not bridge._refs
    game.in_menu = False
    bridge.pump(game, server, now=100.2)
    assert server.state["session"] == before["session"]
    assert server.state["tracks"][0]["label"] == "C002"
    assert server.state["tracks"][0]["ref"] != before["tracks"][0]["ref"]


@pytest.mark.parametrize("state", ["HANGAR", "VERLOREN", "AUF", "ZURUECK"])
def test_helo_pose_only_exported_while_airborne(game, state):
    game.helo.state = state
    game.helo.x, game.helo.y, game.helo.course = 123, 234, 45
    before = game.save_state()
    bridge, server = start(game)
    helo = server.state["ownship"]["helo"]
    airborne = state in ("AUF", "ZURUECK")
    assert helo == dict(state=state, x=123 if airborne else None, y=234 if airborne else None,
                        course=45 if airborne else None, fuel_s=game.helo.fuel_s,
                        torpedoes=game.helo.torps, buoys=game.helo.buoys_left)
    assert game.save_state() == before
    game.helo.state = "HANGAR" if airborne else "AUF"
    bridge.pump(game, server, now=100.5)
    pose = server.state["ownship"]["helo"]
    assert (pose["x"], pose["y"], pose["course"]) == ((None, None, None) if airborne else (123, 234, 45))


@pytest.mark.parametrize("state", ["HANGAR", "VERLOREN"])
def test_nonairborne_pose_is_not_read(game, monkeypatch, state):
    game.helo.state = state

    def forbidden(*args):
        raise AssertionError("read a nonairborne asset position")

    for key in ("x", "y", "course"):
        monkeypatch.setattr(type(game.helo), key, property(forbidden), raising=False)
    bridge, server = start(game)
    helo = server.state["ownship"]["helo"]
    assert helo["state"] == state
    assert helo["x"] is helo["y"] is helo["course"] is None


def test_fake_expired_envelopes_each_get_terminal_bounded_rejection(game):
    c = contact(game)
    bridge, server = start(game)
    before = game.save_state()
    for index in range(6):
        server.send(command(server, command_id=f"expired-{index}"))
    bridge.pump(game, server, now=105.1)
    assert len(server.state["results"]) == 4 and len(server.queue) == 2
    bridge.pump(game, server, now=105.2)
    assert server.state["results"] == [dict(id=f"expired-{index}", status="rejected", reasoncode="unauthorized")
                                        for index in range(6)]
    assert not server.queue and c.player_class is None
    assert game.save_state() == before
