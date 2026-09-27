"""Rendering and the main loop of the game: frame composition, the station
chrome (top bar, bottom panel, ticker), overlays (help, nations, save, end
panel, options, live traffic, quit), display preferences and the real-time
frame clock (``Game`` mixin).

Verbatim moves from ``game.py`` (plan 1.3, phase 2, step 4b)."""

import math
import time

import pygame

from src.audio.engine import AudioEngine
from src.core import config
from src.core.debuglog import append_bounded_log
from src.core.i18n import (Translator, display_value, localized, localize,
                           message, raw_text, translation_scope)
from src.core.preferences import save_preferences
from src.core.help import get_global_help, get_help, get_sop, get_uboot_help
from src.core import manual
from src.core.station import Station
from src.core import uboot_local
from src.nations.nations import reference_summary
from src.ui import layout
from src.ui import observations
from src.ui.map_view import draw_map_view
from src.ui.splash_view import draw_splash
from src.ui.sonar_view import draw_sonar_view
from src.ui.weather_station import draw_weather_station
from src.ui import uboot_view
from src.ui.stations_view import (
    draw_autocrew_overview,
    draw_bridge_view,
    draw_lookout_glasses,
    draw_damage_view,
    draw_eloka_view,
    draw_engine_view,
    draw_opz_view,
    draw_radio_view,
    draw_helicopter_view)
from src.ui.stations_view import opz_ppi_rect
from src.ui.mission_editor import MissionEditor
from src.ui.simlog_view import draw_simlog_view
from src.ui.weapons_view import draw_weapons_overlay, draw_weapons_panel
# Shared display/help constants and helpers (re-exported for tests/tools).
from src.core.game_shared import HELP_MANUAL_PAGE, HELP_PAGE_COUNT, letterbox_layout
# Names tests and tools import from ``src.core.game`` (kept as re-exports).
from src.core.game_events import _ECO_REFRESH_EVENTS


