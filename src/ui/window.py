"""The game window: where the finished 1280x720 canvas is shown.

Two kinds of window carry the same picture:

* ``DisplayWindow`` is pygame's own display window (``pygame.display``),
  used on the uConsole, on Windows and on Linux, unchanged since 1.0.
* ``RetinaWindow`` is used on the Mac.  pygame's display window never asks
  macOS for the screen's backing pixels, so on a Retina screen the system
  stretched the picture by two.  This window is an SDL window that allows
  high resolution, with a renderer that shows the canvas on the GPU at the
  screen's own pixels; the canvas is drawn at that resolution (src/ui/hires.py).

Both speak window coordinates (points on the Mac) for the mouse and the
real pixels for drawing.  Display only, never simulation.
"""

from __future__ import annotations

import os
import sys

import pygame

from src.core import config
from src.core.game_shared import letterbox_layout

# Off switch for the Mac window (the picture is then stretched as before).
NO_RETINA_ENV = "U_JAGD_NO_RETINA"
# Test switch: the Mac window on another system.
RETINA_ENV = "U_JAGD_RETINA"
# The open Mac window: pygame's display has no surface then, so the font
# cache keys its lifetime on this window instead (src/ui/layout.py).
_RETINA = None


def live_token():
    """The open Mac window, or None (pygame's display window is used)."""
    return _RETINA.window if _RETINA is not None else None


def wants_retina(platform: str | None = None, env=None) -> bool:
    """True where the game opens the high-resolution Mac window."""
    platform = sys.platform if platform is None else platform
    env = os.environ if env is None else env
    if env.get(NO_RETINA_ENV, "") not in ("", "0"):
        return False
    if env.get(RETINA_ENV, "") not in ("", "0"):
        return True
    return platform == "darwin"


class DisplayWindow:
    """pygame's display window (the uConsole, Windows, Linux)."""

    kind = "display"

    def __init__(self, size, fullscreen: bool, title: str):
        pygame.display.set_caption(title)
        self.set_fullscreen(fullscreen, size)

    def set_fullscreen(self, on: bool, size) -> None:
        # (0,0)+FULLSCREEN lets SDL pick the desktop's own resolution.
        if on:
            pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            pygame.display.set_mode(tuple(size), pygame.RESIZABLE)

    def set_title(self, title: str) -> None:
        pygame.display.set_caption(title)

    def size(self) -> tuple:
        """The window in mouse coordinates."""
        return pygame.display.get_window_size()

    def pixel_size(self) -> tuple:
        """The window in real pixels."""
        return pygame.display.get_window_size()

    def token(self):
        """Changes when SDL replaced the window (font cache lifetime)."""
        return pygame.display.get_surface()

    def present(self, canvas: pygame.Surface) -> None:
        from src.ui import quality
        w, h = self.size()
        base_w, base_h = canvas.get_size()
        if w <= 0 or h <= 0:
            w, h = base_w, base_h
        # Under X11/XWayland pygame replaces the display surface after the
        # first event pump or resize; the current one is always fetched.
        display = pygame.display.get_surface()
        if display is None:
            return
        display.fill((0, 0, 0))
        if (w, h) == (base_w, base_h) and pygame.Surface.get_size(canvas) == (w, h):
            display.blit(canvas, (0, 0))
        elif config.FILL_SCREEN:
            display.blit(quality.scale_canvas(canvas, (w, h)), (0, 0))
        else:
            # Sharp smooth scaling for the graphics level (src/ui/quality.py).
            _, ox, oy, sw, sh = letterbox_layout(w, h, base_w, base_h)
            display.blit(quality.scale_canvas(canvas, (sw, sh)), (ox, oy))
        pygame.display.flip()

    def close(self) -> None:
        pass


class RetinaWindow:
    """An SDL window with the screen's real pixels and a GPU renderer (Mac)."""

    kind = "retina"

    def __init__(self, size, fullscreen: bool, title: str):
        from pygame._sdl2 import video
        # Linear filtering when the texture is fitted to the window.
        os.environ.setdefault("SDL_RENDER_SCALE_QUALITY", "linear")
        self._video = video
        self._window_size = tuple(size)
        self.window = video.Window(title, size=self._window_size,
                                   resizable=True, allow_highdpi=True)
        self.renderer = video.Renderer(self.window, vsync=False)
        self._texture = None
        self._texture_size = None
        global _RETINA
        _RETINA = self
        if fullscreen:
            self.set_fullscreen(True, size)

    def set_fullscreen(self, on: bool, size) -> None:
        if on:
            self.window.set_fullscreen(desktop=True)
        else:
            self.window.set_windowed()
            self.window.size = tuple(size)

    def set_title(self, title: str) -> None:
        self.window.title = title

    def size(self) -> tuple:
        return tuple(self.window.size)

    def pixel_size(self) -> tuple:
        # Without a viewport the renderer covers its whole output, which
        # on a Retina screen counts the real pixels.
        self.renderer.set_viewport(None)
        view = self.renderer.get_viewport()
        return (view.w, view.h)

    def token(self):
        return self.window

    def present(self, canvas: pygame.Surface) -> None:
        w, h = self.pixel_size()
        if w <= 0 or h <= 0:
            return
        physical = pygame.Surface.get_size(canvas)
        if self._texture is None or self._texture_size != physical:
            self._texture = self._video.Texture(self.renderer, physical, streaming=True)
            self._texture_size = physical
        self._texture.update(canvas)
        base_w, base_h = canvas.get_size()
        _, ox, oy, sw, sh = letterbox_layout(w, h, base_w, base_h)
        self.renderer.draw_color = (0, 0, 0, 255)
        self.renderer.clear()
        self.renderer.blit(self._texture, pygame.Rect(ox, oy, sw, sh))
        self.renderer.present()

    def close(self) -> None:
        global _RETINA
        if _RETINA is self:
            _RETINA = None
        self._texture = None
        self.window.destroy()


def open_window(size, fullscreen: bool, title: str):
    """The game window for this system; pygame's own if the Mac window fails."""
    if wants_retina():
        try:
            return RetinaWindow(size, fullscreen, title)
        except (pygame.error, ImportError, AttributeError, TypeError, OSError):
            pass
    return DisplayWindow(size, fullscreen, title)
