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

    def age(self, now: float) -> float:
        return max(0.0, now - self.last_seen)

    def display_quality(self, now: float, stale_s: float) -> float:
        return max(0.0, self.quality * (1.0 - self.age(now) / stale_s))


class TrackPicture:
    """Merge current measurements and retain them briefly after contact loss."""

    def __init__(self, stale_s: float = 8.0):
        self.stale_s = stale_s
        self._tracks: dict[str, SensorTrack] = {}

    def observe(self, *, track_id: str, kind: str, target_id: int,
                source: str, bearing: float, range_nm: float | None,
                observer_x: float, observer_y: float, course: float | None,
                quality: float, now: float, label: str,
                hostile: bool = False, jamming: bool = False) -> SensorTrack:
        raw_bearing = bearing % 360.0
        x = y = None
        if range_nm is not None:
            x = observer_x + range_nm * math.sin(math.radians(raw_bearing))
            y = observer_y - range_nm * math.cos(math.radians(raw_bearing))
        epoch_s = (config.OBS_RADAR_EPOCH_S if source.startswith("RADAR")
                   else config.OBS_BEARING_EPOCH_S)
        epoch = f"{source}:{math.floor((now + 1e-9) / epoch_s)}"
        measurement = dict(t=now, bearing=raw_bearing, range_nm=range_nm,
                           x=x, y=y, observer_x=observer_x,
                           observer_y=observer_y, course=course)
        track = self._tracks.get(track_id)
        if track is None:
            track = SensorTrack(
                track_id, kind, target_id, source, raw_bearing, range_nm,
                x, y, course, quality, now, label, hostile, jamming,
                raw_bearing, range_nm, x, y, course, epoch, [measurement])
            self._tracks[track_id] = track
        else:
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
            if track.measurement_history is None:
                track.measurement_history = []
            if epoch != track.measurement_epoch:
                last_t = (track.measurement_history[-1]["t"]
                          if track.measurement_history else now - epoch_s)
                tau = (config.OBS_RADAR_SMOOTH_TAU_S
                       if source.startswith("RADAR")
                       else config.OBS_BEARING_SMOOTH_TAU_S)
                alpha = 1.0 - math.exp(-max(0.0, now - last_t) / tau)
                if source != previous_source:
                    alpha = 1.0
                track.bearing = (track.bearing + config.angle_diff_deg(
                    raw_bearing, track.bearing) * alpha) % 360.0
                if x is None or y is None:
                    track.range_nm = track.x = track.y = None
                elif track.x is None or track.y is None:
                    track.x, track.y = x, y
                    track.range_nm = range_nm
                else:
                    track.x += (x - track.x) * alpha
                    track.y += (y - track.y) * alpha
                    track.range_nm = math.hypot(
                        track.x - observer_x, track.y - observer_y)
                if course is None or track.course is None:
                    track.course = course
                else:
                    track.course = (track.course + config.angle_diff_deg(
                        course, track.course) * alpha) % 360.0
                track.measurement_history.append(measurement)
                del track.measurement_history[:-config.OBS_HISTORY_MAX]
                track.measurement_epoch = epoch
        return track

    def expire(self, now: float) -> None:
        self._tracks = {key: track for key, track in self._tracks.items()
                        if track.age(now) <= self.stale_s}

    def tracks(self, now: float, kinds: tuple[str, ...] | None = None) -> list[SensorTrack]:
        self.expire(now)
        result = list(self._tracks.values())
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
            self._tracks[track.track_id] = track
