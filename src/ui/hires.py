"""High-resolution drawing for large windows (display only).

Every view draws on the virtual 1280x720 canvas in logical pixels.  In a
window much larger than that (a desktop monitor in fullscreen, a 4K screen)
the canvas is made ``SCALE`` times larger in physical pixels while all
drawing keeps its logical coordinates: text is rendered from the font at
``SCALE`` times its size, lines, circles, polygons and rectangles are drawn
at the physical resolution, and the frame is then fitted to the window.
Layout, hit testing and text measuring stay those of the 1280x720 canvas, so
the picture is the same one the uConsole shows, only sharper.

How it works: a canvas made by :func:`surface` while ``SCALE`` is above one
is a :class:`pygame.Surface` subclass whose class carries ``K`` (its
physical pixels per logical pixel).  Its size, rect, clip, fill, blit,
subsurface and pixel methods speak logical pixels; ``pygame.draw`` and the
used ``pygame.transform`` functions are wrapped (once, on the first large
window) so that they scale the coordinates of such a surface and leave every
other surface untouched.  Text comes from :class:`HiFont`: its measurements
are those of the logical face (so word wraps and ellipses match the
uConsole), only ``render`` draws with the larger face.

The uConsole's own 1280x720 screen never switches this on: nothing is
wrapped and every surface stays a plain ``pygame.Surface``.  Nothing here
reads or changes the simulation.
"""

from __future__ import annotations

import math
import os

import pygame

# Physical pixels per logical pixel of new canvases (1 = plain 1280x720).
SCALE = 1
# The highest factor (a 4K screen draws at 3x; larger screens upscale).
MAX_SCALE = 3
# True once the drawing functions are wrapped (the first large window).
ACTIVE = False
# Environment switch to keep the plain 1280x720 picture everywhere.
DISABLE_ENV = "U_JAGD_NO_HIRES"

# 32-bit RGB without alpha: an opaque canvas never takes the window format.
OPAQUE_MASKS = (0xFF0000, 0xFF00, 0xFF, 0)

_CLASSES: dict = {}
_K_OF: dict = {}
_RAW: dict = {}


def choose_scale(window_w: int, window_h: int, canvas_w: int, canvas_h: int,
                 level: str = "normal") -> int:
    """The drawing factor for a window: the canvas' letterbox factor rounded
    up to whole pixels (1 at or below the canvas size, at the low graphics
    level, or when ``U_JAGD_NO_HIRES`` is set)."""
    if level == "low" or os.environ.get(DISABLE_ENV, "") not in ("", "0"):
        return 1
    if window_w <= 0 or window_h <= 0:
        return 1
    factor = min(window_w / canvas_w, window_h / canvas_h)
    # A window only a few pixels larger than the canvas keeps plain pixels.
    if factor <= 1.05:
        return 1
    return max(1, min(MAX_SCALE, math.ceil(factor - 0.02)))


def k_of(surface) -> int:
    """Physical pixels per logical pixel of ``surface`` (1 for plain ones)."""
    return _K_OF.get(type(surface), 1)


def stale(surface) -> bool:
    """True for a kept canvas drawn at another factor than the current one."""
    return ACTIVE and _K_OF.get(type(surface), 1) != SCALE


def physical_size(surface) -> tuple:
    return pygame.Surface.get_size(surface)


def _num(value) -> float:
    return float(value)


def _pt(point, k: int):
    c = (k - 1) / 2.0
    return (_num(point[0]) * k + c, _num(point[1]) * k + c)


def _rect(rect, k: int) -> pygame.Rect:
    r = pygame.Rect(rect)
    return pygame.Rect(r.x * k, r.y * k, r.w * k, r.h * k)


