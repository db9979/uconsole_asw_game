from unittest.mock import Mock

from src.core.game import Game
from src.sonar.sonar import Contact
from src.ui.nato_symbols import domain_for_kind


def _publish(game, monkeypatch, contact):
    contact.last_seen = game.sim_t
    contact.confidence = contact.quality = 1.0
    contact.passive_bearing = 90.0
    monkeypatch.setattr(game.sonar, "update", Mock())
    monkeypatch.setattr(game.sonar, "active_contacts", lambda: [contact])
    game._update_sensors(0.25)
    return game.air_picture._tracks[f"U-{contact.target_id}"]


def test_generic_underwater_contact_publishes_unknown_domain(monkeypatch):
    game = Game(seed=901, audio_enabled=False)
    contact = Contact(7, 700, "passiv", "sub")

    track = _publish(game, monkeypatch, contact)

    assert track.kind == "UNKNOWN"
    assert track.label == "K7"
    assert track.hostile is False


def test_torpedo_domain_comes_only_from_operator_classification(monkeypatch):
    game = Game(seed=902, audio_enabled=False)
    contact = Contact(8, 800, "passiv", "torpedo")
    # The weapon itself publishes no domain until the operator classifies it.
    assert _publish(game, monkeypatch, contact).kind == "UNKNOWN"
    contact.player_class = "TORPEDO"
    game.sim_t += 1.0   # next measurement epoch

    track = _publish(game, monkeypatch, contact)

    assert track.kind == "TORP"
    assert domain_for_kind(track.kind) == "UNDERWATER_WEAPON"
    assert track.label == "K8"
    assert track.hostile is False


def test_biological_contact_publishes_no_domain_hint(monkeypatch):
    game = Game(seed=903, audio_enabled=False)
    contact = Contact(9, 900, "passiv", "animal")

    track = _publish(game, monkeypatch, contact)

    # A whale once published SUBSURFACE while real boats stayed UNKNOWN.
    assert track.kind == "UNKNOWN"
    assert domain_for_kind(track.kind) == "UNKNOWN"
    assert track.label == "K9"
    assert track.hostile is False


def test_manual_reclassification_does_not_rewrite_sensor_domain(monkeypatch):
    game = Game(seed=904, audio_enabled=False)
    contact = Contact(10, 1000, "passiv", "sub")
    track = _publish(game, monkeypatch, contact)
    assert track.kind == "UNKNOWN"

    contact.player_class = "U_BOOT"
    assert contact.display_label == "U-Boot"
    track = _publish(game, monkeypatch, contact)

    assert track.kind == "UNKNOWN"
    assert track.label == "K10"
    assert track.hostile is False
