"""A detonation close to the own ship shakes its screens (display only)."""

import sys
from pathlib import Path

import pygame

from src.core import shock
from src.ui import shock_fx
from src.ui.shock_fx import ShockFx

sys.path.insert(0, str(Path(__file__).parent))
from test_opfor_sub import _crewed  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _kinds(rows):
    return [row["kind"] for row in rows]


def test_the_shock_cue_follows_the_distance():
    assert shock.cue(0.0) == "shock_heavy"
    assert shock.cue(shock.HEAVY_NM) == "shock_heavy"
    assert shock.cue(shock.HEAVY_NM + 0.01) == "shock_light"
    assert shock.cue(shock.LIGHT_NM) == "shock_light"
    assert shock.cue(shock.LIGHT_NM + 0.01) is None


def test_the_frigate_and_the_boat_feel_close_detonations_only():
    game, _server, _bridge = _crewed(seed=62)
    boat, ship = game.opfor, game.ship
    game._emit_sound("explosion", at=(ship.x + 0.1, ship.y))
    game._emit_sound("explosion", at=(ship.x + 0.4, ship.y))
    game._emit_sound("explosion", at=(ship.x + 3.0, ship.y))
    frigate = _kinds(game._sound_events)
    assert frigate.count("shock_heavy") == 1 and frigate.count("shock_light") == 1
    seqs = [row["seq"] for row in game._sound_events]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
    sub = boat.sub
    before = len(boat.sound_events)
    game._emit_sound("explosion", at=(sub.x, sub.y + 0.05))
    game._emit_sound("explosion", at=(sub.x + 1.5, sub.y))
    assert _kinds(boat.sound_events)[before:] == ["detonation_near", "shock_heavy",
                                                  "detonation_near"]


def test_the_effect_plays_on_wall_time_and_starts_quiet_in_a_new_world():
    fx = ShockFx()
    rows = [dict(seq=1, kind="explosion"), dict(seq=2, kind="shock_heavy")]
    fx.pump("a", rows, 10.0)
    assert fx.started is None            # a new world only sets the mark
    rows.append(dict(seq=3, kind="shock_light"))
    rows.append(dict(seq=4, kind="shock_heavy"))
    fx.pump("a", rows, 11.0)
    assert fx.kind == "shock_heavy" and fx.strength(11.0) == 1.0
    assert fx.offset(11.0) == (0, 0) or fx.strength(11.05) > 0.0
    assert fx.strength(11.0 + shock_fx.DURATION_S["shock_heavy"] + 0.01) == 0.0
    assert fx.active(11.0 + 5.0)          # the cracked glass fades slowly
    assert not fx.active(11.0 + shock_fx.CRACK_S + 1.0)
    fx.pump("b", rows, 12.0)
    assert fx.started is None


def test_the_effect_draws_and_the_low_level_does_not_shake():
    surface = pygame.Surface((1280, 720))
    surface.fill((200, 200, 200))
    fx = ShockFx()
    fx.pump("a", [], 0.0)
    fx.pump("a", [dict(seq=1, kind="shock_heavy")], 1.0)
    fx.draw(surface, 1.02)
    assert surface.get_at((640, 700))[:3] != (200, 200, 200)
    low = pygame.Surface((1280, 720))
    low.fill((200, 200, 200))
    fx.draw(low, 1.02, low=True)
    top = low.get_at((0, 0))
    assert top[0] > top[1]                # dimmed towards red, not moved


def test_the_browser_knows_the_shock_cues():
    shared = (ROOT / "data/commander/js/state/shared.js").read_text(encoding="utf-8")
    for cue in shock.CUES:
        assert f'"{cue}"' in shared
    bindings = (ROOT / "data/commander/js/app/bindings.js").read_text(encoding="utf-8")
    assert "syncShock(state)" in bindings
