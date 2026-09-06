"""Save/Load-Roundtrip (Phase 2): kompletter Zustandsabgleich v3."""

import pytest

from src.core import config
from src.core.game import Game
from src.air.asm import ASM
from src.air.sonobuoy import Sonobuoy
from src.weapons.torpedo import Torpedo

DT = 1.0 / 60.0


def pump(g, frames):
    for _ in range(frames):
        g.update(DT)
        g.draw()


@pytest.fixture
def tmp_saves(isolated_saves):
    return isolated_saves


def test_default_save_paths_are_isolated(tmp_path):
    """No opt-in fixture is needed for either slots or legacy saves."""
    saves = tmp_path / "saves"
    assert config.SAVE_DIR == str(saves)
    assert config.SAVE_PATH == str(saves / "save.json")
    assert list(saves.iterdir()) == []
    g = Game(seed=2024, start_menu=False)
    assert g.load_from_slot(5) is False
    assert g.load_game() is False
    g.save_to_slot(2)
    assert g.save_game() == str(saves / "save.json")
    assert {path.name for path in saves.iterdir()} == {"slot2.json", "save.json"}
    assert g.load_from_slot(2)
    assert g.load_game()


def test_roundtrip_preserves_state(tmp_saves):
    g = Game(seed=2024, start_menu=False)
    pump(g, 240)

    # Zustand, der erhalten bleiben muss:
    g.torpedo_depth = 95.0
    g.sonar_mode = "TOWED"
    g.damage.compartments["sonar"].state = "BESCHAEDIGT"
    g.damage.compartments["sonar"].flood = 12.5
    g.damage.compartments["engine"].fire = 20.0
    tgt = g.subs[0]
    g.torpedoes.append(Torpedo(g.ship.x, g.ship.y, 90.0, 60.0, tgt, 99))
    g.asms.append(ASM(g.ship.x + 10.0, g.ship.y, 0.0, 42, g.rng_asm))
    g.buoys.append(Sonobuoy(g.ship.x + 1.0, g.ship.y + 1.0, 7))
    g.hq_msg("Testnachricht")

    before = dict(
        mission_type=g.mission.type_key,
        hour=g.world.hour,
        sea=g.world.sea_state,
        ship_x=g.ship.x, ship_y=g.ship.y,
        sub_state=tgt.state, sub_x=tgt.x, sub_depth=tgt.depth,
        sub_torps=tgt.torpedoes_left,
    )
    g.save_to_slot(1)

    # Zustand sabotieren, dann laden:
    g.ship.x += 3.0
    g.sonar_mode = "BOW"
    g.torpedo_depth = 10.0
    g.torpedoes.clear()
    g.asms.clear()
    g.buoys.clear()
    g.damage.compartments["sonar"].state = "OK"

    ok = g.load_from_slot(1)
    assert ok, "Load fehlgeschlagen"

    # Mission/Welt
    assert g.mission.type_key == before["mission_type"]
    assert abs(g.world.hour - before["hour"]) < 0.01
    assert g.world.sea_state == before["sea"]

    # Fregatte + Waffe
    assert abs(g.ship.x - before["ship_x"]) < 1e-6
    assert abs(g.ship.y - before["ship_y"]) < 1e-6
    assert g.sonar_mode == "TOWED"
    assert g.torpedo_depth == 95.0

    # Schaden (inkl. repair_mult + Brand)
    assert g.damage.compartments["sonar"].state == "BESCHAEDIGT"
    assert abs(g.damage.compartments["sonar"].flood - 12.5) < 1e-6
    assert abs(g.damage.compartments["engine"].fire - 20.0) < 1e-6
    lvl = config.LEVELS[g.level]
    assert abs(g.damage.repair_mult - lvl["repair_mult"]) < 1e-9

    # U-Boot-KI-Zustand
    s = g.subs[0]
    assert s.state == before["sub_state"]
    assert abs(s.x - before["sub_x"]) < 1e-6
    assert abs(s.depth - before["sub_depth"]) < 0.01
    assert s.torpedoes_left == before["sub_torps"]

    # Laufende Entitaeten
    assert len(g.torpedoes) == 1
    assert g.torpedoes[0].idx == 99
    assert g.torpedoes[0].target is not None
    assert g.torpedoes[0].target.id == g.subs[0].id
    assert len(g.asms) == 1 and g.asms[0].seq == 42
    assert len(g.buoys) == 1 and g.buoys[0].seq == 7
    assert g.messages and g.messages[-1][1] == "Testnachricht"

    # Simulation laeuft nach dem Laden weiter (kein Crash)
    pump(g, 120)
    assert g.sim_t > 0.0


def test_load_empty_slot(tmp_saves):
    g = Game(seed=1, start_menu=False)
    assert g.load_from_slot(5) is False


def test_legacy_version_accepted(tmp_saves):
    """v2-Dateien ohne neue Felder bleiben laedbar (Default-Values)."""
    g = Game(seed=99, start_menu=False)
    g.save_to_slot(1)
    import json
    import os
    path = os.path.join(config.SAVE_DIR, "slot1.json")
    with open(path) as f:
        data = json.load(f)
    # Alte v2-Felder loeschend simulieren:
    for key in ("world", "torpedoes_in_flight", "asms", "essms", "buoys",
                "messages", "sonar", "rngs", "chaff_cd", "hq_timer",
                "asm_sel", "dmg_cursor"):
        data.pop(key, None)
    data["version"] = 2
    with open(path, "w") as f:
        json.dump(data, f)
    ok = g.load_from_slot(1)
    assert ok
    assert g.mission.type_key == "patrouille"
    assert len(g.subs) >= 1


def test_malformed_supported_save_does_not_replace_live_game(tmp_saves):
    import json
    import os

    game = Game(seed=101, start_menu=False)
    before = (game.seed, game.ship.x, game.ship.y, game.mission.type_key)
    path = os.path.join(config.SAVE_DIR, "slot2.json")
    with open(path, "w") as handle:
        json.dump({"version": 6, "seed": 999, "ship": None}, handle)

    assert game.load_from_slot(2) is False
    assert (game.seed, game.ship.x, game.ship.y,
            game.mission.type_key) == before
