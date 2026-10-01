"""The crewed boat's selected sonar contact survives save/load (found by the
soak test: the restore looked the selection up by the wrong key, so a boat
save with a selected contact did not load)."""

import json

from src.core.game import Game


def test_boat_save_with_a_selected_contact_loads():
    game = Game(seed=61, start_menu=False, audio_enabled=False, language="en")
    game.reset(61, "s7_geleitzug")
    game.local_side = "uboot"
    game._update(0.05)
    station = game.opfor.station
    for _ in range(600):
        game.update(0.1)
        contacts = [contact for contact in station.sonar.contacts.values()
                    if contact.id != contact.target_id]
        if contacts:
            break
    assert contacts, "no boat contact whose id differs from its target id"
    station.selected_contact = contacts[0]
    document = json.loads(json.dumps(game.save_state()))
    assert document["crew"]["station"]["selected_contact_id"] == contacts[0].id
    loaded = Game(seed=1, start_menu=True, audio_enabled=False, language="en")
    assert loaded._load_save_data(document)
    assert loaded.opfor.station.selected_contact.id == contacts[0].id
