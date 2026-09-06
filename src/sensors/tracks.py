"""Persistent observations without exposing simulation objects to views."""

from dataclasses import asdict, dataclass


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
        x = y = None
        if range_nm is not None:
            import math
            x = observer_x + range_nm * math.sin(math.radians(bearing))
            y = observer_y - range_nm * math.cos(math.radians(bearing))
        track = self._tracks.get(track_id)
        if track is None:
            track = SensorTrack(track_id, kind, target_id, source,
                                bearing % 360.0, range_nm, x, y, course,
                                quality, now, label, hostile, jamming)
            self._tracks[track_id] = track
        else:
            track.kind = kind
            track.target_id = target_id
            track.source = source
            track.bearing = bearing % 360.0
            track.range_nm = range_nm
            track.x, track.y = x, y
            track.course = course
            track.quality = quality
            track.last_seen = now
            track.label = label
            track.hostile = hostile
            track.jamming = jamming
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
        for row in rows:
            track = SensorTrack(**row)
            self._tracks[track.track_id] = track