class DrawMixin:
    """Display half of ``Game``: ``draw``, the overlays and ``run``."""

    def flash_banner_rect(self) -> pygame.Rect:
        """Opaque, text-sized banner in the free right part of the top bar.

        It starts right of the status line, so it never prints over a map,
        station tabs or chart labels; only a message too long for one line
        grows downward (at most two lines).
        """
        face = layout.font(layout.scaled_size(self.FLASH_TEXT_SIZE))
        left = max(config.SCREEN_W // 2,
                   getattr(self, "_top_status_right", 0) + 16)
        max_w = config.SCREEN_W - 6 - left
        lines = layout.wrap_text(localize(self.msg), face, max_w - 20)
        lines = lines[:self.FLASH_MAX_LINES] or [""]
        width = min(max_w, max(face.size(line)[0] for line in lines) + 20)
        height = max(config.TOP_BAR_H - 4,
                     len(lines) * layout._line_height(face) + 6)
        return pygame.Rect(config.SCREEN_W - 6 - width, 2, width, height)

    def _draw_flash_banner(self, surface) -> None:
        # The banner covers what lies beneath it instead of printing over
        # the map and the station tabs.
        box = self.flash_banner_rect()
        pygame.draw.rect(surface, config.COLOR_OVERLAY_BG, box)
        pygame.draw.rect(surface, config.COLOR_WARN, box, 1)
        layout.blit_block(surface, localize(self.msg), box.x + 10, box.y + 3,
                          box.w - 20, box.h - 6, config.COLOR_WARN,
                          size=self.FLASH_TEXT_SIZE, align="center", valign="center")

    def compose_frame(self) -> None:
        """Virtuellen 1280x720-Canvas aufs Display bringen (M8/M9).

        FILL_SCREEN=True: Stretch auf die volle Fläche (keine schwarzen
        Balken bei 16:9); False: aspect-correctes Letterbox.
        """
        w, h = pygame.display.get_window_size()
        if w <= 0 or h <= 0:
            w, h = config.SCREEN_W, config.SCREEN_H
        # Unter X11/XWayland ersetzt pygame die Display-Surface nach dem ersten
        # Event-Pump/Resize durch ein neues Objekt; das gemerkte self.display
        # ist dann 0x0 und der Blit scheitert mit "Surfaces must not be locked".
        display = pygame.display.get_surface()
        if display is None:
            return
        self.display = display
        display.fill((0, 0, 0))
        if (w, h) == (config.SCREEN_W, config.SCREEN_H):
            display.blit(self.screen, (0, 0))
        elif config.FILL_SCREEN:
            display.blit(pygame.transform.scale(self.screen, (w, h)), (0, 0))
        else:
            _, ox, oy, sw, sh = letterbox_layout(w, h)
            display.blit(
                pygame.transform.scale(self.screen, (sw, sh)), (ox, oy))
        pygame.display.flip()

    # --- Input ---

    @localized
    def draw_menu(self) -> None:
        """W4: Szenario -> (Level bei s4) -> Briefing -> Start."""
        s = self.screen
        s.fill(config.COLOR_BG)
        cx = config.SCREEN_W // 2

        def center(text: str, y: int, font=None, color=config.COLOR_TEXT) -> None:
            f = font or self.menu_font
            text = localize(text)
            surf = f.render(text, True, color)
            s.blit(surf, surf.get_rect(center=(cx, y)))

        center("U-JAGD – FREGATTE F-217", 100, self.menu_font_big)

        if self.main_menu:
            labels = ("menu.new_game", "menu.load", "menu.mission_editor",
                      "menu.unit_editor", "menu.contact_analyzer", "option.title",
                      "menu.quit")
            for i, key in enumerate(labels):
                marker = "> " if i == self.main_menu_sel else "  "
                color = config.COLOR_TEXT if i == self.main_menu_sel else config.COLOR_TEXT_DIM
                center(message("menu.choice", marker=marker,
                               label=self.tr(key).upper()), 185 + i * 47, color=color)
        elif self.menu_screen == "side":
            center(self.tr("menu.choose_side"), 170, color=config.COLOR_TEXT_DIM)
            for i, side in enumerate(("frigate", "uboot")):
                selected = i == self.menu_sel
                center(message("menu.choice", marker="► " if selected else "  ",
                               label=self.tr(f"menu.side.{side}")),
                       250 + i * 90, self.menu_font_big if selected else None,
                       config.COLOR_TEXT if selected else config.COLOR_TEXT_DIM)
                layout.blit_line(s, f"menu.side.{side}.note", (cx - 420, 285 + i * 90, 840, 26),
                                 config.COLOR_TEXT_DIM, size=18, align="center")
            center(self.tr("menu.side_hint"), 470, color=config.COLOR_TEXT_DIM)
        elif self.menu_screen == "scenario":
            center(self.tr("menu.choose_scenario"),
                   150, color=config.COLOR_TEXT_DIM)
            scenario_names = {"s1_patrouille": "patrol", "s2_doppeljagd": "double",
                              "s3_abfang": "intercept", "s4_zufall": "random"}
            for i, key in enumerate(config.SCENARIO_ORDER):
                sc = config.SCENARIOS[key]
                marker = "► " if i == self.menu_sel else "  "
                col = config.COLOR_TEXT if i == self.menu_sel \
                    else config.COLOR_TEXT_DIM
                lv = self.tr("menu.difficulty_fixed" if sc["difficulty"] is not None
                             else "menu.difficulty_custom")
                title = self.tr("scenario." + scenario_names[key] + ".title")
                center(message("menu.scenario_choice", index=i + 1,
                               marker=marker, title=title, level=lv),
                       240 + i * 40, color=col)
        elif self.menu_screen == "difficulty":
            center(self.tr("menu.choose_difficulty"),
                   150, color=config.COLOR_TEXT_DIM)
            row_h = 26
            for i, name in enumerate(config.DIFFICULTY_FIELD_ORDER):
                kind, _low, _high, _step, _default = config.DIFFICULTY_FIELDS[name]
                marker = "► " if i == self.menu_sel else "  "
                col = config.COLOR_TEXT if i == self.menu_sel \
                    else config.COLOR_TEXT_DIM
                value = self.menu_difficulty[name]
                value_text = (str(value) if kind is int
                             else f"{value:.3f}".rstrip("0").rstrip("."))
                center(message("menu.difficulty_choice", marker=marker,
                               label=self.tr("difficulty." + name),
                               value=value_text),
                       190 + i * row_h, color=col)
            i = len(config.DIFFICULTY_FIELD_ORDER)
            selected = i == self.menu_sel
            center(message("menu.difficulty_choice",
                           marker="► " if selected else "  ",
                           label=self.tr("menu.hq_intel"),
                           value=self.tr("menu.hq_intel." + self.hq_intel_mode_menu())),
                   190 + i * row_h,
                   color=config.COLOR_TEXT if selected else config.COLOR_TEXT_DIM)
        else:  # briefing
            sc = config.SCENARIOS[self.scenario_key]
            scenario_key = {"s1_patrouille": "patrol", "s2_doppeljagd": "double",
                            "s3_abfang": "intercept", "s4_zufall": "random"}[self.scenario_key]
            center(self.tr("scenario." + scenario_key + ".title"), 170,
                   self.menu_font_big, config.COLOR_WARN)
            layout.blit_block(s, self.tr("scenario." + scenario_key + ".brief"),
                              cx - 420, 210, 840, 180,
                              color=config.COLOR_TEXT, size=20)
            if sc["win_text"]:
                center(message("menu.goal_value",
                               goal=self.tr("scenario." + scenario_key + ".win")),
                       420, color=config.COLOR_OK)
            if sc["lose_text"]:
                center(message("menu.loss_value",
                               loss=self.tr("scenario." + scenario_key + ".lose")), 448,
                       color=config.COLOR_DANGER)
            center(self.tr("menu.start_hint"), 520,
                   color=config.COLOR_TEXT_DIM)
            center(message("menu.local_side", side=message(
                "menu.local_side.uboot" if self.local_side == "uboot"
                else "menu.local_side.frigate")), 556,
                color=config.COLOR_WARN if self.local_side == "uboot"
                else config.COLOR_TEXT_DIM)

        if self.world_mode in ("procedural", "real_fixed"):
            from src.world.real_coast import sector_for_seed
            sector, _ = sector_for_seed(self.seed)
            world_label = sector["name"]
            if self.world_mode == "real_fixed":
                center(self.tr("menu.real_fixed_hint", sector=sector["id"]),
                       config.SCREEN_H - 95, color=config.COLOR_TEXT_DIM)
        else:
            world_label = self.tr("menu.fixed_chart")
        center(self.tr("menu.world_status", world=world_label, seed=self.seed),
               config.SCREEN_H - 68, color=config.COLOR_OK)
        center(self.tr("menu.seed_fullscreen", seed=self.seed,
                       action=self.tr("menu.windowed" if self.fullscreen
                                      else "menu.fullscreen")),
               config.SCREEN_H - 40, color=config.COLOR_TEXT_DIM)

    # --- W0: Draw-Grid ---

    @property
    def _station_overlay_open(self) -> bool:
        """A full-station overlay (F3 autocrew, 0 weather) replaces the station."""
        return self.autocrew_overview_open or self.weather_station_open

    @localized
    def _eco_display_active(self) -> bool:
        """Solo browser is live: the uConsole shows a cheap status screen.

        Pure display decision; it never touches simulation state, saves or input.
        """
        return (self.running and not self.splash_active and self.editor is None
                and not self.simlog_view_open and not self.in_menu
                and not self.main_menu and not self.administration_open
                and not self.game_over and not self._station_overlay_open
                and self.commander.eco_display_ready(self))

    def _skip_eco_frame(self) -> bool:
        """True while the last eco frame is still current (draw and blit skipped)."""
        if not self._eco_display_active():
            self._eco_drawn_at = float("-inf")
            return False
        if self._t - self._eco_drawn_at < config.ECO_REDRAW_S:
            return True
        self._eco_drawn_at = self._t
        return False

    @localized
    def draw_eco_display(self) -> None:
        s = self.screen
        panel = pygame.Rect(240, 90, 800, 360)
        layout.panel(s, panel)
        x, w = panel.x + 24, panel.w - 48
        layout.blit_line(s, "eco.title", (x, panel.y + 16, w, 36),
                         config.COLOR_WARN, size=28, align="center")
        layout.blit_block(s, "eco.subtitle", x, panel.y + 66, w, 66,
                          config.COLOR_TEXT, size=20, align="center", valign="center")
        address = getattr(self.commander, "address", None)
        if address is not None:
            url = raw_text(f"http://{address[0]}:{address[1]}/")
            proxy = getattr(self.commander, "public_origin", None)
            layout.blit_line(s, message("commander.local.url_proxy", url=url,
                                        proxy=raw_text(proxy + "/"))
                             if proxy else message("commander.local.url", url=url),
                (x, panel.y + 150, w, 32), config.COLOR_TEXT, size=22, align="center")
        layout.blit_line(s, message(
            "eco.state.running", time=raw_text(self.world.format_time())),
            (x, panel.y + 200, w, 32), config.COLOR_OK,
            size=24, align="center")
        layout.blit_line(s, "eco.hint", (x, panel.bottom - 56, w, 30),
                         config.COLOR_TEXT_DIM, size=16, align="center")

    def draw(self) -> None:
        # One translation scope for the whole frame: text drawn directly here
        # (flash banner, overlays) must follow the game language, not the
        # process-wide default translator.
        with layout.bottom_panel_regions(self.bottom_panel_mode()), \
                translation_scope(self.tr):
            self._draw()

    def _draw(self) -> None:
        self._apply_text_size()
        s = self.screen
        eco = self._eco_display_active()
        s.fill(config.COLOR_BG)
        if self.splash_active:
            draw_splash(s, self._t - self.splash_started_at, self.tr)
        elif self.editor is not None:
            self.editor.draw(s)
            if isinstance(self.editor, MissionEditor) and self.editor.mode == "browser":
                hint = self.font.render(localize("F5: start selected runtime-compatible mission"),
                                        True, config.COLOR_OK)
                s.blit(hint, (config.SCREEN_W - hint.get_width() - 20,
                              config.SCREEN_H - 68))
        elif self.simlog_view_open:
            draw_simlog_view(self)
        elif self.in_menu:
            self.draw_menu()
        elif self.local_side == "uboot":
            uboot_view.draw(self)
        elif eco:
            self.draw_top_bar()
            self.draw_eco_display()
            self.draw_bottom_panel()
        else:
            self.draw_top_bar()
            map_station = (not self._station_overlay_open
                           and self._map_station_visible())
            previous_rect = config.STATION_RECT
            try:
                config.STATION_RECT = (config.STATION_PANEL_RECT if map_station else
                                       # The weather panel takes the whole
                                       # screen below the top bar.
                                       config.OPZ_STATION_RECT
                                       if self.weather_station_open
                                       or (self.station is Station.OPZ
                                           and not self._station_overlay_open) else
                                       config.FULL_STATION_RECT)
                if self.autocrew_overview_open:
                    with layout.clip_to(s, config.STATION_RECT):
                        draw_autocrew_overview(self)
                elif self.weather_station_open:
                    with layout.clip_to(s, config.STATION_RECT):
                        draw_weather_station(self)
                elif map_station:
                    draw_map_view(self)
                    if self.lookout_glasses_shown():
                        draw_lookout_glasses(self)
                    if self.station is Station.WEAPONS:
                        draw_weapons_overlay(self)
                if not self._station_overlay_open:
                    with layout.clip_to(s, config.STATION_RECT):
                        if self.station is Station.SONAR:
                            draw_sonar_view(self)
                        elif self.station is Station.WEAPONS:
                            draw_weapons_panel(self)
                        elif self.station is Station.DAMAGE:
                            draw_damage_view(self)
                        elif self.station is Station.OPZ:
                            draw_opz_view(self)
                        elif self.station is Station.RADIO:
                            draw_radio_view(self)
                        elif self.station is Station.ENGINE:
                            draw_engine_view(self)
                        elif self.station is Station.HELICOPTER:
                            draw_helicopter_view(self)
                        elif self.station is Station.ELOKA:
                            draw_eloka_view(self)
                        else:
                            draw_bridge_view(self)
                if (self.station is not Station.OPZ and not self.weather_station_open
                        and not self.feed_overlay_open):
                    self.draw_bottom_panel()
                if self.feed_overlay_open:
                    self.draw_feed_overlay()
                self.draw_navigation_input()
                if self.game_over and self.debrief_open:
                    from src.ui.debrief_view import draw_debrief
                    draw_debrief(self)
                elif self.game_over:
                    self.draw_end_panel()
            finally:
                config.STATION_RECT = previous_rect
        if self.quit_confirm:
            self.draw_quit_overlay()
        elif self.help_open:
            self.draw_help_overlay()
        elif self.nations_open:
            self.draw_nations_overlay()
        elif self.save_ui is not None:
            self.draw_save_ui()
        elif self.options_open:
            self.draw_options_overlay()
        elif self.live_traffic_open:
            self.draw_live_traffic_overlay()
        elif self.commander_open:
            self.commander.draw(self)
        self.commander.draw_confirm(self)
        if self.msg and self._t < self.msg_until:
            self._draw_flash_banner(s)
        if (not self.in_menu and not self.splash_active and self.editor is None
                and not self.simlog_view_open and not self._station_overlay_open
                and self.tooltips_enabled and not eco
                and self.local_side != "uboot"
                and not self.administration_open and not self.game_over):
            canvas = self._window_to_canvas(pygame.mouse.get_pos())
            payload = self.pinned_tooltip or self.tooltip_at(canvas)
            anchor = self._tooltip_anchor if self.pinned_tooltip else canvas
            if payload is not None and anchor is not None:
                layout.draw_tooltip(s, payload, anchor,
                                    (0, 0, config.SCREEN_W, config.SCREEN_H))
        if self._scanlines is not None:
            s.blit(self._scanlines, (0, 0))
        if self.preferences.night_mode:
            s.blit(self._night_overlay, (0, 0), special_flags=pygame.BLEND_MULT)

    @localized
    def draw_navigation_input(self) -> None:
        """Show the active numeric command without hiding the simulation."""
        if self.input_mode is None:
            return
        label = self.tr("input." + self.input_mode)
        rect = pygame.Rect(280, 88, 720, 70)
        pygame.draw.rect(self.screen, config.COLOR_OVERLAY_BG, rect)
        pygame.draw.rect(self.screen, config.COLOR_WARN, rect, 2)
        layout.blit_line(self.screen, self.tr("input.value", label=label,
                                              value=self.input_buffer),
                         (rect.x + 14, rect.y + 8, rect.w - 28, 26),
                         config.COLOR_TEXT, size=20)
        layout.blit_line(self.screen, self.tr("input.hint"),
                         (rect.x + 14, rect.y + 38, rect.w - 28, 22),
                         config.COLOR_TEXT_DIM, size=14)

    @localized
    def top_bar_scenario(self) -> str:
        """Mission title shown in the top status bar."""
        if self.custom_mission_definition is not None:
            return localize(self.mission_name_display())
        return self.tr("scenario." + {"s1_patrouille": "patrol", "s2_doppeljagd": "double",
                                      "s3_abfang": "intercept", "s4_zufall": "random"}
                       [self.scenario_key] + ".title")

    def draw_top_bar(self) -> None:
        layout.configure_for(self)
        s = self.screen
        pygame.draw.rect(s, config.COLOR_PANEL_BG, (0, 0, config.SCREEN_W, config.TOP_BAR_H))
        pygame.draw.line(s, config.COLOR_SONAR_RING,
                         (0, config.TOP_BAR_H - 1),
                         (config.SCREEN_W, config.TOP_BAR_H - 1), 1)
        station = display_value("station", self.station.name, self.tr).upper()
        scenario = self.top_bar_scenario()
        txt = self.tr("top.status", station=station, scenario=scenario,
                      time=self.world.format_time(), speed=f"{self.ship.speed:4.1f}",
                      course=f"{self.ship.course:4.0f}")
        layout.blit_line(s, txt, (10, 4, config.SCREEN_W - 20,
                                  config.TOP_BAR_H - 8),
                         config.COLOR_TEXT, size=18)
        self._top_status_right = 10 + layout.font(layout.scaled_size(18)).size(
            localize(txt))[0]

    def draw_bottom_panel(self, entries=None, rows=None, heading="feed.heading",
                          ticker_keys=None, ticker_hint="ticker.hint") -> None:
        """Event feed and telemetry: docked band or one status ticker.

        ``entries``/``rows`` replace the frigate's feed and telemetry (the
        crewed submarine's own log and readings use the same band).
        """
        if self.bottom_panel_mode() == "ticker":
            self.draw_status_ticker(entries, rows, ticker_keys, ticker_hint)
        else:
            self.draw_bottom_feed(entries, heading)
            self.draw_bottom_telemetry(rows)

    def _feed_lines(self, width: int, face, entries=None) -> list:
        """Wrap feed entries (oldest first) into (text, colour, is_first) rows.

        Entries wrap onto continuation lines under the text column; nothing
        is ever cut off with an ellipsis.
        """
        rows = []
        for entry in self.feed.entries if entries is None else entries:
            prefix = f"[{entry.stamp}] {entry.tag():4s} "
            indent = face.size(prefix)[0]
            wrapped = layout.wrap_text(localize(entry.text), face,
                                       max(40, width - indent)) or [""]
            rows.append((prefix, wrapped[0], entry.color(), indent))
            rows.extend(("", line, entry.color(), indent) for line in wrapped[1:])
        return rows

    def _blit_feed_rows(self, rect, rows, scroll: int = 0) -> None:
        """Draw wrapped feed rows bottom-up (newest at the bottom)."""
        face = layout.font(16)
        pitch = layout._line_height(face)
        visible = max(1, rect.h // pitch)
        end = max(0, len(rows) - scroll)
        shown = rows[max(0, end - visible):end]
        y = rect.bottom - len(shown) * pitch
        with layout.clip_to(self.screen, rect):
            for prefix, text, color, indent in shown:
                if prefix:
                    layout.blit_line(self.screen, raw_text(prefix),
                                     (rect.x, y, indent, pitch),
                                     config.COLOR_TEXT_DIM, size=16)
                layout.blit_line(self.screen, raw_text(text),
                                 (rect.x + indent, y, rect.w - indent, pitch),
                                 color, size=16)
                y += pitch

    @localized
    def draw_bottom_feed(self, entries=None, heading="feed.heading") -> None:
        s = self.screen
        x, y, w, h = config.FEED_RECT
        pygame.draw.rect(s, config.COLOR_FEED_BG, (x, y, w, h))
        pygame.draw.rect(s, config.COLOR_SONAR_RING, (x, y, w, h), 1)
        layout.blit_line(s, heading, (x + 8, y + 3, w - 16, 20),
                         config.COLOR_TEXT_DIM, size=16)
        body = pygame.Rect(x + 8, y + 25, w - 16, h - 29)
        face = layout.font(16)
        self._blit_feed_rows(body, self._feed_lines(body.w, face, entries))

    @localized
    def draw_bottom_telemetry(self, rows=None) -> None:
        s = self.screen
        x, y, w, h = config.TELEMETRY_RECT
        pygame.draw.rect(s, config.COLOR_FEED_BG, (x, y, w, h))
        pygame.draw.rect(s, config.COLOR_SONAR_RING, (x, y, w, h), 1)
        layout.blit_line(s, "panel.telemetry", (x + 8, y + 3, w - 16, 20),
                         config.COLOR_TEXT_DIM, size=16)
        self._blit_telemetry_rows(pygame.Rect(x + 8, y + 25, w - 16, h - 29),
                                  short=True, rows=rows)

    def _blit_telemetry_rows(self, rect, short: bool, rows=None) -> None:
        face = layout.font(16)
        rows = observations.telemetry_rows(self) if rows is None else rows
        pitch = max(layout._line_height(face), rect.h // max(1, len(rows)))
        labels = [localize(observations.telemetry_label(key, short))
                  for key, *_rest in rows]
        label_w = max(face.size(label)[0] for label in labels) + 10
        colors = {"ok": config.COLOR_TEXT, "warn": config.COLOR_WARN,
                  "danger": config.COLOR_DANGER}
        for index, ((_key, value, level, _compact), label) in enumerate(zip(rows, labels)):
            y = rect.y + index * pitch
            layout.blit_line(self.screen, raw_text(label), (rect.x, y, label_w, pitch),
                             config.COLOR_TEXT_DIM, size=16)
            layout.blit_line(self.screen, value, (rect.x + label_w, y,
                                                  rect.w - label_w, pitch),
                             colors[level], size=16)

    def _ticker_telemetry_text(self, width: int | None = None, rows=None,
                               keys=None) -> str:
        """Compact telemetry for the ticker, most important readings first.

        Readings that do not fit are left out whole (never clipped); the
        F11 overlay always shows all of them.
        """
        parts = []
        keys = observations.TICKER_KEYS if keys is None else keys
        rows = observations.telemetry_rows(self) if rows is None else rows
        for key, _value, _level, compact in rows:
            if key in keys:
                label = observations.telemetry_label(key, short=True)
                parts.append(f"{localize(label)} {localize(compact)}")
        face = layout.font(16)
        while width is not None and len(parts) > 1 and face.size(
                " \u00b7 ".join(parts))[0] > width:
            parts.pop()
        return " \u00b7 ".join(parts)

    @localized
    def draw_status_ticker(self, entries=None, rows=None, keys=None,
                           hint_key="ticker.hint") -> None:
        """One 22 px strip: newest event (scrolls if long) + key telemetry."""
        s = self.screen
        rect = layout.ticker_rect()
        pygame.draw.rect(s, config.COLOR_FEED_BG, rect)
        pygame.draw.line(s, config.COLOR_SONAR_RING, rect.topleft, rect.topright, 1)
        face = layout.font(16)
        rows = observations.telemetry_rows(self) if rows is None else rows
        telemetry = self._ticker_telemetry_text(int(rect.w * .6) - 16, rows, keys)
        level = ("danger" if any(row[2] == "danger" for row in rows)
                 else "warn" if any(row[2] == "warn" for row in rows) else "ok")
        colors = {"ok": config.COLOR_TEXT, "warn": config.COLOR_WARN,
                  "danger": config.COLOR_DANGER}
        tele_w = face.size(telemetry)[0] + 16
        tele_rect = pygame.Rect(rect.right - tele_w, rect.y + 2, tele_w - 8, rect.h - 2)
        layout.blit_line(s, raw_text(telemetry), tele_rect, colors[level],
                         size=16, align="right")
        hint = localize(hint_key) if hint_key else ""
        hint_w = face.size(hint)[0] + 12 if hint else 0
        if hint:
            layout.blit_line(s, raw_text(hint), (rect.x + 6, rect.y + 2, hint_w, rect.h - 2),
                             config.COLOR_TEXT_DIM, size=16)
        feed_rect = pygame.Rect(rect.x + 6 + hint_w, rect.y + 2,
                                tele_rect.x - 12 - (rect.x + 6 + hint_w), rect.h - 2)
        latest = self.feed.recent(1) if entries is None else list(entries)[-1:]
        if not latest or feed_rect.w <= 20:
            return
        entry = latest[0]
        text = f"[{entry.stamp}] {entry.tag()} {localize(entry.text)}"
        width = face.size(text)[0]
        with layout.clip_to(s, feed_rect):
            if width <= feed_rect.w:
                layout.blit_line(s, raw_text(text), feed_rect, entry.color(), size=16)
            else:
                # Marquee instead of an ellipsis: the full line stays readable.
                gap = 60
                offset = int(self._t * config.TICKER_SCROLL_PX_S) % (width + gap)
                surface = layout.font(16).render(text, True, entry.color())
                s.blit(surface, (feed_rect.x - offset, feed_rect.y))
                s.blit(surface, (feed_rect.x - offset + width + gap, feed_rect.y))

    def feed_overlay_rect(self) -> pygame.Rect:
        return pygame.Rect(0, config.SCREEN_H - 330, config.SCREEN_W, 330)

    @localized
    def draw_feed_overlay(self) -> None:
        """F11: full event history and telemetry over the station (display only)."""
        s = self.screen
        rect = self.feed_overlay_rect()
        shade = pygame.Surface(rect.size, pygame.SRCALPHA)
        shade.fill((*config.COLOR_FEED_BG, 238))
        s.blit(shade, rect.topleft)
        pygame.draw.rect(s, config.COLOR_WARN, rect, 1)
        tele_w = 360
        feed = pygame.Rect(rect.x + 10, rect.y + 30, rect.w - tele_w - 30, rect.h - 40)
        tele = pygame.Rect(rect.right - tele_w - 10, rect.y + 30, tele_w, rect.h - 40)
        face = layout.font(16)
        rows = self._feed_lines(feed.w, face)
        visible = max(1, feed.h // layout._line_height(face))
        self.feed_overlay_scroll = max(0, min(self.feed_overlay_scroll,
                                              len(rows) - visible))
        layout.blit_line(s, message("feed.overlay.title",
                                    shown=min(len(rows), visible), total=len(rows)),
                         (rect.x + 10, rect.y + 5, feed.w, 22), config.COLOR_WARN,
                         size=16)
        layout.blit_line(s, "panel.telemetry", (tele.x, rect.y + 5, tele.w, 22),
                         config.COLOR_WARN, size=16)
        self._blit_feed_rows(feed, rows, self.feed_overlay_scroll)
        pygame.draw.line(s, config.COLOR_SONAR_RING, (tele.x - 10, feed.y),
                         (tele.x - 10, feed.bottom), 1)
        self._blit_telemetry_rows(pygame.Rect(tele.x, tele.y, tele.w, 7 * 26),
                                  short=False)
        layout.blit_block(s, "feed.overlay.hint", tele.x, tele.bottom - 44, tele.w,
                          44, config.COLOR_TEXT_DIM, size=16)

    def _help_lines(self) -> tuple[list[str], int]:
        """Wrap before scrolling so every line remains reachable at either size."""
        layout.configure_for(self)
        intro, keys, params, tactics = get_help(self.station, self.tr)
        face = layout.font(18)
        visible = max(1, 500 // layout._line_height(face))
        if self.help_page == HELP_MANUAL_PAGE:
            chapter = manual.CHAPTERS[self.help_manual_chapter % len(manual.CHAPTERS)]
            blocks = manual.chapter_blocks(chapter, manual.manual_language(self.tr))
            width = max(20, 960 // max(1, face.size("M")[0]))
            # Leading blanks survive word wrapping only as no-break spaces.
            lines = [line[:len(line) - len(line.lstrip(" "))].replace(" ", "\u00a0")
                     + line.lstrip(" ") for line in manual.text_lines(blocks, width)]
            return lines, visible
        if self.help_page == 0:
            title, bindings = get_global_help(self.tr)
            text = title + "\n\n" + "\n".join(f"{k:<18} {a}" for k, a in bindings)
        elif self.help_page == 1 and self.local_side == "uboot":
            title, bindings = get_uboot_help(self.tr)
            text = title + "\n\n" + "\n".join(f"{k:<18} {a}" for k, a in bindings)
        elif self.help_page == 1:
            sop = get_sop(self.station, self.tr)
            text = (intro + "\n\n" + "\n".join(f"{k:<18} {a}" for k, a in keys)
                    + "\n\n" + self.tr("help.sop.title") + "\n"
                    + "\n".join(f"{n}. {step}" for n, step in enumerate(sop, 1)))
        else:
            text = self.tr("help.sensors_tactics") + "\n\n" + "\n\n".join(params + tactics)
        return layout.wrap_text(text, face, 960), visible

    @localized
    def draw_help_overlay(self) -> None:
        layout.configure_for(self)
        s = self.screen
        dim = pygame.Surface((config.SCREEN_W, config.SCREEN_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 170))
        s.blit(dim, (0, 0))
        bw, bh = 1000, 620
        bx = (config.SCREEN_W - bw) // 2
        by = (config.SCREEN_H - bh) // 2
        pygame.draw.rect(s, config.COLOR_PANEL_BG, (bx, by, bw, bh))
        pygame.draw.rect(s, config.COLOR_SONAR_RING, (bx, by, bw, bh), 2)
        help_title = self.tr("help.title", station=display_value(
            "station", self.station.name, self.tr).upper())
        layout.blit_line(s, help_title, (bx + 18, by + 10, bw - 36, 40),
                         config.COLOR_TEXT, size=30)
        x = bx + 20
        w = bw - 40
        y = by + 52
        lines, visible = self._help_lines()
        scroll = min(getattr(self, "help_scroll", 0), max(0, len(lines) - visible))
        body = "\n".join(lines[scroll:scroll + visible])
        if self.help_page == HELP_MANUAL_PAGE:
            body = raw_text(body)
            hint = self.tr("help.manual.hint",
                           chapter=self.help_manual_chapter % len(manual.CHAPTERS) + 1,
                           chapters=len(manual.CHAPTERS), first=scroll + 1,
                           last=min(len(lines), scroll + visible), total=len(lines))
        else:
            hint = self.tr("control.help.scroll_hint", page=self.help_page + 1,
                           pages=HELP_PAGE_COUNT, first=scroll + 1,
                           last=min(len(lines), scroll + visible), total=len(lines))
        layout.blit_block(s, body, x, y, w, 500, config.COLOR_TEXT, size=18, min_size=18)
        layout.blit_block(s, hint, x, by + bh - 62, w, 54, config.COLOR_TEXT_DIM, size=16)

    @localized
    def draw_nations_overlay(self) -> None:
        s = self.screen
        dim = pygame.Surface((config.SCREEN_W, config.SCREEN_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 160))
        s.blit(dim, (0, 0))
        bw, bh = 1100, 620
        bx = (config.SCREEN_W - bw) // 2
        by = (config.SCREEN_H - bh) // 2
        pygame.draw.rect(s, config.COLOR_PANEL_BG, (bx, by, bw, bh))
        pygame.draw.rect(s, config.COLOR_SONAR_RING, (bx, by, bw, bh), 2)
        layout.blit_line(s, "panel.nations", (bx + 18, by + 12, bw - 36, 38),
                         config.COLOR_TEXT, size=30)
        summary = getattr(self, "_nations_summary", None)
        if summary is None:
            summary = reference_summary(self.world.coast, self.runtime_catalog)
            self._nations_summary = summary
        legacy_country_names = {
            "HANSE": "nations.country.hanse",
            "BOREN": "nations.country.boren",
            "SKANDIA": "nations.country.skandia",
        }
        countries = ", ".join(self.tr(legacy_country_names[c])
                              if c in legacy_country_names else c
                              for c in summary["countries"]) or self.tr("nations.none")
        cards = (
            ("nations.area", self.tr("nations.countries", countries=countries)
             + "\n\n" + self.tr("nations.reference_note"), config.COLOR_FLIGHT),
            ("nations.friendly", "\n".join(summary["friendly"]), config.COLOR_OK),
            ("nations.hostile", self.tr("nations.subs", count=len(summary["hostile_subs"]))
             + "\n" + ", ".join(summary["hostile_subs"])
             + "\n\n" + self.tr("nations.surfaces", count=len(summary["hostile_surfaces"]))
             + "\n" + ", ".join(summary["hostile_surfaces"]), config.COLOR_DANGER),
            ("nations.other", self.tr("nations.neutral_military", count=summary["neutral_military"])
             + "\n\n" + self.tr("nations.civilian", count=summary["civilian"])
             + "\n\n" + self.tr("nations.catalog_hint"), config.COLOR_CONTACT_ZIVIL),
        )
        cw, ch = 520, 260
        for i, (title, body, color) in enumerate(cards):
            cx = bx + 18 + (i % 2) * (cw + 14)
            cyy = by + 52 + (i // 2) * (ch + 12)
            pygame.draw.rect(s, config.COLOR_PANEL_BG, (cx, cyy, cw, ch))
            pygame.draw.rect(s, color, (cx, cyy, cw, ch), 1)
            layout.blit_line(s, title, (cx + 12, cyy + 8, cw - 24, 36), color, size=24)
            layout.blit_block(s, body, cx + 12, cyy + 50, cw - 24, ch - 58,
                              color=config.COLOR_TEXT, size=18)
        layout.blit_line(s, "nations.close", (bx + bw - 160, by + bh - 30, 140, 24),
                         config.COLOR_TEXT_DIM, size=16, align="right")

    @localized
    def draw_save_ui(self) -> None:
        s = self.screen
        mode = self.tr("common.save" if self.save_ui == "save" else "common.load").upper()
        dim = pygame.Surface((config.SCREEN_W, config.SCREEN_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 150))
        s.blit(dim, (0, 0))
        bw, bh = 660, 380
        bx = (config.SCREEN_W - bw) // 2
        by = (config.SCREEN_H - bh) // 2
        pygame.draw.rect(s, config.COLOR_PANEL_BG, (bx, by, bw, bh))
        pygame.draw.rect(s, config.COLOR_SONAR_RING, (bx, by, bw, bh), 2)
        layout.blit_line(s, self.tr("save.title", mode=mode),
                         (bx + 18, by + 14, bw - 36, 34), config.COLOR_TEXT, size=22)
        ly = by + 70
        for slot in range(1, 6):
            info = self.save_info[slot - 1] if len(self.save_info) == 5 else "--"
            selected = slot == self.save_slot
            col = config.COLOR_WARN if selected else config.COLOR_TEXT_DIM
            layout.blit_line(s, message("save.slot", marker=">" if selected else " ",
                                         slot=slot, info=localize(info)),
                             (bx + 24, ly, bw - 48, 32), col, size=19)
            ly += 42
        hint = "save.live"
        if self.save_confirm:
            hint = ("save.overwrite" if self.save_ui == "save"
                    else "save.replace")
        layout.blit_line(s, hint, (bx + 18, by + bh - 54, bw - 36, 34),
                         config.COLOR_WARN, size=18)

    @localized
    def draw_end_panel(self) -> None:
        """M8: Endpanel mit Score-Bruchrechnung und Hinweisen."""
        s = self.screen
        dim = pygame.Surface((config.SCREEN_W, config.SCREEN_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 140))
        s.blit(dim, (0, 0))
        w, h = 700, 340
        x = (config.SCREEN_W - w) // 2
        y = (config.SCREEN_H - h) // 2
        pygame.draw.rect(s, (12, 26, 18), (x, y, w, h))
        pygame.draw.rect(s, config.COLOR_TEXT_DIM, (x, y, w, h), 2)
        col = config.COLOR_OK if self.mission_result == "SIEG" else config.COLOR_DANGER
        result = self.tr("end.victory" if self.mission_result == "SIEG"
                         else "end.defeat")
        lines = [
            (message("end.result", result=result,
                     reason=localize(self.result_reason)), col, True),
            ("", config.COLOR_TEXT, False),
            (message("end.score_value", score=self.score), config.COLOR_TEXT, True),
            (message("end.mission_level", mission=self.mission_name_display(),
                     level=self.mission_level_display()),
             config.COLOR_TEXT_DIM, False),
            (message("end.time_remaining",
                     remaining=self.mission.format_remaining(self.mission_time))
             if (self.mission_result == "SIEG"
                 or self.mission_time < self.mission.time_limit_s)
             else "end.expired",
             config.COLOR_TEXT_DIM, False),
        ]
        board = getattr(self, "tasking", None)
        if board is not None and board.tasks:
            counts = board.counts()
            lines.append((message("end.tasks", done=counts["done"], failed=counts["failed"],
                                  declined=counts["declined"]),
                          config.COLOR_TEXT_DIM, False))
        lines += [
            ("", config.COLOR_TEXT, False),
            ("end.restart", config.COLOR_TEXT_DIM, False),
        ]
        ly = y + 44
        for text, c, big in lines:
            if not text:
                ly += 16
                continue
            size = 26 if big else 20
            height = 36 if big else 26
            layout.blit_line(s, text, (x + 16, ly, w - 32, height), c,
                             size=size, align="center")
            ly += 42 if big else 30

    @classmethod
    def _options_row_rects(cls):
        return tuple(pygame.Rect(292, 118 + index * 40, 696, 36)
                     for index in range(max(len(page) for page in cls._OPTION_PAGES)))

    # Row rect index of each setup-page row (the side's help text sits between).
    _SETUP_ROW_INDICES = (0, 7)

    @classmethod
    def _option_row_hit_rects(cls, rows) -> tuple:
        """Clickable rects of the shown options rows, in row order."""
        rects = cls._options_row_rects()
        if rows is cls._OPTION_ROWS_SETUP:
            return tuple(rects[index] for index in cls._SETUP_ROW_INDICES[:len(rows)])
        return rects[:len(rows)]

    @classmethod
    def _options_page_rects(cls):
        """Clickable page tabs left and right of the options title."""
        return tuple(pygame.Rect(292 + index * 590, 70, 106, 36)
                     for index in range(len(cls._OPTION_PAGES)))

    def _option_rows(self) -> tuple:
        page = self.options_page if 0 <= self.options_page < len(self._OPTION_PAGES) else 0
        return self._OPTION_PAGES[page]

    def _set_options_page(self, page: int) -> None:
        self.options_page = page % len(self._OPTION_PAGES)
        self.options_sel = 0

    def local_side_locked(self) -> bool:
        """The uConsole's side is chosen outside a mission only."""
        return not self.in_menu

    def _toggle_local_side(self) -> None:
        if not self.local_side_locked():
            uboot_local.toggle_side(self)

    @localized
    def draw_options_overlay(self) -> None:
        # Panel/row geometry is sized so the footer hint always starts below
        # the last row with margin, never overlapping it (was previously a
        # fixed y=612 footer colliding with row 9's box at y=620-662).
        rect = pygame.Rect(260, 40, 760, 660)
        pygame.draw.rect(self.screen, config.COLOR_OVERLAY_BG, rect)
        pygame.draw.rect(self.screen, config.COLOR_WARN, rect, 2)
        layout.blit_line(self.screen, "option.title", (292, 64, 696, 48),
                         config.COLOR_WARN, size=32, align="center")
        for page, tab in enumerate(self._options_page_rects()):
            active = page == self.options_page
            pygame.draw.rect(self.screen, config.COLOR_WARN if active
                             else config.COLOR_TEXT_DIM, tab, 1)
            layout.blit_line(self.screen, message("option.page", page=page + 1,
                                                  pages=len(self._OPTION_PAGES)),
                             tab.inflate(-8, -4), config.COLOR_WARN if active
                             else config.COLOR_TEXT_DIM, size=18, align="center")
        if self._option_rows() is self._OPTION_ROWS_SETUP:
            self._draw_options_setup_page()
            return
        values = (
            self.tr("option.language") + ": " + self.tr("option.language." + self.preferences.language),
            self.tr("option.fullscreen") + ": " + self.tr("common.on" if self.preferences.fullscreen else "common.off"),
            self.tr("option.audio") + ": " + self.tr("common.on" if self.audio.available else "common.off"),
            self.tr("option.large_text") + ": " + self.tr("common.on" if self.preferences.large_text else "common.off"),
            self.tr("option.tooltips") + ": "
            + self.tr("common.on" if self.tooltips_enabled else "common.off"),
            self.tr("option.simlog") + ": "
            + self.tr("common.on" if self.preferences.simlog else "common.off"),
            self.tr("option.night_mode") + ": "
            + self.tr("common.on" if self.preferences.night_mode else "common.off"),
            self.tr("option.high_contrast") + ": "
            + self.tr("common.on" if self.preferences.high_contrast else "common.off"),
            self.tr("option.frame_rate", fps=self.frame_rate()),
            self.tr("option.bottom_panel") + ": "
            + self.tr("option.bottom_panel." + self.bottom_panel_mode()),
            self.tr("option.operator_assist") + ": "
            + self.tr("option.operator_assist." + ("training" if self.operator_assist()
                                                   else "off")),
            self.tr("option.live_traffic"),
            self.tr("commander.local.option"),
        )
        for index, (value, row) in enumerate(zip(values, self._options_row_rects())):
            color = config.COLOR_TEXT if index == self.options_sel else config.COLOR_TEXT_DIM
            prefix = "> " if index == self.options_sel else "  "
            layout.blit_line(self.screen, raw_text(prefix + value), row, color, size=20)
        layout.blit_block(self.screen,
                          "commander.local.options_hint",
                          292, 650, 696, 46, config.COLOR_TEXT_DIM, size=18,
                          align="center")

    def _draw_options_setup_page(self) -> None:
        row = self._options_row_rects()[0]
        locked = self.local_side_locked()
        value = (self.tr("option.local_side") + ": "
                 + self.tr("option.local_side." + self.local_side))
        selected = self.options_sel == 0
        color = (config.COLOR_TEXT_DIM if locked or not selected else config.COLOR_TEXT)
        layout.blit_line(self.screen, raw_text(("> " if selected else "  ") + value),
                         row, color, size=20)
        layout.blit_block(self.screen, "option.local_side.help",
                          row.x + 24, row.bottom + 10, row.w - 24, 150,
                          config.COLOR_TEXT_DIM, size=18)
        if locked:
            layout.blit_block(self.screen, "option.local_side.locked",
                              row.x + 24, row.bottom + 170, row.w - 24, 50,
                              config.COLOR_WARN, size=18)
        # Display: anti-aliased chart lines (row 8 leaves the side's help room).
        row = self._options_row_rects()[self._SETUP_ROW_INDICES[1]]
        selected = self.options_sel == 1
        value = (self.tr("option.aa_lines") + ": "
                 + self.tr("common.on" if self.preferences.aa_lines else "common.off"))
        layout.blit_line(self.screen, raw_text(("> " if selected else "  ") + value), row,
                         config.COLOR_TEXT if selected else config.COLOR_TEXT_DIM, size=20)
        layout.blit_block(self.screen, "option.aa_lines.help",
                          row.x + 24, row.bottom + 10, row.w - 24, 80,
                          config.COLOR_TEXT_DIM, size=18)
        layout.blit_block(self.screen,
                          "commander.local.options_hint",
                          292, 650, 696, 46, config.COLOR_TEXT_DIM, size=18,
                          align="center")

    @staticmethod
    def _live_traffic_row_rects():
        return tuple(pygame.Rect(292, 150 + index * 84, 696, 44) for index in range(5))

    @staticmethod
    def _mask_credential(value: str) -> str:
        value = (value or "").strip()
        if not value:
            return "-"
        return f"...{value[-4:]}" if len(value) > 4 else "*" * len(value)

    @localized
    def draw_live_traffic_overlay(self) -> None:
        rect = pygame.Rect(260, 40, 760, 660)
        pygame.draw.rect(self.screen, config.COLOR_OVERLAY_BG, rect)
        pygame.draw.rect(self.screen, config.COLOR_WARN, rect, 2)
        layout.blit_line(self.screen, "live_traffic.title", (292, 64, 696, 48),
                         config.COLOR_WARN, size=32, align="center")
        online = self.connectivity.online
        status_key = ("live_traffic.online" if online
                     else "live_traffic.offline" if online is False
                     else "live_traffic.checking")
        layout.blit_line(self.screen, status_key, (292, 108, 696, 28),
                         config.COLOR_TEXT_DIM, size=16, align="center")
        rows = self._live_traffic_row_rects()
        names = self._LIVE_TRAFFIC_ROWS
        toggle_labels = (
            self.tr("live_traffic.ais_toggle") + ": "
            + self.tr("common.on" if self.preferences.live_ais_enabled else "common.off"),
            self.tr("live_traffic.adsb_toggle") + ": "
            + self.tr("common.on" if self.preferences.live_adsb_enabled else "common.off"),
        )
        for index in range(2):
            color = (config.COLOR_TEXT if index == self.live_traffic_sel
                     else config.COLOR_TEXT_DIM)
            if not getattr(self.preferences, names[index]) \
                    and not self._live_traffic_can_enable(names[index]):
                color = config.COLOR_TEXT_DIM
            prefix = "> " if index == self.live_traffic_sel else "  "
            layout.blit_line(self.screen, raw_text(prefix + toggle_labels[index]),
                             rows[index], color, size=20)
        for index, key in ((2, "aisstream_api_key"), (3, "opensky_credentials")):
            color = config.COLOR_TEXT if index == self.live_traffic_sel else config.COLOR_TEXT_DIM
            prefix = "> " if index == self.live_traffic_sel else "  "
            label = self.tr("live_traffic.aisstream_key" if key == "aisstream_api_key"
                            else "live_traffic.opensky_key")
            row = rows[index]
            layout.blit_line(self.screen, raw_text(prefix + label),
                             (row.x, row.y, row.w, 22), color, size=18)
            field_rect = pygame.Rect(row.x, row.y + 24, row.w, 30)
            if self.live_traffic_field is not None and self.live_traffic_field_name == key:
                self.live_traffic_field.draw(self.screen, field_rect, focused=True)
            else:
                layout.blit_line(self.screen,
                                 raw_text(self._mask_credential(getattr(self.preferences, key))),
                                 field_rect, config.COLOR_TEXT_DIM, size=16)
        test_row = rows[4]
        color = config.COLOR_TEXT if self.live_traffic_sel == 4 else config.COLOR_TEXT_DIM
        prefix = "> " if self.live_traffic_sel == 4 else "  "
        layout.blit_line(self.screen, raw_text(prefix + self.tr("live_traffic.test_action")),
                         (test_row.x, test_row.y, test_row.w, 22), color, size=18)
        status_line = self.tr("live_traffic.test_result",
                              ais=self._live_traffic_test_label("ais"),
                              adsb=self._live_traffic_test_label("adsb"))
        layout.blit_line(self.screen, raw_text(status_line),
                         (test_row.x, test_row.y + 24, test_row.w, 24),
                         config.COLOR_TEXT_DIM, size=16)
        layout.blit_block(self.screen,
                          "live_traffic.hint",
                          292, 636, 696, 58, config.COLOR_TEXT_DIM, size=16,
                          align="center")

    def _live_traffic_test_label(self, side: str) -> str:
        status, reason = self.live_traffic_test_result.get(side, ("idle", None))
        if status == "running":
            return self.tr("live_traffic.test_running")
        if status == "no_key":
            return self.tr("live_traffic.test_no_key")
        if status == "ok":
            return self.tr("live_traffic.test_ok")
        if status == "error":
            return self.tr("live_traffic.test_error", reason=(reason or "?")[:80])
        return self.tr("live_traffic.test_idle")

    @localized
    def draw_quit_overlay(self) -> None:
        """Require an explicit confirmation before leaving a live mission."""
        s = self.screen
        dim = pygame.Surface((config.SCREEN_W, config.SCREEN_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 155))
        s.blit(dim, (0, 0))
        choices = (("quit.menu", "common.exit") if self.in_menu else
                   ("quit.game", "quit.save", "quit.main_menu", "quit.no_save"))
        rect = pygame.Rect(260, 185 - 20 * (len(choices) - 3),
                           760, 330 + 40 * (len(choices) - 3))
        pygame.draw.rect(s, config.COLOR_PANEL_BG, rect)
        pygame.draw.rect(s, config.COLOR_WARN, rect, 2)
        layout.blit_line(s, "quit.title", (rect.x + 20, rect.y + 22,
                         rect.w - 40, 36), config.COLOR_WARN, size=28)
        layout.blit_line(s, "quit.warning",
                         (rect.x + 20, rect.y + 74, rect.w - 40, 26),
                         config.COLOR_TEXT, size=16)
        for index, label in enumerate(choices):
            selected = index == self.quit_selection
            layout.blit_line(s, message("menu.choice",
                                        marker="> " if selected else "  ",
                                        label=self.tr(label)),
                             (rect.x + 20, rect.y + 124 + index * 40, rect.w - 40, 32),
                             config.COLOR_WARN if selected else config.COLOR_TEXT,
                             size=22)
        layout.blit_line(s, "control.quit_hint",
                         (rect.x + 20, rect.bottom - 44, rect.w - 40, 28),
                         config.COLOR_TEXT_DIM, size=18)

    # --- Main loop ---

    def _perf_debug_log(self, wall_dt: float) -> None:
        """Optional 1 Hz diagnostics line, enabled via U_JAGD_PERF_DEBUG=1.

        Appends bounded per-frame-average phase timings (physics substeps,
        audio publish, Remote Crew pump, draw/compose) to perf_debug.log
        inside the save directory, for on-device (uConsole) CPU diagnosis.
        Purely measures wall time already spent in existing calls; never
        alters simulation timing, input, or rendering. No-op unless enabled.
        """
        if not self._perf_debug_enabled:
            return
        try:
            wall_dt = float(wall_dt)
        except (TypeError, ValueError, OverflowError):
            return
        if not math.isfinite(wall_dt) or wall_dt <= 0.0:
            return
        self._perf_frames += 1
        self._perf_frame_max_s = max(self._perf_frame_max_s, wall_dt)
        self._perf_debug_due += wall_dt
        if self._perf_debug_due < 1.0:
            return
        self._perf_debug_due %= 1.0
        frames = self._perf_frames
        line = ("t={t:.1f} fps={fps} substeps_avg={sub:.2f} sim_ms={sim:.2f} "
                "audio_ms={audio:.2f} commander_ms={cmd:.2f} "
                "commander_max_ms={cmdmax:.1f} events_ms={events:.2f} "
                "traffic_ms={traffic:.2f} "
                "draw_ms={draw:.2f} frame_max_ms={fmax:.1f} "
                "sim_lag_ms={lag:.1f} sim_dropped_ms={drop:.1f}\n").format(
            t=time.monotonic(), fps=frames, sub=self._perf_substeps / frames,
            fmax=1000 * self._perf_frame_max_s, lag=1000 * self._sim_debt_s,
            drop=1000 * self._sim_dropped_s,
            sim=1000 * self._perf_sim_s / frames,
            audio=1000 * self._perf_audio_s / frames,
            cmd=1000 * self._perf_commander_s / frames,
            cmdmax=1000 * self._perf_commander_max_s,
            events=1000 * self._perf_events_s / frames,
            traffic=1000 * self._perf_traffic_s / frames,
            draw=1000 * self._perf_draw_s / frames)
        append_bounded_log(config.SAVE_DIR, "perf_debug.log", line,
                           config.PERF_DEBUG_LOG_MAX_BYTES)
        self._perf_frames = 0
        self._perf_sim_s = 0.0
        self._perf_substeps = 0
        self._perf_audio_s = 0.0
        self._perf_commander_s = 0.0
        self._perf_commander_max_s = 0.0
        self._perf_events_s = 0.0
        self._perf_traffic_s = 0.0
        self._perf_draw_s = 0.0
        self._perf_frame_max_s = 0.0

    def _frame_dt(self, wall_dt: float) -> float:
        """Simulation seconds for this frame from wall time and bounded debt.

        A frame never advances more than SIM_FRAME_DT_MAX, but the remainder of
        a slow frame is caught up over the next frames, so simulation time (and
        the sonar audio produced in it) keeps pace with wall-clock playback.
        Debt above SIM_CATCHUP_MAX_S is dropped. After a pause, menu, overlay,
        load or world reset the first frame is only clamped, never caught up.
        """
        try:
            wall_dt = float(wall_dt)
        except (TypeError, ValueError, OverflowError):
            wall_dt = 0.0
        if not math.isfinite(wall_dt) or wall_dt < 0.0:
            wall_dt = 0.0
        if self._frame_clock_reset:
            self._frame_clock_reset = False
            self._sim_debt_s = 0.0
            return min(wall_dt, config.SIM_FRAME_DT_MAX)
        debt = self._sim_debt_s + wall_dt
        if debt > config.SIM_CATCHUP_MAX_S:
            self._sim_dropped_s += debt - config.SIM_CATCHUP_MAX_S
            debt = config.SIM_CATCHUP_MAX_S
        dt = min(debt, config.SIM_FRAME_DT_MAX)
        self._sim_debt_s = debt - dt
        return dt

    def frame_rate(self) -> int:
        """Active frame-rate cap from the saved preference."""
        value = getattr(self.preferences, "frame_rate", config.FPS_DEFAULT)
        return value if value in config.FPS_CHOICES else config.FPS_DEFAULT

    def run(self) -> None:
        try:
            while self.running:
                if self.auto_quit is not None:
                    self.auto_quit -= 1
                    if self.auto_quit <= 0:
                        self.running = False
                wall_dt = self.clock.tick(self.frame_rate()) / 1000.0
                dt = self._frame_dt(wall_dt)
                self._t += dt
                events_started = (time.perf_counter()
                                  if self._perf_debug_enabled else None)
                for e in pygame.event.get():
                    if not self.web_mode:
                        self.handle_event(e)
                        if e.type in _ECO_REFRESH_EVENTS:
                            self._eco_drawn_at = float("-inf")
                if events_started is not None:
                    self._perf_events_s += time.perf_counter() - events_started
                commander_started = (time.perf_counter()
                                     if self._perf_debug_enabled else None)
                self.commander.pump(self)
                if commander_started is not None:
                    now = time.perf_counter()
                    self._perf_commander_s += now - commander_started
                    self._perf_commander_max_s = max(
                        self._perf_commander_max_s, now - commander_started)
                    commander_started = now
                self.live_traffic.pump(self)
                if commander_started is not None:
                    self._perf_traffic_s += time.perf_counter() - commander_started
                self.update(dt, audio_dt=wall_dt)
                self._perf_debug_log(wall_dt)
                if self.web_mode:
                    continue
                if self._skip_eco_frame():
                    continue
                draw_started = time.perf_counter() if self._perf_debug_enabled else None
                self.draw()
                self.compose_frame()
                if draw_started is not None:
                    self._perf_draw_s += time.perf_counter() - draw_started
        finally:
            try:
                self.commander.stop()
            finally:
                try:
                    self.connectivity.stop()
                    self.live_traffic.stop()
                finally:
                    self.audio.shutdown()
                    pygame.quit()

    def _apply_text_size(self) -> None:
        layout.configure_for(self)
        self.font = layout.font(18)
        self.font_big = layout.font(28, bold=True)
        # Menus get a larger baseline than in-game HUD text: more free
        # space per screen, and no risk to the already-tuned station views
        # that also read `self.font`/`self.font_big`.
        self.menu_font = layout.font(21)
        self.menu_font_big = layout.font(34, bold=True)

    def toggle_fullscreen(self, persist: bool = True) -> None:
        """Vollbild: (0,0)+FULLSCREEN = native Desktop-Größe (deckt Taskleiste
        ab, keine schwarzen Balken). Zurück = 1280x720-Fenster."""
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            self.display = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.display = pygame.display.set_mode(
                (config.SCREEN_W, config.SCREEN_H), pygame.RESIZABLE)
        if persist:
            from dataclasses import replace
            self.preferences = replace(self.preferences, fullscreen=self.fullscreen)
            try:
                save_preferences(self.preferences)
            except OSError:
                pass
        self.flash(message("event.fullscreen_on" if self.fullscreen
                           else "event.fullscreen_off"), 2.0)

    def _set_preference(self, name: str, value) -> None:
        from dataclasses import replace
        self.preferences = replace(self.preferences, **{name: value})
        if name == "language":
            self.translator = Translator(value)
            self.tr = self.translator.t
            self.pinned_tooltip = None
            self._tooltip_anchor = None
            pygame.display.set_caption(self.tr("app.title"))
            if self.editor is not None:
                self.editor.tr = self.tr
            self.flash(message("status.language_changed",
                               language=self.tr("option.language." + value)), 2.0)
        elif name == "fullscreen" and bool(value) != self.fullscreen:
            self.toggle_fullscreen(persist=False)
        elif name == "audio":
            self.audio.shutdown()
            self.audio = AudioEngine(sample_rate=config.AUDIO_SAMPLE_RATE,
                                     enabled=bool(value))
            self._audio_timer = 0.0
            self._sonar_audio_sequence = -1
        elif name in ("large_text", "high_contrast", "aa_lines"):
            self._apply_text_size()
        elif name == "tooltips":
            self.tooltips_enabled = bool(value)
            self.pinned_tooltip = None
            self._tooltip_anchor = None
        try:
            save_preferences(self.preferences)
        except OSError:
            self.flash(message("status.preferences_error"), 3.0)

    def _reset_map_view(self) -> None:
        """Standard-Karte: Detail-Zoom, Kamera folgt der Fregatte."""
        self.map_view.set_rect(config.MAP_RECT)
        self.map_view.scale = config.MAP_ZOOM_DEFAULT_PX_PER_NM
        self.map_view.cx = self.ship.x
        self.map_view.cy = self.ship.y
        self.map_view.clamp_center()
        self.map_follow = True
        self._configure_opz_map_view()
        self.opz_map_view.scale = min(self.opz_map_view.rect[2],
                                      self.opz_map_view.rect[3]) / (
            2.0 * config.OPZ_MAP_DEFAULT_RADIUS_NM)
        self.opz_map_view.cx = self.ship.x
        self.opz_map_view.cy = self.ship.y
        self.opz_map_view.clamp_center()
        self.opz_map_follow = True

    def _configure_opz_map_view(self, chart=None) -> None:
        chart = pygame.Rect(chart or opz_ppi_rect(config.OPZ_STATION_RECT))
        self.opz_map_view.world_size = self.world.size_nm
        self.opz_map_view.set_rect(tuple(chart))
        self.opz_map_view.min_scale = min(chart.w, chart.h) / self.world.size_nm
        self.opz_map_view.max_scale = max(
            self.opz_map_view.min_scale, min(chart.w, chart.h) / (
                2.0 * config.OPZ_MAP_MAX_ZOOM_RADIUS_NM))
        self.opz_map_view.scale = config.clamp(
            self.opz_map_view.scale, self.opz_map_view.min_scale,
            self.opz_map_view.max_scale)
