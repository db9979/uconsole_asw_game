"""Damage-control view: compartment schematic and teams (verbatim from
``stations_view``)."""


import pygame

from src.ui import theme

from src.core import config
from src.core.i18n import localized, localize, raw_text
from src.core.station import Station
from src.ship.damage import COMPARTMENTS
from src.ui import console, damage_section, layout, pointer


from src.ui.stations.common import (
    STATE_LABEL,
    _compartment_name,
    _shortcut_footer,
    _state_color,
    _station_content_top,
    draw_station_page_tabs,
    message)


# --- Schadensbekämpfung (M5, M14) ------------------------------------------

# Lamp cards under the profile, stern to bow, then the hull voids.
CARD_ORDER = ("flightdeck", "engine", "radio", "opz", "weapons",
              "bridge", "sonar", "hull_left", "hull_right")
# Selection page of a wide station: compartment cards left, the selected
# compartment in the middle, the repair teams right (px).
DAMAGE_CARDS_W = 320
DAMAGE_TEAMS_W = 300
TEAM_CARD_H = 50
TEAM_CARD_PITCH = 56


def damage_regions(game=None, station_rect=None, page=0) -> dict:
    """Shared fictional side-profile geometry in virtual-canvas coordinates.

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
    cards = teams = pygame.Rect(0, 0, 0, 0)
    if page == 0:
        schematic = pygame.Rect(x0, top, full_w, max(1, bottom - top))
        detail = pygame.Rect(0, 0, 0, 0)
    elif station.w >= 1000:
        gap = 10
        height = max(1, bottom - top)
        cards = pygame.Rect(x0, top, DAMAGE_CARDS_W, height)
        teams = pygame.Rect(x0 + full_w - DAMAGE_TEAMS_W, top, DAMAGE_TEAMS_W, height)
        detail = pygame.Rect(cards.right + gap, top, teams.x - gap - cards.right - gap, height)
        schematic = pygame.Rect(0, 0, 0, 0)
    else:
        detail_w = 760
        detail = pygame.Rect(station.centerx - detail_w // 2, top,
                             detail_w, max(1, bottom - top))
        schematic = pygame.Rect(0, 0, 0, 0)
    compartments = {}
    profile = section = pygame.Rect(0, 0, 0, 0)
    if page == 0:
        # Side profile over a grid of lamp cards; the cross-section with both
        # hull voids beside the profile (bow right, like the plan aboard).
        cols = 5 if schematic.w >= 900 else 3
        rows = -(-len(COMPARTMENTS) // cols)
        line_h = layout.font(16).get_linesize() + 2
        card_h = max(44, line_h * 2 + 8)
        gap = 6
        legend_h = 28
        title_h = 26
        cards_top = schematic.bottom - legend_h - rows * card_h - (rows - 1) * gap
        art = pygame.Rect(schematic.x, schematic.y + title_h, schematic.w,
                          max(40, cards_top - gap - schematic.y - title_h))
        section_w = max(90, min(art.w // 5, art.h))
        profile = pygame.Rect(art.x, art.y, art.w - section_w - gap, art.h)
        section = pygame.Rect(profile.right + gap, art.y, section_w, art.h)
        heel = float(game.damage.list_deg()) if game is not None and hasattr(game, "damage") else 0.0
        draft = float(getattr(getattr(game, "damage", None), "draft_m", 7.5))
        polygons = damage_section.frigate_room_polygons(profile, section, heel, draft)
        card_w = (schematic.w - (cols - 1) * gap) // cols
        for index, key in enumerate(CARD_ORDER):
            col, row = index % cols, index // cols
            callout = pygame.Rect(schematic.x + col * (card_w + gap),
                                  cards_top + row * (card_h + gap), card_w, card_h)
            polygon = polygons[key]
            anchor = (sum(p[0] for p in polygon) // len(polygon),
                      sum(p[1] for p in polygon) // len(polygon))
            compartments[key] = {"polygon": polygon, "callout": callout, "anchor": anchor}
        compartments = {key: compartments[key] for key, _ in COMPARTMENTS}
    return {"station": station, "schematic": schematic, "detail": detail,
            "cards": cards, "teams": teams, "profile": profile, "section": section, "compartments": compartments,
            "footer": pygame.Rect(station.x + 16, station.bottom - 56, station.w - 32, 48)}


def damage_selection_cards(game, station_rect=None) -> list:
    """(compartment key, rect) of every card in the left column of the
    selection page; empty on a narrow station."""
    column = damage_regions(game, station_rect or config.FULL_STATION_RECT, page=1)["cards"]
    if column.w <= 0:
        return []
    keys = list(game.damage.compartments)
    pitch = max(1, (column.h - 42) // len(keys))
    return [(key, pygame.Rect(column.x + 6, column.y + 36 + index * pitch,
                              column.w - 12, pitch - 4))
            for index, key in enumerate(keys)]


def damage_team_cards(game, station_rect=None) -> list:
    """(team number, rect) of the repair-team cards in the right column."""
    column = damage_regions(game, station_rect or config.FULL_STATION_RECT, page=1)["teams"]
    if column.w <= 0:
        return []
    return [(team, pygame.Rect(column.x + 6, column.y + 36 + index * TEAM_CARD_PITCH,
                               column.w - 12, TEAM_CARD_H))
            for index, team in enumerate(sorted(game.damage.teams))]


def damage_compartment_at(game, pos, page=0):
    """Return compartment ID for polygon OR callout, otherwise None; no mutation."""
    if page not in (0, 1):
        return None
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

    if page == 2:
        _draw_crew(game, s, rect)
        return
    if page == 0:
        plan = regions["schematic"]
        layout.record_geometry("schematic", plan, "damage.schematic.title")
        layout.blit_line(s, "damage.schematic.title", (plan.x, plan.y, plan.w, 26),
                         config.COLOR_TEXT_DIM, size=16)
        selected_room = selected_key
        damage_section.draw_frigate_profile(s, regions["profile"], game.damage, selected_room)
        damage_section.draw_frigate_section(s, regions["section"], game.damage, selected_room)
        layout.record_geometry("schematic", regions["profile"], "damage.profile.title")
        sec = regions["section"]
        layout.blit_line(s, message("damage.section.list", list=f"{game.damage.list_deg():+.1f}"),
                         (sec.x, sec.bottom - 20, sec.w, 20),
                         config.COLOR_WARN if abs(game.damage.list_deg()) >= 5.0
                         else config.COLOR_TEXT_DIM, size=14, align="center")
        prof = regions["profile"]
        layout.blit_line(s, message("damage.profile.draft",
                                    draft=f"{float(getattr(game.damage, 'draft_m', 7.5)):.1f}",
                                    trim=f"{game.damage.trim_deg():+.1f}"),
                         (prof.x + 4, prof.bottom - 20, prof.w // 2, 20), theme.c("info"), size=14)
        line_h = layout.font(16).get_linesize() + 2
        for i, (key, c) in enumerate(items):
            card = regions["compartments"][key]["callout"]
            _draw_callout(game, s, card, i, key, c, i == game.dmg_cursor, line_h)
            pointer.add_hotspot(card)       # damage_compartment_at takes the click
        _draw_legend(s, pygame.Rect(plan.x, plan.bottom - 30, plan.w, 24))
    else:
        if regions["cards"].w > 0:
            _draw_selection_cards(game, s, regions["cards"], rect)
            _draw_team_cards(game, s, regions["teams"], rect)
        detail = layout.box(s, regions["detail"],
                            "panel.selection_actions", border=_state_color(selected.state))
        dx, dy, dw, _ = detail
        layout.blit_line(s, _compartment_name(selected_key, selected.name),
                         (dx, dy, dw, 32), config.COLOR_TEXT, size=22)
        dy += layout.line_pitch(22)
        row = layout.line_pitch(18, gap=3)
        for label, value, color in (
                ("ui.state", localize(STATE_LABEL[selected.state]), _state_color(selected.state)),
                ("ui.flooding", f"{selected.flood:.0f}%", config.COLOR_TEXT),
                ("ui.fire", f"{selected.fire:.0f}%", config.COLOR_DANGER if selected.fire else config.COLOR_TEXT_DIM)):
            layout.blit_line(s, localize(label), (dx, dy, 140, row), config.COLOR_TEXT_DIM, size=18)
            layout.blit_line(s, value, (dx + 144, dy, dw - 144, row), color, size=18)
            dy += row
        trend = game.damage.compartment_trend(selected_key)
        for hazard in ("flood", "fire"):
            rate = trend[hazard + "_rate"]
            trend_key = ("damage.unrepairable" if not trend["repairable"] else
                         "damage.rising" if rate > .001 else
                         "damage.falling" if rate < -.001 else "damage.stable")
            layout.blit_line(s, message("damage.net." + hazard,
                trend=localize(trend_key), rate=f"{rate * 60:+.1f}"),
                (dx, dy, dw, row), config.COLOR_WARN if rate > 0 else config.COLOR_TEXT_DIM, size=18)
            dy += row
        pygame.draw.line(s, config.COLOR_GRID, (dx, dy), (dx + dw, dy))
        dy += 14
        assignment = game.damage.teams[game.dmg_team]
        assignment_text = (_compartment_name(assignment, game.damage.compartments[assignment].name)
                           if assignment is not None else localize("damage.free"))
        layout.blit_line(s, message("damage.team_destination", team=game.dmg_team,
                                    destination=assignment_text),
                         (dx, dy, dw, row), config.COLOR_OK, size=18)
        dy += row + 4
        assigned = game.damage.teams_on(selected_key)
        layout.blit_line(s, "ui.on_scene", (dx, dy, 120, row), config.COLOR_TEXT_DIM, size=18)
        layout.blit_line(s, message("damage.line.teams_on_scene", teams=", ".join(map(str, assigned)))
                         if assigned else "damage.line.no_team", (dx + 124, dy, dw - 124, row),
                         config.COLOR_OK if assigned else config.COLOR_WARN, size=18)
        dy += row
        room = game.damage.counterflood_room
        layout.blit_line(s, message(
            "damage.line.stability", list=f"{game.damage.list_deg():+.1f}",
            trim=f"{game.damage.trim_deg():+.1f}",
            room=(localize("damage.counterflood.none") if room is None
                  else _compartment_name(room, game.damage.compartments[room].name))),
            (dx, dy, dw, row), config.COLOR_WARN if room is not None else config.COLOR_TEXT_DIM,
            size=16)

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



def _pick_compartment(game, key) -> None:
    game.dmg_cursor = list(game.damage.compartments).index(key)


def _pick_team(game, team) -> None:
    game.dmg_team = team


def _card_frame(s, card, chosen, stripe) -> None:
    pygame.draw.rect(s, config.COLOR_TAB_ACTIVE if chosen else theme.c("raised"),
                     card, border_radius=4)
    pygame.draw.rect(s, theme.c("focus") if chosen else theme.c("line"),
                     card, 2 if chosen else 1, border_radius=4)
    pygame.draw.rect(s, stripe, (card.x + 3, card.y + 5, 3, card.h - 10))


def _draw_selection_cards(game, s, column, station_rect) -> None:
    """Left column of the selection page: one card per compartment (state
    stripe, name, water and fire, teams on scene); a click selects it."""
    layout.box(s, column, "damage.panel.compartments")
    for index, (key, card) in enumerate(damage_selection_cards(game, station_rect)):
        c = game.damage.compartments[key]
        chosen = index == game.dmg_cursor
        _card_frame(s, card, chosen, _state_color(c.state))
        two_lines = card.h >= 42
        name_w = card.w - 18 - (0 if two_lines else 104)
        layout.blit_line(s, message("damage.schematic.callout", number=f"{index + 1:02}",
                                    name=localize("damage.short." + key)),
                         (card.x + 12, card.y + (3 if two_lines else (card.h - 19) // 2),
                          name_w, 19), config.COLOR_TEXT, size=15)
        teams = game.damage.teams_on(key)
        if two_lines:
            _draw_hazards(s, card.x + 12, card.y + 24, c)
            if teams:
                console.badges(s, card.right - 42, card.bottom - 23, teams)
        else:
            _draw_hazards(s, card.right - 104, card.y + (card.h - 19) // 2, c)
        pointer.add_action(card, lambda _pos, picked=key: _pick_compartment(game, picked))


def _draw_hazards(s, x, y, c) -> None:
    """Water and fire of a compartment as two lamps with their percentages
    (the lamp colours of the ship plan's legend)."""
    for index, (level, value) in enumerate(
            (("caution" if c.flood > 0 else "off", c.flood),
             ("alarm" if c.fire > 0 else "off", c.fire))):
        base = x + index * 52
        console.led(s, (base + 5, y + 10), 5, level)
        color = console.level_color(level) if level != "off" else config.COLOR_TEXT_DIM
        layout.blit_line(s, raw_text(f"{value:.0f}%"), (base + 13, y, 38, 19), color, size=13)


def _draw_team_cards(game, s, column, station_rect) -> None:
    """Right column of the selection page: the three repair teams with their
    destination and whether they are on the way or working; a click picks the
    team that Enter sends."""
    layout.box(s, column, "damage.panel.teams")
    damage = game.damage
    cards = damage_team_cards(game, station_rect)
    for team, card in cards:
        destination = damage.teams[team]
        chosen = team == game.dmg_team
        eta = float(damage.team_eta.get(team, 0.0))
        if destination is None:
            state, color = localize("damage.card.team_ready"), config.COLOR_TEXT_DIM
        elif eta > 0.0:
            state, color = message("damage.card.team_en_route", eta=f"{eta:.0f}"), config.COLOR_WARN
        else:
            state, color = localize("ui.on_scene"), config.COLOR_OK
        _card_frame(s, card, chosen, color)
        where = (_compartment_name(destination, damage.compartments[destination].name)
                 if destination is not None else localize("damage.free"))
        layout.blit_line(s, message("damage.team_destination", team=team, destination=where),
                         (card.x + 12, card.y + 4, card.w - 20, 21), config.COLOR_TEXT, size=16)
        layout.blit_line(s, state, (card.x + 12, card.y + 27, card.w - 20, 19), color, size=13)
        pointer.add_action(card, lambda _pos, picked=team: _pick_team(game, picked))
    if cards:
        bottom = cards[-1][1].bottom + 12
        layout.blit_block(s, "damage.teams.hint", column.x + 12, bottom, column.w - 24,
                          max(1, column.bottom - bottom - 8), color=config.COLOR_TEXT_DIM,
                          size=14, min_size=layout.MIN_OPERATIONAL_FONT)
        pointer.add_token_keys((column.x + 12, bottom, column.w - 24,
                                max(1, column.bottom - bottom - 8)), "damage.teams.hint", 14,
                               (("Enter", "Enter"),), min_size=layout.MIN_OPERATIONAL_FONT,
                               screen=s)


def _state_level(c) -> str:
    return ("alarm" if c.state in ("ZERSTOERT", "FLUTEND") else
            "caution" if c.state != "OK" else "on")


def _draw_callout(game, s, card, index, key, c, is_sel, line_h) -> None:
    """A lamp card: name, then state/flood/fire LEDs, values and the teams."""
    sc = _state_color(c.state)
    layout.record_geometry("callout", card, "damage.short." + key)
    pygame.draw.rect(s, theme.c("raised"), card)
    pygame.draw.rect(s, config.COLOR_TEXT if is_sel else sc, card, 2 if is_sel else 1)
    label = message("damage.schematic.callout", number=f"{index + 1:02}",
                    name=localize("damage.short." + key))
    lx = card.x + 20
    console.led(s, (card.x + 10, card.y + 3 + line_h // 2), 5, _state_level(c))
    layout.blit_line(s, label, (lx, card.y + 3, card.w - 26, line_h),
                     config.COLOR_TEXT, size=16)
    y = card.y + line_h + 3
    cy = y + line_h // 2
    teams = game.damage.teams_on(key)
    team_w = 3 * 24                          # room for all three teams
    item_w = (card.right - 6 - team_w - card.x) // 2
    for index, (level, value) in enumerate(
            (("caution" if c.flood > 0 else "off", c.flood),
             ("alarm" if c.fire > 0 else "off", c.fire))):
        base = card.x + index * item_w
        console.led(s, (base + 10, cy), 5, level)
        color = console.level_color(level) if level != "off" else config.COLOR_TEXT_DIM
        layout.blit_line(s, raw_text(f"{value:.0f}%"), (base + 20, y, 44, line_h), color, size=15)
        bar = pygame.Rect(base + 68, cy - 4, item_w - 76, 8)
        if bar.w > 12:
            pygame.draw.rect(s, console.LED_OFF, bar)
            fill = round(bar.w * max(0.0, min(100.0, float(value))) / 100.0)
            if fill:
                pygame.draw.rect(s, color, (bar.x, bar.y, fill, bar.h))
            pygame.draw.rect(s, layout.BRACKET_COLOR, bar, 1)
    if teams:
        console.badges(s, card.right - 4 - team_w // 2, cy - 10, teams)


def _draw_legend(s, rect) -> None:
    """LED legend under the plan: state, water, fire, repair team."""
    items = (("on", "damage.legend.state"), ("caution", "damage.legend.flood"),
             ("alarm", "damage.legend.fire"), (None, "damage.legend.team"))
    width = rect.w // len(items)
    for index, (level, key) in enumerate(items):
        x = rect.x + index * width
        if level is None:
            console.badges(s, x + 10, rect.centery - 10, (1,))
        else:
            console.led(s, (x + 10, rect.centery), 5, level)
        layout.blit_line(s, key, (x + 26, rect.y, width - 30, rect.h),
                         config.COLOR_TEXT_DIM, size=16)


def crew_lines(view) -> dict:
    """Localized crew facts for the crew page (and its tests)."""
    left = view["watch_left_s"]
    if view["action_stations"]:
        relief = message("crew.relief.action_stations")
    elif view["turnover"]:
        relief = message("crew.relief.turnover")
    else:
        relief = message("crew.relief.in", minutes=f"{left // 60:.0f}",
                         seconds=f"{left % 60:02.0f}")
    effect = view["effectiveness"]
    from src.core.crew import sonar_penalty_db
    return dict(
        state=message("crew.state.action_stations" if view["action_stations"]
                      else "crew.state.watch", watch=str(view["on_watch"])),
        relief=relief,
        effectiveness=message("crew.effectiveness", value=f"{effect:.0%}"),
        morale=message("crew.morale", value=f"{view['morale']:.0%}"),
        sonar=message("crew.effect.sonar", db=f"{sonar_penalty_db(effect):+.1f}"),
        repair=message("crew.effect.repair", value=f"{effect:.0%}"))


def casualty_lines(view) -> list:
    """The wounded, empty posts, medical team and spare hands."""
    gaps = {row["station"]: row["gaps"] for row in view["stations"]}
    empty = any(gaps.values())
    rows = [(message("crew.casualties.wounded", wounded=view["wounded"],
                     serious=view["serious"], returned=view["returned"]),
             config.COLOR_WARN if empty else config.COLOR_TEXT_DIM),
            (message("crew.casualties.posts", **{key: gaps[key] for key in gaps}),
             config.COLOR_WARN if empty else config.COLOR_TEXT_DIM),
            (message("crew.casualties.medic", station=message("crew.casualties.at." + view["medic"]))
             if view["medic"] else message("crew.casualties.medic_idle"), config.COLOR_TEXT_DIM),
            (message("crew.casualties.spare_wait", spare=view["spare"],
                     seconds=f"{view['reassign_in_s']:.0f}") if view["reassign_in_s"] > 0.0
             else message("crew.casualties.spare", spare=view["spare"]), config.COLOR_TEXT_DIM)]
    return rows


def _draw_crew(game, s, rect) -> None:
    """Page 3: watch bill, fatigue, morale and what they do to the crew."""
    view = game.crew_view()
    lines = crew_lines(view)
    from src.core.crew import sonar_penalty_db
    effect = view["effectiveness"]
    # Empty posts weigh on top of the watch's own state.
    lines["sonar"] = message("crew.effect.sonar", db=f"{sonar_penalty_db(effect * game.casualty_factor('sonar')):+.1f}")
    lines["repair"] = message("crew.effect.repair",
                              value=f"{effect * game.casualty_factor('damage'):.0%}")
    top = _station_content_top(rect, 3)
    bottom = rect.bottom - 58
    x, w = rect.x + 16, rect.w - 32
    split = int(w * .5)
    left = layout.box(s, (x, top, split - 6, bottom - top), "panel.crew_watches")
    right = layout.box(s, (x + split + 6, top, w - split - 6, bottom - top), "panel.crew_state")
    lx, ly, lw, _ = left
    for row in view["watches"]:
        color = config.COLOR_OK if row["on_duty"] else config.COLOR_TEXT_DIM
        layout.blit_line(s, message("crew.watch_row", watch=str(row["index"]),
                                    duty=localize("crew.on_duty" if row["on_duty"]
                                                  else "crew.off_duty"),
                                    fatigue=f"{row['fatigue']:.0%}"),
                         (lx, ly, lw, 26), color, size=18)
        tired = row["fatigue"] > config.CREW_FATIGUE_FREE
        layout.meter(s, pygame.Rect(lx, ly + 28, lw, 12), row["fatigue"],
             config.COLOR_WARN if tired else config.COLOR_OK)
        ly += 56
    layout.blit_block(s, "crew.explain", lx, ly, lw, max(1, left[1] + left[3] - ly),
                      config.COLOR_TEXT_DIM, size=16)
    rx, ry, rw, _ = right
    effect = view["effectiveness"]
    state_color = config.COLOR_WARN if view["action_stations"] else config.COLOR_TEXT
    for key, color in (("state", state_color), ("relief", config.COLOR_TEXT)):
        layout.blit_line(s, lines[key], (rx, ry, rw, 26), color, size=18)
        ry += 30
    layout.blit_line(s, lines["effectiveness"], (rx, ry, rw, 26),
                     config.COLOR_OK if effect >= .95 else config.COLOR_WARN, size=18)
    layout.meter(s, pygame.Rect(rx, ry + 28, rw, 10), effect / config.CREW_EFFECT_MAX,
         config.COLOR_OK if effect >= .95 else config.COLOR_WARN)
    ry += 50
    layout.blit_line(s, lines["morale"], (rx, ry, rw, 26), config.COLOR_TEXT, size=18)
    layout.meter(s, pygame.Rect(rx, ry + 28, rw, 10), view["morale"],
         config.COLOR_OK if view["morale"] >= .5 else config.COLOR_WARN)
    ry += 50
    for key in ("sonar", "repair"):
        layout.blit_line(s, lines[key], (rx, ry, rw, 24), config.COLOR_TEXT_DIM, size=16)
        ry += 28
    for text, color in casualty_lines(game.casualty_view()):
        if ry + 24 > right[1] + right[3]:
            break
        layout.blit_line(s, text, (rx, ry, rw, 24), color, size=16)
        ry += 26
    footer_y = rect.bottom - 52
    _shortcut_footer(s, (rect.x + 16, footer_y + 26, rect.w - 32, 19), (
        ("W", "damage.footer.watch"),
        ("G", "damage.footer.action_stations"),
        ("M", "damage.footer.medic"),
        ("U", "damage.footer.reassign"),
    ))
