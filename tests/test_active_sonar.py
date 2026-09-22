import random

from src.core import config
from src.enemies.sub import Sub
from src.ship.ship import Ship
from src.sonar.sonar import SonarSystem
from src.sonar import propagation
from src.world.world import World


def test_delayed_ping_notifies_once_and_records_measurement_only_history():
    world = World(seed=8)
    ship = Ship(250, 250, speed_kn=4)
    sub = Sub(255, 250, 60, 0, "diesel_alt", random.Random(8))
    calls = []
    sub.hear_ping = lambda: calls.append(True)
    sonar = SonarSystem(8)
    sonar.queue_ping(ship, [sub], world, 0)
    sonar.update(30, 30, ship, [], world)
    assert len(calls) == 1
    assert len(sonar.echo_history) == 1
    observation = sonar.echo_history[0]
    assert set(observation) == {
        "t", "contact_id", "bearing", "range_nm", "range_sigma_nm",
        "depth_m", "depth_sigma_m", "snr_db", "mode",
    }
    assert observation["range_sigma_nm"] > 0
    assert observation["depth_sigma_m"] > 0
    assert "target_id" not in observation


def test_ping_fix_expires_without_passive_detection_and_history_is_bounded():
    world = World(seed=9)
    ship = Ship(250, 250, speed_kn=4)
    sub = Sub(252, 250, 60, 0, "diesel_alt", random.Random(9))
    sonar = SonarSystem(9)
    contact = sonar.apply_ping(ship, [sub], world, 0)[0]
    contact.confidence = 1
    sonar.update(1, config.SONAR_PING_FIX_MAX_AGE_S + 1, ship, [], world)
    assert contact.range_est is None and contact.depth_est is None
    assert contact.range_source is None

    for i in range(config.SONAR_ECHO_HISTORY_MAX + 5):
        sonar.apply_ping(ship, [sub], world, i + 200)
    assert len(sonar.echo_history) == config.SONAR_ECHO_HISTORY_MAX
    assert sonar.echo_history[0]["t"] == 205


def test_ping_cooldown_state_is_public():
    sonar = SonarSystem()
    assert sonar.ping_ready and sonar.ping_cooldown_remaining == 0
    assert sonar.fire_ping()
    assert not sonar.ping_ready
    assert sonar.ping_cooldown_remaining == config.SONAR_PING_COOLDOWN_S


def test_ping_animation_timer_stops_at_canonical_zero():
    sonar = SonarSystem()
    ship = Ship(250, 250, speed_kn=4)
    assert sonar.fire_ping()
    sonar.advance_mechanics(2.0, 2.0, ship)
    assert sonar._ping_anim_timer == 0.0
    assert not sonar.ping_active


def test_stowed_towed_array_cannot_ping_or_notify_target():
    world = World(seed=10)
    ship = Ship(250, 250, speed_kn=4)
    sub = Sub(252, 250, 60, 0, "diesel_alt", random.Random(10))
    calls = []
    sub.hear_ping = lambda: calls.append(True)
    sonar = SonarSystem(10)
    sonar.queue_ping(ship, [sub], world, 0, mode="TOWED")
    assert not sonar._pending_pings and not calls
    assert sonar.apply_ping(ship, [sub], world, 0, mode="TOWED") == []
    assert not calls


def test_terrain_blocks_new_sonar_observations_but_retains_acquired_contact(monkeypatch):
    world = World(seed=11)
    ship = Ship(250, 250, speed_kn=4)
    sub = Sub(252, 250, 60, 0, "diesel_alt", random.Random(11))
    sonar = SonarSystem(11)
    sonar.update(1, 1, ship, [sub], world)
    contact = sonar.contacts[sub.id]
    confidence = contact.confidence

    monkeypatch.setattr(world, "sonar_path_blocked", lambda *args: True)
    assert sonar.apply_ping(ship, [sub], world, 2) == []
    sonar.update(1, 2, ship, [sub], world)
    assert sonar.contacts[sub.id] is contact
    assert contact.confidence < confidence


def test_active_range_reject_precedes_expensive_occlusion_query(monkeypatch):
    world = World(seed=12)
    ship = Ship(250, 250, speed_kn=4)
    far = Sub(400, 400, 60, 0, "diesel_alt", random.Random(12))
    calls = []
    monkeypatch.setattr(world, "sonar_path_blocked",
                        lambda *args: calls.append(args) or False)

    sonar = SonarSystem(12)
    assert sonar.apply_ping(ship, [far], world, 0) == []
    sonar.queue_ping(ship, [far], world, 0)
    assert sonar._pending_pings == []
    assert calls == []


def test_active_queue_apply_and_return_never_use_passive_propagation(monkeypatch):
    world = World(seed=13)
    ship = Ship(250, 250, speed_kn=4)
    sub = Sub(252, 250, 60, 0, "diesel_alt", random.Random(13))
    sonar = SonarSystem(13)
    monkeypatch.setattr(propagation, "propagate",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(
                            AssertionError("active sonar called propagation")))

    assert sonar.apply_ping(ship, [sub], world, 0)
    sonar.queue_ping(ship, [sub], world, 1)
    sonar.update(30, 31, ship, [], world)
    assert sonar.echo_history
