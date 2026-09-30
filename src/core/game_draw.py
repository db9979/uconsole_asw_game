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
from src.core.launch_signal import game_visible
from src.core.i18n import (Translator, display_value, localized, localize,
                           message, raw_text, translation_scope)
from src.core.preferences import save_preferences
from src.core.help import get_global_help, get_help, get_sop, get_uboot_help
from src.core import manual
from src.core.station import Station
from src.core import pointer_input, station_alarms, uboot_local
from src.nations.nations import reference_summary
from src.ui import layout, pointer
from src.ui import observations
from src.ui import overlay_style
from src.ui.red_light import RedLight, draw_lamp
from src.ui.map_view import draw_map_view
from src.ui.splash_view import (draw_logo, draw_menu_backdrop, draw_menu_panel,
                                draw_splash)
from src.ui.support import draw_support_corner
from src.core.game_bugreport import BUG_REPORT_ENTRY, MAIN_MENU_LABELS
from src.core.game_welcome import WELCOME_SCREEN
from src.ui.sonar_view import draw_sonar_view
from src.ui.weather_station import draw_weather_station
from src.ui import uboot_view
from src.ui.stations.common import _shortcut_footer as shortcut_footer
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

# Width of the soft ends of the scrolling ticker line: a few letters fade
# out instead of one glyph being cut in half.
TICKER_FADE_PX = 64
from src.ui.stations_view import opz_ppi_rect
from src.ui.mission_editor import MissionEditor
from src.ui.simlog_view import draw_simlog_view
from src.ui.weapons_view import draw_weapons_overlay, draw_weapons_panel
# Shared display/help constants and helpers (re-exported for tests/tools).
from src.core.game_shared import HELP_MANUAL_PAGE, HELP_PAGE_COUNT, letterbox_layout
# Names tests and tools import from ``src.core.game`` (kept as re-exports).
from src.core.game_events import _ECO_REFRESH_EVENTS


FRIGATE_TAB_W = 84


def frigate_station_tab_rects() -> list:
    """Top-bar tab rectangles of the frigate's nine stations."""
    return [pygame.Rect(4 + index * (FRIGATE_TAB_W + 3), 3, FRIGATE_TAB_W,
                        config.TOP_BAR_H - 6) for index in range(len(list(Station)))]


