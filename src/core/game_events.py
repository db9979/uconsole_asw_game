"""Input ownership of the game: the single-owner ``handle_event`` precedence
(splash, editor, pinned tooltip, administration, menu, numeric entry, live
station controls), the administrative overlays' keys, pointer mapping and
tooltips (``Game`` mixin).

Verbatim moves from ``game.py`` (plan 1.3, phase 2, step 3)."""

import json
import os
import threading

import pygame

from src.core import config
from src.core.autocrew import station_key
from src.core.commands import MAP_STATIONS, STATION_PAGES, station_page_step, toggle_tas, toggle_vds
from src.core.i18n import display_value, localize, message
from src.network.adsb_client import test_connection as adsb_test_connection
from src.network.ais_client import test_connection as ais_test_connection
from src.core import manual
from src.core.station import Station
from src.core.game_shared import (HELP_MANUAL_PAGE, HELP_PAGE_COUNT, SONAR_BAND_PRESETS,
                                  letterbox_layout)
from src.core import training, uboot_local
from src.core.limits import MAX_TRACK_DISPLAY_ID_LEN
from src.sonar import analysis_tools
from src.sonar import tma_operator
from src.data.catalog import CATALOG
from src.data.user_content import default_store
from src.nations.nations import reference_summary
from src.ui import layout
from src.ui.editor_widgets import TextField
from src.ui.map_view import map_hit_target
from src.ui.stations.bridge import lookout_glasses_bearing_at
from src.ui.sonar_view import sonar_click_target, sonar_hit_target
from src.ui.stations_view import station_hit_target
from src.ui.stations_view import (damage_compartment_at, eloka_track_at,
                                    helicopter_acoustic_hit, opz_action_at, opz_ppi_rect,
                                    opz_world_at,
                                    station_page_tab_at)
from src.ui.mission_editor import MissionEditor
from src.ui.unit_editor import UnitEditor, catalog_builtins
from src.ui import simlog_map
from src.ui.weapons_view import weapons_hit_target
# Names tests and tools import from ``src.core.game`` (kept as re-exports).
from src.core.game_save import _read_save_document
from src.core.game_bugreport import BUG_REPORT_ENTRY


# Input and window changes redraw an eco frame at once; pointer motion does not.
_ECO_REFRESH_EVENTS = frozenset(
    getattr(pygame, name) for name in (
        "KEYDOWN", "MOUSEBUTTONDOWN", "VIDEOEXPOSE", "VIDEORESIZE", "WINDOWSHOWN",
        "WINDOWEXPOSED", "WINDOWRESIZED", "WINDOWSIZECHANGED", "WINDOWRESTORED",
        "WINDOWFOCUSGAINED", "WINDOWFOCUSLOST") if hasattr(pygame, name))


