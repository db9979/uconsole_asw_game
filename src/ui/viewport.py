"""W0: Viewport-Kamera für Karte & Scopes (stufenlos Zoom + Pan).

Weltkoordinaten: NM (0..world_size, y nach Süden). Screen: Pixel im
angegebenen Rect. 0° = Norden (oben), 90° = Osten (rechts).
"""

from src.core import config


class Viewport:
    def __init__(self, world_size_nm: float, min_scale: float,
                 max_scale: float):
        self.world_size = world_size_nm
        self.min_scale = min_scale
        self.max_scale = max_scale
        self.cx = world_size_nm / 2.0
        self.cy = world_size_nm / 2.0
        self.scale = 1.0
        self._rect = (0, 0, world_size_nm, world_size_nm)

    # --- Rect (je Frame gesetzt) ---

    def set_rect(self, rect: tuple) -> None:
        """rect = (x, y, w, h) in Pixel."""
        self._rect = rect

    @property
    def rect(self) -> tuple:
        return self._rect

    def fits_world(self) -> None:
        """Zurück auf 'ganze Welt sichtbar'."""
        x, y, w, h = self._rect
        self.scale = min(w / self.world_size, h / self.world_size)
        self.cx = self.world_size / 2.0
        self.cy = self.world_size / 2.0

    # --- Transformationen ---

    def world_to_screen(self, x_nm: float, y_nm: float) -> tuple:
        x, y, w, h = self._rect
        px = x + w / 2.0 + (x_nm - self.cx) * self.scale
        py = y + h / 2.0 + (y_nm - self.cy) * self.scale
        return px, py

    def screen_to_world(self, px: float, py: float) -> tuple:
        x, y, w, h = self._rect
        wx = self.cx + (px - (x + w / 2.0)) / self.scale
        wy = self.cy + (py - (y + h / 2.0)) / self.scale
        return wx, wy

    # --- Interaktion ---

    def zoom(self, factor: float, pivot: tuple = None) -> None:
        """Stufenloses Zoomen; pivot = Screen-Pixel, der unter dem Cursor
        fix bleibt (None = Zentrum)."""
        if factor <= 0:
            return
        new_scale = config.clamp(self.scale * factor,
                                 self.min_scale, self.max_scale)
        if new_scale == self.scale:
            return
        if pivot is not None:
            wx, wy = self.screen_to_world(pivot[0], pivot[1])
            self.scale = new_scale
            x, y, w, h = self._rect
            self.cx = wx - (pivot[0] - (x + w / 2.0)) / self.scale
            self.cy = wy - (pivot[1] - (y + h / 2.0)) / self.scale
        else:
            self.scale = new_scale
        self.clamp_center()

    def pan_px(self, dx_px: float, dy_px: float) -> None:
        """Karte um (dx_px, dy_px) verschieben (Kamera folgt dem Drag)."""
        self.cx -= dx_px / self.scale
        self.cy -= dy_px / self.scale
        self.clamp_center()

    def clamp_center(self) -> None:
        s = self.world_size
        x, y, w, h = self._rect
        half_w = w / 2.0 / self.scale
        half_h = h / 2.0 / self.scale
        if half_w >= s / 2.0:
            self.cx = s / 2.0
        else:
            self.cx = config.clamp(self.cx, half_w, s - half_w)
        if half_h >= s / 2.0:
            self.cy = s / 2.0
        else:
            self.cy = config.clamp(self.cy, half_h, s - half_h)
