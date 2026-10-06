"""The Bridge charts (uConsole and browser) draw one track per contact: radar
and lookout reports of the same ship that the OPZ fused stand behind their
fusion (bug report 2026-10-06: every convoy ship appeared twice)."""

import math

import pygame
import pytest

from src.commander.bridge import CommanderBridge
from src.core.game import Game
from src.core.station import Station
from src.ui import chart_trails, map_view
from test_commander_bridge import Server


def _close_pairs(points, limit_nm=0.4):
    return sum(1 for index, first in enumerate(points) for second in points[index + 1:]
               if math.hypot(first[0] - second[0], first[1] - second[1]) < limit_nm)


@pytest.fixture(scope="module")
def convoy():
    game = Game(seed=3, start_menu=False, audio_enabled=False)
    game.start_new_game("s7_geleitzug", "fixed", seed=3)
    game.surface_radar_on = True
    for _ in range(int(120 / 0.25)):
        game._update_sim(0.25)
    return game


def test_radar_and_lookout_reports_of_one_ship_chart_once(convoy):
    raw = [(t["x"], t["y"]) for t in convoy.radar_tracks()
           if t["kind"] == "SURFACE" and t["x"] is not None]
    charted = [t for t in convoy.chart_tracks()
               if t["kind"] == "SURFACE" and t["x"] is not None]
    # The picture itself keeps one report per sensor (radar and lookout) ...
    assert _close_pairs(raw) >= 2
    # ... the chart draws each ship once, as the fused OPZ contact.
    assert _close_pairs([(t["x"], t["y"]) for t in charted]) == 0
    fused = [t for t in charted if t["source"] == "FUSION"]
    assert fused and all(t["track_id"].startswith("F-") for t in fused)
    published = {item.observation_id: item for item in convoy.opz_published_observations()}
    for track in fused:
        assert track["label"] == published[track["track_id"]].label
        assert track["lead"] in track["members"]
    members = {member for t in fused for member in t["members"]}
    assert not members & {t["track_id"] for t in charted}


def test_bridge_chart_draws_and_tooltips_the_fusion(convoy):
    convoy.station = Station.BRIDGE
    convoy.screen = pygame.Surface((1280, 720))
    labels = []
    original = map_view._map_label

    def record(surface, game, text, *args, **kwargs):
        labels.append(str(text))
        return original(surface, game, text, *args, **kwargs)

    map_view._map_label = record
    try:
        map_view.draw_map_view(convoy)
    finally:
        map_view._map_label = original
    fused = [t for t in convoy.chart_tracks() if t["source"] == "FUSION"]
    for track in fused:
        assert any(track["label"] in label for label in labels)
    hidden = {t["track_id"][-6:] for t in convoy.radar_tracks()
              if any(t["track_id"] in f["members"] for f in fused)}
    assert not any(label in hidden for label in labels)


def test_fused_reports_keep_one_trail():
    tracks = [dict(track_id="F-01", members=("A", "B"), lead="A"),
              dict(track_id="C")]
    assert map_view.fused_trail_keys(tracks) == frozenset({("track", "B")})

    class Side:
        own = []
        tracks = {("track", "A"): [(0, 1.0, 1.0), (1, 1.1, 1.0)],
                  ("track", "B"): [(0, 1.0, 1.0), (1, 1.1, 1.0)]}

        @staticmethod
        def bearing_history(_key):
            return ()

    drawn = []
    original = chart_trails.draw_track_history
    chart_trails.draw_track_history = lambda surface, rows, *rest: drawn.append(rows)
    try:
        chart_trails.draw_side(None, Side, None, (0, 0, 10, 10), (0, 0, 0),
                               hidden_keys=frozenset({("track", "B")}))
    finally:
        chart_trails.draw_track_history = original
    assert drawn == [Side.tracks[("track", "A")]]


def test_browser_bridge_lists_each_ship_once(convoy):
    bridge, server = CommanderBridge(), Server()
    bridge.pump(convoy, server, now=10.0)
    rows = server.v2_states["bridge"]["bridge"]["tactical_summary"]
    opz = server.v2_states["opz"]["opz"]
    fused_members = {ref for fusion in opz["fusions"] for ref in fusion["members"]}
    refs = [row["ref"] for row in rows]
    assert len(refs) == len(set(refs))
    assert not fused_members & set(refs)
    assert any(row["source"] == "FUSION" for row in rows)
    surface = [(row["x"], row["y"]) for row in rows
               if row["domain"] == "SURFACE" and row["x"] is not None]
    assert _close_pairs(surface) == 0
    # The lookout's sighting stays with the fused row.
    assert any(row["source"] == "FUSION" and row["visual_class"] is not None
               for row in rows)


def test_unfused_radar_and_lookout_reports_of_one_ship_chart_once():
    """Bug report 2026-10-06 ("doppelte Anzeige"): before the OPZ fused
    them (their first motion estimates still disagree), a radar and a
    lookout report of the same convoy ship showed as two labelled tracks
    with two vectors. The chart draws them as one contact; two ships a
    cable apart seen by the same sensor stay two."""
    from src.sensors.fusion import merge_chart_reports

    def item(key, family, x, y, quality=.8, fused=False, domain="SURFACE"):
        return dict(key=key, families={family}, domain=domain, x=x, y=y,
                    range_nm=1.4, fused=fused, quality=quality)

    joined = merge_chart_reports([
        item("L-1", "VISUAL", 1.00, 1.00, .6), item("S-1", "RADAR", 1.05, 0.98, .9),
        item("L-2", "VISUAL", -1.0, 1.0), item("S-2", "RADAR", -1.03, 1.02, .9),
        item("S-3", "RADAR", 3.0, 3.0), item("S-4", "RADAR", 3.1, 3.0),
        item("L-5", "VISUAL", 5.0, 5.0, domain="AIR"), item("S-5", "RADAR", 5.0, 5.0)])
    # The better report leads; same-sensor echoes and other domains stay apart.
    assert joined == {"L-1": "S-1", "L-2": "S-2"}
    # Two radar echoes equally close leave a lookout report alone (ambiguous).
    assert merge_chart_reports([item("S-6", "RADAR", 0, 0), item("S-7", "RADAR", .15, 0),
                                item("L-6", "VISUAL", .07, 0)]) == {}


def test_bridge_chart_draws_an_unfused_report_pair_once():
    game = Game(seed=3, start_menu=False, audio_enabled=False)
    ship = game.ship
    rows = [dict(kind="SURFACE", track_id="L-1", target_id=0, source="LOOKOUT",
                 x=ship.x + 1.0, y=ship.y - 1.0, course=245.0, speed_kn=186.0,
                 label="805A5F", quality=.6, visual="x"),
            dict(kind="SURFACE", track_id="S-1", target_id=0, source="RADAR-S",
                 x=ship.x + 1.03, y=ship.y - 0.98, course=90.0, speed_kn=8.0,
                 label="6A8DB5", quality=.9, visual=None)]
    game.radar_tracks = lambda: [dict(row) for row in rows]
    charted = [t for t in game.chart_tracks() if t["x"] is not None]
    assert [t["track_id"] for t in charted] == ["S-1"]
    assert charted[0]["members"] == ("S-1", "L-1") and charted[0]["lead"] == "S-1"
    assert charted[0]["visual"] == "x"
    assert map_view.fused_trail_keys(charted) == frozenset({("track", "L-1")})