class EventMixin:
    """Event half of ``Game``: ``handle_event`` and the owners it dispatches to."""

    def _open_joystick(self, index: int) -> None:
        """Retain SDL device handles; unavailable devices remain optional."""
        try:
            device = pygame.joystick.Joystick(index)
            device.init()
            self._joysticks[device.get_instance_id()] = device
        except pygame.error:
            pass

    @property
    def administration_open(self) -> bool:
        return (self.help_open or self.nations_open or self.quit_confirm
                or self.save_ui is not None or self.options_open or self.commander_open
                or self.live_traffic_open)

    def _clear_station_input(self) -> None:
        self.held.clear()
        self._joy_turn = 0
        self._joy_acc = 0.0
        self._joy_x_acc = 0.0
        self._map_drag = None
        self._map_drag_moved = False

    def _clear_controls(self) -> None:
        self._clear_station_input()
        self._stop_sonar_audio()
        self._frame_clock_reset = True

    def _local_station_input_locked(self) -> bool:
        if (not self.autocrew.enabled[station_key(self.station)]
                and not self.commander.station_leased(self.station)):
            return False
        self._clear_station_input()
        self.input_mode = None
        self.input_buffer = ""
        return True

    def _stop_sonar_audio(self) -> None:
        self.audio.stop_sonar(immediate=True)
        self.sonar.reset_audition_audio()
        self.helo_audition.reset_audition_audio()
        self._sonar_audio_sequence = -1
        self._sonar_audio_suspended = False

    def _open_administration(self, name: str) -> None:
        """One administrative owner; manual/focus pause remains independent."""
        self._clear_controls()
        self.input_mode = None
        self.input_buffer = ""
        if name == "nations":
            self._nations_summary = reference_summary(self.world.coast,
                                                      self.runtime_catalog)
        self.help_open = name == "help"
        self.nations_open = name == "nations"
        self.quit_confirm = name == "quit"
        self.save_ui = name if name in ("save", "load") else None
        self.options_open = name == "options"
        self.commander_open = name == "commander"
        if self.commander_open:
            self.commander.prepare()
        self.live_traffic_open = name == "live_traffic"
        if self.live_traffic_open:
            self.live_traffic_sel = 0
            self.live_traffic_field = None
            self.live_traffic_field_name = None
            self.connectivity.start()
        self.quit_selection = 0
        self.quit_after_save = False
        self.save_confirm = False
        self.msg = ""
        self.help_page = 0
        self.help_scroll = 0
        self.help_manual_chapter = manual.CHAPTERS.index(
            manual.STATION_CHAPTERS.get(self.station, "quickstart"))
        if self.save_ui is not None:
            self.save_info = []
            for slot in range(1, 6):
                path = os.path.join(config.SAVE_DIR, f"slot{slot}.json")
                try:
                    data = _read_save_document(path)
                    if not isinstance(data, dict):
                        raise ValueError("Kein Spielstand")
                    info = message("save.slot_info",
                                   name=data.get("mission_name", "?"),
                                   level=data.get("level", "?"))
                except FileNotFoundError:
                    info = message("save.empty")
                except (OSError, ValueError):
                    info = message("save.unreadable")
                self.save_info.append(info)

    def _handle_administration_key(self, key: int) -> None:
        enter = key in (pygame.K_RETURN, pygame.K_KP_ENTER)
        if self.commander_open:
            self.commander.handle_key(self, key)
        elif self.options_open:
            rows = self._option_rows()
            if key == pygame.K_ESCAPE:
                self.options_open = False
            elif key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN, pygame.K_TAB):
                self._set_options_page(self.options_page
                                       + (-1 if key == pygame.K_PAGEUP else 1))
            elif key in (pygame.K_UP, pygame.K_DOWN):
                self.options_sel = ((self.options_sel + (1 if key == pygame.K_DOWN else -1))
                                    % len(rows))
            elif key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_RETURN, pygame.K_KP_ENTER):
                name = rows[self.options_sel]
                if name == "local_side":
                    self._toggle_local_side()
                    return
                if name in ("live_traffic", "commander"):
                    self._open_administration(name)
                    return
                if name == "language":
                    value = "de" if self.preferences.language == "en" else "en"
                elif name == "frame_rate":
                    choices = config.FPS_CHOICES
                    step = -1 if key == pygame.K_LEFT else 1
                    value = choices[(choices.index(self.frame_rate()) + step) % len(choices)]
                elif name == "level":
                    levels = config.LEVELS
                    step = -1 if key == pygame.K_LEFT else 1
                    value = levels[(levels.index(self._preferred_level()) + step)
                                   % len(levels)]
                elif name == "bottom_panel":
                    choices = layout.BOTTOM_PANEL_MODES
                    value = choices[(choices.index(self.bottom_panel_mode()) + 1)
                                    % len(choices)]
                else:
                    value = not getattr(self.preferences, name)
                self._set_preference(name, value)
        elif self.live_traffic_open:
            self._handle_live_traffic_key(key)
        elif self.quit_confirm:
            choices = (0, 2) if self.in_menu else (0, 1, 3, 2)
            if key in (pygame.K_ESCAPE, pygame.K_n):
                self.quit_confirm = False
            elif key in (pygame.K_UP, pygame.K_DOWN):
                self.quit_selection = (self.quit_selection +
                                       (1 if key == pygame.K_DOWN else -1)) % len(choices)
            elif enter:
                action = choices[self.quit_selection]
                if action == 0:
                    self.quit_confirm = False
                elif action == 1:
                    self._open_administration("save")
                    self.quit_after_save = True
                elif action == 3:
                    self._return_to_main_menu()
                else:
                    self.running = False
        elif self.save_ui is not None:
            if key == pygame.K_ESCAPE:
                if self.save_confirm:
                    self.save_confirm = False
                elif self.quit_after_save:
                    self._open_administration("quit")
                else:
                    self.save_ui = None
            elif pygame.K_1 <= key <= pygame.K_5:
                self.save_slot = key - pygame.K_1 + 1
                self.save_confirm = False
            elif enter:
                path = os.path.join(config.SAVE_DIR, f"slot{self.save_slot}.json")
                if not self.save_confirm and (self.save_ui == "load" or os.path.exists(path)):
                    self.save_confirm = True
                    return
                try:
                    if self.save_ui == "save":
                        self.save_to_slot(self.save_slot)
                        if self.quit_after_save:
                            self.running = False
                    elif not self.load_from_slot(self.save_slot):
                        self.flash(message("save.invalid"), 4.0)
                        return
                except (OSError, ValueError) as exc:
                    self.flash(message("runtime.save.error", error=str(exc)), 4.0)
                    return
                self.save_ui = None
                self.save_confirm = False
                self.quit_after_save = False
        elif self.help_open:
            if key in (pygame.K_ESCAPE, pygame.K_F1):
                self.help_open = False
            elif key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_TAB):
                self.help_page = (self.help_page + (-1 if key == pygame.K_LEFT else 1)) \
                    % HELP_PAGE_COUNT
                self.help_scroll = 0
            elif self.help_page == HELP_MANUAL_PAGE and key in (
                    pygame.K_LEFTBRACKET, pygame.K_RIGHTBRACKET,
                    pygame.K_COMMA, pygame.K_PERIOD):
                step = 1 if key in (pygame.K_RIGHTBRACKET, pygame.K_PERIOD) else -1
                self.help_manual_chapter = (self.help_manual_chapter + step) \
                    % len(manual.CHAPTERS)
                self.help_scroll = 0
            elif self.help_page == HELP_MANUAL_PAGE and pygame.K_0 <= key <= pygame.K_9:
                self.help_manual_chapter = key - pygame.K_0
                self.help_scroll = 0
            elif key == pygame.K_HOME:
                self.help_scroll = 0
            elif key in (pygame.K_UP, pygame.K_DOWN, pygame.K_PAGEUP, pygame.K_PAGEDOWN):
                lines, visible = self._help_lines()
                step = visible if key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN) else 1
                if key in (pygame.K_UP, pygame.K_PAGEUP):
                    step = -step
                self.help_scroll = max(0, min(max(0, len(lines) - visible),
                                              getattr(self, "help_scroll", 0) + step))
        elif self.nations_open and key in (pygame.K_ESCAPE, pygame.K_n):
            self.nations_open = False

    _LIVE_TRAFFIC_ROWS = ("live_ais_enabled", "live_adsb_enabled",
                         "aisstream_api_key", "opensky_credentials", "test")

    def _start_live_traffic_test(self) -> None:
        """Einmaliger Hintergrund-Test, ob AIS-/ADS-B-API erreichbar sind.

        Laeuft in einem eigenen Daemon-Thread (Netzwerk-I/O darf die
        Spiel-Loop nie blockieren, siehe `ais_client`/`adsb_client`);
        `live_traffic_test_result` wird ausschliesslich vom Worker-Thread
        geschrieben und nur im Hauptthread gelesen (Overlay-Zeichnen).
        """
        if (self._live_traffic_test_thread is not None
                and self._live_traffic_test_thread.is_alive()):
            return
        bbox = self.live_traffic._bounding_box_latlon()
        ais_key = self.preferences.aisstream_api_key.strip()
        adsb_credentials = self.preferences.opensky_credentials.strip()
        self.live_traffic_test_result = {
            "ais": ("running", None) if ais_key else ("no_key", None),
            "adsb": ("running", None),
        }

        def _run() -> None:
            result = dict(self.live_traffic_test_result)
            if ais_key:
                ok, reason = ais_test_connection(ais_key, bbox)
                result["ais"] = ("ok", None) if ok else ("error", reason)
            ok, reason = adsb_test_connection(adsb_credentials, bbox)
            result["adsb"] = ("ok", None) if ok else ("error", reason)
            self.live_traffic_test_result = result

        self._live_traffic_test_thread = threading.Thread(
            target=_run, name="live-traffic-test", daemon=True)
        self._live_traffic_test_thread.start()

    def _live_traffic_can_enable(self, name: str) -> bool:
        if not self.connectivity.online:
            return False
        if name == "live_ais_enabled":
            return bool(self.preferences.aisstream_api_key.strip())
        return True

    def _handle_live_traffic_key(self, key: int) -> None:
        name = self._LIVE_TRAFFIC_ROWS[self.live_traffic_sel]
        if self.live_traffic_field is not None:
            if key == pygame.K_ESCAPE:
                self.live_traffic_field = None
                self.live_traffic_field_name = None
            elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._set_preference(self.live_traffic_field_name,
                                     self.live_traffic_field.value.strip())
                self.live_traffic_field = None
                self.live_traffic_field_name = None
                self.live_traffic.configure(self, self.world, self.preferences)
            return
        if key == pygame.K_ESCAPE:
            self.connectivity.stop()
            self.live_traffic_open = False
            return
        if key in (pygame.K_UP, pygame.K_DOWN):
            self.live_traffic_sel = (self.live_traffic_sel
                                     + (1 if key == pygame.K_DOWN else -1)
                                     ) % len(self._LIVE_TRAFFIC_ROWS)
            return
        if key not in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_RETURN, pygame.K_KP_ENTER):
            return
        if name == "test":
            self._start_live_traffic_test()
            return
        if name in ("aisstream_api_key", "opensky_credentials"):
            self.live_traffic_field = TextField(
                value=getattr(self.preferences, name), maximum=256)
            self.live_traffic_field_name = name
            return
        new_value = not getattr(self.preferences, name)
        if new_value and not self._live_traffic_can_enable(name):
            self.flash(message("live_traffic.needs_prerequisite"), 3.0)
            return
        self._set_preference(name, new_value)
        self.live_traffic.configure(self, self.world, self.preferences)

    def _window_to_canvas(self, pos):
        """Convert display coordinates to the virtual 1280x720 canvas."""
        if pos is None:
            return None
        win_w, win_h = pygame.display.get_window_size()
        if win_w <= 0 or win_h <= 0:
            return None
        if config.FILL_SCREEN:
            return (pos[0] * config.SCREEN_W / win_w,
                    pos[1] * config.SCREEN_H / win_h)
        scale, ox, oy, sw, sh = letterbox_layout(win_w, win_h)
        if not (ox <= pos[0] < ox + sw and oy <= pos[1] < oy + sh):
            return None
        return ((pos[0] - ox) / scale, (pos[1] - oy) / scale)

    def _map_pointer(self, event_pos=None):
        """Return a virtual-canvas pointer only when the map is visible."""
        pos = event_pos if event_pos is not None else pygame.mouse.get_pos()
        canvas = self._window_to_canvas(pos)
        if canvas is None or not self._map_station_visible():
            return None
        # The lookout's binoculars cover the chart: it takes no pointer then.
        if self.lookout_glasses_shown():
            return None
        if not pygame.Rect(config.MAP_RECT).collidepoint(canvas):
            return None
        return canvas

    def _map_station_visible(self) -> bool:
        return (self.station in MAP_STATIONS
                and not (self.station is Station.HELICOPTER
                         and self.station_page == 3))

    def _opz_map_pointer(self, event_pos=None):
        """Return a canvas pointer only over the native OPZ chart."""
        if self.station is not Station.OPZ:
            return None
        pos = event_pos if event_pos is not None else pygame.mouse.get_pos()
        canvas = self._window_to_canvas(pos)
        if canvas is None:
            return None
        chart = opz_ppi_rect(config.OPZ_STATION_RECT)
        return canvas if chart.collidepoint(canvas) else None

    def tooltip_at(self, canvas_pos):
        """Return serializable context for the meaningful visual under the pointer."""
        if (not self.tooltips_enabled or canvas_pos is None or self.in_menu
                or self.game_over or self.administration_open):
            return None
        previous = config.STATION_RECT
        config.STATION_RECT = (config.STATION_PANEL_RECT
                               if self._map_station_visible() else
                               config.OPZ_STATION_RECT
                               if self.station is Station.OPZ else
                               config.FULL_STATION_RECT)
        try:
            if (self._map_station_visible()
                    and pygame.Rect(config.MAP_RECT).collidepoint(canvas_pos)):
                if self.lookout_glasses_shown():
                    return None
                return map_hit_target(self, canvas_pos)
            if self.station is Station.SONAR:
                return sonar_hit_target(self, canvas_pos)
            if self.station is Station.WEAPONS:
                return weapons_hit_target(self, canvas_pos)
            return station_hit_target(self, canvas_pos)
        finally:
            config.STATION_RECT = previous

    def _pin_tooltip_at(self, event_pos) -> bool:
        if not self.tooltips_enabled:
            return False
        canvas = self._window_to_canvas(event_pos)
        payload = self.tooltip_at(canvas)
        if payload is None:
            return False
        payload = dict(payload, lines=[self.tr("tooltip.snapshot", time=f"{self.sim_t:.1f}")]
                       + list(payload.get("lines", [])))
        self.pinned_tooltip = layout.valid_tooltip(payload)
        self._tooltip_anchor = tuple(canvas)
        return self.pinned_tooltip is not None

    def bottom_panel_mode(self) -> str:
        mode = getattr(self.preferences, "bottom_panel", "docked")
        return mode if mode in layout.BOTTOM_PANEL_MODES else "docked"

    def handle_event(self, e) -> None:
        with layout.bottom_panel_regions(self.bottom_panel_mode()):
            self._handle_event(e)

    def _handle_event(self, e) -> None:
        # Observe actual input transitions, not candidate restoration. Two owner
        # changes within one wall frame must still invalidate queued commands.
        fields = ("in_menu", "main_menu", "splash_active", "input_mode",
                  "help_open", "nations_open", "quit_confirm", "save_ui",
                  "options_open", "commander_open", "live_traffic_open",
                  "simlog_view_open",
                  "autocrew_overview_open", "weather_station_open",
                  "running", "game_over")
        before = tuple(getattr(self, field) for field in fields), id(self.editor)
        try:
            self._handle_owned_event(e)
        finally:
            after = tuple(getattr(self, field) for field in fields), id(self.editor)
            if before != after:
                self.commander.invalidate_commands()

    def _handle_owned_event(self, e) -> None:
        if e.type == pygame.JOYDEVICEADDED:
            self._open_joystick(e.device_index)
            return
        if e.type == pygame.JOYDEVICEREMOVED:
            device = self._joysticks.pop(e.instance_id, None)
            if device is not None:
                device.quit()
            self._clear_controls()
            return
        if e.type == pygame.WINDOWFOCUSLOST:
            # Real time never stops; losing focus only releases held controls.
            self._clear_controls()
            return
        if e.type == pygame.KEYDOWN and getattr(e, "repeat", False):
            return
        if (e.type == pygame.KEYDOWN
                and e.key in (pygame.K_RETURN, pygame.K_KP_ENTER)
                and getattr(e, "mod", 0) & pygame.KMOD_ALT):
            self.toggle_fullscreen()
            return
        if self.splash_active:
            if e.type == pygame.QUIT:
                self.running = False
            elif (e.type == pygame.KEYDOWN
                  and self._t - self.splash_started_at >= .35):
                self.splash_active = False
            return
        if e.type == pygame.KEYUP:
            self.held.discard(e.key)
            return
        if self.editor is not None:
            if e.type == pygame.QUIT:
                self.editor = None
                self.audio.stop_preview()
                self._open_administration("quit")
                return
            if (e.type == pygame.KEYDOWN and e.key == pygame.K_F5
                    and isinstance(self.editor, MissionEditor)
                    and self.editor.mode == "browser"):
                selected = self.editor.selected
                if selected is not None and not selected.builtin:
                    if self.start_custom_mission(selected.data):
                        self.editor = None
                        self.audio.stop_preview()
                    else:
                        self.editor.status = self.tr("editor.runtime_unsupported")
                return
            if (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE
                    and getattr(self.editor, "mode", "browser") == "browser"):
                self.editor = None
                self.audio.stop_preview()
                if self.in_menu:
                    self.main_menu = True
                return
            if e.type in (pygame.JOYAXISMOTION, pygame.JOYBUTTONDOWN):
                return
            if e.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP,
                          pygame.MOUSEMOTION, pygame.MOUSEWHEEL):
                pos = getattr(e, "pos", pygame.mouse.get_pos())
                canvas = self._window_to_canvas(pos)
                if canvas is None:
                    return
                attrs = dict(e.dict, pos=canvas)
                if hasattr(e, "rel"):
                    previous = self._window_to_canvas((pos[0] - e.rel[0], pos[1] - e.rel[1]))
                    attrs["rel"] = ((canvas[0] - previous[0], canvas[1] - previous[1])
                                    if previous is not None else (0, 0))
                e = pygame.event.Event(e.type, attrs)
            self.editor.handle_event(e)
            return
        if self.simlog_view_open:
            if e.type == pygame.QUIT:
                self._close_simlog_view()
                self._open_administration("quit")
                return
            if e.type == pygame.JOYHATMOTION:
                _, y = e.value
                if y:
                    self._scroll_simlog_view(6 if y < 0 else -6)
                return
            if e.type == pygame.MOUSEWHEEL:
                self._scroll_simlog_view(-e.y * 3)
                return
            if e.type == pygame.KEYDOWN:
                if e.key in (pygame.K_F4, pygame.K_ESCAPE):
                    self._close_simlog_view()
                    return
                if e.key == pygame.K_m:
                    self.simlog_view_map = not self.simlog_view_map
                    return
                if e.key == pygame.K_f and self.simlog_view_map:
                    self.simlog_map_fit = (
                        simlog_map.FIT_UNITS
                        if self.simlog_map_fit == simlog_map.FIT_WORLD
                        else simlog_map.FIT_WORLD)
                    return
                if self.simlog_view_map:
                    return
                if e.key in (pygame.K_UP, pygame.K_DOWN, pygame.K_PAGEUP,
                             pygame.K_PAGEDOWN, pygame.K_HOME, pygame.K_END):
                    amount = {pygame.K_UP: -1, pygame.K_DOWN: 1,
                              pygame.K_PAGEUP: -15, pygame.K_PAGEDOWN: 15,
                              pygame.K_HOME: -10000, pygame.K_END: 10000}[e.key]
                    self._scroll_simlog_view(amount)
                    return
                return
            return
        if self.autocrew_overview_open:
            if e.type == pygame.QUIT:
                self.autocrew_overview_open = False
                self._open_administration("quit")
            elif (e.type == pygame.KEYDOWN
                  and e.key in (pygame.K_F3, pygame.K_ESCAPE)):
                self.autocrew_overview_open = False
                self._clear_station_input()
            return
        if self.weather_station_open:
            # The read-only panel owns input: 0 / Esc close it, nothing leaks
            # to the station underneath.
            if e.type == pygame.QUIT:
                self.weather_station_open = False
                self._open_administration("quit")
            elif (e.type == pygame.KEYDOWN
                  and e.key in (pygame.K_0, pygame.K_KP0, pygame.K_ESCAPE)):
                self.weather_station_open = False
                self._clear_station_input()
            return
        if (self.local_side == "uboot" and not self.in_menu
                and not self.administration_open
                and e.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP,
                               pygame.MOUSEMOTION, pygame.MOUSEWHEEL,
                               pygame.JOYAXISMOTION, pygame.JOYBUTTONDOWN,
                               pygame.JOYBUTTONUP, pygame.JOYHATMOTION)):
            # The frigate's pointer and trackball controls do not exist aboard
            # the boat; only the boat's chart and page tabs take the mouse.
            if e.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP,
                          pygame.MOUSEMOTION, pygame.MOUSEWHEEL):
                uboot_local.handle_pointer(self, e)
            return
        if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            if self._local_station_input_locked():
                return
            if self._map_drag is not None and not self._map_drag_moved:
                if self.station is Station.OPZ:
                    canvas = self._window_to_canvas(getattr(e, "pos", None))
                    point = (opz_world_at(self, canvas, config.OPZ_STATION_RECT)
                             if self.station_page == 2 and self.mpa.airborne else None)
                    if point is not None:
                        self._mpa_order_feedback(self.set_mpa_waypoint(*point))
                    else:
                        self._pin_tooltip_at(getattr(e, "pos", None))
                    self._map_drag = None
                    self._map_drag_moved = False
                    return
                canvas = self._window_to_canvas(getattr(e, "pos", None))
                hit = map_hit_target(self, canvas) if canvas is not None else None
                hit_id = hit.get("id", "") if isinstance(hit, dict) else ""
                parts = hit_id.split(":")
                if len(parts) >= 3 and parts[:2] == ["map", "sonar"] \
                        and parts[2].isascii() and parts[2].isdigit():
                    contact_id = int(parts[2])
                    contact = next((item for item in self.sonar.active_contacts()
                                    if item.id == contact_id), None)
                    if contact is not None:
                        self.selected_contact = contact
                        self._pin_tooltip_at(getattr(e, "pos", None))
                elif (self.station is Station.HELICOPTER and canvas is not None
                      and hit_id.startswith("chart:")):
                    self.map_view.set_rect(config.MAP_RECT)
                    x_nm, y_nm = self.map_view.screen_to_world(*canvas)
                    if self.set_helicopter_waypoint(x_nm, y_nm) is True:
                        bearing, distance = self._helo_waypoint_polar()
                        self.flash(message("runtime.helo.waypoint",
                                           bearing=f"{bearing:03.0f}",
                                           range=f"{distance:.0f}"), 1.5)
                else:
                    self._pin_tooltip_at(getattr(e, "pos", None))
            self._map_drag = None
            self._map_drag_moved = False
            return
        if e.type == pygame.QUIT:
            if self.welcome_active:
                # Closing the window on the welcome page also ends onboarding.
                self._finish_onboarding()
            if not self.quit_confirm:
                self._open_administration("quit")
            return
        if (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE
                and self.pinned_tooltip is not None):
            self.pinned_tooltip = None
            self._tooltip_anchor = None
            return
        if self.administration_open:
            if e.type == pygame.KEYDOWN:
                if (self.live_traffic_field is not None
                        and e.key not in (pygame.K_RETURN, pygame.K_KP_ENTER,
                                         pygame.K_ESCAPE)):
                    self.live_traffic_field.handle_event(e)
                else:
                    self._handle_administration_key(e.key)
            elif e.type == pygame.TEXTINPUT and self.live_traffic_field is not None:
                self.live_traffic_field.handle_text(e.text)
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                canvas = self._window_to_canvas(getattr(e, "pos", None))
                if canvas is not None:
                    if self.commander_open:
                        self.commander.handle_click(self, canvas)
                    elif self.options_open:
                        rows = self._option_rows()
                        for page, rect in enumerate(self._options_page_rects()):
                            if rect.collidepoint(canvas):
                                self._set_options_page(page)
                                break
                        for index, rect in enumerate(self._option_row_hit_rects(rows)):
                            if rect.collidepoint(canvas):
                                self.options_sel = index
                                name = rows[index]
                                if name in ("live_traffic", "commander"):
                                    self._open_administration(name)
                                elif name == "local_side":
                                    self._toggle_local_side()
                                break
            return
        if (e.type == pygame.TEXTINPUT and getattr(e, "text", "") == "?"
                and self.input_mode is None):
            # Layout-independent help key (US Shift+/, DE Shift+ß).
            self._open_administration("help")
            return
        if self.game_over and self.debrief_open:
            # The debrief page owns input until it is closed (Esc or D).
            if e.type == pygame.KEYDOWN:
                self._handle_debrief_key(e.key, getattr(e, "mod", 0))
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                self._handle_debrief_click(self._window_to_canvas(getattr(e, "pos", None)))
            return
        if e.type != pygame.KEYDOWN:
            if self.input_mode is not None or self.in_menu or self.game_over:
                return
            if self.commander.confirm_visible(self):
                if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    canvas = self._window_to_canvas(getattr(e, "pos", None))
                    if (canvas is not None
                            and self.commander.handle_confirm_click(self, canvas)):
                        return
            if self._local_station_input_locked():
                return
        if e.type == pygame.KEYDOWN:
            if self.in_menu:
                if e.key == pygame.K_F1:
                    self._open_administration("help")
                elif e.key == pygame.K_F9:
                    self._open_administration("commander")
                else:
                    self._handle_menu_key(e.key)
                return
            if self.local_side == "uboot" and not self._uboot_dispatch:
                uboot_local.handle_key(self, e)
                return
            if self.input_mode is not None and self._local_station_input_locked():
                pass
            elif self.input_mode is not None:
                self._handle_numeric_input(e.key)
                return
            if e.key == pygame.K_F9:
                self._open_administration("commander")
                return
            if self.commander.confirm_visible(self):
                if self.commander.handle_confirm_key(self, e.key):
                    return
            if (self.plot_mode and not self.game_over
                    and self._handle_plot_key(e.key, getattr(e, "mod", 0))):
                return
            if e.key == pygame.K_ESCAPE:
                self._open_administration("quit")
                return
            if e.key == pygame.K_F1:
                self._open_administration("help")
                return
            if e.key == pygame.K_F10:
                self._open_administration("options")
                return
            if e.key == pygame.K_F11:
                self.feed_overlay_open = not self.feed_overlay_open
                self.feed_overlay_scroll = 0
                return
            if e.key == pygame.K_F8:
                self._open_analyzer_in_game()
                return
            if e.key == pygame.K_F2:
                enabled = self.autocrew.toggle(self.station, self.sim_t)
                self._clear_station_input()
                self.flash(message("autocrew.toggled.on" if enabled
                                   else "autocrew.toggled.off",
                                   station=display_value(
                                       "station", self.station.name, self.tr)))
                return
            if e.key == pygame.K_F3:
                self._clear_station_input()
                self.autocrew_overview_open = True
                return
            if e.key in (pygame.K_0, pygame.K_KP0):
                self._clear_station_input()
                self.pinned_tooltip = None
                self._tooltip_anchor = None
                self.weather_station_open = True
                return
            if e.key == pygame.K_F4:
                self._open_simlog_view()
                return
            if (e.key == pygame.K_n and self.station is not Station.SONAR
                    and not (self.station is Station.HELICOPTER
                             and self.station_page == 3)):
                self._open_administration("nations")
                return
            if e.key in (pygame.K_s, pygame.K_l) and not (
                    e.key == pygame.K_l and self.station is Station.OPZ):
                self._open_administration("save" if e.key == pygame.K_s else "load")
                return
            if pygame.K_1 <= e.key <= pygame.K_9:
                destination = list(Station)[e.key - pygame.K_1]
                self.pinned_tooltip = None
                self._tooltip_anchor = None
                if destination is self.station:
                    # Page cycle: clear held controls, but keep the station's
                    # audio stream continuous (no stop/restart blip).
                    self._clear_station_input()
                    if self.station is Station.SONAR:
                        self.sonar_page = station_page_step(
                            Station.SONAR, self.sonar_page, 1)
                    elif len(STATION_PAGES[self.station]) > 1:
                        self.station_page = station_page_step(
                            self.station, self.station_page, 1)
                else:
                    self._clear_controls()
                    self.station = destination
                    self.station_page = (2 if destination is Station.HELICOPTER
                                         else 0)
                return
            if e.key == pygame.K_TAB:
                self._clear_controls()
                self.pinned_tooltip = None
                self._tooltip_anchor = None
                order = list(Station)
                step = -1 if getattr(e, "mod", 0) & pygame.KMOD_SHIFT else 1
                self.station = order[(order.index(self.station) + step) % len(order)]
                self.station_page = (2 if self.station is Station.HELICOPTER
                                     else 0)
                return
            if self.game_over:
                if e.key == pygame.K_d:
                    self.open_debrief()
                elif e.key == pygame.K_r:
                    definition = self.custom_mission_definition
                    lesson = training.lesson_of(definition)
                    if lesson is not None:
                        self.start_training(lesson)
                    elif definition is None or not self.start_custom_mission(
                            json.loads(json.dumps(definition))):
                        self.reset(self.seed)
                elif e.key == pygame.K_m:
                    self._return_to_main_menu()
                return
            if self._local_station_input_locked():
                return
            if e.key == pygame.K_p and self._plot_view() is not None:
                self.toggle_plot_mode()
                return
            if (e.key in (pygame.K_RETURN, pygame.K_KP_ENTER)
                    and getattr(e, "mod", 0) & pygame.KMOD_CTRL):
                if self.station is Station.WEAPONS:
                    self.launch_torpedo()
                    return
                if self.station is Station.OPZ:
                    self.launch_essm()
                    return
                if self.station is Station.HELICOPTER:
                    self.launch_helo_torpedo()
                    return
            if (self.station is Station.HELICOPTER and self.station_page == 3
                    and e.key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN)):
                step = 1 if e.key == pygame.K_PAGEDOWN else -1
                self.helo_acoustic_page = (self.helo_acoustic_page + step) % 3
                return
            if self.station is Station.SONAR:
                mods = getattr(e, "mod", 0)
                if e.key == pygame.K_c and mods & pygame.KMOD_SHIFT:
                    self._cycle_sonar_display_palette()
                    return
                if e.key == pygame.K_h and mods & pygame.KMOD_SHIFT:
                    self._cycle_sonar_display_history()
                    return
                if e.key in (pygame.K_i, pygame.K_o) and mods & (
                        pygame.KMOD_SHIFT | pygame.KMOD_CTRL):
                    delta = -1.0 if e.key == pygame.K_i else 1.0
                    if mods & pygame.KMOD_SHIFT:
                        self._adjust_sonar_display_contrast(delta * .2)
                    else:
                        self._adjust_sonar_display_black(delta * .01)
                    return
                if e.key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN):
                    self.sonar_page = station_page_step(
                        Station.SONAR,
                        self.sonar_page, 1 if e.key == pygame.K_PAGEDOWN else -1)
                    return
                if e.key == pygame.K_w:
                    pulse = self.sonar.cycle_pulse()
                    self.flash(message("runtime.sonar.pulse",
                                       pulse=message(f"sonar.pulse.{pulse.lower()}")))
                    return
                if e.key == pygame.K_e:
                    if self.measure_sonar_bt() is True:
                        depth = self.sonar.bt_profile["thermocline_m"]
                        self.flash(message("runtime.bt.measured", depth=f"{depth:.0f}"))
                        # The log of the listening side: never the frigate's
                        # feed while the uConsole plays the submarine.
                        notice = message("runtime.bt.feed", depth=f"{depth:.0f}")
                        if self._sonar_ctx is self._frigate_sonar:
                            self.feed.add(self.world.format_time(), "sonar", notice)
                        elif self._opfor is not None and self._sonar_ctx is self._opfor.station:
                            self._opfor.notice(self.sim_t, "sonar", notice,
                                               stamp=self.world.format_time())
                    else:
                        self.flash(message("runtime.bt.cooldown",
                                           seconds=f"{self.sonar.bt_cooldown:.0f}"))
                    return
                if e.key in (pygame.K_u, pygame.K_v) and self.sonar_mode == "VDS":
                    requested = config.clamp(
                        self.sonar.vds_depth_target_m
                        + (-10.0 if e.key == pygame.K_u else 10.0),
                        config.SONAR_VDS_DEPTH_MIN_M,
                        config.SONAR_VDS_DEPTH_MAX_M)
                    self.set_sonar_vds_depth(requested)
                    depth = self.sonar.vds_depth_target_m
                    self.flash(message("runtime.vds.depth", depth=f"{depth:.0f}"))
                    return
                if e.key in (pygame.K_u, pygame.K_v):
                    requested = config.clamp(
                        self.sonar.towed_depth_target_m
                        + (-10.0 if e.key == pygame.K_u else 10.0),
                        config.SONAR_TOWED_DEPTH_MIN_M,
                        config.SONAR_TOWED_DEPTH_MAX_M)
                    self.set_sonar_tow_depth(requested)
                    depth = self.sonar.towed_depth_target_m
                    self.flash(message("runtime.tas.depth", depth=f"{depth:.0f}"))
                    return
                if e.key == pygame.K_r:
                    self._begin_numeric_input("bearing")
                    return
                if e.key == pygame.K_j:
                    self.sonar_audio_enabled = not self.sonar_audio_enabled
                    self._stop_sonar_audio()
                    self.flash(message("runtime.sonar_audio.on" if self.sonar_audio_enabled
                                       else "runtime.sonar_audio.off"))
                    return
                if (e.key == pygame.K_t and self.sonar_page == 3
                        and getattr(e, "mod", 0) & pygame.KMOD_SHIFT):
                    self._cycle_tma_method()
                    return
                if e.key == pygame.K_k and self.sonar_page == 3:
                    self._tma_key(e)
                    return
                if e.key == pygame.K_k:
                    self._cycle_sonar_harmonic()
                    return
                if e.key == pygame.K_x and self.sonar_page in (0, 4):
                    self._tas_side_key(e)
                    return
                if e.key in (pygame.K_z, pygame.K_x) and self.sonar_page in (1, 2):
                    self._sonar_cursor_key(e)
                    return
                if self.sonar_page == 3 and e.key in (pygame.K_z, pygame.K_x,
                                                      pygame.K_q, pygame.K_k):
                    self._tma_key(e)
                    return
                if e.key == pygame.K_q:
                    if getattr(e, "mod", 0) & pygame.KMOD_SHIFT:
                        self.set_sonar_vernier(not self.sonar_tools.vernier)
                        self.flash(message("runtime.vernier.on" if self.sonar_tools.vernier
                                           else "runtime.vernier.off"), 1.5)
                    else:
                        seconds = self.sonar_tools.cycle_integration()
                        self.flash(message("runtime.integration", seconds=seconds), 1.5)
                    return
                if e.key == pygame.K_d:
                    mode = ("BROADBAND" if self.sonar.audition_mode == "FILTERED"
                            else "FILTERED")
                    self._set_sonar_audition_mode(mode)
                    return
                if e.key in (pygame.K_a, pygame.K_b, pygame.K_h) \
                        and not getattr(e, "mod", 0) & pygame.KMOD_SHIFT:
                    self._set_sonar_audition_mode({pygame.K_a: "BROADBAND",
                                                   pygame.K_b: "FILTERED",
                                                   pygame.K_h: "HETERODYNE"}[e.key])
                    return
                if e.key in (pygame.K_COMMA, pygame.K_PERIOD):
                    self.sonar_volume = round(config.clamp(self.sonar_volume +
                        (.1 if e.key == pygame.K_PERIOD else -.1), 0.0, 1.0), 1)
                    self.flash(message("runtime.listen.volume",
                                        volume=f"{self.sonar_volume:.0%}"))
                    return
                if e.key in (pygame.K_LEFT, pygame.K_RIGHT):
                    mods = getattr(e, "mod", 0)
                    step = .1 if mods & pygame.KMOD_CTRL else (5.0 if mods & pygame.KMOD_SHIFT else .5)
                    self.set_sonar_listen_bearing((self.sonar.listen_bearing +
                        (step if e.key == pygame.K_RIGHT else -step)) % 360.0)
                    return
                if e.key in (pygame.K_UP, pygame.K_DOWN):
                    self._cycle_selected_contact(1 if e.key == pygame.K_DOWN else -1)
                    return
                if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    contact = self.selected_contact
                    if self.sonar.focus_locked:
                        if self.clear_sonar_focus() is True:
                            self.flash(message("runtime.listen.manual"))
                    elif contact is not None and self.set_sonar_focus(contact) is True:
                        self.flash(message("runtime.listen.follow", contact=contact.id))
                    else:
                        self.flash(message("runtime.listen.no_contact"))
                    return
            if self.station in (Station.OPZ, Station.RADAR) and \
                    e.key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN):
                self._cycle_radar_range(
                    1 if e.key == pygame.K_PAGEUP else -1)
                return
            # The raised binoculars take ↑/↓ (tilt), Q/E (zoom) and Space
            # (stabilizer) from the telegraph and the covered chart.
            if self.lookout_glasses_shown() and self._lookout_optics_key(e):
                return
            if e.key in (pygame.K_UP, pygame.K_DOWN):
                if self.station is Station.DAMAGE:
                    self.dmg_team = (self.dmg_team - 1 +
                                     (1 if e.key == pygame.K_DOWN else -1)) % 3 + 1
                elif self.station is Station.WEAPONS:
                    self.held.add(e.key)
                elif self.station is Station.BRIDGE:
                    self.ship.cycle_telegraph(
                        1 if e.key == pygame.K_UP else -1)
                    self.flash(message("runtime.telegraph", order=self.ship.telegraph), 1.5)
                elif self.station is Station.ENGINE:
                    self._cycle_engine_telegraph(
                        1 if e.key == pygame.K_UP else -1)
                    self.flash(message("runtime.telegraph", order=self.ship.telegraph), 1.5)
                elif self.station is Station.HELICOPTER:
                    self._adjust_helo_waypoint(
                        range_delta=1.0 if e.key == pygame.K_UP else -1.0)
                elif self.station is Station.RADIO and self.station_page == 2:
                    self._cycle_task(1 if e.key == pygame.K_DOWN else -1)
                elif self.station is Station.RADIO:
                    self._cycle_hfdf(1 if e.key == pygame.K_DOWN else -1)
                elif self.station in (Station.OPZ, Station.RADAR):
                    self._cycle_opz_track(1 if e.key == pygame.K_DOWN else -1)
                elif self.station is Station.ELOKA:
                    self._cycle_eloka_track(1 if e.key == pygame.K_DOWN else -1)
                return
            if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_BACKSPACE) and self.station is Station.DAMAGE:
                if e.key == pygame.K_BACKSPACE:
                    destination = self.damage.teams[self.dmg_team]
                    if destination is not None:
                        self.unassign_damage_team(self.dmg_team, destination)
                    self.flash(message("runtime.team.withdrawn", team=self.dmg_team))
                else:
                    self._assign_selected_team()
                return
            crew_page = self.station is Station.DAMAGE and self.station_page == 2
            if e.key == pygame.K_w and crew_page:
                if self.change_watch() is not True:
                    self.flash(message("crew.watch_blocked"), 2.0)
                return
            if e.key in (pygame.K_m, pygame.K_u) and crew_page:
                if e.key == pygame.K_m:
                    self.casualty_medic()
                else:
                    self.casualty_reassign()
                return
            if e.key == pygame.K_g and (self.station is Station.BRIDGE or crew_page):
                self.toggle_action_stations()
                return
            if (e.key in (pygame.K_a, pygame.K_d, pygame.K_r, pygame.K_k, pygame.K_h)
                    and self.station is Station.RADIO and self.station_page == 2):
                if e.key in (pygame.K_k, pygame.K_h):
                    result = (self.send_contact_report() if e.key == pygame.K_k
                              else self.request_support())
                    if result is not True:
                        self.flash(message("runtime.task." + result), 2.5)
                elif e.key == pygame.K_a:
                    self._task_accept_selected()
                elif e.key == pygame.K_r:
                    self._ras_request_selected()
                else:
                    self._task_decline_selected()
                return
            if self.station is Station.OPZ and self.station_page == 2 and e.key in (
                    pygame.K_a, pygame.K_w, pygame.K_z, pygame.K_x, pygame.K_y,
                    pygame.K_t, pygame.K_d, pygame.K_v):
                shift = bool(getattr(e, "mod", 0) & pygame.KMOD_SHIFT)
                order = {
                    pygame.K_a: self.toggle_mpa,
                    pygame.K_w: self.mpa_waypoint_to_selection,
                    pygame.K_z: ((lambda: self.set_mpa_pattern("single")) if shift
                                 else self.cycle_mpa_pattern),
                    pygame.K_x: self.mpa_drop_buoy,
                    pygame.K_y: self.toggle_mpa_buoy_mode,
                    pygame.K_t: self.toggle_mpa_radar,
                    pygame.K_v: self.toggle_mpa_mad,
                    pygame.K_d: self.mpa_attack,
                }[e.key]
                self._mpa_order_feedback(order())
                return
            if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER) \
                    and self.station is Station.RADIO:
                self.capture_hfdf()
                return
            if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER) \
                    and self.station is Station.OPZ:
                self.confirm_live_engagement()
                return
            if e.key == pygame.K_n and self.station is Station.HELICOPTER and self.station_page == 3:
                self.set_helicopter_audio_notch(not self.helo_audition.notch_enabled)
                return
            if (e.key == pygame.K_n and self.station is Station.SONAR
                    and getattr(e, "mod", 0) & pygame.KMOD_SHIFT):
                current = getattr(self.sonar, "operator_notch_hz", None)
                cursor = self.sonar_tools.lofar_cursor_hz
                self.set_sonar_operator_notch(None if current == cursor else cursor)
                notch = self.sonar.operator_notch_hz
                if notch is None:
                    self.flash(message("runtime.operator_notch.off"), 1.5)
                else:
                    self.flash(message("runtime.operator_notch.on",
                                       frequency=f"{notch:.1f}"), 1.5)
                return
            if e.key == pygame.K_n:
                if self.station is Station.SONAR:
                    self.set_sonar_notch(not self.sonar.notch_enabled)
                    self.flash(message("runtime.notch.on" if self.sonar.notch_enabled
                                       else "runtime.notch.off"), 1.5)
                else:
                    self.nations_open = not self.nations_open
            elif e.key == pygame.K_SPACE and self.station is Station.SONAR:
                self.set_sonar_peak_hold(not self.sonar.peak_hold)
                self.flash(message("runtime.peak_hold.on" if self.sonar.peak_hold
                                   else "runtime.peak_hold.off"), 1.5)
            elif e.key == pygame.K_SPACE and self.station is Station.OPZ:
                self._toggle_opz_mark()
            elif e.key == pygame.K_l and self.station is Station.OPZ:
                if getattr(e, "mod", 0) & pygame.KMOD_SHIFT:
                    self._dissolve_opz_fusion()
                else:
                    self._create_opz_fusion()
            elif e.key == pygame.K_u and self.station is Station.OPZ:
                if getattr(e, "mod", 0) & pygame.KMOD_SHIFT:
                    self._dismiss_opz_suggestion()
                else:
                    self._accept_opz_suggestion()
            elif e.key == pygame.K_j and self.station is Station.OPZ:
                self._begin_track_id_input()
            elif e.key == pygame.K_j and self.station is Station.HELICOPTER:
                if not self.helo_audio_enabled and not self.helicopter_audio_ready():
                    self.flash(message("runtime.sonar_audio.receiver_required"))
                    return
                self.helo_audio_enabled = not self.helo_audio_enabled
                self._stop_sonar_audio()
                self.flash(message("runtime.sonar_audio.on" if self.helo_audio_enabled
                                   else "runtime.sonar_audio.off"))
            elif e.key == pygame.K_b and self.station is Station.BRIDGE \
                    and getattr(e, "mod", 0) & pygame.KMOD_CTRL:
                self._route_result(self.clear_baffles())
            elif e.key == pygame.K_b and self.station is Station.BRIDGE \
                    and self.station_page == 2:
                self._toggle_lookout_glasses()
            elif e.key in (pygame.K_COMMA, pygame.K_PERIOD) \
                    and self.lookout_glasses_shown():
                step = (config.LOOKOUT_GLASSES_STEP_FAST_DEG
                        if getattr(e, "mod", 0) & pygame.KMOD_SHIFT
                        else config.LOOKOUT_GLASSES_STEP_DEG)
                self._train_lookout_glasses(step if e.key == pygame.K_PERIOD else -step)
            elif e.key in (pygame.K_COMMA, pygame.K_PERIOD) \
                    and self.station is Station.BRIDGE and self.station_page == 2:
                self._cycle_lookout_range(1 if e.key == pygame.K_PERIOD else -1)
            elif e.key in (pygame.K_COMMA, pygame.K_PERIOD) \
                    and self.station is Station.WEAPONS:
                self._adjust_torpedo_enable(1 if e.key == pygame.K_PERIOD else -1)
            elif e.key == pygame.K_w and self.station is Station.WEAPONS:
                self._cycle_torpedo_type()
            elif e.key == pygame.K_x and self.station is Station.WEAPONS:
                self._cycle_torpedo_pattern()
            elif e.key == pygame.K_x and self.station is Station.HELICOPTER:
                self._cycle_helicopter_pattern()
            elif (e.key == pygame.K_m and self.station is Station.HELICOPTER
                  and getattr(e, "mod", 0) & pygame.KMOD_SHIFT):
                result = self.set_helicopter_mad(not self.helo.mad_mode)
                if result == "dip_deployed":
                    self.flash(message("runtime.helo.mad_dip"), 2.0)
                elif result == "not_ready":
                    self.flash(message("runtime.helo.not_airborne"))
            elif e.key in (pygame.K_COMMA, pygame.K_PERIOD) \
                    and self.station is Station.HELICOPTER and self.station_page == 3:
                self.sonar_volume = round(config.clamp(self.sonar_volume +
                    (.1 if e.key == pygame.K_PERIOD else -.1), 0.0, 1.0), 1)
                self.flash(message("runtime.listen.volume",
                                   volume=f"{self.sonar_volume:.0%}"))
            elif e.key == pygame.K_BACKSPACE and self.station is Station.OPZ:
                self.opz_fusion.marked.clear()
            elif e.key == pygame.K_BACKSPACE and self.station is Station.BRIDGE:
                self._route_result(self.clear_route(), "runtime.route.cleared")
            elif e.key == pygame.K_w and self.station is Station.BRIDGE:
                self._route_result(self.cycle_route_pattern())
            elif e.key == pygame.K_DELETE and self.station is Station.OPZ:
                self._toggle_opz_suppression()
            elif e.key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
                self.ship.cycle_telegraph(1)
                self.flash(message("runtime.telegraph", order=self.ship.telegraph), 1.5)
            elif e.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                self.ship.cycle_telegraph(-1)
                self.flash(message("runtime.telegraph", order=self.ship.telegraph), 1.5)
            elif e.key in (pygame.K_i, pygame.K_o) and self.station is Station.SONAR:
                self._adjust_sonar_gain(-3.0 if e.key == pygame.K_i else 3.0)
            elif e.key in (pygame.K_i, pygame.K_o) and self.station is Station.HELICOPTER and self.station_page == 3:
                self.set_helicopter_audio_gain(config.clamp(
                    self.helo_audition.gain_db + (-3.0 if e.key == pygame.K_i else 3.0), -12.0, 24.0))
            elif e.key == pygame.K_i and self.station is Station.OPZ:
                if self.set_ciws_authorized(not self.ciws_authorized) is True:
                    self.flash(message(
                        "runtime.ciws.authorized" if self.ciws_authorized
                        else "runtime.ciws.withheld"), 1.5)
            elif e.key == pygame.K_a and (self.station is not Station.SONAR
                                           or getattr(e, "mod", 0) & pygame.KMOD_SHIFT):
                if self.station is Station.SONAR:
                    result = self.send_active_ping()
                    if result == "sonar_down":
                        self.flash(message("runtime.sonar.down"), 3.0)
                    elif result is True:
                        self.flash(message("runtime.ping.sent"), 1.5)
                elif self.station is Station.ENGINE:
                    if self.set_quiet_mode(not self.ship.quiet_mode) is True:
                        self.flash(message("runtime.quiet.on" if self.ship.quiet_mode
                                           else "runtime.quiet.off"))
                elif self.station is Station.HELICOPTER:
                    result = self.send_helicopter_dipping_ping()
                    self.flash(message("runtime.helo.dip_ping_sent" if result is True
                                       else "runtime.helo.dip_ping_unavailable"))
                elif self.station is Station.WEAPONS:
                    self.fire_own_asroc()
                elif self.station is Station.ELOKA:
                    self.set_ecm_auto(not self.ecm_jammer.auto_enabled)
                    self.flash(message("runtime.eloka.auto_on"
                                       if self.ecm_jammer.auto_enabled else
                                       "runtime.eloka.auto_off"), 1.5)
            elif (e.key == pygame.K_r and self.station is Station.HELICOPTER
                  and getattr(e, "mod", 0) & pygame.KMOD_SHIFT):
                self.set_helicopter_radar(not self.helo.radar_on)
            elif e.key == pygame.K_r:
                if self.station in (Station.OPZ, Station.RADAR):
                    domain = ("air" if getattr(e, "mod", 0)
                              & pygame.KMOD_SHIFT else "surface")
                    self.toggle_radar(domain)
                elif self.station is Station.HELICOPTER and self.station_page == 3:
                    self.set_helicopter_listen_bearing(None)
                elif self.station is Station.WEAPONS:
                    if getattr(e, "mod", 0) & pygame.KMOD_SHIFT:
                        self.fire_rbu_defence()
                    else:
                        self.fire_rbu()
            elif e.key == pygame.K_m:
                if self.station in (Station.SONAR, Station.WEAPONS,
                                    Station.HELICOPTER):
                    self.set_target()
                elif self.station in (Station.OPZ, Station.RADAR):
                    self.designate_opz_track()
                elif self.station is Station.ELOKA:
                    self.eloka_audio_enabled = not self.eloka_audio_enabled
                    self.flash(message("runtime.eloka_audio.on"
                                       if self.eloka_audio_enabled else
                                       "runtime.eloka_audio.off"))
            elif e.key == pygame.K_u and self.station in (Station.BRIDGE,
                                                           Station.ENGINE):
                self._begin_numeric_input("course")
            elif e.key == pygame.K_LEFT:
                if self.station is Station.BRIDGE:
                    self.held.add(e.key)
                elif self.station is Station.WEAPONS:
                    self._cycle_selected_contact(-1)
                elif self.station in (Station.OPZ, Station.RADAR):
                    self._cycle_asm_track(-1)
                elif self.station is Station.DAMAGE:
                    n = len(self.damage.compartments)
                    self.dmg_cursor = (self.dmg_cursor - 1) % n
                elif self.station is Station.HELICOPTER:
                    if self.station_page == 3:
                        self.set_helicopter_listen_bearing(
                            ((self.helo_listen_bearing or 0.0) - 5.0) % 360.0)
                    else:
                        self._adjust_helo_waypoint(bearing_delta=-15.0)
            elif e.key == pygame.K_RIGHT:
                if self.station is Station.BRIDGE:
                    self.held.add(e.key)
                elif self.station is Station.WEAPONS:
                    self._cycle_selected_contact(1)
                elif self.station in (Station.OPZ, Station.RADAR):
                    self._cycle_asm_track(1)
                elif self.station is Station.DAMAGE:
                    n = len(self.damage.compartments)
                    self.dmg_cursor = (self.dmg_cursor + 1) % n
                elif self.station is Station.HELICOPTER:
                    if self.station_page == 3:
                        self.set_helicopter_listen_bearing(
                            ((self.helo_listen_bearing or 0.0) + 5.0) % 360.0)
                    else:
                        self._adjust_helo_waypoint(bearing_delta=15.0)
            elif e.key == pygame.K_c:
                if self.station in (Station.SONAR, Station.HELICOPTER):
                    self._cycle_classification()
                elif self.station is Station.DAMAGE:
                    self._toggle_counterflood()
                elif self.station in (Station.OPZ, Station.RADAR):
                    self._cycle_opz_classification()
                elif self.station is Station.ELOKA:
                    self._cycle_eloka_annotation()
            elif e.key == pygame.K_j and self.station is Station.ELOKA:
                if getattr(e, "mod", 0) & pygame.KMOD_SHIFT:
                    technique = self._cycle_jamming_technique(
                        self.selected_eloka_track())
                    technique_names = {
                        "noise": message("eloka.technique.noise"),
                        "rgpo": message("eloka.technique.rgpo"),
                        "vgpo": message("eloka.technique.vgpo"),
                        "false_targets": message(
                            "eloka.technique.false_targets"),
                    }
                    notice = (message("runtime.eloka.technique",
                                      technique=technique_names[technique])
                              if technique in technique_names else
                              message("runtime.eloka.jamming_off"))
                    self.flash(notice, 1.5)
                else:
                    result = self.deploy_jamming(self.selected_eloka_track())
                    self.flash(message("runtime.eloka.jamming_on"
                                       if result is True else
                                       "runtime.eloka.jamming_off"), 1.5)
            elif e.key == pygame.K_b and (self.station is not Station.SONAR
                                           or getattr(e, "mod", 0) & pygame.KMOD_SHIFT):
                if self.station is Station.SONAR:
                    self._cycle_sonar_mode()
                elif self.station in (Station.WEAPONS, Station.HELICOPTER):
                    if self.station is Station.HELICOPTER and getattr(e, "mod", 0) & pygame.KMOD_SHIFT:
                        self.set_helicopter_buoy_mode(
                            "ACTIVE" if self.helo_buoy_mode == "PASSIVE" else "PASSIVE")
                        self.flash(message("helo.buoy_mode.active" if self.helo_buoy_mode == "ACTIVE"
                                           else "helo.buoy_mode.passive"))
                    else:
                        self.deploy_buoys()
                elif self.station is Station.ELOKA:
                    self._cycle_eloka_filter("band")
                elif self.station is Station.OPZ:
                    self._mark_newest_blip()
            elif e.key == pygame.K_z and self.station is Station.WEAPONS:
                self.drop_depth_charges()
            elif e.key == pygame.K_y and self.station is Station.WEAPONS:
                self._cycle_torpedo_salvo()
            elif e.key == pygame.K_g and self.station is Station.ENGINE:
                self._cycle_plant_mode()
            elif e.key == pygame.K_y:
                if self.station is Station.SONAR:
                    if self.damage.station_down("sonar"):
                        self.flash(message("runtime.sonar.down"), 3.0)
                    elif getattr(e, "mod", 0) & pygame.KMOD_SHIFT:
                        toggle_vds(self, self.tr)
                    else:
                        toggle_tas(self, self.tr)
                elif self.station is Station.HELICOPTER:
                    deploy = self.helo.dip_state in ("STOWED", "RETRIEVING")
                    result = self.set_helicopter_dipping(deploy)
                    if result is True:
                        self.flash(message("runtime.helo.dip_deploy" if deploy
                                           else "runtime.helo.dip_retrieve"))
                    elif result == "weather_unsafe":
                        self.flash(message("runtime.helo.weather_unsafe"))
                    else:
                        self.flash(message("runtime.helo.dip_unavailable"))
            elif e.key == pygame.K_h and self.station in (Station.WEAPONS,
                                                           Station.HELICOPTER):
                self.toggle_helo()
            elif e.key == pygame.K_h and self.station is Station.OPZ:
                self.opz_fusion.show_suppressed = not self.opz_fusion.show_suppressed
                self.opz_selected_track_id = None
            elif e.key == pygame.K_d:
                if self.station in (Station.WEAPONS, Station.HELICOPTER):
                    if self.station is Station.HELICOPTER and self.station_page == 3 \
                            and getattr(e, "mod", 0) & pygame.KMOD_SHIFT:
                        modes = ("BROADBAND", "FILTERED", "HETERODYNE")
                        self.set_helicopter_audio_mode(modes[
                            (modes.index(self.helo_audition.audition_mode) + 1) % len(modes)])
                    else:
                        self.launch_helo_torpedo()
            elif e.key == pygame.K_v and self.station is Station.WEAPONS:
                self.deploy_nixie()
            elif e.key in (pygame.K_u, pygame.K_v) \
                    and self.station is Station.HELICOPTER:
                requested = config.clamp(
                    self.helo.dip_depth_target_m
                    + (-10.0 if e.key == pygame.K_u else 10.0),
                    config.HELO_DIP_DEPTH_MIN_M, config.HELO_DIP_DEPTH_MAX_M)
                if self.set_helicopter_dip_depth(requested) is True:
                    self.flash(message("runtime.helo.dip_depth",
                                       depth=f"{self.helo.dip_depth_target_m:.0f}"))
            elif e.key == pygame.K_e:
                if self.station in (Station.OPZ, Station.RADAR):
                    self.launch_essm()
                elif self._map_station_visible():
                    self.map_view.set_rect(config.MAP_RECT)
                    self.map_view.step_zoom(1, config.MAP_ZOOM_STEPS_NM)
            elif e.key == pygame.K_g and self.station in (Station.OPZ,
                                                           Station.RADAR):
                self.launch_chaff()
            elif e.key == pygame.K_g and self.station is Station.SONAR:
                self._toggle_sonar_release()
            elif e.key == pygame.K_g and self.station is Station.HELICOPTER:
                if getattr(e, "mod", 0) & pygame.KMOD_SHIFT:
                    self._toggle_sonar_release()
                else:
                    self._cycle_helo_contact(1)
            elif e.key == pygame.K_t:
                if self.station is Station.WEAPONS:
                    self.launch_torpedo()
                elif self.station is Station.SONAR:
                    self.set_sonar_tma_enabled(not self.sonar.tma_enabled)
                    self.flash(message("runtime.tma.on" if self.sonar.tma_enabled
                                       else "runtime.tma.off"), 1.5)
                elif self.station is Station.HELICOPTER:
                    if self.station_page == 3:
                        sources = ["DIP", *(f"SB{b.seq}" for b in self.buoys
                                            if b.active and b.mode == "PASSIVE")]
                        current = sources.index(self.helo_listen_source) \
                            if self.helo_listen_source in sources else -1
                        self.set_helicopter_listen_source(sources[(current + 1) % len(sources)])
                        return
                    self.helo_sensor_source = ("BUOY" if self.helo_sensor_source == "DIP"
                                               else "DIP")
                    if self.helo_sensor_source == "BUOY":
                        seq = next((seq for seq in sorted(
                            getattr(self.selected_contact, "buoy_reports", {}))
                            if any(b.seq == seq for b in self.buoys)),
                            self.buoys[0].seq if self.buoys else None)
                        if seq is not None:
                            self.set_helicopter_listen_source(f"SB{seq}")
                    else:
                        self.set_helicopter_listen_source("DIP")
                    self.flash(message("helo.source.buoy" if self.helo_sensor_source == "BUOY"
                                       else "helo.source.dip"))
            elif e.key == pygame.K_f:
                if self.station is Station.SONAR and getattr(e, "mod", 0) & pygame.KMOD_SHIFT:
                    bands = analysis_tools.DEMON_BANDS_HZ
                    current = tuple(self.sonar.receiver.demon_band_hz)
                    index = bands.index(current) if current in bands else -1
                    low, high = bands[(index + 1) % len(bands)]
                    self.set_sonar_demon_band(low, high)
                    self.flash(message("runtime.demon_band", low=f"{low:.0f}",
                                       high=f"{high:.0f}"), 1.5)
                elif self.station is Station.SONAR and getattr(e, "mod", 0) & pygame.KMOD_CTRL:
                    offsets = analysis_tools.HETERODYNE_OFFSETS_HZ
                    current = self.sonar.heterodyne_hz
                    index = offsets.index(current) if current in offsets else -1
                    self.set_sonar_heterodyne(offsets[(index + 1) % len(offsets)])
                    self.flash(message("runtime.heterodyne",
                                       frequency=f"{self.sonar.heterodyne_hz:.0f}"), 1.5)
                elif self.station is Station.SONAR:
                    self._cycle_sonar_band()
                elif self.station is Station.ELOKA:
                    self._cycle_eloka_filter(
                        "threat" if getattr(e, "mod", 0) & pygame.KMOD_SHIFT
                        else "status")
                elif self.station is Station.OPZ:
                    if getattr(e, "mod", 0) & pygame.KMOD_SHIFT:
                        self._cycle_opz_contact_filter()
                    else:
                        self._cycle_opz_affiliation()
                elif self.station is Station.WEAPONS:
                    if self.set_flak_authorized(not self.flak_authorized) is True:
                        self.flash(message(
                            "runtime.flak.authorized" if self.flak_authorized
                            else "runtime.flak.withheld"), 1.5)
                elif self.station is Station.HELICOPTER:
                    if self.station_page == 3 and getattr(e, "mod", 0) & pygame.KMOD_SHIFT:
                        bands = tuple(SONAR_BAND_PRESETS)
                        self.set_helicopter_audio_band(bands[
                            (bands.index(self.helo_audio_band) + 1) % len(bands)])
                        return
                    if self.selected_contact is None:
                        return
                    contact = self.selected_contact
                    result = self.qualify_helicopter_contact(
                        contact, not contact.helo_qualified)
                    if result is True:
                        self.flash(message("helo.contact.confirmed" if contact.helo_qualified
                                           else "helo.contact.unconfirmed", contact=contact.id))
            elif e.key == pygame.K_k:
                if self.station is Station.OPZ:
                    self.opz_map_follow = not self.opz_map_follow
                    if self.opz_map_follow:
                        self._configure_opz_map_view()
                        self.opz_map_view.cx = self.ship.x
                        self.opz_map_view.cy = self.ship.y
                        self.opz_map_view.clamp_center()
                    self.flash(message("runtime.map_follow.on" if self.opz_map_follow
                                       else "runtime.map_follow.off"), 1.5)
                elif self._map_station_visible():
                    self.map_follow = not self.map_follow
                    self.flash(message("runtime.map_follow.on" if self.map_follow
                                       else "runtime.map_follow.off"), 1.5)
            elif e.key == pygame.K_q and self._map_station_visible():
                self.map_view.set_rect(config.MAP_RECT)
                self.map_view.step_zoom(-1, config.MAP_ZOOM_STEPS_NM)
            elif e.key == pygame.K_v and self.station in (Station.BRIDGE,
                                                          Station.ENGINE):
                self._begin_numeric_input("speed")
        elif e.type == pygame.JOYAXISMOTION:
            if e.axis == 0:
                if self.station is Station.BRIDGE:
                    self._joy_turn = (1 if e.value > 0.25 else
                                      -1 if e.value < -0.25 else 0)
                else:
                    self._joy_turn = 0
                    self._joy_x_acc += e.value * 0.6
                    if abs(self._joy_x_acc) > 0.8:
                        step = 1 if self._joy_x_acc > 0.0 else -1
                        self._joy_x_acc = 0.0
                        self._joy_horizontal_step(step)
            elif e.axis == 1:
                self._joy_acc += e.value * 0.6
                if self._joy_acc > 0.8:
                    self._joy_acc = 0.0
                    self._joy_step(1)
                elif self._joy_acc < -0.8:
                    self._joy_acc = 0.0
                    self._joy_step(-1)
        elif e.type == pygame.JOYBUTTONDOWN:
            if self.station is Station.DAMAGE and e.button in (0, 1, 2):
                self.dmg_team = e.button + 1
                self._assign_selected_team()
        elif e.type == pygame.MOUSEWHEEL:
            # Wheel-Events haben nicht in allen SDL-Versionen ein pos.
            if self.in_menu or self.game_over or e.y == 0:
                return
            if self.feed_overlay_open:
                canvas = self._window_to_canvas(
                    getattr(e, "pos", None) or pygame.mouse.get_pos())
                if canvas is not None and self.feed_overlay_rect().collidepoint(canvas):
                    # Wheel up reads older entries.
                    self.feed_overlay_scroll = max(0, self.feed_overlay_scroll + e.y * 3)
                    return
            pointer = self._opz_map_pointer(getattr(e, "pos", None))
            if pointer is not None:
                chart = opz_ppi_rect(config.OPZ_STATION_RECT)
                self._configure_opz_map_view(chart)
                self.opz_map_view.zoom(
                    config.MAP_ZOOM_WHEEL_FACTOR ** e.y, pivot=pointer)
                return
            pointer = self._map_pointer(getattr(e, "pos", None))
            if pointer is None:
                return
            factor = config.MAP_ZOOM_WHEEL_FACTOR ** e.y
            self.map_view.set_rect(config.MAP_RECT)
            self.map_view.zoom(factor, pivot=pointer)
        elif e.type == pygame.MOUSEBUTTONDOWN:
            if (e.button == 3 and self.station is Station.BRIDGE and not self.plot_mode
                    and not self.in_menu and not self.game_over):
                # Right click on the Bridge chart: next autopilot waypoint.
                pointer = self._map_pointer(getattr(e, "pos", None))
                if pointer is not None:
                    self.map_view.set_rect(config.MAP_RECT)
                    x, y = self.map_view.screen_to_world(*pointer)
                    self._route_result(self.add_route_waypoint(float(x), float(y)))
                    return
            if (e.button == 1 and self.plot_mode and not self.in_menu
                    and not self.game_over
                    and self._handle_plot_click(getattr(e, "pos", None))):
                return
            if e.button == 1 and not self.in_menu and not self.game_over:
                if self.station is Station.HELICOPTER and self.station_page == 3:
                    canvas = self._window_to_canvas(getattr(e, "pos", None))
                    hit = helicopter_acoustic_hit(self, canvas)
                    if hit is not None:
                        if hit[0] == "page":
                            self.helo_acoustic_page = hit[1]
                        elif hit[0] == "deck":
                            self.station_page = 2
                        elif hit[0] == "contact":
                            self.selected_contact = next(
                                (contact for contact in self.sonar.active_contacts()
                                 if contact.id == hit[1]), None)
                        else:
                            self.set_helicopter_listen_bearing(hit[1])
                        return
                if (self.station is not Station.SONAR
                        and not (self.station is Station.HELICOPTER
                                 and self.station_page == 3)
                        and len(STATION_PAGES[self.station]) > 1
                        and not self._station_overlay_open):
                    canvas = self._window_to_canvas(getattr(e, "pos", None))
                    station_rect = (config.STATION_PANEL_RECT
                                    if self._map_station_visible() else
                                    config.OPZ_STATION_RECT
                                    if self.station is Station.OPZ else
                                    config.FULL_STATION_RECT)
                    page_index = station_page_tab_at(
                        canvas, pygame.Rect(station_rect),
                        len(STATION_PAGES[self.station]))
                    if page_index is not None:
                        self.station_page = page_index
                        self._clear_station_input()
                        self.pinned_tooltip = None
                        self._tooltip_anchor = None
                        return
                if self.station is Station.SONAR:
                    canvas = self._window_to_canvas(getattr(e, "pos", None))
                    previous = config.STATION_RECT
                    config.STATION_RECT = config.FULL_STATION_RECT
                    try:
                        target = sonar_click_target(self, canvas)
                    finally:
                        config.STATION_RECT = previous
                    if target is not None and self._handle_sonar_click(target):
                        self.pinned_tooltip = None
                        self._tooltip_anchor = None
                        return
                if self.station is Station.DAMAGE:
                    canvas = self._window_to_canvas(getattr(e, "pos", None))
                    previous = config.STATION_RECT
                    config.STATION_RECT = config.FULL_STATION_RECT
                    try:
                        compartment = damage_compartment_at(
                            self, canvas,
                            page=int(getattr(self, "station_page", 0)))
                    finally:
                        config.STATION_RECT = previous
                    if compartment is not None:
                        self.dmg_cursor = list(self.damage.compartments).index(compartment)
                        self._assign_selected_team()
                        self._pin_tooltip_at(getattr(e, "pos", None))
                        return
                if self.station is Station.ELOKA:
                    canvas = self._window_to_canvas(getattr(e, "pos", None))
                    track = eloka_track_at(self, canvas, config.FULL_STATION_RECT)
                    if track is not None:
                        self.eloka_selected_track_key = track.track_key
                        self.pinned_tooltip = None
                        self._tooltip_anchor = None
                        self._pin_tooltip_at(getattr(e, "pos", None))
                        return
                if self.station is Station.OPZ:
                    canvas = self._window_to_canvas(getattr(e, "pos", None))
                    action = opz_action_at(self, canvas, config.OPZ_STATION_RECT)
                    if isinstance(action, tuple) and action[0] == "select":
                        self.opz_selected_track_id = action[1]
                    elif isinstance(action, tuple) and action[0] == "blip":
                        self.mark_radar_blip(action[1])
                    elif action == "classify":
                        self._cycle_opz_classification()
                    elif action == "affiliate":
                        self._cycle_opz_affiliation()
                    elif action == "mark":
                        self._toggle_opz_mark()
                    elif action == "fusion":
                        self._create_opz_fusion()
                    else:
                        action = None
                    if action is not None:
                        self.pinned_tooltip = None
                        self._tooltip_anchor = None
                        return
                    pointer = self._opz_map_pointer(getattr(e, "pos", None))
                    if pointer is not None:
                        self._map_drag = pointer
                        self._map_drag_moved = False
                        return
                if self.lookout_glasses_shown():
                    canvas = self._window_to_canvas(getattr(e, "pos", None)
                                                     or pygame.mouse.get_pos())
                    bearing = (lookout_glasses_bearing_at(self, canvas)
                               if canvas is not None else None)
                    if bearing is not None:
                        self._train_lookout_glasses_to(bearing)
                        return
                pointer = self._map_pointer(getattr(e, "pos", None))
                if pointer is not None:
                    self._map_drag = pointer
                    self._map_drag_moved = False
                    return
                if self._pin_tooltip_at(getattr(e, "pos", None)):
                    self._map_drag = None
                    return
        elif e.type == pygame.MOUSEMOTION:
            if self._map_drag is not None:
                pointer = self._window_to_canvas(getattr(e, "pos", None))
                if pointer is None:
                    return
                dx = pointer[0] - self._map_drag[0]
                dy = pointer[1] - self._map_drag[1]
                # Retain the press origin until cumulative displacement is a drag.
                if not self._map_drag_moved and abs(dx) + abs(dy) <= 2:
                    return
                self._map_drag_moved = True
                if self.station is Station.OPZ:
                    self.opz_map_follow = False
                    self.opz_map_view.pan_px(dx, dy)
                else:
                    self.map_follow = False
                    self.map_view.pan_px(dx, dy)
                self._map_drag = pointer

    def _assign_selected_team(self) -> None:
        destination = list(self.damage.compartments)[self.dmg_cursor]
        if self.assign_damage_team(self.dmg_team, destination) is True:
            self.flash(message("runtime.team.assigned", team=self.dmg_team,
                               compartment=message("compartment." + destination)))
        else:
            self.flash(message("runtime.team.rejected"))

    def _route_result(self, result: str, ok_key: str | None = None) -> None:
        """Flash the outcome of a local autopilot route order."""
        if result == "ok":
            if ok_key is not None:
                self.flash(message(ok_key), 1.5)
        elif result in ("route_full", "bridge_down"):
            self.flash(message(f"runtime.route.{result}"), 2.0)

    def steering_input(self) -> tuple:
        """Turn direction from held keys/Trackball (-1/0/+1).
        M10: Fahrtsatz kommt über den Telegraphen (+/-), nicht per Dauer-Taste."""
        if self.station is not Station.BRIDGE:
            return 0, 0
        turn = 0
        if pygame.K_RIGHT in self.held:
            turn += 1
        if pygame.K_LEFT in self.held:
            turn -= 1
        if self._joy_turn:
            turn = max(-1, min(1, turn + self._joy_turn))
        return turn, 0

    # --- M10–M16: Neue Stationen & Waffensysteme ---

    def _handle_menu_key(self, key) -> None:
        if key == pygame.K_f:
            self.toggle_fullscreen()
            return
        if key == pygame.K_w:
            self.world_mode = {"procedural": "fixed", "fixed": "real_fixed",
                               "real_fixed": "procedural"}[self.world_mode]
            return
        if self.world_mode == "real_fixed" and key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN):
            delta = -1 if key == pygame.K_PAGEUP else 1
            sector = (self.seed % 128 + delta) % 128
            candidate = self.seed - self.seed % 128 + sector
            if candidate == 0:
                candidate += 128
            elif candidate >= 1_000_000_000:
                candidate -= 128
            self.seed = candidate
            return
        if key == pygame.K_r:
            self._reroll_menu_seed()
            return
        if self.welcome_active:
            self._handle_welcome_key(key)
            return
        if self.main_menu:
            entries = self.main_menu_entries()
            if key == pygame.K_UP:
                self.main_menu_sel = (self.main_menu_sel - 1) % len(entries)
            elif key == pygame.K_DOWN:
                self.main_menu_sel = (self.main_menu_sel + 1) % len(entries)
            elif key in (pygame.K_RETURN, pygame.K_SPACE):
                action = entries[self.main_menu_sel % len(entries)]
                if action == "continue":
                    self.continue_from_autosave()
                elif action == "new":
                    # A new game first asks which unit the uConsole plays.
                    self.main_menu = False
                    self.menu_screen = "side"
                    self.menu_sel = 1 if self.local_side == "uboot" else 0
                elif action == "training":
                    self.main_menu = False
                    self.menu_screen = "training"
                    self.menu_sel = 0
                elif action == "campaign":
                    self.main_menu = False
                    self.menu_screen = "campaign"
                    self.menu_sel = 0
                    self.campaign_side = "boat" if self.local_side == "uboot" else "frigate"
                elif action == "load":
                    self._open_administration("load")
                elif action == "mission_editor":
                    profiles = set(catalog_builtins(CATALOG)) | {
                        record.key for record in
                        default_store(config.SAVE_DIR).list("unit")}
                    self.editor = MissionEditor(tr=self.tr, profile_keys=profiles)
                elif action == "unit_editor":
                    self.editor = UnitEditor(catalog_builtins(CATALOG), tr=self.tr)
                elif action == "contact_analyzer":
                    self.editor = self._make_analyzer()
                elif action == "options":
                    self._open_administration("options")
                elif action == BUG_REPORT_ENTRY:
                    self.open_bug_report()
                elif action == "logbook":
                    self.open_logbook()
                else:
                    self._open_administration("quit")
            elif key in (pygame.K_ESCAPE, pygame.K_q):
                self._open_administration("quit")
            return
        if self.menu_screen == BUG_REPORT_ENTRY:
            self._handle_bug_report_key(key)
            return
        if self.menu_screen == "logbook":
            self._handle_logbook_key(key)
            return
        if self.menu_screen == "training":
            count = len(training.LESSONS)
            if key == pygame.K_UP:
                self.menu_sel = (self.menu_sel - 1) % count
            elif key == pygame.K_DOWN:
                self.menu_sel = (self.menu_sel + 1) % count
            elif pygame.K_1 <= key < pygame.K_1 + count:
                self.menu_sel = key - pygame.K_1
            elif key in (pygame.K_RETURN, pygame.K_SPACE):
                self.local_side = training.side_of(training.LESSONS[self.menu_sel])
                if not self.start_training(training.LESSONS[self.menu_sel]):
                    self.flash(message("training.start_failed"), 3.0)
            elif key in (pygame.K_ESCAPE, pygame.K_q):
                self.main_menu = True
                self.main_menu_sel = self.main_menu_index("training")
            return
        if self.menu_screen == "campaign":
            self._handle_campaign_menu_key(key)
            return
        if self.menu_screen == "side":
            if key in (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT, pygame.K_TAB):
                self.menu_sel = 1 - self.menu_sel
            elif key in (pygame.K_1, pygame.K_2):
                self.menu_sel = 0 if key == pygame.K_1 else 1
            elif key in (pygame.K_RETURN, pygame.K_SPACE):
                self.local_side = ("frigate", "uboot")[self.menu_sel]
                self.menu_screen = "scenario"
                self.menu_sel = 0
            elif key in (pygame.K_ESCAPE, pygame.K_q):
                self.main_menu = True
                self.main_menu_sel = self.main_menu_index("new")
            return
        if self.menu_screen == "scenario":
            n = len(config.SCENARIO_ORDER)
            if key == pygame.K_UP:
                self.menu_sel = (self.menu_sel - 1) % n
            elif key == pygame.K_DOWN:
                self.menu_sel = (self.menu_sel + 1) % n
            elif key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4,
                         pygame.K_5, pygame.K_6, pygame.K_7)[:n]:
                self.menu_sel = int(pygame.key.name(key)) - 1
            elif key in (pygame.K_RETURN, pygame.K_SPACE):
                self.scenario_key = config.SCENARIO_ORDER[self.menu_sel]
                sc = config.SCENARIOS[self.scenario_key]
                self.menu_screen = "difficulty" if sc["difficulty"] is None else "briefing"
                if self.menu_screen == "difficulty":
                    self.menu_sel = 0
            elif key in (pygame.K_ESCAPE, pygame.K_q):
                self.main_menu = True
                self.main_menu_sel = self.main_menu_index("new")
            return
        if self.menu_screen == "difficulty":
            # The last row (after the saved difficulty fields) is the HQ intel.
            n = len(config.DIFFICULTY_FIELD_ORDER) + 1
            intel_row = self.menu_sel == n - 1
            if key == pygame.K_UP:
                self.menu_sel = (self.menu_sel - 1) % n
            elif key == pygame.K_DOWN:
                self.menu_sel = (self.menu_sel + 1) % n
            elif key in (pygame.K_LEFT, pygame.K_RIGHT) and intel_row:
                modes = config.HQ_INTEL_MODES
                self.menu_hq_intel = modes[(modes.index(self.hq_intel_mode_menu())
                                            + (1 if key == pygame.K_RIGHT else -1))
                                           % len(modes)]
            elif key in (pygame.K_LEFT, pygame.K_RIGHT):
                name = config.DIFFICULTY_FIELD_ORDER[self.menu_sel]
                kind, low, high, step, _default = config.DIFFICULTY_FIELDS[name]
                delta = step * (1 if key == pygame.K_RIGHT else -1)
                value = config.clamp(self.menu_difficulty[name] + delta, low, high)
                self.menu_difficulty[name] = (
                    int(round(value)) if kind is int else round(value, 6))
            elif key in (pygame.K_RETURN, pygame.K_SPACE):
                self.scenario_key = "s4_zufall"
                self._start_menu_mission()
            elif key == pygame.K_ESCAPE:
                self.menu_screen = "scenario"
                self.menu_sel = 3
            return
        # briefing
        if key in (pygame.K_RETURN, pygame.K_SPACE):
            self._start_menu_mission()
        elif key == pygame.K_ESCAPE:
            self.menu_screen = "scenario"

    def _joy_step(self, delta: int) -> None:
        """uConsole-Trackball Y-Achse: stationsabhängiger Schritt."""
        if self.in_menu or self.game_over:
            return
        if self.station is Station.DAMAGE:
            self.dmg_team = (self.dmg_team - 1 + delta) % 3 + 1
        elif self.station is Station.SONAR:
            self._cycle_selected_contact(delta)
        elif self.station is Station.WEAPONS:
            self.torpedo_depth = config.clamp(
                self.torpedo_depth - delta * 10.0, 10.0, 300.0)
        elif self.station is Station.OPZ:
            self._cycle_opz_track(delta)
        elif self.station is Station.ELOKA:
            self._cycle_eloka_track(delta)
        elif self.station is Station.RADIO and self.station_page == 2:
            self._cycle_task(delta)
        elif self.station is Station.RADIO:
            self._cycle_hfdf(delta)
        elif self.station is Station.HELICOPTER:
            self._adjust_helo_waypoint(range_delta=float(-delta))
        elif self.station is Station.BRIDGE:
            self.ship.cycle_telegraph(-delta)
            self.flash(message("runtime.telegraph", order=self.ship.telegraph), 1.5)
        elif self.station is Station.ENGINE:
            self._cycle_engine_telegraph(-delta)
            self.flash(message("runtime.telegraph", order=self.ship.telegraph), 1.5)

    def _joy_horizontal_step(self, delta: int) -> None:
        """uConsole-Trackball X-Achse: selection or bearing step."""
        if self.in_menu or self.game_over:
            return
        if self.station is Station.DAMAGE:
            n = len(self.damage.compartments)
            self.dmg_cursor = (self.dmg_cursor + delta) % n
        elif self.station is Station.SONAR:
            self.sonar.set_listen_bearing(self.sonar.listen_bearing + delta * .5)
        elif self.station is Station.WEAPONS:
            self._cycle_selected_contact(delta)
        elif self.station is Station.OPZ:
            self._cycle_asm_track(delta)
        elif self.station is Station.HELICOPTER:
            self._adjust_helo_waypoint(bearing_delta=float(delta * 15))

    def _sonar_cursor_key(self, e) -> None:
        """Z/X move the frequency cursor; Shift: 10 Hz; Ctrl on LOFAR sets
        the band-pass low (Z) or high (X) edge at the cursor."""
        page = "demon" if self.sonar_page == 2 else "lofar"
        mods = getattr(e, "mod", 0)
        tools = self.sonar_tools
        if page == "lofar" and mods & pygame.KMOD_CTRL:
            cursor = tools.lofar_cursor_hz
            low, high = self.sonar.band_low_hz, self.sonar.band_high_hz
            low, high = ((cursor, high) if e.key == pygame.K_z else (low, cursor))
            if self.set_sonar_band(low, high) is True:
                self.flash(message("runtime.sonar_band", low=f"{low:.1f}",
                                   high=f"{high:.1f}"), 1.5)
            return
        fine = page == "demon" or tools.vernier
        step = 10.0 if mods & pygame.KMOD_SHIFT else (0.5 if fine else 1.0)
        current = tools.demon_cursor_hz if page == "demon" else tools.lofar_cursor_hz
        self.set_sonar_cursor(page, current + (step if e.key == pygame.K_x else -step))

    # --- Operator TMA (sonar page 3) ---

    def _tma_key(self, e) -> None:
        """TMA page: Z/X course -/+ (Shift fine), Ctrl+Z/X speed -/+,
        Q / Shift+Q range -/+, K accept, Shift+K copy the solver proposal."""
        contact = self._tma_contact()
        if contact is None:
            self.flash(message("runtime.tma.no_contact"), 1.5)
            return
        mods = getattr(e, "mod", 0)
        hypothesis = self.tma_hypothesis(contact)
        course, speed, rng = hypothesis.course, hypothesis.speed_kn, hypothesis.range_nm
        if e.key == pygame.K_k:
            if mods & pygame.KMOD_SHIFT:
                if self.tma_method == "ekelund":
                    result = self.copy_tma_ekelund(contact)
                    self.flash(message("runtime.tma.ekelund_copied" if result is True
                                       else "runtime.tma.ekelund_none"), 1.5)
                    return
                result = self.copy_tma_proposal(contact)
                self.flash(message("runtime.tma.copied" if result is True
                                   else "runtime.tma.no_proposal"), 1.5)
                return
            self._accept_tma_with_notice(contact)
            return
        sign = 1.0 if e.key == pygame.K_x else -1.0
        if e.key == pygame.K_q:
            rng += (tma_operator.RANGE_FINE_NM if mods & pygame.KMOD_CTRL
                    else tma_operator.RANGE_STEP_NM) * (1.0 if mods & pygame.KMOD_SHIFT
                                                        else -1.0)
        elif mods & pygame.KMOD_CTRL:
            speed += tma_operator.SPEED_STEP_KN * sign
        else:
            course += (tma_operator.COURSE_FINE_DEG if mods & pygame.KMOD_SHIFT
                       else tma_operator.COURSE_STEP_DEG) * sign
        self.set_tma_hypothesis(contact, course, speed, rng)

    def _tas_side_key(self, e) -> None:
        contact = self.selected_contact
        action = "confirm" if getattr(e, "mod", 0) & pygame.KMOD_SHIFT else "flip"
        result = self.set_tas_side(contact, action)
        if result is True:
            self.flash(message("runtime.tas_side.confirmed" if action == "confirm"
                               else "runtime.tas_side.flipped",
                               contact=self.contact_display_id(contact),
                               side=contact.towed_side), 1.5)
        else:
            self.flash(message("runtime.tas_side.not_ambiguous"), 1.5)

    def _handle_plot_key(self, key: int, mod: int) -> bool:
        """Plot-mode keys; returns True when the key was consumed."""
        view = self._plot_view()
        if view is None or self._local_station_input_locked():
            self._reset_plot_ui()
            return False
        if key == pygame.K_p or (key == pygame.K_ESCAPE and self.plot_anchor is None):
            self.toggle_plot_mode()
            return True
        if key == pygame.K_ESCAPE:
            self.plot_anchor = None
            return True
        steps = {pygame.K_LEFT: (-1, 0), pygame.K_RIGHT: (1, 0),
                 pygame.K_UP: (0, -1), pygame.K_DOWN: (0, 1)}
        if key in steps:
            px = (self.PLOT_CURSOR_STEP_FAST_PX if mod & pygame.KMOD_SHIFT
                  else self.PLOT_CURSOR_STEP_PX)
            step = px / max(view.scale, 1e-6)
            dx, dy = steps[key]
            limit = self.world.size_nm
            self.plot_cursor = (config.clamp(self.plot_cursor[0] + dx * step, 0.0, limit),
                                config.clamp(self.plot_cursor[1] + dy * step, 0.0, limit))
            return True
        if key in self.PLOT_TOOL_KEYS:
            self.plot_tool = self.PLOT_TOOL_KEYS[key]
            self.plot_anchor = None
            return True
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._plot_commit_point()
            return True
        if key in (pygame.K_BACKSPACE, pygame.K_DELETE):
            if mod & pygame.KMOD_SHIFT:
                self.plot_clear()
                self.flash(message("plot.flash.cleared"), 1.5)
                return True
            item = self.plot.nearest(*self.plot_cursor,
                                     self.PLOT_PICK_PX / max(view.scale, 1e-6))
            if item is not None:
                self.plot_remove(item["id"])
                self.flash(message("plot.flash.removed", label=item["label"]), 1.5)
            return True
        return False

    def _handle_plot_click(self, pos) -> bool:
        """Left click on the chart in plot mode places a point there."""
        view = self._plot_view()
        canvas = self._window_to_canvas(pos) if pos is not None else None
        if view is None or canvas is None:
            return False
        if not pygame.Rect(view.rect).collidepoint(canvas):
            return False
        x, y = view.screen_to_world(*canvas)
        limit = self.world.size_nm
        self._plot_commit_point(config.clamp(x, 0.0, limit), config.clamp(y, 0.0, limit))
        return True

    def _handle_numeric_input(self, key: int) -> None:
        if key == pygame.K_ESCAPE:
            self.input_mode = None
            self.input_buffer = ""
            self.flash(message("event.input_cancelled"), 1.5)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._finish_numeric_input()
        elif key == pygame.K_BACKSPACE:
            self.input_buffer = self.input_buffer[:-1]
        elif self.input_mode == "track_id":
            name = pygame.key.name(key)
            if (len(self.input_buffer) < MAX_TRACK_DISPLAY_ID_LEN
                    and len(name) == 1 and name.isascii()
                    and (name.isalnum() or name == "-")):
                self.input_buffer += name.upper()
            elif (len(self.input_buffer) < MAX_TRACK_DISPLAY_ID_LEN
                  and key in (pygame.K_MINUS, pygame.K_KP_MINUS)):
                self.input_buffer += "-"
        elif len(pygame.key.name(key)) == 1 and pygame.key.name(key).isdigit():
            if len(self.input_buffer) < 5:
                self.input_buffer += pygame.key.name(key)
        elif key in (pygame.K_KP0, pygame.K_KP1, pygame.K_KP2, pygame.K_KP3,
                     pygame.K_KP4, pygame.K_KP5, pygame.K_KP6, pygame.K_KP7,
                     pygame.K_KP8, pygame.K_KP9):
            if len(self.input_buffer) < 5:
                self.input_buffer += pygame.key.name(key).strip("[]")
        elif (self.input_mode in ("speed", "bearing", "plot_speed")
              and key in (pygame.K_PERIOD, pygame.K_COMMA, pygame.K_KP_PERIOD)
              and "." not in self.input_buffer):
            self.input_buffer += "."

    def _finish_numeric_input(self) -> None:
        """Validate and apply a pending course or speed order."""
        mode = self.input_mode
        if mode == "track_id":
            track = self.selected_opz_track()
            result = ("stale_ref" if track is None else
                      self.set_opz_track_label(track.observation_id,
                                               self.input_buffer))
            if result is not True:
                self.flash(message("runtime.cic.track_id_invalid"), 2.0)
                return
            self.flash(message("runtime.cic.track_id_set",
                               track=self.input_buffer.upper()), 2.0)
            self.input_mode = None
            self.input_buffer = ""
            return
        value = self.input_buffer.replace(",", ".")
        try:
            number = float(value)
        except ValueError:
            self.flash(message("event.invalid_input"), 2.0)
            return
        if mode == "plot_speed":
            pending = self._plot_dr_pending
            self.input_mode = None
            self.input_buffer = ""
            self._plot_dr_pending = None
            if pending is not None:
                self._plot_flash_result(self.plot_add(
                    "dr", pending[0], pending[1], course=pending[2],
                    speed_kn=number))
            return
        if mode in ("course", "bearing"):
            if not 0.0 <= number < 360.0:
                self.flash(message("runtime.numeric.angle"), 2.0)
                return
            if mode == "bearing":
                if self.set_sonar_listen_bearing(number) is not True:
                    self.flash(message("event.invalid_input"), 2.0)
                    return
                self.flash(message("runtime.numeric.true_bearing", bearing=f"{number:05.1f}"), 2.0)
            else:
                result = (self.set_engine_course(number)
                          if self.station is Station.ENGINE else self.order_course(number))
                if result in ("bridge_down", "engine_down"):
                    self.flash(message("event.bridge_down" if result == "bridge_down"
                                       else "engine.limit.down"))
                    self.input_mode = None
                    self.input_buffer = ""
                    return
                if result != "ok":
                    self.flash(message("event.invalid_input"), 2.0)
                    return
                self.flash(message("runtime.numeric.course", course=f"{number:03.0f}"), 2.0)
        else:
            if not 0.0 <= number <= config.SHIP_SPEED_MAX_KN:
                self.flash(message("runtime.numeric.speed",
                                   maximum=f"{config.SHIP_SPEED_MAX_KN:.0f}"), 2.0)
                return
            result = (self.set_engine_speed(number) if self.station is Station.ENGINE
                      else self.order_speed(number))
            if result not in (True, "ok"):
                self.flash(message("event.invalid_input"), 2.0)
                return
            self.flash(message("runtime.numeric.speed_set", speed=f"{number:.1f}"), 2.0)
        self.input_mode = None
        self.input_buffer = ""

    def _begin_numeric_input(self, mode: str) -> None:
        """Open a keyboard-first entry for a navigation order."""
        self._clear_controls()
        self.input_mode = mode
        if mode == "bearing":
            self.input_buffer = ""
            prompt = message("runtime.input.bearing",
                             current=f"{self.sonar.listen_bearing:05.1f}")
        elif mode == "plot_speed":
            self.input_buffer = ""
            prompt = message("plot.input.speed")
        elif mode == "course":
            self.input_buffer = ""
            prompt = message("runtime.input.course",
                             current=f"{self.ship.target_course:03.0f}")
        else:
            self.input_buffer = ""
            prompt = message("runtime.input.speed",
                             current=f"{self.ship.target_speed:.1f}")
        self.flash(message("runtime.input.pending", prompt=localize(prompt, self.tr),
                            value=self.input_buffer), 60.0)

    def _begin_track_id_input(self) -> None:
        """Open bounded OPZ entry for the selected track's shared display ID."""
        track = self.selected_opz_track()
        if track is None:
            self.flash(message("runtime.cic.none_select"), 2.0)
            return
        self._clear_controls()
        self.input_mode = "track_id"
        self.input_buffer = ""
        self.flash(message("runtime.input.track_id", current=track.label), 60.0)
