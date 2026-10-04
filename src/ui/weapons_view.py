"""W0/W1: Waffenzentrale – Overlay auf der Seekarte + Panel im STATION_RECT."""

import math

import pygame

from src.core import config, status_tips
from src.core.i18n import raw_text, display_value, localized, localize, message as structured_message
from src.core.station import Station
from src.ui import console, engagement, label_layout, layout, map_view, pointer, theme
from src.ui import nato_symbols
from src.ui import observations

# Least height the fire-control box keeps free for the engagement sketch (px).
SKETCH_MIN_H = 130


def message(key, **values):
    return localize(structured_message(key, **values))


def _observed_bearing(contact) -> float:
    return observations.bearing(contact)


def _observed_position(contact):
    return observations.position(contact)


def _contact_position(contact, ship):
    x, y = _observed_position(contact)
    if x is not None and y is not None:
        return x, y
    distance = getattr(contact, "range_est", None)
    if distance is None:
        return None, None
    bearing = math.radians(_observed_bearing(contact))
    return (ship.x + distance * math.sin(bearing),
            ship.y - distance * math.cos(bearing))


def _display_range(contact, ship):
    return observations.range_nm(contact, ship)


def _display_bearing(contact, ship):
    return observations.bearing(contact, ship)


def _readiness_text(value):
    keys = {
        "BLOCKIERT: KEIN ZIEL": "weapons.readiness.no_target",
        "BLOCKIERT: KEINE ENTFERNUNG": "weapons.readiness.no_range",
        "BLOCKIERT: NICHT ALS U-BOOT/KAMPFSCHIFF KLASSIFIZIERT": "weapons.readiness.classification",
        "BLOCKIERT: KEINE TORPEDOS": "weapons.readiness.no_torpedoes",
        "BLOCKIERT: KEIN ROHR BEREIT": "weapons.readiness.no_tube",
        "BLOCKIERT: SALVENLIMIT": "weapons.readiness.salvo_limit",
        "BLOCKIERT: WAFFENZENTRALE GESTOERT": "weapons.readiness.weapons_down",
        "BLOCKIERT: WAFFEN GESPERRT": "weapons.readiness.weapons_tight",
        "FEUER FREI": "weapons.readiness.clear",
    }
    if value in keys:
        return localize(keys[value])
    for affiliation in ("FRIEND", "NEUTRAL"):
        if value == f"BLOCKIERT: ZUGEHOERIGKEIT {affiliation}":
            return localize(message("weapons.readiness.affiliation",
                                    affiliation=display_value("affiliation", affiliation)))
    return str(value)


def _inventory_state(game):
    battery = getattr(game, "player_torpedo_battery", None)
    ready = battery.ready_count if battery is not None else game.torpedo_count
    tubes = battery.mount_count if battery is not None else game.torpedo_total
    reload_s = battery.next_reload_s if battery is not None else 0.0
    store = getattr(game, "nixie_store", None)
    nixies = store.remaining_total if store is not None else 0
    return ready, tubes, reload_s, nixies


def _tube_lamps(game):
    """One annunciator lamp per torpedo tube: loaded, loading or empty."""
    battery = getattr(game, "player_torpedo_battery", None)
    rows = []
    for tube in getattr(battery, "tubes", ())[:8]:
        if tube.loaded_weapon_key is not None:
            level, value = "on", localize("weapons.lamp.loaded")
        elif tube.loading_weapon_key is not None:
            level, value = "caution", f"{tube.reload_remaining_s:.0f} s"
        else:
            level, value = "off", localize("weapons.lamp.empty")
        rows.append((message("weapons.lamp.tube", number=tube.index + 1), value, level))
    return rows


