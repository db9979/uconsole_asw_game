"""M15: Sonarboje – passiver Hörer mit begrenztem Batterieleben."""

from src.core import config


class Sonobuoy:
    """Wird vom HSP-5 ausgesetzt; hört Ziele im Umkreis (Sonar-Update)."""

    def __init__(self, x_nm: float, y_nm: float, seq: int):
        self.x = x_nm
        self.y = y_nm
        self.seq = seq
        self.battery_s = config.BUOY_BATTERY_S

    @property
    def active(self) -> bool:
        return self.battery_s > 0.0

    def update(self, dt: float) -> None:
        self.battery_s = max(0.0, self.battery_s - dt)
