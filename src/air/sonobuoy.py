"""M15: Sonarboje – passiver Hörer mit begrenztem Batterieleben."""

import math

from src.core import config

BUOY_LEEWAY = 0.02   # windage of the float and antenna, fraction of wind
OWNERS = ("HELO", "MPA")


class Sonobuoy:
    """Wird vom HSP-5 ausgesetzt; hört Ziele im Umkreis (Sonar-Update)."""

    def __init__(self, x_nm: float, y_nm: float, seq: int,
                 mode: str = "PASSIVE", owner: str = "HELO"):
        if mode not in ("PASSIVE", "ACTIVE"):
            raise ValueError("invalid sonobuoy mode")
        if owner not in OWNERS:
            raise ValueError("invalid sonobuoy owner")
        # Who laid it: the helicopter or the patrol aircraft (which must
        # relay its buoys to the ship).
        self.owner = owner
        self.x = x_nm
        self.y = y_nm
        self.seq = seq
        self.mode = mode
        self.last_ping_epoch = -1
        self.battery_s = config.BUOY_BATTERY_S

    @property
    def active(self) -> bool:
        return self.battery_s > 0.0

    def update(self, dt: float, world=None) -> None:
        self.battery_s = max(0.0, self.battery_s - dt)
        if world is None:
            return
        # The float drifts with the surface current (which already carries
        # the 3 % wind drift) plus its own windage on the exposed antenna.
        u, v = world.current_vec(self.x, self.y)
        wind = config.kn_to_nm_per_s(world.wind_speed_kn) * BUOY_LEEWAY
        towards = math.radians((world.wind_from_deg + 180.0) % 360.0)
        self.x += config.kn_to_nm_per_s(u) * dt + wind * math.sin(towards) * dt
        self.y -= config.kn_to_nm_per_s(v) * dt + wind * math.cos(towards) * dt