def weapons_regions(game, page=0) -> dict:
    """Shared panel geometry, including the full interlock reason.

    Page 0 shows the targeting solution + engagement stages; page 1 shows
    inventory, active weapons and engagement controls.
    """
    layout.configure_for(game)
    from src.core.commands import STATION_PAGES
    station = pygame.Rect(config.STATION_RECT)
    x, w, gap = station.x + 14, station.w - 28, 10
    top = _content_top(station)
    h = station.bottom - top - 34
    left_w = int(w * .65)
    right_w = w - left_w - gap
    if page == 0:
        # Contact cards above the engagement stages on the left, the
        # fire-control solution on the right.
        side_w = WEAPONS_SIDE_W
        stages_h = min(h // 2, _stages_height())
        return {
            "contacts": pygame.Rect(x, top, side_w, h - stages_h - gap),
            "stages": pygame.Rect(x, top + h - stages_h, side_w, stages_h),
            "solution": pygame.Rect(x + side_w + gap, top, w - side_w - gap, h),
        }
    else:
        inv_h = max(1, int(h * .42))
        lower_h = max(1, h - inv_h - gap)
        return {
            "inventory": pygame.Rect(x, top, w, inv_h),
            "active": pygame.Rect(x, top + inv_h + gap, left_w, lower_h),
            "controls": pygame.Rect(x + left_w + gap, top + inv_h + gap,
                                    right_w, lower_h),
        }


WEAPONS_SIDE_W = 232
CARD_H = 46
CARD_PITCH = 50


def _stages_height() -> int:
    """Height of the engagement-stages box: five lamps and two key lines."""
    lamp_h = layout.line_pitch(13, 0) + 10
    title = 8 + layout.font(16, bold=True).get_linesize() + 8
    return title + 5 * (lamp_h + 4) - 4 + 12 + 24 + 24 + 8


def weapons_contacts(game) -> list:
    """The contacts ←/→ steps through at this station, in the same order."""
    sonar = getattr(game, "sonar", None)
    if sonar is None:
        return []
    return sorted((c for c in sonar.contacts.values()
                   if game.sim_t - c.last_seen < config.SONAR_CONTACT_LOST_S),
                  key=lambda c: c.id)


def weapons_contact_cards(game) -> list:
    """(contact, rect) for each card the contacts box shows, scrolled so the
    selected contact stays visible."""
    box = weapons_regions(game, 0)["contacts"]
    contacts = weapons_contacts(game)
    capacity = max(1, (box.h - 36) // CARD_PITCH)
    chosen = next((index for index, c in enumerate(contacts)
                   if c is game.selected_contact), 0)
    start = max(0, min(chosen - capacity // 2, len(contacts) - capacity))
    return [(c, pygame.Rect(box.x + 6, box.y + 34 + index * CARD_PITCH, box.w - 12, CARD_H))
            for index, c in enumerate(contacts[start:start + capacity])]


def _pick_contact(game, contact) -> None:
    """A click on a card selects its contact, as ←/→ would (M assigns it)."""
    if contact in weapons_contacts(game):
        game.selected_contact = contact
        if game.sonar.focus_locked:
            game.sonar.reset_listening_history()


def _draw_contact_cards(s, game, box) -> None:
    layout.box(s, box, "weapons.panel.contacts")
    cards = weapons_contact_cards(game)
    if not cards:
        layout.blit_block(s, "weapons.no_contacts", box.x + 12, box.y + 36, box.w - 24, 44,
                          config.COLOR_TEXT_DIM, size=14)
    for c, rect in cards:
        chosen = c is game.selected_contact
        targeted = c is game.target
        pygame.draw.rect(s, config.COLOR_TAB_ACTIVE if chosen else theme.c("raised"),
                         rect, border_radius=4)
        pygame.draw.rect(s, theme.c("focus") if chosen else theme.c("line"),
                         rect, 2 if chosen else 1, border_radius=4)
        if targeted:
            pygame.draw.rect(s, config.COLOR_DANGER, (rect.x + 3, rect.y + 5, 3, rect.h - 10))
        layout.blit_line(s, raw_text(observations.contact_display_id(game, c)),
                         (rect.x + 10, rect.y + 3, 48, 20), config.COLOR_TEXT, size=15)
        layout.blit_line(s, display_value("classification", getattr(c, "player_class", None)),
                         (rect.x + 58, rect.y + 4, rect.w - 134, 19),
                         config.COLOR_DANGER if targeted else config.COLOR_TEXT_DIM, size=13)
        layout.blit_line(s, observations.format_bearing(c, game.ship) + "\u00b0",
                         (rect.right - 72, rect.y + 2, 64, 21), config.COLOR_TEXT,
                         size=17, align="right")
        distance = _display_range(c, game.ship)
        layout.blit_line(s, message("weapons.card.range_confidence",
                                    range=f"{distance:.1f}" if distance is not None else "--",
                                    confidence=f"{c.confidence:.0%}"),
                         (rect.x + 10, rect.y + 25, rect.w - 18, 19),
                         config.COLOR_TEXT_DIM, size=13)
        pointer.add_action(rect, lambda _pos, picked=c: _pick_contact(game, picked))


def _active_row_pitch() -> int:
    """Row pitch for active-weapon lines (wraps to two lines at the operational font floor)."""
    face = layout.font(15)
    return 2 * int(face.get_linesize() * 1.15) + 6


def _content_top(station: pygame.Rect) -> int:
    from src.ui import stations_view
    return stations_view._station_content_top(station, 2)


@localized
def weapons_hit_target(game, pos):
    """Hit-test the displayed fire-control panels without consulting targets."""
    layout.configure_for(game)
    from src.core.commands import STATION_PAGES
    from src.core.station import Station as St
    pages = STATION_PAGES[St.WEAPONS]
    page = int(getattr(game, "station_page", 0)) % len(pages)
    station = pygame.Rect(config.STATION_RECT)
    if pos is None or not station.collidepoint(pos):
        return None
    regions = weapons_regions(game, page=page)
    target = game.target
    readiness = game.torpedo_readiness()[0]
    if page == 0:
        solution = regions["solution"]
        stages = regions["stages"]
        if regions["contacts"].collidepoint(pos):
            return layout.tooltip_payload("weapons.panel.contacts", "tooltip.adopt_contact",
                                          target_id="weapons:contacts")
        if solution.collidepoint(pos):
            if target is None:
                return layout.tooltip_payload("panel.fire_solution", "weapons.no_assigned_target",
                                              "tooltip.adopt_contact",
                                              target_id="weapons:solution")
            displayed_range = _display_range(target, game.ship)
            distance = f"{displayed_range:.1f}" if displayed_range is not None else "--"
            sigma = f"{target.range_sigma_nm:.2f}" if target.range_sigma_nm is not None else "--"
            return layout.tooltip_payload(
                message("weapons.tooltip.solution_title", contact=target.id),
                observations.format_bearing_pair(target, game.ship),
                message("weapons.tooltip.range_sigma", range=distance, sigma=sigma),
                message("map.tooltip.class_confidence", classification=display_value('classification', target.player_class), confidence=f"{target.confidence:.0%}"),
                message("weapons.tooltip.source_age", source=target.range_source or localize("map.tooltip.passive_bearing"), age=f"{observations.observation_age(target, game.sim_t):.0f}"),
                message("observation.fix_age", age=f"{observations.position_age(target, game.sim_t):.0f}")
                if observations.position_age(target, game.sim_t) is not None else None,
                _readiness_text(readiness),
                target_id=f"weapons:contact:{target.id}")
        if stages.collidepoint(pos):
            return layout.tooltip_payload("weapons.tooltip.interlock_title", _readiness_text(readiness),
                                          "tooltip.interlock",
                                          target_id="weapons:interlock")
    else:
        inventory = regions["inventory"]
        active = regions["active"]
        controls = regions["controls"]
        if inventory.collidepoint(pos):
            ready, tubes, reload_s, nixies = _inventory_state(game)
            return layout.tooltip_payload(
                "panel.inventory", message("weapons.tooltip.ship_torpedoes", count=game.torpedo_count, total=game.torpedo_total),
                message("weapons.tooltip.tubes", ready=ready,
                        total=tubes, reload=f"{reload_s:.0f}"),
                message("weapons.tooltip.nixie", count=nixies),
                message("weapons.tooltip.helo_assets", torpedoes=game.helo.torps, buoys=game.helo.buoys_left),
                "tooltip.inventory",
                target_id="weapons:inventory")
        if active.collidepoint(pos):
            body_top = active.y + 16 + layout.font(16, bold=True).get_linesize()
            pitch = _active_row_pitch()
            row = (int(pos[1]) - body_top) // pitch
            capacity = max(0, min(5, (active.bottom - _tank_reserve(active)
                                      - body_top - 30) // pitch))
            if 0 <= row < len(game.torpedoes[:capacity]):
                weapon = game.torpedoes[row]
                remaining = max(0.0, weapon.range_nm - weapon.travel)
                mode = display_value("weapon_mode",
                                      "SUCHER" if weapon.seeker_acquired else "DRAHT")
                return layout.tooltip_payload(
                    message("weapons.tooltip.weapon_title", weapon=weapon.idx),
                    message("weapons.tooltip.mode_remaining", mode=mode, remaining=f"{remaining:.1f}"),
                    "tooltip.own_weapon",
                    target_id=f"weapons:torpedo:{weapon.idx}")
            if not game.torpedoes:
                return layout.tooltip_payload("panel.active_weapons", "ui.no_weapons",
                                              target_id="weapons:active")
        if controls.collidepoint(pos):
            return layout.tooltip_payload(
                "tooltip.engagement_controls", message("weapons.tooltip.depth_roe", depth=f"{game.torpedo_depth:.0f}", roe=game.roe),
                message("weapons.tooltip.helo_state", state=localize('enum.helo.' + game.helo.state)),
                "control.weapons",
                target_id="weapons:controls")
    return None


def _torpedo_profile(game):
    """Speed and range of the torpedo type the tubes load (catalog values)."""
    from src.weapons.torpedo import Torpedo
    for weapon in getattr(game, "_ownship_loadout", {}).get("weapons", ()):
        if weapon.get("key") == getattr(game, "torpedo_type", None):
            profile = game.runtime_catalog.torpedoes.get(weapon["runtime_profile_key"])
            if profile is not None:
                return profile.speed_kn, profile.range_nm
    return Torpedo.SPEED_KN, Torpedo.RANGE_NM


def _draw_sketch(s, game, c, fresh, rect) -> None:
    """The engagement sketch from the assigned contact's observation only."""
    ship = getattr(game, "ship", None)
    if ship is None:
        return
    speed, reach = _torpedo_profile(game)
    bearing = target = course = target_speed = None
    if c is not None:
        bearing = _display_bearing(c, ship)
        est_x, est_y = _contact_position(c, ship)
        if est_x is not None and est_y is not None:
            target = (est_x - ship.x, est_y - ship.y)
            course, target_speed = c.tma_course, c.tma_speed
    engagement.draw_engagement_sketch(
        s, rect, own_course=ship.course, torpedo_kn=speed, torpedo_range_nm=reach,
        bearing=bearing, target=target, target_course=course,
        target_speed_kn=target_speed, fresh=fresh)


def _tank_reserve(rect) -> int:
    """Height the magazine tanks take at the foot of the active weapons box."""
    return 138 if rect.height >= 300 else 0


@localized
def draw_weapons_overlay(game, tr=None) -> None:
    """Ziel-/Torpedo-Overlay über der Seekarte (Map-Viewport)."""
    layout.configure_for(game)
    s = game.screen
    view = game.map_view
    r = config.MAP_RECT

    # Continue the chart's label field: the target marks never cover a
    # chart label, and the chart's own contact label is not repeated.
    with layout.clip_to(s, r), label_layout.label_scope(
            r, map_view.last_label_field()):
        for t in game.torpedoes:
            px, py = view.world_to_screen(t.x, t.y)
            ang = math.radians(t.course - 90.0)
            ex, ey = px + 10 * math.cos(ang), py + 10 * math.sin(ang)
            pygame.draw.line(s, config.COLOR_WARN, (int(px), int(py)),
                             (int(ex), int(ey)), 2)
            pygame.draw.circle(s, config.COLOR_WARN, (int(px), int(py)), 3)

        c = game.target
        # The chart already draws and labels the selected contact (or, with
        # none selected, the target) with its line, fix and motion vector.
        charted = c is not None and (game.selected_contact or game.target) is c
        if c is not None:
            px, py = view.world_to_screen(game.ship.x, game.ship.y)
            brg = math.radians(_display_bearing(c, game.ship))
            est_x, est_y = _contact_position(c, game.ship)
            if est_x is not None and est_y is not None:
                tx, ty = view.world_to_screen(est_x, est_y)
                src = ({"tma": "TMA", "ping": "PING",
                        "buoy": localize("map.source.buoy")}
                       .get(c.range_source, "FIX"))
                pygame.draw.line(s, config.COLOR_DANGER, (int(tx) - 10, int(ty)),
                                 (int(tx) + 10, int(ty)), 2)
                pygame.draw.line(s, config.COLOR_DANGER, (int(tx), int(ty) - 10),
                                 (int(tx), int(ty) + 10), 2)
                pygame.draw.circle(s, config.COLOR_DANGER, (int(tx), int(ty)), 8, 1)
                if not charted:
                    nato_symbols.draw_motion_vector(
                        s, (tx, ty), getattr(c, "tma_course", None),
                        getattr(c, "tma_speed", None),
                        view.scale, config.COLOR_DANGER, font=game.font, max_px=120)
                    map_view._map_label(
                        s, game, message("weapons.overlay.fix",
                                         contact=observations.contact_display_id(game, c),
                                         source=src),
                        (int(tx) + 12, int(ty) - 22), config.COLOR_DANGER, r, size=14)
            elif not charted:
                ex = px + 300 * math.sin(brg)
                ey = py - 300 * math.cos(brg)
                pygame.draw.line(s, config.COLOR_DANGER, (int(px), int(py)),
                                 (int(ex), int(ey)), 1)
                map_view._map_label(
                    s, game, structured_message(
                        "weapons.line.bearing_only.short",
                        contact=observations.contact_display_id(game, c)),
                    (int(px) + 12, int(py) - 22), config.COLOR_DANGER, r, size=14)


@localized
def draw_weapons_panel(game, tr=None) -> None:
    layout.configure_for(game)
    from src.core.commands import STATION_PAGES
    from src.ui.stations_view import draw_station_page_tabs, _station_content_top
    s = game.screen
    pages = STATION_PAGES[Station.WEAPONS]
    page = int(getattr(game, "station_page", 0)) % len(pages)
    station = pygame.Rect(config.STATION_RECT)
    layout.panel(s, station, "station.weapons.title", title_size=20)
    draw_station_page_tabs(s, station, pages, page, tr)
    c = game.target
    readiness, readiness_color = game.torpedo_readiness()
    fresh_solution = c is not None and game._contact_range_fresh(c)

    if page == 0:
        regions = weapons_regions(game, 0)
        _draw_contact_cards(s, game, regions["contacts"])
        solution = layout.box(s, regions["solution"], "panel.fire_solution",
                              border=config.COLOR_DANGER if c else config.COLOR_WARN)
        sx, sy, sw, _ = solution
        if c is None:
            layout.blit_line(s, "ui.no_target", (sx, sy, sw, 30),
                             config.COLOR_WARN, size=20)
            layout.blit_block(s, "tooltip.target_contact",
                              sx, sy + 40, sw, 48, config.COLOR_TEXT_DIM, size=16)
            pointer.add_token_keys((sx, sy + 40, sw, 48), "tooltip.target_contact",
                                   16, (("M:", "M"),), min_size=16)
            sy += 88
        else:
            displayed_range = _display_range(c, getattr(game, "ship", None)) \
                if getattr(game, "ship", None) is not None else c.range_est
            dist = f"{displayed_range:6.1f} NM" if displayed_range is not None else "     --"
            lines = [
                (message("weapons.line.contact",
                         contact=observations.contact_display_id(game, c),
                         label=c.display_label), config.COLOR_TEXT, 18),
                (observations.format_bearing_pair(c, getattr(game, "ship", None), compact=True),
                 config.COLOR_TEXT, 15),
                (message("weapons.line.confidence", confidence=int(c.confidence * 100)), config.COLOR_TEXT_DIM, 14),
                (message("weapons.line.range", range=dist.strip()), config.COLOR_TEXT, 15),
            ]
            source = ({"tma": "TMA", "ping": "PING", "buoy": localize("map.source.buoy")}
                      .get(c.range_source, "FIX") if displayed_range is not None
                      else localize("ui.bearing_only"))
            age = observations.observation_age(c, game.sim_t)
            sigma = (f"+/- {c.range_sigma_nm:.2f} NM" if c.range_sigma_nm is not None
                     else localize("weapons.no_range_solution"))
            lines += [
                (message("weapons.line.solution", source=source, sigma=sigma), config.COLOR_OK if fresh_solution else config.COLOR_WARN, 14),
                (message("weapons.line.ages", observation_age=f"{age:.0f}",
                         fix_age=f"{observations.position_age(c, game.sim_t):.0f}")
                 if observations.position_age(c, game.sim_t) is not None
                 else message("weapons.line.age", age=f"{age:.0f}"),
                 config.COLOR_TEXT_DIM, 14),
            ]
            if c.tma_course is not None or c.tma_speed is not None:
                course = f"{c.tma_course % 360:05.1f}" if c.tma_course is not None else "--"
                speed = f"{c.tma_speed:.1f}" if c.tma_speed is not None else "--"
                lines.append((message("weapons.line.tma_compact", course=course, speed=speed,
                                      quality=f"{c.tma_quality:.0%}"),
                              config.COLOR_TEXT_DIM, 14))
            if c.depth_est is not None:
                lines.append((message("weapons.line.depth_compact", actual=f"{c.depth_est:.0f}",
                                      target=f"{game.torpedo_depth:.0f}"),
                              config.COLOR_TEXT, 14))
            for text, color, size in lines:
                if text:
                    face = layout.font(size)
                    wrapped = layout.wrap_text(localize(text), face, sw) or [""]
                    pitch = max(1, len(wrapped)) * int(face.get_linesize() * 1.15) + 4
                    layout.blit_block(s, text, sx, sy, sw, pitch, color, size=size)
                    sy += pitch
        readiness_text = localize(_readiness_text(readiness))
        ready_face, ready_lines = layout.fit_text(
            readiness_text, 14, sw, 96, min_size=14)
        ready_h = max(40, len(ready_lines) * int(ready_face.get_linesize() * 1.15) + 8)
        ready_y = regions["solution"].bottom - ready_h - 6
        layout.blit_block(s, _readiness_text(readiness), sx,
                          ready_y, sw, ready_h,
                          readiness_color, size=14)
        tubes = _tube_lamps(game)
        lamp_h = layout.line_pitch(14, 0) + 8
        sketch_bottom = ready_y - 8
        if tubes and ready_y - lamp_h - 6 > sy:
            console.lamp_grid(s, (sx, ready_y - lamp_h - 6, sw, lamp_h), console.with_tips(
                tubes, [status_tips.lazy(lambda: status_tips.weapons(game), f"tube_{index + 1}")
                        for index in range(len(tubes))]), len(tubes), size=14)
            sketch_bottom = ready_y - lamp_h - 14
        if sketch_bottom - sy >= SKETCH_MIN_H:
            _draw_sketch(s, game, c, fresh_solution, (sx, sy + 4, sw, sketch_bottom - sy - 4))

        ready = layout.box(s, regions["stages"], "panel.engagement_stages",
                            border=readiness_color)
        rx, ry, rw, _ = ready
        has_target = c is not None
        has_solution = fresh_solution
        authorized = (has_target
                      and game.weapon_classification(c) in ("U_BOOT", "KAMPFSCHIFF")
                      and not readiness.startswith("BLOCKIERT: ZUGEHOERIGKEIT"))
        stages = ((message("ui.target"), message("panel.assigned" if has_target else "ui.no_target"), has_target),
                  (message("weapons.fix"), message("panel.valid" if has_solution else
                      "weapons.manual_datum" if has_target and game.roe == "FREE" else "panel.pending"), has_solution),
                  ("ROE", message("panel.authorized" if authorized else "panel.blocked"), authorized),
                  (message("weapons.weapon"), message("ui.ready" if readiness == "FEUER FREI" else "panel.blocked"),
                   readiness == "FEUER FREI"),
                  ("FLAK", message("panel.authorized" if game.flak_authorized else "panel.blocked"),
                   game.flak_authorized))
        # The interlock chain as annunciator lamps: lit when the stage is clear.
        lamp_h = layout.line_pitch(13, 0) + 10
        used = console.lamp_grid(s, (rx, ry, rw, len(stages) * (lamp_h + 4) - 4),
                                 [(name, value, "on" if ok else "caution", key,
                                   status_tips.lazy(lambda: status_tips.weapons(game), tip))
                                  for (name, value, ok), key, tip
                                  in zip(stages, ("M", None, None, None, "F"),
                                         ("target", "fix", "roe", "weapon", "flak"))],
                                 1, size=13)
        layout.blit_line(s, "weapons.control.launch", (rx, ry + used + 12, rw, 24), readiness_color, size=14)
        layout.blit_line(s, "weapons.control.flak", (rx, ry + used + 36, rw, 24), config.COLOR_TEXT_DIM, size=13)
        # The key hints are switches too (Ctrl+Enter fires only here, at station 3).
        pointer.add_token_keys((rx, ry + used + 12, rw, 24), localize("weapons.control.launch"),
                               14, (("Ctrl+Enter:", "Ctrl+Enter"), ("Strg+Enter:", "Ctrl+Enter")), screen=s)
        pointer.add_token_keys((rx, ry + used + 36, rw, 24), localize("weapons.control.flak"),
                               13, (("F:", "F"),), screen=s)

    else:
        regions = weapons_regions(game, 1)
        inventory = layout.box(s, regions["inventory"],
                               "panel.inventory")
        ix, iy, iw, _ = inventory
        layout.status_line(s, ix, iy, iw, "field.torpedoes", message("weapons.line.inventory",
                           count=game.torpedo_count, total=game.torpedo_total),
                           label_w=100, size=17)
        tube_ready, tube_total, reload_s, nixies = _inventory_state(game)
        tube_status = message("weapons.line.tubes", ready=tube_ready,
                              total=tube_total, reload=f"{reload_s:.0f}")
        layout.status_line(s, ix, iy + 30, iw, "weapons.tubes_short", tube_status,
                           label_w=100, size=15)
        layout.status_line(s, ix, iy + 60, iw, "weapons.nixie_short",
                           message("weapons.line.decoy_asw", nixies=nixies,
                                   asw=game.own_asw_stores_line()),
                           label_w=100, size=15)
        half = iw // 2
        layout.status_line(s, ix, iy + 90, half - 8, "ui.helo_torpedoes_short", str(game.helo.torps),
                            label_w=120, size=17)
        layout.status_line(s, ix + half, iy + 90, iw - half, "ui.buoys", str(game.helo.buoys_left),
                            label_w=120, size=17)
        rbu_line = getattr(game, "rbu_stores_line", None)
        if callable(rbu_line):
            layout.status_line(s, ix, iy + 120, iw, "weapons.rbu_short", rbu_line(),
                               label_w=100, size=15)
        choices = getattr(game, "torpedo_type_choices", None)
        if callable(choices):
            stock = next((row[2] for row in choices()
                          if row[0] == game.torpedo_type), 0)
            layout.status_line(s, ix, iy + 150, iw, "weapons.setup_short", message(
                "weapons.line.torpedo_setup",
                name=localize("weapons.type." + game.torpedo_type), stock=stock,
                pattern=display_value("torpedo_pattern", game.torpedo_pattern),
                enable=f"{game.torpedo_enable_nm:.1f}", salvo=game.torpedo_salvo),
                label_w=100, size=14)

        active = layout.box(s, regions["active"],
                             "panel.active_weapons")
        ax, ay, aw, ah = active
        tank_h = _tank_reserve(regions["active"]) - 8 if _tank_reserve(regions["active"]) else 0
        if tank_h:
            # Magazine columns along the foot: what is left of each store.
            from src.weapons import rbu
            stores = (("weapons.tank.torpedoes", game.torpedo_count, game.torpedo_total),
                      ("weapons.tank.helo", game.helo.torps, config.HELO_TORPS),
                      ("weapons.tank.buoys", game.helo.buoys_left, config.BUOY_COUNT),
                      ("weapons.tank.rbu", getattr(game, "rbu_rockets", 0), rbu.STOCK))
            column = aw // len(stores)
            for index, (label, left, full) in enumerate(stores):
                fraction = left / full if full else 0.0
                console.tank(s, (ax + index * column, ay + ah - tank_h, column - 6, tank_h),
                             fraction, label=label, text=raw_text(f"{left}"),
                             level="on" if fraction > .25 else "caution" if left else "alarm")
            ah -= tank_h + 8
        if not game.torpedoes:
            layout.blit_line(s, "ui.no_weapons", (ax, ay, aw, 24),
                             config.COLOR_TEXT_DIM, size=16)
        pitch = _active_row_pitch()
        capacity = max(0, min(5, (regions["active"].bottom - _tank_reserve(regions["active"])
                                  - ay - 30) // pitch))
        for t in game.torpedoes[:capacity]:
            d = t.guidance_distance_nm()
            d_txt = f"{d:.1f} NM" if d != float("inf") else "--"
            mode = display_value("weapon_mode",
                                  "SUCHER" if t.seeker_acquired else "DRAHT")
            remaining = max(0.0, t.range_nm - t.travel)
            run_s = remaining / max(.001, t.speed_nm_per_s)
            layout.blit_block(s, message("weapons.line.active", weapon=t.idx, mode=mode,
                                       solution=d_txt, remaining=f"{remaining:.1f}", time=f"{run_s:.0f}"),
                              ax, ay, aw, pitch, color=config.COLOR_WARN, size=15)
            ay += pitch
        if len(game.torpedoes) > capacity:
            layout.blit_line(s, message("weapons.line.more", count=len(game.torpedoes) - capacity),
                              (ax, ay, aw, 22), config.COLOR_TEXT_DIM, size=14)

        controls = layout.box(s, regions["controls"], "panel.engagement")
        cx, cy, cw, _ = controls
        layout.blit_line(s, message("weapons.depth_roe", depth=f"{game.torpedo_depth:.0f}", roe=game.roe),
                         (cx, cy, cw, 24), config.COLOR_TEXT, size=16)
        helo = game.helo
        from src.ui.stations.helicopter import helo_state_text
        hstate = helo_state_text(helo)
        layout.status_line(s, cx, cy + 28, cw, "HSP-5", hstate,
                           color=config.COLOR_DANGER if helo.state == "VERLOREN" else
                           config.COLOR_WARN if getattr(helo, "preparing", False)
                           or getattr(helo, "refuelling", False) else
                           config.COLOR_OK if helo.airborne else config.COLOR_TEXT_DIM,
                           label_w=80, size=16)
        for offset, (text, tokens) in enumerate((
                ("weapons.control.depth_compact", (("Up/Dn:", "↑/↓"), ("Auf/Ab:", "↑/↓"))),
                ("weapons.control.helo", (("H:", "H"),)),
                ("weapons.control.air_compact", (("B:", "B"), ("D:", "D"))),
                ("weapons.control.nixie", (("V:", "V"),)),
                ("weapons.control.asw", (("A:", "A"), ("Z:", "Z"))),
                ("weapons.control.rbu", (("R/", "R"),)))):
            layout.blit_line(s, text, (cx, cy + 56 + offset * 26, cw, 24),
                             config.COLOR_TEXT_DIM, size=15)
            pointer.add_token_keys((cx, cy + 56 + offset * 26, cw, 24), localize(text),
                                   15, tokens, screen=s)
