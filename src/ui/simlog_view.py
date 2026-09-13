"""F4: Live-Simulationsprotokoll-Ansicht (Vollbild, Simulation laeuft weiter).

Diagnose-Ansicht: nur mit aktivierter simlog-Option (F10) oeffenbar. Sie
liest den aktuellen Simulationszustand direkt (gleiche Struktur wie
Game._simlog_state_data()) und das aufgezeichnete Ereignisprotokoll. Sie ist
keine Workstation: kein Targeting, rein lesend, ohne Input-Effekt auf die
Simulation.
"""

import pygame

from src.core import config
from src.core.i18n import display_value, localize
from src.ui import layout


EVENT_TAIL = 80
SECTION = "section"
ROW = "row"
DIM = "dim"
ACCENT = "accent"
DANGER = "danger"

_COLORS = {
    SECTION: config.COLOR_WARN,
    ROW: config.COLOR_TEXT,
    DIM: config.COLOR_TEXT_DIM,
    ACCENT: config.COLOR_OK,
    DANGER: config.COLOR_DANGER,
}


def _f(value, digits=1):
    return "-" if value is None else f"{float(value):.{digits}f}"


def _i(value):
    return "-" if value is None else str(int(value))


def _b(value, tr):
    return tr("common.yes") if value else tr("common.no")


def _table(title, headers, rows, danger=()):
    """Left-aligned monospace table; column width = widest cell per column.

    ``danger`` is a bool list aligned with ``rows``; flagged rows are drawn
    in the danger color.
    """
    lines = [(f"{title} ({len(rows)})", SECTION)]
    if not rows:
        return lines + [("", ROW)]
    widths = [max(len(headers[i]), *(len(row[i]) for row in rows))
              for i in range(len(headers))]
    header = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    lines.append(("  " + header, DIM))
    for index, row in enumerate(rows):
        text = "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))
        kind = DANGER if index < len(danger) and danger[index] else ROW
        lines.append(("  " + text.rstrip(), kind))
    lines.append(("", ROW))
    return lines


