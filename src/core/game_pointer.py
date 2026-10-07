"""Pointer mapping of the game window: display to canvas coordinates,
map pointers and tooltips.  Moved verbatim from ``game_events.py``;
``EventMixin`` inherits ``PointerMixin``.
"""

import pygame

from src.core import config
from src.core.commands import MAP_STATIONS
from src.core.station import Station
from src.core.game_shared import letterbox_layout
from src.ui import layout, pointer
from src.ui.map_view import map_hit_target
from src.ui.sonar_view import sonar_hit_target
from src.ui.stations_view import station_hit_target
from src.ui.stations_view import opz_ppi_rect
from src.ui.weapons_view import weapons_hit_target


class PointerMixin:
    """Pointer-mapping half of ``EventMixin``."""

    def _window_to_canvas(self, pos):
        """Convert display coordinates to the virtual 1280x720 canvas."""
        if pos is None:
            return None
        win_w, win_h = self.window.size()
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
        # A status lamp's own note (why it shows what it shows) comes first.
        lamp_tip = layout.valid_tooltip(pointer.tip_at(canvas_pos))
        if lamp_tip is not None or getattr(self, "local_side", "frigate") == "uboot":
            return lamp_tip
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
