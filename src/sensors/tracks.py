"""Persistent, smoothed observations without exposing simulation truth."""

import math
from dataclasses import asdict, dataclass, fields

from src.core import config


@dataclass
class SensorTrack:
    track_id: str
    kind: str
    target_id: int
    source: str
    bearing: float
    range_nm: float | None
    x: float | None
    y: float | None
    course: float | None
    quality: float
    last_seen: float
    label: str
    hostile: bool = False
    jamming: bool = False
    raw_bearing: float | None = None
    raw_range_nm: float | None = None
    raw_x: float | None = None
    raw_y: float | None = None
    raw_course: float | None = None
    measurement_epoch: str | None = None
    measurement_history: list[dict] | None = None
    position_seen: float | None = None
    bearing_uncertainty_deg: float | None = None

    def age(self, now: float) -> float:
        return max(0.0, now - self.last_seen)

    def display_quality(self, now: float, stale_s: float) -> float:
        return max(0.0, self.quality * (1.0 - self.age(now) / stale_s))


class TrackPicture:
    """Merge current measurements and retain them briefly after contact loss."""

    def __init__(self, stale_s: float = 8.0):
        self.stale_s = stale_s
        self._tracks: dict[str, SensorTrack] = {}

    @staticmethod
    def _measurement_policy(source: str) -> tuple[float, float]:
        """Return source cadence and smoothing time, both in simulation seconds."""
        if source.startswith("RADAR"):
            return config.OBS_RADAR_EPOCH_S, config.OBS_RADAR_SMOOTH_TAU_S
        if source == "HFDF":
            return 0.5, 2.0
        if source == "ESM":
            return 0.5, 2.0
        if source == "HOJ":
            return 0.5, 1.0
        if source.startswith("SONAR"):
            # Sonar contacts already carry their canonical filtered bearing.
            return 0.0, 0.0
        # Event-produced fixes must not be folded into an unrelated generic epoch.
        return 0.0, config.OBS_BEARING_SMOOTH_TAU_S

    @staticmethod
    def _relative_geometry(x: float, y: float, observer_x: float,
                           observer_y: float) -> tuple[float, float]:
        dx, dy = x - observer_x, y - observer_y
        return (math.degrees(math.atan2(dx, -dy)) % 360.0,
                math.hypot(dx, dy))

    def observe(self, *, track_id: str, kind: str, target_id: int,
                source: str, bearing: float, range_nm: float | None,
                observer_x: float, observer_y: float, course: float | None,
                quality: float, now: float, label: str,
                hostile: bool = False, jamming: bool = False,
                position_time: float | None = None,
                bearing_uncertainty_deg: float | None = None) -> SensorTrack:
        raw_bearing = bearing % 360.0
        x = y = None
        if range_nm is not None:
            x = observer_x + range_nm * math.sin(math.radians(raw_bearing))
            y = observer_y - range_nm * math.cos(math.radians(raw_bearing))
        epoch_s, tau = self._measurement_policy(source)
        epoch_index = (math.floor((now + 1e-9) / epoch_s)
                       if epoch_s > 0.0 else f"{now:.9f}")
        epoch = f"{source}:{epoch_index}"
        measurement = dict(t=now, bearing=raw_bearing, range_nm=range_nm,
                            x=x, y=y, observer_x=observer_x,
                            observer_y=observer_y, course=course,
                            bearing_uncertainty_deg=bearing_uncertainty_deg)
        track = self._tracks.get(track_id)
        if track is not None and track.age(now) > self.stale_s:
            # Reacquisition is simulation-owned, independent of intervening views.
            track = None
        if track is None:
            track = SensorTrack(
                track_id=track_id, kind=kind, target_id=target_id, source=source,
                bearing=raw_bearing, range_nm=range_nm, x=x, y=y, course=course,
                quality=quality, last_seen=now, label=label, hostile=hostile,
                jamming=jamming, raw_bearing=raw_bearing,
                raw_range_nm=range_nm, raw_x=x, raw_y=y, raw_course=course,
                measurement_epoch=epoch, measurement_history=[measurement],
                position_seen=(position_time if position_time is not None else now)
                if x is not None else None,
                bearing_uncertainty_deg=bearing_uncertainty_deg)
            measurement["track_bearing"] = track.bearing
            self._tracks[track_id] = track
        else:
            if epoch == track.measurement_epoch or now <= track.last_seen:
                return track
            previous_source = track.source
            track.kind = kind
            track.target_id = target_id
            track.source = source
            track.quality = quality
            track.last_seen = now
            track.label = label
            track.hostile = hostile
            track.jamming = jamming
            track.raw_bearing = raw_bearing
            track.raw_range_nm = range_nm
            track.raw_x, track.raw_y = x, y
            track.raw_course = course
            track.bearing_uncertainty_deg = bearing_uncertainty_deg
            if track.measurement_history is None:
                track.measurement_history = []
            last_t = (track.measurement_history[-1]["t"]
                      if track.measurement_history else now - max(epoch_s, 1.0))
            alpha = (1.0 if tau <= 0.0 else
                     1.0 - math.exp(-max(0.0, now - last_t) / tau))
            if source != previous_source:
                alpha = 1.0
            if x is not None and y is not None:
                if track.x is None or track.y is None:
                    track.x, track.y = x, y
                else:
                    track.x += (x - track.x) * alpha
                    track.y += (y - track.y) * alpha
                track.position_seen = position_time if position_time is not None else now
            elif (source == "SONAR-BRG" or track.position_seen is None
                  or now - track.position_seen > self.stale_s):
                track.range_nm = track.x = track.y = None
                track.position_seen = None
            if track.x is not None and track.y is not None:
                track.bearing, track.range_nm = self._relative_geometry(
                    track.x, track.y, observer_x, observer_y)
            else:
                track.bearing = (track.bearing + config.angle_diff_deg(
                    raw_bearing, track.bearing) * alpha) % 360.0
            if course is None or track.course is None:
                track.course = course
            else:
                track.course = (track.course + config.angle_diff_deg(
                    course, track.course) * alpha) % 360.0
            measurement["track_bearing"] = track.bearing
            track.measurement_history.append(measurement)
            del track.measurement_history[:-config.OBS_HISTORY_MAX]
            track.measurement_epoch = epoch
        return track

    def expire(self, now: float) -> None:
        self._tracks = {key: track for key, track in self._tracks.items()
                        if track.age(now) <= self.stale_s}

    def tracks(self, now: float, kinds: tuple[str, ...] | None = None) -> list[SensorTrack]:
        result = [track for track in self._tracks.values()
                  if track.age(now) <= self.stale_s]
        if kinds is not None:
            result = [track for track in result if track.kind in kinds]
        return sorted(result, key=lambda track: track.track_id)

    def serialize(self) -> list[dict]:
        return [asdict(track) for track in self._tracks.values()]

    def restore(self, rows: list[dict]) -> None:
        self._tracks = {}
        names = {field.name for field in fields(SensorTrack)}
        for row in rows:
            values = {key: value for key, value in row.items() if key in names}
            track = SensorTrack(**values)
            if track.raw_bearing is None:
                track.raw_bearing = track.bearing
                track.raw_range_nm = track.range_nm
                track.raw_x, track.raw_y = track.x, track.y
                track.raw_course = track.course
            if track.measurement_history is None:
                track.measurement_history = []
            if (track.position_seen is None
                    and track.x is not None and track.y is not None):
                track.position_seen = track.last_seen
            self._tracks[track.track_id] = track
