"""Determinismus: gleicher Seed + gleiche Eingaben -> gleicher Zustand.

Erfaesst: Spawn-Reihenfolge, U-Boot-Patrouillen, Sonar-Peilungsrauschen
(per-Entity sensor_seed), Welt-Wetter, ASM-Spawns.
"""

from src.core.game import Game

DT = 1.0 / 60.0


def _snap(g: Game):
    return (
        round(g.ship.x, 6), round(g.ship.y, 6),
        round(g.ship.course, 6), round(g.ship.speed, 6),
        round(g.sim_t, 6),
        g.world.sea_state,
        round(g.world.hour, 6),
        sorted((round(c.bearing, 3),
                round(c.range_est if c.range_est is not None else -1.0, 3),
                round(c.confidence, 3))
               for c in g.sonar.contacts.values()),
        [(round(s.x, 4), round(s.y, 4), s.state, round(s.depth, 3),
          s.torpedoes_left) for s in g.subs],
        [(a.atype.key, round(a.x, 4), round(a.y, 4), round(a.depth, 3),
          round(a.course, 3), round(a.speed, 3), a.rng.getstate())
         for a in g.animals],
        [(c.signature_key, round(c.x, 4), round(c.y, 4), round(c.course, 3),
          round(c.speed, 3), tuple(
              (key, controller.enabled, round(controller.next_scan_s, 6),
               controller.scan_index)
              for key, controller in sorted(c.sensor_suite.controllers.items())))
         for c in g.civilians],
        [(f.akey, round(f.x, 4), round(f.y, 4), round(f.course, 3),
          tuple((key, controller.enabled, round(controller.next_scan_s, 6),
                 controller.scan_index)
                for key, controller in sorted(f.sensor_suite.controllers.items())))
         for f in g.flights.flights],
        len(g.asms),
    )


def _run(seed: int) -> tuple:
    g = Game(seed=seed, start_menu=False)
    for i in range(300):
        if i == 60:
            g.ship.target_course = (g.ship.target_course + 45.0) % 360.0
        if i == 150:
            g.sonar_mode = "TOWED"
        if i == 220 and g.sonar.fire_ping():
            g.sonar.apply_ping(g.ship, g._sonar_targets(), g.world, g.sim_t,
                               range_factor=1.0, mode=g.sonar_mode)
        g.update(DT)
    return _snap(g)


def test_determinism_same_seed():
    assert _run(777) == _run(777)


def test_determinism_different_seed_differs():
    a = _run(777)
    b = _run(778)
    assert a != b
