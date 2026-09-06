"""Smoke-Test W0-W4: Headless-Run mit Simulation (SDL_VIDEODRIVER=dummy).

Prueft: Game-Start, Update-Loop ueber alle Stationen, Ping, TMA-Bildung,
LOFAR-Wasserfall, Zeitraffer, Save-Slots, Dekoy-Abwurf, Land-Kollision.
"""

import os
import sys
from tempfile import TemporaryDirectory

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame

from src.core import config
from src.core.game import Game
from src.core.station import Station

DT = 1.0 / 60.0


def pump(g: Game, frames: int, dt: float = DT):
    for _ in range(frames):
        g.update(dt)
        g.draw()


def main() -> None:
    previous_paths = config.SAVE_DIR, config.SAVE_PATH
    with TemporaryDirectory(prefix="u-jagd-smoke-") as saves:
        try:
            config.SAVE_DIR = saves
            config.SAVE_PATH = os.path.join(saves, "save.json")
            _run_smoke()
        finally:
            config.SAVE_DIR, config.SAVE_PATH = previous_paths


def _run_smoke() -> None:
    g = Game(seed=1234, start_menu=False)
    assert g.in_menu is False

    # --- W0: Zeitraffer + Sub-Stepping ---
    assert g.time_scale == 1
    g.cycle_time_scale(1)
    assert g.time_scale == 5
    g.cycle_time_scale(1)
    assert g.time_scale == 15
    g.cycle_time_scale(-3)
    assert g.time_scale == 1

    # --- Update ueber alle Stationen ---
    for st in Station:
        g.station = st
        pump(g, 30)
    assert g.sim_t > 0.0

    # --- W3: Welt/Kueste ---
    assert not g.world.on_land(g.ship.x, g.ship.y), "Fregatte in Land gespawnt?"
    coast = g.world.coast
    assert len(coast.landmasses) >= 3
    assert len(coast.airbases) >= 3
    water = g.world.nearest_water(coast.airbases[0]["x"],
                                  coast.airbases[0]["y"])
    assert not g.world.on_land(*water)

    # --- W1: Sonar: Ping + Kontakte ---
    g.station = Station.SONAR
    pump(g, 120)
    assert g.sonar.ping_ready
    assert g.sonar.fire_ping()
    g.sonar.apply_ping(g.ship, g._sonar_targets(), g.world, g.sim_t,
                       range_factor=1.0, mode=g.sonar_mode)
    pump(g, 120)
    print(f"Kontakte: {len(g.sonar.contacts)}")

    # Fokus-Setzen + LOFAR-Wasserfall fuellt sich
    if g.sonar.contacts:
        g.selected_contact = sorted(g.sonar.contacts.values(),
                                    key=lambda c: c.id)[0]
        focus = g._find_target(g.selected_contact.target_id)
        g.station = Station.SONAR
        pump(g, 200)
        assert len(g.sonar.lofar_history) > 0
        assert len(g.sonar.lofar_history[-1]) == config.LOFAR_BINS
        assert focus is not None
        lines = focus.lofar_lines(g.sim_t)
        assert all(0 <= f <= 300 for f, a, w in lines)
        print(f"LOFAR-Spalten: {len(g.sonar.lofar_history)} "
              f"(Fokus K{g.selected_contact.id}, Zeilen: {len(lines)})")

    # --- W1: TMA (erzwungen: Sub in 6 NM + 90°-Manöver der Fregatte) ---
    tma_sub = next((s for s in g.subs if not s.sunk), None)
    if tma_sub is not None:
        tma_sub.x, tma_sub.y = g.ship.x + 6.0, g.ship.y
        tma_sub.depth = 55.0
        tma_sub.state = "LAUER"
        tma_sub.evac_left = 999.0
        tma_sub.speed = 0.0
        tma_sub.course = 90.0
        tma_sub.torpedo_alerted = False
        g.sonar._tracks.clear()
        g.sonar_mode = "TOWED"
        # Mehrminuetige, physikalische Peilbaseline ohne tausende Renderframes.
        for leg_course in (0.0, 0.0, 0.0, 90.0, 90.0, 90.0, 90.0):
            g.ship.course = leg_course
            g.ship.target_course = leg_course
            if leg_course == 0.0:
                g.ship.y -= .2
            else:
                g.ship.x += .2
            g.sim_t += 60.0
            g._update_sensors(60.0)
            g.selected_contact = next(
                (contact for contact in g.sonar.contacts.values()
                 if contact.target_id == tma_sub.id), None)
        c = g.sonar.contacts.get(tma_sub.id)
        assert c is not None, "TMA-Test: Kontakt verloren"
        assert c.tma_pos is not None, "TMA: keine Loesung trotz 90°-Manöver"
        print(f"TMA: OK (Kontakte: {len(g.sonar.contacts)}, "
              f"quality={c.tma_quality:.2f})")
    else:
        print("TMA: übersprungen (kein Sub übrig)")

    # --- W2: Dekoy-Trigger (erzwungen) ---
    for sub in g.subs:
        if not sub.sunk:
            sub.alert_torpedo()
            break
    n_decoys_before = len(g.decoys)
    pump(g, 60)
    if len(g.decoys) > n_decoys_before:
        d = g.decoys[-1]
        assert 0 <= d.x <= config.WORLD_SIZE_NM
        assert d.lofar_lines(g.sim_t)
        print(f"Dekoys aktiv: {len(g.decoys)}")

    # --- W2: LAUER-Zustand pruefen (erzw. EVADE in Naehere) ---
    for sub in g.subs:
        if not sub.sunk:
            sub.x, sub.y = g.ship.x + 10.0, g.ship.y + 10.0
            sub.evac_left = 0.0
            sub.state = "EVADE"
            break
    pump(g, 30)
    luer = [s for s in g.subs if s.state == "LAUER"]
    print(f"LAUER-Zustaende: {len(luer)}")

    # --- Land-Kollision: Fregatte stoesst nicht in Land ---
    for _ in range(400):
        pump(g, 10)
    assert not g.world.on_land(g.ship.x, g.ship.y), "Fregatte in Land gefahren?"

    # --- W4: Save/Load ---
    g.save_to_slot(2)
    snap_x = g.ship.x
    ok = g.load_from_slot(2)
    assert ok, "Load von Slot 2 fehlgeschlagen"
    assert abs(g.ship.x - snap_x) < 0.01
    ok_empty = g.load_from_slot(5)
    assert not ok_empty, "Slot 5 sollte leer sein"
    print("Save/Load Slot-2 OK")

    # --- W4: Menue (Hauptmenue -> Szenario -> Level -> Briefing) ---
    g2 = Game(seed=42, start_menu=True)
    assert g2.in_menu and g2.main_menu
    g2._handle_menu_key(pygame.K_RETURN)     # New Game -> scenario
    assert not g2.main_menu and g2.menu_screen == "scenario"
    g2._handle_menu_key(pygame.K_4)          # s4_zufall
    g2._handle_menu_key(pygame.K_RETURN)     # -> Level
    assert g2.menu_screen == "level"
    g2._handle_menu_key(pygame.K_2)          # normal
    g2._handle_menu_key(pygame.K_RETURN)
    assert not g2.in_menu
    pump(g2, 60)
    print(f"Menue-Flow OK (Szenario: {g2.scenario_key})")

    # --- Draw ueber alle Stationen (ohne Crash) ---
    for st in Station:
        g.station = st
        g.help_open = True
        g.draw()
        g.help_open = False
        g.nations_open = True
        g.draw()
        g.nations_open = False
        g.save_ui = "save"
        g.draw()
        g.save_ui = "load"
        g.draw()
        g.save_ui = None
    print("Draw ueber alle Stationen + Overlays OK")

    # --- Endgame: Mission-Sieg pruefen (erzw.) ---
    g.game_over = True
    g.mission_result = "SIEG"
    g.draw()
    print("Endpanel-Draw OK")

    print("SMOKE-OK")


if __name__ == "__main__":
    main()
    pygame.quit()
