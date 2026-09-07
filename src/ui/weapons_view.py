"""W0/W1: Waffenzentrale – Overlay auf der Seekarte + Panel im STATION_RECT."""

import math

import pygame

from src.core import config
from src.core.i18n import display_value, localized, localize, message as structured_message
from src.ui import layout
from src.ui import observations


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
        "BLOCKIERT: SALVENLIMIT": "weapons.readiness.salvo_limit",
        "BLOCKIERT: WAFFENZENTRALE GESTOERT": "weapons.readiness.weapons_down",
        "FEUER FREI": "weapons.readiness.clear",
    }
    if value in keys:
        return localize(keys[value])
    for affiliation in ("FRIEND", "NEUTRAL"):
        if value == f"BLOCKIERT: ZUGEHOERIGKEIT {affiliation}":
            return localize(message("weapons.readiness.affiliation",
                                    affiliation=display_value("affiliation", affiliation)))
    return str(value)


def weapons_regions(game) -> dict:
    """Shared panel geometry, including the full interlock reason."""
    layout.configure_for(game)
    station = pygame.Rect(config.STATION_RECT)
    top = station.y + 16 + int(layout.font(20).get_linesize() * 1.15)
    x, w, gap = station.x + 14, station.w - 28, 10
    right_w = min(224, max(200, round(w * .37)))
    left_w = w - right_w - gap
    upper_h = 294 if layout.text_scale() > 1 else 270
    ready_h = 166 if layout.text_scale() > 1 else 158
    lower = top + upper_h + gap
    return {
        "solution": pygame.Rect(x, top, left_w, upper_h),
        "stages": pygame.Rect(x + left_w + gap, top, right_w, ready_h),
        "inventory": pygame.Rect(x + left_w + gap, top + ready_h + gap,
                                 right_w, upper_h - ready_h - gap),
        "active": pygame.Rect(x, lower, left_w, station.bottom - lower - 12),
        "controls": pygame.Rect(x + left_w + gap, lower, right_w,
                                station.bottom - lower - 12),
    }