def _unit_tables(snap, tr):
    out = []
    col = {name: tr(f"simlog.view.col_{name}")
           for name in ("kind", "depth", "course", "speed", "state", "torps",
                        "damage", "sunk", "dead", "target", "life", "battery",
                        "active", "jammer", "phase", "pending_asm")}
    out += _table(
        tr("simlog.view.subs"),
        ("ID", "X", "Y", col["depth"], col["course"], col["speed"],
         col["state"], col["torps"], col["sunk"]),
        [(_i(s["id"]), _f(s["x"]), _f(s["y"]), _f(s["depth"]), _f(s["course"]),
          _f(s["speed"]), str(s["state"]), _i(s["torps"]),
          _b(s["sunk"], tr))
         for s in snap["subs"]],
        danger=[bool(s["sunk"]) for s in snap["subs"]],
    )
    out += _table(
        tr("simlog.view.surfaces"),
        ("ID", "X", "Y", col["course"], col["speed"], col["damage"],
         col["sunk"]),
        [(_i(w["id"]), _f(w["x"]), _f(w["y"]), _f(w["course"]),
          _f(w["speed"]), _f(w["damage"]), _b(w["sunk"], tr))
         for w in snap["surfaces"]],
        danger=[bool(w["sunk"]) for w in snap["surfaces"]],
    )
    out += _table(
        tr("simlog.view.torps"),
        ("ID", "X", "Y", col["depth"], col["course"], col["state"],
         col["target"]),
        [(_i(t["id"]), _f(t["x"]), _f(t["y"]), _f(t["depth"]), _f(t["course"]),
          str(t["state"]), _i(t["target"]))
         for t in snap["torpedoes"]],
    )
    out += _table(
        tr("simlog.view.enemy_torps"),
        ("ID", "X", "Y", col["depth"], col["course"], col["state"]),
        [(_i(t["id"]), _f(t["x"]), _f(t["y"]), _f(t["depth"]),
          _f(t["course"]), str(t["state"]))
         for t in snap["enemy_torpedoes"]],
    )
    out += _table(
        tr("simlog.view.decoys"),
        ("ID", "X", "Y", col["depth"], col["life"], col["dead"]),
        [(_i(d["id"]), _f(d["x"]), _f(d["y"]), _f(d["depth"]), _f(d["life"]),
          _b(d["dead"], tr))
         for d in snap["decoys"]],
        danger=[bool(d["dead"]) for d in snap["decoys"]],
    )
    out += _table(
        tr("simlog.view.asms"),
        ("SEQ", "X", "Y", col["course"], col["state"], col["jammer"]),
        [(_i(a["seq"]), _f(a["x"]), _f(a["y"]), _f(a["course"]),
          str(a["state"]), _b(a["jammer"], tr))
         for a in snap["asms"]],
    )
    out += _table(
        tr("simlog.view.essms"),
        ("SEQ", "X", "Y", col["course"], col["state"]),
        [(_i(e["seq"]), _f(e["x"]), _f(e["y"]), _f(e["course"]),
          str(e["state"]))
         for e in snap["essms"]],
    )
    out += _table(
        tr("simlog.view.asrocs"),
        ("SEQ", "X", "Y", col["course"], col["state"]),
        [(_i(a["seq"]), _f(a["x"]), _f(a["y"]), _f(a["course"]),
          str(a["state"]))
         for a in snap["asrocs"]],
    )
    out += _table(
        tr("simlog.view.nixies"),
        ("SEQ", "X", "Y", col["depth"], col["dead"]),
        [(_i(n["seq"]), _f(n["x"]), _f(n["y"]), _f(n["depth"]),
          _b(n["dead"], tr))
         for n in snap["nixies"]],
        danger=[bool(n["dead"]) for n in snap["nixies"]],
    )
    out += _table(
        tr("simlog.view.buoys"),
        ("SEQ", "X", "Y", col["battery"], col["active"]),
        [(_i(b["seq"]), _f(b["x"]), _f(b["y"]), _f(b["battery_s"]),
          _b(b["active"], tr))
         for b in snap["buoys"]],
    )
    out += _table(
        tr("simlog.view.flights"),
        ("SEQ", "Kind", "X", "Y", col["course"]),
        [(_i(f["seq"]), str(f["kind"]), _f(f["x"]), _f(f["y"]),
          _f(f["course"]))
         for f in snap["flights"]],
    )
    out += _table(
        tr("simlog.view.raiders"),
        ("SEQ", "X", "Y", col["course"], col["phase"], "HP",
         col["pending_asm"]),
        [(_i(r["seq"]), _f(r["x"]), _f(r["y"]), _f(r["course"]),
          str(r["phase"]), _i(r["hp"]), _b(r["pending_asm"], tr))
         for r in snap["raiders"]],
    )
    helo = snap["helo"]
    out += _table(
        tr("simlog.view.helo"),
        (col["state"], "X", "Y", col["active"]),
        [(str(helo["state"]), _f(helo["x"]), _f(helo["y"]),
          _b(helo["airborne"], tr))],
    )
    out += _table(
        tr("simlog.view.animals"),
        ("ID", "X", "Y", col["dead"]),
        [(_i(a["id"]), _f(a["x"]), _f(a["y"]), _b(a["dead"], tr))
         for a in snap["animals"]],
        danger=[bool(a["dead"]) for a in snap["animals"]],
    )
    return out


def _events_lines(game, tr, face, width):
    events = [row for row in game.simlog if row.get("cat") != "state"]
    events = events[-EVENT_TAIL:]
    lines = [(tr("simlog.view.events"), SECTION)]
    if not events:
        lines.append((tr("simlog.view.no_events"), DIM))
        lines.append(("", ROW))
        return lines
    for row in events:
        text = (f"[{row['stamp']}] [{row['cat'].upper()}] "
                f"{localize(row['text'], tr)}")
        lines.append((layout.ellipsize(text, face, width - 40), ROW))
    lines.append(("", ROW))
    return lines


