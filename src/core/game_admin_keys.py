"""Keys of the administrative overlays (options, save/load, nations, F8/F9,
live traffic): opening an overlay and its key owner.  Moved verbatim from
``game_events.py``; ``EventMixin`` inherits ``AdminKeysMixin``.
"""

import os

import pygame

from src.core import config
from src.core.i18n import message
from src.core import manual
from src.core.game_shared import HELP_MANUAL_PAGE, HELP_PAGE_COUNT
from src.nations.nations import reference_summary
from src.ui import layout, theme
from src.ui.editor_widgets import TextField
from src.core.game_save import SaveSelfCheckError, _read_save_document
from src.core.preferences import GRAPHICS_LEVELS


class AdminKeysMixin:
    """Administration-overlay half of ``EventMixin``."""

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
        self.advisor_open = name == "advisor"
        self.llm_open = name == "llm"
        if self.llm_open:
            self.llm_sel = 0
            self.llm_field = self.llm_field_name = None
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
            "submarine" if self.local_side == "uboot"
            else manual.STATION_CHAPTERS.get(self.station, "quickstart"))
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
                if name in ("live_traffic", "commander", "llm"):
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
                elif name == "night_mode":
                    # Red light: automatic -> always on -> off -> automatic.
                    following = {"auto": "on", "on": "off", "off": "auto"}[
                        self.red_light_mode()]
                    self._set_preference("red_light_auto", following == "auto")
                    value = following == "on"
                elif name == "theme":
                    # Colour theme: night -> day -> high contrast -> night.
                    self.set_color_theme(theme.next_theme(self.color_theme()))
                    return
                elif name == "graphics":
                    levels = GRAPHICS_LEVELS
                    step = -1 if key == pygame.K_LEFT else 1
                    current = (self.preferences.graphics
                               if self.preferences.graphics in levels else "normal")
                    value = levels[(levels.index(current) + step) % len(levels)]
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
                except SaveSelfCheckError:
                    self.flash(message("runtime.save.error",
                                       error=message("save.self_check_failed")), 4.0)
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
