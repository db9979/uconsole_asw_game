"""Transient, operator-directed OPZ observations and display-only fusions."""

from dataclasses import dataclass
import math

from src.core import config


MAX_OPZ_FUSIONS = config.OPZ_FUSION_MAX
MIN_FUSION_MEMBERS = config.OPZ_FUSION_MEMBER_MIN
MAX_FUSION_MEMBERS = config.OPZ_FUSION_MEMBER_MAX


@dataclass(frozen=True)
class OPZObservation:
    observation_id: str
    source: str
    kind: str
    bearing: float
    range_nm: float | None
    x: float | None
    y: float | None
    course: float | None
    quality: float
    last_seen: float
    label: str
    classification: str | None = None
    bearing_uncertainty_deg: float | None = None
    position_seen: float | None = None
    jamming: bool = False
    members: tuple[str, ...] = ()
    depth_m: float | None = None
    speed_kn: float | None = None
    observer_x: float | None = None
    observer_y: float | None = None
    released_to_opz: bool = False

    @property
    def track_id(self) -> str:
        return self.observation_id

    def __getitem__(self, key):
        aliases = {"track_id": "observation_id", "dist": "range_nm"}
        return getattr(self, aliases.get(key, key))

    def age(self, now: float) -> float:
        return max(0.0, now - self.last_seen)

    def display_quality(self, now: float, stale_s: float) -> float:
        return max(0.0, self.quality * (1.0 - self.age(now) / stale_s))


@dataclass(frozen=True)
class ManualFusion:
    fusion_id: str
    members: tuple[str, ...]
    classification: str | None = None


class OPZFusionPicture:
    """Bounded transient OPZ workspace; it never mutates source pictures."""

    def __init__(self):
        self.fusions: dict[str, ManualFusion] = {}
        self.marked: set[str] = set()
        self.suppressed: set[str] = set()
        self.classifications: dict[str, str] = {}
        self.fusion_affiliations: dict[str, str] = {}
        self.show_suppressed = False
        self._sequence = 0

    def clear(self) -> None:
        self.fusions.clear()
        self.marked.clear()
        self.suppressed.clear()
        self.classifications.clear()
        self.fusion_affiliations.clear()
        self.show_suppressed = False
        self._sequence = 0

    def prune(self, observations) -> None:
        current = {item.observation_id for item in observations}
        self.marked.intersection_update(current)
        self.suppressed.intersection_update(current | set(self.fusions))
        self.classifications = {key: value for key, value in self.classifications.items()
                                if key in current or key in self.fusions}
        for key, fusion in list(self.fusions.items()):
            if not set(fusion.members) <= current:
                del self.fusions[key]
                self.fusion_affiliations.pop(key, None)

    def create(self, observations) -> ManualFusion | None:
        current = {item.observation_id for item in observations}
        members = tuple(sorted(self.marked & current))
        if (not MIN_FUSION_MEMBERS <= len(members) <= MAX_FUSION_MEMBERS
                or len(self.fusions) >= MAX_OPZ_FUSIONS):
            return None
        self._sequence += 1
        key = f"F-{self._sequence:02d}"
        fusion = ManualFusion(key, members)
        self.fusions[key] = fusion
        self.marked.clear()
        return fusion

    def dissolve(self, fusion_id: str) -> bool:
        if fusion_id not in self.fusions:
            return False
        del self.fusions[fusion_id]
        self.suppressed.discard(fusion_id)
        self.classifications.pop(fusion_id, None)
        self.fusion_affiliations.pop(fusion_id, None)
        return True

    def computed(self, fusion: ManualFusion, observations, now: float,
                 stale_s: float) -> OPZObservation | None:
        by_id = {item.observation_id: item for item in observations}
        members = [by_id.get(key) for key in fusion.members]
        if any(item is None for item in members):
            return None
        weights = [max(.001, item.display_quality(now, stale_s)) for item in members]
        positioned = [(item, weight) for item, weight in zip(members, weights)
                      if item.x is not None and item.y is not None]
        x = y = range_nm = position_seen = None
        if positioned:
            total = sum(weight for _, weight in positioned)
            x = sum(item.x * weight for item, weight in positioned) / total
            y = sum(item.y * weight for item, weight in positioned) / total
            position_seen = max(item.position_seen or item.last_seen
                                for item, _ in positioned)
        sx = sum(math.sin(math.radians(item.bearing)) * weight
                 for item, weight in zip(members, weights))
        sy = sum(math.cos(math.radians(item.bearing)) * weight
                 for item, weight in zip(members, weights))
        bearing = math.degrees(math.atan2(sx, sy)) % 360.0
        return OPZObservation(
            fusion.fusion_id, "FUSION", "UNKNOWN", bearing, range_nm, x, y,
            None, sum(weights) / len(weights), max(item.last_seen for item in members),
            fusion.fusion_id, self.classifications.get(fusion.fusion_id),
            max((item.bearing_uncertainty_deg or 0.0) for item in members),
            position_seen, members=fusion.members)

    def visible(self, observations, now: float, stale_s: float):
        self.prune(observations)
        fused = [item for item in (self.computed(fusion, observations, now, stale_s)
                                   for fusion in self.fusions.values()) if item is not None]
        all_items = list(observations) + fused
        return tuple(sorted((item for item in all_items
                            if (item.observation_id in self.suppressed)
                            == self.show_suppressed),
                            key=lambda item: item.observation_id))


def source_classification(observation_id: str, observations) -> str | None:
    """Look up an annotation using detached reports only, never producer labels."""
    return next((item.classification for item in observations
                 if item.observation_id == observation_id), None)