def _build_lines(game, tr):
    face = layout.font(15)
    snap = game._simlog_state_data()
    ship = snap["ship"]
    world = snap["world"]
    weapons = snap["weapons"]
    lines = [
        (tr("simlog.view.own"), SECTION),
        (f"  X {_f(ship['x'])}  Y {_f(ship['y'])}  "
         f"{tr('simlog.view.col_course')} {_f(ship['course'])}  "
         f"{tr('simlog.view.col_speed')} {_f(ship['speed'])}  "
         f"{tr('simlog.view.col_damage')} {_f(ship['damage'])}%  "
         f"{tr('simlog.view.col_sunk')}: {_b(ship['sunk'], tr)}", ACCENT),
    ]
    down = [key for key, value in ship["stations"].items() if value]
    if down:
        names = ", ".join(display_value("station", key, tr) for key in down)
        lines.append((f"  {tr('simlog.view.stations_down')}: {names}", DANGER))
    lines.append(("", ROW))
    lines.append((tr("simlog.view.world"), SECTION))
    lines.append((f"  {tr('simlog.view.world_time')} {_f(world['hour'])}  "
                  f"{tr('simlog.view.sea_state')} {world['sea_state']}  "
                  f"{tr('simlog.view.night')}: {_b(world['night'], tr)}  "
                  f"T+{snap['mission_t']:.0f}s  x{game.time_scale}  "
                  f"{tr('simlog.view.result')}: {snap['result'] or '-'}", ROW))
    lines.append(("", ROW))
    lines.append((tr("simlog.view.weapons"), SECTION))
    lines.append((f"  {tr('simlog.view.torpedoes')} {weapons['torpedoes']}  "
                  f"{tr('simlog.view.vls')} {weapons['vls']}  "
                  f"{tr('simlog.view.ciws')} {weapons['ciws']}  "
                  f"{tr('simlog.view.aa')} {weapons['aa']}  "
                  f"{tr('simlog.view.chaff_cd')} "
                  f"{_f(weapons['chaff_cd'])}s", ROW))
    lines.append(("", ROW))
    lines += _unit_tables(snap, tr)
    width = config.SCREEN_W - 48
    lines += _events_lines(game, tr, face, width)
    return lines


def draw_simlog_view(game) -> None:
    """Vollbild-Protokoll: Header, scrollbarer Live-Status, Fusszeile."""
    layout.configure_for(game)
    s = game.screen
    s.fill(config.COLOR_BG)
    tr = game.tr
    face = layout.font(15)
    line_h = int(face.get_linesize() * 1.15)
    title_face = layout.font(18, bold=True)
    top = pygame.Rect(0, 0, config.SCREEN_W, 44)
    pygame.draw.rect(s, (14, 24, 18), top)
    pygame.draw.line(s, config.COLOR_SONAR_RING, (0, top.bottom),
                     (config.SCREEN_W, top.bottom), 1)
    s.blit(title_face.render(tr("simlog.view.title"), True, config.COLOR_TEXT),
           (16, 10))
    live_face = layout.font(13)
    live = live_face.render(tr("simlog.view.live_note"), True, config.COLOR_OK)
    s.blit(live, (config.SCREEN_W - live.get_width() - 16, 14))
    footer_h = 36
    body = pygame.Rect(12, top.bottom + 4, config.SCREEN_W - 24,
                       config.SCREEN_H - top.bottom - footer_h - 12)
    lines = _build_lines(game, tr)
    visible = max(1, body.height // line_h)
    max_scroll = max(0, len(lines) - visible)
    game.simlog_view_scroll = min(game.simlog_view_scroll, max_scroll)
    with layout.clip_to(s, body):
        for index, (text, kind) in enumerate(
                lines[game.simlog_view_scroll:
                     game.simlog_view_scroll + visible]):
            if not text:
                continue
            y = body.y + index * line_h
            color = _COLORS.get(kind, config.COLOR_TEXT)
            image = layout.font(15, bold=kind == SECTION).render(text, True,
                                                                 color)
            s.blit(image, (body.x, y))
    hints = (f"{tr('simlog.view.close_hint')}   "
             f"{tr('simlog.view.scroll_hint')}")
    hint = layout.font(13).render(hints, True, config.COLOR_TEXT_DIM)
    s.blit(hint, (16, config.SCREEN_H - footer_h + 8))
