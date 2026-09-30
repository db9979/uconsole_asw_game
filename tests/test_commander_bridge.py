"""Focused bridge-level v2 projection and observation-boundary tests."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import random
from types import SimpleNamespace as NS

import numpy as np
import pytest

from src.commander.bridge import CommanderBridge, sonar_pcm_s16le
from src.commander.projections import ROLE_NAMES
from src.core import config
from src.core.game import Game
from src.sonar.sonar import Contact


class Server:
    """Compact detached v2 publication target shared by projection tests."""

    connected = True

    def __init__(self):
        self.v2_states = None
        self.v2_charts = None
        self.proposals = None
        self.events = None
        self.simlogs = None
        self.revocations = 0

    @property
    def state(self):
        # A few projection tests only need the common version field.
        return self.v2_states["sonar"]

    def publish_v2(self, states, charts):
        json.dumps(states, allow_nan=False)
        json.dumps(charts, allow_nan=False)
        self.v2_states = deepcopy(states)
        # The real server serialises each role's chart to its own bytes, so a
        # chart object shared between roles is still independent once published.
        self.v2_charts = {role: deepcopy(chart) for role, chart in charts.items()}

    def publish_proposals_v2(self, **payload):
        self.proposals = deepcopy(payload)

    def publish_events_v2(self, **payload):
        self.events = deepcopy(payload)

    def publish_simlog_v2(self, **payload):
        self.simlogs = deepcopy(payload)

    def publish_debrief_v2(self, **payload):
        json.dumps(payload, allow_nan=False)
        self.debriefs = deepcopy(payload)

    def drain_commands_v2(self):
        return []

    def authority_current_v2(self, _envelope):
        return False

    def invalidate_v2_commands(self, _reason):
        pass

    def revoke(self):
        self.revocations += 1
        self.connected = False


@pytest.fixture
def game():
    current = Game(seed=31, start_menu=False, audio_enabled=False, language="en")
    yield current
    current.audio.shutdown()


def observe(game, key="U-7654321", kind="UNKNOWN", source="SONAR-BRG", now=None):
    return game.air_picture.observe(
        track_id=key, kind=kind, target_id=int(key.split("-")[1]),
        source=source, bearing=90.0, range_nm=None,
        observer_x=game.ship.x, observer_y=game.ship.y, course=None,
        quality=.8, now=game.sim_t if now is None else now, label="K7")


def contact(game):
    current = Contact(7, 7654321, "passiv", "sub")
    current.update_passive(90.0, .8, .8, "hidden producer label", game.sim_t)
    game.sonar.contacts[current.target_id] = current
    observe(game)
    return current


def publish(game, now=100.0):
    bridge, server = CommanderBridge(), Server()
    assert bridge.allowed
    bridge.pump(game, server, now=now)
    return bridge, server


def test_sonar_pcm_conversion_is_exact_deterministic_and_does_not_mutate():
    samples = np.zeros(1024, dtype=np.float32)
    samples[:8] = [0.0, 0.5, -0.5, 0.75, 1.0, -1.0, np.nan, np.inf]
    original = samples.copy()
    first = sonar_pcm_s16le(samples)
    assert first == sonar_pcm_s16le(samples) and len(first) == 2048
    assert np.array_equal(samples, original, equal_nan=True)
    assert np.frombuffer(first, dtype="<i2")[:8].tolist() == [
        0, 16384, -16384, 24575, 28500, -28500, 0, 32112]
    with pytest.raises(ValueError):
        sonar_pcm_s16le(np.zeros(1023, dtype=np.float32))


def test_refs_and_generic_labels_are_opaque_neutral_and_stable(game):
    contact(game)
    observed = observe(game, "S-987654321", "SURFACE", "RADAR-S")
    observed.label = "SECRET PRODUCER LABEL 987654321"
    bridge, server = publish(game)
    sonar = server.v2_states["sonar"]["sonar"]["observations"][0]
    opz = server.v2_states["opz"]["opz"]["observations"][0]
    encoded = json.dumps(list(server.v2_states.values()), sort_keys=True)

    assert sonar["label"] == "K07"
    assert opz["label"].isalnum() and 1 <= len(opz["label"]) <= 16
    assert opz["label"] not in (observed.track_id, observed.label)
    assert sonar["ref"] != sonar["label"] and opz["ref"] != opz["label"]
    assert "987654321" not in encoded and "SECRET PRODUCER LABEL" not in encoded
    refs = sonar["ref"], opz["ref"]
    observed.label = "ANOTHER SECRET"
    bridge.pump(game, server, now=100.5)
    assert server.v2_states["sonar"]["sonar"]["observations"][0]["ref"] == refs[0]
    assert server.v2_states["opz"]["opz"]["observations"][0]["ref"] == refs[1]


def test_helicopter_dip_projection_uses_its_own_bearing_and_active_fix(game):
    current = contact(game)
    current.update_dip_passive(123.0, game.sim_t, 20.0, 30.0, 1.5)
    current._fx, current._fy = 20.0, 30.0
    current.observer_x, current.observer_y = 20.0, 30.0
    current.update_ping(125.0, 4.0, 55.0, .9, game.sim_t,
                        fix_source="DIPPING")
    before = deepcopy(current.__dict__)
    _, server = publish(game)
    rows = server.v2_states["helicopter"]["helicopter"]["dip_observations"]
    assert len(rows) == 1
    row = rows[0]
    assert row["bearing"] == pytest.approx(123.0)
    assert row["active_bearing"] == pytest.approx(125.0)
    assert row["range_nm"] == pytest.approx(4.0)
    assert row["range_uncertainty_nm"] is not None
    assert row["depth_m"] == pytest.approx(55.0)
    assert row["depth_uncertainty_m"] is not None
    tactical = server.v2_states["helicopter"]["helicopter"]["tactical"][0]
    assert tactical["bearing"] == pytest.approx(123.0)
    assert tactical["observer_x"] == pytest.approx(20.0)
    assert tactical["observer_y"] == pytest.approx(30.0)
    assert tactical["range_nm"] is None
    assert current.__dict__ == before

    current.dip_last_seen = game.sim_t - config.SONAR_CONTACT_LOST_S
    _, server = publish(game)
    row = server.v2_states["helicopter"]["helicopter"]["dip_observations"][0]
    assert row["bearing"] is None and row["range_nm"] == pytest.approx(4.0)


def test_helicopter_dip_projection_excludes_ship_only_contact(game):
    contact(game)
    _, server = publish(game)
    assert server.v2_states["helicopter"]["helicopter"]["dip_observations"] == []
    assert server.v2_states["helicopter"]["helicopter"]["tactical"] == []


def test_opz_web_projection_keeps_ship_and_dip_bearing_origins_separate(game):
    current = contact(game)
    current.observer_x, current.observer_y = game.ship.x, game.ship.y
    current.update_dip_passive(180.0, game.sim_t,
                               game.ship.x + 5.0, game.ship.y - 5.0, 1.5)
    current.released_to_opz = True
    current.dip_released_to_opz = True
    _, server = publish(game)
    rows = [row for row in server.v2_states["opz"]["opz"]["observations"]
            if row["source"].startswith("SONAR")]
    assert len(rows) == 2
    ship = next(row for row in rows if row["source"] == "SONAR-BRG")
    dip = next(row for row in rows if row["source"] == "SONAR-DIP-BRG")
    assert ship["ref"] != dip["ref"]
    assert (ship["observer_x"], ship["observer_y"]) == (game.ship.x, game.ship.y)
    assert (dip["observer_x"], dip["observer_y"]) == (game.ship.x + 5.0, game.ship.y - 5.0)
    assert ship["bearing"] == pytest.approx(90.0)
    assert dip["bearing"] == pytest.approx(180.0)


@pytest.mark.parametrize("source", ["ping", "tma", "buoy"])
def test_stale_sonar_fix_never_falls_back_to_mirrored_geometry(game, source):
    game.sim_t = 300.0
    current = contact(game)
    current.range_source = source
    current.range_est, current.range_sigma_nm = 12.0, .3
    current.observed_x, current.observed_y, current.depth_est = 123.0, 124.0, 60.0
    current.tma_course, current.tma_speed, current.tma_quality = 42.0, 9.0, 1.0
    lifetime = (config.SONAR_PING_FIX_MAX_AGE_S if source == "ping"
                else config.SONAR_CONTACT_LOST_S)
    current.range_seen = game.sim_t - lifetime - .01
    current.tma_seen = None
    before = deepcopy(current.__dict__)
    _, server = publish(game)
    row = server.v2_states["sonar"]["sonar"]["observations"][0]

    assert current.__dict__ == before
    assert all(row[key] is None for key in
               ("range_nm", "x", "y", "depth_m", "course", "speed_kn"))
    assert row["source"] == "SONAR-BRG"


def test_chart_is_detached_and_oversized_or_invalid_geometry_is_omitted(game):
    bridge, server = publish(game)
    chart = server.v2_charts["bridge"]
    assert chart["landmasses"] and chart["revision"] == bridge.status["session"]
    chart["landmasses"].clear()
    assert server.v2_charts["sonar"]["landmasses"]

    for points in ([(0, 0)] * 20001, [(float("nan"), 0)] * 3):
        game.world = deepcopy(game.world)
        game.world.coast.landmasses = [NS(points=points)]
        server.connected = True
        bridge.pump(game, server, now=101.0)
        bridge.pump(game, server, now=101.5)
        chart = server.v2_charts["bridge"]
        assert chart["landmasses"] == []
        assert chart["disclaimer"] == game.tr("commander.chart.omitted")


def test_world_replacement_revokes_and_publishes_one_redacted_generation(game):
    contact(game)
    bridge, server = publish(game)
    session = bridge.status["session"]
    game.world = deepcopy(game.world)
    bridge.pump(game, server, now=100.1)
    assert server.revocations == 1 and not bridge.allowed
    assert bridge.status["session"] != session
    assert all(state["role"] is None for state in server.v2_states.values())
    assert all(not chart["landmasses"] for chart in server.v2_charts.values())


@pytest.mark.parametrize("state", ["HANGAR", "VERLOREN"])
def test_nonairborne_helicopter_pose_is_neither_read_nor_published(game, monkeypatch, state):
    game.helo.state = state

    def forbidden(*_args):
        raise AssertionError("read a nonairborne asset position")

    for key in ("x", "y", "course"):
        monkeypatch.setattr(type(game.helo), key, property(forbidden), raising=False)
    _, server = publish(game)
    asset = server.v2_states["helicopter"]["helicopter"]["asset"]
    assert asset["state"] == state
    assert asset["x"] is asset["y"] is asset["course"] is None


def test_polling_is_deterministic_detached_and_does_not_mutate_game(game):
    contact(game)
    before, rng = game.save_state(), random.getstate()
    bridge, server = publish(game)
    first = {role: deepcopy(server.v2_states[role][role]) for role in ROLE_NAMES}
    for index in range(30):
        bridge.pump(game, server, now=100.5 + index / 2)
    assert {role: server.v2_states[role][role] for role in first} == first
    assert game.save_state() == before and random.getstate() == rng
    server.v2_states["damage"]["damage"]["compartments"][0]["fire"] = 99
    assert game.damage.compartments["bridge"].fire == 0


def test_only_main_thread_may_access_game(game):
    bridge, server = publish(game)
    with ThreadPoolExecutor(max_workers=1) as executor:
        for method, args in ((bridge.pump, (game, server)),
                             (bridge.accept_proposal, (game,)),
                             (bridge.reject_proposal, (game,))):
            with pytest.raises(RuntimeError, match="main thread"):
                executor.submit(method, *args).result()


class AudioServer(Server):
    """Fake transport recording the live-audio publication calls."""

    def __init__(self):
        super().__init__()
        self.audio = []
        self.discontinuities = []

    def prepare_sonar_audio(self, *, world_session, world_epoch):
        return 1

    def publish_sonar_audio(self, pcm, *, world_session, world_epoch, station_generation):
        assert type(pcm) is bytes and len(pcm) == 2048
        self.audio.append(pcm)
        return True

    def mark_audio_discontinuity(self, role):
        self.discontinuities.append(role)
        return True


def test_retuned_receiver_marks_exactly_one_audio_discontinuity(game):
    """A listening-bearing change restarts the receiver; browsers must crossfade."""
    bridge, server = CommanderBridge(), AudioServer()
    receiver = game.sonar.receiver
    now = 100.0
    bridge.pump(game, server, now=now)          # binds the stream, skips retained blocks
    for _ in range(3):
        game.update(.25)
        now += .25
        bridge.pump(game, server, now=now)
    assert len(server.audio) >= 2 and server.discontinuities == []
    published = len(server.audio)
    game.set_sonar_listen_bearing(receiver_bearing := 135.0)
    assert receiver.sequence >= 0 and not receiver.blocks_since(-1)
    for _ in range(3):
        game.update(.25)
        now += .25
        bridge.pump(game, server, now=now)
    assert len(server.audio) > published
    assert server.discontinuities == ["sonar"]
    assert game.sonar.listen_bearing == receiver_bearing