# The end panel's keys (frigate), drawn as a clickable legend.
END_KEYS = (("D", "end.key.debrief"), ("R", "end.key.restart"),
            ("M", "end.key.menu"), ("Esc", "end.key.exit"))


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

    def _click_menu_row(self, select, key=pygame.K_RETURN) -> None:
        """A click on a menu row: select it, then press ``key`` (Enter)."""
        select()
        if key is not None:
            self.handle_event(pointer_input.key_event(key))

    @localized
    def draw_menu(self) -> None:
        """W4: Szenario -> (Level bei s4) -> Briefing -> Start."""
        s = self.screen
        cx = config.SCREEN_W // 2
        # The start screen's night hunt, dimmed, behind every menu page.
        draw_menu_backdrop(s, self._t)

        def center(text: str, y: int, font=None, color=config.COLOR_TEXT, keys=None) -> None:
            f = font or self.menu_font
            text = localize(text)
            surf = f.render(text, True, color)
            s.blit(surf, surf.get_rect(center=(cx, y)))
            if keys:
                # Each "a | b" part of a key hint is clickable.
                pointer.add_text_keys(text, f, cx, y, keys)

        def row(y: int, height: int, select, width: int = 720) -> None:
            """A clickable menu row: select it and press Enter."""
            pointer.add_action((cx - width // 2, y - height // 2, width, height),
                               lambda _pos: self._click_menu_row(select))

        draw_logo(s, cx, 34)

        if self.main_menu:
            entries = self.main_menu_entries()
            step = 400 // len(entries)
            draw_menu_panel(s, (cx - 260, 148, 520, 412),
                            (cx - 250, 157 + self.main_menu_sel * step, 500, step - 4))
            for i, entry in enumerate(entries):
                row(157 + step // 2 - 2 + i * step, step - 2,
                    lambda i=i: setattr(self, "main_menu_sel", i), 500)
                marker = "> " if i == self.main_menu_sel else "  "
                color = config.COLOR_TEXT if i == self.main_menu_sel else config.COLOR_TEXT_DIM
                center(message("menu.choice", marker=marker,
                               label=self.tr(MAIN_MENU_LABELS[entry]).upper()),
                       157 + step // 2 - 2 + i * step, color=color)
            if self.bug_report_offer:
                center(self.tr("menu.bug_report.offer"), 584, color=config.COLOR_WARN)
            # Support link: main menu page only, never over a mission.
            draw_support_corner(s, config.SCREEN_W - 24, 600,
                                config.COLOR_TEXT, config.COLOR_TEXT_DIM)
            if not self.welcome_active:
                self.draw_update_notice(s, splash=False)
        elif self.menu_screen == WELCOME_SCREEN:
            self._draw_welcome_page()
        elif self.menu_screen == BUG_REPORT_ENTRY:
            self._draw_bug_report_page(center)
        elif self.lobby_active:
            self._draw_lobby_page()
        elif self.menu_screen == "logbook":
            self._draw_logbook_page(center)
        elif self.menu_screen == "training":
            self._draw_training_menu(center)
        elif self.menu_screen == "campaign":
            self._draw_campaign_menu(center)
        elif self.menu_screen == "side":
            center(self.tr("menu.choose_side"), 170, color=config.COLOR_TEXT_DIM)
            for i, side in enumerate(("frigate", "uboot")):
                row(262 + i * 90, 80, lambda i=i: setattr(self, "menu_sel", i), 860)
                selected = i == self.menu_sel
                center(message("menu.choice", marker="► " if selected else "  ",
                               label=self.tr(f"menu.side.{side}")),
                       250 + i * 90, self.menu_font_big if selected else None,
                       config.COLOR_TEXT if selected else config.COLOR_TEXT_DIM)
                layout.blit_line(s, f"menu.side.{side}.note", (cx - 420, 285 + i * 90, 840, 26),
                                 config.COLOR_TEXT_DIM, size=18, align="center")
            center(self.tr("menu.side_hint"), 470, color=config.COLOR_TEXT_DIM,
                   keys=(None, "Enter", "Esc"))
        elif self.menu_screen == "scenario":
            center(self.tr("menu.choose_scenario"),
                   150, color=config.COLOR_TEXT_DIM)
            scenario_names = config.SCENARIO_NAMES
            for i, key in enumerate(config.SCENARIO_ORDER):
                row(240 + i * 40, 38, lambda i=i: setattr(self, "menu_sel", i))
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
                   150, color=config.COLOR_TEXT_DIM, keys=("Enter", "Esc"),
                   )
            row_h = 26
            for i in range(len(config.DIFFICULTY_FIELD_ORDER) + 1):
                # Left part lowers, right part raises, the middle selects.
                y = 190 + i * row_h
                for part, key in ((0, pygame.K_LEFT), (1, None), (2, pygame.K_RIGHT)):
                    pointer.add_action(
                        (cx - 360 + part * 240, y - row_h // 2, 240, row_h),
                        lambda _pos, i=i, key=key: self._click_menu_row(
                            lambda: setattr(self, "menu_sel", i), key))
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
            scenario_key = config.SCENARIO_NAMES[self.scenario_key]
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
                   color=config.COLOR_TEXT_DIM, keys=("Enter", "Esc"))
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
               config.SCREEN_H - 68, color=config.COLOR_OK, keys=("W", "R"))
        center(self.tr("menu.seed_fullscreen", seed=self.seed,
                       action=self.tr("menu.windowed" if self.fullscreen
                                      else "menu.fullscreen")),
               config.SCREEN_H - 40, color=config.COLOR_TEXT_DIM, keys=(None, "F"))

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

    def _splash_backdrop_active(self) -> bool:
        """A modal overlay or the mission's end panel replaces the station."""
        admission = getattr(getattr(self.commander, "admission", None), "request", None)
        if self.commander_open and admission is not None:
            return False
        return bool(self.administration_open
                    or (self.game_over and not self.debrief_open))

    def red_light_mode(self) -> str:
        """The red light's option: "off", "auto" (night, alarm) or "on"."""
        if self.preferences.night_mode:
            return "on"
        return "auto" if self.preferences.red_light_auto else "off"

    def _mission_shown(self) -> bool:
        return not (self.in_menu or self.splash_active or self.editor is not None
                    or self.simlog_view_open or self.game_over)

    def station_alarm_levels(self) -> dict:
        """The station lamps of the side shown, refreshed four times a
        second of wall time (display only)."""
        if not self._mission_shown():
            self._alarm_cache = (None, {})
            return {}
        stamp, levels = getattr(self, "_alarm_cache", (None, {}))
        if stamp is None or not 0.0 <= self._t - stamp < 0.25:
            levels = station_alarms.for_side(self)
            self._alarm_cache = (self._t, levels)
        return levels

    def _draw_red_light(self, s) -> None:
        mode = self.red_light_mode()
        if mode == "on":
            target = 1.0
        elif mode == "auto" and self._mission_shown():
            target = station_alarms.red_light_target(self, self.station_alarm_levels())
        else:
            target = 0.0
        light = getattr(self, "_red_light", None)
        if light is None:
            light = self._red_light = RedLight()
        if light.step(target, self._t) > 0.0:
            s.blit(light.overlay(s.get_size()), (0, 0), special_flags=pygame.BLEND_MULT)

    def _draw(self) -> None:
        # Mouse targets are rebuilt with every frame (src/ui/pointer.py).
        pointer.reset()
        self._apply_text_size()
        s = self.screen
        eco = self._eco_display_active()
        s.fill(config.COLOR_BG)
        if self.splash_active:
            draw_splash(s, self._t - self.splash_started_at, self.tr)
            self.draw_update_notice(s, splash=True)
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
            with pointer.layer("menu"):
                self.draw_menu()
        elif self._splash_backdrop_active():
            # Modal overlays and the mission end sit on the start screen's
            # night hunt; the station behind is not drawn (saves uConsole CPU).
            overlay_style.backdrop(s, self._t)
            if self.game_over and not self.debrief_open:
                if self.local_side == "uboot":
                    uboot_view.draw_end_panel(self, self.opfor)
                else:
                    self.draw_end_panel()
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
                self.draw_training_hint()
                if self.game_over and self.debrief_open:
                    from src.ui.debrief_view import draw_debrief
                    draw_debrief(self)
                elif self.game_over:
                    self.draw_end_panel()
            finally:
                config.STATION_RECT = previous_rect
        with pointer.layer("overlay"):
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
        self._draw_red_light(s)

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
        # A keypad under the entry: every key is a click (full mouse control).
        keys = ([(raw_text(str(digit)), pygame.K_0 + digit) for digit in range(10)]
                + [(raw_text("."), pygame.K_PERIOD), (raw_text("⌫"), pygame.K_BACKSPACE),
                   ("help.key.enter", pygame.K_RETURN), (raw_text("Esc"), pygame.K_ESCAPE)])
        narrow = (rect.w - 2 * 96) // (len(keys) - 2)
        with pointer.layer("input"):
            x = rect.x
            for index, (label, key) in enumerate(keys):
                width = 96 if index >= len(keys) - 2 else narrow
                cell = pygame.Rect(x, rect.bottom + 4, width - 4, 34)
                x += width
                pygame.draw.rect(self.screen, config.COLOR_OVERLAY_BG, cell)
                pygame.draw.rect(self.screen, config.COLOR_GRID, cell, 1)
                layout.blit_line(self.screen, label, cell.inflate(-4, -6),
                                 config.COLOR_TEXT, size=16, align="center")
                pointer.add_key(cell, key)

    @localized
    def top_bar_scenario(self) -> str:
        """Mission title shown in the top status bar."""
        if self.custom_mission_definition is not None:
            return localize(self.mission_name_display())
        return self.tr("scenario." + config.SCENARIO_NAMES
                       [self.scenario_key] + ".title")

    def draw_top_bar(self) -> None:
        layout.configure_for(self)
        s = self.screen
        pygame.draw.rect(s, config.COLOR_PANEL_BG, (0, 0, config.SCREEN_W, config.TOP_BAR_H))
        pygame.draw.line(s, config.COLOR_SONAR_RING,
                         (0, config.TOP_BAR_H - 1),
                         (config.SCREEN_W, config.TOP_BAR_H - 1), 1)
        # The nine stations as tabs (key number and short name), like the
        # submarine's; a click on a tab presses its number key.
        tabs = frigate_station_tab_rects()
        alarms = self.station_alarm_levels()
        for index, (station, rect) in enumerate(zip(list(Station), tabs)):
            active = station is self.station
            if active:
                pygame.draw.rect(s, config.COLOR_TAB_ACTIVE, rect)
                pygame.draw.line(s, config.COLOR_SONAR_RING, rect.bottomleft,
                                 (rect.right - 1, rect.bottom), 2)
            if index:
                pygame.draw.line(s, config.COLOR_GRID, (rect.x - 2, rect.y + 4),
                                 (rect.x - 2, rect.bottom - 4), 1)
            label = message("top.tab", number=index + 1,
                            name=message(f"top.tab.{station.name.lower()}"))
            layout.blit_line(s, label, rect, config.COLOR_TEXT if active
                             else config.COLOR_TEXT_DIM, size=14, align="center")
            draw_lamp(s, rect, alarms.get(station.name.lower()), self._t)
            pointer.add_key(rect, pygame.K_1 + index)
        self._top_status_right = tabs[-1].right
        if self.msg and self._t < self.msg_until:
            return      # the flash banner stands in the status line's place
        txt = self.tr("top.status_short", scenario=self.top_bar_scenario(),
                      time=self.world.format_time(), speed=f"{self.ship.speed:.1f}",
                      course=f"{self.ship.course % 360:03.0f}")
        left = tabs[-1].right + 12
        layout.blit_line(s, txt, (left, 4, config.SCREEN_W - left - 10,
                                  config.TOP_BAR_H - 8),
                         config.COLOR_TEXT, size=16, align="right")

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

        def strip_text(value, area, color, right=False):
            # Centred on the strip, so large text keeps its descenders on screen.
            image = face.render(value, True, color)
            area = pygame.Rect(area.x, rect.y, area.w, rect.h)
            x = area.right - image.get_width() if right else area.x
            ink = image.get_bounding_rect()
            # The visible glyphs, not the font line, are centred on the strip.
            top = area.y + max(0, (area.h - ink.h) // 2) - ink.y
            rendered = image.get_rect(topleft=(x, top))
            with layout.clip_to(s, area):
                layout.record_text(value, rendered, area, image)
                s.blit(image, rendered)

        strip_text(telemetry, tele_rect, colors[level], right=True)
        hint = localize(hint_key) if hint_key else ""
        hint_w = face.size(hint)[0] + 12 if hint else 0
        if hint:
            strip_text(hint, pygame.Rect(rect.x + 6, rect.y, hint_w, rect.h),
                       config.COLOR_TEXT_DIM)
        feed_rect = pygame.Rect(rect.x + 6 + hint_w, rect.y + 2,
                                tele_rect.x - 12 - (rect.x + 6 + hint_w), rect.h - 2)
        latest = self.feed.recent(1) if entries is None else list(entries)[-1:]
        if not latest or feed_rect.w <= 20:
            return
        entry = latest[0]
        text = f"[{entry.stamp}] {entry.tag()} {localize(entry.text)}"
        width = face.size(text)[0]
        feed_rect = pygame.Rect(feed_rect.x, rect.y, feed_rect.w, rect.h)
        if width <= feed_rect.w:
            strip_text(text, feed_rect, entry.color())
            return
        surface = face.render(text, True, entry.color())
        text_y = feed_rect.y + (feed_rect.h - surface.get_height()) // 2
        with layout.clip_to(s, feed_rect):
            # Marquee instead of an ellipsis: the full line stays readable.
            gap = 60
            offset = int(self._t * config.TICKER_SCROLL_PX_S) % (width + gap)
            s.blit(surface, (feed_rect.x - offset, text_y))
            s.blit(surface, (feed_rect.x - offset + width + gap, text_y))
            # Soft ends: letters fade out instead of being cut in half.
            layout.fade_edges(s, feed_rect, config.COLOR_FEED_BG, TICKER_FADE_PX,
                              left=offset > 0)

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
        bw, bh = 1000, 620
        bx = (config.SCREEN_W - bw) // 2
        by = (config.SCREEN_H - bh) // 2
        overlay_style.panel(s, (bx, by, bw, bh))
        help_title = self.tr("help.title", station=display_value(
            "station", self.station.name, self.tr).upper())
        overlay_style.title(s, help_title, (bx + 18, by + 8, bw - 36, 40), size=30,
                            align="left")
        # Mouse: the title steps the category, the wheel scrolls.
        pointer.add_key((bx + 18, by + 8, bw - 36, 40), pygame.K_TAB)
        overlay_style.rule(s, bx + 18, by + 48, bw - 36)
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
        layout.blit_block(s, hint, x, by + bh - 62, w, 54, overlay_style.accent_color(),
                          size=16)

    @localized
    def draw_nations_overlay(self) -> None:
        s = self.screen
        bw, bh = 1100, 620
        bx = (config.SCREEN_W - bw) // 2
        by = (config.SCREEN_H - bh) // 2
        overlay_style.panel(s, (bx, by, bw, bh))
        overlay_style.title(s, "panel.nations", (bx + 18, by + 8, bw - 36, 38), size=30,
                            align="left")
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
            overlay_style.panel(s, (cx, cyy, cw, ch), accent=color)
            layout.blit_line(s, title, (cx + 12, cyy + 8, cw - 24, 36), color, size=24)
            layout.blit_block(s, body, cx + 12, cyy + 50, cw - 24, ch - 58,
                              color=config.COLOR_TEXT, size=18)
        layout.blit_line(s, "nations.close", (bx + bw - 160, by + bh - 30, 140, 24),
                         overlay_style.accent_color(), size=16, align="right")
        pointer.add_key((bx + bw - 160, by + bh - 30, 140, 24), pygame.K_n)

    @localized
    def draw_save_ui(self) -> None:
        s = self.screen
        mode = self.tr("common.save" if self.save_ui == "save" else "common.load").upper()
        bw, bh = 660, 380
        bx = (config.SCREEN_W - bw) // 2
        by = (config.SCREEN_H - bh) // 2
        overlay_style.panel(s, (bx, by, bw, bh))
        overlay_style.title(s, self.tr("save.title", mode=mode),
                            (bx + 18, by + 12, bw - 36, 38), size=26)
        overlay_style.rule(s, bx + 18, by + 54, bw - 36)
        ly = by + 70
        for slot in range(1, 6):
            info = self.save_info[slot - 1] if len(self.save_info) == 5 else "--"
            selected = slot == self.save_slot
            col = overlay_style.text_color(selected)
            if selected:
                overlay_style.highlight(s, (bx + 14, ly - 4, bw - 28, 36))
            layout.blit_line(s, message("save.slot", marker=">" if selected else " ",
                                         slot=slot, info=localize(info)),
                             (bx + 24, ly, bw - 48, 32), col, size=19)
            pointer.add_action((bx + 14, ly - 4, bw - 28, 36),
                               lambda _pos, slot=slot: self._click_save_slot(slot))
            ly += 42
        hint = "save.live"
        if self.save_confirm:
            hint = ("save.overwrite" if self.save_ui == "save"
                    else "save.replace")
        layout.blit_line(s, hint, (bx + 18, by + bh - 54, bw - 36, 34),
                         overlay_style.accent_color(), size=18, align="center")
        if hint == "save.live":
            pointer.add_text_keys(localize(hint), layout.font(18), bx + bw // 2,
                                  by + bh - 37, ("Esc", None))

    def _click_save_slot(self, slot: int) -> None:
        """A click on a slot picks it; a second click on it confirms."""
        if not (self.save_slot == slot and self.save_confirm):
            self.handle_event(pointer_input.key_event(pygame.K_1 + slot - 1))
        self.handle_event(pointer_input.key_event(pygame.K_RETURN))

    @localized
    def draw_end_panel(self) -> None:
        """M8: Endpanel mit Score-Bruchrechnung und Hinweisen."""
        s = self.screen
        w, h = 780, 340
        x = (config.SCREEN_W - w) // 2
        y = (config.SCREEN_H - h) // 2
        overlay_style.panel(s, (x, y, w, h))
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
        campaign_line = self.campaign_end_line()
        if campaign_line is not None:
            lines.append((campaign_line, config.COLOR_WARN, False))
        logbook_line = self.logbook_end_line()
        if logbook_line is not None:
            lines.append((logbook_line, config.COLOR_OK, False))
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
        for index, (text, c, big) in enumerate(lines):
            if not text:
                ly += 16
                continue
            size = 26 if big else 20
            height = 36 if big else 26
            if text == "end.restart":
                # The keys as a clickable legend, like the station footers.
                with pointer.layer("end"):
                    shortcut_footer(s, (x + 16, ly + 14, w - 32, 22), END_KEYS)
                ly += 50
                continue
            if index == 0:
                # The result line glows like the start screen's title.
                overlay_style.title(s, text, (x + 16, ly, w - 32, height), size=size,
                                    color=c)
            else:
                layout.blit_line(s, text, (x + 16, ly, w - 32, height), c,
                                 size=size, align="center")
            ly += 42 if big else 30

    @classmethod
    def _options_row_rects(cls):
        return tuple(pygame.Rect(292, 118 + index * 40, 696, 36)
                     for index in range(max(len(page) for page in cls._OPTION_PAGES)))

    # Row rect index of each setup-page row (the side's help text sits between).
    _SETUP_ROW_INDICES = (0, 6, 10)

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
        overlay_style.panel(self.screen, rect)
        overlay_style.title(self.screen, "option.title", (400, 64, 480, 48), size=32)
        for page, tab in enumerate(self._options_page_rects()):
            active = page == self.options_page
            if active:
                overlay_style.highlight(self.screen, tab)
            pygame.draw.rect(self.screen, overlay_style.PANEL_RIM
                             if not overlay_style.high_contrast()
                             else config.COLOR_TEXT_DIM, tab, 1)
            layout.blit_line(self.screen, message("option.page", page=page + 1,
                                                  pages=len(self._OPTION_PAGES)),
                             tab.inflate(-8, -4), overlay_style.text_color(active),
                             size=18, align="center")
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
            + self.tr("option.red_light." + self.red_light_mode()),
            self.tr("option.high_contrast") + ": "
            + self.tr("common.on" if self.preferences.high_contrast else "common.off"),
            self.tr("option.frame_rate", fps=self.frame_rate()),
            self.tr("option.bottom_panel") + ": "
            + self.tr("option.bottom_panel." + self.bottom_panel_mode()),
            self._level_option_text(),
            self.tr("option.live_traffic"),
            self.tr("commander.local.option"),
        )
        for index, (value, row) in enumerate(zip(values, self._options_row_rects())):
            color = overlay_style.text_color(index == self.options_sel)
            if index == self.options_sel:
                overlay_style.highlight(self.screen, (row.x - 6, row.y - 5, row.w + 12, 34))
            prefix = "> " if index == self.options_sel else "  "
            layout.blit_line(self.screen, raw_text(prefix + value), row, color, size=20)
        layout.blit_block(self.screen,
                          "commander.local.options_hint",
                          292, 650, 696, 46, config.COLOR_TEXT_DIM, size=18,
                          align="center")

    def _level_option_text(self) -> str:
        """The realism level row; in a mission with another level it says
        that the choice applies from the next mission."""
        chosen = self._preferred_level()
        text = self.tr("option.level", level=self.tr("level." + chosen),
                       factor=round(config.LEVEL_SCORE_FACTOR[chosen] * 100))
        if not self.in_menu and not self.game_over and self.level != chosen:
            text = self.tr("option.level_next", level=self.tr("level." + chosen))
        return text

    def _draw_options_setup_page(self) -> None:
        row = self._options_row_rects()[0]
        locked = self.local_side_locked()
        value = (self.tr("option.local_side") + ": "
                 + self.tr("option.local_side." + self.local_side))
        selected = self.options_sel == 0
        if selected:
            overlay_style.highlight(self.screen, (row.x - 6, row.y - 5, row.w + 12, 34))
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
        # Display: anti-aliased chart lines (row 7 leaves the side's help room).
        row = self._options_row_rects()[self._SETUP_ROW_INDICES[1]]
        selected = self.options_sel == 1
        if selected:
            overlay_style.highlight(self.screen, (row.x - 6, row.y - 5, row.w + 12, 34))
        value = (self.tr("option.aa_lines") + ": "
                 + self.tr("common.on" if self.preferences.aa_lines else "common.off"))
        layout.blit_line(self.screen, raw_text(("> " if selected else "  ") + value), row,
                         config.COLOR_TEXT if selected else config.COLOR_TEXT_DIM, size=20)
        layout.blit_block(self.screen, "option.aa_lines.help",
                          row.x + 24, row.bottom + 10, row.w - 24, 80,
                          config.COLOR_TEXT_DIM, size=18)
        # Spoken crew reports; the help says whether espeak-ng was found.
        row = self._options_row_rects()[self._SETUP_ROW_INDICES[2]]
        selected = self.options_sel == 2
        if selected:
            overlay_style.highlight(self.screen, (row.x - 6, row.y - 5, row.w + 12, 34))
        value = (self.tr("option.speech") + ": "
                 + self.tr("common.on" if self.preferences.speech else "common.off"))
        layout.blit_line(self.screen, raw_text(("> " if selected else "  ") + value), row,
                         config.COLOR_TEXT if selected else config.COLOR_TEXT_DIM, size=20)
        layout.blit_block(self.screen, "option.speech.help" if self.speaker.available
                          else "option.speech.missing",
                          row.x + 24, row.bottom + 6, row.w - 24, 64,
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
        overlay_style.panel(self.screen, rect)
        overlay_style.title(self.screen, "live_traffic.title", (292, 64, 696, 48), size=32)
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
            if index == self.live_traffic_sel:
                overlay_style.highlight(self.screen, (rows[index].x - 6, rows[index].y - 5,
                                                      rows[index].w + 12, 34))
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
        choices = (("quit.menu", "common.exit") if self.in_menu else
                   ("quit.game", "quit.save", "quit.main_menu", "quit.no_save"))
        rect = pygame.Rect(260, 185 - 20 * (len(choices) - 3),
                           760, 330 + 40 * (len(choices) - 3))
        overlay_style.panel(s, rect)
        overlay_style.title(s, "quit.title", (rect.x + 20, rect.y + 20,
                            rect.w - 40, 38), size=30)
        layout.blit_line(s, "quit.warning",
                         (rect.x + 20, rect.y + 74, rect.w - 40, 26),
                         overlay_style.accent_color(), size=16, align="center")
        for index, label in enumerate(choices):
            selected = index == self.quit_selection
            if selected:
                overlay_style.highlight(s, (rect.x + 14, rect.y + 120 + index * 40,
                                            rect.w - 28, 36))
            layout.blit_line(s, message("menu.choice",
                                        marker="> " if selected else "  ",
                                        label=self.tr(label)),
                             (rect.x + 20, rect.y + 124 + index * 40, rect.w - 40, 32),
                             overlay_style.text_color(selected), size=22)
            pointer.add_action((rect.x + 14, rect.y + 120 + index * 40, rect.w - 28, 36),
                               lambda _pos, index=index: self._click_menu_row(
                                   lambda: setattr(self, "quit_selection", index)))
        layout.blit_line(s, "control.quit_hint",
                         (rect.x + 20, rect.bottom - 44, rect.w - 40, 28),
                         config.COLOR_TEXT_DIM, size=18, align="center")

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
                self.autosave_tick(wall_dt)
                self.lobby_tick(wall_dt)
                self.update_tick()
                self._perf_debug_log(wall_dt)
                if self.web_mode:
                    game_visible()
                    continue
                self._pump_speech()
                if self._skip_eco_frame():
                    continue
                draw_started = time.perf_counter() if self._perf_debug_enabled else None
                self.draw()
                self.compose_frame()
                game_visible()
                if draw_started is not None:
                    self._perf_draw_s += time.perf_counter() - draw_started
            # A normal quit (never a crash) keeps the running mission.
            self.autosave_on_exit()
        finally:
            try:
                self.commander.stop()
            finally:
                try:
                    self.connectivity.stop()
                    self.live_traffic.stop()
                finally:
                    self.speaker.stop()
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
        elif name == "level":
            # Beginner brings the operator assistance, the others drop it.
            self.preferences = replace(self.preferences, operator_assist=(
                "training" if value == "beginner" else "off"))
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
