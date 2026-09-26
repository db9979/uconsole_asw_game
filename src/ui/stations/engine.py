"""Engine room view: plant, telegraph and noise (verbatim from ``stations_view``)."""


import pygame

from src.core import config
from src.core.i18n import display_value, localized, localize
from src.core.station import Station
from src.ship.ship import Ship
from src.ui import layout


from src.ui.stations.common import (
    STATE_LABEL,
    _panel,
    _shortcut_footer,
    _station_content_top,
    draw_station_page_tabs,
    message)


# --- Maschinenraum (M10) ---------------------------------------------------

@localized
def draw_engine_view(game, tr=None) -> None:
    layout.configure_for(game)
    s = game.screen
    ship = game.ship
    from src.core.commands import STATION_PAGES
    pages = STATION_PAGES[Station.ENGINE]
    page = int(getattr(game, "station_page", 0)) % len(pages)
    r, y = _panel(game, title="station.engine.title")
    station_rect = pygame.Rect(config.STATION_RECT)
    draw_station_page_tabs(s, station_rect, pages, page, tr)
    cy = _station_content_top(station_rect, len(pages))
    content_h = station_rect.bottom - cy - 34
    x, w = r[0] + 14, r[2] - 28

    if page == 0:
        gap = 16
        col_w = (w - gap) // 2
        orders = layout.box(s, (x, cy, col_w, content_h), "panel.engine_order")
        ox, oy, ow, _ = orders
        layout.blit_line(s, ship.telegraph, (ox, oy, ow, 40), config.COLOR_TEXT, size=28)
        oy += 48
        displayed_orders = (("ASTERN", config.ASTERN_SPEED_KN),
                            *config.TELEGRAPH_ORDERS)
        for i, (name, sp) in enumerate(displayed_orders):
            astern = getattr(ship, "astern", False)
            selected = astern if i == 0 else not astern and i - 1 == ship.order_idx
            mark = ">" if selected else " "
            col = config.COLOR_OK if selected else config.COLOR_TEXT_DIM
            if selected:
                pygame.draw.rect(s, (20, 43, 29), (ox - 4, oy - 2, ow + 8, 28))
            layout.status_line(s, ox, oy, ow,
                               message("engine.line.order", mark=mark, order=name),
                               message("bridge.line.speed", speed=f"{sp:4.1f}"),
                               color=col, label_w=200, size=18)
            oy += 32
        systems = layout.box(s, (x + col_w + gap, cy, col_w, content_h),
                              "panel.propulsion",
                             border=config.COLOR_DANGER if ship.cavitating else config.COLOR_TEXT)
        px, py, pw, _ = systems
        layout.status_line(s, px, py, pw, "panel.shaft",
                            message("engine.line.speed_target", speed=f"{ship.speed:4.1f}", target=f"{ship.target_speed:4.1f}"),
                           label_w=140, size=20)
        py += 40
        layout.status_line(s, px, py, pw, "engine.course",
                           message("engine.line.course_target",
                                   course=f"{ship.course:03.0f}",
                                   target=f"{ship.target_course:03.0f}"),
                           label_w=140, size=20)
        py += 40
        bar_w = int(pw * 0.72)
        max_rpm = Ship.max_rpm()
        frac = min(1.0, ship.rpm() / max_rpm)
        pygame.draw.rect(s, config.COLOR_GRID, (px, py, bar_w, 16))
        pygame.draw.rect(s, config.COLOR_TEXT, (px, py, int(bar_w * frac), 16))
        layout.blit_line(s, message("engine.line.rpm", rpm=f"{ship.rpm():3.0f}"),
                         (px + bar_w + 10, py - 2, pw - bar_w - 10, 24),
                         config.COLOR_TEXT_DIM, size=18)
        py += 42
        nf = ship.noise_level()
        pygame.draw.rect(s, config.COLOR_GRID, (px, py, bar_w, 16))
        pygame.draw.rect(s, config.COLOR_WARN, (px, py, int(bar_w * nf), 16))
        layout.blit_line(s, message("engine.line.noise", noise=f"{nf * 100:3.0f}"),
                         (px + bar_w + 10, py - 2, pw - bar_w - 10, 24),
                         config.COLOR_TEXT_DIM, size=18)
        py += 42
        if ship.cavitating:
            layout.blit_block(s, "engine.cavitation_warning", px, py, pw, 28,
                              color=config.COLOR_DANGER, size=20)
    else:
        cap = game.damage.engine_speed_cap()
        systems = layout.box(s, (x, cy, w, content_h), "panel.propulsion",
                             border=config.COLOR_DANGER if ship.cavitating else config.COLOR_TEXT)
        px, py, pw, _ = systems
        layout.status_line(s, px, py, pw, "panel.shaft",
                           message("engine.line.speed_target", speed=f"{ship.speed:4.1f}", target=f"{ship.target_speed:4.1f}"),
                           label_w=160, size=20)
        py += 38
        layout.status_line(s, px, py, pw, "panel.sea_state",
                           message("engine.line.sea_motion",
                                   sea=f"{getattr(game.world, 'effective_sea_state', game.world.sea_state):.1f}",
                                   roll=f"{ship.roll:4.1f}", pitch=f"{ship.pitch:4.1f}"),
                           label_w=160, size=18)
        py += 34
        list_deg = game.damage.list_deg()
        if abs(list_deg) > 0.05:
            layout.status_line(s, px, py, pw, "panel.hull_list",
                               message("engine.line.hull_list",
                                       side=localize("engine.list_starboard" if list_deg > 0
                                                     else "engine.list_port"),
                                       degrees=f"{abs(list_deg):3.1f}"),
                               label_w=160, size=18, color=config.COLOR_WARN)
            py += 34
        masch = game.damage.compartments.get("engine")
        if masch is not None:
            col = config.COLOR_DANGER if masch.state == "ZERSTOERT" else (
                config.COLOR_WARN if masch.flood > 20 or masch.fire > 0 else config.COLOR_OK)
            extra = (localize(message("engine.line.fire", fire=f"{masch.fire:3.0f}"))
                     if masch.fire > 0 else "")
            layout.blit_block(s, localize(message(
                                  "engine.machinery", state=localize(STATE_LABEL[masch.state]),
                                  flooding=f"{masch.flood:.0f}", extra=extra)),
                               px, py, pw, 26, color=col, size=18)
            py += 34
        fuel_fraction = (ship.fuel_kg / ship.fuel_capacity_kg
                         if ship.fuel_capacity_kg > 0.0 else 0.0)
        endurance = ship.fuel_endurance_h()
        distance = ship.fuel_range_nm()
        layout.status_line(s, px, py, pw, "engine.fuel",
                           message("engine.line.fuel", fuel=f"{ship.fuel_kg / 1000.0:.1f}",
                                   percent=f"{fuel_fraction:.0%}"),
                           color=(config.COLOR_DANGER if fuel_fraction <= 0.1
                                  else config.COLOR_WARN if fuel_fraction <= 0.25
                                  else config.COLOR_TEXT),
                           label_w=160, size=18)
        py += 34
        layout.status_line(s, px, py, pw, "engine.consumption",
                           message("engine.line.endurance",
                                   burn=f"{ship.fuel_burn_kg_h():.0f}",
                                   hours=(f"{endurance:.0f}" if endurance is not None else "--"),
                                   range=(f"{distance:.0f}" if distance is not None else "--")),
                           label_w=160, size=18)
        py += 34
        teams = game.damage.teams_on("engine")
        trend = game.damage.compartment_trend("engine")
        layout.status_line(s, px, py, pw, "engine.repairs",
                           message("engine.line.repairs",
                                   teams=", ".join(str(team) for team in teams) or "--",
                                   flood=f"{trend['flood_rate']:+.2f}",
                                   fire=f"{trend['fire_rate']:+.2f}"),
                           color=config.COLOR_OK if teams else config.COLOR_TEXT_DIM,
                           label_w=160, size=18)
        py += 34
        layout.status_line(s, px, py, pw, "view.engine.speed_limit",
                           message("bridge.line.speed", speed=f"{cap:4.1f}"),
                           label_w=160, size=18)
        py += 34
        layout.status_line(s, px, py, pw, "ui.acoustic_mode",
                            "engine.quiet_limit" if ship.quiet_mode else "station.normal",
                           color=config.COLOR_OK if ship.quiet_mode else config.COLOR_TEXT,
                           label_w=160, size=18)
        py += 34
        sonar_range = game.ship.passive_sonar_range_nm(
            0.5, getattr(game.world, "effective_sea_state", game.world.sea_state))
        if game.sonar_mode == "TOWED":
            sonar_range *= max(0.5, config.SONAR_ARRAY_TOWED_PASSIVE
                               - config.SONAR_TOWED_SPEED_PENALTY * ship.speed)
        available = game.sonar_mode != "TOWED" or game.sonar._tow_available()
        layout.status_line(s, px, py, pw, "ui.sonar_effect",
                            message("engine.line.sonar_effect", range=f"{sonar_range:4.1f}",
                                    array=display_value("array", game.sonar_mode))
                            if available else "engine.tas_unavailable",
                           color=config.COLOR_OK if available and sonar_range > 10 else config.COLOR_WARN,
                           label_w=160, size=18)
        py += 34
        cap_reason = ("engine.limit.down" if game.damage.station_down("engine") else
                      "engine.limit.damaged" if game.damage.station_degraded("engine") else
                      "engine.limit.none")
        layout.status_line(s, px, py, pw, "panel.limit", cap_reason,
                           label_w=160, size=18)

    station_bottom = config.STATION_RECT[1] + config.STATION_RECT[3]
    _shortcut_footer(s, (x, station_bottom - 26, w, 20), (
        ("↑/↓", "engine.footer.telegraph"),
        ("A", "engine.footer.quiet"),
        ("U", "engine.footer.set_course"),
        ("V", "engine.footer.set_speed"),
    ))
