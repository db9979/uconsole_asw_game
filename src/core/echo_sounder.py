"""The crewed boat's echo-sounder trace (display only, never saved).

The navigation page draws the water depth under the keel over the last
minutes beside the boat's own depth.  The samples are own-ship truth only:
the boat's position, its depth and the sounding under it (the depth the boat
already measures for its keel warning).  The trace is bounded, sampled on
simulation time and never feeds back into the simulation; a loaded boat
starts with an empty trace.
"""

from collections import deque
import math

# One sample every SAMPLE_S simulation seconds, WINDOW_S of history.
SAMPLE_S = 5.0
WINDOW_S = 600.0
SAMPLES_MAX = int(WINDOW_S / SAMPLE_S)


class EchoSounder:
    """Bounded ring of ``(t, x_nm, y_nm, bottom_m, depth_m)`` samples, oldest first."""

    def __init__(self):
        self.samples = deque(maxlen=SAMPLES_MAX)
        self._next_t = None

    def clear(self) -> None:
        self.samples.clear()
        self._next_t = None

    def sample(self, sim_t: float, x_nm: float, y_nm: float, bottom_m, depth_m: float) -> bool:
        """Record one sounding when the next sample is due; True if taken.

        A sounding that is not a finite depth (no reading yet, land) is
        skipped and leaves the schedule unchanged."""
        sim_t = float(sim_t)
        if self.samples and sim_t < self.samples[-1][0]:
            # A clock that went backwards (another world) restarts the trace.
            self.clear()
        if self._next_t is not None and sim_t + 1e-9 < self._next_t:
            return False
        if bottom_m is None or depth_m is None:
            return False
        values = (float(x_nm), float(y_nm), float(bottom_m), float(depth_m))
        if not all(math.isfinite(value) for value in values):
            return False
        x_nm, y_nm, bottom_m, depth_m = values
        self.samples.append((sim_t, x_nm, y_nm, max(0.0, bottom_m), max(0.0, depth_m)))
        self._next_t = sim_t + SAMPLE_S
        return True

    def window(self, now: float) -> list:
        """Samples of the last WINDOW_S seconds before ``now`` (oldest first)."""
        return [row for row in self.samples if 0.0 <= now - row[0] <= WINDOW_S + 1e-9]

    def least_clearance(self, now: float):
        """Smallest keel clearance over the window, else None."""
        rows = self.window(now)
        return min((bottom - depth for _t, _x, _y, bottom, depth in rows), default=None)