@localized
def weapons_hit_target(game, pos):
    """Hit-test the displayed fire-control panels without consulting targets."""
    layout.configure_for(game)
    station = pygame.Rect(config.STATION_RECT)
    if pos is None or not station.collidepoint(pos):
        return None
    regions = weapons_regions(game)
    target = game.target
    readiness = game.torpedo_readiness()[0]
    solution, stages, inventory, active, controls = (
        regions[key] for key in ("solution", "stages", "inventory", "active", "controls"))
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
    if inventory.collidepoint(pos):
        return layout.tooltip_payload(
            "panel.inventory", message("weapons.tooltip.ship_torpedoes", count=game.torpedo_count, total=game.torpedo_total),
            message("weapons.tooltip.helo_assets", torpedoes=game.helo.torps, buoys=game.helo.buoys_left),
            "tooltip.inventory",
            target_id="weapons:inventory")
    if active.collidepoint(pos):
        body_top = active.y + 16 + layout.font(16, bold=True).get_linesize()
        row = (int(pos[1]) - body_top) // 23
        capacity = max(0, min(5, (active.bottom - body_top - 30) // 23))
        if 0 <= row < len(game.torpedoes[:capacity]):
            weapon = game.torpedoes[row]
            remaining = max(0.0, weapon.RANGE_NM - weapon.travel)
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


@localized
def draw_weapons_overlay(game, tr=None) -> None:
    """Ziel-/Torpedo-Overlay über der Seekarte (Map-Viewport)."""
    layout.configure_for(game)
    s = game.screen
    view = game.map_view
    r = config.MAP_RECT

    with layout.clip_to(s, r):
        for t in game.torpedoes:
            px, py = view.world_to_screen(t.x, t.y)
            ang = math.radians(t.course - 90.0)
            ex, ey = px + 10 * math.cos(ang), py + 10 * math.sin(ang)
            pygame.draw.line(s, config.COLOR_WARN, (int(px), int(py)),
                             (int(ex), int(ey)), 2)
            pygame.draw.circle(s, config.COLOR_WARN, (int(px), int(py)), 3)

        c = game.target
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
                layout.blit_line(s, message("weapons.overlay.fix", contact=c.id,
                                            source=src),
                                 (int(tx) + 12, int(ty) - 22, 130, 20),
                                 config.COLOR_DANGER, size=14)
            else:
                ex = px + 300 * math.sin(brg)
                ey = py - 300 * math.cos(brg)
                pygame.draw.line(s, config.COLOR_DANGER, (int(px), int(py)),
                                 (int(ex), int(ey)), 1)
                layout.blit_line(s, message("weapons.line.bearing_only", contact=c.id),
                                 (int(px) + 12, int(py) - 22, 260, 22),
                                 config.COLOR_DANGER, size=14)


@localized
def draw_weapons_panel(game, tr=None) -> None:
    layout.configure_for(game)
    s = game.screen
    station = pygame.Rect(config.STATION_RECT)
    layout.panel(s, station, "station.weapons.title", title_size=20)
    regions = weapons_regions(game)
    c = game.target
    readiness, readiness_color = game.torpedo_readiness()
    fresh_solution = c is not None and game._contact_range_fresh(c)

    solution = layout.box(s, regions["solution"], "panel.fire_solution",
                          border=config.COLOR_DANGER if c else config.COLOR_WARN)
    sx, sy, sw, _ = solution
    if c is None:
        layout.blit_line(s, "ui.no_target", (sx, sy, sw, 28),
                         config.COLOR_WARN, size=18)
        layout.blit_block(s, "tooltip.target_contact",
                          sx, sy + 38, sw, 48, config.COLOR_TEXT_DIM, size=14)
    else:
        displayed_range = _display_range(c, getattr(game, "ship", None)) \
            if getattr(game, "ship", None) is not None else c.range_est
        dist = f"{displayed_range:6.1f} NM" if displayed_range is not None else "     --"
        lines = [
            (message("weapons.line.contact", contact=c.id, label=c.display_label), config.COLOR_TEXT, 18),
            (observations.format_bearing_pair(c, getattr(game, "ship", None), compact=True),
             config.COLOR_TEXT, 15),
            (message("weapons.line.confidence", confidence=int(c.confidence * 100)), config.COLOR_TEXT_DIM, 14),
            (message("weapons.line.range", range=dist.strip()), config.COLOR_TEXT, 14),
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
                layout.blit_line(s, text, (sx, sy, sw, 22), color, size=size)
            sy += 24 if layout.text_scale() > 1 else 21
    layout.blit_block(s, _readiness_text(readiness), sx,
                      regions["solution"].bottom - 62, sw, 56,
                      readiness_color, size=14)

    ready = layout.box(s, regions["stages"], "panel.engagement_stages",
                        border=readiness_color)
    rx, ry, rw, _ = ready
    has_target = c is not None
    has_solution = fresh_solution
    authorized = (has_target and c.player_class in ("U_BOOT", "KAMPFSCHIFF")
                  and not readiness.startswith("BLOCKIERT: ZUGEHOERIGKEIT"))
    stages = ((message("ui.target"), message("panel.assigned" if has_target else "ui.no_target"), has_target),
              (message("weapons.fix"), message("panel.valid" if has_solution else
                  "weapons.manual_datum" if has_target and game.roe == "FREE" else "panel.pending"), has_solution),
              ("ROE", message("panel.authorized" if authorized else "panel.blocked"), authorized),
              (message("weapons.weapon"), message("ui.ready" if readiness == "FEUER FREI" else "panel.blocked"),
               readiness == "FEUER FREI"))
    for index, (name, value, ok) in enumerate(stages):
        layout.status_line(s, rx, ry + index * 22, rw, name, value,
                           color=config.COLOR_OK if ok else config.COLOR_WARN,
                           label_w=76, size=15)
    layout.blit_line(s, "weapons.control.launch", (rx, ry + 90, rw, 22), readiness_color, size=14)

    inventory = layout.box(s, regions["inventory"],
                           "panel.inventory")
    ix, iy, iw, _ = inventory
    layout.status_line(s, ix, iy, iw, "ui.tubes", message("weapons.line.inventory",
                       count=game.torpedo_count, total=game.torpedo_total),
                       label_w=78, size=15)
    layout.status_line(s, ix, iy + 24, iw, "ui.helo_torpedoes_short", str(game.helo.torps),
                       label_w=96, size=15)
    layout.status_line(s, ix, iy + 48, iw, "ui.buoys", str(game.helo.buoys_left),
                       label_w=96, size=15)

    active = layout.box(s, regions["active"],
                         "panel.active_weapons")
    ax, ay, aw, ah = active
    if not game.torpedoes:
        layout.blit_line(s, "ui.no_weapons", (ax, ay, aw, 22),
                         config.COLOR_TEXT_DIM, size=14)
    capacity = max(0, min(5, (regions["active"].bottom - ay - 30) // 23))
    for t in game.torpedoes[:capacity]:
        d = t.guidance_distance_nm()
        d_txt = f"{d:.1f} NM" if d != float("inf") else "--"
        mode = display_value("weapon_mode",
                             "SUCHER" if t.seeker_acquired else "DRAHT")
        remaining = max(0.0, t.RANGE_NM - t.travel)
        run_s = remaining / max(.001, t.speed_nm_per_s)
        layout.blit_line(s, message("weapons.line.active", weapon=t.idx, mode=mode,
                                   solution=d_txt, remaining=f"{remaining:.1f}", time=f"{run_s:.0f}"),
                         (ax, ay, aw, 21), config.COLOR_WARN, size=13)
        ay += 23
    if len(game.torpedoes) > capacity:
        layout.blit_line(s, message("weapons.line.more", count=len(game.torpedoes) - capacity),
                         (ax, ay, aw, 19), config.COLOR_TEXT_DIM, size=12)

    controls = layout.box(s, regions["controls"], "panel.engagement")
    cx, cy, cw, _ = controls
    layout.blit_line(s, message("weapons.depth_roe", depth=f"{game.torpedo_depth:.0f}", roe=game.roe),
                     (cx, cy, cw, 22), config.COLOR_TEXT, size=14)
    helo = game.helo
    hstate = localize("enum.helo." + helo.state)
    layout.status_line(s, cx, cy + 22, cw, "HSP-5", hstate,
                       color=config.COLOR_DANGER if helo.state == "VERLOREN" else
                       config.COLOR_OK if helo.airborne else config.COLOR_TEXT_DIM,
                       label_w=66, size=14)
    for offset, text in enumerate(("weapons.control.depth_compact", "weapons.control.helo",
                                   "weapons.control.air_compact")):
        layout.blit_line(s, text, (cx, cy + 44 + offset * 22, cw, 22),
                         config.COLOR_TEXT_DIM, size=14)
