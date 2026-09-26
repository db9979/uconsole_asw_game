"""Damage-control view: compartment schematic and teams (verbatim from
``stations_view``)."""


import pygame

from src.core import config
from src.core.i18n import localized, localize
from src.core.station import Station
from src.ship.damage import COMPARTMENTS
from src.ui import layout


from src.ui.stations.common import (
    STATE_LABEL,
    _compartment_name,
    _shortcut_footer,
    _state_color,
    _station_content_top,
    draw_station_page_tabs,
    message)


# --- Schadensbekämpfung (M5, M14) ------------------------------------------

def damage_regions(game=None, station_rect=None, page=0) -> dict:
    """Shared fictional deck-plan geometry in virtual-canvas coordinates.

    ``compartments`` preserves COMPARTMENTS/save ordering. Each entry contains
    a convex ``polygon``, a ``callout`` Rect and an interior ``anchor`` point.
    Callers must reject letterbox coordinates before using this API. Page 0
    shows the full-width plan; page 1 shows the selected-compartment detail.
    """
    if game is not None:
        layout.configure_for(game)
    station = pygame.Rect(station_rect or config.STATION_RECT)
    top = _station_content_top(station, 2)
    bottom = station.bottom - 58
    x0 = station.x + 16
    full_w = station.w - 32
    if page == 0:
        schematic = pygame.Rect(x0, top, full_w, max(1, bottom - top))
        detail = pygame.Rect(0, 0, 0, 0)
    else:
        detail_w = 760
        detail = pygame.Rect(station.centerx - detail_w // 2, top,
                             detail_w, max(1, bottom - top))
        schematic = pygame.Rect(0, 0, 0, 0)
    hull_w = min(200, int(max(schematic.w, detail.w) * .30))
    hull_center_x = (schematic.centerx if page == 0 else detail.centerx)
    hull_rect = pygame.Rect(hull_center_x - hull_w // 2, top + 40,
                            hull_w, max(1, bottom - top - 90))

    def points(coords):
        return tuple((round(hull_rect.x + x * hull_rect.w),
                      round(hull_rect.y + y * hull_rect.h)) for x, y in coords)

    hull = points(((.5, 0), (.82, .12), (1, .28), (1, .87),
                   (.87, 1), (.13, 1), (0, .87), (0, .28), (.18, .12)))
    polygons = {
        "bridge": ((.2, .27), (.8, .27), (.8, .37), (.2, .37)),
        "sonar": ((.35, .07), (.65, .07), (.82, .15), (.18, .15)),
        "weapons": ((.18, .16), (.82, .16), (.8, .26), (.2, .26)),
        "opz": ((.2, .38), (.8, .38), (.8, .49), (.2, .49)),
        "radio": ((.2, .5), (.8, .5), (.8, .6), (.2, .6)),
        "engine": ((.2, .61), (.8, .61), (.8, .73), (.2, .73)),
        "flightdeck": ((.2, .74), (.8, .74), (.86, .98), (.14, .98)),
        "hull_left": ((.02, .29), (.17, .29), (.17, .88), (.12, .96), (.02, .86)),
        "hull_right": ((.83, .29), (.98, .29), (.98, .86), (.88, .96), (.83, .88)),
    }
    # Callout order is spatial; the public mapping and keyboard order are not.
    left = ("sonar", "bridge", "opz", "engine", "hull_left")
    right = ("weapons", "radio", "flightdeck", "hull_right")
    ref_width = schematic.w if page == 0 else full_w
    compartments = {}
    if page == 0:
        for key, _ in COMPARTMENTS:
            side = left if key in left else right
            row = side.index(key)
            row_h = hull_rect.h // len(side)
            callout_w = int(ref_width * .28)
            callout_h = min(row_h - 5, max(48, layout.font(16).get_linesize() * 2 + 10))
            callout = pygame.Rect(schematic.x if side is left else schematic.right - callout_w,
                                  hull_rect.y + row * row_h, callout_w, callout_h)
            polygon = points(polygons[key])
            anchor = (sum(p[0] for p in polygon) // len(polygon),
                      sum(p[1] for p in polygon) // len(polygon))
            compartments[key] = {"polygon": polygon, "callout": callout, "anchor": anchor}
    features = {
        "gun": points(((.43, .085), (.57, .085), (.59, .13), (.41, .13))),
        "barrel": points(((.5, .085), (.5, .035))),
        "vls": points(((.32, .18), (.68, .18), (.68, .24), (.32, .24))),
        "mast": points(((.5, .4), (.5, .47), (.28, .435), (.72, .435))),
        "funnel": points(((.37, .63), (.63, .63), (.63, .7), (.37, .7))),
        "hangar": points(((.3, .76), (.7, .76), (.7, .83), (.3, .83))),
        "helipad": points(((.28, .86), (.72, .86), (.72, .95), (.28, .95))),
    }
    return {"station": station, "schematic": schematic, "detail": detail,
            "hull": hull, "features": features, "compartments": compartments,
            "footer": pygame.Rect(station.x + 16, station.bottom - 56, station.w - 32, 48)}


def damage_compartment_at(game, pos, page=0):
    """Return compartment ID for polygon OR callout, otherwise None; no mutation."""
    regions = damage_regions(game, page=page)
    if pos is None or not regions["station"].collidepoint(pos):
        return None
    for key, region in regions["compartments"].items():
        if region["callout"].collidepoint(pos):
            return key
        polygon = region["polygon"]
        crosses = [(b[0] - a[0]) * (pos[1] - a[1]) -
                   (b[1] - a[1]) * (pos[0] - a[0])
                   for a, b in zip(polygon, polygon[1:] + polygon[:1])]
        if all(v >= 0 for v in crosses) or all(v <= 0 for v in crosses):
            return key
    return None


@localized
def draw_damage_view(game, tr=None) -> None:
    layout.configure_for(game)
    from src.core.commands import STATION_PAGES
    s = game.screen
    pages = STATION_PAGES[Station.DAMAGE]
    page = int(getattr(game, "station_page", 0)) % len(pages)
    rect = pygame.Rect(config.STATION_RECT)
    layout.panel(s, rect, "station.damage.title")
    draw_station_page_tabs(s, rect, pages, page, tr)
    regions = damage_regions(game, page=page)
    items = list(game.damage.compartments.items())
    selected_key, selected = items[game.dmg_cursor]

    if page == 0:
        plan = regions["schematic"]
        layout.record_geometry("schematic", plan, "damage.schematic.title")
        layout.blit_line(s, "damage.schematic.title", (plan.x, plan.y, plan.w, 26),
                         config.COLOR_TEXT_DIM, size=16)
        pygame.draw.polygon(s, (12, 32, 34), regions["hull"])
        pygame.draw.polygon(s, (115, 161, 163), regions["hull"], 2)
        for i, (key, c) in enumerate(items):
            region = regions["compartments"][key]
            polygon, card, anchor = region["polygon"], region["callout"], region["anchor"]
            sc = _state_color(c.state)
            is_sel = i == game.dmg_cursor
            fill = ((57, 27, 26) if c.state == "ZERSTOERT" else
                    (34, 66, 83) if c.flood > 0 else (18, 42, 39))
            pygame.draw.polygon(s, fill, polygon)
            pygame.draw.polygon(s, config.COLOR_TEXT if is_sel else sc,
                                polygon, 3 if is_sel else 1)
            left_side = card.centerx < anchor[0]
            edge = card.midright if left_side else card.midleft
            endpoint = (min(p[0] for p in polygon) if left_side else max(p[0] for p in polygon),
                        anchor[1])
            pygame.draw.lines(s, sc, False,
                              (edge, (edge[0] + (10 if left_side else -10), edge[1]), endpoint), 1)
            pygame.draw.rect(s, (10, 22, 23), card)
            pygame.draw.rect(s, config.COLOR_TEXT if is_sel else sc, card,
                             2 if is_sel else 1)
            label = message("damage.schematic.callout", number=f"{i + 1:02}",
                            name=localize("damage.short." + key))
            line_h = layout.font(16).get_linesize() + 2
            layout.blit_line(s, label, (card.x + 6, card.y + 3, card.w - 12, line_h),
                             config.COLOR_TEXT, size=16)
            teams = game.damage.teams_on(key)
            markers = ("X" if c.state == "ZERSTOERT" else
                       "!" if c.state != "OK" else "OK")
            markers += (" ~" if c.flood > 0 else "") + (" ^" if c.fire > 0 else "")
            if teams:
                markers += " T" + ",".join(map(str, teams))
            layout.blit_line(s, markers, (card.x + 6, card.y + line_h + 3,
                                          card.w - 12, line_h), sc, size=15)
            ax, ay = anchor
            if c.state == "ZERSTOERT":
                pygame.draw.line(s, sc, (ax - 7, ay - 7), (ax + 7, ay + 7), 2)
                pygame.draw.line(s, sc, (ax - 7, ay + 7), (ax + 7, ay - 7), 2)
            if c.fire > 0:
                pygame.draw.polygon(s, (255, 155, 83),
                                    ((ax - 7, ay + 6), (ax, ay - 8), (ax + 7, ay + 6)), 2)
            if c.flood > 0:
                pygame.draw.lines(s, (132, 194, 223), False,
                                  ((ax - 9, ay + 9), (ax - 3, ay + 6),
                                   (ax + 3, ay + 9), (ax + 9, ay + 6)), 2)
        for name, pts in regions["features"].items():
            if name in ("barrel", "mast"):
                pygame.draw.lines(s, (124, 161, 163), False, pts, 2)
            else:
                pygame.draw.polygon(s, (124, 161, 163), pts, 1)
            if name in ("vls", "funnel", "hangar"):
                for step in range(1, 4):
                    fx = round(pts[0][0] + (pts[1][0] - pts[0][0]) * step / 4)
                    pygame.draw.line(s, (90, 125, 129), (fx, pts[0][1]),
                                     (fx, pts[2][1]), 1)
            if name == "helipad":
                bounds = pygame.Rect(pts[0], (pts[2][0] - pts[0][0],
                                              pts[2][1] - pts[0][1]))
                inset = bounds.inflate(-bounds.w // 2, -bounds.h // 3)
                pygame.draw.line(s, config.COLOR_TEXT_DIM, inset.topleft, inset.bottomleft, 1)
                pygame.draw.line(s, config.COLOR_TEXT_DIM, inset.topright, inset.bottomright, 1)
                pygame.draw.line(s, config.COLOR_TEXT_DIM, inset.midleft, inset.midright, 1)
        layout.blit_line(s, "damage.schematic.legend",
                         (plan.x, plan.bottom - 36, plan.w, 30),
                         config.COLOR_TEXT_DIM, size=16)
    else:
        detail = layout.box(s, regions["detail"],
                            "panel.selection_actions", border=_state_color(selected.state))
        dx, dy, dw, _ = detail
        layout.blit_line(s, _compartment_name(selected_key, selected.name),
                         (dx, dy, dw, 32), config.COLOR_TEXT, size=22)
        dy += 36
        for label, value, color in (
                ("ui.state", localize(STATE_LABEL[selected.state]), _state_color(selected.state)),
                ("ui.flooding", f"{selected.flood:.0f}%", config.COLOR_TEXT),
                ("ui.fire", f"{selected.fire:.0f}%", config.COLOR_DANGER if selected.fire else config.COLOR_TEXT_DIM)):
            layout.blit_line(s, localize(label), (dx, dy, 140, 26), config.COLOR_TEXT_DIM, size=18)
            layout.blit_line(s, value, (dx + 144, dy, dw - 144, 26), color, size=18)
            dy += 30
        trend = game.damage.compartment_trend(selected_key)
        for hazard in ("flood", "fire"):
            rate = trend[hazard + "_rate"]
            trend_key = ("damage.unrepairable" if not trend["repairable"] else
                         "damage.rising" if rate > .001 else
                         "damage.falling" if rate < -.001 else "damage.stable")
            layout.blit_line(s, message("damage.net." + hazard,
                trend=localize(trend_key), rate=f"{rate * 60:+.1f}"),
                (dx, dy, dw, 26), config.COLOR_WARN if rate > 0 else config.COLOR_TEXT_DIM, size=18)
            dy += 30
        pygame.draw.line(s, config.COLOR_GRID, (dx, dy), (dx + dw, dy))
        dy += 14
        assignment = game.damage.teams[game.dmg_team]
        assignment_text = (_compartment_name(assignment, game.damage.compartments[assignment].name)
                           if assignment is not None else localize("damage.free"))
        layout.blit_line(s, message("damage.team_destination", team=game.dmg_team,
                                    destination=assignment_text),
                         (dx, dy, dw, 32), config.COLOR_OK, size=18)
        dy += 36
        assigned = game.damage.teams_on(selected_key)
        layout.blit_line(s, "ui.on_scene", (dx, dy, 120, 26), config.COLOR_TEXT_DIM, size=18)
        layout.blit_line(s, message("damage.line.teams_on_scene", teams=", ".join(map(str, assigned)))
                         if assigned else "damage.line.no_team", (dx + 124, dy, dw - 124, 26),
                         config.COLOR_OK if assigned else config.COLOR_WARN, size=18)
        dy += 30
        layout.blit_block(s, "control.damage_team",
                          dx, dy, dw, max(1, regions["detail"].bottom - dy - 8), config.COLOR_TEXT, size=18)

    footer_y = rect.bottom - 52
    layout.status_line(
        s, rect.x + 16, footer_y, rect.w - 32, "panel.total_flooding",
         message("damage.line.total", total=f"{game.damage.total:3.0f}",
                 maximum=len(game.damage.compartments) * 100,
                 average=f"{game.damage.avg_flood():.0f}"),
        color=config.COLOR_DANGER if game.damage.ship_sunk else config.COLOR_TEXT,
        label_w=190, size=17)
    _shortcut_footer(s, (rect.x + 16, footer_y + 26, rect.w - 32, 19), (
        ("←/→", "damage.footer.department"),
        ("↑/↓", "damage.footer.team"),
        ("Enter", "damage.footer.assign"),
        ("Backspace", "damage.footer.withdraw"),
    ))
