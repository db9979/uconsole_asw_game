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
    altitude_m: float | None = None
    # Bridge lookout report (lookout_id label), never an operator annotation.
    visual: str | None = None

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
        # Dismissed correlation suggestions (pair keys, oldest first). Transient
        # like the fusions themselves: never saved, cleared with the picture.
        self.dismissed: dict[str, None] = {}

    def clear(self) -> None:
        self.fusions.clear()
        self.marked.clear()
        self.suppressed.clear()
        self.classifications.clear()
        self.fusion_affiliations.clear()
        self.show_suppressed = False
        self._sequence = 0
        self.dismissed.clear()

    def dismiss(self, key: str) -> None:
        self.dismissed.pop(key, None)
        self.dismissed[key] = None
        while len(self.dismissed) > config.OPZ_SUGGEST_DISMISSED_MAX:
            del self.dismissed[next(iter(self.dismissed))]

    def prune(self, observations) -> None:
        current = {item.observation_id for item in observations}
        self.marked.intersection_update(current)
        for key in [key for key in self.dismissed
                    if not set(key.split("+")) <= current]:
            del self.dismissed[key]
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
        # Course and speed: quality-weighted over the members that report them.
        steered = [(item, weight) for item, weight in zip(members, weights)
                   if item.course is not None]
        course = None
        if steered:
            cx = sum(math.sin(math.radians(item.course)) * weight for item, weight in steered)
            cy = sum(math.cos(math.radians(item.course)) * weight for item, weight in steered)
            if math.hypot(cx, cy) > 1e-9:
                course = math.degrees(math.atan2(cx, cy)) % 360.0
        timed = [(item, weight) for item, weight in zip(members, weights)
                 if item.speed_kn is not None]
        speed = (sum(item.speed_kn * weight for item, weight in timed)
                 / sum(weight for _, weight in timed)) if timed else None
        return OPZObservation(
            fusion.fusion_id, "FUSION", "UNKNOWN", bearing, range_nm, x, y,
            course, sum(weights) / len(weights), max(item.last_seen for item in members),
            fusion.fusion_id, self.classifications.get(fusion.fusion_id),
            max((item.bearing_uncertainty_deg or 0.0) for item in members),
            position_seen, members=fusion.members, speed_kn=speed)

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


@dataclass(frozen=True)
class CorrelationSuggestion:
    """A candidate pairing of two published reports; never applied by itself."""
    key: str
    members: tuple[str, str]
    bearing: float
    bearing_delta_deg: float
    distance_nm: float | None
    score: float
    course_delta_deg: float | None = None
    speed_delta_kn: float | None = None
    class_match: bool | None = None


# Sensor families whose reports may be suggested together (different families
# only). Remote reports (buoys, dipping sonar, helicopter MAD), home-on-jam
# strobes, datalinked own weapons and fusions are never suggested.
_REMOTE_PREFIXES = ("SONAR-BUOY", "SONAR-DIP", "HELO")
_AIR_KINDS = ("FLG", "ASM", "AIR", "HELO")


def suggestion_key(members) -> str:
    return "+".join(sorted(members))


def _sensor_family(observation) -> str | None:
    source = observation.source
    if source.startswith(_REMOTE_PREFIXES):
        return None
    if source.startswith("SONAR"):
        return "SONAR"
    if source.startswith("RADAR"):
        return "RADAR"
    if source == "ESM":
        return "ESM"
    if source == "LOOKOUT":
        return "VISUAL"
    if source == "AIS":
        return "AIS"
    return None


# Operator classes an AIS transmitter (a declared merchant) can never be.
_NOT_AIS_CLASSES = ("U_BOOT", "BIOLOGISCH", "FLUGZEUG")


def _motion_terms(first, second):
    """(course delta, speed delta, score terms) of two reports, or None when
    their motion rules the pairing out. Terms are fractions of their gates."""
    terms = []
    course_delta = speed_delta = None
    speeds = [item.speed_kn for item in (first, second) if item.speed_kn is not None]
    moving = not speeds or max(speeds) >= config.OPZ_SUGGEST_MIN_SPEED_KN
    if first.course is not None and second.course is not None and moving:
        course_delta = abs(config.angle_diff_deg(first.course, second.course))
        if course_delta > config.OPZ_SUGGEST_COURSE_DEG:
            return None
        terms.append(course_delta / config.OPZ_SUGGEST_COURSE_DEG)
    if first.speed_kn is not None and second.speed_kn is not None:
        speed_delta = abs(first.speed_kn - second.speed_kn)
        gate = (config.OPZ_SUGGEST_SPEED_KN
                + config.OPZ_SUGGEST_SPEED_SHARE * max(first.speed_kn, second.speed_kn))
        if speed_delta > gate:
            return None
        terms.append(speed_delta / gate)
    return course_delta, speed_delta, terms


def _class_match(first, family_a, second, family_b):
    """True/False for two classified reports, None when unknown; "reject"
    when their signatures cannot belong to one contact."""
    for item, other_family in ((first, family_b), (second, family_a)):
        if other_family == "AIS" and item.classification in _NOT_AIS_CLASSES:
            return "reject"
    if first.classification is None or second.classification is None:
        return None
    if first.classification != second.classification:
        return "reject"
    return True