def _logical(rect, k: int) -> pygame.Rect:
    r = pygame.Rect(rect)
    left, top = r.x // k, r.y // k
    right, bottom = -(-r.right // k), -(-r.bottom // k)
    return pygame.Rect(left, top, right - left, bottom - top)


def _dest_xy(dest, k: int) -> tuple:
    if isinstance(dest, pygame.Rect):
        x, y = dest.x, dest.y
    else:
        x, y = dest[0], dest[1]
    return int(math.floor(_num(x) * k)), int(math.floor(_num(y) * k))


def _copy_pixels(target, source, offset=(0, 0)) -> None:
    """Copy ``source``'s pixels exactly into the fresh ``target``."""
    blit = pygame.Surface.blit
    if target.get_flags() & pygame.SRCALPHA:
        pygame.Surface.fill(target, (0, 0, 0, 0))
        if source.get_flags() & pygame.SRCALPHA:
            blit(target, source, offset, None, pygame.BLEND_RGBA_MAX)
            return
        alpha = source.get_alpha()
        if alpha is not None and source.get_colorkey() is None:
            source.set_alpha(None)
            try:
                blit(target, source, offset)
            finally:
                source.set_alpha(alpha)
            target.set_alpha(alpha)
            return
        blit(target, source, offset)
        return
    key = source.get_colorkey()
    if key is not None:
        pygame.Surface.fill(target, key)
        target.set_colorkey(key)
    alpha = source.get_alpha()
    source.set_alpha(None)
    try:
        blit(target, source, offset)
    finally:
        if alpha is not None:
            source.set_alpha(alpha)
    if alpha is not None:
        target.set_alpha(alpha)


def adopt(physical: pygame.Surface, k: int) -> pygame.Surface:
    """A canvas of factor ``k`` holding the pixels of a plain ``physical``
    surface (padded to whole logical pixels)."""
    pw, ph = physical.get_size()
    lw, lh = max(1, -(-pw // k)), max(1, -(-ph // k))
    flags = physical.get_flags() & pygame.SRCALPHA
    if flags:
        out = surface_class(k)((lw * k, lh * k), flags, 32)
    else:
        out = surface_class(k)((lw * k, lh * k), 0, 32, OPAQUE_MASKS)
    _copy_pixels(out, physical)
    return out


def to_factor(source, k: int):
    """``source`` as drawn at factor ``k`` (scaled when its factor differs)."""
    ks = k_of(source)
    if ks == k:
        return source
    pw, ph = pygame.Surface.get_size(source)
    size = (max(1, pw * k // ks), max(1, ph * k // ks))
    if size == (pw, ph):
        return source
    scale = _RAW.get("scale", pygame.transform.scale)
    if k > ks and k % ks == 0:
        scaled = scale(source, size)
    else:
        scaled = _RAW.get("smoothscale", pygame.transform.smoothscale)(source, size) \
            if source.get_bitsize() in (24, 32) else scale(source, size)
    return scaled if k == 1 else adopt(scaled, k)


class _Hi(pygame.Surface):
    """A canvas with ``K`` physical pixels per logical pixel."""

    K = 1

    def get_size(self):
        w, h = pygame.Surface.get_size(self)
        return (w // self.K, h // self.K)

    def get_width(self):
        return pygame.Surface.get_width(self) // self.K

    def get_height(self):
        return pygame.Surface.get_height(self) // self.K

    def get_rect(self, **kwargs):
        rect = pygame.Rect((0, 0), self.get_size())
        for name, value in kwargs.items():
            setattr(rect, name, value)
        return rect

    def get_frect(self, **kwargs):  # pragma: no cover - pygame-ce only
        return self.get_rect(**kwargs)

    def get_clip(self):
        return _logical(pygame.Surface.get_clip(self), self.K)

    def set_clip(self, rect=None):
        if rect is None:
            pygame.Surface.set_clip(self, None)
        else:
            pygame.Surface.set_clip(self, _rect(rect, self.K))

    def fill(self, color, rect=None, special_flags=0):
        k = self.K
        if rect is not None:
            rect = _rect(rect, k)
        return _logical(pygame.Surface.fill(self, color, rect, special_flags), k)

    def blit(self, source, dest=(0, 0), area=None, special_flags=0):
        k = self.K
        source = to_factor(source, k)
        if area is not None:
            area = _rect(area, k)
        drawn = pygame.Surface.blit(self, source, _dest_xy(dest, k), area, special_flags)
        return _logical(drawn, k)

    def blits(self, blit_sequence, doreturn=1):
        rects = [self.blit(*item) for item in blit_sequence]
        return rects if doreturn else None

    def subsurface(self, *rect):
        rect = rect[0] if len(rect) == 1 else rect
        return pygame.Surface.subsurface(self, _rect(rect, self.K))

    def get_at(self, pos):
        k = self.K
        return pygame.Surface.get_at(self, (int(pos[0]) * k, int(pos[1]) * k))

    def set_at(self, pos, color):
        k = self.K
        pygame.Surface.fill(self, color, (int(pos[0]) * k, int(pos[1]) * k, k, k))

    def get_bounding_rect(self, min_alpha=1):
        return _logical(pygame.Surface.get_bounding_rect(self, min_alpha), self.K)

    def scroll(self, dx=0, dy=0):
        pygame.Surface.scroll(self, int(dx) * self.K, int(dy) * self.K)

    def get_offset(self):
        x, y = pygame.Surface.get_offset(self)
        return (x // self.K, y // self.K)

    def get_abs_offset(self):
        x, y = pygame.Surface.get_abs_offset(self)
        return (x // self.K, y // self.K)


def surface_class(k: int):
    cls = _CLASSES.get(k)
    if cls is None:
        cls = type(f"HiSurface{k}", (_Hi,), {"K": k})
        _CLASSES[k] = cls
        _K_OF[cls] = k
    return cls


def surface(size, flags: int = 0, depth=None, masks=None) -> pygame.Surface:
    """A new canvas of logical ``size`` at the current factor.

    Before the first large window this is exactly ``pygame.Surface``."""
    if not ACTIVE:
        if depth is None:
            return pygame.Surface(size, flags)
        if masks is None:
            return pygame.Surface(size, flags, depth)
        return pygame.Surface(size, flags, depth, masks)
    k = SCALE
    w, h = int(size[0]), int(size[1])
    physical = (max(0, w) * k, max(0, h) * k)
    if isinstance(depth, pygame.Surface):
        return surface_class(k)(physical, flags, depth)
    if depth is None and not flags & pygame.SRCALPHA:
        return surface_class(k)(physical, flags, 32, OPAQUE_MASKS)
    if depth is None:
        depth = 32
    if masks is None:
        return surface_class(k)(physical, flags, depth)
    return surface_class(k)(physical, flags, depth, masks)


def canvas(size) -> pygame.Surface:
    """The opaque main canvas at the current factor: explicit 32-bit RGB
    without an alpha channel (the macOS window format carries alpha, see
    ``game_shared.make_canvas``)."""
    w, h = int(size[0]), int(size[1])
    if not ACTIVE:
        return pygame.Surface((w, h), 0, 32, OPAQUE_MASKS)
    return surface_class(SCALE)((w * SCALE, h * SCALE), 0, 32, OPAQUE_MASKS)


# --- wrapped drawing functions ---------------------------------------------

def _wrap_line(raw):
    def line(surface, color, start_pos, end_pos, width=1):
        k = _K_OF.get(type(surface))
        if k is None or k == 1:
            return raw(surface, color, start_pos, end_pos, width)
        if width < 1:
            return pygame.Rect(0, 0, 0, 0)
        return _logical(raw(surface, color, _pt(start_pos, k), _pt(end_pos, k),
                            int(width) * k), k)
    return line


def _wrap_lines(raw):
    def lines(surface, color, closed, points, width=1):
        k = _K_OF.get(type(surface))
        if k is None or k == 1:
            return raw(surface, color, closed, points, width)
        if width < 1:
            return pygame.Rect(0, 0, 0, 0)
        return _logical(raw(surface, color, closed, [_pt(p, k) for p in points],
                            int(width) * k), k)
    return lines


def _wrap_aaline(raw, line_raw):
    def aaline(surface, color, start_pos, end_pos, blend=1):
        k = _K_OF.get(type(surface))
        if k is None or k == 1:
            return raw(surface, color, start_pos, end_pos, blend)
        return _logical(line_raw(surface, color, _pt(start_pos, k), _pt(end_pos, k), k), k)
    return aaline


def _wrap_aalines(raw, lines_raw):
    def aalines(surface, color, closed, points, blend=1):
        k = _K_OF.get(type(surface))
        if k is None or k == 1:
            return raw(surface, color, closed, points, blend)
        return _logical(lines_raw(surface, color, closed, [_pt(p, k) for p in points], k), k)
    return aalines


def _wrap_polygon(raw):
    def polygon(surface, color, points, width=0):
        k = _K_OF.get(type(surface))
        if k is None or k == 1:
            return raw(surface, color, points, width)
        return _logical(raw(surface, color, [_pt(p, k) for p in points],
                            int(width) * k), k)
    return polygon


_RADII = ("border_radius", "border_top_left_radius", "border_top_right_radius",
          "border_bottom_left_radius", "border_bottom_right_radius")


def _wrap_rect(raw):
    def rect(surface, color, rect, width=0, *args, **kwargs):
        k = _K_OF.get(type(surface))
        if k is None or k == 1:
            return raw(surface, color, rect, width, *args, **kwargs)
        args = tuple(int(v) * k if v > 0 else v for v in args)
        for name in _RADII:
            value = kwargs.get(name)
            if value is not None and value > 0:
                kwargs[name] = int(value) * k
        return _logical(raw(surface, color, _rect(rect, k), int(width) * k,
                            *args, **kwargs), k)
    return rect


def _wrap_circle(raw):
    def circle(surface, color, center, radius, width=0, *args, **kwargs):
        k = _K_OF.get(type(surface))
        if k is None or k == 1:
            return raw(surface, color, center, radius, width, *args, **kwargs)
        if radius < 1:
            # pygame draws nothing below one pixel, at any factor.
            return pygame.Rect(0, 0, 0, 0)
        return _logical(raw(surface, color, _pt(center, k),
                            _num(radius) * k + (k - 1) / 2.0,
                            int(width) * k, *args, **kwargs), k)
    return circle


def _wrap_ellipse(raw):
    def ellipse(surface, color, rect, width=0):
        k = _K_OF.get(type(surface))
        if k is None or k == 1:
            return raw(surface, color, rect, width)
        return _logical(raw(surface, color, _rect(rect, k), int(width) * k), k)
    return ellipse


def _wrap_arc(raw):
    def arc(surface, color, rect, start_angle, stop_angle, width=1):
        k = _K_OF.get(type(surface))
        if k is None or k == 1:
            return raw(surface, color, rect, start_angle, stop_angle, width)
        return _logical(raw(surface, color, _rect(rect, k), start_angle, stop_angle,
                            int(width) * k), k)
    return arc


def _wrap_flip(raw):
    def flip(surface, flip_x, flip_y):
        k = _K_OF.get(type(surface))
        if k is None:
            return raw(surface, flip_x, flip_y)
        return adopt(raw(surface, flip_x, flip_y), k)
    return flip


def _wrap_scaler(raw):
    def scale(surface, size, dest_surface=None):
        k = _K_OF.get(type(surface))
        kd = _K_OF.get(type(dest_surface)) if dest_surface is not None else None
        if k is None and kd is None:
            if dest_surface is None:
                return raw(surface, size)
            return raw(surface, size, dest_surface)
        k = kd or k
        physical = (max(0, int(size[0])) * k, max(0, int(size[1])) * k)
        source = to_factor(surface, k) if _K_OF.get(type(surface)) else surface
        if dest_surface is not None:
            raw(source, physical, dest_surface)
            return dest_surface
        return adopt(raw(source, physical), k)
    return scale


def _wrap_rotate(raw):
    def rotate(surface, angle):
        k = _K_OF.get(type(surface))
        if k is None:
            return raw(surface, angle)
        return adopt(raw(surface, angle), k)
    return rotate


def _wrap_rotozoom(raw):
    def rotozoom(surface, angle, scale):
        k = _K_OF.get(type(surface))
        if k is None:
            return raw(surface, angle, scale)
        return adopt(raw(surface, angle, scale), k)
    return rotozoom


def activate() -> None:
    """Wrap the drawing functions once (the first large window)."""
    global ACTIVE
    if ACTIVE:
        return
    draw, transform = pygame.draw, pygame.transform
    for name in ("line", "lines", "aaline", "aalines", "polygon", "rect",
                 "circle", "ellipse", "arc"):
        _RAW[name] = getattr(draw, name)
    for name in ("flip", "scale", "smoothscale", "rotate", "rotozoom"):
        _RAW[name] = getattr(transform, name)
    draw.line = _wrap_line(_RAW["line"])
    draw.lines = _wrap_lines(_RAW["lines"])
    draw.aaline = _wrap_aaline(_RAW["aaline"], _RAW["line"])
    draw.aalines = _wrap_aalines(_RAW["aalines"], _RAW["lines"])
    draw.polygon = _wrap_polygon(_RAW["polygon"])
    draw.rect = _wrap_rect(_RAW["rect"])
    draw.circle = _wrap_circle(_RAW["circle"])
    draw.ellipse = _wrap_ellipse(_RAW["ellipse"])
    draw.arc = _wrap_arc(_RAW["arc"])
    transform.flip = _wrap_flip(_RAW["flip"])
    transform.scale = _wrap_scaler(_RAW["scale"])
    transform.smoothscale = _wrap_scaler(_RAW["smoothscale"])
    transform.rotate = _wrap_rotate(_RAW["rotate"])
    transform.rotozoom = _wrap_rotozoom(_RAW["rotozoom"])
    ACTIVE = True


def deactivate() -> None:
    """Restore the plain drawing functions (tests)."""
    global ACTIVE, SCALE
    if not ACTIVE:
        return
    for name in ("line", "lines", "aaline", "aalines", "polygon", "rect",
                 "circle", "ellipse", "arc"):
        setattr(pygame.draw, name, _RAW[name])
    for name in ("flip", "scale", "smoothscale", "rotate", "rotozoom"):
        setattr(pygame.transform, name, _RAW[name])
    _RAW.clear()
    ACTIVE = False
    SCALE = 1


def set_scale(k: int) -> bool:
    """Make ``k`` the factor of new canvases; True when it changed."""
    global SCALE
    k = max(1, min(MAX_SCALE, int(k)))
    if k > 1:
        activate()
    if k == SCALE:
        return False
    SCALE = k
    return True


def raw(name: str):
    """The unwrapped ``pygame.draw``/``pygame.transform`` function."""
    if name in _RAW:
        return _RAW[name]
    module = pygame.draw if hasattr(pygame.draw, name) else pygame.transform
    return getattr(module, name)


def scaled_pixels(small: pygame.Surface, size) -> pygame.Surface:
    """A plain pixel picture (a waterfall) stretched to logical ``size``,
    straight to the current factor's physical pixels."""
    if not ACTIVE or SCALE == 1:
        return pygame.transform.scale(small, size)
    out = surface(size)
    raw("scale")(small, pygame.Surface.get_size(out), out)
    return out


# --- platform ----------------------------------------------------------------

def prepare_platform(platform: str | None = None, env=None) -> None:
    """Before ``pygame.init``: on Windows ask for the screen's real pixels.

    Without it Windows stretches the whole window by its display scaling
    (125 %, 150 %) as a blurred bitmap; with it the game sees the real
    pixels and draws them itself.  Elsewhere nothing changes."""
    import sys
    platform = sys.platform if platform is None else platform
    env = os.environ if env is None else env
    if platform == "win32" and env.get(DISABLE_ENV, "") in ("", "0"):
        env.setdefault("SDL_WINDOWS_DPI_AWARENESS", "permonitorv2")


def display_scale(platform: str | None = None) -> float:
    """Windows' display scaling (1.0 = 100 %); 1.0 elsewhere and headless."""
    import sys
    platform = sys.platform if platform is None else platform
    if platform != "win32" or os.environ.get("SDL_VIDEODRIVER") == "dummy" \
            or os.environ.get(DISABLE_ENV, "") not in ("", "0"):
        return 1.0
    try:
        import ctypes
        dpi = int(ctypes.windll.user32.GetDpiForSystem())
    except (AttributeError, OSError, ValueError, TypeError):
        return 1.0
    return max(1.0, min(4.0, dpi / 96.0)) if dpi > 0 else 1.0


def window_size(canvas_w: int, canvas_h: int, scale: float, desktop=None) -> tuple:
    """The default window: the canvas grown by the display scaling, kept
    inside the desktop (at most 90 % of it, never below the canvas)."""
    w, h = round(canvas_w * scale), round(canvas_h * scale)
    if desktop:
        dw, dh = int(desktop[0] * 0.9), int(desktop[1] * 0.9)
        if w > dw or h > dh:
            fit = min(dw / canvas_w, dh / canvas_h)
            w, h = round(canvas_w * fit), round(canvas_h * fit)
    return (max(canvas_w, w), max(canvas_h, h))


# --- text --------------------------------------------------------------------

class HiFont(pygame.font.Font):
    """A face measured at its logical size and rendered ``k`` times larger.

    ``size``, line height and metrics are the logical face's own, so every
    layout decision matches the 1280x720 canvas; ``render`` returns a canvas
    of factor ``k`` holding the text drawn from the larger face, aligned on
    the logical baseline and never wider than the logical text."""

    def __init__(self, path, em: int, k: int, hi_em: int | None = None):
        super().__init__(path, em)
        self.hi_k = k
        self._hi = pygame.font.Font(path, hi_em or em * k)
        # The larger face may advance a little wider than k logical glyphs;
        # step it down until a line of capitals fits (monospace face).
        probe = "MW0" * 4
        logical = super().size(probe)[0] * k
        size = hi_em or em * k
        while size > em and self._hi.size(probe)[0] > logical:
            size -= 1
            self._hi = pygame.font.Font(path, size)
        self._shift = k * super().get_ascent() - self._hi.get_ascent()

    def render(self, text, antialias=True, color=(255, 255, 255), background=None):
        k = self.hi_k
        w, h = self.size(text)
        if background is None:
            image = self._hi.render(text, antialias, color)
            out = surface_class(k)((max(1, w) * k, max(1, h) * k), pygame.SRCALPHA, 32)
        else:
            image = self._hi.render(text, antialias, color, background)
            out = surface_class(k)((max(1, w) * k, max(1, h) * k), 0, 32, OPAQUE_MASKS)
        width = w * k
        if image.get_width() > width and width > 0:
            smooth = _RAW.get("smoothscale", pygame.transform.smoothscale)
            image = smooth(image.convert_alpha() if background is None else image,
                           (width, image.get_height()))
        if background is None:
            pygame.Surface.fill(out, (0, 0, 0, 0))
            if image.get_flags() & pygame.SRCALPHA:
                pygame.Surface.blit(out, image, (0, self._shift), None,
                                    pygame.BLEND_RGBA_MAX)
            else:
                pygame.Surface.blit(out, image, (0, self._shift))
        else:
            pygame.Surface.fill(out, background)
            pygame.Surface.blit(out, image, (0, self._shift))
        return out
