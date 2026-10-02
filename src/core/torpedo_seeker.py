"""What a crew hears of a homing torpedo's seeker: the terminal phase.

An active seeker pings slowly while it searches and much faster once it has
acquired something (as real homing torpedoes do).  The crew of the frigate
and of the crewed boat hears those pings on its own measured bearing and
reads three things from them:

* the ping rate: searching or locked on ("Torpedo hat aufgeschaltet");
* a bearing that stands still while the pings grow: collision course
  ("Peilung steht"), a least-squares bearing rate over the last seconds;
* a rough torpedo clock: time to impact from a range guessed by ear (the
  true range off by a stateless draw of ``RANGE_ERROR``) and an assumed
  homing-torpedo speed.  It is meant to be rough.

The ears below are transient display state (never saved): after a load the
crew simply listens again.  They only produce sound cues and crew reports,
never simulation changes, so the weapon's behaviour stays as it was.
"""

from __future__ import annotations

import math
from collections import deque

from src.core import detrand

SEARCH_PING_S = 2.0
LOCKED_PING_S = 0.5
STEADY_WINDOW_S = 10.0
STEADY_MIN_SPAN_S = 8.0
STEADY_MIN_SAMPLES = 12
STEADY_RATE_DEG_S = 0.4
# The crew's guess of a homing torpedo's speed and how far off its ear is.
ASSUMED_KN = 45.0
RANGE_ERROR = 0.3
RANGE_EPOCH_S = 5.0
TTI_MAX_S = 900.0
SAMPLES_MAX = 64


def ping_period(acquired: bool) -> float:
    return LOCKED_PING_S if acquired else SEARCH_PING_S


def bearing_rate(samples) -> float | None:
    """Least-squares bearing rate (deg/s) of ``(t, bearing)`` samples, the
    bearings unwrapped around the first; None with too few or too short."""
    rows = list(samples)
    if len(rows) < STEADY_MIN_SAMPLES or rows[-1][0] - rows[0][0] < STEADY_MIN_SPAN_S:
        return None
    first = rows[0][1]
    ts = [t for t, _ in rows]
    bs = [first + ((b - first + 180.0) % 360.0 - 180.0) for _, b in rows]
    mt, mb = sum(ts) / len(ts), sum(bs) / len(bs)
    var = sum((t - mt) ** 2 for t in ts)
    if var <= 0.0:
        return None
    return sum((t - mt) * (b - mb) for t, b in zip(ts, bs)) / var


def estimated_tti(distance_nm: float, seed: int, key: int, sim_t: float) -> float:
    """The crew's rough time to impact (s) from a range guessed by ear."""
    epoch = math.floor(sim_t / RANGE_EPOCH_S)
    guess = distance_nm * max(0.3, 1.0 + RANGE_ERROR * detrand.normal(seed, "torp-ear", key, epoch))
    return min(TTI_MAX_S, guess / (ASSUMED_KN / 3600.0))


class SeekerEar:
    """One crew's ear for torpedo seekers (transient, never saved)."""

    def __init__(self) -> None:
        self.ticks: dict = {}
        self.samples: dict = {}
        self.reported: dict = {}

    def hear(self, key, bearing: float, sim_t: float, acquired: bool) -> list[str]:
        """Events of one audible seeker now: ``ping`` (a ping is due),
        ``steady`` (the bearing stands, reported once)."""
        events = []
        period = ping_period(acquired)
        phase = (hash_key(key) % 1000) / 1000.0 * period
        tick = (acquired, math.floor((sim_t + phase) / period))
        if self.ticks.get(key) != tick:
            if key in self.ticks:
                events.append("ping")
            self.ticks[key] = tick
        rows = self.samples.setdefault(key, deque(maxlen=SAMPLES_MAX))
        if not rows or sim_t - rows[-1][0] >= 0.5:
            rows.append((sim_t, float(bearing)))
        while rows and sim_t - rows[0][0] > STEADY_WINDOW_S:
            rows.popleft()
        rate = bearing_rate(rows)
        reported = self.reported.setdefault(key, set())
        if rate is not None and abs(rate) <= STEADY_RATE_DEG_S and "steady" not in reported:
            reported.add("steady")
            events.append("steady")
        return events

    def forget(self, live_keys) -> None:
        live = set(live_keys)
        for table in (self.ticks, self.samples, self.reported):
            for key in [key for key in table if key not in live]:
                del table[key]


def hash_key(key) -> int:
    """A stable small integer of a key (no hash randomization)."""
    if isinstance(key, int):
        return abs(key)
    return sum((index + 1) * ord(char) for index, char in enumerate(str(key)))