def _own_bearing(observation, own_x: float, own_y: float, observer_nm: float):
    """Bearing (and position) of a report as seen from the frigate, or None."""
    if observation.x is not None and observation.y is not None:
        dx, dy = observation.x - own_x, observation.y - own_y
        return (math.degrees(math.atan2(dx, -dy)) % 360.0,
                (observation.x, observation.y), math.hypot(dx, dy))
    if (observation.observer_x is not None and observation.observer_y is not None
            and math.hypot(observation.observer_x - own_x,
                           observation.observer_y - own_y) > observer_nm):
        return None
    return observation.bearing % 360.0, None, None


def suggest_correlations(observations, own_x: float, own_y: float, now: float, *,
                         fused=(), dismissed=(), limit: int | None = None,
                         ) -> tuple[CorrelationSuggestion, ...]:
    """Suggest cross-sensor pairings from detached OPZ reports only.

    Pure and bounded: the same reports, own position and time always give the
    same suggestions in the same order. Each report appears in at most one
    suggestion; reports already fused and dismissed pairings are skipped.
    """
    limit = config.OPZ_SUGGEST_MAX if limit is None else limit
    fused = set(fused)
    dismissed = set(dismissed)
    candidates = []
    for item in observations:
        family = _sensor_family(item)
        max_age = (config.OPZ_SUGGEST_AIS_MAX_AGE_S if family == "AIS"
                   else config.OPZ_SUGGEST_MAX_AGE_S)
        if (family is None or item.observation_id in fused
                or not 0.0 <= now - item.last_seen <= max_age):
            continue
        geometry = _own_bearing(item, own_x, own_y, config.OPZ_SUGGEST_OBSERVER_NM)
        if geometry is None:
            continue
        candidates.append((item, family, *geometry))
    candidates.sort(key=lambda row: (-row[0].last_seen, row[0].observation_id))
    del candidates[config.OPZ_SUGGEST_CANDIDATES_MAX:]
    candidates.sort(key=lambda row: row[0].observation_id)
    pairs = []
    for index, (first, family_a, bearing_a, pos_a, range_a) in enumerate(candidates):
        for second, family_b, bearing_b, pos_b, range_b in candidates[index + 1:]:
            if family_a == family_b:
                continue
            if ("SONAR" in (family_a, family_b) or "AIS" in (family_a, family_b)) and (
                    first.kind in _AIR_KINDS or second.kind in _AIR_KINDS):
                continue
            key = suggestion_key((first.observation_id, second.observation_id))
            if key in dismissed:
                continue
            unc_a = (first.bearing_uncertainty_deg
                     if first.bearing_uncertainty_deg is not None
                     else config.OPZ_SUGGEST_BEARING_DEFAULT_UNC_DEG)
            unc_b = (second.bearing_uncertainty_deg
                     if second.bearing_uncertainty_deg is not None
                     else config.OPZ_SUGGEST_BEARING_DEFAULT_UNC_DEG)
            gate = min(config.OPZ_SUGGEST_BEARING_MAX_DEG,
                       config.OPZ_SUGGEST_BEARING_BASE_DEG + math.hypot(unc_a, unc_b))
            delta = abs(config.angle_diff_deg(bearing_a, bearing_b))
            if delta > gate:
                continue
            score = delta / gate
            distance = None
            if pos_a is not None and pos_b is not None:
                distance = math.hypot(pos_a[0] - pos_b[0], pos_a[1] - pos_b[1])
                position_gate = (config.OPZ_SUGGEST_POSITION_NM
                                 + config.OPZ_SUGGEST_POSITION_RANGE_SHARE
                                 * min(range_a, range_b))
                if distance > position_gate:
                    continue
                score = .5 * (score + distance / position_gate)
            motion = _motion_terms(first, second)
            if motion is None:
                continue
            course_delta, speed_delta, terms = motion
            if terms:
                score = (score + sum(terms)) / (1 + len(terms))
            class_match = _class_match(first, family_a, second, family_b)
            if class_match == "reject":
                continue
            if class_match is True:
                score *= config.OPZ_SUGGEST_CLASS_BONUS
            mean = math.degrees(math.atan2(
                math.sin(math.radians(bearing_a)) + math.sin(math.radians(bearing_b)),
                math.cos(math.radians(bearing_a)) + math.cos(math.radians(bearing_b))
            )) % 360.0
            pairs.append(CorrelationSuggestion(
                key, tuple(sorted((first.observation_id, second.observation_id))),
                mean, delta, distance, round(score, 9), course_delta, speed_delta,
                class_match))
    pairs.sort(key=lambda item: (item.score, item.key))
    chosen, used = [], set()
    for pair in pairs:
        if len(chosen) >= limit:
            break
        if used.intersection(pair.members):
            continue
        used.update(pair.members)
        chosen.append(pair)
    return tuple(chosen)
