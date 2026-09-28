"""Display settings of the lookout's binoculars and the periscope's
eyepiece: elevation, magnification and the horizon stabilizer.

Presentation only: the settings change the picture, never what the optics
detect (the sightings come from the contrast model), and are not saved.
"""

from __future__ import annotations

from src.core import config


class Optics:
    """Elevation (degrees, up positive), a magnification step and whether
    the stabilizer takes out the hull's motion."""

    def __init__(self, fov_deg: float, powers: tuple, elevation: tuple):
        self.base_fov_deg = float(fov_deg)
        self.powers = tuple(float(power) for power in powers)
        self.elevation_min, self.elevation_max = elevation
        self.reset()

    def reset(self) -> None:
        self.elevation_deg = 0.0
        self.power_index = 0
        self.stabilized = False

    @property
    def power(self) -> float:
        return self.powers[self.power_index]

    @property
    def fov_deg(self) -> float:
        return self.base_fov_deg / self.power

    def tilt(self, delta_deg: float) -> None:
        self.elevation_deg = config.clamp(self.elevation_deg + delta_deg,
                                          self.elevation_min, self.elevation_max)

    def zoom(self, delta: int) -> None:
        self.power_index = max(0, min(len(self.powers) - 1, self.power_index + delta))

    def toggle_stabilizer(self) -> None:
        self.stabilized = not self.stabilized


def lookout_glasses() -> Optics:
    return Optics(config.LOOKOUT_GLASSES_FOV_DEG, config.LOOKOUT_GLASSES_POWERS,
                  config.LOOKOUT_GLASSES_ELEVATION_DEG)


def periscope() -> Optics:
    return Optics(config.UBOOT_SCOPE_FOV_DEG, config.UBOOT_SCOPE_POWERS,
                  config.UBOOT_SCOPE_ELEVATION_DEG)


def optics_key(game, sight: Optics, key: int, mods: int, zoom_keys=None) -> bool:
    """↑/↓ tilt (Shift: fast), ``zoom_keys`` (out, in; default Q/E) the
    magnification, Space the stabilizer; True when the key was the optics'.
    Reports the new setting in the flash."""
    import pygame
    from src.core.i18n import message
    zoom_out, zoom_in = zoom_keys or (pygame.K_q, pygame.K_e)
    if key in (pygame.K_UP, pygame.K_DOWN):
        step = (config.SIGHT_TILT_STEP_FAST_DEG if mods & pygame.KMOD_SHIFT
                else config.SIGHT_TILT_STEP_DEG)
        sight.tilt(step if key == pygame.K_UP else -step)
        game.flash(message("runtime.optics.elevation",
                           elevation=f"{sight.elevation_deg:+.0f}"), 1.0)
    elif key in (zoom_out, zoom_in):
        sight.zoom(1 if key == zoom_in else -1)
        game.flash(message("runtime.optics.zoom", fov=f"{sight.fov_deg:.0f}",
                           power=f"{sight.power:g}"), 1.0)
    elif key == pygame.K_SPACE:
        sight.toggle_stabilizer()
        game.flash(message("runtime.optics.stabilizer_on" if sight.stabilized
                           else "runtime.optics.stabilizer_off"), 1.0)
    else:
        return False
    return True
